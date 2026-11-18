#!/usr/bin/env python3
"""A known answer for a HAVE bitmap's length (§2, §4.3, §8.2): a bitmap longer than `MAX_HAVE_BYTES` is malformed,
whether or not its group's count is known.

    python3 have_length_known.py        # protocol.md, then protocol-v2.md on top of it

§2 sends a group's bitmap as `ByteList[MAX_HAVE_BYTES]`, 1024 bytes, index i in bit i, trailing zero bytes dropped:
it names indices below 8192 and no other. §8.2 holds a HAVE, and an IHAVE's bitmap (§4.4), to that length, and to
no index at or beyond the group's count once its descriptor is known; a bitmap over either is ignored and counts
against its sender. `valid_have` checks both ("length, and indices within N once known", §4.3).

The check, on one node of a small network that is built and not run, each bitmap in a frame of its own from one
peer, through `on_frame`: for a group whose count is not known, a HAVE and an IHAVE whose bitmap names index 8192,
1025 bytes, must be ignored and penalised; the same naming index 8191, 1024 bytes, must be taken (the controls).
And for a group known to have 4 chunks, a HAVE of index 4 is ignored and penalised, one of index 3 taken: the
count's check, as before (the control that the length's check leaves it).
"""
import sys
from pathlib import Path

SEED, NODE, P = 7, 2, 1
G, G2 = bytes([0x35]) * 32, bytes([0x36]) * 32          # groups no block commits; G2's count is made known below


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
    nd = got["sim"].nodes[NODE]
    ns = nd.ns
    ns["desc"][G2] = type("Descriptor", (), {"count": 4})()         # a group whose count is known: 4 chunks
    cap = 8 * ns["MAX_HAVE_BYTES"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"  {what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def frame(kind, g, i):                                  # one bitmap of index i, in an IDONTWANT (a HAVE) or an
        hb = Wm.HaveBitmap(group=g, bits=bitmap({i}))       #   IHAVE, alone in a frame from P
        ctl = Wm.IDONTWANT(hb) if kind == "HAVE" else Wm.IHAVE(hb)
        pen = nd.penalties
        ns["on_frame"](P, Wm.Frame(Wm.Entry(control=ctl)))
        taken = (ns["peer_has"][P][g].bits if kind == "HAVE" else ns["offered"][P][g]).has(i)
        return (hb.bits.v.bit_length() + 7) // 8, taken, nd.penalties - pen

    for kind, a, where in (("HAVE", "a", "peer_has"), ("IHAVE", "an", "offered")):
        line(f"{a} {kind} of a group whose count is not known, index {cap}: bytes, in {where}, penalties",
             frame(kind, G, cap), (ns["MAX_HAVE_BYTES"] + 1, False, 1))
        line(f"the control: {a} {kind} of that group, index {cap - 1}", frame(kind, G, cap - 1),
             (ns["MAX_HAVE_BYTES"], True, 0))
    line("the count's check: a HAVE of index 4 of a group known to have 4 chunks", frame("HAVE", G2, 4), (1, False, 1))
    line("the count's check, its control: index 3 of that group", frame("HAVE", G2, 3), (1, True, 0))
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
