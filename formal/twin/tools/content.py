#!/usr/bin/env python3
"""What a trace is made from, named by its bytes: the content line.

    python3 content.py [--toy DIR]                  print the line
    python3 content.py --rev REV [--toy DIR]        the line of commit REV of the repository the toy is in, from git's
                                                    objects: what the tree's line must be where a record is adopted
    python3 content.py --diff FILE [--toy DIR]      the names whose bytes differ from FILE's line, one a line; exit 1 if any
    python3 content.py --hashes TRACE [TRACE ...]   each trace's two hashes and its name, a line each
    python3 content.py --self-test

The line is `{"content":{"files":{NAME:SHA256,...},"version":1}}`. It names, each by the sha256 of its bytes:
- the two documents, as `protocol.md` and `protocol-v2.md`;
- every file under the toy's directory, as `toy/PATH`;
- every file under the tools' directory (this file's), as `formal/twin/tools/PATH`.
A directory is walked whole. Left out, and nothing else: a directory named `__pycache__` with all it holds (the
tracers run with a bytecode prefix of their own and read none of it). Refused: a link (to a file or a directory),
anything that is neither a file nor a directory, and a name with a character outside `A-Z a-z 0-9 . _ -`. So a
module that Python could import from the toy's directory is named whether or not git knows it, a bytecode file
outside `__pycache__` too.

The line's form, exactly: one object with the one member `content`, which has `files` and `version` in that
order; `files` has its names in the order of their bytes; no blank anywhere; ASCII; one line end after it. The
names' characters need no escape, so the line has one way to be written, and two lines are compared as bytes.
The documents are the ones the toy reads: `protocol.md` and `protocol-v2.md` beside the toy's directory.

It names no commit, no path of this machine (the toy's place is read, and written as `toy/`), no host, time,
Python version or hash seed. The tracer writes this line first in every trace; the replay is given the same line,
made over the tree it replays against (`--content FILE`), and compares the two.

A trace has two hashes, each the sha256 of bytes of the trace as the tracer wrote it, not of its compressed file
(which holds a time): of the whole trace, and of its body, the trace from its second line on. Another content with
the same records moves the first and not the second; a changed record moves both. What is said of a trace's
records (a replay's report, a matrix's pairs) is tied to the body.
"""
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = 1
TOOLS = "formal/twin/tools"            # the tools' names in the line, wherever this directory lies
NAME = re.compile(r"[A-Za-z0-9._-]+")


class Refused(Exception):
    pass


def walk(top, prefix):
    """{prefix/PATH: sha256} for every file under `top`, by the rule above."""
    out = {}
    stack = [(Path(top), prefix)]
    while stack:
        d, pre = stack.pop()
        with os.scandir(d) as it:
            entries = sorted(it, key=lambda e: e.name)
        for e in entries:
            name = e.name
            if not NAME.fullmatch(name):
                raise Refused(f"a name with a character outside A-Z a-z 0-9 . _ - under {pre}/: {name!r}")
            if e.is_symlink():
                raise Refused(f"a link: {pre}/{name}")
            if e.is_dir(follow_symlinks=False):
                if name != "__pycache__":
                    stack.append((Path(e.path), f"{pre}/{name}"))
            elif e.is_file(follow_symlinks=False):
                out[f"{pre}/{name}"] = hashlib.sha256(Path(e.path).read_bytes()).hexdigest()
            else:
                raise Refused(f"neither a file nor a directory: {pre}/{name}")
    return out


def content(toy, tools=HERE):
    """The content object of the tree the toy is in: the documents beside the toy's directory, the toy, the tools."""
    toy = Path(toy).resolve()
    root = toy.parent
    files = {}
    for doc in ("protocol.md", "protocol-v2.md"):
        p = root / doc
        if p.is_symlink() or not p.is_file():
            raise Refused(f"no document {doc} beside the toy, or a link")
        files[doc] = hashlib.sha256(p.read_bytes()).hexdigest()
    files.update(walk(toy, "toy"))
    files.update(walk(tools, TOOLS))
    return {"content": {"version": VERSION, "files": files}}


def line(obj):
    """The object as its one line (the form in this file's head); a line end after it."""
    files = obj["content"]["files"]
    for n in files:
        if not all(NAME.fullmatch(part) for part in n.split("/")) or not re.fullmatch(r"[0-9a-f]{64}", files[n]):
            raise Refused(f"not a name and a sha256: {n!r}")
    body = ",".join(f'"{n}":"{files[n]}"' for n in sorted(files, key=lambda n: n.encode()))
    return '{"content":{"files":{' + body + '},"version":' + str(int(obj["content"]["version"])) + "}}\n"


def of_rev(toy, rev, tools=HERE):
    """The content object of commit `rev`, from git's objects alone: the same names as the tree's walk gives for a
    clean checkout of that commit. Where the toy and the tools lie in two repositories (a tree that holds the
    specification's as a checkout of its own), `rev` must be HEAD, and each is read at its own repository's."""
    toy = Path(toy).resolve()
    files = {}
    tops = set()

    def tree(path, prefix):
        path = Path(path).resolve()
        top = Path(subprocess.run(["git", "-C", str(path if path.is_dir() else path.parent), "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True, check=True).stdout.strip()).resolve()
        tops.add(top)
        rel = path.relative_to(top).as_posix()
        out = subprocess.run(["git", "-C", str(top), "ls-tree", "-r", "-z", rev, "--", rel], capture_output=True, check=True).stdout
        for rec in out.split(b"\0"):
            if not rec:
                continue
            meta, name = rec.split(b"\t", 1)
            mode, kind, blob = meta.decode().split()
            name = name.decode()
            if kind != "blob" or mode == "120000":
                raise Refused(f"not a plain file in {rev}: {name}")
            data = subprocess.run(["git", "-C", str(top), "cat-file", "blob", blob], capture_output=True, check=True).stdout
            files[prefix + name[len(rel):]] = hashlib.sha256(data).hexdigest()
    for doc in ("protocol.md", "protocol-v2.md"):
        tree(toy.parent / doc, doc)
    tree(toy, "toy")
    tree(tools, TOOLS)
    if len(tops) > 1 and rev != "HEAD":
        raise Refused(f"the toy and the tools lie in {len(tops)} repositories: only HEAD names a commit of each")
    return {"content": {"version": VERSION, "files": files}}


def hashes(trace):
    """A trace's two hashes (this file's head): of the whole, and of the body. A file that ends in .gz is read
    through gzip."""
    trace = Path(trace)
    whole, body = hashlib.sha256(), hashlib.sha256()
    with (gzip.open(trace, "rb") if trace.suffix == ".gz" else open(trace, "rb")) as f:
        whole.update(f.readline())
        for part in iter(lambda: f.read(1 << 20), b""):
            whole.update(part)
            body.update(part)
    return whole.hexdigest(), body.hexdigest()


def diff(a, b):
    """The names whose bytes differ between two content objects, each with what differs."""
    fa, fb = a["content"]["files"], b["content"]["files"]
    out = []
    for n in sorted(set(fa) | set(fb)):
        if n not in fb:
            out.append(f"{n}: only in the first")
        elif n not in fa:
            out.append(f"{n}: only in the second")
        elif fa[n] != fb[n]:
            out.append(f"{n}: other bytes")
    if a["content"]["version"] != b["content"]["version"]:
        out.append("the version of the content's form differs")
    return out


def self_test():
    import shutil
    import tempfile
    bad = 0
    d = Path(tempfile.mkdtemp())
    try:
        def tree(name):
            r = d / name
            (r / "toy").mkdir(parents=True)
            (r / "tools" / "gen").mkdir(parents=True)
            (r / "protocol.md").write_text("doc 1\n")
            (r / "protocol-v2.md").write_text("doc 2\n")
            (r / "toy" / "node.py").write_text("x = 1\n")
            (r / "toy" / "run.py").write_text("import node\n")
            (r / "tools" / "trace3.py").write_text("t = 1\n")
            (r / "tools" / "gen" / "schema.py").write_text("s = 1\n")
            return r
        def c(r):
            return line(content(r / "toy", tools=r / "tools"))
        a, b = tree("a"), tree("elsewhere/deeper/b")
        base = c(a)
        cases = []
        cases.append(("a copy at another path", c(b) == base, True))
        cwd = os.getcwd(); os.chdir(d)
        cases.append(("from another working directory", c(a) == base, True)); os.chdir(cwd)
        (a / "toy" / "__pycache__").mkdir(); (a / "toy" / "__pycache__" / "node.cpython-312.pyc").write_bytes(b"\0")
        cases.append(("a bytecode cache directory added", c(a) == base, True))
        def changed(what, f, new=None, expect=False):
            t = tree("c-" + str(len(cases)))
            p = t / f
            if new is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True); p.write_text(new)
            cases.append((what, c(t) == base, expect))
        changed("a document's bytes changed", "protocol.md", "doc 1.\n")
        changed("the other document's bytes changed", "protocol-v2.md", "doc 2 \n")
        changed("a file of the toy changed", "toy/node.py", "x = 2\n")
        changed("a module added to the toy that git would not know", "toy/random.py", "\n")
        changed("a file of the toy removed", "toy/run.py")
        changed("a tool changed", "tools/trace3.py", "t = 2\n")
        changed("a tool in a directory below changed", "tools/gen/schema.py", "s = 2\n")
        changed("an empty file added to the tools", "tools/new.py", "")
        changed("a bytecode file outside __pycache__, which Python would import", "toy/extra.pyc", "x")
        for what, got, want in cases:
            ok = got == want
            bad += not ok
            print(f"{what}: {'the same line' if got else 'another line'}{'' if ok else '  <-- it must be ' + ('the same' if want else 'another')}")
        t = tree("link"); (t / "toy" / "l.py").symlink_to(t / "toy" / "node.py")
        try:
            c(t); print("a link in the toy: taken  <-- it must be refused"); bad += 1
        except Refused as e:
            print(f"a link in the toy: refused ({e})")
        t = tree("linkdir"); (t / "tools" / "more").symlink_to(t / "toy")
        try:
            c(t); print("a linked directory in the tools: taken  <-- it must be refused"); bad += 1
        except Refused as e:
            print(f"a linked directory in the tools: refused ({e})")
        tr = d / "t.jsonl"
        recs = '{"header":{}}\n{"nodes":[]}\n{"fn":"f","ret":true}\n'
        tr.write_text(base + recs); h0 = hashes(tr)
        tr.write_text(c(tree("h-doc")).replace("0", "1", 1) + recs); h1 = hashes(tr)
        tr.write_text(base + recs.replace("true", "false")); h2 = hashes(tr)
        with gzip.open(d / "t.jsonl.gz", "wb") as z:
            z.write((base + recs).encode())
        h3 = hashes(d / "t.jsonl.gz")
        for what, ok in (("a trace of another content, the same records: the whole's hash moves, the body's does not",
                          h1[0] != h0[0] and h1[1] == h0[1]),
                         ("a trace with a record changed: both hashes move", h2[0] != h0[0] and h2[1] != h0[1]),
                         ("the same trace compressed: the same two hashes", h3 == h0)):
            print(f"{what}: {'so' if ok else 'NOT so  <-- it must be'}"); bad += not ok
        for k, bad_name in enumerate(("caf\u00e9.py", 'a"b.py', "a b.py", "a\\b.py")):
            t = tree(f"name{k}"); (t / "toy" / bad_name).write_text("")
            try:
                c(t); print(f"a name outside the plain characters ({bad_name!r}): taken  <-- it must be refused"); bad += 1
            except Refused:
                print(f"a name outside the plain characters ({bad_name!r}): refused")
        t = tree("nodoc"); (t / "protocol-v2.md").unlink()
        try:
            c(t); print("a document missing: taken  <-- it must be refused"); bad += 1
        except Refused as e:
            print(f"a document missing: refused ({e})")
        obj = json.loads(base)
        ok = (line(obj) == base and list(obj["content"]["files"]) == sorted(obj["content"]["files"]) and base.count("\n") == 1
              and base == json.dumps(obj, separators=(",", ":")) + "\n" and "\\" not in base)
        bad += not ok
        print(f"the line read and written again is the same line, its names sorted: {'yes' if ok else 'NO  <-- it must be'}")
        print(f"the names: {', '.join(obj['content']['files'])}")
    finally:
        shutil.rmtree(d)
    print("content self-test: every case as it must be" if not bad else f"content self-test: {bad} cases wrong")
    return 1 if bad else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv[:1] == ["--hashes"] and len(argv) > 1:
        for t in argv[1:]:
            try:
                w, b = hashes(t)
            except (OSError, EOFError) as e:
                print(f"content: {t}: cannot be read: {e}", file=sys.stderr)
                return 1
            print(f"{w}  {b}  {t}")
        return 0
    toy = other = rev = None
    it = iter(argv)
    for a in it:
        if a == "--toy":
            toy = next(it)
        elif a == "--rev":
            rev = next(it)
        elif a == "--diff":
            other = next(it)
        else:
            print(__doc__)
            return 2
    toy = toy or os.environ.get("SPEC_TOY") or HERE.parents[2] / "toy"
    try:
        obj = of_rev(toy, rev) if rev else content(toy)
    except (Refused, OSError, subprocess.CalledProcessError) as e:
        print(f"content: refused: {e}", file=sys.stderr)
        return 1
    if other:
        d = diff(json.loads(Path(other).read_text()), obj)
        for x in d:
            print(x)
        return 1 if d else 0
    sys.stdout.write(line(obj))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
