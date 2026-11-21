module

public import Veil
public import QuietRanking

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"
-- the longer traces need more than the solver's 60 s on a loaded machine
set_option veil.smt.timeout 300

/-- Q3's per-step facts: Veil's reduction of a one-step temporal goal to
first-order form, the enum axioms' distinctness as inequalities, then Lean's `grind`, which the
kernel checks. `veil_solve_temporal` ends in the SMT solver instead, whose translation or proof
reconstruction fails on most of these goals in Veil v4.35.0. -/
macro "fv_step" : tactic => `(tactic| (
  unveil_temporal
  (try veil_cases_type* Or)
  all_goals (
    (try veil_destruct only [And, Exists])
    veil_fol !
    (try simp only [distinctN_pairwise_neq, List.nodup_cons, List.mem_cons, List.not_mem_nil, or_false,
      not_or, List.nodup_nil, and_true] at *)
    grind)))

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

veil module NoStallEquiv

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192
-- Veil v4.35.0's solver needs more than `veil module`'s 500,000 heartbeats on some conditions
set_option maxHeartbeats 2000000

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
  lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧ countsReset

-- an ask of the chunk from n to q is outstanding: queued, or its promise open (NO_REASK_OPEN)
ghost relation outstanding (n : node) (q : node) := (∃ J, stage askQ n q J) ∨ promise n q
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
  retryArmed n ∧ ¬ inWindow n ∧ ¬ got n ∧ ¬ stop n ∧ offered n q ∧ ¬ parked n q ∧ ¬ tied n q ∧
    ¬ (noReask ∧ outstanding n q)
-- every announcer that is not tied is parked: the last resort
ghost relation en_retryParked (n : node) :=
  retryArmed n ∧ ¬ inWindow n ∧ ¬ got n ∧ ¬ stop n ∧ ∀ Q, offered n Q → parked n Q ∨ tied n Q
ghost relation en_lrNoop (n : node) :=
  lrArmed n ∧ (got n ∨ stop n ∨ inWindow n ∨
    ∀ Q, offered n Q → tied n Q ∨ (parked n Q ∧ askedParked n Q))
ghost relation en_lrAsk (n : node) (q : node) :=
  lrArmed n ∧ ¬ got n ∧ ¬ stop n ∧ ¬ inWindow n ∧ offered n q ∧ ¬ tied n q ∧
    ¬ (noReask ∧ outstanding n q) ∧
    (¬ parked n q ∨ ((∀ Q, offered n Q → parked n Q ∨ tied n Q) ∧ ¬ askedParked n q))
ghost relation en_promiseDue (n : node) (q : node) := promise n q

-- the machinery has something to do
ghost relation work :=
  (∃ N Q J, en_writeAsk N Q J) ∨ (∃ Q N J, en_recvAsk Q N J) ∨ (∃ Q N J, en_owedToQueue Q N J) ∨
  (∃ Q N J, en_writeAns Q N J) ∨ (∃ N Q J, en_recvAns N Q J) ∨ (∃ N, en_elapse N) ∨
  (∃ N, en_retryNoop N) ∨ (∃ N Q, en_retryAsk N Q) ∨ (∃ N, en_retryParked N) ∨
  (∃ N, en_lrNoop N) ∨ (∃ N Q, en_lrAsk N Q) ∨ (∃ N Q, en_promiseDue N Q)

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
  lastResort ∧ ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q ∨ tied n Q) ∧
    ((∃ Q, offered n Q ∧ ¬ tied n Q ∧ ¬ askedParked n Q) ∨ ¬ askedParked n q)

action offerEarly (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ ¬ gate n
  ledger n q := true
  everEarly n := true
}

action offerAsk (n q : node) (j : ord) (full : Bool) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ ¬ parked n q ∧ ¬ inWindow n ∧ ¬ tied n q ∧
    ¬ (noReask ∧ outstanding n q) ∧ nextAsk n q j
  inWindow n := true
  retryArmed n := true
  if full = false then
    made n q j := true
    stage askQ n q j := true
  offered n q := true
}

action offerRecord (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧
    (tied n q ∨ (¬ parked n q ∧ (inWindow n ∨ (noReask ∧ outstanding n q))))
  offered n q := true
}

action offerParkedArm (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧ ¬ tied n q ∧ lrDue n q
  lrArmed n := true
  offered n q := true
}

action offerParked (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ gate n ∧ parked n q ∧ ¬ tied n q ∧ ¬ lrDue n q
  offered n q := true
}

-- §4.4, §6.4 (v0.7): an IHAVE over one of gossipsub's IHAVE limits: the offer is recorded and the
-- chunk held back to the next heartbeat, which runs the retry for it (here the retry is armed)
action offerHeldBack (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ gate n
  if heldBackRetry then
    retryArmed n := true
  offered n q := true
  everHeldBack n := true
}

-- §3, §4.2: the proposer's other block installs at n first. Its bid commits the group, so the gate
-- opens and what was offered meanwhile is asked for (the ledger); copies, naming the builder's block,
-- still wait
action installOther (n : node) {
  require ¬ gate n
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

-- §4.6: n's decode claim (at K of the group's chunks, which takes the builder's block): no further
-- asks, the group's promises close
action stopPull (n : node) {
  require installed n
  stop n := true
  promise n Q := false
}

-- §4.3: q learns from n's HAVE that n claims the chunk
action learnClaim (q n : node) {
  require got n ∨ stop n
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
  peerHas n q := false
  peerHas q n := false
}

/-! ## The machinery -/

-- §7.2: the asker drops an ask for a chunk it holds or no longer pulls, and one to a tied peer
-- (ROOT_TIED); else the promise opens (E)
action writeAsk (n q : node) (j : ord) {
  require en_writeAsk n q j
  stage askQ n q j := false
  if ¬ got n ∧ ¬ stop n ∧ ¬ tied n q then
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
  lastResort ∧ ¬ lrArmed n ∧ (∃ Q, offered n Q ∧ ¬ tied n Q ∧ ¬ askedParked n Q)

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
safety [offers_resolve] premises → ¬ work → installed N → offered N Q → got N ∨ stop N

-- the blocks: holding and stopping take the builder's block, which opens the gate; ties wait for it
invariant [blocks] (installed N → gate N) ∧ (got N → installed N) ∧ (stop N → installed N) ∧
  (tied N Q → ¬ installed N)
-- offers, ties and asks go to nodes that hold the chunk; claims are true
invariant [offer_holder] (offered N Q → got Q) ∧ (ledger N Q → got Q) ∧ (tied N Q → got Q)
invariant [ledger_before] ledger N Q → ¬ gate N
invariant [ask_holder] (stage askQ N Q J → got Q) ∧ (stage askF N Q J → got Q) ∧
  (stage ansQ Q N J → got Q) ∧ (stage ansOwed Q N J → got Q) ∧ (stage ansF Q N J → got Q)
invariant [claims_true] peerHas Q N → got N ∨ stop N
invariant [window_retry] inWindow N → retryArmed N
invariant [askedparked_offered] premises → askedParked N Q → offered N Q
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
-- an ask outstanding goes to an announcer
invariant [asked_offered] premises → (stage askQ N Q J → offered N Q ∨ got N) ∧
  (promise N Q → offered N Q ∨ got N)
-- F6: before the builder's block, a provider is asked at most twice, the second time by the last
-- resort; so its third answer is left for after the switch
invariant [first_ask] premises → ¬ installed N → made N Q o1 →
  (∃ J, stage askQ N Q J) ∨ promise N Q ∨ parked N Q ∨ tied N Q ∨ got N ∨ stop N
invariant [second_ask] premises → ¬ installed N → made N Q o2 → askedParked N Q ∨ tied N Q
invariant [two_before] premises → ¬ installed N → ¬ made N Q o3
-- the third ask, made only with the builder's block, is answered
invariant [third_answered] premises → made N Q o3 →
  pipeline N Q o3 ∨ got N ∨ stop N ∨ peerHas Q N
-- an offer from an unparked announcer that is not tied keeps the retry armed, and one from a parked
-- announcer not tied and not yet asked once more keeps the retry or the last resort armed
invariant [unparked_retry] premises → offered N Q → ¬ parked N Q → ¬ tied N Q →
  got N ∨ stop N ∨ retryArmed N
invariant [parked_timer] premises → offered N Q → parked N Q → ¬ tied N Q → ¬ askedParked N Q →
  got N ∨ stop N ∨ retryArmed N ∨ lrArmed N
-- an offer to a node with the builder's block keeps the asking going: a timer armed, an ask or answer
-- on its way, or every announcer parked and asked once more
invariant [offer_active] premises → installed N → offered N M →
  got N ∨ stop N ∨ retryArmed N ∨ lrArmed N ∨ (∃ Q J, pipeline N Q J) ∨
    (∀ Q, offered N Q → parked N Q ∧ askedParked N Q)
-- an ask once more reaches the announcer and is answered, or waits as a tie
invariant [asked_parked] premises → askedParked N Q →
  got N ∨ stop N ∨ tied N Q ∨ peerHas Q N ∨ (∃ J, pipeline N Q J)

-- a quiet state with an offer from an honest holder, to a node with the builder's block, unresolved
ghost relation stalled := ¬ work ∧ ∃ N Q, installed N ∧ offered N Q ∧ ¬ got N ∧ ¬ stop N

-- Q3: a ranking that every step of the machinery that is not a refused
-- ask lowers. Eleven levels, highest first, each a relation on (asker n, announcer q, ask number
-- z), a level that names fewer holding of every value of the others: n's announcers not yet asked
-- once more, while n neither holds the chunk nor has stopped; n's fresh asks (an offer from an
-- unparked, untied announcer with no promise open and no ask of number z queued, while n neither
-- holds the chunk nor has stopped); armed retries; armed last resorts; ask windows; queued asks;
-- asks in flight; open promises; owed answers; queued answers; answers in flight. Levels 0 and 1
-- are conjunctions of the literals below, stated literal by literal: in Veil v4.35.0 a one-step
-- fact with a conjunction in its conclusion fails (the reduction unfolds the step in its first
-- conjunct only).
ghost relation nGot (n : node) := ¬ got n
ghost relation nStop (n : node) := ¬ stop n
ghost relation nParked (n : node) (q : node) := ¬ parked n q
ghost relation nAP (n : node) (q : node) := ¬ askedParked n q
ghost relation nTied (n : node) (q : node) := ¬ tied n q
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

-- Q3: with finitely many nodes, NO_REASK_OPEN, weakly fair machinery actions (the retry's and the
-- last resort's asks that a queue takes) and an environment that eventually stops, a queue's refusal
-- of an ask included, the asking eventually has nothing to do, for good. In a proof `⟨a⟩` says that
-- a step has the effect of some execution of `a`, whatever action took it: a step that changes
-- nothing is a `stopPull n` once n has stopped, and a step of the machinery can have an environment
-- action's effect. So "the environment stops" is stated as: from some point on, every step that
-- changes the state has a machinery action's effect or no environment action's
temporal (only := verify) [quiet]
  ⌞ ∃ l : List node, ∀ n : node, n ∈ l ⌟ ∧ ⌜ noReask ⌝ ∧ 𝒲ℱ writeAsk ∧ 𝒲ℱ recvAsk ∧ 𝒲ℱ owedToQueue ∧
  𝒲ℱ writeAns ∧ 𝒲ℱ recvAns ∧ 𝒲ℱ windowElapse ∧ 𝒲ℱ retryNoop ∧ 𝒲ℱ (retryAsk · · · false) ∧
  𝒲ℱ retryParked ∧ 𝒲ℱ retryParkedArm ∧ 𝒲ℱ lrNoop ∧ 𝒲ℱ (lrAsk · · · false) ∧ 𝒲ℱ promiseDue ∧
  ◇ □ (⟨stutter⟩ ∨ ⟨writeAsk⟩ ∨ ⟨recvAsk⟩ ∨ ⟨owedToQueue⟩ ∨ ⟨writeAns⟩ ∨ ⟨recvAns⟩ ∨
    ⟨windowElapse⟩ ∨ ⟨retryNoop⟩ ∨ ⟨retryAsk · · · false⟩ ∨ ⟨retryParked⟩ ∨ ⟨retryParkedArm⟩ ∨
    ⟨lrNoop⟩ ∨ ⟨lrAsk · · · false⟩ ∨ ⟨promiseDue⟩ ∨ (¬ ⟨offerEarly⟩ ∧ ¬ ⟨offerAsk⟩ ∧
    ¬ ⟨offerRecord⟩ ∧ ¬ ⟨offerParkedArm⟩ ∧ ¬ ⟨offerParked⟩ ∧ ¬ ⟨offerHeldBack⟩ ∧ ¬ ⟨installOther⟩ ∧
    ¬ ⟨installTakenIn⟩ ∧ ¬ ⟨installStopped⟩ ∧ ¬ ⟨installArm⟩ ∧ ¬ ⟨install⟩ ∧ ¬ ⟨arriveOther⟩ ∧
    ¬ ⟨pushEarly⟩ ∧ ¬ ⟨stopPull⟩ ∧ ¬ ⟨learnClaim⟩ ∧ ¬ ⟨parkOther⟩ ∧ ¬ ⟨close⟩ ∧
    ¬ ⟨retryAsk · · · true⟩ ∧ ¬ ⟨lrAsk · · · true⟩)) →
  ◇ □ ⌜ ¬ work ⌝
temporal (only := verify) [workEnabled]
  □ (⌜ work ⌝ → (∃ n, ∃ q, ∃ j, Enabled (writeAsk n q j)) ∨
    (∃ q, ∃ n, ∃ j, Enabled (recvAsk q n j false false)) ∨
    (∃ q, ∃ n, ∃ j, Enabled (owedToQueue q n j)) ∨ (∃ q, ∃ n, ∃ j, Enabled (writeAns q n j)) ∨
    (∃ n, ∃ q, ∃ j, Enabled (recvAns n q j)) ∨ (∃ n, Enabled (windowElapse n)) ∨
    (∃ n, Enabled (retryNoop n)) ∨ (∃ n, ∃ q, ∃ j, Enabled (retryAsk n q j false)) ∨
    (∃ n, Enabled (retryParked n)) ∨ (∃ n, Enabled (retryParkedArm n)) ∨ (∃ n, Enabled (lrNoop n)) ∨
    (∃ n, ∃ q, ∃ j, Enabled (lrAsk n q j false)) ∨ (∃ n, ∃ q, Enabled (promiseDue n q)))
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
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [writeAskKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [writeAskKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [writeAskKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [writeAskKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [writeAskKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [writeAskKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAsk n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [recvAskKeep_1_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [recvAskKeep_1_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [recvAskKeep_1_3]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [recvAskKeep_1_4]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [recvAskKeep_1_5]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [recvAskKeep_1_6]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ ag : Bool, ∀ fu : Bool, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAsk q n j ag fu⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [owedToQueueKeep_1_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [owedToQueueKeep_1_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_3]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_4]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_5]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [owedToQueueKeep_1_6]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨owedToQueue q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [writeAnsKeep_1_1]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [writeAnsKeep_1_2]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [writeAnsKeep_1_3]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [writeAnsKeep_1_4]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [writeAnsKeep_1_5]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [writeAnsKeep_1_6]
  ∀ q : node, ∀ n : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨writeAns q n j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [recvAnsKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [recvAnsKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [recvAnsKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [recvAnsKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [recvAnsKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [recvAnsKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨recvAns n q j⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [windowElapseKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [windowElapseKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [windowElapseKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [windowElapseKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [windowElapseKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [windowElapseKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨windowElapse n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nGot x ⌝)
temporal (only := verify) [retryNoopKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nStop x ⌝)
temporal (only := verify) [retryNoopKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ off x y ⌝)
temporal (only := verify) [retryNoopKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nParked x y ⌝)
temporal (only := verify) [retryNoopKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nTied x y ⌝)
temporal (only := verify) [retryNoopKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nProm x y ⌝)
temporal (only := verify) [retryNoopKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nAQ x y z ⌝)
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
  ∀ n : node, ∀ q : node, ∀ j : ord, □ (⟨retryAsk n q j false⟩ → ⌜ noReask ⌝ → ⌜ nProm n q ⌝)
temporal (only := verify) [retryAskPre_6]
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
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryAskKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryAskKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [retryAskKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [retryAskKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [retryAskKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [retryAskKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryAsk n q j false⟩ →
    ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ →
    ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nGot x ⌝)
temporal (only := verify) [retryParkedKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nStop x ⌝)
temporal (only := verify) [retryParkedKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ off x y ⌝)
temporal (only := verify) [retryParkedKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nParked x y ⌝)
temporal (only := verify) [retryParkedKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nTied x y ⌝)
temporal (only := verify) [retryParkedKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nProm x y ⌝)
temporal (only := verify) [retryParkedKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParked n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [retryParkedArmKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [retryParkedArmKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [retryParkedArmKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨retryParkedArm n⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nGot x ⌝)
temporal (only := verify) [lrNoopKeep_1_1]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nStop x ⌝)
temporal (only := verify) [lrNoopKeep_1_2]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ off x y ⌝)
temporal (only := verify) [lrNoopKeep_1_3]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nParked x y ⌝)
temporal (only := verify) [lrNoopKeep_1_4]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nTied x y ⌝)
temporal (only := verify) [lrNoopKeep_1_5]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nProm x y ⌝)
temporal (only := verify) [lrNoopKeep_1_6]
  ∀ n : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrNoop n⟩ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ →
    ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ →
    ⌜ nAQ x y z ⌝)
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
    ⌜ nProm n q ⌝)
temporal (only := verify) [lrAskPre2_6]
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
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [lrAskKeep2_1_1]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [lrAskKeep2_1_2]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [lrAskKeep2_1_3]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [lrAskKeep2_1_4]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [lrAskKeep2_1_5]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [lrAskKeep2_1_6]
  ∀ n : node, ∀ q : node, ∀ j : ord, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨lrAsk n q j false⟩ →
    ⌜ ¬ cParked n q ⌝ → ◯ ⌜ nGot x ⌝ → ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ →
    ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ → ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nGot x ⌝)
temporal (only := verify) [promiseDueKeep_1_1]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nStop x ⌝)
temporal (only := verify) [promiseDueKeep_1_2]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ off x y ⌝)
temporal (only := verify) [promiseDueKeep_1_3]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nParked x y ⌝)
temporal (only := verify) [promiseDueKeep_1_4]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nTied x y ⌝)
temporal (only := verify) [promiseDueKeep_1_5]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nProm x y ⌝)
temporal (only := verify) [promiseDueKeep_1_6]
  ∀ n : node, ∀ q : node, ∀ x : node, ∀ y : node, ∀ z : ord, □ (⟨promiseDue n q⟩ → ◯ ⌜ nGot x ⌝ →
    ◯ ⌜ nStop x ⌝ → ◯ ⌜ off x y ⌝ → ◯ ⌜ nParked x y ⌝ → ◯ ⌜ nTied x y ⌝ → ◯ ⌜ nProm x y ⌝ →
    ◯ ⌜ nAQ x y z ⌝ → ⌜ nAQ x y z ⌝)
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

end NoStallEquiv
