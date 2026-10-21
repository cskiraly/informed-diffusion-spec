#!/bin/bash
# Regression sweep: every instance against its expected result, by random simulation.
#   tools/sweep.sh [samples] [jobs] [pattern]
# By default 5000 traces of up to 600 steps a row, one row at a time; jobs > 1 runs rows in
# parallel, each up to about 4 GB (the kite at 800 steps), and prints them in table order. A
# pattern keeps the rows whose instance name contains it (_pick: v0.5's rules). Each row's output
# goes to out/sweep.<pid>/, and is kept for a row whose result is not the expected one.
# "ok" = no violation expected; "viol" = a violation expected (a finding, or a known answer); the
# fourth column is the trace count for a row whose violation is rare, the fifth the trace length
# for a row that checks eventual completion (DONE_BY = 600: traces of 800 steps; for four nodes that
# pull every chunk 1,000: traces of 1,200) ("-": the default).
cd "$(dirname "$0")/.." || exit 2
n=${1:-5000}; jobs=${2:-1}; pat=${3:-}
row() {   # k inst inv want rows steps why...: one row's line, into $OUT/k
  local k=$1 inst=$2 inv=$3 want=$4 rows=$5 steps=$6; shift 6
  local s=$N; [ "$rows" = "-" ] || s=$rows                 # rare events get their own count
  local m=600; [ "$steps" = "-" ] || m=$steps
  local log=$OUT/$k.log out got mark seed
  # into a file, not a pipe: Quint prints a trace, a violation's or an example run's (megabytes on
  # the kite), before its verdict line, and node can exit before a pipe has taken the end of its output
  ./quint run --main="$inst" --invariant="$inv" --max-samples="$s" --max-steps="$m" instances.qnt > "$log" 2>&1
  out=$(grep -E '^\[(violation|ok)\]' "$log" | head -1)
  got=ok; [[ $out == "[violation]"* ]] && got=viol      # the ok line says "No violation found"
  [ -z "$out" ] && got=error
  # no verdict: the output's end says why (printed after the row)
  [ $got = error ] && tail -5 "$log" | sed 's/^/     | /' > "$OUT/$k.err"
  mark=PASS; [ "$got" = "$want" ] || mark=FAIL
  # an unexpected result keeps the seed that reproduces it, and its log
  seed=""; [ $mark = FAIL ] && seed=" [$(grep -oE -- '--seed=0x[0-9a-f]+' "$log" | head -1)]"
  [ $mark = PASS ] && rm -f "$log"
  printf "%-4s %-26s %-14s want %-4s got %-4s  %s%s\n" "$mark" "$inst" "$inv" "$want" "$got" "$*" "$seed" > "$OUT/$k"
}
export -f row
export N=$n OUT=$PWD/out/sweep.$$
mkdir -p "$OUT"
k=0
while read -r inst inv want rows steps why; do
  [ -z "$inst" ] || [ "${inst:0:1}" = "#" ] && continue
  [ -n "$pat" ] && [[ $inst != *"$pat"* ]] && continue
  k=$((k + 1))
  printf '%s\0' "$(printf %04d $k)" "$inst" "$inv" "$want" "$rows" "$steps" "$why"
done <<'TABLE' | xargs -0 -n 7 -P "$jobs" bash -c 'row "$@"' _ ; for f in "$OUT"/[0-9][0-9][0-9][0-9]; do cat "$f"; [ -f "$f.err" ] && cat "$f.err"; done; if ls "$OUT"/*.log >/dev/null 2>&1; then echo "logs of unexpected rows: $OUT/*.log"; fi
# the spec as written
t3                safeNoStall    ok   -     -    A1 W1 W2 S1 P4 on the triangle
f4                safeNoStall    ok   -     -    the same, four nodes
k4                safeNoStall    ok   -     -    the same, the kite
t3                noStall        viol -     -    F1: the triangle stalls
k4                noStall        viol -     -    F1: the kite stalls
k4_fixa           noStall        viol -     -    F2: a slow answer parks the only provider
f4adv             noStall        ok   -     -    one adversary, four nodes
t3r1_coal         noPenalty      ok   -     -    a coalescing transport keeps A1
t3r0_gatelate     noBadPark      viol -     -    F3: a deferred answer parks its sender (R = 0: every chunk asked)
t3r0_gatelate     noBadParkSameBlock viol - -    ... and the equivocation monitor counts it: its node has one block
t3r1_expiry       noExpiredAsk   viol -     -    F4: the retry asks after expiry (a group expires while an ask is out)
f4w1_ab           noParkUnasked  viol -     -    F5: an ask held behind the window
f4q3_ab           noParkUnasked  viol -     -    F5: an ask dropped at a full queue
f4bad             noDropLeak     ok   -     -    drop_group lets nothing of the group out
f4bad             noBadPark      ok   -     -    no announcer parked for the builder's fault
f4pull            noStall        viol -     -    nodes that only pull: parks stall them (F2)
# the first candidate fixes
t3_fixa           noStall        ok   -     -    fix A: the triangle completes
k4_fixab          noStall        ok   -     -    fixes A and B: the kite completes
f4_fixab          safety         ok   -     -    fixes A and B, everything, four nodes
f4adv_ab          safety         ok   -     -    fixes A and B under one adversary
f4w1_abe          noParkUnasked  ok   -     -    fix E: no park for an ask that never left
t3r1q2_abe        noStall        viol -     -    fixes A, B, E: queues that drop still stall (a dropped offer)
# all five first fixes, every property
t3_all            allProps       ok   -     -    fixes A to E, the triangle
k4_all            allProps       ok   -     -    fixes A to E, the kite
f4_all            allProps       ok   -     -    fixes A to E, four nodes
f4adv_all         allProps       ok   -     -    fixes A to E, one adversary
f4w1_all          allProps       ok   -     -    fixes A to E, one window slot
t3r0_gatelate_all allProps       ok   -     -    fixes A to E, the late block
f4bad_all         badCodeProps   ok   -     -    fixes A to E, an inconsistent code
# cases that break the first fixes
t3r0adv_forge_all noStall        viol -     -    C: a forged copy waits unchecked and stops the asks for its index
t3r0adv_forge_all noForgedClose  viol -     -    C: a forged copy closes a promise
t3r0adv_forge_gatelate_all noStall viol -   -    C: a forgery rejected at installation leaves its index unasked
t3r0_gatelate_refuse_all noBadPark viol -   -    C: a refused reservation still parks the answerer
f4adv_o1_pull_ab  doneBy         viol -     1200 B: a captured offer table, and the last resort never goes quiet
t3r1_expiry_all   noExpiredAsk   viol -     -    D: an ask queued before expiry is written after it
t3r0adv_forge_gatelate_bp_all noStall viol - -   C: a forgery that fails its proof at installation leaves its index unasked
t3r1q2_abe        noStall        viol -     -    A, B and E with queues of two: a refused offer is never made again
# cases that break drafts of the revision
t3r0gate_o1adv_b2r live          viol -     800  B′ by replacement: before the block nobody is asked, the withholder keeps the table
k4q2_rev_lrdecide live           viol -     800  B′ counted when decided: a last-resort ask the queue refuses spends the budget
# the fixes as revised: A′, B′, C′, D′ and E (in v0.5)
t3_a2             noStall        ok   -     -    A′: the triangle completes
k4_a2             noStall        viol -     -    A′ alone: F2 remains
k4_ab2            live           ok   -     800  A′ and B′: the kite completes, quiet by step 600
f4adv_o1_pull_ab2 live           ok   -     1200 B′: the captured table recovers
f4adv_o1_pull_b2r live           ok   -     1200 B′ by replacement recovers it too, while asks go out before the block
f4adv_forge_ab2   forgeProps     ok   -     -    A′ and B′ with forged chunks: the spec's level 1 holds (F5 is E's)
t3_rev            liveProps      ok   -     800  every property, and eventual completion: the triangle
k4_rev            liveProps      ok   -     800  the kite
f4_rev            liveProps      ok   -     800  four nodes
f4adv_rev         liveProps      ok   -     800  one adversary
f4w1_rev          liveProps      ok   -     800  one window slot
t3r1_coal_rev     liveProps      ok   -     800  a coalescing transport
t3r0_gatelate_rev liveProps      ok   -     800  the late block: F3 gone (C′)
f4_gate_rev       liveProps      ok   -     800  the block gate, four nodes
f4pull_rev        liveProps      ok   -     1200 nodes that only pull
t3r0adv_forge_rev liveProps      ok   -     800  forged chunks (C′)
t3r0adv_forge_n4_rev liveProps   ok   -     800  forged chunks, N = 4
t3r0adv_forge_gatelate_rev liveProps ok -   800  forged chunks and a late block
f4adv_forge_rev   liveProps      ok   -     800  forged chunks, four nodes
t3r0_gatelate_refuse_rev liveProps ok -     800  a deferred store that refuses
f4adv_o1_pull_rev liveProps      ok   -     1200 a captured offer table
t3r0gate_o1adv_rev liveProps     ok   -     800  a captured offer table before the block: every offer kept, the source asked at installation
t3r0adv_forge_gatelate_bp_rev liveProps ok - 800 a forgery that fails its proof at installation
t3r1q2_rev        liveProps      ok   -     800  queues of two entries: refused pushes, offers and answers owed (A′)
f4q3_rev          liveProps      ok   -     800  queues of three entries, four nodes
k4q2_rev          liveProps      ok   -     800  queues of two on the kite: a refused last-resort ask, refused answers
t3r1_expiry_rev   expiryProps    ok   20000 -    expiry while an ask is out: no ask written past the lifetime (D′), and the rest
t3r1_expiry_any_rev expiryProps  ok   20000 -    expiry at any time (D′)
f4bad_rev         badCodeProps   ok   -     -    an inconsistent code
# equivocation: nodes on the proposer's other block, whose bid commits the same group
t3eq_rev          noEqPark       viol -     800  witness: a node on the other block parks a provider whose answer arrived (C′'s residual)
t3eq_rev          eqProps        ok   -     800  only a node on the other block at the time parks so, and everyone completes, the switched node too
t3r0eq_rev        eqProps        ok   -     800  the same with R = 0: every chunk asked for
t3eq_nosw_rev     eqProps        ok   -     800  a node on the other block for good: the other honest node completes
k4eq_rev          eqProps        ok   -     800  the kite, node 3 on the other block
k4eq2_rev         eqProps        ok   -     800  the kite, node 2 (node 3's only peer) on the other block
f4eq_rev_long     eqProps        ok   -     1200 four nodes, nodes 2 and 3 on the other block
t3eq_rev_any      eqProps        ok   -     800  the switch at any time (no EQ_LATE)
t3r0eq_refuse_rev_any eqProps    ok   -     800  R = 0, a refusing store, the switch at any time
t3r0eq_refuse_nob noEqSwitchShort viol -    800  witness: switched with every peer parked, short of K, nothing waiting
t3r0eq_refuse_nob noEqStall      viol -     800  known answer: without B′ the switched node stalls
t3r0eq_refuse_rev noEqStall      viol -     800  F6: with B′ too, its last resort spent before the switch
# the additions' first forms: EQ_UNPARK (F6), REFUSE_OFFERS (F7)
t3r0eq_refuse_unpark noEqStall   ok   -     800  EQ_UNPARK, with the switch late (EQ_LATE): the installation lifts the group's parks and B′'s counts
t3r0eq_refuse_unpark eqOtherProps ok  -     800  ... every property but the park monitor
t3eq_refuse_unpark noBadParkSameBlock viol - 800 EQ_UNPARK leaves promises open: one from before the switch parks its provider again after it
t3eq_refuse_unpark eqOtherProps  ok   -     800  ... every other property, R = 2
k4n2eqx_unpark    noExhaustSwitch viol -    800  witness (EQ_EXHAUST): the switch with node 2's three answers for a chunk spent
k4n2eqx_unpark    noEqStall      viol -     800  a directed case: EQ_UNPARK does not remove F6 (GOSSIP_RETRANSMISSION spent before the switch)
t3r0n2eqx_unpark  noEqStall      viol -     800  the same on the triangle, both providers' answers spent
k4eq_refuse_unpark eqOtherProps  viol -     800  F7 through equivocation: node 3's only peer pushed, the store refused it
k4gatelate_refuse_rev live       viol -     800  F7 without equivocation: a refused push is lost (the kite, a late block; the block installs)
k4gatelate_refuse_noc live       viol -     800  F7 is the spec's too: without C′ (A′, B′, D′, E)
k4gatelate_refuse_ro liveProps   ok   -     800  REFUSE_OFFERS: a refused copy counts as its sender's announcement
t3r0_gatelate_refuse_ro liveProps ok  -     800  the triangle, R = 0, with REFUSE_OFFERS
t3r0eq_refuse_both eqOtherProps  ok   -     800  equivocation and a refusing store, both additions: the triangle
k4eq_refuse_both  noBadParkSameBlock viol - 800  ... a promise from before the switch parks the provider again (the kite)
k4eq_refuse_both  eqOtherProps   ok   -     800  the kite, node 3 on the other block, every other property
k4eq2_refuse_both eqOtherProps   ok   -     800  the kite, node 2 on the other block
f4eq_refuse_both  eqOtherProps   ok   -     1200 four nodes, two on the other block
t3r0adv_forge_gatelate_both liveProps ok - 800   forged chunks, a late block, a refusing store, both additions
t3r0adv_forge_gatelate_unpark liveProps ok - 800 forged chunks and a late block, EQ_UNPARK
t3r0_gatelate_refuse_unpark liveProps ok - 800   a late block and a refusing store, EQ_UNPARK
# the root-tied recovery (ROOT_TIED) in their place, and NO_REASK_OPEN: liveProps allows no park of a
# provider whose answer arrived at all
t3r0eq_refuse_rt  liveProps      ok   -     800  ROOT_TIED: every property, no such park at all, completion (R = 0, the switch late)
t3eq_refuse_rt    liveProps      ok   -     800  the same with R = 2
t3r0eq_refuse_rt_any liveProps   ok   -     800  the switch at any time
t3eq_rt           liveProps      ok   -     800  a store that keeps everything
k4eq_refuse_rt    liveProps      ok   -     800  the kite, node 3 on the other block: F6 and F7
k4eq2_refuse_rt   liveProps      ok   -     800  the kite, node 2 on the other block
f4eq_refuse_rt    liveProps      ok   -     1200 four nodes, two on the other block
k4gatelate_refuse_rt liveProps   ok   -     800  F7 without equivocation (the kite, a late block)
t3r0_gatelate_refuse_rt liveProps ok  -     800  the triangle, R = 0, a late block
t3r0adv_forge_gatelate_rt liveProps ok -    800  forged chunks, a late block, a refusing store
f4adv_forge_eq_rt liveProps      ok   -     800  four nodes: one on the other block, one forging
t3r0_gatelate_rt_noc liveProps   ok   -     800  ROOT_TIED without C′: an answer that waits parks nobody (F3)
k4n2eqx_rt        noExhaustSwitch viol -    800  residual: asks decided before the provider's first answer came back spend its three
k4n2eqx_rt        noEqStall      viol -     800  ... and the switched node stalls
k4n2eqx_rtnr      noExhaustSwitch ok  -     800  NO_REASK_OPEN: no ask to a peer with one outstanding, so the three are never spent
k4n2eqx_rtnr      liveProps      ok   -     800  ... every property and completion
t3r0n2eqx_rtnr    noExhaustSwitch ok  -     800  the triangle, the same
t3r0n2eqx_rtnr    liveProps      ok   -     800  ...
k4n2eqx_unparknr  noEqStall      ok   -     800  NO_REASK_OPEN rescues EQ_UNPARK here too
t3_rev_nr         liveProps      ok   -     800  NO_REASK_OPEN on the revision's shapes: the triangle
k4_rev_nr         liveProps      ok   -     800  the kite
f4adv_rev_nr      liveProps      ok   -     800  a withholder
f4pull_rev_nr     liveProps      ok   -     1200 nodes that only pull
k4q2_rev_nr       liveProps      ok   -     800  queues of two
f4w1_rev_nr       liveProps      ok   -     800  one window slot
# disconnects: a connection closes and a new one opens at once; B′'s counts go with it, as v0.5 has it
t3disc_rev        noDiscPark     viol -     800  F8: a promise outlives its connection and parks the peer
t3disc_rev        discProps      ok   -     800  every other property, and completion, through one close
t3disc_cp_rev     noDiscPark     ok   -     800  CLOSE_PROMISES_ON_DISC: promises close with the connection
t3disc_cp_rev     discProps      ok   -     800  ... every property with it
t3r0disc_rev      discProps      ok   -     800  R = 0, one close
t3r0disc_cp_rev   discProps      ok   -     800  R = 0, CLOSE_PROMISES_ON_DISC
t3disc_any_rev    discProps      viol -     800  F9: the source's two connections close after the publish: nobody completes
t3disc_src_rev    discProps      viol -     800  F9, directed: the closes before the source has written a chunk
k4disc_rev        discProps      viol -     800  F9 (and F8): node 3's only connection closes once node 2 is complete
f4disc_rev        discProps      ok   -     800  four nodes, two closes while promises are open
f4w1disc_rev      discProps      ok   -     800  one slot, two closes at any time: the window and completion
t3disc_spec       safeNoStall    ok   -     -    the spec as written: safety through a close
t3disc_any_rs     discProps      ok   -     800  RESYNC_ON_CONNECT: each side offers the new connection what it can serve
t3disc_src_rs     discProps      ok   -     800  ... the source too, every chunk, before its first write (its HAVE stays paced: P4)
t3disc_dec_rsmine noUnservableIhave viol - 800  known answer: the resync's first form (the decode claim) offers chunks not yet rebuilt
t3disc_dec_rs     discProps      ok   -     800  the resync from what it can serve, a close while one side decodes
t3r1baddisc_rsmine noDropLeak    viol -     -    known answer: the first form offers a dropped group
t3r1baddisc_rs    badCodeProps   ok   -     -    the resync after a drop offers nothing of the group
t3r1_expiry_disc_rs expiryProps  ok   -     -    the resync after expiry offers nothing
t3r1_expiry_dec_rev noExpiredStore viol -   -    F10: a group expires while it decodes, and the decode stores its chunks again
t3r1_expiry_dec_chk expiryProps  ok   -     -    DECODE_CHECKS_EXPIRY: a decode that returns after the expiry is dropped
t3_expiry_dec_chk expiryProps    ok   -     -    ... at R = 2
f4_expiry_dec_chk expiryProps    ok   -     -    ... four nodes
t3r1_expiry_dec_disc_rs noExpiredStore viol - - F10 with closes once the group has expired and the resync
t3r1_expiry_dec_disc_chk expiryProps ok  -     -    ... with DECODE_CHECKS_EXPIRY
t3disc_any_both   discProps      ok   -     800  both disconnect additions, two closes at any time
t3disc_any_both   noDiscPark     ok   -     800  ... no park for a closed connection's promise
k4disc_both       discProps      ok   -     800  the kite, one close while a promise is open, both additions
k4disc_any_both   discProps      ok   -     800  the kite, two closes at any time, both additions
f4disc_both       discProps      ok   -     800  four nodes, two closes, both additions
f4w1disc_both     discProps      ok   -     800  one slot, two closes at any time, both additions
f4adv_disc_cp     liveProps      ok   -     800  a withholder whose connections close while its promise is open: never parked, everyone completes
f4pulladv_disc_cp liveProps      ok   -     1200 the same, nodes that only pull
f4adv_disc_cpw    liveProps      ok   20000 800  every close a withholder's connection while it owes an answer (DISC_AT = 5)
f4adv_disc_cpw    noSecondDisc   viol -     800  ... and two such closes happen (the witness; 5 of 100 single traces)
f4pulladv_disc_cpw liveProps     ok   20000 1200 the same, nodes that only pull
f4pulladv_disc_cpw noSecondDisc  viol -     1200 ... the witness
# equivocation and disconnects together, ungated: every addition (the revised set, and the first forms)
t3r0eqdisc_new    fullProps      ok   -     800  ROOT_TIED, NO_REASK_OPEN and both disconnect additions: R = 0, a refusing store, two closes
t3eqdisc_new      fullProps      ok   -     800  the same with R = 2
k4eqdisc_new      fullProps      ok   -     800  the kite, node 3 on the other block
k4eqlatedisc_new  fullProps      ok   -     800  the kite, the switch late, closes while a promise is open
f4eqdisc_adv_new  fullProps      ok   -     800  four nodes: one on the other block, one forging (its connections close too), queues of three
t3r0eqdisc_old    eqDiscProps    ok   -     800  EQ_UNPARK, REFUSE_OFFERS and both disconnect additions (every property but the park monitor)
k4eqdisc_old      eqDiscProps    ok   -     800  ... the kite
# the pick, v0.5's rules: the revised fixes, REFUSE_OFFERS, CLOSE_PROMISES_ON_DISC and
# DECODE_CHECKS_EXPIRY together; ROOT_TIED, NO_REASK_OPEN and RESYNC_ON_CONNECT are not in v0.5
t3_pick           liveProps      ok   -     800  the triangle
k4_pick           liveProps      ok   -     800  the kite
f4adv_pick        liveProps      ok   -     800  four nodes, one adversary
f4w1_pick         liveProps      ok   -     800  one window slot
f4pull_pick       liveProps      ok   -     1200 nodes that only pull
t3r1_coal_pick    liveProps      ok   -     800  a coalescing transport
k4q2_pick         liveProps      ok   -     800  the kite, queues of two entries
f4q3_pick         liveProps      ok   -     800  four nodes, queues of three entries
t3r0_gatelate_refuse_pick liveProps ok -    800  a late block, a refusing store
k4gatelate_refuse_pick liveProps ok   -     800  F7's kite: REFUSE_OFFERS asks the refused copies' senders
t3r0adv_forge_gatelate_refuse_pick liveProps ok - 800 forged chunks, a late block, a refusing store
f4adv_forge_pick  liveProps      ok   -     800  four nodes, one forging
t3disc_pick       fullProps      ok   -     800  one close while a promise is open: no park for it (F8), completion
f4disc_pick       fullProps      ok   -     800  four nodes, two closes while promises are open
t3disc_any_pick   discProps      viol -     800  F9, not fixed in v0.5: two closes at any time, nobody completes without the resync
f4adv_disc_cpw_pick fullProps    ok   -     800  a withholder whose connections close while it owes an answer
t3r1_expiry_pick  expiryProps    ok   20000 -    expiry while an ask is out or queued
t3r1_expiry_dec_pick expiryProps ok   -     -    F10: a group expires while it decodes, the decode dropped
f4_expiry_dec_pick expiryProps   ok   -     -    ... four nodes
f4bad_pick        badCodeProps   ok   -     -    an inconsistent code
t3eq_pick         eqProps        ok   -     800  equivocation, a store that keeps
k4eq_pick         eqProps        ok   -     800  ... the kite
# F6 with the pick: its first form (B′'s once more spent before the switch) was not found, though
# its precondition is reached; why REFUSE_OFFERS changes this is not traced, so it is not shown
# gone. Its second form (the providers' answers spent, EQ_EXHAUST) stalls: NO_REASK_OPEN is not in v0.5
t3r0eq_refuse_pick noEqSwitchShort viol - 800  witness: switched with every peer parked, short, nothing waiting
t3r0eq_refuse_pick noEqStall     ok   20000 800 a refusing store, the switch late: no stall found
t3r0eq_refuse_pick eqOtherProps  ok   -     800  ... and every node completes by step 600
k4eq_refuse_pick  noEqSwitchShort viol -    800  witness on the kite
k4eq_refuse_pick  eqOtherProps   ok   -     800  the kite, a refusing store, the switch late: completion
k4n2eqx_pick      noExhaustSwitch viol -    800  witness: the switch with every provider's answers spent
k4n2eqx_pick      noEqStall      viol -     800  F6, not fixed in v0.5: the answers spent before the switch, the kite
t3r0n2eqx_pick    noEqStall      viol -     800  ... the triangle
# known answers: the bugs found earlier
t3r1_noaskfilter  noPenalty      viol -     -    a bug found in an implementation
f4_nowake         noLostWakeup   viol -     -    the spec before 97be57d
f4bad_noleavewake noLostWakeup   viol -     -    the toy's first window (decode only while a writer waits: DROP_LATE)
t3_unpaced        p4             viol -     -    before P4
t3r1_coal_dwfirst noPenalty      viol -     -    IDONTWANT handled before IWANT
TABLE
