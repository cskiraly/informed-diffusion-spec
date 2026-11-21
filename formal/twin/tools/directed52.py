#!/usr/bin/env python3
"""Directed records for §5.2's announce, unpush, owe and note_push (protocol.md §5.2). The toy's own
functions are called in a toy node's namespace on generated states, and trace3.py's tracer logs each call with
the node's whole state.

    python3 directed52.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not (in the fifteen cells a queue never refuses an IHAVE, so announce
owes nothing; a push is unpushed outside the mesh twice in one cell; and no entry of `pushed` is there with no
bit when a push is noted, but for what unpush left):
- announce: an offer a full queue refuses, owed in its place (which no cell runs); nothing to offer
  (the bits pushed already, or held by the peer, or none given), where nothing is enqueued; a peer with no entry
  in `pushed` or in `peer_has`, with one of them, with both; bits of all three kinds in one call;
- unpush: an entry of `pushed` that is missing (it stays missing), that has the index (its last bit too: the
  entry stays, with its clock and ttl), that has not; a peer in the mesh (owed) and one outside it (not owed);
- owe: a peer with nothing owed (the row is made), with other groups owed, with this group owed: other bits, the
  same bits, no bits; and, as no cell has it, no bits to owe (the entry is made, empty);
- note_push: the first push (the clock set to now), a later one (the clock kept), one onto an entry left with no
  bit (the clock set again), an index pushed already; a ttl run down, set again.

The states are in the toy's own forms: an entry of `pushed` as note_push leaves it (bits, a clock, a ttl), one in
ten emptied as unpush can leave it; `peer_has` assigned as on_have does; `owed` rows in a drawn order of groups.
The scenario draws enqueue's refusals (a non-urgent entry refused in a quarter of the samples: the toy's own queue
has no limit); wake is the toy's own (the node's kick of its writer; no event runs here). The node is node 2 of a
5-node cell built as run.py builds it. A sample on which the Python raises is written with `raises` by the tracer;
the counts are printed.
"""
import argparse
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402

FNS = ["announce"] * 7 + ["unpush"] * 5 + ["owe"] * 3 + ["note_push"] * 5


class Scenario:
    refuse = False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed52", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    nd = got["sim"].nodes[2]
    ns = nd.ns
    sc = Scenario()

    def enqueue(p, x, urgent=False, own=ns["enqueue"]):             # the toy's own, but for the refusals drawn
        return False if sc.refuse and not urgent else own(p, x, urgent)
    ns["enqueue"] = enqueue
    tr.install(nd, ns)
    PUSH_TTL = int(ns["PUSH_TTL"])

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    raised, kinds = Counter(), Counter()
    for _ in range(a.n):
        what = rng.choice(FNS)
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 7))
        p = rng.choice(peers)
        g = rng.choice(groups)
        counts = {gg: rng.choice([4, 6, 8]) for gg in groups}
        n_ = counts[g]
        sc.refuse = rng.random() < 0.25

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
        nd.writer_kicked.clear()                # the toy's own wake: each sample's first kick of a peer is one
        ns["mesh"] = set(rng.sample(peers, rng.randrange(len(peers) + 1)))
        for q in peers:
            for gg in groups:
                c = counts[gg]
                if rng.random() < 0.45:             # assigned, as the toy's on_have does: the entry joins its map
                    h = ns["peer_has"][q][gg]
                    h.bits = B.Bits(rng.randrange(1 << c) if rng.random() < 0.85 else 0)
                    h.ttl = int(ns["HAVE_TTL"])
                if rng.random() < 0.45:
                    pe = ns["pushed"][q][gg]         # as note_push leaves it: a clock and a ttl with its bits; one in
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, 0.3, 1.0])   # ten with no bit left, as unpush
                    pe |= B.Bits(rng.randrange(1, 1 << c))                         # can leave it
                    if rng.random() < 0.1:
                        pe.v = 0
                    pe.ttl = rng.randrange(1, PUSH_TTL + 1)
            for gg in rng.sample(groups, rng.randrange(len(groups) + 1)):   # owed groups in a drawn order
                if rng.random() < 0.5:
                    ns["owed"][q][gg] = B.Bits(rng.randrange(1 << counts[gg]) if rng.random() < 0.9 else 0)
            if rng.random() < 0.4:
                ns["queue"][q].normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(
                    group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 1 << 4))))))

        # ---- the call
        there = g in ns["pushed"][p]
        pv = ns["pushed"][p][g].v if there else 0
        hv = ns["peer_has"][p][g].bits.v if g in ns["peer_has"][p] else 0
        try:
            if what == "announce":
                r = rng.random()
                if r < 0.08:
                    bits, kind = 0, "no bits"
                elif r < 0.25 and (pv | hv):
                    bits, kind = (pv | hv) & rng.randrange(1, 1 << n_), "bits pushed or held alone"
                else:
                    bits, kind = rng.randrange(1, 1 << n_), "bits drawn"
                kinds[f"announce: {kind}"] += 1
                ns["announce"](p, g, B.Bits(bits))
            elif what == "unpush":
                if pv and rng.random() < 0.65:
                    i = rng.choice([j for j in range(n_ + 2) if pv >> j & 1])
                else:
                    i = rng.randrange(n_)
                kinds["unpush: " + ("no entry" if not there else "its last bit" if pv == 1 << i else
                                    "a bit of several" if pv >> i & 1 else "a bit the entry has not")
                      + (", in the mesh" if p in ns["mesh"] else ", outside the mesh")] += 1
                ns["unpush"](p, g, i)
            elif what == "owe":
                ov = ns["owed"][p][g].v if p in ns["owed"] and g in ns["owed"][p] else None
                r = rng.random()
                if r < 0.07:
                    bits = 0
                elif r < 0.3 and ov:
                    bits = ov & rng.randrange(1, 1 << n_) or ov
                else:
                    bits = rng.randrange(1, 1 << n_)
                kinds["owe: " + ("no row" if p not in ns["owed"] else "no entry" if ov is None else
                                 "bits owed already" if bits and bits & ~ov == 0 else "an entry") +
                      ("" if bits else ", no bits")] += 1
                ns["owe"](p, g, B.Bits(bits))
            else:
                i = rng.randrange(n_)
                kinds["note_push: " + ("no entry" if not there else "an entry with no bit" if not pv else
                                       "an index pushed already" if pv >> i & 1 else "a later push")] += 1
                ns["note_push"](p, g, i)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed52: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, n in sorted(kinds.items()):
        print(f"  {k}: {n}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
