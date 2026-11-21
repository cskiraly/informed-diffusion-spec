import SpecTwin.Readers

/-! # protocol.md §6.1, "One ask per chunk at a time, move on, park" [c5] (v0.10.4, spec 34f60f8;
the block's `close_promises` and `drop_offer` stand with §4.2's deferral path, in Sec42.lean)

The block's twelve functions, in its order, line for line. Python's meanings kept on purpose:
- `and` and `or` short-circuit, so the node is asked in the Python's order;
- `min` returns the first of the least;
- the offer lists keep their order; the announcers beyond a list come in the node's own order (`ownOrder`);
- a bitmap iterates upward;
- floats are IEEE doubles;
- the state is read entry by entry, the same entries under the same conditions as the Python reads them: the
  replay compares which entries a call read, not how often or in which order (`announcers` reads `offers[a]`
  once, the Python once more per connected peer).

A missing entry reads as empty (§8.1). `branch` marks each way out of a function, for the replay's coverage.
The functions have no state of their own: they reach §6.1's tables through `Tables` and in no other way. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `may_ask(a, p)` -/
def mayAsk (a : Key) (p : Peer) : M m Bool := do
  enter "may_ask"
  let ctx ← read
  if let some t := (← askedAt? a) then
    if ctx.now - t < ctx.c.IWANT_WINDOW then                 -- 200 ms: an ask is in flight
      branch "may_ask: in flight"
      return false
  setAskedAt a ctx.now
  setTried a p ctx.now
  after (ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK) (.retryOffer a)    -- move on, once the window has closed
  branch "may_ask: asks"
  return true                                               -- the promise starts at the write (§7.2)

/-- `parked(p, a)` -/
def parked (p : Peer) (a : Key) : M m Bool := do
  enter "parked"
  let t := (← parkUntil? p a.group).getD negInf
  return (← read).now < t

/-- `outstanding(q, a)`: an ask of a's chunk to q, promised or still queued, in either form -/
def outstanding (q : Peer) (a : Key) : M m Bool := do
  enter "outstanding"
  let k := a.chunk
  if (← allPromises).any (fun ((b, r), _) => r == q && b.chunk == k) then
    branch "outstanding: promised"
    return true
  -- `any((group(b), index(b)) == k for e in queue[q].normal for c in e.iwants() for b in c.ids)`: the twin's own
  -- table; a lane not there reads as empty
  let r := ((← lane? q .normal).getD []).any (fun e => e.asks.any (fun b => b.chunk == k))
  branch (if r then "outstanding: queued" else "outstanding: no")
  return r

/-- `add_offer(a, p)`, within §8.2's limits on a's group -/
def addOffer (a : Key) (p : Peer) : M m Unit := do
  enter "add_offer"
  setOffered p a.group ((← offeredBits p a.group).set a.index)   -- every offer kept, per connection and group
  let o ← offersOf a                                        -- the first 16, in announcement order, are
  if !o.contains p && o.length < 16 then                    --   tried first; an announcer is in at most
    if (← listed p) < 256 then                              --   256 of these lists (§8.2)
      setOffers a (o ++ [p])
      branch "add_offer: listed"
      return
  branch "add_offer: kept in offered only"

/-- `announcers(a)`: the list, then every other peer that offered a, in the node's own order -/
def announcers (a : Key) : M m (List Peer) := do
  enter "announcers"
  let o ← offersOf a
  let peers ← connectedTopicPeers
  let rest ← peers.filterM fun q => do
    if o.contains q then return false
    return (← offeredBits q a.group).has a.index
  return o ++ (← ownOrder rest a)

/-- `ledger(g)`: what was offered of g and is not held, asked as expand (§4.4) would ask it -/
def ledger (g : Group) : M m (List Key) := do
  enter "ledger"
  let mut bits : Bits := 0
  for q in (← connectedTopicPeers) do
    bits := bits ||| (← offeredBits q g)
  let mut out : List Key := []
  for i in bits.toList do
    if !(← mineBits g).has i then
      out := out ++ [(← knownId g i).getD (.want g i)]
  branch (if out.isEmpty then "ledger: empty" else "ledger: asks")
  return out

/-- `untried(cands, a)`: the earliest announcer not asked yet (offers keep announcement order) -/
def untried (cands : List Peer) (a : Key) : M m (Option Peer) := do
  enter "untried"
  for q in cands do
    if (← tried? a q).isNone then return some q
  return none

/-- `least_recently_tried(cands, a)`: `min(cands, key=lambda q: tried[a][q])` -/
def leastRecentlyTried (cands : List Peer) (a : Key) : M m Peer := do
  enter "least_recently_tried"
  let mut best : Option (Peer × Float) := none
  for q in cands do
    let some t := (← tried? a q) | crash s!"KeyError: {q} (least_recently_tried: tried[a][q])"
    match best with
    | none => best := some (q, t)
    | some (_, bt) => if t < bt then best := some (q, t)
  let some (q, _) := best | crash "ValueError: min() of an empty sequence (least_recently_tried)"
  return q

/-- `promise_due(a, p, at)`: k = 1, one broken promise parks p for this group only, 30 s -/
def promiseDue (a : Key) (p : Peer) (at_ : Float) : M m Unit := do
  enter "promise_due"
  let ctx ← read
  let some t := (← promise? a p) | branch "promise_due: gone"; return
  if t != at_ then                                          -- delivered, closed on decode, or gone
    branch "promise_due: another ask's"                     --   with the connection
    return
  erasePromise a p
  setPark p a.group (ctx.now + ctx.c.PARK_TTL)
  branch "promise_due: parks"

/-- `last_resort(a)`: every announcer of a is parked: each is asked once more, later; counted per chunk,
whichever form names it -/
def lastResort (a : Key) : M m Unit := do
  enter "last_resort"
  let ctx ← read
  let k := a.chunk
  let done ← askedParkedOf k
  let untied ← (← announcers a).filterM fun q => return !(← tiedToRoot q a)   -- a tied announcer is passed over
  if (← lrArmed? k) then
    branch "last_resort: armed already"
    return
  for q in untied do
    if !(← parked q a) then
      branch "last_resort: an announcer not parked"
      return
  if untied.all done.contains then
    branch "last_resort: each asked once more"
    return
  setLrArmed k true
  if done.size ≥ 1024 then                                  -- 2 ** n does not convert to a double: Python
    crash "OverflowError: int too large to convert to float (last_resort)"   --   raises, k already armed
  after (ctx.c.PROMISE * (2 ^ done.size).toFloat) (.askParked a)    -- 0.4 s, 0.8 s, 1.6 s, ...
  branch "last_resort: arms"

/-- `retry_offer(a)` -/
def retryOffer (a : Key) : M m Unit := do
  enter "retry_offer"
  let ctx ← read
  if (← held a) then branch "retry_offer: held"; return
  if (← stopPull a.group) then branch "retry_offer: stop-pull"; return
  if (← expired a.group) then branch "retry_offer: expired"; return
  if ctx.now - (← askedAt? a).getD negInf < ctx.c.IWANT_WINDOW then
    branch "retry_offer: in flight"
    return
  let cands ← (← announcers a).filterM fun q => do
    if (← parked q a) then return false
    return !(← tiedToRoot q a)
  if cands.isEmpty then                                     -- every announcer is parked, or tied (§4.2)
    branch "retry_offer: none to ask, last resort"
    return (← lastResort a)
  let free ← cands.filterM fun q => return !(← outstanding q a)   -- an announcer not yet answered is not asked
  if free.isEmpty then                                      -- again: look again later
    branch "retry_offer: all outstanding, again"
    return (← after (ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK) (.retryOffer a))
  let pick ← match (← untried free a) with
    | some q => do branch "retry_offer: untried"; pure q
    | none => do branch "retry_offer: least recently tried"; leastRecentlyTried free a
  if (← mayAsk a pick) then
    let _ ← enqueue pick (.iwant [a]) false

/-- `ask_parked(a)` -/
def askParked (a : Key) : M m Unit := do
  enter "ask_parked"
  let ctx ← read
  let k := a.chunk
  setLrArmed k false
  if (← held a) then branch "ask_parked: held"; return
  if (← stopPull a.group) then branch "ask_parked: stop-pull"; return
  if (← expired a.group) then branch "ask_parked: expired"; return
  if ctx.now - (← askedAt? a).getD negInf < ctx.c.IWANT_WINDOW then   -- someone was asked meanwhile
    branch "ask_parked: in flight"
    return
  let untied ← (← announcers a).filterM fun q => return !(← tiedToRoot q a)
  let mut cands ← untied.filterM fun q => return !(← parked q a)   -- an announcer unparked meanwhile first
  if cands.isEmpty then
    cands ← untied.filterM fun q => return !(← askedParkedOf k).contains q   -- read per announcer, as the Python
    if cands.isEmpty then
      branch "ask_parked: each asked once more"
      return
    branch "ask_parked: a parked announcer"
  else
    branch "ask_parked: an announcer unparked"
  let free ← cands.filterM fun q => return !(← outstanding q a)   -- none asked again while not answered:
  if free.isEmpty then                                      --   the last resort waits as the retry does
    setLrArmed k true
    branch "ask_parked: all outstanding, again"
    return (← after (ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK) (.askParked a))
  let pick ← match (← untried free a) with
    | some q => do branch "ask_parked: untried"; pure q
    | none => do branch "ask_parked: least recently tried"; leastRecentlyTried free a
  if (← mayAsk a pick) then
    if (← enqueue pick (.iwant [a]) false) then
      if (← parked pick a) then                             -- counted once the queue has taken the ask
        setAskedParked k ((← askedParkedOf k).insert pick)
        branch "ask_parked: counted"

end SpecTwin
