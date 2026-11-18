#!/usr/bin/env python3
"""A known answer for §4.2's duplicate path in a dropped group: a copy of a chunk the node stored is acknowledged,
whether or not the group was dropped since.

    python3 dropped_dup_known.py        # protocol.md, then protocol-v2.md on top of it

`on_chunk` acknowledges a copy of a chunk it has seen if `accepted(mid)`, and §8.1's list says what that is: "the
id was stored". `drop_group` (§4.6) marks the group invalid and keeps its stored chunks, so a copy of one of them
is still acknowledged with a HAVE ("its HAVEs stay"), and the HAVE names what the node claimed: a group is dropped
only after its decode claim (§6.2: "`drop_group` follows a claim"), so every index. A chunk that first arrives
after the drop passes level 1, is marked seen and is not stored (§4.2: "a chunk of a dropped group"), so a copy of
it is ignored.

The check, on one node of a small network that is built and not run, its one payload published (K = 4, N = 8), in
the two ways the documents drop a group. The publisher's copies of chunks 0 to 3 arrive: the K-th makes the decode
claim and starts the decode. A second copy of chunk 0 is acknowledged with a HAVE of all 8 indices (the control,
before the drop). Then the decode runs, and the group is dropped:
- **level 2 fails:** the decode finds no codeword (`decode_and_reencode` gives None, as for an inconsistent code;
  the toy's own decode always succeeds), and `decode_group` calls `drop_group`;
- **level 3 fails:** the decode succeeds and stores the rebuilt chunks, and the application's check, called by
  `deliver`, calls `drop_group`.
Then a copy of chunk 0 must be acknowledged with a HAVE of all 8 indices. Where level 2 failed, chunk 4 was never
stored: its first copy after the drop is seen and not stored, and a copy of it must not be acknowledged (the
control). The HAVEs are counted on the urgent lane of the copy's sender, where `send_have` puts them; no copy
counts against its sender.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3          # node 2; peer 1 publishes; peer 3 sends the second copies


def check(doc, level):
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
    d = chunks[0].descriptor
    K, N = ns["K"](d), ns["N"](d)
    every = list(range(N))
    if level == 2:
        ns["decode_and_reencode"] = lambda chunks_g, d: None           # no codeword: level 2 fails
    else:
        ns["deliver"] = lambda g_, payload: ns["drop_group"](g_)       # the application's check fails: level 3
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

    for i in range(K):
        ns["on_chunk"](P, chunks[i])
    line(f"chunks 0 to {K - 1} from the publisher: the state, and the indices the node claims (K = {K}, N = {N})",
         (ns["state"][g], sorted(ns["mine"][g])), ("DECODING", every))
    line("the control: a copy of chunk 0 after the claim, before the drop, adds a HAVE of every index (HAVEs, "
         "penalties)", copy_from(Q, chunks[0]), ([every], 0))
    ns["decode_group"](g)                                   # the decode the claim started (`start`), run now
    line("the decode: the group is invalid, chunk 0 still stored, chunks stored",
         (ns["state"][g], 0 in ns["chunks"][g], len(ns["chunks"][g])), ("INVALID", True, K if level == 2 else N))
    line("a copy of chunk 0 after the drop adds a HAVE of every index", copy_from(Q, chunks[0]), ([every], 0))
    if level == 2:
        added = copy_from(P, chunks[K])
        line(f"chunk {K}'s first copy after the drop: stored, seen, and the HAVEs it added",
             (K in ns["chunks"][g], ns["seen"](ns["message_id"](chunks[K])), added), (False, True, ([], 0)))
        line(f"the control: a copy of chunk {K}, seen and never stored, adds none", copy_from(Q, chunks[K]), ([], 0))
    return bad


def main():
    bad = 0
    for doc in ("v03", "v2"):
        for level in (2, 3):
            print(f"--doc {doc}, level {level} fails:")
            bad += check(doc, level)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
