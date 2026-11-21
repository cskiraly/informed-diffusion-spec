#!/bin/bash
# The quick check of the twin: the twin built from nothing, small traces of the toy replayed through it, and the
# controls, which must fail but for a few of the content line's, which must pass. About ten minutes on eight
# cores.
#
#   bash formal/twin/check.sh [--toy DIR] [--out DIR] [-j N] [--steps a,b,...]
#   bash formal/twin/record.sh [the same options]     the record's run: this script with --record (below)
#
# --toy    the toy's directory (default: SPEC_TOY, or the repository's toy/)
# --out    where everything it makes goes (default: formal/twin/out/check; removed first)
# -j       how many traces, or how many compilations, at a time (default: 4)
# --steps  only these steps, in this order, on what earlier runs left in --out (a part is no pass: it says so)
# `lake`, `lean` and `python3` are the ones on PATH. It runs under the caller's limits and writes its output under
# --out; the self-tests of content.py and matrixdiff.py write fixtures to the system's temporary directory, and
# matrixdiff.py's are left there.
#   perturbed a tracer that perturbs what the toy reads (perturb3.py), on the cell `push`: another digest than
#             golden.txt's, or the digests of the cells show nothing
# It asks git nothing: a trace names what it was made from by its content line (tools/content.py), and every replay
# here is given the line of this tree, made once at the start and once more at the end, which must be the same.
#
# The steps, and what each must show:
#   build     a copy of the twin's sources, built from nothing with `lake build replay`; twin-sources.txt: each
#             source file of the twin, this script and record.sh by sha256 (a link among them is refused; a
#             file whose name ends in .md, prose, is left out of the list); the copy, listed the same way, is
#             that list, and at the end of the run the sources and the copy still are
#   selftests each tool's own cases (content.py, mutants3.py, altered3.py, commentsonly.py, fullid.py, against.py,
#             matrixdiff.py, and trace3.py's of the names protocol-v2.md keeps)
#   tables    the twin's generated files are the schema's (gen.py, makers.py); the views' own cases (footprint_test.py)
#   scope     every function protocol.md's code blocks define has its twin, by name: an `enter "NAME"` in SpecTwin/
#             and a case of the replay's for NAME; counted by section; a twin with one name taken away is refused
#   mutants   every mutant's text stands in the twin once (--places), and each type-checks alone against the build
#   screen    every cell's header and nodes line, under both documents, read by the replay; a nodes line without a
#             constant refused
#   cells     `none`, traced and replayed: its digest is golden.txt's (the tracer perturbs nothing)
#   small     hand5 (whole; §6.1's twelve alone; at PUBLISH), late16, and hand5 twice under protocol-v2.md: each
#             traced and replayed, its digest the untraced run's with the same arguments
#   directed  the 22 directed sets, traced and replayed
#   replays   every replay above read a trace that is not empty, to its trailer, with no record mismatched and no
#             read of the Python's left unmade
#   headers   every trace's first line is this tree's content line, and its header of the kind its name says
#             (header3.py); hashes.txt: each trace's two hashes (the whole, and from its second line on)
#   picks     the replay's pick of a replaced name's records, and a directed set's draw (fixcontrols.py)
#   controls  each must FAIL, for its reason, but for the content line's cases that must pass (below): a mutant
#             that compiles (one record or more mismatched); altered
#             records, wrong content lines, headers and malformed nodes lines (altered3.py); a trace cut short; a trace of another tree, and a tracer started so that what runs
#             need not be what its content line names (contentcontrols.py). A build error or a tree it cannot
#             read fails the control, never passes it.
#
# With --record (record.sh): the record's run, hours on a server. The same steps under the same contract, and:
#   cells     every cell of the toy's check.py, not `none` alone: each digest golden.txt's, each replayed
#   v2cells   every cell under protocol-v2.md: each digest golden-v2.txt's, each replayed (its records are of the
#             names that are protocol.md's all the way down); the tracer's self-test of those names
#   schemacontrols   the schema's and the makers' checks on planted changes: each must fail them
#   viewcontrols     22 broken views, each failing its own count of the views' cases, as written here; and
#             views_control's own controls: three stubs of the test that fail otherwise than its own failure (a
#             line after the verdict, a line on stderr, exit code 2) refused, the plain one taken
#   tracercontrols   a tracer whose views let an assignment through unlogged, and 16 faults planted in the tracer:
#             each must stop it, with its own words
#   seeds     the same bytes whatever Python's hash seed, which is random in every process of an isolated Python:
#             every directed set made again twice, two cells once (46 traces)
#   sizes     sizes.txt: each of the record's traces as the tracer wrote it: bytes, lines, the longest line; and
#             full-id-keys.txt: its records that hold a chunk's full id anywhere but where one stands by design
#             (fullid.py): none in a cell's trace under either document, where the nodes ask by index
#   manifest  record-manifest.txt: the content line's sha256, the Python and the platform, each document's file
#             sha256 (for provenance: the content line names the documents by their code), and the two hashes of
#             each of the record's 55 traces (15 cells, three hand traces, 22 directed sets, 15 v2 cells)
# The steps `replays`, `headers` and the hashes then cover the record's traces.
# With --against DIR too (a record: a directory with a run's record-manifest.txt and content.line), a last step:
#   against   the run's manifest against the record's (against.py): as recorded; or another content and the same
#             bodies, with the files that differ; or not the record's, which fails the run
#
# With --matrix K/N (record.sh --matrix K/N): the Kth of N parts of the mutants' matrix, hours on a server each.
# The twin is built, the 15 cells, the hand traces and the 22 directed sets are traced and replayed as in the
# record's run (no cell under protocol-v2.md: no mutant is replayed there), and then:
#   matrix    every Nth mutant from the Kth (mutants3.py --part), each built and replayed on the records that
#             reach its function or touch its table: first on the directed sets, where each must be told from
#             the twin; then on the 15 cells with hand5 and hand5-publish. In matrix/out: the two reports, a line
#             per mutant and trace for each (the pairs), the builds' hashes, and what ties a part to its traces
#             (the content line, the traces' two hashes, the replay's hash). `mutants3.py --merge OUT PART1 PART2 …`
#             reads the parts as one matrix and refuses parts that did not run the same content on the same traces.
# --cells "C1 C2 …" with --record: a rehearsal of the record's steps over these cells alone (or over none, with
# ""): every count is then of these, and its last line says it is no record.
# --sample drafts with it: a draft's run, never a matrix: every mutant of the part on the directed sets, and on the
# cells the drafts' sample alone (tools/sample_drafts.txt: each mutant with its reason; mutants3.py --sample-make,
# --sample-check); its part is marked (matrix/out/SAMPLE), and `mutants3.py --merge` refuses it.
# --rehearsal "M1 M2 …" with it: these mutants alone, on the hand traces and the directed sets alone (no cell):
# a trial of the step and of the merge (`mutants3.py --merge … --rehearsal M1,M2,…`), never a part of a matrix.
#
# It prints "check.sh: PASS" and exits 0 only if every step ran and showed what it must.
set -u
HERE=$(cd "$(dirname "$0")" && pwd) || exit 2
ROOT=$(cd "$HERE/../.." && pwd) || exit 2
T=$HERE/tools
TOY=${SPEC_TOY:-$ROOT/toy}
OUT=$HERE/out/check
J=4
ALL="build selftests tables scope mutants screen cells small directed replays headers picks controls perturbed"
RECORD_ALL="build selftests tables scope mutants screen cells v2cells small directed replays headers picks controls perturbed schemacontrols viewcontrols tracercontrols seeds sizes manifest"
MATRIX_ALL="build mutants cells small directed replays headers matrix"
RECORD=
PART=
REHEARSAL=
SAMPLE=
FEWCELLS=
CELLS_GIVEN=
AGAINST=
STEPS=
while [ $# -gt 0 ]; do
  case "$1" in
    --toy) TOY=$2; shift ;;
    --out) OUT=$2; shift ;;
    -j) J=$2; shift ;;
    --steps) STEPS=$(echo "$2" | tr ',' ' '); shift ;;
    --record) RECORD=1 ;;
    --matrix) RECORD=1; PART=$2; shift ;;
    --rehearsal) REHEARSAL=$2; shift ;;
    --sample) SAMPLE=$2; shift ;;
    --cells) FEWCELLS=yes; CELLS_GIVEN=$2; shift ;;
    --against) AGAINST=$2; shift ;;
    *) echo "usage: check.sh [--record | --matrix K/N [--rehearsal \"M1 M2 ...\"]] [--toy DIR] [--out DIR] [-j N] [--steps a,b,...]"; exit 2 ;;
  esac
  shift
done
TOY=$(cd "$TOY" 2> /dev/null && pwd) || { echo "check.sh: no toy at $TOY"; exit 2; }
[ -f "$TOY/run.py" ] || { echo "check.sh: no toy at $TOY (no run.py there)"; exit 2; }
export SPEC_TOY=$TOY
[ -z "$RECORD" ] || { ALL=$RECORD_ALL; [ "$OUT" != "$HERE/out/check" ] || OUT=$HERE/out/record; }
if [ -n "$AGAINST" ]; then
  [ -n "$RECORD" ] || { echo "check.sh: --against goes with --record"; exit 2; }
  AGAINST=$(cd "$AGAINST" 2> /dev/null && pwd) || { echo "check.sh: no record at the directory given with --against"; exit 2; }
  ALL="$ALL against"
fi
if [ -n "$PART" ]; then
  case "$PART" in [1-8]/[1-8]) ;; *) echo "check.sh: --matrix K/N, with N from 1 to 8 and K from 1 to N"; exit 2 ;; esac
  ALL=$MATRIX_ALL; [ "$OUT" != "$HERE/out/record" ] || OUT=$HERE/out/matrix-${PART%/*}-of-${PART#*/}
  [ -z "$REHEARSAL" ] || ALL="build small directed matrix"
  case "$SAMPLE" in ""|drafts) ;; *) echo "check.sh: --sample is drafts"; exit 2 ;; esac
elif [ -n "$REHEARSAL" ]; then echo "check.sh: --rehearsal goes with --matrix K/N"; exit 2
elif [ -n "$SAMPLE" ]; then echo "check.sh: --sample goes with --matrix K/N"; exit 2; fi
[ -n "$STEPS" ] || STEPS=$ALL
for s in $STEPS; do case " $ALL " in *" $s "*) ;; *) echo "check.sh: no step $s (the steps: $ALL)"; exit 2 ;; esac; done
if [ "$STEPS" = "$ALL" ]; then rm -rf "$OUT"; fi
mkdir -p "$OUT/traces" "$OUT/directed" "$OUT/v2" || exit 2
OUT=$(cd "$OUT" && pwd)
LOG=$OUT/check.txt
REPLAY=$OUT/twin/.lake/build/bin/replay
CONTENT=$OUT/content.line               # this tree's content line: what every replay here is given
case "$OUT" in *[[:space:]]*) echo "check.sh: --out has white space in its path: $OUT"; exit 2 ;; esac
# every Python here runs isolated (-I: no PYTHONPATH, no user site), with no site directory, writing no bytecode,
# and looking for bytecode under a directory that stays empty: the tracers refuse to start otherwise (trace3.py)
rm -rf "$OUT/pyc"; mkdir -p "$OUT/pyc" || exit 2
PY="python3 -I -S -B -X pycache_prefix=$OUT/pyc"
PYPLAIN="python3 -E -s -S -B"           # the toy run as its own program, untraced: its directory is on its path
fail=
no() { echo "  FAIL: $*"; fail="$fail $step"; }
has() { grep -q "$@"; }                 # has [-x|-E] PATTERN FILE

DIRS="directed directed44 directed44u directed42 directed4b directed7 directed7u directed1 directed6o directed64 directed64h directed46 directed43 directed41 directed46d directed3v directed52 directed53 directed54 directed7p directed71 directed51"
dirtool() {             # a directed set's tool, and its own options
  case $1 in
    directed) echo "directed3.py" ;; directed44u) echo "directed44.py --no-limits" ;;
    directed7) echo "directed7.py --cards on" ;; directed7u) echo "directed7.py --cards off" ;;
    directed7p) echo "directed7.py --source-offers publish" ;;
    *) echo "$1.py" ;;
  esac
}
HAND5="--nodes 5 --degree 4 --msgs 1 --payload 16384 --seed 7"
LATE16="--nodes 16 --degree 8 --msgs 2 --seed 7 --late-block 30,400"
CELLS="announce cap-wait dcb20 hold ihave-limits late-block loss-thin none push push-deep rr-stripe silent withholders without-a without-b"
if [ -n "$FEWCELLS" ]; then
  [ -n "$RECORD" ] && [ -z "$PART" ] || { echo "check.sh: --cells goes with --record"; exit 2; }
  for c in $CELLS_GIVEN; do case " $CELLS " in *" $c "*) ;; *) echo "check.sh: no cell $c"; exit 2 ;; esac; done
  CELLS=$CELLS_GIVEN
fi
SEEDCELLS=$(for c in withholders loss-thin; do case " $CELLS " in *" $c "*) echo "$c" ;; esac; done)   # traced twice
SMALL="traces/late16 v2/hand5 v2/hand5-own"         # the check's small traces that are not the record's
if [ -z "$RECORD" ]; then
  TRACES="traces/none traces/hand5 traces/hand5-sec61 traces/late16 traces/hand5-publish v2/hand5 v2/hand5-own $(for d in $DIRS; do echo "directed/$d"; done)"
elif [ -n "$PART" ]; then       # a matrix part: the record's traces but the cells under protocol-v2.md
  RTRACES="$(for c in $CELLS; do echo "traces/$c"; done) traces/hand5 traces/hand5-sec61 traces/hand5-publish $(for d in $DIRS; do echo "directed/$d"; done)"
  TRACES="$RTRACES $SMALL"
else                    # the record's 55, then the three small ones
  RTRACES="$(for c in $CELLS; do echo "traces/$c"; done) traces/hand5 traces/hand5-sec61 traces/hand5-publish $(for d in $DIRS; do echo "directed/$d"; done) $(for c in $CELLS; do echo "v2/$c"; done)"
  TRACES="$RTRACES $SMALL"
fi

replay_of() {           # $1: a trace, without its .jsonl.gz: replayed to $1.replay; the status is the replay's
  zcat "$OUT/$1.jsonl.gz" | "$REPLAY" --content "$CONTENT" > "$OUT/$1.replay" 2>&1
  return "${PIPESTATUS[1]}"
}
digest_of() { sed -n '/^digest /{s/^digest \(.\{16\}\).*/\1/p;q}' "$1"; }
PIDS=
par() {                 # "$@" in the background, at most J such at a time
  while [ "$(jobs -rp | wc -l)" -ge "$J" ]; do wait -n; done
  "$@" &
  PIDS="$PIDS $!"
}
par_end() { local p rc=0; for p in $PIDS; do wait "$p" || rc=1; done; PIDS=; return $rc; }

twin_list() {           # $1: a directory with the twin's sources: "sha256  name" for each, sorted; a link is refused
  $PY - "$HERE" "$1" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import content, layout
from pathlib import Path
top, out = Path(sys.argv[2]), {}
try:
    for e in sorted(top.iterdir()):
        if e.name in layout.NOT_SOURCES or e.name == "out":
            continue
        if e.is_symlink():
            raise content.Refused(f"a link: {e.name}")
        if e.is_dir():
            out.update(content.walk(e, e.name))     # which leaves out a file whose name ends in .md, as below
        elif e.name.endswith(".md"):
            continue                                # prose (README.md), by its name, left out of the list
        else:
            import hashlib
            out[e.name] = hashlib.sha256(e.read_bytes()).hexdigest()
except content.Refused as x:
    sys.exit(f"the twin's sources: refused: {x}")
for n in sorted(out):
    print(f"{out[n]}  {n}")
EOF
}
s_build() {
  rm -rf "$OUT/twin"
  twin_list "$HERE" > "$OUT/twin-sources.txt" 2> "$OUT/twin-sources.err" || { no "the twin's sources could not be listed (twin-sources.err)"; return; }
  $PY - "$HERE" "$OUT/twin" <<'EOF' || { no "the twin's sources could not be copied"; return; }
import shutil, sys
sys.path.insert(0, sys.argv[1] + "/tools")
import layout
shutil.copytree(sys.argv[1], sys.argv[2], ignore=shutil.ignore_patterns(*layout.NOT_SOURCES, "out"))
EOF
  echo "  $(lean --version 2>&1 | head -n 1)"
  (cd "$OUT/twin" && lake build replay) > "$OUT/build.txt" 2>&1 || { grep -v '^✔' "$OUT/build.txt" | head -n 40; no "the build failed"; return; }
  [ -x "$REPLAY" ] || { no "the build left no replay"; return; }
  twin_list "$OUT/twin" 2> /dev/null | cmp -s - "$OUT/twin-sources.txt" || { no "the copy that was built is not the twin's sources as listed"; return; }
  echo "  the twin's sources: $(wc -l < "$OUT/twin-sources.txt") files, the list's sha256 $(sha256sum < "$OUT/twin-sources.txt" | cut -c1-64) (twin-sources.txt)"
  echo "  the replay: sha256 $(sha256sum < "$REPLAY" | cut -c1-64)"
}
s_selftests() {         # each tool's own cases: exit code 0, its own closing line, and (altered3.py's, which closes with no verdict) no case marked `<-- must be`
  local t n=0
  : > "$OUT/selftests.txt"
  while read -r t opt last; do
    if $PY "$T/$t" "$opt" > "$OUT/selftest.out" 2>&1 && tail -n 1 "$OUT/selftest.out" | grep -q -E -e "$last" && ! grep -q -e '<-- must be ' "$OUT/selftest.out"; then
      echo "$t $opt: $(tail -n 1 "$OUT/selftest.out" | cut -c1-120)" >> "$OUT/selftests.txt"; n=$((n + 1))
    else echo "$t $opt: NOT as it must be: $(tail -n 1 "$OUT/selftest.out" | cut -c1-160)" >> "$OUT/selftests.txt"; no "the self-test of $t (selftests.txt)"; fi
  done <<'EOF_SELF'
content.py --self-test ^content self-test: every case as it must be$
mutants3.py --self-test ^ok: every case of the table check as it must be$
altered3.py --self-test ^altered3 self-test, .*$
commentsonly.py --self-test ^self-test: ([0-9]+) of \1 known answers
fullid.py --self-test ^ok: every case as it must be$
against.py --self-test ^ok: every case as it must be$
matrixdiff.py --self-test ^ok: every case as it must be$
trace3.py --self-test-v2 ^ok: 
EOF_SELF
  rm -f "$OUT/selftest.out"
  [ "$n" = 8 ] || no "not 8 tools' self-tests passed"
  echo "  $n of 8 tools' own cases as they must be (selftests.txt)"
}
s_tables() {
  { $PY "$T/gen/gen.py" --check "$OUT/twin" && $PY "$T/gen/makers.py" --check "$OUT/twin"; } > "$OUT/tables.txt" 2>&1 \
    || no "a generated file is not the schema's, or a Tables value is made elsewhere (tables.txt)"
  tail -n 1 "$OUT/tables.txt" | sed 's/^/  /'
  $PY "$T/footprint_test.py" > "$OUT/views.txt" 2>&1 || no "the views' own cases (views.txt)"
  tail -n 1 "$OUT/views.txt" | sed 's/^/  /'
}
s_scope() {             # the twin's scope held to the document: every `def` of protocol.md's code blocks, by name
  $PY - "$(dirname "$TOY")/protocol.md" "$HERE/SpecTwin" > "$OUT/scope.txt" 2>&1 <<'EOF'
import ast, re, sys
from collections import Counter
from pathlib import Path
doc, twin = Path(sys.argv[1]), Path(sys.argv[2])
defs, sec, block = [], None, None             # (name, section) of every top-level def, in the document's order
for line in doc.read_text().split("\n"):
    if block is None:
        m = re.match(r"#{2,3} (\d+(?:\.\d+)?)[. ]", line)
        if m:
            sec = m.group(1)
        if line.strip() == "```python":
            block = []
    elif line.strip() == "```":
        defs += [(n.name, sec) for n in ast.parse("\n".join(block)).body if isinstance(n, ast.FunctionDef)]
        block = None
    else:
        block.append(line)
entered = set()
for f in sorted(twin.glob("*.lean")):
    entered |= set(re.findall(r'enter "([A-Za-z_0-9]+)"', f.read_text()))
cases = set(re.findall(r'^\s*\| "([A-Za-z_0-9]+)", #\[', (twin / "Replay.lean").read_text(), re.M))

def missing(entered, cases):
    return [f"{n} (§{s}): {'no enter' if n not in entered else 'no case of the replay'}"
            for n, s in defs if n not in entered or n not in cases]
names = [n for n, _ in defs]
bad = missing(entered, cases)
if not defs or len(set(names)) != len(names):
    bad.append(f"the document's defs cannot be read as {len(names)} distinct names")
for b in bad:
    print(f"without its twin: {b}")
by = Counter(s for _, s in defs)
order = sorted(by, key=lambda s: [int(x) for x in s.split(".")])
print("by section: " + ", ".join(f"§{s} {by[s]}" for s in order))
more = sorted(entered & cases - set(names))
print(f"the twin's functions with no def in the code blocks: {', '.join(more) or 'none'}")
gone = names[0]                              # the control: a twin with one name taken away must be refused
ctl = missing(entered - {gone}, cases)
print(f"control, the twin without {gone}: {'refused, as it must be' if ctl and gone in ctl[0] else 'NOT refused  <-- FAIL'}")
if bad or not ctl:
    print(f"NOT every function of protocol.md's code blocks has its twin: {len(bad)} without")
    sys.exit(1)
print(f"{len(names)} of {len(names)} functions of protocol.md's code blocks have their twin, by name")
EOF
  [ $? = 0 ] || no "a function of protocol.md's code blocks without its twin, or the scope's control (scope.txt)"
  sed 's/^/  /' "$OUT/scope.txt"
}
s_mutants() {
  $PY "$T/mutants3.py" --places --twin "$OUT/twin" > "$OUT/mutants-places.txt" 2>&1 || no "a mutant's text does not stand in the twin (mutants-places.txt)"
  tail -n 1 "$OUT/mutants-places.txt" | sed 's/^/  /'
  $PY "$T/mutants3.py" --typecheck "$OUT/twin" "$OUT/typecheck" -j "$J" > "$OUT/mutants-typecheck.txt" 2>&1 || no "a mutant does not type-check (mutants-typecheck.txt)"
  has -x "control, a change that does not type-check: rc=1: it fails, as it must" "$OUT/mutants-typecheck.txt" || no "the type-check's own control"
  tail -n 2 "$OUT/mutants-typecheck.txt" | sed 's/^/  /'
}
s_screen() {
  local f doc
  for doc in v03 v2; do
    f=$OUT/nodeslines-$doc.txt
    $PY "$T/cells3.py" "$TOY" "$OUT/nodeslines-$doc" -j "$J" --replay "$REPLAY" --doc "$doc" --nodes-lines > "$f" 2>&1 || no "a header or a nodes line refused under $doc ($f)"
    has -x ok "$f" || no "no verdict under $doc"
    [ "$(grep -c ': its header and nodes line read by the replay$' "$f")" = 15 ] || no "not 15 cells read under $doc"
    has -x "control, a nodes line without PROMISE: refused, and seen" "$f" || no "the nodes line's control under $doc"
    echo "  $doc: $(grep -c ': its header and nodes line read by the replay$' "$f") cells' header and nodes line read; $(grep '^control' "$f")"
  done
}
s_cells() {
  if [ -z "$RECORD" ]; then
    $PY "$T/cells3.py" "$TOY" "$OUT/traces" -j 1 --replay "$REPLAY" none > "$OUT/cells.txt" 2>&1 || no "none (cells.txt)"
    has -x ok "$OUT/cells.txt" || no "no verdict on none"
    head -n 1 "$OUT/cells.txt" | cut -c1-200 | sed 's/^/  /'
  else                  # every cell of check.py: its digest golden.txt's, its first two lines, its replay
    if [ -z "$CELLS" ]; then echo "  no cell (a rehearsal)"; echo ok > "$OUT/cells.txt"; return; fi
    # shellcheck disable=SC2086
    $PY "$T/cells3.py" "$TOY" "$OUT/traces" -j "$J" --replay "$REPLAY" $CELLS > "$OUT/cells.txt" 2>&1 || no "a cell (cells.txt)"
    has -x ok "$OUT/cells.txt" || no "no verdict on the cells"
    [ "$(grep -c ', digest as golden.txt, ' "$OUT/cells.txt")" = "$(echo $CELLS | wc -w)" ] || no "not every cell's digest is golden.txt's"
    [ "$(grep -c . "$OUT/cells.txt")" = "$(( $(echo $CELLS | wc -w) + 1 ))" ] || no "cells.txt is not a line a cell and the verdict (check.py's cells are not this script's CELLS)"
    echo "  $(grep -c ', digest as golden.txt, ' "$OUT/cells.txt") of $(echo $CELLS | wc -w) cells: digest as golden.txt, replayed (cells.txt)"
  fi
}
s_v2cells() {            # every cell under protocol-v2.md: its digest golden-v2.txt's; the records are protocol.md's names
  $PY "$T/trace3.py" --self-test-v2 > "$OUT/v2-self-test.txt" 2>&1 || no "the tracer's self-test of v2's kept names (v2-self-test.txt)"
  if [ -z "$CELLS" ]; then echo "  no v2 cell (a rehearsal)"; echo ok > "$OUT/cells-v2.txt"; return; fi
  # shellcheck disable=SC2086
  $PY "$T/cells3.py" "$TOY" "$OUT/v2" -j "$J" --doc v2 --replay "$REPLAY" $CELLS > "$OUT/cells-v2.txt" 2>&1 || no "a v2 cell (cells-v2.txt)"
  has -x ok "$OUT/cells-v2.txt" || no "no verdict on the v2 cells"
  [ "$(grep -c ', digest as golden-v2.txt, ' "$OUT/cells-v2.txt")" = "$(echo $CELLS | wc -w)" ] || no "not every v2 cell's digest is golden-v2.txt's"
  echo "  $(grep -c ', digest as golden-v2.txt, ' "$OUT/cells-v2.txt") of $(echo $CELLS | wc -w) v2 cells: digest as golden-v2.txt, replayed (cells-v2.txt)"
}
small() {               # $1: a name; $2: its directory; $3: the tracer's environment setting, or ""; the rest: run.py's arguments
  local name=$1 dir=$2 setting=$3 got plain; shift 3
  rm -f "$OUT/$dir/$name.jsonl.gz" "$OUT/$dir/$name.replay"
  (cd "$TOY" && env $setting $PY "$T/trace3.py" . "$OUT/$dir/$name.jsonl.gz" "$@" --digest > "$OUT/$dir/$name.out" 2> "$OUT/$dir/$name.err") || return 1
  replay_of "$dir/$name"
  (cd "$TOY" && $PYPLAIN run.py "$@" --digest > "$OUT/$dir/$name.plain" 2>&1)
  got=$(digest_of "$OUT/$dir/$name.out"); plain=$(digest_of "$OUT/$dir/$name.plain")
  echo "$dir/$name: digest traced ${got:-none}, untraced ${plain:-none}: $([ -n "$got" ] && [ "$got" = "$plain" ] && echo the same || echo DIFFERENT)" > "$OUT/$dir/$name.digest"
  [ -n "$got" ] && [ "$got" = "$plain" ]
}
s_small() {
  # shellcheck disable=SC2086
  { par small hand5 traces "" $HAND5
    par small hand5-sec61 traces TRACE3_ONLY=sec61 $HAND5
    par small late16 traces "" $LATE16
    par small hand5-publish traces "" $HAND5 --source-offers publish
    par small hand5 v2 "" $HAND5 --doc v2
    par small hand5-own v2 "" $HAND5 --rebuilt none --fault sil30 --doc v2; }
  par_end || no "a small cell was not traced, or its digest is not the untraced run's"
  cat "$OUT"/traces/*.digest "$OUT"/v2/*.digest 2> /dev/null | tee "$OUT/digests.txt" | sed 's/^/  /'
  [ "$(grep -c ': the same$' "$OUT/digests.txt")" = 6 ] || no "not six digests the same"
}
one_directed() {
  local d=$1 tool
  tool=$(dirtool "$d")
  rm -f "$OUT/directed/$d.jsonl.gz" "$OUT/directed/$d.replay"
  # shellcheck disable=SC2046
  (cd "$TOY" && $PY "$T/${tool%% *}" . "$OUT/directed/$d.jsonl.gz" --n 20000 --seed 1 $(case "$tool" in *" "*) echo "${tool#* }" ;; esac) \
      > "$OUT/directed/$d.out" 2> "$OUT/directed/$d.err") || return 1
  replay_of "directed/$d"
}
s_directed() {
  local d
  for d in $DIRS; do par one_directed "$d"; done
  par_end || no "a directed set was not traced, or its replay did not end with status 0"
  echo "  $(ls "$OUT"/directed/*.jsonl.gz 2> /dev/null | wc -l) of 22 directed sets traced"
}
s_replays() {
  local t f n=0
  : > "$OUT/replays.txt"
  for t in $TRACES; do
    f=$OUT/$t.replay
    if [ ! -s "$f" ]; then echo "$t: no replay" >> "$OUT/replays.txt"; no "$t has no replay"; continue; fi
    echo "$t: $(grep '^replay: ' "$f" | head -n 1); $(grep "^reads of the Python's that the twin did not make: " "$f" | head -n 1)" >> "$OUT/replays.txt"
    has -E '^replay: [1-9][0-9]* records, [1-9][0-9]* ok, 0 mismatched$' "$f" || { no "$t: a record mismatched, or none read"; continue; }
    has -x "reads of the Python's that the twin did not make: 0" "$f" || { no "$t: a read of the Python's not made"; continue; }
    has -E "^content: as --content's, [0-9]+ names\$" "$f" || { no "$t: its content line was not compared, or is not this tree's"; continue; }
    if grep -E '^(content|header|nodes|trailer|consts|subset): ' "$f" | grep -v -e '^header: {' -e "^content: as --content's, " | grep -q .; then no "$t: the replay refused a line of the envelope"; continue; fi
    n=$((n + 1))
  done
  echo "  $n of $(echo $TRACES | wc -w) replays: every record of a trace that is not empty, none mismatched, no read left unmade (replays.txt)"
}
s_headers() {
  # shellcheck disable=SC2046
  $PY "$T/header3.py" "$TOY" $(for t in $TRACES; do echo "$OUT/$t.jsonl.gz"; done) > "$OUT/headers.txt" 2>&1 || no "a header is not these tools' and these documents' (headers.txt)"
  [ "$(grep -c "tracing §6.1's 12 alone\$" "$OUT/headers.txt")" = 1 ] && has -E "/hand5-sec61\.jsonl\.gz: .*tracing §6.1's 12 alone\$" "$OUT/headers.txt" \
    || no "hand5-sec61 alone must be of §6.1's twelve"
  [ "$(grep -c -E "/v2/hand5(-own)?\.jsonl\.gz: .*tracing v2's kept, " "$OUT/headers.txt")" = 2 ] || no "the two small v2 traces must be of v2's kept names"
  [ "$(grep -c -E "/v2/[a-z0-9-]+\.jsonl\.gz: .*tracing v2's kept, " "$OUT/headers.txt")" = "$(grep -c -E '/v2/[a-z0-9-]+\.jsonl\.gz: ' "$OUT/headers.txt")" ] || no "a v2 trace is not of v2's kept names"
  echo "  $(grep -c . "$OUT/headers.txt") headers read (headers.txt)"
  # each trace's two hashes, by its name under --out: two runs of one tree, on any machine, give the same file
  # shellcheck disable=SC2046
  (cd "$OUT" && $PY "$T/content.py" --hashes $(for t in $TRACES; do echo "$t.jsonl.gz"; done) > hashes.txt 2> hashes.err) || no "a trace's hashes (hashes.err)"
  echo "  hashes.txt: $(wc -l < "$OUT/hashes.txt") traces, the file's sha256 $(sha256sum < "$OUT/hashes.txt" | cut -c1-64)"
}
s_picks() {
  { $PY "$T/fixcontrols.py" pick "$REPLAY" "$CONTENT" "$OUT/directed/directed42.jsonl.gz" validate_chunk
    $PY "$T/fixcontrols.py" pick "$REPLAY" "$CONTENT" "$OUT/directed/directed41.jsonl.gz" on_iwant
    $PY "$T/fixcontrols.py" pick "$REPLAY" "$CONTENT" "$OUT/directed/directed46d.jsonl.gz" push_rebuilt
    $PY "$T/fixcontrols.py" draw "$OUT/directed/directed3v.jsonl.gz"; } > "$OUT/picks.txt" 2>&1 || no "a pick or the draw (picks.txt)"
  [ "$(grep -c . "$OUT/picks.txt")" = 4 ] || no "not four lines in picks.txt"
  sed 's/^/  /' "$OUT/picks.txt" | cut -c1-200
}
s_controls() {
  local rc
  # 1. a mutant that compiles, replayed over §6.1's directed set: it must be built, and told by a mismatched record
  rm -rf "$OUT/c-mutant"; mkdir -p "$OUT/c-mutant/traces"
  cp "$OUT/directed/directed.jsonl.gz" "$OUT/c-mutant/traces/" 2> /dev/null
  $PY "$T/mutants3.py" "$OUT/c-mutant/traces" "$OUT/c-mutant/work" -j 1 --twin "$OUT/twin" window-le > "$OUT/c-mutant.txt" 2>&1; rc=$?
  if [ "$rc" = 0 ] && has -E '^1 of 1 mutants told from the twin by these traces' "$OUT/c-mutant.txt" && ! has 'no verdict' "$OUT/c-mutant.txt"; then
    echo "  control, a mutant that compiles (window-le): told, as it must be: $(grep -m 1 '^window-le: ' "$OUT/c-mutant.txt" | cut -c1-150)"
  else no "control, a mutant that compiles: rc=$rc, not told by a mismatched record (c-mutant.txt)"; fi
  # 2. altered records, wrong headers, malformed nodes lines: every one refused (altered3.py's own table)
  #    (the traces in the order altered3.py takes them: each group of its controls is of one set's records)
  # shellcheck disable=SC2046
  SPEC_TWIN_REPLAY=$REPLAY $PY "$T/altered3.py" "$OUT/traces/hand5-sec61.jsonl.gz" "$OUT/c-altered" "$OUT/directed/directed.jsonl.gz" "$OUT/traces/hand5.jsonl.gz" \
      "$OUT/directed/directed44.jsonl.gz" "$OUT/directed/directed42.jsonl.gz" "$OUT/v2/hand5.jsonl.gz" \
      $(for d in directed4b directed7 directed1 directed6o directed64 directed64h directed46 directed43 directed41 directed46d directed3v directed52 directed53 directed54 directed7p; do echo "$OUT/directed/$d.jsonl.gz"; done) \
      "$OUT/traces/hand5-publish.jsonl.gz" "$OUT/directed/directed71.jsonl.gz" "$OUT/directed/directed51.jsonl.gz" > "$OUT/c-altered.txt" 2>&1; rc=$?
  if [ "$rc" = 0 ] && ! has -E 'wrong$|<-- ' "$OUT/c-altered.txt" && [ "$(grep -c '^ok: every control of ' "$OUT/c-altered.txt")" -ge 1 ]; then
    echo "  control, altered records, headers and nodes lines: $(grep -c '^ok: every control of ' "$OUT/c-altered.txt") groups, each refused as it must be (c-altered.txt)"
  else no "control, altered records: rc=$rc (c-altered.txt)"; fi
  # 3. a trace cut short: no trailer, so no pass
  zcat "$OUT/traces/hand5.jsonl.gz" | head -n 50 | "$REPLAY" --content "$CONTENT" > "$OUT/c-cut.replay" 2>&1; rc=${PIPESTATUS[2]}
  if [ "$rc" = 1 ] && has -E '^trailer: ' "$OUT/c-cut.replay"; then echo "  control, a trace cut short: refused, as it must be: $(grep -m 1 '^trailer: ' "$OUT/c-cut.replay" | cut -c1-120)"
  else no "control, a trace cut short: rc=$rc, and no line about the trailer"; fi
  # 4. the content line: a trace of another tree refused, the same tree at another place the same bytes, edits of
  #    prose and READMEs leaving the line as it was, and a tracer started so that what runs need not be what the
  #    line names refused (contentcontrols.py's own table)
  $PY "$T/contentcontrols.py" "$TOY" "$OUT/c-content" "$REPLAY" "$OUT/traces/hand5-sec61.jsonl.gz" > "$OUT/c-content.txt" 2>&1; rc=$?
  if [ "$rc" = 0 ] && ! has '<-- ' "$OUT/c-content.txt" && has -x "ok: every control of the content line as it must be" "$OUT/c-content.txt"; then
    echo "  control, the content line: $(grep -c '^content, ' "$OUT/c-content.txt") cases, each as it must be (c-content.txt)"
  else no "control, the content line: rc=$rc (c-content.txt)"; fi
}

VIEWS_TEST=          # the views' test views_control runs: footprint_test.py, or a stub of its own controls
VIEWS_REPORT=        # where views_control writes its line: views-controls.txt, or its own controls' file
views_control() {       # $1: footprint_test.py's option; $2: what is broken; $3: how many cases it must fail
  local f=$OUT/views$1.txt n rc=0 test=${VIEWS_TEST:-$T/footprint_test.py} rep=${VIEWS_REPORT:-$OUT/views-controls.txt}
  $PY "$test" "$1" > "$f" 2> "$f.err" || rc=$?
  n=$(grep -c -F 'FAIL' "$f")
  if [ "$rc" = 1 ] && [ ! -s "$f.err" ] && [ "$(tail -n 1 "$f")" = "footprint_test: a case is NOT as the contract says" ] && [ "$n" = "$3" ]; then
    echo "control, views that $2: $n cases fail, as they must" >> "$rep"
  else
    echo "control, views that $2: rc=$rc, $n cases fail (it must be $3 and the test's own verdict)  <-- NOT" >> "$rep"; return 1
  fi
}
views_control_controls() {      # views_control itself, on three stubs of the test that fail otherwise than its own
  local kind ok=0                #   failure: each must be refused, though each prints the count and the verdict
  mkdir -p "$OUT/views-stubs"; : > "$OUT/views-stubs.txt"
  for kind in line-after stderr exit2; do
    cat > "$OUT/views-stubs/$kind.py" <<EOF_STUB
import sys
print("case, one: NOT  <-- FAIL")
print("case, two: NOT  <-- FAIL")
print("footprint_test: a case is NOT as the contract says")
kind = "$kind"
if kind == "line-after":
    print("one line more, after the verdict")
if kind == "stderr":
    print("a line on stderr", file=sys.stderr)
sys.exit(2 if kind == "exit2" else 1)
EOF_STUB
    if VIEWS_TEST=$OUT/views-stubs/$kind.py VIEWS_REPORT=$OUT/views-stubs.txt views_control "--stub-$kind" "fail otherwise ($kind)" 2; then
      echo "a stub that fails otherwise ($kind): taken  <-- it must be refused" >> "$OUT/views-stubs.txt"
    else ok=$((ok + 1)); echo "a stub that fails otherwise ($kind): refused, as it must be" >> "$OUT/views-stubs.txt"; fi
  done
  # and the stub's form passes where it fails as the test does, so a refusal above is for its one difference
  cat > "$OUT/views-stubs/plain.py" <<'EOF_STUB'
import sys
print("case, one: NOT  <-- FAIL")
print("case, two: NOT  <-- FAIL")
print("footprint_test: a case is NOT as the contract says")
sys.exit(1)
EOF_STUB
  if VIEWS_TEST=$OUT/views-stubs/plain.py VIEWS_REPORT=$OUT/views-stubs.txt views_control "--stub-plain" "fail as the test does" 2; then
    ok=$((ok + 1)); echo "the stub that fails as the test does: taken, as it must be" >> "$OUT/views-stubs.txt"
  else echo "the stub that fails as the test does: refused  <-- it must be taken" >> "$OUT/views-stubs.txt"; fi
  [ "$ok" = 4 ] || no "views_control's own controls (views-stubs.txt)"
  echo "  views_control's own controls: $ok of 4 as they must be (views-stubs.txt)"
}
s_perturbed() {
  local got want
  want=$(awk '$1 == "push" {print substr($2, 1, 16)}' "$TOY/golden.txt")
  # shellcheck disable=SC2046
  (cd "$TOY" && $PY "$T/perturb3.py" . "$OUT/c-perturbed.jsonl.gz" $($PY -c 'import sys; sys.path.insert(0, "."); import check; print(" ".join(check.BASE + check.CELLS["push"]))') --digest \
      > "$OUT/c-perturbed.out" 2> "$OUT/c-perturbed.err")
  got=$(digest_of "$OUT/c-perturbed.out")
  if [ -n "$want" ] && [ -n "$got" ] && [ "$got" != "$want" ] && has -E '^perturb3: ' "$OUT/c-perturbed.err"; then
    echo "  control, a tracer that perturbs: push's digest is $got, golden.txt's $want: another, as it must be"
  else no "control, a tracer that perturbs: digest ${got:-none}, golden.txt's ${want:-none}, or the perturbing view did not say it ran"; fi
}
s_schemacontrols() {    # the generator's check and the makers' check: each planted change must fail them
  { $PY "$T/gen/gen.py" --control "$OUT/twin" "$OUT/c-schema" && $PY "$T/gen/makers.py" --control "$OUT/twin" "$OUT/c-makers"; } > "$OUT/c-schema.txt" 2>&1 \
    || no "the controls of the schema's checks (c-schema.txt)"
  grep -E '^ok: |wrong$' "$OUT/c-schema.txt" | sed 's/^/  /'
}
s_viewcontrols() {      # each broken view must fail its own cases, as many as written here
  local opt n what bad=0
  : > "$OUT/views-controls.txt"
  while read -r opt n what; do
    views_control "$opt" "$what" "$n" || bad=1
  done <<'EOF_VIEWS'
--broken 11 do not log 'k in t'
--broken-level 3 do not note at the assignment what a level brings
--broken-alloc 7 store the row a read of a missing one hands out
--broken-copy 10 hand out a fresh entry of no table for a missing one
--broken-callee 26 keep no log apart for a call on the tape
--broken-keys 1 put no keys on the tape for another section's level
--broken-mesh 1 answer the mesh question in rising order
--broken-rows 19 observe no row above an entry touched
--broken-bread 2 take no block's read after a callee's or an observation
--broken-order 4 keep a callee's own order of touches
--broken-lanes 10 do not take a PeerQueue's lane as a key
--broken-ordered 4 put no order of an ordered level on the tape
--broken-alias 1 have an alias check that refuses nothing
--broken-made-rows 3 write only the touched entry of a row made in the call
--broken-ordered-levels 3 ask no order below a table's top level
--broken-attr-reads 2 know no method's reads
--broken-cw-writes 1 leave out of a call's writes a callee's write the block undid
--broken-list 11 log nothing of a list of the namespace
--broken-values-order 1 ask no order of a table's values
--broken-cell 3 log the count's += and -= as a write alone
--broken-line 4 log the line's changes as a write alone
--broken-pop-miss 5 take a pop that finds nothing as a write too
EOF_VIEWS
  [ "$bad" = 0 ] || no "a broken view does not fail its cases as written (views-controls.txt)"
  [ "$(grep -c ', as they must$' "$OUT/views-controls.txt")" = 22 ] || no "not 22 broken views fail as written (views-controls.txt)"
  views_control_controls
  echo "  $(grep -c ', as they must$' "$OUT/views-controls.txt") of 22 broken views fail their cases, as they must"
}
s_tracercontrols() {
  local f want bad
  # the tracer's check of its own log: an assignment that goes unlogged must stop it
  if (cd "$TOY" && $PY "$T/unlogged3.py" . "$OUT/c-unlogged.jsonl.gz" --n 20000 --seed 1 > "$OUT/c-unlogged.out" 2> "$OUT/c-unlogged.err"); then
    no "the tracer wrote a trace to its end with every twentieth assignment unlogged"
  elif has -E '^unlogged3: ' "$OUT/c-unlogged.err" && has -E "^trace3: the views' log does not account" "$OUT/c-unlogged.err"; then
    echo "  control, an assignment unlogged: the tracer stopped, as it must"
  else no "the tracer stopped on an unlogged assignment for another reason (c-unlogged.err)"; fi
  # the tracer's own checks: each planted fault must stop it, with its own words
  : > "$OUT/c-tracerfaults.txt"; bad=0
  for f in made-rows-off alias alias-control installed-flip pending-twice alias-start alias-message defer-chain replaced false-wrapper stale-id level1-in-cell late-rebind stale-id-callee rebind-after-records limit-fraction; do
    case $f in
      made-rows-off) want="^trace3: the views' log does not account for the state" ;;
      alias) want="^trace3: node [0-9]*: one queue entry stands in two places" ;;
      alias-control) want="^trace3: node [0-9]*: one queue entry's control stands in two places" ;;
      installed-flip) want="^trace3: installed_block\([0-9]*, [0-9a-f]*…\) answered (True, then False|False, then True), in one record" ;;
      pending-twice) want="^trace3: node [0-9]*: peer [0-9]*'s copy [0-9a-f]*… waits twice under one root" ;;
      alias-start) want="^trace3: node [0-9]*: one queue entry's control stands in two places, .*, at the record's start" ;;
      alias-message) want="^trace3: node [0-9]*: one queue control message stands in two places" ;;
      defer-chain) want="^trace3: node [0-9]*: a chain of 3 defers in one record, past the twin's 2" ;;
      replaced) want="^trace3: node [0-9]*: may_ask is traced, and its function here is neither protocol.md's own code nor a listed wrapper of it: replaced\.<locals>" ;;
      false-wrapper) want="^trace3: node [0-9]*: may_ask is traced, and its function here is neither protocol.md's own code nor a listed wrapper of it: .*a listed wrapper's name, without the document's may_ask in its closure" ;;
      late-rebind) want="^trace3: node [0-9]*: may_ask was bound again after the tracer was installed, to what is neither the tracer's wrapper nor a listed wrapper of it: late_rebind\.<locals>" ;;
      rebind-after-records) want="^trace3: node [0-9]*: may_ask was bound again after the tracer was installed, to what is neither the tracer's wrapper nor a listed wrapper of it: rebind_after_records\.<locals>" ;;
      limit-fraction) want="^trace3: node [0-9]*: MAX_IHAVE_LENGTH is no count: 2\.5" ;;
      level1-in-cell) want="^trace3: node [0-9]*: validate_chunk is something else than the document's here \(.*\), which only a trace of the whole state may have" ;;
      *) want="^trace3: node [0-9]*: message_id returned [0-9a-f]{112}, and the document's function gives [0-9a-f]{112} for that chunk" ;;
    esac
    if (cd "$TOY" && $PY "$T/tracerfaults3.py" "--$f" . "$OUT/c-tf-$f.jsonl.gz" --n 20000 --seed 1 > "$OUT/c-tf-$f.out" 2> "$OUT/c-tf-$f.err"); then
      echo "$f: the tracer wrote its trace to the end  <-- it must not" >> "$OUT/c-tracerfaults.txt"; bad=1
    elif has -E '^tracerfaults3: ' "$OUT/c-tf-$f.err" && has -E "$want" "$OUT/c-tf-$f.err"; then
      echo "$f: the tracer stopped, as it must: $(grep -m 1 -E "$want" "$OUT/c-tf-$f.err" | cut -c1-100)" >> "$OUT/c-tracerfaults.txt"
    else echo "$f: the tracer stopped without the words it must give  <-- NOT" >> "$OUT/c-tracerfaults.txt"; bad=1; fi
  done
  [ "$bad" = 0 ] || no "a planted fault of the tracer's (c-tracerfaults.txt)"
  [ "$(grep -c 'the tracer stopped, as it must' "$OUT/c-tracerfaults.txt")" = 16 ] || no "not 16 planted faults stop the tracer as written (c-tracerfaults.txt)"
  echo "  $(grep -c 'the tracer stopped, as it must' "$OUT/c-tracerfaults.txt") of 16 planted faults stop the tracer with their own words"
}
again_directed() {      # $1: a directed set; $2: 1 or 2: made again, in a process of its own
  local d=$1 tool
  tool=$(dirtool "$d")
  # shellcheck disable=SC2046
  (cd "$TOY" && $PY "$T/${tool%% *}" . "$OUT/seeds/$d-again$2.jsonl.gz" --n 20000 --seed 1 $(case "$tool" in *" "*) echo "${tool#* }" ;; esac) > /dev/null 2>&1)
}
seed_cells() {          # the seeds' cells, traced and replayed once more: their report to a file of its own
  # shellcheck disable=SC2086
  $PY "$T/cells3.py" "$TOY" "$OUT/seeds" -j 2 --replay "$REPLAY" $SEEDCELLS > "$OUT/seeds/cells.txt" 2>&1
}
s_seeds() {             # the same bytes whatever Python's hash seed: every directed set made again twice, two cells once
  local d s a b n=0 want h1 h2
  # The tracers' Python runs isolated and reads no PYTHONHASHSEED: its hash seed is random in every process. That
  # is what this step stands on, so it is shown first: two processes hash one string differently.
  h1=$($PY -c 'import sys; print(sys.flags.hash_randomization, hash("the same string"))')
  h2=$($PY -c 'import sys; print(sys.flags.hash_randomization, hash("the same string"))')
  case "$h1" in "1 "*) [ "$h1" != "$h2" ] || no "two Python processes hash a string alike: the hash seed is not random here" ;;
    *) no "Python's hash randomization is off: a retrace shows nothing" ;; esac
  rm -rf "$OUT/seeds"; mkdir -p "$OUT/seeds"; : > "$OUT/same-content.txt"
  for d in $DIRS; do for s in 1 2; do par again_directed "$d" "$s"; done; done
  # shellcheck disable=SC2086
  [ -z "$SEEDCELLS" ] || par seed_cells
  par_end || no "a trace could not be made again"
  for d in $DIRS; do for s in 1 2; do
    a=$(zcat "$OUT/directed/$d.jsonl.gz" | sha256sum | cut -c1-64); b=$(zcat "$OUT/seeds/$d-again$s.jsonl.gz" 2> /dev/null | sha256sum | cut -c1-64)
    echo "$d, made again ($s), and the run's own: $b, $a: $([ "$a" = "$b" ] && echo equal || echo DIFFERENT)" >> "$OUT/same-content.txt"
    [ "$a" = "$b" ] && n=$((n + 1))
  done; done
  for d in $SEEDCELLS; do
    a=$(zcat "$OUT/traces/$d.jsonl.gz" | sha256sum | cut -c1-64); b=$(zcat "$OUT/seeds/$d.jsonl.gz" 2> /dev/null | sha256sum | cut -c1-64)
    echo "$d, traced twice: $a, $b: $([ "$a" = "$b" ] && echo equal || echo DIFFERENT)" >> "$OUT/same-content.txt"
    [ "$a" = "$b" ] && n=$((n + 1))
  done
  want=$(( 2 * $(echo $DIRS | wc -w) + $(echo $SEEDCELLS | wc -w) ))
  [ "$n" = "$want" ] || no "not $want comparisons equal (same-content.txt)"
  echo "  $n of $want traces made again, each in a process with a hash seed of its own, have the same bytes (same-content.txt)"
}
size_one() {            # $1: a trace: its size's line and its full-id line, each to a file of its own
  local t=$1 k f nb nl big n rc
  k=$(echo "$t" | tr '/' '-'); f=$OUT/sizes/$k
  zcat "$OUT/$t.jsonl.gz" > "$f.jsonl" 2> /dev/null || { rm -f "$f.jsonl"; return 1; }
  nb=$(wc -c < "$f.jsonl"); nl=$(wc -l < "$f.jsonl")
  big=$(LC_ALL=C awk '{ if (length($0) > m) m = length($0) } END { print m + 0 }' "$f.jsonl")
  echo "$t: $nb bytes, $nl lines, the longest $big bytes" > "$f.size"
  n=$($PY "$T/fullid.py" "$f.jsonl"); rc=$?
  rm -f "$f.jsonl"
  echo "$t: ${n:-no count} lines with a full id outside its places (fullid.py's exit code $rc)" > "$f.fullid"
  [ "$rc" = 0 ]
}
s_sizes() {
  local t k n
  $PY "$T/fullid.py" --self-test > "$OUT/fullid-self-test.txt" 2>&1 || no "fullid.py's own cases (fullid-self-test.txt)"
  rm -rf "$OUT/sizes"; mkdir -p "$OUT/sizes" || { no "the sizes' directory"; return; }
  for t in $RTRACES; do par size_one "$t"; done
  par_end || no "a trace could not be read, or fullid.py did not count it"
  : > "$OUT/sizes.txt"; : > "$OUT/full-id-keys.txt"
  for t in $RTRACES; do
    k=$(echo "$t" | tr '/' '-')
    cat "$OUT/sizes/$k.size" >> "$OUT/sizes.txt" 2> /dev/null || no "$t has no size"
    cat "$OUT/sizes/$k.fullid" >> "$OUT/full-id-keys.txt" 2> /dev/null || { no "$t has no full-id count"; continue; }
    case "$t" in traces/hand5*|directed/*) ;; *)        # a cell under either document: its nodes ask by index
      n=$(sed -n 's/^[^:]*: \([0-9]*\) lines with a full id .*/\1/p' "$OUT/sizes/$k.fullid")
      [ "$n" = 0 ] || no "$t: ${n:-no count of} lines with a full id where the nodes ask by index" ;; esac
  done
  [ "$(grep -c . "$OUT/sizes.txt")" = "$(echo $RTRACES | wc -w)" ] || no "not every trace in sizes.txt"
  echo "  sizes.txt: $(grep -c . "$OUT/sizes.txt") traces, $(awk '{ s += $2 } END { printf "%d", s }' "$OUT/sizes.txt") bytes in all; the largest: $(sort -t' ' -k2,2n "$OUT/sizes.txt" | tail -n 1)"
  echo "  full-id-keys.txt: $(grep -c ': 0 lines' "$OUT/full-id-keys.txt") traces with none"
}
s_matrix() {            # part $PART of the mutants, on the directed sets first, then on the cells and the hand traces
  local m=$OUT/matrix o=$OUT/matrix/out c d rc mc
  mc="$CELLS hand5 hand5-publish"; [ -z "$REHEARSAL" ] || mc="hand5 hand5-publish"
  rm -rf "$m"; mkdir -p "$m/cells" "$m/directed" "$o" || { no "the matrix's directory"; return; }
  for c in $mc; do ln -s "$OUT/traces/$c.jsonl.gz" "$m/cells/$c.jsonl.gz" || no "no trace of $c for the matrix"; done
  for d in $DIRS; do ln -s "$OUT/directed/$d.jsonl.gz" "$m/directed/$d.jsonl.gz" || no "no directed set $d for the matrix"; done
  # shellcheck disable=SC2086
  $PY "$T/mutants3.py" "$m/directed" "$m/work" -j "$J" --twin "$OUT/twin" --part "$PART" --hashes "$o/mutants.sha256" \
      --pairs "$o/mutants-directed-pairs.txt" $REHEARSAL > "$o/mutants-directed.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] || no "the mutants on the directed sets: rc=$rc (matrix/out/mutants-directed.txt)"
  tail -n 1 "$o/mutants-directed.txt" | grep -q -E '^([0-9]+) of \1 mutants told from the twin by these traces: ' \
    || no "not every mutant of the part is told by a directed set"
  # shellcheck disable=SC2086
  $PY "$T/mutants3.py" "$m/cells" "$m/work" -j "$J" --twin "$OUT/twin" --part "$PART" --reuse \
      --pairs "$o/mutants-pairs.txt" ${SAMPLE:+--sample "$SAMPLE"} $REHEARSAL > "$o/mutants-cells.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] || no "the mutants on the cells: rc=$rc (matrix/out/mutants-cells.txt)"
  # a draft's sample: every mutant of the part on the directed sets, the sample alone on the cells; marked, so
  # that no merge reads it as a matrix's part
  [ -z "$SAMPLE" ] || echo "$SAMPLE" > "$o/SAMPLE"
  if grep -q "'other'" "$o/mutants-directed.txt" "$o/mutants-cells.txt"; then no "a mismatch of a kind the reports do not name ('other')"; fi
  # what ties the part to what it ran and to its traces
  cp "$CONTENT" "$o/content.line" || no "the content line into the part"
  if [ -n "$REHEARSAL" ]; then echo "a rehearsal: no cell traced" > "$o/cells.txt"; else cp "$OUT/cells.txt" "$o/cells.txt" || no "cells.txt into the part"; fi
  sha256sum < "$REPLAY" | cut -c1-64 > "$o/replay.sha256"
  # shellcheck disable=SC2046
  (cd "$OUT" && $PY "$T/content.py" --hashes $(for c in $mc; do echo "traces/$c.jsonl.gz"; done) > "$o/traces.sha256" \
    && $PY "$T/content.py" --hashes $(for d in $DIRS; do echo "directed/$d.jsonl.gz"; done) > "$o/directed.sha256") || no "the traces' hashes into the part"
  (cd "$o" && sha256sum content.line traces.sha256 cells.txt replay.sha256 directed.sha256 mutants.sha256 mutants-pairs.txt \
      mutants-directed-pairs.txt mutants-cells.txt mutants-directed.txt > outputs.sha256) || no "the part's outputs.sha256"
  echo "  the directed sets: $(tail -n 1 "$o/mutants-directed.txt" | cut -c1-110)"
  echo "  the cells: $(tail -n 1 "$o/mutants-cells.txt" | cut -c1-110)"
}
s_against() {           # the run's manifest against the record's
  local rc
  $PY "$T/against.py" "$AGAINST" "$OUT" > "$OUT/against.txt" 2>&1; rc=$?
  case $rc in
    0|3) echo "  $(tail -n 1 "$OUT/against.txt" | cut -c1-200) (against.txt)" ;;
    *) no "the run is not the record's, or one of the two cannot be read (against.py's exit code $rc; against.txt): $(tail -n 1 "$OUT/against.txt" | cut -c1-120)" ;;
  esac
}
s_manifest() {           # the record's 55 traces by their two hashes, with what they were made from and by
  local f=$OUT/record-manifest.txt
  { echo "content $(sha256sum < "$CONTENT" | cut -c1-64)"
    echo "python $($PY -c 'import sys, platform; print(platform.python_version(), platform.machine(), sys.platform)')"
    echo "replay $(sha256sum < "$REPLAY" | cut -c1-64)"
    echo "twin $(sha256sum < "$OUT/twin-sources.txt" | cut -c1-64) ($(wc -l < "$OUT/twin-sources.txt") files: twin-sources.txt)"
    echo "documents protocol.md $(sha256sum < "$TOY/../protocol.md" | cut -c1-64) protocol-v2.md $(sha256sum < "$TOY/../protocol-v2.md" | cut -c1-64) (each file's sha256: reported, it decides nothing)"
    $PY -c 'import sys, hashlib; sys.path.insert(0, sys.argv[1]); import mutants3 as M; n = list(M.MUTANTS); print("mutants", len(n), hashlib.sha256("\n".join(n).encode()).hexdigest(), "(their names, in the tool'"'"'s order)")' "$T"
    # shellcheck disable=SC2046
    (cd "$OUT" && $PY "$T/content.py" --hashes $(for t in $RTRACES; do echo "$t.jsonl.gz"; done))
  } > "$f" 2> "$OUT/record-manifest.err" || no "the manifest (record-manifest.err)"
  [ "$(grep -c -E '^[0-9a-f]{64}  [0-9a-f]{64}  ' "$f")" = "$(echo $RTRACES | wc -w)" ] || no "not $(echo $RTRACES | wc -w) traces in the manifest"
  echo "  record-manifest.txt: $(grep -c -E '^[0-9a-f]{64}  [0-9a-f]{64}  ' "$f") traces; the traces' lines alone: sha256 $(grep -E '^[0-9a-f]{64}  ' "$f" | sha256sum | cut -c1-64)"
}

{
  date '+start %F %T %Z'
  echo "the toy: $TOY"
  $PY "$T/content.py" --toy "$TOY" > "$CONTENT" || { echo "check.sh: no content line of this tree (content.py)"; fail=" setup"; }
  echo "the content line: $(wc -c < "$CONTENT") bytes, sha256 $(sha256sum < "$CONTENT" | cut -c1-64)"
  for step in $STEPS; do
    [ -z "$fail" ] || [ "$fail" != " setup" ] || break
    echo "== $step: $(date '+%T')"
    case $step in build) ;; *) [ -x "$REPLAY" ] || { no "no replay built (the step build comes first)"; continue; } ;; esac
    "s_$step"
  done
  # the tree at the end is the tree at the start, and the bytecode directory is still empty
  $PY "$T/content.py" --toy "$TOY" | cmp -s - "$CONTENT" || { step=end; no "a file the content line names changed while the check ran"; }
  [ -z "$(find "$OUT/pyc" -type f | head -n 1)" ] || { step=end; no "a bytecode file was written to $OUT/pyc"; }
  if [ -s "$OUT/twin-sources.txt" ]; then     # the twin's sources, and the copy that was built, as at the build
    twin_list "$HERE" 2> /dev/null | cmp -s - "$OUT/twin-sources.txt" || { step=end; no "a source of the twin, or this script, changed since the build"; }
    twin_list "$OUT/twin" 2> /dev/null | cmp -s - "$OUT/twin-sources.txt" || { step=end; no "the built copy of the twin changed since the build"; }
  fi
  date '+end %F %T %Z'
  if [ -n "$fail" ]; then echo "check.sh: FAIL ($(echo $fail | tr ' ' '\n' | awk '!seen[$0]++' | tr '\n' ' ' | sed 's/ $//'))"
  elif [ "$STEPS" != "$ALL" ]; then echo "check.sh: these steps passed ($STEPS): a part, not a pass"
  elif [ -n "$REHEARSAL" ]; then echo "check.sh: these steps passed ($STEPS): a rehearsal of the matrix's step, not a part"
  elif [ -n "$SAMPLE" ]; then echo "check.sh: these steps passed ($STEPS): part $PART of a draft's sample ($SAMPLE), not a matrix"
  elif [ -n "$PART" ]; then echo "check.sh: PASS (part $PART of the matrix)"
  elif [ -n "$FEWCELLS" ]; then echo "check.sh: these steps passed ($STEPS): a rehearsal over the cells [$CELLS], not a record"
  elif [ -n "$RECORD" ]; then echo "check.sh: PASS (the record's run)"
  else echo "check.sh: PASS"; fi
} 2>&1 | tee "$LOG"
case "$(tail -n 1 "$LOG")" in "check.sh: PASS"|"check.sh: PASS (the record's run)"|"check.sh: PASS (part "*) true ;; *) false ;; esac \
  || { { [ "$STEPS" != "$ALL" ] || [ -n "$REHEARSAL" ] || [ -n "$SAMPLE" ] || [ -n "$FEWCELLS" ]; } && tail -n 1 "$LOG" | grep -q '^check.sh: these steps passed'; }
