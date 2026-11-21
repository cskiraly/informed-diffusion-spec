#!/usr/bin/env python3
"""Runtime monitors on the spec's own code: the model's safety properties, checked on the toy (which
executes ../protocol.md) in check.py's 60-node cells, each property at its own moment (below).

    python3 -I formal/toy/monitor.py [--seeds 7,8,9] [--cells push,withholders,...] [-j 8] [--break askfilter]

It exits 0 when no property is violated, or, with --break, when the broken rule is caught; 1 otherwise,
and 1 when a cell's run fails (a break that no longer matches protocol.md's text among them).

Checked, as in formal/diffusion.qnt:
- W1 window: in_flight equals the writers holding a slot plus the chunks in `sent`, and is at most W
  (after each event at a node, at that node);
- W2 wake-up, checked with W1: with a slot free, the first writer in line that can write has a run queued
  (a writer whose write has not completed, §7.3, is woken by its transport, and keeps its place but not the
  front, §7.1);
- S1 stale ask: no ask leaves (Sim.transmit) for a chunk the sender holds or no longer pulls;
- P4: a HAVE the source writes names at most one chunk it has not yet sent (the lead HAVE);
- A1 penalties: no node penalises another (the toy counts them; nothing read the counter before).
The toy is not modified: Sim.run and Sim.transmit are wrapped in memory, in a subprocess per cell.
"""
import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
from pathlib import Path

TOY = Path(__file__).resolve().parents[2] / "toy"
BASE = ["--nodes", "60", "--degree", "30", "--msgs", "3"]
CELLS = {                       # check.py's cells
    "push": [], "hold": ["--rebuilt", "hold"], "announce": ["--rebuilt", "announce"],
    "none": ["--rebuilt", "none"], "withholders": ["--fault", "wh30"], "silent": ["--fault", "sil30"],
    "cap-wait": ["--rb-max", "1", "--rb-jitter-ms", "20", "--fault", "sil30"], "dcb20": ["--net", "dcb20"],
    "rr-stripe": ["--uplink", "rr", "--stripe", "on"], "without-a": ["--without", "8,9,12,15"],
    "without-b": ["--without", "11,13,14,17"], "loss-thin": ["--loss-data", "10", "--up", "20"],
}

BREAKS = {                      # known answers: one rule taken out of the extracted spec, in memory; each pattern
    # matches the code alone (a comment may change) and must match exactly once; the property it must break
    "askfilter": (r"^        c\.ids = \[a for a in c\.ids\b[^\n]*\n[^\n]*\bif not held\(a\) and not gated\(a\)[^\n]*\n"
                  r"(?:[^\n]*\n)*?[^\n]*\]\s*(?:#[^\n]*)?\n",
                  "        pass\n", "S1"),
    "wake": (r"(?<=        in_flight \+= 1\n)        wake_front\(\)[^\n]*\n", "", "W2"),
    "writewait": (r"^    if p in waiters: wake_front\(\)[^\n]*\n", "    pass\n", "W2"),     # write_waits wakes no one
    "p4": (r"^    return \(origin\[g\] if g in origin else mine\[g\]\)\.copy\(\)[^\n]*\n",
           "    return mine[g].copy()\n", "P4"),
}

CHILD = r'''
import collections, io, json, re, sys
sys.path.insert(0, TOY)
import node as NODE
src = NODE.SPEC_SRC
for pat, new, _ in PATCHES:
    src, n = re.subn(pat, lambda _m: new, src, count=0, flags=re.M)
    assert n == 1, f"{n} matches: {pat[:60]}"
NODE.SPEC = compile(src, "protocol.md (extracted, monitored)", "exec")
import sim as S
import run as R
V = collections.Counter(); EX = {}
def note(p, m):
    V[p] += 1
    EX.setdefault(p, m)
def check(nd):
    ns = nd.ns
    inf, W = ns["in_flight"], ns["W"]
    held = sum(1 for v in ns["slot_held"].values() if v)
    if inf != held + len(ns["sent"]) or inf > W or inf < 0:
        note("W1", f"node {nd.id} t={nd.sim.now:.4f} in_flight={inf} held={held} sent={len(ns['sent'])} W={W}")
    w = ns["waiters"]
    first = next((q for q in w if q not in nd.writer_blocked), None)    # the first that can write (§7.1, §7.3)
    if first is not None and inf < W and first not in nd.writer_kicked:
        note("W2", f"node {nd.id} t={nd.sim.now:.4f} waiters={list(w)[:4]} first={first} in_flight={inf} W={W}")
orig_run = S.Sim.run
def run(self, until):
    q = self.q
    while q and q[0][0] <= until:
        t, _, node, fn, args = S.heapq.heappop(q)
        self.now = t
        if node is not None:
            node.ns["now"] = t
        fn(*args)
        self.events += 1
        if node is not None:
            check(node)
    self.now = until
S.Sim.run = run
orig_tx = S.Sim.transmit
def transmit(self, node, p, e):
    ns = node.ns
    for c in e.iwants():
        for a in c.ids:
            if ns["held"](a) or ns["gated"](a):
                note("S1", f"node {node.id} -> {p} t={self.now:.4f}")
    if e.control:
        for m in e.control.items:
            if m.kind == "idontwant":
                for h in m.ids:
                    org = ns["origin"].get(getattr(h, "group", None))
                    if org is not None:
                        extra = h.bits.v & ~org.v
                        if bin(extra).count("1") > 1:
                            note("P4", f"source {node.id} -> {p} t={self.now:.4f} names {bin(extra).count('1')} unsent")
    return orig_tx(self, node, p, e)
S.Sim.transmit = transmit
orig_publish = S.Sim.publish
SIMS = []
def publish(self, m):
    if self not in SIMS:
        SIMS.append(self)
    return orig_publish(self, m)
S.Sim.publish = publish
buf = io.StringIO()
real = R.run
R.run = lambda cfg, out=None: real(cfg, out=buf)
R.main(ARGV)
pen = sum(nd.penalties for s in SIMS for nd in s.nodes.values())
if pen:
    note("A1", f"{pen} penalties")
miss = [int(x) for x in __import__("re").findall(r"missing (\d+)", buf.getvalue())]
print(json.dumps({"V": dict(V), "EX": EX, "missing": miss, "events": sum(s.events for s in SIMS)}))
'''


def one(job):
    name, seed, brk = job
    argv = BASE + ["--seed", str(seed)] + CELLS[name]
    patches = [BREAKS[b] for b in brk.split(",") if b]
    code = f"TOY = {str(TOY)!r}\nARGV = {argv!r}\nPATCHES = {patches!r}\n" + CHILD
    p = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=str(TOY))
    if p.returncode:
        return job, None, p.stderr[-500:]
    return job, json.loads(p.stdout.strip().splitlines()[-1]), ""


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="7,8,9")
    ap.add_argument("--cells", default=",".join(CELLS))
    ap.add_argument("-j", type=int, default=8)
    ap.add_argument("--break", dest="brk", default="", help="known answers, one rule taken out: " + ",".join(BREAKS))
    a = ap.parse_args(argv)
    brks = [b for b in a.brk.split(",") if b]
    if len(brks) > 1:                           # each break's property must be caught with that rule alone out
        ap.error("--break: one break a run (two breaks that break the same property would share one count)")
    for b in brks:
        if b not in BREAKS:
            ap.error(f"--break {b}: none such; the breaks are " + ",".join(BREAKS))
    jobs = [(c, int(s), a.brk) for c in a.cells.split(",") for s in a.seeds.split(",")]
    total, errors = {}, 0
    with cf.ThreadPoolExecutor(a.j) as ex:
        for (name, seed, _b), res, err in ex.map(one, jobs):
            if res is None:
                errors += 1
                print(f"{name:12s} {seed:3d} ERROR {err}")
                continue
            for k, v in res["V"].items():
                total[k] = total.get(k, 0) + v
            print(f"{name:12s} {seed:3d} events {res['events']:8d} missing {res['missing']} "
                  f"violations {res['V'] or 'none'} {res['EX'] if res['V'] else ''}")
    print("total violations:", total or "none")
    if errors:
        print(f"FAIL: {errors} of {len(jobs)} runs did not complete")
        return 1
    if brks:                                    # a known answer: each break's property must be caught
        missed = [b for b in brks if not total.get(BREAKS[b][2])]
        print(f"FAIL: not caught: {', '.join(missed)}" if missed else "ok: every break caught")
        return 1 if missed else 0
    print("FAIL: violations" if total else "ok")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
