#!/usr/bin/env python3
"""A known answer for §6.1's reference order of the announcers beyond the list (`own_order`).

    python3 own_order_known.py

The order is the node's own. No other node sees it, so nothing requires two implementations to agree on it. This
file is for those that want to compare themselves with the toy in tests. It fixes the reference function, how a
test derives a node's secret, and one answer.

- The rank of peer q for a chunk: the first 8 bytes, read little-endian, of
  HMAC-SHA-256(secret, group + index as uint32 little-endian + peer id); larger first, then the larger peer id.
- A test's secret for a node: SHA-256("own order" + seed as uint64 little-endian + the node's peer id). A real
  node draws its secret at random.
- The toy's peer id of node p: SHA-256("peer" + p as uint32 little-endian).

The answer below is for seed 7, node 2, the group whose key is 32 bytes of 0x11, and the peers 1, 3, 4, 5. It is
computed twice, through the toy's own `own_order` (by index and by full id) and by the formula written out here
without the toy, and both are compared with it. A control: with the rank read big-endian the order differs for
both chunks, so the comparison can fail.
"""
import hashlib
import hmac
import sys
from pathlib import Path

SEED, NODE, PEERS, GROUP = 7, 2, [1, 3, 4, 5], bytes([0x11]) * 32
SECRET = "0e7cfbf7a74aee104a4025c5db24d9533bf980017b3c8d13a0d731740e293947"
ORDER = {0: [5, 1, 3, 4], 2: [4, 5, 1, 3]}          # index -> the peers, first to last


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)])
    ns = got["sim"].nodes[NODE].ns

    def pid(p):
        return hashlib.sha256(b"peer" + p.to_bytes(4, "little")).digest()

    secret = hashlib.sha256(b"own order" + SEED.to_bytes(8, "little") + pid(NODE)).digest()
    bad = secret.hex() != SECRET
    print(f"seed {SEED}, node {NODE}: secret {secret.hex()}{'' if not bad else '  <-- not the known one'}")
    differs = 0
    for i, known in ORDER.items():
        chunk = GROUP + i.to_bytes(4, "little")

        def rank(q, order="little"):
            return int.from_bytes(hmac.new(secret, chunk + pid(q), hashlib.sha256).digest()[:8], order), pid(q)

        written = sorted(PEERS, key=rank, reverse=True)
        big = sorted(PEERS, key=lambda q: rank(q, "big"), reverse=True)
        by_index = ns["own_order"](PEERS, Wm.WantIndex(GROUP, i))
        by_id = ns["own_order"](PEERS, chunk + bytes(20))
        same = by_index == written == by_id == known
        bad += not same
        differs += big != written
        print(f"index {i}: known {known}; the toy by index {by_index}, by full id {by_id}; written out {written}: "
              f"{'equal' if same else 'DIFFERENT'}; ranks {[rank(q)[0] for q in PEERS]}; read big-endian {big}")
    print(f"the control, big-endian: another order for {differs} of {len(ORDER)} chunks{'' if differs else '  <-- FAIL'}")
    print("ok" if not bad and differs else "FAIL")
    return 0 if not bad and differs else 1


if __name__ == "__main__":
    sys.exit(main())
