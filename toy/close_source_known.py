#!/usr/bin/env python3
"""A known answer for a connection's close at a source (the toy's drop_peer, protocol-v2.md §3's lifetimes): the
room a closed peer's chunks held in flight is released, and that is not the chunks' acknowledgement. A closed
connection drops its copy's room (protocol.md §8.1); a chunk is acknowledged at a holding naming it or at a copy's
window timeout (§4.7), so a close leaves the source's holding and its offers as they were.

    python3 close_source_known.py

On a small payload run, a millisecond after the publish, the source's link to a peer it is pushing to closes while a copy
is in flight and before any holding names the chunk. The room must come back, and the chunk must not join the
source's holding nor be offered because of the close. The control: the same copy's window timeout, called
directly on a second run, does acknowledge the chunk, which shows the watch sees an acknowledgement.
"""
import sys
from pathlib import Path


def run_to_publish():
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7"])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + 0.001)   # the writer's first writes
    return sim


def in_flight(sim):
    """The source and one copy of its, in flight, of a chunk no holding names yet."""
    nd = sim.nodes[1]
    ns = nd.ns
    for key in sorted(ns["sent"], key=str):
        q, g, i = key
        if g in ns["origin"] and not ns["origin"][g].has(i):
            return nd, key
    return nd, None


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    sim = run_to_publish()
    nd, key = in_flight(sim)
    line("a copy in flight of a chunk no holding names, a millisecond after the publish", key is not None, True)
    if key is None:
        print("FAIL")
        return 1
    ns = nd.ns
    q, g, i = key
    offers, ann = [], ns["announce"]
    ns["announce"] = lambda p, gg, bits: (offers.append((p, gg, bits)), ann(p, gg, bits))[1]
    nd.drop_peer(q)
    ns["announce"] = ann
    line("the close: the copy's room released", key in ns["sent"], False)
    line("the close: the chunk in the source's holding", ns["origin"][g].has(i), False)
    line("the close: offers of the group it made", sum(1 for _, gg, _ in offers if gg == g), 0)

    sim = run_to_publish()
    nd, key = in_flight(sim)
    ns = nd.ns
    q, g, i = key
    ns["window_timeout"](key, ns["sent"][key][0])
    line("the control, the copy's window timeout: the chunk in the source's holding", ns["origin"][g].has(i), True)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
