#!/usr/bin/env python3
"""A known answer for §4.2's second copy of an index under another id: a chunk that passes level 1 under an id
the node has not seen, at an index it has already received, is acknowledged and goes no further. It is not
forwarded and not kept for heartbeat gossip. A copy of an index the node holds only as rebuilt is still
forwarded.

    python3 second_id_known.py        # protocol.md, then protocol-v2.md on top of it

`protocol.md`'s `on_validated` returns with the acknowledgement once `received[g]` has the index, before
`forward`. `protocol-v2.md`'s `on_validated` (its §4.2) forwards on the axes whose index it had not received
before this copy. A copy of an index held only as rebuilt is new on its axis in both documents, so both forward
it.

The check, on one node of a small network that is built and not run, its one payload published (K = 4, N = 8),
with `forward` and the gossip history's `put` counted:
- the control: the publisher's copy of chunk 0 is forwarded once;
- a copy of chunk 0 under a second id, from another peer, is acknowledged to that peer, and is neither forwarded
  nor put in the gossip history;
- after chunks 1 to 3 and the decode, chunk 4 (rebuilt, never received) arrives under its own id, which the node
  has not seen: it is forwarded (the control for the rebuilt case);
- then chunk 4 under yet another id: `protocol.md` stored the copy before, so this one is a second copy of a
  received index, not forwarded; `protocol-v2.md` stores no copy of a rebuilt index, so it forwards this one too
  (its §6.1, "more ids for a rebuilt index");
- a repeat of chunk 4 under its own id, the rebuilt chunk's, is acknowledged in both;
- chunk 5, rebuilt, comes first under an id not its own, and both forward it; a repeat of that copy is
  acknowledged by `protocol.md`, which stored it, and ignored by `protocol-v2.md`, which stored none (`accepted`
  answers whether the id was stored, since v0.10.5's toy).

The toy's content id hashes the chunk's identity (`wire.content_id`), so the second id is made by changing what
it hashes. Level 1 is taken as passed (`on_validated` with ACCEPT), as for a relabelled copy whose other block
the node installed (`protocol.md` §4.6's open item). On `protocol-v2.md` before this rule, the second id's copy was
forwarded and put in the gossip history: the check fails there.
"""
import copy
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3          # node 2; peer 1 publishes; peer 3 sends the copy under a second id


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
    calls = {"forward": 0, "put": 0}
    doc_forward, hist = ns["forward"], ns["gossip_history"]
    doc_put = hist.put

    def forward(f, from_peer, *rest):
        calls["forward"] += 1
        return doc_forward(f, from_peer, *rest)

    def put(f):
        calls["put"] += 1
        return doc_put(f)
    ns["forward"], hist.put = forward, put
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def haves(q):                                           # the HAVEs of g queued to q
        return sum(1 for e in ns["queue"][q].urgent for m in (e.control.items if e.control else ())
                   for x in m.ids if m.kind == "idontwant" and isinstance(x, Wm.HaveBitmap) and x.group == g)

    def arrive(q, f, validated=False):                      # one copy: forward and put calls, HAVEs to q, penalties
        before, h, pen = dict(calls), haves(q), nd.penalties
        if validated:
            ns["on_validated"](q, f, ns["ACCEPT"])          # level 1 passed, as for a relabelled copy
        else:
            ns["on_chunk"](q, f)
        return (calls["forward"] - before["forward"], calls["put"] - before["put"], haves(q) - h,
                nd.penalties - pen)

    line("the control: the publisher's chunk 0 (forward, gossip put)",
         arrive(P, chunks[0])[:2], (1, 1))
    f2 = copy.copy(chunks[0])
    f2.data = copy.copy(chunks[0].data)
    f2.data.tag = ("a second id", chunks[0].data.tag)
    f2.mid = None                                           # the toy caches a chunk's id on the object
    mid, mid2 = ns["message_id"](chunks[0]), ns["message_id"](f2)
    line("the second id differs from the first, and is not seen", (mid2 != mid, ns["seen"](mid2)), (True, False))
    line("chunk 0 under a second id, from peer 3 (forward, gossip put, HAVEs to it, penalties)",
         arrive(Q, f2, validated=True), (0, 0, 1, 0))
    for i in range(1, K):
        ns["on_chunk"](P, chunks[i])
    ns["decode_group"](g)                                   # the decode the claim started, run now
    held = K in ns["chunks"][g] and not ns["received"][g].has(K)
    line(f"the decode: chunk {K} stored, and not received", held, True)
    line(f"the control: chunk {K} under its own id, from the publisher (forward, gossip put)",
         arrive(P, chunks[K], validated=True)[:2], (1, 1))
    f3 = copy.copy(chunks[K])
    f3.data = copy.copy(chunks[K].data)
    f3.data.tag = ("another id", chunks[K].data.tag)
    f3.mid = None
    line(f"chunk {K} under another id, from peer 3 (forward, gossip put)",
         arrive(Q, f3, validated=True)[:2], (1, 1) if doc == "v2" else (0, 0))
    line(f"a repeat of chunk {K} under its own id, the rebuilt chunk's, from peer 3 (forward, gossip put, HAVEs "
         "to it, penalties)", arrive(Q, chunks[K]), (0, 0, 1, 0))
    f5 = copy.copy(chunks[K + 1])                           # rebuilt, and first comes under an id not its own
    f5.data = copy.copy(chunks[K + 1].data)
    f5.data.tag = ("a first other id", chunks[K + 1].data.tag)
    f5.mid = None
    line(f"chunk {K + 1}, rebuilt, first under an id not its own, from peer 3 (forward, gossip put)",
         arrive(Q, f5, validated=True)[:2], (1, 1))
    line(f"a repeat of that copy, from peer 3 (forward, gossip put, HAVEs to it, penalties)",
         arrive(Q, f5), (0, 0, 0, 0) if doc == "v2" else (0, 0, 1, 0))
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
