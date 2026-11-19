#!/usr/bin/env python3
"""Trace check.py's cells with trace3.py and replay each through the twin.

    python3 cells3.py TOYDIR OUTDIR [-j N] [--replay BINARY] [--doc v2] [CELL ...]

Per cell, in OUTDIR: <cell>.jsonl.gz (the trace), <cell>.out and <cell>.err (run.py's output and the tracer's),
<cell>.replay (the replay's report). A cell passes when its digest is the golden one (the tracer and its views
perturb nothing), every record replays, and its first line is this tree's content line, its header of the
cell's kind (header3.py). The replay is given the tree's content line (content.py), written once to OUTDIR.

With --doc v2 the cells are protocol-v2.md's (check.py --doc v2, against golden-v2.txt). Their records are
replayed too: trace3.py traces under v2 only the names that are protocol.md's all the way down, so each record is
of the twin's protocol.md, called in v2's states.

Each run is a plain child, under the caller's limits.
"""
import argparse
import re
import subprocess
import sys
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content                          # noqa: E402
import header3                          # noqa: E402
import layout                           # noqa: E402
from layout import REPLAY               # noqa: E402


def golden(path):
    out = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            name, digest, _ = line.split(None, 2)
            out[name] = digest
    return out


def one(toy, out, base, name, args, want, head, replay):
    tr = out / f"{name}.jsonl.gz"
    with open(out / f"{name}.out", "w") as so, open(out / f"{name}.err", "w") as se:
        p = subprocess.run([*layout.python(out), str(HERE / "trace3.py"), str(toy), str(tr),
                            *base, *args, "--digest"], cwd=toy, stdout=so, stderr=se)
    text = (out / f"{name}.out").read_text()
    m = re.search(r"^digest ([0-9a-f]{64})$", text, re.M)
    digest = m.group(1)[:16] if m else None
    hok = not header3.check(toy, tr)
    if replay is None:
        return name, p.returncode, digest == want, None, None, hok, None
    with open(out / f"{name}.replay", "w") as ro:
        # pipefail: the trace's reader failing fails the cell too, not the replay's status alone
        q = subprocess.run(["bash", "-c", f"set -o pipefail; zcat {tr} | {replay} --content {head}"], stdout=ro,
                           stderr=subprocess.STDOUT)
    rep = (out / f"{name}.replay").read_text()
    m = re.search(r"^replay: (\d+) records, (\d+) ok, (\d+) mismatched$", rep, re.M)
    f = re.search(r"^reads of the Python's that the twin did not make: (\d+)$", rep, re.M)
    return name, p.returncode, digest == want, m.groups() if m else None, q.returncode, hok, f.group(1) if f else None


def refusals(text):
    """The replay's refusals of a header or of a nodes line (its echo of the header, `header: {...`, is none)."""
    return [x for x in text.splitlines() if x.startswith("nodes: ") or (x.startswith("header: ") and not x.startswith("header: {"))]


def read_two(replay, head, text):
    """The replay on a content line, a header and a nodes line alone: its refusals of either of the two, or of the
    content line. It must have run to its end: exit code 0 or 1 (three lines have no trailer, which is a 1), and
    its line of the count there. Anything else is a refusal of its own, so that a replay that did not start or
    stopped is not read as "it refused nothing"."""
    q = subprocess.run([replay, "--content", head], input=text, capture_output=True, text=True)
    out = q.stdout + q.stderr
    if q.returncode not in (0, 1) or "replay: 0 records, 0 ok, 0 mismatched" not in out.splitlines():
        return [f"the replay did not run to its end on the three lines (exit code {q.returncode})"]
    return [x for x in out.splitlines() if x.startswith("content: ") and not x.startswith("content: as --content's, ")] + refusals(out)


def nodes_line(toy, out, base, name, args, head, replay):
    """--nodes-lines: a cell's header and nodes line alone, read by the replay. The cell is traced with no message
    published (`--msgs 0`: heartbeats alone, seconds; the toy's own report then fails, which is not looked at), and
    its first two lines go to the replay. A nodes line the replay refuses fails every record with it: without-b's
    (a constant infinite where a card is off) was one, and no step before a full run traced that cell."""
    tr = out / f"{name}.jsonl.gz"
    with open(out / f"{name}.out", "w") as so, open(out / f"{name}.err", "w") as se:
        subprocess.run([*layout.python(out), str(HERE / "trace3.py"), str(toy), str(tr),
                        *base, *args, "--msgs", "0"], cwd=toy, stdout=so, stderr=se)
    try:
        with gzip.open(tr, "rt") as f:
            cl, two = f.readline(), [f.readline(), f.readline()]
    except (OSError, EOFError):
        cl, two = "", ["", ""]
    if not (cl.startswith('{"content"') and two[0].startswith('{"header"') and two[1].startswith('{"nodes"')):
        return name, None, ["the trace does not begin with a content line, a header and a nodes line"]
    return name, [cl + two[0], two[1]], read_two(replay, head, cl + "".join(two))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("--replay", default=str(REPLAY))
    ap.add_argument("--doc", default="v03", choices=("v03", "v2"))
    ap.add_argument("--nodes-lines", action="store_true",
                    help="each cell's header and nodes line alone, read by the replay (no message published: seconds)")
    ap.add_argument("cells", nargs="*")
    a = ap.parse_intermixed_args(argv)
    toy, out = Path(a.toy).resolve(), Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(toy))
    import check                        # noqa: E402: the pinned toy's check.py, for its cells
    # a name that selects no cell must not end "ok" on fewer cells
    unknown = [n for n in a.cells if n not in check.CELLS]
    if unknown:
        print(f"cells3: not a cell of check.py: {', '.join(unknown)}", file=sys.stderr)
        return 2
    cells = {n: c for n, c in check.CELLS.items() if not a.cells or n in a.cells}
    if not cells:
        print("cells3: no cell selected", file=sys.stderr)
        return 2
    v2 = a.doc == "v2"
    want = golden(toy / ("golden-v2.txt" if v2 else "golden.txt"))
    extra = ["--doc", "v2"] if v2 else []
    replay = a.replay                   # v2's records are replayed too
    head = str(out / "content.line")    # the tree's content line, which every replay here is given
    Path(head).write_text(content.line(content.content(toy)))
    if a.nodes_lines:
        with ThreadPoolExecutor(a.j) as ex:
            res = list(ex.map(lambda nc: nodes_line(toy, out, check.BASE, nc[0], [*nc[1], *extra], head, replay),
                              cells.items()))
        bad = 0
        for name, two, why in res:
            bad += bool(why)
            print(f"{name}: its header and nodes line " + ("read by the replay" if not why else f"REFUSED: {why[0][:200]}  <-- FAIL"))
        # the screen's own control: a nodes line that must be refused (a constant taken out of the first cell's)
        two = next((t for _, t, _ in res if t), None)
        seen = False
        if two:
            d = json.loads(two[1])
            d["nodes"][0]["consts"].pop("PROMISE")
            seen = any("no PROMISE" in x for x in read_two(replay, head, two[0] + json.dumps(d, separators=(",", ":")) + "\n"))
        print(f"control, a nodes line without PROMISE: {'refused, and seen' if seen else 'NOT seen  <-- FAIL'}")
        bad += not seen
        print("ok" if not bad else f"{bad} of {len(res) + 1} lines fail")
        return 1 if bad else 0
    with ThreadPoolExecutor(a.j) as ex:
        res = list(ex.map(lambda nc: one(toy, out, check.BASE, nc[0], [*nc[1], *extra], want.get(nc[0]), head, replay),
                          cells.items()))
    bad = 0
    for name, rc, same, counts, qrc, hok, fewer in res:
        ok = rc == 0 and same and hok and counts is not None and counts[2] == "0" and qrc == 0
        bad += not ok
        rep = (f", replay {'/'.join(counts) if counts else 'no report'} (records/ok/mismatched), "
               f"rc={qrc}, reads the twin did not make {fewer}")      # v2's too
        print(f"{name}: trace rc={rc}, digest {'as ' + ('golden-v2.txt' if v2 else 'golden.txt') if same else 'DIFFERS'}"
              f"{rep}, header {'as these tools and these documents' if hok else 'DIFFERS'}"
              f"{'' if ok else '  <-- FAIL'}")
    print("ok" if not bad else f"{bad} of {len(res)} cells fail")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
