#!/usr/bin/env python3
"""A known answer for §4.2's ties: a peer that was only asked about has no tie, and an installation lifts no park of its.

    python3 tie_read_known.py

`tied` holds, per block root, connection and group, the indices of the copies that wait for that root. An entry
is there once a copy tied its sender (`tie`), and `on_block_installed` goes by the entries it finds: for each
peer and group under the installing root, the peer's park for the group lifts and its indices are offers again.
`tied_to_root` only asks whether a peer is tied. If asking left an entry behind, empty, the installation would
lift the park of a peer that never sent a copy.

The check, on one node after a small run, for the run's own block and group: peer 1 is tied for index 3 and
peer 3 is not; both are parked for the group; `tied_to_root` is asked about peer 3, as §6.1's retry asks about
every announcer; then the block installs. Peer 1's park must lift (the control: the installation does lift
parks), and peer 3's must stay.
"""
import sys
from pathlib import Path

SEED, NODE, TIED, ASKED = 7, 2, 1, 3


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])    # the run's one payload, to its end
    ns = sim.nodes[NODE].ns
    (root, block), = sim.blocks.items()
    g = ns["bid_group"](root)
    ns["tied"][root][TIED][g].set(3)
    until = ns["now"] + 60
    ns["park"][TIED][g] = ns["park"][ASKED][g] = until
    asked = ns["tied_to_root"](ASKED, Wm.WantIndex(g, 3))
    under = sorted(ns["tied"][root].keys())
    ns["on_block_installed"](root)
    lifted, kept = g not in ns["park"][TIED], ns["park"][ASKED].get(g) == until
    print(f"peer {ASKED}, asked about: tied_to_root says {asked}; the peers under the root after the question: {under}"
          f"{'' if under == [TIED] else '  <-- the question left an entry'}")
    print(f"the control, peer {TIED}, tied for index 3: its park {'lifted' if lifted else 'NOT lifted  <-- FAIL'} at the installation")
    print(f"peer {ASKED}, not tied: its park {'stays' if kept else 'lifted  <-- FAIL'}")
    ok = asked is False and under == [TIED] and lifted and kept
    print("ok" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
