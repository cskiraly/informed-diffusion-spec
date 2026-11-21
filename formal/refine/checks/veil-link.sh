#!/bin/bash
# formal/refine's link to formal/veil, held. Every check of formal/refine runs this first and stops if it fails.
#
#   bash formal/refine/checks/veil-link.sh [VEILDIR] [REFINEDIR]
#
# VEILDIR is formal/veil (default: ../veil beside formal/refine); REFINEDIR is formal/refine (default: this
# script's package; the controls give a changed copy).
#
# formal/refine does not import formal/veil's model. Veil closes a module at `#gen_spec`, and the proofs here need
# the model's generated definitions without the proofs that follow them there, which take a long build. So
# formal/refine holds two files that must be formal/veil's text:
#   NoStallEquivModel.lean   formal/veil/NoStallEquiv.lean up to and with its `#gen_spec` line, then an empty line
#                            and the line `end NoStallEquiv`
#   QuietRanking.lean        formal/veil/QuietRanking.lean, whole
# and it must be built with the same Lean and the same packages.
#
# It prints "veil-link: PASS" and exits 0 only if all of these hold; anything else is a failure, a missing file too:
#   1. formal/veil/NoStallEquiv.lean has exactly one line that holds `#gen_spec`, and that line is `#gen_spec` alone;
#   2. NoStallEquivModel.lean is the cut at that line, byte for byte;
#   3. QuietRanking.lean is formal/veil's, byte for byte;
#   4. the three lean-toolchain files (formal/veil, formal/refine, formal/twin) are the same;
#   5. every package of formal/veil's lake-manifest.json is in formal/refine's with every field the same (its
#      revision among them, the packages it brings in too), and formal/refine's has one more and no other:
#      `spectwin`, the path `../twin`.
set -u
HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
R=${2:-$HERE/..}
V=${1:-$R/../veil}
fail=
say() { echo "veil-link: $*"; }
no() { say "$*  <-- FAIL"; fail=1; }
for f in "$V/NoStallEquiv.lean" "$V/QuietRanking.lean" "$V/lean-toolchain" "$V/lake-manifest.json" \
         "$R/NoStallEquivModel.lean" "$R/QuietRanking.lean" "$R/lean-toolchain" "$R/lake-manifest.json" \
         "$R/../twin/lean-toolchain"; do
  [ -f "$f" ] && [ ! -L "$f" ] || no "no such file, or a link: $f"
done
if [ -z "$fail" ]; then
  # 1 and 2: the cut
  n=$(grep -c '#gen_spec' "$V/NoStallEquiv.lean")
  at=$(grep -n -x '#gen_spec' "$V/NoStallEquiv.lean" | cut -d: -f1)
  if [ "$n" != 1 ] || [ "$(echo "$at" | grep -c .)" != 1 ]; then
    no "formal/veil's NoStallEquiv.lean has $n lines that hold #gen_spec, and $(echo "$at" | grep -c .) that are #gen_spec alone: one of each is wanted"
  elif { head -n "$at" "$V/NoStallEquiv.lean" && echo && echo "end NoStallEquiv"; } | cmp -s - "$R/NoStallEquivModel.lean"; then
    say "NoStallEquivModel.lean is formal/veil's NoStallEquiv.lean to its #gen_spec line ($at), and the closing line"
  else
    no "NoStallEquivModel.lean is NOT the cut of formal/veil's NoStallEquiv.lean at its #gen_spec line ($at)"
  fi
  # 3
  if cmp -s "$V/QuietRanking.lean" "$R/QuietRanking.lean"; then say "QuietRanking.lean is formal/veil's"
  else no "QuietRanking.lean is NOT formal/veil's"; fi
  # 4
  if cmp -s "$V/lean-toolchain" "$R/lean-toolchain" && cmp -s "$V/lean-toolchain" "$R/../twin/lean-toolchain"; then
    say "the three lean-toolchain files are the same: $(head -n 1 "$V/lean-toolchain")"
  else no "the three lean-toolchain files are NOT the same"; fi
  # 5
  if m=$(python3 -I -S -B - "$V/lake-manifest.json" "$R/lake-manifest.json" <<'EOF'
import json
import sys

veil = json.load(open(sys.argv[1]))["packages"]
refine = json.load(open(sys.argv[2]))["packages"]
names = [p["name"] for p in refine]
if len(set(names)) != len(names) or len({p["name"] for p in veil}) != len(veil):
    sys.exit("a package is listed twice")
by = {p["name"]: p for p in refine}
for p in veil:
    q = by.get(p["name"])
    if q is None:
        sys.exit(f"formal/refine's manifest has no package {p['name']}")
    if q != p:
        d = sorted(k for k in set(p) | set(q) if p.get(k) != q.get(k))
        sys.exit(f"package {p['name']} differs in {', '.join(d)}: formal/veil has {[p.get(k) for k in d]}, "
                 f"formal/refine has {[q.get(k) for k in d]}")
more = [p for p in refine if p["name"] not in {x["name"] for x in veil}]
if len(more) != 1 or more[0].get("name") != "spectwin" or more[0].get("type") != "path" or more[0].get("dir") != "../twin":
    sys.exit(f"formal/refine's manifest must have one package more, spectwin at the path ../twin; it has "
             f"{[(p.get('name'), p.get('type'), p.get('dir', p.get('url'))) for p in more]}")
print(f"{len(veil)} packages as formal/veil's, field for field, and spectwin at ../twin")
EOF
  ); then say "the manifest: $m"; else no "the manifest: ${m:-it could not be compared}"; fi
fi
if [ -n "$fail" ]; then say "FAIL"; exit 1; fi
say "PASS"
