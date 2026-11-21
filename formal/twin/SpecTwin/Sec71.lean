import SpecTwin.Readers
import SpecTwin.Sec51

/-! # The twin of protocol.md §7.1, the window [c14] (v0.10.9): `front`, `wake_front`, `write_waits`,
`acquire_slot`, `release_unused_slot`, `track_in_flight`, `window_release`, `window_timeout` and `free_slot`

- **The window's three tables are the twin's own:** `in_flight`, a signed count in one entry (free_slot at 0
  leaves −1 on a drawn state); `waiters`, the line, one entry, the peers in order; `sent`, the send's time under
  its key (peer, group, index).
- **The block's code calls them:** next_to_send (§7.2: acquire_slot, release_unused_slot, track_in_flight) and
  on_have (§4.3: window_release); the node's writer calls write_waits when a write does not complete at once (§7.3);
  front and wake_front are called by the window's own.
- **The line's front** is its first writer that can write: `writing` is asked of each writer in line in turn, up
  to the first that is not mid-write, as the Python's generator asks it; acquire_slot asks it under W alone;
  wake_front reads the count first and returns where no slot is free, and then asks `front`.
- **Reads as the Python's.** A count or a line read twice in the Python is read once here: a record's reads are a
  set. Where the Python does not read at all, the twin does not either: release_unused_slot looks at the count
  where the peer was in line (wake_front's) and where it gives back a held slot (free_slot's), and nowhere else.
- `W` is none where the node has no window (card 14 off: the toy's W is infinite): every count is under it.
- **Calls:** `wake` (the node's writer), `writing` (whether a writer's write has not completed, §7.3) and `after`
  (the window's timer, with the send's key and time). `origin_acked` (§5.1) is the twin's own (Sec51.lean). -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `in_flight < W` -/
def underW (n : Int) : M m Bool := do
  match (← read).c.W with
  | none => return true
  | some w => return n < (w : Int)

/-- `front()` (§7.1): the first in line whose writer can write. `writing` is asked of each in turn, up to
that one, as the generator asks it -/
def front : M m (Option Peer) := do
  enter "front"
  for q in (← waitersLine .line) do                         -- `next((q for q in waiters if not writing(q)), None)`
    if ← writing q then branch "front: a writer mid-write passed"   -- a writer whose write has not completed
    else return some q                                      --   (§7.3) keeps its place
  return none

/-- `wake_front()` (§7.1): a slot is free: the first in line that can write tries again (§7.2) -/
def wakeFront : M m Unit := do
  enter "wake_front"
  if !(← underW (← inFlight .count)) then                   -- `if in_flight >= W: return`
    branch "wake_front: no slot free"
    return
  match ← front with                                        -- `q = front()`
  | some q => wake q                                        -- `if q is not None: wake(q)`
  | none => branch "wake_front: nobody in line can write"

/-- `write_waits(p)` (§7.1): p's write has not completed (§7.3): the line now skips p, so the first writer in line
that can write tries again, if a slot is free -/
def writeWaits (p : Peer) : M m Unit := do
  enter "write_waits"
  if (← waitersLine .line).contains p then                  -- `if p in waiters: wake_front()`
    wakeFront
  else branch "write_waits: not in line"

/-- `free_slot()` (§7.1) -/
def freeSlot : M m Unit := do
  enter "free_slot"
  setInFlight .count ((← inFlight .count) - 1)              -- `in_flight -= 1`
  wakeFront                                                 -- the first writer in line that can write tries again

/-- `acquire_slot(p)` (§7.1): true, p's writer holds a slot; false, it waits in line -/
def acquireSlot (p : Peer) : M m Bool := do
  enter "acquire_slot"
  let n ← inFlight .count
  let takes ← if ← underW n then do                         -- `in_flight < W and front() in (None, p)`: no writer
      let q ← front                                         --   that can write is ahead of p (front asked under W
      pure (q == none || q == some p)                       --   alone)
    else pure false
  if takes then
    let line ← waitersLine .line
    if line.contains p then setWaitersLine .line (line.erase p)    -- `if p in waiters: waiters.remove(p)`
    setInFlight .count (n + 1)                              -- `in_flight += 1`
    wakeFront                                               -- slots remain: the next in line takes one too
    branch "acquire_slot: a slot"
    return true
  let line ← waitersLine .line
  if !line.contains p then setWaitersLine .line (line ++ [p])   -- a writer keeps its place while it waits
  branch "acquire_slot: in line"
  return false

/-- `release_unused_slot(p)` (§7.1): p's writer has no chunk to send now -/
def releaseUnusedSlot (p : Peer) : M m Unit := do
  enter "release_unused_slot"
  let line ← waitersLine .line
  if line.contains p then                                   -- `if p in waiters:`
    setWaitersLine .line (line.erase p)                     -- `waiters.remove(p)`: it leaves the line, and the next
    wakeFront                                               --   may take a free slot
    branch "release_unused_slot: left the line"
  if ← slotHeld? p then                                     -- `if slot_held[p]:`
    setSlotHeld p false
    freeSlot

/-- `track_in_flight(p, f)` (§7.1): the writer's slot now travels with chunk f -/
def trackInFlight (p : Peer) (f : ChunkF) : M m Unit := do
  enter "track_in_flight"
  let k : SendKey := (p, f.g, f.i)
  if (← sentAt? k).isSome then                              -- `if key in sent: return free_slot()`: a second copy
    freeSlot                                                --   still in flight: back at once
    branch "track_in_flight: a second copy"
    return
  let now := (← read).now
  setSentAt k now                                           -- `sent[key] = now`
  after (← read).c.WINDOW_TIMEOUT (.windowTimeout k now)    -- `after(WINDOW_TIMEOUT, window_timeout, key, now)`

/-- `window_release(p, g, i)` (§7.1): p holds chunk i, from anyone (§4.3) -/
def windowRelease (p : Peer) (g : Group) (i : Nat) : M m Unit := do
  enter "window_release"
  let k : SendKey := (p, g, i)
  if (← sentAt? k).isSome then                              -- `if sent.pop((p, g, i), None) is not None: free_slot()`
    eraseSentAt k
    freeSlot
    branch "window_release: a send released"

/-- `window_timeout(key, at)` (§7.1) -/
def windowTimeout (k : SendKey) (at_ : Float) : M m Unit := do
  enter "window_timeout"
  if (← sentAt? k) == some at_ then                         -- `if sent.get(key) == at:`
    eraseSentAt k                                           -- `del sent[key]`
    freeSlot
    if ← planned k.2.1 then originAcked k.2.1 k.2.2         -- [c3, P4] no claim came in time: released anyway (§5.1)
    branch "window_timeout: released"
  else
    branch "window_timeout: stale"

end SpecTwin
