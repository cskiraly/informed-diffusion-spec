# SEACAST's next version (draft): the protocol on its own notions

> **DRAFT.** Its decisions taken (§8); checked in the toy only; no client runs it, and the research
> harness's simulations ran only designs it contains as settings (§6.2); not model-checked, but for
> §4.1's JOIN and answered GRAFT, checked exhaustively for one link and one relation in small
> bounds.

*SEACAST: Segmented, Encoded, Availability-sampled broadCAST (the E could also read Elastic). The
name since 2026-10-19; v0.4 was published as Informed Diffusion, which now names SEACAST's diffusion
part (§0, "The parts").*

*Draft 1, 2026-10-07. A sibling of [`protocol.md`](protocol.md), which it contains as one
setting (§6.1). That was draft v0.3 when this was written and is v0.10.8 since 2026-11-21, with
the same section numbers; "v0.3" below means that document.*

*Each later version of `protocol.md` is carried into this document in the same way; §5 lists what
carries over, version by version.*

*This draft defines the notions, the messages, the state and the event handlers; the scheduling
that tier 4 measured carries over unchanged where §5 says so. Every design decision is marked
`[D1]` … `[D12]`, and §8 lists where each bites and what was decided. The toy runs this document on top of v0.3's
(`toy/run.py --doc v2`): v0.3's blocks are loaded first, this document's after them, and the tier
4 setting is checked against `protocol.md`'s recorded cells (v0.9's rules since 2026-11-12,
re-recorded on 2026-11-15 with the toy's transport keeping §7.3's rule). Draft 0
(2026-10-06) was written without running; draft 1 is what executing it changed.*

## 0. How to read this

Gossipsub bundles its notions: a *topic* is the namespace, the unit of subscription, the unit of
the mesh, the scope of scoring and the rendezvous; a *subscription* means "everything here", is
announced to every peer and invites GRAFTs; the *mesh* is one symmetric pusher set per topic and the
scope of IDONTWANT; *gossip* is message ids to a few random non-mesh peers per heartbeat. v0.3 ran
inside those notions and loosened them from within: chunks as messages, HAVE bitmaps inside
IDONTWANT and IHAVE, asks by index inside IWANT, the source striping over every connection.
This document unbundles them. What a node receives (*interest*), what it does for others (*duty*),
whom it pushes to and for which indices (the *push relation*, per family and colour), whom it tells
what it holds (the *announce relation*), and where it finds peers (*rendezvous*) are five separate
things, each with its own parameter. Variant C of the posts, one topic per index with everyone
subscribed, and v0.3, one topic with one mesh, are two settings of the same protocol (§6).

**What is assumed and not restated.** The consensus-side objects and their verification: the
payload's descriptor committed in the bid and its Merkle tree over Reed–Solomon chunks (v0.3 §1),
the `DataColumnSidecar` header and the KZG cell proofs (Fulu `das-core`, the partial-columns spec),
RowDAS's rows (EIP-8371). Rendezvous and discovery: how a node finds peers that share an object
type and a family (gossipsub topics where they exist, the ENR's `cgc` and node ids); this document
assumes a set of connected peers per object type and defines what happens on those connections.
The libp2p connection and its framing. Gossipsub itself is *not* assumed: what it provided, the
pusher set, suppression, announcements and pulls, is defined here, and the bindings (§7,
`protocol-v2-bindings.md`) say how the result is
carried on gossipsub's wire where that is the deployed path. v0.3's code is assumed where §5 says
a function carries over: this document redefines what changes and names what it keeps.

**What is normative.** Sections 1 to 3, the notions, the messages and the state, are what both ends
of a link must agree on. Section 4 combines each node's local scheduling with the meaning of the
messages: what a holding, an offer, an ask, a claim and an acknowledgement promise. A client may
schedule differently without breaking interoperability, provided those meanings hold. Section 5
names the v0.3 scheduling that carries over, section 6 the settings, section 7 the bindings and
section 8 the decisions, with what was not taken.

**The parts.** SEACAST has six parts, named for what they do. Three carry message semantics both ends
must share; two are local policy, which a client may change while the meanings hold; the last says
how the messages travel. Named mechanisms inside a part keep their own names.

| part | what it does | sections | mechanisms inside |
|---|---|---|---|
| joins and relations | declares interest and duty per link; keeps the push and announce relations per family and colour, with their directions and floors, and a sampler's coverage floor | §1.2–1.4, §4.1 | coloured push relations |
| Informed Diffusion | pushes chunks into interest, tells holdings and offers, answers and makes asks | §1.5, §4.2–4.5, §4.10 | standing sample requests, routed sample requests (§4.10) |
| completion and repair | the claims, completion per interest, decoding at K, rebuilt chunks, deferral, the probe, evidence | §1.5, §4.6 | |
| informed scheduling *(local)* | what a node sends next and when: the window in bytes, the projection, the next entry, pacing, the ask window | §4.9, §4.11–4.13 | the byte window |
| source distribution *(local)* | how a source releases a group: batch order, striping, its paced holding; any node holding chunks first is a source (§1.6) | §4.7 | striped publishing |
| wire bindings | how the messages travel: standalone (on a stream of its own or in Waggle's framing), on gossipsub's Partial Messages Extension, or on v0.3's wire | §7; `protocol-v2-bindings.md` | |

The heartbeat (§4.8) drives three of them: relation upkeep, announcement gossip and pacing. Outside the
parts, and assumed above: the object type's interface (§1.1: indices, verification, decoding,
projection across groups) and peer discovery, with the connectivity that repair's floor and
sampling's coverage floor ask of it (§4.6, `REPAIR_FLOOR`; §1.3, `SAMPLE_COVER`). *Colour*
partitions a group's indices; it is not a subnet. *Family* is the key of a relation, not
necessarily a custody group.

**Conventions.** Python-like pseudocode in the style of the consensus specs, as in v0.3; a comment
`# [c8]` marks a card of the posts (`protocol.md`'s introduction lists the cards and the posts),
`# [D5]` one of §8's decisions, where it bites. State and helpers keep v0.3's names
wherever the object is the same (`peer_has`, `pushed`, `holders`, `mine`, `received`); the header
of a group is v0.3's `desc`, read here as `hdr`. New helpers are listed in §3.

**Requirement labels.** The draft was written against a list of requirements; the labels it cites
are these ([P4] is v0.4's tag, its §5.1: the source's holding names only the chunks it has sent;
since v0.9, the chunks acknowledged so far, §4.7).

| label | requirement |
|---|---|
| I3 | pushes, announcements and gossip go into interest only |
| I6 | a sample is disclosed only to the peers asked for it |
| I7 | level 1 verifies a chunk alone, level 2 checks the consistency of a set; both per object type |
| I8 | a node may hold chunks it did not receive through the protocol |
| P2 | a chunk is held until its header is validated, and the header travels once |
| P7 | scoring reads interest |
| R2 | a row member's interest is K of 128 cells, a decoder's is all |
| R3 | reconstruction duty is designated and phased |
| R4 | a chunk may belong to two groups, and a verified cell fills both |
| R5 | a claim defers others' reconstruction, and silence after it re-arms them |
| R6 | what a peer may pull is bounded by what it may want |
| R7 | rows must not cost the column path traffic |
| X2 | the protocol is its own, where that gains over an extension of gossipsub |
| X3 | one window and one duty rule over every group |
| X6 | limits before state, for every object type |
| X8 | the source is a role, not a node |

**Numbers.** Every figure in this draft comes from the toy (`toy/`, 60 nodes unless stated) unless
it says otherwise. Since the toy took `protocol.md` §7.3's rule as its default (2026-11-15: one
entry at a time per connection, `--send-buffer 1`; with `--uplink rr`, which has no send buffer,
writes still go at once), figures and comparisons measured before that change ran with its earlier
transport, which takes every write at once (`--send-buffer 0`), unless they name `--send-buffer 1`.
A figure from fewer than ten seeds, a single seed unless stated, is a toy check of a mechanism, not
a measurement; ranges over ten or more seeds say so.

## 1. Notions

### 1.1 Objects, groups, chunks, families

An **object type** `T` is the consensus side's contribution: what an index space is, how one chunk
is verified alone (level 1), how a set of chunks is checked for consistency and what a holder of
enough chunks can rebuild (level 2, one operation: decode, re-encode, compare), how a receiver
learns the header that the verifier needs, and how a chunk maps onto groups.

```python
class ObjectType:                                    # T: one kind of object, a protocol parameter
    name: str
    index_count: Callable[[Header], int]             # N: indices of a group, from its header
    threshold: Callable[[Header], int]               # K: chunks from which the whole object follows
    verify: Callable[[Chunk, Optional[Header]], Result]   # level 1, one chunk: ACCEPT | REJECT | DEFER
    decode: Callable[[Dict[int, Chunk], Header], Optional[Dict[int, Chunk]]]   # level 2: every
                                                     #   chunk of the group, or None if inconsistent
    header_of: Callable[[Chunk], Optional[Header]]   # what the chunk or the block supplies; None: gate closed
    project: Callable[[Chunk], List[Tuple[GroupId, int]]]   # every (group, index) one chunk fills
    cross: Callable[[GroupId, int], List[Tuple[GroupId, int]]]   # the other (group, index) pairs of the chunk
                                                     #   at index i of g, from the ids alone (R4)
    family: Callable[[GroupId], FamilyId]            # the relation key (§1.3)
    derived_interest: Callable[[GroupId, Optional[Header], NodeId, Join], Bitmap]   # from the group id and a
                                                     #   node id: custody, or all; computable before the header
    params: TypeParams                               # §6.3: the decisions' values sit here

class TypeParams:                                    # per object type; values in §6.3
    M: int                                           # colours of the push relation           [D10]
    F_LO: int                                        # in-pushers per family and colour: the floor [D10]
    F_HI: int                                        # and the cap                             [D10]
    D_OUT: int                                       # out-pushees per family and colour       [D10]
    D_OUT_FAST: int                                  # the same for a fast uplink              [c17]
    D_OUT_MAX: int                                   # what a node accepts to push for others
    SYMMETRIC: bool                                  # one relation both ways, kept as gossipsub keeps its mesh (§4.1)
    PRUNE_BACKOFF: float                             # seconds before a relation a PRUNE named is grafted again (§4.1)
    ANNOUNCE_EXTRA: AnnounceWidth                    # ALL_JOINED | SAMPLE | NONE              [D5]
    EAGER: bool                                      # chunks of this type are pushed; False: holdings and offers only (rows, EIP-8371),
                                                     #   at the source too: it offers every chunk at publish (§4.7)
    DECODE_AT_K: Callable[[GroupId], bool]           # repair: who decodes at K, claiming all        [D4]
    DECODE_LATER: Callable[[GroupId], Optional[float]]   # repair: who decodes later if the group is still short, and when (from known_at) [D4]
    REPAIR_TO: Callable[[GroupId], List[PeerId]]     # repair: whom rebuilt chunks of a group go to  [D4]
    REPAIR_BUDGET: bool                              # repair: each rebuilt chunk to R_NODE of them lacking it, offered
                                                     #   to the rest (§1.6: its rebuilder is its source); False: v0.3's,
                                                     #   every peer short of K up to its shortfall   [D4]
    DEFER_WINDOW: float                              # repair: how long a peer's claim defers our own decode (R5) [D4]
    START_DELAY: float                               # seconds before the first ask             [D8]
    SERVE_LIMIT: int                                 # chunks served per peer and group         (R6)
    SAMPLE_RETRY: float                              # a sampler's first wait, before asking another peer (§4.10)
    SAMPLE_RETRY2: float                             # its wait on each later peer (§4.10)          [D12]
    SAMPLE_OUTSTANDING: int                          # its later asks in flight per block (§4.10)   [D12]
    SAMPLE_COVER: int                                # links serving each family, for a node that samples (§1.3) [D12]
    COVER_HIGH: int                                  # families a peer of high custody counts for in it (§1.3) [D12]
    ROUTE_HOPS: int                                  # forwarding steps a sampler's routed request may take (§4.10) [D12]
    FORWARD_LIMIT: int                               # routed requests passed on per peer and slot (§4.5, X6) [D12]
    EVIDENCE: Optional[ObjectType]                   # the fraud-proof object, if any           [D6]
```

| | payload (v0.3) | column (PeerDAS) | row (RowDAS) |
|---|---|---|---|
| a group | one descriptor's chunks, at one slot | one column of one block | one row of one block |
| group id | `group_key(group_id(descriptor), slot)`, the key of v0.3 §1 | `(block_root, column)` | `(block_root, row)` |
| N | `descriptor.count` | the blob count | `NUMBER_OF_COLUMNS` = 128 |
| K | `ceil(total_length / segment_size)` | N: no code across blobs | 64 |
| `verify` | v0.3's `validate_chunk`: the Merkle path to the committed root, and since v0.10 the copy's slot its block's; DEFER before the block | `verify_cell_kzg_proof_batch`, one cell index, many commitments, and the copy's slot its header's (REJECT otherwise, as v0.10's `validate_chunk`); DEFER before the header | the same, one commitment, many cell indices, and the same slot check |
| `decode` | v0.3's `decode_and_reencode`: any K chunks to all N, or None if the root differs; a coded group's root commits the bytes its builder's compressor produced from the body, and whether a canonical compressor should fix those bytes is open (`protocol.md` §1, "Open: the compressed bytes") | the cells present, if all are; nothing is rebuilt within a column (§4.6) | `recover_cells_and_kzg_proofs` from 64 |
| `header_of` | the descriptor: carried by the chunk and checked against the bid's group id (design A, which the toy runs), or carried by the bid itself (design B), so none before the block is installed (the gate, §4.2); `protocol.md` §1 leaves the choice open ("Open: getting the descriptor"), and the installed block confirms it either way | `PartialDataColumnHeader`, validated once per block on any group | the same header |
| `project` | `[(g, i)]` | `[((root, c), b), ((root, row b), c)]` | the same two |
| `cross` | none | index b of column c: `((root, row b), c)` | index c of row b: `((root, c), b)` |
| `family` | one family | the column index | the row's subnet (EIP-8371: `ROW_SUBNET_COUNT` subnets, a node's one from its id, rows mapped to subnets per slot) |
| `derived_interest` | all | all of the column if `c ∈ get_custody_groups(node_id, cgc)`, else none | all of the row if it is the node's row subnet, else none |

A **group** `g` is one instance of an object type: its id is computable before any chunk of it
exists (v0.3 §1; partial columns; the RowDAS design §4), so a receiver can hold state for it,
exchange bitmaps about it and ask for it before it holds anything. Its **header** arrives through
the object type's gate and is what the verifier needs. A **chunk** is one index of a group with the
proof that verifies it alone; `project` says which (group, index) pairs it fills, one for the
payload and two for a cell, which belongs to a column and to a row (R4). A **family** is the key
on which relations are formed (§1.3): where interest is structured, as custody is, a node needs
pushers for each family it has duty in, and the rendezvous is per family (one topic per column).

### 1.2 Interest and duty

**Interest** is what a node is to receive of a group (FullDAS). It comes in three kinds, declared
per link and object type at JOIN (§2):

- `ALL`: the whole object; completion is K distinct chunks and a decode where the type has a code,
  or every index where it has none;
- `DERIVED`: computed by both ends from the node id and the JOIN's `custody_count`
  (`T.derived_interest`), so a custodian never has to say what it wants;
- `DECLARED`: told per group and per peer, in a WANT (§2); a sample. The WANT may precede the
  chunks: it is a standing request, answered when the peer holds them (§4.10), so a sampler needs
  no offer and no promise timer, and the peer learns nothing about the sampler's other samples.

A node may also have interest in a group that it declares on no link, when its interest on another
axis brings every chunk of that group: a supernode, custodian of every column, holds every row
whole once its columns arrive, so it keeps every row with interest `ALL` and no peer offers it row
cells or counts it among a row's members (§4.6, the second phase).

**Duty** is what a node does for others, declared at JOIN: `FORWARD`, it holds push and announce
relations for the object type and forwards what it receives into others' interest; `NONE`, it
receives only. Serving is independent of duty: any node answers asks for what it holds, within the
serving limit (§4.5). A node with duty `FORWARD` also takes a routed sample request for what it
does not hold, and passes it one step on (§4.10). A sampler is `(DECLARED, NONE)`; a
custodian `(DERIVED, FORWARD)`; every node on the payload `(ALL, FORWARD)`. Interest and duty are
per link, so one node may be a custodian towards its custody peers and a sampler towards others;
nothing a node declares on one link is announced on another.

### 1.3 Links, joins and relations

A **link** is a connection on which both ends have exchanged a JOIN for an object type. On a link a
node keeps, per object type and family, two **relations**:

- the **push relation** `push_out[p][T][fam]`: the set of colours (§1.4) for which this node pushes
  chunks of that family to `p` eagerly, and `push_in[p][T][fam]`: the colours for which `p` pushes
  to this node. They are negotiated by GRAFT and PRUNE with a direction, so they need not be
  symmetric: a node's out-relations are sized by its uplink (card 17), its in-relations by its need;
- the **announce relation**: whom this node tells what it holds. It always contains every peer that
  may push to it, since that is what makes a holding a suppression and an acknowledgement, and every
  peer it pushes to, which it offers what it chose not to push; beyond that its width is a
  parameter `[D5]`.

The **suppression scope** of a group is the set of peers that may push it to us. v0.3's mesh is the
case where both relations are the same symmetric set of eight and the scope is the mesh. A type
whose relation is symmetric (`SYMMETRIC`, as v0.3's mesh, §6.1) keeps it as one relation both ways,
grafted and pruned with direction `BOTH` (§4.1).

**Sampling links and the coverage floor** `[D12]`. A sample is served by a peer whose interest holds
it (§4.10), so a node that samples an object type keeps, for every family of the type, at least
`SAMPLE_COVER` links that serve it (a parameter of the object type, set at two covers; §6.3): links
whose peer's interest holds every index of the family's groups, a custodian of the column by its
derived interest or a peer with interest `ALL`.
- **Every link counts**, whatever it was opened for, but a peer of **high custody** (more than the
  base custody count, or interest `ALL`: a supernode, a row reconstructor, a source) counts for at
  most `COVER_HIGH` families.
- **What the node's links leave short, the rendezvous closes with sampling-only links**, on which
  the node joins as `(DECLARED, NONE)` (§1.2; on gossipsub's wires, a connection with no
  subscription, §7). It closes what it can at each heartbeat, a candidate that covers the most
  families still short first; a family that no candidate covers waits for the next heartbeat
  (`keep_coverage`, §4.1). Such a link carries no relation, no push and no offer, since the peer's
  interest towards the node is empty until a WANT names a sample; it costs the peer a connection and
  what it serves, within its serving limit.
- **The links are chosen by custody computed from node ids** (`T.derived_interest` from the id and the
  custody count the rendezvous gives, the ENR's `cgc`; §4.1, `keep_coverage`), before and
  independently of any sample, for every family alike. A node's custody counts, not what it holds as
  a source (§1.6).
- **This floor is on links, not on a relation:** §1.4's floor counts in-pushers per colour. What it
  misses, a link that does not deliver or a family no link serves yet, goes to §4.10's second phase.

**Routing neighbours** (option) `[D12]`. A sample that no link serves goes out as a routed request
(§4.10), passed from node to node toward the column's custodians within a hop limit. Where the
rendezvous keeps, for each node with duty `FORWARD`, `ROUTE_FLOOR` links to custodians of the
families at structured distances from its own (FullDAS's topic routing: hypercube-style, columns `c
+ 2^j mod 128` for each column `c` it custodies; or Kademlia-style, a column in each XOR bucket `j`
of `c`), each step goes to the link nearest the sample's family by that distance, computed from node
ids. Without such neighbours the sampler's step goes to any link with duty `FORWARD` that does not
serve the sample, and one step reaches the family when that link passes the request on to a link of
its own that serves the index: it does so if its own duty is `FORWARD`, within its `FORWARD_LIMIT`
for the asker, to such a link other than the asker that it has not parked for the group (§4.5,
`route_want`). That is the trivial structure, and the one forwarding step that is the request's
default. With steps left (the request's `hops` above 1 when it arrives: `ROUTE_HOPS` above 1 at
the sampler), a forwarder that has no such link may pass the
request on toward the family in turn, to another forwarding link, under the same duty and limit
(§4.5).

#### Rationale

**A floor built for diversity, not for the fewest links.** Its aim is that the node's samples, one
per peer (§4.10), find distinct peers that serve them, so that no peer learns the node's whole
sample. One link to a node that custodies every column would otherwise cover them all and serve
every sample, hence `COVER_HIGH`. Links chosen before and independently of any sample reveal nothing
about what the node will sample (FullDAS's independence of the sample). A source's holding does not
count because a proposer holds every column of its own block only, and proposers rotate. Two covers
were decided on 2026-11-03 (`[D12]`, §8).

**What the floor buys, and what it costs, in the toy.** Without it, a sample of a column none of the
node's links custodies is never served: in the toy's graphs at 500 nodes, nodes custodying 8 of 128
columns and no supernodes (graph only, seeds 7 to 16), a sampler of eight cells has such a sample with
probability 17 % at 70 links and 96 % at 16. With it, on the same graphs, one cover by the fewest
links costs a median of 2 sampling-only links at 70 links and 13 at 16 (§6.3); the diversity floor of
two covers adds 8 and 29 in the toy's 500-node cells (§6.3, §8).

**One forwarding step usually reaches the family.** A custodian's floor per column (§1.4) makes it
likely that one of a forwarding link's own links custodies the sample's family: it keeps about 57
links at a degree of 16 in the toy's graphs.

### 1.4 Colours and the floor

Each index of a group has a **colour**, `colour_of(g, i)`, one of `M[T]` `[D10]`. A chunk is pushed
eagerly only on links whose push relation for its family holds its colour. With `M = 1` every link
carries every index: v0.3's mesh. With `M = N` each index has its own pusher set: variant C's
independent meshes, on one neighbourhood. In between, each link carries a share of the indices and
a node's pushers for a given index are a subset of its links, which is where path diversity comes
from without multiplying topics.

```python
def colour_of(g, i) -> int:
    return i % type_of_group(g).params.M             # [D10] a keyed permutation per group is a variant
```

A node keeps, per family it has duty in and per colour, at least `F_LO` and at most `F_HI` peers in
its in-relation: the **floor** per colour. Colours are proposed from the proposer's least-used colours (balanced
colouring at GRAFT, §4.1). The floor needs links to form on: a node also keeps, per family it has
duty in, at least `F_LO` links to peers whose interest holds the family, and opens more where churn
leaves it short (`keep_floor`, §4.1).

### 1.5 Holdings, offers, claims, completion and evidence

A node says two different things about what it holds, and they are not interchangeable. A
**holding** ("I hold these, verified") goes to whoever may push to us: it suppresses pushes, it
acknowledges the chunk just received (the window, v0.3 §7.1), and it counts the sender as a holder
for rarest-first and cancel. An **offer** ("you may ask me for these") goes to a peer we chose not
to push a chunk to, or to a peer outside the relation: it feeds that peer's offer table and nothing
else. A pusher's holding is not an offer, since it may be pushing that very chunk; an offer is not a
holding count, since what the pull discipline needs is who can serve. v0.3 carries the two in
IDONTWANT and IHAVE; here they are one message with a flag (§2) and two handlers (§4.3).

A holding carries two **claims** besides its bitmap `[D3]`: `claim_all`, the sender holds or can
produce every index (it has reached K and will decode: v0.3's decode claim, made at K, before the
decode, because a group whose chunks do not form a codeword fails at every node), and `complete`,
the sender's interest in this group is satisfied, so nothing more need be pushed or announced to
it. Both are unverified; the window and serving treat them as such, and a claim not followed by the
chunks it implies counts against the claimant (R5).

**Completion** is per interest: a node with interest `ALL` is complete at K distinct chunks; a
custodian at every index of its column; a row member at K cells (it stops pulling and exposes what
it has, EIP-8371) and decodes only if its duty says so; a sampler when its declared indices have
arrived.

**Evidence** is an object a node may publish about a group it found inconsistent at level 2, if the
object type defines one `[D6]`; this document carries it and does not define it. No object type
defines one in this version (§8).

### 1.6 Roles are derived, not declared

A **source** is any node that holds chunks of a group before its peers do: the builder with the
whole payload, or a node that built columns from its mempool at block arrival (I8, X8). The source
rules of v0.3 §5.1 (batch order, striping and the window) apply to what such a node pushes
first; whether a node is a source is read from its holdings and its peers' holdings, not announced.
A **forwarding node** is any node with duty `FORWARD`. A **reconstructor** is a node whose repair
rule (§4.6) says it decodes a group or a block it does not need whole for itself.

## 2. Messages

Abstract messages; the bindings carry them on wires (§7, `protocol-v2-bindings.md`). Every message
names its object type or group, and a
receiver ignores, without penalty, a message for an object type it has not joined on that link.

```python
class Join(Container):                   # per link and object type, sent by both ends   [D11]
    object_type: TypeId
    interest: InterestKind               # ALL | DERIVED | DECLARED
    custody_count: uint64                # the input to derived interest (the ENR's cgc), else 0
    duty: Duty                           # FORWARD | NONE
    colours: uint16                      # M[T] as the sender runs it; a mismatch is no link for T

class Graft(Container):                  # relation maintenance, per family and colour; also the yes to one (§4.1)
    object_type: TypeId
    family: FamilyId
    colour: uint16
    direction: Direction                 # OUT: "I will push you this colour"; IN: "push me this colour"; BOTH
    answer: boolean                      # True: the yes to the receiver's GRAFT, not answered where it is held (§4.1)

class Prune(Container):                  # the no to a GRAFT, or the end of a relation, at both ends (§4.1)
    object_type: TypeId
    family: FamilyId
    colour: uint16
    direction: Direction                 # the sender's view, as a GRAFT's: OUT "I stop pushing you"; IN "stop pushing me"

class Have(Container):                   # what the sender holds, verified                   [c7]
    group: GroupId
    bits: Bitmap
    offer: boolean                       # True: "you may ask me for these"; False: a holding (§1.5)
    claim_all: boolean                   # [c10] the decode claim; holdings only              [D3]
    complete: boolean                    # my interest in this group is satisfied; holdings only [D3]

class Want(Container):                   # "send me these", to this peer only                [D2]
    group: GroupId
    bits: Bitmap
    standing: boolean                    # also when they arrive, not only if held now (§4.10)  [D12]
    hops: uint8                          # forwarding steps the request may still take (§4.10); 0: none [D12]
    probe: boolean                       # the probe of a claim: answered whatever the sender holds (§4.6)   (R5)

class ChunkMsg(Container):
    group: GroupId
    index: uint32
    data: bytes
    proof: Proof
    header: Optional[Header]             # with the first eager push of a group on a link (P2)

class Evidence(Container):               # [D6]
    group: GroupId
    body: bytes
```

- **One message, two kinds.** `offer = False` is a holding (v0.3's IDONTWANT with a bitmap, on the
  urgent lane); `offer = True` is an offer (v0.3's IHAVE with a bitmap, paced). §4.3 handles them
  differently and §1.5 says why.
- **WANT is per recipient** (the RowDAS design's reading of `requests`): what the sender asks *this*
  peer for, not what it lacks, and the peer sends it what it holds of that now and, for a standing
  WANT (below), the rest when it arrives, within the group's lifetime (§4.10). The ask discipline of
  v0.3 §6.1 sends one index per peer at a time and carries over for pulls against offers; a bitmap
  lets a client batch, and a sampler declares its indices in one. There is no third bitmap for need
  `[D2]`: a peer with `DERIVED` or `ALL` interest needs no WANT to declare what both ends can
  compute (its pulls on offers are asks, §4.3), and a declared interest is only ever told to the
  peers it is asked of (I6). Two fields say how long a WANT stands and how far it goes `[D12]`:
  `standing`, answered when the chunks arrive as well as from what is held (a sampler's WANT always
  is, on a `DECLARED` link whether or not it says so); `hops`, the forwarding steps the request may
  still take: a receiver that does not hold the chunks passes it to one of its links with one step
  fewer (§4.10). A pull against an offer, the probe and the repair sample (§4.6) set neither. A
  third field, `probe`, marks the one ask that verifies a peer's claim (§4.6): the claimant answers
  it whatever the asker's holdings say, once per asker and group. The standalone binding carries
  `standing` and `probe` in one flags byte (`protocol-v2-bindings.md` §1.3).
- **A cell carries its header once per group and link**, so cells can be verified before the block
  (P2). The payload's header is the descriptor, which every chunk carries under design A and the bid
  under design B, a choice `protocol.md` §1 leaves open; the installed block confirms it, as in
  v0.3.

## 3. State

```python
# per link and object type (new)
join_recv: Dict[PeerId, Dict[TypeId, Join]]           # what p declared to us
join_sent: Dict[PeerId, Dict[TypeId, Join]]           # what we declared to p
push_out: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Set[int]]]]   # colours we push p, per family
push_in: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Set[int]]]]    # colours p pushes us, per family
grafted_out: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Set[int]]]]   # colours we offered to push p, unanswered (§4.1)
grafted_in: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Set[int]]]]    # colours we asked p to push us, unanswered
owed_relations: Dict[PeerId, List[Container]]                    # per link: JOINs, GRAFTs and PRUNEs a full queue refused, in order
backoff: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Dict[Tuple[int, Direction], float]]]]   # until when we do not graft p
                                                                 #   again for a relation its PRUNE named (§4.1)

# per group (v0.3 §8.1's, plus three)
T_of: Dict[GroupId, ObjectType]                       # new: the group's type, from its id
hdr: Dict[GroupId, Header]                            # v0.3's desc, once the gate opened
state: Dict[GroupId, GroupState]                      # COLLECTING | DECODING | COMPLETE | INVALID
received: Dict[GroupId, Bitmap]                       # chunks from the network
rebuilt: Dict[GroupId, Bitmap]                        # new: chunks from a decode
mine: Dict[GroupId, Bitmap]                           # what we claim: received, rebuilt, or all N at K
chunks: Dict[GroupId, Dict[int, Chunk]]
interest: Dict[GroupId, Bitmap]                       # new: ours, per group (§1.2); ALL reads as every index
stop_pull: Dict[GroupId, bool]                        # [c6]
origin: Dict[GroupId, Bitmap]                         # v0.4's: for a group we publish, the chunks acknowledged so far (§4.7) [P4]
planned: Dict[GroupId, Dict[int, Set[PeerId]]]        # v0.9's: for a group we publish, each chunk's push targets [c3]
known_at: Dict[GroupId, float]                        # new: when the group id became known; START_DELAY runs from here [D8]

# per peer and group (v0.3's, plus flags and one counter)
peer_has: Dict[PeerId, Dict[GroupId, HaveEntry]]      # bits, ttl; and claim_all, complete (§1.5)
holders: Dict[GroupId, Dict[int, Set[PeerId]]]        # [c9] distinct live holders, from holdings only
pushed: Dict[PeerId, Dict[GroupId, PushEntry]]        # bits, first_push, ttl               [c16]
sent_to: Dict[PeerId, Dict[GroupId, Bitmap]]          # [c12]
served: Dict[PeerId, Dict[GroupId, int]]              # new: chunks answered (R6)
promises: Dict[Tuple[Ask, PeerId], float]             # v0.3 §6.1, unchanged
offers: Dict[Ask, List[PeerId]]
tried: Dict[Ask, Dict[PeerId, float]]
asked_at: Dict[Ask, float]
park: Dict[PeerId, Dict[GroupId, float]]
standing: Dict[GroupId, Dict[int, Set[PeerId]]]       # new: WANTs for chunks we do not hold yet (§4.10)
sampled_from: Dict[BlockId, Set[PeerId]]              # new: the peers asked for a sample of a block, one each (I6) [D12]
samples_in_flight: Dict[BlockId, int]                 # new: our second-phase sample asks in flight
held_samples: Dict[BlockId, List[Tuple[GroupId, int]]]   # new: second-phase asks waiting for room
forwarded: Dict[PeerId, int]                          # new: routed requests from p passed on this slot (X6)
claims: Dict[GroupId, Set[PeerId]]                    # new: peers whose claim_all arrived (R5, §4.6)
reconsider_at: Dict[GroupId, float]                   # new: when our later decode duty fires, if armed (§4.6)
deferred: Dict[GroupId, bool]                         # new: we deferred it once on a claim (R5)
duty_at: Dict[GroupId, float]                         # new: the duty's own time when the claim deferred it (R5)
waited: Dict[GroupId, bool]                           # new: we waited once for chunks held on another axis (§4.6)
probe: Dict[GroupId, int]                             # new: the index we asked a claimant for, to verify the claim (R5)
probed: Dict[GroupId, PeerId]                         # new: the claimant we asked
probe_asks: Set[Ask]                                  # new: those asks, exempt from stop-pull until settled (§4.6)
probe_sent: Set[GroupId]                              # new: groups whose probe's WANT was written (§4.6)
probe_ok: Dict[GroupId, Optional[bool]]               # new: the probe's verdict, once: True if the claimant's own copy came;
                                                      #   None: no verdict, the probe not written in time or
                                                      #   the claimant gone (§4.6)
probe_served: Dict[PeerId, Dict[GroupId, bool]]       # new: as a claimant, p's probe of the group answered (§4.6)
probe_answers: Dict[PeerId, Dict[GroupId, Bitmap]]    # new: those answers until written, by the chunk's own group
probe_waiting: Dict[GroupId, Dict[PeerId, int]]       # new: as a claimant still decoding, p's first marked ask of the
                                                      #   group, until the cell is stored (§4.6)
rsample: Dict[GroupId, List[int]]                     # new: the repair sample's indices, asked of custodians (R5, option)
rsample_step: Dict[GroupId, int]                      # new: how many of REPAIR_SAMPLE's steps were asked
rsample_asked: Dict[GroupId, Dict[int, Set[PeerId]]]  # new: the custodians each sampled cell was asked of
rsample_final: Dict[GroupId, bool]                    # new: the last step's re-asks were waited for
```

Lifetimes are v0.3 §8.1's: per-group state lives `GROUP_TTL` past the last chunk or the completion,
or until its slot leaves the node's live window if that comes first, and leaves a tombstone until
the window has passed the slot, and the probe's tables (`probe_ok`, and `probe_served`,
`probe_answers` and `probe_waiting` for every peer) go with it, a peer's entries also with its connection (a bit of
`probe_answers` whose answer is never written stays until then), and a peer's claims go with its
connection (`claims_close`, §4.6); per-peer entries live `HAVE_TTL`
and `PUSH_TTL` heartbeats or until the connection closes; relations live until PRUNE or
disconnection, a GRAFT
of ours until it is answered, a PRUNE of either end ends it or the connection closes, an owed
JOIN, GRAFT or PRUNE until the writer queues it or the connection closes, and a backoff until it
runs out or the connection closes; `forwarded` starts again at each slot. An expired group is not
taken up again: the
receive and publish paths check it as v0.3's do, `fill` on every axis a chunk projects onto, and
the paths that act on a projected group (`forward`, `push_rebuilt`, the repair
sample's `ask_custodian`) skip an expired axis; `check_completion` finds no state to act on.
A dropped group's later chunks are not stored, forwarded, offered or kept for heartbeat gossip on
that axis (`fill`, `forward`, `push_rebuilt`), as `protocol.md`'s `on_validated` returns for one.
Offered, such a chunk would draw asks that the node does not answer, and an asker's promise could
break against an honest node.
The sampler's `sample`, `resample` and `ask_sample` check it (§4.10), so a draw or a retry after
the expiry makes no park, interest or WANT again.
Reading a missing entry allocates nothing;
the admission checks of v0.3 §8.2 and the limits of §6.3 come first. A node may hold state for a
group it has no interest in, when it holds chunks of it or a peer's interest names it (a
reconstructor's non-custodied columns, R4); the number of such groups per slot is bounded (§6.3).

**Helpers not written out**, beyond v0.3 §8.1's: `type_of_group(g)` (the object type a group id
names), `links(T)` (the peers with a JOIN for `T` both ways: theirs received, ours queued rather
than owed, §4.1), `our_join(T)` (the JOIN the node sends for `T`: its interest, custody count,
duty and `M`, §1.2), `joined_types()`, `node_id(p)`,
`in_pushers(T, fam, c)` and `out_pushees(T, fam, c)` (the peers whose relation holds that colour),
`candidates(T, fam, c, d)` (joined peers with duty whose interest holds the family, by
`link_cover`; not yet in the relation of colour `c` and direction `d`, with `BOTH` in neither; with
no GRAFT of ours for it unanswered; and out of its backoff, with `BOTH` for both directions;
§4.1), `least_used_colour(T,
fam)`, `families_with_duty(T)`, `wants_family(T, fam)`, `duty_for(g)`, `uplink_class()` (card 17),
`send(p, msg, urgent)` (a message into the bounded per-peer queue of v0.3 §7; the binding's job;
true if the queue admitted it, as v0.5's `enqueue`; the asks of a `Want` sent through it are marked
`want`, a local mark that goes on no wire, where those the pull discipline queues on an offer,
`respond`, `retry_offer` and `ask_parked`'s, are not; the two kinds go in separate ask messages
of an entry),
`Ask(g, i)` (an ask's key, v0.3's `WantIndex`), `chunk_id(f)` (v0.3's `message_id`),
`open_group(g, f)` (as v0.3's, and records `T_of`, `interest`, `known_at`), `open_group_source(g,
h)`, `group_of(block, h)` (the group a source publishes, by §1.1's table: for the payload the key of
v0.3 §1, for a column or a row its id), `interest_satisfied(g)` (§1.5), `deferred_offers(p, h)` (§4.3),
`publish_evidence(g, body)`, `sampled_types()` (the object types the node samples), `families(T)`
(every family of the type: the 128 columns), `link_cover(q, T)` (§4.1: the families whose every
index `q`'s interest holds, from its JOIN and node id, and whether `q` is of high custody, §1.3),
`high_custody(q, T)` (§1.3: `q`'s custody count above the type's base custody count, or its
interest `ALL`), `cover_candidates(T)` (§4.1: the rendezvous's nodes not yet linked, each with the
same two from its node id and custody count, before any connection), `open_sampling_link(r, T)` (§4.1: connect and JOIN as `(DECLARED,
NONE)`, through `send_join`), `floor_links(T, fam)` (§4.1: the peers the node is connected to with its
JOIN for `T` sent, a link or one forming, whose interest holds `fam` by their node id and the custody
count the rendezvous gives), `floor_candidates(T)` (§4.1: as `cover_candidates`, the rendezvous's
nodes not yet linked, each with the families its custody holds), `open_link(r, T)` (§4.1: connect
and JOIN with `our_join(T)`, through `send_join`), `route_next(T, fam, qs)` (§1.3, §4.10: of the links `qs`, those nearest `fam` by the
routing neighbours' distance between their computed custody and `fam`; all of them where the
rendezvous keeps no such rule), `block_of(g)` (the block a cell group belongs to; `g` itself for a type without blocks),
`wire_size(p, entry)` (§4.11: the bytes the entry's chunk takes on the wire to `p`, the binding's: with a
header where its write carries one),
`cell_groups(root)` (the column and row groups of a block, from their ids alone).

## 4. Events

Validation runs off the receive path as in v0.3 §4.1. The order of handling one frame (a binding's unit
on the wire, which may carry several messages; `protocol-v2-bindings.md` §0) is v0.3's:
chunks, then offers (which produce asks), then asks (which produce answers), then GRAFT and PRUNE,
then holdings, then the response.

```python
def on_frame(p, frame):
    for f in frame.chunks: on_chunk(p, f)                            # §4.2
    offers = [h for h in frame.haves if h.offer]
    if offers: ihave_frames[p] += 1                                   # offer-bearing frames, for §4.3's limits
    asks = [a for h in offers for a in on_offer(p, h)]                # §4.3
    answers = on_want(p, frame.asks)                                  # §4.5
    for gr in frame.grafts: on_graft(p, gr)                           # §4.1: it sends its own answers
    for pr in frame.prunes: on_prune(p, pr)
    for h in frame.haves:
        if not h.offer: on_holding(p, h)                              # §4.3
    respond(p, asks, answers, [])                                     # v0.3 §4.1; a GRAFT's answer goes on its own
```

### 4.1 Joining, and keeping the relations

```python
def on_join(p, j: Join):
    T = type_of(j.object_type)
    if j.colours != T.params.M: return                 # no v2 for T on this link; the stock path remains
    join_recv[p][T] = j
    if T not in join_sent[p]: send_join(p, our_join(T))   # the answer, unless ours went first

def send_join(p, j: Join):                             # every JOIN of ours, once per link and type: when the node opens
    join_sent[p][type_of(j.object_type)] = j           #   the link, a sampling link's included, or in answer to p's;
    send_relation(p, j)                                #   owed as a GRAFT is, so ahead of the type's GRAFTs and PRUNEs

def interest_of_peer(p, g) -> Bitmap:                  # what p is to receive of g, as far as we know
    T = type_of_group(g); j = join_recv[p][T]
    if j.interest == ALL: return EVERY_INDEX
    if j.interest == DERIVED: return T.derived_interest(g, hdr.get(g), node_id(p), j)
    return want_p[p].get(g, EMPTY)                      # DECLARED: only what p asked us for

def wants_from_me(p, g) -> Bitmap:                     # [I3] pushes and offers go into interest
    e = peer_has[p][g]
    if e.complete: return EMPTY
    return interest_of_peer(p, g) & ~e.bits & ~pushed[p][g]

def maintain_relations(T):                             # at the heartbeat, per family we have duty in
    for fam in families_with_duty(T):
        for c in range(T.params.M):
            ins = in_pushers(T, fam, c)
            if T.params.SYMMETRIC:                     # one relation both ways, kept as gossipsub keeps its mesh:
                if len(ins) < T.params.F_LO:           #   below the floor, graft up to D_OUT
                    for q in candidates(T, fam, c, BOTH)[: T.params.D_OUT - len(ins)]:
                        graft(q, T, fam, c, BOTH)
                elif len(ins) >= T.params.F_HI:        #   at the cap, where on_graft refuses, prune down to D_OUT
                    for q in sample_without_replacement(ins, len(ins) - T.params.D_OUT):   # at random
                        prune(q, T, fam, c, BOTH)
                half = set(in_pushers(T, fam, c)) ^ set(out_pushees(T, fam, c))   # held one way only, by lost
                for q in sorted(half):                 #   state: grafted again at any count, and the other end
                    if c not in grafted_in[q][T][fam] and c not in grafted_out[q][T][fam]:   # makes it whole
                        graft(q, T, fam, c, BOTH)      #   or refuses it (on_graft), so the ends agree
                continue
            if len(ins) < T.params.F_LO:               # the floor per colour                [D10]
                for q in candidates(T, fam, c, IN)[: T.params.F_LO - len(ins)]:
                    graft(q, T, fam, c, IN)            # "push me": counted once q says yes
            if len(ins) > T.params.F_HI:
                for q in ins[T.params.F_HI:]:
                    prune(q, T, fam, c, IN)            # "stop pushing me"
            outs = out_pushees(T, fam, c)
            target = T.params.D_OUT_FAST if uplink_class() == FAST else T.params.D_OUT    # [c17]
            for q in candidates(T, fam, c, OUT)[: max(0, target - len(outs))]:
                graft(q, T, fam, c, OUT)               # "I will push you": pushed once q says yes

def graft(q, T, fam, c, d):                            # our GRAFT: nothing is counted until q answers it
    if d in (IN, BOTH): grafted_in[q][T][fam].add(c)
    if d in (OUT, BOTH): grafted_out[q][T][fam].add(c)
    send_relation(q, Graft(object_type=T.id, family=fam, colour=c, direction=d, answer=False))

def prune(q, T, fam, c, d):                            # our PRUNE: the relation ends at our end at once
    if d in (IN, BOTH): push_in[q][T][fam].discard(c); grafted_in[q][T][fam].discard(c)
    if d in (OUT, BOTH): push_out[q][T][fam].discard(c); grafted_out[q][T][fam].discard(c)
    send_relation(q, Prune(object_type=T.id, family=fam, colour=c, direction=d))

def yes(p, T, fam, c, d):                              # an accepted GRAFT's answer, from our side: not answered where held
    send_relation(p, Graft(object_type=T.id, family=fam, colour=c, direction=d, answer=True))

def no(p, T, fam, c, d):                               # a refused GRAFT's answer, from our side
    send_relation(p, Prune(object_type=T.id, family=fam, colour=c, direction=d))

def on_graft(p, gr: Graft):                            # each direction answered: a GRAFT is yes, a PRUNE no
    T = type_of(gr.object_type); fam, c = gr.family, gr.colour
    if T.params.SYMMETRIC:                             # one relation both ways: decided as one, one answer
        asked = c in grafted_in[p][T][fam] or c in grafted_out[p][T][fam]   # the yes to ours, or a crossing
        grafted_in[p][T][fam].discard(c); grafted_out[p][T][fam].discard(c)
        held = c in push_in[p][T][fam] or c in push_out[p][T][fam]   # either way: held, made whole again
        if held or (len(in_pushers(T, fam, c)) < T.params.F_HI and wants_family(T, fam)
                    and join_sent[p][T].duty == FORWARD):
            push_in[p][T][fam].add(c)
            if not asked and not (held and gr.answer): yes(p, T, fam, c, BOTH)   # held: yes again, unless a yes
            join_push(p, T, fam, c)                    # and push_out: what we hold is announced
        else:
            no(p, T, fam, c, BOTH)
        return
    if gr.direction in (OUT, BOTH):                    # p will push us colour c
        asked = c in grafted_in[p][T][fam]             # the yes to our "push me", or a GRAFT that crossed it
        grafted_in[p][T][fam].discard(c)
        if c in push_in[p][T][fam]:                    # held: yes again, unless it answers ours or is a yes
            if not asked and not gr.answer: yes(p, T, fam, c, IN)
        elif len(in_pushers(T, fam, c)) < T.params.F_HI and wants_family(T, fam):
            push_in[p][T][fam].add(c)
            if not asked: yes(p, T, fam, c, IN)        # yes: "push me"
        else:
            no(p, T, fam, c, IN)                       # no: "stop pushing me"
    if gr.direction in (IN, BOTH):                     # p asks us to push it colour c
        asked = c in grafted_out[p][T][fam]            # the yes to our "I will push you", or one that crossed it
        grafted_out[p][T][fam].discard(c)
        if c in push_out[p][T][fam]:                   # held: yes again, unless it answers ours or is a yes
            if not asked and not gr.answer: yes(p, T, fam, c, OUT)
        elif join_sent[p][T].duty == FORWARD and len(out_pushees(T, fam, c)) < T.params.D_OUT_MAX:
            if not asked: yes(p, T, fam, c, OUT)       # yes: "I will push you"
            join_push(p, T, fam, c)                    # in the relation at our end: what we hold is announced
        else:
            no(p, T, fam, c, OUT)                      # no: "I will not push you"

def join_push(p, T, fam, c):                           # p joins our push relation for colour c: what we hold of
    if c in push_out[p][T][fam]: return                #   it is announced (protocol.md §5.4's on_mesh_join);
    push_out[p][T][fam].add(c)                         #   a GRAFT that adds nothing runs nothing
    for g in list(chunks):
        if expired(g) or state[g] == INVALID or type_of_group(g) != T or T.family(g) != fam: continue
        announce(p, g, bitmap({i for i in chunks[g] if colour_of(g, i) == c}))   # stored, received or rebuilt,
                                                       #   minus what p holds, was pushed or does not want (§4.4)

def on_prune(p, pr: Prune):                            # p's no, or p's end of the relation: ours ends too
    T = type_of(pr.object_type); fam, c = pr.family, pr.colour
    d = BOTH if T.params.SYMMETRIC else pr.direction   # a symmetric relation ends both ways
    until = now + T.params.PRUNE_BACKOFF               # and is not grafted again before then
    if d in (OUT, BOTH):                               # "I stop pushing you", "I will not push you"
        push_in[p][T][fam].discard(c); grafted_in[p][T][fam].discard(c)
        backoff[p][T][fam][(c, IN)] = until            #   our "push me" waits
    if d in (IN, BOTH):                                # "stop pushing me"
        push_out[p][T][fam].discard(c); grafted_out[p][T][fam].discard(c)
        backoff[p][T][fam][(c, OUT)] = until           #   our "I will push you" waits

def send_relation(p, m):                               # a JOIN, GRAFT or PRUNE is never lost to a full queue: one
    if owed_relations[p] or not send(p, m, urgent=isinstance(m, Join)):   #   refused, and every later one, is
        owed_relations[p].append(m)                    #   owed in order; a JOIN keeps the urgent lane
        wake(p)

def queue_owed_relations(p):                           # the writer, before anything else (§4.11)
    while owed_relations[p] and has_room(p):
        m = owed_relations[p].pop(0)
        send(p, m, urgent=isinstance(m, Join))

def propose_colour(T, fam) -> int:                     # balanced colouring
    return least_used_colour(T, fam)

def serves(q, g, i) -> bool:                           # §1.3: q's interest holds index i of g, so q will hold it
    T = type_of_group(g)
    return join_recv[q][T].interest != DECLARED and interest_of_peer(q, g).has(i)

def counted(need, r, T) -> List[FamilyId]:            # §1.3: the short families r covers; one of high custody
    short = [fam for fam in r.families if need[fam] > 0]   #   counts for at most COVER_HIGH of them (diversity)
    return short[: T.params.COVER_HIGH] if r.high else short

def keep_coverage(T):                                  # at the heartbeat, for a type we sample (§1.3)     [D12]
    need = {fam: T.params.SAMPLE_COVER for fam in families(T)}
    for q in links(T):                                 # every link counts, whatever it was opened for
        for fam in counted(need, link_cover(q, T), T): need[fam] -= 1
    while any(n > 0 for n in need.values()):
        cs = [r for r in cover_candidates(T) if counted(need, r, T)]   # node ids and custody counts: before connecting
        if not cs: return                              # nobody for those families now; the next heartbeat retries
        best = max(len(counted(need, r, T)) for r in cs)
        r = choice([r for r in cs if len(counted(need, r, T)) == best])   # most families covered, at random among equals
        open_sampling_link(r, T)                       # JOIN (DECLARED, NONE): no relation, no push, no offer
        for fam in counted(need, r, T): need[fam] -= 1

def keep_floor(T):                                     # at the heartbeat: the links §1.4's floor forms on
    for fam in families_with_duty(T):
        short = T.params.F_LO - len(floor_links(T, fam))   # a link counts from its opening, joined or not
        if short <= 0: continue
        rs = [r for r in floor_candidates(T) if fam in r.families]   # node ids and custody counts: before connecting
        for r in sample_without_replacement(rs, min(short, len(rs))):
            open_link(r, T)                            # JOIN; maintain_relations grafts on it
```

Scoring GRAFT floods is the client's, as in gossipsub, and so is the backoff after a PRUNE on
gossipsub's wires (§7); what this document fixes is that a relation exists only after both ends agreed it, and
how each end learns that. A PRUNE names its direction from its sender's side, as a GRAFT does, so
`on_graft` refuses an offer to push with `IN` and a request to be pushed with `OUT`.

**A GRAFT is answered.** A node that accepts a GRAFT says so with its own GRAFT for the same
relation, from its side: an offer to push it is answered "push me", a request to be pushed "I will
push you". A node that refuses it answers with a PRUNE, as before.
- **Each end's relation.** The answering end is in the relation from its yes. The GRAFT's sender
  keeps its GRAFT unanswered (`grafted_out`, `grafted_in`) and is in the relation from the yes it
  receives: only then does it push, count the pusher, or send it holdings. A GRAFT of the other end
  that crosses its own on the wire is that yes, so two ends that graft each other at once agree
  without a third message. A yes that comes when the relation is no longer wanted is refused, as a
  GRAFT would be. An unanswered GRAFT counts for nothing: its peer is not grafted again meanwhile,
  and the next heartbeat grafts another candidate while the floor is short.
- **A PRUNE ends the relation at both ends**: at its sender's at once, at the receiver's when it
  arrives, and with it any GRAFT of the receiver's for that relation still unanswered. A GRAFT that
  reaches a node with nothing of its relation is a new one and is answered; one that reaches a node
  holding the relation is answered yes again (below).
- **Order.** The answer rests on a link's GRAFTs and PRUNEs arriving in the order they were sent.
  The queue keeps control in its order (§4.12). One that a full queue refuses is owed, every later
  one waits behind it, and the writer queues them in that order once there is room
  (`send_relation`, `queue_owed_relations`, §4.11), so none is lost while the connection lasts. A
  binding that merges entries puts at most one GRAFT or PRUNE of a relation in one frame.
- **For a moment, not at rest,** the ends can differ where a PRUNE crosses a later GRAFT of the
  same relation: the PRUNE also ends that GRAFT at its sender, while the other end may accept it.
  For as long as the yes takes to arrive, one end is in a relation the other has left; the yes then
  reaches an end with nothing of the relation and is decided as a new GRAFT.
- **On gossipsub's wires** (§7) no answer comes, since a stock peer accepts in silence. There a
  GRAFT's sender is in the relation from its GRAFT and runs `join_push` at once, as `protocol.md`
  §5.4 does, and the two ends' agreement rests on gossipsub's backoff after a PRUNE.

**A GRAFT for a relation already held is answered yes again.** A node that holds a relation and
receives a GRAFT for it answers yes again (`yes`), where it answered nothing
before, unless that GRAFT is the yes to its own GRAFT or is itself a yes.
- **A yes is marked.** A yes is itself a GRAFT, so an end that answered every GRAFT for a relation
  it holds would answer a yes. Where a PRUNE crosses a later GRAFT (above), both ends then hold the
  relation and would answer each other's yes for ever. So a GRAFT says whether it is a yes
  (`answer`, §2), and a yes for a relation its receiver holds is not answered. A yes that reaches
  an end with nothing of the relation is still decided as a new GRAFT, and answered as one.

**A symmetric relation.** A type with `SYMMETRIC` keeps one relation both ways per family and
colour; gossipsub's mesh is such a type, with `M = 1`, `F_LO = Dlo`, `F_HI = Dhi` and `D_OUT = D`
(§6.1). Its GRAFTs and PRUNEs have direction `BOTH`. A GRAFT is decided as one at the receiver, by
its cap `F_HI`, its own part in the family and its duty, and answered with one GRAFT or one PRUNE; a
PRUNE ends both directions. A GRAFT for a relation the receiver holds in either direction makes it
whole there and is answered yes again (above). The node keeps the relation as gossipsub's heartbeat
keeps its mesh: below `F_LO` it grafts up to `D_OUT`, and at `F_HI` it prunes down to `D_OUT`,
choosing at random. A relation it holds in one direction only, by lost state or a peer's error, it
grafts again at any count, unless its own GRAFT for it is unanswered: the other end makes it whole
and answers yes, or refuses it, and the ends agree either way. Without this, a relation held one way
stays so wherever no count calls for a GRAFT or a PRUNE: an end grafts only a peer outside the
relation, below its floor, and prunes only at its cap.
- **One-way relations** are kept as before: their in-relation between `F_LO` and `F_HI`, their
  out-relation at `D_OUT`.

**A candidate's interest holds the family.** `candidates` takes only peers whose interest holds the
family (`link_cover`), in both directions: a peer asked to push the family receives it only then, and
a peer offered it wants it only then.

**The backoff after a PRUNE.** A PRUNE that a node receives starts a backoff for the relation it
names, from the receiver's side: the peer, type, family, colour and direction. Until the backoff
runs out, `candidates` passes that peer over for that relation. A GRAFT the peer sends meanwhile is
decided as any other. `PRUNE_BACKOFF` is stated by its bounds (§6.3).
- **Its bounds.** At least a round trip, so that a peer that refused is not asked again before its
  refusal could change. At most how long a node may stay below its floor once its candidates have
  refused: a deficit lasts until a GRAFT after the backoff is accepted.
- **Agreement is not touched.** The backoff only holds back when a node grafts, never how a GRAFT
  or PRUNE is handled. On gossipsub's wires the backoff is gossipsub's (§7).

**A JOIN is owed too.** A node sends its JOIN for an object type once per link, through `send_join`:
when it opens the link, a sampling link's included (`open_sampling_link`), or in answer to the
peer's (`on_join`).
- **Owed as a GRAFT is.** A JOIN that a full queue refuses is owed, every later JOIN, GRAFT and
  PRUNE of the connection waits behind it, and the writer queues it on the urgent lane, where a
  JOIN goes, once there is room. `join_sent` records it at once, sent or owed, so the node never
  sends two.
- **No link before it.** The node counts the peer as a link for the type (`links`) only once its
  own JOIN is queued, so its JOIN reaches the peer before any GRAFT, holding, offer or WANT of the
  type.
- **On gossipsub's wires** a JOIN is a subscription (§7): both ends send theirs when the
  connection opens, and one made later goes to every peer, so none is an answer. A sampler's
  `(DECLARED, NONE)` writes nothing there, so it is never owed (`protocol-v2-bindings.md` §4).

**A peer that joins a push relation is announced what the node holds.**
- **What is announced** (`join_push`): what the node stores of each live group of the relation's
  family, received or rebuilt, of the relation's colour, minus what the peer holds, was pushed or
  does not want (`announce`). Not the decode claim, nothing of an expired or dropped group.
- **When.** It runs where a relation in which the node pushes comes into being at its end: at a
  GRAFT it accepts, and at the yes to its own (`on_graft` either way), a round trip after
  `protocol.md`, which runs it at the node's own GRAFT at once. On gossipsub's wires it runs there
  too, as in `protocol.md`. A GRAFT that adds nothing runs nothing. Relations end with the
  connection, so a reconnection is announced again once it is grafted again.

**`keep_coverage` reads custody, never a sample:** it runs before the node knows what it will sample,
and whatever it samples. A node of high custody counts for at most `COVER_HIGH` families. A
sampling-only link that has served nothing for a while is not pruned for that; how long the floor's
links are kept, and whether they rotate, is the rendezvous's (§8).

**The floor's links.** `keep_floor` keeps, for each family a node has duty in, at least `F_LO` links
to peers whose interest holds the family: the links that §1.4's floor per colour forms on. A link
counts from its opening, joined or not, so that a node opens no second link while the first one's
JOINs cross. The links it opens are drawn at random from the rendezvous's nodes whose custody holds
the family, each with the node's own JOIN, and `maintain_relations` grafts on them.
- How long its links are kept, and whether they rotate, is the rendezvous's, as for the coverage
  floor.

#### Rationale

**A refusal names its direction from its sender's side** (decided 2026-11-01). The refusals had echoed
the GRAFT's direction, which undid the opposite relation at the grafter.

**A GRAFT is answered** (decided 2026-11-04).
- **Why.** Silence cannot tell a yes from a GRAFT not yet read, refused by a full queue or ignored.
  Counted at once, a GRAFT that is never accepted leaves its sender pushing a peer that does not
  count it, or counting a pusher that does not push, and the floor per colour (§1.4) is only as
  good as its count. Gossipsub keeps the two ends' views together with its backoff after a PRUNE,
  which must outlast the round trip at both ends. Here the agreement rests on no timer, and the
  backoff only paces the next GRAFT. The cost is a control message per accepted GRAFT, and an offer
  to push takes effect a round trip after the GRAFT, where silence let it start at once; a request
  to be pushed takes effect when the pusher says yes, as before. A peer that agrees and then does
  not push is not caught by this, as it was not before.
- **Checked** (`toy/graft_check.py`): this section's functions as written, on two nodes, from the
  link's first JOIN, sent by either end or both, for one relation over an ordered connection with
  queues of one entry and other traffic taking their room, each end's upkeep grafting or pruning up
  to three times and every GRAFT accepted or refused at will. In each of the 846 states of 2 367 518
  with nothing queued, owed or on the wire (1 484 804 before the yes again, below), the two ends
  agree and no GRAFT is unanswered, and every exchange ends. The check fails where it should: on the
  text before this rule (`toy/controls/graft-unanswered.md`), where the GRAFT's sender recorded
  nothing (the ends disagree in 324 of 724 such states at two upkeep steps), and on this rule
  without the owing, with an owed message overtaken, without the yes, or with a PRUNE that leaves
  the receiver's GRAFT standing. The toy's recorded cells keep their relations static and do not run
  this; under `--upkeep on` it runs this section on the wire.
- **Compared** (`toy/graft_check.py --model`: one relation in the abstract, without queues, four
  upkeep steps per end): counted at the GRAFT, 32 of 81 states at rest disagree without a backoff,
  and none of 121 with a backoff longer than the round trip; answered, none of 49.

**A GRAFT for a relation already held is answered yes again** (decided 2026-11-09).
- **Why.** From ends that agree, the rules keep them agreed (Checked, above). Where they diverge,
  one end in a relation the other has left through lost state or a peer's error, the other end's
  GRAFT for that relation went unanswered: its sender kept it unanswered and never grafted that peer
  again for the relation, while the receiver counted a pusher that did not push, or pushed a peer
  that did not count it. Answered yes again, the sender joins the relation it asked for, and the
  ends agree.
- **Checked** (`toy/graft_check.py --diverged`). The check starts from linked ends that disagree:
  one counts a pusher that does not push, or pushes a peer that does not count it; with `--both`,
  the two ends hold the relation in any way but whole at both or at neither. At three upkeep steps,
  every state at rest once an upkeep has acted agrees, with no GRAFT unanswered, and every exchange
  ends: 1 175 922 states, and 4 647 412 with `--both`. The text before
  (`toy/controls/held-graft-unanswered.md`) fails: a GRAFT for a relation the receiver holds goes
  unanswered (18 of 117 states at rest, at two steps). Without the mark, the check finds an exchange
  that never ends, at two steps. One end's PRUNE crosses the other's later GRAFT, the first end
  accepts that GRAFT, the second decides its yes as a new GRAFT, and the two then answer each
  other's yes for ever.

**A symmetric relation** (decided 2026-11-09).
- **Why at `F_HI`.** Gossipsub's heartbeat prunes a mesh above `D_high` down to `D`, and a mesh gets
  there because, at `D_high`, gossipsub v1.1 refuses only a GRAFT from an inbound connection. Here
  `on_graft` refuses at `F_HI` for every peer, so a prune that waited for more than `F_HI` would never run: the relations
  would rest wherever the GRAFTs left them, near `F_HI`, and cost more bytes wherever every relation
  is pushed (tier 1). In the toy (the payload at 60 nodes and degree 30, under `--upkeep on` with 20
  links replaced per message gap, six messages, seed 7): with a prune only above `F_HI` no node was
  ever pruned and nodes ended at 12, the relations averaging 8.5 per node. With the prune at `F_HI`,
  24 PRUNEs left no node above 11, and the average was 7.9.
- **Why at random.** A capped relation is first come, first served: a full node refuses later
  GRAFTs, and near peers' GRAFTs arrive first, so the relations lean on near peers. Gossipsub's prune
  keeps `D_score` peers by score and the rest at random; scoring is the client's, and the draw is
  this rule's.
- **Checked** (`toy/graft_check.py --both`: both ends graft the relation below `F_LO` and prune it at
  `F_HI`). At three upkeep steps, in each of the 846 states of 2 755 607 at rest, the ends agree in
  both directions and each end holds both or neither, with no GRAFT unanswered, and every exchange
  ends. In every state at rest of these runs and of `--both --diverged` (above), an end that holds
  the relation one way acts on it with its count between its floor and its cap. The text without
  that step fails there: in 108 states at rest, at three steps, an end holds the relation one way
  and neither end's upkeep acts, the first where one end counts it and the other holds nothing.

**A candidate's interest holds the family** (decided 2026-11-09).
- **Why.** Before, `candidates` took any joined peer with duty, so a column's relations could form with
  peers that neither receive nor want the column, and they carried nothing. The toy has read it this
  way since its upkeep was built.

**The backoff after a PRUNE** (decided 2026-11-09).
- **Why.** Before, the backoff was the client's, and the standalone binding has no client under it,
  so `candidates` asked again, at the next heartbeat, a peer that had just refused. Where most of a
  short node's candidates are at their cap for the relation, a draw at random keeps landing on them:
  with one-way relations capped near their targets the refused GRAFTs repeat at every heartbeat,
  and the relations can take many heartbeats to rest, or not rest within a run.
- **Checked.** Since the backoff touches only when a node grafts, every state `toy/graft_check.py`
  reaches with it is one it reaches without, and the check runs at a backoff of 0.

**A JOIN is owed too** (decided 2026-11-04).
- **Why.** Before, a JOIN that a full queue refused was lost, and the link for the type with it
  until the connection closed: the peer never had the node's JOIN, so it never counted the node as
  a link. Such a JOIN is one that opens the type, or answers the peer's, on a connection already
  busy with another type.
- **Checked** with the GRAFT (`toy/graft_check.py`, above): at rest, once either end has sent its
  JOIN, both ends hold each other's, and no GRAFT or PRUNE ever reaches a node that has no link for
  it. The check fails on the text before (`toy/controls/join-lost.md`), where a JOIN a full queue
  refused was lost (in 40 of 508 states at rest, at two upkeep steps, a JOIN was sent and the link
  did not form), and where `send_join` records its JOIN but does not owe it (a GRAFT then reaches a
  node that has no link for it).

**A peer that joins a push relation is announced what the node holds** (2026-10-26, from
`protocol.md` §5.4's `on_mesh_join`).
- **Why.** Offers come from `forward`, at a chunk's arrival, to the relation for its colour (§4.4).
  Nothing else offers a peer that joins the relation after the chunk was forwarded, nor a peer whose
  connection closed what the old connection lost. Heartbeat gossip goes only to peers outside the
  relations, offers the last three heartbeats' chunks, and only for a type whose `ANNOUNCE_EXTRA` is
  `SAMPLE` (§4.8). A holding is not an offer (§4.3). Derived interest lets a custodian be asked
  without an offer (§4.5), but only samplers, routed requests, the repair sample and a custodian's
  alarm ask that way (§4.6, §4.10).
- **The toy's recorded cells** keep their relations static and do not run this; under
  `--upkeep on` it runs.

**`keep_coverage` reads custody, never a sample.** The links it opens say nothing about the sample
(§1.3). With a node of high custody counted for at most `COVER_HIGH` families, the floor rests on many
peers of ordinary custody rather than on one that claims everything: custody counts are self-declared,
and a node that claims every column would otherwise attract every sampler's floor, its samples and its
load. A sampling-only link is not pruned for serving nothing, since its use is the samples it may serve.

**The floor's links** (decided 2026-11-09).
- **Why.** Nothing kept that floor at runtime before. `maintain_relations` grafts only among the
  links the node has, and only `keep_coverage` opened links, for a sampler's floor (§1.3). Yet the
  draft assumes it: the rendezvous is per family (§1.1), and §8's route leans on custodians keeping
  a floor per column.
- **Measured** in the toy (500 nodes at degree 70, its custody setting with a fifth of the nodes
  sampling, two blocks a run, 1 % and 5 % of the links replaced per message gap, seeds 7 to 16).
  Without it, for 8 to 11 % of the nodes at the ends of a closed link, at every seed, the number of
  their (family, colour) below `F_LO` had not come back by the run's end to what it was before the
  close; with it, for 0.1 to 1.2 %. It also removed 84 to 91 % of churn's excess in the
  share of (node, family, colour) below `F_LO`, the share averaged over the heartbeats from the
  first block on, against the same cells without churn. Its cost per node and gap, paired by seed,
  was 0.14 to 0.19 JOINs and 0.30 to 0.44 GRAFTs more at 1 %, and 0.69 to 0.88 and 1.53 to 1.92 at
  5 %. Every node completed, and the warm block's 99th percentile moved within the toy's noise.
  These runs predate 2026-11-16. Since then, the toy's close also drops the closed peer's offers,
  tries, promises and ties, and keeps its park (§3's lifetimes, `protocol.md` §8.1). They were not
  run again.

### 4.2 A chunk arrives

```python
def on_chunk(p, f):
    mid = chunk_id(f)
    if seen(mid) or mid in pending_ids:                # a duplicate, a chunk rejected before, or one waiting
        if accepted(mid):                              # (R5) the claimant's copy passes its probe, a duplicate too
            for (g, i) in type_of_group(f.group).project(f): probe_answer(g, i, p)
            send_have(p, f.group)                      # [c14] duplicates are acknowledged too
        elif mid in pending_ids: tie(p, f)             # another copy of one that waits: its sender too
        return
    if expired(f.group) or not live(f.slot): return    # past its lifetime or live window (v0.3 §8.1)
    T = type_of_group(f.group)
    on_validated(p, f, T.verify(f, T.header_of(f)))   # level 1; DEFER while the gate is closed

def on_validated(p, f, result):
    if expired(f.group) or not live(f.slot): return    # expired or out of the window meanwhile (v0.3 §8.1)
    if result == DEFER: return defer(p, f)             # v0.3 §4.2: the bounded per-peer store
    mark_seen(chunk_id(f))                             # accepted or rejected: never validated again
    if result == REJECT: return penalise(p)            # level 1 failures are the sender's
    T = type_of_group(f.group)
    new = [(g, i) for (g, i) in T.project(f) if not received[g].has(i)]   # a second id for a received index: only acknowledged (fill), as v0.3
    for (g, i) in T.project(f): fill(g, i, f, p)       # (R4) one arrival fills every group it belongs to
    acting = [(g, i) for (g, i) in new if not expired(g) and state[g] != INVALID]   # a dropped group is not acted on (§4.6)
    if any(duty_for(g) == FORWARD for (g, i) in acting): forward(f, p, acting)   # §4.4: on any axis we serve; never waits for level 2
    for (g, i) in T.project(f): check_completion(g)    # §4.6

def fill(g, i, f, p):
    if expired(g): return                              # an expired group is not taken up again (v0.3 §8.1)
    if g not in T_of:
        open_group(g, f)                               # hdr[g], T_of[g], interest[g], known_at[g]
        drop_beyond(g)                                 # what named an index it has not goes (protocol.md §4.2, §8.2)
    if state[g] == INVALID: return                     # a dropped group (§4.6)
    if received[g].has(i) or rebuilt[g].has(i):        # a copy of a chunk we hold: acknowledge it
        probe_answer(g, i, p)                          # (R5) a duplicate from the claimant passes its probe too
        return send_have(p, g) if p is not None else None
    store(g, i, f)
    (received if p is not None else rebuilt)[g].set(i) # from the network, or from our own decode (§4.6, R4)
    probe_answer(g, i, p)                              # (R5) the claimant's own copy passes its probe
    kept = probe_promise(g, i)                         # (R5) another peer's copy leaves the probe's promise open
    close_promises(g, i)                               # [c5] the chunk arrived, from anyone
    if kept: promises[kept[0]] = kept[1]
    serve_standing(g, i)                               # §4.10: WANTs that preceded it are answered now
    serve_waiting_probe(g, i)                          # (R5) and a probe that reached us while we decoded
    claim = not mine[g].has(i)                         # not yet claimed (a node past K claimed everything)
    if claim: mine[g].set(i)                           # [c7] only chunks that passed level 1
    ack = {p} if p is not None else set()              # [c14] the sender's acknowledgement
    for q in (suppression_scope(g) | ack) if claim else ack:
        send_have(q, g)                                # [c7] the holding to our pushers, [c14] the sender's ack

def suppression_scope(g) -> Set[PeerId]:
    T = type_of_group(g); fam = T.family(g)
    return {q for q in links(T) if push_in[q][T][fam]}   # whoever may push this family to us

def send_have(p, g):                                   # [c7] a holding: the whole bitmap, urgent
    h = holding_of(g, have_bits(g))
    if g in origin and MERGE_HOLDINGS and merge_waiting(p, h): return   # [P4] merged (§4.7)
    send(p, h, urgent=True)

def holding_of(g, bits) -> Have:                       # §1.5: the two claims are not the same
    n = type_of_group(g).index_count(hdr[g])
    if g in origin:                                    # [P4] a group we publish claims only what has arrived:
        whole = done = popcount(bits) >= n             #   both claims once every chunk is known to, none before
    else:
        whole, done = state[g] == DECODING or popcount(mine[g]) >= n, stop_pull[g]
    return Have(group=g, bits=bits, offer=False, claim_all=whole, complete=done)
```

`have_bits(g)` is v0.4's (§4.2 there): what we hold, or for a group we publish what is known to
have arrived (§4.7). `merge_waiting(p, h)` is the binding's, used only where the node merges (`MERGE_HOLDINGS`,
§6.3, permitted):
if a holding of `h.group` to `p` is still in our queue, it now names its own bits and `h`'s, with
`h`'s claims, and the call returns True.

**A second copy of a received index goes no further,** axis by axis. A copy under an id the node
has seen is acknowledged if that id was stored (`on_chunk`). One under an id it has not seen goes
through level 1; where it passes, on an axis whose index the node has already received it is
acknowledged there (`fill`, which also answers a waiting probe) and not forwarded there, as
`protocol.md` §4.2 does with "a second copy of an index under another id". `on_validated` forwards
only on the live axes, with duty `FORWARD`, whose index it had not received before the copy, and the
copy is kept for heartbeat gossip only if it is forwarded on some axis. An index held only as
rebuilt, or one the node published, is not received, so a copy of it is forwarded. A network arrival
sets every live axis received at once, so an axis left without the index beside one that has it
received is one expired or dropped at that arrival, which `on_validated` does not act on.

The gate is the object type's: the installed block for the payload (its descriptor comes from the
bid; `validate_chunk` returns DEFER before it), a validated header for cells, which may precede the
block. A deferred chunk is held in the bounded per-peer store of v0.3 §4.2 and §8.2 and resumes
when the gate opens. `authenticable(g)` is the gate of `g`'s type: nothing of `g` is asked for
before it opens, and what was offered meanwhile is asked for when it does: for the payload at v0.5's
`on_block_installed` (its §3, §4.4), for cells when the binding first validates a block's header:

```python
def defer(p, f):                                      # protocol.md §4.2's, at the gate of f's type: the block for
    T = type_of_group(f.group)                        #   the payload, the cell header for cells
    result = T.verify(f, T.header_of(f))
    if result != DEFER: return on_validated(p, f, result)   # the gate opened in the meantime
    if not admitted(p, f): return                     # a group beyond the peer's unknown groups (protocol.md §8.2):
                                                      #   ignored, neither kept nor tied
    tie(p, f)                                         # kept or refused, its sender is tied to the root it names
    if reserve(p, f):                                 # a per-peer reservation in the bounded store (v0.3 §8.2)
        pending[f.beacon_block_root].append((p, f))
        pending_ids.add(chunk_id(f))
    # refused: the copy is not kept, so a later copy is evaluated afresh; its sender stays tied

def on_header_validated(root):                       # (P2) a block's cell header, validated once: the cells'
    groups = set(cell_groups(root))                   #   gate, as installation is the payload's (protocol.md §4.2)
    cells = [(p, f) for p, f in pending[root] if f.group in groups]
    pending[root] = [(p, f) for p, f in pending[root] if f.group not in groups]   # the payload waits for the block
    for p, f in cells:                                # the cells that waited resume level 1
        pending_ids.discard(chunk_id(f)); release(p, f)
        T = type_of_group(f.group)
        on_validated(p, f, T.verify(f, T.header_of(f)))
    for p, held in tied[root].items():                # their senders' ties for the root's cell groups release:
        for g in [g for g in held if g in groups]:    #   parks lift, last-resort counts clear, each an offer again
            bits = held.pop(g)
            if expired(g): continue
            park[p].pop(g, None)
            for i in bits:
                asked_parked[(g, i)].discard(p)
                if g in hdr and i >= type_of_group(g).index_count(hdr[g]):   # an index the group, known now,
                    continue                          #   has not is dropped (protocol.md §8.2), the others kept
                if not mine[g].has(i): add_offer(Ask(g, i), p)
    for p in [p for p, held in tied[root].items() if not held]:   # a sender with nothing left tied under
        del tied[root][p]; tie_slot.pop((root, p), None)          #   the root: its tie's slot goes too (§8.1)
    if not tied[root]: tied.pop(root, None)
    for g in groups:                                  # every column and row group of the block
        for a in ledger(g): retry_offer(a)            # offered meanwhile, or released, asked for now (v0.5 §4.4)
```

**A copy that waits ties its sender,** as in `protocol.md` §4.2 and §6.1.
- **The tie.** A deferred copy, kept or refused, ties its sender to the root it names, for its group
  and index (`tie`); so does another copy of one that waits (`on_chunk`, as in `protocol.md`). The
  sender is not asked for that index while it waits: not by `on_offer`, nor by `protocol.md`'s
  `retry_offer`, `last_resort` or `ask_parked`, which this document takes as they are, nor by
  `filter_entry` (§4.6).
- **The release.** The gate's opening releases the ties: each sender's park for the group lifts,
  the last resort's count for its indices clears, and each index is its offer again; an index the
  group does not have, once its count is known, is dropped instead. A sender with nothing
  left tied under the root loses the slot its ties recorded (`tie_slot`). For the payload this is at
  the block's installation (`on_block_installed`); for cells it is at the header
  (`on_header_validated`, above).
- **What waits is bounded** as in `protocol.md` §4.2 and §8.1, since v0.10, for both object types.
  A copy of a group beyond its sender's limit of unknown groups is ignored, neither kept nor tied
  (`defer`). When a group opens, at its first valid chunk, what named an index beyond its count
  goes: offers, asks, promises, tries and ties (`drop_beyond`, from `fill`). And at each heartbeat,
  what waits for a gate that never opens goes once its slot leaves the live window or its group
  expires (`drop_stale_waits`, from `on_heartbeat`).
- **Tables by group and index** (a note, not a rule). The pseudocode finds what names one chunk by
  scanning whole tables: `drop_beyond` when a group opens, and `protocol.md`'s `close_promises` at
  every arrival, over every promise, offer, try and ask the node holds. That keeps it short, and the
  result is the same either way. An implementation is expected to index these tables by group and
  index, so that an arrival costs a lookup, not a pass over everything the node tracks.
- **Ordering.** `defer` here waits for the gate of the chunk's own type; `protocol.md`'s waited
  for the block alone. Cells leave the store and their ties at the header, so a binding validates
  a block's cell header no later than it installs the block.
- **The second-ask rule.** No second ask of a peer for a chunk while an earlier one is outstanding,
  queued or promised (`outstanding`, `protocol.md` §6.1): `on_offer` passes over such a peer.
- **An ask goes with its announcer's offers** (`protocol.md` §6.1). Where a peer's offers of a chunk
  are dropped, with its tie (`drop_tie`) or 30 s after its last offer of the group, an ask of the
  chunk still queued to it is removed and its promise for the chunk closes (`drop_offer`). This
  document drops offers only on `protocol.md`'s paths, so the rule applies to both object types as
  written.

#### Rationale

**A copy that waits ties its sender** (2026-10-26, from `protocol.md` v0.8; v0.5's offer of a refused
copy is gone).

**A block's cell header before the block** (decided 2026-11-01). The installation would otherwise
resume the cells with the payload's check and drop their ties as forgeries.

**An ask goes with its announcer's offers** (from `protocol.md` v0.8, 2026-10-28). Kept, the ask would
leave the peer outstanding: `on_offer` would pass over its next offer, a parked announcer's offer
would draw no last resort while this peer is unparked, and once its promise fell due nothing would
ask either again, a stall.

**In the toy** cells carry their header, so their gate is open from the first cell and neither
`defer` nor `on_header_validated` runs there; `toy/v2_carried_known.py` calls the latter by hand.

### 4.3 A holding or an offer arrives

```python
def on_holding(p, h: Have):                            # v0.3 §4.3's on_have
    if expired(h.group): return                        # past its active lifetime: ignored
    if not valid_have(h): return penalise(p)           # length, and indices within N once known
    e = peer_has[p][h.group]                           # created at p's first holding for the group
    newly = h.bits & ~e.bits
    e.bits |= h.bits
    e.ttl = HAVE_TTL                                   # heartbeats; refreshed by each holding from p
    e.claim_all = e.claim_all or h.claim_all           # [c10]
    e.complete = e.complete or h.complete              # nothing more need go to p for this group (§1.5)
    if h.claim_all: note_claim(p, h.group)             # (R5) §4.6: it may defer a decode duty of ours
    for i in newly:
        holders[h.group][i].add(p)                     # [c9] distinct live holders
        window_release(p, h.group, i)                  # [c14] a slot to p frees when p holds i, from anyone
        if h.group in planned: origin_acked(h.group, i)   # [c3, P4] a copy of i exists elsewhere (§4.7)

def on_offer(p, h: Have):                              # v0.3 §4.4's on_ihave over one group's bitmap; returns asks
    g = h.group
    if expired(g): return []
    if not valid_have(h):                              # held to a holding's limits, as protocol.md §4.4 holds an
        penalise(p); return []                         #   IHAVE's bitmap: ignored, and counted (§8.2)
    if now - known_at[g] < type_of_group(g).params.START_DELAY:   # [D8] (R7) a secondary axis waits
        return deferred_offers(p, h)                   # recorded as offers; asked when the delay has run
    candidates = []
    for i in h.bits & interest[g] & ~mine[g]:          # offered, wanted, and not held
        a = Ask(g, i)
        add_offer(a, p)                                # [c5] the offer table (v0.5 §6.1)
        if gated(a) or not authenticable(g): continue  # [c6] stop-pull; the gate first (v0.5 §3, §4.2 here)
        if tied_to_root(p, a): continue                # its copy waits for its gate (protocol.md §4.2)
        if parked(p, a): last_resort(a); continue      # [c5] park; every announcer parked: v0.5 §6.1
        if outstanding(p, a): continue                 # an ask of it to p is open (protocol.md §6.1)
        candidates.append(a)
    asks = []
    for a in shuffled(candidates):                     # v0.3 §6.1: one ask per index at a time
        if over_ihave_limits(p): held_back[(group(a), index(a))] = a   # retried at the next heartbeat (§4.8)
        elif may_ask(a, p):
            asks.append(a)
            ihave_asked[p] += 1                        # an ask in reply to p's offers
    return asks
```

**A holding** (`on_holding`), as `protocol.md` §4.3's HAVE. A holding of an expired group is
ignored, and a malformed one is ignored and counts against its sender: one beyond a holding's
length, or naming an index at or beyond the group's count once the count is known (`protocol.md`
§8.2). Otherwise the node adds its bits to what it knows the peer holds (`peer_has`), whose lifetime
each holding from the peer for the group refreshes (`HAVE_TTL`), and keeps the peer's two claims
once set (§1.5): it holds or can produce every index (`claim_all`, card 10), and its interest in the
group is satisfied, so nothing more need be pushed or offered to it (`complete`). A claim of the
whole group can defer one of the node's own decode duties (`note_claim`, §4.6). For each index the
peer newly holds, the node counts the peer as a holder (card 9), frees the window's room taken by
any copy it sent the peer at that index (card 14, §4.11), and, for a group it publishes, takes it as
the chunk's acknowledgement (`origin_acked`, §4.7), which acts once per chunk and does nothing at
`SOURCE_OFFERS = PUBLISH`.

**An offer** (`on_offer`), as `protocol.md` §4.4's IHAVE over one group's bitmap. An offer of an
expired group is ignored, and one beyond a holding's limits is ignored and counts against its
sender, as `protocol.md` holds an IHAVE's bitmap (§8.2). Within the type's start delay after the
group became known (`START_DELAY`, a secondary axis's `[D8]`), each index the peer offers, the node
wants and does not hold is recorded as an offer, and asked once the delay has run, under the checks
of `protocol.md` §6.1's retry (`deferred_offers`). Otherwise each such index is recorded as an offer
(card 5), whatever follows, and becomes a candidate unless stop-pull holds it back (card 6), the
group's gate has not opened (`authenticable`, §4.2), the peer's copy of it waits for its gate
(`protocol.md` §4.2), the peer is parked for the group (then the last resort, `protocol.md` §6.1,
which acts once every untied announcer of the index is parked: it asks the parked announcers once
more each, one at a time, each after a wait of `PROMISE` × 2ⁿ, n being the number of parked
announcers it has already queued such an ask to for the chunk), or an ask of it to the peer is open.
The candidates are taken in random order. While the peer is over an IHAVE limit, each is held back
(below); otherwise it is asked of the peer if `may_ask` allows (`protocol.md` §6.1: one ask per
index at a time).

- **An offer from any link is an offer.** The announce relation decides who learns what a node holds;
  `protocol.md` §6.1's pull decides whom the node asks, when it moves on and whom it parks. Offers never
  touch `peer_has`, `holders`, cancel or the window, and holdings never feed the offer table but in
  one case: a claim of a whole group that defers a decode duty is taken as an offer of the index its
  probe asks for, from that claimant (`defer_on_claim`, §4.6).
- **Gossipsub's two IHAVE limits apply to offers** (`protocol.md` §4.4). They delay asks and lose no
  offer.
  - `MAX_IHAVE_MESSAGES` counts the offer-bearing frames from a peer within a heartbeat (`on_frame`,
    §4), and `MAX_IHAVE_LENGTH` the asks made of the peer in reply to its offers. Both count per peer
    over every object type, as one connection carries them all.
  - Over either limit, the peer's offers are still recorded. What the node would ask of it is held back
    to the next heartbeat (§4.8), which runs `protocol.md`'s retry for it, with the retry's checks.
  - Only asks in reply to offers count against the limits: the retry, the last resort, the asks at a
    gate's release and those after the start delay `[D8]` do not.
- **The limits' values are the client's** (`protocol.md` §8.2). `protocol.md` §8.3 gives reference
  values for gossipsub's: 4096 offer-bearing frames and 5000 ids asked, per peer and heartbeat. What
  the values mean depends on the binding (§7, `protocol-v2-bindings.md` §2, §3):
  - on v0.3's wire, offers are IHAVEs, so a stock gossipsub client applies its own limits;
  - on the standalone binding, the values are the client's alone (§6.3 says which to avoid);
  - on the extension binding, offers travel as `partsMetadata`, not as IHAVEs.

**Open: offers on the extension binding.** Whether the extension limits offers is not checked here.

#### Rationale

**The reference values hold no ask back in the toy.** At 4096 frames and 5000 ids, the toy's 60-node
cells hold back no ask, under this draft's tier 4 setting, variant C (`c`) and custody, with and
without samplers. The busiest peer reached at most 248 frames and 58 asks in a heartbeat (custody),
and 42 and 11 (variant C). Under the rows setting (seeds 7 to 9, with and without half the columns
withheld) none was held back either, the busiest peer at 1 254 frames and 178 asks.

### 4.4 A node forwards

```python
def forward(f, from_peer, axes=None):                                      # axes: those on_validated acts on
    for (g, i) in (type_of_group(f.group).project(f) if axes is None else axes):   # (R4) each axis with its own type
        T = type_of_group(g)
        if expired(g) or state[g] == INVALID: continue                     # an expired or dropped axis is not acted on (v0.3 §8.1, §4.6)
        if duty_for(g) != FORWARD: continue                                # no duty on this axis: we only serve asks
        fam, c = T.family(g), colour_of(g, i)
        pushers = [q for q in links(T) if c in push_out[q][T][fam]]        # the relation for this colour
        holding = [q for q in pushers if peer_has[q][g].has(i)]            # [c4] the sender, normally
        cands = [q for q in pushers if q not in holding and q != from_peer
                 and interest_of_peer(q, g).has(i) and not peer_has[q][g].complete]   # [I3] into interest only
        budget = max(0, R_NODE - len(holding)) if T.params.EAGER else 0    # [c3, c4, c11, c17]; rows: offers only
        targets = choose_push(f, cands, budget, at_source=False)           # v0.3 §5.3 unchanged
        for q in targets:
            if enqueue(q, f, urgent=False): note_push(q, g, i)             # [c7, c16]
            else: owe(q, g, bitmap({i}))                                   # [c3] refused: offered instead (v0.5)
        for q in cands:
            if q not in targets: announce(q, g, bitmap({i}))               # [c3] offered instead
        for q in announce_extra(g, i):                                     # [D5] width beyond the relation
            announce(q, g, bitmap({i}))
    if state[f.group] != INVALID: gossip_history.put(f)                    # heartbeat gossip (§4.8); never a dropped group's (§4.6)

def announce(p, g, bits):                                                  # [c3, c7] an offer
    b = bits & ~pushed[p][g] & ~peer_has[p][g].bits & interest_of_peer(p, g)   # an empty bitmap is not sent
    if b and not send(p, Have(group=g, bits=b, offer=True, claim_all=False, complete=False), urgent=False):
        owe(p, g, b)                                                       # refused by a full queue: owed (v0.5)

def announce_extra(g, i) -> List[PeerId]:                                  # [D5]
    T = type_of_group(g); fam = T.family(g)
    if T.params.ANNOUNCE_EXTRA != ALL_JOINED: return []                    # SAMPLE: the heartbeat's paced gossip (§4.8)
    related = {q for q in links(T) if push_out[q][T][fam] or push_in[q][T][fam]}
    return [q for q in links(T) if q not in related and wants_from_me(q, g).has(i)]

def fills(g, i) -> List[Tuple[GroupId, int]]:         # (R4) every (group, index) the chunk at index i of g fills,
    return [(g, i)] + type_of_group(g).cross(g, i)     #   from the ids alone: the chunk need not be stored

def note_push(p, g, i):                                # protocol.md §5.2's, under every group the chunk fills (R4):
    for (g2, i2) in fills(g, i):                       #   a chunk noted through one group is not offered or
        e = pushed[p][g2]                              #   repaired to that peer again through another
        if e.empty(): e.first_push = now               # the guard's clock (§5.3 there), per group
        e.set(i2); e.ttl = PUSH_TTL
```

**A forwarding node's rules are v0.3 §5.2 and §5.3** with two changes: the candidates are the push
relation for the chunk's colour instead of the mesh, filtered by the peer's interest; and the
offer's width beyond the relation is a parameter: `ALL_JOINED` for columns and rows, `NONE`
permitted for columns (`[D5]`, §8). With `M = 1`, interest `ALL` everywhere and
`ANNOUNCE_EXTRA = SAMPLE`, the two functions are v0.3's `forward` and `announce`.

### 4.5 An ask arrives, and serving

```python
def on_want(p, asks):                                  # v0.3 §4.5's on_iwant, plus the serving limit (R6)
    answers = {}                                       # by id: one answer per id per frame
    for a in asks:
        gi = group_index(a)
        if gi and expired(gi.group): continue          # past its active lifetime: ignored, no penalty
        declared = gi and join_recv[p][type_of_group(gi.group)].interest == DECLARED
        if declared:                                   # its WANT is its interest (§1.2)
            want_p[p][gi.group] = want_p[p].get(gi.group, EMPTY) | bitmap({gi.index})
        flagged = probe_of_claim(p, gi)                # (R5) p's probe of our claim: answered whatever p holds
        if gi and peer_has[p][gi.group].has(gi.index) and not flagged:
            penalise(p)                                # it asks for a chunk it claimed: the claim wins
            continue
        if gi and served[p][gi.group] >= type_of_group(gi.group).params.SERVE_LIMIT:
            continue                                   # (R6) refused without penalty
        mid = resolve(a)                               # [c7] our chunk at that index: received or rebuilt
        if mid is None:                                # gi carries its WANT's fields (§2)
            if flagged and p not in probe_waiting[gi.group]:   # (R5) claimed, not stored: we are decoding; the
                probe_waiting[gi.group][p] = gi.index  #   first per asker and group is answered when it is (§4.6),
                standing[gi.group][gi.index].discard(p)   #   once: in place of p's standing WANT of that index,
            elif (gi and (declared or gi.standing)     #   whether it came before the probe or after it
                  and probe_waiting[gi.group].get(p) != gi.index):
                standing[gi.group][gi.index].add(p)    # §4.10: answered when the chunk arrives
            if gi and gi.hops > 0: route_want(p, gi.group, gi.index, gi.hops)   # §4.10: one step on
            continue
        if mid in unwanted[p] and not flagged: continue    # (R5) nor does a receipt of p's stop the probe's answer
        serve_count[p][mid] += 1
        if serve_count[p][mid] > GOSSIP_RETRANSMISSION: continue   # stock: 3 answers per id per peer
        if gi: served[p][gi.group] += 1
        if flagged: serve_probe(p, gi.group, chunk_of(mid))  # (R5) answered: the probe's one exemption, taken
        answers[mid] = chunk_of(mid)
    return list(answers.values())                      # [c14] one chunk per queue entry (v0.3 §4.1)

def serve_standing(g, i):                              # §4.10: the chunk a WANT waited for is here
    for q in standing[g].pop(i, ()):
        if peer_has[q][g].has(i) or served[q][g] >= type_of_group(g).params.SERVE_LIMIT: continue
        served[q][g] += 1
        if not enqueue(q, Entry(chunk=chunks[g][i], solicited=True), urgent=False):   # an answer, like any
            owed_answers[q][g].set(i)                  #   other: refused by a full queue, owed (v0.5 §7.2)
        note_push(q, g, i)                             # so that no offer follows it (§4.4)

def serve_waiting_probe(g, i):                         # (R5) the cell a kept probe waited for is stored, received or
    for q in [q for q, j in probe_waiting[g].items() if j == i]:   # rebuilt: answered as on_want answers a probe,
        del probe_waiting[g][q]                        #   with its one exemption
        if probe_served[q][g] or served[q][g] >= type_of_group(g).params.SERVE_LIMIT: continue
        served[q][g] += 1
        serve_probe(q, g, chunks[g][i])
        if not enqueue(q, Entry(chunk=chunks[g][i], solicited=True), urgent=False):   # an answer, like any
            owed_answers[q][g].set(i)                  #   other: refused by a full queue, owed (v0.5 §7.2)
        note_push(q, g, i)                             # so that no offer follows it (§4.4)

def route_want(p, g, i, hops):                         # §4.10: a routed sample request we cannot answer, one step on
    T = type_of_group(g)
    if join_sent[p][T].duty != FORWARD or forwarded[p] >= T.params.FORWARD_LIMIT:
        return                                         # (X6) refused without penalty: the sampler's wait moves it on
    qs, left = [q for q in links(T) if q != p and serves(q, g, i) and not parked(q, Ask(g, i))], 0
    if not qs and hops > 1:                            # no link serves it: one more step, toward the family
        qs, left = route_next(T, T.family(g), [q for q in links(T) if q != p
                                               and join_recv[q][T].duty == FORWARD]), hops - 1
    if not qs: return                                  # no route: silence, as above
    forwarded[p] += 1
    send(choice(qs), Want(group=g, bits=bitmap({i}), standing=True, hops=left), urgent=False)

def may_be_asked(p, g, i, routed=False) -> bool:       # (P7) scoring reads interest
    T = type_of_group(g)
    return (offered_us(p, g, i) or interest_of_peer(p, g).has(i) or peer_has[p][g].claim_all
            or routed and join_recv[p][T].duty == FORWARD)   # [D12] a routed request may go to any forwarding node
```

**A node serves what it holds**, received or rebuilt, to anyone who asks, within the serving limit per
peer and group `[R6]`, whatever the asker's duty. An ask may go to a peer that offered the index
or whose derived interest includes it (a custodian can be asked without offering, PeerDAS's
"knows exactly what a peer should be able to respond to"); an ask outside both is a violation,
unless it is a routed request and goes to a peer with duty `FORWARD` (below). A promise is made by an
offer, and a broken one parks the peer for the group (v0.3 §6.1). A
`DECLARED` peer's WANT is also its interest: `want_p[p][g]` is set from it before the asks are
answered, and what the peer does not hold yet is kept as a standing request (§4.10), which is why
derived interest makes no promise with a timer: the custodian answers when it can. A standing
request is answered when the chunk is stored, received or rebuilt (`serve_standing`, from `fill` and
`decode_group`). Standing requests live with the group's state (`GROUP_TTL`) and count against the
serving limit when answered.

**A routed sample request** (a WANT with `hops` above zero, §4.10) may also go to a peer with duty
`FORWARD` that neither offered the index nor custodies it `[D12]`. That peer answers it from what it
holds, keeps it standing for the rest, and, at most `FORWARD_LIMIT` times per asking peer and slot,
passes it one step on: to a link that serves the index, with `hops` 0, or, where none does and
steps are left, to the link nearest the index's family (`route_next`, §1.3's routing neighbours)
with one step fewer. Each WANT it sends is its own and standing, and what comes back is answered
on as any standing request, so the cell returns the way the request went, and each node on the way
sees only the one before it. A forwarder that has no such link, or is past its limit, says
nothing, and is not penalised: the sampler's wait moves it on. Its interest does not grow: what it
asked for on a sampler's behalf comes to it as an answer, not as a push into its interest (I3). The
fields are the asker's to set and cost the receiver only what it answers and passes on; a routed
request to a peer without duty `FORWARD` is read as a WANT without `hops`.

### 4.6 Completion, the claims, decoding and repair

```python
def check_completion(g):
    T = type_of_group(g)
    if state[g] != COLLECTING or interest[g].empty() or not interest_satisfied(g): return
    stop_pull[g] = True                                # [c6] no further asks for the group
    if T.params.DECODE_AT_K(g):                        # [c10] the decode claim at K, before decoding   [D4]
        state[g] = DECODING
        mine[g] = all_bits(T.index_count(hdr[g]))
    else:
        state[g] = COMPLETE                            # e.g. a row member at K: complete, no claim_all (R2)
        later = T.params.DECODE_LATER(g)               # a later duty, if the group is still short then   [D4]
        if later is not None: arm(g, known_at[g] + later)
    for q in suppression_scope(g): send_have(q, g)     # complete; and claim_all when decoding
    close_promises_of_group(g)                         # [c5] nobody owes us chunks of this group
    if state[g] == DECODING: start(decode_group, g)    # level 2, off the chunk path

def arm(g, at):                                        # a decode duty that fires unless the group fills first
    reconsider_at[g] = at
    after(max(0, at - now), reconsider, g, at)

def known_in_scope(g) -> Bitmap:                       # what we and our relation peers hold of g, by their holdings
    known = mine[g].copy()
    for q in suppression_scope(g):
        if q in claims[g]: continue                    # (R5) an unverified claim counts for nothing here
        known |= peer_has[q][g].bits
    return known

def known_across(g) -> Bitmap:                         # (R4) what our relation peers on the other axis hold of g
    T = type_of_group(g); known = mine[g].copy()
    for i in range(T.index_count(hdr[g])):
        if known.has(i): continue
        for (g2, i2) in T.cross(g, i):                 # a supernode's columns: every index of every row
            if any(peer_has[q][g2].has(i2) for q in suppression_scope(g2)):
                known.set(i); break
    return known

def repair_verdict(g):                                 # (R5, option) IncrementalDAS on the claimant's repair: cells
    T = type_of_group(g); steps = T.params.REPAIR_SAMPLE   #   of g we lack, asked of their columns' custodians;
    k = rsample_step[g]                                #   [(S1, L1), (S2, L2), ...], each sample containing the last
    if k > 0:                                          # step k's sample was asked SAMPLE_WAIT ago
        lost = [i for i in rsample[g] if not (received[g].has(i) or rebuilt[g].has(i))]
        if len(lost) <= steps[k - 1][1]: return REPAIRED   # at most L_k of S_k missing: the repair followed
        if k == len(steps) and rsample_final[g]: return NOT_REPAIRED   # the last re-asks were waited for
        reasked = [i for i in lost if T.params.REPAIR_REASK and ask_custodian(g, i)]   # a lost cell of another
        if k == len(steps):                            #   custodian: a silent one is not a missing repair
            if not reasked: return NOT_REPAIRED
            rsample_final[g] = True; return ASKED      # the last step: one more wait, for the re-asks only
    want = steps[k][0] - len(rsample[g])               # extend the sample, never a fresh one (IncrementalDAS)
    for i in shuffled([i for i in range(T.index_count(hdr[g]))
                       if not (received[g].has(i) or rebuilt[g].has(i)) and i not in rsample[g]]):
        if want == 0: break
        if ask_custodian(g, i): rsample[g].append(i); want -= 1
    rsample_step[g] = k + 1
    return ASKED if rsample[g] else REPAIRED            # nothing left to sample: nothing the repair could owe

def ask_custodian(g, i) -> bool:                       # (R5, option) cell i of g, of a custodian of its column not
    T = type_of_group(g); (g2, i2) = T.cross(g, i)[0]  #   yet asked for it and not a claimant (REPAIR_FLOOR keeps
    if expired(g2): return False                       #   the node a link to one per column); an expired column
    qs = [q for q in links(type_of_group(g2))          #   is not asked for (v0.3 §8.1)
          if interest_of_peer(q, g2).has(i2) and q not in claims[g] and q not in rsample_asked[g][i]]
    if not qs: return False
    q = choice(qs); rsample_asked[g][i].add(q)
    send(q, Want(group=g2, bits=bitmap({i2})), urgent=False)   # answered if the custodian holds it
    return True

def owed_missing(g) -> bool:                           # (R5) the member check: a chunk of g that is ours on the other
    T = type_of_group(g)                               #   axis is still missing (the row's cells in our custody
    return any(interest[g2].has(i2) and not (received[g].has(i) or rebuilt[g].has(i))   # columns, which a
               for i in range(T.index_count(hdr[g])) for (g2, i2) in T.cross(g, i))     #   claimant's repair brings)

def reconsider(g, at):
    T = type_of_group(g)
    if reconsider_at.get(g) != at or state[g] != COMPLETE: return   # re-armed since, or decoding already
    del reconsider_at[g]
    if deferred[g] and g not in probe_ok:              # (R5) the verdict, once: only the claimant's own copy
        if g in probe_sent:                            #   passes it, whichever peer brought the cell; a probe
            settle_probe(g, False); penalise(probed[g])   # not written by now gets none, and our own repair
        else: settle_probe(g, None)                    #   goes on below (§4.6)
    if popcount(known_in_scope(g)) >= T.index_count(hdr[g]): return # whole in the subnet's view: nothing to rebuild
    if (deferred[g] and received[g].has(probe[g]) and wants_family(T, T.family(g))   # (R5) the claim held, on a
            and not owed_missing(g)):                        #   row we take part in, and its repair reached us; on a
        if T.params.REPAIR_SAMPLE is None: return            #   row kept on no link, only cells held count
        verdict = repair_verdict(g)                          # (R5, option) the repair sampled across the columns
        if verdict == REPAIRED: return
        if verdict == ASKED: return arm(g, now + T.params.SAMPLE_WAIT)  # the sample asked or extended: re-armed
                                                                        # NOT_REPAIRED: rebuild
    if not waited[g] and not deferred[g] and popcount(known_in_scope(g) | known_across(g)) >= T.index_count(hdr[g]):
        waited[g] = True                                            # (R4) held on the other axis: on its way, so
        return arm(g, now + T.params.DEFER_WINDOW)                  #   wait once; a false holding costs one window
    if claims[g] and not deferred[g]: return defer_on_claim(g)      # (R5) a claim arrived: one deferral, the one wait
    state[g] = DECODING                                             # the late decode claim, as at K
    mine[g] = all_bits(T.index_count(hdr[g]))
    for q in suppression_scope(g): send_have(q, g)
    start(decode_group, g)

def claims_close(p):                                   # (R5) p's connection closed: its claims go, so a probe draws
    for g in [g for g, qs in claims.items() if p in qs]:   #   among connected claimants; our probe of p, not yet
        claims[g].discard(p)                           #   judged, gets no verdict, its promise gone with the
        if deferred[g] and probed.get(g) == p and g not in probe_ok:   # connection, and the deferral ends:
            settle_probe(g, None)                      #   no verdict, and our own repair is reconsidered at the
            arm(g, max(now, duty_at.get(g, now)))      #   duty's own time, at once if that has passed

def note_claim(p, g):                                  # (R5) from on_holding: p claims every index of g
    claims[g].add(p)
    if (g in reconsider_at and state[g] == COMPLETE and not deferred[g]
            and popcount(mine[g]) < type_of_group(g).index_count(hdr[g])): defer_on_claim(g)

def defer_on_claim(g):                                 # (R5) verify the claim by one ask, and wait for it
    T = type_of_group(g)
    deferred[g] = True
    duty_at[g] = reconsider_at.get(g, now)             # the duty's own time: a probe with no verdict returns to it
    lack = [i for i in range(T.index_count(hdr[g])) if not mine[g].has(i)]
    i = choice(lack)                                   # an index we lack, at random: the claimant cannot tell which
    probe[g] = i
    q = probed[g] = choice(list(claims[g]))
    a = Ask(g, i)
    add_offer(a, q); tried[a][q] = now                 # a claim is an offer of every index (v0.3 §6.1's tables)
    probe_asks.add(a)                                  # past stop-pull and the ask window: gated exempts it
    if not send(q, Want(group=g, bits=bitmap({i}), probe=True), urgent=False):   # marked: answered whatever we hold
        settle_probe(g, None)                          # refused by a full queue, never written: no verdict, and our
        return arm(g, max(now, duty_at[g]))            #   own repair is reconsidered at the duty's own time (§4.6)
    arm(g, max(reconsider_at.get(g, now), now + T.params.DEFER_WINDOW))   # its promise starts at its write
                                                       #   (filter_entry); not written by then: no verdict either

def gated(a): return stop_pull[group(a)] and a not in probe_asks    # [c6] v0.3 §6.2, with the probe exempt

def settle_probe(g, verdict):                          # (R5) the verdict, once (True passed, False failed, None no
    probe_ok[g] = verdict                              #   verdict); settled, the probe's ask is gated again, so the
    probe_asks.discard(Ask(g, probe[g]))               #   probed cell is pulled past stop-pull no more (§4.6)

def probe_answer(g, i, p):                             # (R5) the claimant's own copy of the probed index, first or a
    if deferred[g] and probe.get(g) == i and p is not None and p == probed.get(g) and g not in probe_ok:
        settle_probe(g, True)                          #   duplicate, passes the probe and keeps its promise
        promises.pop((Ask(g, i), p), None)

def probe_promise(g, i):                               # (R5) the probe's promise, still open: another peer's copy
    if not deferred[g] or probe.get(g) != i or g in probe_ok: return None   #   does not close it; once the
    k = (Ask(g, i), probed[g])                         #   probe is judged or given no verdict, a promise under
    return (k, promises[k]) if k in promises else None #   its key is a plain ask's, which any copy closes

def probe_waits(a, p) -> bool:                         # (R5) a is our probe of p, flagged and not yet answered or
    gi = group_index(a)                                #   judged: our queue writes it even if another peer's copy
    return (gi is not None and gi.probe and deferred[gi.group] and probed.get(gi.group) == p   # came first
            and probe.get(gi.group) == gi.index and gi.group not in probe_ok)

def probe_settled(a) -> bool:                          # (R5) a is our probe, judged or given no verdict: if still
    gi = group_index(a)                                #   queued, it is not written (§4.6)
    return gi is not None and gi.probe and gi.group in probe_ok

def probe_of_claim(p, gi) -> bool:                     # (R5) as the claimant: p's flagged ask of an index we claim,
    return (gi is not None and gi.probe and mine[gi.group].has(gi.index)   #   while no flagged ask of the group
            and not probe_served[p][gi.group]          #   from p was answered; a later one is a plain ask (the cap),
            and probe_waiting[gi.group].get(p, gi.index) == gi.index)   # as is one of another index while p's is kept

def serve_probe(p, g, f):                              # (R5) f answers p's probe of g: the cap is taken, and card 8
    probe_served[p][g] = True                          #   lets that answer through once, whatever p holds
    probe_answers[p][f.group].set(f.index)

def filter_entry(p, entry):                            # protocol.md §7.2's, but for the lines marked (R5) and want's
    f = entry.chunk
    if f:
        exempt = entry.solicited and probe_answers[p][f.group].has(f.index)   # (R5) our answer to p's probe
        if CANCEL and not exempt and peer_has[p][f.group].has(f.index):    # [c8] it became a duplicate
            entry.chunk = None
        elif PROJECT and not entry.solicited and projected(p, f.group):    # [c12]
            entry.chunk = None
            unpush(p, f.group, f.index)                        # [c3] not made: offered instead (§5.2)
        else:
            sent_to[p][f.group].set(f.index)
            if exempt: probe_answers[p][f.group].clear(f.index)   # (R5) spent by the answer written, once
    for c in entry.iwants():                                   # the asker drops asks for chunks it
        c.ids = [a for a in c.ids                              #   now holds, no longer pulls, or of a
                 if (not held(a) or probe_waits(a, p))         # (R5) but our waiting probe of p
                 and not probe_settled(a)                      # (R5) and a probe settled while queued,
                 and not gated(a) and not expired(group(a))    #   group past its lifetime,
                 and not tied_to_root(p, a)]                   #   and asks to a peer whose copy waits
        for a in c.ids:                                        # [c5] the promise starts at the write
            if probe_waits(a, p) and group(a) not in probe_sent:   # (R5) our probe, written now: its promise
                W = type_of_group(group(a)).params.DEFER_WINDOW    #   and the verdict's wait start here (§4.6)
                probe_sent.add(group(a))
                promises[(a, p)] = now; after(W, promise_due, a, p, now)   # broken: the claimant is parked
                arm(group(a), max(reconsider_at.get(group(a), now), now + W))
            elif (a, p) not in promises and (not c.want or probe_waits(a, p)):   # an ask not made on an offer
                promises[(a, p)] = now                         #   (want, §3) starts none, but a probe (§4.5, §4.10)
                after(PROMISE, promise_due, a, p, now)         # 400 ms
    return entry if not entry.is_empty() else None             # control rides on and survives

def decode_group(g):                                   # level 2, off the chunk path
    T = type_of_group(g)
    whole = T.decode(chunks[g], hdr[g])                # every chunk of the group, or None
    if expired(g): return                              # the group passed its lifetime meanwhile (v0.5 §8.1)
    if whole is None: return drop_group(g)             # [D6] and publish_evidence(g, …) if T.params.EVIDENCE
    new = [i for i in whole if not received[g].has(i)] # rebuilt, and not received meanwhile
    filled = []                                        # the other groups the rebuilt chunks fill, in order
    for i in new:
        store(g, i, whole[i]); rebuilt[g].set(i)       # servable from now on
        serve_standing(g, i)                           # §4.10: WANTs that preceded it are answered now, as in fill
        serve_waiting_probe(g, i)                      # (R5) a probe that reached us while we decoded (§4.6)
        for (g2, i2) in T.project(whole[i]):           # (R4) a rebuilt chunk fills its other groups too
            if g2 == g: continue
            fill(g2, i2, whole[i], None)
            if g2 not in filled: filled.append(g2)
    state[g] = COMPLETE
    push_rebuilt(g, new)                               # [c10] repair: level 2 has passed
    for g2 in filled: check_completion(g2)             # (R4) as on_chunk does: a filled group may be complete
    deliver(g, payload_of(whole))                      # level 3: the application's checks

def push_rebuilt(g, new):                              # [c10] v0.3 §4.6 over each group a rebuilt chunk fills
    T = type_of_group(g)
    by_group = {}
    for i in new:
        for (g2, i2) in T.project(chunks[g][i]): by_group.setdefault(g2, []).append((i2, chunks[g][i]))
    for g2, items in by_group.items():
        if expired(g2) or state[g2] == INVALID: continue   # an expired or dropped axis is not acted on (v0.3 §8.1, §4.6)
        T2 = type_of_group(g2); k = T2.threshold(hdr[g2])
        if T2.params.REPAIR_BUDGET and T2.params.EAGER:
            push_rebuilt_as_source(g2, items); continue
        for q in shuffled(T2.params.REPAIR_TO(g2)):    # peers whose interest includes them (I3)   [D4]
            e = peer_has[q][g2]
            known = e.bits | pushed[q][g2]             # what q claimed, and what we chose to push it
            short = k - popcount(known)                # q's shortfall: none after its decode claim
            if short <= 0 or e.complete: continue
            want = interest_of_peer(q, g2)                               # [I3] into interest only
            lacks = shuffled([x for x in items if not known.has(x[0]) and want.has(x[0])])   # at random, so
            for i2, f in lacks[:short]:                                  #   that decoded neighbours differ
                if not T2.params.EAGER: announce(q, g2, bitmap({i2})); continue   # rows: offered, pulled when wanted
                if enqueue(q, f, urgent=False): note_push(q, g2, i2)
                else: owe(q, g2, bitmap({i2}))                           # refused: offered instead (v0.5)

def push_rebuilt_as_source(g2, items):                 # [D4] REPAIR_BUDGET: a rebuilt chunk as its source pushes one (§1.6)
    T2 = type_of_group(g2)
    for i2, f in items:
        cands = [q for q in shuffled(T2.params.REPAIR_TO(g2))
                 if not (peer_has[q][g2].bits | pushed[q][g2]).has(i2) and not peer_has[q][g2].complete
                 and interest_of_peer(q, g2).has(i2)]                    # [I3] lacking it, into interest only
        for q in cands[:R_NODE]:                                         # the per-chunk budget [c17]
            if enqueue(q, f, urgent=False): note_push(q, g2, i2)
            else: owe(q, g2, bitmap({i2}))                               # refused: offered instead (v0.5)
        for q in cands[R_NODE:]: announce(q, g2, bitmap({i2}))           # [c3] offered to the rest
```

- **Two claims.** `complete` says "stop sending me this group"; `claim_all` says "I can serve any
  index of it". A row member that stops at 64 cells and exposes them sends the first and not the
  second (R2); a payload node at K sends both.
- **Who decodes, and when** `[D4]`. `DECODE_AT_K` is the duty that decodes the moment K chunks are
  in, with the claim before the decode: every node on the payload; on a row, EIP-8371's first
  phase, a row reconstructor on the row of its own subnet. `DECODE_LATER` is the duty that waits:
  a member of the row's subnet decodes at the third phase's delay from the block root if the row is
  still short of 128 then, with a jitter so that the first to decode cancels the others; the second
  phase, a supernode over every row, is the same rule with a shorter delay. "Still short" is read
  in the subnet's view: what the member holds together with what its relation peers' holdings
  show (`known_in_scope`), so that a row whose cells all exist among the members is not rebuilt
  by a member that stopped at 64, while a withheld column's cells, which no member holds, are. A
  duty armed this way fires unless the group became whole in that view meanwhile ("a node MUST
  cancel a pending reconstruction of a row that completes through other means", EIP-8371).
- **Deferral on a claim, verified by one ask** (R5). A peer's `claim_all` for a group whose later
  duty is armed defers the duty once, by at least `DEFER_WINDOW` (a probe that ends without a
  verdict returns the duty to its own time, below), and the receiver asks one claimant, drawn at
  random among the peers whose claim of the group it holds, for one index it lacks, drawn at random
  (a claim is a promise: §4.5 `may_be_asked`). The duty and the claimant are
  judged apart. If the chunk arrives, from anyone, the claim is verified for the duty, and a row
  member's duty ends when the window has run; a node that keeps the row on no link goes by the cells
  it holds (below). The claimant passes only on its own copy, an answer or a push: if none has come
  when the deferred duty fires, with its probe written and the claimant still connected (below), the
  claimant is penalised, once, and another peer's copy leaves its promise open, so that v0.3's pull
  discipline parks it when the promise breaks. That holds only while the probe waits: once it is
  judged or given no verdict, a promise under its key is a plain ask's, which any copy closes
  (`probe_promise`), and the probe's ask is no longer exempt from stop-pull (`settle_probe`), so the
  member pulls the probed cell from nobody after the verdict, as it pulls no other cell of the row
  once complete. The probe's promise is the deferral window itself, not v0.3's `PROMISE` of 400 ms.
  A claim counts for nothing in the subnet's view of the row (`known_in_scope`), verified or not; a
  verified claim ends a member's duty through the deferral instead. The probe is an ask past
  completion, so until it is settled it is exempt from stop-pull (card 6) and from the
  one-ask-per-index window; and it counts against the claimant's serving limit like any answer: the
  draw of the claimant does not look at the limit, so a member that has already pulled `SERVE_LIMIT`
  chunks from the claimant it draws has its probe refused, and that claimant is judged as one that
  does not answer: penalised, the probe having been written, unless its own push of the cell comes
  in time. A client
  may prefer a claimant it has pulled less from, or keep one ask in reserve.
- **The probe is marked, and its cell drawn at random** (R5). Three rules keep
  the verdict on the claimant fair to an honest one and hard to meet for a dishonest one. Three
  more say when the probe's wait starts, and what a claimant still decoding and
  a claimant's departure do.
  - *The mark.* The probe's WANT sets `probe` (§2). The claimant answers the first such ask per
    asker and group, of an index it claims, whatever the asker's holdings say: neither the claim
    rule (§4.5) nor a receipt of the asker's refuses it, and card 8 lets the answer through once
    (`filter_entry`, `protocol.md` §7.2's with the probe's lines). The exemption is the answer's
    alone: it is taken when the claimant answers, only for an index it claims, and spent when that
    answer is written, so a push of the same cell neither uses it nor passes card 8. A second marked
    ask of the group, after one was answered, is a plain ask. The mark costs no byte: on v0.3's wire
    and in Partial Messages it is one more bit beside `standing`, and the standalone binding carries
    `standing` and `probe` in one flags byte (`protocol-v2-bindings.md` §1.3).
  - *The asker's queue keeps the probe.* While the probe waits, the asker's queue writes its marked
    WANT even when another peer's copy came first and the asker holds the cell (`probe_waits`). The
    writer's other checks on an ask still apply: not past the group's lifetime, and not to a
    claimant whose copy of the index waits for its gate (`filter_entry`).
  - *The cell at random.* The probed index is drawn uniformly among those the member lacks.
  - *The probe's wait starts at its write*, as every promise does (`protocol.md` §6.1). The probe's
    promise starts when its WANT is first written (`filter_entry`) and lasts `DEFER_WINDOW`; a write
    of it again while it waits, that promise gone, starts v0.5's plain one, as any ask on an offer;
    the wait for the verdict lasts until the later of that and the duty's own time, the time it was
    armed for when the claim deferred it (`duty_at`). A probe that is not written gets no penalty,
    and no verdict unless the claimant's own copy of the probed cell comes first, which passes it as
    it passes any probe; without a verdict, the member's own repair is reconsidered (`reconsider`):
    - one a full queue refuses, at the duty's own time, at once if that has passed (`send`'s
      result);
    - one still unwritten when the duty next fires, `DEFER_WINDOW` after the decision or at the
      duty's own time if that is later. Settled while still queued, it is not written later
      (`probe_settled`): no verdict waits on it any more.

    The second bounds the deferral: the verdict, or the reconsideration without one, comes at most
    one window past the later of the duty's own time and one window after the decision
    (`max(duty_at, decision + DEFER_WINDOW) + DEFER_WINDOW`): otherwise a claimant that stopped
    reading its connection would keep the probe queued and hold the member's repair off without
    end, which the probe exists to prevent.
  - *A claimant still decoding answers when the cell is stored.* A claimant that decodes claims
    every index at once, before it has stored the cells it rebuilds, so a probe can find nothing to
    answer (`resolve`). The claimant keeps the first marked ask per asker and group of a claimed
    index it has not stored (`probe_waiting`), and answers it, with its exemption, when the cell is
    stored, received or rebuilt (`serve_waiting_probe`, from `fill` and `decode_group`). It answers
    it once: while it is kept, neither the same marked ask repeated nor a standing WANT of the same
    index from the same asker, sent before it or after it, is kept as a standing WANT as well, which
    would send the cell twice and charge the serving limit twice, or spend the last slot without the
    exemption, so that the claimant's own queue could cancel the answer as a duplicate once the
    asker's holding names the cell. Nor, while it is kept, does the same asker's marked ask of
    another index of the group take the exemption: it is a plain ask (`probe_of_claim`), so the kept
    probe keeps it for when its cell is stored. It is answered then if the asker has not reached
    `SERVE_LIMIT` in the group by then (`serve_waiting_probe`). A decode that fails stores nothing,
    so its claimant is judged as one that does not answer.
  - *A claimant that leaves is not judged.* A peer's claims go with its connection (`claims_close`),
    so the probed claimant is drawn among connected ones. A probe of a claimant whose connection
    closes before the verdict gets none, neither a pass nor a penalty: its answer can no longer
    come, and its promise went with the connection (`protocol.md` §8.1). The deferral then ends, and
    the member's own repair is reconsidered at the duty's own time, at once if that has passed
    (`reconsider`, which rebuilds unless the group is whole in the subnet's view or the repair
    reached it): the claim, unverified, returns the duty to its own time, or to the close if that
    time has passed, so the members a departed claimant claimed to do not all rebuild at the same
    instant. As after any deferral, the member does not then take the one wait for the other axis
    (R4), so its rebuild can come up to one window sooner than with no claim. No second claimant is
    probed: one deferral per group, as before.
- **The verdict, by what the node can see** (R5: re-arm "if the cells do not follow"; with sampling
  the repair, below, an option). A row member, a node that takes part in the row's family
  (`wants_family`: its own subnet's row), has a subnet's view of the row (`known_in_scope`), and a
  verified claim ends its duty when the window has run, whoever made it, subject to the member check
  (below). A node that keeps the row on no link, a supernode on the rows of the other subnets
  (interest declared on no link, §1.2) and on every row under custody alone, goes by the cells it
  holds: a claimant that answers the probe and sends nothing else costs it one window, not the row.
  A deferral is the duty's one wait (no `known_across` wait follows it), and only a probe the
  claimant's own copy did not answer counts against it.
- **The member check** (R5; `owed_missing`). A verified claim ends a member's duty only once the
  row's cells in the member's own custody columns have arrived: those are the cells the claimant's
  repair owes it (§4.6 below: rebuilt cells go to the custodians lacking them), so an honest
  claimant delivers them within the window and a claimant that repairs nothing does not. Otherwise
  the member goes by the cells it holds and rebuilds the row, telling its subnet peers as for any
  decode. The check needs nothing new on the wire: the member reads its own holdings at the moment
  it would have stopped.
- **Sampling the repair** (R5, option: `REPAIR_SAMPLE`, `SAMPLE_WAIT`). The member check asks
  whether the member's own share of the repair came; RowDAS's rule asks whether the cells followed,
  into every column. A member cannot see the other columns, but it can sample them, as a node
  samples a block, and IncrementalDAS gives the test its shape ("LossyDAS: lossy, incremental, and
  diagonal sampling for data availability", ethresear.ch 2024, https://ethresear.ch/t/18963): after
  a verified claim and a passed member check, the member asks cells of the row that it lacks, up to
  `S1`, each of a linked peer whose interest holds the cell, on a live column, and that is not a
  claimant (`ask_custodian`; `REPAIR_FLOOR` keeps the member a link to a custodian of each column it
  does not custody, which may be the claimant), and re-arms its duty for `SAMPLE_WAIT`. With at most
  `L1` of them missing, the repair followed and the duty ends; otherwise it extends the sample
  toward `S2` cells containing the first and re-arms once more, and with more than `L2` missing it
  rebuilds. A step that finds fewer cells to ask than its target is judged by the same `L_k` on the
  cells asked, and a sample that has found no cell to ask at all counts as followed: the duty ends
  (`repair_verdict`). It extends the sample, never drawing a fresh one, as IncrementalDAS does. The
  cells a member lacks past K are the withheld columns', the ones only a repair brings, and the
  claimant cannot know which the sample picks.
  - *Re-asking a lost cell* (`REPAIR_REASK`) separates an unresponsive custodian from a missing
    repair: when a step fails, each missing cell is re-asked, with the extension, of another
    eligible peer, if the column is live and a linked peer whose interest holds the cell, not a
    claimant and not yet asked for it, is left (`ask_custodian`; a WANT a full queue refuses counts
    as asked). At the last step the re-asks get one more wait, after which the member rebuilds if
    more than `L_k` are still missing; with no re-ask made, it rebuilds at once.
- **Rebuilt cells marked seen** (option: `REBUILT_SEEN`, only with `REPAIR_SAMPLE`). `decode_group`
  stores what it rebuilds without `mark_seen`, where `publish` marks a source's chunks seen. So a
  copy of a rebuilt cell that another rebuilder pushes is validated again and forwarded on every
  axis where the node has duty `FORWARD`. Marked seen, it is a duplicate: acknowledged, and
  forwarded no further.
- **A custodian's alarm** (option: `ALARM_WAIT`, with `ALARM_NEXT` and `ALARM_MAX`; for networks
  without an honest supernode). The sample allows a lost cell at its last step, since a custodian
  may not yet hold a repaired cell when asked. So a claimant that repairs every withheld column of
  its row but one passes every member's sample with certainty, and the custodians of that column
  stay short. Only they see which cell is missing.
  - *The alarm.* At `ALARM_WAIT` after `known_at`, with a jitter, an honest custodian that still
    lacks a cell of a custody column, one that no peer's holding shows, sends a standing WANT for
    that cell's row, at the column's index, to a member of the row's subnet among its links. While
    the cell is missing it asks another member every `ALARM_NEXT`, up to `ALARM_MAX`.
  - *The member.* A member that deferred on a verified claim asks that claimant for the index once,
    with the probe's promise (`DEFER_WINDOW`), started at the ask's write, as the probe's is. A
    broken promise counts against the claimant, and the member rebuilds the row and repairs it as
    after any decode. A claimant that cannot be asked, because its connection has closed or a full
    queue refuses the ask, or whose connection closes before the ask is written or before the
    promise ends, is not judged, and the member rebuilds the row if the cell is still missing.
    Nothing new goes on the wire: the alarm is a standing WANT, and a member that rebuilds the row
    answers it from `decode_group` as any standing WANT, unless the custodian's holding names the
    cell by then or it has reached `SERVE_LIMIT` in the group (`serve_standing`, §4.5).
  - *Its wait* is stated by its bound: above the honest custodians' tail on the network, or it fires
    without a fault. A rescue comes a round trip, `DEFER_WINDOW` and a decode after the wait, later
    than the sample's, so the alarm backs the sample up rather than replacing it.
- **Repair across groups** (R4). A rebuilt chunk fills every group it belongs to (`fill` on the
  other axis) and `push_rebuilt` works group by group: for a row, the rebuilt cells of row b go into
  the column groups of their columns, to the custodians `REPAIR_TO` names that lack them, which is
  "the push into non-custodied columns is the whole of the relief" (the RowDAS design); the row's
  own members, complete at 64, are not pushed what they do not want. For the payload, `project` is
  the identity and this is v0.3's `push_rebuilt`. PeerDAS's reconstruction is the second phase
  without row subnets (below). A push, and an answer to a standing WANT or a kept probe, is noted
  under every group the chunk fills (`note_push`, §4.4; `unpush` clears it for a source's push its
  queue refuses and for a push the writer skips by projection), so a chunk noted through one of its
  groups is not offered or repaired to that peer again through another, nor pushed to it by a
  source (`wants_from_me`). The note does not keep a forwarding node from pushing the chunk to that
  peer (`choose_push` only ranks by it), and an answer from `on_want`, a probe's included, is not
  noted.
- **A rebuilt chunk names the block its sources name** (`protocol.md` §4.6, v0.8). Otherwise,
  under two blocks of a slot, a rebuilt copy naming the other block would wait for good at a
  neighbour that installed only the first.
  - The payload: by `decode_and_reencode`, as `protocol.md` defines it.
  - A cell: by construction. Its group id carries the root (§1.1), and `project` keeps it, so a
    rebuilt cell of row b fills the column groups of the same block.
  - The rule keeps honest copies on the source's block only as long as no node relabels a chunk
    (`protocol.md` §4.6, "Open: relabelled copies", with its options; 2026-10-28). The payload is
    exposed as there. A cell relabelled under the other block is a cell of that block's groups,
    which its id carries. It cannot stand in for the source's copy or tie its sender for this
    block's groups: for cells this is that list's option of a group per block root. The cells'
    case is by inspection: neither the toy nor a model runs relabelled copies.
- **A rebuilt chunk completes the groups it fills** (R4). `decode_group` checks the completion of
  every other group its rebuilt chunks filled, as `on_chunk` does after an arrival. A member whose
  custody column lacked only cells of the row it rebuilt holds the whole column after its own
  decode.
- **Every member keeps a link to each column** (`REPAIR_FLOOR`, decided). A row is gathered from the
  columns and repaired into them, so a member needs, for every column, a link to a node that
  custodies it: to pull that column's cell of its row, and to push the cell it rebuilt. `REPAIR_TO`
  names custodians among the node's links, and EIP-8371 reaches the other columns through
  gossipsub's fanout ("after reconstruction, a node SHOULD use the Gossipsub fanout mechanism to
  provide cells from the reconstructed blob to peers across column subnets it is not subscribed
  to"), which uses connected peers only. So the rendezvous keeps, for every node that may rebuild,
  at least `REPAIR_FLOOR` links to custodians of each column it does not custody, as `SOURCE_FLOOR`
  keeps a proposer's links to the columns it publishes (§4.7). Opening a link through the rendezvous
  only when a rebuilt cell has nowhere to go is an option: it costs a lookup and a handshake while
  the cell waits, and it does not help a member gather a row.
- **A supernode keeps every row** (the second phase, R3). A node that custodies every column
  receives every cell of every row with its columns, so it keeps every row group, filled from its
  columns (R4), with interest `ALL` declared on no link (§1.2). Its duty on a row outside its own
  subnet is `DECODE_LATER` at the second phase's delay, shorter than the third's: if the row is
  still short then, it rebuilds the row, and the rebuilt cells go into the columns as any
  rebuilder's do. EIP-8371 puts this phase on supernodes because "only a node subscribed to all
  column subnets can observe rows completing elsewhere and cancel the redundant work": a row rebuilt
  elsewhere reaches a supernode as column cells. A node with 64 to 127 columns never holds the cells
  of the columns it lacks, so it cannot tell a row rebuilt elsewhere from one still short, and it
  keeps no second-phase duty here (the EIP's MAY, left out). Under custody alone, without row
  subnets, the same rule is PeerDAS's reconstruction ("If the node obtains 50%+ of all the columns,
  it SHOULD reconstruct the full data matrix … Nodes MAY delay this reconstruction"), with the delay
  made the rule's: a supernode keeps the rows, no other node does, and it rebuilds only the rows its
  columns have not completed by then.
- **A row held on the columns is on its way** (R4). The subnet's view (`known_in_scope`) holds only
  the row's own axis, and at the second phase's timer a supernode may still be receiving its 128
  columns. A chunk held on one axis is held on the other, so the duty also reads what its relation
  peers on the other axis hold (`known_across`; `T.cross` names a chunk's other (group, index) pairs
  from the ids alone): for a supernode, its peers' bitmaps on every column, which is EIP-8371's
  "observing the bitmaps of all column subnets". A row whole in that view but not in the node's
  holdings is on its way: the duty waits once, `DEFER_WINDOW`, and fires then if the row is still
  short in the node's holdings, so a false holding delays a rebuild by one window and no more. A
  member reads the same view over its custody columns.
- **A rebuilder pushes as a source** (`REPAIR_BUDGET`, an option, off). A rebuilder holds the
  rebuilt chunks before its peers do, so it is their source (§1.6), and the option has it push each
  one to `R_NODE` of the peers lacking it and offer it to the rest, as a source does, instead of
  pushing it to every peer short of it. It stays an option.
- **Whom rebuilt cells go to** (`REPAIR_TO`, options). The push stays. Three forms are options:
  offering the cells to the nodes that keep every row instead of pushing them; offering every
  rebuilt cell, as a row's are; and leaving the keepers out.

#### Rationale

**Deferral on a claim, verified by one ask.**
- *The probe's promise* is the window, not `PROMISE`: a reconstructor that has just decoded is
  pushing a row's worth of rebuilt cells through its window, and in the toy its answer to a probe
  left 450 ms after it was decided, so with the shorter promise honest claimants were parked and
  penalised.
- *A claim outside the subnet's view.* Executing the toy's liar fault showed that a false claim
  counted there made the row look whole to every member of its subnet and suppressed the third
  phase, the suppression the RowDAS design warned of.
- *The probe exempt.* Without the exemptions, the one-ask-per-index window dropped the probe in the
  toy and penalised honest reconstructors.
- *Defer and re-arm.* The RowDAS design asked for "defer and re-arm" because a bitmap takes a round
  trip and cancelling on a claim outright lets any peer suppress reconstruction; the probe makes the
  re-arm a verdict on the claimant rather than a timer, at the cost of one cell.

**The probe is marked, and its cell drawn at random** (decided 2026-11-15; the probe's wait from its
write, a claimant still decoding and a claimant that leaves since 2026-11-16; `probe_of_claim` since
2026-11-17).
- *Why the mark.* The probed cell often reaches the asker from another peer during the wait, on its
  other axis, and the asker's holding then names it; without the mark, the claimant's queue
  cancelled its own answer as a duplicate, and an honest claimant failed its probe.
- *Why the asker's queue keeps it.* Otherwise the asker dropped its own probe, and the claimant
  could pass only on a push.
- *Why at random.* The lowest one, which an earlier draft took, can be read from the member's
  announced holdings, so a claimant could keep exactly that cell and withhold the rest; drawn at
  random, the claimant cannot tell which cell will be asked.
- *Why from its write.* Started at the decision instead, the wait penalised a claimant for a WANT it
  never received.
- *Why the claimant keeps the probe.* Dropped, the probe would go unanswered, and an honest claimant
  whose decode outlasts the probe's round trip would be penalised. An honest member sends one probe
  per group; before, a faulty asker's second marked ask, of a stored cell, took the exemption, and
  the kept one went unanswered.
- *Measured* in the toy's rows (60 nodes, three blocks, seeds 7 to 9, `--send-buffer 0`), in five
  cells: honest; a fifth of the nodes lying (`--fault claim20`); the same with 16 subnets and half
  the columns withheld; a fifth hoarding (`--fault hoard20`) with 16 subnets and half withheld;
  and the liars' withheld cell with 5 % supernodes (three of 60), on this section's rules as they
  stand (2026-11-18). None of 1 281 verdicts on honest or hoarding claimants failed, and every
  probe got a verdict and was written: none was still unwritten when its window ran out, and no
  probe reached a claimant still decoding (the toy's queues refuse nothing, and these cells close
  no connection). Liars passed their probe 1, 0 and 65 times in the three liar cells, over the
  three seeds, each time on a copy the liar pushed (a toy liar answers no ask). The mark cost 5
  duplicate cells in 2 417 probes: exempt answers written over a holding the asker had sent. A
  probe was written when it was decided, at the median; the longest wait was 163 ms, against a
  `DEFER_WINDOW` of 1 s. One run, the 16-subnet liars' cell at seed 9, delivers no block to 58 of
  its 60 nodes, as it did before, and decides no probe; the figures include it. Against the runs
  with the rules of 2026-11-16 (below), every run changed its events; copies stayed within 0.03 in
  11 of 15 runs and moved in four, not traced: the hoarders' cell by −0.04 at seed 9 and +0.03 at
  seed 7, the supernodes' cell by +0.04 at seed 7 and +0.09 at seed 9.
- *Measured with the rules of 2026-11-16*, before four later fixes (a probe settled while queued,
  a kept probe answered once, the duty's own time, a settled probe's promise) and the later
  changes to the draft, in the same cells: none of 1 298 verdicts on honest or hoarding
  claimants failed; liars passed 3, 1 and 61 times; the mark cost 9 duplicate cells in 2 428
  probes; one probe, in the supernodes' cell at seed 8, passed before it was written, on a copy
  the liar pushed; the 16-subnet liars' cell at seed 9 decided 3 probes; the longest wait from
  decision to write was 101 ms.
- *Measured before 2026-11-16*, and before v0.10's order of the announcers beyond the list
  (`protocol.md` §6.1), which moves the supernodes' cell at seed 8 and, bracketed but not run at
  that change, at seed 9, in the same five cells: judged by the claimant's own copy without the mark
  and the kept WANT, 3 of 1 289 verdicts on honest or hoarding claimants failed, all three honest
  ones in the hoarders' cell; with them, none of 1 299 did. When any peer's copy passed the
  claimant, liars passed at least 57, 115 and 558 times. Against the earlier rule's runs (the lowest
  index, any peer's copy passing), copies stayed within 0.03 in 12 of 15 runs; they were 0.03 to
  0.04 lighter in the hoarders' cell at seed 8, and 0.08 lighter at two seeds of the supernodes'
  cell, almost all of it data, not traced further.
- *The random index's cost, and what is not measured.* Against the lowest index, measured before
  2026-11-16, the random one let liars pass a little more often (3, 1 and 61 against 0, 0 and
  49). In six traced runs, which hold all 65 such passes, the liar had by then already sent the
  member the lowest lacked cell in 45 and held it unsent in 20; in none had it neither. The
  excess fits the draw choosing a cell already on its way, but that is not proven. The toy's
  liars do not aim at the cell they expect to be asked, so these runs measure the draw's side
  effects, not its purpose; nor does any fault send marked asks, which the cap bounds to one
  exempt answer per asker and group.
- Figures in this section measured before 2026-11-15 ran with the lowest index, without the mark
  and the kept WANT, and with any peer's copy passing the claimant, unless they say otherwise.

**The verdict, by what the node can see** (decided 2026-10-10). Draft 1 ended a row member's duty on
a verified claim; the rule above keeps that, subject to the member check.
- *The wording.* An earlier wording told the two apart by a non-empty suppression scope (some peer
  pushes the row to the node); a member that no peer pushed its row to then counted as keeping the
  row on no link and rebuilt after a verified claim, which with 32 subnets (about two members each
  at 60 nodes) added about 4 member decodes per run (20 against draft 1's 16, the median over seeds
  7 to 19) and none with 16. With this wording the row cells with supernodes (honest, and half the
  columns withheld with 16 and with 32 subnets) and the withheld custody cell with a fifth of the
  nodes hoarding run as under draft 1, event for event on all 13 seeds, and so do 48 of the 52
  seed-cells of the row cells with supernodes and a fifth or half hoarding.
- *Draft 1, and a first version.* Draft 1 ended both on the probed cell; when the toy's rebuilders
  stopped pushing to supernodes (an exploration), supernodes deferred on a claim that came in an
  acknowledgement, received the probed cell, and ended one cell short of a column. A first version
  of this rule counted a verified claim only from a peer in the node's view, and row members decoded
  two to four times as many rows (with 16 subnets, 31 against 9 per run, the median over seeds 7
  to 19) for no change in time or bytes: their claimants were mostly supernodes rebuilding the row
  in the second phase, which have no relation on it, so their claims reach a member in the
  acknowledgement of a column chunk (§4.2, `fill`).
- *What it leaves to the member check.* A claimant that rebuilds a row, answers the probe and pushes
  nothing (the toy's `--fault hoard`) passes the probe and ends the members' duties. Where an honest
  supernode keeps the row, its second phase repairs the row, under this rule and under draft 1's
  alike: in three traced runs no supernode ended its duty on a verified claim, presumably because a
  claim on a row reaches a supernode outside the subnet only in the acknowledgement of a cell the
  supernode sent, which a hoarder sends while still short. Where none does, the row is lost: without
  supernodes, a fifth of the nodes hoarding left custodians short in every run over seeds 7 to 19
  (16 subnets, half the columns withheld), each time a subnet whose honest members had deferred to a
  hoarding reconstructor; the member check (above) closed this in those runs wherever the subnet had
  an honest member, against a claimant that repairs nothing.

**The member check** (decided 2026-10-09). Measured in the toy over seeds 7 to 19 at 60 nodes, 16
subnets, half the columns withheld (`toy/README.md`):
- *What it addresses: a claimant that rebuilds, passes the probe and repairs nothing* (the toy's
  `--fault hoard`). Without supernodes, with a fifth of the nodes hoarding, custodians were left
  short on every seed without the check and on 3 of 13 with it; with half hoarding, on 13 and on
  10. Every seed on which each subnet has an honest member completes.
- *And a false claim the cell's arrival let through.* For the duty, the claim holds when the
  probed cell arrives, from anyone; a claimant that never answers ends the duty when another peer
  brings the cell in time, though it is itself penalised (above). Among the toy's liars (`--fault
  claim`, which claim their row and answer no ask) without supernodes, this happened 1 to 3 times
  per run on 5 of 13 seeds, and each time the member check sent the member to rebuild instead of
  trusting the liar (all five seeds traced; measured when that cell also passed the claimant). The
  few (node, row) pairs left short on those seeds, with and without the check, are the liars' own
  rows, which the toy's liars never rebuild: the check moved their count by one or two, on three
  seeds.
- *What it does not address.* A subnet whose members all misbehave (seeds 14, 17 and 18 at a
  fifth): nobody honest is there to check. A member whose custody columns are all among the
  published ones holds its cells whatever the claimant does (0.3 % of members with 8 of 128
  columns and half withheld), so the check passes for it, though its subnet's other members still
  check. A claimant that pushes each member exactly its custody cells of the row and withholds the
  rest passes the check (the toy's `--fault hoardm`: without supernodes, a fifth of the nodes
  doing so left custodians short on all 13 seeds); sampling the repair samples for it. Where an
  honest supernode keeps the row, its second phase already repairs what a hoarder withholds,
  and the check never fired there.
- *What it costs.* Where nobody misbehaves, nothing: in five cells (rows honest with and without
  supernodes, withheld with 16 subnets with and without, withheld with 32 with supernodes) it never
  fired and every event is the same. A rescued block completes later, 3.25 / 3.44 s (p50 / p99)
  against 2.44 / 2.71 s without hoarders, since the member rebuilds at the third phase after a
  deferral; its bytes are not higher (2.33 copies against 2.36), since hoarders push nothing. In ten
  traced runs with hoarders or liars all 162 firings were on a misbehaving claimant's claim: a
  needless rebuild, an honest claimant's repair still on its way when the window ends, was not seen
  at 60 nodes. It is the case to watch at larger scale, where repair travels further.

**Sampling the repair.** Extended, never redrawn, since the larger sample could have been drawn at
once ("toss a coin until you like the result" is the alternative the post rules out); allowing
losses is LossyDAS's answer to a custodian that has not yet received a repaired cell when asked.
Measured over seeds 7 to 19 at 60 nodes, 16 subnets, half the columns withheld (`toy/README.md`):
- *Against a claimant that repairs only the members' cells* (a fifth of the nodes, without
  supernodes): short on 13 seeds with the member check alone, 5 with `(3, 1), (6, 2)`, 3 with
  `(4, 0), (8, 1)` or `(6, 0), (12, 1)`, the seeds on which a subnet has no honest member. In a
  traced run every failed sample was on a hoarder's claim. The lenient form passed partial repairs:
  the hoarding members' own pushes had filled some columns, and 4 of 6 cells came. A rescued block
  completes at 4.2 s (p50) against 2.4 s without the fault, the rebuild waiting out the deferral and
  two sample steps; the member check alone catches a claimant that repairs nothing at 3.25 s.
- *Where nobody misbehaves* no sample failed in any form, with or without supernodes, and the times
  and bytes are within the seeds' spread; the cost is the sampled cells, at `(4, 0), (8, 1)` without
  supernodes 532 per run, 4.4 per node and block averaged over all nodes. With supernodes every cell
  completed in every form.
- *Where custodians do not answer.* The toy's liars answer no ask, so a sample cell asked of one is
  lost: with a fifth of the nodes lying, `(4, 0), (8, 1)` failed on honest claimants in 18 of 41
  verdicts at seed 7 and in 46 of 48 at seed 8 with supernodes, where a liar is a supernode and so
  a custodian of every column, and the strict forms had members rebuild 21 to 26 rows per run
  more, without changing completion.
- *Re-asking a lost cell* (`REPAIR_REASK`), over the same seeds. Among liars the strict forms'
  failed samples fell from 15 to 27 per run (median) to none at the median, at most 22 in one run,
  and members rebuilt as many rows as with the member check alone (74 against 80 without supernodes,
  46 against 45 with them, at `(4, 0), (8, 1)`). Where no cell was lost (no fault, and a claimant
  that repairs nothing) the runs are the same event for event. Against a claimant that repairs only
  the members' cells, `(4, 0), (8, 1)` and `(6, 0), (12, 1)` still leave short only the seeds
  without an honest member, and a rescued block completes half a second later, at 4.7 s, for the one
  more wait; `(3, 1), (6, 2)` stays lenient (short on 4).
- *At 500 nodes* (32 subnets, half the columns withheld, seeds 7 to 9, `(4, 0), (8, 1)` with
  re-ask against the member check alone): where nobody misbehaves, with and without 25
  supernodes, the member check never fired, no sample failed, and times and bytes are similar
  (2 312 to 2 360 ms at the median without supernodes, 1 170 to 1 178 ms with them); the sample
  asked 2.7 cells per node and block without supernodes, about a tenth of that with them, since
  a supernode's second phase makes most rows whole in the members' view first. A fifth of the
  nodes repairing only the members' cells left nobody short at this size even with the member
  check alone (2 354 to 2 388 ms). With the sample, two seeds are similar and on the third (seed
  7) all nine failed samples were on one row the hoarder had not repaired; its members rebuilt it
  after the deferral, two sample steps and the re-ask's wait, and the block's last custody cells
  came 2.3 s later than in the run with the member check alone, where an honest node had rebuilt
  that row earlier (the runs diverge from the first block; which node is not traced). The rescue
  path's length, `DEFER_WINDOW` plus two `SAMPLE_WAIT` and the re-ask's, is the cost to cut; a
  shorter wait was not measured.

**Rebuilt cells marked seen** (kept as an option, 2026-11-01).
- *It needs the sample.* The forwarded copies also repair by accident: two hoarding
  reconstructors that forward each other's rebuilt cells fill columns that neither repairs on
  purpose. Marked seen, such hoarders leave more columns unrepaired. At seed 11 of the toy's
  500-node rows it was 34 columns instead of 5, in a network model that the runs matched. The
  member check, which looks only at the member's own columns, misses them, and the sample catches
  them. With the member check alone, the option left more custodians short at three seeds, so it is
  never on without the sample.
- *Measured at ten seeds* in the toy's 500-node rows: seeds 7 to 16, 32 subnets, half the columns
  withheld, no supernodes, a fifth of the nodes repairing only the members' cells, the sample
  `(4, 0), (8, 1)` with re-ask. The member check alone left 5 of 20 blocks short, the sample 1, and
  the sample with rebuilt cells marked seen none. In honest cells the two together cost about 0.5 %
  more copies (0.01 a block) and 0.004 more of control, against neither, with no direction in time.

**A custodian's alarm** (kept on 2026-11-01 for networks without an honest supernode).
- *Its wait, in the toy.* In the toy's 500-node rows without a fault, no custodian completed later
  than 2.944 s over seeds 7 to 16. The measurements use 3.5 s, with `ALARM_NEXT` 1.5 s and
  `ALARM_MAX` 3. The member's ask starts its promise at its write in the toy since 2026-11-17, at the
  decision before; and since 2026-11-17 a member that rebuilds the row answers the alarm from
  `decode_group`.
- *Measured again on the rules as they stand* (2026-11-18), in the 500-node cells of the one-column
  hoarder at seeds 11, 12 and 16, with writes completing at once as before. Without the alarm 2 of 6
  blocks were short (108 custodians): the same blocks as before but seed 16's first, which now
  completes. With it none was, for 61 alarms and 10 rebuilds, as before. In honest cells and under
  false claims (seeds 7 to 9, rebuilt cells not marked seen) no alarm fired. The figures below were
  not measured again.
- *Measured at ten seeds*, before the member's changes of 2026-11-17 above, as above, with the
  sample and rebuilt cells marked seen. A fifth of the nodes repaired all but one withheld column
  per subnet, with no supernodes. Without the alarm, 3 of 20 blocks were short (165 custodians);
  with it, none, for 61 alarms and 10 rebuilds, all at the two short seeds. With 5 % supernodes none
  was short without it, since a supernode's second phase rebuilds the row: the alarm is for networks
  without one. In honest cells, with the builder at 1 Gbps or at home, no alarm fired; the latest
  custodian completed at 2.6 and 2.8 s. Under false claims by a fifth of the nodes, 2 alarms fired
  and no rebuild followed.
- *Not measured:* the wait on thinner links, where the honest tail is longer; and the alarm since
  the probed cell is drawn at random. These runs probed the lowest index a member lacked, which
  was never the hidden column; drawn at random, the probe can ask for it, and a claimant that
  serves it to nobody then fails the probe itself.

**Repair across groups** (`note_push` under every group the chunk fills since 2026-11-17).

**A rebuilt chunk completes the groups it fills.** Draft 1 filled the column without the check, so
the member never completed it: it neither stopped pulling it nor told its peers, and the toy counted
it short (in one run of the repair floor's measurement below, before the fix).

**Every member keeps a link to each column.** In the toy's withheld row cell over seeds 7 to 19 at
60 nodes, without the floor five runs left custodians short, and each was a missing link. In four, a
column with two custodians missed a cell because neither was linked to the only member that rebuilt
the row; the deferral on a claim, which cancels a second decode once the first is verified, makes a
single rebuilder common. In the fifth, a subnet had two members, linked only to each other among
members, and each gathered 63 cells of its rows from the columns' custodians, one short: neither was
linked to the only custodian of one published column, so neither row was ever rebuilt. With
`REPAIR_FLOOR = 1` all thirteen runs completed, at 1 to 30 added links per run, with completion
times and bytes within the seeds' spread (§6.2, `toy/README.md`).

**A supernode keeps every row.** In the toy at 60 nodes, three supernodes (5 %) on datacenter links
complete every custodian on all thirteen seeds of the custody cell whose proposer withholds half the
columns, which nothing else recovers, in 1.20 s at the median and 1.25 s at the tail (the medians
over the seeds); they complete the 32-subnet withheld row cell, which its subnets without members
left short, in 1.20 and 1.83 s, and they take the 16-subnet cell from 2.44 / 2.71 s to
1.20 / 1.76 s. The cost is bytes: 3.3 copies of a node's custody in the withheld row cells against
2.4 without supernodes, and 3.8 in the custody cell (§6.2, `toy/README.md`), most of it duplicate
pushes of the fast class: with a budget of `R` for cells it is 2.6 to 2.8 copies, with the tails 0.1
to 0.15 s shorter (§6.3, `R_NODE`, for later study).

**A row held on the columns is on its way.** Without the wait, on home links, three supernodes in
the toy's honest row cell rebuilt 186 rows that nobody had withheld, and the cell's tail went from
1.09 to 1.49 s (seed 7). With the wait, no supernode rebuilt a row in any of the thirteen honest
custody or row runs. In the withheld cells the three supernodes still rebuild most rows more than
once (131 to 167 of the 192 row decodes that three supernodes and two blocks of 32 rows allow); a
jitter longer than a rebuilt row's trip to the other supernodes would cancel more of them, not
measured. For a member it changed no event of the seed-7 row cells without supernodes.

**A rebuilder pushes as a source.** Without supernodes, in the withheld 16-subnet row cell, where
members on home links rebuild, it is better on every count over the thirteen seeds: 12 900 repair
pushes against 36 900, 2.19 copies against 2.36, the tail 2.62 s against 2.71 (the median over the
seeds) and 2.68 against 2.82 at the worst seed. With supernodes on datacenter links, whose budget is
the fast class's six, it saves 0.15 copies and costs 0.21 to 0.25 s at the tail (2.00 against 1.76 s
with 16 subnets, 2.04 against 1.83 with 32), and in the custody cell 0.05 copies for 53 ms. With the
fast class's budget off for cells (§6.3, `R_NODE`) it saves 0.41 copies in the 16-subnet cell for
0.1 s at the median and the tail (seeds 7 to 9).

**Whom rebuilt cells go to.** A supernode keeps every row, so a rebuilder's push into a column
reaches it too, and where several nodes rebuild a row their pushes cross in flight: at 500 nodes
(seed 7) 88 % of the rebuilt cells pushed in the withheld custody cell arrived as duplicates, the
whole of that cell's extra cost over the honest one (3.76 against 2.83 copies). The duplicates are
bounded by what a node's own peers push it, so no estimate of the network's size is needed to bound
them. Measured over seeds 7 to 19 at 60 nodes with three supernodes (the toy README): offering the
cells to the nodes that keep every row instead of pushing them saves 0.17 to 0.33 copies at no cost
in time; offering every rebuilt cell, as a row's are, saves 0.5 to 0.7 copies and costs 60 to 110 ms
at the median; leaving the keepers out saves as much as offering to them, but costs the custody cell
a 2.3 s tail, since a supernode left out has only its own rebuild, after a deferral.

### 4.7 The source

```python
def publish(block, d, shards):                         # the payload's builder; v0.3 §5.1 over the relation
    g = group_of(block, d)                             # §1.1's table: the payload's key, a column's id
    if expired(g) or not live(block.slot): return      # too late: past its live window (v0.3 §8.1)
    open_group_source(g, d)                            # hdr[g] = d; T_of, interest, known_at
    T = type_of_group(g)
    for s in shards:                                   # the source holds every chunk from the start
        f = Chunk(slot=block.slot, beacon_block_root=block_root(block), group=g,
                  descriptor=d, index=s.index, proof=s.proof, data=s.data)    # descriptor: design A (B open, protocol.md §1)
        store(g, s.index, f); mark_seen(chunk_id(f))
        gossip_history.put(f)                          # heartbeat gossip may offer it (§4.8)
    mine[g] = all_bits(N(d)); state[g] = COMPLETE; stop_pull[g] = True
    if not T.params.EAGER: return offer_at_publish(g, d)   # a pull-only type: nothing pushed (§4.7)
    origin[g] = bitmap(set())                          # [P4] our holding names the chunks acknowledged so far (§4.7): none yet
    plan = []
    for i in range(N(d)):                              # index order; each chunk's targets see earlier plans
        f = chunks[g][i]
        targets = choose_push(f, candidates_for_source(f), budget=R, at_source=True)   # v0.3 §5.3
        for p in targets: note_push(p, g, i)
        plan.append((f, targets))
    led = set()
    for copy in range(R):                              # the first copy of every chunk before any second  [c2]
        for f, targets in plan:
            if copy < len(targets):
                p = targets[copy]
                if p not in led:                       # [P4] a peer's first chunk from us follows our holding
                    led.add(p)                         #   naming it, as a forwarding node's holding precedes its pushes
                    send(p, holding_of(g, origin[g] | bitmap({f.index})), urgent=True)
                if not enqueue(p, f, urgent=False): unpush(p, g, f.index)   # refused: offered instead (v0.5 §5.2)
    planned[g] = {f.index: set(targets) for f, targets in plan}   # [c3] the relation peers not chosen to be
                                                       #   pushed a chunk are offered it at its acknowledgement
    if SOURCE_OFFERS == PUBLISH:                       # the source's own choice (§4.7, §6.3): those offers now,
        for f, targets in plan:                        #   and its holding grows at each chunk's first write
            for p in source_pool(T, g, colour_of(g, f.index)):
                if p not in targets: announce(p, g, bitmap({f.index}))

def origin_written(f):                                 # SOURCE_OFFERS = PUBLISH: a chunk of a group we publish
    g = f.group                                        #   leaves for the first time; it joins our holding, which
    if g not in origin or origin[g].has(f.index): return   #   goes where origin_acked's goes (§4.2)
    origin[g].set(f.index)
    for q in suppression_scope(g): send_have(q, g)

def offer_at_publish(g, d):                            # a pull-only type's source (EAGER off) pushes nothing, so no
    origin[g] = all_bits(N(d))                         #   acknowledgement can come: every chunk is offered at once, to
    for q in suppression_scope(g): send_have(q, g)     #   the peers origin_acked would offer it to, and our holding
    T = type_of_group(g); offers = {}                  #   names every chunk, which the offers show anyway
    for i in range(N(d)):
        for q in source_pool(T, g, colour_of(g, i)): offers.setdefault(q, set()).add(i)
    for q, idx in offers.items(): announce(q, g, bitmap(idx))

def origin_acked(g, i):                                # [c3, P4] a chunk of a group we publish is acknowledged:
    if SOURCE_OFFERS == PUBLISH: return                #   (none at PUBLISH: the offers left at publish, §4.7)
    if origin[g].has(i): return                        #   a peer's holding names it (§4.3), or
    origin[g].set(i)                                   #   a copy's room timed out first (§4.11). It joins our
    for q in suppression_scope(g): send_have(q, g)     #   holding, which goes where a forwarding node's goes (§4.2)
    T = type_of_group(g); fam = T.family(g); c = colour_of(g, i)   # [c3] the relation peers not chosen to be
    for p in [q for q in source_pool(T, g, c) if q not in planned[g][i]]:
        announce(p, g, bitmap({i}))                    #   pushed it are offered it; a refused push is owed (v0.7)

def candidates_for_source(f):
    T = type_of_group(f.group); g = f.group; fam = T.family(g); c = colour_of(g, f.index)
    if UPLINK >= STRIPE_UPLINK: pool = links(T)                                   # [c13] every link
    else: pool = source_pool(T, g, c)                                             # the relation, as the other nodes do
    return [q for q in pool if wants_from_me(q, g).has(f.index)]

def source_pool(T, g, c):                              # whom a source pushes below STRIPE_UPLINK, and offers to
    fam = T.family(g)
    rel = [q for q in links(T) if c in push_out[q][T][fam]]
    return rel or links(T)                             # none in fam for colour c: the links, filtered by interest
                                                       #   by the caller, as gossipsub's fanout (below)

def unpush(p, g, i):                                   # [c3] a chosen push that will not be made: not counted, under
    for (g2, i2) in fills(g, i): pushed[p][g2].clear(i2)   # every group note_push marked, and owed to a relation peer,
                                                       #   or at a source to a peer of the
    if p in mesh or (g in origin and p in source_pool(type_of_group(g), g, colour_of(g, i))):   # pool as it stands
        owe(p, g, bitmap({i}))                         #   now (v0.5 §5.2's, with the fallback links)
```

**What carries over.** Batch order (card 2) and striping (card 13) are v0.3 §5.1 unchanged, and the
window (card 14) is v0.3's counted in bytes (§4.11). So is v0.7's single offer: the source offers a chunk only to the peers of its pool (the
relation for the chunk's colour, or the fallback links, below) not chosen to be pushed it, and a
peer whose push its queue refuses is owed the chunk instead, so these two paths never offer a peer
the same chunk twice; a join (`join_push`, §4.1) or heartbeat gossip (§4.8) may offer it again. The
generalisation is that
the candidates are the links that want the chunk, which for a pre-seeded peer (a node with the blobs
from its mempool, I8) is decided by the holding it sent before any data, so a source holding *part*
of a group pushes only what its peers lack.

**A refused push to a fallback link is owed.** `protocol.md`'s `unpush` (v0.5 §5.2) owes a push the
queue refuses to a mesh peer, there the set the source pushes and offers to. With no relation in the
family for the chunk's colour that set is the fallback links (`source_pool`), so `unpush` here owes a
peer of the source's pool too, the pool as it stands when the push is refused. As for a relation peer, the owed offer may leave
before the chunk's acknowledgement, and at a slow source an asker that waits past the promise parks
it for the group.

**When the source offers** [c3] (v0.9 §5.1). A chunk is *acknowledged* at the first holding naming
it, from any peer (§4.3), or, if none comes, at the first window timeout of any copy of it (§4.11; a
closed connection drops its copy's room, `protocol.md` §8.1), as `protocol.md`'s glossary has it.
- **A source offers a chunk at its acknowledgement** by default (`SOURCE_OFFERS = ACK`), for every
  object type a source pushes, the rule v0.9 had for every source. The offers trail the pushes by
  about a round trip.
- **Offering at publish is the source's choice** (`SOURCE_OFFERS = PUBLISH`). No rule at another
  node needs either setting: a receiver takes an offer whenever it comes. The setting changes how a
  group spreads, as any default does (`protocol.md` §8.3): what other nodes are asked and pushed,
  and when they complete. A source whose offers draw asks it cannot answer in time is parked by its
  askers for the group, a cost it bears itself. At `PUBLISH` the source offers each chunk at
  publish, by the rule it would use at the acknowledgement, to its pool as it stands then, and its
  holding grows at each chunk's first write (`origin_written`), as before v0.9; an acknowledgement
  then does nothing (`origin_acked`), not even for a chunk a peer rebuilt before the source wrote
  it. A source that wants P4's cover toward its pool offers at the acknowledgement (below). A client
  may key the choice on its uplink, as striping is (`STRIPE_UPLINK`); this document does not
  (below).
- **A chunk that no peer wants** is pushed to no one and never acknowledged. That costs nothing: its
  offers would have gone to no one either.
- **A pull-only type's source** (`EAGER` off) pushes nothing, so no acknowledgement can come. It
  offers every chunk at publish, by the rule it would use at the acknowledgement, to its pool as it
  stands then, and its holding names every chunk (`offer_at_publish`). With no pushes, the offers
  have nothing to race. They name the source to those peers, which [P4]'s paced holding does not
  hide. No setting publishes a pull-only type: rows come from cross-fill or a rebuild.

**Open: a chunk that is never acknowledged,** as `protocol.md` §5.1 names it. At
`SOURCE_OFFERS = ACK` the source offers a chunk to the rest of its pool only at the chunk's
acknowledgement, and a chunk has none while no holding naming it reaches the source and no copy of
it times out in the window (§4.11). That happens when each of its chosen pushes was refused or
skipped by projection, stays queued to a peer that does not read, or went with its connection before a holding or
the timeout (`protocol.md` §8.1). A refused or skipped push to a relation peer, or to a fallback
link where the chunk's colour has no relation, is offered to that peer instead (above); one to any
other link, which only a striping source pushes, is forgotten (`unpush`, as `protocol.md` §5.2). A
holding naming the chunk comes once a peer that holds a copy claims it to the source: a copy
delivered before its connection closed and forwarded, a rebuilt copy, or a decode claim, which names
every chunk of a coded group (§4.2, §4.6). Until then the source offers the chunk only once a peer
has asked for it and the source's answer is acknowledged: a peer offered the chunk in place of its
push, at a join (`join_push`, §4.1) or, for a type whose `ANNOUNCE_EXTRA` is `SAMPLE`, by heartbeat
gossip outside its relations (§4.8), or a peer that asks without an offer, by the source's custody
or as a routed request (§4.5, §4.10). No rule bounds that wait within the group's lifetime. At
`PUBLISH` the chunk is offered at publish.

**A source's links in a family it does not custody.** A proposer holds every column of its block but
custodies few of them (§1.3), and no rule forms a relation in a family a node has no duty in. A
source never waits for links: it publishes at once to the links it has. On top of its fanout, three
layers keep its chunks moving:
- **The fanout.** Below `STRIPE_UPLINK` a source pushes and offers a chunk to its relation peers for
  the chunk's family. With no relation in the family for the chunk's colour, it uses the links whose
  interest holds the chunk (`source_pool`), as gossipsub's fanout reaches a topic its publisher has
  not joined. A push to one of them that a full queue refuses is owed, as to a relation peer
  (`unpush`). The fallback holds for the payload too, where `protocol.md`'s source with no
  mesh peer sends nothing (§6.1).
- **1. Links kept for the families it will publish** (`SOURCE_FLOOR`, a parameter). A node keeps at
  least `SOURCE_FLOOR` links to custodians of each family it will publish, opened through the
  rendezvous as `keep_floor` opens its own (§4.1). A proposer knows its slot in advance and can open
  them before it. 0 leaves the source to the hunt. Whether the floor pays depends on what the hunt
  costs, on the network and on the binding, so it has no default.
- **2. A hunt when a chunk has nowhere to go.** A source with no link whose interest holds a family
  it publishes reaches a custodian through the binding's means, while the rest of its chunks go out:
  a lookup at the rendezvous and a new connection, or a send outside the links over the transports
  of §7's fetch outside the links. It costs a lookup or a handshake while those chunks wait: one
  round trip where the node already knows a custodian's record, more where it must look one up.
- **3. The code.** A column that reaches no custodian from its source is a withheld column, and the
  rows rebuild it where rows are kept (§4.6: the row setting, or supernodes under custody; under
  custody alone no node rebuilds a column).

**The source's holding is paced** [P4], as in v0.4 §5.1 and for the same reason: a holding that
names every chunk before any has left can come only from the source.
- **What it names.** A group's holding names the chunks acknowledged so far, at `ACK`. A chunk joins
  it at its acknowledgement (above), for every object type a source pushes, and the holding then
  goes to the suppression scope, as a forwarding node's does when a chunk arrives (§4.2).
- **A pushed peer.** Before its first push to a peer, the source sends the peer a holding naming
  that chunk, urgent, so that it goes just ahead of it; once per peer, whether or not the queue
  admitted either (`led`).
- **Per group.** The rule is per group, so a proposer paces the holding of each column group it
  publishes.
- **The claims.** The two claims (§1.5) follow the paced bitmap: a source claims neither
  `claim_all` nor `complete` for a group it publishes until every chunk of it is acknowledged. That
  is what v0.4 does by reading its decode claim from a full bitmap.
- **Not covered: a pre-seeded node** (I8). It holds part of a group before its peers but did not
  publish it, and its first holding names what it holds, which is what lets its peers skip it.

**Merging the source's holdings** (`MERGE_HOLDINGS`, §4.2, permitted). v0.4 allows holdings that would
leave together to be merged into one; here a holding still in the source's queue takes the newer
chunks instead of a second holding going out.

**Open: fewer holdings.** Keeping the source's holdings back for a set time, or sending them to
fewer of the scope's peers, which v0.4 does not provide for, is for later study.

#### Rationale

**v0.7's single offer** (since 2026-11-04). Of the toy's thirteen recorded cells then (2026-11-04,
with the earlier transport) only the thin lossy one (`loss-thin`), whose queues refuse a tenth of
the chunks at admission, met the second offer: it now sends 91 fewer offers of 82 938 over its three
payloads, and its warm medians, of completion and of copies, stay as they were.

**A refused push to a fallback link is owed** (decided 2026-11-14). Without it, a fallback target
whose push was refused would be neither pushed the chunk nor offered it at the acknowledgement,
whose offers skip the planned targets (`origin_acked`). When every copy was refused, no copy is in
the window either, so the acknowledgement itself waits for a holding that names the chunk, such as a
decode claim, or for a later copy, an answer to an ask, to time out. Not taken: an offer to a
refused fallback target at the chunk's acknowledgement, which then comes that late; and leaving the
gap.

**When the source offers** (v0.9 §5.1, taken for every object type on 2026-11-11; the source's choice
since 2026-11-18).

**Offering at the acknowledgement, by default.** Offered at publish, the offers race the pushes: a
transport that takes the whole batch at once lets every offer leave at once, the relation asks for
chunks whose pushes are still queued, and the source answers on top of its pushes. The acknowledgement
is the one event the source sees whatever the transport holds (§4.11).

**Offering at publish, the source's choice** (decided 2026-11-18). Two things decide it:
- *Its uplink.* The offers draw asks on top of its pushes. In the toy's custody cell (seeds 7 to 9,
  writes completing at once and one write at a time), a 1 Gbps proposer that offers at publish
  completes its block 30 to 114 ms sooner at the median on the toy's 60-node graph, and 13 to 92 ms
  sooner on the research harness's 100-node one, and answers 4.7 to 12 times as many asks.
  A 50 Mbps proposer completes it 24 ms later at 60 nodes and 26 ms later at 500 (below, against
  the acknowledgement).
- *Its privacy.* Every chunk offered at once, by the one node that holds them all, names the source
  to those peers, and the paced holding [P4] then hides nothing from them. Toward the peers outside
  its pool (the relation for the chunk's colour, or with none the fallback links, `source_pool`) the
  settings are alike: for a type whose `ANNOUNCE_EXTRA` is `SAMPLE`, its heartbeat gossip draws on
  every chunk at either setting, since `publish` puts each in the gossip history (§4.8), and for one
  at `ALL_JOINED` or `NONE` there is none. A source that wants P4's cover toward its pool offers at
  the acknowledgement.

Copies do not decide it: offering at publish adds 0.06 to 0.14 copies of the block received per
node, data and control, on the toy's 60-node graph, and saves 0.10 to 0.19 on the research
harness's 100-node one. A client may key the choice on its uplink, as striping is (`STRIPE_UPLINK`);
this document does not, since a fast source may still want P4.

**A pull-only type's source** (decided 2026-11-18).

**A chunk that is never acknowledged, in the toy.** The recorded cells do not churn, and a churn cell
bounds it only where every copy of one chunk is lost with its connection; no toy knob closes a
source's links in the middle of a message.

**The acknowledgement against the document before, in the toy.** At 60 nodes (seeds 7 to 16; the
median of the seeds, and its range):
- **The payload** completes 0 to 8 ms sooner, and its source saves bytes where the transport takes
  the batch at once (below, "The source's offers, card 3 at the source").
- **A 50 Mbps proposer's custody block** completes 24 ms sooner (−46 to +10, sooner on eight
  seeds).
- **A column's source** uploads 5 to 28 % less and is asked 88 to 99 % less (with §4.11's rule, 5
  to 29 % and 87 to 96 % less than with that rule alone). The rows' proposer uploads 1.49 copies of
  its block instead of 2.07.
- **The cost.** The rows complete 178 ms later (69 to 304, later on every seed), more than with no
  source offers at all (128 ms), and the rows with liars 214 ms later. A 1 Gbps proposer's custody
  block completes 38 ms later (24 to 114).
- **Why the rows pay at 60 nodes.** At seed 7 the proposer's relation peers pulled from it, while it
  pushed, the cells it did not push them. Offered each cell only at its acknowledgement, they
  completed 410 to 470 ms later. The other nodes moved by 56 ms.

At 500 nodes (degree 70):
- **Against the document before** (seed 7, one run each; the median): the payload completes 4 ms
  sooner (tier 4 in the all-home network), the rows 8 ms sooner, a 50 Mbps proposer's custody block
  48 ms sooner, and a 1 Gbps proposer's 5 ms later (a fifth of the nodes sampling).
- **Against offers per type** (below; seeds 7 to 9, paired by seed; the median of the seeds, and
  its range):
  - the rows complete 7 ms later (−15 to +17), and with §4.11's rule 28 ms later (18 to 54, later
    on every seed);
  - a 1 Gbps proposer's block 9 ms later (6 to 15);
  - a 50 Mbps proposer's 26 ms sooner (18 to 38), and 41 ms sooner at the tail;
  - a column's source uploads 8 to 33 % less, and is asked 57 to 98 % less.
- **The relation peers at 500 nodes.** At seed 7, 12 of the 499 nodes pull more than 20 cells from
  the rows' proposer with offers per type (at 60 nodes, 26 of 59, in the document before). With the
  offers at the acknowledgement they complete 18 ms later at the median (−140 to +292). The two of
  them that completed first, at 1.79 and 2.05 s, are 292 and 253 ms later. The 449 that pull
  nothing from the proposer move by 5 ms.
- **So the rows' cost is a 60-node finding.**

**The alternative: offers per type** (decided 2026-11-10, replaced 2026-11-11). A field per object
type had the payload's source offer at the acknowledgement and a column's at publish.
- **What it kept:** the rows' early completion at 60 nodes, 175 ms sooner than with offers at the
  acknowledgement for every type (seeds 7 to 16), and 300 ms sooner with §4.11's rule; and a
  1 Gbps proposer's block, 44 ms sooner at 60 nodes and 9 ms at 500.
- **What it gave up:** at 500 nodes, a column's source's saving (8 to 33 % of its upload) and a
  50 Mbps proposer's 26 ms, for the rows' 7 ms (28 with §4.11's rule).

One rule for every type, as v0.9 has it, was taken instead; since 2026-11-18 any source may offer at
publish (`SOURCE_OFFERS`, above).

**A source's links in a family it does not custody** (decided 2026-11-13; found 2026-11-09, writing
`candidates`' interest rule, §4.1).
- *In the toy.* Its setup gives the proposer a relation with every custodian it links to, which are
  the fallback's peers. Its custody and row settings use a `SOURCE_FLOOR` of 2, at setup
  (`--source-floor`). The hunt is not measured. At 500 nodes (one seed, §4.11), with half the columns
  withheld, every custodian completed through the rows in 2.4 s at the median.
- *Not taken:* holding the publish until the links are there, which would delay every family for one
  that the code can recover. No layer reaches a column that no node but the source custodies (seven
  of 128 in the toy's 60-node cells); routed sample requests do (§4.10).

**The source's holding is paced** [P4].
- **Why not at the write.** Until v0.9 a chunk joined at its first write, as it still does at
  `PUBLISH`. Where the transport takes a batch at once, that named chunks which had not left (v0.9
  §5.1).
- **The signs that remain.** These remain here too, from v0.4's list and `protocol.md` §5.1's:
  - the source offers every chunk, at `ACK` about a round trip after its first copy;
  - its holding tends to grow faster than anyone's;
  - it offers the group's chunks of the relation's colour at once to a peer that joins its relation
    (`join_push`, §4.1);
  - it is usually everyone's first sender;
  - and, at either setting, for a type whose `ANNOUNCE_EXTRA` is `SAMPLE`, its heartbeat gossip
    draws on every chunk of the group for the peers it samples outside its relations at each of its
    next three heartbeats, less what `announce` leaves out, since `publish` puts every chunk in the
    gossip history (§4.8), at `ACK` without waiting for any chunk's acknowledgement. Keeping a
    source's chunks out of the gossip history until they are acknowledged is left, as in
    `protocol.md` §5.4, to the work on the source's privacy.
- **The cost of the later holding.** It names a chunk about a round trip later than at the write.
  A relation peer that got the chunk from a forwarder may push it back to the source until the
  holding arrives; cancel drops what is still queued. In the toy at 60 nodes (seeds 7 to 16):
  - with writes that complete at once, 2 to 6 of a payload's chunks come back a message at the
    median of the seeds, and up to 59 at one seed;
  - with §4.11's rule, 0 to 2, and up to 17;
  - no column's cells come back.

What P4 costs here depends on how many groups a source publishes. For the payload, one group, it
costs nothing (§6.1). A proposer of 128 column groups sends a holding per cell to each peer in that
column's scope: in the toy at seed 7, about 38 800 holdings of 52 bytes over three blocks, 0.68 MB
a block, which is about 108 ms of a 50 Mbps uplink. In the toy at 60 nodes (seeds 7 to 16) the
custody block completes 116 ms later at the median of the seeds (53 to 164 ms) and 106 ms later at
the tail, and the row cells 98 ms later at the median and 132 ms at the tail. With a 1 Gbps
proposer the cost is 6 ms at the median. Its peers, no longer told that it holds every cell, also
offer it cells. Under the liar fault P4 leaves more row members short (108 (member, row) pairs over
ten seeds against 80; not traced). With v0.5 merged (2026-10-21) 2 pairs stay short over the same
seeds, none on eight of them. It is v0.5's last resort (its §6.1): when every announcer of a cell
is parked, each is asked once more, at waits that double. In a toy check at three seeds, without
it the members stay short as before v0.5 (12, 24 and 18 pairs against 12, 22 and 20), while asking
announcers beyond the first sixteen changes nothing; the doubling waits are why those rows complete
late. The other cells move by a few ms (`toy/README.md`).

These figures were measured with the holding at the write. At the acknowledgement P4 sends as many
holdings (38 808 at seed 7), a round trip later. Moved there alone, with a column's offers still at
publish, the holding moves the toy's column cells at the median, over seeds 7 to 16 (the median of
the seeds, and its range):
- the rows by 0 ms (−20 to +34), and the rows with liars by −1 ms;
- the custody block by −5 ms (−34 to 0) with a 50 Mbps proposer, and by −6 ms (−9 to +4) with a
  1 Gbps one.

The offers at the acknowledgement then move them as above.

**Merging the source's holdings** (measured with the holding at the write) takes back little of P4's
cost. With writes that complete at once, only holdings made in the same instant are in the queue
together: 7 % of the slow proposer's holdings merge, and the custody block gains 10 ms of P4's 116
at the median and 12 ms at the tail, the rows 4 ms at the median and 20 ms at the tail. With a
transport that takes one write per connection at a time (the toy's `--send-buffer 1`), a holding
also waits while another entry to the same peer goes out: 18 % merge, and the custody block gains
16 ms of P4's 80 ms there, the rows again 4 ms at the median. Copies and completion do not change,
and under the liar fault 100 pairs stay short against P4's 108 (both before v0.5). Most holdings
would leave alone anyway: at seed 7, 59 % find no earlier holding of their group still waiting, in
the queue or in the transport. Taking back more needs fewer holdings, which v0.4 does not provide
for: holding them back for a set time, or sending them to fewer of the scope's peers; both are for
later study. The figures are in `toy/README.md`.

**The source's offers, card 3 at the source,** cost a home builder bytes.
- **At publish**, in the toy's tier 4 cells:
  - they drew asks that the builder answered after its first copies, 0.34 to 1.35 copies of the
    message over three seeds, with 81 to 94 % of those answers arriving as duplicates;
  - without the offers a 50 Mbps builder uploads 1.6 to 1.8 copies of the message instead of 2.1
    to 2.9, and its cells' medians move by less than 10 ms;
  - a 1 Gbps builder uploads 2.0 copies instead of 10 to 12, but completes 10 ms later;
  - a 1 Gbps proposer of columns completes 75 ms later, since its offers let peers pull from it
    while its uplink has room.
- **At the acknowledgement**, with writes that complete at once (60 nodes, seeds 7 to 16, the
  median of the seeds):
  - the payload's offers draw 61 % fewer asks (222 ids over three payloads against 572);
  - a 50 Mbps builder uploads 2.07 copies of the message instead of 2.50, and a 1 Gbps builder
    5.9 instead of 10.0;
  - the medians move by −8 to 0 ms.

  So most of those bytes are saved where the transport takes the batch at once, and none need saving
  where it keeps §4.11's rule: there the offers wait behind the pushes either way (40 asks against
  45).
- **A column's offers wait for the acknowledgement too** (above). A fast proposer pays for it: its
  block completes 44 ms later at 60 nodes (seeds 7 to 16) and 9 ms later at 500 (seeds 7 to 9) than
  with its offers at publish.
  - A fast proposer can take it back by offering at publish (`SOURCE_OFFERS`, above). With the
    offers keyed on the configured uplink, as striping is, its block completed 6 ms sooner at 60
    nodes than in the document before (−9 to +4); at 500 nodes the cost is 9 ms. The order of a
    source's queue is §4.12's.

### 4.8 The heartbeat

```python
def on_heartbeat():
    ihave_frames.clear(); ihave_asked.clear()                 # §4.3's limits start again, and the
    for a in held_back.values(): retry_offer(a)               #   retry runs for what they held back,
    held_back.clear()                                         #   which they do not count
    drop_stale_waits()                                        # protocol.md §4.2: copies and ties past their window
    ids = gossip_history.gossip_ids()                         # stock: ids of the last 3 heartbeats
    for T in joined_types(): keep_floor(T)                    # §4.1, links for the floor per family
    for T in joined_types(): maintain_relations(T)            # §4.1
    for T in sampled_types(): keep_coverage(T)                # §4.1, the coverage floor   [D12]
    eligible = [q for q in joined_peers() if not related(q) and gossip_eligible(q)]   # stock: scores
    n = min(len(eligible), max(D_LAZY, floor(GOSSIP_FACTOR * len(eligible))))
    for q in sample_without_replacement(eligible, n):
        if PACED: pace_queue.append((q, ids, now))            # [c15]
        else: send_gossip(q, ids)

def send_gossip(q, ids):                                       # [c7] offers, per group
    for g, bits in group_bits(ids):
        if type_of_group(g).params.ANNOUNCE_EXTRA == SAMPLE:   # [D5] ALL_JOINED offered at forward time already
            announce(q, g, bits)                               # minus pushed[q], minus peer_has[q] (§4.4)
```

Per heartbeat, as v0.3 §6.4: §4.3's IHAVE limits start again and what they held back is retried,
TTLs expire, the links for the floor per family, the relations and a sampler's coverage floor are
maintained, and heartbeat gossip goes out: offers of the last three heartbeats' chunks, less what
each peer holds, was pushed or lies outside its interest (`announce`), to a sample of the joined
peers outside the node's relations that stock scoring admits, one peer per pace tick with card 15
(`on_pace_tick` unchanged) and all at once without it. It offers only groups of a type whose
`ANNOUNCE_EXTRA` is `SAMPLE` (`send_gossip`): a type at `ALL_JOINED` is offered at forward time
instead, and one at `NONE` not beyond its relations `[D5]`. The window of v0.3 §7.1 is per node
across every group of every object type (X3).

### 4.9 The window's projection, per object type

```python
def projected(p, g):                                           # [c12] v0.3 §7.1, read per object type
    T, h = type_of_group(g), hdr[g]
    if T.threshold(h) == T.index_count(h): return False         # no code: every index is needed, nothing is projected
    has, sent = peer_has[p][g].bits, sent_to[p][g]
    return popcount(has) + FAN_IN * popcount(sent & ~has) >= T.threshold(h)
```

**Projection applies to types with a code only.** Card 12 drops a push, never an answer, to a peer
that is projected to reach K from what it holds and what is on its way, on the premise that any K
chunks complete a coded group. For a group whose K equals its N, as a column's, `projected` is
false: every index is needed, and nothing is projected.

#### Rationale

**Why only with a code.** A column has no code across its cells (K = N), so the premise fails: a
dropped cell is a cell the peer still needs, and in a thin family nobody else may be pushing it.
Executing the custody setting (§6.2) found this: with v0.3's `projected` a custodian ended short of
exactly the cells its pushers had projected away, and nobody offered them, since a planned push is
not announced.

### 4.10 A sampler pulls

```python
def sample(g, bits):                                   # at block arrival: the application's draw, never narrowed to
    if expired(g): return                              #   what our links serve; ours from now on (§1.5), unless
    interest[g] |= bits                                #   the group is past its lifetime (v0.3 §8.1)
    for i in bits: ask_sample(g, i, first=True)        # the first phase: every sample at once, one peer each

def ask_sample(g, i, first=False):                     # one sample to one peer, never one asked for another
    T, b = type_of_group(g), block_of(g)               #   sample of the block (I6): a link that serves it, else
                                                       #   a routed request through another (§4.5, route_want)
    if mine[g].has(i) or expired(g): return
    if not first and samples_in_flight[b] >= T.params.SAMPLE_OUTSTANDING:
        return held_samples[b].append((g, i))          # LiteDAS's cap: asked when a second-phase ask ends
    fresh = [q for q in links(T) if q not in sampled_from[b] and not parked(q, Ask(g, i))]
    direct = [q for q in fresh if serves(q, g, i) and not high_custody(q, T)]
    via = route_next(T, T.family(g), [q for q in fresh if not serves(q, g, i)
                                      and join_recv[q][T].duty == FORWARD])
    high = [q for q in fresh if serves(q, g, i) and high_custody(q, T)]
    order = [(direct, 0), (via, T.params.ROUTE_HOPS)] + ([] if first else [(high, 0)])   # high custody: the fallback
    cands, hops = next(((c, h) for c, h in order if c), (None, 0))
    if cands is None:
        if first: after(T.params.SAMPLE_RETRY, ask_sample, g, i)   # only high custody serves it: the second phase
        return                                         # nobody left to ask: missing, for the application's verdict
    q = choice(cands)
    sampled_from[b].add(q)
    if not first: samples_in_flight[b] += 1
    send(q, Want(group=g, bits=bitmap({i}), standing=True, hops=hops), urgent=False)   # no promise timer (§4.5)
    after(T.params.SAMPLE_RETRY if first else T.params.SAMPLE_RETRY2, resample, g, i, q, first)

def resample(g, i, q, first):                          # the wait ran out
    T, b = type_of_group(g), block_of(g)
    if not first: samples_in_flight[b] -= 1
    if expired(g): return                              # past its lifetime: no state is made again for it
    if not mine[g].has(i):
        park[q][g] = now + PARK_TTL                    # it held or should have held it (a first hop may have had no route)
        ask_sample(g, i)                               # the second phase: another peer, a short wait
    while held_samples[b] and samples_in_flight[b] < T.params.SAMPLE_OUTSTANDING:
        ask_sample(*held_samples[b].pop(0))
```

**A sampler's interest is `DECLARED` and its duty `NONE`** (§1.2). It learns the group ids from the
block, as everyone does, and declares each sample to one peer: a link of ordinary custody that
serves it (§1.3: a custodian of the column), or, where none is left, another link, as a routed
request; a peer of high custody only in the second phase, as the fallback.

**The declaration is a WANT and nothing else:** no JOIN names the sample, no holding of ours reaches
anyone but the sender of a chunk (the acknowledgement of §4.2), and a peer learns only the sample it
was asked for. Nor does the WANT start a promise: `SAMPLE_RETRY` and `SAMPLE_RETRY2` are the WANT's
own timers (the repair sample's WANT of §4.6 likewise). `filter_entry` starts v0.5's promise for an
ask the pull discipline makes on an offer and not for one marked `want` (§3: sent as a `Want`), but
a claim's probe, which keeps its own (§4.6). Under the alarm option the member's ask of the
claimant takes the probe's promise too (§4.6), which the option, having no code block here, starts.

**One sample per peer.** A peer is asked for at most one sample of a block, so that no peer learns
more than one of the node's samples; §8 gives the reasons, selective disclosure first.

**The WANT is standing:** the peer answers from what it holds and, for the rest, when the chunks
arrive (§4.5), so the WANT may go out at block arrival, before any cell has reached the custodian;
in the toy it does. The duplicate that a peer may still deliver after the sampler moved on is
acknowledged like any duplicate.

**A custodian bounds what one peer pulls from it per group** with `SERVE_LIMIT` (R6): the answers
it gives the peer are counted per group the asks name (`served`). Its bound is what an honest peer
may need from it (§6.3): K for a row, so at that value a peer is answered at most K asks in a row's
group; the index count for a column, so the limit alone does not keep a "sampler" from pulling from
one custodian a column it did not join. Since a cell is stored under its row and its column, a row's
cells asked through their column groups count against the columns, not the row.

**Two phases** `[D12]`. The first phase declares every sample at once, one peer each, and waits
`SAMPLE_RETRY`, a long wait: on the honest path the custodian receives the cell within it, and the
sample arrives once, one hop after the cell reached the custodian. A sample still missing then goes
to the second phase: the peer asked is parked for the group, and the sample is declared to another
peer that has not been asked for one, a link of ordinary custody that serves it while one is left, a
routed request through another link after, a peer of high custody last, each with a short wait
`SAMPLE_RETRY2`, and at most `SAMPLE_OUTSTANDING` such asks in flight per block; a slot frees when
its wait ends. A sample with no peer to declare it to in the first phase (no link of ordinary
custody not yet asked serves it, and none routes it) is not declared then, and goes to the second
phase after the same wait. The hunt ends when no link is left to ask (each has been asked for a
sample, is parked for the group, or neither serves the sample nor forwards) or the group expires, so
an unavailable block costs a bounded number of asks. Where the binding offers a fetch
from a node that is not a link (§7), the second phase may use it before a routed request, under the
same rule: one sample per node.

**Routed sample requests** `[D12]`: a sample request with a hop limit. Where no link serves a
sample, from the first phase on, the WANT goes as a routed request, `hops` set to `ROUTE_HOPS`, to a
link with duty `FORWARD` that does not serve it, the nearest to the sample's family where routing
neighbours are kept (§1.3); each node on the way answers from what it holds and passes the request
one step on (§4.5, `route_want`). The default is one forwarding step (`ROUTE_HOPS` = 1), two hops:
the first hop asks a link of its own that serves the sample. A larger limit lets the request travel
further where one step does not reach a custodian, within each forwarder's `FORWARD_LIMIT`. The cell
comes back the way the request went, each hop verifying it (level 1) as any chunk. Each node on the
way learns the sampled cell, and the custodian learns that the node before it wants it, not who
sampled it; so a node spreads its samples over different paths, one sample per first hop (one sample
per peer, above).

**The verdict** is the application's, as are the sample's size and when it decides: a sample not
arrived by then is missing, whether no peer had it or none could be reached, and the coverage floor
and the routed requests are what make the second case rare. LossyDAS's and IncrementalDAS's are the
form this section expects: a sample of `S` passes with at most `L` missing, and a failed one is
extended, never redrawn, its new samples declared as in the first phase (§4.6's `REPAIR_SAMPLE`
steps likewise). The draw is never narrowed to the columns the node's links serve. How many samples
a node takes is the application's: FullDAS's cells per slot, or PeerDAS's eight columns.

#### Rationale

**From LiteDAS.** One sample per peer is LiteDAS's ("asking each from distinct nodes"), and so are
the two phases' timing ("an initial period to handle the happy path, and a second period to handle
potential issues") and the cap on the second phase's asks in flight ("use timeouts and the number of
outstanding queries to avoid traffic explosion").

**No promise for a sampler's WANT** (decided): v0.5 starts a promise when an ask is written (its
§7.2); a sampler's WANT, as the repair sample's, has only its own timers, while a claim's probe has
the promise of §4.6.

**Routed requests, from FullDAS:** its topic routing and its query forwarding as one mechanism ("A
node can take one of it's peers according to Topic Routing, and send to it a forwardable query.
We’ll get the sample in 2 hops").

**How far one step reaches, in the toy's graphs** (500 nodes, graph only, seeds 7 to 16;
`toy/sampler_graph.py c`): a sampler's own links serve 98 % of (sampler, column) pairs at 70 links
and 58 % at 16, and a path of two hops exists for every other pair. One step to the link whose
computed custody is nearest the column left 1.8 % of all pairs unreached at 16 links where
custodians keep their floor per column, and 19 % without that floor; the second phase meets such a
miss through another first hop, the routing rules by construction (§6.3, `ROUTE_FLOOR`). Beyond one
step: without the floor, the Kademlia-style rule reached 95.9 % of the pairs within two hops and the
other 4.1 % in three. A first hop drawn at random, as here without the rules, was not measured.

**Not taken: narrowing the draw** to the columns the node's links serve. A sample drawn among what a
neighbourhood offers is a sample that neighbourhood steers, which breaks the independence the
guarantee rests on (FullDAS: "the more the block producer and its 'accomplices' knows about the
sample selection of a node, the easier it is to introduce correlation and thus fool someone").

### 4.11 The window, in bytes

```python
W_BYTES = W * CHUNK_BYTES             # v0.3's W slots of CHUNK_BYTES: the payload's capacity is unchanged  [c14, X3]
in_flight = 0                         # bytes taken: held by a writer for the chunk it is about to send, or travelling
waiters = deque()                     # peer writers waiting for room, first come first served
sent = {}                             # (peer, group, index) -> (send time, bytes)

def wake_front():                     # protocol.md §7.1's, over the window in bytes: room is free, so the first
    if in_flight >= W_BYTES: return   #   in line that can write tries again (§7.2 there)
    q = front()
    if q is not None: wake(q)

def write_waits(p):                   # protocol.md §7.1's: p's write has not completed, so the line skips p
    if p in waiters: wake_front()     #   and the first writer in line that can write tries again, if room is free

def acquire_room(p, need) -> bool:    # True: p's writer may send `need` bytes now; False: it waits in line
    global in_flight
    fits = in_flight + need <= W_BYTES or in_flight == 0          # an empty window always takes one chunk
    if fits and front() in (None, p):                            # no writer that can write is ahead of p
        if p in waiters: waiters.remove(p)                       #   (protocol.md §7.1's front, writing)
        in_flight += need
        wake_front()                                             # room remains: the next in line tries too
        return True
    if p not in waiters: waiters.append(p)                       # a writer keeps its place while it waits
    return False

def leave_line(p):                    # p's writer has nothing to send now
    if p in waiters:
        waiters.remove(p)
        wake_front()

def track_in_flight(p, f, need):      # the room now travels with chunk f
    key = (p, f.group, f.index)
    if key in sent: return free_room(need)        # a second copy still in flight: back at once
    sent[key] = (now, need)
    after(WINDOW_TIMEOUT, window_timeout, key, now)

def window_release(p, g, i):          # p holds chunk i, from anyone (§4.3)
    e = sent.pop((p, g, i), None)
    if e is not None: free_room(e[1])

def window_timeout(key, at):
    e = sent.get(key)
    if e is not None and e[0] == at:
        del sent[key]
        free_room(e[1])
        if key[1] in planned: origin_acked(key[1], key[2])    # [c3, P4] no holding came in time: released anyway (§4.7)

def free_room(need):
    global in_flight
    in_flight -= need
    wake_front()                                  # the first writer in line that can write tries again

def next_to_send(p):                  # v0.3 §7.2, with the chunk chosen before the room is taken
    q = queue[p]
    while True:
        queue_owed_relations(p)                                # JOINs, GRAFTs and PRUNEs a full queue refused, in order (§4.1)
        if owed_answers[p] and has_room(p):                    # an answer a full queue refused (v0.5 §4.1)
            enqueue(p, Entry(chunk=pop_owed_answer(p), solicited=True), urgent=False)
        if q.urgent: return with_owed(p, q.urgent.pop(0))      # HAVEs, acks, decode claims: first
        if not q.normal:
            out = with_owed(p, Entry()) if owed[p] else None   # owed offers on their own (v0.5 §7.2)
            if out: return out
            leave_line(p); return None                         # nothing to send
        k = choose(q)                                          # §4.12; chosen first: its size is what the window counts
        entry = q.normal[k]
        need = wire_size(p, entry) if entry.chunk else 0       # control takes no room
        if need and not acquire_room(p, need): return WAIT     # [c14] in line, FIFO over peers; an urgent arrival
        q.normal.pop(k)                                        #   wakes the writer, which keeps its place
        out = filter_entry(p, entry)                           # [c8, c12], and stale asks
        if need and not (out and out.chunk): free_room(need)   # the chunk did not leave: the room goes back
        if out:
            if out.chunk:
                track_in_flight(p, out.chunk, need)            # [c14] the room travels with the chunk
                if SOURCE_OFFERS == PUBLISH: origin_written(out.chunk)   # §4.7: the holding at the first write
            return with_owed(p, out)                           # owed offers ride along
```

**The window keeps about one round trip of the uplink in flight,** whatever the chunks' sizes: a
payload chunk of 12 KB takes six times the room of a cell, and `W_BYTES` is v0.3's `W` slots of
`CHUNK_BYTES`, so the payload's cells see the same capacity as before. Two things change besides the
unit. The writer chooses the entry before taking room, since the room depends on the chunk, and
control takes no room. And an empty window always admits one chunk, so a chunk larger than the
window is not stuck. `rarest` and `projected` (§4.9) are as before, and `filter_entry` is §4.6's;
`wire_size(p, entry)` is the binding's, the bytes the entry's chunk takes on the wire to `p`, with
the header a first push of a cell's group carries on the standalone binding
(`protocol-v2-bindings.md` §1.3).

**The line skips a writer mid-write,** as `protocol.md` §7.1's does. Writers wait for room first
come, first served over peers, and keep their place while they wait. A writer whose write has not
completed (`writing`, as `protocol.md` §7.3 and its helpers define it) keeps its place but not the
front: `acquire_room` admits the first waiter whose writer can write (`front`), and every window
wake goes to that one (`wake_front`, here over the window in bytes: only while room is free).
Without this, a peer that stops reading while its writer heads the line holds all free room, and the
node sends no chunk to any other peer.

**A writer in line whose control write waits wakes the next,** as `protocol.md` §7.1's does. A
writer in line may write control, which takes no room: an urgent entry, owed offers on their own, or
a control-only entry of the normal lane. It keeps its place in line. When the transport does not
take that write at once (`protocol.md` §7.3), the writer calls `write_waits` as it starts to wait,
and the window wake lets the first writer in line that can write try again, if room is free. A write
that completes at once does not call `write_waits`. A client that cannot tell when a write starts
to wait, as with a blocking write call, may call `write_waits` before a control write from the line,
once it has marked the write pending (`writing(p)` true, as from `next_to_send`'s return). That is
safe: `front` then skips the writer, and admission is unchanged: a writer takes room only while
room is free, and never ahead of a writer in line that can write. Its cost is a change of
schedule: the early call can queue an extra run for the next writer even when the write then
completes at once.

**Open: room left unused after a queue edit.** A writer takes room only if its chosen entry
fits: `in_flight + need <= W_BYTES`, or the window is empty (`acquire_room`). The first writer in
line that can write may wait with a chunk that does not fit, say 12 KB with about 3 KB free. If a
later discard (a dropped or expired group) leaves it a smaller entry that would fit, say a 2 KB
cell, the discard itself queues no run for that writer. The cell waits until another event wakes
the writer, for example an urgent entry for its peer, another writer leaving the line, or room that
a holding or a window timeout frees. Waking the front writer when a discard changes its entry is a
rule change, for a later release.

**Below the writer** (v0.9 §7.3, as written). A writer should hand a chunk to the transport only
while the connection has less than one chunk unsent. The backlog then waits in the queue, where
cancel, projection and §4.12's order act on it.
- **v0.9 §7.3 says the rest:** what the rule bounds and what it does not, what follows when it is
  not kept, how quic-go and TCP keep it, and the note for operators on the access link's queue.
- **Two chunk sizes.** Cells and payload chunks share a connection, so the rule reads either as one
  write per connection at a time or, in bytes, as less than one payload chunk unsent; either serves.
- **A timed-out copy.** A copy's room that times out (`window_timeout`) also acknowledges the chunk
  at its source (§4.7).

#### Rationale

**The window's unit (X3, decided 2026-11-13, §8).** v0.3 §7.1 counts the window in slots of
`CHUNK_BYTES` (12 000 bytes, the payload's chunk),
`W = ceil(uplink_bytes_per_s · (RTT_REF + TARGET) / CHUNK_BYTES)`. A cell is 2 096 bytes, so the
same slot count carries a sixth of the bytes per round trip: in the toy a 50 Mbps proposer of 128
column groups was held to about 10 Mbps by its own window (a 9 MB block took 9.2 s where its uplink
allows 2 s), a 1 Gbps one to about a fifth of its uplink, and a reconstructor's answer to a probe
left 450 ms late behind its burst of rebuilt cells. One window over every object type (X3) is
therefore counted in bytes here, a chunk taking its own length of it; slots per object type would be
the alternative, with the same capacity question at every boundary between types.

**The entry before the room.** v0.3 took a slot first and chose after, which also made a
control-only entry at the head of the queue wait for a chunk's slot.

**What the unit changes, in the toy** (60 nodes, one seed, `toy/README.md` for the tables): the
custody setting's block completes in 347 ms at the median and 456 ms at the tail with a 1 Gbps
proposer where the slot window gave 777 and 963, and in 2.4 s with a 50 Mbps proposer where it gave
9.2 s, which is the uplink's own bound (2.2 s with §4.12's source rule); the sampling cell's samples
arrive in 264 ms at the median where they took 750; under half the columns withheld every custodian
completes through the rows in 2.4 s where it took 2.7, with every claim verified and none re-armed,
since a reconstructor's answers no longer queue behind its rebuilt cells; and in the honest row cell
no member decodes at the third phase at all, where 37 did, because the column path is done before
the phase and the subnet's view is whole. At 500 nodes the custody block completes in 531 ms at the
median and 680 at the tail where the slot window gave 1 011 and 1 207, and the withheld block
through the rows in 2.4 and 2.5 s where it gave 2.5 and 3.0. Tier 4 moves within 15 ms and 0.04
copies (§6.1).

**Below the writer, in the toy.** The toy runs the rule as one write per connection at a time
(`--send-buffer 1`). Read in bytes instead, as less than one payload chunk unsent, it moves the
column cells by at most 36 ms at the median (seed 7).
- **Its effect,** with §4.7's rules, in the toy at 60 nodes over seeds 7 to 16 (the median of the
  seeds, and its range):
  - the 50 Mbps payload cells complete 38 to 46 ms sooner, on 29 of their 30 seeds, with 0.10 to
    0.36 fewer copies;
  - the rows complete 14 ms sooner (−93 to +164, sooner on six seeds), and the rows with liars
    47 ms sooner (sooner on six seeds). With a column's offers at publish (§4.7's alternative) the
    rule brought them 110 and 90 ms sooner;
  - a 50 Mbps proposer's custody block completes 48 ms later (−36 to +63, later on eight seeds), and
    34 ms later at the tail;
  - the 1 Gbps cells move by at most 4 ms;
  - at 500 nodes, the payload completes 18 ms sooner with 0.31 fewer copies (seed 7), and the rows
    2 ms sooner (1 to 21, seeds 7 to 9, sooner on every seed).

**The line skips a writer mid-write** (2026-11-20, from `protocol.md` v0.10.7's §7.1).
- *The case.* The line admitted only its first writer, and every freed room woke only it. A writer
  whose write has not completed cannot take room, so a peer that stops reading while its writer
  heads the line held every free byte. On 2026-11-20 `toy/line_stall_known.py --doc v2` showed it on
  the `push` cell's network: with the source's line head stalled, nine other peers' chunks waited in
  an empty window and none was sent for two seconds. With the rule none was held up. The check now
  counts the sends from 600 ms after the stall on (past `WINDOW_TIMEOUT`), or accepts queues left
  empty.
- *The wake when a control write waits* (since `protocol.md` v0.10.9's §7.1). A burst of urgent
  entries woke writers in line that each blocked on its write, and free room went to nobody.
  `protocol.md`'s monitor (its W2) found this in `loss-thin`. So a writer in line whose control
  write does not complete at once wakes the first writer in line that can write, as it starts to
  wait (`write_waits`), as `protocol.md`'s does. Here control has a third path, a control-only entry
  of the normal lane, which takes no room and reaches the lane's head when a writer's queued chunks
  are discarded (a dropped or expired group). The wake acts at the write, whatever the entry, so it
  covers that path with the other two. A client whose write call blocks may call `write_waits`
  before a control write from the line instead, once it has marked the write pending. The early call
  can queue an extra run even for a write that completes at once. Admission is unchanged: a writer
  takes room only while room is free, and never ahead of a writer in line that can write.
  `toy/write_wait_known.py --doc v2` checks four cases on each of the three paths, with p the writer
  that writes control and q the other writer in line: q is not woken before p's write, q is woken
  once the write waits, and q is not woken when p is not in line or when the window is full. Where p
  is in line, it keeps its place at the head. `protocol.md` has no such third path: its
  control-only entry goes through `release_unused_slot`, which gives back the writer's slot and
  also takes the writer out of the line when it holds none, so there a control-only entry is never
  written from the line.
  `wake_front` is this document's own, since its room is counted in bytes (`W_BYTES`), where
  `protocol.md`'s counts slots.
- *Replaced: the wake before the write* (v0.10.7's). It woke the next writer in line before every
  control write of a writer in line, whether or not the write then waited. A write that completes at
  once leaves its writer able to write, and waking another then would change the schedule of the
  node's writers where nothing else changes.
- *The recorded cells* (`golden-v2.txt`, against v0.10.6's). Twelve move in their digest only:
  `push`, `hold`, `announce`, `none`, `withholders`, `silent`, `cap-wait`, `dcb20`, `rr-stripe`,
  `without-a`, `ihave-limits` and `push-deep`. Two move in their numbers too: `loss-thin` (p50 807
  to 814 ms, p99 922 to 894 ms, copies 1.64 to 1.65) and `late-block` (p99 727 to 718 ms).
  `without-b` is the same. The figures in this document measured before 2026-11-20 ran without the
  rule. With the wake at the wait (v0.10.9), `rr-stripe` and `push-deep` move in their digest only,
  back to their values before v0.10.7. Every other cell kept its recorded digest, `loss-thin` and
  `late-block` among them: there the wake moved within the same writer event. The wake before the
  write could reorder writers' runs that fell at the same time, and their frames to different peers.

### 4.12 Which entry goes next

```python
def choose(q) -> int:                 # the normal entry the writer sends next (§4.11)
    if q.normal[0].chunk is None: return 0                     # control at the head goes at once: it takes no room
    own = [k for k, e in enumerate(q.normal) if own_chunk(e)]
    if own: return pick(q, own)                                # [X3] a source's own chunks first, over the whole queue
    if ANSWERS_FIRST:                                          # an option, off in every setting (below)
        asked = [k for k, e in enumerate(q.normal) if e.solicited]
        if asked: return pick(q, asked)                        # answers before pushes
    return rarest(q) if RAREST else 0                          # [c9] v0.3: chunks up to the first control-only entry

def own_chunk(e) -> bool:             # a push of a chunk this node held before any peer: it is the group's source (§1.6)
    f = e.chunk
    return (f is not None and not e.solicited
            and not received[f.group].has(f.index) and not rebuilt[f.group].has(f.index))

def pick(q, ks) -> int:               # [c9] the rarest of these entries, the earliest on a tie; without card 9 the earliest
    if not RAREST: return ks[0]
    return min(ks, key=lambda k: (len(holders[q.normal[k].chunk.group][q.normal[k].chunk.index]), k))
```

**A source's own chunks go first.** After the urgent entries (§4.11) and a control-only entry at the
head of the normal queue, the writer chooses among the pushes of the node's own chunks, those it
held before any peer (`own_chunk`), over the whole queue, past offers and answers: the rarest with
card 9, the earliest without it.

**Answers before pushes** (`ANSWERS_FIRST`, an option, off). With the option the writer sends queued
answers, chosen as above, after the node's own chunks and before any other push. The option is the
one to try where answers wait behind long runs of pushes.

#### Rationale

**A source's own chunks first** (decided 2026-11-14, §8, under X3's window in bytes over every
group). v0.3's rarest-first (card 9) reorders only the chunks ahead of the first control-only entry,
and its source queues each group's offers after that group's pushes (v0.3 §5.1). With one group the
offers follow every push, and rarest-first sees them all. A proposer publishes a block's 128 column
groups at one instant, one group after another, so the first group's offers sit in every peer's
queue ahead of the other groups' pushes. Rarest-first then sees one group's chunks at a time, the
offers leave early and draw asks, and the answers and the second copies take the proposer's window
from its first copies.

**Measured in the toy.** At three seeds and 60 nodes with a 50 Mbps proposer, the custody
block completes 247 ms sooner at the median and 430 ms sooner at the tail, every seed
sooner. At seed 7 the proposer's last first copy leaves 0.3 s sooner, it sends 1 992 second copies
where it sent 2 400 and answers 518 asks where it answered 1 212, and over both blocks it sends 15 %
fewer chunks, since more of its queued pushes are dropped by a holding while they wait (card 8).
Elsewhere the rule changes nothing that the seeds can tell apart. Every single-group cell (tier 4,
variant C, the twelve check cells) runs exactly as under v0.3's order, at 60 nodes and at 500. At 60
nodes so does every cell with a 1 Gbps proposer, except the honest row cell, whose tail is 22 ms
sooner while its median moves by between 8 ms sooner and 42 ms later. At 500 nodes, over three
seeds, the 1 Gbps proposer's custody and sampling cells move within 5 ms at the median and between
5 ms sooner and 17 ms later at the tail, and its withheld row cell runs exactly as before.

**Not taken:** v0.3's order, and two other cures for the same cause, which lose in the toy.
Dropping the source's offers, or queueing them after all of the block's pushes, matches the gain
with a slow proposer but costs 7 to 355 ms at the median with a fast one, whose offers let
custodians pull from it while its uplink has room.

**Answers first, as an option.** An answer is a chunk its receiver asked for, so it is never a
guess, and the asker's clock runs: for a pull on an offer, after the ask window it may ask another
holder, and a promise still open `PROMISE` after the ask's write parks us for the group (§4.13); a
sampler's WANT has its own timers (§4.10). A push has no clock. Under v0.3's order an asked chunk is
rarely the rarest, since a peer of ours holds it, so its answer waits behind fresh pushes.

**Answers first, in the toy.** Checked at three seeds against the source-first rule with the option
off, completion barely moves: within 5 ms at the median in most tier 4 cells, 39 ms sooner in the
honest row cell, and 12 ms later in the thin lossy cell (`loss-thin`) on every seed. The asks' round
trip at the 99th percentile is shorter in most cells, by up to 44 ms, and a few hundredths of a copy
are saved. With cards 8, 9, 12 and 15 off, a node's answers waited 1.1 to 1.7 s at the 99th
percentile, and at most 0.22 s with the option. Not taken: three other forms; checked against v0.3's
order, they lose. The oldest answer first, before a source's own chunks too, costs a 50 Mbps
proposer 315 ms at the median. An answer's writer ahead of the window's line of writers costs
`loss-thin` 91 ms at the median. An answer first only once it has waited 100 ms costs `loss-thin`
12 ms and the 50 Mbps proposer 61 ms.

### 4.13 The ask window follows the uplink

```python
def ask_scale() -> float:
    """1 at ASK_UPLINK and above; ASK_UPLINK / UPLINK below it (5 at 10 Mbps)."""
    return max(1.0, ASK_UPLINK / UPLINK)


IWANT_WINDOW = IWANT_WINDOW * ask_scale()      # 200 ms at 50 Mbps and above, 1 s at 10 Mbps
```

**The ask window stretches as the uplink falls.** v0.3 puts two clocks on an ask (§6.1 there): at
`IWANT_WINDOW` (200 ms) plus `RETRY_SLACK` after the ask, its retry asks an announcer, an untried
one first, if the chunk is still missing, under the retry's checks (`retry_offer`); and the ask's promise, from its
write, parks the asked peer for the group if it is still open after `PROMISE` (400 ms). Here the ask
window stretches in proportion as the node's own uplink falls below `ASK_UPLINK`, and stays as v0.3
set it above it. The promise does not change.
- **Whose uplink:** the asker's own, the one figure a node is configured with (card 14 sizes its
  window from it, card 17 its push degree). The asked peer's link is not known; a home node asking a
  datacenter peer waits longer than it needs to before moving on, which costs time only when that
  peer does not answer.
- **The floor** is v0.3's value: at 50 Mbps and above the protocol is v0.3's, event for event.
- **The promise stays at 400 ms**, so a peer that does not answer is still parked as soon as in
  v0.3, and the asker moves on from it later only by the window. A slow honest peer can now be
  parked before the asker has moved on from it (the promise is shorter than the window below
  25 Mbps). A promise per peer that follows its observed answer times is permitted as local policy
  (§8).

#### Rationale

**Why the window follows the uplink.** v0.3's two clocks are fixed. Both were set where answers come
back within a round trip or two, at 50 Mbps. On a thinner link an answer waits longer behind the
answerer's queue, the window runs out before it arrives, the second ask's answer competes with the
first for the same thin uplinks, and both arrive: the bytes stop falling with the bandwidth and the
tail grows.

**The promise's length** (decided 2026-11-13, §8). Stretching the promise with the window too was
checked and rejected: with 30 % withholders at 10 Mbps it lengthened the tail by 18.5 % at the
median of three paired seeds in the research harness, since withholders then went unparked for the
whole payload. Under the rule as it stands (the window stretched, the promise at 400 ms), the toy's
count of parked pairs stayed below v0.3's on clean, withholding and mixed networks, since fewer asks
go out, but rose by about 60 % with 10 % of chunks lost (lost answers break promises).

**Evidence** (the research harness of the posts), against v0.3's fixed window on the same seed: at
10 Mbps per node, over ten paired seeds, every seed faster and leaner, the tail 5.1 % shorter at the
median (2.2 to 8.4 %) and 0.20 fewer copies (0.15 to 0.23); at 25 Mbps, over ten, fewer copies in
every seed but only 0.03, and the tail unchanged within the seeds' spread (0.8 % shorter at the
median, from 2.4 % shorter to 3.3 % longer); with 30 % withholders at 10 Mbps, over three, the tail
3.5 % shorter and 0.18 fewer copies. The toy's checks (mixed network, silent peers, loss): §6.3,
`ASK_UPLINK`.

## 5. What carries over from v0.3 unchanged

| v0.3 | here | note |
|---|---|---|
| §1 the payload, the code, the commitment | the payload object type's `verify`, `decode`, `header_of` | the leaf rule unchanged in this version; a fraud proof would change it (`[D6]`, §8) |
| §3 the three levels | level 1 = `T.verify`, level 2 = `T.decode`, level 3 = the application | per object type (I7) |
| §4.1 `respond` | called from §4's `on_frame` | asks ride on the first answer; an answer a full queue refuses is owed (v0.5) |
| §4.2 `defer`, `tie`, `on_block_installed`, the bounded store | §4.2 | the gate is the type's (`authenticable`; `defer` here waits for it, and `on_header_validated` releases a block's cells and their ties); a copy that waits, kept or refused, and another copy of one that waits, tie their senders to the root they name (v0.8), no longer an offer (v0.5); v0.10's bounds on what waits in this document's own `defer`, `fill` (`drop_beyond`), `on_heartbeat` (`drop_stale_waits`) and `on_header_validated` (an index the group has not, `tie_slot`), since 2026-11-16; a second id for a received index only acknowledged, as there, on each axis (`on_validated`, since 2026-11-19) |
| §3 level 1's slot check (v0.10) | §1's table, `verify` of each type | a payload copy's slot is its block's (`validate_chunk`), a cell's its header's (since 2026-11-16) |
| §4.4 an IHAVE's bitmap held to a HAVE's limits (v0.10) | §4.3 `on_offer` | an offer's bitmap, ignored and counted beyond them (since 2026-11-16) |
| §4.4 gossipsub's IHAVE limits (v0.7): `over_ihave_limits`, `ihave_frames`, `ihave_asked`, `held_back` | §4 `on_frame`, §4.3 `on_offer`, §4.8 | counted per offer-bearing frame and per ask in reply to offers, per peer over every object type; what they hold back is retried at the next heartbeat (since 2026-10-27) |
| §4.6 `drop_group` | §4.6 | plus evidence `[D6]`; a later chunk is not forwarded or offered on the dropped axis, where the draft did (§4.4 `on_validated`, `forward`; since 2026-11-18) |
| §5.1 batch order, striping, the paced source HAVE [P4] | §4.7 | candidates filtered by interest; P4 per group, its claims with the bitmap; v0.7's single offer (since 2026-11-04); a pull-only type's source pushes nothing and offers every chunk at publish (`offer_at_publish`, since 2026-11-18); any source may offer at publish, its own choice (`SOURCE_OFFERS`, since 2026-11-18) |
| §5.3 `choose_push`, `guard_fails`, `note_push` | §4.4, §4.7 | candidates come from the relation |
| §5.4 `on_mesh_join` (v0.8) | §4.1 `join_push` | at a GRAFT the node accepts into a push relation, the relation's colour, and at the yes to its own GRAFT, a round trip after v0.8's (§4.1); on gossipsub's wires at its own GRAFT, as v0.8 |
| §6.1 `may_ask`, `retry_offer`, `promise_due`, `parked`, the offer table | from §4.3's `on_offer` | offers from any link; `IWANT([a])` read as a WANT, a pull on an offer (not `want`, §3); start delay `[D8]`; `IWANT_WINDOW` scaled by the node's uplink (§4.13); v0.5's offers kept per connection and group (`add_offer`, `announcers`) and its last resort when every announcer is parked (`last_resort`, `ask_parked`); v0.8's ties and no second ask of a peer while one is outstanding (`tied_to_root`, `outstanding`; §4.2 here), and the asks that go with an announcer's dropped offers (`drop_offer`, 2026-10-28) |
| v0.5 §5.2, §7.2 `owe`, `unpush`, `with_owed` | §4.4 to §4.7, §4.11 | a push or an offer a full queue refuses, or a push the writer skips by projection, can be owed (`owe`, `unpush`), and what is still owed rides the next write to the peer, less what that write's filter drops; `unpush` is §4.7's, where a source also owes a peer of its pool as it stands then; `mesh` in it reads as the peers of the push relation |
| §6.2 `gated` | `on_offer`, `filter_entry` | per interest |
| §6.4 `on_pace_tick` | §4.8 | |
| §7.2 `filter_entry`, `rarest` | `send`, `enqueue`; §4.12 | `rarest` unchanged; the writer takes a source's own chunks first (§4.12); `filter_entry` is this document's (§4.6): v0.5's promise starts when an ask on an offer is written; an ask sent as a `Want` (`want`, §3), a sampler's, a routed request's or the repair sample's, starts none (§4.10), but a claim's probe starts one (§4.6), and under the alarm option the member's ask of the claimant too |
| §7.1 the window, §7.2 `next_to_send` | §4.11 | one window per node over every object type, counted in bytes; the entry is chosen before the room is taken; JOINs, GRAFTs and PRUNEs a full queue refused are queued first, in order (§4.1); the line skips a writer mid-write, and a writer in line whose control write does not complete at once wakes the first writer in line that can write as it starts to wait, if room is free, as v0.3's do (`front`, `write_waits`; `wake_front` this document's own, in bytes; since 2026-11-20, the wake at the wait since v0.10.9) |
| §7.1 `projected` | §4.9 | reads the type's K; off for a type without a code |
| §8.2 limits | §6.3 | plus relations and groups per slot |

**The versions carried.** Each later version of `protocol.md` comes in the same way. Its changes to
functions this document does not redefine apply as written, and those to functions it does are
carried into them, with the date each was carried where it came later than the version.
- v0.4 (2026-10-13): its one change of behaviour, the source's HAVE paced by its sends [P4],
  since 2026-10-21 (§4.2 `send_have`, §4.7 `publish`, §4.11 `next_to_send`).
- v0.5 (2026-10-21, the fixes from a model check of v0.4): §4.3 `on_offer`, §4.4 `forward` and
  `announce`, §4.5 `serve_standing`, §4.6 `decode_group` and the repair, §4.7 `publish`, §4.11
  `next_to_send`.
- v0.6 (2026-10-21) released this document's draft and changed nothing in `protocol.md`. v0.6.1
  changed only its §9.
- v0.7 (2026-10-25):
  - The live window and the group's key apply as written; §6.1 gives how the cells moved.
  - Gossipsub's IHAVE limits are carried since 2026-10-27 (§4 `on_frame`, §4.3 `on_offer`,
    §4.8).
  - Its single offer at the source (`protocol.md` §5.1) is carried since 2026-11-04 (§4.7
    `publish`): a chunk is offered only to the peers of its pool not chosen to be pushed it, so a
    push its queue refused, owed already, is not offered a second time.
- v0.8 (2026-10-26):
  - A peer that joins the mesh is announced what the node holds: §4.1's `join_push`, at a GRAFT
    the node accepts and, since 2026-11-04, at the yes to its own (§4.1).
  - Ties, and the cells released at the header (§4.2).
  - No second ask of a peer at once (§4.3).
  - A rebuilt chunk names its sources' block (§4.6).
  - Since 2026-10-28: an ask goes with its announcer's offers (§4.2), and relabelled copies are
    open (§4.6).
- v0.9 (2026-11-10):
  - The source's holding grows at a chunk's acknowledgement, not at its write (§4.3 `on_holding`,
    §4.7 `origin_acked`, §4.11 `window_timeout` and `next_to_send`), at `SOURCE_OFFERS = ACK`, the
    default since 2026-11-18 (§4.7).
  - Its offers wait for the acknowledgement too, at `ACK`, for every object type a source pushes; a
    pull-only type's source pushes nothing and offers every chunk at publish (§4.7).
  - What the transport below the writer should hold, and the note for operators (its §7.3), apply
    as written (§4.11).
- v0.10 (2026-11-15):
  - The toy's default transport keeps `protocol.md` §7.3's rule, one entry at a time per
    connection, and both recordings were made again (§0's "Numbers", §6.1).
  - What waits for a gate is carried where this document uses `protocol.md`'s functions: `tie`,
    with `tie_room`'s limits, the limit of unknown groups and the slot it records (`tie_slot`);
    `close_promises`, now code, from `fill` and `tie`; and `on_block_installed`, which drops at
    installation a tied index the group, known by then, does not have, and whose level 1 for the
    payload is `validate_chunk` with its new check of the copy's slot (`protocol.md` §3, §4.2).
  - The announcers beyond a chunk's ordered list are tried in the node's own order, in
    `protocol.md`'s ask path, which this document keeps (`protocol.md` §6.1).
  - Carried since 2026-11-16 where this document has functions of its own (§4.2, §4.3, §4.8,
    §1's table):
    - its `defer` ignores a copy beyond its sender's limit of unknown groups, as `protocol.md`'s
      does;
    - its `on_heartbeat` calls `drop_stale_waits`, so what waits for a gate that never opens goes
      at the live window's edge or the group's expiry;
    - its `fill` calls `drop_beyond` when it opens a group, so offers, asks and ties of an index
      beyond the group's count go;
    - its `on_offer` holds an offer's bitmap to a holding's limits, as `protocol.md`'s `on_ihave`
      holds an IHAVE's;
    - its `on_header_validated` drops a tied index a cell group, known by then, does not have, and
      removes a sender's `tie_slot` with its last tie under the root, as `on_block_installed` does;
    - a cell's level 1 rejects a copy whose slot is not its header's, as `validate_chunk` does for
      the payload against its block (decided 2026-11-16).
- v0.10.1 (2026-11-15) and v0.10.2 (2026-11-16): `protocol.md`'s prose and comments rewritten,
  its code the same, and the toy's tables made faster, the recorded cells' digests the same;
  nothing to carry.
- v0.10.3 (2026-11-18): `protocol.md`'s constants in three kinds, reference values for
  gossipsub's two IHAVE limits, "frame" for what a peer writes on its stream, the source's HAVE
  said as "acknowledged", and the source's choice of when it announces (`SOURCE_OFFERS`). This
  draft carries them all: the rename (`on_frame`, `frame`, `ihave_frames`), §6.3's bounds in §8.3's
  kinds, the IHAVE values (§4.3, §6.3), "acknowledged" (§4.7), and `SOURCE_OFFERS` (§4.7, §6.3).
- v0.10.4 (2026-11-18): `protocol.md` says what heartbeat gossip tells of the source, names a chunk
  that is never acknowledged as open, and keeps an IDONTWANT entry that is not a HAVE bitmap as
  stock gossipsub keeps an id (`on_frame`); the toy follows the documents at a dropped group and in
  its reading of bitmaps and ids. This draft runs on the same toy. It carries the IDONTWANT rule
  onto v0.3's wire (`protocol-v2-bindings.md` §3), where the toy now keeps such an entry in
  `unwanted[p]`. §4.7 already says that, for a type that gossips (`ANNOUNCE_EXTRA = SAMPLE`), the
  source's heartbeat gossip draws on every chunk at either setting, and its open item on a chunk
  that is never acknowledged is the one `protocol.md` §5.1 names.
- v0.10.5 (2026-11-19): `protocol.md` is the same but for its version line, and the proofs in
  `formal/veil/` move to Veil's release. The toy's `accepted` answers whether the id was stored, as
  `protocol.md`'s helper list says, so under this draft a later copy of a copy that level 1 rejected
  no longer passes the probe (R5), and a repeat of a copy under a second id, seen and not stored, is
  not acknowledged (§4.2). This draft runs on the same toy; nothing else to carry.
- v0.10.6 (2026-11-19): `protocol.md` names an open question in §1, whether the protocol fixes a
  coded group's compressed bytes ("Open: the compressed bytes"); this draft points to it from §1.1's
  `decode` row, and leaves where the descriptor travels open, as `protocol.md` §1 does.
- v0.10.7 (2026-11-20): `protocol.md`'s window line (§7.1, §7.2): a free slot goes to the first
  writer in line that can write, and a writer in line that writes control first wakes another that
  can write. This draft carries both into its window in bytes (§4.11), with its own `wake_front`
  over `W_BYTES`, and wakes on a third path it has, a control-only entry of the normal lane;
  `line_stall_known.py --doc v2` shows the first.
- v0.10.8 (2026-11-21): `protocol.md` is the same but for its version line, and the Lean twin's
  record and a first piece of a refinement come into `formal/`; nothing to carry.
- v0.10.9 (2026-11-21): `protocol.md`'s wake in the window's line moves to the moment a writer
  starts to wait for its transport (§7.1, §7.2). In this draft, `write_waits` wakes the first writer
  in line that can write if the waiting writer is in line and the window has room (§4.11). It
  replaces the wake before the write on the three control paths, and `wake_front` loses `past`;
  `write_wait_known.py --doc v2` checks it on all three.

## 6. Settings

### 6.1 v0.3 as a setting

| notion here | in v0.3 |
|---|---|
| object type | the payload only; one family |
| JOIN | subscription to the payload's topic: interest `ALL`, duty `FORWARD`, `M = 1` |
| push relation | the mesh: `SYMMETRIC` (`direction = BOTH`), `F_LO = 6`, `F_HI = 12`, `D_OUT = 8`; `PRUNE_BACKOFF` the client's (gossipsub's backoff) |
| announce relation | the mesh, plus `ANNOUNCE_EXTRA = SAMPLE` (heartbeat gossip to `max(D_LAZY, GOSSIP_FACTOR · n)` non-mesh peers, paced) |
| suppression scope | the mesh |
| holding / offer | IDONTWANT with a `HaveBitmap` / IHAVE with a `HaveBitmap` |
| WANT | IWANT with a `WantIndex`, one index at a time |
| claims | `claim_all` = the decode claim (all N bits); `complete` = the same, since interest is all |
| repair | `(everyone, at once, the mesh peers)` |
| `START_DELAY`, `SERVE_LIMIT` | 0, unbounded (the stock per-id limit remains) |
| evidence | none |
| wire | v0.3 §2's magic strings (`protocol-v2-bindings.md` §3) |

**Three differences in the rules, which no recorded cell exercises.**
- *A source with an empty mesh.* A source with no mesh peer for the payload offers its chunks to its
  links whose interest holds them, and owes them a refused push (§4.7, `source_pool`); below
  `STRIPE_UPLINK` it also pushes to them, as a column's source does with no relation in the family.
  `protocol.md`'s source offers to its mesh only and, below `STRIPE_UPLINK`, pushes to it only: with
  an empty mesh it offers nothing at publish, a slower one makes no push, and its chunks enter its
  heartbeat gossip. This document keeps the fallback for every object type, since a source never
  waits for links (§4.7). No recorded cell has a source with an empty mesh.
- *More ids for a rebuilt index.* At an index held only as rebuilt, both documents forward the first
  copy that arrives under an id the node has not seen. `protocol.md` stores it, so a copy under yet
  another id is a second copy of a received index, only acknowledged; here `fill` stores none of
  them, so each such copy enters forwarding (`forward`, where the choice of peers still applies).
  A repeat of a seen id at such an index is acknowledged where that id was stored (`accepted`):
  there, the id of the first network copy, which `protocol.md` stores over the rebuilt one; here,
  the rebuilt chunk's own id, since `fill` stores none. Where the two ids are the same, both
  acknowledge it; where they differ, each acknowledges its own and ignores the other. No recorded
  cell has two ids for one index.
- *An IHAVE entry by id.* On v0.3's wire this document takes offers as bitmaps only
  (`protocol-v2-bindings.md` §3), where `protocol.md` records a valid structured id in an IHAVE as
  an offer, which can draw an ask under its §4.4's checks. No recorded cell names an id in an IHAVE.

The differences the recorded cells do show are in the scheduling (§4.11 to §4.13), which moves
times and copies by the amounts the Rationale measures.

**The regression.** The toy's fifteen cells are the regression for this setting, recorded for this
document in `toy/golden-v2.txt` (`toy/check.py --doc v2`) and compared against v0.3's own recording
with `toy/check.py --doc v2 --golden golden.txt`. Since 2026-10-27 a thirteenth cell,
`ihave-limits`, sets stock gossipsub's two IHAVE limits (10 offer-bearing frames and 5000 asks;
§4.3). The other cells set none. Since 2026-11-15 two more: `late-block`, where 18 of the 60 nodes
install each block 400 ms after its publish (`protocol.md` §4.2's deferral and ties; this document
runs its own `defer`), and `push-deep`, the `push` cell with the earlier transport
(`--send-buffer 0`), whose line is the `push` cell's before the transport changed.

#### Rationale

**The distance to the recordings, by date.**
- Checked on 2026-10-07: with v0.3's window (slots of one payload chunk) eleven of the twelve cells
  reproduced v0.3's completion times and bytes exactly and `rr-stripe` differed by 3 ms at the
  median, the residue being the order of same-instant sends (this document iterates the relation in
  peer order where v0.3 iterated the mesh set). With the window in bytes (§4.11) the cells move by
  at most 7 ms at the median, 15 ms at the tail and 0.04 copies either way (`announce`
  p99 576 → 587 ms, `without-a` 578 → 565 ms, `loss-thin` 984 → 999 ms, `push` copies 2.41 → 2.43),
  which is the two structural changes of §4.11 and not the unit: a control-only entry at the head of
  a queue no longer waits for a chunk's slot, and the chunk is chosen before the room is taken. So
  this document contains v0.3 to within those amounts, and with v0.3's window exactly but for
  `rr-stripe`'s 3 ms.
- Since v0.4's P4 came in (2026-10-21, §4.7) the comparison is with v0.4's recording (`golden.txt`):
  eleven cells within 3 ms at the median, 16 ms at the tail and 0.03 copies (`announce`
  p99 568 → 584 ms, `rr-stripe` 521 → 505 ms), and `loss-thin`, at a 20 Mbps uplink, 8 ms later at
  the median and 0.10 copies lighter, the one cell where §4.13's scaled ask window applies; without
  P4 the medians had been up to 102 ms behind v0.4's (`silent` 678 against 576 ms).
- With v0.5 merged (2026-10-21; every cell of both recordings moves) the comparison is with v0.5's:
  eleven cells within 7 ms at the median, 15 ms at the tail and 0.03 copies (`rr-stripe`
  p50 417 → 410 ms, `dcb20` p99 358 → 343 ms, `cap-wait` 740 → 754 ms), and `loss-thin` 1 ms later
  at the median and 0.12 copies lighter, as before the merge (1.81 copies).
- With the group's key (2026-10-23, v0.3 §1; both recordings move again, as under any renaming:
  `toy/README.md`) eleven cells are within 6 ms at the median, 35 ms at the tail and 0.03 copies
  (`without-a` p99 613 → 578 ms, `cap-wait` 815 → 797 ms), and `loss-thin` is 10 ms later at the
  median and 0.11 copies lighter (1.81 copies).
- Since `protocol.md` §5.1 announces only to the mesh peers it did not choose for a chunk
  (2026-10-25), its `loss-thin` runs differently with the same medians and copies, so these
  distances stand.
- With ties and no second ask of a peer at once (2026-10-26, `protocol.md` §4.2, §6.1; both
  recordings move) eleven cells are within 8 ms at the median, 30 ms at the tail and 0.03 copies
  (`silent` p50 641 → 649 ms, `without-a` p99 598 → 568 ms), and `loss-thin` is 8 ms later at the
  median and 0.12 copies lighter (1.81 copies).
- Asks that go with their announcer's dropped offers (2026-10-28, `protocol.md` §6.1) change no
  event in any cell of either recording: nothing was tied in the toy then, and its offers expire
  only after their group has completed.
- With v0.9's rules (2026-11-10, §4.7: the source's holding and its offers at the acknowledgement;
  every cell of both recordings moves), eleven cells are within 13 ms at the median, 18 ms at the
  tail and 0.06 copies of v0.9's own recording (`cap-wait` 630 → 643 ms, `without-a`
  p99 551 → 533 ms), and `loss-thin` is 6 ms later at the median and 0.14 copies lighter (1.80
  copies).
- With the toy's transport keeping `protocol.md` §7.3's rule (2026-11-15, one entry at a time per
  connection; every cell of both recordings moves but `rr-stripe`, whose uplink has no send buffer),
  eleven cells are within 8 ms at the median, 16 ms at the tail and 0.02 copies of `protocol.md`'s
  recording (`cap-wait` 544 → 552 ms, p99 710 → 726 ms), and `loss-thin` is 18 ms later at the
  median and 0.07 copies lighter (1.64 copies).

**`ihave-limits` against `protocol.md`.**
- Under v0.9's rules and the toy's transport since 2026-11-15, this document holds back 26 667 asks
  to the next heartbeat, where `protocol.md` holds back 26 799. It is 2 ms sooner at the median and
  1 ms later at the tail, with 0.02 copies more (p50 510 against 512 ms, p99 593 against 592 ms,
  2.07 against 2.05 copies). With the earlier transport (`--send-buffer 0`) it held back 24 248
  against 24 538, 3 ms sooner at the median and 7 ms sooner at the tail (p50 541 against 544 ms,
  p99 621 against 628 ms, 2.41 against 2.40 copies).
- Before §4.3 carried the limits, it held back none and ran as without them (p50 470 ms).

**Draft 0** did not reproduce the cells at all: it filtered a forwarding node's push candidates by
what it had already pushed, which v0.3 does not, and it shuffled the relation peers for repair in a
different order than v0.3's mesh set, so its random draws diverged; draft 1 fixed both.

### 6.2 The five designs as settings

| setting | object types | `M` | interest | duty | announce extra | repair | start delay | what it tests |
|---|---|---|---|---|---|---|---|---|
| tier 4 | payload | 1 | ALL | FORWARD | SAMPLE | everyone decodes at K; rebuilt chunks to relation peers short of K | 0 | the regression (§6.1) |
| variant C | payload | N | ALL | FORWARD | SAMPLE per colour | same | 0 | independent pusher sets per index on one neighbourhood; the floor |
| PeerDAS custody | column (rows kept by supernodes) | 1 | DERIVED (`cgc`) | FORWARD | ALL_JOINED | nobody decodes a column (no code); supernodes (every column) keep the rows and rebuild a row still short at the second phase's delay, PeerDAS's reconstruction delayed; rebuilt cells to the custodians lacking them | 0 | thin families, pre-seeded sources, cross-group repair, a proposer withholding half the columns |
| RowDAS | column, row | 1 | DERIVED (columns: `cgc`; rows: the node's subnet) | FORWARD | ALL_JOINED | rows not pushed (`EAGER` off); at K: row reconstructors (64 columns or more) on their subnet's row; later: supernodes on every other row at the second phase's delay, any member on its subnet's row at the third's, each with jitter; a row held on the columns waits once; rebuilt cells to the custodians lacking them; one claim defers once, verified by a probe | rows: 1 s (`[D8]`; RowDAS: a slot fraction) | cross-fill, the two claims, deferral on a claim, a proposer withholding half the columns, subnets without members |
| FullDAS sampling | column | 1 | DECLARED | NONE | none | none | 0 | interest without duty: a standing WANT per sample, retried at another link (§4.10); the custodians' serving load |

**All five run in the toy** (`toy/run.py --doc v2 --setting t4|c|custody|rows`, custody with
`--samplers` for the sampling row). Each setting is a settings file for the toy, and the invariants
the toy checks for every setting (`toy/invariants.py`) are these: every node completes its interest
given a source; nothing is pushed outside interest; upload within the duty bounds; a claim whose
probe goes unanswered is detected; one cell fills both groups; the tier 4 setting reproduces v0.3's
cells. All six are checked: the first three on every run, the claim and cross-fill ones under the
row setting, the last by `check.py --doc v2 --golden golden.txt`.

#### Rationale

**Variant C** as a setting of this document completes the toy's check cell faster in the tail and at
more bytes than the tier 4 setting, the direction the harness measured, with the toy's sizes
(`toy/README.md`).

**The custody setting** runs a block of 32 blobs as 128 column groups from one proposer to
custodians of 8 columns each, with a mesh per column on the custodians' subgraph; every custodian
completes, nothing is pushed outside interest and no node pushes a chunk above its budget, and
executing it found two things in the carried-over code: the window's line of writers stalled while
slots were free (v0.3 §7.1, fixed there, since it is v0.3's window) and card 12's projection assumes
a code (§4.9). With supernodes (`--supernodes`), custodians of every column that keep the rows and
rebuild a row still short at the second phase's delay, the custody cell whose proposer withholds
half the columns completes on all thirteen seeds, where without them 58 of 59 custodians stay short;
this is PeerDAS's reconstruction, delayed (§4.6).

**The sampling setting** runs on top of custody (`--samplers`): a share of the nodes declare eight
cells per block to one custodian each, and every reachable sample completes, a little before the
custodians' columns do, with the custodians serving a handful of chunks each to samplers; executing
it is what made the WANT a standing request (§4.5, §4.10), since a sampler's WANT reaches the
custodian before the cell does, and a pull with a promise timer would have parked every custodian it
asked.

**The row setting** runs EIP-8371's rows on top of custody: one designated subnet per node, rows
pull-only, members complete at 64, reconstructors of 64 columns decoding at K, any member later, and
a proposer that withholds half the columns, so that only the rows can fill them; at the recorded
seed every custodian completes through the rows, and on all thirteen seeds from 7 to 19 with a
custodian link per column for every member (§4.6's repair floor; without it five runs left
custodians short, each for a missing link), every cell sits in both of its groups (R4), and a liar
fault shows a false claim detected by the probe (R5). Executing it changed the document in eight
places: a chunk a node rebuilt is filled into its other groups as rebuilt and acknowledged to
nobody, and completes them (`decode_group` checks them as `on_chunk` does); repair respects `EAGER`,
so rebuilt row cells are offered to row members and pushed only into the columns; the claim in a
holding is "I hold or can produce every index", not "my interest is satisfied", since a member
complete at 64 was read as claiming 128; the probe is exempt from stop-pull and the ask window and
its promise is the deferral window; an unverified claim counts for nothing in the subnet's view, or
a liar suppresses the third phase; and "still incomplete" is read in that view, or every member
short of 128 rebuilds a row the network already has; and every member keeps a link to each column
(`REPAIR_FLOOR`), or a row is neither gathered nor repaired where no member has one. With three
supernodes the second phase completes the 32-subnet withheld cell on all thirteen seeds, a cell some
of whose subnets have no member (short at seed 7 without them), and halves the withheld cells' time;
it changed the document in two more places: a supernode keeps every row with interest declared on no
link (§1.2), and a row whole on its columns' bitmaps but not in the node's holdings waits once
before it is rebuilt (`known_across`), or a supernode still receiving its columns rebuilds rows
nobody withheld.

### 6.3 Parameters, limits and constants

| name | per | meaning | status |
|---|---|---|---|
| `M` | object type | colours of the push relation; 1 … N | `[D10]`: a parameter with no default (decided). Measured at 1 (tier 4, v0.3) and at N (variant C); 1 < M < N is open (below) |
| `F_LO`, `F_HI` | object type | in-pushers per family and colour: floor and cap (v0.3: 6, 12) | `[D10]` |
| `D_OUT`, `D_OUT_FAST`, `D_OUT_MAX` | object type | out-pushees per family and colour by uplink class (v0.3: 8; card 17's classes) | `[D10]` |
| `SYMMETRIC` | object type | one relation both ways per family and colour, grafted and pruned with `BOTH`: below `F_LO` grafted up to `D_OUT`, at `F_HI` pruned down to `D_OUT` at random (§4.1); False: in- and out-relations apart | v0.3's mesh: True (§6.1), with `F_LO ≤ D_OUT < F_HI`, since at `D_OUT = F_HI` the prune makes no room; one-way relations are an option `[D10]` |
| `PRUNE_BACKOFF` | object type | how long after a PRUNE that a node receives it does not graft that peer again for the relation the PRUNE named (§4.1) | stated by its bounds: at least a round trip, at most how long a node may stay below its floor once its candidates have refused; on gossipsub's wires gossipsub's backoff (§7) |
| `R_NODE`, `R` | node | the per-chunk push budget (v0.3: 2, 6 fast; the source's plan) | v0.3 §8.3's open item on size; for cells, open (below) |
| `ANNOUNCE_EXTRA` | object type | ALL_JOINED, SAMPLE or NONE beyond the relations | `[D5]`, decided: `ALL_JOINED` for columns and rows, as in every measurement; `NONE` permitted for columns, never for rows (§8); the payload `SAMPLE`, v0.3's heartbeat gossip (§6.1) |
| `EAGER` | object type | chunks of the type are pushed eagerly; False: holdings and offers only (rows), at the source too, which offers every chunk at publish (§4.7) | – |
| `DECODE_AT_K`, `DECODE_LATER` | object type | who decodes at K; who decodes later and when (from `known_at`), e.g. EIP-8371's phases | `[D4]`, decided: EIP-8371's phases (§4.6), the second phase's delay shorter than the third's; the second at 1 s and the third at 2 s, each with up to 0.2 s of jitter, in the toy and in the research harness |
| `REPAIR_TO` | object type | whom rebuilt chunks of a group go to (v0.3: the mesh; columns: custodians lacking them) | `[D4]`, decided: pushed to the custodians lacking them, as measured. Options measured (§4.6, "Whom rebuilt cells go to"): the cells offered, not pushed, to the nodes that keep every row, or every rebuilt cell offered |
| `REPAIR_BUDGET` | object type | each rebuilt chunk to `R_NODE` of those lacking it and offered to the rest, as its source pushes a chunk (§1.6); off: to every peer short of K, v0.3's | `[D4]`: an option, off (decided) |
| `REPAIR_FLOOR` | object type | links the rendezvous keeps, for a node that may rebuild, to custodians of each family it does not hold (the rebuilders' fanout, §4.6) | `[D4]`; decided, stated by its bound: at least 1; 1 in every measurement of the rows |
| `SOURCE_FLOOR` | object type | links a node keeps to custodians of each family it will publish, opened through the rendezvous (§4.7, the first of the source's three layers) | a parameter with no default (decided): 0 leaves the source to the hunt and the code; the toy's custody and row settings use 2, at setup |
| `DEFER_WINDOW` | object type | how long a peer's claim defers our own decode while one ask verifies it, and that ask's promise (R5) | `[D4]`, decided: 1 s, in the toy and in the research harness |
| `REPAIR_SAMPLE`, `SAMPLE_WAIT`, `REPAIR_REASK` | object type | after a verified claim, the steps `[(S1, L1), (S2, L2), …]` of a sample of the cells we lack, asked of their columns' custodians, each step extending the last and passing with at most `L_k` of `S_k` missing; the wait before each step is judged; and whether a lost cell is re-asked of another custodian, with the extension or, at the last step, in one more wait (R5) | option, off (`None`, `False`); kept as an option, on together with `REBUILT_SEEN` where a node defends against hoarding claimants; measured in §4.6 |
| `REBUILT_SEEN` | object type | a chunk the node rebuilt is marked seen, so a pushed copy of it is a duplicate and is not forwarded again (§4.6) | option, off; only with `REPAIR_SAMPLE`, never alone; measured in §4.6 |
| `ALARM_WAIT`, `ALARM_NEXT`, `ALARM_MAX` | object type | a custodian's alarm: how long after `known_at` a custodian lacking a cell of its custody asks a member of the row's subnet; how long before it asks another; and how many it asks (§4.6) | option, off; for networks without an honest supernode. The wait is stated by its bound: above the honest custodians' tail on the network. The measurements use 3.5 s, 1.5 s and 3 |
| `START_DELAY` | object type | seconds from the group id being known to the first ask | `[D8]`, decided: 1 s for rows, as in every measurement of the toy and the research harness; 0 for the payload and columns. Shorter for rows at a cost: with liars, row members are left short (§8) |
| `SERVE_LIMIT` | object type | chunks served per peer and group (R6) | stated by its bound: at least what an honest peer's interest may need from the node in the group, K for a row member (it completes at K) and the index count for a column's custodian; a sampler asks one cell per peer and block. Rows: 64 (K) in the toy and the research harness; columns: no limit in the measurements |
| `PROMISE` | node | how long an offer's promise runs before a broken one parks the peer for the group (v0.3 §6.1: 400 ms), one value for every object type in the code (`filter_entry`) | the payload's promise stays at 400 ms (§4.13); a promise per peer that follows its answer times is permitted as local policy, with 400 ms the default (§8, decided); a longer promise for cells, so one per object type, is open (below) |
| `SAMPLE_RETRY` | object type | seconds a sampler waits for its first-phase standing request before the second phase asks another peer (§4.10) | `[D12]`, stated by its bound: longer than the honest path's latest sample, the custodians' tail plus a hop; 2 s in every measurement, LiteDAS suggests 4 s; a shorter wait is open (below) |
| `SAMPLE_RETRY2`, `SAMPLE_OUTSTANDING` | object type | the second phase's wait per peer, and its asks in flight per block (§4.10, LiteDAS) | `[D12]`, stated by their bounds: the wait at least a routed request's round trip (two hops out and back), the asks in flight at least 1; 0.5 s and 4 in every measurement, no other value tried |
| `SAMPLE_COVER` | object type | links serving each family that a node keeps for a type it samples, sampling-only links closing what its other links leave short (§1.3, §4.1) | `[D12]`; 2, decided, built for diversity (`COVER_HIGH`), and at least 1 (§1.3). One cover is an option |
| `COVER_HIGH` | object type | families a peer of high custody counts for in the coverage floor (§1.3, §4.1) | `[D12]`; 1, decided, as in the measurements |
| `ROUTE_FLOOR` | object type | links a node with duty `FORWARD` keeps to custodians at the routing neighbours' distances (§1.3) | `[D12]`; an option, off |
| `ROUTE_HOPS` | object type | forwarding steps a sampler's routed request may take (§4.10) | `[D12]`; 1, decided (FullDAS's two hops), and at least 1. More is an option where one step does not reach a custodian |
| `FORWARD_LIMIT` | object type | routed requests a node passes on per peer and slot (§4.5, §4.10) | `[D12]`; X6: a bound, each node's within it (`protocol.md` §8.3's kinds), decided, stated: at least one per block whose samples an asking peer may still be hunting in the slot, since under `ROUTE_HOPS` 1 and one sample per peer a sampler routes at most one request per first hop and block |
| `EVIDENCE` | object type | the fraud-proof object, if any | `[D6]`: none in this version (decided); the hook stays |
| `ANSWERS_FIRST` | node | queued answers by rarity before pushes, after a source's own chunks (§4.12) | an option, off in every setting; a wash in three-seed toy checks |
| `SOURCE_OFFERS` | node | when a source offers each chunk to the peers of its pool (§4.7) it did not choose to push it to: `ACK`, at the chunk's acknowledgement; `PUBLISH`, at publish, its holding growing at each chunk's first write (§4.7) | a default, `ACK`, `protocol.md` §5.1's rule; `PUBLISH` is the source's own choice: sooner for a fast source, later for a slow one, and it names the source (§4.7); decided |
| groups tracked per slot | node | state for groups we hold or peers want, beyond our interest | X6: a bound, each node's within it (`protocol.md` §8.3's kinds), stated: at least the groups the chunks a node holds or rebuilds project onto (R4, §3), which for a row member or a reconstructor is up to every column of the block, for each block in its live window. The value is the client's; no limit in the measurements |
| relations per link | link | families × colours a link may carry | X6: a bound, each node's within it (`protocol.md` §8.3's kinds), stated: at least the families of the node's own interest times `M`, per object type, since an honest peer grafts a relation only for a family the other end's interest holds (`candidates`, §4.1). The value is the client's; no limit in the measurements |
| sampling-only links accepted | node | inbound links joined `(DECLARED, NONE)` that a node accepts (§1.3) | `[D12]`; X6: a bound, each node's within it (`protocol.md` §8.3's kinds), stated: high enough that the network's samplers each keep `SAMPLE_COVER` links per family they sample. The value is the client's; no limit in the measurements, and the serving load not measured |
| `ASK_UPLINK` | node | the uplink at and above which `IWANT_WINDOW` keeps v0.3's value; below it the window scales by `ASK_UPLINK / UPLINK` (§4.13); 50 Mbps | scaling by the asked peer's link is open (below) |
| `IWANT_WINDOW` | node | v0.3 §8.3's 200 ms, scaled by `ask_scale()` (§4.13) | – |
| `MERGE_HOLDINGS` | node | a holding of a group the node publishes that is still in its queue takes the newer chunks instead of a second holding (§4.2; v0.4 §5.1 allows it) | permitted: a source may merge (local policy, as v0.4 words it); the toy keeps it off so that its recorded cells stay comparable |
| `HAVE_TTL`, `PUSH_TTL`, `GROUP_TTL`, `PARK_TTL`, offers, `GUARD_GRACE`, `RTT_REF`, `TARGET`, `WINDOW_TIMEOUT`, pace tick, `GOSSIP_RETRANSMISSION` | – | v0.3 §8.3 unchanged | – |
| `MAX_IHAVE_MESSAGES`, `MAX_IHAVE_LENGTH` | node, per peer and heartbeat | gossipsub's two IHAVE limits on offers: offer-bearing frames, and asks in reply to them. Over either, asks wait for the next heartbeat (§4.3). The values are the client's (`protocol.md` §8.2); on v0.3's wire a stock gossipsub client sets 10 and 5000 (`protocol-v2-bindings.md` §3) | `protocol.md` §8.3's reference values are 4096 frames and 5000 ids per peer and heartbeat; this draft chooses no values of its own for its bindings. *Recommended* on the standalone binding: not gossipsub's 10 (below) |

**Open, for later study:**
- *`M`:* 1 < M < N.
- *`R_NODE`, `R` for cells* (to be evaluated carefully): whether cells keep the fast class's 6 or
  take `R` (2), which would make the budget per object type. Not yet evaluated: larger families (500
  nodes and more), fast nodes other than supernodes, the payload's fast class in the same network,
  the harness.
- *`PROMISE` for cells* (to be evaluated carefully): a longer promise for cells. Not yet evaluated:
  the longer promise for cells under withholding; more seeds and 500 nodes for cells; what peer
  scoring reads from a broken promise.
- *`SAMPLE_RETRY`:* a shorter wait.
- *`ASK_UPLINK`:* whether a node should scale by the asked peer's link where it knows it.
- *The IHAVE limits:* the trade of latency for copies against the other knobs that make it, the ask
  window (§4.13) first. Not yet tested: 500 nodes, seeds other than 7 outside the rows setting, or a
  peer that floods offers.

#### Rationale

**When each was decided.** On 2026-11-01: `REPAIR_SAMPLE` with its steps kept as an option,
`REBUILT_SEEN` only with it, and the alarm for networks without an honest supernode. On 2026-11-13:
`M`, `DECODE_AT_K` and `DECODE_LATER`, `REPAIR_TO`, `REPAIR_BUDGET`, `REPAIR_FLOOR`, `SOURCE_FLOOR`,
`DEFER_WINDOW`, `EVIDENCE`, and the promise per peer. On 2026-11-14: `ANNOUNCE_EXTRA`,
`START_DELAY`, and the bounds on groups tracked per slot, relations per link and sampling-only links
accepted. On 2026-11-18: `SOURCE_OFFERS`.

**`R_NODE`, `R` for cells, in the toy.** The toy's 60-node cells so far, over seeds 7 to 19:
supernodes on datacenter links, in the fast class, pushed mostly duplicates into columns of about
ten custodians (0.96 copies more per node in the honest custody cell; 0.72 copies and half a second
of tail in the honest row cell); with cells at `R` the honest row cell is back at 1.13 s at the tail
and 2.22 copies (1.14 s and 2.16 without supernodes), the withheld cells are as fast or faster at
the tail (custody 1.25 s, 16 subnets 1.64 s, 32 subnets 1.69 s, against 1.25, 1.76 and 1.83) at 0.6
to 1.2 copies fewer, and the honest custody cell gives up 31 ms at the median and 73 ms at the tail
for 1.17 copies fewer.

**`PROMISE`, in the toy.** The toy so far: in the honest row cell the 400 ms promise broke 3 321 to
4 204 times per run and parked 804 to 1 039 honest (peer, group) pairs; nearly every broken promise
was a column ask that the asked node answered later, 0.45 s after the ask at the median and 0.8 s at
the 99th percentile, behind the rows' pulls on its uplink, and none was a refusal. At 0.8 s it broke
1 to 3 times, with completion times and bytes unchanged (seeds 7 to 9), since the asker moves on
after `IWANT_WINDOW` either way and the promise decides only whom it parks. For the payload,
evaluated with §4.13 (2026-10-19): a promise stretched with the ask window on thin links lets
withholders go unparked for the payload (30 % withholders at 10 Mbps: the tail 18.5 % longer in the
research harness, three paired seeds; silent peers, who announce nothing and so are never asked,
were not hurt in the toy), so the payload's promise stays at 400 ms.

**`SAMPLE_RETRY`.** In the toy's 500-node cells the custodians' 99th percentile was 0.67 to 0.70 s.
Under 30 % withholders the samplers' median follows `SAMPLE_RETRY`'s 2 s wait: 2.5 to 2.9 s at 500
nodes.

**`SAMPLE_COVER`.** At least 1: without a floor a sampler of eight cells holds a sample no link
serves with probability 17 % at 70 links and 96 % at 16 (§1.3). In the toy's 500-node cells
(custody, seeds 7 to 16, a fifth of the nodes sampling, 2 000 sampler-blocks per network), two
covers left no sampler short, honest or under 30 % withholders, at 70 links and at 16. One cover did
as well at 70; at 16 it left 7 short under withholders and raised the honest samples' 99th
percentile to 2.2 s (0.7 s with two). For the floor of the fewest links, high custody counted in
full, in the toy's graphs (500 nodes, 8 of 128 columns a node, graph only, seeds 7 to 16, greedy
cover; `toy/sampler_graph.py a`): once, a median of 2 added links on top of 70 (0 to 5) and 13 on
top of 16 (9 to 18), 23 from none; twice, 8, 29 and 42; one link to a node custodying every column
covers all; with 10 % of nodes custodying 64 columns, 0 on top of 70 and 3 on top of 16. For the
diversity floor, covers counted by distinct links (graph only, the same graphs, 400 draws per
sampler; `toy/sampler_match.py`), the share of eight-sample draws that find eight distinct serving
links: two covers 99.77 % or more at 16 links (29 to 31 links added, median) and 99.92 % or more at
70 (8 to 9); three covers 99.99 % or more at both (47 to 49, 17 to 20), and the one that holds for
sixteen samples; one cover only 64 to 86 % at 16 and 97 % at 70.

**`COVER_HIGH`.** 0 is within 0.4 points of 1 with eight samples (1.7 with sixteen), at a link more;
counted in full, one supernode link with no other rule finds eight distinct servers for 4.7 % of
draws at 16 links.

**`ROUTE_FLOOR`.** In the same graphs, without a per-column floor at 16 links: the hypercube rule
brings every (sampler, column) pair within two hops for 17 added links per custodian, the
Kademlia-style rule 95.9 % within two and 4.1 % in three for 6.4.

**`ROUTE_HOPS` above 1** serves where one step does not reach a custodian, as the Kademlia-style
rule's 4.1 % in three hops; in a 60-node cell one request that took a second step brought its sample
at 468 ms, where it had waited for the second phase.

**`FORWARD_LIMIT`.** In the toy's 60-node cells (seed 7, two covers, routed requests on), a limit of
1 changed no event, honest or under 30 % withholders; with half the columns withheld it refused 10
of 1 048 forwards, and the same samples arrived.

**Sampling-only links accepted.** On average the bound is the samplers' added links over the nodes
that serve them: in the toy's graphs, with a fifth of 500 nodes sampling, two covers add 8 links per
sampler at 70 links and 29 at 16 (`SAMPLE_COVER`, above), about 2 and 7 per other node, and a limit
at the average would refuse some, as the draws are not even.

**`ASK_UPLINK`.** The toy, in the research harness's setting, against v0.3's fixed window, seeds 7
to 9: fewer copies in every cell, 0.16 to 0.33; the tail shorter in the all-home network at
12.5 Mbps (0.7 to 3.0 %), with 30 % silent peers (2.4 to 4.4 %), in the mixed-bandwidth network at
6 Mbps with a home builder (3.1 to 3.2 %) and with a datacenter builder (3.0 to 3.6 %), and within
±1.6 % with 30 % withholders; with 10 % of chunks lost it is up to 3.2 % longer (a lost answer is
waited for until the longer window closes).

**`MERGE_HOLDINGS`.** The toy, seeds 7 to 16 (§4.7): for a 50 Mbps proposer of 128 column groups it
takes back 10 of P4's 116 ms at the custody block's median with writes that complete at once, 16 of
80 ms with one write per connection at a time; copies unchanged.

**The IHAVE limits.** A low message limit trades latency for copies. Offers come chunk by chunk, so
it holds back many asks. An ask held back is likely often never made, because by the heartbeat the
chunk has come by push: a duplicate pull saved (not counted). In the toy's `ihave-limits` cell (60
nodes, one seed, under v0.9's rules; `toy/run.py --doc v2 --ihave-limits M,5000`), against no limit
(p50 461 ms, 2.49 copies): 10 frames cost 80 ms at the median and save 0.08 copies, 20 cost 31 ms
and save 0.11, 40 cost 3 ms and save 0.01, and 100 change neither. The 5000 asks never bound. On the
standalone binding, not gossipsub's 10, since in that cell 20 saves more copies for under half the
delay. On v0.3's wire, batching a peer's offers into fewer frames avoids the delay, and with it the
saving. At `protocol.md` §8.3's reference values (4096 frames, 5000 ids, per peer and heartbeat): no
ask held back in the toy's 60-node cells under the tier 4 setting, variant C and custody (with and
without samplers), each run as with no limit; the busiest peer reached 248 frames and 58 asks in a
heartbeat. Under the rows setting (60 nodes, seeds 7 to 9, with and without half the columns
withheld), no ask held back either, each run as with no limit; the busiest peer reached 1 254 frames
and 178 asks. What the limits protect is mostly bounded already: one ask per index at a time (v0.3
§6.1), asks only for groups an installed block commits (§4.2), and the offer table's limits
(`protocol.md` §8.2).

## 7. Bindings `[D1]`

The protocol is defined on its own messages (§2). A **binding** carries them between two nodes. The
bindings, their bytes and the rules that hold on one binding only are in
[`protocol-v2-bindings.md`](protocol-v2-bindings.md). It has three:
- the standalone binding, on a stream of its own or in Waggle's framing;
- gossipsub with the Partial Messages Extension;
- v0.3's wire.

A node may speak more than one, and negotiates per link which one a peer takes. This section says what
every binding provides, and what the rules do where a binding lacks a capability.

**What every binding provides:**
- *Links:* a link per connected peer, with its open and its close, which start and end §3's
  per-connection lifetimes.
- *Whole messages, in order:* what a node writes to a peer arrives as whole messages, in the order
  written for each object type at least (Waggle's framing has a stream per type). How a binding marks
  where each ends is its own: its frames.
- *The queue and the write:*
  - `send(p, msg, urgent)` puts a message into the per-peer queue (§3), or reports that a full queue
    refused it;
  - the writer chooses the next entry when it writes (§4.12);
  - a write completes as §4.11's "Below the writer" says.
- *Limits before state:* a bound on each message kind's size, checked before the receiver holds any
  state for the message (X6), after the binding's own bound on its frame.
- *The header:* a cell group's header reaches a peer before or with its first cell of the group (§2).
  A binding validates a block's cell header no later than it installs the block (§4.2). It validates a
  header a chunk carries apart from the chunk, before the chunk is handled. A copy whose id is already
  seen or waiting still brings its header (`on_header_validated`), and a header that fails never marks
  the chunk's id as seen, so an honest copy of the chunk is still taken.
- *The fork:* a link carries an object type only where both ends run it at the same fork, since a
  type's header and limits change at forks.
- *A chunk's id and size:* `chunk_id(f)`, and `wire_size(p, entry)`, the bytes its write to `p` will
  take, a header included (§3).

Rendezvous and discovery are outside the bindings (§0).

**The capabilities the bindings differ in**, and what the rules do without each:

| capability | standalone | extension | v0.3's wire | without it |
|---|---|---|---|---|
| interest without subscription: a JOIN per link, `DECLARED` interest told only to the peers asked (§1.2) | yes | for a sampler only | for a sampler only | a sampler subscribes to nothing, its WANTs are its interest, and their answers are admitted by their WANT (`protocol-v2-bindings.md` §4) |
| relations per family and colour, with a direction and a floor per colour (§1.3, §4.1) | yes | `BOTH` only, a colour field, no floor per colour | stock: `BOTH`, one colour | the relation is the topic's mesh |
| the answered GRAFT, and `PRUNE_BACKOFF` this document's (§4.1) | yes | no: accepted in silence, gossipsub's backoff | no (the toy runs it under `--upkeep on`) | a GRAFT's sender is in the relation from its GRAFT, and the ends' agreement rests on the backoff after a PRUNE (§4.1) |
| a holding's claims; the WANT's `standing`, `hops` and `probe` (§2) | yes | in extension fields | beside the bitmap or the index | – (every binding carries them) |
| EVIDENCE (§2) | its kind reserved | a full message on the rendezvous topic | no | none in this version (`[D6]`) |
| a frame of one message, or several (§4's `on_frame`) | one | several (gossipsub's frame) | several | the handling order of one frame is §4's; where a frame holds one message, the IHAVE limits (§4.3) count messages, and one answer per id per frame (§4.5) is one per message |
| merging queued entries (`merge_waiting`, §4.2, permitted; §4.1's one GRAFT or PRUNE of a relation per frame) | the client's | the client's | the client's | – (a choice, not a capability) |
| how a cell's header travels (§2) | with the first eager push of its group on a link | the partial columns' own rule | beside the chunk, charged nothing in the toy | – |
| an urgent lane at the transport, beside the writer's (§4.12) | for later study (a second stream) | no | no | the writer's urgent lane alone, as one stream per peer gives |
| scoring on these messages (P7) | yes | gossipsub's | gossipsub's | gossipsub's scoring of its own messages |

**Where the gains are.** The standalone binding is where X2's gains are had: interest without
subscription, a push relation per family and colour with a floor and a direction, and scoring on
these messages. The extension binding gives up the first two, but for a sampler's interest, and
keeps the rollout inside existing topics; it is the binding for columns while the extension is the
deployed path. A mixed network needs a bridge between a binding and the stock path that does not
double the bytes; it is outside this version (`[D1]`, §8).

**A fetch outside the links** `[D12]` (possible, binding-dependent). A binding may offer one
capability beyond its links: fetching a sample quickly from a node of the known node set, a node
whose custody the sampler computes from its node id, that is not a link.
- *What it gives:* it reaches a custodian directly where §4.10 would route. That is one hop instead of
  two, nothing disclosed to a forwarder, and fewer links kept for the coverage floor, which matters
  most where a node's connection budget is small (at 16 links the floor of the fewest links costs 13
  more, §6.3).
- *What the protocol needs:* only the notion of such a fetch, a WANT answered by a CHUNK from a node
  that is not a link, and its privacy rule: one sample per node, as on links (§4.10). The serving
  limit and the second phase's cap apply as on a link.
- *How it is carried* is the binding's (`protocol-v2-bindings.md` §5), so the protocol's rules do not
  depend on it.

## 8. Decisions, and where they bite

| decision | where in this document |
|---|---|
| `[D1]` identity and bindings (decided: a protocol of its own, carried by three bindings, in their own document since 2026-11-17; a bridge to the stock path is outside this version) | §7, `protocol-v2-bindings.md`; §0's "what is assumed" |
| `[D2]` two bitmaps, WANT per recipient, no need bitmap (decided, as written) | §2 `Want`, `on_want`, `wants_from_me` |
| `[D3]` two claims (decided, as written) | §2 `Have`, §1.5, §4.6 |
| `[D4]` repair's parameters (decided: EIP-8371's phases, rebuilt cells pushed to the custodians lacking them, `DEFER_WINDOW` 1 s, `REPAIR_BUDGET` an option, off; the repair floor at least one link to a custodian of each column) | `TypeParams.DECODE_AT_K`, `DECODE_LATER`, `REPAIR_TO`, `DEFER_WINDOW`; §6.3's `REPAIR_SAMPLE`, `REBUILT_SEEN`, `ALARM_WAIT`; §4.6 `check_completion`, `reconsider`, `push_rebuilt` |
| `[D5]` the announce relation's width (decided: `ALL_JOINED` for columns and rows; `NONE` permitted for columns, never for rows) | `TypeParams.ANNOUNCE_EXTRA`, §4.4 `announce_extra`, §4.8 `send_gossip` |
| `[D6]` the payload's consistency route (decided: none in this version; the `EVIDENCE` hook stays) | `TypeParams.EVIDENCE`, §4.6 `decode_group`, the payload's leaf rule in §1.1's table |
| `[D7]` groups per column and per row, cross-fill (decided, as written) | `ObjectType.project`, `family`, §4.2 `on_validated`, §4.4 `forward` |
| `[D8]` the row pull delay (decided: 1 s; shorter at a cost under liars) | `TypeParams.START_DELAY`, §4.3 `on_offer` |
| `[D9]` one document or a sibling (decided: a sibling) | this file; §6.1 is the merge path |
| `[D10]` colours (decided: a parameter, with no default) | `TypeParams.M`, `F_LO`, `F_HI`, `D_OUT`, `SYMMETRIC`, §1.4, §4.1 |
| `[D11]` join = (interest, duty); topics as rendezvous (decided: the join as written; the rendezvous gossipsub topics per family, with the ENR beside them) | §2 `Join`, §1.2, `protocol-v2-bindings.md` §0's rendezvous row |
| `[D12]` a sampler's reach (decided: a coverage floor with `SAMPLE_COVER` set at 2, LiteDAS's second phase, routed sample requests of one step) | §1.3; §2 `Want`; §4.1 `keep_coverage`; §4.5 `route_want`; §4.10; `TypeParams.SAMPLE_RETRY2`, `SAMPLE_OUTSTANDING`, `SAMPLE_COVER`, `COVER_HIGH`, `ROUTE_HOPS`, `FORWARD_LIMIT`; §6.3's `ROUTE_FLOOR`; §7's last paragraph |
| the promise's length (§4.13) (decided: 400 ms the default; the per-peer promise permitted as local policy) | v0.3 §6.1's `PROMISE`; §6.3's `PROMISE` row |
| a source's links in a family it does not custody (decided: it never waits for links; three layers on top of its fanout; a refused push to a fallback link owed) | §4.7 `source_pool`, `candidates_for_source`, `origin_acked`, `unpush`; §6.3's `SOURCE_FLOOR` row |
| the probe of a claim (R5) (decided: the claimant judged by its own copy; the probe marked and answered whatever the asker holds, once per asker and group; the asker's queue keeps it; its cell drawn at random) | §2 `Want.probe`; §4.2 `on_chunk`, `fill`; §4.5 `on_want`; §4.6 `reconsider`, `defer_on_claim`, `settle_probe`, `probe_answer`, `probe_promise`, `probe_waits`, `probe_of_claim`, `serve_probe`, `filter_entry`; `protocol-v2-bindings.md` §0's WANT row |

**Decided on 2026-11-13.** Six of the decisions above were chosen, each with what was not taken:
- **`[D1]` identity and bindings.** v2 is a protocol of its own, defined on its own messages and
  carried by three bindings, defined in their own document (`protocol-v2-bindings.md`, since
  2026-11-17): the standalone one, the binding onto gossipsub's Partial Messages Extension, and v0.3's
  wire. §7 states what every binding provides and the capabilities each gives up. Not taken: the
  extension alone, which gives up interest without subscription and the push relation's floor and
  direction (§7);
  and deciding after a paired cell of the signalling cost on both wires, which neither
  implementation here can run, since neither speaks the extension's wire. A bridge between a
  binding and the stock path, which a mixed network needs, is a deployment question no measurement
  here settles; it is outside this version.
- **`[D4]` the repair floor.** A node that may rebuild keeps at least `REPAIR_FLOOR` links, at
  least 1, to custodians of each column it does not custody (§4.6). Without it, five of thirteen
  runs of the toy's withheld row cell left custodians short, each by a missing link; with 1, all
  thirteen completed. Not taken: opening a link only when a rebuilt cell has nowhere to go (§4.6),
  kept as an option.
- **`[D6]` the payload's consistency route.** None in this version: the payload's consistency is
  left to level 2 and the application, and `EVIDENCE` stays a hook that an object type may fill.
  Not taken here, each needing work outside this document: a fraud proof over the current code,
  which changes the leaf rule and needs a condition on the consensus side, and stays the route that
  changes neither the code nor the commitment scheme; the payload in blobs, a change to the bid;
  and a layout in two dimensions.
- **`[D9]` one document or a sibling.** A sibling. `protocol.md` is the published and measured
  protocol, and this document contains it as one setting (§6.1), which is the merge path if one
  document is ever wanted. The cost is that each version of `protocol.md` is carried in here (§5).
  Not taken: one document, whose case is that the payload and the general rules are the same code;
  folding `protocol.md` into these notions would rewrite text without changing behaviour.
- **`[D10]` colours.** `M` is a parameter with no default. It is measured at 1 (tier 4, v0.3) and
  at N (variant C); 1 < M < N is for later study, which needs colour negotiation and a floor per
  colour in the toy first. Not taken: a measured default before release.
- **`[D11]` the rendezvous.** Gossipsub topics per family, in every binding, with the ENR beside
  them. This keeps the stock path, and a network that mixes it with the bindings. Not taken: the
  ENR alone, an option the standalone binding could run.

The others were confirmed as the toy runs them, and the research harness's Go build where named.
Nothing measured argues against them.
- **`[D2]`:** two bitmaps, the WANT per recipient, and no bitmap for need (§2), as the RowDAS
  design has it. `[D12]` added the WANT's `standing` and `hops`.
- **`[D3]`:** the two claims, `claim_all` and `complete` (§2, §1.5). They are unverified, and a
  claim not followed by the chunks it implies counts against the claimant.
- **`[D4]`, the rest of repair's parameters:**
  - who decodes and when, EIP-8371's phases;
  - rebuilt cells pushed to the custodians lacking them;
  - `DEFER_WINDOW` 1 s;
  - `REPAIR_BUDGET` an option, off.

  Their values are §6.3's, the same in both implementations.
- **`[D7]`:** groups per column and per row, with a rebuilt chunk filling its other groups
  (`project`, `cross`, R4).
- **`[D11]`, the join:** a JOIN per link and object type, carrying interest and duty (§2, §4.1).

**The promise's length.** §4.13 stretches the ask window on thin links and keeps the promise at
400 ms, so a peer that does not answer is parked as in v0.3, and a slow honest peer can be parked
too before the asker has moved on. The option is a promise per peer that follows the times its
answers took: `max(PROMISE, srtt + 4 · rttvar)`, smoothed as TCP's retransmission timer (RFC 6298),
a peer that never answered keeping the floor. In the toy, in the research harness's setting at
12.5 Mbps (seeds 7 to 9): with the same completion times and bytes as §4.13's form, it parked 283
to 360 honest (peer, group) pairs per run instead of 503 to 642 (v0.3: 584 to 702), and parked the
withholders of a 30 % withholding network as before. What it buys is the honest peers' standing
(and whatever scoring reads from broken promises), not time; it needs per-peer state and a sample
on every answered ask. Not measured in the harness. A promise stretched with the window, the
other form, is rejected (§4.13).
- **Decided on 2026-11-13:** 400 ms stays the default, and the per-peer promise is permitted as
  local policy, as `MERGE_HOLDINGS` is. The promise is the asker's own timer: it changes whom the
  asker parks, and so whom it asks next, not what either end means.
- **Not taken:** the per-peer promise as the default, which would first want the research harness
  at ten seeds.

**A source's links in a family it does not custody** (decided 2026-11-13, §4.7). A source never
waits for links: it publishes at once to the links it has, and with no relation in a family for a
chunk's colour its fanout uses its links whose interest holds the chunk, and a push to one of them
that a full queue refuses is owed, as to a relation peer (decided 2026-11-14). Three layers keep its
chunks moving on top: links kept to custodians of each family it will publish (`SOURCE_FLOOR`, a
parameter with no default), a hunt through the binding when a chunk has nowhere to go, and the code
as the backstop. In the toy the fallback never yields a peer, since its proposer has a relation with
every custodian it links to, and the hunt is not measured. Not taken: holding the publish until the
links are there, which would delay every family for one that the code can recover; and for a refused
push, an offer at the chunk's acknowledgement, which, when every copy was refused, waits for a
holding that names the chunk or a later copy's timeout.

**The window's unit** (X3, decided 2026-11-13): bytes, as §4.11 runs it, a chunk taking its own
length of the window. The column cells gain in the toy (one seed, §4.11): at 500 nodes the custody
block completes in 531 ms at the median and 680 at the tail, against 1 011 and 1 207 with slots.
Tier 4 moves within 15 ms (§4.11). Not taken: v0.3's slots of `CHUNK_BYTES`, and slots per object
type, which leave the same capacity question at every boundary between types (§4.11).

**Decided on 2026-11-14.** Two decisions after their runs, and §4.12's rule. The runs are toy
checks (`toy/run.py --doc v2`, the flags `--col-announce`, `--row-announce` and `--row-delay`),
each setting read against the value every earlier measurement ran, paired by seed. A value is
*close* if it leaves no more nodes short, and none on a seed where the other left none, and moves
the custodians' median and 99th percentile, and in the row settings a row member's 64th cell, by
at most +20 ms at the median over the seeds.
- **`[D5]` the announce relation's width.** `ALL_JOINED` for columns and rows, as every measurement
  ran it. `NONE`, offers to the relations only, is permitted for columns, never for rows.
  - *At 60 nodes* (seeds 7 to 16), the columns' `NONE` is close in custody at 50 Mbps and with a
    1 Gbps proposer, in custody and in rows with half the columns withheld, and in the honest rows.
    It sends 19 to 30 % fewer offers, and 0.00 to 0.06 fewer copies. With a fifth of the nodes
    lying about their row holdings (`claim20`) it is not close: on one seed a custodian is short in
    two blocks, where with `ALL_JOINED` one was short in one, and on another a row member is short
    where none was.
  - *At 500 nodes* (seeds 7 to 9, two blocks): close in custody, with 7 % fewer offers and 0.03
    fewer copies of 1.81; close in rows with half the columns withheld and a 1 Gbps proposer, with
    28 % fewer offers and 0.15 fewer copies of 2.3. With liars it is close only by the letter
    without withheld columns (the custodians' median +19 ms on the middle seed, +31 on another),
    and not close with half withheld (+40 ms); no node short in either. Three seeds show a pass or
    a fail, not a comparison, and do not show the 60-node shortfall gone.
  - *The rows' `NONE`* left row members short on every seed in every row setting: the rows need
    the offers to every joined peer.
  - *The columns' `SAMPLE`* (the heartbeat's paced gossip) was close where `NONE` was but in the
    500-node rows with half withheld (the custodians' 99th percentile +26 ms on the middle seed).
    The rows' `SAMPLE` runs as `NONE`, since a cell is published under its column and the
    heartbeat offers it there.
  - Not taken: `NONE` as the columns' default. Its saving is mostly control; its failures are under
    liars, where the offers beyond the relation are the fallback; and its passes at 500 nodes rest
    on three seeds.
- **`[D8]` the row pull delay.** 1 s, as every measurement of the toy and the research harness ran
  it: a secondary axis waits for the column path (R7). In the toy at 60 nodes (seeds 7 to 16; honest
  rows, rows with a fifth of the nodes lying about their row holdings, rows with half the columns
  withheld), 2 s costs the column path: the custodians complete 147 to 386 ms later at the median.
  - *It can be shorter, at a cost.* 0.5 s and 0 s keep the custodians within 10 ms at the median.
    0.5 s brings a row member's 64th cell 24 to 80 ms sooner at the median. But with liars both
    leave row members short on every seed: 154 at 0.5 s and 219 at 0 s over the ten seeds, counted
    once per block they are short in, against one at 1 s; 0 s also leaves a custodian short in one block more.
    Without liars neither leaves any short. Why was not traced.
  - Not taken: 2 s, which fails R7; and a delay under 1 s as the default.
- **A source's own chunks go first** (§4.12), under X3's window in bytes. In the toy, with a 50 Mbps
  proposer, at 60 nodes over three seeds, the custody block completes 247 ms sooner at the median
  and 430 ms sooner at the tail; single-group cells run as under v0.3's order. Not taken: v0.3's
  order, and dropping the source's offers or queueing them after the block's pushes, which cost a
  fast proposer 7 to 355 ms at the median.

**The probe of a claim** (R5, decided 2026-11-15, §4.6). The probe judges the claimant by its own
copy of the probed cell only, an answer or a push. Three rules make that fair to an honest claimant
and hard to meet for a dishonest one: the probe's WANT is marked (`probe`, §2), and the claimant
answers it whatever the asker's holdings say, once per asker and group, the exemption taken by the
answer and spent when it is written; the asker's queue keeps its marked WANT while the probe waits;
and the probed cell is drawn at random among those the member lacks. In the toy's rows (60 nodes,
three blocks, `--send-buffer 0`), over five cells and three seeds, no honest or hoarding claimant
failed its probe (none of 1 281 verdicts with the rules as they stand, none of 1 298 with those of
2026-11-16; before them, 3 of 1 289 failed without the mark and the kept WANT), and liars passed 1,
0 and 65 times in the three liar cells. Since 2026-11-16, the probe's wait starts at its write, a probe not written when the duty
next fires gets no verdict unless the claimant's own copy came first, and is not written later, a
claimant still decoding keeps the first probe per asker and group and answers it once when the cell
is stored, and a claimant that leaves before the verdict gets none; without a verdict, the member's
own repair is reconsidered at the duty's own time, at once if that has passed; and once the probe
is settled, a promise under its key is a plain ask's, which any copy closes. Not taken: any peer's
copy passing the claimant, which let liars pass whenever another peer brought the cell (at least 57,
115 and 558 times in the same cells, measured before 2026-11-16); hiding the probed cell from the
claimant in the asker's holdings while the probe waits, which changes what a node announces and
cannot hide a cell already named before the probe; and the lowest lacked index, which a claimant can
read from the member's holdings. The random index's purpose, against a claimant that keeps only the
cell it expects to be asked, is not measured: the toy's liars do not aim. The standalone binding
carries `standing` and `probe` in one `Bitvector[8]`, its other bits zero when sent and ignored when
received, so that a later flag fits without breaking older readers (`protocol-v2-bindings.md` §1.3).
Not taken there: a byte of
its own for the mark, which every WANT would pay, and a message of its own for the probe, which
every binding would have to carry.

**The repair's options** `[D4]` (decided 2026-11-01). The repair sample and rebuilt cells marked
seen stay options. They are on together where a node defends against hoarding claimants, and the
second is never on alone (§4.6). The custodian's alarm stays an option for networks without an
honest supernode.

**Dropped: biasing the repair sample** toward the columns the member check cannot vouch for, those
that no member of the row's subnet custodies, by drawing half of each step's new cells from them.
- *What the node knows.* It knows only the members it is linked to. From those, 38 to 50 of the
  about 60 cells a member lacks look uncovered, so the bias barely narrows the draw.
- *The odds.* In a network model of the toy's 500-node rows, seed 11's hoarders repair the members'
  cells and leave 5 columns unrepaired. The chance that every honest member of the subnet passes,
  so that the row stays short, is 0.52 with the uniform sample and 0.38 with the bias over linked
  members. It is 0.06 only with every member known, a view the node does not have.
- *Where hoarders mark their rebuilt cells seen,* the uniform sample already catches them: below
  0.001 in the model. Beside that option, three seeds showed nothing from the bias.

**A sampler's reach** `[D12]`, decided (2026-11-03). The steady state is a coverage floor built
for diversity (§1.3). Its size is `SAMPLE_COVER`, a parameter of the object type with a bound of at
least 1, set at two links per family; `COVER_HIGH` is set at 1 (§6.3). Routed sample requests
take what the floor misses, one forwarding step by default (§4.10, `ROUTE_HOPS` 1). Both run on
LiteDAS's two phases: one sample per peer, with peers of high custody as the second phase's
fallback. The standing WANT carries the first phase (§2, §4.5), and `FORWARD_LIMIT` and
`SERVE_LIMIT` are limits stated by their bounds (§6.3). The evidence is the toy's graphs, its
60-node cells and its 500-node cells at ten seeds (§6.3). Kept as options: one cover
(`SAMPLE_COVER` 1), more than one forwarding step, the routing neighbours (`ROUTE_FLOOR`), and the
fetch outside the links (§7). For later study:
- *Why diversity, not the fewest links.* Three reasons. One node that holds a sampler's whole
  sample can release exactly those cells to it: Al-Bassam, Sonnino and Buterin's selective share
  disclosure ("If a block producer selectively releases shares as light clients ask for them, up to
  (k + 1)² shares, they can violate the soundness property", their §5.4), defeated only where "the
  network would not be able to link different per-share sample requests to the same clients".
  Custody counts are self-declared, so a node that claims every column would attract every
  sampler's floor and samples. And the load would concentrate on the nodes of high custody. In the
  toy's honest 60-node cell before this rule (floor and routed requests, degree 30, seed 7), the
  proposer, which holds every column, was asked for 28 of 288 samples, up to 5 of one sampler's 8
  in a block, where no other peer was asked for more than 2; with it, for none, and no peer for
  more than one.
- *The floor's size* (decided: `SAMPLE_COVER` set at 2, a parameter of the object type). On the
  toy's graphs, eight samples find eight distinct serving links in 99.77 % or more of draws with
  two covers, against 64 to 86 % at 16 links and 97 % at 70 with one (§6.3). In the toy's 500-node
  cells (seeds 7 to 16, 2 000 sampler-blocks per network), two covers confirmed every sampler in
  every block, honest and under 30 % withholders, at 70 links and at 16. One cover did as well at
  70 links. At 16 it cost the honest tail (the samples' 99th percentile 2.2 s against 0.7 s), and
  under withholders 7 sampler-blocks did not confirm. Two covers add 8 links on top of 70 and 29 on
  top of 16; one cover adds 2 and 13. Three covers (99.99 %, and the floor that holds for sixteen
  samples) would add 17 to 20 and 47 to 49. How many sampling-only links a custodian accepts is a
  bound, each node's within it (§6.3); the serving load they bring it is not measured.
- *The floor's lifetime.* Kept across slots, chosen from custody alone; whether and how often it
  rotates, and what churn costs it (not measured).
- *The route and its privacy.* Without routing neighbours a first hop is any link with duty
  `FORWARD`. Where custodians keep a floor per column of their own (§1.4, as PeerDAS's subnet
  peering), one step on random links left 1.8 % of (sampler, column) pairs unreached at 16 links in
  the toy's graphs, and 0.05 % at 70; without such a floor, 19 % at 16 links (§4.10). The routing
  rules (§1.3, `ROUTE_FLOOR`) are for networks without it; the Kademlia-style rule is the cheaper,
  and its 4.1 % of pairs at three hops is the case for `ROUTE_HOPS` above one. A first hop drawn at
  random is not measured. What a forwarder learns, one sample of one sampler, is measured nowhere
  yet, nor is a forwarder colluding with the proposer, nor the time a routed sample takes.
- *The hunt's cost.* A sample nobody holds is asked of one fresh peer after another until none is
  left, each peer at most once per block, so the asks per block are bounded by the node's links.
  With half the columns withheld (60 nodes, degree 30, seed 7): 1.3 to 1.7 asks per sample without
  routed requests, 3.0 with them and 4.2 to 5.2 with the floor of one or two covers as well, 380 to
  704 requests passed on over two blocks (11 to 12 asks per sample, 1 813 to 2 042 passed on, before
  one sample per peer). A
  bound on the first hops a sample tries, or the application's deadline ending the hunt, is open.
- *The cost of one sample per peer.* Under 30 % withholders (the toy, the floor with routed
  requests, one cover, seed 8), every sample still arrived, at a median of 2.7 to 3.7 s and a 99th
  percentile up to 7.7 s, against 2.2 to 2.7 s and 4.9 s when a peer could be asked again: the
  second phase must find a fresh peer each time.
- *Small networks.* The floor covers only the families some node other than a source custodies;
  in the toy's 60-node cells seven of 128 columns had no custodian but the proposer, and routed
  requests reached it for them.
- *Rows as a second axis.* A row member holds a cell of its row once it has it, and serves it to
  anyone who asks; `serves` counts columns only. In the toy's graphs at 70 links
  (`toy/sampler_graph.py e`), counting half rows (the draft's members stop at 64 of 128) takes the
  samplers left with a sample no link serves from 17 % to 7.5 % with 32 row subnets and to 13.5 %
  with 128; whole rows (FullDAS's two-dimensional code), to 3.2 % and 11.0 %. At 16 links rows
  barely help.
- *LiteDAS's slot start.* A group id names the block, so a WANT waits for the block's header; a
  request keyed by slot would let it go at slot start, as LiteDAS's does. Not proposed.
- *LiteDAS's extensions.* A holdings list in the reply, and a NACK by which a custodian that lacks
  the cell asks the sampler to pass it on once it has it (feeding custody): not proposed.
- *Outside the links.* A fetch from a node of the known node set that is not a link (§7), over an
  ephemeral libp2p connection, plain UDP, a fast QUIC connection or discv5: the binding's.
- *Rejected:* narrowing the sample to what the node's links serve (§4.10).
