#!/usr/bin/env python3
"""A known answer for `accepted(mid)` (§8.1: "`accepted`: the id was stored"): it asks after the id, not the index.

    python3 accepted_id_known.py        # protocol.md, then protocol-v2.md on top of it

§4.2's duplicate path acknowledges a copy of a chunk it has seen if `accepted(mid)`, and protocol-v2.md's also
answers the copy's probe there. Two ids can name one index: a copy whose content differs has its own content id,
and so its own id (§2: the group, the index and the content id). Only the id that was stored is accepted. So:
- a copy that level 1 rejected (here: naming a slot that is not its block's) is seen and never stored; a later copy
  of it must not be acknowledged, though the node stores another copy of that index;
- a copy with its own id that passes level 1 after the index was received is acknowledged by `on_validated` as a
  second copy (§4.2: "a second copy of a chunk we received: acknowledge") and is not stored; a later copy of it is
  seen, and is not acknowledged, since its id was not stored. (The toy's level 1 does not check proofs, so such a
  copy passes it. That a first copy is acknowledged and a later one is not is the text's.)
The controls: a copy of the stored chunk is acknowledged; `accepted` answers yes for the stored id.

The check, on one node of a small network that is built and not run, its one payload published (K = 4, N = 8), as
in dropped_dup_known.py: the publisher's copies of chunks 0 to 3 arrive and are stored. The HAVEs are counted on
the urgent lane of the copy's sender, where `send_have` puts them, with the node's penalties.
"""
import copy as C
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3          # node 2; peer 1 publishes; peer 3 sends the other copies


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
    d = chunks[0].descriptor
    K, N = ns["K"](d), ns["N"](d)
    every = list(range(N))
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

    def copy_from(q, f):                                    # one copy of f from q: the HAVEs it adds, the penalties
        before, pen = len(haves(q)), nd.penalties
        ns["on_chunk"](q, f)
        return haves(q)[before:], nd.penalties - pen

    def own_id(f, slot=None):                               # a copy of f with other content, so another id
        x = C.copy(f)
        x.data = Wm.Blob(len(f.data), ("other", f.data.tag))
        if slot is not None:
            x.slot = slot
        x.mid = None                                        # the toy caches a chunk's id on the object
        return x

    for i in range(K):
        ns["on_chunk"](P, chunks[i])
    a = ns["message_id"](chunks[0])
    line(f"chunks 0 to {K - 1} from the publisher: chunk 0 stored, under its id", ns["known_id"][g].get(0) == a, True)
    line("the control: a copy of chunk 0 adds a HAVE of every index (HAVEs, penalties)",
         copy_from(Q, chunks[0]), ([every], 0))

    bad_copy = own_id(chunks[0], slot=chunks[0].slot - 1)   # level 1 rejects it: its slot is not its block's
    b = ns["message_id"](bad_copy)
    line("a copy of index 0 with its own id, naming another slot: same group and index, another id",
         (b[:36] == a[:36], b != a), (True, True))
    line("its first copy: rejected, so no HAVE and a penalty; seen, and not stored",
         (copy_from(Q, bad_copy), ns["seen"](b), ns["known_id"][g].get(0) == a), (([], 1), True, True))
    line("**a later copy of it is not acknowledged** (accepted asks after the id)", copy_from(Q, bad_copy), ([], 0))

    second = own_id(chunks[1])                              # its own id; the toy's level 1 passes it
    c = ns["message_id"](second)
    line("a copy of index 1 with its own id: its first copy, acknowledged as a second copy, not stored",
         (copy_from(Q, second), ns["seen"](c), ns["known_id"][g].get(1) == ns["message_id"](chunks[1])),
         (([every], 0), True, True))
    line("**a later copy of it is not acknowledged** (its id was not stored)", copy_from(Q, second), ([], 0))

    line("accepted: the stored id of index 0, the rejected one, the second copy's of index 1",
         (ns["accepted"](a), ns["accepted"](b), ns["accepted"](c)), (True, False, False))
    line("the control: a copy of chunk 1 as stored is still acknowledged", copy_from(Q, chunks[1]), ([every], 0))
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
