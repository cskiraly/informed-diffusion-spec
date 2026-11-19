#!/usr/bin/env python3
"""Two merged matrices of the same mutants, compared pair by pair: what each tells, and what one tells that the
other does not.

    python3 matrixdiff.py OLD NEW        two directories as `mutants3.py --merge` writes them
    python3 matrixdiff.py --self-test

A mutant is told on a trace where a record mismatches or a read of the Python's is not made (the pairs' count or
their reads above 0). Compared:
- the mutants: the two matrices must be of the same names, in the same order (mutants.sha256's names);
- the cells, (mutant, trace) by (mutant, trace), from mutants-pairs.txt: told in both, in OLD alone (lost), in NEW
  alone (gained); for a pair told in both, whether its count or its kinds moved;
- the directed sets, mutant by mutant: from mutants-directed-pairs.txt where both have one, (mutant, set) as for
  the cells; where OLD has none (a matrix made before the directed step wrote pairs), from each report's line of
  the mutant: told by a record or by reads not made, or not told.

A lost pair is printed with OLD's kinds for it: a pair told in OLD by `writes` alone is the kind a change of what a
record writes can take away (a pop that finds nothing, since trace format 7, is no write). Every lost pair is to be
read; this tool does not judge them.

The last line gives the counts. Exit code 0: nothing lost at the level of a mutant (every mutant told by the
directed sets in OLD is told by them in NEW, and every mutant told by a cell in OLD by a cell in NEW); 1: a mutant
lost (each is named); 2: the matrices cannot be compared (other mutants, a file missing).
"""
import ast
import re
import sys
from collections import Counter
from pathlib import Path

LINE = re.compile(r"^(\S+): .*?: (?:(\d+) mismatched records in (\d+) of (\d+) traces, by (\{.*?\})|no record mismatches); (\d+) reads not made")


class Unreadable(Exception):
    pass


def names(d):
    try:
        return [l.split()[1] for l in (Path(d) / "mutants.sha256").read_text().splitlines() if l.strip()]
    except (OSError, IndexError) as e:
        raise Unreadable(f"{d}: mutants.sha256: {e}")


def pairs(path):
    """{(mutant, trace): (count, reads, Counter of kinds)}, or None where there is no such file."""
    p = Path(path)
    if not p.exists():
        return None
    out = {}
    for l in p.read_text().splitlines():
        try:
            m, t, c, r, k = l.split(" ", 4)
            out[(m, t)] = (int(c), int(r), Counter(ast.literal_eval(k)))
        except (ValueError, SyntaxError) as e:
            raise Unreadable(f"{path}: not a pairs line: {l[:80]!r} ({e})")
    return out


def report(path):
    """{mutant: (records, reads)} from a report's mutant lines."""
    out = {}
    for l in Path(path).read_text().splitlines():
        m = LINE.match(l)
        if m:
            out[m[1]] = (int(m[2] or 0), int(m[6]))
    return out


def told(v):
    return v[0] > 0 or v[1] > 0


def compare(old, new):
    """(exit code, lines)."""
    out = []
    on, nn = names(old), names(new)
    if on != nn:
        return 2, [f"the two matrices are not of the same mutants in one order ({len(on)} and {len(nn)})"]
    lost_m, gained_m = [], []
    # the cells
    po, pn = pairs(Path(old) / "mutants-pairs.txt"), pairs(Path(new) / "mutants-pairs.txt")
    if po is None or pn is None:
        return 2, ["a cells' pairs file is missing"]
    if set(po) != set(pn):
        return 2, [f"the cells' pairs are not of the same (mutant, trace): {len(set(po) ^ set(pn))} differ"]
    both = lost = gained = moved = 0
    for key in po:
        a, b = told(po[key]), told(pn[key])
        if a and b:
            both += 1
            if po[key][0] != pn[key][0] or po[key][2] != pn[key][2]:
                moved += 1
        elif a:
            lost += 1
            out.append(f"cells, lost: {key[0]} on {key[1]}: OLD {po[key][0]} records, {po[key][1]} reads not made, {dict(po[key][2])}")
        elif b:
            gained += 1
            out.append(f"cells, gained: {key[0]} on {key[1]}: NEW {pn[key][0]} records, {pn[key][1]} reads not made, {dict(pn[key][2])}")
    for m in on:
        ta = any(told(po[k]) for k in po if k[0] == m)
        tb = any(told(pn[k]) for k in pn if k[0] == m)
        if ta and not tb:
            lost_m.append(f"cells: {m}")
        elif tb and not ta:
            gained_m.append(f"cells: {m}")
    cells_old = sum(1 for m in on if any(told(po[k]) for k in po if k[0] == m))
    cells_new = sum(1 for m in on if any(told(pn[k]) for k in pn if k[0] == m))
    out.append(f"cells: {len(po)} pairs: told in both {both} ({moved} with another count or kinds), lost {lost}, gained {gained}; "
               f"mutants told by a cell: OLD {cells_old}, NEW {cells_new} of {len(on)}")
    # the directed sets
    do, dn = pairs(Path(old) / "mutants-directed-pairs.txt"), pairs(Path(new) / "mutants-directed-pairs.txt")
    if do is not None and dn is not None:
        if set(do) != set(dn):
            return 2, out + [f"the directed pairs are not of the same (mutant, set): {len(set(do) ^ set(dn))} differ"]
        ta = {m: any(told(do[k]) for k in do if k[0] == m) for m in on}
        tb = {m: any(told(dn[k]) for k in dn if k[0] == m) for m in on}
        dl = sum(1 for k in do if told(do[k]) and not told(dn[k]))
        dg = sum(1 for k in do if told(dn[k]) and not told(do[k]))
        how = f"by their pairs: {len(do)} (mutant, set), lost {dl}, gained {dg}"
    else:
        ro, rn = report(Path(old) / "mutants-directed.txt"), report(Path(new) / "mutants-directed.txt")
        if set(ro) != set(on) or set(rn) != set(on):
            return 2, out + [f"a directed report does not have a line for each mutant ({len(ro)} and {len(rn)} of {len(on)})"]
        ta = {m: told(ro[m]) for m in on}
        tb = {m: told(rn[m]) for m in on}
        how = "by their reports' lines (OLD has no directed pairs)"
    for m in on:
        if ta[m] and not tb[m]:
            lost_m.append(f"directed: {m}")
        elif tb[m] and not ta[m]:
            gained_m.append(f"directed: {m}")
    out.append(f"directed sets, {how}; mutants told: OLD {sum(ta.values())}, NEW {sum(tb.values())} of {len(on)}")
    for x in lost_m:
        out.append(f"a mutant LOST: {x}")
    for x in gained_m:
        out.append(f"a mutant gained: {x}")
    out.append(f"{len(lost_m)} mutants lost, {len(gained_m)} gained")
    return (1 if lost_m else 0), out


def self_test():
    import tempfile
    d = Path(tempfile.mkdtemp())
    bad = 0

    def matrix(name, cells, directed=None, report_lines=None, mutants=("m1", "m2", "m3")):
        p = d / name
        p.mkdir()
        (p / "mutants.sha256").write_text("".join(f"{'0' * 64}  {m}\n" for m in mutants))
        (p / "mutants-pairs.txt").write_text("".join(f"{m} {t} {c} {r} {k}\n" for (m, t), (c, r, k) in cells.items()))
        if directed is not None:
            (p / "mutants-directed-pairs.txt").write_text("".join(f"{m} {t} {c} {r} {k}\n" for (m, t), (c, r, k) in directed.items()))
        (p / "mutants-directed.txt").write_text("".join(l + "\n" for l in (report_lines or [])))
        return p
    E = "{}"
    cells = {("m1", "a"): (3, 0, "{'tape': 3}"), ("m1", "b"): (0, 0, E), ("m2", "a"): (0, 0, E), ("m2", "b"): (1, 0, "{'writes': 1}"),
             ("m3", "a"): (0, 0, E), ("m3", "b"): (0, 0, E)}
    dpairs = {("m1", "d"): (5, 0, "{'tape': 5}"), ("m2", "d"): (2, 0, "{'post': 2}"), ("m3", "d"): (0, 1, E)}
    rep = ["m1: x: 5 mismatched records in 1 of 22 traces, by {'tape': 5}; 0 reads not made",
           "m2: x: 2 mismatched records in 1 of 22 traces, by {'post': 2}; 0 reads not made",
           "m3: x: no record mismatches; 1 reads not made"]
    a = matrix("a", cells, dpairs, rep)
    cases = []
    rc, out = compare(a, a)
    cases.append(("a matrix against itself", rc == 0 and out[-1] == "0 mutants lost, 0 gained"))
    c2 = dict(cells); c2[("m2", "b")] = (0, 0, E)
    rc, out = compare(a, matrix("b", c2, dpairs, rep))
    cases.append(("a mutant's one cell pair lost", rc == 1 and "a mutant LOST: cells: m2" in out
                  and any(l.startswith("cells, lost: m2 on b: OLD 1 records, 0 reads not made, {'writes': 1}") for l in out)))
    c3 = dict(cells); c3[("m1", "a")] = (7, 0, "{'tape': 7}")
    rc, out = compare(a, matrix("c", c3, dpairs, rep))
    cases.append(("a pair's count moved, nothing lost", rc == 0 and any("(1 with another count or kinds)" in l for l in out)))
    d2 = dict(dpairs); d2[("m3", "d")] = (0, 0, E)
    rc, out = compare(a, matrix("e", cells, d2, rep))
    cases.append(("a mutant lost on the directed sets, by pairs", rc == 1 and "a mutant LOST: directed: m3" in out))
    old = matrix("f", cells, None, rep)
    rep2 = rep[:2] + ["m3: x: no record mismatches; 0 reads not made  <-- no record tells it from the twin"]
    rc, out = compare(old, matrix("g", cells, dpairs, rep2))
    cases.append(("OLD without directed pairs: by the reports' lines, a mutant lost", rc == 1 and "a mutant LOST: directed: m3" in out))
    rc, out = compare(old, matrix("h", cells, dpairs, rep))
    cases.append(("OLD without directed pairs: by the reports' lines, nothing lost", rc == 0))
    c4 = dict(cells); c4[("m3", "a")] = (2, 0, "{'return': 2}")
    rc, out = compare(a, matrix("i", c4, dpairs, rep))
    cases.append(("a mutant gained by a cell", rc == 0 and "a mutant gained: cells: m3" in out))
    rc, out = compare(a, matrix("j", cells, dpairs, rep, mutants=("m1", "m3", "m2")))
    cases.append(("other mutants' order", rc == 2))
    c5 = dict(cells); del c5[("m3", "b")]
    rc, out = compare(a, matrix("k", c5, dpairs, rep))
    cases.append(("a pair missing", rc == 2))
    for name, ok in cases:
        bad += not ok
        print(f"matrixdiff self-test, {name}: {'as it must be' if ok else 'NOT  <-- FAIL'}")
    print("ok: every case as it must be" if not bad else f"{bad} cases wrong")
    return 1 if bad else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        rc, out = compare(argv[0], argv[1])
    except (OSError, Unreadable) as e:
        print(f"matrixdiff: cannot be read: {e}")
        return 2
    for l in out:
        print(l)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
