# formal/: models of the protocol, proofs, and a Lean twin

## How the checks fit together

`protocol.md`'s rules come with their code, in Python. Some of the checks run that code or
transcribe it; the others check models of the rules written by hand. The diagram shows the toy, the
twin and the models, and the links between them; a paragraph below says what each link shows at this
commit. Paths in this section are from the repository's root.

```text
                    protocol.md: the rules, with their code in Python
                          |                                     |
                  the code, as written                  the rules, by hand
                          |                                     |
    +---------------------+                                     +----------------------+
    |                     v                                                            |
    |  +--------------------------------+  five monitored  +-------------------------+ |
    |  | toy/: runs it, with recorded   |<-----------------| formal/diffusion.qnt:   |<+
    |  | cells and known answers        |    properties    | Quint, v0.5's rules,    | |
    |  +--------------------------------+                  | small instances         | |
    |                     ^                                +-------------------------+ |
    |                     | trace replay                                               |
    |                     v                                                            |
    |  +--------------------------------+    refinement    +-------------------------+ |
    +->| formal/twin/: transcribes it   | - - - - - - - -> | formal/veil/: Veil,     |<+
       | into Lean, function by         |  (a first piece: | v0.8's rules, any       |
       | function                       |  formal/refine/) | number of nodes         |
       +--------------------------------+                  +-------------------------+
```

**The toy runs the code.** [`toy/`](../toy/) executes every `python` block of `protocol.md` as
written, once per simulated node. Two kinds of check watch what the code does: recorded cells
(`toy/check.py` runs small networks and compares with `toy/golden.txt` a digest of every event, its
time, node, function and arguments, so that a change in what a node does moves a digest, though a
change of state that alters no event does not), and known answers (`toy/*_known.py`: scenarios
whose outcome is stated beforehand, for what a digest cannot show). This is testing: it shows what
the code does in those runs, not that the rules are right, and the toy's numbers are not
measurements. The next version's draft, `protocol-v2.md`, runs in the toy too, with recorded cells
of its own (`toy/golden-v2.txt`), known answers on its own functions, and the invariants its §6.2
names: `toy/invariants.py` checks three on every run and two under its row setting, and
`toy/check.py --doc v2 --golden golden.txt` holds its tier 4 setting to `protocol.md`'s cells.
Outside the toy, nothing here checks its own functions.

**The Quint model checks the rules on small instances.** [`formal/diffusion.qnt`](diffusion.qnt)
models §4–§7 for one group, written by hand at v0.4's rules with v0.5's as switches. TLC explores
its smallest instances, exhaustively or to a depth, and random simulation samples runs of three or
four nodes; checking v0.4 and the fixes proposed for it this way found the ten gaps that v0.5 and
v0.8 closed. Runtime monitors (`formal/toy/monitor.py`) check five of its safety properties on the
code itself, on twelve of `toy/check.py`'s cells: W1 and W2 after each event, S1 and P4 (in a weaker
form) at each transmission, and A1 on the run's count of penalties. W2 is asked of the line as
`protocol.md` §7.1 has it: with a slot free, the first writer in line that can write has a run
queued.
At this commit they find no violation in those cells at seeds 7 to 9, and each of their three known
answers, a rule taken out of the document, makes its monitor fire. Beside the model,
`formal/wire/check_wire.py` checks §1–§2's arithmetic, restated in the script from v0.4's and v0.5's
rules, for every compressed length of a coded group and, for plain groups, the shortest and the
longest of each K. [The Quint model](#the-quint-model), below, gives the instances, the results and
their limits.

**The Veil models prove properties at any size.** [`formal/veil/`](veil/) holds state machines of
the rules, written by hand, each with the state its property needs, and proofs for any number of
nodes, groups and chunks: A1 (an honest node is never penalised) and the per-chunk pieces of no
stall (Q1) as inductive invariants whose conditions Lean's kernel checks, with the count that
completes Q1 in plain Lean; that the transport and the asking go quiet once the environment stops
(Q3), with finitely many nodes, under weak fairness; and agreement, in plain Lean. These are proofs
about the models, which have v0.8's rules: their README lists the rules `protocol.md` changed since,
and whether each result carries over to them is not checked. Each result holds under the assumptions
that README states (with malicious peers, relabelled copies are excluded). The models' traces also
show a run that `protocol.md` §6.1 leaves open, an announcer that is never parked holding the last
resort off; that the run is fair is read from the traces by inspection, not proved. Being written by
hand, the models can drift from the code. No check compares them with the code directly: trace
replay checks the twin against the code, and a first piece of refinement relates one of the models
to the twin, on a narrow scope (both below).

**The twin transcribes the code into Lean.** [`formal/twin/`](twin/) is a
transcription of `protocol.md`'s Python into Lean, function by function, executable: every function
the document's code blocks define, matched by name (its README counts them by section), but not the
helpers the document names without writing them out (one aside, `held`), nor the events it gives in
prose (a connection's close, an announcer's offers ageing out, a group's expiry), nor
`protocol-v2.md`'s own functions. It is not an abstract model: it follows the code's functions and
branches, but for a few narrowings its README names, and holds the code's tables, some in a form of
its own; on its own it proves nothing. It is there to be checked against the code on one side, by
trace replay, and linked to the Veil models on the other, by refinement.

**Trace replay checks the twin against the code.** A tracer runs the toy and records, for each
top-level call of a function that the trace selects (among those the twin has, where the node uses
the implementation that the twin covers), what the call read and wrote of the node's tables, what it
asked of the rest of the node, and what it returned or raised. The twin replays each call from the
recorded state, with the recorded answers, and `formal/twin/check.sh` requires it to read the
entries the Python read, leave those it wrote as the Python left them, and return what it returned
or raise what it raised. The replay does not count a read that the Python made and the twin did not
as a mismatch: it counts such reads separately, and `check.sh` refuses a read left unmade as well as
a mismatch. `check.sh` passes at this commit. It builds the twin from nothing; traces one of
`toy/check.py`'s cells, whose digest must be the recorded one, a few short runs under both
documents, each giving the digest of the same run untraced, and directed sets, states generated to
reach what the cells do not, with the toy's own functions called on them; replays every trace
through the twin with no record mismatched and no read left unmade; and runs controls that must
fail, among them altered records, a mutant (a twin with one rule changed) and a trace of another
tree. Replay is evidence on the calls traced, not on every input, and a faithful twin copies a
mistake of the code: it checks the copying, not the rules. The twin's README says what `check.sh`
checks and what the replay cannot see.

**The twin's record is in [`formal/twin/record/`](twin/record/).** It holds the outputs of one run
of `record.sh`, which traces every cell of `toy/check.py` under both documents, the hand runs and
the directed sets, and replays each trace through the twin. The traces themselves are not kept:
`manifest/hashes.txt` there names each by its two hashes. It also holds the matrix of the mutants,
which shows which mutants part of those traces tell from the twin, by a mismatched record or by a
read left unmade. Its [`RECORD.md`](twin/record/RECORD.md) says what else the directory holds, what
the record ran, what it shows and what it does not show.

**Refinement, from the twin to the Veil models, has a first piece.** A refinement proof would show
that the twin's initial states and each of its steps, projected onto a model's state, are states and
steps the model allows; the model's invariants would then hold for the twin, and its other results
where their assumptions, fairness among them, hold for the projected runs.
[`formal/refine/`](refine/) holds a first piece, whose README states its narrow scope. It relates
the twin's side of the asking path of §6.1 to one Veil model, `NoStallEquiv`, through an abstraction
of the twin at one node and one chunk. In the cases that its theorems cover, a retry timer firing in
the twin (`retry_offer`) that changes the abstraction is a step of that model's generated transition
`retryAsk` or `retryNoop`, and a promise falling due (`promise_due`) that changes it is `promiseDue`
or `parkOther`. A firing that leaves the abstraction as it was, such as a retry of another chunk or
a promise of another group, is the model's stutter. A run, as the package defines it, is a finite
sequence of steps of three kinds: a covered retry timer firing, with the premises of its theorem; a
change that leaves the abstraction as it was; and any other change, after which the abstraction must
satisfy the model's `Invariants`. For a promise falling due, in the cases that its theorems cover,
the package proves this from `Invariants` before the step. For such a run whose first state
satisfies `Invariants`, read through the abstraction, the package proves that every later state does
too. This result takes as hypotheses the model's own statements that `retryAsk` and `retryNoop` keep
`Invariants`; those for `promiseDue` and `parkOther` serve the proof for a promise falling due. A
second result, for a run whose first state is an initial state of the model, read through the
abstraction, gives the model's safety clause, `offers_resolve`, for the abstraction of every state
of the run. It takes the model's statement for its initializer in place of the assumption on the
first state. The piece is not a proof that the twin satisfies the model's properties.

**At this commit.** Together, the links are meant to carry the proofs to the code: properties proved
of the models, refinement showing that the twin behaves as the models do, and replay that the code
behaves as the twin does on every call traced. At this commit, refinement is a first piece only,
under the hypotheses its README names. The twin's record covers what its `RECORD.md` says. The
models have older rules than `protocol.md`'s (v0.5's and v0.8's). So the proofs are about the
models, the replay is evidence on what it traces, and the toy's checks are tests: none of them yet
proves that `protocol.md`'s code has the properties proved of the models. Even with a whole
refinement, the last link, from the twin to the code, stays replay: evidence on the calls traced,
not a proof.

## The Quint model

A [Quint](https://github.com/informalsystems/quint) model of §4–§7 of
[`protocol.md`](../protocol.md) for one group, checked by random simulation and, on the smallest
instances, exhaustively with TLC; runtime monitors that check the same safety properties on the
[toy](../toy/), which runs the document itself; and an exhaustive check of the wire's arithmetic
(§1–§2). The model was written against draft v0.4, and the rules v0.5 added are switches in it, so
one model checks both. Checking v0.4, and the fixes proposed for it, found ten gaps (F1 to F10,
below): v0.5 fixes eight, and v0.8 the other two (F6, F9), as their rows say.

**Scope: small instances.** Three or four nodes, one group of K = 1 or 2 data chunks out of at most
N = 4. TLC explores every reachable state only at K = 1; at K = 2 it covers every state within 29
steps. Random simulation samples runs, which is evidence, not proof. Nothing here says how often a
finding occurs in a real network, or how fast the protocol is.

### What is modelled

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
  RPC. Every connection is a mesh link. The source announces as v0.5 does, to every mesh peer not
  counted as pushed, so under A′ a push its queue refuses is both owed and announced;
  `protocol.md` §5.1 now announces only to the mesh peers it did not choose, which leaves that
  second offer out.
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

### v0.5's rules, as switches

The constants of `diffusion.qnt` select the rules: all false is v0.4 as written, and v0.5 is v0.4
with these on (`PICK` in `tools/gen_instances.py`, the rules picked for v0.5; the instances named
`*_pick`):

| v0.5's rule | switches | fixes |
|---|---|---|
| A′: a push to a mesh peer that does not happen is offered to it instead, and an offer or answer a full queue refuses is owed (§5.2, §7.2, §4.1) | `PROJECT_OFFERS`, `ADMIT_OFFERS` | F1 |
| B′, the last resort: every offer is kept, and when every announcer of a chunk is parked, each is asked once more, at a wait that doubles (§6.1, §8.2) | `LAST_RESORT`, `OFFERS_DURABLE` | F2 |
| C′: no ask before the block is installed; what was offered meanwhile is asked for then (§3, §4.4, §4.2) | `NO_ASK_BEFORE_INSTALL` | F3 |
| D′: the retry and the writer's ask filter check expiry, and a group's pull state goes at its expiry (§6.1, §7.2, §8.1) | `RETRY_CHECKS_EXPIRY`, `EXPIRY_CLEANUP` | F4 |
| E: a promise starts when the ask is written (§7.2, §6.1) | `PROMISE_AT_WRITE` | F5 |
| A copy the deferred store refuses counts as its sender's offer (§4.2) | `REFUSE_OFFERS` | F7 |
| A promise closes with its connection (§6.1, §8.1) | `CLOSE_PROMISES_ON_DISC` | F8 |
| A decode that returns checks expiry (§4.6, §8.1) | `DECODE_CHECKS_EXPIRY` | F10 |

The other switches are earlier forms of these fixes; three candidate rules that v0.5 does not have
(`ROOT_TIED` and `NO_REASK_OPEN` for F6, which v0.8 has as §4.2's ties and §6.1's rule against a
second ask; `RESYNC_ON_CONNECT` for F9, which v0.8's §5.4 moves from the connection to the mesh)
and their earlier forms; the
setting above (the adversary, the late block, expiry, queue limits, coalescing, equivocation,
disconnects, and `*_LATE` gates that hold an event back until its case is reachable); `MAX_ASKS`
(the asks per chunk and node), which keeps the state space finite, and `EAGER_WRITERS` (a writer
runs until it has nothing to send or waits for a slot, in one step), which keeps it small enough
for TLC; and known answers, switches that bring back bugs found earlier.

### What was checked, and the result for v0.5

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
- **Toy**: monitors wrapped around the toy (`toy/monitor.py`) run twelve of `check.py`'s 60-node
  cells, seeds 7–9, about 47 million events at this commit, and check W1 and W2 after each event at
  a node, S1 and P4 at each transmission, and A1 over the run; every node completes. The toy
  installs every block at its publish, no group expires and no connection closes there, and its
  queues have no limit, so C′, D′ and the last three rules above do not act there: the model checks
  them.

| | property | spec | checked by | result |
|---|---|---|---|---|
| A1 | No honest node penalises an honest one: an honest ask never arrives after the asker's HAVE named the chunk ("the claim wins") | §4.5, §4.1 | TLC (K = 2), simulation, toy | holds |
| S1 | No ask leaves for a chunk the node holds, or after its pull stopped | §6.1, §6.2, §7.2 | TLC (K = 2), simulation, toy | holds |
| W1 | `in_flight` is the writers holding a slot plus the chunks in `sent`, and at most W | §7.1 | TLC (K = 1, 2), simulation, toy | holds |
| W2 | With a slot free and a writer waiting, the first in line will run | §7.1 | TLC (K = 1, 2), simulation, toy | holds; the toy's monitor asks it of the first writer in line that can write, as `protocol.md` §7.1 has it (§7.3) |
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
| Q1 | When nothing is left to happen, every honest node is complete | §4–§7 | TLC (K = 1, 2), simulation | holds, except in F6's case before §4.2's ties and §6.1's rule against a second ask, and F9's before §5.4; not checked where a group expires or the code is inconsistent, where completion is not expected |
| Q3 | Every run goes quiet, with every honest node complete | §4–§7 | TLC (K = 1, weak fairness), simulation (quiet and complete by step 600; 1,000 where four nodes only pull) | as Q1 |

By construction in the model: a node keeps one ask window per chunk at a time (§6.1), though an
ask whose window has ended may still be answered; no chunk is sent to a peer whose covering HAVE
the sender holds (§7.2); level 1 gates every use of a chunk (§3); repair gives each short mesh peer
at most its shortfall (§4.6); a forwarding node pushes a chunk to at most `R_NODE − holders` peers
(§5.2). Not checked: that per-peer state stays within §8.2's limits; that either every node that
reaches K passes level 2 or none does (a coding lemma, not checked here: `veil/Agreement.lean`
proves it in plain Lean, under the codec's assumptions `veil/README.md` lists, an MDS code and a
binding hash among them).

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

### The findings, and v0.5

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
| F6 | Under equivocation, a node that switches to the builder's block can stall, in two forms: B′'s once-more asks spent before the switch; and its providers' answers for a chunk (three each) spent before it, which takes a switch within the serve counts' lifetime | simulation (directed cases) | **open** in v0.5 to v0.7 (the second form stalls under v0.5's rules; the first was not found in 20,000 traces, which does not show it gone); closed by `protocol.md` §4.2's ties and §6.1's rule against a second ask of a peer at once (`ROOT_TIED`, `NO_REASK_OPEN`), with which both forms hold here, and proved at any size in `veil/` (`NoStallEquiv.lean`), under its assumptions: every honest copy names the builder's block, rebuilt ones included (§4.6; a node that relabels chunks under the other block's root breaks this, a gap §4.6 lists as open), lifetimes outlast diffusion, and completion is for the nodes the source reaches through nodes that installed that block |
| F7 | A push the deferred store refuses is lost | simulation (a late block, a refusing store) | fixed: in v0.5 a refused copy counted as its sender's offer; since §4.2's ties, its sender is tied and asked at the installation |
| F8 | A promise outlives its connection and parks the peer | simulation (closes) | fixed |
| F9 | Nothing offers a new connection again what the old one lost: on the triangle with two closes at any time, nobody completes | simulation (closes) | **open** in v0.5 to v0.7; closed by `protocol.md` §5.4 (a peer that joins the mesh is announced what the node holds), proved at any size in `veil/` |
| F10 | A decode that returns after its group expired stores, pushes and offers the group again; it takes a decode slower than `GROUP_TTL`, which the document does not bound | simulation (a directed case) | fixed |

F6 to F10 are existence results: how often they occur in real networks is not measured. On v0.4 as
written, TLC found no safety violation (A1, S1, P4, W1, W2) within depth 33 on the triangle at
K = 2, N = 4 (270 M distinct states).

### Running the checks

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
- `veil/`: properties at any size, proved in Veil (Lean 4) for any number of nodes, groups and chunks: A1 at every place a node penalised in v0.8 (an ask: with no assumption under the live window, `protocol.md` §8.1, a group's key fixing its slot, §1, and under the fallback without a slot given the bound on its tombstone; a chunk that fails level 1; a malformed HAVE), and no stall (Q1), in three pieces: no quiet state in which an honest node reachable from the source along mesh links is incomplete, under the assumptions its README states (among them no equivocation); the mesh may change and connections close, with §5.4's announcement to a peer that joins the mesh (F9). Under equivocation it holds with §4.2's ties and §6.1's rule against a second ask (F6), for the nodes the source reaches through nodes that installed the builder's block (`NoStallEquiv.lean`, with its assumptions). The no-stall proof found an eleventh gap, F11: an IHAVE over a receiver's IHAVE limit was ignored, and nothing offered its chunks again; v0.7 closes it (`protocol.md` §4.4, and its README). Q1 also holds with malicious peers, for the honest nodes the source reaches through honest nodes that installed the block, relabelled copies (F12, open in `protocol.md` §4.6) excluded; with finitely many nodes and weak fairness, a run goes quiet (Q3) once the environment stops, adversaries' actions included (the asking with `NO_REASK_OPEN`; with malicious peers, the honest nodes' machinery); level 2 is all or none, a check that succeeds recovers the bytes the root commits, and two honest nodes that both deliver a group deliver the same payload, under the codec's assumptions its README lists, an MDS code and a binding hash among them. Two more findings are there: F13, dropped offers that leave their ask, closed in v0.8, and F14, an announcer that is never parked holding the last resort off, open (`protocol.md` §6.1). The proofs are of v0.8's rules; their README lists what changed since, and each result's assumptions.
- `twin/`: the Lean twin of `protocol.md`'s Python. Its README says what it covers and what
  `check.sh` checks, and `twin/record/RECORD.md` says what its record ran, what it shows and what it
  does not show.
- `refine/`: a first piece of a refinement from the twin to the Veil model `NoStallEquiv`, on the
  asking path of §6.1. Its README states its scope and what it takes as hypotheses.
