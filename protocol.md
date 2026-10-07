# Segmented payload diffusion, tier 4: the protocol in pseudocode

> **DRAFT v0.3, 2026-10-05.** Companion to the post *Informed diffusion: making home builders
> publish fast*. Field level on the wire; byte-exact layouts follow in a second phase. Written from
> the research implementation (Prysm and a go-libp2p-pubsub fork) and revised after a review
> against it; section 9 lists where the measured runs differ from what is written here.

## 0. How to read this

This document defines what a node does, one event at a time, in Python-like pseudocode in the
style of the consensus specs. It covers every tier, because the tiers are nested, and a tier is the
set of cards it enables:

| tier | cards | in one line |
|---|---|---|
| 1 | 1, 2 | segments with a bid commitment, batch publishing |
| 2 | + 3, 4, 5 | announce instead of push, the phase, disciplined pulls |
| 3 | + 6 | the erasure code over the compressed payload, stop-pull |
| 4 | + 7–17 | HAVE bitmaps, cancel, rarest at pop, decode claim and repair, r = 2, projection, striped publishing, the static window, paced gossip, furthest behind first, push by uplink class |

One rule carries the tag [P4] instead of a card: it is there for the source's privacy, not for
speed or bytes (§5.1).

The code runs as written: [`toy/`](toy/) executes every block of this document, once per node, on
a simulated network.

Related documents, with the short names used below:
- [Wen fast payload broadcast? Segment, code, push, pull, and everything in between](https://ethresear.ch/t/wen-fast-payload-broadcast-segment-code-push-pull-and-everything-in-between/25913)
  (*Segment, code, push-pull*, 2026): the design space, the commitment and the relay rules;
- [EIP-8411: what segmented payload diffusion is made of](https://ethresear.ch/t/eip-8411-what-segmented-payload-diffusion-is-made-of/26025)
  (*What segmented payload diffusion is made of*, 2026): tiers 1 to 3, cards 0 to 6;
- *Informed diffusion: making home builders publish fast* (*Informed diffusion*, forthcoming):
  tier 4 and the design as a whole;
- [Segmented payload diffusion, card by card](https://notes.ethereum.org/@cskiraly/segmented-stack-cards)
  (2026): each card in prose, with what it costs and when it matters;
- [Who decides that a payload is revealed?](https://notes.ethereum.org/@cskiraly/eip-8411-envelope-signature)
  (2026): how the envelope's signature travels.
- *What a forwarding node checks, and when it decodes* (2026, forthcoming): the validation levels, when the
  decode claim goes out, and what a node does with the frames it rebuilds.

**Card tags.** A comment such as `# [c8]` marks the line or block that implements card 8. Tags say
which mechanism is responsible; they are not deletion instructions, and deleting a tagged line does
not always leave a working protocol. What a node does without a card:

| card | without it |
|---|---|
| 3 | every mesh peer is pushed every frame (the budget is D); nothing is announced on forwarding |
| 4 | the budget is R, whatever the holders |
| 5 | stock IWANT handling: every announcer is asked, with no window, offer table or park |
| 6 | no code: N = K, completion needs every frame, and there is no stop-pull |
| 7 | per-id IDONTWANT and IHAVE, asks by full id; cards 8, 9, 10, 12 and 16 lose their input, and card 14 its acknowledgement |
| 8 | the writer sends a queued frame even if the peer has since said it holds it |
| 9 | the writer sends its queue in order |
| 10 | a decoded node claims only the frames it received, keeps receiving the rest, and pushes none of the frames it rebuilt |
| 11 | R = 3 at 1 MiB, the uncoded schedule |
| 12 | no push is skipped by projection |
| 13 | the source's push candidates are its mesh peers, whatever its uplink |
| 14 | no window: the writer hands frames to the transport as fast as it takes them, and sends no acknowledgements; card 16's guard keeps its evidence, the HAVEs mesh peers send (card 7) |
| 15 | heartbeat gossip goes out at once to every sampled peer |
| 16 | push targets in the order of the tie-break alone, a rank that differs per frame |
| 17 | `R_NODE = R` for every node |

**What is assumed and not restated.** Gossipsub v1.2 as specified: the mesh and its maintenance
(D = 8, Dlo = 6, Dhi = 12), GRAFT and PRUNE, the heartbeat (700 ms, as Prysm sets it), the message
cache (6 heartbeats, gossip from the newest 3), IHAVE, IWANT and IDONTWANT, the seen cache, and peer
scoring. Only what changes is written out; one stock limit changes with it, the number of IHAVE
messages a node accepts per peer and heartbeat (§8.3). Messages are unsigned and carry no author,
as Prysm publishes them.

**Scope.** Every peer on the payload's topic is assumed to run this protocol. A stock peer would
misread the bitmaps (§2), so a network in which only some nodes support segmentation needs more
than is written here, and is left out.

**What is normative.** Sections 1–3 are the consensus-side and wire definitions that both ends must
agree on. Sections 4–7 combine each node's local scheduling with the meaning of the messages it
exchanges: what a HAVE, an ask, a decode claim and an acknowledgement promise. A client may schedule
differently without breaking interoperability, provided those meanings hold; the measurements are of
the scheduling written here. Section 8 lists the state, its limits and the constants, and section 9
the known differences from the measured implementation.

## 1. The payload, the code and the commitment [c1, c6]

What is segmented is the SSZ container of what the builder holds at bid time,
`ExecutionPayloadSegmentBody{payload, execution_requests}`, as *Segment, code, push-pull* (2026)
specifies. The unsigned envelope is rebuilt from it and the block. Its signature cannot be rebuilt,
and travels on its own with the roots needed to check it, as *Who decides that a payload is
revealed?* (2026) recommends (its option A).

```python
UNIT = 16 * 1024                # target segment size, uncompressed               [c1]
MAX_FRAMES = 256                # codec limit on data + parity frames             [c6]
MAX_PLAIN_FRAMES = 8192         # every group fits one HAVE bitmap (§2)           [c1]
MAX_SEGMENT_SIZE = 2 * UNIT     # above snappy's worst-case expansion             [c1]

class SegmentDescriptor(Container):     # committed in the bid                    [c1]
    version: uint8          # 2 = coded (compress first, then Reed–Solomon); 1 = plain
    hash_id: uint8          # 0 = SHA-256
    encoding: uint8         # 1 = snappy block compression applied before coding [c6]
    count: uint32           # N: frames in the group (data + parity)
    segment_size: uint32    # bytes per frame (the last data frame may be shorter)
    total_length: uint64    # length of the segmented byte string
    root: Bytes32           # Merkle root over the N frames

def group_id(d: SegmentDescriptor) -> Bytes32:
    return sha256(b"\x02" + serialize(d))

def K(d) -> int: return ceil(d.total_length / d.segment_size)     # data frames
def N(d) -> int: return d.count

def segment_length(d, i) -> int:
    if i == K(d) - 1: return d.total_length - (K(d) - 1) * d.segment_size   # the last data frame
    return d.segment_size                                                   # data and parity

def valid_descriptor(d) -> bool:         # checked before any state is allocated for the group
    if d.hash_id != 0 or d.segment_size == 0 or d.segment_size > MAX_SEGMENT_SIZE: return False
    if d.total_length == 0: return False
    if d.version == 2: return d.encoding == 1 and d.count == 2 * K(d) <= MAX_FRAMES
    if d.version == 1: return d.encoding == 0 and d.count == K(d) <= MAX_PLAIN_FRAMES
    return False
```

**The bid.** This proposal adds one field to Gloas's `ExecutionPayloadBid`: either the group id of
the payload's descriptor, `execution_payload_segment_group_id` (design A below), or the descriptor
itself, `execution_payload_segment_descriptor` (design B). Neither exists in the Gloas baseline.
Every frame is then authenticated through the block that carries the bid: installed block → bid →
descriptor → Merkle proof → frame.

**Getting the descriptor (open).** A receiver needs the descriptor itself to check a frame's proof;
the group id is only its hash. Two designs work, and the choice is not made:
- **A, descriptor in the frame:** every frame carries the descriptor, and the receiver checks its
  hash against the bid's group id (the measured implementation does this).
- **B, descriptor in the bid:** the bid carries the descriptor itself instead of its hash, and
  frames carry only the group id.

At these frame sizes the bytes do not decide it. Section 3 is written for either.

```python
class Shard(Container):                  # a frame's content, before it has a block to name
    index: uint32
    proof: List[Bytes32, 14]
    data: bytes

def build_group(body: bytes) -> Tuple[SegmentDescriptor, List[Shard]]:     # at bid time
    K = ceil(len(body) / UNIT)                                   # data frames      [c1]
    coded = 2 * K <= MAX_FRAMES                                  #                  [c6]
    data = snappy_block_encode(body) if coded else body          # compress first   [c6]
    size = ceil(len(data) / K)
    segs = [data[i*size:(i+1)*size] for i in range(K)]           # the last may be short
    parity = rs_parity(pad_each(segs, size), K) if coded else [] # K parity frames  [c6]
    leaves = segs + parity
    d = SegmentDescriptor(version=2 if coded else 1, hash_id=0, encoding=1 if coded else 0,
                          count=len(leaves), segment_size=size, total_length=len(data),
                          root=merkle_root(leaves))
    return d, [Shard(index=i, proof=merkle_proof(leaves, i), data=leaves[i])
               for i in range(len(leaves))]
```

- **The code** [c6]: systematic Reed–Solomon over GF(2⁸) (polynomial 0x11d), evaluation points
  0..N−1. Frames 0..K−1 are the compressed bytes themselves and K..N−1 are parity, so any K distinct
  frames rebuild the payload. At 1 MiB this gives K = 64 and N = 128, frames of about 12 KB.
- **The tree** [c1]: leaves `sha256(0x00 ‖ frame data)`, nodes `sha256(0x01 ‖ left ‖ right)`,
  padded to a power of two with zero digests. A proof is log₂ of that width, 7 digests at N = 128.
- **Decoding** is the second level of validation (§3): take any K frames, recover the data frames,
  re-encode the parity, rebuild the tree, and require the committed root.

## 2. The wire [c1, c7]

Nothing here adds a protobuf field or an RPC type. Frames travel as gossipsub messages on one
topic, and the bitmaps as message-id strings inside existing control fields.

```python
class Frame(Container):                 # gossipsub Message.data, snappy-compressed SSZ   [c1]
    slot: Slot
    beacon_block_root: Root             # the block whose bid commits this group
    group: Bytes32                      # group_id of the committed descriptor
    descriptor: SegmentDescriptor       # design A only (section 1)
    index: uint32
    proof: List[Bytes32, 14]
    data: ByteList[MAX_SEGMENT_SIZE]

def message_id(f: Frame) -> bytes:                          # structured id      [c1]
    return f.group + uint32_le(f.index) + content_id(f)     # 32 + 4 + 20 bytes
```

The structured id lets a receiver match an announcement to a group and an index before it holds the
frame, and match both to a bid once its block is installed. `content_id` is the 20-byte message id
of the Altair networking rules, computed over the topic and the decompressed frame, so different
snappy encodings of one frame share an id, and different contents claiming one index do not. A
frame that decodes gets the 56-byte structured id, itself a change to that rule for this topic. If
bounded decompression or the frame's decoding fails, the message gets the inherited Altair id, with
no prefix, and is rejected before any group state is created. The topic's name and type mapping
are left to the byte-exact phase.

**HAVE bitmaps** [c7]. One bitmap per group replaces per-id control messages. Its meaning is set by
the control field that carries it:

```python
MAX_HAVE_BYTES = 1024                   # 8192 indices: MAX_PLAIN_FRAMES

class HaveBitmap(Container):            # carried as one message-id string   [c7]
    MAGIC = b"HAVE"                     # the string opens with MAGIC, then VERSION as a uint8
    VERSION = 1
    group: Bytes32
    bits: ByteList[MAX_HAVE_BYTES]      # bit i = frame index i; trailing zero bytes dropped

class WantIndex(Container):             # an ask by index, in IWANT          [c7]
    MAGIC = b"WANT"
    VERSION = 1
    group: Bytes32
    index: uint32
```

Both are built by field name, `HaveBitmap(group=g, bits=b)`; `MAGIC` and `VERSION` are fixed by the
type, not passed.

| carried in | means | sent when |
|---|---|---|
| IDONTWANT | "I hold these frames": always the sender's whole current bitmap for the group, so the receiver ORs it in and order does not matter | on every new frame that passes level 1, to the mesh and to the frame's sender (§4.2); by the source before its data (§5.1); on decode, all N bits (§4.6) |
| IHAVE | "I can send you these": exactly the frames the announcement names, minus what the sender pushed you and what you told it you hold; never empty | announce instead of push (§5.2); heartbeat gossip (§6.4) |
| IWANT, as `WantIndex` | "send me frame `index`": used when the asker does not know the frame's full id | §6.1 |

A bitmap that names an index at or beyond its group's N, once the descriptor is known, is a
protocol violation.

**What a stock peer would see.** The protobuf schema is unchanged, but the meaning is not. A stock
peer takes a bitmap in an IDONTWANT for an id that matches nothing, which is harmless; a bitmap in
an IHAVE it takes for an ordinary id, asks for it, and counts the unanswered ask as a broken
promise. Hence the scope of §0.

Without card 7, the same information travels as ordinary per-id IDONTWANT and IHAVE, and asks use
the full message id.

## 3. Validation: three levels, and what each gates [c1, c6, c10]

A node cannot validate a payload before it forwards pieces of it; that is where the speed comes
from. Validation therefore comes in three levels, and only the first fits a frame.

**Level 1, per frame: authenticity.** The frame is the committed piece at its index:

```python
def validate_frame(f: Frame) -> Result:
    block = installed_block(f.slot, f.beacon_block_root)    # validated and applied locally
    if block is None:
        return DEFER                    # held in a bounded store (§8.2); not claimed, not relayed
    d = committed_descriptor(block, f)
    if d is None or group_id(d) != f.group or not valid_descriptor(d): return REJECT
    if f.index >= d.count: return REJECT
    if len(f.data) != segment_length(d, f.index): return REJECT
    if not verify_merkle_proof(d.root, f.data, f.index, d.count, f.proof): return REJECT
    return ACCEPT

def committed_descriptor(block, f: Frame) -> Optional[SegmentDescriptor]:
    bid = block.body.signed_execution_payload_bid.message
    if DESCRIPTOR_IN_FRAME:                                         # design A
        ok = group_id(f.descriptor) == bid.execution_payload_segment_group_id
        return f.descriptor if ok else None
    return bid.execution_payload_segment_descriptor                 # design B
```

It costs a Merkle proof, so every node runs it before it claims, relays or serves a frame. A frame
that fails it is therefore the fault of the peer that sent it, and counts against that peer.

**Level 2, per group, after any K frames: the code's consistency.** Decode, re-encode the parity,
rebuild the tree, and require the root (§4.6). Only the builder can fail it, and then it fails at
every node. A node pushes or serves frames it rebuilt, and delivers the payload, only after this
check passes; it claims them at K, before the check (§4.6).

**Level 3, per message: the application's checks** on the reassembled payload and its envelope: the
builder's signature (which arrives on its own and can be checked as soon as the block is installed),
the payload against the bid, then execution. A frame carries nothing these could check: with
compression before coding, a frame is not even a parseable fragment.

**What each level gates.**
- Level 1 gates everything a node does with a frame: holding it, claiming it, relaying it, serving
  it, counting it toward K.
- Level 2 gates delivery and every frame the node rebuilt. The decode claim goes out at K, before
  it: a group that fails level 2 fails it at every node, so the claim can only be wrong about a
  group every node drops (§4.6).
- Level 3 gates what consensus consumes: fork choice, the payload timeliness vote, import. It gates
  nothing in diffusion: relaying never waits for it.
- When level 2 or 3 fails, the node drops the group (§4.6): it stops relaying, answering and
  pushing it, and retracts nothing, because what it claimed were authentic pieces.

**What bounds the damage: the builder's cost.** A frame authenticates only against the bid an
installed beacon block carries, so at most one payload per winning bid crosses the network: one
per block. Frames committed to a losing bid never validate. Under Gloas, a bid's pending payment
that reaches the same-slot attestation quorum is queued for withdrawal whether or not its payload
ever arrives: if it is not settled earlier, at the end of the epoch after the bid's. A builder that
commits to an invalid payload therefore pays for the slot and gets nothing for it. One case moves
the cost: a proposer that signs a second block for the slot is slashed, and the slashing clears
that slot's pending payment. The nodes that forwarded it could not have known, so a payload that fails level 2
or 3 never counts against them.

**Relay gating.** These rules are from *Segment, code, push-pull* (2026). None of them ran in the
measured cells (section 9).
- **Do not relay a frame whose block is not installed.** Deferred frames wait in a bounded store
  with per-peer reservations, and are validated when the block installs, or dropped when their slot
  leaves the live window (§4.2, §8).
- **A receiver may decline to ask for what it cannot yet authenticate.** A declined announcement is
  remembered in a bounded ledger and replayed when the block installs.
- **Push only with evidence the peer holds the block.** Mesh membership is not such evidence. How a
  node gets it, for its mesh and for the wider set striped publishing reaches (card 13), is open,
  and the push selectors of section 5 do not apply this rule: they are the measured policy.

## 4. Receiving

### 4.1 The order of handling

```python
def on_rpc(p, rpc):
    for f in rpc.frames: on_frame(p, f)                       # §4.2
    asks = on_ihave(p, rpc.ihave)                              # §4.4
    answers = on_iwant(p, rpc.iwant)                           # §4.5
    prunes = handle_graft_prune(p, rpc)                        # stock
    for h in rpc.idontwant: on_have(p, h)                      # §4.3 (stock ids go to unwanted[p])
    respond(p, asks, answers, prunes)

def respond(p, asks, answers, prunes):                         # one response per RPC handled
    control = IWANT(asks) + PRUNE(prunes) if asks or prunes else None   # an empty part is left out
    if not answers:
        if control: enqueue(p, Entry(control=control), urgent=False)
        return                                                 # nothing to ask, answer or prune
    for k, f in enumerate(answers):                            # one frame per entry; the control
        enqueue(p, Entry(frame=f, solicited=True, control=control if k == 0 else None), urgent=False)
```

An ask and a HAVE in the same RPC are therefore handled ask first, and the asks and answers one RPC
produces leave together, the control riding on the first answer. Validation (§3) runs off this
path, on the router's event loop like block installation; a frame's handling continues when its
result is known.

### 4.2 A frame arrives

```python
def on_frame(p, f):
    mid = message_id(f)
    if seen(mid) or mid in pending_ids:              # a duplicate, a frame rejected before, or one waiting
        if accepted(mid): send_have(p, f.group)      # [c14] duplicates are acknowledged too
        return
    if expired(f.group): return                      # past its active lifetime (§8.1): ignored
    on_validated(p, f, validate_frame(f))            # level 1 (§3)

def on_validated(p, f, result):
    if result == DEFER: return defer(p, f)           # ahead of its block: no claim, no relay
    mark_seen(message_id(f))                         # accepted or rejected: never validated again
    if result == REJECT: return penalise(p)          # level 1 failures are the sender's (§3)
    g, i = f.group, f.index
    if g not in desc: open_group(g, f)               # desc[g] from the bid; state[g] = COLLECTING
    if state[g] == INVALID: return                   # a dropped group (§4.6)
    if received[g].has(i): return send_have(p, g)    # a second copy of a frame we received: acknowledge
    store(g, i, f); received[g].set(i)               # also records known_id[g][i] = message_id(f)
    close_promises(g, i)                             # [c5] the frame arrived, from anyone
    claim = not mine[g].has(i)                       # not yet claimed (decoded nodes claimed everything)
    if claim: mine[g].set(i)                         # [c7] only frames that passed level 1
    for q in (mesh | {p}) if claim else {p}:
        send_have(q, g)                              # [c7] the claim to the mesh, and [c14] the sender's ack
    forward(f, p)                                    # §5.2: relaying never waits for levels 2 and 3
    if state[g] == COLLECTING and popcount(received[g]) >= K(desc[g]):
        state[g] = DECODING                          # once per group
        claim_group(g)                               # [c10] the decode claim, at K (§4.6)
        start(decode_group, g)                       # level 2, off the frame path, for as long as a
                                                     #   decode takes (§8.1)

def defer(p, f):                                     # on the router's event loop, like installation
    if installed_block(f.slot, f.beacon_block_root):           # installed in the meantime
        return on_validated(p, f, validate_frame(f))
    if reserve(p, f):                                # a per-peer reservation in a bounded store (§8.2)
        pending[f.beacon_block_root].append((p, f))
        pending_ids.add(message_id(f))
    # refused: nothing is remembered, so a later copy is evaluated afresh

def on_block_installed(root):                        # resumes level 1
    for p, f in pending.pop(root, []):
        pending_ids.discard(message_id(f)); release(p, f)      # the reservation goes back
        on_validated(p, f, validate_frame(f))

def send_have(p, g):                                 # [c7] always the whole bitmap, as it is now
    enqueue(p, IDONTWANT(HaveBitmap(group=g, bits=have_bits(g))), urgent=True)

def have_bits(g):                                    # what our HAVE says of g: what we hold, or, for a
    return (origin[g] if g in origin else mine[g]).copy()      # group we publish, what we have sent [P4]
```

A node announces a frame once its proof checks, not on arrival as stock IDONTWANT does: a held
index is stronger evidence than a held id, since it covers any frame claiming that index. A frame
that arrives ahead of its block is announced only when the block installs; until then its senders
may keep pushing it, and their window slots stay held (§7.1). Announcing such a frame by its exact
id on arrival, which is safe because an id covers only those bytes, is a variant not evaluated yet.

Without card 7 the node sends the stock IDONTWANT for `mid` to its mesh, and no acknowledgement goes
back to the sender.

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
```

`peer_has` is the one view of what each peer holds. Cancel and projection (§7.2), the push
candidates and budget (§5.2), whom to push to (§5.3) and what to announce read it at the moment they
act, by index, so a HAVE that arrives before its frame's id is known still counts.

### 4.4 An IHAVE arrives [c3, c5, c7]

```python
def on_ihave(p, ih):                                                  # returns the asks (§4.1)
    candidates = []
    for entry in ih.ids:
        for a in expand(entry):                                       # [c7]
            if held(a) or expired(group(a)): continue
            add_offer(a, p)                                           # [c5] offer table (§8.2)
            if parked(p, a) or gated(a): continue                     # [c5] park; [c6] stop-pull
            candidates.append(a)
    return [a for a in shuffled(candidates) if may_ask(a, p)]        # §6.1

def expand(entry):                                                    # [c7]
    if not is_have_bitmap(entry): return [entry]
    g = entry.group
    return [known_id[g].get(i) or WantIndex(group=g, index=i) for i in entry.bits if not mine[g].has(i)]
```

An IHAVE bitmap tells us who can serve, not who holds. It feeds the offer table only: never
`peer_has`, `holders`, cancel or the window. A node handles at most `MAX_IHAVE_MESSAGES` IHAVE-bearing
RPCs per peer and heartbeat (§8.3).

### 4.5 An IWANT arrives

```python
def on_iwant(p, iw):                                  # returns the answers (§4.1)
    answers = {}                                      # by id: one answer per id per RPC
    for a in iw.ids:
        gi = group_index(a)                           # from a WantIndex or a structured id
        if gi and expired(gi.group): continue         # past its active lifetime: ignored, no penalty
        if gi and peer_has[p][gi.group].has(gi.index):
            penalise(p)                               # it asks for a frame it claimed: dropped
            continue
        mid = resolve(a)                              # [c7] our id at that index: received or rebuilt
        if mid is None or mid in unwanted[p]: continue
        serve_count[p][mid] += 1
        if serve_count[p][mid] > GOSSIP_RETRANSMISSION: continue   # stock: 3 answers per id per peer
        answers[mid] = frame_of(mid)
    return list(answers.values())                     # [c14] one frame per queue entry (§4.1)
```

**An ask for a frame the asker claimed is dropped: the claim wins.** Claims are made only for frames
that passed level 1, and within a group's active lifetime (§8.1) a node's holdings only grow. Both
lanes of a peer's queue feed one ordered writer, the asker drops its queued asks for frames it holds
just before writing them (§7.2), and RPCs are handled in stream order, with IWANT before IDONTWANT
within one (§4.1). So on a live connection an honest ask always arrives before the claim it would
contradict, and an ask after the claim is a protocol violation. A node does not ask again for a
group past its active lifetime, and controls for such a group are ignored without penalty. A
restart is not an exception: it is a new connection, with no claims.

`resolve` returns nothing for a group the node dropped (§4.6).

### 4.6 Decode, the claim, repair and the levels above [c6, c10]

```python
def claim_group(g):                                   # [c10] at the K-th frame, before decoding
    stop_pull[g] = True                               # [c6] no further asks for this group
    mine[g] = all_bits(N(desc[g]))                    # [c10]
    for q in mesh: send_have(q, g)                    # [c10] the decode claim: all N bits
    close_promises_of_group(g)                        # [c5] nobody owes us frames of this group

def decode_group(g):                                  # level 2, off the frame path (§3)
    d = desc[g]
    rebuilt = decode_and_reencode(frames[g], d)       # any K frames -> all N, or None if the root differs
    if rebuilt is None: return drop_group(g)          # an inconsistent code: the builder's fault
    new = [i for i in rebuilt if not received[g].has(i)]      # rebuilt, and not received meanwhile
    for i in new: store(g, i, rebuilt[i])             # servable from now on; not marked seen,
    state[g] = COMPLETE                               #   so a copy that arrives later is still relayed
    push_rebuilt(g, new)                              # [c10] repair: level 2 has passed
    deliver(g, payload_of(rebuilt))                   # level 3: the application's checks (§3)

def push_rebuilt(g, new):                             # [c10] to the mesh peers still short of K
    for q in shuffled(mesh):
        known = peer_has[q][g].bits | pushed[q][g]    # what q claimed, and what we chose to push it
        short = K(desc[g]) - popcount(known)          # q's shortfall: none after its decode claim
        if short <= 0: continue
        lacks = shuffled([i for i in new if not known.has(i)])    # at random, so that decoded
        for i in lacks[:short]:                                   #   neighbours tend to differ
            enqueue(q, frames[g][i], urgent=False)    # cards 8, 9, 12 and 14 act on it (§7.2)
            note_push(q, g, i)

def drop_group(g):                                    # level 2 or level 3 failed
    state[g] = INVALID
    stop_pull[g] = True
    discard_queued(g)                                 # g's frames, IHAVEs and IWANTs in every queue; HAVEs stay
    gossip_history.remove_group(g)                    # no further heartbeat announcements of g
    discard_paced(g)                                  # nor paced ones
    close_promises_of_group(g)                        # its announcers did nothing wrong: nobody is parked
```

- **The decode claim goes out at K, before decoding.** Every frame that passed level 1 is an
  authentic leaf under the committed root. If the N leaves form a codeword, every node's decode
  succeeds and the claim is true; if they do not, any K of them rebuild a codeword that differs
  somewhere, so every node's check fails, and the claim was about a group every node drops. What
  waits for level 2 is everything that hands out rebuilt data: delivery, and the rebuilt frames,
  which the node pushes, and `resolve` finds, only once they are stored. *What a forwarding node checks,
  and when it decodes* (2026) maps the alternatives.
- **Relaying continues** while a node decodes: the frames it received were authentic whatever
  levels 2 and 3 find, so it forwards later arrivals as before (§4.2).
- **The decode claim makes the node a holder.** Its peers stop pushing to it and count it as a
  holder of every frame. The claim is not an announcement, and asks go to announcers (§6.1), so a
  node that only held its rebuilt frames would never be asked for them: holding them is the same as
  rebuilding nothing.
- **Repair** [c10]. Once level 2 passes, the node pushes the frames it rebuilt to each mesh peer
  whose claims show it short of K: at most that peer's shortfall, counting what the node already
  chose to push it, picked at random among the rebuilt frames the peer lacks, so that decoded
  neighbours tend to push different frames. Card 4's budget cannot be reused here: late in a
  diffusion most mesh peers have claimed every frame, and the budget would shrink to nothing. The
  pushes are ordinary normal-lane frames: rarest at pop orders them with the rest of the queue
  (card 9), one the peer claims meanwhile is cancelled at dispatch (card 8), a peer projected to
  reach K without it is skipped (card 12), and the window keeps the backlog where those rules act
  (card 14). There is no random delay before the push: on a full release a short one changed
  nothing measurable; with only K frames released it was not tried. A peer that claims less than it
  holds draws at most its claimed shortfall from each decoded neighbour, once per group; repair
  skips card 16's guard and draw.
- **What a receiver sees.** A rebuilt frame is the source's frame, byte for byte: the same id and
  the same proof. Its receiver checks it at level 1 and relays it like any other. Nothing marks it
  as rebuilt, and nothing needs to. Repair waits for level 2 but not for level 3: once the group
  has passed level 2, a rebuilt frame is an authentic leaf, as a relayed one is.
- **Why push, and not hold or announce.** A builder may release only the K frames needed to
  decode. Every node then needs every one of them, the slowest to reach it included, and the other
  K exist only in the nodes that have decoded. Completion times spread out, and a builder that
  releases late, near a deadline such as the payload timeliness vote, can use the spread to split
  the network. Repair puts the other K back as soon as the first nodes decode, so that a node still
  short can again complete on any K of the N. That brings the spread most of the way back to that
  of a full release, also against withholders that refuse to repair, whether or not they announce
  frames they do not hold, and about half of the way against silent nodes. An announcement would
  add an ask and an answer, three link delays instead of one, so it helps mainly where other asks
  fail. It can also be baited: an announcement is a promise nobody can check before asking, and a
  withholder or a liar draws asks it never answers until the park stops them (§6.1). Where every
  frame is released and the other nodes are honest, a rebuilt frame is one more copy of a plentiful one,
  and repair has little to do; on thin links it changed nothing measurable. *What a forwarding node
  checks, and when it decodes* (2026) gives the measurements.
- **Level 3 runs on the reassembled payload**, with the envelope's separately sent signature, and
  gates only what consensus consumes. If it fails, the application calls `drop_group`.
- **The claim reaches mesh peers only.** A peer outside the mesh that is still pushing (the striping
  source of card 13) or answering learns of it from the node's next acknowledgement.

Without card 10 a node that has decoded claims only the frames it received, its peers keep pushing
it parity it does not need, and it pushes none of the frames it rebuilt. Without card 6 there is no
code: a node needs every frame, and completion is "all K received".

## 5. Publishing and forwarding

### 5.1 The source [c2, c13]

The source builds the group at bid time (§1), and publishes once the block carrying its bid is
known:

```python
def publish(block, d, shards):
    g = group_id(d)
    desc[g] = d
    for s in shards:                                  # the source holds every frame from the start
        f = Frame(slot=block.slot, beacon_block_root=block_root(block), group=g,
                  descriptor=d, index=s.index, proof=s.proof, data=s.data)    # descriptor: design A
        store(g, s.index, f); mark_seen(message_id(f))
        gossip_history.put(f)                         # stock: heartbeat gossip may announce it (§6.4)
    mine[g] = all_bits(N(d)); state[g] = COMPLETE; stop_pull[g] = True
    origin[g] = bitmap(set())               # [P4] our HAVE names only frames we have sent: none yet
    plan = []
    for i in range(N(d)):                   # index order; each frame's targets see earlier plans
        f = frames[g][i]
        targets = choose_push(f, candidates_for_source(f), budget=R, at_source=True)   # §5.3
        for p in targets: note_push(p, g, i)
        plan.append((f, targets))
    led = set()
    for copy in range(R):                   # the first copy of every frame before any second  [c2]
        for f, targets in plan:
            if copy < len(targets):
                p = targets[copy]
                if p not in led:            # [P4] a peer's first frame from us follows our HAVE naming
                    led.add(p)              #   it, as a relay's HAVE precedes its pushes
                    enqueue(p, IDONTWANT(HaveBitmap(group=g, bits=origin[g] | bitmap({f.index}))), urgent=True)
                enqueue(p, f, urgent=False)
    for i in range(N(d)):
        for p in mesh: announce(p, g, bitmap({i}))  # [c3] mesh peers not pushed a frame are announced it

def origin_sent(f):                         # [P4] a frame of a group we publish leaves for the first
    if origin[f.group].has(f.index): return     # time (§7.2): it joins our HAVE, which goes to the
    origin[f.group].set(f.index)                # mesh as a relay's does when a frame arrives (§4.2)
    for q in mesh: send_have(q, f.group)

def candidates_for_source(f):
    pool = connected_topic_peers() if UPLINK >= STRIPE_UPLINK else mesh    # [c13] configured uplink
    return [p for p in pool if not peer_has[p][f.group].has(f.index)]
```

- **Batch publishing** [c2] fixes only the order in which frames enter each peer's queue. What
  leaves first on each link is decided when the queue sends (§7).
- **Striped publishing** [c13]: a source whose configured uplink is at least `STRIPE_UPLINK`
  stripes; a slower one pushes to its mesh, as the other nodes do. Striping pays only when the source can
  send faster than its mesh peers can pass the frames on, and the source knows neither their uplinks
  nor how much of its own it can count on, so the threshold sits where the gain is measured. The
  candidates are then every connected peer on the topic. With the fewest-first order of §5.3, and
  each connection starting with nothing, the frames are dealt two at a time over all connections:
  the two copies of a frame go to two different peers, and each connection receives about 2N/C
  frames. Only mesh peers that were not pushed a frame are announced it; other connections get no
  announcement from this step, though heartbeat gossip may announce to them later (§6.4).
- The source pushes each frame to R = 2 peers. It never uses the fast-class degree of card 17.
- **The source's HAVE is paced** [P4], for the source's privacy. A HAVE that names every frame
  before any frame has left can come only from the source, so it tells each mesh peer who published
  the payload. The source's HAVE therefore names only frames it has sent: a frame joins it when the
  source's writer first sends it, and the HAVE then goes to the mesh, as a relay's does when a frame
  arrives. A peer the source pushes to gets a HAVE naming its first frame just ahead of it, as a
  relay's HAVE precedes its pushes. The HAVE still keeps relays from pushing the source's frames
  back to it, a frame at a time. HAVEs to the mesh that would leave together may be merged into one,
  as the research implementation merges those of the frames sent between two of its router's turns. This removes the one certain sign of the source; others remain (its
  HAVE grows faster than any relay's, it announces every frame at publish, it is everyone's first
  sender), and are the subject of separate work on the source's privacy, where P4 is this measure's
  name. The research implementation has it as an option, measured at no cost in delivery.

### 5.2 A node forwards [c3, c4, c11, c17]

```python
def forward(f, from_peer):
    g, i = f.group, f.index
    holding = [p for p in mesh if peer_has[p][g].has(i)]                # [c4] the sender, normally
    cands = [p for p in mesh if p not in holding and p != from_peer]
    budget = max(0, R_NODE - len(holding))                              # [c3, c4, c11, c17]
    targets = choose_push(f, cands, budget, at_source=False)            # §5.3
    for p in targets:
        enqueue(p, f, urgent=False)
        note_push(p, g, i)                                              # [c7]
    for p in cands:
        if p not in targets: announce(p, g, bitmap({i}))                # [c3]
    gossip_history.put(f)                                               # stock message cache (§6.4)

def announce(p, g, bits):                                               # [c3, c7]
    b = bits & ~pushed[p][g] & ~peer_has[p][g].bits
    if b: enqueue(p, IHAVE(HaveBitmap(group=g, bits=b)), urgent=False)  # an empty bitmap is not sent

def note_push(p, g, i):
    e = pushed[p][g]                                                    # created at the first push
    if e.empty(): e.first_push = now                                    # the guard's clock (§5.3)
    e.set(i); e.ttl = PUSH_TTL                                          # heartbeats
```

- **Announce instead of push** [c3]: a node pushes each frame to at most `budget` mesh peers and
  announces it to the others, which ask if they still need it.
- **The phase** [c4]: the budget shrinks with every mesh peer already known to hold the frame. The
  sender has normally claimed the frame before it arrives (its HAVE travels urgently, ahead of the
  data), so it counts as a holder. At R = 2 a received frame therefore goes on to one more peer early
  in its life, and to none late. Without card 4 the budget is R, whatever the holders.
- **R** [c11]: 2 with the code. Without card 11, 3 at 1 MiB (the uncoded schedule).
- **Push by uplink class** [c17]: `R_NODE = R_FAST` (6) if the node's configured uplink is at least
  `FAST_UPLINK` (500 Mbps), else R. The node knows its uplink from the same configuration that sizes
  its window (§7.1).

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

- **Frames held** counts what the peer told us in its HAVEs plus what we chose to push it, including
  pushes still queued. Announcements and answered asks do not count.
- **The lower-half draw** picks the push targets uniformly, without replacement, among the peers at
  or below the median of that count. That is not a guarantee of a fair share of the traffic: an
  under-reporter is drawn with bounded probability within the lower half.
- **The guard** moves a peer to the back when we have chosen to push it at least `R_NODE` frames of
  the group, the first more than 200 ms ago, and it has sent no HAVE for the group, not even an
  empty one. A demoted peer can still be pushed if the budget reaches it, and the demotion lifts at
  its first HAVE.
- **At the source** the ranking is fewest-frames-first, with no draw. The guard is evaluated but
  cannot fire, because the whole group is planned at one instant.
- **Tie-break:** a hash of (message id, peer id), finalised; larger first, then the larger peer id.
- **Without card 16:** order candidates by that tie-break alone.

## 6. Asking

### 6.1 One ask per frame at a time, move on, park [c5]

```python
def may_ask(a, p):
    at = asked_at.get(a)
    if at is not None and now - at < IWANT_WINDOW:       # 200 ms: an ask is in flight
        return False
    asked_at[a] = now
    tried[a][p] = now
    after(IWANT_WINDOW + RETRY_SLACK, retry_offer, a)    # move on, once the window has closed
    if (a, p) not in promises:
        promises[(a, p)] = now
        after(PROMISE, promise_due, a, p, now)           # 400 ms
    return True

def retry_offer(a):
    if held(a) or stop_pull[group(a)]: return
    if now - asked_at.get(a, -inf) < IWANT_WINDOW: return
    cands = [q for q in offers[a] if not parked(q, a)]
    if not cands: return                                  # wait for a fresh announcement
    pick = untried(cands, a)
    if pick is None: pick = least_recently_tried(cands, a)
    if may_ask(a, pick): enqueue(pick, IWANT([a]), urgent=False)

def untried(cands, a):                                    # the earliest announcer not asked yet:
    return next((q for q in cands if q not in tried[a]), None)    # offers keep announcement order

def least_recently_tried(cands, a):
    return min(cands, key=lambda q: tried[a][q])

def promise_due(a, p, at):
    if promises.get((a, p)) != at: return                  # delivered, or closed on decode
    del promises[(a, p)]
    park[p][group(a)] = now + PARK_TTL                     # k = 1: one broken promise parks p
                                                           # for this group only, 30 s
def parked(p, a): return now < park[p].get(group(a), -inf)
```

- **Offers** are recorded from every announcement, parked or not, within the limits of §8.2, and
  dropped when the frame arrives, when the announcer's connection closes, or after 30 s.
- **A promise closes** when the frame arrives from anyone, or when the group is decoded (§4.6).
- **Parking** affects only asks: a parked peer's announcements are not acted on for that group, but
  its pushes and our answers to it continue.
- Without the offer table and park, the discipline alone asks the first announcer. It re-asks
  whoever announces after the window.

### 6.2 Stop-pull [c6]

```python
def gated(a): return stop_pull[group(a)]      # from the decode claim on, no further asks for the group
```

Pushes already on their way still land. Before completion, each newly accepted distinct index
counts toward K; duplicates do not.

### 6.3 Receiving an answer

Answers are ordinary frames and go through §4.2.

### 6.4 Heartbeat gossip and pacing [c15]

```python
def on_heartbeat():
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

The gossip history holds the frames the source published and the frames a node received and
forwarded; it does not hold the frames a decoded node rebuilt, which are pushed instead of
announced (§4.6). Paced gossip releases the heartbeat's announcements one peer per tick instead of
all at once.

## 7. Sending: the per-peer queue and the window

### 7.1 The window [c14]

```python
W = ceil(uplink_bytes_per_s * (RTT_REF + TARGET) / FRAME_BYTES)   # one window per node  [c14]
in_flight = 0                         # slots taken: held by a writer, or travelling with a frame
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

def release_unused_slot(p):           # p's writer has no frame to send now
    if p in waiters:
        waiters.remove(p)                         # it leaves the line, and the next may take a free slot
        if waiters and in_flight < W: wake(waiters[0])
    if slot_held[p]:
        slot_held[p] = False
        free_slot()

def track_in_flight(p, f):            # the writer's slot now travels with frame f
    key = (p, f.group, f.index)
    if key in sent: return free_slot()            # a second copy still in flight: back at once
    sent[key] = now
    after(WINDOW_TIMEOUT, window_timeout, key, now)

def window_release(p, g, i):          # p holds frame i, from anyone (§4.3)
    if sent.pop((p, g, i), None) is not None: free_slot()

def window_timeout(key, at):
    if sent.get(key) == at:
        del sent[key]
        free_slot()

def free_slot():
    global in_flight
    in_flight -= 1
    if waiters: wake(waiters[0])                  # the first writer in line tries again (§7.2)
```

- **What takes a slot:** a frame sent on the normal lane, push or answer.
- **What gives it back:** a HAVE from that peer that newly covers the frame's index (§4.3), or
  `WINDOW_TIMEOUT` (500 ms) after sending, or the peer's queue closing.
- **What bypasses it:** urgent control (HAVEs, acknowledgements, decode claims) never waits.
- **A second copy** of a frame still in flight to the same peer waits for a slot like any frame but
  returns it at once: the window counts frames a peer is not yet known to hold, not bytes on the
  wire.
- **Sizing:** the node sizes the window from its configured uplink. It does not need to be exact:
  a window sized for twice the real uplink costs about a tenth in the tail.

### 7.2 Choosing what to send, at the moment of sending [c8, c9, c12, c14]

One writer per peer. A queue entry carries at most one frame, and may also carry control. Each time
the previous write to that peer has completed, and whenever the writer is woken (a slot freed for
it, or an urgent entry arrived), it calls `next_to_send`: an entry to write, `None` when there is
nothing to send, or `WAIT` when it waits in line for a slot.

```python
def next_to_send(p):
    q = queue[p]
    while True:
        if q.urgent: return q.urgent.pop(0)                    # HAVEs, acks, decode claims: first
        if not q.normal:
            release_unused_slot(p); return None                # nothing to send: a held slot goes back
        if q.has_frames() and not slot_held[p]:
            if not acquire_slot(p): return WAIT                # [c14] in line, FIFO over peers; an urgent
            slot_held[p] = True                                #   arrival wakes the writer, which keeps
            continue                                           #   its place in line
        entry = q.normal.pop(rarest(q) if RAREST else 0)       # [c9]
        out = filter_entry(p, entry)                           # [c8, c12], and stale asks
        if not (out and out.frame): release_unused_slot(p)     # no frame leaves: the slot goes back
        if out:
            if out.frame:
                track_in_flight(p, out.frame); slot_held[p] = False    # [c14] the slot is used
                if out.frame.group in origin: origin_sent(out.frame)   # [P4] our HAVE grows (§5.1)
            return out
        # nothing was left of the entry: start again from the urgent lane

def filter_entry(p, entry):
    f = entry.frame
    if f:
        if CANCEL and peer_has[p][f.group].has(f.index):       # [c8] it became a duplicate
            entry.frame = None
        elif PROJECT and not entry.solicited and projected(p, f.group):    # [c12]
            entry.frame = None
        else:
            sent_to[p][f.group].set(f.index)
    for c in entry.iwants():                                   # the asker drops asks for frames it
        c.ids = [a for a in c.ids if not held(a) and not gated(a)]   # now holds, or no longer pulls (§4.5)
    return entry if not entry.is_empty() else None             # control rides on and survives

def rarest(q):                                                 # [c9]
    best, best_i = inf, 0
    for i, entry in enumerate(q.normal):
        if not entry.frame: break                              # never overtake a control-only entry
        h = len(holders[entry.frame.group][entry.frame.index])
        if h < best: best, best_i = h, i                       # earliest wins ties
    return best_i

def projected(p, g):                                           # [c12]
    has, sent = peer_has[p][g].bits, sent_to[p][g]
    return popcount(has) + FAN_IN * popcount(sent & ~has) >= K(desc[g])
```

- **Cancel** [c8] drops a queued frame if the peer has said it holds it. Answers are cancelled too:
  an ask for a frame the asker had claimed is never answered (§4.5), so only a HAVE sent after the
  ask cancels the answer.
- **Projection** [c12] skips a push to a peer that will reach K without it. It counts what the peer
  holds, plus twice what we have sent it and it has not yet confirmed (FAN_IN = 2 assumes one other
  pusher as fast as us). Answers are never projected away.
- **Rarest at pop** [c9] sends first the queued frame the fewest of our peers hold. It only reorders
  frames ahead of the first control-only entry.
- **The slot is taken before the frame is chosen**, so the window never decides which frame; the
  three rules above do. When filtering leaves no frame, the slot goes back and the writer starts
  again, so another peer's writer may take it.

Without cards 8, 9 and 12 the writer sends its queue in order. Without card 14 it sends as fast as
the transport accepts, and the backlog moves into the transport, where none of the rules above can
act.

## 8. State, limits and constants

### 8.1 State and its lifetime

| state | kept per | lives | when it goes |
|---|---|---|---|
| own frames, ids, `mine`, `received`, `desc`, `state` | group | its active lifetime: `GROUP_TTL` after its last frame arrived or it completed | at expiry, leaving a tombstone (the group id) until the seen cache forgets its frames |
| `origin` | group we publish | the group's active lifetime | with the group [P4] |
| `asked_at` | ask | `IWANT_WINDOW` after the last ask | at expiry, or when the frame arrives |
| `peer_has` (and `holders`, `sent_to` for that peer) | connection and group | `HAVE_TTL` after the peer's last HAVE for the group | at expiry, or when the connection closes; the peer leaves `holders` |
| `pushed` (with `first_push`) | connection and group | `PUSH_TTL` after the last push | at expiry, or when the connection closes |
| `unwanted`, `serve_count` | connection | stock | stock, or when the connection closes |
| offers, `tried` | ask and announcer | 30 s | when the frame arrives, at expiry, or when the announcer's connection closes |
| promises | ask and peer | `PROMISE` | when the frame arrives, or the group completes |
| `park` | peer id and group | `PARK_TTL` | at expiry; kept across reconnections, as scores are |
| deferred frames | block root | until the block installs | when their slot leaves the live window; reservations are released |
| window slots | node | until a covering HAVE | `WINDOW_TIMEOUT`, or when the peer's queue closes |

- **Per-connection state** is reset when the connection closes. A restarted peer usually keeps its
  peer id, so this state must not be keyed by peer id alone.
- **Within a group's active lifetime a node's holdings only grow:** it never drops a frame it has
  claimed (§4.5). Past it, the node keeps only the group's id, as a tombstone; it does not ask for the
  group's frames again, and ignores controls that name the group, without penalty (`expired`).
- **Lifetimes counted in heartbeats** (`HAVE_TTL`, `PUSH_TTL`) are counted by the heartbeat, not
  timed exactly: an entry lives that many heartbeats after it was last refreshed.

**Helpers not written out.**
- *Frames and groups:* `open_group` (records the group's committed descriptor in `desc` and sets
  `state` to COLLECTING), `received` (the frames a node got from the network, as against those it
  rebuilt), `expired` (the group is past its active lifetime: only its tombstone is left),
  `store` (keeps a frame in `frames` and records its id in `known_id`),
  `accepted` (the id was stored), `held` (an ask's frame is in `mine`), `resolve` and `frame_of` (an
  ask's id and stored frame, at an index the node holds, received or rebuilt; nothing for a dropped
  group), `group_index` and `group` (the group and index an ask names, a WantIndex or a structured id, or
  just its group),
  `decode_and_reencode` (§1's decoding: every frame of the group by index, as the source built it,
  proof included; None if the root differs) and `payload_of` (the decompressed body),
  `close_promises` and `close_promises_of_group` (§6.1's promises for an index, or for the whole
  group), `discard_queued` (removes a group's frames, IHAVEs and IWANTs from every queue, keeping
  HAVEs), `gossip_history.remove_group` and `discard_paced` (drop a group from the gossip history
  and from paced jobs), `deliver` (hands the body to the application for level 3), and the codec
  functions of §1.
- *Peers and messages:* `seen` and `mark_seen` (the stock seen cache), `pending_ids` (the ids of
  deferred frames), `valid_have`, `reserve`, `release` and `add_offer` (the checks and reservations
  of §8.2), `Entry` (a queue entry: at most one frame, plus control), `enqueue` (into the bounded
  per-peer queue of §7), `handle_graft_prune` (stock), `penalise` (the client's peer scoring, if it
  has one; a client may ignore it), `tiebreak`
  and `peer_id_bytes` (§5.3), `group_bits` (splits gossip ids by group into bitmaps), and the stock
  `topic_peers`, `connected_topic_peers`, `gossip_eligible`, `connected`, `installed_block` and
  `block_root`.
- *The writer:* `slot_held` (whether a peer's writer holds a slot it has not used; false at first),
  `wake` (runs a peer's writer again, §7.2) and `WAIT` (what `next_to_send` returns while the writer
  waits in line).
- *Timing and sets:* `after` (a timer); `start` (runs a task off the frame path, for as long as the
  task takes: for level 2, a decode, a few milliseconds with an optimised codec, which this document
  does not fix); `shuffled`; `sample_without_replacement`; and the bitmap operations, among them
  `bitmap(indices)`, which builds a bitmap from a set of indices, and `copy`.

A group or per-peer entry that does not exist reads as empty, with `stop_pull` false, and reading it
allocates nothing: the admission checks of §8.2 come before any state is created.

### 8.2 Limits

A node checks a message's shape before it allocates state for it.

| what | limit | at the limit |
|---|---|---|
| a HAVE bitmap | `MAX_HAVE_BYTES` (8192 indices); no index at or beyond N once the descriptor is known | the HAVE is ignored and counts against the sender |
| a descriptor | `valid_descriptor` (§1) | the frame is rejected |
| groups not yet tied to an installed block, named in a peer's HAVEs, IHAVEs or deferred frames | `MAX_PENDING_GROUPS` per peer | the peer's further unknown groups are ignored until one resolves or expires |
| deferred frames | a bounded store with per-peer reservations | the peer's further deferred frames are dropped, neither claimed nor relayed |
| offers | 16 announcers per id, 256 entries per announcer | new offers are refused |
| IHAVE handling | `MAX_IHAVE_MESSAGES` IHAVE-bearing RPCs per peer and heartbeat, and the stock `MAX_IHAVE_LENGTH` ids | further IHAVEs are ignored for the rest of the heartbeat |
| per-peer queue | client-chosen, shared by both lanes | a new entry is dropped, urgent control included: urgency orders dispatch, not admission. A dropped HAVE costs its window slot a timeout |

`MAX_PENDING_GROUPS` and the deferred store's sizes are the client's to set; what this document
fixes is the behaviour at the limit. Frames are deduplicated by id and, once accepted, by index:
only one content per index can pass the proof, so a forged variant costs one proof check and counts
against its sender.

### 8.3 Constants

| name | value | card | why |
|---|---|---|---|
| `UNIT` | 16 KiB | 1 | the unit where A's latency reached its floor (*What segmented payload diffusion is made of*) |
| `MAX_FRAMES` | 256 | 6 | codec limit; above 2 MiB of SSZ the group is plain |
| `MAX_PLAIN_FRAMES` | 8192 | 1 | every group fits one HAVE bitmap |
| `MAX_SEGMENT_SIZE` | 32 KiB | 1 | twice `UNIT`, above snappy's worst-case expansion |
| `MAX_HAVE_BYTES` | 1024 | 7 | 8192 indices |
| `R` | 2 | 3, 11 | the coded group needs less fan-in; 3 without the code at 1 MiB |
| `R_FAST`, `FAST_UPLINK` | 6, 500 Mbps | 17 | the knee: receivers' downlinks bind beyond 6 |
| `STRIPE_UPLINK` | 1 Gbps (configured uplink) | 13 | where striping's gain is measured; the first hop suggests it starts near eight times the peers' uplink, 400 Mbps in the all-home network |
| `IWANT_WINDOW` | 200 ms | 5 | one ask in flight per id, then move on |
| `RETRY_SLACK` | 5 ms | 5 | the retry looks just after the ask's window has closed |
| `PROMISE` | 400 ms | 5 | a late answer is still taken; after this the peer is parked |
| `PARK_K`, `PARK_TTL`, scope | 1, 30 s, per (peer, group) | 5 | bounds capture; a slow peer on one payload is not parked for the next |
| offers | 16 per id, 256 per peer, 30 s | 5 | bounded memory of who announced |
| `GUARD_GRACE` | 200 ms | 16 | about one round trip, so honest peers are not demoted |
| `FAN_IN` | 2 | 12 | one other pusher assumed as fast as us |
| `RTT_REF`, `TARGET` | 112 ms, 20 ms | 14 | the network's mean round trip, plus a small queue |
| `FRAME_BYTES` | ≈ 12 KB | 14 | the encoded frame at 1 MiB |
| `WINDOW_TIMEOUT` | 500 ms | 14 | a lost acknowledgement frees its slot |
| pace tick | heartbeat / 16 = 43.75 ms | 15 | one announcement per tick |
| `MAX_IHAVE_MESSAGES` | 4096 | 3, 7 | one IHAVE per frame and peer when announcing instead of pushing; stock gossipsub's 10 would drop most of them. Batching each peer's announcements would let it stay low |
| `MAX_IHAVE_LENGTH`, `D_LAZY`, `GOSSIP_FACTOR`, `GOSSIP_RETRANSMISSION` | 5000, 6, 0.25, 3 | – | stock gossipsub |
| `HAVE_TTL` | 3 heartbeats after the peer's last HAVE for the group | 7 | stock IDONTWANT expiry |
| `PUSH_TTL` | 6 heartbeats after the last push | 16 | the message cache's length |
| `GROUP_TTL` | at least 7 heartbeats and the seen cache's lifetime, after the group's last frame or its completion | – | a group outlives its diffusion |
| heartbeat, mesh, cache | 700 ms, D = 8, 6 / 3 heartbeats | – | Prysm's gossipsub settings |

**Open: the push degree against payload size.** The measured tier 4 runs at R = 2 at 1 MiB and was
swept over sizes with R = 4, 3, 2 by size (4 at 128 KiB). The rule should be keyed on K rather
than on the uncompressed size, and is not yet fixed.

## 9. As measured: where the research implementation differs

The measurements in the post come from a research harness. Where it does something this document
does not specify, and what that means for the numbers:

**Harness shortcuts, not part of the protocol.**
- *No validation.* Frames were accepted, claimed and relayed on arrival, with no proof check and no
  block gate (section 3); the simulated slot has no blocks. The measurements therefore exclude block
  propagation, relay gating and proof validation, and do not quantify what those add. With the block
  installed, the proof check before a claim adds microseconds; a frame ahead of its block waits for
  it.
- *The wire format.* The measured frames used a 101-byte structured id (slot, a synthetic block
  root, group, index, content id) and a custom segment encoding inside an SSZ byte field. Their
  descriptor had no `encoding` field, compress-first being configured outside, so their group ids
  differ from §1's. The payload was generated bytes, not a serialised
  `ExecutionPayloadSegmentBody`. The longer id inflates control bytes against the 56-byte id of
  section 2; HAVE and WANT strings have their own lengths. Each frame carried the descriptor
  (design A).
- *K was fixed at 64* rather than derived from `UNIT`. At 1 MiB both give 64. The codec allowed up
  to 16384 frames, more than a HAVE bitmap can name; §1 caps a group at 8192.
- *No decode.* Completion was counted at K distinct received frames, where the decode claim went
  out, as in this document (§4.6). Decoding, re-encoding, decompression and the application's checks
  did not run, so delivery's latency is not in the numbers; optimised implementations decode and
  check in a few milliseconds. No frame was rebuilt, so the measured runs did not repair (§4.6): a
  decoded node pushed, served and announced only frames it had received. Repair was measured in
  separate runs, on top of tier 4, with each node handed the frames its decode would rebuild 5 ms
  after its K-th frame (*What a forwarding node checks, and when it decodes*, 2026). On the post's clean
  networks it should have little to act on, since every frame is released and a rebuilt frame is
  one more copy of a plentiful one; on thin links with every frame released it changed nothing
  measurable.
- *Stop-pull* ran as a harness gate that flips at completion. The decode claim already makes every
  index of the group non-askable, so the effect is the one in §6.2.
- *The fast class* was read from the simulator's link settings, and the window's round trip and
  frame size from the cell's configuration. A node would configure its uplink.
- *Striping* was set on or off per cell; this document selects it by the configured uplink
  (`STRIPE_UPLINK`).
- *Per-peer dispatch state* existed from the first send only because a measurement option set it
  up. Without it, a peer's first frames would have skipped rarest-first, projection and the window.
  This document creates it with the connection.
- *The random heartbeat phase* was overwritten on the segmented arms, so every node's first
  heartbeat fell at the same offset from its start. Paced gossip's ticks follow the heartbeat.
- *Random draws* (the lower-half draw, shuffles) used the process-global generator, with no seed
  the harness controlled, and the source enqueued its targets in the order of a Go map's iteration;
  §5.1 keeps the selector's order.
- *The guard and the window.* The measured implementation required the window for card 16's guard,
  so the runs without card 14 also ran without the guard. The guard needs only HAVEs (§0).

**Behaviours that shaped the numbers, as measured, and where this document departs.**
- *Announcing on arrival.* With no validation, a node claimed a frame as it arrived. This document
  claims it after level 1 (§4.2).
- *The source's HAVE* went out once per frame as each was added to the batch: N cumulative HAVEs to
  each mesh peer, all before the data, which names the source to its mesh. This document paces it
  instead (§5.1, [P4]). A change of 2026-10-07 makes the implementation send one HAVE before the
  data by default, and pace it as an option (`SEGMENT_SRC_HAVE=paced`).
- *The sender counts as a holder* in a forwarding node's budget (§5.2), so R = 2 means one further push per
  received frame. This is what was measured. The sender is also excluded from the candidates here;
  in the code it could take a budget slot and then be skipped, which is rare.
- *Control waits behind the window.* While frames are queued to a peer, that peer's IHAVE, IWANT,
  GRAFT and PRUNE on the normal lane wait for a slot, though they do not keep it. A writer waiting
  for a slot also lost its place in line whenever an urgent message arrived for it; this document
  keeps its place (§7.1). Whether control should bypass the window is open. At home only the
  source's window filled in the measured cells, so the other nodes were not affected.
- *A slot frees when the peer holds the frame from anyone,* not when our copy arrives. A decode
  claim frees all of that peer's slots at once.
- *Holder counts for rarest-first* only ever increased: a departed peer's claims were dropped, but
  not its share of the counts, and a peer whose HAVE expired and was re-sent was counted twice. This
  document counts distinct live holders.
- *An ask by index for a frame the asker had claimed* was answered: the measured node cleared that
  claim in the asker's send queue, for cancel and projection only, and kept it everywhere else. This
  document drops such an ask (§4.5), and the asker drops queued asks for frames it holds (§7.2). The
  asker's queue kept such asks, and its HAVE, on the urgent lane, overtook them: the answers arrived
  as duplicates, 0.1 % of them at home and 2 to 3 % on the datacenter mix. A change of 2026-10-07
  makes the implementation do as this document does.
- *Promises were not closed on decode* for the park. Asks still open when a node decoded broke at
  400 ms and parked the asked peers for the completed group only, which changed no later decision.
  This document closes them.
- *The offer-table retry* picked untried announcers in peer-id order; this document takes the
  earliest to have announced. A retry that finds every announcer parked stops, and the frame waits
  for a fresh announcement.
- *An ask dropped at a full queue* was lost, and its promise still fell due.
- *The IHAVE limit.* The measured handler allowed 4096 control-bearing RPCs per peer per heartbeat,
  a counter that also counts RPCs carrying other control. §8.3 makes a raised limit part of the
  protocol and counts only IHAVE-bearing RPCs.
- *Clearing promises on decode* in the stock gossip tracer had no effect in the measured cells,
  because the harness runs no peer scoring. In a client that scores peers it keeps honest peers from
  being penalised for asks the decode made unnecessary.
- *No block evidence.* Neither push selector checked that its target holds the block (§3); the
  measured runs had no blocks.
- *Serving.* A measured node served frames from its message cache, six heartbeats long. This
  document serves a group's frames for the group's active lifetime (§8.1).
- *The pacer* skipped a job within the same tick when per-id holding evidence had removed all its
  ids; only a job emptied while its ids became bitmaps consumed the tick. This document consumes
  the tick in both cases.
- *Per-peer tables:* offers, retries and answer counts were keyed by peer id and survived a
  reconnection. §8.1 resets them with the connection.
