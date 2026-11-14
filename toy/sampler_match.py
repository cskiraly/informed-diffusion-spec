#!/usr/bin/env python3
"""sampler_match.py POPULATION DEGREE [--seeds 7-16] [--draws 400]: can a sampler send each sample
to a different linked custodian? Graph-only, on the toy's networks (no events).

The figures of protocol-v2.md's diversity floor ([D12]: §1.3, §6.3's SAMPLE_COVER row, §8's "The
floor's size"), one sample per peer. For each sampler, links = its own links plus a floor of
sampling-only links, chosen by computed custody (greedy multi-cover, t covers of every column):
  (i)   own links only;
  (ii)  one cover, a high-custody peer (64 or more columns) counting toward all its columns, and
        eligible as a floor link (never the proposer, which rotates; it counts where already linked);
  (iii) one cover under the diversity rule: a high-custody link counts toward at most k columns
        (k = 1) or none (k = 0); the floor's links are custodians of fewer than 64 columns;
  (iv)  two covers under the same rule; and three and four, to find where the targets are reached.
A sample set is 8 (and 16, the sensitivity) distinct cells drawn uniformly from 128 columns x 32
rows; it is matched when every sample goes to a distinct link custodying its column (Kuhn's
augmenting paths), which Hall's condition decides. The same draws are used under every floor.
POPULATION: custody (8-column custodians and the proposer), sn5 (5 % supernodes), rows (the row
setting: 10 % custody 64 columns).
"""
import contextlib
import io
import os
import random
import statistics as st
import sys

TOY = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOY)
os.chdir(TOY)

import run  # noqa: E402
import sim as simmod  # noqa: E402

COLS, ROWS = 128, 32
POPS = {"custody": "--setting custody --samplers 20",
        "sn5": "--setting custody --samplers 20 --supernodes 5",
        "rows": "--setting rows --row-subnets 32 --samplers 20"}
FLOORS = [("(i) own links only", None, 0), ("(ii) one cover, high-custody counted in full", "all", 1),
          ("(iii) one cover, high-custody ≤ 1 column", "k1", 1), ("(iii) one cover, high-custody not counted", "k0", 1),
          ("(iv) two covers, high-custody ≤ 1 column", "k1", 2), ("(iv) two covers, high-custody not counted", "k0", 2),
          ("three covers, high-custody ≤ 1 column", "k1", 3), ("three covers, high-custody not counted", "k0", 3),
          ("four covers, high-custody ≤ 1 column", "k1", 4), ("four covers, high-custody not counted", "k0", 4)]
_built = []


def build(args, seed):
    def capture(cfg, out=None):
        _built.append(simmod.Sim(cfg))
    run.run = capture
    with contextlib.redirect_stdout(io.StringIO()):
        run.main(f"{args} --doc v2 --msgs 1 --net bld --seed {seed}".split())
    s = _built.pop()
    return s, {i: sorted(s.custody.get(i) or ()) for i in s.nodes}


def floor(own, cust, cands, rule, t, rng):
    """The floor's added links: greedy until every column has t custodians among the links, a
    high-custody link counting in full ("all"), toward one column ("k1") or none ("k0")."""
    if rule is None or t == 0:
        return []
    cnt = [0] * COLS
    for q in own:
        cols = cust[q]
        if len(cols) < 64 or rule == "all":
            for c in cols:
                cnt[c] += 1
        elif rule == "k1":
            c = min(cols, key=lambda x: cnt[x])         # toward the column that needs it most
            cnt[c] += 1
    pool = [q for q in cands if rule == "all" or len(cust[q]) < 64]
    rng.shuffle(pool)
    masks = {q: sum(1 << c for c in cust[q]) for q in pool}
    added = []
    while True:
        need = sum(1 << c for c in range(COLS) if cnt[c] < t)
        if not need:
            return added
        best = max(pool, key=lambda q: (masks[q] & need).bit_count(), default=None)
        if best is None or not masks[best] & need:
            return added                                # cannot complete from these candidates
        pool.remove(best)
        added.append(best)
        for c in cust[best]:
            cnt[c] += 1


def matched(cols, serve):
    """Every sample (its column) to a distinct link serving that column: Kuhn's augmenting paths."""
    owner = {}

    def augment(i, seen):
        for q in serve[cols[i]]:
            if q in seen:
                continue
            seen.add(q)
            if q not in owner or augment(owner[q], seen):
                owner[q] = i
                return True
        return False
    return all(serve[c] for c in cols) and all(augment(i, set()) for i in range(len(cols)))


def main():
    pop, deg = sys.argv[1], int(sys.argv[2])
    opts = dict(zip(sys.argv[3::2], sys.argv[4::2]))
    a, b = opts.get("--seeds", "7-16").split("-")
    seeds, draws = range(int(a), int(b) + 1), int(opts.get("--draws", "400"))
    rows = {f[0]: dict(p8=[], p16=[], added=[], mean_srv=[], min_srv=[], le1=[]) for f in FLOORS}
    for seed in seeds:
        s, cust = build(f"--nodes 500 --degree {deg} {POPS[pop]}", seed)
        rng = random.Random(seed * 7919 + 31)
        per_seed = {f[0]: ([], []) for f in FLOORS}
        cells = [(c, r) for c in range(COLS) for r in range(ROWS)]
        for i, nd in s.nodes.items():
            if not nd.sampler:
                continue
            own = [q for q in nd.peers if cust[q]]
            cands = [q for q in s.nodes if q != i and q != 1 and q not in nd.peers and cust[q]]
            d8 = [[c for c, _ in rng.sample(cells, 8)] for _ in range(draws)]
            d16 = [[c for c, _ in rng.sample(cells, 16)] for _ in range(draws)]
            for label, rule, t in FLOORS:
                add = floor(own, cust, cands, rule, t, random.Random(seed * 104729 + i))
                links = own + add
                serve = [[] for _ in range(COLS)]
                for q in links:
                    for c in cust[q]:
                        serve[c].append(q)
                r = rows[label]
                r["added"].append(len(add))
                k = [len(x) for x in serve]
                r["mean_srv"].append(sum(k) / COLS)
                r["min_srv"].append(min(k))
                r["le1"].append(sum(1 for x in k if x <= 1) / COLS)
                per_seed[label][0].append(sum(matched(cols, serve) for cols in d8) / draws)
                per_seed[label][1].append(sum(matched(cols, serve) for cols in d16) / draws)
        for label, (p8, p16) in per_seed.items():
            rows[label]["p8"].append(st.mean(p8))
            rows[label]["p16"].append(st.mean(p16))
    pct = lambda xs: f"{100 * st.mean(xs):.2f} % ({100 * min(xs):.2f} to {100 * max(xs):.2f})"
    q = lambda xs, f: sorted(xs)[min(len(xs) - 1, int(f * len(xs)))]
    for label, r in rows.items():
        ad = r["added"]
        print(f"| {deg} | {pop} | {label} | {st.median(ad):.0f} / {q(ad, .9)} / {max(ad)} | {pct(r['p8'])} | {pct(r['p16'])} | "
              f"{st.mean(r['mean_srv']):.1f} | {st.mean(r['min_srv']):.2f} | {100 * st.mean(r['le1']):.1f} % |", flush=True)


if __name__ == "__main__":
    main()
