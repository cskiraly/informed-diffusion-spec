#!/usr/bin/env python3
"""A run of the record's driver against a record: are its traces the record's?

    python3 against.py RECORD RUN      two directories, each with record-manifest.txt and content.line
    python3 against.py --matrix RECORD MERGED   the matrix's traces (MERGED: `mutants3.py --merge`'s directory,
                                       or one part's) against the record's, by body
    python3 against.py --bodies RECORD RUN      every trace of either manifest in the other, by body, counted by
                                       directory; a manifest of an earlier kit (no twin or mutants line) is read
    python3 against.py --bodies-in RECORD HASHES   each trace a list names ("WHOLE  BODY  NAME" lines, as
                                       `content.py --hashes` writes them) is the record's, by body, as --matrix
    python3 against.py --self-test

A manifest (record.sh's step `manifest`) names what a run was made from and by, and each trace by its two hashes:
the whole trace, and its body, the trace from its second line on (content.py). One of three results, on the last
line, with the exit code:

  0  as recorded: the same content, twin, replay and mutants, and every trace's two hashes the record's
  3  another content, the same bodies: a file the content line names differs (each is listed), and every trace's
     records are the record's all the same; the twin, the replay and the mutants are the record's
  1  NOT the record's: a trace's body differs, a trace is missing or one more, or the twin, the replay or the
     mutants are others (each is listed)

The Python's line (its version and platform) is reported where it differs and decides nothing: the traces' bytes
do. The documents line, where a manifest has one, is reported the same way and decides nothing either. It gives
the sha256 of each document's file, for the record's provenance. The content line names the documents by their
code (content.py, version 2), so an edit of their prose alone changes the documents line and not the content
line. A content line of version 1 against one of version 2 counts as another content, and the report names the
version. Exit code 2: a manifest that cannot be read as one.

--matrix: a matrix replays its mutants on traces of its own making (its traces.sha256 and directed.sha256, each
line "WHOLE  BODY  NAME"). Its traces are the record's where each has a line in the record's manifest with the same
body: exit code 0, "the matrix's N traces are the record's, by body"; 1 where one is missing from the record or
has another body (each is named); 2 where a file cannot be read. The whole hashes may differ (another content: a
tool changed between the two runs) and are counted, not judged.

--bodies: the bodies alone, both ways, for a record made before the manifest named its twin and its mutants, or
a run of another base. Each trace with another body, or in one manifest alone, is named; then a line a
directory (`traces/`, `directed/`, `v2/`): how many of its traces have the record's body. The head lines both
manifests have are reported where they differ (the replay's above all), and decide nothing. Exit code 0: every
trace of each in the other, with its body; 1: not so; 2: a manifest that cannot be read.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content                          # noqa: E402

HEAD = ("content", "python", "replay", "twin", "mutants")
INFO = ("documents",)                   # a head line that a manifest may have, reported where it differs, deciding nothing
TRACE = re.compile(r"([0-9a-f]{64})  ([0-9a-f]{64})  (\S+)")


class Unreadable(Exception):
    pass


def manifest(text, whole=True):
    """({content, python, replay, twin, mutants, and documents where it is: the line's text after its word},
    {trace: (whole, body)}). With
    whole=False (--matrix, which compares traces alone) a head line may be missing: a manifest of an earlier kit."""
    head, traces = {}, {}
    for l in text.splitlines():
        m = TRACE.fullmatch(l)
        if m:
            if m[3] in traces:
                raise Unreadable(f"a trace twice: {m[3]}")
            traces[m[3]] = (m[1], m[2])
            continue
        word, _, rest = l.partition(" ")
        if word not in HEAD + INFO or word in head or not rest:
            raise Unreadable(f"not a line of a manifest, or a line twice: {l[:80]!r}")
        head[word] = rest
    if (whole and not set(HEAD) <= set(head)) or not traces:
        raise Unreadable(f"a manifest without {sorted(set(HEAD) - set(head)) or 'a trace'}")
    return head, traces


def compare(rec, run, rec_content=None, run_content=None):
    """(the exit code, the lines to print). The two content lines are given where the files that differ are to be
    named."""
    (rh, rt), (uh, ut) = rec, run
    out, bad = [], False
    for w in ("twin", "replay", "mutants"):
        if rh[w].split()[:2] != uh[w].split()[:2] if w == "mutants" else rh[w].split()[0] != uh[w].split()[0]:
            out.append(f"{w}: the record's {rh[w][:90]}, the run's {uh[w][:90]}")
            bad = True
    if rh["python"] != uh["python"]:
        out.append(f"(python: the record's {rh['python']}, the run's {uh['python']}: reported, it decides nothing)")
    if rh.get("documents") != uh.get("documents"):
        out.append(f"(documents: the record's {rh.get('documents', 'none')}, the run's "     # whole: two hashes
                   f"{uh.get('documents', 'none')}: reported, it decides nothing)")
    for n in sorted(set(rt) - set(ut)):
        out.append(f"{n}: in the record, not in the run")
        bad = True
    for n in sorted(set(ut) - set(rt)):
        out.append(f"{n}: in the run, not in the record")
        bad = True
    bodies = [n for n in sorted(set(rt) & set(ut)) if rt[n][1] != ut[n][1]]
    for n in bodies:
        out.append(f"{n}: its body is another: the record's {rt[n][1][:16]}…, the run's {ut[n][1][:16]}…")
    whole = [n for n in sorted(set(rt) & set(ut)) if rt[n][1] == ut[n][1] and rt[n][0] != ut[n][0]]
    same_content = rh["content"].split()[0] == uh["content"].split()[0]
    if bad or bodies:
        return 1, out + [f"NOT the record's: {len(bodies)} of {len(rt)} traces' bodies differ"
                         + ("; and what is listed above" if bad else "")]
    if same_content and not whole:
        return 0, out + [f"as recorded: the same content, twin, replay and mutants; {len(rt)} traces, each hash the record's"]
    if same_content:                    # one content line, one body, another whole: not possible for a trace of this kit
        return 1, out + [f"NOT the record's: {len(whole)} traces have the record's content and body and another whole hash"]
    if rec_content is not None and run_content is not None:
        try:
            out += [f"content: {d}" for d in content.diff(json.loads(rec_content), json.loads(run_content))]
        except (ValueError, KeyError, TypeError):
            out.append("content: a content line cannot be read; the files that differ are not named")
    return 3, out + [f"another content, the same bodies: {len(rt)} traces, each body the record's "
                     f"(the first in the lines above is the record's, the second the run's)"]


def matrix_against(rec_traces, mx_lines, what="the matrix's"):
    """(exit code, lines): the matrix's traces (or a list's: `what`) against the record's, by body."""
    out, bad, whole = [], 0, 0
    if not mx_lines:
        return 2, [f"{what} names no trace"]
    for l in mx_lines:
        m = TRACE.fullmatch(l)
        if not m:
            return 2, [f"not a line of a trace's two hashes: {l[:80]!r}"]
        name = m[3]
        if name not in rec_traces:
            out.append(f"{name}: in {what[:-2]}, not in the record"); bad += 1
        elif rec_traces[name][1] != m[2]:
            out.append(f"{name}: its body is another: the record's {rec_traces[name][1][:16]}…, {what} {m[2][:16]}…"); bad += 1
        elif rec_traces[name][0] != m[1]:
            whole += 1
    if bad:
        return 1, out + [f"NOT the record's: {bad} of {what} {len(mx_lines)} traces"]
    return 0, out + [f"{what} {len(mx_lines)} traces are the record's, by body"
                     + (f" ({whole} with another whole hash: another content)" if whole else " (and by their whole hashes)")]


def bodies_against(rec, run):
    """(exit code, lines): every trace of each manifest in the other, by body; counted by directory."""
    (rh, rt), (uh, ut) = rec, run
    out = []
    for w in HEAD:
        if w in rh and w in uh and rh[w] != uh[w]:
            out.append(f"({w}: the record's {rh[w][:90]}, the run's {uh[w][:90]}: reported, it decides nothing)")
    bad, by = 0, {}
    for n in sorted(set(rt) | set(ut)):
        d = n.split("/")[0] + "/" if "/" in n else "./"
        same, total = by.get(d, (0, 0))
        if n not in ut:
            out.append(f"{n}: in the record, not in the run"); bad += 1
        elif n not in rt:
            out.append(f"{n}: in the run, not in the record"); bad += 1
        elif rt[n][1] != ut[n][1]:
            out.append(f"{n}: its body is another: the record's {rt[n][1][:16]}…, the run's {ut[n][1][:16]}…"); bad += 1
        else:
            same += 1
        by[d] = (same, total + 1)
    out += [f"{d}: {s} of {t} traces with the record's body" for d, (s, t) in sorted(by.items())]
    n = len(set(rt) | set(ut))
    if bad:
        return 1, out + [f"NOT every trace's body the record's: {bad} of {n} traces differ or are in one manifest alone"]
    return 0, out + [f"every trace's body the record's: {n} of {n}, both ways"]


def self_test():
    H = lambda c: c * 64                # noqa: E731
    base = (f"content {H('a')}\npython 3.12.3 x86_64 linux\nreplay {H('b')}\ntwin {H('c')} (32 files: twin-sources.txt)\n"
            f"mutants 554 {H('d')} (their names, in the tool's order)\n{H('1')}  {H('2')}  traces/none.jsonl.gz\n"
            f"{H('3')}  {H('4')}  directed/directed.jsonl.gz\n")
    c1 = content.line({"content": {"version": 1, "files": {"protocol.md": H("1"), "toy/node.py": H("2")}}})
    c2 = content.line({"content": {"version": 1, "files": {"protocol.md": H("9"), "toy/node.py": H("2")}}})
    other = base.replace(f"content {H('a')}", f"content {H('e')}").replace(f"{H('1')}  {H('2')}", f"{H('5')}  {H('2')}") \
                .replace(f"{H('3')}  {H('4')}", f"{H('6')}  {H('4')}")
    cases = [
        ("the record against itself", base, 0, "as recorded: "),
        ("another Python, the same bytes", base.replace("3.12.3", "3.13.5"), 0, "as recorded: "),
        ("another content, every body the record's", other, 3, "another content, the same bodies: 2 traces"),
        ("another content, and one body another", other.replace(f"{H('6')}  {H('4')}", f"{H('6')}  {H('7')}"), 1,
         "NOT the record's: 1 of 2 traces' bodies differ"),
        ("the same content, one body another", base.replace(f"{H('3')}  {H('4')}", f"{H('8')}  {H('7')}"), 1,
         "NOT the record's: 1 of 2"),
        ("the same content and bodies, one whole hash another", base.replace(f"{H('1')}  {H('2')}", f"{H('5')}  {H('2')}"), 1,
         "another whole hash"),
        ("a trace missing", base.replace(f"{H('3')}  {H('4')}  directed/directed.jsonl.gz\n", ""), 1, "in the record, not in the run"),
        ("a trace more", base + f"{H('3')}  {H('4')}  v2/none.jsonl.gz\n", 1, "in the run, not in the record"),
        ("another twin", base.replace(f"twin {H('c')}", f"twin {H('f')}"), 1, "twin: the record's"),
        ("another replay", base.replace(f"replay {H('b')}", f"replay {H('f')}"), 1, "replay: the record's"),
        ("one mutant more", base.replace("mutants 554", "mutants 555"), 1, "mutants: the record's"),
        ("other mutants' names", base.replace(f"mutants 554 {H('d')}", f"mutants 554 {H('f')}"), 1, "mutants: the record's"),
    ]
    bad = 0
    for name, run, want, words in cases:
        rc, out = compare(manifest(base), manifest(run), c1, c2)
        ok = rc == want and any(words in l for l in out)
        bad += not ok
        print(f"against self-test, {name}: exit code {rc}, must be {want}; "
              f"{'says' if any(words in l for l in out) else 'does NOT say'}: {words}{'' if ok else '  <-- FAIL'}")
    rc, out = compare(manifest(base), manifest(other), c1, c2)
    ok = "content: protocol.md: other bytes" in out
    bad += not ok
    print(f"against self-test, another content names the file that differs: {'so' if ok else 'NOT so  <-- FAIL'}")
    c3 = content.line({"content": {"version": 2, "files": {"protocol.md": H("9"), "toy/node.py": H("2")}}})
    rc, out = compare(manifest(base), manifest(other), c1, c3)
    ok = rc == 3 and "content: the version of the content's form differs" in out
    bad += not ok
    print(f"against self-test, a record of content version 1 against a run of version 2: exit code {rc}, the version "
          f"named: {'so' if ok else 'NOT so  <-- FAIL'}")
    docs = f"documents protocol.md {H('7')} protocol-v2.md {H('8')} (each file's sha256: reported, it decides nothing)\n"
    for name, rec, run, want, words in (
            ("a documents line in both, the same", base + docs, base + docs, 0, "as recorded: "),
            ("a documents line in both, another document's bytes", base + docs, base + docs.replace(H("8"), H("9")), 0,
             "(documents: the record's"),
            ("a documents line in the run alone (a record of an earlier kit)", base, base + docs, 0, "(documents: the record's none"),
            ("a documents line in both, the second document's hash another in its last digit", base + docs,
             base + docs.replace(H("8"), H("8")[:-1] + "9"), 0, f"the run's protocol.md {H('7')} protocol-v2.md {H('8')[:-1]}9")):
        try:
            rc, out = compare(manifest(rec), manifest(run), c1, c1)
            ok = rc == want and any(words in l for l in out)
        except Unreadable as e:
            rc, out, ok = None, [str(e)], False
        bad += not ok
        print(f"against self-test, {name}: exit code {rc}, must be {want}; "
              f"{'says' if any(words in l for l in out) else 'does NOT say'}: {words}{'' if ok else '  <-- FAIL'}")
    for name, text in (("no trace", "\n".join(base.splitlines()[:5]) + "\n"), ("a head line twice", base + f"content {H('a')}\n"),
                       ("a line that is none of a manifest's", base + "something else\n"), ("no twin line", base.replace(f"twin {H('c')} (32 files: twin-sources.txt)\n", ""))):
        try:
            manifest(text)
            ok = False
        except Unreadable:
            ok = True
        bad += not ok
        print(f"against self-test, a manifest with {name}: {'refused' if ok else 'read  <-- FAIL'}")
    rec = manifest(base)[1]
    mx = [f"{H('1')}  {H('2')}  traces/none.jsonl.gz", f"{H('3')}  {H('4')}  directed/directed.jsonl.gz"]
    for name, lines, want, words in (
            ("a matrix's traces, the record's", mx, 0, "the matrix's 2 traces are the record's, by body (and by"),
            ("another content, the same bodies", [mx[0].replace(H('1'), H('5'), 1), mx[1]], 0, "(1 with another whole hash"),
            ("a body another", [mx[0], mx[1].replace(H('4'), H('7'))], 1, "directed/directed.jsonl.gz: its body is another"),
            ("a trace the record does not have", mx + [f"{H('3')}  {H('4')}  traces/hand5.jsonl.gz"], 1, "in the matrix, not in the record"),
            ("a line that is no trace's", ["x"], 2, "not a line of a trace's two hashes")):
        rc, out = matrix_against(rec, lines)
        ok = rc == want and any(words in l for l in out)
        bad += not ok
        print(f"against self-test, --matrix, {name}: exit code {rc}, must be {want}{'' if ok else '  <-- FAIL'}")
    for name, lines, want, words in (
            ("a list's one trace, the record's, another content", [mx[0].replace(H('1'), H('5'), 1)], 0,
             "the list's 1 traces are the record's, by body (1 with another whole hash"),
            ("a list's one trace, another body", [mx[0].replace(H('2'), H('7'))], 1,
             "traces/none.jsonl.gz: its body is another: the record's")):
        rc, out = matrix_against(rec, lines, what="the list's")
        ok = rc == want and any(words in l for l in out)
        bad += not ok
        print(f"against self-test, --bodies-in, {name}: exit code {rc}, must be {want}{'' if ok else '  <-- FAIL'}")
    early = "\n".join(l for l in base.splitlines() if not l.startswith(("twin ", "mutants "))) + "\n"   # an earlier kit's
    v2 = f"{H('7')}  {H('8')}  v2/none.jsonl.gz\n"
    for name, r_text, u_text, want, words in (
            ("an earlier kit's record, the same bodies, another content", early + v2, other + v2, 0,
             "every trace's body the record's: 3 of 3, both ways"),
            ("the same, by directory", early + v2, other + v2, 0, "v2/: 1 of 1 traces with the record's body"),
            ("a v2 body another: named, and counted in its directory", early + v2, other + v2.replace(H('8'), H('9')), 1,
             "v2/: 0 of 1 traces with the record's body"),
            ("a trace in the record alone", early + v2, other, 1, "v2/none.jsonl.gz: in the record, not in the run"),
            ("a trace in the run alone", early, other + v2, 1, "v2/none.jsonl.gz: in the run, not in the record"),
            ("another replay: reported, deciding nothing", early, base.replace(f"replay {H('b')}", f"replay {H('f')}"), 0,
             "(replay: the record's")):
        rc, out = bodies_against(manifest(r_text, whole=False), manifest(u_text, whole=False))
        ok = rc == want and any(words in l for l in out)
        bad += not ok
        print(f"against self-test, --bodies, {name}: exit code {rc}, must be {want}{'' if ok else '  <-- FAIL'}")
    print("ok: every case as it must be" if not bad else f"{bad} cases wrong")
    return 1 if bad else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) == 3 and argv[0] == "--matrix":
        try:
            rec = manifest((Path(argv[1]) / "record-manifest.txt").read_text(), whole=False)[1]
            mx = [l for f in ("traces.sha256", "directed.sha256") for l in (Path(argv[2]) / f).read_text().splitlines() if l.strip()]
        except (OSError, Unreadable) as e:
            print(f"against: cannot be read: {e}")
            return 2
        rc, out = matrix_against(rec, mx)
        for l in out:
            print(l)
        return rc
    if len(argv) == 3 and argv[0] == "--bodies-in":
        try:
            rec = manifest((Path(argv[1]) / "record-manifest.txt").read_text(), whole=False)[1]
            lines = [l for l in Path(argv[2]).read_text().splitlines() if l.strip()]
        except (OSError, Unreadable) as e:
            print(f"against: cannot be read: {e}")
            return 2
        rc, out = matrix_against(rec, lines, what="the list's")
        for l in out:
            print(l)
        return rc
    if len(argv) == 3 and argv[0] == "--bodies":
        try:
            a = manifest((Path(argv[1]) / "record-manifest.txt").read_text(), whole=False)
            b = manifest((Path(argv[2]) / "record-manifest.txt").read_text(), whole=False)
        except (OSError, Unreadable) as e:
            print(f"against: cannot be read: {e}")
            return 2
        rc, out = bodies_against(a, b)
        for l in out:
            print(l)
        return rc
    if len(argv) != 2:
        print(__doc__)
        return 2
    rec, run = Path(argv[0]), Path(argv[1])
    try:
        a = manifest((rec / "record-manifest.txt").read_text())
        b = manifest((run / "record-manifest.txt").read_text())
        ca, cb = (rec / "content.line").read_text(), (run / "content.line").read_text()
    except (OSError, Unreadable) as e:
        print(f"against: cannot be read: {e}")
        return 2
    rc, out = compare(a, b, ca, cb)
    for l in out:
        print(l)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
