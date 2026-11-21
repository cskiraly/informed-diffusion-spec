import SpecTwin.Sec42
import SpecTwin.Sec52

/-! # The twin of protocol.md §5.1, "The source" [c3, P4] (v0.10.4, spec 34f60f8): `publish`,
`origin_acked` and `origin_written`

`origin_written` came with v0.10.4: at
`SOURCE_OFFERS = PUBLISH` a chunk of a group the node publishes joins its HAVE at its first write (next_to_send,
§7.2), and the HAVE goes to the mesh as at the acknowledgement.

- `origin` is the twin's own table: a group there with no bit is a value, and a group that
  is not there is one the node does not publish.
- `g not in origin or origin[g].has(f.index)` reads the one entry; so does the twin.
- The mesh is asked in the node's order (`for q in mesh`), and `send_have` is §4.2's, the twin's.
- `origin_acked` asks the mesh twice, as the Python iterates it twice, and reads `planned[g].get(i, ())` once a
  mesh peer, as the Python does (not at all where the mesh is empty).
- Two cases no record draws: a group in `planned` and not in `origin` (a KeyError in the Python, a crash here);
  a group with no row in `planned` (the Python raises at `planned[g]`; here the missing index reads as none).
  Both callers ask `g in planned` first, and publish writes `origin` and `planned` together.
-/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `origin_written(f)` (§5.1) [P4]: at PUBLISH, a chunk of a group we publish leaves for the first
time (§7.2): it joins our HAVE, which goes to the mesh as at the acknowledgement -/
def originWritten (f : ChunkF) : M m Unit := do
  enter "origin_written"
  let g := f.g
  match ← origin g with                                     -- `if g not in origin or origin[g].has(f.index): return`
  | none => branch "origin_written: not a group we publish"
  | some b =>
    if b.has f.i then
      branch "origin_written: in our HAVE already"
    else
      setOrigin g (b.set f.i)                               -- `origin[g].set(f.index)`
      for q in ← meshList do sendHave q g                   -- `for q in mesh: send_have(q, g)`
      branch "origin_written: the HAVE grows"

/-- `origin_acked(g, i)` (§5.1) [c3, P4]: a chunk of a group we publish is acknowledged: a peer's HAVE
names it (§4.3), or a copy's slot timed out first (§7.1) -/
def originAcked (g : Group) (i : Nat) : M m Unit := do
  enter "origin_acked"
  if (← read).c.SOURCE_OFFERS_PUBLISH then                  -- `if SOURCE_OFFERS == PUBLISH: return`
    branch "origin_acked: at PUBLISH, nothing"
    return
  let some b ← origin g                                     -- `origin[g]`
    | crash "KeyError: origin[g] (origin_acked: a group in planned and not in origin)"
  if b.has i then                                           -- `if origin[g].has(i): return`
    branch "origin_acked: acknowledged before"
    return
  setOrigin g (b.set i)                                     -- `origin[g].set(i)`: it joins our HAVE,
  for q in ← meshList do sendHave q g                       -- which goes to the mesh (§4.2),
  for p in ← meshList do                                    -- and the mesh peers not chosen to be pushed it are
    if !((← plannedTargets? g i).getD {}).contains p then   -- announced it: `if p not in planned[g].get(i, ()):`
      announce p g (1 <<< i)                                --   `announce(p, g, bitmap({i}))`
  branch "origin_acked: the HAVE grows"

/-- `publish(block, d, shards)` (§5.1) [c2, c3, P4]: the source of a group. It holds every chunk from
the start, plans R copies of each, sends the first copy of every chunk before any second, and leaves the mesh
peers not pushed a chunk to be announced it (at its acknowledgement, or now at PUBLISH).

The chunks are built here: a built chunk has no id until
`message_id(f)` is called, and is wide (the descriptor, the shard's proof and data), so `store` and that call's
`content_id` are asked with all of it. After `message_id` the chunk carries the id it returned.

Limits, named: a descriptor of no chunk (`planned[g]` would be an empty row: the twin stops at once, before any
question); a descriptor that counts more chunks than the shards give (`chunks[g][i]` a KeyError, which no record
writes). -/
def publish (block : Block) (d : Descriptor) (shards : List Shard) : M m Unit := do
  enter "publish"
  let c := (← read).c
  if d.count == 0 then
    return (← crash "limit: publish of a descriptor of no chunk (planned[g] an empty row, which the twin's table does not hold)")
  let g ← groupKey (← groupId d) block.slot                 -- `g = group_key(group_id(d), block.slot)`
  if ← expired g then                                       -- `if expired(g) or not live(block.slot): return`
    branch "publish: the group expired"
    return
  if !(← live block.slot) then
    branch "publish: past its live window"
    return
  setDesc g d                                               -- `desc[g] = d`
  for s in shards do                                        -- the source holds every chunk from the start
    let f : ChunkF :=                                       -- `Chunk(slot=…, beacon_block_root=block_root(block), …)`
      { g, i := s.index, slot := block.slot, root := ← blockRoot block, mid := .want g s.index,
        wide := some { desc := some d, proof := s.proof, data := s.data } }
    store g s.index f                                       -- `store(g, s.index, f)`
    let a ← messageId f                                     -- `mark_seen(message_id(f))`
    markSeen a
    gossipPut { f with mid := a }                           -- `gossip_history.put(f)` (stock, §6.4)
  setMine g ((1 <<< (← N (some d))) - 1)                    -- `mine[g] = all_bits(N(d))`
  setState g .complete                                      -- `state[g] = COMPLETE`
  setStopPull g true                                        -- `stop_pull[g] = True`
  setOrigin g 0                                             -- `origin[g] = bitmap(set())` [P4]: none yet
  let mut plan : Array (ChunkF × List Peer) := #[]
  for i in List.range (← N (some d)) do                     -- index order; each chunk's targets see earlier plans
    let f ← chunkAt g i                                     -- `f = chunks[g][i]`
    let targets ← choosePush f (← candidatesForSource f) c.R true   -- §5.3
    for p in targets do notePush p g i
    plan := plan.push (f, targets)
  let mut led : List Peer := []
  for copy in List.range c.R do                             -- the first copy of every chunk before any second [c2]
    for (f, targets) in plan do
      if let some p := targets[copy]? then                  -- `if copy < len(targets): p = targets[copy]`
        if !led.contains p then                             -- [P4] a peer's first chunk from us follows our HAVE
          led := p :: led                                   --   naming it
          let some o ← origin g
            | crash "KeyError: origin[g] (publish: written above)"
          let _ ← enqueue p (.have g (o ||| (1 <<< f.i))) true   -- `IDONTWANT(HaveBitmap(g, origin[g] | {f.index}))`
        if !(← enqueue p (.chunk f) false) then             -- refused: offered instead (§5.2)
          unpush p g f.i
          branch "publish: a push refused, unpushed"
  erasePlannedRow g                                         -- `planned[g] = {f.index: set(targets) for …}`: the row
  for (f, targets) in plan do                               --   assigned whole [c3]
    setPlanned g f.i (Std.HashSet.ofList targets)
  if c.SOURCE_OFFERS_PUBLISH then                           -- `if SOURCE_OFFERS == PUBLISH:` the offers now (§5.1)
    for (f, targets) in plan do
      for p in ← meshList do                                -- `for p in mesh:` once a planned chunk
        if !targets.contains p then announce p g (1 <<< f.i)
    branch "publish: published, the offers at publish"
  else
    branch "publish: published"

end SpecTwin
