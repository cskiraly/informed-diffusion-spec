#!/usr/bin/env python3
"""Known answers for protocol-v2.md §4.6's probe and its write (R5): the probe's promise and the verdict's wait
start when its WANT is written, and a probe not written gets no verdict.

    python3 probe_write_known.py

On one node of a small rows run (protocol-v2.md, one block, run to its end), for a row it holds, three of whose
cells it is made to lack, with one claimant, the deferral is made by hand (`defer_on_claim`) three times:
- **A probe a full queue refuses** (`send` returns False): no verdict, and the member's own repair is
  reconsidered at once; the duty, fired, penalises nobody.
- **A probe still unwritten when the wait ends** (queued, the writer never reaching it): no verdict when the duty
  fires, and nobody penalised, so a claimant that stops reading cannot hold the repair off.
- **A probe written 0.3 s after the decision** (the writer takes it then, `filter_entry`): its promise starts at
  the write, and the duty is re-armed `DEFER_WINDOW` after it. Unanswered, it is judged when the duty fires: the
  claimant fails and is penalised (the control: a written probe is still a verdict).
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
    W = T_row.params.DEFER_WINDOW
    q = sorted(nd.peers)[0]
    lack = sorted(ns["chunks"][g])[:3]                      # three cells the member lacks: the probe draws one
    t0 = ns["now"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def setup():
        ns["now"] = t0
        ns["state"][g], ns["deferred"][g] = "COMPLETE", False
        for i in lack:                                      # (a fired duty's rebuild claims them all again)
            ns["mine"][g].clear(i)
        ns["probe_ok"].pop(g, None)
        if "probe_sent" in ns:
            ns["probe_sent"].discard(g)
        ns["reconsider_at"].pop(g, None)
        ns["claims"][g].clear(); ns["claims"][g].add(q)
        for k in [k for k in ns["promises"] if k[1] == q]:
            del ns["promises"][k]
        ns["queue"][q].normal[:] = []

    def fire():                                             # the duty fires when it is armed
        at = ns["reconsider_at"].get(g)
        ns["now"] = at
        pen = nd.penalties
        ns["reconsider"](g, at)
        return nd.penalties - pen

    # a probe a full queue refuses
    setup()
    send = ns["send"]
    ns["send"] = lambda p, m, urgent=False: False if getattr(m, "probe", False) else send(p, m, urgent)
    ns["defer_on_claim"](g)
    ns["send"] = send
    line("refused: the verdict, and the duty's time (now)",
         (g in ns["probe_ok"], ns["probe_ok"].get(g), ns["reconsider_at"].get(g)), (True, None, t0))
    line("refused: penalties when the duty fires", fire(), 0)

    # a probe still unwritten when the wait ends
    setup()
    ns["defer_on_claim"](g)
    line("unwritten: the duty armed DEFER_WINDOW after the decision", ns["reconsider_at"].get(g), t0 + W)
    pen = fire()
    line("unwritten: the verdict, and penalties when the duty fires", (ns["probe_ok"].get(g, "none yet"), pen),
         (None, 0))

    # a probe written 0.3 s after the decision
    setup()
    ns["defer_on_claim"](g)
    ns["now"] = t0 + 0.3
    entry = ns["queue"][q].normal[-1]
    ns["filter_entry"](q, entry)
    a = next(k[0] for k in ns["promises"] if k[1] == q)
    line("written at +0.3 s: the promise's start, and the duty's time",
         (round(ns["promises"][(a, q)] - t0, 6), round(ns["reconsider_at"].get(g) - t0, 6)), (0.3, round(0.3 + W, 6)))
    pen = fire()
    line("written, unanswered (the control): the verdict, and penalties when the duty fires",
         (ns["probe_ok"].get(g), pen), (False, 1))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
