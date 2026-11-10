# Changelog

Each release is a tag (its commit in the heading below), and `protocol.md` names its version at the top.
Changes after the latest tag are on `main`; when there are any, this file's first entry names them. A
release changes the text and its checks, not earlier measurements: each measurement says which code it
ran (`protocol.md` §9 for the SEACAST post's figures).

## Draft v0.9, 2026-11-10 (on `main`, not yet tagged)

The source announces a chunk to the mesh peers it did not push it to, and its HAVE names the chunk, at the
chunk's acknowledgement: the first HAVE naming it from any peer, or its first copy's window timeout (§5.1,
§4.3, §7.1), in place of v0.8's announcement at publish and HAVE at the write. Announced at publish, the
offers raced the pushes wherever the transport takes the batch at once, and the source answered asks for
chunks whose pushes were still queued. A new §7.3 says what the transport below the writer should hold: a
writer should hand a chunk to the transport only while the connection has less than one chunk unsent, what
that bounds and what it does not, how quic-go and TCP keep it, and a note for operators on the access
link's queue. §9 records that the measured implementation announced at publish over quic-go. The toy's
events change in every recorded cell of `golden.txt` (at seed 7 by −14 to +1 ms at the median, −47 to
+12 ms at the tail and −0.11 to +0.06 copies), the recording made again; `golden-v2.txt` is unchanged,
since the next version keeps its own source. The toy takes `--payload BYTES`, the bytes of each payload
(default 1 MiB), the compressed size following at the same ratio, so that small sizes give hand-counted cases
(16384 bytes: K = 1, N = 2); the recorded cells are unchanged by it.

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
