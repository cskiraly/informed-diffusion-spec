"""One node: the pseudocode's functions, executed in a namespace of their own, and the helpers the
pseudocode names but does not write out (§8.1, "Helpers not written out").

Each node gets a fresh module namespace. The spec's code (extract.py) is compiled once and executed
in every namespace, so each node's functions read that node's state through their globals, exactly
as the pseudocode reads `mesh`, `peer_has` or `now`. What lives here is only what the document
leaves to the environment; a behaviour that matters and is not in the document is a gap in the
document, and is listed in README.md.
"""
import math
import random
from collections import deque

import bits as B
import wire as Wm
from bits import AutoMap, Bits, DefaultMap, HaveEntry, LazyMap, PushEntry, all_bits, bitmap, popcount
from extract import generate

SPEC_SRC = generate()
SPEC = compile(SPEC_SRC, "protocol.md (extracted)", "exec")

COLLECTING, DECODING, COMPLETE, INVALID = "COLLECTING", "DECODING", "COMPLETE", "INVALID"
ACCEPT, REJECT, DEFER = "ACCEPT", "REJECT", "DEFER"


class _Wait:
    """next_to_send's answer while the writer waits in line for a slot (§7.2)."""

    def __repr__(self):
        return "WAIT"


WAIT = _Wait()


class PeerQueue:
    """queue[p]: the two lanes of one peer's bounded queue (§7)."""
    __slots__ = ("urgent", "normal")

    def __init__(self):
        self.urgent, self.normal = [], []

    def has_chunks(self):
        for e in self.normal:
            if e.chunk is not None:
                return True
        return False


class GossipHistory:
    """The stock message cache: ids by heartbeat window; gossip from the newest three (§6.4)."""

    def __init__(self, length=6, gossip=3):
        self.windows = deque([[] for _ in range(length)], maxlen=length)
        self.gossip = gossip

    def put(self, f):
        self.windows[0].append(f.mid)

    def shift(self):
        self.windows.appendleft([])

    def gossip_ids(self):
        out = []
        for w in list(self.windows)[: self.gossip]:
            out.extend(w)
        return out

    def remove_group(self, g):
        for w in self.windows:
            w[:] = [m for m in w if m[:32] != g]


class GroupIndex:
    __slots__ = ("group", "index")

    def __init__(self, group, index):
        self.group, self.index = group, index


def parse_id(mid):
    """A structured id's group and index (§2)."""
    return mid[:32], int.from_bytes(mid[32:36], "little")


class Node:
    def __init__(self, sim, nid, cls, cfg):
        self.sim, self.id, self.cls, self.cfg = sim, nid, cls, cfg
        self.peers = []                 # connected peers on the topic
        self.writer_kicked = set()      # peers whose writer has a run queued
        self.writer_blocked = set()     # peers whose writer waits for the transport (--send-buffer)
        self.rx_data = self.rx_ctrl = 0
        self.tx_data = self.tx_ctrl = 0
        self.penalties = 0
        self.dropped = 0                # chunks lost at admission (loss_data)
        self.completed = {}             # group -> time of the K-th distinct chunk
        self.delivered = {}             # group -> time of delivery (after the check)
        ns = self._namespace()
        exec(SPEC, ns)
        self._override(ns)
        self.ns = ns

    # ---- the namespace the spec's code runs in

    def _namespace(self):
        c, node = self.cfg, self
        up = self.cls["up"]
        ns = {
            "__name__": f"node{self.id}",
            # language and sets
            "ceil": math.ceil, "floor": math.floor, "inf": math.inf, "deque": deque,
            "popcount": popcount, "all_bits": all_bits, "bitmap": bitmap, "WAIT": WAIT,
            # wire
            "sha256": Wm.sha256, "serialize": Wm.serialize, "uint32_le": Wm.uint32_le,
            "content_id": Wm.content_id, "is_have_bitmap": Wm.is_have_bitmap,
            "Container": Wm.Container, "uint8": Wm.uint8, "uint32": Wm.uint32, "uint64": Wm.uint64,
            "Bytes32": Wm.Bytes32, "Root": Wm.Root, "Slot": Wm.Slot, "Result": Wm.Result,
            "List": Wm.List, "ByteList": Wm.ByteList, "Optional": Wm.Optional, "Tuple": Wm.Tuple,
            "IHAVE": Wm.IHAVE, "IWANT": Wm.IWANT, "IDONTWANT": Wm.IDONTWANT, "PRUNE": Wm.PRUNE,
            "Entry": Wm.Entry,
            # results and states
            "ACCEPT": ACCEPT, "REJECT": REJECT, "DEFER": DEFER,
            "COLLECTING": COLLECTING, "DECODING": DECODING, "COMPLETE": COMPLETE, "INVALID": INVALID,
            # constants (§8.3) and card switches
            "R": c["R"], "R_FAST": c["R_FAST"], "FAST_UPLINK": c["FAST_UPLINK"],
            "R_NODE": c["R_FAST"] if (c["card17"] and up >= c["FAST_UPLINK"]) else c["R"],
            "UPLINK": up, "STRIPE_UPLINK": c["STRIPE_UPLINK"] if c["card13"] else math.inf,
            "uplink_bytes_per_s": up * c["window_scale"] / 8,
            "IWANT_WINDOW": c["IWANT_WINDOW"], "RETRY_SLACK": c["RETRY_SLACK"],
            "PROMISE": c["PROMISE"], "PARK_TTL": c["PARK_TTL"],
            "GUARD_GRACE": c["GUARD_GRACE"], "FAN_IN": c["FAN_IN"],
            "RTT_REF": c["RTT_REF"], "TARGET": c["TARGET"], "CHUNK_BYTES": c["CHUNK_BYTES"],
            "WINDOW_TIMEOUT": c["WINDOW_TIMEOUT"], "HEARTBEAT": c["HEARTBEAT"],
            "D_LAZY": c["D_LAZY"], "GOSSIP_FACTOR": c["GOSSIP_FACTOR"],
            "GOSSIP_RETRANSMISSION": c["GOSSIP_RETRANSMISSION"],
            "HAVE_TTL": c["HAVE_TTL"], "PUSH_TTL": c["PUSH_TTL"],
            "CANCEL": c["card8"], "RAREST": c["card9"], "PROJECT": c["card12"], "PACED": c["card15"],
            "DESCRIPTOR_IN_CHUNK": True,
            # state (§8.1); missing entries read as empty
            "desc": {}, "state": DefaultMap(None), "chunks": AutoMap(dict), "known_id": AutoMap(dict),
            "received": AutoMap(Bits), "mine": AutoMap(Bits), "stop_pull": DefaultMap(False),
            "origin": {},
            "peer_has": AutoMap(lambda: LazyMap(HaveEntry)),
            "pushed": AutoMap(lambda: LazyMap(PushEntry)),
            "holders": AutoMap(lambda: AutoMap(set)), "sent_to": AutoMap(lambda: AutoMap(Bits)),
            "queue": AutoMap(PeerQueue), "slot_held": DefaultMap(False),
            "unwanted": AutoMap(set), "serve_count": AutoMap(lambda: AutoMap(int)),
            "asked_at": {}, "tried": AutoMap(dict), "offers": AutoMap(list), "promises": {},
            "park": AutoMap(dict), "gossip_history": GossipHistory(), "pace_queue": [],
            "pending": AutoMap(list), "pending_ids": set(),
            "mesh": set(), "now": 0.0,
        }
        self._seen = set()
        self._by_index = {}             # (group, index) -> set of ask keys, for closing promises

        # ---- chunks and groups (§8.1)
        def open_group(g, f):
            ns["desc"][g] = f.descriptor
            ns["state"][g] = COLLECTING

        def store(g, i, f):
            ns["chunks"][g][i] = f
            ns["known_id"][g][i] = ns["message_id"](f)

        def accepted(mid):
            g, i = parse_id(mid)
            fr = ns["chunks"].get(g)
            return fr is not None and i in fr and ns["state"][g] != INVALID

        def expired(g):
            return False                # groups outlive these runs (GROUP_TTL > the run)

        def group_index(a):
            if isinstance(a, Wm.WantIndex):
                return a
            if isinstance(a, bytes) and len(a) >= 36:
                return GroupIndex(*parse_id(a))
            return None

        def group(a):
            return a.group if isinstance(a, Wm.WantIndex) else a[:32]

        def held(a):
            gi = group_index(a)
            return gi is not None and ns["mine"][gi.group].has(gi.index)

        def resolve(a):
            gi = group_index(a)
            if gi is None or ns["state"][gi.group] == INVALID:
                return None
            if gi.index not in ns["chunks"][gi.group]:
                return None
            return ns["known_id"][gi.group][gi.index]

        def chunk_of(mid):
            g, i = parse_id(mid)
            return ns["chunks"][g][i]

        def decode_and_reencode(chunks_g, d):
            return node.sim.rebuild(chunks_g, d)

        def payload_of(rebuilt):
            return None

        def deliver(g, payload):
            node.delivered[g] = node.sim.now

        def close_promises(g, i):
            for a in self._by_index.pop((g, i), ()):
                for p in list(ns["tried"].get(a, {})):
                    ns["promises"].pop((a, p), None)
                ns["offers"].pop(a, None)
                ns["asked_at"].pop(a, None)
                ns["tried"].pop(a, None)

        def close_promises_of_group(g):
            for (gg, i) in [k for k in self._by_index if k[0] == g]:
                for a in self._by_index[(gg, i)]:
                    for p in list(ns["tried"].get(a, {})):
                        ns["promises"].pop((a, p), None)

        def discard_queued(g):
            for q in ns["queue"].values():
                q.normal = [e for e in q.normal if not (e.chunk is not None and e.chunk.group == g)]

        def discard_paced(g):
            pass

        # ---- peers and messages (§8.1, §8.2)
        def seen(mid):
            return mid in self._seen

        def mark_seen(mid):
            self._seen.add(mid)

        def valid_have(h):
            d = ns["desc"].get(h.group)
            return d is None or h.bits.v >> d.count == 0

        def add_offer(a, p):
            lst = ns["offers"][a]
            if p not in lst and len(lst) < 16:
                lst.append(p)
                gi = group_index(a)
                if gi is not None:
                    self._by_index.setdefault((gi.group, gi.index), set()).add(a)

        def reserve(p, f):
            return False

        def release(p, f):
            pass

        def penalise(p):
            node.penalties += 1

        def handle_graft_prune(p, rpc):
            return []

        def enqueue(p, x, urgent=False):
            e = x if isinstance(x, Wm.Entry) else (
                Wm.Entry(control=x) if isinstance(x, Wm.Control) else Wm.Entry(chunk=x))
            if e.is_empty():
                return                  # an empty response or bitmap is not sent (§2, §5.2)
            q = ns["queue"][p]
            (q.urgent if urgent else q.normal).append(e)
            node.kick(p)

        def topic_peers():
            return node.peers

        connected_topic_peers = topic_peers

        def connected(q):
            return True

        def gossip_eligible(q):
            return True

        def installed_block(slot, root):
            return node.sim.blocks.get(root)

        def block_root(block):
            return block.root

        def group_bits(ids):
            out = {}
            for mid in ids:
                g, i = parse_id(mid)
                out.setdefault(g, Bits()).set(i)
            return list(out.items())

        def tiebreak(f, p):
            return node.sim.tiebreak(f.mid, p)

        def peer_id_bytes(p):
            return node.sim.peer_id(p)

        # ---- the writer (§7.2)
        def wake(p):
            node.kick(p)

        # ---- codec, crypto and timing
        def snappy_block_encode(body):
            return Wm.Blob(round(len(body) / c["COMPRESSION"]), ("snappy", body.tag))

        def pad_each(segs, size):
            return segs

        def rs_parity(segs, k):
            size = len(segs[0])
            return [Wm.Blob(size, ("parity", segs[0].tag, j)) for j in range(k)]

        def merkle_root(leaves):
            return Wm.sha256(repr([lf.tag for lf in leaves]).encode())

        def merkle_proof(leaves, i):
            width = 1 << max(0, (len(leaves) - 1).bit_length())
            return [b"\0" * 32] * max(1, width.bit_length() - 1)

        def verify_merkle_proof(root, data, index, count, proof):
            return True                 # honest chunks only; level 1 is the cost of a hash, not modelled

        rng = random.Random((c["seed"] << 20) ^ self.id)       # each node's own draws, seeded

        def shuffled(xs):
            xs = list(xs)
            rng.shuffle(xs)
            return xs

        def sample_without_replacement(xs, k):
            return rng.sample(list(xs), k)

        def after(delay, fn, *args):
            node.sim.after(node, delay, fn, *args)

        def start(fn, g):
            node.sim.after(node, c["CHECK_TIME"], fn, g)

        ns.update({k: v for k, v in locals().items() if callable(v) and not k.startswith("_")
                   and k not in ("c", "node", "up", "ns", "rng")})
        ns["_rng"] = rng
        return ns

    def _override(self, ns):
        """Runtime stand-ins for the bitmap and the ask (their wire sizes, and asks hashed by value
        as table keys), and the window off (card 14)."""
        ns["HaveBitmap"] = Wm.HaveBitmap
        ns["WantIndex"] = Wm.WantIndex
        if not self.cfg["card14"]:
            ns["W"] = math.inf
        spec_message_id = ns["message_id"]

        def message_id(f):              # computed once per chunk object
            m = getattr(f, "mid", None)
            if m is None:
                m = f.mid = spec_message_id(f)
            return m
        ns["message_id"] = message_id
        spec_claim_group, node, c = ns["claim_group"], self, self.cfg

        def claim_group(g):             # the measurement point: completion at the K-th chunk
            node.completed[g] = node.sim.now
            spec_claim_group(g)
        ns["claim_group"] = claim_group
        if c.get("rebuilt"):
            self._rebuilt(ns)
        self._faults(ns)

    def _faults(self, ns):
        """The harness's adversaries on the nodes it picks (scenario.fail_select), and admission loss."""
        c = self.cfg
        if self.id in c.get("faulty", ()):
            ns["on_iwant"] = lambda p, iw: []           # withholds: announces, never answers
            if c.get("silent"):
                put = ns["gossip_history"].put

                def forward(f, from_peer):             # forwards nothing; heartbeat gossip still announces
                    put(f)
                ns["forward"] = forward
                if c.get("rebuilt", "push") == "push":  # nor pushes what it rebuilt, as the
                    ns["push_rebuilt"] = lambda g, new: None    # harness's silent nodes do
        if c.get("loss_data"):
            pct, spec_enqueue, node = c["loss_data"], ns["enqueue"], self

            def enqueue(p, x, urgent=False):           # every node drops pct % of chunks at admission
                f = x.chunk if isinstance(x, Wm.Entry) else (x if not isinstance(x, Wm.Control) else None)
                if f is not None:
                    h = Wm.sha256(b"loss" + node.id.to_bytes(4, "little") + p.to_bytes(4, "little") + ns["message_id"](f))
                    if int.from_bytes(h[:8], "little") % 100 < pct:
                        node.dropped += 1
                        if isinstance(x, Wm.Entry) and x.control is not None:
                            return spec_enqueue(p, Wm.Entry(control=x.control), urgent)
                        return
                return spec_enqueue(p, x, urgent)
            ns["enqueue"] = enqueue

    def _rebuilt(self, ns):
        """What a decoded node does with the chunks it rebuilt. The document pushes them (§4.6,
        push_rebuilt); the variants replace that: none (no chunk is rebuilt, as in the harness's
        tier-4 cells; sim.rebuild), hold, announce, and push capped at rb_max chunks per peer."""
        c, mode = self.cfg, self.cfg["rebuilt"]
        if c.get("rb_jitter"):
            def start(fn, g):                          # the hand-over waits up to rb_jitter more
                self.sim.after(self, c["CHECK_TIME"] + ns["_rng"].uniform(0, c["rb_jitter"]), fn, g)
            ns["start"] = start
        if mode in ("none", "hold"):
            ns["push_rebuilt"] = lambda g, new: None   # kept and servable, but nobody asks for them
        elif mode == "announce":
            def push_rebuilt(g, new):                  # offered as received chunks are (§5.2, §6.4)
                for i in new:
                    ns["gossip_history"].put(ns["chunks"][g][i])
                for q in ns["shuffled"](ns["mesh"]):
                    ns["announce"](q, g, set(new))
            ns["push_rebuilt"] = push_rebuilt
        elif c.get("rb_max"):
            def push_rebuilt(g, new):                  # the document's push, at most rb_max per peer
                k = ns["K"](ns["desc"][g])
                for q in ns["shuffled"](ns["mesh"]):
                    known = ns["peer_has"][q][g].bits | ns["pushed"][q][g]
                    short = k - popcount(known)
                    if short <= 0:
                        continue
                    pool = ns["shuffled"]([i for i in new if not known.has(i)])
                    for i in pool[:min(short, c["rb_max"])]:
                        ns["enqueue"](q, ns["chunks"][g][i], urgent=False)
                        ns["note_push"](q, g, i)
            ns["push_rebuilt"] = push_rebuilt

    # ---- the writer: one per peer (§7.2)

    def kick(self, p):
        if p not in self.writer_kicked:
            self.writer_kicked.add(p)
            self.sim.after(self, 0.0, self._write, p)

    def _write(self, p):
        self.writer_kicked.discard(p)
        nts = self.ns["next_to_send"]
        buf, ln = self.sim.send_buffer, self.sim.links[self.id]
        while True:
            if buf is not None and ln.backlog.get(p, 0) >= buf:
                self.writer_blocked.add(p)      # the transport takes no more for now: the write
                return                          #   has not completed (§7.2), the link wakes us
            e = nts(p)
            if e is None or e is WAIT:          # nothing to send, or in line for a slot (§7.2)
                return
            self.sim.transmit(self, p, e)
