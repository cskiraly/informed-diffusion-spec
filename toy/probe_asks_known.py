#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.6's probe ask once the probe is settled.

    python3 probe_asks_known.py

The probe's ask is exempt from stop-pull while the probe waits (`probe_asks`, `gated`). Once the probe is settled,
by a pass, a failure or no verdict, the exemption goes: a member that is complete does not pull the probed cell
from another peer's offer, as it pulls no other cell of the group.

On one node of a small rows run (protocol-v2.md, one block, run to its end), made by hand, as the member, on a
row it holds, three of whose cells it is made to lack (taken out of its store), with one claimant and stop-pull
on (the member is complete):
- **a failure:** the probe written, the duty fires, the row whole in the subnet's view: the claimant is
  penalised and nothing is rebuilt;
- **no verdict, the probe still queued** when the duty fires, the row whole in view;
- **no verdict, the claimant closes;**
- **no verdict, a full queue refuses the probe.**

After each, another peer offers the probed cell: the member must not ask for it.
Controls: before the probe is settled, the same offer is asked for (the probe's exemption); in every case, an
offer of another cell the member lacks is not asked for (stop-pull); after a pass, the cell is held and the offer
is not asked for.
"""
import sys
from pathlib import Path

SEED, NODE = 7, 2


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    T_row = nd._types["row"]
    g = next(g for g in ns["T_of"] if sim.gtype.get(g) == "row"
             and len(ns["chunks"][g]) == T_row.index_count(ns["hdr"][g]))
    q, r = sorted(nd.peers)[:2]                            # q the claimant, r another peer that offers
    lack = sorted(ns["chunks"][g])[:3]
    cells = {i: ns["chunks"][g][i] for i in lack}
    t0 = ns["now"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def setup():                                            # the member, complete, before the claim
        ns["now"] = t0
        ns["state"][g], ns["deferred"][g] = "COMPLETE", False
        ns["stop_pull"][g] = True
        for i in lack:                                      # lacked: not claimed, not stored
            ns["mine"][g].clear(i)
            ns["chunks"][g].pop(i, None)
            ns["known_id"][g].pop(i, None)
            ns["received"][g].clear(i); ns["rebuilt"][g].clear(i)
        ns["probe_ok"].pop(g, None)
        ns["probe_sent"].discard(g)
        for a in [a for a in ns["probe_asks"] if ns["group"](a) == g]:   # each case's own probe only
            ns["probe_asks"].discard(a)
        ns["reconsider_at"].pop(g, None)
        ns["claims"][g].clear(); ns["claims"][g].add(q)
        for k in [k for k in ns["promises"] if k[1] in (q, r)]:
            del ns["promises"][k]
        for a in [a for a in list(ns["asked_at"]) if ns["group"](a) == g]:
            ns["asked_at"].pop(a, None); ns["tried"].pop(a, None)
        ns["queue"][q].normal[:] = []
        ns["queue"][r].normal[:] = []

    def offered(i):                                         # r offers cell i: the asks the member makes
        ns["now"] += 0.5                                    # past any ask window
        h = ns["Have"](group=g, bits=ns["bitmap"]({i}), offer=True, claim_all=False, complete=False)
        return [ns["index"](a) for a in ns["on_offer"](r, h)]

    def other(i):                                           # a lacked cell that is not the probe's
        return next(j for j in lack if j != i)

    def whole_in_view(fn):                                  # the duty fires with the row whole in the subnet's view
        kis = ns["known_in_scope"]
        ns["known_in_scope"] = lambda g_: ns["all_bits"](T_row.index_count(ns["hdr"][g_])) if g_ == g else kis(g_)
        try:
            fn()
        finally:
            ns["known_in_scope"] = kis

    def written():                                          # the queued probe written now (filter_entry)
        e = next(e for e in ns["queue"][q].normal
                 if any(getattr(ns["group_index"](a), "probe", False) for c in e.iwants() for a in c.ids))
        ns["filter_entry"](q, e)

    # the control: before the probe is settled
    setup()
    ns["defer_on_claim"](g)
    i = ns["probe"][g]
    line("waiting (control): the verdict; asks for the probed cell, and for another lacked one",
         (ns["probe_ok"].get(g, "none yet"), offered(i), offered(other(i))), ("none yet", [i], []))

    # a failure
    setup()
    ns["defer_on_claim"](g)
    i = ns["probe"][g]
    ns["now"] = t0 + 0.05
    written()
    at = ns["reconsider_at"][g]
    ns["now"] = at
    whole_in_view(lambda: ns["reconsider"](g, at))
    line("failed: the verdict; asks for the probed cell, and for another lacked one",
         (ns["probe_ok"].get(g, "none yet"), offered(i), offered(other(i))), (False, [], []))

    # no verdict, the probe still queued when the duty fires
    setup()
    ns["defer_on_claim"](g)
    i = ns["probe"][g]
    at = ns["reconsider_at"][g]
    ns["now"] = at
    whole_in_view(lambda: ns["reconsider"](g, at))
    line("no verdict, queued: the verdict; asks for the probed cell, and for another lacked one",
         (ns["probe_ok"].get(g, "none yet"), offered(i), offered(other(i))), (None, [], []))

    # no verdict, the claimant closes
    setup()
    ns["defer_on_claim"](g)
    i = ns["probe"][g]
    ns["now"] = t0 + 0.1
    ns["claims_close"](q)
    line("no verdict, closed: the verdict; asks for the probed cell, and for another lacked one",
         (ns["probe_ok"].get(g, "none yet"), offered(i), offered(other(i))), (None, [], []))

    # no verdict, a full queue refuses the probe
    setup()
    send = ns["send"]
    ns["send"] = lambda p, m, urgent=False: False if getattr(m, "probe", False) else send(p, m, urgent)
    ns["defer_on_claim"](g)
    ns["send"] = send
    i = ns["probe"][g]
    line("no verdict, refused: the verdict; asks for the probed cell, and for another lacked one",
         (ns["probe_ok"].get(g, "none yet"), offered(i), offered(other(i))), (None, [], []))

    # the control: a pass, the claimant's own copy
    setup()
    ns["defer_on_claim"](g)
    i = ns["probe"][g]
    ns["now"] = t0 + 0.05
    written()
    ns["now"] = t0 + 0.1
    ns["fill"](g, i, cells[i], q)
    line("passed (control): the verdict, the cell held; asks for the probed cell, and for another lacked one",
         (ns["probe_ok"].get(g, "none yet"), ns["mine"][g].has(i), offered(i), offered(other(i))),
         (True, True, [], []))

    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
