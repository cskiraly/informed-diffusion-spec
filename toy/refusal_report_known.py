#!/usr/bin/env python3
"""A known answer for the toy's report of asks left unanswered (`Node.refused`, run.py's "asks left unanswered by
the asked node"), for protocol-v2.md's marked probe (R5).

    python3 refusal_report_known.py

The claim rule (§4.5) leaves unanswered an ask of an index the asker's holding names, and the report counts it
as "claimed". A marked probe of an index the node claims is answered whatever the asker holds, once per asker and
group (`probe_of_claim`), so the report must not count it. On one node of a small rows run (protocol-v2.md, one
block, run to its end), for a row cell the node holds, each asker's holding made to name it:
- a plain ask from peer 1 (the control): counted "claimed";
- a marked probe from peer 3: not counted;
- a second marked probe from peer 3, after the first was answered, a plain ask by the cap (the control):
  counted "claimed".
"""
import sys
from pathlib import Path

SEED, NODE = 7, 2


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    from bits import Bits
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    g, i = next((g, i) for g in ns["T_of"] if sim.gtype.get(g) == "row" for i in ns["chunks"][g]
                if ns["mine"][g].has(i))
    T = ns["type_of_group"](g)
    p1, p3 = sorted(nd.peers)[:2]
    for p in (p1, p3):                                      # each asker's holding names the cell
        ns["peer_has"][p][g].bits = ns["peer_has"][p][g].bits | Bits(1 << i)
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def claimed(p, a):
        before = nd.refused[(T.id, "claimed")]
        ns["on_want"](p, [a])
        return nd.refused[(T.id, "claimed")] - before

    line(f"a plain ask from peer {p1} of a cell its holding names (the control): counted claimed",
         claimed(p1, Wm.WantIndex(g, i)), 1)
    line(f"a marked probe from peer {p3} of that cell: counted claimed",
         claimed(p3, Wm.FlaggedWant(g, i, False, 0, probe=True)), 0)
    line(f"a second marked probe from peer {p3}, a plain ask by the cap (the control): counted claimed",
         claimed(p3, Wm.FlaggedWant(g, i, False, 0, probe=True)), 1)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
