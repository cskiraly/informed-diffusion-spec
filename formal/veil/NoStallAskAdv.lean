module

public import Veil

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"
-- the longer traces need more than the solver's 60 s on a loaded machine
set_option veil.smt.timeout 300

/-! # No stall, the asking part, with malicious peers, for any number of nodes

`NoStallAsk.lean` with adversaries: SEACAST, `protocol.md` v0.5 (§4.1,
§4.4, §4.5, §6.1, §7.2), with v0.7's IHAVE limits (§4.4, §6.4) and connections that close (§8.1).
**When no honest node's asking machinery has anything left to do, an honest node that has the block
holds every chunk an honest peer offered it, or has stopped pulling the group, whatever the other
peers do.** The chunk is any one chunk of the group, so the result holds for each.

The adversaries (`adv`, any set of nodes) are part of the environment: they offer the chunk whether
they hold it or not, before the block or after, any number of times (an IHAVE, handled as an honest
one is, so they also fill an honest node's offers and its last resort); they claim the chunk
whether or not they hold it (a HAVE, which only stops honest nodes answering them); they ask honest
nodes for it at any time (an IWANT by full id or by index), which honest nodes answer within the
serve limit; they answer or not, and an answer from one that holds the chunk is the chunk arriving
(`recvAns`, or `arriveOther`), any other leaves the asker's promise open, to fall due; and they close
their connections at any time, which the environment's `close` already allows for every pair. Their
own pending events are not work: "nothing left to do" is about honest nodes only (asks queued or in
flight to an honest node, answers queued or owed or in flight to one, an honest node's windows,
retries, last resorts and promises), so an ask that waits at an adversary for good does not keep a
state from being quiet. What this does not show: that a run gets quiet (an adversary that offers,
is asked and closes, again and again, keeps the retry busy), nor anything about time.

The rules as v0.7 writes them (no ties, no rule against a second ask: those are v0.8's, in
`NoStallEquiv.lean`, which has no adversaries). They do not carry over by themselves: a rule that
withholds an ask can make a state quiet that was not. With one block, a tie binds only a copy that
waits for a root, which here is an adversary's own, and passes over that adversary only; an ask
withheld because one is outstanding leaves a queued entry or an open promise, honest work until it
is written or falls due. v0.8's asking with adversaries is `NoStallEquivAdv.lean`.

What the adversary's powers stand for (the correspondence, by inspection): a stock per-id
IDONTWANT, repeated IWANTs and malformed or repeated control in one RPC change only the sender's own
connection (what it is sent, its serve count, its penalties); an ask by full id resolves, as one by
index, to the holder's chunk of that group and index; the offer list's 16 announcers per id lose no
honest announcer, since every offer is also kept in the connection's `offered` bitmap (the last
resort's), and the deferred store's reservations, the ties and the admission of groups are per peer
(§8.2); an adversary's asks can take the node-wide send window, which the drain assumption covers,
and the answers it draws are queued to it (`advAsk`).

What the machinery does with an offer is modelled as the spec writes it: one ask per chunk in flight
(its window ends at any time); the retry asks an unparked announcer, any one; a promise opens at the
write and falls due at any time while open, parking its peer for the group; when every announcer is
parked, each is asked once more (the last resort); the asker drops an ask for a chunk it holds or no
longer pulls; the first ask a node receives for a chunk it holds is answered, later ones may be
dropped (the serve limit, at its worst), and one from a peer that claimed the chunk is dropped; an
answer is cancelled if the asker claimed the chunk meanwhile; a queue may refuse any entry (the
group's other traffic can fill it): a refused ask is lost and its retry stays armed, a refused
answer is owed (§4.1).

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
per connection goes: the offers (the ledger's too), the last-resort counts, the serve count and the
claims. Parks stay, kept by peer id. The offers a new connection brings (F9's resync) are offers
from honest holders, as above. Resetting the last-resort counts is a switch with a known answer:
kept across the close, an announcer whose last resort the close lost is never asked again.

Known answer for the adversaries: the last-resort count kept per chunk instead of per announcer
(§6.1's rationale names this case), the last resort is spent on an adversary that announced first,
and an honest announcer parked by another chunk is never asked again.

Not modelled here: how offers come about (the transport: `NoStallTransport.lean`), lifetimes. -/

veil module NoStallAskAdv

-- Veil v4.35.0's solver needs more than `veil module`'s 500,000 heartbeats on some conditions
set_option maxHeartbeats 2000000

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192

type node
-- the stages of an ask from a to b (queued at a, in flight) and of an answer from a to b (queued at
-- a, owed by a, in flight)
enum kind = { askQ, askF, ansQ, ansOwed, ansF }

immutable individual lastResort : Bool     -- §6.1: every announcer parked, each asked once more
immutable individual owedAnswers : Bool    -- §4.1, §7.2: an answer a full queue refuses is owed
immutable individual askLedger : Bool      -- C′ (§3, §4.2): what was offered before the block is asked
-- §4.4, §6.4 (v0.7): an ask an IHAVE limit holds back is retried at the next heartbeat
immutable individual heldBackRetry : Bool
-- §6.1, §8.1: the last-resort count for an announcer goes with its connection, as `tried` does
immutable individual countsReset : Bool
-- §6.1: the last-resort count is kept per announcer and chunk (off: per chunk, the known answer)
immutable individual countPerAnnouncer : Bool
-- the adversaries
immutable relation adv (n : node) : Bool

relation installed (n : node) : Bool               -- n's block is installed
relation got (n : node) : Bool                     -- n holds the chunk
relation stop (n : node) : Bool                    -- n stopped pulling the group (its decode claim)
relation peerHas (q : node) (n : node) : Bool      -- q knows that n claims the chunk
relation offered (n : node) (q : node) : Bool      -- q offered the chunk to n
relation ledger (n : node) (q : node) : Bool       -- q offered it before n's block (§4.2)
relation inWindow (n : node) : Bool                -- an ask of n's is in its window
relation retryArmed (n : node) : Bool
relation lrArmed (n : node) : Bool                 -- the last resort's timer
relation parked (n : node) (q : node) : Bool       -- n parked q, for the group
relation askedParked (n : node) (q : node) : Bool  -- the last-resort count
relation promise (n : node) (q : node) : Bool      -- n's ask to q, written, open
relation served (q : node) (n : node) : Bool       -- q answered an ask of n's
relation stage (k : kind) (a : node) (b : node) : Bool
-- history only, for the non-vacuity queries below: no action reads them
relation everLastResort (n : node) : Bool
relation everEarly (n : node) : Bool
relation everHeldBack (n : node) : Bool
relation closedAsk (n : node) : Bool               -- a close lost an ask of n's
relation everArmedBy (n : node) (q : node) : Bool  -- q's offer armed n's last resort
relation everLrAsked (n : node) (q : node) : Bool  -- n's last resort asked q once more

#gen_state

theory ghost relation premises :=
  lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset ∧ countPerAnnouncer

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

-- an honest node's machinery has something to do: the event is at an honest node (its queue, its
-- timers, a message it receives); what is pending at an adversary is not work
ghost relation work :=
  (∃ N Q, ¬ adv N ∧ en_writeAsk N Q) ∨ (∃ Q N, ¬ adv Q ∧ en_recvAsk Q N) ∨
  (∃ Q N, ¬ adv Q ∧ en_owedToQueue Q N) ∨ (∃ Q N, ¬ adv Q ∧ en_writeAns Q N) ∨
  (∃ N Q, ¬ adv N ∧ en_recvAns N Q) ∨ (∃ N, ¬ adv N ∧ en_elapse N) ∨
  (∃ N, ¬ adv N ∧ en_retryNoop N) ∨ (∃ N Q, ¬ adv N ∧ en_retryAsk N Q) ∨
  (∃ N, ¬ adv N ∧ en_retryParked N) ∨ (∃ N, ¬ adv N ∧ en_lrNoop N) ∨
  (∃ N Q, ¬ adv N ∧ en_lrAsk N Q) ∨ (∃ N Q, ¬ adv N ∧ en_promiseDue N Q)

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
  everArmedBy N Q := false
  everLrAsked N Q := false
}

/-! ## The environment -/

-- §4.4, §6.1: an honest node holding the chunk, or an adversary, offers it to an honest n (an
-- adversary's own asking is not modelled: nothing of an honest node depends on it). Ignored if n
-- claims the chunk (no state changes, so not modelled); recorded otherwise; before n's block,
-- recorded only (§3); with it, by the case: asked for if the offerer is not parked and no ask is in
-- its window; from a parked offerer, the last resort armed when every announcer is parked and one
-- has not been asked once more
ghost relation lrDue (n : node) (q : node) :=
  lastResort ∧ ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q) ∧
    ((∃ Q, offered n Q ∧ ¬ askedParked n Q) ∨ ¬ askedParked n q)

action offerEarly (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ ¬ installed n
  ledger n q := true
  everEarly n := true
}

action offerAsk (n q : node) (full : Bool) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ ¬ parked n q ∧
    ¬ inWindow n
  inWindow n := true
  retryArmed n := true
  if full = false then
    stage askQ n q := true
  offered n q := true
}

action offerInWindow (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ ¬ parked n q ∧
    inWindow n
  offered n q := true
}

action offerParkedArm (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧ lrDue n q
  lrArmed n := true
  offered n q := true
  everArmedBy n q := true
}

-- from a parked offerer while the last resort is not due (`lrDue`): one action per reason, so that
-- each one's conditions are rebuilt into a proof (together they are `¬ lrDue n q`): the last resort
-- is armed already; another announcer is not parked; every announcer is parked and asked once more,
-- this one too; or there is no last resort (`lastResort` off, the known answer)
action offerParked (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧
    lrArmed n
  offered n q := true
}

action offerParkedUnparked (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧
    ¬ lrArmed n ∧ (∃ Q, offered n Q ∧ ¬ parked n Q)
  offered n q := true
}

-- an announcer asked once more has offered already (`askedparked_offered`): its offer changes
-- nothing; it is new only where the last-resort count outlived a close (`countsReset` off, the
-- known answer)
action offerParkedAsked (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧
    ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q ∧ askedParked n Q) ∧ askedParked n q ∧
    offered n q
}

action offerParkedAskedNew (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧
    ¬ lrArmed n ∧ (∀ Q, offered n Q → parked n Q ∧ askedParked n Q) ∧ askedParked n q ∧
    ¬ offered n q
  offered n q := true
}

action offerParkedNoLR (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n ∧ parked n q ∧
    ¬ lastResort
  offered n q := true
}

-- §4.4, §6.4 (v0.7): an IHAVE over one of gossipsub's IHAVE limits: the offer is recorded and the
-- chunk held back, whatever its window, to the next heartbeat, which runs the retry for it (here the
-- retry is armed, and finds the offers; with every announcer parked it arms the last resort). The
-- loop holds back an unparked offerer's chunk (a parked one's goes to the last resort at once:
-- `offerParked…`); §4.4's bitmap reading holds back any offerer's, parked or not
action offerHeldBack (n q : node) {
  require n ≠ q ∧ ¬ adv n ∧ (got q ∨ adv q) ∧ ¬ got n ∧ ¬ stop n ∧ installed n
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

-- §4.3: q learns from n's HAVE that n claims the chunk: true of an honest node, anything of an
-- adversary
action learnClaim (q n : node) {
  require got n ∨ stop n ∨ adv n
  peerHas q n := true
}

-- an adversary asks q for the chunk (an IWANT, by full id or by index), any number of times
action advAsk (a q : node) {
  require adv a ∧ ¬ adv q ∧ a ≠ q ∧ installed a
  stage askF a q := true
}

-- §6.1: a promise for another chunk of the group falls due and parks q for the group
action parkOther (n q : node) {
  parked n q := true
}

-- §8.1: the connection between n and q closes: what is queued, owed or in flight between them is
-- lost, both ways; their promises close (§6.1); the state kept per connection goes (offers, the
-- ledger's too, the last-resort counts, the serve count, claims); parks, windows and timers stay
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

-- §6.1: the last resort's timer: nothing to do
action lrNoop (n : node) {
  require en_lrNoop n
  lrArmed n := false
}

-- §6.1 (the last resort): an announcer unparked meanwhile, or else a parked one not asked once
-- more; counted once the queue has taken the ask
action lrAsk (n q : node) (full : Bool) {
  require en_lrAsk n q
  lrArmed n := false
  inWindow n := true
  retryArmed n := true
  if full = false then
    stage askQ n q := true
    if parked n q then
      if countPerAnnouncer then
        askedParked n q := true
      else
        askedParked n Q := askedParked n Q || offered n Q
      everLastResort n := true
      everLrAsked n q := true
}

-- §6.1: a promise falls due (the answer is slow) and parks the peer for the group
action promiseDue (n q : node) {
  require en_promiseDue n q
  promise n q := false
  parked n q := true
}

-- when no honest node's machinery has anything to do, every honest offer to an honest node that has
-- its block has been resolved: the chunk is held, or the pull stopped
safety [offers_resolve] premises → ¬ work → installed N → offered N Q → ¬ adv N → ¬ adv Q →
  got N ∨ stop N

-- offers and asks go to nodes that hold the chunk, or to adversaries; an adversary asks anyone;
-- honest claims are true
invariant [offer_holder] (offered N Q → got Q ∨ adv Q) ∧ (ledger N Q → got Q ∨ adv Q)
invariant [ledger_before] ledger N Q → ¬ installed N
invariant [ask_holder] (stage askQ N Q → got Q ∨ adv Q) ∧ (stage askF N Q → got Q ∨ adv Q ∨ adv N)
invariant [claims_true] peerHas Q N → got N ∨ stop N ∨ adv N
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
-- an ask once more reaches an honest announcer, and is answered
invariant [asked_parked] premises → askedParked N Q → ¬ adv Q →
  got N ∨ stop N ∨ stage askQ N Q ∨ stage askF N Q ∨ served Q N ∨ peerHas Q N

-- a quiet state with an offer from an honest holder, to an honest node that has its block, never
-- resolved
ghost relation stalled :=
  ¬ work ∧ ∃ N Q, ¬ adv N ∧ ¬ adv Q ∧ installed N ∧ offered N Q ∧ ¬ got N ∧ ¬ stop N

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

-- an adversary offers and never answers: its promise falls due and parks it, the chunk arrives
-- otherwise, and the state is quiet with the ask to the adversary waiting there for good, which is
-- not work
sat trace [adv_withholds] {
  install
  offerAsk
  writeAsk
  promiseDue
  windowElapse
  arriveOther
  retryNoop
  assert (premises ∧ ¬ work ∧ ∃ N A, got N ∧ adv A ∧ parked N A ∧ stage askF N A)
}

/-! ## Known answers: with any one rule off, an offer is never resolved -/

-- the last-resort count kept per chunk: the last resort, armed by the adversary's offer, which came
-- first, is spent on it, and an honest announcer parked by another chunk is never asked again
sat trace [ka_count_per_chunk] {
  install
  arriveOther
  install
  parkOther
  parkOther
  offerParkedArm
  offerParked
  lrAsk
  writeAsk
  promiseDue
  windowElapse
  retryParked
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset ∧
    ¬ countPerAnnouncer ∧ ¬ work ∧ ∃ N A M, ¬ adv N ∧ adv A ∧ ¬ adv M ∧ installed N ∧
    offered N M ∧ ¬ got N ∧ ¬ stop N ∧ everArmedBy N A ∧ everLrAsked N A)
}

-- the control: with the count per announcer (the spec), the last resort goes on from the adversary
-- that announced first, and asks the honest announcer once more too
sat trace [count_per_announcer_goes_on] {
  install
  arriveOther
  install
  parkOther
  parkOther
  offerParkedArm
  offerParked
  lrAsk
  windowElapse
  retryParked
  lrAsk
  assert (premises ∧ ∃ N A M, ¬ adv N ∧ adv A ∧ ¬ adv M ∧ everArmedBy N A ∧ everLrAsked N A ∧
    everLrAsked N M)
}

-- F2: an offerer parked by another chunk is never asked
sat trace [ka_no_last_resort] {
  install
  arriveOther
  install
  parkOther
  offerParkedNoLR
  assert (¬ lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset ∧
    countPerAnnouncer ∧ stalled)
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
  assert (lastResort ∧ ¬ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ countsReset ∧
    countPerAnnouncer ∧ stalled)
}

-- an offer recorded before the block is never asked for
sat trace [ka_no_ledger] {
  install
  arriveOther
  offerEarly
  install
  assert (lastResort ∧ owedAnswers ∧ ¬ askLedger ∧ heldBackRetry ∧ countsReset ∧
    countPerAnnouncer ∧ stalled)
}

-- F11's recovery without its retry: an offer over an IHAVE limit is recorded and never asked for
sat trace [ka_held_back_lost] {
  install
  arriveOther
  install
  offerHeldBack
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ ¬ heldBackRetry ∧ countsReset ∧
    countPerAnnouncer ∧ stalled)
}

-- the last-resort count kept across a close: the ask it counted is lost with the connection, the
-- announcer offers again on the new one, and it is never asked: its count says it was asked once
-- more
sat trace [ka_counts_kept] {
  install
  arriveOther
  install
  parkOther
  offerParkedArm
  lrAsk
  writeAsk
  close
  offerParkedAskedNew
  windowElapse
  retryParked
  assert (lastResort ∧ owedAnswers ∧ askLedger ∧ heldBackRetry ∧ ¬ countsReset ∧
    countPerAnnouncer ∧ stalled)
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
      let n := Name.mkStr `NoStallAskAdv s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `NoStallAskAdv && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in NoStallAskAdv, resting on {rest.toList}"

end NoStallAskAdv
