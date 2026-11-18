# The protocol, executed: a toy simulator

[`protocol.md`](../protocol.md) is written in Python-like pseudocode, in the style of the consensus
specs. This directory runs it. `extract.py` takes every `python` block of the document, in order,
and the toy executes that code once per simulated node, with each node's state in its own
namespace. The document stays the source of truth: change it, and the next run executes the change.

The toy is small (pure Python, no dependencies), so it is a place to try a rule before anyone
implements it, and a check that the document is complete enough to run. It is not a measurement.
The posts' measurements come from a research harness, a Go simulation of the research
implementation (Prysm with a go-libp2p-pubsub fork) on a virtual clock. The toy copies the
harness's model of the network where it can, so that the two can be set side by side, but its
network is simpler (below), and its numbers are not to be quoted in place of the harness's.

## Running it

```
python3 run.py --net home --seed 7                 # tier 4 in the all-home network, 500 nodes, 6 payloads
python3 run.py --net dcb20 --seed 7 --without 17   # with a datacenter builder, without card 17
python3 run.py --net home --stripe on              # every source stripes, as the harness's tier-4 cells did
python3 run.py --net home --rebuilt none           # nothing rebuilt, as in the harness's tier-4 cells
python3 run.py --latency-only --seed 7             # the latency summary line only
python3 check.py                                   # the document still runs as recorded (below)
python3 run.py --topology cell.jsonl.gz --rebuilt none --stripe on   # a harness cell's own network (below)
```

Networks (`scenario.py`): `home` (every node 50/100 Mbps), `dc20` (20 % of nodes at 1 Gbps,
home builder), `dcb20` (the same and a 1 Gbps builder), `bld` (the 1 Gbps builder alone). A cell,
one run of one configuration, prints what the harness prints for each payload: the receivers' p50
and p99 completion time (the K-th distinct chunk, from the publish instant, nearest rank) and the
bytes each node received, in copies of the compressed payload, chunks and control apart. Payloads
2 to 6 are the warm ones.

A 500-node cell takes about five minutes on one core and about 250 MB.

**The transport** (since 2026-11-15): a connection's transport takes one entry at a time
(`--send-buffer 1`), so a writer hands a chunk over only when the previous one has left, as
`protocol.md` §7.3 asks and as the harness's stream writes block. `--send-buffer 0` is the earlier
default, a transport that takes every write at once (§7.3's rule not met); `--uplink rr` has no send
buffer and always runs that way. Figures and comparisons in this README measured before that change
ran with that earlier transport unless they say otherwise.

## Checking a change

`check.py` runs fifteen small cells (60 nodes, three payloads) in parallel and compares each with
`golden.txt`. Each cell's digest hashes every event the simulator processes, in order: its time,
its node, the function it runs, and its int and bytes arguments. A change in what any node does, at
any moment, changes the digest, even when the printed numbers stay the same.

The thirteenth cell, `ihave-limits` (2026-10-27), sets stock gossipsub's two IHAVE limits
(`--ihave-limits 10,5000`).
- The others set none, so it is the one cell where asks are held back to the next heartbeat
  (`protocol.md` §4.4).
- In `protocol.md`'s run, 26 799 asks are held back. The warm median goes from the `push` cell's
  427 ms to 512 ms, and every node completes.
- At `protocol.md`'s reference values (§8.3, `--ihave-limits 4096,5000`) no cell holds an ask back,
  with or without `--doc v2`: every other cell gives its recorded digest, and this cell, run at
  those values instead, gives the `push` cell's (2026-11-18).

The fourteenth cell, `late-block` (2026-11-15), is the one cell where a block installs after its
chunks arrive (`--late-block 30,400`): 18 of the 60 nodes install each block 400 ms after its
publish, and each keeps at most two deferred copies per peer.
- Everywhere else a block installs at its publish at every node, so it is the one cell that runs
  `protocol.md` §4.2's deferral: `defer`, `tie`, `on_block_installed`, and the ties' release into
  offers.
- In `protocol.md`'s run, 491 deferred copies are kept and 347 refused, 923 ties are released, and
  at the end nothing waits: no copy, tie, reservation or block. Every node completes. Under
  `--late-block` run.py checks both, and fails if either does not hold (`late_drain_known.py`), since
  a leak of state changes no event and so no digest. The warm median goes from the `push` cell's 427 ms
  to 635 ms, and not only through the 18: the 41 nodes that install on time are slower too, at
  628, 616 and 645 ms at their median for the three payloads, against 426, 423 and 420 ms for the
  same nodes without late blocks. The cause is the source's sending window (`protocol.md` §7.1), one
  for all its peers. A chunk pushed to a late node holds its slot until that node's HAVE covers it,
  which can come only after the node installs, or until `WINDOW_TIMEOUT` ("their window slots stay
  held", §4.2), while an on-time peer's comes back within tens of milliseconds. So for the second payload the late peers hold 59 of the 69 slots at 450 ms,
  and the source's sends fall from 30 chunks per 50 ms at its start to about 7 from 150 to 450 ms
  (one seed). The push selectors do not apply §3's rule to push only with evidence that the peer
  holds the block.
- It does not reach `drop_tie`, which needs a copy that names a root whose bid commits another
  group, nor §8.2's limit on ties, which the toy does not set, nor what `drop_stale_waits` drops:
  the toy's slots never leave the live window and its groups never expire. A late node asks
  nothing of a group before its block installs, so the cell also cannot show what a tie does to a
  promise, a park, a last-resort count or the retry's choice: those need a node that has one block
  and waits for another. Known answers on states made by hand have most of these
  (`tie_helpers_known.py`, `tie_release_known.py`, `deferral_rules_known.py`); not the retry's
  choice, nor `drop_tie` for a root whose bid commits another group.
- `--late-block` with `--churn`: since 2026-11-16 a closed connection's ties go with it, with the
  rest of §8.1's per-connection state (`close_known.py`); no recorded cell combines them. It never
  draws a node that publishes, and at 0 % it draws none (`late_draw_known.py`).

The fifteenth cell, `push-deep` (2026-11-15), is the `push` cell with the earlier transport,
which takes every write at once (`--send-buffer 0`, the default until that day): §7.3's rule not
met, a case the document allows and the check keeps. Its line is the `push` cell's line before the
default changed, in both recordings.

Every cell of `golden.txt` runs the source at `protocol.md`'s reference value, `SOURCE_OFFERS = ACK`
(§5.1). `--source-offers publish` sets `PUBLISH`, the source's other choice: its offers at publish and
its HAVE growing at each chunk's first write, as before v0.9's rule. In all fifteen cells it gives the
digest of the document with the source of before that rule put back (v0.8's `publish` and
`origin_sent`, from `c9881d3`'s parent), and none gives its recorded digest (2026-11-18). That
needs the acknowledgement to do nothing at `PUBLISH`: with `origin_acked` acting, `loss-thin` and
`late-block` differ, since there a chunk is acknowledged before the source writes it. `--doc v2`
takes `publish` too: the draft's `SOURCE_OFFERS` (§4.7). The option's other values, `off` and
`late`, act only on offers `publish` itself makes, so since v0.9's rule they change nothing.

Thirty-three scripts hold known answers for what a digest cannot show. Each is a check that can fail, and
where one has a control that must come out the other way, it is named:
- `own_order_known.py`: §6.1's reference order; its control, the rank read big-endian, must differ.
- `ihave_id_known.py`: §4.4, an IHAVE id that is not a chunk's id; a valid id beside it must leave an
  offer. And an IHAVE bitmap of an index beyond the group's known count is ignored and penalised;
  bitmaps within it, or of a group whose count is not known, leave an offer.
- `have_length_known.py`: a HAVE, and an IHAVE's bitmap, longer than `MAX_HAVE_BYTES` (index 8192, in
  1025 bytes) is ignored and penalised, also where the group's count is not known (§2, §8.2), in both
  documents; at 1024 bytes, the controls, both are taken. The count's check stays: in a group known
  to have 4 chunks, a HAVE of index 4 is ignored and penalised, one of index 3 taken.
- `id_parse_known.py`: an ask by id names a group and an index only as a structured id, of exactly
  56 bytes (§2, `group_index`), in both documents: IWANTs of 36, 40, 55 and 57 bytes that begin as a
  held chunk's id get no answer, and one from a peer that claimed the chunk counts nothing against
  it. The controls: the chunk's id and a WantIndex of it are answered, a 20-byte id is not, and the
  claimant's ask of the chunk's id counts against it.
- `tie_read_known.py`: a peer that was only asked about has no tie; the tied peer beside it must
  lose its park.
- `tie_helpers_known.py`: `tie_room`, `drop_offer`, and `close_promises` with `of`, by the values
  they must leave in every table they touch, the tries, last asks and last-resort counts included.
- `tie_release_known.py`: what a tie does to its sender's promise, and its release to the sender's
  park, last-resort count and offer; a peer parked but not tied beside it must keep both.
- `deferral_rules_known.py`: §4.2's rules no honest cell reaches.
  - A copy over its sender's limit of unknown groups is ignored; a peer within it beside it is kept
    and tied.
  - At installation, a tied index the group does not have is dropped; the same peer's other index
    is offered.
  - What waits for a root that never installs goes, through `on_heartbeat`, when its slot (its
    sender's first copy's) leaves the live window or its group expires; a copy of a live slot
    beside it stays.
  - When a group's count becomes known, the offers, asks and ties of an index beyond it go; an
    offer of an index within it stays.
  - Level 1 rejects a copy whose slot is not its block's; the copy as it came passes.

  With `--doc v2` it runs the same states on `protocol-v2.md`'s own `defer`, `on_heartbeat` and
  `fill`, which carry these rules since 2026-11-16.
- `v2_carried_known.py`: the same rules where `protocol-v2.md` has its own functions for offers and
  cells, on a small rows run.
  - An offer's bitmap of an index beyond the group's known count is ignored and penalised; one
    within it leaves an offer.
  - At the cell header, a tied index the group does not have is dropped, and the same peer's other
    index is offered.
  - A sender with nothing left tied under the root loses its tie's slot; a peer still tied for
    another group keeps its slot.
  - A cell's level 1 rejects a copy whose slot is not its header's, for its column and its row; the
    copy as it came passes.
- `close_known.py`: a connection's close under `protocol-v2.md` (`--churn`).
  - The closed announcer's offers, tries, promises, last-resort counts and ties go; its park and
    the kept deferred copy, the controls, stay.
  - A probed claimant that leaves gets no verdict and no penalty, and the duty is re-armed at its own
    time, here already passed, so at once; a connected claimant beside it, the control, is judged.
  - The closed peer leaves the window's line, the writer behind it is woken, and the room its chunk
    held in flight is released.
- `alarm_member_known.py`: the custodian alarm's member (`--alarm-wait`). Its ask's promise and the
  alarm's wait start at the write, not at the decision; a full queue's refusal and a claimant gone
  before the alarm, before the write or after it penalise nobody, and the member rebuilds; a
  close before the write also takes the ask out of the stop-pull exemption. Controls: a silent
  connected claimant is penalised once, and a claimant's own copy leaves no penalty and no rebuild.
- `late_drain_known.py`: the `late-block` cell with a leak put in by hand must fail, and so must
  the cell with a node that gets no chunk; as it is, it must pass.
- `late_draw_known.py`: `--late-block`'s draw and its argument.
- `bid_gate_known.py`: a late node cannot read the group a block's bid commits before the block
  installs; after, it can.
- `table_read_known.py`: that a read creates no entry the tables show (no `in`, `len` or
  iteration sees it), table by table; one write through the same reads must leave exactly the
  entry it wrote. It does not test §8.1's "reading it allocates nothing": the toy keeps an entry
  for each missing key read, until it is written (`bits.py`). Held reads share one entry, a held read
  written after a set fails, the collections' own writes join, and an offer list refuses what
  would bypass `listed`. And the writer after a read of an owed answer. With `--doc v2` it also
  reads the tables `protocol-v2.md` adds (§3: the relations, JOINs, backoffs, standing asks,
  claims, the probe's tables, the repair sample's and the sampler's), which read without creating
  since 2026-11-16.
- `probe_decode_known.py`: a marked probe that reaches a claimant still decoding is kept, the
  first per asker and group, and answered with its exemption when the decode stores the cell. A
  second probe from the same asker is not kept as a probe and gets no exemption; on its `DECLARED`
  link it stands, and the decode answers it as a standing WANT. A plain ask beside them must not be
  answered.
- `standing_decode_known.py`: standing WANTs for cells of a group the node is still decoding, a
  `DECLARED` link's plain one and a `DERIVED` link's flagged one, are answered when the decode stores
  the cells, each charged once against the serving limit; a `DERIVED` link's plain WANT beside them,
  the control, must not be.
- `probe_write_known.py`: the probe's promise and the verdict's wait start when its WANT is
  written; a probe a full queue refuses, or one still unwritten when the wait ends, gets no verdict
  and penalises nobody. A probe written and not answered beside them must be judged and penalised.
- `probe_settle_known.py`: a probe given no verdict while still queued is not written later; a
  refused probe, and one whose claimant closes, return the duty to its own time when that is later;
  after a probe given no verdict, a plain ask of the probed cell queued to the claimant is not
  written, since stop-pull gates it again, and a promise under the probe's key is closed by the
  claimant's copy. A marked ask kept while decoding is answered and charged once, with its exemption:
  alone, repeated, or beside a standing ask of the same asker sent before it or after it, and
  repeated with one slot of the serving limit left. A probe not yet settled must still be written,
  the claimant's own copy before the write must pass it, another peer's copy must leave a written
  probe's promise open, a close when the duty was due must reconsider at once, and a plain standing
  ask must be answered once. Askers on links that are not `DECLARED`, whose marked asks do not
  stand: one, two (each kept and answered once), and one that marks another index too (its first
  stays the one kept). `--controls` runs three broken texts, each caught by its own line.
- `probe_asks_known.py`: once the probe is settled, by a failure or by no verdict (the probe still
  queued, the claimant closed, or a full queue refusing it), a complete member does not ask for the
  probed cell when another peer offers it. Controls: before the verdict the offer is asked for (the
  probe's exemption), an offer of another lacked cell never is (stop-pull), and after a pass the
  cell is held.
- `note_push_known.py`: a send is noted under every group the chunk fills from the ids alone, so a
  chunk of a dropped group, not stored, can be noted; and `unpush` clears every mark `note_push` made,
  the row's as well as the column's. The control: the payload's push undone as before.
- `dropped_group_known.py`: a chunk of a group the node dropped is not stored, sent under the group to
  anyone, or put in the gossip history, as `protocol.md`'s `on_validated` returns. The control: with the
  group live, the same chunk is stored, pushed or offered, and put there. And a row's repair
  (`push_rebuilt`) sends nothing under a dropped column; the control, the column live, sends.
- `dropped_dup_known.py`: after a node drops a group, a copy of a chunk it stored before is still
  acknowledged with a HAVE, since `accepted` is "the id was stored" (§4.2, §8.1), in both documents.
  The group is dropped after its decode claim, as the documents drop one: by a decode that finds no
  codeword (level 2, put in by hand: the toy's decode always succeeds), and by the application's check
  failing (level 3); the HAVE then names every index. The controls: a copy after the claim and before
  the drop is acknowledged the same way, and a copy of a chunk whose first copy came after the drop,
  seen and not stored, is not.
- `discard_queued_known.py`: `drop_group` takes the group's chunks, IHAVEs and IWANTs out of both
  lanes of every queue, by index and by id, with what is owed of it, and keeps its HAVEs (§4.6, §8.1),
  in both documents. Where an entry carries another group's part too (an answer with the frame's asks
  and PRUNE, the IHAVEs of what is owed), that part stays, and the entry with it; the controls are
  the other group's pushes, asks, IHAVEs and owed bits, which stay. An entry kept without its chunk
  is no longer an answer, so with `--doc v2` §4.12's `choose` under `ANSWERS_FIRST` takes the other
  group's answer; the other group's answer keeps its mark. Three entries are queued by hand in shapes
  the documents' code does not queue here, each named in the script: `with_owed`'s entry with an IHAVE
  of each group, built by `with_owed` itself, which builds it only at the write; an IHAVE by id, as a
  peer without card 7 sends, with the ask by id it brings; and an urgent HAVE with an IHAVE beside it.
- `discard_paced_known.py`: after `drop_group`, the pace ticks (card 15, §6.4) announce the group to
  nobody, in both documents: its ids leave every paced job, and a job that named it alone goes (§4.6,
  §8.1). The controls: the other group's ids in the same jobs are still announced, and a job that was
  empty before the drop still takes its tick.
- `close_source_known.py`: a source's link closing with a copy in flight releases the copy's room, and the
  chunk is not acknowledged for it: it does not join the source's holding and is not offered. The control: the
  copy's window timeout does acknowledge it.
- `source_offers_known.py`: at `SOURCE_OFFERS = PUBLISH` an acknowledgement neither grows the source's
  holding nor offers, also for a chunk a peer rebuilt before the source wrote it (a 10 Mbps source among
  faster peers). The control: at `ACK` the same run's acknowledgements act, some before a first write.
- `pull_source_known.py`: the source of a pull-only type (`EAGER` off) pushes nothing at its publish,
  offers every chunk, and its holding names every chunk; every node completes by asks alone. The
  control: with the type eager, the source pushes.
- `rebuilt_once_known.py`: a cell answered through its row, to a peer that stands for it there, is
  not pushed again through its column by the repair, where that peer is a custodian short of it
  (`note_push` under every group the chunk fills). The control: a custodian that made no WANT is
  pushed the cell once.
- `standalone_wire_known.py`: an encoder written from `protocol-v2-bindings.md` §1.
  - Every message kind round-trips at its smallest and largest.
  - §1.3's layout, read from the document, must be the encoder's, field by field, with its fixed
    sizes. The largest bodies equal §1.6's bounds, and §1.7's sizes hold, both tables read from the
    document.
  - A reader refuses a frame over its kind's bound before reading its body, and an unknown kind's
    frame over the largest known kind's room. It refuses a chunk whose stated decompressed length
    is over the bound, snappy input that ends inside an element, and bodies that do not decode.
  - It skips an unknown kind, on the stream and in Waggle's carriage, which reads every kind back.
  - `BINDINGS_DOC=<path>` reads another copy of the document: one with a wrong number, a widened
    field, two fields swapped, a line the check cannot read, or a name defined twice must fail.
  - snappy's reader refuses a length preamble over five bytes, and Waggle's carriage holds an unknown
    kind to the largest known room.
- `standalone_charge_known.py`: under `--wire standalone`, every message kind is charged the length
  of the frame the encoder writes: JOIN, GRAFT, PRUNE, a holding and an offer, WANTs plain and
  flagged, the payload's chunk, and a cell. The cell carries its header on the first push of its
  group to a peer, not on the next push nor on an answer, and again to another peer. An entry
  is charged the sum of its messages, and the window's size of a cell is what its write will
  charge: the header with a first push, none with an answer or a later push.
- `probe_kept_known.py`: while a claimant still decoding keeps an asker's marked probe, that
  asker's marked ask of another, stored, cell of the group is answered as a plain ask, without the
  exemption, and the kept probe is answered with it when its cell is stored; also in the order a
  standing ask, the marked ask, then the other marked ask. The control: one marked probe alone.
- `refusal_report_known.py`: the report of asks left unanswered does not count a marked probe of a
  claimed index as claimed, since it is answered (R5); a plain ask beside it, and a second marked
  probe past the cap, must be counted.

An edit that should change nothing must leave every digest as it is. An edit that changes behaviour
shows which cells moved, with their warm medians before and after; `python3 check.py --update` then
records the new digests, to be committed with the edit. The cells `hold` and `none` have the same
digest: a chunk that is held and never announced is never asked for (§4.6).

A change of names moves every cell without changing a rule: a chunk's push rank (§5.3) hashes its
id, as admission loss does, and the payloads and peer ids are the same at every seed, so a naming
is one draw that seeds do not average out. The group's key (2026-10-23, §1) re-recorded both
recordings this way. With the key replaced by the group id, every cell of both documents kept its
digest; with the key, the cells moved at seed 7 by −10 to +69 ms at the median in `golden.txt`
(`silent` 579 → 648 ms) and by −6 to +74 ms in `golden-v2.txt`. Over seeds 1 to 20 of `push`,
`silent`, `cap-wait` and `without-a`, the mean of the 80 warm medians was 486 to 498 ms across seven
namings: 486 ms for the descriptor's group id, the naming until then; 491 and 493 ms for the same
construction under two other domain bytes; 498 ms for the key and 489 to 497 ms for three other
keys. The key and another key differ by +1.1 ± 3.5 ms (mean ± standard error over the 20 seeds,
each seed's four cells averaged). The next version's column and row groups keep their names, and
its custody and row settings their digests at seed 7, with and without supernodes, samplers and
withheld columns.

Ties and no second ask of a peer at once (2026-10-26, §4.2, §6.1) re-recorded both recordings. No
copy waited for its block in the toy then, so nothing was tied; the rule against a second ask changes
the events of all twelve cells of `golden.txt` and eleven of `golden-v2.txt`, at seed 7 by −7 to +3 ms at the median and −15 to +13 ms at the tail in
`golden.txt`, and by −6 to +3 ms and −10 to +19 ms in `golden-v2.txt`. Over seeds 7 to 9 of the
twelve cells it moved them by −8 to +6 ms at p50, −15 to +34 ms at p99 and −0.04 to +0.03 copies,
where `--check-ms 5.01`, a change that alters no rule, moved them by −1 to +5 ms, −13 to +10 ms
and −0.05 to +0.01. Its digests at seed 7 are those of the run that measured it.

Asks that go with their announcer's dropped offers (2026-10-28, §6.1) change no event in either
recording: nothing was tied in the toy then, and its offers expire only after their group has completed.

The source's announcement and HAVE at the acknowledgement (2026-11-10, §5.1) re-recorded
`golden.txt`: every cell, at seed 7 by −14 to +1 ms at the median, −47 to +12 ms at the tail and
−0.11 to +0.06 copies. The toy's transport then took a write at once (`--send-buffer 0`, its default until 2026-11-15), so at publish
the source's offers used to leave with its pushes still queued and drew asks for them; at 60 nodes
and degree 30 the asks the publisher receives fall to about a third and its upload by about one
payload. One cost appears with it: the publisher's HAVE names a chunk about a round trip later than
before, and a mesh peer that got the chunk from a forwarder meanwhile may push it back to the
publisher (a few chunks a payload at that size; cancel drops the pushes still queued when the HAVE
arrives). `golden-v2.txt` was unchanged by it: the next version kept its own source until it took
the rule for every object type (2026-11-11) and was recorded again.

## How it maps onto the document

| file | what it holds |
|---|---|
| `extract.py` | the document's code blocks, in order, and a table of rewrites, each of which must match exactly once (empty: the document runs as written) |
| `node.py` | a node: the document's code executed in its namespace, and the helpers §8.1 lists as "not written out" |
| `bits.py` | bitmaps, and maps whose missing entries read as empty without being created (§8.1) |
| `wire.py` | stand-ins for the wire types of §1 and §2, and the bytes each message is charged |
| `sim.py` | the event loop, the links, the source, the heartbeat and the measurements |
| `scenario.py` | latency, connections, the mesh and the bandwidth classes |
| `run.py` | the command line |
| `check.py`, `golden.txt` | the check above, and its recorded digests |
| `xcheck.py` | the harness's network loaded from its dump, and the counters and invariants it prints, counted here the same way (below) |
| `graft_check.py` | `protocol-v2.md` §4.1's JOIN and answered GRAFT: its functions as written, on two nodes, over every interleaving from the link's first JOIN, for one link and one relation, with `--both` for a `SYMMETRIC` type's relation (an end that holds it one way acts on it at any count), `--diverged` to start from linked ends that disagree (the yes again; with `--both`, every way but whole or empty at both), `--doc` for another version of the text (its three controls in `controls/` must fail) and `--model` for the abstract comparison of the three ways (`python3 graft_check.py`: "ok", about 2.5 minutes and 2.3 GiB) |

What the toy adds to the document, and nothing else:
- **The environment the document assumes:** the clock (`now`, `after`), the per-peer queues and
  their writer (`wake`), the stock heartbeat duties (the message cache's windows, TTLs counted in
  heartbeats), and §8.1's helpers.
- **A measurement hook:** `claim_group` is wrapped to record when each node reaches K.
- **Stand-ins:** chunks carry no bytes, only their length and identity; the Merkle proof always
  checks (only honest nodes run here); a decode returns the source's chunks and takes 5 ms
  (`--check-ms`; the document leaves a decode's duration to the implementation). `HaveBitmap` and
  `WantIndex` are replaced by classes that know their wire size and compare asks by value.
- **Card switches:** `--without N` turns card N off where the document reads a switch (`CANCEL`,
  `RAREST`, `PROJECT`, `PACED`), a constant (`R`, `STRIPE_UPLINK`, `R_NODE`) or the window (`W`).
- **Variants and stresses the document does not specify:** rebuilt chunks held or announced
  instead of pushed, or none rebuilt at all (`--rebuilt`), a cap on the chunks pushed per peer
  (`--rb-max`) and a random wait before the push (`--rb-jitter-ms`); the harness's withholders and
  silent nodes (`--fault`; a silent node pushes nothing it rebuilt, as in the harness), chunks
  lost at admission (`--loss-data`) and thin links (`--up`, `--down`). The loss is a refusal at
  admission (`enqueue` returns false), so a lost push is offered instead (§5.2); it hashes the
  node, the peer and the chunk, so a chunk lost once to a peer is lost every time, and an answer
  owed for it (§4.1) is dropped when the writer queues it again.
- **What the runs leave out:** every block installs at its publish, at every node, so nothing is
  deferred or asked for at installation, except under `--late-block` (the `late-block` cell,
  above); groups do not expire, and none is dropped, since a decode always returns the source's
  chunks and nothing fails level 3 (§4.6); connections do not close; the
  queues have no limit but the loss above, and neither IHAVE limit is set (§8.2) but in the
  `ihave-limits` cell, so elsewhere nothing is held back to the next heartbeat (§4.4); set to §8.3's
  reference values, they would hold nothing back either ("Checking a change"). The
  document's rules for the other cases are not exercised here.

## The network

- **Latency:** the harness's geographic model
  ([`testing/gossipsim/geo.go`](https://github.com/cskiraly/prysm/blob/followup-part1/testing/gossipsim/geo.go)),
  reproduced exactly: five regions, the same base matrix and the same per-pair jitter, from the
  same seed. Seed 7 prints the harness's own line, one-way mean 56 ms, p10 8, p50 61, p90 99.
- **Connections and mesh:** a random 70-regular graph (a circulant mixed by edge swaps, as the
  harness builds it, though not the harness's graph for the seed), and a gossipsub mesh kept
  between 6 and 12 by grafting and pruning, around D = 8. The mesh is built before the first publish
  and no connection closes, so §5.4, a peer joining the mesh, never runs here.
- **Links:** each node has an uplink and a downlink. A writer hands its entries to the
  connection's transport, one at a time by default (below), as `protocol.md` §7.3 asks; the window
  (card 14) is what holds chunks back, as in the document. The uplink is shared equally by the connections with
  something to send (processor sharing), the fluid limit of the harness's FQ-CoDel, which serves
  per-peer flows a packet at a time; `--uplink rr` sends whole entries in turn instead. The
  downlink is a FIFO over the entries that reach it.
- **Not modelled:** QUIC's congestion control and CoDel's drops, so a fast sender is never slowed
  by a slow receiver's link; processing time (the harness runs on a virtual clock, where processing
  is free too).
- **The transport's buffer:** one entry at a time per connection (`--send-buffer 1`, the default
  since 2026-11-15); `--send-buffer 0` takes every write at once, as `--uplink rr` always does (below).

## Side by side with the harness

The harness can write the network a cell ran on (`SEGMENT_XC_DUMP=<path>`): each node's uplink and
downlink, its connections with the latency model's one-way delays, each node's push degree, the
faulty set, and at every publish the publisher and every node's mesh. `--topology <path>` runs
the toy on exactly that network, so what still differs is the link model and the rules. Node ids
are the harness's indices plus one.

With `--topology` (or `--xcheck` alone) the toy prints, after each message, the harness's own
`xcheck` line per population: what the nodes sent, counted at the sender's transmit after the
writer's filter (where the harness counts at the stream write), what they received, and the
invariants the document's rules imply, each a count that must be zero:

- `budget`: a forwarding node that pushed one chunk more often than its push degree;
- `window`: a node with more slots in flight than `W`;
- `overlap`: an ask for a chunk decided while an earlier ask for it is open (inside `IWANT_WINDOW`, not
  yet held), timed at `may_ask`, where the harness's request ledger times its asks too;
- `late`: a chunk sent to a mesh peer whose HAVE for it (in an IDONTWANT, the only carrier that feeds
  `peer_has`) had reached the sender earlier in the message, held or since expired, as the harness's
  ledger reads it; `late_live` counts those the sender still held, which cancel should have dropped;
- `fault`: a chunk from a silent node, or an answer from a withholder.

The recorder reads node state without creating entries and schedules nothing, so a run's events
and digest are the same with it or without it. A duplicate is a chunk received before, as the
harness's seen cache counts it, not one held only since the decode. It counts tier 4's events and
runs under `--doc v03` only: under `--doc v2` its window hook takes the wrong arguments.

**A DAS dump** (the research harness's column proxy, 2026-11-01) runs under `--doc v2 --setting
custody` or `rows`. Besides `net`, it has records of its own:
- `network`: the base graph;
- `shape`: the links the harness added, each with its pass (custody floor, the proposer's fanout,
  the repair floor);
- `faults`;
- `das`: each node's custody as its columns, the supernodes, the reconstructors and the row subnets;
- from a running cell, a `block` record and a mesh per column topic.

The toy takes these in place of its own draws, and the protocol's derived interest reads the dump's
custody and row subnets. The graph is taken whole: no floor link is added. The meshes are the
running cell's first block's, or are built on the graph where the dump has none (one resolved
without a run). The proposer's relation stays the toy's: its custodian links per column. The dump
gives `--cgc`, `--blobs`, `--row-subnets`, `--reconstructors`, `--repair-floor`, `--source-floor`,
`--supernodes` and `--samplers`, so these are refused. A running cell's blocks give `--withhold`, and
cap `--msgs` at the blocks dumped. `--fault`, if given, names what the dump's faulty set does: the
toy's draw of that share must be the dump's set (both are the harness's failSelect).

The load stops where the records disagree:
- `net`'s edges must be `network`'s plus `shape`'s, one-way delays included;
- `faults` must repeat `net`'s fault fields;
- the supernodes must be exactly the nodes custodying all 128 columns;
- a node's mesh on a column must be empty unless it custodies the column, and hold links only;
- the proposer must be node 0 in every block (per-block proposers are not run yet);
- the withheld columns must be the last ones;
- nothing may be preseeded, and there may be no samplers.

The `dump graph:` line reads the graph as the harness's `graphLine()` does. It also says how far the
graph falls short of the floors `custody_topology` builds. On the rows network of 2026-11-01, 482
of 499 row members have fewer than the floor's 6 fellow members as links: the harness adds no
subnet floor.

## Known differences from the harness

- **Bytes.** Without congestion control, a sender is never held back by a slow receiver, so the
  toy's byte counts run above the harness's.
- **Repair.** A decoded node pushes the chunks it rebuilt (§4.6, `push_rebuilt`), and so does the
  toy by default. The toy's repair costs more extra bytes than the harness's, on a clean network
  too, and why is not known yet: its repair bytes are not the protocol's.
- **The transport.** Since 2026-11-15 a connection's transport takes one entry at a time
  (`--send-buffer 1`), which matches the harness on the source's asks, answers and cancels and on
  the forwarding nodes' cancels (n = 100): the harness's stream writes block, so its writers
  interleave and its queues hold their backlog, where cancel acts. The earlier default,
  `--send-buffer 0`, completes a write at once, as if a connection's transport took any amount
  ahead of the link: a writer woken first can then hand its whole queue over while window slots
  remain, and the entries behind it go straight after. At publish the source's mesh peers then get
  their few pushes and every announcement at once, and ask the source for most chunks.
- **The graph.** The latencies are the harness's for the same seed; the connection graph and the
  mesh are the toy's own, unless `--topology` loads the harness's.

## What running it found in the document

The document's code runs as written: `extract.py` rewrites nothing. Making it run first found nine
places where it was not yet executable or left a choice open, all fixed in the document on
2026-10-03:

1. **A literal with a unit** (§6.1), `IWANT_WINDOW + 5ms`: now the constant `RETRY_SLACK` (§8.3).
2. **Declarations without constructors** (§1, §2): `Shard`, `HaveBitmap` and `WantIndex` declared
   fields only, and the code built `HaveBitmap(g, b)` positionally against a declaration whose
   first fields were `magic` and `version`. All three are now containers built by field name, with
   `MAGIC` and `VERSION` fixed by the type.
3. **Set literals where bitmaps are meant** (§5.1, §5.2): `announce(p, g, {i})` passed a set into
   bitmap arithmetic; now `bitmap({i})`.
4. **A blocking call** (§7.2): `slot_held[p] = acquire_slot(p); continue` had to wait for a slot.
   `next_to_send` now returns `WAIT`, and the window's functions are written out (§7.1).
5. **Whether a waiting writer keeps its place** when an urgent entry wakes it: it does, and §9 says
   the measured writer lost it. Writing the window out also showed a stall the prose hid: when the
   first writer in line leaves with nothing to send, the next must be woken if a slot is free.
6. **Empty responses** (§4.1): `respond` queued an entry with no asks, answers or prunes; it now
   sends nothing.
7. **A snapshot or a live bitmap** (§4.2): `send_have` passed `mine[g]` itself; it now copies it
   when the HAVE is made.
8. **Which untried announcer to ask** (§6.1): `untried` and `least_recently_tried` were named, not
   defined, and `untried(...) or least_recently_tried(...)` failed on a peer id that reads as false.
   Both are written out: the earliest announcer not asked yet, else the one asked longest ago (§9
   notes the measured order, by peer id).
9. **How long the check takes** (§4.2, §8.1): `start` now runs a task for as long as it takes, and
   the document says it does not fix a decode's duration.

With these, the toy's 60-node smoke cell printed the same results as before, down to the number of
events processed: the fixes wrote down the choices the toy had made.

A tenth was found on 2026-10-07 by running the custody setting of `protocol-v2.md` (below), and
fixed in `protocol.md` since the window is v0.3's:

10. **The line of writers stalled while slots were free** (§7.1). A writer that took a slot did not
    wake the next writer in line, so when several slots freed at one instant (a holding bitmap
    acknowledging several chunks, several window timeouts) only one chunk went out and the line
    waited for the next release. Under tier 4 this throttled the source a little without costing
    time; under 128 column groups from one proposer the window sat at ten chunks in flight of 1375
    and the second block barely left the source. `acquire_slot` now wakes the next writer when
    slots remain. The twelve cells were re-recorded: completion times moved by at most 17 ms either
    way, copies rose by 0.03 to 0.12 (`cap-wait` 1.64 → 1.66, `dcb20` 3.20 → 3.32, `push` 2.35 →
    2.41), since chunks that had waited in the line, and were pulled meanwhile, now go out.

## The next version (`--doc v2`)

*The next version is a draft, checked in this toy only (its banner). Figures below from fewer than ten
seeds, a single seed unless stated, are toy checks of a mechanism, not measurements. Those of runs
with a payload (tier 4, variant C) were recorded before 2026-10-23, under the descriptor's group id
as the payload's name; under the group's key their exact values move as any renaming's do
("Checking a change"). Column and row groups are named as before.*

[`protocol-v2.md`](../protocol-v2.md) is run on top of `protocol.md`: `extract.py` pulls both
documents' blocks, v0.3's are executed first and the next version's after them in the same namespace, so
the next version redefines what it changes (`on_frame`, `on_chunk`, `forward`, `announce`, the holding and
offer handlers, `on_want`, completion and repair, `publish`, the heartbeat) and keeps what it says
carries over (the ask discipline, `choose_push`; the window and the writer as its §4.11 and §4.12 adapt them). `node.py` supplies what
the next version leaves to the environment under its tier 4 setting (its §6.1): the payload object type
with its parameters, the join tables, the push relation behind the mesh, and the binding of its
messages onto v0.3's wire (`protocol-v2-bindings.md` §3): a holding is an IDONTWANT bitmap, an offer an
IHAVE bitmap, an ask a `WantIndex`. Relations are static, as the mesh is for v0.3.

`check.py --doc v2` runs the fifteen cells against the next version's own recording,
`golden-v2.txt` (`--update` records it, as for v0.3). `check.py --doc v2 --golden golden.txt`
compares the next version against `protocol.md`'s cells instead (v0.3's until 2026-10-13, v0.4's
until 2026-10-21, v0.5's until 2026-10-25, v0.7's until 2026-10-26, v0.8's until 2026-11-12, v0.9's
since); there a cell whose digest moved but whose numbers did not is reported as such and does not
count, since the next version iterates the relation in peer order where v0.3 iterates the mesh set,
which reorders same-instant sends. On 2026-10-07, with v0.3's slot window, eleven cells reproduced
v0.3's numbers exactly and `rr-stripe` differed by 3 ms at the median; with the window in bytes
(`protocol-v2.md` §4.11) the cells differ from v0.3's by at most 7 ms at the median, 15 ms at the
tail and 0.04 copies either way, which is the writer choosing the entry before taking room and
control taking none, not the unit.

**v0.4's P4 in the next version** (2026-10-21, `protocol-v2.md` §4.7): the source's holding names only the
chunks it has sent. Against v0.4's recording the twelve cells now sit within 3 ms at the median,
16 ms at the tail and 0.03 copies, `loss-thin` aside (§4.13's ask window, at 20 Mbps); without P4
the medians had been up to 102 ms behind. On the settings it costs a slow proposer of columns
(60 nodes, warm medians, before and after; over several seeds the median and the range):

| cell | seeds | p50 | p99 | copies |
|---|---|---|---|---|
| custody, 50 Mbps proposer | 7 to 16 | +116 ms (+53 to +164) | +106 ms (−4 to +175) | +0.02 |
| custody, 1 Gbps proposer (`--net bld`) | 7 to 16 | +6 ms (−1 to +7) | +6 ms (−17 to +27) | +0.02 |
| custody with samplers (20 %) | 7 | +64 ms | +104 ms | +0.02 |
| custody, half withheld, 10 % supernodes | 7 | +58 ms | +40 ms | −0.04 |
| rows | 7 to 16 | +98 ms (+4 to +180) | +132 ms (+96 to +157) | +0.01 |
| rows, `hoardm20`, without and with the repair sample | 7 | +107, +111 ms | +182, +155 ms | +0.02, +0.01 |

The cost is the paced holdings themselves: a proposer of 128 column groups sends one holding per
cell to each peer of that column's scope, about 37 500 more urgent messages over the run at seed 7
(210 153 → 247 686). At 52 bytes each its holdings come to 2.0 MB over the three blocks, 0.68 MB a
block, about 108 ms of its 50 Mbps uplink, which is the cost; urgent entries go first, so its
first copies wait longer in its queue (1 179 → 1 225 ms at the median). Its peers, no longer told
it holds every cell, also offer it cells (84 700 → 94 117 offers). With a 1 Gbps proposer the
holdings cost nothing measurable.

`--merge-holdings on` (`protocol-v2.md` §6.3's `MERGE_HOLDINGS`, an option, off by default) merges
them as v0.4 allows (its §5.1): a holding of a group the node publishes that is still in its queue
takes the newer chunks instead of a second holding going out. It takes back little (P4 against P4
with merging, seeds 7 to 16; `--send-buffer 1` has its own P4 baseline):

| cell | transport | holdings merged | p50 | p99 | copies |
|---|---|---|---|---|---|
| custody, 50 Mbps proposer | writes complete at once | 7.1 % | −10 ms (−18 to −1) | −12 ms (−54 to +7) | 0.00 |
| | `--send-buffer 1` | 17.8 % | −16 ms (−24 to +13) | −18 ms (−55 to 0) | −0.01 |
| custody, 1 Gbps proposer | at once | 68.7 % | −4 ms (−8 to +1) | −2 ms (−14 to +30) | −0.01 |
| | `--send-buffer 1` | 18.5 % | 0 ms (−5 to +3) | −2 ms (−11 to +35) | 0.00 |
| rows | at once | 6.3 % | −4 ms (−44 to +16) | −20 ms (−85 to +30) | 0.00 |
| | `--send-buffer 1` | 11.9 % | −4 ms (−29 to +39) | −19 ms (−83 to +72) | 0.00 |
| rows, liar (`claim20`) | at once | 6.4 % | −8 ms (−38 to +12) | −1 ms | 0.00 |
| | `--send-buffer 1` | 12.1 % | −18 ms (−29 to +9) | −19 ms | 0.00 |

Under `--send-buffer 1` P4 itself costs less (the custody block +80 ms at the median, the rows
+76 ms), since holdings and chunks take turns on each connection there. A fast proposer merges most
of its holdings, since its writer sends many cells in one instant, but it had nothing to take back.
Under the liar fault merging leaves 100 (member, row) pairs short against P4's 108 (80 without P4)
with writes at once, and 57 against 68 (55) with `--send-buffer 1`. Merging takes back little
because most holdings would leave alone: with writes at once, 59 % of the source's holdings at seed
7 find no earlier holding of their group still waiting, in its queue or in the transport; 9.6 %
follow one made in the same instant, which merging catches, and 31 % one still waiting in the
transport, which it cannot reach there.

In the liar cell (`--fault claim20`), whose row members already fail to complete on nine seeds of
ten, P4 leaves more of them short: 108 (member, row) pairs never completed over seeds 7 to 16
against 80, more on seven seeds, as many on two, fewer on one (not traced). Its custody completes
as before, on every seed but 13, where two custodians stay short either way. Tables further down
that predate 2026-10-21 were recorded without P4.

**v0.5 in the next version** (2026-10-21, `protocol-v2.md` §5 and the functions it names in its header):
a refused push or offer is offered with the next write, parked announcers are asked once more, the
gate per object type, the promise from the write (a WANT starts none). Against the next version just
before the merge, with P4 (60 nodes, warm medians; over several seeds the median and the range):

| cell | seeds | p50 | p99 | copies | (node, group) pairs short |
|---|---|---|---|---|---|
| custody, 50 Mbps proposer | 7 to 16 | −2 ms (−5 to +16) | +3 ms (−61 to +75) | 0.00 | 0 → 0 |
| custody, 1 Gbps proposer (`--net bld`) | 7 to 16 | the same events | | | 0 → 0 |
| rows | 7 to 16 | +8 ms (−35 to +37) | +12 ms (−39 to +45) | 0.00 | 0 → 0 |
| rows, liars (`claim20`) | 7 to 16 | +4 ms (−18 to +24) | −18 ms (−393 to +638), 9 seeds | 0.00 | 110 → 4 |
| custody with samplers (20 %) | 7 | −7 ms | +7 ms | 0.00 | 0 → 0 |
| custody, half withheld, 10 % supernodes | 7 | −3 ms | +2 ms | −0.01 | 0 → 0 |
| rows, `hoardm20`, without and with the repair sample | 7 | +9, +8 ms | +8, +22 ms | −0.01 | 0 → 0 |
| custody, `--merge-holdings on --send-buffer 1` | 7 | 0 ms | −9 ms | 0.00 | 0 → 0 |
| custody, `--promise-mode peer` | 7 | +19 ms | −20 ms | 0.00 | 0 → 0 |
| variant C (`--setting c`) | 7 | +1 ms | +5 ms | 0.00 | 0 → 0 |

In the liar cell the row members' short pairs fall from 108 to 2 (none on eight seeds; seed 13's
p99 is infinite both ways, through its two custodians that stay short either way); the rows' own
tail, infinite on every seed before, is finite on eight after, 2.2 to 8.4 s. A toy check at seeds
9, 14 and 15 names the cause: with v0.5's last resort switched off (no parked announcer asked once
more) the short pairs are 12, 24 and 18, as before v0.5 (12, 22, 20); with the candidates limited
to the ordered list of the first sixteen announcers they stay at 0, 1 and 0, as with all of v0.5.
The asks of the last resort delivered 274 and 351 cells at seeds 14 and 15. With
half the columns withheld and supernodes, 107 (peer, group) pairs are parked on a broken promise
against 283. Custody with
`--loss-data 10` leaves 149 (node, group) pairs short over three blocks, against 150 before the
merge: the loss refuses a chunk on a link every time, which the custody setting does not get
around either way (not traced).

Every `--doc v2` run ends with the **invariants report** (`invariants.py`; `--no-invariants` skips
it): the invariants `protocol-v2.md` §6.2 asks of every setting, checked on
the links and the nodes' state without scheduling anything, so the digest is unchanged. It
reports chunks pushed outside the receiver's interest (I3: must be none), offers for indices the
receiver does not want (waste, counted), eager pushes of one chunk by one node above its budget
(R_NODE for a forwarding node, R for a source: must be none), repair copies, the upload per message
by bandwidth class in units of the node's own interest with the duty spread (max over median), the
source's upload in copies of the message, and whether every node completed its interest. The
other two of the invariants `protocol-v2.md` §6.2 lists, a claim whose probe goes unanswered and a cell filling both of its
groups, are checked under the row setting, where deferral and cross-fill exist. Three lines on the
queues follow: how long each class of entry waited from being queued to being handed to the link
(urgent control, asks, offers, answers, the source's answers of chunks it held from the start,
pushes, the source's first copies, repair), how long each took on the link, and what the asks
experienced: the time from a chunk's first ask to its arrival from anyone, whether the asked peer
or another delivered it first, the (peer, group) pairs parked on a broken promise, and the chunks
that arrived at a node already holding them, by class.

`--setting c` (with `--doc v2`) is variant C as a setting of the same document: a colour per index
(`M = N`) and a mesh per colour built on the same connections, so each chunk's pushers are its own
colour's mesh and a node's holdings go to every peer that may push it something. The toy's
indications on the 60-node check cell (degree 30, three payloads, seed 7), not measurements:

| setting | net | warm p50 | warm p99 | copies |
|---|---|---|---|---|
| t4 | home | 493 ms | 577 ms | 2.43 |
| c | home | 424 ms | 519 ms | 3.27 |
| t4 | dcb20 | 246 ms | 349 ms | 3.31 |
| c | dcb20 | 242 ms | 292 ms | 4.79 |

(With v0.3's slot window the same cells gave t4 491 / 570 ms / 2.41 and 247 / 353 / 3.32, and c
426 / 528 / 3.30 and 242 / 294 / 4.85: the payload's chunks are the slot's size, so the unit does
not move them.)

The direction is the harness's (faster tail, more bytes and control); the sizes are the toy's. The
per-colour heartbeat gossip of variant C is not modelled: a peer in any colour's mesh counts as
related, so the heartbeat has nobody to gossip to.

`--setting custody` (with `--doc v2`) is the PeerDAS custody row of `protocol-v2.md` §6.2: a block
of `--blobs` blobs (32) published as 128 column groups whose header is a descriptor-shaped object
with the blob count as N and K = N (no code within a column, `sim.publish_block`), a derived
interest of `--cgc` columns (8) per node from das-core's `get_custody_groups` over the toy's peer
ids, duty FORWARD, `ANNOUNCE_EXTRA = ALL_JOINED`, repair only through supernodes (`--supernodes`,
below), cells of 2048 + 48 bytes with a stub verifier. Node 1 is the proposer and holds every
column. The connection graph is the random regular graph plus the edges subnet peer search would
add: each node keeps `--floor` (6) custodian peers for every column it custodies, or all there are,
and the proposer `--source-floor` (2) for every column; the push relation of a column is a gossipsub
mesh built on its custodians' subgraph (`scenario.custody_topology`), and the proposer's relation is
its custodian links per column. A node's completion is the last of its custody columns to complete,
and copies are in units of its own custody's chunks. Executing this setting found the
window stall (item 10 above) and that card 12's projection assumes a code (`protocol-v2.md` §4.9).
The indications, one seed, with the invariants holding (nothing pushed outside interest, no push
above budget, every custodian complete):

| nodes | degree | proposer | custodians per column | warm p50 | warm p99 | copies of own custody | other nodes' upload per block | proposer upload |
|---|---|---|---|---|---|---|---|---|
| 60 | 30 | 1 Gbps | about 4 | 347 ms | 456 ms | 2.14 | median 1.27 | 2.6 blocks |
| 60 | 30 | 50 Mbps | about 4 | 2 220 ms | 2 479 ms | 1.82 | median 1.24 | 1.6 blocks |
| 500 | 70 | 1 Gbps | about 31 | 531 ms | 697 ms | 1.84 | median 1.05, max 4.1 | 4.4 blocks |

The proposer's upload counts its first copies (two per cell) and the asks it answers; a 1 Gbps
proposer among custodians that pull serves about as much again as it pushes. These are the numbers
with the window in bytes (`protocol-v2.md` §4.11) and a source's own chunks first (§4.12). With
v0.3's slot window the same cells gave 777 / 963 ms and 1.90 copies, 9 173 / 9 475 ms and 1.75,
and 1 011 / 1 207 ms and 1.78: a cell is a sixth of a payload chunk, so the slot window admitted a
sixth of the bytes per round trip and held the 50 Mbps proposer to about 10 Mbps (a 9 MB block at
50 Mbps needs about 2 s; it now takes 2.2) and the 1 Gbps one to about a fifth of its uplink. The
byte window costs a few hundredths of a copy in duplicates, since more pushes complete before a
holding can cancel them. The source rule moves the 50 Mbps row, from 2 444 / 2 907 ms, 1.88
copies and 1.9 blocks under v0.3's order of the queue (`--answers-first v03`), and the 500-node
row's tail from 680 ms at this seed; over seeds 7 to 9 that tail moves between 5 ms sooner and
17 ms later.

At 500 nodes most cells arrive by pull (under the slot window, 221 000 answers against 115 000
eager pushes for 128 000 cells needed), and control is 0.4 copies of a node's custody, which is
where the announce width `[D5]` and the push budget act.

`--samplers PCT` (with `--setting custody`) turns that share of the nodes into samplers, the
FullDAS sampling row of `protocol-v2.md` §6.2: interest `DECLARED`, duty `NONE`, no custody, no
place in any column's mesh and no top-up edges, so a sampler reaches a column only through the
custodians among its random peers. At block arrival each sampler draws `--samples` (8) cells of the
block at random and declares each to one link whose interest includes it, as §4.10 says: the WANT
is a standing request, answered when the custodian holds the cell, with no promise timer; after
`--sample-retry` (2 s) an unanswered sample is declared to another link and the first is parked.
A sample that no link can serve (no link custodies its column, or every one that does was parked)
is counted as unreachable and dropped from the sampler's interest (`unreachable`, the
application's decision in the document), and the sampler then confirms nothing for that block: the
`samples` line counts a sampler as complete only once every cell it declared arrived, so its
`missing` is the samplers that did not confirm, and the time over the samples that arrived follows
on the same line. The `sampling` line gives the samplers, the samples declared and unreachable,
and the custodians' serving load towards samplers. Indications on the 60-node cell (12 samplers),
one seed, recorded before 2026-10-23, when the `samples` line still left out the samples given up
(the table's "samples missing" counts samples, and its times are over the samples that arrived):

| cell | custodians p50 / p99 | samples p50 / p99 | samples missing | unreachable | chunks to samplers per custodian |
|---|---|---|---|---|---|
| 1 Gbps proposer | 334 / 433 ms | 277 / 440 ms | 0 of 167 | 25 of 192 | median 3, max 6 |
| the same, 30 % withholding custodians (`--fault wh30`) | 336 ms / never (one withholder whose three pushers all withhold) | 2 090 / 4 016 ms | 0 of 149 | 43 of 192 | median 2, max 6 |
| 500 nodes, degree 70, 100 samplers, 1 Gbps proposer, slot window | 1 014 / 1 216 ms | 918 / 1 146 ms | 0 of 1 553 | 47 of 1 600 | median 3, max 11 |

The first two rows are with the window in bytes (`protocol-v2.md` §4.11); with v0.3's slot window
they gave 752 / 910 and 750 / 828 ms, and 809 / 1 482 and 798 / 4 197 ms. Under withholders a
sampler's completion is the retry: with eight samples each and 30 % of custodians withholding,
nearly every sampler declares at least one sample to a withholder first and waits the 2 s before
declaring it again, so the median of sampler completion is the retry delay, not the custodians'
speed; the 4 s tail is two retries.

A sample completes when its custodian receives that cell, so samples finish a little before the
custodians' columns do. Under withholders the retry path shows: a sample declared to a custodian
that never answers is declared again after 2 s to another link, and twice when the second
withholds too (the 4 s tail), and a sample whose every custodian link was parked becomes
unreachable, which is the rise from 25 to 43. The unreachable samples of the honest cells are the
connection graph's: a column is custodied by none of a sampler's peers 14 % of the time at degree
30, and about 3 % at degree 70 when a fifth of those peers are samplers themselves.

Counted the current way (2026-10-23; 60 nodes, degree 30, 12 samplers, a 1 Gbps proposer with
`--net bld`, seed 7), a sampler with a sample given up confirms nothing, and at degree 30 that is
most of them. In the honest cell 7, 7 and 5 of the 12 samplers do not confirm in its three blocks
(35 of 288 samples unreachable; with 14 % of columns custodied by none of a sampler's peers,
1 − 0.86⁸ ≈ 70 % of samplers would hold at least one such sample), and under 30 % withholders 8, 8
and 7 (63 unreachable). With half the columns withheld and no supernodes (`--withhold 64`, two
blocks), 12 and 11 of the 12 do not confirm (105 of 192 samples unreachable), where the line had
read 200 ms at the median and nobody missing. The runs' event digests are those of the earlier
report: only the counting changed. What a sampler does with a sample no link can serve, a verdict
of unavailable or another round through other peers, the document leaves to the application
(§4.10).

**A sampler's reach** (`protocol-v2.md` `[D12]`: the coverage floor of §1.3, routed sample requests
and LiteDAS's two phases in §4.10). `--sample-cover T` builds the floor with the graph: each sampler
adds sampling-only links, the custodian covering the most columns still short first, until every
column has T custodians among its links, counted by distinct links, a node of high custody (more
than `--cgc` columns, the proposer included) counting for at most `--cover-high` (1) of them; its
draws are its own, after the meshes, so that the graph and the meshes are those of a run without
it, and the proposer counts where it already is a link and is never added (proposers rotate).
`--route on|off` (on) lets a sample that no link serves go as a routed request to a link with duty
`FORWARD`, which passes it one step on (§4.5), `--route-hops` (1) steps at most; `--sample-retry2`
(0.5 s), `--sample-outstanding` (4) and `--forward-limit` (none) are the second phase's wait per
peer, its asks in flight per block and the forwarders' limit. A sampler asks a peer for at most one
sample of a block, and a peer of high custody only in the second phase. The `reach` line gives the
floor's links per sampler, by which ask each sample first arrived, the asks per sample, the routed
requests passed on per node, the most samples of a block one peer was asked for by one sampler,
and how many were asked of the block's source. A sample nobody delivered is missing (the document
no longer gives one up): it is reported on a line of its own, not as a completion violation, which
stays the custodians' invariant.

Known answers (2026-10-23; 60 nodes, degree 30, 12 samplers, `--net bld`, seed 7): without samplers
the custody and row cells' digests are those from before the change, and both `check.py` runs pass.
With the samplers, no peer is asked for more than one of a sampler's samples in a block, in every
cell. With neither the floor nor routed requests, 9, 9 and 8 of the 12 do not confirm: the 35
samples that no link serves, and those whose only serving links had been asked for another of the
sampler's samples (when a peer could be asked again, 7, 7 and 5).
With routed requests alone every sampler confirms (71 samples routed, the source asked for none);
with the floor alone (two covers) 7 of the 36 do not confirm, since seven of the 128 columns are
custodied by nobody but the proposer at 60 nodes and the floor never adds it; with both every
sampler confirms (14 routed, the source asked for none, the samples' p50 and p99 292 and 376 ms
against the custodians' 339 and 437). With half the columns withheld, 12 and 11 of 12 do not confirm
under every combination, and the hunt is bounded by one sample per peer: 1.3 to 1.7 asks per sample
without routed requests, 3.0 with them and 5.2 with the floor as well. With `--route-hops 2` one
request took a second step, and its sample came at 468 ms where it had waited for the second phase.
At 500 nodes (graph only, seeds 7 to 16, high custody counted in full, the earlier rule) the floor
of one cover added 0 / 0 / 2 / 3 / 5 links per sampler (min, p10, median, p90, max; mean 1.8) at
degree 70 and 0 / 12 / 13 / 15 / 18 (mean 13.0) at degree 16, as `sampler_graph.py a` counts with
its own greedy cover (0 / 0 / 2 / 3 / 6 and 0 / 12 / 13 / 15 / 17). Before one sample per peer, the proposer was asked
for 28 of the 288 samples in the honest cell with both, up to 5 of one sampler's 8. With 30 %
withholders, both (one cover) and seed 8, every sample arrived, at a median of 2.7 to 3.7 s and a 99th
percentile up to 7.7 s (2.2 to 2.7 s and 4.9 s when a peer could be asked again).

The document's graph figures for `[D12]` (§1.3, §4.10, the `SAMPLE_COVER` and `ROUTE_FLOOR` rows of
§6.3, §8) come from two scripts that build the toy's networks and run no events, 500 nodes, a fifth
samplers, seeds 7 to 16: `python3 sampler_graph.py a|c|e` (the floor's links, routed requests' hops
under the routing rules, rows as a second axis; 2 to 3 minutes each) and `python3 sampler_match.py
custody 70|16` (eight and sixteen samples matched to distinct serving links under each floor, 400
draws per sampler; about a minute). Both print markdown tables.

The matrix (2026-10-23, on that day's draft, with `[D12]` as proposed then; 60 nodes, degree 30, 12
samplers, `--net bld`, seeds 7 to 9, three blocks each, two with half withheld; the seed-7 cells'
digests equal the local runs'): samplers that did not confirm, of the sampler-blocks; the samples'
p50 and p99 over the blocks (inf where most did not confirm); the custodians'; samples routed per
run; asks per sample. "Off" is neither the floor nor routed requests, A the floor of two covers (the
draft then proposed one; two were decided later), C routed requests, one step.

| network | off | A | C | A+C | samples p50 / p99, C and A+C | custodians p50 / p99 | routed, C / A+C | asks per sample, off / A / C / A+C |
|---|---|---|---|---|---|---|---|---|
| honest | 76 of 108 | 24 of 108 | 0 | 0 | 321 / 411 and 292 / 406 ms | 327–335 / 439–466 ms | 73 / 18 | 1.00 throughout |
| 30 % withholders (`wh30`) | 99 of 108 | 61 of 108 | 0 | 0 | 2 749 / 4 732 and 2 682 / 4 539 ms | 353–370 / 1 035–1 208 ms, 2 or 3 missing | 119 / 50 | 1.20 / 1.30 / 1.63 / 1.54 |
| half withheld (`--withhold 64`) | 71 of 72 | 70 of 72 | 70 of 72 | 70 of 72 | – | never (276 missing) | 25 / 7 | 1.36 / 1.72 / 3.01 / 5.28 |

With routed requests every sampler confirmed in every honest and withholding block, and the block's
source was asked for no sample. Without them, one sample per peer leaves a sample nowhere to go once
its serving links were asked for others or withhold: under 30 % withholders 99 and 61 of 108 did not
confirm. Under withholders the samplers' median is the first phase's 2 s wait (`--sample-retry`):
with eight samples and 30 % withholders, nearly every sampler declares one sample to a withholder
first (all eight escape with probability 0.7⁸ ≈ 6 %). With half withheld, the one or two sampler
blocks that confirm are those whose eight samples all fell in the published half (2⁻⁸ per sampler
and block): availability is never confirmed by reaching more custodians. The floor's 24 and 61
honest and withholding misses at 60 nodes are the columns only the proposer custodies (above).

The matrix at 500 nodes (2026-10-26, on the draft of 2026-10-23): degree 70 and 16, a fifth of the
nodes sampling, `--setting custody --net bld --msgs 2`, seeds 7 to 16, honest and 30 % withholders.
Off is set against A+C with the floor of one cover (then the draft's proposal; two were decided
later) and of two. The batch's first cell, the 60-node `r-honest-AC-s7`, printed its digest again.
Every A+C cell's floor links equal those of a build of its graph alone (2 and 8 added per sampler on
top of 70, 13 and 29 on top of 16, as `protocol-v2.md` §6.3 counts).

The table gives, over 2 000 sampler-blocks per row:
- short: samplers that did not confirm;
- the samples' p50 and p99 at one cover and at two, medians over the 20 blocks;
- the custodians' p50 and p99 over the three arms, and their missing summed over the blocks (off,
  one, two);
- samples routed per run;
- asks per sample;
- the data copies per node.

| network | short: off / one / two | samples, one; two | custodians p50 / p99; missing | routed, one / two | asks per sample, off / one / two | data copies, off / one / two |
|---|---|---|---|---|---|---|
| degree 70, honest | 461 / 0 / 0 | 482 / 648; 486 / 660 ms | 520–522 / 666–678 ms; none | 16 / 2 | 1.00 throughout | 1.34 / 1.35 / 1.35 |
| degree 70, `wh30` | 1 103 / 0 / 0 | 2 604 / 5 638; 2 528 / 5 054 ms | 939–946 / 1 390–1 419 ms; 26 / 26 / 26 | 136 / 79 | 1.34 / 1.50 / 1.47 | 1.23 / 1.24 / 1.25 |
| degree 16, honest | 1 994 / 0 / 0 | 520 / 2 197; 502 / 679 ms | 544–546 / 694–702 ms; none | 140 / 7 | 1.00 throughout | 1.25 / 1.35 / 1.35 |
| degree 16, `wh30` | 1 999 / 7 / 0 | 2 856 / 6 116; 2 667 / 6 004 ms | 945–954 / 1 386–1 412 ms; 39 / 43 / 49 | 470 / 179 | 1.08 / 1.65 / 1.54 | 1.12 / 1.24 / 1.24 |

**Two covers.** Every sampler confirmed in every block, and the block's source was asked for no
sample (off asked it for 6 to 16 a run).

**One cover.**
- At 70 links it did as well as two.
- At 16 it cost the tail. Honest, the samples' p99 rose to 2.2 s against 0.7 s, above 2 s in 16 of
  the 20 blocks: a few samples a block are asked again after the first phase's 2 s wait. The most
  asks of one sample is 2 or 3 in every run, against 1 or 2 with two covers. A trace of seed 7
  names them. In all seven slow samples, the sampler's only serving link was taken by another of
  its samples. The sample went routed through a forwarding link drawn at random, which had no link
  serving the column and dropped it silently. The second routed request delivered it after the
  wait. 7 of 132 routed first asks found no route; no custodian was slow.
- Under withholders, at 16 links, 7 sampler-blocks in five of the ten seeds did not confirm (10
  samples never delivered, one sample asked up to 19 times). In seed 12's trace, the two samples
  never delivered belong to the two samplers of 100 with the most withholders among their links
  (53 % and 52 %, median 30 %). Their hunts ended with no fresh link left.

**The custodians** were not slowed: within 30 ms of off. Their missing at degree 16 under
withholders differ only in two seeds, in opposite directions:
- seed 7: 6 off, 29 with two covers;
- seed 15: 27 off, 14 with two covers.

**The data copies** rise by 0.10 at 16 links and 0.01 at 70. These are the samples that now
arrive. Each node's bytes count against its own interest, and a sampler's interest is its eight
sampled cells. So each sample that arrives adds 1/8 to its sampler's ratio, and samplers are a fifth
of the nodes. At 16 links, (1 600 − 806) / 1 600 × 1/5 = 0.099. The custodians' own data barely
move.

**Under withholders,** the samplers' median is again the first phase's 2 s wait.

`--setting rows` is the RowDAS row of `protocol-v2.md` §6.2 on top of custody (EIP-8371 as the
pinned draft reads): a second object type, the row, with N = 128 cells and K = 64; every cell is
index b of column c and index c of row b, so one arrival fills both groups (R4); each node has one
designated row subnet from its id (`--row-subnets`, 32 by default so that every subnet is active
with 32 blobs; the EIP says 128), blob rows map to subnets by a draw per block, members keep
`--floor` fellow members as peers and a gossipsub mesh per subnet carries holdings and offers but no
pushes (`EAGER` off); members complete at 64 cells and claim nothing; `--reconstructors` percent of
nodes custody 64 columns and decode their subnet's row at K (phase 1); any member decodes at
`--phase3` seconds from the block plus a jitter if the row is still short in the subnet's view
(phase 3); rebuilt cells are pushed to the custodians of their columns and offered to row members; a
peer's claim defers an armed duty by `--defer-window`, during which one probe ask verifies it (R5);
row offers are asked only after `--row-delay` (R7); a peer serves at most 64 cells of a row (R6);
and each member keeps `--repair-floor` (1) custodian peers for every column it does not custody
(`protocol-v2.md` §4.6), drawn after the meshes from a generator of its own, so that the graph and
the meshes are the same with and without them and these links are in no mesh; 0 leaves a member the
links the graph gives it. `--withhold N` makes the proposer keep the last N columns, so that only
reconstruction can fill them, and `--fault claimNN` makes that share of the nodes claim every cell
of their row at the first one and never answer. The report adds the cross-fill check (cells not
mirrored in their other group: must be none) and the rows line: decodes at K and later, duties
deferred, claims verified by the probe, re-arms with the claimant penalised, and the links the
repair floor added. `--col-announce` and `--row-announce` set the columns' and the rows'
`ANNOUNCE_EXTRA` (`protocol-v2.md` `[D5]`; `ALL_JOINED`, the default, `SAMPLE` or `NONE`). A cell is
published under its column, and its message id names that group, so the heartbeat's gossip offers
cells under their columns: the rows' `SAMPLE` runs as `NONE` (the same events in the rows cell at
seed 7). Indications at 60 nodes (degree 30, a 1 Gbps proposer, 6 reconstructors), one seed:

| cell | custodians p50 / p99 | rows at 64 p50 / p99 | decodes at K / later | deferred / verified / re-armed | completion |
|---|---|---|---|---|---|
| honest, 32 subnets | 620 / 1 085 ms | 1 098 / 1 186 ms | 12 / 0 | 25 / 25 / 0 | all |
| half the columns withheld, 16 subnets | 2 408 / 2 740 ms | 1 363 / 1 571 ms | 24 / 71 | 141 / 141 / 0 | all, through the rows, on all thirteen seeds from 7 to 19 (below) |
| the same, 32 subnets | never | 1 223 / 1 260 ms | 12 / 63 | 43 / 43 / 0 | 3 subnets have no member, their 3 rows are never rebuilt, every withheld column stays 3 cells short |
| half withheld, 16 subnets, 20 % liars | 2 957 / 3 873 ms | 1 776 ms / never | 24 / 90 | 137 / 82 / 55 | all but 4 custody groups; the rows of 2 members short of 64 in the first block, of 1 in the second |
| 500 nodes, degree 70, half withheld, 32 subnets, 50 reconstructors | 2 360 / 2 504 ms | 1 219 / 1 302 ms | 100 / 215 | 680 / 680 / 0 | all, through the rows; copies 2.28 of own custody, control 0.72; the proposer served 4.7 copies of the block |

These are the numbers with the window in bytes (`protocol-v2.md` §4.11) and the repair floor (§4.6).
Without the floor the seed-7 cells gave 632 / 1 095 ms (honest), 2 438 / 2 750 ms (withheld, 16
subnets), 3 101 / 3 315 ms (liars) and 2 368 / 2 505 ms at 500 nodes, with the same completions.
With v0.3's slot window and no floor the same 60-node cells gave: honest 848 / 2 037 ms with 37
later decodes and 1 re-arm; withheld with 16 subnets 2 735 / 3 104 ms with 84 later decodes and 8
re-arms against honest claimants; the liar cell 4 541 ms / never, with a second block that lost
three rows. The slot window held a reconstructor's answers behind its burst of rebuilt cells (the
re-arms) and slowed the column path enough that members' subnet views were still short at the third
phase (the later decodes in the honest cell); with bytes neither happens, and in the liar cell both
blocks complete but for the few groups the table lists, because the honest members reach 64 before the liars' broken promises park every
peer they have.

At 500 nodes, with about fifteen members per subnet, every custodian of a withheld column completes
through the rows in 2.4 s at the median and 2.5 s at the tail (2.5 and 3.0 under the slot window),
every one of the 680 claims is verified and none re-armed, and the rows themselves are at 64 in
1.2 s; the cost shows in control (0.72 copies of a node's custody, the rows' holdings and offers),
in the proposer's serving load (4.7 copies of the block, most of it answers to pulls, since it is
the one holder its custodian links can ask for the published half) and in the 215 later decodes
for 64 rows, where members of one subnet decode in parallel because the 200 ms jitter is shorter
than a claim's trip plus the probe; the duty spread is 3.8, a reconstructor uploading six times
its interest. The probe's promise is the deferral window (1 s) and not v0.3's 400 ms because
under the slot window a reconstructor's answer to a probe left 450 ms after it was decided, behind
its burst of rebuilt cells. In the liar cell the probe parks the liars it meets (44 of 50 parked
claimants in one block under the slot window) and the re-arms decode the rows the liars claimed;
the rows still missing are the liars' own. The empty subnets of the 32-subnet cell are the EIP's
team-size floor seen at toy scale: 59 members over 32 subnets leave some with none.

**The probe of a claim** (R5, since 2026-11-15; `protocol-v2.md` §4.6). The claimant passes only on
its own copy; the probe's WANT carries `probe`, which the toy's binding carries beside the index
(`wire.FlaggedWant`) and charges no bytes, as it does `standing` and `hops`; and the probed index is
drawn at random among those lacked. The toy draws that index from a generator of its own, seeded by
the run's seed and the node (`probe-index/<seed>/<node>` in `node.py`), so that the draw moves no
other; the claimant is then drawn from the node's own generator, as before. Over five cells at 60
nodes, degree 30, three blocks and seeds 7 to 9, with `--send-buffer 0` (`--setting rows`; `--fault claim20`; with
`--row-subnets 16 --withhold 64`; the same with `--fault hoard20` in place of the liars; and the
liars' withheld cell with `--supernodes 5`), no honest or hoarding claimant failed its probe (none
of 1 298 verdicts with the rules of 2026-11-16; before them, 3 of 1 289 failed with the claimant's
own copy alone), and liars passed 3, 1 and 61 times in the three liar cells, where any peer's copy
passed at least 57, 115 and 558 (measured before 2026-11-16). Figures in this section
measured before 2026-11-15 ran with the lowest index, without the mark and the kept WANT, and with any
peer's copy passing the claimant, unless they say otherwise.

The table's rows are seed 7. Over seeds 7 to 19 the withheld 16-subnet cell completes on every seed
with the repair floor, and without it (`--repair-floor 0`) leaves custodians short in five of the
thirteen runs, each for a missing link, traced cell by cell. In four (seeds 10, 12, 16 and 18), a
withheld column with two custodians missed one or two cells: the only member that rebuilt the row
was linked to neither custodian, and nothing else brings the cell, since members stop pulling a row
at 64 cells, which the published half gives them before the third phase, and the deferral on a
claim, which cancels a second decode once the first is verified, makes single rebuilders common. In
the fifth (seed 15), a subnet had two members, linked to each other and to no other member; each
gathered 63 cells of its two rows from the columns' custodians, one short, because neither was
linked to the only custodian of published column 24, so neither row was rebuilt and every custodian
of a withheld column stayed two cells short. EIP-8371 has a rebuilder give its cells to the column
subnets it is not in through gossipsub's fanout, which reaches connected peers only; the toy's
rebuilders push to the custodians among their links (`REPAIR_TO`), and the floor gives every member
one for each column, which serves the row's gathering as much as its repair. It adds 1 to 30 links
per run (2 to 8 in the honest cell), and on the eight seeds that complete either way it moves the
median by −54 to +34 ms, the tail by −65 to +129 ms and the copies by at most 0.07, within the
seeds' spread. With the floor, the run at seed 7 found a node that held every cell of a custody
column and never completed it: it had rebuilt the row that supplied the column's last cell, and
`decode_group` filled the column without checking its completion, which `protocol-v2.md` §4.6 now
does; without the floor the fix changes one event in one of the thirteen runs and no result.

`--supernodes PCT` (custody and rows) makes that share of the nodes custody all 128 columns, drawn
by a generator of their own so that the other draws stay those of a run without them, on the
datacenter link (`--supernode-link home` for the home one). A supernode keeps every row group,
filled from its columns, with interest declared on no link, and rebuilds a row still short
`--phase2` seconds (1) after the block plus up to `--phase2-jitter` (0.2): EIP-8371's second
phase, and under custody alone PeerDAS's reconstruction with a delay (`protocol-v2.md` §4.6). Under
rows it is also a row reconstructor of its own subnet. A row whose missing cells its column peers
hold waits once, `--defer-window`, before it is rebuilt (`known_across`). `--repair-budget on`
pushes each rebuilt cell to `R_NODE` custodians lacking it and offers it to the rest. The rows line
adds the second phase's decodes, and under custody alone a reconstruction line counts them.
Over seeds 7 to 19 at 60 nodes (degree 30, a 1 Gbps proposer, 6 row reconstructors where there are
rows), three supernodes, the medians over the seeds and the tail's worst seed:

| cell | supernodes | p50 | p99, median / worst | copies of own custody | second-phase decodes of 192 | completion |
|---|---|---|---|---|---|---|
| custody, honest | none | 344 ms | 459 / 512 ms | 2.14 | – | all |
| custody, honest | 3 | 334 ms | 459 / 508 ms | 3.10 | 0 on every seed | all |
| custody, half the columns withheld | none | never | – | – | – | 58 of 59 custodians short (seed 7) |
| custody, half withheld | 3 | 1 196 ms | 1 251 / 1 318 ms | 3.76 | 143 to 167 | all, every seed |
| the same, `--repair-budget on` | 3 | 1 215 ms | 1 304 / 1 400 ms | 3.71 | 149 (median) | all |
| rows, honest | none | 459 ms | 1 143 / 1 390 ms | 2.16 | – | all |
| rows, honest | 3 | 428 ms | 1 674 / 1 846 ms | 2.88 | 0 on every seed | all |
| rows, 16 subnets, half withheld | none | 2 442 ms | 2 709 / 2 816 ms | 2.36 | – | all |
| the same, `--repair-budget on` | none | 2 423 ms | 2 623 / 2 677 ms | 2.19 | – | all |
| rows, 16 subnets, half withheld | 3 | 1 200 ms | 1 756 / 1 922 ms | 3.33 | 131 to 153 | all |
| the same, `--repair-budget on` | 3 | 1 263 ms | 2 002 / 2 123 ms | 3.18 | 138 (median) | all |
| rows, 32 subnets, half withheld | none | never | – | – | – | 3 subnets without members (seed 7) |
| rows, 32 subnets, half withheld | 3 | 1 202 ms | 1 833 / 1 948 ms | 3.32 | 144 to 165 | all, every seed |
| the same, `--repair-budget on` | 3 | 1 257 ms | 2 041 / 2 188 ms | 3.15 | 150 (median) | all |

The no-supernode 16-subnet row is the repair floor's thirteen runs above, which the new code
reproduces event for event (every cell without supernodes keeps its digest at seed 7). The second
phase recovers what nothing else could and halves the withheld cells' time; in the honest cells no
supernode rebuilds a row, which `known_across` is for: before it, three supernodes on home links,
still receiving their 128 columns at the second phase's timer, rebuilt 186 rows of the honest row
cell at seed 7 and took its tail from 1.09 to 1.49 s, and with it, still on home links, they rebuild
139 rows of the honest custody cell at seed 7 and hold its median at 584 ms, since a supernode on a
home downlink is still receiving its columns at the timer and after the one wait (the cell's tail is
1.8 s); hence the datacenter link by default. The cost is bytes, in every cell with supernodes: 0.7
to 1.0 copies more per node where the cell completes without them, mostly duplicate pushes (87 000
against 22 000 in the honest custody cell at the median), and in the honest row cell half a second
of tail. The duplicates are the fast class's: a supernode on a datacenter link is in card 17's fast
class and pushes each chunk it receives to six peers (`R_FAST`), into columns of about ten
custodians at this scale. With the fast class off (`--without 17`, which leaves these cells without
supernodes as they were, to the millisecond and the count at seeds 7 to 9), over seeds 7 to 19 and
with supernodes, the honest custody cell is at 365 / 532 ms and 1.93 copies (334 / 459 ms and 3.10
with the fast class, 344 / 459 ms and 2.14 without supernodes), the honest row cell at 467 / 1 133
ms and 2.22 copies (428 / 1 674 ms and 2.88; 459 / 1 143 ms and 2.16), the withheld custody cell at
1 198 / 1 247 ms and 2.60 copies (1 196 / 1 251 ms and 3.76), and the withheld row cells at 1 203 /
1 642 ms and 2.76 copies with 16 subnets and 1 192 / 1 685 ms and 2.66 with 32 (1 200 / 1 756 and
3.33; 1 202 / 1 833 and 3.32). The repair budget pays where members on home links rebuild and loses
tail where datacenter supernodes do; with the fast class off it saves 0.41 copies in the 16-subnet
cell for 0.1 s at seeds 7 to 9 (1 305 / 1 728 ms, 2.37 copies; `protocol-v2.md` §4.6, §6.3).

`--promise` sets v0.3's promise (0.4 s). The asks line now matches an answer to an ask on either
axis: a row ask is answered with a column chunk, and the earlier report counted every row ask as
never delivered. Two lines were added to find where the row cells' parks came from: asks the asked
node left unanswered, by reason (none in the honest and withheld row cells or the custody cell at
seed 7), and the broken promises, with how much later the asked node's answer came. In the honest
row cell at seeds 7 to 9 the 400 ms promise broke 3 321 to 4 204 times and parked 804 to 1 039
(peer, group) pairs; at seed 7, 3 522 of the 3 580 broken promises were column asks the asked node
answered later, 448 ms after the ask at the median and 824 ms at the 99th percentile, behind the
rows' pulls on its uplink. With `--promise 0.8` it broke 1 to 3 times and parked as many pairs, the
withheld 16-subnet cell parked none where it had parked 41 to 127, the medians moved by at most 3
ms, the copies not at all and the tails by at most 20 ms: the asker moves on after `IWANT_WINDOW`
either way, and the promise decides only whom it parks (`protocol-v2.md` §6.3, `PROMISE`, for later
study).

Whom rebuilt cells go to, explored on 2026-10-08. Supernodes keep every row, so a
rebuilder's push into a column reaches them too, and with several rebuilders the pushes cross in
flight: at 500 nodes (seed 7) 88 % of the rebuilt cells pushed in the withheld custody cell arrived
as duplicates, which is the whole of that cell's extra cost over the honest one (3.76 against 2.83
copies). `--repair-keepers offer` leaves the nodes that keep every row out of the pushes and offers
them the cells; `skip` leaves them out entirely; `--repair-push offer` offers every rebuilt cell
instead of pushing it, as a row's are (`--keeper-claims ignore` makes a supernode's second phase
ignore claims, kept for the measurement). Over seeds 7 to 19 at 60 nodes with three supernodes, the
medians, p50 / p99 and copies of own custody:

| cell | pushed (`protocol-v2.md`) | keepers offered | keepers skipped | all offered |
|---|---|---|---|---|
| custody, half withheld | 1 196 / 1 251 ms, 3.76 | 1 195 / 1 290 ms, 3.43 | 1 199 / 2 309 ms, 3.38 | 1 264 / 1 386 ms, 3.04 |
| rows, 16 subnets, half withheld | 1 203 / 1 767 ms, 3.34 | 1 185 / 1 647 ms, 3.16 | 1 194 / 1 693 ms, 3.16 | 1 313 / 1 782 ms, 2.80 |
| rows, 32 subnets, half withheld | 1 208 / 1 811 ms, 3.34 | 1 201 / 1 718 ms, 3.17 | 1 204 / 1 910 ms, 3.16 | 1 304 / 1 756 ms, 2.70 |
| rows, honest | 428 / 1 674 ms, 2.88 | 433 / 1 705 ms, 2.87 | 417 / 1 654 ms, 2.87 | 436 / 1 674 ms, 2.81 |

The honest custody cell rebuilds nothing and is unchanged (334 / 459 ms, 3.10). Offering to the
keepers saves 0.17 to 0.33 copies at no cost in time; offering everything saves the most bytes and
costs 60 to 110 ms at the median; skipping the keepers saves as much as offering to them, but a
skipped supernode in the custody cell gets its missing cells only from its own rebuild, after it
has waited out a deferral on the claims it heard, which is the 2.3 s tail. None of these is in
`protocol-v2.md`; §4.6 keeps the push (options).

R5's verdict (`protocol-v2.md` §4.6, "The verdict, by what the node can see"). Draft 1 ended a
deferred duty when the probed cell arrived. When the explorations above stopped pushing to
supernodes, supernodes deferred on a claim that came in an acknowledgement, received the probed
cell and ended one cell short of a column. The rule now: a row member ends its duty on a verified
claim, as in draft 1, and a node that keeps the row on no link (a supernode's rows of other
subnets, every row under custody alone) goes by the cells it holds. A first version counted a
verified claim only from a peer that pushes the row to the node, and members decoded 31 rows per
run against draft 1's 9 with 16 subnets (38 against 16 with 32; the medians over seeds 7 to 19),
for no change in time or bytes: traced in three runs, the claimants were supernodes rebuilding in
the second phase, whose claims reach a member only in the acknowledgement of a column chunk. A
second version told a member by a non-empty suppression scope, and members decoded 9 (16 subnets)
and 20 (32 subnets) per run: with 32 subnets, members with no peer pushing the row to them counted
as keeping the row on no link. The rule now tells a member by the family it takes part in
(`wants_family`, its own subnet's row), and members decode 9 and 16, as in draft 1. With the
member check below, the row cells with supernodes (honest; withheld with 16 and with 32 subnets)
and the withheld custody cell with 20 % hoarders are event for event draft 1's on all 13 seeds,
the row cells with supernodes and hoarders on 48 of 52 seed-cells, and every cell without
supernodes is unchanged by the new wording; the liar cell with supernodes changes on six seeds,
its few short pairs with them.

The liar cell over seeds 7 to 19 (`--fault claim20`, 16 subnets, half withheld). Without
supernodes it leaves 797 to 1 058 (node, column) pairs short on five of the thirteen seeds, with and
without the rule: on seeds 9, 14, 15 and 17 a published column's custodians are all liars, which
never answer, and with exactly half the columns published a row needs every published one, so no
row reaches 64 cells anywhere; on seed 18 one subnet's members are all liars, so its rows are never
rebuilt. The seed-7 row of the first table is one of the eight seeds without such a failure (its few short
groups aside). With three
supernodes every custodian completes on every seed, and 1 to 7 (node, row) pairs stay short of 64
cells on twelve of the thirteen, with and without the rule; on seeds 7 and 8 the first of them is a
liar's own row, as in the first table (the others not checked). Its median is bimodal by seed,
near 1.4 s or near 2.1 s, and a seed changes
mode with small changes in the code, so the cell's median over seeds moves by half a second between
versions that differ in nothing the liars touch.

`--fault hoard<pct>` is the claimant the probe cannot catch: a node that rebuilds and claims as the
document says, pushes none of its rebuilt cells, drops a standing WANT for one, and answers an ask
for one only once per peer and group and only when it is the frame's one ask on that group, which is
what a probe looks like; it forwards what it receives. The hoarders line counts them by role, the
rows they rebuilt, and the asks for their rebuilt cells answered (the probes) and refused.
The member check (`protocol-v2.md` §4.6, decided 2026-10-09, on by default; `--member-check off`
removes it) ends a member's duty on its own subnet's row on a verified claim only if the row's cells
in the member's custody columns are held, the cells an honest claimant's repair brings it; otherwise
the member goes by the cells it holds and rebuilds. Over seeds 7 to 19 at 60 nodes, half the columns
withheld, medians (p50 / p99) where every seed completes:

| cell | hoarders | draft 1 | R5's second wording, no check | `protocol-v2.md` (the check, R5's wording fixed) |
|---|---|---|---|---|
| rows, 16 subnets, 3 supernodes | 20 % | 1 215 / 1 816 ms, all | 1 215 / 1 796 ms, all | 1 215 / 1 816 ms, all; draft 1's events on 12 of 13 seeds |
| | 50 % | short on seed 14 | short on seed 14 | short on seed 14 |
| rows, 32 subnets, 3 supernodes | 20 % | 1 207 / 1 836 ms, all | 1 216 / 1 822 ms, all | 1 207 / 1 836 ms, all; draft 1's events on every seed |
| | 50 % | short on seed 14 | short on seed 14 | short on seed 14 |
| rows, 16 subnets, no supernodes | 20 % | short on every seed (371 to 810 pairs) | the same | short on seeds 14, 17, 18; 3 254 / 3 438 ms, 2.33 copies |
| | 50 % | short on every seed | the same | short on 10 of 13 seeds |
| custody, 3 supernodes | 20 % | 1 216 / 1 271 ms, all | the same | the same (no row subnets) |
| | 50 % | 1 255 / 1 327 ms, all | the same | the same |

Without the fault the check never fires and changes no event in any of the five cells run (rows
honest, with and without supernodes; withheld with 16 and 32 subnets; withheld with 16 and none),
and with it off, under R5's second wording, the toy reproduced the runs before the check event for
event (three cells over the 13 seeds). The table's last column is the current text; fixing R5's
wording changed no cell without supernodes, so the figures below hold for it. Where an honest
supernode keeps a row, its second phase repairs what a hoarder withholds, under draft 1 as under
the current rule: in three traced runs no supernode ended its duty on a
verified claim, and the check never fired there. Without supernodes a hoarder's verified claim ends
the duties of its subnet's honest members and nobody else keeps the row: at seed 7 the four short
rows were all of subnet 13, rebuilt only by a hoarding row reconstructor to which 15 duties had
deferred. The check rescues every seed on which each subnet has an honest member and none on which
one has none: seeds 14, 17 and 18 at 20 % (one subnet each), and at 50 % the ten seeds with one to
four such subnets; on seed 14 at 50 % the three supernodes are hoarders too. The rescued runs are
slower (3.25 s against 2.44 s without hoarders, the rebuilds coming at the third phase plus a
deferral) and no dearer (2.33 copies against 2.36), since hoarders repair nothing. In the liar cell
without supernodes it fires 1 to 3 times per run on 5 of 13 seeds, each time (traced at seeds 8, 11
and 12) on a liar's claim that passed the probe because another peer brought the probed cell
(measured when such a copy also passed the claimant, before 2026-11-15): the member rebuilds
instead of trusting it. The check moved the few pairs short in that cell on those
three seeds by one or two (4 to 5, 0 to 1, 3 to 5), and in the three traces every short pair, with
and without the check, is a liar's own row, which the toy's liars never rebuild; in the liar cell
with supernodes it never fires.

`--fault hoardm<pct>` is a hoarder that pushes each member of the row's subnet among its peers the
row's cells of that member's custody columns and nobody else anything, so that every member check
passes and the columns no member keeps stay short. `--repair-sample S1:L1,S2:L2` (`protocol-v2.md`
§4.6, "Sampling the repair", an option) samples the repair after a verified claim and a passed
member check: `S1` cells of the row the member lacks, each asked of a custodian of its column that
is not a claimant, judged `--sample-wait` (0.5 s) later, passing with at most `L1` missing, else
extended to `S2` and judged again, and rebuilt with more than `L2` missing. The repair sample line
counts the cells asked and the verdicts by step. Over seeds 7 to 19 at 60 nodes, half the columns
withheld, 16 subnets, the member check on throughout, seeds short / p50 / p99 (where every seed
completes) / sample cells asked per run (median):

| cell | supernodes | member check alone | `3:1,6:2` | `4:0,8:1` | `6:0,12:1` |
|---|---|---|---|---|---|
| no fault | none | 0 / 2 442 / 2 709 ms / – | 0 / 2 436 / 2 726 / 399 | 0 / 2 437 / 2 729 / 532 | 0 / 2 434 / 2 725 / 786 |
| | 3 | 0 / 1 200 / 1 756 / – | 0 / 1 202 / 1 794 / 155 | 0 / 1 199 / 1 744 / 199 | 0 / 1 203 / 1 793 / 262 |
| hoard20 | none | 3 / 3 254 / 3 438 / – | 3 / 3 228 / 3 443 / 351 | 3 / 3 224 / 3 412 / 472 | 3 / 3 239 / 3 433 / 726 |
| | 3 | 0 / 1 215 / 1 816 / – | 0 / 1 223 / 1 760 / 163 | 0 / 1 206 / 1 803 / 208 | 0 / 1 217 / 1 833 / 259 |
| hoardm20 | none | 13 / – | 5 / 4 231 / 4 395 / 441 | 3 / 4 184 / 4 326 / 576 | 3 / 4 198 / 4 370 / 864 |
| | 3 | 0 / 1 211 / 1 809 / – | 0 / 1 223 / 1 891 / 179 | 0 / 1 214 / 1 802 / 224 | 0 / 1 217 / 1 778 / 331 |
| claim20 | none | 13 (5 large) / – | 12 / – / 258 | 12 / – / 456 | 12 / – / 690 |
| | 3 | 12 / – / – | 12 / – / 212 | 11 / – / 382 | 12 / – / 579 |

The member check alone reproduces the runs before the sample event for event in the six cells they
share. No sample failed without a fault in any form; the copies moved by at most 0.02. Against
`hoardm20` without supernodes the strict forms leave short only seeds 14, 17 and 18, where a subnet
has no honest member, and in the run traced at seed 7 (`4:0,8:1`) all 14 failed samples were on
hoarders' claims and all 112 verdicts on honest claimants passed; `3:1,6:2` passes partial repairs
(at seed 7 the one honest member of subnet 13 got 4 of 6 cells, which the hoarding members' own
pushes had brought into some columns). With `hoard20` the member check catches the claimant before
the sample is asked. In the liar cells a sample cell asked of a liar, which answers no ask, is
lost: at `4:0,8:1` 18 of 41 verdicts on honest claimants failed at seed 7, and 46 of 48 at seed 8 with supernodes, where a liar is a supernode and
custodian of every column; members rebuilt 21 to 26 more rows per run in the strict forms.

`--repair-reask on` (`REPAIR_REASK`) re-asks each sample cell still missing when a step is judged of
another custodian of its column, with the extension, and at the last step in one more wait; the
repair sample line adds the re-asks. Over the same seeds and cells, with re-ask (failed samples per
run, median, and member decodes per run):

| cell | supernodes | `3:1,6:2` | `4:0,8:1` | `6:0,12:1` |
|---|---|---|---|---|
| claim20 | none | 1 → 0; 79 → 76 | 15 → 0; 101 → 74 | 20 → 0; 101 → 79 |
| | 3 | 3 → 0; 47 → 43 | 17 → 0; 67 → 46 | 27 → 0; 71 → 47 |

With the member check alone the liar cells decode 80 and 45 rows per run. Where no sample cell was
lost (no fault; `hoard20`, which the member check catches first) re-ask changes no event. Against
`hoardm20` without supernodes `4:0,8:1` and `6:0,12:1` with re-ask leave short the same three seeds
(14, 17, 18), and the rescued blocks complete at 4 714 / 4 876 ms and 4 688 / 4 915 ms (p50 / p99),
about 0.5 s later than without re-ask, the one more wait; `3:1,6:2` is short on 4 seeds. In the
liar cells completion is as without the sample; their medians are bimodal by seed and not compared.

At 500 nodes (degree 70, 32 subnets, half the columns withheld, seeds 7, 8 and 9, 47 to 105
minutes a run), the member check alone against `4:0,8:1` with
re-ask, p50 / p99 ms and copies per seed:

| cell | supernodes | member check alone | `4:0,8:1`, re-ask |
|---|---|---|---|
| no fault | none | 2 360 / 2 504, 2.28; 2 312 / 2 488, 2.28; 2 309 / 2 484, 2.29 | 2 348 / 2 513, 2.30; 2 316 / 2 493, 2.28; 2 332 / 2 510, 2.30 |
| | 25 | 1 178 / 2 211, 3.62; 1 178 / 2 251, 3.63; 1 170 / 2 415, 3.66 | 1 179 / 2 235, 3.62; 1 173 / 2 292, 3.65; 1 170 / 2 440, 3.66 |
| hoardm20 | none | 2 371 / 2 521, 2.24; 2 388 / 2 609, 2.25; 2 354 / 2 514, 2.25 | 4 650 / 4 894, 2.26; 2 410 / 2 583, 2.25; 2 389 / 2 578, 2.27 |

Every run completed. The member check fired in none, and no sample failed without the fault; the
sample asked 2 687 to 2 788 cells per run without supernodes and 172 to 258 with them. At seed 7
with the targeted hoarder, 9 samples failed, all on subnet 23's row of the second block, and its
members rebuilt it at 19.5 s. In a diagnostic trace of that run every late node's last custody
cell was of that row, and the block's last custody cells came at 19.65 s at the median; in the
trace of the run with the member check alone they came at 17.37 s, the late nodes' last cells of
several rows, so that row had been rebuilt earlier there (the runs diverge from the first block).

**A custodian's alarm** (`--alarm-wait S`, an option proposed on 2026-10-28; off by default,
which changes no event).
- **The custodian.** An honest custodian that, `S` seconds after `known_at` (plus up to
  `--alarm-jitter`), still lacks a cell of its custody columns that no peer's holding shows sends a
  standing WANT for it. The WANT names the row's group at the column's index, and goes to a member
  of the row's subnet among its links. Every `--alarm-next` seconds it asks another member, up to
  `--alarm-max`.
- **The member.** A member that deferred on a claim its probe verified asks that claimant for the
  index, once, as the probe is asked. If that promise breaks, it penalises the claimant and rebuilds.
  Since 2026-11-17 the promise starts at the ask's write, as the probe's does. A claimant that cannot
  be asked (its connection closed, or a full queue refuses the ask), or whose connection closes
  before the ask is written or before the promise ends, is not judged, and the member rebuilds if
  the cell is still missing. The
  figures below were measured before.
- Faulty nodes neither alarm nor act on one (`node.py`, `_alarm`).

**`--fault hoardcol<pct>`**, with `--rebuilt-seen on`, is a hoarder that repairs every withheld
column of its row but one, the document's `push_rebuilt` for the rest.
- The hidden column is, per subnet, the highest withheld column no honest member custodies. When
  a member probed the lowest index it lacked, the hidden one was never a probe, and the figures
  below were measured so. Since the probed index is drawn at random (2026-11-15), a member can probe
  the hidden cell, and the hoarder, which serves it to nobody, then fails the probe; not measured.
- The hoarder serves the hidden cell to nobody.
- It passes the member check and the repair sample's one lost cell.
- The report gives the fault's known answer per block: the custodians of the hidden columns of the
  rows no honest node rebuilt, the rebuilders aside. With the alarm off, that is the block's
  `missing`.

At 60 nodes (degree 20, 4 subnets, half the columns withheld, the repair sample with re-ask), the
fault bites only where a subnet's row reconstructors are hoarders alone (`seed 22`; at seeds 9 and 11
every row was rebuilt by an honest node).
- **Seed 22, alarm off:** 8 and 5 rows were not rebuilt by an honest node. 5 custodians are short in
  each block, as predicted.
- **Alarm at 3.5 s:** none is short, and the p99 is 4.90 and 4.92 s.
  - 42 alarms went from 3 custodians for 42 cells, against a bound of 126. 27 were kept by honest
    members as standing asks, and 15 were refused by hoarders.
  - There were 26 asks of a claimant (at most the 27 kept), all broken, so 26 members rebuilt their
    row: about two per row.
- Without a fault, under `hoardm20` with the member check alone, and under `claim20`, no alarm was
  sent at seed 11.

**`--wire standalone`** (with `--doc v2`) charges the links the standalone binding's bytes
(`protocol-v2-bindings.md` §1) in place of v0.3's wire, which stays the default and the recordings'.
It is a model of bytes: what reaches the receiver, and when, follows from those bytes, but an entry
is still delivered as one unit, as on v0.3's wire.
- *Each message is a frame of its own:* a uvarint length, a kind byte and its SSZ, sized before
  compression. The payload's chunk is `protocol.md`'s `Chunk`; a cell is a `CellChunk`.
- *One WANT per ask:* several asks of one group to one peer are charged a frame each, where one
  bitmap could carry them, so the asks' bytes are an upper bound.
- *An entry is delivered as one unit:* `on_frame` sees the entry's messages together, so the IHAVE
  limits (`protocol-v2.md` §4.3) count entries, not each offer's frame. Only the `ihave-limits` cell
  sets them.
- *A cell carries the block's header* (every blob's commitment) with the first eager push of its
  group on a link: an unsolicited cell, once per group and connection. The default wire charges none.
  The header's bytes are an upper bound: consensus's partial columns also skip it for a peer that
  has already sent a message of the block, which the toy does not.
- *The window's chunk size follows the wire* (`wire_size(p, entry)`), a first push's header
  included. "copies" keeps its denominators, so a cell's copies compare bytes on both wires.
- *Measured* (2026-11-17; `check.py`'s 15 cells under `--doc v2`, and two 60-node custody cells, one
  with a fifth of the nodes sampling; seed 7, one run each). The same numbers, to the byte, after the
  window began counting the header: in the custody cell the window sized 5 649 writes with a header
  and never refused one, so its size changed no event.
  - control bytes −30 to −36 %: no topic in an offer, no protobuf tags, a few bytes a relation
    message;
  - data within ±0.8 %;
  - all bytes −1.5 to −3.0 % in the 15 cells and −4.2 % in both custody cells;
  - the warm medians within 11 ms and the 99th percentiles within 28 ms, either way, one seed each.
  - In the custody cells data moved by +0.0 and −0.7 %. At 32 blobs one header (1 880 bytes) costs
    what about 13 cells save (143 bytes each), and the header goes once per group and link
    (`protocol-v2.md` §2). This is a balance of magnitudes at one seed, with the two wires running
    different events, not a measurement of either. Per block instead of per group, as consensus's
    partial columns allow, is for later study.

`--answers-first` sets the writer's order (`protocol-v2.md` §4.12). The default sends a source's
own chunks first, past its offers and answers, by rarity, and `on` adds the option of answers
before pushes. `v03` is v0.3's order, rarest-first up to the first control-only entry. The other
values are forms checked against it on 2026-10-07, kept so that the check can be repeated
(`node.py`, `_writer_variants`): `oldest` sends the oldest answer first, before a source's own
chunks too; `line` does that and puts the answer's writer ahead of the window's line; `others`,
`fresh`, `late` and `othersans` protect a source's own chunks in weaker ways. `--source-offers off`
drops the source's offers and `late` queues them after the pushes of every group it published at
the same instant. Both act only on offers `publish` itself makes, so since v0.9's rule moved the offers
to the acknowledgement they change nothing; their columns are from before it. The table gives each form's change against v0.3's order, at the median and the
99th percentile in ms, the mean over seeds 7, 8 and 9, paired by seed, at 60 nodes:

| cell | own chunks first (default) | and answers first (`on`) | oldest answer first (`oldest`) | ahead of the line (`line`) | no source offers | source offers late |
|---|---|---|---|---|---|---|
| tier 4, home builder (`push`) | 0 / 0 | −2 / −6 | +2 / −4 | −3 / −8 | −3 / −4 | 0 / 0 |
| tier 4, fast builder (`dcb20`) | 0 / 0 | 0 / +5 | −1 / +7 | +1 / −3 | +10 / +8 | 0 / 0 |
| tier 4, thin and lossy (`loss-thin`) | 0 / 0 | +12 / −2 | +18 / +12 | +91 / +75 | +8 / −12 | – |
| tier 4, withholders | 0 / 0 | +3 / +1 | +2 / −4 | +4 / +1 | +5 / +6 | – |
| variant C, home | 0 / 0 | +1 / +11 | +1 / −1 | +9 / +7 | 0 / −7 | – |
| custody, 1 Gbps proposer | 0 / 0 | 0 / 0 | +2 / −4 | 0 / −2 | +75 / +59 | +17 / +3 |
| custody, 50 Mbps proposer | −247 / −430 | −247 / −430 | +315 / +125 | +215 / +76 | −282 / −526 | −266 / −493 |
| sampling | 0 / 0 | 0 / 0 | 0 / 0 | +4 / 0 | +72 / +48 | +7 / 0 |
| rows, honest | +15 / −22 | −24 / −4 | −33 / −1 | +46 / +39 | +355 / +409 | +59 / −38 |

The source rule is the only form that gains where there is something to gain; elsewhere its
effects in these three-seed toy checks are small and mixed. With a 50 Mbps proposer of 128 column groups it saves a quarter of a second at the median
and nearly half a second at the tail, on every seed. v0.3's rarest-first stops at the first group's
offers in each queue; those offers draw asks early, and the answers and the second copies take the
proposer's window from its first copies. At seed 7 the proposer's last first copy leaves 0.3 s
sooner with the rule, it sends 1 992 second copies where it sent 2 400, it answers 518 asks where it
answered 1 212, and over both blocks it sends 15 % fewer chunks, since more of its queued pushes are
dropped by a holding while they wait. In every single-group cell the rule changes no event
(`check.py --doc v2` passes unchanged), and with a 1 Gbps proposer it changes nothing but the honest
row cell. Dropping the source's offers, or deferring them, gains as much with the slow proposer and
loses with a fast one, whose offers let custodians pull from it while its uplink has room. Answers
first is a wash: against the source rule it moves the median within 5 ms in every tier 4 and variant
C cell but the thin lossy one, which it slows by 12 ms on every seed, it helps the honest row cell's
median by 39 ms, it shortens the asks' round trip at the 99th percentile in most cells, by up to 44
ms, and it saves a few hundredths of a copy. The stronger forms lose: the oldest answer first takes
the slow proposer's uplink from its first copies, and an answer's writer ahead of the window's line
starves the other writers at thin links. Each of `others`, `fresh`, `late` and `othersans` loses all
or most of the slow proposer's gain, and none is ahead of the source rule with `on` in the row cells
by more than a few ms.

The same runs checked the source's offers in tier 4, where a source's offers draw asks that it
answers after its first copies. A home builder answers 0.34 to 1.35 copies of the message over
seeds 7 to 9, and 81 to 94 % of those answers arrive as duplicates. Without its offers it uploads
1.6 to 1.8 copies of the message instead of 2.1 to 2.9 (1.9 instead of 3.2 at 500 nodes), and its
cells' medians move by less than 10 ms. A fast builder uploads 9.7 to 12.0 copies with its offers
and 2.0 without, and then completes 10 ms later at the median. A rule keyed on the configured
uplink, as striping's is, could save the home builder's bytes where they are scarce. It is not in
the document; v0.9's timing of the source's offers, below, saves most of them instead.

**v0.9 in the next version** (2026-11-11, `protocol-v2.md` §4.7, §4.11). What the next version
takes from v0.9, as written:
- the source's holding grows at a chunk's acknowledgement, not at its write;
- its offers wait for the acknowledgement, for every object type;
- §4.11 takes v0.9's rule below the writer, which the toy runs as `--send-buffer 1`.

The choice follows a toy check of v0.9's rules in this document, at 60 nodes (seeds 7 to 16) and at
500 (seeds 7 to 9). Offers per object type (the payload's at the acknowledgement, a column's at
publish) were chosen first, on 2026-11-10. They were replaced on 2026-11-11, once the 500-node
seeds showed the rows' cost to be a 60-node finding. The tables keep them as "offers per type".

`--source-offers publish` (2026-11-18) is the draft's `SOURCE_OFFERS = PUBLISH` (§4.7), the document
before these rules (spec 11b9143) as a source's choice: the source offers each chunk at publish, to the
peers it offers it to at the acknowledgement, and its holding grows at a chunk's first write. It gives
11b9143's digests: the
custody cell above at seed 7 with `--send-buffer 0` (`a5260b63…`), and the research harness's 100-node
custody graph at seed 7 (`--topology`, `--ihave-limits 4096,5000`, `--send-buffer 0`: `05f64359…`).

At 60 nodes, the median of the seeds and its range: p50 in ms, against the document before.

| cell | as taken: offers at the acknowledgement for every type | offers per type | no source offers | `--send-buffer 1` | as taken, with `--send-buffer 1` |
|---|---|---|---|---|---|
| payload, `push` | −4 (−12 to +1) | the same | – | −42 (−53 to −12) | −42 (−53 to −15) |
| payload, `--rebuilt none` | −4 (−9 to +6) | the same | – | −38 (−54 to −6) | −39 (−52 to −12) |
| payload, `sil30` | −8 (−19 to +4) | the same | – | −48 (−98 to −5) | −54 (−102 to −8) |
| payload, 1 Gbps builder (`dcb20`) | 0 (−4 to +4) | the same | – | −3 (−8 to +2) | −2 (−7 to +2) |
| rows | +178 (+69 to +304) | 0 (−20 to +34) | +128 (−10 to +235) | −109 (−171 to −65) | +199 (−24 to +318) |
| rows, liars (`claim20`) | +214 (+39 to +429) | −1 (−32 to +9) | – | −97 (−184 to −44) | +255 (−42 to +384) |
| custody, 50 Mbps proposer | −24 (−46 to +10) | −5 (−34 to 0) | −38 (−61 to −6) | +22 (−77 to +69) | +10 (−48 to +61) |
| custody, 1 Gbps proposer (`--net bld`) | +38 (+24 to +114) | −6 (−9 to +4) | +47 (+14 to +127) | +4 (−2 to +14) | +37 (+6 to +106) |

**The payload's source, at the acknowledgement**, with writes that complete at once:
- it is asked 61 % less (222 ids over three payloads against 572);
- it uploads 2.07 copies of the message instead of 2.50, and a 1 Gbps builder 5.9 instead of 10.0;
- 2 to 6 of its chunks come back a message at the median of the seeds, and up to 59 at one seed,
  since its holding names them a round trip later.

With `--send-buffer 1` the offers' timing changes nothing measurable there (40 asks against 45, the
medians within 4 ms), and 0 to 2 chunks come back.

**Why the rows pay at 60 nodes.** At seed 7, with the offers at publish, the proposer's relation
peers pulled from it, while it pushed, the cells it did not push them, and completed at 1.8 to
2.0 s. Offered each cell only at its acknowledgement, they completed 410 to 470 ms later, and the
other nodes 56 ms later. Those pulls are also what a column's source saves at the acknowledgement
(the medians of the seeds):
- it is asked 88 to 99 % less (the rows' proposer 214 ids over three blocks against 6 241);
- it uploads 5 to 28 % less (the rows' proposer 1.49 copies of its block instead of 2.07, a 1 Gbps
  proposer 1.96 instead of 2.74, a 50 Mbps proposer 1.46 instead of 1.54).

With `--send-buffer 1` the savings are about the same: 87 to 96 % of the asks and 5 to 29 % of the
upload, against `--send-buffer 1` alone.

**At 500 nodes** (degree 70, seed 7, one run each; p50 in ms, against the document before):

| cell | as taken | offers per type | `--send-buffer 1` | as taken, with `--send-buffer 1` |
|---|---|---|---|---|
| payload, tier 4 in the all-home network | −4 | the same | −19 | −22 |
| rows | −8 | −15 | −31 | −9 |
| custody, 50 Mbps proposer | −48 | −30 | – | – |
| custody, 1 Gbps proposer, a fifth of the nodes sampling | +5 | −1 | −9 | – |

- **The payload's source, as taken,** is asked 22 % less (2 139 ids over six payloads against
  2 733) and uploads 3.06 copies of the message instead of 3.24.
- **`--send-buffer 1`** saves 0.31 copies of the payload, with v0.9's offers or without.

**The two options at 500 nodes, over seeds 7 to 9.** Offers at the acknowledgement for every type,
as taken, against offers per type, paired by seed: the median of the seeds and its range, in ms,
and the range over the seeds of what a column's source saves.

| cell | p50 | seeds later | p99 | the source's upload | its asks |
|---|---|---|---|---|---|
| rows | +7 (−15 to +17) | 2 of 3 | −7 (−34 to +19) | 14 to 23 % less | 95 to 97 % less |
| rows, `--send-buffer 1` | +28 (+18 to +54) | 3 of 3 | +33 (+23 to +37) | 14 to 18 % less | 92 to 98 % less |
| custody, 50 Mbps proposer | −26 (−38 to −18) | 0 of 3 | −41 (−62 to −30) | 8 to 9 % less | 91 to 96 % less |
| custody, 1 Gbps proposer, a fifth of the nodes sampling | +9 (+6 to +15) | 3 of 3 | +22 (+9 to +31) | 28 to 33 % less | 57 to 69 % less |

- **The rows' cost** of a column's offers at the acknowledgement is 175 ms against offers per type
  at 60 nodes (seeds 7 to 16; 300 with `--send-buffer 1`), and 7 ms here (28).
- **The proposer's relation peers.** At seed 7, 12 of the 499 nodes pull more than 20 cells from
  the rows' proposer with offers per type, against 26 of 59 at 60 nodes in the document before.
  With offers at the acknowledgement for every type they complete 18 ms later at the median (−140
  to +292). The two of them that completed first, at 1.79 and 2.05 s, are 292 and 253 ms later.
  The 449 nodes that pull nothing from the proposer move by 5 ms.
- **`--send-buffer 1` on the rows** brings them 2 ms sooner (1 to 21) as taken, and 45 ms sooner
  (12 to 58) with offers per type.

**`golden-v2.txt` is re-recorded.**
- At seed 7 every cell moves, by −10 to +2 ms at the median, −35 to +9 ms at the tail and −0.13 to
  +0.06 copies. `golden.txt` is unchanged.
- Against v0.9's own recording, eleven cells are within 13 ms at the median, 18 ms at the tail and
  0.06 copies. `loss-thin` is 6 ms later and 0.14 copies lighter.

**The announce relation's width and the row pull delay** (`protocol-v2.md` §8, `[D5]` and `[D8]`,
decided 2026-11-14). Each arm is run against `base` (`ALL_JOINED` on both axes, a 1 s row delay)
and paired with it by seed; a figure is the median over the seeds of the arm's change. The arms:
`--col-announce SAMPLE` or `NONE`, `--row-announce NONE`, and `--row-delay 0`, `0.5` or `2`. The
custodians' times are their warm p50 and p99, and a row member's are those of its 64th cell; ∞
where a node never got there. *Short* counts the nodes with a group incomplete in a block, summed
over the seeds and blocks, the arm's against `base`'s. *Copies* are data and control; *offers* are
the arm's total against `base`'s. §8 reads them by its rule.

At 60 nodes (degree 30, three blocks, seeds 7 to 16; `--setting custody` or `rows`; the 1 Gbps
proposer `--net bld`; half withheld `--withhold 64`, with `--supernodes 10` in custody and
`--row-subnets 16` in rows; liars `--fault claim20`, a fifth of the nodes lying about their row
holdings):

| setting | arm | custodians p50 / p99 (ms) | row member's 64th cell p50 / p99 (ms) | short: custodians; row members (arm / `base`) | copies | offers |
|---|---|---|---|---|---|---|
| custody | columns `SAMPLE` | +1 / +3 | – | 0 / 0 | +0.00 | −29.5 % |
| custody | columns `NONE` | +1 / +0 | – | 0 / 0 | +0.00 | −29.6 % |
| custody, 1 Gbps proposer | columns `SAMPLE` | −1 / −0 | – | 0 / 0 | −0.00 | −29.2 % |
| custody, 1 Gbps proposer | columns `NONE` | −1 / −0 | – | 0 / 0 | −0.00 | −29.2 % |
| custody, half withheld | columns `SAMPLE` | +2 / −5 | – | 0 / 0 | −0.04 | −19.4 % |
| custody, half withheld | columns `NONE` | +4 / −4 | – | 0 / 0 | −0.04 | −19.7 % |
| rows | columns `SAMPLE` | −10 / −26 | −13 / −14 | 0 / 0; 0 / 0 | −0.02 | −21.4 % |
| rows | columns `NONE` | −11 / −45 | −10 / −12 | 0 / 0; 0 / 0 | −0.03 | −24.6 % |
| rows | rows `NONE` | +156 / +138 | +∞ / +∞ | 0 / 0; 1365 / 0 | −0.45 | −31.2 % |
| rows | delay 0 s | −4 / −5 | −28 / +9 | 0 / 0; 0 / 0 | +0.01 | −0.6 % |
| rows | delay 0.5 s | +10 / −8 | −47 / −10 | 0 / 0; 0 / 0 | +0.02 | −0.5 % |
| rows | delay 2 s | +161 / +181 | +893 / +888 | 0 / 0; 0 / 0 | +0.21 | +3.8 % |
| rows, liars | columns `SAMPLE` | −12 / −15 | −11 / −414 | 3 / 1; 0 / 1 | −0.03 | −21.3 % |
| rows, liars | columns `NONE` | −12 / −26 | −20 / −361 | 2 / 1; 1 / 1 | −0.04 | −24.5 % |
| rows, liars | rows `NONE` | +144 / +201 | +∞ / +∞ | 3 / 1; 1444 / 1 | −0.39 | −31.5 % |
| rows, liars | delay 0 s | −10 / −15 | −85 / +∞ | 2 / 1; 219 / 1 | +0.00 | −1.6 % |
| rows, liars | delay 0.5 s | −7 / −14 | −80 / +∞ | 1 / 1; 154 / 1 | +0.00 | −1.2 % |
| rows, liars | delay 2 s | +147 / +194 | +846 / −1872 | 0 / 1; 0 / 1 | +0.13 | +4.7 % |
| rows, half withheld | columns `SAMPLE` | +8 / +16 | −21 / −40 | 0 / 0; 0 / 0 | −0.04 | −22.8 % |
| rows, half withheld | columns `NONE` | −2 / −2 | −34 / −48 | 0 / 0; 0 / 0 | −0.06 | −25.3 % |
| rows, half withheld | rows `NONE` | +∞ / +∞ | +∞ / +∞ | 1743 / 0; 1770 / 0 | −1.47 | −68.7 % |
| rows, half withheld | delay 0 s | +10 / +1 | +2 / −30 | 0 / 0; 0 / 0 | −0.00 | −0.1 % |
| rows, half withheld | delay 0.5 s | −6 / +6 | −24 / −55 | 0 / 0; 0 / 0 | −0.01 | +0.1 % |
| rows, half withheld | delay 2 s | +386 / +333 | +860 / +818 | 0 / 0; 0 / 0 | −0.03 | +2.6 % |

With liars, a row member's p99 is ∞ on some seeds of `base` as well as of the arm, so its median
change there (−414, −361, −1872) compares finite with infinite seeds and says little.

At 500 nodes (degree 70, two blocks, seeds 7 to 9, `--msgs 2`; half withheld `--withhold 64
--row-subnets 32 --net bld`). Three seeds show a pass or a fail by the rule, not a comparison:

| setting | arm | custodians p50 / p99 (ms) | row member's 64th cell p50 / p99 (ms) | short: custodians; row members (arm / `base`) | copies | offers |
|---|---|---|---|---|---|---|
| custody | columns `SAMPLE` | +3 / +6 | – | 0 / 0 | −0.03 | −7.1 % |
| custody | columns `NONE` | +2 / −7 | – | 0 / 0 | −0.03 | −7.2 % |
| rows, half withheld, 1 Gbps proposer | columns `SAMPLE` | +11 / +26 | +0 / +1 | 0 / 0; 0 / 0 | −0.14 | −26.9 % |
| rows, half withheld, 1 Gbps proposer | columns `NONE` | +11 / +7 | −1 / −8 | 0 / 0; 0 / 0 | −0.15 | −28.5 % |
| rows, liars | columns `NONE` | +19 / +16 | −6 / −2 | 0 / 0; 0 / 0 | −0.17 | −30.6 % |
| rows, half withheld, 1 Gbps proposer, liars | columns `NONE` | +40 / +13 | +11 / +18 | 0 / 0; 0 / 0 | −0.17 | −30.0 % |
