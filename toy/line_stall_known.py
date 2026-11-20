#!/usr/bin/env python3
"""A known answer for the window's line (§7.1, §7.3): a peer that stops reading does not hold the node's chunks to
its other peers.

    python3 line_stall_known.py [--doc v2]    # protocol.md, or protocol-v2.md's window in bytes (its §4.11)

The line is first come first served, and a writer keeps its place while it waits. A writer whose write has not
completed (§7.3: the transport has not taken all but about one chunk of it) cannot take a slot, so it keeps its place
but not the line's front: `acquire_slot` admits the first waiter whose writer can write (`writing`). Without that, a
peer that stops reading while its writer heads the line holds every free slot: each one wakes it to no effect, and no
other writer may take one.

The check, on the cell `push`'s network (60 nodes, degree 30, three payloads, seed 7), run from the first publish:
when the source's line first holds two writers, the peer at its head stops reading (the source's link to it stops
draining: done here, around the toy's link, which is not changed) and an urgent entry for it is written, so its
writer blocks while it heads the line. Then, over the next two seconds:
- **the source's other peers are not held up:** within that time it sends them chunks, or has none left for them;
  where the head held the line, it sends them none while chunks wait in their queues and slots are free;
- the stalled peer is handed no chunk after it (its writer stays blocked);
- control still flows: the source hands its transport control-only entries for its other peers.
The control: the same run with the peer reading; its other peers are not held up either.

With `--doc v2` the same run reaches `protocol-v2.md`'s window, which counts bytes (`W_BYTES`) and has the same line
(its §4.11, `acquire_room`): its `acquire_room` admits the first waiter whose writer can write, as `acquire_slot`
does. Before it did, the check failed there as here.
"""
import sys
from pathlib import Path

SEED, CELL = 7, ["--nodes", "60", "--degree", "30", "--msgs", "3"]
if sys.argv[1:] not in ([], ["--doc", "v2"]):
    sys.exit("usage: line_stall_known.py [--doc v2]")
V2 = sys.argv[1:] == ["--doc", "v2"]
STEP, SPAN = 0.001, 2.0


def run(stall):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run as R
    import sim as S
    got = {}
    real_run = R.run
    R.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    try:
        R.main(CELL + ["--seed", str(SEED)] + (["--doc", "v2"] if V2 else []))
    finally:
        R.run = real_run
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"])
    sim.publish(1)
    src = sim.nodes[1]                                  # node 1 publishes (sim.publish)
    ns = src.ns
    (g, _), = sim.canonical.items()
    stalled = set()
    log = []                                            # (time, peer, carries a chunk, urgent control only)

    orig_start = S.Sim._ps_start
    def ps_start(self, ln, p):                          # a peer that stops reading: its connection takes no more
        if ln is self.links[src.id] and p in stalled:
            return
        return orig_start(self, ln, p)
    orig_tx = S.Sim.transmit
    def transmit(self, node, p, e):
        if node is src:
            log.append((self.now, p, bool(e.chunk), not e.chunk))
        return orig_tx(self, node, p, e)
    S.Sim._ps_start, S.Sim.transmit = ps_start, transmit
    try:
        t = sim.now
        while not (len(ns["waiters"]) >= 2 and ns["waiters"][0] not in src.writer_blocked):
            t += STEP
            sim.run(t)
            if t > cfg["first"] + 30:
                raise SystemExit("the source's line never formed")
        head, ts = ns["waiters"][0], sim.now
        if stall:
            stalled.add(head)
        log.clear()                                     # from here on: what the source hands its transport
        ns["send_have"](head, g)                        # an urgent entry: the head's writer writes it
        sim.run(ts + SPAN)
        late = [x for x in log if x[0] >= ts + 0.6]     # past WINDOW_TIMEOUT: every chunk in flight at the stall
        others = {p for p in src.peers if p != head}    #   is released by then
        sent_others = sum(1 for x in late if x[1] in others and x[2])
        waiting = sum(1 for p in others if p in ns["queue"] and ns["queue"][p].has_chunks())
        to_head = sum(1 for x in log if x[1] == head and x[2])
        ctrl_others = sum(1 for x in log if x[1] in others and x[3])
        return dict(head=head, t=round(ts, 4), sent_others=sent_others, waiting=waiting, to_head=to_head,
                    ctrl_others=ctrl_others, in_flight=ns["in_flight"], W=ns["W_BYTES" if V2 else "W"],
                    line=len(ns["waiters"]),
                    head_writing=head in src.writer_blocked)
    finally:
        S.Sim._ps_start, S.Sim.transmit = orig_start, orig_tx


def main():
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    for stall in (False, True):
        r = run(stall)
        print(f"{'the head stops reading' if stall else 'the control: the head reads'} (peer {r['head']}, "
              f"t={r['t']}): {r}")
        line(("**" if stall else "") + "the other peers are not held up: chunks sent to them past the window "
             "timeout, or none left for them" + ("**" if stall else ""),
             r["sent_others"] > 0 or r["waiting"] == 0, True)
        if stall:
            line("the stalled head is handed no chunk after the stall, and its writer is still blocked",
                 (r["to_head"], r["head_writing"]), (0, True))
        line("the source hands its transport control-only entries for its other peers", r["ctrl_others"] > 0, True)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
