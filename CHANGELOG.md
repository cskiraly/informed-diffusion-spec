# Changelog

Each release is a tag (its commit in the heading below), and `protocol.md` names its version at the top.
Changes after the latest tag are on `main`; when there are any, this file's first entry names them. A
release changes the text and its checks, not earlier measurements: each measurement says which code it
ran (`protocol.md` §9 for the SEACAST post's figures).

## v0.10.1, 2026-11-15

The text rewritten for readers; the code unchanged, some comments reworded.

- `protocol.md`, every section. A rule to a paragraph, with new paragraphs that say what each handler
  does, written from its code. The reasons move to an unnumbered Rationale at the end of a section,
  with the alternatives not taken. What this version leaves open is marked **Open:**. §0 says how
  the document is organized and how to read it, and a glossary after §9 defines its terms.
- A rule's history is left to this changelog, measured figures to §9 and the companion documents,
  and review labels are dropped. Three code comments that called the last resort B′ name it, on the
  same lines.
- Two sentences that still had the source announce at publish (§5.1, §5.4) follow the code, which
  announces at the acknowledgement (since v0.9).
- `README.md` describes the next version's draft, `formal/` and `formal/veil/` without their
  history, and without the toy's one-seed figures.
- This changelog's v0.10 and v0.9 entries are lists.
- The toy, its recorded cells, `protocol-v2.md` and `formal/` are unchanged.

## v0.10, 2026-11-15 (`1643c01`)

`protocol.md`:
- A chunk that arrives before its block is installed now waits by rules written out as code (§4.2,
  §6.1: `tie_room`, `drop_offer` and the `of=` form of `close_promises`), and four rules are added
  for what waits:
  - a deferred copy of a group beyond its sender's limit of unknown groups is ignored;
  - at installation, a tied index the group does not have is dropped;
  - when a group's count becomes known, what named an index at or beyond it goes (§4.2, §8.1);
  - what waits for a root that never installs goes when its slot leaves the live window or its group
    expires (§4.2, §6.4, §8.1).
- Level 1 rejects a copy whose slot is not its block's (§3).
- An IHAVE entry is a bitmap or a chunk's valid id, anything else ignored without penalty, and an
  IHAVE's bitmap is held to a HAVE's limits: one naming an index at or beyond the group's known count
  is ignored and counts against the sender (§4.4, §8.2).
- The announcers beyond a chunk's ordered list are tried in an order of the node's own, a hash of
  the chunk and the peer keyed by a secret the node draws, which no peer can predict or arrange
  (§6.1, §8.1).
- Two weaknesses are named and not addressed in this version: an announcer that is never parked
  holds the last resort off a parked honest provider (§6.1), and one IHAVE naming a chunk under two
  keys gets its sender asked once per key (§4.4).
- §6.2 says when the stop-pull test decides, §4.4 why the lookup of `known_id` is kept, and §9 which
  announcers the measured retry took.

The toy:
- Its default transport keeps §7.3's rule, one entry at a time per connection (`--send-buffer 1`;
  `--send-buffer 0` is the earlier transport, which takes every write at once). Every recorded cell
  but `rr-stripe` changes in both recordings, at seed 7 by −98 to −3 ms at the median, −99 to −2 ms
  at the tail and −0.72 to −0.03 copies (`push` in `golden.txt`: 464 → 427 ms, 533 → 522 ms, 2.49 →
  2.15 copies), the recordings made again. A cell `push-deep` keeps the earlier transport and gives
  the earlier `push` line exactly.
- A block can install late at some nodes (`--late-block`), and a recorded cell where 18 of 60 nodes
  do runs §4.2's deferral and fails if anything is left waiting. The README says why its on-time
  nodes finish later: the late peers hold slots of the source's sending window (§7.1).
- Every table of `protocol.md` reads without creating an entry, and known-answer scripts
  (`toy/*_known.py`) check the new rules. `toy/check.py` has fifteen cells.

The draft of SEACAST's next version (`protocol-v2.md`), changed since v0.6:
- Every decision of its §8 is taken, those chosen among alternatives with what was not taken. Among
  them: a protocol of its own carried by §7's three bindings (`[D1]`); a sampler's reach, a coverage
  floor built for diversity with routed sample requests on LiteDAS's two phases (`[D12]`); a
  column's and a row's offers to every joined peer, offers to the relations only permitted for
  columns (`[D5]`); the row pull delay of 1 s, shorter at a cost where nodes lie about their
  holdings (`[D8]`); the promise's length; and the window in bytes.
- §6.3 states its limits by their bounds, the values the client's.
- v0.7's, v0.8's and v0.9's rules are carried in, v0.9's acknowledgement for every object type
  (§4.7).
- The relations' upkeep is written out and runs on the toy's wire (§4.1: a GRAFT is answered,
  JOINs, GRAFTs and PRUNEs are owed at a full queue, a symmetric type keeps one relation both ways),
  and `toy/graft_check.py` checks the JOIN and GRAFT exchanges in every interleaving for one link and
  one relation, in small bounds. A PRUNE names its direction from its sender's side (§4.1), and a
  binding validates a block's cell header no later than it installs the block (§4.2).
- A source publishes at once to the links it has in a family it does not custody (§4.7,
  `source_pool`, `SOURCE_FLOOR`), the payload's too, where `protocol.md`'s source with no mesh peer
  sends nothing (§6.1), and owes a push to them that a full queue refuses, as to a relation peer
  (`unpush`). A source's own chunks go before its offers and answers (§4.12).
- Repair keeps a floor of custodian links, and its sample, rebuilt cells marked seen and a
  custodian's alarm are options (§4.6).
- The probe of a claim judges the claimant by its own copy only, is marked so that the claimant
  answers it whatever the asker holds (`Want.probe`, once per asker and group), is kept in the
  asker's queue while it waits, and asks for a cell drawn at random among those lacked, where it
  asked for the lowest. The standalone binding carries its mark and `standing` in one flags byte,
  and three cases it does not yet handle are named open (§4.6, R5).
- §7 says how a sampler rides gossipsub's wires, and frames the standalone binding as Waggle does.
- The toy gains options for these (among them `--sample-cover`, `--upkeep`, `--churn`,
  `--col-announce`, `--row-announce`, `--alarm-wait` and `--rebuilt-seen`), `--topology` also loads
  the research harness's DAS graphs, and `golden-v2.txt` is recorded again where a carried rule
  changed its events. `toy/sampler_graph.py` and `toy/sampler_match.py` compute `[D12]`'s figures
  on graphs alone.
- `toy/check.py` gains a cell with stock gossipsub's IHAVE limits (`ihave-limits`), recorded in
  `golden.txt`. The draft's figures measured before the toy's transport change say so (its §0), and
  its header lists what it carries of this version's `protocol.md` changes and what not yet, where it
  has functions of its own.

`formal/` and `formal/veil/` are unchanged: their models are of v0.5's and v0.8's rules.

## v0.9, 2026-11-10 (`ed5745a`)

- The source announces a chunk to the mesh peers it did not push it to, and its HAVE names the
  chunk, at the chunk's acknowledgement: the first HAVE naming it from any peer, or its first copy's
  window timeout (§5.1, §4.3, §7.1). This replaces v0.8's announcement at publish and HAVE at the
  write. Announced at publish, the offers raced the pushes wherever the transport takes the batch at
  once, and the source answered asks for chunks whose pushes were still queued.
- A new §7.3 says what the transport below the writer should hold: a writer should hand a chunk to
  the transport only while the connection has less than one chunk unsent; what that bounds and what
  it does not; how quic-go and TCP keep it; and a note for operators on the access link's queue.
- §9 records that the measured implementation announced at publish over quic-go.
- The toy's events change in every recorded cell of `golden.txt` (at seed 7 by −14 to +1 ms at the
  median, −47 to +12 ms at the tail and −0.11 to +0.06 copies), the recording made again.
  `golden-v2.txt` was unchanged by it, since the next version kept its own source until it took this
  rule (v0.10).
- The toy takes `--payload BYTES`, the bytes of each payload (default 1 MiB), the compressed size
  following at the same ratio, so that small sizes give hand-counted cases (16384 bytes: K = 1,
  N = 2). The recorded cells are unchanged by it.

## v0.8, 2026-10-28 (`bc7a0a6`)

A peer that joins a node's mesh is announced what the node holds, so a peer that joins after a chunk
was forwarded, or whose connection closed, is offered it (§5.4; F9 in `formal/`); a copy that waits
for its block ties its sender to the root it names, and that root's installation makes the sender an
offer of the index, in place of v0.5's offer of a refused copy (§4.2); and no peer is asked for a
chunk while an earlier ask of it to that peer is outstanding (§6.1). The last two close F6, a stall
under equivocation. Where a peer's offers of a chunk are dropped, with its tie or at their expiry, its
queued ask of the chunk goes with them and its promise closes (§6.1): kept, the ask could keep a node
from ever asking a parked announcer, a stall. A rebuilt chunk names the block the chunks it was
rebuilt from name (§4.6), so among honest nodes every copy names the builder's block, as their proof
assumes, as long as no node relabels a chunk under the proposer's other block: such a copy is
authentic, honest nodes forward it, and a node behind them can stall, a gap §4.6 lists as open, with
its options. `formal/veil/` proves no stall (Q1) with the mesh changing and connections closing, and
under equivocation for the nodes the source reaches through nodes that installed the builder's block.
The rule against a second ask changes the toy's events in all twelve recorded cells and in eleven of
the next version's, both recordings made again; asks that go with their announcer's offers change
none.

## v0.7, 2026-10-25 (`d5c1ae9`)

A group whose slot has left a node's live window is expired for good, its tombstone kept until then,
and a group without a slot keeps its tombstone `TOMBSTONE_TTL` (§8.1, §8.3); a group is named in
diffusion by its key, the hash of its group id and slot, so its slot is fixed (§1); an IHAVE over
either of gossipsub's IHAVE limits is recorded instead of ignored, its asks waiting for the next
heartbeat's retry, with the limits' values the client's (§4.4, §6.4, §8.2); §5.1's source announces a
chunk only to the mesh peers it did not choose for a push, so a push its queue refuses is offered
once; and a rebuilt chunk names an installed block whose bid commits its group (§4.6). §9 says where
the rerun of the SEACAST post's Figures 4 and 5 does as this document does (v0.6.1). `formal/veil/`
proves A1 at every place a node penalises, and no stall (Q1), at any size; the no-stall proof found
the IHAVE gap. The toy runs the text as written: under the group's key every recorded cell moved, as
under any renaming.

## v0.6.1, 2026-10-23 (`6606abd`)

§9 after the rerun of the SEACAST post's Figures 4 and 5 on an implementation with version 0.5's
rules and the paced source HAVE: each entry the rerun changes says so; the rules added after v0.4 as
the rerun has them; and a new entry, announcing after the decode claim, which accounts for the
implementation's extra HAVEs against the toy. `formal/veil/`, the proof of A1, is in this release.
The protocol text is still version 0.5.

## v0.6, 2026-10-21 (`586ffae`)

The name SEACAST; the formal model (`formal/`), which checks v0.5's rules; and a draft of SEACAST's
next version (`protocol-v2.md`), which adds availability sampling and other object types, with the
toy's support for it. `protocol.md` and the toy's recorded cells were as in v0.5.

## v0.5, 2026-10-21 (`10e1f87`)

Fixes from a model check of v0.4: a push to a mesh peer that does not happen is offered to it
instead, and an offer or answer a full queue refuses is owed (§5.2, §7.2, §4.1); every offer is kept,
per connection and group, and when every announcer of a chunk is parked, each is asked once more, at a
wait that doubles (§6.1, §8.2); no ask before the block is installed, and what was offered meanwhile is
asked for then (§3, §4.4, §4.2); expiry is checked by the retry, the writer's ask filter and a decode
that returns, and a group's pull state goes at its expiry (§6.1, §7.2, §4.6, §8.1); a promise starts
when the ask is written and closes with its connection (§7.2, §6.1); and a copy the deferred store
refuses counts as its sender's offer (§4.2). §8's state, limits and constants follow, and §9 lists
these rules among those the measured implementation predates (v0.6.1 records the rerun on one that has
them). The toy runs the text as written, so its recorded results moved.

## v0.4, 2026-10-13 (`fe41907`)

The source's HAVE names only the chunks it has sent (§5.1, [P4]), which removes the one certain sign
of the source; a writer that takes a window slot wakes the next one while slots remain (§7.1); the
toy runs on a harness cell's network (`toy/xcheck.py`, `--send-buffer`) to set the two side by side;
and the terms follow the posts: *chunk* for the unit on the wire, *node* and *forward* where the text
said relay, and *Informed Diffusion* for the protocol.

## v0.3, 2026-10-05 (`181be31`)

The protocol in pseudocode, and a toy that runs it: this repository's first release. Since v0.2, a
node that has decoded a group pushes the chunks it rebuilt to the mesh peers that still lack enough
chunks to decode (§4.6), instead of holding them.
