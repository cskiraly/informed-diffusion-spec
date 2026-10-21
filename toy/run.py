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
import statistics as st
import sys
import time

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
                  f"max {s['max']*1000:.0f}ms missing {s['missing']} unreachable {s['unreachable']}", file=out)
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
    if cfg.get("MERGE_HOLDINGS"):
        merged, sent = (sum(nd.merged[k] for nd in sim.nodes.values()) for k in (0, 1))
        print(f"  merged holdings: {merged} of {sent} holdings of published groups went into one still queued", file=out)
    if sim.digest is not None:
        print(f"digest {sim.digest.hexdigest()}", file=out)
    return summary, rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="home", choices=sorted(scenario.NETS))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--nodes", type=int, default=500)
    ap.add_argument("--msgs", type=int, default=6)
    ap.add_argument("--degree", type=int, default=70)
    ap.add_argument("--without", default="", help="comma-separated card numbers to switch off")
    ap.add_argument("--check-ms", type=float, default=5.0)
    ap.add_argument("--stripe", default="rule", choices=("rule", "on"),
                    help="rule: STRIPE_UPLINK as §5.1 sets it; on: every source stripes, as the harness's tier-4 cells did")
    ap.add_argument("--uplink", default="ps", choices=("ps", "rr"),
                    help="ps: processor sharing over busy connections (FQ-CoDel's fluid limit); rr: whole entries in turn")
    ap.add_argument("--send-buffer", type=int, default=0,
                    help="bytes a connection's transport accepts ahead of the link; a writer waits while its backlog "
                         "is at it, as a QUIC stream write blocks (0: writes complete at once)")
    ap.add_argument("--rebuilt", default="push", choices=("push", "hold", "announce", "none"),
                    help="what a decoded node does with the chunks it rebuilt: push (the document, §4.6), hold or "
                         "announce (the decoding note's variants); none: it rebuilds nothing (the harness's tier-4 cells)")
    ap.add_argument("--rb-jitter-ms", type=float, default=0.0, help="ms: a random extra wait, up to this, before the decode hands its chunks over")
    ap.add_argument("--rb-max", type=int, default=0, help="push: at most this many chunks per peer (0: its whole shortfall)")
    ap.add_argument("--fault", default="", help="wh<pct> withholders or sil<pct> silent nodes, as the harness picks them; "
                    "v2: claim<pct> claim their row and never answer, hoard<pct> rebuild and claim, answer only the probe and repair nothing, "
                    "hoardm<pct> the same but push each row member the row's cells of its custody columns")
    ap.add_argument("--loss-data", type=int, default=0, help="percent of chunks every node drops at admission")
    ap.add_argument("--up", type=float, default=0, help="Mbps: every home node's uplink (downlink twice it)")
    ap.add_argument("--down", type=float, default=0, help="Mbps: every home node's downlink")
    ap.add_argument("--topology", default="", help="the harness's SEGMENT_XC_DUMP file: run on its graph, latencies, "
                    "link classes, meshes, publishers and faulty set (--net, --nodes, --fault are then ignored)")
    ap.add_argument("--xcheck", action="store_true", help="print the harness's xcheck line per message "
                    "(per-rule counts and invariants at publish + 3 s); on with --topology")
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
    ap.add_argument("--sample-wait", type=float, default=0.5, help="rows: seconds before each step of the repair sample is judged")
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
    ap.add_argument("--no-invariants", action="store_true", help="--doc v2: skip the invariants report (invariants.py)")
    ap.add_argument("--answers-first", default="off",
                    choices=("off", "on", "v03", "oldest", "line", "others", "fresh", "late", "othersans"),
                    help="--doc v2: off and on are protocol-v2.md §4.12's ANSWERS_FIRST (a source's own chunks first either way); "
                         "v03 is v0.3's order; the others are the forms measured against it (node.py _writer_variants, README)")
    ap.add_argument("--source-offers", default="on", choices=("on", "off", "late"),
                    help="off: the source does not offer its chunks to the relation peers it did not push them (card 3 at the source); "
                         "late: it offers them after the pushes of every group it published at the same instant")
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
    a = ap.parse_args(argv)
    cfg = dict(CFG, seed=a.seed, nodes=a.nodes, msgs=a.msgs, degree=a.degree, CHECK_TIME=a.check_ms / 1000,
               digest=a.digest, doc=a.doc, setting=a.setting, blobs=a.blobs, cgc=a.cgc, F_LO=a.floor,
               SOURCE_FLOOR=a.source_floor, REPAIR_FLOOR=a.repair_floor, samplers=a.samplers, samples=a.samples, SAMPLE_RETRY=a.sample_retry,
               ROW_SUBNETS=a.row_subnets, reconstructors=a.reconstructors, withhold=a.withhold, ROW_DELAY=a.row_delay,
               PHASE3=a.phase3, PHASE3_JITTER=a.phase3_jitter, DEFER_WINDOW=a.defer_window,
               supernodes=a.supernodes, PHASE2=a.phase2, PHASE2_JITTER=a.phase2_jitter, supernode_link=a.supernode_link,
               repair_budget=a.repair_budget, repair_keepers=a.repair_keepers, keeper_claims=a.keeper_claims, repair_push=a.repair_push, PROMISE=a.promise, ASK_UPLINK=a.ask_uplink * 1e6, promise_mode=a.promise_mode,
               member_check=a.member_check, SAMPLE_WAIT=a.sample_wait, REPAIR_REASK=a.repair_reask == "on",
               REPAIR_SAMPLE=[tuple(int(x) for x in step.split(":")) for step in a.repair_sample.split(",")] if a.repair_sample else None,
               invariants=(a.doc == "v2" and not a.no_invariants), answers_first=a.answers_first, answer_due=a.answer_due,
               source_offers=a.source_offers, MERGE_HOLDINGS=a.merge_holdings == "on")
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
    notes = []
    if a.topology:
        topo = xcheck.load(a.topology)
        if topo["net"]["seed"] != a.seed:
            print(f"note: --seed {a.seed} replaced by the dump's seed {topo['net']['seed']}")
            cfg["seed"] = topo["net"]["seed"]
            cfg["latency"] = scenario.geo_latency(cfg["seed"])
        notes = xcheck.apply(cfg, topo, cfg["latency"])
        if len(topo["meshes"]) < a.msgs:
            cfg["msgs"] = len(topo["meshes"])
    if a.latency_only:
        print(latency_summary(cfg["latency"](a.nodes, None), a.nodes))
        return
    print(f"toy: doc={a.doc}{' setting=' + a.setting if a.doc == 'v2' else ''}"
          f"{f' blobs={a.blobs} cgc={a.cgc} floor={a.floor}/{a.source_floor}' if a.setting in ('custody', 'rows') else ''}"
          f"{f' subnets={a.row_subnets} reconstructors={a.reconstructors}% withhold={a.withhold} row-delay={a.row_delay:g}s phase3={a.phase3:g}+{a.phase3_jitter:g}s defer={a.defer_window:g}s repair-floor={a.repair_floor}' if a.setting == 'rows' else ''}"
          f"{f' samplers={a.samplers}% samples={a.samples} retry={a.sample_retry:g}s' if a.samplers else ''}"
          f"{f' withhold={a.withhold}' if a.withhold and a.setting == 'custody' else ''}"
          f"{f' supernodes={a.supernodes}% ({a.supernode_link}) phase2={a.phase2:g}+{a.phase2_jitter:g}s' if a.supernodes and a.setting in ('custody', 'rows') else ''}"
          f" net={a.net if not a.topology else 'dump'} seed={cfg['seed']} n={cfg['nodes']} msgs={cfg['msgs']} without={a.without or '-'} stripe={a.stripe} uplink={a.uplink} rebuilt={a.rebuilt}"
          f"{' jitter=%gms' % a.rb_jitter_ms if a.rb_jitter_ms else ''}{' rbmax=%d' % a.rb_max if a.rb_max else ''}"
          f"{' fault=' + a.fault if a.fault else ''}{' answers-first=' + a.answers_first if a.answers_first != 'off' else ''}"
          f"{' source-offers=' + a.source_offers if a.source_offers != 'on' else ''}"
          f"{' repair-budget=on' if a.repair_budget == 'on' else ''}"
          f"{' repair-keepers=' + a.repair_keepers if a.repair_keepers != 'push' else ''}"
          f"{' keeper-claims=' + a.keeper_claims if a.keeper_claims != 'defer' else ''}"
          f"{' member-check=off' if a.member_check == 'off' else ''}"
          f"{' repair-sample=' + a.repair_sample + ' wait=%gs' % a.sample_wait if a.repair_sample else ''}"
          f"{' reask' if a.repair_sample and a.repair_reask == 'on' else ''}"
          f"{' repair-push=' + a.repair_push if a.repair_push != 'push' else ''}{f' promise={a.promise:g}s' if a.promise != 0.4 else ''}{f' ask-uplink={a.ask_uplink:g}' if a.ask_uplink != 50 else ''}{' promise-mode=' + a.promise_mode if a.promise_mode != 'fixed' else ''}"
          f"{' loss=%d%%' % a.loss_data if a.loss_data else ''}{' up=%g' % a.up if a.up else ''}{' down=%g' % a.down if a.down else ''}"
          f"{' dc=%g' % a.dc_mbps if a.dc_mbps else ''}{' builder=%g' % a.builder_mbps if a.builder_mbps else ''}"
          f"{' merge-holdings=on' if a.merge_holdings == 'on' else ''}{' send-buffer=%d' % a.send_buffer if a.send_buffer else ''}"
          f"{' topology=' + a.topology if a.topology else ''}")
    for note in notes:
        print(f"note: {note}")
    run(cfg)


if __name__ == "__main__":
    main(sys.argv[1:])
