#!/usr/bin/env python3
"""A known answer for §7.1's wake when a write waits (`protocol.md`, and `protocol-v2.md` §4.11): a writer in the
window's line that writes control wakes the first writer in line that can write when its write starts to wait for
the transport (`write_waits`), and not before the write.

    python3 write_wait_known.py [--doc v2]

The check, on one node of a small network that is built and not run, a new network for each case: the window is
empty, and two peers wait in its line, p first, then q. A run queued for q is an event in the simulator's queue that
runs q's writer, and the check reads the queue itself. For each way p's writer writes control (an urgent entry; owed
offers on their own; and, under `protocol-v2.md`, a control-only entry of the normal lane):
- (a) `next_to_send(p)` returns the control, and q has no run queued: the wake does not come before the write.
  v0.10.7 and v0.10.8 woke q here, and this case fails on them.
- (b) p's writer writes the control, and its transport takes no more after it (the toy's send buffer is full): the
  write waits, and q has a run queued. With no wake at all, q would wait though the window is empty.
- (c) as (b), with p not in line: no run is queued for q.
- (d) as (b), with the window full: no run is queued for q, since no slot (or room) is free.
In (a), (b) and (d), p keeps its place at the head of the line.
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


def queued(sim, node, peer):
    """Whether the simulator's queue holds a run of node's writer for peer (Node.kick's event)."""
    return any(e[2] is node and e[3] == node._write and e[4] == (peer,) for e in sim.q)


def setup(sim, kind, in_line, full=False):
    import wire as Wm
    from bits import bitmap
    node = sim.nodes[NODE]
    ns = node.ns
    if queued(sim, node, Q) or Q in node.writer_kicked or P in node.writer_kicked:
        raise SystemExit("write_wait_known.py: the network as built already has a writer's run queued")
    w = ns["waiters"]
    w.clear()
    if in_line:
        w.append(P)
    w.append(Q)
    ns["in_flight"] = (ns["W_BYTES"] if "W_BYTES" in ns else ns["W"]) if full else 0   # full, or empty
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
    node.writer_blocked.discard(P)
    node.writer_blocked.discard(Q)
    sim.links[NODE].backlog[P] = 0
    return node, ns


def woken(sim, node):
    """q has a run queued; the flag Node.kick keeps must agree with the queue."""
    w = queued(sim, node, Q)
    if w != (Q in node.writer_kicked):
        raise SystemExit("write_wait_known.py: q's flag and the simulator's queue disagree")
    return w


def before_write(doc_v2, kind):
    sim = build(doc_v2)
    node, ns = setup(sim, kind, True)
    out = ns["next_to_send"](P)
    wrote = out is not None and out is not ns["WAIT"] and not out.chunk
    return wrote, woken(sim, node), list(ns["waiters"])[:1] == [P]


def write_waits(doc_v2, kind, in_line, full=False):
    sim = build(doc_v2)
    node, ns = setup(sim, kind, in_line, full)
    if sim.send_buffer is None:
        raise SystemExit("write_wait_known.py: the network has no send buffer, so no write can wait")
    node._write(P)
    return P in node.writer_blocked, woken(sim, node), list(ns["waiters"])[:1] == [P]


def main():
    if sys.argv[1:] not in ([], ["--doc", "v2"]):
        print("usage: write_wait_known.py [--doc v2]")
        return 2
    doc_v2 = sys.argv[1:] == ["--doc", "v2"]
    kinds = ["an urgent entry", "owed offers on their own"]
    if doc_v2:
        kinds.append("a control-only entry of the normal lane")
    bad = 0
    for kind in kinds:
        wrote, woke, place = before_write(doc_v2, kind)
        ok = wrote and not woke and place
        print(f"(a) p in line, {kind}: next_to_send returns it {wrote}, q woken {woke}, p keeps its place {place}: "
              f"{'no wake before the write' if ok else 'not as the rule says  <-- FAIL'}")
        bad += not ok
        waits, woke, place = write_waits(doc_v2, kind, True)
        ok = waits and woke and place
        print(f"(b) p in line, {kind}, the write waits {waits}: q woken {woke}, p keeps its place {place}: "
              f"{'the next writer that can write is woken' if ok else 'not as the rule says  <-- FAIL'}")
        bad += not ok
        waits, woke, _ = write_waits(doc_v2, kind, False)
        ok = waits and not woke
        print(f"(c) p not in line, {kind}, the write waits {waits}: q woken {woke}: "
              f"{'nothing woken' if ok else 'a wake for a writer not in line  <-- FAIL'}")
        bad += not ok
        waits, woke, place = write_waits(doc_v2, kind, True, full=True)
        ok = waits and not woke and place
        print(f"(d) p in line, the window full, {kind}, the write waits {waits}: q woken {woke}, p keeps its place "
              f"{place}: {'nothing woken' if ok else 'not as the rule says  <-- FAIL'}")
        bad += not ok
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
