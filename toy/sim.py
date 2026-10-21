"""The toy's world: an event loop, links, a topology, a source and the measurements.

Network model (deliberately simple; README.md says what it leaves out):
- each node has an uplink and a downlink rate; each ordered pair a fixed one-way latency;
- a node's writer hands entries to its connection's transport at once, as a QUIC stream accepts
  writes; the window (card 14) is what holds chunks back, as in the pseudocode;
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

import scenario
import wire as Wm
from bits import Bits, popcount
from invariants import Checker
from node import Node, parse_id
from scenario import fail_select as scenario_fail_select

CELL_BYTES = 2048 + 48                     # a cell and its KZG proof (das-core); the column setting's chunk
COLUMNS = 128                              # NUMBER_OF_COLUMNS


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
    __slots__ = ("up", "down", "conns", "rr", "busy", "down_busy", "active", "heap", "V", "vt", "version", "backlog")

    def __init__(self, up, down):
        self.up, self.down = up, down          # bits per second
        self.conns = {}                        # peer -> deque of (entry, data, ctrl) not yet started
        self.rr = deque()                      # round robin: peers with entries waiting, in turn
        self.busy = False
        self.down_busy = 0.0                   # when the downlink will have carried what reached it
        self.active = {}                       # sharing: peer -> (entry, data, ctrl, F) in service
        self.heap = []                         # sharing: (F, seq, peer) of the entries in service
        self.V, self.vt, self.version = 0.0, 0.0, 0
        self.backlog = {}                      # peer -> bytes handed to the link and not yet sent


class Sim:
    def __init__(self, cfg):
        self.cfg = cfg
        self.rng = random.Random(cfg["seed"])
        self.now = 0.0
        self.q, self.seq = [], 0
        self.blocks = {}
        self.canonical = {}                    # group -> {index: chunk}, the source's chunks
        self.msgs = []                         # (publish time, [groups]) per message: one group for a
                                               #   payload, COLUMNS groups for a block of columns
        self.pubs = []                         # the publisher per message: node 1 unless the harness's dump names one
        self.gtype = {}                        # group -> object type id, for groups whose id names one ("column", "row")
        self.gcol = {}                         # column group -> column index
        self.ghdr = {}                         # column or row group -> its header
        self.gsub = {}                         # row group -> its row subnet
        self.grow = {}                         # (block root, blob row) -> row group
        self.gcolgroup = {}                    # (block root, column) -> column group
        self.custody = {}                      # node -> set of columns (the custody setting)
        self.events = 0
        self.recorder = None                   # xcheck.Recorder, when run.py installs one
        # --send-buffer: the bytes a connection's transport accepts ahead of the link; a writer waits
        # while its backlog is at it, as a stream write blocks. None: writes complete at once.
        self.send_buffer = cfg.get("send_buffer")
        if self.send_buffer is not None and cfg.get("uplink", "ps") != "ps":
            raise ValueError("--send-buffer needs the processor-sharing uplink")
        self.digest = hashlib.sha256() if cfg.get("digest") else None
        self.inv = Checker(self) if cfg.get("invariants") else None
        self._ids = {}
        self._custody_cache = {}
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

    def custody_of_id(self, node_id, count):
        """The custody setting's derived interest: a node id's columns (scenario.custody_columns)."""
        key = (node_id, count)
        s = self._custody_cache.get(key)
        if s is None:
            s = self._custody_cache[key] = (set(range(COLUMNS)) if count >= COLUMNS
                                            else scenario.custody_columns(node_id, count))
        return s

    def row_subnet_of_id(self, node_id):
        """The row setting's derived interest: a node id's designated row subnet (EIP-8371)."""
        s = self._custody_cache.get(("row", node_id))
        if s is None:
            s = self._custody_cache[("row", node_id)] = scenario.row_subnet(node_id, self.cfg["ROW_SUBNETS"])
        return s

    def rebuild_row(self, chunks_g, h):
        """recover_cells_and_kzg_proofs for an honest row: every cell of blob row h.row, as the source built them."""
        return {col: self.canonical[self.gcolgroup[(h.block, col)]][h.row] for col in range(COLUMNS)}

    # ---- the network

    def _build(self):
        c, n = self.cfg, self.cfg["nodes"]
        classes = c["classes"](n, self.rng)                    # node id -> {"up", "down"}
        if c.get("fault"):                                     # wh<pct>, sil<pct> (the harness's set), claim<pct>, hoard<pct>
            kind, pct = re.fullmatch(r"(wh|sil|claim|hoardm|hoard)(\d+)", c["fault"]).groups()   # or hoardm<pct> (v2)
            c["faulty"] = scenario_fail_select(c["seed"], n, int(pct))
            c["silent"] = kind == "sil"
            c["claim"] = kind == "claim"
            c["hoard"] = kind in ("hoard", "hoardm")
            c["hoard_members"] = kind == "hoardm"              # repairs only the row's members' custody cells
        das = c.get("doc") == "v2" and c.get("setting") in ("custody", "rows")
        if das and c.get("samplers"):
            k = max(1, (c["samplers"] * (n - 1) + 50) // 100)         # samplers: interest without duty (§4.10)
            c["sampler_ids"] = set(self.rng.sample(range(2, n + 1), k))
        self.custody_count = {}
        if das and c.get("setting") == "rows" and c.get("reconstructors"):
            pool = [i for i in range(2, n + 1) if i not in c.get("sampler_ids", ())]
            k = max(1, (c["reconstructors"] * (n - 1) + 50) // 100)   # row reconstructors: 64 columns (EIP-8371)
            c["reconstructor_ids"] = set(self.rng.sample(pool, k))
            for i in c["reconstructor_ids"]:
                self.custody_count[i] = 64
        if das and c.get("supernodes"):                        # supernodes: every column (PeerDAS), drawn apart so that
            pool = [i for i in range(2, n + 1)                 #   the other draws are those of a run without them
                    if i not in c.get("sampler_ids", ()) and i not in c.get("reconstructor_ids", ())]
            k = max(1, (c["supernodes"] * (n - 1) + 50) // 100)
            c["supernode_ids"] = set(random.Random(c["seed"] * 7919 + 1201).sample(pool, k))
            for i in c["supernode_ids"]:
                self.custody_count[i] = COLUMNS
                if c.get("supernode_link", "dc") == "dc":      # a node that takes every column runs on a datacenter link
                    classes[i] = dict(scenario.DC)
        if das:
            self.custody_count[1] = COLUMNS
        self.nodes = {i: Node(self, i, classes[i], c) for i in range(1, n + 1)}
        self.links = {i: Link(classes[i]["up"], classes[i]["down"]) for i in self.nodes}
        self.lat = c["latency"](n, self.rng)                   # (i, j) -> one-way seconds
        setting = c.get("setting") if c.get("doc") == "v2" else None
        if setting in ("custody", "rows"):                     # PeerDAS custody: columns as the object type; rows on top
            for i, nd in self.nodes.items():                   # node 1, the proposer, holds every column
                self.custody[i] = (set() if nd.sampler else set(range(COLUMNS)) if i == 1
                                   else scenario.custody_columns(self.peer_id(i), self.custody_count.get(i, c["cgc"])))
            row_subnets = None
            if setting == "rows":                              # EIP-8371: one designated row subnet per node
                row_subnets = {i: (None if i == 1 or nd.sampler else scenario.row_subnet(self.peer_id(i), c["ROW_SUBNETS"]))
                               for i, nd in self.nodes.items()}
            conns, meshes, row_meshes, self.repair_links = scenario.custody_topology(
                n, c["degree"], c["D"], self.rng, self.custody, floor=c["F_LO"], source_floor=c["SOURCE_FLOOR"],
                row_subnets=row_subnets, repair_floor=c.get("REPAIR_FLOOR", 0),
                repair_rng=random.Random(c["seed"] * 7919 + 4243))      # its own draws: the graph stays the same
            for i, nd in self.nodes.items():
                nd.peers = sorted(conns[i])
                nd.custody = self.custody[i]
                if row_subnets:
                    nd.row_subnet = row_subnets[i]
                if i == 1:                                     # the proposer's fanout: its custodian links, per column
                    rel = {col: {q for q in nd.peers if col in self.custody[q]} for col in range(COLUMNS)}
                else:
                    rel = {col: meshes[col][i] for col in nd.custody}
                row_rel = None
                if row_subnets and nd.row_subnet is not None:
                    row_rel = {nd.row_subnet: row_meshes[nd.row_subnet][i]}
                nd.set_column_relations(rel, row_rel)
        else:
            conns, mesh = c["topology"](n, c["degree"], c["D"], self.rng)
            colour_meshes = None
            if setting == "c":                                 # variant C: a mesh per index on the same connections
                n_colours = 2 * math.ceil(c["payload"] / (16 * 1024))      # N at this payload (protocol.md §1)
                colour_meshes = [scenario.gossip_mesh(conns, c["D"], 6, 12, self.rng) for _ in range(n_colours)]
            for i, nd in self.nodes.items():
                nd.peers = sorted(conns[i])
                nd.set_mesh(mesh[i], None if colour_meshes is None else {k: m[i] for k, m in enumerate(colour_meshes)})
        phase = c.get("heartbeat_phase", 0.0)
        for nd in self.nodes.values():
            off = self.rng.uniform(0, c["HEARTBEAT"]) if c.get("random_phase") else phase
            self.after(nd, off, self._heartbeat, nd)

    def transmit(self, node, p, e):
        data, ctrl = Wm.entry_wire(e)
        node.tx_data += data
        node.tx_ctrl += ctrl
        if self.inv is not None:
            self.inv.transmit(node, p, e)
        ln = self.links[node.id]
        ln.backlog[p] = ln.backlog.get(p, 0) + data + ctrl
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
            ln.backlog[p] -= data + ctrl
            self.after(None, self.lat(node.id, p), self._arrive, node.id, p, e, data, ctrl)
            if ln.conns[p]:
                self._ps_start(ln, p)
            if self.send_buffer is not None and p in node.writer_blocked and ln.backlog[p] < self.send_buffer:
                node.writer_blocked.discard(p)  # the transport has room again: the write completed
                node.kick(p)
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
        if self.inv is not None:
            self.inv.deliver(src, dst, e)
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
        nd.expire_offers(self.now)                         # §8.1's 30 s, checked at each heartbeat: an
                                                           #   offer can outlive it by up to one
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
        if self.custody:
            return self.publish_block(m)
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
        self.msgs.append((self.now, [g]))
        self.pubs.append(pub)
        ns["publish"](self.blocks[root], d, shards)
        self.canonical[g] = dict(ns["chunks"][g])

    def publish_block(self, m):
        """A block of `blobs` blobs as COLUMNS column groups (protocol-v2.md §1.1's table): each
        group's header is a descriptor-shaped object whose count is the blob count, so that v0.3's
        N and K read it (K = N: no code within a column), its root names the block and the column,
        and its id is group_id(header), computable by everyone from the block root."""
        src = self.nodes[1]
        ns = src.ns
        B, c = self.cfg["blobs"], self.cfg
        root = hashlib.sha256(b"block" + m.to_bytes(4, "little")).digest()
        self.blocks[root] = Block(m, root, None)
        groups = []
        for col in range(COLUMNS):
            hdr = Wm.Container(version=3, hash_id=0, encoding=0, count=B, segment_size=CELL_BYTES,
                               total_length=B * CELL_BYTES, column=col, block=root,
                               root=hashlib.sha256(b"column" + root + col.to_bytes(2, "little")).digest())
            g = ns["group_id"](hdr)
            self.gtype[g], self.gcol[g], self.ghdr[g] = "column", col, hdr
            self.gcolgroup[(root, col)] = g
            groups.append(g)
        subnets = c.get("setting") == "rows"
        if subnets or c.get("supernodes"):                     # the row groups: N = 128 cells, K = 64 (EIP-8371); under
            if subnets:                                        #   custody alone the rows a supernode rebuilds, without subnets
                perm = self.rng.sample(range(c["ROW_SUBNETS"]), B) if B <= c["ROW_SUBNETS"] else [b % c["ROW_SUBNETS"] for b in range(B)]
            else:
                perm = [None] * B
            for b in range(B):
                hdr = Wm.Container(version=4, hash_id=0, encoding=0, count=COLUMNS, segment_size=CELL_BYTES,
                                   total_length=(COLUMNS // 2) * CELL_BYTES, row=b, subnet=perm[b], block=root,
                                   root=hashlib.sha256(b"row" + root + b.to_bytes(2, "little")).digest())
                g = ns["group_id"](hdr)
                self.gtype[g], self.ghdr[g] = "row", hdr
                if subnets:
                    self.gsub[g] = perm[b]
                self.grow[(root, b)] = g
                groups.append(g)
        self.msgs.append((self.now, groups))
        self.pubs.append(1)
        for nd in self.nodes.values():                         # the block root is known everywhere now (the toy's gate)
            for g in groups:
                nd.ns["known_at"][g] = self.now
        withheld = set(range(COLUMNS - c.get("withhold", 0), COLUMNS))
        for g in groups:                                       # one publish per column, as sidecars go
            if self.gtype[g] != "column":
                continue
            hdr = self.ghdr[g]
            shards = [Wm.Shard(index=b, proof=[], data=Wm.Blob(CELL_BYTES, ("cell", m, hdr.column, b)))
                      for b in range(B)]
            if hdr.column in withheld:                         # the proposer keeps these: only reconstruction can supply them
                self.canonical[g] = {s.index: ns["Chunk"](slot=m, beacon_block_root=root, group=g, descriptor=hdr,
                                                          index=s.index, proof=s.proof, data=s.data) for s in shards}
                continue
            ns["publish"](self.blocks[root], hdr, shards)
            self.canonical[g] = dict(ns["chunks"][g])
        for i, nd in self.nodes.items():                       # the samplers declare at block arrival (§4.10)
            if not nd.sampler:
                continue
            cells = self.rng.sample([(col, b) for col in range(COLUMNS) for b in range(B)], self.cfg["samples"])
            per_group = {}
            for col, b in cells:
                per_group.setdefault(groups[col], Bits()).set(b)
            for g, bits in per_group.items():
                nd.samples[g] = bits
                self.after(nd, 0.0, nd.ns["sample"], g, bits.copy())

    def unit(self, i):
        """The bytes node i must receive for its interest in one message: the compressed payload,
        or the chunks of its custody columns."""
        if not self.custody:
            return self.cfg["COMPRESSED"]
        if not self.msgs:
            return len(self.custody[i]) * self.cfg["blobs"] * CELL_BYTES
        _, groups = self.msgs[0]
        nd, total = self.nodes[i], 0
        for g in groups:
            if not nd.interested(g):
                continue
            if self.gtype.get(g) == "row":                     # a row member needs K = 64 of the row's 128 cells
                hdr = self.ghdr[g]
                total += (COLUMNS // 2) * Wm.chunk_wire(self.canonical[self.gcolgroup[(hdr.block, 0)]][hdr.row])
                continue
            total += sum(Wm.chunk_wire(f) for k, f in self.canonical[g].items() if nd.wants(g, k))
        return total

    def completion(self, i, groups):
        """When node i completed its interest in a message: the latest of its groups, inf if any is missing;
        None if it has no interest in the message."""
        nd, t = self.nodes[i], None
        for g in groups:
            if not nd.interested(g):
                continue
            t = max(t or 0.0, nd.completed.get(g, math.inf))
        return t

    def incomplete(self):
        """(node, group) pairs whose interest never completed."""
        out = []
        for (_, groups), pub in zip(self.msgs, self.pubs):
            for i, nd in self.nodes.items():
                if i == pub:
                    continue
                out += [(i, g) for g in groups if nd.interested(g) and g not in nd.completed]
        return out

    def rebuild(self, chunks_g, d):
        """decode_and_reencode for an honest group: the source's chunks, as a real decode would give."""
        if self.cfg.get("rebuilt") == "none":
            return dict(chunks_g)               # no chunk is rebuilt, as in the harness's tier-4 cells
        for f in chunks_g.values():
            return dict(self.canonical[f.group])
        return None

    # ---- the measurements

    def results(self):
        """Per message: the receivers' completion (custodians, or every node on a payload), and the
        samplers' apart, since a sample is a different interest."""
        out = []
        for k, ((t0, groups), pub) in enumerate(zip(self.msgs, self.pubs)):
            cols = [g for g in groups if self.gtype.get(g) != "row"]
            rws = [g for g in groups if self.gtype.get(g) == "row"]
            ts, ss, rs = [], [], []
            for i, nd in self.nodes.items():
                if i == pub:
                    continue
                t = self.completion(i, cols)                   # the payload, or the node's custody columns
                if t is not None:
                    (ss if nd.sampler else ts).append(t - t0)
                if rws:
                    t = self.completion(i, rws)                # a row member's row, at K
                    if t is not None:
                        rs.append(t - t0)
            ts.sort()
            ss.sort()
            rs.sort()
            r = {"msg": k + 1, "p50": pct(ts, 50), "p99": pct(ts, 99),
                 "max": ts[-1] if ts else math.nan, "missing": sum(1 for t in ts if t == math.inf),
                 "nodes": len(ts)}
            if rs:
                r["rows"] = {"p50": pct(rs, 50), "p99": pct(rs, 99), "max": rs[-1],
                             "missing": sum(1 for t in rs if t == math.inf), "nodes": len(rs)}
            if ss:
                r["samplers"] = {"p50": pct(ss, 50), "p99": pct(ss, 99), "max": ss[-1],
                                 "missing": sum(1 for t in ss if t == math.inf), "nodes": len(ss),
                                 "unreachable": sum(popcount(nd.unreachable.get(g, Bits())) for nd in self.nodes.values()
                                                    if nd.sampler for g in groups)}
            out.append(r)
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
