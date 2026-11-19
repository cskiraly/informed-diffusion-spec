"""Where things are, from this file's own place: `formal/twin/tools/` of the specification's repository.

    TWIN    formal/twin, the Lean package these tools check
    ROOT    the repository's root: the two documents are ROOT/protocol.md and ROOT/protocol-v2.md
    REPLAY  the twin's replay, where `lake build` leaves it
    toy()   the toy: ROOT/toy, or the directory the environment's SPEC_TOY names
    python(work)    the command a tracer's Python is started with (below)

The toy's place is the one parameter. A tool that takes TOYDIR as an argument uses that; a tool that needs the toy
and has no such argument asks `toy()`. Nothing else here or in the tools is a path outside this layout: `lake` and
`lean` are the ones on PATH (elan's, or a toolchain's `bin` put first), and a tool runs its children as plain
children, under the caller's limits.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TWIN = HERE.parent
ROOT = HERE.parents[2]
REPLAY = TWIN / ".lake" / "build" / "bin" / "replay"
NOT_SOURCES = (".lake", "tools", "record", "__pycache__")    # what a copy of the twin's sources leaves out


def toy():
    """The toy's directory, resolved. It must hold run.py: a wrong place is refused here, not at the first import."""
    d = Path(os.environ.get("SPEC_TOY") or ROOT / "toy").resolve()
    if not (d / "run.py").is_file():
        raise SystemExit(f"layout: no toy at {d} (no run.py there): set SPEC_TOY to the toy's directory")
    return d


def python(work):
    """The command a tracer's Python is started with, as trace3.py requires it (its `start_check`): isolated (-I),
    with no site directory (-S), writing no bytecode (-B) and looking for bytecode under a prefix that holds no
    file: this process's own prefix where it has one, or an empty directory made under `work`."""
    pre = sys.pycache_prefix
    if not pre:
        pre = Path(work) / "pyc"
        pre.mkdir(parents=True, exist_ok=True)
    return [sys.executable, "-I", "-S", "-B", "-X", f"pycache_prefix={pre}"]
