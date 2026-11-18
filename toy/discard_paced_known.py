#!/usr/bin/env python3
"""A known answer for `discard_paced`, which `drop_group` calls (§4.6, §6.4, §8.1): a dropped group is announced no
more by paced gossip either.

    python3 discard_paced_known.py      # protocol.md, then protocol-v2.md on top of it

§4.6: the node "announces the group no more, at the heartbeat or paced". `drop_group` calls
`gossip_history.remove_group` and `discard_paced`, which §8.1's list defines: they "drop a group from the gossip
history and from paced jobs"; at a group's expiry "its paced jobs go". With card 15 (§6.4) the heartbeat queues one
job per sampled peer, `(q, ids, now)`, the ids of the last three heartbeats' chunks, of any groups, and
`on_pace_tick` releases one job per tick, announcing its ids as one IHAVE per group (`send_gossip`). So the group's
ids leave every job, and a job that named the group alone goes with them. A job that was empty already is not the
group's: it stays, and its tick with it.

The check, on one node of a small network that is built and not run, with paced jobs queued by hand as
`on_heartbeat` queues them, for groups g and h: to peer 3 a job of g's ids alone (an earlier heartbeat's), to peer
1 an empty one, and to peers 4 and 5 jobs sharing one list of g's and h's ids (one heartbeat's). Then
`drop_group(g)`, and `on_pace_tick` until no job is left. No IHAVE may name g; peers 4 and 5 must each get one of
h (the controls), and the empty job must still take its tick.
"""
import sys
from pathlib import Path

SEED, NODE = 7, 2
G, H = bytes([0x39]) * 32, bytes([0x3a]) * 32              # g is dropped, h is kept; no block commits either
NAME = {G: "g", H: "h"}


def check(doc):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)]
             + (["--doc", "v2"] if doc == "v2" else []))
    nd = got["sim"].nodes[NODE]
    ns = nd.ns
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    mid = lambda g, i: g + i.to_bytes(4, "little") + bytes([0x44]) * 20
    line("card 15 is on (PACED)", ns["PACED"], True)
    now = ns["now"]
    one_heartbeat = [mid(G, 0), mid(G, 1), mid(H, 0)]
    pq = ns["pace_queue"]
    pq += [(3, [mid(G, 0), mid(G, 1)], now), (1, [], now), (4, one_heartbeat, now), (5, one_heartbeat, now)]

    def jobs():
        return [(q, [f"{NAME[m[:32]]}{int.from_bytes(m[32:36], 'little')}" for m in ids]) for q, ids, _ in pq]

    print(f"  the jobs, as queued: {jobs()}")
    ns["drop_group"](G)
    line("the jobs after drop_group", jobs(), [(1, []), (4, ["h0"]), (5, ["h0"])])
    ticks = 0
    while pq and ticks < 10:
        ns["on_pace_tick"]()
        ticks += 1
    out = {}
    for q in (1, 3, 4, 5):
        for e in ns["queue"][q].normal:
            for m in (e.control.items if e.control else ()):
                if m.kind == "ihave":
                    out.setdefault(q, []).extend(f"{NAME[x.group]}{sorted(x.bits)}" for x in m.ids)
    line("the IHAVEs the pace ticks queued, per peer", out, {4: ["h[0]"], 5: ["h[0]"]})
    line("the ticks they took, the empty job's included", ticks, 3)
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
