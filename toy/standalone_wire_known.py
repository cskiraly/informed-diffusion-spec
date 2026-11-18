#!/usr/bin/env python3
"""A known answer for protocol-v2-bindings.md §1, the standalone binding's bytes: an encoder written from the text.

    python3 standalone_wire_known.py

- Every message kind (§1.2, §1.3) is built at its smallest and its largest, encoded as SSZ, and decoded back to
  the same message.
- The largest body of each kind must equal §1.6's bound, the fixed kinds their size, and §1.7's sizes must hold.
  Both tables are read from the document itself, as is §1.2's table of kinds.
- Frames (§1.5): every frame §1.6 allows needs at most 3 bytes of length, and a reader that takes a stream of
  frames:
  - must refuse a frame over its kind's bound from its length and kind alone, before its body is read;
  - must refuse a chunk whose stated decompressed length is over the bound, before decompressing;
  - must refuse a body that does not decode;
  - must skip a frame of an unknown kind and read the next.
- Waggle's carriage (§1.8): each message is carried as (objectID, piecesMetadata, pieces) and read back.

`BINDINGS_DOC=<path>` reads another copy of the document: one with a wrong number in a table must fail.

The snappy here is the block format with literals only on the writing side, which any reader takes; the reader
also takes copies. The toy's runs charge no compression (§1.7: sizes before it).
"""
import os
import re
import struct
import sys
from pathlib import Path

DOC = Path(os.environ.get("BINDINGS_DOC") or Path(__file__).resolve().parent.parent / "protocol-v2-bindings.md")

MAX_HAVE_BYTES = 1024
MAX_SEGMENT_SIZE = 32 * 1024                # protocol.md §8.3: twice UNIT
MAX_PROOF = 14                              # protocol.md §2's Chunk: List[Bytes32, 14]
BYTES_PER_CELL = 2048
MAX_BLOB_COMMITMENTS_PER_BLOCK = 4096
INCLUSION_DEPTH = 4                         # KZG_COMMITMENTS_INCLUSION_PROOF_DEPTH
SIGNED_HEADER = 8 + 8 + 32 + 32 + 32 + 96   # SignedBeaconBlockHeader: the header's five fields and the signature

KINDS = {0x01: "JOIN", 0x02: "GRAFT", 0x03: "PRUNE", 0x04: "HAVE", 0x05: "WANT", 0x06: "CHUNK_PAYLOAD",
         0x07: "CHUNK_CELL"}
CHUNK_KINDS = (0x06, 0x07)


class Violation(Exception):
    pass


# ---- SSZ, as much as these types need


def u(n, x):
    return int(x).to_bytes(n, "little")


def take(b, off, n):
    if off + n > len(b):
        raise Violation("short body")
    return b[off:off + n], off + n


def container(fixed, var):
    """fixed: bytes of the fixed fields in order, with None where a variable field's offset goes; var: their bytes."""
    size = sum(4 if f is None else len(f) for f in fixed)
    out, tail, vi = [], [], 0
    for f in fixed:
        if f is None:
            out.append(u(4, size + sum(len(t) for t in tail)))
            tail.append(var[vi]); vi += 1
        else:
            out.append(f)
    return b"".join(out + tail)


def variable_parts(b, fixed_len, n_var):
    """The variable fields' bytes, from the offsets at the given positions of the fixed part."""
    offs = [struct.unpack_from("<I", b, p)[0] for p in fixed_len]
    if any(o > len(b) for o in offs) or offs != sorted(offs):
        raise Violation("bad offset")
    ends = offs[1:] + [len(b)]
    return [b[a:e] for a, e in zip(offs, ends)][:n_var]


def group_id(t, key, index):
    return u(1, t) + key + u(2, index)


def bits_bytes(indices):
    if not indices:
        return b""
    n = max(indices) // 8 + 1
    v = bytearray(n)
    for i in indices:
        v[i // 8] |= 1 << (i % 8)
    return bytes(v)


def enc(kind, m):
    if kind == 0x01:
        return u(1, m["type"]) + m["fork"] + u(1, m["interest"]) + u(8, m["custody"]) + u(1, m["duty"]) + u(2, m["colours"])
    if kind == 0x02:
        return u(1, m["type"]) + u(2, m["family"]) + u(2, m["colour"]) + u(1, m["direction"]) + u(1, m["answer"])
    if kind == 0x03:
        return u(1, m["type"]) + u(2, m["family"]) + u(2, m["colour"]) + u(1, m["direction"])
    if kind == 0x04:
        return container([m["group"], u(1, m["flags"]), None], [m["bits"]])
    if kind == 0x05:
        return container([m["group"], u(1, m["flags"]), u(1, m["hops"]), None], [m["bits"]])
    if kind == 0x06:
        d = m["descriptor"]
        return container([u(8, m["slot"]), m["root"], m["group"], d, u(4, m["index"]), None, None],
                         [b"".join(m["proof"]), m["data"]])
    if kind == 0x07:
        hdr = b"".join(container([None, m["header"]["signed"], b"".join(m["header"]["proof"])],
                                 [b"".join(m["header"]["commitments"])]) for _ in range(1 if m["header"] else 0))
        hlist = (u(4, 4) + hdr) if m["header"] else b""         # a list of one variable-size element: its offset
        return container([m["group"], u(4, m["index"]), m["cell"], m["proof"], None], [hlist])
    raise ValueError(kind)


def dec(kind, b):
    if kind == 0x01:
        if len(b) != 17:
            raise Violation("JOIN size")
        return {"type": b[0], "fork": b[1:5], "interest": b[5], "custody": int.from_bytes(b[6:14], "little"),
                "duty": b[14], "colours": int.from_bytes(b[15:17], "little")}
    if kind == 0x02:
        if len(b) != 7 or b[6] > 1:
            raise Violation("GRAFT")
        return {"type": b[0], "family": int.from_bytes(b[1:3], "little"), "colour": int.from_bytes(b[3:5], "little"),
                "direction": b[5], "answer": b[6]}
    if kind == 0x03:
        if len(b) != 6:
            raise Violation("PRUNE size")
        return {"type": b[0], "family": int.from_bytes(b[1:3], "little"), "colour": int.from_bytes(b[3:5], "little"),
                "direction": b[5]}
    if kind == 0x04:
        if len(b) < 40:
            raise Violation("HAVE short")
        bits, = variable_parts(b, [36], 1)
        if len(bits) > MAX_HAVE_BYTES or struct.unpack_from("<I", b, 36)[0] != 40:
            raise Violation("HAVE bitmap")
        return {"group": b[:35], "flags": b[35], "bits": bits}
    if kind == 0x05:
        if len(b) < 41:
            raise Violation("WANT short")
        bits, = variable_parts(b, [37], 1)
        if len(bits) > MAX_HAVE_BYTES or struct.unpack_from("<I", b, 37)[0] != 41:
            raise Violation("WANT bitmap")
        return {"group": b[:35], "flags": b[35], "hops": b[36], "bits": bits}
    if kind == 0x06:
        if len(b) < 135 or struct.unpack_from("<I", b, 127)[0] != 135:
            raise Violation("CHUNK short")
        proof, data = variable_parts(b, [127, 131], 2)
        if len(proof) % 32 or len(proof) > 32 * MAX_PROOF or len(data) > MAX_SEGMENT_SIZE:
            raise Violation("CHUNK lists")
        return {"slot": int.from_bytes(b[:8], "little"), "root": b[8:40], "group": b[40:72], "descriptor": b[72:123],
                "index": int.from_bytes(b[123:127], "little"),
                "proof": [proof[i:i + 32] for i in range(0, len(proof), 32)], "data": data}
    if kind == 0x07:
        if len(b) < 2139 or struct.unpack_from("<I", b, 2135)[0] != 2139:
            raise Violation("CELL short")
        hlist = b[2139:]
        header = None
        if hlist:
            if len(hlist) < 4 or struct.unpack_from("<I", hlist, 0)[0] != 4:
                raise Violation("CELL header list")
            h = hlist[4:]
            if len(h) < 340 or struct.unpack_from("<I", h, 0)[0] != 340:
                raise Violation("CELL header")
            comm = h[340:]
            if len(comm) % 48 or len(comm) > 48 * MAX_BLOB_COMMITMENTS_PER_BLOCK:
                raise Violation("CELL commitments")
            header = {"signed": h[4:4 + SIGNED_HEADER],
                      "proof": [h[212 + 32 * k:244 + 32 * k] for k in range(INCLUSION_DEPTH)],
                      "commitments": [comm[i:i + 48] for i in range(0, len(comm), 48)]}
        return {"group": b[:35], "index": int.from_bytes(b[35:39], "little"), "cell": b[39:2087], "proof": b[2087:2135],
                "header": header}
    raise ValueError(kind)


# ---- snappy's block format: literals when writing; literals and copies when reading


def uvarint(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        out.append(x | (0x80 if n else 0))
        if not n:
            return bytes(out)


def read_uvarint(b, off):
    n = shift = 0
    while True:
        if off >= len(b) or shift > 63:
            raise Violation("bad varint")
        x = b[off]; off += 1
        n |= (x & 0x7F) << shift
        if not x & 0x80:
            return n, off
        shift += 7


def snappy(data):
    out = bytearray(uvarint(len(data)))
    for i in range(0, len(data), 65536):
        lit = data[i:i + 65536]
        n = len(lit) - 1
        if n < 60:
            out.append(n << 2)
        elif n < 256:
            out += bytes([60 << 2, n])
        else:
            out += bytes([61 << 2]) + n.to_bytes(2, "little")
        out += lit
    return bytes(out)


def unsnappy(b, bound):
    n, off = read_uvarint(b, 0)
    if off > 5:
        raise Violation("snappy: a length preamble over five bytes")      # a uint32's varint, as snappy's own reader
    if n > bound:
        raise Violation(f"decompressed length {n} over the bound {bound}")    # before decompressing

    def need(k):                                            # the input must hold the next k bytes
        if off + k > len(b):
            raise Violation("snappy: the input ends inside an element")
    out = bytearray()
    while off < len(b):
        tag = b[off]; off += 1
        t = tag & 3
        if t == 0:
            ln = tag >> 2
            if ln >= 60:
                k = ln - 59
                need(k)
                ln = int.from_bytes(b[off:off + k], "little"); off += k
            ln += 1
            need(ln)
            out += b[off:off + ln]; off += ln
        else:
            if t == 1:
                need(1)
                ln, o = 4 + ((tag >> 2) & 7), ((tag >> 5) << 8) | b[off]; off += 1
            elif t == 2:
                need(2)
                ln, o = 1 + (tag >> 2), int.from_bytes(b[off:off + 2], "little"); off += 2
            else:
                need(4)
                ln, o = 1 + (tag >> 2), int.from_bytes(b[off:off + 4], "little"); off += 4
            if o == 0 or o > len(out):
                raise Violation("bad copy")
            for _ in range(ln):
                out.append(out[-o])
        if len(out) > n:
            raise Violation("over the stated length")
    if len(out) != n:
        raise Violation("short of the stated length")
    return bytes(out)


# ---- frames (§1.5) and a reader that refuses before it reads


def frame(kind, m):
    body = enc(kind, m)
    if kind in CHUNK_KINDS:
        body = snappy(body)
    return uvarint(1 + len(body)) + bytes([kind]) + body


def frame_room(kind, bounds):
    n = bounds[kind]
    return 1 + (32 + n + n // 6 if kind in CHUNK_KINDS else n)       # kind byte and the body, compressed at worst


class Reader:
    """Reads frames from bytes; `read` counts how many body bytes it has taken, to show a refusal took none."""

    def __init__(self, data, bounds):
        self.b, self.off, self.bounds, self.body_bytes_read = data, 0, bounds, 0

    def next(self):
        ln, off = read_uvarint(self.b, self.off)
        if off >= len(self.b):
            raise Violation("no kind byte")
        kind = self.b[off]
        room = frame_room(kind, self.bounds) if kind in self.bounds else max(frame_room(k, self.bounds) for k in KINDS)
        if ln > room:                                               # an unknown kind: the largest known kind's room
            raise Violation(f"frame of {ln} bytes over kind {kind:#04x}'s room")       # nothing of the body read
        body = self.b[off + 1:off + ln]
        if len(body) != ln - 1:
            raise Violation("short frame")
        self.body_bytes_read += len(body)
        self.off = off + ln
        if kind not in self.bounds:
            return kind, None                                            # unknown: skipped, without penalty
        if kind in CHUNK_KINDS:
            body = unsnappy(body, self.bounds[kind])
        if len(body) > self.bounds[kind]:
            raise Violation("body over the bound")
        return kind, dec(kind, body)


# ---- Waggle's carriage (§1.8)


def to_waggle(kind, m):
    body = enc(kind, m)
    if kind in (0x01, 0x02, 0x03):
        return b"\x00", bytes([kind]) + body, b""
    if kind in CHUNK_KINDS:
        return m["group"] if kind == 0x07 else group_id(0, m["group"], 0), bytes([kind]), snappy(body)
    return m["group"], bytes([kind]) + body, b""


def from_waggle(object_id, meta, pieces, bounds):
    kind = meta[0]
    if kind not in bounds:                                          # an unknown kind: skipped, without penalty, but held
        if len(meta) + len(pieces) > max(frame_room(k, bounds) for k in KINDS):   # to the largest known room
            raise Violation(f"an unknown kind {kind:#04x} over the largest room")
        return kind, None
    body = unsnappy(pieces, bounds[kind]) if kind in CHUNK_KINDS else meta[1:]
    m = dec(kind, body)
    gid = {0x04: lambda: m["group"], 0x05: lambda: m["group"], 0x07: lambda: m["group"],
           0x06: lambda: group_id(0, m["group"], 0)}.get(kind, lambda: b"\x00")()
    if gid != object_id:
        raise Violation("objectID")
    return kind, m


# ---- the document's own tables, and §1.3's layout

LAYOUT = {                                  # §1.3 as this encoder writes it: aliases, then each container's fields
    "aliases": {"TypeId": "uint8", "FamilyId": "uint16", "Direction": "uint8", "InterestKind": "uint8",
                "Duty": "uint8", "MAX_HAVE_BYTES": "1024", "Bitmap": "ByteList[MAX_HAVE_BYTES]"},
    "GroupId": [("type", "TypeId"), ("key", "Bytes32"), ("index", "uint16")],
    "JoinMsg": [("object_type", "TypeId"), ("fork_digest", "ForkDigest"), ("interest", "InterestKind"),
                ("custody_count", "uint64"), ("duty", "Duty"), ("colours", "uint16")],
    "GraftMsg": [("object_type", "TypeId"), ("family", "FamilyId"), ("colour", "uint16"), ("direction", "Direction"),
                 ("answer", "boolean")],
    "PruneMsg": [("object_type", "TypeId"), ("family", "FamilyId"), ("colour", "uint16"), ("direction", "Direction")],
    "HaveMsg": [("group", "GroupId"), ("flags", "Bitvector[8]"), ("bits", "Bitmap")],
    "WantMsg": [("group", "GroupId"), ("flags", "Bitvector[8]"), ("hops", "uint8"), ("bits", "Bitmap")],
    "CellChunk": [("group", "GroupId"), ("index", "uint32"), ("cell", "ByteVector[BYTES_PER_CELL]"),
                  ("proof", "KZGProof"), ("header", "List[PartialDataColumnHeader, 1]")],
}
FIXED = {"uint8": 1, "uint16": 2, "uint32": 4, "uint64": 8, "boolean": 1, "Bytes32": 32, "ForkDigest": 4,
         "KZGProof": 48, "Bitvector[8]": 1, "ByteVector[BYTES_PER_CELL]": BYTES_PER_CELL}


def doc_layout(text):
    """§1.3's python block: its aliases and its containers' fields, in order."""
    sec = text[text.index("### 1.3 The types"):text.index("### 1.4")]
    block = sec[sec.index("```python") + len("```python"):sec.index("```", sec.index("```python") + 9)]
    out, cur = {"aliases": {}}, None
    for ln in block.splitlines():
        code = ln.split("#")[0].rstrip()
        if not code:
            continue
        m = re.match(r"^class (\w+)\(Container\):$", code)
        if m:
            cur = out.setdefault(m.group(1), [])
            continue
        m = re.match(r"^    (\w+): (.+)$", code)
        if m and cur is not None:
            cur.append((m.group(1), m.group(2).strip()))
            continue
        m = re.match(r"^(\w+) = (.+)$", code)
        if m:
            if m.group(1) in out["aliases"]:                  # a name defined twice: the fields would read the last
                out.setdefault("unparsed", []).append(code)   #   definition, which this check must not trust
            out["aliases"][m.group(1)] = m.group(2).strip()
            cur = None
            continue
        out.setdefault("unparsed", []).append(code)           # anything else is a change this check must see
    return out


def fixed_size(layout, name):
    """A container's fixed part from a layout: a variable field counts its 4-byte offset."""
    total = 0
    for _, t in layout[name]:
        t = layout["aliases"].get(t, t)
        if t in layout and t != "aliases":
            total += fixed_size(layout, t)
        elif t in FIXED:
            total += FIXED[t]
        elif t.startswith(("ByteList[", "List[")):
            total += 4
        else:
            raise Violation(f"unknown type {t!r} in {name}")
    return total


def num(s):
    return int(s.replace(" ", ""))


def doc_tables():
    text = DOC.read_text()
    kinds = {int(k, 16): v for k, v in re.findall(r"^\| `(0x0[0-9])` \| ([A-Z]+)", text, re.M)}
    lim = text[text.index("### 1.6 Limits"):text.index("### 1.7")]
    row = lambda name: re.search(r"^\| " + re.escape(name) + r" \| ([^|]+)\|", lim, re.M).group(1)
    nums = lambda s: [num(x) for x in re.findall(r"\d{1,3}(?: \d{3})*", s)]
    j, g, p = nums(row("JOIN, GRAFT, PRUNE"))[:3]
    h, w = nums(row("HAVE, WANT"))[:2]
    bounds = {0x01: j, 0x02: g, 0x03: p, 0x04: h, 0x05: w,
              0x06: nums(row("CHUNK of the payload"))[0], 0x07: nums(row("CHUNK of a cell"))[0]}
    siz = text[text.index("### 1.7 Sizes"):text.index("### 1.8")]
    srow = lambda name: re.search(r"^\| " + re.escape(name) + r" \|[^|]*\| ([^|]+)\|", siz, re.M).group(1).strip()
    sizes = {k: srow(k) for k in ("JOIN", "GRAFT", "PRUNE", "HAVE, holding or offer", "WANT, one index i",
                                 "CHUNK, a cell", "CHUNK, the payload")}
    return kinds, bounds, sizes, doc_layout(text)


def main():
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    kinds, bounds, sizes, layout = doc_tables()
    line("§1.3's layout, as the document writes it, against this encoder's", layout, LAYOUT)
    line("§1.3's fixed parts: GroupId, JOIN, GRAFT, PRUNE, HAVE, WANT, a cell",
         [fixed_size(layout, c) for c in ("GroupId", "JoinMsg", "GraftMsg", "PruneMsg", "HaveMsg", "WantMsg",
                                          "CellChunk")], [35, 17, 7, 6, 40, 41, 2139])
    line("§1.2's kinds, as the document lists them", kinds,
         {1: "JOIN", 2: "GRAFT", 3: "PRUNE", 4: "HAVE", 5: "WANT", 6: "CHUNK", 7: "CHUNK", 8: "EVIDENCE"})
    root, key = b"\x11" * 32, b"\x22" * 32
    col = group_id(1, root, 127)
    line("a GroupId's size", len(col), 35)

    hdr = lambda n: {"signed": b"\x05" * SIGNED_HEADER, "proof": [b"\x06" * 32] * INCLUSION_DEPTH,
                     "commitments": [b"\x07" * 48] * n}
    smallest = {
        0x01: {"type": 0, "fork": b"\0" * 4, "interest": 0, "custody": 0, "duty": 0, "colours": 1},
        0x02: {"type": 0, "family": 0, "colour": 0, "direction": 0, "answer": 0},
        0x03: {"type": 0, "family": 0, "colour": 0, "direction": 0},
        0x04: {"group": group_id(0, key, 0), "flags": 0, "bits": b""},
        0x05: {"group": group_id(0, key, 0), "flags": 0, "hops": 0, "bits": b""},
        0x06: {"slot": 0, "root": root, "group": key, "descriptor": b"\0" * 51, "index": 0, "proof": [], "data": b""},
        0x07: {"group": col, "index": 0, "cell": b"\0" * BYTES_PER_CELL, "proof": b"\0" * 48, "header": None},
    }
    largest = {
        0x01: {"type": 2, "fork": b"\xff" * 4, "interest": 2, "custody": 2 ** 64 - 1, "duty": 1, "colours": 65535},
        0x02: {"type": 2, "family": 65535, "colour": 65535, "direction": 2, "answer": 1},
        0x03: {"type": 2, "family": 65535, "colour": 65535, "direction": 2},
        0x04: {"group": col, "flags": 7, "bits": b"\xff" * MAX_HAVE_BYTES},
        0x05: {"group": col, "flags": 3, "hops": 255, "bits": b"\xff" * MAX_HAVE_BYTES},
        0x06: {"slot": 2 ** 64 - 1, "root": root, "group": key, "descriptor": b"\x01" * 51, "index": 2 ** 32 - 1,
               "proof": [b"\x03" * 32] * MAX_PROOF, "data": b"\x04" * MAX_SEGMENT_SIZE},
        0x07: {"group": col, "index": 4095, "cell": b"\x08" * BYTES_PER_CELL, "proof": b"\x09" * 48,
               "header": hdr(MAX_BLOB_COMMITMENTS_PER_BLOCK)},
    }
    for k in sorted(KINDS):
        lo, hi = enc(k, smallest[k]), enc(k, largest[k])
        line(f"{KINDS[k]}: round trips, smallest and largest", (dec(k, lo) == smallest[k], dec(k, hi) == largest[k]),
             (True, True))
        line(f"{KINDS[k]}: the largest body against §1.6's bound", len(hi), bounds[k])

    line("every frame §1.6 allows: bytes of length, at most", max(len(uvarint(frame_room(k, bounds))) for k in KINDS), 3)

    # §1.7's sizes, on the stream (uncompressed for chunks)
    on_stream = lambda k, m: len(uvarint(1 + len(enc(k, m)))) + 1 + len(enc(k, m))
    have16 = {"group": col, "flags": 0, "bits": b"\xff" * 16}
    want = lambda i: {"group": col, "flags": 1, "hops": 0, "bits": bits_bytes([i])}
    cell48 = dict(largest[0x07], header=hdr(48))
    pay = lambda p, n: dict(smallest[0x06], proof=[b"\x03" * 32] * p, data=b"\x04" * n)
    line("§1.7: JOIN, GRAFT, PRUNE",
         [on_stream(1, smallest[1]), on_stream(2, smallest[2]), on_stream(3, smallest[3])],
         [num(sizes["JOIN"]), num(sizes["GRAFT"]), num(sizes["PRUNE"])])
    have = lambda n: {"group": col, "flags": 0, "bits": b"\xff" * n}
    line("§1.7: a HAVE of b bytes is 42 + b up to b = 86 and 43 + b from 87",
         ([on_stream(4, have(n)) - n for n in (16, 86, 87, MAX_HAVE_BYTES)], sizes["HAVE, holding or offer"]),
         ([42, 42, 43, 43], "42 + b; 43 + b from b = 87"))
    line("§1.7: a WANT of index i is 44 + ⌊i/8⌋ up to i = 679 and 45 + ⌊i/8⌋ from 680",
         ([on_stream(5, want(i)) - i // 8 for i in (0, 127, 679, 680)], sizes["WANT, one index i"]),
         ([44, 44, 44, 45], "44 + ⌊i/8⌋; 45 + ⌊i/8⌋ from i = 680"))
    line("§1.7: a cell without a header, and with a 48-blob header",
         [on_stream(7, smallest[7]), on_stream(7, cell48)],
         [num(x) for x in re.findall(r"\d{1,3}(?: \d{3})*", sizes["CHUNK, a cell"])[0::2]])   # 2 142; 48-blob; 4 790
    line("§1.7: the payload's chunk, 138 + 32p + data below a 16 384-byte frame and 139 above",
         (on_stream(6, pay(1, 1000)) - 32 - 1000, on_stream(6, pay(14, MAX_SEGMENT_SIZE)) - 32 * 14 - MAX_SEGMENT_SIZE),
         (138, 139))

    # a stream of frames, read back; and what the reader must refuse
    good = b"".join(frame(k, largest[k]) for k in sorted(KINDS)) + uvarint(4) + b"\x09abc" + frame(1, smallest[1])
    r, got = Reader(good, bounds), []
    while r.off < len(good):
        got.append(r.next())
    line("a stream of the largest frames, an unknown kind among them, read back",
         ([k for k, _ in got], [m == largest.get(k) for k, m in got[:7]], got[7], got[8][1] == smallest[1]),
         (sorted(KINDS) + [0x09, 0x01], [True] * 7, (0x09, None), True))

    def refused(data):
        rd = Reader(data, bounds)
        try:
            rd.next()
            return False, rd.body_bytes_read
        except Violation:
            return True, rd.body_bytes_read

    over = enc(4, {"group": col, "flags": 0, "bits": b"\xff" * (MAX_HAVE_BYTES + 1)})
    line("a HAVE frame one byte over its bound: refused, with no body byte read",
         refused(uvarint(1 + len(over)) + b"\x04" + over), (True, 0))
    huge = snappy(enc(7, largest[7]) + b"\0" * 64)              # a cell body past the bound, compressed
    line("a cell frame whose stated decompressed length is over the bound: refused",
         refused(uvarint(1 + len(huge)) + b"\x07" + huge)[0], True)
    line("a JOIN body one byte short: refused", refused(uvarint(17) + b"\x01" + enc(1, smallest[1])[:-1])[0], True)
    line("a HAVE whose bitmap offset points past the body: refused",
         refused(uvarint(41) + b"\x04" + col + b"\x00" + u(4, 99))[0], True)
    line("the controls, the largest HAVE and cell frames: accepted",
         [refused(frame(4, largest[4]))[0], refused(frame(7, largest[7]))[0]], [False, False])

    # Waggle's carriage
    back = []
    for k in sorted(KINDS):
        oid, meta, pieces = to_waggle(k, largest[k])
        back.append(from_waggle(oid, meta, pieces, bounds) == (k, largest[k]) and (oid == b"\x00") == (k <= 3))
    line("Waggle's carriage: every kind read back, objectID 0x00 for JOIN, GRAFT and PRUNE", back, [True] * len(KINDS))
    line("Waggle's carriage: an unknown kind skipped", from_waggle(b"\x00", b"\x09abc", b"", bounds), (0x09, None))
    big = max(frame_room(k, bounds) for k in KINDS)

    def waggle(meta, pieces):
        try:
            return from_waggle(b"\x00", meta, pieces, bounds)
        except Violation:
            return "refused"
    line("Waggle's carriage: an unknown kind at the largest room, and one byte over it",
         [waggle(b"\x09" + bytes(big - 1), b""), waggle(b"\x09" + bytes(big), b"")], [(0x09, None), "refused"])

    # snappy's block format, read: copies, and input that ends inside an element
    def snap(b):
        try:
            return unsnappy(bytes(b), 1 << 20)
        except Violation:
            return "refused"
    line("snappy: a literal then a one-byte-offset copy, and a two-byte-offset copy",
         [snap([8, 0x0C, 97, 98, 99, 100, 0x01, 4]), snap([8, 0x0C, 97, 98, 99, 100, 0x0E, 4, 0])],
         [b"abcdabcd", b"abcdabcd"])
    line("snappy: a literal short of its length, and a copy short of its offset: refused",
         [snap([1, 0x04, 0x41]), snap([2, 0x00, 0x41, 0x02, 0x01])], ["refused", "refused"])
    line("snappy: a length preamble of six bytes, refused; of five, read",
         [snap([0x81, 0x80, 0x80, 0x80, 0x80, 0x00, 0x00, 0x41]), snap([0x81, 0x80, 0x80, 0x80, 0x00, 0x00, 0x41])],
         ["refused", b"A"])
    line("a frame of an unknown kind over the largest known kind's room: refused, with no body byte read",
         refused(uvarint(max(frame_room(k, bounds) for k in KINDS) + 1) + b"\x09")[0:2], (True, 0))

    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                      # a table the reader could not parse, or a refusal not expected
        print(f"stopped: {type(e).__name__}: {e}  <-- must run to its end")
        print("FAIL")
        sys.exit(1)
