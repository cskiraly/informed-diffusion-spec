import SpecTwin.Sec52
import SpecTwin.Sec53

/-! # The twin of protocol.md's `forward` (§5.2), `candidates_for_source` (§5.1)
and `on_mesh_join` (§5.4) (v0.10.4, spec 34f60f8)

- **`forward` at a node that runs something else under the name** (the cells silent and cap-wait: a faulty node
  forwards nothing; a directed set's scenario) is asked of the node by its caller, on_validated, as
  push_rebuilt is by decode_group.
- **The mesh is asked twice in `forward`,** as the Python iterates it twice (`holding`, then `cands`); each answer
  is the peers in the node's order.
- **`gossip_history.put(f)`** is the node's (the stock message cache): a call.
- **`chunks`** is another section's table (the node's store). on_mesh_join reads its keys: the groups held, in the
  node's order, and a group's indices. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `candidates_for_source(f)` (§5.1) [c13] -/
def candidatesForSource (f : ChunkF) : M m (List Peer) := do
  enter "candidates_for_source"
  let c := (← read).c
  let stripe := c.UPLINK ≥ c.STRIPE_UPLINK                  -- [c13] configured uplink
  let pool ← if stripe then connectedTopicPeers else meshList
  branch (if stripe then "candidates_for_source: every connected peer" else "candidates_for_source: the mesh")
  pool.filterM fun p => return !(← peerHas p f.g).has f.i   -- `if not peer_has[p][f.group].has(f.index)`

/-- `forward(f, from_peer)` (§5.2) [c3, c4, c11, c17] -/
def forward (f : ChunkF) (fromPeer : Peer) : M m Unit := do
  enter "forward"
  let g := f.g
  let i := f.i
  let holding ← (← meshList).filterM fun p => return (← peerHas p g).has i   -- [c4] the sender, normally
  let cands := (← meshList).filter fun p => !holding.contains p && p != fromPeer
  let budget := (← read).c.R_NODE - holding.length          -- `max(0, R_NODE - len(holding))`  [c3, c4, c11, c17]
  let targets ← choosePush f cands budget false             -- §5.3
  for p in targets do
    if ← enqueue p (.chunk f) false then                    -- [c7]
      notePush p g i
    else
      owe p g (1 <<< i)                                     -- [c3] refused: offered instead
      branch "forward: a push refused, owed"
  for p in cands do
    if !targets.contains p then announce p g (1 <<< i)      -- [c3]
  gossipPut f                                               -- stock message cache (§6.4)
  branch (if budget == 0 then "forward: no budget" else "forward: a budget")

/-- `on_mesh_join(p)` (§5.4): p joins our mesh -/
def onMeshJoin (p : Peer) : M m Unit := do
  enter "on_mesh_join"
  for g in ← chunksGroups do                                -- `for g in list(chunks):`
    if ← expired g then                                     -- nothing of an expired or dropped group
      branch "on_mesh_join: an expired group"
      continue
    if (← state? g) == some .invalid then                   -- `state[g] == INVALID`
      branch "on_mesh_join: a dropped group"
      continue
    let bits := (← chunkIndices g).foldl (fun b j => b ||| (1 <<< j)) 0   -- `bitmap(set(chunks[g]))`
    announce p g bits                                       -- what we can serve, received or rebuilt (§5.2)
    branch "on_mesh_join: a group offered"

end SpecTwin
