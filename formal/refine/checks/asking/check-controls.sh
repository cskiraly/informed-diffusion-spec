#!/bin/bash
# The controls of the asking path's check (check.sh here). Two kinds; the table of what each must do is this
# script.
#
# A. Of check.sh: each plants one change in the tree, runs check.sh with its outputs in a directory of its
#    own, and restores the change. A control passes when check.sh FAILS and its fail list has the reason the change
#    is for, and, where the control names them, none of the reasons it must not have. (Every planted change also
#    makes the tree differ from HEAD, so "dirty-sources" or "dirty-references" is on every list: the reason named
#    is the evidence, not the exit code.)
#
# B. Of the theorems: the twin changed in a COPY of formal/twin and formal/refine (the twin itself is not
#    touched), with the theorems still stated as they are, and this check's two files built there. A control passes when the build
#    FAILS, with none of its errors in the twin's own files (a change that does not compile shows nothing), and
#    with BOTH of these among its errors in Refine/AskInterp.lean:
#    - a proof that no longer goes through (this alone shows only that the proof depends on the changed line: a
#      change that keeps the behaviour could fail the same way);
#    - the computed fact threeAnn_after_facts found false: the changed twin, run on the three announcers' world
#      with the answers as they are, does something else. This is the control with the admission outcome fixed.
#    The copy unchanged must build: without that, a copy that cannot build at all would pass.
#
#   bash formal/refine/checks/asking/check-controls.sh      # writes check-controls.txt and controls/<name>.txt
#
# Run it on a clean tree: it restores each file from HEAD. `lake` is PATH's; it runs under the caller's limits.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
F=$(cd "$HERE/../../../.." && pwd)
W=${WORK:-$F/formal/refine/.lake/checks-work/asking}      # where the controls' outputs and copies go
T=formal/refine/checks/asking
PKG="formal/twin formal/refine/Refine formal/refine/Carry formal/refine/NoStallEquivModel.lean formal/refine/QuietRanking.lean formal/refine/lakefile.lean formal/refine/lake-manifest.json formal/refine/lean-toolchain formal/refine/checks/veil-link.sh"
mkdir -p "$W" "$HERE/controls"
cd "$F"
[ -z "$(git status --porcelain -- $PKG $T/statements.txt $T/Audit.lean $T/check.sh)" ] \
  || { echo "check-controls.sh: the sources or the references are not HEAD's"; exit 2; }
command -v lake > /dev/null || { echo "check-controls.sh: no lake on PATH"; exit 2; }
bad=0
{
  date '+start %F %T %Z'
  echo "commit $(git rev-parse --short=8 HEAD)"
  verdict() {      # name, the reason expected, check.sh's rc, the reasons it must not have (a regex), if any
    local name=$1 want=$2 rc=$3 unwanted=${4:-}
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
  control() {      # name, the reason expected, the file changed, the python that changes it, the unwanted reasons
    local name=$1 want=$2 file=$3 code=$4 unwanted=${5:-}
    python3 -c "$code" "$F/$file"
    set +e
    bash "$HERE/check.sh" --out "$W/$name" > /dev/null 2>&1
    local rc=$?
    set -e
    git checkout HEAD -- "$file"
    verdict "$name" "$want" "$rc" "$unwanted"
  }
  sub='import sys; p = sys.argv[1]; s = open(p).read(); a, b = OLD, NEW; assert s.count(a) == 1, a; open(p, "w").write(s.replace(a, b))'
  echo "A. of check.sh"
  # a proof of the model's side replaced by sorry
  control sorry axioms formal/refine/Refine/RetryAsk.lean \
    "OLD = '  simp [alpha, askedWorld_queued, hadm, hqd] at hst\n'; NEW = '  sorry\n'; $sub"
  # a proof of the twin's side replaced by sorry
  control sorry-twin-side axioms formal/refine/Refine/AskInterp.lean \
    "OLD = '  simp [askedWorld, hadm]\n'; NEW = '  sorry\n'; $sub"
  # a proof ended with admit
  control admit sorry formal/refine/Refine/RetryAsk.lean \
    "OLD = '  simp [alpha, askedWorld_queued, hadm, hqd] at hst\n'; NEW = '  admit\n'; $sub"
  # a condition added to a theorem that is not applied: it still builds, on the allowed axioms
  control statement statements formal/refine/Refine/AskInterp.lean \
    "OLD = '    (hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = false) :\n    (retryFire i a ctx ans w).made = w.made'; NEW = '    (hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = false) (_extra : ans.live 0 = true) :\n    (retryFire i a ctx ans w).made = w.made'; $sub" \
    'build|warnings|axioms|sorry'
  # a condition added to the main theorem: its applications no longer build
  control statement-applied build formal/refine/Refine/RetryAsk.lean \
    "OLD = '    (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) :\n    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord\n      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ (pickP ctx ans w.st a)\n      (nextOrd ord'; NEW = '    (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) (_extra : ans.live 0 = false) :\n    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord\n      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ (pickP ctx ans w.st a)\n      (nextOrd ord'; $sub"
  # a default of the answers changed: no statement or printed definition shows it; the fingerprints must
  control default statements formal/refine/Refine/AskInterp.lean \
    "OLD = '  live : Nat → Bool := fun _ => true\n'; NEW = '  live : Nat → Bool := fun _ => false\n'; $sub" \
    'build|warnings|axioms|sorry'
  # a definition changed under unchanged statements: a fixture's constant
  control definition statements formal/refine/Refine/AskInterp.lean \
    "OLD = 'PROMISE := 0.4, PARK_TTL := 30.0, MAX_PLAIN_CHUNKS := 8192 }'; NEW = 'PROMISE := 0.4, PARK_TTL := 31.0, MAX_PLAIN_CHUNKS := 8192 }'; $sub" \
    'build|warnings|axioms|sorry'
  # an axiom declared under an applied theorem's name
  control axiom axioms formal/refine/Refine/RetryAsk.lean \
    "OLD = '\nend Refine.Ask\n'; NEW = '\naxiom retryFire_refines_applies.bogus : False\n\nend Refine.Ask\n'; $sub"
  # a theorem made to rest on a declared axiom
  control axiom-used axioms formal/refine/Refine/RetryAsk.lean \
    "OLD = '\nend Refine.Ask\n'; NEW = '\naxiom extra : 0 = 0\ntheorem uses_extra : 0 = 0 := extra\n\nend Refine.Ask\n'; $sub"
  # the statements' record edited, not committed
  control reference-statements dirty-references $T/statements.txt \
    "import sys; p = sys.argv[1]; open(p, 'a').write('statement Refine.Ask.added : True\n')"
  # a file added to Refine/ that no list of the check names
  printf 'namespace Refine.Ask\ntheorem unlisted : 0 = 0 := rfl\nend Refine.Ask\n' > formal/refine/Refine/Unlisted.lean
  set +e
  bash "$HERE/check.sh" --out "$W/new-file" > /dev/null 2>&1
  rc=$?
  set -e
  rm -f formal/refine/Refine/Unlisted.lean
  verdict new-file files "$rc"
  # and the tree as it is passes
  set +e
  bash "$HERE/check.sh" --out "$W/clean" > /dev/null 2>&1
  rc=$?
  set -e
  cp "$W/clean/check.txt" "$HERE/controls/clean.txt"
  line=$(grep '^check.sh: ' "$W/clean/check.txt" || echo "check.sh: no verdict")
  if [ "$rc" = 0 ] && [ "$line" = "check.sh: PASS" ]; then echo "clean: passes: rc=$rc, $line"; else echo "clean: DOES NOT pass: rc=$rc, $line"; bad=$((bad + 1)); fi

  echo "B. of the theorems: the twin changed in a copy, the theorems as stated"
  ( cd "$W" && rm -rf twin-clean twin-enqueue-dropped twin-window-turned twin-untried-turned )
  twin() {         # name, whether the build must pass, the python that changes the copy's Sec61.lean (or none)
    local name=$1 must=$2 code=${3:-}
    mkdir -p "$W/$name"
    mkdir -p "$W/$name/formal"                         # the two packages alone, their builds with them
    cp -a --reflink=auto "$F/formal/twin" "$F/formal/refine" "$W/$name/formal/"
    [ -z "$code" ] || python3 -c "$code" "$W/$name/formal/twin/SpecTwin/Sec61.lean"
    set +e
    (cd "$W/$name/formal/refine" && lake build Refine.AskInterp Refine.RetryAsk) > "$W/$name/build.txt" 2>&1
    local rc=$?
    set -e
    { [ -z "$code" ] || diff "$F/formal/twin/SpecTwin/Sec61.lean" "$W/$name/formal/twin/SpecTwin/Sec61.lean" || true
      grep -v '^✔' "$W/$name/build.txt" | cut -c1-400 | head -60 || true
      echo "lake build rc=$rc"; } > "$HERE/controls/$name.txt"
    local here twin_err fact computed
    here=$(grep -c '^error: Refine/AskInterp.lean' "$W/$name/build.txt" || true)
    twin_err=$(grep -c '^error: .*SpecTwin' "$W/$name/build.txt" || true)
    # the computed fact found false: native_decide's error at the fact's own lines, in the copy
    fact=$(grep -n '^theorem threeAnn_after_facts' "$W/$name/formal/refine/Refine/AskInterp.lean" | cut -d: -f1)
    computed=$(awk -v a="$fact" -F: '/^error: Refine\/AskInterp.lean:[0-9]+:[0-9]+: Tactic `native_decide` evaluated that the proposition/ { if ($3 >= a && $3 <= a + 8) n++ } END { print n + 0 }' "$W/$name/build.txt")
    { echo "errors in Refine/AskInterp.lean: $here; in the twin: $twin_err; the computed fact (line $fact) found false: $computed"
      echo "every error's first line, and the computed fact's error (the build's lines above stop at 60):"
      grep '^error: ' "$W/$name/build.txt" | cut -c1-200 || true
      grep -A9 '^error: Refine/AskInterp.lean:[0-9]*:[0-9]*: Tactic `native_decide` evaluated' "$W/$name/build.txt" | cut -c1-200 || true
    } >> "$HERE/controls/$name.txt"
    if [ "$must" = pass ]; then
      if [ "$rc" = 0 ]; then echo "$name: builds, as it must: rc=$rc"; else echo "$name: DOES NOT build: rc=$rc"; bad=$((bad + 1)); fi
    elif [ "$rc" != 0 ] && [ "$here" -ge 2 ] && [ "$computed" = 1 ] && [ "$twin_err" = 0 ]; then
      echo "$name: the build fails as it must: rc=$rc, $here errors in Refine/AskInterp.lean, the computed fact found false among them, none in the twin"
    else
      echo "$name: NOT as it must be: rc=$rc, $here errors in Refine/AskInterp.lean, the computed fact found false $computed times, $twin_err in the twin"; bad=$((bad + 1))
    fi
  }
  # the copy as it is
  twin twin-clean pass
  # retry_offer's enqueue dropped: the twin notes the ask and arms the timer, and queues nothing
  twin twin-enqueue-dropped fail \
    "OLD = '    let _ ← enqueue pick (.iwant [a]) false\n'; NEW = '    pure ()\n'; $sub"
  # retry_offer's window comparison turned: it goes on while the ask is in flight, and returns once the window closed
  twin twin-window-turned fail \
    "OLD = '  if ctx.now - (← askedAt? a).getD negInf < ctx.c.IWANT_WINDOW then\n    branch \"retry_offer: in flight\"'; NEW = '  if ctx.now - (← askedAt? a).getD negInf >= ctx.c.IWANT_WINDOW then\n    branch \"retry_offer: in flight\"'; $sub"
  # untried's test turned: the pick is the earliest announcer already asked
  twin twin-untried-turned fail \
    "OLD = '    if (← tried? a q).isNone then return some q\n'; NEW = '    if (← tried? a q).isSome then return some q\n'; $sub"
  date '+end %F %T %Z'
  if [ "$bad" = 0 ]; then echo "check-controls.sh: every control as it must be"; else echo "check-controls.sh: $bad NOT as it must be"; fi
} > "$HERE/check-controls.txt" 2>&1
cat "$HERE/check-controls.txt"
[ "$bad" = 0 ]
