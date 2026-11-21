#!/usr/bin/env python3
"""Directed records for §4.1's on_frame and respond, and §4.5's on_iwant (protocol.md at
spec 34f60f8). The toy's own functions are called in two toy nodes' namespaces on generated states, and
trace3.py's tracer logs each call with the node's whole state.

    python3 directed41.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

Node 2 runs the document's on_iwant. Node 3 runs its own under that name (a node that withholds, or answers
whatever it holds without counting), so there on_frame's call of it is a call on the tape, and on_iwant has no
record.

What the records reach that the cells do not (in the cells an ask is by index, of a chunk the asker has not
claimed, served once; no queue refuses; a frame has one or two parts):
- on_iwant: ids under both forms of an ask key, one to five, a chunk asked twice in one IWANT (one answer, counted
  twice); a group expired; a chunk the asker claimed (penalised); nothing to answer with (a group dropped, a chunk
  not held); an id the asker does not want; an id served up to and beyond GOSSIP_RETRANSMISSION times;
- respond: asks and answers, none or some of each; the control alone, riding on the first of several answers; a
  queue that refuses (the answer owed), into a queue row there or made by the call;
- on_frame: frames with a chunk, an IHAVE, an IWANT and an IDONTWANT in any combination, among them the two whose
  order decides: an ask and a HAVE of one chunk from one peer (the ask is answered, then the claim is taken), and
  a chunk whose HAVE comes in the same frame; an empty frame;
- a frame's chunk: a duplicate accepted before (acknowledged), a duplicate rejected before, a group expired, a copy
  rejected (penalised), a copy accepted and stored, the K-th of them (the claim);
- **an IDONTWANT's entry that is no bitmap** (since v0.10.4; no cell sends one): a stock id of 20
  bytes, a structured id of 56 (a held chunk's, or one nobody holds), beside bitmaps and alone, one twice in a
  frame, one the peer said already, into a peer's set that is there and into one the call makes. Their counts are
  printed.

The scenario answers seen, accepted, mark_seen, expired, live, validate_chunk, authenticable, penalise, after,
start, forward, installed_block and content_id; the node's store (resolve, chunk_of, store), its enqueue (but for
the refusals drawn), valid_have, the draws and the rest are the toy's own. A sample on which the Python raises is
written with `raises` by the tracer; the counts are printed.
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
        self.seen, self.accepted, self.expired, self.auth = set(), set(), set(), set()
        self.verdict, self.refuse, self.withhold = None, False, False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed41", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
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
        ns["seen"] = lambda mid: mid in sc.seen
        ns["accepted"] = lambda mid: mid in sc.accepted
        ns["mark_seen"] = lambda mid: sc.seen.add(mid)
        ns["content_id"] = lambda f: f.cid
        ns["expired"] = lambda g: g in sc.expired
        ns["live"] = lambda slot: True
        ns["validate_chunk"] = lambda f: sc.verdict
        ns["authenticable"] = lambda g: g in sc.auth
        ns["penalise"] = lambda p: None
        ns["after"] = lambda delay, fn, *args: None
        ns["start"] = lambda fn, g: None
        ns["forward"] = lambda f, p: None
        ns["installed_block"] = lambda slot, root: types.SimpleNamespace(slot=slot, root=root)

        def enqueue(p, x, urgent=False, own=ns["enqueue"]):         # the toy's own, but for the refusals drawn
            return False if sc.refuse and not urgent else own(p, x, urgent)
        ns["enqueue"] = enqueue
        if k == 3:                      # this node's own function under the name; it counts nothing
            def on_iwant(p, iw, ns=ns):
                if sc.withhold:
                    return []
                out = []
                for b in iw.ids:
                    gi = ns["group_index"](b)
                    if gi.index in ns["chunks"][gi.group]:
                        out.append(ns["chunks"][gi.group][gi.index])
                return out
            ns["on_iwant"] = on_iwant
        tr.install(nd, ns)
        nodes[k] = (nd, ns)
    C = {k: nodes[2][1][k] for k in ("COLLECTING", "DECODING", "COMPLETE", "INVALID", "ACCEPT", "REJECT")}
    LIMIT = nodes[2][1]["GOSSIP_RETRANSMISSION"]

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised, idkinds = Counter(), Counter()
    STOCK = [bytes([0x22]) * 20, bytes([0x23]) * 20, bytes([0x24]) * 3]      # opaque ids: two of 20 bytes, one of 3
    for _ in range(a.n):
        what = rng.choice(["on_frame", "on_frame", "on_frame", "on_iwant", "on_iwant", "respond"])
        nd, ns = nodes[3 if what != "on_iwant" and rng.random() < 0.3 else 2]
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 6))
        p = rng.choice(peers)
        counts = {gg: rng.choice([4, 6]) for gg in groups}
        sc.__init__()
        sc.verdict = C["ACCEPT"]        # level 1's result where nothing else is drawn (a copy of a chunk not held)
        sc.expired = {gg for gg in groups if rng.random() < 0.12}
        sc.auth = {gg for gg in groups if rng.random() < 0.85}
        sc.refuse = rng.random() < 0.15
        sc.withhold = rng.random() < 0.5

        def chunk(gg, j, salt=7):
            cid = bytes([salt]) * 20
            return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, cid=cid,
                                         mid=gg + j.to_bytes(4, "little") + cid)

        def keys_of(gg, j):             # the two forms of a chunk's ask key
            return [Wm.WantIndex(gg, j), chunk(gg, j).mid]

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
        ns["mesh"] = set(rng.sample(peers, rng.choice([0, 1, len(peers)])))
        held = {}                       # the chunks this node holds
        for gg in groups:
            c = counts[gg]
            ns["desc"][gg] = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32,
                                                   count=c, segment_size=4, total_length=4 * (c // 2))
            ns["state"][gg] = rng.choice([C["COLLECTING"], C["COLLECTING"], C["COMPLETE"], C["INVALID"]])
            for j in rng.sample(range(c), rng.randrange(0, c // 2 + 1)):       # fewer than K: no claim made yet
                f = chunk(gg, j)
                held[(gg, j)] = f
                ns["chunks"][gg][j] = f
                ns["known_id"][gg][j] = f.mid
                ns["received"][gg].set(j)
                ns["mine"][gg].set(j)
                sc.seen.add(f.mid)
                sc.accepted.add(f.mid)
            for q in peers:
                if rng.random() < 0.3:          # what the peer claimed
                    e = ns["peer_has"][q][gg]
                    e.bits = B.Bits(rng.randrange(1 << c))
                    e.ttl = 3
                    for j in range(c):
                        if e.bits.has(j):
                            ns["holders"][gg][j].add(q)
        for (gg, j), f in held.items():
            for q in peers:
                r = rng.random()
                if r < 0.15:
                    ns["unwanted"][q].add(f.mid)
                elif r < 0.5:
                    ns["serve_count"][q][f.mid] = rng.choice([1, LIMIT - 1, LIMIT, LIMIT + 1])
        for q in peers:                         # (v0.10.4) a stock id the peer said already
            if rng.random() < 0.2:
                ns["unwanted"][q].add(rng.choice(STOCK))
        for q in peers:
            if rng.random() < 0.4:              # a queue row there, with control in its normal lane
                ns["queue"][q].normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(
                    group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 16))))))

        def some_chunk():               # a held chunk, more often than chance; or any
            if held and rng.random() < 0.7:
                return rng.choice(sorted(held))
            gg = rng.choice(groups)
            return gg, rng.randrange(counts[gg])

        def asks():
            ids = [rng.choice(keys_of(*some_chunk())) for _ in range(rng.randrange(1, 6))]
            if rng.random() < 0.25:
                ids.append(rng.choice(keys_of(ids[0].group, ids[0].index)
                                      if isinstance(ids[0], Wm.WantIndex) else [ids[0]]))    # one twice
            return ids

        # ---- the call
        try:
            if what == "on_iwant":
                ns["on_iwant"](p, types.SimpleNamespace(ids=asks()))
            elif what == "respond":
                ans = [held[k] for k in rng.sample(sorted(held), min(len(held), rng.choice([0, 0, 1, 3])))]
                want = [Wm.WantIndex(*some_chunk()) for _ in range(rng.choice([0, 0, 1, 2]))]
                ns["respond"](p, want, ans, [])
            else:
                parts = []
                f = None
                r = rng.random()
                gg, j = some_chunk()
                if r < 0.2:                                     # a copy of a chunk held: a duplicate
                    f = held.get((gg, j)) or chunk(gg, j)
                elif r < 0.5:                                   # a new chunk
                    free = [(x, y) for x in groups for y in range(counts[x]) if (x, y) not in held]
                    gg, j = rng.choice(free)
                    f = chunk(gg, j, salt=rng.choice([7, 7, 7, 9]))
                    sc.verdict = rng.choice([C["ACCEPT"], C["ACCEPT"], C["ACCEPT"], C["REJECT"]])
                    if rng.random() < 0.15:
                        sc.seen.add(f.mid)                      # rejected before: seen, and not accepted
                if rng.random() < 0.4:                          # an IHAVE: a bitmap of a group
                    hg = rng.choice(groups)
                    parts.append(Wm.IHAVE(Wm.HaveBitmap(group=hg, bits=B.Bits(rng.randrange(1, 1 << counts[hg])))))
                iw = None
                if rng.random() < 0.5:
                    iw = asks()
                    parts.append(Wm.IWANT(iw))
                if rng.random() < 0.5:                          # an IDONTWANT: HAVEs
                    r = rng.random()
                    if iw is not None and r < 0.5:              # of a chunk asked in this frame
                        b = iw[0]
                        hg, hj = (b.group, b.index) if isinstance(b, Wm.WantIndex) else (b[:32], int.from_bytes(b[32:36], "little"))
                        bits = 1 << hj
                    elif f is not None and r < 0.8:             # of the frame's own chunk
                        hg, bits = f.group, 1 << f.index
                    else:
                        hg = rng.choice(groups)
                        bits = rng.randrange(1, 1 << counts[hg])
                    hs = [Wm.HaveBitmap(group=hg, bits=B.Bits(bits))]
                    if rng.random() < 0.3:
                        og = rng.choice(groups)
                        hs.append(Wm.HaveBitmap(group=og, bits=B.Bits(rng.randrange(1, 1 << counts[og]))))
                    # (v0.10.4) entries that are no bitmap: opaque ids, kept in unwanted[p] (§4.1)
                    r = rng.random()
                    if r < 0.45:
                        ids = []
                        for _ in range(rng.choice([1, 1, 2, 3])):
                            k = rng.random()
                            ids.append(rng.choice(STOCK) if k < 0.5
                                       else held[rng.choice(sorted(held))].mid if held and k < 0.8
                                       else chunk(*some_chunk(), salt=9).mid)
                        if rng.random() < 0.2:
                            ids.append(ids[0])                  # one twice in a frame
                        if r < 0.08:
                            hs = []                             # ids alone
                        for x in ids:
                            hs.insert(rng.randrange(len(hs) + 1), x)
                        was = set(ns["unwanted"].get(p, ()))
                        idkinds["frames with an id in their IDONTWANT"] += 1
                        idkinds["  ids alone, no bitmap"] += not any(Wm.is_have_bitmap(h) for h in hs)
                        idkinds["  an id twice in the frame"] += len(set(ids)) < len(ids)
                        idkinds["  an id the peer said already"] += any(x in was for x in ids)
                        idkinds["  into a set that is there"] += bool(was)
                        idkinds["  into a set the call makes"] += not was
                        idkinds["  a structured id (56 bytes)"] += any(len(x) == 56 for x in ids)
                        idkinds["  a stock id (20 bytes)"] += any(len(x) == 20 for x in ids)
                        idkinds["  an id of 3 bytes"] += any(len(x) == 3 for x in ids)
                    parts.append(Wm.IDONTWANT(hs))
                control = None
                for c_ in parts:
                    control = c_ if control is None else control + c_
                ns["on_frame"](p, Wm.Frame(Wm.Entry(chunk=f, control=control)))
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed41: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, v in idkinds.items():
        print(f"  {k}: {v}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
