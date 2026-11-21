#!/usr/bin/env python3
"""What a trace is made from, named by its code and its bytes: the content line.

    python3 content.py [--toy DIR]                  print the line
    python3 content.py --rev REV [--toy DIR]        the line of commit REV of the repository the toy is in, from git's
                                                    objects: what the tree's line must be where a record is adopted
    python3 content.py --diff FILE [--toy DIR]      the names whose hashes differ from FILE's line or that one line
                                                    alone has, and a version that differs, one a line; exit 1 if any
    python3 content.py --hashes TRACE [TRACE ...]   each trace's two hashes and its name, a line each
    python3 content.py --self-test

The line is `{"content":{"files":{NAME:SHA256,...},"version":2}}`. It names:
- the two documents, as `protocol.md` and `protocol-v2.md`, each by the sha256 of its code: the text that the
  toy's own `extract.py` makes of it (`generate(doc)`), which is what the toy compiles. That text holds every
  python block of the document in order, each under a comment with the heading it stands under, comments inside
  the blocks included. So an edit of a document's prose, its version line among it, leaves the line as it was;
  an edit of its code, of a comment in a block, or of a heading that labels a block, moves it;
- every file under the toy's directory, as `toy/PATH`, by the sha256 of its bytes;
- every file under the tools' directory (this file's), as `formal/twin/tools/PATH`, by the sha256 of its bytes.
A directory is walked whole. Left out, and nothing else: a directory named `__pycache__` with all it holds (the
tracers run with a bytecode prefix of their own and read none of it), and a file whose name ends in `.md`
(prose, by its name). Refused: a link (to a file or a directory), anything that is neither a file
nor a directory, a name with a character outside `A-Z a-z 0-9 . _ -`, and a toy whose `extract.py` is missing or
fails on a document. So a module that Python could import from the toy's directory is named whether or not git
knows it, a bytecode file outside `__pycache__` too. Version 1 named each document by its bytes and walked the
`.md` files too.

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
VERSION = 2
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
            elif e.is_file(follow_symlinks=False) and name.endswith(".md"):
                continue                # prose, by its name, left out (the documents are named by their code)
            elif e.is_file(follow_symlinks=False):
                out[f"{pre}/{name}"] = hashlib.sha256(Path(e.path).read_bytes()).hexdigest()
            else:
                raise Refused(f"neither a file nor a directory: {pre}/{name}")
    return out


DOCS = ("protocol.md", "protocol-v2.md")


def code_of(extract_py, doc):
    """The sha256 of the code that the toy compiles from document `doc`: `generate(doc)` of the toy's own
    `extract.py` (the file at `extract_py`), compiled from its source text, so that no cached bytecode can stand
    in for it. Refused if it cannot be compiled or run, or fails."""
    import types
    try:
        mod = types.ModuleType("content_extract")
        mod.__file__ = str(extract_py)
        exec(compile(Path(extract_py).read_bytes(), str(extract_py), "exec"), mod.__dict__)
        src = mod.generate(doc)
    except BaseException as e:      # any failure of extract.py, SystemExit included, is refused
        raise Refused(f"the toy's extract.py cannot make the code of {Path(doc).name}: {e!r}")
    if not isinstance(src, str):
        raise Refused(f"the toy's extract.py made no text for {Path(doc).name}")
    return hashlib.sha256(src.encode()).hexdigest()


def content(toy, tools=HERE):
    """The content object of the tree the toy is in: the documents beside the toy's directory, by their code; the
    toy; the tools."""
    toy = Path(toy).resolve()
    root = toy.parent
    files = {}
    ex = toy / "extract.py"
    if ex.is_symlink() or not ex.is_file():
        raise Refused("no extract.py in the toy, or a link")
    for doc in DOCS:
        p = root / doc
        if p.is_symlink() or not p.is_file():
            raise Refused(f"no document {doc} beside the toy, or a link")
        files[doc] = code_of(ex, p)
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
    clean checkout of that commit; a file that git tracks under a `__pycache__` is left out, as the walk leaves it
    out. Where the toy and the tools lie in two repositories (a tree that holds the
    specification's as a checkout of its own), `rev` must be HEAD, and each is read at its own repository's."""
    import tempfile
    toy = Path(toy).resolve()
    files = {}
    tops = set()
    blobs = {}                                  # the documents' and extract.py's bytes at `rev`, for their code

    def tree(path, prefix):
        path = Path(path)                       # its last part as named, not where a link there points: the
        path = path.parent.resolve() / path.name    # commit's file of that name is what is read
        here = path if path.is_dir() and not path.is_symlink() else path.parent    # a link is not followed here either
        top = Path(subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
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
            out_name = prefix + name[len(rel):]
            if "__pycache__" in out_name.split("/")[:-1]:
                continue                        # as in walk(): a directory of that name, whatever it holds
            if kind != "blob" or mode == "120000":
                raise Refused(f"not a plain file in {rev}: {name}")
            if out_name.endswith(".md") and out_name not in DOCS:
                continue                        # prose, as in walk()
            data = subprocess.run(["git", "-C", str(top), "cat-file", "blob", blob], capture_output=True, check=True).stdout
            if out_name in DOCS or out_name == "toy/extract.py":
                blobs[out_name] = data
            if out_name not in DOCS:
                files[out_name] = hashlib.sha256(data).hexdigest()
    for doc in DOCS:
        tree(toy.parent / doc, doc)
    tree(toy, "toy")
    tree(tools, TOOLS)
    if len(tops) > 1 and rev != "HEAD":
        raise Refused(f"the toy and the tools lie in {len(tops)} repositories: only HEAD names a commit of each")
    for doc in DOCS:
        if doc not in blobs:
            raise Refused(f"no document {doc} in {rev}")
    if "toy/extract.py" not in blobs:
        raise Refused(f"no toy/extract.py in {rev}")
    with tempfile.TemporaryDirectory() as tmp:     # that commit's extract.py, on that commit's documents
        (Path(tmp) / "toy").mkdir()
        (Path(tmp) / "toy" / "extract.py").write_bytes(blobs["toy/extract.py"])
        for doc in DOCS:
            (Path(tmp) / doc).write_bytes(blobs[doc])
        for doc in DOCS:
            files[doc] = code_of(Path(tmp) / "toy" / "extract.py", Path(tmp) / doc)
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
    """The names whose hashes differ between two content objects, or that one object alone has, each with what
    differs; and the version of their form, where it differs."""
    fa, fb = a["content"]["files"], b["content"]["files"]
    out = []
    for n in sorted(set(fa) | set(fb)):
        if n not in fb:
            out.append(f"{n}: only in the first")
        elif n not in fa:
            out.append(f"{n}: only in the second")
        elif n in DOCS and {a["content"]["version"], b["content"]["version"]} == {1, 2}:
            out.append(f"{n}: named by its bytes in one line and by its code in the other")   # not comparable
        elif fa[n] != fb[n]:            # version 2 names a document by its code
            code = n in DOCS and a["content"]["version"] == b["content"]["version"] == 2
            out.append(f"{n}: other {'code' if code else 'bytes'}")
    if a["content"]["version"] != b["content"]["version"]:
        out.append("the version of the content's form differs")
    return out


DOC1 = ("# Doc one\n\nVersion 1.\n\n## 1. One\n\nProse of one.\n\n```python\n# set x\nx = 1\n```\n\n"
        "## Notes\n\nNo code here.\n")
DOC2 = "# Doc two\n\n## 1. Two\n\nProse of two.\n\n```python\ny = 2\n```\n"
EXTRACT = '''import re
from pathlib import Path


def generate(doc):
    text, parts, section = Path(doc).read_text(), [], "preamble"
    for m in re.finditer(r"^(#{2,4} [^\\n]*)$|^```python\\n(.*?)^```", text, flags=re.M | re.S):
        if m.group(1):
            section = m.group(1).lstrip("#").strip()
        else:
            parts.append(f"# ---- {section}\\n{m.group(2)}")
    return "\\n".join(parts)
'''


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
            (r / "protocol.md").write_text(DOC1)
            (r / "protocol-v2.md").write_text(DOC2)
            (r / "toy" / "extract.py").write_text(EXTRACT)
            (r / "toy" / "README.md").write_text("about the toy\n")
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
        changed("a document's prose changed", "protocol.md", DOC1.replace("Prose of one.", "Prose of one, edited."), True)
        changed("a document's version line changed", "protocol.md", DOC1.replace("Version 1.", "Version 2."), True)
        changed("a heading with no code under it changed", "protocol.md", DOC1.replace("## Notes", "## Remarks"), True)
        changed("the other document's prose changed", "protocol-v2.md", DOC2.replace("Prose of two.", "More prose."), True)
        changed("a document's code changed", "protocol.md", DOC1.replace("x = 1", "x = 2"))
        changed("a comment inside a document's code block changed", "protocol.md", DOC1.replace("# set x", "# set x first"))
        changed("a heading over a code block relabelled", "protocol.md", DOC1.replace("## 1. One", "## 1. Uno"))
        changed("the other document's code changed", "protocol-v2.md", DOC2.replace("y = 2", "y = 3"))
        changed("the toy's README changed", "toy/README.md", "about the toy, edited\n", True)
        changed("a README added to the tools", "tools/README.md", "about the tools\n", True)
        changed("a Markdown file added below the tools", "tools/gen/notes.md", "notes\n", True)
        changed("the toy's extract.py changed", "toy/extract.py", EXTRACT + "# another line\n")
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
        # --rev: a commit's line from git's objects is the line of its clean checkout, and its own extract.py makes
        # its documents' code, not the working tree's
        t = tree("git")
        (t / "toy" / "__pycache__").mkdir(); (t / "toy" / "__pycache__" / "node.cpython-312.pyc").write_bytes(b"\0")
        g = ["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(g[:3] + ["init", "-q"], check=True)        # the bytecode file is tracked: --rev leaves it out
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-q", "-m", "t"], check=True)
        r0 = line(of_rev(t / "toy", "HEAD", tools=t / "tools"))
        (t / "toy" / "extract.py").write_text(EXTRACT.replace('f"# ---- {section}', 'f"# == {section}'))
        r1 = line(of_rev(t / "toy", "HEAD", tools=t / "tools"))
        for what, ok in (("--rev: a commit's line is its clean checkout's", r0 == base),
                         ("--rev: the commit's extract.py, not the working tree's, makes the documents' code",
                          r1 == base and c(t) != base)):
            print(f"{what}: {'so' if ok else 'NOT so  <-- it must be'}"); bad += not ok
        # --rev with the working protocol.md a link to protocol-v2.md: the commit's protocol.md all the same
        t = tree("git-link")
        subprocess.run(["git", "-C", str(t), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "t"], check=True)
        (t / "protocol.md").unlink(); (t / "protocol.md").symlink_to(t / "protocol-v2.md")
        try:
            ok = line(of_rev(t / "toy", "HEAD", tools=t / "tools")) == base
        except Refused:
            ok = False
        print(f"--rev with the working protocol.md a link to protocol-v2.md: the commit's protocol.md: "
              f"{'so' if ok else 'NOT so  <-- it must be'}"); bad += not ok
        # --rev with the working protocol.md a link to a directory of another repository: the commit's protocol.md
        other = d / "another-repo"
        (other / "dir").mkdir(parents=True)
        subprocess.run(["git", "-C", str(other), "init", "-q"], check=True)
        (t / "protocol.md").unlink(); (t / "protocol.md").symlink_to(other / "dir")
        try:
            ok = line(of_rev(t / "toy", "HEAD", tools=t / "tools")) == base
        except (Refused, ValueError, subprocess.CalledProcessError):
            ok = False
        print(f"--rev with the working protocol.md a link to a directory of another repository: the commit's "
              f"protocol.md: {'so' if ok else 'NOT so  <-- it must be'}"); bad += not ok
        # --rev and the walk on caches: a link tracked under a __pycache__ directory, and a file named __pycache__
        t = tree("git-cache")
        (t / "toy" / "__pycache__").mkdir(); (t / "toy" / "__pycache__" / "l.pyc").symlink_to(t / "toy" / "node.py")
        (t / "toy" / "zz").mkdir(); (t / "toy" / "zz" / "__pycache__").write_text("a file of that name\n")
        g2 = ["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(g2[:3] + ["init", "-q"], check=True)
        subprocess.run(g2 + ["add", "-A"], check=True)
        subprocess.run(g2 + ["commit", "-q", "-m", "t"], check=True)
        (t / "toy" / "__pycache__" / "l.pyc").unlink()
        try:
            ok = line(of_rev(t / "toy", "HEAD", tools=t / "tools")) == c(t)
        except Refused as e:
            ok = False
        print(f"--rev and the walk on caches (a tracked link under __pycache__, a file named __pycache__): the same "
              f"line: {'so' if ok else 'NOT so  <-- it must be'}"); bad += not ok
        # an extract.py whose cached bytecode, valid for its source's size and time, holds other code: the source runs
        import importlib.util
        import py_compile
        t = tree("pyc")
        ex = t / "toy" / "extract.py"
        alt = EXTRACT.replace("# ---- ", "# ==== ")
        assert len(alt) == len(EXTRACT) and alt != EXTRACT
        st = ex.stat()
        prefix = sys.pycache_prefix     # the cache planted under a prefix of the case's own, not the run's: a file in
        sys.pycache_prefix = str(d / "pyc-prefix")  # the run's prefix stops every tracer after this self-test
        try:
            ex.write_text(alt); os.utime(ex, ns=(st.st_atime_ns, st.st_mtime_ns))
            py_compile.compile(str(ex), cfile=importlib.util.cache_from_source(str(ex)), doraise=True)
            ex.write_text(EXTRACT); os.utime(ex, ns=(st.st_atime_ns, st.st_mtime_ns))
            ok = c(t) == base
        finally:
            sys.pycache_prefix = prefix
        print(f"an extract.py with other code in its cached bytecode: its source makes the line: "
              f"{'so' if ok else 'NOT so  <-- it must be'}"); bad += not ok
        t = tree("noextract"); (t / "toy" / "extract.py").unlink()
        try:
            c(t); print("a toy without extract.py: taken  <-- it must be refused"); bad += 1
        except Refused as e:
            print(f"a toy without extract.py: refused ({e})")
        t = tree("badextract"); (t / "toy" / "extract.py").write_text("def generate(doc):\n    raise SystemExit('no')\n")
        try:
            c(t); print("an extract.py that fails: taken  <-- it must be refused"); bad += 1
        except Refused as e:
            print(f"an extract.py that fails: refused ({e})")
        t = tree("nodoc"); (t / "protocol-v2.md").unlink()
        try:
            c(t); print("a document missing: taken  <-- it must be refused"); bad += 1
        except Refused as e:
            print(f"a document missing: refused ({e})")
        v2a = json.loads(base)
        v2b = json.loads(base); v2b["content"]["files"]["protocol.md"] = "0" * 64; v2b["content"]["files"]["toy/node.py"] = "0" * 64
        v1a, v1b = json.loads(base), json.loads(json.dumps(v2b))
        v1a["content"]["version"] = v1b["content"]["version"] = 1
        for what, got, want in (("diff of two v2 lines: a document's code", diff(v2a, v2b), "protocol.md: other code"),
                                ("diff of two v2 lines: a file of the toy", diff(v2a, v2b), "toy/node.py: other bytes"),
                                ("diff of two v1 lines: a document's bytes", diff(v1a, v1b), "protocol.md: other bytes"),
                                ("diff of a v1 line and a v2 line: a document's two hashes not compared", diff(v1b, v2a),
                                 "protocol.md: named by its bytes in one line and by its code in the other")):
            ok = want in got
            print(f"{what}: {'says' if ok else 'does NOT say'} {want!r}{'' if ok else '  <-- it must'}"); bad += not ok
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
