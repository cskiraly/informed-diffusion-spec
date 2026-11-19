#!/usr/bin/env python3
"""Directed records for §4.6's decode_group and push_rebuilt (protocol.md lines 829-838 and 840-849). The toy's
own functions are called in two toy nodes' namespaces on generated states, and trace3.py's tracer logs each call
with the node's whole state.

    python3 directed46d.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

Node 2 runs the document's push_rebuilt. Node 3 runs its own under that name, a variant of the repair that
announces nothing and pushes one chunk to the first mesh peer, so there decode_group's call of it is a call on
the tape, and push_rebuilt has no record.

What the records reach that the cells do not (in the cells a decode gives every chunk, no group expires while it
decodes, no queue refuses, and a mesh peer's shortfall is what its HAVEs left):
- decode_group: a root that differs (the group dropped: its state INVALID, its queue entries gone); a group that
  expired meanwhile (nothing stored, pushed or delivered); a decode that gives every chunk, or the chunks held
  alone (nothing new); chunks received meanwhile, which are not new; the rebuilt chunks in index order and in
  another; a payload that is nothing, as the toy's, or a blob;
- push_rebuilt: the mesh empty, one peer, several, drawn in another order; a peer that claimed everything (not
  short), one short by less than what it lacks (the first of the draw), by more (all it lacks), one that lacks
  nothing new though short; what was pushed to it counted as known; a queue that refuses (the chunk owed); a
  queue row there, and one the push makes;
- push_rebuilt called directly, with indices new and not.

The scenario answers decode_and_reencode, expired, payload_of, deliver; the node's store, its enqueue (but for the
refusals drawn), the draws, note_push and owe are the toy's own. A sample on which the Python raises is written
with `raises` by the tracer; the counts are printed.
"""
import argparse
import random
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402


class Scenario:
    def __init__(self):
        self.expired, self.rebuilt, self.payload, self.refuse = set(), None, None, False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed46d", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    sc = Scenario()
    nodes = {}
    for k in (2, 3):
        nd = got["sim"].nodes[k]
        ns = nd.ns
        ns["content_id"] = lambda f: f.cid
        ns["expired"] = lambda g: g in sc.expired
        ns["decode_and_reencode"] = lambda chunks_g, d: sc.rebuilt
        ns["payload_of"] = lambda rebuilt: sc.payload
        ns["deliver"] = lambda g, payload: None

        def enqueue(p, x, urgent=False, own=ns["enqueue"]):         # the toy's own, but for the refusals drawn
            return False if sc.refuse and not urgent else own(p, x, urgent)
        ns["enqueue"] = enqueue
        if k == 3:                      # this node's own repair: one chunk to the first mesh peer, by its index
            def push_rebuilt(g, new, ns=ns):
                mesh = sorted(ns["mesh"])
                if mesh and new:
                    ns["enqueue"](mesh[0], ns["chunks"][g][min(new)], urgent=False)
            ns["push_rebuilt"] = push_rebuilt
        tr.install(nd, ns)
        nodes[k] = (nd, ns)
    C = {k: nodes[2][1][k] for k in ("COLLECTING", "DECODING", "COMPLETE", "INVALID")}

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised = Counter()
    for _ in range(a.n):
        what = rng.choice(["decode_group", "decode_group", "push_rebuilt"])
        nd, ns = nodes[3 if what == "decode_group" and rng.random() < 0.3 else 2]
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 7))
        g = rng.choice(groups)
        counts = {gg: rng.choice([4, 6, 8]) for gg in groups}
        n_ = counts[g]
        k_ = n_ // 2
        sc.__init__()
        sc.expired = {gg for gg in groups if rng.random() < 0.1}
        sc.refuse = rng.random() < 0.15
        sc.payload = None if rng.random() < 0.7 else Wm.Blob(rng.choice([16384, 40000]), ("payload", rng.randrange(4)))

        def chunk(gg, j):
            cid = bytes([7]) * 20
            return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, cid=cid,
                                         mid=gg + j.to_bytes(4, "little") + cid)

        # ---- the state, cleared, then drawn
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
        for w in ns["gossip_history"].windows:
            w.clear()
        ns["mesh"] = set(rng.sample(peers, rng.choice([0, 1, 2, len(peers)])))
        for gg in groups:
            c = counts[gg]
            ns["desc"][gg] = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32,
                                                   count=c, segment_size=4, total_length=4 * (c // 2))
            ns["state"][gg] = C["DECODING"] if gg == g else rng.choice(list(C.values()))
            have = rng.sample(range(c), rng.randrange(c // 2, c + 1)) if gg == g else rng.sample(range(c), rng.randrange(0, c))
            for j in have:              # the chunks held: received, but for one now and then (stored by a decode before)
                f = chunk(gg, j)
                ns["chunks"][gg][j] = f
                ns["known_id"][gg][j] = f.mid
                if rng.random() < 0.9:
                    ns["received"][gg].set(j)
            ns["mine"][gg] = B.Bits((1 << c) - 1) if gg == g else B.Bits(0)
            ns["stop_pull"][gg] = gg == g
            for q in peers:
                r = rng.random()
                if r < 0.5:             # what the peer claimed: some, or everything (its decode claim)
                    e = ns["peer_has"][q][gg]
                    e.bits = B.Bits(rng.randrange(1 << c) if r < 0.38 else (1 << c) - 1)
                    e.ttl = 3
                if rng.random() < 0.3:  # what was pushed to it: the toy's own entry (note_push sets its clock and ttl)
                    pe = ns["pushed"][q][gg]         # as note_push leaves it: a clock and a ttl with its bits (`pushed`
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, 0.3, 1.0])     # the twin's own); one in
                    pe |= B.Bits(sum(1 << j for j in rng.sample(range(c), rng.randrange(1, c))))                 # ten with no bit left, as unpush can leave it
                    if rng.random() < 0.1:
                        pe.v = 0
                    pe.ttl = rng.randrange(1, int(ns["PUSH_TTL"]) + 1)
        for q in peers:
            r = rng.random()
            if r < 0.5:
                continue                # no queue of the peer's: a push makes the row
            pq = ns["queue"][q]
            for _ in range(rng.randrange(0, 3)):        # chunks of g and of others, and control, in the normal lane
                gg = g if rng.random() < 0.5 else rng.choice(groups)
                if rng.random() < 0.6:
                    pq.normal.append(Wm.Entry(chunk=chunk(gg, rng.randrange(counts[gg])), solicited=rng.random() < 0.4))
                else:
                    pq.normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(group=gg, bits=B.Bits(1)))))

        # ---- the call
        try:
            if what == "push_rebuilt":
                held = sorted(ns["chunks"][g])
                new = rng.sample(held, rng.randrange(0, len(held) + 1))
                ns["push_rebuilt"](g, new)
            else:
                r = rng.random()
                if r < 0.12:
                    sc.rebuilt = None                           # the root differs
                else:
                    idx = list(range(n_)) if r < 0.8 else sorted(ns["chunks"][g])       # every chunk, or those held
                    if rng.random() < 0.3:
                        rng.shuffle(idx)
                    sc.rebuilt = {j: chunk(g, j) for j in idx}
                ns["decode_group"](g)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed46d: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
