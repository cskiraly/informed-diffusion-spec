#!/usr/bin/env python3
"""Directed records for §6.4's on_heartbeat (protocol.md §6.4). The toy's own function is called in
toy nodes' namespaces on generated states, and trace3.py's tracer logs each call with the node's whole state.

    python3 directed64h.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

Three nodes of one cell are traced, each with its own constants (the nodes line), and each sample is one
call at one of them:

    node 1: PACED on,  D_LAZY 6, GOSSIP_FACTOR 0.25   (the toy's)
    node 2: PACED off, D_LAZY 2, GOSSIP_FACTOR 0.5
    node 3: PACED on,  D_LAZY 0, GOSSIP_FACTOR 0.3

What the records reach that the cells do not (in the cells no ask is held back at a heartbeat, every peer is
eligible, and the constants are the toy's):
- the IHAVE limits' counts, some there, cleared; none there;
- asks held back, none to three, under both forms of an ask key, in a drawn order: the retry of each, which asks
  (an offer there, nobody asked lately), or returns early (the chunk held, the group stopped or expired, an ask in
  flight), or finds nobody to ask;
- §4.2's copies waiting under a root whose group expired (dropped), and ones that stay;
- gossip ids: none, of one group, of several;
- topic peers in a drawn order: in the mesh (not asked for eligibility), not eligible, eligible; none eligible;
- the count: fewer eligible peers than D_LAZY (all of them), D_LAZY above the factor's share, the share above
  D_LAZY, a share that is no whole number (floor), D_LAZY zero with a share of zero (nobody);
- paced: jobs appended to an empty queue and behind jobs already there, each with the heartbeat's ids and time;
  not paced: send_gossip for each sampled peer, with announce's log.

The scenario answers expired, topic_peers, gossip_eligible, connected_topic_peers, release and content_id; the
draw (`sample_without_replacement`) is the toy's own. A sample on which the Python raises is written with `raises`
by the tracer; the counts are printed.
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

NODES = {1: dict(PACED=True, D_LAZY=6, GOSSIP_FACTOR=0.25), 2: dict(PACED=False, D_LAZY=2, GOSSIP_FACTOR=0.5),
         3: dict(PACED=True, D_LAZY=0, GOSSIP_FACTOR=0.3)}


class Scenario:
    def __init__(self):
        self.expired, self.topic, self.ineligible = set(), [], set()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed64h", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    sc = Scenario()
    nodes = {}
    for k, consts in NODES.items():
        nd = got["sim"].nodes[k]
        ns = nd.ns
        ns.update(consts)
        ns["expired"] = lambda g: g in sc.expired
        ns["topic_peers"] = lambda: list(sc.topic)
        ns["connected_topic_peers"] = lambda: list(sc.topic)
        ns["gossip_eligible"] = lambda q: q not in sc.ineligible
        ns["release"] = lambda p, f: None
        ns["content_id"] = lambda f: f.cid
        tr.install(nd, ns)
        nodes[k] = (nd, ns)

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    roots = [bytes([0xa1 + j]) * 32 for j in range(2)]
    raised = Counter()
    for _ in range(a.n):
        nd, ns = nodes[rng.choice([1, 1, 2, 2, 3])]
        n_ = rng.choice([3, 4, 6])
        now = ns["now"] = rng.choice([1.0, 3.25, 10.0])
        peers = rng.sample(range(1, 64), rng.choice([0, 1, 2, 3, 5, 8, 12, 12, 14]))
        sc.__init__()
        sc.topic = list(peers)
        sc.expired = {gg for gg in groups if rng.random() < 0.15}
        sc.ineligible = {q for q in peers if rng.random() < rng.choice([0.0, 0.2, 0.2, 1.0])}

        def fid(gg, j, salt=7):
            return gg + j.to_bytes(4, "little") + bytes([salt]) * 20

        def keys_of(gg, j):             # the two forms of a chunk's ask key
            return [Wm.WantIndex(gg, j), fid(gg, j)]

        def chunk(gg, j, root):
            return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, mid=fid(gg, j),
                                         cid=bytes([7]) * 20)

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        for w in ns["gossip_history"].windows:
            w.clear()
        ns["mesh"] = set(q for q in peers if rng.random() < rng.choice([0.0, 0.3, 0.3, 0.6]))
        for q in peers:                                         # §4.4's counts
            if rng.random() < 0.4:
                ns["ihave_frames"][q] = rng.randrange(1, 5)
            if rng.random() < 0.3:
                ns["ihave_asked"][q] = rng.randrange(1, 40)
        held = []
        for _ in range(rng.choice([0, 0, 1, 2, 3]) if peers else 0):    # asks held back, and what their retries read
            gg, j = rng.choice(groups), rng.randrange(n_)
            if (gg, j) in ns["held_back"]:
                continue
            b = rng.choice(keys_of(gg, j))
            ns["held_back"][(gg, j)] = b
            held.append(b)
            r = rng.random()
            if r < 0.7:                                         # offers of it, in the list and in bitmaps
                for q in rng.sample(peers, rng.randrange(1, min(len(peers), 3) + 1)):
                    ns["offers"][b].append(q)
                    ns["offered"][q][gg] = B.Bits(ns["offered"][q][gg].v | (1 << j))
            if rng.random() < 0.15:
                ns["mine"][gg] = B.Bits(1 << j)                 # held meanwhile
            if rng.random() < 0.1:
                ns["stop_pull"][gg] = True
            if rng.random() < 0.2:
                ns["asked_at"][b] = now - rng.choice([0.05, 0.5])   # in flight, or long ago
            if rng.random() < 0.2 and peers:
                ns["tried"][b][rng.choice(peers)] = now - 0.5
        for root in roots:                                      # §4.2's copies waiting: some of an expired group
            for _ in range(rng.choice([0, 0, 0, 1, 2]) if peers else 0):
                f = chunk(rng.choice(groups), rng.randrange(n_), root)
                p = rng.choice(peers)
                if f.mid in ns["pending_ids"] or any(q == p and x.mid == f.mid for q, x in ns["pending"][root]):
                    continue
                ns["pending"][root].append((p, f))
                ns["pending_ids"].add(f.mid)
        hist = ns["gossip_history"].windows                     # the gossip history's last windows
        r = rng.random()
        gs = [] if r < 0.15 else groups[:1] if r < 0.5 else rng.sample(groups, rng.randrange(1, 4))
        for gg in gs:
            for j in rng.sample(range(n_), rng.randrange(1, n_ + 1)):
                hist[rng.randrange(0, 4)].append(fid(gg, j))    # window 3 is past the three that gossip
        if rng.random() < 0.3:                                  # jobs of an earlier heartbeat still queued
            old = [fid(groups[0], 0)]
            for _ in range(rng.randrange(1, 3)):
                ns["pace_queue"].append((rng.randrange(1, 64), old, now - 0.7))
        for q in peers:
            for gg in groups:
                if rng.random() < 0.3:          # what the peer said it holds, and what was pushed to it
                    h = ns["peer_has"][q][gg]
                    h.bits = B.Bits(rng.randrange(1, 1 << n_) if rng.random() < 0.7 else (1 << n_) - 1)
                if rng.random() < 0.3:
                    pe = ns["pushed"][q][gg]         # as note_push leaves it: a clock and a ttl with its bits (`pushed`
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, 0.3, 1.0])     # the twin's own); one in
                    pe |= B.Bits(rng.randrange(1, 1 << n_))                 # ten with no bit left, as unpush can leave it
                    if rng.random() < 0.1:
                        pe.v = 0
                    pe.ttl = rng.randrange(1, int(ns["PUSH_TTL"]) + 1)
            if rng.random() < 0.3:
                ns["queue"][q].normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(
                    group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 1 << n_))))))

        # ---- the call
        try:
            ns["on_heartbeat"]()
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed64h: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
