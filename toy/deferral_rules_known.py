#!/usr/bin/env python3
"""Known answers for the rules of §4.2's deferral that no honest cell reaches: they need a peer over its limit
of unknown groups, a block that never installs or an index its group does not have.

    python3 deferral_rules_known.py

On one node after a small run (one payload, its group of N = 2 complete there), with states made by hand:

- **A copy from a peer over its limit of unknown groups is ignored** (§8.2: "the peer's further unknown groups
  are ignored"). `defer` keeps nothing of it: no copy, no reservation, no tie. A peer within its limit, the
  control, has its copy kept and is tied. (The toy admits every group, so here `admitted` is replaced: peer 1
  is over its limit, peer 3 is not.) The copies name a root that has not installed.
"""
import copy as C
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3
ROOT = bytes([0x66]) * 32                                   # a root that never installs here


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED),
              "--late-block", "0,400,2"])                   # no late node; a store of two copies per peer
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])    # the run's one payload, to its end
    nd = sim.nodes[NODE]
    ns = nd.ns
    (root, block), = sim.blocks.items()
    g = ns["bid_group"](root)
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def waiting_copy(i, root_=ROOT):                        # a copy of chunk i of the run's group, naming another root
        f = C.copy(ns["chunks"][g][i])
        f.beacon_block_root = root_
        return f

    def held(p, root_=ROOT):                                # what waits for the root from p: copies kept,
        kept = [f.index for q, f in ns["pending"].get(root_, []) if q == p]   #   its reservations, its ties
        ties = sorted(ns["tied"][root_][p][g]) if p in ns["tied"][root_] else []
        return kept, nd.reserved[p], ties

    # rule 1: a copy over the sender's limit of unknown groups is ignored
    ns["admitted"] = lambda p, f: p != P
    ns["defer"](P, waiting_copy(0))
    ns["defer"](Q, waiting_copy(0))
    line("rule 1: peer 1, over its limit: copies kept, reservations, ties", held(P), ([], 0, []))
    line("rule 1: peer 3, within it (the control): copies kept, reservations, ties", held(Q), ([0], 1, [0]))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
