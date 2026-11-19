#!/usr/bin/env python3
"""A known answer for protocol-v2.md's rule that a WANT starts no promise at its write (§4.5, §4.10, §5's row
on v0.5 §7.2): `filter_entry` starts v0.5's promise for an ask made on an offer, and not for an ask that a WANT
carries, whose sender has its own timers (a sampler's `SAMPLE_RETRY`, the repair sample's `SAMPLE_WAIT`, a
routed request's sampler); a claim's probe keeps the promise of §4.6.

    python3 want_promise_known.py [--doc v2]

It runs `protocol-v2.md` either way: `protocol.md` has no WANT.

The check, on one node of a small network that is built and not run: the node sends a peer a WANT for one
index of a group, through the binding's `send` (v0.3's wire, `protocol-v2-bindings.md` §3, where the toy marks
the IWANT that carries a WANT), and the entry queued for it is written (`filter_entry`). No promise may start
for that ask. The control: an ask on an offer, an IWANT not so marked, written the same way, must start one.
And a claim's probe, a WANT that keeps a promise (§4.6): its first write must start one, and so must a write
of it again once its group is in `probe_sent` and its first promise is gone, as the toy's wrapper left it. On
the document before the rule was in its code, `filter_entry` started a promise for every ask, and the toy took
the WANT's away in a wrapper; with the wrapper taken out the check fails there. Without the probe's half of
the rule (`or probe_waits(a, p)`) the probe's second write fails.
"""
import sys
from pathlib import Path

SEED, NODE, PEER = 7, 2, 1
G = bytes([0x36]) * 32                              # a group no block commits


def main():
    if sys.argv[1:] not in ([], ["--doc", "v2"]):
        print("usage: want_promise_known.py [--doc v2]")
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    from bits import bitmap
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED),
              "--doc", "v2"])
    node = got["sim"].nodes[NODE]
    ns = node.ns

    def promised(i):
        return [k for k in ns["promises"] if k[1] == PEER and ns["group"](k[0]) == G and ns["index"](k[0]) == i]

    q = node.queues[PEER] if hasattr(node, "queues") else ns["queue"][PEER]
    before = len(q.normal)
    ns["send"](PEER, ns["Want"](group=G, bits=bitmap({3}), standing=True, hops=0, probe=False), urgent=False)
    entries = q.normal[before:]
    if len(entries) != 1:
        print(f"the WANT queued {len(entries)} entries, not one  <-- FAIL")
        print("FAIL")
        return 1
    out = ns["filter_entry"](PEER, entries[0])
    written = out is not None and any(ns["index"](a) == 3 for c in out.iwants() for a in c.ids)
    want_ok = written and not promised(3)
    print(f"a WANT for index 3, written {written}: promises {len(promised(3))}: "
          f"{'none, as §4.5 says' if want_ok else 'NOT as protocol-v2.md §4.5 says  <-- FAIL'}")

    entry = Wm.Entry(control=Wm.IWANT([ns["Ask"](G, 5)]))   # an ask on an offer, as respond queues it
    out = ns["filter_entry"](PEER, entry)
    written = out is not None and any(ns["index"](a) == 5 for c in out.iwants() for a in c.ids)
    ask_ok = written and len(promised(5)) == 1
    print(f"the control: an ask on an offer for index 5, written {written}: promises {len(promised(5))}: "
          f"{'one, v0.5 §7.2' if ask_ok else 'NOT as v0.5 §7.2 says  <-- FAIL'}")
    # A claim's probe is a WANT too, but keeps a promise (§4.6): its first write starts the probe's, and
    # a write of it again, once its group is in probe_sent and its promise gone, starts v0.5's plain one.
    ns["deferred"][G], ns["probed"][G], ns["probe"][G] = True, PEER, 7
    probe_ok = []
    for n in (1, 2):
        before = len(q.normal)
        ns["send"](PEER, ns["Want"](group=G, bits=bitmap({7}), standing=False, hops=0, probe=True), urgent=False)
        out = ns["filter_entry"](PEER, q.normal[before])
        written = out is not None and any(ns["index"](a) == 7 for c in out.iwants() for a in c.ids)
        ok = written and len(promised(7)) == 1
        print(f"the probe of index 7, write {n}, written {written}: promises {len(promised(7))}: "
              f"{'one, §4.6' if ok else 'NOT as protocol-v2.md §4.6 says  <-- FAIL'}")
        probe_ok.append(ok)
        for k in promised(7):
            del ns["promises"][k]                       # gone, as a timer or a close would take it
    bad = (not want_ok) + (not ask_ok) + probe_ok.count(False)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
