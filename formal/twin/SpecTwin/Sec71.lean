import SpecTwin.Readers
import SpecTwin.Sec51

/-! # The twin of protocol.md §7.1, the window [c14] (v0.10.4, spec 34f60f8): `acquire_slot`,
`release_unused_slot`, `track_in_flight`, `window_release`, `window_timeout` and `free_slot` (lines 1704–1746)

- **The window's three tables are the twin's own:** `in_flight`, a signed count in one entry (free_slot at 0
  leaves −1 on a drawn state); `waiters`, the line, one entry, the peers in order; `sent`, the send's time under
  its key (peer, group, index).
- **The block's code calls these six:** next_to_send (§7.2) and on_have (§4.3).
- **Reads as the Python's.** A count or a line read twice in the Python is read once here: a record's reads are a
  set. Where the Python does not read at all, the twin does not either: release_unused_slot looks at the count
  only where somebody is left in line.
- `W` is none where the node has no window (card 14 off: the toy's W is infinite): every count is under it.
- **Calls:** `wake` (the node's writer) and `after` (the window's timer, with the send's key and time).
  `origin_acked` (§5.1) is the twin's own (Sec51.lean). -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `in_flight < W` -/
def underW (n : Int) : M m Bool := do
  match (← read).c.W with
  | none => return true
  | some w => return n < (w : Int)

/-- `free_slot()` (lines 1743–1746) -/
def freeSlot : M m Unit := do
  enter "free_slot"
  setInFlight .count ((← inFlight .count) - 1)              -- `in_flight -= 1`
  match ← waitersLine .line with                            -- `if waiters: wake(waiters[0])`: the first writer in
  | q :: _ => wake q                                        --   line tries again (§7.2)
  | [] => pure ()

/-- `acquire_slot(p)` (lines 1710–1718): true, p's writer holds a slot; false, it waits in line -/
def acquireSlot (p : Peer) : M m Bool := do
  enter "acquire_slot"
  let n ← inFlight .count
  let line ← waitersLine .line
  if (← underW n) && (line.isEmpty || line.head? == some p) then    -- `in_flight < W and (not waiters or waiters[0] == p)`
    let rest := line.drop 1                                 -- `if waiters: waiters.popleft()`
    if !line.isEmpty then setWaitersLine .line rest
    setInFlight .count (n + 1)                              -- `in_flight += 1`
    match rest with                                         -- `if waiters and in_flight < W: wake(waiters[0])`:
    | q :: _ => if ← underW (n + 1) then wake q             --   slots remain: the next in line takes one too
    | [] => pure ()
    branch "acquire_slot: a slot"
    return true
  if !line.contains p then setWaitersLine .line (line ++ [p])   -- a writer keeps its place while it waits
  branch "acquire_slot: in line"
  return false

/-- `release_unused_slot(p)` (lines 1720–1726): p's writer has no chunk to send now -/
def releaseUnusedSlot (p : Peer) : M m Unit := do
  enter "release_unused_slot"
  let line ← waitersLine .line
  if line.contains p then                                   -- `if p in waiters:`
    let rest := line.erase p                                -- `waiters.remove(p)`: it leaves the line, and the next
    setWaitersLine .line rest                               --   may take a free slot
    match rest with                                         -- `if waiters and in_flight < W: wake(waiters[0])`
    | q :: _ => if ← underW (← inFlight .count) then wake q
    | [] => pure ()
    branch "release_unused_slot: left the line"
  if ← slotHeld? p then                                     -- `if slot_held[p]:`
    setSlotHeld p false
    freeSlot

/-- `track_in_flight(p, f)` (lines 1728–1732): the writer's slot now travels with chunk f -/
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

/-- `window_release(p, g, i)` (lines 1734–1735): p holds chunk i, from anyone (§4.3) -/
def windowRelease (p : Peer) (g : Group) (i : Nat) : M m Unit := do
  enter "window_release"
  let k : SendKey := (p, g, i)
  if (← sentAt? k).isSome then                              -- `if sent.pop((p, g, i), None) is not None: free_slot()`
    eraseSentAt k
    freeSlot
    branch "window_release: a send released"

/-- `window_timeout(key, at)` (lines 1737–1741) -/
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
