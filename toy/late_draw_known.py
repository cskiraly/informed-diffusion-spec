#!/usr/bin/env python3
"""Known answers for `--late-block`'s draw of the late nodes and for its argument.

    python3 late_draw_known.py

- 0 % draws no node (it once drew one: fail_select's draw has a floor of one).
- 30 % of 60 nodes, node 1 publishing, draws the 18 nodes the `late-block` cell was recorded with, which are
  fail_select's under the same domain.
- A node that publishes is never drawn, whichever it is: at 100 %, with node 2 publishing every payload, node 2
  is not drawn and node 1 is.
- An argument out of range, or not a number, is refused.
"""
import contextlib
import io
import sys
from pathlib import Path

DOMAIN = 0x1A7EB10C1A7EB10C


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import scenario
    bad = 0

    def line(what, got, want):
        nonlocal bad
        bad += got != want
        print(f"{what}: {got}{'' if got == want else f'  <-- must be {want}'}")

    line("0 %, 60 nodes, node 1 publishing", sorted(scenario.late_select(7, 60, 0, {1})), [])
    line("30 %, 60 nodes, node 1 publishing, against fail_select's draw",
         scenario.late_select(7, 60, 30, {1}) == scenario.fail_select(7, 60, 30, domain=DOMAIN), True)
    line("  how many", len(scenario.late_select(7, 60, 30, {1})), 18)
    drawn = scenario.late_select(7, 10, 100, {2})
    line("100 %, 10 nodes, node 2 publishing: node 2 drawn, node 1 drawn", (2 in drawn, 1 in drawn), (False, True))
    for arg in ("101,400", "-1,400", "30,-5", "30,400,-1", "30.5,400", "30", "x,400", "30,400,2.5"):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                run.main(["--nodes", "5", "--latency-only", f"--late-block={arg}"])
                rc = 0
            except SystemExit as e:
                rc = e.code
        line(f"--late-block {arg}: refused", rc == 2 and "--late-block PCT,MS[,STORE]" in err.getvalue(), True)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
