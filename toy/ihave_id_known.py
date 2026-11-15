#!/usr/bin/env python3
"""A known answer for §4.4's rule on an IHAVE entry that is not a bitmap: it is a chunk's structured id, or it is
ignored.

    python3 ihave_id_known.py

A chunk's id (§2) is 56 bytes: the group's 32, the index as uint32 little-endian, and a 20-byte content id. §4.4's
`valid_id` takes an entry for one if it has that length and names an index its group can have: below
`MAX_PLAIN_CHUNKS`, and below the group's count where its descriptor is known. Any other entry leaves no offer,
no ask and no penalty, and its RPC still counts as one that bears an IHAVE.

The check, on one node of a small network that is built and not run, with one IHAVE from a peer per case: ids
that are not a chunk's, each for one reason; and beside them two that are, which must each leave an offer (the
control: the rule does not ignore everything).
"""
import sys
from pathlib import Path

SEED, NODE, PEER = 7, 2, 1
G, G2 = bytes([0x33]) * 32, bytes([0x34]) * 32      # groups no block commits; G2's descriptor is made known below


def chunk_id(g, i, tail=20):
    return g + i.to_bytes(4, "little") + bytes([0x44]) * tail


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)])
    node = got["sim"].nodes[NODE]
    ns = node.ns
    ns["desc"][G2] = type("Descriptor", (), {"count": 4})()         # a group whose count is known: 4 chunks
    n2 = ns["N"](ns["desc"][G2])
    cap = ns["MAX_PLAIN_CHUNKS"]
    cases = [("20 bytes, an id of the inherited kind", bytes([0x22]) * 20, False),
             ("36 bytes, a group and an index and no content id", chunk_id(G, 5, 0), False),
             ("55 bytes", chunk_id(G, 5, 19), False),
             ("57 bytes", chunk_id(G, 5, 21), False),
             (f"56 bytes, index {cap}, which no group has", chunk_id(G, cap), False),
             ("56 bytes, the largest index 32 bits hold", chunk_id(G, 2 ** 32 - 1), False),
             (f"56 bytes, index {n2} of a group known to have {n2} chunks", chunk_id(G2, n2), False),
             (f"the control: 56 bytes, index {cap - 1}, the last a group can have", chunk_id(G, cap - 1), True),
             (f"the control: 56 bytes, index {n2 - 1} of the group known to have {n2}", chunk_id(G2, n2 - 1), True)]

    def state():
        return (ns["ihave_rpcs"][PEER], sum(len(o) for o in ns["offers"].values()),
                sum(len(list(b)) for groups in ns["offered"].values() for b in groups.values()), node.penalties)

    bad = 0
    for what, entry, valid in cases:
        before = state()
        try:
            asks = ns["on_ihave"](PEER, Wm._IHave([entry]))
        except Exception as e:                       # what the toy did before the rule: it stopped in the loop
            print(f"{what}: on_ihave stopped with {type(e).__name__}: {e}  <-- FAIL")
            bad += 1
            continue
        after = state()
        want = (before[0] + 1, before[1] + valid, before[2] + valid, before[3])
        ok = asks == [] and after == want and ns["valid_id"](entry) == valid
        bad += not ok
        print(f"{what}: valid_id {ns['valid_id'](entry)}; asks {asks}; IHAVE RPCs counted {before[0]} -> {after[0]}, "
              f"lists {before[1]} -> {after[1]}, offers kept {before[2]} -> {after[2]}, penalties {before[3]} -> {after[3]}: "
              f"{('an offer, as a chunk id leaves' if valid else 'ignored, and counted') if ok else 'NOT as §4.4 says  <-- FAIL'}")
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
