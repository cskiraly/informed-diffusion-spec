"""The cross-check with the research harness: its network, loaded, and its per-rule counters and
invariants, counted here the same way.

load(path) reads the harness's SEGMENT_XC_DUMP file: gzip'd JSON lines, first the network (each
node's uplink and downlink, each connection with its one-way delay, each node's push degree, the
faulty set and its knobs), then one line per message with its publisher and every node's mesh at
the publish. apply(cfg, topo) makes those the toy's classes, latencies, connections, meshes,
publishers and faulty set, so that what still differs from the harness is the link model and the
rules, not the topology. Toy ids are the harness's node indices plus one.

A DAS dump (the research harness's column proxy) adds records of its own beside net: network
(the base graph), shape (the links the harness added, each with its pass), faults, das (custody,
supernodes, reconstructors, row subnets) and, from a running cell, a block record and a mesh per
column topic. check(topo) stops on records that disagree, and apply_das(cfg, topo) makes them the
custody or row setting's network in place of the toy's own draws (sim.py reads cfg["das_dump"]).

Recorder counts what the harness's xcheck line counts (its xcheck_test.go): at the sender's
transmit, after the writer's filter, as the harness counts at the stream write; at the receiver's
delivery; and in the document's filter_entry (cancel), acquire_slot and track_in_flight (the
window). It reads node state with get(), so no map grows; its delivery hook keeps the name the
digest records, and it schedules nothing: a run's events and digest are the same with it or
without it. Per message it resets at the publish and is read at the horizon, publish + 3 s.

The invariants, each a count that must be zero:
- budget: forwarding nodes that pushed one chunk more often than their push degree (R_NODE);
- window: nodes whose slots in flight exceeded W;
- overlap: an ask for a chunk decided while an earlier ask for it was open (inside IWANT_WINDOW,
  the chunk not yet held), timed at may_ask, where the harness's request ledger also times asks
  (when the router sends them, not when the writer writes them);
- late: chunks sent to a mesh peer whose HAVE (in an IDONTWANT, the only carrier that feeds
  peer_has, §4.4) for them had reached the sender earlier in the message, whether or not the sender
  still holds it: the harness's ledger reads it the same way. late_live, a diagnostic, counts those
  whose HAVE the sender still held, which cancel (card 8) should have dropped;
- fault: chunks sent by silent nodes, answers sent by withholders.
"""
import gzip
import json
import statistics
from collections import Counter, defaultdict

import wire as Wm
from scenario import NUMBER_OF_COLUMNS

KEYS = ("push", "answer", "cancel", "ask", "iwant_ids", "have_ihave", "ihave_ids",
        "have_idontwant", "idontwant_ids", "dup", "rx")


# ---- the harness's network


def load(path):
    """The dump as a dict: net (the first record) and meshes {msg: (pub, [[peer, ...] by node])}. A DAS
    dump also has network (the base graph), shape (the links the harness
    added, each with its pass), faults, das, blocks {msg: record} and topic_meshes {msg: {topic: (pub,
    mesh)}}; one resolved without a run has no net, block or mesh. Records of other kinds are ignored."""
    opener = gzip.open if str(path).endswith(".gz") else open
    rec = dict.fromkeys(("net", "network", "shape", "faults", "das"))
    meshes, topic_meshes, blocks = {}, {}, {}
    with opener(path, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            k = r["kind"]
            if k in rec:
                rec[k] = r
            elif k == "block":
                blocks[r["msg"]] = r
            elif k == "mesh" and "topic" in r:
                topic_meshes.setdefault(r["msg"], {})[r["topic"]] = (r["pub"], r["mesh"])
            elif k == "mesh":
                meshes[r["msg"]] = (r["pub"], r["mesh"])
    if rec["net"] is None and rec["network"] is None:
        raise ValueError(f"{path}: no network record")
    if set(meshes) & set(topic_meshes):
        raise ValueError(f"{path}: mesh records with and without a topic for msgs {sorted(set(meshes) & set(topic_meshes))}")
    return dict(rec, meshes=meshes, topic_meshes=topic_meshes, blocks=blocks)


def _edges(*records):
    """{(a, b) with a < b: owd_ms} over the records' edges; a pair given twice is an error."""
    out = {}
    for r in records:
        for e in r["edges"]:
            k = (min(e["a"], e["b"]), max(e["a"], e["b"]))
            if k in out:
                raise ValueError(f"the edge {k} is given twice")
            out[k] = e["owd_ms"]
    return out


FAULT_KEYS = ("faulty", "silent", "mute", "underreport", "noack", "push_degree")


def check(topo):
    """The load-time checks of a DAS dump's records (as the harness writes them); each
    mismatch stops the load. `net` is authoritative where it is present: its edges must equal network's
    plus shape's, one-way delays included, its rates network's, and faults must repeat its fault fields.
    The supernodes must be exactly the nodes custodying every column, and each block's proposer one of
    them. A payload dump (net and meshes only) passes unchecked, as before."""
    net, network, shape, faults, das = (topo[k] for k in ("net", "network", "shape", "faults", "das"))
    if network is not None:
        given = _edges(network, *([shape] if shape else []))
        if net is not None:
            want = _edges(net)
            if given != want:
                missing, extra = set(want) - set(given), set(given) - set(want)
                moved = [k for k in set(want) & set(given) if want[k] != given[k]]
                raise ValueError(f"net's edges are not network's plus shape's: {len(missing)} missing, {len(extra)} "
                                 f"extra, {len(moved)} with another delay")
            for k in ("n", "up_bps", "down_bps"):
                if net[k] != network[k]:
                    raise ValueError(f"net's {k} differs from network's")
    if net is not None and faults is not None:
        for k in FAULT_KEYS:
            a, b = net.get(k), faults.get(k)
            if k == "faulty":
                a, b = sorted(a or []), sorted(b or [])
            if a != b:
                raise ValueError(f"faults' {k} differs from net's")
    if das is not None:
        cols = das["columns"]
        full = {i for i, cs in enumerate(das["custody"]) if len(set(cs)) == cols}
        if full != set(das["supernodes"]):
            raise ValueError(f"supernodes {sorted(das['supernodes'])} are not the nodes custodying all {cols} "
                             f"columns {sorted(full)}")
        for b in topo["blocks"].values():
            if b["proposer"] not in full:
                raise ValueError(f"block {b['msg']}'s proposer {b['proposer']} does not custody every column")


def apply(cfg, topo, fallback_latency):
    """Make the dump the toy's network. Returns the notes worth printing (knobs the toy lacks)."""
    net, meshes = topo["net"], topo["meshes"]
    n = net["n"]
    cfg["nodes"] = n
    up, down = net["up_bps"], net["down_bps"]

    def classes(_n, _rng):
        return {i + 1: {"up": float(up[i]), "down": float(down[i])} for i in range(n)}
    cfg["classes"] = classes

    owd = {}
    for e in net["edges"]:
        a, b, s = e["a"] + 1, e["b"] + 1, e["owd_ms"] / 1000.0
        owd[(a, b)] = owd[(b, a)] = s

    def latency(nn, rng):
        geo = fallback_latency(nn, rng)

        def pair(a, b):
            v = owd.get((a, b))
            return v if v is not None else geo(a, b)
        return pair
    cfg["latency"] = latency

    first = meshes[min(meshes)][1] if meshes else None

    def topology(_n, _d, _D, _rng):
        conns = {i: set() for i in range(1, n + 1)}
        for e in net["edges"]:
            conns[e["a"] + 1].add(e["b"] + 1)
            conns[e["b"] + 1].add(e["a"] + 1)
        mesh = {i + 1: {j + 1 for j in first[i]} for i in range(n)} if first else {i: set() for i in conns}
        return conns, mesh
    cfg["topology"] = topology
    cfg["publishers"] = {m: pub + 1 for m, (pub, _) in meshes.items()}
    cfg["meshes"] = {m: [{j + 1 for j in ms} for ms in mesh] for m, (_, mesh) in meshes.items()}
    cfg["fault"] = ""
    cfg["faulty"] = {i + 1 for i in net.get("faulty", [])}
    cfg["silent"] = bool(net.get("silent"))
    notes = []
    for k in ("mute", "underreport", "noack"):
        if net.get(k):
            notes.append(f"the harness ran {k} on the faulty set, which the toy does not model")
    cfg["xc_degree"] = net.get("push_degree")
    return notes


def apply_das(cfg, topo, fallback_latency):
    """Make a DAS dump (check()ed) the toy's network for the custody and row settings: the classes and
    delays, the graph taken whole (network plus shape), the faulty set, and cfg["das_dump"], which sim.py
    reads in place of its own draws: each node's custody, the supernodes (the proposer aside), the
    reconstructors, the row subnets and, from a running cell's first block, the mesh per column and row
    subnet (otherwise sim.py builds them on the graph). The proposer must be node 0 (toy id 1) in every
    block, and the withheld columns the last ones (the toy's --withhold), the same in every block.
    Returns the notes worth printing. Raises ValueError where the dump asks what the toy cannot run."""
    network, shape, das, blocks = topo["network"], topo["shape"], topo["das"], topo["blocks"]
    net = topo["net"]
    n, cols = network["n"], das["columns"]
    if cols != NUMBER_OF_COLUMNS:
        raise ValueError(f"the dump has {cols} columns, the toy {NUMBER_OF_COLUMNS}")
    cfg["nodes"] = n
    up, down = network["up_bps"], network["down_bps"]
    cfg["classes"] = lambda _n, _rng: {i + 1: {"up": float(up[i]), "down": float(down[i])} for i in range(n)}
    edges = _edges(network, *([shape] if shape else []))
    owd = {}
    conns = {i: set() for i in range(1, n + 1)}
    for (a, b), ms in edges.items():
        owd[(a + 1, b + 1)] = owd[(b + 1, a + 1)] = ms / 1000.0
        conns[a + 1].add(b + 1)
        conns[b + 1].add(a + 1)

    def latency(nn, rng):
        geo = fallback_latency(nn, rng)
        return lambda a, b: owd[(a, b)] if (a, b) in owd else geo(a, b)
    cfg["latency"] = latency
    src = net if net is not None else topo["faults"] or {}
    cfg["fault"] = ""
    cfg["faulty"] = {i + 1 for i in src.get("faulty", [])}
    cfg["silent"] = bool(src.get("silent"))
    notes = [f"the harness ran {k} on the faulty set, which the toy does not model"
             for k in ("mute", "underreport", "noack") if src.get(k)]
    cfg["xc_degree"] = src.get("push_degree")

    custody = {i + 1: set(cs) for i, cs in enumerate(das["custody"])}
    if custody[1] != set(range(cols)):
        raise ValueError("node 0, the toy's proposer, does not custody every column")
    if das.get("samplers"):
        raise ValueError("samplers from a dump: not yet")
    row_subnet = {i + 1: s for i, s in enumerate(das["row_subnet"])}
    if row_subnet[1] is not None:
        raise ValueError("node 0, the proposer, has a row subnet")
    withheld = None
    for m, b in sorted(blocks.items()):
        if b["proposer"] != 0:
            raise ValueError(f"block {m}'s proposer is node {b['proposer']}: the toy's is node 0 (id 1), per-block proposers not yet")
        if any((b.get("preseeded") or {}).get(k) for k in ("full", "miss")):
            raise ValueError(f"block {m} is preseeded, which the toy does not model")
        w = sorted(b["withheld"])
        if w != list(range(cols - len(w), cols)):
            raise ValueError(f"block {m} withholds {w}, not the last columns (the toy's --withhold)")
        if withheld is not None and w != withheld:
            raise ValueError(f"block {m} withholds other columns than the first block")
        withheld = w
    meshes = row_meshes = None
    with_meshes = sorted(topo["topic_meshes"])
    if with_meshes:
        def resolve(m):
            by_col, by_row = {}, {}
            for topic, (pub, mesh) in topo["topic_meshes"][m].items():
                if pub != 0:
                    raise ValueError(f"block {m}'s {topic} was published by node {pub}, not node 0")
                kind, x = topic.split("/")
                ms = {}
                for i, peers in enumerate(mesh):
                    v = i + 1
                    if v == 1:
                        continue                                   # the proposer's relation is the toy's (sim.py)
                    member = int(x) in custody[v] if kind == "col" else row_subnet[v] == int(x)
                    if peers and not member:
                        raise ValueError(f"block {m}: node {i} has a mesh on {topic} it is not a member of")
                    if any(j + 1 not in conns[v] for j in peers):
                        raise ValueError(f"block {m}: node {i}'s mesh on {topic} has a peer that is no link")
                    if member:
                        ms[v] = {j + 1 for j in peers}
                (by_col if kind == "col" else by_row)[int(x)] = ms
            return by_col, by_row
        first = resolve(with_meshes[0])
        meshes, row_meshes = first[0], first[1] or None
        for m in with_meshes[1:]:
            later = resolve(m)
            moved = sum(1 for k in (0, 1) for x, ms in later[k].items() for v in ms
                        if ms[v] != first[k].get(x, {}).get(v, set()))
            if moved:
                notes.append(f"block {m}'s meshes differ from block {with_meshes[0]}'s at {moved} (node, topic) pairs; "
                             f"the toy keeps the first block's")
        if len(meshes) != cols:
            raise ValueError(f"block {with_meshes[0]} has meshes for {len(meshes)} of {cols} columns")
    passes = Counter(e["pass"] for e in shape["edges"]) if shape else Counter()
    cfg["das_dump"] = dict(custody=custody, conns=conns, meshes=meshes, row_meshes=row_meshes, row_subnet=row_subnet,
                           supernodes={i + 1 for i in das["supernodes"]} - {1},
                           reconstructors={i + 1 for i in das["reconstructors"]}, passes=passes,
                           blocks=len(with_meshes), withheld=withheld)
    # The supernodes setting is a percentage for the toy's own draw (not run here); sim.publish_block and the
    # node's row type read only whether it is set, so it carries the dumped supernodes' count: their rows exist.
    cfg["supernodes"] = len(cfg["das_dump"]["supernodes"])
    cfg["cgc"], cfg["blobs"] = das["cgc"], das["rows"]
    if das.get("row_subnets"):
        cfg["ROW_SUBNETS"] = das["row_subnets"]
    if shape:
        cfg["REPAIR_FLOOR"], cfg["SOURCE_FLOOR"] = shape["repair_floor"], shape["source_floor"]
    return notes


def graph_line(cfg, shape):
    """The dumped graph as graphLine() and the toy's floors read it: custodians per column, custodian
    links per (node, custodied column) and the proposer's per column (min / median / max, the proposer
    aside), and how far the graph falls short of the floors custody_topology would build at the dump's
    values: (node, column) pairs below the custody floor (min(floor, custodians - 1) other custodians as
    links), columns below the proposer's fanout, row members below the subnet floor, and row members'
    (node, column) pairs below the repair floor."""
    dd = cfg["das_dump"]
    conns, custody, rs = dd["conns"], dd["custody"], dd["row_subnet"]
    floor, sfloor, rfloor = (shape or {}).get("floor", 0), cfg["SOURCE_FLOOR"], cfg["REPAIR_FLOOR"]
    cust = {c: {v for v in conns if v != 1 and c in custody[v]} for c in range(NUMBER_OF_COLUMNS)}
    links = [sum(1 for u in conns[v] if u in cust[c]) for v in conns if v != 1 for c in sorted(custody[v])]
    src = [sum(1 for u in conns[1] if u in cust[c]) for c in range(NUMBER_OF_COLUMNS)]
    mmm = lambda xs: f"{min(xs)} / {statistics.median(xs):g} / {max(xs)}" if xs else "-"
    short_c = sum(1 for v in conns if v != 1 for c in custody[v]
                  if sum(1 for u in conns[v] if u in cust[c]) < min(floor, len(cust[c]) - 1))
    short_s = sum(1 for c in range(NUMBER_OF_COLUMNS) if src[c] < min(sfloor, len(cust[c])))
    members = {}
    for v, s in rs.items():
        if s is not None:
            members.setdefault(s, set()).add(v)
    short_r = sum(1 for s, ms in members.items() for v in ms
                  if len(conns[v] & ms) < min(floor, len(ms) - 1))
    short_p = sum(1 for v, s in rs.items() if s is not None and rfloor for c in range(NUMBER_OF_COLUMNS)
                  if c not in custody[v] and len(conns[v] & cust[c]) < min(rfloor, len(cust[c])))
    passes = ", ".join(f"{k} {v}" for k, v in sorted(dd["passes"].items())) or "none"
    return (f"dump graph: {sum(len(s) for s in conns.values()) // 2} links ({passes} added by the harness); "
            f"custodians per column {mmm([len(cust[c]) for c in range(NUMBER_OF_COLUMNS)])}; custodian links per "
            f"node-column {mmm(links)}; the proposer's per column {mmm(src)}; short of the toy's floors "
            f"(floor {floor}, source {sfloor}, repair {rfloor}): {short_c} node-columns, {short_s} columns at the "
            f"proposer, {short_r} row members of {sum(len(ms) for ms in members.values())}, {short_p} repair node-columns; "
            f"{len(dd['supernodes'])} supernodes besides the proposer, {len(dd['reconstructors'])} reconstructors")


# ---- the counters and invariants


class Recorder:
    def __init__(self, sim, horizon=3.0):
        self.sim, self.horizon = sim, horizon
        self.lines = {}                 # msg -> [line, ...]
        self.window = sim.cfg["IWANT_WINDOW"]
        self.faulty = sim.cfg.get("faulty", set())
        self.silent = sim.cfg.get("silent", False)
        self.msg, self.pub = 0, None
        self._reset()
        self._install()

    def _reset(self):
        self.c = defaultdict(Counter)           # node id -> counter by KEYS and invariants
        self.pushes = defaultdict(Counter)      # node id -> (group, index) -> eager pushes
        self.asked = defaultdict(dict)          # node id -> (group, index) -> time of the last ask
        self.peak = Counter()                   # node id -> most slots in flight
        self.have_ever = {}                     # (node, peer, group) -> every HAVE bit the peer sent it
        self.times = {"ihave": [], "push": [], "answer": []}   # the source's sends, s after publish
        self.asks_sent = Counter()              # (node, group, index) -> asks it has written for the chunk
        self.ask_first = self.ask_retry = 0     # asks written to the source: their asker's first, or later

    # -- hooks

    def _install(self):
        sim = self.sim
        spec_transmit, spec_deliver = sim.transmit, sim._deliver
        rec = self

        def transmit(node, p, e):
            rec.sent(node, p, e)
            return spec_transmit(node, p, e)

        def _deliver(src, dst, e, data, ctrl):  # the name the digest records stays the same
            rec.received(src, dst, e)
            return spec_deliver(src, dst, e, data, ctrl)
        sim.transmit, sim._deliver = transmit, _deliver
        for nd in sim.nodes.values():
            self._wrap_node(nd)

    def _wrap_node(self, nd):
        ns, rec, nid = nd.ns, self, nd.id
        spec_filter, spec_acquire, spec_track = ns["filter_entry"], ns["acquire_slot"], ns["track_in_flight"]
        spec_may_ask, group_index = ns["may_ask"], ns["group_index"]

        def may_ask(a, p):
            ok = spec_may_ask(a, p)
            if ok:
                gi = group_index(a)
                if gi is not None:
                    key, now = (gi.group, gi.index), rec.sim.now
                    last = rec.asked[nid].get(key)
                    mine = ns["mine"].get(gi.group)
                    held = mine is not None and mine.has(gi.index)
                    if last is not None and now - last < rec.window - 0.001 and not held:
                        rec.c[nid]["inv_overlap"] += 1
                    rec.asked[nid][key] = now
            return ok

        def filter_entry(p, entry):
            f = entry.chunk
            if f is not None and ns["CANCEL"]:
                ph = ns["peer_has"].get(p)
                he = ph.get(f.group) if ph is not None else None
                if he is not None and he.has(f.index):
                    rec.c[nid]["cancel"] += 1
            return spec_filter(p, entry)

        def acquire_slot(p):
            got = spec_acquire(p)
            rec.peak[nid] = max(rec.peak[nid], ns["in_flight"])
            return got

        def track_in_flight(p, f):
            out = spec_track(p, f)
            rec.peak[nid] = max(rec.peak[nid], ns["in_flight"])
            return out
        ns["filter_entry"], ns["acquire_slot"], ns["track_in_flight"] = filter_entry, acquire_slot, track_in_flight
        ns["may_ask"] = may_ask

    def sent(self, node, p, e):
        c, nid, ns = self.c[node.id], node.id, node.ns
        f = e.chunk
        if nid == self.pub:
            t = self.sim.now - self.t0
            if f is not None:
                self.times["answer" if e.solicited else "push"].append(t)
            if e.control is not None and any(m.kind == "ihave" and m.ids for m in e.control.items):
                self.times["ihave"].append(t)
        if f is not None:
            if e.solicited:
                c["answer"] += 1
            else:
                c["push"] += 1
                self.pushes[nid][(f.group, f.index)] += 1
            if p in ns["mesh"] and (self.have_ever.get((nid, p, f.group), 0) >> f.index) & 1:
                c["inv_late"] += 1
                ph = ns["peer_has"].get(p)
                he = ph.get(f.group) if ph is not None else None
                if he is not None and he.has(f.index):
                    c["late_live"] += 1
            if nid in self.faulty and (self.silent or e.solicited):
                c["inv_fault"] += 1
        if e.control is None:
            return
        for m in e.control.items:
            if m.kind == "ihave":
                c["ihave_ids"] += len(m.ids)
                c["have_ihave"] += sum(1 for x in m.ids if isinstance(x, Wm.HaveBitmap))
            elif m.kind == "idontwant":
                c["idontwant_ids"] += len(m.ids)
                c["have_idontwant"] += sum(1 for x in m.ids if isinstance(x, Wm.HaveBitmap))
            elif m.kind == "iwant":
                c["iwant_ids"] += len(m.ids)
                c["ask"] += sum(1 for x in m.ids if isinstance(x, Wm.WantIndex))
                for x in m.ids:
                    if not isinstance(x, Wm.WantIndex):
                        continue
                    k = (nid, x.group, x.index)
                    if p == self.pub:
                        if self.asks_sent[k]:
                            self.ask_retry += 1
                        else:
                            self.ask_first += 1
                    self.asks_sent[k] += 1

    def received(self, src, dst, e):
        if e.control is not None:
            for m in e.control.items:
                if m.kind == "iwant" and m.ids:      # asks received, as the harness counts them on receipt
                    self.c[dst]["asks_in"] += len(m.ids)
                    if src in self.sim.nodes[dst].ns["mesh"]:
                        self.c[dst]["asks_in_mesh"] += len(m.ids)
                if m.kind == "idontwant":
                    for x in m.ids:
                        if isinstance(x, Wm.HaveBitmap):
                            k = (dst, src, x.group)
                            self.have_ever[k] = self.have_ever.get(k, 0) | x.bits.v
        f = e.chunk
        if f is None:
            return
        c = self.c[dst]
        c["rx"] += 1
        # A duplicate is a chunk the node had received before, or the publisher's own, as the
        # harness's seen cache counts it; not one it holds only since its decode (mine, card 10).
        got = self.sim.nodes[dst].ns["received"].get(f.group)
        if (got is not None and got.has(f.index)) or dst == self.pub:
            c["dup"] += 1

    # -- per message

    def publish(self, m, pub):
        """Called at message m's publish: start its counts. run.py reads them at the horizon
        (take), between two of its own run() calls, so the recorder schedules no event."""
        self.msg, self.pub, self.t0 = m, pub, self.sim.now
        self._reset()

    def take(self, m):
        ms = round(self.horizon * 1000)
        pops = [("honest", [i for i in self.sim.nodes if i != self.pub and i not in self.faulty])]
        if self.faulty:
            pops.append(("attacker", sorted(self.faulty - {self.pub})))
        out = [f"xcheck@{ms}ms [{name} {len(s)}]: {self.line(s)}" for name, s in pops if s]
        out.append(f"xcheck@{ms}ms [publisher]: {self.line([self.pub])}")
        self.lines[m] = out

    def line(self, nodes):
        tot = Counter()
        budget_nodes = over = push_max = win_nodes = peak = w_hi = 0
        for i in nodes:
            tot.update(self.c[i])
            ns = self.sim.nodes[i].ns
            if i != self.pub:
                deg = ns["R_NODE"]
                top = max(self.pushes[i].values(), default=0)
                push_max = max(push_max, top)
                k = sum(1 for v in self.pushes[i].values() if v > deg)
                if k:
                    budget_nodes += 1
                    over += k
            w = ns["W"]
            if w != float("inf"):
                w_hi = max(w_hi, int(w))
                peak = max(peak, self.peak[i])
                if self.peak[i] > w:
                    win_nodes += 1
        f = [f"{k}={tot[k]}" for k in KEYS]
        f += ["|", f"inv_budget={budget_nodes}", f"inv_budget_chunks={over}", f"inv_window={win_nodes}",
              f"inv_overlap={tot['inv_overlap']}", f"inv_late={tot['inv_late']}", f"inv_fault={tot['inv_fault']}",
              "|", f"push_max={push_max}", f"peak={peak}", f"w={w_hi}", "late_same=0",
              f"late_live={tot['late_live']}",
              f"ask_window_ms={round(self.window * 1000)}",
              "|", f"asks_in={tot['asks_in']}", f"asks_in_mesh={tot['asks_in_mesh']}"]
        if list(nodes) == [self.pub]:               # the source's timeline, ms after publish
            for name in ("ihave", "push", "answer"):
                ts = sorted(self.times[name])
                ms = [round(t * 1000) for t in ts] or [-1]
                f += [f"{name}_n={len(ts)}", f"{name}_first_ms={ms[0]}", f"{name}_p50_ms={ms[len(ms) // 2]}",
                      f"{name}_last_ms={ms[-1]}"]
            f += [f"asks_first={self.ask_first}", f"asks_retry={self.ask_retry}"]
        return " ".join(f)

    def degree_mismatches(self, degree):
        """Nodes whose push degree in the toy differs from the harness's, as (toy id, toy, harness)."""
        if not degree:
            return []
        return [(i, self.sim.nodes[i].ns["R_NODE"], degree[i - 1]) for i in sorted(self.sim.nodes)
                if self.sim.nodes[i].ns["R_NODE"] != degree[i - 1] and i != 1]
