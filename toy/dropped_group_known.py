#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.4's on_validated and forward with a dropped group: a chunk of a group the
node dropped (§4.6, level 2 failed) is not stored, not pushed, not offered and not put in the gossip history, as
protocol.md's on_validated returns.

    python3 dropped_group_known.py

On a small payload run (one payload, run to its end), node 2 is made to have lost one chunk, and its peers other
than the sender to lack it. The control: with the group live, the chunk is stored and pushed or offered to some
peer. With the group dropped, nothing is sent under the group, the chunk is not stored, and the gossip history does
not take it. On a small rows run, a complete row's repair (push_rebuilt) of one cell, its peers made to lack it under
its column: with the column live something is sent under it (the control), with the column dropped nothing.
"""
import sys
from pathlib import Path


def sim_of(args):
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(args)
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    return sim


class History:                                              # the gossip history, counting what is put in it
    def __init__(self, inner):
        self.inner, self.put_ids = inner, []

    def put(self, f):
        self.put_ids.append(f)
        return self.inner.put(f)

    def __getattr__(self, k):
        return getattr(self.inner, k)


def arrive(ns, peers, g, i, f, p, dropped):
    """node's state as if it lacked chunk i and its peers but p lacked it too; then f arrives from p, accepted."""
    ns["chunks"][g].pop(i, None)
    ns["known_id"][g].pop(i, None)                          # store() writes both: not stored, so not accepted
    ns["received"][g].clear(i)
    for q in peers:
        if q != p:
            ns["peer_has"][q].pop(g, None)
            ns["pushed"][q].pop(g, None)
    state = ns["state"][g]
    if dropped:
        ns["state"][g] = "INVALID"
    sent = []                                               # (peer, what) under g: chunks enqueued, messages sent
    enq, snd, hist = ns["enqueue"], ns["send"], History(ns["gossip_history"])

    def enqueue(q, m, *a, **k):
        if getattr(m, "group", None) == g and getattr(m, "index", None) is not None:
            sent.append((q, m))
        return enq(q, m, *a, **k)

    def send(q, m, *a, **k):
        if getattr(m, "group", None) == g:
            sent.append((q, m))
        return snd(q, m, *a, **k)
    ns["enqueue"], ns["send"], ns["gossip_history"] = enqueue, send, hist
    try:
        ns["on_validated"](p, f, "ACCEPT")
    finally:
        ns["enqueue"], ns["send"], ns["gossip_history"] = enq, snd, hist.inner
    ns["state"][g] = state
    return [(q, m) for q, m in sent if q != p], sent, i in ns["chunks"][g], len(hist.put_ids)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    pay = sim_of(["--doc", "v2", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7"])
    nd = pay.nodes[2]
    ns = nd.ns
    peers = sorted(nd.peers)
    g = pay.msgs[0][1][0]
    i = sorted(ns["chunks"][g])[0]
    f = ns["chunks"][g][i]
    p = peers[0]
    to_others, under_g, stored, put = arrive(ns, peers, g, i, f, p, dropped=False)
    line("the control, the group live: pushed or offered to a peer other than the sender",
         len(to_others) > 0, True)
    line("the control: stored, and put in the gossip history", (stored, put), (True, 1))
    to_others, under_g, stored, put = arrive(ns, peers, g, i, f, p, dropped=True)
    line("the group dropped: anything sent under it, to anyone", len(under_g), 0)
    line("the group dropped: stored, and put in the gossip history", (stored, put), (False, 0))

    rows = sim_of(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7"])
    found = None
    for nid in sorted(rows.nodes):                              # a node with a complete row whose repair, the cell's
        nd = rows.nodes[nid]                                    #   column live, sends something under that column
        ns = nd.ns
        T_row = nd._types.get("row")
        if T_row is None:
            continue
        for gr in [g for g in ns["T_of"] if rows.gtype.get(g) == "row"
                   and len(ns["chunks"][g]) == T_row.index_count(ns["hdr"][g])]:
            for c in sorted(ns["chunks"][gr]):
                (gc, b), = T_row.cross(gr, c)
                if repair(ns, sorted(nd.peers), gr, c, gc, dropped=False):
                    found = (ns, sorted(nd.peers), gr, c, gc)
                    break
            if found:
                break
        if found:
            break
    line("the control, a row's repair with the cell's column live: something sent under the column", found is not None,
         True)
    if found:
        ns, peers, gr, c, gc = found
        line("a row's repair with the cell's column dropped: anything sent under the column",
             len(repair(ns, peers, gr, c, gc, dropped=True)), 0)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


def repair(ns, peers, gr, c, gc, dropped):
    """push_rebuilt of row gr's cell c, its peers made to lack the cell under its column gc; what it sent under gc."""
    for q in peers:
        ns["peer_has"][q].pop(gc, None)
        ns["pushed"][q].pop(gc, None)
    state = ns["state"][gc]
    if dropped:
        ns["state"][gc] = "INVALID"
    sent = []
    enq, snd = ns["enqueue"], ns["send"]

    def enqueue(q, m, *a, **k):
        if getattr(m, "index", None) is not None and gc in [g for g, _ in ns["type_of_group"](m.group).project(m)]:
            sent.append((q, m))
        return enq(q, m, *a, **k)

    def send(q, m, *a, **k):
        if getattr(m, "group", None) == gc:
            sent.append((q, m))
        return snd(q, m, *a, **k)
    ns["enqueue"], ns["send"] = enqueue, send
    try:
        ns["push_rebuilt"](gr, [c])
    finally:
        ns["enqueue"], ns["send"] = enq, snd
        ns["state"][gc] = state
    return sent


if __name__ == "__main__":
    sys.exit(main())
