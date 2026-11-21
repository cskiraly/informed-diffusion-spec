#!/usr/bin/env python3
"""Directed records for drop_offer (protocol.md §6.1). The toy's own drop_offer is called in a
toy node's namespace on generated states, and trace3.py's tracer logs each call with the node's whole state. It
asks nothing of the rest of the node: it reads and writes the twin's own tables alone, and calls close_promises.

    python3 directed6o.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells and the other sets do not (directed4b reaches drop_offer through drop_tie,
with no queue and no promise drawn; the cells never call it):
- `offered[p][g]` with the chunk's bit and without it, and other peers' bitmaps of the group, which stay;
- `offers` under both forms of the chunk's key (by index, and a full id): p alone in the list (the list goes), p
  among others (p goes), p not in it; and offers of other chunks that list p, which stay;
- p's queue: none (the lane assigned stays missing, and no row is made); a row there with both lanes empty; a
  normal lane with an IWANT of the chunk alone (the entry goes), of the chunk and others, in both forms of its key,
  riding on a chunk (the entry stays); IHAVEs, which stay; and an IWANT of the chunk in the urgent lane, which
  stays: the document's loop is over the normal lane;
- other peers' queues with asks of the chunk, which stay;
- promises of the chunk under both forms of its key, to p (closed) and to others (kept); and `tried` and
  `asked_at` of the chunk, which stay: close_promises is called with `of=p`.

The node is node 2 of a 5-node cell built as run.py builds it (no event runs). A sample on which the Python raises
is written with `raises` by the tracer; the counts are printed.
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


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed6o", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    nd = got["sim"].nodes[2]
    ns = nd.ns
    tr.install(nd, ns)

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised = Counter()
    for _ in range(a.n):
        n_ = rng.choice([3, 4, 6])
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 6))
        g, i = rng.choice(groups), rng.randrange(n_)
        p = rng.choice(peers) if rng.random() < 0.9 else rng.choice([q for q in range(1, 64) if q not in peers])

        def fid(gg, j, salt=7):
            return gg + j.to_bytes(4, "little") + bytes([salt]) * 20

        def keys_of(gg, j):             # the two forms of a chunk's ask key
            return [Wm.WantIndex(gg, j), fid(gg, j)]

        def chunk(gg, j):
            return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, mid=fid(gg, j))

        def some_chunk():               # the chunk in hand, more often than chance; or another
            return (g, i) if rng.random() < 0.6 else (rng.choice(groups), rng.randrange(n_))

        def iwant():
            ids = []
            for _ in range(rng.randrange(1, 4)):
                ids.append(rng.choice(keys_of(*some_chunk())))
            return Wm.IWANT(ids)

        def entry():
            r = rng.random()
            if r < 0.55:                # an IWANT, of the chunk alone now and then
                return Wm.Entry(control=Wm.IWANT([rng.choice(keys_of(g, i))]) if rng.random() < 0.4 else iwant())
            if r < 0.8:                 # a chunk, now and then with an IWANT riding on it
                e = Wm.Entry(chunk=chunk(rng.choice(groups), rng.randrange(n_)), solicited=rng.random() < 0.4)
                if rng.random() < 0.5:
                    e.control = iwant()
                return e
            return Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 1 << n_)))))

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        for q in sorted(set(peers) | {p}):
            for gg in groups:
                r = rng.random()
                if r < 0.35:
                    ns["offered"][q][gg] = B.Bits(rng.randrange(1, 1 << n_))
                elif r < 0.55 and gg == g:
                    ns["offered"][q][gg] = B.Bits(1 << i)       # the chunk's bit alone: the bitmap is left empty
        for _ in range(rng.randrange(0, 5)):                    # offer lists, under either form of a chunk's key
            b = rng.choice(keys_of(*some_chunk()))
            r = rng.random()
            who = [p] if r < 0.3 else rng.sample(peers, rng.randrange(1, len(peers) + 1))
            if r >= 0.3 and rng.random() < 0.5 and p not in who:
                who.insert(rng.randrange(len(who) + 1), p)
            for q in who:
                if q not in ns["offers"][b]:
                    ns["offers"][b].append(q)
        for _ in range(rng.randrange(0, 5)):                    # promises, to p and to others
            b = rng.choice(keys_of(*some_chunk()))
            ns["promises"][(b, p if rng.random() < 0.6 else rng.choice(peers))] = rng.choice([0.5, 0.9])
        for _ in range(rng.randrange(0, 3)):                    # tried and asked_at of a chunk: they stay
            b = rng.choice(keys_of(*some_chunk()))
            ns["tried"][b][rng.choice(peers)] = 0.5
            if rng.random() < 0.5:
                ns["asked_at"][b] = 0.5
        for q in sorted(set(peers) | {p}):
            r = rng.random()
            if q == p and r < 0.2:
                continue                                        # no queue of p's
            if q != p and r < 0.5:
                continue
            pq = ns["queue"][q]
            if q == p and r < 0.3:                              # a row there, both lanes empty
                pq.normal.append(entry())
                pq.normal.pop()
                continue
            for _ in range(rng.randrange(0, 5)):
                pq.normal.append(entry())
            for _ in range(rng.randrange(0, 2)):                # the urgent lane: an ask of the chunk there stays
                pq.urgent.append(Wm.Entry(control=Wm.IWANT([rng.choice(keys_of(g, i))])))

        # ---- the call
        try:
            ns["drop_offer"](g, i, p)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed6o: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
