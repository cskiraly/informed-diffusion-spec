#!/usr/bin/env python3
"""A known answer for §7.1's wake when a write waits (`protocol.md`, and `protocol-v2.md` §4.11): a writer in the
window's line that writes control wakes the first writer in line that can write when its write starts to wait for
the transport (`write_waits`), and not before the write.

    python3 write_wait_known.py [--doc v2]

The check, on one node of a small network that is built and not run: the window is empty, and two peers wait in its
line, p first, then q. For each way p's writer writes control (an urgent entry; owed offers on their own; and, under
`protocol-v2.md`, a control-only entry of the normal lane):
- (a) `next_to_send(p)` returns the control, and q has no run queued: the wake does not come before the write. The
  code before v0.10.9 woke q here, and this part fails on it.
- (b) p's writer writes the control, and its transport takes no more after it (the toy's send buffer is full): the
  write waits, and q has a run queued. With no wake at all, q would wait though the window is empty.
- (c) the control: as (b), with p not in line. No run is queued for q.
The toy is not changed: the check builds the network with `run.py`'s own options and sets the node's tables.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3
G = bytes([0x37]) * 32                              # a group no block commits


def build(doc_v2):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    got = {}
    saved = run.run
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    try:
        run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)]
                 + (["--doc", "v2"] if doc_v2 else []))
    finally:
        run.run = saved
    return got["sim"]


def setup(sim, kind, in_line):
    import wire as Wm
    from bits import bitmap
    node = sim.nodes[NODE]
    ns = node.ns
    w = ns["waiters"]
    w.clear()
    if in_line:
        w.append(P)
    w.append(Q)
    ns["in_flight"] = 0                             # the window is empty: a slot, or room, is free
    if "slot_held" in ns:
        ns["slot_held"][P] = False
    q = ns["queue"][P]
    q.urgent.clear()
    q.normal.clear()
    ns["owed"][P].clear()
    ctrl = Wm.IHAVE(Wm.HaveBitmap(G, bitmap({1})))
    if kind == "an urgent entry":
        q.urgent.append(Wm.Entry(control=ctrl))
    elif kind == "owed offers on their own":
        ns["owed"][P][G] = bitmap({1})
    else:                                           # a control-only entry of the normal lane (protocol-v2.md)
        q.normal.append(Wm.Entry(control=ctrl))
    node.writer_kicked.discard(Q)
    node.writer_blocked.discard(P)
    node.writer_blocked.discard(Q)
    sim.links[NODE].backlog[P] = 0
    return node, ns


def before_write(sim, kind):
    node, ns = setup(sim, kind, True)
    out = ns["next_to_send"](P)
    wrote = out is not None and out is not ns["WAIT"] and not out.chunk
    return wrote, Q in node.writer_kicked


def write_waits(sim, kind, in_line):
    node, ns = setup(sim, kind, in_line)
    if sim.send_buffer is None:
        raise SystemExit("write_wait_known.py: the network has no send buffer, so no write can wait")
    node._write(P)
    return P in node.writer_blocked, Q in node.writer_kicked


def main():
    if sys.argv[1:] not in ([], ["--doc", "v2"]):
        print("usage: write_wait_known.py [--doc v2]")
        return 2
    doc_v2 = sys.argv[1:] == ["--doc", "v2"]
    sim = build(doc_v2)
    kinds = ["an urgent entry", "owed offers on their own"]
    if doc_v2:
        kinds.append("a control-only entry of the normal lane")
    bad = 0
    for kind in kinds:
        wrote, woken = before_write(sim, kind)
        ok = wrote and not woken
        print(f"(a) p in line, {kind}: next_to_send returns it {wrote}, q woken {woken}: "
              f"{'no wake before the write' if ok else 'a wake before the write  <-- FAIL'}")
        bad += not ok
        waits, woken = write_waits(sim, kind, True)
        ok = waits and woken
        print(f"(b) p in line, {kind}, the write waits {waits}: q woken {woken}: "
              f"{'the next writer that can write is woken' if ok else 'q is not woken  <-- FAIL'}")
        bad += not ok
        waits, woken = write_waits(sim, kind, False)
        ok = waits and not woken
        print(f"(c) the control: p not in line, {kind}, the write waits {waits}: q woken {woken}: "
              f"{'nothing woken' if ok else 'a wake that should not happen  <-- FAIL'}")
        bad += not ok
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
