"""Mutants of the twin's code for §1 and §2's message_id (`E`), drop_offer (`DROP_OFFER`), §6.4 (`D`) and the
functions from claim_group to validate_chunk (`B1` … `B5`), each changed in one rule. mutants3.py takes `CYCLE1`
into its MUTANTS; `PRED` is what each must be told by, written before any of them is built: the table of
`mutants_c1.py --table` is made from it.

A row: (name, what it changes, file, old, new, D, H, C, why).
- `what` begins with the traced function whose records the mutant is replayed on, or, for a change of
  SpecTwin/Tables.lean, with "the tables:" (its table is in TABLES_OF).
- D: the directed sets (sixteen); H: the hand cell (hand5); C: the fifteen cells. "yes": at least one record there
  tells the mutant. "open": not predicted, to be measured. `why` ends with the replay's kind where one is named.
"""
import sys

SEC1, SEC2, SEC3 = "SpecTwin/Sec1.lean", "SpecTwin/Sec2.lean", "SpecTwin/Sec3.lean"
SEC41, SEC42, SEC43 = "SpecTwin/Sec41.lean", "SpecTwin/Sec42.lean", "SpecTwin/Sec43.lean"
SEC46, SEC64, TABLES = "SpecTwin/Sec46.lean", "SpecTwin/Sec64.lean", "SpecTwin/Tables.lean"

# ---- §1 and §2's message_id
E = [
    ("k-exact-ceiling", "K: an exact ceiling of the quotient", SEC1,
     "match pyCeilDiv d.totalLength d.segmentSize with",
     "match (some ((d.totalLength + d.segmentSize - 1) / d.segmentSize) : Option Nat) with",
     "yes", "no", "no", "directed1's 2^53 + 1 over 1: the Python gives 2^53; a cell's quotients are small and exact (return)"),
    ("k-two-conversions", "K: each operand made a double, then divided", SEC1,
     "match pyCeilDiv d.totalLength d.segmentSize with",
     "match (some (Float.ceil (d.totalLength.toFloat / d.segmentSize.toFloat)).toUInt64.toNat : Option Nat) with",
     "yes", "no", "no", "directed1's pair where two roundings differ from one, and its lengths past 2^64 (return)"),
    ("group-id-prefix", "group_id: 0x03 for 0x02", SEC1,
     'sha256 ("02" ++ (← serialize d))', 'sha256 ("03" ++ (← serialize d))',
     "yes", "yes", "yes", "every group_id: sha256 asked of other bytes (tape)"),
    ("group-key-prefix", "group_key: 0x02 for 0x03", SEC1,
     'sha256 ("03" ++ gid ++ leHex 8 slot)', 'sha256 ("02" ++ gid ++ leHex 8 slot)',
     "yes", "yes", "yes", "every group_key (tape)"),
    ("group-key-slot-order", "group_key: the slot before the id", SEC1,
     'sha256 ("03" ++ gid ++ leHex 8 slot)', 'sha256 ("03" ++ leHex 8 slot ++ gid)',
     "yes", "yes", "yes", "every group_key (tape)"),
    ("group-key-slot-width", "group_key: the slot in 4 bytes", SEC1,
     'sha256 ("03" ++ gid ++ leHex 8 slot)', 'sha256 ("03" ++ gid ++ leHex 4 slot)',
     "yes", "yes", "yes", "every group_key (tape)"),
    ("valid-descriptor-coded-bound", "valid_descriptor: `2K <= MAX_CHUNKS` dropped", SEC1,
     "let r := d.count == k2 && k2 ≤ c.MAX_CHUNKS", "let r := d.count == k2",
     "yes", "no", "no", "directed1's 2K = 258 with the count 258; no cell's group is past the bound (return)"),
    ("valid-descriptor-plain-bound", "valid_descriptor: `K <= MAX_PLAIN_CHUNKS` dropped", SEC1,
     "let r := d.count == k && k ≤ c.MAX_PLAIN_CHUNKS", "let r := d.count == k",
     "yes", "no", "no", "directed1's K = 8193 with the count 8193 (return)"),
    ("valid-descriptor-segment-size-ge", "valid_descriptor: `>=` for `>` at MAX_SEGMENT_SIZE", SEC1,
     "d.segmentSize > c.MAX_SEGMENT_SIZE then", "d.segmentSize ≥ c.MAX_SEGMENT_SIZE then",
     "yes", "no", "no", "directed1's segment size of exactly the bound; a cell's is about UNIT, half of it (return)"),
    ("segment-length-last-test", "segment_length: `i == K` for `i == K - 1`", SEC1,
     "if (i : Int) == ((← K (some d)) : Int) - 1 then", "if (i : Int) == ((← K (some d)) : Int) then",
     "yes", "no", "yes", "a short last data chunk: `none`'s groups (746262 bytes in 64 segments of 11661); hand5's one "
     "segment is the whole, so both lengths are 11660 (return)"),
    ("segment-length-natural", "segment_length: the last length in natural numbers", SEC1,
     "return (d.totalLength : Int) - (((← K (some d)) : Int) - 1) * (d.segmentSize : Int)",
     "return ((d.totalLength - ((← K (some d)) - 1) * d.segmentSize : Nat) : Int)",
     "yes", "no", "no", "directed1's 2^62 + 513 over 1, whose last length is -510; a cell's is positive (return)"),
    ("build-group-coded-bound-lt", "build_group: `2K < MAX_CHUNKS`", SEC1,
     "let coded := 2 * k ≤ c.MAX_CHUNKS", "let coded := 2 * k < c.MAX_CHUNKS",
     "yes", "no", "no", "directed1's body of 128 units: no compression asked; a cell's K is 64 (tape)"),
    ("build-group-slice-unclamped", "build_group: a slice named by the bounds asked, not the clamped ones", SEC1,
     "(List.range k).map fun i => data.slice (i * size) ((i + 1) * size)",
     '(List.range k).map fun i => ({ n := (i + 1) * size - i * size, tag := s!"[{data.tag},{i * size},{(i + 1) * size}]" } : Blob)',
     "yes", "no", "yes", "a short last segment: `none`'s (64 x 11661 is past 746262); hand5's one slice is the whole (tape)"),
    ("message-id-index-width", "message_id: the index in 8 bytes", SEC2,
     "f.g ++ leHex 4 f.i ++ (← contentId f)", "f.g ++ leHex 8 f.i ++ (← contentId f)",
     "yes", "yes", "yes", "every id (return; tape, where the id is asked of)"),
    ("message-id-index-last", "message_id: the index after the content id", SEC2,
     "f.g ++ leHex 4 f.i ++ (← contentId f)", "f.g ++ (← contentId f) ++ leHex 4 f.i",
     "yes", "yes", "yes", "every id (return, tape)"),
]

# ---- drop_offer (§6.1; the twin's own): directed6o alone reaches it
DROP_OFFER = [
    ("drop-offer-bit-kept", "drop_offer: the offered bit kept", SEC42,
     "if b.has i then setOffered p g (b.clear i)", "if false then setOffered p g (b.clear i)",
     "yes", "no", "no", "directed6o; no cell calls drop_offer (state)"),
    ("drop-offer-list-kept", "drop_offer: the peer left in the offers' lists", SEC42,
     "    if o'.isEmpty then eraseOffers a                        -- `if not offers[a]: del offers[a]`\n"
     "    else setOffers a o'\n",
     "    if o'.isEmpty && false then eraseOffers a\n",
     "yes", "no", "no", "directed6o (state)"),
    ("drop-offer-asks-kept", "drop_offer: the asks queued to the peer kept", SEC42,
     "| .iwant ids => .iwant (ids.filter fun b => b.chunk != k)", "| .iwant ids => .iwant (ids.filter fun b => b.chunk != k || true)",
     "yes", "no", "no", "directed6o's lanes with an ask of the chunk (state)"),
    ("drop-offer-empty-entries-kept", "drop_offer: an entry emptied of its asks kept", SEC42,
     "setLane p .normal (filtered.filter (!·.isEmpty))", "setLane p .normal filtered",
     "yes", "no", "no", "directed6o's entries whose one ask goes (state)"),
    ("drop-offer-promise-kept", "drop_offer: the peer's promise not closed", SEC42,
     "closePromises g i (some p)", "pure ()",
     "yes", "no", "no", "directed6o (state, reached)"),
    ("drop-offer-every-promise", "drop_offer: the chunk closed under every key, as if it had arrived", SEC42,
     "closePromises g i (some p)", "closePromises g i none",
     "yes", "no", "no", "directed6o's other peers' promises and the offers (state)"),
]

# ---- §6.4
D = [
    ("pace-stale-gt", "on_pace_tick: `>` for `>=` at the staleness test", SEC64,
     "job.at_ ≥ ctx.c.HEARTBEAT then", "job.at_ > ctx.c.HEARTBEAT then",
     "yes", "no", "no", "directed64's job exactly one heartbeat old; a cell's job is sent within the heartbeat (tape)"),
    ("pace-stale-not-tested", "on_pace_tick: the staleness test left out", SEC64,
     "if ctx.now - Float.ofBits job.at_ ≥ ctx.c.HEARTBEAT then", "if false then",
     "yes", "no", "no", "directed64's stale jobs; `none` and late16 drop none: a heartbeat queues at most 6, a tick sends one (tape)"),
    ("pace-connected-not-asked", "on_pace_tick: `connected` not asked", SEC64,
     "else if !(← connected job.q) then", "else if false then",
     "yes", "no", "yes", "every job that is not stale: `none`'s 20,160 (tape)"),
    ("pace-connected-first", "on_pace_tick: `connected` asked before the staleness test", SEC64,
     "      if ctx.now - Float.ofBits job.at_ ≥ ctx.c.HEARTBEAT then   -- stale\n"
     '        branch "on_pace_tick: a stale job dropped"\n'
     "        paceTurns fuel\n"
     "      else if !(← connected job.q) then                     -- or q has left\n",
     "      let conn ← connected job.q\n"
     "      if ctx.now - Float.ofBits job.at_ ≥ ctx.c.HEARTBEAT then\n"
     '        branch "on_pace_tick: a stale job dropped"\n'
     "        paceTurns fuel\n"
     "      else if !conn then\n",
     "yes", "no", "no", "directed64's stale jobs: asked where the tape has no question; no cell has a stale job (tape)"),
    ("pace-job-not-popped", "on_pace_tick: the job not popped", SEC64,
     "setPaceJobs .jobs rest", "pure ()",
     "yes", "no", "yes", "every tick with a job (state; writes in a cell)"),
    ("pace-last-popped", "on_pace_tick: the last job popped in place of the first", SEC64,
     "    | job :: rest =>\n"
     "      setPaceJobs .jobs rest                                -- `q, ids, at = pace_queue.pop(0)`\n",
     "    | first :: more =>\n"
     "      let job := ((first :: more).getLast?).getD first\n"
     "      let rest := (first :: more).dropLast\n"
     "      setPaceJobs .jobs rest\n",
     "yes", "no", "yes", "two jobs of different peers: a cell's heartbeat queues up to 6 (tape, state)"),
    ("pace-two-jobs-a-tick", "on_pace_tick: the next job sent in the same tick", SEC64,
     "        sendGossip job.q job.ids\n"
     '        branch "on_pace_tick: one job\'s gossip sent"        -- one peer per tick, even if nothing was left to send\n',
     "        sendGossip job.q job.ids\n"
     "        paceTurns fuel\n",
     "yes", "no", "yes", "jobs left after the one sent (tape, state)"),
    ("pace-stops-at-stale", "on_pace_tick: the loop stops at the first stale job", SEC64,
     '        branch "on_pace_tick: a stale job dropped"\n'
     "        paceTurns fuel\n",
     '        branch "on_pace_tick: a stale job dropped"\n',
     "yes", "no", "no", "directed64's stale job before a fresh one (tape, state)"),
    ("pace-fuel-one-short", "on_pace_tick: the fuel one short", SEC64,
     "paceTurns (← paceJobs .jobs).length", "paceTurns ((← paceJobs .jobs).length - 1)",
     "yes", "no", "yes", "a tick with one job left, or every job dropped: a crash where the Python returns (raise)"),
    ("gossip-first-group-alone", "send_gossip: `announce` of the first group alone", SEC64,
     "for (g, bits) in ← groupBits ids do", "for (g, bits) in (← groupBits ids).take 1 do",
     "yes", "no", "open", "directed64's ids of two groups; a cell's three heartbeats of ids span two groups or not: not counted (tape)"),
    ("gossip-other-peer", "send_gossip: `announce` to another peer", SEC64,
     "    announce q g bits", "    announce (q + 1) g bits",
     "yes", "no", "yes", "every job sent with ids (tape)"),
    ("gossip-no-ids", "send_gossip: `group_bits` asked of no ids", SEC64,
     "← groupBits ids do", "← groupBits [] do",
     "yes", "no", "yes", "every job sent with ids (tape)"),
    ("tables-pace-read-no-note", "the tables: a read of pace_queue is not noted", TABLES,
     "  paceJobs e := do note (.read (.paceQueue e)); return (← get).paceQueue.getD e []",
     "  paceJobs e := do return (← get).paceQueue.getD e []",
     "yes", "no", "yes", "every tick and every job queued; hand5 queues none and has no tick (reads)"),
    ("tables-pace-write-none", "the tables: a write of pace_queue notes itself and writes nothing", TABLES,
     "  setPaceJobs e js := do note (.write (.paceQueue e)); modify fun s => { s with paceQueue := s.paceQueue.insert e js }",
     "  setPaceJobs e _ := do note (.write (.paceQueue e))",
     "yes", "no", "yes", "every job queued or popped (state; writes in a cell)"),
    ("heartbeat-frames-not-cleared", "on_heartbeat: ihave_frames not cleared", SEC64,
     "clearIhaveFrames; clearIhaveAsked", "clearIhaveAsked",
     "yes", "yes", "yes", "a heartbeat after an IHAVE: hand5's record 268 and its like (state; writes)"),
    ("heartbeat-asked-not-cleared", "on_heartbeat: ihave_asked not cleared", SEC64,
     "clearIhaveFrames; clearIhaveAsked", "clearIhaveFrames",
     "yes", "yes", "yes", "a heartbeat after an ask on an IHAVE: hand5's record 268 (state; writes)"),
    ("heartbeat-held-back-not-cleared", "on_heartbeat: held_back not cleared", SEC64,
     "\n  clearHeldBack ", "\n  pure () ",
     "yes", "no", "open", "directed64h; of the cells ihave-limits alone sets the limits: whether it holds an ask back to a heartbeat is not counted (state)"),
    ("heartbeat-cleared-before-retries", "on_heartbeat: held_back cleared before the retries", SEC64,
     "  let held ← allHeldBack ", "  clearHeldBack\n  let held ← allHeldBack ",
     "yes", "no", "open", "directed64h: no retry, its questions left; ihave-limits as above (tape)"),
    ("heartbeat-retries-own-order", "on_heartbeat: the retries in the table's order, the node's not asked", SEC64,
     "for k in ← heldBackOrder (held.map (·.1)) do", "for k in held.map (·.1) do",
     "yes", "yes", "yes", "every heartbeat: the order is asked of the node even of nothing (tape)"),
    ("heartbeat-no-stale-waits", "on_heartbeat: drop_stale_waits not called", SEC64,
     "\n  dropStaleWaits ", "\n  pure () ",
     "yes", "yes", "yes", "every heartbeat: its two orders asked of the node (tape, reached)"),
    ("heartbeat-stale-waits-first", "on_heartbeat: drop_stale_waits called before the retries too", SEC64,
     "clearIhaveFrames; clearIhaveAsked", "clearIhaveFrames; clearIhaveAsked; dropStaleWaits",
     "yes", "yes", "yes", "every heartbeat: the tape's order"),
    ("heartbeat-eligible-asked-of-mesh", "on_heartbeat: `gossip_eligible` asked of a mesh peer too", SEC64,
     "    if !(← meshHas q) then                                  --   `gossip_eligible(q)]` (stock: scores)\n"
     "      if ← gossipEligible q then eligible := eligible ++ [q]\n",
     "    let inMesh ← meshHas q\n"
     "    let el ← gossipEligible q\n"
     "    if !inMesh && el then eligible := eligible ++ [q]\n",
     "yes", "yes", "yes", "a topic peer in the mesh: hand5's four at every heartbeat (tape)"),
    ("heartbeat-mesh-not-asked", "on_heartbeat: `q in mesh` not asked", SEC64,
     "if !(← meshHas q) then", "if true then",
     "yes", "yes", "yes", "every topic peer (tape)"),
    ("heartbeat-eligible-reversed", "on_heartbeat: the eligible peers in reverse", SEC64,
     "if ← gossipEligible q then eligible := eligible ++ [q]", "if ← gossipEligible q then eligible := q :: eligible",
     "yes", "no", "yes", "two eligible peers: the draw's argument; hand5 has none (tape)"),
    ("gossip-count-max-for-min", "on_heartbeat: `max` for `min` in the count", SEC64,
     "return min len (max c.D_LAZY k)", "return max len (max c.D_LAZY k)",
     "yes", "yes", "yes", "fewer eligible than D_LAZY: hand5's none gives a draw of 6 (tape)"),
    ("gossip-count-min-for-max", "on_heartbeat: `min` for `max` in the count", SEC64,
     "return min len (max c.D_LAZY k)", "return min len (min c.D_LAZY k)",
     "yes", "no", "yes", "eligible peers whose share is below D_LAZY: the draw's count; of none it is 0 either way (tape)"),
    ("gossip-count-share-rounded-up", "on_heartbeat: the share rounded up", SEC64,
     "Float.floor (c.GOSSIP_FACTOR * len.toFloat)", "Float.ceil (c.GOSSIP_FACTOR * len.toFloat)",
     "yes", "no", "no", "directed64h's shares that are no whole number and exceed D_LAZY; a cell's share is below D_LAZY (tape)"),
    ("gossip-count-no-lazy", "on_heartbeat: D_LAZY left out of the count", SEC64,
     "return min len (max c.D_LAZY k)", "return min len k",
     "yes", "no", "yes", "eligible peers whose share is below D_LAZY (tape)"),
    ("heartbeat-paced-always", "on_heartbeat: paced whatever PACED says", SEC64,
     "\n    if ctx.c.PACED then", "\n    if true then",
     "yes", "no", "open", "directed64h's node 2, PACED off; `none` and late16 are paced: a cell with the card off is not counted (tape, state)"),
    ("heartbeat-job-time-zero", "on_heartbeat: a job's time zero", SEC64,
     "at_ := ctx.now.toBits }", "at_ := 0 }",
     "yes", "no", "yes", "every job queued (state; writes)"),
    ("heartbeat-job-first", "on_heartbeat: a job put first in the queue", SEC64,
     "((← paceJobs .jobs) ++ [{ q, ids, at_ := ctx.now.toBits }])",
     "(([{ q, ids, at_ := ctx.now.toBits }] : List Job) ++ (← paceJobs .jobs))",
     "yes", "no", "yes", "a heartbeat's second job (state; writes)"),
    ("tables-frames-clear-no-note", "the tables: the clear of ihave_frames notes nothing", TABLES,
     "  clearIhaveFrames := do\n"
     "    for (p, _) in (← get).ihaveFrames.toList do note (.write (.ihaveFrames p))\n",
     "  clearIhaveFrames := do\n",
     "yes", "yes", "yes", "a heartbeat that clears a count: hand5's record 268 (writes)"),
    ("tables-asked-clear-no-note", "the tables: the clear of ihave_asked notes nothing", TABLES,
     "  clearIhaveAsked := do\n"
     "    for (p, _) in (← get).ihaveAsked.toList do note (.write (.ihaveAsked p))\n",
     "  clearIhaveAsked := do\n",
     "yes", "yes", "yes", "the same (writes)"),
    ("tables-heldback-clear-no-note", "the tables: the clear of held_back notes nothing", TABLES,
     "  clearHeldBack := do\n"
     "    for (k, _) in (← get).heldBack.toList do note (.write (.heldBack k))\n",
     "  clearHeldBack := do\n",
     "yes", "no", "open", "directed64h; ihave-limits as above (writes)"),
]

# ---- claim_group and drop_group; stop_pull
B1 = [
    ("claim-stop-pull-not-set", "claim_group: stop_pull not set", SEC42,
     "  setStopPull g true                                        -- [c6]", "  pure ()                                                   -- [c6]",
     "yes", "yes", "yes", "every claim: hand5's four (state; writes)"),
    ("claim-mine-received", "claim_group: mine set to the bits received, not all", SEC42,
     "setMine g ((1 <<< (← N (← desc g))) - 1)", "setMine g (← receivedBits g)",
     "yes", "yes", "yes", "every claim: the HAVE's bits (tape, state)"),
    ("claim-all-bits-of-k", "claim_group: all bits of K, not N", SEC42,
     "setMine g ((1 <<< (← N (← desc g))) - 1)", "setMine g ((1 <<< (← K (← desc g))) - 1)",
     "yes", "yes", "yes", "every claim of a coded group (tape, state)"),
    ("claim-haves-before-mine", "claim_group: the HAVEs before mine is set", SEC42,
     "  setMine g ((1 <<< (← N (← desc g))) - 1)                  -- [c10] `mine[g] = all_bits(N(desc[g]))`\n"
     "  for q in ← meshList do sendHave q g                       -- [c10] the decode claim: all N bits\n",
     "  for q in ← meshList do sendHave q g\n"
     "  setMine g ((1 <<< (← N (← desc g))) - 1)\n",
     "yes", "yes", "yes", "every claim with a mesh: the HAVE's bits (tape)"),
    ("claim-mesh-sorted", "claim_group: the mesh sorted", SEC42,
     "for q in ← meshList do sendHave q g                       -- [c10]", "for q in (← meshList).mergeSort do sendHave q g                       -- [c10]",
     "yes", "no", "open", "directed46's mesh drawn in another order; hand5's is in order; a cell's, not counted (tape)"),
    ("claim-have-first-peer-alone", "claim_group: a HAVE to the first mesh peer alone", SEC42,
     "for q in ← meshList do sendHave q g                       -- [c10]", "for q in (← meshList).take 1 do sendHave q g                       -- [c10]",
     "yes", "yes", "yes", "a mesh of two or more (tape)"),
    ("claim-promises-not-closed", "claim_group: close_promises_of_group not called", SEC42,
     "  closePromisesOfGroup g                                    -- [c5]", "  pure ()                                                   -- [c5]",
     "yes", "yes", "yes", "every claim (tape)"),
    ("drop-group-promises-not-closed", "drop_group: close_promises_of_group not called", SEC46,
     "  closePromisesOfGroup g                                    -- its announcers", "  pure ()                                                   -- its announcers",
     "yes", "no", "no", "directed46 and directed46d; no decode fails in hand5, `none` or late16, and no cell has a builder at fault (tape)"),
    ("drop-group-state-complete", "drop_group: the state set COMPLETE", SEC46,
     "setState g .invalid", "setState g .complete",
     "yes", "no", "no", "the same (state)"),
    ("drop-group-stop-pull-not-set", "drop_group: stop_pull not set", SEC46,
     "  setStopPull g true                                        -- `stop_pull[g] = True`", "  pure ()",
     "yes", "no", "no", "directed46's groups dropped with stop_pull unset (state; writes)"),
    ("drop-group-discard-after-history", "drop_group: discard_queued after the gossip history", SEC46,
     "  discardQueued g                                           -- g's chunks, IHAVEs and IWANTs in every queue, and\n"
     "                                                            --   what is owed of g; HAVEs stay\n"
     "  gossipRemoveGroup g                                       -- no further heartbeat announcements of g\n",
     "  gossipRemoveGroup g\n"
     "  discardQueued g\n",
     "yes", "no", "no", "the tape's order"),
    ("drop-group-paced-not-discarded", "drop_group: discard_paced not called", SEC46,
     "  discardPaced g ", "  pure () ",
     "yes", "no", "no", "the tape"),
    ("tables-stop-pull-read-false", "the tables: a read of stop_pull notes nothing and answers false", TABLES,
     "  stopPull g := do note (.read (.stopPull g)); return (← get).stopPull.contains g",
     "  stopPull _ := do return false",
     "yes", "yes", "yes", "every `gated`: hand5's ask (reads; return where the group is claimed)"),
    ("tables-stop-pull-write-no-note", "the tables: a write of stop_pull is not noted", TABLES,
     "  setStopPull g armed := do\n    note (.write (.stopPull g))\n",
     "  setStopPull g armed := do\n",
     "yes", "yes", "yes", "every claim (writes)"),
]

# ---- on_have; peer_has and holders
B2 = [
    ("have-expiry-not-asked", "on_have: the expiry not asked", SEC43,
     "  if ← expired g then                                       -- past its active lifetime (§8.1): ignored", "  if false then",
     "yes", "yes", "yes", "every HAVE (tape)"),
    ("have-invalid-taken", "on_have: an invalid HAVE taken", SEC43,
     "if !(← validHave g bits) then", "if !(← validHave g bits) && false then",
     "yes", "no", "no", "directed43's invalid HAVEs; an honest node sends none (state, tape)"),
    ("have-invalid-not-penalised", "on_have: the sender of an invalid HAVE not penalised", SEC43,
     '    penalise p\n    branch "on_have: not a valid HAVE"; return\n',
     '    branch "on_have: not a valid HAVE"; return\n',
     "yes", "no", "no", "the same (tape)"),
    ("have-newly-all-bits", "on_have: the new bits those of the HAVE, not those the entry lacks", SEC43,
     "let newly := bits.minus e.bits", "let newly := bits",
     "yes", "yes", "yes", "a HAVE with a bit the entry had: hand5's 16 with nothing new, and every second HAVE of a peer (tape)"),
    ("have-bits-replaced", "on_have: the entry's bits replaced, not joined", SEC43,
     "{ bits := e.bits ||| bits, ttl := (← read).c.HAVE_TTL }", "{ bits := bits, ttl := (← read).c.HAVE_TTL }",
     "yes", "no", "no", "directed43's HAVEs that lack a bit the entry has; a node's HAVEs only grow, and arrive in order (state)"),
    ("have-ttl-not-refreshed-nothing-new", "on_have: the ttl not refreshed where nothing is new", SEC43,
     "  setPeerHas p g { bits := e.bits ||| bits, ttl := (← read).c.HAVE_TTL }",
     "  let fresh := (← read).c.HAVE_TTL\n  setPeerHas p g { bits := e.bits ||| bits, ttl := if newly == 0 then e.ttl else fresh }",
     "yes", "no", "open", "directed43's entries with another ttl; hand5's HAVEs all come before a heartbeat counts one down; a cell's repeat after a heartbeat, not counted (state)"),
    ("have-ttl-kept", "on_have: the ttl kept where the entry had bits", SEC43,
     "  setPeerHas p g { bits := e.bits ||| bits, ttl := (← read).c.HAVE_TTL }",
     "  let fresh := (← read).c.HAVE_TTL\n  setPeerHas p g { bits := e.bits ||| bits, ttl := if e.bits == 0 then fresh else e.ttl }",
     "yes", "no", "open", "the same (state)"),
    ("have-holder-not-added", "on_have: the peer not added to the holders", SEC43,
     "setHolders g i ((← holdersOf g i).insert p)", "setHolders g i (← holdersOf g i)",
     "yes", "yes", "yes", "every new index: hand5's record 131 (state; writes)"),
    ("have-release-after-ack", "on_have: window_release after the origin's question", SEC43,
     "    windowRelease p g i                                     -- [c14] a slot to p frees when p holds i, from anyone\n"
     "    if ← planned g then originAcked g i                     -- [c3, P4] a copy of i exists elsewhere (§5.1)\n",
     "    if ← planned g then originAcked g i\n"
     "    windowRelease p g i\n",
     "yes", "yes", "yes", "every new index (the tape's order)"),
    ("have-ack-unplanned", "on_have: origin_acked whatever `planned` says", SEC43,
     "if ← planned g then originAcked g i", "if (← planned g) || true then originAcked g i",
     "yes", "yes", "yes", "a new index of a group the node does not publish: hand5's record 131 (tape)"),
    ("have-planned-once", "on_have: `planned` asked once, before the loop", SEC43,
     "  for i in newly.toList do\n"
     "    setHolders g i ((← holdersOf g i).insert p)             -- [c9] distinct live holders\n"
     "    windowRelease p g i                                     -- [c14] a slot to p frees when p holds i, from anyone\n"
     "    if ← planned g then originAcked g i                     -- [c3, P4] a copy of i exists elsewhere (§5.1)\n",
     "  let pl ← planned g\n"
     "  for i in newly.toList do\n"
     "    setHolders g i ((← holdersOf g i).insert p)\n"
     "    windowRelease p g i\n"
     "    if pl then originAcked g i\n",
     "yes", "yes", "yes", "a HAVE with nothing new: asked where the tape has no question; hand5's 16 (tape)"),
    ("have-new-indices-downward", "on_have: the new indices downward", SEC43,
     "for i in newly.toList do", "for i in newly.toList.reverse do",
     "yes", "open", "yes", "a HAVE with two new indices: a decode claim in a cell; whether a hand5 HAVE brings two at once is not counted (the tape's order)"),
    ("tables-peer-has-read-none", "the tables: a read of peer_has notes itself and answers none", TABLES,
     "  peerHasEntry? p g := do note (.read (.peerHas p g)); return ((← get).peerHas.getD p {}).get? g",
     "  peerHasEntry? p g := do note (.read (.peerHas p g)); return none",
     "yes", "yes", "yes", "a peer's second HAVE; the writer's and the decode's reads of what a peer claimed (tape, state)"),
    ("tables-peer-has-write-none", "the tables: a write of peer_has notes itself and writes nothing", TABLES,
     "  setPeerHas p g e := do\n"
     "    note (.write (.peerHas p g))\n"
     "    modify fun s => { s with peerHas := s.peerHas.insert p ((s.peerHas.getD p {}).insert g e) }\n",
     "  setPeerHas p g _ := do\n"
     "    note (.write (.peerHas p g))\n",
     "yes", "yes", "yes", "every valid HAVE (state; writes)"),
    ("tables-holders-read-no-note", "the tables: a read of holders is not noted", TABLES,
     "  holdersOf g i := do note (.read (.holders g i)); return ((← get).holders.getD g {}).getD i {}",
     "  holdersOf g i := do return ((← get).holders.getD g {}).getD i {}",
     "yes", "yes", "yes", "every new index of a HAVE (reads)"),
    ("tables-holders-write-none", "the tables: a write of holders notes itself and writes nothing", TABLES,
     "  setHolders g i ps := do\n"
     "    note (.write (.holders g i))\n"
     "    modify fun s => { s with holders := s.holders.insert g ((s.holders.getD g {}).insert i ps) }\n",
     "  setHolders g i _ := do\n"
     "    note (.write (.holders g i))\n",
     "yes", "yes", "yes", "every new index (state; writes)"),
]

# ---- on_iwant, respond and on_frame
B3 = [
    ("iwant-expiry-not-asked", "on_iwant: the expiry not asked", SEC41,
     "    if ← expired a.group then                               -- past its active lifetime: ignored, no penalty", "    if false then",
     "yes", "yes", "yes", "every ask: hand5's one (tape)"),
    ("iwant-claimed-answered", "on_iwant: an ask of a chunk the asker claimed answered", SEC41,
     "if (← peerHas p a.group).has a.index then", "if (← peerHas p a.group).has a.index && false then",
     "yes", "no", "no", "directed41; on a live connection an honest ask comes before the claim (tape)"),
    ("iwant-claimed-not-penalised", "on_iwant: the asker of a chunk it claimed not penalised", SEC41,
     "      penalise p                                            -- it asks for a chunk it claimed: dropped\n", "",
     "yes", "no", "no", "the same (tape)"),
    ("iwant-unwanted-not-read", "on_iwant: `unwanted` not read", SEC41,
     "if (← unwantedOf p).contains mid.idHex then", "if false then",
     "yes", "yes", "yes", "every ask the node can answer (`unwanted` is the twin's own: by the read the twin does "
     "not make; and in directed41 by an ask of an id the peer does not want: the tape)"),
    ("iwant-count-not-written", "on_iwant: the count not written", SEC41,
     "      setServeCount p mid n\n", "",
     "yes", "yes", "yes", "every ask the node can answer (state; writes)"),
    ("iwant-limit-ge", "on_iwant: `>=` for `>` at the limit", SEC41,
     "if n > (← read).c.GOSSIP_RETRANSMISSION then", "if n ≥ (← read).c.GOSSIP_RETRANSMISSION then",
     "yes", "no", "open", "directed41's id served exactly the limit; a cell's third ask of one id to one peer, not counted (return)"),
    ("iwant-count-after-limit", "on_iwant: the count written after the limit's test only", SEC41,
     "      setServeCount p mid n\n"
     "      if n > (← read).c.GOSSIP_RETRANSMISSION then          -- stock: 3 answers per id per peer\n"
     '        branch "on_iwant: served too often"\n'
     "        continue\n",
     "      if n > (← read).c.GOSSIP_RETRANSMISSION then\n"
     '        branch "on_iwant: served too often"\n'
     "        continue\n"
     "      setServeCount p mid n\n",
     "yes", "no", "open", "directed41's asks past the limit; a cell's fourth, not counted (state)"),
    ("iwant-twice-answered-twice", "on_iwant: an id asked twice in a frame answered twice", SEC41,
     "      answers := if answers.any (·.1 == mid) then answers.map fun (k, v) => if k == mid then (k, f) else (k, v)\n"
     "                 else answers ++ [(mid, f)]\n",
     "      answers := answers ++ [(mid, f)]\n",
     "yes", "no", "no", "directed41's frames; an honest IWANT names a chunk once (tape)"),
    ("iwant-answers-reversed", "on_iwant: the answers in reverse", SEC41,
     "return answers.map (·.2)", "return answers.reverse.map (·.2)",
     "yes", "no", "yes", "a frame with two answers: `none` has 13,530 answers in 13,526 frames (tape)"),
    ("iwant-later-answer-later-place", "on_iwant: an id asked again takes the later place", SEC41,
     "      answers := if answers.any (·.1 == mid) then answers.map fun (k, v) => if k == mid then (k, f) else (k, v)\n"
     "                 else answers ++ [(mid, f)]\n",
     "      answers := (answers.filter (·.1 != mid)) ++ [(mid, f)]\n",
     "yes", "no", "no", "directed41's three asks, the first id again last (tape)"),
    ("respond-control-on-every-answer", "respond: the control on every answer", SEC41,
     "control := if first then control else none, solicited := true }", "control := control, solicited := true }",
     "yes", "no", "open", "directed41's two answers with a control; a cell's frame with two answers and an ask or a prune, not counted (tape)"),
    ("respond-control-not-on-first", "respond: the control on every answer but the first", SEC41,
     "control := if first then control else none, solicited := true }", "control := if first then none else control, solicited := true }",
     "yes", "no", "open", "an answer with a control; a cell's frame with an answer and an ask or a prune, not counted (tape)"),
    ("respond-no-prune-part", "respond: no PRUNE part", SEC41,
     "some [.iwant asks, .prune]", "some [.iwant asks]",
     "yes", "yes", "yes", "every control: hand5's one, record 133 (tape)"),
    ("respond-control-own-entry", "respond: with answers, the control as an entry of its own", SEC41,
     "  let mut first := true\n",
     "  if control.isSome then\n"
     "    let _ ← enqueue p (.entry { chunk := none, control, solicited := false }) false\n"
     "  let mut first := false\n",
     "yes", "no", "open", "as respond-control-not-on-first (tape)"),
    ("respond-answer-unsolicited", "respond: an answer not marked solicited", SEC41,
     "control := if first then control else none, solicited := true }", "control := if first then control else none, solicited := false }",
     "yes", "yes", "yes", "every answer: hand5's one, record 142 (tape)"),
    ("respond-refused-not-owed", "respond: a refused answer not owed", SEC41,
     "setOwedAnswers p f.g ((← owedAnswerBits p f.g).set f.i)", "pure ()",
     "yes", "no", "yes", "directed41's refusals; loss-thin's owed answers (state; writes)"),
    ("respond-refused-owed-next-index", "respond: a refused answer owed under the next index", SEC41,
     "setOwedAnswers p f.g ((← owedAnswerBits p f.g).set f.i)", "setOwedAnswers p f.g ((← owedAnswerBits p f.g).set (f.i + 1))",
     "yes", "no", "yes", "the same (state; writes)"),
    ("respond-urgent", "respond: an answer queued urgent", SEC41,
     "if !(← enqueue p (.entry e) false) then", "if !(← enqueue p (.entry e) true) then",
     "yes", "yes", "yes", "every answer (tape)"),
    ("frame-haves-before-iwant", "on_frame: the HAVEs before the IWANT", SEC41,
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant    -- §4.5; or the node\'s own\n'
     "                else onIwant p fr.iwant\n"
     "  let prunes ← handleGraftPrune p                           -- stock\n"
     "  for h in fr.idontwant do                                  -- §4.3: a HAVE bitmap (§2); any other entry is an\n"
     "    match h with                                            --   opaque id, kept with stock's admission and\n"
     "    | .bitmap g bits => onHave p g bits                     --   lifetime (§8.1)\n"
     "    | .id a => setUnwanted p ((← unwantedOf p).insert a.idHex)      -- `unwanted[p].add(h)`\n"
     "    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)\n",
     "  for h in fr.idontwant do\n"
     "    match h with\n"
     "    | .bitmap g bits => onHave p g bits\n"
     "    | .id a => setUnwanted p ((← unwantedOf p).insert a.idHex)\n"
     "    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)\n"
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant\n'
     "                else onIwant p fr.iwant\n"
     "  let prunes ← handleGraftPrune p\n",
     "yes", "yes", "yes", "a frame with a HAVE: its questions before the prunes' (the tape's order); directed41's ask and HAVE of one chunk"),
    ("frame-ihave-after-iwant", "on_frame: the IHAVE after the IWANT", SEC41,
     "  let asks ← onIhave p fr.ihave                             -- §4.4\n"
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant    -- §4.5; or the node\'s own\n'
     "                else onIwant p fr.iwant\n",
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant\n'
     "                else onIwant p fr.iwant\n"
     "  let asks ← onIhave p fr.ihave\n",
     "yes", "yes", "yes", "a frame with an IWANT: hand5's record 142 (the tape's order)"),
    ("frame-chunks-after-control", "on_frame: the chunks after the control", SEC41,
     "  for f in fr.chunks do onChunk p f                         -- §4.2\n"
     "  let asks ← onIhave p fr.ihave                             -- §4.4\n"
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant    -- §4.5; or the node\'s own\n'
     "                else onIwant p fr.iwant\n"
     "  let prunes ← handleGraftPrune p                           -- stock\n"
     "  for h in fr.idontwant do                                  -- §4.3: a HAVE bitmap (§2); any other entry is an\n"
     "    match h with                                            --   opaque id, kept with stock's admission and\n"
     "    | .bitmap g bits => onHave p g bits                     --   lifetime (§8.1)\n"
     "    | .id a => setUnwanted p ((← unwantedOf p).insert a.idHex)      -- `unwanted[p].add(h)`\n"
     "    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)\n",
     "  let asks ← onIhave p fr.ihave\n"
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant\n'
     "                else onIwant p fr.iwant\n"
     "  let prunes ← handleGraftPrune p\n"
     "  for h in fr.idontwant do\n"
     "    match h with\n"
     "    | .bitmap g bits => onHave p g bits\n"
     "    | .id a => setUnwanted p ((← unwantedOf p).insert a.idHex)\n"
     "    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)\n"
     "  for f in fr.chunks do onChunk p f\n",
     "yes", "yes", "yes", "a frame with a chunk (the tape's order)"),
    ("frame-own-iwant-not-asked", "on_frame: the node's own on_iwant not asked where it has one", SEC41,
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant    -- §4.5; or the node\'s own\n'
     "                else onIwant p fr.iwant\n",
     "  let answers ← onIwant p fr.iwant\n",
     "yes", "no", "open", "directed41's node 3; a cell whose nodes answer otherwise (withholders, silent), not counted (tape)"),
    ("frame-node-iwant-always", "on_frame: the node asked for the answers where it runs the document's", SEC41,
     '  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant    -- §4.5; or the node\'s own\n'
     "                else onIwant p fr.iwant\n",
     "  let answers ← onIwantNode p fr.iwant\n",
     "yes", "yes", "yes", "every frame of a node that runs the document's (tape, reached)"),
    ("frame-no-empty-respond", "on_frame: respond not called for an empty response", SEC41,
     "  respond p asks answers prunes\n",
     "  if !asks.isEmpty || !answers.isEmpty || prunes > 0 then respond p asks answers prunes\n",
     "yes", "yes", "yes", "a frame with nothing to ask, answer or prune: hand5's 86 (reached)"),
    ("tables-serve-count-read-no-note", "the tables: a read of serve_count is not noted", TABLES,
     "  serveCount p m := do note (.read (.serveCount p m)); return ((← get).serveCount.getD p {}).getD m 0",
     "  serveCount p m := do return ((← get).serveCount.getD p {}).getD m 0",
     "yes", "yes", "yes", "every ask the node can answer (reads)"),
    ("tables-serve-count-write-none", "the tables: a write of serve_count notes itself and writes nothing", TABLES,
     "  setServeCount p m n := do\n"
     "    note (.write (.serveCount p m))\n"
     "    modify fun s => { s with serveCount := s.serveCount.insert p ((s.serveCount.getD p {}).insert m n) }\n",
     "  setServeCount p m _ := do\n"
     "    note (.write (.serveCount p m))\n",
     "yes", "yes", "yes", "the same (state; writes)"),
    ("tables-owed-answers-write-none", "the tables: a write of owed_answers notes itself and writes nothing", TABLES,
     "  setOwedAnswers p g b := do\n"
     "    note (.write (.owedAnswers p g))\n"
     "    modify fun s => { s with owedAnswers := s.owedAnswers.insert p ((s.owedAnswers.getD p {}).insert g b) }\n",
     "  setOwedAnswers p g _ := do\n"
     "    note (.write (.owedAnswers p g))\n",
     "yes", "no", "yes", "a refused answer: directed41's; loss-thin's (state; writes)"),
]

# ---- decode_group and push_rebuilt
B4 = [
    ("decode-expiry-not-asked", "decode_group: the expiry not asked", SEC46,
     "  if ← expired g then                                       -- the group passed its lifetime meanwhile (§8.1)", "  if false then",
     "yes", "yes", "yes", "every decode: hand5's four (tape)"),
    ("decode-expiry-before-decode", "decode_group: the expiry asked before the decode", SEC46,
     "  let rebuilt ← decodeAndReencode g d                       -- any K chunks -> all N, or None if the root differs\n"
     "  if ← expired g then                                       -- the group passed its lifetime meanwhile (§8.1)\n"
     '    branch "decode_group: expired meanwhile"; return\n',
     "  if ← expired g then\n"
     '    branch "decode_group: expired meanwhile"; return\n'
     "  let rebuilt ← decodeAndReencode g d\n",
     "yes", "yes", "yes", "every decode (the tape's order)"),
    ("decode-new-all", "decode_group: every rebuilt chunk taken as new, received or not", SEC46,
     "if !(← receivedBits g).has i then new := new ++ [i]", "if !(← receivedBits g).has i || true then new := new ++ [i]",
     "yes", "yes", "yes", "a decode with a chunk received: each is stored again (tape)"),
    ("decode-not-stored", "decode_group: the rebuilt chunks not stored", SEC46,
     "if new.contains i then store g i f", "if new.contains i && false then store g i f",
     "yes", "yes", "yes", "a decode that rebuilds a chunk (tape)"),
    ("decode-state-not-complete", "decode_group: the state not set COMPLETE", SEC46,
     "    setState g .complete\n", "",
     "yes", "yes", "yes", "every decode that passes (state; writes)"),
    ("decode-deliver-before-push", "decode_group: delivered before the repair", SEC46,
     '    if (← read).replaced.contains "push_rebuilt" then pushRebuiltNode g new      -- [c10] repair; or the node\'s own\n'
     "    else pushRebuilt g new\n"
     "    deliver g (← payloadOf chunks)                          -- level 3: the application's checks (§3)\n",
     "    deliver g (← payloadOf chunks)\n"
     '    if (← read).replaced.contains "push_rebuilt" then pushRebuiltNode g new\n'
     "    else pushRebuilt g new\n",
     "yes", "yes", "yes", "every decode that passes (the tape's order)"),
    ("decode-no-deliver", "decode_group: not delivered", SEC46,
     "deliver g (← payloadOf chunks)", "let _ ← payloadOf chunks",
     "yes", "yes", "yes", "every decode that passes (tape)"),
    ("decode-root-differs-not-dropped", "decode_group: a group whose root differs not dropped", SEC46,
     "    dropGroup g                                             -- an inconsistent code: the builder's fault\n", "",
     "yes", "no", "no", "directed46d's decodes that give nothing; no decode fails in hand5, `none` or late16 (state, tape, reached)"),
    ("decode-own-push-not-asked", "decode_group: the node's own repair not asked where it has one", SEC46,
     '    if (← read).replaced.contains "push_rebuilt" then pushRebuiltNode g new      -- [c10] repair; or the node\'s own\n'
     "    else pushRebuilt g new\n",
     "    pushRebuilt g new\n",
     "yes", "no", "yes", "directed46d's node 3; `none`, whose nodes run their own (tape, reached)"),
    ("decode-node-push-always", "decode_group: the node asked for the repair where it runs the document's", SEC46,
     '    if (← read).replaced.contains "push_rebuilt" then pushRebuiltNode g new      -- [c10] repair; or the node\'s own\n'
     "    else pushRebuilt g new\n",
     "    pushRebuiltNode g new\n",
     "yes", "yes", "yes", "every decode of a node that runs the document's: hand5's four, late16's 30 (tape, reached)"),
    ("decode-new-reversed", "decode_group: the new indices in reverse", SEC46,
     "if !(← receivedBits g).has i then new := new ++ [i]", "if !(← receivedBits g).has i then new := [i] ++ new",
     "yes", "no", "yes", "two new indices and a peer short: the draw's argument; hand5's decodes rebuild one (tape)"),
    ("push-rebuilt-mesh-not-shuffled", "push_rebuilt: the mesh not shuffled", SEC46,
     "for q in ← shuffledNats (← meshList) do", "for q in ← meshList do",
     "yes", "yes", "yes", "every repair (tape)"),
    ("push-rebuilt-pushed-not-counted", "push_rebuilt: what was pushed to the peer not counted as known", SEC46,
     "let known := (← peerHas q g) ||| (← pushed q g)", "let known := (← peerHas q g) ||| ((← pushed q g) &&& 0)",
     "yes", "no", "yes", "a mesh peer pushed a chunk before the decode: late16's forwards; hand5's four repairs find nothing pushed (tape)"),
    ("push-rebuilt-claimed-not-counted", "push_rebuilt: what the peer claimed not counted as known", SEC46,
     "let known := (← peerHas q g) ||| (← pushed q g)", "let known := ((← peerHas q g) &&& 0) ||| (← pushed q g)",
     "yes", "yes", "yes", "a mesh peer that claimed: hand5's record 178, peer 4 (tape)"),
    ("push-rebuilt-short-of-n", "push_rebuilt: the shortfall against N, not K", SEC46,
     "let short : Int := ((← K (← desc g)) : Int) - known.popcount", "let short : Int := ((← N (← desc g)) : Int) - known.popcount",
     "yes", "yes", "yes", "a peer that knows K and not N: hand5's record 178, peer 1 (tape, reached)"),
    ("push-rebuilt-short-lt", "push_rebuilt: a peer short of nothing drawn for", SEC46,
     "if short ≤ 0 then", "if short < 0 then",
     "yes", "yes", "yes", "a peer that knows exactly K: hand5's record 178, peer 1: the draw asked (tape)"),
    ("push-rebuilt-lacks-not-shuffled", "push_rebuilt: what the peer lacks not shuffled", SEC46,
     "let lacks ← shuffledNats (new.filter fun i => !known.has i)", "let lacks := new.filter fun i => !known.has i",
     "yes", "yes", "yes", "every short peer (tape)"),
    ("push-rebuilt-lacks-all-new", "push_rebuilt: every new index drawn, known to the peer or not", SEC46,
     "shuffledNats (new.filter fun i => !known.has i)", "shuffledNats new",
     "yes", "no", "yes", "a short peer that knows a new index: late16's; hand5's short peers know nothing (tape)"),
    ("push-rebuilt-all-lacks", "push_rebuilt: all the peer lacks pushed, not its shortfall", SEC46,
     "for i in lacks.take short.toNat do", "for i in lacks do",
     "yes", "no", "yes", "a peer that lacks more than it is short of: late16's; hand5's lack one and are short one (tape)"),
    ("push-rebuilt-not-noted", "push_rebuilt: a push not noted", SEC46,
     "        notePush q g i\n", "        pure ()\n",
     "yes", "yes", "yes", "every push (tape)"),
    ("push-rebuilt-refused-not-owed", "push_rebuilt: a refused push not owed", SEC46,
     "        owe q g (1 <<< i) ", "        pure () ",
     "yes", "no", "open", "directed46d's refusals (15%); a cell's queue that refuses a repair push, not counted (tape)"),
    ("push-rebuilt-urgent", "push_rebuilt: a push queued urgent", SEC46,
     "if ← enqueue q (.chunk (← chunkAt g i)) false then", "if ← enqueue q (.chunk (← chunkAt g i)) true then",
     "yes", "yes", "yes", "every push (tape)"),
]

# ---- level 1: told by directed3v and the cells. In directed42 and directed4b level 1 is a question of the node,
# so no record there runs this code: the one mutant those two tell is the last, which takes the question away.
B5 = [
    ("validate-no-block-accepted", "validate_chunk: a chunk with no block accepted", SEC3,
     'do branch "validate_chunk: no block yet"; return .defer', 'do branch "validate_chunk: no block yet"; return .accept',
     "yes", "no", "yes", "directed3v; late-block's deferrals (late16: 326); hand5's blocks are all there. Not directed42 or 4b (return)"),
    ("validate-slot-not-compared", "validate_chunk: the slot not compared", SEC3,
     "if f.slot != block.slot then", "if false then",
     "yes", "no", "no", "directed3v's block of another slot; an honest copy names its block's. Not directed42 or 4b (return)"),
    ("validate-key-not-compared", "validate_chunk: the group's key not compared", SEC3,
     "if (← groupKey (← groupId d) block.slot) != f.g then", "if (← groupKey (← groupId d) block.slot) != f.g && false then",
     "yes", "no", "no", "directed3v's copy under another group's name. Not directed42 or 4b (return)"),
    ("validate-validity-not-read", "validate_chunk: the descriptor's validity not read", SEC3,
     "if !(← validDescriptor d) then", "if false then",
     "yes", "yes", "yes", "every chunk that reaches it: valid_descriptor not entered (reached); directed3v's committed descriptor that is not valid (return). Not directed42 or 4b"),
    ("validate-validity-before-key", "validate_chunk: validity read before the key", SEC3,
     "  if (← groupKey (← groupId d) block.slot) != f.g then\n"
     '    branch "validate_chunk: not the group\'s key"; return .reject\n'
     "  if !(← validDescriptor d) then\n"
     '    branch "validate_chunk: not a valid descriptor"; return .reject\n',
     "  if !(← validDescriptor d) then\n"
     '    branch "validate_chunk: not a valid descriptor"; return .reject\n'
     "  if (← groupKey (← groupId d) block.slot) != f.g then\n"
     '    branch "validate_chunk: not the group\'s key"; return .reject\n',
     "yes", "no", "no", "directed3v's descriptor that is not valid: the key's hashes not asked (tape). Not directed42 or 4b"),
    ("validate-count-gt", "validate_chunk: `>` for `>=` at the count", SEC3,
     "if f.i ≥ d.count then", "if f.i > d.count then",
     "yes", "no", "no", "directed3v's index at the count (return, tape). Not directed42 or 4b"),
    ("validate-length-not-compared", "validate_chunk: the length not compared", SEC3,
     "if (w.data.n : Int) != (← segmentLength d f.i) then", "if (w.data.n : Int) != (← segmentLength d f.i) && false then",
     "yes", "no", "no", "directed3v's data longer or shorter than its segment (tape, return). Not directed42 or 4b"),
    ("validate-proof-not-asked", "validate_chunk: the proof not asked", SEC3,
     "if !(← verifyMerkleProof d.root w.data f.i d.count w.proof) then", "if false then",
     "yes", "yes", "yes", "every chunk that reaches the proof: hand5's eight (tape). Not directed42 or 4b"),
    ("validate-proof-of-segment-size", "validate_chunk: the proof asked of the segment size, not the count", SEC3,
     "verifyMerkleProof d.root w.data f.i d.count w.proof", "verifyMerkleProof d.root w.data f.i d.segmentSize w.proof",
     "yes", "yes", "yes", "the same: the question's argument (tape). Not directed42 or 4b"),
    # (the three of committed_descriptor that name the chunk's descriptor follow the twin's text, where `w.desc` is
    # optional and is bound as `fd`)
    ("committed-id-not-compared", "committed_descriptor: the bid's id not compared (design A)", SEC3,
     "let ok := some (← groupId fd) == block.groupId", "let ok := some (← groupId fd) == block.groupId || true",
     "yes", "no", "no", "directed3v's chunk whose descriptor the bid does not commit. Not directed42 or 4b (return)"),
    ("committed-chunk-descriptor-under-b", "committed_descriptor: the chunk's descriptor under design B", SEC3,
     "  return block.desc ", "  return f.wide.bind (·.desc) ",
     "yes", "no", "no", "directed3v's node 3; every cell runs design A. Not directed42 or 4b (return)"),
    ("committed-bid-descriptor-under-a", "committed_descriptor: the bid's descriptor under design A", SEC3,
     "return if ok then some fd else none", "return if ok then block.desc else none",
     "yes", "yes", "yes", "every chunk under design A, whose bid has no descriptor: hand5's eight (return). Not directed42 or 4b"),
    ("validate-own-level1-not-asked", "validate_chunk: the node's level 1 not asked where it has its own", SEC3,
     '  if (← read).replaced.contains "validate_chunk" then return ← validateChunkNode f.narrow     -- the node\'s own\n', "",
     "yes", "no", "no", "directed42 and directed4b alone, where the scenario's level 1 is the node's: the document's runs on a "
     "narrow chunk (raise, tape). No cell may replace it (the tracer's twelfth fault)"),
]

GROUPS = [("§1 and §2's message_id", E), ("drop_offer", DROP_OFFER), ("§6.4", D),
          ("§4.6 and §6.2: claim_group, drop_group, stop_pull", B1), ("§4.3: on_have, peer_has, holders", B2),
          ("§4.1 and §4.5: on_iwant, respond, on_frame", B3), ("§4.6: decode_group, push_rebuilt", B4),
          ("§3: level 1", B5)]
ROWS = [r for _, g in GROUPS for r in g]
assert len({r[0] for r in ROWS}) == len(ROWS), "a name twice"
CYCLE1 = {r[0]: (r[1], r[2], r[3], r[4]) for r in ROWS}
PRED = {r[0]: {"D": r[5], "H": r[6], "C": r[7], "why": r[8]} for r in ROWS}

# a table mutant's table (mutants3.py's TABLE_OF), the new traced functions, the helpers that are a traced function's
# own code, and each new table's operations (TABLE_NAMES)
TABLE_OF = {
    "tables-pace-read-no-note": "pace_queue", "tables-pace-write-none": "pace_queue",
    "tables-frames-clear-no-note": "ihave_frames", "tables-asked-clear-no-note": "ihave_asked",
    "tables-heldback-clear-no-note": "held_back",
    "tables-stop-pull-read-false": "stop_pull", "tables-stop-pull-write-no-note": "stop_pull",
    "tables-peer-has-read-none": "peer_has", "tables-peer-has-write-none": "peer_has",
    "tables-holders-read-no-note": "holders", "tables-holders-write-none": "holders",
    "tables-serve-count-read-no-note": "serve_count", "tables-serve-count-write-none": "serve_count",
    "tables-owed-answers-write-none": "owed_answers",
}
TRACED = ("group_id", "group_key", "K", "N", "segment_length", "valid_descriptor", "build_group", "message_id",
          "drop_offer", "on_heartbeat", "on_pace_tick", "send_gossip", "claim_group", "drop_group", "on_have",
          "on_iwant", "respond", "on_frame", "decode_group", "push_rebuilt", "validate_chunk", "committed_descriptor")
PART_OF = {"pace_turns": "on_pace_tick", "gossip_count": "on_heartbeat"}
TABLE_NAMES = {
    "pace_queue": ("paceJobs", "setPaceJobs", "paceQueue"),
    "stop_pull": ("stopPull", "setStopPull", "allStopPull"),
    "peer_has": ("peerHasEntry?", "setPeerHas", "allPeerHas", "peerHas"),
    "holders": ("holdersOf", "setHolders", "allHolders", "holders"),
    "serve_count": ("serveCount", "setServeCount", "allServeCount"),
    "owed_answers": ("owedAnswerBits", "setOwedAnswers", "owedAnswers"),
}
TABLE_NAMES_MORE = {"ihave_frames": ("clearIhaveFrames",), "ihave_asked": ("clearIhaveAsked",),
                    "held_back": ("clearHeldBack", "allHeldBack")}


def table():
    """The mutants and their predictions as Markdown tables, a section per entry of GROUPS."""
    out = []
    for title, g in GROUPS:
        out += [f"## {title} ({len(g)})", "", "| mutant | what it changes | D | H | C | why |", "|---|---|---|---|---|---|"]
        out += [f"| {n} | {what.split(': ', 1)[1]} | {d} | {h} | {c} | {why} |" for n, what, _, _, _, d, h, c, why in g]
        out.append("")
    for col, k in (("D", 5), ("H", 6), ("C", 7)):
        vals = [r[k] for r in ROWS]
        out.append(f"- {col}: " + ", ".join(f"{vals.count(v)} {v}" for v in ("yes", "no", "open") if vals.count(v)))
    return "\n".join(out)


if __name__ == "__main__":
    if sys.argv[1:] == ["--table"]:
        print(table())
    else:
        print(f"{len(ROWS)} mutants: " + ", ".join(f"{t.split(':')[0]} {len(g)}" for t, g in GROUPS))
