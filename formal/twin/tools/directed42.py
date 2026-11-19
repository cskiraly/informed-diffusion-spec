#!/usr/bin/env python3
"""Directed records for §4.2: the toy's own on_chunk, on_validated, drop_beyond, send_have, have_bits and
close_promises, and the readers held and tied_to_root, called in a toy node's namespace on generated states, with
what they ask of the rest of the node answered by the scenario, and logged by trace3.py's tracer with the node's
whole state.

    python3 directed42.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What they reach that the cells do not:
- on_chunk: a duplicate accepted; one seen and not accepted; one whose id waits, with the `if` and the `elif` both
  true (pending and accepted; seen and pending); expired; out of the live window;
- on_validated: its own first line, with `expired` false to on_chunk and true to it; DEFER, which goes to `defer`,
  the twin's own (kept, refused, not admitted, and its second validation once the block is installed); REJECT;
  ACCEPT with a group not known yet (open_group, then drop_beyond with offers, tries, asks, promises, queued asks
  and ties at, beyond and below N); an INVALID group; a chunk received before; a chunk claimed before (a decoded
  node); no claim, where the mesh is not asked; K reached at COLLECTING, and past it; the mesh with p in it,
  without it, and empty;
- have_bits with origin there with bits, there and empty, and missing; send_have;
- close_promises in both forms, alone, with other peers' and other chunks' promises as decoys;
- drop_beyond alone, and after a callee has changed the queue (its drop_offer, between two indices);
- held and tied_to_root alone: rows of tied there and empty at each level, and an index beyond N;
- the toy's own enqueue in about 30% of the samples (from a stream of its own), so that a record of the whole
  state checks an enqueue's `cw` against the tables: a row it makes, with both lanes;
- ties of two indices, often one below N and one at or beyond it, so that drop_beyond clears a tie in part and
  writes what is left (from a stream of its own: the other draws are as without it).
And orders that are not sorted: CPython iterates a set of small ints upward, so the cells alone would pass a twin
that sorts. Here the peers are drawn from 1 to 63, so a set of them iterates in its hash table's order, which is
often not sorted: `mesh | {p}` is the toy's own set operation, answered in that order. The queue's rows are put
in a drawn order, one of them often there with both lanes empty.

The scenario answers seen, accepted, mark_seen, expired, live, validate_chunk, penalise, enqueue, after, start and
forward, and the deferral path's installed_block (a block or nothing), admitted, reserve and release. `forward`
touches none of the twin's tables, and the toy's own needs the simulator's peer data, which these peers have not:
it is the scenario's here, and the cells run the toy's. The toy's own open_group, store and claim_group run, and
protocol.md's drop_offer: their reads and writes of the twin's tables are their `cr` and `cw` on the tape. defer
and tie run as protocol.md has them, and they are the twin's own: in its records, not on the tape. claim_group's
`close_promises_of_group` reads the toy's index of ask keys per chunk (`_by_index`), which this file keeps for
the keys it draws.

As directed61.py's and directed44.py's, the states are drawn without the document's invariants: `accepted` apart
from `chunks` and `state`, `state` apart from `desc`, `mine` apart from `received`, ties and offers of indices the
group has not, a duplicate both seen and waiting.

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

FNS = (["on_chunk"] * 10 + ["on_validated"] * 10 + ["drop_beyond"] * 4 + ["close_promises"] * 4 + ["send_have"] * 2
       + ["have_bits"] * 2 + ["held"] * 2 + ["tied_to_root"] * 2)


class Scenario:
    def __init__(self):
        self.seen, self.accepted, self.expired, self.dead = set(), set(), set(), set()
        self.expired_seq, self.verdicts = [], []
        self.admit, self.installed, self.admitted, self.reserve = True, False, True, True
        self.own_enqueue = False        # the toy's own enqueue, not the drawn answer


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed42", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import node as N                    # noqa: E402
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

    def expired(g):
        return sc.expired_seq.pop(0) if sc.expired_seq else g in sc.expired

    def validate_chunk(f):
        return sc.verdicts.pop(0) if sc.verdicts else C["ACCEPT"]

    ns["seen"] = lambda mid: mid in sc.seen
    ns["accepted"] = lambda mid: mid in sc.accepted
    ns["mark_seen"] = lambda mid: sc.seen.add(mid)
    # a chunk's content id is the scenario's, the part of its id after group and index (`cid`), so that the id
    # each chunk carries is the document's message_id of it in this namespace
    ns["content_id"] = lambda f: f.cid
    ns["expired"] = expired
    ns["live"] = lambda slot: slot not in sc.dead
    ns["validate_chunk"] = validate_chunk
    ns["penalise"] = lambda p: None
    own_enqueue = ns["enqueue"]         # the toy's own, kept: a share of the samples runs it
    ns["enqueue"] = lambda p, x, urgent=False: own_enqueue(p, x, urgent) if sc.own_enqueue else sc.admit
    ns["after"] = lambda delay, fn, *args: None
    ns["start"] = lambda fn, g: None
    ns["forward"] = lambda f, p: None
    # the block or nothing, as §8's interface has it (the tracer reads which, and refuses anything else)
    ns["installed_block"] = lambda slot, root: types.SimpleNamespace(slot=slot, root=root) if sc.installed else None
    ns["admitted"] = lambda p, f: sc.admitted
    ns["reserve"] = lambda p, f: sc.reserve
    ns["release"] = lambda p, f: None
    tr.install(nd, ns)

    rng = random.Random(a.seed)
    rng3 = random.Random(a.seed + 2000003)      # which samples run the toy's own enqueue
    rng2 = random.Random(a.seed + 1000003)      # a tie's second index, apart from the main stream, so that
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]   #   every other draw is as without it
    roots = [bytes([0xa1 + j]) * 32 for j in range(3)]
    raised = Counter()
    for _ in range(a.n):
        g, other_g = rng.sample(groups, 2)
        root, oroot = rng.sample(roots, 2)
        n_ = rng.choice([2, 3, 4])
        k_ = rng.randrange(1, n_ + 1)
        d = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32, count=n_, total_length=4 * k_,     # N(d) = n_, K(d) = k_;
                                  segment_size=4)                                   #   a whole descriptor
        now = rng.choice([1.0, 3.25])
        ns["now"] = now
        times = [now - x for x in (0.05, 0.3, 0.6)]

        def fid(gg, j, salt):
            return gg + j.to_bytes(4, "little") + bytes([salt]) * 20

        def keys_of(gg, j):             # the two forms of a chunk's ask key
            return [Wm.WantIndex(gg, j), fid(gg, j, 7)]

        i = rng.randrange(n_ + 1)       # now and then an index the group has not (n_)
        f = types.SimpleNamespace(slot=rng.choice([1, 2]), beacon_block_root=root, group=g, index=i, descriptor=d,
                                  mid=fid(g, i, rng.randrange(256)))
        f.cid = f.mid[36:]              # its content id: what `content_id(f)` answers here
        peers = rng.sample(range(1, 64), rng.randrange(1, 7))     # a set of them iterates in hash order
        p = rng.choice(peers) if rng.random() < 0.8 else rng.choice([q for q in range(1, 64) if q not in peers])
        r = rng.random()
        mesh = set(rng.sample(peers, rng.randrange(len(peers) + 1)))
        if r < 0.3:
            mesh.add(p)                 # the sender in the mesh
        elif r < 0.4:
            mesh = set()                # an empty mesh
        else:
            mesh.discard(p)

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        ns["mesh"] = mesh
        sc.__init__()
        sc.own_enqueue = rng3.random() < 0.3
        js = list(range(n_ + 2))        # indices below N, at it and beyond it
        if rng.random() < 0.5:          # the group's descriptor known, or not
            ns["desc"][g] = d
        if rng.random() < 0.5:
            ns["desc"][other_g] = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32, count=3,
                                                         total_length=8, segment_size=4)
        r = rng.random()
        st = (None if r < 0.35 else C["COLLECTING"] if r < 0.65 else C["DECODING"] if r < 0.75
              else C["COMPLETE"] if r < 0.85 else C["INVALID"])
        if st is not None:              # drawn apart from desc: a state without a descriptor, and the other way round
            ns["state"][g] = st
        if rng.random() < 0.4:
            ns["state"][other_g] = C["COLLECTING"]
        for gg in (g, other_g):
            if rng.random() < 0.7:
                ns["received"][gg] = B.Bits(rng.randrange(1 << n_))
            r = rng.random()
            if r < 0.15:
                ns["mine"][gg] = B.Bits((1 << n_) - 1)          # a decoded node: everything claimed
            elif r < 0.75:
                ns["mine"][gg] = B.Bits(rng.randrange(1 << n_))
        # §6.1's tables under the chunks' keys, below, at and beyond N, and another group's
        for gg in (g, other_g):
            for j in js if gg == g else js[:2]:
                for b in keys_of(gg, j):
                    if rng.random() < 0.2:
                        ns["asked_at"][b] = rng.choice(times)
                        nd._by_index.setdefault((gg, j), set()).add(b)
                    if rng.random() < 0.15:
                        ns["tried"][b] = {q: rng.choice(times) for q in rng.sample(peers, rng.randrange(1, len(peers) + 1))}
                    if rng.random() < 0.2:
                        for q in rng.sample(peers, rng.randrange(1, len(peers) + 1)):
                            ns["offers"][b].append(q)
                        nd._by_index.setdefault((gg, j), set()).add(b)
                    for q in peers:
                        if rng.random() < 0.08:
                            ns["promises"][(b, q)] = rng.choice(times)
                if rng.random() < 0.15:
                    ns["asked_parked"][(gg, j)] = set(rng.sample(peers, rng.randrange(1, len(peers) + 1)))
        for q in peers:
            for gg in (g, other_g):
                if rng.random() < 0.5:
                    ns["offered"][q][gg] = B.Bits(rng.randrange(1, 1 << (n_ + 2)))
            if rng.random() < 0.2:
                ns["park"][q][g] = now + 10
        # the queue: rows in a drawn order, IWANTs of the chunk's asks and others; one row often there and empty
        for q in rng.sample(peers, rng.randrange(len(peers) + 1)):
            pq = ns["queue"][q]
            for _ in range(rng.randrange(1, 3)):
                ids = [rng.choice(keys_of(g, rng.choice(js))) for _ in range(rng.randrange(1, 3))]
                pq.normal.append(Wm.Entry(control=Wm.IWANT(ids)))
            if rng.random() < 0.25:
                pq.normal = []          # there, with both lanes empty
        # tied: ties at, beyond and below N, under two roots; rows there and empty at each level
        for q in peers:
            r = rng.random()
            rr = root if rng.random() < 0.6 else oroot
            if r < 0.35:
                ns["tied"][rr][q][g].set(rng.choice(js))
                if rng2.random() < 0.5:         # often a second index, so a tie lies on both sides of N and
                    ns["tied"][rr][q][g].set(rng2.choice(js))   #   drop_beyond's clear leaves some of it (setTied)
                ns["tie_slot"].setdefault((rr, q), f.slot)
            elif r < 0.45:
                ns["tied"][rr][q][other_g].set(rng.randrange(3))
            elif r < 0.52:
                b = ns["tied"][rr][q][g]                # a bitmap there and empty
                b.set(0)
                b.clear(0)
            elif r < 0.58:
                row = ns["tied"][rr][q]                 # a peer's row there and empty
                row[other_g].set(0)
                row.pop(other_g)
            elif r < 0.62:
                ns["tied"][rr][q][other_g].set(0)       # a root's row there and empty
                ns["tied"][rr].pop(q)
        r = rng.random()
        if r < 0.2:
            ns["origin"][g] = B.Bits(rng.randrange(1, 1 << n_))         # a group we publish: what arrived
        elif r < 0.3:
            ns["origin"][g] = B.Bits(0)                                 # there and empty
        if rng.random() < 0.2:
            ns["origin"][other_g] = B.Bits(1)
        # the scenario's: seen, accepted, waiting, expiry and window, level 1's verdicts, the deferral path
        if rng.random() < 0.35:
            sc.seen.add(f.mid)
        if rng.random() < 0.5:
            sc.accepted.add(f.mid)
        if rng.random() < 0.2:
            ns["pending_ids"].add(f.mid)
        if rng.random() < 0.3:
            ns["pending_ids"].add(fid(g, i, 255))                       # another copy's id waits
        if rng.random() < 0.06:
            sc.expired.add(g)
        if rng.random() < 0.06:
            sc.dead.add(f.slot)
        sc.admit = rng.random() < 0.85
        sc.installed = rng.random() < 0.3
        sc.admitted = rng.random() < 0.85
        sc.reserve = rng.random() < 0.7
        r = rng.random()
        first = C["ACCEPT"] if r < 0.65 else C["REJECT"] if r < 0.8 else C["DEFER"]
        second = rng.choice([C["ACCEPT"], C["ACCEPT"], C["REJECT"], C["DEFER"]])   # defer's validation again
        fn = rng.choice(FNS)
        if fn in ("on_chunk", "on_validated") and rng.random() < 0.08 and g not in sc.expired:
            sc.expired_seq = [False, True] if fn == "on_chunk" else [True]     # expired meanwhile (its own first line)
        if fn == "on_chunk":
            sc.verdicts = [first, second]
            args = (p, f)
        elif fn == "on_validated":
            sc.verdicts = [second]
            args = (p, f, first)
        elif fn == "drop_beyond":
            if rng.random() < 0.97:
                ns["desc"][g] = d       # called once the count is known; now and then not, where N(None) raises
            args = (g,)
        elif fn == "close_promises":
            j = rng.choice(js)
            args = (g, j) if rng.random() < 0.6 else (g, j, rng.choice(peers))
        elif fn == "send_have":
            args = (rng.choice(peers), g)
        elif fn == "have_bits":
            args = (g,)
        elif fn == "held":
            args = (rng.choice(keys_of(g, rng.choice(js))),)
        else:
            args = (rng.choice(peers), rng.choice(keys_of(g, rng.choice(js))))
        try:
            if fn == "close_promises" and len(args) == 3:
                ns[fn](args[0], args[1], of=args[2])
            else:
                ns[fn](*args)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed42: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
