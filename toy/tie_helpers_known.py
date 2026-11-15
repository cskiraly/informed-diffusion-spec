#!/usr/bin/env python3
"""Known answers for three functions of the document that §4.2's deferral calls: `tie_room`, `close_promises`
with `of`, and `drop_offer` (§4.2, §6.1).

    python3 tie_helpers_known.py

A cell of check.py tells only that something changed, and `tie_room` and `drop_offer` run in a cell only where a
block installs late. Here each is called on a state made by hand, on one node after a small run, and every table it may touch is read before and
after. Peers 1 and 3; a group G no block commits; chunk 3 named in both forms, by index and by a full id.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3
G, ROOT, ROOT2 = bytes([0x55]) * 32, bytes([0x66]) * 32, bytes([0x77]) * 32


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)])
    ns = got["sim"].nodes[NODE].ns
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    by_index, by_id = Wm.WantIndex(G, 3), G + (3).to_bytes(4, "little") + bytes([0x88]) * 20
    other = Wm.WantIndex(G, 4)
    copy = lambda i, root=ROOT, g=G: type("Copy", (), {"group": g, "index": i, "beacon_block_root": root})()

    # tie_room: the index in range; a root and group tied for the peer already, or room for another
    ns["MAX_PENDING_GROUPS"] = 1
    line("tie_room, nothing tied, a limit of 1", ns["tie_room"](P, copy(3)), True)
    line("tie_room, an index no group has", ns["tie_room"](P, copy(ns["MAX_PLAIN_CHUNKS"])), False)
    ns["tied"][ROOT][P][G].set(3)
    line("tie_room, the same root and group again", ns["tie_room"](P, copy(4)), True)
    line("tie_room, another root for the same peer, at the limit", ns["tie_room"](P, copy(3, ROOT2)), False)
    line("tie_room, another peer, which has none", ns["tie_room"](Q, copy(3, ROOT2)), True)
    line("tie_room's questions left no entry: the peers under the two roots",
         (sorted(ns["tied"][ROOT].keys()), sorted(ns["tied"][ROOT2].keys())), ([P], []))

    # the state for the other two: offers, asks and promises of chunk 3 in both forms, and of chunk 4
    for a in (by_index, by_id, other):
        for p in (P, Q):
            ns["add_offer"](a, p)
            ns["promises"][(a, p)] = 1.0
    ns["offers"][by_id].remove(Q)                           # P alone in one list
    for p in (P, Q):
        ns["queue"][p].normal.append(Wm.Entry(control=Wm.IWANT([by_index, other])))
        ns["queue"][p].normal.append(Wm.Entry(control=Wm.IWANT([by_id])))

    def state():
        return {"promises": sorted((ns["index"](a), isinstance(a, bytes), p) for (a, p) in ns["promises"]),
                "lists": sorted((ns["index"](a), isinstance(a, bytes), list(o)) for a, o in ns["offers"].items()
                                if ns["group"](a) == G),
                "offered": {p: sorted(ns["offered"][p][G]) for p in (P, Q)},
                "queued": {p: [[ns["index"](b) for c in e.iwants() for b in c.ids] for e in ns["queue"][p].normal]
                           for p in (P, Q)},
                "listed": {p: ns["listed"](p) for p in (P, Q)}}

    before = state()
    ns["close_promises"](G, 3, of=P)
    after = state()
    want = dict(before, promises=[x for x in before["promises"] if not (x[0] == 3 and x[2] == P)])
    line("close_promises of one peer: its two promises for the chunk go, in both forms, and nothing else changes",
         after == want and len(before["promises"]) - len(after["promises"]) == 2, True)

    before = state()
    ns["drop_offer"](G, 3, P)
    after = state()
    line("drop_offer: the peer's bit of the chunk", (before["offered"][P], after["offered"][P]), ([3, 4], [4]))
    line("drop_offer: the other peer's bits", after["offered"][Q], before["offered"][Q])
    line("drop_offer: the chunk's lists, by index and by id (the id's had the peer alone, and is gone)",
         [x for x in after["lists"] if x[0] == 3], [(3, False, [Q])])
    line("drop_offer: the other chunk's list", [x for x in after["lists"] if x[0] == 4], [(4, False, [P, Q])])
    line("drop_offer: the lists each peer is in, before and after", (before["listed"], after["listed"]),
         ({P: 3, Q: 2}, {P: 1, Q: 2}))
    line("drop_offer: what is queued to the peer (the entry of the id alone is gone)", after["queued"][P], [[4]])
    line("drop_offer: what is queued to the other peer", after["queued"][Q], before["queued"][Q])
    line("drop_offer: the promises left", after["promises"], [x for x in before["promises"] if not (x[0] == 3 and x[2] == P)])

    before = state()
    ns["close_promises"](G, 3)
    after = state()
    line("close_promises of the chunk: its promises, lists and bits go for every peer, the other chunk's stay",
         (after["promises"], after["lists"], after["offered"]),
         ([x for x in before["promises"] if x[0] != 3], [x for x in before["lists"] if x[0] != 3], {P: [4], Q: [4]}))
    line("close_promises of the chunk: the lists each peer is in", after["listed"], {P: 1, Q: 1})
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
