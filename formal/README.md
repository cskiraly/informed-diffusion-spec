# formal/: a model of the protocol, and what was checked

A [Quint](https://github.com/informalsystems/quint) model of §4–§7 of
[`protocol.md`](../protocol.md) for one group, checked by random simulation and, on the smallest
instances, exhaustively with TLC; runtime monitors that check the same safety properties on the
[toy](../toy/), which runs the document itself; and an exhaustive check of the wire's arithmetic
(§1–§2). The model was written against draft v0.4, and the rules v0.5 added are switches in it, so
one model checks both. Checking v0.4, and the fixes proposed for it, found ten gaps (F1 to F10,
below): v0.5 fixes eight, and two remain open.

**Scope: small instances.** Three or four nodes, one group of K = 1 or 2 data chunks out of at most
N = 4. TLC explores every reachable state only at K = 1; at K = 2 it covers every state within 29
steps. Random simulation samples runs, which is evidence, not proof. Nothing here says how often a
finding occurs in a real network, or how fast the protocol is.

## What is modelled

- **Events.** One step is one event: a link delivers its oldest RPC, a writer runs, a timer fires,
  a node finishes decoding, a block installs, a group expires, the source publishes. Node 0 is the
  source. Most properties are monitors: the state records a violation at the event that breaks it.
- **Time.** Links are FIFO and deliver at any time; a timer fires at any time after it is armed.
  The model has no clock, so it covers every timing, and its liveness results say nothing about
  latency. Where the document draws at random (a forwarding node's push targets, the retry among
  tried announcers, the repair's shuffle), any choice is allowed, which covers every outcome of the
  draw. The source's plan follows §5.3, with ties going any way; rarest at pop follows card 9,
  taking the earliest queued chunk on ties.
- **The transport** (§7): the per-peer queues and the window, its slots and wake-ups; optionally
  queues that refuse entries beyond a limit, and a transport that coalesces several writes into one
  RPC. Every connection is a mesh link.
- **The adversary**: a node that answers, forwards and acknowledges nothing, and sends up to three
  announcements or HAVEs of its choice; forged chunks, one that fails its proof and one that names
  a root that never installs; a builder whose code is inconsistent, so that level 2 fails; and
  equivocation: nodes that installed the proposer's other block, whose bid commits the same group,
  and switch to the builder's block later.
- **The setting**: a block that installs late, with chunks waiting in a deferred store that may
  refuse them; expiry; and disconnects, where a connection closes and a new one opens at once.
- **Not modelled**: heartbeat gossip and its pacing (§6.4), the fast class (card 17), the offer
  table's limit per announcer and `MAX_PENDING_GROUPS` (§8.2), timed lifetimes such as `PARK_TTL`,
  several groups at once, restarts, and a proposer's third block. By default a group does not
  expire while it decodes (`GROUP_TTL` runs seconds after its last chunk, a decode milliseconds); a
  directed case lifts this, since the document bounds no decode. Card 16's order and striping
  (card 13) need no model of their own: any choice among the push candidates covers every order
  they produce.

## v0.5's rules, as switches

The constants of `diffusion.qnt` select the rules: all false is v0.4 as written, and v0.5 is v0.4
with these on (`PICK` in `tools/gen_instances.py`, the rules picked for v0.5; the instances named
`*_pick`):

| v0.5's rule | switches | fixes |
|---|---|---|
| A′: a push to a mesh peer that does not happen is offered to it instead, and an offer or answer a full queue refuses is owed (§5.2, §7.2, §4.1) | `PROJECT_OFFERS`, `ADMIT_OFFERS` | F1 |
| B′: every offer is kept, and when every announcer of a chunk is parked, each is asked once more, at a wait that doubles (§6.1, §8.2) | `LAST_RESORT`, `OFFERS_DURABLE` | F2 |
| C′: no ask before the block is installed; what was offered meanwhile is asked for then (§3, §4.4, §4.2) | `NO_ASK_BEFORE_INSTALL` | F3 |
| D′: the retry and the writer's ask filter check expiry, and a group's pull state goes at its expiry (§6.1, §7.2, §8.1) | `RETRY_CHECKS_EXPIRY`, `EXPIRY_CLEANUP` | F4 |
| E: a promise starts when the ask is written (§7.2, §6.1) | `PROMISE_AT_WRITE` | F5 |
| A copy the deferred store refuses counts as its sender's offer (§4.2) | `REFUSE_OFFERS` | F7 |
| A promise closes with its connection (§6.1, §8.1) | `CLOSE_PROMISES_ON_DISC` | F8 |
| A decode that returns checks expiry (§4.6, §8.1) | `DECODE_CHECKS_EXPIRY` | F10 |

The other switches are earlier forms of these fixes; three candidate rules that v0.5 does not have
(`ROOT_TIED` and `NO_REASK_OPEN` for F6, `RESYNC_ON_CONNECT` for F9) and their earlier forms; the
setting above (the adversary, the late block, expiry, queue limits, coalescing, equivocation,
disconnects, and `*_LATE` gates that hold an event back until its case is reachable); `MAX_ASKS`
(the asks per chunk and node), which keeps the state space finite, and `EAGER_WRITERS` (a writer
runs until it has nothing to send or waits for a slot, in one step), which keeps it small enough
for TLC; and known answers, switches that bring back bugs found earlier.

## What was checked, and the result for v0.5

Four ways of checking:

- **TLC, K = 1**: every reachable state of the triangle with K = 1, N = 2, R = 1, one window slot,
  one ask per chunk and node, and eager writers, under v0.5's rules (`x3k1e_pick`): complete, with
  no violation (3,283,843 distinct states, depth 36; under ten minutes on six workers). These are
  as many states as with A′ to E alone: v0.5's three other rules act only on a copy the deferred
  store refuses, a closed connection and an expired group, none of which this instance has.
  Eventual completion is checked as `<>[]Quiet` under weak fairness (with Q1, quiet means
  complete). **Nobody asks on this instance**: every node completes on the first chunk it is
  pushed, and a probe (`NoAsk`: no node decides an ask) holds in every state. So it checks the push
  side, the window and completion; the properties of asks, promises and parks hold there trivially,
  and only K = 2 and the simulation check them.
- **TLC, K = 2**: the triangle with K = 2, N = 3, otherwise as above (`x3k2n3e_rev`), breadth first:
  every state within depth 29 (168 M distinct states); the check stopped at its deadline at depth
  30, after eight hours on six workers. It runs A′ to E without v0.5's three other rules, which act
  only on a copy the deferred store refuses, a closed connection and an expired group, none of which
  this instance has. O1 was added to the model after this check and is not among its invariants.
- **Simulation**: Quint's random simulator on the 30 rows of v0.5's rules in `tools/sweep.sh`, up
  to 5,000 traces a row (20,000 where marked; a row stops at its first violation), of up to 800
  steps where a row checks completion (1,200 where four nodes only pull) and 600 otherwise. The
  rows cover the triangle, the kite (a triangle plus a node with one peer) and the four-node mesh,
  with an adversary, forged chunks, one window slot, a coalescing transport, queues of two and of
  three entries, a late block with a refusing deferred store, closes while promises are open,
  closes at any time, a withholder's closes, expiry while asks are out, a group that expires while
  it decodes, an inconsistent code, and equivocation (with a store that keeps copies or refuses
  them, the switch late, and the providers' answers spent before the switch).
- **Toy**: monitors wrapped around the toy (`toy/monitor.py`) check after every event of
  `check.py`'s twelve 60-node cells, seeds 7–9, about 36 million events; every node completes. The
  toy installs every block at its publish, nothing expires or closes there and its queues have no
  limit, so C′, D′ and the last three rules above do not act there: the model checks them.

| | property | spec | checked by | result |
|---|---|---|---|---|
| A1 | No honest node penalises an honest one: an honest ask never arrives after the asker's HAVE named the chunk ("the claim wins") | §4.5, §4.1 | TLC (K = 2), simulation, toy | holds |
| S1 | No ask leaves for a chunk the node holds, or after its pull stopped | §6.1, §6.2, §7.2 | TLC (K = 2), simulation, toy | holds |
| W1 | `in_flight` is the writers holding a slot plus the chunks in `sent`, and at most W | §7.1 | TLC (K = 1, 2), simulation, toy | holds |
| W2 | With a slot free and a writer waiting, the first in line will run | §7.1 | TLC (K = 1, 2), simulation, toy | holds |
| P4 | Each HAVE the source writes names only chunks it has written, plus the receiver's first | §5.1 | TLC (K = 1, 2), simulation, toy | holds; the toy's monitor checks a weaker form: each HAVE from the source names at most one chunk it has not sent |
| O1 | An announcement an honest node writes names only chunks it can serve | §4.4, §4.5 | TLC (K = 1), simulation | holds |
| D1 | After `drop_group`, nothing of the group but HAVEs leaves the node | §3, §4.6 | simulation (an inconsistent code) | holds |
| D2 | No peer is parked for a chunk whose authentic copy from it arrived after the latest ask to it was written, nor for a dropped group | §6.1, §4.6 | TLC (K = 2), simulation | holds; under equivocation a node still on the other block may park a provider whose copy waits for the builder's block (the monitor allows it there), and with a refusing store under equivocation parks are not monitored |
| | No peer is parked for an ask that never left the node | §6.1, §7.2 | TLC (K = 2), simulation | holds |
| D3 | No ask leaves for a group past its active lifetime | §4.5, §8.1 | simulation (expiry, 20,000 traces) | holds |
| D4 | No peer is parked for a promise its closed connection left open | §6.1, §8.1 | simulation (closes) | holds |
| D5 | Past its active lifetime a node stores nothing of the group | §8.1 | simulation (expiry while decoding) | holds |
| L4 | A chunk that fails level 1 counts only against a forger | §3 | simulation (forged chunks) | holds |
| L5 | No forged copy discharges another peer's promise | §3, §6.1 | simulation (forged chunks) | holds |
| Q1 | When nothing is left to happen, every honest node is complete | §4–§7 | TLC (K = 1, 2), simulation | holds, except in F6's and F9's cases; not checked where a group expires or the code is inconsistent, where completion is not expected |
| Q3 | Every run goes quiet, with every honest node complete | §4–§7 | TLC (K = 1, weak fairness), simulation (quiet and complete by step 600; 1,000 where four nodes only pull) | as Q1 |

By construction in the model: a node keeps one ask window per chunk at a time (§6.1), though an
ask whose window has ended may still be answered; no chunk is sent to a peer whose covering HAVE
the sender holds (§7.2); level 1 gates every use of a chunk (§3); repair gives each short mesh peer
at most its shortfall (§4.6); a forwarding node pushes a chunk to at most `R_NODE − holders` peers
(§5.2). Not checked: that per-peer state stays within §8.2's limits; that either every node that
reaches K passes level 2 or none does (a coding lemma, not mechanised).

**The wire** (§1–§2, unchanged since v0.4; `wire/check_wire.py`), for every K a coded group can
have and every compressed length snappy can produce, and for plain groups (K from 129 to 8192) at
the shortest and the longest length of each K: `build_group`'s K and `valid_descriptor`'s K(d)
agree (they would part only above about UNIT/K times compression, which snappy cannot reach); every
chunk fits `MAX_SEGMENT_SIZE` (the largest is 19,146 bytes); the chunk lengths add up to
`total_length` and the last data chunk is never empty; a proof fits `List[Bytes32, 14]` and a bitmap
of 8,192 indices fits `MAX_HAVE_BYTES`. One observation for the byte-exact phase: a HAVE string
with 19 bitmap bytes is as long as a structured id, and only the 5-byte `MAGIC` and `VERSION` prefix
tells them apart; in tier 4 no full chunk id travels in a control field, so nothing reaches the
ambiguity.

**Known answers**: switches that break a property where the break is reachable, to show that the
check catches it. The sweep has a row for each of F1 to F10 where the finding shows; without the
writer's ask filter, S1 and A1 fail (in TLC at the 14th state at K = 2); without either wake-up,
W2; with IDONTWANT handled before IWANT on a coalescing transport, A1; with the source's HAVE
unpaced, P4 (in TLC at the third state at K = 1); and without fairness TLC finds a run that stutters
before it is quiet. L4 has no known answer. In the toy, three rules taken out of the extracted
document make their monitors fire (`--break askfilter`: S1 and A1; `wake`: W2; `p4`: P4); W1 has no
known answer there.

## The findings, and v0.5

F1 to F5 were found in v0.4 as written. F6 to F10 were found with the fixes A′ to E on, once the
model had equivocation, disconnects, a refusing deferred store and expiry; F7 and F10 are in v0.4
as written too.

| | the gap | found by | v0.5 |
|---|---|---|---|
| F1 | A push that projection (card 12) skips still counts as pushed, so its target is never offered the chunk: a triangle, a ring or a node with one peer never completes. TLC's shortest stall, on the triangle at K = 2, is 20 steps of publish, writes and deliveries, with no timer in it, and v0.4's toy stalls the same way | simulation, TLC | fixed (A′) |
| F2 | One slow answer parks a node's only provider for the payload (§6.1) | simulation | fixed (B′) |
| F3 | An answer that waits for its block parks the node that sent it | simulation (a late block) | fixed (C′) |
| F4 | `retry_offer` has no expiry check | simulation (expiry) | fixed (D′) |
| F5 | A peer is parked for an ask that never left, held behind the window or dropped at a full queue | simulation | fixed (E) |
| F6 | Under equivocation, a node that switches to the builder's block can stall, in two forms: B′'s once-more asks spent before the switch; and its providers' answers for a chunk (three each) spent before it, which takes a switch within the serve counts' lifetime | simulation (directed cases) | **open**: the second form stalls under v0.5's rules; the first was not found (20,000 traces), which does not show it gone |
| F7 | A push the deferred store refuses is lost | simulation (a late block, a refusing store) | fixed |
| F8 | A promise outlives its connection and parks the peer | simulation (closes) | fixed |
| F9 | A new connection is never offered what the old one lost: on the triangle with two closes at any time, nobody completes | simulation (closes) | **open** |
| F10 | A decode that returns after its group expired stores, pushes and offers the group again; it takes a decode slower than `GROUP_TTL`, which the document does not bound | simulation (a directed case) | fixed |

F6 to F10 are existence results: how often they occur in real networks is not measured. On v0.4 as
written, TLC found no safety violation (A1, S1, P4, W1, W2) within depth 33 on the triangle at
K = 2, N = 4 (270 M distinct states).

## Running the checks

Node.js 18 or later (for Quint), Java 17 or 21 (for TLC), Python 3, and curl. In `formal/`:

```
npm ci                                  # Quint 0.33.0, as package-lock.json pins it
./quint typecheck instances.qnt         # ./quint runs it with QUINT_HOME=.quint
```

Random simulation: one instance (its switches are in `instances.qnt`) against a property set (at
the end of `diffusion.qnt`), or the sweep, every row against its expected result:

```
./quint run --main=t3_pick --invariant=liveProps --max-samples=5000 --max-steps=800 instances.qnt
tools/sweep.sh 5000 4 _pick             # v0.5's 30 rows, four at a time: PASS when as expected
tools/sweep.sh 5000 4                   # every row: v0.4, earlier forms, candidates, known answers
mkdir -p out && ./quint run --main=t3disc_any_pick --invariant=discProps --max-samples=5000 \
    --max-steps=800 --mbt --out-itf=out/f9.itf.json instances.qnt
python3 -I tools/itf.py out/f9.itf.json --steps          # F9's trace, one line per step
```

TLC (`quint verify --backend=tlc` fails here, as the model's IR is over Apalache's 20 MB RPC limit,
so `tlc/mkcheck.sh` takes the IR through a file: Quint's JSON IR, Apalache's typechecker writes
TLA+, and a wrapper module written by hand in `mkcheck.sh` adds the invariants). The first run
downloads Apalache 0.62.1, whose jar holds TLC:

```
tlc/mkcheck.sh x3k1e_pick gen AllProps NoExpiredAsk LIVE   # TLA+ and a config, in tlc/out/
tlc/mkcheck.sh x3k1e_pick run 6                            # 6 workers
```

`tlc/configs/` holds the configurations of the checks below, all but the probe's; `mkcheck.sh`
writes the same for the invariants it is given:

| instance | `mkcheck.sh … gen` | result |
|---|---|---|
| `x3k1e_pick`: v0.5, K = 1 | `AllProps NoExpiredAsk LIVE` | complete: no violation, eventual completion holds (3,283,843 states, depth 36) |
| `x3k1e_pick` | `NoAsk` (a probe) | holds in every state: nobody asks |
| `x3k2n3e_rev`: A′ to E, K = 2, N = 3 | `AllProps` | no violation within depth 29 |
| `x3k2n2e_rev`: A′ to E, K = 2, N = 2 | `AllProps LIVE` | no violation within depth 21; eventual completion not shown |
| `x3k2n3e_noaskfilter`: v0.4 without the writer's ask filter | `Safe` | violated at the 14th state (known answer) |
| `x3k1e_unpaced`: v0.4 with the source's HAVE unpaced | `P4` | violated at the third state (known answer) |
| `x3e`: v0.4, K = 2, N = 4 | `NoStall` | violated: F1's shortest stall |

The toy's monitors and the wire's arithmetic, from the repository's root:

```
python3 -I formal/toy/monitor.py --seeds 7,8,9 -j 6                       # no violation expected
python3 -I formal/toy/monitor.py --cells push --seeds 7 --break askfilter  # known answer: S1, A1
python3 -I formal/wire/check_wire.py
```

## Files

- `diffusion.qnt`: the model. One state record, pure functions named after the document's
  (`onRpc`, `onChunk`, `forward`, `writerStep`, `acquireSlot`, ...), one action per event, the
  switches as constants, and the monitors and property sets at the end.
- `instances.qnt`, `one/`: the instances, written by `tools/gen_instances.py` from its table (edit
  the table: `python3 -I tools/gen_instances.py > instances.qnt`, and `--one <name>` for a single
  instance for TLC).
- `tools/sweep.sh`: the regression sweep; `tools/itf.py`: reads a trace.
- `tlc/mkcheck.sh`, `tlc/configs/`: TLC.
- `toy/monitor.py`: the runtime monitors on the toy; `wire/check_wire.py`: §1–§2's arithmetic.
- `package.json`, `package-lock.json`, `quint`: the pinned toolchain.
- `veil/`: one rule at any size: "the claim wins" (A1), proved in Veil (Lean 4) for any number of nodes, groups and chunks, under one stated assumption (its README).
