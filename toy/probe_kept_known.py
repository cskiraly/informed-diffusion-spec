#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.6's kept probe, against a second marked ask of the same group.

    python3 probe_kept_known.py

A claimant still decoding keeps the first marked ask per asker and group of a claimed index it has not stored
(`probe_waiting`), and answers it, with its one exemption, when the cell is stored. While it is kept, the same
asker's marked ask of another index of the group is a plain ask (`probe_of_claim`): it takes no exemption, so
the kept probe is answered when its cell is stored. An honest member sends one probe per group; only a faulty
asker sends a second.

On one node of a small rows run (protocol-v2.md, one block, run to its end), made by hand, as the claimant, on
a row it holds whole: cell i claimed and not stored (still decoding), cell j stored. Then:
- peer p sends a marked ask of i (kept), then a marked ask of j;
- peer r sends a standing ask of i, then a marked ask of i (kept, in place of its standing ask), then a marked
  ask of j: a faulty asker's sequence;
- peer c, the control, sends one marked ask of i.

At once, j goes to p and to r as a plain answer, without the exemption; then cell i is stored, and i goes to
each of p, r and c with the exemption, once.
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
    i, j = sorted(ns["chunks"][g])[:2]
    fi, fj = ns["chunks"][g][i], ns["chunks"][g][j]
    p, r, c, s = sorted(nd.peers)[:4]                      # s brings cell i
    ns["state"][g] = "DECODING"                             # still decoding: i claimed, not stored
    ns["chunks"][g].pop(i, None)
    ns["known_id"][g].pop(i, None)
    ns["received"][g].clear(i); ns["rebuilt"][g].clear(i)
    for x in (p, r, c):
        ns["peer_has"][x].pop(g, None)                      # the askers claim nothing of the row
        ns["queue"][x].normal[:] = []; ns["queue"][x].urgent[:] = []
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def queued(x, f):                                       # solicited answers of f in x's queue
        qx = ns["queue"][x]
        return sum(1 for e in list(qx.urgent) + list(qx.normal) if e.chunk is f and e.solicited)

    def ask(x, k, standing=False, probe=False):
        return ns["on_want"](x, [Wm.FlaggedWant(g, k, standing, 0, probe=probe)])

    got_p = ask(p, i, probe=True) + ask(p, j, probe=True)
    got_r = ask(r, i, standing=True) + ask(r, i, probe=True) + ask(r, j, probe=True)
    got_c = ask(c, i, probe=True)
    line("kept probes", dict(ns["probe_waiting"][g]), {p: i, r: i, c: i})
    line(f"at once: j answered to peers {p} and {r} (in the answers returned), and peer {c} answered nothing",
         ([f is fj for f in got_p], [f is fj for f in got_r], got_c), ([True], [True], []))
    line(f"at once: the exemption taken by peers {p}, {r} (j is a plain ask while i is kept)",
         [bool(ns["probe_served"][x][g]) or ns["probe_answers"][x][fj.group].has(fj.index) for x in (p, r)], [False, False])
    ns["fill"](g, i, fi, s)                                 # cell i is stored
    line(f"after i is stored: i answered to peers {p}, {r}, {c} (solicited, in their queues)",
         [queued(x, fi) for x in (p, r, c)], [1, 1, 1])
    line(f"after i is stored: the exemption taken, on i, by peers {p}, {r}, {c}",
         [(bool(ns["probe_served"][x][g]), ns["probe_answers"][x][fi.group].has(fi.index)) for x in (p, r, c)],
         [(True, True)] * 3)
    line("after i is stored: kept probes left", dict(ns["probe_waiting"][g]), {})
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
