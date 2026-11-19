# SEACAST in Veil: properties at any size

Models of the spec, `protocol.md`, whose properties are proved for **any number of nodes, groups and
chunk indices** and every interleaving. In each Veil model the safety property is an inductive
invariant whose conditions Lean's kernel checks (the SMT solver is not trusted), and Q3's are
temporal theorems the kernel checks too, their one-step facts proved by Lean's `grind` without the
solver; the plain-Lean files are theorems.

- `ClaimWins.lean`: an honest node is never penalised for an ask, "the claim wins" (A1, §4.5);
- `SenderFault.lean`: nor for a chunk that fails level 1 or a malformed HAVE (A1's other two
  penalties, §3, §4.2, §4.3), so A1 holds at every place a node penalised in v0.8 (v0.10 adds one,
  below);
- `NoStallTransport.lean`, `NoStallAsk.lean` and `NoStallCount.lean`: no stall (Q1). For any one
  chunk, when the transport has nothing left to do, a node with its block holds every chunk a mesh
  neighbour received, has stopped pulling, or holds that neighbour's offer; when the asking machinery
  has nothing left to do, every such offer is resolved; and, counting in plain Lean, every honest node
  reachable from the source along mesh links stops at K and completes. The mesh may change on the
  way (peers join and leave it, connections close), with F9's rule, `protocol.md` §5.4 since v0.8: a
  peer that joins the mesh is announced what the node holds. How the pieces make Q1 is below. The
  counting also gives Q1 with a builder that releases only K of the N chunks, with a source that
  drops out, and with nodes that never install the block.
- `NoStallEquiv.lean`: the asking piece under equivocation, with F6's two rules, §4.2's ties and
  §6.1's rule against a second ask of a peer at once since v0.8, in place of `NoStallAsk.lean` when
  a proposer signs two blocks for the slot: Q1 then holds for every honest
  node reachable from the source through nodes that installed the builder's block, given that
  every honest copy, rebuilt ones included, names that block (a node that relabels chunks under the
  other block's root breaks this: `protocol.md` §4.6 lists the gap as open).
- `NoStallAskAdv.lean`, `NoStallTransportAdv.lean` and `NoStallEquivAdv.lean`: the per-chunk pieces
  with malicious peers. With the counting through honest nodes, Q1 holds for every honest node the
  source reaches along links between honest nodes, into nodes that installed the block, whatever the
  other peers do, relabelled copies excluded. `NoStallEquivAdv.lean` is v0.8's asking among them,
  and shows two findings: F13, closed in v0.8, and F14, which `protocol.md` §6.1 leaves open.
- `Agreement.lean` (plain Lean): level 2 is all or none, a check that succeeds recovers the bytes the
  root commits, and two honest nodes never deliver different payloads for a group, under the codec's
  assumptions (below).
- `QuietRanking.lean` (plain Lean) and the theorems `quiet` of `NoStallTransport.lean`,
  `NoStallEquiv.lean`, `NoStallTransportAdv.lean` and `NoStallEquivAdv.lean`: a run goes quiet (Q3).
  With finitely many nodes and weak fairness, in every run whose environment eventually stops (with
  malicious peers, their actions included), the transport and v0.8's asking (with `NO_REASK_OPEN`)
  eventually have nothing left to do, for good (with malicious peers, the honest nodes' machinery).

The Quint model next door (`../diffusion.qnt`) checks the claim rule (A1's `noPenalty`), Q1 and Q3
on three or four nodes, and not agreement or integrity (`../README.md` lists its checks).

**The models are of v0.8's rules** (`NoStallAsk.lean` and `NoStallAskAdv.lean` have v0.7's asking,
which `NoStallEquiv.lean` and `NoStallEquivAdv.lean` take to v0.8's). Each header names the sections
and the version it follows. `protocol.md` has changed since, and the models do not have these
changes; whether each result carries over to them is not checked:
- **v0.9, the source's announcements at the acknowledgement** (§5.1): the source announces a chunk,
  and its HAVE names it, at the chunk's acknowledgement. In the transport model publishing makes the
  source's forwarding to each mesh peer due, a push or an announcement, as in v0.8. Since v0.10.3
  that is the timing of `SOURCE_OFFERS = PUBLISH`, with any choice of the chunk's push targets and
  without the source's HAVE growing at each chunk's first write (`origin_written`); the default,
  `ACK`, is not modelled.
  v0.9's §7.3, on what the transport below the writer should hold, is not modelled either: the
  models' queues may refuse any entry, and drain.
- **v0.10, four rules for what waits for its block** (§4.2, §6.1, §8.1):
  - a deferred copy beyond its sender's limit of unknown groups is ignored;
  - at installation, a tied index the group does not have is dropped;
  - when a group's count becomes known, what named an index at or beyond it goes;
  - what waits for a root that never installs goes when its slot leaves the live window or its
    group expires.
- **v0.10, level 1 checks the slot** (§3): it rejects a copy whose slot is not its block's.
- **v0.10, IHAVE entries and bitmaps checked** (§4.4, §8.2): an entry is a bitmap or a chunk's valid
  id (`valid_id`), anything else ignored, and a bitmap is held to a HAVE's limits. One naming an
  index at or beyond the group's count, once its descriptor is known, counts against its sender: a
  penalty `SenderFault.lean` has for a HAVE only. §4.4 also leaves open one chunk under two keys,
  where a sender can be asked once per key; in the models a chunk has one key.
- **v0.10, the node's own order of announcers** (§6.1, §8.1): the announcers beyond a chunk's
  ordered list are tried in an order keyed by a secret the node draws. The models let the retry ask
  any unparked announcer, so they cover every order.
- **v0.10.3, the constants in three kinds** (§8.3), with reference values for gossipsub's two IHAVE
  limits: no rule changed, and the models take those limits as any values. `GOSSIP_RETRANSMISSION`
  is now a bound, at least 3. The v0.7 asking models answer a peer's first eligible ask, and any
  later one or not, as the run chooses; the equivocation models the first three, and any later one
  or not; so each covers every value the bound allows.
- **v0.10.4** (§4.1, §5.1, §5.4):
  - an IDONTWANT entry that is not a HAVE bitmap is kept as stock gossipsub keeps an id, where every
    entry went to `on_have`. The models have no stock ids as state; `NoStallAskAdv.lean`'s header
    reads an adversary's stock IDONTWANT, by inspection, as changing only its own connection;
  - §5.1 names open a chunk that is never acknowledged, at `ACK`, which the models do not have
    (above);
  - §5.1 and §5.4 say what heartbeat gossip tells of the source outside the mesh; the models follow
    mesh links only.

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

### Results (Veil `v4.35.0`)

| check | how | result |
|---|---|---|
| the claim wins, any size | an inductive invariant of ten clauses (`#check_invariants`); 154 verification conditions (eleven for each of thirteen actions and at initialisation), each a theorem Lean's kernel checks (`#gen_theorems`), with the SMT solver's answers rebuilt as proofs, not trusted | **holds**: with the live window, with no assumption; under the fallback, given its bound |
| the audit | every verification condition, derived from the module itself, must be a theorem; no clause may be assumed instead of checked; every theorem the module adds must rest on Lean's own axioms only; any failure fails the build | 154 of 154; none assumed; all 601 theorems rest on `propext`, `Classical.choice` and `Quot.sound` |
| not vacuous | `sat trace`, every rule on: the spec as written (with the window) and the fallback can each hold; an ask queued before its chunk arrived is still queued when the claim reaches the peer; an ask and the claim of its chunk travel in one RPC; with the window, the tombstone gone while a peer still holds the node's claim of a chunk the node no longer has; under the fallback, a group taken up again after its tombstone went, with an ask on its way for a chunk the asker once claimed to that peer | all six found |
| known answers | `sat trace`, every other rule on, with the window: no filter; IDONTWANT first; RPCs out of order; neither expiry rule; neither the window nor the assumption, the tombstone gone while the peer holds the claim; a window that moves back | **a penalty in each**, on two nodes and one chunk |
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
its slot, indices start at zero, and so on); an earlier check, not this build, proved it without
them.

| check | how | result |
|---|---|---|
| neither penalty on an honest node, any size | an inductive invariant of nine clauses; 200 verification conditions (the nine and `doesNotThrow`, for nineteen actions and the initializer), each a theorem Lean's kernel checks, the SMT solver not trusted | **holds**; in an earlier check, not this build, also with only the two assumptions it rests on |
| the audit | as for the claim rule, the assumptions listed | 200 of 200; none trusted; all 799 theorems rest on `propext`, `Classical.choice` and `Quot.sound` |
| not vacuous | `sat trace`, every rule on: the premises can all hold; a forger penalised for a chunk, and for a HAVE bit beyond N; a chunk ahead of its block accepted when the block installs; one node accepting chunks under two blocks of a slot whose bids commit the same group, and under two that commit different groups; an inconsistent code's authentic pieces relayed between honest nodes, unpenalised | all seven found |
| known answers | `sat trace`, one rule off, every other on | **an honest node penalised in each**: a relay before level 1; a rebuilt chunk sent before level 2, from an inconsistent code; a chunk rejected ahead of its block; level 1 against the receiver's own block of the slot; a rebuilt chunk naming the slot's other block; a HAVE for a chunk on arrival; a HAVE judged by a forger's descriptor |

When two blocks of a slot commit a group, the group's chunks name either root, which is part of the
id, and a decoder cannot tell which root the source's chunk at an index it never received names.
What the proof needs is that a rebuilt chunk names a block whose bid commits its group
(`rebuiltRoot`); naming a block whose bid commits another group gets the decoder penalised (its known
answer). Since v0.7 §4.6 says so: a rebuilt chunk names an installed block whose bid commits the
group (since v0.8, the block the chunks it was rebuilt from name, or one of them where they name
several), and is the source's chunk byte for byte where it names the same root.

## No stall (`NoStallTransport.lean`, `NoStallAsk.lean`, `NoStallCount.lean`)

Q1: **when nothing is left to happen, every honest node reachable from the source along the mesh it
then has is complete**, the links followed from each node to the peers in its mesh, to which it
forwards. In three pieces, each proved for any number of nodes; the first two are about any one
chunk of the group, so they hold for each:

- **The transport** (`NoStallTransport`): when it has nothing left to do, a node that has its block
  holds every chunk a mesh neighbour received, has stopped pulling the group, or holds that
  neighbour's offer of the chunk. It models the source's publish, forwarding (pushed or announced,
  any targets, never to the sender or a peer known to hold it), queues that may refuse any entry
  (owed and offered, A′), the writer's cancel and projection (A′), what is owed, announcements
  recorded as offers, the deferred store (refused copies as offers, F7's fix, which since v0.8 the
  ties of §4.2 make at the block's installation), copies taken in at installation, repair, and a
  mesh that changes: peers join it (by a GRAFT, sent or accepted, and are then announced what the
  node holds: §5.4, F9's rule) and leave it (a PRUNE), and
  connections close, with what is queued, owed or in flight on them and the state kept per
  connection (§8.1). The mesh is directed, as gossipsub's is, and starts empty.
- **The asking** (`NoStallAsk`): when it has nothing left to do, every offer to a node that has its
  block is resolved: the node holds the chunk or has stopped pulling. It models one ask in its
  window, the retry, parks from promises that fall due at any time, the last resort, the writer's
  ask filter, the serve limit at its worst, the claim rule's drop, answers cancelled or owed, offers
  before the block kept and asked for at installation (C′), offers over an IHAVE limit kept and
  asked for by the next heartbeat's retry (v0.7), and connections that close: what is between the
  two nodes is lost, their promises close, and the state kept per connection goes, the last-resort
  counts with it; parks stay (§6.1, §8.1).
- **The counting** (`NoStallCount`, plain Lean): a node stops pulling at its K-th received chunk,
  the source has stopped, and with nothing pending a node that has received K has made its decode
  claim; a node that has not stopped holds only chunks it received. Then, by induction along the
  quiet state's mesh paths from the source, every connected node stops, and, its decode no longer
  pending, is complete.

Each piece treats what the others do as its **environment**: events at any time, any number of
times, that are not part of its own pending work. The transport's environment: blocks installing,
stop-pull, the decode storing the chunk, HAVEs learned (true, possibly never sent), answers bringing
the chunk, and the mesh changing. The asking's: offers from honest holders (before the block, kept in
the ledger; a new connection's resync among them), the chunk arriving by push, stop-pull, HAVEs
learned, blocks installing, parks from the group's other chunks (F2's way), and connections closing.
How the spec's events fall into the pieces:

| spec event | transport | asking |
|---|---|---|
| publish (§5.1) | `publish` | the source's `install`, `arriveOther`, `stopPull` |
| forward and write a push, an announcement or what is owed (§5.2, §7.2) | `fwd`, `writePush`, `writeIhave`, `writeOwed` | none |
| a chunk arrives with the block (§4.2) | `recvChunk` | `arriveOther` |
| a chunk arrives ahead of the block: deferred, or refused and its sender an offer at installation (§4.2's tie) | `recvChunk` | none, or `offerEarly` |
| an announcement arrives (§4.4) | `recvIhave` | `offerEarly` before the block, else `offerAsk`, `offerInWindow`, `offerParked`, `offerParkedArm`; over an IHAVE limit `offerHeldBack` (by the loop, from an unparked offerer; by §4.4's bitmap reading, from any) |
| an ask written, handled, answered, owed; an answer written (§4.1, §4.5, §7.2) | none | `writeAsk`, `recvAsk`, `owedToQueue`, `writeAns` |
| an answer arrives (§4.2) | `answerArrives` | `recvAns` |
| a window ends, a retry (the heartbeat's too, for what an IHAVE limit held back, §6.4), a promise falls due, the last resort (§6.1) | none | `windowElapse`, `retry…`, `promiseDue`, `lr…`; another chunk's promise: `parkOther` |
| a HAVE arrives (§4.3) | `learnClaim` | `learnClaim` |
| the block installs: its handler takes the deferred copies in, then asks for the ledger (§3, §4.2) | `install`, then `resume` | `installTakenIn` if a copy of the chunk was deferred, `installStopped` if the copies brought the group to K, else `install` |
| the decode claim at K; the decode returns, repair (§4.6) | `stopPull`; `rebuild`, `repair` | `stopPull`; `arriveOther` |
| a peer joins a node's mesh, by a GRAFT sent or accepted, and is announced what the node holds (§5.4) | `join` | its announcement arrives as any does |
| a peer leaves a node's mesh (a PRUNE) | `leave` | none |
| a connection closes (§8.1) | `close` | `close` |

The shared relations mean the same in both pieces: holding the chunk (`holds`, `got`), stop-pull,
claims learned, the block; and a node's offers, except that before its block the asking keeps them
apart, in `ledger`, merged into `offered` when the block installs (the transport's `offered` is the
asking's `ledger` until then). A spec state in which nothing is pending but lifetimes has every
piece's `work` false for every chunk: each piece's pending work is a pending event of the spec (a
queued entry, an RPC in flight, a timer armed, a deferred copy whose block is installed, something due
or owed). The asking's `retryArmed` stands for the retry's timer or the next heartbeat's retry of
what an IHAVE limit held back (§6.4), and a push that projection skips is owed only while its peer
is in the mesh (§5.2's `unpush`), as in the spec. The counting's hypothesis that a node with K
received chunks has stopped is what excludes a decode claim still due. With `NoStallEquiv` as the
asking piece, the transport's `installed` is the builder's block; its offers before that block are
the asking's offers once the other block has opened the gate, and its ledger before; and a refused
copy's offer is, with `ROOT_TIED`, a tie that the builder's block's installation makes an offer.

**Kernel-checked**: each piece's inductive invariant, and the counting. **Found by the SMT solver**,
not kernel-checked (Veil keeps no proof of a trace): the non-vacuity traces and the known answers.
**By inspection**, as for every model here: each piece's correspondence to the spec, and the table
above. **Assumed** (the counting's corollaries and the models with malicious peers, below, drop
parts of it): honest nodes; one block that every node installs (`NoStallEquiv` drops this: at
most two blocks for the slot, both committing the group, every honest copy naming the builder's
block, rebuilt ones included, and Q1 for the nodes reachable from the source through nodes that
installed that block); no traffic outside the mesh (heartbeat gossip, §6.4, and the source's stripes,
§5.1, are left out); lifetimes
that outlast diffusion; a send window that lets every queue drain (W2, W3, checked on small
instances only); an honest builder's code; and the one group admitted by §8.2's limits (so a copy
that waits always ties its sender, §4.2).

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

**F9, open in v0.7 and closed in v0.8: its rule proved here.** Without it, nothing guarantees that a new connection is
offered again what the old one lost (`../README.md`, F9): offers come from announcements, which
follow a chunk's arrival, and a closed connection takes with it what was queued, owed or in flight on
it (§8.1). The same gap opens without a close, for a peer that joins a node's mesh after the node
forwarded the chunk: the Quint model, in which every connection is a mesh link, could not show it.
Heartbeat gossip may announce the chunk on a connection before it joins the mesh, and a later copy
may be forwarded, but neither need happen (the gossip goes to a sample of the peers outside the
mesh, for three heartbeats); the models leave both out. The rule, §5.4, moves the resync of the
Quint model's `RESYNC_ON_CONNECT` from the connection to the mesh: a peer that joins a node's mesh,
by a GRAFT either way, is announced what the node holds of each live group, minus what the node
pushed it and what it claimed. A closed connection leaves the mesh, so a reconnection is announced
again once the two join each other's mesh again; a reconnection whose peers never graft each other
gets no resync, where `RESYNC_ON_CONNECT` would have announced on it. What is proved is about the
quiet state's mesh, in which such peers are not neighbours. In the transport the rule is
`resyncOnJoin`, with two known answers without it: `ka_rejoin_lost` (a close with a push of the chunk
queued, the peer back in the mesh, nothing offered) and `ka_late_join` (a peer that joins after the
publish). In the asking, a close loses what is between the two nodes and resets the state kept per
connection, as §8.1 has it, and the proof needs the last-resort count to go with the connection
(`countsReset`): kept, the last resort's ask lost with the connection is never made again
(`ka_counts_kept`).

**F6, open in v0.7 and closed in v0.8: its rules proved here** (`NoStallEquiv.lean`). A proposer that signs
two blocks for one slot may put the same bid in both, so both commit the group. A node that installs
the other block asks, since its bid commits the group, but every honest chunk names the builder's
block, so a copy waits for that block, kept or refused; the node may switch to the builder's block
later. Before the switch the providers' answers wait or are refused, their promises fall due and
park them, the last resort is spent on them, and so are a provider's three answers per chunk and
connection (`GOSSIP_RETRANSMISSION`); after the switch the node can stall (`../README.md`, F6). The
rules: `ROOT_TIED` (§4.2's ties), under which a copy that waits ties its sender, closes its promise
and keeps it from being asked for the index until the root it names installs, whose installation
lifts the sender's park and last-resort count and makes it an offer again; and `NO_REASK_OPEN`
(§6.1), no ask to a peer while an earlier ask of the chunk to it is outstanding, queued or promised. `NoStallEquiv` is
the asking piece with the gate (a block whose bid commits the group: asks are allowed) split from the
builder's block (which a copy needs to validate), both rules as switches, and the asks to a peer
numbered (the first, second, third and any later one), so that two asks in flight to one peer are
two and a provider's answers are counted. The stages of `NoStallAsk.lean` are sets, harmless there,
where the serve limit is at its worst, but they would hide F6's second form. The result: when the
asking is done, a node that has installed the builder's block holds every offered chunk or has
stopped pulling, also when it installed the other block first, and with connections closing. At its
core, before the builder's block a provider is asked at most twice, the second time by the last
resort, so its third answer is left for after the switch (`two_before`), and the third ask, made
only with that block, is answered (`third_answered`). Known answers: without `ROOT_TIED` the switch
leaves every announcer parked and asked once more, with nothing on its way, so no ask follows (F6's
first form); without `NO_REASK_OPEN` a provider is asked a third time before the switch, the bound
F6's second form breaks (its stall, some 30 steps, is the Quint model's); and the last-resort counts
kept across a close. With `NoStallEquiv` in place of `NoStallAsk`, Q1 holds for the honest nodes
reachable from the source through nodes that installed the builder's block, along whom the counting
runs (`every_installed_reachable_node_completes`): a node that installs only the other block cannot
validate the chunks, so nothing reaches a node behind it. This rests on every honest copy naming the
builder's block, rebuilt ones included, which the models assume. v0.7's §4.6 let a rebuilt chunk
name either installed block whose bid commits the group: a node that installed both could rebuild a
chunk naming the other block, which waits for good at a neighbour with only the builder's, while its
sender, which counted the push, sends nothing more for the index. Since v0.8, §4.6 has a rebuilt
chunk name the block the chunks it was rebuilt from name, where they all name one: the source
publishes under one block, and forwarding and the rule keep it, so among honest nodes every copy
names the builder's block, and the case where a node's chunks name several, in which §4.6 lets it
name any one of them, does not arise (A1's model of rebuilt chunks needs only that the block named
commit the group, which the rule keeps). That holds while no node relabels a chunk: a node that
puts the other block's root in a chunk makes an authentic copy, which honest nodes on that block
forward and rebuild from, and a node behind them with only the builder's block can then stall;
`protocol.md` §4.6 lists this gap, F12, as open, with its options. That argument is by inspection,
not in the models.

| piece | proof | traces | the build |
|---|---|---|---|
| transport | 200 of 200 conditions, 922 theorems | 6 non-vacuity (a push delivered; an announcement recorded as an offer; a copy deferred and taken in; a refused copy offered; the chunk announced again to a peer back in the mesh after a close lost a queued push; and to a peer that joined after the publish), 6 known answers (F1: a skipped push counted, offered to nobody; a refused push lost; F7: a refused copy lost; F11: an announcement ignored by the receiver's limit; F9: without the resync, nothing offers the chunk to a peer back in the mesh after a close lost a queued push, nor to a late joiner) | 3.6 minutes |
| asking | 378 of 378 conditions, 1143 theorems | 6 non-vacuity (an offer answered; an offerer parked by another chunk, asked once more by the last resort; an offer before the block asked for at installation; an offer over an IHAVE limit asked for by the heartbeat's retry; one from a parked offerer, asked once more by the last resort the heartbeat's retry arms; an ask lost with its connection, the announcer's offer on the new one asked for by the retry), 5 known answers (F2: without the last resort an offerer parked by another chunk is never asked; answers lost twice without owed answers; an offer before the block never asked without the ledger; an offer over an IHAVE limit never asked without the heartbeat's retry; the last-resort count kept across a close, the ask it counted lost with the connection never made again) | 4.8 minutes |
| asking, under equivocation | 704 of 704 conditions, 1913 theorems | 6 non-vacuity (an offer answered; on the other block, an answer that waits ties its sender and closes its promise; a node on the other block with a tied sender switches, the sender is asked and the chunk validates; the last resort; the ledger; an ask lost with its connection, the announcer asked afresh on the new one), 5 known answers (without `ROOT_TIED`, at the switch every announcer parked and asked once more with nothing on its way; without `NO_REASK_OPEN`, a third ask to a provider before the switch; without the last resort; without the ledger; the last-resort counts kept across a close) | 25 minutes |
| counting | twelve theorems and the lemma `count_mono` they use, two of the twelve known answers (below) | none | a second |

"The build" is Lake's time for the module in one build of the whole library, beside the other
modules (below, "Running it").

The transport's and the asking under equivocation's conditions include those of Q3's `stutter`
action, and the latter's those of `retryParkedArm` (below, "A run goes quiet"); their theorems
include Q3's proofs. All conditions are theorems Lean's kernel checks, on `propext`,
`Classical.choice` and `Quot.sound` only, the audits derived from each module; the traces are
cvc5's. A first, whole model of the per-link step in one Veil module (35 fields, 26 actions) held
with the SMT solver trusted but was too large for Veil to finish; the pieces replace it.

### Delivers even if …

The counting's hypotheses are the per-link step and two facts about stopping, so three more cases
follow from it without a new Veil model. Each theorem below is stated for any node type, mesh, N
and K, and takes the per-link step (`link`), the two stopping facts (`stopped_has_K`,
`K_has_stopped`) and, where it concludes completion, the decode's outcome (`decoded`), as the main
theorem does:
- **A builder that releases only K of the N chunks** (`completes_from_K_chunks`): in place of the
  source's having stopped, the hypothesis is that the source has received at least K distinct
  chunks (`K ≤ count (rcv src)`; in the transport, `publish` sets the source's `rcv`); then every
  node reachable from the source along the mesh is complete. A chunk the source withholds has its
  own per-link step, by inspection: the transport piece with no source (`one_source` allows none),
  or with the source publishing it to the mesh it has, possibly none.
- **A source that drops out** (`stops_from_holders`, `completes_from_holders`): for a node n and a
  set S of at least K distinct chunks (`K ≤ count S`), where for each chunk of S some node that
  reaches n along the mesh has received it or has stopped (`holder`), n has stopped, and with
  `decoded` is complete. The source need not be among those nodes, nor any one of them have received
  K. `received_or_stopped` is the step to it: along the mesh from a node that received a chunk,
  every node has received it or has stopped. `completes_from_holders_installed` is the same with the
  mesh restricted to links into nodes that installed the block (`inst`), `holder`'s paths included,
  and `link` needed only for those links.
- **Nodes that never install the block**: `every_installed_reachable_node_completes`, with `inst`
  the nodes that installed it, and the source's having stopped (`source_stopped`), as the main
  theorem has. The one-block pieces' per-link steps hold for any receiver that installed the block
  and assume nothing of the others.

Two known answers show the new hypotheses needed, each an instance where every other hypothesis of
`stops_from_holders` holds: without `holder` (two nodes, no mesh link, one chunk received by the
first, K = 1), the second has not stopped (`holder_needed`); with fewer than K distinct chunks (one
link, both nodes holding the same one of the two needed, K = 2), the receiver has not stopped
(`enough_needed`).
That the transport lets the source close its connections and leave every mesh at any time, keeping
the copies deferred at receivers, is the transport piece's (`close`, `leave`), and the
correspondence is by inspection.

## With malicious peers (`NoStallAskAdv.lean`, `NoStallTransportAdv.lean`, `NoStallEquivAdv.lean`)

Copies of the per-chunk pieces with adversaries (`adv`, any set of nodes but the source), part of the
environment, and the counting through honest nodes (`every_honest_reachable_node_completes`):
**when no honest node has anything left to do, every honest node the source reaches along links
between honest nodes, into nodes that installed the block, is complete, whatever the other peers
do.**
- **In the transport** an adversary sends authentic copies only of a chunk it holds: a copy that is
  not the committed piece fails level 1, and one naming a root that never installs waits; either has
  an id of its own (§2), so it neither displaces an authentic copy nor makes one look seen. It
  announces and claims anything, and joins, leaves and closes as every node may.
- **In the asking** it offers whether it holds the chunk or not, claims anything, asks honest nodes
  for it (`advAsk`), and answers or not. Honest nodes' offers go to honest receivers: an adversary's
  own asking is not modelled, since nothing of an honest node depends on it.
- **"Nothing left to do" counts honest nodes' pending events only:** an ask that waits at an
  adversary for good does not keep a state from being quiet. The invariants about claims and offers
  hold of honest peers.
- **What the adversary's powers stand for** (the stock per-id IDONTWANT, asks by full id, the offer
  list's 16 announcers, the per-peer limits, the send window) is in `NoStallAskAdv.lean`'s header,
  by inspection.

`NoStallAskAdv.lean` has v0.7's asking. Its known answer is the last-resort count kept per chunk
instead of per announcer (`ka_count_per_chunk`, the case §6.1's Rationale names): the last resort is
spent on an adversary that announced first, and an honest announcer parked by another chunk is never
asked again. Non-vacuity: an honest node's ask to an adversary, left in flight in a quiet state; in
the transport, a false claim and an adversary's offer left in a quiet state; and a control for the
known answer, the last resort going on from the adversary to the honest announcer.

**v0.8's asking with adversaries** is `NoStallEquivAdv.lean`: `NoStallEquiv.lean` with the same
adversaries and §4.2's ties by root. An adversary's waiting copy ties it to the builder's root before
that block installs, released by the installation, or at any time to another root, which the
builder's installation leaves: released by the proposer's other block's installation, dropped with
the adversary's offers where its bid commits another group (`drop_tie`), or kept for good. The
invariants about a provider's asks before the builder's block, and that the last-resort count goes
with an offer, are for honest providers. Relabelled copies are excluded: every copy an honest node
can take in names the builder's block, as the honest model assumes.

**F13: dropped offers must take their asks with them.** Where a tie is dropped, or an adversary's
offers expire (§8.1's 30 s after its last offer of the group, at any time here, since it chooses when
it last offers), its offers go. If its ask still waits in the queue, the ask is written once the
offers are gone, the sender's next offer is recorded with nothing scheduled, and while its promise
runs the last resort for a parked honest announcer returns at once: the asking stalls
(`ka_drop_keeps_asks`, `ka_expiry_keeps_asks`; with the ask written just before the expiry, its
promise does the same, `ka_expiry_keeps_promise`). §6.1's rule since v0.8, `drop_offer`, closes it: a
peer's queued asks of an index go and its promise for it closes where its offers of it are dropped
(the switches `dropAsks` and `dropPromises`). With it the proof holds.

**F14, open in `protocol.md` §6.1: an announcer that is never parked holds the last resort off.**
The traces `ka_f14_s0` to `ka_f14_s3` and `ka_f14_loop`, under v0.8's rules, show it:
- an honest node n with the builder's block lacks a chunk, and its honest provider h is parked by a
  slow answer on another chunk of the group;
- an adversary a is never parked: it closes before its promise falls due (a close does not park,
  §6.1), and offers again on a new connection;
- the last resort is armed only when every untied announcer is parked. The retry would find that
  only at the one state between a's close and its new offer; enabled there alone, it is not forced
  by weak fairness, and the last resort never asks h.

The traces reach a state with these roles, and take the loop `writeAsk(n, a)`, `windowElapse(n)`,
the close between n and a, `offerAsk(n, a)` back to a state with them. At each of the loop's states
they assert which honest events are pending. That the run repeating the loop is weakly fair is read
from these finite traces and the actions, by inspection, not proved. The control
(`f14_control`) shows that without a's new offer the last resort asks h. In the spec the same holds
for as long as h's park lasts and the group is live, and an adversary that leaves its ask unwritten
by not reading does the same without reconnecting, which these models leave out (their writes drain).
`protocol.md` §6.1 names this open, and no rule for it is modelled. Q1 above holds in the quiet
states, which such a run never reaches; Q3 with malicious peers (below) holds once the environment,
the adversaries included, stops.

**Level 1 by group** (`NoStallEquivAdv.lean`'s switch `byGroup`): **a candidate rule, off for the
spec's rules.** It is one of the options `protocol.md` §4.6 lists for relabelled copies (F12): the
root a chunk names takes no part in level 1, deferral or ties. With it on, a copy passes level 1
against either block, so the first installation of either is the node's installation, and offers
resolve at an honest node with either block (`offers_resolve_any`); without it, a node with only the
other block stalls (`ka_other_block_stalls`, a known answer for that clause). The switch excludes
only the other block's installation alone, so its runs are a subset of those proved with it off.
Reading `installed` as the first installation of either block, and the handler that takes every
waiting copy of the group in at that installation, are by inspection of a draft of the rule, not of
`protocol.md`, and the transport under the rule is a model outside this folder. Nothing here
proposes the rule: it is in the file so that the option's asking part is checked with the rest.

| piece | proof | traces | the build |
|---|---|---|---|
| transport, with adversaries | 220 of 220 conditions, 991 theorems | 14: the transport's 12, a false claim, an adversary's offer left in a quiet state | 5.2 minutes |
| asking (v0.7's), with adversaries | 448 of 448 conditions, 1324 theorems | 14: the asking's 11, `adv_withholds`, `ka_count_per_chunk` (bound to the adversary's offer coming first) and its control | 7.3 minutes |
| asking under v0.8's rules, with adversaries and the offers' expiry | 1134 of 1134 conditions (42 × 27: 41 actions and the initializer, 26 clauses and `doesNotThrow`), 2625 theorems | 29: `NoStallEquiv.lean`'s 11 (their nodes honest); an ask left at an adversary; an adversary tied to another root after the block, alone and beside an honest offer that resolves; a tie released; a tie dropped; an ask gone with expired offers; F13 by a dropped tie, by the expiry without the queued asks' part, and by the expiry without the promise's; under `byGroup`, an offer answered and a tie released, and the known answer without it; F14's five and its control | 71 minutes |

## Agreement and integrity (`Agreement.lean`)

Plain Lean, one `Codec N K` per valid descriptor (§1): the segmented byte strings (the payload,
compressed), their encoding into N leaves (K data chunks, the last short, then the Reed–Solomon
parity, none for a plain group), a decoder from given positions, the Merkle root and the proof
check. What a node decodes from is any set of at least K distinct positions whose chunks passed
level 1; level 2 re-encodes the recovered bytes and compares the root. Whatever the builder
committed:
- any two checks of a group succeed or fail together (`level2_all_or_none`, L3);
- one that succeeds recovers the one byte string the root commits (`integrity`);
- two honest nodes that both deliver a group deliver the same payload, a function of those bytes
  (`agreement`, and `agreement_by_key` across descriptors with one key, given that a key names one
  descriptor, `key_inj`: the group id is the descriptor's hash, taken as collision-free);
- an honest builder's group passes everywhere (`honest_succeeds`);
- the decode claim is true of a group whose check succeeds, and wrong only of one that every node
  reaching K drops.

Each theorem takes the hypotheses it uses:
- the decoder reads its positions (`Local`) and recovers from any K positions of an encoding (`MDS`:
  that Reed–Solomon over GF(2⁸) is MDS is assumed here);
- a proof binds a position to one leaf (`Binding`: the hash's collision resistance, taken as exact;
  it also covers level 1's length check);
- each leaf of a committed vector has a proof (`Complete`).

Known answers: without `Binding` two checks succeed with different bytes (`binding_needed`), and with
a code that is not MDS one succeeds and one fails (`mds_needed`), the other hypotheses holding in
each; an instance meets all four (`plainOne_meets_all`). The sixteen theorems rest on `propext`,
`Classical.choice` and `Quot.sound` only.

## A run goes quiet (Q3: `QuietRanking.lean` and the models' `quiet`)

Q1 speaks of the states in which nothing is left to happen; Q3 is that a run reaches one and stays
there. For each honest per-chunk piece, with any finite number of nodes:

- **the transport goes quiet** (`NoStallTransport.lean`, `quiet`): in every run in which the
  transport's environment eventually stops (a block installing, the decode claim, the decode's
  store, a learned claim, an answer that brings the chunk, the mesh and its connections changing),
  and each of its nine machinery actions (all its own but `dropIhave`, F11's known answer) is weakly
  fair, the transport eventually has nothing left to do, for good (`◇ □ ¬ work`), whatever rules
  are on;
- **the asking goes quiet** (`NoStallEquiv.lean`, `quiet`: v0.8's asking, one block or two): the
  same, with the queues' refusals of an ask stopping too, the machinery's thirteen actions weakly
  fair (the retry's and the last resort's asks that a queue takes), and `NO_REASK_OPEN` on, whatever
  the other rules.

Weak fairness is Veil's `𝒲ℱ a`, per action as a family and by effect: if the family stays enabled,
possibly through different instances, eventually a step has some instance's effect. A queue's
refusal is the environment's (Q1's "a send window that lets every queue drain"). "The environment
eventually stops" is stated by effect, as Veil reads `⟨a⟩` in a proof: from some point on, every
step that changes the state has an own action's effect or no environment action's (`◇ □ (⟨stutter⟩
∨ ⟨own⟩ ∨ ¬ ⟨env⟩)`), which every run whose environment stops meets. The plainer form, `◇ □ ¬ ⟨env⟩`,
would exclude every run that ends with a node stopped, whose `stopPull` then changes nothing, so that
every later step has its effect (with fields as functions), and so, in the transport, every run with
a source: a theorem under it would be empty. With Q1, by the same composition by
inspection, and given that every decode that starts eventually returns (Q1's counting assumes
decoding succeeds), every honest node the source reaches through nodes with the builder's block
eventually completes.

**Why**: every step of a piece lowers a lexicographic tuple of counts of relations, its levels,
highest first; the environment may raise it, finitely often. `QuietRanking.lean` (plain Lean, on
Lentil's semantics) proves once that this, finitely many nodes, weak fairness and an environment
that stops give `◇ □ ¬ work` (`quiet_exec`), with the order's two facts: a step that gains nothing at
any level down to its own and loses an element there lowers the counts (`counts_dec`), and the order
is well-founded (`counts_wf`, from Lentil's `List.lexLt_wfRel`). Each model states, per own action
(and case), that its witness element is at its level before the step (`…Pre`), not after it
(`…Post`), and that no level down to its own gains an element (`…Keep_j`), each a temporal property
of one step proved by `fv_step` (below); that while there is work, some honest node's machinery
action is enabled (`workEnabled`, proved by Veil's `veil_solve_temporal`); and its proof of `quiet`
puts them together. Neither proof uses the module's invariants. The one-step facts use no SMT
solver; `veil_solve_temporal` may, its answers then rebuilt as kernel proofs, as for the
invariants.

| piece | levels (highest first), each a relation | facts |
|---|---|---|
| transport | on pairs (m, n): not yet published; m has not received the chunk; forwarding due; repair due; a push, an announcement queued; an offer owed; a copy in flight; a copy deferred; an announcement in flight | 91 |
| asking | on (asker, announcer, ask number): announcers not yet asked once more; fresh asks (offered, unparked, untied, no promise open, none of that number queued), both while the asker neither holds the chunk nor has stopped; armed retries; armed last resorts; ask windows; queued asks; asks in flight; open promises; owed, queued answers; answers in flight | 222 |

`fv_step` is Veil's reduction of a one-step goal (`unveil_temporal`, the case split, `veil_fol`),
the enums' distinctness as inequalities, then `grind`, all kernel-checked; `veil_solve_temporal`,
which ends in the SMT solver, fails on most of these facts (below). Two limits of Veil `v4.35.0`
shape them: no conclusion is a conjunction (so the levels that are conjunctions are stated literal by
literal), and no branch condition has an `∃` (so `retryParked` is two actions, `retryParkedArm`
arming the last resort, as `install` is two).

**With malicious peers** (`NoStallTransportAdv.lean`'s and `NoStallEquivAdv.lean`'s `quiet`): for
each piece, with any finite number of nodes, in every run in which the environment eventually stops
(the adversaries' actions included), and in which each machinery action is weakly fair at every
honest node, the honest nodes' machinery eventually has nothing to do, for good. The asking needs
`NO_REASK_OPEN`, as in the honest case.
- **The rankings** are the honest pieces', counting every node's elements; the asking's level of
  fresh asks needs the announcer tied to no root (`tied ∨ tiedElse`).
- **Fairness is per honest node** (`∀ m, ⌜ hon m ⌝ → 𝒲ℱ (act m · …)`): an adversary's steps of the
  same actions are not forced, and when taken they lower the ranking as an honest node's do.
- **With Q1 with malicious peers**, by inspection, under Q1's assumptions: once the environment, the
  adversaries included, stops, the run reaches a quiet state, in which every offer still pending from
  an honest node to an honest node that installed the block is resolved (`offers_resolve`).
  Completion also takes decodes that return, as in the honest case.
  While the adversaries keep acting, F14 (above) is a run that never goes quiet.

The proofs and the facts are counted among each model's theorems in the tables above: 93 in each
transport model, 224 in `NoStallEquiv` and 239 in `NoStallEquivAdv`.

**Known answers**, checked when the proofs were written, on altered copies of the models that are
not kept here and not part of this folder's build: forwarding that never clears its due flag makes
the transport's proof fail at `fwdPost` alone; an ask window that never ends makes the asking's with
adversaries fail at `windowElapsePost` alone; and on a toy model the model checker finds a run that
never goes quiet without fairness, one with an environment that never stops, and none with both.

**Not covered**: v0.7's asking without `NO_REASK_OPEN`, Q3 under level 1 by group, and anything
about time.

## Running it

Veil is its release `v4.35.0`, pinned by commit in `lakefile.lean`, and every dependency by commit
in `lake-manifest.json`; `lean-toolchain` names the Lean release, 4.35.0. With
[elan](https://github.com/leanprover/elan) installed, and the system dependencies Veil's README
lists, from this directory:

```sh
lake build Veil      # once: Veil and its dependencies (it downloads cvc5 and Zipperposition
                     #   from their GitHub releases)
LEAN_NUM_THREADS=2 lake build   # the models: queries, model checks, proofs, theorems, audits
```

A clean `lake build` means every check passed: a clause that fails, a query without a trace, a
violation and a failed audit are errors. The one warning is Veil's own, at `NoStallEquivAdv.lean`'s
`#gen_spec`: it could not prove its generated `Next.tr_abstract`, a lemma for temporal proofs. It
did not stop the model's: each one-step fact has an action in its premise, and `workEnabled` clears
the transition relation (`tclear … hNext`). Packages and build outputs go to `.lake`. In the whole
library's build, its outputs took 0.8 GiB beside 1.8 GiB of packages. With Veil already built, the
models took 87 minutes on ten cores of an AMD EPYC 9254 (`taskset`, `LEAN_NUM_THREADS=2`, on a
machine shared with other jobs), and 44,400 seconds of CPU; Lake builds independent modules side by
side, and `NoStallEquivAdv.lean` alone took 71 of the minutes.

Veil checks as many conditions at once as `LEAN_NUM_THREADS` says, each with its own SMT run, or,
where it is not set, as many as `getconf _NPROCESSORS_ONLN` reports; the variable also sizes Lean's
own task pool, for each Lean process. It does not bound the build's CPU: with
`LEAN_NUM_THREADS=2`, an earlier build of `NoStallEquiv.lean` alone, on another machine, used about
seven cores on average. Pin the CPUs with `taskset` and cap the memory as well, with room above the
peaks of the whole library's build: its processes together reached about 25 GiB (25,856 MiB,
sampled every 20 seconds), and the largest of them alone 23.3 GiB (GNU time's maximum resident set
size). For larger instances `#model_check compiled` builds a native checker, which needs `clang`,
`lld`, `libc++-dev` and `libc++abi-dev`. In an earlier check, on the pre-release, it found the
127,504 states of the window's instance above in about 80 seconds with its build; the library's
build runs `interpreted` only.

## Veil 2.0, as met here

These cost time, and each has its workaround in the model. The first items were met on a
pre-release (`02791b2d`); the later ones are new on the release `v4.35.0`.

- A relation binder names one variable: `(a : node) (b : node)`, not `(a b : node)` (the error
  says only "unable to extract type from binder").
- `sat trace` queries fail to translate an update `r n … := decide $ …` whose target names an
  action parameter (`cannot translate Type`, a universe-level error, or a cvc5 parse error, by the
  proposition), and a ghost relation read after an update in the same action (a lambda SMT-LIB
  lacks). `#check_invariants` handles both. Hence Bool operators or `if` in updates, and conditions
  on the state before the updates.
- `set_option veil.smt.trust false` works at file level, not as `set_option … in #check_invariants`;
  `#check_invariants` alone adds no theorem, `#gen_theorems` does.
- The model checker's memory grows fast: two nodes with two chunks and three positions filled
  24 GB in 50 minutes interpreted, and in 4 minutes compiled (on an earlier version of the model).
- `lake env lean` on a loose file does not load cvc5; pass the plugins listed in
  `.lake/build/ir/ClaimWins.setup.json` (`--plugin=…`) to check one by hand.
- With the SMT solver not trusted (as here), a relation with six arguments breaks every
  preservation condition ("Tactic `assumption` failed"), where one with five works: hence
  `SenderFault`'s `piece`, which folds a chunk's index and contents into one argument. An
  `assumption` that is a bare relation fails with "type expected"; give it a connective.
- `veil module` sets `maxRecDepth` to 1024 and `maxHeartbeats` to 500000, whatever is set above it;
  a long trace's simplification needs more depth, and on `v4.35.0` some conditions more heartbeats,
  so the models set both after the `veil module` line (`maxHeartbeats` to 2,000,000).
- A state field must not share a name with Veil's own locals: a relation `has` (Veil binds its
  assumptions as `has`) breaks `#gen_spec` with a type mismatch, and so do `hinv` and `core`.
- Veil's cost grows with the state's width: a 35-field model did not finish `#gen_spec` in 30
  minutes, while the pieces of 15 and 16 fields finish in under three. Splitting a model, each piece
  with its environment, is the remedy.
- Where the SMT solver answers unsat but lean-smt cannot rebuild the proof ("no witness provided"),
  `set_option veil.solver "grind+smt"` tries Lean's `grind` first, kernel-checked as it is; and an
  action whose conditions nest quantifiers proves more easily split into one action per case.
- On `v4.35.0`, a long trace may need more than the SMT solver's 60 s on a loaded machine
  (`unknown`): `set_option veil.smt.timeout 300`.
- On `v4.35.0`, in `NoStallEquivAdv.lean` (41 actions, 26 clauses), the search for the invariants'
  instance at `#gen_spec` ran out at its 20,000 heartbeats, with only a warning, and 53 conditions
  then failed on an SMT path that breaks. `set_option synthInstance.maxHeartbeats 200000` fixes it.
  Read a warning at `#gen_spec` before the failures that follow it.
- A temporal proof (`prove_temporal_by`) considers only runs whose every step is an action, so a
  model needs `action stutter { pure () }` for its quiet runs to exist. In the proof `⟨a⟩` is read by
  effect (the step has the effect of some execution of `a`, whatever action took it), not by the
  action taken, and `𝒲ℱ a` with `a` unapplied is fairness of the family: write premises in that
  reading ("A run goes quiet" above).
- `veil_solve_temporal`, which ends in the SMT solver, failed on most one-step facts of these models
  (translation errors, or "Tactic `assumption` failed" in the proof's rebuild). Veil's reduction then
  `grind` (`fv_step`) proves them, with two limits: a conjunction in a fact's conclusion fails (the
  reduction unfolds the step in its first part only), and `grind` does not split an `if` whose
  condition is an `∃`. A `Veil.Enumeration` instance broke the SMT translation of every condition
  ("incorrect number of universe levels List"), so finiteness is a premise of the property instead.
- `#temporal_check` did not finish on the transport model with two nodes in 15 minutes.
