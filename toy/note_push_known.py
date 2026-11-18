#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.4's note_push and §4.7's unpush: a send noted, and undone, under every group
the chunk fills, from the ids alone.

    python3 note_push_known.py

- **A chunk not stored.** forward runs whatever fill did, and fill stores nothing for a group dropped at level 2.
  On a small payload run (one payload, run to its end), a group is made dropped and one of its chunks taken out of
  the store: note_push of that chunk must not need it, and must note the send under the group.
- **The other axis, noted and undone.** On a small rows run (one block), a cell's push through its column is noted
  under the column and under the row (R4); unpush, a push that will not be made, must clear both. The control: a
  push noted under one group alone, the payload's, is cleared by unpush as before.
"""
import sys
from pathlib import Path


def sim_of(args):
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(args)
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    return sim


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    pay = sim_of(["--doc", "v2", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7"])
    nd = pay.nodes[2]
    ns = nd.ns
    g = pay.msgs[0][1][0]
    i = sorted(ns["chunks"][g])[0]
    q = sorted(nd.peers)[0]
    ns["state"][g] = "INVALID"                              # dropped at level 2: nothing more is stored
    ns["chunks"][g].pop(i, None)
    ns["pushed"][q].pop(g, None)
    try:
        ns["note_push"](q, g, i)
        got = ("noted", ns["pushed"][q][g].has(i))
    except Exception as e:
        got = (f"raised {type(e).__name__}", None)
    line("a chunk of a dropped group, not stored: note_push", got, ("noted", True))
    ns["unpush"](q, g, i)
    line("the payload's push undone (control): noted under its group", ns["pushed"][q][g].has(i), False)

    rows = sim_of(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7"])
    nd = rows.nodes[2]
    ns = nd.ns
    T_row = nd._types["row"]
    gr = next(g for g in ns["T_of"] if rows.gtype.get(g) == "row"
              and len(ns["chunks"][g]) == T_row.index_count(ns["hdr"][g]))
    c = sorted(ns["chunks"][gr])[0]
    (gc, b), = T_row.cross(gr, c)                           # the cell's column group, and its index there
    q = sorted(nd.peers)[0]
    for gg in (gr, gc):
        ns["pushed"][q].pop(gg, None)
    ns["note_push"](q, gc, b)                               # a push through the column
    line("a cell's push through its column: noted under the column, and under the row",
         (ns["pushed"][q][gc].has(b), ns["pushed"][q][gr].has(c)), (True, True))
    ns["unpush"](q, gc, b)                                  # not made after all
    line("unpush of it: the column's mark, and the row's", (ns["pushed"][q][gc].has(b), ns["pushed"][q][gr].has(c)),
         (False, False))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
