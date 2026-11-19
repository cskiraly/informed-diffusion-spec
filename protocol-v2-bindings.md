# SEACAST's next version (draft): its bindings

> **DRAFT.** A companion of [`protocol-v2.md`](protocol-v2.md), released with it. The standalone
> binding is defined to the byte (§1); the two bindings onto gossipsub's wires are defined to the
> field (§2, §3). Checked in the toy only: no client speaks these bytes yet.

*Written 2026-11-17 from `protocol-v2.md`'s §7 of that date, which it takes over whole, and the
standalone binding's bytes, decided the same day. `protocol-v2.md` §7 now says what every binding
provides and which capabilities the bindings differ in.*

## 0. How to read this

`protocol-v2.md` defines the protocol on its own messages (its §2) and what any binding must provide
(its §7). This document defines the bindings:
- how each carries the messages;
- the rules that hold on one binding only;
- the standalone binding's bytes.

The three bindings:
1. **the standalone binding** (§1): a protocol of its own, on a libp2p stream of its own or in Waggle's
   framing (§1.8);
2. **gossipsub with the Partial Messages Extension** (§2);
3. **v0.3's wire** (§3), `protocol.md`'s, which the toy runs.

§4 has the rules on both of gossipsub's wires, and §5 the transports of a fetch outside the links.
A node may speak more than one binding, and negotiates per link which one a peer takes.

**Terms.**
- A **message** is one of `protocol-v2.md` §2's.
- A **frame** is the unit a binding writes on the wire, and what it is depends on the binding:
  - on the standalone binding's stream, a length prefix and one encoded message (§1.5);
  - in Waggle's framing, one `ObjectPieces`, which Waggle length-prefixes itself (§1.8);
  - on gossipsub's wires, gossipsub's protobuf `RPC`, which can carry several messages.

  It is not a frame of the layers below (QUIC's, or a stream multiplexer's), which carry these frames
  as bytes. `protocol-v2.md`'s rules speak of messages; its §7 names frames only to say that each
  binding's are its own.

**What is normative:**
- §1, the standalone binding, to the byte;
- §2 and §3, the bindings onto gossipsub's wires, to the field;
- §4, the rules on gossipsub's wires.

The sizes in §1.7 are informative.

**At a glance**, message by message:

| message | standalone (§1) | onto gossipsub with the Partial Messages Extension (§2) | v0.3's wire (§3) |
|---|---|---|---|
| JOIN | kind `0x01`, the first message per object type on a link | `SubOpts(topic, requestsPartial, supportsSendingPartial)` plus an extension field for duty and `M`; a sampler's `(DECLARED, NONE)` is no subscription (§4) | subscription; a sampler's is none (§4) |
| GRAFT, PRUNE with colour and direction | kinds `0x02`, `0x03`: an accepted GRAFT is answered by one marked `answer`, and a GRAFT for a relation the receiver holds by a yes again; `PRUNE_BACKOFF` `protocol-v2.md`'s (§4.1 there) | gossipsub's GRAFT/PRUNE with an extension field for the colour; direction `BOTH` only; no floor per colour; accepted in silence, as gossipsub's: the sender is in the relation from its GRAFT, and the backoff after a PRUNE keeps the ends together (`protocol-v2.md` §4.1) | stock, accepted in silence as on the extension binding; under `--upkeep on` the toy runs `protocol-v2.md` §4.1's answered exchange instead, `answer` carried beside the GRAFT, with `PRUNE_BACKOFF` from `--prune-backoff` |
| HAVE, holding | kind `0x04`, flag bit 0 clear | `partsMetadata.available` plus two flag bits | IDONTWANT `HaveBitmap`; `claim_all` and `complete` read from a full bitmap, or carried beside it (the toy's extension, needed for a row member complete at 64; the toy charges no bytes for them, the research harness's Go path a flags byte after the root, under version 4) |
| HAVE, offer | kind `0x04`, flag bit 0 set | `partsMetadata.available` to a peer not being pushed | IHAVE `HaveBitmap` |
| WANT | kind `0x05`: `standing` and `probe` in one flags byte, `hops` a byte | `partsMetadata.requests`; `standing`, `hops` and `probe` need an extension field, which also asks for the part where the asker has not subscribed (§4) | IWANT `WantIndex`; `standing`, `hops` and `probe` carried beside the index, as a holding's claims (the toy charges no bytes for them, the research harness's Go path a flags byte and a hops byte, 43 bytes in all, where `probe` would be a second bit of the flags byte) |
| CHUNK | kind `0x06` for the payload, `0x07` for a cell | `partialMessage` | a gossipsub message per chunk |
| EVIDENCE | kind `0x08`, reserved: none in this version (`[D6]`) | a full message on the rendezvous topic | – |
| rendezvous | gossipsub topics per family, with the ENR beside them `[D11]` | the topics | the topic |

## 1. The standalone binding

A protocol of its own, carrying `protocol-v2.md` §2's messages with every rule of that document: interest
without subscription, a push relation per family and colour with a floor and a direction, the answered
GRAFT, and scoring on these messages (`protocol-v2.md` §7's capabilities, all of them).

### 1.1 The protocol id and the streams

- **The protocol id is `/seacast/2.0.0`.** An incompatible change of these bytes or of the rules moves
  the major version. A compatible addition moves the minor, such as a kind that older readers skip
  (§1.2). A node negotiates per link which binding, and which version, a peer takes.
- **One outbound stream per peer.** Each node opens one stream to each peer with the protocol id, and
  writes its frames there. It reads the peer's frames on the stream the peer opened.
- **The writer's order.** Frames go in the order the writer chooses them (`protocol-v2.md` §4.12),
  each written whole.
- **For later study:** a second outbound stream for frames without a chunk, so that a holding need not
  wait behind a chunk being written to the same peer (the urgent lane at the transport). The toy does
  not model it. A node would then read both of a peer's streams alike.

### 1.2 The message encoding

An **encoded message** is `kind || body`: one byte naming the message's kind, then the message's SSZ,
compressed for the two chunk kinds (§1.4). The same encoded message travels on the stream (§1.5), in
Waggle's framing (§1.8) and in a fetch outside the links (§5).

| kind | message | body (§1.3) |
|---|---|---|
| `0x01` | JOIN | `JoinMsg` |
| `0x02` | GRAFT | `GraftMsg` |
| `0x03` | PRUNE | `PruneMsg` |
| `0x04` | HAVE, a holding or an offer | `HaveMsg` |
| `0x05` | WANT | `WantMsg` |
| `0x06` | CHUNK of the payload | `protocol.md` §2's `Chunk`, compressed |
| `0x07` | CHUNK of a cell, in a column or a row | `CellChunk`, compressed |
| `0x08` | EVIDENCE | reserved: none in this version (`[D6]`) |

- **Unknown kinds.** A message of an unknown kind is skipped without penalty, so that a later version
  can add kinds. Its frame is held to the largest known kind's (§1.6): a longer one is a violation.
- **Types not joined.** A message naming an object type the link has not joined is ignored without
  penalty (`protocol-v2.md` §2).
- **Violations.** A body that does not decode, or one over its kind's bound (§1.6), is a violation: it
  is penalised, and the stream closed.

### 1.3 The types

```python
TypeId = uint8                         # the payload 0, columns 1, rows 2; a new object type takes the next value
FamilyId = uint16                      # the payload 0; a column's index; a row's subnet
Direction = uint8                      # OUT 0, IN 1, BOTH 2
InterestKind = uint8                   # ALL 0, DERIVED 1, DECLARED 2
Duty = uint8                           # NONE 0, FORWARD 1
MAX_HAVE_BYTES = 1024                  # protocol.md §2's: 8 192 indices
Bitmap = ByteList[MAX_HAVE_BYTES]      # protocol.md §2's: index i is bit i % 8 of byte i // 8, least significant
                                       #   bit first; trailing zero bytes dropped

class GroupId(Container):              # one layout for every object type: 35 bytes
    type: TypeId
    key: Bytes32                       # the payload: its group key (protocol.md §1); a column or a row: the block root
    index: uint16                      # the payload: 0; a column: its index; a row: its index (the blob's)

class JoinMsg(Container):              # 0x01
    object_type: TypeId
    fork_digest: ForkDigest            # the fork at which the sender runs the type
    interest: InterestKind
    custody_count: uint64
    duty: Duty
    colours: uint16

class GraftMsg(Container):             # 0x02
    object_type: TypeId
    family: FamilyId
    colour: uint16
    direction: Direction
    answer: boolean

class PruneMsg(Container):             # 0x03
    object_type: TypeId
    family: FamilyId
    colour: uint16
    direction: Direction

class HaveMsg(Container):              # 0x04
    group: GroupId
    flags: Bitvector[8]                # bit 0 offer, bit 1 claim_all, bit 2 complete
    bits: Bitmap

class WantMsg(Container):              # 0x05
    group: GroupId
    flags: Bitvector[8]                # bit 0 standing, bit 1 probe
    hops: uint8
    bits: Bitmap

class CellChunk(Container):            # 0x07
    group: GroupId                     # the column or the row it is sent in
    index: uint32                      # the row in a column, the column in a row
    cell: ByteVector[BYTES_PER_CELL]   # 2 048 bytes
    proof: KZGProof
    header: List[PartialDataColumnHeader, 1]   # with the first eager push of a group on a link (P2)
```

- **The flags.** A flags byte's other bits are zero when sent and ignored when received, so that a
  later flag fits without breaking older readers.
- **The enums.** A value outside `Direction`'s, `InterestKind`'s or `Duty`'s list is a violation. A
  `TypeId` a node does not know names a type the link has not joined, and is ignored (§1.2).
- **The payload's chunk (`0x06`)** is `protocol.md` §2's `Chunk`, unchanged: its proof a
  `List[Bytes32, 14]`, its header the descriptor it carries under design A; under design B the bid
  carries the descriptor and the chunk does not, a choice `protocol.md` §1 leaves open. It is the
  same bytes on this binding as on v0.3's wire, compression aside, and its group is `GroupId(0,
  chunk.group, 0)`.
- **The consensus types:** `ForkDigest`, `KZGProof`, `BYTES_PER_CELL` and `PartialDataColumnHeader`
  are consensus-specs' (the header from Fulu's partial columns, `specs/fulu/partial-columns/
  p2p-interface.md`, at `2ea9d96a`). The header is optional as partial columns make it optional: a
  list of zero or one.
- **The fork** (`protocol-v2.md` §7). A link carries an object type only where both ends' JOINs for it
  name the same `fork_digest`, as their `colours` must match. At a fork a node sends its new JOIN.
  - *Open:* what a link's relations do from the fork until both ends' JOINs name the new digest. Also
    open is how the new JOIN sits with `send_join`'s once per link and type (`protocol-v2.md` §4.1).
- **The header** (`CellChunk.header`) goes with the first eager push of a group on a link
  (`protocol-v2.md` §2). It is validated apart from the cell, before the cell is handled
  (`protocol-v2.md` §7): a copy whose id is seen or waiting still brings it. A header that fails its
  checks is rejected, as consensus rejects one, and counts against its sender; one that cannot be
  judged yet, which consensus ignores (a slot ahead, a parent not yet seen), waits and counts against
  no one. Neither marks the cell's id.
  - *An answer carries none:* the asker held the header to ask, as consensus's partial columns also
    reason.
  - *A node pushed nothing of a group,* a sampler on its sampling-only links for one, takes the header
    from the block (`on_header_validated`).
  - *Consensus's partial columns also skip it* for a peer that has sent a message of the block, or that
    was sent the header on another topic. Sending it once per block and link, not per group, is for
    later study.
- **A bitmap's length** is the sender's, up to the bound. Bits past the group's count, once known, are
  the violation `protocol-v2.md` makes them (`valid_have`, `drop_beyond`).
- **A chunk's id** (`chunk_id`, `protocol-v2.md` §3) takes the part of `protocol.md` §2's structured
  id, which hashes a topic in, on a binding that has no topics. It is 59 bytes:
  - *the payload's chunk:* its `GroupId`, its index as a little-endian `uint32`, and the first 20 bytes
    of SHA-256 over the decompressed body;
  - *a cell:* one id whichever group carries it, so that a copy through the other axis, or one with a
    header, is the same chunk to `seen`. It is its column's `GroupId`, its row as the index, and the
    first 20 bytes of SHA-256 over the cell and its proof.
- **A chunk's size** (`wire_size(p, entry)`, `protocol-v2.md` §3) is its frame's on the stream (§1.5),
  with the header when its write carries one, so that the window counts what the link carries.

### 1.4 Compression

- **The two chunk kinds** (`0x06`, `0x07`) carry their SSZ compressed with snappy's block format, as
  gossip carries chunks and data columns. A partly filled blob's cells are mostly zeros.
- **The decompressed length,** which a snappy block states first, is checked against the kind's bound
  (§1.6) before decompressing.
- **The other kinds** carry their SSZ as it is: a few dozen bytes, mostly a key and a bitmap, which
  snappy would lengthen.

### 1.5 The stream's frames

On the standalone binding's stream, a frame is one encoded message after its length:

    frame := uvarint(len(kind || body)) || kind || body

- The length is libp2p's unsigned varint.
- Every frame §1.6 allows fits in at most 3 bytes of it.

### 1.6 Limits

Each kind has a bound on its body, from its types' static sizes (X6, limits before state):

| kind | the body's bound, uncompressed |
|---|---|
| JOIN, GRAFT, PRUNE | 17, 7, 6 (fixed) |
| HAVE, WANT | 1 064, 1 065 (a full bitmap) |
| CHUNK of the payload | 33 351 under design A (`MAX_SEGMENT_SIZE`, 14 proof steps, the descriptor's 51 bytes); 33 300 under design B, without the descriptor (`protocol.md` §1, open) |
| CHUNK of a cell | 199 091 (the header with `MAX_BLOB_COMMITMENTS_PER_BLOCK` commitments) |

- **On the stream,** a receiver reads a frame's length and kind, and refuses a frame that cannot fit
  its kind's bound before reading the body. A frame of an unknown kind is held to the largest known
  kind's room. For a chunk kind the frame may be the bound's snappy
  worst case, `32 + n + n / 6`. Its decompressed length is checked against the bound itself.
- **The epoch's own bound** on a cell's header, its `max_blobs_per_block` commitments, is checked at
  level 1, where consensus checks it.
- **`protocol-v2.md` §6.3's limits on state stay as they are:** groups tracked per slot, relations per
  link, and sampling-only links accepted.

### 1.7 Sizes (informative)

A message's size on the stream: its body, then its kind and its length.

| message | body | on the stream |
|---|---|---|
| JOIN | type 1, fork digest 4, interest 1, custody count 8, duty 1, colours 2 | 19 |
| GRAFT | type 1, family 2, colour 2, direction 1, answer 1 | 9 |
| PRUNE | type 1, family 2, colour 2, direction 1 | 8 |
| HAVE, holding or offer | group 35, flags 1, offset 4, bitmap b | 42 + b; 43 + b from b = 87 |
| WANT, one index i | group 35, flags 1, hops 1, offset 4, bitmap ⌊i/8⌋ + 1 | 44 + ⌊i/8⌋; 45 + ⌊i/8⌋ from i = 680 |
| CHUNK, a cell | group 35, index 4, cell 2 048, proof 48, offset 4; header (if sent) 4 + 340 + 48 a blob | 2 142; with a 48-blob header, 4 790 |
| CHUNK, the payload | `protocol.md`'s `Chunk`: 135 under design A (the descriptor's 51 bytes in it), 84 under design B, + 32 a proof step + data | 138 or 139 under design A, 86 to 88 under design B, + 32 a proof step + data |

A chunk's size is before compression.

### 1.8 In Waggle's framing

Waggle, libp2p's working draft of a pubsub protocol for incrementally reconstructed objects
(`/waggle/1.0`), is a transport:
- one stream per topic to each connected peer;
- one message, `ObjectPieces{objectID, piecesMetadata, pieces}`, whose fields are opaque;
- no mesh and no scoring.

The standalone binding can travel in it with every rule of its own, as on a stream of its own; only
the framing changes.

- **Topics are per object type, never per family.** A Waggle subscription is a stream to the node's
  connected peers, one per topic. With a topic per family, a sampler would subscribe to the families
  it samples and disclose them to every peer (I6). A topic per type says only that the node takes
  part in the type. What it receives is said per link, in its JOIN and its WANTs, and the group tells
  one family's chunks from another's.
- **JOIN** is the first message the node sends that peer on the type's topic. Waggle sends to a peer
  only on the stream of its subscription, so a link forms once both ends have subscribed and each has
  sent its JOIN.
- **Every message is one `ObjectPieces`, carrying one encoded message (§1.2):**
  - `objectID`: the `GroupId`'s 35 bytes, or for JOIN, GRAFT and PRUNE, which name no group, the one
    byte `0x00`;
  - `piecesMetadata`: the encoded message, for every message but a chunk; for a chunk, its kind byte
    alone;
  - `pieces`: a chunk's body, compressed as on the stream; empty otherwise.

  Waggle length-prefixes each `ObjectPieces` itself, so the encoded message carries no length. The
  bounds of §1.6 are checked once Waggle has read the `ObjectPieces`.
- **Whom a node pushes, tells and asks is `protocol-v2.md` §4's.** SEACAST's rules take the place of
  the draft's dissemination prose (a new piece to the peers whose metadata shows it missing, metadata
  to some others), which lets the application choose the peers ("latency or other
  application-defined criteria").
- **The urgent lane at the transport.** Where the framing keeps the messages without pieces on a
  stream of their own (a second stream, or a second topic per type), a holding, a claim or an
  acknowledgement no longer waits behind a chunk being written to the same peer, which one stream per
  peer, as gossipsub's, cannot give.
- **What it does not give:**
  - scoring, which the draft leaves to the application and the standalone binding has on its own
    messages (P7);
  - the fetch outside the links, whose transports are §5's.

Waggle's `ObjectPieces` has the shape of the extension binding's partial message: a group id, the
parts' metadata and the parts. So a client can move between the two changing mostly where the topic
lives.

## 2. Onto gossipsub with the Partial Messages Extension

The binding for columns while the extension is the deployed path. It keeps the rollout inside
existing topics.

- **What it gives up** (`protocol-v2.md` §7's capabilities):
  - interest without subscription, but for a sampler's (§4);
  - the push relation's floor and direction;
  - the answered GRAFT: it is accepted in silence;
  - scoring on SEACAST's own messages: gossipsub's applies.
- **The two ends of a relation agree through gossipsub's backoff.** With the GRAFT accepted in
  silence, what keeps the ends' views of a relation together is gossipsub's backoff after a PRUNE:
  each end holds it from a PRUNE it sends or receives, and refuses the peer's GRAFT within it.
  (`protocol-v2.md`'s own `PRUNE_BACKOFF`, held only by the end that receives a PRUNE and refusing
  no GRAFT, needs neither, since its GRAFT is answered.) The ends must be able to rely on it, so it
  must outlast the link's longest round trip at each end that may prune (`protocol-v2.md` §4.1's
  Rationale). With a shorter one, a GRAFT that crosses a PRUNE can reach its peer as the backoff
  ends and be accepted at that end alone; at exactly the round trip it turns on whether a GRAFT at
  the backoff's last instant is within it, which gossipsub does not say. With a longer one, the
  ends agree in every state at rest that `toy/graft_check.py --model` reaches (up to four upkeep
  steps per end; a bounded check, not a proof). A wait added to a node's own GRAFTs after the
  backoff does not cover it, since the disagreement comes from a GRAFT accepted. Gossipsub's
  recommended backoff of one minute meets the bound on any link whose round trip is shorter; this
  binding sets no backoff of its own.
- **What it depends on:** libp2p's Partial Messages Extension (libp2p specs, pull request 685), and
  consensus-specs' partial columns (`specs/fulu/partial-columns/p2p-interface.md`, and Gloas's of the
  same name). The partial message's group id is theirs, a version byte `0x00` and the block root,
  with the column from the topic.
- **The fork** is in the topic's name, as gossipsub's topics carry it.
- **The extension fields** it needs:
  - the JOIN's duty and `M`, beside the subscription;
  - a GRAFT's colour;
  - the WANT's `standing`, `hops` and `probe`, which also ask for the part where the asker has not
    subscribed (§4).

  Their bytes are the extension's to define, beside its own fields.
- **Gossipsub's IHAVE limits:** offers travel as `partsMetadata`, not as IHAVEs. Whether the extension
  limits them is not checked here (`protocol-v2.md` §4.3).
- **The mapping** is §0's table, middle column.

## 3. v0.3's wire

`protocol.md`'s wire (its §2): chunks as gossipsub messages, and holdings, offers and asks as
message-id strings inside existing control fields. Nothing here adds a protobuf field or a gossipsub
message type. The toy runs `protocol-v2.md` on it.

- **What it gives up** (`protocol-v2.md` §7's capabilities): the same as the extension binding (§2),
  and EVIDENCE.
- **The two ends of a relation** agree through gossipsub's backoff, as on the extension binding (§2).
- **The fork** is in the topic's name.
- **A chunk's id** is `protocol.md` §2's structured `message_id`.
- **An IDONTWANT's entries** are read as `protocol.md` §4.1 reads them. An IDONTWANT names no topic, so
  beside the `HaveBitmap`s its entries can be stock message ids, another topic's say. An entry that
  opens with `HaveBitmap`'s MAGIC and a version this wire writes (`protocol.md` §2's 1, which its
  `is_have_bitmap` tests, or the research harness's 4, below), and holds a group after them, and at
  version 4 the claims' flags byte, is a holding (`protocol-v2.md` §4.3's `on_holding`). Any other
  entry, one cut short included, is an opaque id, kept in
  `unwanted[p]` with stock gossipsub's admission and lifetime, where `on_want` reads it
  (`protocol-v2.md` §4.5); it is not read as a holding. Both are handled after the frame's asks, as
  `protocol-v2.md` §4's `on_frame` handles holdings.
- **An IHAVE's entries** are offers only as `HaveBitmap`s. Any other entry is ignored, without
  penalty, where `protocol.md` §4.4 reads it as a structured id: this draft offers by bitmap only.
- **The extra fields** are carried beside the bitmap or the index: a holding's `claim_all` and
  `complete`, and the WANT's `standing`, `hops` and `probe`. The toy charges no bytes for them. The
  research harness's Go path writes a flags byte after the root for the claims, and a flags byte and a
  hops byte for the WANT (43 bytes), under version 4 of the strings.
- **Gossipsub's IHAVE limits:** offers are IHAVEs, so a stock gossipsub client applies its own
  (`protocol-v2.md` §4.3).
- **The mapping** is §0's table, right column.

## 4. A sampler on gossipsub's wires

On both gossipsub bindings a JOIN is a subscription, and a subscription is announced to every peer. A
sampler's `(DECLARED, NONE)` therefore cannot be one:
- a subscription to the topic of a family it samples would disclose the sample to every peer (I6);
- and it would make the node a receiver of the whole family, pushed all of it.

A sampler subscribes to nothing for the families it only samples, and these rules make that work:

- **No JOIN on the wire.** The JOIN `(DECLARED, NONE)` that `send_join` sends writes nothing on
  these wires and counts as queued at once, so a sampler's links for a type are the peers from
  which it has received a subscription to one of the type's topics. A peer that has subscribed to
  none of a type's topics is read as `(DECLARED, NONE)` for that type: its WANTs are its interest
  and stand (`protocol-v2.md` §4.5), and nothing is pushed or offered to it; it receives only the
  answers to its WANTs. A node that subscribes to some of the type's topics, a custodian, samples
  another family through the WANT's `standing` flag, which every sampler sets (`protocol-v2.md`
  §4.10).
- **Answers admitted by their WANT.** A node accepts a chunk on a topic it has not subscribed to
  only as the answer to a WANT it sent: the group's chunk at that index, from the peer the WANT
  went to, until the group expires. Nothing else on such a topic is accepted, no other index and no
  other peer; a copy from a peer asked earlier is accepted and acknowledged like any duplicate
  (`protocol-v2.md` §4.10). A forwarder's own WANT for a routed request (`protocol-v2.md` §4.5,
  `route_want`) is admitted the same way, so a forwarder subscribes to nothing new either. Where a
  receive path drops a message on a topic the node has not subscribed to, the admission is an
  exception to that drop, and an admitted chunk is then checked and validated as any other.
- **On the extension binding** the extension ties `requestsPartial` to a subscription, so a peer
  could answer an asker that has not subscribed only with the full message. The WANT's extension
  field also asks for the part as a partial message, and the asker does not downscore a partial
  message it asked for this way as unrequested.

Rejected: approximating `DECLARED` interest by subscribing, either to the sampled families (the
disclosure above) or to every family of the type (every family pushed to the sampler). The
standalone binding needs none of this: its JOIN goes per link and names no sample
(`protocol-v2.md` §1.2).

## 5. A fetch outside the links: its transports

`protocol-v2.md` §7 defines the fetch: a WANT answered by a CHUNK from a node of the known node set
that is not a link, with its privacy rule. How it is carried is the binding's. The transports
considered:
- an ephemeral libp2p connection, short-lived and admitted above the peer limit (FullDAS's
  "libP2P-ephemeralConnect");
- plain UDP (PANDAS's one-hop requests to nodes in a crawled view);
- a fast QUIC connection;
- a discv5 request in a handshake of two round trips (FullDAS's "new primitive outside of the libp2p
  framework", implemented in its simulator).

Over a datagram, the standalone binding's encoded message (§1.2) needs no length prefix: the
datagram's boundary marks it.
