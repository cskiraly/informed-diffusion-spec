#!/usr/bin/env python3
"""Write formal/instances.qnt from the table below: every instance is the spec's defaults plus what
it changes. Run from formal/: python3 -I tools/gen_instances.py > instances.qnt
(and python3 -I tools/gen_instances.py --one <name> > one/<name>.qnt for TLC)"""
import sys

TRI = "Map(0 -> Set(1, 2), 1 -> Set(0, 2), 2 -> Set(0, 1))"
FULL4 = "Map(0 -> Set(1, 2, 3), 1 -> Set(0, 2, 3), 2 -> Set(0, 1, 3), 3 -> Set(0, 1, 2))"
# a line 0 - 1 - 2 - 3 plus 0 - 2: node 3's only peer is node 2
KITE = "Map(0 -> Set(1, 2), 1 -> Set(0, 2), 2 -> Set(0, 1, 3), 3 -> Set(2))"
DEFAULTS = dict(NN=3, K=2, N=4, MESH=TRI, R=2, R_NODE=2, W=2, OFFERS_MAX=16, SERVE_MAX=3, FAN_IN=2,
                CANCEL=True, PROJECT=True, RAREST=True, REPAIR=True, PACED_SRC_HAVE=True, PARK=True,
                PROJECT_OFFERS=False, PARK_LAST_RESORT=False, PROMISE_AT_WRITE=False, FORGET_DROPPED=False,
                CLOSE_ON_DEFER=False, RETRY_CHECKS_EXPIRY=False,
                ADMIT_OFFERS=False, LAST_RESORT=False, LR_MAX=1, OFFER_REPLACE=False, OFFERS_DURABLE=False, NO_ASK_BEFORE_INSTALL=False,
                EXPIRY_CLEANUP=False, ADV_FORGE=False, FORGE_KINDS="Set(1, 2)", DEFER_REFUSE=False, DONE_BY=0,
                MAX_ASKS=99, COALESCE=False, BLOCK_GATE=False, EXPIRY=False, INSTALL_LATE=False, EXPIRE_LATE=False, DROP_LATE=False,
                EXPIRE_DECODING=False, DECODE_CHECKS_EXPIRY=False, IDONTWANT_FIRST=False,
                NO_ASK_FILTER=False, LR_AT_DECISION=False, NO_WAKE_ON_TAKE=False, NO_WAKE_ON_LEAVE=False, ADV="Set()", ADV_MSGS=0, BAD_CODE=False, QMAX=99, EAGER_WRITERS=False,
                EQ="Set()", EQ_SWITCH=False, EQ_LATE=False, EQ_EXHAUST=False, EQ_UNPARK=False,
                DISC_MAX=0, DISC_LATE=False, DISC_AT=0, DISC_ADV=False, CLOSE_PROMISES_ON_DISC=False, REFUSE_OFFERS=False,
                RESYNC_ON_CONNECT=False, RESYNC_MINE=False, ROOT_TIED=False, NO_REASK_OPEN=False)
AB = dict(PROJECT_OFFERS=True, PARK_LAST_RESORT=True)     # the two candidate fixes
ALL = dict(PROJECT_OFFERS=True, PARK_LAST_RESORT=True, PROMISE_AT_WRITE=True, CLOSE_ON_DEFER=True, RETRY_CHECKS_EXPIRY=True)  # fixes A to E
# the fixes as revised (in v0.5): A′ = A + ADMIT_OFFERS; B′ = LAST_RESORT +
# OFFERS_DURABLE in place of B (its first form had OFFER_REPLACE: B2R); C′ = NO_ASK_BEFORE_INSTALL in
# place of C; D′ = D + EXPIRY_CLEANUP; E as is
A2 = dict(PROJECT_OFFERS=True, ADMIT_OFFERS=True)
B2 = dict(LAST_RESORT=True, OFFERS_DURABLE=True)
B2R = dict(LAST_RESORT=True, OFFER_REPLACE=True)
AB2 = dict(**A2, **B2)
REV = dict(**AB2, NO_ASK_BEFORE_INSTALL=True, RETRY_CHECKS_EXPIRY=True, EXPIRY_CLEANUP=True, PROMISE_AT_WRITE=True)
# the pick, v0.5's rules: the revised fixes and the additions for F7, F8 and F10; ROOT_TIED and
# NO_REASK_OPEN (F6) and RESYNC_ON_CONNECT (F9) are not in v0.5
PICK = dict(**REV, REFUSE_OFFERS=True, CLOSE_PROMISES_ON_DISC=True, DECODE_CHECKS_EXPIRY=True)
LIVE = dict(DONE_BY=600)   # eventual completion: quiet and complete by step 600 (traces of 800 steps)
LIVE_PULL = dict(DONE_BY=1000)   # four nodes that pull every chunk take longer (traces of 1,200 steps)
ORDER = list(DEFAULTS)

INSTANCES = [
    # name, comment, changes
    ("t3", "the triangle with the spec's R = 2: the source pushes every chunk to both peers", {}),
    ("t3r1", "the triangle with R = 1: each chunk is pushed once and announced once", dict(R=1)),
    ("t3r1w1", "R = 1 and one window slot", dict(R=1, W=1)),
    ("t3_fixa", "the triangle with candidate fix A", dict(PROJECT_OFFERS=True)),
    ("t3r1_fixa", "R = 1 with candidate fix A", dict(R=1, PROJECT_OFFERS=True)),
    ("t3r1_fixa_nopark", "R = 1, fix A, no park", dict(R=1, PROJECT_OFFERS=True, PARK=False)),
    ("t3_noproject", "the triangle without card 12", dict(PROJECT=False)),
    ("t3r1_noproject", "R = 1 without card 12", dict(R=1, PROJECT=False)),
    ("f4", "four nodes in a full mesh", dict(NN=4, MESH=FULL4)),
    ("f4_fixa", "four nodes, fix A", dict(NN=4, MESH=FULL4, PROJECT_OFFERS=True)),
    ("k4", "four nodes, node 3 hangs off node 2", dict(NN=4, MESH=KITE)),
    ("k4_fixa", "the kite with fix A", dict(NN=4, MESH=KITE, PROJECT_OFFERS=True)),
    ("k4_fixab", "the kite with fixes A and B", dict(NN=4, MESH=KITE, PROJECT_OFFERS=True, PARK_LAST_RESORT=True)),
    ("t3r1_fixab", "R = 1 with fixes A and B", dict(R=1, PROJECT_OFFERS=True, PARK_LAST_RESORT=True)),
    ("f4_fixab", "four nodes, fixes A and B", dict(NN=4, MESH=FULL4, PROJECT_OFFERS=True, PARK_LAST_RESORT=True)),
    ("k4_fixb", "the kite with fix B alone", dict(NN=4, MESH=KITE, PARK_LAST_RESORT=True)),
    # extensions, with both candidate fixes so that F1 and F2 do not mask what is looked for
    ("t3r1_coal", "a coalescing transport, the spec's handling order", dict(R=1, COALESCE=True, **AB)),
    ("f4_coal", "four nodes, a coalescing transport", dict(NN=4, MESH=FULL4, COALESCE=True, **AB)),
    ("t3r1_gate", "the block gate: chunks ahead of the block wait", dict(R=1, BLOCK_GATE=True, **AB)),
    ("f4_gate", "four nodes, the block gate", dict(NN=4, MESH=FULL4, BLOCK_GATE=True, **AB)),
    ("t3r0_gate", "the block gate, and a source that only announces (R = 0): every chunk is asked for",
     dict(R=0, BLOCK_GATE=True, **AB)),
    ("t3r1_gatelate", "the block gate, installed only once a chunk waits for it", dict(R=1, BLOCK_GATE=True, INSTALL_LATE=True, **AB)),
    ("t3r0_gatelate", "R = 0 and a late block", dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, **AB)),
    ("t3r1_expiry", "groups may expire at any node but the source, while an ask of theirs is out or queued",
     dict(R=1, EXPIRY=True, EXPIRE_LATE=True, **AB)),
    # one adversarial node: it answers, forwards and acknowledges nothing, and sends up to ADV_MSGS
    # announcements or HAVEs naming any chunks
    ("f4adv", "four nodes, node 3 adversarial, the spec", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3)),
    ("f4adv_ab", "four nodes, node 3 adversarial, fixes A and B", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, **AB)),
    ("k4adv_ab", "the kite, node 1 adversarial, fixes A and B", dict(NN=4, MESH=KITE, ADV="Set(1)", ADV_MSGS=3, **AB)),
    ("t3adv_ab", "the triangle, node 2 adversarial, fixes A and B", dict(ADV="Set(2)", ADV_MSGS=3, **AB)),
    ("f4adv_o1_ab", "four nodes, node 3 adversarial, offer table of one announcer (16 Sybils in small), fixes A and B",
     dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, OFFERS_MAX=1, **AB)),
    ("f4o1_ab", "four nodes, honest, offer table of one announcer, fixes A and B", dict(NN=4, MESH=FULL4, OFFERS_MAX=1, **AB)),
    # the builder committed a non-codeword: every decode fails and the group is dropped
    ("t3bad", "an inconsistent code, the triangle", dict(R=1, BAD_CODE=True, **AB)),
    ("f4bad", "an inconsistent code, four nodes", dict(NN=4, MESH=FULL4, BAD_CODE=True, **AB)),
    ("f4bad_noleavewake", "noLostWakeup: drop_group empties a waiting writer's queue, which leaves the line waking nobody",
     dict(NN=4, MESH=FULL4, BAD_CODE=True, NO_WAKE_ON_LEAVE=True, W=1, DROP_LATE=True, **AB)),
    # parking soundness: asks held behind the window, or dropped at a full queue
    ("f4w1_ab", "four nodes, one window slot, fixes A and B", dict(NN=4, MESH=FULL4, W=1, **AB)),
    ("f4q3_ab", "four nodes, queues of three entries, fixes A and B", dict(NN=4, MESH=FULL4, QMAX=3, **AB)),
    ("t3r1q2_ab", "the triangle with R = 1, queues of two entries, fixes A and B", dict(R=1, QMAX=2, **AB)),
    ("f4w1_abe", "one window slot, fixes A, B and E", dict(NN=4, MESH=FULL4, W=1, PROMISE_AT_WRITE=True, **AB)),
    ("f4q3_abe", "queues of three entries, fixes A, B and E", dict(NN=4, MESH=FULL4, QMAX=3, PROMISE_AT_WRITE=True, **AB)),
    ("t3r1q2_abe", "queues of two entries, fixes A, B, E and A'", dict(R=1, QMAX=2, PROMISE_AT_WRITE=True, FORGET_DROPPED=True, **AB)),
    # finite instances for exhaustive checks: at most two asks per chunk and node
    ("x3r1_ab", "R = 1, fixes A and B, two asks per chunk", dict(R=1, MAX_ASKS=2, **AB)),
    ("x3r1", "R = 1, the spec, two asks per chunk", dict(R=1, MAX_ASKS=2)),
    ("x3", "the spec's triangle, two asks per chunk", dict(MAX_ASKS=2)),
    ("x3_abe", "the triangle with fixes A, B and E, two asks per chunk", dict(MAX_ASKS=2, PROMISE_AT_WRITE=True, **AB)),
    ("x3_all", "the triangle with fixes A to E, two asks per chunk", dict(MAX_ASKS=2, **ALL)),
    ("x3k1", "the spec's triangle, K = 1, N = 2, R = 1, one slot, one ask per chunk", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1)),
    ("x3k1_all", "the same with fixes A to E", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, **ALL)),
    ("x3k1e", "x3k1 with eager writers", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True)),
    ("x3k1e_all", "x3k1_all with eager writers", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, **ALL)),
    ("x3k1e_noaskfilter", "known answer for TLC: x3k1e without the writer's ask filter", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, NO_ASK_FILTER=True)),
    ("x3k1e_unpaced", "known answer for TLC: x3k1e with the source's HAVE unpaced", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, PACED_SRC_HAVE=False)),
    ("x3e", "the spec's triangle (K = 2), eager writers, two asks per chunk", dict(MAX_ASKS=2, EAGER_WRITERS=True)),
    ("x3e_all", "the same with fixes A to E", dict(MAX_ASKS=2, EAGER_WRITERS=True, **ALL)),
    ("x3e_noaskfilter", "known answer for TLC: x3e without the writer's ask filter", dict(MAX_ASKS=2, EAGER_WRITERS=True, NO_ASK_FILTER=True)),
    ("x3r1e_noaskfilter", "known answer for TLC: R = 1, eager, without the writer's ask filter", dict(R=1, MAX_ASKS=2, EAGER_WRITERS=True, NO_ASK_FILTER=True)),
    ("x4ke_all", "the kite, fixes A to E, eager writers, two asks per chunk", dict(NN=4, MESH=KITE, MAX_ASKS=2, EAGER_WRITERS=True, **ALL)),
    ("x4ke_a", "the kite, fix A only, eager writers, two asks per chunk (F2 expected)", dict(NN=4, MESH=KITE, MAX_ASKS=2, EAGER_WRITERS=True, PROJECT_OFFERS=True)),
    # every candidate fix, A to E
    ("t3_all", "the triangle, fixes A to E", dict(**ALL)),
    ("t3e_all", "the triangle, fixes A to E, eager writers", dict(EAGER_WRITERS=True, **ALL)),
    ("t3e", "the triangle, eager writers", dict(EAGER_WRITERS=True)),
    ("k4_all", "the kite, fixes A to E", dict(NN=4, MESH=KITE, **ALL)),
    ("f4_all", "four nodes, fixes A to E", dict(NN=4, MESH=FULL4, **ALL)),
    ("f4adv_all", "four nodes, one adversary, fixes A to E", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, **ALL)),
    ("t3r0_gatelate_all", "the late block, fixes A to E", dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, **ALL)),
    ("t3r1_expiry_all", "expiry while an ask is out or queued, fixes A to E", dict(R=1, EXPIRY=True, EXPIRE_LATE=True, **ALL)),
    ("f4w1_all", "one window slot, fixes A to E", dict(NN=4, MESH=FULL4, W=1, **ALL)),
    ("f4bad_all", "an inconsistent code, fixes A to E", dict(NN=4, MESH=FULL4, BAD_CODE=True, **ALL)),
    # known answers: each must break the property named
    ("t3r1_coal_dwfirst", "noPenalty: a coalescing transport and IDONTWANT handled before IWANT",
     dict(R=1, COALESCE=True, IDONTWANT_FIRST=True, **AB)),
    ("t3r1_noaskfilter", "noStaleAsk (and maybe noPenalty): the writer keeps asks for chunks it has since received",
     dict(R=1, NO_ASK_FILTER=True, PROJECT_OFFERS=True)),
    ("f4_nowake", "noLostWakeup: a writer that takes a slot wakes nobody while slots remain",
     dict(NN=4, MESH=FULL4, NO_WAKE_ON_TAKE=True, PROJECT_OFFERS=True)),
    ("f4_noleavewake", "noLostWakeup: a writer that leaves the line wakes nobody",
     dict(NN=4, MESH=FULL4, NO_WAKE_ON_LEAVE=True, PROJECT_OFFERS=True)),
    ("t3_unpaced", "p4: the source's HAVE names every chunk from the start", dict(PACED_SRC_HAVE=False, PROJECT_OFFERS=True)),
    # the revised fixes, A′ to D′ and E, on the shapes the first five were checked on
    ("t3_a2", "the triangle, fix A′ alone", dict(**A2)),
    ("k4_a2", "the kite, fix A′ alone (F2 expected)", dict(NN=4, MESH=KITE, **A2)),
    ("k4_ab2", "the kite, fixes A′ and B′", dict(NN=4, MESH=KITE, **AB2, **LIVE)),
    ("t3_rev", "the triangle, the revised fixes", dict(**REV, **LIVE)),
    ("k4_rev", "the kite, the revised fixes", dict(NN=4, MESH=KITE, **REV, **LIVE)),
    ("f4_rev", "four nodes, the revised fixes", dict(NN=4, MESH=FULL4, **REV, **LIVE)),
    ("f4adv_rev", "four nodes, one adversary, the revised fixes", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, **REV, **LIVE)),
    ("f4w1_rev", "one window slot, the revised fixes", dict(NN=4, MESH=FULL4, W=1, **REV, **LIVE)),
    ("t3r0_gatelate_rev", "the late block, R = 0, the revised fixes", dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, **REV, **LIVE)),
    ("f4_gate_rev", "four nodes, the block gate, the revised fixes", dict(NN=4, MESH=FULL4, BLOCK_GATE=True, **REV, **LIVE)),
    ("t3r1_expiry_rev", "expiry while an ask is out or queued, the revised fixes", dict(R=1, EXPIRY=True, EXPIRE_LATE=True, **REV)),
    ("t3r1_expiry_any_rev", "expiry at any time, the revised fixes", dict(R=1, EXPIRY=True, **REV)),
    ("f4bad_rev", "an inconsistent code, the revised fixes", dict(NN=4, MESH=FULL4, BAD_CODE=True, **REV)),
    ("t3r1_coal_rev", "a coalescing transport, the revised fixes", dict(R=1, COALESCE=True, **REV, **LIVE)),
    # cases that break the first fixes, where the revised ones must hold
    # forged copies (C trusts a waiting copy by index): node 2 forges, node 1 pulls everything (R = 0);
    # N = K = 2, so that one index kept from node 1 stalls it
    ("t3r0adv_forge_all", "R = 0, N = K = 2, node 2 forges chunks, fixes A to E", dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, **ALL)),
    ("t3r0adv_forge_rev", "the same, the revised fixes", dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, **REV, **LIVE)),
    ("t3r0adv_forge_n4_rev", "R = 0, N = 4, node 2 forges chunks, the revised fixes", dict(R=0, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, **REV, **LIVE)),
    ("t3r0adv_forge_gatelate_all", "R = 0, N = K = 2, node 2 forges, a late block: a forgery fails level 1 at installation, fixes A to E",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, BLOCK_GATE=True, INSTALL_LATE=True, **ALL)),
    ("t3r0adv_forge_gatelate_rev", "the same, the revised fixes",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, BLOCK_GATE=True, INSTALL_LATE=True, **REV, **LIVE)),
    ("f4adv_forge_ab2", "four nodes, node 3 forges chunks, fixes A′ and B′ (the spec's handling of forgeries)",
     dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, ADV_FORGE=True, **AB2)),
    ("f4adv_forge_rev", "four nodes, node 3 forges chunks, the revised fixes", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, ADV_FORGE=True, **REV, **LIVE)),
    # a refused reservation: C closes promises only when the copy is kept
    ("t3r0_gatelate_refuse_all", "the late block, a deferred store that may refuse, fixes A to E",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **ALL)),
    ("t3r0_gatelate_refuse_rev", "the same, the revised fixes", dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **REV, **LIVE)),
    # a captured offer table and a node that only pulls (no pushes: R = 0, R_NODE = 1, no repair)
    ("f4pull", "four nodes that only pull, the spec", dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False)),
    ("f4pull_rev", "four nodes that only pull, the revised fixes", dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, **REV, **LIVE_PULL)),
    ("f4adv_o1_pull_ab", "pull only, node 3 announces and withholds, one announcer per chunk, fixes A and B",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, OFFERS_MAX=1, **AB, **LIVE_PULL)),
    ("f4adv_o1_pull_ab2", "the same, fixes A′ and B′",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, OFFERS_MAX=1, **AB2, **LIVE_PULL)),
    ("f4adv_o1_pull_rev", "the same, the revised fixes",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, OFFERS_MAX=1, **REV, **LIVE_PULL)),
    ("f4adv_pull_ab", "pull only, node 3 announces and withholds, fixes A and B (the unbounded last resort)",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, **AB, **LIVE_PULL)),
    ("f4adv_o1_pull_b2r", "the captured table, fixes A′ and B′'s first form (replacement, not durable offers)",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, OFFERS_MAX=1, **A2, **B2R, **LIVE_PULL)),
    # cases that break drafts of the revision: a captured table before the block (C′ asks nobody, so replacement
    # finds no entry already asked), a last-resort ask refused at a full queue, a forgery that fails
    # level 1 at installation alone
    ("t3r0gate_o1adv_b2r", "R = 0, late block, one announcer per chunk, node 2 withholds, B′'s first form",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, OFFERS_MAX=1, ADV="Set(2)", ADV_MSGS=3,
          **A2, **B2R, NO_ASK_BEFORE_INSTALL=True, RETRY_CHECKS_EXPIRY=True, EXPIRY_CLEANUP=True, PROMISE_AT_WRITE=True, **LIVE)),
    ("t3r0gate_o1adv_rev", "the same, the revised fixes (durable offers)",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, OFFERS_MAX=1, ADV="Set(2)", ADV_MSGS=3, **REV, **LIVE)),
    ("k4q2_rev", "the kite, queues of two entries, the revised fixes: a last-resort ask may be refused",
     dict(NN=4, MESH=KITE, QMAX=2, **REV, **LIVE)),
    ("k4q2_rev_lrdecide", "known answer: the same, the last resort counted when decided",
     dict(NN=4, MESH=KITE, QMAX=2, LR_AT_DECISION=True, **REV, **LIVE)),
    ("t3r0adv_forge_gatelate_bp_all", "R = 0, N = K = 2, a late block, node 2 forges chunks that fail their proof, fixes A to E",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, FORGE_KINDS="Set(1)", BLOCK_GATE=True, INSTALL_LATE=True, **ALL)),
    ("t3r0adv_forge_gatelate_bp_rev", "the same, the revised fixes",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, FORGE_KINDS="Set(1)", BLOCK_GATE=True, INSTALL_LATE=True, **REV, **LIVE)),
    ("f4adv_pull_ab2", "the same, fixes A′ and B′",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, **AB2, **LIVE_PULL)),
    ("f4adv_pull_rev", "the same, the revised fixes",
     dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3, **REV, **LIVE_PULL)),
    # equivocation: node 2 (in the kite node 3, in four nodes node 3) installed the proposer's other
    # block, whose bid commits the same group; honest chunks name the builder's block and wait there.
    # With C′ it still asks; its providers' answers wait and they are parked (C′'s residual). With
    # EQ_SWITCH it installs the builder's block later, once it has parked a provider (EQ_LATE)
    ("t3eq_rev", "equivocation: node 2 on the other block, switching later, the revised fixes",
     dict(EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, **REV, **LIVE)),
    ("t3r0eq_rev", "the same with R = 0: node 2 gets every chunk by asking",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, **REV, **LIVE)),
    ("t3r0eq_refuse_rev", "the same, a deferred store that may refuse",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, **REV, **LIVE)),
    ("t3r0eq_nob", "known answer: the same without B′: the switching node's providers are all parked",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, **A2, NO_ASK_BEFORE_INSTALL=True,
          RETRY_CHECKS_EXPIRY=True, EXPIRY_CLEANUP=True, PROMISE_AT_WRITE=True, **LIVE)),
    ("t3r0eq_refuse_nob", "known answer: the refusing store without B′: the switched node's providers are all parked",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, **A2, NO_ASK_BEFORE_INSTALL=True,
          RETRY_CHECKS_EXPIRY=True, EXPIRY_CLEANUP=True, PROMISE_AT_WRITE=True, **LIVE)),
    # the candidate addition: a block's installation lifts its group's parks and B′'s counts
    ("t3r0eq_refuse_unpark", "the refusing store with the revised fixes and EQ_UNPARK",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, **REV, **LIVE)),
    ("t3eq_refuse_unpark", "the same with R = 2", dict(EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, **REV, **LIVE)),
    ("k4eq_refuse_unpark", "the kite, node 3 on the other block, a refusing store, EQ_UNPARK",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, **REV, **LIVE)),
    ("f4eq_refuse_unpark", "four nodes, nodes 2 and 3 on the other block, a refusing store, EQ_UNPARK",
     dict(NN=4, MESH=FULL4, EQ="Set(2, 3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, **REV, **LIVE)),
    ("t3r0adv_forge_gatelate_unpark", "forged chunks and a late block, the revised fixes and EQ_UNPARK",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, BLOCK_GATE=True, INSTALL_LATE=True, EQ_UNPARK=True, **REV, **LIVE)),
    ("t3r0_gatelate_refuse_unpark", "a late block and a refusing store, the revised fixes and EQ_UNPARK",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, **REV, **LIVE)),
    # a push the deferred store refuses is lost under C′: its sender counted it, the ledger has no offer
    ("k4gatelate_refuse_rev", "the kite, a late block, a refusing store, the revised fixes (node 3's only peer pushed)",
     dict(NN=4, MESH=KITE, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **REV, **LIVE)),
    ("k4gatelate_refuse_ro", "the same with REFUSE_OFFERS: a refused copy records its sender's offer",
     dict(NN=4, MESH=KITE, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    ("t3r0_gatelate_refuse_ro", "the triangle, R = 0, a late block, a refusing store, REFUSE_OFFERS",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    ("k4eq_refuse_both", "the kite, node 3 on the other block, a refusing store, EQ_UNPARK and REFUSE_OFFERS",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    ("t3r0eq_refuse_both", "the triangle, R = 0, node 2 on the other block, a refusing store, both additions",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    ("k4eq2_refuse_both", "the kite, node 2 (node 3's only peer) on the other block, a refusing store, both additions",
     dict(NN=4, MESH=KITE, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    ("f4eq_refuse_both", "four nodes, nodes 2 and 3 on the other block, a refusing store, both additions (1,000 steps)",
     dict(NN=4, MESH=FULL4, EQ="Set(2, 3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, EQ_UNPARK=True, REFUSE_OFFERS=True, **REV, **LIVE_PULL)),
    ("t3r0adv_forge_gatelate_both", "forged chunks, a late block, a refusing store, the revised fixes and both additions",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True,
          EQ_UNPARK=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    ("f4eq_rev_long", "four nodes, nodes 2 and 3 on the other block, the revised fixes (1,000 steps)",
     dict(NN=4, MESH=FULL4, EQ="Set(2, 3)", EQ_SWITCH=True, EQ_LATE=True, **REV, **LIVE_PULL)),
    ("k4eq_refuse_rev", "the kite, node 3 on the other block, a refusing store, the revised fixes",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, **REV, **LIVE)),
    ("t3eq_nosw_rev", "node 2 on the other block for good: node 1 completes, node 2 cannot",
     dict(EQ="Set(2)", **REV, **LIVE)),
    ("k4eq_rev", "the kite, node 3 (one peer) on the other block, switching later, the revised fixes",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, **REV, **LIVE)),
    ("k4eq2_rev", "the kite, node 2 (node 3's only peer) on the other block, switching later",
     dict(NN=4, MESH=KITE, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, **REV, **LIVE)),
    ("f4eq_rev", "four nodes, nodes 2 and 3 on the other block, switching later, the revised fixes",
     dict(NN=4, MESH=FULL4, EQ="Set(2, 3)", EQ_SWITCH=True, EQ_LATE=True, **REV, **LIVE)),
    # disconnects: a connection between two honest nodes closes and a new one opens at once, while a
    # promise between them is open (DISC_LATE); what was on the link is lost
    ("t3disc_rev", "the triangle, one disconnect, the revised fixes", dict(DISC_MAX=1, DISC_LATE=True, **REV, **LIVE)),
    ("t3disc_cp_rev", "the same, promises closing with their connection", dict(DISC_MAX=1, DISC_LATE=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("t3r0disc_rev", "R = 0 (every chunk asked for), one disconnect, the revised fixes", dict(R=0, DISC_MAX=1, DISC_LATE=True, **REV, **LIVE)),
    ("t3r0disc_cp_rev", "the same, promises closing with their connection", dict(R=0, DISC_MAX=1, DISC_LATE=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("t3disc_any_rev", "the triangle, two disconnects at any time, the revised fixes", dict(DISC_MAX=2, **REV, **LIVE)),
    ("f4disc_rev", "four nodes, two disconnects, the revised fixes", dict(NN=4, MESH=FULL4, DISC_MAX=2, DISC_LATE=True, **REV, **LIVE)),
    ("k4disc_rev", "the kite, one disconnect, the revised fixes", dict(NN=4, MESH=KITE, DISC_MAX=1, DISC_LATE=True, **REV, **LIVE)),
    ("f4w1disc_rev", "four nodes, one window slot, two disconnects at any time, the revised fixes", dict(NN=4, MESH=FULL4, W=1, DISC_MAX=2, **REV, **LIVE)),
    # the candidate additions for disconnects: promises close with their connection, and a new
    # connection gets each side's offer of what it holds
    ("t3disc_any_rs", "two disconnects at any time, the revised fixes and RESYNC_ON_CONNECT", dict(DISC_MAX=2, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("t3disc_any_both", "the same with promises closing with their connection too",
     dict(DISC_MAX=2, RESYNC_ON_CONNECT=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("k4disc_both", "the kite, one disconnect, both disconnect additions",
     dict(NN=4, MESH=KITE, DISC_MAX=1, DISC_LATE=True, RESYNC_ON_CONNECT=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("k4disc_any_both", "the kite, two disconnects at any time, both disconnect additions",
     dict(NN=4, MESH=KITE, DISC_MAX=2, RESYNC_ON_CONNECT=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("f4disc_both", "four nodes, two disconnects, both disconnect additions",
     dict(NN=4, MESH=FULL4, DISC_MAX=2, DISC_LATE=True, RESYNC_ON_CONNECT=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("f4w1disc_both", "four nodes, one slot, two disconnects at any time, both disconnect additions",
     dict(NN=4, MESH=FULL4, W=1, DISC_MAX=2, RESYNC_ON_CONNECT=True, CLOSE_PROMISES_ON_DISC=True, **REV, **LIVE)),
    ("t3disc_spec", "the triangle as written (no fixes), one disconnect", dict(DISC_MAX=1, DISC_LATE=True)),
    # the resync from what a node can serve, at its
    # boundaries (while decoding, after a bad code, before the source's first write, after expiry);
    # RESYNC_MINE is its first form, from the decode claim
    ("t3disc_dec_rsmine", "known answer: a close while one side decodes, the resync's first form (the decode claim)",
     dict(DISC_MAX=1, DISC_AT=1, RESYNC_ON_CONNECT=True, RESYNC_MINE=True, **REV, **LIVE)),
    ("t3disc_dec_rs", "a close while one side decodes, the resync from what it can serve",
     dict(DISC_MAX=1, DISC_AT=1, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("t3r1baddisc_rsmine", "known answer: an inconsistent code, a close once a node has dropped the group, the first form",
     dict(R=1, BAD_CODE=True, DISC_MAX=1, DISC_AT=2, RESYNC_ON_CONNECT=True, RESYNC_MINE=True, **REV)),
    ("t3r1baddisc_rs", "the same, the resync from what it can serve", dict(R=1, BAD_CODE=True, DISC_MAX=1, DISC_AT=2, RESYNC_ON_CONNECT=True, **REV)),
    ("t3disc_src_rev", "the source's connections close before it has written a chunk, the revised fixes (F9)",
     dict(DISC_MAX=2, DISC_AT=3, **REV, **LIVE)),
    ("t3disc_src_rs", "the same with the resync: the source announces every chunk (its HAVE stays paced, P4)",
     dict(DISC_MAX=2, DISC_AT=3, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("t3r1_expiry_disc_rs", "expiry while an ask is out, closes once a group has expired, the resync",
     dict(R=1, EXPIRY=True, EXPIRE_LATE=True, DISC_MAX=2, DISC_AT=4, RESYNC_ON_CONNECT=True, **REV)),
    ("t3r1_expiry_disc_rsmine", "the same, the first form", dict(R=1, EXPIRY=True, EXPIRE_LATE=True, DISC_MAX=2, DISC_AT=4,
     RESYNC_ON_CONNECT=True, RESYNC_MINE=True, **REV)),
    # the root-tied recovery (ROOT_TIED) in place of EQ_UNPARK and REFUSE_OFFERS: a copy that waits ties
    # its sender to the root it names, for its index (its promise closes, it is not asked for the index
    # meanwhile); the root's installation releases the ties (unpark, B′'s count, an offer, the ask)
    ("t3r0eq_refuse_rt", "the triangle, R = 0, node 2 on the other block, a refusing store, ROOT_TIED",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("t3eq_refuse_rt", "the same with R = 2", dict(EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("t3r0eq_refuse_rt_any", "R = 0, node 2 on the other block, switching at any time, a refusing store, ROOT_TIED",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("t3eq_rt", "node 2 on the other block, a store that keeps everything, ROOT_TIED", dict(EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("k4eq_refuse_rt", "the kite, node 3 on the other block, a refusing store, ROOT_TIED",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("k4eq2_refuse_rt", "the kite, node 2 (node 3's only peer) on the other block, a refusing store, ROOT_TIED",
     dict(NN=4, MESH=KITE, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("f4eq_refuse_rt", "four nodes, nodes 2 and 3 on the other block, a refusing store, ROOT_TIED (1,000 steps)",
     dict(NN=4, MESH=FULL4, EQ="Set(2, 3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE_PULL)),
    ("k4gatelate_refuse_rt", "the kite, a late block, a refusing store, ROOT_TIED (F7 without equivocation)",
     dict(NN=4, MESH=KITE, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("t3r0_gatelate_refuse_rt", "the triangle, R = 0, a late block, a refusing store, ROOT_TIED",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("t3r0adv_forge_gatelate_rt", "forged chunks, a late block, a refusing store, ROOT_TIED",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True,
          ROOT_TIED=True, **REV, **LIVE)),
    ("f4adv_forge_eq_rt", "four nodes, node 2 on the other block, node 3 forges, a refusing store, ROOT_TIED",
     dict(NN=4, MESH=FULL4, EQ="Set(2)", EQ_SWITCH=True, ADV="Set(3)", ADV_MSGS=3, ADV_FORGE=True, DEFER_REFUSE=True,
          ROOT_TIED=True, **REV, **LIVE)),
    ("t3r0_gatelate_rt_noc", "the late block, R = 0, a refusing store, ROOT_TIED with A′, B′, D′, E but not C′ (asks before the block)",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, ROOT_TIED=True, **AB2, RETRY_CHECKS_EXPIRY=True,
          EXPIRY_CLEANUP=True, PROMISE_AT_WRITE=True, **LIVE)),
    # F7 is the spec's as written too: no C′ (A′, B′, D′, E, so that F1 and F2 do not mask it)
    ("k4gatelate_refuse_noc", "the kite, a late block, a refusing store, A′, B′, D′, E without C′",
     dict(NN=4, MESH=KITE, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **AB2, RETRY_CHECKS_EXPIRY=True,
          EXPIRY_CLEANUP=True, PROMISE_AT_WRITE=True, **LIVE)),
    # a directed case for EQ_UNPARK (EQ_EXHAUST): the kite with N = K = 2, node 3 (one peer)
    # on the other block, a refusing store; the switch once node 2's three answers for a chunk node 3
    # lacks are spent
    ("k4n2eqx_unpark", "N = K = 2, node 3 on the other block, the switch with answers spent, EQ_UNPARK and REFUSE_OFFERS",
     dict(NN=4, MESH=KITE, N=2, EQ="Set(3)", EQ_SWITCH=True, EQ_EXHAUST=True, DEFER_REFUSE=True, EQ_UNPARK=True,
          REFUSE_OFFERS=True, **REV, **LIVE)),
    ("k4n2eqx_rt", "the same, ROOT_TIED", dict(NN=4, MESH=KITE, N=2, EQ="Set(3)", EQ_SWITCH=True, EQ_EXHAUST=True,
     DEFER_REFUSE=True, ROOT_TIED=True, **REV, **LIVE)),
    ("k4n2eqx_rtnr", "the same, ROOT_TIED and NO_REASK_OPEN", dict(NN=4, MESH=KITE, N=2, EQ="Set(3)", EQ_SWITCH=True,
     EQ_EXHAUST=True, DEFER_REFUSE=True, ROOT_TIED=True, NO_REASK_OPEN=True, **REV, **LIVE)),
    ("k4n2eqx_unparknr", "the same, EQ_UNPARK, REFUSE_OFFERS and NO_REASK_OPEN", dict(NN=4, MESH=KITE, N=2, EQ="Set(3)",
     EQ_SWITCH=True, EQ_EXHAUST=True, DEFER_REFUSE=True, EQ_UNPARK=True, REFUSE_OFFERS=True, NO_REASK_OPEN=True, **REV, **LIVE)),
    ("t3r0n2eqx_rtnr", "the triangle, R = 0, N = K = 2, node 2 on the other block, the switch with answers spent, ROOT_TIED and NO_REASK_OPEN",
     dict(R=0, N=2, EQ="Set(2)", EQ_SWITCH=True, EQ_EXHAUST=True, DEFER_REFUSE=True, ROOT_TIED=True, NO_REASK_OPEN=True, **REV, **LIVE)),
    ("t3r0n2eqx_unpark", "the same, EQ_UNPARK and REFUSE_OFFERS",
     dict(R=0, N=2, EQ="Set(2)", EQ_SWITCH=True, EQ_EXHAUST=True, DEFER_REFUSE=True, EQ_UNPARK=True, REFUSE_OFFERS=True, **REV, **LIVE)),
    # NO_REASK_OPEN on the shapes the revision was checked on
    ("t3_rev_nr", "the triangle, the revised fixes and NO_REASK_OPEN", dict(NO_REASK_OPEN=True, **REV, **LIVE)),
    ("k4_rev_nr", "the kite, the same", dict(NN=4, MESH=KITE, NO_REASK_OPEN=True, **REV, **LIVE)),
    ("f4adv_rev_nr", "four nodes, one withholder, the same", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, NO_REASK_OPEN=True, **REV, **LIVE)),
    ("f4pull_rev_nr", "four nodes that only pull, the same", dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, NO_REASK_OPEN=True, **REV, **LIVE_PULL)),
    ("k4q2_rev_nr", "the kite, queues of two, the same", dict(NN=4, MESH=KITE, QMAX=2, NO_REASK_OPEN=True, **REV, **LIVE)),
    ("f4w1_rev_nr", "one window slot, the same", dict(NN=4, MESH=FULL4, W=1, NO_REASK_OPEN=True, **REV, **LIVE)),
    # equivocation and disconnects together, ungated, with every addition: the revised set (ROOT_TIED,
    # NO_REASK_OPEN, CLOSE_PROMISES_ON_DISC, RESYNC_ON_CONNECT) and the first forms
    # (EQ_UNPARK, REFUSE_OFFERS, CLOSE_PROMISES_ON_DISC, RESYNC_ON_CONNECT)
    ("t3r0eqdisc_new", "R = 0, node 2 on the other block, switching at any time, two closes at any time, a refusing store, the revised additions",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, DEFER_REFUSE=True, DISC_MAX=2, ROOT_TIED=True, NO_REASK_OPEN=True,
          CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("t3eqdisc_new", "the same with R = 2", dict(EQ="Set(2)", EQ_SWITCH=True, DEFER_REFUSE=True, DISC_MAX=2, ROOT_TIED=True,
     NO_REASK_OPEN=True, CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("k4eqdisc_new", "the kite, node 3 on the other block, switching at any time, two closes at any time, a refusing store, the revised additions",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, DEFER_REFUSE=True, DISC_MAX=2, ROOT_TIED=True, NO_REASK_OPEN=True,
          CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("k4eqlatedisc_new", "the kite, node 3 on the other block, switching late (EQ_LATE), closes while a promise is open, the revised additions",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, DISC_MAX=2, DISC_LATE=True, ROOT_TIED=True,
          NO_REASK_OPEN=True, CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("f4eqdisc_adv_new", "four nodes: node 2 on the other block, node 3 forges and its connections close too, queues of three, a refusing store, the revised additions",
     dict(NN=4, MESH=FULL4, EQ="Set(2)", EQ_SWITCH=True, ADV="Set(3)", ADV_MSGS=3, ADV_FORGE=True, DEFER_REFUSE=True, QMAX=3,
          DISC_MAX=2, DISC_ADV=True, ROOT_TIED=True, NO_REASK_OPEN=True, CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("t3r0eqdisc_old", "R = 0, node 2 on the other block, switching at any time, two closes at any time, a refusing store, the additions' first forms",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, DEFER_REFUSE=True, DISC_MAX=2, EQ_UNPARK=True, REFUSE_OFFERS=True,
          CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("k4eqdisc_old", "the kite, node 3 on the other block, switching at any time, two closes at any time, a refusing store, the additions' first forms",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, DEFER_REFUSE=True, DISC_MAX=2, EQ_UNPARK=True, REFUSE_OFFERS=True,
          CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    # a withholder whose connection closes while its promise is open, so it is never parked (CLOSE_PROMISES_ON_DISC)
    ("f4adv_disc_cp", "four nodes, node 3 withholds and its connections close while a promise is open, both disconnect additions",
     dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, DISC_MAX=2, DISC_LATE=True, DISC_ADV=True, CLOSE_PROMISES_ON_DISC=True,
          RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("f4pulladv_disc_cp", "the same, nodes that only pull", dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3,
     DISC_MAX=2, DISC_LATE=True, DISC_ADV=True, CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE_PULL)),
    # the same with every close a withholder's
    # connection while it owes an answer (DISC_AT = 5), so the rows witness the case they name
    ("f4adv_disc_cpw", "four nodes, every close a connection of the withholder's while it owes an answer, both disconnect additions",
     dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, DISC_MAX=2, DISC_LATE=True, DISC_ADV=True, DISC_AT=5,
          CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE)),
    ("f4pulladv_disc_cpw", "the same, nodes that only pull", dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, ADV="Set(3)", ADV_MSGS=3,
     DISC_MAX=2, DISC_LATE=True, DISC_ADV=True, DISC_AT=5, CLOSE_PROMISES_ON_DISC=True, RESYNC_ON_CONNECT=True, **REV, **LIVE_PULL)),
    # F10: a decode that outlives its group (the spec bounds no decode's duration); expiry only while
    # the group decodes, and the candidate check that drops such a decode
    ("t3r1_expiry_dec_rev", "a group expires while it decodes, the revised fixes", dict(R=1, EXPIRY=True, EXPIRE_DECODING=True, **REV)),
    ("t3r1_expiry_dec_chk", "the same, a decode that returns after the expiry dropped (DECODE_CHECKS_EXPIRY)",
     dict(R=1, EXPIRY=True, EXPIRE_DECODING=True, DECODE_CHECKS_EXPIRY=True, **REV)),
    ("t3_expiry_dec_chk", "the same at R = 2", dict(EXPIRY=True, EXPIRE_DECODING=True, DECODE_CHECKS_EXPIRY=True, **REV)),
    ("f4_expiry_dec_chk", "four nodes, the same", dict(NN=4, MESH=FULL4, EXPIRY=True, EXPIRE_DECODING=True, DECODE_CHECKS_EXPIRY=True, **REV)),
    # the second verify round: F10 as the sweep first found it, with closes once a group has expired
    # and the resync, the check off and on
    ("t3r1_expiry_dec_disc_rs", "a group expires while it decodes, then closes and the resync, the revised fixes",
     dict(R=1, EXPIRY=True, EXPIRE_DECODING=True, DISC_MAX=2, DISC_AT=4, RESYNC_ON_CONNECT=True, **REV)),
    ("t3r1_expiry_dec_disc_chk", "the same with DECODE_CHECKS_EXPIRY",
     dict(R=1, EXPIRY=True, EXPIRE_DECODING=True, DECODE_CHECKS_EXPIRY=True, DISC_MAX=2, DISC_AT=4, RESYNC_ON_CONNECT=True, **REV)),
    # equivocation, ungated: the switch at any time (no EQ_LATE)
    ("t3eq_rev_any", "node 2 on the other block, switching at any time, the revised fixes", dict(EQ="Set(2)", EQ_SWITCH=True, **REV, **LIVE)),
    ("t3r0eq_refuse_rev_any", "R = 0, a refusing store, switching at any time, the revised fixes",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, DEFER_REFUSE=True, **REV, **LIVE)),
    # queues that refuse entries: A′ owes what a refused push or announcement named
    ("t3r1q2_rev", "the triangle with R = 1, queues of two entries, the revised fixes", dict(R=1, QMAX=2, **REV, **LIVE)),
    ("f4q3_rev", "four nodes, queues of three entries, the revised fixes", dict(NN=4, MESH=FULL4, QMAX=3, **REV, **LIVE)),
    # the pick together: the revision's shapes, where its additions act (a refusing store, closes,
    # expiry while decoding), and where a finding v0.5 does not fix should still show (F6, F9)
    ("t3_pick", "the triangle, the pick", dict(**PICK, **LIVE)),
    ("k4_pick", "the kite, the pick", dict(NN=4, MESH=KITE, **PICK, **LIVE)),
    ("f4adv_pick", "four nodes, one adversary, the pick", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, **PICK, **LIVE)),
    ("f4w1_pick", "one window slot, the pick", dict(NN=4, MESH=FULL4, W=1, **PICK, **LIVE)),
    ("f4pull_pick", "four nodes that only pull, the pick", dict(NN=4, MESH=FULL4, R=0, R_NODE=1, REPAIR=False, **PICK, **LIVE_PULL)),
    ("t3r1_coal_pick", "a coalescing transport, the pick", dict(R=1, COALESCE=True, **PICK, **LIVE)),
    ("k4q2_pick", "the kite, queues of two entries, the pick", dict(NN=4, MESH=KITE, QMAX=2, **PICK, **LIVE)),
    ("f4q3_pick", "four nodes, queues of three entries, the pick", dict(NN=4, MESH=FULL4, QMAX=3, **PICK, **LIVE)),
    ("t3r0_gatelate_refuse_pick", "the late block, R = 0, a refusing store, the pick",
     dict(R=0, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    ("k4gatelate_refuse_pick", "the kite, a late block, a refusing store (F7), the pick",
     dict(NN=4, MESH=KITE, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    ("t3r0adv_forge_gatelate_refuse_pick", "forged chunks, a late block, a refusing store, the pick",
     dict(R=0, N=2, ADV="Set(2)", ADV_MSGS=3, ADV_FORGE=True, BLOCK_GATE=True, INSTALL_LATE=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    ("f4adv_forge_pick", "four nodes, node 3 forges chunks, the pick", dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, ADV_FORGE=True, **PICK, **LIVE)),
    ("t3disc_pick", "the triangle, one close while a promise is open, the pick", dict(DISC_MAX=1, DISC_LATE=True, **PICK, **LIVE)),
    ("f4disc_pick", "four nodes, two closes while promises are open, the pick", dict(NN=4, MESH=FULL4, DISC_MAX=2, DISC_LATE=True, **PICK, **LIVE)),
    ("t3disc_any_pick", "the triangle, two closes at any time, the pick (F9: no resync in v0.5)", dict(DISC_MAX=2, **PICK, **LIVE)),
    ("f4adv_disc_cpw_pick", "four nodes, every close a connection of the withholder's while it owes an answer, the pick",
     dict(NN=4, MESH=FULL4, ADV="Set(3)", ADV_MSGS=3, DISC_MAX=2, DISC_LATE=True, DISC_ADV=True, DISC_AT=5, **PICK, **LIVE)),
    ("t3r1_expiry_pick", "expiry while an ask is out or queued, the pick", dict(R=1, EXPIRY=True, EXPIRE_LATE=True, **PICK)),
    ("t3r1_expiry_dec_pick", "a group expires while it decodes, the pick", dict(R=1, EXPIRY=True, EXPIRE_DECODING=True, **PICK)),
    ("f4_expiry_dec_pick", "four nodes, a group expires while it decodes, the pick",
     dict(NN=4, MESH=FULL4, EXPIRY=True, EXPIRE_DECODING=True, **PICK)),
    ("f4bad_pick", "an inconsistent code, the pick", dict(NN=4, MESH=FULL4, BAD_CODE=True, **PICK)),
    ("t3eq_pick", "equivocation: node 2 on the other block, switching later, the pick", dict(EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, **PICK, **LIVE)),
    ("k4eq_pick", "the kite, node 3 on the other block, switching later, the pick",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, **PICK, **LIVE)),
    ("t3r0eq_refuse_pick", "R = 0, node 2 on the other block, a refusing store, switching late, the pick (F6)",
     dict(R=0, EQ="Set(2)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    ("k4eq_refuse_pick", "the kite, node 3 on the other block, a refusing store, switching late, the pick",
     dict(NN=4, MESH=KITE, EQ="Set(3)", EQ_SWITCH=True, EQ_LATE=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    ("k4n2eqx_pick", "N = K = 2, node 3 on the other block, the switch with answers spent, the pick",
     dict(NN=4, MESH=KITE, N=2, EQ="Set(3)", EQ_SWITCH=True, EQ_EXHAUST=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    ("t3r0n2eqx_pick", "the triangle, N = K = 2, R = 0, node 2 on the other block, answers spent, the pick",
     dict(R=0, N=2, EQ="Set(2)", EQ_SWITCH=True, EQ_EXHAUST=True, DEFER_REFUSE=True, **PICK, **LIVE)),
    # finite instances for exhaustive checks
    ("x3k1e_rev", "x3k1e with the revised fixes", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, **REV)),
    ("x3k1e_pick", "x3k1e with the pick (v0.5's rules)", dict(K=1, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, **PICK)),
    ("x3e_rev", "the spec's triangle (K = 2), eager writers, two asks per chunk, the revised fixes", dict(MAX_ASKS=2, EAGER_WRITERS=True, **REV)),
    # K = 2 made small enough to finish: one slot, one ask per chunk, R = 1, eager writers
    ("x3k2n3e_rev", "K = 2, N = 3, R = 1, one slot, one ask per chunk, eager writers, the revised fixes",
     dict(K=2, N=3, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, **REV)),
    ("x3k2n3e_noaskfilter", "known answer for TLC: the same shape, the spec without the writer's ask filter",
     dict(K=2, N=3, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, NO_ASK_FILTER=True)),
    ("x3k2n2e_rev", "K = 2, N = 2 (no parity: both chunks needed), R = 1, one slot, one ask per chunk, eager writers, the revised fixes",
     dict(K=2, N=2, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, **REV)),
    ("x3k2e_rev", "K = 2, N = 4, R = 1, one slot, one ask per chunk, eager writers, the revised fixes",
     dict(K=2, N=4, R=1, W=1, MAX_ASKS=1, EAGER_WRITERS=True, **REV)),
]


def val(v):
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def one(name):
    """one/<name>.qnt: a single instance, for exhaustive checks (tlc/mkcheck.sh)"""
    comment, ch = next((c, x) for n, c, x in INSTANCES if n == name)
    p = dict(DEFAULTS, **ch)
    args = ", ".join(f"{k} = {val(p[k])}" for k in ORDER)
    return "\n".join(["// -*- mode: Bluespec; -*-",
                      "// One instance, for exhaustive checks (written by tools/gen_instances.py --one).",
                      f"// {comment}", f"module {name} {{", f"  import diffusion({args}).* from \"../diffusion\"", "}"])


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        print(one(sys.argv[2]))
        return
    out = ["// -*- mode: Bluespec; -*-",
           "// Instances of the diffusion model, written by tools/gen_instances.py: edit the table there.",
           "// K = 2, N = 4; the spec's defaults (R = 2, R_NODE = 2, W = 2, offers 16, 3 answers, FAN_IN 2,",
           "// cards 8, 9, 10, 12 and P4 on) unless the comment says otherwise.", ""]
    for name, comment, ch in INSTANCES:
        p = dict(DEFAULTS, **ch)
        args = ", ".join(f"{k} = {val(p[k])}" for k in ORDER)
        out.append(f"// {comment}")
        out.append(f"module {name} {{")
        out.append(f"  import diffusion({args}).* from \"./diffusion\"")
        out.append("}")
    print("\n".join(out))


if __name__ == "__main__":
    main()
