#!/usr/bin/env python3
"""Directed records for §3's level 1, validate_chunk and committed_descriptor (protocol.md §3). The
toy's own functions are called in two toy nodes' namespaces on generated chunks and blocks, and trace3.py's tracer
logs each call with the node's whole state.

    python3 directed3v.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

Node 2 runs design A (`DESCRIPTOR_IN_CHUNK`: the chunk carries the descriptor, the bid commits the group's id), as
every cell does. Node 3 runs design B (the bid commits the descriptor).

What the records reach that the cells do not (in the cells every chunk is the committed piece at its index, of a
block that is there or not):
- no block yet (DEFER); a block of another slot than the copy names;
- design A: a chunk whose descriptor is not the one the bid's id commits (another descriptor; a block of no
  group, as one of columns); design B: a bid with another descriptor, or none;
- **a design B chunk in its wire shape, without a descriptor field** (half of node 3's; accepted where the bid's
  descriptor commits it), and a design A chunk without one (the document raises AttributeError);
- design A's block is the toy's, the committed id alone, four times in five; one in five has design B's member
  too, a descriptor that is another than the chunk's where the id is the chunk's (level 1 does not read it there);
- a group key that is not the committed id at the block's slot (a copy under another group's name; under the
  right id at another slot);
- a descriptor that is committed and not valid (plain where coded is the rule here, a count that is not twice K,
  a segment size of zero or beyond the limit, a hash that is not SHA-256);
- an index at the count, and beyond it;
- data longer or shorter than its segment (the last data chunk is the short one), and of the right length;
- a proof the tree refuses, and one it takes (the tree is the toy's stand-in: the scenario answers);
- committed_descriptor called directly, under both designs.

The scenario answers installed_block and verify_merkle_proof; the hash, the serialization and §1's functions are
the toy's own. A sample on which the Python raises is written with `raises` by the tracer; the counts are
printed.
"""
import argparse
import math
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402


class Scenario:
    def __init__(self):
        self.block, self.proof_ok = None, True


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed3v", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import run                          # noqa: E402: the pinned toy's
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    sc = Scenario()
    nodes = {}
    for k, in_chunk in ((2, True), (3, False)):
        nd = got["sim"].nodes[k]
        ns = nd.ns
        ns["DESCRIPTOR_IN_CHUNK"] = in_chunk
        ns["installed_block"] = lambda slot, root: sc.block
        ns["verify_merkle_proof"] = lambda root, data, index, count, proof: sc.proof_ok
        doc = {name: ns[name] for name in ("group_id", "group_key")}    # the document's, untraced: for this file's
        tr.install(nd, ns)                                              #   draws (neither calls a traced name)
        nodes[k] = (nd, ns, doc)
    ns2 = nodes[2][1]
    D, Chunk, UNIT, MAXSEG = ns2["SegmentDescriptor"], ns2["Chunk"], ns2["UNIT"], ns2["MAX_SEGMENT_SIZE"]

    rng = random.Random(a.seed)
    roots = [bytes([0xa1 + j]) * 32 for j in range(3)]
    raised, bare = Counter(), Counter()
    for _ in range(a.n):
        nd, ns, doc = nodes[rng.choice([2, 2, 3])]
        ns["now"] = rng.choice([1.0, 3.25])
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue",
                     "planned", "serve_count", "unwanted"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()

        def desc(valid=True):           # a coded descriptor: K data chunks and as many of parity
            ss = rng.choice([4, 8, 1000, UNIT])
            k = rng.choice([1, 2, 3, 8])
            tl = ss * k - rng.choice([0, 0, 1, ss - 1])         # the last data chunk whole, or short
            d = D(version=2, hash_id=0, encoding=1, count=2 * math.ceil(tl / ss), segment_size=ss, total_length=tl,
                  root=rng.randbytes(32))
            if not valid:
                what = rng.randrange(5)
                if what == 0:
                    d.version = 1                               # plain: its count is K, not 2 K
                elif what == 1:
                    d.count += rng.choice([-1, 1, 2])
                elif what == 2:
                    d.segment_size = rng.choice([0, MAXSEG + 1])
                elif what == 3:
                    d.hash_id = 1
                else:
                    d.encoding = 0
            return d

        slot = rng.choice([1, 2, 7])
        root = rng.choice(roots)
        d = desc(valid=rng.random() < 0.85)
        gid = doc["group_id"](d)
        other = desc()
        r = rng.random()
        if r < 0.1:
            sc.block = None                                     # no block yet
        else:
            bslot = slot if rng.random() < 0.9 else slot + 1
            committed = gid if rng.random() < 0.85 else rng.choice([doc["group_id"](other), None])
            sc.block = S.Block(bslot, root, committed)
            bid = sc.block.body.signed_execution_payload_bid.message
            # Design B's member, the descriptor: on a design B node's block (node 3) always. On a design A node's
            # (node 2) the toy's block has the id alone (sim.py's Block), and so it is here, most of the time. One
            # in five has the member too, with ANOTHER descriptor than the chunk's where the id is the chunk's:
            # a block the toy never makes, which shows that level 1 does not read the member under design A. (With
            # the member set to the chunk's own descriptor where the id matched, the bid's descriptor returned for
            # the chunk's would be the same value, and no record would tell `committed-bid-descriptor-under-a`.)
            if nd is nodes[3][0]:
                bid.execution_payload_segment_descriptor = d if committed == gid else (other if committed else None)
            elif rng.random() < 0.2:
                bid.execution_payload_segment_descriptor = other if committed == gid else (d if committed else None)
        r = rng.random()
        if r < 0.85 or sc.block is None:
            group = doc["group_key"](gid, slot)                 # the committed id at the copy's slot
        elif r < 0.93:
            group = doc["group_key"](gid, slot + 1)             # at another slot
        else:
            group = doc["group_key"](doc["group_id"](other), slot)      # another group's name
        count = max(d.count, 1)
        r = rng.random()
        index = rng.randrange(count) if r < 0.9 else rng.choice([count, count + 3])
        # the segment's length, as the document's segment_length has it, computed here: the document's own calls K,
        # a traced name, which from this file would be a record of its own
        ss, tl = d.segment_size, d.total_length
        kk = math.ceil(tl / ss) if ss else 0
        want = tl - (kk - 1) * ss if ss and index == kk - 1 else (ss or 4)
        n = want if rng.random() < 0.85 else max(0, want + rng.choice([-1, 1, 5]))
        sc.proof_ok = rng.random() < 0.9
        f = Chunk(slot=slot, beacon_block_root=root, group=group, descriptor=d, index=index,
                  proof=[rng.randbytes(32) for _ in range(rng.randrange(0, 4))], data=Wm.Blob(max(0, n), ("d", rng.randrange(8))))
        # a design B chunk in its wire shape has no descriptor field (protocol.md §2: "design A only"): half of
        # node 3's chunks. And now and then a design A chunk without one, where the document's `f.descriptor` raises
        if (nd is nodes[3][0] and rng.random() < 0.5) or (nd is nodes[2][0] and rng.random() < 0.03):
            del f.descriptor
            bare["design B, no descriptor" if nd is nodes[3][0] else "design A, no descriptor"] += 1
        try:
            if sc.block is not None and rng.random() < 0.2:
                ns["committed_descriptor"](sc.block, f)
            else:
                ns["validate_chunk"](f)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed3v: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, v in sorted(bare.items()):
        print(f"  chunks of {k}: {v}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
