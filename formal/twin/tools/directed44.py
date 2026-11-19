#!/usr/bin/env python3
"""Directed records for §4.4 and §6.2: the toy's own on_ihave, over_ihave_limits, valid_id, expand and gated,
called in a toy node's namespace on generated states, with what they ask of the rest of the node answered by the
scenario, and logged by trace3.py's tracer with the node's whole state.

They reach what check.py's cells never do. The toy sets neither IHAVE limit, so in a cell over_ihave_limits is
always false and held_back is never written: here the limits are 2 IHAVE-bearing frames and 3 asks, and the
counts are drawn on both sides of each. Also: an IHAVE with no entry; entries that are full ids, and bitmaps of
two groups; chunks held, groups expired, stopped or without a block; a copy that waits (tied_to_root); the peer
parked, which arms the last resort; an ask open to the peer, by promise or in its queue; the ask window open; an
order of the candidates that the scenario draws; and decoys: counts of other peers, asks held back for other
chunks, §6.1's tables under other keys.

Since v0.10 (§4.4's `valid_id` and the bitmap's `valid_have`): ids that are not a chunk's structured id (0, 20,
36, 55 and 57 bytes; 56 bytes with an index no group has, 8192 or 2**32 - 1) beside ones that are (56 bytes,
index 8191 or below 3); a group's descriptor known (counts 1 to 3, so that an index of the bitmaps and ids here
falls on both sides of it) or not; and so bitmaps the toy's `valid_have` refuses, whose sender is penalised.
valid_id is also called alone, now and then with a bitmap, of which the Python's `len` raises.

As directed61.py's, the states are drawn without the document's invariants (its docstring lists what that
allows for §6.1's tables). For the other tables: held_back may hold an ask for a chunk whose group is not
authenticable, or one that is held; a count of asks may exceed the count of frames' asks.

    python3 directed44.py TOYDIR OUT.jsonl.gz [--n N] [--seed S] [--no-limits]

With --no-limits the two limits stay as the toy sets them, which is not at all (the cells' case): over_ihave_limits
is then always false, and its two counts are read all the same. The same states and calls otherwise.

The node is node 2 of a 5-node cell built as run.py builds it (no event runs).

As in directed61.py, `held` and `tied_to_root` are the toy's own, over `mine` and `tied`. Each sample draws the
scenario's held and tied from the main stream, then sets `mine`'s bits for the six chunks to agree with held and
puts the drawn ties in `tied` under one root, with decoys from a stream of their own (other roots, and rows there
and empty at each level). A descriptor gets K = N (no draw), since `desc` is read as N and K. `OUT.moved.json`
lists the records whose held, as drawn, disagreed with `mine`.
"""
import argparse
import json
import random
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402

FNS = ["on_ihave"] * 10 + ["over_ihave_limits"] * 2 + ["valid_id"] * 2 + ["expand"] * 2 + ["gated"]
LIMIT_RPCS, LIMIT_ASKS = 2, 3


class Scenario:
    held, expired, tied, peers, listed, admit, rank, block, order = set(), set(), set(), [], {}, True, {}, set(), {}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-limits", action="store_true",
                    help="leave the two IHAVE limits as the toy has them: none (the cells' case, with the whole state)")
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed44", f"--n={a.n}", f"--seed={a.seed}"] + (["--no-limits"] if a.no_limits else []),
                        whole=True)
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
    gi = ns["group_index"]

    def chunk(x):
        b = gi(x)
        return (b.group, b.index)

    if not a.no_limits:
        ns["MAX_IHAVE_MESSAGES"], ns["MAX_IHAVE_LENGTH"] = LIMIT_RPCS, LIMIT_ASKS
    ns["expired"] = lambda g: g in sc.expired
    ns["authenticable"] = lambda g: g in sc.block
    ns["connected_topic_peers"] = lambda: list(sc.peers)
    ns["own_order"] = lambda xs, x: sorted(xs, key=lambda q: sc.rank[q])
    ns["shuffled"] = lambda xs: sorted(xs, key=lambda x: sc.order.get((chunk(x), isinstance(x, bytes)), 2.0))   # this
    #   sample's draw; an id of index 8191 is drawn last
    ns["listed"] = lambda p: sc.listed.get(p, 0)
    ns["enqueue"] = lambda p, x, urgent=False: sc.admit
    ns["after"] = lambda delay, fn, *args: None
    tr.install(nd, ns)

    rng = random.Random(a.seed)
    rng2 = random.Random(a.seed + 1000003)      # the draws of `tied`'s decoys: apart from the main stream
    roots = [bytes([0xa1 + j]) * 32 for j in range(4)]      # the ties' root; the decoys' three
    held_apart = []                     # records whose drawn held disagreed with mine
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(2)]
    raised = Counter()
    for _ in range(a.n):
        g = rng.choice(groups)
        other_g = groups[1] if g == groups[0] else groups[0]
        now = rng.choice([0.5, 1.0, 3.25, 7.0])
        ns["now"] = now
        peers = rng.sample(range(1, 7), rng.randrange(1, 6))
        sc.peers = peers[:]
        rng.shuffle(sc.peers)
        p = rng.choice(peers)
        times = [now - d for d in (0.05, 0.15, 0.3, 0.6)] + [now]

        def fid(gg, i, salt=0):
            return gg + i.to_bytes(4, "little") + bytes([salt]) * 20

        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()             # the toy's count of lists per announcer (`listed` is the scenario's)
        keys = [Wm.WantIndex(gg, i) for gg in groups for i in range(3)] + [fid(gg, i) for gg in groups for i in range(3)]
        chunks = [(gg, i) for gg in groups for i in range(3)]
        # §6.1's tables, under the keys an IHAVE of these groups can bring
        for b in keys:
            r = rng.random()
            if r < 0.25:
                ns["asked_at"][b] = rng.choice(times)       # inside the window or outside it
            if rng.random() < 0.2:
                ns["tried"][b] = {q: rng.choice(times) for q in rng.sample(peers, rng.randrange(1, len(peers) + 1))}
            if rng.random() < 0.3:                  # an offer list joins `offers` by its first append (v0.10)
                for q in rng.sample(peers, rng.randrange(1, len(peers) + 1)):
                    ns["offers"][b].append(q)
            for q in peers:
                if rng.random() < 0.08:
                    ns["promises"][(b, q)] = rng.choice(times)
        for q in peers:
            for gg in groups:
                if rng.random() < 0.5:
                    ns["offered"][q][gg] = B.Bits(rng.randrange(1, 8))
                r = rng.random()
                if r < 0.25:
                    ns["park"][q][gg] = now + 10 if r < 0.15 else now - 1
            if rng.random() < 0.15:
                ns["queue"][q].normal.append(Wm.Entry(control=Wm.IWANT([rng.choice(keys)])))
        for c in chunks:
            if rng.random() < 0.2:
                ns["asked_parked"][c] = set(rng.sample(peers, rng.randrange(1, len(peers) + 1)))
            if rng.random() < 0.15:
                ns["last_resort_armed"].add(c)
        for gg in groups:
            if rng.random() < 0.12:
                ns["stop_pull"][gg] = True
            ns["mine"][gg] = B.Bits(rng.randrange(8) if rng.random() < 0.6 else 0)
            for j in range(3):
                if rng.random() < 0.3:
                    ns["known_id"][gg][j] = fid(gg, j, salt=1)
            if rng.random() < 0.5:                  # the group's descriptor known: its count (§4.4's valid_id,
                n_ = rng.choice([1, 2, 3])                  #   the toy's valid_have); K = N, drawn from nothing
                ns["desc"][gg] = types.SimpleNamespace(version=2, hash_id=0, encoding=1, root=bytes([0xd0]) * 32, count=n_, total_length=n_, segment_size=1)   # a whole descriptor
        # the limits' tables: the counts on both sides of each limit, for p and for the others; asks held back
        for q in peers:
            if rng.random() < (0.8 if q == p else 0.4):
                ns["ihave_frames"][q] = rng.randrange(1, LIMIT_RPCS + 2)
            if rng.random() < (0.7 if q == p else 0.4):
                ns["ihave_asked"][q] = rng.randrange(1, LIMIT_ASKS + 2)
        for c in chunks:
            if rng.random() < 0.2:
                ns["held_back"][c] = rng.choice([Wm.WantIndex(*c), fid(*c)])
        sc.held = {c for c in chunks if rng.random() < 0.15}
        sc.expired = {gg for gg in groups if rng.random() < 0.08}
        sc.block = {gg for gg in groups if rng.random() < 0.88}
        sc.tied = {(q, c) for q in peers for c in chunks if rng.random() < 0.06}
        sc.listed = {q: rng.choice([0, 10, 255, 256, 300]) for q in peers}
        sc.rank = {q: rng.random() for q in peers}
        sc.order = {(c, full): rng.random() for c in chunks for full in (False, True)}
        sc.admit = rng.random() < 0.85

        def an_id(gg):                  # an id: a chunk's structured id, or not one (§4.4's valid_id)
            r = rng.random()
            if r < 0.6:
                return fid(gg, rng.randrange(3))
            if r < 0.7:
                return fid(gg, 8191)            # the last index a group can have
            if r < 0.8:
                return fid(gg, rng.choice([8192, 2 ** 32 - 1]))     # an index no group has
            return fid(gg, rng.randrange(3))[:rng.choice([0, 20, 36, 55])] if rng.random() < 0.8 else \
                fid(gg, rng.randrange(3)) + b"\x44"                    # 57 bytes

        def entry():                    # an IHAVE's entry: an id, or a bitmap of a group
            gg = g if rng.random() < 0.75 else other_g
            if rng.random() < 0.4:
                return an_id(gg)
            return Wm.HaveBitmap(gg, B.Bits(rng.randrange(1, 8)))

        # held and tied_to_root are the toy's own, over mine and tied, which follow the scenario's draw
        apart = False
        for gg, i in chunks:
            m = ns["mine"][gg]
            if m.has(i) != ((gg, i) in sc.held):
                apart = True
                m.v ^= 1 << i               # the sample's own Bits, assigned above
        ns["tied"]._d.clear()
        for q, (tg, ti) in sorted(sc.tied):
            ns["tied"][roots[0]][q][tg].set(ti)
        for q in peers:                     # decoys: rows there and empty, under the other roots
            r = rng2.random()
            gg = rng2.choice(groups)
            if r < 0.1:
                b = ns["tied"][rng2.choice(roots[1:])][q][gg]           # a bitmap there and empty
                b.set(0)
                b.clear(0)
            elif r < 0.2:
                row = ns["tied"][rng2.choice(roots[1:])][q]             # a peer's row there and empty
                row[gg].set(0)
                row.pop(gg)
            elif r < 0.27:
                root = rng2.choice(roots[1:])                           # a root's row there and empty
                ns["tied"][root][q][gg].set(0)
                ns["tied"][root].pop(q)
        if apart:
            held_apart.append(sum(tr.counts.values()))
        fn = rng.choice(FNS)
        if fn == "on_ihave":
            r = rng.random()
            ids = [] if r < 0.06 else [entry() for _ in range(rng.choice([1, 1, 1, 2, 3]))]
            args = (p, types.SimpleNamespace(ids=ids))
        elif fn == "over_ihave_limits":
            args = (p,)
        elif fn == "expand":
            args = (entry(),)
        elif fn == "valid_id":                  # of an id; of a bitmap now and then, where the Python's len raises
            gg = g if rng.random() < 0.75 else other_g
            args = (an_id(gg) if rng.random() < 0.95 else Wm.HaveBitmap(gg, B.Bits(rng.randrange(1, 8))),)
        else:
            args = (rng.choice(keys),)
        try:
            ns[fn](*args)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    Path(a.out + ".moved.json").write_text(json.dumps({"held_apart": held_apart}) + "\n")
    print(f"directed44: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}; "
          f"{len(held_apart)} with held drawn apart from mine", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
