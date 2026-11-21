#!/bin/bash
# The controls of check.sh: each plants one change, runs check.sh with its outputs in a directory of its own, and
# restores the change. A control passes when check.sh FAILS and its fail list has the reason the change is for, and,
# where the control names them, none of the reasons it must not have (a statement control that fails by a build
# error proves nothing of the statements' comparison).
# (Every planted change also makes the tree differ from HEAD, so "dirty-sources" or "dirty-references" is on
# every list: the reason named below is the evidence, not the exit code.)
#
#   bash formal/refine/checks/twinstep/check-controls.sh     # writes check-controls.txt and controls/<name>.txt
#
# Run it on a clean tree: it restores each file from HEAD.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
F=$(cd "$HERE/../../../.." && pwd)
W=${WORK:-$F/formal/refine/.lake/checks-work/twinstep}      # where the controls' outputs go before they are copied here
T=formal/refine/checks/twinstep
PKG="formal/twin formal/refine/Refine formal/refine/Carry formal/refine/NoStallEquivModel.lean formal/refine/QuietRanking.lean formal/refine/lakefile.lean formal/refine/lake-manifest.json formal/refine/lean-toolchain formal/refine/checks/veil-link.sh"
mkdir -p "$W" "$HERE/controls"
cd "$F"
# what the controls change and restore from HEAD must be HEAD's now (check.sh's own outputs may differ)
[ -z "$(git status --porcelain -- $PKG $T/statements.txt $T/Audit.lean $T/Printed.lean $T/check.sh)" ] \
  || { echo "check-controls.sh: the sources or the references are not HEAD's"; exit 2; }
bad=0
{
  date '+start %F %T %Z'
  echo "commit $(git rev-parse --short=8 HEAD)"
  control() {      # name, the reason expected, the file changed, the python that changes it, and the reasons it must
    local name=$1 want=$2 file=$3 code=$4 unwanted=${5:-}   #   not have (a regex of names), if any
    python3 -c "$code" "$F/$file"
    set +e
    bash "$HERE/check.sh" --out "$W/$name" > /dev/null 2>&1
    local rc=$?
    set -e
    git checkout HEAD -- "$file"
    cp "$W/$name/check.txt" "$HERE/controls/$name.txt"
    local line
    line=$(grep '^check.sh: ' "$W/$name/check.txt" || echo "check.sh: no verdict")
    if [ -n "$unwanted" ] && echo "$line" | grep -Eq "FAIL \(.*\b($unwanted)\b.*\)"; then
      echo "$name: fails, but also on what it must not ($unwanted): rc=$rc, $line"; bad=$((bad + 1))
    elif [ "$rc" != 0 ] && echo "$line" | grep -q "FAIL (.*\b$want\b.*)"; then
      echo "$name: fails as it must, on $want: rc=$rc, $line"
    else
      echo "$name: DOES NOT fail on $want: rc=$rc, $line"; bad=$((bad + 1))
    fi
  }
  sub='import sys; p = sys.argv[1]; s = open(p).read(); a, b = OLD, NEW; assert s.count(a) == 1, a; open(p, "w").write(s.replace(a, b))'
  # a proof replaced by sorry
  control sorry axioms formal/refine/Refine/Controls.lean \
    "OLD = '  exact absurd hg.2.1 (by simp)\n'; NEW = '  sorry\n'; $sub"
  # a proof ended with admit
  control admit sorry formal/refine/Refine/Controls.lean \
    "OLD = '  exact absurd hg.2.1 (by simp)\n'; NEW = '  admit\n'; $sub"
  # a condition added to a theorem, which still builds and rests on the allowed axioms
  control statement statements formal/refine/Refine/Controls.lean \
    "OLD = '    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :\n    alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st) ≠\n'; NEW = '    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) (_extra : ans.live 0 = true) :\n    alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st) ≠\n'; $sub" \
    'build|warnings|axioms|sorry'
  # a definition changed under unchanged statements: the interpreter's step named, with other arguments
  control definition statements formal/refine/Refine/Controls.lean \
    "OLD = 'def someCtx : Ctx := ⟨⟨0.2, 0.05, 0.4, 30.0, none,'; NEW = 'def someCtx : Ctx := ⟨⟨0.2, 0.05, 0.4, 31.0, none,'; $sub" \
    'build|warnings|axioms|sorry'
  # an axiom declared under a computed theorem's name
  control axiom axioms formal/refine/Refine/Controls.lean \
    "OLD = '\nend Refine\n'; NEW = '\naxiom promiseDue_refines_applies.bogus : False\n\nend Refine\n'; $sub"
  # a theorem made to rest on a declared axiom
  control axiom-used axioms formal/refine/Refine/Controls.lean \
    "OLD = '\nend Refine\n'; NEW = '\naxiom extra : 0 = 0\ntheorem uses_extra : 0 = 0 := extra\n\nend Refine\n'; $sub"
  # the statements' record edited, not committed
  control reference-statements dirty-references $T/statements.txt \
    "import sys; p = sys.argv[1]; open(p, 'a').write('statement Refine.added : True\n')"
  # the model's file no longer the cut of formal/veil's (a comment line more): the link must fail
  control link-cut veil-link formal/refine/NoStallEquivModel.lean \
    "import sys; p = sys.argv[1]; open(p, 'a').write('-- a line more\n')"
  # QuietRanking.lean no longer formal/veil's
  control link-ranking veil-link formal/refine/QuietRanking.lean \
    "import sys; p = sys.argv[1]; open(p, 'a').write('-- a line more\n')"
  # and the tree as it is passes
  set +e
  bash "$HERE/check.sh" --out "$W/clean" > /dev/null 2>&1
  rc=$?
  set -e
  line=$(grep '^check.sh: ' "$W/clean/check.txt" || echo "check.sh: no verdict")
  if [ "$rc" = 0 ] && [ "$line" = "check.sh: PASS" ]; then echo "clean: passes: rc=$rc, $line"; else echo "clean: DOES NOT pass: rc=$rc, $line"; bad=$((bad + 1)); fi
  date '+end %F %T %Z'
  if [ "$bad" = 0 ]; then echo "check-controls.sh: every control as it must be"; else echo "check-controls.sh: $bad NOT as it must be"; fi
} > "$HERE/check-controls.txt" 2>&1
cat "$HERE/check-controls.txt"
[ "$bad" = 0 ]
