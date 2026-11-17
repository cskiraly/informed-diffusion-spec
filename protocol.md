# Informed Diffusion: the protocol in pseudocode

> **DRAFT v0.10.2, 2026-11-16.** Companion to the post [*Informed Diffusion: making home builders
> publish fast*](https://ethresear.ch/t/informed-diffusion-making-home-builders-publish-fast/26151). Field level on the wire; byte-exact layouts follow in a second phase. Written from
> the research implementation (Prysm and a go-libp2p-pubsub fork) and revised after a review
> against it; section 9 lists where the measured runs differ from what is written here.

## 0. How to read this

This document defines what a node does to diffuse an execution payload, one event at a time: what it
sends, what it checks, and what it does with each message it receives. It is written in Python-like
pseudocode, in the style of the consensus specs. Where a rule has code, the code is the
specification, and the prose says what it does and why. A rule that has no code is stated in the
prose and its tables: among them §2's table of what each bitmap means, §5.4's "When it runs", §7.3,
and §8's state, limits and helpers.

**How it is organized.**
- §1 to §3 define the payload's commitment and its code (§1), the messages on the wire (§2), and
  how a chunk and a group are validated (§3).
- §4 to §7 define what a node does: with each message it receives (§4), when it publishes and
  forwards (§5), when it asks for a chunk (§6), and how it sends, through a queue per peer and a
  window (§7).
- §8 lists the state a node keeps and for how long, its limits and its constants.
- §9 lists where the research implementation, on which the measurements ran, differs from this
  document.

**What is normative.** Sections 1 to 3 are the consensus-side and wire definitions that both ends
must agree on. Sections 4 to 7 combine each node's local scheduling with the meaning of the messages
it exchanges: what a HAVE, an ask, a decode claim and an acknowledgement promise. A client may
schedule differently without breaking interoperability, provided those meanings hold. The
measurements are of the scheduling written here. Of §8.3's constants, only the limits are shared by
every node; a node sets the others itself, the bounds within what §8.3 states.

**Reading it.** An implementer can read §1 to §7 in order, with §8 at hand for the state, limits and
constants each section uses. Where a section has code, its prose says what the code does, a rule to
a paragraph. A section with reasoning to give ends with an unnumbered *Rationale*: why its rules are
as they are, and the alternatives that were not taken, with the reason for each. A paragraph that
opens with **Open:** names a question this version leaves open. The constants (`PROMISE`) are listed
in §8.3, with their values and the reasons for them, and the limits a client sets in §8.2. `R_NODE`
(§5.2) and `W` (§7.1) are defined where they are used, `UPLINK` is the node's configured uplink
(§5.1), and `CANCEL`, `RAREST`, `PROJECT` and `PACED` switch cards 8, 9, 12 and 15 on, and
`DESCRIPTOR_IN_CHUNK` design A (§1). The glossary at the end defines the document's terms.
Measurements are reported in the documents below, and §9 says which code they ran.

**Tiers and cards.** The document covers every tier, because the tiers are nested. A tier is the set
of cards it enables:

| tier | cards | in one line |
|---|---|---|
| 1 | 1, 2 | segments with a bid commitment, batch publishing |
| 2 | + 3, 4, 5 | announce instead of push, the phase, disciplined pulls |
| 3 | + 6 | the erasure code over the compressed payload, stop-pull |
| 4 | + 7–17 | HAVE bitmaps, cancel, rarest at pop, decode claim and repair, r = 2, projection, striped publishing, the static window, paced gossip, furthest behind first, push by uplink class |

One rule carries the tag [P4] instead of a card: it is there for the source's privacy, not for
speed or bytes (§5.1).

**Card tags.** A comment such as `# [c8]` marks the line or block that implements card 8. A tag
says which mechanism is responsible; it is not a deletion instruction, and deleting a tagged line
does not always leave a working protocol. What a node does without a card:

| card | without it |
|---|---|
| 3 | every mesh peer is pushed every chunk (the budget is D); nothing is announced on forwarding |
| 4 | the budget is R, whatever the holders |
| 5 | stock IWANT handling: every announcer is asked, with no window, offer table or park |
| 6 | no code: N = K, completion needs every chunk, and there is no stop-pull |
| 7 | per-id IDONTWANT and IHAVE, asks by full id; cards 8, 9, 10, 12 and 16 lose their input, and card 14 its acknowledgement |
| 8 | the writer sends a queued chunk even if the peer has since said it holds it |
| 9 | the writer sends its queue in order |
| 10 | a decoded node claims only the chunks it received, keeps receiving the rest, and pushes none of the chunks it rebuilt |
| 11 | R = 3 at 1 MiB, the uncoded schedule |
| 12 | no push is skipped by projection |
| 13 | the source's push candidates are its mesh peers, whatever its uplink |
| 14 | no window: the writer hands chunks to the transport as fast as it takes them, and sends no acknowledgements; card 16's guard keeps its evidence, the HAVEs mesh peers send (card 7) |
| 15 | heartbeat gossip goes out at once to every sampled peer |
| 16 | push targets in the order of the tie-break alone, a rank that differs per chunk |
| 17 | `R_NODE = R` for every node |

**The code runs as written.** [`toy/`](toy/) executes every block of this document, once per node,
on a simulated network. It shows that the document is complete enough to run; its numbers are not
measurements.

**Related documents**, with the short names used below:
- [Wen fast payload broadcast? Segment, code, push, pull, and everything in between](https://ethresear.ch/t/wen-fast-payload-broadcast-segment-code-push-pull-and-everything-in-between/25913)
  (*Segment, code, push-pull*, 2026): the design space, the commitment and the forwarding rules;
- [EIP-8411: what segmented payload diffusion is made of](https://ethresear.ch/t/eip-8411-what-segmented-payload-diffusion-is-made-of/26025)
  (*What segmented payload diffusion is made of*, 2026): tiers 1 to 3, cards 0 to 6;
- [*Informed Diffusion: making home builders publish fast*](https://ethresear.ch/t/informed-diffusion-making-home-builders-publish-fast/26151) (*Informed Diffusion*, 2026):
  tier 4 and the design as a whole;
- [Segmented payload diffusion, card by card](https://notes.ethereum.org/@cskiraly/segmented-stack-cards)
  (2026): each card in prose, with what it costs and when it matters;
- [Who decides that a payload is revealed?](https://notes.ethereum.org/@cskiraly/eip-8411-envelope-signature)
  (2026): how the envelope's signature travels;
- [*What a forwarding node checks, and when it decodes*](https://notes.ethereum.org/@cskiraly/informed-diffusion-decoding) (2026): the validation levels, when the
  decode claim goes out, and what a node does with the chunks it rebuilds.

**What is assumed and not restated.** Gossipsub v1.2 as specified: the mesh and its maintenance
(D = 8, Dlo = 6, Dhi = 12), GRAFT and PRUNE, the heartbeat (700 ms, as Prysm sets it), the message
cache (6 heartbeats, gossip from the newest 3), IHAVE, IWANT and IDONTWANT, the seen cache, and peer
scoring. Only what changes is written out. That includes what a node does at gossipsub's two IHAVE
limits: an IHAVE over either is recorded, and its asks wait for the next heartbeat, where stock
gossipsub ignores it (§4.4, §8.2). Messages are unsigned and carry no author, as Prysm publishes
them.

**Scope.** Every peer on the payload's topic is assumed to run this protocol. A stock peer would
misread the bitmaps (§2), so a network in which only some nodes support segmentation needs more
than is written here, and is left out.

## 1. The payload, the code and the commitment [c1, c6]

What is segmented is the SSZ container of what the builder holds at bid time,
`ExecutionPayloadSegmentBody{payload, execution_requests}`, as *Segment, code, push-pull* (2026)
specifies. The unsigned envelope is rebuilt from it and the block. The envelope's signature cannot be
rebuilt: it travels on its own, with the roots needed to check it, as *Who decides that a payload is
revealed?* (2026) recommends (its option A).

The builder cuts the body into chunks, which form a *group*, and describes the group in a
descriptor that its bid commits to:

```python
UNIT = 16 * 1024                # target segment size, uncompressed               [c1]
MAX_CHUNKS = 256                # codec limit on data + parity chunks             [c6]
MAX_PLAIN_CHUNKS = 8192         # every group fits one HAVE bitmap (§2)           [c1]
MAX_SEGMENT_SIZE = 32 * 1024    # above snappy's worst case at the default UNIT   [c1]

class SegmentDescriptor(Container):     # committed in the bid                    [c1]
    version: uint8          # 2 = coded (compress first, then Reed–Solomon); 1 = plain
    hash_id: uint8          # 0 = SHA-256
    encoding: uint8         # 1 = snappy block compression applied before coding [c6]
    count: uint32           # N: chunks in the group (data + parity)
    segment_size: uint32    # bytes per chunk (the last data chunk may be shorter)
    total_length: uint64    # length of the segmented byte string
    root: Bytes32           # Merkle root over the N chunks

def group_id(d: SegmentDescriptor) -> Bytes32:
    return sha256(b"\x02" + serialize(d))

def group_key(gid: Bytes32, slot: Slot) -> Bytes32:     # the group's name in diffusion: a group id
    return sha256(b"\x03" + gid + uint64_le(slot))      #   committed at a slot (below)

def K(d) -> int: return ceil(d.total_length / d.segment_size)     # data chunks
def N(d) -> int: return d.count

def segment_length(d, i) -> int:
    if i == K(d) - 1: return d.total_length - (K(d) - 1) * d.segment_size   # the last data chunk
    return d.segment_size                                                   # data and parity

def valid_descriptor(d) -> bool:         # checked before any state is allocated for the group
    if d.hash_id != 0 or d.segment_size == 0 or d.segment_size > MAX_SEGMENT_SIZE: return False
    if d.total_length == 0: return False
    if d.version == 2: return d.encoding == 1 and d.count == 2 * K(d) <= MAX_CHUNKS
    if d.version == 1: return d.encoding == 0 and d.count == K(d) <= MAX_PLAIN_CHUNKS
    return False
```

**The bid.** This proposal adds one field to Gloas's `ExecutionPayloadBid`: either the group id of
the payload's descriptor, `execution_payload_segment_group_id` (design A below), or the descriptor
itself, `execution_payload_segment_descriptor` (design B). Neither exists in the Gloas baseline.
Every chunk is then authenticated through the block that carries the bid: installed block → bid →
descriptor → Merkle proof → chunk.

**The group's key.** In diffusion, a group is a descriptor committed at a slot, and it is named by
its key, `group_key(group_id(d), slot)`. Chunks, their ids, HAVEs and asks all carry the key (§2).
Every node derives the key from an installed block: from the group id its bid commits, and the
block's slot. So a bid of a later slot that commits the same descriptor names another group, and a
group's slot is fixed by its name (§8.1). Two blocks of one slot whose bids commit the same
descriptor share the key, and their chunks are one group.

**Open: getting the descriptor.** A receiver needs the descriptor itself to check a chunk's proof;
the group id is only its hash. Two designs work, and the choice is not made:
- **A, descriptor in the chunk:** every chunk carries the descriptor, and the receiver checks its
  hash against the bid's group id (the measured implementation does this).
- **B, descriptor in the bid:** the bid carries the descriptor itself instead of its hash, and
  chunks carry only the key.

Section 3 is written for either. What the choice decides is in the Rationale below.

The builder makes the group at bid time:

```python
class Shard(Container):                  # a chunk's content, before it has a block to name
    index: uint32
    proof: List[Bytes32, 14]
    data: bytes

def build_group(body: bytes) -> Tuple[SegmentDescriptor, List[Shard]]:     # at bid time
    K = ceil(len(body) / UNIT)                                   # data chunks      [c1]
    coded = 2 * K <= MAX_CHUNKS                                  #                  [c6]
    data = snappy_block_encode(body) if coded else body          # compress first   [c6]
    size = ceil(len(data) / K)
    segs = [data[i*size:(i+1)*size] for i in range(K)]           # the last may be short
    parity = rs_parity(pad_each(segs, size), K) if coded else [] # K parity chunks  [c6]
    leaves = segs + parity
    d = SegmentDescriptor(version=2 if coded else 1, hash_id=0, encoding=1 if coded else 0,
                          count=len(leaves), segment_size=size, total_length=len(data),
                          root=merkle_root(leaves))
    return d, [Shard(index=i, proof=merkle_proof(leaves, i), data=leaves[i])
               for i in range(len(leaves))]
```

- **The code** [c6]: systematic Reed–Solomon over GF(2⁸) (polynomial 0x11d), with evaluation points
  0..N−1. Chunks 0..K−1 are the compressed bytes themselves and K..N−1 are parity, so any K distinct
  chunks rebuild the payload. At 1 MiB and the default `UNIT` this gives K = 64 and N = 128, chunks
  of about 12 KB.
- **The tree** [c1]: leaves `sha256(0x00 ‖ chunk data)`, nodes `sha256(0x01 ‖ left ‖ right)`,
  padded to a power of two with zero digests. A proof is log₂ of that width: 7 digests at N = 128.
- **Decoding** is the second level of validation (§3): take any K chunks, recover the data chunks,
  re-encode the parity, rebuild the tree, and require the committed root.
- **The cut** [c1]: `UNIT` is the builder's (§8.3). It sets K, and so whether the group fits the
  code. Receivers check the group a cut gives, as §3 does any group, and not `UNIT`: its descriptor
  passes `valid_descriptor`, or every chunk of the group fails level 1 (§3). Not every `UNIT` gives
  a valid group. A large one can give chunks above `MAX_SEGMENT_SIZE`. A small one can give a large
  payload more chunks than `MAX_PLAIN_CHUNKS`, or leave a coded group's last data chunks empty where
  the payload compresses well, so that its count is not twice the K a receiver derives. At the
  default `UNIT` none of these happens to a body of up to 128 MiB.

### Rationale

**The slot in the group's key.** An honest builder never commits one descriptor at two slots, since
the payload carries its slot's timestamp. A dishonest one could. With the slot in the key, its
commitment at a later slot names a new group, so it cannot make a group that has expired live again.

**Where the descriptor travels.** The choice between design A, the descriptor in the chunk, and
design B, the descriptor in the bid (open above), decides the four things below. It does not decide
when a chunk is accepted: under either design only the installed block's bid says which group is
committed, so a copy waits for its block in both (§3, §4.2).

*When a node knows a group's shape.* The descriptor gives the group's chunk count, the chunks' size
and the code. Every limit set by a group's count (on bitmaps, ids and ties: §2, §4.2, §4.4, §8.2)
holds once a node has the descriptor; before, the same limits use `MAX_PLAIN_CHUNKS`, what any group
can have. This document's code gives a receiver the descriptor when the group's first chunk passes
level 1, under either design (`open_group`, §4.2), and the source has it from `publish` (§5.1).
Under B the installed block's bid holds the descriptor, so a node could apply these limits from the
installation, without waiting for any of the group's chunks. Under A it could apply them from the
group's first copy, even one that waits for its block, once that copy's descriptor is checked
against the key it names (below).

*What a copy shows before its block.* Under A a copy carries the descriptor, and an honest copy's
key is that descriptor's hash at the copy's slot (`group_key`). A node could therefore check a copy
that waits: its descriptor against its key, and its index, length and proof against its descriptor.
These checks do not authenticate: a group made up whole passes them, and only the block tells it
apart. Under B a copy that waits carries nothing to check it against. This document's level 1 does
none of this before the block (§3).

*What the bid fixes.* Either design adds one field to the bid (above). Under A it is a 32-byte group
id whatever the descriptor holds: a field added to the descriptor later changes `Chunk`, which
carries the descriptor (§2), and not the bid's layout. Under B the descriptor's layout is part of
the bid's, so a field added to it changes `ExecutionPayloadBid`, a consensus container, and no
chunk. Under both it changes what `group_id` hashes, and so the groups' keys, and every node needs
the new layout (§0).

*What a chunk carries.* Under A each of the group's N chunks carries the descriptor, 51 bytes as
serialized (§2). Under B no chunk carries it, and each bid that commits the group carries its 51
bytes in place of the 32-byte group id. At these chunk sizes the bytes do not decide it: 51 bytes
against a chunk of about 12 KB, at 1 MiB and the default `UNIT`, is under half a percent, and the
share grows as chunks get smaller.

## 2. The wire [c1, c7]

Nothing here adds a protobuf field or a control type. Chunks travel as gossipsub messages on one
topic, and the bitmaps as message-id strings inside existing control fields. A *frame* is one
gossipsub `RPC`: the protobuf a peer writes on its stream, with the messages and control fields it
carries. It is not a frame of the layers below, QUIC's or a stream multiplexer's.

```python
class Chunk(Container):                 # gossipsub Message.data, snappy-compressed SSZ   [c1]
    slot: Slot
    beacon_block_root: Root             # the block whose bid commits this group
    group: Bytes32                      # the group's key (§1): the bid's group id, at this slot
    descriptor: SegmentDescriptor       # design A only (section 1)
    index: uint32
    proof: List[Bytes32, 14]
    data: ByteList[MAX_SEGMENT_SIZE]

def message_id(f: Chunk) -> bytes:                          # structured id      [c1]
    return f.group + uint32_le(f.index) + content_id(f)     # 32 + 4 + 20 bytes
```

**The message id** of a chunk is structured (`message_id`): the group's key, the chunk's index, and
its content id. The content id is the 20-byte message id of the Altair networking rules, computed
over the topic and the decompressed chunk. A chunk that decodes gets the 56-byte structured id,
which is itself a change to the Altair rule for this topic. If bounded decompression or the chunk's
decoding fails, the message gets the inherited Altair id, with no prefix, and is rejected before
any group state is created. The topic's name and type mapping are left to the byte-exact phase.

**HAVE bitmaps** [c7]. One bitmap per group replaces per-id control messages. Its meaning is set by
the control field that carries it:

```python
MAX_HAVE_BYTES = 1024                   # 8192 indices: MAX_PLAIN_CHUNKS

class HaveBitmap(Container):            # carried as one message-id string   [c7]
    MAGIC = b"HAVE"                     # the string opens with MAGIC, then VERSION as a uint8
    VERSION = 1
    group: Bytes32
    bits: ByteList[MAX_HAVE_BYTES]      # bit i = chunk index i; trailing zero bytes dropped

class WantIndex(Container):             # an ask by index, in IWANT          [c7]
    MAGIC = b"WANT"
    VERSION = 1
    group: Bytes32
    index: uint32
```

Both are built by field name, `HaveBitmap(group=g, bits=b)`; `MAGIC` and `VERSION` are fixed by the
type, not passed. Their `group` is the group's key, as a chunk's is (§1).

| carried in | means | sent when |
|---|---|---|
| IDONTWANT | "I hold these chunks": always the sender's whole current bitmap for the group, so the receiver ORs it in and order does not matter | on every new chunk that passes level 1, to the mesh and to the chunk's sender (§4.2); by the source before its data (§5.1); on decode, all N bits (§4.6) |
| IHAVE | "I can send you these": exactly the chunks the announcement names, minus what the sender pushed you and what you told it you hold; never empty | announce instead of push (§5.2); heartbeat gossip (§6.4) |
| IWANT, as `WantIndex` | "send me chunk `index`": used when the asker does not know the chunk's full id | §6.1 |

A bitmap that names an index at or beyond its group's N, once the descriptor is known, is a
protocol violation.

Without card 7, the same information travels as ordinary per-id IDONTWANT and IHAVE, and asks use
the full message id.

### Rationale

**A structured id.** It lets a receiver match an announcement to a group and an index before it
holds the chunk, and match both to a bid once its block is installed. The content id is computed
over the decompressed chunk, so different snappy encodings of one chunk share an id, and different
contents claiming one index do not.

**What a stock peer would see.** The protobuf schema is unchanged, but the meaning is not. A stock
peer takes a bitmap in an IDONTWANT for an id that matches nothing, which is harmless. A bitmap in an
IHAVE it takes for an ordinary id: it asks for it, and counts the unanswered ask as a broken
promise. Hence the scope of §0: every peer on the topic runs this protocol.

## 3. Validation: three levels, and what each gates [c1, c6, c10]

A node cannot validate a payload before it forwards pieces of it; that is where the speed comes
from. Validation therefore comes in three levels, and only the first fits a chunk.

**Level 1, per chunk: authenticity.** The chunk is the committed piece at its index:

```python
def validate_chunk(f: Chunk) -> Result:
    block = installed_block(f.slot, f.beacon_block_root)    # validated and applied locally
    if block is None:
        return DEFER                    # held in a bounded store (§8.2); not claimed, not forwarded
    if f.slot != block.slot: return REJECT                  # the slot a copy names is its block's (§1)
    d = committed_descriptor(block, f)
    if d is None or group_key(group_id(d), block.slot) != f.group or not valid_descriptor(d): return REJECT
    if f.index >= d.count: return REJECT
    if len(f.data) != segment_length(d, f.index): return REJECT
    if not verify_merkle_proof(d.root, f.data, f.index, d.count, f.proof): return REJECT
    return ACCEPT

def committed_descriptor(block, f: Chunk) -> Optional[SegmentDescriptor]:
    bid = block.body.signed_execution_payload_bid.message
    if DESCRIPTOR_IN_CHUNK:                                         # design A
        ok = group_id(f.descriptor) == bid.execution_payload_segment_group_id
        return f.descriptor if ok else None
    return bid.execution_payload_segment_descriptor                 # design B
```

Level 1 costs a Merkle proof, so every node runs it before it claims, forwards or serves a chunk. A
chunk that fails it is the fault of the peer that sent it, and counts against that peer. A chunk
whose block is not installed yet is neither accepted nor rejected: it waits for the block (§4.2).

**Level 2, per group, after any K chunks: the code's consistency.** Decode, re-encode the parity,
rebuild the tree, and require the root (§4.6). Only the builder can fail it, and then it fails at
every node. A node pushes or serves the chunks it rebuilt, and delivers the payload, only after this
check passes. It claims them at K, before the check (§4.6).

**Level 3, per message: the application's checks** on the reassembled payload and its envelope: the
builder's signature (which arrives on its own and can be checked as soon as the block is installed),
the payload against the bid, then execution. A chunk carries nothing these could check: with
compression before coding, a chunk is not even a parseable fragment.

**What each level gates.**
- Level 1 gates everything a node does with a chunk: holding it, claiming it, forwarding it, serving
  it, counting it toward K.
- Level 2 gates delivery and every chunk the node rebuilt. The decode claim goes out at K, before
  it (§4.6).
- Level 3 gates what consensus consumes: fork choice, the payload timeliness vote, import. It gates
  nothing in diffusion: forwarding never waits for it.
- When level 2 or 3 fails, the node drops the group (§4.6): it stops forwarding, answering and
  pushing it, and retracts nothing. A payload that fails level 2 or 3 never counts against the
  nodes that forwarded its chunks.

**Gated forwarding.** These rules are from *Segment, code, push-pull* (2026), which calls the first
one non-relay.
- **Do not forward a chunk whose block is not installed.** Deferred chunks wait in a bounded store
  with per-peer reservations, and are validated when the block installs, or dropped when their slot
  leaves the live window (§4.2, §8.1). A copy that waits, kept or refused, ties its sender to the
  root it names, and that root's installation makes the sender an offer of the index (§4.2).
- **A receiver does not ask for what it cannot yet authenticate** (§4.4). The announcements it
  receives meanwhile stay in the offer table, its ledger, and are asked for when the block installs
  (§4.2).
- **Push only with evidence the peer holds the block.** Mesh membership is not such evidence.

**Open: the evidence for a push.** How a node gets evidence that a peer holds the block, for its
mesh and for the wider set striped publishing reaches (card 13), is open. The push selectors of
section 5 do not apply this rule: they are the measured policy.

### Rationale

**The decode claim before level 2.** Only the builder can fail level 2, and then it fails at every
node, so a claim made at K can only be wrong about a group that every node drops. What a node
claimed of such a group were authentic pieces, so it has nothing to retract.

**What bounds the damage: the builder's cost.** A chunk authenticates only against the bid an
installed beacon block carries, so at most one payload per winning bid crosses the network: one per
block. Chunks committed to a losing bid never validate. Under Gloas, a bid's pending payment that
reaches the same-slot attestation quorum is queued for withdrawal whether or not its payload ever
arrives: if it is not settled earlier, at the end of the epoch after the bid's. A builder that
commits to an invalid payload therefore pays for the slot and gets nothing for it. One case moves
the cost: a proposer that signs a second block for the slot is slashed, and the slashing clears that
slot's pending payment. The nodes that forwarded the payload could not have known it was invalid,
which is why it never counts against them.

**No ask before the block.** An answer could not be checked before the block is installed anyway:
asked for early, it would wait in the deferred store, a provider's answer spent on a copy that
cannot be checked yet.

## 4. Receiving

### 4.1 The order of handling

A node handles each frame from a peer in a fixed order: its chunks, its IHAVEs, its IWANTs, GRAFT
and PRUNE, and its HAVEs last. It then sends one response.

```python
def on_frame(p, frame):
    for f in frame.chunks: on_chunk(p, f)                     # §4.2
    asks = on_ihave(p, frame.ihave)                            # §4.4
    answers = on_iwant(p, frame.iwant)                         # §4.5
    prunes = handle_graft_prune(p, frame)                      # stock
    for h in frame.idontwant: on_have(p, h)                    # §4.3 (stock ids go to unwanted[p])
    respond(p, asks, answers, prunes)

def respond(p, asks, answers, prunes):                         # one response per frame handled
    control = IWANT(asks) + PRUNE(prunes) if asks or prunes else None   # an empty part is left out
    if not answers:
        if control: enqueue(p, Entry(control=control), urgent=False)
        return                                                 # nothing to ask, answer or prune
    for k, f in enumerate(answers):                            # one chunk per entry; the control
        e = Entry(chunk=f, solicited=True, control=control if k == 0 else None)    # rides on the first
        if not enqueue(p, e, urgent=False):                    # refused by a full queue: owed, and
            owed_answers[p][f.group].set(f.index)              #   queued once there is room (§7.2)
```

So an ask and a HAVE in the same frame are handled ask first, and the asks and answers one frame
produces leave together, the control riding on the first answer. An answer that a full queue
refuses is owed: the writer queues it once there is room (§7.2), so the queue cannot turn an honest
answer into the asker's broken promise. Validation (§3) runs off this path, on the router's event
loop, like block installation; a chunk's handling continues when its result is known.

### 4.2 A chunk arrives

```python
def on_chunk(p, f):
    mid = message_id(f)
    if seen(mid) or mid in pending_ids:              # a duplicate, a chunk rejected before, or one waiting
        if accepted(mid): send_have(p, f.group)      # [c14] duplicates are acknowledged too
        elif mid in pending_ids: tie(p, f)           # another copy of one that waits: its sender too
        return
    if expired(f.group) or not live(f.slot): return  # past its lifetime or live window (§8.1): ignored
    on_validated(p, f, validate_chunk(f))            # level 1 (§3)

def on_validated(p, f, result):
    if expired(f.group) or not live(f.slot): return  # expired or out of the window meanwhile (§8.1)
    if result == DEFER: return defer(p, f)           # ahead of its block: not claimed, not forwarded
    mark_seen(message_id(f))                         # accepted or rejected: never validated again
    if result == REJECT: return penalise(p)          # level 1 failures are the sender's (§3)
    g, i = f.group, f.index
    if g not in desc:
        open_group(g, f)                             # desc[g] from the bid; state[g] = COLLECTING
        drop_beyond(g)                               # what named an index it has not goes (§8.2)
    if state[g] == INVALID: return                   # a dropped group (§4.6)
    if received[g].has(i): return send_have(p, g)    # a second copy of a chunk we received: acknowledge
    store(g, i, f); received[g].set(i)               # also records known_id[g][i] = message_id(f)
    close_promises(g, i)                             # [c5] the chunk arrived, from anyone
    claim = not mine[g].has(i)                       # not yet claimed (decoded nodes claimed everything)
    if claim: mine[g].set(i)                         # [c7] only chunks that passed level 1
    for q in (mesh | {p}) if claim else {p}:
        send_have(q, g)                              # [c7] the claim to the mesh, and [c14] the sender's ack
    forward(f, p)                                    # §5.2: forwarding never waits for levels 2 and 3
    if state[g] == COLLECTING and popcount(received[g]) >= K(desc[g]):
        state[g] = DECODING                          # once per group
        claim_group(g)                               # [c10] the decode claim, at K (§4.6)
        start(decode_group, g)                       # level 2, off the chunk path, for as long as a
                                                     #   decode takes (§8.1)

def defer(p, f):                                     # on the router's event loop, like installation
    if installed_block(f.slot, f.beacon_block_root):           # installed in the meantime
        return on_validated(p, f, validate_chunk(f))
    if not admitted(p, f): return                    # a group beyond the peer's unknown groups (§8.2):
                                                     #   ignored, neither kept nor tied
    tie(p, f)                                        # kept or refused, its sender is tied to the root
    if reserve(p, f):                                # a per-peer reservation in a bounded store (§8.2)
        pending[f.beacon_block_root].append((p, f))
        pending_ids.add(message_id(f))
    # refused: the copy is not kept, so a later copy is evaluated afresh; its sender stays tied

def tie(p, f):                                       # a copy that cannot be checked yet ties its
    if expired(f.group) or not live(f.slot): return  #   sender to the root it names, per connection
    if not admitted(p, f) or not tie_room(p, f):     #   and group, within its lifetime and window
        return                                       #   and §8.2's limits on ties
    tied[f.beacon_block_root][p][f.group].set(f.index)
    tie_slot.setdefault((f.beacon_block_root, p), f.slot)      # the slot p's first copy named: when its
                                                     #   ties to the root leave the live window (§8.1)
    close_promises(f.group, f.index, of=p)           # p answered: its promise for the index closes

def tie_room(p, f):                                  # §8.2's limits on ties, per connection:
    if f.index >= MAX_PLAIN_CHUNKS: return False     #   an index no group has,
    if f.group in desc and f.index >= N(desc[f.group]): return False   # or this group has not;
    if f.group in tied[f.beacon_block_root][p]: return True            # a root and group tied for p already,
    return sum(len(t[p]) for t in tied.values()) < MAX_PENDING_GROUPS  #   or room for another

def tied_to_root(p, a):                              # p is not asked for a while its copy waits
    return any(t[p][group(a)].has(index(a)) for t in tied.values())

def on_block_installed(root):                        # resumes level 1
    for p, f in pending.pop(root, []):
        pending_ids.discard(message_id(f)); release(p, f)      # the reservation goes back
        on_validated(p, f, validate_chunk(f))
    g0 = bid_group(root)                             # the group this root's bid commits
    for p, groups in tied.pop(root, {}).items():     # the copies that waited for this root
        tie_slot.pop((root, p), None)
        for g, bits in groups.items():
            if expired(g): continue                  # its offers went with its lifetime (§8.1)
            if g != g0:                              # a copy naming a group its root does not commit
                drop_tie(p, g, bits); continue       #   is a forgery: nothing is released
            park[p].pop(g, None)                     # the senders' parks for the group lift,
            for i in bits:
                asked_parked[(g, i)].discard(p)      #   their last-resort counts per index clear,
                if g in desc and i >= N(desc[g]):    #   an index the group, known now, has not
                    continue                         #   is dropped (§8.2), the others kept,
                if not mine[g].has(i):               #   and each is an offer of its index again
                    add_offer(WantIndex(group=g, index=i), p)
    for a in ledger(g0):                             # what was announced meanwhile (§4.4), and what
        retry_offer(a)                               #   the ties released, is asked for now

def drop_tie(p, g, bits):                            # a tie its root does not release: a mismatch,
    for i in bits:                                   #   or its slot left the live window (§8.1)
        drop_offer(g, i, p)                          #   p's offers of these indices go, with its
        if authenticable(g):                         #   asks of them (§6.1), and the recovery goes
            retry_offer(WantIndex(group=g, index=i)) #   on without p (else the ledger asks at
                                                     #   installation)

def drop_stale_waits():                              # at each heartbeat (§6.4): what waits for a root
    for root in list(pending):                       #   not installed, past its group's lifetime or
        for p, f in [(p, f) for p, f in pending[root] if expired(f.group) or not live(f.slot)]:
            pending[root].remove((p, f))             #   its slot's live window (§8.1): a kept copy
            pending_ids.discard(message_id(f)); release(p, f)  # goes, its reservation back,
        if not pending[root]: del pending[root]
    for (root, p), s in list(tie_slot.items()):      # and a tie, by the slot its sender's first copy
        groups = tied[root][p]                       #   named, goes through drop_tie: the sender's
        for g in [g for g in groups if expired(g) or not live(s)]:     # offers and asks of those
            drop_tie(p, g, groups.pop(g))            #   indices with it (§6.1)
        if not groups:                               # nothing left of p under the root
            tied[root].pop(p, None); tie_slot.pop((root, p), None)
            if not tied[root]: tied.pop(root, None)

def drop_beyond(g):                                  # g's count is known now: what named an index it
    n = N(desc[g])                                   #   has not, while the count was unknown, goes (§8.2)
    idx = {i for q in list(offered) for i in offered[q][g] if i >= n}
    idx |= {index(a) for t in (offers, tried, asked_at) for a in list(t) if group(a) == g and index(a) >= n}
    for i in sorted(idx):                            # an offer of it, an ask of it still queued, a
        for q in list(queue): drop_offer(g, i, q)    #   promise, a try, a last-resort count, under every key
        close_promises(g, i)
    for root, peers in list(tied.items()):           # and a tie of it: a copy that names it can only
        for q, groups in list(peers.items()):        #   be rejected when its block installs
            bits = groups.get(g)
            if bits is None: continue
            for i in [i for i in bits if i >= n]: bits.clear(i)
            if not bits: groups.pop(g)

def send_have(p, g):                                 # [c7] always the whole bitmap, as it is now
    enqueue(p, IDONTWANT(HaveBitmap(group=g, bits=have_bits(g))), urgent=True)

def have_bits(g):                                    # what our HAVE says of g: what we hold, or, for a
    return (origin[g] if g in origin else mine[g]).copy()      # group we publish, what is acknowledged (§5.1) [P4]
```

**The path of a chunk** (`on_chunk`, `on_validated`). A copy of a chunk the node stored before is
acknowledged. A copy of any other chunk it has seen is ignored: one it rejected, or one that passed
level 1 and was not stored (a second copy of an index under another id, or a chunk of a dropped
group). Another copy of one that waits for its block ties its sender too (below). None of them goes
further. A chunk of an expired group, or whose slot is
outside the live window, is ignored (§8.1). Any other chunk goes through level 1 (§3), and is ignored
if, meanwhile, its group expired or its slot left the live window. A chunk that waits for its block
is deferred (`defer`, below). Otherwise the chunk is marked seen, accepted or rejected, and is never
validated again; one that fails level 1 counts against its sender. A chunk that passes opens its
group if it is the group's first (below). It is ignored if the group was dropped (§4.6), and only
acknowledged if the node received that index already. Otherwise it is stored, and closes every
promise for its index (§6.1). The node claims it unless it had claimed it already (a decoded node
has claimed every chunk), sends its HAVE to the mesh if it claimed the chunk, and to the sender in
any case, as the acknowledgement (§7.1), and forwards the chunk (§5.2). At the K-th chunk received
it claims the group and starts decoding (§4.6).

**A node claims a chunk once its proof checks**: its HAVE names the chunk only then, not on arrival
as stock IDONTWANT does. A chunk that arrives ahead of its block is claimed only when the block
installs. Until then its senders may keep pushing it, and their window slots stay held (§7.1).

**A copy that waits ties its sender** (`tie`) to the root it names, for its index, whether the
deferred store keeps the copy or refuses it, within §8.2's limits on ties (`tie_room`). A copy of a
group beyond the sender's limit of unknown groups is ignored, as its HAVEs and offers of that group
are: neither kept nor tied (`defer`). The sender's promise for the index closes, since it answered,
with a copy that cannot be checked yet, and it is not asked for the index again until that root
installs (`tied_to_root`: §4.4, §6.1, §7.2).

**The block's installation** (`on_block_installed`) resumes level 1 for the copies that waited for
its root, and releases the root's ties for the group its bid commits: each tied sender's park for the
group lifts, its last-resort counts for those indices clear, and it becomes an offer of each index
again, asked for with the rest of the ledger if the node still wants it. An index the group does not
have, known by then, is dropped (§8.2). An installation releases its own root's ties once.

**A tie that is not released.** The group and root a copy names are its sender's claim, unchecked
until the block installs. A tie whose root's bid commits another group is a forgery: it is dropped
with its sender's offers of those indices and its asks of them (`drop_tie`, §6.1), and the recovery
goes on without the sender. So is a tie whose slot leaves the live window. At each heartbeat
(`drop_stale_waits`, §6.4) the node also drops the copies that wait past their group's lifetime or
their slot's live window, and gives their reservations back.

**The group's count becomes known** at the group's first valid chunk. Then every offer, ask and tie
of an index beyond it, made while it was unknown, goes (`drop_beyond`), so the node never asks for a
chunk that cannot exist.

Without card 7 the node sends the stock IDONTWANT for `mid` to its mesh, and no acknowledgement goes
back to the sender.

#### Rationale

**A held index, not a held id.** A node claims a chunk once its proof checks because a held index is
stronger evidence than a held id: it covers any chunk claiming that index. Not evaluated yet:
claiming a chunk that arrives ahead of its block by its exact id, on arrival. That is safe, because
an id covers only those bytes.

**Why ties.** Without them, a push the store refuses is lost: its sender counts it as pushed and
offers it to nobody, so a node whose only peer pushed it that chunk never completes. And a node on
the proposer's other block (§3), whose copies all wait for the builder's block, would spend its
providers' parks, the last resort's asks and their answers on copies that cannot validate, and could
stall once it switches to that block.

**What a forger can do.** It affects only its own promise and the asks to itself. An installation
releases its own root's ties, once, so a proposer that signs m blocks for the slot allows at most m
releases at a node.

### 4.3 A HAVE arrives in an IDONTWANT [c7]

```python
def on_have(p, h: HaveBitmap):
    if expired(h.group): return                       # past its active lifetime (§8.1): ignored
    if not valid_have(h): return penalise(p)          # length, and indices within N once known (§8.2)
    e = peer_has[p][h.group]                          # created at p's first HAVE for the group
    newly = h.bits & ~e.bits
    e.bits |= h.bits
    e.ttl = HAVE_TTL                                  # heartbeats; refreshed by each HAVE from p for the group
    for i in newly:
        holders[h.group][i].add(p)                    # [c9] distinct live holders
        window_release(p, h.group, i)                 # [c14] a slot to p frees when p holds i, from anyone
        if h.group in planned: origin_acked(h.group, i)   # [c3, P4] a copy of i exists elsewhere (§5.1)
```

A HAVE for an expired group is ignored (§8.1), and a malformed one counts against its sender (§8.2).
Otherwise the node adds the HAVE's bits to what it knows the peer holds (`peer_has`), whose lifetime
each HAVE for the group refreshes (`HAVE_TTL`). For each index the peer newly holds, the node counts
the peer as a holder (card 9), frees the window slot of any copy it sent the peer at that index
(card 14), and, for a group it publishes, notes that a copy of the chunk exists elsewhere (§5.1).

`peer_has` is the one view of what each peer holds. Cancel and projection (§7.2), the push
candidates and budget (§5.2), whom to push to (§5.3) and what to announce read it at the moment they
act, by index, so a HAVE that arrives before its chunk's id is known still counts.

### 4.4 An IHAVE arrives [c3, c5, c7]

```python
def on_ihave(p, ih):                                                  # returns the asks (§4.1)
    if ih.ids: ihave_frames[p] += 1                                   # IHAVE-bearing frames (§8.2)
    candidates = []
    for entry in ih.ids:
        if is_have_bitmap(entry) and not valid_have(entry):           # a bitmap is held to a HAVE's
            penalise(p); continue                                     #   limits: ignored, and counted (§8.2)
        for a in expand(entry):                                       # [c7]
            if held(a) or expired(group(a)): continue
            add_offer(a, p)                                           # [c5] offer table (§6.1)
            if gated(a) or not authenticable(group(a)): continue      # [c6] stop-pull; the block first (§3)
            if tied_to_root(p, a): continue                           # its copy waits (§4.2)
            if parked(p, a): last_resort(a); continue                 # [c5] park; last resort (§6.1)
            if outstanding(p, a): continue                            # an ask of it to p is open (§6.1)
            candidates.append(a)
    asks = []
    for a in shuffled(candidates):                                    # §6.1
        if over_ihave_limits(p): held_back[(group(a), index(a))] = a  # retried at the next heartbeat (§6.4)
        elif may_ask(a, p):
            asks.append(a)
            ihave_asked[p] += 1                                       # an ask in reply to p's IHAVEs
    return asks

def over_ihave_limits(p):                                             # §8.2, per peer and heartbeat
    return ihave_frames[p] > MAX_IHAVE_MESSAGES or ihave_asked[p] >= MAX_IHAVE_LENGTH

def valid_id(a):                                                      # a chunk's structured id (§2): its
    if len(a) != 56: return False                                     #   56 bytes, and an index its group
    g, i = group(a), index(a)                                         #   can have (§8.2)
    return i < MAX_PLAIN_CHUNKS and (g not in desc or i < N(desc[g]))

def expand(entry):                                                    # [c7]
    if not is_have_bitmap(entry): return [entry] if valid_id(entry) else []   # an id, or nothing (below)
    g = entry.group
    return [known_id[g].get(i) or WantIndex(group=g, index=i) for i in entry.bits if not mine[g].has(i)]
```

**What an IHAVE does** (`on_ihave`). Each entry is a HAVE bitmap or a chunk's id (below). Every chunk
an entry names (`expand`) that the node does not hold, in a group not expired, is recorded as an
offer from the sender (§6.1). The node then asks the sender for it, unless the group's pull has
stopped (§6.2), no installed block's bid commits the group yet (§3), the sender's copy of the chunk
waits for its block (§4.2), the sender is parked for the group (the last resort may then be armed,
§6.1), or an ask of the chunk to the sender is outstanding (§6.1). The asks go in random order, each
through `may_ask`, the one ask per chunk at a time of §6.1. Over gossipsub's IHAVE limits they wait
for the next heartbeat (below).

**An IHAVE bitmap tells the node who can serve, not who holds.** It feeds the offer table only:
never `peer_has`, `holders`, cancel or the window. Nothing is asked for a group no installed block's
bid commits: the offer table keeps the announcement, and the installation asks for it (§4.2).

**Valid entries.** An IHAVE's bitmap is held to a HAVE's limits (`valid_have`, §4.3, §8.2): one with
an index at or beyond the group's count, once its descriptor is known, is ignored and counts against
the sender, as a HAVE is. An entry that is not a bitmap is a chunk's structured id (§2), or it is
ignored (`valid_id`). An id is valid if it has the id's 56 bytes and names an index its group can
have: below `MAX_PLAIN_CHUNKS`, and below the group's count where its descriptor is known. Any other
id leaves no offer, no ask and no penalty. Either way the frame still counts as one that bears an
IHAVE (§8.2). The id's last 20 bytes, the content id, cannot be checked before the chunk is held.

**Gossipsub's two IHAVE limits** delay asks here, and lose no offer. Beyond `MAX_IHAVE_MESSAGES`
IHAVE-bearing frames from a peer within a heartbeat, or once the peer has been asked
`MAX_IHAVE_LENGTH` ids in reply to its IHAVEs, its announcements are still recorded, and what the
node would ask of it is held back to the next heartbeat. The heartbeat runs the retry for it as for
any ask, with the retry's checks (§6.4, §6.1). Only asks in reply to IHAVEs count against the
limits: the retry, the last resort and the asks at installation do not. Every entry of an IHAVE is
read, where a stock implementation may stop after `MAX_IHAVE_LENGTH` ids of one IHAVE. The limits'
values are the client's (§8.2), and §8.3 gives reference values.

**Over a limit a node may read an IHAVE's bitmaps without the loop above.** Their indices join
`offered`, for a group not expired and within §8.2's limits on offers, and `held_back`, for a group
an installed block's bid commits. The heartbeat's retry does the rest: it skips what is held,
stopped or expired, and arms the last resort when every announcer is parked. This differs from the
loop in timing and order: a chunk can be retried at the heartbeat where the loop would have left it
to a retry already armed or to the last resort, which can add an ask, and the peer is missing from
the ordered list `offers`. An IHAVE over a limit then costs what a HAVE does. The limits pace the
asks made in reply to IHAVEs; they bound neither the work of reading IHAVEs nor the retries.

**Open: one chunk under two keys.** One IHAVE can name a chunk under two keys: a valid id and a
bitmap's index, or two valid ids of one group and index that differ in their content id. Its sender
can then be asked once per key, where the checks and the IHAVE limits let both asks through, each
ask with its own window (`may_ask`), promise and retries: `outstanding` sees an ask in either form,
but `on_ihave` tests it for every candidate before it asks any. A sender that follows this document
never does this (with card 7 it names bitmaps only, without it full ids only), and the cost of one
that does is not assessed.

#### Rationale

**Every entry read, every offer kept.** Ignoring an IHAVE, or the rest of one, as stock gossipsub
does, could lose a node's only offer of a chunk: nothing ensures that an announcement is repeated,
and heartbeat gossip is for peers outside the mesh. A limit therefore delays asks, to the next
heartbeat's retry, and loses no offer.

**Why `expand` looks up `known_id`.** For a bitmap, `expand` asks by index, and so does `ledger`
(§6.1): the lookup of `known_id` in both never gives an id as this document stands. An id is
recorded only for a chunk the node stored, every stored chunk is in `mine`, and neither asks for a
chunk in `mine`. The lookup is kept for a node that knows a chunk's id without holding the chunk,
which nothing here brings about.

### 4.5 An IWANT arrives

```python
def on_iwant(p, iw):                                  # returns the answers (§4.1)
    answers = {}                                      # by id: one answer per id per frame
    for a in iw.ids:
        gi = group_index(a)                           # from a WantIndex or a structured id
        if gi and expired(gi.group): continue         # past its active lifetime: ignored, no penalty
        if gi and peer_has[p][gi.group].has(gi.index):
            penalise(p)                               # it asks for a chunk it claimed: dropped
            continue
        mid = resolve(a)                              # [c7] our id at that index: received or rebuilt
        if mid is None or mid in unwanted[p]: continue
        serve_count[p][mid] += 1
        if serve_count[p][mid] > GOSSIP_RETRANSMISSION: continue   # stock: 3 answers per id per peer
        answers[mid] = chunk_of(mid)
    return list(answers.values())                     # [c14] one chunk per queue entry (§4.1)
```

**What an IWANT does** (`on_iwant`). Each id asked for is a `WantIndex` or a chunk's structured id.
An ask for a chunk of an expired group is ignored, without penalty. An ask for a chunk the asker has
claimed counts against the asker, and is dropped (below). Otherwise the node answers with its copy
of the chunk at that index, received or rebuilt (`resolve`), unless it holds none, the asker said
it does not want that id (stock IDONTWANT), or the asker has already made `GOSSIP_RETRANSMISSION`
(3) asks for that id that the node could answer (`serve_count`, which counts a repeat within one
frame too). One frame draws at most one answer per id. `resolve` returns nothing for a group the
node dropped (§4.6).

**An ask for a chunk the asker claimed is dropped: the claim wins.** On a live connection an honest
ask always arrives before the claim it would contradict (Rationale), so an ask after the claim is a
protocol violation.

**A group past its active lifetime stays expired**, so a node never asks for it again. The group's
tombstone keeps it out until its slot leaves the live window, and the window from then on (§8.1).
Controls for an expired group are ignored without penalty. A restart is not an exception: it is a
new connection, with no claims.

#### Rationale

**Why an honest ask comes before the claim.** Claims are made only for chunks that passed level 1,
and within a group's active lifetime (§8.1) a node's holdings only grow. Both lanes of a peer's
queue feed one ordered writer, the asker drops its queued asks for chunks it holds just before
writing them (§7.2), and frames are handled in stream order, with IWANT before IDONTWANT within one
(§4.1).

**Why an expired group stays expired.** A node's claims of the group can outlive the expiry: a HAVE
still queued leaves after it, and a peer keeps a claim for `HAVE_TTL`. Taking the group up again
could contradict them.

### 4.6 Decode, the claim, repair and the levels above [c6, c10]

```python
def claim_group(g):                                   # [c10] at the K-th chunk, before decoding
    stop_pull[g] = True                               # [c6] no further asks for this group
    mine[g] = all_bits(N(desc[g]))                    # [c10]
    for q in mesh: send_have(q, g)                    # [c10] the decode claim: all N bits
    close_promises_of_group(g)                        # [c5] nobody owes us chunks of this group

def decode_group(g):                                  # level 2, off the chunk path (§3)
    d = desc[g]
    rebuilt = decode_and_reencode(chunks[g], d)       # any K chunks -> all N, or None if the root differs
    if expired(g): return                             # the group passed its lifetime meanwhile (§8.1)
    if rebuilt is None: return drop_group(g)          # an inconsistent code: the builder's fault
    new = [i for i in rebuilt if not received[g].has(i)]      # rebuilt, and not received meanwhile
    for i in new: store(g, i, rebuilt[i])             # servable from now on; not marked seen,
    state[g] = COMPLETE                               #   so a copy that arrives later is still forwarded
    push_rebuilt(g, new)                              # [c10] repair: level 2 has passed
    deliver(g, payload_of(rebuilt))                   # level 3: the application's checks (§3)

def push_rebuilt(g, new):                             # [c10] to the mesh peers still short of K
    for q in shuffled(mesh):
        known = peer_has[q][g].bits | pushed[q][g]    # what q claimed, and what we chose to push it
        short = K(desc[g]) - popcount(known)          # q's shortfall: none after its decode claim
        if short <= 0: continue
        lacks = shuffled([i for i in new if not known.has(i)])    # at random, so that decoded
        for i in lacks[:short]:                                   #   neighbours tend to differ
            if enqueue(q, chunks[g][i], urgent=False):    # cards 8, 9, 12 and 14 act on it (§7.2)
                note_push(q, g, i)
            else: owe(q, g, bitmap({i}))              # refused by a full queue: offered instead (§5.2)

def drop_group(g):                                    # level 2 or level 3 failed
    state[g] = INVALID
    stop_pull[g] = True
    discard_queued(g)                                 # g's chunks, IHAVEs and IWANTs in every queue, and
                                                      #   what is owed of g; HAVEs stay
    gossip_history.remove_group(g)                    # no further heartbeat announcements of g
    discard_paced(g)                                  # nor paced ones
    close_promises_of_group(g)                        # its announcers did nothing wrong: nobody is parked
```

**The decode claim goes out at K, before decoding** (`claim_group`). At its K-th chunk a node stops
asking for the group (stop-pull, §6.2), claims all N chunks, sends its mesh a HAVE with all N bits,
and closes every promise for the group (§6.1).

**The decode claim makes the node a holder.** Its peers stop pushing to it and count it as a holder
of every chunk. The claim reaches mesh peers only: a peer outside the mesh that is still pushing (the
striping source of card 13) or answering learns of it from the node's next acknowledgement.

**Decoding** (`decode_group`) is level 2 (§3), and runs off the chunk path. Its result is dropped if
the group expired meanwhile: a decode that returns after the expiry stores, pushes, offers and
delivers nothing (§8.1). If the code is inconsistent, the node drops the group (below). Otherwise it
stores the chunks it rebuilt and serves them from then on: `resolve` finds a rebuilt chunk only once
it is stored. A rebuilt chunk is not marked seen, so a copy that arrives later is still forwarded.
The node then pushes the rebuilt chunks (repair, below) and delivers the payload to level 3.

**Forwarding continues** while a node decodes: it forwards later arrivals as before (§4.2).

**Repair** [c10]. Once level 2 passes, the node pushes the chunks it rebuilt to each mesh peer whose
claims show it short of K (`push_rebuilt`). It pushes a peer at most its shortfall, counting what the
node already chose to push it, picked at random among the rebuilt chunks the peer lacks. The pushes
are ordinary normal-lane chunks: rarest at pop orders them with the rest of the queue (card 9), one
the peer claims meanwhile is cancelled at dispatch (card 8), a peer projected to reach K without it
is skipped (card 12), and the window keeps the backlog where those rules act (card 14). A push that a
full queue refuses is offered instead (§5.2). There is no random delay before the push. A peer that
claims less than it holds draws at most its claimed shortfall from each decoded neighbour, once per
group. Repair skips card 16's guard and draw.

**What a receiver sees.** A rebuilt chunk names the block the chunks it was rebuilt from name, where
they all name one, even when another installed block's bid commits the group; where they name
several, it names one of those blocks. Where the source's chunk at that index names the same root,
the rebuilt one is that chunk, byte for byte: the same id and the same proof. Its receiver checks it
at level 1 and forwards it like any other. Nothing marks it as rebuilt. Repair waits for level 2 but
not for level 3.

**Dropping a group** (`drop_group`), when level 2 or level 3 fails. The node marks the group invalid
and stops pulling it. It removes the group's chunks, IHAVEs and IWANTs from every queue, with what is
owed of it; its HAVEs stay. It announces the group no more, at the heartbeat or paced, and it closes
every promise for the group, so nobody is parked: its announcers did nothing wrong.

**Level 3 runs on the reassembled payload**, with the envelope's separately sent signature, and
gates only what consensus consumes. If it fails, the application calls `drop_group`.

**Open: relabelled copies.** Where a proposer signs two blocks of a slot whose bids commit the
group, any node can relabel a chunk, putting the other block's root in place of the one it names.
The copy is authentic: level 1 finds the block by the root the chunk names and checks the proof
against the descriptor's root (§3), so it passes wherever that block is installed, and its id is its
own (§2). An honest node that installed that block takes such copies in, forwards them and can
decode from them. The source's copies of those indices are then second copies, only acknowledged
(§4.2), and its rebuilt chunks can name that block too (above). A neighbour that installed only the
builder's block defers these copies, ties their sender to the other root (§4.2), and asks it for
those indices again only if that root installs there. Where that sender is its only provider, the
neighbour stalls once more than N − K of the sender's copies name the other block (any one, for a
plain group), although the source reaches it through honest nodes. Nobody is penalised, since every
copy is authentic. It takes such a proposer, which is slashable (§3), and a node that relabels.
Options, none chosen:
- *level 1 by group*: the root a chunk names takes no part in level 1, deferral or ties. Level 1
  checks against any installed block whose bid commits the chunk's group, a copy waits only while
  none is installed, ties go by group and index, and any such block's installation releases them.
  Two blocks whose bids commit the group then act as one for diffusion;
- *a group per block root*: chunks under different roots are separate groups, deduplicated apart,
  so the honest node takes in and forwards the source's copies too, at the cost of shared
  deduplication under equivocation;
- *root-aware asks*: the asker names the root it installed and the answerer sends its chunk under
  that root, with the ties and the choice of the copy a node keeps changed to match.

Without card 10 a node that has decoded claims only the chunks it received, its peers keep pushing
it parity it does not need, and it pushes none of the chunks it rebuilt. Without card 6 there is no
code: a node needs every chunk, and completion is "all K received".

#### Rationale

**The claim before decoding.** Every chunk that passed level 1 is an authentic leaf under the
committed root. If the N leaves form a codeword, every node's decode succeeds and the claim is true.
If they do not, any K of them rebuild a codeword that differs somewhere, so every node's check fails,
and the claim was about a group every node drops. What waits for level 2 is everything that hands
out rebuilt data: delivery, and the rebuilt chunks. *What a forwarding node checks, and when it
decodes* (2026) maps the alternatives. Forwarding need not wait either: the chunks a node received
were authentic whatever levels 2 and 3 find.

**Why push, and not hold or announce.** A builder may release only the K chunks needed to decode.
Every node then needs every one of them, the slowest to reach it included, and the other K exist
only in the nodes that have decoded. Completion times spread out, and a builder that releases late,
near a deadline such as the payload timeliness vote, can use the spread to split the network.
Repair puts the other K back as soon as the first nodes decode, so that a node still short can again
complete on any K of the N. Holding the rebuilt chunks would not do it: the claim is not an
announcement, and asks go to announcers (§6.1), so a node that only held its rebuilt chunks would
never be asked for them, which is the same as rebuilding nothing. An announcement would add an ask
and an answer, three link delays instead of one, so it helps mainly where other asks fail. It can
also be baited: an announcement is a promise nobody can check before asking, and a withholding node
or a liar draws asks it never answers until the park stops them (§6.1). Where every chunk is released
and the other nodes are honest, a rebuilt chunk is one more copy of a plentiful one, and repair has
little to do. *What a forwarding node checks, and when it decodes* (2026) measures how much of the
spread repair takes back, against withholding nodes and silent nodes, and what it does on a full
release.

**A shortfall, not card 4's budget.** Card 4's budget cannot be reused for repair: late in a
diffusion most mesh peers have claimed every chunk, and the budget would shrink to nothing. The
chunks are picked at random so that decoded neighbours tend to push different ones. A random delay
before the push, so that decoded neighbours do not all push at once, was not taken: *What a
forwarding node checks, and when it decodes* found it changed nothing measurable on a full release,
and did not try it with only K chunks released.

**Nothing marks a rebuilt chunk.** Once the group has passed level 2, a rebuilt chunk is an authentic
leaf, as a forwarded one is.

**Keeping the root its chunks name.** The roots can differ only when a proposer signs two blocks of
a slot whose bids commit the group: the group's chunks may then name either root, which their ids
cover, and a node cannot tell which one the source's chunk names at an index it never received. A
rebuilt chunk naming the other block would wait for good at a neighbour that installed only the
block the chunks name, and its sender, which counted the push, would send nothing more for the
index. A source names one block, so with this rule every honest copy of a group names it, as long
as no node relabels a chunk: honest nodes forward a relabelled copy, and rebuild from it (above). A
rebuilt chunk that named a block whose bid commits another group would never pass level 1: a
receiver without that block defers it until the block installs, then rejects it.

**A decode that outlives its group.** This document does not bound a decode's duration (§8.1), and
a group past its active lifetime keeps only its tombstone, so the decode's result has nothing left
to act on.

## 5. Publishing and forwarding

### 5.1 The source [c2, c13]

The source builds the group at bid time (§1), and publishes once the block carrying its bid is
known:

```python
def publish(block, d, shards):
    g = group_key(group_id(d), block.slot)
    if expired(g) or not live(block.slot): return     # too late: past its live window (§8.1)
    desc[g] = d
    for s in shards:                                  # the source holds every chunk from the start
        f = Chunk(slot=block.slot, beacon_block_root=block_root(block), group=g,
                  descriptor=d, index=s.index, proof=s.proof, data=s.data)    # descriptor: design A
        store(g, s.index, f); mark_seen(message_id(f))
        gossip_history.put(f)                         # stock: heartbeat gossip may announce it (§6.4)
    mine[g] = all_bits(N(d)); state[g] = COMPLETE; stop_pull[g] = True
    origin[g] = bitmap(set())               # [P4] our HAVE names the chunks acknowledged so far (§5.1): none yet
    plan = []
    for i in range(N(d)):                   # index order; each chunk's targets see earlier plans
        f = chunks[g][i]
        targets = choose_push(f, candidates_for_source(f), budget=R, at_source=True)   # §5.3
        for p in targets: note_push(p, g, i)
        plan.append((f, targets))
    led = set()
    for copy in range(R):                   # the first copy of every chunk before any second  [c2]
        for f, targets in plan:
            if copy < len(targets):
                p = targets[copy]
                if p not in led:            # [P4] a peer's first chunk from us follows our HAVE naming
                    led.add(p)              #   it, as a forwarding node's HAVE precedes its pushes
                    enqueue(p, IDONTWANT(HaveBitmap(group=g, bits=origin[g] | bitmap({f.index}))), urgent=True)
                if not enqueue(p, f, urgent=False): unpush(p, g, f.index)   # refused: offered instead (§5.2)
    planned[g] = {f.index: set(targets) for f, targets in plan}    # [c3] the mesh peers not chosen to be
                                            #   pushed a chunk are announced it at its acknowledgement

def origin_acked(g, i):                     # [c3, P4] a chunk of a group we publish is acknowledged:
    if origin[g].has(i): return             #   a peer's HAVE names it (§4.3), or its
    origin[g].set(i)                        #   first copy's slot timed out (§7.1). It joins our HAVE, which
    for q in mesh: send_have(q, g)          #   goes to the mesh as a forwarding node's does when a chunk
    for p in mesh:                          #   arrives (§4.2), and the mesh peers not chosen to be pushed
        if p not in planned[g].get(i, ()):  #   it are announced it (a refused push is owed already, §5.2)
            announce(p, g, bitmap({i}))

def candidates_for_source(f):
    pool = connected_topic_peers() if UPLINK >= STRIPE_UPLINK else mesh    # [c13] configured uplink
    return [p for p in pool if not peer_has[p][f.group].has(f.index)]
```

**Publishing** (`publish`). Unless the group has expired or its slot is outside the live window, the
source stores every chunk, marks it seen, and puts it in the message cache for heartbeat gossip
(§6.4). It holds the whole group from the start and stops pulling it; its HAVE names none of the
group yet (below). It then plans the pushes: for each chunk, in
index order, R targets that §5.3 chooses among its candidates (`candidates_for_source`), each chunk's
choice seeing the plans made before it. It sends the first copy of every chunk before any second
copy. A peer's first chunk from the source follows a HAVE that names it (below). A push that a full
queue refuses is offered instead (§5.2).

- **Batch publishing** [c2] fixes only the order in which chunks enter each peer's queue. What
  leaves first on each link is decided when the queue sends (§7).
- **Striped publishing** [c13]: a source whose configured uplink is at least `STRIPE_UPLINK`
  stripes; a slower one pushes to its mesh, as the other nodes do. A source that stripes takes every
  connected peer on the topic as a candidate. With the fewest-first order of §5.3, and each
  connection starting with nothing, the chunks are dealt two at a time over all connections: the two
  copies of a chunk go to two different peers, and each connection receives about 2N/C chunks. Only
  mesh peers not chosen to be pushed a chunk are announced it, and one whose push the queue refuses
  is offered it instead (§5.2), so no peer is offered a chunk twice. Other connections get no
  announcement from this step, though heartbeat gossip may announce to them later (§6.4).
- The source pushes each chunk to R = 2 peers. It never uses the fast-class degree of card 17.
- **The source announces at the acknowledgement** [c3] (`origin_acked`). The mesh peers not chosen
  to be pushed a chunk are announced it at its acknowledgement: at the first HAVE naming it, from
  any peer (§4.3), or, if none comes, when its first copy's window slot times out (§7.1). The offers
  trail the pushes by about a round trip.
- **The source's HAVE is paced** [P4], for the source's privacy. It names the chunks acknowledged so
  far: a chunk joins it at its acknowledgement, and the HAVE then goes to the mesh, as a forwarding
  node's does when a chunk arrives. A peer the source pushes to also gets a HAVE naming its first
  chunk, just ahead of it, as a forwarding node's HAVE precedes its pushes. HAVEs to the mesh that
  would leave together may be merged into one, as the research implementation merges those of the
  chunks sent between two of its router's turns.

#### Rationale

**Striping's threshold.** Striping pays only when the source can send faster than its mesh peers
can pass the chunks on. The source knows neither their uplinks nor how much of its own it can count
on, so the threshold sits where the gain is measured (§8.3).

**Announcing at the acknowledgement, not at publish.** Announced at publish, the offers would race
the pushes. A transport that takes the whole batch at once (a deep library buffer, a socket's send
buffer, a router's queue) lets every announcement leave at once; the mesh then asks for chunks whose
pushes are still queued, and the source answers on top of its pushes. The acknowledgement is the one
event the source sees whatever the transport holds (§7.3).

**The paced HAVE.** A HAVE that names every chunk before any chunk has left can come only from the
source, so it would tell each mesh peer who published the payload. The paced HAVE still keeps the
other nodes from pushing the source's chunks back to it, a chunk at a time. It removes the one
certain sign of the source. Others remain: the source's HAVE grows faster than any other node's, it
announces every chunk at once to a peer that joins its mesh (§5.4), and it is everyone's first
sender. They are the subject of separate work on the source's privacy, where P4 is this measure's
name.

### 5.2 A node forwards [c3, c4, c11, c17]

```python
def forward(f, from_peer):
    g, i = f.group, f.index
    holding = [p for p in mesh if peer_has[p][g].has(i)]                # [c4] the sender, normally
    cands = [p for p in mesh if p not in holding and p != from_peer]
    budget = max(0, R_NODE - len(holding))                              # [c3, c4, c11, c17]
    targets = choose_push(f, cands, budget, at_source=False)            # §5.3
    for p in targets:
        if enqueue(p, f, urgent=False): note_push(p, g, i)              # [c7]
        else: owe(p, g, bitmap({i}))                                    # [c3] refused: offered instead
    for p in cands:
        if p not in targets: announce(p, g, bitmap({i}))                # [c3]
    gossip_history.put(f)                                               # stock message cache (§6.4)

def announce(p, g, bits):                                               # [c3, c7]
    b = bits & ~pushed[p][g] & ~peer_has[p][g].bits                     # an empty bitmap is not sent
    if b and not enqueue(p, IHAVE(HaveBitmap(group=g, bits=b)), urgent=False):
        owe(p, g, b)                                                    # refused by a full queue: owed

def unpush(p, g, i):                                                    # [c3] a chosen push that will not
    pushed[p][g].clear(i)                                               #   be made: not counted (the guard's
    if p in mesh: owe(p, g, bitmap({i}))                                #   clock stays), offered instead

def owe(p, g, bits):                                                    # an offer that must not be lost:
    owed[p][g] |= bits                                                  #   the next write to p carries
    wake(p)                                                             #   it (§7.2)

def note_push(p, g, i):
    e = pushed[p][g]                                                    # created at the first push
    if e.empty(): e.first_push = now                                    # the guard's clock (§5.3)
    e.set(i); e.ttl = PUSH_TTL                                          # heartbeats
```

**Forwarding** (`forward`). A node forwards each chunk it stores at an index it had not received
(§4.2). It pushes the chunk to at
most `budget` of the mesh peers that do not hold it, chosen by §5.3, announces it to the other mesh
peers that do not hold it, and puts it in the message cache for heartbeat gossip (§6.4). The peer it
came from is neither pushed nor announced the chunk.

- **Announce instead of push** [c3]: a node pushes each chunk to at most `budget` mesh peers and
  announces it to the others, which ask if they still need it.
- **A push that does not happen is offered instead** [c3] (`unpush`, `owe`). A chosen push that
  projection skips when the writer reaches it (§7.2), or that a full queue refuses (§8.2), is no
  longer counted as pushed, and the chunk is offered to the peer instead, if it is in the mesh, as a
  chunk not pushed is. An offer that a full queue refuses is owed, and the next write to the peer
  carries it (§7.2). A skipped push to a connection outside the mesh (card 13) is forgotten but not
  offered, so §5.1's other connections still get no announcement from the source's step.
- **The phase** [c4]: the budget shrinks with every mesh peer already known to hold the chunk. The
  sender has normally claimed the chunk before it arrives (its HAVE travels urgently, ahead of the
  data), so it counts as a holder. At R = 2 a received chunk therefore goes on to one more peer early
  in its life, and to none late. Without card 4 the budget is R, whatever the holders.
- **R** [c11]: 2 with the code. Without card 11, 3 at 1 MiB (the uncoded schedule).
- **Push by uplink class** [c17]: `R_NODE = R_FAST` (6) if the node's configured uplink is at least
  `FAST_UPLINK` (500 Mbps), else R. The node knows its uplink from the same configuration that sizes
  its window (§7.1).

#### Rationale

**A push that does not happen is not counted.** Counted, such a push would leave its peer neither
pushed nor offered the chunk. Where no other peer offers it, as in a triangle, a ring or at a node
with one peer, that peer would never complete.

### 5.3 Whom to push to: furthest behind first [c16]

```python
def choose_push(f, cands, budget, at_source):
    if budget >= len(cands): return cands              # everyone, no ordering needed
    g = f.group
    known = {p: popcount(peer_has[p][g].bits | pushed[p][g]) for p in cands}      # [c16]
    unproven = {p: guard_fails(p, g) for p in cands}                              # [c16]
    order = sorted(cands, key=lambda p: (tiebreak(f, p), peer_id_bytes(p)), reverse=True)
    order.sort(key=lambda p: (unproven[p], known[p]))  # stable: equal counts keep the tie-break
    if not at_source:                                                             # [c16] safer form
        ok = [p for p in order if not unproven[p]]
        if ok:
            median = known[ok[(len(ok) - 1) // 2]]
            pool = [p for p in ok if known[p] <= median]
            drawn = sample_without_replacement(pool, min(budget, len(pool)))
            order = drawn + [p for p in order if p not in drawn]
    return order[:budget]

def guard_fails(p, g):                                                            # [c16] proof guard
    e = pushed[p][g]
    return (popcount(e) >= R_NODE and now - e.first_push > GUARD_GRACE
            and g not in peer_has[p])              # no HAVE at all from p for g while we keep pushing it
```

**Choosing the targets** (`choose_push`). When the budget covers every candidate, every candidate is
pushed. Otherwise the candidates are ranked: peers the guard demotes last, the others by the chunks
of the group they are known to hold, fewest first, and ties by the tie-break. A forwarding node then
draws its targets at random among the peers the guard does not demote whose count is at or below
their median, and fills any places left in rank order. The source takes the ranking as it is.

- **Chunks held** counts what the peer told us in its HAVEs plus what we chose to push it, including
  pushes still queued, and not since skipped by projection or refused by a full queue (§5.2).
  Announcements and answered asks do not count. Repair's shortfall (§4.6) reads the same count.
- **The lower-half draw** picks the push targets uniformly, without replacement, among the peers at
  or below the median of that count. That is not a guarantee of a fair share of the traffic: an
  under-reporter is drawn with bounded probability within the lower half.
- **The guard** (`guard_fails`) moves a peer to the back when we have chosen to push it at least
  `R_NODE` chunks of the group, the first more than `GUARD_GRACE` ago, and it has sent no HAVE for
  the group, not even an empty one. A demoted peer can still be pushed if the budget reaches it, and
  the demotion lifts at its first HAVE. Once every push counted to a peer has been skipped or
  refused, the clock starts again at the next push, one the peer can receive (`note_push`, §5.2);
  each restart delays a demotion by at most `GUARD_GRACE` from the push that starts it. A peer that
  asks and sends no HAVE can cause such restarts, since our answers let projection skip the pushes
  counted to it.
- **At the source** the ranking is fewest-chunks-first, with no draw. The guard is evaluated but
  cannot fire, because the whole group is planned at one instant.
- **Tie-break:** a hash of (message id, peer id), finalised; larger first, then the larger peer id.
- **Without card 16:** order candidates by that tie-break alone.

#### Rationale

**Furthest behind first.** The peers that hold the fewest chunks are the ones for which a push is
least likely to be a duplicate, and the ones that would otherwise have to ask.

**A draw, not the single furthest behind.** The count trusts what each peer says about itself. Taking
the single peer furthest behind, an under-reporter would always look furthest behind and win every
contested push; a node that tells each pusher it holds only what that pusher sent it would draw
most of its neighbours' pushes and pass none on. Drawn within the lower half, it no
longer wins every contested push.

**The guard** is for a peer that takes pushes and never reports at all.
`GUARD_GRACE` allows for the first push to leave the node and the peer's first HAVE to come back,
about one round trip where queues are short (§8.3). An honest peer can still be demoted while its
copies wait for their block, or if its HAVE is dropped at a full queue, until its first HAVE comes.
At the source the plain ranking is what spreads card 13's stripes evenly over its connections
(§5.1).
*Segmented payload diffusion, card by card* (2026, card 16) gives what each form costs against
under-reporters, as measured.

### 5.4 A peer joins the mesh

```python
def on_mesh_join(p):                                  # p joins our mesh: by our GRAFT, or by one of p's
    for g in list(chunks):                            #   that we accept (stock gossipsub decides who)
        if expired(g) or state[g] == INVALID: continue    # nothing of an expired or dropped group
        announce(p, g, bitmap(set(chunks[g])))        # what we can serve, received or rebuilt (§5.2)
```

- **A peer that joins the mesh is announced what the node holds** (`on_mesh_join`).
- **What is announced** is what `resolve` answers (§4.5): the chunks the node stores, received or
  rebuilt, one bitmap per group, minus what it pushed the peer and what the peer claimed
  (`announce`, §5.2), owed if a full queue refuses it. Not the decode claim, which names chunks not
  yet rebuilt, and nothing of a group that expired or was dropped.
- **At the source** that is every chunk of a group it publishes, sent or not; its HAVE stays paced
  (P4). The announcement stays inside the mesh.
- **When it runs**: at every addition of a peer to the node's mesh for the topic, whatever adds it:
  a GRAFT the node accepts, its own GRAFT when it joins the topic, the heartbeat's upkeep (a mesh
  below `Dlo`, the outbound quota) and opportunistic grafting. The node's own GRAFT runs it at once,
  without waiting for the peer to accept: a peer that prunes the node instead has received an
  ordinary offer from a peer outside its mesh. A GRAFT from a peer already in the mesh adds nothing
  and runs nothing; a peer that leaves the mesh and joins it again, even within a heartbeat, is
  announced again. A closed connection leaves the mesh, so a reconnection is announced again once
  the two graft each other again.
- **Its cost** is one IHAVE bitmap per stored group and join (the bitmap 16 bytes at N = 128, up to
  1 KiB at `MAX_PLAIN_CHUNKS`, plus the group id and framing), several groups' bitmaps in one frame
  where they fit, and the asks they draw. At the receiver they count as any IHAVE does: its IHAVE
  limits delay the asks, not the reading of the bitmaps nor the retries (§4.4), and its offers are
  kept within §8.2's limits on admitted groups.

#### Rationale

**Why announce at a join.** Offers come from announcements, and a node announces a chunk when it
forwards it, which follows the chunk's arrival. Without the announcement at a join, nothing would
ensure that a peer that joins the mesh after a chunk was forwarded is offered it, nor that a peer
whose connection closed is offered on the new connection what the old one lost: a closed connection
takes with it what was queued, owed or in flight on it (§8.1). Heartbeat gossip may announce a chunk
on a connection outside the mesh, and a later copy may be forwarded, but neither need happen: the
gossip goes to a sample of the peers outside the mesh and names only the last three heartbeats'
chunks (§6.4).

**The source's announcement stays inside the mesh.** On connections outside it, the source's
announcement of every chunk at once would tell more peers who published.

## 6. Asking

### 6.1 One ask per chunk at a time, move on, park [c5]

A node asks for a chunk it lacks from one announcer at a time. Each ask has a window,
`IWANT_WINDOW`: if the chunk has not arrived when the window closes, the node asks an announcer it
has not asked yet, or else the one it asked longest ago (*the retry*). An ask written to a peer
opens a *promise*. If nothing closes the promise
within `PROMISE`, the peer is *parked* for the chunk's group for `PARK_TTL`: the node stops asking
it for that group's chunks. When every announcer of a chunk is parked, the node asks each of them
once more, after waits that double (*the last resort*).

```python
def may_ask(a, p):
    at = asked_at.get(a)
    if at is not None and now - at < IWANT_WINDOW:       # 200 ms: an ask is in flight
        return False
    asked_at[a] = now
    tried[a][p] = now
    after(IWANT_WINDOW + RETRY_SLACK, retry_offer, a)    # move on, once the window has closed
    return True                                          # the promise starts at the write (§7.2)

def retry_offer(a):
    if held(a) or stop_pull[group(a)] or expired(group(a)): return
    if now - asked_at.get(a, -inf) < IWANT_WINDOW: return
    cands = [q for q in announcers(a) if not parked(q, a) and not tied_to_root(q, a)]
    if not cands: return last_resort(a)                   # every announcer is parked, or tied (§4.2)
    free = [q for q in cands if not outstanding(q, a)]    # an announcer not yet answered is not asked
    if not free: return after(IWANT_WINDOW + RETRY_SLACK, retry_offer, a)   # again: look again later
    pick = untried(free, a)
    if pick is None: pick = least_recently_tried(free, a)
    if may_ask(a, pick): enqueue(pick, IWANT([a]), urgent=False)

def outstanding(q, a):                                    # an ask of a's chunk to q, promised or still
    k = (group(a), index(a))                              #   queued, in either form
    if any(r == q and (group(b), index(b)) == k for (b, r) in promises): return True
    return any((group(b), index(b)) == k for e in queue[q].normal for c in e.iwants() for b in c.ids)

def add_offer(a, p):                                      # within §8.2's limits on a's group
    offered[p][group(a)].set(index(a))                    # every offer kept, per connection and group
    o = offers[a]                                         # the first 16, in announcement order, are
    if p not in o and len(o) < 16 and listed(p) < 256:    #   tried first; an announcer is in at most
        o.append(p)                                       #   256 of these lists (§8.2)

def announcers(a):                                        # the list, then every other peer that offered a,
    return offers[a] + own_order([q for q in connected_topic_peers()   #   in the node's own order (below)
                                  if q not in offers[a] and offered[q][group(a)].has(index(a))], a)

def ledger(g):                                            # what was offered of g and is not held, asked
    bits = bitmap(set())                                  #   as expand (§4.4) would ask it
    for q in connected_topic_peers(): bits |= offered[q][g]
    return [known_id[g].get(i) or WantIndex(group=g, index=i) for i in bits if not mine[g].has(i)]

def untried(cands, a):                                    # the first not asked yet: the list keeps
    return next((q for q in cands if q not in tried[a]), None)    #   announcement order (below)

def least_recently_tried(cands, a):
    return min(cands, key=lambda q: tried[a][q])

def promise_due(a, p, at):
    if promises.get((a, p)) != at: return                  # delivered, closed on decode, or gone
    del promises[(a, p)]                                   #   with the connection
    park[p][group(a)] = now + PARK_TTL                     # k = 1: one broken promise parks p
                                                           # for this group only, 30 s
def parked(p, a): return now < park[p].get(group(a), -inf)

def close_promises(g, i, of=None):                        # chunk i of g arrived, from anyone: what was
    k = (g, i)                                            #   kept to ask for it goes, under every key
    for (a, q) in list(promises):                         #   that names it (§8.1). With `of`, that peer
        if (group(a), index(a)) == k and of in (None, q): #   alone answered, with a copy that waits
            del promises[(a, q)]                          #   (§4.2): its promise closes, nothing else
    if of is not None: return
    for a in [a for t in (offers, tried, asked_at) for a in list(t) if (group(a), index(a)) == k]:
        offers.pop(a, None); tried.pop(a, None); asked_at.pop(a, None)
    asked_parked.pop(k, None)                             # the last resort's count is per chunk
    for q in list(offered):
        if g in offered[q]: offered[q][g].clear(i)

def drop_offer(g, i, p):                                  # p's offers of chunk i of g go, under every
    k = (g, i)                                            #   key that names it, and its asks of the
    if g in offered[p]: offered[p][g].clear(i)            #   chunk with them (§4.2's drop_tie; the
    for a in [a for a in list(offers) if (group(a), index(a)) == k and p in offers[a]]:   # offers' expiry)
        offers[a].remove(p)
        if not offers[a]: del offers[a]
    for e in queue[p].normal:                             # an ask of it still queued to p is removed,
        for c in e.iwants(): c.ids = [b for b in c.ids if (group(b), index(b)) != k]
    queue[p].normal = [e for e in queue[p].normal if not e.is_empty()]
    close_promises(g, i, of=p)                            #   and p's promise for it closes

def last_resort(a):                                       # every announcer of a is parked: each is
    k = (group(a), index(a))                              #   asked once more, later; counted per
    done = asked_parked[k]                                #   chunk, whichever form names it
    untied = [q for q in announcers(a) if not tied_to_root(q, a)]    # a tied announcer is passed over
    if k in last_resort_armed or any(not parked(q, a) for q in untied): return
    if all(q in done for q in untied): return
    last_resort_armed.add(k)
    after(PROMISE * 2 ** len(done), ask_parked, a)        # 0.4 s, 0.8 s, 1.6 s, ...

def ask_parked(a):
    k = (group(a), index(a))
    last_resort_armed.discard(k)
    if held(a) or stop_pull[group(a)] or expired(group(a)): return
    if now - asked_at.get(a, -inf) < IWANT_WINDOW: return    # someone was asked meanwhile
    untied = [q for q in announcers(a) if not tied_to_root(q, a)]
    cands = [q for q in untied if not parked(q, a)]          # an announcer unparked meanwhile first
    if not cands:
        cands = [q for q in untied if q not in asked_parked[k]]
        if not cands: return
    free = [q for q in cands if not outstanding(q, a)]       # none asked again while not answered:
    if not free:                                             #   the last resort waits as the retry does
        last_resort_armed.add(k)
        return after(IWANT_WINDOW + RETRY_SLACK, ask_parked, a)
    pick = untried(free, a)
    if pick is None: pick = least_recently_tried(free, a)
    if may_ask(a, pick) and enqueue(pick, IWANT([a]), urgent=False):
        if parked(pick, a): asked_parked[k].add(pick)     # counted once the queue has taken the ask
```

The rules follow. Why each is as it is comes after them, under *Rationale*.

**Offers.** Every announcement of a chunk is recorded as an offer (`add_offer`), within §8.2's
limits on offers. That includes an announcement from a parked peer, and one in an IHAVE over
gossipsub's limits (§4.4). The node keeps two records:
- `offered` holds every offer, as one bitmap per connection and group;
- `offers` lists, for each chunk id, its first 16 announcers in the order they announced it. The
  list only sets the order in which announcers are tried. An announcer is in at most 256 such
  lists (§8.2). An announcer left out of a list, because the list was full or because it was in
  256 lists already, is still in `offered`.

An offer is dropped when the chunk arrives (`close_promises`), when the announcer's connection
closes, or 30 s after the announcer's last offer of the group (`drop_offer`). Until the block is
installed, the offers are also the ledger of what to ask for when it installs (`ledger`, §4.2).

**The retry** (`retry_offer`) runs `IWANT_WINDOW` + `RETRY_SLACK` after each ask, armed by
`may_ask`. It also makes the asks at the block's installation (§4.2), those for the indices of a tie
that is dropped (`drop_tie`, §4.2), and, at the next heartbeat, those held back over gossipsub's
IHAVE limits (§6.4). It does nothing if the chunk is held, if the
group's pull has stopped (§6.2) or the group has expired, or if another ask of the chunk is still
within its window. Otherwise it takes the chunk's announcers in order (`announcers`): first the
list, in announcement order, then every other connected peer on the topic that offered the chunk,
in the node's own order (below). It passes over an announcer that is parked, that is tied to a root
not yet installed (§4.2), or that has an ask of the chunk outstanding (below). Of the rest, it asks
the first one it has not asked before (`untried`), or else the one it asked longest ago
(`least_recently_tried`). If every announcer is parked or tied, it turns to the last resort. If
every one left has an ask outstanding, it looks again `IWANT_WINDOW` + `RETRY_SLACK` later.

**The node's own order.** The announcers beyond the list are those left out of it, because it was
full or because they were in 256 lists already, and those whose IHAVE was read without the loop,
over a limit (§4.4). The node tries them after the list, in an order of its own, which no peer can
predict or arrange. That is all the order has to be: no other node sees it and nothing on the wire
carries it, so two nodes that make it differently work together as well as two that make it alike.
The reference way, which `own_order` stands for and the toy runs (§8.1), ranks the announcers by a
keyed hash of the chunk (its group and index) and the peer id, under a secret the node draws when it
starts and never sends: larger first, then the larger peer id, as in §5.3's tie-break. The rank
differs per chunk and per node, and stays the same over a chunk's retries. The secret lasts while
the node runs, and nothing depends on its surviving a restart. An implementation is advised to run
the reference way outside its tests too, with a secret drawn at random, so that the code its tests
exercise is the code that runs.

**Promises.** A promise starts when the ask is written (§7.2), not when the node decides to ask: an
ask still queued behind §7.1's window, or dropped at a full queue, opens none. If the
promise is still open `PROMISE` after the write, the peer is parked for the chunk's group for
`PARK_TTL` (`promise_due`). One broken promise is enough. A promise closes, and parks nobody, when:
- a copy of the chunk that passes level 1 arrives, from anyone;
- the group is decoded (§4.6);
- the peer's own copy of the chunk waits for its block: the copy ties the peer (§4.2), which closes
  that peer's promise and no other;
- the peer's offers of the chunk are dropped (`drop_offer`, below);
- the peer's connection closes. The ask or its answer went with the connection, and the retry,
  whose timer is per ask, moves on to the other announcers.

So an announcer that withholds a chunk, and whose connection closes before its promise falls due,
is not parked. On a new connection it may be asked again, per index one ask and one last resort.
(While its promise is open, the retry does not ask it again: see below.)

**Parking** affects only asks. A parked peer is not asked for the group's chunks, except by the
last resort, but its pushes, and the node's answers to it, go on.

**No second ask of a peer while one is outstanding.** An ask of a chunk to a peer is outstanding
while it is queued to the peer or its promise is open, whether it names the chunk by id or by group
and index (`outstanding`). The retry, the last resort and §4.4 pass over an announcer with an ask
outstanding. When every candidate has one, the retry and the last resort look again
`IWANT_WINDOW` + `RETRY_SLACK` later.

**An ask goes with its announcer's offers.** When an announcer's offers of a chunk are dropped,
with its tie (§4.2's `drop_tie`) or 30 s after its last offer of the group, an ask of the chunk
still queued to it is removed, and its promise for the chunk closes (`drop_offer`). Its next offer
of the chunk is then asked for, with the retry, as any offer is. The chunk's arrival and a closed
connection need nothing more: the writer drops an ask for a chunk the node holds (§7.2), the
arrival closes the chunk's promises (§4.2), and a close takes the queue and the promises with the
connection.

**The last resort** (`last_resort`, `ask_parked`) is armed when every untied announcer of the
chunk is parked: by the retry, when every announcer is parked or tied, and by §4.4, when a parked
announcer offers the chunk. It asks the parked announcers once more each, one at a time: an ask
after a wait of `PROMISE` × 2ⁿ, where n is the number of parked announcers it has already asked
for the chunk (0.4, 0.8, 1.6 s, ...). An announcer unparked in the meantime is asked first. The
count of those asked (`asked_parked`) and the one timer armed for it are kept per chunk, by group
and index, whichever form names the chunk. An ask is counted once the queue has taken it, so an
ask that a full queue refuses spends nothing. `asked_parked` lives as `tried` does, and a closed
connection resets its announcer's count. Against announcers that never answer, the last resort
adds at most one ask per announcer and chunk while its count is kept. While no count is reset, the
doubling waits allow at most six such asks for a chunk within the 30 s an offer lives, at the
default `PROMISE`. The retry is unchanged by it.

**An answer can still wait for a block** at a node that asks only once its block is installed
(§3), when the answer names another root. That root is a forgery's or, when the proposer signed
two blocks for the slot, the builder's block at a node that installed the other one, whose bid may
commit the same group. The copy ties its sender (§4.2): the sender's promise closes, so it is not
parked for the copy, and it is not asked for the index again until the root the copy names
installs. That installation makes it an offer again. A forgery's root never installs, or commits
another group, and its tie goes with it.

**Without the offer table and the park,** the window alone asks the first announcer, and asks again
whoever announces after the window.

**Open: an announcer that is never parked holds the last resort off.** The last resort is armed
only when every untied announcer is parked. An announcer whose connection closes before its promise
falls due is not parked (above). Nor is one that leaves the ask unwritten by not reading, so that
its promise never starts. While such an announcer stays a candidate, a parked honest provider of
the chunk is not asked again, for as long as its park lasts and the group is live. This version
does not address it; a fix is open.

#### Rationale

**One announcer at a time, then the next.** Some gossipsub implementations, go-libp2p's among them,
ask every peer that announces a message they lack, which is what a node without card 5 does (§0).
With an announcement per chunk (card 3), that brings back through the pull path the duplicates the
push path saved. Asking one announcer at a time needs a window after which the node moves on:
waiting on a single peer would let a peer that announces and never serves hold the chunk up. An
answer that comes after the window is still taken.

**Promises and the park.** The park bounds what a peer that announces and does not serve can
capture: once parked, it is asked for the group's chunks only by the last resort. The park is
scoped to the group, so that one payload's broken promise does not cost the next: a busy peer, the
builder included, can break a promise on one payload, and a park across groups would then pass it
over on the payloads that follow. *Segmented payload diffusion, card by card* (2026, card 5) gives
what card 5 costs and saves in the measured networks.

**A promise starts at the write**, not at the decision to ask, so that no peer is parked for an ask
it never received.

**Every offer is kept; the list is only an order.** As at gossipsub's IHAVE limits (§4.4), nothing
ensures that an announcement is repeated, so an offer the node forgot could be its only offer of
the chunk. The list, and the bound on how many lists an announcer is in, therefore bound only the
state that orders the asks: a full list forgets no announcer, nor does the bound on lists, and
`offered` keeps every offer within §8.2's bound per peer.

**An order of the node's own, beyond the list.** An order that a peer can arrange, by when it
connects or by its id, would let it stand ahead of every other announcer beyond the list, for every
chunk and at every node. So would a rank under a key that is public: a peer that can compute it can
connect under the id that ranks first. Under a secret rank, of two announcers beyond the list each
is ahead of the other about half the time, and nodes rank them independently of one another. This
covers the announcers beyond the list only. The list keeps announcement order, which the first to
announce still decides, and a sender with several peer ids beyond the list has one of them ahead
more often. Whatever the order, among the announcers it may ask, the retry takes one it has not
asked before one it has.

**No second ask while one is outstanding.** On a live connection an answer does not overtake the
ask before it, so a second ask of the same peer could only draw a second answer. That matters while
the answers cannot be validated yet. A provider answers a peer at most `GOSSIP_RETRANSMISSION` (3)
times per chunk and connection (§4.5). With the rule, while its park and the last resort's count
last, a provider is asked for a chunk at most twice before the root its copies name installs: once,
and once more by the last resort. Its third answer is left for after a switch to that block.
Without the rule, asks decided while the first answer is on its way (the retry after the window, an
ask held in the queue, the last resort's ask) can spend all three answers on copies that cannot
validate, and the node stalls after it switches.

**An ask goes with its announcer's offers.** Kept, the ask would leave the announcer outstanding,
with nothing to look at it again. Once its offers are gone, a retry that finds no other announcer
to ask ends. The announcer's next offer is only recorded, since an ask of the chunk to it is
outstanding (§4.4). While that lasts, a parked announcer that offers the chunk draws no last
resort, since this one is not parked. Once the promise falls due and parks this one too, nothing
asks either of them again, and the node can stall although a parked honest announcer was never
asked once more. An announcer can bring this about: it keeps the ask queued by not reading, and
chooses when it last offers.

**The last resort.** Without it, one slow answer parks a node's only provider for the group, and
the node stalls. The count is per announcer: with one count per chunk, a withholding announcer that
announced first would spend it, and an honest provider parked later for one slow answer would get
none. The count and the timer are per chunk, by group and index, so a parked peer that announces one
index under many ids gets one last resort for it.

### 6.2 Stop-pull [c6]

```python
def gated(a): return stop_pull[group(a)]      # from the decode claim on, no further asks for the group
```

From the decode claim on (§4.6), a node asks for no chunk of the group (`gated`). Pushes already on
their way still land. Before completion, each newly accepted distinct index counts toward K;
duplicates do not.

**When the gate decides.** With card 10 the gate never decides alone for an ask of an index the
group has: wherever `stop_pull[g]` is set, every index of the group is already in `mine[g]`
(`claim_group` sets both, and `drop_group` follows a claim), so `held` answers first wherever the two
are tested (`on_ihave`, `retry_offer`, `ask_parked` and `filter_entry`). An ask of an index at or
beyond the group's count is stopped by the gate alone. The gate decides for every ask at a node
without card 10, which claims only the chunks it received (§4.6).

### 6.3 Receiving an answer

Answers are ordinary chunks and go through §4.2.

### 6.4 Heartbeat gossip and pacing [c15]

```python
def on_heartbeat():
    ihave_frames.clear(); ihave_asked.clear()                 # §4.4's limits start again, and the
    for a in held_back.values(): retry_offer(a)               #   retry runs for what they held back,
    held_back.clear()                                         #   which they do not count
    drop_stale_waits()                                        # §4.2's copies and ties past their window
    ids = gossip_history.gossip_ids()                         # stock: ids of the last 3 heartbeats
    eligible = [q for q in topic_peers() if q not in mesh and gossip_eligible(q)]   # stock: scores
    n = min(len(eligible), max(D_LAZY, floor(GOSSIP_FACTOR * len(eligible))))
    for q in sample_without_replacement(eligible, n):
        if PACED: pace_queue.append((q, ids, now))            # [c15]
        else: send_gossip(q, ids)

def on_pace_tick():                                            # [c15] every HEARTBEAT / 16, from the
    while pace_queue:                                          #   first job queued
        q, ids, at = pace_queue.pop(0)
        if now - at >= HEARTBEAT or not connected(q): continue    # stale, or q has left
        send_gossip(q, ids)
        return                                                 # one peer per tick, even if nothing was left to send

def send_gossip(q, ids):                                       # [c7]
    for g, bits in group_bits(ids):
        announce(q, g, bits)                                   # minus pushed[q], minus peer_has[q] (§5.2)
```

**At each heartbeat** (`on_heartbeat`) a node starts the counts of §4.4's IHAVE limits again, and runs
the retry of §6.1 for each chunk they held back; these retries do not count against the limits. It
drops what has waited for its block past its group's lifetime or its slot's live window (§4.2).
Then it sends heartbeat gossip as stock gossipsub does: the ids of the last three heartbeats'
chunks, to a sample of the topic peers outside the mesh that stock scoring admits. It announces them
as IHAVE bitmaps, one per group, minus what it pushed each peer and what the peer claimed
(`send_gossip`, §5.2).

**Paced gossip** [c15] (`on_pace_tick`) releases the heartbeat's announcements one peer per tick,
every heartbeat/16, instead of all at once. A job still queued a heartbeat later, or for a peer that
has left, is dropped.

The gossip history holds the chunks the source published and the chunks a node received and
forwarded. It does not hold the chunks a decoded node rebuilt, which are pushed instead of announced
(§4.6). A full bitmap held back can mean a retry per chunk where one IWANT would have carried the
asks; the retries to one peer may go in one IWANT.

#### Rationale

**Paced gossip.** Stock gossipsub announces new messages to its sample of peers outside the mesh all
at once, at the heartbeat. Those peers then ask the source for what they lack while the source's
uplink is still busy with its first copies (*Segmented payload diffusion, card by card*, 2026, card
15).

## 7. Sending: the per-peer queue and the window

### 7.1 The window [c14]

```python
W = ceil(uplink_bytes_per_s * (RTT_REF + TARGET) / CHUNK_BYTES)   # one window per node  [c14]
in_flight = 0                         # slots taken: held by a writer, or travelling with a chunk
waiters = deque()                     # peer writers waiting for a slot, first come first served
sent = {}                             # (peer, group, index) -> send time

def acquire_slot(p):                  # True: p's writer holds a slot; False: it waits in line
    global in_flight
    if in_flight < W and (not waiters or waiters[0] == p):
        if waiters: waiters.popleft()
        in_flight += 1
        if waiters and in_flight < W: wake(waiters[0])    # slots remain: the next in line takes one too
        return True
    if p not in waiters: waiters.append(p)        # a writer keeps its place while it waits
    return False

def release_unused_slot(p):           # p's writer has no chunk to send now
    if p in waiters:
        waiters.remove(p)                         # it leaves the line, and the next may take a free slot
        if waiters and in_flight < W: wake(waiters[0])
    if slot_held[p]:
        slot_held[p] = False
        free_slot()

def track_in_flight(p, f):            # the writer's slot now travels with chunk f
    key = (p, f.group, f.index)
    if key in sent: return free_slot()            # a second copy still in flight: back at once
    sent[key] = now
    after(WINDOW_TIMEOUT, window_timeout, key, now)

def window_release(p, g, i):          # p holds chunk i, from anyone (§4.3)
    if sent.pop((p, g, i), None) is not None: free_slot()

def window_timeout(key, at):
    if sent.get(key) == at:
        del sent[key]
        free_slot()
        if key[1] in planned: origin_acked(key[1], key[2])    # [c3, P4] no claim came in time: released anyway (§5.1)

def free_slot():
    global in_flight
    in_flight -= 1
    if waiters: wake(waiters[0])                  # the first writer in line tries again (§7.2)
```

**The window** bounds the chunks a node has in flight, to all its peers together. It has `W` slots,
shared by all of the node's peers, sized from the node's configured uplink:
what the uplink sends in `RTT_REF` + `TARGET`, in chunks of `CHUNK_BYTES`. A peer's writer takes a
slot before it sends a chunk (`acquire_slot`, §7.2); when none is free it waits in line, first come
first served over the peers, and keeps its place while it waits. The slot then travels with the
chunk until the peer is known to hold it, or until `WINDOW_TIMEOUT` or the queue's closing frees it
(below).

- **What takes a slot:** a chunk sent on the normal lane, push or answer.
- **What gives it back:** a HAVE from that peer that newly covers the chunk's index (§4.3), or
  `WINDOW_TIMEOUT` (500 ms) after sending, or the peer's queue closing. A writer that holds a slot
  and finds no chunk to send gives it back too (`release_unused_slot`).
- **What bypasses it:** urgent control (HAVEs, acknowledgements, decode claims) never waits.
- **At the source,** the first HAVE naming a chunk, from any peer, or else its first copy's window
  timeout, is the chunk's acknowledgement: its announcements go out and it joins the source's HAVE
  (§5.1).
- **A second copy** of a chunk still in flight to the same peer waits for a slot like any chunk, but
  returns it at once: the window counts chunks a peer is not yet known to hold, not bytes on the
  wire.
- **Sizing:** the node sizes the window from its configured uplink. It does not need to be exact.
  *Segmented payload diffusion, card by card* (2026, card 14) gives what a window sized for twice
  the real uplink costs.

### 7.2 Choosing what to send, at the moment of sending [c8, c9, c12, c14]

One writer per peer. A queue entry carries at most one chunk, and may also carry control; the writer
writes it as one frame (§2). A client may merge the control of several entries into one frame, as
§5.1 (HAVEs), §5.4 and §8.3 (announcements) and §6.4 (asks) allow. Each time the previous write to
that peer has completed, and whenever the writer is woken (a slot freed for it, or an urgent entry
arrived), it calls `next_to_send`: an entry to write, `None` when there is nothing to send, or
`WAIT` when it waits in line for a slot.

```python
def next_to_send(p):
    q = queue[p]
    while True:
        if owed_answers[p] and has_room(p):                    # an answer a full queue refused (§4.1)
            enqueue(p, Entry(chunk=pop_owed_answer(p), solicited=True), urgent=False)
        if q.urgent: return with_owed(p, q.urgent.pop(0))      # HAVEs, acks, decode claims: first
        if not q.normal:
            out = with_owed(p, Entry()) if owed[p] else None   # owed offers on their own
            if out: return out
            release_unused_slot(p); return None                # nothing to send: a held slot goes back
        if q.has_chunks() and not slot_held[p]:
            if not acquire_slot(p): return WAIT                # [c14] in line, FIFO over peers; an urgent
            slot_held[p] = True                                #   arrival wakes the writer, which keeps
            continue                                           #   its place in line
        entry = q.normal.pop(rarest(q) if RAREST else 0)       # [c9]
        out = filter_entry(p, entry)                           # [c8, c12], and stale asks
        if not (out and out.chunk): release_unused_slot(p)     # no chunk leaves: the slot goes back
        if out:
            if out.chunk:
                track_in_flight(p, out.chunk); slot_held[p] = False    # [c14] the slot is used
            return with_owed(p, out)                           # owed offers ride along
        # nothing was left of the entry: start again from the urgent lane

def filter_entry(p, entry):
    f = entry.chunk
    if f:
        if CANCEL and peer_has[p][f.group].has(f.index):       # [c8] it became a duplicate
            entry.chunk = None
        elif PROJECT and not entry.solicited and projected(p, f.group):    # [c12]
            entry.chunk = None
            unpush(p, f.group, f.index)                        # [c3] not made: offered instead (§5.2)
        else:
            sent_to[p][f.group].set(f.index)
    for c in entry.iwants():                                   # the asker drops asks for chunks it
        c.ids = [a for a in c.ids                              #   now holds, no longer pulls, or of a
                 if not held(a) and not gated(a) and not expired(group(a))     # group past its lifetime,
                 and not tied_to_root(p, a)]                   #   and asks to a peer whose copy waits
        for a in c.ids:                                        # [c5] the promise starts at the write
            if (a, p) not in promises:
                promises[(a, p)] = now
                after(PROMISE, promise_due, a, p, now)         # 400 ms
    return entry if not entry.is_empty() else None             # control rides on and survives

def with_owed(p, entry):                                       # what is owed to p, one IHAVE per group
    for g in list(owed[p]):
        b = owed[p].pop(g) & ~pushed[p][g] & ~peer_has[p][g].bits
        if entry.chunk and entry.chunk.group == g: b.clear(entry.chunk.index)
        if b: entry.add_ihave(HaveBitmap(group=g, bits=b))
    return entry if not entry.is_empty() else None

def rarest(q):                                                 # [c9]
    best, best_i = inf, 0
    for i, entry in enumerate(q.normal):
        if not entry.chunk: break                              # never overtake a control-only entry
        h = len(holders[entry.chunk.group][entry.chunk.index])
        if h < best: best, best_i = h, i                       # earliest wins ties
    return best_i

def projected(p, g):                                           # [c12]
    has, sent = peer_has[p][g].bits, sent_to[p][g]
    return popcount(has) + FAN_IN * popcount(sent & ~has) >= K(desc[g])
```

**What the writer sends** (`next_to_send`). It first queues an answer it owes, if the queue has room
(§4.1). Urgent entries go first: HAVEs, acknowledgements, decode claims. With nothing on the normal
lane, it sends what it owes the peer on its own, or nothing, and gives back a slot it held. When the
normal lane holds a chunk, the writer takes a slot of the window first (§7.1), or waits in line for
one. It then takes an entry, the rarest chunk first (card 9), and filters it (`filter_entry`):
cancel and projection may drop its chunk, and the asks it carries lose those for chunks the node
holds, no longer pulls, or has let expire, and those to a peer whose copy of the chunk waits (§4.2).
The promise of each ask that leaves starts here (§6.1). If no chunk is left, the slot goes back. What
remains is written, with what is owed to the peer riding along (`with_owed`); if nothing remains, the
writer starts again from the urgent lane.

- **Cancel** [c8] drops a queued chunk if the peer has said it holds it. Answers are cancelled too:
  an ask for a chunk the asker had claimed is never answered (§4.5), so only a HAVE sent after the
  ask cancels the answer.
- **Projection** [c12] skips a push to a peer that will reach K without it. It counts what the peer
  holds, plus twice what we have sent it and it has not yet confirmed (`FAN_IN` = 2 assumes one other
  pusher as fast as us). Answers are never projected away. A skipped push is offered instead
  (§5.2).
- **What is owed** leaves with the next write to the peer. An owed offer (§5.2) skips the queue, so
  a full queue cannot lose it; it rides on whatever the writer sends next, or goes alone, as one
  IHAVE per group, minus what we pushed the peer since and what it has claimed. On the urgent lane
  that puts an IHAVE ahead of queued chunks, which nothing relies on. An owed answer (§4.1) is
  queued as soon as the queue has room, and is then an ordinary answer: cancel drops it if the peer
  has meanwhile claimed the chunk, and it is not counted against `GOSSIP_RETRANSMISSION` again. A
  bit owed lives until it leaves, until the peer claims the chunk, or until the group is dropped or
  expires or the connection closes, with no lifetime of its own: an answer refused through a long
  backpressure must not expire unsent.
- **Rarest at pop** [c9] sends first the queued chunk the fewest of our peers hold. It only reorders
  chunks ahead of the first control-only entry.
- **The slot is taken before the chunk is chosen**, so the window never decides which chunk; the
  three rules above do. When filtering leaves no chunk, the slot goes back and the writer starts
  again, so another peer's writer may take it.

Without cards 8, 9 and 12 the writer sends its queue in order. Without card 14 it sends as fast as
the transport accepts, and the backlog moves into the transport, where none of the rules above can
act.

### 7.3 Below the writer: what the transport holds

The rules above act on a chunk while it is in the node's own queue. Once the writer hands it to the
transport, nothing here reaches it: the library's buffer, the socket, the host's queue and the access
link's queue hold it until it leaves, and a chunk the peer has meanwhile claimed is sent all the same.
This document decides at the moment of sending, so it needs the backlog to be in the queue.

- **A writer should hand a chunk to the transport only while the connection has less than one chunk
  unsent.** The write of §7.2 then completes when the transport has taken all but about one chunk,
  and the queue holds the rest: cancel, projection and rarest-first act on what has not left (§7.2),
  the window counts what no peer is yet known to hold (§7.1), and the queue's order is the link's.
  The rule bounds the library's buffer and nothing below it: the connection's congestion window, the
  socket and the link's queue still hold up to about a round trip of the path plus the connection's
  share of the bottleneck's standing queue, which the window is sized to cover.
- **Not met,** nothing breaks and no peer can tell. The backlog sits below the queue, where cancel and
  projection cannot drop it, and the node sends copies its peers no longer need. The node itself can
  tell: a chunk's write that returns at once on a slow link, or asks for chunks whose pushes it has
  not yet sent.
- **Per transport.** quic-go's stream write blocks until all but one packet of its data is packed, so
  a node on it keeps the rule as it is. Over TCP the kernel's send buffer takes several chunks ahead
  of the link, and go-libp2p's yamux returns a stream write once its yamux frame is in a channel of
  64 yamux frames above the socket: keeping the rule there takes `TCP_NOTSENT_LOWAT` at about
  `CHUNK_BYTES`, or a poll of the socket's unsent bytes, together with a multiplexer whose write
  waits for the socket. A stack that offers neither a blocking write nor a count of its unsent bytes
  cannot keep the rule, and runs with the backlog below the queue.
- **For operators,** not a rule of this protocol: the queue at the access link decides what sits
  below the socket. A deep FIFO, as older modems and a Linux gateway's default transmit queue have,
  holds hundreds of milliseconds to a second of a slow uplink, lets the congestion window fill it,
  and stretches the window's holds past `WINDOW_TIMEOUT`. An AQM at the bottleneck (fq_codel, cake or
  PIE, as SQM routers and DOCSIS 3.1 modems run) keeps the standing queue at a few milliseconds and
  moves the backlog up to the queue, where this protocol drops it: cancel [c8] and the group's expiry
  are the drops it needs.

## 8. State, limits and constants

### 8.1 State and its lifetime

| state | kept per | lives | when it goes |
|---|---|---|---|
| own chunks, ids, `mine`, `received`, `desc`, `state` | group | its active lifetime: `GROUP_TTL` after its last chunk arrived or it completed, ended sooner if its slot leaves the live window | at expiry, leaving a tombstone (the group's key and slot) until its slot leaves the live window (where groups have no slot, for `TOMBSTONE_TTL`) |
| `origin` | group we publish | the group's active lifetime | with the group [P4] |
| `planned` | group we publish | the group's active lifetime | with the group [c3] |
| `asked_at` | ask | `IWANT_WINDOW` after the last ask | at expiry, or when the chunk arrives |
| `peer_has` (and `holders`, `sent_to` for that peer) | connection and group | `HAVE_TTL` after the peer's last HAVE for the group | at expiry, or when the connection closes; the peer leaves `holders` |
| `pushed` (with `first_push`) | connection and group | `PUSH_TTL` after the last push | at expiry, or when the connection closes |
| `unwanted`, `serve_count` | connection | stock | stock, or when the connection closes |
| offers (`offers`, and `offered` per connection and group) | ask and announcer | 30 s after the announcer's last offer of the group | when the chunk arrives, at expiry or with a dropped tie (`drop_offer`, the announcer's asks of the chunk with them, §6.1), when the group's count, once known, has not the index (`drop_beyond`, §4.2), or when the announcer's connection closes |
| `tried` | ask and announcer | 30 s | when the chunk arrives, at expiry, or when the announcer's connection closes |
| `asked_parked` | chunk (group and index) and announcer | 30 s, as `tried` | as `tried` |
| `last_resort_armed` | chunk | one timer, until it fires | — |
| the secret of `own_order` (§6.1) | node | while the node runs | never sent; a restart draws another |
| `ihave_frames`, `ihave_asked` | connection | one heartbeat | at the next heartbeat, or when the connection closes |
| `held_back` | chunk (group and index) of an admitted group | until the next heartbeat | at that heartbeat, which runs the retry for it (the retry checks expiry, §6.1) |
| promises | ask and peer | `PROMISE` | when a copy that passes level 1 arrives, the peer's copy waits for its block (a tie, §4.2), the peer's offers of the chunk are dropped (`drop_offer`, §6.1), the group completes or expires, or the peer's connection closes |
| `owed`, `owed_answers` | connection and group | until they leave | when the peer claims the chunk, when the group is dropped or expires, or when the connection closes |
| `park` | peer id and group | `PARK_TTL` | at expiry; kept across reconnections, as scores are |
| deferred chunks | block root | until the block installs | when their slot leaves the live window or their group expires, at the next heartbeat (`drop_stale_waits`); reservations are released |
| `tied`, with `tie_slot` (the slot a connection's first copy named, per root and connection) | block root, connection and group | until the root installs | released at its installation; dropped when that slot leaves the live window or its group expires, at the next heartbeat (`drop_stale_waits`), or where the root's bid commits another group (`drop_tie`); an index the group's count, once known, has not (`drop_beyond`); when the connection closes |
| window slots | node | until a covering HAVE | `WINDOW_TIMEOUT`, or when the peer's queue closes |

- **Per-connection state** is reset when the connection closes. A restarted peer usually keeps its
  peer id, so this state must not be keyed by peer id alone.
- **Within a group's active lifetime a node's holdings only grow:** it never drops a chunk it has
  claimed (§4.5). Past it, the group is expired for good (`expired`): the node keeps only its key and
  slot, as a tombstone, until the live window has passed it (below), never asks for its chunks
  again, and ignores controls that name it, without penalty.
- **The live window.** A slot is live at a node from its start, as the node's clock shows it with
  consensus gossip's allowance for clock disparity (`MAXIMUM_GOSSIP_CLOCK_DISPARITY`), until it is
  `LIVE_WINDOW` slots behind the node's current slot (`live`): a chunk of a later slot is ignored, as
  a block from a future slot is. The window only moves forward: a node's current slot never goes
  back, even when its clock does. A group's slot is fixed by its key (§1): it is the slot of every
  block whose bid commits the group, which every chunk names and level 1 checks (§3). A group's
  active lifetime ends when its slot leaves the window, if it has not ended before, and a chunk
  whose slot has left the window is ignored before level 1 (§4.2). The tombstone is kept until the
  group's slot leaves the window, and then goes: from then on the window keeps the group out. A
  node that holds nothing of a group still knows the group's slot wherever it could take the group
  up: a chunk names it, and an ask needs an installed block whose bid commits the group (§4.4).
- **How long a window.** `LIVE_WINDOW` sets how long diffusion works on a group: past it a node
  neither takes up, asks for nor serves the group. It must exceed what a group needs to reach every
  honest node, counted from the start of its slot: the block's propagation, which comes first, the
  group's diffusion, and the clock disparity between nodes. A node still short of the group by then
  gets the payload by other means. Above that, a longer window costs only state: a node keeps the
  groups, tombstones and deferred chunks of `LIVE_WINDOW` slots, besides what §8.2 bounds for groups
  not yet tied to a block. Nodes need not agree on `LIVE_WINDOW` or on the current slot.
- **Without a slot.** Where groups carry no slot, which no group of this document does, there is no
  window, and the tombstone is kept for `TOMBSTONE_TTL` after the expiry instead. It must outlast
  the node's claims of the group: longer than a HAVE already queued can wait, plus the time a frame
  takes to reach the peer and be handled, plus the peer's `HAVE_TTL` and one of its heartbeats. This
  document bounds neither of the first two and leaves the third to each node, so a deployment that
  relies on this fallback states all three; discarding the group's queued HAVEs at its expiry
  removes the first. Once the tombstone has gone, the group can be taken up again: a late
  announcement can make the node pull it a second time.
- **At a group's expiry** its pull state goes with it: its offers, `tried`, `asked_at`,
  `asked_parked`, promises, what is owed of it, and its queued chunks, IHAVEs and IWANTs
  (`discard_queued`, as at `drop_group`). Its chunks leave the gossip history and its paced jobs go
  (`gossip_history.remove_group`, `discard_paced`), so nothing announces it afterwards, also when
  the window ends it sooner than `GROUP_TTL` would. Timers already armed then find nothing to do:
  the retry and the writer's ask filter check expiry too (§6.1, §7.2), a decode that returns after
  it is dropped (§4.6), and so is a chunk whose validation returns after it or whose block installs
  after it (§4.2). Window slots come back the usual ways.
- **Lifetimes counted in heartbeats** (`HAVE_TTL`, `PUSH_TTL`) are counted by the heartbeat, not
  timed exactly: an entry lives that many heartbeats after it was last refreshed.

**Helpers not written out.** *Chunks and groups:*
- `open_group`: records the group's committed descriptor in `desc` and sets `state` to COLLECTING;
- `received`: the chunks a node got from the network, as against those it rebuilt;
- `expired`: the group is past its active lifetime: only its tombstone is left, or, once its slot
  has left the live window, nothing (§8.1);
- `live`: the slot is in the node's live window (§8.1);
- `store`: keeps a chunk in `chunks` and records its id in `known_id`;
- `accepted`: the id was stored;
- `held`: an ask's chunk is in `mine`;
- `resolve` and `chunk_of`: an ask's id and stored chunk, at an index the node holds, received or
  rebuilt; nothing for a dropped group;
- `group_index`, `group` and `index`: the group and index an ask names, a WantIndex or a structured
  id, or just one of them;
- `authenticable`: an installed block's bid commits the group (its group id at the block's slot
  gives the group's key);
- `bid_group`: the key of the group the bid of the block with this root commits;
- `decode_and_reencode`: §1's decoding: every chunk of the group by index, as the source built it,
  proof included, each naming the block the decode's chunks name, or one of them where they name
  several (§4.6); None if the root differs;
- `payload_of`: the decompressed body;
- `close_promises_of_group`: §6.1's promises for a whole group;
- `discard_queued`: removes a group's chunks, IHAVEs and IWANTs from every queue, and what is owed of
  it, keeping HAVEs;
- `gossip_history.remove_group` and `discard_paced`: drop a group from the gossip history and from
  paced jobs;
- `deliver`: hands the body to the application for level 3;
- and the codec functions of §1.

*Peers and messages:*
- `seen` and `mark_seen`: the stock seen cache;
- `pending_ids`: the ids of deferred chunks;
- `valid_have`, `reserve`, `release`, `admitted` and `listed`: the checks and reservations of §8.2;
  `admitted`: a chunk's group within the peer's limits; `listed`: how many ordered offer lists an
  announcer is in;
- `Entry`: a queue entry, at most one chunk plus control; `add_ihave` adds an IHAVE to its control;
- `enqueue`: into the bounded per-peer queue of §7; true if the queue admitted the entry;
- `has_room`: the queue would admit one now;
- `pop_owed_answer`: takes the lowest owed answer and returns its chunk;
- `handle_graft_prune`: stock;
- `penalise`: the client's peer scoring, if it has one; a client may ignore it;
- `tiebreak` and `peer_id_bytes`: §5.3;
- `own_order`: §6.1's list of peers in the node's own order for an ask's chunk. Any order that no
  peer can predict or arrange will do. The reference, for comparing implementations in tests, sorts
  by the first 8 bytes, read little-endian, of HMAC-SHA-256(secret, group ‖ index as uint32
  little-endian ‖ peer id), larger first, then the larger peer id; `toy/own_order_known.py` has how
  a test derives the secret, and a known answer;
- `group_bits`: splits gossip ids by group into bitmaps;
- and the stock `topic_peers`, `connected_topic_peers`, `gossip_eligible`, `connected`,
  `installed_block` (the installed block with the root, or nothing; the slot a copy names is checked
  against the block's at level 1, §3) and `block_root`.

*The writer:*
- `slot_held`: whether a peer's writer holds a slot it has not used; false at first;
- `wake`: runs a peer's writer again (§7.2);
- `WAIT`: what `next_to_send` returns while the writer waits in line.

*Timing and sets:*
- `after`: a timer;
- `start`: runs a task off the chunk path, for as long as the task takes: for level 2, a decode, a
  few milliseconds with an optimised codec, which this document does not fix;
- `shuffled` and `sample_without_replacement`;
- the bitmap operations, among them `bitmap(indices)`, which builds a bitmap from a set of indices,
  `copy`, and `clear(i)`.

A group or per-peer entry that does not exist reads as empty, with `stop_pull` false, and reading it
allocates nothing: the admission checks of §8.2 come before any state is created.

#### Rationale

**Why an expired group stays expired.** A node's claims of a group outlive the group's expiry: a
HAVE still queued leaves after it, and a peer keeps the claim for `HAVE_TTL`. A node that took the
group up again could ask a peer for a chunk the peer still holds as its claim, and be penalised for
an honest ask (§4.5). The window rules this out without a bound on queues, the transport or clocks.
Nodes need not agree on `LIVE_WINDOW` or on the current slot: each node's own window keeps it from
taking a group up again, and a group expired at one node and not at another is expiry at different
times, which §4.5 already allows. The claim rule needs no value of `LIVE_WINDOW`, only a window that
moves forward.

**A group's slot fixed by its key.** The window needs a group's slot to be fixed, and the key fixes
it (§1). Named by its group id alone, a group could come back: a bid of a later slot could commit its
descriptor, which only a dishonest builder does, and the group would be live again until its payload
failed level 3.

### 8.2 Limits

A node checks a message's shape before it allocates state for it.

| what | limit | at the limit |
|---|---|---|
| a HAVE bitmap, and an IHAVE's (§4.4) | `MAX_HAVE_BYTES` (8192 indices); no index at or beyond N once the descriptor is known | the HAVE, or the IHAVE's bitmap, is ignored and counts against the sender |
| a descriptor | `valid_descriptor` (§1) | the chunk is rejected |
| groups not yet bound to an installed block, named in a peer's HAVEs, IHAVEs or deferred chunks | `MAX_PENDING_GROUPS` per peer | the peer's further unknown groups are ignored until one resolves or expires |
| deferred chunks | a bounded store with per-peer reservations | the peer's further deferred chunks are dropped, neither claimed nor forwarded; each ties the peer to the root it names, as a kept one does (§4.2) |
| ties (§4.2) | per peer, at most `MAX_PENDING_GROUPS` roots and groups not yet installed; an index below `MAX_PLAIN_CHUNKS`, and below N where the group's descriptor is known | a copy beyond them ties nothing, and is kept or refused as any deferred copy |
| offers | 16 announcers per id in the ordered list, an announcer in at most 256 lists; one `offered` bitmap per connection and admitted group, of at most `MAX_HAVE_BYTES` | an announcer's further ids are not listed, and its offers of them are kept in `offered` only; a peer's offers for groups beyond `MAX_PENDING_GROUPS` are ignored, as its HAVEs are |
| IHAVE handling | `MAX_IHAVE_MESSAGES` IHAVE-bearing frames per peer and heartbeat, and `MAX_IHAVE_LENGTH` ids asked of the peer in reply to its IHAVEs per heartbeat | the peer's further announcements are recorded, and what the node would ask of it waits for the next heartbeat (§4.4) |
| per-peer queue | client-chosen, shared by both lanes | a new entry is dropped, urgent control included: urgency orders dispatch, not admission. A dropped HAVE costs its window slot a timeout |

`MAX_PENDING_GROUPS`, the deferred store's sizes and the two IHAVE limits are the client's to set,
and so are the offers' 16 and 256. §8.3 gives defaults for the IHAVE limits and the offers; what
this document fixes is the behaviour at the limit. Every offer for an admitted group is kept
(§6.1): per peer at most (`MAX_PENDING_GROUPS` + the live groups) × 1 KiB of `offered`, the same
order as `peer_has`.
Chunks are deduplicated by id and, once accepted, by index: only one content per index can pass
the proof, so a forged variant costs one proof check and counts against its sender.

### 8.3 Constants

The constants are of three kinds, by what they leave to a node:
- **Limits** are the same at every node: they cap what §1 and §2 accept, and a descriptor, chunk
  or bitmap beyond one is invalid. Changing a limit changes the protocol. §8.2 says what a node does
  at each, and which limits on its own state are the client's to set.
- **Bounds** are each node's to set, within a bound that another node, or a property of this
  document, needs. Each is given with its bound and with what needs it.
- **Defaults** are each node's own. Nodes with other values work together: a value changes how the
  payload spreads, how fast and at what cost, not whether a node follows the protocol.

The values given are this document's reference values. Most are those of the implementation the
measurements ran on, and §9 says where the measured runs differ. A value measured on one network is
not shown to carry over to another.

**Limits.** Every node also shares what §1 to §3 fix besides these, among them the descriptor's
versions and code, N = 2K for a coded group, the tree and the ids.

| name | value | card | why |
|---|---|---|---|
| `MAX_CHUNKS` | 256 | 6 | codec limit; above 2 MiB of SSZ, at the default `UNIT`, the group is plain |
| `MAX_PLAIN_CHUNKS` | 8192 | 1 | every group fits one HAVE bitmap |
| `MAX_SEGMENT_SIZE` | 32 KiB | 1 | twice the default `UNIT`, above snappy's worst-case expansion; a builder's own `UNIT` does not change it |
| `MAX_HAVE_BYTES` | 1024 | 7 | 8192 indices |

**Bounds.**

| name | bound | value | card | why |
|---|---|---|---|---|
| `R`, `R_FAST` | at least 1 | 2, 6 | 3, 11, 17 | a source that pushes nothing offers its mesh no chunk, since §5.1's offers wait for a chunk's acknowledgement: only a peer that joins its mesh (§5.4), or heartbeat gossip outside it (§6.4), is offered anything, so the group's diffusion may never start. §5.3's guard also reads the first push to a peer, which a budget of 0 never makes. 2: the coded group needs less fan-in; 3 without the code at 1 MiB. 6: the knee, beyond which receivers' downlinks bind |
| `GUARD_GRACE` | longer than a push takes to leave this node's queue and reach the peer, plus the peer's first HAVE coming back: about the round trip to the peer where queues are short | 200 ms | 16 | so that an honest peer is not demoted before its first HAVE can arrive (§5.3). A peer whose copies wait for their block sends no HAVE until it installs (§4.2), and one whose queue to this node is full can drop its HAVE (§8.2): either can be demoted meanwhile, until its first HAVE |
| `GOSSIP_RETRANSMISSION` | at least 3 | 3, stock gossipsub | – | while its park and the last resort's count last, §6.1's rules ask a provider for a chunk at most twice before the root its copies name installs, and leave its third answer for after the switch to that block (§6.1's Rationale) |
| `GROUP_TTL` | at least 7 heartbeats and the seen cache's lifetime, after the group's last chunk or its completion | not fixed | – | so that a group outlives its diffusion. That is not assured: a decode, which this document does not bound, can outlast the group (§4.6), as can what is still queued for it (§7.2), and the live window can end the group sooner (§8.1) |
| `LIVE_WINDOW` | more slots than a group needs to reach every honest node from the start of its slot (the block's propagation, the group's diffusion, the clock disparity), and no more than a node can keep groups, tombstones and deferred chunks for (§8.2 bounds the groups not yet tied to a block) | not fixed | – | diffusion's deadline; an expired group never comes back (§8.1) |
| `TOMBSTONE_TTL` | only where groups have no slot: more than a queued HAVE can wait, plus a frame's time to its peer, plus the peer's `HAVE_TTL` and one of its heartbeats, after the expiry; a deployment that relies on it states these (§8.1) | not fixed | – | the tombstone outlasts the node's claims (§8.1) |

**Defaults.** `UNIT` is the builder's: receivers check the group a cut gives, not the value (§1).
The others are each node's. They are values, and the rules they enter stay rules (§4 to §7). Three
of §6.1's could be read as values:
- one broken promise parks a peer, for its group only;
- every offer for an admitted group is kept;
- the last resort asks each parked announcer once more per chunk, after `PROMISE` × 2ⁿ for the n-th.
  At the default `PROMISE` that allows at most six such asks for a chunk within the 30 s an offer
  lives, while no count is reset.

`GOSSIP_RETRANSMISSION`'s bound counts on the first and the third, while a park and the last
resort's count last.

| name | value | card | why |
|---|---|---|---|
| `UNIT` | 16 KiB | 1 | the unit where variant A's latency reached its floor (*What segmented payload diffusion is made of*) |
| `FAST_UPLINK` | 500 Mbps | 17 | the configured uplink from which a node pushes `R_FAST` (§5.2) |
| `STRIPE_UPLINK` | 1 Gbps (configured uplink) | 13 | where striping's gain is measured; the first hop suggests it starts near eight times the peers' uplink, 400 Mbps in the all-home network |
| `IWANT_WINDOW` | 200 ms | 5 | one ask in flight per id, then move on |
| `RETRY_SLACK` | 5 ms | 5 | the retry looks just after the ask's window has closed |
| `PROMISE` | 400 ms | 5 | a late answer is still taken; after this the peer is parked, which affects only this node's asks of it (§6.1) |
| `PARK_TTL` | 30 s | 5 | bounds capture; a park is per group, so a slow peer on one payload is not parked for the next |
| offers | 16 per id tried in order, 256 lists per peer, 30 s after the announcer's last offer of the group | 5 | bounded memory of who announced |
| `FAN_IN` | 2 | 12 | one other pusher assumed as fast as us |
| `RTT_REF`, `TARGET` | 112 ms, 20 ms | 14 | the network's mean round trip, plus a small queue |
| `CHUNK_BYTES` | ≈ 12 KB | 14 | the encoded chunk at 1 MiB and the default `UNIT` |
| `WINDOW_TIMEOUT` | 500 ms | 14 | a lost acknowledgement frees its slot |
| pace tick | heartbeat / 16 = 43.75 ms | 15 | one announcement per tick |
| `MAX_IHAVE_MESSAGES`, `MAX_IHAVE_LENGTH` | 4096 frames, 5000 ids, per peer and heartbeat | 3, 7 | a limit delays asks and loses no offer (§4.4). The values are those the measurements ran with, 5000 being stock gossipsub's; §9 says where the measured handler differs. At these values the toy's recorded cells hold back no ask (`toy/README.md`). A limit below what a peer sends within a heartbeat, up to an IHAVE-bearing frame per chunk it announces and as many asks, holds some of its asks back to the next heartbeat: stock gossipsub's 10 frames would hold back most of a group's announcements, which come one per chunk. Its 5000 ids are kept, although in a router shared with other topics they count every topic's asks. Batching a peer's announcements keeps the frame count low |
| `D_LAZY`, `GOSSIP_FACTOR` | 6, 0.25 | – | stock gossipsub |
| `HAVE_TTL` | 3 heartbeats after the peer's last HAVE for the group | 7 | stock IDONTWANT expiry; where groups have no slot, a peer's `TOMBSTONE_TTL` has to outlast it (§8.1) |
| `PUSH_TTL` | 6 heartbeats after the last push | 16 | the message cache's length |
| heartbeat, mesh, cache | 700 ms, D = 8, 6 / 3 heartbeats | – | Prysm's gossipsub settings |

**Open: the push degree against payload size.** R is 2 at 1 MiB. The rule should be keyed on K
rather than on the uncompressed size, and is not yet fixed. §9 says which degrees the measurements
used at other sizes.

#### Rationale

**Three kinds, not one table.** In one table, a node's own choice, measured on one network, reads
as a rule of the protocol, as a limit does. Apart, a limit says what every node accepts, a bound
says how far a node may go and what needs the bound, and a default says where a node is free and
gives a reference value. A bound in place of a value also lets an argument hold for every value
within it, each property needing only its side: reaching every honest node needs `LIVE_WINDOW`'s
lower bound, bounded state its upper one, and the claim rule neither, only a window that moves
forward (§8.1).

**What makes a bound.** A constant is a bound when a guarantee of this document needs its value in a
range. A peer's outcome can depend on it: `GUARD_GRACE` decides when a peer that has sent no HAVE is
pushed last, and a peer's asks need the answers `GOSSIP_RETRANSMISSION` allows. So can the group's
diffusion (`R` at the source, `GROUP_TTL`, `LIVE_WINDOW`), or the node's own state and standing
with its peers (`LIVE_WINDOW`, `TOMBSTONE_TTL`). `PROMISE` and `PARK_TTL` are defaults, although
they decide how a node treats a peer: a parked peer is only not asked, except once more per chunk
by the last resort, and its pushes and the node's answers to it go on (§6.1). A promise that falls
due too soon costs the node that sets it a provider for the group, and can bring the last resort's
ask while the first answer is still on its way; `promise_due` penalises no one. A client that also
scored peers by this promise would make it a bound.

## 9. As measured: where the research implementation differs

The measurements in the posts this document accompanies come from a research harness. This section
lists where the harness does something this document does not specify, and what that means for the
numbers. Figures 4 and 5 of
[*SEACAST: fast, lean broadcast for Ethereum, with an executable spec and a formal model*](https://ethresear.ch/t/seacast-fast-lean-broadcast-for-ethereum-with-an-executable-spec-and-a-formal-model/26167)
(2026) were rerun on an implementation with v0.5's rules and the source's paced HAVE; that
post's other figures, and the earlier posts', come from the implementation before them. Where the
rerun does as this document does, the entry says so.

**Harness shortcuts, not part of the protocol.**
- *No validation.* Chunks were accepted, claimed and forwarded on arrival, with no proof check and no
  block gate (section 3); the simulated slot has no blocks. The measurements therefore exclude block
  propagation, gated forwarding and proof validation, and do not quantify what those add. With the block
  installed, the proof check before a claim adds microseconds; a chunk ahead of its block waits for
  it.
- *The wire format.* The measured chunks used a 101-byte structured id (slot, a synthetic block
  root, group, index, content id) and a custom segment encoding inside an SSZ byte field. Their
  descriptor had no `encoding` field, compress-first being configured outside, so their group ids
  differ from §1's. The payload was generated bytes, not a serialised
  `ExecutionPayloadSegmentBody`. The longer id inflates control bytes against the 56-byte id of
  section 2; HAVE and WANT strings have their own lengths. Each chunk carried the descriptor
  (design A).
- *K was fixed at 64* rather than derived from `UNIT`. At 1 MiB and the default `UNIT` both give 64.
  The codec allowed up to 16384 chunks, more than a HAVE bitmap can name; §1 caps a group at 8192.
- *No decode.* Completion was counted at K distinct received chunks, where the decode claim went
  out, as in this document (§4.6). Decoding, re-encoding, decompression and the application's checks
  did not run, so delivery's latency is not in the numbers; optimised implementations decode and
  check in a few milliseconds. No chunk was rebuilt, so the measured runs did not repair (§4.6): a
  decoded node pushed, served and announced only chunks it had received. Repair was measured in
  separate runs, on top of tier 4, with each node handed the chunks its decode would rebuild 5 ms
  after its K-th chunk (*What a forwarding node checks, and when it decodes*, 2026). On the post's clean
  networks it should have little to act on, since every chunk is released and a rebuilt chunk is
  one more copy of a plentiful one; on thin links with every chunk released it changed nothing
  measurable.
- *Stop-pull* ran as a harness gate that flips at completion. The decode claim already makes every
  index of the group non-askable, so the effect is the one in §6.2.
- *The fast class* was read from the simulator's link settings, and the window's round trip and
  chunk size from the cell's configuration. A node would configure its uplink.
- *Striping* was set on or off per cell; this document selects it by the configured uplink
  (`STRIPE_UPLINK`).
- *Per-peer dispatch state* existed from the first send only because a measurement option set it
  up. Without it, a peer's first chunks would have skipped rarest-first, projection and the window.
  This document creates it with the connection.
- *The random heartbeat phase* was overwritten on the segmented arms, so every node's first
  heartbeat fell at the same offset from its start. Paced gossip's ticks follow the heartbeat.
- *Random draws* (the lower-half draw, shuffles) used the process-global generator, with no seed
  the harness controlled, and the source enqueued its targets in the order of a Go map's iteration;
  §5.1 keeps the selector's order.
- *The guard and the window.* The measured implementation required the window for card 16's guard,
  so the runs without card 14 also ran without the guard. The guard needs only HAVEs (§0).

**Behaviours that shaped the numbers, as measured, and where this document departs.**
- *Announcing on arrival.* With no validation, a node claimed a chunk as it arrived. This document
  claims it after level 1 (§4.2).
- *Announcing after the decode claim.* A measured node announced every new chunk to its mesh, as
  stock IDONTWANT does for every new message, also after its decode claim had named every chunk of
  the group. This document acknowledges such a chunk to its sender only (§4.2): the mesh learns
  nothing from the HAVE. The extra HAVEs are about a fifth of the honest nodes' HAVEs at about 70
  connections, and more with a datacenter builder, whose fast nodes deliver more chunks after the
  decode. With the measured rule, the toy sends as many HAVEs as the implementation, and its tail
  does not change. The rerun of Figures 4 and 5 still announces these chunks.
- *The source's HAVE* went out once per chunk as each was added to the batch: N cumulative HAVEs to
  each mesh peer, all before the data, which names the source to its mesh. This document paces it
  instead (§5.1, [P4]). A change of 2026-10-07 makes the implementation send one HAVE before the
  data by default, and pace it as an option (`SEGMENT_SRC_HAVE=paced`), measured at no cost in
  delivery. The rerun of Figures 4 and 5
  paces it at the write; this document's HAVE grows at the acknowledgement instead (§5.1), about a
  round trip later.
- *The source announced at publish.* The implementation queues a chunk's offers to the mesh peers it
  does not push it to in the same step as the pushes; this document queues them at the chunk's
  acknowledgement (§5.1). Over quic-go, whose stream write blocks until all but one packet is
  packed, the offers waited behind the pushes in each peer's queue and drew few asks. Over a
  transport that takes the whole batch at once, offers made at publish drew asks for chunks whose
  pushes were still queued, an order of magnitude more asks at the source than the harness saw
  (the cross-check of 2026-10-07, on the toy).
- *The transport below the writer* was quic-go's: the measured runs kept §7.3's rule by the
  library's behaviour, not by a rule, and the harness's per-peer queue held the backlog.
- *The push degree by payload size.* The measured tier 4 runs at R = 2 at 1 MiB, and was swept over
  sizes with R = 4, 3, 2 by size (4 at 128 KiB). This document fixes no rule by size (§8.3).
- *The sender counts as a holder* in a forwarding node's budget (§5.2), so R = 2 means one further push per
  received chunk. This is what was measured. The sender is also excluded from the candidates here;
  in the code it could take a budget slot and then be skipped, which is rare.
- *Control waits behind the window.* While chunks are queued to a peer, that peer's IHAVE, IWANT,
  GRAFT and PRUNE on the normal lane wait for a slot, though they do not keep it. A writer waiting
  for a slot also lost its place in line whenever an urgent message arrived for it; this document
  keeps its place (§7.1). Whether control should bypass the window is open. At home only the
  source's window filled in the measured cells, so the other nodes were not affected.
- *A slot frees when the peer holds the chunk from anyone,* not when our copy arrives. A decode
  claim frees all of that peer's slots at once.
- *Holder counts for rarest-first* only ever increased: a departed peer's claims were dropped, but
  not its share of the counts, and a peer whose HAVE expired and was re-sent was counted twice. This
  document counts distinct live holders.
- *An ask by index for a chunk the asker had claimed* was answered: the measured node cleared that
  claim in the asker's send queue, for cancel and projection only, and kept it everywhere else. This
  document drops such an ask (§4.5), and the asker drops queued asks for chunks it holds (§7.2). The
  asker's queue kept such asks, and its HAVE, on the urgent lane, overtook them: the answers arrived
  as duplicates, 0.1 % of them at home and 2 to 3 % with a datacenter builder. A change of 2026-10-07
  makes the implementation do as this document does; the rerun of Figures 4 and 5 has it.
- *Promises were not closed on decode* for the park. Asks still open when a node decoded broke at
  400 ms and parked the asked peers for the completed group only, which changed no later decision.
  This document closes them.
- *The offer-table retry* picked untried announcers in peer-id order; this document takes the
  earliest to have announced among the announcers admitted to a chunk's ordered list (at most 16,
  and an announcer in at most 256 lists, §8.2), and the others after them in the node's own order
  (§6.1). A retry that found every announcer parked stopped, and the chunk
  waited for a fresh announcement; this document asks each parked announcer once more, later, and
  keeps every offer (§6.1). The rerun of Figures 4 and 5 does as this document does, but for the
  order beyond the list, which is newer than the rerun.
- *An ask dropped at a full queue* was lost, and its promise still fell due. This document starts
  the promise when the ask is written (§7.2), as the rerun of Figures 4 and 5 does.
- *A push that did not happen.* A push that projection skipped was not announced in its place: the
  implementation's comment has the peer pull the chunk from others that announced it, and where
  none did, the peer stayed short. This document offers it (§5.2). A push, offer or answer that a
  full queue refused was dropped, as an ask was; this document owes it (§7.2). The rerun of
  Figures 4 and 5 does both.
- *Rules added after v0.4,* from a model of this document's rules: the three above; no ask before
  the block (§3, §4.4) and a refused deferred copy counted as its sender's offer (§4.2; since
  replaced by ties, below), which need blocks, and the measured runs had none; promises that close with their connection (§6.1); and
  expiry checked by the retry, the writer's ask filter and a returning decode (§6.1, §7.2, §4.6).
  The implementation behind the earlier figures predates them. The rerun of Figures 4 and 5 has
  each of them that has a counterpart in the implementation. Two have none: the implementation keeps
  no deferred copies, and it does not decode, so the expiry check of a returning decode falls to its
  rebuild step, which the measured runs do not reach. Of the rest, three act in those runs: the
  promise from the write, the offer of a skipped push, and the second ask of parked announcers. The
  runs have no blocks, no expiry within a payload's lifetime and no disconnects, so the others do
  nothing there. Against the same runs without these rules, the times and bytes stayed within the
  spread between runs, and honest nodes parked honest peers less often.
- *The IHAVE limits.* The measured handler allowed 4096 control-bearing frames per peer per
  heartbeat, a counter that also counts frames carrying other control, and asked a peer for at most
  the stock 5000 ids a heartbeat; as in stock gossipsub, an IHAVE that arrived over either limit was
  ignored, and so were the ids of one IHAVE after its 5000th. This document counts only
  IHAVE-bearing frames, reads every entry, and records an IHAVE over either limit and retries its
  asks at the next heartbeat (§4.4), so the two differ only in a heartbeat in which a peer reaches a
  limit, or for an IHAVE of more than 5000 ids. The rerun's source announces a chunk only to the
  mesh peers it did not choose for a push, as §5.1 does.
- *The live window and the group's key* (§8.1, §1) came after the implementation measured, its
  rerun included. The measured runs have no blocks and no expiry within a payload's lifetime, so
  neither would act there: in those runs the key only renames groups, which in the toy moves the
  recorded cells as any renaming does (`toy/README.md`).
- *A peer that joins the mesh* (§5.4) came after the implementation measured, its rerun included.
  No connection closes in the measured runs, and their meshes settle before the first publish (the
  harness waits for the grafting to finish), so the rule would act there only where gossipsub's
  upkeep grafts a peer during a payload's lifetime, which the runs did not count.
- *Ties, no second ask of a peer at once, and asks that go with their announcer's offers* (§4.2,
  §6.1), came after the implementation measured, its rerun included; ties replace v0.5's offer of a
  refused copy. The measured runs have no blocks, so no copy waits there and nothing is tied, and
  their groups complete long before an offer's 30 s, so no ask goes with dropped offers there or in
  the toy. The rule against a second ask acts in ordinary runs:
  in the toy's twelve cells at seeds 7 to 9 it changes the events of 31 of the 36 runs, and moves
  the warm medians by −8 to +6 ms at p50, −15 to +34 ms at p99 and −0.04 to +0.03 copies, where a
  change that alters no rule moves them by −1 to +5 ms, −13 to +10 ms and −0.05 to +0.01.
- *Clearing promises on decode* in the stock gossip tracer had no effect in the measured cells,
  because the harness runs no peer scoring. In a client that scores peers it keeps honest peers from
  being penalised for asks the decode made unnecessary.
- *No block evidence.* Neither push selector checked that its target holds the block (§3); the
  measured runs had no blocks.
- *Serving.* A measured node served chunks from its message cache, six heartbeats long. This
  document serves a group's chunks for the group's active lifetime (§8.1).
- *The pacer* skipped a job within the same tick when per-id holding evidence had removed all its
  ids; only a job emptied while its ids became bitmaps consumed the tick. This document consumes
  the tick in both cases.
- *Per-peer tables:* offers, retries and answer counts were keyed by peer id and survived a
  reconnection. §8.1 resets them with the connection. In the rerun of Figures 4 and 5 a closed
  connection's promises, offers and tried asks go with it; its answer counts still survive.

## Glossary

The document's terms, each with the section that defines it.

- **acknowledgement**: the HAVE a node sends the peer a chunk came from (§4.2); it gives back the
  window slot of that copy (§7.1). At the source, a chunk's acknowledgement is the first HAVE naming
  it from any peer, or its first copy's window timeout (§5.1).
- **announce**: to send an IHAVE bitmap naming chunks a node can send (§2, §5.2); the peer that
  announced a chunk is its **announcer**, and the announcement its **offer** (§6.1). Where §9 says a
  node *announced* a chunk it held, as stock IDONTWANT does, it means its HAVE: a claim (below),
  not an announcement in this sense.
- **ask**: an IWANT for one chunk, by its id or by group and index (`WantIndex`) (§2, §6.1). An ask
  is **outstanding** while it is queued to the peer or its promise is open (§6.1).
- **budget**: the most mesh peers a forwarding node pushes a chunk to: `R_NODE` less the mesh peers
  known to hold it, and never below zero (§5.2).
- **card**: one mechanism of the design, numbered; a **tier** is the set of cards it enables, and
  the tiers are nested (§0). A comment `# [c8]` tags the code of card 8.
- **chunk**: one piece of the payload, coded from tier 3 on, with its Merkle proof: the unit on the
  wire (§1, §2).
- **claim**: a node's statement, in its HAVE, that it holds a chunk. A chunk it receives is claimed
  only once it passes level 1 (§4.2); the **decode claim** names all N chunks of a group at the K-th
  chunk received, before decoding (§4.6). A source's HAVE names the chunks acknowledged so far
  (§5.1).
- **deferred**: a copy of a chunk whose block is not installed yet; it waits in a bounded store, or
  is refused, and within §8.2's limits ties its sender either way (§4.2).
- **descriptor**: the `SegmentDescriptor` a bid commits to, which says how the payload was cut and
  coded (§1).
- **expired**: a group past its active lifetime. Its tombstone keeps it out until its slot leaves
  the live window, and the window from then on, so it never comes back (§8.1). Groups without a
  slot, which this document does not have, keep a tombstone for `TOMBSTONE_TTL` instead.
- **forward**: to pass on a chunk a node has stored at an index it had not received: push it to some
  mesh peers and announce it to the others (§5.2).
- **frame**: one gossipsub `RPC`, the protobuf a peer writes on its stream, with the messages and
  control fields it carries (§2). Not a frame of the layers below.
- **group**: the N chunks of one payload, named in diffusion by its **key**, the group id at the
  block's slot (§1).
- **HAVE**: a bitmap of the chunks of one group a node holds, carried in an IDONTWANT (§2, §4.3).
  A peer whose HAVE names a chunk is one of its **holders**.
- **installed**: a block validated and applied locally (§3).
- **K, N**: a group's data chunks, and all its chunks, parity included (§1).
- **last resort**: one more ask of each parked announcer of a chunk, after waits that double (§6.1).
- **ledger**: what was offered of a group and is not held, asked for when its block installs (§6.1,
  §4.2).
- **level 1, 2, 3**: the three levels of validation: a chunk's authenticity, the code's
  consistency, the application's checks (§3).
- **limit**: two kinds. §8.3's limits are the same at every node: a descriptor, chunk or bitmap
  beyond one is invalid. §8.2's limits on a node's own state are the client's to set, and the
  document fixes what a node does at them.
- **live window**: the slots a node works on; a group whose slot has left it is out for good (§8.1).
- **owed**: an offer that a full queue refused, or one that takes the place of a push that was
  skipped or refused, which the next write to the peer carries; or an answer that a full queue
  refused, which is queued once the queue has room (§4.1, §5.2, §7.2).
- **park**: a peer whose promise broke is not asked for the group's chunks for `PARK_TTL`, except by
  the last resort (§6.1).
- **promise**: what an ask written to a peer opens; if nothing closes it within `PROMISE`, the peer
  is parked (§6.1).
- **push**: to send a chunk unasked (§5.2). **Repair** is a decoded node's push of the chunks it
  rebuilt (§4.6).
- **retry**: the next ask of a chunk once an ask's window has closed: of an announcer not asked yet,
  or else of the one asked longest ago (§6.1).
- **source**: the node that publishes a group (§5.1).
- **stop-pull**: no further asks for a group from its decode claim on (§6.2).
- **tie**: what a copy that waits for its block does to its sender: the sender is not asked for that
  index until the root the copy names installs (§4.2).
- **window**: two different things. An ask's window, `IWANT_WINDOW`, is how long one ask of a chunk
  is in flight before the retry (§6.1). The node's sending window, §7.1's, bounds the chunks it has
  in flight: a slot travels with a chunk until its receiver is known to hold it, or a timeout frees
  it. Its **slots** are not consensus slots.
- **withholding node**: one that keeps forwarding but never answers an ask; a **silent node**
  announces what it holds but forwards and answers nothing (*What a forwarding node checks, and when
  it decodes*, 2026; used in §4.6).
