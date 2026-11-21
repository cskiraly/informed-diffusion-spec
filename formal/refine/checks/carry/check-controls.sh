#!/bin/bash
# The controls of the carry's check (check.sh here). Two kinds; the table of what each must do is this script.
#
# A. Of check.sh, and of what the theorems rest on: each plants one change in the tree, runs check.sh with
#    its outputs in a directory of its own, and restores the change. A control passes when check.sh FAILS and its
#    fail list has the reason the change is for, and, where the control names them, none of the reasons it must
#    not have. (Every planted change also makes the tree differ from HEAD, so "dirty-sources" or
#    "dirty-references" is on every list: the reason named is the evidence, not the exit code.)
#    Among them, the ones that show a proof uses what its docstring says it uses (each must fail the BUILD):
#    - hypothesis-dropped: the third step kind without its named hypothesis;
#    - fv-clause: one of the Veil model's statements for retryNoop given for another clause;
#    - plain-clause, plain-work: a plain clause, and the plain `work`, that is not the generated one;
#    - toy-unchecked: the toy's action no longer keeps its invariant, so Veil generates no theorem for it.
#
# B. Of the twin's side: the twin changed in a COPY of formal/twin and formal/refine (the twin itself is not
#    touched). Refine/AskInterp.lean's own proofs walk retry_offer line by line and break first, and Lake then
#    builds nothing that imports them. So in the copy those named proofs are replaced by `sorry` (the control's
#    record lists them), and
#    Carry/Twin.lean is built there. A control passes when the build FAILS with no error in the twin's own files
#    and none in Refine/, and with BOTH of these among its errors in Carry/Twin.lean:
#    - a proof that no longer goes through, where the control names one;
#    - the named computed fact found false: the changed twin, run on the fixture, does something else.
#    The copy unchanged must build the whole library: without that, a copy that cannot build at all would pass.
#
#   bash formal/refine/checks/carry/check-controls.sh --part A   # writes check-controls-A.txt
#   ... --part B                                                         # writes check-controls-B.txt
#   (both write controls/<name>.txt; without --part: both parts in one run, to check-controls.txt)
#
# The two parts are there so that each can run alone: the whole took about five minutes on eight cores.
#
# Run it on a clean tree: it restores each file from HEAD. `lake` is PATH's; it runs under the caller's limits.
set -euo pipefail
PART=all
if [ "${1:-}" = --part ]; then PART=${2:-}; shift 2; fi
case "$PART" in
  all) REC=check-controls.txt ;;
  A|B) REC=check-controls-$PART.txt ;;
  *) echo "usage: check-controls.sh [--part A|B]"; exit 2 ;;
esac
[ $# = 0 ] || { echo "usage: check-controls.sh [--part A|B]"; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
F=$(cd "$HERE/../../../.." && pwd)
W=${WORK:-$F/formal/refine/.lake/checks-work/carry}      # where the controls' outputs and copies go
T=formal/refine/checks/carry
PKG="formal/twin formal/refine/Refine formal/refine/Carry formal/refine/NoStallEquivModel.lean formal/refine/QuietRanking.lean formal/refine/lakefile.lean formal/refine/lake-manifest.json formal/refine/lean-toolchain formal/refine/checks/veil-link.sh"
mkdir -p "$W" "$HERE/controls"
cd "$F"
[ -z "$(git status --porcelain -- $PKG $T/statements.txt $T/Audit.lean $T/check.sh)" ] \
  || { echo "check-controls.sh: the sources or the references are not HEAD's"; exit 2; }
command -v lake > /dev/null || { echo "check-controls.sh: no lake on PATH"; exit 2; }
bad=0
HEAD0=$(git rev-parse HEAD)
{
  date '+start %F %T %Z'
  echo "commit $(git rev-parse --short=8 HEAD)"
  echo "part $PART"
  verdict() {      # name, the reason expected, check.sh's rc, the reasons it must not have (a regex), if any;
                   # WHERE: for a build failure, a regex one of the build's error lines must match (the place and
                   # the kind of error the change is for), and no error may be in another file
    local name=$1 want=$2 rc=$3 unwanted=${4:-}
    cp "$W/$name/check.txt" "$HERE/controls/$name.txt"
    local line
    line=$(grep '^check.sh: ' "$W/$name/check.txt" || echo "check.sh: no verdict")
    if [ -n "${WHERE:-}" ]; then
      local wfile=${WHERE%%:*}
      if ! grep -Eq "^error: $WHERE" "$W/$name/check.txt"; then
        echo "$name: NOT at the place meant (no build error matches '$WHERE'): rc=$rc, $line"; bad=$((bad + 1)); return
      fi
      if grep '^error: [A-Za-z]' "$W/$name/check.txt" | grep -v "^error: $wfile:" | grep -vq '^error: build failed'; then
        echo "$name: build errors outside $wfile: rc=$rc, $line"; bad=$((bad + 1)); return
      fi
    fi
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
  if [ "$PART" != B ]; then        # part A (to its `fi` before part B; the lines between are not indented again)
  echo "A. of check.sh, and of what the theorems rest on"
  # a proof of the run's side replaced by sorry
  control sorry axioms formal/refine/Carry/Run.lean \
    "OLD = '  | other h => exact h\n'; NEW = '  | other h => sorry\n'; $sub"
  # a proof of the twin's side replaced by sorry
  control sorry-twin-side axioms formal/refine/Carry/Twin.lean \
    "OLD = '  promise := by intro q; simp [promisedP, hprom]\n'; NEW = '  promise := by sorry\n'; $sub"
  # a proof ended with admit
  control admit sorry formal/refine/Carry/Witness.lean \
    "OLD = '  simp [alpha, hlast] at h1\n'; NEW = '  admit\n'; $sub"
  # a condition added to a theorem that is not applied: it still builds, on the allowed axioms
  control statement statements formal/refine/Carry/AfterAsk.lean \
    "OLD = '    (hw : (abs kind ord n₀ k sl rt c₀).inWindow n₀ = true) :\n    NoStallEquiv.work r'; NEW = '    (hw : (abs kind ord n₀ k sl rt c₀).inWindow n₀ = true) (_extra : sl = sl) :\n    NoStallEquiv.work r'; $sub" \
    'build|warnings|axioms|sorry'
  # a definition changed under unchanged statements: a second connected peer in the fixtures' answers
  control definition statements formal/refine/Carry/Twin.lean \
    "OLD = '  { connectedTopicPeers := [1], authenticable'; NEW = '  { connectedTopicPeers := [1, 2], authenticable'; $sub" \
    'build|warnings|axioms|sorry'
  # the third step kind without its named hypothesis: the proof that a step preserves Invariants must not build
  WHERE='Carry/Run.lean:[0-9]+:[0-9]+: (Too many variable names provided at alternative `other`|Unknown identifier `h`)' \
  control hypothesis-dropped build formal/refine/Carry/Run.lean \
    "OLD = '  | other {c c\' : Cfg kind ord} (h : MInv kind ord r (abs kind ord n₀ k sl rt c\')) : Step n₀ k sl rt r c c\'\n'; NEW = '  | other {c c\' : Cfg kind ord} : Step n₀ k sl rt r c c\'\n'; $sub"
  # one of the Veil model's statements for retryNoop given for another clause: the preservation lemma must not build
  WHERE='Carry/Fv.lean:[0-9]+:[0-9]+: Application type mismatch' \
  control fv-clause build formal/refine/Carry/Fv.lean \
    "OLD = '  blocks : RetryNoopMeets kind ord CL(NoStallEquiv.blocks)\n'; NEW = '  blocks : RetryNoopMeets kind ord CL(NoStallEquiv.offers_resolve)\n'; $sub"
  # a plain clause that is not the generated one (window_retry turned round): the definitional check must fail
  WHERE='Carry/Plain.lean:[0-9]+:[0-9]+: Application type mismatch' \
  control plain-clause build formal/refine/Carry/Plain.lean \
    "OLD = '  window_retry : ∀ N, s.inWindow N = true → s.retryArmed N = true\n'; NEW = '  window_retry : ∀ N, s.retryArmed N = true → s.inWindow N = true\n'; $sub"
  # the plain work with one condition changed (an open window read as a closed one)
  WHERE='Carry/Plain.lean:[0-9]+:[0-9]+: Type mismatch' \
  control plain-work build formal/refine/Carry/Plain.lean \
    "OLD = '(∃ N, s.inWindow N = true) ∨\n'; NEW = '(∃ N, s.inWindow N = false) ∨\n'; $sub"
  # the toy's action no longer keeps its invariant: Veil's check fails, and no theorem is generated for it
  WHERE='Carry/BridgeToy.lean:[0-9]+:[0-9]+: Initialization must establish the invariant' \
  control toy-unchecked toy formal/refine/Carry/BridgeToy.lean \
    "OLD = '  flag n := true\n  seen n := true\n'; NEW = '  flag n := true\n'; $sub"
  # an axiom declared in the namespace
  control axiom axioms formal/refine/Carry/Witness.lean \
    "OLD = '\nend\n\nend Refine.Carry\n'; NEW = '\nend\n\naxiom bogus : False\n\nend Refine.Carry\n'; $sub"
  # a theorem made to rest on a declared axiom
  control axiom-used axioms formal/refine/Carry/Witness.lean \
    "OLD = '\nend\n\nend Refine.Carry\n'; NEW = '\nend\n\naxiom extra : 0 = 0\ntheorem uses_extra : 0 = 0 := extra\n\nend Refine.Carry\n'; $sub"
  # the statements' record edited, not committed
  control reference-statements dirty-references $T/statements.txt \
    "import sys; p = sys.argv[1]; open(p, 'a').write('statement Refine.Carry.added : True\n')"
  # a file added to Carry/ that the check's list does not name
  printf 'namespace Refine.Carry\ntheorem unlisted : 0 = 0 := rfl\nend Refine.Carry\n' > formal/refine/Carry/Unlisted.lean
  set +e
  bash "$HERE/check.sh" --out "$W/new-file" > /dev/null 2>&1
  rc=$?
  set -e
  rm -f formal/refine/Carry/Unlisted.lean
  verdict new-file files "$rc"
  # and the tree as it is passes
  set +e
  bash "$HERE/check.sh" --out "$W/clean" > /dev/null 2>&1
  rc=$?
  set -e
  cp "$W/clean/check.txt" "$HERE/controls/clean.txt"
  line=$(grep '^check.sh: ' "$W/clean/check.txt" || echo "check.sh: no verdict")
  if [ "$rc" = 0 ] && [ "$line" = "check.sh: PASS" ]; then echo "clean: passes: rc=$rc, $line"; else echo "clean: DOES NOT pass: rc=$rc, $line"; bad=$((bad + 1)); fi

  fi                               # part A's end
  if [ "$PART" != A ]; then        # part B (to its `fi` before the HEAD test)
  echo "B. of the twin's side: the twin changed in a copy, Refine/AskInterp.lean's broken proofs replaced by sorry there"
  ( cd "$W" && rm -rf twin-clean twin-expired-dropped twin-held-turned twin-promise-turned )
  # replaces, in the copy's AskInterp.lean, the proof of each named theorem by `sorry`: from its `:= by` to the
  # line before the next line that does not start with a space (a proof on the theorem's own line too)
  sorry_proofs='
import sys, re
p = sys.argv[1]; s = open(p).read()
for name in sys.argv[2:]:
    i = s.index("theorem " + name + " ")
    j = s.index(":= by", i) + len(":= by")
    m = re.compile(r"^\S", re.M).search(s, s.index("\n", j))
    s = s[:j] + " sorry\n" + s[m.start():]
open(p, "w").write(s)
'
  twin() {         # name, pass or fail, the python that changes the copy's Sec61.lean (or none), the computed fact,
                   # the theorem whose proof must be among the errors (its name, or no), Refine/AskInterp.lean's proofs to replace;
                   # TWINFILE: the file of Carry/ built and read for the errors (Twin.lean unless set)
    local name=$1 must=$2 code=${3:-} factname=${4:-} proof=${5:-no} tf=${TWINFILE:-Twin}
    shift; shift; shift || true; shift || true; shift || true
    mkdir -p "$W/$name"
    mkdir -p "$W/$name/formal"                         # the two packages alone, their builds with them
    cp -a --reflink=auto "$F/formal/twin" "$F/formal/refine" "$W/$name/formal/"
    local target=Carry
    if [ -n "$code" ]; then
      python3 -c "$code" "$W/$name/formal/twin/SpecTwin/Sec61.lean"
      python3 -c "$sorry_proofs" "$W/$name/formal/refine/Refine/AskInterp.lean" "$@"
      target=Carry.$tf
    fi
    set +e
    (cd "$W/$name/formal/refine" && lake build $target) > "$W/$name/build.txt" 2>&1
    local rc=$?
    set -e
    { [ -z "$code" ] || { diff "$F/formal/twin/SpecTwin/Sec61.lean" "$W/$name/formal/twin/SpecTwin/Sec61.lean" || true
        echo "Refine/AskInterp.lean's proofs replaced by sorry in the copy: $*"; }
      grep -v '^✔' "$W/$name/build.txt" | cut -c1-400 | head -60 || true
      echo "lake build $target rc=$rc"; } > "$HERE/controls/$name.txt"
    if [ "$must" = pass ]; then
      if [ "$rc" = 0 ]; then echo "$name: builds, as it must: rc=$rc"; else echo "$name: DOES NOT build: rc=$rc"; bad=$((bad + 1)); fi
      return
    fi
    local here refine_err twin_err fact computed
    here=$(grep -c "^error: Carry/$tf.lean" "$W/$name/build.txt" || true)
    refine_err=$(grep -c '^error: Refine/' "$W/$name/build.txt" || true)
    twin_err=$(grep -c '^error: .*SpecTwin' "$W/$name/build.txt" || true)
    # the computed fact found false: native_decide's error at the fact's own lines, in the copy
    fact=$(grep -n "^theorem $factname " "$W/$name/formal/refine/Carry/$tf.lean" | cut -d: -f1)
    # (the fact's own lines: from its `theorem` line to the next declaration or docstring)
    local factend
    factend=$(awk -v a="$fact" 'NR > a && /^(theorem|def|structure|inductive|end|section|namespace) / { print NR; exit } NR > a && /^\/--/ { print NR; exit }' "$W/$name/formal/refine/Carry/$tf.lean")
    computed=$(awk -v a="$fact" -v b="$factend" -v f="Carry/$tf.lean" -F: '$1 == "error" && $2 == " " f && /Tactic `native_decide` evaluated that the proposition/ { if ($3 >= a && $3 < b) n++ } END { print n + 0 }' "$W/$name/build.txt")
    { echo "errors in Carry/$tf.lean: $here; in Refine/: $refine_err; in the twin: $twin_err; the computed fact $factname (line $fact) found false: $computed"
      echo "every error's first line, and the computed fact's error (the build's lines above stop at 60):"
      grep '^error: ' "$W/$name/build.txt" | cut -c1-200 || true
      grep -A9 "^error: Carry/$tf.lean:[0-9]*:[0-9]*: Tactic \`native_decide\` evaluated" "$W/$name/build.txt" | cut -c1-200 || true
    } >> "$HERE/controls/$name.txt"
    # the named proof broken: an error at a line of that theorem (from its `theorem` line to the next declaration)
    local need=1 broken=1
    if [ "$proof" != no ]; then
      need=2
      local pl pn
      pl=$(grep -n "^theorem $proof " "$W/$name/formal/refine/Carry/$tf.lean" | cut -d: -f1)
      pn=$(awk -v a="$pl" 'NR > a && /^(theorem|def|structure|inductive|\/--|end|section|namespace) / { print NR; exit } NR > a && /^\/--/ { print NR; exit }' "$W/$name/formal/refine/Carry/$tf.lean")
      broken=$(awk -v a="$pl" -v b="$pn" -v f="Carry/$tf.lean" -F: '$1 == "error" && $2 == " " f && $3 >= a && $3 < b { n++ } END { print n + 0 }' "$W/$name/build.txt")
      echo "the proof of $proof (lines $pl to $pn): $broken errors" >> "$HERE/controls/$name.txt"
    fi
    if [ "$rc" != 0 ] && [ "$here" -ge "$need" ] && [ "$broken" -ge 1 ] && [ "$computed" = 1 ] && [ "$twin_err" = 0 ] && [ "$refine_err" = 0 ]; then
      echo "$name: the build fails as it must: rc=$rc, $here errors in Carry/$tf.lean, the computed fact $factname found false among them, none in the twin or in Refine/"
    else
      echo "$name: NOT as it must be: rc=$rc, $here errors in Carry/$tf.lean (at least $need wanted), the named proof's errors $broken, the computed fact $factname found false $computed times, $twin_err in the twin, $refine_err in Refine/"; bad=$((bad + 1))
    fi
  }
  # the copy as it is: the whole library builds
  twin twin-clean pass
  # retry_offer's expired test dropped: on the control's world the twin asks, where it must return.
  # The proof retryFire_expired breaks, and stalledStart_after_facts is false.
  twin twin-expired-dropped fail \
    "OLD = '  if (← expired a.group) then branch \"retry_offer: expired\"; return\n'; NEW = ''; $sub" \
    stalledStart_after_facts retryFire_expired run_retryOffer_asks
  # retry_offer's held test turned: on the witness's world the twin goes on and asks, where it must return.
  # quietHeld_after_facts is false. (retryFire_expired breaks too: it walks past the held test.) Piece 1's own
  # computed fact threeAnn_after_facts is false under this change as well, and is among the three replaced.
  twin twin-held-turned fail \
    "OLD = '  if (← held a) then branch \"retry_offer: held\"; return\n'; NEW = '  if !(← held a) then branch \"retry_offer: held\"; return\n'; $sub" \
    quietHeld_after_facts no run_retryOffer_asks retryFire_held threeAnn_after_facts
  # promise_due's test of the promise's time turned: on promisedOne the twin returns ("another ask's") where it
  # must park. The proofs of promiseFire_other and promiseFire_parks break, and promisedOne_facts is false.
  # Piece 1's files do not walk promise_due, so nothing of theirs is replaced.
  TWINFILE=TwinPromise twin twin-promise-turned fail \
    "OLD = '  if t != at_ then                                          -- delivered, closed on decode, or gone\n'; NEW = '  if t == at_ then                                          -- delivered, closed on decode, or gone\n'; $sub" \
    promisedOne_facts promiseFire_parks
  fi                               # part B's end
  # HEAD must be the same at the end as at the start: the controls restore from
  # HEAD and the check compares with it
  if [ "$(git rev-parse HEAD)" != "$HEAD0" ]; then
    echo "HEAD moved during the run: $(git rev-parse --short=8 "$HEAD0") at its start, $(git rev-parse --short=8 HEAD) at its end"; bad=$((bad + 1))
  fi
  date '+end %F %T %Z'
  if [ "$bad" = 0 ]; then echo "check-controls.sh: every control as it must be"; else echo "check-controls.sh: $bad NOT as it must be"; fi
} > "$HERE/$REC" 2>&1
cat "$HERE/$REC"
[ "$bad" = 0 ]
