import SpecTwin.Sec42
import SpecTwin.Sec52

/-! # The twin of protocol.md §6.4, "Heartbeat gossip and pacing" [c15] (v0.10.4, spec 34f60f8): `on_heartbeat`,
`on_pace_tick` and `send_gossip`

- **`pace_queue` is the twin's own table:** one entry, `jobs`, whose value is the jobs in order, read and
  written whole as a lane of a peer's queue is. An empty queue is no value.
- **A job's time is kept as its 64 bits**, as a record writes it; the staleness test reads it as the float.
- **Questions:** `connected(q)`, and `group_bits(ids)`, the ids' indices per group, which is the node's stock
  gossip. §5.2's `announce` is the twin's own (Sec52.lean).
- **on_heartbeat** calls the twin's own `retry_offer` (§6.1) for each ask held back and `drop_stale_waits`
  (§4.2), so a heartbeat is one record with theirs in it.
  - `ihave_frames.clear()`, `ihave_asked.clear()` and `held_back.clear()` are each a write of every entry there
    (the tables' `clear`), and no read.
  - `held_back.values()` reads the table as a whole; its order is the node's (`heldBackOrder`).
  - Questions: `gossip_history.gossip_ids()`, `topic_peers()`, `q in mesh`, `gossip_eligible(q)`, asked of a
    peer outside the mesh alone, and the draw, `sample_without_replacement`.
  - `floor(GOSSIP_FACTOR * len(eligible))` is computed in floats, as the Python does (`gossipCount`).
- **The loop (L1):** each turn of `while pace_queue` pops one job, and nothing the call reaches appends one. So the
  turns are bounded by the jobs at entry: the fuel. At zero fuel with a job still queued the twin crashes, where
  the Python would turn again. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `send_gossip(q, ids)` (§6.4) [c7] -/
def sendGossip (q : Peer) (ids : List Key) : M m Unit := do
  enter "send_gossip"
  for (g, bits) in ← groupBits ids do                       -- `for g, bits in group_bits(ids):`
    announce q g bits                                       --   minus pushed[q], minus peer_has[q] (§5.2)

/-- `min(len, max(D_LAZY, floor(GOSSIP_FACTOR * len)))`, for `len` eligible peers. The product and its floor are
floats, as the Python's are; `math.floor` raises on a product that is not finite. A floor at or beyond `len` gives
`len` whatever it is, and one below zero gives what zero gives, so the floor is turned into a number only between
the two. -/
def gossipCount (len : Nat) : M m Nat := do
  let c := (← read).c
  let fl := Float.floor (c.GOSSIP_FACTOR * len.toFloat)
  if fl.isNaN then return (← crash "ValueError: cannot convert float NaN to integer (on_heartbeat: floor)")
  if fl.isInf then return (← crash "OverflowError: cannot convert float infinity to integer (on_heartbeat: floor)")
  let k := if fl ≤ 0 then 0 else if fl ≥ len.toFloat then len else fl.toUInt64.toNat
  return min len (max c.D_LAZY k)

/-- `on_heartbeat()` (§6.4) -/
def onHeartbeat : M m Unit := do
  enter "on_heartbeat"
  clearIhaveFrames; clearIhaveAsked                           -- §4.4's limits start again,
  let held ← allHeldBack                                    -- `for a in held_back.values(): retry_offer(a)`
  for k in ← heldBackOrder (held.map (·.1)) do
    match held.lookup k with
    | some a => retryOffer a                                --   the retry runs for what they held back,
    | none => crash "KeyError: held_back (on_heartbeat: the node's order names a chunk the table has not)"
  clearHeldBack                                             --   which they do not count
  dropStaleWaits                                            -- §4.2's copies and ties past their window
  let ids ← gossipIds                                       -- stock: ids of the last 3 heartbeats
  let mut eligible : List Peer := []
  for q in ← topicPeers do                                  -- `[q for q in topic_peers() if q not in mesh and`
    if !(← meshHas q) then                                  --   `gossip_eligible(q)]` (stock: scores)
      if ← gossipEligible q then eligible := eligible ++ [q]
  let n ← gossipCount eligible.length
  let ctx ← read
  for q in ← sample eligible n do                           -- `for q in sample_without_replacement(eligible, n):`
    if ctx.c.PACED then                                     -- [c15] `pace_queue.append((q, ids, now))`
      setPaceJobs .jobs ((← paceJobs .jobs) ++ [{ q, ids, at_ := ctx.now.toBits }])
    else sendGossip q ids
  branch (if ctx.c.PACED then "on_heartbeat: gossip paced" else "on_heartbeat: gossip sent at once")

/-- The turns of `on_pace_tick`'s loop, at most `fuel`. -/
def paceTurns : Nat → M m Unit
  | 0 => do
    if (← paceJobs .jobs).isEmpty then branch "on_pace_tick: the queue ran out"
    else crash "RecursionError: on_pace_tick (more turns than the jobs at entry: L1)"
  | fuel + 1 => do
    match ← paceJobs .jobs with                             -- `while pace_queue:`
    | [] => branch "on_pace_tick: the queue ran out"
    | job :: rest =>
      setPaceJobs .jobs rest                                -- `q, ids, at = pace_queue.pop(0)`
      let ctx ← read
      if ctx.now - Float.ofBits job.at_ ≥ ctx.c.HEARTBEAT then   -- stale
        branch "on_pace_tick: a stale job dropped"
        paceTurns fuel
      else if !(← connected job.q) then                     -- or q has left
        branch "on_pace_tick: the job of a peer that left dropped"
        paceTurns fuel
      else
        sendGossip job.q job.ids
        branch "on_pace_tick: one job's gossip sent"        -- one peer per tick, even if nothing was left to send

/-- `on_pace_tick()` (§6.4) [c15]: every HEARTBEAT / 16, from the first job queued -/
def onPaceTick : M m Unit := do
  enter "on_pace_tick"
  paceTurns (← paceJobs .jobs).length

end SpecTwin
