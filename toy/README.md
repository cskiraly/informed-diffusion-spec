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
python3 run.py --net dcb20 --seed 7 --without 17   # the datacenter mix, without card 17
python3 run.py --net home --stripe on              # every source stripes, as the harness's tier-4 cells did
python3 run.py --net home --rebuilt none           # nothing rebuilt, as in the harness's tier-4 cells
python3 run.py --latency-only --seed 7             # the latency summary line only
python3 check.py                                   # the document still runs as recorded (below)
python3 run.py --topology cell.jsonl.gz --rebuilt none --stripe on   # a harness cell's own network (below)
```

Networks (`scenario.py`): `home` (every node 50/100 Mbps), `dc20` (20 % of nodes at 1 Gbps,
home builder), `dcb20` (the same and a 1 Gbps builder), `bld` (the 1 Gbps builder alone). A cell,
one run of one configuration, prints what the harness prints for each payload: the receivers' p50
and p99 completion time (the K-th distinct frame, from the publish instant, nearest rank) and the
bytes each node received, in copies of the compressed payload, frames and control apart. Payloads
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
digest: a frame that is held and never announced is never asked for (§4.6).

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
- **Stand-ins:** frames carry no bytes, only their length and identity; the Merkle proof always
  checks (only honest nodes run here); a decode returns the source's frames and takes 5 ms
  (`--check-ms`; the document leaves a decode's duration to the implementation). `HaveBitmap` and
  `WantIndex` are replaced by classes that know their wire size and compare asks by value.
- **Card switches:** `--without N` turns card N off where the document reads a switch (`CANCEL`,
  `RAREST`, `PROJECT`, `PACED`), a constant (`R`, `STRIPE_UPLINK`, `R_NODE`) or the window (`W`).
- **Variants and stresses the document does not specify:** rebuilt frames held or announced
  instead of pushed, or none rebuilt at all (`--rebuilt`), a cap on the frames pushed per peer
  (`--rb-max`) and a random wait before the push (`--rb-jitter-ms`); the harness's withholders and
  silent nodes (`--fault`; a silent node pushes nothing it rebuilt, as in the harness), frames
  lost at admission (`--loss-data`) and thin links (`--up`, `--down`).

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
  holds frames back, as in the document. The uplink is shared equally by the connections with
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

- `budget`: a relay that pushed one frame more often than its push degree;
- `window`: a node with more slots in flight than `W`;
- `overlap`: an ask for a frame decided while an earlier ask for it is open (inside `IWANT_WINDOW`, not
  yet held), timed at `may_ask`, where the harness's request ledger times its asks too;
- `late`: a frame sent to a mesh peer whose HAVE for it (in an IDONTWANT, the only carrier that feeds
  `peer_has`) had reached the sender earlier in the message, held or since expired, as the harness's
  ledger reads it; `late_live` counts those the sender still held, which cancel should have dropped;
- `fault`: a frame from a silent relay, or an answer from a withholder.

The recorder reads node state without creating entries and schedules nothing, so a run's events
and digest are the same with it or without it. A duplicate is a frame received before, as the
harness's seen cache counts it, not one held only since the decode.

## Known differences from the harness

- **Bytes.** Without congestion control, a sender is never held back by a slow receiver, so the
  toy's byte counts run above the harness's.
- **Repair.** A decoded node pushes the frames it rebuilt (§4.6, `push_rebuilt`), and so does the
  toy by default. The toy's repair costs more extra bytes than the harness's, on a clean network
  too, and why is not known yet: its repair bytes are not the protocol's.
- **The transport.** By default a write completes at once, as if a connection's transport took any
  amount ahead of the link. A writer woken first can then hand its whole queue over while window
  slots remain, and the entries behind it go straight after: at publish the source's mesh peers get
  their few pushes and every announcement at once, and ask the source for most frames. The
  harness's stream writes block, so its writers interleave and its queues hold their backlog, where
  cancel acts. `--send-buffer 1`, one entry at a time per connection, matches the harness on the
  source's asks, answers and cancels and on the relays' cancels (n = 100); use it to set the two side
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
