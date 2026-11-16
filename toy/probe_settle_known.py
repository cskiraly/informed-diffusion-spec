#!/usr/bin/env python3
"""Known answers for protocol-v2.md §4.6's probe once it is settled, and for the duty's time it defers (R5).

    python3 probe_settle_known.py

On one node of a small rows run (protocol-v2.md, one block, run to its end), made by hand:

As the member, on a row it holds, three of whose cells it is made to lack (taken out of its store), with one
claimant:
- **A probe given no verdict while still queued** (the duty fires with the probe unwritten, and returns because the
  row is whole in the subnet's view): the queued WANT is dropped at the write, so no late probe goes out and no
  promise starts for it.
- **A probe a full queue refuses, with the duty armed later** (the duty was due 10 s on): the duty keeps its own
  time; it is not moved to now.
- **A probe whose claimant closes, with the duty armed later**: the same, the duty back at its own time.
- **After a probe given no verdict, a plain ask of the probed cell to the claimant** (the claimant offered it):
  the ask's promise starts at its write, and the claimant's answer closes it; the settled probe's rule no longer
  holds it open.
- Controls, the same before and after: a close when the duty was due at the decision is reconsidered at once; a
  probe not yet settled is written; the claimant's own copy before the write passes the probe, and the queued
  WANT is dropped (option (a), §4.6); before the verdict, another peer's copy leaves the written probe's promise
  open.

As the claimant, on another row it holds, one of whose cells it is made to have claimed but not stored (still
decoding):
- **A marked ask kept while decoding** is answered once when the cell is stored, with its exemption, and charged
  once to the serving limit, in every order of one asker's asks: the marked ask alone, and standing; the marked
  ask twice; a plain standing ask, then the marked ask; the marked ask, then a plain standing ask; and the marked
  ask twice with one slot of the serving limit left, where a standing copy of it took the slot first.
- The control: a plain standing ask of the same cell, from another peer, is answered once.
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
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    T_row = nd._types["row"]
    whole = [g for g in ns["T_of"] if sim.gtype.get(g) == "row"
             and len(ns["chunks"][g]) == T_row.index_count(ns["hdr"][g])]
    g, g2 = whole[0], whole[-1]
    W = T_row.params.DEFER_WINDOW
    q = sorted(nd.peers)[0]
    lack = sorted(ns["chunks"][g])[:3]
    cells = {i: ns["chunks"][g][i] for i in lack}
    t0 = ns["now"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def setup(duty=None):                                   # the member, before the claim; duty: its armed time
        ns["now"] = t0
        ns["state"][g], ns["deferred"][g] = "COMPLETE", False
        for i in lack:                                      # lacked: not claimed, not stored
            ns["mine"][g].clear(i)
            ns["chunks"][g].pop(i, None)
            ns["known_id"][g].pop(i, None)
            ns["received"][g].clear(i); ns["rebuilt"][g].clear(i)
        ns["probe_ok"].pop(g, None)
        ns["probe_sent"].discard(g)
        ns["reconsider_at"].pop(g, None)
        if duty is not None:
            ns["arm"](g, duty)
        ns["claims"][g].clear(); ns["claims"][g].add(q)
        for k in [k for k in ns["promises"] if k[1] == q]:
            del ns["promises"][k]
        ns["queue"][q].normal[:] = []

    def probe_entry():                                      # the queued WANT that carries the probe
        return next(e for e in ns["queue"][q].normal
                    if any(getattr(ns["group_index"](a), "probe", False) for c in e.iwants() for a in c.ids))

    def asks_left(entry):
        return sum(len(c.ids) for c in entry.iwants())

    # a probe given no verdict while still queued
    setup()
    ns["defer_on_claim"](g)
    entry = probe_entry()
    at = ns["reconsider_at"][g]
    ns["now"] = at
    kis = ns["known_in_scope"]
    ns["known_in_scope"] = lambda g_: ns["all_bits"](T_row.index_count(ns["hdr"][g_])) if g_ == g else kis(g_)
    ns["reconsider"](g, at)                                 # whole in the subnet's view: no rebuild
    ns["known_in_scope"] = kis
    line("no verdict, queued: the verdict, and the cell still lacked",
         (ns["probe_ok"].get(g, "none yet"), ns["mine"][g].has(ns["probe"][g])), (None, False))
    ns["now"] = at + 0.1
    out = ns["filter_entry"](q, entry)
    line("no verdict, queued: probe asks written later, and promises started for them",
         (asks_left(entry) if out is not None else 0, sum(1 for k in ns["promises"] if k[1] == q)), (0, 0))

    # a probe a full queue refuses, the duty armed 10 s on
    setup(duty=t0 + 10)
    send = ns["send"]
    ns["send"] = lambda p, m, urgent=False: False if getattr(m, "probe", False) else send(p, m, urgent)
    ns["defer_on_claim"](g)
    ns["send"] = send
    line("refused, the duty armed 10 s on: the verdict, and the duty's time from the decision",
         (ns["probe_ok"].get(g, "none yet"), round(ns["reconsider_at"][g] - t0, 6)), (None, 10.0))

    # a probe whose claimant closes, the duty armed 10 s on
    setup(duty=t0 + 10)
    ns["defer_on_claim"](g)
    ns["now"] = t0 + 0.1
    ns["claims_close"](q)
    line("closed, the duty armed 10 s on: the verdict, and the duty's time from the decision",
         (ns["probe_ok"].get(g, "none yet"), round(ns["reconsider_at"][g] - t0, 6)), (None, 10.0))

    # the control: a close when the duty was due at the decision
    setup()
    ns["defer_on_claim"](g)
    ns["now"] = t0 + 0.1
    ns["claims_close"](q)
    line("closed, the duty due at the decision (control): the duty's time from the decision",
         round(ns["reconsider_at"][g] - t0, 6), 0.1)

    # the control: a probe not yet settled is written
    setup()
    ns["defer_on_claim"](g)
    entry = probe_entry()
    ns["now"] = t0 + 0.3
    out = ns["filter_entry"](q, entry)
    line("not settled (control): probe asks written, and the probe's promise started",
         (asks_left(entry) if out is not None else 0, g in ns["probe_sent"]), (1, True))

    # the control: the claimant's own copy before the write passes the probe (option (a))
    setup()
    ns["defer_on_claim"](g)
    entry = probe_entry()
    i = ns["probe"][g]
    ns["now"] = t0 + 0.05
    ns["fill"](g, i, cells[i], q)
    ns["now"] = t0 + 0.1
    out = ns["filter_entry"](q, entry)
    line("own copy before the write (control): the verdict, probe asks written, probe written",
         (ns["probe_ok"].get(g), asks_left(entry) if out is not None else 0, g in ns["probe_sent"]),
         (True, 0, False))

    # after a probe given no verdict, a plain ask of the probed cell to the claimant, which answers it
    setup()
    ns["defer_on_claim"](g)
    entry = probe_entry()
    i = ns["probe"][g]
    at = ns["reconsider_at"][g]
    ns["now"] = at
    ns["known_in_scope"] = lambda g_: ns["all_bits"](T_row.index_count(ns["hdr"][g_])) if g_ == g else kis(g_)
    ns["reconsider"](g, at)                                 # no verdict, and no rebuild
    ns["known_in_scope"] = kis
    ns["filter_entry"](q, entry)                            # the probe, settled while queued, is dropped
    ask = ns["Ask"](g, i)
    ns["queue"][q].normal[:] = []
    ns["enqueue"](q, Wm.IWANT([ask]), False)                # the claimant offers the cell: a plain ask (§4.4)
    plain = ns["queue"][q].normal[-1]
    ns["now"] = at + 0.1
    ns["filter_entry"](q, plain)                            # written: its promise starts (protocol.md §6.1)
    started = (ask, q) in ns["promises"]
    ns["now"] = at + 0.2
    ns["fill"](g, i, cells[i], q)                           # the claimant answers it
    line("no verdict, then a plain ask the claimant answers: its promise started, and still open",
         (started, (ask, q) in ns["promises"]), (True, False))

    # the control: before the verdict, another peer's copy leaves the written probe's promise open
    setup()
    ns["defer_on_claim"](g)
    entry = probe_entry()
    i = ns["probe"][g]
    ns["now"] = t0 + 0.1
    ns["filter_entry"](q, entry)                            # the probe written: its promise starts
    other = next(x for x in sorted(nd.peers) if x != q)
    ns["now"] = t0 + 0.2
    ns["fill"](g, i, cells[i], other)
    line("written, another peer's copy first (control): the probe's promise still open, and no verdict",
         ((ns["Ask"](g, i), q) in ns["promises"], ns["probe_ok"].get(g, "none yet")), (True, "none yet"))

    # as the claimant, on row g2: cell j claimed and not stored, so a marked ask is kept while decoding
    p, r, s = sorted(nd.peers)[:3]
    j = sorted(ns["chunks"][g2])[0]
    f = ns["chunks"][g2][j]
    limit = T_row.params.SERVE_LIMIT

    def claimant(asks, slots=None):                         # asks: (peer, marked) in order of arrival; slots: the
        ns["state"][g2] = "DECODING"                        #   serving limit's slots left for p
        ns["chunks"][g2].pop(j, None)
        ns["known_id"][g2].pop(j, None)
        ns["received"][g2].clear(j); ns["rebuilt"][g2].clear(j)
        ns["standing"][g2].pop(j, None)
        ns["probe_waiting"][g2].clear()
        for x in (p, r):
            ns["queue"][x].normal[:] = []; ns["queue"][x].urgent[:] = []
            ns["probe_served"][x][g2] = False
            ns["probe_answers"][x][g2].clear(j)
        if slots is not None:
            ns["served"][p][g2] = limit - slots
        before = {x: ns["served"][x][g2] for x in (p, r)}
        for x, marked in asks:
            ns["on_want"](x, [Wm.FlaggedWant(g2, j, True, 0, probe=marked)])
        ns["fill"](g2, j, f, s)                             # the cell is stored

        def answers(x):
            qx = ns["queue"][x]
            return sum(1 for e in list(qx.urgent) + list(qx.normal) if e.chunk is f and e.solicited)
        return {x: (answers(x), ns["served"][x][g2] - before[x], bool(ns["probe_served"][x][g2])) for x in (p, r)}

    out = claimant([(p, True), (r, False)])
    line(f"peer {p}'s marked standing ask: answers queued, charges, and its exemption taken", out[p], (1, 1, True))
    line(f"peer {r}'s plain standing ask (control): answers queued, and charges", out[r][:2], (1, 1))
    line(f"peer {p}'s marked ask twice: answers queued, charges, and its exemption taken",
         claimant([(p, True), (p, True)])[p], (1, 1, True))
    line(f"peer {p}'s plain standing ask, then its marked ask: answers queued, charges, and the exemption taken",
         claimant([(p, False), (p, True)])[p], (1, 1, True))
    line(f"peer {p}'s marked ask, then its plain standing ask: answers queued, charges, and the exemption taken",
         claimant([(p, True), (p, False)])[p], (1, 1, True))
    line(f"peer {p}'s marked ask twice, one slot left: answers queued, charges, and the exemption taken",
         claimant([(p, True), (p, True)], slots=1)[p], (1, 1, True))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
