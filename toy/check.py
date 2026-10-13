#!/usr/bin/env python3
"""Check that protocol.md still runs as recorded.

    python3 check.py [-j N]      # run every cell, in parallel, and compare with golden.txt
    python3 check.py --update    # record the current results, after an intended change

A cell is a small run of run.py with --digest, which hashes every event the simulator processes, in
order: its time, its node, the function it runs, and its int and bytes arguments. A change in what
any node does, at any moment, changes the digest. An edit that should change nothing must leave
every digest as it is; one that changes behaviour shows which cells moved, with their warm medians
before and after, and --update records the new results, to be committed with the edit.
"""
import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden.txt"
BASE = ["--nodes", "60", "--degree", "30", "--msgs", "3", "--seed", "7"]
CELLS = {                               # name -> run.py's arguments on top of BASE
    "push": [],
    "hold": ["--rebuilt", "hold"],      # the same events as none: nobody asks for a held chunk (§4.6)
    "announce": ["--rebuilt", "announce"],
    "none": ["--rebuilt", "none"],
    "withholders": ["--fault", "wh30"],
    "silent": ["--fault", "sil30"],
    "cap-wait": ["--rb-max", "1", "--rb-jitter-ms", "20", "--fault", "sil30"],
    "dcb20": ["--net", "dcb20"],
    "rr-stripe": ["--uplink", "rr", "--stripe", "on"],
    "without-a": ["--without", "8,9,12,15"],
    "without-b": ["--without", "11,13,14,17"],
    "loss-thin": ["--loss-data", "10", "--up", "20"],
}
WARM = re.compile(r"^warm median: (p50 \S+ p99 \S+ copies \S+)", re.M)
DIGEST = re.compile(r"^digest ([0-9a-f]{64})$", re.M)


def run(name):
    """(digest, warm medians) of one cell, or (None, the end of its output) if it failed."""
    p = subprocess.run([sys.executable, "-B", "run.py", *BASE, *CELLS[name], "--digest"],
                       cwd=HERE, capture_output=True, text=True)
    d, w = DIGEST.search(p.stdout), WARM.search(p.stdout)
    if p.returncode or not d or not w:
        return None, (p.stdout + p.stderr).strip().splitlines()[-1:]
    return d.group(1)[:16], w.group(1)


def read_golden():
    out = {}
    if GOLDEN.exists():
        for line in GOLDEN.read_text().splitlines():
            if line and not line.startswith("#"):
                name, digest, warm = line.split(None, 2)
                out[name] = (digest, warm)
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="write golden.txt from this run")
    ap.add_argument("-j", type=int, default=min(len(CELLS), os.cpu_count() or 1))
    a = ap.parse_args(argv)
    with ThreadPoolExecutor(a.j) as ex:
        got = dict(zip(CELLS, ex.map(run, CELLS)))
    failed = [n for n, (d, _) in got.items() if d is None]
    for n in failed:
        print(f"{n}: FAILED: {' '.join(got[n][1])}")
    if a.update:
        if failed:
            return 1
        lines = [f"# cell, digest, warm medians: check.py's cells (run.py {' '.join(BASE)} ... --digest)"]
        lines += [f"{n} {d} {w}" for n, (d, w) in got.items()]
        GOLDEN.write_text("\n".join(lines) + "\n")
        print(f"recorded {len(got)} cells in {GOLDEN.name}")
        return 0
    want, bad = read_golden(), len(failed)
    for n, (d, w) in got.items():
        if d is None:
            continue
        if n not in want:
            print(f"{n}: not recorded ({w})")
            bad += 1
        elif want[n][0] != d:
            print(f"{n}: CHANGED: was {want[n][1]}, now {w}")
            bad += 1
        else:
            print(f"{n}: same")
    for n in sorted(set(want) - set(got)):
        print(f"{n}: recorded but no longer a cell")
        bad += 1
    print("ok" if not bad else f"{bad} of {len(CELLS)} cells differ from {GOLDEN.name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
