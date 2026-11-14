#!/usr/bin/env python3
"""sampler_graph.py PART [--seeds 7-16]: how a sampler reaches custodians, on the toy's graphs.

The figures of protocol-v2.md's [D12] (§1.3, §4.10, §6.3's SAMPLE_COVER and ROUTE_FLOOR rows, §8's
"A sampler's reach"): three ways for a sampler to reach a custodian of each column, graph-only
(no events): each network is built by the toy (custody from node ids, das-core's
get_custody_groups; the random regular graph plus the custodian floor), 500 nodes, a fifth of them
samplers.

  a   the coverage floor (SAMPLE_COVER): sampling-only links a sampler adds, chosen by computed
      custody (greedy set multi-cover), so that every column has a custodian among its links once
      (t = 1) or twice (t = 2); on top of its existing links and from scratch; with and without
      high-custody peers (the proposer, supernodes, the row setting's 64-column reconstructors)
      counting.
  c   routed sample requests under routing rules (ROUTE_FLOOR): hops from a sampler to a custodian
      of each column under today's random links, a hypercube rule (every custodian keeps, per
      custody column c, a link to a custodian of c + 2^j mod 128, j = 0..6) and a Kademlia-style rule
      (per c and j, a link to a custodian of a column in XOR bucket j of c); greedy forwarding on
      computed custody and the shortest path; and the links each rule adds.
  e   rows as a second axis (§8; `serves` counts columns only): a cell is served by a custodian of
      its column or by a member of its row's subnet holding it, half the row (the draft: a member
      stops at 64 of 128 cells) or all of it (FullDAS's two-dimensional code); 32 and 128 row
      subnets.
"""
import contextlib
import io
import os
import random
import statistics as st
import sys
from collections import deque
from math import comb

TOY = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOY)
os.chdir(TOY)

import run  # noqa: E402
import scenario  # noqa: E402
import sim as simmod  # noqa: E402

COLS, ROWS, SAMPLES, J = 128, 32, 8, 7
FULL = (1 << COLS) - 1
_built = []


def build(args, seed):
    """The toy's network for these run.py arguments, no events run: (sim, custody as sets, as masks)."""
    def capture(cfg, out=None):
        _built.append(simmod.Sim(cfg))
    run.run = capture
    with contextlib.redirect_stdout(io.StringIO()):
        run.main(f"{args} --doc v2 --msgs 1 --net bld --seed {seed}".split())
    s = _built.pop()
    cust = {i: set(s.custody.get(i) or ()) for i in s.nodes}
    mask = {i: sum(1 << c for c in cols) for i, cols in cust.items()}
    return s, cust, mask


def dist_summary(xs):
    xs = sorted(xs)
    q = lambda f: xs[min(len(xs) - 1, int(f * len(xs)))]
    return f"{xs[0]} / {q(.1)} / {q(.5)} / {q(.9)} / {xs[-1]} (mean {st.mean(xs):.1f})"


# ---- a: the coverage floor

def floor_links(have, cands, t, rng):
    """Greedy multi-cover with column masks: links added from cands (masks) until every column is
    covered t (1 or 2) times, counting `have` (masks of the links already there)."""
    m0, m1 = FULL, 0                                    # columns covered 0 times, once (t = 2)
    for h in have:
        if t == 2:
            m0, m1 = m0 & ~h, (m1 & ~h) | (m0 & h)
        else:
            m0 &= ~h
    need = lambda: (m0 | m1) if t == 2 else m0
    pool = list(cands)
    rng.shuffle(pool)                                   # ties broken at random
    added = 0
    while need():
        nd = need()
        best = max(range(len(pool)), key=lambda k: (pool[k] & nd).bit_count(), default=None)
        if best is None or not (pool[best] & nd):
            return None                                 # these candidates cannot cover it
        h = pool.pop(best)
        if t == 2:
            m0, m1 = m0 & ~h, (m1 & ~h) | (m0 & h)
        else:
            m0 &= ~h
        added += 1
    return added


def part_a(seeds):
    pops = [("custodians of 8 columns and the proposer", "--setting custody --samplers 20"),
            ("with 5 % supernodes", "--setting custody --samplers 20 --supernodes 5"),
            ("the row setting (10 % custody 64 columns)", "--setting rows --row-subnets 32 --samplers 20")]
    print("| degree | population | high-custody peers | t | links added on top of the sampler's own: min / p10 / median / p90 / max (mean) | from scratch: min / p10 / median / p90 / max (mean) |")
    print("|---|---|---|---|---|---|")
    for deg in (16, 70):
        for label, args in pops:
            rows = {(high, t): ([], []) for high in (False, True) for t in (1, 2)}
            for seed in seeds:
                s, cust, mask = build(f"--nodes 500 --degree {deg} {args}", seed)
                rng = random.Random(seed * 7919 + 77)
                for high in (False, True):
                    # counted: a link to a node of 64 columns or more covers its columns; such nodes may be
                    # chosen, but never the proposer (the block's source rotates); not counted: neither
                    ok = lambda q: mask[q] and (high or len(cust[q]) <= 8)
                    cand = lambda q: ok(q) and q != 1
                    for t in (1, 2):
                        on_top, scratch = rows[(high, t)]
                        for k, (i, nd) in enumerate((i, nd) for i, nd in s.nodes.items() if nd.sampler):
                            peers = set(nd.peers)
                            on_top.append(floor_links([mask[q] for q in peers if ok(q)],
                                                      [mask[q] for q in s.nodes if q != i and q not in peers and cand(q)], t, rng))
                            if k < 20:                          # from scratch depends only on the draw: 20 a seed
                                scratch.append(floor_links([], [mask[q] for q in s.nodes if q != i and cand(q)], t, rng))
            for (high, t), (on_top, scratch) in rows.items():
                print(f"| {deg} | {label} | {'counted' if high else 'not counted'} | {t} | {dist_summary(on_top)} | "
                      f"{dist_summary(scratch)} |", flush=True)


# ---- c: forwarding hops under routing rules

def add_rule(s, cust, rule, rng):
    """The links the rule adds among custodians of fewer than 64 columns (samplers have no position,
    high custody needs none): per custody column c and j = 0..6, a link to a custodian of c + 2^j
    (hypercube) or of a column in c's XOR bucket j (Kademlia-style), where the node has none.
    Returns the adjacency and the links each node gained (both ends counted)."""
    adj = {i: set(nd.peers) for i, nd in s.nodes.items()}
    of_col = {c: [v for v in s.nodes if c in cust[v]] for c in range(COLS)}
    gained = {i: 0 for i in s.nodes}
    if rule == "random":
        return adj, gained
    for v in sorted(s.nodes):
        if not cust[v] or len(cust[v]) >= 64:
            continue
        for c in sorted(cust[v]):
            for j in range(J):
                if rule == "hypercube":
                    targets = {(c + (1 << j)) % COLS}
                else:
                    targets = {b for b in range(COLS) if (c ^ b).bit_length() - 1 == j}
                if any(cust[q] & targets for q in adj[v]):
                    continue
                pool = sorted({q for x in targets for q in of_col[x] if q != v})
                if not pool:
                    continue
                q = rng.choice(pool)
                adj[v].add(q)
                adj[q].add(v)
                gained[v] += 1
                gained[q] += 1
    return adj, gained


def part_c(seeds, cap=12):
    hyper = lambda a, x: bin((x - a) % COLS).count("1")
    kad = lambda a, x: a ^ x
    print("| degree | custodian floor | links | forwarding | 1 hop | 2 hops | ≥ 3 hops | not reached | links added per custodian: median / mean / max | links per custodian, median |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for deg, (floor_label, floor_args) in [(d, f) for d in (16, 70) for f in (("6 a column (the toy)", ""), ("none", " --floor 0 --source-floor 0"))]:
        for rule in ("random", "hypercube", "kademlia"):
            res = {"greedy on computed custody": [0, 0, 0, 0], "shortest path": [0, 0, 0, 0]}
            gains, degs = [], []
            for seed in seeds:
                s, cust, mask = build(f"--nodes 500 --degree {deg} --setting custody --samplers 20{floor_args}", seed)
                adj, gained = add_rule(s, cust, rule, random.Random(seed * 7919 + 99))
                for v in s.nodes:
                    if cust[v] and len(cust[v]) < 64:
                        gains.append(gained[v])
                        degs.append(len(adj[v]))
                dfun = kad if rule == "kademlia" else hyper
                dn = {v: [min((dfun(a, x) for a in cust[v]), default=None) for x in range(COLS)] for v in s.nodes}
                of_col = {c: [v for v in s.nodes if c in cust[v]] for c in range(COLS)}
                for i, nd in s.nodes.items():
                    if not nd.sampler:
                        continue
                    dist, dq = {i: 0}, deque([i])               # one BFS per sampler
                    while dq:
                        v = dq.popleft()
                        if dist[v] >= 4:
                            continue
                        for q in adj[v]:
                            if q not in dist:
                                dist[q] = dist[v] + 1
                                dq.append(q)
                    for x in range(COLS):
                        sp = min((dist[v] for v in of_col[x] if v in dist), default=None)
                        cur, hops, seen, best, gh = i, 0, {i}, None, None
                        while hops < cap:                       # greedy: the link nearest x by its custody
                            cand = [(dn[q][x], q) for q in adj[cur] if q not in seen and cust[q]]
                            if not cand:
                                break
                            d, q = min(cand)
                            if best is not None and d >= best:
                                break                           # stuck: no link nearer
                            hops += 1
                            if d == 0:
                                gh = hops
                                break
                            seen.add(q)
                            cur, best = q, d
                        for how, h in (("greedy on computed custody", gh), ("shortest path", sp)):
                            res[how][3 if h is None else min(h, 3) - 1] += 1
            for how, r in res.items():
                n = sum(r)
                print(f"| {deg} | {floor_label} | {rule} | {how} | {100 * r[0] / n:.1f} % | {100 * r[1] / n:.1f} % | {100 * r[2] / n:.1f} % | "
                      f"{100 * r[3] / n:.2f} % | {st.median(gains):.0f} / {st.mean(gains):.1f} / {max(gains)} | {st.median(degs):.0f} |", flush=True)


# ---- e: rows as a second axis

def all_served(s_vals):
    """P(8 distinct cells drawn uniformly all served) = e_8(s) / C(4096, 8): the elementary symmetric
    polynomial of the cells' service probabilities (cells independent given the graph)."""
    e = [1.0] + [0.0] * SAMPLES
    for v in s_vals:
        if v:
            for k in range(SAMPLES, 0, -1):
                e[k] += e[k - 1] * v
    return e[SAMPLES] / comb(ROWS * COLS, SAMPLES)


def part_e(seeds):
    print("| degree | a row member holds | row subnets | samplers expected not to confirm: mean over seeds (range) | cells a sampler cannot be served, mean of 4 096 |")
    print("|---|---|---|---|---|")
    for deg in (16, 70):
        for hold, label in ((0.0, "nothing counted (columns only; the known answer)"), (0.5, "half its row (the draft: 64 of 128)"),
                            (1.0, "its whole row (FullDAS's two-dimensional code)")):
            for subnets in ((32,) if hold == 0 else (32, 128)):
                per_seed, unserved = [], []
                for seed in seeds:
                    s, cust, mask = build(f"--nodes 500 --degree {deg} --setting custody --samplers 20", seed)
                    sub = {i: scenario.row_subnet(s.peer_id(i), subnets) for i in s.nodes
                           if i != 1 and not s.nodes[i].sampler}
                    row_sub = random.Random(seed * 7919 + 55).sample(range(subnets), ROWS)   # the block's rows onto subnets
                    fails = []
                    for i, nd in s.nodes.items():
                        if not nd.sampler:
                            continue
                        covered = set().union(*(cust[q] for q in nd.peers))
                        members = [sum(1 for q in nd.peers if sub.get(q) == row_sub[r]) for r in range(ROWS)]
                        served = [1.0 if c in covered else 1 - (1 - hold) ** members[r] for c in range(COLS) for r in range(ROWS)]
                        unserved.append(sum(1 - v for v in served))
                        fails.append(1 - all_served(served))
                    per_seed.append(st.mean(fails))
                print(f"| {deg} | {label} | {subnets if hold else '–'} | {100 * st.mean(per_seed):.1f} % "
                      f"({100 * min(per_seed):.1f} to {100 * max(per_seed):.1f} %) | {st.mean(unserved):.0f} |", flush=True)


if __name__ == "__main__":
    part = sys.argv[1]
    a, b = (sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--seeds" else "7-16").split("-")
    seeds = range(int(a), int(b) + 1)
    {"a": part_a, "c": part_c, "e": part_e}[part](seeds)
