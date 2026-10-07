"""The toy's world: an event loop, links, a topology, a source and the measurements.

Network model (deliberately simple; README.md says what it leaves out):
- each node has an uplink and a downlink rate; each ordered pair a fixed one-way latency;
- a node's writer hands entries to its connection's transport at once, as a QUIC stream accepts
  writes; the window (card 14) is what holds frames back, as in the pseudocode;
- the uplink shares itself equally among the connections with something to send (processor
  sharing, the fluid limit of the harness's per-flow FQ-CoDel), each connection sending its entries
  in order; --uplink rr sends whole entries in turn instead;
- the receiver's downlink is a fluid FIFO: an entry finishes when its last byte has arrived and the
  downlink has carried everything that reached it first.
Processing takes no time, as in the harness's virtual clock.
"""
import hashlib
import heapq
import math
import random
from collections import deque

import re

import wire as Wm
from node import Node, parse_id
from scenario import fail_select as scenario_fail_select


class Block:
    __slots__ = ("slot", "root", "body")

    def __init__(self, slot, root, group):
        self.slot, self.root = slot, root
        bid = type("Bid", (), {})()
        bid.execution_payload_segment_group_id = group
        signed = type("SignedBid", (), {})()
        signed.message = bid
        self.body = type("Body", (), {})()
        self.body.signed_execution_payload_bid = signed


class Link:
    """One node's access link: its uplink scheduler and its downlink's fluid FIFO.

    The uplink is processor sharing by default: every connection with something to send gets an
    equal share, which is the fluid limit of the harness's FQ-CoDel (deficit round robin over
    per-peer flows, one packet at a time). V is the virtual clock of that sharing, in bits sent per
    busy connection; an entry finishes when V reaches its virtual finish F. The round-robin model
    sends whole entries in turn instead (--uplink rr)."""
    __slots__ = ("up", "down", "conns", "rr", "busy", "down_busy", "active", "heap", "V", "vt", "version")

    def __init__(self, up, down):
        self.up, self.down = up, down          # bits per second
        self.conns = {}                        # peer -> deque of (entry, data, ctrl) not yet started
        self.rr = deque()                      # round robin: peers with entries waiting, in turn
        self.busy = False
        self.down_busy = 0.0                   # when the downlink will have carried what reached it
        self.active = {}                       # sharing: peer -> (entry, data, ctrl, F) in service
        self.heap = []                         # sharing: (F, seq, peer) of the entries in service
        self.V, self.vt, self.version = 0.0, 0.0, 0


class Sim:
    def __init__(self, cfg):
        self.cfg = cfg
        self.rng = random.Random(cfg["seed"])
        self.now = 0.0
        self.q, self.seq = [], 0
        self.blocks = {}
        self.canonical = {}                    # group -> {index: frame}, the source's frames
        self.groups = []                       # (group, publish time, publisher) in order
        self.events = 0
        self.recorder = None                   # xcheck.Recorder, when run.py installs one
        self.digest = hashlib.sha256() if cfg.get("digest") else None
        self._ids = {}
        self._build()

    # ---- the clock

    def after(self, node, delay, fn, *args):
        self.seq += 1
        heapq.heappush(self.q, (self.now + delay, self.seq, node, fn, args))

    def run(self, until):
        q, h = self.q, self.digest
        while q and q[0][0] <= until:
            t, _, node, fn, args = heapq.heappop(q)
            self.now = t
            if node is not None:
                node.ns["now"] = t
            if h is not None:                   # every event: time, node, kind, int and bytes args
                h.update(repr((t, node.id if node is not None else 0, getattr(fn, "__name__", "?"),
                               [a for a in args if type(a) in (int, bytes)])).encode())
            fn(*args)
            self.events += 1
        self.now = until

    # ---- identities

    def peer_id(self, p):
        b = self._ids.get(p)
        if b is None:
            b = self._ids[p] = hashlib.sha256(b"peer" + p.to_bytes(4, "little")).digest()
        return b

    def tiebreak(self, mid, p):
        h = hashlib.sha256(mid + self.peer_id(p)).digest()
        return int.from_bytes(h[:8], "little")

    # ---- the network

    def _build(self):
        c, n = self.cfg, self.cfg["nodes"]
        classes = c["classes"](n, self.rng)                    # node id -> {"up", "down"}
        if c.get("fault"):                                     # wh<pct> or sil<pct>, the harness's set
            kind, pct = re.fullmatch(r"(wh|sil)(\d+)", c["fault"]).groups()
            c["faulty"] = scenario_fail_select(c["seed"], n, int(pct))
            c["silent"] = kind == "sil"
        self.nodes = {i: Node(self, i, classes[i], c) for i in range(1, n + 1)}
        self.links = {i: Link(classes[i]["up"], classes[i]["down"]) for i in self.nodes}
        self.lat = c["latency"](n, self.rng)                   # (i, j) -> one-way seconds
        conns, mesh = c["topology"](n, c["degree"], c["D"], self.rng)
        for i, nd in self.nodes.items():
            nd.peers = sorted(conns[i])
            nd.ns["mesh"] = set(mesh[i])
        phase = c.get("heartbeat_phase", 0.0)
        for nd in self.nodes.values():
            off = self.rng.uniform(0, c["HEARTBEAT"]) if c.get("random_phase") else phase
            self.after(nd, off, self._heartbeat, nd)

    def transmit(self, node, p, e):
        data, ctrl = Wm.entry_wire(e)
        node.tx_data += data
        node.tx_ctrl += ctrl
        ln = self.links[node.id]
        dq = ln.conns.get(p)
        if dq is None:
            dq = ln.conns[p] = deque()
        if self.cfg.get("uplink", "ps") == "rr":
            if not dq:
                ln.rr.append(p)
            dq.append((e, data, ctrl))
            if not ln.busy:
                self._rr_serve(node)
            return
        self._ps_advance(ln)
        dq.append((e, data, ctrl))
        if p not in ln.active:
            self._ps_start(ln, p)
            self._ps_reschedule(node, ln)

    # -- processor sharing

    def _ps_advance(self, ln):
        n = len(ln.active)
        if n:
            ln.V += (self.now - ln.vt) * ln.up / n
        ln.vt = self.now

    def _ps_start(self, ln, p):
        e, data, ctrl = ln.conns[p].popleft()
        F = ln.V + (data + ctrl) * 8
        ln.active[p] = (e, data, ctrl, F)
        self.seq += 1
        heapq.heappush(ln.heap, (F, self.seq, p))

    def _ps_reschedule(self, node, ln):
        ln.version += 1
        if ln.heap:
            wait = (ln.heap[0][0] - ln.V) * len(ln.active) / ln.up
            self.after(node, max(0.0, wait), self._ps_complete, node, ln, ln.version)

    def _ps_complete(self, node, ln, version):
        if version != ln.version:
            return                              # the set of busy connections changed since
        self._ps_advance(ln)
        # This event was scheduled for the earliest finish: it completes, whatever rounding left V
        # a hair short of it (V reaches 1e8 bits and more, so an absolute tolerance would not do).
        ln.V = max(ln.V, ln.heap[0][0])
        tol = 1e-9 * ln.V + 1e-6
        while ln.heap and ln.heap[0][0] <= ln.V + tol:
            _, _, p = heapq.heappop(ln.heap)
            e, data, ctrl, _ = ln.active.pop(p)
            self.after(None, self.lat(node.id, p), self._arrive, node.id, p, e, data, ctrl)
            if ln.conns[p]:
                self._ps_start(ln, p)
        self._ps_reschedule(node, ln)

    # -- round robin, one whole entry at a time

    def _rr_serve(self, node):
        ln = self.links[node.id]
        if not ln.rr:
            ln.busy = False
            return
        p = ln.rr.popleft()
        dq = ln.conns[p]
        e, data, ctrl = dq.popleft()
        if dq:
            ln.rr.append(p)
        finish = self.now + (data + ctrl) * 8 / ln.up
        ln.busy = True
        self.after(node, finish - self.now, self._rr_serve, node)
        self.after(None, finish - self.now + self.lat(node.id, p), self._arrive, node.id, p, e, data, ctrl)

    def _arrive(self, src, dst, e, data, ctrl):
        """The last byte has reached dst's downlink: a fluid FIFO that carried what came first."""
        rx = self.links[dst]
        s = (data + ctrl) * 8 / rx.down
        rx.down_busy = max(rx.down_busy, self.now - s) + s
        self.after(self.nodes[dst], rx.down_busy - self.now, self._deliver, src, dst, e, data, ctrl)

    def _deliver(self, src, dst, e, data, ctrl):
        nd = self.nodes[dst]
        nd.rx_data += data
        nd.rx_ctrl += ctrl
        nd.ns["on_rpc"](src, Wm.RPC(e))

    # ---- the heartbeat (stock duties the pseudocode assumes, then §6.4)

    def _heartbeat(self, nd):
        ns = nd.ns
        ns["gossip_history"].shift()
        for p, groups in ns["peer_has"].items():
            for g in [g for g, e in groups.items() if _tick(e)]:
                del groups[g]
                for i, hs in ns["holders"].get(g, {}).items():
                    hs.discard(p)
        for p, groups in ns["pushed"].items():
            for g in [g for g, e in groups.items() if _tick(e)]:
                del groups[g]
        had_pace = bool(ns["pace_queue"])
        ns["on_heartbeat"]()
        if ns["PACED"] and ns["pace_queue"] and not had_pace:
            self.after(nd, ns["HEARTBEAT"] / 16, self._pace_tick, nd)
        self.after(nd, ns["HEARTBEAT"], self._heartbeat, nd)

    def _pace_tick(self, nd):
        ns = nd.ns
        ns["on_pace_tick"]()
        if ns["pace_queue"]:
            self.after(nd, ns["HEARTBEAT"] / 16, self._pace_tick, nd)

    # ---- the source and its payloads

    def publish(self, m):
        pub = self.cfg.get("publishers", {}).get(m, 1)     # node 1 unless the harness's dump names one
        meshes = self.cfg.get("meshes", {}).get(m)
        if meshes is not None:                             # the harness's meshes at this publish
            for i, nd in self.nodes.items():
                nd.ns["mesh"] = set(meshes[i - 1])
        if self.recorder is not None:
            self.recorder.publish(m, pub)
        src = self.nodes[pub]
        ns = src.ns
        body = Wm.Blob(self.cfg["payload"], ("payload", m))
        d, shards = ns["build_group"](body)
        g = ns["group_id"](d)
        root = hashlib.sha256(b"block" + m.to_bytes(4, "little")).digest()
        self.blocks[root] = Block(m, root, g)
        self.groups.append((g, self.now, pub))
        ns["publish"](self.blocks[root], d, shards)
        self.canonical[g] = dict(ns["frames"][g])

    def rebuild(self, frames_g, d):
        """decode_and_reencode for an honest group: the source's frames, as a real decode would give."""
        if self.cfg.get("rebuilt") == "none":
            return dict(frames_g)               # no frame is rebuilt, as in the harness's tier-4 cells
        for f in frames_g.values():
            return dict(self.canonical[f.group])
        return None

    # ---- the measurements

    def results(self):
        c, out = self.cfg, []
        W = c["COMPRESSED"]
        for k, (g, t0, pub) in enumerate(self.groups):
            K = len(self.canonical[g]) // 2
            ts = sorted(nd.completed.get(g, math.inf) - t0 for i, nd in self.nodes.items() if i != pub)
            out.append({"msg": k + 1, "p50": pct(ts, 50), "p99": pct(ts, 99),
                        "max": ts[-1], "missing": sum(1 for t in ts if t == math.inf)})
        return out


def _tick(e):
    e.ttl -= 1
    return e.ttl <= 0


def pct(xs, q):
    """Nearest-rank percentile of a sorted list."""
    if not xs:
        return math.nan
    k = max(0, math.ceil(q / 100 * len(xs)) - 1)
    return xs[k]
