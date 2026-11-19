#!/usr/bin/env python3
"""The controls of the content line: a trace names what it was made from, and what ran is what it names.

    python3 contentcontrols.py TOYDIR WORKDIR REPLAY TRACE

TRACE is the 5-node hand-counted cell's trace with §6.1's twelve traced alone (the check's `hand5-sec61`), made
from this tree. Each case copies the tree (the two documents, the toy, these tools) to a place of its own under
WORKDIR, changes one thing, and traces the same cell there. What each must give is written here before it ran:

- the tree copied, unchanged, traced from another place and another directory: the trace's bytes are TRACE's, and
  the replay, given this tree's content line, passes it;
- a document, a file of the toy or a tool with other bytes, or a module more in the toy: the tracer runs, the
  trace from its second line on is TRACE's byte for byte (the change touches nothing this cell runs), its first
  line is another, and the replay refuses it and names the file;
- a name the line cannot hold, or a link, under the toy: the tracer stops before it writes;
- a bytecode file of other code beside a source of the toy: a Python that looks for bytecode beside the sources
  runs it (the case shows that first), the tracers' Python does not, and the trace's bytes are TRACE's;
- a tracer started in a way that lets something else run than the line names: not isolated (with a module of
  another directory on PYTHONPATH), with no bytecode prefix, writing bytecode, optimised, with a dump named on
  its command line, with its output under the toy, or from a program outside the tools: each refused, for its
  reason, and none leaves a trace that the replay passes.

Not controlled here: a file changed while a trace is made (the tracer makes the line again at the trace's end and
compares; no case changes a file under a running tracer).

It prints one line a case and, at the end, "ok: every control of the content line as it must be", and exits 0;
or it says how many are wrong and exits 1.
"""
import gzip
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content                          # noqa: E402
import layout                           # noqa: E402

ARGS = ["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7", "--digest"]
ENV = {"TRACE3_ONLY": "sec61"}


def copy_tree(toy, to):
    """The tree the content line names, at `to`: the documents, the toy and the tools at their places."""
    toy = Path(toy).resolve()
    if to.exists():
        shutil.rmtree(to)
    ign = shutil.ignore_patterns("__pycache__")
    (to / "formal" / "twin").mkdir(parents=True)
    for d in ("protocol.md", "protocol-v2.md"):
        shutil.copyfile(toy.parent / d, to / d)
    shutil.copytree(toy, to / "toy", ignore=ign)
    shutil.copytree(HERE, to / "formal" / "twin" / "tools", ignore=ign)
    return to


def trace(tree, out, py, env=None, args=ARGS, program=None, cwd=None):
    """The cell traced in `tree` by its own copy of the tools. The exit code and what the tracer said."""
    program = program or tree / "formal" / "twin" / "tools" / "trace3.py"
    e = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    e.update(ENV)
    e.update(env or {})
    p = subprocess.run([*py, str(program), str(tree / "toy"), str(out), *args], cwd=cwd or tree / "toy", env=e,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def lines(path):
    """A trace's first line and the rest, as bytes; (None, None) where there is no trace to read."""
    try:
        with gzip.open(path, "rb") as f:
            first = f.readline()
            return first, f.read()
    except (OSError, EOFError):
        return None, None


def replay(exe, cfile, path):
    try:
        with gzip.open(path, "rb") as f:
            data = f.read()
    except (OSError, EOFError):
        return None, "no trace to read"
    p = subprocess.run([str(exe), "--content", str(cfile)], input=data, capture_output=True)
    return p.returncode, (p.stdout + p.stderr).decode(errors="replace")


def main(argv):
    toy, work, exe, given = Path(argv[0]).resolve(), Path(argv[1]).resolve(), Path(argv[2]).resolve(), Path(argv[3])
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    py = layout.python(work)
    cfile = work / "content.line"
    cfile.write_text(content.line(content.content(toy)))
    first0, body0 = lines(given)
    assert first0 == cfile.read_bytes(), "TRACE's first line is not this tree's content line"
    hdr = json.loads(body0.split(b"\n", 1)[0])["header"]
    assert hdr["args"] == ARGS and len(hdr["traced"]) == 12, "TRACE is not the hand cell's trace of §6.1's twelve"
    bad = 0

    def say(name, ok, got, must):
        nonlocal bad
        bad += not ok
        print(f"content, {name}: {got}; must be: {must}{'' if ok else '  <-- FAIL'}")

    def passes(out):                    # does the replay, given this tree's line, pass the trace at `out`?
        rc, text = replay(exe, cfile, out)
        return rc == 0 and "content: as --content's" in text

    # 1. the same tree at another place
    t = copy_tree(toy, work / "same" / "elsewhere" / "tree")
    out = work / "same.jsonl.gz"
    rc, said = trace(t, out, py, cwd=work)
    f, b = lines(out)
    say("the tree copied to another place, traced from another directory",
        rc == 0 and f == first0 and b == body0 and passes(out),
        f"tracer rc={rc}, first line {'the same' if f == first0 else 'ANOTHER'}, the rest "
        f"{'the same' if b == body0 else 'ANOTHER'}, the replay {'passes it' if passes(out) else 'does NOT pass it'}",
        "rc=0, every byte TRACE's, passed")

    # 2. other bytes, or a file more: refused by the replay, which names the file; the rest of the trace the same
    tools = "formal/twin/tools"

    def changed(name, rel, do, why):
        tag = re.sub(r"[^A-Za-z0-9]+", "-", name)    # no blank in a path: tools that list files split at one
        t = copy_tree(toy, work / tag / "tree")
        do(t / rel)
        out = work / f"{tag}.jsonl.gz"
        rc, said = trace(t, out, py)
        f, b = lines(out)
        qrc, text = replay(exe, cfile, out)
        told = f"content: NOT --content's: {why}" in text
        say(f"{name} ({rel})", rc == 0 and f != first0 and b == body0 and qrc == 1 and told,
            f"tracer rc={rc}, first line {'another' if f != first0 else 'THE SAME'}, the rest "
            f"{'the same' if b == body0 else 'ANOTHER'}, replay rc={qrc}, "
            f"{'says' if told else 'does NOT say'}: {why}",
            "rc=0, another first line, the same rest, replay rc=1 with these words")

    def more(p):
        p.write_bytes(p.read_bytes() + b"\n# one line more\n")
    changed("a document with other bytes", "protocol-v2.md", lambda p: p.write_bytes(p.read_bytes() + b"\nOne line more.\n"),
            "protocol-v2.md: other bytes")
    changed("a file of the toy with other bytes", "toy/xcheck.py", more, "toy/xcheck.py: other bytes")
    changed("a tool with other bytes, one this tracer does not load", f"{tools}/directed41.py", more,
            f"{tools}/directed41.py: other bytes")
    changed("a module more in the toy", "toy/zz.py", lambda p: p.write_text("ZZ = 1\n"), "toy/zz.py: in the trace's alone")
    changed("a file less in the toy", "toy/README.md", lambda p: p.unlink(), "toy/README.md: not in the trace's")

    # 3. what the line cannot name: the tracer stops, and leaves no trace the replay passes
    def stops(name, do, words, **kw):
        tag = re.sub(r"[^A-Za-z0-9]+", "-", name)
        t = copy_tree(toy, work / tag / "tree")
        extra = do(t)
        extra = dict(extra) if isinstance(extra, dict) else {}
        out = extra.pop("out", work / f"{tag}.jsonl.gz")
        rc, said = trace(t, out, extra.pop("py", py), **extra, **kw)
        ok = rc != 0 and words in said and not passes(out)
        say(name, ok, f"tracer rc={rc}, {'says' if words in said else 'does NOT say'}: {words}; "
            f"{'no trace the replay passes' if not passes(out) else 'a trace the replay PASSES'}",
            "a tracer that stops with these words, and no trace that passes")

    stops("a name with a blank under the toy", lambda t: (t / "toy" / "a b.py").write_text("X = 1\n"),
          "a name with a character outside")
    stops("a link under the toy", lambda t: os.symlink("node.py", t / "toy" / "node2.py"), "a link: toy/node2.py")

    # 4. a bytecode file of other code beside a source of the toy
    t = copy_tree(toy, work / "bytecode" / "tree")
    src = work / "bytecode" / "sim-other.py"
    src.write_text((t / "toy" / "sim.py").read_text() + "\nPLANTED = 1\n")
    # where a Python with no prefix looks for sim's bytecode (this process has a prefix: it is not asked)
    planted = t / "toy" / "__pycache__" / f"sim.{sys.implementation.cache_tag}.pyc"
    planted.parent.mkdir()
    py_compile.compile(str(src), cfile=str(planted), doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    probe = "import sys; sys.path.insert(0, sys.argv[1]); import sim; print(hasattr(sim, 'PLANTED'))"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    beside = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", probe, str(t / "toy")], capture_output=True,
                            text=True, env=env).stdout.strip()
    under = subprocess.run([*py, "-c", probe, str(t / "toy")], capture_output=True, text=True, env=env).stdout.strip()
    out = work / "bytecode.jsonl.gz"
    rc, said = trace(t, out, py)
    f, b = lines(out)
    say("a bytecode file of other code beside toy/sim.py",
        beside == "True" and under == "False" and rc == 0 and f == first0 and b == body0,
        f"a Python with no prefix runs the planted code: {beside}; the tracers' Python: {under}; tracer rc={rc}, "
        f"the trace {'TRACE byte for byte' if (f, b) == (first0, body0) else 'ANOTHER'}",
        "True; False; rc=0, TRACE byte for byte")

    # 5. a tracer started so that something else could run than the line names: refused, each for its reason
    exe_py = sys.executable
    pre = py[-1]                        # pycache_prefix=DIR
    shadow = work / "shadow"
    shadow.mkdir()
    (shadow / "random.py").write_text("raise SystemExit('the shadow of random ran')\n")
    stops("not isolated, with a random.py on PYTHONPATH", lambda t: {"py": [exe_py, "-S", "-B", "-X", pre],
          "env": {"PYTHONPATH": str(shadow)}}, "trace3: Python does not run isolated (-I)")
    stops("with no bytecode prefix", lambda t: {"py": [exe_py, "-I", "-S", "-B"]}, "trace3: Python has no bytecode prefix")
    full = work / "prefix-with-a-file"
    full.mkdir()
    (full / "x.pyc").write_bytes(b"")
    stops("with a bytecode prefix that holds a file", lambda t: {"py": [exe_py, "-I", "-S", "-B", "-X", f"pycache_prefix={full}"]},
          "trace3: the bytecode prefix holds a file")
    stops("writing bytecode", lambda t: {"py": [exe_py, "-I", "-S", "-X", f"pycache_prefix={work / 'pyc-written'}"]},
          "trace3: Python writes bytecode")      # (a prefix of its own: this one does write there)
    stops("optimised", lambda t: {"py": [*py, "-O"]}, "trace3: Python runs optimised (-O)")
    stops("with a dump named on its command line", lambda t: {"args": [*ARGS, "--topology", "x.json"]},
          "trace3: --xcheck and --topology are not traced")
    stops("with its output under the toy", lambda t: {"out": t / "toy" / "out.jsonl.gz"},
          "trace3: the output lies under the toy or the tools")

    def outside(t):                     # a program of another place that runs the tracer's own main
        prog = t.parent / "start.py"
        prog.write_text("import sys\nsys.path.insert(0, sys.argv[0].rsplit('/', 1)[0] + '/tree/formal/twin/tools')\n"
                        "import trace3\ntrace3.main(sys.argv[1:])\n")
        return {"program": prog}
    stops("started from a program outside the tools", outside, "trace3: module __main__ was loaded from")

    # the isolated Python ignores the same PYTHONPATH: the trace is TRACE's
    t = copy_tree(toy, work / "isolated" / "tree")
    out = work / "isolated.jsonl.gz"
    rc, said = trace(t, out, py, env={"PYTHONPATH": str(shadow)})
    f, b = lines(out)
    say("isolated, with the same random.py on PYTHONPATH", rc == 0 and (f, b) == (first0, body0),
        f"tracer rc={rc}, the trace {'TRACE byte for byte' if (f, b) == (first0, body0) else 'ANOTHER'}",
        "rc=0, TRACE byte for byte")

    print("the tree's content line: sha256 " + hashlib.sha256(first0).hexdigest())
    print("ok: every control of the content line as it must be" if not bad else f"{bad} controls of the content line wrong")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
