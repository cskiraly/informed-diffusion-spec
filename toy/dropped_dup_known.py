#!/usr/bin/env python3
"""A known answer for §4.2's duplicate path in a dropped group: a copy of a chunk the node stored is acknowledged,
whether or not the group was dropped since.

    python3 dropped_dup_known.py        # protocol.md, then protocol-v2.md on top of it

`on_chunk` acknowledges a copy of a chunk it has seen if `accepted(mid)`, and §8.1's list says what that is: "the
id was stored". `drop_group` (§4.6) marks the group invalid and keeps its stored chunks, so a copy of one of them
is still acknowledged with a HAVE ("its HAVEs stay"). A chunk that first arrives after the drop passes level 1, is
marked seen and is not stored (§4.2: "a chunk of a dropped group"), so a copy of it is ignored.

The check, on one node of a small network that is built and not run, its one payload published (K = 4, N = 8):
the publisher's copy of chunk 0 arrives and is stored; a second copy of it from another peer is acknowledged (the
control, before any drop); the node drops the group; chunk 1's first copy arrives and is not stored. Then a copy
of chunk 0 must be acknowledged, and a copy of chunk 1 must not (the control). The HAVEs are counted on the urgent
lane of the copy's sender, where `send_have` puts them; no copy counts against its sender.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3          # node 2; peer 1 publishes; peer 3 sends the second copies


def check(doc):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "65536", "--seed", str(SEED)]
             + (["--doc", "v2"] if doc == "v2" else []))
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"])
    sim.publish(1)                                          # the block installs, its chunks exist; nothing delivered
    nd = sim.nodes[NODE]
    ns = nd.ns
    (g, chunks), = sim.canonical.items()
    f0, f1 = chunks[0], chunks[1]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def haves(q):                                           # the HAVEs of g queued to q, each as the indices it names
        out = []
        for e in ns["queue"][q].urgent:
            for m in (e.control.items if e.control else ()):
                out += [sorted(x.bits) for x in m.ids if m.kind == "idontwant" and isinstance(x, Wm.HaveBitmap)
                        and x.group == g]
        return out

    def copy_from(q, f):                                    # one copy of f from q: the HAVEs it adds to q's queue
        before, pen = len(haves(q)), nd.penalties
        ns["on_chunk"](q, f)
        return haves(q)[before:], nd.penalties - pen

    ns["on_chunk"](P, f0)
    line("chunk 0 from the publisher: stored, and seen", (0 in ns["chunks"][g], ns["seen"](ns["message_id"](f0))),
         (True, True))
    line("the control: a second copy of chunk 0, before any drop, adds a HAVE of [0] (the HAVEs added, penalties)",
         copy_from(Q, f0), ([[0]], 0))
    ns["drop_group"](g)
    line("drop_group: the group is invalid, chunk 0 still stored", (ns["state"][g], 0 in ns["chunks"][g]),
         ("INVALID", True))
    added = copy_from(P, f1)
    line("chunk 1's first copy after the drop: stored, seen, and the HAVEs it added",
         (1 in ns["chunks"][g], ns["seen"](ns["message_id"](f1)), added), (False, True, ([], 0)))
    line("a copy of chunk 0, stored before the drop, adds a HAVE of [0]", copy_from(Q, f0), ([[0]], 0))
    line("the control: a copy of chunk 1, seen and never stored, adds none", copy_from(Q, f1), ([], 0))
    return bad


def main():
    bad = 0
    for doc in ("v03", "v2"):
        print(f"--doc {doc}:")
        bad += check(doc)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
