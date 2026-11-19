#!/usr/bin/env python3
"""Is one directory of Lean and Python sources another with nothing changed but its comments?

    python3 commentsonly.py OLD NEW        two directories (a Lean package with its build files, or a directory of tools)
    python3 commentsonly.py --self-test    the known answers, each reported

Exit 0 where NEW is OLD but for the text of comments and docstrings; 1 otherwise, with the first difference of each
file that has one.

What is compared
- The file set (every file under each directory, outside `.lake/` and `__pycache__/`): no file more, none fewer.
- A file that is neither a `.lean` nor a `.py` file, byte for byte. `lake-manifest.json` and `lean-toolchain` are
  such files; `lakefile.lean` is a Lean file and is compared as one.
- A `.py` file, by its syntax tree (Python's own `ast`, type comments included), with every docstring taken out:
  a comment's text and a docstring's text may change, and nothing else. Layout that leaves the tree as it was (a
  call wrapped onto two lines) is not seen. A first line `#!…` and a coding line are held as they are. Where a file
  reads its own `__doc__`, a docstring's text is something it prints: the report says so.
- A `.lean` file, by its stream of words with their layout. A word is a run of characters with no blank, line end
  or comment inside it; a string, a character literal and a name in «» are kept whole, with what they hold. Each
  word is held with its column and with whether a line end stands between it and the word before. Lean reads
  both: a column where it compares indentation, a line end where it ends a term.
- A comment (`-- …`, `/- … -/`, nested or not) is white space to Lean: its text may change, and it may be added
  or removed, as long as every word keeps its column and its line ends.
- A docstring (`/-- … -/`) and a module docstring (`/-! … -/`) are syntax, not white space: each stays, in its
  place and of its kind, and only its text may change. A docstring before `#guard_msgs` is that command's
  expected output: its text is compared too.

Where the lexer cannot be sure, it refuses the file instead of guessing
- `--` or `/-` directly after an operator character (`<--`): Lean reads the longest token it knows there, and this
  script does not know Lean's tokens. Put a blank before the comment.
- A string not written `s!"…"`, `m!"…"` or `f!"…"` that reads differently as an interpolated string than as a plain
  one (it holds a `{` whose hole holds a `"`).
- A tab or a carriage return outside comments and strings; a `'` that begins no character literal.
"""
import ast
import difflib
import io
import re
import sys
import tokenize
from pathlib import Path

BUILD_FILES = ("lakefile.lean", "lake-manifest.json", "lean-toolchain")
SKIP_DIRS = (".lake", "__pycache__")
CHAR = re.compile(r"'(?:\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)|[^\\'\n])'")
RAW = re.compile(r'r(#*)"')
CLOSERS = ')]}⟩»",'


class Refused(Exception):
    """The lexer cannot be sure what a place of the file is."""


def ident_like(c):
    return c.isalnum() or c in "_'"


def where(s, i):
    return f"line {s.count(chr(10), 0, i) + 1}, column {i - (s.rfind(chr(10), 0, i) + 1)}"


def block_end(s, i, opener):
    """The end of the block comment that opens at i with `opener` (`/-`, `/--` or `/-!`), nested ones inside it."""
    j, depth = i + len(opener), 1
    while j < len(s):
        if s.startswith("-/", j):
            depth, j = depth - 1, j + 2
            if depth == 0:
                return j
        elif s.startswith("/-", j):
            depth, j = depth + 1, j + 2
        else:
            j += 1
    raise Refused(f"a block comment opened at {where(s, i)} is not closed")


def plain_end(s, i):
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
        elif s[j] == '"':
            return j + 1
        else:
            j += 1
    return None


def hole_end(s, j):
    """The end of an interpolated string's hole whose `{` is before j: code, with its own strings and comments."""
    depth = 1
    while j < len(s):
        c = s[j]
        if c == '"':
            j = string_end(s, j)
        elif s.startswith("--", j):
            k = s.find("\n", j)
            j = len(s) if k < 0 else k
        elif s.startswith("/-", j):
            j = block_end(s, j, "/-")
        elif c == "'" and CHAR.match(s, j) and not ident_like(s[j - 1]):
            j = CHAR.match(s, j).end()
        elif c == "{":
            depth, j = depth + 1, j + 1
        elif c == "}":
            depth, j = depth - 1, j + 1
            if depth == 0:
                return j
        else:
            j += 1
    return None


def interp_end(s, i):
    j = i + 1
    try:
        while j is not None and j < len(s):
            if s[j] == "\\":
                j += 2
            elif s[j] == '"':
                return j + 1
            elif s[j] == "{":
                j = hole_end(s, j + 1)
            else:
                j += 1
    except Refused:
        pass
    return None


def string_end(s, i):
    """The end of the string that opens at i. An interpolated one (`s!`, `m!`, `f!`) is read with its holes; any
    other must read the same both ways."""
    marked = i >= 2 and s[i - 1] == "!" and s[i - 2] in "smf" and (i < 3 or not ident_like(s[i - 3]))
    p, q = plain_end(s, i), interp_end(s, i)
    if marked:
        if q is None:
            raise Refused(f"the interpolated string at {where(s, i)} does not end")
        return q
    if p is None:
        raise Refused(f"the string at {where(s, i)} does not end")
    if p != q:
        raise Refused(f"the string at {where(s, i)} reads differently as an interpolated string than as a plain one")
    return p


def scan(s):
    """The file as pieces in order, each (kind, start, end): `code` (words and white space), `lit` (a string, a
    character literal, a name in «»: part of a word, kept whole), `line` and `block` (comments), `doc`, `moddoc`."""
    segs, i, start, n = [], 0, 0, len(s)

    def close(j):
        if j > start:
            segs.append(("code", start, j))

    def sure(j, what):
        if j > start and not (s[j - 1] in " \n" or ident_like(s[j - 1]) or s[j - 1] in CLOSERS):
            raise Refused(f"`{what}` directly after `{s[j - 1]}` at {where(s, j)}: a comment, or part of a longer token?")

    while i < n:
        c = s[i]
        if c in "\t\r":
            raise Refused(f"a tab or a carriage return at {where(s, i)}")
        if s.startswith("--", i):
            sure(i, "--")
            j = s.find("\n", i)
            j = n if j < 0 else j
            close(i)
            segs.append(("line", i, j))
            i = start = j
        elif s.startswith("/-", i):
            sure(i, "/-")
            kind, opener = (("doc", "/--") if s.startswith("/--", i) else ("moddoc", "/-!") if s.startswith("/-!", i)
                            else ("block", "/-"))
            j = block_end(s, i, opener)
            close(i)
            segs.append((kind, i, j))
            i = start = j
        elif c == '"' or c == "«" or (c == "'" and not (i and (ident_like(s[i - 1]) or s[i - 1] in "?!"))) \
                or (c == "r" and RAW.match(s, i) and not (i and ident_like(s[i - 1]))):
            if c == '"':
                j = string_end(s, i)
            elif c == "«":
                j = s.find("»", i) + 1
                if j == 0:
                    raise Refused(f"the name opened with « at {where(s, i)} is not closed")
            elif c == "'":
                m = CHAR.match(s, i)
                if not m:
                    raise Refused(f"a ' at {where(s, i)} that begins no character literal")
                j = m.end()
            else:
                m = RAW.match(s, i)
                j = s.find('"' + m.group(1), m.end())
                if j < 0:
                    raise Refused(f"the raw string at {where(s, i)} does not end")
                j += 1 + len(m.group(1))
            close(i)
            segs.append(("lit", i, j))
            i = start = j
        else:
            i += 1
    close(n)
    return segs


def stream(s):
    """(items, lines, comments). An item is ("w", text, column, line end before) for a word, or (kind, column,
    line end before, text or None) for a docstring: its text is there only before `#guard_msgs`. `lines` gives each
    item's line, for the report. `comments` is each comment and docstring as (items before it, kind, text)."""
    atoms = []                              # (kind, start, end): "w" (no blank inside), "ws", or a comment's kind
    for kind, a, b in scan(s):
        if kind == "code":
            for m in re.finditer(r"[ \n]+|[^ \n]+", s[a:b]):
                atoms.append(("ws" if m.group()[0] in " \n" else "w", a + m.start(), a + m.end()))
        else:
            atoms.append(("w" if kind == "lit" else kind, a, b))
    items, lines, comments, docs = [], [], [], []
    word, nl = None, True

    def col(i):
        return i - (s.rfind("\n", 0, i) + 1)

    def end_word():
        nonlocal word, nl
        if word:
            a, b, was_nl = word
            items.append(("w", s[a:b], col(a), was_nl))
            lines.append(s.count("\n", 0, a) + 1)
            word, nl = None, False

    for kind, a, b in atoms:
        if kind == "w":
            word = (word[0], b, word[2]) if word else (a, b, nl)
            continue
        end_word()
        if kind == "ws" or kind in ("line", "block"):
            nl = nl or "\n" in s[a:b]
            if kind != "ws":
                comments.append((len(items), kind, s[a:b]))
        else:                               # doc, moddoc
            docs.append(len(items))
            comments.append((len(items), kind, s[a:b]))
            items.append((kind, col(a), nl, s[a:b]))
            lines.append(s.count("\n", 0, a) + 1)
            nl = False
    end_word()
    for k in docs:                          # a docstring's text is held only where it is a command's expected output
        guard = k + 1 < len(items) and items[k + 1][0] == "w" and items[k + 1][1].startswith("#guard_msgs")
        if not guard:
            items[k] = items[k][:3] + (None,)
    return items, lines, comments


def show(item):
    if item[0] == "w":
        return f"`{item[1]}` at column {item[2]}" + (", first of its line" if item[3] else "")
    return f"a {'docstring' if item[0] == 'doc' else 'module docstring'} at column {item[1]}" + \
        (f" with the text {item[3]!r}" if item[3] is not None else "")


def compare_lean(old, new):
    """(None, counts) where `new` is `old` but for comments; (the first difference, None) otherwise."""
    try:
        a, la, ca = stream(old)
    except Refused as e:
        return f"OLD refused: {e}", None
    try:
        b, lb, cb = stream(new)
    except Refused as e:
        return f"NEW refused: {e}", None
    if a != b:
        k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        x = f"{show(a[k])} (line {la[k]})" if k < len(a) else "the end of the file"
        y = f"{show(b[k])} (line {lb[k]})" if k < len(b) else "the end of the file"
        return f"OLD has {x}; NEW has {y}", None
    counts = {"reworded": 0, "added": 0, "removed": 0, "docstrings": 0}
    plain_a = [c for c in ca if c[1] in ("line", "block")]
    plain_b = [c for c in cb if c[1] in ("line", "block")]
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, plain_a, plain_b, autojunk=False).get_opcodes():
        if tag == "replace":
            both = min(i2 - i1, j2 - j1)
            counts["reworded"] += both
            counts["removed"] += (i2 - i1) - both
            counts["added"] += (j2 - j1) - both
        elif tag == "delete":
            counts["removed"] += i2 - i1
        elif tag == "insert":
            counts["added"] += j2 - j1
    doc_a = [c for c in ca if c[1] in ("doc", "moddoc")]
    doc_b = [c for c in cb if c[1] in ("doc", "moddoc")]
    counts["docstrings"] = sum(1 for x, y in zip(doc_a, doc_b) if x != y)
    return None, counts


CODING = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")


def py_form(src):
    """A Python file as (its syntax tree's dump with every docstring emptied, the docstrings, its `#!` and coding
    lines, its comments, whether it reads `__doc__`)."""
    tree = ast.parse(src, type_comments=True)
    docs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                docs.append(b[0].value.value)
                b[0].value.value = ""
    head = [x for x in src.split("\n")[:2] if x.startswith("#!") or CODING.match(x)]
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    comments = [t.string for t in toks if t.type == tokenize.COMMENT and not (t.start[0] <= 2 and t.line.rstrip("\n") in head)]
    reads_doc = any(t.type == tokenize.NAME and t.string == "__doc__" for t in toks)
    return ast.dump(tree), docs, head, comments, reads_doc


def compare_py(old, new):
    """(None, counts) where `new` is `old` but for comments and docstrings; (the first difference, None) otherwise."""
    try:
        a = py_form(old)
    except (SyntaxError, tokenize.TokenError) as e:
        return f"OLD does not parse: {e}", None
    try:
        b = py_form(new)
    except (SyntaxError, tokenize.TokenError) as e:
        return f"NEW does not parse: {e}", None
    if a[2] != b[2]:
        return f"the `#!` or coding lines differ: OLD has {a[2]}; NEW has {b[2]}", None
    if a[0] != b[0]:
        k = next((i for i, (x, y) in enumerate(zip(a[0], b[0])) if x != y), min(len(a[0]), len(b[0])))
        return (f"the syntax trees differ: OLD has …{a[0][max(0, k - 50):k + 50]}…; "
                f"NEW has …{b[0][max(0, k - 50):k + 50]}…"), None
    counts = {"reworded": 0, "added": 0, "removed": 0,
              "docstrings": sum(1 for x, y in zip(a[1], b[1]) if x != y), "reads_doc": a[4] or b[4]}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a[3], b[3], autojunk=False).get_opcodes():
        if tag == "replace":
            both = min(i2 - i1, j2 - j1)
            counts["reworded"] += both
            counts["removed"] += (i2 - i1) - both
            counts["added"] += (j2 - j1) - both
        elif tag == "delete":
            counts["removed"] += i2 - i1
        elif tag == "insert":
            counts["added"] += j2 - j1
    return None, counts


def compare_trees(old, new):
    """`old` and `new` map each file's relative name to its bytes. (lines of the report, ok)."""
    out, ok = [], True
    for name in sorted(set(old) | set(new)):
        if name not in new or name not in old:
            out.append(f"{name}: only in {'OLD' if name in old else 'NEW'}  <-- NOT")
            ok = False
        elif not name.endswith((".lean", ".py")):
            if old[name] != new[name]:
                what = "a build file" if name in BUILD_FILES else "neither a Lean nor a Python file"
                out.append(f"{name}: {what}, and its bytes differ  <-- NOT")
                ok = False
        else:
            compare = compare_lean if name.endswith(".lean") else compare_py
            why, counts = compare(old[name].decode("utf-8"), new[name].decode("utf-8"))
            if why:
                out.append(f"{name}: {why}  <-- NOT")
                ok = False
            elif any(counts[k] for k in ("reworded", "added", "removed", "docstrings")):
                printed = "; the file reads its `__doc__`: a docstring's text is printed" if counts.get("reads_doc") else ""
                out.append(f"{name}: comments only: {counts['reworded']} reworded, {counts['added']} added, "
                           f"{counts['removed']} removed; {counts['docstrings']} docstrings edited{printed}")
            elif old[name] != new[name]:
                out.append(f"{name}: layout only (blanks, empty lines" +
                           (")" if name.endswith(".lean") else ", or code wrapped another way)"))
    return out, ok


def load(d):
    d = Path(d)
    if not d.is_dir():
        raise SystemExit(f"commentsonly: {d} is no directory")
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*"))
            if p.is_file() and not set(p.relative_to(d).parts) & set(SKIP_DIRS)}


BASE = {
    "lakefile.lean": "import Lake\nopen Lake DSL\n-- the package\npackage t where\n  leanOptions := #[⟨`autoImplicit, false⟩]\n",
    "lake-manifest.json": '{"packages": [{"name": "x", "rev": "abc"}]}\n',
    "lean-toolchain": "leanprover/lean4:v4.35.0\n",
    "A.lean": ('/-! # Module A (see the manual) -/\n'
               'set_option maxHeartbeats 1000\n'
               '/-- adds one (a first draft) -/\n'
               'def f (n : Nat) : Nat :=\n'
               '  n + 1   -- the successor\n'
               '/- a block /- nested -/ still comment -/\n'
               'def g (s : String) : String :=\n'
               '  s ++ "a--b" ++ s!"x {f 1} -- {"q"}" /- in line -/ ++ s\n'
               '-- a line with /- in it\n'
               'def h : Char := \'"\'\n'
               '/-- info: 2 -/\n'
               '#guard_msgs in\n'
               '#eval f 1\n'),
    "tool.py": ('#!/usr/bin/env python3\n'
                '"""A tool (see the manual)."""\n'
                'import sys  # noqa: E402\n'
                'N = 3  # since the start\n'
                'def f(x, y=1):\n'
                '    """adds (a first draft)"""\n'
                '    # a comment\n'
                '    return x + y\n'
                'print(f(N), "a # b")\n'),
}
CASES = [   # (the case, file, old text, new text, accepted?)
    ("a changed token", "A.lean", "n + 1 ", "n + 2 ", False),
    ("a changed string literal", "A.lean", '"a--b"', '"a--c"', False),
    ("a change inside an interpolated string's hole", "A.lean", '{"q"}', '{"r"}', False),
    ("a changed character literal", "A.lean", "'\"'", "'x'", False),
    ("code commented out", "A.lean", "  n + 1   -- the successor", "  -- n + 1   the successor", False),
    ("a comment made code", "A.lean", "n + 1   -- the successor", "n + 1   + the successor", False),
    ("the code after a line comment that holds `/-`", "A.lean", "in it\ndef h", "in it\ndef k", False),
    ("an indentation change", "A.lean", "  n + 1 ", "    n + 1 ", False),
    ("a comment in a line made longer, the word after it moved", "A.lean", "/- in line -/", "/- in the line -/", False),
    ("a comment in a line removed, the word after it moved", "A.lean", " /- in line -/", "", False),
    ("a line end added inside a term", "A.lean", "s ++ \"a--b\"", "s ++\n  \"a--b\"", False),
    ("a changed `set_option` value", "A.lean", "maxHeartbeats 1000", "maxHeartbeats 2000", False),
    ("a changed `#guard_msgs` expectation", "A.lean", "info: 2", "info: 3", False),
    ("a docstring made a plain comment", "A.lean", "/-- adds one", "/- adds one", False),
    ("a docstring removed", "A.lean", "/-- adds one (a first draft) -/\n", "", False),
    ("a module docstring removed", "A.lean", "/-! # Module A (see the manual) -/\n", "", False),
    ("a comment directly after an operator", "A.lean", "n + 1   -- the", "n +-- the", False),
    ("a tab", "A.lean", "  n + 1 ", "\tn + 1 ", False),
    ("an added lakefile option", "lakefile.lean", "false⟩]", "false⟩, ⟨`relaxedAutoImplicit, false⟩]", False),
    ("a changed manifest rev", "lake-manifest.json", '"abc"', '"abd"', False),
    ("a changed toolchain", "lean-toolchain", "v4.35.0", "v4.36.0", False),
    ("an added file", "B.lean", None, "def x := 1\n", False),
    ("a removed file", "A.lean", BASE["A.lean"], None, False),
    ("a pure comment edit", "A.lean", "-- the successor", "-- one more", True),
    ("a comment at a line's end removed, with the blanks before it", "A.lean", "n + 1   -- the successor", "n + 1", True),
    ("a comment line removed", "A.lean", "-- a line with /- in it\n", "", True),
    ("a comment line added", "A.lean", "def h", "-- a character\ndef h", True),
    ("a comment in a line reworded at the same length", "A.lean", "/- in line -/", "/- a  note -/", True),
    ("a docstring edit", "A.lean", "adds one (a first draft)", "adds one", True),
    ("a module docstring edit", "A.lean", " (see the manual)", "", True),
    ("an edit of a line comment that holds `/-`", "A.lean", "with /- in it", "with /- inside", True),
    ("an edit inside a nested block comment", "A.lean", "/- nested -/ still comment", "/- nest -/ still", True),
    ("a comment edit in the lakefile", "lakefile.lean", "-- the package", "-- a package for the self-test", True),
    ("nothing changed", "A.lean", "", "", True),
    ("Python: a changed number", "tool.py", "N = 3", "N = 4", False),
    ("Python: a changed string", "tool.py", '"a # b"', '"a # c"', False),
    ("Python: a changed default", "tool.py", "y=1", "y=2", False),
    ("Python: code commented out", "tool.py", "    return x + y", "    # return x + y\n    return x", False),
    ("Python: a comment made code", "tool.py", "    # a comment\n", "    x = 0\n", False),
    ("Python: a line taken out of its block", "tool.py", "    return x + y", "return x + y", False),
    ("Python: a changed `#!` line", "tool.py", "python3\n", "python\n", False),
    ("Python: a docstring made a comment", "tool.py", '    """adds (a first draft)"""', "    # adds", False),
    ("Python: a file that does not parse", "tool.py", "def f(x, y=1):", "def f(x, y=1:", False),
    ("Python: a comment edit", "tool.py", "# since the start", "# the count", True),
    ("Python: a comment removed", "tool.py", "  # since the start", "", True),
    ("Python: a comment line removed", "tool.py", "    # a comment\n", "", True),
    ("Python: a docstring edit", "tool.py", " (a first draft)", "", True),
    ("Python: a module docstring edit", "tool.py", " (see the manual)", "", True),
    ("Python: code wrapped onto two lines", "tool.py", 'f(N), "a # b"', 'f(N),\n      "a # b"', True),
]


def self_test():
    bad = 0
    for what, file, old, new, accepted in CASES:
        a = {k: v.encode() for k, v in BASE.items()}
        b = dict(a)
        if old is None:
            b[file] = new.encode()
        elif new is None:
            del b[file]
        else:
            if old and BASE[file].count(old) != 1:
                raise SystemExit(f"self-test: {what}: its text stands {BASE[file].count(old)} times in {file}")
            b[file] = BASE[file].replace(old, new).encode() if old else a[file]
        out, ok = compare_trees(a, b)
        right = ok == accepted
        bad += not right
        said = "accepted" if ok else "rejected"
        why = ("; ".join(out) or "no difference") if not right or not ok else (out[0] if out else "no difference")
        print(f"{said}{'' if right else '  <-- it must be ' + ('accepted' if accepted else 'rejected')}: {what}: {why}")
    n_rej = sum(1 for c in CASES if not c[4])
    print(f"self-test: {len(CASES) - bad} of {len(CASES)} known answers ({n_rej} that must be rejected, "
          f"{len(CASES) - n_rej} that must be accepted)")
    return 1 if bad else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) != 2 or argv[0].startswith("-"):
        print(__doc__)
        return 2
    out, ok = compare_trees(load(argv[0]), load(argv[1]))
    for line in out:
        print(line)
    n = len(load(argv[1]))
    print(f"commentsonly: {'the same but for comments' if ok else 'NOT the same but for comments'} "
          f"({n} files in NEW; {sum(1 for x in out if 'comments only' in x)} with comment edits, "
          f"{sum(1 for x in out if '<-- NOT' in x)} refused or different)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
