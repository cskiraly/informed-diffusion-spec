module

public import Veil
public import QuietRanking

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"

/-- Q3's per-step facts (as `NoStallEquiv.lean`'s): Veil's reduction of a
one-step temporal goal to first-order form, the enum axioms' distinctness as inequalities, then
Lean's `grind`, which the kernel checks. `veil_solve_temporal` ends in the SMT solver instead, whose
translation or proof reconstruction fails on most of these goals in Veil v4.35.0. -/
macro "fv_step" : tactic => `(tactic| (
  unveil_temporal
  (try veil_cases_type* Or)
  all_goals (
    (try veil_destruct only [And, Exists])
    veil_fol !
    (try simp only [distinctN_pairwise_neq, List.nodup_cons, List.mem_cons, List.not_mem_nil, or_false,
      not_or, List.nodup_nil, and_true] at *)
    grind)))

/-! # The asking under v0.8's rules, with malicious peers, for any number of nodes

`NoStallEquiv.lean` with adversaries: v0.8's ties (§4.2) and rule
against a second ask of a peer (§6.1), with the proposer's other block or without it. **When no
honest node's asking machinery has anything left to do, an honest node that has the builder's block
holds every chunk an honest peer offered it, or has stopped pulling, whatever the other peers do.**
As in `NoStallAskAdv.lean`: the adversaries (`adv`) offer whether they hold the chunk or not,
before the gate or after, claim anything, ask honest nodes (`advAsk`, numbered as any ask) and
answer or not; honest nodes' offers go to honest receivers (an adversary's own asking is not
modelled); "nothing left to do" counts honest nodes' pending events only; the safety and the
invariants about claims, offers, ties and an asker's numbered asks are for honest nodes, and those
about a provider's asks before the builder's block and that the last-resort count goes with an
offer are for honest providers: an adversary's dropped tie drops its offers, not its count, and it
may be asked again. Besides, §4.2's ties are by root: an adversary's copy that waits ties it to the
root it names, its promise closed, either to the builder's, before that block installs at the node
(`advTie`), released by the installation as any tie, or to another root, at any time (`advTieElse`,
`tiedElse`), which the builder's installation leaves: the proposer's other block's, whose
installation releases it (`releaseElse`: the park lifts, the last-resort count clears, an offer
again; at any time once the gate is open, any number of times, where §4.2 allows one per block), a
root that never installs (the tie stays), or one whose bid commits another group (`dropTie`: dropped
with the adversary's offers, the retry armed once the gate is open). A sender tied to any root is
passed over (`tiedToRoot`, §4.2's `tied_to_root`). **F13**: where `drop_tie` drops the sender's
offers and leaves its asks (without v0.8's rule below), an ask still queued is written once the tie
is gone, the retry, finding no announcer, ends, and the sender's next offer is recorded with nothing
scheduled, the ask outstanding (§4.4); while it is, the last resort for a parked honest announcer
returns at once (§6.1), and the promise falls due and only parks (`ka_drop_keeps_asks`). An offer's
expiry, 30 s after the announcer's last offer of the group (§6.1, §8.1), leaves the ask the same way
(`ka_expiry_keeps_asks`); an adversary's offers expire here at any time (`advExpire`), since it
chooses when it last offers, and an honest announcer's outlast diffusion, as Q1 assumes. F13's
rule, v0.8's `drop_offer` (§6.1: dropped offers take their ask with them): where a peer's offers of
an index are dropped, by `drop_tie` or by their expiry, its queued asks of it go (`dropAsks`) and
its promise for it closes (`dropPromises`); an ask written just before the expiry keeps the sender
outstanding through its promise (`ka_expiry_keeps_promise`). **Under level 1 by group** (`byGroup`:
a candidate rule, off for the spec's rules; one of the options `protocol.md` §4.6 lists for
relabelled copies, F12, which it leaves open): a copy passes level 1 against either block, so the
first installation of either is the node's installation (the `install` actions), a copy waits only
before it, whatever root it names, and it releases every tie; the other block's gate alone does not
arise. An adversary's tie after it (`advTieElse`), its release and its drop stay, as an
over-approximation (under a draft of the rule such a copy, one whose slot is not its group's, is
rejected). Offers then resolve at a node with either block (`offers_resolve_any`), and without the
rule a node with only the other block stalls (`ka_other_block_stalls`). Relabelled copies need
nothing more here: an answer, whatever root it names, passes level 1 at a node with either block,
and a transport model under the rule, not in this folder, shows that no copy waits there once it is
quiet, so no answer is taken for a waiting copy: where an installation takes every waiting copy of
the group in, in the same handler and before the ledger is asked for, as a draft of the rule does,
no copy of the group waits after it, so this holds at every step after the installation, not only
once the transport is quiet. Without the rule, excluded, as the honest model's assumption has it:
an adversary's copy that names the proposer's other block and so validates at a node on it (a
relabelled copy, F12): every copy an honest node can take in names the builder's block, and a copy
that names the other block's root fails its proof when that block installs.
The offers from a parked announcer are split by case, and offers go to honest receivers, so that
each condition's proof can be rebuilt for the kernel (as in `NoStallAskAdv.lean`).

The rest of this header is `NoStallEquiv.lean`'s. -/

/-! # No stall under equivocation, the asking part (F6), for any number of nodes

SEACAST, `protocol.md` v0.7 (§3, §4.1, §4.2, §4.4, §4.5, §6.1, §6.4, §7.2), with the two rules
for F6 that v0.8 adds (`../README.md`, F6): **when the asking machinery has nothing left to do, a node
that has installed the builder's block holds every chunk an honest peer offered it, or has stopped
pulling the group, also when it installed the proposer's other block first.** The chunk is any one
chunk of the group, so the result holds for each.

Equivocation (§3, §4.2): a proposer that signs two blocks for one slot may put the same bid in both,
so both commit the group. A node that installs the other block first has a block whose bid commits
the group, so it asks (C′: `gate`); but every honest chunk names the builder's block, so a copy that
reaches it waits for that block, kept by the deferred store or refused. The node may install the
builder's block later (fork choice: the switch), and only then does a copy validate (`installed`).

F6: before the switch the providers' answers wait or are refused, their promises fall due and park
them, the last resort's ask is spent on them, and so are a provider's three answers per chunk and
connection (`GOSSIP_RETRANSMISSION`); after the switch every announcer is parked and has been asked
once more, or has no answer left, and the node stalls. The two rules, each a switch with a known
answer:
- `ROOT_TIED` (§4.2's ties): a copy that waits ties its sender to the root it names, for its index;
  the sender's promise closes, since it answered, and it is not asked for the index again until that
  root installs. The installation releases the ties: each sender's park lifts, the last-resort count
  for it clears, and it is an offer again, asked for (§4.2's `on_block_installed`).
- `NO_REASK_OPEN` (§6.1): no announcer is asked for a chunk while an earlier ask of it to that announcer is
  outstanding, queued or promised; a retry or a last resort that finds every candidate outstanding
  waits, and the outstanding ask is pending work.

Asks are numbered per peer (`ord`): the j-th ask from n to q, each with its own stages, so that two
asks in flight to one peer are two, not one, and what a provider answers is counted. The provider
answers the first three, and may drop any later one (its count kept for the connection's life, the
worst case of the stock lifetime).

The rest is `NoStallAsk.lean`'s machinery: one ask per chunk in its window, the retry, promises that
fall due at any time, the last resort, the writer's ask filter (which also drops a queued ask to a
tied peer), the claim rule's drop, answers cancelled or owed, the ledger (C′), held-back offers
(v0.7); and its environment, with the other block's installation and pushes that wait for the
builder's block.

Connections close at any time, as in `NoStallAsk.lean`: what is between the two nodes is lost both
ways, their promises close, and the state kept per connection goes, the asks' numbering (with the
provider's serve count) and the ties among it (§8.1); the last-resort counts with it are a switch
with a known answer.

Assumed: every honest copy names the builder's block, rebuilt ones included. v0.7's §4.6 let a
rebuilt chunk name either installed block whose bid commits the group, so a node that installed
both blocks could rebuild a chunk naming the other one; at a node with only the builder's block
that copy waits for good, and its sender, which counted it, sends nothing more for the index.
v0.8's §4.6 has a rebuilt chunk name the block the chunks it was rebuilt from name, where they all
name one: the source publishes under one block, and forwarding and the rule keep it, so among
honest nodes every copy names it, while no node relabels a chunk under the other block's root
(`protocol.md` §4.6, open: honest nodes forward such a copy and rebuild from it). That argument is
by inspection, not in this model.

Not modelled here: how offers come about (the transport), lifetimes, adversaries (so every tie is
honest: a copy naming the builder's root, whose bid commits the group), and more than two blocks
for the slot. -/

veil module NoStallEquivAdv

-- Veil v4.35.0's solver needs more than `veil module`'s 500,000 heartbeats on some conditions
set_option maxHeartbeats 2000000

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192

-- the LocalRProp instance for the invariants needs more than the typeclass search's 20,000
-- heartbeats: without it 53 conditions fell through to the SMT solver and failed (f2, 2026-11-10)
set_option synthInstance.maxHeartbeats 200000

type node
-- the stages of an ask from a to b (queued at a, in flight) and of an answer from a to b (queued at
-- a, owed by a, in flight)
enum kind = { askQ, askF, ansQ, ansOwed, ansF }
-- an ask's number among n's asks to q for the chunk: the first, the second, the third, a later one
enum ord = { o1, o2, o3, o4 }

immutable individual lastResort : Bool     -- §6.1: every announcer parked, each asked once more
immutable individual owedAnswers : Bool    -- §4.1, §7.2: an answer a full queue refuses is owed
immutable individual askLedger : Bool      -- C′ (§3, §4.2): what was offered before the block is asked
-- §4.4, §6.4 (v0.7): an ask an IHAVE limit holds back is retried at the next heartbeat
immutable individual heldBackRetry : Bool
immutable individual rootTied : Bool       -- F6: ROOT_TIED (§4.2's ties, v0.8)
immutable individual noReask : Bool        -- F6: NO_REASK_OPEN (§6.1, v0.8)
-- §6.1, §8.1: the last-resort count for an announcer goes with its connection, as `tried` does
immutable individual countsReset : Bool
-- F13's rule (v0.8's `drop_offer`, 2026-10-28): where a peer's offers of the chunk are dropped (§4.2's
-- `drop_tie`, or their expiry), its queued asks of it go, and its promise for it closes
immutable individual dropAsks : Bool
immutable individual dropPromises : Bool
-- level 1 by group, a candidate rule for F12 (`protocol.md` §4.6's relabelled copies, open), off for
-- the spec's rules: a copy passes level 1 against either block, so the first installation of either
-- is the node's installation, and the other block's gate alone (`installOther`) does not arise
immutable individual byGroup : Bool
-- the adversaries
immutable relation adv (n : node) : Bool

relation gate (n : node) : Bool                    -- a block whose bid commits the group is installed
relation installed (n : node) : Bool               -- the builder's block, which the chunks name
relation got (n : node) : Bool                     -- n holds the chunk
relation stop (n : node) : Bool                    -- n stopped pulling the group (its decode claim)
relation peerHas (q : node) (n : node) : Bool      -- q knows that n claims the chunk
relation offered (n : node) (q : node) : Bool      -- q offered the chunk to n
relation ledger (n : node) (q : node) : Bool       -- q offered it before n's gate opened (§4.2)
relation inWindow (n : node) : Bool                -- an ask of n's is in its window
relation retryArmed (n : node) : Bool
relation lrArmed (n : node) : Bool                 -- the last resort's timer
relation parked (n : node) (q : node) : Bool       -- n parked q, for the group
relation askedParked (n : node) (q : node) : Bool  -- the last-resort count
relation promise (n : node) (q : node) : Bool      -- n's ask to q, written, open
relation tied (n : node) (q : node) : Bool         -- q's copy waits at n for the builder's root
                                                   -- (under `byGroup`: for a block committing the group)
relation tiedElse (n : node) (q : node) : Bool     -- an adversary q's copy waits at n for another root
relation made (n : node) (q : node) (j : ord) : Bool    -- n's j-th ask to q was queued
relation stage (k : kind) (a : node) (b : node) (j : ord) : Bool
-- history only, for the non-vacuity queries below: no action reads them
relation everLastResort (n : node) : Bool
relation everEarly (n : node) : Bool
relation everHeldBack (n : node) : Bool
relation everTied (n : node) : Bool
relation everSwitched (n : node) : Bool            -- n installed the builder's block after the other
relation closedAsk (n : node) : Bool               -- a close lost an ask of n's

#gen_state

theory ghost relation premises :=
  lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset ∧ dropAsks ∧
    dropPromises

-- an ask of the chunk from n to q is outstanding: queued, or its promise open (NO_REASK_OPEN)
ghost relation outstanding (n : node) (q : node) := (∃ J, stage askQ n q J) ∨ promise n q
-- q's copy waits at n, for any root: q is passed over (§4.2's `tied_to_root`)
ghost relation tiedToRoot (n : node) (q : node) := tied n q ∨ tiedElse n q
-- j is the number of n's next ask to q
ghost relation nextAsk (n : node) (q : node) (j : ord) :=
  (j = o1 ∧ ¬ made n q o1) ∨ (j = o2 ∧ made n q o1 ∧ ¬ made n q o2) ∨
    (j = o3 ∧ made n q o2 ∧ ¬ made n q o3) ∨ (j = o4 ∧ made n q o3)
-- the j-th ask from n to q, or its answer, is on its way
ghost relation pipeline (n : node) (q : node) (j : ord) :=
  stage askQ n q j ∨ stage askF n q j ∨ stage ansQ q n j ∨ stage ansOwed q n j ∨ stage ansF q n j

-- the machinery's actions' enabling conditions, each its action's `require` (with the ask's number)
ghost relation en_writeAsk (n : node) (q : node) (j : ord) := stage askQ n q j
ghost relation en_recvAsk (q : node) (n : node) (j : ord) := stage askF n q j
ghost relation en_owedToQueue (q : node) (n : node) (j : ord) := stage ansOwed q n j
ghost relation en_writeAns (q : node) (n : node) (j : ord) := stage ansQ q n j
ghost relation en_recvAns (n : node) (q : node) (j : ord) := stage ansF q n j
ghost relation en_elapse (n : node) := inWindow n
ghost relation en_retryNoop (n : node) := retryArmed n ∧ ¬ inWindow n ∧ (got n ∨ stop n)
-- the retry asks an unparked announcer that is not tied, and (NO_REASK_OPEN) not outstanding
ghost relation en_retryAsk (n : node) (q : node) :=
  retryArmed n ∧ ¬ inWindow n ∧ ¬ got n ∧ ¬ stop n ∧ offered n q ∧ ¬ parked n q ∧ ¬ tiedToRoot n q ∧
    ¬ (noReask ∧ outstanding n q)
-- every announcer that is not tied is parked: the last resort
ghost relation en_retryParked (n : node) :=
  retryArmed n ∧ ¬ inWindow n ∧ ¬ got n ∧ ¬ stop n ∧ ∀ Q, offered n Q → parked n Q ∨ tiedToRoot n Q
ghost relation en_lrNoop (n : node) :=
  lrArmed n ∧ (got n ∨ stop n ∨ inWindow n ∨
    ∀ Q, offered n Q → tiedToRoot n Q ∨ (parked n Q ∧ askedParked n Q))
ghost relation en_lrAsk (n : node) (q : node) :=
  lrArmed n ∧ ¬ got n ∧ ¬ stop n ∧ ¬ inWindow n ∧ offered n q ∧ ¬ tiedToRoot n q ∧
    ¬ (noReask ∧ outstanding n q) ∧
    (¬ parked n q ∨ ((∀ Q, offered n Q → parked n Q ∨ tiedToRoot n Q) ∧ ¬ askedParked n q))
ghost relation en_promiseDue (n : node) (q : node) := promise n q

-- an honest node's machinery has something to do: the event is at an honest node; what is pending
-- at an adversary is not work
ghost relation work :=
  (∃ N Q J, ¬ adv N ∧ en_writeAsk N Q J) ∨ (∃ Q N J, ¬ adv Q ∧ en_recvAsk Q N J) ∨
  (∃ Q N J, ¬ adv Q ∧ en_owedToQueue Q N J) ∨ (∃ Q N J, ¬ adv Q ∧ en_writeAns Q N J) ∨
  (∃ N Q J, ¬ adv N ∧ en_recvAns N Q J) ∨ (∃ N, ¬ adv N ∧ en_elapse N) ∨
  (∃ N, ¬ adv N ∧ en_retryNoop N) ∨ (∃ N Q, ¬ adv N ∧ en_retryAsk N Q) ∨
  (∃ N, ¬ adv N ∧ en_retryParked N) ∨ (∃ N, ¬ adv N ∧ en_lrNoop N) ∨
  (∃ N Q, ¬ adv N ∧ en_lrAsk N Q) ∨ (∃ N Q, ¬ adv N ∧ en_promiseDue N Q)

after_init {
  gate N := false
  installed N := false
  got N := false
  stop N := false
  peerHas Q N := false
  offered N Q := false
  ledger N Q := false
  inWindow N := false
  retryArmed N := false
  lrArmed N := false
  parked N Q := false
  askedParked N Q := false
  promise N Q := false
  tied N Q := false
  tiedElse N Q := false
  made N Q J := false
  stage K A B J := false
  everLastResort N := false
  everEarly N := false
  everHeldBack N := false
  everTied N := false
  everSwitched N := false
  closedAsk N := false
}

/-! ## The environment -/

-- §4.4, §6.1: an honest node holding the chunk offers it to n. Ignored if n claims the chunk (no
-- state changes, so not modelled); recorded otherwise; before n's gate, recorded only (§3); with
-- it, by the case: asked for if the offerer is not parked, not tied, not outstanding, and no ask is
-- in its window; recorded only if tied, outstanding or in the window; from a parked offerer, the
-- last resort armed when every announcer not tied is parked and one has not been asked once more
ghost relation lrDue (n : node) (q : node) :=
  lastResort ∧ ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q ∨ tiedToRoot n Q) ∧
    ((∃ Q, offered n Q ∧ ¬ tiedToRoot n Q ∧ ¬ askedParked n Q) ∨ ¬ askedParked n q)

action offerEarly (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ ¬ gate n
  ledger n q := true
  everEarly n := true
}

action offerAsk (n q : node) (j : ord) (full : Bool) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ ¬ parked n q ∧
    ¬ inWindow n ∧ ¬ tiedToRoot n q ∧ ¬ (noReask ∧ outstanding n q) ∧ nextAsk n q j
  inWindow n := true
  retryArmed n := true
  if full = false then
    made n q j := true
    stage askQ n q j := true
  offered n q := true
}

action offerRecord (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧
    (tiedToRoot n q ∨ (¬ parked n q ∧ (inWindow n ∨ (noReask ∧ outstanding n q))))
  offered n q := true
}

action offerParkedArm (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧
    ¬ tiedToRoot n q ∧ lrDue n q
  lrArmed n := true
  offered n q := true
}

-- from a parked offerer while the last resort is not due (`lrDue`), one action per reason (together
-- `¬ lrDue n q`): the last resort is armed; another announcer is neither parked nor tied; every
-- announcer not tied is parked and asked once more, this one too (it has offered already, so
-- nothing changes, except where the last-resort count outlived a close: the known answer); no
-- last resort
action offerParked (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧
    ¬ tiedToRoot n q ∧ lrArmed n
  offered n q := true
}

action offerParkedUnparked (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧
    ¬ tiedToRoot n q ∧ ¬ lrArmed n ∧ (∃ Q, offered n Q ∧ ¬ parked n Q ∧ ¬ tiedToRoot n Q)
  offered n q := true
}

action offerParkedAsked (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧
    ¬ tiedToRoot n q ∧ ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q ∨ tiedToRoot n Q) ∧
    (∀ Q, offered n Q → tiedToRoot n Q ∨ askedParked n Q) ∧ askedParked n q ∧ offered n q
}

action offerParkedAskedNew (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧
    ¬ tiedToRoot n q ∧ ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q ∨ tiedToRoot n Q) ∧
    (∀ Q, offered n Q → tiedToRoot n Q ∨ askedParked n Q) ∧ askedParked n q ∧ ¬ offered n q
  offered n q := true
}

action offerParkedNoLR (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧
    ¬ tiedToRoot n q ∧ ¬ lastResort
  offered n q := true
}

-- §4.4, §6.4 (v0.7): an IHAVE over one of gossipsub's IHAVE limits: the offer is recorded and the
-- chunk held back to the next heartbeat, which runs the retry for it (here the retry is armed)
action offerHeldBack (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ gate n
  if heldBackRetry then
    retryArmed n := true
  offered n q := true
  everHeldBack n := true
}

-- §3, §4.2: the proposer's other block installs at n first. Its bid commits the group, so the gate
-- opens and what was offered meanwhile is asked for (the ledger); copies, naming the builder's block,
-- still wait. Under level 1 by group it is an installation as the builder's block's is (the actions
-- below), and this one does not arise
action installOther (n : node) {
  require ¬ byGroup ∧ ¬ gate n
  gate n := true
  if askLedger ∧ (∃ Q, ledger n Q) then
    retryArmed n := true
  offered n Q := offered n Q || ledger n Q
  ledger n Q := false
}

-- §3, §4.2: the builder's block installs at n, first or as the switch. Its handler takes the deferred
-- copies in, then releases the ties (ROOT_TIED) and asks for what is offered, by the case: a copy of
-- this chunk was waiting, and the chunk is held; the copies brought the group to K, and the decode
-- claim stopped the pull; or neither: each tied sender's park lifts, the last-resort count for it
-- clears, it is an offer again, the ledger's offers join, and the retry is armed, which finds them
action installTakenIn (n : node) {
  require ¬ installed n
  if gate n then
    everSwitched n := true
  installed n := true
  gate n := true
  got n := true
  ledger n Q := false
  tied n Q := false
}

action installStopped (n : node) {
  require ¬ installed n
  if gate n then
    everSwitched n := true
  installed n := true
  gate n := true
  stop n := true
  parked n Q := parked n Q && !tied n Q
  askedParked n Q := askedParked n Q && !tied n Q
  offered n Q := offered n Q || ledger n Q || tied n Q
  ledger n Q := false
  tied n Q := false
}

-- (two actions, by whether there is anything to ask for, so that each condition's proof can be
-- rebuilt for the kernel)
action installArm (n : node) {
  require ¬ installed n ∧ ((askLedger ∧ (∃ Q, ledger n Q)) ∨ (∃ Q, tied n Q ∨ offered n Q))
  if gate n then
    everSwitched n := true
  installed n := true
  gate n := true
  retryArmed n := true
  parked n Q := parked n Q && !tied n Q
  askedParked n Q := askedParked n Q && !tied n Q
  offered n Q := offered n Q || ledger n Q || tied n Q
  ledger n Q := false
  tied n Q := false
}

-- nothing to ask for: no tie, no offer, and (without C′'s ask, the known answer) the ledger's offers
-- join unasked
action install (n : node) {
  require ¬ installed n ∧ ¬ ((askLedger ∧ (∃ Q, ledger n Q)) ∨ (∃ Q, tied n Q ∨ offered n Q))
  if gate n then
    everSwitched n := true
  installed n := true
  gate n := true
  offered n Q := offered n Q || ledger n Q
  ledger n Q := false
}

-- §4.2: the chunk reaches n otherwise, a push with the builder's block installed: held; its promises
-- close and its offers go
action arriveOther (n : node) {
  require installed n
  got n := true
  promise n Q := false
  offered n Q := false
  askedParked n Q := false
  inWindow n := false
}

-- §4.2: an honest holder's push reaches n before the builder's block: the copy waits, kept or
-- refused; with ROOT_TIED its sender is tied, and its promise closes
action pushEarly (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ installed n
  if rootTied then
    tied n q := true
    promise n q := false
    everTied n := true
}

-- an adversary's copy that names the builder's root waits at n, before n has that block: with
-- ROOT_TIED the adversary is tied, and its promise closes; the installation releases it as any tie
action advTie (n a : node) {
  require adv a ∧ ¬ adv n ∧ n ≠ a ∧ ¬ installed n
  if rootTied then
    tied n a := true
    promise n a := false
}

-- an adversary's copy waits at n for another root, at any time: the proposer's other block's, one
-- that never installs, or one whose bid commits another group (§4.2); with ROOT_TIED the adversary
-- is tied to it, and its promise closes. Kept under level 1 by group, with `releaseElse` and
-- `dropTie`, as an over-approximation: there a copy of the group waits only before n's
-- installation, whatever root it names, unless its slot is not its group's, which a draft of the
-- rule rejects
action advTieElse (n a : node) {
  require adv a ∧ ¬ adv n ∧ n ≠ a
  if rootTied then
    tiedElse n a := true
    promise n a := false
}

-- §4.2: the root an adversary's tie names installs at n, its bid committing the group (the proposer's
-- other block): the copy fails its proof (a relabelled one, which would validate, is excluded) and
-- the tie is released: the park lifts, the last-resort count clears, and the adversary is an offer
-- again, asked for. At any time once the gate is open, any number of times (§4.2: once per block).
-- An adversary that another root still ties is this action followed at once by `advTieElse`, which
-- changes nothing else: a tied sender has no open promise, since no ask to it is written
action releaseElse (n a : node) {
  require tiedElse n a ∧ gate n
  tiedElse n a := false
  parked n a := false
  askedParked n a := false
  if ¬ got n ∧ ¬ stop n then
    offered n a := true
    retryArmed n := true
}

-- §4.2's `drop_tie`: the root an adversary's tie names installs and its bid commits another group, a
-- forgery: the tie is dropped with the adversary's offers of the index (`drop_offer`; the
-- last-resort count is left as it is; with F13's rule its queued asks go and its promise closes,
-- which a tie has closed already; without the rule both are left: F13), and the recovery goes on
-- without it, the retry armed once the gate is open; the adversary may stay tied to another root
-- (`still`)
action dropTie (n a : node) (still : Bool) {
  require tiedElse n a
  if still = false then
    tiedElse n a := false
  offered n a := false
  ledger n a := false
  if dropAsks then
    stage askQ n a J := false
  if dropPromises then
    promise n a := false
  if gate n then
    retryArmed n := true
}

-- §6.1, §8.1: an adversary's offers at n expire, 30 s after its last offer of the group, which it
-- chooses, so at any time (an honest announcer's offers outlast diffusion, as Q1 assumes): its offers
-- go, the ledger's too (`drop_offer`), and with F13's rule its queued asks of the chunk go and its
-- promise closes; nothing is armed, since the expiry calls no retry; the last-resort count lives on
-- its own
action advExpire (n a : node) {
  require adv a ∧ ¬ adv n ∧ n ≠ a
  offered n a := false
  ledger n a := false
  if dropAsks then
    stage askQ n a J := false
  if dropPromises then
    promise n a := false
}

-- an adversary asks q for the chunk (an IWANT, by full id or by index), numbered as any ask
action advAsk (a q : node) (j : ord) {
  require adv a ∧ ¬ adv q ∧ a ≠ q ∧ gate a ∧ nextAsk a q j
  made a q j := true
  stage askF a q j := true
}

-- §4.6: n's decode claim (at K of the group's chunks, which takes the builder's block): no further
-- asks, the group's promises close
action stopPull (n : node) {
  require installed n
  stop n := true
  promise n Q := false
}

-- §4.3: q learns from n's HAVE that n claims the chunk: true of an honest node, anything of an
-- adversary
action learnClaim (q n : node) {
  require got n ∨ stop n ∨ adv n
  peerHas q n := true
}

-- §6.1: a promise for another chunk of the group falls due and parks q for the group
action parkOther (n q : node) {
  parked n q := true
}

-- §8.1: the connection between n and q closes: what is queued, owed or in flight between them is
-- lost, both ways; their promises close (§6.1); the state kept per connection goes: offers (the
-- ledger's too), the last-resort counts, the asks' numbering with the serve count, ties (§8.1) and
-- claims; parks, windows and timers stay
action close (n q : node) {
  require n ≠ q
  if ∃ J, stage askQ n q J ∨ stage askF n q J then
    closedAsk n := true
  stage K n q J := false
  stage K q n J := false
  promise n q := false
  promise q n := false
  offered n q := false
  offered q n := false
  ledger n q := false
  ledger q n := false
  if countsReset then
    askedParked n q := false
    askedParked q n := false
  made n q J := false
  made q n J := false
  tied n q := false
  tied q n := false
  tiedElse n q := false
  tiedElse q n := false
  peerHas n q := false
  peerHas q n := false
}

/-! ## The machinery -/

-- §7.2: the asker drops an ask for a chunk it holds or no longer pulls, and one to a tied peer
-- (ROOT_TIED); else the promise opens (E)
action writeAsk (n q : node) (j : ord) {
  require en_writeAsk n q j
  stage askQ n q j := false
  if ¬ got n ∧ ¬ stop n ∧ ¬ tiedToRoot n q then
    stage askF n q j := true
    promise n q := true
}

-- §4.5, §4.1: q receives n's j-th ask: dropped if n claimed the chunk; answered if it is one of the
-- first three (`GOSSIP_RETRANSMISSION`), a later one perhaps; a refused answer is owed
action recvAsk (q n : node) (j : ord) (again full : Bool) {
  require en_recvAsk q n j
  stage askF n q j := false
  if ¬ peerHas q n ∧ got q ∧ (j ≠ o4 ∨ again) then
    if full then
      if owedAnswers then
        stage ansOwed q n j := true
    else
      stage ansQ q n j := true
}

-- §7.2: an owed answer is queued once there is room
action owedToQueue (q n : node) (j : ord) {
  require en_owedToQueue q n j
  stage ansOwed q n j := false
  stage ansQ q n j := true
}

-- §7.2: an answer is cancelled if n claimed the chunk meanwhile, else sent
action writeAns (q n : node) (j : ord) {
  require en_writeAns q n j
  stage ansQ q n j := false
  if ¬ peerHas q n then
    stage ansF q n j := true
}

-- §4.2, §6.3: the answer arrives. With the builder's block the chunk is held, its promises close and
-- its offers go; without it the copy waits, kept or refused, and with ROOT_TIED its sender is tied
-- and its promise closes
action recvAns (n q : node) (j : ord) {
  require en_recvAns n q j
  stage ansF q n j := false
  if installed n then
    got n := true
    promise n Q := false
    offered n Q := false
    askedParked n Q := false
    inWindow n := false
  else
    if rootTied then
      tied n q := true
      promise n q := false
      everTied n := true
}

-- §6.1: the ask's window ends
action windowElapse (n : node) {
  require en_elapse n
  inWindow n := false
}

-- §6.1: the retry finds the chunk held, or the pull stopped
action retryNoop (n : node) {
  require en_retryNoop n
  retryArmed n := false
}

-- §6.1: the retry asks an unparked announcer (any one, not tied, not outstanding); its own retry is
-- armed again
action retryAsk (n q : node) (j : ord) (full : Bool) {
  require en_retryAsk n q ∧ nextAsk n q j
  inWindow n := true
  if full = false then
    made n q j := true
    stage askQ n q j := true
}

-- §6.1: every announcer not tied is parked: the last resort, armed if one has not been asked once
-- more (two actions, by whether it is armed: Q3's step facts end in `grind`, which in Veil v4.35.0
-- does not close a step whose `if` is on an `∃`, even with a witness at hand)
ghost relation lrArm (n : node) :=
  lastResort ∧ ¬ lrArmed n ∧ (∃ Q, offered n Q ∧ ¬ tiedToRoot n Q ∧ ¬ askedParked n Q)

action retryParkedArm (n : node) {
  require en_retryParked n ∧ lrArm n
  retryArmed n := false
  lrArmed n := true
}

action retryParked (n : node) {
  require en_retryParked n ∧ ¬ lrArm n
  retryArmed n := false
}

-- §6.1: the last resort's timer: nothing to do
action lrNoop (n : node) {
  require en_lrNoop n
  lrArmed n := false
}

-- §6.1 (the last resort): an announcer unparked meanwhile, or else a parked one not asked once
-- more, neither tied nor outstanding; counted once the queue has taken the ask
action lrAsk (n q : node) (j : ord) (full : Bool) {
  require en_lrAsk n q ∧ nextAsk n q j
  lrArmed n := false
  inWindow n := true
  retryArmed n := true
  if full = false then
    made n q j := true
    stage askQ n q j := true
    if parked n q then
      askedParked n q := true
      everLastResort n := true
}

-- §6.1: a promise falls due (the answer is slow) and parks the peer for the group
action promiseDue (n q : node) {
  require en_promiseDue n q
  promise n q := false
  parked n q := true
}

-- Q3: nothing happens (a step of time: the runs a temporal proof considers take an action at every
-- step)
action stutter { pure () }

-- when the machinery is done, every offer to a node that has the builder's block has been resolved:
-- the chunk is held, or the pull stopped
safety [offers_resolve] premises → ¬ work → installed N → offered N Q → ¬ adv N → ¬ adv Q →
  got N ∨ stop N
-- under level 1 by group, at a node that has either block
safety [offers_resolve_any] premises → byGroup → ¬ work → gate N → offered N Q → ¬ adv N →
  ¬ adv Q → got N ∨ stop N

-- under level 1 by group the gate opens only with the node's installation
invariant [by_group_gate] byGroup → gate N → installed N

-- the blocks: holding and stopping take the builder's block, which opens the gate; ties wait for it
-- (under `byGroup`, `installed` is the first installation of either block)
invariant [blocks] (installed N → gate N) ∧ (got N → installed N) ∧ (stop N → installed N) ∧
  (tied N Q → ¬ adv Q → ¬ installed N)
-- offers, ties and asks go to nodes that hold the chunk; claims are true
invariant [offer_holder] (offered N Q → got Q ∨ adv Q) ∧ (ledger N Q → got Q ∨ adv Q) ∧
  (tied N Q → got Q ∨ adv Q)
-- a tie to another root is an adversary's
invariant [tied_else_adv] tiedElse N Q → adv Q
invariant [ledger_before] ledger N Q → ¬ gate N
invariant [ask_holder] stage askQ N Q J → got Q ∨ adv Q
invariant [ask_in_flight_holder] stage askF N Q J → got Q ∨ adv Q ∨ adv N
invariant [ans_holder] (stage ansQ Q N J → got Q) ∧ (stage ansOwed Q N J → got Q) ∧
  (stage ansF Q N J → got Q)
invariant [claims_true] peerHas Q N → got N ∨ stop N ∨ adv N
invariant [window_retry] inWindow N → retryArmed N
invariant [askedparked_offered] premises → ¬ adv Q → askedParked N Q → offered N Q
invariant [askedparked_parked] askedParked N Q → parked N Q
-- the machinery runs only once the gate is open
invariant [after_gate] (offered N Q → gate N) ∧ (retryArmed N → gate N) ∧ (lrArmed N → gate N) ∧
  (promise N Q → gate N) ∧ (made N Q J → gate N) ∧ (stage askQ N Q J → gate N) ∧
  (stage askF N Q J → gate N) ∧ (stage ansQ Q N J → gate N) ∧ (stage ansOwed Q N J → gate N) ∧
  (stage ansF Q N J → gate N)
-- the asks' numbers: made in order, and every stage belongs to an ask that was made
invariant [made_order] (made N Q o2 → made N Q o1) ∧ (made N Q o3 → made N Q o2) ∧
  (made N Q o4 → made N Q o3)
invariant [stage_made] (stage askQ N Q J → made N Q J) ∧ (stage askF N Q J → made N Q J) ∧
  (stage ansQ Q N J → made N Q J) ∧ (stage ansOwed Q N J → made N Q J) ∧
  (stage ansF Q N J → made N Q J)
-- an ask outstanding goes to an announcer (with F13's rule, also where the offers were dropped)
invariant [asked_offered] premises → (stage askQ N Q J → offered N Q ∨ got N) ∧
  (promise N Q → offered N Q ∨ got N)
-- F6: before the builder's block, an honest provider is asked at most twice, the second time by the
-- last resort; so its third answer is left for after the switch
invariant [first_ask] premises → ¬ adv N → ¬ adv Q → ¬ installed N → made N Q o1 →
  (∃ J, stage askQ N Q J) ∨ promise N Q ∨ parked N Q ∨ tied N Q ∨ got N ∨ stop N
invariant [second_ask] premises → ¬ adv N → ¬ adv Q → ¬ installed N → made N Q o2 →
  askedParked N Q ∨ tied N Q
invariant [two_before] premises → ¬ adv N → ¬ adv Q → ¬ installed N → ¬ made N Q o3
-- the third ask, made only with the builder's block, is answered
invariant [third_answered] premises → ¬ adv N → ¬ adv Q → made N Q o3 →
  pipeline N Q o3 ∨ got N ∨ stop N ∨ peerHas Q N
-- an offer from an unparked announcer that is not tied keeps the retry armed, and one from a parked
-- announcer not tied and not yet asked once more keeps the retry or the last resort armed
invariant [unparked_retry] premises → ¬ adv N → offered N Q → ¬ parked N Q → ¬ tiedToRoot N Q →
  got N ∨ stop N ∨ retryArmed N
invariant [parked_timer] premises → ¬ adv N → offered N Q → parked N Q → ¬ tiedToRoot N Q →
  ¬ askedParked N Q →
  got N ∨ stop N ∨ retryArmed N ∨ lrArmed N
-- an offer to a node with the builder's block keeps the asking going: a timer armed, an ask or answer
-- on its way, or every announcer parked and asked once more
invariant [offer_active] premises → ¬ adv N → installed N → offered N M →
  got N ∨ stop N ∨ retryArmed N ∨ lrArmed N ∨ (∃ Q J, pipeline N Q J) ∨
    (∀ Q, offered N Q → tiedToRoot N Q ∨ (parked N Q ∧ askedParked N Q))
-- an ask once more reaches the announcer and is answered, or waits as a tie
invariant [asked_parked] premises → ¬ adv N → ¬ adv Q → askedParked N Q →
  got N ∨ stop N ∨ tied N Q ∨ peerHas Q N ∨ (∃ J, pipeline N Q J)

-- a quiet state with an offer from an honest holder, to a node with the builder's block, unresolved
ghost relation stalled :=
  ¬ work ∧ ∃ N Q, ¬ adv N ∧ ¬ adv Q ∧ installed N ∧ offered N Q ∧ ¬ got N ∧ ¬ stop N

-- Q3 with malicious peers: the honest asking's ranking
-- (`NoStallEquiv.lean`), with ties by root: eleven levels, highest first, each a relation on (asker
-- n, announcer q, ask number z), a level that names fewer holding of every value of the others: n's
-- announcers not yet asked once more, while n neither holds the chunk nor has stopped; n's fresh
-- asks (an offer from an announcer neither parked nor tied to any root, with no promise open and
-- no ask of number z queued, while n neither holds the chunk nor has stopped); armed retries; armed
-- last resorts; ask windows; queued asks; asks in flight; open promises; owed answers; queued
-- answers; answers in flight. The levels count every node's elements, adversaries' too. Levels 0
-- and 1 are conjunctions of the literals below, stated literal by literal: in Veil v4.35.0 a
-- one-step fact with a conjunction in its conclusion fails (the reduction unfolds the step in its
-- first conjunct only).
ghost relation nGot (n : node) := ¬ got n
ghost relation nStop (n : node) := ¬ stop n
ghost relation nParked (n : node) (q : node) := ¬ parked n q
ghost relation nAP (n : node) (q : node) := ¬ askedParked n q
ghost relation nTied (n : node) (q : node) := ¬ tied n q
ghost relation nTiedE (n : node) (q : node) := ¬ tiedElse n q
ghost relation off (n : node) (q : node) := offered n q
ghost relation nProm (n : node) (q : node) := ¬ promise n q
ghost relation nAQ (n : node) (q : node) (z : ord) := ¬ stage askQ n q z
ghost relation lv2 (n : node) (_q : node) (_z : ord) := retryArmed n
ghost relation lv3 (n : node) (_q : node) (_z : ord) := lrArmed n
ghost relation lv4 (n : node) (_q : node) (_z : ord) := inWindow n
ghost relation lv5 (n : node) (q : node) (z : ord) := stage askQ n q z
ghost relation lv6 (n : node) (q : node) (z : ord) := stage askF n q z
ghost relation lv7 (n : node) (q : node) (_z : ord) := promise n q
ghost relation lv8 (n : node) (q : node) (z : ord) := stage ansOwed q n z
ghost relation lv9 (n : node) (q : node) (z : ord) := stage ansQ q n z
ghost relation lv10 (n : node) (q : node) (z : ord) := stage ansF q n z
-- the two cases of `lrAsk`
ghost relation cParked (n : node) (q : node) := parked n q
-- an honest node: the machinery's fairness is assumed for its steps
ghost relation hon (n : node) := ¬ adv n

/-! ## F14: a reconnecting adversary keeps the last resort away

An honest node n with the builder's block lacks the chunk. Its honest provider h offered the chunk
while parked by another chunk, and is not asked once more. The adversary a offers, is asked, and
closes before its promise falls due, again and again: the close does not park it (§6.1), and on
its new connection it is an announcer that is not parked. The retry would find every untied
announcer parked only at the one state between the close and the new offer; enabled there alone,
it is not forced by weak fairness, and the last resort never arms. The loop's four steps lead from
a state `f14` back to one; the assertions say which of the honest nodes' machinery events are
pending at each of the loop's states, so the run that repeats the loop is weakly fair. F14 is open:
`protocol.md` §6.1 names it ("an announcer that is never parked holds the last resort off") and
does not address it. -/

-- the three roles, in an instance of three nodes
ghost relation f14Roles (n : node) (h : node) (a : node) :=
  (∀ X, X = n ∨ X = h ∨ X = a) ∧ ¬ adv n ∧ ¬ adv h ∧ adv a ∧ n ≠ h ∧ n ≠ a ∧ h ≠ a ∧
    installed n ∧ ¬ got n ∧ ¬ stop n ∧ got h

-- the loop's state: h offered, parked, not asked once more and not tied; a offered, neither parked
-- nor tied, n's first ask to it queued and not written; n's window open, its retry armed, its last
-- resort not. (What else is between n and a goes with the loop's close: from the second turn on, it
-- is only what the new offer brings.)
ghost relation f14 (n : node) (h : node) (a : node) :=
  f14Roles n h a ∧
    offered n h ∧ parked n h ∧ ¬ askedParked n h ∧ ¬ tiedToRoot n h ∧ ¬ promise n h ∧
    offered n a ∧ ¬ parked n a ∧ ¬ tiedToRoot n a ∧ ¬ promise n a ∧
    made n a o1 ∧ ¬ made n a o2 ∧ stage askQ n a o1 ∧ ¬ stage askF n a o1 ∧
    inWindow n ∧ retryArmed n ∧ ¬ lrArmed n

-- at the loop's first state the honest nodes' machinery events are n's queued ask to a and its
-- window, and nothing else
ghost relation f14Only (n : node) (a : node) :=
  (∀ Q N J, ¬ adv Q → ¬ en_recvAsk Q N J) ∧ (∀ Q N J, ¬ adv Q → ¬ en_owedToQueue Q N J) ∧
    (∀ Q N J, ¬ adv Q → ¬ en_writeAns Q N J) ∧ (∀ N Q J, ¬ adv N → ¬ en_recvAns N Q J) ∧
    (∀ N, ¬ adv N → ¬ en_retryNoop N) ∧ (∀ N Q, ¬ adv N → ¬ en_retryAsk N Q) ∧
    (∀ N, ¬ adv N → ¬ en_retryParked N) ∧ (∀ N, ¬ adv N → ¬ en_lrNoop N) ∧
    (∀ N Q, ¬ adv N → ¬ en_lrAsk N Q) ∧ (∀ N Q, ¬ adv N → ¬ en_promiseDue N Q) ∧
    (∀ N Q J, ¬ adv N → en_writeAsk N Q J → N = n ∧ Q = a ∧ J = o1) ∧
    (∀ N, ¬ adv N → en_elapse N → N = n)

-- n's events at the loop's four states (the loop's steps touch only what is between n and a, n's
-- window and retry, and `closedAsk n`, so every other honest event stays as `f14Only` has it: none)
ghost relation f14s0 (n : node) (h : node) (a : node) :=
  en_writeAsk n a o1 ∧ en_elapse n ∧ ¬ en_promiseDue n a ∧ ¬ en_retryParked n ∧
    ¬ en_retryAsk n a ∧ ¬ en_retryAsk n h
ghost relation f14s1 (n : node) (h : node) (a : node) :=
  ¬ en_writeAsk n a o1 ∧ en_elapse n ∧ en_promiseDue n a ∧ ¬ en_retryParked n ∧
    ¬ en_retryAsk n a ∧ ¬ en_retryAsk n h ∧ ¬ en_lrNoop n ∧ ¬ en_lrAsk n a ∧ ¬ en_lrAsk n h
ghost relation f14s2 (n : node) (h : node) (a : node) :=
  ¬ en_writeAsk n a o1 ∧ ¬ en_elapse n ∧ en_promiseDue n a ∧ ¬ en_retryParked n ∧
    ¬ en_retryAsk n a ∧ ¬ en_retryAsk n h ∧ ¬ en_lrNoop n ∧ ¬ en_lrAsk n a ∧ ¬ en_lrAsk n h
ghost relation f14s3 (n : node) (h : node) (a : node) :=
  ¬ en_writeAsk n a o1 ∧ ¬ en_elapse n ∧ ¬ en_promiseDue n a ∧ en_retryParked n ∧
    ¬ en_retryAsk n a ∧ ¬ en_retryAsk n h ∧ ¬ en_lrNoop n ∧ ¬ en_lrAsk n a ∧ ¬ en_lrAsk n h ∧
    ¬ offered n a ∧ ¬ parked n a ∧ ¬ promise n a

-- Q3 with malicious peers: with finitely many nodes, NO_REASK_OPEN, the machinery's actions weakly
-- fair at every honest node (the retry's and the last resort's asks that a queue takes; an
-- adversary's steps are not forced) and an environment that eventually stops, the adversaries'
-- actions and a queue's refusal of an ask included, the honest nodes' machinery eventually has
-- nothing to do, for good. In a proof `⟨a⟩` says that a step has the effect of some execution of
-- `a`, whatever action took it; so "the environment stops" is stated as: from some point on, every
-- step that changes the state has a machinery action's effect, any node's, or no environment
-- action's
temporal (only := verify) [quiet]
  ⌞ ∃ l : List node, ∀ n : node, n ∈ l ⌟ ∧ ⌜ noReask ⌝ ∧ (∀ m : node, ⌜ hon m ⌝ →
  (𝒲ℱ (writeAsk m · ·) ∧ 𝒲ℱ (recvAsk m · · · ·) ∧ 𝒲ℱ (owedToQueue m · ·) ∧ 𝒲ℱ (writeAns m · ·) ∧
  𝒲ℱ (recvAns m · ·) ∧ 𝒲ℱ (windowElapse m) ∧ 𝒲ℱ (retryNoop m) ∧ 𝒲ℱ (retryAsk m · · false) ∧
  𝒲ℱ (retryParked m) ∧ 𝒲ℱ (retryParkedArm m) ∧ 𝒲ℱ (lrNoop m) ∧ 𝒲ℱ (lrAsk m · · false) ∧
  𝒲ℱ (promiseDue m ·))) ∧
  ◇ □ (⟨stutter⟩ ∨ ⟨writeAsk⟩ ∨ ⟨recvAsk⟩ ∨ ⟨owedToQueue⟩ ∨ ⟨writeAns⟩ ∨ ⟨recvAns⟩ ∨
    ⟨windowElapse⟩ ∨ ⟨retryNoop⟩ ∨ ⟨retryAsk · · · false⟩ ∨ ⟨retryParked⟩ ∨ ⟨retryParkedArm⟩ ∨
    ⟨lrNoop⟩ ∨ ⟨lrAsk · · · false⟩ ∨ ⟨promiseDue⟩ ∨ (¬ ⟨offerEarly⟩ ∧ ¬ ⟨offerAsk⟩ ∧
    ¬ ⟨offerRecord⟩ ∧ ¬ ⟨offerParkedArm⟩ ∧ ¬ ⟨offerParked⟩ ∧ ¬ ⟨offerParkedUnparked⟩ ∧
    ¬ ⟨offerParkedAsked⟩ ∧ ¬ ⟨offerParkedAskedNew⟩ ∧ ¬ ⟨offerParkedNoLR⟩ ∧ ¬ ⟨offerHeldBack⟩ ∧
    ¬ ⟨installOther⟩ ∧ ¬ ⟨installTakenIn⟩ ∧ ¬ ⟨installStopped⟩ ∧ ¬ ⟨installArm⟩ ∧ ¬ ⟨install⟩ ∧
    ¬ ⟨arriveOther⟩ ∧ ¬ ⟨pushEarly⟩ ∧ ¬ ⟨advTie⟩ ∧ ¬ ⟨advTieElse⟩ ∧ ¬ ⟨releaseElse⟩ ∧ ¬ ⟨dropTie⟩ ∧
    ¬ ⟨advExpire⟩ ∧ ¬ ⟨advAsk⟩ ∧ ¬ ⟨stopPull⟩ ∧ ¬ ⟨learnClaim⟩ ∧ ¬ ⟨parkOther⟩ ∧ ¬ ⟨close⟩ ∧
    ¬ ⟨retryAsk · · · true⟩ ∧ ¬ ⟨lrAsk · · · true⟩)) →
  ◇ □ ⌜ ¬ work ⌝
temporal (only := verify) [workEnabled]
  □ (⌜ work ⌝ → (∃ n, ∃ q, ∃ j, ⌜ hon n ⌝ ∧ Enabled (writeAsk n q j)) ∨ (∃ q, ∃ n, ∃ j, ⌜ hon q ⌝ ∧
    Enabled (recvAsk q n j false false)) ∨ (∃ q, ∃ n, ∃ j, ⌜ hon q ⌝ ∧
    Enabled (owedToQueue q n j)) ∨ (∃ q, ∃ n, ∃ j, ⌜ hon q ⌝ ∧ Enabled (writeAns q n j)) ∨
    (∃ n, ∃ q, ∃ j, ⌜ hon n ⌝ ∧ Enabled (recvAns n q j)) ∨ (∃ n, ⌜ hon n ⌝ ∧
    Enabled (windowElapse n)) ∨ (∃ n, ⌜ hon n ⌝ ∧ Enabled (retryNoop n)) ∨
    (∃ n, ∃ q, ∃ j, ⌜ hon n ⌝ ∧ Enabled (retryAsk n q j false)) ∨ (∃ n, ⌜ hon n ⌝ ∧
    Enabled (retryParked n)) ∨ (∃ n, ⌜ hon n ⌝ ∧ Enabled (retryParkedArm n)) ∨ (∃ n, ⌜ hon n ⌝ ∧
    Enabled (lrNoop n)) ∨ (∃ n, ∃ q, ∃ j, ⌜ hon n ⌝ ∧ Enabled (lrAsk n q j false)) ∨
    (∃ n, ∃ q, ⌜ hon n ⌝ ∧ Enabled (promiseDue n q)))
temporal (only := verify) [writeAskPre_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨writeAsk n q j⟩ → ⌜ lv5 n q j ⌝)
temporal (only := verify) [writeAskPost]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨writeAsk n q j⟩ → ¬ ◯ ⌜ lv5 n q j ⌝)
temporal (only := verify) [writeAskKeep_0_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [writeAskKeep_0_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [writeAskKeep_0_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [writeAskKeep_1_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [writeAskKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [writeAskKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [writeAskKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [writeAskKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [writeAskKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [writeAskKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [writeAskKeep_1_7]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [writeAskKeep_2_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [writeAskKeep_3_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ lv3 x y z ⌝ → ⌜ lv3 x y z ⌝)
temporal (only := verify) [writeAskKeep_4_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ lv4 x y z ⌝ → ⌜ lv4 x y z ⌝)
temporal (only := verify) [writeAskKeep_5_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ lv5 x y z ⌝ → ⌜ lv5 x y z ⌝)
temporal (only := verify) [recvAskPre_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, □ (⟨recvAsk q n j ag fu⟩ →
    ⌜ lv6 n q j ⌝)
temporal (only := verify) [recvAskPost]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, □ (⟨recvAsk q n j ag fu⟩ →
    ¬ ◯ ⌜ lv6 n q j ⌝)
temporal (only := verify) [recvAskKeep_0_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [recvAskKeep_0_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [recvAskKeep_0_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [recvAskKeep_1_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [recvAskKeep_1_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [recvAskKeep_1_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [recvAskKeep_1_3]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [recvAskKeep_1_4]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [recvAskKeep_1_5]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [recvAskKeep_1_6]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [recvAskKeep_1_7]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [recvAskKeep_2_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [recvAskKeep_3_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ lv3 x y z ⌝ → ⌜ lv3 x y z ⌝)
temporal (only := verify) [recvAskKeep_4_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ lv4 x y z ⌝ → ⌜ lv4 x y z ⌝)
temporal (only := verify) [recvAskKeep_5_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ lv5 x y z ⌝ → ⌜ lv5 x y z ⌝)
temporal (only := verify) [recvAskKeep_6_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ lv6 x y z ⌝ → ⌜ lv6 x y z ⌝)
temporal (only := verify) [owedToQueuePre_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, □ (⟨owedToQueue q n j⟩ → ⌜ lv8 n q j ⌝)
temporal (only := verify) [owedToQueuePost]
  ∀ q : node, ∀ n : node, ∀ j : ord, □ (⟨owedToQueue q n j⟩ → ¬ ◯ ⌜ lv8 n q j ⌝)
temporal (only := verify) [owedToQueueKeep_0_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [owedToQueueKeep_0_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [owedToQueueKeep_0_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [owedToQueueKeep_1_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [owedToQueueKeep_1_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_3]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_4]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_5]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_6]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_7]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [owedToQueueKeep_2_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [owedToQueueKeep_3_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv3 x y z ⌝ → ⌜ lv3 x y z ⌝)
temporal (only := verify) [owedToQueueKeep_4_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv4 x y z ⌝ → ⌜ lv4 x y z ⌝)
temporal (only := verify) [owedToQueueKeep_5_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv5 x y z ⌝ → ⌜ lv5 x y z ⌝)
temporal (only := verify) [owedToQueueKeep_6_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv6 x y z ⌝ → ⌜ lv6 x y z ⌝)
temporal (only := verify) [owedToQueueKeep_7_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv7 x y z ⌝ → ⌜ lv7 x y z ⌝)
temporal (only := verify) [owedToQueueKeep_8_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ lv8 x y z ⌝ → ⌜ lv8 x y z ⌝)
temporal (only := verify) [writeAnsPre_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, □ (⟨writeAns q n j⟩ → ⌜ lv9 n q j ⌝)
temporal (only := verify) [writeAnsPost]
  ∀ q : node, ∀ n : node, ∀ j : ord, □ (⟨writeAns q n j⟩ → ¬ ◯ ⌜ lv9 n q j ⌝)
temporal (only := verify) [writeAnsKeep_0_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [writeAnsKeep_0_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [writeAnsKeep_0_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [writeAnsKeep_1_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [writeAnsKeep_1_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [writeAnsKeep_1_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [writeAnsKeep_1_3]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [writeAnsKeep_1_4]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [writeAnsKeep_1_5]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [writeAnsKeep_1_6]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [writeAnsKeep_1_7]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [writeAnsKeep_2_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [writeAnsKeep_3_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv3 x y z ⌝ → ⌜ lv3 x y z ⌝)
temporal (only := verify) [writeAnsKeep_4_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv4 x y z ⌝ → ⌜ lv4 x y z ⌝)
temporal (only := verify) [writeAnsKeep_5_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv5 x y z ⌝ → ⌜ lv5 x y z ⌝)
temporal (only := verify) [writeAnsKeep_6_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv6 x y z ⌝ → ⌜ lv6 x y z ⌝)
temporal (only := verify) [writeAnsKeep_7_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv7 x y z ⌝ → ⌜ lv7 x y z ⌝)
temporal (only := verify) [writeAnsKeep_8_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv8 x y z ⌝ → ⌜ lv8 x y z ⌝)
temporal (only := verify) [writeAnsKeep_9_0]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ lv9 x y z ⌝ → ⌜ lv9 x y z ⌝)
temporal (only := verify) [recvAnsPre_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨recvAns n q j⟩ → ⌜ lv10 n q j ⌝)
temporal (only := verify) [recvAnsPost]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨recvAns n q j⟩ → ¬ ◯ ⌜ lv10 n q j ⌝)
temporal (only := verify) [recvAnsKeep_0_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [recvAnsKeep_0_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [recvAnsKeep_0_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [recvAnsKeep_1_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [recvAnsKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [recvAnsKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [recvAnsKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [recvAnsKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [recvAnsKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [recvAnsKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [recvAnsKeep_1_7]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [recvAnsKeep_2_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [recvAnsKeep_3_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv3 x y z ⌝ → ⌜ lv3 x y z ⌝)
temporal (only := verify) [recvAnsKeep_4_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv4 x y z ⌝ → ⌜ lv4 x y z ⌝)
temporal (only := verify) [recvAnsKeep_5_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv5 x y z ⌝ → ⌜ lv5 x y z ⌝)
temporal (only := verify) [recvAnsKeep_6_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv6 x y z ⌝ → ⌜ lv6 x y z ⌝)
temporal (only := verify) [recvAnsKeep_7_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv7 x y z ⌝ → ⌜ lv7 x y z ⌝)
temporal (only := verify) [recvAnsKeep_8_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv8 x y z ⌝ → ⌜ lv8 x y z ⌝)
temporal (only := verify) [recvAnsKeep_9_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv9 x y z ⌝ → ⌜ lv9 x y z ⌝)
temporal (only := verify) [recvAnsKeep_10_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ lv10 x y z ⌝ → ⌜ lv10 x y z ⌝)
temporal (only := verify) [windowElapsePre_0]
  ∀ n : node, □ (⟨windowElapse n⟩ → ⌜ lv4 n n o1 ⌝)
temporal (only := verify) [windowElapsePost]
  ∀ n : node, □ (⟨windowElapse n⟩ → ¬ ◯ ⌜ lv4 n n o1 ⌝)
temporal (only := verify) [windowElapseKeep_0_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [windowElapseKeep_0_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [windowElapseKeep_0_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [windowElapseKeep_1_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [windowElapseKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [windowElapseKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [windowElapseKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [windowElapseKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [windowElapseKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [windowElapseKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [windowElapseKeep_1_7]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [windowElapseKeep_2_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ lv2 x y z ⌝ →
    ⌜ lv2 x y z ⌝)
temporal (only := verify) [windowElapseKeep_3_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ lv3 x y z ⌝ →
    ⌜ lv3 x y z ⌝)
temporal (only := verify) [windowElapseKeep_4_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ lv4 x y z ⌝ →
    ⌜ lv4 x y z ⌝)
temporal (only := verify) [retryNoopPre_0]
  ∀ n : node, □ (⟨retryNoop n⟩ → ⌜ lv2 n n o1 ⌝)
temporal (only := verify) [retryNoopPost]
  ∀ n : node, □ (⟨retryNoop n⟩ → ¬ ◯ ⌜ lv2 n n o1 ⌝)
temporal (only := verify) [retryNoopKeep_0_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryNoopKeep_0_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryNoopKeep_0_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [retryNoopKeep_1_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryNoopKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryNoopKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [retryNoopKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [retryNoopKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [retryNoopKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [retryNoopKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [retryNoopKeep_1_7]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [retryNoopKeep_2_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [retryAskPre_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nGot n ⌝)
temporal (only := verify) [retryAskPre_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nStop n ⌝)
temporal (only := verify) [retryAskPre_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ off n q ⌝)
temporal (only := verify) [retryAskPre_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nParked n q ⌝)
temporal (only := verify) [retryAskPre_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nTied n q ⌝)
temporal (only := verify) [retryAskPre_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nTiedE n q ⌝)
temporal (only := verify) [retryAskPre_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nProm n q ⌝)
temporal (only := verify) [retryAskPre_7]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nAQ n q j ⌝)
temporal (only := verify) [retryAskPost]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ¬ ◯ ⌜ nAQ n q j ⌝)
temporal (only := verify) [retryAskKeep_0_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryAskKeep_0_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryAskKeep_0_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [retryAskKeep_1_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryAskKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryAskKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [retryAskKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [retryAskKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [retryAskKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [retryAskKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [retryAskKeep_1_7]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [retryParkedPre_0]
  ∀ n : node, □ (⟨retryParked n⟩ → ⌜ lv2 n n o1 ⌝)
temporal (only := verify) [retryParkedPost]
  ∀ n : node, □ (⟨retryParked n⟩ → ¬ ◯ ⌜ lv2 n n o1 ⌝)
temporal (only := verify) [retryParkedKeep_0_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryParkedKeep_0_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryParkedKeep_0_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [retryParkedKeep_1_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryParkedKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryParkedKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [retryParkedKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [retryParkedKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [retryParkedKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [retryParkedKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [retryParkedKeep_1_7]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [retryParkedKeep_2_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ lv2 x y z ⌝ →
    ⌜ lv2 x y z ⌝)
temporal (only := verify) [retryParkedArmPre_0]
  ∀ n : node, □ (⟨retryParkedArm n⟩ → ⌜ lv2 n n o1 ⌝)
temporal (only := verify) [retryParkedArmPost]
  ∀ n : node, □ (⟨retryParkedArm n⟩ → ¬ ◯ ⌜ lv2 n n o1 ⌝)
temporal (only := verify) [retryParkedArmKeep_0_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryParkedArmKeep_0_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryParkedArmKeep_0_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryParkedArmKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryParkedArmKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_7]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [retryParkedArmKeep_2_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ lv2 x y z ⌝ →
    ⌜ lv2 x y z ⌝)
temporal (only := verify) [lrNoopPre_0]
  ∀ n : node, □ (⟨lrNoop n⟩ → ⌜ lv3 n n o1 ⌝)
temporal (only := verify) [lrNoopPost]
  ∀ n : node, □ (⟨lrNoop n⟩ → ¬ ◯ ⌜ lv3 n n o1 ⌝)
temporal (only := verify) [lrNoopKeep_0_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [lrNoopKeep_0_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [lrNoopKeep_0_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [lrNoopKeep_1_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [lrNoopKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [lrNoopKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [lrNoopKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [lrNoopKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [lrNoopKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [lrNoopKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [lrNoopKeep_1_7]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [lrNoopKeep_2_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ lv2 x y z ⌝ → ⌜ lv2 x y z ⌝)
temporal (only := verify) [lrNoopKeep_3_0]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ lv3 x y z ⌝ → ⌜ lv3 x y z ⌝)
temporal (only := verify) [lrAskPre1_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ cParked n q ⌝ → ⌜ nGot n ⌝)
temporal (only := verify) [lrAskPre1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ cParked n q ⌝ → ⌜ nStop n ⌝)
temporal (only := verify) [lrAskPre1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ cParked n q ⌝ → ⌜ nAP n q ⌝)
temporal (only := verify) [lrAskPost1]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ cParked n q ⌝ → ¬ ◯ ⌜ nAP n q ⌝)
temporal (only := verify) [lrAskKeep1_0_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [lrAskKeep1_0_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [lrAskKeep1_0_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [lrAskPre2_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nGot n ⌝)
temporal (only := verify) [lrAskPre2_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nStop n ⌝)
temporal (only := verify) [lrAskPre2_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ off n q ⌝)
temporal (only := verify) [lrAskPre2_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nParked n q ⌝)
temporal (only := verify) [lrAskPre2_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nTied n q ⌝)
temporal (only := verify) [lrAskPre2_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nTiedE n q ⌝)
temporal (only := verify) [lrAskPre2_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nProm n q ⌝)
temporal (only := verify) [lrAskPre2_7]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ⌜ noReask ⌝ →
    ⌜ nAQ n q j ⌝)
temporal (only := verify) [lrAskPost2]
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨lrAsk n q j false⟩ → ⌜ ¬ cParked n q ⌝ → ¬ ◯ ⌜ nAQ n q j ⌝)
temporal (only := verify) [lrAskKeep2_0_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [lrAskKeep2_0_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [lrAskKeep2_0_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [lrAskKeep2_1_0]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [lrAskKeep2_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [lrAskKeep2_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [lrAskKeep2_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [lrAskKeep2_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [lrAskKeep2_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [lrAskKeep2_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [lrAskKeep2_1_7]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [promiseDuePre_0]
  ∀ n : node, ∀ q : node, □ (⟨promiseDue n q⟩ → ⌜ lv7 n q o1 ⌝)
temporal (only := verify) [promiseDuePost]
  ∀ n : node, ∀ q : node, □ (⟨promiseDue n q⟩ → ¬ ◯ ⌜ lv7 n q o1 ⌝)
temporal (only := verify) [promiseDueKeep_0_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [promiseDueKeep_0_1]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [promiseDueKeep_0_2]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ nAP x y ⌝ → ⌜ nAP x y ⌝)
temporal (only := verify) [promiseDueKeep_1_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [promiseDueKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [promiseDueKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [promiseDueKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [promiseDueKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [promiseDueKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTiedE x y ⌝)
temporal (only := verify) [promiseDueKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [promiseDueKeep_1_7]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nTiedE x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
temporal (only := verify) [promiseDueKeep_2_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ lv2 x y z ⌝ →
    ⌜ lv2 x y z ⌝)
temporal (only := verify) [promiseDueKeep_3_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ lv3 x y z ⌝ →
    ⌜ lv3 x y z ⌝)
temporal (only := verify) [promiseDueKeep_4_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ lv4 x y z ⌝ →
    ⌜ lv4 x y z ⌝)
temporal (only := verify) [promiseDueKeep_5_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ lv5 x y z ⌝ →
    ⌜ lv5 x y z ⌝)
temporal (only := verify) [promiseDueKeep_6_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ lv6 x y z ⌝ →
    ⌜ lv6 x y z ⌝)
temporal (only := verify) [promiseDueKeep_7_0]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ lv7 x y z ⌝ →
    ⌜ lv7 x y z ⌝)

#gen_spec

/-! ## Non-vacuity: with every rule on, runs reach a quiet state -/

-- an offer, asked for and answered, without equivocation
sat trace [offer_answered] {
  installTakenIn
  install
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧ ∃ N Q, got N ∧ made N Q o1)
}

-- a node on the other block asks; the answer waits, ties its sender and closes its promise (the
-- longer run, through the switch, exceeds the simplifier's steps: the next trace starts from a tie)
sat trace [tie_on_other_block] {
  installTakenIn
  installOther
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  assert (premises ∧ (∀ A, ¬ adv A) ∧
    ∃ N Q, gate N ∧ ¬ installed N ∧ tied N Q ∧ ¬ promise N Q ∧ made N Q o1)
}

-- a node on the other block, its sender tied by a waiting copy; the switch releases the tie, the
-- sender is asked, and the chunk validates
sat trace [switch_asks_tied] {
  installTakenIn
  installOther
  pushEarly
  installArm
  retryAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧ ∃ N, got N ∧ everSwitched N ∧ everTied N)
}

-- the offerer parked by another chunk: the last resort asks it once more
sat trace [last_resort_resolves] {
  installTakenIn
  install
  parkOther
  offerParkedArm
  lrAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧ ∃ N, got N ∧ everLastResort N)
}

-- an offer before any block, asked for once the builder's block installs
sat trace [ledger_asks] {
  installTakenIn
  offerEarly
  installArm
  retryAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧ ∃ N, got N ∧ everEarly N)
}

-- an ask lost with its connection: the announcer offers again on the new one (F9's resync), and is
-- asked, its asks numbered afresh
sat trace [close_reasked] {
  installTakenIn
  install
  offerAsk
  close
  windowElapse
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  assert (premises ∧ (∀ A, ¬ adv A) ∧ ∃ N, got N ∧ closedAsk N)
}

-- an adversary offers and never answers: its promise falls due and parks it, the chunk arrives
-- otherwise, and the state is quiet with the ask to the adversary waiting there for good
sat trace [adv_withholds] {
  install
  offerAsk
  writeAsk
  promiseDue
  windowElapse
  arriveOther
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N A J, ¬ adv N ∧ got N ∧ adv A ∧ parked N A ∧ stage askF N A J)
}

-- an adversary tied to another root after the builder's block, while an honest provider's offer is
-- asked for and answered: the tie does not keep the honest offer from resolving
sat trace [adv_tied_honest_resolves] {
  installTakenIn
  install
  advTieElse
  offerRecord
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N A M, ¬ adv N ∧ adv A ∧ ¬ adv M ∧ got N ∧ tiedElse N A ∧ made N M o1)
}

-- an adversary's copy waits for a root that never installs at a node with the builder's block: the
-- adversary stays tied, and passed over, in a quiet state
sat trace [adv_tied_after_block] {
  install
  advTieElse
  offerRecord
  assert (premises ∧ ¬ work ∧ ∃ N A, ¬ adv N ∧ adv A ∧ installed N ∧ tiedElse N A ∧ offered N A)
}

-- an adversary tied to the other block's root, released by that block's installation: an offer
-- again, asked for
sat trace [adv_tie_released] {
  install
  advTieElse
  offerRecord
  releaseElse
  retryAsk
  assert (premises ∧ ∃ N A J, ¬ adv N ∧ adv A ∧ installed N ∧ ¬ tiedElse N A ∧ stage askQ N A J)
}

-- an adversary's tie whose root's bid commits another group: dropped with its offers, the retry armed
sat trace [adv_tie_dropped] {
  install
  advTieElse
  offerRecord
  dropTie
  assert (premises ∧ ∃ N A, ¬ adv N ∧ adv A ∧ installed N ∧ ¬ tiedToRoot N A ∧ ¬ offered N A ∧
    retryArmed N)
}

-- an adversary's offers expire with its ask still queued: the ask goes with them (F13's rule), and
-- the adversary's next offer is asked for
sat trace [adv_offer_expired] {
  install
  offerAsk
  advExpire
  windowElapse
  offerAsk
  assert (premises ∧ ∃ N A, ¬ adv N ∧ adv A ∧ installed N ∧ made N A o2 ∧ stage askQ N A o2 ∧
    ¬ stage askQ N A o1 ∧ ¬ stage askF N A o1)
}

-- under level 1 by group: an offer asked for and answered at the node's installation, of either
-- block
sat trace [by_group_answered] {
  installTakenIn
  install
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ byGroup ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧ ∃ N Q, got N ∧ made N Q o1)
}

-- under level 1 by group: a copy that waits before the installation ties its sender, and the
-- installation releases the tie: the sender is asked, and the chunk validates
sat trace [by_group_tie_released] {
  installTakenIn
  pushEarly
  installArm
  retryAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ byGroup ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧ ∃ N, got N ∧ everTied N)
}

/-! ## Known answers: with one rule off, the machinery fails -/

-- without level 1 by group, a node with only the other block: its gate is open, but the provider's
-- answer, naming the builder's block, waits there and ties the provider, and the retry finds every
-- announcer tied: a quiet state with the offer unresolved at a node that has a block committing the
-- group. A known answer for `offers_resolve_any`, not a finding: v0.8 never claimed this node's
-- offers resolve (it has not the builder's block)
sat trace [ka_other_block_stalls] {
  installTakenIn
  installOther
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  windowElapse
  retryParked
  assert (premises ∧ ¬ byGroup ∧ (∀ A, ¬ adv A) ∧ ¬ work ∧
    ∃ N Q, gate N ∧ ¬ installed N ∧ offered N Q ∧ ¬ got N ∧ ¬ stop N)
}

-- F6's first form, without ROOT_TIED: on the other block, the provider (parked by another chunk) is
-- asked once more by the last resort; the answer waits and its promise falls due; at the switch
-- every announcer is parked and has been asked once more, with nothing on its way, so no ask can
-- follow: the retry the installation arms finds them all parked and arms no last resort (the run to
-- that quiet state exceeds the simplifier's steps)
sat trace [ka_no_root_tied] {
  installTakenIn
  installOther
  parkOther
  offerParkedArm
  lrAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  promiseDue
  installArm
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ ¬ rootTied ∧ noReask ∧ countsReset ∧
    (∀ A, ¬ adv A) ∧
    ∃ N Q, installed N ∧ offered N Q ∧ ¬ got N ∧ ¬ stop N ∧ ¬ lrArmed N ∧ ¬ promise N Q ∧
      (∀ P, offered N P → parked N P ∧ askedParked N P) ∧ (∀ P J, ¬ pipeline N P J))
}

-- F6's second form, without NO_REASK_OPEN: asks decided while the first answer is on its way, so a
-- provider is asked a third time before the switch (the bound `two_before` fails): once these asks
-- are answered, its last answer within the budget is spent on a copy that cannot validate (the run
-- through the answers and the switch to the stall is the Quint model's, too long for a trace here)
sat trace [ka_no_reask] {
  installTakenIn
  installOther
  offerAsk
  windowElapse
  retryAsk
  windowElapse
  retryAsk
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ ¬ noReask ∧ countsReset ∧
    (∀ A, ¬ adv A) ∧ ∃ N Q, ¬ installed N ∧ made N Q o3)
}

-- F2: an offerer parked by another chunk is never asked
sat trace [ka_no_last_resort] {
  installTakenIn
  install
  parkOther
  offerParkedNoLR
  assert (¬ lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset ∧
    stalled)
}

-- an offer recorded before any block is never asked for
sat trace [ka_no_ledger] {
  installTakenIn
  offerEarly
  install
  assert (lastResort ∧ owedAnswers ∧ ¬ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset ∧
    stalled)
}

-- the last-resort count kept across a close: the ask it counted is lost with the connection, the
-- announcer offers again on the new one, and it is never asked: its count says it was asked once
-- more
sat trace [ka_counts_kept] {
  installTakenIn
  install
  parkOther
  offerParkedArm
  lrAsk
  close
  offerParkedAskedNew
  windowElapse
  retryParked
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧
    ¬ countsReset ∧ stalled)
}

-- F13, without the rule's queued asks (its promises closing does not help: a tie closed the promise):
-- an ask to an adversary, still queued when its tie is dropped, is written once the tie is gone; the
-- retry, finding no announcer, ends; the adversary offers again while the ask is outstanding
-- (recorded only), an honest announcer parked by another chunk offers while the adversary is
-- unparked (no last resort), and the adversary's promise falls due and parks it: a quiet state with
-- the honest offer never asked
sat trace [ka_drop_keeps_asks] {
  installTakenIn
  install
  parkOther
  offerAsk
  advTieElse
  dropTie
  windowElapse
  retryParked
  writeAsk
  offerRecord
  offerParkedUnparked
  promiseDue
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset ∧
    ¬ dropAsks ∧ dropPromises ∧ stalled)
}

-- F13 by an offer's expiry, without the rule's queued asks: the same run, the adversary's offers
-- expiring where its tie was dropped
sat trace [ka_expiry_keeps_asks] {
  installTakenIn
  install
  parkOther
  offerAsk
  advExpire
  windowElapse
  retryParked
  writeAsk
  offerRecord
  offerParkedUnparked
  promiseDue
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset ∧
    ¬ dropAsks ∧ dropPromises ∧ stalled)
}

-- F13 by an offer's expiry, without the rule's promises: the ask to the adversary is written before
-- its offers expire, and its open promise keeps the adversary outstanding as the queued ask did
sat trace [ka_expiry_keeps_promise] {
  installTakenIn
  install
  parkOther
  offerAsk
  writeAsk
  advExpire
  windowElapse
  retryParked
  offerRecord
  offerParkedUnparked
  promiseDue
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset ∧
    dropAsks ∧ ¬ dropPromises ∧ stalled)
}

/-! ### F14's run -/

-- F14's loop, under v0.8's rules (every rule on, level 1 by group off): h holds the chunk, n installs
-- the builder's block with nothing to ask for, a offers and is asked, a slow answer on another chunk
-- parks h, and h offers, which is only recorded since a is not parked: `f14`. Then n writes its ask
-- to a, the ask's window ends, a closes before its promise falls due, and a offers again and is asked:
-- `f14` again, with the same three nodes and a close behind. One trace per state of the loop, each
-- asserting at its end (Veil's simplification of one trace with the five assertions exceeds its
-- steps); in an instance of three nodes with these roles every step's arguments are forced but the
-- order of `close`'s two nodes, which changes only the trace marker `closedAsk`, so the five are one
-- run, cut at each state
sat trace [ka_f14_s0] {
  installTakenIn
  install
  offerAsk
  parkOther
  offerParkedUnparked
  assert (premises ∧ ¬ byGroup ∧ ∃ N H A, f14 N H A ∧ f14Only N A ∧ f14s0 N H A)
}

sat trace [ka_f14_s1] {
  installTakenIn
  install
  offerAsk
  parkOther
  offerParkedUnparked
  writeAsk
  assert (premises ∧ ¬ byGroup ∧ ∃ N H A, f14Roles N H A ∧ f14s1 N H A)
}

sat trace [ka_f14_s2] {
  installTakenIn
  install
  offerAsk
  parkOther
  offerParkedUnparked
  writeAsk
  windowElapse
  assert (premises ∧ ¬ byGroup ∧ ∃ N H A, f14Roles N H A ∧ f14s2 N H A)
}

sat trace [ka_f14_s3] {
  installTakenIn
  install
  offerAsk
  parkOther
  offerParkedUnparked
  writeAsk
  windowElapse
  close
  assert (premises ∧ ¬ byGroup ∧ ∃ N H A, f14Roles N H A ∧ f14s3 N H A)
}

sat trace [ka_f14_loop] {
  installTakenIn
  install
  offerAsk
  parkOther
  offerParkedUnparked
  writeAsk
  windowElapse
  close
  offerAsk
  assert (premises ∧ ¬ byGroup ∧ ∃ N H A, f14 N H A ∧ f14Only N A ∧ f14s0 N H A ∧ closedAsk N)
}

-- the control: the same run up to the close, after which a does not offer again: the retry finds
-- every announcer parked and arms the last resort, which asks h once more
sat trace [f14_control] {
  installTakenIn
  install
  offerAsk
  parkOther
  offerParkedUnparked
  writeAsk
  windowElapse
  close
  retryParkedArm
  lrAsk
  assert (premises ∧ ¬ byGroup ∧ ∃ N H A, f14Roles N H A ∧ askedParked N H ∧ stage askQ N H o1 ∧
    everLastResort N ∧ closedAsk N)
}

/-! ## The proof: the clauses above are an inductive invariant -/

#check_invariants

-- each proof as a theorem in the environment, which Lean's kernel checks as it adds it
#gen_theorems

/-! ## Q3 with malicious peers: the honest machinery goes quiet

The ranking's facts, per action of the machinery and case: its witness element is at its level
before the step (`…Pre`) and not after (`…Post`), and no level down to its own gains an element
(`…Keep_j`). Then the proof: a list of the nodes and of the ask numbers, the ranking's counts, the
steps sorted into the machinery's (any node's), the environment's (the adversaries' and refused
asks included) and stutters, the fair families (one action's steps taken by one honest node), and
`FvQuiet.quiet_exec`. -/

prove_temporal_by [writeAskPre_0]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [writeAskPost]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_0_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_0_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_0_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_3]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_4]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_5]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_6]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_1_7]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_2_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_3_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_4_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAskKeep_5_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskPre_0]
  tclear hInit hInv
  tintro q n j ag fu
  tmonotone
  fv_step

prove_temporal_by [recvAskPost]
  tclear hInit hInv
  tintro q n j ag fu
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_0_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_0_1]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_0_2]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_1]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_2]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_3]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_4]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_5]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_6]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_1_7]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_2_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_3_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_4_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_5_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [recvAskKeep_6_0]
  tclear hInit hInv
  tintro q n j ag fu x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueuePre_0]
  tclear hInit hInv
  tintro q n j
  tmonotone
  fv_step

prove_temporal_by [owedToQueuePost]
  tclear hInit hInv
  tintro q n j
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_0_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_0_1]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_0_2]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_1]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_2]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_3]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_4]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_5]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_6]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_1_7]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_2_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_3_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_4_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_5_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_6_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_7_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [owedToQueueKeep_8_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsPre_0]
  tclear hInit hInv
  tintro q n j
  tmonotone
  fv_step

prove_temporal_by [writeAnsPost]
  tclear hInit hInv
  tintro q n j
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_0_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_0_1]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_0_2]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_1]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_2]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_3]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_4]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_5]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_6]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_1_7]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_2_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_3_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_4_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_5_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_6_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_7_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_8_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [writeAnsKeep_9_0]
  tclear hInit hInv
  tintro q n j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsPre_0]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [recvAnsPost]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_0_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_0_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_0_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_3]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_4]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_5]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_6]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_1_7]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_2_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_3_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_4_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_5_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_6_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_7_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_8_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_9_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [recvAnsKeep_10_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapsePre_0]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [windowElapsePost]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_0_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_0_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_0_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_3]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_4]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_5]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_6]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_1_7]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_2_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_3_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [windowElapseKeep_4_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopPre_0]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [retryNoopPost]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_0_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_0_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_0_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_3]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_4]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_5]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_6]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_1_7]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryNoopKeep_2_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_0]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_1]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_2]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_3]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_4]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_5]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_6]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPre_7]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskPost]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_0_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_0_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_0_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_3]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_4]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_5]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_6]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryAskKeep_1_7]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedPre_0]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [retryParkedPost]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_0_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_0_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_0_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_3]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_4]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_5]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_6]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_1_7]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedKeep_2_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmPre_0]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmPost]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_0_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_0_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_0_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_3]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_4]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_5]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_6]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_1_7]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [retryParkedArmKeep_2_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopPre_0]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [lrNoopPost]
  tclear hInit hInv
  tintro n
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_0_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_0_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_0_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_1]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_2]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_3]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_4]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_5]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_6]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_1_7]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_2_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrNoopKeep_3_0]
  tclear hInit hInv
  tintro n x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskPre1_0]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre1_1]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre1_2]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPost1]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep1_0_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep1_0_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep1_0_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_0]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_1]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_2]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_3]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_4]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_5]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_6]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPre2_7]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskPost2]
  tclear hInit hInv
  tintro n q j
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_0_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_0_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_0_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_0]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_1]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_2]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_3]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_4]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_5]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_6]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [lrAskKeep2_1_7]
  tclear hInit hInv
  tintro n q j x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDuePre_0]
  tclear hInit hInv
  tintro n q
  tmonotone
  fv_step

prove_temporal_by [promiseDuePost]
  tclear hInit hInv
  tintro n q
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_0_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_0_1]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_0_2]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_1]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_2]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_3]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_4]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_5]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_6]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_1_7]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_2_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_3_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_4_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_5_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_6_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [promiseDueKeep_7_0]
  tclear hInit hInv
  tintro n q x y z
  tmonotone
  fv_step

prove_temporal_by [workEnabled]
  tclear hInit hNext hInv
  tmonotone
  veil_solve_temporal

prove_temporal_by [quiet]
  texit
  intro e i h hprem
  obtain ⟨hfin, hnr, hfp, henv⟩ := hprem
  obtain ⟨xs, hxs⟩ := hfin
  -- every triple, and the ranking's levels on them
  let os : List ord := [ord_EnumClass.o1, ord_EnumClass.o2, ord_EnumClass.o3, ord_EnumClass.o4]
  have hos : ∀ o, o ∈ os := by
    intro o; rcases ord_EnumClass.complete o with h | h | h | h <;> simp [os, h]
  let xs3 : List (node × node × ord) :=
    xs.flatMap (fun a => xs.flatMap (fun b => os.map (fun c => (a, b, c))))
  have hxs3 : ∀ x, x ∈ xs3 := by
    intro x; rcases x with ⟨a, b, c⟩; simp [xs3, hxs, hos]
  let δ : Nat → node × node × ord → σ → Prop := fun l x s => match l with
    | 0 => nGot x.1 th s ∧ nStop x.1 th s ∧ nAP x.1 x.2.1 th s
    | 1 => nGot x.1 th s ∧ nStop x.1 th s ∧ off x.1 x.2.1 th s ∧ nParked x.1 x.2.1 th s ∧ nTied x.1 x.2.1 th s ∧ nTiedE x.1 x.2.1 th s ∧ nProm x.1 x.2.1 th s ∧ nAQ x.1 x.2.1 x.2.2 th s
    | 2 => lv2 x.1 x.2.1 x.2.2 th s
    | 3 => lv3 x.1 x.2.1 x.2.2 th s
    | 4 => lv4 x.1 x.2.1 x.2.2 th s
    | 5 => lv5 x.1 x.2.1 x.2.2 th s
    | 6 => lv6 x.1 x.2.1 x.2.2 th s
    | 7 => lv7 x.1 x.2.1 x.2.2 th s
    | 8 => lv8 x.1 x.2.1 x.2.2 th s
    | 9 => lv9 x.1 x.2.1 x.2.2 th s
    | 10 => lv10 x.1 x.2.1 x.2.2 th s
    | _ => False
  -- the machinery's actions by family and by the node that takes the step, its first argument
  -- (without the refused asks), and the environment's
  let fam : Nat → node → σ → σ → Prop := fun k m s s' => match k with
    | 0 => ∃ q, ∃ j, NoStallEquivAdv.writeAsk.ext.tr ρ σ node kind ord χ m q j th s s'
    | 1 => ∃ n, ∃ j, ∃ ag, ∃ fu, NoStallEquivAdv.recvAsk.ext.tr ρ σ node kind ord χ m n j ag fu th s s'
    | 2 => ∃ n, ∃ j, NoStallEquivAdv.owedToQueue.ext.tr ρ σ node kind ord χ m n j th s s'
    | 3 => ∃ n, ∃ j, NoStallEquivAdv.writeAns.ext.tr ρ σ node kind ord χ m n j th s s'
    | 4 => ∃ q, ∃ j, NoStallEquivAdv.recvAns.ext.tr ρ σ node kind ord χ m q j th s s'
    | 5 => NoStallEquivAdv.windowElapse.ext.tr ρ σ node kind ord χ m th s s'
    | 6 => NoStallEquivAdv.retryNoop.ext.tr ρ σ node kind ord χ m th s s'
    | 7 => ∃ q, ∃ j, NoStallEquivAdv.retryAsk.ext.tr ρ σ node kind ord χ m q j false th s s'
    | 8 => NoStallEquivAdv.retryParked.ext.tr ρ σ node kind ord χ m th s s'
    | 9 => NoStallEquivAdv.retryParkedArm.ext.tr ρ σ node kind ord χ m th s s'
    | 10 => NoStallEquivAdv.lrNoop.ext.tr ρ σ node kind ord χ m th s s'
    | 11 => ∃ q, ∃ j, NoStallEquivAdv.lrAsk.ext.tr ρ σ node kind ord χ m q j false th s s'
    | _ => ∃ q, NoStallEquivAdv.promiseDue.ext.tr ρ σ node kind ord χ m q th s s'
  let own : σ → σ → Prop := fun s s' => ∃ k, ∃ m, fam k m s s'
  let envf : Nat → σ → σ → Prop := fun k s s' => match k with
    | 0 => ∃ n, ∃ q, NoStallEquivAdv.offerEarly.ext.tr ρ σ node kind ord χ n q th s s'
    | 1 => ∃ n, ∃ q, ∃ j, ∃ fu, NoStallEquivAdv.offerAsk.ext.tr ρ σ node kind ord χ n q j fu th s s'
    | 2 => ∃ n, ∃ q, NoStallEquivAdv.offerRecord.ext.tr ρ σ node kind ord χ n q th s s'
    | 3 => ∃ n, ∃ q, NoStallEquivAdv.offerParkedArm.ext.tr ρ σ node kind ord χ n q th s s'
    | 4 => ∃ n, ∃ q, NoStallEquivAdv.offerParked.ext.tr ρ σ node kind ord χ n q th s s'
    | 5 => ∃ n, ∃ q, NoStallEquivAdv.offerParkedUnparked.ext.tr ρ σ node kind ord χ n q th s s'
    | 6 => ∃ n, ∃ q, NoStallEquivAdv.offerParkedAsked.ext.tr ρ σ node kind ord χ n q th s s'
    | 7 => ∃ n, ∃ q, NoStallEquivAdv.offerParkedAskedNew.ext.tr ρ σ node kind ord χ n q th s s'
    | 8 => ∃ n, ∃ q, NoStallEquivAdv.offerParkedNoLR.ext.tr ρ σ node kind ord χ n q th s s'
    | 9 => ∃ n, ∃ q, NoStallEquivAdv.offerHeldBack.ext.tr ρ σ node kind ord χ n q th s s'
    | 10 => ∃ n, NoStallEquivAdv.installOther.ext.tr ρ σ node kind ord χ n th s s'
    | 11 => ∃ n, NoStallEquivAdv.installTakenIn.ext.tr ρ σ node kind ord χ n th s s'
    | 12 => ∃ n, NoStallEquivAdv.installStopped.ext.tr ρ σ node kind ord χ n th s s'
    | 13 => ∃ n, NoStallEquivAdv.installArm.ext.tr ρ σ node kind ord χ n th s s'
    | 14 => ∃ n, NoStallEquivAdv.install.ext.tr ρ σ node kind ord χ n th s s'
    | 15 => ∃ n, NoStallEquivAdv.arriveOther.ext.tr ρ σ node kind ord χ n th s s'
    | 16 => ∃ n, ∃ q, NoStallEquivAdv.pushEarly.ext.tr ρ σ node kind ord χ n q th s s'
    | 17 => ∃ n, ∃ a, NoStallEquivAdv.advTie.ext.tr ρ σ node kind ord χ n a th s s'
    | 18 => ∃ n, ∃ a, NoStallEquivAdv.advTieElse.ext.tr ρ σ node kind ord χ n a th s s'
    | 19 => ∃ n, ∃ a, NoStallEquivAdv.releaseElse.ext.tr ρ σ node kind ord χ n a th s s'
    | 20 => ∃ n, ∃ a, ∃ still, NoStallEquivAdv.dropTie.ext.tr ρ σ node kind ord χ n a still th s s'
    | 21 => ∃ n, ∃ a, NoStallEquivAdv.advExpire.ext.tr ρ σ node kind ord χ n a th s s'
    | 22 => ∃ a, ∃ q, ∃ j, NoStallEquivAdv.advAsk.ext.tr ρ σ node kind ord χ a q j th s s'
    | 23 => ∃ n, NoStallEquivAdv.stopPull.ext.tr ρ σ node kind ord χ n th s s'
    | 24 => ∃ q, ∃ n, NoStallEquivAdv.learnClaim.ext.tr ρ σ node kind ord χ q n th s s'
    | 25 => ∃ n, ∃ q, NoStallEquivAdv.parkOther.ext.tr ρ σ node kind ord χ n q th s s'
    | 26 => ∃ n, ∃ q, NoStallEquivAdv.close.ext.tr ρ σ node kind ord χ n q th s s'
    | 27 => ∃ n, ∃ q, ∃ j, NoStallEquivAdv.retryAsk.ext.tr ρ σ node kind ord χ n q j true th s s'
    | _ => ∃ n, ∃ q, ∃ j, NoStallEquivAdv.lrAsk.ext.tr ρ σ node kind ord χ n q j true th s s'
  -- a step is sorted by its effect: one with an own action's effect is own, whatever action took it;
  -- an environment step that changes nothing is a stutter
  let env : σ → σ → Prop := fun s s' => (∃ k, envf k s s') ∧ ¬ own s s' ∧ s' ≠ s
  -- the fair families: an action's instances taken by one honest node
  refine FvQuiet.quiet_exec e i own env (fun s s' => s' = s)
    (fun p : {p : Fin 13 × node // hon p.2 th (e i)} => fam p.1.1.val p.1.2) _
    (fun s' s => LentilLib.ListLex.List.lexLt Nat.lt_wfRel
      (FvQuiet.counts xs3 δ 0 11 s') (FvQuiet.counts xs3 δ 0 11 s))
    (FvQuiet.counts_wf xs3 δ 0 11) ?hsplit ?hdec (fun s s' h => h)
    (fun p s s' h => ⟨p.1.1.val, p.1.2, h⟩) ?hwork ?hfair ?henv
  case hsplit =>
    intro k hk
    have hk' := h.2.1 (k - i)
    rw [show i + (k - i) = k by omega] at hk'
    obtain ⟨label, hl⟩ := hk'
    rcases Classical.em (e (k + 1) = e k) with hs | hs
    · exact Or.inr (Or.inr hs)
    rcases Classical.em (own (e k) (e (k + 1))) with ho | ho
    · exact Or.inl ho
    cases label with
    | writeAsk n q j => exact Or.inl ⟨0, n, q, j, hl⟩
    | recvAsk q n j ag fu => exact Or.inl ⟨1, q, n, j, ag, fu, hl⟩
    | owedToQueue q n j => exact Or.inl ⟨2, q, n, j, hl⟩
    | writeAns q n j => exact Or.inl ⟨3, q, n, j, hl⟩
    | recvAns n q j => exact Or.inl ⟨4, n, q, j, hl⟩
    | windowElapse n => exact Or.inl ⟨5, n, hl⟩
    | retryNoop n => exact Or.inl ⟨6, n, hl⟩
    | retryAsk n q j fu =>
      cases fu with
      | false => exact Or.inl ⟨7, n, q, j, hl⟩
      | true => exact Or.inr (Or.inl ⟨⟨27, n, q, j, hl⟩, ho, hs⟩)
    | retryParked n => exact Or.inl ⟨8, n, hl⟩
    | retryParkedArm n => exact Or.inl ⟨9, n, hl⟩
    | lrNoop n => exact Or.inl ⟨10, n, hl⟩
    | lrAsk n q j fu =>
      cases fu with
      | false => exact Or.inl ⟨11, n, q, j, hl⟩
      | true => exact Or.inr (Or.inl ⟨⟨28, n, q, j, hl⟩, ho, hs⟩)
    | promiseDue n q => exact Or.inl ⟨12, n, q, hl⟩
    | offerEarly n q => exact Or.inr (Or.inl ⟨⟨0, n, q, hl⟩, ho, hs⟩)
    | offerAsk n q j fu => exact Or.inr (Or.inl ⟨⟨1, n, q, j, fu, hl⟩, ho, hs⟩)
    | offerRecord n q => exact Or.inr (Or.inl ⟨⟨2, n, q, hl⟩, ho, hs⟩)
    | offerParkedArm n q => exact Or.inr (Or.inl ⟨⟨3, n, q, hl⟩, ho, hs⟩)
    | offerParked n q => exact Or.inr (Or.inl ⟨⟨4, n, q, hl⟩, ho, hs⟩)
    | offerParkedUnparked n q => exact Or.inr (Or.inl ⟨⟨5, n, q, hl⟩, ho, hs⟩)
    | offerParkedAsked n q => exact Or.inr (Or.inl ⟨⟨6, n, q, hl⟩, ho, hs⟩)
    | offerParkedAskedNew n q => exact Or.inr (Or.inl ⟨⟨7, n, q, hl⟩, ho, hs⟩)
    | offerParkedNoLR n q => exact Or.inr (Or.inl ⟨⟨8, n, q, hl⟩, ho, hs⟩)
    | offerHeldBack n q => exact Or.inr (Or.inl ⟨⟨9, n, q, hl⟩, ho, hs⟩)
    | installOther n => exact Or.inr (Or.inl ⟨⟨10, n, hl⟩, ho, hs⟩)
    | installTakenIn n => exact Or.inr (Or.inl ⟨⟨11, n, hl⟩, ho, hs⟩)
    | installStopped n => exact Or.inr (Or.inl ⟨⟨12, n, hl⟩, ho, hs⟩)
    | installArm n => exact Or.inr (Or.inl ⟨⟨13, n, hl⟩, ho, hs⟩)
    | install n => exact Or.inr (Or.inl ⟨⟨14, n, hl⟩, ho, hs⟩)
    | arriveOther n => exact Or.inr (Or.inl ⟨⟨15, n, hl⟩, ho, hs⟩)
    | pushEarly n q => exact Or.inr (Or.inl ⟨⟨16, n, q, hl⟩, ho, hs⟩)
    | advTie n a => exact Or.inr (Or.inl ⟨⟨17, n, a, hl⟩, ho, hs⟩)
    | advTieElse n a => exact Or.inr (Or.inl ⟨⟨18, n, a, hl⟩, ho, hs⟩)
    | releaseElse n a => exact Or.inr (Or.inl ⟨⟨19, n, a, hl⟩, ho, hs⟩)
    | dropTie n a still => exact Or.inr (Or.inl ⟨⟨20, n, a, still, hl⟩, ho, hs⟩)
    | advExpire n a => exact Or.inr (Or.inl ⟨⟨21, n, a, hl⟩, ho, hs⟩)
    | advAsk a q j => exact Or.inr (Or.inl ⟨⟨22, a, q, j, hl⟩, ho, hs⟩)
    | stopPull n => exact Or.inr (Or.inl ⟨⟨23, n, hl⟩, ho, hs⟩)
    | learnClaim q n => exact Or.inr (Or.inl ⟨⟨24, q, n, hl⟩, ho, hs⟩)
    | parkOther n q => exact Or.inr (Or.inl ⟨⟨25, n, q, hl⟩, ho, hs⟩)
    | close n q => exact Or.inr (Or.inl ⟨⟨26, n, q, hl⟩, ho, hs⟩)
    | stutter => exact absurd hl.symm hs
  case hdec =>
    intro k hk hown
    obtain ⟨k', rfl⟩ : ∃ k', k = i + k' := ⟨k - i, by omega⟩
    obtain ⟨c, hc⟩ := hown
    rcases c with _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | c
    · -- writeAsk
      obtain ⟨n, q, j, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 5 _ _ (by omega) (by omega) ?_
        ⟨(n, q, j), writeAskPre_0._proof th hass e i h n q j k' hs,
          fun hx => writeAskPost._proof th hass e i h n q j k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (writeAskKeep_0_0._proof th hass e i h n q j x y z k' hs a0 a1 a2) (And.intro (writeAskKeep_0_1._proof th hass e i h n q j x y z k' hs a0 a1 a2) (writeAskKeep_0_2._proof th hass e i h n q j x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (writeAskKeep_1_0._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAskKeep_1_1._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAskKeep_1_2._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAskKeep_1_3._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAskKeep_1_4._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAskKeep_1_5._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAskKeep_1_6._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (writeAskKeep_1_7._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact writeAskKeep_2_0._proof th hass e i h n q j x y z k' hs hx
      · exact writeAskKeep_3_0._proof th hass e i h n q j x y z k' hs hx
      · exact writeAskKeep_4_0._proof th hass e i h n q j x y z k' hs hx
      · exact writeAskKeep_5_0._proof th hass e i h n q j x y z k' hs hx
      · omega
    · -- recvAsk
      obtain ⟨q, n, j, ag, fu, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 6 _ _ (by omega) (by omega) ?_
        ⟨(n, q, j), recvAskPre_0._proof th hass e i h q n j ag fu k' hs,
          fun hx => recvAskPost._proof th hass e i h q n j ag fu k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (recvAskKeep_0_0._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2) (And.intro (recvAskKeep_0_1._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2) (recvAskKeep_0_2._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (recvAskKeep_1_0._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAskKeep_1_1._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAskKeep_1_2._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAskKeep_1_3._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAskKeep_1_4._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAskKeep_1_5._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAskKeep_1_6._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (recvAskKeep_1_7._proof th hass e i h q n j ag fu x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact recvAskKeep_2_0._proof th hass e i h q n j ag fu x y z k' hs hx
      · exact recvAskKeep_3_0._proof th hass e i h q n j ag fu x y z k' hs hx
      · exact recvAskKeep_4_0._proof th hass e i h q n j ag fu x y z k' hs hx
      · exact recvAskKeep_5_0._proof th hass e i h q n j ag fu x y z k' hs hx
      · exact recvAskKeep_6_0._proof th hass e i h q n j ag fu x y z k' hs hx
      · omega
    · -- owedToQueue
      obtain ⟨q, n, j, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 8 _ _ (by omega) (by omega) ?_
        ⟨(n, q, j), owedToQueuePre_0._proof th hass e i h q n j k' hs,
          fun hx => owedToQueuePost._proof th hass e i h q n j k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (owedToQueueKeep_0_0._proof th hass e i h q n j x y z k' hs a0 a1 a2) (And.intro (owedToQueueKeep_0_1._proof th hass e i h q n j x y z k' hs a0 a1 a2) (owedToQueueKeep_0_2._proof th hass e i h q n j x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (owedToQueueKeep_1_0._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (owedToQueueKeep_1_1._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (owedToQueueKeep_1_2._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (owedToQueueKeep_1_3._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (owedToQueueKeep_1_4._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (owedToQueueKeep_1_5._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (owedToQueueKeep_1_6._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (owedToQueueKeep_1_7._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact owedToQueueKeep_2_0._proof th hass e i h q n j x y z k' hs hx
      · exact owedToQueueKeep_3_0._proof th hass e i h q n j x y z k' hs hx
      · exact owedToQueueKeep_4_0._proof th hass e i h q n j x y z k' hs hx
      · exact owedToQueueKeep_5_0._proof th hass e i h q n j x y z k' hs hx
      · exact owedToQueueKeep_6_0._proof th hass e i h q n j x y z k' hs hx
      · exact owedToQueueKeep_7_0._proof th hass e i h q n j x y z k' hs hx
      · exact owedToQueueKeep_8_0._proof th hass e i h q n j x y z k' hs hx
      · omega
    · -- writeAns
      obtain ⟨q, n, j, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 9 _ _ (by omega) (by omega) ?_
        ⟨(n, q, j), writeAnsPre_0._proof th hass e i h q n j k' hs,
          fun hx => writeAnsPost._proof th hass e i h q n j k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (writeAnsKeep_0_0._proof th hass e i h q n j x y z k' hs a0 a1 a2) (And.intro (writeAnsKeep_0_1._proof th hass e i h q n j x y z k' hs a0 a1 a2) (writeAnsKeep_0_2._proof th hass e i h q n j x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (writeAnsKeep_1_0._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAnsKeep_1_1._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAnsKeep_1_2._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAnsKeep_1_3._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAnsKeep_1_4._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAnsKeep_1_5._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (writeAnsKeep_1_6._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (writeAnsKeep_1_7._proof th hass e i h q n j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact writeAnsKeep_2_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_3_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_4_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_5_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_6_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_7_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_8_0._proof th hass e i h q n j x y z k' hs hx
      · exact writeAnsKeep_9_0._proof th hass e i h q n j x y z k' hs hx
      · omega
    · -- recvAns
      obtain ⟨n, q, j, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 10 _ _ (by omega) (by omega) ?_
        ⟨(n, q, j), recvAnsPre_0._proof th hass e i h n q j k' hs,
          fun hx => recvAnsPost._proof th hass e i h n q j k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (recvAnsKeep_0_0._proof th hass e i h n q j x y z k' hs a0 a1 a2) (And.intro (recvAnsKeep_0_1._proof th hass e i h n q j x y z k' hs a0 a1 a2) (recvAnsKeep_0_2._proof th hass e i h n q j x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (recvAnsKeep_1_0._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAnsKeep_1_1._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAnsKeep_1_2._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAnsKeep_1_3._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAnsKeep_1_4._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAnsKeep_1_5._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (recvAnsKeep_1_6._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (recvAnsKeep_1_7._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact recvAnsKeep_2_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_3_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_4_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_5_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_6_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_7_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_8_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_9_0._proof th hass e i h n q j x y z k' hs hx
      · exact recvAnsKeep_10_0._proof th hass e i h n q j x y z k' hs hx
      · omega
    · -- windowElapse
      obtain ⟨n, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 4 _ _ (by omega) (by omega) ?_
        ⟨(n, n, ord_EnumClass.o1), windowElapsePre_0._proof th hass e i h n k' hs,
          fun hx => windowElapsePost._proof th hass e i h n k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (windowElapseKeep_0_0._proof th hass e i h n x y z k' hs a0 a1 a2) (And.intro (windowElapseKeep_0_1._proof th hass e i h n x y z k' hs a0 a1 a2) (windowElapseKeep_0_2._proof th hass e i h n x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (windowElapseKeep_1_0._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (windowElapseKeep_1_1._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (windowElapseKeep_1_2._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (windowElapseKeep_1_3._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (windowElapseKeep_1_4._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (windowElapseKeep_1_5._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (windowElapseKeep_1_6._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (windowElapseKeep_1_7._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact windowElapseKeep_2_0._proof th hass e i h n x y z k' hs hx
      · exact windowElapseKeep_3_0._proof th hass e i h n x y z k' hs hx
      · exact windowElapseKeep_4_0._proof th hass e i h n x y z k' hs hx
      · omega
    · -- retryNoop
      obtain ⟨n, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 2 _ _ (by omega) (by omega) ?_
        ⟨(n, n, ord_EnumClass.o1), retryNoopPre_0._proof th hass e i h n k' hs,
          fun hx => retryNoopPost._proof th hass e i h n k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (retryNoopKeep_0_0._proof th hass e i h n x y z k' hs a0 a1 a2) (And.intro (retryNoopKeep_0_1._proof th hass e i h n x y z k' hs a0 a1 a2) (retryNoopKeep_0_2._proof th hass e i h n x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (retryNoopKeep_1_0._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryNoopKeep_1_1._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryNoopKeep_1_2._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryNoopKeep_1_3._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryNoopKeep_1_4._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryNoopKeep_1_5._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryNoopKeep_1_6._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (retryNoopKeep_1_7._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact retryNoopKeep_2_0._proof th hass e i h n x y z k' hs hx
      · omega
    · -- retryAsk
      obtain ⟨n, q, j, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 1 _ _ (by omega) (by omega) ?_
        ⟨(n, q, j), And.intro (retryAskPre_0._proof th hass e i h n q j k' hs hnr) (And.intro (retryAskPre_1._proof th hass e i h n q j k' hs hnr) (And.intro (retryAskPre_2._proof th hass e i h n q j k' hs hnr) (And.intro (retryAskPre_3._proof th hass e i h n q j k' hs hnr) (And.intro (retryAskPre_4._proof th hass e i h n q j k' hs hnr) (And.intro (retryAskPre_5._proof th hass e i h n q j k' hs hnr) (And.intro (retryAskPre_6._proof th hass e i h n q j k' hs hnr) (retryAskPre_7._proof th hass e i h n q j k' hs hnr))))))),
          fun hx => retryAskPost._proof th hass e i h n q j k' hs (by dsimp only [δ] at hx; exact hx.2.2.2.2.2.2.2)⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (retryAskKeep_0_0._proof th hass e i h n q j x y z k' hs a0 a1 a2) (And.intro (retryAskKeep_0_1._proof th hass e i h n q j x y z k' hs a0 a1 a2) (retryAskKeep_0_2._proof th hass e i h n q j x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (retryAskKeep_1_0._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryAskKeep_1_1._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryAskKeep_1_2._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryAskKeep_1_3._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryAskKeep_1_4._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryAskKeep_1_5._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryAskKeep_1_6._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (retryAskKeep_1_7._proof th hass e i h n q j x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · omega
    · -- retryParked
      obtain ⟨n, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 2 _ _ (by omega) (by omega) ?_
        ⟨(n, n, ord_EnumClass.o1), retryParkedPre_0._proof th hass e i h n k' hs,
          fun hx => retryParkedPost._proof th hass e i h n k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (retryParkedKeep_0_0._proof th hass e i h n x y z k' hs a0 a1 a2) (And.intro (retryParkedKeep_0_1._proof th hass e i h n x y z k' hs a0 a1 a2) (retryParkedKeep_0_2._proof th hass e i h n x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (retryParkedKeep_1_0._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedKeep_1_1._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedKeep_1_2._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedKeep_1_3._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedKeep_1_4._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedKeep_1_5._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedKeep_1_6._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (retryParkedKeep_1_7._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact retryParkedKeep_2_0._proof th hass e i h n x y z k' hs hx
      · omega
    · -- retryParkedArm
      obtain ⟨n, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 2 _ _ (by omega) (by omega) ?_
        ⟨(n, n, ord_EnumClass.o1), retryParkedArmPre_0._proof th hass e i h n k' hs,
          fun hx => retryParkedArmPost._proof th hass e i h n k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (retryParkedArmKeep_0_0._proof th hass e i h n x y z k' hs a0 a1 a2) (And.intro (retryParkedArmKeep_0_1._proof th hass e i h n x y z k' hs a0 a1 a2) (retryParkedArmKeep_0_2._proof th hass e i h n x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (retryParkedArmKeep_1_0._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedArmKeep_1_1._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedArmKeep_1_2._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedArmKeep_1_3._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedArmKeep_1_4._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedArmKeep_1_5._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (retryParkedArmKeep_1_6._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (retryParkedArmKeep_1_7._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact retryParkedArmKeep_2_0._proof th hass e i h n x y z k' hs hx
      · omega
    · -- lrNoop
      obtain ⟨n, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 3 _ _ (by omega) (by omega) ?_
        ⟨(n, n, ord_EnumClass.o1), lrNoopPre_0._proof th hass e i h n k' hs,
          fun hx => lrNoopPost._proof th hass e i h n k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (lrNoopKeep_0_0._proof th hass e i h n x y z k' hs a0 a1 a2) (And.intro (lrNoopKeep_0_1._proof th hass e i h n x y z k' hs a0 a1 a2) (lrNoopKeep_0_2._proof th hass e i h n x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (lrNoopKeep_1_0._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrNoopKeep_1_1._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrNoopKeep_1_2._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrNoopKeep_1_3._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrNoopKeep_1_4._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrNoopKeep_1_5._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrNoopKeep_1_6._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (lrNoopKeep_1_7._proof th hass e i h n x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact lrNoopKeep_2_0._proof th hass e i h n x y z k' hs hx
      · exact lrNoopKeep_3_0._proof th hass e i h n x y z k' hs hx
      · omega
    · -- lrAsk
      obtain ⟨n, q, j, hs⟩ := hc
      by_cases hcd : cParked n q th (e (i + k'))
      · -- level 0
        refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 0 _ _ (by omega) (by omega) ?_
          ⟨(n, q, j), And.intro (lrAskPre1_0._proof th hass e i h n q j k' hs hcd) (And.intro (lrAskPre1_1._proof th hass e i h n q j k' hs hcd) (lrAskPre1_2._proof th hass e i h n q j k' hs hcd)),
            fun hx => lrAskPost1._proof th hass e i h n q j k' hs hcd (by dsimp only [δ] at hx; exact hx.2.2)⟩
        intro l _ hl x hx
        rcases x with ⟨x, y, z⟩
        rcases l with _ | l
        · dsimp only [δ] at hx
          obtain ⟨a0, a1, a2⟩ := hx
          exact And.intro (lrAskKeep1_0_0._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2) (And.intro (lrAskKeep1_0_1._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2) (lrAskKeep1_0_2._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2))
        · omega
      · -- level 1
        refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 1 _ _ (by omega) (by omega) ?_
          ⟨(n, q, j), And.intro (lrAskPre2_0._proof th hass e i h n q j k' hs hcd hnr) (And.intro (lrAskPre2_1._proof th hass e i h n q j k' hs hcd hnr) (And.intro (lrAskPre2_2._proof th hass e i h n q j k' hs hcd hnr) (And.intro (lrAskPre2_3._proof th hass e i h n q j k' hs hcd hnr) (And.intro (lrAskPre2_4._proof th hass e i h n q j k' hs hcd hnr) (And.intro (lrAskPre2_5._proof th hass e i h n q j k' hs hcd hnr) (And.intro (lrAskPre2_6._proof th hass e i h n q j k' hs hcd hnr) (lrAskPre2_7._proof th hass e i h n q j k' hs hcd hnr))))))),
            fun hx => lrAskPost2._proof th hass e i h n q j k' hs hcd (by dsimp only [δ] at hx; exact hx.2.2.2.2.2.2.2)⟩
        intro l _ hl x hx
        rcases x with ⟨x, y, z⟩
        rcases l with _ | _ | l
        · dsimp only [δ] at hx
          obtain ⟨a0, a1, a2⟩ := hx
          exact And.intro (lrAskKeep2_0_0._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2) (And.intro (lrAskKeep2_0_1._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2) (lrAskKeep2_0_2._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2))
        · dsimp only [δ] at hx
          obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
          exact And.intro (lrAskKeep2_1_0._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrAskKeep2_1_1._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrAskKeep2_1_2._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrAskKeep2_1_3._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrAskKeep2_1_4._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrAskKeep2_1_5._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (lrAskKeep2_1_6._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7) (lrAskKeep2_1_7._proof th hass e i h n q j x y z k' hs hcd a0 a1 a2 a3 a4 a5 a6 a7)))))))
        · omega
    · -- promiseDue
      obtain ⟨n, q, hs⟩ := hc
      refine FvQuiet.counts_dec xs3 hxs3 δ 11 0 7 _ _ (by omega) (by omega) ?_
        ⟨(n, q, ord_EnumClass.o1), promiseDuePre_0._proof th hass e i h n q k' hs,
          fun hx => promiseDuePost._proof th hass e i h n q k' hs hx⟩
      intro l _ hl x hx
      rcases x with ⟨x, y, z⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | _ | l
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2⟩ := hx
        exact And.intro (promiseDueKeep_0_0._proof th hass e i h n q x y z k' hs a0 a1 a2) (And.intro (promiseDueKeep_0_1._proof th hass e i h n q x y z k' hs a0 a1 a2) (promiseDueKeep_0_2._proof th hass e i h n q x y z k' hs a0 a1 a2))
      · dsimp only [δ] at hx
        obtain ⟨a0, a1, a2, a3, a4, a5, a6, a7⟩ := hx
        exact And.intro (promiseDueKeep_1_0._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (promiseDueKeep_1_1._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (promiseDueKeep_1_2._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (promiseDueKeep_1_3._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (promiseDueKeep_1_4._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (promiseDueKeep_1_5._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (And.intro (promiseDueKeep_1_6._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7) (promiseDueKeep_1_7._proof th hass e i h n q x y z k' hs a0 a1 a2 a3 a4 a5 a6 a7)))))))
      · exact promiseDueKeep_2_0._proof th hass e i h n q x y z k' hs hx
      · exact promiseDueKeep_3_0._proof th hass e i h n q x y z k' hs hx
      · exact promiseDueKeep_4_0._proof th hass e i h n q x y z k' hs hx
      · exact promiseDueKeep_5_0._proof th hass e i h n q x y z k' hs hx
      · exact promiseDueKeep_6_0._proof th hass e i h n q x y z k' hs hx
      · exact promiseDueKeep_7_0._proof th hass e i h n q x y z k' hs hx
      · omega
  case hwork =>
    intro k hk hw
    obtain ⟨k', rfl⟩ : ∃ k', k = i + k' := ⟨k - i, by omega⟩
    rcases workEnabled._proof th hass e i h k' hw with
      ⟨n, q, j, hhn, s', hs'⟩ | ⟨q, n, j, hhn, s', hs'⟩ | ⟨q, n, j, hhn, s', hs'⟩ | ⟨q, n, j, hhn, s', hs'⟩ | ⟨n, q, j, hhn, s', hs'⟩ | ⟨n, hhn, s', hs'⟩ | ⟨n, hhn, s', hs'⟩ | ⟨n, q, j, hhn, s', hs'⟩ | ⟨n, hhn, s', hs'⟩ | ⟨n, hhn, s', hs'⟩ | ⟨n, hhn, s', hs'⟩ | ⟨n, q, j, hhn, s', hs'⟩ | ⟨n, q, hhn, s', hs'⟩
    · exact ⟨⟨(⟨0, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨q, j, hs'⟩⟩
    · exact ⟨⟨(⟨1, by omega⟩, q), hhn⟩, s', by dsimp only; exact ⟨n, j, false, false, hs'⟩⟩
    · exact ⟨⟨(⟨2, by omega⟩, q), hhn⟩, s', by dsimp only; exact ⟨n, j, hs'⟩⟩
    · exact ⟨⟨(⟨3, by omega⟩, q), hhn⟩, s', by dsimp only; exact ⟨n, j, hs'⟩⟩
    · exact ⟨⟨(⟨4, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨q, j, hs'⟩⟩
    · exact ⟨⟨(⟨5, by omega⟩, n), hhn⟩, s', by dsimp only; exact hs'⟩
    · exact ⟨⟨(⟨6, by omega⟩, n), hhn⟩, s', by dsimp only; exact hs'⟩
    · exact ⟨⟨(⟨7, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨q, j, hs'⟩⟩
    · exact ⟨⟨(⟨8, by omega⟩, n), hhn⟩, s', by dsimp only; exact hs'⟩
    · exact ⟨⟨(⟨9, by omega⟩, n), hhn⟩, s', by dsimp only; exact hs'⟩
    · exact ⟨⟨(⟨10, by omega⟩, n), hhn⟩, s', by dsimp only; exact hs'⟩
    · exact ⟨⟨(⟨11, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨q, j, hs'⟩⟩
    · exact ⟨⟨(⟨12, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨q, hs'⟩⟩
  case hfair =>
    intro p
    obtain ⟨⟨k, m⟩, hm⟩ := p
    obtain ⟨hw0, hw1, hw2, hw3, hw4, hw5, hw6, hw7, hw8, hw9, hw10, hw11, hw12⟩ := hfp m hm
    match k with
    | ⟨0, _⟩ => exact hw0
    | ⟨1, _⟩ => exact hw1
    | ⟨2, _⟩ => exact hw2
    | ⟨3, _⟩ => exact hw3
    | ⟨4, _⟩ => exact hw4
    | ⟨5, _⟩ => exact hw5
    | ⟨6, _⟩ => exact hw6
    | ⟨7, _⟩ => exact hw7
    | ⟨8, _⟩ => exact hw8
    | ⟨9, _⟩ => exact hw9
    | ⟨10, _⟩ => exact hw10
    | ⟨11, _⟩ => exact hw11
    | ⟨12, _⟩ => exact hw12
    | ⟨k + 13, hk⟩ => exact absurd hk (by omega)
  case henv =>
    obtain ⟨k0, hk0⟩ := henv
    show ∃ k0, ∀ k, ¬ env (e (i + k0 + k)) (e (i + k0 + k + 1))
    refine ⟨k0, fun k ⟨⟨c, hc⟩, hno, hne⟩ => ?_⟩
    rcases hk0 k with hst | ho0 | ho1 | ho2 | ho3 | ho4 | ho5 | ho6 | ho7 | ho8 | ho9 | ho10 | ho11 | ho12 | ⟨h0, h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12, h13, h14, h15, h16, h17, h18, h19, h20, h21, h22, h23, h24, h25, h26, h27, h28⟩
    · exact hne (Eq.symm hst)
    · obtain ⟨n, q, j, hh⟩ := ho0; exact hno ⟨0, n, q, j, hh⟩
    · obtain ⟨q, n, j, ag, fu, hh⟩ := ho1; exact hno ⟨1, q, n, j, ag, fu, hh⟩
    · obtain ⟨q, n, j, hh⟩ := ho2; exact hno ⟨2, q, n, j, hh⟩
    · obtain ⟨q, n, j, hh⟩ := ho3; exact hno ⟨3, q, n, j, hh⟩
    · obtain ⟨n, q, j, hh⟩ := ho4; exact hno ⟨4, n, q, j, hh⟩
    · obtain ⟨n, hh⟩ := ho5; exact hno ⟨5, n, hh⟩
    · obtain ⟨n, hh⟩ := ho6; exact hno ⟨6, n, hh⟩
    · obtain ⟨n, q, j, hh⟩ := ho7; exact hno ⟨7, n, q, j, hh⟩
    · obtain ⟨n, hh⟩ := ho8; exact hno ⟨8, n, hh⟩
    · obtain ⟨n, hh⟩ := ho9; exact hno ⟨9, n, hh⟩
    · obtain ⟨n, hh⟩ := ho10; exact hno ⟨10, n, hh⟩
    · obtain ⟨n, q, j, hh⟩ := ho11; exact hno ⟨11, n, q, j, hh⟩
    · obtain ⟨n, q, hh⟩ := ho12; exact hno ⟨12, n, q, hh⟩
    rcases c with _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | c
    · obtain ⟨n, q, hs⟩ := hc; exact h0 ⟨n, q, hs⟩
    · obtain ⟨n, q, j, fu, hs⟩ := hc; exact h1 ⟨n, q, j, fu, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h2 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h3 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h4 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h5 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h6 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h7 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h8 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h9 ⟨n, q, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h10 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h11 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h12 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h13 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h14 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h15 ⟨n, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h16 ⟨n, q, hs⟩
    · obtain ⟨n, a, hs⟩ := hc; exact h17 ⟨n, a, hs⟩
    · obtain ⟨n, a, hs⟩ := hc; exact h18 ⟨n, a, hs⟩
    · obtain ⟨n, a, hs⟩ := hc; exact h19 ⟨n, a, hs⟩
    · obtain ⟨n, a, still, hs⟩ := hc; exact h20 ⟨n, a, still, hs⟩
    · obtain ⟨n, a, hs⟩ := hc; exact h21 ⟨n, a, hs⟩
    · obtain ⟨a, q, j, hs⟩ := hc; exact h22 ⟨a, q, j, hs⟩
    · obtain ⟨n, hs⟩ := hc; exact h23 ⟨n, hs⟩
    · obtain ⟨q, n, hs⟩ := hc; exact h24 ⟨q, n, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h25 ⟨n, q, hs⟩
    · obtain ⟨n, q, hs⟩ := hc; exact h26 ⟨n, q, hs⟩
    · obtain ⟨n, q, j, hs⟩ := hc; exact h27 ⟨n, q, j, hs⟩
    · obtain ⟨n, q, j, hs⟩ := hc; exact h28 ⟨n, q, j, hs⟩


-- the audit, every failure a build error: the verification conditions, derived from the module
-- itself (the initializer and each action, against `doesNotThrow` and each safety and invariant
-- clause), are all theorems; no clause is trusted instead of checked; and every theorem in the
-- module rests on Lean's own axioms only
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
      let n := Name.mkStr `NoStallEquivAdv s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `NoStallEquivAdv && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in NoStallEquivAdv, resting on {rest.toList}"

end NoStallEquivAdv
