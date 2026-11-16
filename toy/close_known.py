#!/usr/bin/env python3
"""Known answers for a connection's close under protocol-v2.md (`Node.drop_peer`, which `--churn` runs): what
goes, by §3's lifetimes, which are `protocol.md` §8.1's, and what the probe does when its claimant leaves (R5,
`claims_close`).

    python3 close_known.py

On one node of a small network (protocol-v2.md, one payload, run to its end), with states made by hand:

- **What an announcer leaves goes with its connection.** Peer 1 is made to hold what an announcer holds:
  - an offer of three chunks, so a place in three ordered lists (`listed` 3) and three bits in `offered`;
  - a try of one of them, a promise for it, and a place in the last resort's count (`asked_parked`);
  - a park for the group;
  - a tie to a root not installed, with its slot, and a kept deferred copy with its reservation.

  After the close, `listed`, the lists, `offered`, the try, the promise, the last resort's count, the tie and
  its slot are gone. Two controls stay:
  - the park, kept across reconnections as scores are;
  - the kept copy and its reservation, keyed by block root.
- **A claimant that leaves is not judged.** Peers 1 and 3 claim the group, and peer 1 is the probed claimant,
  its probe written and not yet judged. After peer 1's close:
  - its claim is gone and peer 3's stays, so a probe draws among connected claimants;
  - the probe has no verdict (`probe_ok` None), and the decode duty is re-armed at its own time, here the time
    of the deferral, so at once;
  - that reconsideration penalises nobody.

  The control: the same deferral with peer 3 probed and connected, judged when the duty fires, penalises
  peer 3.
"""
import copy as C
import sys
from pathlib import Path

P, Q, NODE = 1, 3, 2
G = bytes([0x55]) * 32
ROOT = bytes([0x66]) * 32


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7",
              "--late-block", "0,400,2", "--doc", "v2"])          # a store of two copies per peer
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    (root, block), = sim.blocks.items()
    g = ns["bid_group"](root)
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    # what an announcer leaves goes with its connection
    asks = [Wm.WantIndex(G, i) for i in range(3)]
    for a in asks:
        ns["add_offer"](a, P)
    ns["tried"][asks[0]][P] = ns["now"]
    ns["promises"][(asks[0], P)] = ns["now"] + 1
    ns["asked_parked"][(G, 0)].add(P)
    ns["park"][P][G] = ns["now"] + 60
    f = C.copy(ns["chunks"][g][0])
    f.beacon_block_root = ROOT
    ns["defer"](P, f)                                       # kept (a store of two per peer), and tied

    def state():
        return {"listed": ns["listed"](P),
                "lists": sum(P in ns["offers"][a] for a in asks),
                "offered": sum(len(list(b)) for b in ns["offered"][P].values()) if P in ns["offered"] else 0,
                "tried": sum(P in ns["tried"].get(a, {}) for a in asks),
                "promises": sum(k[1] == P for k in ns["promises"]),
                "last resort": sum(P in s for s in ns["asked_parked"].values()),
                "tied": sum(P in t for t in ns["tied"].values()),
                "tie_slot": sum(k[1] == P for k in ns["tie_slot"]),
                "park": sorted(k.hex()[:6] for k in ns["park"].get(P, {})),
                "kept copies, reservations": (sum(q == P for v in ns["pending"].values() for q, _ in v),
                                              nd.reserved[P])}
    gone = ("listed", "lists", "offered", "tried", "promises", "last resort", "tied", "tie_slot")
    before = state()
    line("before the close", before, {"listed": 3, "lists": 3, "offered": 3, "tried": 1, "promises": 1,
                                      "last resort": 1, "tied": 1, "tie_slot": 1, "park": ["555555"],
                                      "kept copies, reservations": (1, 1)})

    # a claimant that leaves is not judged (set up before the close)
    ns["claims"][g] |= {P, Q}
    ns["state"][g] = "COMPLETE"
    ns["deferred"][g], ns["probed"][g], ns["probe"][g] = True, P, 0
    if "probe_sent" in ns:                                  # its WANT written (protocol-v2.md §4.6, since 2026-11-16)
        ns["probe_sent"].add(g)
    ns["probe_ok"].pop(g, None)
    later = ns["now"] + 1
    ns["reconsider_at"][g] = later                          # the duty armed for later, as defer_on_claim arms it
    if "duty_at" in ns:                                     # the duty's own time: due at the deferral, as when
        ns["duty_at"][g] = ns["now"]                        #   reconsider defers it (protocol-v2.md §4.6)

    nd.drop_peer(P)
    after = state()
    line("after the close, what goes with the connection", {k: after[k] for k in gone}, {k: 0 for k in gone})
    line("after the close, the park (kept across reconnections)", after["park"], ["555555"])
    line("after the close, the kept copy and its reservation (by block root)", after["kept copies, reservations"],
         (1, 1))
    line("the probe: peer 1's claim, and peer 3's (the run's own claimants stay too)",
         (P in ns["claims"][g], Q in ns["claims"][g]), (False, True))
    line("the probe: its verdict, and the duty re-armed at its own time, at once",
         (g in ns["probe_ok"], ns["probe_ok"].get(g), ns["reconsider_at"].get(g)), (True, None, ns["now"]))
    pen = nd.penalties
    ns["reconsider"](g, ns["reconsider_at"].get(g))         # the duty fires, when it is armed
    line("the probe: penalties when the duty fires", nd.penalties - pen, 0)

    # the control: a connected claimant, probed and not answering, is judged when the duty fires
    ns["state"][g] = "COMPLETE"
    ns["deferred"][g], ns["probed"][g], ns["probe"][g] = True, Q, 0
    if "probe_sent" in ns:
        ns["probe_sent"].add(g)
    ns["probe_ok"].pop(g, None)
    ns["reconsider_at"][g] = later
    pen = nd.penalties
    ns["reconsider"](g, later)
    line("the control: peer 3 probed and connected, judged: its verdict, penalties",
         (ns["probe_ok"].get(g), nd.penalties - pen), (False, 1))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
