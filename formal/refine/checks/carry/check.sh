#!/bin/bash
# The check of formal/refine/Carry (the carry of the model's safety theorem). It holds formal/refine's link to
# formal/veil (../veil-link.sh), builds the library from its sources, audits every theorem of its namespace (what
# it rests on), and compares the theorems' statements, the definitions and the inductive types with the recorded
# ones. `lake` and `lean` are the ones on PATH; it runs under the caller's limits.
#
#   bash formal/refine/checks/carry/check.sh              # check, and compare with the record
#   bash formal/refine/checks/carry/check.sh --update     # adopt the statements, after an intended change:
#                                                         #   never a pass; run it again without --update
#   bash formal/refine/checks/carry/check.sh --out DIR    # write the outputs to DIR (the controls do)
#
# The outputs: check.txt (this run), audit.txt (each theorem, its axioms; every statement, definition and
# inductive type). The reference, beside this script: statements.txt.
#
# It prints "check.sh: PASS" and exits 0 only if: the sources and the reference are HEAD's; formal/refine/Carry
# holds the thirteen known files, and no other; the lakefile has the library by its glob; the link to formal/veil
# holds and Veil's checkout is the manifest's; the build passes with no warning and leaves the manifest as it was, and the toy's
# invariant is checked for the initializer and the action; no file of Carry/ has `sorry` or `admit`; every theorem
# rests on allowed axioms only, no other axiom is declared, and the toy's four generated theorems are there on
# the allowed axioms; the theorems named below are among the audited ones; and every statement, definition
# and inductive type is the recorded one.
#
# What it does not check: that a statement means what its docstring says; the Veil model's statements themselves (they are
# hypotheses here: the structures FvRetryAsk, FvRetryNoop, FvPromiseDue, FvParkOther and FvInit, in the record); a
# declaration outside the namespace Refine.Carry (Refine's are ../twinstep's and ../asking's); and the twin (this check prints
# formal/twin's tree and pins nothing of it but that it is HEAD's).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
F=$(cd "$HERE/../../../.." && pwd)
R=$F/formal/refine
D=$HERE
UPDATE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --update) UPDATE=1 ;;
    --out) D=$2; shift ;;
    *) echo "usage: check.sh [--update] [--out DIR]"; exit 2 ;;
  esac
  shift
done
mkdir -p "$D"
OUT=$D/check.txt
ALL="Carry/AfterAsk.lean Carry/Bridge.lean Carry/BridgeToy.lean Carry/BridgeUse.lean Carry/Fv.lean Carry/Idle.lean Carry/Plain.lean Carry/Promise.lean Carry/PromiseRun.lean Carry/Run.lean Carry/Twin.lean Carry/TwinPromise.lean Carry/Witness.lean"
T=formal/refine/checks/carry
# what a run reads of the two packages, and never its own outputs (they lie beside this script)
PKG="formal/twin formal/refine/Refine formal/refine/Carry formal/refine/NoStallEquivModel.lean formal/refine/QuietRanking.lean formal/refine/lakefile.lean formal/refine/lake-manifest.json formal/refine/lean-toolchain formal/refine/checks/veil-link.sh"
fail=""
cd "$R"
{
  date '+start %F %T %Z'
  echo "commit $(git -C "$F" rev-parse --short=8 HEAD)"
  echo "trees: formal/twin $(git -C "$F" rev-parse --short=8 HEAD:formal/twin), formal/refine $(git -C "$F" rev-parse --short=8 HEAD:formal/refine)"
  # 1. the sources are HEAD's, and so is the reference this check compares with
  if git -C "$F" diff --quiet HEAD -- $PKG $T/Audit.lean $T/check.sh \
     && [ -z "$(git -C "$F" ls-files --others --exclude-standard -- $PKG)" ]; then
    echo "sources: as HEAD"
  else
    echo "sources: DIFFER from HEAD"
    fail="$fail dirty-sources"
  fi
  refs="$T/statements.txt"
  if [ "$UPDATE" = 1 ]; then
    echo "reference: not held to HEAD (--update writes it)"
  elif git -C "$F" diff --quiet HEAD -- $refs && git -C "$F" ls-files --error-unmatch $refs > /dev/null 2>&1; then
    echo "reference: as HEAD ($refs)"
  else
    echo "reference: DIFFERS from HEAD, or is not committed ($refs)"
    fail="$fail dirty-references"
  fi
  # 2. coverage: Carry/ holds the thirteen known files, and no other (the library takes every module under Carry/,
  #    and the audit imports four of them, which import the rest: a file added later must fail here until it is listed)
  have=$(ls Carry/*.lean | sort | tr '\n' ' ')
  if [ "$have" = "$ALL " ]; then echo "files: Carry/ holds the thirteen known ones"; else echo "files: Carry/ holds [$have], not [$ALL ]"; fail="$fail files"; fi
  if [ -z "$(find Carry -mindepth 1 ! -name '*.lean' | head -1)" ]; then echo "files: nothing else under Carry/"; else echo "files: something else under Carry/"; fail="$fail files"; fi
  if grep -q '^lean_lib Carry where$' lakefile.lean && grep -q '^  globs := #\[\.submodules `Carry\]$' lakefile.lean; then
    echo "library: the lakefile has Carry by its glob"
  else
    echo "library: the lakefile does NOT have Carry by its glob"; fail="$fail library"
  fi
  # 3. the link to formal/veil holds (the cut, QuietRanking, the toolchains, the manifest); Veil is the manifest's
  if bash "$HERE/../veil-link.sh"; then :; else fail="$fail veil-link"; fi
  cp lake-manifest.json "$D/manifest.before"
  want=$(python3 -c 'import json,sys; print([p["rev"] for p in json.load(open("lake-manifest.json"))["packages"] if p["name"] == "veil"][0])')
  got=$(git -C .lake/packages/veil rev-parse HEAD)
  if [ "$want" = "$got" ] && [ -z "$(git -C .lake/packages/veil status --porcelain)" ]; then
    echo "veil: the manifest's $want, clean"
  else
    echo "veil: checkout $got, manifest $want, or not clean"; fail="$fail veil"
  fi
  echo "toolchain: $(lean --version 2>/dev/null || echo "no lean on PATH")"
  sha256sum $ALL
  # 4. the library, built again from its sources, so that its warnings and errors are in this record
  rm -rf .lake/build/lib/lean/Carry .lake/build/ir/Carry
  set +e
  lake build Carry 2>&1 | grep -v '^✔' > "$D/build.tmp"
  brc=${PIPESTATUS[0]}
  set -e
  cat "$D/build.tmp"
  echo "lake build rc=$brc"
  [ "$brc" = 0 ] || fail="$fail build"
  if grep -q -i 'warning\|error' "$D/build.tmp"; then echo "build: warnings or errors"; fail="$fail warnings"; else echo "build: no warning"; fi
  # the toy: Veil checked its invariant for the initializer and for the action (two lines of each kind)
  if [ "$(grep -c '^  *flag_seen \.\.\. ✅$' "$D/build.tmp")" = 2 ] && [ "$(grep -c '^  *doesNotThrow \.\.\. ✅$' "$D/build.tmp")" = 2 ]; then
    echo "toy: the invariant and doesNotThrow checked, for the initializer and the action"
  else
    echo "toy: its check's four lines are NOT there"; fail="$fail toy"
  fi
  rm -f "$D/build.tmp"
  if cmp -s lake-manifest.json "$D/manifest.before"; then echo "the manifest: as before the build"
  else echo "the manifest: CHANGED by the build"; fail="$fail manifest"; fi
  rm -f "$D/manifest.before"
  n=$(cat Carry/*.lean | grep -c -w 'sorry\|admit' || true)
  echo "lines with sorry or admit in Carry/: $n"
  [ "$n" = 0 ] || fail="$fail sorry"
  # 5. every theorem of the namespace: its axioms; every statement, definition and inductive type
  set +e
  lake env lean "$HERE/Audit.lean" > "$D/audit.txt" 2>&1
  arc=$?
  set -e
  echo "audit rc=$arc"
  [ "$arc" = 0 ] || fail="$fail audit-run"
  sed -n '/^theorem /,/^audit: /p' "$D/audit.txt" | grep -v '^audit: ' || true
  grep '^audit: ' "$D/audit.txt" || { echo "audit: no summary"; fail="$fail audit-summary"; }
  grep -q '^audit: [0-9]* theorems, [0-9]* definitions, [0-9]* inductive types, [0-9]* axioms declared, 0 not allowed$' "$D/audit.txt" || fail="$fail axioms"
  # the theorems named here must be among the audited ones (a renamed or dropped one is not a pass)
  for t in bridge Meets.bridge toy_raise_flag_seen toy_init_flag_seen toy_raise_meets toy_init_meets toy_raise_plain \
           retryAsk_preserves retryNoop_preserves init_invariants \
           covered_preserves step_preserves carried carried_offers_resolve carried_from_init \
           work_iff minv_of_plain plain_of_minv offers_resolve_gives offers_resolve_twin carried_plain \
           run_held_or_window_or_clause run_safety_twin witness_safety control_asks_start control_asks_carried \
           idleButPromises_of_empty abs_prom promState_invariants promisedOne_idle promise_start promise_step_applies \
           retryFire_expired idleW_of_empty quietHeld_facts stalledStart_facts stalledStart_asks_facts \
           quietHeld_after_facts stalledStart_after_facts quietHeld_idle stalledStart_idle \
           abs_idle idleState_invariants idleState_no_work idleState_stalled \
           not_step_of_not_inv witness_start witness_step witness_after_abs witness_not_stutter witness_antecedent \
           witness_carried control_start control_after_abs control_stalled control_not_a_step \
           control_asks_when_not_expired held_last_open_breaks_window_retry bgFalse_init empty_is_init \
           open_window_is_work asks_opens_window covered_keeps_window covered_run_keeps_work \
           promiseFire_gone promiseFire_other promiseFire_parks promisedOne_facts \
           promiseDue_tr_intro parkOther_tr_intro promiseFire_noop_same promiseFire_parks_other_group_same \
           promiseFire_refines_promiseDue promiseFire_refines_parkOther promiseFire_other_chunk_parkOther \
           promiseDue_preserves parkOther_preserves promise_preserves promise_step promise_due_applies; do
    grep -q "^theorem Refine.Carry.$t: ok " "$D/audit.txt" || { echo "audit: $t is not there, or not ok"; fail="$fail named"; }
  done
  # 6. the statements, definitions and inductive types, against the record
  sed -n '/^statement /,$p' "$D/audit.txt" > "$D/statements.new"
  count() { echo "$(grep -c '^statement ' "$1") statements, $(grep -c "^axiom's statement " "$1") axioms', $(grep -c '^definition ' "$1") definitions, $(grep -c '^inductive ' "$1") inductive types, $(grep -c '^constructor ' "$1") constructors, $(grep -c '^toy statement ' "$1") of the toy's, $(grep -c '^fingerprint ' "$1") fingerprints"; }
  if [ "$UPDATE" = 1 ]; then
    cp "$D/statements.new" "$HERE/statements.txt"
    echo "statements: recorded now, not compared ($(count "$HERE/statements.txt"))"
  elif [ -f "$HERE/statements.txt" ] && cmp -s "$D/statements.new" "$HERE/statements.txt"; then
    echo "statements: as recorded ($(count "$HERE/statements.txt"))"
  else
    echo "statements: DIFFER from the record"
    diff "$HERE/statements.txt" "$D/statements.new" | head -20 || true
    fail="$fail statements"
  fi
  rm -f "$D/statements.new"
  date '+end %F %T %Z'
  if [ -n "$fail" ]; then echo "check.sh: FAIL ($(echo $fail))"
  elif [ "$UPDATE" = 1 ]; then echo "check.sh: UPDATED the statements; not a pass: commit them and run it again"
  else echo "check.sh: PASS"; fi
} > "$OUT" 2>&1
tail -3 "$OUT"
[ -z "$fail" ]
