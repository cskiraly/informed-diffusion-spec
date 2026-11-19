#!/usr/bin/env python3
"""The control of "the tracer perturbs nothing": trace3.py with a view that does perturb.

    python3 perturb3.py TOYDIR OUT.jsonl.gz [run.py's arguments ...]

The same run as trace3.py's, but every thousandth `get` of an entry through a recording view answers as if the
entry were missing. A cell run this way must not keep its golden digest: if it does, the digest does not see what
the views do, and "24 of 24 goldens" shows nothing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import footprint as F                   # noqa: E402
import trace3                           # noqa: E402

N = [0]
_get = F.View.get


def get(self, k, default=None):
    if self._r.on and self._leaf():
        N[0] += 1
        if N[0] % 1000 == 0:
            self._r.read(self._t, self._p + (k,))
            return default              # the perturbation: the entry read as missing
    return _get(self, k, default)


F.View.get = get

if __name__ == "__main__":
    try:
        trace3.main(sys.argv[1:])
    finally:
        print(f"perturb3: {N[0]} gets through a recording view, {N[0] // 1000} answered as missing", file=sys.stderr)
