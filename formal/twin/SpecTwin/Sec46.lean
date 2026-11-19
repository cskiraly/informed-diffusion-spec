import SpecTwin.Sec42
import SpecTwin.Sec52

/-! # The twin of protocol.md §4.6, "Decode, the claim, repair and the levels above" [c6, c10] (v0.10.4, spec
34f60f8): `decode_group` (lines 841–850), `push_rebuilt` (lines 852–861) and `drop_group` (lines 863–870)

`claim_group` is §4.6's too, and stands in Sec42.lean, before on_validated, which calls it.

- **`stop_pull` is the twin's own table,** since these two set it: gated's, retry_offer's and ask_parked's
  reads of it are reads of the twin's state, and not on the tape.
- **decode_group** runs off the chunk path (`start`), so it is a record of its own. The codec is the node's:
  `decode_and_reencode` answers with the rebuilt chunks, each under its index, in the node's order, or none.
  `payload_of` and `deliver` are the node's too (level 3).
- **push_rebuilt:** the mesh in the node's order, drawn (`shuffled`); what each peer is known to hold is the
  twin's `peer_has` and another section's `pushed`; a chunk held is a read of `chunks[g][i]`; `note_push` and
  `owe` are §5.2's (Sec52.lean). A peer's shortfall can be negative: an integer.
- **A node that runs something else as `push_rebuilt`** (the cells with `--rebuilt none`, hold, announce, capped)
  is asked, where the document's function would be called.
- **The node's helpers are calls with their logs:** `discard_queued`, `discard_paced`,
  `close_promises_of_group` (§8.2's interface). `gossip_history.remove_group` is the stock cache's. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `push_rebuilt(g, new)` (lines 852–861) [c10]: to the mesh peers still short of K -/
def pushRebuilt (g : Group) (new : List Nat) : M m Unit := do
  enter "push_rebuilt"
  for q in ← shuffledNats (← meshList) do                   -- `for q in shuffled(mesh):`
    let known := (← peerHas q g) ||| (← pushed q g)         -- what q claimed, and what we chose to push it
    let short : Int := ((← K (← desc g)) : Int) - known.popcount    -- q's shortfall: none after its decode claim
    if short ≤ 0 then
      branch "push_rebuilt: a peer not short"
      continue
    let lacks ← shuffledNats (new.filter fun i => !known.has i)     -- at random, so that decoded neighbours tend
    for i in lacks.take short.toNat do                              --   to differ
      if ← enqueue q (.chunk (← chunkAt g i)) false then    -- cards 8, 9, 12 and 14 act on it (§7.2)
        notePush q g i
      else
        owe q g (1 <<< i)                                   -- refused by a full queue: offered instead (§5.2)
        branch "push_rebuilt: a push refused, owed"
    branch "push_rebuilt: a peer short"

/-- `drop_group(g)` (lines 863–870): level 2 or level 3 failed -/
def dropGroup (g : Group) : M m Unit := do
  enter "drop_group"
  setState g .invalid                                       -- `state[g] = INVALID`
  setStopPull g true                                        -- `stop_pull[g] = True`
  discardQueued g                                           -- g's chunks, IHAVEs and IWANTs in every queue, and
                                                            --   what is owed of g; HAVEs stay
  gossipRemoveGroup g                                       -- no further heartbeat announcements of g
  discardPaced g                                            -- nor paced ones
  closePromisesOfGroup g                                    -- its announcers did nothing wrong: nobody is parked

/-- `decode_group(g)` (lines 841–850): level 2, off the chunk path (§3) -/
def decodeGroup (g : Group) : M m Unit := do
  enter "decode_group"
  -- `d = desc[g]`. A named limit: with no descriptor the document's `desc[g]` is a
  -- KeyError, and so is this; the toy's `desc` is a map that answers None for a missing group (node.py:
  -- `DefaultMap(None)`), so the toy goes on and asks its codec with None. No record can hold the case (the
  -- tracer's writing of that question has no form for it), and no caller reaches it: open_group writes the
  -- group's descriptor before its first chunk is stored.
  let some d ← desc g
    | crash "KeyError: desc (decode_group: a group with no descriptor)"
  let rebuilt ← decodeAndReencode g d                       -- any K chunks -> all N, or None if the root differs
  if ← expired g then                                       -- the group passed its lifetime meanwhile (§8.1)
    branch "decode_group: expired meanwhile"; return
  match rebuilt with
  | none =>
    dropGroup g                                             -- an inconsistent code: the builder's fault
    branch "decode_group: the root differs, dropped"
  | some chunks =>
    let mut new : List Nat := []                            -- rebuilt, and not received meanwhile
    for (i, _) in chunks do
      if !(← receivedBits g).has i then new := new ++ [i]
    for (i, f) in chunks do                                 -- `for i in new: store(g, i, rebuilt[i])`: servable
      if new.contains i then store g i f                    --   from now on; not marked seen
    setState g .complete
    if (← read).replaced.contains "push_rebuilt" then pushRebuiltNode g new      -- [c10] repair; or the node's own
    else pushRebuilt g new
    deliver g (← payloadOf chunks)                          -- level 3: the application's checks (§3)
    branch "decode_group: complete"

end SpecTwin
