#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.5's standing WANTs, answered when a decode stores the cell.

    python3 standing_decode_known.py

A WANT for a chunk the node does not hold yet stands: a `DECLARED` peer's always, any peer's when it says
`standing` (§2, §4.5, §4.10). It is answered when the chunk is stored, received or rebuilt (`serve_standing`,
from `fill` and `decode_group`). A rebuilt chunk fills its other groups through `fill`, which answers their
standing WANTs; the group being decoded stores its own rebuilt chunks itself, and answers them there.

On one node of a small rows run (protocol-v2.md, one block, run to its end), for a row the node holds whole:
three of its cells are taken out of its store, as if it were still decoding, its claim on them kept. Then:
- peer 1, a `DECLARED` link, sends a plain WANT of the first cell (it stands: a declared peer's WANT does);
- peer 3, a `DERIVED` link, sends a WANT of the second cell that says `standing`;
- peer 4, a `DERIVED` link, sends a plain WANT of the third cell (the control: it does not stand);
- the row is decoded (`decode_group`, the document's), which stores the three cells again.

After the decode, peers 1 and 3 each hold a solicited answer of their cell in their queue, each charged one
answer against the serving limit, and neither WANT stands any longer; peer 4's queue holds no solicited answer.
"""
import sys
from pathlib import Path

SEED, NODE = 7, 2


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    T_row = nd._types["row"]
    g = next(g for g in ns["T_of"] if sim.gtype.get(g) == "row"
             and len(ns["chunks"][g]) == T_row.index_count(ns["hdr"][g]))
    i1, i2, i3 = sorted(ns["chunks"][g])[:3]
    cells = {i: ns["chunks"][g][i] for i in (i1, i2, i3)}
    for i in cells:                                         # still decoding: claimed, not stored
        del ns["chunks"][g][i]
        ns["known_id"][g].pop(i, None)
        ns["received"][g].clear(i); ns["rebuilt"][g].clear(i)
    p1, p3, p4 = sorted(nd.peers)[:3]
    kinds = [ns["join_recv"][p][T_row].interest for p in (p1, p3, p4)]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def answered(p, f):                                     # a solicited answer of f in p's queue
        q = ns["queue"].get(p)
        return q is not None and any(e.chunk is f and e.solicited for e in list(q.urgent) + list(q.normal))

    line(f"the links' interest (peers {p1}, {p3}, {p4})", kinds, ["DECLARED", "DERIVED", "DERIVED"])
    line("while decoding: the node claims the three cells, and holds none of them",
         ([ns["mine"][g].has(i) for i in cells], [i in ns["chunks"][g] for i in cells]),
         ([True] * 3, [False] * 3))
    served0 = [ns["served"][p][g] for p in (p1, p3, p4)]
    ans = ns["on_want"](p1, [Wm.WantIndex(g, i1)])
    ans += ns["on_want"](p3, [Wm.FlaggedWant(g, i2, True, 0)])
    ans += ns["on_want"](p4, [Wm.WantIndex(g, i3)])
    line("while decoding: answers given at once", ans, [])
    line("while decoding: who stands for each cell",
         [sorted(ns["standing"][g].get(i, ())) for i in (i1, i2, i3)], [[p1], [p3], []])
    ns["state"][g] = "DECODING"
    ns["decode_group"](g)
    line("after the decode: the three cells stored again", [i in ns["chunks"][g] for i in cells], [True] * 3)
    line(f"peer {p1}'s standing WANT (declared): answered (solicited, in its queue)", answered(p1, cells[i1]), True)
    line(f"peer {p3}'s standing WANT (flagged): answered (solicited, in its queue)", answered(p3, cells[i2]), True)
    line(f"peer {p4}'s plain WANT (the control): answered", answered(p4, cells[i3]), False)
    line("answers charged against the serving limit",
         [ns["served"][p][g] - s for p, s in zip((p1, p3, p4), served0)], [1, 1, 0])
    line("after the decode: who stands for each cell",
         [sorted(ns["standing"][g].get(i, ())) for i in (i1, i2, i3)], [[], [], []])
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
