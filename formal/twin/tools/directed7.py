#!/usr/bin/env python3
"""Directed records for §7.2's writer. The toy's own next_to_send, filter_entry, with_owed and projected are
called in a toy node's namespace on generated states. What they ask of the rest of the node is answered by the
scenario, and trace3.py's tracer logs each call with the node's whole state.

    python3 directed7.py TOYDIR OUT.jsonl.gz [--n N] [--seed S] [--cards on|off] [--source-offers publish]

With `--source-offers publish` (directed7p) the node's SOURCE_OFFERS is PUBLISH, a constant of the trace as the
cards are: next_to_send then calls origin_written (§5.1) for a chunk that leaves, and the run draws `origin` (a
group the node publishes, with the chunk's bit there or not) and calls origin_written by itself too (nothing
untraced calls it). Its draws come after the others', and only in that run: directed7's and directed7u's records
are as without it.

The cards (CANCEL [c8], PROJECT [c12], RAREST [c9]) are constants of a trace, read once, so they are fixed per run:
on (directed7) and off (directed7u). What the records reach that the cells may not:
- next_to_send:
  - owed answers queued (has_room true) and not (false), one to four, in half held by the peer, with the toy's own
    pop_owed_answer;
  - the urgent lane first, with up to three entries; nothing to send; owed offers alone;
  - a slot taken, and the writer in line (WAIT): by §7.1's own code on a drawn window (W is 2; the count at 0 to
    3; the line empty, with the peer first, with another first; a send of a queued chunk still in flight, so that
    its second copy gives the slot back at once);
  - an entry left empty, so that the loop turns again;
  - rarest over chunks behind a control-only entry, and holders drawn to tie;
- filter_entry:
  - cancel; projection with the toy's own unpush, to a peer in the mesh and not; a chunk sent;
  - an answer never projected away;
  - an IWANT's asks dropped for each of their four reasons, and kept, with a promise there already and not;
- with_owed: owed offers minus what was pushed and what the peer claimed, the carried chunk's index taken out,
  groups owed in a drawn order;
- projected at, under and over K.
The orders are drawn: a peer's owed groups in a drawn order, the lanes' entries in a drawn order.

The scenario answers expired, live, has_room, after, connected_topic_peers and listed. §7.1's acquire_slot,
release_unused_slot, track_in_flight and free_slot are the document's, the twin's own; `wake` is the toy's own,
on the tape. The toy's own pop_owed_answer and unpush (§5.2, with its owe) run: their writes of the twin's tables
(owed_answers, owed) are their `cr` and `cw` on the tape. enqueue is the toy's own in a share of the samples (an
owed answer then lands in the normal lane), and the scenario's otherwise.

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

FNS = ["next_to_send"] * 8 + ["filter_entry"] * 3 + ["with_owed"] * 2 + ["projected"] * 2


class Scenario:
    def __init__(self):
        self.expired, self.dead = set(), set()
        self.room, self.acquire, self.admit, self.own_enqueue = True, True, True, False
        self.peers, self.listed = [], {}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cards", choices=("on", "off"), default="on")
    ap.add_argument("--source-offers", choices=("ack", "publish"), default="ack")
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    publish = a.source_offers == "publish"
    tr = trace3.Tracer3(toy, a.out, ["directed7", f"--n={a.n}", f"--seed={a.seed}", f"--cards={a.cards}"]
                        + (["--source-offers=publish"] if publish else []), whole=True)
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
    on = a.cards == "on"
    for card in ("CANCEL", "PROJECT", "RAREST"):
        ns[card] = on                   # before the tracer installs: the trace's constants are read then
    if publish:
        ns["SOURCE_OFFERS"] = ns["PUBLISH"]
    kinds = Counter()
    ns["expired"] = lambda g: g in sc.expired
    ns["live"] = lambda slot: slot not in sc.dead
    ns["has_room"] = lambda p: sc.room
    ns["W"] = 2                         # the window: §7.1's own code runs on a drawn count and line
    ns["after"] = lambda delay, fn, *args: None
    ns["connected_topic_peers"] = lambda: list(sc.peers)
    ns["listed"] = lambda p: sc.listed.get(p, 0)
    own_enqueue = ns["enqueue"]
    ns["enqueue"] = lambda p, x, urgent=False: own_enqueue(p, x, urgent) if sc.own_enqueue else sc.admit
    tr.install(nd, ns)

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised = Counter()
    for _ in range(a.n):
        n_ = rng.choice([3, 4, 6])
        k_ = rng.randrange(1, n_ + 1)
        d = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32, count=n_, total_length=4 * k_,     # N(d) = n_, K(d) = k_;
                                  segment_size=4)                                   #   a whole descriptor
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 6))

        def chunk(gg, j):
            return types.SimpleNamespace(slot=1, beacon_block_root=root, group=gg, index=j, descriptor=d,
                                         mid=gg + j.to_bytes(4, "little") + bytes([7]) * 20)

        def iwant():
            ids = []
            for _ in range(rng.randrange(1, 4)):
                gg, j = rng.choice(groups), rng.randrange(n_)
                ids.append(Wm.WantIndex(gg, j) if rng.random() < 0.7 else chunk(gg, j).mid)
            return Wm.IWANT(ids)

        def entry():
            r = rng.random()
            if r < 0.45:                # a chunk: a push or an answer, now and then with control riding on it
                e = Wm.Entry(chunk=chunk(rng.choice(groups), rng.randrange(n_)), solicited=rng.random() < 0.4)
                if rng.random() < 0.2:
                    e.control = iwant()
                return e
            if r < 0.8:                 # an IWANT
                return Wm.Entry(control=iwant())
            if r < 0.9:                 # an IHAVE of a bitmap
                return Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(group=rng.choice(groups), bits=B.Bits(rng.randrange(1, 1 << n_)))))
            return Wm.Entry(control=Wm.IWANT([]))      # an IWANT left with no asks: an empty entry

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "desc", "received", "state", "origin", "pending_ids",
                     "pending", "chunks", "tie_slot", "owed", "owed_answers", "sent_to", "slot_held", "peer_has",
                     "pushed", "holders", "sent"):
            ns[name].clear()
        ns["waiters"].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        sc.__init__()
        sc.peers = list(peers)
        sc.listed = {q: rng.choice([0, 3, 256]) for q in peers}
        sc.room = rng.random() < 0.8
        count = rng.choice([0, 0, 0, 1, 1, 2, 2, 3])            # the window's count, behind the tracer's
        ns["in_flight"]._h.count = count                        #   cell (no record is open); W is 2
        sc.admit = rng.random() < 0.9
        sc.own_enqueue = rng.random() < 0.6
        ns["mesh"] = set(rng.sample(peers, rng.randrange(len(peers) + 1)))
        p = rng.choice(peers)
        for gg in groups:
            if rng.random() < 0.8:
                ns["desc"][gg] = d
            if rng.random() < 0.1:
                sc.expired.add(gg)
            if rng.random() < 0.1:
                ns["stop_pull"][gg] = True
            if rng.random() < 0.5:
                ns["mine"][gg] = B.Bits(rng.randrange(1 << n_))
            for q in peers:
                if rng.random() < 0.4:          # assigned, as the toy's on_have does: a HaveEntry joins its map
                    h = ns["peer_has"][q][gg]       #   on an attribute's assignment (bits.py's _Lazy), not on a bit
                    h.bits = B.Bits(h.bits.v | (1 << rng.randrange(n_)))   # set in its bitmap
                if rng.random() < 0.3:
                    pe = ns["pushed"][q][gg]         # as note_push leaves it: a clock and a ttl with its bits (`pushed`
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, 0.3, 1.0])     # the twin's own); one in
                    pe |= B.Bits(1 << rng.randrange(n_))                 # ten with no bit left, as unpush can leave it
                    if rng.random() < 0.1:
                        pe.v = 0
                    pe.ttl = rng.randrange(1, int(ns["PUSH_TTL"]) + 1)
                if rng.random() < 0.3:
                    ns["sent_to"][q][gg].set(rng.randrange(n_))
            for j in range(n_):
                for q in rng.sample(peers, rng.randrange(0, 3)):
                    ns["holders"][gg][j].add(q)
        for gg in rng.sample(groups, rng.randrange(len(groups) + 1)):   # owed groups in a drawn order
            r = rng.random()
            if r < 0.85:
                ns["owed"][p][gg] = B.Bits(rng.randrange(1, 1 << n_))
            else:
                ns["owed"][p][gg] = B.Bits(0)           # a group owed with no bits: there, and nothing to send
        if rng.random() < 0.3:                          # owed answers, their chunks stored: one to four. In
            held = rng.random() < 0.5                   #   half, each held by the peer, so that CANCEL empties
            for _ in range(rng.choice([1, 2, 3, 4])):   #   its entry and the loop turns again
                gg, j = rng.choice(groups), rng.randrange(n_)
                ns["chunks"][gg][j] = chunk(gg, j)
                ns["owed_answers"][p][gg].set(j)
                if held:
                    h = ns["peer_has"][p][gg]
                    h.bits = B.Bits(h.bits.v | (1 << j))
        if rng.random() < 0.5:
            ns["slot_held"][p] = rng.random() < 0.5
        for _ in range(rng.randrange(0, 3)):            # promises there already
            ns["promises"][(Wm.WantIndex(rng.choice(groups), rng.randrange(n_)), p)] = 0.5
        if rng.random() < 0.15:                         # a tie of p, so that an ask to it is dropped
            ns["tied"][root][p][rng.choice(groups)].set(rng.randrange(n_))
        q = ns["queue"][p]
        r = rng.random()                                # up to three urgent entries, each its own bit, so that the
        for k in range(0 if r < 0.65 else 1 if r < 0.85 else 2 if r < 0.95 else 3):    # first is told from the last
            q.urgent.append(Wm.Entry(control=Wm.IDONTWANT(Wm.HaveBitmap(group=rng.choice(groups), bits=B.Bits(1 << k)))))
        for _ in range(rng.randrange(0, 5)):
            q.normal.append(entry())
        r = rng.random()                                # the line: empty, the peer first, another first
        line = ([] if r < 0.5 else [p] + rng.sample([x for x in peers if x != p], rng.randrange(0, 2)) if r < 0.75
                else rng.sample(peers, rng.randrange(1, len(peers) + 1)))
        ns["waiters"].extend(line)
        for e in q.normal:                              # a send of a queued chunk still in flight (a second copy)
            if e.chunk is not None and rng.random() < 0.15:
                ns["sent"][(p, e.chunk.group, e.chunk.index)] = ns["now"] - 0.2

        if publish:                     # `origin`: the groups this node publishes, each with some bits
            for gg in groups:           #   acknowledged or written; none, some or all of them
                if rng.random() < 0.6:
                    ns["origin"][gg] = B.Bits(rng.choice([0, rng.randrange(1 << n_), (1 << n_) - 1]))
        before = {gg: b.v for gg, b in ns["origin"].items()} if publish else None     # (the recorder is off)

        # ---- the call
        fn = rng.choice(FNS + ["origin_written"] * 3) if publish else rng.choice(FNS)
        if fn == "origin_written":
            f = chunk(rng.choice(groups), rng.randrange(n_))
            args = (f,)
            kinds["origin_written alone: " + ("not a group we publish" if f.group not in before else
                                              "the bit there already" if before[f.group] >> f.index & 1 else
                                              "the HAVE grows" + (", no mesh" if not ns["mesh"] else ""))] += 1
        elif fn == "next_to_send":
            args = (p,)
        elif fn in ("filter_entry", "with_owed"):
            args = (p, entry())
        else:
            args = (p, rng.choice(groups))
        try:
            ns[fn](*args)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
        if publish and fn == "next_to_send":
            after = {gg: b.v for gg, b in ns["origin"].items()}
            kinds["next_to_send: " + ("origin grew" if after != before else "origin as it was")] += 1
    tr.close()
    print(f"directed7: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, v in sorted(kinds.items()):
        print(f"  {k}: {v}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
