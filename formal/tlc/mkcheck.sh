#!/bin/bash
# Exhaustive check of one instance with TLC: Quint -> JSON IR -> Apalache's typechecker writes TLA+
# -> a wrapper module adds the invariants -> TLC. (quint verify --backend=tlc fails on this model:
# its IR is over Apalache's 20 MB RPC string limit, so the IR goes through a file instead.)
#
#   tlc/mkcheck.sh <instance> gen [INVARIANT...]   write tlc/out/<instance>/ (default: Safe NoStall);
#                                                  LIVE among them adds the temporal property that
#                                                  every behaviour ends quiet (<>[]Quiet, weakly fair)
#   tlc/mkcheck.sh <instance> run [workers]        run TLC on it (heap TLC_HEAP, default 10g)
# Apalache (whose jar also holds TLC) is the one Quint downloads into QUINT_HOME (./quint: .quint/).
set -euo pipefail
inst=$1; mode=${2:-gen}; shift 2 || true
here=$(cd "$(dirname "$0")/.." && pwd)
out=$here/tlc/out/$inst
A=${QUINT_HOME:-$here/.quint}/apalache-dist-0.62.1/apalache
v=${inst}_diffusion

if [ ! -x "$A/bin/apalache-mc" ]; then     # not downloaded yet: the release Quint 0.33 uses
  mkdir -p "$(dirname "$A")"
  curl -fsSL https://github.com/apalache-mc/apalache/releases/download/v0.62.1/apalache.tgz | tar -xz -C "$(dirname "$A")"
fi
if [ "$mode" = gen ]; then
  invs=("$@"); [ ${#invs[@]} -gt 0 ] || invs=(Safe NoStall)
  mkdir -p "$out"
  "$here/quint" compile --target=json --main="$inst" "$here/one/$inst.qnt" > "$out/$inst.qnt.json" 2>/dev/null
  (cd "$out" && JVM_ARGS="-Xmx8g" "$A/bin/apalache-mc" typecheck --output="${inst}_t.tla" "$inst.qnt.json" > typecheck.log 2>&1)
  # Quint's init assigns s' (s' := e); TLC's Init must not prime: drop the prime, since Apalache
  # defines x := e as x = e (the prime and := may sit on different lines)
  python3 -I - "$out/${inst}_t.tla" "$v" <<'PY'
import sys
path, v = sys.argv[1], sys.argv[2]
lines = open(path).read().split("\n")
start = next(k for k, l in enumerate(lines) if l.startswith(f"{v}_init =="))
end = next(k for k in range(start + 1, len(lines)) if lines[k] and not lines[k][0].isspace() and "==" in lines[k])
for var in ("s", "clock"):                     # the state and the step count
    for k in range(start, end):
        if f"{v}_{var}'" in lines[k]:
            lines[k] = lines[k].replace(f"{v}_{var}'", f"{v}_{var}", 1)
            break
    else:
        raise SystemExit(f"init assignment of {var} not found")
open(path, "w").write("\n".join(lines))
PY
  cat > "$out/${inst}_check.tla" <<TLA
---- MODULE ${inst}_check ----
EXTENDS ${inst}_t, FiniteSets, Sequences
St == ${v}_s
Wn == ${v}_W
\* A1, S1, P4 (the monitors' sets stay empty)
NoPenalty == St.penalties = {}
NoStaleAsk == St.badAsk = {}
P4 == St.badHave = {}
\* W1: slots conserved and bounded
WindowConserved == \A n \in DOMAIN St.nodes :
    /\ St.nodes[n].inFlight = Cardinality(St.nodes[n].slotHeld) + Cardinality(St.nodes[n].sent)
    /\ St.nodes[n].inFlight <= Wn
\* W2: a free slot and a waiting writer: the first in line will run
NoLostWakeup == \A n \in DOMAIN St.nodes :
    (Len(St.nodes[n].waiters) > 0 /\ St.nodes[n].inFlight < Wn) => Head(St.nodes[n].waiters) \in St.nodes[n].runnable
\* Q1: when nothing is left to happen (the model's own quiescent), every honest node is complete
\* and every slot back
Quiet == ${v}_quiescent(St)
NoStall == Quiet => \A n \in (DOMAIN St.nodes) \\ ${v}_ADV :
    St.nodes[n].stage = ${v}_COMPLETE /\ St.nodes[n].inFlight = 0 /\ St.nodes[n].slotHeld = {}
Safe == NoPenalty /\ NoStaleAsk /\ P4 /\ WindowConserved /\ NoLostWakeup
\* parking soundness, drop_group and expiry (the model's monitors)
NoBadPark == St.badPark = {}
NoParkUnasked == St.badUnsent = {}
NoDropLeak == St.badDrop = {}
NoExpiredAsk == St.badExpiredAsk = {}
\* L4: only forgers are penalised for a chunk that fails level 1; L5: no forged copy closes another
\* peer's promise; O1: an announcement names only chunks its sender can serve
NoHonestLvl1Pen == \A n \in DOMAIN St.nodes : St.nodes[n].lvl1Pen \subseteq ${v}_ADV
NoForgedClose == St.badClose = {}
NoUnservableIhave == St.badIhave = {}
\* a probe, not a property: no node decides an ask (it holds on the K = 1 triangle: nobody asks there)
NoAsk == \A n \in DOMAIN St.nodes : \A i \in DOMAIN St.nodes[n].askCount : St.nodes[n].askCount[i] = 0
\* every property the simulator's allProps checks
AllProps == Safe /\ NoStall /\ NoBadPark /\ NoParkUnasked /\ NoDropLeak /\ NoHonestLvl1Pen /\ NoForgedClose /\ NoUnservableIhave
\* Q3, eventual completion over the whole state space: under weak fairness every behaviour ends quiet
\* (no cycle of steps that never goes quiet), and NoStall makes quiet complete
Vars == <<${v}_s, ${v}_clock>>
FairSpec == q_init /\ [][q_step]_Vars /\ WF_Vars(q_step)
UnfairSpec == q_init /\ [][q_step]_Vars      \* its known answer (LIVE0): without fairness it may stutter
EventuallyQuiet == <>[]Quiet
====
TLA
  live=0; plain=()
  for i in "${invs[@]}"; do case $i in LIVE) live=Fair;; LIVE0) live=Unfair;; *) plain+=("$i");; esac; done
  { if [ $live != 0 ]; then echo "SPECIFICATION ${live}Spec"; echo "PROPERTY EventuallyQuiet"
    else echo "INIT q_init"; echo "NEXT q_step"; fi
    for i in "${plain[@]}"; do echo "INVARIANT $i"; done; echo "CHECK_DEADLOCK FALSE"; } > "$out/${inst}_check.cfg"
  echo "wrote $out (invariants: ${invs[*]})"
elif [ "$mode" = run ]; then
  workers=${1:-4}
  cd "$out"
  exec java -Xmx${TLC_HEAP:-10g} -Xss64m -XX:+UseParallelGC -cp "$A/lib/apalache.jar" tlc2.TLC -workers "$workers" -deadlock \
    -config "${inst}_check.cfg" "${inst}_check.tla"
else
  echo "mode: gen or run" >&2; exit 2
fi
