#!/usr/bin/env python3
"""Is a format-7 trace of this tree's content, and of which kind?

    python3 header3.py TOYDIR TRACE [TRACE ...]

A trace's first line must be this tree's content line, byte for byte (content.py, made over TOYDIR, the documents
beside it and these tools): a trace kept from other tools, another toy or other documents is refused, and the
reason names the first file whose bytes differ. The replay makes the same comparison with the file it is given;
this one is made against the tree itself. cells3.py asks it of each trace it has just made.

What the replay does not check of the header, the second line: the tracer's name, and that the functions traced
(`traced`) are the block's (trace3.BLOCK), §6.1's twelve (TRACE3_ONLY=sec61), or, for a trace run with --doc v2,
the block's names that are protocol.md's all the way down (trace3.v2_kept), computed here from TOYDIR's documents;
and that it claims the whole state exactly where it is a directed set's. A trace that passes is printed with its
kind.

Exit code 0 when every trace passes; otherwise each trace's reasons are printed.
"""
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content                          # noqa: E402
import trace3                           # noqa: E402


def want(toy):
    return {"format": 7, "tracer": "trace3.py", "own": list(trace3.OWN), "foreign": list(trace3.FOREIGN)}


KINDS = {tuple(sorted(trace3.BLOCK)): f"the block's {len(trace3.BLOCK)} functions",
         tuple(sorted(trace3.SEC61)): f"§6.1's {len(trace3.SEC61)} alone"}


def v2_kind(toy):
    """v2's kept names, sorted, from TOYDIR's documents: the toy's node.py makes their extracted code."""
    sys.path.insert(0, str(Path(toy).resolve()))
    import node                         # noqa: E402: the pinned toy, from TOYDIR
    return tuple(sorted(n for n in trace3.v2_kept(trace3.BLOCK, node.SPEC_SRC, node.generate(node.DOC2))
                        if n not in trace3.SEC71))      # the window's six are not traced under v2


def kind_of(toy, traced, args):
    """The name of a traced list's kind, or None. A trace run with --doc v2 has one kind, v2's kept, and a trace run
    without it never has that one: the block's list under --doc v2 does not pass."""
    t = tuple(traced) if isinstance(traced, list) else None
    if trace3.doc_of(args or []) == "v2":
        return f"v2's kept, {len(t)} functions" if t is not None and t == v2_kind(toy) else None
    return KINDS.get(t)


def head_lines(trace):
    """A trace's first line as text, and its header (the second line), or the reason it has none."""
    trace = Path(trace)
    try:
        with (gzip.open(trace, "rt") if trace.suffix == ".gz" else open(trace)) as f:
            line1 = f.readline()
            second = json.loads(f.readline())
    except (OSError, ValueError) as e:
        return None, None, f"its first two lines cannot be read: {e}"
    h = second.get("header") if isinstance(second, dict) else None
    return (line1, h, None) if isinstance(h, dict) else (line1, None, "no header on the second line")


def header(trace):
    """A trace's header, or the reason it has none."""
    _, h, no = head_lines(trace)
    return h, no


def content_why(toy, line1):
    """Why a trace's first line is not this tree's content line: nothing when it is."""
    mine = content.line(content.content(toy))
    if line1 == mine:
        return []
    try:
        got = json.loads(line1)
        d = content.diff(json.loads(mine), got)
    except (ValueError, KeyError, TypeError, AttributeError):
        return ["content: the first line is no content line"]
    return [f"content: not this tree's: {d[0]}" if d else "content: this tree's names and hashes, written otherwise"]


def check(toy, trace):
    """The reasons a trace's header is not as it must be: none when it is."""
    line1, h, no = head_lines(trace)
    if h is None:
        return [no]
    why = content_why(toy, line1)
    traced = h.get("traced")
    if kind_of(toy, traced, h.get("args")) is None:
        why.append(f"traced: {traced!r}, must be the block's functions, §6.1's alone, or under --doc v2 v2's kept, "
                   "sorted")
    for name, v in want(toy).items():
        got = h.get(name)
        if got == v:
            continue
        why.append(f"{name}: {got!r}, must be {v!r}")
    # the directed records hold the whole state, a cell's do not (directed42.py's, §4.2's; directed4b.py's, its
    # deferral path's)
    whole = h.get("args", [None])[:1] in (["directed3"], ["directed44"], ["directed42"], ["directed4b"], ["directed7"],
                                             ["directed1"], ["directed6o"], ["directed64"], ["directed64h"], ["directed46"], ["directed43"], ["directed41"], ["directed46d"], ["directed3v"], ["directed52"], ["directed53"], ["directed54"], ["directed71"], ["directed51"])   # among them §1's (directed1.py),
    #                                              drop_offer's (directed6o.py), §6.4's (directed64.py, directed64h.py), §4.6's (directed46.py), §4.3's (directed43.py), §4.1's (directed41.py), §4.6's decode's (directed46d.py), §3's (directed3v.py)
    if h.get("whole") is not whole:
        why.append(f"whole: {h.get('whole')!r}, must be {whole!r} for this kind of trace")
    return why


def main(argv):
    bad = 0
    for t in argv[1:]:
        why = check(argv[0], t)
        bad += bool(why)
        h = header(t)[0]
        kind = "" if why else f", tracing {kind_of(argv[0], h['traced'], h.get('args'))}"
        print(f"{t}: {'as these tools and these documents' + kind if not why else '; '.join(why)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
