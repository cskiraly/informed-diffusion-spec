#!/usr/bin/env python3
"""Known answers for what §4.2's tie does, from the tie to the installation that releases it.

    python3 tie_release_known.py

The `late-block` cell cannot show these: a late node asks nothing of a group before its block installs, so no
promise of it is open when a copy ties its sender, and no park or last-resort count is there for the installation to
lift. Here they are made by hand, on one node after a small run, for the run's own block and group, with the
node made to lack one chunk (index 1 of N = 2).

- **The tie.** A copy of index 1 from peer 1 ties it: its promise for index 1 closes (it answered, with a copy
  that cannot be checked yet), and `tied_to_root` says it is tied, so the retry does not ask it again.
- **The release.** The installation lifts peer 1's park for the group, clears it from the last-resort count of index 1,
  makes it an offer of index 1 again, and leaves no tie. Peer 3, parked and counted too but not tied, is the
  control: its park and its count stay.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q, I = 7, 2, 1, 3, 1          # the group has N = 2


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
    a = Wm.WantIndex(g, I)
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    ns["mine"][g].clear(I)                                  # the node lacks chunk 1
    until = ns["now"] + 60
    for p in (P, Q):
        ns["promises"][(a, p)] = ns["now"] + 1
        ns["park"][p][g] = until
        ns["asked_parked"][(g, I)].add(p)
    copy = type("Copy", (), {"group": g, "index": I, "beacon_block_root": root, "slot": block.slot})()

    ns["tie"](P, copy)
    line("the tie: peer 1's promise for index 1 is closed, peer 3's is open",
         ((a, P) in ns["promises"], (a, Q) in ns["promises"]), (False, True))
    line("the tie: tied_to_root, peer 1 and peer 3", (ns["tied_to_root"](P, a), ns["tied_to_root"](Q, a)), (True, False))

    ns["on_block_installed"](root)
    line("the release: peer 1's park for the group lifted, peer 3's kept",
         (g in ns["park"][P], ns["park"][Q].get(g) == until), (False, True))
    line("the release: the last-resort count of index 1 holds peer 1, peer 3",
         (P in ns["asked_parked"][(g, I)], Q in ns["asked_parked"][(g, I)]), (False, True))
    line("the release: peer 1 an announcer of index 1 again", ns["offered"][P][g].has(I) and P in ns["offers"][a], True)
    line("the release: ties left under the root, and tied_to_root of peer 1",
         (root in ns["tied"], ns["tied_to_root"](P, a)), (False, False))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
