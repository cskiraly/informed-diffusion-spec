"""Mutants of more of the twin's code, each with what was predicted of it before it was built, and with its witness:
a record its pick selects in which its patch runs, and the member of the record that then differs.

A row names its witness since a prediction alone can fail two ways: the directed sets may leave a mutant untold
(by its pick or by a set's draw), and a picked record may reach the patch while nothing it compares differs.

A row: (name, what, file, old, new, D, H, C, why, witness). D: told by a directed set; H: by hand5; C: by a cell;
each "yes", "no" or "open". `witness` names the set, the function's record and the member that differs.
"""
TABLES, SEC52 = "SpecTwin/Tables.lean", "SpecTwin/Sec52.lean"
# the traced functions this file adds, each a name a mutant's description may begin with (mutants3.py's TRACED:
# the name picks the records the mutant is replayed on); beside each, the list that holds its mutants
TRACED = ("owe", "note_push", "unpush", "announce",                 # PART1
          "guard_fails", "choose_push",                             # PART2
          "forward", "candidates_for_source", "on_mesh_join",       # PART4
          "origin_written",                                         # PARTC
          "acquire_slot", "release_unused_slot", "track_in_flight", "window_release", "window_timeout",
          "free_slot",                                              # PART5B
          "front", "wake_front", "write_waits",                     # PART7
          "origin_acked",                                           # PART5C
          "publish")                                                # PART6

# the twin's tables origin, planned, pushed and desc: a mutant of each one's read
PART0 = [
    ("tables-origin-read-none", "the tables: a read of origin answers that the group is not there, and notes its read", TABLES,
     "  origin g := do note (.read (.origin g)); return (← get).origin.get? g\n",
     "  origin g := do note (.read (.origin g)); return none\n",
     "yes", "yes", "yes",
     "have_bits at a node that published the group answers `mine` for `origin`: every chunk, where only the acknowledged "
     "ones are in the HAVE",
     "directed42, a have_bits record whose reads have origin[g] there with fewer bits than mine[g]: the return value; "
     "hand5, the source's HAVE after an acknowledgement (send_have's enqueue on the tape)"),
    ("tables-planned-row-read-false", "the tables: a read of a group's row of planned answers that it is not there", TABLES,
     "  planned g := do note (.read (.plannedRow g)); return (← get).planned.contains g\n",
     "  planned g := do note (.read (.plannedRow g)); return false\n",
     "yes", "yes", "yes",
     "on_have at the source, a new index of a group it published: origin_acked is not asked",
     "directed43, an on_have record whose reads have planned[g] true and whose tape has origin_acked: the tape (the "
     "call logged and not asked)"),
    ("tables-pushed-read-none", "the tables: a read of pushed answers that nothing was pushed, and notes its read", TABLES,
     "  pushedEntry? p g := do note (.read (.pushed p g)); return ((← get).pushed.getD p {}).get? g\n",
     "  pushedEntry? p g := do note (.read (.pushed p g)); return none\n",
     "yes", "open", "open",
     "with_owed offers a peer what was pushed to it; push_rebuilt counts a peer short by what was pushed to it",
     "directed7, a next_to_send record whose reads have pushed[p][g] with a bit that is owed: the return value (the "
     "IHAVE's bits); directed46d, a push_rebuilt record whose reads have pushed[q][g] with bits: the tape (a push more)"),
    ("tables-desc-read-none", "the tables: a read of desc answers that the group is not there, and notes its read", TABLES,
     "  desc g := do note (.read (.desc g)); return (← get).desc.get? g\n",
     "  desc g := do note (.read (.desc g)); return none\n",
     "yes", "yes", "yes",
     "every reader of a group's descriptor: valid_id takes an index beyond the count, on_validated opens a group "
     "that is open, claim_group and push_rebuilt have no K",
     "directed44, a valid_id record whose reads have desc[g] there and whose reached has N: reached (the twin does not "
     "enter N); hand5, any on_frame with a chunk of an open group (open_group asked again: the tape)"),
]

# §5.2's owe, note_push, unpush and announce. "directed52" is their own set; a witness names the kind of record
# there (the set prints how many of each kind it drew). H and C: hand5 and the cells reach the four through
# next_to_send (unpush), decode_group's repair (note_push, owe), send_gossip (announce) and through records of their
# own (note_push under publish).
OWE = "  setOwed p g (((← owed? p g).getD 0) ||| bits)             -- `owed[p][g] |= bits`\n"
CLOCK = ("  let first := if e.bits == 0 then some now else e.firstPush   -- `if e.empty(): e.first_push = now`: "
         "the guard's\n")
SETP = "  setPushed p g { bits := e.bits.set i, firstPush := first, ttl := (← read).c.PUSH_TTL }\n"
CLEAR = "  | some e => setPushed p g { e with bits := e.bits.clear i }\n"
MESH = "  if ← meshHas p then                                       -- `if p in mesh: owe(p, g, bitmap({i}))`\n"
MINUS = "  let b := (bits.minus (← pushed p g)).minus (← peerHas p g)\n"
ENQ = ("  else if !(← enqueue p (.ihave g b) false) then            -- `enqueue(p, IHAVE(HaveBitmap(group=g, bits=b)), "
       "urgent=False)`\n")
OWED = "    owe p g b                                               -- refused by a full queue: owed\n"
PART1 = [
    ("owe-not-ored", "owe: the bits written in place of what was owed, not added to it", SEC52,
     OWE, "  let _ ← owed? p g\n  setOwed p g bits\n",
     "yes", "open", "open",
     "an offer owed before is lost when another is owed to the same peer for the same group",
     "directed52, an owe record of the kind \"an entry\" whose reads have owed[p][g] with a bit the call's bits have "
     "not: the writes (owed[p][g]'s value)"),
    ("owe-no-wake", "owe: the peer's writer not woken", SEC52,
     OWE + "  wake p\n", OWE,
     "yes", "open", "yes",
     "what is owed waits for another write to the peer",
     "directed52, any owe record: the tape (wake logged and not asked); the cells: any next_to_send record that "
     "unpushes to a mesh peer (14 cells of 15)"),
    ("note-push-clock-always", "note_push: the first push's time set at every push", SEC52,
     CLOCK, "  let first := some now\n",
     "yes", "open", "yes",
     "the guard's grace starts again at every push, so a peer that never proves is never demoted",
     "directed52, a note_push record of the kind \"a later push\": the writes (pushed[p][g]'s first push); the cells: "
     "a second push to a peer for a group (4,700 of 6,024 calls in `none`)"),
    ("note-push-clock-kept-if-set", "note_push: the first push's time set only where the entry has none", SEC52,
     CLOCK, "  let first := match e.firstPush with | some t => some t | none => some now\n",
     "yes", "open", "open",
     "an entry emptied by unpush keeps its old clock at the next push, and the guard counts from a push never made",
     "directed52, a note_push record of the kind \"an entry with no bit\": the writes (the first push's time)"),
    ("note-push-ttl-kept", "note_push: the ttl set at the first push alone", SEC52,
     # (the constant bound first: a read nested in the `if` does not type-check)
     SETP, "  let ttl0 := (← read).c.PUSH_TTL\n"
           "  setPushed p g { bits := e.bits.set i, firstPush := first, ttl := if e.bits == 0 then ttl0 else e.ttl }\n",
     "yes", "no", "open",
     "an entry expires PUSH_TTL heartbeats after its first push, whatever was pushed since",
     "directed52, a note_push record of the kind \"a later push\" whose reads have the entry's ttl below PUSH_TTL: "
     "the writes (the ttl)"),
    ("note-push-index-off", "note_push: the bit after the index set", SEC52,
     SETP, "  setPushed p g { bits := e.bits.set (i + 1), firstPush := first, ttl := (← read).c.PUSH_TTL }\n",
     "yes", "yes", "yes",
     "another chunk is counted as pushed",
     "directed52, any note_push record: the writes (the bits); hand5 and the cells: a note_push record under publish"),
    ("unpush-not-cleared", "unpush: the index not cleared", SEC52,
     CLEAR, "  | some e => setPushed p g e\n",
     "yes", "open", "yes",
     "a push not made stays counted: its peer is neither pushed the chunk nor, by with_owed's subtraction, offered it",
     "directed52, an unpush record of the kinds \"its last bit\" or \"a bit of several\": the writes (the bits); the "
     "cells: any next_to_send record that unpushes (projection)"),
    ("unpush-makes-entry", "unpush: an entry made where none was", SEC52,
     "  | none => branch \"unpush: nothing pushed\"                 -- a missing entry stays missing\n",
     "  | none => setPushed p g {}\n",
     "yes", "open", "open",
     "an entry with no clock is there, which guard_fails then reads",
     "directed52, an unpush record of the kind \"no entry\": the footprint (the twin changes an entry the Python "
     "read as missing and did not write)"),
    ("unpush-clock-cleared", "unpush: the first push's time cleared with the index", SEC52,
     CLEAR, "  | some e => setPushed p g { e with bits := e.bits.clear i, firstPush := none }\n",
     "yes", "open", "yes",
     "the guard's clock does not stay",
     "directed52, an unpush record whose reads have the entry: the writes (the first push's time)"),
    ("unpush-owes-outside-mesh", "unpush: owed to a peer outside the mesh too", SEC52,
     MESH, "  if (← meshHas p) || true then\n",
     "yes", "open", "open",
     "§5.1's other connections get an announcement from the source's step",
     "directed52, an unpush record of a kind \"outside the mesh\": the tape (wake asked, and the tape has no more); "
     "the cells: rr-stripe alone, 2 records"),
    ("unpush-never-owes", "unpush: nothing owed", SEC52,
     MESH, "  if (← meshHas p) && false then\n",
     "yes", "open", "yes",
     "a push not made is not offered either: where no other peer offers the chunk, its peer never completes",
     "directed52, an unpush record of a kind \"in the mesh\": the tape (wake logged and not asked)"),
    ("announce-pushed-not-minus", "announce: what was pushed to the peer offered too", SEC52,
     MINUS, "  let _ ← pushed p g\n  let b := bits.minus (← peerHas p g)\n",
     "yes", "open", "open",
     "a chunk on its way to the peer is offered to it, and asked for on top of the push",
     "directed52, an announce record of the kind \"bits drawn\" whose reads have pushed[p][g] with one of the bits "
     "that peer_has[p][g] has not: the tape (enqueue's bits)"),
    ("announce-held-not-minus", "announce: what the peer holds offered too", SEC52,
     MINUS, "  let _ ← peerHas p g\n  let b := bits.minus (← pushed p g)\n",
     "yes", "open", "open",
     "a chunk the peer said it holds is offered to it",
     "directed52, an announce record of the kind \"bits drawn\" whose reads have peer_has[p][g] with one of the bits "
     "that pushed[p][g] has not: the tape (enqueue's bits)"),
    ("announce-empty-enqueued", "announce: an empty offer enqueued", SEC52,
     "  if b == 0 then                                            -- an empty bitmap is not sent\n",
     "  if false then\n",
     "yes", "open", "open",
     "an IHAVE of no chunk is queued",
     "directed52, an announce record of the kinds \"no bits\" or \"bits pushed or held alone\": the tape (enqueue "
     "asked, and the tape has none)"),
    ("announce-refused-not-owed", "announce: a refused offer not owed", SEC52,
     ENQ + OWED, ENQ,
     "yes", "no", "no",
     "an offer a full queue refuses is lost. No cell runs the line (the toy's queue refuses no IHAVE): the reach "
     "table's line 410",
     "directed52, an announce record with bits to offer in a sample whose enqueue refuses: the tape (wake logged and "
     "not asked) and the writes (owed)"),
    ("announce-owes-all-bits", "announce: the bits given owed, not the bits offered", SEC52,
     ENQ + OWED, ENQ + "    owe p g bits\n",
     "yes", "no", "no",
     "what the peer holds or was pushed is owed to it. No cell runs the line",
     "directed52, an announce record refused whose bits have one that pushed[p][g] or peer_has[p][g] has: the writes "
     "(owed[p][g])"),
    ("announce-urgent", "announce: the offer enqueued urgently", SEC52,
     ENQ, "  else if !(← enqueue p (.ihave g b) true) then\n",
     "yes", "open", "yes",
     "offers overtake the chunks queued before them",
     "directed52, an announce record with bits to offer: the tape (enqueue's urgent)"),
    ("announce-owed-when-taken", "announce: owed also where the queue took the offer", SEC52,
     "  else\n    branch \"announce: offered\"\n",
     "  else\n    owe p g b\n    branch \"announce: offered\"\n",
     "yes", "open", "yes",
     "every offer is made twice",
     "directed52, an announce record whose enqueue is taken: the tape (wake asked, and the tape has no more)"),
    ("tables-pushed-write-not-made", "the tables: a write of pushed noted and not made", TABLES,
     "  setPushed p g e := do\n    note (.write (.pushed p g))\n"
     "    modify fun s => { s with pushed := s.pushed.insert p ((s.pushed.getD p {}).insert g e) }\n",
     "  setPushed p g e := do\n    note (.write (.pushed p g))\n",
     "yes", "yes", "yes",
     "no push is counted",
     "directed52, any note_push record: the whole state (pushed[p][g]); hand5: a note_push record under publish"),
]

# §5.3's guard_fails and choose_push. "directed53" is their own set; a witness names the kind of record there (the
# set prints how many of each kind it drew). The rows' C column counts choose_push's records in the cells as
# publish's alone: at the source, with a budget of R below the candidates' count, nobody demoted. So it is "no" for
# what only a forwarding node's call or a demoted peer shows; RESTATED_C below restates it with forward the twin's.
SEC53 = "SpecTwin/Sec53.lean"
GUARD_R = "  if e.bits.popcount < (← read).c.R_NODE then               -- `popcount(e) >= R_NODE and …`\n"
GRACE = "  if !((← read).now - Float.ofBits first > (← read).c.GUARD_GRACE) then\n"
HEARD = ("  let heard := (← peerHasEntry? p g).isSome                 -- `g not in peer_has[p]`: no HAVE at all from p "
         "for g\n")
EVERY = "  if budget ≥ cands.length then                             -- everyone, no ordering needed\n"
KNOWN = "    known := known ++ [(p, ((← peerHas p g) ||| (← pushed p g)).popcount)]\n"
KEYS = "    let t ← tiebreak f p\n    keys := keys ++ [(p, (t, ← peerIdBytes p))]\n"
LARGER = "  let larger (a b : Nat × String) : Bool := a.1 > b.1 || (a.1 == b.1 && a.2 > b.2)\n"
SORT1 = "  let order0 := cands.mergeSort fun a b => !(larger (key b) (key a))\n"
SORT2 = "    (rank a).1 < (rank b).1 || ((rank a).1 == (rank b).1 && (rank a).2 ≤ (rank b).2)\n"
OK = "    let ok := order.filter fun p => (rank p).1 == 0         -- `[p for p in order if not unproven[p]]`\n"
MEDIAN = "      let median := (rank (ok.getD ((ok.length - 1) / 2) 0)).2   -- `known[ok[(len(ok) - 1) // 2]]`\n"
POOL = "      let pool := ok.filter fun p => (rank p).2 ≤ median\n"
DRAW = ("      let drawn ← sample pool (min budget pool.length)      -- `sample_without_replacement(pool, min(budget, "
        "len(pool)))`\n")
AFTER = "      order := drawn ++ order.filter fun p => !drawn.contains p\n"
SOURCE = "  if !atSource then                                         -- [c16] safer form\n"
TAKE = "  return order.take budget                                  -- `order[:budget]`\n"
PART2 = [
    ("guard-more-than-r", "guard_fails: more than R_NODE pushes asked, not R_NODE", SEC53,
     GUARD_R, "  if e.bits.popcount ≤ (← read).c.R_NODE then\n",
     "yes", "no", "no",
     "a peer pushed exactly R_NODE chunks and silent is not demoted",
     "directed53, a guard_fails record of the kind \"demoted\" whose reads have pushed[p][g] with exactly two bits: "
     "the return value"),
    ("guard-at-the-grace", "guard_fails: demoted at the grace exactly", SEC53,
     GRACE, "  if !((← read).now - Float.ofBits first ≥ (← read).c.GUARD_GRACE) then\n",
     "yes", "no", "no",
     "the grace is a strict bound",
     "directed53, a guard_fails record of the kind \"at the grace exactly\" with no HAVE from the peer: the return "
     "value"),
    ("guard-no-grace", "guard_fails: the grace not waited", SEC53,
     GRACE, "  if false then\n",
     "yes", "no", "no",
     "a peer is demoted before its first HAVE could arrive",
     "directed53, a guard_fails record of the kind \"within the grace\" with no HAVE from the peer: the return value"),
    ("guard-empty-have-not-counted", "guard_fails: a HAVE with no bit not taken as a HAVE", SEC53,
     HEARD, "  let heard := ((← peerHasEntry? p g).map (·.bits != 0)).getD false\n",
     "yes", "no", "no",
     "a peer that sent an empty HAVE is demoted: not even an empty one, the document says",
     "directed53, a guard_fails record of the kind \"a HAVE seen\" whose reads have peer_has[p][g] there with no "
     "bit: the return value"),
    ("guard-have-read-first", "guard_fails: the peer's HAVEs read before the pushes are counted", SEC53,
     "  let e := (← pushedEntry? p g).getD {}                     -- `e = pushed[p][g]`\n",
     "  let _ ← peerHasEntry? p g\n  let e := (← pushedEntry? p g).getD {}\n",
     "yes", "no", "yes",
     "a read the Python does not make where the first two tests fail",
     "directed53, a guard_fails record of the kind \"fewer than R_NODE pushed\": the footprint (the twin reads "
     "peer_has[p][g], which the Python did not); the cells: a choose_push record under publish, whose candidates "
     "have nothing pushed yet"),
    ("choose-budget-strict", "choose_push: everyone only where the budget is more than the candidates", SEC53,
     EVERY, "  if budget > cands.length then\n",
     "yes", "open", "open",
     "with as many candidates as the budget, they come back in the push order, not their own",
     "directed53, a choose_push record of the kind \"everyone\" with budget = len(cands) >= 2: the tape (the keys "
     "asked, none logged)"),
    ("choose-known-without-pushed", "choose_push: what was pushed not counted as held", SEC53,
     KNOWN, "    let _ ← pushed p g\n    known := known ++ [(p, (← peerHas p g).popcount)]\n",
     "yes", "open", "open",
     "a peer pushed many chunks and silent ranks as furthest behind, and is pushed again",
     "directed53, a choose_push record whose candidates' ranks differ by `pushed` alone: the return value"),
    ("choose-known-without-have", "choose_push: what the peer said it holds not counted", SEC53,
     KNOWN, "    let _ ← peerHas p g\n    known := known ++ [(p, (← pushed p g).popcount)]\n",
     "yes", "no", "no",
     "the furthest behind is not chosen first",
     "directed53, a choose_push record whose candidates' ranks differ by `peer_has` alone: the return value"),
    ("choose-keys-id-first", "choose_push: the peer's id asked before its tie-break", SEC53,
     KEYS, "    let i ← peerIdBytes p\n    let t ← tiebreak f p\n    keys := keys ++ [(p, (t, i))]\n",
     "yes", "yes", "yes",
     "the order of the questions",
     "directed53, any choose_push record that is not \"everyone\": the tape; hand5 and the cells: a choose_push "
     "record under publish"),
    ("choose-smallest-first", "choose_push: the smallest tie-break first", SEC53,
     SORT1, "  let order0 := cands.mergeSort fun a b => !(larger (key a) (key b))\n",
     "yes", "yes", "yes",
     "the push order is reversed among equal counts",
     "directed53, a choose_push record with two candidates of one rank and different tie-breaks: the return value"),
    ("choose-id-not-compared", "choose_push: equal tie-breaks left in the candidates' order", SEC53,
     LARGER, "  let larger (a b : Nat × String) : Bool := a.1 > b.1\n",
     "yes", "no", "no",
     "two peers with one tie-break are ordered by the list, not by their ids. No cell has two equal tie-breaks (64 "
     "bits of a hash)",
     "directed53, a choose_push record of a kind \"tie-breaks from four values\" with two candidates of one rank "
     "and one tie-break, the later with the larger id: the return value"),
    ("choose-unproven-not-last", "choose_push: the guard's demoted peers not moved back", SEC53,
     SORT2, "    (rank a).2 ≤ (rank b).2\n",
     "yes", "no", "no",
     "a silent peer keeps its rank",
     "directed53, a choose_push record of a kind \"at the source, some demoted\" where a demoted candidate has the "
     "lowest count: the return value"),
    ("choose-most-held-first", "choose_push: the candidates that hold most first", SEC53,
     SORT2, "    (rank a).1 < (rank b).1 || ((rank a).1 == (rank b).1 && (rank a).2 ≥ (rank b).2)\n",
     "yes", "open", "open",
     "furthest ahead first",
     "directed53, a choose_push record at the source with candidates of different counts: the return value"),
    ("choose-demoted-in-the-draw", "choose_push: the demoted peers in the draw's pool too", SEC53,
     OK, "    let ok := order\n",
     "yes", "no", "no",
     "the draw can pick a peer the guard demotes",
     "directed53, a choose_push record of the kind \"a draw, some demoted\": the tape (the pool asked of the draw)"),
    ("choose-median-upper", "choose_push: the upper median", SEC53,
     MEDIAN, "      let median := (rank (ok.getD (ok.length / 2) 0)).2\n",
     "yes", "no", "no",
     "with an even number of proven peers the pool takes in the next count up",
     "directed53, a choose_push record of a kind \"a draw\" with an even number of proven candidates whose two "
     "middle counts differ: the tape (the pool)"),
    ("choose-pool-below-median", "choose_push: the pool below the median, not at it", SEC53,
     POOL, "      let pool := ok.filter fun p => (rank p).2 < median\n",
     "yes", "no", "no",
     "the median's own peers are left out of the draw",
     "directed53, any choose_push record of a kind \"a draw\": the tape (the pool)"),
    ("choose-draw-of-budget", "choose_push: the budget drawn, whatever the pool holds", SEC53,
     DRAW, "      let drawn ← sample pool budget\n",
     "yes", "no", "no",
     "a draw of more than the pool",
     "directed53, a choose_push record of a kind \"a draw\" whose pool is smaller than the budget: the tape (the "
     "draw's count)"),
    ("choose-drawn-not-first", "choose_push: the drawn peers left at their rank", SEC53,
     AFTER, "      order := order\n",
     "yes", "no", "no",
     "the draw is asked and not used",
     "directed53, a choose_push record of a kind \"a draw\" whose draw is not the first of the order: the return "
     "value"),
    ("choose-source-draws", "choose_push: the source draws too", SEC53,
     SOURCE, "  if true then\n",
     "yes", "yes", "yes",
     "the source's plan is not the ranking as it is",
     "directed53, a choose_push record of a kind \"at the source\": the tape (the draw asked, none logged); hand5 and "
     "the cells: a choose_push record under publish"),
    ("choose-one-more", "choose_push: one more than the budget", SEC53,
     TAKE, "  return order.take (budget + 1)\n",
     "yes", "yes", "yes",
     "a push more",
     "directed53, any choose_push record that is not \"everyone\": the return value"),
]

# forward, candidates_for_source, on_mesh_join. "directed54" is their own set. forward runs in every cell's
# on_frame records; on_mesh_join in the set alone (no caller in the toy); candidates_for_source in a cell under
# publish alone, with nobody holding the chunk.
SEC54 = "SpecTwin/Sec54.lean"
HOLDING = "  let holding ← (← meshList).filterM fun p => return (← peerHas p g).has i   -- [c4] the sender, normally\n"
CANDS = "  let cands := (← meshList).filter fun p => !holding.contains p && p != fromPeer\n"
BUDGET = "  let budget := (← read).c.R_NODE - holding.length          -- `max(0, R_NODE - len(holding))`  [c3, c4, c11, c17]\n"
FPUSH = "    if ← enqueue p (.chunk f) false then                    -- [c7]\n"
FOWE = "      owe p g (1 <<< i)                                     -- [c3] refused: offered instead\n"
FANN = "    if !targets.contains p then announce p g (1 <<< i)      -- [c3]\n"
FPUT = "  gossipPut f                                               -- stock message cache (§6.4)\n"
POOL = "  let pool ← if stripe then connectedTopicPeers else meshList\n"
CFILT = "  pool.filterM fun p => return !(← peerHas p f.g).has f.i   -- `if not peer_has[p][f.group].has(f.index)`\n"
MEXP = "    if ← expired g then                                     -- nothing of an expired or dropped group\n"
MINV = "    if (← state? g) == some .invalid then                   -- `state[g] == INVALID`\n"
MANN = "    announce p g bits                                       -- what we can serve, received or rebuilt (§5.2)\n"
PART4 = [
    ("forward-holders-not-counted", "forward: the budget not reduced by the holders", SEC54,
     BUDGET, "  let budget := (← read).c.R_NODE\n",
     "yes", "open", "yes",
     "the phase [c4]: a chunk held by its sender is pushed to R_NODE more, not R_NODE less one",
     "directed54, a forward record of a kind \"no budget\" with a candidate: the tape (a push)"),
    ("forward-sender-a-candidate", "forward: the sender a candidate where it does not hold the chunk", SEC54,
     CANDS, "  let cands := (← meshList).filter fun p => !holding.contains p\n",
     "yes", "open", "open",
     "the chunk is pushed or offered back to the peer it came from",
     "directed54, a forward record whose sender is in the mesh and holds nothing of the chunk: the tape (a key or an "
     "offer for the sender)"),
    ("forward-holders-candidates", "forward: the holders candidates too", SEC54,
     CANDS, "  let cands := (← meshList).filter fun p => p != fromPeer\n",
     "yes", "open", "yes",
     "a holder is pushed or offered the chunk it holds (announce subtracts it; choose_push may still pick it)",
     "directed54, a forward record with a holder that is not the sender, of a kind \"the draw\" or \"everyone pushed\": "
     "the tape (a push to a holder, or its keys)"),
    ("forward-mesh-asked-once", "forward: the mesh asked once, for the holders and the candidates", SEC54,
     HOLDING + CANDS,
     "  let ms ← meshList\n  let holding ← ms.filterM fun p => return (← peerHas p g).has i\n"
     "  let cands := ms.filter fun p => !holding.contains p && p != fromPeer\n",
     "yes", "yes", "yes",
     "the Python iterates the mesh twice, and the node answers each time",
     "directed54, any forward record: the tape (the second mesh logged and not asked); hand5 and the cells: an "
     "on_frame record that forwards"),
    ("forward-push-urgent", "forward: a push queued urgently", SEC54,
     FPUSH, "    if ← enqueue p (.chunk f) true then\n",
     "yes", "yes", "yes",
     "pushes overtake what was queued before them",
     "directed54, any forward record with a push: the tape (enqueue's urgent); hand5 and the cells: an on_frame record "
     "that forwards"),
    ("forward-refused-not-owed", "forward: a refused push not offered instead", SEC54,
     FOWE, "",
     "yes", "no", "open",
     "a refused push leaves its peer neither pushed nor offered the chunk",
     "directed54, a forward record of a kind \"pushes refused\": the tape (wake logged and not asked) and the writes "
     "(owed); the cells: loss-thin alone (420 refusals)"),
    ("forward-targets-announced-too", "forward: the chunk offered to the peers it was pushed to as well", SEC54,
     FANN, "    announce p g (1 <<< i)\n",
     "yes", "open", "yes",
     "announce is entered for a target, where the Python does not call it; for a target whose push was refused the "
     "offer is made (or refused) again. (Predicted untold before its build, on the argument that announce subtracts "
     "what was pushed: wrong. The record's `reached` names the functions entered, and a refused target has no bit "
     "pushed.)",
     "directed54, a forward record of a kind \"everyone pushed\" with no other candidate (reached: announce entered, "
     "not in the record's) or of a kind \"pushes refused\" (tape: an offer more)"),
    ("forward-not-cached", "forward: the chunk not put in the message cache", SEC54,
     FPUT, "",
     "yes", "yes", "yes",
     "the chunk is not gossiped at the heartbeat",
     "directed54, any forward record: the tape (gossip_put logged and not asked)"),
    ("candidates-always-mesh", "candidates_for_source: the mesh whatever the uplink", SEC54,
     POOL, "  let pool ← meshList\n",
     "yes", "no", "yes",
     "a source at the stripe's uplink pushes to its mesh alone [c13]",
     "directed54, a candidates_for_source record of a kind \"every connected peer\": the tape (mesh asked, "
     "connected_topic_peers logged); the cells: dcb20's and rr-stripe's sources"),
    ("candidates-holders-kept", "candidates_for_source: the holders candidates too", SEC54,
     CFILT, "  pool.filterM fun p => do let _ ← peerHas p f.g; return true\n",
     "yes", "no", "no",
     "the source pushes a chunk to a peer that holds it. In a cell nobody holds a chunk when it is published",
     "directed54, a candidates_for_source record of a kind \"a holder among them\": the return value"),
    ("mesh-join-expired-offered", "on_mesh_join: an expired group offered", SEC54,
     MEXP, "    if (← expired g) && false then\n",
     "yes", "no", "no",
     "chunks past their lifetime are offered to a new mesh peer. No cell calls on_mesh_join",
     "directed54, an on_mesh_join record with an expired group held: the tape (the state read, an offer)"),
    ("mesh-join-dropped-offered", "on_mesh_join: a dropped group offered", SEC54,
     MINV, "    if (← state? g) == some .invalid && false then\n",
     "yes", "no", "no",
     "chunks of a group that failed its check are offered",
     "directed54, an on_mesh_join record with an INVALID group held and not expired: the tape (an offer)"),
    ("mesh-join-state-read-first", "on_mesh_join: the state read before the expiry is asked", SEC54,
     MEXP, "    let _ ← state? g\n" + MEXP,
     "yes", "no", "no",
     "a read the Python does not make of an expired group's state",
     "directed54, an on_mesh_join record with an expired group held: the footprint (the twin reads state[g], which "
     "the Python did not)"),
    ("mesh-join-first-group-alone", "on_mesh_join: the first live group offered alone", SEC54,
     MANN, MANN + "    break\n",
     "yes", "no", "no",
     "a new mesh peer learns one group of what we can serve",
     "directed54, an on_mesh_join record of a kind \"2 of\" or \"3 of\" groups offered: the tape (the second group's "
     "expiry logged and not asked)"),
]

# on_frame's branch for an IDONTWANT's entry that is no bitmap, and `unwanted` the twin's own table. No cell
# handles such an entry, so the first three are directed41's alone; the fourth writes `unwanted` at every HAVE,
# which every cell has
SEC41 = "SpecTwin/Sec41.lean"
KEEP = ("    | .id a => setUnwanted p ((← unwantedOf p).insert a.idHex)      -- `unwanted[p].add(h)`\n"
        "    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)\n")
PARTB = [
    ("frame-id-not-kept", "on_frame: an IDONTWANT's id not kept", SEC41,
     KEEP, "    | _ => pure ()\n",
     "yes", "no", "no",
     "the peer goes on being sent what it said it does not want (stock's IDONTWANT, §4.1)",
     "directed41, an on_frame record whose IDONTWANT has an id the peer had not said: the writes (unwanted) and the "
     "whole state"),
    ("frame-id-replaces-the-set", "on_frame: an id kept in place of the peer's set", SEC41,
     KEEP, "    | .id a => setUnwanted p (({} : Std.HashSet Hex).insert a.idHex)\n"
           "    | .other raw => setUnwanted p (({} : Std.HashSet Hex).insert raw)\n",
     "yes", "no", "no",
     "the ids the peer said before are forgotten at each new one",
     "directed41, an on_frame record with a new id into a set that is there: the whole state (the set's other ids), "
     "and the read of the set not made"),
    ("frame-opaque-id-not-kept", "on_frame: an id that is no structured id not kept", SEC41,
     "    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)\n", "    | .other _ => pure ()\n",
     "yes", "no", "no",
     "§4.1: any other entry is an opaque id; a stock id of 20 bytes is the usual one",
     "directed41, an on_frame record whose IDONTWANT has a stock id of 20 or of 3 bytes not said before: the writes "
     "(unwanted)"),
    ("frame-bitmap-kept-as-id", "on_frame: a HAVE bitmap's group also kept as an id", SEC41,
     "    | .bitmap g bits => onHave p g bits                     --   lifetime (§8.1)\n",
     "    | .bitmap g bits => do\n      onHave p g bits\n      setUnwanted p ((← unwantedOf p).insert g)\n",
     "yes", "yes", "yes",
     "a bitmap is read as a HAVE and is no id (the toy's idontwant_id_known.py's control)",
     "any on_frame record with a HAVE: the twin writes unwanted, which the Python neither read nor wrote"),
]

# next_to_send's line at PUBLISH and §5.1's origin_written. No cell of the H or C column runs at PUBLISH: but for
# the first, these are directed7p's (and the small traced cell's, hand5-publish, which is no column here)
SEC72, SEC51 = "SpecTwin/Sec72.lean", "SpecTwin/Sec51.lean"
PARTC = [
    ("next-to-send-origin-written-at-ack", "next_to_send: origin_written called whatever SOURCE_OFFERS is", SEC72,
     "      if (← read).c.SOURCE_OFFERS_PUBLISH then originWritten f   -- [P4] the source's HAVE (§5.1)\n",
     "      originWritten f\n",
     "yes", "yes", "yes",
     "at ACK the source's HAVE grows at the acknowledgement alone (§5.1)",
     "any next_to_send record in which a chunk leaves, at ACK: reached (origin_written entered) and a read of "
     "origin the Python did not make; at the source the writes too"),
    ("next-to-send-origin-written-never", "next_to_send: origin_written not called at PUBLISH", SEC72,
     "      if (← read).c.SOURCE_OFFERS_PUBLISH then originWritten f   -- [P4] the source's HAVE (§5.1)\n", "",
     "yes", "no", "no",
     "at PUBLISH the source's HAVE would never grow: its peers go on asking it for what it sent",
     "directed7p, a next_to_send record in which a chunk leaves: reached; where the group is published and the bit "
     "new, the writes (origin) and the tape (the mesh)"),
    ("origin-written-bit-not-asked", "origin_written: the HAVE sent again where the bit is there", SEC51,
     "    if b.has f.i then\n", "    if false then\n",
     "yes", "no", "no",
     "a chunk's second copy would send the whole HAVE to the mesh again",
     "directed7p, an origin_written record of the kind \"the bit there already\" with a mesh: the tape (the mesh "
     "asked, where the tape is over)"),
    ("origin-written-have-not-sent", "origin_written: the HAVE not sent to the mesh", SEC51,
     "      for q in ← meshList do sendHave q g                   -- `for q in mesh: send_have(q, g)`\n", "",
     "yes", "no", "no",
     "the source's holding would grow unseen",
     "directed7p, an origin_written record of the kind \"the HAVE grows\" with a mesh: the tape (the mesh logged, "
     "not asked)"),
    ("origin-written-any-group", "origin_written: a group the node does not publish taken as published", SEC51,
     "  | none => branch \"origin_written: not a group we publish\"\n",
     "  | none => setOrigin g ((0 : Bits).set f.i)\n",
     "yes", "no", "no",
     "every node would claim to be a source of what it forwards",
     "directed7p, an origin_written record of the kind \"not a group we publish\": the whole state (origin)"),
]

# §7.1's window, the twin's own. The three table mutants, then the six functions'. Where a cell's column says
# "open": no cell's reach of that branch was counted before the row was written
SEC71 = "SpecTwin/Sec71.lean"
PART5B = [
    ("tables-in-flight-write-not-made", "the tables: a write of the window's count is noted and not made", TABLES,
     "  setInFlight e n := do note (.write (.inFlight e)); modify fun s => { s with inFlight := s.inFlight.insert e n }\n",
     "  setInFlight e n := do note (.write (.inFlight e))\n",
     "yes", "yes", "yes",
     "a slot taken or freed leaves the count as it was: the window never fills, or never empties",
     "directed71, an acquire_slot record that takes a slot: the whole state (in_flight); every write of a chunk in "
     "a cell (acquire_slot's)"),
    ("tables-waiters-read-reversed", "the tables: the line read from its other end", TABLES,
     "  waitersLine e := do note (.read (.waiters e)); return (← get).waiters.getD e []\n",
     "  waitersLine e := do note (.read (.waiters e)); return ((← get).waiters.getD e []).reverse\n",
     "yes", "no", "open",
     "the last writer in line is taken for the first: FIFO over peers [c14] the other way round",
     "directed71, an acquire_slot or free_slot record with two peers or more in line: the tape (wake of the other "
     "end) or the return value"),
    ("tables-sent-erase-not-made", "the tables: an erase of a send's time is noted and not made", TABLES,
     "  eraseSentAt k := do note (.write (.sent k)); modify fun s => { s with sent := s.sent.erase k }\n",
     "  eraseSentAt k := do note (.write (.sent k))\n",
     "yes", "yes", "yes",
     "a send released stays in flight: its timer frees the slot a second time",
     "directed71, a window_release record whose send is in flight: the whole state (sent); a cell's on_have of a "
     "chunk the node sent"),
    ("free-slot-count-kept", "free_slot: the count not lowered", SEC71,
     "  setInFlight .count ((← inFlight .count) - 1)              -- `in_flight -= 1`\n",
     "  let _ ← inFlight .count\n",
     "yes", "yes", "yes",
     "no slot ever comes back",
     "directed71, any free_slot record: the writes (in_flight); a cell's release of a send"),
    ("free-slot-no-wake", "free_slot: the first writer in line that can write not woken", SEC71,
     '  wakeFront                                                 -- the first writer in line that can write tries again\n',
     "",
     "yes", "no", "open",
     "a writer in line would wait for its next arrival to try again",
     "directed71, a free_slot record with somebody in line that can write and a slot free: the tape (wake logged, not asked)"),
    ("acquire-over-the-window", "acquire_slot: a slot taken with the window full", SEC71,
     '  let takes ← if ← underW n then do                         -- `in_flight < W and front() in (None, p)`: no writer\n',
     "  let takes ← if true then do\n",
     "yes", "no", "open",
     "the window [c14] bounds nothing",
     "directed71, an acquire_slot record of the kind \"the window full\" with nobody in line: the return value"),
    ("acquire-jumps-the-line", "acquire_slot: a slot taken past the writers in line that can write", SEC71,
     '      pure (q == none || q == some p)                       --   alone)\n',
     "      pure true\n",
     "yes", "no", "open",
     "FIFO over peers: a later writer would overtake the first in line",
     "directed71, an acquire_slot record of the kind \"another the front\" with a slot free: the return value"),
    ("acquire-keeps-its-place", "acquire_slot: the writer that takes a slot stays in line", SEC71,
     '    if line.contains p then setWaitersLine .line (line.erase p)    -- `if p in waiters: waiters.remove(p)`\n', "",
     "yes", "no", "open",
     "the line would never shorten",
     "directed71, an acquire_slot record of the kind \"the peer the front\" with a slot free: the writes (the "
     "line)"),
    ("acquire-count-not-raised", "acquire_slot: the count not raised", SEC71,
     "    setInFlight .count (n + 1)                              -- `in_flight += 1`\n", "",
     "yes", "yes", "yes",
     "every writer gets a slot: no window",
     "directed71, an acquire_slot record that takes a slot: the writes (in_flight); every chunk's write in a cell"),
    ("acquire-next-not-woken", "acquire_slot: the next in line not woken where slots remain", SEC71,
     '    wakeFront                                               -- slots remain: the next in line takes one too\n', "",
     "yes", "no", "open",
     "a free slot would wait for the next release",
     "directed71, an acquire_slot record of the kind \"the peer the front, others behind\" with two slots free: "
     "the tape (wake logged, not asked)"),
    ("acquire-joins-the-line-twice", "acquire_slot: a waiting writer joins the line again", SEC71,
     "  if !line.contains p then setWaitersLine .line (line ++ [p])   -- a writer keeps its place while it waits\n",
     "  setWaitersLine .line (line ++ [p])\n",
     "yes", "no", "open",
     "a writer keeps its place while it waits: one place",
     "directed71, an acquire_slot record of the kind \"another first, the peer in line already\": the whole state "
     "(the line)"),
    ("release-stays-in-line", "release_unused_slot: the peer does not leave the line", SEC71,
     "  if line.contains p then                                   -- `if p in waiters:`\n", "  if false then\n",
     "yes", "no", "no",
     "a writer with nothing to send would hold its place, and the line behind it",
     "directed71, a release_unused_slot record with the peer in line (no cell and no other set has one): the writes "
     "(the line)"),
    ("release-slot-not-freed", "release_unused_slot: a held slot not given back", SEC71,
     "    setSlotHeld p false\n    freeSlot\n", "    setSlotHeld p false\n",
     "yes", "open", "open",
     "a slot taken for a chunk that was cancelled or projected away would be lost",
     "directed71, a release_unused_slot record whose peer holds a slot: the reached functions (free_slot) and the "
     "writes (in_flight)"),
    ("track-second-copy-tracked", "track_in_flight: a second copy's slot kept", SEC71,
     "  if (← sentAt? k).isSome then                              -- `if key in sent: return free_slot()`: a second copy\n",
     "  if false then\n",
     "yes", "no", "open",
     "one send's key would hold two slots, and one release frees one",
     "directed71, a track_in_flight record of a send still in flight: the reached functions (free_slot) and the "
     "tape (a timer more)"),
    ("track-no-timer", "track_in_flight: no timer armed", SEC71,
     "  after (← read).c.WINDOW_TIMEOUT (.windowTimeout k now)    -- `after(WINDOW_TIMEOUT, window_timeout, key, now)`\n", "",
     "yes", "yes", "yes",
     "a send whose HAVE never comes would hold its slot for ever",
     "directed71, a track_in_flight record of a new send: the tape (after logged, not asked); every chunk's write "
     "in a cell"),
    ("window-release-send-kept", "window_release: the send's time not erased", SEC71,
     "    eraseSentAt k\n    freeSlot\n    branch \"window_release: a send released\"\n",
     "    freeSlot\n    branch \"window_release: a send released\"\n",
     "yes", "yes", "yes",
     "the send's timer would free its slot a second time",
     "directed71, a window_release record whose send is in flight: the writes (sent)"),
    ("window-release-no-slot", "window_release: the slot not freed", SEC71,
     "    eraseSentAt k\n    freeSlot\n    branch \"window_release: a send released\"\n",
     "    eraseSentAt k\n    branch \"window_release: a send released\"\n",
     "yes", "yes", "yes",
     "a HAVE would release nothing: the window would run on timers alone",
     "directed71, a window_release record whose send is in flight: the reached functions (free_slot)"),
    ("timeout-of-a-later-send", "window_timeout: a stale timer releases a later send", SEC71,
     "  if (← sentAt? k) == some at_ then                         -- `if sent.get(key) == at:`\n",
     "  if (← sentAt? k).isSome then\n",
     "yes", "open", "open",
     "a chunk sent again would lose its slot at the first copy's timer",
     "directed71, a window_timeout record of the kind \"sent again since\": the writes (sent) and the reached "
     "functions"),
    ("timeout-no-acknowledgement", "window_timeout: the chunk of a planned group not taken as acknowledged", SEC71,
     "    if ← planned k.2.1 then originAcked k.2.1 k.2.2         -- [c3, P4] no claim came in time: released anyway (§5.1)\n", "",
     "yes", "open", "open",
     "[P4] a chunk whose claim never came would never be announced to the mesh peers not pushed it",
     "directed71, a window_timeout record still in flight for a planned group: the tape (origin_acked logged, not "
     "asked)"),
]

# §5.1's origin_acked, the twin's own
PART5C = [
    ("origin-acked-acts-at-publish", "origin_acked: acts at SOURCE_OFFERS = PUBLISH", SEC51,
     "  if (← read).c.SOURCE_OFFERS_PUBLISH then                  -- `if SOURCE_OFFERS == PUBLISH: return`\n"
     "    branch \"origin_acked: at PUBLISH, nothing\"\n    return\n", "",
     "yes", "no", "no",
     "at PUBLISH the offers left at publish and the HAVE grows at the first write: an acknowledgement would send "
     "both again",
     "directed71, an origin_acked or window_timeout record at the node at PUBLISH whose chunk's bit is new: the "
     "tape (the mesh asked) and the writes (origin); no cell of the H or C column runs at PUBLISH (hand5-publish "
     "does)"),
    ("origin-acked-again", "origin_acked: a chunk acknowledged before acts again", SEC51,
     "  if b.has i then                                           -- `if origin[g].has(i): return`\n", "  if false then\n",
     "yes", "open", "open",
     "each later HAVE of a chunk would send the whole HAVE to the mesh and offer the chunk again",
     "directed71, an origin_acked record of the kind \"acknowledged before\" with a mesh: the tape (the mesh asked "
     "where the tape is over)"),
    ("origin-acked-bit-not-set", "origin_acked: the chunk not added to the node's HAVE", SEC51,
     "  setOrigin g (b.set i)                                     -- `origin[g].set(i)`: it joins our HAVE,\n", "",
     "yes", "yes", "yes",
     "the source's HAVE would never grow: its peers would go on asking it",
     "directed71, an origin_acked record of the kind \"the HAVE grows\": the writes (origin) and the HAVE sent (the "
     "tape); every acknowledgement at a cell's source"),
    ("origin-acked-have-not-sent", "origin_acked: the HAVE not sent to the mesh", SEC51,
     "  for q in ← meshList do sendHave q g                       -- which goes to the mesh (§4.2),\n", "",
     "yes", "yes", "yes",
     "the source's holding would grow unseen by its mesh",
     "directed71, an origin_acked record of the kind \"the HAVE grows\" with a mesh: the tape (the mesh logged twice, "
     "asked once) and the reached functions (send_have)"),
    ("origin-acked-targets-announced-too", "origin_acked: the chunk offered to the peers it was pushed to as well", SEC51,
     "    if !((← plannedTargets? g i).getD {}).contains p then   -- announced it: `if p not in planned[g].get(i, ()):`\n",
     "    if true then\n",
     "yes", "open", "open",
     "[c3] the peers chosen for a chunk's push are not offered it; announce takes out what was pushed, so the "
     "offer may be empty, but announce is entered for them and `planned` is not read",
     "directed71, an origin_acked record with a mesh peer among the chunk's planned targets: the reached functions "
     "or the tape, and the read of planned not made"),
    ("origin-acked-nobody-announced", "origin_acked: the mesh peers not pushed the chunk are not announced it", SEC51,
     "  for p in ← meshList do                                    -- and the mesh peers not chosen to be pushed it are\n"
     "    if !((← plannedTargets? g i).getD {}).contains p then   -- announced it: `if p not in planned[g].get(i, ()):`\n"
     "      announce p g (1 <<< i)                                --   `announce(p, g, bitmap({i}))`\n", "",
     "yes", "open", "open",
     "[c3] the acknowledgement is when the source offers a chunk to the rest of its mesh: without it they wait "
     "for gossip",
     "directed71, an origin_acked record of the kind \"the HAVE grows\" with a mesh peer outside the targets: the tape "
     "(the mesh's second question logged, not asked)"),
]

# rules of the 22 functions of mutants_c1.py's TRACED that no mutant there changes. Records exist for each
# (directed1 draws every branch of valid_descriptor; directed46 drops groups): the gap was in the demonstration.
# The cells' columns that were open when the rows were written are as a preflight run counted them; drop_offer's C
# stays open (hand5 and late16 have no record that reaches it)
SEC1, SEC2, SEC42, SEC46 = "SpecTwin/Sec1.lean", "SpecTwin/Sec2.lean", "SpecTwin/Sec42.lean", "SpecTwin/Sec46.lean"
PARTR = [
    ("n-one-more", "N: one more than the descriptor's count", SEC1,
     "  return d.count\n", "  return d.count + 1\n",
     "yes", "yes", "yes",
     "N is the group's chunk count: the claim's bits, a HAVE's width, level 1's index bound",
     "directed1, any N record: the return value"),
    ("valid-descriptor-any-hash", "valid_descriptor: the hash id not checked", SEC1,
     "  if d.hashId != 0 || d.segmentSize == 0 || d.segmentSize > c.MAX_SEGMENT_SIZE then\n",
     "  if d.segmentSize == 0 || d.segmentSize > c.MAX_SEGMENT_SIZE then\n",
     "yes", "no", "no",
     "a descriptor of another hash would be taken (§1: hash_id 0 alone)",
     "directed1, a valid_descriptor record with hash_id not 0 and the rest valid: the return value"),
    ("valid-descriptor-zero-segment", "valid_descriptor: a segment size of zero not refused", SEC1,
     "  if d.hashId != 0 || d.segmentSize == 0 || d.segmentSize > c.MAX_SEGMENT_SIZE then\n",
     "  if d.hashId != 0 || d.segmentSize > c.MAX_SEGMENT_SIZE then\n",
     "yes", "no", "no",
     "K would divide by zero where the document answers False",
     "directed1, a valid_descriptor record with segment_size 0: the twin raises where the Python returns"),
    ("valid-descriptor-zero-length", "valid_descriptor: a total length of zero taken", SEC1,
     "  if d.totalLength == 0 then\n    branch \"valid_descriptor: no length\"\n    return false\n", "",
     "yes", "no", "no",
     "an empty payload has no chunk",
     "directed1, a valid_descriptor record with total_length 0: the return value where count is 0, and the "
     "branch reached"),
    ("valid-descriptor-coded-any-encoding", "valid_descriptor: version 2 with another encoding taken", SEC1,
     "    if d.encoding != 1 then\n      branch \"valid_descriptor: coded, another encoding\"\n      return false\n", "",
     "yes", "no", "no",
     "version 2 is the coded form, encoding 1 alone",
     "directed1, a valid_descriptor record of version 2, encoding not 1, count 2K: the return value"),
    ("valid-descriptor-plain-any-encoding", "valid_descriptor: version 1 with another encoding taken", SEC1,
     "    if d.encoding != 0 then\n      branch \"valid_descriptor: plain, another encoding\"\n      return false\n", "",
     "yes", "no", "no",
     "version 1 is the plain form, encoding 0 alone",
     "directed1, a valid_descriptor record of version 1, encoding not 0, count K: the return value"),
    ("valid-descriptor-coded-count-under", "valid_descriptor: a coded count under 2K taken", SEC1,
     "    let r := d.count == k2 && k2 ≤ c.MAX_CHUNKS\n", "    let r := d.count ≤ k2 && k2 ≤ c.MAX_CHUNKS\n",
     "yes", "no", "no",
     "the coded group has exactly 2K chunks: K data and K parity",
     "directed1, a valid_descriptor record of version 2 with count under 2K: the return value"),
    ("valid-descriptor-plain-count-over", "valid_descriptor: a plain count over K taken", SEC1,
     "    let r := d.count == k && k ≤ c.MAX_PLAIN_CHUNKS\n", "    let r := d.count ≥ k && k ≤ c.MAX_PLAIN_CHUNKS\n",
     "yes", "no", "no",
     "the plain group has exactly K chunks",
     "directed1, a valid_descriptor record of version 1 with count over K: the return value"),
    ("valid-descriptor-any-version", "valid_descriptor: a version that is neither 1 nor 2 taken", SEC1,
     "  branch \"valid_descriptor: no such version\"\n  return false\n",
     "  branch \"valid_descriptor: no such version\"\n  return true\n",
     "yes", "no", "no",
     "§1 has two versions",
     "directed1, a valid_descriptor record of another version, the hash and the sizes in bounds: the return value"),
    ("build-group-size-of-the-body", "build_group: the segment size from the body, not the compressed data", SEC1,
     "  let some size := pyCeilDiv data.n k                        -- `size = ceil(len(data) / K)`\n",
     "  let some size := pyCeilDiv body.n k\n",
     "yes", "yes", "yes",
     "[c6] compress first: the segments are of the compressed data",
     "directed1, a build_group record of a coded body (compression changes its length): the return value and the "
     "tape (pad_each's size)"),
    ("build-group-parity-always", "build_group: parity made for a plain group too", SEC1,
     "  if coded then\n    let padded ← padEach segs size\n",
     "  if true then\n    let padded ← padEach segs size\n",
     "yes", "no", "open",
     "[c6] a group past MAX_CHUNKS coded is sent plain: no parity",
     "directed1, a build_group record of a body too large to code: the tape (pad_each asked)"),
    ("build-group-length-of-the-body", "build_group: the descriptor's total length the body's", SEC1,
     "      count := leaves.length, segmentSize := size, totalLength := data.n, root := root }\n",
     "      count := leaves.length, segmentSize := size, totalLength := body.n, root := root }\n",
     "yes", "yes", "yes",
     "total_length is of what the segments cut: the compressed data",
     "directed1, a build_group record of a coded body: the return value (the descriptor)"),
    ("build-group-shard-index-from-one", "build_group: the shards numbered from one", SEC1,
     "    shards := shards.push { index := i, proof := proof, data := leaf }\n",
     "    shards := shards.push { index := i + 1, proof := proof, data := leaf }\n",
     "yes", "yes", "yes",
     "a shard's index is its leaf's",
     "directed1, any build_group record: the return value"),
    ("group-key-slot-big-endian", "group_key: the slot's bytes in the other order", SEC1,
     "  sha256 (\"03\" ++ gid ++ leHex 8 slot)                       -- `sha256(b\"\\x03\" + gid + uint64_le(slot))`\n",
     "  sha256 (\"03\" ++ gid ++ String.join ((List.range 8).reverse.map fun j => leHex 1 ((slot >>> (8 * j)) % 256)))\n",
     "yes", "yes", "yes",
     "uint64_le",
     "directed1, a group_key record of a slot that is no byte palindrome: the tape (sha256's argument); every "
     "group_key in a cell (slot 1 and up)"),
    ("message-id-index-big-endian", "message_id: the index's bytes in the other order", SEC2,
     "  return .id (f.g ++ leHex 4 f.i ++ (← contentId f)) f.g f.i   -- `f.group + uint32_le(f.index) + content_id(f)`\n",
     "  return .id (f.g ++ String.join ((List.range 4).reverse.map fun j => leHex 1 ((f.i >>> (8 * j)) % 256)) ++ (← contentId f)) f.g f.i\n",
     "yes", "yes", "yes",
     "uint32_le",
     "directed1, a message_id record of an index that is no byte palindrome: the return value; a cell's "
     "message_id of an index of 1 or more"),
    ("drop-offer-urgent-lane", "drop_offer: the urgent lane read where the normal one is filtered", SEC42,
     "  match ← lane? p .normal with                              -- `for e in queue[p].normal:`\n",
     "  match ← lane? p .urgent with\n",
     "yes", "no", "open",
     "an ask queued to the peer is in its normal lane",
     "directed6o, a drop_offer record whose peer has entries in both lanes: the whole state (the normal lane) and "
     "the reads"),
    ("respond-control-alone-dropped", "respond: asks or prunes with no answer are not sent", SEC41,
     "      let _ ← enqueue p (.entry { chunk := none, control, solicited := false }) false\n", "",
     "yes", "yes", "yes",
     "a frame's asks go out in its one response: without an answer to ride on, as an entry of their own",
     "directed41, a respond record with asks and no answer: the tape (enqueue logged, not asked); a cell's "
     "response to an IHAVE"),
    ("drop-group-queued-kept", "drop_group: what is queued of the group stays", SEC46,
     "  discardQueued g                                           -- g's chunks, IHAVEs and IWANTs in every queue, and\n", "",
     "yes", "no", "no",
     "an inconsistent group's chunks would still be sent (§4.6)",
     "directed46, a drop_group record: the tape (discard_queued logged, not asked); no cell drops a group"),
    ("drop-group-history-kept", "drop_group: the group stays in the gossip history", SEC46,
     "  gossipRemoveGroup g                                       -- no further heartbeat announcements of g\n", "",
     "yes", "no", "no",
     "the heartbeat would go on announcing a dropped group",
     "directed46, a drop_group record: the tape (the history's removal logged, not asked)"),
]

# publish. Each row's old text is Sec51.lean's own line (the hand cell's column of three rows is as a preflight run
# counted it: publish-have-every-chunk "no", as no peer is pushed both of hand5's chunks; the two that were open)
PART6 = [
    ('publish-expired-published', 'publish: an expired group is published all the same', SEC51,
     '  if ← expired g then                                       -- `if expired(g) or not live(block.slot): return`\n',
     '  if (← expired g) && false then\n',
     'yes', 'no', 'no',
     '§8.1: too late, nothing of an expired group is stored or sent',
     'directed51, a publish record of the kind "the group expired": the tape (live asked where the tape is over)'),
    ('publish-not-live-published', 'publish: a slot past its live window is published all the same', SEC51,
     '  if !(← live block.slot) then\n',
     '  if !(← live block.slot) && false then\n',
     'yes', 'no', 'no',
     '§8.1: past its live window',
     'directed51, a record of the kind "past its live window": the tape (block_root asked where the tape is over)'),
    ('publish-desc-not-written', "publish: the group's descriptor not kept", SEC51,
     '  setDesc g d                                               -- `desc[g] = d`\n',
     '',
     'yes', 'yes', 'yes',
     'desc[g] is what the node answers a descriptor from, and what N and K read of the group',
     'any record that publishes: the whole state (desc), the writes'),
    ('publish-chunk-no-descriptor', 'publish: the chunk built without its descriptor', SEC51,
     '      { g, i := s.index, slot := block.slot, root := ← blockRoot block, mid := .want g s.index,\n        wide := some { desc := some d, proof := s.proof, data := s.data } }\n',
     '      { g, i := s.index, slot := block.slot, root := ← blockRoot block, mid := .want g s.index,\n        wide := some { desc := none, proof := s.proof, data := s.data } }\n',
     'yes', 'yes', 'yes',
     'design A: the chunk carries the descriptor',
     "any record that publishes: the tape (store's chunk as built)"),
    ('publish-chunk-slot-zero', "publish: the chunk built with slot 0, not the block's", SEC51,
     '      { g, i := s.index, slot := block.slot, root := ← blockRoot block, mid := .want g s.index,\n        wide := some { desc := some d, proof := s.proof, data := s.data } }\n',
     '      { g, i := s.index, slot := 0, root := ← blockRoot block, mid := .want g s.index,\n        wide := some { desc := some d, proof := s.proof, data := s.data } }\n',
     'yes', 'yes', 'yes',
     "a chunk names its block's slot",
     "any record that publishes (no slot is 0): the tape (store's chunk)"),
    ('publish-chunk-proof-dropped', 'publish: the chunk built without its proof', SEC51,
     '      { g, i := s.index, slot := block.slot, root := ← blockRoot block, mid := .want g s.index,\n        wide := some { desc := some d, proof := s.proof, data := s.data } }\n',
     '      { g, i := s.index, slot := block.slot, root := ← blockRoot block, mid := .want g s.index,\n        wide := some { desc := some d, proof := [], data := s.data } }\n',
     'yes', 'yes', 'yes',
     'level 1 at every receiver verifies the proof',
     "any record that publishes: the tape (store's chunk as built)"),
    ('publish-store-next-index', 'publish: the chunk stored under the next index', SEC51,
     '    store g s.index f                                       -- `store(g, s.index, f)`\n',
     '    store g (s.index + 1) f                                       -- `store(g, s.index, f)`\n',
     'yes', 'yes', 'yes',
     "the store is by the chunk's index",
     "any record that publishes: the tape (store's index)"),
    ('publish-not-marked-seen', "publish: the chunk's id not marked seen", SEC51,
     '    markSeen a\n',
     '',
     'yes', 'yes', 'yes',
     'a copy that comes back would be taken as new',
     'any record that publishes: the tape (mark_seen logged, gossip_history.put asked)'),
    ('publish-history-not-put', 'publish: the chunk not put into the gossip history', SEC51,
     '    gossipPut { f with mid := a }                           -- `gossip_history.put(f)` (stock, §6.4)\n',
     '',
     'yes', 'yes', 'yes',
     'stock: heartbeat gossip may announce it (§6.4)',
     'any record that publishes: the tape (the put logged, not asked)'),
    ('publish-mine-one-short', 'publish: mine lacks the last chunk', SEC51,
     '  setMine g ((1 <<< (← N (some d))) - 1)                    -- `mine[g] = all_bits(N(d))`\n',
     '  setMine g ((1 <<< ((← N (some d)) - 1)) - 1)                    -- `mine[g] = all_bits(N(d))`\n',
     'yes', 'yes', 'yes',
     'the source holds every chunk from the start',
     'any record that publishes: the whole state (mine)'),
    ('publish-state-not-complete', "publish: the group's state not set to COMPLETE", SEC51,
     '  setState g .complete                                      -- `state[g] = COMPLETE`\n',
     '',
     'yes', 'yes', 'yes',
     'a complete group is not collected, decoded or dropped',
     'any record that publishes: the whole state (state), the writes'),
    ('publish-stop-pull-not-set', 'publish: stop_pull not set', SEC51,
     '  setStopPull g true                                        -- `stop_pull[g] = True`\n',
     '',
     'yes', 'yes', 'yes',
     'the source asks for nothing of its own group',
     'any record that publishes: the whole state (stop_pull), the writes'),
    ('publish-origin-whole', "publish: the node's HAVE starts with every chunk", SEC51,
     '  setOrigin g 0                                             -- `origin[g] = bitmap(set())` [P4]: none yet\n',
     '  setOrigin g ((1 <<< d.count) - 1)                                             -- `origin[g] = bitmap(set())` [P4]: none yet\n',
     'yes', 'yes', 'yes',
     "[P4] the source's HAVE names the chunks acknowledged (or written) so far: none yet",
     "any record that publishes: the whole state (origin); with a target, the tape (the first HAVE's bits)"),
    ('publish-budget-r-node', "publish: the budget is R_NODE, a forwarding node's, not R", SEC51,
     '    let targets ← choosePush f (← candidatesForSource f) c.R true   -- §5.3\n',
     '    let targets ← choosePush f (← candidatesForSource f) c.R_NODE true   -- §5.3\n',
     'yes', 'no', 'open',
     "[c2] the source pushes R copies; R_NODE is §5.3's, by the node's uplink class",
     "directed51, a record at node 3 (R 3, R_NODE 2) with three candidates or more: the tape (the third copy's enqueue) and the state (pushed, planned); a cell tells it only where a source's R_NODE is not R"),
    ('publish-not-at-source', "publish: choose_push called as a forwarding node's", SEC51,
     '    let targets ← choosePush f (← candidatesForSource f) c.R true   -- §5.3\n',
     '    let targets ← choosePush f (← candidatesForSource f) c.R false   -- §5.3\n',
     'yes', 'yes', 'open',
     '§5.3: at the source the guard does not apply',
     'directed51, a record whose pool has a peer the guard demotes (pushed entries from a publish before, past the grace): the targets'),
    ('publish-note-push-missing', 'publish: a planned push not noted', SEC51,
     '    for p in targets do notePush p g i\n',
     '',
     'yes', 'yes', 'yes',
     '§5.2: pushed says what was pushed to a peer (later plans in the same publish see it)',
     'any record with a target: the whole state (pushed); with two chunks, the later choice'),
    ('publish-copies-chunk-major', 'publish: every copy of a chunk before the next chunk', SEC51,
     '  for copy in List.range c.R do                             -- the first copy of every chunk before any second [c2]\n    for (f, targets) in plan do\n',
     '  for (f, targets) in plan do\n    for copy in List.range c.R do\n',
     'yes', 'yes', 'yes',
     '[c2] the first copy of every chunk before any second',
     'a record with two chunks, one of two targets: the tape (the order of the enqueues)'),
    ('publish-no-first-have', "publish: a peer's first chunk not led by the HAVE", SEC51,
     "        if !led.contains p then                             -- [P4] a peer's first chunk from us follows our HAVE\n",
     '        if false then\n',
     'yes', 'yes', 'yes',
     "[P4] a peer's first chunk from us follows our HAVE naming it",
     "any record with a target: the tape (the urgent enqueue logged, the chunk's asked)"),
    ('publish-have-every-chunk', "publish: the HAVE before every chunk, not a peer's first alone", SEC51,
     "        if !led.contains p then                             -- [P4] a peer's first chunk from us follows our HAVE\n",
     '        if true then\n',
     'yes', 'no', 'yes',
     '[P4] once a peer: its later chunks need none',
     'a record where a peer is pushed two chunks: the tape (a second urgent enqueue)'),
    ('publish-have-without-the-chunk', 'publish: the first HAVE does not name the chunk it leads', SEC51,
     '          let _ ← enqueue p (.have g (o ||| (1 <<< f.i))) true   -- `IDONTWANT(HaveBitmap(g, origin[g] | {f.index}))`\n',
     '          let _ ← enqueue p (.have g o) true   -- `IDONTWANT(HaveBitmap(g, origin[g] | {f.index}))`\n',
     'yes', 'yes', 'yes',
     '[P4] the HAVE names the chunk that follows it',
     "any record with a target: the tape (the HAVE's bits)"),
    ('publish-have-not-urgent', 'publish: the first HAVE queued in the normal lane', SEC51,
     '          let _ ← enqueue p (.have g (o ||| (1 <<< f.i))) true   -- `IDONTWANT(HaveBitmap(g, origin[g] | {f.index}))`\n',
     '          let _ ← enqueue p (.have g (o ||| (1 <<< f.i))) false   -- `IDONTWANT(HaveBitmap(g, origin[g] | {f.index}))`\n',
     'yes', 'yes', 'yes',
     'the HAVE must leave before the chunk it leads: urgent',
     "any record with a target: the tape (enqueue's urgent)"),
    ('publish-refused-not-unpushed', 'publish: a refused push stays noted as pushed', SEC51,
     '          unpush p g f.i\n',
     '',
     'yes', 'no', 'open',
     '§5.2: a refused push is offered instead (unpush owes it)',
     'directed51, a record of the kinds "pushes refused": the whole state (pushed, owed)'),
    ('publish-planned-row-kept', "publish: the plan's row not replaced whole", SEC51,
     '  erasePlannedRow g                                         -- `planned[g] = {f.index: set(targets) for …}`: the row\n',
     '',
     'yes', 'no', 'no',
     "[c3] planned[g] is this publish's plan",
     'directed51, a record of the kind "published again": the writes (the row), and the state where the plan before had an index this one has not'),
    ('publish-planned-first-target', "publish: the plan keeps a chunk's first target alone", SEC51,
     '    setPlanned g f.i (Std.HashSet.ofList targets)\n',
     '    setPlanned g f.i (Std.HashSet.ofList (targets.take 1))\n',
     'yes', 'yes', 'yes',
     '[c3] the mesh peers not chosen to be pushed a chunk are announced it: every target counts as chosen',
     'a record with a chunk of two targets: the whole state (planned)'),
    ('publish-offers-always', 'publish: the offers at publish at SOURCE_OFFERS = ACK too', SEC51,
     '  if c.SOURCE_OFFERS_PUBLISH then                           -- `if SOURCE_OFFERS == PUBLISH:` the offers now (§5.1)\n',
     '  if true then\n',
     'yes', 'yes', 'yes',
     "§5.1: at ACK the offers come at each chunk's acknowledgement",
     "a record at a node at ACK with a mesh peer that is not a chunk's target: the tape (the mesh asked) and the branch"),
    ('publish-offers-never', 'publish: no offers at publish at SOURCE_OFFERS = PUBLISH', SEC51,
     '  if c.SOURCE_OFFERS_PUBLISH then                           -- `if SOURCE_OFFERS == PUBLISH:` the offers now (§5.1)\n',
     '  if false then\n',
     'yes', 'no', 'no',
     '§5.1: at PUBLISH the source offers at once',
     'directed51, a record at node 4 that publishes with a mesh: the tape (the mesh asked) (hand5-publish too; no cell of the H or C column runs at PUBLISH)'),
    ('publish-offers-to-targets-too', "publish: at PUBLISH a chunk's targets are offered it too", SEC51,
     '        if !targets.contains p then announce p g (1 <<< f.i)\n',
     '        announce p g (1 <<< f.i)\n',
     'yes', 'no', 'no',
     '[c3] the peers pushed a chunk need no offer of it',
     'directed51, a record at node 4 with a target in the mesh: what announce reaches and reads for that peer'),
]

# v0.10.7's line (protocol.md §7.1 and §7.2 at spec 903f12b): front and wake_front, and the writer in
# line that writes control. Written before any was built; C "open" where no cell's reach was counted
PART7 = [
    ("front-takes-a-writer-mid-write", "front: a writer mid-write taken for the first that can write (the line before v0.10.7)", SEC71,
     '    if ← writing q then branch "front: a writer mid-write passed"   -- a writer whose write has not completed\n    else return some q                                      --   (§7.3) keeps its place\n',
     "    let _ ← writing q\n    return some q\n",
     "yes", "no", "open",
     "a writer whose write has not completed holds the line's front: the head-of-line stall v0.10.7 removes "
     "(toy/line_stall_known.py)",
     "directed71, a front record of the kind \"a writer mid-write passed\": the return value"),
    ("wake-front-wakes-a-writer-mid-write", "wake_front: the line's first woken, mid-write or not", SEC71,
     '  match ← front with                                        -- `q = front()`\n',
     "  match (← waitersLine .line).head? with\n",
     "yes", "no", "open",
     "a free slot wakes a writer that cannot write, and the next that can waits for another (v0.10.9: wake_front "
     "asks front)",
     "directed71, a wake_front record of the kind \"the first passed\": the tape (the wake of the writer mid-write, "
     "and no writing asked)"),
    ("wake-front-with-no-slot", "wake_front: a writer woken with no slot free", SEC71,
     '  if !(← underW (← inFlight .count)) then                   -- `if in_flight >= W: return`\n    branch "wake_front: no slot free"\n    return\n',
     "  let _ ← inFlight .count\n",
     "yes", "no", "open",
     "a writer is woken to find the window full and goes back to its place: a turn for nothing",
     "directed71, a wake_front record of the kind \"no slot free\" with somebody in line that can write: the tape "
     "(wake logged, not asked)"),
    ("release-next-not-woken", "release_unused_slot: the next in line that can write not woken when the peer leaves", SEC71,
     '    wakeFront                                               --   may take a free slot\n', "",
     "yes", "no", "open",
     "a writer that leaves the line with a slot free leaves it to nobody until the next release",
     "directed71, a release_unused_slot record of the kind \"the next that can write woken\": the tape (wake logged, not "
     "asked)"),
]

# v0.10.9's wake (protocol.md §7.1 and §7.2 at spec 5372ebb): next_to_send's urgent branch and its branch of owed
# offers alone no longer call wake_front (release_unused_slot still calls it, for a writer that leaves the line or
# gives back a slot); write_waits calls it for a writer in line whose write starts to wait. wake_front wakes the
# line's front only while a slot is free. The rule before it, as mutants (its pre-wakes, calling v0.10.9's
# wake_front, which has no `past`, so the front it wakes can be the writer itself), and write_waits's own. Written
# before any was built; C "open" where no cell's reach was counted
PART7B = [
    ("nts-urgent-wakes-first", "next_to_send: a writer in line that writes an urgent entry calls wake_front "
     "first (as the rule before v0.10.9, without its `past`)", SEC72,
     "  | e :: rest =>\n    setLane p .urgent rest                                  -- `q.urgent.pop(0)`\n",
     "  | e :: rest =>\n    if (← waitersLine .line).contains p then wakeFront\n    setLane p .urgent rest\n",
     "yes", "no", "open",
     "a write that completes at once can queue an extra run of the line's front, and the schedule moves where "
     "nothing should (as rr-stripe's and push-deep's digests did at 903f12b, under the rule with `past`)",
     "directed7, a next_to_send record with an urgent entry, the peer in line and a slot free: the tape (wake logged, "
     "not asked) and the reads (the line, the count)"),
    ("nts-owed-alone-wakes-first", "next_to_send: a writer in line that writes owed offers alone calls "
     "wake_front first (as the rule before v0.10.9, without its `past`)", SEC72,
     "    if let some o := out then\n      branch \"next_to_send: owed offers alone\"\n",
     "    if let some o := out then\n      if (← waitersLine .line).contains p then wakeFront\n"
     "      branch \"next_to_send: owed offers alone\"\n",
     "yes", "no", "open",
     "as for an urgent entry: owed offers are control too",
     "directed7, a next_to_send record of the kind owed offers alone, the peer in line and a slot free: the tape "
     "(wake logged, not asked) and the reads (the line, the count)"),
    ("write-waits-wakes-nobody", "write_waits: a writer in line whose write waits wakes no one", SEC71,
     "  if (← waitersLine .line).contains p then                  -- `if p in waiters: wake_front()`\n    wakeFront\n",
     "  if (← waitersLine .line).contains p then                  -- `if p in waiters: wake_front()`\n    pure ()\n",
     "yes", "no", "open",
     "the writer in line writes control, its write waits (§7.3), and the slot stays free while the next that can "
     "write waits: the toy monitor's W2 (its break writewait), the lost wake of 1dc2d93",
     "directed71, a write_waits record of the kind \"the first woken\": the tape (wake logged, not asked) and the "
     "reads (the count)"),
    ("write-waits-wakes-out-of-line", "write_waits: the line's front woken whether or not the writer is in line", SEC71,
     "  if (← waitersLine .line).contains p then                  -- `if p in waiters: wake_front()`\n",
     "  if true then\n",
     "yes", "no", "open",
     "every write that waits wakes the line's front, in line or not: the schedule moves wherever a write waits",
     "directed71, a write_waits record of the kind \"the peer not in line\" with a slot free and somebody in line "
     "that can write: the tape (the wake); with no slot free, the line's read left unmade"),
]

ROWS = PART0 + PART1 + PART2 + PART4 + PARTB + PARTC + PART5B + PART5C + PARTR + PART6 + PART7 + PART7B
assert len({r[0] for r in ROWS}) == len(ROWS), "a name twice"
CYCLE2 = {r[0]: (r[1], r[2], r[3], r[4]) for r in ROWS}
PRED = {r[0]: {"D": r[5], "H": r[6], "C": r[7], "why": r[8], "witness": r[9]} for r in ROWS}
# PART2's cells column, restated with forward the twin's: the cells' on_frame records run the draw, the ranks and
# the guard at every forwarding node. "no" stays where a cell cannot show it: two equal tie-breaks (64 bits of a
# hash), a clock at the grace exactly.
RESTATED_C = {"guard-more-than-r": "open", "guard-no-grace": "open", "guard-empty-have-not-counted": "open",
              "choose-known-without-have": "open", "choose-unproven-not-last": "open",
              "choose-demoted-in-the-draw": "open", "choose-median-upper": "open", "choose-pool-below-median": "yes",
              "choose-draw-of-budget": "open", "choose-drawn-not-first": "open",
              "guard-at-the-grace": "no", "choose-id-not-compared": "no"}
for _k, _v in RESTATED_C.items():
    PRED[_k]["C"] = _v
TABLE_OF = {"tables-origin-read-none": "origin", "tables-planned-row-read-false": "planned",
            "tables-pushed-read-none": "pushed", "tables-desc-read-none": "desc",
            "tables-pushed-write-not-made": "pushed",
            "tables-in-flight-write-not-made": "in_flight", "tables-waiters-read-reversed": "waiters",
            "tables-sent-erase-not-made": "sent"}      # the window's three
# the operations of TABLE_OF's tables and their fields of the state, by their exact names (mutants3.py's TABLE_NAMES)
TABLE_NAMES = {"origin": ("origin", "setOrigin", "allOrigin"),
               "planned": ("planned", "plannedTargets?", "setPlanned", "erasePlannedRow", "allPlannedAll"),
               "pushed": ("pushedEntry?", "setPushed", "allPushed", "pushed"),
               "desc": ("desc", "setDesc", "allDesc"),
               "in_flight": ("inFlight", "setInFlight", "allInFlight"),       # PART5B: in_flight, waiters, sent
               "waiters": ("waitersLine", "setWaitersLine", "allWaiters", "waiters"),
               "sent": ("sentAt?", "setSentAt", "eraseSentAt", "allSent", "sent")}
