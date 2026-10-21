"""One node: the pseudocode's functions, executed in a namespace of their own, and the helpers the
pseudocode names but does not write out (§8.1, "Helpers not written out").

Each node gets a fresh module namespace. The spec's code (extract.py) is compiled once and executed
in every namespace, so each node's functions read that node's state through their globals, exactly
as the pseudocode reads `mesh`, `peer_has` or `now`. What lives here is only what the document
leaves to the environment; a behaviour that matters and is not in the document is a gap in the
document, and is listed in README.md.
"""
import math
from collections import Counter
import random
from collections import deque

import bits as B
import wire as Wm
from bits import AutoMap, Bits, DefaultMap, HaveEntry, LazyMap, OfferList, PushEntry, all_bits, bitmap, popcount
from extract import DOC, generate

SPEC_SRC = generate()
SPEC = compile(SPEC_SRC, "protocol.md (extracted)", "exec")
DOC2 = DOC.parent / "protocol-v2.md"
_SPEC2 = None


def spec2():
    """protocol-v2.md's blocks, compiled once; they run after protocol.md's in the same namespace
    (--doc v2), redefining what version 2 changes and keeping what it says carries over."""
    global _SPEC2
    if _SPEC2 is None:
        _SPEC2 = compile(generate(DOC2), "protocol-v2.md (extracted)", "exec")
    return _SPEC2

COLLECTING, DECODING, COMPLETE, INVALID = "COLLECTING", "DECODING", "COMPLETE", "INVALID"
OFFER_TTL = 30.0                        # §8.1: offers live 30 s
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
        self.merged = [0, 0]            # --merge-holdings: holdings of a group we publish, [merged, sent]
        self.refused = Counter()        # asks this node left unanswered: (object type, reason) -> count
        self.broken = []                # promises broken to this node: (when, asked at, peer, group, index)
        self.dropped = 0                # chunks lost at admission (loss_data)
        self.completed = {}             # group -> time of the K-th distinct chunk
        self.delivered = {}             # group -> time of delivery (after the check)
        self.custody = None             # the custody setting: this node's columns
        self.sampler = self.id in cfg.get("sampler_ids", ())    # interest DECLARED, duty NONE (§4.10)
        self.samples = {}               # a sampler's declared interest: group -> Bits, per block
        self.unreachable = {}           # samples no link could serve: group -> Bits
        self.supernode = self.id in cfg.get("supernode_ids", ())          # every column; rebuilds any row still short (phase 2)
        self.reconstructor = self.supernode or self.id in cfg.get("reconstructor_ids", ())   # rows: 64 columns or more, decodes its row at K
        self.row_subnet = None          # rows: the node's designated row subnet (EIP-8371)
        self.liar = cfg.get("claim") and self.id in cfg.get("faulty", ())   # rows: claims a row it did not rebuild
        self.hoarder = cfg.get("hoard") and self.id in cfg.get("faulty", ())   # v2: rebuilds and claims, passes the probe, repairs nothing
        self.hoard_served = self.hoard_refused = 0      # a hoarder's rebuilt chunks: asks answered (probes), asks refused
        self.member_checks = 0                          # (R5) the member check: verified claims not taken, custody cells missing
        self.repair_verdicts = Counter()                # (R5, option) the repair sample's verdicts
        self._retry_armed = set()       # asks whose delayed first try is scheduled (deferred offers, [D8])
        ns = self._namespace()
        exec(SPEC, ns)
        self.v2 = cfg.get("doc") == "v2"
        if self.v2:
            self._v2_names(ns)
            exec(spec2(), ns)
        self._override(ns)
        if self.v2:
            self._v2(ns)
            if "column" in self._types and (cfg.get("repair_push", "push") == "offer" or self._keepers_to is not None):
                self._repair_variants(ns)
            if cfg.get("keeper_claims", "defer") == "ignore" and self.supernode:
                spec_note_claim = ns["note_claim"]

                def note_claim(p, g):                   # exploration: a supernode's second phase cancels on completion
                    if self.row_subnet is not None and self.sim.gsub.get(g) == self.row_subnet:   # it observes, not
                        spec_note_claim(p, g)           #   on a claim; its own subnet's row as any member's
                ns["note_claim"] = note_claim
            self._member_check(ns, cfg.get("member_check", "on") == "on")
        self.ns = ns

    def _member_check(self, ns, on):
        """(R5) the member check, counted: each verified claim a member did not take because a cell of the row
        in its custody columns was missing. --member-check off (ablation): the claim ends the duty whether or
        not those cells came, as in the document before the check."""
        spec_owed_missing, node = ns["owed_missing"], self

        def owed_missing(g):
            if not on:
                return False
            missing = spec_owed_missing(g)
            node.member_checks += missing
            return missing
        ns["owed_missing"] = owed_missing
        spec_repair_verdict = ns["repair_verdict"]

        def repair_verdict(g):
            v = spec_repair_verdict(g)
            node.repair_verdicts[(v, ns["rsample_step"][g])] += 1
            return v
        ns["repair_verdict"] = repair_verdict

    def _repair_variants(self, ns):
        """Explorations of whom rebuilt cells go to and how. --repair-push offer: the peers push_rebuilt
        picks get them as offers instead of pushes, as a row's do (EAGER off), so each receiver pulls one
        copy. --repair-keepers offer: peers that keep every row are left out of the pushes and offered
        the cells in a second pass of the document's push_rebuilt."""
        cprm, spec_push_rebuilt = self._types["column"].params, ns["push_rebuilt"]
        rtype = self._types.get("row")
        offer_all, keepers_to = self.cfg.get("repair_push", "push") == "offer", self._keepers_to

        def push_rebuilt(g, new):
            eager, to = cprm.EAGER, cprm.REPAIR_TO
            try:
                if offer_all:
                    cprm.EAGER = False
                spec_push_rebuilt(g, new)
                if keepers_to is not None:               # the second pass: the keepers, offered; the row's own peers not again
                    cprm.EAGER, cprm.REPAIR_TO = False, keepers_to
                    rto = rtype.params.REPAIR_TO if rtype is not None else None
                    if rtype is not None:
                        rtype.params.REPAIR_TO = lambda g2: []
                    try:
                        spec_push_rebuilt(g, new)
                    finally:
                        if rtype is not None:
                            rtype.params.REPAIR_TO = rto
            finally:
                cprm.EAGER, cprm.REPAIR_TO = eager, to
        ns["push_rebuilt"] = push_rebuilt

    def set_mesh(self, mesh, colour_meshes=None):
        """The topology's mesh for this node; under v2 it is also the push relation both ways. With
        colour_meshes ({colour: this node's mesh for it}, the variant C setting) the relation
        carries one colour per mesh and `mesh` becomes their union."""
        self.ns["mesh"] = set(mesh)
        if self.v2:
            self._v2_relations(mesh, colour_meshes)

    # ---- interest, as the world sees it (the invariants checker's ground truth)

    def interest_bits(self, g):
        """What this node is to receive of group g: every index (Bits(-1)), or none."""
        if self.custody is None:
            return Bits(-1)                                      # the payload settings: interest ALL
        if self.sim.gtype.get(g) == "row":
            return self.interest_bits_row(g)                     # a row group: the node's subnet, or none
        col = self.sim.gcol.get(g)
        if col is None:
            return Bits(-1)                                      # a payload group
        if self.sampler:
            return self.samples.get(g, Bits(0))                  # what it declared (§4.10)
        return Bits(-1) if col in self.custody else Bits(0)

    def interest_bits_row(self, g):
        sub = self.sim.gsub.get(g)
        return Bits(-1) if sub is not None and sub == self.row_subnet and not self.sampler else Bits(0)

    def own_interest_bits(self, g):
        """The node's own interest, its state's: what it declared, and for a supernode every row, which its
        columns bring it whole and no link is asked for (protocol-v2.md §4.6, the second phase)."""
        if self.supernode and self.sim.gtype.get(g) == "row":
            return Bits(-1)
        return self.interest_bits(g)

    def wants(self, g, i):
        return self.interest_bits(g).has(i)

    def interested(self, g):
        return not self.interest_bits(g).empty()

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
            "REPAIRED": "REPAIRED", "ASKED": "ASKED", "NOT_REPAIRED": "NOT_REPAIRED",
            # constants (§8.3) and card switches
            "R": c["R"], "R_FAST": c["R_FAST"], "FAST_UPLINK": c["FAST_UPLINK"],
            "R_NODE": c["R_FAST"] if (c["card17"] and up >= c["FAST_UPLINK"]) else c["R"],
            "UPLINK": up, "STRIPE_UPLINK": c["STRIPE_UPLINK"] if c["card13"] else math.inf,
            "uplink_bytes_per_s": up * c["window_scale"] / 8,
            "IWANT_WINDOW": c["IWANT_WINDOW"], "RETRY_SLACK": c["RETRY_SLACK"], "ASK_UPLINK": c.get("ASK_UPLINK", 50e6),
            "MERGE_HOLDINGS": c.get("MERGE_HOLDINGS", False),
            "PROMISE": c["PROMISE"], "PARK_TTL": c["PARK_TTL"],
            "GUARD_GRACE": c["GUARD_GRACE"], "FAN_IN": c["FAN_IN"],
            "RTT_REF": c["RTT_REF"], "TARGET": c["TARGET"], "CHUNK_BYTES": c["CHUNK_BYTES"],
            "WINDOW_TIMEOUT": c["WINDOW_TIMEOUT"], "HEARTBEAT": c["HEARTBEAT"],
            "D_LAZY": c["D_LAZY"], "GOSSIP_FACTOR": c["GOSSIP_FACTOR"],
            "GOSSIP_RETRANSMISSION": c["GOSSIP_RETRANSMISSION"],
            "HAVE_TTL": c["HAVE_TTL"], "PUSH_TTL": c["PUSH_TTL"],
            "CANCEL": c["card8"], "RAREST": c["card9"], "PROJECT": c["card12"], "PACED": c["card15"],
            "ANSWERS_FIRST": c.get("answers_first", "off") == "on",
            "DESCRIPTOR_IN_CHUNK": True,
            # state (§8.1); missing entries read as empty
            "desc": DefaultMap(None), "state": DefaultMap(None), "chunks": AutoMap(dict), "known_id": AutoMap(dict),
            "received": AutoMap(Bits), "mine": AutoMap(Bits), "stop_pull": DefaultMap(False),
            "origin": {},
            "peer_has": AutoMap(lambda: LazyMap(HaveEntry)),
            "pushed": AutoMap(lambda: LazyMap(PushEntry)),
            "holders": AutoMap(lambda: AutoMap(set)), "sent_to": AutoMap(lambda: AutoMap(Bits)),
            "queue": AutoMap(PeerQueue), "slot_held": DefaultMap(False),
            "unwanted": AutoMap(set), "serve_count": AutoMap(lambda: AutoMap(int)),
            "asked_at": {}, "tried": AutoMap(dict), "offers": LazyMap(OfferList), "promises": {},
            "offered": AutoMap(lambda: AutoMap(Bits)), "asked_parked": AutoMap(set),
            "last_resort_armed": set(),
            "owed": AutoMap(lambda: AutoMap(Bits)), "owed_answers": AutoMap(lambda: AutoMap(Bits)),
            "park": AutoMap(dict), "gossip_history": GossipHistory(), "pace_queue": [],
            "pending": AutoMap(list), "pending_ids": set(),
            "mesh": set(), "now": 0.0,
        }
        self._seen = set()
        self._by_index = {}             # (group, index) -> set of ask keys, for closing promises
        self._listed = {}               # announcer -> how many ordered offer lists it is in (§8.2)
        self._offer_at = {}             # (announcer, group) -> its last offer, for the 30 s of §8.1

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

        def index(a):
            return group_index(a).index

        def authenticable(g):           # every block installs at its publish, at every node
            return any(b.body.signed_execution_payload_bid.message.execution_payload_segment_group_id == g
                       for b in node.sim.blocks.values())

        def bid_group(root):
            return node.sim.blocks[root].body.signed_execution_payload_bid.message.execution_payload_segment_group_id

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

        def close_promises(g, i):       # the chunk arrived: its promises, offers and tries go (§8.1)
            for a in self._by_index.pop((g, i), ()):
                for p in list(ns["tried"].get(a, {})):
                    ns["promises"].pop((a, p), None)
                for p in ns["offers"].pop(a, ()):
                    self._listed[p] -= 1
                ns["asked_at"].pop(a, None)
                ns["tried"].pop(a, None)
            ns["asked_parked"].pop((g, i), None)         # B′'s count is per chunk (§6.1)
            for q, groups in ns["offered"].items():
                if g in groups:
                    groups[g].clear(i)

        def close_promises_of_group(g):
            for (gg, i) in [k for k in self._by_index if k[0] == g]:
                for a in self._by_index[(gg, i)]:
                    for p in list(ns["tried"].get(a, {})):
                        ns["promises"].pop((a, p), None)

        def discard_queued(g):
            for q in ns["queue"].values():
                q.normal = [e for e in q.normal if not (e.chunk is not None and e.chunk.group == g)]
            for owed in (ns["owed"], ns["owed_answers"]):
                for groups in owed.values():
                    groups.pop(g, None)

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

        def admitted(p, f):
            return True                 # no group limits here (MAX_PENDING_GROUPS)

        def listed(p):
            return self._listed.get(p, 0)

        def reserve(p, f):
            return False

        def release(p, f):
            pass

        def penalise(p):
            node.penalties += 1

        def handle_graft_prune(p, rpc):
            return []

        def enqueue(p, x, urgent=False):    # the queues here have no limit: every entry is admitted
            e = x if isinstance(x, Wm.Entry) else (
                Wm.Entry(control=x) if isinstance(x, Wm.Control) else Wm.Entry(chunk=x))
            if e.is_empty():
                return True             # an empty response or bitmap is not sent (§2, §5.2)
            q = ns["queue"][p]
            (q.urgent if urgent else q.normal).append(e)
            if e.at is None:
                e.at, e.urgent = node.sim.now, urgent  # observed by invariants.py, read by nothing else
            node.kick(p)
            return True

        def has_room(p):
            return True

        def pop_owed_answer(p):
            groups = ns["owed_answers"][p]
            g = min(groups)
            i = min(groups[g])
            groups[g].clear(i)
            if not groups[g]:
                del groups[g]
            return ns["chunks"][g][i]

        def merge_waiting(p, h):                        # protocol-v2.md §4.2 [P4]: a holding of h's group to p
            node.merged[1] += 1                         #   still in our queue names its bits and h's, with h's
            for e in ns["queue"][p].urgent:             #   claims; with writes completing at once, only those
                items = e.control.items if e.chunk is None and e.control else ()   # queued before the writer ran
                if len(items) == 1 and items[0].kind == "idontwant" and len(items[0].ids) == 1:
                    hb = items[0].ids[0]
                    if isinstance(hb, Wm.HaveBitmap) and hb.group == h.group:
                        hb.bits = hb.bits | h.bits
                        hb.claim_all, hb.complete = h.claim_all, h.complete
                        node.merged[0] += 1
                        return True
            return False

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
            ns["W_BYTES"] = math.inf                # protocol-v2.md §4.11's window, off with the card too
        spec_message_id = ns["message_id"]

        def message_id(f):              # computed once per chunk object
            m = getattr(f, "mid", None)
            if m is None:
                m = f.mid = spec_message_id(f)
            return m
        ns["message_id"] = message_id
        spec_add_offer, spec_may_ask, group_index = ns["add_offer"], ns["may_ask"], ns["group_index"]
        offers, listed = ns["offers"], self._listed

        def index_ask(a):               # the ask keys of an index, in either form, for close_promises
            gi = group_index(a)
            if gi is not None:
                self._by_index.setdefault((gi.group, gi.index), set()).add(a)

        def add_offer(a, p):            # and the lists each announcer is in, for `listed`
            was = a in offers and p in offers[a]
            spec_add_offer(a, p)
            if not was and a in offers and p in offers[a]:
                listed[p] = listed.get(p, 0) + 1
                index_ask(a)            # a listed key; one only in `offered` has nothing to close
            self._offer_at[(p, ns["group"](a))] = ns["now"]

        def may_ask(a, p):              # an ask under a key no offer used (the ledger's) closes too
            ok = spec_may_ask(a, p)
            if ok:
                index_ask(a)
            return ok
        ns["add_offer"], ns["may_ask"] = add_offer, may_ask
        spec_claim_group, node, c = ns["claim_group"], self, self.cfg

        def claim_group(g):             # the measurement point: completion at the K-th chunk
            node.completed[g] = node.sim.now
            spec_claim_group(g)
        ns["claim_group"] = claim_group
        if c.get("rebuilt"):
            self._rebuilt(ns)
        self._faults(ns)
        if c.get("source_offers", "on") == "off":
            self._no_source_offers(ns)
        elif c.get("source_offers", "on") == "late":
            self._late_source_offers(ns)
        if c.get("answers_first", "off") not in ("off", "on") and "choose" in ns:
            self._writer_variants(ns, c["answers_first"])

    def _no_source_offers(self, ns):
        """To measure card 3 at the source: publish without offering the chunks to the relation
        peers that were not pushed them (v0.3 §5.1's last loop, protocol-v2.md §4.7's)."""
        spec_publish = ns["publish"]

        def publish(*a):
            spec_announce = ns["announce"]
            ns["announce"] = lambda p, g, bits: None
            try:
                spec_publish(*a)
            finally:
                ns["announce"] = spec_announce
        ns["publish"] = publish

    def _late_source_offers(self, ns):
        """To measure the order of a source's offers: the offers of every group published in one
        event are queued after all of those groups' pushes, as v0.3 §5.1 orders one group's."""
        spec_publish, node, pending = ns["publish"], self, []

        def flush():
            todo, pending[:] = list(pending), []
            for p, g, bits in todo:
                spec_announce(p, g, bits)

        def publish(*a):
            ns["announce"] = lambda p, g, bits: pending.append((p, g, bits))
            try:
                spec_publish(*a)
            finally:
                ns["announce"] = spec_announce
            node.sim.after(node, 0.0, flush)
        spec_announce = ns["announce"]
        ns["publish"] = publish

    def _writer_variants(self, ns, mode):
        """protocol-v2.md §4.12's choice of the next entry against the forms measured on 2026-10-07
        (toy/README.md). v03 is v0.3's order: rarest-first up to the first control-only entry, no
        source rule. oldest sends the oldest queued answer first, before a source's own chunks too;
        line does that and lets the answer's writer take room ahead of the window's line; others is
        oldest but keeps v0.3's order while the node's own chunks are queued; fresh sends first a
        chunk no peer of ours holds, then the oldest answer; late sends an answer first once it has
        waited ANSWER_DUE, never while own chunks are queued; othersans sends answers by rarity and
        keeps v0.3's order while own chunks are queued."""
        node = self
        node.answer_chosen = False
        own, v03 = ns["own_chunk"], (lambda q: ns["rarest"](q) if ns["RAREST"] else 0)

        def holders_of(e):
            return len(ns["holders"][e.chunk.group][e.chunk.index])

        def rarest_of(q, pred):         # the rarest entry satisfying pred, anywhere in the queue
            best, best_k = None, None
            for k, e in enumerate(q.normal):
                if e.chunk is not None and pred(e):
                    key = (holders_of(e), k)
                    if best is None or key < best:
                        best, best_k = key, k
            return best_k

        def choose(q):
            node.answer_chosen = False
            if q.normal[0].chunk is None or mode == "v03":
                return v03(q)
            own_queued = any(own(e) for e in q.normal)
            if mode == "late":
                if not own_queued:
                    due = node.sim.now - ns["ANSWER_DUE"]
                    k = next((k for k, e in enumerate(q.normal) if e.solicited and e.at is not None and e.at <= due), None)
                    if k is not None:
                        return k
                return v03(q)
            if mode == "othersans":
                k = None if own_queued else rarest_of(q, lambda e: e.solicited)
                return k if k is not None else v03(q)
            if mode == "fresh":
                k = v03(q)
                f = q.normal[k].chunk
                if not q.normal[k].solicited and not ns["holders"][f.group][f.index]:
                    return k                    # nobody around us holds it: it goes first
            if not (mode == "others" and own_queued):
                k = next((k for k, e in enumerate(q.normal) if e.solicited), None)
                if k is not None:
                    node.answer_chosen = True
                    return k
            return v03(q)

        ns["ANSWER_DUE"] = self.cfg.get("answer_due", 0.100)
        ns["choose"] = choose
        if mode != "line":
            return
        spec_acquire = ns["acquire_room"]

        def acquire_room(p, need):
            if not node.answer_chosen:
                return spec_acquire(p, need)
            w = ns["waiters"]
            if ns["in_flight"] + need <= ns["W_BYTES"] or ns["in_flight"] == 0:
                if p in w:
                    w.remove(p)
                ns["in_flight"] += need
                if w and ns["in_flight"] < ns["W_BYTES"]:
                    ns["wake"](w[0])
                return True
            if p in w:
                w.remove(p)
            w.appendleft(p)                 # an answer waits at the head of the line
            return False
        ns["acquire_room"] = acquire_room

    def _faults(self, ns):
        """The harness's adversaries on the nodes it picks (scenario.fail_select), and admission loss."""
        c = self.cfg
        if self.id in c.get("faulty", ()) and not c.get("hoard"):
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

            # every node drops pct % of chunks at admission, by a hash of the node, the peer and the
            # chunk: a chunk refused once to a peer is refused every time, so an answer owed for
            # it (§4.1) is refused again when the writer queues it, and dropped (has_room cannot
            # foresee a loss; at a real full queue it does guarantee the admission)
            def enqueue(p, x, urgent=False):
                f = x.chunk if isinstance(x, Wm.Entry) else (x if not isinstance(x, Wm.Control) else None)
                if f is not None:
                    h = Wm.sha256(b"loss" + node.id.to_bytes(4, "little") + p.to_bytes(4, "little") + ns["message_id"](f))
                    if int.from_bytes(h[:8], "little") % 100 < pct:
                        node.dropped += 1
                        if isinstance(x, Wm.Entry) and x.control is not None:
                            spec_enqueue(p, Wm.Entry(control=x.control), urgent)
                        return False    # the chunk was refused at admission
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

    def _peer_promise(self, ns):
        """--promise-mode peer: a promise per peer, max(PROMISE_FLOOR, srtt + 4 rttvar) over the times its
        answers took (RFC 6298's smoothing, 1/8 and 1/4; the first sample sets srtt and rttvar = srtt / 2);
        a peer that never answered keeps the floor. The ask window stays as §4.13 scales it."""
        floor = self.cfg["PROMISE"]                     # v0.3's 400 ms, before §4.13's scaling
        srtt, var, sender = {}, {}, [None]
        doc_fill, doc_filter_entry, doc_close = ns["fill"], ns["filter_entry"], ns["close_promises"]

        def fill(g, i, f, p):
            sender[0] = p
            try:
                return doc_fill(g, i, f, p)
            finally:
                sender[0] = None

        def close_promises(g, i):
            q = sender[0]
            if q is not None:
                for a in self._by_index.get((g, i), ()):
                    at = ns["promises"].get((a, q))
                    if at is not None:                  # q answered our ask: one sample of its answer time
                        x = ns["now"] - at
                        if q not in srtt:
                            srtt[q], var[q] = x, x / 2
                        else:
                            var[q] = 0.75 * var[q] + 0.25 * abs(srtt[q] - x)
                            srtt[q] = 0.875 * srtt[q] + 0.125 * x
            return doc_close(g, i)

        def filter_entry(p, entry):                     # v0.5 starts the promise at the write (§7.2)
            scaled = ns["PROMISE"]
            ns["PROMISE"] = max(floor, srtt[p] + 4 * var[p]) if p in srtt else floor
            try:
                return doc_filter_entry(p, entry)
            finally:
                ns["PROMISE"] = scaled
        ns.update(fill=fill, close_promises=close_promises, filter_entry=filter_entry)

    # ---- version 2 (protocol-v2.md): the tier 4 setting on v0.3's wire

    def _v2_names(self, ns):
        """Names protocol-v2.md's annotations use before its own classes define them."""
        for k in ("Callable", "Dict", "Set", "Header", "GroupId", "FamilyId", "NodeId", "Bitmap",
                  "TypeId", "TypeParams", "ObjectType", "InterestKind", "Duty", "Direction",
                  "AnnounceWidth", "Proof", "boolean", "uint16", "Ask", "PeerId", "GroupState",
                  "HaveEntry", "PushEntry", "Join", "Have", "Want", "Graft", "Prune", "ChunkMsg"):
            ns.setdefault(k, Wm.uint32)                 # an annotation-only type (wire._Ann)

    def _v2(self, ns):
        """What protocol-v2.md leaves to the environment, under the tier 4 setting (its §6.1): the
        payload object type and its parameters, the join tables, the relations behind the mesh,
        and the binding of the v2 messages onto v0.3's wire (its §7, last column)."""
        node, c = self, self.cfg
        Have, Want, Graft, Prune, Join = ns["Have"], ns["Want"], ns["Graft"], ns["Prune"], ns["Join"]
        ns.update(ALL="ALL", DERIVED="DERIVED", DECLARED="DECLARED", FORWARD="FORWARD", NONE="NONE",
                  IN="IN", OUT="OUT", BOTH="BOTH", ALL_JOINED="ALL_JOINED", SAMPLE="SAMPLE",
                  FAST="FAST", HOME="HOME", EVERY_INDEX=Bits(-1), EMPTY=Bits(0))

        class Obj:
            pass

        P = Obj()                                       # the payload object type (§1.1's table)
        P.name = P.id = "payload"
        P.index_count = lambda d: ns["N"](d)
        P.threshold = lambda d: ns["K"](d)
        P.verify = lambda f, h: ns["validate_chunk"](f)
        P.decode = lambda fr, d: ns["decode_and_reencode"](fr, d)
        P.header_of = lambda f: f.descriptor
        P.project = lambda f: [(f.group, f.index)]
        P.cross = lambda g, i: []
        P.family = lambda g: 0
        P.derived_interest = lambda h, nid, j: Bits(-1)
        prm = Obj()                                     # §6.1: the tier 4 setting
        prm.M, prm.F_LO, prm.F_HI, prm.D_OUT, prm.D_OUT_FAST, prm.D_OUT_MAX = 1, 6, 12, 8, 8, 12
        prm.ANNOUNCE_EXTRA, prm.START_DELAY, prm.SERVE_LIMIT, prm.EVIDENCE = "SAMPLE", 0.0, math.inf, None
        prm.SAMPLE_RETRY = c.get("SAMPLE_RETRY", 2.0)
        prm.EAGER, prm.DEFER_WINDOW = True, c.get("DEFER_WINDOW", 0.5)
        prm.REPAIR_SAMPLE, prm.SAMPLE_WAIT, prm.REPAIR_REASK = None, 0.0, False   # (R5) the repair sample: rows only
        prm.DECODE_AT_K, prm.DECODE_LATER = (lambda g: True), (lambda g: None)   # [D4] v0.3: everyone, at K
        prm.REPAIR_TO = lambda g: ns["mesh"]            # the out-relation is the mesh here
        prm.REPAIR_BUDGET = False                       # v0.3: every peer short of K, up to its shortfall
        P.params = prm
        self._P = P
        types = {"payload": P}
        joins = {P: Join(object_type="payload", interest="ALL", custody_count=0, duty="FORWARD", colours=1)}
        rows = c.get("setting") == "rows"
        has_rows = rows or bool(c.get("supernodes"))    # the block has row groups (sim.publish_block)
        keeps_rows = rows or node.supernode             # under custody alone only a supernode keeps the rows it may rebuild
        if c.get("setting") in ("custody", "rows"):     # §6.2's PeerDAS custody row: the column object type
            sim = node.sim

            def interest_in(g):                         # [D4] REPAIR_TO: joined peers whose interest includes the group
                return [q for q in node.peers if not ns["interest_of_peer"](q, g).empty()]

            COL = Obj()
            COL.name = COL.id = "column"
            COL.index_count = lambda h: h.count          # the blob count
            COL.threshold = lambda h: h.count            # K = N: no code within a column
            COL.verify = lambda f, h: ACCEPT             # the cell's KZG proof, assumed to check (honest chunks only, as v0.3's Merkle proof here)
            COL.decode = lambda fr, h: dict(fr)          # the cells present, if all are; nothing rebuilt within a column
            COL.header_of = lambda f: f.descriptor       # the header rides with the chunk (P2)
            if keeps_rows:                               # (R4) a cell is index b of column c and index c of row b
                COL.project = lambda f: [(f.group, f.index), (sim.grow[(f.descriptor.block, f.index)], sim.gcol[f.group])]
            else:
                COL.project = lambda f: [(f.group, f.index)]
            COL.cross = ((lambda g, i: [(sim.grow[(sim.ghdr[g].block, i)], sim.gcol[g])]) if keeps_rows
                         else (lambda g, i: []))
            COL.family = lambda g: sim.gcol[g]           # the relation key is the column
            COL.derived_interest = (lambda g, h, nid, j:
                                    Bits(-1) if sim.gcol[g] in sim.custody_of_id(nid, j.custody_count) else Bits(0))
            cprm = Obj()
            cprm.M, cprm.F_LO, cprm.F_HI, cprm.D_OUT, cprm.D_OUT_FAST, cprm.D_OUT_MAX = 1, c["F_LO"], 12, 8, 8, 12
            cprm.ANNOUNCE_EXTRA, cprm.START_DELAY, cprm.SERVE_LIMIT, cprm.EVIDENCE = "ALL_JOINED", 0.0, math.inf, None
            cprm.SAMPLE_RETRY = c.get("SAMPLE_RETRY", 2.0)
            cprm.EAGER, cprm.DEFER_WINDOW = True, c.get("DEFER_WINDOW", 0.5)
            cprm.REPAIR_SAMPLE, cprm.SAMPLE_WAIT, cprm.REPAIR_REASK = None, 0.0, False
            cprm.DECODE_AT_K, cprm.DECODE_LATER = (lambda g: False), (lambda g: None)   # no code within a column
            cprm.REPAIR_TO = interest_in                 # custodians lacking the rebuilt cells (via the rows)
            keepers_mode = c.get("repair_keepers", "push")
            self._keepers_to = None
            if keepers_mode != "push":                   # exploration: a peer that keeps every row rebuilds its own
                def keeps_every_row(q):                  # what q declared in its JOIN: every column (128)
                    j = ns["join_recv"][q].get(COL)
                    return j is not None and j.custody_count >= 128
                cprm.REPAIR_TO = lambda g: [q for q in interest_in(g) if not keeps_every_row(q)]
                if keepers_mode == "offer":              # offered to it instead, by _repair_variants
                    self._keepers_to = lambda g: [q for q in interest_in(g) if keeps_every_row(q)]
            cprm.REPAIR_BUDGET = c.get("repair_budget") == "on"   # [D4] each rebuilt cell to R_NODE of them, offered to the rest
            COL.params = cprm
            types = {"column": COL}
            my_cgc = sim.custody_count.get(node.id, c["cgc"])
            if node.sampler:                             # §4.10: interest without duty
                joins = {COL: Join(object_type="column", interest="DECLARED", custody_count=0, duty="NONE", colours=1)}
            else:
                joins = {COL: Join(object_type="column", interest="DERIVED", custody_count=my_cgc, duty="FORWARD", colours=1)}
            if has_rows:                                 # §6.2's RowDAS row: the row object type (EIP-8371)
                ROW = Obj()
                ROW.name = ROW.id = "row"
                ROW.index_count = lambda h: h.count      # 128 cells
                ROW.threshold = lambda h: ns["K"](h)     # 64: any half of a row rebuilds it
                ROW.verify = lambda f, h: ACCEPT
                ROW.decode = lambda fr, h: sim.rebuild_row(fr, h)   # recover_cells_and_kzg_proofs, as the source's chunks
                ROW.header_of = lambda f: f.descriptor
                ROW.project = COL.project                # the same chunk, the same two groups
                ROW.cross = lambda g, i: [(sim.gcolgroup[(sim.ghdr[g].block, i)], sim.ghdr[g].row)]
                ROW.family = lambda g: sim.gsub.get(g, -1)   # the relation key is the row's subnet (none under custody alone)
                ROW.derived_interest = (lambda g, h, nid, j:
                                        Bits(-1) if g in sim.gsub and sim.row_subnet_of_id(nid) == sim.gsub[g] else Bits(0))
                rprm = Obj()
                rprm.M, rprm.F_LO, rprm.F_HI, rprm.D_OUT, rprm.D_OUT_FAST, rprm.D_OUT_MAX = 1, c["F_LO"], 12, 8, 8, 12
                rprm.ANNOUNCE_EXTRA, rprm.START_DELAY, rprm.EVIDENCE = "ALL_JOINED", c["ROW_DELAY"], None
                rprm.SERVE_LIMIT = 64                    # (R6) half a row per peer, EIP-8371
                rprm.SAMPLE_RETRY = c.get("SAMPLE_RETRY", 2.0)
                rprm.EAGER, rprm.DEFER_WINDOW = False, c.get("DEFER_WINDOW", 0.5)   # rows: holdings and offers only
                rprm.REPAIR_SAMPLE, rprm.SAMPLE_WAIT = c.get("REPAIR_SAMPLE"), c.get("SAMPLE_WAIT", 0.5)   # (R5) option
                rprm.REPAIR_REASK = c.get("REPAIR_REASK", False)
                def own_row(g):                          # a row of the node's designated subnet
                    return node.row_subnet is not None and sim.gsub.get(g) == node.row_subnet

                def decode_later(g):
                    if own_row(g):                       # phase 3: any member, later
                        return None if node.liar else c["PHASE3"] + ns["_rng"].uniform(0, c["PHASE3_JITTER"])
                    if node.supernode:                   # phase 2: a supernode, every other row (PeerDAS's reconstruction, delayed)
                        return c["PHASE2"] + ns["_rng"].uniform(0, c["PHASE2_JITTER"])
                    return None

                rprm.DECODE_AT_K = lambda g: node.reconstructor and own_row(g)   # phase 1: a row reconstructor, its subnet's row
                rprm.DECODE_LATER = decode_later
                rprm.REPAIR_TO = interest_in             # the custodians of the rebuilt cells' columns, by projection
                rprm.REPAIR_BUDGET = False               # rows are offered, not pushed (EAGER off)
                ROW.params = rprm
                types["row"] = ROW
                if node.sampler or node.id == 1 or not rows:   # the proposer wants no row: it holds the columns; under
                    joins[ROW] = Join(object_type="row", interest="DECLARED", custody_count=0, duty="NONE", colours=1)   # custody alone nobody joins rows
                else:
                    joins[ROW] = Join(object_type="row", interest="DERIVED", custody_count=0, duty="FORWARD", colours=1)
        self._types, self._joins = types, joins

        class InterestMap(dict):                        # interest[g]: ours, computable before any chunk (§3)
            def __missing__(self, g):
                return node.own_interest_bits(g)

        ns.update(PAYLOAD=P, hdr=ns["desc"], T_of={}, rebuilt=AutoMap(Bits), interest=InterestMap(),
                  known_at=DefaultMap(0.0), served=AutoMap(lambda: AutoMap(int)), want_p=AutoMap(dict),
                  join_recv=AutoMap(dict), join_sent=AutoMap(dict),
                  push_out=AutoMap(lambda: AutoMap(lambda: AutoMap(set))),
                  push_in=AutoMap(lambda: AutoMap(lambda: AutoMap(set))),
                  standing=AutoMap(lambda: AutoMap(set)),
                  claims=AutoMap(set), reconsider_at={}, deferred=DefaultMap(False), waited=DefaultMap(False), probe={}, probed={},
                  probe_asks=set(), rsample=AutoMap(list), rsample_step=DefaultMap(0),
                  rsample_asked=AutoMap(lambda: AutoMap(set)), rsample_final=DefaultMap(False))
        Ask = Wm.WantIndex
        chunk_id = ns["message_id"]
        spec_open_group = ns["open_group"]

        def type_of_group(g):
            return types.get(node.sim.gtype.get(g), P)

        _doc_authenticable, _doc_filter_entry = ns["authenticable"], ns["filter_entry"]

        def authenticable(g):                           # §4.2: the gate is the type's; a cell's header rides
            return _doc_authenticable(g) if type_of_group(g) is P else True   # with it (P2)

        def filter_entry(p, entry):                     # v0.5 §7.2 starts an ask's promise at its write; a
            fresh = [(a, p) for m in entry.iwants() if getattr(m, "want", False)   # WANT starts none (§4.5)
                     for a in m.ids if (a, p) not in ns["promises"]]
            out = _doc_filter_entry(p, entry)
            for k in fresh:
                ns["promises"].pop(k, None)             # its timer finds no promise and does nothing
            return out

        def type_of(tid):
            return types[tid]

        def links(T):
            return node.peers                           # every peer joins every type of the setting

        def joined_types():
            return list(types.values())

        def joined_peers():
            return node.peers

        def related(q):
            po, pi = ns["push_out"].get(q), ns["push_in"].get(q)
            return any(cols for m in (po, pi) if m for fams in m.values() for cols in fams.values())

        def node_id(p):
            return node.sim.peer_id(p)

        def in_pushers(T, fam, col):
            return [q for q in node.peers if col in ns["push_in"][q][T][fam]]

        def out_pushees(T, fam, col):
            return [q for q in node.peers if col in ns["push_out"][q][T][fam]]

        def candidates(T, fam):
            return []                                   # the toy's topology is static, as for v0.3

        def least_used_colour(T, fam):
            return 0

        def families_with_duty(T):
            if T is P:
                return [0]
            if T.id == "row":
                return [node.row_subnet] if node.row_subnet is not None else []
            return sorted(node.custody)

        def wants_family(T, fam):
            if T is P:
                return True
            if T.id == "row":
                return fam == node.row_subnet
            return fam in node.custody

        def duty_for(g):                                # §1.2: duty is per object type, declared at JOIN
            return joins[type_of_group(g)].duty

        def uplink_class():
            return "FAST" if (c["card17"] and node.cls["up"] >= c["FAST_UPLINK"]) else "HOME"

        def our_join(T):
            return joins[T]

        def open_group(g, f):
            spec_open_group(g, f)
            h = node.sim.ghdr.get(g)
            if h is not None:
                ns["desc"][g] = h                       # a row group's header is the row's, not the chunk's column's
            ns["T_of"][g] = type_of_group(g)
            ns["interest"][g] = node.own_interest_bits(g)
            ns["known_at"].setdefault(g, ns["now"])     # the block's arrival, if the sim recorded it

        def open_group_source(g, d):
            ns["desc"][g] = d
            ns["T_of"][g] = type_of_group(g)
            ns["interest"][g] = node.own_interest_bits(g)
            ns["known_at"].setdefault(g, ns["now"])

        def interest_satisfied(g):                      # §1.5: K distinct chunks for ALL with a code, else every wanted index
            d = ns["desc"].get(g)
            if d is None:
                return False
            have = ns["received"][g] | ns["rebuilt"][g]
            want = ns["interest"][g]
            if want.v < 0:
                return popcount(have) >= type_of_group(g).threshold(d)
            return (want & ~have).empty()

        def decode_duty(g):                             # §4.6: a decode where the type has a code
            T, d = type_of_group(g), ns["desc"][g]
            return T.threshold(d) < T.index_count(d)

        def deferred_offers(p, h):                      # [D8] recorded now, asked once the start delay has run
            g = h.group
            due = ns["known_at"][g] + type_of_group(g).params.START_DELAY - ns["now"]
            for i in h.bits & ns["interest"][g] & ~ns["mine"][g]:
                a = Ask(g, i)
                ns["add_offer"](a, p)
                if a not in node._retry_armed:
                    node._retry_armed.add(a)
                    ns["after"](max(0.0, due) + 1e-6, ns["retry_offer"], a)
            return []

        def offered_us(p, g, i):
            return p in ns["offers"].get(Ask(g, i), ())

        def publish_evidence(g, body):
            pass

        def choice(xs):
            return ns["shuffled"](xs)[0]

        def wire_size(f):                               # §4.11: the chunk's bytes on the wire, as the links charge them
            return Wm.chunk_wire(f)

        def unreachable(g, bits):                       # §4.10: no link can serve these samples; here: given up
            node.unreachable[g] = node.unreachable.get(g, Bits()) | bits
            if g in node.samples:
                node.samples[g] = node.samples[g] & ~bits
            ns["interest"][g] = ns["interest"][g] & ~bits

        def send(p, msg, urgent=False):                 # the v0.3-wire binding (protocol-v2.md §7); true if the
            if isinstance(msg, Have):                   #   queue admitted it, as v0.5's enqueue
                hb = Wm.HaveBitmap(msg.group, msg.bits)
                if not msg.offer:                       # the two claims ride in the version byte (§7, last column)
                    hb.claim_all, hb.complete = msg.claim_all, msg.complete
                return ns["enqueue"](p, (Wm.IHAVE if msg.offer else Wm.IDONTWANT)(hb), urgent)
            elif isinstance(msg, Want):
                w = Wm.IWANT([Ask(msg.group, i) for i in msg.bits])
                w.items[0].want = True                  # §4.5: a WANT starts no promise at its write
                return ns["enqueue"](p, w, urgent)
            elif isinstance(msg, (Graft, Prune, Join)):
                return True                             # relations are static here; JOIN is the subscription
            else:
                return ns["enqueue"](p, msg, urgent)

        ns.update({k: v for k, v in locals().items() if callable(v) and not k.startswith("_")
                   and k not in ("c", "node", "ns", "Have", "Want", "Graft", "Prune", "Join", "Obj",
                                 "P", "prm", "COL", "cprm", "ROW", "rprm", "rows", "has_rows", "keeps_rows", "sim", "my_cgc", "interest_in",
                                 "own_row", "decode_later",
                                 "types", "joins", "InterestMap", "spec_open_group")})
        ns["Ask"] = Ask
        ns["chunk_id"] = chunk_id
        doc_on_rpc = ns["on_rpc"]

        def on_rpc(p, rpc):                             # v0.3's RPC read as v2's messages
            haves = []
            for hb in rpc.ihave.ids:
                if isinstance(hb, Wm.HaveBitmap):
                    haves.append(Have(group=hb.group, bits=hb.bits, offer=True, claim_all=False, complete=False))
            for hb in rpc.idontwant:
                if isinstance(hb, Wm.HaveBitmap):
                    d = ns["desc"].get(hb.group) or node.sim.ghdr.get(hb.group)   # a column's header is known from its id
                    full = d is not None and hb.bits.v == all_bits(ns["N"](d)).v
                    haves.append(Have(group=hb.group, bits=hb.bits, offer=False,
                                      claim_all=full or hb.claim_all, complete=full or hb.complete))
            r = Obj()
            r.chunks, r.haves, r.asks, r.grafts, r.prunes = rpc.chunks, haves, list(rpc.iwant.ids), [], []
            return doc_on_rpc(p, r)
        ns["on_rpc"] = on_rpc
        doc_check = ns["check_completion"]

        def check_completion(g):                        # the measurement point: completion at K
            was = ns["stop_pull"][g]
            doc_check(g)
            if not was and ns["stop_pull"][g] and g not in node.completed:
                node.completed[g] = node.sim.now
        ns["check_completion"] = check_completion
        doc_on_want = ns["on_want"]

        def on_want(p, asks):                           # the invariants' count of asks left unanswered, by reason,
            for a in asks:                              #   in on_want's order; it reads state without allocating it
                gi = ns["group_index"](a)
                if gi is None:
                    continue
                g, T = gi.group, type_of_group(gi.group)
                e = ns["peer_has"].get(p, {}).get(g)
                mid = None
                if e is not None and e.has(gi.index):
                    why = "claimed"
                elif ns["served"].get(p, {}).get(g, 0) >= T.params.SERVE_LIMIT:
                    why = "limit"
                elif (mid := ns["resolve"](a)) is None:
                    why = None if node.sim.nodes[p].sampler else "not held"
                elif mid in ns["unwanted"].get(p, ()):
                    why = "unwanted"
                elif ns["serve_count"].get(p, {}).get(mid, 0) >= ns["GOSSIP_RETRANSMISSION"]:
                    why = "retransmitted"
                else:
                    why = None
                if why:
                    node.refused[(T.id, why)] += 1
            return doc_on_want(p, asks)
        ns["on_want"] = on_want
        doc_promise_due = ns["promise_due"]

        def promise_due(a, p, at):                      # the same name, so that events hash as before: records a
            if ns["promises"].get((a, p)) == at:        #   broken promise for the invariants (when, whom, which ask)
                gi = ns["group_index"](a)
                if gi is not None:
                    node.broken.append((ns["now"], at, p, gi.group, gi.index))
            return doc_promise_due(a, p, at)
        ns["promise_due"] = promise_due
        if c.get("promise_mode") == "peer":             # an option against §4.13: the promise follows each peer's
            self._peer_promise(ns)                      #   observed answer times (RTO), floored at v0.3's PROMISE
        elif c.get("promise_mode") == "uplink":         # the form §4.13 rejects: the promise scaled with the window
            ns["PROMISE"] = ns["PROMISE"] * ns["ask_scale"]()
        if self.id in c.get("faulty", ()) and not self.hoarder:
            ns["on_want"] = lambda p, asks: []          # withholds: offers, never answers
        if self.liar:                                   # --fault claim: claims every cell of its row at the first one
            doc_send_have = ns["send_have"]

            def send_have(p, g):
                if type_of_group(g).id == "row" and node.interest_bits(g).v != 0:
                    d = ns["desc"].get(g) or node.sim.ghdr.get(g)
                    ns["send"](p, Have(group=g, bits=all_bits(ns["N"](d)), offer=False, claim_all=True, complete=True), urgent=True)
                else:
                    doc_send_have(p, g)
            ns["send_have"] = send_have
        if self.hoarder:                                # --fault hoard: decodes and claims as the document says, but its
            ns["push_rebuilt"] = lambda g, new: None    #   rebuilt chunks go to nobody unasked, a standing WANT is dropped,
            if c.get("hoard_members"):                  # --fault hoardm: a row's rebuilt cells go to its subnet's members
                def push_rebuilt(g, new):               #   that custody their columns, and to nobody else: each member
                    sub = node.sim.gsub.get(g)          #   gets what the member check looks for
                    for i in new:
                        f = ns["chunks"][g][i]
                        for (g2, i2) in ns["type_of_group"](g).project(f):
                            if g2 == g: continue
                            for q in node.peers:
                                nq = node.sim.nodes[q]
                                if (nq.row_subnet == sub and node.sim.gcol.get(g2) in nq.custody
                                        and not (ns["peer_has"][q][g2].bits | ns["pushed"][q][g2]).has(i2)):
                                    ns["enqueue"](q, f, urgent=False)
                                    ns["note_push"](q, g2, i2)
                ns["push_rebuilt"] = push_rebuilt
            spec_on_want, probed = ns["on_want"], set() #   and an ask for one is answered once per peer and group, and only
                                                        #   when it is the RPC's one ask on that group: what a probe looks like
            def on_want(p, asks):
                per_group = Counter(gi.group for gi in map(ns["group_index"], asks) if gi is not None)
                keep = []
                for a in asks:
                    gi = ns["group_index"](a)
                    if gi is not None and ns["rebuilt"][gi.group].has(gi.index):
                        if per_group[gi.group] != 1 or (p, gi.group) in probed:
                            node.hoard_refused += 1
                            continue
                        probed.add((p, gi.group))
                        node.hoard_served += 1
                    keep.append(a)
                return spec_on_want(p, keep)
            ns["on_want"] = on_want
            spec_serve_standing = ns["serve_standing"]

            def serve_standing(g, i):
                if ns["rebuilt"][g].has(i):
                    ns["standing"][g].pop(i, None)
                    return
                spec_serve_standing(g, i)
            ns["serve_standing"] = serve_standing

    def set_column_relations(self, rel, row_rel=None):
        """The custody and row settings: rel = {column: peers}, the push relation both ways per column
        (the column's mesh; for the proposer its custodian links), and row_rel = {subnet: peers} for
        the node's row subnet. Every peer has joined every type of the setting."""
        ns, COL = self.ns, self._types["column"]
        ROW = self._types.get("row")
        for q in self.peers:                            # what each peer declared to us, and ours to it
            sampler = self.sim.nodes[q].sampler
            if sampler:
                ns["join_recv"][q][COL] = Wm.Container(object_type="column", interest="DECLARED",
                                                       custody_count=0, duty="NONE", colours=1)
            else:
                ns["join_recv"][q][COL] = Wm.Container(object_type="column", interest="DERIVED",
                                                       custody_count=self.sim.custody_count.get(q, self.cfg["cgc"]),
                                                       duty="FORWARD", colours=1)
            ns["join_sent"][q][COL] = self._joins[COL]
            if ROW is not None:                         # the proposer, like a sampler, wants no row: it holds the columns;
                no_row = sampler or q == 1 or self.cfg.get("setting") != "rows"   # under custody alone nobody joins rows
                ns["join_recv"][q][ROW] = Wm.Container(object_type="row", interest="DECLARED" if no_row else "DERIVED",
                                                       custody_count=0, duty="NONE" if no_row else "FORWARD", colours=1)
                ns["join_sent"][q][ROW] = self._joins[ROW]
        union = set()
        for col, peers in rel.items():
            for q in peers:
                ns["push_out"][q][COL][col].add(0)
                ns["push_in"][q][COL][col].add(0)
            union |= set(peers)
        for sub, peers in (row_rel or {}).items():      # rows: the relation carries holdings and offers, no pushes (EAGER off)
            for q in peers:
                ns["push_out"][q][ROW][sub].add(0)
                ns["push_in"][q][ROW][sub].add(0)
            union |= set(peers)
        ns["mesh"] = union

    def _v2_relations(self, mesh, colour_meshes=None):
        ns, P = self.ns, self._P
        for q in self.peers:
            ns["join_recv"][q][P] = ns["join_sent"][q][P] = self._joins[P]
        if colour_meshes is None:                       # the tier 4 setting: one colour, the mesh
            for q in mesh:
                ns["push_out"][q][P][0].add(0)
                ns["push_in"][q][P][0].add(0)
            return
        P.params.M = len(colour_meshes)                 # variant C: M = N, a relation per colour
        union = set()
        for col, m in colour_meshes.items():
            for q in m:
                ns["push_out"][q][P][0].add(col)
                ns["push_in"][q][P][0].add(col)
            union |= set(m)
        ns["mesh"] = union                              # what the toy's v0.3-side options read as "the mesh"

    def expire_offers(self, now):
        """§8.1: an announcer's offers of a group go 30 s after its last one (the ordered lists and
        `offered`), checked at each heartbeat, so an offer can outlive its 30 s by up to one. A
        group's diffusion takes well under that, so what goes here is what a group that completed
        by decoding left behind; it matters for `listed` alone."""
        ns, old = self.ns, now - OFFER_TTL
        gone = [k for k, t in self._offer_at.items() if t < old]
        for p, g in gone:
            del self._offer_at[(p, g)]
            ns["offered"][p].pop(g, None)
            empty = []
            for a, lst in ns["offers"].items():
                if p in lst and ns["group"](a) == g:
                    lst.remove(p)
                    self._listed[p] -= 1
                    if not lst:
                        empty.append(a)
            for a in empty:
                del ns["offers"][a]

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
