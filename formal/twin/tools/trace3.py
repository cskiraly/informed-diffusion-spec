#!/usr/bin/env python3
"""Trace protocol.md's functions (the block, BLOCK below) and §4.2's two readers `held` and `tied_to_root` (the
twin's code over its `mine` and `tied`), with what each call reads and writes (format 7).

Format 7. A trace's first line is its content line (content.py): what it was made from, each file by the sha256 of
its bytes: the two documents, every file of the toy, every file of these tools. Nothing else in a trace names
that, and the line names no commit, path, host or time: the same tree gives the same trace at any place. The
tracer makes sure that what runs is what the line names. Before the toy is imported (`start_check`): its Python
runs isolated (-I), not optimised, writes no bytecode (-B) and looks for bytecode under a prefix that holds no
file (-X pycache_prefix=DIR), and the output lies outside the toy and the tools. At the trace's end
(`loaded_check`): the line made again is the same, and every module loaded from a file is a source the line
names, or the standard library's. --xcheck and --topology are not traced (a dump is an input the line does not
name). layout.py's `python(work)` is the command that meets this.

The second line is the header: the format, `whole`, the tables' names (`own`, `foreign`), the functions traced
and the run's arguments. The third is the one nodes line:
  {"nodes": [{"n": [node, ...], "consts": {...}, "replaced": [name, ...]}, ...]}
one entry per distinct pair of constants and replaced names, with the nodes that have it. A record is replayed with
its own node's constants. At each node every traced name must be protocol.md's own code, a listed wrapper that holds
it, or the node's listed helper (`own_code`); a name on REPLACEABLE that is none of these is a question at that node,
and the node's entry says so.

    python3 trace3.py TOYDIR OUT.jsonl.gz [run.py's arguments ...]

With TRACE3_ONLY=sec61 in its environment it traces §6.1's twelve alone: most of their calls are otherwise inside
an on_ihave record, and these are the baseline's records. The two readers are then not traced, so their reads are
the calling record's. With --doc v2 among run.py's arguments it traces the block's names that are protocol.md's all
the way down (`v2_kept`, 20 at v0.10). The header's `traced` lists the functions traced, sorted: the block's
(BLOCK), §6.1's twelve, or v2's kept.

As trace61.py (whose encodings this file uses), nothing changes in TOYDIR: each node's namespace is wrapped after
the toy's own overrides, and the cell runs as run.py runs it, printing its digest with --digest, so that a run
shows the tracer perturbs nothing.

The state tables are wrapped too, by footprint.py's recording views, under the schema below. One record per
top-level call of a traced function, per node:
  n, t, fn, args   as in format 2
  reads    the entries of the block's own tables whose first touch in the call was a read, in that order, each
           [table, path, value before the call]; a missing or empty entry has the value null
  scans    the levels read as a whole, each [table, prefix]: every entry under one is in reads
  writes   the entries the call wrote or changed in place, each [table, path, value after the call]
  rest     entries the call did not read, each [table, path, value before the call]: the ones it wrote without
           reading first; and with whole=True (the directed records, whose states are small) every other entry of
           the block's own tables too. The replay loads them beside the reads, and the twin may not read them:
           they are there so that a write that does not do what it notes, or does more, shows.

With whole=True the log is also checked against the state itself, at the two ends of every call (`account`): the
tables as they were before the call must be the record's reads and rest, and as they are after it, those with the
record's writes applied. A write the views did not log, of an entry the call did not otherwise touch, stops the
tracer there. (One to an entry the call had read shows as that entry's changed value, and is recorded as the
write it is.) It is a check of the net change to the own tables: it does not see an unlogged read, a write undone
within the call, or a change in place of another section's value.

The trailer counts the records and the entries of rest, so that a trace cut down does not pass for a whole one.
  tape     what the block asked of the rest of the node, in order: the interface calls as in format 2, and each
           read of another section's table as ["read", table, path, value]; and these:
           - a call on the tape that touched the own tables carries, last, {"cr": [...], "cw": [...]}: the entries
             whose first touch in it was a read, with their values then, and the ones it wrote or changed in place,
             with their values at its end. A call that touched none carries nothing more. Inside a call, other
             sections' tables are its own business: nothing of them goes on the tape;
           - another section's level iterated by the block: ["keys", table, path, [key, ...]], in the Python's order;
             also `list(queue)`, an own table's top level whose order is asked: its rows are read whole, and the
             order is on the tape (["keys", "queue", [], [peer, ...]]);
           - `mesh | {p}` iterated by the block: ["mesh_and", [p], [q, ...]], in the Python's order.
           Every own entry a call on the tape touched first is in `rest`, with its value before the call, and
           `writes` hold the call's whole net change, its callees' writes among them.
  ret, or raises (and raises_key), as in format 2
  reached  the traced functions the call reached, its own among them, sorted
  tables   the own tables its reads, scans and writes name, sorted
These two are the record's last members, in this order: a replay of a subset (--only) picks a record by its line's
end without parsing it.

A path has one element per level of the table: an ask key as trace61.py writes it (hex of a full id, or
[group hex, index]), a peer as the toy's node id, a group as hex, a chunk as [group hex, index]; a promise's one
level is the pair [key, peer]. Floats are their IEEE-754 bits.
"""
import ast
import functools
import gzip
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "gen"))
import content                          # noqa: E402
import footprint as F                   # noqa: E402
import schema                           # noqa: E402: gen/schema.py, the twin's tables, which its Lean is made from too
from trace61 import CONSTS, SEC61, Tracer, fbits   # noqa: E402

OWN = tuple(t.name for t in schema.TABLES)
SEC44 = ("on_ihave", "over_ihave_limits", "valid_id", "expand", "gated")   # §4.4, and §6.2's gated
READERS = ("held", "tied_to_root")      # §4.2's two readers, the twin's code over its `mine` and `tied`
SEC42 = ("on_chunk", "on_validated", "send_have", "have_bits", "close_promises", "drop_beyond")
SEC42B = ("defer", "tie", "tie_room", "on_block_installed", "drop_tie", "drop_stale_waits")
SEC72 = ("next_to_send", "filter_entry", "with_owed", "rarest", "projected")   # §7.2's writer
# §1's seven
SEC1 = ("group_id", "group_key", "K", "N", "segment_length", "valid_descriptor", "build_group")
SEC2 = ("message_id",)                  # §2's: its content_id is a question at every call
SEC61B = ("drop_offer",)                # §6.1's last
SEC64 = ("on_pace_tick", "send_gossip", "on_heartbeat")  # §6.4 (the pace queue the twin's own table)
SEC46 = ("claim_group", "drop_group",   # §4.6's: `stop_pull` own
         "decode_group", "push_rebuilt")    # level 2 and the repair: the codec, the payload and delivery the node's
SEC43 = ("on_have",)                    # §4.3's: `peer_has` and `holders` the twin's own
SEC3 = ("validate_chunk", "committed_descriptor")   # §3's level 1: a chunk wide where it arrives or waits
SEC41 = ("on_iwant", "respond", "on_frame")     # §4.5's and §4.1's: one record per frame; `serve_count` own
# §5.2's four. One that the simulation or an untraced function calls is a record of its own
SEC52 = ("owe", "note_push", "unpush", "announce")
# §5.3's two
SEC53 = ("guard_fails", "choose_push")
# forward (replaceable), candidates_for_source and on_mesh_join (no caller in the toy: a directed set's)
SEC54 = ("forward", "candidates_for_source", "on_mesh_join")
# §7.1's six (the window's three tables the twin's own). window_timeout is a timer's record
SEC71 = ("acquire_slot", "release_unused_slot", "track_in_flight", "window_release", "window_timeout", "free_slot")
# §5.1's origin_written, which next_to_send calls at SOURCE_OFFERS = PUBLISH (no cell of check.py runs there:
# hand5-publish and directed7p do), origin_acked, and publish
SEC51 = ("origin_written", "origin_acked",
         "publish")     # the simulation's call, a record a published payload.
#                         With it the block is every function of protocol.md (and `held`, §4.2's reader)
BLOCK = SEC61 + SEC44 + READERS + SEC42 + SEC42B + SEC72 + SEC1 + SEC2 + SEC61B + SEC64 + SEC46 + SEC43 + SEC41 + SEC3 + SEC52 + SEC53 + SEC54 + SEC71 + SEC51
DEFER_DEPTH = 2                         # the twin's deferDepth (Sec42.lean): a record's chain of defers stops at the
                                        #   third, where the twin would crash
CARDS = ("CANCEL", "PROJECT", "RAREST")  # the writer's cards [c8, c12, c9], and FAN_IN [c12]
LIMITS = ("MAX_IHAVE_MESSAGES", "MAX_IHAVE_LENGTH", "MAX_PENDING_GROUPS")   # §8.2: the client's; none where it
#   sets none
FOREIGN = ("known_id",                     # `queue`, `pending_ids` and `stop_pull` are own
           "chunks")     # (`unwanted` is own: on_frame writes it)
#                                             the writer reads §5.2's (`peer_has` and `holders`, §4.3's, are the
#                                             twin's own: on_have asks `g in planned`)
# §7.1's three, the twin's own. Under protocol.md a cell holds the count and views hold the line and the sends;
# under --doc v2 they are not installed (there the count is bytes and a send's value a pair, and no traced function
# of protocol.md touches them)
WINDOW = ("in_flight", "waiters", "sent")
V2_FILE = "protocol-v2.md (extracted)"  # the toy compiles protocol-v2.md's blocks under this name (node.py, spec2)


# the calls the block makes on the tape: each a question, answered from the trace, whoever defines it (install's
# `enc` must name these, and only these)
TAPE = ("expired", "connected_topic_peers", "own_order", "listed", "authenticable", "shuffled", "valid_have",
        "penalise", "enqueue", "after", "seen", "accepted", "mark_seen", "live", "open_group",
        "store", "start",
        # the deferral path's questions (defer and tie are the twin's own)
        "installed_block", "admitted", "reserve", "release", "bid_group",
        # the writer's questions, and §7.1's, §4.1's and §5.2's calls it makes
        "has_room", "pop_owed_answer",     # (§7.1's three and unpush are the twin's own)
        # §1's questions: the toy's stand-ins for the hash, the serialization, the codec and the tree
        "sha256", "serialize", "snappy_block_encode", "pad_each", "rs_parity", "merkle_root", "merkle_proof",
        # §6.4's questions (whether a peer is still there; the ids' indices per group, in the order of each group's
        # first id) (§5.2's announce is the twin's own)
        "connected", "group_bits",
        # and on_heartbeat's: the topic's peers, a peer's eligibility for gossip (stock: scores), the sample
        "topic_peers", "gossip_eligible", "sample_without_replacement",
        # the node's helpers that §4.6's two call, each a call with its log
        "close_promises_of_group", "discard_queued", "discard_paced",
        # (on_have's calls of window_release and origin_acked are not on it: both are traced)
        # on_iwant's questions of the node's store, and on_frame's of the stock's prunes
        "resolve", "chunk_of", "handle_graft_prune",
        # decode_group's questions of the codec and of level 3 (push_rebuilt's two calls of §5.2's, note_push
        # and owe, are the twin's own)
        "decode_and_reencode", "payload_of", "deliver",
        # owe's call of the node's writer (§7.2), which the toy's enqueue makes itself
        "wake",
        # the push order's keys: each a question, a candidate at a time
        "tiebreak", "peer_id_bytes",
        # level 1's question of the tree (validate_chunk is the twin's own)
        "verify_merkle_proof",
        # publish's question of the block it publishes under
        "block_root")
# The questions written with their own encoders of arguments and answer (`calls`, in install), so that one that
# raises is on the tape too, its answer {"raises": the exception's type}: serialize of a field beyond its width.
CALLS = ("sha256", "serialize", "snappy_block_encode", "pad_each", "rs_parity", "merkle_root", "merkle_proof",
         "connected", "group_bits", "topic_peers", "gossip_eligible", "sample_without_replacement",
         "close_promises_of_group", "discard_queued", "discard_paced",
         "resolve", "chunk_of", "handle_graft_prune",
         "decode_and_reencode", "payload_of", "deliver", "wake", "tiebreak", "peer_id_bytes", "verify_merkle_proof",
         "block_root")


def v2_kept(names, p_src, v2_src, cut=TAPE):
    """Under --doc v2: the names of `names` that are protocol.md's all the way down. A def of protocol.md goes if
    protocol-v2.md defines it (v2 redefines it), or if it names one that goes, through any def of protocol.md, not
    through the names of `names` alone. A name of `cut` is a call on the tape: a question, answered from the trace
    whoever defines it, so it is not followed, and does not make its caller go. From the documents' own source:
    `p_src` protocol.md's extracted code, `v2_src` protocol-v2.md's."""
    v2_defs = {d.name for d in ast.parse(v2_src).body if isinstance(d, ast.FunctionDef)}
    defs = {d.name: d for d in ast.parse(p_src).body if isinstance(d, ast.FunctionDef)}
    refs = {n: {x.id for x in ast.walk(d) if isinstance(x, ast.Name)} - set(cut) for n, d in defs.items()}
    gone = {n for n in set(defs) | set(names) if n in v2_defs and n not in cut}
    grew = True
    while grew:
        grew = False
        for n in defs:
            if n not in gone and n not in cut and refs[n] & gone:
                gone.add(n)
                grew = True
    return tuple(n for n in names if n not in gone)


def doc_of(argv):
    """The document run.py is given (--doc v2 or --doc=v2), or None for protocol.md."""
    for i, a in enumerate(argv):
        if a == "--doc" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--doc="):
            return a.split("=", 1)[1]
    return None


DOC_FILE = "protocol.md (extracted)"    # the toy compiles protocol.md's blocks under this name (node.py, SPEC)
# A traced name's function at a node is protocol.md's own code, or one of these.
# WRAPPERS: the toy's wrappers of a document's function, each by its qualified name; it must hold the document's
# function of that name in its closure. Read once each (toy/node.py): message_id stores the id on the chunk;
# claim_group notes the completion's time; may_ask, add_offer and close_promises keep the toy's index of a chunk's
# ask keys and an offer's time; over_ihave_limits counts the asks held back; under --doc v2, promise_due notes a
# broken promise for the invariants. Each then calls the document's function with its own arguments.
WRAPPERS = {"message_id": "Node._override.<locals>.message_id", "claim_group": "Node._override.<locals>.claim_group",
            "may_ask": "Node._override.<locals>.may_ask", "add_offer": "Node._override.<locals>.add_offer",
            "close_promises": "Node._override.<locals>.close_promises",
            "over_ihave_limits": "Node.__init__.<locals>.over_ihave_limits",
            "promise_due": "Node._v2.<locals>.promise_due"}
# NODE_OWN: a traced name that is no function of the document's, but the node's helper the twin has as its own code
# (`held`, §8's interface, over the twin's `mine`).
NODE_OWN = {"held": "Node._namespace.<locals>.held"}
# REPLACEABLE: the traced names a node may run as something else (a fault, a variant). At such a node the name is
# a question on the tape, and the node's line says so.
REPLACEABLE = ("forward",               # a node that forwards nothing (silent, cap-wait), a scenario's
               "on_iwant",              # a withholder's (check.py's withholders, silent, cap-wait)
               "push_rebuilt",          # and the variants of the repair (--rebuilt none, hold, announce, capped)
               "validate_chunk")        # and, in a directed set alone (REPLACEABLE_WHOLE), a scenario's level 1
# A name replaceable only in a trace of the whole state: no cell runs anything but the document's level 1. The
# directed sets of §4.2 draw its result (a sequence of DEFERs with the block there, a REJECT of a chunk whose proof
# nobody made) to reach on_validated's and defer's paths, as they did while validate_chunk was a question.
REPLACEABLE_WHOLE = ("validate_chunk",)


def own_code(name, fn):
    """What a traced name's function is at a node: ("own", where) for protocol.md's own code, a listed wrapper that
    holds it, or the node's listed helper; ("replaced", where) for anything else."""
    code = getattr(fn, "__code__", None)
    if code is None:
        return "replaced", f"no Python function ({type(fn).__name__})"
    if code.co_filename == DOC_FILE:
        return ("own", "the document's") if code.co_name == name else ("replaced", f"the document's {code.co_name}")
    qual = getattr(fn, "__qualname__", "?")
    where = f"{qual} ({Path(code.co_filename).name}:{code.co_firstlineno})"
    if NODE_OWN.get(name) == qual and Path(code.co_filename).name == "node.py":
        return "own", where
    if WRAPPERS.get(name) == qual:
        for cell in fn.__closure__ or ():
            try:
                inner = cell.cell_contents
            except ValueError:
                continue
            ic = getattr(inner, "__code__", None)
            if ic is not None and ic.co_filename == DOC_FILE and ic.co_name == name:
                return "own", where
        return "replaced", f"{where}: a listed wrapper's name, without the document's {name} in its closure"
    return "replaced", where


def namespace_check(names, traced, v2_defs, ns, replaceable=None):
    """The namespace against the documents' source: no traced function is v2's, and every name of `names` that
    protocol-v2.md defines (`v2_defs`) is v2's here. Two derivations of the set, each checking the other. The reason
    the namespace is refused, or None.

    A replaceable name that protocol-v2.md defines may be the node's own here, neither document's: the toy's
    variants of push_rebuilt (--rebuilt none, hold, announce, capped; a silent node's), a silent node's forward.
    Such a name is not traced under v2 (v2 defines it), and nothing of the check depends on which of the two it is.
    protocol.md's own function under a name v2 defines is still refused: v2's block was not run over it. (Without
    the exception, a v2 cell whose nodes run their own push_rebuilt could not be traced.)"""
    replaceable = REPLACEABLE if replaceable is None else replaceable
    for name in names:
        file = getattr(getattr(ns.get(name), "__code__", None), "co_filename", None)
        v2_here = file == V2_FILE
        if name in traced and v2_here:
            return f"{name} is traced, but its function here is protocol-v2.md's"
        if name in v2_defs and not v2_here:
            if name in replaceable and file != DOC_FILE:
                continue
            return f"protocol-v2.md defines {name}, but its function here is not v2's"
    return None


def v2_kept_self_test():
    """v2_kept's cases on planted sources, and namespace_check's on a planted namespace: each must give what it
    states. The namespace's case with a redefined name left in the traced list is the control "a traced list
    computed with one redefined name left in must fail its check"."""
    p = "def a():\n    b()\ndef b():\n    pass\ndef c():\n    d()\ndef d():\n    pass\ndef e():\n    x()\ndef f():\n    c()\n"
    names = ("a", "b", "c", "d", "e", "f")
    cases = [
        ("v2 redefines d: d goes, c (calls d) and f (calls c) go with it; e's call of x, no name of theirs, is a "
         "question", v2_kept(names, p, "def d():\n    pass\n"), ("a", "b", "e")),
        ("v2 redefines x alone, which is none of the names: nothing goes", v2_kept(names, p, "def x():\n    pass\n"),
         names),
        ("v2 redefines nothing: nothing goes", v2_kept(names, p, ""), names),
        ("a name protocol.md does not define (a toy helper) stays unless v2 defines it",
         v2_kept(("a", "h"), p, "def d():\n    pass\n"), ("a", "h")),
        # the closure through every def of protocol.md, cut at the tape's names
        ("a name that reaches a redefined def through a helper outside the names goes",
         v2_kept(("f", "a"), p, "def d():\n    pass\n", cut=()), ("a",)),
        ("a name that calls a tape name v2 redefines stays: the call is a question",
         v2_kept(("c", "a"), p, "def d():\n    pass\n", cut=("d",)), ("c", "a")),
    ]
    bad = 0
    for what, got, want in cases:
        ok = got == want
        bad += not ok
        print(f"v2_kept self-test, {what}: {'ok' if ok else f'got {got}, must be {want}  <-- FAIL'}")
    # a namespace as the toy makes one: protocol.md's functions compiled under one file name, v2's under V2_FILE
    ns = {}
    exec(compile(p, "protocol.md (extracted)", "exec"), ns)
    exec(compile("def d():\n    pass\n", V2_FILE, "exec"), ns)
    kept = v2_kept(names, p, "def d():\n    pass\n")
    own = {}
    exec(compile("def d():\n    pass\n", "node.py", "exec"), own)       # a node's own function under the name
    ncases = [
        ("the computed set, d v2's here: passes", namespace_check(names, kept, {"d"}, ns), None),
        ("the computed set with d, which v2 redefines, left in: refused",
         namespace_check(names, kept + ("d",), {"d"}, ns), "d is traced, but its function here is protocol-v2.md's"),
        ("the computed set, but d protocol.md's here (v2's block not run over it): refused",
         namespace_check(names, kept, {"d"}, {**ns, "d": ns["b"]}),
         "protocol-v2.md defines d, but its function here is not v2's"),
        # a replaceable name v2 defines may be the node's own (neither document's)
        ("d replaceable and the node's own here (a function of neither document): passes",
         namespace_check(names, kept, {"d"}, {**ns, "d": own["d"]}, replaceable=("d",)), None),
        ("d replaceable, but protocol.md's here: refused",
         namespace_check(names, kept, {"d"}, {**ns, "d": ns["b"]}, replaceable=("d",)),
         "protocol-v2.md defines d, but its function here is not v2's"),
        ("d the node's own here, and not replaceable: refused",
         namespace_check(names, kept, {"d"}, {**ns, "d": own["d"]}, replaceable=()),
         "protocol-v2.md defines d, but its function here is not v2's"),
        ("d replaceable and left in the traced list, v2's here: refused as before",
         namespace_check(names, kept + ("d",), {"d"}, ns, replaceable=("d",)),
         "d is traced, but its function here is protocol-v2.md's"),
    ]
    for what, got, want in ncases:
        ok = got == want
        bad += not ok
        print(f"namespace_check self-test, {what}: {'ok' if ok else f'got {got!r}, must be {want!r}  <-- FAIL'}")
    print("ok: every case as it must be" if not bad else f"{bad} cases wrong")
    return 1 if bad else 0


class Tracer3(Tracer):
    def __init__(self, toy, out, argv, whole=False):     # not Tracer's: the header differs
        self.whole = whole
        self.only61 = os.environ.get("TRACE3_ONLY") == "sec61"     # §6.1's twelve alone: the baseline's records
        self.toy = Path(toy).resolve()
        self.start_check(out)           # before the toy is imported
        sys.path.insert(0, str(toy))
        import node as N                # noqa: E402: the pinned toy, from TOYDIR
        import wire as Wm               # noqa: E402
        self.N, self.Wm = N, Wm
        F.ATTR_LEVELS[N.PeerQueue] = ("urgent", "normal")    # a PeerQueue's lanes are its keys
        F.ATTR_READS[N.PeerQueue] = {"has_chunks": ("normal",)}  # next_to_send's `q.has_chunks()`
        # the content line first: what this trace is made from (content.py)
        self.content_line = content.line(content.content(self.toy))
        self.out = gzip.open(out, "wt", compresslevel=1)
        self.out.write(self.content_line)
        self.counts = Counter()
        self.nodes = []                 # (node, its constants, its replaced names), as each is installed (the nodes line)
        self.nodes_written = False
        self.bound = []                 # (node, namespace, {traced name: the tracer's wrapper of it there}), for the
        #                                   names' second check (final_check)
        self.doc_mid = {}               # and m2_check's reference function, a node's own
        self.cur_nid = None             # the node of the record being written (mid_of's reference)
        self.built_objs = {}            # the chunks the record's publish built (built, content_id_asked)
        self.rest_total = 0
        self.doc_message_id = None      # the document's message_id: the tracer's own way to a chunk's id,
        #                                   untraced, storing nothing on the chunk
        # what is traced: §6.1's twelve alone (TRACE3_ONLY=sec61); under --doc v2, the block's names that are
        # protocol.md's all the way down; otherwise the block
        self.doc_v2 = doc_of(argv) == "v2"
        if any(a.split("=")[0] in ("--xcheck", "--topology") for a in argv):
            # --topology reads a dump, an input the content line does not name; and the toy's cross-check recorder
            # keeps `max(peak, ns["in_flight"])`, which hands out the count's cell
            raise SystemExit("trace3: --xcheck and --topology are not traced: a dump is an input the content line "
                             "does not name, and the toy's recorder there keeps the window's count, which is a cell "
                             "of the tracer's here")
        self.v2_defs = ({d.name for d in ast.parse(N.generate(N.DOC2)).body if isinstance(d, ast.FunctionDef)}
                        if self.doc_v2 else set())
        if self.only61:
            self.traced = SEC61
        elif self.doc_v2:
            # (under v2 the window's count is bytes and a send's value a pair, and the three tables are not
            # installed: the six are not traced there, by name)
            self.traced = tuple(n for n in v2_kept(BLOCK, N.SPEC_SRC, N.generate(N.DOC2)) if n not in SEC71)
        else:
            self.traced = BLOCK
        for d in (N.DOC, N.DOC2):       # the documents the toy reads are the two the content line names
            if Path(d).resolve() != self.toy.parent / Path(d).name:
                raise SystemExit(f"trace3: the toy reads a document that is not beside it: {d}")
        self.write({"header": {"format": 7, "whole": whole, "own": list(OWN), "foreign": list(FOREIGN),
                               "traced": sorted(self.traced), "tracer": "trace3.py", "args": argv}})

    def write_nodes(self):
        """The nodes line: every node the tracer was installed at, by what the replay needs of it: its
        constants, and the traced names its namespace has replaced (a question there).
        One entry per distinct pair, in the order of its first node, with the nodes that have it. Written once,
        before the first record; a trace with no record has it before its trailer."""
        self.final_check()
        entries = []
        for nid, consts, replaced in self.nodes:
            for e in entries:
                if e["consts"] == consts and e["replaced"] == replaced:
                    e["n"].append(nid)
                    break
            else:
                entries.append({"n": [nid], "consts": consts, "replaced": replaced})
        self.write({"nodes": entries})
        self.nodes_written = True

    def close(self):
        if not self.nodes_written:
            self.write_nodes()
        else:                           # the traced names once more at the end: a name bound again after the first
            self.final_check()          #   record is seen too
        self.loaded_check()
        self.write({"trailer": {"records": sum(self.counts.values()), "by_fn": dict(sorted(self.counts.items())),
                                "rest": self.rest_total}})
        self.out.close()

    def start_check(self, out):
        """What must hold of this Python before the toy is imported, so that what runs is what the content line
        names. It runs isolated (-I: no PYTHONPATH, no user site, no directory of its own on the path), not
        optimised (-O would take out the tracer's own checks), writes no bytecode (-B), and looks for bytecode
        under a prefix (-X pycache_prefix=DIR) that holds no file: a bytecode file beside a source is then never
        read in the source's place. The output lies outside the toy and the tools, or the line would name it."""
        if not sys.flags.isolated:
            raise SystemExit("trace3: Python does not run isolated (-I): PYTHONPATH could put another module "
                             "in place of one the content line names")
        if sys.flags.optimize:
            raise SystemExit("trace3: Python runs optimised (-O): the tracer's own checks would not run")
        if not sys.dont_write_bytecode:
            raise SystemExit("trace3: Python writes bytecode (run it with -B)")
        self.prefix_check()
        outp = Path(out).resolve()
        if self.toy in outp.parents or HERE in outp.parents:
            raise SystemExit(f"trace3: the output lies under the toy or the tools, which the content line names: {outp}")

    @staticmethod
    def prefix_check():
        pre = sys.pycache_prefix
        if not pre:
            raise SystemExit("trace3: Python has no bytecode prefix (-X pycache_prefix=DIR, an empty directory): "
                             "a bytecode file beside a source could be read in the source's place")
        for _root, _dirs, files in os.walk(pre):
            if files:
                raise SystemExit(f"trace3: the bytecode prefix holds a file: {pre}")

    def loaded_check(self):
        """At the trace's end, what ran is what the content line names: the line made again is the same line (no
        file changed under the run); the bytecode prefix still holds no file; and every module this process loaded
        from a file is a source the line names, or the standard library's. A module from anywhere else (a
        site directory, a path put before the toy's) stops the tracer here."""
        if content.line(content.content(self.toy)) != self.content_line:
            raise SystemExit("trace3: a file the content line names changed while the trace was made")
        self.prefix_check()
        names = set(json.loads(self.content_line)["content"]["files"])
        std = Path(os.__file__).resolve().parent
        for name, m in sorted(sys.modules.items()):
            f = getattr(m, "__file__", None)
            if f is None:               # built in
                continue
            where = Path(f).resolve()
            if self.toy in where.parents:
                key = "toy/" + where.relative_to(self.toy).as_posix()
            elif HERE in where.parents:
                key = content.TOOLS + "/" + where.relative_to(HERE).as_posix()
            elif std in where.parents and "site-packages" not in where.parts and "dist-packages" not in where.parts:
                continue                # the standard library's
            else:
                raise SystemExit(f"trace3: module {name} was loaded from {f}, which is neither the toy's, the "
                                 f"tools' nor the standard library's")
            if key not in names or where.suffix != ".py":
                raise SystemExit(f"trace3: module {name} was loaded from {f}, which the content line does not name "
                                 f"as a source")
            # the program itself (__main__) is run from its source, never from bytecode
            if name != "__main__" and type(getattr(m, "__loader__", None)).__name__ != "SourceFileLoader":
                raise SystemExit(f"trace3: module {name} was not loaded from its source: {f}")
    def account(self, rec, r, before):
        """The log against the state itself (a trace of the whole state): `before` is the own tables as they were
        when the call began, read from the containers."""
        def k(e):
            return (e[0], json.dumps(e[1]))
        said = {k(e): e[2] for e in r["reads"] if e[2] is not None}
        said.update({k(e): e[2] for e in r["rest"]})
        if said != before:
            d = sorted(x for x in set(said) | set(before) if said.get(x) != before.get(x))[:4]
            raise SystemExit(f"trace3: the views' log does not account for the state before {r['fn']}{r['args']} "
                             f"at node {r['n']}: reads and rest differ from the tables at {d}")
        want = dict(before)
        for e in r["writes"]:
            if e[2] is None:
                want.pop(k(e), None)
            else:
                want[k(e)] = e[2]
        after = rec.snapshot()
        if after != want:
            d = sorted(x for x in set(after) | set(want) if after.get(x) != want.get(x))[:4]
            raise SystemExit(f"trace3: the views' log does not account for the state after {r['fn']}{r['args']} "
                             f"at node {r['n']}: the tables differ from reads, rest and writes at {d}")

    # ---- §4.4's arguments and results (the twelve of §6.1: trace61.py)
    def ihave_entry(self, e):
        """An entry of an IHAVE: a full id as a key is written, or ["bits", group, bitmap]."""
        if self.Wm.is_have_bitmap(e):
            return ["bits", e.group.hex(), e.bits.v]
        if isinstance(e, bytes):
            return e.hex()
        raise TypeError(f"not an IHAVE's entry: {e!r}")

    def chunk(self, f):
        """A chunk as the twin reads it: [group, index, slot, root, id], the id as the toy computes it once per chunk
        (toy/node.py's message_id), so the twin never computes one."""
        return [f.group.hex(), int(f.index), int(f.slot), f.beacon_block_root.hex(), self.mid_of(f).hex()]

    def wchunk(self, f):
        """A chunk where it arrives or waits: the chunk, and what level 1 reads of it, [descriptor, the proof's
        digests, the data as a blob]. A chunk object without all three (a directed set's, whose level 1 is its
        scenario's: §4.2's sets give a chunk its descriptor alone, for open_group) is written narrow. The document's
        level 1 on such a chunk is then a crash of the twin's, and a mismatch: no cell's chunk lacks any."""
        # (the descriptor is apart from the two: a design B chunk has none on the wire (§2), and level 1 still
        # reads its data and its proof, so it is written with a null descriptor; written narrow, a design B chunk
        # in its wire shape would be the twin's crash)
        d, proof, data = (getattr(f, k, None) for k in ("descriptor", "proof", "data"))
        if proof is None or data is None:
            return self.chunk(f)
        return self.chunk(f) + [[None if d is None else self.descriptor(d), [x.hex() for x in proof], self.blob(data)]]

    def built(self, f):
        """A chunk the block built (publish's `Chunk(...)`), where it is stored: no id yet, and all of its
        content, `[group, index, slot, root, null, [descriptor or null, the proof's digests, the data]]`. In the toy
        the id is on the chunk object once its store has run; the document's chunk has none until message_id is
        called, and the twin's neither. The object is remembered for this record: the `content_id` of the block's
        next message_id of it is written the same way (content_id_asked), once."""
        d = getattr(f, "descriptor", None)
        self.built_objs[id(f)] = f              # held, so that its id() names no other object in this record
        return [f.group.hex(), int(f.index), int(f.slot), f.beacon_block_root.hex(), None,
                [None if d is None else self.descriptor(d), [x.hex() for x in f.proof], self.blob(f.data)]]

    def block(self, b):
        """A block as level 1 reads it: [slot, the bid's group id or None, the bid's descriptor or None]. A block
        with no bid (a directed set's stand-in) commits neither."""
        bid = getattr(getattr(getattr(b, "body", None), "signed_execution_payload_bid", None), "message", None)
        gid = getattr(bid, "execution_payload_segment_group_id", None)
        d = getattr(bid, "execution_payload_segment_descriptor", None)
        return [self.nat(b.slot), None if gid is None else gid.hex(), None if d is None else self.descriptor(d)]

    def mid_of(self, f):
        """A chunk's id for the tracer's own use: the one the chunk has stored, or the document's function's,
        computed here and not stored. So tracing warms no cache of the toy's."""
        m = getattr(f, "mid", None)
        return m if m is not None else self.doc_mid.get(self.cur_nid, self.doc_message_id)(f)

    def content_id_asked(self, tape, f, r, nid):
        """A call of message_id by the block: `content_id(f)` goes on the tape with its answer, the last 20 bytes of
        the id returned, whether the toy's wrapper computed the id or had it stored. And the id returned is the
        document's function's for that chunk, computed again here: a stored id that is not stops the run."""
        self.m2_check(f, r, nid)
        if self.built_objs.pop(id(f), None) is f:       # publish's own message_id of a chunk it built
            form = self.built(f)
            del self.built_objs[id(f)]                  #   (once: the twin's chunk carries the id from here on)
        else:
            form = self.chunk(f)
        tape.append(["content_id", [form], bytes(r)[36:].hex()])

    def m2_check(self, f, r, nid):
        """The check alone: the id message_id returned is the document's function's for that chunk, by the node's own
        function. Also where a call on the tape makes the call: the node's store calls message_id, and a stale
        stored id used there alone would otherwise go unchecked."""
        try:
            want = self.doc_mid.get(nid, self.doc_message_id)(f)
        except Exception as e:
            raise SystemExit(f"trace3: node {nid}: message_id returned a stored id where the document's function "
                             f"raises {type(e).__name__} for that chunk") from e
        if bytes(want) != bytes(r):
            raise SystemExit(f"trace3: node {nid}: message_id returned {bytes(r).hex()}, and the document's function "
                             f"gives {bytes(want).hex()} for that chunk: the id stored on it is not the document's")

    def final_check(self):
        """The traced names once more, when the nodes line is written, and again at the trace's end: install runs
        inside `Node._override`, and the toy binds more after it returns (`Node.__init__`: over_ihave_limits' wrapper; under v2 `_v2`'s names,
        on_frame, promise_due, a liar's send_have; a variant's wrapper of close_promises). A traced name must still
        be the tracer's own wrapper at that node, or a listed wrapper that holds it: anything else runs outside the
        records, unseen where no record calls it and another function's where one does. The names on the tape are
        not held so: a question rebound later is missing from a tape, which the replay refuses, and under v2 the toy
        rebinds several that no kept function asks."""
        for nd, ns, bound in self.bound:
            for name, w in bound.items():
                now = ns.get(name)
                if now is w:
                    continue
                held = []
                for cell in getattr(now, "__closure__", None) or ():
                    try:
                        held.append(cell.cell_contents)
                    except ValueError:
                        pass
                if WRAPPERS.get(name) == getattr(now, "__qualname__", None) and any(x is w for x in held):
                    continue
                code = getattr(now, "__code__", None)
                where = (f"{getattr(now, '__qualname__', '?')} ({Path(code.co_filename).name}:{code.co_firstlineno})"
                         if code is not None else repr(now))
                raise SystemExit(f"trace3: node {nd.id}: {name} was bound again after the tracer was installed, to "
                                 f"what is neither the tracer's wrapper nor a listed wrapper of it: {where}")

    def control(self, x):
        """A control message on the tape: an IWANT's asks as keys (trace61.py), an IDONTWANT's HAVE as a bitmap."""
        if not isinstance(x, self.Wm.Control):
            raise TypeError(f"the block enqueues control only, got {x!r}")
        # (announce's IHAVE of a bitmap, written as an IHAVE's entry is)
        return [[m.kind, [self.ihave_entry(b) if m.kind == "idontwant" or self.Wm.is_have_bitmap(b) else self.key(b)
                          for b in m.ids]] for m in x.items]

    def args_of(self, fn, args, kw=None):
        kw = kw or {}
        if fn == "choose_push":                                     # §5.3: the document calls it
            names = ("f", "cands", "budget", "at_source")           #   with `budget=` and `at_source=`
            v = dict(zip(names, args))
            if set(v) & set(kw) or set(v) | set(kw) != set(names):
                raise TypeError(f"trace3: choose_push called with {len(args)} arguments and keywords {sorted(kw)}")
            v.update(kw)
            if not isinstance(v["at_source"], bool):
                raise TypeError(f"trace3: choose_push's at_source is no bool: {v['at_source']!r}")
            return [self.chunk(v["f"]), [int(p) for p in v["cands"]], self.nat(v["budget"]), v["at_source"]]
        if kw and not (fn == "close_promises" and set(kw) == {"of"}):
            raise TypeError(f"trace3: {fn} called with keywords {sorted(kw)}")
        if fn in ("on_chunk",):         # a chunk is wide where it arrives or waits
            p, f = args
            return [p, self.wchunk(f)]
        if fn == "on_validated":
            p, f, result = args
            return [p, self.wchunk(f), result]
        if fn == "validate_chunk":      # §3
            (f,) = args
            return [self.wchunk(f)]
        if fn == "committed_descriptor":
            block, f = args
            return [self.block(block), self.wchunk(f)]
        if fn == "send_have":
            p, g = args
            return [p, g.hex()]
        if fn in ("defer", "tie"):                                  # the chunk wide
            p, f = args
            return [p, self.wchunk(f)]
        if fn == "tie_room":
            p, f = args
            return [p, self.chunk(f)]
        if fn == "on_block_installed":
            (root,) = args
            return [root.hex()]
        if fn == "drop_tie":
            p, g, bits = args
            return [p, g.hex(), bits.v]
        if fn == "drop_stale_waits":
            assert not args, args
            return []
        if fn == "next_to_send":
            (p,) = args
            return [p]
        if fn in ("filter_entry", "with_owed"):
            p, e = args
            return [p, self.qentry(e)]
        if fn == "projected":
            p, g = args
            return [p, g.hex()]
        if fn == "rarest":                                          # v2's choose calls it alone, with `queue[p]`:
            (q,) = args                                             #   the peer is the key whose queue it is, in the
            q = F.unwrap(q)                                         #   node's own queue table (by identity)
            ps = [k for k, v in dict.items(self.cur_queue) if v is q]
            if len(ps) != 1:
                raise TypeError(f"trace3: rarest of a queue that is no peer's queue[p] at this node: {q!r}")
            return [ps[0]]
        if fn in ("have_bits", "drop_beyond"):
            (g,) = args
            return [g.hex()]
        if fn == "close_promises":
            g, i, *of = args
            of = kw["of"] if "of" in kw else (of[0] if of else None)
            return [g.hex(), int(i), of]
        if fn == "on_ihave":
            p, ih = args
            return [p, [self.ihave_entry(e) for e in ih.ids]]
        if fn == "over_ihave_limits":
            (p,) = args
            return [p]
        if fn in ("expand", "valid_id"):
            (e,) = args
            return [self.ihave_entry(e)]
        if fn in ("gated", "held"):
            (a,) = args
            return [self.key(a)]
        # §1's seven. K and N take what their caller read of `desc`: a descriptor, or None
        if fn == "drop_offer":                                      # §6.1's
            g, i, p = args
            return [g.hex(), self.nat(i), p]
        if fn == "message_id":                                      # §2
            (f,) = args
            try:
                return [self.chunk(f)]
            except OverflowError:       # an index beyond a uint32 has no id (the document's function raises, in
                # the tracer's own computation of the id too): the chunk is written with a null id, so that the
                # call's raise is a record, and not a raise here, before any record
                return [[f.group.hex(), int(f.index), int(f.slot), f.beacon_block_root.hex(), None]]
        if fn in ("group_id", "valid_descriptor"):
            (d,) = args
            return [self.descriptor(d)]
        if fn in ("K", "N"):
            (d,) = args
            return [None if d is None else self.descriptor(d)]
        if fn == "group_key":
            gid, slot = args
            return [gid.hex(), self.nat(slot)]
        if fn == "segment_length":
            d, i = args
            return [self.descriptor(d), self.nat(i)]
        if fn == "build_group":
            (body,) = args
            return [self.blob(body)]
        if fn == "tied_to_root":
            p, a = args
            return [p, self.key(a)]
        if fn == "on_iwant":                                        # §4.5
            p, iw = args
            return [int(p), [self.ask_key(a) for a in iw.ids]]
        if fn == "respond":                                         # §4.1
            p, asks, answers, prunes = args
            return [int(p), [self.key(a) for a in asks], [self.chunk(f) for f in answers], len(self.no_prunes(prunes))]
        if fn == "on_frame":
            p, frame = args
            return [int(p), self.frame(frame)]
        if fn == "on_have":                                         # §4.3: a HAVE's bitmap
            p, h = args
            return [int(p), h.group.hex(), h.bits.v]
        if fn == "push_rebuilt":                                    # §4.6
            g, new = args
            return [g.hex(), [self.nat(i) for i in new]]
        if fn in SEC46:
            (g,) = args
            return [g.hex()]
        if fn in ("on_pace_tick", "on_heartbeat"):                  # §6.4
            assert not args, args
            return []
        if fn == "send_gossip":
            q, ids = args
            return [int(q), [self.key(m) for m in ids]]
        if fn in ("announce", "owe"):                               # §5.2: a bitmap
            p, g, bits = args
            if not isinstance(bits, self.N.B.Bits):
                raise TypeError(f"trace3: {fn}'s bits are no bitmap: {bits!r}")
            return [int(p), g.hex(), bits.v]
        if fn in ("unpush", "note_push"):
            p, g, i = args
            return [int(p), g.hex(), self.nat(i)]
        if fn == "guard_fails":                                     # §5.3
            p, g = args
            return [int(p), g.hex()]
        if fn == "forward":                                         # §5.2's
            f, p = args
            return [self.chunk(f), int(p)]
        if fn == "candidates_for_source":
            (f,) = args
            return [self.chunk(f)]
        if fn == "on_mesh_join":
            (p,) = args
            return [int(p)]
        if fn in ("acquire_slot", "release_unused_slot"):           # §7.1's
            (p,) = args
            return [int(p)]
        if fn == "track_in_flight":
            p, f = args
            return [int(p), self.chunk(f)]
        if fn == "window_release":
            p, g, i = args
            return [int(p), g.hex(), self.nat(i)]
        if fn == "window_timeout":                                  # the send's key and the time's bits
            k, at = args
            return [[int(k[0]), k[1].hex(), self.nat(k[2])], fbits(at)]
        if fn == "free_slot":
            assert not args, args
            return []
        if fn == "origin_written":                                  # §5.1's
            (f,) = args
            return [self.chunk(f)]
        if fn == "publish":                                         # the block, the descriptor, the shards
            block, d, shards = args
            return [self.block(block), self.descriptor(d),
                    [[self.nat(x.index), [h.hex() for h in x.proof], self.blob(x.data)] for x in shards]]
        if fn == "origin_acked":
            g, i = args
            return [g.hex(), self.nat(i)]
        return super().args_of(fn, args)

    def ret_of(self, fn, r):
        if fn in ("on_ihave", "expand"):
            return [self.key(a) for a in r]
        if fn == "have_bits":
            return r.v
        if fn == "tie_room":
            assert isinstance(r, bool), (fn, r)
            return r
        if fn == "next_to_send":                                    # an entry, WAIT, or nothing
            return "WAIT" if r is self.WAIT else None if r is None else self.qentry(r)
        if fn in ("filter_entry", "with_owed"):
            return None if r is None else self.qentry(r)
        if fn == "projected":
            assert isinstance(r, bool), (fn, r)
            return r
        if fn == "rarest":
            return int(r)
        if fn in SEC42 or fn in SEC42B or fn in SEC61B or fn in SEC64 or fn in SEC46 or fn in SEC43 or fn in SEC52 or fn in ("respond", "on_frame"):
            assert r is None, (fn, r)
            return None
        if fn in ("choose_push", "candidates_for_source"):          # the targets, the candidates: peers in order
            return [int(p) for p in r]
        if fn in ("forward", "on_mesh_join", "origin_written", "origin_acked", "publish"):
            assert r is None, (fn, r)
            return None
        if fn == "acquire_slot":
            assert isinstance(r, bool), (fn, r)
            return r
        if fn in SEC71:
            assert r is None, (fn, r)
            return None
        if fn in ("over_ihave_limits", "gated", "valid_id", "held", "tied_to_root", "valid_descriptor", "guard_fails"):
            assert isinstance(r, bool), (fn, r)
            return r
        if fn == "on_iwant":                                        # the answers: chunks
            return [self.chunk(f) for f in r]
        if fn == "validate_chunk":                                  # level 1's result
            if r not in ("ACCEPT", "REJECT", "DEFER"):
                raise TypeError(f"trace3: not a result of validate_chunk: {r!r}")
            return r
        if fn == "committed_descriptor":
            return None if r is None else self.descriptor(r)
        if fn in ("group_id", "group_key", "message_id"):           # §1's; §2's id
            return r.hex()
        if fn in ("K", "N"):
            return self.nat(r)
        if fn == "segment_length":
            return self.integer(r)
        if fn == "build_group":
            d, shards = r
            return [self.descriptor(d), [[self.nat(s.index), [x.hex() for x in s.proof], self.blob(s.data)] for s in shards]]
        return super().ret_of(fn, r)

    @staticmethod
    def boolean(r):                     # a question's answer that must be a bool itself, not a truthy value
        if not isinstance(r, bool):
            raise TypeError(f"trace3: not a bool: {r!r}")
        return r

    def drawn(self, a):                 # a member of a list shuffled: a peer or an index as it is, an ask as its key
        return a if isinstance(a, int) and not isinstance(a, bool) else self.key(a)

    @staticmethod
    def store_group(cg):                # `chunks[g]`, the node's store of a group, as decode_and_reencode's argument:
        if isinstance(cg, F.View) and len(cg._p) == 1:      # the group whose row of `chunks` it is
            return cg._p[0].hex()
        raise TypeError(f"trace3: decode_and_reencode's chunks are not a row of `chunks`: {cg!r}")

    def rebuilt(self, r):               # the rebuilt chunks, each under its index, in the dict's order; or None
        return None if r is None else [[self.nat(i), self.chunk(f)] for i, f in r.items()]

    def payload(self, x):               # a payload: nothing (the toy's payload_of), or a blob
        return None if x is None else self.blob(x)

    @staticmethod
    def no_prunes(r):                   # the stock's prunes: none in the toy's runs, and a record holds none's content
        if list(r):
            raise TypeError(f"trace3: prunes, of which a record holds none: {r!r}")
        return []

    def ask_key(self, a):               # an IWANT's id: an ask by index, or a structured id
        if not (isinstance(a, self.Wm.WantIndex) or (isinstance(a, bytes) and len(a) == 56)):
            raise TypeError(f"trace3: an IWANT's id that is neither an ask by index nor a structured id of 56 bytes: {a!r}")
        return self.key(a)

    def frame(self, fr):                # a frame as on_frame sees it: [chunks, ihave, iwant, idontwant]
        if fr.prune or fr.graft or fr.join:
            raise TypeError("trace3: a frame with a PRUNE, a GRAFT or a JOIN: the stock's, of which a record holds none")
        # (since v0.10.4 an IDONTWANT's entry that is no HAVE bitmap is an opaque id, kept in `unwanted[p]`:
        # ihave_entry writes it as its hex, and raises for an entry that is neither a bitmap nor bytes)
        return [[self.wchunk(f) for f in fr.chunks], [self.ihave_entry(e) for e in fr.ihave.ids],
                [self.ask_key(a) for a in fr.iwant.ids], [self.ihave_entry(h) for h in fr.idontwant]]

    @staticmethod
    def nothing(r):                     # a call that returns nothing
        if r is not None:
            raise TypeError(f"trace3: a call that returns nothing returned {r!r}")
        return None

    # ---- the values: numbers, descriptors, blobs
    @staticmethod
    def nat(i):
        """A natural number of a record: a Python int, not a bool, not negative."""
        if not isinstance(i, int) or isinstance(i, bool) or i < 0:
            raise TypeError(f"trace3: not a natural number: {i!r}")
        return i

    @staticmethod
    def integer(i):
        """An integer that can be negative: a natural number, or ["-", n] for -n. A record has no number with a
        sign (the replay's strict scan refuses one)."""
        if not isinstance(i, int) or isinstance(i, bool):
            raise TypeError(f"trace3: not an integer: {i!r}")
        return i if i >= 0 else ["-", -i]

    def descriptor(self, d):
        """A descriptor, whole: [version, hash_id, encoding, count, segment_size, total_length, root]."""
        return [self.nat(d.version), self.nat(d.hash_id), self.nat(d.encoding), self.nat(d.count),
                self.nat(d.segment_size), self.nat(d.total_length), d.root.hex()]

    def blob(self, b):
        """A blob: [length, tag], the toy's tag with its tuples as lists (a string or an int at its leaves)."""
        def tag(t):
            if isinstance(t, tuple):
                return [tag(x) for x in t]
            if isinstance(t, (str, int)) and not isinstance(t, bool):
                return t
            raise TypeError(f"trace3: a blob's tag the record cannot hold: {t!r}")
        if not isinstance(b, self.Wm.Blob):
            raise TypeError(f"trace3: not a blob: {b!r}")
        return [len(b), tag(b.tag)]

    # ---- §7's queue, the twin's own table
    def lane(self, entries):
        """A lane's value: its entries in order, each [chunk or null, control or null, solicited]. The toy's own
        marks of an entry (`at`, `urgent`) are not written: nothing the documents run reads them."""
        return [self.qentry(e) for e in entries]

    def qentry(self, e):
        c = e.control
        return [self.chunk(e.chunk) if e.chunk is not None else None,
                None if c is None else [self.qmsg(m) for m in c.items], bool(e.solicited)]

    def qmsg(self, m):
        """A control message of an entry: an IWANT's ids as ask keys, an IHAVE's and an IDONTWANT's as IHAVE
        entries (v2's claims and WANT fields are not written: the twin reads neither). A PRUNE with ids, a GRAFT
        or a JOIN is refused: none is queued in the toy's runs (its stock prunes are none, and --upkeep is off)."""
        if m.kind == "iwant":
            return ["iwant", [self.key(b) for b in m.ids]]
        if m.kind in ("ihave", "idontwant"):
            return [m.kind, [self.ihave_entry(x) for x in m.ids]]
        if m.kind == "prune" and not m.ids:
            return ["prune", []]
        raise TypeError(f"trace3: a queue entry's control message the record cannot hold: {m.kind} {m.ids!r}")

    # ---- the checks of installed_block's answers and of pending
    def installed(self, slot, root, r):
        """installed_block's answer as the twin reads it (the block as level 1 reads it, or nothing), held to one
        answer, there or not, per (slot, root) in a record: on_validated and defer recurse at most twice only
        while the node answers the same way within one call; the twin's fuel relies on it, and a run that answers
        otherwise stops here. The answer is the block or nothing (§8's interface), and defer reads its truth: an
        answer that is neither (a False, say) would be read as a block here and as none by the Python, so it stops
        the run too."""
        if r is not None and not r:
            raise SystemExit(f"trace3: installed_block({slot}, {root.hex()[:16]}…) answered {r!r}: neither a block nor "
                             f"nothing, as §8's interface has it")
        got = r is not None
        was = self.ib.setdefault((int(slot), bytes(root)), got)
        if was != got:
            raise SystemExit(f"trace3: installed_block({slot}, {root.hex()[:16]}…) answered {was}, then {got}, in one "
                             f"record: the twin's recursion between on_validated and defer assumes one answer")
        return self.block(r) if got else None

    def pending_check(self, rec, nid):
        """No (peer, chunk) waits twice under one root (on_chunk's `mid in pending_ids` stands before defer). The
        twin removes a pair as Python's list.remove does, the first equal one, so a twice-kept pair would matter."""
        raw = rec.roots["pending"][1]
        for root in F._keys(raw):
            seen = set()
            for p, f in F._peek(raw, root):
                k = (int(p), bytes(self.mid_of(f)))
                if k in seen:
                    raise SystemExit(f"trace3: node {nid}: peer {p}'s copy {k[1].hex()[:16]}… waits twice under one "
                                     f"root")
                seen.add(k)

    def alias_check(self, rec, nid, args=(), when="end"):
        """No entry object stands in two places of the node's queue (two lanes, or twice in one), and no entry's
        control, or one of its messages, is another entry's too (drop_offer changes a message's ids in place). A
        value model would miss a change in place of one seen through the other, so a run that aliases stops here.

        Called at a record's start as well as at its end: an alias made outside any record, of which the call
        consumes one side (next_to_send pops one of two entries sharing a control and filters it), would leave one
        owner at the end, and the other lane's change unwritten. At the start, an entry the call is given
        (filter_entry's and with_owed's) counts as a place too."""
        raw = rec.roots["queue"][1]
        seen = {}

        def one(obj, what, at):
            w = seen.setdefault(id(obj), (what, at))
            if w != (what, at):
                raise SystemExit(f"trace3: node {nid}: one queue {what} stands in two places, {w[1]} and {at}, at "
                                 f"the record's {when}: the queue's values would miss a change of it in place")

        def entry(e, at):
            one(e, "entry", at)
            if e.control is not None:
                one(e.control, "entry's control", at)
                for j, m in enumerate(e.control.items):
                    one(m, "control message", at + (j,))
        for i, a in enumerate(args):            # the call's own entries
            if hasattr(a, "control") and hasattr(a, "chunk") and hasattr(a, "solicited"):
                entry(a, ("argument", i))
        for p in F._keys(raw):
            pq = F._peek(raw, p)
            for ln in ("urgent", "normal"):
                for k, e in enumerate(getattr(pq, ln)):
                    entry(e, (p, ln, k))

    def schema(self, ns):
        key = self.key

        def ghex(g):
            return g.hex()

        desc = self.descriptor          # the descriptor whole: the twin's code calls §1's N and K of it, and this
        #                                   encoder calls nothing

        # the twin's own tables: one line each in gen/schema.py; then the other sections' that §6.1 reads
        return schema.python_tables(F, key, fbits, lane=self.lane,
                                    waits=lambda w: [[int(p), self.wchunk(f)] for p, f in w] or None,
                                    jobs=lambda js: [[int(q), [key(m) for m in ids], fbits(at)]
                                                     for q, ids, at in js] or None, desc=desc) + [
            F.Table("known_id", [ghex, int], key, foreign=True),
            F.Table("chunks", [ghex, int], self.chunk, foreign=True),      # push_rebuilt's `chunks[g][i]`
        ]

    # ---- the wrappers, per node
    def install(self, nd, ns):
        consts = {c: fbits(ns[c]) for c in CONSTS}
        for c in LIMITS + ("MAX_PLAIN_CHUNKS", "FAN_IN"):     # each a count (a limit may be +inf, none): int() of
            v = ns[c]                                          #   anything else would cut it without a word
            if c in LIMITS and isinstance(v, float) and math.isinf(v) and v > 0:
                continue
            try:
                whole = v >= 0 and v == int(v)
            except (OverflowError, ValueError, TypeError):
                whole = False
            if not whole:
                raise SystemExit(f"trace3: node {nd.id}: {c} is no count: {v!r}")
        consts.update({c: None if math.isinf(ns[c]) else int(ns[c]) for c in LIMITS})
        consts["MAX_PLAIN_CHUNKS"] = int(ns["MAX_PLAIN_CHUNKS"])            # §2, read by valid_id
        consts.update({c: bool(ns[c]) for c in CARDS})                     # the writer's cards
        consts["FAN_IN"] = int(ns["FAN_IN"])
        consts.update({c: self.nat(ns[c]) for c in ("UNIT", "MAX_CHUNKS", "MAX_SEGMENT_SIZE")})   # §1's
        consts.update({c: fbits(ns[c]) for c in ("HEARTBEAT", "GOSSIP_FACTOR")})   # §6.4's
        consts["D_LAZY"] = self.nat(ns["D_LAZY"])
        consts["PACED"] = bool(ns["PACED"])                                # [c15]
        consts["HAVE_TTL"] = self.nat(ns["HAVE_TTL"])                      # §4.3's
        consts["GOSSIP_RETRANSMISSION"] = self.nat(ns["GOSSIP_RETRANSMISSION"])     # §4.5's (stock)
        consts["DESCRIPTOR_IN_CHUNK"] = bool(ns["DESCRIPTOR_IN_CHUNK"])    # §3's choice of design
        consts["PUSH_TTL"] = self.nat(ns["PUSH_TTL"])                      # §5.2's (note_push)
        consts["R"] = self.nat(ns["R"])                                    # §5.1's copies a chunk [c2]
        consts["R_NODE"] = self.nat(ns["R_NODE"])                          # §5.3's guard; by a node's uplink
        consts["GUARD_GRACE"] = fbits(ns["GUARD_GRACE"])                   #   class [c17]
        consts["UPLINK"] = fbits(ns["UPLINK"])                             # §5.1's stripe [c13]; the
        consts["STRIPE_UPLINK"] = fbits(ns["STRIPE_UPLINK"])               #   threshold infinite where card 13 is off
        w = ns.get("W", math.inf)                                          # §7.1's window; none where the
        if not math.isinf(w) and (w != int(w) or w < 0):                   #   node has none (card 14 off)
            raise SystemExit(f"trace3: node {nd.id}: W is no count of slots: {w!r}")
        consts["W"] = None if math.isinf(w) else int(w)
        consts["WINDOW_TIMEOUT"] = fbits(ns["WINDOW_TIMEOUT"])
        if ns["SOURCE_OFFERS"] not in ("ACK", "PUBLISH"):                  # v0.10.4: §5.1's choice of when the
            raise SystemExit(f"trace3: node {nd.id}: SOURCE_OFFERS is {ns['SOURCE_OFFERS']!r}")   # source announces
        consts["SOURCE_OFFERS"] = ns["SOURCE_OFFERS"]
        # what each traced name is at this node, and the node's own line
        replaced = []
        for name in self.traced:
            what, where = own_code(name, ns.get(name))
            if what == "replaced" and name in REPLACEABLE_WHOLE and not self.whole:
                raise SystemExit(f"trace3: node {nd.id}: {name} is something else than the document's here ({where}), "
                                 f"which only a trace of the whole state may have: a directed set's scenario")
            if what == "replaced" and name in REPLACEABLE:
                replaced.append(name)
            elif what != "own":
                raise SystemExit(f"trace3: node {nd.id}: {name} is traced, and its function here is neither "
                                 f"protocol.md's own code nor a listed wrapper of it: {where}")
        if self.nodes_written:
            raise SystemExit(f"trace3: node {nd.id} is installed after the trace's first record: its line cannot be "
                             f"written before its records")
        self.nodes.append((int(nd.id), consts, sorted(replaced)))
        self.WAIT = ns["WAIT"]                                               # next_to_send's "in line" (§7.2)
        if self.doc_message_id is None:     # the document's function, from the toy's wrapper's closure (own_code
            mid_fn = ns["message_id"]       #   found it there, or found the name to be the document's own)
            if getattr(getattr(mid_fn, "__code__", None), "co_filename", None) != DOC_FILE:
                mid_fn = next(c.cell_contents for c in mid_fn.__closure__ or ()
                              if getattr(getattr(c.cell_contents, "__code__", None), "co_filename", None) == DOC_FILE
                              and c.cell_contents.__code__.co_name == "message_id")
            self.doc_message_id = mid_fn
        mid_fn = ns["message_id"]           # and each node's own, by the same way
        if getattr(getattr(mid_fn, "__code__", None), "co_filename", None) != DOC_FILE:
            mid_fn = next(c.cell_contents for c in mid_fn.__closure__ or ()
                          if getattr(getattr(c.cell_contents, "__code__", None), "co_filename", None) == DOC_FILE
                          and c.cell_contents.__code__.co_name == "message_id")
        self.doc_mid[int(nd.id)] = mid_fn
        rec = F.Recorder()
        F.install(rec, ns, [t for t in self.schema(ns) if not (self.doc_v2 and t.name in WINDOW)])
        window = {} if self.doc_v2 else {name: ns[name] for name in WINDOW}    # the installed cell and views: each
        #                                                                         record's end checks they are still there
        st = {"depth": 0, "ext": 0, "cur": None}
        key, tr = self.key, self

        def sec61(name, fn):
            @functools.wraps(fn)
            def w(*args, **kw):
                if st["ext"]:                       # inside an interface call: not §6.1's own call
                    r = fn(*args, **kw)
                    if name == "message_id":        # m2_check there too: the node's store asks it
                        tr.m2_check(args[0], r, nd.id)
                    return r
                if st["depth"]:
                    st["reached"].add(name)
                    st["depth"] += 1
                    if name == "defer":             # a record's chain of defers, bounded as the
                        st["defers"] += 1           #   twin's fuel (deferDepth) is
                        if st["defers"] > DEFER_DEPTH:
                            raise SystemExit(f"trace3: node {nd.id}: a chain of {st['defers']} defers in one record, "
                                             f"past the twin's {DEFER_DEPTH} (deferDepth)")
                    try:
                        r = fn(*args, **kw)
                        if name == "message_id":    # its content_id, a question at every call
                            tr.content_id_asked(st["cur"]["tape"], args[0], r, nd.id)
                        return r
                    finally:
                        st["depth"] -= 1
                        if name == "defer":
                            st["defers"] -= 1
                if not tr.nodes_written:            # the nodes line, before the first record
                    tr.write_nodes()
                tr.cur_queue = F.unwrap(ns["queue"])    # rarest's peer, by its queue (args_of)
                tr.cur_nid = int(nd.id)
                r_ = {"n": nd.id, "t": fbits(ns["now"]), "fn": name, "args": tr.args_of(name, args, kw), "tape": []}
                tr.ib = {}                          # installed_block's answers in this record
                tr.built_objs = {}                  # the chunks this record's publish built and stored
                before = rec.snapshot() if tr.whole else None

                def finish(**out):
                    rec.on = False
                    for wname, wobj in window.items():      # a name of the window's rebound to another object
                        if ns[wname] is not wobj:           #   would go on unlogged
                            raise SystemExit(f"trace3: node {nd.id}: {wname} no longer holds the tracer's own object "
                                             f"at the end of {name}: {type(ns[wname]).__name__}")
                    r_["reads"], r_["scans"], r_["writes"] = rec.footprint()
                    r_["rest"] = rec.rest(tr.whole)
                    if tr.whole:
                        tr.account(rec, r_, before)
                    tr.rest_total += len(r_["rest"])
                    r_.update(out)
                    # last, in this order: which traced functions the call reached, itself among them, and which
                    # of the own tables it touched. The replay checks both; a mutant is replayed only on the
                    # records that name its function or its table (mutants3.py), picked by these two members
                    r_["reached"] = sorted(st["reached"])
                    r_["tables"] = sorted({e[0] for e in r_["reads"]} | {s[0] for s in r_["scans"]}
                                          | {e[0] for e in r_["writes"]})
                    if "queue" in r_["tables"]:      # the queue as values holds only where no entry is aliased
                        tr.alias_check(rec, nd.id)
                    if "pending" in r_["tables"]:    # no copy waits twice under one root
                        tr.pending_check(rec, nd.id)
                    tr.counts[name + (" (raises)" if "raises" in out else "")] += 1
                    tr.write(r_)

                rec.clear()
                if "queue" in rec.roots:            # before the call too, with its own entries, so
                    tr.alias_check(rec, nd.id, args, "start")   # that an alias the call consumes cannot hide
                rec.tape = r_["tape"]
                st["cur"], st["depth"], st["reached"], st["defers"] = r_, 1, {name}, 1 if name == "defer" else 0
                mesh_on()
                rec.on = True
                if name == "rarest":            # v2's choose passes the raw queue it took outside a record;
                    args = (ns["queue"][r_["args"][0]],)    # the view of queue[p] logs its read of the lane
                try:
                    r = fn(*args, **kw)
                    if name == "message_id":        # its content_id, a question at every call
                        tr.content_id_asked(r_["tape"], args[0], r, nd.id)
                except Exception as e:              # written with the state it left; the exception goes on
                    if isinstance(e, KeyError):     # which key was missing: the place it raised
                        (miss,) = e.args
                        if not isinstance(miss, int):
                            raise TypeError(f"trace3: a KeyError on a key that is not a peer: {miss!r}") from e
                        finish(raises=type(e).__name__, raises_key=miss)
                    else:
                        finish(raises=type(e).__name__)
                    raise
                finally:
                    rec.on = False
                    mesh_off()
                    st["depth"], st["cur"] = 0, None
                finish(ret=tr.ret_of(name, r))
                return r
            return w

        def iface(name, fn, enc):
            @functools.wraps(fn)
            def w(*args, **kw):
                if not st["depth"] or st["ext"]:    # not asked by §6.1's own code
                    return fn(*args, **kw)
                # the tracer's third state: what the rest of the node reads is behind the tape, but its
                # accesses of the own tables are logged apart, as the callee's `cr` and `cw`
                st["ext"] += 1
                rec.begin_callee()
                mesh_off()
                raised = None
                try:
                    r = fn(*args, **kw)
                except Exception as e:              # a question that raises: on the tape, for CALLS
                    raised = e
                    raise
                finally:
                    st["ext"] -= 1
                    cr, cw = rec.end_callee()
                    mesh_on()
                    if raised is not None and name in calls:
                        if cr or cw:
                            raise TypeError(f"trace3: {name} raised after touching the own tables")
                        st["cur"]["tape"].append([name, calls[name][0](*args, **kw), {"raises": type(raised).__name__}])
                st["cur"]["tape"].append([name, *enc(r, *args, **kw)] + ([{"cr": cr, "cw": cw}] if cr or cw else []))
                return r
            return w

        def mesh_on():                              # the block's code sees `mesh` as the question it asks,
            m = ns.get("mesh")                      #   and the gossip history as the node's
            if isinstance(m, set):
                ns["mesh"] = MeshQuestion(m, lambda: st["cur"]["tape"])
            h = ns.get("gossip_history")
            if h is not None and not isinstance(h, GossipQuestion):
                ns["gossip_history"] = GossipQuestion(h, lambda: st["cur"]["tape"], key, tr.chunk)

        def mesh_off():                             # and everything else, the set and the history themselves
            m = ns.get("mesh")
            if isinstance(m, MeshQuestion):
                ns["mesh"] = m.m
            h = ns.get("gossip_history")
            if isinstance(h, GossipQuestion):
                ns["gossip_history"] = h.h

        def after_args(delay, fn, *args):
            if fn.__name__ == "promise_due":                # filter_entry's `after(PROMISE, promise_due, a, p, now)`
                a, p, at = args
                return [fbits(delay), fn.__name__, [key(a), int(p), fbits(at)]]
            if fn.__name__ == "window_timeout":             # track_in_flight's `after(WINDOW_TIMEOUT,
                k, at = args                                #   window_timeout, key, now)`
                return [fbits(delay), fn.__name__, [[int(k[0]), k[1].hex(), int(k[2])], fbits(at)]]
            out = []
            for x in args:
                if isinstance(x, (bytes, self.Wm.WantIndex)):
                    out.append(key(x))
                else:
                    raise TypeError(f"§6.1 arms timers on keys only, got {x!r}")
            return [fbits(delay), fn.__name__, out]

        enc = {     # the tape's calls: TAPE's names, and only those (checked below)
            "expired": lambda r, g: [[g.hex()], bool(r)],
            "connected_topic_peers": lambda r: [[], list(r)],
            "own_order": lambda r, xs, a: [[list(xs), key(a)], list(r)],
            "listed": lambda r, p: [[p], int(r)],
            "authenticable": lambda r, g: [[g.hex()], bool(r)],
            # a draw of ask keys; of peers (the mesh: its own order was put on the tape where shuffled read it)
            # or of indices (push_rebuilt's)
            "shuffled": lambda r, xs: [[[tr.drawn(a) for a in (xs.m if isinstance(xs, MeshQuestion) else xs)]],
                                       [tr.drawn(a) for a in r]],
            "valid_have": lambda r, e: [[tr.ihave_entry(e)], bool(r)],    # asked by on_ihave of a bitmap
            "penalise": lambda r, p: [[p], None],
            "enqueue": lambda r, p, x, urgent=False: [[p, ["entry", tr.qentry(x)] if isinstance(x, tr.Wm.Entry)
                                                       else tr.control(x) if isinstance(x, tr.Wm.Control)
                                                       else ["chunk", tr.chunk(x)], bool(urgent)], bool(r)],
            "after": lambda r, delay, fn, *args: [after_args(delay, fn, *args), None],
            # §4.2
            "seen": lambda r, m: [[m.hex()], bool(r)],
            "accepted": lambda r, m: [[m.hex()], bool(r)],
            "mark_seen": lambda r, m: [[m.hex()], None],
            "live": lambda r, slot: [[int(slot)], bool(r)],
            "open_group": lambda r, g, f: [[g.hex(), tr.chunk(f)], None],
            # (in a publish record the chunk stored is one the block built: written as built)
            "store": lambda r, g, i, f: [[g.hex(), int(i), tr.built(f) if st["cur"]["fn"] == "publish" else tr.chunk(f)],
                                         None],
            "start": lambda r, fn, g: [[fn.__name__, g.hex()], None],
            # the deferral path's questions (defer and tie are the twin's own)
            "installed_block": lambda r, slot, root: [[int(slot), root.hex()], tr.installed(slot, root, r)],
            "admitted": lambda r, p, f: [[p, tr.chunk(f)], bool(r)],
            "reserve": lambda r, p, f: [[p, tr.chunk(f)], bool(r)],
            "release": lambda r, p, f: [[p, tr.chunk(f)], None],
            "bid_group": lambda r, root: [[root.hex()], None if r is None else r.hex()],
            # the writer's questions and calls
            "has_room": lambda r, p: [[p], bool(r)],
            "pop_owed_answer": lambda r, p: [[p], tr.chunk(r)],
        }
        blobs = lambda xs: [tr.blob(x) for x in xs]     # noqa: E731
        calls = {   # CALLS' questions: how each one's arguments, and its answer, are written
            "sha256": (lambda b: [b.hex()], lambda r: r.hex()),
            "serialize": (lambda d: [tr.descriptor(d)], lambda r: r.hex()),
            "snappy_block_encode": (lambda b: [tr.blob(b)], tr.blob),
            "pad_each": (lambda segs, size: [blobs(segs), tr.nat(size)], blobs),
            "rs_parity": (lambda segs, k: [blobs(segs), tr.nat(k)], blobs),
            "merkle_root": (lambda leaves: [blobs(leaves)], lambda r: r.hex()),
            "merkle_proof": (lambda leaves, i: [blobs(leaves), tr.nat(i)], lambda r: [x.hex() for x in r]),
            # §6.4's
            "connected": (lambda q: [int(q)], tr.boolean),
            "group_bits": (lambda ids: [[key(m) for m in ids]], lambda r: [[g.hex(), b.v] for g, b in r]),
            "topic_peers": (lambda: [], lambda r: [int(q) for q in r]),
            "gossip_eligible": (lambda q: [int(q)], tr.boolean),
            "sample_without_replacement": (lambda xs, k: [[int(q) for q in xs], tr.nat(k)], lambda r: [int(q) for q in r]),
            # §4.6's, on_iwant's and on_frame's
            "close_promises_of_group": (lambda g: [g.hex()], tr.nothing),
            "discard_queued": (lambda g: [g.hex()], tr.nothing),
            "discard_paced": (lambda g: [g.hex()], tr.nothing),
            "resolve": (lambda a: [key(a)], lambda r: None if r is None else r.hex()),
            "chunk_of": (lambda mid: [mid.hex()], tr.chunk),
            "handle_graft_prune": (lambda p, frame: [int(p)], tr.no_prunes),
            # decode_group's and push_rebuilt's
            "decode_and_reencode": (lambda cg, d: [tr.store_group(cg), tr.descriptor(d)], tr.rebuilt),
            "payload_of": (lambda rebuilt: [tr.rebuilt(rebuilt)], tr.payload),
            "deliver": (lambda g, payload: [g.hex(), tr.payload(payload)], tr.nothing),
            "wake": (lambda p: [int(p)], tr.nothing),               # owe's
            # the push order's keys: a chunk's tie-break for a peer (asked by the chunk's id), a number;
            # a peer's id, bytes
            "tiebreak": (lambda f, p: [tr.mid_of(f).hex(), int(p)], tr.nat),
            "peer_id_bytes": (lambda p: [int(p)], lambda r: bytes(r).hex()),
            "verify_merkle_proof": (lambda root, data, index, count, proof:
                                    [root.hex(), tr.blob(data), tr.nat(index), tr.nat(count), [x.hex() for x in proof]],
                                    tr.boolean),
            "block_root": (lambda b: [tr.block(b)], lambda r: bytes(r).hex()),     # publish's
        }
        if set(calls) != set(CALLS):
            raise SystemExit(f"trace3: the questions with their own encoders are not CALLS': {sorted(set(calls) ^ set(CALLS))}")
        for name, (ea, er) in calls.items():
            enc[name] = lambda r, *a, _ea=ea, _er=er: [_ea(*a), _er(r)]
        # the namespace must agree with the documents' source: no traced function is v2's, and under --doc v2 every
        # name of the block that v2 defines is v2's here (two derivations of the set, each checking the other)
        if set(enc) != set(TAPE):
            raise SystemExit(f"trace3: the tape's calls are not TAPE's: {sorted(set(enc) ^ set(TAPE))}")
        why = namespace_check(BLOCK, tr.traced, tr.v2_defs, ns)
        if why:
            raise SystemExit(f"trace3: node {nd.id}: {why}")
        # a traced name this node runs as something else: the node's, a call on the tape where the block's
        # code calls it (on_frame's on_iwant), with its log; never a record
        replaced_enc = {"forward": lambda r, f, p: [[tr.chunk(f), int(p)], tr.nothing(r)],
                        "on_iwant": lambda r, p, iw: [[int(p), [tr.ask_key(a) for a in iw.ids]],
                                                      [tr.chunk(f) for f in r]],
                        "push_rebuilt": lambda r, g, new: [[g.hex(), [tr.nat(i) for i in new]], tr.nothing(r)],
                        "validate_chunk": lambda r, f: [[tr.chunk(f)], r]}
        if set(replaced_enc) != set(REPLACEABLE):
            raise SystemExit("trace3: the replaceable names' encoders are not REPLACEABLE's")
        for name in tr.traced:
            ns[name] = iface(name, ns[name], replaced_enc[name]) if name in replaced else sec61(name, ns[name])
        tr.bound.append((nd, ns, {name: ns[name] for name in tr.traced}))      # for final_check
        for name, e in enc.items():
            ns[name] = iface(name, ns[name], e)


class GossipQuestion:
    """The gossip history as the block's own code sees it: the node's. `gossip_ids()` is a question on the tape
    with its answer, ["gossip_ids", [], [id...]]. Any other use raises."""
    __slots__ = ("h", "tape", "key", "chunk")

    def __init__(self, h, tape, key, chunk):
        self.h, self.tape, self.key, self.chunk = h, tape, key, chunk

    def put(self, f):                   # forward's `gossip_history.put(f)`, a call that returns
        r = self.h.put(f)               #   nothing
        if r is not None:
            raise TypeError(f"trace3: gossip_history.put returned {r!r}")
        self.tape().append(["gossip_put", [self.chunk(f)], None])

    def gossip_ids(self):
        r = self.h.gossip_ids()
        self.tape().append(["gossip_ids", [], [self.key(m) for m in r]])
        return r

    def remove_group(self, g):          # drop_group's: the stock cache's, a call that returns nothing
        r = self.h.remove_group(g)
        if r is not None:
            raise TypeError(f"trace3: gossip_history.remove_group returned {r!r}")
        self.tape().append(["gossip_remove_group", [g.hex()], None])


class MeshQuestion:
    """`mesh` as the block's own code sees it: `mesh | {p}`, whose iteration is a question on the tape with its
    answer, ["mesh_and", [p], [q...]], in the order the Python iterates the set the untraced code makes; a
    membership test, `q in mesh`, ["mesh_has", [q], the answer]; and its own iteration, `for q in mesh`, ["mesh",
    [], [q...]]. The set itself is not copied, since a copy can iterate in another order. Any other use raises."""
    __slots__ = ("m", "tape")

    def __init__(self, m, tape):
        self.m, self.tape = m, tape

    def __contains__(self, q):
        r = q in self.m
        self.tape().append(["mesh_has", [int(q)], r])
        return r

    def __iter__(self):                 # `for q in mesh`, the peers in the order the set iterates
        order = list(self.m)
        self.tape().append(["mesh", [], [int(q) for q in order]])
        return iter(order)

    def __or__(self, other):
        if not isinstance(other, set):
            raise TypeError(f"trace3: mesh | {other!r}: the mesh question takes a set of peers")
        return _MeshAnd(self, list(other), list(set.__or__(self.m, other)))


class _MeshAnd:
    __slots__ = ("q", "p", "order")

    def __init__(self, q, p, order):
        self.q, self.p, self.order = q, p, order

    def __iter__(self):
        self.q.tape().append(["mesh_and", self.p, list(self.order)])
        return iter(self.order)


def main(argv):
    toy, out, rest = Path(argv[0]).resolve(), argv[1], argv[2:]
    tr = Tracer3(toy, out, rest)
    orig = tr.N.Node._override

    def _override(self, ns):
        orig(self, ns)
        tr.install(self, ns)

    tr.N.Node._override = _override
    import run                          # noqa: E402: the toy's run.py, from TOYDIR
    try:
        run.main(rest)
    finally:
        tr.close()
    print(f"trace3: {sum(tr.counts.values())} records, {dict(sorted(tr.counts.items()))}", file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test-v2"]:
        sys.exit(v2_kept_self_test())
    main(sys.argv[1:])
