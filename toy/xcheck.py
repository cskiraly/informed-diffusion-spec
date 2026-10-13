"""The cross-check with the research harness: its network, loaded, and its per-rule counters and
invariants, counted here the same way.

load(path) reads the harness's SEGMENT_XC_DUMP file: gzip'd JSON lines, first the network (each
node's uplink and downlink, each connection with its one-way delay, each node's push degree, the
faulty set and its knobs), then one line per message with its publisher and every node's mesh at
the publish. apply(cfg, topo) makes those the toy's classes, latencies, connections, meshes,
publishers and faulty set, so that what still differs from the harness is the link model and the
rules, not the topology. Toy ids are the harness's node indices plus one.

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
from collections import Counter, defaultdict

import wire as Wm

KEYS = ("push", "answer", "cancel", "ask", "iwant_ids", "have_ihave", "ihave_ids",
        "have_idontwant", "idontwant_ids", "dup", "rx")


# ---- the harness's network


def load(path):
    """The dump as a dict: net (the first record) and meshes {msg: (pub, [[peer, ...] by node])}."""
    opener = gzip.open if str(path).endswith(".gz") else open
    net, meshes = None, {}
    with opener(path, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r["kind"] == "net":
                net = r
            elif r["kind"] == "mesh":
                meshes[r["msg"]] = (r["pub"], r["mesh"])
    if net is None:
        raise ValueError(f"{path}: no network record")
    return {"net": net, "meshes": meshes}


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
