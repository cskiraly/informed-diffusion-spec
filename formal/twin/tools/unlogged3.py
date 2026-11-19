#!/usr/bin/env python3
"""The control of the tracer's check of its own log (trace3.py's `account`): views that let a write through
without logging it.

    python3 unlogged3.py TOYDIR OUT.jsonl.gz [directed61.py's arguments ...]

The run is directed3.py's, but every twentieth assignment to an entry through a view is forwarded to the toy's
container and not logged. The tracer must stop, with a non-zero exit code and a line that says the log does not
account for the state: if it writes its trace to the end, the check of the log checks nothing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import directed3                        # noqa: E402
import footprint as F                   # noqa: E402

N = [0]
_set = F.View.__setitem__


def setitem(self, k, v):
    if self._r.on and self._leaf():
        N[0] += 1
        if N[0] % 20 == 0:
            self._o[k] = F.unwrap(v)    # the fault: the write is made, and not logged
            return
    _set(self, k, v)


F.View.__setitem__ = setitem

if __name__ == "__main__":
    directed3.directed61.trace61.Tracer = directed3.Tracer
    try:
        directed3.directed61.main(sys.argv[1:])
    finally:
        print(f"unlogged3: {N[0]} assignments through a view, {N[0] // 20} not logged", file=sys.stderr)
