#!/usr/bin/env python3
"""A known answer for the toy's charge on the standalone binding (run.py --wire standalone): for every message kind,
what the links charge equals the length of the frame standalone_wire_known.py's encoder writes from
protocol-v2-bindings.md §1 (before compression, as §1.7's sizes are).

    python3 standalone_charge_known.py

On a small custody run and a small payload run (protocol-v2.md, one block or payload, --wire standalone), entries
are built by hand and charged by the simulator (sim.standalone_wire):
- a JOIN, a GRAFT and a PRUNE; a holding (IDONTWANT) and an offer (IHAVE) of a 16-byte bitmap; WANTs of index 3
  and of index 127, plain and flagged;
- the payload's chunk;
- a cell pushed to a peer for the first time in its group (with the block's header: every blob's commitment), the
  next push of the same group to it (no header), an answer of another group (no header, since an answer is not an
  eager push), and a push of the first group to another peer (the header again).
An entry with a chunk and control is charged as the sum of its messages' frames. The window's size of a chunk
(wire_size) is what its write will charge: the header with a first push, none with an answer or a later push.
"""
import sys
from pathlib import Path


def sim_of(args):
    import run
    import sim as S
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(args)
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    return sim


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import standalone_wire_known as K
    import wire as Wm
    from bits import bitmap
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    def framed(kind, m):                                    # the encoder's frame, before compression
        body = K.enc(kind, m)
        return len(K.uvarint(1 + len(body))) + 1 + len(body)

    sim = sim_of(["--doc", "v2", "--setting", "custody", "--nodes", "8", "--degree", "6", "--msgs", "1",
                  "--seed", "7", "--wire", "standalone"])
    nd = sim.nodes[2]
    p, q = sorted(nd.peers)[:2]
    cols = [g for g in sim.canonical if sim.gtype.get(g) == "column"]
    g1, g2 = cols[0], cols[1]
    f1 = next(iter(sim.canonical[g1].values()))
    f2 = next(iter(sim.canonical[g2].values()))
    gid = K.group_id(1, b"\0" * 32, 0)

    def charge(e, to=p):
        return sim.standalone_wire(nd, to, e)

    hb = Wm.HaveBitmap(g1, bitmap(range(128)))             # a whole row's 128 bits: 16 bytes
    msgs = [
        ("JOIN", Wm.JOIN([object()]), framed(1, {"type": 1, "fork": b"\0" * 4, "interest": 1, "custody": 8, "duty": 1,
                                                 "colours": 1})),
        ("GRAFT", Wm.GRAFT([object()]), framed(2, {"type": 1, "family": 5, "colour": 0, "direction": 2, "answer": 0})),
        ("PRUNE", Wm.PRUNE([object()]), framed(3, {"type": 1, "family": 5, "colour": 0, "direction": 2})),
        ("HAVE, holding", Wm.IDONTWANT(hb), framed(4, {"group": gid, "flags": 4, "bits": b"\xff" * 16})),
        ("HAVE, offer", Wm.IHAVE(hb), framed(4, {"group": gid, "flags": 1, "bits": b"\xff" * 16})),
        ("WANT of index 3", Wm.IWANT([Wm.WantIndex(g1, 3)]),
         framed(5, {"group": gid, "flags": 0, "hops": 0, "bits": K.bits_bytes([3])})),
        ("WANT of index 127, flagged", Wm.IWANT([Wm.FlaggedWant(g1, 127, True, 1, True)]),
         framed(5, {"group": gid, "flags": 3, "hops": 1, "bits": K.bits_bytes([127])})),
    ]
    for name, c, want in msgs:
        line(f"{name}: charged against the encoder's frame", charge(Wm.Entry(control=c)), (0, want))

    blobs = sim.cfg["blobs"]
    hdr = {"signed": b"\0" * K.SIGNED_HEADER, "proof": [b"\0" * 32] * K.INCLUSION_DEPTH,
           "commitments": [b"\0" * 48] * blobs}
    cell = {"group": gid, "index": 0, "cell": b"\0" * K.BYTES_PER_CELL, "proof": b"\0" * 48, "header": None}
    with_h, without_h = framed(7, dict(cell, header=hdr)), framed(7, cell)
    sim.headers_sent.clear()                                # the run's own pushes are not this case's
    push1 = charge(Wm.Entry(chunk=f1))
    push2 = charge(Wm.Entry(chunk=f1))
    answer = charge(Wm.Entry(chunk=f2, solicited=True))
    other = charge(Wm.Entry(chunk=f1), to=q)
    line(f"a cell, first pushed in its group to peer {p}: with the {blobs}-blob header", push1, (with_h, 0))
    line("the next push of that group to the same peer: no header", push2, (without_h, 0))
    line("an answer, the first cell of another group to that peer: no header", answer, (without_h, 0))
    line(f"the first group pushed to another peer, {q}: the header again", other, (with_h, 0))
    both = charge(Wm.Entry(chunk=f1, control=Wm.IDONTWANT(hb) + Wm.IWANT([Wm.WantIndex(g1, 3)])))
    line("a chunk with a holding and an ask: the sum of three frames", both, (without_h, msgs[3][2] + msgs[5][2]))
    sim.headers_sent.clear()                                # the window's size, before any of these writes
    ws = nd.ns["wire_size"]
    line(f"the window's size (wire_size) of a first push to peer {p}, of an answer, of a push after the header",
         (ws(p, Wm.Entry(chunk=f1)), ws(p, Wm.Entry(chunk=f1, solicited=True)), (charge(Wm.Entry(chunk=f1)),
          ws(p, Wm.Entry(chunk=f1)))[1]), (with_h, without_h, without_h))

    pay = sim_of(["--doc", "v2", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", "7", "--wire", "standalone"])
    g = pay.msgs[0][1][0]
    f = next(iter(pay.canonical[g].values()))
    pm = {"slot": 0, "root": b"\0" * 32, "group": b"\0" * 32, "descriptor": b"\0" * 51, "index": 0,
          "proof": [b"\0" * 32] * len(f.proof), "data": b"\0" * len(f.data)}
    line(f"the payload's chunk ({len(f.proof)} proof steps, {len(f.data)} bytes of data)",
         pay.standalone_wire(pay.nodes[2], sorted(pay.nodes[2].peers)[0], Wm.Entry(chunk=f)), (framed(6, pm), 0))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
