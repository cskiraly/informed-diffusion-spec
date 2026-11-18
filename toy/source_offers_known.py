#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.7's SOURCE_OFFERS: at PUBLISH the source's offers leave at publish and its
holding grows only at a chunk's first write, as before v0.9's rules, so an acknowledgement does nothing.

    python3 source_offers_known.py

On a small coded payload run (one payload, writes one at a time, a 10 Mbps source among faster peers), peers decode
at K and acknowledge rebuilt chunks, some before the source has written them. At the source, every call of
origin_acked is watched: whether it grew the holding or offered. At PUBLISH it must do neither. The control: at ACK
the same run's origin_acked acts, and some of it before the chunk's first write, which shows the run meets the case.
"""
import sys
from collections import Counter
from pathlib import Path


ARGS = ["--doc", "v2", "--nodes", "16", "--degree", "8", "--msgs", "1", "--seed", "7", "--send-buffer", "1",
        "--net", "bld", "--builder-mbps", "10"]          # a 10 Mbps source among faster peers: some decode early


def one(offers, args=None):
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main((args or ARGS) + ["--source-offers", offers])
    sim, cfg = got["sim"], got["sim"].cfg
    ns = sim.nodes[1].ns                                    # the publisher
    seen = {"acted": 0, "early": 0, "offered": Counter()}
    acked, ann, written = ns["origin_acked"], ns["announce"], set()
    track = ns["track_in_flight"]

    def track_in_flight(p, f, need):
        written.add((f.group, f.index))
        return track(p, f, need)

    def announce(p, g, bits):
        for i in bits:
            seen["offered"][(p, g, i)] += 1
        return ann(p, g, bits)

    def origin_acked(g, i):
        before = ns["origin"][g].has(i) if g in ns["origin"] else None
        n = sum(seen["offered"].values())
        acked(g, i)
        after = ns["origin"][g].has(i) if g in ns["origin"] else None
        if after != before or sum(seen["offered"].values()) != n:
            seen["acted"] += 1
            seen["early"] += (g, i) not in written
    ns["origin_acked"], ns["announce"], ns["track_in_flight"] = origin_acked, announce, track_in_flight
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    twice = sum(1 for v in seen["offered"].values() if v > 1)
    return seen["acted"], seen["early"], twice


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    acted, early, _ = one("on")
    line("the control, ACK: acknowledgements that grew the holding or offered, any; and before a first write, any",
         (acted > 0, early > 0), (True, True))
    acted, early, _ = one("publish")
    line("PUBLISH: acknowledgements that grew the holding or offered", acted, 0)
    line("PUBLISH: of them, before the chunk's first write", early, 0)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
