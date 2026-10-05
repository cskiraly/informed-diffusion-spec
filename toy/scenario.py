"""The networks the toy runs on, modelled on the harness's TestQ6RealisticMesh cells.

- latency: the harness's geo model (testing/gossipsim/geo.go), reproduced exactly: same regions,
  same base matrix, same hash, so a seed gives the same one-way latencies as the harness's seed;
- connections: a random d-regular graph (the harness mixes a circulant by edge swaps; any near
  uniform d-regular graph will do, the seed's graph is not reproduced);
- mesh: D = 8 kept between Dlo = 6 and Dhi = 12 by grafting and pruning rounds, as heartbeats do;
- bandwidth classes: home 50/100 Mbps, datacenter 1 Gbps symmetric, by index after the
  source, as SEGMENT_DATACENTER_PCT and SEGMENT_BUILDER_UP_MBPS place them.
"""
import random

M64 = (1 << 64) - 1
REGION_WEIGHTS = [35, 20, 10, 25, 10]                  # eu, na-east, na-west, asia, rest
BASE_MS = [[8, 40, 70, 90, 110],
           [40, 8, 30, 80, 60],
           [70, 30, 8, 60, 70],
           [90, 80, 60, 10, 70],
           [110, 60, 70, 70, 15]]


def geo_mix(x):
    x &= M64
    x ^= x >> 30
    x = (x * 0xbf58476d1ce4e5b9) & M64
    x ^= x >> 27
    x = (x * 0x94d049bb133111eb) & M64
    x ^= x >> 31
    return x


def geo_latency(seed):
    """latency(n, rng) -> f(i, j): the harness's pair function for harness index i-1, j-1."""
    def build(n, _rng):
        total = sum(REGION_WEIGHTS)
        region = []
        for i in range(n):
            r = geo_mix(seed ^ 0x9E01A7E ^ i) % total
            for k, w in enumerate(REGION_WEIGHTS):
                if r < w:
                    region.append(k)
                    break
                r -= w
        cache = {}

        def pair(a, b):                                 # toy ids are harness index + 1
            i, j = a - 1, b - 1
            key = (i, j) if i < j else (j, i)
            v = cache.get(key)
            if v is None:
                if i == j:
                    v = 0.001
                else:
                    lo, hi = key
                    base = BASE_MS[region[i]][region[j]]
                    f = 0.8 + 0.4 * (geo_mix(seed ^ (lo << 20) ^ hi) % 1024) / 1024
                    v = base * f / 1000.0
                cache[key] = v
            return v
        return pair
    return build


def random_regular(n, d, rng, swaps_per_edge=10):
    """A near-uniform random d-regular graph, as the harness builds one: a circulant (each node
    joined to its d/2 nearest on each side of a ring), mixed by degree-preserving double-edge swaps."""
    if d % 2 or d >= n:
        raise ValueError("random_regular needs an even d below n")
    adj = {v: set() for v in range(1, n + 1)}
    edges = []
    for v in range(1, n + 1):
        for k in range(1, d // 2 + 1):
            u = (v - 1 + k) % n + 1
            adj[v].add(u)
            adj[u].add(v)
            edges.append((v, u))
    m = len(edges)
    for _ in range(swaps_per_edge * m):
        i, j = rng.randrange(m), rng.randrange(m)
        a, b = edges[i]
        c, e = edges[j]
        if rng.random() < 0.5:
            c, e = e, c
        if len({a, b, c, e}) < 4 or e in adj[a] or b in adj[c]:
            continue
        adj[a].discard(b); adj[b].discard(a); adj[c].discard(e); adj[e].discard(c)
        adj[a].add(e); adj[e].add(a); adj[c].add(b); adj[b].add(c)
        edges[i], edges[j] = (a, e), (c, b)
    return adj


def gossip_mesh(conns, D, Dlo, Dhi, rng, rounds=20):
    """Grafting and pruning rounds until every node sits between Dlo and Dhi (the stock heartbeat)."""
    mesh = {v: set() for v in conns}
    order = list(conns)
    for _ in range(rounds):
        rng.shuffle(order)
        for v in order:
            if len(mesh[v]) < Dlo:
                cand = [u for u in conns[v] if u not in mesh[v] and len(mesh[u]) < Dhi]
                for u in rng.sample(cand, min(D - len(mesh[v]), len(cand))):
                    mesh[v].add(u)
                    mesh[u].add(v)
            elif len(mesh[v]) > Dhi:
                for u in rng.sample(sorted(mesh[v]), len(mesh[v]) - D):
                    mesh[v].discard(u)
                    mesh[u].discard(v)
    return mesh


def topology(n, d, D, rng):
    conns = random_regular(n, d, rng)
    return conns, gossip_mesh(conns, D, 6, 12, rng)


def fail_select(seed, n, pct, domain=0xF1F1F1F1F1F1F1F1):
    """The harness's faulty nodes (failSelect, topology_test.go): pct % of the non-publishers,
    ranked by a seeded hash; toy ids are the harness's indices plus one."""
    s = geo_mix(seed ^ domain)
    count = max(1, (pct * (n - 1) + 50) // 100)
    idxs = sorted(range(1, n), key=lambda i: geo_mix(s ^ i), reverse=True)
    return {i + 1 for i in idxs[:count]}


HOME = {"up": 50e6, "down": 100e6}
DC = {"up": 1e9, "down": 1e9}


def classes(dc_pct=0, builder_up=None, home=HOME):
    """classes(n, rng) -> {id: link}: node 1 is the source; the datacenter block follows it."""
    def build(n, _rng):
        out = {}
        dc = dc_pct * (n - 1) // 100
        for i in range(1, n + 1):
            out[i] = dict(home)
        for i in range(2, 2 + dc):
            out[i] = dict(DC)
        if builder_up:
            out[1] = {"up": builder_up, "down": builder_up}
        return out
    return build


NETS = {
    "home": dict(),
    "dc20": dict(dc_pct=20),
    "dcb20": dict(dc_pct=20, builder_up=1e9),
    "bld": dict(builder_up=1e9),
}


def net(name, up=None, down=None):
    """A network by name; up/down (bits per second) replace the home link, as the harness's UP and DOWN do."""
    home = dict(HOME)
    if up:
        home = {"up": up, "down": down or 2 * up}
    elif down:
        home["down"] = down
    return classes(home=home, **NETS[name])
