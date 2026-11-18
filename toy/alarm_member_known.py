#!/usr/bin/env python3
"""A known answer for the toy's custodian alarm (--alarm-wait, an option), the member's part.

    python3 alarm_member_known.py

A member that deferred on a claim its probe verified, and gets a custodian's standing WANT for a cell of its row
that it lacks, asks the claimant for that cell once, as the probe is asked: its promise (DEFER_WINDOW) and the
alarm's wait start at the ask's write, as the probe's do (protocol-v2.md §4.6). A claimant that cannot be asked,
because its connection closed or a full queue refuses the ask, or whose connection closes before the promise
ends, is not judged; the member rebuilds the row if the cell is still missing.

On one node of a small rows run (protocol-v2.md, one block, the alarm on, run to its end), made by hand, on the
node's own row, which it holds whole: one cell is taken out of its store, the probe of another cell is set as
verified on claimant q, and custodian c sends the standing WANT. Then:
- **the write:** nothing starts at the decision; at the write the promise starts, and the alarm's wait is due
  one window after the write;
- **a full queue refuses the ask:** no promise, no penalty, and the member rebuilds at once;
- **the claimant has left before the alarm:** no ask, no penalty, and the member rebuilds at once;
- **the claimant leaves after the write:** at the wait's end, no penalty, and the member rebuilds;
- **the claimant's connection closes before the write** (the queue goes with it, drop_peer): the ask is settled
  at the close, not judged, it leaves probe_asks, and the member rebuilds.
Controls: the claimant connected and silent is penalised once and the member rebuilds; the claimant's own copy
before the wait's end leaves no penalty and no rebuild.
"""
import sys
from pathlib import Path

SEED, NODE = 7, 2


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED),
              "--alarm-wait", "3.5"])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    T_row = nd._types["row"]
    W = T_row.params.DEFER_WINDOW
    g = next(g for g in ns["T_of"] if sim.gtype.get(g) == "row" and sim.gsub.get(g) == nd.row_subnet)
    n = T_row.index_count(ns["hdr"][g])
    line_ok = len(ns["chunks"][g]) == n
    j, *cells = sorted(ns["chunks"][g])[:7]                # j: the probe's cell; one lacked cell per case (the
    held = {k: ns["chunks"][g][k] for k in cells}           #   member asks the claimant once per cell)
    peers = [p for p in sorted(nd.peers) if ns["join_recv"][p][T_row].interest != "DECLARED"]
    q, c = peers[:2]                                        # q the claimant, c the custodian
    t0 = ns["now"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    calls = []
    doc_penalise = ns["penalise"]

    def penalise(p):
        calls.append(p)
        doc_penalise(p)
    ns["penalise"] = penalise
    i = a = None

    def setup(k):                                           # the member, complete, its probe of q verified; case k
        nonlocal i, a
        i = cells[k]
        a = ns["Ask"](g, i)
        ns["now"] = t0
        sim.churn = False
        if q not in nd.peers:
            nd.peers.add(q) if isinstance(nd.peers, set) else nd.peers.append(q)
        ns["state"][g] = "COMPLETE"
        ns["stop_pull"][g] = True
        ns["chunks"][g].pop(i, None)
        ns["known_id"][g].pop(i, None)
        ns["received"][g].clear(i); ns["rebuilt"][g].clear(i); ns["mine"][g].clear(i)
        ns["deferred"][g] = True
        ns["probe"][g], ns["probed"][g] = j, q
        ns["received"][g].set(j)
        ns["peer_has"][c].pop(g, None)
        for k in [k for k in ns["promises"] if k[1] == q]:
            del ns["promises"][k]
        ns["probe_asks"].discard(a)
        ns["queue"][q].normal[:] = []; ns["queue"][q].urgent[:] = []
        for x in list(nd.alarm):
            nd.alarm[x] = 0
        calls.clear()
        sim.q[:] = [e for e in sim.q if e[2] is not nd]     # no timer of this node left from the run or a case

    def alarm():                                            # custodian c's standing WANT of cell i
        ns["on_want"](c, [Wm.FlaggedWant(g, i, True, 0)])

    def the_entry():
        return next((e for e in ns["queue"][q].normal
                     if any(ns["group"](b) == g and ns["index"](b) == i for m in e.iwants() for b in m.ids)), None)

    def due_events(name):                                   # this node's queued timers named `name`: (time, args)
        return sorted((round(t - sim.now, 6), args) for t, _, x, fn, args in sim.q if x is nd and fn.__name__ == name)

    def fire(name):                                         # run this node's queued timers named `name`, in order
        for t, _, x, fn, args in sorted([e for e in sim.q if e[2] is nd and e[3].__name__ == name], key=lambda e: e[:2]):
            fn(*args)

    def rebuilt():
        return ns["state"][g] in ("DECODING",) or nd.alarm["rebuilds"] > 0

    line("the node's own row, held whole", line_ok, True)

    # the write: nothing at the decision, the promise and the wait from the write
    setup(0)
    alarm()
    e = the_entry()
    line("at the decision: the ask queued, a promise, and alarm timers",
         (e is not None, (a, q) in ns["promises"], len(due_events("alarm_due"))), (True, False, 0))
    ns["now"] = t0 + 0.3
    out = ns["filter_entry"](q, e)
    line("at the write (0.3 s on): the promise's start, and the alarm's wait due one window after the write",
         (ns["promises"].get((a, q)), [d for d, _ in due_events("alarm_due")]), (t0 + 0.3, [W]))
    ns["now"] = t0 + 0.3 + W
    fire("alarm_due")
    line("the claimant connected and silent (control): penalties of q, and a rebuild", (calls, rebuilt()), ([q], True))

    # a full queue refuses the ask
    setup(1)
    send = ns["send"]
    ns["send"] = lambda p, m, urgent=False: False if p == q and getattr(m, "group", None) == g else send(p, m, urgent)
    alarm()
    ns["send"] = send
    line("refused: a promise, alarm timers, penalties of q, and a rebuild at once",
         ((a, q) in ns["promises"], len(due_events("alarm_due")), calls, rebuilt()), (False, 0, [], True))

    # the claimant has left before the alarm
    setup(2)
    sim.churn = True
    nd.peers.remove(q)
    alarm()
    line("the claimant gone before: an ask queued, alarm timers, penalties of q, and a rebuild at once",
         (the_entry() is not None, len(due_events("alarm_due")), calls, rebuilt()), (False, 0, [], True))
    nd.peers.add(q) if isinstance(nd.peers, set) else nd.peers.append(q)
    sim.churn = False

    # the claimant leaves after the write
    setup(3)
    alarm()
    ns["now"] = t0 + 0.1
    ns["filter_entry"](q, the_entry())
    ns["promises"].pop((a, q), None)                        # its promise goes with the connection (drop_peer)
    ns["now"] = t0 + 0.1 + W
    fire("alarm_due")
    line("the claimant gone after the write: penalties of q, and a rebuild", (calls, rebuilt()), ([], True))

    # the claimant's own copy before the wait's end (control)
    setup(4)
    alarm()
    ns["now"] = t0 + 0.1
    ns["filter_entry"](q, the_entry())
    ns["now"] = t0 + 0.2
    ns["fill"](g, i, held[i], q)
    ns["now"] = t0 + 0.1 + W
    fire("alarm_due")
    line("the claimant answers (control): penalties of q, and a rebuild", (calls, rebuilt()), ([], False))

    # the claimant's connection closes before the write: the queue goes with it
    setup(5)
    alarm()
    sim.churn = True
    nd.peers.remove(q)
    nd.drop_peer(q)
    line("closed before the write: penalties of q, a rebuild, the ask exempt from stop-pull, not judged",
         (calls, rebuilt(), a in ns["probe_asks"], nd.alarm["not judged"]), ([], True, False, 1))
    nd.peers.add(q) if isinstance(nd.peers, set) else nd.peers.append(q)
    sim.churn = False

    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
