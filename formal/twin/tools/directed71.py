#!/usr/bin/env python3
"""Directed records for §7.1's window (protocol.md, v0.10.7): front, wake_front, acquire_slot,
release_unused_slot, track_in_flight, window_release, window_timeout and free_slot. The toy's own functions are
called in a toy node's namespace on generated states, and trace3.py's tracer logs each call with the node's whole
state.

    python3 directed71.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not, or that few do:
- **release_unused_slot with the peer in line** (no cell, no other set): it leaves the line; the next is woken
  where a slot is free and not where none is; the peer alone in line; holding a slot too (freed after);
- window_timeout whose send is still in flight at that time (without-a and late-block alone), for a group the
  node publishes (origin_acked asked) and for another; a stale timer after a resend; a timer of a send released;
- track_in_flight with a second copy still in flight (three cells, 66 calls): the slot goes back at once;
- acquire_slot: the window full; a slot free and nobody in line; the peer first in line, with others behind and a
  slot left for the next or none; another peer first (it joins the line, or keeps its place);
- the line's front (v0.10.7): writers mid-write (`writing`, from the node's writer_blocked, drawn) passed over, by
  front and wake_front called by themselves (wake_front with `past` in half, next_to_send's form, and with no
  slot free) and through acquire_slot, release_unused_slot and free_slot: the peer behind a writer mid-write takes
  a slot; nobody in line can write; the first can;
- free_slot at 0 (the count goes below zero: no state of the toy's, and the signed entry's reason), and with
  somebody in line;
- a node with no window (W infinite: card 14 off): every count is under it.

The states are in the toy's own forms: the count a number, the line a deque of peers, `sent` a dict from (peer,
group, index) to the send's time, `slot_held` a peer's flag, `planned` a group's row. The scenario answers `after`
(it arms nothing here); `wake`, `writing` and `enqueue` are the toy's own. origin_acked is the document's, the twin's own:
a planned group has its `origin`, the mesh is drawn, and origin_acked is called by itself too. Three nodes of a
5-node cell built as run.py builds it: node 2 with W set to 2 before the tracer is installed (a node's constants
are read then), node 3 with no window, node 4 with W 2 at SOURCE_OFFERS = PUBLISH. A sample on which the Python
raises is written with `raises` by the tracer; the counts are printed.
"""
import argparse
import math
import random
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402

FNS = (["acquire_slot"] * 4 + ["release_unused_slot"] * 4 + ["track_in_flight"] * 2 + ["window_release"] * 2
       + ["window_timeout"] * 3 + ["free_slot"] * 2 + ["origin_acked"] * 2 + ["front"] * 2 + ["wake_front"] * 2)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed71", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    nodes = {}
    for k in (2, 3, 4):
        nd = got["sim"].nodes[k]
        ns = nd.ns
        ns["content_id"] = lambda f: f.cid
        ns["after"] = lambda delay, fn, *args: None
        ns["W"] = math.inf if k == 3 else 2
        if k == 4:                      # a node at SOURCE_OFFERS = PUBLISH: origin_acked does nothing there
            ns["SOURCE_OFFERS"] = ns["PUBLISH"]
        tr.install(nd, ns)
        nodes[k] = (nd, ns)

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised, kinds = Counter(), Counter()
    for _ in range(a.n):
        what = rng.choice(FNS)
        r = rng.random()
        nd, ns = nodes[4 if r < 0.12 else 3 if r < 0.27 else 2]
        at_publish = ns["SOURCE_OFFERS"] == ns["PUBLISH"]
        w = ns["W"]
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(2, 6))
        p = rng.choice(peers)
        g = rng.choice(groups)
        i = rng.randrange(8)
        cid = bytes([7]) * 20
        f = types.SimpleNamespace(slot=1, beacon_block_root=root, group=g, index=i, cid=cid,
                                  mid=g + i.to_bytes(4, "little") + cid)

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue",
                     "planned", "sent"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        nd.writer_kicked.clear()
        nd.writer_blocked.clear()
        ns["waiters"].clear()
        count = rng.choice([0, 0, 1, 1, 2, 2, 3])
        ns["in_flight"]._h.count = count            # the count itself, behind the tracer's cell (no record is open)
        r = rng.random()
        others = [q for q in peers if q != p]
        line = ([] if r < 0.35 else [p] + rng.sample(others, min(len(others), rng.randrange(0, 3))) if r < 0.6
                else rng.sample(peers, rng.randrange(1, len(peers) + 1)))
        ns["waiters"].extend(line)
        blocked = {q for q in peers if rng.random() < 0.35}    # writers mid-write: `writing` says so
        nd.writer_blocked.update(blocked)
        can = [q for q in line if q not in blocked]
        first = can[0] if can else None                 # the line's front
        passed = ", a writer mid-write passed" if line and line[0] in blocked else ""
        for q in peers:
            if rng.random() < 0.4:
                ns["slot_held"][q] = True
        key = (p, g, i)
        at = ns["now"] - rng.choice([0.1, 0.5, 0.75])
        r = rng.random()
        if r < 0.45:
            ns["sent"][key] = at                    # the send still in flight, at the timer's time
        elif r < 0.6:
            ns["sent"][key] = ns["now"]             # sent again since: the old timer is stale
        for q in peers:                             # other sends in flight
            if rng.random() < 0.3:
                ns["sent"][(q, rng.choice(groups), rng.randrange(8))] = ns["now"] - 0.2
        ns["mesh"] = set(rng.sample(peers, rng.randrange(len(peers) + 1)))     # origin_acked's sends and offers
        for gg in groups:
            if rng.random() < 0.4 or (what == "origin_acked" and gg == g):     # a group the node publishes: its plan
                ns["planned"][gg] = {j: set(rng.sample(peers, rng.randrange(0, 3))) for j in range(8) if rng.random() < 0.5}
                ns["origin"][gg] = B.Bits(rng.choice([0, rng.randrange(1 << 8), (1 << 8) - 1]))    #   and what is acknowledged

        # ---- the call
        under = count < w
        try:
            if what == "acquire_slot":
                kinds["acquire_slot: " + ("the window full" if not under else "nobody in line" if not line else
                                          "nobody in line can write" if first is None else
                                          "the peer the front" + (", others behind" if len(line) > 1 else "") + passed
                                          if first == p else "another the front, the peer " +
                                          ("in line" if p in line else "not in line") + passed)
                      + (", no window" if math.isinf(w) else "")] += 1
                ns["acquire_slot"](p)
            elif what == "release_unused_slot":
                rest = [q for q in line if q != p]
                restcan = [q for q in rest if q not in blocked]
                kinds["release_unused_slot: " + ("the peer not in line" if p not in line else
                                                 "it leaves the line" + (", nobody left" if not rest else
                                                                         ", no slot for the next" if not under else
                                                                         ", nobody left can write" if not restcan else
                                                                         ", the next that can write woken"))
                      + (", its slot freed" if ns["slot_held"][p] else "")] += 1
                ns["release_unused_slot"](p)
            elif what == "track_in_flight":
                kinds["track_in_flight: " + ("a second copy" if key in ns["sent"] else "a first copy")] += 1
                ns["track_in_flight"](p, f)
            elif what == "window_release":
                kinds["window_release: " + ("a send released" if key in ns["sent"] else "nothing in flight")
                      + (", somebody in line" if line and key in ns["sent"] else "")] += 1
                ns["window_release"](p, g, i)
            elif what == "window_timeout":
                live = ns["sent"].get(key) == at
                kinds["window_timeout: " + ("released" + (", a group the node publishes" + (", at PUBLISH" if at_publish else "")
                                                          if g in ns["planned"] else "")
                                            if live else "stale, sent again" if key in ns["sent"] else
                                            "stale, released before")] += 1
                ns["window_timeout"](key, at)
            elif what == "origin_acked":
                kinds["origin_acked: " + ("at PUBLISH, nothing" if at_publish else
                                          "acknowledged before" if ns["origin"][g].has(i) else
                                          "the HAVE grows" + (", no mesh" if not ns["mesh"] else ""))] += 1
                ns["origin_acked"](g, i)
            elif what == "front":
                kinds["front: " + ("nobody in line" if not line else "nobody in line can write" if first is None else
                                   "the first can write" if first == line[0] else "a writer mid-write passed")] += 1
                ns["front"]()
            elif what == "wake_front":          # with `past` (next_to_send's, for a writer in line) or without
                past = p if rng.random() < 0.5 else None
                woke = next((q for q in line if q != past and q not in blocked), None)
                kinds["wake_front: " + ("no slot free" if not under else "nobody in line" if not line else
                                        "nobody in line can write" if woke is None else
                                        "the first woken" if woke == line[0] else "the first passed")
                      + ("" if past is None else ", past the peer" + ("" if p in line else " (not in line)"))] += 1
                if past is None:
                    ns["wake_front"]()
                else:
                    ns["wake_front"](past=p)
            else:
                kinds["free_slot: " + ("at 0" if count == 0 else "a slot back")
                      + ("" if not line else ", nobody in line can write" if first is None else
                         ", somebody in line" + passed)] += 1
                ns["free_slot"]()
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed71: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, n in sorted(kinds.items()):
        print(f"  {k}: {n}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
