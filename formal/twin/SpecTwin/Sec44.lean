import SpecTwin.Sec61
import SpecTwin.Sec1

/-! # protocol.md §4.4, "An IHAVE arrives" [c3, c5, c7], and §6.2's `gated` (v0.10.4, spec 34f60f8)

`on_ihave`, `over_ihave_limits`, `valid_id` and `expand`, line for line, and `gated`. Python's meanings kept on
purpose:
- `or` and `and` short-circuit, so the node and the tables are asked in the Python's order, and the second side
  only where the first does not decide: `held(a)` before `expired(group(a))`, `gated(a)` before
  `authenticable(group(a))`, `ihave_frames[p]` before `ihave_asked[p]`. Each is written as two `if`s: in a `do`
  block `(← x) || (← y)` runs both. (No cell can tell the two apart, since there a chunk an IHAVE brings is
  never held and its group never stopped; the directed records tell them apart.)
- `expand(entry)` is built whole before the first of its asks is handled: the comprehension reads `mine[g]` once
  per index of the bitmap, and `known_id[g]` for the indices not held;
- a bitmap iterates upward;
- `x[p] += 1` is a read of `x[p]` and a write of it;
- a limit the client does not set is no limit: the count is read all the same, as the Python compares it with
  infinity;
- `valid_id`'s `g not in desc or i < N(desc[g])` reads `desc[g]` twice where the descriptor is known (the test,
  then the count), once where it is not, and not at all for an index at or beyond `MAX_PLAIN_CHUNKS`.

The functions reach the block's tables through `Tables` and in no other way.

An id of any length is an entry since v0.10, which settles what §4.4 did not say before: one that is not a
chunk's structured id is ignored (`valid_id`), and so is a bitmap beyond a HAVE's limits, with a penalty. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `gated(a)` (§6.2): from the decode claim on, no further asks for the group -/
def gated (a : Key) : M m Bool := do
  enter "gated"
  stopPull a.group

/-- `over_ihave_limits(p)` (§8.2, per peer and heartbeat) -/
def overIhaveLimits (p : Peer) : M m Bool := do
  enter "over_ihave_limits"
  let c := (← read).c
  let frames ← ihaveFrames p
  if c.MAX_IHAVE_MESSAGES.any (frames > ·) then
    branch "over_ihave_limits: frames"
    return true
  let asked ← ihaveAsked p
  let r := c.MAX_IHAVE_LENGTH.any (asked ≥ ·)
  branch (if r then "over_ihave_limits: asks" else "over_ihave_limits: no")
  return r

/-- `valid_id(a)`: a chunk's structured id (§2): its 56 bytes, and an index its group can have (§8.2). It is
asked of an entry that is not a bitmap; of a bitmap, the Python's `len` raises. -/
def validId (e : IhaveEntry) : M m Bool := do
  enter "valid_id"
  match e with
  | .other _ =>                                             -- `if len(a) != 56: return False`
    branch "valid_id: not 56 bytes"
    return false
  | .bitmap .. => crash "TypeError: len() of a bitmap (valid_id)"
  | .id a =>                                                -- `g, i = group(a), index(a)`
    let c := (← read).c
    if !(a.index < c.MAX_PLAIN_CHUNKS) then                 -- `i < MAX_PLAIN_CHUNKS and (…)`
      branch "valid_id: no group has the index"
      return false
    if (← desc a.group).isNone then                         -- `g not in desc or …`
      branch "valid_id: the count not known"
      return true
    let n ← N (← desc a.group)                              -- `i < N(desc[g])`: §1's N, of a second read
    let r := a.index < n
    branch (if r then "valid_id: within the count" else "valid_id: beyond the count")
    return r

/-- `expand(entry)` [c7] -/
def expand (entry : IhaveEntry) : M m (List Key) := do
  enter "expand"
  match entry with
  | .id a =>                                                -- `if not is_have_bitmap(entry):`
    if ← validId (.id a) then                               -- `return [entry] if valid_id(entry) else []`
      branch "expand: an id"
      return [a]
    branch "expand: an id ignored"
    return []
  | e@(.other _) =>
    if ← validId e then crash "never: valid_id holds of an entry that is not 56 bytes (expand)"
    branch "expand: an id ignored"
    return []
  | .bitmap g bits =>
    let mut out := #[]
    for i in bits.toList do
      if !(← mineBits g).has i then                         -- `if not mine[g].has(i)`
        out := out.push ((← knownId g i).getD (.want g i))  -- `known_id[g].get(i) or WantIndex(group=g, index=i)`
    branch "expand: a bitmap"
    return out.toList

/-- `on_ihave(p, ih)`: returns the asks (§4.1). `ids` is `ih.ids`. -/
def onIhave (p : Peer) (ids : List IhaveEntry) : M m (List Key) := do
  enter "on_ihave"
  if !ids.isEmpty then setIhaveFrames p ((← ihaveFrames p) + 1)  -- IHAVE-bearing frames (§8.2)
  let mut candidates := #[]
  for entry in ids do
    if let .bitmap g bits := entry then                     -- `if is_have_bitmap(entry) and not valid_have(entry):`
      if !(← validHave g bits) then                         --   a bitmap is held to a HAVE's limits: ignored,
        penalise p                                          --   and counted (§8.2)
        branch "on_ihave: a bitmap beyond a HAVE's limits"
        continue
    for a in ← expand entry do                              -- [c7]
      -- `if held(a) or expired(group(a)): continue`, one side at a time: Lean's `||` on two `←` asks both
      if ← held a then
        branch "on_ihave: held"
        continue
      if ← expired a.group then
        branch "on_ihave: expired"
        continue
      addOffer a p                                          -- [c5] offer table (§6.1)
      -- `if gated(a) or not authenticable(group(a)): continue`: [c6] stop-pull; the block first (§3)
      if ← gated a then
        branch "on_ihave: gated"
        continue
      if !(← authenticable a.group) then
        branch "on_ihave: no block"
        continue
      if ← tiedToRoot p a then                              -- its copy waits (§4.2)
        branch "on_ihave: tied"
        continue
      if ← parked p a then                                  -- [c5] park; last resort (§6.1)
        lastResort a
        branch "on_ihave: parked"
        continue
      if ← outstanding p a then                             -- an ask of it to p is open (§6.1)
        branch "on_ihave: outstanding"
        continue
      candidates := candidates.push a
  let mut asks := #[]
  for a in ← shuffled candidates.toList do                  -- §6.1
    if ← overIhaveLimits p then
      setHeldBack (a.group, a.index) a                      -- retried at the next heartbeat (§6.4)
      branch "on_ihave: held back"
    else if ← mayAsk a p then
      asks := asks.push a
      setIhaveAsked p ((← ihaveAsked p) + 1)                -- an ask in reply to p's IHAVEs
      branch "on_ihave: asks"
  return asks.toList

end SpecTwin
