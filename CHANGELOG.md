# Changelog

Each release is a tag, and `protocol.md` names its version at the top. A release's heading below
names the tag's commit from the next release on, since a commit cannot name itself. Changes after
the latest tag are on `main`; when there are any, this file's first entry names them. A release
changes the text and its checks, not earlier measurements: each measurement says which code it ran
(`protocol.md` §9 for the SEACAST post's figures).

Each entry opens with a one-line summary and lists its changes by kind. **Rules** come first: they
change what a node does, under `protocol.md`, `protocol-v2.md` or its bindings. **Added**,
**Changed**, **Fixed** and **Removed** follow. Each line says what changed and where. The reasons
are in the documents, most of them in their Rationales, and the full story is in the commit
messages. The detailed notes of every release up to v0.10.8 are in
[the changelog at the v0.10.8 tag](https://github.com/cskiraly/seacast-spec/blob/v0.10.8/CHANGELOG.md).

## v0.10.9 — 2026-11-21

The wake in the window's line moves to the moment a write starts to wait, and the index of an ask
by index (`WantIndex`) is little-endian.

### Rules
- `protocol.md` §7.1, §7.2: when a writer in line starts to wait for its transport, it wakes the
  first writer in line that can write, if a slot is free (`write_waits`), and no longer wakes one
  before it writes control; `wake_front` loses its argument.
- `protocol-v2.md` §4.11: the same, if the window has room, in place of the wake before the write
  on its three control paths.
- `protocol.md` §7.1, `protocol-v2.md` §4.11: a client that cannot tell when a write starts to wait
  may call `write_waits` before each control write of a writer in line, once that write is pending.
- `protocol.md` §2: the message-id string of a `WantIndex` carries the index as a little-endian
  uint32.

### Added
- `toy/write_wait_known.py [--doc v2]`: a known answer for the wake at the wait, which also checks
  that the next writer is not woken while the window is full and that the writer keeps its place in
  line.
- `formal/toy/monitor.py`: a fourth known answer, `--break writewait`, which W2 catches.
- `protocol-v2.md` §4.11: "Open: room left unused after a queue edit".
- `protocol.md` §9: the research harness writes the index of a WANT string big-endian, in versions
  1 and 4 of its strings.

### Changed
- `protocol.md` §7.1: the window's line has a paragraph of its own, and the Rationale a paragraph
  on when the next writer is woken.
- `protocol-v2.md` §4.11: the wake at the wait has a paragraph of its own, and the Rationale gives
  it in place of the wake before the write.
- `toy/node.py`: the toy calls `write_waits` where a writer's transport first takes no more.
- `formal/twin/`: the twin follows the wake at the wait (`write_waits`, `wake_front` without its
  argument, and no wake in `next_to_send`'s urgent branch or its branch of owed offers alone).
- `toy/golden.txt`, `toy/golden-v2.txt`: `rr-stripe` and `push-deep` move in their digests only;
  every other cell keeps its digest.
- `formal/toy/monitor.py`: one break a run.
- `formal/README.md`, `formal/diffusion.qnt`: the Quint model stays at v0.5's rules and is not
  ported further.
- `formal/README.md`: the map counts four known answers for the monitors, which check W1 and W2
  after each event at a node.
- `protocol-v2.md` §3: a dropped group's chunk is not offered, since the node would not answer the
  asks it drew.
- `protocol-v2.md` §5: the versions carried gain v0.10.9.
- `CHANGELOG.md`: each entry lists its changes by kind, one line each; the detailed notes up to
  v0.10.8 stay at the v0.10.8 tag.

### Removed
- `toy/control_wake_known.py`, which tested the wake before the write.

## v0.10.8 — 2026-11-21 (`9475af8`)

The Lean twin's record and the first piece of a refinement come into the repository, and no rule
changes.

### Added
- `formal/twin/record/`: the twin's record. It holds one run of `record.sh` over every cell of the
  toy under both documents, the hand runs and the directed sets, and the matrix of the mutants;
  `RECORD.md` says what it shows and what it does not show.
- `formal/refine/`: the first piece of a refinement, from the twin's side of §6.1's asking path to
  the Veil model `NoStallEquiv`.
- `formal/twin/tools/`: a draft part of the matrix (`--sample drafts`), which the merge of a matrix
  refuses.
- `formal/twin/tools/against.py`: it reports a difference in a document's SHA-256, and the
  difference decides nothing.
- `formal/twin/tools/matrixdiff.py`: `--common`, which compares two matrices over the mutants they
  share.

### Changed
- `formal/twin/tools/content.py` (version 2): a trace's first line names each document by the code
  that the toy runs from it, and the replay reads either version and passes a trace only if its
  first line is the one it is given.
- `formal/twin/`: the tracer reads its command line as the toy's parser does, and most citations
  name sections instead of line numbers.
- `formal/twin/README.md`, `formal/README.md`, `README.md`: the twin is no longer called a draft,
  and the map takes in the record and the refinement.

## v0.10.7 — 2026-11-20 (`c67d0e5`)

A writer that cannot write no longer holds the window's line, and the Lean twin comes in as a
draft.

### Rules
- `protocol.md` §7.1, §7.2: a free slot goes to the first writer in line that can write, and the
  writer passed over keeps its place; before a writer in line writes control, it wakes the first
  other writer in line that can write, if a slot is free.
- `protocol-v2.md` §4.11: the same, in its window in bytes and on its three control paths.

### Added
- `formal/twin/`: a draft of the Lean twin of `protocol.md`'s code, with the tracer, the replay
  and `check.sh`.
- `formal/README.md`: a map of how the checks fit together.
- `protocol.md` §7.1: a Rationale; the helper list gains `writing`.
- `toy/line_stall_known.py [--doc v2]`: a known answer for the window's line.
- `toy/control_wake_known.py`: a known answer for `protocol-v2.md`'s third control path.

### Changed
- `toy/golden.txt`, `toy/golden-v2.txt`: the digests move with the rule, and a few cells' printed
  figures move slightly.
- `formal/toy/monitor.py`: W2 is asked of the line as §7.1 now has it, and each known answer takes
  its rule out of the code where it matches once and names the property it breaks.
- `formal/toy/monitor.py`: the harness exits 1 when a run fails, when a run without a known answer
  finds a violation, or when a known answer's property is not caught.
- `protocol.md` §9: the note on the measured implementation's line follows the rule.
- `toy/`: the `--answers line` option wakes the same way (`wake_front`).
- `README.md`: `formal/`'s bullets, and "Where SEACAST stands" points to the map.

## v0.10.6 — 2026-11-19 (`de7a028`)

`protocol.md` names an open question on a coded group's compressed bytes, and the next version's
draft is rewritten for readers.

### Rules
- `protocol-v2.md` §4.6: `filter_entry` starts a promise only for an ask made on an offer, and none
  for one sent as a `Want`; a claim's probe keeps its own promise at its first write.
- `protocol-v2.md` §4.2, §4.4: a copy under an id the node has not seen, at an index it has already
  received on an axis, is acknowledged there and not forwarded on that axis, as in `protocol.md`;
  it is kept for heartbeat gossip only if some axis forwards it.
- `protocol-v2-bindings.md` §3: v0.3's wire reads an IDONTWANT's entries as `protocol.md` §4.1
  does, and reads as a holding an entry with `HaveBitmap`'s MAGIC at either version it writes.
- `protocol-v2-bindings.md` §3: v0.3's wire ignores an IHAVE entry that is not a bitmap.
- `protocol-v2-bindings.md` §2, §3: where a GRAFT is accepted in silence, gossipsub's backoff after
  a PRUNE must outlast the link's longest round trip at each end that may prune.

### Added
- `protocol.md` §1: "Open: the compressed bytes"; the glossary gains *canonical compressor*.
- `protocol-v2-bindings.md` §1.3, §1.6, §1.7: the payload's chunk under either design.
- `toy/want_promise_known.py`, `toy/second_id_known.py`: known answers.

### Changed
- `protocol-v2.md`: rewritten for readers in `protocol.md`'s form, and the record of each
  `protocol.md` version carried moves to §5; the rewrite leaves the code and all its comments but
  one as they were, and changes no rule.
- `protocol-v2.md` §1.1, §2: where the descriptor travels is left open, as in `protocol.md` §1.
- `protocol-v2.md` §1.1: the `decode` row points to `protocol.md`'s open item on the compressed
  bytes.
- `protocol-v2.md`: statements made true to the code, among them heartbeat gossip only for a type
  that gossips, no cap over whole messages, and three differences from `protocol.md` in §6.1
  (§1.3, §1.6, §4.1, §4.3, §4.6 to §4.10, §4.12, §4.13, §5, §6.1, §6.3).
- `protocol-v2.md` §5, §6.1: its lines on v0.10.4 and v0.10.5 say what it carries, and §6.1 adds
  the difference that v0.10.5 opens.
- `toy/` (`--doc v2`): the document's `filter_entry` runs unwrapped, and the IWANT that an ask
  sent as a `Want` is written as carries `want`.
- `toy/idontwant_id_known.py`: it also runs under `--doc v2`.

### Fixed
- `toy/` (`--doc v2`): an IDONTWANT's stock id is kept in `unwanted[p]`, where the toy dropped it.

## v0.10.5 — 2026-11-19 (`662c526`)

The Veil proofs move to Veil's release and gain malicious peers, quiet runs and agreement, and the
toy's `accepted` follows `protocol.md`.

### Added
- `formal/veil/`: malicious peers (`NoStallAskAdv.lean`, `NoStallTransportAdv.lean`,
  `NoStallEquivAdv.lean`): no stall (Q1) for the honest nodes that the source reaches through
  honest nodes that installed the block, relabelled copies excluded, and Q3 once the environment
  stops, the adversaries' actions included; with the findings F13 and F14, and a switch, `byGroup`,
  for level 1 by group.
- `formal/veil/`: a run goes quiet (Q3), with finitely many nodes and weak fairness, once the
  environment stops (`QuietRanking.lean`).
- `formal/veil/NoStallCount.lean`: the counting through honest nodes, and three corollaries.
- `formal/veil/Agreement.lean`: agreement and integrity, under the codec's assumptions.
- `toy/accepted_id_known.py`, `toy/probe_replay_known.py`: known answers.

### Changed
- `formal/veil/`: Veil's release v4.35.0, in place of a pre-release.
- `formal/veil/README.md`: the results of the whole build, and the changes of `protocol.md` since
  v0.8 that the models do not have; `README.md` and `formal/README.md` describe the new proofs.
- `formal/veil/`: the new models say "the last resort", as `protocol.md` does.

### Fixed
- `toy/`: `accepted(mid)` answers whether the id was stored, as `protocol.md`'s helper list says.
- `formal/veil/README.md`: `SenderFault.lean`'s clause count.

## v0.10.4 — 2026-11-18 (`34f60f8`)

The repository is renamed `seacast-spec`, an IDONTWANT's stock ids are kept as stock gossipsub
keeps them, and the next version's draft gains a bindings document.

### Rules
- `protocol.md` §4.1: an IDONTWANT entry that is not a HAVE bitmap is kept in `unwanted[p]`, as
  stock gossipsub keeps an id (`on_frame`, `is_have_bitmap`).
- `protocol-v2.md` §4.7, §6.3: when a source offers is its own choice (`SOURCE_OFFERS`): at the
  acknowledgement by default, or at publish, its holding then growing at each chunk's first write.
- `protocol-v2.md` §4.7: a pull-only type's source pushes nothing and offers every chunk at publish.
- `protocol-v2.md` §3, §4.4, §4.6: a node skips the axis of a chunk whose group was dropped, and
  goes on with its other axes.
- `protocol-v2.md` §4.6: a decode answers the standing WANTs of its own group.
- `protocol-v2.md` §3, §4.11: the window counts the binding's size of a write's chunk, with a
  carried header (`wire_size`).
- `protocol-v2.md` §4.4: a push, or an answer to a standing WANT or a kept probe, is noted under
  every group the chunk fills (`note_push`), and a push not made is undone under each (`unpush`).
- `protocol-v2.md` §4.6: a settled probe's ask is no longer exempt from stop-pull.
- `protocol-v2.md` §4.6: while a claimant keeps an asker's probe, that asker's marked ask of another
  index of the group is a plain ask.
- `protocol-v2-bindings.md` §1.3: on the standalone binding, a cell's header goes with the first
  eager push of a group on a link and with no answer, and a node that receives no eager push of a
  group, such as a sampler, takes it from the block; a carried header is validated apart from the
  cell, before the cell is handled, and does not mark the cell's id.
- `protocol-v2-bindings.md` §1.3: on the standalone binding, a link carries an object type only
  where both ends' JOINs for it name the same fork digest, and a cell has one id whichever group
  carries it.
- `protocol-v2-bindings.md` §1.2, §1.6: on the standalone binding, each message kind has a bound on
  its body, and on the stream a receiver refuses a frame that cannot fit it before reading the body;
  a message of an unknown kind is skipped without penalty, and its frame is held to the largest
  frame that a known kind allows.
- `protocol-v2-bindings.md` §1.3: a carried header that fails its checks is rejected and counts
  against its sender; one that cannot be judged yet waits and counts against no one.

### Added
- `protocol.md` §5.1: "Open: a chunk that is never acknowledged".
- `protocol-v2-bindings.md`: a document of its own for the draft's bindings, with the old §7's
  mappings and its rules for a sampler on gossipsub's wires; it defines the standalone binding to
  the byte.
- `protocol-v2.md` §7: what every binding provides, and the capabilities the bindings differ in.
- `protocol-v2.md` §4.2: a note that an implementation indexes the tables the pseudocode scans.
- `toy/`: `--wire standalone`, which charges the links the standalone binding's bytes.
- `toy/*_known.py`: known answers for these changes.

### Changed
- The repository is renamed `seacast-spec`, and `protocol.md`'s title is *SEACAST: the protocol in
  pseudocode*; `README.md` follows.
- `protocol.md` §5.1, §5.4: the text says that the source's chunks go out in its heartbeat gossip,
  to its sample outside the mesh.
- `protocol.md` §2, §5.1, §7.1, §9: where the source's announcements go, said exactly.
- `protocol-v2.md` §4.3, §4.6, §4.7, §6.3: "acknowledged" and "a bound" as `protocol.md` says them,
  the IHAVE limits at `protocol.md`'s reference values, and the probe's and the alarm's figures
  measured again.
- `protocol-v2.md`, `protocol-v2-bindings.md`, `toy/`: "frame" where they said RPC.

### Fixed
- `toy/`: the custodian alarm's promise starts at the write, and a claimant that cannot be asked,
  or whose connection closes before the promise ends, is not penalised.
- `toy/` (`--churn`): a closed peer leaves the window's line and releases the room its chunks held.
- `toy/node.py`: the toy follows both documents at a dropped group (`discard_queued`,
  `discard_paced`, `accepted`) and in how it reads bitmaps (`valid_have`) and ids (`group_index`).

## v0.10.3 — 2026-11-18 (`afc85e8`)

`protocol.md` sorts its constants into three kinds, gives the IHAVE limits reference values, says
"frame" for what a peer writes, and lets the source choose when it announces.

### Rules
- `protocol.md` §5.1, §8.3: when the source announces is its own choice (`SOURCE_OFFERS`): at a
  chunk's acknowledgement by default, or at publish, its HAVE then growing at each chunk's first
  write.
- `protocol.md` §8.3, §1: `R`, `R_FAST`, `GUARD_GRACE` and `GOSSIP_RETRANSMISSION` are bounds, each
  node's within the bound given, and `UNIT` is the builder's.
- `protocol-v2.md`: v0.10's rules in its own functions (`defer`, `fill`, `on_heartbeat`,
  `on_offer`, `on_header_validated`), and a cell's level 1 checks the slot.
- `protocol-v2.md` §3, §4.6: a connection's close follows §3's lifetimes, and a peer's claims go
  with it (`claims_close`).
- `protocol-v2.md` §4.6: the probe's wait starts at its write; a probe that a full queue refuses,
  or that is still unwritten when the duty next fires, gets no verdict unless the claimant's copy
  comes first, and a probe settled while queued is not written later.
- `protocol-v2.md` §4.6: when a full queue refuses a probe, or the claimant's connection closes
  before the verdict, the member's own repair is reconsidered at the duty's own time (`duty_at`), at
  once if that time has passed; for a probe still unwritten when the duty next fires, the repair is
  reconsidered then.
- `protocol-v2.md` §4.6: a settled probe holds no promise open, and a claimant still decoding keeps
  the first marked ask and answers it when the cell is stored.

### Added
- `protocol.md` §8.3: reference values for gossipsub's two IHAVE limits, each node's own: 4096
  IHAVE-bearing frames and 5000 ids asked, per peer and heartbeat.
- `toy/`: `--source-offers publish`, for `protocol.md` only, and known answers for these changes.

### Changed
- `protocol.md` §8.3, §0, §8.2, glossary: the constants in three kinds, limits, bounds and
  defaults, with a Rationale; `MAX_SEGMENT_SIZE` is written as its value.
- `protocol.md` §1: the Rationale says what the descriptor's placement decides.
- `protocol.md` §2, §7.2, §7.3, glossary: "frame", not "RPC", for what a peer writes; `on_rpc`
  becomes `on_frame` and `ihave_rpcs` `ihave_frames`, in both documents, the toy and a comment of
  the Quint model.
- `protocol.md` §5.1, §7.1, glossary: what the source's HAVE names, and when it announces, said as
  the code does it.
- `protocol-v2.md` §4.6: the probe's figures measured again.
- `toy/`: the draft's tables read without creating entries, and `toy/README.md` says what the lazy
  tables do.

### Fixed
- `toy/` (`--churn`): a connection's close drops what §8.1's rows say, and keeps the peer's park.
- `toy/`: the report of asks left unanswered no longer counts a marked probe as claimed.

## v0.10.2 — 2026-11-16 (`f08a90b`)

No rule changes: the toy's lazy tables no longer slow its runs, and the toy and the Veil proofs
say "the last resort".

### Changed
- `toy/README.md`, two known answers, `formal/veil/` (comments): the last resort is named as
  `protocol.md` names it, and `formal/README.md`'s table gives the name.
- `CHANGELOG.md`: each entry opens with a summary and each change with a bold lead, and the entries
  before v0.9 are lists.

### Fixed
- `toy/bits.py`: a lazy table keeps a detached entry in a plain cache, so runs of `protocol-v2.md`
  are no longer slowed.

## v0.10.1 — 2026-11-15 (`ea92383`)

The text is rewritten for readers, the code is unchanged, and some comments are reworded.

### Changed
- `protocol.md`: rewritten for readers, with a rule to a paragraph, a Rationale closing each
  section, **Open:** items, a reading guide in §0 and a glossary.
- `protocol.md`: a rule's history goes to this changelog, measured figures go to §9 and the
  companion documents, review labels are dropped, and three comments name the last resort.
- `README.md`: rewritten.
- `CHANGELOG.md`: the v0.10 and v0.9 entries are lists.

### Fixed
- `protocol.md` §5.1, §5.4: two sentences follow the code, which announces at the acknowledgement.

## v0.10 — 2026-11-15 (`1643c01`)

What waits for a block is written out as code with four new rules, the toy sends one entry at a
time per connection, and every decision of the next version's draft is taken.

### Rules
- `protocol.md` §4.2: a deferred copy of a group beyond its sender's limit of unknown groups is
  ignored, and at installation a tied index that the group does not have is dropped.
- `protocol.md` §4.2, §8.1: when a group's count becomes known, what named an index at or beyond it
  is dropped.
- `protocol.md` §4.2, §6.4, §8.1: what waits for a root that never installs is dropped when its slot
  leaves the live window or its group expires.
- `protocol.md` §3: level 1 rejects a copy whose slot is not its block's.
- `protocol.md` §4.4, §8.2: an IHAVE entry that is neither a bitmap nor a chunk's valid id is
  ignored without penalty.
- `protocol.md` §4.4, §8.2: an IHAVE's bitmap is held to a HAVE's limits; one that names an index
  at or beyond the group's known count is ignored and counts against the sender.
- `protocol.md` §6.1, §8.1: the announcers beyond a chunk's ordered list are tried in an order of
  the node's own, keyed by a secret it draws.
- `protocol-v2.md` §8: every decision is taken, with the alternatives not taken beside it, among
  them a protocol of its own carried by three bindings (`[D1]`), a sampler's coverage floor with
  routed requests (`[D12]`), a column's and a row's offers to every joined peer (`[D5]`), a row
  pull delay of 1 s (`[D8]`), the promise's length and the window in bytes.
- `protocol-v2.md`: `protocol.md`'s v0.7, v0.8 and v0.9 rules are carried in.
- `protocol-v2.md` §4.1, §4.2: the relations' upkeep is written out (a GRAFT is answered; JOINs,
  GRAFTs and PRUNEs a full queue refused are owed; a symmetric type keeps one relation both ways),
  a PRUNE names its direction from its sender's side, and a binding validates a block's cell header
  no later than it installs the block.
- `protocol-v2.md` §4.7, §4.12: a source in a family it does not custody publishes at once to the
  links it has there and owes them a push that a full queue refuses, and a source's own chunks go
  before its offers and answers.
- `protocol-v2.md` §4.6: repair keeps a floor of custodian links, and its sample, rebuilt cells
  marked seen and a custodian's alarm are options.
- `protocol-v2.md` §4.6: the probe of a claim judges the claimant by its own copy, is marked so
  that the claimant answers it whatever the asker holds, is kept in the asker's queue while it
  waits, and asks for a cell drawn at random among those lacked.

### Added
- `protocol.md` §6.1, §4.4: two weaknesses named open: an announcer that is never parked holds the
  last resort off, and one IHAVE naming a chunk under two keys can get its sender asked once per
  key.
- `protocol.md` §6.2, §4.4, §9: when the stop-pull test decides, why the lookup of `known_id` is
  kept, and which announcers the measured retry took.
- `protocol-v2.md` §4.6, §8: three cases of the probe named open.
- `protocol-v2.md` §7: how a sampler rides gossipsub's wires, and the standalone binding framed as
  Waggle frames it, with the probe's mark and `standing` in one flags byte.
- `toy/`: late blocks (`--late-block`) with a recorded cell, a cell with gossipsub's stock IHAVE
  limits (`ihave-limits`), and known answers for the new rules.
- `toy/`: options for the draft (`--sample-cover`, `--upkeep`, `--churn` and others), the research
  harness's DAS graphs for `--topology`, `toy/graft_check.py`, `toy/sampler_graph.py` and
  `toy/sampler_match.py`.

### Changed
- `protocol.md` §4.2, §6.1: what waits for its block is written out as code (`tie_room`,
  `drop_offer`, the `of=` form of `close_promises`).
- `toy/`: the default transport sends one entry at a time per connection (`--send-buffer 1`); every
  recorded cell but `rr-stripe` moves, and the cell `push-deep` keeps the earlier transport.
- `toy/`: every table of `protocol.md` reads without creating an entry.
- `protocol-v2.md` §6.3: the limits are stated by their bounds.
- `protocol-v2.md` §0: the figures measured before the toy's transport change say so, and its
  header lists what it carries.
- `toy/golden-v2.txt`: recorded again where a carried rule changed its events.

## v0.9 — 2026-11-10 (`ed5745a`)

The source announces a chunk at its acknowledgement, and a new §7.3 says what the transport below
the writer should hold.

### Rules
- `protocol.md` §5.1, §4.3, §7.1: the source announces a chunk to the mesh peers it did not push it
  to, and its HAVE names the chunk, at the chunk's acknowledgement: the first HAVE naming it from
  any peer, or its first copy's window timeout.
- `protocol.md` §7.3: a writer should hand a chunk to the transport only while the connection has
  less than one chunk unsent; a note for operators covers the access link's queue.

### Added
- `toy/`: `--payload BYTES`, the bytes of each payload.

### Changed
- `protocol.md` §9: the measured implementation announced at publish, over quic-go.
- `toy/golden.txt`: every recorded cell moves.

## v0.8 — 2026-10-28 (`bc7a0a6`)

Stalls are closed for a peer that joins the mesh, under equivocation (two blocks for one slot),
and where a peer's offers are dropped.

### Rules
- `protocol.md` §5.4: a peer that joins a node's mesh is announced what the node holds.
- `protocol.md` §4.2: a copy that waits for its block ties its sender to the root it names, and
  that root's installation makes the sender an offer of the index.
- `protocol.md` §6.1: no peer is asked for a chunk while an earlier ask of it to that peer is
  outstanding.
- `protocol.md` §6.1: where a peer's offers of a chunk are dropped, its queued ask of the chunk goes
  with them, and its promise closes.
- `protocol.md` §4.6: a rebuilt chunk names the block that the chunks it was rebuilt from name.

### Added
- `protocol.md` §4.6: a copy relabelled under the proposer's other block is named open.
- `formal/veil/`: no stall (Q1) with the mesh changing and connections closing, and under
  equivocation for the nodes the source reaches through nodes that installed the builder's block.

### Changed
- `toy/golden.txt`, `toy/golden-v2.txt`: both recordings are made again.

## v0.7 — 2026-10-25 (`d5c1ae9`)

Groups expire with the live window and are named by a key that fixes their slot, and
`formal/veil/` proves A1 and no stall at any size.

### Rules
- `protocol.md` §8.1, §8.3: a group whose slot has left a node's live window is expired for good,
  its tombstone kept until then, and a group without a slot keeps its tombstone `TOMBSTONE_TTL`.
- `protocol.md` §1: a group is named by its key, the hash of its group id and slot.
- `protocol.md` §4.4, §6.4, §8.2: an IHAVE over either of gossipsub's IHAVE limits is recorded, its
  asks waiting for the next heartbeat, where it was ignored.
- `protocol.md` §5.1: the source announces a chunk only to the mesh peers it did not choose for a
  push.
- `protocol.md` §4.6: a rebuilt chunk names an installed block whose bid commits its group.

### Added
- `formal/veil/`: proofs at any size of A1, that an honest node is never penalised, and of no stall
  (Q1).

### Changed
- `protocol.md` §9: where the rerun of the SEACAST post's Figures 4 and 5 does as the document does.
- `toy/golden.txt`: every recorded cell moves under the group's key.

## v0.6.1 — 2026-10-23 (`6606abd`)

§9 follows the rerun of the SEACAST post's Figures 4 and 5, the proof of A1 comes in, and the
protocol text is still version 0.5.

### Added
- `formal/veil/`: the proof that an honest node is never penalised for an ask (A1).
- `protocol.md` §9: an entry on announcing after the decode claim.

### Changed
- `protocol.md` §9: each entry that the rerun changes says so, and the rules that v0.5 added are
  given as the rerun has them.

## v0.6 — 2026-10-21 (`586ffae`)

The protocol is named SEACAST, the formal model comes in with a draft of the next version, and
`protocol.md` is unchanged.

### Added
- `formal/`: the Quint model, which checks v0.5's rules.
- `protocol-v2.md`: a draft of SEACAST's next version, with availability sampling and other object
  types, and the toy's support for it.

### Changed
- The protocol is named SEACAST.

## v0.5 — 2026-10-21 (`10e1f87`)

Six fixes from a model check of v0.4 change the rules, the last resort among them.

### Rules
- `protocol.md` §5.2, §7.2, §4.1: a push to a mesh peer that does not happen is offered to it
  instead, and an offer or answer that a full queue refuses is owed.
- `protocol.md` §6.1, §8.2: every offer is kept, per connection and group, and when every announcer
  of a chunk is parked, each is asked once more, at a wait that doubles (the last resort).
- `protocol.md` §3, §4.4, §4.2: no ask goes out before the block is installed, and what was offered
  meanwhile is asked for then.
- `protocol.md` §6.1, §7.2, §4.6, §8.1: the retry, the writer's ask filter and a returning decode
  check expiry, and a group's pull state goes at its expiry.
- `protocol.md` §7.2, §6.1: a promise starts when the ask is written, and closes with its
  connection.
- `protocol.md` §4.2: a copy that the deferred store refuses counts as its sender's offer.

### Changed
- `protocol.md` §8, §9: the state, limits and constants follow, and §9 lists these rules among those
  the measured implementation predates.
- `toy/`: the recorded results move.

## v0.4 — 2026-10-13 (`fe41907`)

The source's HAVE names only what it has sent, and the toy runs beside the research harness.

### Rules
- `protocol.md` §5.1: the source's HAVE names only the chunks it has sent [P4].
- `protocol.md` §7.1: a writer that takes a window slot wakes the next one while slots remain.

### Added
- `toy/xcheck.py`, `--send-buffer`: the toy runs on a harness cell's network.

### Changed
- The text takes the posts' terms: *chunk* for the unit on the wire, *node* and *forward* where it
  said relay, and *Informed Diffusion* for the protocol.

## v0.3 — 2026-10-05 (`181be31`)

This repository's first release holds the protocol in pseudocode, and a toy that runs it.

### Rules
- `protocol.md` §4.6: a node that has decoded a group pushes the chunks it rebuilt to the mesh
  peers that still lack enough chunks to decode (since v0.2).
