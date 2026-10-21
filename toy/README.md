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

## Checking a change

`check.py` runs twelve small cells (60 nodes, three payloads) in parallel and compares each with
`golden.txt`. Each cell's digest hashes every event the simulator processes, in order: its time,
its node, the function it runs, and its int and bytes arguments. A change in what any node does, at
any moment, changes the digest, even when the printed numbers stay the same.

An edit that should change nothing must leave every digest as it is. An edit that changes behaviour
shows which cells moved, with their warm medians before and after; `python3 check.py --update` then
records the new digests, to be committed with the edit. The cells `hold` and `none` have the same
digest: a chunk that is held and never announced is never asked for (§4.6).

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
  deferred or asked for at installation; groups do not expire; connections do not close; the
  queues have no limit but the loss above. The document's rules for those cases are not exercised
  here.

## The network

- **Latency:** the harness's geographic model
  ([`testing/gossipsim/geo.go`](https://github.com/cskiraly/prysm/blob/followup-part1/testing/gossipsim/geo.go)),
  reproduced exactly: five regions, the same base matrix and the same per-pair jitter, from the
  same seed. Seed 7 prints the harness's own line, one-way mean 56 ms, p10 8, p50 61, p90 99.
- **Connections and mesh:** a random 70-regular graph (a circulant mixed by edge swaps, as the
  harness builds it, though not the harness's graph for the seed), and a gossipsub mesh kept
  between 6 and 12 by grafting and pruning, around D = 8.
- **Links:** each node has an uplink and a downlink. A writer hands its entries to the
  connection's transport at once, as a QUIC stream accepts writes; the window (card 14) is what
  holds chunks back, as in the document. The uplink is shared equally by the connections with
  something to send (processor sharing), the fluid limit of the harness's FQ-CoDel, which serves
  per-peer flows a packet at a time; `--uplink rr` sends whole entries in turn instead. The
  downlink is a FIFO over the entries that reach it.
- **Not modelled:** QUIC's congestion control and CoDel's drops, so a fast sender is never slowed
  by a slow receiver's link; processing time (the harness runs on a virtual clock, where processing
  is free too).
- **The transport's buffer:** unbounded unless `--send-buffer` bounds it (below).

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
harness's seen cache counts it, not one held only since the decode.

## Known differences from the harness

- **Bytes.** Without congestion control, a sender is never held back by a slow receiver, so the
  toy's byte counts run above the harness's.
- **Repair.** A decoded node pushes the chunks it rebuilt (§4.6, `push_rebuilt`), and so does the
  toy by default. The toy's repair costs more extra bytes than the harness's, on a clean network
  too, and why is not known yet: its repair bytes are not the protocol's.
- **The transport.** By default a write completes at once, as if a connection's transport took any
  amount ahead of the link. A writer woken first can then hand its whole queue over while window
  slots remain, and the entries behind it go straight after: at publish the source's mesh peers get
  their few pushes and every announcement at once, and ask the source for most chunks. The
  harness's stream writes block, so its writers interleave and its queues hold their backlog, where
  cancel acts. `--send-buffer 1`, one entry at a time per connection, matches the harness on the
  source's asks, answers and cancels and on the forwarding nodes' cancels (n = 100); use it to set the two side
  by side.
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

## Version 2 (`--doc v2`)

*Version 2 is a draft, checked in this toy only (its banner). Figures below from fewer than ten
seeds, a single seed unless stated, are toy checks of a mechanism, not measurements.*

[`protocol-v2.md`](../protocol-v2.md) is run on top of `protocol.md`: `extract.py` pulls both
documents' blocks, v0.3's are executed first and version 2's after them in the same namespace, so
version 2 redefines what it changes (`on_rpc`, `on_chunk`, `forward`, `announce`, the holding and
offer handlers, `on_want`, completion and repair, `publish`, the heartbeat) and keeps what it says
carries over (the ask discipline, `choose_push`; the window and the writer as its §4.11 and §4.12 adapt them). `node.py` supplies what
version 2 leaves to the environment under its tier 4 setting (its §6.1): the payload object type
with its parameters, the join tables, the push relation behind the mesh, and the binding of its
messages onto v0.3's wire (its §7, last column): a holding is an IDONTWANT bitmap, an offer an
IHAVE bitmap, an ask a `WantIndex`. Relations are static, as the mesh is for v0.3.

`check.py --doc v2` runs the twelve cells against version 2's own recording, `golden-v2.txt`
(`--update` records it, as for v0.3). `check.py --doc v2 --golden golden.txt` compares version 2
against `protocol.md`'s cells instead (v0.3's until 2026-10-13, v0.4's until 2026-10-21, v0.5's since); there a cell whose digest moved but whose numbers did not is
reported as such and does not count, since version 2 iterates the relation in peer order where
v0.3 iterates the mesh set, which reorders same-instant sends. On 2026-10-07, with v0.3's slot
window, eleven cells reproduced v0.3's numbers exactly and `rr-stripe` differed by 3 ms at the
median; with the window in bytes (`protocol-v2.md` §4.11) the cells differ from v0.3's by at most
7 ms at the median, 15 ms at the tail and 0.04 copies either way, which is the writer choosing the
entry before taking room and control taking none, not the unit.

**v0.4's P4 in version 2** (2026-10-21, `protocol-v2.md` §4.7): the source's holding names only the
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

**v0.5 in version 2** (2026-10-21, `protocol-v2.md` §5 and the functions it names in its header):
a refused push or offer is offered with the next write, parked announcers are asked once more, the
gate per object type, the promise from the write (a WANT starts none). Against version 2 just
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
tail, infinite on every seed before, is finite on eight after, 2.2 to 8.4 s; not traced. With
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
A sample whose column no link custodies is counted as unreachable and dropped from the sampler's
interest (`unreachable`, the application's decision in the document). The report's `sampling`
line gives the samplers, the samples declared and unreachable, and the custodians' serving load
towards samplers. Indications on the 60-node cell (12 samplers), one seed:

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
repair floor added. Indications at 60 nodes (degree 30, a 1 Gbps proposer, 6 reconstructors), one
seed:

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
for one only once per peer and group and only when it is the RPC's one ask on that group, which is
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
and 12) on a liar's claim that passed the probe because another peer brought the probed cell: the
member rebuilds instead of trusting it. The check moved the few pairs short in that cell on those
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

`--answers-first` sets the writer's order (`protocol-v2.md` §4.12). The default sends a source's
own chunks first, past its offers and answers, by rarity, and `on` adds the option of answers
before pushes. `v03` is v0.3's order, rarest-first up to the first control-only entry. The other
values are forms checked against it on 2026-10-07, kept so that the check can be repeated
(`node.py`, `_writer_variants`): `oldest` sends the oldest answer first, before a source's own
chunks too; `line` does that and puts the answer's writer ahead of the window's line; `others`,
`fresh`, `late` and `othersans` protect a source's own chunks in weaker ways. `--source-offers off`
drops the source's offers and `late` queues them after the pushes of every group it published at
the same instant. The table gives each form's change against v0.3's order, at the median and the
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
the document.
