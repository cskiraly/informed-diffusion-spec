#!/usr/bin/env python3
"""Directed records for §6.1: the toy's own §6.1 functions, called in a toy node's namespace on generated states,
with what §6.1 asks of the rest of the node answered by the scenario, and logged as in a cell by the tracer its
caller puts in trace61.Tracer's place (directed3.py: trace3.py's). They reach what check.py's cells never do: ledger, the window's and the park's boundaries, ties among
the tried, a stop-pull or an expiry before the chunk is held, an unparked announcer at the last resort, and
orders of announcers that change the pick; promises and queued asks for other chunks, which a wrong match would
take; and the three places the Python raises (least_recently_tried on an untried candidate or on none, and the
last resort past 1,023 counted asks, with its last finite case, 1,023, beside it).

Also: decoys, state a twin reading more widely than the Python would see (asked_at, tried and offers under the
chunk's other form, another chunk of the group and the same index in another group; park and offered of another
group; asked_parked and last_resort_armed of other chunks; asks of another group in the queues, and an entry of
one ahead of the drawn one, from a stream of its own; from that stream too, a two-id IWANT with the drawn ask
second, an IHAVE ahead of the IWANT in one entry, an entry with a chunk, and an ask of the chunk in the urgent
lane); now below IWANT_WINDOW and below 0, where the -inf defaults decide; a list of 16 announcers, and one place
left in it; and no peer connected. The records hold the node's whole §6.1 state (the tracer's whole=True).

The states are drawn without the document's invariants, on purpose: a translation is tested on more than the
states a run reaches, and some of the block's paths no run takes. So a directed record is not one a node of the
document could produce. The departures known:
- known_id entries for indices not in mine: §4.2 records an id only for a chunk it stores, and claims every
  stored index, so `known_id[g].get(i) or` never yields an id as the document stands;
- expired answered true with the group's pull state still there (§8.1 drops it at expiry);
- the overflow samples' 1,023 or 1,024 counted peers, which are neither connected nor announcers;
- stop_pull set apart from mine: wherever the document sets stop_pull[g], mine[g] already has every index
  (claim_group, publish; drop_group comes after the claim), so held decides first and, with every card on, no
  run reaches the two stop-pull branches;
- listed answered apart from the offer lists the state holds, and above the limit of 256 (§8.1: `listed` is how
  many lists an announcer is in);
- a peer in an offer list without its bit in offered (add_offer sets the bit before it lists the peer);
- equal times among the tried (every ask resets the window, so a run's tries are IWANT_WINDOW apart), and the
  decoys' times, drawn like any other.

A negative now is not among them: the document fixes no epoch for its clock.

    python3 directed3.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]      (this file's `main`, with trace3.py's tracer)

The node is node 2 of a 5-node cell built as run.py builds it (no event runs). Each sample sets §6.1's state
in that namespace, the scenario's answers (expired, connected_topic_peers, own_order, listed, enqueue; after only
records), and calls one of the twelve functions at top level. A sample on which the Python raises is written with
`raises` by the tracer; the counts are printed.

`held(a)` and `tied_to_root(p, a)` are the twin's code, so the toy's own run here, over `mine` and `tied`. Each
sample draws the scenario's held and tied from the main stream, and then sets `mine[g]`'s bit for the chunk to
agree with held, and puts the drawn ties in `tied` under one root. `tied` also gets decoys, from a stream of
their own so that the main stream, and every other draw, are as without them: ties of another index or group,
under another root, and rows there and empty at each level. `OUT.moved.json` lists the records whose held, as
drawn, disagreed with `mine`'s bit: the only ones whose outcome may differ from one with held answered by the
scenario.
"""
import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace61                          # noqa: E402

FNS = (["retry_offer"] * 6 + ["ask_parked"] * 6 + ["last_resort"] * 3 + ["promise_due"] * 3 + ["may_ask"] * 3
       + ["outstanding", "add_offer", "announcers", "ledger", "untried", "least_recently_tried", "parked"])


class Scenario:
    held, expired, tied, peers, listed, admit, rank = set(), set(), set(), [], {}, True, {}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace61.Tracer(toy, a.out, ["directed61", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
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
    ns["expired"] = lambda g: g in sc.expired
    ns["connected_topic_peers"] = lambda: list(sc.peers)
    ns["own_order"] = lambda xs, a: sorted(xs, key=lambda q: sc.rank[q])     # this sample's order, the same at each ask
    ns["listed"] = lambda p: sc.listed.get(p, 0)
    ns["enqueue"] = lambda p, x, urgent=False: sc.admit
    ns["after"] = lambda delay, fn, *args: None
    tr.install(nd, ns)

    rng = random.Random(a.seed)
    rng2 = random.Random(a.seed + 1000003)      # the draws of `tied`'s decoys: apart from the main stream
    rng3 = random.Random(a.seed + 2000003)      # the decoy entries ahead of an ask: apart from both
    roots = [bytes([0xa1 + j]) * 32 for j in range(4)]      # the ties' root; the decoys' three
    held_apart = []                     # records whose drawn held disagreed with mine's bit
    W = ns["IWANT_WINDOW"]
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(2)]
    raised = Counter()
    for _ in range(a.n):
        g = rng.choice(groups)
        other_g = groups[1] if g == groups[0] else groups[0]
        i = rng.randrange(3)
        wi = Wm.WantIndex(g, i)
        fid = g + i.to_bytes(4, "little") + bytes(rng.randrange(256) for _ in range(20))
        key = rng.choice([wi, fid])
        other = fid if key is wi else wi        # the chunk's other form: what is kept under it is a decoy
        k = (g, i)
        r = rng.random()                        # now below the window, where the -inf defaults decide, and
        now = (rng.choice([0.0, 0.1]) if r < 0.1 else -2.0 if r < 0.13    # below 0 (the document fixes no
               else rng.choice([0.5, 1.0, 3.25, 7.0]))                    # clock's epoch)
        ns["now"] = now
        r = rng.random()
        if r < 0.02:                            # no peer connected
            peers = []
        elif r < 0.07:                          # enough peers for a list of 16
            peers = rng.sample(range(1, 21), rng.randrange(16, 20))
        else:
            peers = rng.sample(range(1, 7), rng.randrange(1, 6))
        sc.peers = peers[:]
        rng.shuffle(sc.peers)
        times = [now - d for d in (0.05, 0.15, 0.3, 0.6)] + [now]

        def window_edge():                  # an asked_at with now - asked_at == IWANT_WINDOW exactly, if any
            t = now - W
            for _ in range(8):
                if now - t == W:
                    return t
                t = math.nextafter(t, -math.inf if now - t < W else math.inf)
            return rng.choice(times)

        for name in ("asked_at", "promises", "last_resort_armed"):
            ns[name].clear()
        for name in ("tried", "offered", "asked_parked", "park", "stop_pull", "queue", "mine", "known_id"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()         # the toy's count of lists per announcer (`listed` is the scenario's)
        r = rng.random()
        if r < 0.5:
            ns["asked_at"][key] = rng.choice(times) if r < 0.4 else window_edge()
        if rng.random() < 0.7:
            tried = {}
            tie = rng.choice(times)
            for q in rng.sample(peers, rng.randrange(len(peers) + 1)):
                tried[q] = tie if rng.random() < 0.4 else rng.choice(times)
            if tried:
                ns["tried"][key] = tried
        if rng.random() < 0.8:                  # since v0.10 a list joins `offers` by its first append, and
            if len(peers) >= 16:                #   no other change of it is let through (bits.OfferMap): the
                ol = rng.sample(peers, rng.choice([15, 16]))      # drawn peers, one append each.
            else:                               #   A full list, or one place left
                ol = rng.sample(peers, rng.randrange(len(peers) + 1))
            for q in ol:
                ns["offers"][key].append(q)
        for q in peers:
            if rng.random() < 0.7:
                v = rng.randrange(8) | ((1 << i) if rng.random() < 0.7 else 0)
                ns["offered"][q][g] = B.Bits(v)
        for q in peers:
            if rng.random() < 0.35:
                ns["promises"][(rng.choice([wi, fid]), q)] = rng.choice(times)
        for q in peers:                     # promises for other chunks: what a wrong match would take
            if rng.random() < 0.25:
                ns["promises"][(rng.choice([Wm.WantIndex(g, (i + 1) % 3), Wm.WantIndex(other_g, i)]), q)] = rng.choice(times)
        for q in peers:
            r = rng.random()
            if r < 0.5:
                ns["park"][q][g] = now + 10 if r < 0.25 else (now - 1 if r < 0.4 else now)
        if rng.random() < 0.5:
            ns["asked_parked"][k] = set(rng.sample(peers, rng.randrange(len(peers) + 1)))
        if rng.random() < 0.25:
            ns["last_resort_armed"].add(k)
        if rng.random() < 0.15:
            ns["stop_pull"][g] = True
        for q in peers:
            if rng.random() < 0.2:
                r = rng.random()
                ids = ([rng.choice([wi, fid])] if r < 0.5 else [Wm.WantIndex(g, (i + 1) % 3)] if r < 0.75
                       else [Wm.WantIndex(other_g, i)])
                if rng3.random() < 0.4:         # an entry ahead of it, an ask of another group,
                    ns["queue"][q].normal.append(Wm.Entry(control=Wm.IWANT([Wm.WantIndex(other_g, i)])))   #   so
                # that a twin reading the first entry alone misses the chunk's ask. From the same stream: the drawn
                # ask second in a two-id IWANT; an IHAVE ahead of the IWANT in one entry; an entry with a chunk
                # (another group's, as the toy queues one) and the IWANT
                x3 = rng3.random()
                if x3 < 0.25:
                    entry = Wm.Entry(control=Wm.IWANT([Wm.WantIndex(other_g, i)] + ids))
                elif x3 < 0.5:
                    entry = Wm.Entry(control=Wm.IHAVE(other_g + i.to_bytes(4, "little") + bytes(20)) + Wm.IWANT(ids))
                elif x3 < 0.7:
                    chunk = SimpleNamespace(group=other_g, index=i, slot=1, beacon_block_root=bytes([0xa1]) * 32,
                                            mid=other_g + i.to_bytes(4, "little") + bytes([0x5c]) * 20)
                    entry = Wm.Entry(chunk=chunk, control=Wm.IWANT(ids))
                else:
                    entry = Wm.Entry(control=Wm.IWANT(ids))
                ns["queue"][q].normal.append(entry)
                if rng3.random() < 0.15:        # an ask of the chunk in the urgent lane, which the Python
                    ns["queue"][q].urgent.append(Wm.Entry(control=Wm.IWANT([wi])))   #   does not read
        # decoys: what a twin reading more widely than the Python would see
        for b in (other, Wm.WantIndex(g, (i + 1) % 3), Wm.WantIndex(other_g, i)):
            if rng.random() < 0.4:
                ns["asked_at"][b] = rng.choice(times)
            if peers and rng.random() < 0.4:
                ns["tried"][b] = {q: rng.choice(times) for q in rng.sample(peers, rng.randrange(1, len(peers) + 1))}
            if peers and rng.random() < 0.4:
                for q in rng.sample(peers, rng.randrange(1, min(len(peers), 16) + 1)):
                    ns["offers"][b].append(q)
        for q in peers:
            if rng.random() < 0.5:
                ns["offered"][q][other_g] = B.Bits(rng.randrange(1, 8))
            r = rng.random()
            if r < 0.4:
                ns["park"][q][other_g] = now + 10 if r < 0.25 else now - 1
        for c in ((g, (i + 1) % 3), (other_g, i)):
            if peers and rng.random() < 0.3:
                ns["asked_parked"][c] = set(rng.sample(peers, rng.randrange(1, len(peers) + 1)))
            if rng.random() < 0.2:
                ns["last_resort_armed"].add(c)
        ns["mine"][g] = B.Bits(rng.randrange(8))
        for j in range(3):
            if rng.random() < 0.3:
                ns["known_id"][g][j] = g + j.to_bytes(4, "little") + bytes(20)
        sc.held = {k} if rng.random() < 0.12 else set()
        sc.expired = {g} if rng.random() < 0.08 else set()
        sc.tied = {(q, k) for q in peers if rng.random() < 0.15}
        sc.listed = {q: rng.choice([0, 10, 255, 256, 300]) for q in peers}
        sc.rank = {q: rng.random() for q in peers}
        sc.admit = rng.random() < 0.85
        fn = rng.choice(FNS)
        if len(peers) >= 16 and rng.random() < 0.3:     # the list's limit of 16: more offers at a long list
            fn = "add_offer"
        if rng.random() < 0.03:             # the last resort at 1,023 counted asks (2 ** n still a double) and
                                            #   at 1,024 (the Python raises)
            ns["asked_at"].pop(key, None)
            ns["last_resort_armed"].discard(k)
            ns["stop_pull"].pop(g, None)
            sc.held, sc.expired, sc.tied = set(), set(), set()
            ns["asked_parked"][k] = set(range(1000, 1000 + rng.choice([1023, 1024])))
            for q in peers:
                ns["park"][q][g] = now + 10
                ns["offered"][q][g] = B.Bits(1 << i)
            fn = rng.choice(["last_resort", "retry_offer"])
        p = rng.choice(peers) if peers else 9       # with none connected: a peer not connected
        # held and tied_to_root are the toy's own, over mine and tied, which follow the scenario's draw
        m = ns["mine"][g]
        apart = m.has(i) != (k in sc.held)
        if apart:
            m.v ^= 1 << i
        ns["tied"]._d.clear()
        for q, (tg, ti) in sorted(sc.tied):
            ns["tied"][roots[0]][q][tg].set(ti)
        for q in peers:                     # decoys: none ties q to the chunk under any root
            r = rng2.random()
            if r < 0.15:
                ns["tied"][rng2.choice(roots)][q][other_g].set(rng2.randrange(3))      # another group
            elif r < 0.25:
                ns["tied"][rng2.choice(roots)][q][g].set((i + rng2.randrange(1, 3)) % 3)     # another index
            elif r < 0.32:
                b = ns["tied"][rng2.choice(roots[1:])][q][g]            # a bitmap there and empty
                b.set(i)
                b.clear(i)
            elif r < 0.38:
                row = ns["tied"][rng2.choice(roots[1:])][q]             # a peer's row there and empty
                row[other_g].set(0)
                row.pop(other_g)
            elif r < 0.42:
                root = rng2.choice(roots[1:])                           # a root's row there and empty
                ns["tied"][root][q][other_g].set(0)
                ns["tied"][root].pop(q)
        if fn == "add_offer" and len(peers) >= 16:    # mostly from a peer not yet in the list
            out = [q for q in peers if q not in (ns["offers"].get(key) or [])]
            if out and rng.random() < 0.8:
                p = rng.choice(out)
        if fn in ("retry_offer", "ask_parked", "last_resort", "announcers"):
            args = (key,)
        elif fn in ("may_ask", "add_offer"):
            args = (key, p)
        elif fn in ("outstanding", "parked"):
            args = (p, key)
        elif fn == "ledger":
            args = (g,)
        elif fn == "promise_due":
            at = ns["promises"].get((key, p), rng.choice(times)) if rng.random() < 0.8 else rng.choice(times)
            args = (key, p, at)
        elif fn == "untried":
            args = (rng.sample(peers, rng.randrange(len(peers) + 1)), key)
        else:                               # least_recently_tried: among the tried, as its callers call it,
            tried = list(ns["tried"].get(key, {}))   # or not (the Python raises)
            untried_peers = [q for q in peers if q not in tried]
            r = rng.random()
            if r < 0.05:
                args = ([], key)
            elif r < 0.15 and untried_peers:
                cands = (rng.sample(tried, rng.randrange(len(tried) + 1))     # one untried, or two: the
                         + rng.sample(untried_peers, min(len(untried_peers), rng.choice([1, 2]))))   # first raises
                rng.shuffle(cands)
                args = (cands, key)
            elif tried:
                args = (rng.sample(tried, rng.randrange(1, len(tried) + 1)), key)
            else:
                continue
        if apart:                           # listed by its record's place, once the sample is sure to make one
            held_apart.append(sum(tr.counts.values()))
        try:
            ns[fn](*args)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    Path(a.out + ".moved.json").write_text(json.dumps({"held_apart": held_apart}) + "\n")
    print(f"directed61: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}; "
          f"{len(held_apart)} with held drawn apart from mine", file=sys.stderr)

