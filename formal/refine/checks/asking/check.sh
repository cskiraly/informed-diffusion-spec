#!/bin/bash
# The check of the asking path refined (Refine/AskInterp.lean, Refine/RetryAsk.lean). It holds formal/refine's
# link to formal/veil (../veil-link.sh), builds the two files from their sources, audits every theorem of their
# namespace (what it rests on), and compares the theorems' statements and the definitions with the recorded ones.
# `lake` and `lean` are the ones on PATH; it runs under the caller's limits.
#
#   bash formal/refine/checks/asking/check.sh              # check, and compare with the record
#   bash formal/refine/checks/asking/check.sh --update     # adopt the statements, after an intended change:
#                                                          #   never a pass; run it again without --update
#   bash formal/refine/checks/asking/check.sh --out DIR    # write the outputs to DIR (the controls do)
#
# The outputs: check.txt (this run), audit.txt (each theorem, its axioms; every statement and definition). The
# reference, beside this script: statements.txt (the recorded statements and definitions).
#
# It prints "check.sh: PASS" and exits 0 only if: the sources and the reference are HEAD's; formal/refine/Refine
# holds the five known files (../twinstep's three and these two) and no other; the lakefile's roots name these two;
# the link to formal/veil holds and Veil's checkout is the manifest's; the build passes with no warning and leaves
# the manifest as it was; no file of Refine/ has `sorry` or `admit`; every theorem rests on allowed axioms only, and no other axiom
# is declared; and every statement and definition is the recorded one.
#
# What it does not check: that a statement means what its docstring says; a declaration outside the namespace
# Refine.Ask (the other three files' are ../twinstep/check.sh's; the twin's are not in the record: this check
# prints formal/twin's tree and pins nothing of it but that it is HEAD's). What a printed statement or definition hides is covered by its fingerprint (Audit.lean).
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
SRC="Refine/AskInterp.lean Refine/RetryAsk.lean"
ALL="Refine/AskInterp.lean Refine/Controls.lean Refine/PromiseDue.lean Refine/RetryAsk.lean Refine/TwinStep.lean"
T=formal/refine/checks/asking
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
  # 2. coverage: Refine/ holds the five known files, and no other (a file added later is in no list of this check,
  #    and must fail it until it is); the lakefile's roots name this check's two
  have=$(ls Refine/*.lean | sort | tr '\n' ' ')
  if [ "$have" = "$ALL " ]; then echo "files: Refine/ holds the five known ones"; else echo "files: Refine/ holds [$have], not [$ALL ]"; fail="$fail files"; fi
  if grep -q '`Refine.AskInterp' lakefile.lean && grep -q '`Refine.RetryAsk' lakefile.lean; then
    echo "roots: the lakefile names Refine.AskInterp and Refine.RetryAsk"
  else
    echo "roots: the lakefile does NOT name both"; fail="$fail roots"
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
  sha256sum $SRC
  # 4. the two files, built again from their sources, so that their warnings and errors are in this record
  rm -f .lake/build/lib/lean/Refine/AskInterp.olean .lake/build/lib/lean/Refine/RetryAsk.olean
  set +e
  lake build Refine.AskInterp Refine.RetryAsk 2>&1 | grep -v '^✔' > "$D/build.tmp"
  brc=${PIPESTATUS[0]}
  set -e
  cat "$D/build.tmp"
  echo "lake build rc=$brc"
  [ "$brc" = 0 ] || fail="$fail build"
  if grep -q -i 'warning\|error' "$D/build.tmp"; then echo "build: warnings or errors"; fail="$fail warnings"; else echo "build: no warning"; fi
  rm -f "$D/build.tmp"
  if cmp -s lake-manifest.json "$D/manifest.before"; then echo "the manifest: as before the build"
  else echo "the manifest: CHANGED by the build"; fail="$fail manifest"; fi
  rm -f "$D/manifest.before"
  n=$(cat Refine/*.lean | grep -c -w 'sorry\|admit' || true)
  echo "lines with sorry or admit in Refine/: $n"
  [ "$n" = 0 ] || fail="$fail sorry"
  # 5. every theorem of the namespace: its axioms; every statement and definition
  set +e
  lake env lean "$HERE/Audit.lean" > "$D/audit.txt" 2>&1
  arc=$?
  set -e
  echo "audit rc=$arc"
  [ "$arc" = 0 ] || fail="$fail audit-run"
  sed -n '/^theorem /,/^audit: /p' "$D/audit.txt" | grep -v '^audit: ' || true
  grep '^audit: ' "$D/audit.txt" || { echo "audit: no summary"; fail="$fail audit-summary"; }
  grep -q '^audit: [0-9]* theorems, [0-9]* definitions, [0-9]* axioms declared, 0 not allowed$' "$D/audit.txt" || fail="$fail axioms"
  # the theorems named here must be among the audited ones (a renamed or dropped one is not a pass)
  for t in retryFire_asks retryFire_refines_retryAsk retryFire_admitted_not_refused retryFire_refused_not_admitted \
           retryFire_refused_keeps retryFire_admitted_outstanding retryFire_refines_applies \
           retryFire_refines_applies_refused retryFire_refines_applies_fourth retryFire_refines_applies_later \
           retryFire_other_chunk_same retryFire_asks_is_next_for retryFire_held retryFire_held_same \
           retryFire_held_last_retryNoop retryFire_held_last_open_not_retryNoop retryFire_held_last_applies \
           threeAnn_after_facts retryFire_admitted_not_refused_applies retryFire_refused_not_admitted_applies; do
    grep -q "^theorem Refine.Ask.$t: ok " "$D/audit.txt" || { echo "audit: $t is not there, or not ok"; fail="$fail named"; }
  done
  # 6. the statements and definitions, against the record
  sed -n '/^statement /,$p' "$D/audit.txt" > "$D/statements.new"
  count() { echo "$(grep -c '^statement ' "$1") statements, $(grep -c "^axiom's statement " "$1") axioms', $(grep -c '^definition ' "$1") definitions, $(grep -c '^fingerprint ' "$1") fingerprints"; }
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
