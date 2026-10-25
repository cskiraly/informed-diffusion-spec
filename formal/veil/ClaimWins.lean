module

public import Veil

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false

/-! # The claim wins (A1), for any number of nodes, groups and chunks

SEACAST, `protocol.md` v0.5, §4.5 (with §4.1, §4.3, §7.2 and §8.1), and the live window that keeps
an expired group out for good (§8.1, with the group's key of §1, added after v0.6): a node
penalises a peer that asks it for a chunk the peer has claimed. §4.5 argues that an honest node
never does so on a live connection: claims are made only for chunks in `mine`, which only grows
within a group's active lifetime; both lanes of a peer's queue feed one ordered writer; the asker
drops its queued asks for chunks in `mine` just before writing them; RPCs are handled in stream
order, IWANT before IDONTWANT within one; and a group past its active lifetime is never taken up
again. This model proves that argument, for every number of nodes, groups and chunk indices and
every interleaving, as an inductive invariant: Lean's kernel checks a theorem for each action and
clause (`#gen_theorems`), and the SMT solver is not trusted. With the live window the proof needs no
assumption; the fallback for groups without a slot rests on one, the bound on its tombstone's
lifetime (below). The Quint model (`../diffusion.qnt`, monitor `noPenalty`) checks the same
property on small instances.

- **Claims.** A claim is a bit of a HAVE bitmap, sent in an IDONTWANT (§4.3). A node may queue any
  bit it has in `mine`, for any peer, at any time: every HAVE the spec sends, the source's [P4]
  included, is such a snapshot. `mine` grows when a chunk is accepted and at the decode claim (every
  bit, with stop-pull, as the source's publish too); at expiry it goes, leaving the tombstone (§8.1).
- **Asks.** An ask is decided only for a chunk not in `mine`, of a group neither stop-pulled nor
  expired (§4.4, §6.1), and queued for a peer.
- **The queue is a set.** The writer takes queued asks and HAVE bits one at a time, in any order,
  so every lane discipline, rarest at pop, cancel and the owed parts are covered. At the write the
  asker drops an ask for a chunk in `mine`, of a stop-pulled group or of an expired one (§7.2: `held`
  reads `mine`).
- **A link is one ordered stream of RPCs.** Each write starts an RPC after every earlier one, or
  joins the newest if it has not been handled yet (a coalescing transport). The receiver handles the
  oldest RPC, its IWANTs before its IDONTWANTs (§4.1).
- **The penalty.** The receiver penalises an ask for a chunk the asker claimed on this connection,
  unless the group has expired for the receiver (§4.5). A claim lapses (`HAVE_TTL`, here at any
  time) and goes at the receiver's expiry; when a connection closes its claims, queues and RPCs go,
  and a new one starts with none (§8.1).
- **Expiry, the tombstone and the live window.** At the end of its active lifetime a group's state
  goes, leaving its tombstone (§8.1). With the live window, a group whose slot has left the node's
  window is expired too, whatever its active lifetime, and its state goes as at expiry; the
  tombstone goes only then, and since the window only moves forward and a group's key fixes its
  slot (§1: a later bid committing the same descriptor names another group), the group never comes
  back. Without the window, the tombstone can go and the group be taken up again (`forget`). The
  fallback, for groups without a slot, keeps the tombstone `TOMBSTONE_TTL` after the expiry, long
  enough that it goes only once no claim of the group from that node is queued, on a stream or held
  by a peer: the assumption `claimsGoFirst`, since no time is modelled. v0.5 had neither: its
  tombstone lasted "until the seen cache forgets its chunks", which with the stock seen cache can be
  at expiry already. With neither, a known answer below penalises an honest node with every rule
  on; so does a window that moves back.

Not modelled: the chunks themselves (only which are in `mine`), the send window (§7.1), and timers
and lifetimes (a claim may lapse, a group expire, its slot leave the window and its tombstone go, at
any time the rules allow); how a node tells a group's slot (here every node knows it: §8.1 has a
node take up only groups whose slot it can tell, from an installed block or from the chunk); the
other two reasons for a penalty, a chunk that fails level 1 and a malformed HAVE. All nodes are
honest.

The rules the argument rests on are switches, `immutable` Booleans, each on in the spec; so is the
fallback's assumption. The invariants hold where `premises`: the filter, IWANT first and in-order
handling, at least one of the two expiry rules, and the tombstone rule: the live window, moving only
forward, or, without a window, the fallback's assumption. The known answers below are `sat trace`s:
with the filter, IWANT first or in-order handling off, with both expiry rules off, with neither the
window nor the assumption, or with a window that moves back, an honest node is penalised.
-/

veil module ClaimWins

type node
type group
type index
type pos                                     -- the position of an RPC on a link's stream
instantiate ord : TotalOrder pos
open TotalOrder

immutable individual filterAsks : Bool       -- §7.2: the writer drops asks for chunks in mine
immutable individual asksFirst : Bool        -- §4.1: IWANT before IDONTWANT within an RPC
immutable individual inOrder : Bool          -- §4.5: one ordered writer, RPCs handled in order
immutable individual expiryInFilter : Bool   -- §7.2: the writer's filter checks expiry (v0.5)
immutable individual discardAtExpiry : Bool  -- §8.1: expiry discards the group's queued IWANTs
immutable individual liveWindow : Bool       -- §8.1: the live window; the tombstone goes only past it
immutable individual windowForward : Bool    -- §8.1, §1: the window only moves forward; slots are fixed
immutable individual claimsGoFirst : Bool    -- §8.1's fallback, assumed: a tombstone outlives its claims

-- the asker's side
relation mine (n : node) (g : group) (i : index) : Bool
relation stopPull (n : node) (g : group) : Bool
relation tomb (n : node) (g : group) : Bool                          -- the tombstone
relation out (n : node) (g : group) : Bool               -- the group's slot has left n's live window
relation qAsk (a : node) (b : node) (g : group) (i : index) : Bool    -- an IWANT queued at a for b
relation qHave (a : node) (b : node) (g : group) (i : index) : Bool   -- a HAVE bit queued at a for b
-- the stream from a to b
relation used (a : node) (b : node) (t : pos) : Bool       -- a position written on the link
relation rpc (a : node) (b : node) (t : pos) : Bool        -- an RPC written, not yet handled
relation sAsk (a : node) (b : node) (t : pos) (g : group) (i : index) : Bool
relation sHave (a : node) (b : node) (t : pos) (g : group) (i : index) : Bool
-- the receiver's side
relation peerHas (b : node) (a : node) (g : group) (i : index) : Bool   -- what a claimed to b (§4.3)
relation penalised (b : node) (a : node) : Bool    -- b penalised a for an ask (§4.5)
-- history only, for the non-vacuity query below: no action reads it
relation everClaimed (b : node) (a : node) (g : group) (i : index) : Bool

#gen_state

-- the tombstone rule: the live window, moving only forward; or, where groups have no slot and so no
-- window, the fallback's assumption (a window that moves back is not saved by it: the window can
-- end a group that has no tombstone yet)
theory ghost relation tombstoneRule :=
  (liveWindow ∧ windowForward) ∨ (¬ liveWindow ∧ claimsGoFirst)

theory ghost relation premises :=
  filterAsks ∧ asksFirst ∧ inOrder ∧ (expiryInFilter ∨ discardAtExpiry) ∧ tombstoneRule

-- the spec as written: every rule on, with the live window (every group of protocol.md has a slot)
theory ghost relation windowed :=
  filterAsks ∧ asksFirst ∧ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ liveWindow ∧ windowForward ∧
    ¬ claimsGoFirst

-- the fallback: every rule on, no window, and the assumption on the tombstone's lifetime
theory ghost relation fallback :=
  filterAsks ∧ asksFirst ∧ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ ¬ liveWindow ∧
    claimsGoFirst

-- §8.1's `expired`: the tombstone is kept, or the group's slot has left the live window
ghost relation expired (n : node) (g : group) := tomb n g ∨ out n g

-- where a write to b can go: an RPC after every earlier one on the link, or the newest RPC if it
-- has not been handled yet (a coalescing transport)
ghost relation writable (a : node) (b : node) (t : pos) :=
  (∀ T, used a b T → ¬ le t T) ∨ (rpc a b t ∧ ∀ T, used a b T → le T t)

-- the RPC at t is the oldest on the link not yet handled
ghost relation oldest (a : node) (b : node) (t : pos) := ∀ T, rpc a b T → le t T

-- the RPC at t asks b for a chunk that a has claimed to b, of a group alive for b (§4.5): before
-- this RPC, or, with its IDONTWANTs handled first, in it
ghost relation askClaimed (a : node) (b : node) (t : pos) :=
  ∃ g i, sAsk a b t g i ∧ ¬ expired b g ∧ peerHas b a g i
ghost relation askClaimedHere (a : node) (b : node) (t : pos) :=
  ∃ g i, sAsk a b t g i ∧ ¬ expired b g ∧ (peerHas b a g i ∨ sHave a b t g i)

-- nothing is left of n's claims of g: none queued, none on a stream, none held by a peer
ghost relation claimsGone (n : node) (g : group) :=
  ∀ P J T, ¬ qHave n P g J ∧ ¬ sHave n P T g J ∧ ¬ peerHas P n g J

after_init {
  mine N G I := false
  stopPull N G := false
  tomb N G := false
  out N G := false
  qAsk A B G I := false
  qHave A B G I := false
  used A B T := false
  rpc A B T := false
  sAsk A B T G I := false
  sHave A B T G I := false
  peerHas B A G I := false
  penalised B A := false
  everClaimed B A G I := false
}

-- §4.2: a chunk passes level 1 and goes into mine
action accept (n : node) (g : group) (i : index) {
  require ¬ expired n g
  mine n g i := true
}

-- §4.6 (and §5.1 at the source): every bit claimed, no further asks
action claimAll (n : node) (g : group) {
  require ¬ expired n g
  mine n g I := true
  stopPull n g := true
}

-- §8.1: the group's active lifetime ends: it goes, leaving its tombstone; its queued IWANTs go with
-- it, its HAVEs stay, and so do the claims its peers hold of it; the claims it holds of its peers
-- for the group go
action expire (n : node) (g : group) {
  tomb n g := true
  mine n g I := false
  stopPull n g := false
  peerHas n A g I := false
  if discardAtExpiry then
    qAsk n B g I := false
}

-- §8.1: the group's slot leaves the node's live window: the group is expired, whatever its active
-- lifetime, and its state goes as at expiry
action leaveWindow (n : node) (g : group) {
  require liveWindow
  out n g := true
  mine n g I := false
  stopPull n g := false
  peerHas n A g I := false
  if discardAtExpiry then
    qAsk n B g I := false
}

-- a window that moves back (a node whose current slot follows its clock back, or a group named by its
-- group id alone that a later slot's bid commits again, which §1's key rules out): the group's slot
-- is in the window again
action windowBack (n : node) (g : group) {
  require liveWindow ∧ ¬ windowForward
  out n g := false
}

-- §8.1: the tombstone goes. With the live window, only once the group's slot has left it, which
-- then keeps the group out; under the fallback's assumption, only once nothing is left of the
-- node's claims of it; with neither, at any time. Unless the window keeps it out, the group can then
-- be taken up again
action forget (n : node) (g : group) {
  require tomb n g
  require ¬ liveWindow ∨ out n g
  require ¬ claimsGoFirst ∨ claimsGone n g
  tomb n g := false
}

-- §4.3, §8.1: b's record of what a claimed of g lapses (`HAVE_TTL`; here at any time)
action claimLapses (b : node) (a : node) (g : group) {
  peerHas b a g I := false
}

-- §4.4, §6.1: an ask for a chunk not in mine, of a group still pulled and not expired
action decideAsk (a b : node) (g : group) (i : index) {
  require a ≠ b
  require ¬ mine a g i ∧ ¬ stopPull a g ∧ ¬ expired a g
  qAsk a b g i := true
}

-- §4.2, §4.6, §5.1: a HAVE bit from mine, for any peer, at any time
action sendHave (a b : node) (g : group) (i : index) {
  require a ≠ b
  require mine a g i
  qHave a b g i := true
}

-- §7.2: the writer takes queued parts one at a time, in any order; an ask that the filter
-- catches is dropped and nothing is written
action writeAsk (a b : node) (g : group) (i : index) (t : pos) {
  require a ≠ b
  require qAsk a b g i
  require writable a b t
  qAsk a b g i := false
  if ¬ filterAsks ∨ (¬ mine a g i ∧ ¬ stopPull a g ∧ (¬ expiryInFilter ∨ ¬ expired a g)) then
    sAsk a b t g i := true
    rpc a b t := true
    used a b t := true
}

action writeHave (a b : node) (g : group) (i : index) (t : pos) {
  require a ≠ b
  require qHave a b g i
  require writable a b t
  qHave a b g i := false
  sHave a b t g i := true
  rpc a b t := true
  used a b t := true
}

-- §4.1, §4.3, §4.5: b handles the RPC at t from a, the oldest one (any one if inOrder is off)
action handle (a b : node) (t : pos) {
  require rpc a b t
  require ¬ inOrder ∨ oldest a b t
  -- IWANT first: the asks are checked against the claims made before this RPC; IDONTWANT first:
  -- against this RPC's claims too. (Every condition reads the state before the updates, which
  -- use Bool operators: Veil 2.0's trace queries cannot translate `decide` over an update's
  -- quantified variables, nor a ghost relation read after such an update.)
  if (asksFirst ∧ askClaimed a b t) ∨ (¬ asksFirst ∧ askClaimedHere a b t) then
    penalised b a := true
  peerHas b a G I := peerHas b a G I || (sHave a b t G I && !tomb b G && !out b G)
  everClaimed b a G I := everClaimed b a G I || (sHave a b t G I && !tomb b G && !out b G)
  rpc a b t := false
  sAsk a b t G I := false
  sHave a b t G I := false
}

-- §8.1: the connection closes, and its state goes, both ways
action disconnect (a b : node) {
  require a ≠ b
  rpc a b T := false
  sAsk a b T G I := false
  sHave a b T G I := false
  qAsk a b G I := false
  qHave a b G I := false
  peerHas b a G I := false
  rpc b a T := false
  sAsk b a T G I := false
  sHave b a T G I := false
  qAsk b a G I := false
  qHave b a G I := false
  peerHas a b G I := false
}

safety [claim_wins] premises → ¬ penalised B A

-- claims are true: whatever a HAVE says is in mine, unless the group has expired, which under the
-- tombstone rule it stays while any claim of it is left
invariant [have_queued] tombstoneRule → qHave A B G I → mine A G I ∨ expired A G
invariant [have_stream] tombstoneRule → sHave A B T G I → mine A G I ∨ expired A G
invariant [claims_true] tombstoneRule → peerHas B A G I → mine A G I ∨ expired A G
-- no queued ask is of an expired group, where expiry discards them
invariant [queued_alive] discardAtExpiry → qAsk A B G I → ¬ expired A G
-- an ask on the stream has not been claimed, and no claim of its chunk is ahead of it
invariant [ask_unclaimed] premises → sAsk A B T G I → ¬ peerHas B A G I
invariant [ask_before_have] premises → sAsk A B T G I ∧ sHave A B T2 G I → le T T2
-- the stream's bookkeeping
invariant [ask_in_rpc] sAsk A B T G I → rpc A B T
invariant [have_in_rpc] sHave A B T G I → rpc A B T
invariant [rpc_used] rpc A B T → used A B T

#gen_spec

/-! ## Non-vacuity: with every rule on, the cases they exist for happen

`windowed` is the spec as written, with the live window; `fallback` has no window and assumes the
tombstone's bound instead. -/

sat trace [windowed_holds] {
  assert windowed
}

sat trace [fallback_holds] {
  assert fallback
}

-- an ask queued before its chunk arrived, still queued when the claim reaches the peer
sat trace [claim_overtakes_queued_ask] {
  decideAsk
  accept
  sendHave
  writeHave
  handle
  assert (windowed ∧ ∃ A B G I, qAsk A B G I ∧ peerHas B A G I)
}

-- an ask and the claim of its chunk in one RPC
sat trace [ask_and_claim_coalesced] {
  decideAsk
  writeAsk
  accept
  sendHave
  writeHave
  assert (windowed ∧ ∃ A B T G I, sAsk A B T G I ∧ sHave A B T G I)
}

-- with the window: the group's slot has left it and the tombstone has gone, while a peer still
-- holds the node's claim of a chunk the node no longer has; only the window keeps the group out
sat trace [window_keeps_out] {
  accept
  sendHave
  writeHave
  handle
  expire
  leaveWindow
  forget
  assert (windowed ∧ ∃ A B G I, ¬ tomb A G ∧ ¬ mine A G I ∧ peerHas B A G I)
}

-- under the fallback, a group taken up again after its tombstone went: an ask on its way to a
-- peer, for a chunk the asker once claimed to that peer
sat trace [taken_up_again] {
  accept
  sendHave
  writeHave
  handle
  claimLapses
  expire
  forget
  decideAsk
  writeAsk
  assert (fallback ∧ ∃ A B T G I, sAsk A B T G I ∧ everClaimed B A G I)
}

/-! ## Known answers: an honest node is penalised with any of the first three rules off, with both
expiry rules off (either alone suffices: the proof holds with one), with neither the window nor the
fallback's assumption, or with a window that moves back; every other rule on, with the window -/

sat trace [ka_no_filter] {
  decideAsk
  accept
  sendHave
  writeHave
  handle
  writeAsk
  handle
  assert (¬ filterAsks ∧ asksFirst ∧ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ liveWindow ∧
    windowForward ∧ ¬ claimsGoFirst ∧ ∃ B A, penalised B A)
}

sat trace [ka_claim_first_in_rpc] {
  decideAsk
  writeAsk
  accept
  sendHave
  writeHave
  handle
  assert (filterAsks ∧ ¬ asksFirst ∧ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ liveWindow ∧
    windowForward ∧ ¬ claimsGoFirst ∧ ∃ B A, penalised B A)
}

sat trace [ka_out_of_order] {
  decideAsk
  writeAsk
  accept
  sendHave
  writeHave
  handle
  handle
  assert (filterAsks ∧ asksFirst ∧ ¬ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ liveWindow ∧
    windowForward ∧ ¬ claimsGoFirst ∧ ∃ B A, penalised B A)
}

sat trace [ka_expiry_unchecked] {
  decideAsk
  accept
  sendHave
  writeHave
  handle
  expire
  writeAsk
  handle
  assert (filterAsks ∧ asksFirst ∧ inOrder ∧ ¬ expiryInFilter ∧ ¬ discardAtExpiry ∧ liveWindow ∧
    windowForward ∧ ¬ claimsGoFirst ∧ ∃ B A, penalised B A)
}

-- no window and no bound: the tombstone goes while the peer still holds the claim, and the group is
-- taken up again
sat trace [ka_no_tombstone_rule] {
  accept
  sendHave
  writeHave
  handle
  expire
  forget
  decideAsk
  writeAsk
  handle
  assert (filterAsks ∧ asksFirst ∧ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ ¬ liveWindow ∧
    ¬ claimsGoFirst ∧ ∃ B A, penalised B A)
}

-- the group's slot leaves the window and comes back while the peer still holds the claim
sat trace [ka_window_moves_back] {
  accept
  sendHave
  writeHave
  handle
  leaveWindow
  windowBack
  decideAsk
  writeAsk
  handle
  assert (filterAsks ∧ asksFirst ∧ inOrder ∧ expiryInFilter ∧ discardAtExpiry ∧ liveWindow ∧
    ¬ windowForward ∧ ¬ claimsGoFirst ∧ ∃ B A, penalised B A)
}

/-! ## A model check: every clause in every reachable state of a small instance

Two nodes, one group of one chunk, two RPC positions per link (two RPCs per link over the whole
run: positions are not reused), the rules as written: with the live window, and under the
fallback. -/

#model_check interpreted { node := Fin 2, group := Fin 1, index := Fin 1, pos := Fin 2 }
  { filterAsks := true, asksFirst := true, inOrder := true, expiryInFilter := true,
    discardAtExpiry := true, liveWindow := true, windowForward := true, claimsGoFirst := false }

#model_check interpreted { node := Fin 2, group := Fin 1, index := Fin 1, pos := Fin 2 }
  { filterAsks := true, asksFirst := true, inOrder := true, expiryInFilter := true,
    discardAtExpiry := true, liveWindow := false, windowForward := true, claimsGoFirst := true }

/-! ## The proof: the clauses above are an inductive invariant

The SMT solver's answers are not trusted: lean-smt rebuilds a proof of each from cvc5's, and Lean's
kernel checks it. -/

#check_invariants

-- each proof as a theorem in the environment, which Lean's kernel checks as it adds it
#gen_theorems

-- the audit, every failure a build error: the verification conditions, derived from the module
-- itself (the initializer and each action, against `doesNotThrow` and each safety and invariant
-- clause), are all theorems; no clause is assumed instead of checked; and every theorem in the
-- module rests on Lean's own axioms only (no `sorryAx`, no step taken on trust)
open Lean Elab Command in
#eval show CommandElabM Unit from do
  let mod ← Veil.getCurrentModule
  let env ← getEnv
  let allowed := [``propext, ``Classical.choice, ``Quot.sound]
  let acts := mod.procedures.toList.filterMap fun p => match p.info with
    | .initializer => some "initializer"
    | .action n _ => some n.toString
    | .procedure _ => none
  let mut cls := ["doesNotThrow"]
  for a in mod.assertions do
    match a.kind with
    | .safety | .invariant => cls := cls ++ [a.name.toString]
    | _ => logError m!"{a.name} is assumed, not checked"
  logInfo m!"actions {acts}; clauses {cls}"
  let mut vcs : Nat := 0
  for act in acts do
    for cl in cls do
      let n := Name.mkStr `ClaimWins s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `ClaimWins && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in ClaimWins, resting on {rest.toList}"

end ClaimWins
