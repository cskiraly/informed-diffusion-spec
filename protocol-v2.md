# SEACAST's next version (draft): the protocol on its own notions

> **DRAFT.** Open decisions in §8; checked in the toy only; no client or full simulation runs
> it; not model-checked.

*SEACAST: Segmented, Encoded, Availability-sampled broadCAST (the E could also read Elastic). The
name since 2026-10-19; v0.4 was published as Informed Diffusion, which now names SEACAST's diffusion
part (§0, "The parts").*

*Draft 1, 2026-10-07. A sibling of [`protocol.md`](protocol.md) (draft v0.3 when this was
written, v0.4 since 2026-10-13, with the same section numbers; "v0.3" below means that document),
which it contains as one setting (§6.1). v0.4's one change of behaviour, the source's HAVE paced by
its sends [P4], is carried here since 2026-10-21 in this document's own versions of the functions
it touches (§4.2 `send_have`, §4.7 `publish`, §4.11 `next_to_send`). v0.5 (2026-10-21, the
fixes from a model check of v0.4) comes in the same way: its changes to functions this document
does not redefine apply as written, and those to functions it does are carried into them (§4.3
`on_offer`, §4.4 `forward` and `announce`, §4.5 `serve_standing`, §4.6 `decode_group` and the
repair, §4.7 `publish`, §4.11 `next_to_send`; §5 lists the rest). This draft defines the
notions, the messages, the state and the event handlers; the scheduling that tier 4 measured
carries over unchanged where §5 says so. Every open design
decision is marked `[D1]` … `[D11]`, and §8 lists where each bites. The toy runs this document on
top of v0.3's (`toy/run.py --doc v2`): v0.3's blocks are loaded first, this document's after them,
and the tier 4 setting is checked against `protocol.md`'s recorded cells (v0.5's since
2026-10-21). Draft 0 (2026-10-06) was written without running; draft 1 is what executing it
changed.*

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
pusher set, suppression, announcements and pulls, is defined here, and §7 says how the result is
carried on gossipsub's wire where that is the deployed path. v0.3's code is assumed where §5 says
a function carries over: this document redefines what changes and names what it keeps.

**What is normative.** Sections 1 to 3, the notions, the messages and the state, are what both ends
of a link must agree on. Section 4 combines each node's local scheduling with the meaning of the
messages: what a holding, an offer, an ask, a claim and an acknowledgement promise. A client may
schedule differently without breaking interoperability, provided those meanings hold. Section 5
names the v0.3 scheduling that carries over, section 6 the settings, section 7 the bindings and
section 8 the open decisions.

**The parts.** SEACAST has six parts, named for what they do. Three carry message semantics both ends
must share; two are local policy, which a client may change while the meanings hold; the last says
how the messages travel. Named mechanisms inside a part keep their own names.

| part | what it does | sections | mechanisms inside |
|---|---|---|---|
| joins and relations | declares interest and duty per link; keeps the push and announce relations per family and colour, with their directions and floors | §1.2–1.4, §4.1 | coloured push relations |
| Informed Diffusion | pushes chunks into interest, tells holdings and offers, answers and makes asks | §1.5, §4.2–4.5, §4.10 | standing sample requests (§4.10) |
| completion and repair | the claims, completion per interest, decoding at K, rebuilt chunks, deferral, the probe, evidence | §1.5, §4.6 | |
| informed scheduling *(local)* | what a node sends next and when: the window in bytes, the projection, the next entry, pacing, the ask window | §4.9, §4.11–4.13 | the byte window |
| source distribution *(local)* | how a source releases a group: batch order, striping, the cap, its paced holding; any node holding chunks first is a source (§1.6) | §4.7 | striped publishing |
| wire bindings | how the messages travel: standalone, on gossipsub's Partial Messages Extension, or on v0.3's wire | §7 | |

The heartbeat (§4.8) drives three of them: relation upkeep, announcement gossip and pacing. Outside the
parts, and assumed above: the object type's interface (§1.1: indices, verification, decoding,
projection across groups) and peer discovery, with the connectivity that repair's floor asks of it
(§4.6, `REPAIR_FLOOR`). *Colour* partitions a group's indices; it is not a subnet. *Family* is the key
of a relation, not necessarily a custody group.

**Conventions.** Python-like pseudocode in the style of the consensus specs, as in v0.3; a comment
`# [c8]` marks a card of the posts (`protocol.md`'s introduction lists the cards and the posts),
`# [D5]` an open decision. State and helpers keep v0.3's names
wherever the object is the same (`peer_has`, `pushed`, `holders`, `mine`, `received`); the header
of a group is v0.3's `desc`, read here as `hdr`. New helpers are listed in §3.

**Requirement labels.** The draft was written against a list of requirements; the labels it cites
are these ([P4] is v0.4's tag, its §5.1: the source's holding names only the chunks it has sent).

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

**Numbers.** Every figure in this draft comes from the toy (`toy/`, 60 nodes unless stated)
unless it says otherwise. A
figure from fewer than ten seeds, a single seed unless stated, is a toy check of a mechanism, not a
measurement; ranges over ten or more seeds say so.

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
    params: TypeParams                               # §6.3: the open decisions sit here

class TypeParams:                                    # per object type; values in §6.3
    M: int                                           # colours of the push relation           [D10]
    F_LO: int                                        # in-pushers per family and colour: the floor [D10]
    F_HI: int                                        # and the cap                             [D10]
    D_OUT: int                                       # out-pushees per family and colour       [D10]
    D_OUT_FAST: int                                  # the same for a fast uplink              [c17]
    D_OUT_MAX: int                                   # what a node accepts to push for others
    ANNOUNCE_EXTRA: AnnounceWidth                    # ALL_JOINED | SAMPLE | NONE              [D5]
    EAGER: bool                                      # chunks of this type are pushed; False: holdings and offers only (rows, EIP-8371)
    DECODE_AT_K: Callable[[GroupId], bool]           # repair: who decodes at K, claiming all        [D4]
    DECODE_LATER: Callable[[GroupId], Optional[float]]   # repair: who decodes later if the group is still short, and when (from known_at) [D4]
    REPAIR_TO: Callable[[GroupId], List[PeerId]]     # repair: whom rebuilt chunks of a group go to  [D4]
    REPAIR_BUDGET: bool                              # repair: each rebuilt chunk to R_NODE of them lacking it, offered
                                                     #   to the rest (§1.6: its rebuilder is its source); False: v0.3's,
                                                     #   every peer short of K up to its shortfall   [D4]
    DEFER_WINDOW: float                              # repair: how long a peer's claim defers our own decode (R5) [D4]
    START_DELAY: float                               # seconds before the first ask             [D8]
    SERVE_LIMIT: int                                 # chunks served per peer and group         (R6)
    SAMPLE_RETRY: float                              # a sampler's wait before trying another link (§4.10)
    EVIDENCE: Optional[ObjectType]                   # the fraud-proof object, if any           [D6]
```

| | payload (v0.3) | column (PeerDAS) | row (RowDAS) |
|---|---|---|---|
| a group | one descriptor's chunks | one column of one block | one row of one block |
| group id | `group_id(descriptor)` | `(block_root, column)` | `(block_root, row)` |
| N | `descriptor.count` | the blob count | `NUMBER_OF_COLUMNS` = 128 |
| K | `ceil(total_length / segment_size)` | N: no code across blobs | 64 |
| `verify` | v0.3's `validate_chunk`: the Merkle path to the committed root; DEFER before the block | `verify_cell_kzg_proof_batch`, one cell index, many commitments; DEFER before the header | the same, one commitment, many cell indices |
| `decode` | v0.3's `decode_and_reencode`: any K chunks to all N, or None if the root differs | the cells present, if all are; nothing is rebuilt within a column (§4.6) | `recover_cells_and_kzg_proofs` from 64 |
| `header_of` | the descriptor the chunk carries (design A), checked against the bid in the installed block | `PartialDataColumnHeader`, validated once per block on any group | the same header |
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
serving limit (§4.5). A sampler is `(DECLARED, NONE)`; a custodian `(DERIVED, FORWARD)`; every node
on the payload `(ALL, FORWARD)`. Interest and duty are per link, so one node may be a custodian
towards its custody peers and a sampler towards others; nothing a node declares on one link is
announced on another.

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
case where both relations are the same symmetric set of eight and the scope is the mesh.

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
colouring at GRAFT, §4.1).

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
object type defines one `[D6]`; this document carries it and does not define it.

### 1.6 Roles are derived, not declared

A **source** is any node that holds chunks of a group before its peers do: the builder with the
whole payload, or a node that built columns from its mempool at block arrival (I8, X8). The source
rules of v0.3 §5.1 (batch order, striping, the window and the cap) apply to what such a node pushes
first; whether a node is a source is read from its holdings and its peers' holdings, not announced.
A **forwarding node** is any node with duty `FORWARD`. A **reconstructor** is a node whose repair
rule (§4.6) says it decodes a group or a block it does not need whole for itself.

## 2. Messages

Abstract messages; §7 binds them to wires. Every message names its object type or group, and a
receiver ignores, without penalty, a message for an object type it has not joined on that link.

```python
class Join(Container):                   # per link and object type, sent by both ends   [D11]
    object_type: TypeId
    interest: InterestKind               # ALL | DERIVED | DECLARED
    custody_count: uint64                # the input to derived interest (the ENR's cgc), else 0
    duty: Duty                           # FORWARD | NONE
    colours: uint16                      # M[T] as the sender runs it; a mismatch is no link for T

class Graft(Container):                  # relation maintenance, per family and colour
    object_type: TypeId
    family: FamilyId
    colour: uint16
    direction: Direction                 # OUT: "I will push you this colour"; IN: "push me this colour"; BOTH

class Prune(Container):
    object_type: TypeId
    family: FamilyId
    colour: uint16
    direction: Direction

class Have(Container):                   # what the sender holds, verified                   [c7]
    group: GroupId
    bits: Bitmap
    offer: boolean                       # True: "you may ask me for these"; False: a holding (§1.5)
    claim_all: boolean                   # [c10] the decode claim; holdings only              [D3]
    complete: boolean                    # my interest in this group is satisfied; holdings only [D3]

class Want(Container):                   # "send me these", to this peer only                [D2]
    group: GroupId
    bits: Bitmap

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
  peer for, not what it lacks, and the peer sends it what it holds of that now and the rest when it
  arrives, within the group's lifetime (§4.10). The ask discipline of v0.3 §6.1 sends one index per
  peer at a time and carries over for pulls against offers; a bitmap lets a client batch, and a
  sampler declares its indices in one. There is no third bitmap for need `[D2]`: a peer with
  `DERIVED` or `ALL` interest never sends a WANT for what both ends can compute, and a declared
  interest is only ever told to the peers it is asked of (I6).
- **A chunk carries its header once per group and link**, so cells can be verified before the block
  (P2); the payload's header is the descriptor, which the chunk carries (design A) and the installed
  block confirms, as in v0.3.

## 3. State

```python
# per link and object type (new)
join_recv: Dict[PeerId, Dict[TypeId, Join]]           # what p declared to us
join_sent: Dict[PeerId, Dict[TypeId, Join]]           # what we declared to p
push_out: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Set[int]]]]   # colours we push p, per family
push_in: Dict[PeerId, Dict[TypeId, Dict[FamilyId, Set[int]]]]    # colours p pushes us, per family

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
origin: Dict[GroupId, Bitmap]                         # v0.4's: for a group we publish, the chunks we have sent [P4]
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
claims: Dict[GroupId, Set[PeerId]]                    # new: peers whose claim_all arrived (R5, §4.6)
reconsider_at: Dict[GroupId, float]                   # new: when our later decode duty fires, if armed (§4.6)
deferred: Dict[GroupId, bool]                         # new: we deferred it once on a claim (R5)
waited: Dict[GroupId, bool]                           # new: we waited once for chunks held on another axis (§4.6)
probe: Dict[GroupId, int]                             # new: the index we asked a claimant for, to verify the claim (R5)
probed: Dict[GroupId, PeerId]                         # new: the claimant we asked
probe_asks: Set[Ask]                                  # new: those asks, exempt from stop-pull (§4.6)
rsample: Dict[GroupId, List[int]]                     # new: the repair sample's indices, asked of custodians (R5, option)
rsample_step: Dict[GroupId, int]                      # new: how many of REPAIR_SAMPLE's steps were asked
rsample_asked: Dict[GroupId, Dict[int, Set[PeerId]]]  # new: the custodians each sampled cell was asked of
rsample_final: Dict[GroupId, bool]                    # new: the last step's re-asks were waited for
```

Lifetimes are v0.3 §8.1's: per-group state lives `GROUP_TTL` past the last chunk or the completion
and leaves a tombstone; per-peer entries live `HAVE_TTL` and `PUSH_TTL` heartbeats or until the
connection closes; relations live until PRUNE or disconnection. Reading a missing entry allocates
nothing; the admission checks of v0.3 §8.2 and the limits of §6.3 come first. A node may hold state
for a group it has no interest in, when it holds chunks of it or a peer's interest names it (a
reconstructor's non-custodied columns, R4); the number of such groups per slot is bounded (§6.3).

**Helpers not written out**, beyond v0.3 §8.1's: `type_of_group(g)` (the object type a group id
names), `links(T)` (the peers with a JOIN for `T` both ways), `joined_types()`, `node_id(p)`,
`in_pushers(T, fam, c)` and `out_pushees(T, fam, c)` (the peers whose relation holds that colour),
`candidates(T, fam)` (joined peers with duty, not yet in the relation), `least_used_colour(T,
fam)`, `families_with_duty(T)`, `wants_family(T, fam)`, `duty_for(g)`, `uplink_class()` (card 17),
`send(p, msg, urgent)` (a message into the bounded per-peer queue of v0.3 §7; the binding's job;
true if the queue admitted it, as v0.5's `enqueue`),
`Ask(g, i)` (an ask's key, v0.3's `WantIndex`), `chunk_id(f)` (v0.3's `message_id`),
`open_group(g, f)` (as v0.3's, and records `T_of`, `interest`, `known_at`), `open_group_source(g,
h)`, `interest_satisfied(g)` (§1.5), `deferred_offers(p, h)` (§4.3),
`publish_evidence(g, body)`, `unreachable(g, bits)` (§4.10: no link can serve a sample; the
application decides), `wire_size(f)` (§4.11: the chunk's bytes on the wire, the binding's),
`cell_groups(root)` (the column and row groups of a block, from their ids alone).

## 4. Events

Validation runs off the receive path as in v0.3 §4.1. The order of handling one RPC is v0.3's:
chunks, then offers (which produce asks), then asks (which produce answers), then GRAFT and PRUNE,
then holdings, then the response.

```python
def on_rpc(p, rpc):
    for f in rpc.chunks: on_chunk(p, f)                              # §4.2
    asks = [a for h in rpc.haves if h.offer for a in on_offer(p, h)]  # §4.3
    answers = on_want(p, rpc.asks)                                    # §4.5
    prunes = []
    for gr in rpc.grafts: prunes += on_graft(p, gr)                   # §4.1
    for pr in rpc.prunes: on_prune(p, pr)
    for h in rpc.haves:
        if not h.offer: on_holding(p, h)                              # §4.3
    respond(p, asks, answers, prunes)                                 # v0.3 §4.1
```

### 4.1 Joining, and keeping the relations

```python
def on_join(p, j: Join):
    T = type_of(j.object_type)
    if j.colours != T.params.M: return                 # no v2 for T on this link; the stock path remains
    join_recv[p][T] = j
    if T not in join_sent[p]: send(p, our_join(T), urgent=True)

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
            if len(ins) < T.params.F_LO:               # the floor per colour                [D10]
                for q in candidates(T, fam)[: T.params.F_LO - len(ins)]:
                    send(q, Graft(object_type=T.id, family=fam, colour=c, direction=IN), urgent=False)
            if len(ins) > T.params.F_HI:
                for q in ins[T.params.F_HI:]:
                    send(q, Prune(object_type=T.id, family=fam, colour=c, direction=IN), urgent=False)
                    push_in[q][T][fam].discard(c)
            outs = out_pushees(T, fam, c)
            target = T.params.D_OUT_FAST if uplink_class() == FAST else T.params.D_OUT    # [c17]
            for q in candidates(T, fam)[: max(0, target - len(outs))]:
                send(q, Graft(object_type=T.id, family=fam, colour=c, direction=OUT), urgent=False)

def on_graft(p, gr: Graft):                            # returns the PRUNEs to send back
    T = type_of(gr.object_type); fam, c = gr.family, gr.colour
    back = []
    if gr.direction in (OUT, BOTH):                    # p offers to push us colour c
        if len(in_pushers(T, fam, c)) < T.params.F_HI and wants_family(T, fam):
            push_in[p][T][fam].add(c)
        else:
            back.append(Prune(object_type=T.id, family=fam, colour=c, direction=OUT))
    if gr.direction in (IN, BOTH):                     # p asks us to push it colour c
        if join_sent[p][T].duty == FORWARD and len(out_pushees(T, fam, c)) < T.params.D_OUT_MAX:
            push_out[p][T][fam].add(c)
        else:
            back.append(Prune(object_type=T.id, family=fam, colour=c, direction=IN))
    return back

def on_prune(p, pr: Prune):
    T = type_of(pr.object_type)
    if pr.direction in (OUT, BOTH): push_in[p][T][pr.family].discard(pr.colour)
    if pr.direction in (IN, BOTH): push_out[p][T][pr.family].discard(pr.colour)

def propose_colour(T, fam) -> int:                     # balanced colouring
    return least_used_colour(T, fam)
```

Gossipsub's symmetric mesh is `direction = BOTH` with `M = 1`, `F_LO = Dlo`, `F_HI = Dhi` and
`D_OUT = D` (§6.1). Backoff after PRUNE and the scoring of GRAFT floods are the client's, as in
gossipsub; what this document fixes is that a relation exists only after both ends agreed it.

### 4.2 A chunk arrives

```python
def on_chunk(p, f):
    mid = chunk_id(f)
    if seen(mid) or mid in pending_ids:                # a duplicate, a chunk rejected before, or one waiting
        if accepted(mid): send_have(p, f.group)        # [c14] duplicates are acknowledged too
        return
    if expired(f.group): return
    T = type_of_group(f.group)
    on_validated(p, f, T.verify(f, T.header_of(f)))   # level 1; DEFER while the gate is closed

def on_validated(p, f, result):
    if result == DEFER: return defer(p, f)             # v0.3 §4.2: the bounded per-peer store
    mark_seen(chunk_id(f))                             # accepted or rejected: never validated again
    if result == REJECT: return penalise(p)            # level 1 failures are the sender's
    T = type_of_group(f.group)
    for (g, i) in T.project(f): fill(g, i, f, p)       # (R4) one arrival fills every group it belongs to
    if any(duty_for(g) == FORWARD for (g, i) in T.project(f)): forward(f, p)   # §4.4: on any axis we serve; never waits for level 2
    for (g, i) in T.project(f): check_completion(g)    # §4.6

def fill(g, i, f, p):
    if g not in T_of: open_group(g, f)                 # hdr[g], T_of[g], interest[g], known_at[g]
    if state[g] == INVALID: return                     # a dropped group (§4.6)
    if received[g].has(i) or rebuilt[g].has(i):        # a copy of a chunk we hold: acknowledge it
        return send_have(p, g) if p is not None else None
    store(g, i, f)
    (received if p is not None else rebuilt)[g].set(i) # from the network, or from our own decode (§4.6, R4)
    close_promises(g, i)                               # [c5] the chunk arrived, from anyone
    serve_standing(g, i)                               # §4.10: WANTs that preceded it are answered now
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
    if g in origin:                                    # [P4] a group we publish claims only what we have sent:
        whole = done = popcount(bits) >= n             #   both claims once every chunk has left, none before
    else:
        whole, done = state[g] == DECODING or popcount(mine[g]) >= n, stop_pull[g]
    return Have(group=g, bits=bits, offer=False, claim_all=whole, complete=done)
```

`have_bits(g)` is v0.4's (§4.2 there): what we hold, or for a group we publish what we have sent
(§4.7). `merge_waiting(p, h)` is the binding's, used only where the node merges (`MERGE_HOLDINGS`,
§6.3, permitted):
if a holding of `h.group` to `p` is still in our queue, it now names its own bits and `h`'s, with
`h`'s claims, and the call returns True.

The gate is the object type's: the installed block for the payload (its descriptor comes from the
bid; `validate_chunk` returns DEFER before it), a validated header for cells, which may precede the
block. A deferred chunk is held in the bounded per-peer store of v0.3 §4.2 and §8.2 and resumes
when the gate opens. `authenticable(g)` is the gate of `g`'s type: nothing of `g` is asked for
before it opens, and what was offered meanwhile is asked for when it does: for the payload at v0.5's
`on_block_installed` (its §3, §4.4), for cells when the binding first validates a block's header:

```python
def on_header_validated(root):                       # (P2) a block's cell header, validated once
    for g in cell_groups(root):                       # every column and row group of the block
        for a in ledger(g): retry_offer(a)            # offered meanwhile, asked for now (v0.5 §4.4)
```

The toy's cells carry their header, so their gate is open from the first cell and this never runs
there.

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
    e.complete = e.complete or h.complete              # nothing more goes to p for this group
    if h.claim_all: note_claim(p, h.group)             # (R5) §4.6: it may defer a decode duty of ours
    for i in newly:
        holders[h.group][i].add(p)                     # [c9] distinct live holders
        window_release(p, h.group, i)                  # [c14] a slot to p frees when p holds i, from anyone

def on_offer(p, h: Have):                              # v0.3 §4.4's on_ihave over one group's bitmap; returns asks
    g = h.group
    if expired(g): return []
    if now - known_at[g] < type_of_group(g).params.START_DELAY:   # [D8] (R7) a secondary axis waits
        return deferred_offers(p, h)                   # recorded as offers; asked when the delay has run
    candidates = []
    for i in h.bits & interest[g] & ~mine[g]:          # offered, wanted, and not held
        a = Ask(g, i)
        add_offer(a, p)                                # [c5] the offer table (v0.5 §6.1)
        if gated(a) or not authenticable(g): continue  # [c6] stop-pull; the gate first (v0.5 §3, §4.2 here)
        if parked(p, a): last_resort(a); continue      # [c5] park; every announcer parked: v0.5 §6.1
        candidates.append(a)
    return [a for a in shuffled(candidates) if may_ask(a, p)]   # v0.3 §6.1: one ask per index at a time
```

An offer from any link is an offer: the announce relation decides who learns what we hold, the
pull discipline of v0.3 §6.1 decides whom we ask, when to move on and whom to park. Offers never
touch `peer_has`, `holders`, cancel or the window; holdings never feed the offer table. A node
handles at most `MAX_IHAVE_MESSAGES` offer-bearing RPCs per peer and heartbeat (v0.3 §8.3).

### 4.4 A node forwards

```python
def forward(f, from_peer):
    for (g, i) in type_of_group(f.group).project(f):                       # (R4) each axis with its own type
        T = type_of_group(g)
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
    gossip_history.put(f)                                                  # heartbeat gossip (§4.8)

def announce(p, g, bits):                                                  # [c3, c7] an offer
    b = bits & ~pushed[p][g] & ~peer_has[p][g].bits & interest_of_peer(p, g)   # an empty bitmap is not sent
    if b and not send(p, Have(group=g, bits=b, offer=True, claim_all=False, complete=False), urgent=False):
        owe(p, g, b)                                                       # refused by a full queue: owed (v0.5)

def announce_extra(g, i) -> List[PeerId]:                                  # [D5]
    T = type_of_group(g); fam = T.family(g)
    if T.params.ANNOUNCE_EXTRA != ALL_JOINED: return []                    # SAMPLE: the heartbeat's paced gossip (§4.8)
    related = {q for q in links(T) if push_out[q][T][fam] or push_in[q][T][fam]}
    return [q for q in links(T) if q not in related and wants_from_me(q, g).has(i)]
```

A forwarding node's rules are v0.3 §5.2 and §5.3 with two changes: the candidates are the push
relation for the chunk's colour instead of the mesh, filtered by the peer's interest; and the
offer's width beyond the relation is a parameter. With `M = 1`, interest `ALL` everywhere and
`ANNOUNCE_EXTRA = SAMPLE`, the two functions are v0.3's `forward` and `announce`.

### 4.5 An ask arrives, and serving

```python
def on_want(p, asks):                                  # v0.3 §4.5's on_iwant, plus the serving limit (R6)
    answers = {}                                       # by id: one answer per id per RPC
    for a in asks:
        gi = group_index(a)
        if gi and expired(gi.group): continue          # past its active lifetime: ignored, no penalty
        declared = gi and join_recv[p][type_of_group(gi.group)].interest == DECLARED
        if declared:                                   # its WANT is its interest (§1.2)
            want_p[p][gi.group] = want_p[p].get(gi.group, EMPTY) | bitmap({gi.index})
        if gi and peer_has[p][gi.group].has(gi.index):
            penalise(p)                                # it asks for a chunk it claimed: the claim wins
            continue
        if gi and served[p][gi.group] >= type_of_group(gi.group).params.SERVE_LIMIT:
            continue                                   # (R6) refused without penalty
        mid = resolve(a)                               # [c7] our chunk at that index: received or rebuilt
        if mid is None:
            if declared: standing[gi.group][gi.index].add(p)   # §4.10: answered when the chunk arrives
            continue
        if mid in unwanted[p]: continue
        serve_count[p][mid] += 1
        if serve_count[p][mid] > GOSSIP_RETRANSMISSION: continue   # stock: 3 answers per id per peer
        if gi: served[p][gi.group] += 1
        answers[mid] = chunk_of(mid)
    return list(answers.values())                      # [c14] one chunk per queue entry (v0.3 §4.1)

def serve_standing(g, i):                              # §4.10: the chunk a WANT waited for is here
    for q in standing[g].pop(i, ()):
        if peer_has[q][g].has(i) or served[q][g] >= type_of_group(g).params.SERVE_LIMIT: continue
        served[q][g] += 1
        if not enqueue(q, Entry(chunk=chunks[g][i], solicited=True), urgent=False):   # an answer, like any
            owed_answers[q][g].set(i)                  #   other: refused by a full queue, owed (v0.5 §7.2)
        note_push(q, g, i)                             # so that no offer follows it (§4.4)

def may_be_asked(p, g, i) -> bool:                     # (P7) scoring reads interest
    return offered_us(p, g, i) or interest_of_peer(p, g).has(i) or peer_has[p][g].claim_all
```

A node serves what it holds, received or rebuilt, to anyone who asks, within the serving limit per
peer and group `[R6]`, whatever the asker's duty. An ask may go to a peer that offered the index
or whose derived interest includes it (a custodian can be asked without offering, PeerDAS's
"knows exactly what a peer should be able to respond to"); an ask outside both is a violation. A
promise is made by an offer, and a broken one parks the peer for the group (v0.3 §6.1). A
`DECLARED` peer's WANT is also its interest: `want_p[p][g]` is set from it before the asks are
answered, and what the peer does not hold yet is kept as a standing request (§4.10), which is why
derived interest makes no promise with a timer: the custodian answers when it can. Standing
requests live with the group's state (`GROUP_TTL`) and count against the serving limit when
answered.

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
    qs = [q for q in links(type_of_group(g2))          #   the node a link to one per column)
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
    if deferred[g] and not received[g].has(probe[g]): penalise(probed[g])   # (R5) the probe was not answered
    state[g] = DECODING                                             # the late decode claim, as at K
    mine[g] = all_bits(T.index_count(hdr[g]))
    for q in suppression_scope(g): send_have(q, g)
    start(decode_group, g)

def note_claim(p, g):                                  # (R5) from on_holding: p claims every index of g
    claims[g].add(p)
    if (g in reconsider_at and state[g] == COMPLETE and not deferred[g]
            and popcount(mine[g]) < type_of_group(g).index_count(hdr[g])): defer_on_claim(g)

def defer_on_claim(g):                                 # (R5) verify the claim by one ask, and wait for it
    T = type_of_group(g)
    deferred[g] = True
    i = next(i for i in range(T.index_count(hdr[g])) if not mine[g].has(i))
    probe[g] = i
    q = probed[g] = choice(list(claims[g]))
    a = Ask(g, i)
    add_offer(a, q); tried[a][q] = now                 # a claim is an offer of every index (v0.3 §6.1's tables)
    probe_asks.add(a)                                  # past stop-pull and the ask window: gated exempts it
    promises[(a, q)] = now; after(T.params.DEFER_WINDOW, promise_due, a, q, now)   # broken: the claimant is parked
    send(q, Want(group=g, bits=bitmap({i})), urgent=False)
    arm(g, max(reconsider_at.get(g, now), now + T.params.DEFER_WINDOW))

def gated(a): return stop_pull[group(a)] and a not in probe_asks    # [c6] v0.3 §6.2, with the probe exempt

def decode_group(g):                                   # level 2, off the chunk path
    T = type_of_group(g)
    whole = T.decode(chunks[g], hdr[g])                # every chunk of the group, or None
    if expired(g): return                              # the group passed its lifetime meanwhile (v0.5 §8.1)
    if whole is None: return drop_group(g)             # [D6] and publish_evidence(g, …) if T.params.EVIDENCE
    new = [i for i in whole if not received[g].has(i)] # rebuilt, and not received meanwhile
    filled = []                                        # the other groups the rebuilt chunks fill, in order
    for i in new:
        store(g, i, whole[i]); rebuilt[g].set(i)       # servable from now on
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
  duty is armed defers the duty once, by at least `DEFER_WINDOW`, and the receiver asks that peer
  for one index it lacks (a claim is a promise: §4.5 `may_be_asked`). If the chunk arrives, the
  claim held, and a row member's duty ends when the window has run; a node that keeps the row on
  no link goes by the cells it holds (below). If the promise is broken, v0.3's pull discipline
  parks the claimant and the duty fires with the probed claimant penalised. The probe's promise is the
  deferral window itself, not v0.3's `PROMISE` of 400 ms: a reconstructor that has just decoded is
  pushing a row's worth of rebuilt cells through its window, and in the toy its answer to a probe
  left 450 ms after it was decided, so with the shorter promise honest claimants were parked and
  penalised. Until a probe has verified it, a
  claim counts for nothing in the subnet's view of the row (`known_in_scope`): executing the toy's
  liar fault showed that a false claim otherwise made the row look whole to every member of its
  subnet and suppressed the third phase, the suppression the RowDAS design warned of. The probe is
  an ask past completion,
  so it is exempt from stop-pull (card 6) and from the one-ask-per-index window, which otherwise
  dropped it in the toy and penalised honest reconstructors; and it counts against the claimant's
  serving limit like any answer, so a member that has already pulled `SERVE_LIMIT` chunks from the
  claimant should probe another claimant or keep one ask in reserve. The RowDAS design asked for
  "defer and re-arm" because a bitmap takes a round trip and cancelling on a claim outright lets
  any peer suppress reconstruction; the probe makes the re-arm a verdict on the claimant rather
  than a timer, at the cost of one cell.
- **The verdict, by what the node can see** (R5: re-arm "if the cells do not follow"; decided
  2026-10-10, with sampling the repair, below, an option). A row
  member, a node that takes part in the row's family (`wants_family`: its own subnet's row), has a
  subnet's view of the row (`known_in_scope`), and a verified claim ends its duty when the window
  has run, whoever made it, as in draft 1, subject to the member check (below). A node that keeps
  the row on no link, a supernode on the rows of the other subnets (interest declared on no link,
  §1.2) and on every row under custody alone, goes by the cells it holds: a claimant that answers
  the probe and sends nothing else costs it one window, not the row. An earlier wording told the two
  apart by a non-empty suppression scope (some peer pushes the row to the node); a member that no
  peer pushed its row to then counted as keeping the row on no link and rebuilt after a verified
  claim, which with 32 subnets (about two members each at 60 nodes) added about 4 member decodes
  per run (20 against draft 1's 16, the median over seeds 7 to 19) and none with 16. With this
  wording the row cells with supernodes (honest, and half the columns withheld with 16 and with 32
  subnets) and the withheld custody cell with a fifth of the nodes hoarding run as under draft 1,
  event for event on all 13 seeds, and so do 48 of the 52 seed-cells of the row cells with
  supernodes and a fifth or half hoarding. Draft 1 ended both on the probed cell; when the toy's
  rebuilders stopped pushing to supernodes (an exploration), supernodes deferred on a claim that
  came in an acknowledgement, received the probed cell, and ended one cell short of a column. A first version of this rule counted a verified claim only from a peer in the
  node's view, and row members decoded two to four times as many rows (with 16 subnets, 31 against
  9 per run, the median over seeds 7 to 19) for no change in time or bytes: their claimants were
  mostly supernodes rebuilding the row in the second phase, which have no relation on it, so their
  claims reach a member in the acknowledgement of a column chunk (§4.2, `fill`). A claimant that
  rebuilds a row, answers the probe and pushes nothing (the toy's `--fault hoard`) passes the probe
  and ends the members' duties. Where an honest supernode keeps the row, its second phase repairs
  the row, under this rule and under draft 1's alike: in three traced runs no supernode ended its
  duty on a verified claim, presumably because a claim on a row reaches a supernode outside the
  subnet only in the acknowledgement of a cell the supernode sent, which a hoarder sends while still
  short. Where none does, the row is lost: without
  supernodes, a fifth of the nodes hoarding left custodians short in every run over seeds 7 to 19
  (16 subnets, half the columns withheld), each time a subnet whose honest members had deferred to
  a hoarding reconstructor; the member check (next) closes this where the subnet has an honest
  member. A deferral is the duty's one wait (no `known_across` wait follows it), and only a broken
  probe counts against the claimant.
- **The member check** (R5, decided 2026-10-09; `owed_missing`). A verified claim ends a member's
  duty only once the row's cells in the member's own custody columns have arrived: those are the
  cells the claimant's repair owes it (§4.6 below: rebuilt cells go to the custodians lacking them),
  so an honest claimant delivers them within the window and a claimant that repairs nothing does
  not. Otherwise the member goes by the cells it holds and rebuilds the row, telling its subnet
  peers as for any decode. The check needs nothing new on the wire: the member reads its own
  holdings at the moment it would have stopped. Measured in the toy over seeds 7 to 19 at 60
  nodes, 16 subnets, half the columns withheld (`toy/README.md`):
  - *What it addresses: a claimant that rebuilds, passes the probe and repairs nothing* (the toy's
    `--fault hoard`). Without supernodes, with a fifth of the nodes hoarding, custodians were left
    short on every seed without the check and on 3 of 13 with it; with half hoarding, on 13 and on
    10. Every seed on which each subnet has an honest member completes.
  - *And a false claim the probe let through.* The probe counts as answered when the probed cell
    arrives, from anyone; a claimant that never answers passes it when another peer brings the cell
    in time. Among the toy's liars (`--fault claim`, which claim their row and answer no ask)
    without supernodes, this happened 1 to 3 times per run on 5 of 13 seeds, and each time the
    member check sent the member to rebuild instead of trusting the liar (all five seeds traced).
    The few (node, row) pairs left short on those seeds, with and without the check, are the liars'
    own rows, which the toy's liars never rebuild: the check moved their count by one or two, on
    three seeds.
  - *What it does not address.* A subnet whose members all misbehave (seeds 14, 17 and 18 at a
    fifth): nobody honest is there to check. A member whose custody columns are all among the
    published ones holds its cells whatever the claimant does (0.3 % of members with 8 of 128
    columns and half withheld), so the check passes for it, though its subnet's other members still
    check. A claimant that pushes each member exactly its custody cells of the row and withholds the
    rest passes the check (the toy's `--fault hoardm`: without supernodes, a fifth of the nodes
    doing so left custodians short on all 13 seeds); the next bullet samples for it. Where an
    honest supernode keeps the row, its second phase already repairs what a hoarder withholds,
    and the check never fired there.
  - *What it costs.* Where nobody misbehaves, nothing: in five cells (rows honest with and without
    supernodes, withheld with 16 subnets with and without, withheld with 32 with supernodes) it
    never fired and every event is the same. A rescued block completes later, 3.25 / 3.44 s (p50 /
    p99) against 2.44 / 2.71 s without hoarders, since the member rebuilds at the third phase after
    a deferral; its bytes are not higher (2.33 copies against 2.36), since hoarders push nothing.
    In ten traced runs with hoarders or liars all 162 firings were on a misbehaving claimant's
    claim: a needless rebuild, an honest claimant's repair
    still on its way when the window ends, was not seen at 60 nodes. It is the case to watch at
    larger scale, where repair travels further.
- **Sampling the repair** (R5, option: `REPAIR_SAMPLE`, `SAMPLE_WAIT`). The member check asks
  whether the member's own share of the repair came; RowDAS's rule asks whether the cells followed,
  into every column. A member cannot see the other columns, but it can sample them, as a node
  samples a block, and IncrementalDAS gives the test its shape ("LossyDAS: lossy, incremental, and
  diagonal sampling for data availability", ethresear.ch 2024,
  https://ethresear.ch/t/18963): after a verified claim and a passed member check, the member asks
  `S1` cells of the row that it lacks, each of a custodian of the cell's column that is not a
  claimant (`REPAIR_FLOOR` keeps it a link to one), and re-arms its duty for `SAMPLE_WAIT`. With at
  most `L1` of them missing, the repair followed and the duty ends; otherwise it extends the sample
  to `S2` cells containing the first and re-arms once more, and with more than `L2` missing it
  rebuilds. It extends the sample, never drawing a fresh one, as IncrementalDAS does, since the
  larger sample could have been drawn at once ("toss a coin until you like the result" is the alternative
  the post rules out); allowing losses is LossyDAS's answer to a custodian that has not yet received
  a repaired cell when asked. The cells a member lacks past K are the withheld columns', the ones
  only a repair brings, and the claimant cannot know which the sample picks. Over seeds 7 to 19 at
  60 nodes, 16 subnets, half the columns withheld (`toy/README.md`):
  - *Against a claimant that repairs only the members' cells* (a fifth of the nodes, without
    supernodes): short on 13 seeds with the member check alone, 5 with `(3, 1), (6, 2)`, 3 with
    `(4, 0), (8, 1)` or `(6, 0), (12, 1)`, the seeds on which a subnet has no honest member. In a
    traced run every failed sample was on a hoarder's claim. The lenient form passed partial repairs:
    the hoarding members' own pushes had filled some columns, and 4 of 6 cells came. A rescued block
    completes at 4.2 s (p50) against 2.4 s without the fault, the rebuild waiting out the deferral and
    two sample steps; the member check alone catches a claimant that repairs nothing at 3.25 s.
  - *Where nobody misbehaves* no sample failed in any form, with or without supernodes, and the
    times and bytes are within the seeds' spread; the cost is the sampled cells, at `(4, 0), (8, 1)`
    without supernodes 532 per run, 4.4 per node and block averaged over all nodes. With supernodes every cell completed in every form.
  - *Where custodians do not answer.* The toy's liars answer no ask, so a sample cell asked of one is
    lost: with a fifth of the nodes lying, `(4, 0), (8, 1)` failed on honest claimants in 18 of 41
    verdicts at seed 7 and in 46 of 48 at seed 8 with supernodes, where a liar is a supernode and so
    a custodian of every column, and the strict forms had members rebuild 21 to 26 rows per run
    more, without changing completion.
  - *Re-asking a lost cell* (`REPAIR_REASK`, measured over the same seeds) separates an
    unresponsive custodian from a missing repair: when a step is judged, each missing cell is
    re-asked of another custodian of its column, with the extension, and at the last step in one
    more wait before the rebuild. Among liars the strict forms' failed samples fell from 15 to 27
    per run (median) to none at the median, at most 22 in one run, and members rebuilt as many rows as with the member check alone (74
    against 80 without supernodes, 46 against 45 with them, at `(4, 0), (8, 1)`). Where no cell was
    lost (no fault, and a claimant that repairs nothing) the runs are the same event for event.
    Against a claimant that repairs only the members' cells, `(4, 0), (8, 1)` and `(6, 0), (12, 1)`
    still leave short only the seeds without an honest member, and a rescued block completes half
    a second later, at 4.7 s, for the one more wait; `(3, 1), (6, 2)` stays lenient (short on 4).
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
- **Repair across groups** (R4). A rebuilt chunk fills every group it belongs to (`fill` on the
  other axis) and `push_rebuilt` works group by group: for a row, the rebuilt cells of row b go
  into the column groups of their columns, to the custodians `REPAIR_TO` names that lack them,
  which is "the push into non-custodied columns is the whole of the relief" (the RowDAS design);
  the row's own members, complete at 64, are not pushed what they do not want. For the payload,
  `project` is the identity and this is v0.3's `push_rebuilt`. PeerDAS's reconstruction is the
  second phase without row subnets (below).
- **A rebuilt chunk completes the groups it fills** (R4). `decode_group` checks the completion of
  every other group its rebuilt chunks filled, as `on_chunk` does after an arrival. A member whose
  custody column lacked only cells of the row it rebuilt holds the whole column after its own
  decode; draft 1 filled the column without the check, so the member never completed it: it neither
  stopped pulling it nor told its peers, and the toy counted it short (in one run of the repair
  floor's measurement below, before the fix).
- **Every member keeps a link to each column** (`REPAIR_FLOOR`, recommended). A row is gathered from
  the columns and repaired into them, so a member needs, for every column, a link to a node that
  custodies it: to pull that column's cell of its row, and to push the cell it rebuilt. `REPAIR_TO`
  names custodians among the node's links, and EIP-8371 reaches the other columns through
  gossipsub's fanout ("after reconstruction, a node SHOULD use the Gossipsub fanout mechanism to
  provide cells from the reconstructed blob to peers across column subnets it is not subscribed
  to"), which uses connected peers only. So the rendezvous keeps, for every node that may rebuild,
  at least `REPAIR_FLOOR` links to custodians of each column it does not custody, as a proposer
  keeps links to every column it publishes. In the toy's withheld row cell over seeds 7 to 19 at 60
  nodes, without the floor five runs left custodians short, and each was a missing link. In four, a
  column with two custodians missed a cell because neither was linked to the only member that
  rebuilt the row; the deferral on a claim, which cancels a second decode once the first is
  verified, makes a single rebuilder common. In the fifth, a subnet had two members, linked only to
  each other among members, and each gathered 63 cells of its rows from the columns' custodians, one
  short: neither was linked to the only custodian of one published column, so neither row was ever
  rebuilt. With `REPAIR_FLOOR = 1` all thirteen runs completed, at 1 to 30 added links per run, with
  completion times and bytes within the seeds' spread (§6.2, `toy/README.md`). Opening a link
  through the rendezvous only when a rebuilt cell has nowhere to go is an option: it costs a lookup
  and a handshake while the cell waits, and it does not help a member gather a row.
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
  columns have not completed by then. In the toy at 60 nodes, three supernodes (5 %) on datacenter
  links complete every custodian on all thirteen seeds of the custody cell whose proposer withholds
  half the columns, which nothing else recovers, in 1.20 s at the median and 1.25 s at the tail (the
  medians over the seeds); they complete the 32-subnet withheld row cell, which its subnets without
  members left short, in 1.20 and 1.83 s, and they take the 16-subnet cell from 2.44 / 2.71 s to
  1.20 / 1.76 s. The cost is bytes: 3.3 copies of a node's custody in the withheld row cells against
  2.4 without supernodes, and 3.8 in the custody cell (§6.2, `toy/README.md`), most of it duplicate
  pushes of the fast class: with a budget of `R` for cells it is 2.6 to 2.8 copies, with the tails
  0.1 to 0.15 s shorter (§6.3, `R_NODE`, for later study).
- **A row held on the columns is on its way** (R4). The subnet's view (`known_in_scope`) holds only
  the row's own axis, and at the second phase's timer a supernode may still be receiving its 128
  columns. On home links, three supernodes in the toy's honest row cell rebuilt 186 rows that
  nobody had withheld, and the cell's tail went from 1.09 to 1.49 s (seed 7). A chunk held on one
  axis is held on the other, so the duty also reads what its relation peers on the other axis
  hold (`known_across`; `T.cross` names a chunk's other (group, index) pairs from the ids alone):
  for a supernode, its peers' bitmaps on every column, which is EIP-8371's "observing the bitmaps
  of all column subnets". A row whole in that view but not in the node's holdings is on its way:
  the duty waits once, `DEFER_WINDOW`, and fires then if the row is still short in the node's
  holdings, so a false holding delays a rebuild by one window and no more. With it, no supernode
  rebuilt a row in any of the thirteen honest custody or row runs. In the withheld cells the three
  supernodes still rebuild most rows more than once (131 to 167 of the 192 row decodes that three
  supernodes and two blocks of 32 rows allow); a jitter longer than a rebuilt row's trip to the
  other supernodes would cancel more of them, not measured. A member reads the same view over its
  custody columns; it changed no event of the seed-7 row cells without supernodes.
- **A rebuilder pushes as a source** (`REPAIR_BUDGET`, an option, off). A rebuilder holds the
  rebuilt chunks before its peers do, so it is their source (§1.6), and the option has it push each
  one to `R_NODE` of the peers lacking it and offer it to the rest, as a source does, instead of
  pushing it to every peer short of it. Without supernodes, in the withheld 16-subnet row cell,
  where members on home links rebuild, it is better on every count over the thirteen seeds: 12 900
  repair pushes against 36 900, 2.19 copies against 2.36, the tail 2.62 s against 2.71 (the median
  over the seeds) and 2.68 against 2.82 at the worst seed. With supernodes on datacenter links,
  whose budget is the fast class's six, it saves 0.15 copies and costs 0.21 to 0.25 s at the tail
  (2.00 against 1.76 s with 16 subnets, 2.04 against 1.83 with 32), and in the custody cell 0.05
  copies for 53 ms. With the fast class's budget off for cells (§6.3, `R_NODE`) it saves 0.41 copies
  in the 16-subnet cell for 0.1 s at the median and the tail (seeds 7 to 9). It stays an option.
- **Whom rebuilt cells go to** (`REPAIR_TO`, options). A supernode keeps every row, so a rebuilder's
  push into a column reaches it too, and where several nodes rebuild a row their pushes cross in
  flight: at 500 nodes (seed 7) 88 % of the rebuilt cells pushed in the withheld custody cell
  arrived as duplicates, the whole of that cell's extra cost over the honest one (3.76 against 2.83
  copies). The duplicates are bounded by what a node's own peers push it, so no estimate of the
  network's size is needed to bound them. Three forms were measured over seeds 7 to 19 at 60 nodes
  with three supernodes (the toy README): offering the cells to the nodes that keep every row
  instead of pushing them saves 0.17 to 0.33 copies at no cost in time; offering every rebuilt cell,
  as a row's are, saves 0.5 to 0.7 copies and costs 60 to 110 ms at the median; leaving the keepers out
  saves as much as offering to them, but costs the custody cell a 2.3 s tail, since a supernode left
  out has only its own rebuild, after a deferral. Each is an option; the push stays.

### 4.7 The source

```python
def publish(block, d, shards):                         # the payload's builder; v0.3 §5.1 over the relation
    g = group_id(d)
    open_group_source(g, d)                            # hdr[g] = d; T_of, interest, known_at
    T = type_of_group(g)
    for s in shards:                                   # the source holds every chunk from the start
        f = Chunk(slot=block.slot, beacon_block_root=block_root(block), group=g,
                  descriptor=d, index=s.index, proof=s.proof, data=s.data)    # descriptor: design A
        store(g, s.index, f); mark_seen(chunk_id(f))
        gossip_history.put(f)                          # heartbeat gossip may offer it (§4.8)
    mine[g] = all_bits(N(d)); state[g] = COMPLETE; stop_pull[g] = True
    origin[g] = bitmap(set())                          # [P4] our holding names only chunks we have sent: none yet
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
    fam = T.family(g)
    for i in range(N(d)):
        for p in [q for q in links(T) if colour_of(g, i) in push_out[q][T][fam]]:
            announce(p, g, bitmap({i}))                # [c3] relation peers not pushed a chunk are offered it

def origin_sent(f):                                    # [P4] a chunk of a group we publish leaves for the first
    if origin[f.group].has(f.index): return            #   time (§4.11): it joins our holding, which goes where a
    origin[f.group].set(f.index)                       #   forwarding node's goes when a chunk arrives (§4.2)
    for q in suppression_scope(f.group): send_have(q, f.group)

def candidates_for_source(f):
    T = type_of_group(f.group); g = f.group; fam = T.family(g); c = colour_of(g, f.index)
    if UPLINK >= STRIPE_UPLINK: pool = links(T)                                   # [c13] every link
    else: pool = [q for q in links(T) if c in push_out[q][T][fam]]                # the relation, as the other nodes do
    return [q for q in pool if wants_from_me(q, g).has(f.index)]
```

Batch order (card 2), striping (card 13), the window (card 14) and the concurrency cap over whole
messages are v0.3 §5.1 and §7.1 unchanged; the generalisation is that the candidates are
the links that want the chunk, which for a pre-seeded peer (a node with the blobs from its
mempool, I8) is decided by the holding it sent before any data, so a source holding *part* of a
group pushes only what its peers lack.

**The source's holding is paced** [P4], as in v0.4 §5.1 and for the same reason: a holding that
names every chunk before any has left can come only from the source. A group's holding names only
the chunks its source has sent; a chunk joins it when the writer first sends it (§4.11), and the
holding then goes to the suppression scope, as a forwarding node's does when a chunk arrives (§4.2).
A peer the source pushes to gets a holding naming its first chunk just ahead of it. The rule is per
group, so a proposer paces the holding of each column group it publishes. The two claims (§1.5)
follow the paced bitmap: a source claims neither `claim_all` nor `complete` for a group it
publishes until every chunk of it has left, which is what v0.4 does by reading its decode claim from
a full bitmap. A pre-seeded node (I8) is not covered: it holds part of a group before its peers but
did not publish it, and its first holding names what it holds, which is what lets its peers skip it.
The signs v0.4 lists as remaining remain here too: the source offers every chunk at publish (the
last loop above), its holding grows faster than anyone's, and it is everyone's first sender.

What P4 costs here depends on how many groups a source publishes. For the payload, one group, it
costs nothing (§6.1). A proposer of 128 column groups sends a holding per cell to each peer in that
column's scope: in the toy at seed 7, about 38 800 holdings of 52 bytes over three blocks, 0.68 MB
a block, which is about 108 ms of a 50 Mbps uplink. In the toy at 60 nodes (seeds 7 to 16) the
custody block completes 116 ms later at the median of the seeds (53 to 164 ms) and 106 ms later at
the tail, and the row cells 98 ms later at the median and 132 ms at the tail. With a 1 Gbps
proposer the cost is 6 ms at the median. Its peers, no longer told that it holds every cell, also
offer it cells. Under the liar fault P4 leaves more row members short (108 (member, row) pairs over
ten seeds against 80; not traced). With v0.5 merged (2026-10-21) 2 pairs stay short over the same
seeds, none on eight of them; v0.5 changed whom a node asks once the announcers it tried broke
their promises (its §6.1), but the runs are not traced. The other cells move by a few ms
(`toy/README.md`).

**Merging the source's holdings** (`MERGE_HOLDINGS`, §4.2, permitted) takes back little of this.
v0.4 allows holdings that would leave together to be merged into one; here a holding still in the
source's queue takes the newer chunks instead of a second holding going out. With writes that
complete at once, only holdings made in the same instant are in the queue together: 7 % of the
slow proposer's holdings merge, and the custody block gains 10 ms of P4's 116 at the median and
12 ms at the tail, the rows 4 ms at the median and 20 ms at the tail. With a transport that takes
one write per connection at a time (the toy's `--send-buffer 1`), a holding also waits while
another entry to the same peer goes out: 18 % merge, and the custody block gains 16 ms of P4's
80 ms there, the rows again 4 ms at the median. Copies and completion do not change, and under the
liar fault 100 pairs stay short against P4's 108 (both before v0.5). Most holdings would leave alone anyway: at seed
7, 59 % find no earlier holding of their group still waiting, in the queue or in the transport.
Taking back more needs fewer holdings, which v0.4 does not provide for: holding them back for a
set time, or sending them to fewer of the scope's peers; both are for later study. The figures
are in `toy/README.md`.

The offers in the last loop are card 3 at the source, and they cost a home builder bytes. In the
toy's tier 4 cells they draw asks that the builder answers after its first copies, 0.34 to 1.35
copies of the message over three seeds, and 81 to 94 % of those answers arrive as duplicates.
Without the offers a 50 Mbps builder uploads 1.6 to 1.8 copies of the message instead of 2.1 to
2.9, and its cells' medians move by less than 10 ms; a 1 Gbps builder uploads 2.0 copies instead
of 10 to 12 but completes 10 ms later, and a 1 Gbps proposer of columns 75 ms later, since its
offers let peers pull from it while its uplink has room. A rule keyed on the configured uplink, as
striping's is, would save the bytes where they are scarce. Open; the order of a source's queue is
§4.12's.

### 4.8 The heartbeat

```python
def on_heartbeat():
    ids = gossip_history.gossip_ids()                         # stock: ids of the last 3 heartbeats
    for T in joined_types(): maintain_relations(T)            # §4.1
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

Per heartbeat, as v0.3 §6.4: TTLs expire, the relations are maintained, and the paced gossip of
offers to the sample goes out one peer per pace tick (card 15, `on_pace_tick` unchanged). The
window of v0.3 §7.1 is per node across every group of every object type (X3).

### 4.9 The window's projection, per object type

```python
def projected(p, g):                                           # [c12] v0.3 §7.1, read per object type
    T, h = type_of_group(g), hdr[g]
    if T.threshold(h) == T.index_count(h): return False         # no code: every index is needed, nothing is projected
    has, sent = peer_has[p][g].bits, sent_to[p][g]
    return popcount(has) + FAN_IN * popcount(sent & ~has) >= T.threshold(h)
```

Card 12 drops a chunk to a peer that is projected to reach K from what it holds and what is on its
way, on the premise that any K chunks complete a coded group. A column has no code across its
cells (K = N), so the premise fails: a dropped cell is a cell the peer still needs, and in a thin
family nobody else may be pushing it. Executing the custody setting (§6.2) found this: with v0.3's
`projected` a custodian ended short of exactly the cells its pushers had projected away, and
nobody offered them, since a planned push is not announced. Projection applies to types with a
code only.

**The window's unit (X3).** v0.3 §7.1 counts the window in slots of `CHUNK_BYTES` (12 000 bytes,
the payload's chunk), `W = ceil(uplink_bytes_per_s · (RTT_REF + TARGET) / CHUNK_BYTES)`. A cell is
2 096 bytes, so the same slot count carries a sixth of the bytes per round trip: in the toy a
50 Mbps proposer of 128 column groups was held to about 10 Mbps by its own window (a 9 MB block
took 9.2 s where its uplink allows 2 s), a 1 Gbps one to about a fifth of its uplink, and a
reconstructor's answer to a probe left 450 ms late behind its burst of rebuilt cells. One window
over every object type (X3) is therefore counted in bytes here, a chunk taking its own length of
it (§4.11); slots per object type would be the alternative, with the same capacity question at
every boundary between types.

### 4.10 A sampler pulls

```python
def sample(g, bits):                                   # interest without duty: declare, to one peer that will hold it
    T = type_of_group(g)
    cands = [q for q in links(T) if join_recv[q][T].interest != DECLARED
             and not parked(q, Ask(g, 0)) and (interest_of_peer(q, g) & bits) == bits]
    if not cands: return unreachable(g, bits)          # no link custodies it: the application decides
    q = choice(cands)
    interest[g] |= bits                                # ours, from now on (§1.5: complete when they arrived)
    send(q, Want(group=g, bits=bits), urgent=False)    # a standing request (§4.5); no promise timer
    after(T.params.SAMPLE_RETRY, resample, g, bits, q)

def resample(g, bits, q):                              # the peer did not deliver in time: another one
    missing = bits & ~mine[g]
    if missing.empty(): return
    park[q][g] = now + PARK_TTL                        # it held or should have held them; counts against it
    sample(g, missing)
```

A sampler's interest is `DECLARED` and its duty `NONE` (§1.2). It learns the group ids from the
block, as everyone does, and declares each sample to one link whose interest includes it: a
custodian of the column, or a peer with interest `ALL`. The declaration is a WANT and nothing else:
no JOIN names the sample, no holding of ours reaches anyone but the sender of a chunk (the
acknowledgement of §4.2), and the peer learns only what it was asked. Decided: nor does it start a
promise, which v0.5 starts when an ask is written (its §7.2); `SAMPLE_RETRY` is the WANT's own
timer (the repair sample's WANT of §4.6 likewise). The custodian answers from
what it holds and, for the rest, when the chunks arrive (§4.5), so the WANT may go out at block
arrival, before any cell has reached the custodian; in the toy it does. A peer that has not
delivered after `SAMPLE_RETRY` is parked for the group and the sample is declared to another link;
the duplicate that the first peer may still deliver is acknowledged like any duplicate. With
`SERVE_LIMIT` a custodian bounds what one peer pulls from it per group (R6), which is what keeps a
"sampler" from pulling a column it did not join. What a sampler does when no link can serve a
sample (`unreachable`), and how many samples it takes, are the application's: FullDAS's cells per
slot, or PeerDAS's eight columns.

### 4.11 The window, in bytes

```python
W_BYTES = W * CHUNK_BYTES             # v0.3's W slots of CHUNK_BYTES: the payload's capacity is unchanged  [c14, X3]
in_flight = 0                         # bytes taken: held by a writer for the chunk it is about to send, or travelling
waiters = deque()                     # peer writers waiting for room, first come first served
sent = {}                             # (peer, group, index) -> (send time, bytes)

def acquire_room(p, need) -> bool:    # True: p's writer may send `need` bytes now; False: it waits in line
    global in_flight
    fits = in_flight + need <= W_BYTES or in_flight == 0          # an empty window always takes one chunk
    if fits and (not waiters or waiters[0] == p):
        if waiters: waiters.popleft()
        in_flight += need
        if waiters and in_flight < W_BYTES: wake(waiters[0])     # room remains: the next in line tries too
        return True
    if p not in waiters: waiters.append(p)                       # a writer keeps its place while it waits
    return False

def leave_line(p):                    # p's writer has nothing to send now
    if p in waiters:
        waiters.remove(p)
        if waiters and in_flight < W_BYTES: wake(waiters[0])

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

def free_room(need):
    global in_flight
    in_flight -= need
    if waiters: wake(waiters[0])                  # the first writer in line tries again

def next_to_send(p):                  # v0.3 §7.2, with the chunk chosen before the room is taken
    q = queue[p]
    while True:
        if owed_answers[p] and has_room(p):                    # an answer a full queue refused (v0.5 §4.1)
            enqueue(p, Entry(chunk=pop_owed_answer(p), solicited=True), urgent=False)
        if q.urgent: return with_owed(p, q.urgent.pop(0))      # HAVEs, acks, decode claims: first
        if not q.normal:
            out = with_owed(p, Entry()) if owed[p] else None   # owed offers on their own (v0.5 §7.2)
            if out: return out
            leave_line(p); return None                         # nothing to send
        k = choose(q)                                          # §4.12; chosen first: its size is what the window counts
        entry = q.normal[k]
        need = wire_size(entry.chunk) if entry.chunk else 0    # control takes no room
        if need and not acquire_room(p, need): return WAIT     # [c14] in line, FIFO over peers; an urgent arrival
        q.normal.pop(k)                                        #   wakes the writer, which keeps its place
        out = filter_entry(p, entry)                           # [c8, c12], and stale asks
        if need and not (out and out.chunk): free_room(need)   # the chunk did not leave: the room goes back
        if out:
            if out.chunk:
                track_in_flight(p, out.chunk, need)            # [c14] the room travels with the chunk
                if out.chunk.group in origin: origin_sent(out.chunk)   # [P4] our holding grows (§4.7)
            return with_owed(p, out)                           # owed offers ride along
```

The window keeps about one round trip of the uplink in flight, whatever the chunks' sizes: a
payload chunk of 12 KB takes six times the room of a cell, and `W_BYTES` is v0.3's `W` slots
of `CHUNK_BYTES`, so the payload's cells see the same capacity as before. Two things change
besides the unit. The writer chooses the entry before taking room, since the room depends on the
chunk; v0.3 took a slot first and chose after, which also made a control-only entry at the head of
the queue wait for a chunk's slot, and here control takes no room. And an empty window always
admits one chunk, so a chunk larger than the window is not stuck. `filter_entry`, `rarest` and
`projected` (§4.9) are as before; `wire_size(f)` is the binding's, the chunk's bytes on the
wire.

What the unit changes, in the toy (60 nodes, one seed, `toy/README.md` for the tables): the
custody setting's block completes in 347 ms at the median and 456 ms at the tail with a 1 Gbps
proposer where the slot window gave 777 and 963, and in 2.4 s with a 50 Mbps proposer where it
gave 9.2 s, which is the uplink's own bound (2.2 s with §4.12's source rule); the sampling
cell's samples arrive in 264 ms at the median where they took 750; under half the columns
withheld every custodian completes through the
rows in 2.4 s where it took 2.7, with every claim verified and none re-armed, since a
reconstructor's answers no longer queue behind its rebuilt cells; and in the honest row cell no
member decodes at the third phase at all, where 37 did, because the column path is done before
the phase and the subnet's view is whole. At 500 nodes the custody block completes in 531 ms at
the median and 680 at the tail where the slot window gave 1 011 and 1 207, and the withheld block
through the rows in 2.4 and 2.5 s where it gave 2.5 and 3.0. Tier 4 moves within 15 ms and 0.04
copies (§6.1). The recommendation is the byte window; the decision is open (X3).

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

**A source's own chunks go first.** v0.3's rarest-first (card 9) reorders only the chunks ahead of
the first control-only entry, and its source queues each group's offers after that group's pushes
(v0.3 §5.1). With one group the offers follow every push, and rarest-first sees them all. A
proposer publishes a block's 128 column groups at one instant, one group after another, so the
first group's offers sit in every peer's queue ahead of the other groups' pushes. Rarest-first then
sees one group's chunks at a time, the offers leave early and draw asks, and the answers and the
second copies take the proposer's window from its first copies. Here the writer chooses among the
node's own chunks over the whole queue, past offers and answers, by rarity, before anything else.
In the toy, at three seeds and 60 nodes with a 50 Mbps proposer, the custody block completes 247 ms
sooner at the median and 430 ms sooner at the tail, every seed sooner. At seed 7 the proposer's
last first copy leaves 0.3 s sooner, it sends 1 992 second copies where it sent 2 400 and answers
518 asks where it answered 1 212, and over both blocks it sends 15 % fewer chunks, since more of
its queued pushes are dropped by a holding while they wait (card 8). Elsewhere the rule changes
nothing that the seeds can tell apart. Every single-group cell (tier 4, variant C, the twelve check
cells) runs exactly as under v0.3's order, at 60 nodes and at 500. At 60 nodes so does every cell
with a 1 Gbps proposer, except the honest row cell, whose tail is 22 ms sooner while its median
moves by between 8 ms sooner and 42 ms later. At 500 nodes, over three seeds, the 1 Gbps proposer's
custody and sampling cells move within 5 ms at the median and between 5 ms sooner and 17 ms later
at the tail, and its withheld row cell runs exactly as before. Two other cures for the same cause
were checked in the toy and lose. Dropping the source's offers, or queueing them after all of the block's
pushes, matches the gain with a slow proposer but costs 7 to 355 ms at the median with a fast one,
whose offers let custodians pull from it while its uplink has room. The rule is recommended, under
X3 (one window over every group); the decision is open.

**Answers before pushes** (`ANSWERS_FIRST`, an option, off). An answer is a chunk its receiver
asked for, so it is never a guess, and the asker's clock runs: after `IWANT_WINDOW` it asks
another holder, and after `PROMISE` it parks us for the group. A push has no clock. Under v0.3's
order an asked chunk is rarely the rarest, since a peer of ours holds it, so its answer waits
behind fresh pushes. With the option the writer sends queued answers, by rarity, after the node's
own chunks and before any other push. Checked against the rule above at three seeds, completion
barely moves: within 5 ms at the median in most tier 4 cells, 39 ms sooner in the honest row cell,
and 12 ms later in the thin lossy cell (`loss-thin`) on every seed. The asks' round trip at the
99th percentile is shorter in most cells, by up to 44 ms, and a few hundredths of a copy are
saved. Three other forms were checked against v0.3's order and lose. The oldest answer first,
before a source's own chunks too, costs a 50 Mbps proposer 315 ms at the median. An answer's writer
ahead of the window's line of writers costs `loss-thin` 91 ms at the median. An answer first only
once it has waited 100 ms costs `loss-thin` 12 ms and the 50 Mbps proposer 61 ms. The option is the
one to try where answers wait behind long runs of pushes: with cards 8, 9, 12 and 15 off, a node's
answers waited 1.1 to 1.7 s at the 99th percentile, and at most 0.22 s with the option.

### 4.13 The ask window follows the uplink

v0.3's two clocks on an ask (§6.1 there) are fixed: after `IWANT_WINDOW` (200 ms) the asker asks
another holder, and after `PROMISE` (400 ms) it parks the asked peer for the group. Both were set
where answers come back within a round trip or two, at 50 Mbps. On a thinner link an answer waits
longer behind the answerer's queue, the window runs out before it arrives, the second ask's answer
competes with the first for the same thin uplinks, and both arrive: the bytes stop falling with
the bandwidth and the tail grows. Here the ask window stretches in proportion as the node's own
uplink falls below `ASK_UPLINK`, and stays as v0.3 set it above it. The promise does not change.

```python
def ask_scale() -> float:
    """1 at ASK_UPLINK and above; ASK_UPLINK / UPLINK below it (5 at 10 Mbps)."""
    return max(1.0, ASK_UPLINK / UPLINK)


IWANT_WINDOW = IWANT_WINDOW * ask_scale()      # 200 ms at 50 Mbps and above, 1 s at 10 Mbps
```

- **Whose uplink:** the asker's own, the one figure a node is configured with (card 14 sizes its
  window from it, card 17 its push degree). The asked peer's link is not known; a home node asking a
  datacenter peer waits longer than it needs to before moving on, which costs time only when that
  peer does not answer.
- **The floor** is v0.3's value: at 50 Mbps and above the protocol is v0.3's, event for event.
- **The promise stays at 400 ms**, so a peer that does not answer is still parked as soon as in
  v0.3, and the asker moves on from it later only by the window. Stretching the promise with the
  window too was checked and rejected: with 30 % withholders at 10 Mbps it lengthened the tail by
  18.5 % at the median of three paired seeds in the research harness, since withholders then went
  unparked for the whole payload. A slow honest peer can now be parked before the asker has moved
  on from it (the promise is shorter than the window below 25 Mbps); in the toy the count of parked
  pairs stayed below v0.3's on clean, withholding and mixed networks, since fewer asks go out, but
  rose by about 60 % with 10 % of chunks lost (lost answers break promises). A promise per peer that follows its observed
  answer times is the open alternative (§8).
- **Evidence** (the research harness of the posts), against v0.3's fixed window
  on the same seed: at 10 Mbps per node, over ten paired seeds, every seed faster and leaner, the
  tail 5.1 % shorter at the median (2.2 to 8.4 %) and 0.20 fewer copies (0.15 to 0.23); at 25 Mbps,
  over ten, fewer copies in every seed but only 0.03, and the tail unchanged within the seeds'
  spread (0.8 % shorter at the median, from 2.4 % shorter to 3.3 % longer); with 30 % withholders at
  10 Mbps, over three, the tail 3.5 % shorter and 0.18 fewer copies. The toy's checks (mixed network,
  silent peers, loss): §6.3's `ASK_UPLINK` row.

## 5. What carries over from v0.3 unchanged

| v0.3 | here | note |
|---|---|---|
| §1 the payload, the code, the commitment | the payload object type's `verify`, `decode`, `header_of` | the leaf rule may change under `[D6]` |
| §3 the three levels | level 1 = `T.verify`, level 2 = `T.decode`, level 3 = the application | per object type (I7) |
| §4.1 `respond` | called from §4's `on_rpc` | asks ride on the first answer; an answer a full queue refuses is owed (v0.5) |
| §4.2 `defer`, `on_block_installed`, the bounded store | §4.2 | the gate is the type's (`authenticable`); a copy the store refuses counts as its sender's offer (v0.5) |
| §4.6 `drop_group` | §4.6 | plus evidence `[D6]` |
| §5.1 batch order, striping, the cap, the paced source HAVE [P4] | §4.7 | candidates filtered by interest; P4 per group, its claims with the bitmap |
| §5.3 `choose_push`, `guard_fails`, `note_push` | §4.4, §4.7 | candidates come from the relation |
| §6.1 `may_ask`, `retry_offer`, `promise_due`, `parked`, the offer table | from §4.3's `on_offer` | offers from any link; `IWANT([a])` read as a WANT; start delay `[D8]`; `IWANT_WINDOW` scaled by the node's uplink (§4.13); v0.5's offers kept per connection and group (`add_offer`, `announcers`) and its last resort when every announcer is parked (`last_resort`, `ask_parked`) |
| v0.5 §5.2, §7.2 `owe`, `unpush`, `with_owed` | §4.4 to §4.7, §4.11 | a push or an offer a full queue refuses, or a push the writer skips, is offered with the next write to the peer; `mesh` in `unpush` reads as the peers of the push relation |
| §6.2 `gated` | `on_offer`, `filter_entry` | per interest |
| §6.4 `on_pace_tick` | §4.8 | |
| §7.2 `filter_entry`, `rarest` | `send`, `enqueue`; §4.12 | unchanged; the writer takes a source's own chunks first (§4.12); v0.5's promise starts when an ask is written, and a WANT starts none (§4.10) |
| §7.1 the window, §7.2 `next_to_send` | §4.11 | one window per node over every object type, counted in bytes; the entry is chosen before the room is taken |
| §7.1 `projected` | §4.9 | reads the type's K; off for a type without a code |
| §8.2 limits | §6.3 | plus relations and groups per slot |

## 6. Settings

### 6.1 v0.3 as a setting

| notion here | in v0.3 |
|---|---|
| object type | the payload only; one family |
| JOIN | subscription to the payload's topic: interest `ALL`, duty `FORWARD`, `M = 1` |
| push relation | the mesh: `direction = BOTH`, `F_LO = 6`, `F_HI = 12`, `D_OUT = 8` |
| announce relation | the mesh, plus `ANNOUNCE_EXTRA = SAMPLE` (heartbeat gossip to `max(D_LAZY, GOSSIP_FACTOR · n)` non-mesh peers, paced) |
| suppression scope | the mesh |
| holding / offer | IDONTWANT with a `HaveBitmap` / IHAVE with a `HaveBitmap` |
| WANT | IWANT with a `WantIndex`, one index at a time |
| claims | `claim_all` = the decode claim (all N bits); `complete` = the same, since interest is all |
| repair | `(everyone, at once, the mesh peers)` |
| `START_DELAY`, `SERVE_LIMIT` | 0, unbounded (the stock per-id limit remains) |
| evidence | none |
| wire | v0.3 §2's magic strings (§7) |

The toy's twelve cells are the regression for this setting, recorded for this document in
`toy/golden-v2.txt` (`toy/check.py --doc v2`) and compared against v0.3's own recording with
`toy/check.py --doc v2 --golden golden.txt`. Checked on 2026-10-07: with v0.3's window (slots of
one payload chunk) eleven of the twelve cells reproduced v0.3's completion times and bytes exactly
and `rr-stripe` differed by 3 ms at the median, the residue being the order of same-instant sends
(this document iterates the relation in peer order where v0.3 iterated the mesh set). With the
window in bytes (§4.11) the cells move by at most 7 ms at the median, 15 ms at the tail and 0.04
copies either way (`announce` p99 576 → 587 ms, `without-a` 578 → 565 ms, `loss-thin` 984 →
999 ms, `push` copies 2.41 → 2.43), which is the two structural changes of §4.11 and not the unit:
a control-only entry at the head of a queue no longer waits for a chunk's slot, and the chunk is
chosen before the room is taken. So this document contains v0.3 to within those amounts, and
with v0.3's window exactly but for `rr-stripe`'s 3 ms. Since v0.4's P4 came in (2026-10-21, §4.7) the comparison is with v0.4's
recording (`golden.txt`): eleven cells within 3 ms at the median, 16 ms at the tail and 0.03 copies
(`announce` p99 568 → 584 ms, `rr-stripe` 521 → 505 ms), and `loss-thin`, at a 20 Mbps uplink,
8 ms later at the median and 0.10 copies lighter, the one cell where §4.13's scaled ask window
applies; without P4 the medians had been up to 102 ms behind v0.4's (`silent` 678 against
576 ms). With v0.5 merged (2026-10-21; every cell of both recordings moves) the comparison is
with v0.5's: eleven cells within 7 ms at the median, 15 ms at the tail and 0.03 copies
(`rr-stripe` p50 417 → 410 ms, `dcb20` p99 358 → 343 ms, `cap-wait` 740 → 754 ms), and
`loss-thin` 1 ms later at the median and 0.12 copies lighter, as before the merge (1.81 copies).
Draft 0 did not reproduce the cells at all: it filtered a forwarding node's push candidates by
what it had already pushed, which v0.3 does not, and it shuffled the
relation peers for repair in a different order than v0.3's mesh set, so its random draws diverged;
draft 1 fixed both.

### 6.2 The five designs as settings

| setting | object types | `M` | interest | duty | announce extra | repair | start delay | what it tests |
|---|---|---|---|---|---|---|---|---|
| tier 4 | payload | 1 | ALL | FORWARD | SAMPLE | everyone decodes at K; rebuilt chunks to relation peers short of K | 0 | the regression (§6.1) |
| variant C | payload | N | ALL | FORWARD | SAMPLE per colour | same | 0 | independent pusher sets per index on one neighbourhood; the floor |
| PeerDAS custody | column (rows kept by supernodes) | 1 | DERIVED (`cgc`) | FORWARD | ALL_JOINED | nobody decodes a column (no code); supernodes (every column) keep the rows and rebuild a row still short at the second phase's delay, PeerDAS's reconstruction delayed; rebuilt cells to the custodians lacking them | 0 | thin families, pre-seeded sources, cross-group repair, a proposer withholding half the columns |
| RowDAS | column, row | 1 | DERIVED (columns: `cgc`; rows: the node's subnet) | FORWARD | ALL_JOINED | rows not pushed (`EAGER` off); at K: row reconstructors (64 columns or more) on their subnet's row; later: supernodes on every other row at the second phase's delay, any member on its subnet's row at the third's, each with jitter; a row held on the columns waits once; rebuilt cells to the custodians lacking them; one claim defers once, verified by a probe | rows: a slot fraction | cross-fill, the two claims, deferral on a claim, a proposer withholding half the columns, subnets without members |
| FullDAS sampling | column | 1 | DECLARED | NONE | none | none | 0 | interest without duty: a standing WANT per sample, retried at another link (§4.10); the custodians' serving load |

All five run in the toy (`toy/run.py --doc v2 --setting t4|c|custody|rows`, custody with
`--samplers` for the sampling row). Variant C as a
setting of this document completes the toy's check cell faster in the tail and at more bytes than
the tier 4 setting, the direction the harness measured, with the toy's sizes (`toy/README.md`).
The custody setting runs a block of 32 blobs as 128 column groups from one proposer to custodians
of 8 columns each, with a mesh per column on the custodians' subgraph; every custodian completes,
nothing is pushed outside interest and no node pushes a chunk above its budget, and executing it
found two things in the carried-over code: the window's line of writers stalled while slots were
free (v0.3 §7.1, fixed there, since it is v0.3's window) and card 12's projection assumes a code
(§4.9). With supernodes (`--supernodes`), custodians of every column that keep the rows and rebuild
a row still short at the second phase's delay, the custody cell whose proposer withholds half the
columns completes on all thirteen seeds, where without them 58 of 59 custodians stay short; this is
PeerDAS's reconstruction, delayed (§4.6). The sampling
setting runs on top of custody (`--samplers`): a share of the nodes declare eight cells per block
to one custodian each, and every reachable sample completes, a little before the custodians'
columns do, with the custodians serving a handful of chunks each to samplers; executing it is what
made the WANT a standing request (§4.5, §4.10), since a sampler's WANT reaches the custodian before
the cell does, and a pull with a promise timer would have parked every custodian it asked. The row
setting runs EIP-8371's rows on top of custody: one designated subnet per node, rows pull-only,
members complete at 64, reconstructors of 64 columns decoding at K, any member later, and a
proposer that withholds half the columns, so that only the rows can fill them; at the recorded
seed every custodian completes through the rows, and on all thirteen seeds from 7 to 19 with a
custodian link per column for every member (§4.6's repair floor; without it five runs left
custodians short, each for a missing link), every cell sits in both of its groups (R4), and a
liar fault shows a false claim detected by the probe (R5). Executing it changed the document in
eight places: a chunk a node rebuilt is filled into its other groups as rebuilt and acknowledged
to nobody, and completes them (`decode_group` checks them as `on_chunk` does); repair respects
`EAGER`, so rebuilt row cells are offered to row members and pushed only into the columns; the
claim in a holding is "I hold or can produce every index", not "my interest is satisfied", since a
member complete at 64 was read as claiming 128; the probe is exempt from stop-pull and the ask
window and its promise is the deferral window; an unverified claim counts for nothing in the
subnet's view, or a liar suppresses the third phase; and "still incomplete" is read in that view,
or every member short of 128 rebuilds a row the network already has; and every member keeps a
link to each column (`REPAIR_FLOOR`), or a row is neither gathered nor repaired where no member
has one. With three supernodes the second phase completes the 32-subnet withheld cell on all
thirteen seeds, a cell some of whose subnets have no member (short at seed 7 without them), and
halves the withheld cells' time; it
changed the document in two more places: a supernode keeps every row with interest declared on no
link (§1.2), and a row whole on its columns' bitmaps but not in the node's holdings waits once
before it is rebuilt (`known_across`), or a supernode still receiving its columns rebuilds rows
nobody withheld. Each setting is a settings
file for the toy, and the invariants the
toy checks for every setting (`toy/invariants.py`) are these: every node
completes its interest given a source; nothing is pushed outside interest; upload within the duty
bounds; a claim whose probe goes unanswered is detected; one cell fills both groups; the tier 4 setting
reproduces v0.3's cells. All six are checked: the first three on every run, the claim and cross-fill
ones under the row setting, the last by `check.py --doc v2 --golden golden.txt`.

### 6.3 Parameters, limits and constants

| name | per | meaning | open |
|---|---|---|---|
| `M` | object type | colours of the push relation; 1 … N | `[D10]`: a parameter; the measurement decides |
| `F_LO`, `F_HI` | object type | in-pushers per family and colour: floor and cap (v0.3: 6, 12) | `[D10]` |
| `D_OUT`, `D_OUT_FAST`, `D_OUT_MAX` | object type | out-pushees per family and colour by uplink class (v0.3: 8; card 17's classes) | `[D10]` |
| `R_NODE`, `R` | node | the per-chunk push budget (v0.3: 2, 6 fast; the source's plan) | v0.3 §8.3's open item on size. **For later study** (each to be evaluated carefully): whether cells keep the fast class's 6 or take `R` (2), which would make the budget per object type. The toy's 60-node cells so far, over seeds 7 to 19: supernodes on datacenter links, in the fast class, pushed mostly duplicates into columns of about ten custodians (0.96 copies more per node in the honest custody cell; 0.72 copies and half a second of tail in the honest row cell); with cells at `R` the honest row cell is back at 1.13 s at the tail and 2.22 copies (1.14 s and 2.16 without supernodes), the withheld cells are as fast or faster at the tail (custody 1.25 s, 16 subnets 1.64 s, 32 subnets 1.69 s, against 1.25, 1.76 and 1.83) at 0.6 to 1.2 copies fewer, and the honest custody cell gives up 31 ms at the median and 73 ms at the tail for 1.17 copies fewer. Not yet evaluated: larger families (500 nodes and more), fast nodes other than supernodes, the payload's fast class in the same network, the harness |
| `ANNOUNCE_EXTRA` | object type | ALL_JOINED, SAMPLE or NONE beyond the relations | `[D5]` |
| `EAGER` | object type | chunks of the type are pushed eagerly; False: holdings and offers only (rows) | – |
| `DECODE_AT_K`, `DECODE_LATER` | object type | who decodes at K; who decodes later and when (from `known_at`), e.g. EIP-8371's phases | `[D4]`; the toy's second phase at 1 s, its third at 2 s, each with up to 0.2 s of jitter |
| `REPAIR_TO` | object type | whom rebuilt chunks of a group go to (v0.3: the mesh; columns: custodians lacking them) | `[D4]`; options measured (§4.6, "Whom rebuilt cells go to"): the cells offered, not pushed, to the nodes that keep every row, or every rebuilt cell offered |
| `REPAIR_BUDGET` | object type | each rebuilt chunk to `R_NODE` of those lacking it and offered to the rest, as its source pushes a chunk (§1.6); off: to every peer short of K, v0.3's | `[D4]` |
| `REPAIR_FLOOR` | object type | links the rendezvous keeps, for a node that may rebuild, to custodians of each family it does not hold (the rebuilders' fanout, §4.6) | `[D4]`; recommended, value open; the toy's rows use 1 |
| `DEFER_WINDOW` | object type | how long a peer's claim defers our own decode while one ask verifies it, and that ask's promise (R5) | `[D4]`; the toy uses 1 s |
| `REPAIR_SAMPLE`, `SAMPLE_WAIT`, `REPAIR_REASK` | object type | after a verified claim, the steps `[(S1, L1), (S2, L2), …]` of a sample of the cells we lack, asked of their columns' custodians, each step extending the last and passing with at most `L_k` of `S_k` missing; the wait before each step is judged; and whether a lost cell is re-asked of another custodian, with the extension or, at the last step, in one more wait (R5) | option, off (`None`, `False`); measured in §4.6 |
| `START_DELAY` | object type | seconds from the group id being known to the first ask | `[D8]` |
| `SERVE_LIMIT` | object type | chunks served per peer and group (R6) | – |
| `PROMISE` | object type | how long an offer's promise runs before a broken one parks the peer for the group (v0.3 §6.1: 400 ms) | **For later study** (each to be evaluated carefully): a longer promise for cells. The toy so far: in the honest row cell the 400 ms promise broke 3 321 to 4 204 times per run and parked 804 to 1 039 honest (peer, group) pairs; nearly every broken promise was a column ask that the asked node answered later, 0.45 s after the ask at the median and 0.8 s at the 99th percentile, behind the rows' pulls on its uplink, and none was a refusal. At 0.8 s it broke 1 to 3 times, with completion times and bytes unchanged (seeds 7 to 9), since the asker moves on after `IWANT_WINDOW` either way and the promise decides only whom it parks. For the payload, evaluated with §4.13 (2026-10-19): a promise stretched with the ask window on thin links lets withholders go unparked for the payload (30 % withholders at 10 Mbps: the tail 18.5 % longer in the research harness, three paired seeds; silent peers, who announce nothing and so are never asked, were not hurt in the toy), so the payload's promise stays at 400 ms; a promise per peer that follows its answer times is an option (§8). Not yet evaluated: the longer promise for cells under withholding; more seeds and 500 nodes for cells; what peer scoring reads from a broken promise |
| `SAMPLE_RETRY` | object type | seconds a sampler waits for a standing request before declaring the sample to another link (§4.10) | value open; the toy uses 2 s |
| `EVIDENCE` | object type | the fraud-proof object, if any | `[D6]` |
| `ANSWERS_FIRST` | node | queued answers by rarity before pushes, after a source's own chunks (§4.12) | an option, off in every setting; a wash in three-seed toy checks |
| groups tracked per slot | node | state for groups we hold or peers want, beyond our interest | X6: a limit, value open |
| relations per link | link | families × colours a link may carry | X6: a limit, value open |
| `ASK_UPLINK` | node | the uplink at and above which `IWANT_WINDOW` keeps v0.3's value; below it the window scales by `ASK_UPLINK / UPLINK` (§4.13); 50 Mbps | The toy, in the research harness's setting, against v0.3's fixed window, seeds 7 to 9: fewer copies in every cell, 0.16 to 0.33; the tail shorter in the all-home network at 12.5 Mbps (0.7 to 3.0 %), with 30 % silent peers (2.4 to 4.4 %), in the mixed-bandwidth network at 6 Mbps with a home builder (3.1 to 3.2 %) and with a datacenter builder (3.0 to 3.6 %), and within ±1.6 % with 30 % withholders; with 10 % of chunks lost it is up to 3.2 % longer (a lost answer is waited for until the longer window closes). Open: whether a node should scale by the asked peer's link where it knows it |
| `IWANT_WINDOW` | node | v0.3 §8.3's 200 ms, scaled by `ask_scale()` (§4.13) | – |
| `MERGE_HOLDINGS` | node | a holding of a group the node publishes that is still in its queue takes the newer chunks instead of a second holding (§4.2; v0.4 §5.1 allows it) | permitted: a source may merge (local policy, as v0.4 words it); the toy keeps it off so that its recorded cells stay comparable. The toy, seeds 7 to 16 (§4.7): for a 50 Mbps proposer of 128 column groups it takes back 10 of P4's 116 ms at the custody block's median with writes that complete at once, 16 of 80 ms with one write per connection at a time; copies unchanged |
| `HAVE_TTL`, `PUSH_TTL`, `GROUP_TTL`, `PARK_TTL`, offers, `GUARD_GRACE`, `RTT_REF`, `TARGET`, `WINDOW_TIMEOUT`, pace tick, `MAX_IHAVE_MESSAGES`, `GOSSIP_RETRANSMISSION` | – | v0.3 §8.3 unchanged | – |

## 7. Bindings `[D1]`

The protocol is defined on its own messages. Three bindings carry them; a node may speak more than
one and negotiates per link which one a peer takes.

| message | standalone: a protocol id of its own, these messages as the RPC | onto gossipsub with the Partial Messages Extension | v0.3's wire (the toy's binding) |
|---|---|---|---|
| JOIN | the RPC's first message per object type | `SubOpts(topic, requestsPartial, supportsSendingPartial)` plus an extension field for duty and `M`; interest `DECLARED` is approximated by subscribing | subscription |
| GRAFT, PRUNE with colour and direction | as defined | gossipsub's GRAFT/PRUNE with an extension field for the colour; direction `BOTH` only; no floor per colour | stock |
| HAVE, holding | as defined | `partsMetadata.available` plus two flag bits | IDONTWANT `HaveBitmap`; `claim_all` and `complete` read from a full bitmap, or carried as two bits of the `HaveBitmap`'s version byte (the toy's extension, needed for a row member complete at 64) |
| HAVE, offer | as defined | `partsMetadata.available` to a peer not being pushed | IHAVE `HaveBitmap` |
| WANT | as defined | `partsMetadata.requests` | IWANT `WantIndex` |
| CHUNK | as defined | `partialMessage` | a gossipsub message per chunk |
| EVIDENCE | as defined | a full message on the rendezvous topic | – |
| rendezvous | gossipsub topics per family, or the ENR alone `[D11]` | the topics | the topic |

The standalone binding is where X2's gains are had: interest without
subscription, a push relation per family and colour with a floor and a direction, scoring on these
messages. The extension binding gives up the first two and keeps the rollout inside existing
topics; it is the binding for columns while the extension is the deployed path. A mixed network
needs a bridge between a binding and the stock path that does not double the bytes; it is
not written here.

## 8. Open decisions, and where they bite

| decision | where in this document |
|---|---|
| `[D1]` identity and bindings | §7; §0's "what is assumed" |
| `[D2]` two bitmaps, WANT per recipient, no need bitmap | §2 `Want`, `on_want`, `wants_from_me` |
| `[D3]` two claims | §2 `Have`, §1.5, §4.6 |
| `[D4]` repair's parameters | `TypeParams.DECODE_AT_K`, `DECODE_LATER`, `REPAIR_TO`, `DEFER_WINDOW`; §4.6 `check_completion`, `reconsider`, `push_rebuilt` |
| `[D5]` the announce relation's width | `TypeParams.ANNOUNCE_EXTRA`, §4.4 `announce_extra`, §4.8 `send_gossip` |
| `[D6]` the payload's consistency route | `TypeParams.EVIDENCE`, §4.6 `decode_group`, the payload's leaf rule in §1.1's table |
| `[D7]` groups per column and per row, cross-fill | `ObjectType.project`, `family`, §4.2 `on_validated`, §4.4 `forward` |
| `[D8]` the row pull delay | `TypeParams.START_DELAY`, §4.3 `on_offer` |
| `[D9]` one document or a sibling | this file; §6.1 is the merge path |
| `[D10]` colours (taken: a parameter) | `TypeParams.M`, `F_LO`, `F_HI`, `D_OUT`, §1.4, §4.1 |
| `[D11]` join = (interest, duty); topics as rendezvous | §2 `Join`, §1.2, §7's last row |
| the promise's length (§4.13) | v0.3 §6.1's `PROMISE`; §6.3's `PROMISE` row |

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
