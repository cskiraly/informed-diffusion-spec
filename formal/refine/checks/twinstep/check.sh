#!/bin/bash
# The check of the twin's step against the model's transition (Refine/TwinStep.lean, Refine/PromiseDue.lean,
# Refine/Controls.lean). It holds formal/refine's link to formal/veil (../veil-link.sh), builds the three files
# from their sources, audits every theorem of their namespace (what it rests on), compares the theorems'
# statements and the definitions with the recorded ones, and prints the generated definitions. `lake` and `lean`
# are the ones on PATH; it runs under the caller's limits.
#
#   bash formal/refine/checks/twinstep/check.sh              # check, and compare with the record
#   bash formal/refine/checks/twinstep/check.sh --update     # adopt the statements, after an intended change:
#                                                            #   never a pass; run it again without --update
#   bash formal/refine/checks/twinstep/check.sh --out DIR    # write the outputs to DIR (the controls do)
#
# The outputs: check.txt (this run), audit.txt (each theorem, its axioms; every statement and definition),
# generated.txt (Veil's definitions as printed). The reference, beside this script: statements.txt (the recorded
# statements and definitions).
#
# It prints "check.sh: PASS" and exits 0 only if: the sources and the reference are HEAD's; the link to formal/veil
# holds (the model's file is the cut of formal/veil's at its `#gen_spec` line, QuietRanking.lean is formal/veil's,
# the toolchains and the packages are the same); Veil's checkout is the manifest's; the build passes with no
# warning and leaves the manifest as it was; no source has `sorry` or `admit`; every theorem rests on allowed
# axioms only, and no other axiom is declared; and every statement and definition is the recorded one.
#
# What it does not check: that a statement means what its docstring says; a declaration outside the namespace Refine;
# what a printed statement hides (instance arguments).
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
SRC="Refine/TwinStep.lean Refine/PromiseDue.lean Refine/Controls.lean"
T=formal/refine/checks/twinstep
# what a run reads of the two packages, and never its own outputs (they lie beside this script)
PKG="formal/twin formal/refine/Refine formal/refine/Carry formal/refine/NoStallEquivModel.lean formal/refine/QuietRanking.lean formal/refine/lakefile.lean formal/refine/lake-manifest.json formal/refine/lean-toolchain formal/refine/checks/veil-link.sh"
fail=""
cd "$R"
{
  date '+start %F %T %Z'
  echo "commit $(git -C "$F" rev-parse --short=8 HEAD)"
  # 1. the sources are HEAD's, and so are the references this check compares with
  if git -C "$F" diff --quiet HEAD -- $PKG $T/Audit.lean $T/Printed.lean $T/check.sh \
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
  # 2. the link to formal/veil holds (the cut, QuietRanking, the toolchains, the manifest); Veil is the manifest's
  if bash "$HERE/../veil-link.sh"; then :; else fail="$fail veil-link"; fi
  cp lake-manifest.json "$D/manifest.before"
  want=$(python3 -c 'import json,sys; print([p["rev"] for p in json.load(open("lake-manifest.json"))["packages"] if p["name"] == "veil"][0])')
  got=$(git -C .lake/packages/veil rev-parse HEAD)
  if [ "$want" = "$got" ] && [ -z "$(git -C .lake/packages/veil status --porcelain)" ]; then
    echo "veil: the manifest's $want, clean"
  else
    echo "veil: checkout $got, manifest $want, or not clean"; fail="$fail veil"
  fi
  sha256sum $SRC
  # 3. the three files, built again from their sources, so that their warnings and errors are in this record
  rm -f .lake/build/lib/lean/Refine/TwinStep.olean .lake/build/lib/lean/Refine/PromiseDue.olean .lake/build/lib/lean/Refine/Controls.olean
  set +e
  lake build Refine.TwinStep Refine.PromiseDue Refine.Controls 2>&1 | grep -v '^✔' > "$D/build.tmp"
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
  n=$(cat $SRC | grep -c -w 'sorry\|admit' || true)
  echo "lines with sorry or admit in the three sources: $n"
  [ "$n" = 0 ] || fail="$fail sorry"
  # 4. every theorem of the namespace: its axioms; every statement and definition
  set +e
  lake env lean "$HERE/Audit.lean" > "$D/audit.txt" 2>&1
  arc=$?
  set -e
  echo "audit rc=$arc"
  [ "$arc" = 0 ] || fail="$fail audit-run"
  sed -n '/^theorem /,/^audit: /p' "$D/audit.txt" | grep -v '^audit: ' || true
  grep '^audit: ' "$D/audit.txt" || { echo "audit: no summary"; fail="$fail audit-summary"; }
  grep -q '^audit: [0-9]* theorems, [0-9]* definitions, [0-9]* axioms declared, 0 not allowed$' "$D/audit.txt" || fail="$fail axioms"
  # 5. the statements and definitions, against the record
  sed -n '/^statement /,$p' "$D/audit.txt" > "$D/statements.new"
  count() { echo "$(grep -c '^statement ' "$1") statements, $(grep -c "^axiom's statement " "$1") axioms', $(grep -c '^definition ' "$1") definitions"; }
  if [ "$UPDATE" = 1 ]; then
    cp "$D/statements.new" "$HERE/statements.txt"
    echo "statements: recorded now, not compared ($(count "$HERE/statements.txt"))"
  elif cmp -s "$D/statements.new" "$HERE/statements.txt"; then
    echo "statements: as recorded ($(count "$HERE/statements.txt"))"
  else
    echo "statements: DIFFER from the record"
    diff "$HERE/statements.txt" "$D/statements.new" | head -20 || true
    fail="$fail statements"
  fi
  rm -f "$D/statements.new"
  # 6. the generated definitions, as printed, and their counts
  set +e
  lake env lean "$HERE/Printed.lean" > "$D/generated.txt" 2>&1
  prc=$?
  set -e
  echo "printed rc=$prc"
  [ "$prc" = 0 ] || fail="$fail printed"
  python3 - "$D/generated.txt" <<'PY' || fail="$fail counts"
import re, sys
s = open(sys.argv[1]).read()
parts = re.split(r"\n(?=@\[reducible\] def |def )", s)
for p in parts:
    m = re.match(r"(?:@\[reducible\] )?def (\S+)", p)
    sig = p[:p.index(" :=")]                  # the type; the value's binders repeat its instances
    print(f"generated.txt: {m.group(1)}: {len(p)} characters as printed, {len(re.findall(r'Decidable(?!Eq)', sig))} Decidable instances in its type")
t = s[s.index("def NoStallEquiv.NextTr"):]
sig = t[:t.index(" :=")]
body = t[t.rindex("rd st label st' =>"):]
names = re.findall(r"\[(\w+_dec_\d+) :", sig)
print("generated.txt: NextTr's type takes", len(re.findall(r"Decidable(?!Eq)", sig)), "Decidable instances and",
      len(re.findall(r"DecidableEq", sig)), "DecidableEq; its body names", len(re.findall(r"\.ext\.tr\b", body)), "actions' ext.tr")
print("generated.txt: the Decidable instances:", " ".join(names))
PY
  echo "disk: .lake is $(du -sh .lake | cut -f1)"
  date '+end %F %T %Z'
  if [ -n "$fail" ]; then echo "check.sh: FAIL ($(echo $fail))"
  elif [ "$UPDATE" = 1 ]; then echo "check.sh: UPDATED the statements; not a pass: commit them and run it again"
  else echo "check.sh: PASS"; fi
} > "$OUT" 2>&1
tail -3 "$OUT"
[ -z "$fail" ]
