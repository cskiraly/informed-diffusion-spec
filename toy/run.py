#!/usr/bin/env python3
"""Run the pseudocode on a toy network and print what the harness prints.

    python3 run.py [--net home|dc20|dcb20|bld] [--seed 7] [--nodes 500] [--msgs 6]
                   [--without 8,9,...] [--check-ms 5] [--rebuilt push|hold|announce|none]
                   [--latency-only] [--digest]

A cell publishes `msgs` payloads 12 s apart on one standing network, as the harness's MSGS=6
cells do; message 1 is cold, messages 2.. are warm. For each message it prints the receivers'
p50 and p99 completion time (the K-th distinct chunk, from the publish instant, nearest rank) and
what each node received, in copies of the compressed payload (746262 bytes at 1 MiB): data (the
chunks' bytes) and control, as the harness's rx/node and ctrl rx/node.
"""
import argparse
import math
import re
import statistics as st
import sys
import time
from collections import Counter

import scenario
import xcheck
from sim import Sim

CFG = {
    # §8.3, and the harness's operating point
    "R": 2, "R_FAST": 6, "FAST_UPLINK": 500e6, "STRIPE_UPLINK": 1e9,
    "IWANT_WINDOW": 0.200, "RETRY_SLACK": 0.005, "PROMISE": 0.400, "PARK_TTL": 30.0, "GUARD_GRACE": 0.200, "FAN_IN": 2,
    "RTT_REF": 0.112, "TARGET": 0.020, "CHUNK_BYTES": 12000, "WINDOW_TIMEOUT": 0.500,
    "HEARTBEAT": 0.700, "D_LAZY": 6, "GOSSIP_FACTOR": 0.25, "GOSSIP_RETRANSMISSION": 3,
    "HAVE_TTL": 3, "PUSH_TTL": 6, "window_scale": 1.0,
    "D": 8, "degree": 70, "nodes": 500, "payload": 1 << 20, "COMPRESSION": (1 << 20) / 746262,
    "COMPRESSED": 746262, "CHECK_TIME": 0.005, "heartbeat_phase": 0.100,
    "msgs": 6, "gap": 12.0, "first": 3.0, "seed": 7,
    **{f"card{k}": True for k in range(1, 18)},
}


def latency_summary(pair, n):
    """The harness's log line: the same deterministic sample of pairs (geo.go)."""
    s = sorted(pair(i + 1, (i + k * 7919) % n + 1) for i in range(n) for k in (1, 2, 3))
    q = lambda f: s[int(f * (len(s) - 1))] * 1000
    return (f"one-way mean {round(sum(s) / len(s) * 1000)}ms, p10 {round(q(.1))}ms, "
            f"p50 {round(q(.5))}ms, p90 {round(q(.9))}ms over {len(s)} sampled pairs")


def run(cfg, out=sys.stdout):
    t0 = time.time()
    sim = Sim(cfg)
    print(f"latency model geo: {latency_summary(sim.lat, cfg['nodes'])}", file=out)
    rec = None
    if cfg.get("xcheck"):
        rec = sim.recorder = xcheck.Recorder(sim)
        for i, toy, harness in rec.degree_mismatches(cfg.get("xc_degree")):
            print(f"xcheck: node {i} pushes at {toy} here, {harness} in the harness", file=out)
    rows, snaps = [], []
    for m in range(1, cfg["msgs"] + 1):
        at = cfg["first"] + (m - 1) * cfg["gap"]
        sim.run(at)
        snaps.append({i: (nd.rx_data, nd.rx_ctrl) for i, nd in sim.nodes.items()})
        sim.publish(m)
        if rec is not None:             # read at the horizon; run() in two steps processes the same events
            sim.run(at + rec.horizon)
            rec.take(m)
    sim.run(cfg["first"] + cfg["msgs"] * cfg["gap"])
    snaps.append({i: (nd.rx_data, nd.rx_ctrl) for i, nd in sim.nodes.items()})
    units = {i: sim.unit(i) for i in sim.nodes}            # bytes of one node's interest: the payload, or its columns
    nodes = [i for i in sim.nodes if units[i]]
    label = "block" if sim.custody else "msg"
    for r, (a, b) in zip(sim.results(), zip(snaps, snaps[1:])):
        data = sum((b[i][0] - a[i][0]) / units[i] for i in nodes) / len(nodes)
        ctrl = sum((b[i][1] - a[i][1]) / units[i] for i in nodes) / len(nodes)
        r.update(data=data, ctrl=ctrl, copies=data + ctrl)
        rows.append(r)
        print(f"{label} {r['msg']}: p50 {r['p50']*1000:.0f}ms p99 {r['p99']*1000:.0f}ms "
              f"max {r['max']*1000:.0f}ms missing {r['missing']}  "
              f"copies {r['copies']:.2f} (data {data:.2f}, control {ctrl:.3f})", file=out)
        s = r.get("samplers")
        if s:
            print(f"  samples {r['msg']}: {s['nodes']} samplers, p50 {s['p50']*1000:.0f}ms p99 {s['p99']*1000:.0f}ms "
                  f"max {s['max']*1000:.0f}ms missing {s['missing']} unreachable {s['unreachable']}; "
                  f"the samples that arrived p50 {s['arrived_p50']*1000:.0f}ms p99 {s['arrived_p99']*1000:.0f}ms", file=out)
        s = r.get("rows")
        if s:
            print(f"  rows {r['msg']}: {s['nodes']} members at 64 cells, p50 {s['p50']*1000:.0f}ms p99 {s['p99']*1000:.0f}ms "
                  f"max {s['max']*1000:.0f}ms missing {s['missing']}", file=out)
        for line in (rec.lines.get(r["msg"], []) if rec is not None else []):
            print(f"  {line}", file=out)
    warm = rows[1:] or rows
    summary = {k: st.median(r[k] for r in warm) for k in ("p50", "p99", "copies", "data", "ctrl")}
    print(f"warm median: p50 {summary['p50']*1000:.0f}ms p99 {summary['p99']*1000:.0f}ms "
          f"copies {summary['copies']:.2f}  [{sim.events} events, {time.time()-t0:.0f}s]", file=out)
    if sim.inv is not None:
        sim.inv.report(out)
    if cfg.get("MAX_IHAVE_MESSAGES", math.inf) < math.inf or cfg.get("MAX_IHAVE_LENGTH", math.inf) < math.inf:
        held = sum(nd.held_back for nd in sim.nodes.values())
        print(f"  ihave limits: {held} asks held back to the next heartbeat", file=out)
    if cfg.get("late_block"):                   # --late-block: what §4.2's deferral did
        tot = sum((nd.late for nd in sim.nodes.values()), Counter())
        print(f"  late blocks: at {len(cfg['late_nodes'])} nodes, {cfg['late_block'][1] * 1000:g} ms after the publish; "
              f"deferred copies kept {tot['kept']}, refused {tot['refused']}; ties released {tot['ties released']}", file=out)
        left = [sum(len(v) for v in nd.ns["pending"].values()) + len(nd.ns["pending_ids"]) + len(nd.ns["tied"])
                + len(nd.ns["tie_slot"]) + sum(nd.reserved.values()) + len(nd.blocks_waiting)
                for nd in sim.nodes.values()]
        print(f"  late blocks: left at the end (copies waiting, their ids, ties and their slots, reservations, blocks "
              f"not installed): "
              f"{sum(left)}{'' if not sum(left) else '  <-- something still waits'}", file=out)
        missing = sum(r["missing"] for r in rows)      # the cell's two claims, checked: nothing waits at the end,
        if sum(left) or missing:                        #   and every node completes every payload
            cfg["failed"] = (f"--late-block: {sum(left)} entries still wait at the end, "
                             f"{missing} payloads missing at their nodes")
    if cfg.get("upkeep"):                       # --upkeep on: protocol-v2.md §4.1's messages on the wire
        tot = sum((nd.relation_msgs for nd in sim.nodes.values()), Counter())
        print(f"  upkeep: {tot['Join']} JOINs, {tot['Graft']} GRAFTs, {tot['Prune']} PRUNEs sent; the coverage floor "
              f"short {sum(nd.cover_gaps for nd in sim.nodes.values())} times, "
              f"{sum(nd.cover_opened for nd in sim.nodes.values())} sampling-only links opened", file=out)
    if cfg.get("churn"):
        print(f"  churn: {len(sim.churn_log)} link replacements; {sim.churn_dropped} entries dropped on closed links",
              file=out)
    if cfg.get("keep_floor"):
        print(f"  keep-floor: {len(sim.floor_log)} links opened to custodians of a column below the floor of "
              f"{cfg['F_LO']}, by {len({x for _, x, _, _ in sim.floor_log})} nodes", file=out)
    if cfg.get("ALARM_WAIT"):                   # each count against its bound
        tot = Counter()
        for nd in sim.nodes.values():
            tot.update(nd.alarm)
        cells = sum(len(nd.alarm_cells) for nd in sim.nodes.values())
        got = sum(1 for nd in sim.nodes.values() for (g, b) in nd.alarm_cells
                  if nd.ns["received"][g].has(b) or nd.ns["rebuilt"][g].has(b))
        print(f"  alarm: {tot['sent']} sent by {sum(1 for nd in sim.nodes.values() if nd.alarm_cells)} custodians for "
              f"{cells} cells (at most {cells * cfg['ALARM_MAX']}), {got} of the cells held at the end; members kept "
              f"{tot['kept']} as standing asks, {tot['answered']} answered, {tot['held at once']} answered at once "
              f"(held), {tot['alarms refused by a hoarder']} refused by a hoarder; {tot['asks of a claimant']} asks of a claimant "
              f"(at most {tot['kept']}), {tot['broken']} broken, {tot['rebuilds']} rebuilds on an alarm; "
              f"{tot['no member left']} cells with no member left to ask", file=out)
    if cfg.get("hoard_column"):                 # the fault's known answer: per block, the custodians of each row's hidden
        tot = Counter()                         #   column but the row's rebuilders, where no honest node rebuilt the row
        for nd in sim.nodes.values():
            tot.update(nd.alarm)
        faulty = cfg["faulty"]
        for k, ((_, groups), pub) in enumerate(zip(sim.msgs, sim.pubs)):
            short, hidden, honest = set(), 0, 0
            for rg in (g for g in groups if sim.gtype.get(g) == "row"):
                x = sim.hoard_x.get(sim.gsub.get(rg))
                if x is None:
                    continue
                hidden += 1
                if any(nd.ns["rebuilt"].get(rg) for i, nd in sim.nodes.items() if i not in faulty):
                    honest += 1
                    continue
                short |= {i for i, nd in sim.nodes.items()
                          if i != pub and x in nd.custody and not nd.ns["rebuilt"].get(rg)}
            print(f"  hoardcol block {k + 1}: {hidden} rows with a hidden column, {honest} rebuilt by an honest node; "
                  f"{len(short)} custodians of the others' hidden columns, not rebuilders", file=out)
        print(f"  hoardcol: {tot['probe at the hidden index']} probes at a hidden index, {tot['hidden refused']} asks "
              f"for a hidden cell refused; {sum(1 for x in sim.hoard_x.values() if x is None)} subnets with no column "
              f"to hide", file=out)
    if cfg.get("MERGE_HOLDINGS"):
        merged, sent = (sum(nd.merged[k] for nd in sim.nodes.values()) for k in (0, 1))
        print(f"  merged holdings: {merged} of {sent} holdings of published groups went into one still queued", file=out)
    if sim.digest is not None:
        print(f"digest {sim.digest.hexdigest()}", file=out)
    return summary, rows


FAULT = r"(wh|sil|claim|hoardcol|hoardm|hoard)(\d+)"       # sim.py's --fault kinds


def das_dump(ap, a, argv, cfg, topo):
    """A DAS dump (xcheck.apply_das) under --doc v2 --setting custody or rows. The flags whose values the
    dump gives are refused; a running cell's blocks give --withhold and cap --msgs; --fault, if given,
    names the behaviour of the dump's faulty set, whose draw the toy's must equal (both are the harness's
    failSelect), and without it that set withholds or is silent, as the dump says. The header prints the
    dump's values. Returns the notes worth printing."""
    given = lambda flag: any(x == flag or x.startswith(flag + "=") for x in argv)
    if a.doc != "v2" or a.setting not in ("custody", "rows"):
        ap.error("a DAS dump runs under --doc v2 --setting custody or rows")
    for flag in ("--row-subnets", "--reconstructors", "--repair-floor", "--source-floor", "--supernodes",
                 "--supernode-link", "--samplers", "--sample-cover", "--cgc", "--blobs"):
        if given(flag):
            ap.error(f"{flag}: the dump gives it")
    das = topo["das"]
    if a.setting == "custody" and (das.get("row_subnets") or das["reconstructors"]):
        ap.error("a rows network: run it with --setting rows")
    if a.setting == "rows" and not das.get("row_subnets"):
        ap.error("--setting rows needs a dump with row subnets")
    try:
        notes = xcheck.apply_das(cfg, topo, cfg["latency"])
    except ValueError as err:
        ap.error(f"{a.topology}: {err}")
    dd = cfg["das_dump"]
    if dd["blocks"]:                                   # a running cell: what its blocks did
        w = len(dd["withheld"])
        if given("--withhold") and a.withhold != w:
            ap.error(f"--withhold {a.withhold}: the dump's blocks withhold {w}")
        cfg["withhold"] = w
        cfg["msgs"] = min(cfg["msgs"], dd["blocks"])
    if a.fault:
        m = re.fullmatch(FAULT, a.fault)
        if m is None:
            ap.error(f"--fault {a.fault}: not one of the toy's kinds")
        if scenario.fail_select(cfg["seed"], cfg["nodes"], int(m[2])) != cfg["faulty"]:
            ap.error(f"--fault {a.fault}: the toy's draw is not the dump's faulty set ({len(cfg['faulty'])} nodes)")
        if (m[1] == "sil") != cfg["silent"]:
            ap.error(f"--fault {a.fault}: the dump's faulty set is {'' if cfg['silent'] else 'not '}silent")
        cfg["fault"] = a.fault
    cfg["xcheck"] = a.xcheck                           # its counters are tier 4's: on only when asked
    a.blobs, a.cgc, a.source_floor, a.withhold = cfg["blobs"], cfg["cgc"], cfg["SOURCE_FLOOR"], cfg["withhold"]
    a.row_subnets, a.repair_floor = cfg["ROW_SUBNETS"], cfg["REPAIR_FLOOR"]
    return notes


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="home", choices=sorted(scenario.NETS))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--nodes", type=int, default=500)
    ap.add_argument("--payload", type=int, default=0,
                    help="bytes of each payload (default 1 MiB); the compressed size follows at the same ratio. "
                         "16384 gives K = 1 and N = 2, 32768 K = 2 and N = 4: small groups for hand-counted cases")
    ap.add_argument("--msgs", type=int, default=6)
    ap.add_argument("--degree", type=int, default=70)
    ap.add_argument("--without", default="", help="comma-separated card numbers to switch off")
    ap.add_argument("--check-ms", type=float, default=5.0)
    ap.add_argument("--stripe", default="rule", choices=("rule", "on"),
                    help="rule: STRIPE_UPLINK as §5.1 sets it; on: every source stripes, as the harness's tier-4 cells did")
    ap.add_argument("--uplink", default="ps", choices=("ps", "rr"),
                    help="ps: processor sharing over busy connections (FQ-CoDel's fluid limit); rr: whole entries in turn")
    ap.add_argument("--send-buffer", type=int, default=None,
                    help="bytes a connection's transport accepts ahead of the link; a writer waits while its backlog "
                         "is at it, as a QUIC stream write blocks. Default 1, one entry at a time per connection: "
                         "protocol.md §7.3's rule, as the harness's stream writes block. 0: writes complete at once "
                         "(§7.3 not met). With --uplink rr, which has no send buffer, the default is 0 and only 0 is taken")
    ap.add_argument("--rebuilt", default="push", choices=("push", "hold", "announce", "none"),
                    help="what a decoded node does with the chunks it rebuilt: push (the document, §4.6), hold or "
                         "announce (the decoding note's variants); none: it rebuilds nothing (the harness's tier-4 cells)")
    ap.add_argument("--rb-jitter-ms", type=float, default=0.0, help="ms: a random extra wait, up to this, before the decode hands its chunks over")
    ap.add_argument("--rb-max", type=int, default=0, help="push: at most this many chunks per peer (0: its whole shortfall)")
    ap.add_argument("--fault", default="", help="wh<pct> withholders or sil<pct> silent nodes, as the harness picks them; "
                    "v2: claim<pct> claim their row and never answer, hoard<pct> rebuild and claim, answer only the probe and repair nothing, "
                    "hoardm<pct> the same but push each row member the row's cells of its custody columns; "
                    "hoardcol<pct> (option, with --rebuilt-seen on) repair every withheld column but one per subnet, serving none of it")
    ap.add_argument("--loss-data", type=int, default=0, help="percent of chunks every node drops at admission")
    ap.add_argument("--up", type=float, default=0, help="Mbps: every home node's uplink (downlink twice it)")
    ap.add_argument("--down", type=float, default=0, help="Mbps: every home node's downlink")
    ap.add_argument("--topology", default="", help="the harness's SEGMENT_XC_DUMP file: run on its graph, latencies, "
                    "link classes, meshes, publishers and faulty set (--net, --nodes, --fault are then ignored); a DAS "
                    "dump (with a das record) under --doc v2 --setting custody or rows also gives custody, supernodes, "
                    "reconstructors, row subnets and the withheld columns, and --fault then names its faulty set's behaviour")
    ap.add_argument("--xcheck", action="store_true", help="print the harness's xcheck line per message "
                    "(per-rule counts and invariants at publish + 3 s); on with --topology, but for a DAS dump")
    ap.add_argument("--dc-mbps", type=float, default=0, help="Mbps: every datacenter node's link, both ways (default 1000)")
    ap.add_argument("--builder-mbps", type=float, default=0, help="Mbps: a datacenter builder's link, both ways (default 1000)")
    ap.add_argument("--latency-only", action="store_true")
    ap.add_argument("--digest", action="store_true", help="also print a hash of every event the run processed (check.py)")
    ap.add_argument("--doc", default="v03", choices=("v03", "v2"),
                    help="v03: protocol.md; v2: protocol-v2.md loaded on top of it, under its tier 4 setting (its §6.1)")
    ap.add_argument("--setting", default="t4", choices=("t4", "c", "custody", "rows"),
                    help="--doc v2 only. t4: one colour, the mesh (protocol-v2.md §6.1); c: a colour per index with a "
                         "mesh per colour on the same connections, variant C on one neighbourhood (its §6.2); "
                         "custody: PeerDAS custody, a block of --blobs blobs as 128 column groups, derived interest "
                         "of --cgc columns per node, a mesh per column (its §6.2); rows: custody plus RowDAS's row "
                         "groups, one row subnet per node, reconstructors and phases (its §6.2)")
    ap.add_argument("--row-subnets", type=int, default=32, help="rows: ROW_SUBNET_COUNT (EIP-8371: 128; the toy's default keeps every subnet active with 32 blobs)")
    ap.add_argument("--reconstructors", type=int, default=10, help="rows: percent of nodes custodying 64 columns, with phase-1 duty on their row")
    ap.add_argument("--withhold", type=int, default=0, help="custody, rows: columns the proposer withholds (the last ones); only reconstruction supplies them")
    ap.add_argument("--supernodes", type=int, default=0, help="custody, rows: percent of nodes custodying all 128 columns (PeerDAS supernodes); each "
                         "rebuilds every row still short --phase2 seconds after the block (EIP-8371's second phase; under custody alone, "
                         "PeerDAS's reconstruction with a delay), and under rows is also a row reconstructor of its own subnet")
    ap.add_argument("--phase2", type=float, default=1.0, help="supernodes: seconds from the block before a supernode rebuilds a row still short")
    ap.add_argument("--phase2-jitter", type=float, default=0.2, help="supernodes: random extra seconds on the second phase's delay")
    ap.add_argument("--supernode-link", default="dc", choices=("dc", "home"), help="supernodes: their access link, the datacenter class (1 Gbps both ways) or the home one")
    ap.add_argument("--repair-budget", default="off", choices=("off", "on"), help="custody, rows: protocol-v2.md's REPAIR_BUDGET for columns: on, a rebuilt cell goes to "
                         "R_NODE custodians lacking it and is offered to the rest, as its source would push it; off, to every custodian lacking it")
    ap.add_argument("--repair-keepers", default="push", choices=("push", "offer", "skip"), help="custody, rows (exploration): what a rebuilder does "
                         "for a peer that custodies every column, which keeps every row and rebuilds its own (supernodes, the proposer): push the "
                         "rebuilt cells it lacks (the document), offer them, or skip it")
    ap.add_argument("--keeper-claims", default="defer", choices=("defer", "ignore"), help="custody, rows (exploration): ignore, a supernode's "
                         "second-phase duty does not defer on a peer's claim and cancels only on completion it observes (EIP-8371's phase 2)")
    ap.add_argument("--repair-push", default="push", choices=("push", "offer"), help="custody, rows (exploration): offer, a rebuilt cell "
                         "is offered to the peers it would be pushed to, and each pulls one copy")
    ap.add_argument("--member-check", default="on", choices=("on", "off"), help="rows: off (ablation), a member's duty on its own "
                         "subnet's row ends on a verified claim even when the row's cells in its custody columns have not come "
                         "(protocol-v2.md's member check, R5, removed)")
    ap.add_argument("--repair-sample", default="", help="rows (option, R5): after a verified claim, sample the cells we lack "
                         "from their columns' custodians in steps S:L,S:L,... (each extends the last; at most L of S missing passes), "
                         "e.g. 3:1,6:2; the protocol-v2.md parameter REPAIR_SAMPLE")
    ap.add_argument("--repair-reask", default="off", choices=("off", "on"), help="rows (option, R5): on, a lost sample cell is "
                         "re-asked of another custodian of its column, with the extension or, at the last step, in one more wait")
    ap.add_argument("--rebuilt-seen", default="off", choices=("off", "on"), help="custody, rows (option): on, a node marks "
                         "the cells it rebuilt seen (decode_group), so pushed copies of them are acknowledged, not validated "
                         "or forwarded again; makes --fault hoardm strict")
    ap.add_argument("--repair-bias", type=float, default=0.0, help="rows (option): the share of each repair-sample step's "
                         "new cells drawn first from the cells lacked in columns no linked member of the row's subnet "
                         "custodies (a claimant aside); 0, every cell drawn uniformly as the document does")
    ap.add_argument("--sample-wait", type=float, default=0.5, help="rows: seconds before each step of the repair sample is judged")
    ap.add_argument("--alarm-wait", type=float, default=0.0, help="rows (option): seconds after known_at at which an honest "
                    "custodian still lacking a cell no peer holds asks a member of the row's subnet for it (a standing WANT), and "
                    "a member that deferred on a verified claim asks the claimant, rebuilding if that promise breaks; 0: off")
    ap.add_argument("--alarm-jitter", type=float, default=0.2, help="--alarm-wait: up to this many seconds more, per custodian")
    ap.add_argument("--alarm-next", type=float, default=1.5, help="--alarm-wait: seconds before the next member is asked")
    ap.add_argument("--alarm-max", type=int, default=3, help="--alarm-wait: members asked per cell, at most")
    ap.add_argument("--col-announce", default="ALL_JOINED", choices=("ALL_JOINED", "SAMPLE", "NONE"),
                    help="custody, rows: the columns' ANNOUNCE_EXTRA ([D5]): offers beyond the relations to every joined peer "
                         "whose interest holds the cell, at forward time; SAMPLE: the heartbeat's paced gossip; NONE: none")
    ap.add_argument("--row-announce", default="ALL_JOINED", choices=("ALL_JOINED", "SAMPLE", "NONE"),
                    help="rows: the rows' ANNOUNCE_EXTRA ([D5]), as --col-announce")
    ap.add_argument("--row-delay", type=float, default=1.0, help="rows: seconds from the block before a member asks for row cells (R7, [D8])")
    ap.add_argument("--phase3", type=float, default=2.0, help="rows: seconds from the block before a member decodes a row still short (phase 3)")
    ap.add_argument("--phase3-jitter", type=float, default=0.2, help="rows: random extra seconds on the phase-3 delay")
    ap.add_argument("--defer-window", type=float, default=1.0, help="rows: how long a peer's claim defers our decode while a probe verifies it, and the probe's promise (R5)")
    ap.add_argument("--blobs", type=int, default=32, help="custody: blobs per block (cells per column)")
    ap.add_argument("--cgc", type=int, default=8, help="custody: columns each node custodies")
    ap.add_argument("--floor", type=int, default=6, help="custody: custodian peers a node keeps per custody column")
    ap.add_argument("--source-floor", type=int, default=2, help="custody: custodian peers the proposer keeps per column")
    ap.add_argument("--repair-floor", type=int, default=1, help="rows: custodian peers each row member keeps per column it does not custody, so that a row it rebuilds reaches every column (the rebuilders' fanout, protocol-v2.md §4.6); 0: only the links it has")
    ap.add_argument("--samplers", type=int, default=0, help="custody: percent of nodes that sample instead of custodying (interest DECLARED, duty NONE)")
    ap.add_argument("--samples", type=int, default=8, help="custody: cells each sampler declares per block")
    ap.add_argument("--sample-retry", type=float, default=2.0, help="custody: seconds a sampler waits before asking another link")
    ap.add_argument("--sample-cover", type=int, default=0, help="custody: protocol-v2.md's SAMPLE_COVER [D12]: each sampler adds "
                    "sampling-only links until every column has this many custodians among its links (the coverage floor, §1.3); 0: its links as drawn")
    ap.add_argument("--cover-high", type=int, default=1, help="custody: COVER_HIGH [D12]: columns a node of high custody (more than "
                    "--cgc, or the proposer) counts for in the coverage floor (§1.3: diversity, not the fewest links); a large value counts it in full")
    ap.add_argument("--route", default="on", choices=("on", "off"), help="custody: protocol-v2.md's routed sample requests [D12]: a sample "
                    "no link serves goes to a link with duty FORWARD, which passes it one step on (§4.5, §4.10)")
    ap.add_argument("--churn", type=int, default=0, help="with --upkeep on: link replacements per message gap; in "
                    "each, a node other than the source closes one of its links and opens one to a node it has none "
                    "with, at an instant drawn from the churn's own generator (0: none)")
    ap.add_argument("--keep-floor", default="off", choices=("off", "on"), help="custody, with --upkeep on: protocol-v2.md "
                    "§4.1's keep_floor for the columns, the custodian floor per column the graph is built with (--floor) "
                    "kept at runtime: at its heartbeat a custodian short of it in a column opens links to custodians it "
                    "has none with (off, the ablation: keep_floor finds no candidates, and the floor is met at setup only)")
    ap.add_argument("--upkeep", default="off", choices=("off", "on"), help="protocol-v2.md §4.1 on the wire: JOINs, "
                    "GRAFTs and PRUNEs sent and read, and the heartbeat's maintain_relations given candidates (off: the "
                    "relations stay as built, the messages are not sent)")
    ap.add_argument("--symmetric", default="on", choices=("on", "off"), help="the payload's SYMMETRIC (protocol-v2.md "
                    "§4.1, §6.1: v0.3's mesh, one relation both ways); off: its in- and out-relations kept apart, the "
                    "upkeep before 2026-11-09")
    ap.add_argument("--prune-backoff", type=float, default=0.0, help="seconds: every type's PRUNE_BACKOFF (protocol-v2.md "
                    "§4.1): after a PRUNE received, its relation is not grafted again before then (0: none)")
    ap.add_argument("--route-hops", type=int, default=1, help="custody: ROUTE_HOPS, the forwarding steps of a routed request (1: two hops)")
    ap.add_argument("--sample-retry2", type=float, default=0.5, help="custody: SAMPLE_RETRY2, the second phase's wait per peer (§4.10)")
    ap.add_argument("--sample-outstanding", type=int, default=4, help="custody: SAMPLE_OUTSTANDING, second-phase asks in flight per block (§4.10)")
    ap.add_argument("--forward-limit", type=float, default=math.inf, help="custody: FORWARD_LIMIT, routed requests a node passes on per peer and block")
    ap.add_argument("--no-invariants", action="store_true", help="--doc v2: skip the invariants report (invariants.py)")
    ap.add_argument("--answers-first", default="off",
                    choices=("off", "on", "v03", "oldest", "line", "others", "fresh", "late", "othersans"),
                    help="--doc v2: off and on are protocol-v2.md §4.12's ANSWERS_FIRST (a source's own chunks first either way); "
                         "v03 is v0.3's order; the others are the forms measured against it (node.py _writer_variants, README)")
    ap.add_argument("--source-offers", default="on", choices=("on", "off", "late", "publish"),
                    help="off: publish does not offer the chunks to the peers it did not push them (card 3 at the source); "
                         "late: publish queues those offers after the pushes of every group published at the same instant; "
                         "both act only on offers publish itself makes, so since v0.9's rule (offers at the acknowledgement) "
                         "they change nothing; publish: protocol.md's SOURCE_OFFERS = PUBLISH (§5.1), the offers at publish "
                         "and the HAVE growing at a chunk's first write, as before v0.9's rule; not with --doc v2")
    ap.add_argument("--answer-due", type=float, default=0.100, help="--answers-first late: seconds an answer waits before it goes ahead of pushes")
    ap.add_argument("--promise", type=float, default=0.400, help="seconds an offer's promise runs before the peer is parked for the group (v0.3 §6.1's PROMISE)")
    ap.add_argument("--promise-mode", default="fixed", choices=("fixed", "uplink", "peer"),
                    help="--doc v2: fixed, protocol-v2.md §4.13 (the promise stays at --promise); uplink: the form §4.13 rejects, "
                         "the promise scaled with the ask window; peer: an option, a promise per peer following its observed "
                         "answer times (srtt + 4 rttvar, floored at --promise)")
    ap.add_argument("--ask-uplink", type=float, default=50, help="--doc v2: Mbps, protocol-v2.md §4.13's ASK_UPLINK, below which a node's "
                    "IWANT_WINDOW and PROMISE scale by ASK_UPLINK / its uplink; 0: never (v0.3's fixed clocks)")
    ap.add_argument("--merge-holdings", default="off", choices=("off", "on"),
                    help="--doc v2: protocol-v2.md §6.3's MERGE_HOLDINGS, an option: a holding of a group the node publishes "
                         "that is still in its queue takes the newer chunks instead of a second holding (§4.2, §4.7)")
    ap.add_argument("--ihave-limits", default="",
                    help="MESSAGES,LENGTH: gossipsub's two IHAVE limits, the client's (protocol.md §4.4, §8.2; protocol-v2.md "
                         "§4.3): offer-bearing RPCs per peer and heartbeat, and asks in reply to them; the asks over either "
                         "wait for the next heartbeat's retry (stock gossipsub: 10,5000). Empty: no limit")
    ap.add_argument("--late-block", default="",
                    help="PCT,MS[,STORE]: PCT percent of the nodes that publish nothing (0 to 100; 0: none) install each block MS milliseconds "
                         "after its publish, so that the chunks ahead of it take protocol.md §4.2's deferral: each such node "
                         "keeps at most STORE deferred copies per peer (default 2) and refuses the rest. The payload only")
    a = ap.parse_args(argv)
    send_buffer_default = 1 if a.uplink == "ps" else 0      # §7.3's rule where the toy's link can keep it
    if a.send_buffer is None:
        a.send_buffer = send_buffer_default
    late = None
    if a.late_block:
        try:
            parts = a.late_block.split(",")
            late = [int(parts[0]), float(parts[1])] + [int(x) for x in parts[2:]]
        except (ValueError, IndexError):
            late = []
        if (len(late) not in (2, 3) or not 0 <= late[0] <= 100 or not late[1] >= 0 or min(late[2:] or [0]) < 0
                or a.setting in ("custody", "rows")):
            ap.error("--late-block PCT,MS[,STORE]: PCT a whole number from 0 to 100, MS and STORE not negative "
                     "(STORE a whole number); and not with --setting custody or rows")
    limits = [float(x) for x in a.ihave_limits.split(",")] if a.ihave_limits else [math.inf, math.inf]
    cfg = dict(CFG, seed=a.seed, nodes=a.nodes, msgs=a.msgs, degree=a.degree, CHECK_TIME=a.check_ms / 1000,
               digest=a.digest, doc=a.doc, setting=a.setting, blobs=a.blobs, cgc=a.cgc, F_LO=a.floor, upkeep=a.upkeep == "on",
               churn=a.churn, keep_floor=a.keep_floor == "on", symmetric=a.symmetric, prune_backoff=a.prune_backoff,
               SOURCE_FLOOR=a.source_floor, REPAIR_FLOOR=a.repair_floor, samplers=a.samplers, samples=a.samples, SAMPLE_RETRY=a.sample_retry,
               SAMPLE_COVER=a.sample_cover, COVER_HIGH=a.cover_high, route=a.route, ROUTE_HOPS=a.route_hops, SAMPLE_RETRY2=a.sample_retry2,
               SAMPLE_OUTSTANDING=a.sample_outstanding, FORWARD_LIMIT=a.forward_limit,
               ROW_SUBNETS=a.row_subnets, reconstructors=a.reconstructors, withhold=a.withhold, ROW_DELAY=a.row_delay, COL_ANNOUNCE=a.col_announce, ROW_ANNOUNCE=a.row_announce,
               PHASE3=a.phase3, PHASE3_JITTER=a.phase3_jitter, DEFER_WINDOW=a.defer_window,
               supernodes=a.supernodes, PHASE2=a.phase2, PHASE2_JITTER=a.phase2_jitter, supernode_link=a.supernode_link,
               repair_budget=a.repair_budget, repair_keepers=a.repair_keepers, keeper_claims=a.keeper_claims, repair_push=a.repair_push, PROMISE=a.promise, ASK_UPLINK=a.ask_uplink * 1e6, promise_mode=a.promise_mode,
               member_check=a.member_check, rebuilt_seen=a.rebuilt_seen, REPAIR_BIAS=a.repair_bias, SAMPLE_WAIT=a.sample_wait, REPAIR_REASK=a.repair_reask == "on",
               REPAIR_SAMPLE=[tuple(int(x) for x in step.split(":")) for step in a.repair_sample.split(",")] if a.repair_sample else None,
               invariants=(a.doc == "v2" and not a.no_invariants), answers_first=a.answers_first, answer_due=a.answer_due,
               source_offers=a.source_offers, MERGE_HOLDINGS=a.merge_holdings == "on",
               MAX_IHAVE_MESSAGES=limits[0], MAX_IHAVE_LENGTH=limits[1],
               late_block=(int(late[0]), late[1] / 1000, int(late[2]) if len(late) == 3 else 2) if late else None,
               ALARM_WAIT=a.alarm_wait, ALARM_JITTER=a.alarm_jitter, ALARM_NEXT=a.alarm_next, ALARM_MAX=a.alarm_max)
    if a.source_offers == "publish" and a.doc == "v2":
        ap.error("--source-offers publish is protocol.md's SOURCE_OFFERS: protocol-v2.md here has none")
    if a.fault.startswith("hoardcol") and a.rebuilt_seen != "on":
        ap.error("--fault hoardcol is meant strict: with --rebuilt-seen on")
    if a.payload:
        cfg["payload"], cfg["COMPRESSED"] = a.payload, round(a.payload / CFG["COMPRESSION"])
    for k in filter(None, a.without.split(",")):
        cfg[f"card{int(k)}"] = False
    if not cfg["card11"]:
        cfg["R"] = 3                    # §0: without card 11, R = 3 at 1 MiB
    if a.stripe == "on":
        cfg["STRIPE_UPLINK"] = 0
    cfg["uplink"] = a.uplink
    cfg["send_buffer"] = a.send_buffer or None
    cfg["classes"] = scenario.net(a.net, a.up * 1e6, a.down * 1e6, a.dc_mbps * 1e6, a.builder_mbps * 1e6)
    cfg.update(rebuilt=a.rebuilt, rb_jitter=a.rb_jitter_ms / 1000, rb_max=a.rb_max, fault=a.fault, loss_data=a.loss_data)
    cfg["latency"] = scenario.geo_latency(a.seed)
    cfg["topology"] = scenario.topology
    cfg["xcheck"] = a.xcheck or bool(a.topology)
    notes, graph = [], None
    if a.topology:
        try:
            topo = xcheck.load(a.topology)
        except ValueError as err:
            ap.error(str(err))
        try:
            xcheck.check(topo)
        except ValueError as err:
            ap.error(f"{a.topology}: {err}")
        base = topo["net"] or topo["network"]
        if base["seed"] != a.seed:
            print(f"note: --seed {a.seed} replaced by the dump's seed {base['seed']}")
            cfg["seed"] = base["seed"]
            cfg["latency"] = scenario.geo_latency(cfg["seed"])
        if topo["das"] is None:
            if topo["net"] is None:
                ap.error(f"{a.topology}: a dump without a das record needs its net record")
            notes = xcheck.apply(cfg, topo, cfg["latency"])
            if len(topo["meshes"]) < a.msgs:
                cfg["msgs"] = len(topo["meshes"])
        else:
            notes = das_dump(ap, a, argv, cfg, topo)
            graph = xcheck.graph_line(cfg, topo["shape"])
    if a.latency_only:
        print(latency_summary(cfg["latency"](a.nodes, None), a.nodes))
        return
    recon = (f"{a.reconstructors}%" if cfg.get("das_dump") is None
             else f"{len(cfg['das_dump']['reconstructors'])} (dump)")
    supers = f"{a.supernodes}% ({a.supernode_link})" if cfg.get("das_dump") is None else f"{cfg['supernodes']} (dump)"
    print(f"toy: doc={a.doc}{' setting=' + a.setting if a.doc == 'v2' else ''}"
          f"{f' blobs={a.blobs} cgc={a.cgc} floor={a.floor}/{a.source_floor}' if a.setting in ('custody', 'rows') else ''}"
          f"{f' subnets={a.row_subnets} reconstructors={recon} withhold={a.withhold} row-delay={a.row_delay:g}s phase3={a.phase3:g}+{a.phase3_jitter:g}s defer={a.defer_window:g}s repair-floor={a.repair_floor}' if a.setting == 'rows' else ''}"
          f"{f' samplers={a.samplers}% samples={a.samples} retry={a.sample_retry:g}s' if a.samplers else ''}"
          f"{f' cover={a.sample_cover}/{a.cover_high} route={a.route}/{a.route_hops} retry2={a.sample_retry2:g}s outstanding={a.sample_outstanding} forward-limit={a.forward_limit:g}' if a.samplers else ''}"
          f"{f' withhold={a.withhold}' if a.withhold and a.setting == 'custody' else ''}"
          f"{f' supernodes={supers} phase2={a.phase2:g}+{a.phase2_jitter:g}s' if cfg.get('supernodes') and a.setting in ('custody', 'rows') else ''}"
          f" net={a.net if not a.topology else 'dump'} seed={cfg['seed']} n={cfg['nodes']} msgs={cfg['msgs']} without={a.without or '-'} stripe={a.stripe} uplink={a.uplink} rebuilt={a.rebuilt}"
          f"{' jitter=%gms' % a.rb_jitter_ms if a.rb_jitter_ms else ''}{' rbmax=%d' % a.rb_max if a.rb_max else ''}"
          f"{' fault=' + a.fault if a.fault else ''}{' answers-first=' + a.answers_first if a.answers_first != 'off' else ''}"
          f"{' source-offers=' + a.source_offers if a.source_offers != 'on' else ''}"
          f"{' col-announce=' + a.col_announce if a.col_announce != 'ALL_JOINED' else ''}"
          f"{' row-announce=' + a.row_announce if a.row_announce != 'ALL_JOINED' else ''}"
          f"{' repair-budget=on' if a.repair_budget == 'on' else ''}"
          f"{' repair-keepers=' + a.repair_keepers if a.repair_keepers != 'push' else ''}"
          f"{' keeper-claims=' + a.keeper_claims if a.keeper_claims != 'defer' else ''}"
          f"{' member-check=off' if a.member_check == 'off' else ''}"
          f"{' repair-sample=' + a.repair_sample + ' wait=%gs' % a.sample_wait if a.repair_sample else ''}"
          f"{' reask' if a.repair_sample and a.repair_reask == 'on' else ''}{' rebuilt-seen=on' if a.rebuilt_seen == 'on' else ''}{f' repair-bias={a.repair_bias:g}' if a.repair_bias else ''}"
          f"{f' alarm={a.alarm_wait:g}+{a.alarm_jitter:g}s next={a.alarm_next:g}s max={a.alarm_max}' if a.alarm_wait else ''}"
          f"{' repair-push=' + a.repair_push if a.repair_push != 'push' else ''}{f' promise={a.promise:g}s' if a.promise != 0.4 else ''}{f' ask-uplink={a.ask_uplink:g}' if a.ask_uplink != 50 else ''}{' promise-mode=' + a.promise_mode if a.promise_mode != 'fixed' else ''}"
          f"{' loss=%d%%' % a.loss_data if a.loss_data else ''}{' up=%g' % a.up if a.up else ''}{' down=%g' % a.down if a.down else ''}"
          f"{' dc=%g' % a.dc_mbps if a.dc_mbps else ''}{' builder=%g' % a.builder_mbps if a.builder_mbps else ''}"
          f"{' merge-holdings=on' if a.merge_holdings == 'on' else ''}{' send-buffer=%d' % a.send_buffer if a.send_buffer != send_buffer_default else ''}"
          f"{' ihave-limits=' + a.ihave_limits if a.ihave_limits else ''}"
          f"{' late-block=' + a.late_block if a.late_block else ''}"
          f"{' payload=%d' % a.payload if a.payload else ''}"
          f"{' topology=' + a.topology if a.topology else ''}")
    if graph:
        print(graph)
    for note in notes:
        print(f"note: {note}")
    run(cfg)
    if cfg.get("failed"):                       # after the digest line, so that check.py shows this one
        sys.exit(f"run.py: FAILED: {cfg['failed']}")


if __name__ == "__main__":
    main(sys.argv[1:])
