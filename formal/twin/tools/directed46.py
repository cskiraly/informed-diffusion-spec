#!/usr/bin/env python3
"""Directed records for §4.6's claim_group and drop_group (protocol.md §4.6), called
directly. The toy's own functions are called in a toy node's namespace on generated states, and trace3.py's
tracer logs each call with the node's whole state.

    python3 directed46.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells and the other sets do not (in the cells and in directed42 a claim comes
through on_validated, at the K-th chunk, with `mine` short of all bits; no cell drops a group):
- claim_group of a group whose count is 4, 6 or 8 chunks, with `mine` empty, partial and full already; `stop_pull`
  set already, and not;
- the mesh empty, one peer, several, in the set's own order: a HAVE to each, of bits it was sent already (nothing
  enqueued) and of new ones, into a queue there and into one the call makes;
- promises of the group's chunks under both forms of an ask key, to several peers, closed by the node's
  `close_promises_of_group`, with promises of other groups, which stay;
- drop_group: the group's state set INVALID from any state, or from none; `stop_pull` set; what is owed of it
  and its owed answers dropped; its ids out of the gossip history; and, as the toy's helpers do since v0.10.4
  (spec 34f60f8): the group's chunks, IHAVEs and IWANTs taken out of both lanes of every queue (an entry goes only
  once nothing else is left of it: a chunk with another group's offer beside it stays as the offer; a HAVE of the
  group stays), and its ids out of every paced job (a job that named it alone goes, an empty one stays).

The node's own helpers run (`close_promises_of_group`, `discard_queued`, `discard_paced`): each is a call on the
tape with its log. The node is node 2 of a 5-node cell built as run.py builds it (no event runs). A sample on
which the Python raises is written with `raises` by the tracer; the counts are printed.
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
    tr = trace3.Tracer3(toy, a.out, ["directed46", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
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
    C = {k: ns[k] for k in ("COLLECTING", "DECODING", "COMPLETE", "INVALID")}

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised = Counter()
    for _ in range(a.n):
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 7))
        g = rng.choice(groups)
        counts = {gg: rng.choice([4, 6, 8]) for gg in groups}     # N of each group: its descriptor's count

        def fid(gg, j, salt=7):
            return gg + j.to_bytes(4, "little") + bytes([salt]) * 20

        def keys_of(gg, j):             # the two forms of a chunk's ask key
            return [Wm.WantIndex(gg, j), fid(gg, j)]

        def chunk(gg, j):
            return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, mid=fid(gg, j))

        def some_chunk():               # of the group in hand, more often than chance
            gg = g if rng.random() < 0.6 else rng.choice(groups)
            return gg, rng.randrange(counts[gg])

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
        ns["mesh"] = set(rng.sample(peers, rng.choice([0, 1, 2, len(peers)])))
        for gg in groups:
            n_ = counts[gg]
            ns["desc"][gg] = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32,
                                                   count=n_, segment_size=8, total_length=4 * n_)
            r = rng.random()
            if r < 0.8:
                ns["state"][gg] = rng.choice(list(C.values()))
            if rng.random() < 0.2:
                ns["stop_pull"][gg] = True
            r = rng.random()
            if r < 0.6:
                ns["mine"][gg] = B.Bits(rng.randrange(1, 1 << n_) if r < 0.45 else (1 << n_) - 1)
            if rng.random() < 0.3:
                ns["origin"][gg] = B.Bits(rng.randrange(1 << n_))
            for q in peers:
                if rng.random() < 0.3:          # a HAVE sent already: of some bits, or of all
                    ns["sent_to"][q][gg] = B.Bits(rng.randrange(1, 1 << n_) if rng.random() < 0.6 else (1 << n_) - 1)
                if rng.random() < 0.25:
                    ns["owed"][q][gg] = B.Bits(rng.randrange(1, 1 << n_))
                if rng.random() < 0.2:
                    ns["owed_answers"][q][gg].set(rng.randrange(n_))
            for j in rng.sample(range(n_), rng.randrange(0, 3)):      # the gossip history's ids
                ns["gossip_history"].windows[rng.randrange(0, 3)].append(fid(gg, j))
        for _ in range(rng.randrange(0, 6)):                    # promises and tries, with the toy's index of keys
            gg, j = some_chunk()
            b = rng.choice(keys_of(gg, j))
            nd._by_index.setdefault((gg, j), set()).add(b)
            for q in rng.sample(peers, rng.randrange(1, 3)):
                ns["tried"][b][q] = 0.5
                if rng.random() < 0.8:
                    ns["promises"][(b, q)] = 0.5
        for q in peers:
            r = rng.random()
            if r < 0.4:
                continue                                        # no queue of the peer's
            pq = ns["queue"][q]
            for _ in range(rng.randrange(0, 4)):                # the normal lane: chunks of g and of others, control
                if rng.random() < 0.7:
                    pq.normal.append(Wm.Entry(chunk=chunk(*some_chunk()), solicited=rng.random() < 0.4))
                else:
                    gg, j = some_chunk()
                    pq.normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(group=gg, bits=B.Bits(1 << j)))))
            if rng.random() < 0.3:                              # the urgent lane: a chunk of g (it leaves too, since
                pq.urgent.append(Wm.Entry(chunk=chunk(g, rng.randrange(counts[g])), solicited=True))    # v0.10.4)
            # v0.10.4's discard_queued: g's IHAVEs and IWANTs leave both lanes too, an entry only once nothing else
            # is left of it, and a HAVE of g stays (§4.6, §8.1). So, in either lane: an IHAVE of several bitmaps, an
            # IWANT of asks in both forms, a chunk with an offer beside it, a HAVE of g
            for lane in (pq.normal, pq.urgent):
                for _ in range(rng.randrange(0, 3)):
                    r = rng.random()
                    if r < 0.35:
                        hs = [Wm.HaveBitmap(group=gg, bits=B.Bits(1 << j))
                              for gg, j in [some_chunk() for _ in range(rng.randrange(1, 4))]]
                        lane.append(Wm.Entry(control=Wm.IHAVE(hs)))
                    elif r < 0.7:
                        ks = [rng.choice(keys_of(*some_chunk())) for _ in range(rng.randrange(1, 4))]
                        lane.append(Wm.Entry(control=Wm.IWANT(ks)))
                    elif r < 0.85:
                        (gg, j), (g2, j2) = some_chunk(), some_chunk()
                        lane.append(Wm.Entry(chunk=chunk(gg, j), solicited=rng.random() < 0.5,
                                             control=Wm.IHAVE(Wm.HaveBitmap(group=g2, bits=B.Bits(1 << j2)))))
                    else:
                        lane.append(Wm.Entry(control=Wm.IDONTWANT(
                            Wm.HaveBitmap(group=g, bits=B.Bits(rng.randrange(1, 1 << counts[g]))))))
        # v0.10.4's discard_paced: g's ids leave every paced job (§6.4), a job that named g alone goes, and one
        # that was empty already stays. Jobs of g alone, of g and others, of others, and of no id
        for _ in range(rng.randrange(0, 4)):
            r = rng.random()
            ids = ([] if r < 0.15 else [fid(g, rng.randrange(counts[g])) for _ in range(rng.randrange(1, 3))] if r < 0.4
                   else [fid(*some_chunk()) for _ in range(rng.randrange(1, 4))])
            ns["pace_queue"].append((rng.choice(peers), ids, ns["now"] + rng.choice([0.0, 0.1])))

        # ---- the call
        try:
            ns[rng.choice(["claim_group", "drop_group"])](g)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed46: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
