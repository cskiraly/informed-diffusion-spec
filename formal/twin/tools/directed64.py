#!/usr/bin/env python3
"""Directed records for §6.4's on_pace_tick and send_gossip (protocol.md §6.4). The toy's own
functions are called in a toy node's namespace on generated states, and trace3.py's tracer logs each call with
the node's whole state.

    python3 directed64.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not (in the cells every peer is connected, and a job is stale only
where a tick comes late):
- the pace queue empty at the tick; one job to five;
- a job stale by more than a heartbeat, by exactly one (`now - at >= HEARTBEAT` at equality), fresh by a little;
- a job whose peer has left (`connected(q)` false; the toy's own answers True always, so this set puts its own
  function there before the tracer wraps it), asked only of a job that is not stale;
- several jobs dropped before one is sent, every job dropped (the queue runs out), and jobs left after the one
  sent, which stay;
- a job with no ids (nothing announced), with ids of one group and of several, an id twice;
- announce's part, a call with its log: an offer of which `pushed` or `peer_has` leaves nothing is not enqueued
  (no log), another is appended to the peer's normal lane, in a row there or made by the call;
- send_gossip called directly.

The node is node 2 of a 5-node cell built as run.py builds it (no event runs). A sample on which the Python raises
is written with `raises` by the tracer; the counts are printed.
"""
import argparse
import random
import sys
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
    tr = trace3.Tracer3(toy, a.out, ["directed64", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
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
    ns["connected"] = lambda q: q not in gone       # the node's answer, drawn here (the toy's: always True)
    tr.install(nd, ns)
    HB = ns["HEARTBEAT"]

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    raised = Counter()
    for _ in range(a.n):
        n_ = rng.choice([3, 4, 6])
        now = ns["now"] = rng.choice([1.0, 3.25, 10.0])
        peers = rng.sample(range(1, 64), rng.randrange(2, 6))
        gone.clear()
        gone.update(q for q in peers if rng.random() < 0.25)

        def fid(gg, j, salt=7):
            return gg + j.to_bytes(4, "little") + bytes([salt]) * 20

        def some_ids():
            r = rng.random()
            if r < 0.12:
                return []
            gs = groups[:1] if r < 0.45 else rng.sample(groups, rng.randrange(1, 4))
            ids = [fid(rng.choice(gs), rng.randrange(n_)) for _ in range(rng.randrange(1, 7))]
            if rng.random() < 0.2:
                ids.append(rng.choice(ids))                     # an id twice
            return ids

        def when():                     # stale, at the bound, fresh
            off = rng.choice([0.0, 0.25, 0.5, HB, HB, 0.75, 2.0])
            if rng.random() < 0.1:
                return now - HB - rng.choice([-1e-9, 1e-9])
            return now - off

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
        shared = some_ids()             # a heartbeat's jobs hold one list of ids
        for _ in range(rng.choice([0, 1, 1, 2, 3, 5])):
            q = rng.choice(peers) if rng.random() < 0.9 else rng.choice([x for x in range(1, 64) if x not in peers])
            ns["pace_queue"].append((q, shared if rng.random() < 0.6 else some_ids(), when()))
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
            r = rng.random()
            if r < 0.5:
                continue                        # no queue of the peer's: announce's enqueue makes the row
            pq = ns["queue"][q]
            if r < 0.65:                        # a row there, both lanes empty
                pq.normal.append(Wm.Entry(control=Wm.IWANT([fid(groups[0], 0)])))
                pq.normal.pop()
                continue
            for _ in range(rng.randrange(1, 3)):
                pq.normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(group=rng.choice(groups),
                                                                         bits=B.Bits(rng.randrange(1, 1 << n_))))))

        # ---- the call
        try:
            if rng.random() < 0.85:
                ns["on_pace_tick"]()
            else:
                ns["send_gossip"](rng.choice(peers), some_ids())
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed64: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
