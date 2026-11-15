#!/usr/bin/env python3
"""A known answer for the `late-block` cell's own check: a run that leaves something waiting fails.

    python3 late_drain_known.py [--doc v2]

The cell says that every node completes and that at the end nothing waits: no deferred copy, its id, tie,
reservation or block not installed. run.py checks both under `--late-block` and exits with a failure if either
does not hold, so check.py sees it. A count that is only printed would let a leak through with an unchanged
digest, since the digest hashes events, not state.

Two runs of the cell (check.py's base and `--late-block 30,400`): as it is, which must exit 0; and with a leak put
in by hand, which must exit with run.py's failure. The leak: each installation's deferred ids are put back
after `on_block_installed` has removed them, as if the document forgot `pending_ids.discard`. That changes no
event, so only the check can tell.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELL = ["--nodes", "60", "--degree", "30", "--msgs", "3", "--seed", "7", "--late-block", "30,400"]


def cell(leak, extra):
    sys.path.insert(0, str(HERE))
    import node as N
    import run
    if leak:
        installed = N.Node.install_block

        def leaky(self, root):
            ids = {self.ns["message_id"](f) for _, f in self.ns["pending"].get(root, [])}
            installed(self, root)
            self.ns["pending_ids"] |= ids           # the ids go back: a leak that changes no event
        N.Node.install_block = leaky
    run.main(CELL + extra)


def main(argv):
    if argv[:1] == ["--cell"]:
        return cell(argv[1] == "leak", argv[2:])
    extra = argv
    bad = 0
    for leak, want in ((False, 0), (True, 1)):
        p = subprocess.run([sys.executable, "-B", __file__, "--cell", "leak" if leak else "as-is", *extra],
                           capture_output=True, text=True)
        last = (p.stdout + p.stderr).strip().splitlines()[-1:]
        ok = (p.returncode == 0) if want == 0 else (p.returncode != 0 and "FAILED" in "".join(last))
        bad += not ok
        print(f"{'with the leak' if leak else 'as it is'}: rc={p.returncode}; its last line: {last[0] if last else ''}"
              f"{'' if ok else '  <-- must be ' + ('rc=0' if want == 0 else 'a FAILED line, rc not 0')}")
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
