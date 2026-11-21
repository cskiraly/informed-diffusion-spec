#!/usr/bin/env python3
"""Directed records for forward (protocol.md §5.2), candidates_for_source (§5.1) and on_mesh_join
(§5.4). The toy's own functions are called in a toy node's namespace on generated states, and trace3.py's
tracer logs each call with the node's whole state.

    python3 directed54.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not:
- **on_mesh_join whole** (no caller in the toy): no group held; groups held of which some have expired, some are
  INVALID, some have no state; the joining peer with entries in `pushed` and `peer_has` (announce subtracts them:
  nothing left to offer for a group it holds whole), and an offer a full queue refuses (owed);
- **candidates_for_source with a holder in its pool** (in a cell nobody holds a chunk when it is published), at a
  node whose uplink is under the stripe's (the pool is the mesh) and at one at it (every connected topic peer:
  the scenario's answer);
- forward: the sender in the mesh and outside it; no holder, some, R_NODE and more (no budget: every other peer
  is offered the chunk); a budget that covers the candidates (no key asked) and one that does not (the draw); **a
  push the queue refuses** (owed: among the cells loss-thin's alone); a candidate not targeted whose bit was
  pushed already (nothing offered); no mesh at all.

The states are in the toy's own forms (`pushed` as note_push leaves it, `peer_has` as on_have does, `chunks` and
`state` as the node's store and open_group leave them). The scenario answers expired, connected_topic_peers and the
push order's two keys (as directed53's), and draws enqueue's refusals; the draw and the gossip history's put are
the toy's own. Two nodes of a 5-node cell built as run.py builds it: node 2 as it is (uplink under the stripe's),
node 3 with its UPLINK set to STRIPE_UPLINK before the tracer is installed (a node's constants are read then). A
sample on which the Python raises is written with `raises` by the tracer; the counts are printed.
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

FNS = ["forward"] * 2 + ["candidates_for_source", "on_mesh_join"]


class Scenario:
    def __init__(self):
        self.tie, self.ids, self.expired, self.connected, self.refuse = {}, {}, set(), [], False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed54", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
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
        ns["connected_topic_peers"] = lambda: list(sc.connected)
        ns["tiebreak"] = lambda f, p: sc.tie[p]
        ns["peer_id_bytes"] = lambda p: sc.ids[p]

        def enqueue(p, x, urgent=False, own=ns["enqueue"]):         # the toy's own, but for the refusals drawn
            return False if sc.refuse and not urgent else own(p, x, urgent)
        ns["enqueue"] = enqueue
        if k == 3:                      # a node at the stripe's uplink: its source's pool is every connected peer
            ns["UPLINK"] = ns["STRIPE_UPLINK"] = 1e9
        tr.install(nd, ns)
        nodes[k] = (nd, ns)
    INVALID, COLLECTING, COMPLETE = (nodes[2][1][k] for k in ("INVALID", "COLLECTING", "COMPLETE"))
    assert nodes[2][1]["UPLINK"] < nodes[2][1]["STRIPE_UPLINK"] and int(nodes[2][1]["R_NODE"]) == 2

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised, kinds = Counter(), Counter()

    def chunk(gg, j):
        cid = bytes([7]) * 20
        return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, cid=cid,
                                     mid=gg + j.to_bytes(4, "little") + cid)

    for _ in range(a.n):
        what = rng.choice(FNS)
        nd, ns = nodes[3 if what == "candidates_for_source" and rng.random() < 0.5 else 2]
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(0, 8))
        g = rng.choice(groups)
        counts = {gg: rng.choice([4, 6, 8]) for gg in groups}
        i = rng.randrange(counts[g])
        f = chunk(g, i)
        sc.__init__()
        sc.refuse = rng.random() < 0.2
        sc.expired = {gg for gg in groups if rng.random() < 0.2}
        wide = rng.random() < 0.5
        for q in range(1, 64):
            sc.tie[q] = rng.randrange(1 << 64) if wide else rng.choice([0, 1, 2, (1 << 64) - 1])
            sc.ids[q] = bytes([rng.choice([0, 0x80]), q])

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue",
                     "planned"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        nd.writer_kicked.clear()
        for w in ns["gossip_history"].windows:
            w.clear()
        mesh = rng.sample(peers, rng.randrange(len(peers) + 1))
        ns["mesh"] = set(mesh)
        sc.connected = rng.sample(peers, rng.randrange(len(peers) + 1))
        few = rng.random() < 0.5
        for q in peers:
            for gg in groups:
                c = counts[gg]
                r = rng.random()
                if r < 0.55:                    # assigned, as the toy's on_have does; the chunk's bit in a third
                    h = ns["peer_has"][q][gg]
                    v = 0 if r < 0.08 else (rng.choice([1, 3]) if few else rng.randrange(1 << c))
                    if gg == g and rng.random() < 0.35:
                        v |= 1 << i
                    if rng.random() < 0.08:
                        v = (1 << c) - 1        # the group whole: nothing left to offer it
                    h.bits = B.Bits(v)
                    h.ttl = int(ns["HAVE_TTL"])
                if rng.random() < 0.5:
                    pe = ns["pushed"][q][gg]     # as note_push leaves it
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, 0.3, 1.0])
                    pe |= B.Bits(rng.choice([1, 2, 3, 7]) if few else rng.randrange(1, 1 << c))
                    if gg == g and rng.random() < 0.2:
                        pe |= B.Bits(1 << i)
                    if rng.random() < 0.1:
                        pe.v = 0
                    pe.ttl = rng.randrange(1, int(ns["PUSH_TTL"]) + 1)
            if rng.random() < 0.3:
                ns["queue"][q].normal.append(trace3_entry(tr, rng, groups, B))
        held = rng.sample(groups, rng.randrange(len(groups) + 1))       # the store: groups in a drawn order
        for gg in held:
            for j in rng.sample(range(counts[gg]), rng.randrange(1, counts[gg] + 1)):
                cj = chunk(gg, j)
                ns["chunks"][gg][j] = cj
                ns["known_id"][gg][j] = cj.mid
            r = rng.random()
            if r < 0.6:
                ns["state"][gg] = rng.choice([COLLECTING, COMPLETE])
            elif r < 0.85:
                ns["state"][gg] = INVALID       # a dropped group: its chunks may still be in the store

        # ---- the call
        try:
            if what == "forward":
                sender = rng.choice(mesh) if mesh and rng.random() < 0.7 else rng.randrange(1, 64)
                holding = [q for q in mesh if g in ns["peer_has"][q] and ns["peer_has"][q][g].bits.v >> i & 1]
                cands = [q for q in mesh if q not in holding and q != sender]
                budget = max(0, 2 - len(holding))
                kinds["forward: " + ("no mesh" if not mesh else "no budget" if not budget else
                                     "everyone pushed" if budget >= len(cands) else "the draw")
                      + (", the sender outside the mesh" if mesh and sender not in mesh else "")
                      + (", pushes refused" if sc.refuse and budget and cands else "")] += 1
                ns["forward"](f, sender)
            elif what == "candidates_for_source":
                stripe = ns["UPLINK"] >= ns["STRIPE_UPLINK"]
                pool = sc.connected if stripe else mesh
                holder = any(g in ns["peer_has"][q] and ns["peer_has"][q][g].bits.v >> i & 1 for q in pool)
                kinds["candidates_for_source: " + ("every connected peer" if stripe else "the mesh")
                      + (", nobody there" if not pool else ", a holder among them" if holder else ", no holder")] += 1
                ns["candidates_for_source"](f)
            else:
                p = rng.choice(peers) if peers and rng.random() < 0.8 else rng.randrange(1, 64)
                live = [gg for gg in held if gg not in sc.expired and ns["state"][gg] != INVALID]
                kinds["on_mesh_join: " + ("nothing held" if not held else "nothing to offer of what is held" if not live
                                          else f"{len(live)} of {len(held)} groups offered")
                      + (", offers refused" if sc.refuse and live else "")] += 1
                ns["on_mesh_join"](p)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed54: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, n in sorted(kinds.items()):
        print(f"  {k}: {n}", file=sys.stderr)


def trace3_entry(tr, rng, groups, B):
    """An offer queued before the call: an IHAVE of a few bits of a group."""
    Wm = tr.Wm
    return Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 1 << 4)))))


if __name__ == "__main__":
    main(sys.argv[1:])
