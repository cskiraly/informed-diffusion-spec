#!/bin/bash
# The controls of veil-link.sh: each a copy of formal/veil's and formal/refine's files with one change, which
# veil-link.sh must refuse with the words given; and the unchanged copy, which it must pass.
#
#   bash formal/refine/checks/veil-link-controls.sh [VEILDIR] [WORKDIR]
#
# VEILDIR is formal/veil (default: ../veil beside formal/refine). WORKDIR (default: a new temporary directory,
# removed at the end) gets the copies. Nothing is built: the files compared are a few. Exit 0 only if every
# control fails as it must and the unchanged copy passes.
set -u
HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
R=$HERE/..
V=${1:-$R/../veil}
W=${2:-}
own=
if [ -z "$W" ]; then W=$(mktemp -d) || exit 1; own=1; fi
bad=0; n=0
fresh() {                       # a copy of the files the link reads, in the spec's layout
  rm -rf "$W/c"; mkdir -p "$W/c/veil" "$W/c/refine" "$W/c/twin" || exit 1
  cp "$V/NoStallEquiv.lean" "$V/QuietRanking.lean" "$V/lean-toolchain" "$V/lake-manifest.json" "$W/c/veil/" || exit 1
  cp "$R/NoStallEquivModel.lean" "$R/QuietRanking.lean" "$R/lean-toolchain" "$R/lake-manifest.json" "$W/c/refine/" || exit 1
  cp "$R/../twin/lean-toolchain" "$W/c/twin/" || exit 1
}
control() {                     # control WHAT WORDS: the copy as changed must fail, with WORDS in the output
  n=$((n + 1))
  out=$(bash "$HERE/veil-link.sh" "$W/c/veil" "$W/c/refine" 2>&1); rc=$?
  if [ "$rc" = 1 ] && echo "$out" | grep -q -F -- "$2" && echo "$out" | grep -q -x 'veil-link: FAIL' \
     && ! echo "$out" | grep -q 'veil-link: PASS'; then
    echo "control $n, $1: refused, as it must be ($2)"
  else
    echo "control $n, $1: rc=$rc, and not refused with \"$2\"  <-- WRONG"; echo "$out" | sed 's/^/    /'; bad=$((bad + 1))
  fi
}
py() { python3 -I -S -B -c "$@" || exit 1; }

fresh
out=$(bash "$HERE/veil-link.sh" "$W/c/veil" "$W/c/refine" 2>&1); rc=$?
if [ "$rc" = 0 ] && [ "$(echo "$out" | tail -n 1)" = "veil-link: PASS" ]; then echo "the unchanged copy: passes"
else echo "the unchanged copy: rc=$rc  <-- WRONG"; echo "$out" | sed 's/^/    /'; bad=$((bad + 1)); fi

fresh; rm "$W/c/veil/NoStallEquiv.lean"
control "formal/veil's model is missing" "no such file, or a link"
fresh; echo '#gen_spec' >> "$W/c/veil/NoStallEquiv.lean"
control "a second #gen_spec line in formal/veil's model" "has 2 lines that hold #gen_spec"
fresh; echo '-- as #gen_spec does above' >> "$W/c/veil/NoStallEquiv.lean"
control "#gen_spec named again in a comment of formal/veil's model" "has 2 lines that hold #gen_spec"
fresh; sed -i 's/^#gen_spec$/#gen_spec  /' "$W/c/veil/NoStallEquiv.lean"
control "the #gen_spec line with blanks after it" "and 0 that are #gen_spec alone"
fresh; sed -i '1s/$/ /' "$W/c/veil/NoStallEquiv.lean"
control "a blank added to the first line of formal/veil's model" "NOT the cut"
fresh; sed -i '1s/$/ /' "$W/c/refine/NoStallEquivModel.lean"
control "a blank added to the first line of the cut" "NOT the cut"
fresh; echo '-- one line more' >> "$W/c/refine/NoStallEquivModel.lean"
control "a line added after the cut's closing line" "NOT the cut"
fresh; py 'import sys; p = sys.argv[1]; s = open(p).read().split("\n"); i = s.index("#gen_spec"); del s[i - 2]; open(p, "w").write("\n".join(s))' "$W/c/refine/NoStallEquivModel.lean"
control "a line taken out of the cut before #gen_spec" "NOT the cut"
fresh; py 'import sys; p = sys.argv[1]; s = open(p).read().split("\n"); i = s.index("#gen_spec"); s.insert(i + 1, "theorem extra : True := trivial"); open(p, "w").write("\n".join(s))' "$W/c/veil/NoStallEquiv.lean"
out=$(bash "$HERE/veil-link.sh" "$W/c/veil" "$W/c/refine" 2>&1); rc=$?     # what follows #gen_spec there is not the cut's
if [ "$rc" = 0 ] && [ "$(echo "$out" | tail -n 1)" = "veil-link: PASS" ]; then echo "a line added to formal/veil's model after #gen_spec: passes, as it must"
else echo "a line added to formal/veil's model after #gen_spec: rc=$rc  <-- WRONG"; bad=$((bad + 1)); fi
fresh; echo '-- a comment more' >> "$W/c/refine/QuietRanking.lean"
control "QuietRanking.lean with a line more" "QuietRanking.lean is NOT formal/veil's"
fresh; rm "$W/c/refine/QuietRanking.lean"
control "QuietRanking.lean missing" "no such file, or a link"
fresh; echo 'leanprover/lean4:v4.36.0' > "$W/c/twin/lean-toolchain"
control "formal/twin's toolchain another release" "lean-toolchain files are NOT the same"
fresh; echo 'leanprover/lean4:v4.36.0' > "$W/c/refine/lean-toolchain"
control "formal/refine's toolchain another release" "lean-toolchain files are NOT the same"
fresh; py 'import json, sys; p = sys.argv[1]; m = json.load(open(p)); q = [x for x in m["packages"] if x["name"] != "spectwin"][-1]; q["rev"] = "0" * 40; json.dump(m, open(p, "w"))' "$W/c/refine/lake-manifest.json"
control "a transitive package's revision changed in formal/refine's manifest" "differs in rev"
fresh; py 'import json, sys; p = sys.argv[1]; m = json.load(open(p)); q = [x for x in m["packages"] if x["name"] == "veil"][0]; q["rev"] = "0" * 40; json.dump(m, open(p, "w"))' "$W/c/veil/lake-manifest.json"
control "Veil's revision changed in formal/veil's manifest" "package veil differs in rev"
fresh; py 'import json, sys; p = sys.argv[1]; m = json.load(open(p)); m["packages"] = [x for x in m["packages"] if x["name"] != "spectwin"]; json.dump(m, open(p, "w"))' "$W/c/refine/lake-manifest.json"
control "spectwin taken out of formal/refine's manifest" "must have one package more"
fresh; py 'import json, sys; p = sys.argv[1]; m = json.load(open(p)); m["packages"].append({"name": "extra", "type": "git", "url": "https://example.org/x", "rev": "1" * 40}); json.dump(m, open(p, "w"))' "$W/c/refine/lake-manifest.json"
control "a package more in formal/refine's manifest" "must have one package more"
fresh; py 'import json, sys; p = sys.argv[1]; m = json.load(open(p)); m["packages"] = m["packages"][:-1]; json.dump(m, open(p, "w"))' "$W/c/veil/lake-manifest.json"
control "a package fewer in formal/veil's manifest" "must have one package more"
fresh; py 'import json, sys; p = sys.argv[1]; m = json.load(open(p)); [x for x in m["packages"] if x["name"] == "spectwin"][0]["dir"] = "../other"; json.dump(m, open(p, "w"))' "$W/c/refine/lake-manifest.json"
control "spectwin at another path" "must have one package more"
fresh; rm "$W/c/veil/lake-manifest.json"; ln -s "$W/c/refine/lake-manifest.json" "$W/c/veil/lake-manifest.json"
control "formal/veil's manifest a link" "no such file, or a link"

[ -z "$own" ] || rm -rf "$W"
echo "veil-link-controls: $((n - bad)) of $n controls refused as they must be$( [ "$bad" = 0 ] || echo "  <-- $bad WRONG")"
[ "$bad" = 0 ]
