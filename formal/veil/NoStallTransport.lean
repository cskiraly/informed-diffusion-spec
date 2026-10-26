module

public import Veil

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"

/-! # No stall, the transport part (Q1's second piece), for any number of nodes

SEACAST, `protocol.md` v0.7 (§3, §4.2, §4.4, §4.6, §5, §7.2, §8.1), with F9's rule, §5.4 since v0.8:
**when the transport has nothing left to do, a node that has its block holds every chunk a mesh
neighbour received, or has stopped pulling the group, or holds that neighbour's offer of the
chunk**, which the asking part (`NoStallAsk.lean`) then resolves. The chunk is any one chunk of the
group, so the result holds for each; the mesh is the one the quiet state has, however it changed.

The transport, as the spec writes it: the source publishes, pushing or announcing the chunk to each
mesh peer (§5.1); a node that stores the chunk forwards it to each mesh peer that is neither its
sender nor known to hold it, pushed (counted) or announced, any targets (§4.2, §5.2, §5.3); a queue
may refuse any entry (the group's other traffic can fill it), and a refused push or announcement is
owed and offered (A′); the writer cancels a push the peer has claimed, may skip any push by
projection, which is then uncounted and offered (A′), and sends what is owed, minus what it pushed
the peer and what the peer claimed (§7.2); an announcement is recorded as an offer unless the chunk
is claimed (§4.4); a chunk ahead of its block is deferred, or refused by the store and then its
sender's offer, and dropped if a copy already waits (§4.2); a deferred copy is taken in when the block
installs; a decoded node's repair may push the chunk to mesh peers that have not claimed it (§4.6).

The rest of the protocol is the **environment**, events at any time and any number of times, not in
`work`: a node's block installs; a node stops pulling the group (its decode claim, which takes the
block); a stopped node's decode stores the chunk and makes its repair due; a node learns that a peer
claims the chunk (a HAVE: true, possibly never sent); an answer brings the chunk to a node with its
block from a node that holds it (the asking part); and the mesh changes: a peer joins a node's mesh
(a GRAFT, sent or accepted), leaves it (a PRUNE) or loses its connection, which takes with it what
is queued, owed or in flight on it and the state kept per connection (§8.1). The mesh is directed,
as gossipsub's is: `mesh n m` is "m is in n's mesh", the peers n forwards to; it starts empty, so
every mesh is reached by joins. What is proved is about the states in which the transport is done,
in whatever mesh they have.

F9's rule (§5.4 since v0.8), as a switch with two known answers: a peer that joins a node's mesh is
announced what the node holds of each live group, as `announce` sends it (minus what the node pushed
it and what it claimed; a full queue owes it, A′). Without it nothing guarantees that a reconnection
is offered again what the old connection lost (F9), or that a peer that joins the mesh after the
chunk was forwarded is offered it: offers come from announcements, which follow a chunk's arrival.
Heartbeat gossip may announce the chunk on a connection before it joins the mesh, and a later copy
may be forwarded, but neither need happen (the gossip goes to a sample of peers outside the mesh,
for three heartbeats); the model leaves both out, so its known answers show the missing guarantee.

A rule since v0.7, as a switch with a known answer: every announcement is recorded, an IHAVE over
the receiver's IHAVE limits too, and what the receiver would ask in reply waits for the next
heartbeat (§4.4, §6.4; the asking part's `offerHeldBack`). The known answer is F11: up to v0.6, §8.2
let a receiver ignore IHAVEs beyond `MAX_IHAVE_MESSAGES` (4096) IHAVE-bearing RPCs per peer and
heartbeat, shared by all groups, and `MAX_IHAVE_LENGTH` ids each; a peer announces one chunk per
IHAVE, so a plain group of more chunks than that (up to 8192) announced within a heartbeat could
exceed it, and nothing guarantees an ignored announcement is offered again (the announcer does not
learn of the drop, and repeats an announcement only when an offer of it is owed or when it forwards
a copy received after rebuilding the chunk). Also assumed: §8.2's limits admit the one group
modelled, so a copy the deferred store refuses counts as its sender's offer (`admitted`).

Equivocation (`NoStallEquiv.lean`, F6) needs nothing more here, given that every honest copy names
the builder's block, rebuilt ones included (assumed: v0.7's §4.6 let a rebuilt chunk name either
installed block whose bid commits the group, and one naming the other block waits for good at a
node with only the builder's; since v0.8 it names the block the chunks it was rebuilt from name). `installed` is the builder's block, so a node that installed the
proposer's other block is a node without its block: its copies wait, and it forwards nothing of the
group until it switches. With `ROOT_TIED` a copy the store refuses ties its sender instead of being
its offer at once, and the builder's block's installation turns the tie into the offer
`refusedAsOffer` records; before that block the offers here are the asking part's ledger, or its
offers once the other block opened its gate.

Not modelled here: what is asked and answered (the asking part), traffic outside the mesh (heartbeat
gossip, §6.4, and the source's stripes, §5.1), lifetimes, adversaries; the send window, assumed to
let every queue drain (W2, W3). -/

veil module NoStallTransport

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192

type node
-- a queued push or announcement, an owed offer, and a chunk or announcement in flight, from a to b
enum pk = { qPush, qIhave, owedOffer, fChunk, fIhave }

immutable relation source (n : node) : Bool

immutable individual offerSkipped : Bool     -- A′ (§5.2, §7.2): a skipped push is uncounted and offered
immutable individual oweRefused : Bool       -- A′ (§5.2, §8.2): a refused push or announcement is owed
immutable individual refusedAsOffer : Bool   -- §4.2: a copy the deferred store refuses is an offer
-- §4.4 (v0.7): every announcement is recorded, an IHAVE over the receiver's IHAVE limits too (up to
-- v0.6 the receiver ignored those for the rest of the heartbeat)
immutable individual ihaveHandled : Bool
-- §5.4 (v0.8), F9's rule: a peer that joins the mesh is announced what the node holds
immutable individual resyncOnJoin : Bool

relation mesh (n : node) (m : node) : Bool    -- m is in n's mesh: n forwards to m
individual published : Bool
relation installed (n : node) : Bool
relation stop (n : node) : Bool               -- stopped pulling the group (its decode claim)
relation rcv (n : node) : Bool                -- received the chunk (or published it): forwards it
relation holds (n : node) : Bool              -- holds the chunk: received or rebuilt
relation peerHas (m : node) (n : node) : Bool       -- m knows that n claims the chunk
relation pushed (m : node) (n : node) : Bool        -- m counts a push of the chunk to n
relation pendingFwd (m : node) (n : node) : Bool    -- m's forwarding of the chunk to n, due
relation fwdFrom (m : node) (n : node) : Bool       -- m's first copy came from n
relation repairDue (m : node) (n : node) : Bool
relation pipe (k : pk) (a : node) (b : node) : Bool
relation pend (n : node) (m : node) : Bool          -- n's deferred store holds m's copy
relation offered (n : node) (m : node) : Bool       -- m offered the chunk to n
-- history only, for the non-vacuity queries below: no action reads them
relation everDeferred (n : node) : Bool
relation everRefused (n : node) : Bool
relation everResynced (n : node) (m : node) : Bool   -- n announced its holding to m as m joined
relation lostPush (n : node) (m : node) : Bool       -- a close lost n's queued push to m

#gen_state

assumption [one_source] source N → source M → N = M

theory ghost relation premises :=
  offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin

-- the transport's actions' enabling conditions, each its action's only `require`
ghost relation en_publish (s : node) := source s ∧ ¬ published
ghost relation en_fwd (m : node) (n : node) := pendingFwd m n
ghost relation en_writePush (m : node) (n : node) := pipe qPush m n
ghost relation en_writeIhave (m : node) (n : node) := pipe qIhave m n
ghost relation en_writeOwed (m : node) (n : node) := pipe owedOffer m n
ghost relation en_recvChunk (n : node) (m : node) := pipe fChunk m n
ghost relation en_resume (n : node) (m : node) := installed n ∧ pend n m
ghost relation en_recvIhave (n : node) (m : node) := pipe fIhave m n
ghost relation en_repair (m : node) (n : node) := repairDue m n

-- the transport has something to do
ghost relation work :=
  (∃ S, en_publish S) ∨ (∃ M N, en_fwd M N) ∨ (∃ M N, en_writePush M N) ∨
  (∃ M N, en_writeIhave M N) ∨ (∃ M N, en_writeOwed M N) ∨ (∃ N M, en_recvChunk N M) ∨
  (∃ N M, en_resume N M) ∨ (∃ N M, en_recvIhave N M) ∨ (∃ M N, en_repair M N)

-- for the known answers: a quiet state in which a node with its block lacks a chunk a mesh
-- neighbour received, has not stopped, and holds no offer of it from that neighbour
ghost relation undelivered :=
  ¬ work ∧ ∃ M N, installed N ∧ rcv M ∧ mesh M N ∧ ¬ holds N ∧ ¬ stop N ∧ ¬ offered N M

after_init {
  mesh N M := false
  published := false
  installed N := false
  stop N := false
  rcv N := false
  holds N := false
  peerHas M N := false
  pushed M N := false
  pendingFwd M N := false
  fwdFrom M N := false
  repairDue M N := false
  pipe K A B := false
  pend N M := false
  offered N M := false
  everDeferred N := false
  everRefused N := false
  everResynced N M := false
  lostPush N M := false
}

/-! ## The environment -/

-- §3: n's block installs (its deferred copies are then taken in, by `resume`)
action install (n : node) {
  require ¬ installed n
  installed n := true
}

-- §4.6: n's decode claim, which takes the block
action stopPull (n : node) {
  require installed n
  stop n := true
}

-- §4.6: a stopped node's decode stores the chunk; repair may push it to mesh peers that have not
-- claimed it, if the node did not receive it
action rebuild (n : node) {
  require stop n
  holds n := true
  repairDue n Q := mesh n Q && !rcv n && !peerHas n Q
}

-- §4.3: m learns from n's HAVE that n claims the chunk
action learnClaim (m n : node) {
  require holds n ∨ stop n
  peerHas m n := true
}

-- §4.5, §6.3: an answer brings the chunk to n, which has its block, from q, which holds it: stored,
-- its offers go, claimed (a HAVE: the environment) and forwarded
action answerArrives (n q : node) {
  require installed n ∧ holds q ∧ ¬ rcv n
  holds n := true
  rcv n := true
  fwdFrom n q := true
  offered n Q := false
  pendingFwd n Q := mesh n Q && !peerHas n Q
}

-- the mesh changes (stock gossipsub: GRAFT, PRUNE, the heartbeat's upkeep). m joins n's mesh, by n's
-- GRAFT or by m's that n accepts; with F9's rule, n announces what it holds to m, as `announce` does
-- (§5.2): minus what it pushed m and what m claimed, owed if a full queue refuses it (A′)
action join (n m : node) (full : Bool) {
  require n ≠ m ∧ ¬ mesh n m
  mesh n m := true
  if resyncOnJoin ∧ holds n ∧ ¬ pushed n m ∧ ¬ peerHas n m then
    everResynced n m := true
    if full then
      if oweRefused then
        pipe owedOffer n m := true
    else
      pipe qIhave n m := true
}

-- m leaves n's mesh (a PRUNE, sent or received): the connection stays, and what is on it
action leave (n m : node) {
  require mesh n m
  mesh n m := false
}

-- §8.1: the connection between n and m closes (a reconnection is a new connection, in the mesh again
-- only once a peer joins it): each leaves the other's mesh; what is queued, owed or in flight on it is
-- lost, both ways, and so is the forwarding and repair still due to the other, whose entries the
-- queue would have held; the state kept per connection goes: claims, counted pushes, offers. A
-- deferred copy stays: the deferred store is kept per block root, not per connection
action close (n m : node) {
  require n ≠ m
  if pipe qPush n m then
    lostPush n m := true
  if pipe qPush m n then
    lostPush m n := true
  mesh n m := false
  mesh m n := false
  pipe K n m := false
  pipe K m n := false
  pendingFwd n m := false
  pendingFwd m n := false
  repairDue n m := false
  repairDue m n := false
  peerHas n m := false
  peerHas m n := false
  pushed n m := false
  pushed m n := false
  offered n m := false
  offered m n := false
}

/-! ## The transport -/

-- §5.1: the source holds the chunk, has claimed the group and pulls nothing; the chunk is pushed or
-- announced to each mesh peer, as forwarding does
action publish (s : node) {
  require en_publish s
  published := true
  installed s := true
  stop s := true
  rcv s := true
  holds s := true
  pendingFwd s Q := mesh s Q
}

-- §5.2, §5.3: m forwards the chunk to n: pushed (counted) or announced, minus what it pushed n and
-- what n claimed; refused by a full queue, owed instead (A′); never to the copy's sender
action fwd (m n : node) (pushIt full : Bool) {
  require en_fwd m n
  pendingFwd m n := false
  if ¬ fwdFrom m n then
    if pushIt then
      if full then
        if oweRefused then
          pipe owedOffer m n := true
      else
        pipe qPush m n := true
        pushed m n := true
    else
      if ¬ pushed m n ∧ ¬ peerHas m n then
        if full then
          if oweRefused then
            pipe owedOffer m n := true
        else
          pipe qIhave m n := true
}

-- §7.2: a queued push: cancelled if n has claimed the chunk; skipped by projection, then uncounted
-- and offered if n is still in m's mesh (A′, §5.2's `unpush`); else sent
action writePush (m n : node) (projected : Bool) {
  require en_writePush m n
  pipe qPush m n := false
  if ¬ peerHas m n then
    if projected then
      if offerSkipped then
        pushed m n := false
        if mesh m n then
          pipe owedOffer m n := true
    else
      pipe fChunk m n := true
}

action writeIhave (m n : node) {
  require en_writeIhave m n
  pipe qIhave m n := false
  pipe fIhave m n := true
}

-- §7.2: what is owed leaves with the next write, minus what m pushed n and what n claimed
action writeOwed (m n : node) {
  require en_writeOwed m n
  pipe owedOffer m n := false
  if ¬ pushed m n ∧ ¬ peerHas m n then
    pipe fIhave m n := true
}

-- §4.2: the chunk arrives at n from m. With the block: a first copy is stored, its offers go, it is
-- claimed (a HAVE: the environment) and forwarded; a second copy is acknowledged (the environment).
-- Ahead of the block: dropped if a copy already waits, else deferred, or refused by the store and then
-- m's offer
action recvChunk (n m : node) (kept : Bool) {
  require en_recvChunk n m
  pipe fChunk m n := false
  if installed n then
    if ¬ rcv n then
      holds n := true
      rcv n := true
      fwdFrom n m := true
      offered n Q := false
      pendingFwd n Q := mesh n Q && !peerHas n Q
  else
    if ¬ (∃ P, pend n P) then
      if kept then
        pend n m := true
        everDeferred n := true
      else
        if refusedAsOffer then
          offered n m := true
          everRefused n := true
}

-- §4.2: the block installed, a deferred copy resumes level 1, as a chunk that arrives
action resume (n m : node) {
  require en_resume n m
  pend n m := false
  if ¬ rcv n then
    holds n := true
    rcv n := true
    fwdFrom n m := true
    offered n Q := false
    pendingFwd n Q := mesh n Q && !peerHas n Q
}

-- §4.4: an announcement from m: recorded as m's offer unless n claims the chunk (what is asked is
-- the asking part's)
action recvIhave (n m : node) {
  require en_recvIhave n m
  pipe fIhave m n := false
  if ¬ holds n ∧ ¬ stop n then
    offered n m := true
}

-- §4.4, §8.2 up to v0.6: without the rule, an announcement beyond the receiver's limit is ignored
action dropIhave (n m : node) {
  require en_recvIhave n m ∧ ¬ ihaveHandled
  pipe fIhave m n := false
}

-- §4.6: repair pushes the rebuilt chunk to n, or not (each mesh peer's shortfall picks)
action repair (m n : node) (pushIt full : Bool) {
  require en_repair m n
  repairDue m n := false
  if pushIt then
    if full then
      if oweRefused then
        pipe owedOffer m n := true
    else
      pipe qPush m n := true
      pushed m n := true
}

-- when the transport is done, a node with its block holds every chunk a mesh neighbour received, has
-- stopped pulling, or holds the neighbour's offer of it
safety [delivered] premises → ¬ work → installed N → rcv M → mesh M N →
  holds N ∨ stop N ∨ offered N M

-- no node is in its own mesh
invariant [mesh_irrefl] mesh N M → N ≠ M
-- what is stored and claimed
invariant [stored] (rcv N → holds N) ∧ (holds N → rcv N ∨ stop N) ∧ (stop N → installed N) ∧
  (holds N → installed N)
invariant [claims_true] peerHas M N → holds N ∨ stop N
-- what is sent, forwarded, repaired, deferred or offered is held by its sender
invariant [senders_hold] (pipe qPush M N → holds M) ∧ (pipe fChunk M N → holds M) ∧
  (pendingFwd M N → holds M) ∧ (repairDue M N → holds M) ∧ (pipe qIhave M N → holds M) ∧
  (pipe fIhave M N → holds M) ∧ (pipe owedOffer M N → holds M)
invariant [others_hold] (fwdFrom N P → holds P) ∧ (pend N P → holds P) ∧ (offered N Q → holds Q)
-- a queued push is counted
invariant [qpush_pushed] pipe qPush M N → pushed M N
-- the chain that carries a chunk across a mesh link: forwarded, then pushed or offered
invariant [delivery] premises → rcv M → mesh M N →
  holds N ∨ stop N ∨ pendingFwd M N ∨ pipe qPush M N ∨ pushed M N ∨ pipe owedOffer M N ∨
    pipe qIhave M N ∨ pipe fIhave M N ∨ offered N M ∨ peerHas M N
-- a counted push arrives, waits in the deferred store, or is refused by it and then an offer
invariant [pushed_chain] premises → pushed M N →
  holds N ∨ stop N ∨ pipe qPush M N ∨ pipe fChunk M N ∨ (∃ P, pend N P) ∨ offered N M ∨
    peerHas M N

#gen_spec

/-! ## Non-vacuity: with every rule on, runs reach a quiet state (the mesh starts empty: each trace
first lets a peer join the source's) -/

-- a push delivered
sat trace [push_delivered] {
  join
  publish
  install
  fwd
  writePush
  recvChunk
  assert (premises ∧ ¬ work ∧ ∃ N, holds N ∧ ¬ source N)
}

-- an announcement, recorded as an offer for the asking part
sat trace [announced_offer] {
  join
  publish
  fwd
  writeIhave
  recvIhave
  install
  assert (premises ∧ ¬ work ∧ ∃ N M, installed N ∧ offered N M ∧ ¬ holds N)
}

-- a copy ahead of the block, deferred and taken in when it installs
sat trace [deferred_taken_in] {
  join
  publish
  fwd
  writePush
  recvChunk
  install
  resume
  assert (premises ∧ ¬ work ∧ ∃ N, holds N ∧ everDeferred N)
}

-- a copy the deferred store refuses, recorded as its sender's offer
sat trace [refused_copy_offer] {
  join
  publish
  fwd
  writePush
  recvChunk
  install
  assert (premises ∧ ¬ work ∧ ∃ N M, everRefused N ∧ installed N ∧ offered N M)
}

-- F9's case: the connection closes with a push of the chunk queued; the peer joins the mesh again,
-- and the resync's announcement is recorded as an offer
sat trace [resync_after_close] {
  join
  publish
  fwd
  close
  join
  writeIhave
  recvIhave
  install
  assert (premises ∧ ¬ work ∧
    ∃ N M, installed N ∧ offered N M ∧ ¬ holds N ∧ everResynced M N ∧ lostPush M N)
}

-- a peer that joins the mesh after the publish is announced the chunk
sat trace [resync_late_join] {
  publish
  join
  writeIhave
  recvIhave
  install
  assert (premises ∧ ¬ work ∧ ∃ N M, installed N ∧ offered N M ∧ ¬ holds N ∧ everResynced M N)
}

/-! ## Known answers: with any one rule off, a node is left without the chunk and without an offer -/

-- F1: a push projection skips is still counted, and offered to nobody
sat trace [ka_skip_counted] {
  join
  publish
  install
  fwd
  writePush
  assert (¬ offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- a push a full queue refuses is lost
sat trace [ka_refused_lost] {
  join
  publish
  install
  fwd
  assert (offerSkipped ∧ ¬ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- F7: a push the deferred store refuses is lost
sat trace [ka_refused_copy_lost] {
  join
  publish
  fwd
  writePush
  recvChunk
  install
  assert (offerSkipped ∧ oweRefused ∧ ¬ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- F11: an announcement the receiver's IHAVE limit ignores is lost, and offered by nobody again
sat trace [ka_ihave_dropped] {
  join
  publish
  install
  fwd
  writeIhave
  dropIhave
  assert (offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ¬ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- F9: the connection closes with a push of the chunk queued, the peer joins the mesh again, and
-- nothing offers it the chunk
sat trace [ka_rejoin_lost] {
  join
  publish
  fwd
  close
  join
  install
  assert (offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ ¬ resyncOnJoin ∧ ¬ work ∧
    ∃ M N, lostPush M N ∧ installed N ∧ rcv M ∧ mesh M N ∧ ¬ holds N ∧ ¬ stop N ∧ ¬ offered N M)
}

-- the same gap without a close: nothing offers the chunk to a peer that joins the mesh after the
-- publish
sat trace [ka_late_join] {
  publish
  join
  install
  assert (offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ ¬ resyncOnJoin ∧ undelivered)
}

/-! ## The proof: the clauses above are an inductive invariant -/

#check_invariants

-- each proof as a theorem in the environment, which Lean's kernel checks as it adds it
#gen_theorems

-- the audit, every failure a build error: the verification conditions, derived from the module
-- itself (the initializer and each action, against `doesNotThrow` and each safety and invariant
-- clause), are all theorems; no clause is trusted instead of checked (the assumption, that there is
-- one source, is listed); and every theorem in the module rests on Lean's own axioms only
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
  let mut assumed : List String := []
  for a in mod.assertions do
    match a.kind with
    | .safety | .invariant => cls := cls ++ [a.name.toString]
    | .assumption => assumed := assumed ++ [a.name.toString]
    | _ => logError m!"{a.name} is trusted, not checked"
  logInfo m!"actions {acts}; clauses {cls}; assumptions {assumed}"
  let mut vcs : Nat := 0
  for act in acts do
    for cl in cls do
      let n := Name.mkStr `NoStallTransport s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `NoStallTransport && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in NoStallTransport, resting on {rest.toList}"

end NoStallTransport
