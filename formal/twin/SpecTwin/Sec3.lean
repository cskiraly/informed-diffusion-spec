import SpecTwin.Sec1

/-! # The twin of protocol.md §3, "Validation: three levels, and what each gates" [c1, c6, c10] (v0.10.4, spec
34f60f8): level 1, `validate_chunk` (lines 341–351) and `committed_descriptor` (lines 353–358)

- **A chunk is wide where level 1 reads it:** its descriptor, its proof and its data, a blob. A chunk without
  them here is a crash: the record did not carry what the call reads.
- **A block is what level 1 reads of it:** its slot, and what its bid commits. `installed_block` answers with
  it, or nothing. Design A (`DESCRIPTOR_IN_CHUNK`): the bid commits the group's id, and the chunk carries the
  descriptor. Design B: the bid commits the descriptor.
- **The tree is the node's stand-in:** `verify_merkle_proof` is a question. The hash and the
  serialization, in `group_id` and `group_key`, are §1's questions.
- **Python's `or` short-circuits:** `d is None or group_key(group_id(d), block.slot) != f.group or not
  valid_descriptor(d)` asks the hash only where there is a descriptor, and reads the descriptor's validity only
  where the key matched.
- **A node that runs something else as `validate_chunk`** is asked. No cell has one: it is the directed
  sets' scenarios, which draw level 1's result to reach §4.2's paths. -/

namespace SpecTwin

open Node61

variable {m : Type → Type} [Monad m] [Node61 m]

/-- `committed_descriptor(block, f)` (lines 353–358) -/
def committedDescriptor (block : Block) (f : ChunkF) : M m (Option Descriptor) := do
  enter "committed_descriptor"
  -- `bid = block.body.signed_execution_payload_bid.message`
  if (← read).c.DESCRIPTOR_IN_CHUNK then                    -- design A
    let some w := f.wide | crash "AttributeError: descriptor (committed_descriptor: a chunk without what level 1 reads)"
    let some fd := w.desc                                   -- `f.descriptor`: a chunk without the field
      | crash "AttributeError: descriptor (committed_descriptor: a chunk without its descriptor, under design A)"
    -- `ok = group_id(f.descriptor) == bid.execution_payload_segment_group_id`
    let ok := some (← groupId fd) == block.groupId
    return if ok then some fd else none
  return block.desc                                         -- design B: `bid.execution_payload_segment_descriptor`

/-- `validate_chunk(f)` (lines 341–351): level 1, the chunk is the committed piece at its index -/
def validateChunk (f : ChunkF) : M m Verdict := do
  if (← read).replaced.contains "validate_chunk" then return ← validateChunkNode f.narrow     -- the node's own
  enter "validate_chunk"
  let some block ← installedBlock f.slot f.root             -- validated and applied locally
    | do branch "validate_chunk: no block yet"; return .defer   -- held in a bounded store (§8.2)
  if f.slot != block.slot then                              -- the slot a copy names is its block's (§1)
    branch "validate_chunk: another slot than its block's"; return .reject
  let some d ← committedDescriptor block f
    | do branch "validate_chunk: no committed descriptor"; return .reject
  if (← groupKey (← groupId d) block.slot) != f.g then
    branch "validate_chunk: not the group's key"; return .reject
  if !(← validDescriptor d) then
    branch "validate_chunk: not a valid descriptor"; return .reject
  if f.i ≥ d.count then
    branch "validate_chunk: an index beyond the count"; return .reject
  let some w := f.wide | crash "AttributeError: data (validate_chunk: a chunk without what level 1 reads)"
  if (w.data.n : Int) != (← segmentLength d f.i) then       -- `len(f.data) != segment_length(d, f.index)`
    branch "validate_chunk: not the segment's length"; return .reject
  if !(← verifyMerkleProof d.root w.data f.i d.count w.proof) then
    branch "validate_chunk: the proof fails"; return .reject
  branch "validate_chunk: accepted"
  return .accept

end SpecTwin
