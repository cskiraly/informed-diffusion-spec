module

public import Veil

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"

/-! # No stall, the asking part (Q1's first piece), for any number of nodes

SEACAST, `protocol.md` v0.5 (§4.1, §4.4, §4.5, §6.1, §7.2), with v0.7's IHAVE limits (§4.4, §6.4)
and connections that close (§8.1):
**when the asking machinery has nothing left to do, a node that has the block holds every chunk an
honest peer offered it, or has stopped pulling the group.** The chunk is any one chunk of the group,
so the result holds for each.

What the machinery does with an offer is modelled as the spec writes it: one ask per chunk in flight
(its window ends at any time); the retry asks an unparked announcer, any one; a promise opens at the
write and falls due at any time while open, parking its peer for the group; when every announcer is
parked, each is asked once more (B′); the asker drops an ask for a chunk it holds or no longer pulls;
the first ask a node receives for a chunk it holds is answered, later ones may be dropped (the serve
limit, at its worst), and one from a peer that claimed the chunk is dropped; an answer is cancelled
if the asker claimed the chunk meanwhile; a queue may refuse any entry (the group's other traffic
can fill it): a refused ask is lost and its retry stays armed, a refused answer is owed (§4.1).

The rest of the protocol is the **environment**, events that may happen at any time and any number
of times: an honest node holding the chunk offers it (an IHAVE, handled as §4.4 does: over one of
gossipsub's IHAVE limits, the offer is recorded and what the node would ask waits for the next
heartbeat, which runs the retry for it, §6.4); the chunk
reaches a node otherwise (a push); a node stops pulling the group (its decode claim, at K of the
group's chunks); a node learns that a peer claims the chunk (a HAVE: true, and possibly never sent);
and a promise for another chunk of the group falls due, parking its peer for the group (the way F2
stalls); and a node's block installs. These are not in `work`, the machinery's own pending events:
what is proved is about the states in which the machinery is done, whatever the environment did
before and may do after.

The block (C′, §3, §4.2): nothing is asked before it is installed; an offer that arrives before it is
recorded, and the installation asks for what was offered meanwhile (the ledger: here the retry is
armed, and finds the offers). A node stops pulling, and takes a chunk in, only once it has its block.

A connection closes at any time (§8.1), also part of the environment: what is queued, owed or in
flight between the two nodes is lost both ways; their promises close (§6.1: the ask or its answer
went with the connection, and the retry, whose timer is per ask, stays armed); and the state kept
per connection goes: the offers (the ledger's too), B′'s counts, the serve count and the claims.
Parks stay, kept by peer id. The offers a new connection brings (F9's resync) are offers from
honest holders, as above. Resetting B′'s counts is a switch with a known answer: kept across the
close, an announcer whose last resort the close lost is never asked again.

Not modelled here: how offers come about (the transport: `NoStallTransport.lean`), lifetimes,
adversaries. -/

veil module NoStallAsk

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192

type node
-- the stages of an ask from a to b (queued at a, in flight) and of an answer from a to b (queued at
-- a, owed by a, in flight)
enum kind = { askQ, askF, ansQ, ansOwed, ansF }

immutable individual lastResort : Bool     -- B′ (§6.1): every announcer parked, each asked once more
immutable individual owedAnswers : Bool    -- §4.1, §7.2: an answer a full queue refuses is owed
immutable individual askLedger : Bool      -- C′ (§3, §4.2): what was offered before the block is asked
-- §4.4, §6.4 (v0.7): an ask an IHAVE limit holds back is retried at the next heartbeat
immutable individual heldBackRetry : Bool
-- §6.1, §8.1: B′'s count for an announcer goes with its connection, as `tried` does
immutable individual countsReset : Bool

relation installed (n : node) : Bool               -- n's block is installed
relation got (n : node) : Bool                     -- n holds the chunk
relation stop (n : node) : Bool                    -- n stopped pulling the group (its decode claim)
relation peerHas (q : node) (n : node) : Bool      -- q knows that n claims the chunk
relation offered (n : node) (q : node) : Bool      -- q offered the chunk to n
relation ledger (n : node) (q : node) : Bool       -- q offered it before n's block (§4.2)
relation inWindow (n : node) : Bool                -- an ask of n's is in its window
relation retryArmed (n : node) : Bool
relation lrArmed (n : node) : Bool                 -- B′'s timer
relation parked (n : node) (q : node) : Bool       -- n parked q, for the group
relation askedParked (n : node) (q : node) : Bool  -- B′'s count
relation promise (n : node) (q : node) : Bool      -- n's ask to q, written, open
relation served (q : node) (n : node) : Bool       -- q answered an ask of n's
relation stage (k : kind) (a : node) (b : node) : Bool
-- history only, for the non-vacuity queries below: no action reads them
relation everLastResort (n : node) : Bool
relation everEarly (n : node) : Bool
relation everHeldBack (n : node) : Bool
relation closedAsk (n : node) : Bool               -- a close lost an ask of n's

#gen_state

theory ghost relation premises := lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset

-- the machinery's actions' enabling conditions, each its action's only `require`
ghost relation en_writeAsk (n : node) (q : node) := stage askQ n q
ghost relation en_recvAsk (q : node) (n : node) := stage askF n q
ghost relation en_owedToQueue (q : node) (n : node) := stage ansOwed q n
ghost relation en_writeAns (q : node) (n : node) := stage ansQ q n
ghost relation en_recvAns (n : node) (q : node) := stage ansF q n
ghost relation en_elapse (n : node) := inWindow n
ghost relation en_retryNoop (n : node) := retryArmed n ∧ ¬ inWindow n ∧ (got n ∨ stop n)
ghost relation en_retryAsk (n : node) (q : node) :=
  retryArmed n ∧ ¬ inWindow n ∧ ¬ got n ∧ ¬ stop n ∧ offered n q ∧ ¬ parked n q
ghost relation en_retryParked (n : node) :=
  retryArmed n ∧ ¬ inWindow n ∧ ¬ got n ∧ ¬ stop n ∧ ∀ Q, offered n Q → parked n Q
ghost relation en_lrNoop (n : node) :=
  lrArmed n ∧ (got n ∨ stop n ∨ inWindow n ∨ ∀ Q, offered n Q → parked n Q ∧ askedParked n Q)
ghost relation en_lrAsk (n : node) (q : node) :=
  lrArmed n ∧ ¬ got n ∧ ¬ stop n ∧ ¬ inWindow n ∧ offered n q ∧
    (¬ parked n q ∨ ((∀ Q, offered n Q → parked n Q) ∧ ¬ askedParked n q))
ghost relation en_promiseDue (n : node) (q : node) := promise n q

-- the machinery has something to do
ghost relation work :=
  (∃ N Q, en_writeAsk N Q) ∨ (∃ Q N, en_recvAsk Q N) ∨ (∃ Q N, en_owedToQueue Q N) ∨
  (∃ Q N, en_writeAns Q N) ∨ (∃ N Q, en_recvAns N Q) ∨ (∃ N, en_elapse N) ∨
  (∃ N, en_retryNoop N) ∨ (∃ N Q, en_retryAsk N Q) ∨ (∃ N, en_retryParked N) ∨
  (∃ N, en_lrNoop N) ∨ (∃ N Q, en_lrAsk N Q) ∨ (∃ N Q, en_promiseDue N Q)

after_init {
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
  served Q N := false
  stage K A B := false
  everLastResort N := false
  everEarly N := false
  everHeldBack N := false
  closedAsk N := false
}

/-! ## The environment -/

-- §4.4, §6.1: an honest node holding the chunk offers it to n. Ignored if n claims the chunk (no
-- state changes, so not modelled); recorded otherwise; before n's block, recorded only (§3); with
-- it, by the case: asked for if the offerer is not parked and no ask is in its window; from a parked
-- offerer, the last resort armed when every announcer is parked and one has not been asked once more
ghost relation lrDue (n : node) (q : node) :=
  lastResort ∧ ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q) ∧
    ((∃ Q, offered n Q ∧ ¬ askedParked n Q) ∨ ¬ askedParked n q)

action offerEarly (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ ¬ installed n
  ledger n q := true
  everEarly n := true
}

action offerAsk (n q : node) (full : Bool) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ ¬ parked n q ∧ ¬ inWindow n
  inWindow n := true
  retryArmed n := true
  if full = false then
    stage askQ n q := true
  offered n q := true
}

action offerInWindow (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ ¬ parked n q ∧ inWindow n
  offered n q := true
}

action offerParkedArm (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧ lrDue n q
  lrArmed n := true
  offered n q := true
}

action offerParked (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧ ¬ lrDue n q
  offered n q := true
}

-- §4.4, §6.4 (v0.7): an IHAVE over one of gossipsub's IHAVE limits: the offer is recorded and the
-- chunk held back, whatever its window, to the next heartbeat, which runs the retry for it (here the
-- retry is armed, and finds the offers; with every announcer parked it arms the last resort). The
-- loop holds back an unparked offerer's chunk (a parked one's goes to the last resort at once:
-- `offerParked…`); §4.4's bitmap reading holds back any offerer's, parked or not
action offerHeldBack (n q : node) {
  require n ≠ q ∧ got q ∧ ¬ got n ∧ ¬ stop n ∧ installed n
  if heldBackRetry then
    retryArmed n := true
  offered n q := true
  everHeldBack n := true
}

-- §3, §4.2: n's block installs. Its handler first takes in the deferred copies, then asks for what
-- was offered meanwhile and is neither held nor stopped (the ledger), by the case: a copy of this
-- chunk was waiting, and the chunk is held (a decode claim the copies brought can follow, as
-- `stopPull`); the copies brought the group to K, and the decode claim stopped the pull; or neither,
-- and the offers join and the retry is armed, which finds them
action installTakenIn (n : node) {
  require ¬ installed n
  installed n := true
  got n := true
  ledger n Q := false
}

action installStopped (n : node) {
  require ¬ installed n
  installed n := true
  stop n := true
  offered n Q := offered n Q || ledger n Q
  ledger n Q := false
}

action install (n : node) {
  require ¬ installed n
  installed n := true
  if askLedger ∧ (∃ Q, ledger n Q) then
    retryArmed n := true
  offered n Q := offered n Q || ledger n Q
  ledger n Q := false
}

-- §4.2: the chunk reaches n otherwise (a push, or a deferred copy once the block installs): its
-- promises close and its offers go
action arriveOther (n : node) {
  require installed n
  got n := true
  promise n Q := false
  offered n Q := false
  askedParked n Q := false
  inWindow n := false
}

-- §4.6: n's decode claim (at K of the group's chunks, which takes the block): no further asks, the
-- group's promises close
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
-- lost, both ways; their promises close (§6.1); the state kept per connection goes (offers, the
-- ledger's too, B′'s counts, the serve count, claims); parks, windows and timers stay
action close (n q : node) {
  require n ≠ q
  if stage askQ n q ∨ stage askF n q then
    closedAsk n := true
  stage K n q := false
  stage K q n := false
  promise n q := false
  promise q n := false
  offered n q := false
  offered q n := false
  ledger n q := false
  ledger q n := false
  if countsReset then
    askedParked n q := false
    askedParked q n := false
  served n q := false
  served q n := false
  peerHas n q := false
  peerHas q n := false
}

/-! ## The machinery -/

-- §7.2: the asker drops an ask for a chunk it holds or no longer pulls; the promise opens (E)
action writeAsk (n q : node) {
  require en_writeAsk n q
  stage askQ n q := false
  if ¬ got n ∧ ¬ stop n then
    stage askF n q := true
    promise n q := true
}

-- §4.5, §4.1: q receives n's ask: dropped if n claimed the chunk; the first ask is answered, later
-- ones may be dropped (the serve limit); a refused answer is owed
action recvAsk (q n : node) (again full : Bool) {
  require en_recvAsk q n
  stage askF n q := false
  if ¬ peerHas q n ∧ got q ∧ (¬ served q n ∨ again) then
    served q n := true
    if full then
      if owedAnswers then
        stage ansOwed q n := true
    else
      stage ansQ q n := true
}

-- §7.2: an owed answer is queued once there is room
action owedToQueue (q n : node) {
  require en_owedToQueue q n
  stage ansOwed q n := false
  stage ansQ q n := true
}

-- §7.2: an answer is cancelled if n claimed the chunk meanwhile, else sent
action writeAns (q n : node) {
  require en_writeAns q n
  stage ansQ q n := false
  if ¬ peerHas q n then
    stage ansF q n := true
}

-- §4.2, §6.3: the answer arrives: the chunk is held, its promises close, its offers go
action recvAns (n q : node) {
  require en_recvAns n q
  stage ansF q n := false
  got n := true
  promise n Q := false
  offered n Q := false
  askedParked n Q := false
  inWindow n := false
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

-- §6.1: the retry asks an unparked announcer (any one); its own retry is armed again
action retryAsk (n q : node) (full : Bool) {
  require en_retryAsk n q
  inWindow n := true
  if full = false then
    stage askQ n q := true
}

-- §6.1: every announcer is parked: the last resort, armed if one has not been asked once more
action retryParked (n : node) {
  require en_retryParked n
  retryArmed n := false
  if lastResort ∧ ¬ lrArmed n ∧ (∃ Q, offered n Q ∧ ¬ askedParked n Q) then
    lrArmed n := true
}

-- §6.1 (B′): the last resort's timer: nothing to do
action lrNoop (n : node) {
  require en_lrNoop n
  lrArmed n := false
}

-- §6.1 (B′): an announcer unparked meanwhile, or else a parked one not asked once more; counted once
-- the queue has taken the ask
action lrAsk (n q : node) (full : Bool) {
  require en_lrAsk n q
  lrArmed n := false
  inWindow n := true
  retryArmed n := true
  if full = false then
    stage askQ n q := true
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

-- when the machinery is done, every offer to a node that has its block has been resolved: the chunk
-- is held, or the pull stopped
safety [offers_resolve] premises → ¬ work → installed N → offered N Q → got N ∨ stop N

-- offers and asks go to nodes that hold the chunk; claims are true
invariant [offer_holder] (offered N Q → got Q) ∧ (ledger N Q → got Q)
invariant [ledger_before] ledger N Q → ¬ installed N
invariant [ask_holder] (stage askQ N Q → got Q) ∧ (stage askF N Q → got Q)
invariant [claims_true] peerHas Q N → got N ∨ stop N
invariant [window_retry] inWindow N → retryArmed N
invariant [askedparked_offered] premises → askedParked N Q → offered N Q
-- the machinery runs only with the block: offers (earlier ones are in the ledger), timers, asks,
-- and so the answers that come back
invariant [after_block] (offered N Q → installed N) ∧ (retryArmed N → installed N) ∧
  (lrArmed N → installed N) ∧
  (stage askQ N Q → installed N) ∧ (stage askF N Q → installed N) ∧ (served Q N → installed N) ∧
  (stage ansQ Q N → installed N) ∧ (stage ansOwed Q N → installed N) ∧ (stage ansF Q N → installed N)
-- an offer keeps the asking going: the block still to come, a timer armed, an ask on its way or
-- answered, or every announcer parked and asked once more
invariant [offer_active] premises → offered N M →
  got N ∨ stop N ∨ ¬ installed N ∨ retryArmed N ∨ lrArmed N ∨
    (∃ Q, stage askQ N Q ∨ stage askF N Q ∨ served Q N) ∨
    (∀ Q, offered N Q → parked N Q ∧ askedParked N Q)
-- an offer from an unparked announcer keeps the retry armed, and one from a parked announcer not yet
-- asked once more keeps the retry or the last resort armed: so a close that loses the ask in flight
-- leaves the asking going
invariant [unparked_retry] premises → installed N → offered N Q → ¬ parked N Q →
  got N ∨ stop N ∨ retryArmed N
invariant [parked_timer] premises → installed N → offered N Q → parked N Q → ¬ askedParked N Q →
  got N ∨ stop N ∨ retryArmed N ∨ lrArmed N
-- an answer, once given, arrives (or was cancelled by a claim)
invariant [served_answer] premises → served Q N →
  got N ∨ stop N ∨ stage ansQ Q N ∨ stage ansOwed Q N ∨ stage ansF Q N ∨ peerHas Q N
-- an ask once more reaches the announcer, and is answered
invariant [asked_parked] premises → askedParked N Q →
  got N ∨ stop N ∨ stage askQ N Q ∨ stage askF N Q ∨ served Q N ∨ peerHas Q N

-- a quiet state with an offer from an honest holder, to a node that has its block, never resolved
ghost relation stalled := ¬ work ∧ ∃ N Q, installed N ∧ offered N Q ∧ ¬ got N ∧ ¬ stop N

#gen_spec

/-! ## Non-vacuity: with every rule on, runs reach a quiet state -/

-- an offer, asked for and answered
sat trace [offer_answered] {
  install
  arriveOther
  install
  offerAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ Q N, got N ∧ served Q N)
}

-- the offerer parked by another chunk of the group: the last resort asks it once more
sat trace [last_resort_resolves] {
  install
  arriveOther
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

-- an offer that arrives before the block, asked for once it installs
sat trace [ledger_asks] {
  install
  arriveOther
  offerEarly
  install
  retryAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ everEarly N)
}

-- an offer over an IHAVE limit, asked for by the heartbeat's retry
sat trace [held_back_asked] {
  install
  arriveOther
  install
  offerHeldBack
  retryAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ everHeldBack N)
}

-- an offer over an IHAVE limit from an offerer parked by another chunk (§4.4's bitmap reading): the
-- heartbeat's retry finds every announcer parked, and the last resort asks it once more
sat trace [held_back_parked] {
  install
  arriveOther
  install
  parkOther
  offerHeldBack
  retryParked
  lrAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ everHeldBack N ∧ everLastResort N)
}

-- an ask lost with its connection: the announcer offers again on the new one (F9's resync), and the
-- retry asks it, armed as it was, once the window has passed
sat trace [close_reasked] {
  install
  arriveOther
  install
  offerAsk
  writeAsk
  close
  offerInWindow
  windowElapse
  retryAsk
  writeAsk
  recvAsk
  writeAns
  recvAns
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N, got N ∧ closedAsk N)
}

/-! ## Known answers: with any one rule off, an offer is never resolved -/

-- F2: an offerer parked by another chunk is never asked
sat trace [ka_no_last_resort] {
  install
  arriveOther
  install
  parkOther
  offerParked
  assert (¬ lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset ∧ stalled)
}

-- an answer a full queue refuses is lost, twice: the ask's and the last resort's
sat trace [ka_answer_lost] {
  install
  arriveOther
  install
  offerAsk
  writeAsk
  recvAsk
  promiseDue
  windowElapse
  retryParked
  lrAsk
  writeAsk
  recvAsk
  promiseDue
  windowElapse
  retryParked
  assert (lastResort ∧ ¬ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset ∧ stalled)
}

-- an offer recorded before the block is never asked for
sat trace [ka_no_ledger] {
  install
  arriveOther
  offerEarly
  install
  assert (lastResort ∧ owedAnswers ∧ ¬ askLedger ∧ heldBackRetry ∧ countsReset ∧ stalled)
}

-- F11's recovery without its retry: an offer over an IHAVE limit is recorded and never asked for
sat trace [ka_held_back_lost] {
  install
  arriveOther
  install
  offerHeldBack
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ ¬ heldBackRetry ∧ countsReset ∧ stalled)
}

-- B′'s count kept across a close: the last resort's ask is lost with the connection, the announcer
-- offers again on the new one, and it is never asked: its count says it was asked once more
sat trace [ka_counts_kept] {
  install
  arriveOther
  install
  parkOther
  offerParkedArm
  lrAsk
  writeAsk
  close
  offerParked
  windowElapse
  retryParked
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ ¬ countsReset ∧ stalled)
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
      let n := Name.mkStr `NoStallAsk s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `NoStallAsk && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in NoStallAsk, resting on {rest.toList}"

end NoStallAsk
