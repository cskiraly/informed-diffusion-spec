#!/usr/bin/env python3
"""Directed records for §6.1: directed61.py's samples, logged by trace3.py's tracer.

    python3 directed3.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

The generator is directed61.py's, unchanged: the same states, drawn without the document's invariants, the same
calls, and the same departures from the document (its docstring lists them). Only the tracer differs: a record
holds what the Python read and wrote, and beside it, as `rest`, every other entry of the node's state. The decoys
of the generated states are in `rest`: a twin that reads one reads an entry the Python did not, and fails on that
alone; a twin, or an operation of its tables, that changes one fails the comparison of the whole state. At every
call the tracer also checks its own log against the tables themselves (trace3.py's `account`), and stops if a
write went unlogged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import directed61                       # noqa: E402
import trace3                           # noqa: E402


class Tracer(trace3.Tracer3):
    def __init__(self, toy, out, argv, whole=False):        # directed61.py asks for the whole state: `rest`
        super().__init__(toy, out, ["directed3", *argv[1:]], whole=whole)


if __name__ == "__main__":
    directed61.trace61.Tracer = Tracer
    directed61.main(sys.argv[1:])
