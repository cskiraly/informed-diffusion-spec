#!/usr/bin/env python3
"""Check that protocol.md (or protocol-v2.md on top of it) still runs as recorded.

    python3 check.py [-j N]                     # run every cell, in parallel, and compare with golden.txt
    python3 check.py --update                   # record the current results, after an intended change
    python3 check.py --doc v2                   # the same for protocol-v2.md's tier 4 setting, against golden-v2.txt
    python3 check.py --doc v2 --golden golden.txt   # version 2 against v0.3's recording: what the documents differ by

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


EXTRA = []                              # --doc v2: run protocol-v2.md's tier 4 setting against the same golden


def run(name):
    """(digest, warm medians) of one cell, or (None, the end of its output) if it failed."""
    p = subprocess.run([sys.executable, "-B", "run.py", *BASE, *CELLS[name], *EXTRA, "--digest"],
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
    ap.add_argument("--doc", default="v03", choices=("v03", "v2"),
                    help="v2: run protocol-v2.md on top of protocol.md (its tier 4 setting) against golden-v2.txt")
    ap.add_argument("--golden", default=None,
                    help="compare against this recording instead (e.g. --doc v2 --golden golden.txt: version 2 against "
                         "v0.3's cells; a cell whose digest moved but whose numbers did not is then reported as such)")
    a = ap.parse_args(argv)
    global GOLDEN
    if a.doc != "v03":
        EXTRA[:] = ["--doc", a.doc]
        GOLDEN = HERE / "golden-v2.txt"
    if a.golden:
        GOLDEN = HERE / a.golden
    cross = bool(a.golden) and GOLDEN.name != ("golden-v2.txt" if a.doc == "v2" else "golden.txt")
    print(f"checking --doc {a.doc} against {GOLDEN.name}")
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
        elif want[n][0] != d and want[n][1] == w:
            print(f"{n}: same numbers, digest differs ({w})")
            bad += 0 if cross else 1    # across documents, same-instant events reorder (protocol-v2.md §6.1)
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
