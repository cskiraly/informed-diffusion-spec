#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.11: a writer in line that writes a control-only entry of the normal lane
first wakes the first other writer in line that can write, as for an urgent entry or owed offers on their own.

    python3 control_wake_known.py [--doc v2]

It runs `protocol-v2.md` either way: `protocol.md`'s control-only entry goes through `release_unused_slot`.

A writer waits in the window's line and keeps its place there (`acquire_room`). When it writes control, which
takes no room, its write may not complete (§7.3 of `protocol.md`), so it must not hold the room it leaves free: it
wakes the first other writer in line that can write (`wake_front(past=p)`). A control-only entry reaches the normal
lane's head when the writer's queued chunks are discarded, a dropped or expired group's say.

The check, on one node of a small network that is built and not run: two peers wait in the line, p first, then q,
the window empty. p's normal lane holds one control-only entry (an offer), its urgent lane and owed offers nothing,
and p's writer runs (`next_to_send`). It must write the offer and leave q's writer with a run queued. The control:
the same with p not in the line, where nothing is woken. On the document before the wake, q was left unwoken: the
check fails there.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3
G = bytes([0x37]) * 32                              # a group no block commits


def check(in_line):
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
    w = ns["waiters"]
    w.clear()
    if in_line:
        w.append(P)
    w.append(Q)
    q = ns["queue"][P]
    q.urgent.clear()
    q.normal.clear()
    q.normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(G, bitmap({1})))))   # control only: no room
    node.writer_kicked.discard(Q)
    node.writer_blocked.discard(P)
    node.writer_blocked.discard(Q)
    out = ns["next_to_send"](P)
    wrote = out is not None and out is not ns["WAIT"] and not out.chunk
    return wrote, Q in node.writer_kicked, ns["in_flight"]


def main():
    if sys.argv[1:] not in ([], ["--doc", "v2"]):
        print("usage: control_wake_known.py [--doc v2]")
        return 2
    bad = 0
    wrote, woken, inf = check(True)
    ok = wrote and woken and inf == 0
    print(f"p in line writes a control-only entry: written {wrote}, q woken {woken}, in_flight {inf}: "
          f"{'the next writer that can write takes the free room' if ok else 'NOT as protocol-v2.md §4.11 says  <-- FAIL'}")
    bad += not ok
    wrote, woken, inf = check(False)
    ok = wrote and not woken
    print(f"the control: p not in line writes it: written {wrote}, q woken {woken}: "
          f"{'nothing woken' if ok else 'a wake that should not happen  <-- FAIL'}")
    bad += not ok
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
