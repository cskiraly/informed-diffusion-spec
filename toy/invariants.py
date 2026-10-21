"""The invariants every setting of protocol-v2.md must keep, checked on a run.

protocol-v2.md §6.2 names them: every node completes its
interest given a publishing source; no chunk is pushed to a link whose interest excludes it (I3);
each node's upload stays within the duty bounds; a claim whose probe goes unanswered is detected; a cell
arriving on one axis fills both groups (R4); and the tier 4 setting reproduces v0.3's cells
(check.py --doc v2 --golden golden.txt). This module checks the first three on every run of run.py --doc v2 and the
fourth and fifth under the row setting, where deferral and cross-fill exist, and reports them after
the run's results. It also reports how long each class of queue entry waited before it was sent,
what the asks experienced (from the first ask to the chunk, matched on either axis, who delivered it,
broken promises and how much later the asked node's answer came, asks it left unanswered and why)
and the duplicates on arrival by class, which is what protocol-v2.md §4.12's ANSWERS_FIRST acts on. The
checker observes the queues (the time an entry was queued), the links (Sim.transmit, Sim._deliver)
and the nodes' state; it schedules nothing, so a run's digest is the same with it or without it.
"""
import statistics as st
from collections import Counter, defaultdict

import wire as Wm
from bits import popcount


class Checker:
    def __init__(self, sim):
        self.sim = sim
        self.outside = []           # (t, sender, receiver, group, index, solicited): a chunk into no interest
        self.offers_outside = 0     # offer bits for indices the receiver does not want (waste, not a violation)
        self.eager = Counter()      # (sender, group, index) -> eager pushes of a chunk it received
        self.origin = Counter()     # the same, for a chunk the sender held from the start (a source)
        self.repair = Counter()     # the same, for a chunk the sender rebuilt
        self.answers = Counter()    # the same, answers to asks
        self.to_samplers = Counter()    # sender -> chunks answered to samplers (their serving load, §4.10)
        self.wait = defaultdict(list)   # class -> seconds from queued to handed to the transport
        self.trip = defaultdict(list)   # class -> seconds from handed to the transport to delivered
        self.in_flight = {}             # id(entry) -> (class, handed over at): entries on the links
        self.asked = {}                 # (asker, group, index) -> when its first ask was queued
        self.asks_sent = 0              # ask ids handed to the transport, re-asks included
        self.ask_rtt = []               # first ask queued -> the chunk delivered, from anyone
        self.ask_from = Counter()       # who delivered an asked chunk first: "asked" peer or "other"
        self.dup = Counter()            # class -> chunks delivered to a node that already held them
        self.repair_to = Counter()      # (keeper or other, useful / dup / dup-own) -> rebuilt chunks delivered
        self.answered = {}              # (asker, server, group, index) -> first answer's arrival, both axes

    def klass(self, node, e):
        """What an entry is, for the queue report: urgent, answer, push, origin, repair, ask, offer, control."""
        if e.urgent:
            return "urgent"
        f = e.chunk
        if f is not None:
            if e.solicited:
                return "answer" if node.ns["received"][f.group].has(f.index) or node.id != 1 else "answer@source"
            rb = node.ns.get("rebuilt")
            if rb is not None and rb[f.group].has(f.index):
                return "repair"
            return "push" if node.ns["received"][f.group].has(f.index) else "origin"
        kinds = {m.kind for m in e.control.items if not m.empty()} if e.control else set()
        return "ask" if "iwant" in kinds else "offer" if "ihave" in kinds else "control"

    def transmit(self, node, p, e):
        rcv = self.sim.nodes[p]
        k = self.klass(node, e)
        now = self.sim.now
        if e.at is not None:
            self.wait[k].append(now - e.at)
        self.in_flight[id(e)] = (k, now, p)
        for m in e.iwants():
            for a in m.ids:
                if hasattr(a, "group"):
                    self.asks_sent += 1
                    self.asked.setdefault((node.id, a.group, a.index), (e.at if e.at is not None else now, p))
        f = e.chunk
        if f is not None:
            g, i = f.group, f.index
            if not rcv.wants(g, i) and not self.wants_other_axis(rcv, f):
                self.outside.append((self.sim.now, node.id, p, g, i, e.solicited))
            key = (node.id, g, i)
            if rcv.sampler:
                self.to_samplers[node.id] += 1
            if e.solicited:
                self.answers[key] += 1
            else:
                rb = node.ns.get("rebuilt")
                if rb is not None and rb[g].has(i):
                    self.repair[key] += 1
                elif not node.ns["received"][g].has(i):
                    self.origin[key] += 1       # held from the start: the source of the group
                else:
                    self.eager[key] += 1
        if e.control:
            for m in e.control.items:
                if m.kind == "ihave":
                    for hb in m.ids:
                        if isinstance(hb, Wm.HaveBitmap):
                            self.offers_outside += sum(1 for i in hb.bits if not rcv.wants(hb.group, i))

    def deliver(self, src, dst, e):
        """An entry's last byte is at dst, before dst handles it."""
        k, tx, _ = self.in_flight.pop(id(e), (None, None, None))
        if k is not None:
            self.trip[k].append(self.sim.now - tx)
        f = e.chunk
        if f is None:
            return
        ns = self.sim.nodes[dst].ns
        r, rb = ns["received"].get(f.group), ns["rebuilt"].get(f.group) if "rebuilt" in ns else None
        held = (r is not None and r.has(f.index)) or (rb is not None and rb.has(f.index))
        if held:
            self.dup[k] += 1
        if k == "repair":                               # a node that custodies every column keeps every row
            who = "keeper" if self.sim.custody_count.get(dst, 0) >= 128 else "other"
            self.repair_to[(who, "dup" if held else "useful")] += 1
            if held and rb is not None and rb.has(f.index):
                self.repair_to[(who, "dup-own")] += 1
        keys = [(f.group, f.index)]                     # an ask names the cell on its row or on its column (R4)
        g_row = self.sim.grow.get((f.descriptor.block, f.index)) if self.sim.grow and f.group in self.sim.gcol else None
        if g_row is not None:
            keys.append((g_row, self.sim.gcol[f.group]))
        for g, i in keys:
            if e.solicited:
                self.answered.setdefault((dst, src, g, i), self.sim.now)
            a = self.asked.pop((dst, g, i), None)
            if a is not None:
                self.ask_rtt.append(self.sim.now - a[0])
                self.ask_from["asked" if a[1] == src else "other"] += 1

    def wants_other_axis(self, rcv, f):
        """(R4) a cell pushed for its row: the receiver's interest in the row group, if any."""
        sim = self.sim
        if not sim.grow:
            return False
        g_row = sim.grow.get((f.descriptor.block, f.index))
        return g_row is not None and rcv.wants(g_row, sim.gcol[f.group])

    # ---- the report

    def over_budget(self):
        """Eager pushes of one chunk by one node above its budget: R_NODE for a forwarding node, R at a source."""
        nodes, bad = self.sim.nodes, []
        for (s, g, i), n in self.eager.items():
            if n > nodes[s].ns["R_NODE"]:
                bad.append((s, g, i, n, nodes[s].ns["R_NODE"]))
        for (s, g, i), n in self.origin.items():
            if n > nodes[s].ns["R"]:
                bad.append((s, g, i, n, nodes[s].ns["R"]))
        return bad

    def upload(self):
        """Per class: median and maximum upload in units of the node's own interest, and the duty
        spread (max over median); the source apart."""
        sim = self.sim
        by_class, msgs = {}, max(1, len(sim.msgs))
        for i, nd in sim.nodes.items():
            if i == 1:
                continue
            unit = sim.unit(i)
            if not unit:
                continue
            by_class.setdefault(nd.cls["up"], []).append(nd.tx_data / unit / msgs)
        out = []
        for up, xs in sorted(by_class.items()):
            med = st.median(xs)
            out.append((up, len(xs), med, max(xs), (max(xs) / med) if med else float("inf")))
        return out

    def report(self, out):
        sim = self.sim
        n_chunks = sum(len(fr) for fr in sim.canonical.values())
        print(f"invariants: {n_chunks} chunks published, {sum(self.eager.values())} eager pushes, "
              f"{sum(self.origin.values())} from the source, {sum(self.repair.values())} repair, "
              f"{sum(self.answers.values())} answers", file=out)
        if self.outside:
            t, s, p, g, i, sol = self.outside[0]
            print(f"  VIOLATION I3: {len(self.outside)} chunks pushed outside the receiver's interest; "
                  f"first at {t*1000:.0f}ms {s}->{p} group {g[:4].hex()} index {i}"
                  f"{' (an answer)' if sol else ''}", file=out)
        else:
            print("  I3: no chunk pushed outside the receiver's interest", file=out)
        print(f"  offers for unwanted indices: {self.offers_outside}", file=out)
        bad = self.over_budget()
        if bad:
            s, g, i, n, b = bad[0]
            print(f"  VIOLATION duty: {len(bad)} (node, chunk) pairs pushed above budget; first: node {s} "
                  f"pushed group {g[:4].hex()} index {i} {n} times, budget {b}", file=out)
        else:
            print("  duty: no node pushed a chunk it received more than R_NODE times, nor a source more than R", file=out)
        if self.repair:
            print(f"  repair: {len(self.repair)} (node, chunk) pairs, at most {max(self.repair.values())} copies of one chunk", file=out)
            rt = self.repair_to
            print(f"  repair deliveries: to nodes keeping every row {rt[('keeper', 'useful')]} useful, {rt[('keeper', 'dup')]} duplicate "
                  f"({rt[('keeper', 'dup-own')]} it had rebuilt itself); to the others {rt[('other', 'useful')]} useful, "
                  f"{rt[('other', 'dup')]} duplicate ({rt[('other', 'dup-own')]} rebuilt there)", file=out)
        for up, n, med, mx, spread in self.upload():
            print(f"  upload per message, {n} nodes at {up/1e6:.0f} Mbps: median {med:.2f}, max {mx:.2f} of own interest; spread {spread:.1f}", file=out)
        src = sim.nodes[1]
        if sim.msgs:
            whole = sum(Wm.chunk_wire(f) for g in sim.msgs[0][1] if g in sim.canonical for f in sim.canonical[g].values())
            print(f"  the source uploaded {src.tx_data / whole / len(sim.msgs):.1f} copies of the message's chunks per message", file=out)
        rowset = set(sim.grow.values())
        if rowset:                                              # rows: cross-fill (R4), the decodes, claims (R5)
            mism, held_rows = 0, 0
            for i, nd in sim.nodes.items():
                if i == 1:
                    continue                                    # the source stores what it published, by column only
                chunks, kept = nd.ns["chunks"], nd.ns["T_of"]
                for g, fr in chunks.items():
                    if g in rowset:                             # a row group: each cell must sit in its column group too
                        for col, f in fr.items():
                            held_rows += 1
                            if chunks.get(f.group, {}).get(f.index) is not f:
                                mism += 1
                    elif g in sim.gcol:                         # a column group: each cell must sit in its row group too,
                        for b, f in fr.items():                 #   at a node that keeps rows
                            g_row = sim.grow.get((f.descriptor.block, b))
                            if g_row is not None and g_row in kept and chunks.get(g_row, {}).get(sim.gcol[g]) is not f:
                                mism += 1
            print(f"  {'VIOLATION ' if mism else ''}cross-fill (R4): {held_rows} row cells held, {mism} not mirrored in the other axis", file=out)
            at_k = later = phase2 = deferred = verified = rearmed = anyway = 0
            for nd in sim.nodes.values():
                ns = nd.ns
                for g in rowset:
                    if ns["rebuilt"].get(g):
                        if nd.row_subnet is None or sim.gsub.get(g) != nd.row_subnet:
                            phase2 += 1                         # a supernode's row of another subnet, or under custody alone
                        elif nd.reconstructor:
                            at_k += 1
                        else:
                            later += 1
                    if ns["deferred"].get(g):
                        deferred += 1
                        if ns["received"][g].has(ns["probe"][g]):
                            verified += 1
                            if ns["rebuilt"].get(g):
                                anyway += 1             # (R5) verified, and the row still short when the window ran out
                        else:
                            rearmed += 1
            liars = sum(1 for nd in sim.nodes.values() if nd.liar)
            supers = sum(1 for nd in sim.nodes.values() if nd.supernode)
            if sim.gsub:
                print(f"  rows: {at_k} decoded at K by reconstructors, {later} later by members"
                      f"{f', {phase2} in the second phase by {supers} supernodes' if supers else ''}; {deferred} duties deferred on a claim, "
                      f"{verified} claims verified by the probe ({anyway} rebuilt anyway), {rearmed} re-armed with the claimants penalised"
                      f"{f' ({liars} liars)' if liars else ''}; the repair floor added {getattr(sim, 'repair_links', 0)} links", file=out)
            else:
                print(f"  reconstruction: {phase2} rows rebuilt by {supers} supernodes; {deferred} duties deferred on a claim, "
                      f"{verified} verified by the probe ({anyway} rebuilt anyway), {rearmed} re-armed", file=out)
            checks = sum(nd.member_checks for nd in sim.nodes.values())
            if checks:
                print(f"  member check: {checks} verified claims not taken, the row's cells in the member's custody columns "
                      f"missing", file=out)
            rv = Counter()
            for nd in sim.nodes.values():
                rv.update(nd.repair_verdicts)
            if rv:
                asked = sum(len(v) for nd in sim.nodes.values() for v in nd.ns["rsample"].values())
                reasks = sum(len(qs) - 1 for nd in sim.nodes.values() for d in nd.ns["rsample_asked"].values()
                             for qs in d.values() if qs)
                print(f"  repair sample: {asked} cells asked of custodians, {reasks} re-asked of another; verdicts " + ", ".join(
                      f"{v.lower()} after step {k}: {n}" for (v, k), n in sorted(rv.items())), file=out)
            hoarders = [nd for nd in sim.nodes.values() if nd.hoarder]
            if hoarders:
                hrows = sum(1 for nd in hoarders for g in rowset if nd.ns["rebuilt"].get(g))
                print(f"  hoarders: {len(hoarders)} ({sum(nd.supernode for nd in hoarders)} supernodes, "
                      f"{sum(nd.reconstructor and not nd.supernode for nd in hoarders)} row reconstructors), {hrows} rows rebuilt by them; "
                      f"asks for their rebuilt cells: {sum(nd.hoard_served for nd in hoarders)} answered (probes), "
                      f"{sum(nd.hoard_refused for nd in hoarders)} refused", file=out)
        samplers = [nd for nd in sim.nodes.values() if nd.sampler]
        if samplers:
            declared = sum(popcount(b) for nd in samplers for b in nd.samples.values())
            unreach = sum(popcount(b) for nd in samplers for b in nd.unreachable.values())
            loads = sorted(self.to_samplers.get(i, 0) for i, nd in sim.nodes.items() if not nd.sampler and i != 1)
            print(f"  sampling: {len(samplers)} samplers, {declared} samples declared and {unreach} unreachable "
                  f"(no link custodies the column, or every one that does was parked); "
                  f"chunks to samplers per custodian: median {st.median(loads) if loads else 0:.0f}, "
                  f"max {loads[-1] if loads else 0}; from the proposer {self.to_samplers.get(1, 0)}", file=out)
        self.report_queue(out)
        incomplete = sim.incomplete()
        if incomplete:
            print(f"  VIOLATION completion: {len(incomplete)} (node, group) pairs never completed; "
                  f"first: node {incomplete[0][0]} group {incomplete[0][1][:4].hex()}", file=out)
        else:
            print("  completion: every node completed its interest", file=out)
        return not (self.outside or bad or incomplete)

    def report_queue(self, out):
        """How long each class of entry waits in its peer's queue, and what the asks experience."""
        def ms(xs, q):
            xs = sorted(xs)
            return xs[min(len(xs) - 1, int(q * len(xs)))] * 1000 if xs else 0.0
        order = ("urgent", "ask", "offer", "control", "answer", "answer@source", "push", "origin", "repair")
        parts = [f"{k} {ms(self.wait[k], .5):.0f}/{ms(self.wait[k], .99):.0f}/{ms(self.wait[k], 1):.0f} ({len(self.wait[k])})"
                 for k in order if self.wait[k]]
        print(f"  queue, ms queued to sent p50/p99/max (entries): {', '.join(parts)}", file=out)
        parts = [f"{k} {ms(self.trip[k], .5):.0f}/{ms(self.trip[k], .99):.0f}" for k in order if self.trip[k]]
        print(f"  link, ms sent to delivered p50/p99: {', '.join(parts)}", file=out)
        parks = sum(len(v) for nd in self.sim.nodes.values() for v in nd.ns["park"].values())
        refused = Counter()
        for nd in self.sim.nodes.values():
            refused.update(getattr(nd, "refused", {}))
        if refused:
            print(f"  asks left unanswered by the asked node: {', '.join(f'{t} {w} {n}' for (t, w), n in sorted(refused.items()))}", file=out)
        late, never, by_type = [], 0, Counter()
        for i, nd in self.sim.nodes.items():
            for t, at, p, g, idx in getattr(nd, "broken", ()):
                by_type[self.sim.gtype.get(g, "payload")] += 1
                ta = self.answered.get((i, p, g, idx))
                if ta is not None and ta >= t:
                    late.append(ta - at)
                else:
                    never += 1
        if by_type:
            print(f"  broken promises: {sum(by_type.values())} ({', '.join(f'{k} {v}' for k, v in sorted(by_type.items()))}); "
                  f"the asked node's answer came later in {len(late)}, from the ask p50 {ms(late, .5):.0f} ms, p99 {ms(late, .99):.0f} ms; "
                  f"no answer from it {never}", file=out)
        n = len(self.ask_rtt) + len(self.asked)
        print(f"  asks: {n} chunks asked for ({self.asks_sent} asks sent), first ask to the chunk p50 "
              f"{ms(self.ask_rtt, .5):.0f} ms, p99 {ms(self.ask_rtt, .99):.0f} ms; delivered first by the asked peer "
              f"{self.ask_from['asked']}, by another {self.ask_from['other']}, never {len(self.asked)}; "
              f"{parks} (peer, group) parked on a broken promise; duplicates on arrival: "
              f"{', '.join(f'{k} {self.dup[k]}' for k in order if self.dup[k]) or 'none'}", file=out)
