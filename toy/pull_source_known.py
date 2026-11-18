#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.7's publish of a pull-only type (EAGER off): the source pushes nothing and
offers every chunk at publish, since with nothing pushed no acknowledgement can come.

    python3 pull_source_known.py

On a small payload run (one payload), every node's payload type is made pull-only before the publish. At the
publish, the source must enqueue no chunk, and offer each chunk to some peer; its holding names every chunk. Run to
its end, every node must complete the payload, by asks alone. The control: the same run with the type eager, where
the source pushes, which shows that the count sees pushes.
"""
import sys
from pathlib import Path


def build(args):
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(args)
    return got["sim"]


def one(eager):
    sim = build(["--doc", "v2", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7"])
    cfg = sim.cfg
    for nd in sim.nodes.values():
        nd._types["payload"].params.EAGER = eager
    ns = sim.nodes[1].ns                                    # the publisher (node 1 unless a dump names one)
    seen = {"pushed": set(), "offered": set(), "g": None}
    enq, snd, pub = ns["enqueue"], ns["send"], ns["publish"]

    def enqueue(q, m, *a, **k):
        if getattr(m, "index", None) is not None and getattr(m, "data", None) is not None:
            seen["pushed"].add(m.index)
        return enq(q, m, *a, **k)

    def send(q, m, *a, **k):
        if getattr(m, "offer", False):
            seen["offered"] |= set(m.bits)
        return snd(q, m, *a, **k)

    def publish(block, d, shards):
        ns["enqueue"], ns["send"] = enqueue, send
        try:
            pub(block, d, shards)
        finally:
            ns["enqueue"], ns["send"] = enq, snd
        seen["g"] = ns["group_of"](block, d)
        seen["n"] = ns["N"](d)
    ns["publish"] = publish
    sim.run(cfg["first"]); sim.publish(1)
    g, n = seen["g"], seen["n"]
    holding = [j for j in range(n) if ns["origin"][g].has(j)]  # what its holding names (§4.7)
    sim.run(cfg["first"] + cfg["gap"])
    done = sum(nd.ns["state"][g] == "COMPLETE" for nd in sim.nodes.values())
    return len(seen["pushed"]), len(seen["offered"]), n, len(holding), done, len(sim.nodes)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    pushed, offered, n, held, done, nodes = one(eager=True)
    line("the control, eager: chunks the source pushed at its publish, any", pushed > 0, True)
    pushed, offered, n, held, done, nodes = one(eager=False)
    line("pull-only: chunks the source pushed at its publish", pushed, 0)
    line("pull-only: chunks it offered at its publish, of N", (offered, n), (n, n))
    line("pull-only: chunks its holding names after its publish, of N", (held, n), (n, n))
    line("pull-only: nodes that completed the payload, of all", (done, nodes), (nodes, nodes))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
