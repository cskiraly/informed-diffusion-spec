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
    rows, snaps = [], []
    for m in range(1, cfg["msgs"] + 1):
        at = cfg["first"] + (m - 1) * cfg["gap"]
        sim.run(at)
        snaps.append({i: (nd.rx_data, nd.rx_ctrl) for i, nd in sim.nodes.items()})
        sim.publish(m)
    sim.run(cfg["first"] + cfg["msgs"] * cfg["gap"])
    snaps.append({i: (nd.rx_data, nd.rx_ctrl) for i, nd in sim.nodes.items()})
    W, n = cfg["COMPRESSED"], cfg["nodes"]
    for r, (a, b) in zip(sim.results(), zip(snaps, snaps[1:])):
        data = sum(b[i][0] - a[i][0] for i in a) / n / W
        ctrl = sum(b[i][1] - a[i][1] for i in a) / n / W
        r.update(data=data, ctrl=ctrl, copies=data + ctrl)
        rows.append(r)
        print(f"msg {r['msg']}: p50 {r['p50']*1000:.0f}ms p99 {r['p99']*1000:.0f}ms "
              f"max {r['max']*1000:.0f}ms missing {r['missing']}  "
              f"copies {r['copies']:.2f} (data {data:.2f}, control {ctrl:.3f})", file=out)
    warm = rows[1:] or rows
    summary = {k: st.median(r[k] for r in warm) for k in ("p50", "p99", "copies", "data", "ctrl")}
    print(f"warm median: p50 {summary['p50']*1000:.0f}ms p99 {summary['p99']*1000:.0f}ms "
          f"copies {summary['copies']:.2f}  [{sim.events} events, {time.time()-t0:.0f}s]", file=out)
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
    ap.add_argument("--rebuilt", default="push", choices=("push", "hold", "announce", "none"),
                    help="what a decoded node does with the chunks it rebuilt: push (the document, §4.6), hold or "
                         "announce (the decoding note's variants); none: it rebuilds nothing (the harness's tier-4 cells)")
    ap.add_argument("--rb-jitter-ms", type=float, default=0.0, help="ms: a random extra wait, up to this, before the decode hands its chunks over")
    ap.add_argument("--rb-max", type=int, default=0, help="push: at most this many chunks per peer (0: its whole shortfall)")
    ap.add_argument("--fault", default="", help="wh<pct> withholders or sil<pct> silent nodes, as the harness picks them")
    ap.add_argument("--loss-data", type=int, default=0, help="percent of chunks every node drops at admission")
    ap.add_argument("--up", type=float, default=0, help="Mbps: every home node's uplink (downlink twice it)")
    ap.add_argument("--down", type=float, default=0, help="Mbps: every home node's downlink")
    ap.add_argument("--latency-only", action="store_true")
    ap.add_argument("--digest", action="store_true", help="also print a hash of every event the run processed (check.py)")
    a = ap.parse_args(argv)
    cfg = dict(CFG, seed=a.seed, nodes=a.nodes, msgs=a.msgs, degree=a.degree, CHECK_TIME=a.check_ms / 1000,
               digest=a.digest)
    for k in filter(None, a.without.split(",")):
        cfg[f"card{int(k)}"] = False
    if not cfg["card11"]:
        cfg["R"] = 3                    # §0: without card 11, R = 3 at 1 MiB
    if a.stripe == "on":
        cfg["STRIPE_UPLINK"] = 0
    cfg["uplink"] = a.uplink
    cfg["classes"] = scenario.net(a.net, a.up * 1e6, a.down * 1e6)
    cfg.update(rebuilt=a.rebuilt, rb_jitter=a.rb_jitter_ms / 1000, rb_max=a.rb_max, fault=a.fault, loss_data=a.loss_data)
    cfg["latency"] = scenario.geo_latency(a.seed)
    cfg["topology"] = scenario.topology
    if a.latency_only:
        print(latency_summary(cfg["latency"](a.nodes, None), a.nodes))
        return
    print(f"toy: net={a.net} seed={a.seed} n={a.nodes} msgs={a.msgs} without={a.without or '-'} stripe={a.stripe} uplink={a.uplink} rebuilt={a.rebuilt}"
          f"{' jitter=%gms' % a.rb_jitter_ms if a.rb_jitter_ms else ''}{' rbmax=%d' % a.rb_max if a.rb_max else ''}"
          f"{' fault=' + a.fault if a.fault else ''}"
          f"{' loss=%d%%' % a.loss_data if a.loss_data else ''}{' up=%g' % a.up if a.up else ''}{' down=%g' % a.down if a.down else ''}")
    run(cfg)


if __name__ == "__main__":
    main(sys.argv[1:])
