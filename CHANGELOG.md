# Changelog

Each release is a tag (its commit in the heading below), and `protocol.md` names its version at the top.
Changes after the latest tag are on `main`; when there are any, this file's first entry names them. A
release changes the text and its checks, not earlier measurements: each measurement says which code it
ran (`protocol.md` §9 for the SEACAST post's figures).

## v0.10.6, 2026-11-19

`protocol.md` names an open question in §1: whether the protocol fixes a coded group's compressed
bytes. No rule, value or code of `protocol.md` changes.

The next version's draft carries `protocol.md` v0.10.4's rule on an IDONTWANT entry that is not a
HAVE bitmap onto v0.3's wire, is rewritten for readers, and makes two code changes: an ask sent as a
`Want` starts no promise, but a claim's probe; and a second id for a received index goes no further,
as in `protocol.md`. It carries v0.10.5, whose toy fix changes none of its rules; §5 and §6.1 say
what it shows.

`protocol.md`:
- **Open: the compressed bytes** (§1). A coded group's root commits the bytes its builder's
  compressor produced, and a node checks the group by decoding, which needs no compressor. The open
  alternative is a canonical compressor: the chunks would follow from the body and the group's
  descriptor, so that a node that got the body from elsewhere could build and serve them, at the
  cost of every client reproducing that compressor's output byte for byte. The glossary gains
  **canonical compressor**.

`protocol-v2-bindings.md`:
- **An IDONTWANT's entries on v0.3's wire** (§3) are read as `protocol.md` §4.1 reads them: one that
  `is_have_bitmap` accepts is a holding, and any other is a stock id, kept in `unwanted[p]`, where
  `on_want` reads it. The standalone and the extension bindings put no stock ids beside a holding.
- **The backoff on the gossipsub bindings** (§2, §3): where a GRAFT is accepted in silence,
  gossipsub's backoff after a PRUNE keeps the two ends of a relation together (each end holds it
  from a PRUNE sent or received, and refuses a GRAFT within it). It must outlast the link's longest
  round trip at each end that may prune: a shorter one can fail, and with a longer one the toy's
  abstract model finds the ends agreed in every state at rest it reaches (a bounded check).
  Gossipsub's recommended minute meets that on any link whose round trip is shorter; the bindings
  set no backoff of their own.
- **v0.3's wire** (§3) reads as a holding an entry with `HaveBitmap`'s MAGIC at either version it
  writes (at version 4 with its flags byte), and ignores an IHAVE entry that is not a bitmap.
- **The payload's chunk under either design** (§1.3, §1.6, §1.7): it carries the descriptor under
  design A, its body at most 33 351 bytes, and not under design B, where the bid carries it, its
  body at most 33 300; `protocol.md` §1 leaves the choice open.

`protocol-v2.md`:
- **Where the descriptor travels, left open** as `protocol.md` §1 leaves it: in the chunk (design A,
  which the toy runs) or in the bid (design B), in §1.1's `header_of` row, §2 and `publish`'s
  comment, where the draft had taken A.
- **§1.1's `decode` row points to `protocol.md` §1's "Open: the compressed bytes"**: a coded
  group's root commits the bytes its builder's compressor produced from the body, and whether a
  canonical compressor should fix those bytes is open.
- **Rewritten for readers, in the form `protocol.md` has since v0.10.1.** The rules stay with their
  code, each a paragraph or an item with a bold lead. Dates, reasons, earlier drafts and the toy's
  figures move to a Rationale closing each section, and what is left open to **Open:** items. §6.3's
  table keeps each parameter's decision and bound, with its figures in a Rationale and what is for
  later study in an Open list. The record of each `protocol.md` version carried moves to §5. The
  rewrite leaves the code the same, comments included but one, and changes no rule.
- **An ask not made on an offer starts no promise, in the code** (§4.6's `filter_entry`). The rule
  §4.10 and §5 state was kept by the toy in a wrapper; the document's own `filter_entry` started
  v0.5's promise for every ask it wrote. Now it starts one only for an ask the pull discipline makes
  on an offer, not for one sent as a `Want` (`want`, defined with `send` in §3); a claim's probe
  keeps its own at its first write, and gets v0.5's at a write again once that one is gone.
  `want_promise_known.py` checks the promise of each kind, and fails on the document before. Runs of
  the toy with samplers, routed requests and the repair sample send the same, at the same times, as
  before.
- **A second id for a received index goes no further** (§4.2's `on_validated`, §4.4's `forward`).
  Axis by axis: a copy under an id the node has not seen, at an index it has already received on an
  axis, is acknowledged there and is no longer forwarded on that axis, as `protocol.md` §4.2 does,
  nor kept for heartbeat gossip unless some axis forwards it. A copy of an index held only as
  rebuilt, or one the node published, is still forwarded. `second_id_known.py` checks both
  documents, and fails on this one before. No recorded cell has two ids for one index.
- **Statements made true to the code.** §4.6: what `note_push` notes (a push, and an answer to a
  standing WANT or a kept probe) and what the note stops. §4.7: a chunk that is never acknowledged,
  as `protocol.md` §5.1's open item names it, in place of a copy lost with its connection. §4.7,
  §4.8 and §5: heartbeat gossip only for a type whose `ANNOUNCE_EXTRA` is `SAMPLE`. §1.6, §4.7 and
  §5: no cap over whole messages, which `protocol.md` does not have. §6.1: three differences in the
  rules, which no recorded cell exercises (a source with an empty mesh, more ids for a rebuilt
  index, each of which this document forwards, and an IHAVE entry by id). And conditions the code
  has where the text left them out: the coverage floor's links and a routed request's steps (§1.3),
  who asks without an offer (§4.1), the holding's acknowledgement, a start-delayed offer and the
  last resort (§4.3), the probe's draw and write, its refusal at the serving limit and a kept
  probe's answer, the repair sample's cells and re-ask, a sample with no cell to ask, and the
  alarm's answer (§4.6), what carries over at the source and its pool (§4.7), card 12's pushes only
  (§4.9), what `SERVE_LIMIT` counts, which WANT starts a promise, a first-phase sample with no peer
  and when the hunt ends (§4.10), the writer's order (§4.12), v0.3's two clocks (§4.13), and in §6.3
  the IHAVE row's values as `protocol.md`'s and `PROMISE` as one value per node.
- **Its line on v0.10.4** (now in §5) says what it carries: the IDONTWANT rule above; the source's
  heartbeat gossip, which §4.7 names for a type that gossips; and §4.7's open item on a chunk that
  is never acknowledged, `protocol.md` §5.1's. Its line on v0.10.5 says what the toy's `accepted`
  fix changes under this draft; §6.1 adds the one difference it opens: at an index held only as
  rebuilt, a repeat of a seen id is acknowledged where that id was stored, by `protocol.md` the
  first network copy's id, which it stores over the rebuilt one, and here the rebuilt chunk's own
  (`second_id_known.py`).

The toy:
- **`--doc v2` keeps an IDONTWANT's stock id in `unwanted[p]`**, after the frame's asks, where it
  dropped it. `idontwant_id_known.py --doc v2` checks it and fails on the toy before. No recorded cell
  sends such an entry, and every recorded cell gives its recorded events.
- **`--doc v2` runs the document's `filter_entry` unwrapped**, now that the document keeps an ask
  sent as a `Want` from starting a promise; the IWANT such an ask is written as carries `want`. The
  recorded cells send none and give their recorded events. In the runs compared that send them, the
  only events gone are promise timers that found nothing, so a run's event digest changes and
  nothing it sends does.

## v0.10.5, 2026-11-19 (`662c526`)

The proofs in `formal/veil/` move to Veil's release v4.35.0, and gain malicious peers, runs that go
quiet (Q3) and agreement. They stay proofs of v0.8's rules, and their README lists what changed
since. No rule, value or code of `protocol.md` changes. The toy's `accepted` now answers whether the
id was stored, as `protocol.md` says.

`formal/veil/`:
- **Veil's release v4.35.0** (Lean 4.35.0), in place of a pre-release. The six models keep their
  results, with raised solver limits; the transport and the asking under equivocation gain Q3's
  actions (190 to 200 and 660 to 704 conditions).
- **A run goes quiet (Q3).** With finitely many nodes and weak fairness, once the environment stops,
  the transport and v0.8's asking (with `NO_REASK_OPEN`) eventually have nothing left to do, for
  good (`QuietRanking.lean`, and `quiet` in `NoStallTransport.lean` and `NoStallEquiv.lean`).
- **Malicious peers** (`NoStallAskAdv.lean`, `NoStallTransportAdv.lean`, `NoStallEquivAdv.lean`).
  Q1 holds for the honest nodes the source reaches through honest nodes that installed the block,
  relabelled copies excluded, and Q3 once the environment stops, the adversaries' actions included.
  Two findings, both already in `protocol.md`:
  - F13: dropped offers that leave their ask; v0.8's `drop_offer` (§6.1) closes it;
  - F14: an announcer that is never parked holds the last resort off; §6.1 leaves it open.

  `NoStallEquivAdv.lean`'s switch `byGroup` checks the asking under level 1 by group, one of the
  options §4.6 lists for relabelled copies; it is off for the spec's rules.
- **The counting through honest nodes, and three corollaries** (`NoStallCount.lean`): Q1 with a
  builder that releases only K of the N chunks, with a source that drops out, and with nodes that
  never install the block, with two known answers.
- **Agreement and integrity** (`Agreement.lean`, plain Lean): level 2 is all or none, a check that
  succeeds recovers the committed bytes, and two honest nodes never deliver different payloads for a
  group, under the codec's assumptions the README lists, an MDS code and a binding hash among them.
- **The README** gives the results of the whole library's build, and says which of `protocol.md`'s
  changes since v0.8 the models do not have; it also corrects `SenderFault.lean`'s clause count.
  `README.md` and `formal/README.md` describe the new proofs. The new models say "the last resort",
  as `protocol.md` does.

The toy:
- **`accepted(mid)` answers whether the id was stored**, as `protocol.md`'s helper list says, where it
  answered whether the id's index was stored. So a later copy of a copy that level 1 rejected, or of a
  second copy with its own id, is no longer acknowledged, and under `protocol-v2.md` it no longer
  passes the probe. Two known answers, `accepted_id_known.py` and `probe_replay_known.py`, fail on the
  toy before the fix; `accepted` reads the id stored at the index now, and the case where a copy with
  its own id is stored over a rebuilt one belongs to relabelled copies, which `protocol.md` names open.

## v0.10.4, 2026-11-18 (`34f60f8`)

The repository is renamed `seacast-spec`, from `informed-diffusion-spec`, which GitHub redirects, and
`protocol.md`'s title is now *SEACAST: the protocol in pseudocode*; the README's heading, its release
link and its line on the old title follow. `protocol.md` also says what heartbeat gossip tells of the
source and names a chunk that is never acknowledged as open; and its `on_frame` keeps an IDONTWANT
entry that is not a HAVE bitmap as stock gossipsub keeps an id, where it handed every entry to
`on_have`: the one code change, whose new branch no recorded cell reaches. The toy follows both
documents at a dropped group, and in how it reads bitmaps and ids.

The next version's draft carries `protocol.md` v0.10.3's changes, lets any source offer its chunks at publish,
its own choice as in `protocol.md`, closes the probe's last open cases, and measures its probe and alarm
figures again. Its bindings move to a document of their own, which defines the standalone binding to the
byte.

`protocol.md`:
- **The source's chunks in heartbeat gossip** (§5.1's Rationale, §5.4's bullet "At the source" and its
  Rationale): `publish` puts every chunk in the gossip history, so each of the source's next three
  heartbeats announces them to its sample outside the mesh, at `ACK` without waiting for their
  acknowledgement. §5.4 said the source's announcement stays inside the mesh: that holds for the
  join's, as for §5.1's at the acknowledgement or at publish, and not for heartbeat gossip. Keeping the
  chunks out of the gossip history until acknowledged is left to the work on the source's privacy.
- **Open: a chunk that is never acknowledged** (§5.1). At `ACK`, a chunk whose pushes are all refused,
  skipped, left queued to a peer that does not read, or lost with their connections has no
  acknowledgement, and is announced to the rest of the mesh only once a HAVE naming it reaches the
  source (a peer's claim of a forwarded or rebuilt copy, or a decode claim), or once the source's
  answer to a peer's ask is acknowledged; at `PUBLISH` it is announced at publish.
- **Where the source's announcements go, said exactly:** §2's IHAVE row names the source's step and
  the mesh join; §5.1 says that a refused push to a mesh peer is offered to it instead; §5.1's bullet
  on the acknowledgement, §7.1 and §9 say that those announcements go to the mesh.
- **An IDONTWANT entry that is not a HAVE bitmap is kept as stock gossipsub keeps an id** (§4.1's
  `on_frame`, and `is_have_bitmap` among the helpers). An IDONTWANT names no topic, so beside the HAVE
  bitmaps its entries can be stock message ids; `on_frame` handed every entry to `on_have`, which needs a
  bitmap. It now hands it the bitmaps and keeps any other entry in `unwanted[p]`, as its comment said,
  and §4.1 says why. A string is a bitmap if it opens with `HaveBitmap`'s MAGIC and VERSION and holds a
  group after them, so a stock id of 20 bytes is never taken for one. No recorded cell sends an entry
  that is not a bitmap, so every digest stays.

The draft's bindings, in a new document, `protocol-v2-bindings.md`:
- **`protocol-v2.md` §7 now says what every binding provides:** links with their open and close,
  whole messages in order per object type at least, the queue and the write, limits before state,
  the header before or with a group's first cell, agreement on the fork, and a chunk's id and size. It also lists the capabilities the three bindings differ in, with what the
  rules do without each.
- **The new document** takes the old §7's mappings, and its rules for a sampler on gossipsub's wires.
- **It defines the standalone binding to the byte:**
  - the protocol id `/seacast/2.0.0`, one outbound stream per peer;
  - one encoded message, a kind byte and its SSZ: after a uvarint length on its own stream, and in
    Waggle's `ObjectPieces` without one;
  - snappy on chunks only;
  - one 35-byte group id for every object type, and `protocol.md`'s bitmap;
  - the payload's chunk as `protocol.md`'s, and a cell chunk with the consensus column header;
  - the fork digest in the JOIN, with the transition at a fork left open;
  - a chunk's id without a topic, and one id per cell whichever group carries it;
  - the header with a group's first eager push, none with an answer; a node pushed nothing, such as a
    sampler, takes it from the block; a carried header validated apart from the cell, never marking its
    id;
  - a bound per message kind, an unknown kind held to the largest, and the bitmap's bit order.
- **Terms:** the prose says frame, a binding's unit on the wire, where it said RPC.
- **A carried header that fails its checks is rejected** and counts against its sender; one that cannot be
  judged yet waits and counts against no one, as consensus ignores it (§1.3).

The draft of SEACAST's next version (`protocol-v2.md`), changed since v0.10.3:
- **When a source offers is its own choice** (§4.7, §6.3's `SOURCE_OFFERS`): at the acknowledgement by
  default, as `protocol.md` has it, or at publish, its holding then growing at each chunk's first write
  (`origin_written`) and an acknowledgement doing nothing. No rule at another node needs either setting. A fast source finishes sooner offering at publish, a
  slow one later, and offers at publish name the source. In the toy's custody cell a 1 Gbps proposer
  offering at publish completes 13 to 114 ms sooner and answers 4.7 to 12 times as many asks; copies move
  either way with the graph. `toy/run.py --source-offers publish` sets it; `toy/source_offers_known.py`.
- **"Acknowledged", as `protocol.md` now says it** (§4.7): the source's holding names the chunks
  acknowledged so far, where the draft said "known to have arrived"; wording and comments only.
- **`protocol.md` §8.3's kinds:** §6.3's four rows that said "a limit, stated by its bound" (`FORWARD_LIMIT`,
  groups tracked per slot, relations per link, sampling-only links accepted) say "a bound", each node's
  within it: in §8.3's terms a limit is the same at every node, and a value each node sets within a stated
  bound is a bound. Wording only.
- **The IHAVE limits at `protocol.md`'s reference values** (§4.3, §6.3): 4096 offer-bearing frames and 5000
  ids per peer and heartbeat hold back no ask in the toy's 60-node cells under the tier 4 setting,
  variant C and custody, with or without samplers. The busiest peer reached 248 frames and 58 asks
  in a heartbeat. Under the rows setting (seeds 7 to 9, with and without half the columns withheld) none
  is held back either, the busiest peer at 1 254 frames and 178 asks. The draft chooses no values of its
  own; 500 nodes, other seeds outside the rows setting and a peer that floods offers are not yet run.
- **A dropped group's chunk is not acted on** (§3, §4.4, §4.6): `on_validated`, `forward` and `push_rebuilt`
  skip an axis whose group was dropped, as `protocol.md`'s `on_validated` returns. The draft forwarded such a chunk and
  offered it, so an asker's promise broke against an honest node, and put it in the gossip history.
  The cell's other axes go on. No recorded cell drops a group. `toy/dropped_group_known.py`.
- **A pull-only type's source offers at publish** (§4.7, §6.3's `EAGER` row): `EAGER` off covers the
  source too. It pushes nothing, so no acknowledgement can come, and it offers every chunk at publish to
  the peers it would offer at the acknowledgement; its holding names every chunk (`offer_at_publish`).
  The draft pushed `R` copies whatever `EAGER` said. No setting publishes a pull-only type.
  `toy/pull_source_known.py`.
- **A decode answers its own group's standing WANTs.** `decode_group` stored a group's rebuilt chunks
  without answering the standing WANTs that waited for them; only the other groups a rebuilt chunk
  fills answered theirs, through `fill`. It now calls `serve_standing` as `fill` does (§4.5). No
  recorded cell moves, and the sampler cells behind §4.10's figures decode nothing.
- **The window counts what a write carries** (`wire_size(p, entry)`, §3, §4.11): the binding's size of
  the entry's chunk to that peer, with the header a cell's first push carries on the standalone binding.
- **A send is noted under every group the chunk fills** (`note_push`, §4.4, R4), from the ids alone
  (`fills`), and a push not made is undone under each (`unpush`): a cell answered through its row is not
  pushed again through its column by the repair, and the other way round.
- **A note, not a rule** (§4.2): the pseudocode scans whole tables to find what names one chunk
  (`drop_beyond`, and `protocol.md`'s `close_promises`), and an implementation is expected to index them
  by group and index.
- **The probe's figures measured on this draft** (§4.6): the five rows cells at seeds 7 to 9, on the rules as
  they stand. None of 1 281 verdicts on honest or hoarding claimants failed, liars passed 1, 0 and 65
  times, and the mark cost 5 duplicate cells in 2 417 probes; every probe was written, the longest wait
  163 ms. The figures with the rules of 2026-11-16 are kept, labelled as such, and the paragraph that said
  what those runs did not show is gone.
- **The alarm measured again where it acts** (§4.6): the one-column hoarder's 500-node cells at seeds 11, 12
  and 16. Without the alarm 2 of 6 blocks are short (108 custodians), one fewer than before; with it none,
  for 61 alarms and 10 rebuilds, as before. The ten-seed figures are kept, labelled as measured earlier.
- **A settled probe's ask is no longer exempt from stop-pull** (`settle_probe`, §4.6): after the verdict the
  member pulls the probed cell from nobody, as it pulls no other cell of the row once complete.
- **An asker's second marked ask is a plain ask** (`probe_of_claim`, §4.6): while a claimant still decoding
  keeps an asker's probe, that asker's marked ask of another index of the group takes no exemption, so the
  kept probe is still answered, which a faulty asker's second marked ask could prevent before.

The toy:
- **`--wire standalone`** charges the links the standalone binding's bytes (`protocol-v2-bindings.md`
  §1), each message a frame of its own and a cell's header with the first eager push of its group on
  a link; v0.3's wire stays the default. On `check.py`'s 15 cells under `--doc v2` control bytes fall
  30 to 36 % and all bytes 1.5 to 3 %, and 4.2 % in two custody cells, where the header spends what
  the smaller cells save (`toy/README.md`). The toy's frame names replace its RPC names.
- **The custodian alarm (an option, off)**: the member's ask of the claimant starts its promise at the
  write, as the probe's does, not at the decision. A claimant that cannot be asked, because its
  connection has closed or a full queue refuses the ask, or whose connection closes before the promise
  ends, is no longer penalised; the member rebuilds if the cell is still missing. The alarm's figures
  were measured before (§4.6).
- **A connection's close (`--churn`)** also takes the closed peer out of the window's line, where at the head
  it stalled every writer behind it, and releases the room its chunks held in flight, as `WINDOW_TIMEOUT`
  releases it (`protocol.md` §8.1), but without the acknowledgement a timeout gives (`close_source_known.py`).
- **Known answers** for the changes above: `toy/standing_decode_known.py`, `toy/probe_asks_known.py`,
  `toy/probe_kept_known.py`, `toy/alarm_member_known.py`, `toy/standalone_wire_known.py`,
  `toy/standalone_charge_known.py`, `toy/rebuilt_once_known.py` and `toy/note_push_known.py`, and those named
  in their items.
- **`toy/idontwant_id_known.py`:** a stock id in an IDONTWANT is kept in `unwanted[p]`, with no penalty, and a
  HAVE bitmap beside it is read as a HAVE and not kept there; run on the document before, the toy stops in
  `on_have`, which the stock id reached.
- **The toy follows the documents at a dropped group, and in how it reads bitmaps and ids** (`toy/node.py`,
  on both documents):
  - `discard_queued` takes a dropped group's IHAVEs and IWANTs out of both lanes of every queue, as §4.6
    says, keeping the other groups' control that rides with them, where it took only the group's chunks;
    an entry left with control only is no longer an answer (`toy/discard_queued_known.py`);
  - `discard_paced` takes the group out of the paced jobs, where it did nothing, so a paced IHAVE of a
    dropped group no longer goes out at the next tick (`toy/discard_paced_known.py`);
  - `accepted` is "the id was stored", as §8.1 says, so a copy of a chunk that a dropped group stored is
    acknowledged (`toy/dropped_dup_known.py`);
  - `valid_have` checks a bitmap's length against `MAX_HAVE_BYTES`, as §8.2 says, also where the group's
    count is not known (`toy/have_length_known.py`);
  - an ask by id names a group and an index only as a structured id of exactly 56 bytes (§2,
    `group_index`), where the toy read any id of 36 bytes or more as one (`toy/id_parse_known.py`).

  No recorded cell drops a group or sends such a bitmap or id, so every digest stays.
- **Unchanged:** every recorded cell's digest in `golden.txt` and `golden-v2.txt`.

## v0.10.3, 2026-11-18 (`afc85e8`)

`protocol.md` sorts its constants into limits, bounds and defaults, gives gossipsub's two IHAVE limits
reference values, calls what a peer writes on its stream a frame, and lets a source announce its
chunks at publish, its own choice, the acknowledgement staying the default. None of the values it gave
before changes, and at the defaults the code does all it did; its §1 says what the open choice of where
the descriptor travels decides. The next version's draft carries v0.10's rules where it has
functions of its own, follows §8.1's lifetimes at a connection's close, and settles the probe of a
claim's open cases; its figures are measured again.

`protocol.md`:
- **§1 says what the descriptor's placement decides**, in its Rationale, under "Where the descriptor
  travels": when a node knows a group's shape, what a copy shows before its block, what the bid fixes
  and what a chunk carries, with the descriptor in the chunk (design A) or in the bid (design B). The
  choice stays open; the "Open:" paragraph points to the Rationale, and its sentence on the bytes
  moves there.
- **The constants in three kinds** (§8.3): limits, the same at every node; bounds, each node's within
  a bound given with what needs it; and defaults, each node's own, at the document's reference values.
  The rules the defaults enter stay rules: one broken promise parks, every offer is kept, and the last
  resort asks once more. A Rationale closes §8.3, §0 says which constants every node shares, the
  glossary which limits are which, and §8.2 lists the offers' 16 and 256 with what the client sets.
  `UNIT` is the builder's (§1, "The cut", which says which cuts give a valid group). Constants that had
  one value each are bounds: `R` and `R_FAST`, at least 1; `GUARD_GRACE`, longer than an honest peer's
  first HAVE takes, which a peer still waiting for its block does not send (§5.3 says so too); and
  `GOSSIP_RETRANSMISSION`, at least 3, which §6.1's rules count on. `MAX_SEGMENT_SIZE` is written as
  its value, 32 KiB, so that a builder's `UNIT` does not change it: the one code line this changes.
  §8.1's tombstone without a slot counts on the peer's `HAVE_TTL`, and §6.1's six asks are at the
  default `PROMISE`. `UNIT`'s reason names the post's variant A, which is not §1's design A.
- **Reference values for gossipsub's two IHAVE limits** (§8.3): 4096 IHAVE-bearing frames and 5000 ids
  asked, per peer and heartbeat, where §8.3 gave none: the numbers the measurements ran with, on a
  handler that counted every control-bearing frame (§9). They stay each node's own, and a limit still
  delays asks and loses no offer (§4.4); §4.4 and §8.2 point to them. At these values the toy's
  recorded cells hold back no ask.
- **"Frame", not "RPC",** for what a peer writes on its stream: one gossipsub `RPC`, with the messages
  and control fields it carries, and not a frame of the layers below (§2, and the glossary). `RPC`
  stays only for the protobuf type. `on_rpc` becomes `on_frame`, its parameter `frame`, and
  `ihave_rpcs` `ihave_frames`, here, in `protocol-v2.md`'s code, in the toy and in a comment of the
  Quint model, whose own `onRpc` keeps its name. §7.2 says that the writer writes each entry as one
  frame, and that a client may merge entries' control into one, as §5.1, §5.4, §6.4 and §8.3 already
  allowed; §7.3 says that its "yamux frames" are the multiplexer's. No rule or value changes.
- **What the source's HAVE names, and when it announces, said as the code does it.** A chunk is
  acknowledged at the first HAVE naming it, from any peer, or at the first window timeout of a copy of
  it (§5.1, §7.1, and the glossary's "acknowledgement"). At the default (next item), the source's HAVE
  names the chunks acknowledged so far, and its announcements wait for the acknowledgement; a pushed
  peer's first HAVE also names the first chunk queued for it, as before. Two comments, §5.1's bullet
  on the HAVE and the glossary said "known to have arrived", and `publish`'s comment "chunks we have
  sent"; §5.1's bullet on the announcements and §8.3's `R` row had the offers wait for "a copy known
  to exist elsewhere", and §7.1 named only a slot's return or timeout. Wording and comments only.
- **When the source announces is its own choice** (§5.1, §8.3's `SOURCE_OFFERS`): at a chunk's
  acknowledgement by default (`ACK`), as since v0.9, or at publish (`PUBLISH`), its HAVE then growing
  at each chunk's first write (`origin_written`) and the acknowledgement doing nothing, as before v0.9
  and as the research implementation offers (§9). No rule at another node needs either setting,
  though, like any default, it changes how the payload spreads. The acknowledgement is an event the
  source sees whatever the transport holds, and keeps P4's cover toward the mesh; announcing at
  publish names the source to its mesh, and can draw asks on top of its pushes where the transport
  takes a writer's entries at once. §5.1's Rationale gives the trade, with the toy's figures, and §2,
  §4.3, §7.1, §8.3's `R` row, §9 and the glossary say which setting they describe.

The draft of SEACAST's next version (`protocol-v2.md`), changed since v0.10:
- **v0.10's rules in the draft's own functions.** Its `defer` ignores a copy beyond its sender's limit
  of unknown groups; its `fill` drops what names an index beyond a group's count when it opens the
  group (`drop_beyond`); its `on_heartbeat` drops what waits for a gate that never opens
  (`drop_stale_waits`); its `on_offer` holds an offer's bitmap to a holding's limits; and its
  `on_header_validated` drops a tied index a cell group does not have, and a sender's `tie_slot` with
  its last tie. A cell's level 1 rejects a copy whose slot is not its header's, as `validate_chunk`
  does for the payload (§1's table). §5 gains two rows.
- **A connection's close** follows §3's lifetimes, which are `protocol.md` §8.1's. A peer's claims go
  with its connection (`claims_close`), and a probe of a claimant that leaves before its verdict gets
  none: the member's own repair is reconsidered at the duty's own time, the time it was armed for
  when the claim deferred it (`duty_at`), at once if that has passed (§4.6).
- **The probe's wait starts at its write**, as every promise does (`protocol.md` §6.1): its promise
  starts when its WANT is written (`probe_sent`), and the verdict waits until the later of one window
  after that and the duty's own time. A probe a full queue refuses, or one still unwritten when the
  duty next fires, gets no verdict unless the claimant's own copy comes first, and otherwise the
  member's own repair is reconsidered, which bounds the deferral at one window past the later of the
  duty's own time and one window after the decision. A probe settled while still queued is not
  written later (`probe_settled`). Once settled, the probe holds no promise open: a promise under its
  key is a plain ask's, which any copy closes (`probe_promise`), so a later plain ask of the probed
  cell does not park a claimant that answered it (§4.6).
- **A claimant still decoding answers the probe when the cell is stored.** It keeps the first marked
  ask per asker and group of a claimed index it has not stored (`probe_waiting`), and answers it once,
  with its exemption, from `fill` and `decode_group` (`serve_waiting_probe`). While it is kept,
  neither the same marked ask repeated nor a standing WANT of the same index from the same asker,
  sent before it or after it, is kept as a standing WANT as well. No case of the probe is left open
  (§4.6, §8).
- **The probe's figures measured again** with these rules, in the toy's rows at 60 nodes over five cells
  and three seeds: none of 1 298 verdicts on honest or hoarding claimants failed, liars passed 3, 1 and
  61 times in the three liar cells, and the mark cost 9 duplicate cells in 2 428 probes. None of the
  runs reached a path that `probe_settled`, `duty_at` or the single answer changes (a probe given no
  verdict while queued, a refusal or a close, a kept probe), and the settled probe's promise changes
  no verdict once given: it acts only on an ask of the probed cell to the claimant after the
  verdict, and after a pass the member holds the cell, while after a failure the claimant was parked
  for the group when its promise broke. The runs did not count such asks, so whether it would change
  their events, copies or verdict counts is not shown. The earlier figures stay, labelled as
  measured before (§4.6, §8, `toy/README.md`).

The toy:
- **The draft's tables read without creating entries**, as `protocol.md`'s do since v0.10
  (`toy/bits.py`'s non-inserting classes), and the report of asks left unanswered no longer counts a
  marked probe as claimed.
- **A connection's close (`--churn`)** drops what §8.1's rows say and keeps the peer's park, which it
  deleted before.
- **The lazy tables' text says what they do** (`toy/README.md`, `toy/bits.py`): `table_read_known.py`
  checks that a read creates no entry the tables show. It does not check §8.1's "reading it allocates
  nothing", since the toy keeps an entry for each missing key read until the key is written. §8.1 rules
  that out for a node, where IWANTs naming groups never admitted would make such state grow without
  bound; the toy's runs send no such IWANT, and no outcome depends on the kept entries.
- **The IHAVE limits at `protocol.md`'s reference values hold back no ask** in any recorded cell,
  with or without `--doc v2`: each cell runs as it does with no limit (`toy/README.md`).
- **`--source-offers publish` runs `protocol.md`'s `SOURCE_OFFERS = PUBLISH`.** In each of the fifteen
  cells of `golden.txt` it gives the digest of the document with the source of before v0.9's rule put
  back, and none of the recorded digests (`toy/README.md`); `--doc v2` refuses it. Its help says that
  `off` and `late` act only on offers `publish` makes, so since v0.9's rule they change nothing.
- **Known answers** for each change: `toy/v2_carried_known.py`, `toy/close_known.py`,
  `toy/refusal_report_known.py`, `toy/probe_decode_known.py`, `toy/probe_write_known.py` and
  `toy/probe_settle_known.py`; `toy/deferral_rules_known.py` and `toy/table_read_known.py` also run the
  draft (`--doc v2`).
- **Unchanged:** every recorded cell's digest in `golden.txt` and `golden-v2.txt`. Of the code lines
  `protocol.md` changes, `MAX_SEGMENT_SIZE` keeps its value, `SOURCE_OFFERS`'s change nothing at the
  default `ACK`, and the others only take the new names (`on_frame`, `frame`, `ihave_frames`) or a
  reworded comment.

## v0.10.2, 2026-11-16 (`f08a90b`)

No rule changes: the toy's runs of the next version's draft no longer slowed by its lazy tables, the
last resort named as `protocol.md` names it in the toy and the Veil proofs, and this changelog easier to
scan.

- **The toy's lazy tables keep their detached entries.** `toy/bits.py`: a missing key of a lazy table
  reads as a detached entry, which is now kept in a plain cache until it joins its table or its key is
  set, not in a weak one. The weak cache made an entry and dropped it again at most reads of a missing
  key, which made the toy's runs of `protocol-v2.md` much slower than before v0.10. Every reader sees
  the same as before: an entry nobody wrote is empty, as a new one would be. An entry that is read and
  never written now stays in its table's cache, one per key, table and node, so a run holds a little
  more memory.
- **The toy and the Veil proofs call B′ the last resort**, as `protocol.md` does since v0.10.1:
  `toy/README.md`, two known answers (`toy/tie_helpers_known.py`, `toy/tie_release_known.py`, and two
  lines they print) and `formal/veil/` (comments only). The Quint model and its tools keep the label,
  where it tells the last resort apart from the fix's earlier forms; `formal/README.md`'s table
  names it.
- **Each entry of this changelog opens with a summary**, and each change with a few words in bold; the
  entries before v0.9 are lists, as v0.9's and v0.10's are since v0.10.1.
- **Unchanged:** `protocol.md`, `protocol-v2.md`, the models and proofs in `formal/` (only comments and
  README wording changed there), and every recorded cell's digest.

## v0.10.1, 2026-11-15 (`ea92383`)

The text rewritten for readers; the code unchanged, some comments reworded.

- **`protocol.md` rewritten for readers**, every section: a rule to a paragraph, with new paragraphs
  that say what each handler does, written from its code. The reasons move to an unnumbered Rationale
  at the end of a section, with the alternatives not taken. What this version leaves open is marked
  **Open:**. §0 says how the document is organized and how to read it, and a glossary after §9
  defines its terms.
- **History and figures out of the rules.** A rule's history is left to this changelog, measured
  figures to §9 and the companion documents, and review labels are dropped. Three code comments that
  called the last resort B′ name it, on the same lines.
- **Two sentences corrected to the code.** The two that still had the source announce at publish
  (§5.1, §5.4) follow the code, which announces at the acknowledgement (since v0.9).
- **`README.md` rewritten:** it describes the next version's draft, `formal/` and `formal/veil/`
  without their history, and without the toy's one-seed figures.
- **This changelog's v0.10 and v0.9 entries are lists.**
- **Unchanged:** the toy, its recorded cells, `protocol-v2.md` and `formal/`.

## v0.10, 2026-11-15 (`1643c01`)

What waits for a block is written out as code, with four new rules; the toy's transport sends one entry
at a time; every decision of the next version's draft is taken.

`protocol.md`:
- **What waits for its block, as code.** A chunk that arrives before its block is installed now waits
  by rules written out as code (§4.2, §6.1: `tie_room`, `drop_offer` and the `of=` form of
  `close_promises`), and four rules are added for what waits:
  - a deferred copy of a group beyond its sender's limit of unknown groups is ignored;
  - at installation, a tied index the group does not have is dropped;
  - when a group's count becomes known, what named an index at or beyond it goes (§4.2, §8.1);
  - what waits for a root that never installs goes when its slot leaves the live window or its group
    expires (§4.2, §6.4, §8.1).
- **Level 1 checks the slot:** it rejects a copy whose slot is not its block's (§3).
- **IHAVE entries and bitmaps checked.** An IHAVE entry is a bitmap or a chunk's valid id, anything
  else ignored without penalty, and an IHAVE's bitmap is held to a HAVE's limits: one naming an index
  at or beyond the group's known count is ignored and counts against the sender (§4.4, §8.2).
- **The node's own order of announcers.** The announcers beyond a chunk's ordered list are tried in an
  order of the node's own, a hash of the chunk and the peer keyed by a secret the node draws, which no
  peer can predict or arrange (§6.1, §8.1).
- **Two weaknesses named, not addressed in this version:** an announcer that is never parked holds the
  last resort off a parked honest provider (§6.1), and one IHAVE naming a chunk under two keys gets its
  sender asked once per key (§4.4).
- **Three explanations added:** §6.2 says when the stop-pull test decides, §4.4 why the lookup of
  `known_id` is kept, and §9 which announcers the measured retry took.

The toy:
- **One entry at a time per connection.** The default transport keeps §7.3's rule (`--send-buffer 1`;
  `--send-buffer 0` is the earlier transport, which takes every write at once). Every recorded cell
  but `rr-stripe` changes in both recordings, at seed 7 by −98 to −3 ms at the median, −99 to −2 ms
  at the tail and −0.72 to −0.03 copies (`push` in `golden.txt`: 464 → 427 ms, 533 → 522 ms, 2.49 →
  2.15 copies), the recordings made again. A cell `push-deep` keeps the earlier transport and gives
  the earlier `push` line exactly.
- **Late blocks.** A block can install late at some nodes (`--late-block`), and a recorded cell where
  18 of 60 nodes do runs §4.2's deferral and fails if anything is left waiting. The README says why its
  on-time nodes finish later: the late peers hold slots of the source's sending window (§7.1).
- **`toy/check.py` gains a cell with gossipsub's stock IHAVE limits** (`ihave-limits`), recorded in
  `golden.txt`.
- **Tables read without creating entries.** Every table of `protocol.md` reads without creating an
  entry, and known-answer scripts (`toy/*_known.py`) check the new rules. `toy/check.py` has fifteen
  cells.

The draft of SEACAST's next version (`protocol-v2.md`), changed since v0.6:
- **Every decision taken.** Every decision of its §8 is taken; where one was chosen among
  alternatives, those not taken are written beside it. Among them: a protocol of its own carried by
  §7's three bindings (`[D1]`); a sampler's reach, a coverage floor built for diversity with routed
  sample requests on LiteDAS's two phases (`[D12]`); a column's and a row's offers to every joined
  peer, offers to the relations only permitted for columns (`[D5]`); the row pull delay of 1 s,
  shorter at a cost where nodes lie about their holdings (`[D8]`); the promise's length; and the
  window in bytes.
- **Limits by their bounds:** §6.3 states its limits by their bounds, the values the client's.
- **`protocol.md`'s v0.7, v0.8 and v0.9 rules carried in**, v0.9's acknowledgement for every object
  type (§4.7).
- **The relations' upkeep written out.** It runs on the toy's wire (§4.1: a GRAFT is answered, JOINs,
  GRAFTs and PRUNEs are owed at a full queue, a symmetric type keeps one relation both ways), and
  `toy/graft_check.py` checks the JOIN and GRAFT exchanges in every interleaving for one link and one
  relation, in small bounds. A PRUNE names its direction from its sender's side (§4.1), and a binding
  validates a block's cell header no later than it installs the block (§4.2).
- **A source in a family it does not custody.** It publishes at once to the links it has there (§4.7,
  `source_pool`, `SOURCE_FLOOR`), the payload's too, where `protocol.md`'s source with no mesh peer
  sends nothing (§6.1), and owes a push to them that a full queue refuses, as to a relation peer
  (`unpush`). A source's own chunks go before its offers and answers (§4.12).
- **Repair's options:** repair keeps a floor of custodian links, and its sample, rebuilt cells marked
  seen and a custodian's alarm are options (§4.6).
- **The probe of a claim.** It judges the claimant by its own copy only, is marked so that the claimant
  answers it whatever the asker holds (`Want.probe`, once per asker and group), is kept in the asker's
  queue while it waits, and asks for a cell drawn at random among those lacked, where it asked for the
  lowest. The standalone binding carries its mark and `standing` in one flags byte, and three cases it
  does not yet handle are named open (§4.6, R5).
- **Bindings:** §7 says how a sampler rides gossipsub's wires, and frames the standalone binding as
  Waggle does.
- **The toy's options for the draft.** The toy gains options for these (among them `--sample-cover`,
  `--upkeep`, `--churn`, `--col-announce`, `--row-announce`, `--alarm-wait` and `--rebuilt-seen`),
  `--topology` also loads the research harness's DAS graphs, and `golden-v2.txt` is recorded again
  where a carried rule changed its events. `toy/sampler_graph.py` and `toy/sampler_match.py` compute
  `[D12]`'s figures on graphs alone.
- **What the draft carries, stated.** The draft's figures measured before the toy's transport change
  say so (its §0), and its header lists what it carries of this version's `protocol.md` changes and
  what not yet, where it has functions of its own.

**Unchanged:** `formal/` and `formal/veil/`; their models are of v0.5's and v0.8's rules.

## v0.9, 2026-11-10 (`ed5745a`)

The source announces a chunk at its acknowledgement, not at publish, and a new §7.3 says what the
transport below the writer should hold.

`protocol.md`:
- **The source announces at the acknowledgement.** It announces a chunk to the mesh peers it did not
  push it to, and its HAVE names the chunk, at the chunk's acknowledgement: the first HAVE naming it
  from any peer, or its first copy's window timeout (§5.1, §4.3, §7.1). This replaces v0.8's
  announcement at publish and HAVE at the write. Announced at publish, the offers raced the pushes
  wherever the transport takes the batch at once, and the source answered asks for chunks whose pushes
  were still queued.
- **What the transport should hold (§7.3).** A new §7.3 says what the transport below the writer
  should hold: a writer should hand a chunk to the transport only while the connection has less than
  one chunk unsent; what that bounds and what it does not; how quic-go and TCP keep it; and a note for
  operators on the access link's queue.
- **§9 on the measured implementation:** it announced at publish over quic-go.

The toy:
- **The recording made again.** The toy's events change in every recorded cell of `golden.txt` (at
  seed 7 by −14 to +1 ms at the median, −47 to +12 ms at the tail and −0.11 to +0.06 copies).
  `golden-v2.txt` was unchanged by it, since the next version kept its own source until it took this
  rule (v0.10).
- **The payload's size as an option.** The toy takes `--payload BYTES`, the bytes of each payload
  (default 1 MiB), the compressed size following at the same ratio, so that small sizes give
  hand-counted cases (16384 bytes: K = 1, N = 2). The recorded cells are unchanged by it.

## v0.8, 2026-10-28 (`bc7a0a6`)

Stalls closed: for a peer that joins the mesh, under equivocation (two blocks for one slot) and where a
peer's offers are dropped; a rebuilt chunk names its sources' block.

`protocol.md`:
- **A peer that joins is offered what the node holds.** A peer that joins a node's mesh is announced
  what the node holds, so a peer that joins after a chunk was forwarded, or whose connection closed, is
  offered it (§5.4; F9 in `formal/README.md`).
- **A waiting copy ties its sender.** A copy that waits for its block ties its sender to the root it
  names, and that root's installation makes the sender an offer of the index, in place of v0.5's offer
  of a refused copy (§4.2).
- **No second ask while one is outstanding.** No peer is asked for a chunk while an earlier ask of it
  to that peer is outstanding (§6.1). With the tie above, this closes F6, a stall under equivocation.
- **Dropped offers take their ask with them.** Where a peer's offers of a chunk are dropped, with its
  tie or at their expiry, its queued ask of the chunk goes with them and its promise closes (§6.1):
  kept, the ask could keep a node from ever asking a parked announcer, a stall.
- **A rebuilt chunk names its sources' block:** the block the chunks it was rebuilt from name (§4.6).
  Among honest nodes every copy then names the builder's block, as the proofs in `formal/veil/`
  assume, as long as no node relabels a chunk under the proposer's other block: such a copy is
  authentic, honest nodes forward it, and a node behind them can stall. §4.6 lists this gap as open,
  with its options.

`formal/veil/`:
- **No stall with a changing mesh and under equivocation.** `formal/veil/` proves no stall (Q1) with
  the mesh changing and connections closing, and under equivocation for the nodes the source reaches
  through nodes that installed the builder's block.

The toy:
- **Both recordings made again.** The rule against a second ask changes the toy's events in all twelve
  recorded cells and in eleven of the next version's; asks that go with their announcer's offers change
  none.

## v0.7, 2026-10-25 (`d5c1ae9`)

Groups expire with the live window and are named by a key that fixes their slot; IHAVEs over gossipsub's
limits are kept for the next heartbeat; `formal/veil/` proves A1 and no stall at any size.

`protocol.md`:
- **Expiry by the live window.** A group whose slot has left a node's live window is expired for good,
  its tombstone kept until then, and a group without a slot keeps its tombstone `TOMBSTONE_TTL` (§8.1,
  §8.3).
- **A group's key fixes its slot.** In diffusion a group is named by its key, the hash of its group id
  and slot, so its slot is fixed (§1).
- **IHAVEs over the limits recorded, not ignored.** An IHAVE over either of gossipsub's IHAVE limits is
  recorded instead of ignored, its asks waiting for the next heartbeat's retry, with the limits' values
  the client's (§4.4, §6.4, §8.2).
- **The source announces only to the peers it did not push to.** §5.1's source announces a chunk only
  to the mesh peers it did not choose for a push, so a push its queue refuses is offered once.
- **A rebuilt chunk names an installed block** whose bid commits its group (§4.6).
- **§9 and the rerun:** §9 says where the rerun of the SEACAST post's Figures 4 and 5 does as this
  document does (v0.6.1).

`formal/veil/`:
- **Proofs at any size.** `formal/veil/` proves A1, that an honest node is never penalised, at every
  place a node penalises, and no stall (Q1), at any size; the no-stall proof found the IHAVE gap.

The toy:
- **Every recorded cell moved.** The toy runs the text as written: under the group's key every
  recorded cell moved, as under any renaming.

## v0.6.1, 2026-10-23 (`6606abd`)

§9 after the rerun of the SEACAST post's Figures 4 and 5, and the proof of A1; the protocol text still
version 0.5.

- **§9 after the rerun** of the SEACAST post's Figures 4 and 5 on an implementation with version 0.5's
  rules and the paced source HAVE: each entry the rerun changes says so; the rules added after v0.4 are
  given as the rerun has them; and a new entry, announcing after the decode claim, accounts for the
  implementation's extra HAVEs against the toy.
- **The proof of A1:** `formal/veil/` is in this release, with the proof that an honest node is never
  penalised for an ask.
- **Unchanged:** the protocol text is still version 0.5.

## v0.6, 2026-10-21 (`586ffae`)

The name SEACAST, the formal model, and a draft of SEACAST's next version; `protocol.md` unchanged.

- **The name SEACAST.**
- **The formal model:** `formal/`, which checks v0.5's rules.
- **A draft of SEACAST's next version:** `protocol-v2.md`, which adds availability sampling and other
  object types, with the toy's support for it.
- **Unchanged:** `protocol.md` and the toy's recorded cells, as in v0.5.

## v0.5, 2026-10-21 (`10e1f87`)

Six fixes from a model check of v0.4 (its findings are in `formal/README.md`, since v0.6), the last
resort among them; the toy's recorded results moved.

`protocol.md`:
- **A push that does not happen is offered instead.** A push to a mesh peer that does not happen is
  offered to it instead, and an offer or answer a full queue refuses is owed (§5.2, §7.2, §4.1).
- **The last resort.** Every offer is kept, per connection and group, and when every announcer of a
  chunk is parked, each is asked once more, at a wait that doubles (§6.1, §8.2).
- **No ask before the block is installed;** what was offered meanwhile is asked for then (§3, §4.4,
  §4.2).
- **Expiry checks.** Expiry is checked by the retry, the writer's ask filter and a decode that returns,
  and a group's pull state goes at its expiry (§6.1, §7.2, §4.6, §8.1).
- **A promise starts when the ask is written** and closes with its connection (§7.2, §6.1).
- **A copy the deferred store refuses** counts as its sender's offer (§4.2).
- **§8 and §9 follow:** §8's state, limits and constants follow, and §9 lists these rules among those
  the measured implementation predates (v0.6.1 records the rerun on one that has them).

The toy runs the text as written, so its recorded results moved.

## v0.4, 2026-10-13 (`fe41907`)

The source's HAVE names only what it has sent, removing the one certain sign of the source; the toy
runs beside the research harness; the text takes the posts' terms.

- **The source's HAVE names only the chunks it has sent** (§5.1, [P4]), which removes the one certain
  sign of the source.
- **A writer that takes a window slot wakes the next one** while slots remain (§7.1).
- **The toy beside the harness:** it runs on a harness cell's network (`toy/xcheck.py`,
  `--send-buffer`) to set the two side by side.
- **The posts' terms:** *chunk* for the unit on the wire, *node* and *forward* where the text said
  relay, and *Informed Diffusion* for the protocol.

## v0.3, 2026-10-05 (`181be31`)

This repository's first release: the protocol in pseudocode, and a toy that runs it.

- **Rebuilt chunks pushed.** Since v0.2, a node that has decoded a group pushes the chunks it rebuilt
  to the mesh peers that still lack enough chunks to decode (§4.6), instead of holding them.
