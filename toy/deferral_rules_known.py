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
  peer 1's again (the control); index N is not.
- **What waits for a root that never installs goes when its slot leaves the live window or its group expires**
  (§8.1; `drop_stale_waits`, which `on_heartbeat` runs: the check goes through it). For a root that never
  installs: peer 1's kept copy names a slot that then leaves the window, a second copy of peer 1's names the
  run's slot (the ties keep the first copy's), and peer 1 also offers its index; peer 3's kept copy names the
  run's slot (the control); peer 4 is tied for another group, which then expires. (The toy's slots never leave the
  window and its groups never expire, so here `live` and `expired` are replaced.) After the sweep, peer 1's
  copy, its id, its reservation, its tie and its slot are gone, and so is its offer of the index (`drop_tie`);
  peer 4's tie and slot are gone; peer 3's copy, tie and slot stay.
- **When the group's count becomes known, what named an index beyond it goes** (`drop_beyond`, called by
  `on_validated` when the group's first valid chunk opens it). With the count not known, peer 3 offers index N
  (by an IHAVE id and by index), an ask of it is made and one queued to peer 3 with its promise, and peer 5 is
  tied for it under a root that never installs. Then a valid chunk of the group arrives: none of these names
  index N any more, and peer 3's offer of index 1 stays (the control).
- **Level 1 rejects a copy whose slot is not its block's** (§1: a group's slot is the slot of every block whose
  bid commits it, which every chunk names and level 1 checks). A chunk the node accepted passes again (the
  control); the same chunk naming an older slot is rejected, so that a node neither forwards it nor takes its
  slot for its sender's ties.
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
    ns["tie"](P, type("Copy", (), {"group": g, "index": 1, "beacon_block_root": ROOT3, "slot": block.slot})())
    ns["add_offer"](Wm.WantIndex(g, 0), P)                  #   a second copy naming the run's slot (the first's
                                                            #   slot is the ties'), and its offer of index 0
    ns["defer"](Q, waiting_copy(1, ROOT3))                  # peer 3: a copy of the run's slot (the control)
    ns["tie"](R, type("Copy", (), {"group": GX, "index": 0, "beacon_block_root": ROOT3, "slot": block.slot})())
    ids = lambda: sorted(f.index for f in (stale, ) if ns["message_id"](f) in ns["pending_ids"])
    line("rule 3, before: peer 1's copy, reservation and ties; their slot, its first copy's",
         (held(P, ROOT3), ns["tie_slot"].get((ROOT3, P))), (([0], 1, [0, 1]), OLD))
    line("rule 3, before: peer 3's; peer 4 tied for the other group", (held(Q, ROOT3), R in ns["tied"][ROOT3]),
         (([1], 1, [1]), True))
    line("rule 3, before: peer 1 an announcer of index 0, and its copy's id waiting",
         (ns["offered"][P][g].has(0), P in ns["offers"][Wm.WantIndex(g, 0)], ids()), (True, True, [0]))
    ns["live"] = lambda s: s != OLD                         # the slot leaves the live window,
    ns["expired"] = lambda x: x == GX                       #   and the other group expires
    ns["on_heartbeat"]()                                    # which runs drop_stale_waits
    line("rule 3, after: peer 1's copy, reservation and both ties gone, its id and slot too",
         (held(P, ROOT3), ids(), (ROOT3, P) in ns["tie_slot"]), (([], 0, []), [], False))
    line("rule 3, after: peer 1 no longer an announcer of index 0 (drop_tie)",
         (ns["offered"][P][g].has(0), P in ns["offers"][Wm.WantIndex(g, 0)]), (False, False))
    line("rule 3, after: peer 3's copy, reservation and tie kept (the control), and its slot",
         (held(Q, ROOT3), ns["tie_slot"].get((ROOT3, Q))), (([1], 1, [1]), block.slot))
    line("rule 3, after: peer 4's tie to the expired group gone, and its slot",
         (R in ns["tied"][ROOT3], (ROOT3, R) in ns["tie_slot"]), (False, False))

    # when the group's count becomes known, what named an index beyond it goes (drop_beyond, from on_validated)
    ROOT4, U = bytes([0x88]) * 32, 5                        # a root that never installs; peer 5
    d = ns["desc"].pop(g)                                   # the group's count not known yet
    beyond, inside = Wm.WantIndex(g, n), Wm.WantIndex(g, 1)
    ns["on_ihave"](Q, Wm._IHave([g + n.to_bytes(4, "little") + bytes([0x44]) * 20]))   # an id of index N: an offer
    ns["tried"][beyond][Q] = ns["now"]; ns["asked_at"][beyond] = ns["now"]  # an ask of it made (the group is past
                                                                            #   its stop-pull here, so by hand)
    ns["add_offer"](beyond, Q); ns["add_offer"](inside, Q)  # Q offers index N, and index 1 (the control)
    ns["queue"][Q].normal.append(Wm.Entry(control=Wm.IWANT([beyond])))      # an ask of index N queued to Q,
    ns["promises"][(beyond, Q)] = ns["now"] + 1                             #   and its promise
    ns["tie"](U, type("Copy", (), {"group": g, "index": n, "beacon_block_root": ROOT4, "slot": block.slot})())
    named = lambda: {"offered": ns["offered"][Q][g].has(n),
                     "listed": any(Q in o and ns["group"](a) == g and ns["index"](a) == n for a, o in ns["offers"].items()),
                     "tried or asked": any(ns["index"](a) == n and ns["group"](a) == g
                                           for t_ in ("tried", "asked_at") for a in ns[t_]),
                     "queued": any(ns["index"](b) == n for e in ns["queue"][Q].normal for c in e.iwants() for b in c.ids),
                     "promised": any(ns["index"](a) == n and ns["group"](a) == g for (a, q) in ns["promises"]),
                     "tied": n in set(ns["tied"][ROOT4][U][g])}
    line(f"the count unknown: index {n} offered, listed, tried or asked, queued, promised and tied",
         sorted(k for k, v in named().items() if v), sorted(named()))
    first = C.copy(ns["chunks"][g][0])                      # the group's first valid chunk at this node, again
    ns["mark_seen"] = lambda mid: None
    ns["on_validated"](P, first, "ACCEPT")                  # opens the group: its count is known now
    line(f"the count known ({ns['N'](ns['desc'][g])}): what still names index {n}", sorted(k for k, v in named().items() if v), [])
    line("the control: Q's offer of index 1 kept", (ns["offered"][Q][g].has(1), Q in ns["offers"][inside]), (True, True))

    # level 1: a copy whose slot is not its block's is rejected
    good = ns["chunks"][g][0]                               # a chunk the node accepted, of the installed block
    wrong = C.copy(good)
    wrong.slot = block.slot - 1                             # the same chunk, naming an older slot
    line("level 1: the chunk as it came, and the same naming another slot",
         (ns["validate_chunk"](good), ns["validate_chunk"](wrong)), ("ACCEPT", "REJECT"))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
