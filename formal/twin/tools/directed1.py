#!/usr/bin/env python3
"""Directed records for protocol.md §1's seven functions (group_id, group_key, K, N, segment_length,
valid_descriptor, build_group), and §2's message_id. The toy's own functions are called in a toy node's namespace
on drawn arguments, and trace3.py's tracer logs each call, with the node's whole state (the seven touch none of it).

    python3 directed1.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not: the cells call §1's functions on the honest descriptors of three
payloads. Here, first a fixed list of edges, then N draws from pools that hold them:
- K where the Python's true division is not the exact ceiling: `total_length` 2^53 + 1 and 2^53 + 3 over 1, 2^54 + 1
  over 4, 2^64 - 1; the pair where two conversions and a division differ from it (15177058598789620474 over 85295);
  and 2^62 + 513 over 1, where K is 2^62 + 1024 and the last data chunk's length is negative;
- K and N of no descriptor (an AttributeError), and a segment_size of 0 (a ZeroDivisionError);
- valid_descriptor at each chain's bound (2K at 254, 256 and 258; K at 8191, 8192 and 8193), at MAX_SEGMENT_SIZE - 1,
  at it and above it, and every other branch;
- segment_length at the last data chunk, before it and after it;
- group_id with each field one beyond serialize's width (the toy's serialize raises an OverflowError: a question
  that raises, written on the tape as one);
- group_key with a slot of 2^64 - 1 and of 2^64 (an OverflowError), and ids of 0, 31 and 33 bytes;
- message_id (§2) of a chunk whose id the toy has not stored yet, of the same chunk again, and of an index of 2^32
  (an OverflowError before content_id is asked);
- build_group with bodies of 0 bytes (a ZeroDivisionError), of 1, around UNIT, at the coded limit (128 UNIT), one
  byte over it, and at 150 UNIT (plain).

The node is node 2 of a 5-node cell built as run.py builds it (no event runs); the seven are the document's own
code there, which the tracer checks at its install. A sample on which the Python raises is written with `raises`
by the tracer; the counts are printed.
"""
import argparse
import math
import random
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402

DOUBLE = (15177058598789620474, 85295)  # a / b and float(a) / float(b) have different ceilings


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed1", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import run                          # noqa: E402: the pinned toy's
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    nd = got["sim"].nodes[2]
    ns = nd.ns
    UNIT, MAX_CHUNKS = ns["UNIT"], ns["MAX_CHUNKS"]
    tr.install(nd, ns)
    rng = random.Random(a.seed)

    D = ns["SegmentDescriptor"]

    def mk(version, hash_id, encoding, count, ss, tl, root=None):
        return D(version=version, hash_id=hash_id, encoding=encoding, count=count, segment_size=ss, total_length=tl,
                 root=root if root is not None else rng.randbytes(32))

    def k_of(tl, ss):
        return math.ceil(tl / ss) if ss else 0

    SS = [1, 2, 3, 4, 7, 85295, UNIT, 2 * UNIT - 1, 2 * UNIT, 2 * UNIT + 1, 2 ** 32 - 1]
    BIG = [2 ** 53 - 1, 2 ** 53, 2 ** 53 + 1, 2 ** 53 + 3, 2 ** 54 + 1, DOUBLE[0], 2 ** 64 - 1]

    def draw_desc():
        ss = 0 if rng.random() < 0.04 else rng.choice(SS + [rng.randint(1, 2 * UNIT)] * 4)
        mode = rng.random()
        if mode < 0.08:
            tl = rng.choice([0, 1] + BIG + [rng.getrandbits(64)])
        elif mode < 0.16 and ss:
            tl = rng.randint(8190, 8196) * ss + rng.choice((-1, 0, 0, 1))       # at the plain bound
        else:
            tl = max(0, rng.randint(0, 300) * max(ss, 1) + rng.choice((-1, 0, 0, 0, 1)))
        k = k_of(tl, ss)
        version = rng.choice((1, 1, 1, 1, 2, 2, 2, 2, 0, 3))
        count = rng.choice((k, k, k, 2 * k, 2 * k, 2 * k, k + 1, 2 * k + 1, max(0, 2 * k - 1), 0, MAX_CHUNKS,
                            MAX_CHUNKS + 1, MAX_CHUNKS + 2, 8192, 8193, rng.randint(0, 600)))
        if rng.random() < 0.6:
            count = 2 * k if version == 2 else k
        encoding = ({2: 1, 1: 0}.get(version, 0) if rng.random() < 0.85 else rng.choice((0, 1, 2)))
        hash_id = 0 if rng.random() < 0.93 else 1
        return mk(version, hash_id, encoding, min(count, 2 ** 32 - 1), ss, tl)

    def body(n):
        return Wm.Blob(n, ("body", n))

    # ---- the fixed edges, then the draws
    samples = []
    for tl, ss in [(2 ** 53 + 1, 1), (2 ** 53 + 3, 1), (2 ** 54 + 1, 4), DOUBLE, (2 ** 64 - 1, 1), (2 ** 64 - 1, 2 ** 32 - 1),
                   (2 ** 53, 1), (2 ** 53 - 1, 1),
                   (2 ** 62 + 513, 1),     # K is 2^62 + 1024, and the last data chunk's length −510
                   (0, 5), (1, 5), (5, 5), (6, 5), (5, 0), (0, 0)]:
        k = k_of(tl, ss)
        for version, count in ((1, k), (2, 2 * k)):
            d = mk(version, 0, 2 - version, min(count, 2 ** 32 - 1), ss, tl)
            samples += [("K", [d]), ("valid_descriptor", [d]), ("segment_length", [d, max(0, k - 1)]),
                        ("segment_length", [d, 0]), ("N", [d]), ("group_id", [d])]
    samples += [("K", [None]), ("N", [None])]
    for k in (MAX_CHUNKS // 2 - 1, MAX_CHUNKS // 2, MAX_CHUNKS // 2 + 1):     # the coded chain's bound, 2K against MAX_CHUNKS
        samples.append(("valid_descriptor", [mk(2, 0, 1, 2 * k, 1000, 1000 * k)]))
    for k in (8191, 8192, 8193):                                               # the plain chain's bound
        samples.append(("valid_descriptor", [mk(1, 0, 0, k, 1000, 1000 * k)]))
    for ss in (2 * UNIT - 1, 2 * UNIT, 2 * UNIT + 1):                          # MAX_SEGMENT_SIZE
        samples.append(("valid_descriptor", [mk(1, 0, 0, 3, ss, 3 * ss)]))
    for over in ((256, 0, 0, 1, 1, 1), (1, 256, 0, 1, 1, 1), (1, 0, 256, 1, 1, 1), (1, 0, 0, 2 ** 32, 1, 1),
                 (1, 0, 0, 1, 2 ** 32, 1), (1, 0, 0, 1, 1, 2 ** 64)):          # a field beyond serialize's width
        samples.append(("group_id", [mk(*over)]))
    for slot in (0, 1, 2 ** 32, 2 ** 64 - 1, 2 ** 64):
        samples.append(("group_key", [rng.randbytes(32), slot]))
    for n in (0, 1, UNIT - 1, UNIT, UNIT + 1, 2 * UNIT, 5 * UNIT + 7, 64 * UNIT, (MAX_CHUNKS // 2) * UNIT,
              (MAX_CHUNKS // 2) * UNIT + 1, 150 * UNIT):
        samples.append(("build_group", [body(n)]))
    for _ in range(a.n):
        fn = rng.choice(("K",) * 4 + ("N",) + ("segment_length",) * 4 + ("valid_descriptor",) * 6 + ("group_id",) * 2
                        + ("group_key",) * 2)
        if fn == "group_key":
            args = [rng.randbytes(rng.choice((32,) * 8 + (0, 31, 33))),
                    rng.choice((0, 1, rng.getrandbits(64), rng.getrandbits(20), 2 ** 64 - 1, 2 ** 64))]
        elif fn == "segment_length":
            d = draw_desc()
            k = k_of(d.total_length, d.segment_size)
            args = [d, max(0, rng.choice((0, k - 1, k - 1, k - 1, k, k - 2, d.count - 1, rng.randint(0, 300))))]
        elif fn in ("K", "N") and rng.random() < 0.02:
            args = [None]
        else:
            args = [draw_desc()]
        samples.append((fn, args))
    for _ in range(12):
        samples.append(("build_group", [body(rng.randint(0, 20 * UNIT))]))

    # §2's message_id, with the toy's own content_id: a chunk with no id stored, which the toy's wrapper computes
    # and stores; the same chunk again, its id stored now; and an index beyond a uint32, where the document's
    # uint32_le raises before content_id is asked
    def chunk(i, n):
        return types.SimpleNamespace(slot=1, beacon_block_root=bytes([0xa1]) * 32, group=bytes([0x11]) * 32, index=i,
                                     data=Wm.Blob(n, ("data", i, n)))
    for _ in range(200):
        f = chunk(rng.choice((0, 1, 255, 2 ** 32 - 1, rng.randrange(8192))), rng.randrange(1, 4096))
        samples.append(("message_id", [f]))
        if rng.random() < 0.5:
            samples.append(("message_id", [f]))
    samples.append(("message_id", [chunk(2 ** 32, 5)]))

    raised = Counter()
    for fn, args in samples:
        try:
            ns[fn](*args)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[f"{fn}: {type(e).__name__}"] += 1
    tr.close()
    print(f"directed1: {sum(tr.counts.values())} records, raised {dict(sorted(raised.items()))}, "
          f"{dict(sorted(tr.counts.items()))}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
