#!/usr/bin/env python3
"""Directed records for §4.2's deferral path. The toy's own defer, tie, tie_room, on_block_installed, drop_tie
and drop_stale_waits, and on_chunk and on_validated where they reach it, are called in a toy node's namespace on
generated states. What they ask of the rest of the node is answered by the scenario, and trace3.py's tracer logs
each call with the node's whole state (as directed42.py does for the rest of §4.2).

    python3 directed4b.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What they reach that the cells and directed42.py do not:
- tie_room's four ways out, under a limit: MAX_PENDING_GROUPS is 3 here (directed42.py and the cells run without
  one). An index at or beyond MAX_PLAIN_CHUNKS; one beyond a known count; a root and group tied already; room for
  another, and no room;
- on_block_installed:
  - copies waiting under the root, and none;
  - a bid that commits the tie's group (the ties released), another group (drop_tie, with authenticable true and
    false), and a tie's group expired;
  - parks lifted; asked_parked's sets with the peer and without;
  - an index beyond a count learnt meanwhile; an index held, and not;
  - ledger(g0)'s retries;
- drop_stale_waits:
  - several roots waiting, in a drawn order; copies stale by expiry, stale by the window, and fresh;
  - several (root, peer) ties, in a drawn order; groups stale and fresh;
  - a peer's row emptied and popped, a root's row emptied and popped;
  - a tie whose row is missing, a row there and empty;
- defer, tie and drop_tie alone;
- the deferral's depth reached and not passed: a copy deferred, its block installed, deferred again, then
  accepted (the scenario's validate_chunk answers DEFER, DEFER, then ACCEPT for one copy), never deeper;
- the orders: `tied` with several roots, peers and groups, and `pending` and `tie_slot` with several entries, all
  put in a drawn order. The peers are drawn from 1 to 63, so a set or dict of them is often not sorted.
Not drawn: a bid that commits no group (a block of columns), since no record can hold ledger(None)'s reads.

The scenario answers seen, accepted, mark_seen, expired, live, validate_chunk, penalise, enqueue, after, start,
forward, connected_topic_peers, own_order, listed and authenticable, and the deferral path's installed_block (a
block or nothing), admitted, reserve, release and bid_group. The toy's own open_group, store, claim_group and
drop_offer run: drop_offer's reads and writes of the twin's tables are its `cr` and `cw` on the tape, and a
queue row it makes is written whole.

As in directed42.py, the states are drawn without the document's invariants: ties of indices a group has not,
a tie_slot pair with no row in `tied`, waits whose ids are not all in `pending_ids`, extra ids there. One rule is
kept, because the tracer checks it: no (peer, chunk) waits twice under one root, by construction.

The node is node 2 of a 5-node cell built as run.py builds it (no event runs). A sample on which the Python raises is
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

FNS = (["on_block_installed"] * 8 + ["drop_stale_waits"] * 8 + ["tie"] * 3 + ["tie_room"] * 3 + ["defer"] * 3
       + ["drop_tie"] * 2 + ["on_chunk"] * 2 + ["on_validated"])
LIMIT = 3                               # MAX_PENDING_GROUPS here


class Scenario:
    def __init__(self):
        self.seen, self.accepted, self.expired, self.dead, self.auth = set(), set(), set(), set(), set()
        self.vseq = {}                  # a copy's id -> validate_chunk's answers, in order; then ACCEPT
        self.installed = set()          # the roots whose block is installed
        self.admitted, self.reserve, self.admit = True, True, True
        self.bid = {}                   # root -> the group its bid commits
        self.peers, self.rank, self.listed = [], {}, {}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed4b", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
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
    C = {k: ns[k] for k in ("COLLECTING", "DECODING", "COMPLETE", "INVALID", "ACCEPT", "REJECT", "DEFER")}

    def validate_chunk(f):
        q = sc.vseq.get(f.mid)
        return q.pop(0) if q else C["ACCEPT"]

    ns["seen"] = lambda mid: mid in sc.seen
    ns["accepted"] = lambda mid: mid in sc.accepted
    ns["mark_seen"] = lambda mid: sc.seen.add(mid)
    # a chunk's content id is the scenario's, the part of its id after group and index (`cid`), so that the id
    # each chunk carries is the document's message_id of it in this namespace
    ns["content_id"] = lambda f: f.cid
    ns["expired"] = lambda g: g in sc.expired
    ns["live"] = lambda slot: slot not in sc.dead
    ns["validate_chunk"] = validate_chunk
    ns["penalise"] = lambda p: None
    ns["enqueue"] = lambda p, x, urgent=False: sc.admit
    ns["after"] = lambda delay, fn, *args: None
    ns["start"] = lambda fn, g: None
    ns["forward"] = lambda f, p: None
    ns["connected_topic_peers"] = lambda: list(sc.peers)
    ns["own_order"] = lambda xs, a: sorted(xs, key=lambda q: sc.rank[q])     # this sample's order, the same at each ask
    ns["listed"] = lambda p: sc.listed.get(p, 0)
    ns["authenticable"] = lambda g: g in sc.auth
    # the block or nothing, as §8's interface has it
    ns["installed_block"] = lambda slot, root: (types.SimpleNamespace(slot=slot, root=root) if root in sc.installed
                                                else None)
    ns["admitted"] = lambda p, f: sc.admitted
    ns["reserve"] = lambda p, f: sc.reserve
    ns["release"] = lambda p, f: None
    ns["bid_group"] = lambda root: sc.bid[root]
    ns["MAX_PENDING_GROUPS"] = LIMIT    # before the tracer installs: the trace's constants are read then
    tr.install(nd, ns)

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    roots = [bytes([0xa1 + j]) * 32 for j in range(3)]
    raised = Counter()
    for _ in range(a.n):
        n_ = rng.choice([2, 3, 4])
        k_ = rng.randrange(1, n_ + 1)
        d = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32, count=n_, total_length=4 * k_,     # N(d) = n_, K(d) = k_;
                                  segment_size=4)                                   #   a whole descriptor
        now = rng.choice([1.0, 3.25])
        ns["now"] = now
        times = [now - x for x in (0.05, 0.3, 0.6)]
        peers = rng.sample(range(1, 64), rng.randrange(2, 7))     # a set or dict of them iterates in hash order
        js = list(range(n_ + 2))        # indices below N, at it and beyond it

        def fid(gg, j, salt):
            return gg + j.to_bytes(4, "little") + bytes([salt]) * 20

        def chunk(gg, j, slot, root):
            c = types.SimpleNamespace(slot=slot, beacon_block_root=root, group=gg, index=j, descriptor=d,
                                      mid=fid(gg, j, rng.randrange(256)))
            c.cid = c.mid[36:]          # its content id: what `content_id(f)` answers here
            return c

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        sc.__init__()
        sc.peers = list(peers)
        sc.rank = {q: rng.random() for q in peers}
        sc.listed = {q: rng.choice([0, 0, 3, 256]) for q in peers}
        sc.admit = rng.random() < 0.9
        sc.admitted = rng.random() < 0.85
        sc.reserve = rng.random() < 0.7
        ns["mesh"] = set(rng.sample(peers, rng.randrange(len(peers) + 1)))
        for gg in groups:
            if rng.random() < 0.5:
                ns["desc"][gg] = d                              # a count known (learnt meanwhile, for a tie)
            if rng.random() < 0.25:
                sc.expired.add(gg)
            if rng.random() < 0.5:
                sc.auth.add(gg)
            if rng.random() < 0.15:
                ns["stop_pull"][gg] = True
            r = rng.random()
            if r < 0.15:
                ns["mine"][gg] = B.Bits((1 << n_) - 1)          # everything held
            elif r < 0.7:
                ns["mine"][gg] = B.Bits(rng.randrange(1 << n_))
            if rng.random() < 0.3:
                ns["state"][gg] = C["COLLECTING"]
                ns["received"][gg] = B.Bits(rng.randrange(1 << n_))
        for slot in (1, 2):
            if rng.random() < 0.2:
                sc.dead.add(slot)
        for rr in roots:
            sc.bid[rr] = rng.choice(groups)                     # never none: a block of columns is not drawn
            if rng.random() < 0.5:
                sc.installed.add(rr)
        # offers, so that ledger and retry_offer find announcers; known ids under some indices
        for gg in groups:
            for q in peers:
                if rng.random() < 0.3:
                    ns["offered"][q][gg] = B.Bits(rng.randrange(1, 1 << (n_ + 2)))
            for j in js:
                if rng.random() < 0.15:
                    ns["known_id"][gg][j] = fid(gg, j, 9)
                b = Wm.WantIndex(gg, j)
                if rng.random() < 0.15:
                    for q in rng.sample(peers, rng.randrange(1, len(peers) + 1)):
                        ns["offers"][b].append(q)
                    nd._by_index.setdefault((gg, j), set()).add(b)
                if rng.random() < 0.1:
                    ns["asked_at"][b] = rng.choice(times)
                    nd._by_index.setdefault((gg, j), set()).add(b)
                if rng.random() < 0.15:
                    ns["asked_parked"][(gg, j)] = set(rng.sample(peers, rng.randrange(1, len(peers) + 1)))
        for q in peers:
            for gg in groups:
                if rng.random() < 0.15:
                    ns["park"][q][gg] = now + 10
        # tied: roots, peers and groups in drawn orders; rows there and empty at each level; tie_slot beside it,
        # now and then missing for a tied pair, or there for a pair with no row
        for rr in rng.sample(roots, rng.randrange(len(roots) + 1)):
            for q in rng.sample(peers, rng.randrange(1, len(peers) + 1)):
                r = rng.random()
                if r < 0.75:
                    for gg in rng.sample(groups, rng.randrange(1, 3)):
                        for _ in range(rng.randrange(1, 3)):
                            ns["tied"][rr][q][gg].set(rng.choice(js))
                elif r < 0.85:
                    row = ns["tied"][rr][q]                     # a peer's row there and empty
                    row[groups[0]].set(0)
                    row.pop(groups[0])
                else:
                    b = ns["tied"][rr][q][groups[1]]            # a bitmap there and empty
                    b.set(0)
                    b.clear(0)
                if rng.random() < 0.9:
                    ns["tie_slot"][(rr, q)] = rng.choice([1, 2])
            if rng.random() < 0.1:                              # a root's row there and empty
                q = rng.choice(peers)
                if q not in ns["tied"][rr]:
                    ns["tied"][rr][q][groups[2]].set(0)
                    ns["tied"][rr].pop(q)
        if rng.random() < 0.2:                                  # a pair with a slot and no row
            rr, q = rng.choice(roots), rng.choice(peers)
            if q not in ns["tied"].get(rr, {}):
                ns["tie_slot"][(rr, q)] = rng.choice([1, 2])
        # pending: roots in a drawn order, each with waits of distinct copies, their ids in pending_ids, now and then
        # one left out of it; and an id there of no wait
        for rr in rng.sample(roots, rng.randrange(len(roots) + 1)):
            waits = set()                       # (peer, id) once under a root, by construction
            for _ in range(rng.randrange(1, 4)):
                f = chunk(rng.choice(groups), rng.choice(js), rng.choice([1, 2]), rr)
                q = rng.choice(peers)
                if (q, f.mid) in waits:
                    continue
                waits.add((q, f.mid))
                ns["pending"][rr].append((q, f))
                if rng.random() < 0.9:
                    ns["pending_ids"].add(f.mid)
                if rng.random() < 0.2:
                    sc.vseq[f.mid] = [rng.choice([C["REJECT"], C["DEFER"]])]   # at most one DEFER: deferral's depth
        if rng.random() < 0.2:
            ns["pending_ids"].add(fid(rng.choice(groups), 1, 255))

        # ---- the call
        fn = rng.choice(FNS)
        p = rng.choice(peers) if rng.random() < 0.85 else rng.choice([q for q in range(1, 64) if q not in peers])
        root = rng.choice(roots)
        g = rng.choice(groups)
        r = rng.random()
        i = rng.choice(js) if r < 0.85 else rng.choice([8191, 8192, 9000])   # at or beyond MAX_PLAIN_CHUNKS too
        f = chunk(g, i, rng.choice([1, 2]), root)
        if fn == "on_block_installed":
            sc.installed.add(root)      # the block installs: it is there for every question of the call
            if rng.random() < 0.6 and ns["tied"].get(root):     # the bid commits a tied group, often
                q0 = rng.choice(list(ns["tied"][root]))
                gs = list(ns["tied"][root][q0])
                if gs:
                    sc.bid[root] = rng.choice(gs)
            args = (root,)
        elif fn == "drop_stale_waits":
            args = ()
        elif fn == "drop_tie":
            args = (p, g, B.Bits(rng.randrange(1, 1 << (n_ + 2))))
        elif fn in ("tie", "tie_room", "defer"):
            if rng.random() < 0.3 and ns["tied"].get(root):     # a peer with ties already: tied already, or no room
                p = rng.choice(list(ns["tied"][root]))
            args = (p, f)
        else:                           # on_chunk, on_validated: the deferral's depth, reached and not passed
            f = chunk(g, rng.choice(js[:n_]), rng.choice([1, 2]), root)
            if rng.random() < 0.8:      # the block there by the time defer asks, mostly
                sc.installed.add(root)
            else:
                sc.installed.discard(root)
            sc.dead.discard(f.slot)
            sc.expired.discard(g)
            if fn == "on_chunk":
                sc.vseq[f.mid] = [C["DEFER"], C["DEFER"]]       # then ACCEPT: two levels of defer
                args = (p, f)
            else:
                sc.vseq[f.mid] = [C["DEFER"]] if rng.random() < 0.7 else []
                args = (p, f, C["DEFER"])
        try:
            ns[fn](*args)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed4b: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
