#!/usr/bin/env python3
"""Directed records for §4.3's on_have (protocol.md §4.3). The toy's own function is called in a toy
node's namespace on generated states, and trace3.py's tracer logs each call with the node's whole state.

    python3 directed43.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not (in the cells no group expires, every HAVE is valid, and a peer's
entry is new or carries the toy's ttl):
- a HAVE for an expired group (ignored), and one that is not valid, with bits at or beyond the group's count
  (the sender penalised, nothing else);
- the peer's entry for the group: missing, there and empty, there with some of the HAVE's bits, with all of them
  (nothing new: the ttl still refreshed), with a ttl run down to 1 or 0;
- an empty HAVE, which makes the entry and nothing else;
- new indices, one to six: each joins `holders`, into a set that is missing, that holds other peers, that holds
  this peer already (stale: the simulator's expiry clears both, but the document's function does not assume it);
- a group the node publishes (in `planned`): `origin_acked` for each new index, a call with its log (the node's
  own HAVE grows, HAVEs and announcements go to the mesh), for an index acked already too; and a group not
  planned;
- `window_release` for each new index (the twin's own): with nothing in flight, and, in half of the samples,
  **with sends in flight to the peer for some of the HAVE's indices and peers in line**: a slot freed, the next
  in line woken. Beside a planned group this is the record where the order of on_have's two calls shows (the
  wake, then the mesh asked): both calls are the twin's own, and without a window drawn here no set would tell
  `have-release-after-ack`.

The scenario answers `expired`; `valid_have`, `penalise`, `window_release` and `origin_acked` are the toy's own.
The node is node 2 of a 5-node cell built as run.py builds it (no event runs), with a window of 2 slots (W, set
before the tracer is installed, as directed71's). A sample on which the Python raises
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
    tr = trace3.Tracer3(toy, a.out, ["directed43", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    nd = got["sim"].nodes[2]
    ns = nd.ns
    gone = set()
    ns["expired"] = lambda g: g in gone
    ns["W"] = 2                         # a window of two slots (a node's constant, read at install)
    tr.install(nd, ns)
    TTL = ns["HAVE_TTL"]

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    raised = Counter()
    for _ in range(a.n):
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 7))
        p = rng.choice(peers)
        g = rng.choice(groups)
        counts = {gg: rng.choice([4, 6, 8]) for gg in groups}
        n_ = counts[g]
        gone.clear()
        gone.update(gg for gg in groups if rng.random() < 0.1)

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue",
                     "planned", "sent"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        nd.writer_kicked.clear()
        # the window (§7.1): idle, or in use, with sends in flight to p for indices of g and peers in line
        ns["waiters"].clear()
        in_use = rng.random() < 0.5
        ns["in_flight"]._h.count = rng.choice([1, 2, 2, 3]) if in_use else 0   # the count itself, behind the tracer's
        #                                                                         cell (no record is open)
        if in_use:
            others = [q for q in peers if q != p]
            r = rng.random()
            ns["waiters"].extend([] if r < 0.25 else rng.sample(others, rng.randrange(1, len(others) + 1)) if r < 0.8
                                 else [p] + rng.sample(others, rng.randrange(0, len(others) + 1)))
            for j in range(n_):
                if rng.random() < 0.4:
                    ns["sent"][(p, g, j)] = ns["now"] - 0.2         # a copy of chunk j in flight to p
            for q in others:                                         # other sends in flight
                if rng.random() < 0.3:
                    ns["sent"][(q, rng.choice(groups), rng.randrange(8))] = ns["now"] - 0.2
        ns["mesh"] = set(rng.sample(peers, rng.choice([0, 1, 2, len(peers)])))
        for gg in groups:
            c = counts[gg]
            if rng.random() < 0.8:              # the count known: a HAVE's bits are held to it
                ns["desc"][gg] = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32,
                                                       count=c, segment_size=8, total_length=4 * c)
            if rng.random() < 0.35:             # a group this node publishes: its own HAVE, and whom it pushes what
                ns["origin"][gg] = B.Bits(rng.randrange(1 << c))
                ns["planned"][gg] = {j: set(rng.sample(peers, rng.randrange(0, 3))) for j in range(c) if rng.random() < 0.6}
                ns["mine"][gg] = B.Bits((1 << c) - 1)
            for q in peers:
                r = rng.random()
                if r < 0.45:                    # the peer's entry: some bits or none, a ttl fresh or run down
                    e = ns["peer_has"][q][gg]
                    e.bits = B.Bits(rng.randrange(1 << c) if rng.random() < 0.8 else 0)
                    e.ttl = rng.choice([TTL, TTL, 1, 0])
                if rng.random() < 0.3:
                    pe = ns["pushed"][q][gg]         # as note_push leaves it: a clock and a ttl with its bits (`pushed`
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, 0.3, 1.0])     # the twin's own); one in
                    pe |= B.Bits(rng.randrange(1, 1 << c))                 # ten with no bit left, as unpush can leave it
                    if rng.random() < 0.1:
                        pe.v = 0
                    pe.ttl = rng.randrange(1, int(ns["PUSH_TTL"]) + 1)
                if rng.random() < 0.3:
                    ns["sent_to"][q][gg] = B.Bits(rng.randrange(1, 1 << c))
            for j in range(c):                  # the holders: of the peer's bits, and now and then others
                for q in peers:
                    has = gg in ns["peer_has"][q] and ns["peer_has"][q][gg].bits.has(j)
                    if (has and rng.random() < 0.9) or rng.random() < 0.05:
                        ns["holders"][gg][j].add(q)
        for q in peers:
            if rng.random() < 0.4:
                ns["queue"][q].normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(
                    group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 1 << 4))))))

        # ---- the HAVE
        r = rng.random()
        if r < 0.08:
            bits = 0                                            # an empty HAVE
        elif r < 0.2:
            bits = rng.randrange(1, 1 << n_) | (1 << rng.choice([n_, n_ + 1, 40]))     # beyond the count
        elif r < 0.35 and g in ns["peer_has"][p]:
            have = ns["peer_has"][p][g].bits.v                  # nothing new: bits the entry has
            bits = have & rng.randrange(1 << n_) if have else 0
        else:
            bits = rng.randrange(1, 1 << n_)
        try:
            ns["on_have"](p, Wm.HaveBitmap(group=g, bits=B.Bits(bits)))
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed43: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
