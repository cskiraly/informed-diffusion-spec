#!/usr/bin/env python3
"""A known answer for the `late-block` cell's own check: a run that leaves something waiting fails.

    python3 late_drain_known.py [--doc v2]

The cell says that every node completes and that at the end nothing waits: no deferred copy, its id, tie,
reservation or block not installed. run.py checks both under `--late-block` and exits with a failure if either
does not hold, so check.py sees it. A count that is only printed would let a leak through with an unchanged
digest, since the digest hashes events, not state.

Three runs of the cell (check.py's base and `--late-block 30,400`): as it is, which must exit 0; with a leak put in
by hand, which must exit with run.py's failure naming entries that still wait; and with one node on time that
gets no chunk, which must exit with the failure naming payloads missing. The leak: each installation's deferred
ids are put back after `on_block_installed` has removed them, as if the document forgot `pending_ids.discard`.
That changes no event, so only the check can tell.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELL = ["--nodes", "60", "--degree", "30", "--msgs", "3", "--seed", "7", "--late-block", "30,400"]


def cell(mode, extra):
    sys.path.insert(0, str(HERE))
    import node as N
    import run
    import sim as S
    if mode == "miss":                              # one node on time gets no chunk at all: it misses every
        delivered = S.Sim._deliver                  #   payload, and nothing is left waiting

        def deliver(self, src, dst, e, data, ctrl):
            if dst == max(set(self.nodes) - set(self.cfg["late_nodes"])) and e.chunk is not None:
                return
            return delivered(self, src, dst, e, data, ctrl)
        S.Sim._deliver = deliver
    if mode == "leak":
        installed = N.Node.install_block

        def leaky(self, root):
            ids = {self.ns["message_id"](f) for _, f in self.ns["pending"].get(root, [])}
            installed(self, root)
            self.ns["pending_ids"] |= ids           # the ids go back: a leak that changes no event
        N.Node.install_block = leaky
    run.main(CELL + extra)


def main(argv):
    if argv[:1] == ["--cell"]:
        return cell(argv[1], argv[2:])
    extra = argv
    bad = 0
    for mode, want in (("as-is", None), ("leak", "entries still wait"), ("miss", "payloads missing")):
        p = subprocess.run([sys.executable, "-B", __file__, "--cell", mode, *extra], capture_output=True, text=True)
        last = "".join((p.stdout + p.stderr).strip().splitlines()[-1:])
        if want is None:
            ok = p.returncode == 0
        else:                                       # the FAILED line, with a count not 0 for what was put in
            import re
            m = re.search(r"(\d+) " + want, last)
            ok = p.returncode != 0 and "FAILED" in last and m is not None and int(m.group(1)) > 0
        bad += not ok
        print(f"{ {'as-is': 'as it is', 'leak': 'with a leak', 'miss': 'with a node missing every payload'}[mode] }: "
              f"rc={p.returncode}; its last line: {last}"
              f"{'' if ok else '  <-- must be ' + ('rc=0' if want is None else 'a FAILED line with ' + want + ' not 0')}")
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
