#!/usr/bin/env python3
"""A known answer for what an ask by id names (§2, §4.5, §8.1): a group and an index only if it is a chunk's
structured id, of exactly 56 bytes.

    python3 id_parse_known.py           # protocol.md, then protocol-v2.md on top of it

A chunk's id is structured: the group's 32 bytes, the index as uint32 little-endian, and a 20-byte content id,
"32 + 4 + 20 bytes" (§2); §4.4's `valid_id` takes nothing else for one. §8.1's `group_index` gives the group and
index of a WantIndex or a structured id. An id of any other length names neither, so an IWANT of it is not
answered (`resolve` finds nothing) and counts against nobody, even where the asker has claimed the chunk that its
first 36 bytes would name.

The check, on one node of a small network that is built and not run, its one payload published and chunk 0 stored
there: IWANTs, each alone in a frame through `on_frame`. From peer 3: ids of 36, 40, 55 and 57 bytes whose first 36
bytes name chunk 0 must get no answer; the chunk's own id and a WantIndex of it are answered (the controls), and
so is none of an inherited 20-byte id (the control below 36). From peer 4, which has claimed chunk 0: a 40-byte id
must count nothing against it; the chunk's own id counts one, the claim winning (the control). Peer 3's count of
answers per id is cleared between asks, so that the stock limit of three does not decide.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q, R = 7, 2, 1, 3, 4                         # peer 1 publishes; 3 asks; 4 has claimed chunk 0


def check(doc):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    from bits import bitmap
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "65536", "--seed", str(SEED)]
             + (["--doc", "v2"] if doc == "v2" else []))
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"])
    sim.publish(1)
    nd = sim.nodes[NODE]
    ns = nd.ns
    (g, chunks), = sim.canonical.items()
    f0 = chunks[0]
    ns["on_chunk"](P, f0)                                   # stored: chunk 0 of a group of K = 4
    mid = ns["message_id"](f0)
    ns["on_frame"](R, Wm.Frame(Wm.Entry(control=Wm.IDONTWANT(Wm.HaveBitmap(group=g, bits=bitmap({0}))))))
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def ask(q, a):                                          # (group_index names something, answers, penalties)
        if q in ns["serve_count"]:
            del ns["serve_count"][q]
        before, pen = len(ns["queue"][q].normal), nd.penalties
        ns["on_frame"](q, Wm.Frame(Wm.Entry(control=Wm.IWANT([a]))))
        answers = sum(1 for e in ns["queue"][q].normal[before:] if e.chunk is f0)
        return ns["group_index"](a) is not None, answers, nd.penalties - pen

    for n in (36, 40, 55, 57):
        a = (mid + bytes([0x44]))[:n]
        line(f"an ask of {n} bytes, its first 36 those of chunk 0's id: named, answers, penalties", ask(Q, a),
             (False, 0, 0))
    line("the control: chunk 0's own id, 56 bytes", ask(Q, mid), (True, 1, 0))
    line("the control: a WantIndex of chunk 0", ask(Q, Wm.WantIndex(g, 0)), (True, 1, 0))
    line("the control: an inherited id, 20 bytes", ask(Q, mid[36:]), (False, 0, 0))
    line("from the peer that claimed chunk 0, an ask of 40 bytes", ask(R, mid[:40]), (False, 0, 0))
    line("the control: from that peer, chunk 0's own id (the claim wins)", ask(R, mid), (True, 0, 1))
    return bad


def main():
    bad = 0
    for doc in ("v03", "v2"):
        print(f"--doc {doc}:")
        bad += check(doc)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
