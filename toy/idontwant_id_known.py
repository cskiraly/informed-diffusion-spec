#!/usr/bin/env python3
"""A known answer for §4.1's rule on an IDONTWANT entry that is not a HAVE bitmap: it is a stock message id, kept
in `unwanted[p]` as stock gossipsub keeps it, and not read as a HAVE.

    python3 idontwant_id_known.py [--doc v2]

An IDONTWANT names no topic, so beside the HAVE bitmaps (§2, a string opening with MAGIC "HAVE" and VERSION, and
holding a group after them) its entries can be stock message ids, another topic's say. `on_frame` hands a bitmap
to `on_have` (§4.3) and keeps any other entry in `unwanted[p]`, the stock IDONTWANT state that `on_iwant` reads
(§4.5).

The check, on one node of a small network that is built and not run, with one frame from a peer: an IDONTWANT
holding a stock id of 20 bytes and a HAVE bitmap. The stock id must end in `unwanted[p]`, with no penalty and no
error; and the bitmap beside it must still be read as a HAVE, and not be kept in `unwanted[p]` (the controls:
the rule neither sets every entry aside nor keeps every entry as an id), its index now in what the node knows
the peer holds. On the document before the rule, the stock id went to `on_have`, which needs a bitmap: the
check fails there. The toy tells a bitmap by its type (`wire.is_have_bitmap`), so this does not test the
document's test of the string's first bytes and length.

With `--doc v2`, the same frame reaches `protocol-v2.md` on v0.3's wire (`protocol-v2-bindings.md` §3): the toy
reads the frame as v2's messages, a bitmap in an IDONTWANT as a holding (`on_holding`, v2's §4.3) and any other
entry as a stock id in `unwanted[p]`, which v2's `on_want` reads (§4.5). Before the binding said so, the toy left
the stock id out of `unwanted[p]`: the check fails there.
"""
import sys
from pathlib import Path

SEED, NODE, PEER = 7, 2, 1
G = bytes([0x35]) * 32                              # a group no block commits
STOCK_ID = bytes([0x22]) * 20                       # a stock message id, another topic's
V2 = sys.argv[1:] == ["--doc", "v2"]
RULE = "protocol-v2-bindings.md §3" if V2 else "§4.1"


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    from bits import bitmap
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)]
             + (["--doc", "v2"] if V2 else []))
    node = got["sim"].nodes[NODE]
    ns = node.ns

    frame = object.__new__(Wm.Frame)                # one frame: no chunk, no IHAVE or IWANT, an IDONTWANT
    frame.chunks, frame.ihave, frame.iwant = [], Wm._IHave([]), Wm._IWant([])
    frame.prune, frame.graft, frame.join = [], [], []
    hb = Wm.HaveBitmap(group=G, bits=bitmap({3}))
    frame.idontwant = [STOCK_ID, hb]

    penalties = node.penalties
    try:
        ns["on_frame"](PEER, frame)
    except Exception as e:                          # the document before the rule: the stock id reached on_have
        print(f"on_frame stopped with {type(e).__name__}: {e}  <-- FAIL")
        print("FAIL")
        return 1
    kept = STOCK_ID in ns["unwanted"].get(PEER, ())
    held = ns["peer_has"][PEER][G].has(3)
    penalised = node.penalties - penalties
    ok_stock = kept and penalised == 0
    print(f"a stock id of 20 bytes in an IDONTWANT: in unwanted[p] {kept}, penalties {penalties} -> {node.penalties}: "
          f"{'kept as stock keeps it' if ok_stock else f'NOT as {RULE} says  <-- FAIL'}")
    aside = any(e is hb for e in ns["unwanted"].get(PEER, ()))
    print(f"the control: a HAVE bitmap of index 3 beside it: read as a HAVE {held}, in unwanted[p] {aside}: "
          f"{'what the node knows the peer holds, and not an id' if held and not aside else f'NOT as {RULE} says  <-- FAIL'}")
    bad = (not ok_stock) + (not held) + aside
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
