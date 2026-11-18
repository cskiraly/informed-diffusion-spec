#!/usr/bin/env python3
"""A known answer for `discard_queued`, which `drop_group` calls (§4.6, §8.1): a dropped group's chunks, IHAVEs and
IWANTs leave every queue, with what is owed of it; its HAVEs stay, and so does everything of another group.

    python3 discard_queued_known.py     # protocol.md, then protocol-v2.md on top of it

§4.6: "It removes the group's chunks, IHAVEs and IWANTs from every queue, with what is owed of it; its HAVEs stay."
§8.1's list: `discard_queued` "removes a group's chunks, IHAVEs and IWANTs from every queue, and what is owed of it,
keeping HAVEs". A queue entry carries at most one chunk and may carry control (§7.2): an answer carries the asks and
prunes of the frame it answers (§4.1), and what is owed rides as one IHAVE per group (`with_owed`). So the group's
part of an entry goes, and the entry with it only if nothing is left.

The check, on one node of a small network that is built and not run, with queues made by hand for two peers and
two groups, g dropped and h kept (chunks stand-ins that name their group and index). Peer 1's normal lane: a push
of g's and one of h's; an answer of g's carrying an ask of h's; an answer of h's carrying asks of g's and h's and a
PRUNE; an IHAVE of g, one of h, and an entry with an IHAVE of each; asks of g by id and by a standing WANT; an IHAVE
of g by id. Its urgent lane: a HAVE of g, a HAVE of h, and a HAVE of g with an IHAVE of g beside it. Peer 3's
normal lane: a push, an ask and an IHAVE of g's, and a push of h's. What is owed to peer 1, offers and answers, of
both groups. After `drop_group(g)` every part naming g must be gone but the HAVEs, and every part naming h stay.
"""
import sys
from pathlib import Path

SEED, NODE, P, Q = 7, 2, 1, 3
G, H = bytes([0x37]) * 32, bytes([0x38]) * 32              # g is dropped, h is kept; no block commits either
NAME = {G: "g", H: "h"}


def check(doc):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    from bits import bitmap
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)]
             + (["--doc", "v2"] if doc == "v2" else []))
    ns = got["sim"].nodes[NODE].ns
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    chunk = lambda g, i: type("Chunk", (), {"group": g, "index": i})()
    full_id = lambda g, i: g + i.to_bytes(4, "little") + bytes([0x44]) * 20
    hb = lambda g, *i: Wm.HaveBitmap(group=g, bits=bitmap(set(i)))

    def entry(f=None, ctl=None, solicited=False):
        return Wm.Entry(chunk=f, control=ctl, solicited=solicited)

    def owed_entry(*bms):                                   # what with_owed builds: one IHAVE per group
        e = Wm.Entry()
        for b in bms:
            e.add_ihave(b)
        return e

    qp, qq = ns["queue"][P], ns["queue"][Q]
    qp.normal.extend([
        entry(chunk(G, 0)),                                                 # a push of g's
        entry(chunk(H, 0)),                                                 # a push of h's
        entry(chunk(G, 1), Wm.IWANT([Wm.WantIndex(H, 2)]), True),           # g's answer, an ask of h's riding
        entry(chunk(H, 1), Wm.IWANT([Wm.WantIndex(G, 2), Wm.WantIndex(H, 3)]) + Wm.PRUNE(["prune"]), True),
        entry(None, Wm.IHAVE(hb(G, 3, 4))),
        entry(None, Wm.IHAVE(hb(H, 5))),
        owed_entry(hb(G, 6), hb(H, 6)),
        entry(None, Wm.IWANT([full_id(G, 7)])),                             # an ask by id
        entry(None, Wm.IWANT([Wm.FlaggedWant(G, 9, True, 0)])),             # a standing WANT
        entry(None, Wm.IHAVE([full_id(G, 8)])),                             # an IHAVE by id, as without card 7
    ])
    haves_g = entry(None, Wm.IDONTWANT(hb(G, 0, 1)))
    haves_g.add_ihave(hb(G, 9))
    qp.urgent.extend([entry(None, Wm.IDONTWANT(hb(G, 0))), entry(None, Wm.IDONTWANT(hb(H, 0))), haves_g])
    qq.normal.extend([entry(chunk(G, 2)), entry(None, Wm.IWANT([Wm.WantIndex(G, 0)])),
                      entry(None, Wm.IHAVE(hb(G, 1))), entry(chunk(H, 3))])
    for t, i in (("owed", 1), ("owed_answers", 3)):
        ns[t][P][G].set(i)
        ns[t][P][H].set(i + 1)

    def name(x):
        if isinstance(x, Wm.HaveBitmap):
            return f"{NAME[x.group]}{sorted(x.bits)}"
        if isinstance(x, Wm.WantIndex):
            return f"{NAME[x.group]}#{x.index}{' standing' if x.standing else ''}"
        if isinstance(x, bytes) and len(x) == 56:
            return f"{NAME[x[:32]]}@{int.from_bytes(x[32:36], 'little')}"
        return str(x)

    def show(e):                                            # an entry as the parts it would write
        parts = [f"chunk {NAME[e.chunk.group]}{e.chunk.index}"] if e.chunk is not None else []
        for m in (e.control.items if e.control else ()):
            if m.ids:
                parts.append(f"{m.kind} {' '.join(name(x) for x in m.ids)}")
        return "; ".join(parts)

    def state():
        return {"1 normal": [show(e) for e in qp.normal], "1 urgent": [show(e) for e in qp.urgent],
                "3 normal": [show(e) for e in qq.normal],
                "owed": {t: {NAME[g]: sorted(b) for g, b in ns[t][P].items()} for t in ("owed", "owed_answers")}}

    before = state()
    ns["drop_group"](G)
    after = state()
    print(f"  as made, before drop_group: {before}")
    line("peer 1's normal lane, after", after["1 normal"],
         ["chunk h0", "iwant h#2", "chunk h1; iwant h#3; prune prune", "ihave h[5]", "ihave h[6]"])
    line("peer 1's urgent lane, after: the HAVEs stay, the IHAVE beside one goes", after["1 urgent"],
         ["idontwant g[0]", "idontwant h[0]", "idontwant g[0, 1]"])
    line("peer 3's normal lane, after", after["3 normal"], ["chunk h3"])
    line("what is owed to peer 1, after", after["owed"], {"owed": {"h": [2]}, "owed_answers": {"h": [4]}})
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
