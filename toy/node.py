"""One node: the pseudocode's functions, executed in a namespace of their own, and the helpers the
pseudocode names but does not write out (§8.1, "Helpers not written out").

Each node gets a fresh module namespace. The spec's code (extract.py) is compiled once and executed
in every namespace, so each node's functions read that node's state through their globals, exactly
as the pseudocode reads `mesh`, `peer_has` or `now`. What lives here is only what the document
leaves to the environment; a behaviour that matters and is not in the document is a gap in the
document, and is listed in README.md.
"""
import hashlib
import hmac
import math
from collections import Counter
import random
from collections import deque

import bits as B
import scenario
import wire as Wm
from bits import (AutoMap, Bits, DefaultMap, HaveEntry, LazyBits, LazyList, LazyMap, LazySet, OfferMap, PushEntry,
                  _join, all_bits, bitmap, lazy, lazy2, lazy_dict, popcount, tie_table, zero)
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


class _Lane(list):
    """A lane of a PeerQueue: an entry added to it makes the queue join its map (bits.LazyDict)."""
    __slots__ = ("_q",)

    def __init__(self, q, items=()):
        super().__init__(items)
        self._q = q

    def append(self, x):
        super().append(x)
        _join(self._q)

    def extend(self, xs):
        super().extend(xs)
        if self:
            _join(self._q)

    def insert(self, i, x):
        super().insert(i, x)
        _join(self._q)

    def __iadd__(self, xs):
        super().__iadd__(xs)
        if self:
            _join(self._q)
        return self

    def __setitem__(self, i, x):                # an element, or a slice
        super().__setitem__(i, x)
        if self:
            _join(self._q)


class PeerQueue:
    """queue[p]: the two lanes of one peer's bounded queue (§7). Read for a peer it does not hold, the queue
    table gives a detached, empty one, which joins the table when an entry goes into a lane (§8.1: reading
    allocates nothing)."""
    __slots__ = ("urgent", "normal", "_home", "_key", "__weakref__")

    def __init__(self, home=None, key=None):
        object.__setattr__(self, "_home", home)
        object.__setattr__(self, "_key", key)
        self.urgent, self.normal = [], []

    def __setattr__(self, k, v):
        if k in ("urgent", "normal"):
            v = _Lane(self, v)
            object.__setattr__(self, k, v)
            if v:
                _join(self)
        else:
            object.__setattr__(self, k, v)

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
    standing, hops, probe = False, 0, False   # an ask by message id carries no WANT fields (protocol-v2.md §2)

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
        self.unreachable = {}           # samples no link could serve: group -> Bits (protocol-v2.md before [D12]; now none)
        self.sample_log = {}            # [D12] a sampler's asks per sample: (group, index) -> [(peer, forwarded, when)]
        self.sample_from = {}           # [D12] the first arrival of each sample: (group, index) -> (peer, when)
        self._uprng = None              # --upkeep on: the node's own draws for §3's candidates
        self.relation_msgs = Counter()  # --upkeep on: JOINs, GRAFTs and PRUNEs handed to the wire
        self.cover_opened = 0           # --upkeep on: sampling-only links keep_coverage opened at run time
        self.forwarded_out = 0          # [D12] routed requests this node passed on for a sampler (route_want)
        self.cover_gaps = 0             # [D12] families keep_coverage found short (the graph's floor missed them)
        self.cover_added = 0            # [D12] sampling-only links the graph added for this sampler
        self._cover_checked = False
        self.supernode = self.id in cfg.get("supernode_ids", ())          # every column; rebuilds any row still short (phase 2)
        self.reconstructor = self.supernode or self.id in cfg.get("reconstructor_ids", ())   # rows: 64 columns or more, decodes its row at K
        self.row_subnet = None          # rows: the node's designated row subnet (EIP-8371)
        self.liar = cfg.get("claim") and self.id in cfg.get("faulty", ())   # rows: claims a row it did not rebuild
        self.hoarder = cfg.get("hoard") and self.id in cfg.get("faulty", ())   # v2: rebuilds and claims, passes the probe, repairs nothing
        self.hoard_served = self.hoard_refused = 0      # a hoarder's rebuilt chunks: asks answered (probes), asks refused
        self.member_checks = 0                          # (R5) the member check: verified claims not taken, custody cells missing
        self.repair_verdicts = Counter()                # (R5, option) the repair sample's verdicts
        self.bias_drawn = self.bias_uncovered = 0       # --repair-bias: cells put first from uncovered columns, and
                                                        #   the uncovered cells lacked where it drew (option 1)
        self._retry_armed = set()       # asks whose delayed first try is scheduled (deferred offers, [D8])
        self.held_back = 0              # --ihave-limits: asks held back to the next heartbeat (protocol.md §4.4)
        self.blocks_waiting = set()     # --late-block: the roots of the blocks not installed here yet (protocol.md §4.2)
        self.reserved = Counter()       # --late-block: peer -> its deferred copies in the bounded store (§8.2)
        self.late = Counter()           # --late-block: its counters (run.py reports them)
        self.alarm = Counter()          # --alarm-wait, --fault hoardcol: their counters (run.py reports them)
        self.alarm_cells = {}           # --alarm-wait: (column group, index) -> the members asked, as a custodian
        self.alarming = False           # --alarm-wait: an alarm is being sent (not a routed request, forwarded_out)
        self.alarm_rng = random.Random(cfg["seed"] * 7919 + 7307 + nid)   #   its own draws: the jitter, the member
        ns = self._namespace()
        exec(SPEC, ns)
        self.v2 = cfg.get("doc") == "v2"
        if self.v2:
            self._v2_names(ns)
            exec(spec2(), ns)
        self._override(ns)
        if ns["MAX_IHAVE_MESSAGES"] < math.inf or ns["MAX_IHAVE_LENGTH"] < math.inf:
            spec_over = ns["over_ihave_limits"]

            def over_ihave_limits(p):                   # each candidate ask is checked once: true holds it back
                over = spec_over(p)
                self.held_back += over
                return over
            ns["over_ihave_limits"] = over_ihave_limits
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
            if cfg.get("rebuilt_seen", "off") == "on":
                self._rebuilt_seen(ns)
            if cfg.get("REPAIR_BIAS", 0) > 0 and "row" in self._types:
                self._repair_bias(ns, cfg["REPAIR_BIAS"])
            if cfg.get("hoard_column") and "row" in self._types:
                self._hoard_column(ns)
            if cfg.get("ALARM_WAIT") and "row" in self._types and self.id not in cfg.get("faulty", ()):
                self._alarm(ns)
        self.ns = ns

    def _hidden(self, g, i):
        """--fault hoardcol: whether index i of group g is the cell its row's hoarders hide (sim.hoard_x)."""
        sim = self.sim
        if g in sim.gsub:                               # a row: index i is column i
            return sim.hoard_x.get(sim.gsub[g]) == i
        if g not in sim.gcol:
            return False
        r = sim.grow.get((sim.ghdr[g].block, i))        # a column: index i is row i
        return r is not None and sim.hoard_x.get(sim.gsub.get(r)) == sim.gcol[g]

    def _hoard_column(self, ns):
        """--fault hoardcol (an option, proposed on 2026-10-28): a hoarder that
        repairs every withheld column of its row but one, the one sim.hoard_x names for the subnet: the highest
        withheld column no honest member custodies. It runs --fault hoard's code with the document's push_rebuilt
        for every other cell, and serves nothing of the hidden one to anyone, its hidden cell in the column group
        included (the probe-shaped answer aside). Meant with --rebuilt-seen on, which run.py requires. An honest
        node counts its probes at the hidden index: none while the probed index was the lowest lacked; drawn at random
        (protocol-v2.md §4.6), it can be the hidden one."""
        node = self
        if self.hoarder:
            doc_push_rebuilt, spec_on_want = self._doc_push_rebuilt, ns["on_want"]

            def push_rebuilt(g, new):
                doc_push_rebuilt(g, [i for i in new if not node._hidden(g, i)])
            ns["push_rebuilt"] = push_rebuilt

            def on_want(p, asks):
                keep = []
                for a in asks:
                    gi = ns["group_index"](a)
                    if gi is not None and node._hidden(gi.group, gi.index):
                        node.alarm["hidden refused"] += 1
                        node.alarm["alarms refused by a hoarder"] += bool(gi.standing)
                        continue
                    keep.append(a)
                return spec_on_want(p, keep)
            ns["on_want"] = on_want
        else:
            doc_defer_on_claim = ns["defer_on_claim"]

            def defer_on_claim(g):
                doc_defer_on_claim(g)
                if node._hidden(g, ns["probe"][g]):
                    node.alarm["probe at the hidden index"] += 1
            ns["defer_on_claim"] = defer_on_claim

    def _alarm(self, ns):
        """--alarm-wait S (an option, proposed on 2026-10-28), an honest node's two
        parts; faulty nodes neither alarm nor act on one. The custodian (alarm_check, scheduled by sim.publish_block
        at known_at + S + up to --alarm-jitter): for each row whose cell in its custody columns it still lacks and no
        peer's holding shows, a standing WANT for the row's group at the column's index, to a linked member of the
        row's subnet not yet asked for it (its node id's subnet and a row JOIN); again every --alarm-next seconds while
        the cell is missing, up to --alarm-max members. The member (on_want): a standing ask for an index of its own
        row that it lacks, from a peer not DECLARED, is kept as the document keeps it (§4.10); if the member
        deferred on a claim its probe verified, it asks that claimant for the index once, as the probe is asked
        (exempt from stop-pull, DEFER_WINDOW as the promise); if that promise breaks and the row is still COMPLETE,
        it penalises the claimant and decodes as reconsider's rebuild does. Nothing new on the wire."""
        node, sim, c = self, self.sim, self.cfg
        ROW, Want = self._types["row"], ns["Want"]
        doc_on_want, Ask = ns["on_want"], ns["Ask"]
        asked = AutoMap(set)                            # row group -> indices asked of the claimant on an alarm
        alarms = set()                                  # (row group, index, peer): standing asks kept as alarms

        def alarm_check(root, k):
            B = sim.cfg["blobs"]
            for col in sorted(node.custody):
                g = sim.gcolgroup[(root, col)]
                if ns["expired"](g):
                    continue
                for b in range(B):
                    if ns["received"][g].has(b) or ns["rebuilt"][g].has(b) or ns["holders"][g][b]:
                        continue
                    rg = sim.grow[(root, b)]
                    tried = node.alarm_cells.setdefault((g, b), [])
                    if len(tried) >= c["ALARM_MAX"]:
                        continue                        # every member it may ask was asked
                    ms = [q for q in node.peers if q not in tried   # a member: its node id's subnet, and a row JOIN
                          and sim.nodes[q].row_subnet == sim.gsub[rg]]   #   (none for the proposer, a sampler)
                    if not ms:
                        node.alarm["no member left"] += 1
                        continue
                    q = node.alarm_rng.choice(ms)
                    tried.append(q)
                    node.alarm["sent"] += 1
                    node.alarming = True
                    ns["send"](q, Want(group=rg, bits=bitmap({col}), standing=True), urgent=False)
                    node.alarming = False
            if k + 1 < c["ALARM_MAX"]:
                sim.after(node, c["ALARM_NEXT"], node.alarm_check, root, k + 1)
        self.alarm_check = alarm_check

        def on_alarm(g, i):
            if not (ns["deferred"][g] and ns["received"][g].has(ns["probe"][g])) or i in asked[g]:
                return                                  # a verified claim only, and once per index
            asked[g].add(i)
            T, q, a = ns["type_of_group"](g), ns["probed"][g], Ask(g, i)
            ns["add_offer"](a, q)                       # a claim is an offer of every index (§4.6's probe)
            ns["tried"][a][q] = ns["now"]
            ns["probe_asks"].add(a)                     # past stop-pull, as the probe
            ns["promises"][(a, q)] = ns["now"]
            ns["after"](T.params.DEFER_WINDOW, ns["promise_due"], a, q, ns["now"])
            ns["after"](T.params.DEFER_WINDOW, alarm_due, g, i, q)
            node.alarm["asks of a claimant"] += 1
            ns["send"](q, Want(group=g, bits=bitmap({i})), urgent=False)   # as defer_on_claim sends the probe

        def alarm_due(g, i, q):
            if ns["received"][g].has(i) or ns["rebuilt"][g].has(i) or ns["state"][g] != ns["COMPLETE"]:
                return                                  # answered, rebuilt, or decoding already
            node.alarm["broken"] += 1
            ns["penalise"](q)
            T = ns["type_of_group"](g)                  # reconsider's rebuild: the late decode claim
            ns["state"][g] = ns["DECODING"]
            ns["mine"][g] = all_bits(T.index_count(ns["hdr"][g]))
            for q2 in ns["suppression_scope"](g):
                ns["send_have"](q2, g)
            node.alarm["rebuilds"] += 1
            ns["start"](ns["decode_group"], g)

        def on_want(p, asks):
            for a in asks:
                gi = ns["group_index"](a)
                if (gi is None or not gi.standing or gi.group not in sim.gsub or sim.gsub[gi.group] != node.row_subnet
                        or ns["expired"](gi.group) or ns["join_recv"][p][ROW].interest == "DECLARED"
                        or ns["peer_has"][p][gi.group].has(gi.index)):
                    continue
                if ns["resolve"](a) is not None:
                    node.alarm["held at once"] += 1     # answered now, as any ask for a chunk we hold
                    continue
                if (gi.group, gi.index, p) not in alarms:
                    alarms.add((gi.group, gi.index, p))
                    node.alarm["kept"] += 1
                on_alarm(gi.group, gi.index)
            return doc_on_want(p, asks)
        ns["on_want"] = on_want
        doc_serve_standing = ns["serve_standing"]

        def serve_standing(g, i):                       # the document's test for an answer, before it pops them
            limit = ns["type_of_group"](g).params.SERVE_LIMIT
            for p in ns["standing"].get(g, {}).get(i, ()):
                if ((g, i, p) in alarms and not ns["peer_has"][p][g].has(i)
                        and ns["served"][p][g] < limit):
                    node.alarm["answered"] += 1
            doc_serve_standing(g, i)
        ns["serve_standing"] = serve_standing

    def _rebuilt_seen(self, ns):
        """--rebuilt-seen on (an option, proposed on 2026-10-26): decode_group marks each cell it
        rebuilt seen, as publish marks the source's own chunks. A pushed copy of it is then acknowledged (it is
        stored, so accepted) and neither validated nor forwarded again; a hoarder that relays only what it
        received (--fault hoardm) no longer relays the copies of what it rebuilt. A rebuilt cell is the source's
        chunk (rebuild_row), so one id covers every copy of it."""
        doc_decode_group, rebuilt, chunks = ns["decode_group"], ns["rebuilt"], ns["chunks"]

        def decode_group(g):
            before = rebuilt[g].copy()
            doc_decode_group(g)
            for i in rebuilt[g]:
                if not before.has(i):
                    ns["mark_seen"](ns["chunk_id"](chunks[g][i]))
        ns["decode_group"] = decode_group

    def _repair_bias(self, ns, share):
        """--repair-bias SHARE (an option, proposed on 2026-10-26): in repair_verdict's extension of the
        sample, up to SHARE of the step's new cells are put first from the cells we lack in uncovered columns, the
        rest drawn uniformly as the document draws them all. A column is uncovered when no member of the row's
        subnet that we are linked to custodies it, a claimant aside; a peer's subnet and custody follow from its
        node id and its column JOIN, as for link_cover. The document's code runs as written: only its one draw,
        shuffled(...), is ordered for the call; ask_custodian's choice(...) draws with shuffled too, so it is
        kept on the plain draw (peers are numbered as columns are; an earlier build ordered it as well), and a second
        shuffled in one call fails."""
        sim, node, COL = self.sim, self, self._types["column"]
        spec_repair_verdict, spec_shuffled = ns["repair_verdict"], ns["shuffled"]

        def covered(g):
            sub, cols = sim.gsub.get(g), set()
            for q in node.peers:
                if q in ns["claims"][g]:
                    continue
                qid = ns["node_id"](q)
                j = ns["join_recv"][q].get(COL)
                if j is None or sim.row_subnet_of_id(qid) != sub:
                    continue
                cols |= sim.custody_of_id(qid, j.custody_count)
            return cols

        def repair_verdict(g):
            steps, k = ns["type_of_group"](g).params.REPAIR_SAMPLE, ns["rsample_step"][g]
            if not steps or k >= len(steps):
                return spec_repair_verdict(g)          # the last step's judgement draws nothing
            n = int(share * (steps[k][0] - len(ns["rsample"][g])))
            draws = []

            def shuffled(xs):                          # index i of a row is column i
                draws.append(1)                        # the extension's draw only: a second one is a leak
                assert len(draws) == 1, "--repair-bias: shuffled drawn twice in one repair_verdict"
                cov = covered(g)
                unc = [i for i in xs if i not in cov]
                first = spec_shuffled(unc)[:n]
                node.bias_drawn += len(first)
                node.bias_uncovered += len(unc)
                taken = set(first)
                return first + spec_shuffled([i for i in xs if i not in taken])
            spec_choice = ns["choice"]
            ns["shuffled"], ns["choice"] = shuffled, lambda xs: spec_shuffled(xs)[0]
            try:
                return spec_repair_verdict(g)
            finally:
                ns["shuffled"], ns["choice"] = spec_shuffled, spec_choice
        ns["repair_verdict"] = repair_verdict

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
            "uint64_le": Wm.uint64_le,
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
            "MAX_PENDING_GROUPS": c.get("MAX_PENDING_GROUPS", math.inf),     # the client's (§8.2): no limit
            "MAX_IHAVE_MESSAGES": c.get("MAX_IHAVE_MESSAGES", math.inf),     # the client's (§8.2): no limit
            "MAX_IHAVE_LENGTH": c.get("MAX_IHAVE_LENGTH", math.inf),         #   unless --ihave-limits
            "HAVE_TTL": c["HAVE_TTL"], "PUSH_TTL": c["PUSH_TTL"],
            "CANCEL": c["card8"], "RAREST": c["card9"], "PROJECT": c["card12"], "PACED": c["card15"],
            "ANSWERS_FIRST": c.get("answers_first", "off") == "on",
            "DESCRIPTOR_IN_CHUNK": True,
            # state (§8.1); missing entries read as empty
            "desc": DefaultMap(None), "state": DefaultMap(None), "chunks": lazy(lazy_dict), "known_id": lazy(lazy_dict),
            "received": lazy(LazyBits), "mine": lazy(LazyBits), "stop_pull": DefaultMap(False),
            "origin": {}, "planned": {},
            "peer_has": lazy(lambda home, p: LazyMap(HaveEntry, home, p)),
            "pushed": lazy(lambda home, p: LazyMap(PushEntry, home, p)),
            "holders": lazy2(LazySet), "sent_to": lazy2(LazyBits),
            "queue": lazy(PeerQueue), "slot_held": DefaultMap(False),
            "unwanted": lazy(LazySet), "serve_count": lazy2(zero),
            "asked_at": {}, "tried": lazy(lazy_dict), "offers": OfferMap(), "promises": {},
            "offered": lazy2(LazyBits), "asked_parked": lazy(LazySet),
            "last_resort_armed": set(),
            "ihave_rpcs": DefaultMap(0), "ihave_asked": DefaultMap(0), "held_back": {},
            "owed": lazy2(LazyBits), "owed_answers": lazy2(LazyBits),
            "park": lazy(lazy_dict), "gossip_history": GossipHistory(), "pace_queue": [],
            "pending": lazy(LazyList), "pending_ids": set(),
            "tied": tie_table(),                                          # root -> peer -> group -> indices
            "tie_slot": {},                                               # (root, peer) -> the slot its first copy named
            "mesh": set(), "now": 0.0,
        }
        self._seen = set()
        self._by_index = {}             # (group, index) -> set of ask keys, for closing promises
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

        def live(slot):
            return True                 # a run lasts one slot, well inside the live window

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

        bid_keys = {}                   # block root -> the key of the group its bid commits (§1)

        def bid_group(root):            # of an installed block only: before, the node has not seen its bid
            if root in node.blocks_waiting:
                raise AssertionError(f"bid_group of a block not installed at node {node.id} (--late-block)")
            if root not in bid_keys:
                b = node.sim.blocks[root]
                gid = b.body.signed_execution_payload_bid.message.execution_payload_segment_group_id
                bid_keys[root] = None if gid is None else ns["group_key"](gid, b.slot)   # a block of columns: none
            return bid_keys[root]

        def authenticable(g):           # a block installs at its publish, or later here (--late-block)
            return any(bid_group(root) == g for root in node.sim.blocks if root not in node.blocks_waiting)

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
            return ns["offers"].listed.get(p, 0)

        _room = (c.get("late_block") or (0, 0, 0))[2]    # --late-block: deferred copies kept per peer (§8.2)

        def reserve(p, f):              # the bounded store's reservation: a place for one more copy of p's
            if node.reserved[p] >= _room:
                node.late["refused"] += 1
                return False
            node.reserved[p] += 1
            node.late["kept"] += 1
            return True

        def release(p, f):
            node.reserved[p] -= 1

        def penalise(p):
            node.penalties += 1

        def handle_graft_prune(p, rpc):
            return []

        def enqueue(p, x, urgent=False):    # the queues here have no limit: every entry is admitted
            if node.sim.churn and p not in node.peers:
                return True             # --churn: the link is closed; what was for it ends with it (§3)
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
            return None if root in node.blocks_waiting else node.sim.blocks.get(root)

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

        # §6.1's own order: a keyed hash of the chunk and the peer id, under a secret of the node's. A real node
        # draws the secret at random; here it comes from the run's seed and the node's id, so that a run can be
        # made again, and another code base given the same seed and ids ranks the same peers the same way.
        own_secret = hashlib.sha256(b"own order" + (c["seed"] & (2 ** 64 - 1)).to_bytes(8, "little")
                                    + node.sim.peer_id(self.id)).digest()

        def own_order(xs, a):
            gi = group_index(a)
            chunk = gi.group + gi.index.to_bytes(4, "little")

            def rank(q):                # larger first, then the larger peer id, as §5.3's tie-break
                pid = node.sim.peer_id(q)
                return int.from_bytes(hmac.new(own_secret, chunk + pid, hashlib.sha256).digest()[:8], "little"), pid
            return sorted(xs, key=rank, reverse=True)

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
        offers, spec_close = ns["offers"], ns["close_promises"]

        def index_ask(a):               # the ask keys of an index, in either form, for close_promises
            gi = group_index(a)
            if gi is not None:
                self._by_index.setdefault((gi.group, gi.index), set()).add(a)

        def add_offer(a, p):            # and when the announcer last offered the group, for the 30 s
            was = a in offers and p in offers[a]
            spec_add_offer(a, p)
            if not was and a in offers and p in offers[a]:
                index_ask(a)            # a listed key; one only in `offered` has nothing to close
            self._offer_at[(p, ns["group"](a))] = ns["now"]

        def may_ask(a, p):              # an ask under a key no offer used (the ledger's) closes too
            ok = spec_may_ask(a, p)
            if ok:
                index_ask(a)
            return ok
        def close_promises(g, i, of=None):      # the document's (§6.1); the toy's index of a chunk's ask
            spec_close(g, i, of=of)             #   keys, which close_promises_of_group reads, goes with them
            if of is None:
                self._by_index.pop((g, i), None)
        ns["add_offer"], ns["may_ask"], ns["close_promises"] = add_offer, may_ask, close_promises
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

        def close_promises(g, i, of=None):
            q = sender[0]
            if q is not None and of is None:
                for a in self._by_index.get((g, i), ()):
                    at = ns["promises"].get((a, q))
                    if at is not None:                  # q answered our ask: one sample of its answer time
                        x = ns["now"] - at
                        if q not in srtt:
                            srtt[q], var[q] = x, x / 2
                        else:
                            var[q] = 0.75 * var[q] + 0.25 * abs(srtt[q] - x)
                            srtt[q] = 0.875 * srtt[q] + 0.125 * x
            return doc_close(g, i, of=of)

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
                  "HaveEntry", "PushEntry", "Join", "Have", "Want", "Graft", "Prune", "ChunkMsg", "BlockId"):
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
        prm.SYMMETRIC = bool(c.get("upkeep")) and c.get("symmetric", "on") == "on"   # §6.1: v0.3's mesh, kept as
        #   §4.1 keeps it under --upkeep on (--symmetric off: one-way); the recorded cells keep the mesh as built,
        #   where nodes at F_HI would otherwise be pruned at the first heartbeat
        prm.PRUNE_BACKOFF = c.get("prune_backoff", 0.0)      # §4.1 (--prune-backoff; 0: none)
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
            cprm.SYMMETRIC, cprm.PRUNE_BACKOFF = False, c.get("prune_backoff", 0.0)   # one-way, as measured
            cprm.ANNOUNCE_EXTRA, cprm.START_DELAY, cprm.SERVE_LIMIT, cprm.EVIDENCE = c.get("COL_ANNOUNCE", "ALL_JOINED"), 0.0, math.inf, None   # [D5]
            cprm.SAMPLE_RETRY = c.get("SAMPLE_RETRY", 2.0)
            cprm.SAMPLE_RETRY2, cprm.SAMPLE_OUTSTANDING = c.get("SAMPLE_RETRY2", 0.5), c.get("SAMPLE_OUTSTANDING", 4)   # [D12]
            cprm.SAMPLE_COVER, cprm.FORWARD_LIMIT = c.get("SAMPLE_COVER", 0), c.get("FORWARD_LIMIT", math.inf)   # [D12]
            cprm.COVER_HIGH = c.get("COVER_HIGH", 1)     # [D12] families a peer of high custody counts for in the floor
            cprm.ROUTE_HOPS = c.get("ROUTE_HOPS", 1)     # [D12] forwarding steps of a routed sample request
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
                rprm.SYMMETRIC, rprm.PRUNE_BACKOFF = False, c.get("prune_backoff", 0.0)
                rprm.ANNOUNCE_EXTRA, rprm.START_DELAY, rprm.EVIDENCE = c.get("ROW_ANNOUNCE", "ALL_JOINED"), c["ROW_DELAY"], None   # [D5]
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
                  grafted_out=AutoMap(lambda: AutoMap(lambda: AutoMap(set))),
                  grafted_in=AutoMap(lambda: AutoMap(lambda: AutoMap(set))), owed_relations=AutoMap(list),
                  backoff=AutoMap(lambda: AutoMap(lambda: AutoMap(dict))),
                  standing=AutoMap(lambda: AutoMap(set)),
                  claims=AutoMap(set), reconsider_at={}, deferred=DefaultMap(False), waited=DefaultMap(False), probe={}, probed={},
                  probe_asks=set(), probe_ok={}, probe_served=AutoMap(lambda: DefaultMap(False)),
                  probe_answers=AutoMap(lambda: AutoMap(Bits)), rsample=AutoMap(list), rsample_step=DefaultMap(0),
                  rsample_asked=AutoMap(lambda: AutoMap(set)), rsample_final=DefaultMap(False),
                  sampled_from=AutoMap(set), samples_in_flight=DefaultMap(0),
                  held_samples=AutoMap(list), forwarded=DefaultMap(0))   # [D12] §4.10's and §4.5's
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
            if not c.get("upkeep"):
                return node.peers                       # every peer joins every type of the setting
            return [q for q in node.peers if T in ns["join_recv"][q] and T in ns["join_sent"][q]   # §4.1, under
                    and not any(isinstance(m, Join) for m in ns["owed_relations"][q])]           #   --upkeep on

        def joined_types():
            return list(types.values())

        def joined_peers():
            if not c.get("upkeep"):
                return node.peers
            return [q for q in node.peers if ns["join_recv"].get(q) and ns["join_sent"].get(q)]   # --upkeep on

        def related(q):
            po, pi = ns["push_out"].get(q), ns["push_in"].get(q)
            return any(cols for m in (po, pi) if m for fams in m.values() for cols in fams.values())

        def node_id(p):
            return node.sim.peer_id(p)

        def in_pushers(T, fam, col):
            return [q for q in node.peers if col in ns["push_in"][q][T][fam]]

        def out_pushees(T, fam, col):
            return [q for q in node.peers if col in ns["push_out"][q][T][fam]]

        def candidates(T, fam, col, d):
            if not c.get("upkeep"):
                return []                               # the toy's topology is static, as for v0.3
            ds = ("IN", "OUT") if d == "BOTH" else (d,)        # --upkeep on: §3's candidates, joined peers with
            now, bo = ns["now"], ns["backoff"]                 #   duty whose interest holds the family, outside
            qs = [q for q in links(T) if ns["join_recv"][q][T].duty == "FORWARD"   #   the relation, no GRAFT of
                  and fam in link_cover(q, T).families                           #   ours unanswered, out of
                  and not any(col in (ns["push_in"] if x == "IN" else ns["push_out"])[q][T][fam]   # its backoff
                              or col in (ns["grafted_in"] if x == "IN" else ns["grafted_out"])[q][T][fam]
                              or bo[q][T][fam].get((col, x), 0.0) > now for x in ds)]
            if node._uprng is None:                     # its own draws: the run's generator is not touched
                node._uprng = random.Random(c["seed"] * 1000003 + node.id)
            node._uprng.shuffle(qs)
            return qs

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

        def sampled_types():                            # §4.8 [D12]: the toy's links are static, so the coverage floor,
            if not node.sampler or not types.get("column"):   # built with the graph
                return []                               #   (scenario.custody_topology), is checked once;
            if not c.get("upkeep"):                     #   under --upkeep on, at every heartbeat
                if node._cover_checked:
                    return []
                node._cover_checked = True
            return [types["column"]] if types["column"].params.SAMPLE_COVER > 0 else []

        def families(T):
            return range(scenario.NUMBER_OF_COLUMNS) if T.id == "column" else families_with_duty(T)

        def high_custody(q, T):                         # §1.3: above the base custody count (the toy's --cgc), or ALL
            j = ns["join_recv"][q].get(T)
            return j is not None and (j.interest == "ALL" or j.custody_count > c["cgc"])

        def link_cover(q, T):                           # §4.1: the families q serves, from its JOIN and node id alone
            r, j = Obj(), ns["join_recv"][q].get(T)
            r.high = high_custody(q, T)
            if j is None or j.interest == "DECLARED":
                r.families = []
            elif j.interest == "ALL" or T is P:
                r.families = list(families(T))
            elif T.id == "row":                         # a row member's derived interest: its row subnet
                r.families = [node.sim.row_subnet_of_id(node_id(q))]
            else:
                r.families = sorted(node.sim.custody_of_id(node_id(q), j.custody_count))
            return r

        def cover_candidates(T):                        # called only when keep_coverage finds a family short:
            node.cover_gaps += 1                        #   the graph's floor missed it (the toy opens no links)
            if not c.get("upkeep"):
                return []
            out, linked = [], set(node.peers)           # --upkeep on: §3's candidates, every node not linked,
            for u in sorted(node.sim.nodes):            #   with its custody from its id and count (the source and
                if u in linked or u in (node.id, 1) or node.sim.nodes[u].sampler:   # samplers apart, as the
                    continue                            #   graph's floor does)
                r = Obj()
                r.id, r.families = u, sorted(node.sim.custody[u])
                r.high = node.sim.custody_count.get(u, c["cgc"]) > c["cgc"]
                out.append(r)
            return out

        def open_sampling_link(r, T):
            if not c.get("upkeep"):
                raise AssertionError("the toy's links are static")
            node.cover_opened += 1                      # --upkeep on: connect; both ends' JOINs go (node.on_open)
            node.sim.open_link(node.id, r.id)

        def floor_links(T, fam):                        # §4.1: the peers connected, joined or not, whose custody
            if T is P:                                  #   holds fam; for columns the toy's custody, its proposer
                return list(node.peers)                 #   apart, as the graph's floor counts (scenario's)
            if T.id == "row":
                return [u for u in node.peers if node.sim.nodes[u].row_subnet == fam]
            return [u for u in node.peers if u != 1 and fam in node.sim.custody.get(u, ())]

        def floor_candidates(T):                        # §4.1: none unless --keep-floor on, and only for columns, as
            if not node.sim.keep_floor or T.id != "column" or node.id == 1:   # measured (the proposer keeps none,
                return []                               #   as the graph's floor gives it none)
            out, linked = [], set(node.peers)
            for u in sorted(node.sim.nodes):            # every custodian not linked, in id order: the floor's draw
                if u in linked or u in (node.id, 1) or not node.sim.custody.get(u):   # is sim.floor_rng's
                    continue
                r = Obj()
                r.id, r.families = u, sorted(node.sim.custody[u])
                out.append(r)
            return out

        def open_link(r, T):                            # §4.1: connect; both ends' JOINs go (node.on_open)
            node.sim.floor_log.append((node.sim.now, node.id, r.id, None))
            node.sim.open_link(node.id, r.id)

        def route_next(T, fam, qs):                     # [D12] no routing neighbours here: any of them
            return list(qs) if c.get("route", "on") == "on" else []   #   (--route off: no routed requests)

        def block_of(g):
            h = node.sim.ghdr.get(g)
            return h.block if h is not None and hasattr(h, "block") else g

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

        def group_of(block, h):                         # §1.1's table: a column's or row's header id names it
            g = ns["group_id"](h)                       #   (it holds the block's root); the payload's is the
            return g if g in node.sim.gtype else ns["group_key"](g, block.slot)    # key of v0.3 §1

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

        def send(p, msg, urgent=False):                 # the v0.3-wire binding (protocol-v2.md §7); true if the
            if isinstance(msg, Have):                   #   queue admitted it, as v0.5's enqueue
                hb = Wm.HaveBitmap(msg.group, msg.bits)
                if not msg.offer:                       # the two claims ride in the version byte (§7, last column)
                    hb.claim_all, hb.complete = msg.claim_all, msg.complete
                return ns["enqueue"](p, (Wm.IHAVE if msg.offer else Wm.IDONTWANT)(hb), urgent)
            elif isinstance(msg, Want):
                st, hp = getattr(msg, "standing", False), getattr(msg, "hops", 0)   # §2's fields [D12]
                pr = getattr(msg, "probe", False)       # and the probe's mark (R5)
                w = Wm.IWANT([Wm.FlaggedWant(msg.group, i, st, hp, pr) if st or hp or pr else Ask(msg.group, i)
                              for i in msg.bits])
                w.items[0].want = True                  # §4.5: a WANT starts no promise at its write
                if node.sampler:                        # the reach report: whom each sample was asked of, how
                    for i in msg.bits:
                        node.sample_log.setdefault((msg.group, i), []).append((p, hp > 0, ns["now"]))
                elif st and not node.alarming:          # only route_want sends a standing WANT from a non-sampler,
                    node.forwarded_out += 1             #   but for --alarm-wait's custodian
                return ns["enqueue"](p, w, urgent)
            elif isinstance(msg, (Graft, Prune, Join)):
                if not c.get("upkeep"):
                    return True                         # relations are static here; JOIN is the subscription
                node.relation_msgs[type(msg).__name__] += 1   # --upkeep on: on the wire, counted
                ctl = (Wm.JOIN if isinstance(msg, Join) else Wm.GRAFT if isinstance(msg, Graft) else Wm.PRUNE)([msg])
                return ns["enqueue"](p, ctl, urgent)
            else:
                return ns["enqueue"](p, msg, urgent)

        ns.update({k: v for k, v in locals().items() if callable(v) and not k.startswith("_")
                   and k not in ("c", "node", "ns", "Have", "Want", "Graft", "Prune", "Join", "Obj",
                                 "P", "prm", "COL", "cprm", "ROW", "rprm", "rows", "has_rows", "keeps_rows", "sim", "my_cgc", "interest_in",
                                 "own_row", "decode_later",
                                 "types", "joins", "InterestMap", "spec_open_group")})
        ns["Ask"] = Ask
        ns["chunk_id"] = chunk_id
        doc_keep_floor = ns["keep_floor"]

        def keep_floor(T):                              # §4.1's, drawing from sim.floor_rng, so that the run's
            draw = ns["sample_without_replacement"]     #   other draws stay as they were
            ns["sample_without_replacement"] = lambda xs, k: node.sim.floor_rng.sample(list(xs), k)
            try:
                doc_keep_floor(T)
            finally:
                ns["sample_without_replacement"] = draw
        ns["keep_floor"] = keep_floor
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
            for j in rpc.join:                          # --upkeep on: a JOIN first, as on the wire (§4.1)
                ns["on_join"](p, j)
            r = Obj()
            r.chunks, r.haves, r.asks = rpc.chunks, haves, list(rpc.iwant.ids)
            r.grafts, r.prunes = list(rpc.graft), [x for x in rpc.prune if hasattr(x, "family")]
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
                    why = None if node.sim.nodes[p].sampler or gi.standing else "not held"
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
        if self.sampler:                                # [D12] the reach report: who delivered each sample first
            doc_fill = ns["fill"]

            def fill(g, i, f, p):
                k = (g, i)
                if p is not None and k in node.sample_log and k not in node.sample_from \
                        and not (ns["received"][g].has(i) or ns["rebuilt"][g].has(i)):
                    node.sample_from[k] = (p, ns["now"])
                return doc_fill(g, i, f, p)
            ns["fill"] = fill
        doc_promise_due = ns["promise_due"]

        def promise_due(a, p, at):                      # the same name, so that events hash as before: records a
            if ns["promises"].get((a, p)) == at:        #   broken promise for the invariants (when, whom, which ask)
                gi = ns["group_index"](a)
                if gi is not None:
                    node.broken.append((ns["now"], at, p, gi.group, gi.index))
            return doc_promise_due(a, p, at)
        ns["promise_due"] = promise_due
        prng = random.Random(f"probe-index/{c['seed']}/{node.id}")   # (R5) the probed index's draw on a stream of
        doc_defer = ns["defer_on_claim"]                #   its own, seeded by the run's seed and the node, so that it
                                                        #   moves no other draw (as sim.floor_rng for keep_floor)
        def defer_on_claim(g):                          # the same name; the document draws the index first, then
            spec_choice, drawn = ns["choice"], []       #   the claimant: only that first choice is this stream's

            def choice(xs):
                if drawn:
                    return spec_choice(xs)
                drawn.append(1)
                xs = list(xs)
                return xs[prng.randrange(len(xs))]
            ns["choice"] = choice
            try:
                return doc_defer(g)
            finally:
                ns["choice"] = spec_choice
        ns["defer_on_claim"] = defer_on_claim
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
            self._doc_push_rebuilt = ns["push_rebuilt"] #   (--fault hoardcol: the document's, but for one column)
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
        if self.cfg.get("upkeep") and self.id != 1 and 1 in self.peers:   # --upkeep on: the proposer's fanout
            for col in self.custody:                    #   holds a relation with every custodian it links to; the
                ns["push_out"][1][COL][col].add(0)      #   custodian holds it too, so both ends agree (§4.1)
                ns["push_in"][1][COL][col].add(0)
            union.add(1)
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

    def install_block(self, root):
        """--late-block: the block installs here now, and what waited for it resumes (protocol.md §4.2)."""
        self.blocks_waiting.discard(root)
        self.late["ties released"] += sum(len(list(bits)) for groups in self.ns["tied"].get(root, {}).values()
                                          for bits in groups.values())
        self.ns["on_block_installed"](root)

    def expire_offers(self, now):
        """§8.1: an announcer's offers of a group go 30 s after its last one (the ordered lists and
        `offered`), checked at each heartbeat, so an offer can outlive its 30 s by up to one, and
        its asks of those indices go with them (§6.1's `drop_offer`: an ask still queued to it is
        removed, and its promise for the index closes). A group's diffusion takes well under that,
        so what goes here is what a group that completed by decoding left behind; it matters for
        `listed` alone."""
        ns, old = self.ns, now - OFFER_TTL
        gone = [k for k, t in self._offer_at.items() if t < old]
        for p, g in gone:
            del self._offer_at[(p, g)]
            bits = ns["offered"][p].pop(g, None)
            idx = set(bits) if bits is not None else set()
            empty = []
            for a, lst in ns["offers"].items():
                if p in lst and ns["group"](a) == g:
                    lst.remove(p)
                    idx.add(ns["index"](a))
                    if not lst:
                        empty.append(a)
            for a in empty:
                del ns["offers"][a]
            dropped = lambda a: ns["group"](a) == g and ns["index"](a) in idx
            q = ns["queue"].get(p)
            if q is not None:
                for e in q.normal:
                    for m in e.iwants():
                        m.ids = [a for a in m.ids if not dropped(a)]
                q.normal = [e for e in q.normal if not e.is_empty()]
            for k in [k for k in ns["promises"] if k[1] == p and dropped(k[0])]:
                del ns["promises"][k]

    # ---- the writer: one per peer (§7.2)

    def kick(self, p):
        if p not in self.writer_kicked:
            self.writer_kicked.add(p)
            self.sim.after(self, 0.0, self._write, p)

    def drop_peer(self, q):
        """--churn: protocol-v2.md §3's lifetimes at a close (sim.close_link). Per-peer entries, the
        relations, our unanswered GRAFTs and anything owed end; asks and promises to q stay, so their
        timers treat q as a silent peer (v0.3 §6.1)."""
        ns = self.ns
        for name in ("join_recv", "join_sent", "push_out", "push_in", "grafted_out", "grafted_in",
                     "owed_relations", "backoff", "peer_has", "pushed", "sent_to", "served", "want_p", "forwarded",
                     "park", "queue"):
            m = ns.get(name)
            if m is not None and q in m:
                del m[q]
        for name in ("holders", "standing"):
            for idx in ns[name].values():
                for s in idx.values():
                    s.discard(q)
        if isinstance(ns.get("mesh"), set):
            ns["mesh"].discard(q)
        pq = ns.get("pace_queue")                   # paced gossip queued for q goes with the link
        if pq:
            kept = [x for x in pq if x[0] != q]
            pq.clear()
            pq.extend(kept)
        self.writer_blocked.discard(q)

    def on_open(self, q):
        """--churn: a link opened (sim.open_link); each type's JOIN goes, once (§4.1 send_join)."""
        ns = self.ns
        for T in ns["joined_types"]():
            if T not in ns["join_sent"][q]:
                ns["send_join"](q, ns["our_join"](T))

    def _write(self, p):
        self.writer_kicked.discard(p)
        if self.sim.churn and p not in self.peers:
            return                                  # --churn: the link closed after the kick
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
