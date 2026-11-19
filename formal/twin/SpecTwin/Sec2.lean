import SpecTwin.Sec1

/-! # The twin of protocol.md §2, "The wire" [c1, c7] (v0.10.4, spec 34f60f8): `message_id` (lines 276–277)

- **The document's line:** `f.group + uint32_le(f.index) + content_id(f)`. The twin computes the layout and asks
  `content_id`, at every call.
- **The toy calls the document's function through a wrapper that stores the id on the chunk object**
  (`toy/node.py`), so the document's body runs once per chunk object. The cache is the node's way of answering
  `content_id`: the tracer writes the question at every call the block makes, cache warm or cold, and checks
  at each that the id returned is the document's function's.
- A chunk in a record still carries its id (`ChunkF.mid`), as its identity there. What the twin computes here must
  be that id wherever the document's code uses it: the replay holds `content_id`'s answer to the carried id's last
  20 bytes. -/

namespace SpecTwin

open Node61

variable {m : Type → Type} [Monad m] [Node61 m]

/-- `message_id(f)` (lines 276–277): the structured id: 32 + 4 + 20 bytes -/
def messageId (f : ChunkF) : M m Key := do
  enter "message_id"
  if f.i ≥ 2 ^ 32 then                                      -- `uint32_le(f.index)`
    return (← crash "OverflowError: int too big to convert (message_id: uint32_le(f.index))")
  return .id (f.g ++ leHex 4 f.i ++ (← contentId f)) f.g f.i   -- `f.group + uint32_le(f.index) + content_id(f)`

end SpecTwin
