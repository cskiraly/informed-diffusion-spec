#!/usr/bin/env python3
"""Directed records for §5.3's choose_push and guard_fails (protocol.md §5.3). The toy's own functions
are called in a toy node's namespace on generated states, and trace3.py's tracer logs each call with the node's
whole state.

    python3 directed53.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

What the records reach that the cells do not (in all fifteen cells nobody is proven in 10 calls, and two
tie-breaks are never equal: the toy's is 64 bits of a hash):
- choose_push away from the source: the lower half's draw, with a pool smaller than the budget, as large, larger;
  nobody proven (no draw); the guard's demoted peers last, reached by the budget or not;
- budgets from none to more than the candidates (everyone, no question asked); no candidate;
- equal counts, where the tie-break decides; **equal tie-breaks** (the scenario's, drawn from four values), where
  the peer's id decides; ids that share their first byte;
- guard_fails, alone and under choose_push: fewer than R_NODE pushed; R_NODE and more, the first within the
  grace, at it exactly, past it; past it with a HAVE from the peer for the group, an empty one too, and with none
  (demoted).

The states are in the toy's own forms: an entry of `pushed` as note_push leaves it (bits, a clock, a ttl);
`peer_has` assigned as on_have does, one in five with no bit. The scenario answers tiebreak and peer_id_bytes; the
draw is the toy's own. The node is node 2 of a 5-node cell built as run.py builds it (R_NODE 2, GUARD_GRACE
0.2 s). A sample on which the Python raises is written with `raises` by the tracer; the counts are printed.
"""
import argparse
import random
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402

FNS = ["choose_push"] * 3 + ["guard_fails"]


class Scenario:
    def __init__(self):
        self.tie, self.ids = {}, {}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed53", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    nd = got["sim"].nodes[2]
    ns = nd.ns
    sc = Scenario()
    ns["content_id"] = lambda f: f.cid
    ns["tiebreak"] = lambda f, p: sc.tie[p]
    ns["peer_id_bytes"] = lambda p: sc.ids[p]
    tr.install(nd, ns)
    R_NODE, GRACE = int(ns["R_NODE"]), float(ns["GUARD_GRACE"])
    assert (R_NODE, GRACE) == (2, 0.2), (R_NODE, GRACE)

    rng = random.Random(a.seed)
    groups = [bytes([0x11 * (j + 1)]) * 32 for j in range(3)]
    root = bytes([0xa1]) * 32
    raised, kinds = Counter(), Counter()
    for _ in range(a.n):
        what = rng.choice(FNS)
        ns["now"] = rng.choice([1.0, 3.25, GRACE])      # at GRACE, a first push at 0.0 is the grace ago exactly
        peers = rng.sample(range(1, 64), rng.randrange(0, 9))
        g = rng.choice(groups)
        c = rng.choice([4, 6, 8])
        i = rng.randrange(c)
        cid = bytes([7]) * 20
        f = types.SimpleNamespace(slot=1, beacon_block_root=root, group=g, index=i, cid=cid,
                                  mid=g + i.to_bytes(4, "little") + cid)
        sc.__init__()
        wide = rng.random() < 0.3                   # tie-breaks apart, as the toy's are; else four values: ties
        for q in range(1, 64):
            sc.tie[q] = rng.randrange(1 << 64) if wide else rng.choice([0, 1, 2, (1 << 64) - 1])
            sc.ids[q] = bytes([rng.choice([0, 0x80]), q])   # distinct, half of them with one first byte

        # ---- the state, cleared, then drawn
        for name in ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
                     "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
                     "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
                     "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue",
                     "planned"):
            ns[name].clear()
        ns["offers"]._d.clear()
        ns["offers"].listed.clear()
        ns["tied"]._d.clear()
        nd._by_index.clear()
        ns["mesh"] = set(peers)
        few = rng.random() < 0.5                    # counts from a few values, so that candidates tie
        for q in peers:
            for gg in groups:
                if rng.random() < 0.5:              # assigned, as the toy's on_have does: the entry joins its map
                    h = ns["peer_has"][q][gg]
                    h.bits = B.Bits(0 if rng.random() < 0.2 else
                                    rng.choice([1, 3]) if few else rng.randrange(1 << c))
                    h.ttl = int(ns["HAVE_TTL"])
                if rng.random() < 0.6:
                    pe = ns["pushed"][q][gg]         # as note_push leaves it: a clock and a ttl with its bits
                    pe.first_push = ns["now"] - rng.choice([0.0, 0.05, GRACE, 0.3, 1.0])
                    pe |= B.Bits(rng.choice([1, 2, 3, 7]) if few else rng.randrange(1, 1 << c))
                    if rng.random() < 0.1:
                        pe.v = 0                     # no bit left, as unpush can leave it
                    pe.ttl = rng.randrange(1, int(ns["PUSH_TTL"]) + 1)

        # ---- the call
        def guard(q):                               # which test of the guard decides for q, read from the state
            there = g in ns["pushed"][q]
            e = ns["pushed"][q][g] if there else None
            if e is None or bin(e.v).count("1") < R_NODE:
                return "fewer than R_NODE pushed"
            d = ns["now"] - e.first_push
            if not d > GRACE:
                return "at the grace exactly" if d == GRACE else "within the grace"
            return "a HAVE seen" if g in ns["peer_has"][q] else "demoted"
        try:
            if what == "guard_fails":
                q = rng.choice(peers) if peers and rng.random() < 0.9 else rng.randrange(1, 64)
                kinds[f"guard_fails: {guard(q)}"] += 1
                ns["guard_fails"](q, g)
            else:
                cands = list(peers)
                rng.shuffle(cands)
                cands = cands[:rng.randrange(len(cands) + 1)]
                if cands and rng.random() < 0.75:           # below the candidates: the order is made
                    budget = rng.randrange(len(cands))
                else:                                       # everyone: no question asked
                    budget = rng.choice([len(cands), len(cands) + 1, 6])
                at_source = rng.random() < 0.3
                demoted = sum(guard(q) == "demoted" for q in cands)
                kinds["choose_push: " + ("everyone" if budget >= len(cands) else
                                         ("at the source" if at_source else
                                          "nobody proven" if demoted == len(cands) else "a draw")
                                         + (", some demoted" if demoted else "")
                                         + (", tie-breaks from four values" if not wide else ""))] += 1
                ns["choose_push"](f, cands, budget, at_source=at_source)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed53: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for k, n in sorted(kinds.items()):
        print(f"  {k}: {n}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
