"""The networks the toy runs on, modelled on the harness's TestQ6RealisticMesh cells.

- latency: the harness's geo model (testing/gossipsim/geo.go), reproduced exactly: same regions,
  same base matrix, same hash, so a seed gives the same one-way latencies as the harness's seed;
- connections: a random d-regular graph (the harness mixes a circulant by edge swaps; any near
  uniform d-regular graph will do, the seed's graph is not reproduced);
- mesh: D = 8 kept between Dlo = 6 and Dhi = 12 by grafting and pruning rounds, as heartbeats do;
- bandwidth classes: home 50/100 Mbps, datacenter 1 Gbps symmetric, by index after the
  source, as SEGMENT_DATACENTER_PCT and SEGMENT_BUILDER_UP_MBPS place them.
"""
import hashlib
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


# ---- the custody setting (protocol-v2.md §6.2): columns, custodians, a mesh per column

NUMBER_OF_COLUMNS = 128


def custody_columns(node_id, count):
    """das-core's get_custody_groups over a node id (bytes), with one column per custody group."""
    if count >= NUMBER_OF_COLUMNS:
        return set(range(NUMBER_OF_COLUMNS))
    cur, out = int.from_bytes(node_id, "big"), []
    while len(out) < count:
        c = int.from_bytes(hashlib.sha256(cur.to_bytes(32, "little")).digest()[:8], "little") % NUMBER_OF_COLUMNS
        if c not in out:
            out.append(c)
        cur = (cur + 1) % (1 << 256)
    return set(out)


def row_subnet(node_id, count):
    """EIP-8371's get_row_subnet: bytes [8:16] of the node id's hash, so that it is decorrelated from custody."""
    return int.from_bytes(hashlib.sha256(node_id).digest()[8:16], "little") % count


def family_topology(conns, members, rng, D, floor, exclude=()):
    """Top up the connection graph so that every member of a family has `floor` fellow members as
    peers (or all there are), as peer search for subnet coverage does, and build a gossipsub mesh
    per family on the members' subgraph. members: {family: [nodes]}; nodes in `exclude` (the
    source) get no top-ups here and sit in no mesh."""
    fams_of = {}
    for fam, ms in members.items():
        for v in ms:
            fams_of.setdefault(v, []).append(fam)
    order = [v for v in conns if v not in exclude and v in fams_of]
    rng.shuffle(order)
    for v in order:
        for fam in sorted(fams_of[v]):
            ms = [u for u in members[fam] if u not in exclude]
            pool = [u for u in ms if u != v and u not in conns[v]]
            have = sum(1 for u in conns[v] if u not in exclude and u in set(members[fam]))
            need = min(floor, len(ms) - 1) - have
            for u in rng.sample(pool, max(0, min(need, len(pool)))):
                conns[v].add(u)
                conns[u].add(v)
    meshes = {}
    for fam, ms in members.items():
        ms = [u for u in ms if u not in exclude]
        mset = set(ms)
        sub = {v: {u for u in conns[v] if u in mset} for v in ms}
        meshes[fam] = gossip_mesh(sub, D, 6, 12, rng) if ms else {}
    return meshes


def custody_topology(n, d, D, rng, custody, floor=6, source_floor=2, row_subnets=None, repair_floor=0, repair_rng=None):
    """Connections and a mesh per column (and per row subnet) for the custody and row settings. The
    base is the random d-regular graph; then each node adds custodian peers until it has `floor` of
    them for every column it custodies (or all there are), the source, node 1, until it has
    `source_floor` for every column (its fanout), and, with row_subnets = {node: subnet}, each
    member adds fellow members until it has `floor`. The mesh of a column or a row subnet is
    gossipsub's, built on the subgraph of its members, without the source. Last, with
    `repair_floor`, each row member adds custodian peers until it has that many for every column
    it does not custody (the rebuilders' fanout, protocol-v2.md §4.6), drawn from `repair_rng` after
    the meshes, so that the graph and the meshes are the same with and without it and these links
    are in no mesh. Returns the connections, the meshes and the number of links the floor added."""
    conns = random_regular(n, d, rng)
    custodians = {c: [v for v in conns if v != 1 and c in custody[v]] for c in range(NUMBER_OF_COLUMNS)}
    meshes = family_topology(conns, custodians, rng, D, floor, exclude={1})
    for c in range(NUMBER_OF_COLUMNS):                  # the source's fanout
        pool = [u for u in custodians[c] if u not in conns[1]]
        have = sum(1 for u in conns[1] if c in custody[u])
        need = min(source_floor, len(custodians[c])) - have
        for u in rng.sample(pool, max(0, min(need, len(pool)))):
            conns[1].add(u)
            conns[u].add(1)
    row_meshes = None
    if row_subnets:
        members = {}
        for v, s in row_subnets.items():
            if s is not None:
                members.setdefault(s, []).append(v)
        row_meshes = family_topology(conns, members, rng, D, floor, exclude={1})
    added = 0
    if row_subnets and repair_floor:                   # the rebuilders' fanout: a row member may rebuild any row
        for v in sorted(v for v, s in row_subnets.items() if s is not None):   # of its subnet (phase 3)
            for c in range(NUMBER_OF_COLUMNS):
                if c in custody[v]:
                    continue
                have = sum(1 for u in conns[v] if u != 1 and c in custody[u])
                pool = [u for u in custodians[c] if u not in conns[v]]
                need = min(repair_floor, len(custodians[c])) - have
                for u in repair_rng.sample(pool, max(0, min(need, len(pool)))):
                    conns[v].add(u)
                    conns[u].add(v)
                    added += 1
    return conns, meshes, row_meshes, added


def fail_select(seed, n, pct, domain=0xF1F1F1F1F1F1F1F1):
    """The harness's faulty nodes (failSelect, topology_test.go): pct % of the non-publishers,
    ranked by a seeded hash; toy ids are the harness's indices plus one."""
    s = geo_mix(seed ^ domain)
    count = max(1, (pct * (n - 1) + 50) // 100)
    idxs = sorted(range(1, n), key=lambda i: geo_mix(s ^ i), reverse=True)
    return {i + 1 for i in idxs[:count]}


HOME = {"up": 50e6, "down": 100e6}
DC = {"up": 1e9, "down": 1e9}


def classes(dc_pct=0, builder_up=None, home=HOME, dc_link=DC):
    """classes(n, rng) -> {id: link}: node 1 is the source; the datacenter block follows it."""
    def build(n, _rng):
        out = {}
        dc = dc_pct * (n - 1) // 100
        for i in range(1, n + 1):
            out[i] = dict(home)
        for i in range(2, 2 + dc):
            out[i] = dict(dc_link)
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


def net(name, up=None, down=None, dc=None, builder=None):
    """A network by name; up/down (bits per second) replace the home link, as the harness's UP and DOWN do;
    dc the datacenter link and builder a datacenter builder's, both ways, as SEGMENT_DATACENTER_MBPS and
    SEGMENT_BUILDER_UP_MBPS do."""
    home = dict(HOME)
    if up:
        home = {"up": up, "down": down or 2 * up}
    elif down:
        home["down"] = down
    kw = dict(NETS[name])
    if builder and kw.get("builder_up"):
        kw["builder_up"] = builder
    return classes(home=home, dc_link={"up": dc, "down": dc} if dc else DC, **kw)
