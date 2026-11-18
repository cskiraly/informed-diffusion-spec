"""Runtime stand-ins for the pseudocode's wire types (§1, §2) and the queue entry (§7).

The toy does not move real bytes. A payload is a Blob that knows its length and where it came
from; chunks, bitmaps and asks are small objects; and every message is charged the bytes its wire
form would take (wire_bytes), which is what the byte counts of a run add up.
"""
import hashlib

from bits import Bits


# ---- payload bytes


class Blob:
    """A byte string of known length and provenance, never materialised."""
    __slots__ = ("n", "tag")

    def __init__(self, n, tag):
        self.n, self.tag = n, tag

    def __len__(self):
        return self.n

    def __getitem__(self, s):
        a, b, _ = s.indices(self.n)
        return Blob(max(0, b - a), (self.tag, a, b))


def sha256(b):
    return hashlib.sha256(b).digest()


def serialize(x):
    """Enough of SSZ for group_id: a descriptor's fields, in order."""
    return b"".join([
        x.version.to_bytes(1, "little"), x.hash_id.to_bytes(1, "little"),
        x.encoding.to_bytes(1, "little"), x.count.to_bytes(4, "little"),
        x.segment_size.to_bytes(4, "little"), x.total_length.to_bytes(8, "little"), x.root,
    ])


DESCRIPTOR_BYTES = 1 + 1 + 1 + 4 + 4 + 8 + 32


def uint32_le(i):
    return int(i).to_bytes(4, "little")


def uint64_le(i):
    return int(i).to_bytes(8, "little")


def content_id(f):
    """The 20-byte Altair id over the topic and the decompressed chunk: here, over its identity."""
    return sha256(b"content" + f.group + uint32_le(f.index) + repr(f.data.tag).encode())[:20]


# ---- annotation-only types of the pseudocode: they must evaluate, and mean nothing at run time


class _Ann:
    def __getitem__(self, _):
        return self

    def __call__(self, *a, **k):
        raise TypeError("annotation type used as a constructor")


uint8 = uint32 = uint64 = Bytes32 = Root = Slot = Result = _Ann()
List = ByteList = Optional = Tuple = _Ann()


class Container:
    """SSZ containers of the pseudocode: built by keyword, read by attribute."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---- classes the pseudocode declares without a constructor; they replace its declarations


class Shard:
    __slots__ = ("index", "proof", "data")

    def __init__(self, index, proof, data):
        self.index, self.proof, self.data = index, proof, data


class HaveBitmap:
    """One group's bitmap, as a message-id string (§2). Under protocol-v2.md the two claims of a
    holding ride beside the bitmap (protocol-v2-bindings.md §3), charged no bytes here; v0.3 reads them
    from a full bitmap."""
    __slots__ = ("group", "bits", "claim_all", "complete")

    def __init__(self, group, bits):
        self.group, self.bits = group, Bits(bits.v)       # a snapshot: the node's own map keeps growing
        self.claim_all = self.complete = False

    def wire_len(self):
        v = self.bits.v
        return 4 + 1 + 32 + (v.bit_length() + 7) // 8      # trailing zero bytes dropped


class WantIndex:
    """An ask by index (§2). Equal asks are one key in the asker's tables."""
    __slots__ = ("group", "index")
    standing, hops, probe = False, 0, False   # protocol-v2.md §2's WANT fields: a plain ask has none

    def __init__(self, group, index):
        self.group, self.index = group, index

    def __eq__(self, o):
        return isinstance(o, WantIndex) and o.group == self.group and o.index == self.index

    def __hash__(self):
        return hash((self.group, self.index))

    def wire_len(self):
        return 4 + 1 + 32 + 4

    def __repr__(self):
        return f"WantIndex({self.group[:3].hex()}, {self.index})"


class FlaggedWant(WantIndex):
    """An ask from a WANT with protocol-v2.md §2's `standing` and `hops` ([D12]) or `probe` (R5), carried
    beside the index (protocol-v2-bindings.md §3) and charged no bytes here: the same key as the plain ask, the
    same bytes on the wire."""
    __slots__ = ("standing", "hops", "probe")

    def __init__(self, group, index, standing, hops, probe=False):
        super().__init__(group, index)
        self.standing, self.hops, self.probe = standing, hops, probe


def is_have_bitmap(entry):
    return isinstance(entry, HaveBitmap)


def id_len(x):
    if isinstance(x, (HaveBitmap, WantIndex)):
        return x.wire_len()
    if hasattr(x, "family"):                    # protocol-v2.md §2's GRAFT or PRUNE (--upkeep on)
        return REL_BYTES
    if hasattr(x, "interest") and hasattr(x, "colours"):
        return JOIN_BYTES                       # §2's JOIN (--upkeep on)
    return len(x)


# ---- control messages and queue entries


class Control:
    """A list of control messages; `+` concatenates (§4.1's IWANT(asks) + PRUNE(prunes))."""
    __slots__ = ("items",)

    def __init__(self, items=()):
        self.items = list(items)

    def __add__(self, o):
        return Control(self.items + o.items)

    def empty(self):
        return all(m.empty() for m in self.items)


class _Msg:
    __slots__ = ("ids",)
    kind = "?"

    def __init__(self, ids):
        self.ids = list(ids)

    def empty(self):
        return not self.ids


class _IHave(_Msg):
    kind = "ihave"


class _IWant(_Msg):
    kind = "iwant"


class _IDontWant(_Msg):
    kind = "idontwant"


class _Prune(_Msg):
    kind = "prune"


class _Graft(_Msg):                             # protocol-v2.md §2's GRAFT, sent only under --upkeep on
    kind = "graft"


class _Join(_Msg):                              # §2's JOIN, the same: on v0.3's wire it is the subscription
    kind = "join"


def IHAVE(x):
    return Control([_IHave(x if isinstance(x, list) else [x])])


def IWANT(ids):
    return Control([_IWant(ids)])


def IDONTWANT(x):
    return Control([_IDontWant(x if isinstance(x, list) else [x])])


def PRUNE(prunes):
    return Control([_Prune(prunes)])


def GRAFT(grafts):
    return Control([_Graft(grafts)])


def JOIN(joins):
    return Control([_Join(joins)])


class Entry:
    """A queue entry: at most one chunk, plus control (§7.2)."""
    __slots__ = ("chunk", "control", "solicited", "at", "urgent")

    def __init__(self, chunk=None, control=None, solicited=False):
        self.chunk, self.control, self.solicited = chunk, control, solicited
        self.at = self.urgent = None    # the toy's: when and on which lane it was queued (invariants.py)

    def iwants(self):
        return [m for m in self.control.items if m.kind == "iwant"] if self.control else []

    def add_ihave(self, h):
        c = IHAVE(h)
        self.control = c if self.control is None else self.control + c

    def is_empty(self):
        return self.chunk is None and (self.control is None or self.control.empty())


class Frame:
    """What a receiver's on_frame sees of one gossipsub frame: the entry's chunk and its control, grouped by kind (§4.1)."""
    __slots__ = ("chunks", "ihave", "iwant", "idontwant", "prune", "graft", "join")

    def __init__(self, entry):
        self.chunks = [entry.chunk] if entry.chunk is not None else []
        ih, iw, idw, pr, gr, jn = [], [], [], [], [], []
        if entry.control:
            for m in entry.control.items:
                {"ihave": ih, "iwant": iw, "idontwant": idw, "prune": pr, "graft": gr, "join": jn}[m.kind].extend(m.ids)
        self.ihave, self.iwant, self.idontwant, self.prune = _IHave(ih), _IWant(iw), idw, pr
        self.graft, self.join = gr, jn


# ---- wire sizes (bytes charged to the links and counted as received)

TOPIC_BYTES = 48          # the payload topic's name in an IHAVE
FRAME_OVERHEAD = 6        # a gossipsub frame's length prefix and its protobuf `RPC`'s own tags
FIELD = 3                 # tag and length of one repeated field
REL_BYTES = TOPIC_BYTES + 4    # a GRAFT or PRUNE: the type's topic, then family, colour and direction (§2)
JOIN_BYTES = TOPIC_BYTES + 12  # a JOIN: the topic, then interest, custody count, duty and M (§2)


def chunk_wire(f):
    """Chunk SSZ (§2) inside a gossipsub Message: data dominates."""
    ssz = 8 + 32 + 32 + DESCRIPTOR_BYTES + 4 + 4 + 32 * len(f.proof) + 4 + len(f.data)
    return ssz + FIELD + TOPIC_BYTES + FIELD


def control_wire(c):
    n = 0
    for m in c.items:
        if m.empty():
            continue
        n += FIELD + sum(FIELD + id_len(x) for x in m.ids)
        if m.kind == "ihave":
            n += FIELD + TOPIC_BYTES
    return n


def entry_wire(e):
    """(data bytes, control bytes) of one queue entry on v0.3's wire: one gossipsub frame."""
    data = chunk_wire(e.chunk) if e.chunk is not None else 0
    ctrl = (control_wire(e.control) if e.control else 0) + FRAME_OVERHEAD
    return data, ctrl


# ---- the standalone binding's sizes (protocol-v2-bindings.md §1; run.py --wire standalone)
# Each message is a frame of its own on the stream (§1.5): a uvarint length, a kind byte, the body (§1.3). Sizes are
# before compression (§1.7), as the toy's data are not real bytes.

GROUP_ID = 1 + 32 + 2                   # GroupId: type, key, index
HAVE_FIXED = GROUP_ID + 1 + 4           # HaveMsg: the group, flags, the bitmap's offset
WANT_FIXED = GROUP_ID + 1 + 1 + 4       # WantMsg: the group, flags, hops, the bitmap's offset
JOIN_BODY, GRAFT_BODY, PRUNE_BODY = 17, 7, 6
CELL_BODY = GROUP_ID + 4 + 2048 + 48 + 4    # CellChunk without a header: the group, index, cell, proof, the list's offset
CELL_HEADER = 4 + 340                   # a header in that list: its offset, and PartialDataColumnHeader but its commitments
COMMITMENT = 48                         # one KZG commitment of the header


def uvarint_len(n):
    k = 1
    while n >= 0x80:
        n >>= 7
        k += 1
    return k


def frame_len(body):
    return uvarint_len(1 + body) + 1 + body


def standalone_chunk(f, cell, header_blobs=None):
    """A chunk's frame: a cell's CellChunk, with the header when header_blobs is given; the payload's Chunk (0x06)."""
    if cell:
        return frame_len(CELL_BODY + (CELL_HEADER + COMMITMENT * header_blobs if header_blobs is not None else 0))
    return frame_len(8 + 32 + 32 + DESCRIPTOR_BYTES + 4 + 4 + 4 + 32 * len(f.proof) + len(f.data))


def _index(x):
    return x.index if isinstance(x, WantIndex) else int.from_bytes(bytes(x[32:36]), "little")   # or a structured id


def standalone_control(c):
    """The control messages of an entry, each its own frame: a HAVE per bitmap (an IDONTWANT's is a holding, an
    IHAVE's an offer), a WANT per ask, a JOIN, GRAFT or PRUNE each (§1.3)."""
    n = 0
    for m in c.items:
        for x in m.ids:
            if m.kind in ("ihave", "idontwant"):
                b = (x.bits.v.bit_length() + 7) // 8 if isinstance(x, HaveBitmap) else _index(x) // 8 + 1
                n += frame_len(HAVE_FIXED + b)
            elif m.kind == "iwant":
                n += frame_len(WANT_FIXED + _index(x) // 8 + 1)
            elif m.kind == "join":
                n += frame_len(JOIN_BODY)
            elif m.kind == "graft":
                n += frame_len(GRAFT_BODY)
            elif m.kind == "prune":
                n += frame_len(PRUNE_BODY)
    return n
