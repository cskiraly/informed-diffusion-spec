#!/usr/bin/env python3
"""Known answers for the rules of §4.2's deferral that no honest cell reaches: they need a peer over its limit
of unknown groups, a block that never installs or an index its group does not have.

    python3 deferral_rules_known.py

On one node after a small run (one payload, its group of N = 2 complete there), with states made by hand:

- **A copy from a peer over its limit of unknown groups is ignored** (§8.2: "the peer's further unknown groups
  are ignored"). `defer` keeps nothing of it: no copy, no reservation, no tie. A peer within its limit, the
  control, has its copy kept and is tied. (The toy admits every group, so here `admitted` is replaced: peer 1
  is over its limit, peer 3 is not.) The copies name a root that has not installed.
- **At installation, a tied index that the group, known by then, does not have is dropped, that index alone**
  (§8.2: no index at or beyond N once the descriptor is known). Peer 1's copies of indices 1 and N tie it
  while the group's descriptor is not known yet (as when every copy was refused); the descriptor is then known
  (as when a kept copy opens the group), and the block installs. Index 1, which the node lacks, is an offer of
  peer 1's again (the control); index N is not, so the node never asks for a chunk that cannot exist.
- **What waits for a root that never installs goes when its slot leaves the live window or its group expires**
  (§8.1; `drop_stale_waits`, at each heartbeat). For a root that never installs: peer 1's kept copy names a
  slot that then leaves the window, and peer 1 also offers its index; peer 3's kept copy names the run's slot
  (the control); peer 4 is tied for another group, which then expires. (The toy's slots never leave the
  window and its groups never expire, so here `live` and `expired` are replaced.) After the sweep, peer 1's
  copy, its id, its reservation, its tie and its slot are gone, and so is its offer of the index (`drop_tie`);
  peer 4's tie and slot are gone; peer 3's copy, tie and slot stay.
"""
import copy as C
import sys
from pathlib import Path

SEED, NODE, P, Q, R = 7, 2, 1, 3, 4
ROOT = bytes([0x66]) * 32                                   # a root that never installs here


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
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
    ns["admitted"] = lambda p, f: True

    # rule 2: at installation, a tied index the group, known by then, does not have is dropped, that index alone
    n = ns["N"](ns["desc"][g])
    d = ns["desc"].pop(g)                                   # the group's descriptor not known yet when p's copies tie
    ns["mine"][g].clear(1)                                  # the node lacks chunk 1
    ns["tie"](P, waiting_copy(1, root))                     # chunk 1, and an index the group has not
    ns["tie"](P, type("Copy", (), {"group": g, "index": n, "beacon_block_root": root, "slot": block.slot})())
    line(f"rule 2: peer 1 tied for indices 1 and {n} while the group's N is unknown", sorted(ns["tied"][root][P][g]), [1, n])
    ns["desc"][g] = d                                       # a copy that waited opens the group: N = 2 now
    ns["on_block_installed"](root)
    offers = lambda i: (ns["offered"][P][g].has(i), P in ns["offers"][Wm.WantIndex(g, i)])
    line("rule 2: after the installation, peer 1 an announcer of index 1 (the control)", offers(1), (True, True))
    line(f"rule 2: after the installation, peer 1 an announcer of index {n}, which the group has not", offers(n),
         (False, False))

    for q, f in ns["pending"].pop(ROOT, []):                # what rule 1's lines left waiting for ROOT, cleared
        ns["pending_ids"].discard(ns["message_id"](f)); ns["release"](q, f)       #   by hand
    ns["tied"].pop(ROOT, None); ns["tie_slot"].pop((ROOT, Q), None)

    # rule 3: what waits for a root that never installs goes when its slot leaves the live window or its group expires
    ROOT3, OLD, GX = bytes([0x77]) * 32, block.slot - 1, bytes([0xAB]) * 32
    stale = waiting_copy(0, ROOT3)
    stale.slot = OLD                                        # peer 1: a copy of a slot that is to leave the window,
    ns["defer"](P, stale)
    ns["add_offer"](Wm.WantIndex(g, 0), P)                  #   and its offer of that index
    ns["defer"](Q, waiting_copy(1, ROOT3))                  # peer 3: a copy of the run's slot (the control)
    ns["tie"](R, type("Copy", (), {"group": GX, "index": 0, "beacon_block_root": ROOT3, "slot": block.slot})())
    ids = lambda: sorted(f.index for f in (stale, ) if ns["message_id"](f) in ns["pending_ids"])
    line("rule 3, before: peer 1's copy, reservation and tie; its slot", (held(P, ROOT3), ns["tie_slot"].get((ROOT3, P))),
         (([0], 1, [0]), OLD))
    line("rule 3, before: peer 3's; peer 4 tied for the other group", (held(Q, ROOT3), R in ns["tied"][ROOT3]),
         (([1], 1, [1]), True))
    line("rule 3, before: peer 1 an announcer of index 0, and its copy's id waiting",
         (ns["offered"][P][g].has(0), P in ns["offers"][Wm.WantIndex(g, 0)], ids()), (True, True, [0]))
    ns["live"] = lambda s: s != OLD                         # the slot leaves the live window,
    ns["expired"] = lambda x: x == GX                       #   and the other group expires
    ns["drop_stale_waits"]()
    line("rule 3, after: peer 1's copy, reservation and tie gone, its id and slot too",
         (held(P, ROOT3), ids(), (ROOT3, P) in ns["tie_slot"]), (([], 0, []), [], False))
    line("rule 3, after: peer 1 no longer an announcer of index 0 (drop_tie)",
         (ns["offered"][P][g].has(0), P in ns["offers"][Wm.WantIndex(g, 0)]), (False, False))
    line("rule 3, after: peer 3's copy, reservation and tie kept (the control), and its slot",
         (held(Q, ROOT3), ns["tie_slot"].get((ROOT3, Q))), (([1], 1, [1]), block.slot))
    line("rule 3, after: peer 4's tie to the expired group gone, and its slot",
         (R in ns["tied"][ROOT3], (ROOT3, R) in ns["tie_slot"]), (False, False))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
