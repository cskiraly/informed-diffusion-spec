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
    """One group's bitmap, as a message-id string (§2)."""
    __slots__ = ("group", "bits")

    def __init__(self, group, bits):
        self.group, self.bits = group, Bits(bits.v)       # a snapshot: the node's own map keeps growing

    def wire_len(self):
        v = self.bits.v
        return 4 + 1 + 32 + (v.bit_length() + 7) // 8      # trailing zero bytes dropped


class WantIndex:
    """An ask by index (§2). Equal asks are one key in the asker's tables."""
    __slots__ = ("group", "index")

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


def is_have_bitmap(entry):
    return isinstance(entry, HaveBitmap)


def id_len(x):
    return x.wire_len() if isinstance(x, (HaveBitmap, WantIndex)) else len(x)


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


def IHAVE(x):
    return Control([_IHave(x if isinstance(x, list) else [x])])


def IWANT(ids):
    return Control([_IWant(ids)])


def IDONTWANT(x):
    return Control([_IDontWant(x if isinstance(x, list) else [x])])


def PRUNE(prunes):
    return Control([_Prune(prunes)])


class Entry:
    """A queue entry: at most one chunk, plus control (§7.2)."""
    __slots__ = ("chunk", "control", "solicited")

    def __init__(self, chunk=None, control=None, solicited=False):
        self.chunk, self.control, self.solicited = chunk, control, solicited

    def iwants(self):
        return [m for m in self.control.items if m.kind == "iwant"] if self.control else []

    def is_empty(self):
        return self.chunk is None and (self.control is None or self.control.empty())


class RPC:
    """What a receiver's on_rpc sees: the entry's chunk and its control, grouped by kind (§4.1)."""
    __slots__ = ("chunks", "ihave", "iwant", "idontwant", "prune")

    def __init__(self, entry):
        self.chunks = [entry.chunk] if entry.chunk is not None else []
        ih, iw, idw, pr = [], [], [], []
        if entry.control:
            for m in entry.control.items:
                {"ihave": ih, "iwant": iw, "idontwant": idw, "prune": pr}[m.kind].extend(m.ids)
        self.ihave, self.iwant, self.idontwant, self.prune = _IHave(ih), _IWant(iw), idw, pr


# ---- wire sizes (bytes charged to the links and counted as received)

TOPIC_BYTES = 48          # the payload topic's name in an IHAVE
RPC_OVERHEAD = 6          # stream length prefix and the RPC's own tags
FIELD = 3                 # tag and length of one repeated field


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
    """(data bytes, control bytes) of one RPC."""
    data = chunk_wire(e.chunk) if e.chunk is not None else 0
    ctrl = (control_wire(e.control) if e.control else 0) + RPC_OVERHEAD
    return data, ctrl
