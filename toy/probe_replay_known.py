#!/usr/bin/env python3
"""A known answer for protocol-v2.md §4.6's probe (R5) and `accepted(mid)`: the claimant's copy that level 1
rejected does not pass the probe when it comes again, though the node has since stored another peer's good copy.

    python3 probe_replay_known.py

on_chunk's duplicate path answers the probe (`probe_answer`) and acknowledges the copy only if `accepted(mid)`,
and `accepted` asks after the id that was stored (protocol.md §8.1: "`accepted`: the id was stored"), not after the
index. A copy of the probed cell with other content has its own id (the group, the index and the content id, §2),
so a copy that level 1 rejected is seen and never stored, and a later copy of it is not accepted. Under a helper
that asked whether the index was stored, the claimant could replay its rejected copy once another peer's good
copy was stored, and pass the probe with a cell it never had.

On one node of a small rows run (protocol-v2.md, one block, run to its end), made by hand as in
probe_settle_known.py: the member, on a row it holds, three of whose cells it is made to lack (taken out of its
store, in the row and in each cell's column, as one arrival fills both, R4), with one claimant:
1. the control: the probe is written to the claimant (no verdict yet);
2. the claimant's copy of the probed cell, with other content and naming another slot: level 1 rejects it (the
   cell's slot check, §1's table), so a penalty; its id is seen, and not stored; no verdict;
3. the control: another peer's good copy of the cell is stored, in both its groups; the probe's promise stays
   open, and no verdict (as in probe_settle_known.py);
4. **the claimant's rejected copy again**: not accepted, so no verdict and no HAVE to the claimant;
5. the control: the claimant's copy of the cell as stored, a duplicate, passes the probe and is acknowledged.
Line 4 fails on the toy before spec commit 27a3819, whose `accepted` asked whether the index was stored.
"""
import copy as C
import sys
from pathlib import Path

SEED, NODE = 7, 2


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--doc", "v2", "--setting", "rows", "--nodes", "8", "--degree", "6", "--msgs", "1", "--seed", str(SEED)])
    sim, cfg = got["sim"], got["sim"].cfg
    sim.run(cfg["first"]); sim.publish(1); sim.run(cfg["first"] + cfg["gap"])
    nd = sim.nodes[NODE]
    ns = nd.ns
    T_row = nd._types["row"]
    whole = [g for g in ns["T_of"] if sim.gtype.get(g) == "row"
             and len(ns["chunks"][g]) == T_row.index_count(ns["hdr"][g])]
    g = whole[0]
    q = sorted(nd.peers)[0]                                 # the claimant
    r = next(x for x in sorted(nd.peers) if x != q)         # another peer
    lack = sorted(ns["chunks"][g])[:3]
    cells = {i: ns["chunks"][g][i] for i in lack}
    t0 = ns["now"]
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    def setup():                                            # the member, before the claim
        ns["now"] = t0
        ns["state"][g], ns["deferred"][g] = "COMPLETE", False
        for i in lack:                                      # lacked: not claimed, not stored, in both groups
            for gg, ii in ns["type_of_group"](cells[i].group).project(cells[i]):
                ns["mine"][gg].clear(ii)
                ns["chunks"][gg].pop(ii, None)
                ns["known_id"][gg].pop(ii, None)
                ns["received"][gg].clear(ii); ns["rebuilt"][gg].clear(ii)
        ns["probe_ok"].pop(g, None)
        ns["probe_sent"].discard(g)
        ns["reconsider_at"].pop(g, None)
        ns["claims"][g].clear(); ns["claims"][g].add(q)
        for k in [k for k in ns["promises"] if k[1] == q]:
            del ns["promises"][k]
        ns["queue"][q].normal[:] = []

    def probe_entry():                                      # the queued WANT that carries the probe
        return next(e for e in ns["queue"][q].normal
                    if any(getattr(ns["group_index"](a), "probe", False) for c in e.iwants() for a in c.ids))

    def asks_left(entry):
        return sum(len(c.ids) for c in entry.iwants())

    def haves(p, groups):                                   # the HAVEs of the groups queued to p (accepted_id_known.py)
        out = []
        for e in ns["queue"][p].urgent:
            for m in (e.control.items if e.control else ()):
                out += [x.group for x in m.ids if m.kind == "idontwant" and isinstance(x, Wm.HaveBitmap)
                        and x.group in groups]
        return out

    def copy_from(p, f):                                    # one copy of f from p: the HAVEs of f's groups it adds
        groups = {gg for gg, _ in ns["type_of_group"](f.group).project(f)}
        before = len(haves(p, groups))
        ns["on_chunk"](p, f)
        return len(haves(p, groups)) - before

    def stored(mid):                                        # the id stored, at either group of the probed cell
        return any(ns["known_id"][gg].get(ii) == mid for gg, ii in ns["type_of_group"](cell.group).project(cell))

    def verdict():
        return ns["probe_ok"].get(g, "none yet")

    # 1. the probe, written to the claimant (control)
    setup()
    ns["defer_on_claim"](g)
    entry = probe_entry()
    i = ns["probe"][g]
    cell = cells[i]
    good = ns["message_id"](cell)
    ns["now"] = t0 + 0.1
    out = ns["filter_entry"](q, entry)
    line(f"the probe of cell {i} written to the claimant, peer {q} (control): probe asks written, the probe written, "
         f"the verdict", (asks_left(entry) if out is not None else 0, g in ns["probe_sent"], verdict()),
         (1, True, "none yet"))

    # 2. the claimant's copy of the cell, which level 1 rejects: other content (so its own id, of the same group
    #    and index, as the content id is over the group, the index and the data) and another slot (the cell's
    #    level 1 checks the copy's slot against its header's block, §1's table)
    rejected = C.copy(cell)
    rejected.data = Wm.Blob(len(cell.data), ("other", cell.data.tag))
    rejected.slot = cell.slot - 1
    rejected.mid = None                                     # the toy caches a chunk's id on the object
    b = ns["message_id"](rejected)
    T = ns["type_of_group"](rejected.group)
    line("the claimant's copy, other content, another slot: same group and index, another id; level 1",
         (b[:36] == good[:36], b != good, T.verify(rejected, T.header_of(rejected))), (True, True, "REJECT"))
    pen = nd.penalties
    ns["now"] = t0 + 0.2
    acks = copy_from(q, rejected)
    line("its first copy: penalties added, HAVEs, seen, stored, the verdict",
         (nd.penalties - pen, acks, ns["seen"](b), stored(b), verdict()), (1, 0, True, False, "none yet"))

    # 3. another peer's good copy, stored in both groups of the cell (its id was seen in the run, so on_chunk would
    #    take the duplicate path: fill, as on_validated's line for each group the cell belongs to)
    ns["now"] = t0 + 0.3
    for gg, ii in T.project(cell):
        ns["fill"](gg, ii, cell, r)
    line(f"peer {r}'s good copy (control): stored, the probe's promise still open, the verdict",
         (stored(good), (ns["Ask"](g, i), q) in ns["promises"], verdict()), (True, True, "none yet"))

    # 4. the claimant's rejected copy again: seen, and not accepted (its id was not stored)
    pen = nd.penalties
    ns["now"] = t0 + 0.4
    acks = copy_from(q, rejected)
    line("**the claimant's rejected copy again**: the verdict, HAVEs to the claimant, penalties added",
         (verdict(), acks, nd.penalties - pen), ("none yet", 0, 0))

    # 5. the claimant's copy of the cell as stored, a duplicate (its id seen in the run): passes the probe
    line("the claimant's copy of the stored cell (control): its id seen, so the duplicate path",
         ns["seen"](good), True)
    ns["now"] = t0 + 0.45
    acks = copy_from(q, cell)
    line("the claimant's copy of the stored cell (control): the verdict, HAVEs to the claimant",
         (verdict(), acks), (True, 1))
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
