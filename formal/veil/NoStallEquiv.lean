module

public import Veil

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"

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
them, B′'s ask once more is spent on them, and so are a provider's three answers per chunk and
connection (`GOSSIP_RETRANSMISSION`); after the switch every announcer is parked and has been asked
once more, or has no answer left, and the node stalls. The two rules, each a switch with a known
answer:
- `ROOT_TIED` (§4.2's ties): a copy that waits ties its sender to the root it names, for its index;
  the sender's promise closes, since it answered, and it is not asked for the index again until that
  root installs. The installation releases the ties: each sender's park lifts, B′'s count for it
  clears, and it is an offer again, asked for (§4.2's `on_block_installed`).
- `NO_REASK_OPEN` (§6.1): no announcer is asked for a chunk while an earlier ask of it to that announcer is
  outstanding, queued or promised; a retry or a last resort that finds every candidate outstanding
  waits, and the outstanding ask is pending work.

Asks are numbered per peer (`ord`): the j-th ask from n to q, each with its own stages, so that two
asks in flight to one peer are two, not one, and what a provider answers is counted. The provider
answers the first three, and may drop any later one (its count kept for the connection's life, the
worst case of the stock lifetime).

The rest is `NoStallAsk.lean`'s machinery: one ask per chunk in its window, the retry, promises that
fall due at any time, B′, the writer's ask filter (which also drops a queued ask to a tied peer), the
claim rule's drop, answers cancelled or owed, the ledger (C′), held-back offers (v0.7); and its
environment, with the other block's installation and pushes that wait for the builder's block.

Connections close at any time, as in `NoStallAsk.lean`: what is between the two nodes is lost both
ways, their promises close, and the state kept per connection goes, the asks' numbering (with the
provider's serve count) and the ties among it (§8.1); B′'s counts with it are a switch with a known
answer.

Assumed: every honest copy names the builder's block, rebuilt ones included. v0.7's §4.6 let a
rebuilt chunk name either installed block whose bid commits the group, so a node that installed
both blocks could rebuild a chunk naming the other one; at a node with only the builder's block
that copy waits for good, and its sender, which counted it, sends nothing more for the index.
v0.8's §4.6 has a rebuilt chunk name the block the chunks it was rebuilt from name, where they all
name one: the source publishes under one block, and forwarding and the rule keep it, so among
honest nodes every copy names it. That argument is by inspection, not in this model.

Not modelled here: how offers come about (the transport), lifetimes, adversaries (so every tie is
honest: a copy naming the builder's root, whose bid commits the group), and more than two blocks
for the slot. -/

veil module NoStallEquiv

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192

type node
-- the stages of an ask from a to b (queued at a, in flight) and of an answer from a to b (queued at
-- a, owed by a, in flight)
enum kind = { askQ, askF, ansQ, ansOwed, ansF }
-- an ask's number among n's asks to q for the chunk: the first, the second, the third, a later one
enum ord = { o1, o2, o3, o4 }

immutable individual lastResort : Bool     -- B′ (§6.1): every announcer parked, each asked once more
immutable individual owedAnswers : Bool    -- §4.1, §7.2: an answer a full queue refuses is owed
immutable individual askLedger : Bool      -- C′ (§3, §4.2): what was offered before the block is asked
-- §4.4, §6.4 (v0.7): an ask an IHAVE limit holds back is retried at the next heartbeat
immutable individual heldBackRetry : Bool
immutable individual rootTied : Bool       -- F6: ROOT_TIED (§4.2's ties, v0.8)
immutable individual noReask : Bool        -- F6: NO_REASK_OPEN (§6.1, v0.8)
-- §6.1, §8.1: B′'s count for an announcer goes with its connection, as `tried` does
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
relation lrArmed (n : node) : Bool                 -- B′'s timer
relation parked (n : node) (q : node) : Bool       -- n parked q, for the group
relation askedParked (n : node) (q : node) : Bool  -- B′'s count
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
-- claim stopped the pull; or neither: each tied sender's park lifts, B′'s count for it clears, it is
-- an offer again, the ledger's offers join, and the retry is armed, which finds them
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
-- ledger's too), B′'s counts, the asks' numbering with the serve count, ties (§8.1) and claims;
-- parks, windows and timers stay
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
-- more
action retryParked (n : node) {
  require en_retryParked n
  retryArmed n := false
  if lastResort ∧ ¬ lrArmed n ∧ (∃ Q, offered n Q ∧ ¬ tied n Q ∧ ¬ askedParked n Q) then
    lrArmed n := true
}

-- §6.1 (B′): the last resort's timer: nothing to do
action lrNoop (n : node) {
  require en_lrNoop n
  lrArmed n := false
}

-- §6.1 (B′): an announcer unparked meanwhile, or else a parked one not asked once more, neither tied
-- nor outstanding; counted once the queue has taken the ask
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
-- F6: before the builder's block, a provider is asked at most twice, the second time by B′; so its
-- third answer is left for after the switch
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
  assert (premises ∧ ¬ work ∧ ∃ N Q, got N ∧ made N Q o1)
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
  assert (premises ∧ ∃ N Q, gate N ∧ ¬ installed N ∧ tied N Q ∧ ¬ promise N Q ∧ made N Q o1)
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
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ everSwitched N ∧ everTied N)
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
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ everLastResort N)
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
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ everEarly N)
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
  assert (premises ∧ ∃ N, got N ∧ closedAsk N)
}

/-! ## Known answers: with one rule off, the machinery fails -/

-- F6's first form, without ROOT_TIED: on the other block, the provider (parked by another chunk) is
-- asked once more by B′; the answer waits and its promise falls due; at the switch every announcer
-- is parked and has been asked once more, with nothing on its way, so no ask can follow: the retry
-- the installation arms finds them all parked and arms no last resort (the run to that quiet state
-- exceeds the simplifier's steps)
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
    ∃ N Q, ¬ installed N ∧ made N Q o3)
}

-- F2: an offerer parked by another chunk is never asked
sat trace [ka_no_last_resort] {
  installTakenIn
  install
  parkOther
  offerParked
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

-- B′'s count kept across a close: the last resort's ask is lost with the connection, the announcer
-- offers again on the new one, and it is never asked: its count says it was asked once more
sat trace [ka_counts_kept] {
  installTakenIn
  install
  parkOther
  offerParkedArm
  lrAsk
  close
  offerParked
  windowElapse
  retryParked
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ rootTied ∧ noReask ∧
    ¬ countsReset ∧ stalled)
}

/-! ## The proof: the clauses above are an inductive invariant -/

#check_invariants

-- each proof as a theorem in the environment, which Lean's kernel checks as it adds it
#gen_theorems

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
      let n := Name.mkStr `NoStallEquiv s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `NoStallEquiv && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in NoStallEquiv, resting on {rest.toList}"

end NoStallEquiv
