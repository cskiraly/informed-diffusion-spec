#!/usr/bin/env python3
"""A known answer for a cell sent once to a peer, whichever of its two groups the send went through (protocol-v2.md
§4.4's note_push, R4).

    python3 rebuilt_once_known.py

A cell belongs to a column and to a row. A send of it to a peer, a push or an answer, is noted under every group it
fills, so the other group's repair, forward or offer does not send it to that peer again.

On one node of a small rows run (protocol-v2.md, one block, run to its end), made by hand, on a row the node holds
whole: a cell of it is taken out of its store (the row still decoding), at an index whose column a peer q custodies.
q sends a standing WANT for that cell on the row, and nothing of the column is known of q. The row is decoded
(decode_group): the answer goes to q through the row, and push_rebuilt then looks at the column, where q is a
custodian short of the cell. q's queue must hold the cell once. The control: a custodian of the column that made
no WANT is pushed the cell once, by the repair.
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
    pick = None                                             # (index, the column's group, its custodian q, another r)
    for i in sorted(ns["chunks"][g]):
        (g2, _), = T_row.cross(g, i)
        T2 = ns["type_of_group"](g2)
        qs = [q for q in T2.params.REPAIR_TO(g2) if q in nd.peers]
        if len(qs) >= 2:
            pick = (i, g2, qs[0], qs[1])
            break
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    line("a cell whose column two of the node's peers custody", pick is not None, True)
    i, g2, q, r = pick
    f = ns["chunks"][g][i]
    i2 = next(j for (gg, j) in T_row.project(f) if gg == g2)
    del ns["chunks"][g][i]                                  # still decoding: claimed, not stored
    ns["known_id"][g].pop(i, None)
    ns["received"][g].clear(i); ns["rebuilt"][g].clear(i)
    for gg, j in ((g2, i2),):
        ns["received"][gg].clear(j); ns["rebuilt"][gg].clear(j)
        ns["chunks"][gg].pop(j, None)
        ns["known_id"][gg].pop(j, None)                     # store() writes both: not stored, so not accepted
    for x in (q, r):                                        # nothing of either group known of q and r, nothing sent
        for gg in (g, g2):
            ns["peer_has"][x].pop(gg, None)
            ns["pushed"][x].pop(gg, None)
        ns["queue"][x].normal[:] = []; ns["queue"][x].urgent[:] = []
    ns["on_want"](q, [Wm.FlaggedWant(g, i, True, 0)])      # q's standing WANT on the row
    line(f"peer {q} stands for the cell on the row", q in ns["standing"][g].get(i, ()), True)
    ns["state"][g] = "DECODING"
    ns["decode_group"](g)

    def sends(x):                                           # entries of this cell in x's queue: (solicited, ...)
        qx = ns["queue"][x]
        return [e.solicited for e in list(qx.urgent) + list(qx.normal) if e.chunk is not None
                and e.chunk.index == f.index and e.chunk.group == f.group]
    line(f"peer {q}, standing on the row and custodian of the column: the cell's sends in its queue", sends(q), [True])
    line(f"peer {r}, custodian of the column only (control): the cell's sends in its queue", sends(r), [False])
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
