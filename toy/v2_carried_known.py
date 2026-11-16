#!/usr/bin/env python3
"""Known answers for v0.10's rules where protocol-v2.md has functions of its own, for cells and offers. The
payload's (`defer`'s limit of unknown groups, `drop_stale_waits` from `on_heartbeat`, `drop_beyond` when a
group opens) are `deferral_rules_known.py --doc v2`.

    python3 v2_carried_known.py

On one node of a small rows run (protocol-v2.md, one block, run to its end), with states made by hand:

- **An offer's bitmap is held to a HAVE's limits** (§4.3 `on_offer`, as `protocol.md` §4.4's IHAVE bitmap): an
  offer naming an index at or beyond its group's known count is ignored and counts against the sender. An offer
  of an index the group has and the node lacks, the control, is kept, with no penalty.
- **At the cell header, a tied index the group, known by then, does not have is dropped, that index alone**
  (§4.2 `on_header_validated`, as `protocol.md`'s `on_block_installed`). Peer 1 is tied for indices 0 and N of a
  column while the column's count is not known yet; the count is then known, and the header validated. Index 0,
  which the node lacks, is an offer of peer 1's again (the control); index N is not.
- **A sender with nothing left tied under the root loses its tie's slot** (`tie_slot`, `protocol.md` §4.2 and
  §8.1). Peer 4 is tied only for that column: after the header, it is no longer tied under the root and its slot
  is gone. Peer 1 is also tied for a group of the root that is not a cell group: it stays tied, with its slot
  (the control).
- **A cell's level 1 rejects a copy whose slot is not its header's** (§1's table, as `protocol.md` §3's
  `validate_chunk` for the payload). A cell the node accepted passes again, for its column and for its row (the
  control); the same cell naming an older slot is rejected for both.

The toy's cells carry their header, so `on_header_validated` never runs in a recorded cell; here it is called
by hand, with `cell_groups` (§3's helper) given from the run's own groups.
"""
import copy as C
import sys
from pathlib import Path

SEED, NODE, P, R = 7, 2, 1, 4


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    from bits import bitmap
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])    # the run's one block, to its end
    nd = sim.nodes[NODE]
    ns = nd.ns
    (root, block), = sim.blocks.items()
    groups = [g for g, h in sim.ghdr.items() if h.block == root]
    ns["cell_groups"] = lambda r: [g for g, h in sim.ghdr.items() if h.block == r]
    col = next(g for g in groups if sim.gtype[g] == "column" and g in ns["T_of"] and ns["chunks"][g].get(0))
    row = next(g for g in groups if sim.gtype[g] == "row" and g in ns["T_of"] and ns["chunks"][g])
    n = ns["N"](ns["desc"][col])
    Ask = ns["Ask"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def copy_of(g, i, slot=block.slot):
        return type("Copy", (), {"group": g, "index": i, "beacon_block_root": root, "slot": slot})()

    def announcer(p, g, i):
        return ns["offered"][p][g].has(i), p in ns["offers"][Ask(g, i)]

    # an offer's bitmap is held to a HAVE's limits
    ns["mine"][col].clear(0)                                # the node lacks cell 0 of the column
    before = nd.penalties
    asks = ns["on_offer"](P, ns["Have"](group=col, bits=bitmap({n}), offer=True, claim_all=False, complete=False))
    line(f"offer: index {n} of a column known to have {n}: asks, an announcer of it, penalties",
         (asks, announcer(P, col, n), nd.penalties - before), ([], (False, False), 1))
    before = nd.penalties
    ns["on_offer"](P, ns["Have"](group=col, bits=bitmap({0}), offer=True, claim_all=False, complete=False))
    line("offer, the control: index 0 of that column, which the node lacks: an announcer of it, penalties",
         (announcer(P, col, 0), nd.penalties - before), ((True, True), 0))
    ns["drop_offer"](col, 0, P)                             # back as it was, for the ties below

    # at the cell header: a tied index the group, known by then, does not have is dropped; a sender with nothing
    # left tied under the root loses its tie's slot
    GX = bytes([0xAB]) * 32                                 # a group of the root that is not a cell group
    d = ns["desc"].pop(col)                                 # the column's count not known yet when the copies tie
    ns["tie"](P, copy_of(col, 0)); ns["tie"](P, copy_of(col, n)); ns["tie"](P, copy_of(GX, 0))
    ns["tie"](R, copy_of(col, 0))
    line(f"header, before: peer 1 tied for the column's indices 0 and {n}, and for the other group; peer 4 for 0",
         (sorted(ns["tied"][root][P][col]), sorted(ns["tied"][root][P][GX]), sorted(ns["tied"][root][R][col])),
         ([0, n], [0], [0]))
    ns["desc"][col] = d                                     # the column's count known now
    ns["on_header_validated"](root)
    line("header, after: peer 1 an announcer of index 0 (the control)", announcer(P, col, 0), (True, True))
    line(f"header, after: peer 1 an announcer of index {n}, which the column has not", announcer(P, col, n),
         (False, False))
    line("header, after: peer 1 still tied for the other group, with its slot (the control)",
         (P in ns["tied"].get(root, {}) and GX in ns["tied"][root][P], ns["tie_slot"].get((root, P))),
         (True, block.slot))
    line("header, after: peer 4 tied under the root, and its slot",
         (R in ns["tied"].get(root, {}), (root, R) in ns["tie_slot"]), (False, False))

    # a cell's level 1: a copy whose slot is not its header's is rejected
    for g, what in ((col, "column"), (row, "row")):
        T = ns["type_of_group"](g)
        good = next(iter(ns["chunks"][g].values()))
        wrong = C.copy(good)
        wrong.slot = block.slot - 1
        line(f"level 1, {what}: the cell as it came, and the same naming another slot",
             (T.verify(good, T.header_of(good)), T.verify(wrong, T.header_of(wrong))), ("ACCEPT", "REJECT"))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
