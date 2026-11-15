#!/usr/bin/env python3
"""A known answer for the gate on what a node knows of a block before it installs (`--late-block`).

    python3 bid_gate_known.py

A late node has not installed the block, so it knows neither the block nor the group its bid commits:
`installed_block` gives nothing and `authenticable` is false for the group. `bid_group` reads the group from the
block, so it is allowed for an installed block alone, and refuses a block that waits. The document's callers ask
it only after the gate (`on_block_installed`, `authenticable`); a caller that did not would fail here instead of
learning the group early.

On one late node of a small run, between the publish and the installation: `authenticable` is false,
`bid_group` refuses, and after the installation both answer (the control).
"""
import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7",
              "--late-block", "50,400"])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + 0.1)        # 100 ms in: the block waits
    late = min(cfg["late_nodes"])
    nd = sim.nodes[late]
    (root, block), = sim.blocks.items()
    on_time = min(set(sim.nodes) - set(cfg["late_nodes"]))
    g = sim.nodes[on_time].ns["bid_group"](root)                               # the group, as a node that has it reads it
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"node {late}, {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    try:
        nd.ns["bid_group"](root)
        refused = False
    except AssertionError:
        refused = True
    line("the block waits; bid_group refuses", refused, True)
    line("the block waits; authenticable of its group", nd.ns["authenticable"](g), False)
    sim.run(cfg["first"] + cfg["gap"])                                         # past the installation
    line("the block installed (the control); it waits", root in nd.blocks_waiting, False)
    line("the block installed; bid_group answers the group", nd.ns["bid_group"](root) == g, True)
    line("the block installed; authenticable of its group", nd.ns["authenticable"](g), True)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
