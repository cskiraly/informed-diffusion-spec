#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.6's probe that reaches a claimant still decoding (R5).

    python3 probe_decode_known.py

A claimant that decodes claims every index at once, before it has stored the cells it rebuilds. A marked probe
of such a cell finds nothing (`resolve`); the claimant keeps the first one per asker and group, and answers it
with its exemption when the cell is stored, rebuilt included (`probe_waiting`, `serve_waiting_probe`). The toy's
decode takes 5 ms, so no run meets the case; it is made by hand.

On one node of a small rows run (protocol-v2.md, one block, run to its end), for a row the node holds whole:
three of its cells are taken out of its store, as if it were still decoding, its claim on them kept. Then:
- peer 1 sends a marked probe of the first cell, and a second marked probe, of the second cell (only the first
  per asker and group is kept);
- peer 3 sends a plain ask of the third cell (the control: a plain ask of a cell not stored is not kept);
- the row is decoded (`decode_group`, the document's), which stores the three cells again.

After the decode, peer 1's queue holds a solicited answer of the first cell, its exemption taken (`probe_served`
and `probe_answers`), and none of the second; peer 3's queue holds no solicited answer of the third.
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
    p1, p3 = sorted(nd.peers)[:2]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def answered(p, f):                                     # a solicited answer of f in p's queue
        q = ns["queue"].get(p)
        return q is not None and any(e.chunk is f and e.solicited for e in list(q.urgent) + list(q.normal))

    line("while decoding: the node claims the three cells, and holds none of them",
         ([ns["mine"][g].has(i) for i in cells], [i in ns["chunks"][g] for i in cells]),
         ([True] * 3, [False] * 3))
    ans = ns["on_want"](p1, [Wm.FlaggedWant(g, i1, False, 0, probe=True)])
    ans += ns["on_want"](p1, [Wm.FlaggedWant(g, i2, False, 0, probe=True)])
    ans += ns["on_want"](p3, [Wm.WantIndex(g, i3)])
    line("while decoding: answers given at once", ans, [])
    ns["state"][g] = "DECODING"
    ns["decode_group"](g)
    line("after the decode: the three cells stored again", [i in ns["chunks"][g] for i in cells], [True] * 3)
    f1 = cells[i1]
    line(f"peer {p1}'s first marked probe: answered (solicited, in its queue), its exemption taken",
         (answered(p1, f1), bool(ns["probe_served"][p1][g]), ns["probe_answers"][p1][f1.group].has(f1.index)),
         (True, True, True))
    line(f"peer {p1}'s second marked probe: answered", answered(p1, cells[i2]), False)
    line(f"peer {p3}'s plain ask (the control): answered", answered(p3, cells[i3]), False)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
