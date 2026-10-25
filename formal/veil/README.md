# SEACAST in Veil: properties at any size

Models of the spec, `protocol.md`, whose properties are proved for **any number of nodes, groups and
chunk indices** and every interleaving, each as an inductive invariant whose conditions Lean's kernel
checks (the SMT solver is not trusted):

- `ClaimWins.lean`: an honest node is never penalised for an ask, "the claim wins" (A1, §4.5);
- `SenderFault.lean`: nor for a chunk that fails level 1 or a malformed HAVE (A1's other two
  penalties, §3, §4.2, §4.3), so A1 holds at every place a node penalises;
- `NoStallTransport.lean`, `NoStallAsk.lean` and `NoStallCount.lean`: no stall (Q1). For any one
  chunk, when the transport has nothing left to do, a node with its block holds every chunk a mesh
  neighbour received, has stopped pulling, or holds that neighbour's offer; when the asking machinery
  has nothing left to do, every such offer is resolved; and, counting in plain Lean, every honest node
  connected to the source stops at K and completes. How the pieces make Q1 is below.

The Quint model next door (`../diffusion.qnt`) checks these properties on three or four nodes.

## The claim wins (`ClaimWins.lean`)

A model of one argument of the spec, §4.5: an honest node is never penalised for asking a peer for a
chunk it has claimed to that peer. With §8.1's live window it holds with no assumption; under the
fallback for groups without a slot, it holds given the bound §8.1 sets on the tombstone's lifetime
(below). The Quint model's monitor for it is `noPenalty`.

`ClaimWins.lean` holds the model, its inductive invariant, the queries that show it is not vacuous,
the known answers, model checks and an audit of the proof. Its header says what is modelled and what
is not: in short, claims (HAVE bits from `mine`), asks, the writer's filter, a link as one ordered
stream of RPCs that a coalescing transport can join, the receiver's IWANT-before-IDONTWANT, claims
that lapse, a group's expiry, its tombstone, the live window and the tombstone's end, and
connections that close; not the chunks themselves, the send window or timers (every lifetime can
end at any time), how a node tells a group's slot, and not the other two reasons for a penalty (a
chunk failing level 1, a malformed HAVE). The queue is a set, so the result holds for any order the
writer picks.

### What it rests on

§4.5's argument and §8.1's tombstone rule, each part a switch in the model (an `immutable` Boolean,
on in the spec), and the fallback's assumption, also a switch:

| switch | rule | where |
|---|---|---|
| `filterAsks` | the writer drops a queued ask for a chunk in `mine` (`held`), of a stop-pulled group or of an expired one | §7.2 |
| `asksFirst` | within one RPC, IWANT is handled before IDONTWANT | §4.1 |
| `inOrder` | one ordered writer per peer: RPCs are handled in the order written | §4.5, §7.2 |
| `expiryInFilter` | the writer's filter also checks expiry (v0.5) | §7.2 |
| `discardAtExpiry` | a group's expiry discards its queued IWANTs (v0.5) | §8.1 |
| `liveWindow` | a group whose slot has left the node's live window is expired, whatever its active lifetime, and its tombstone goes only then | §8.1 |
| `windowForward` | the live window only moves forward, and a group's slot is fixed: its key names it | §8.1, §1 |
| `claimsGoFirst` | the fallback, for groups without a slot, assumed: a node's tombstone for a group goes only once no claim of the group from it is queued, on a stream or held by a peer, as the bound on `TOMBSTONE_TTL` provides | §8.1 |

The invariant holds where `premises`: the first three rules, at least one of the two expiry rules,
and the tombstone rule: the live window, moving only forward, or, without a window, the assumption.

**The tombstone.** Past its active lifetime a node keeps only a group's key and slot, its tombstone
(§8.1). A node's claims of a group outlive the group's expiry: a HAVE still queued leaves after it,
and a peer keeps the claim for `HAVE_TTL`. A node that took the group up again could ask for a chunk
a peer still holds as its claim. v0.5 kept the tombstone "until the seen cache forgets its chunks",
which with the stock seen cache can be at expiry already, and nothing stopped the node from taking
the group up again. The live window closes this for good: a group whose slot has left the window
stays out, so the tombstone can go then, and the proof needs no bound on queues, the transport or
clocks, nor nodes that agree on the window: each node's own window must only move forward, and a
group's slot must be fixed, which its key does (§1): a bid of a later slot that commits the same
descriptor names another group. Without a slot, the fallback keeps the tombstone `TOMBSTONE_TTL` after the expiry; the model has no time,
so the proof assumes what that bound provides, that the tombstone outlives the claims. Two known
answers show what each part prevents. With neither the window nor the assumption an honest node is
penalised with every rule on: the asker's group expires and its tombstone goes while the peer still
holds its claim; the asker takes the group up again and asks. A window that moves back does the
same: the group's slot leaves the window and comes back, as it would for a group named by its group
id alone that a later slot's bid commits again.

### Results (2026-10-23, Veil at `02791b2`)

| check | how | result |
|---|---|---|
| the claim wins, any size | an inductive invariant of ten clauses (`#check_invariants`); 154 verification conditions (eleven for each of thirteen actions and at initialisation), each a theorem Lean's kernel checks (`#gen_theorems`), with the SMT solver's answers rebuilt as proofs, not trusted | **holds**: with the live window, with no assumption; under the fallback, given its bound |
| the audit | every verification condition, derived from the module itself, must be a theorem; no clause may be assumed instead of checked; every theorem the module adds must rest on Lean's own axioms only; any failure fails the build | 154 of 154; none assumed; all 537 theorems rest on `propext`, `Classical.choice` and `Quot.sound` |
| not vacuous | `sat trace`, every rule on: the spec as written (with the window) and the fallback can each hold; an ask queued before its chunk arrived is still queued when the claim reaches the peer; an ask and the claim of its chunk travel in one RPC; with the window, the tombstone gone while a peer still holds the node's claim of a chunk the node no longer has; under the fallback, a group taken up again after its tombstone went, with an ask on its way for a chunk the asker once claimed to that peer | all six found |
| known answers | `sat trace`, every other rule on, with the window: no filter; IDONTWANT first; RPCs out of order; neither expiry rule; neither the window nor the assumption, the tombstone gone while the peer holds the claim; a window that moves back | **a penalty in each** (7, 6, 7, 8, 9 and 9 steps), on two nodes and one chunk |
| a small instance, every state | `#model_check interpreted`: two nodes, one group of one chunk, two RPC positions per link (two RPCs per link over the whole run), every rule on, with the window and under the fallback | no clause violated: 127,504 states with the window, 88,000 under the fallback |

So the filter, IWANT first and in-order handling are each needed, and so is a tombstone rule; of
the two expiry rules v0.5 added (D′) either alone suffices, since the proof holds with one, and with
neither an honest node is penalised: the asker's group expires, `mine` goes with it, and an ask
queued before the chunk arrived passes the filter while the peer, whose group is still alive, holds
the claim. v0.4 had
neither rule (its filter checked `held` and stop-pull, and `discard_queued` ran only at
`drop_group`), so it could penalise an honest node that way. Its lifetimes do not prevent it: a HAVE
queued before the expiry still leaves after it (queued HAVEs survive expiry, in v0.5 too) and
refreshes the peer's claim, whatever `HAVE_TTL` is. It takes an ask that stays queued from before
its chunk arrived until the group expired, at least `GROUP_TTL`, with a HAVE of the chunk leaving
ahead of it.

## The other two penalties (`SenderFault.lean`)

Besides the claim rule, a node penalises a peer for a chunk that fails level 1 (§4.2: "level 1
failures are the sender's") and for a malformed HAVE (§4.3, §8.2: longer than `MAX_HAVE_BYTES`, or
naming an index at or beyond N once the descriptor is known). The model proves that neither falls on
an honest node, with forgers that send anything, a builder that commits an inconsistent code or an
invalid descriptor, and a proposer that signs several blocks for a slot, whose bids commit one group
or different ones. A block is named by its root, so what its bid commits is the same at every node;
a chunk carries a piece (its index, the descriptor, the proof and the data), and `good` stands for
every check of §3 but the block's. Messages are sets, so any order, loss and duplication; expiry,
the window, §8.2's limits and refused deferrals only drop messages or state. A HAVE bit stands for a
bitmap's bit, which covers the length check because an honest bitmap drops its trailing zero bytes
(§2). The header says the rest.

| switch | rule | where |
|---|---|---|
| `gateLevel1` | level 1 before a chunk is stored, forwarded or served | §3 |
| `gateLevel2` | a rebuilt chunk only once level 2 has passed | §3, §4.6 |
| `deferUnknown` | a chunk whose block is not installed waits, and is checked when it installs | §3, §4.2 |
| `namedRoot` | level 1 checks the block the chunk names | §3 |
| `rebuiltRoot` | a rebuilt chunk names a block whose bid commits its group | §4.6 |
| `claimValidated` | a HAVE names only chunks that passed level 1 | §4.2 |
| `descCommitted` | a HAVE is judged by the committed descriptor | §3, §8.2 |

The proof rests on two assumptions about the world: level 1 checks the index against N, and a group
with a piece that passes level 1 has a descriptor that passed `valid_descriptor`, so N is at most
8192 (that an honest builder's does is `../wire/`'s W1). Nine more only keep the traces to worlds
that can happen (a block's bid commits one group and some group, the blocks that commit a group share
its slot, indices start at zero, and so on); the proof was also checked without them.

| check | how | result |
|---|---|---|
| neither penalty on an honest node, any size | an inductive invariant of ten clauses; 200 verification conditions (ten clauses and `doesNotThrow`, for nineteen actions and the initializer), each a theorem Lean's kernel checks, the SMT solver not trusted | **holds**, also with only the two assumptions it rests on |
| the audit | as for the claim rule, the assumptions listed | 200 of 200; none trusted; all 717 theorems rest on `propext`, `Classical.choice` and `Quot.sound` |
| not vacuous | `sat trace`, every rule on: a forger penalised for a chunk, and for a HAVE bit beyond N; a chunk ahead of its block accepted when the block installs; one node accepting chunks under two blocks of a slot whose bids commit the same group, and under two that commit different groups; an inconsistent code's authentic pieces relayed between honest nodes, unpenalised | all seven found |
| known answers | `sat trace`, one rule off, every other on | **an honest node penalised in each**: a relay before level 1 (4 steps); a rebuilt chunk sent before level 2, from an inconsistent code (7); a chunk rejected ahead of its block (4); level 1 against the receiver's own block of the slot (5); a rebuilt chunk naming the slot's other block (10); a HAVE for a chunk on arrival (5); a HAVE judged by a forger's descriptor (6) |

When two blocks of a slot commit a group, the group's chunks name either root, which is part of the
id, and a decoder cannot tell which root the source's chunk at an index it never received names.
What the proof needs is that a rebuilt chunk names a block whose bid commits its group
(`rebuiltRoot`); naming a block whose bid commits another group gets the decoder penalised (its known
answer). Since v0.7 §4.6 says so: a rebuilt chunk names an installed block whose bid commits the
group, and is the source's chunk byte for byte where it names the same root.

## No stall (`NoStallTransport.lean`, `NoStallAsk.lean`, `NoStallCount.lean`)

Q1: **when nothing is left to happen, every honest node connected to the source is complete.** In
three pieces, each proved for any number of nodes; the first two are about any one chunk of the
group, so they hold for each:

- **The transport** (`NoStallTransport`): when it has nothing left to do, a node that has its block
  holds every chunk a mesh neighbour received, has stopped pulling the group, or holds that
  neighbour's offer of the chunk. It models the source's publish, forwarding (pushed or announced,
  any targets, never to the sender or a peer known to hold it), queues that may refuse any entry
  (owed and offered, A′), the writer's cancel and projection (A′), what is owed, announcements
  recorded as offers, the deferred store (refused copies as offers, F7's fix), copies taken in at
  installation, and repair.
- **The asking** (`NoStallAsk`): when it has nothing left to do, every offer to a node that has its
  block is resolved: the node holds the chunk or has stopped pulling. It models one ask in its
  window, the retry, parks from promises that fall due at any time, B′'s last resort, the writer's
  ask filter, the serve limit at its worst, the claim rule's drop, answers cancelled or owed, offers
  before the block kept and asked for at installation (C′), and offers over an IHAVE limit kept and
  asked for by the next heartbeat's retry (v0.7).
- **The counting** (`NoStallCount`, plain Lean): a node stops pulling at its K-th received chunk, the
  source holds all N, and with nothing pending a node that has received K has made its decode claim;
  a node that has not stopped holds only chunks it received. Then, by induction along mesh paths
  from the source, every connected node stops, and, its decode no longer pending, is complete.

Each piece treats what the others do as its **environment**: events at any time, any number of
times, that are not part of its own pending work. The transport's environment: blocks installing,
stop-pull, the decode storing the chunk, HAVEs learned (true, possibly never sent), answers bringing
the chunk. The asking's: offers from honest holders (before the block, kept in the ledger), the chunk
arriving by push, stop-pull, HAVEs learned, blocks installing, and parks from the group's other
chunks (F2's way). How the spec's events fall into the pieces:

| spec event | transport | asking |
|---|---|---|
| publish (§5.1) | `publish` | the source's `install`, `arriveOther`, `stopPull` |
| forward and write a push, an announcement or what is owed (§5.2, §7.2) | `fwd`, `writePush`, `writeIhave`, `writeOwed` | none |
| a chunk arrives with the block (§4.2) | `recvChunk` | `arriveOther` |
| a chunk arrives ahead of the block: deferred, or refused and offered (§4.2) | `recvChunk` | none, or `offerEarly` |
| an announcement arrives (§4.4) | `recvIhave` | `offerEarly` before the block, else `offerAsk`, `offerInWindow`, `offerParked`, `offerParkedArm`; over an IHAVE limit `offerHeldBack` (by the loop, from an unparked offerer; by §4.4's bitmap reading, from any) |
| an ask written, handled, answered, owed; an answer written (§4.1, §4.5, §7.2) | none | `writeAsk`, `recvAsk`, `owedToQueue`, `writeAns` |
| an answer arrives (§4.2) | `answerArrives` | `recvAns` |
| a window ends, a retry (the heartbeat's too, for what an IHAVE limit held back, §6.4), a promise falls due, the last resort (§6.1) | none | `windowElapse`, `retry…`, `promiseDue`, `lr…`; another chunk's promise: `parkOther` |
| a HAVE arrives (§4.3) | `learnClaim` | `learnClaim` |
| the block installs: its handler takes the deferred copies in, then asks for the ledger (§3, §4.2) | `install`, then `resume` | `installTakenIn` if a copy of the chunk was deferred, `installStopped` if the copies brought the group to K, else `install` |
| the decode claim at K; the decode returns, repair (§4.6) | `stopPull`; `rebuild`, `repair` | `stopPull`; `arriveOther` |

The shared relations mean the same in both pieces: holding the chunk (`holds`, `got`), stop-pull,
claims learned, the block; and a node's offers, except that before its block the asking keeps them
apart, in `ledger`, merged into `offered` when the block installs (the transport's `offered` is the
asking's `ledger` until then). A spec state in which nothing is pending but lifetimes has every
piece's `work` false for every chunk: each piece's pending work is a pending event of the spec (a
queued entry, an RPC in flight, a timer armed, a deferred copy whose block is installed, something due
or owed). The counting's hypothesis that a node with K received chunks has stopped is what excludes a
decode claim still due.

**Kernel-checked**: each piece's inductive invariant, and the counting. **Found by the SMT solver**,
not kernel-checked (Veil keeps no proof of a trace): the non-vacuity traces and the known answers.
**By inspection**, as for every model here: each piece's correspondence to the spec, and the table
above. **Assumed**: honest nodes; one block (no equivocation) that every node installs; no
disconnects; every connection a mesh link (so heartbeat gossip, which goes outside the mesh, reaches
none); lifetimes that outlast diffusion; a send window that lets every queue drain (W2, W3, checked on
small instances only); an honest builder's code; and the one group admitted by §8.2's limits (so a
copy the deferred store refuses counts as its sender's offer).

**F11, found here and closed in v0.7.** Up to v0.6, §8.2 let a node handle at most
`MAX_IHAVE_MESSAGES` (4096) IHAVE-bearing RPCs per peer and heartbeat and ignore the rest. A node
announces one chunk per IHAVE (§5.1, §5.2), so a plain group of more than 4096 chunks (up to
`MAX_PLAIN_CHUNKS`, 8192) announced to a mesh peer within a heartbeat exceeded it, and nothing
guarantees an ignored announcement is offered again: a node announces a chunk when it forwards it,
and again only when an offer of it is owed (a push or announcement its queue refused, or a push
projection skipped) or when it forwards a copy it receives after rebuilding the chunk; it does not
learn of the drop, and heartbeat gossip goes only outside the mesh (§6.4). An example: a source
with twelve leaf neighbours and a plain group of 8192 chunks; the leaf has no other neighbour that
could offer it the chunks it ignored, so it never completes, as a plain group needs every chunk.
v0.7 records every announcement, an IHAVE over either of gossipsub's IHAVE limits too, and holds
back what it would ask in reply to the next heartbeat, which runs the retry for it (§4.4, §6.4); the
limits' values are the client's. In the transport this is the rule `ihaveHandled`, whose known
answer `ka_ihave_dropped` shows the loss without it; in the asking, `offerHeldBack` (the offer
recorded, the retry armed), whose known answer `ka_held_back_lost` shows the offer never asked for
without the heartbeat's retry.

| piece | proof | traces | cost |
|---|---|---|---|
| transport | 144 of 144 conditions, 577 theorems | 4 non-vacuity (a push delivered; an announcement recorded as an offer; a copy deferred and taken in; a refused copy offered), 4 known answers (F1: a skipped push counted, offered to nobody; a refused push lost; F7: a refused copy lost; F11: an announcement ignored by the receiver's limit) | 2.2 minutes, 2.9 GB |
| asking | 312 of 312 conditions, 932 theorems | 5 non-vacuity (an offer answered; an offerer parked by another chunk, asked once more by the last resort; an offer before the block asked for at installation; an offer over an IHAVE limit asked for by the heartbeat's retry; one from a parked offerer, asked once more by the last resort the heartbeat's retry arms), 4 known answers (F2: without B′ an offerer parked by another chunk is never asked; answers lost twice without owed answers; an offer before the block never asked without the ledger; an offer over an IHAVE limit never asked without the heartbeat's retry) | 3.9 minutes, 7.2 GB |
| counting | two theorems | none | seconds |

All conditions are theorems Lean's kernel checks, on `propext`, `Classical.choice` and `Quot.sound`
only, the audits derived from each module; the traces are cvc5's. A first, whole model of the per-link step in one Veil
module (35 fields, 26 actions) held with the SMT solver trusted but was too large for Veil to finish;
the pieces replace it.

## Running it

Veil is the 2.0 pre-release, pinned to a commit in `lakefile.lean`, and every dependency by commit
in `lake-manifest.json`; `lean-toolchain` names the Lean release. With
[elan](https://github.com/leanprover/elan) installed, and the system dependencies Veil's README
lists, from this directory:

```sh
lake build Veil      # once: Veil and its dependencies (about 4 minutes on 8 cores)
lake build           # the models: queries, model checks, proofs, theorems, audits (about 4 minutes)
```

A clean `lake build` means every check passed: a clause that fails, a query without a trace, a
violation and a failed audit are errors. Packages and build outputs go to `.lake` (about 1.5 GB).
Veil checks as many conditions at once as `getconf _NPROCESSORS_ONLN` reports, each with its own SMT
run; a `getconf` placed first in `PATH` that prints a smaller number for `_NPROCESSORS_ONLN` caps it
(two at once keep every model here under 8 GB). For larger instances `#model_check compiled` builds
a native checker, which needs `clang`, `lld`, `libc++-dev` and `libc++abi-dev`: on the window's
instance above it finds the same 127,504 states in about 80 seconds with its build.

## Veil 2.0, as met here

A pre-release: these cost time, and each has its workaround in the model.

- A relation binder names one variable: `(a : node) (b : node)`, not `(a b : node)` (the error
  says only "unable to extract type from binder").
- `sat trace` queries fail to translate (`cannot translate Type`, or a lambda SMT-LIB lacks) on a
  higher-order choice (`let s : (group → index → Bool) :| …`), on `decide $ …` over an update's
  quantified variables, and on a ghost relation read after such an update. `#check_invariants`
  handles all three. Hence one-part writes, Bool operators in updates, and conditions on the state
  before the updates.
- `set_option veil.smt.trust false` works at file level, not as `set_option … in #check_invariants`;
  `#check_invariants` alone adds no theorem, `#gen_theorems` does.
- The model checker's memory grows fast: two nodes with two chunks and three positions filled
  24 GB in 50 minutes interpreted, and in 4 minutes compiled (on an earlier version of the model).
- `lake env lean` on a loose file does not load cvc5; pass the plugins listed in
  `.lake/build/ir/ClaimWins.setup.json` (`--plugin=…`) to check one by hand.
- A relation with six arguments breaks every verification condition ("Tactic `assumption`
  failed"), where one with five works: hence `SenderFault`'s `piece`, which folds a chunk's index
  and contents into one argument. An `assumption` that is a bare relation fails with "type
  expected"; give it a connective.
- `veil module` sets `maxRecDepth` to 1024 and `maxHeartbeats` to 500000, whatever is set above it;
  a long trace's simplification needs more depth, so the `NoStall` pieces set it after the
  `veil module` line.
- A state field must not share a name with Veil's own locals: a relation `has` (Veil binds its
  assumptions as `has`) breaks `#gen_spec` with a type mismatch, and every check after it.
- Veil's cost grows with the state's width: a 35-field model did not finish `#gen_spec` in 30
  minutes, while the pieces of 15 and 16 fields finish in under three. Splitting a model, each piece
  with its environment, is the remedy.
- Where the SMT solver answers unsat but lean-smt cannot rebuild the proof ("no witness provided"),
  `set_option veil.solver "grind+smt"` tries Lean's `grind` first, kernel-checked as it is; and an
  action whose conditions nest quantifiers proves more easily split into one action per case.
