#!/usr/bin/env python3
"""Controls of footprint.py: one case for each line of its contract.

    python3 footprint_test.py            # exit code 0 when every case is as the contract says
    python3 footprint_test.py --broken   # the control: with views that do not log `k in t`, it must exit 1

Small tables of plain containers, a recorder, and one access each. Prints a line per case. The cases marked
"limit" show what is NOT logged: they pass when the log is indeed silent, so that the limit is a known one and a
change of it shows here.

Then the same views over the pinned toy's own lazy tables (`toy/bits.py`, spec v0.10, where a read allocates
nothing and a detached entry joins its map at its first write, §8.1): a read of a missing entry is logged and
leaves nothing in the container, and a write through a detached entry is logged and stays. Also a one-level set
value (asked_parked's shape), a count that reads 0 (DefaultMap), a lazy table of another section, and an entry
emptied and left; its controls are four broken views (--broken, --broken-level, --broken-alloc, --broken-copy),
each failing its own cases. (tied's three levels: below.)

A call the block makes on the tape keeps its own log (`cr`, `cw`, other sections' tables transparent in it,
`offers.listed` its one attribute read), another section's level iterated by the block puts its keys on the tape,
and `mesh | {p}` is a question answered in the Python's order (trace3.py). Their controls: --broken-callee (no log
apart), --broken-keys (1), --broken-mesh (a sorted answer: 1).

Presence: `tied`'s three levels over the toy's own `tie_table()`, each row that is there an entry, True, and a
bitmap there and empty 0. Its controls: --broken-rows (no row observed above an entry touched; P9 fails by the
order of its reads) and --broken-bread (a block's read of an entry a callee read, or one observed, first, not
taken as the block's read: 2). And --broken-order, a recorder that keeps a callee's own order of touches in its
log and the record.

The record's run (`record.sh`) holds how many cases each control fails: the numbers are written there, beside each
option, and a control that fails another number of cases fails the run. --broken-pop-miss: views that take a pop
that finds nothing as a write too (M1, M2, M4 and M6, and `sent`'s W15).

The queue: `queue` over the pinned toy's own PeerQueue (two lanes, `urgent` and `normal`, as attributes), its rows
kept, its top level's order asked. Cases Q1 to Q11: a lane read, a missing peer's lane, an append to a detached
queue in a callee (enqueue's), a lane assigned whole (drop_offer's filter), an entry changed in place
(drop_offer's removal of an IWANT's id, add_ihave), a lane emptied and left in its row, `list(queue)` by the block
(read whole, its order on the tape) and in a callee (read, no order), another attribute of a PeerQueue refused,
and an alias (one entry in two lanes), which trace3.py's alias check must refuse. Their controls: --broken-lanes
(a lane's attribute not taken as a key), --broken-ordered (no order on the tape) and --broken-alias (an alias
check that refuses nothing). A row made in a call: Q3 writes both lanes of the row it makes, and Q12 checks a row
made by one callee and read by a later one against the tables at both ends; their control is --broken-made-rows.
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import footprint as F                   # noqa: E402
import layout                           # noqa: E402


class Bits:                             # a value changed in place, as the toy's bitmaps are
    def __init__(self, v=0):
        self.v = v

    def set(self, i):
        self.v |= 1 << i

    def has(self, i):
        return bool(self.v >> i & 1)


def fresh():
    ns = {
        "flat": {"a": 1, "b": 2},                               # flat[k] -> a number
        "deep": defaultdict(dict, {"a": {1: 10, 2: 20}}),       # deep[k][p] -> a number
        "bits": {"a": Bits(1)},                                 # bits[k] -> a bitmap, changed in place
        "armed": {"a", "b"},                                    # a set: its members are its entries
        "other": {"q": [1]},                                    # another section's table
    }
    tables = [
        F.Table("flat", [str], lambda v: v),
        F.Table("deep", [str, int], lambda v: v),
        F.Table("bits", [str], lambda b: b.v or None),
        F.Table("armed", [str], lambda x: True),
        F.Table("other", [str], lambda v: list(v) or None, foreign=True),
    ]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    return ns, rec, raw


def fresh_lazy():
    """The pinned toy's lazy tables, each with one entry stored: `tried` as lazy(lazy_dict), `offered` as
    lazy2(LazyBits), `offers` as OfferMap, `sets` as lazy(LazySet) (asked_parked's kind)."""
    toy = layout.toy()
    sys.path.insert(0, str(toy))
    import bits as B                    # noqa: E402: the pinned toy's
    sys.path.remove(str(toy))
    ns = {"tried": B.lazy(B.lazy_dict), "offered": B.lazy2(B.LazyBits), "offers": B.OfferMap(), "sets": B.lazy(B.LazySet),
          "pset": B.lazy(B.LazySet), "cnt": B.DefaultMap(0), "omine": B.lazy(B.LazyBits)}
    ns["tried"]["a"][1] = 10
    ns["offered"][1]["g"].set(0)
    ns["offers"]["a"].append(1)
    ns["sets"]["c"].add(1)
    tables = [
        F.Table("tried", [str, int], lambda v: v),
        F.Table("offered", [int, str], lambda b: b.v or None),
        F.Table("offers", [str], lambda l: list(l) or None),
        F.Table("sets", [str, int], lambda x: True),
        F.Table("pset", [str], lambda s: sorted(s) or None),            # asked_parked's shape: one level, a set value
        F.Table("cnt", [int], lambda n: n or None),                     # ihave_frames' kind: a count that reads 0
        F.Table("omine", [str], lambda b: b.v or None, foreign=True),    # a lazy table of another section, as mine
    ]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    return ns, rec, raw


def fresh_tied():
    """`tied` as the pinned toy makes it (`tie_table()`: root -> peer -> group -> indices), with presence: r1's
    peer 1 has g = {0}; r1's peer 3 has g there and empty (set, then cleared); r2's peer 2 is a row there and empty
    (its one group popped); and `flat` of fresh()."""
    toy = layout.toy()
    sys.path.insert(0, str(toy))
    import bits as B                    # noqa: E402: the pinned toy's
    sys.path.remove(str(toy))
    tied = B.tie_table()
    tied["r1"][1]["g"].set(0)
    tied["r1"][3]["g"].set(1)
    tied["r1"][3]["g"].clear(1)
    tied["r2"][2]["h"].set(0)
    tied["r2"][2].pop("h")
    ns = {"tied": tied, "flat": {"a": 1, "b": 2}}
    tables = [F.Table("tied", [str, int, str], lambda b: b.v, rows=True), F.Table("flat", [str], lambda v: v)]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    return ns, rec, raw


def fresh_planned():
    """`planned` (group -> index -> the peers chosen), a table that keeps its rows and whose `g in planned` is a
    read of the row's own entry (`presence_in`): g1 with index 0 for peers 2 and 5 and index 1 for none; and
    `flat` of fresh()."""
    ns = {"planned": {"g1": {0: {5, 2}, 1: set()}}, "flat": {"a": 1, "b": 2}}
    tables = [F.Table("planned", [str, int], lambda v: sorted(v), rows=True, presence_in=True),
              F.Table("flat", [str], lambda v: v)]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    return ns, rec, raw


def fresh_ordered():
    """fresh_tied()'s `tied` with its ordered levels (a root's peers, a peer's groups), and `ts`, a table keyed by
    a pair whose top level is ordered (tie_slot's shape): (r1, 1) -> 5, (r2, 2) -> 6."""
    ns, rec, raw = fresh_tied()
    t = rec.roots["tied"][0]
    t.ordered_levels = (1, 2)
    ts = {("r1", 1): 5, ("r2", 2): 6}
    tt = F.Table("ts", [lambda k: [k[0], k[1]]], int, ordered=True)
    rec.roots["ts"] = (tt, ts)
    ns["ts"] = F.View(rec, tt, (), ts)
    raw["ts"] = ts
    return ns, rec, raw


def fresh_queue():
    """`queue` as the pinned toy makes it (lazy(PeerQueue)): peer 1's normal lane holds one entry, an IWANT of "a"
    and "b", and its urgent lane is empty; peer 2 is a row there with both lanes empty (an entry put, then taken).
    A lane is written here as [chunk, [[kind, ids], ...] or None, solicited], the ids as they are."""
    toy = layout.toy()
    sys.path.insert(0, str(toy))
    import bits as B                    # noqa: E402: the pinned toy's
    import node as N                    # noqa: E402
    import wire as W                    # noqa: E402
    sys.path.remove(str(toy))
    F.ATTR_LEVELS[N.PeerQueue] = ("urgent", "normal")
    F.ATTR_READS[N.PeerQueue] = {"has_chunks": ("normal",)}
    queue = B.lazy(N.PeerQueue)
    queue[1].normal.append(W.Entry(control=W.IWANT(["a", "b"])))
    queue[2].normal.append(W.Entry(chunk="c"))
    queue[2].normal.pop()

    def lane(entries):
        return [[e.chunk, [[m.kind, list(m.ids)] for m in e.control.items] if e.control else None, e.solicited]
                for e in entries]
    ns = {"queue": queue, "flat": {"a": 1, "b": 2}}
    tables = [F.Table("queue", [int, str], lane, rows=True, ordered=True), F.Table("flat", [str], lambda v: v)]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    QW[0] = W
    return ns, rec, raw


QW = [None]                             # the toy's wire module, for the queue cases' entries
VALUES_ORDERED = [True]                 # --broken-values-order: the flag not set


def fresh_list(jobs=((4, ["x"], 1.0), (5, ["x", "y"], 1.0))):
    """`pq`, a list of the namespace as §6.4's `pace_queue` is, a table of the one entry `jobs`; two jobs in it,
    each (peer, ids, time). And `flat` of fresh()."""
    ns = {"pq": list(jobs), "flat": {"a": 1, "b": 2}}
    tables = [F.Table("pq", [str], lambda js: [[q, list(ids), at] for q, ids, at in js] or None),
              F.Table("flat", [str], lambda v: v)]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    return ns, rec, raw


def fresh_list_empty():
    return fresh_list(jobs=())




def fresh_window(count=1, line=(5, 7)):
    """§7.1's three as the node has them: `in_flight`, a number; `waiters`, a deque; `sent`, a dict from a send's
    key to its time, one send in it. And W."""
    import collections
    ns = {"in_flight": count, "waiters": collections.deque(line), "sent": {(5, "g", 3): 0.25}, "W": 2}
    tables = [F.Table("in_flight", [str], lambda n: None if n == 0 else n if n > 0 else ["-", -n]),
              F.Table("waiters", [str], lambda o: list(o) or None),
              F.Table("sent", [lambda k: list(k)], lambda t: t)]
    rec = F.Recorder()
    raw = dict(ns)
    F.install(rec, ns, tables)
    rec.tape = []
    return ns, rec, raw


def stored(raw, name, k):
    """Whether the container itself holds k (no read through the views, no allocation)."""
    t = raw[name]
    d = getattr(t, "_d", None)
    return k in (d if isinstance(d, dict) else dict.keys(t))


REC = [None]                            # the case's recorder, for `callee`


def callee(fn):
    """`fn` run as a call the block makes on the tape, as trace3.py's `iface` runs one: its `cr` and `cw` go on the
    tape as ["call", cr, cw] when it touched an own table, and nothing goes there otherwise."""
    rec = REC[0]
    rec.begin_callee()
    try:
        fn()
    finally:
        cr, cw = rec.end_callee()
    if cr or cw:
        rec.tape.append(["call", cr, cw])


def fresh_other2():
    """fresh(), with a second key in another section's table, stored after the first."""
    ns, rec, raw = fresh()
    raw["other"]["b"] = [2]
    return ns, rec, raw


def case(name, body, reads=(), scans=(), writes=(), rest=(), tape=(), raises=None, limit=False, make=None, post=None):
    ns, rec, raw = (make or fresh)()
    REC[0] = rec
    rec.clear()
    rec.on = True
    got = None
    try:
        body(ns, raw)
    except Exception as e:              # noqa: BLE001
        got = type(e).__name__
    rec.on = False
    r, s, w = rec.footprint()
    out = {"reads": r, "scans": s, "writes": w, "rest": rec.rest(False), "tape": rec.tape, "raises": got}
    want = {"reads": [list(x) for x in reads], "scans": [list(x) for x in scans], "writes": [list(x) for x in writes],
            "rest": [list(x) for x in rest], "tape": [list(x) for x in tape], "raises": raises}
    if post is not None:                # what the container holds after the call
        out["post"], want["post"] = post(raw), True
    ok = out == want
    diff = "" if ok else "  <-- FAIL: " + "; ".join(f"{k}: {out[k]!r}, must be {want[k]!r}" for k in want if out[k] != want[k])
    print(f"{'limit' if limit else 'case'}, {name}: {'as the contract says' if ok else 'NOT'}{diff}")
    return ok


def main():
    ok = True
    # ---- reads
    ok &= case("t[k]", lambda ns, raw: ns["flat"]["a"], reads=[["flat", ["a"], 1]])
    ok &= case("t.get(k) of a missing entry", lambda ns, raw: ns["flat"].get("z"), reads=[["flat", ["z"], None]])
    ok &= case("k in t", lambda ns, raw: "b" in ns["flat"], reads=[["flat", ["b"], 2]])
    ok &= case("t[k][p]", lambda ns, raw: ns["deep"]["a"][1], reads=[["deep", ["a", 1], 10]])
    ok &= case("p in t[k]", lambda ns, raw: 3 in ns["deep"]["a"], reads=[["deep", ["a", 3], None]])
    ok &= case("a level read as a whole: iteration", lambda ns, raw: list(ns["flat"]),
               reads=[["flat", ["a"], 1], ["flat", ["b"], 2]], scans=[["flat", []]])
    ok &= case("a level read as a whole: items() of a row", lambda ns, raw: list(ns["deep"]["a"].items()),
               reads=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]], scans=[["deep", ["a"]]])
    ok &= case("a level read as a whole: len, of the table", lambda ns, raw: len(ns["deep"]),
               reads=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]], scans=[["deep", []]])
    ok &= case("t.get(k) of a missing row: the row read as a whole, and empty", lambda ns, raw: ns["deep"].get("z"),
               scans=[["deep", ["z"]]])
    ok &= case("a member of a set", lambda ns, raw: "a" in ns["armed"], reads=[["armed", ["a"], True]])
    # ---- writes
    ok &= case("t[k] = v, of an entry that was there: its value before is in the rest",
               lambda ns, raw: ns["flat"].__setitem__("a", 7), writes=[["flat", ["a"], 7]], rest=[["flat", ["a"], 1]])
    ok &= case("t[k] = v, of an entry that was not", lambda ns, raw: ns["flat"].__setitem__("z", 7),
               writes=[["flat", ["z"], 7]])
    ok &= case("t[k] = v, to the value it had: a write all the same",
               lambda ns, raw: ns["flat"].__setitem__("a", 1), writes=[["flat", ["a"], 1]], rest=[["flat", ["a"], 1]])
    ok &= case("del t[k]", lambda ns, raw: ns["flat"].__delitem__("a"), writes=[["flat", ["a"], None]],
               rest=[["flat", ["a"], 1]])
    ok &= case("t.pop(k): a read and a write", lambda ns, raw: ns["flat"].pop("a"), reads=[["flat", ["a"], 1]],
               writes=[["flat", ["a"], None]])
    # ---- a pop that finds nothing: a read, and no write (M1 to M7; their control: --broken-pop-miss)
    ok &= case("M1 t.pop(k, None) of a missing entry: a read alone", lambda ns, raw: ns["flat"].pop("z", None),
               reads=[["flat", ["z"], None]])

    def there_and_empty(ns, raw):       # asked_parked's shape: a set emptied by discard stays in its map, empty
        ns["pset"]["k"].add(3)
        ns["pset"]["k"].discard(3)
        assert stored(raw, "pset", "k"), "the fixture's entry is not there"
        ns["pset"].pop("k", None)
    ok &= case("M2 an entry there and empty, popped: a read alone (a record holds it as missing, before and after)",
               there_and_empty, reads=[["pset", ["k"], None]], make=fresh_lazy,
               post=lambda raw: not stored(raw, "pset", "k"))
    ok &= case("M3 a level popped that is not there: read as a whole, nothing written",
               lambda ns, raw: ns["deep"].pop("zz", None), scans=[["deep", ["zz"]]])
    ok &= case("M4 a root's row popped that is not there (tied.pop(root, {})): its row read, the level read as a "
               "whole, nothing written", lambda ns, raw: ns["tied"].pop("r9", None), reads=[["tied", ["r9"], None]],
               scans=[["tied", ["r9"]]], make=fresh_tied)
    ok &= case("M5 a row that is there with nothing under it, popped (tied[root].pop(p, None)): its presence written",
               lambda ns, raw: ns["tied"]["r2"].pop(2, None), reads=[["tied", ["r2", 2], True]],
               scans=[["tied", ["r2", 2]]], writes=[["tied", ["r2", 2], None]],
               rest=[["tied", ["r2"], True]], make=fresh_tied)        # (the root's row above it: observed)
    ok &= case("M6 a callee's pop that finds nothing: in its cr, and no write of the callee's or the call's",
               lambda ns, raw: callee(lambda: ns["flat"].pop("z", None)), tape=[["call", [["flat", ["z"], None]], []]])
    ok &= case("M7 a callee's pop that finds its entry: its write, the callee's and the call's",
               lambda ns, raw: callee(lambda: ns["flat"].pop("a", None)),
               tape=[["call", [["flat", ["a"], 1]], [["flat", ["a"], None]]]], writes=[["flat", ["a"], None]],
               rest=[["flat", ["a"], 1]])
    ok &= case("read, then written", lambda ns, raw: ns["flat"].__setitem__("a", ns["flat"]["a"] + 1),
               reads=[["flat", ["a"], 1]], writes=[["flat", ["a"], 2]])
    ok &= case("a set's discard of a member", lambda ns, raw: ns["armed"].discard("a"),
               writes=[["armed", ["a"], None]], rest=[["armed", ["a"], True]])
    ok &= case("a set's discard of what is not a member: a write all the same",
               lambda ns, raw: ns["armed"].discard("z"), writes=[["armed", ["z"], None]])
    ok &= case("a set's add", lambda ns, raw: ns["armed"].add("z"), writes=[["armed", ["z"], True]])
    ok &= case("a value changed in place: a write of its entry", lambda ns, raw: ns["bits"]["a"].set(3),
               reads=[["bits", ["a"], 1]], writes=[["bits", ["a"], 9]])
    ok &= case("a row deleted whole: every entry under it written",
               lambda ns, raw: ns["deep"].__delitem__("a"),
               writes=[["deep", ["a", 1], None], ["deep", ["a", 2], None]],
               rest=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]])
    ok &= case("a level read as a whole: a truth test", lambda ns, raw: bool(ns["flat"]),
               reads=[["flat", ["a"], 1], ["flat", ["b"], 2]], scans=[["flat", []]])
    ok &= case("a level read as a whole: keys()", lambda ns, raw: list(ns["flat"].keys()),
               reads=[["flat", ["a"], 1], ["flat", ["b"], 2]], scans=[["flat", []]])
    ok &= case("a level read as a whole: values()", lambda ns, raw: list(ns["flat"].values()),
               reads=[["flat", ["a"], 1], ["flat", ["b"], 2]], scans=[["flat", []]])
    ok &= case("t == u, two tables: both read as a whole", lambda ns, raw: ns["flat"] == ns["armed"],
               reads=[["flat", ["a"], 1], ["flat", ["b"], 2], ["armed", ["a"], True], ["armed", ["b"], True]],
               scans=[["flat", []], ["armed", []]])
    ok &= case("a set's remove of a member: a read and a write", lambda ns, raw: ns["armed"].remove("a"),
               reads=[["armed", ["a"], True]], writes=[["armed", ["a"], None]])
    ok &= case("a table cleared: every entry under it written", lambda ns, raw: ns["flat"].clear(),
               writes=[["flat", ["a"], None], ["flat", ["b"], None]], rest=[["flat", ["a"], 1], ["flat", ["b"], 2]])
    ok &= case("a row popped whole: read as a whole, and every entry under it written",
               lambda ns, raw: ns["deep"].pop("a"),
               reads=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]], scans=[["deep", ["a"]]],
               writes=[["deep", ["a", 1], None], ["deep", ["a", 2], None]])
    ok &= case("a row assigned whole: what was under it written, and what is under it now, which was missing before",
               lambda ns, raw: ns["deep"].__setitem__("a", {3: 30}),
               writes=[["deep", ["a", 1], None], ["deep", ["a", 2], None], ["deep", ["a", 3], 30]],
               rest=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]])
    # ---- a level assigned as a whole, and touched again in the same call
    def then_read(ns, raw):
        ns["deep"]["a"] = {3: 30}
        ns["deep"]["a"][3]
    ok &= case("a row assigned whole, then an entry it brought read: no read of it, it was missing before the call",
               then_read,
               writes=[["deep", ["a", 1], None], ["deep", ["a", 2], None], ["deep", ["a", 3], 30]],
               rest=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]])

    def twice(ns, raw):
        ns["deep"]["a"] = {3: 30}
        ns["deep"]["a"] = {4: 40}
    ok &= case("a row assigned whole twice: what the first brought has no value before the call",
               twice,
               writes=[["deep", ["a", 1], None], ["deep", ["a", 2], None], ["deep", ["a", 3], None],
                       ["deep", ["a", 4], 40]],
               rest=[["deep", ["a", 1], 10], ["deep", ["a", 2], 20]])
    # ---- another section's table
    ok &= case("a read of another section's table: on the tape", lambda ns, raw: ns["other"].get("q"),
               tape=[["read", "other", ["q"], [1]]])
    ok &= case("a write of another section's table through a view: refused",
               lambda ns, raw: ns["other"].__setitem__("q", [2]), raises="TypeError")
    # ---- an operation the views do not know
    ok &= case("an operation the views do not know, on a table: refused", lambda ns, raw: ns["flat"].update({"z": 1}),
               raises="TypeError")
    ok &= case("an operation the views do not know, on a row: refused", lambda ns, raw: ns["deep"]["a"].popitem(),
               raises="TypeError")
    # ---- a call the block makes on the tape: its own log, `cr` and `cw`
    def flat(ns, k, v=None):
        return (lambda: ns["flat"][k]) if v is None else (lambda: ns["flat"].__setitem__(k, v))

    def seq(*fs):
        return lambda: [f() for f in fs]
    ok &= case("a callee's read: in its cr, not among the call's reads, and in the rest",
               lambda ns, raw: callee(flat(ns, "a")), tape=[["call", [["flat", ["a"], 1]], []]], rest=[["flat", ["a"], 1]])
    ok &= case("a callee's write: in its cw and the call's writes, its value before in the rest",
               lambda ns, raw: callee(flat(ns, "a", 7)), tape=[["call", [], [["flat", ["a"], 7]]]],
               writes=[["flat", ["a"], 7]], rest=[["flat", ["a"], 1]])
    ok &= case("a callee that writes an entry and then reads it: not in its cr",
               lambda ns, raw: callee(seq(flat(ns, "z", 5), flat(ns, "z"))), tape=[["call", [], [["flat", ["z"], 5]]]],
               writes=[["flat", ["z"], 5]])
    ok &= case("a callee that reads an entry and then writes it: in its cr, with the value then, and its cw",
               lambda ns, raw: callee(seq(flat(ns, "a"), flat(ns, "a", 3))),
               tape=[["call", [["flat", ["a"], 1]], [["flat", ["a"], 3]]]], writes=[["flat", ["a"], 3]], rest=[["flat", ["a"], 1]])
    ok &= case("a value changed in place in a callee: in its cw",
               lambda ns, raw: callee(lambda: ns["bits"]["a"].set(2)), tape=[["call", [["bits", ["a"], 1]], [["bits", ["a"], 5]]]],
               writes=[["bits", ["a"], 5]], rest=[["bits", ["a"], 1]])
    ok &= case("the block's read of an entry a callee wrote: no read of the Python's",
               lambda ns, raw: (callee(flat(ns, "a", 7)), ns["flat"]["a"]), tape=[["call", [], [["flat", ["a"], 7]]]],
               writes=[["flat", ["a"], 7]], rest=[["flat", ["a"], 1]])
    ok &= case("two callees: the second's cr holds the first's write",
               lambda ns, raw: (callee(flat(ns, "a", 7)), callee(flat(ns, "a"))),
               tape=[["call", [], [["flat", ["a"], 7]]], ["call", [["flat", ["a"], 7]], []]],
               writes=[["flat", ["a"], 7]], rest=[["flat", ["a"], 1]])
    ok &= case("another section's table in a callee: nothing on the tape, its write not refused",
               lambda ns, raw: callee(seq(lambda: ns["other"]["q"], lambda: ns["other"].__setitem__("r", [2]))),
               post=lambda raw: raw["other"].get("r") == [2])
    ok &= case("another section's table iterated in a callee: nothing on the tape",
               lambda ns, raw: callee(lambda: list(ns["other"])), make=fresh_other2)
    ok &= case("`offers.listed` read in a callee: passes, and logs nothing",
               lambda ns, raw: callee(lambda: ns["offers"].listed), make=fresh_lazy)
    ok &= case("an operation the views do not know, on an own table, in a callee: refused",
               lambda ns, raw: callee(lambda: ns["flat"].popitem()), raises="TypeError")
    # ---- another section's level iterated by the block: its keys on the tape, in the Python's order
    ok &= case("another section's table iterated by the block: its keys on the tape",
               lambda ns, raw: list(ns["other"]), tape=[["keys", "other", [], ["q", "b"]]], make=fresh_other2)
    ok &= case("another section's table's length in the block: refused, as before",
               lambda ns, raw: len(ns["other"]), raises="TypeError")
    # ---- `mesh | {p}` in the block: a question with its answer, in the Python's order (trace3.py)
    import trace3                       # noqa: E402
    mesh = set(range(64))               # a set whose union with {29} iterates out of rising order: [29, 3, 35, 8, 40, 61]
    for i in range(64):
        if i not in (3, 8, 35, 40, 61):
            mesh.discard(i)
    order = list(mesh | {29})
    ok &= case("mesh | {p}, iterated by the block: asked on the tape, answered in the order the untraced code makes",
               lambda ns, raw: [q for q in trace3.MeshQuestion(mesh, lambda: REC[0].tape) | {29}],
               tape=[["mesh_and", [29], order]])
    # the mesh iterated, and a membership test, are questions too; any other use is refused
    ok &= case("M2 mesh iterated by the block: asked on the tape, answered in the set's own order",
               lambda ns, raw: [q for q in trace3.MeshQuestion(mesh, lambda: REC[0].tape)],
               tape=[["mesh", [], list(mesh)]])
    ok &= case("M3 a membership test of mesh by the block: asked on the tape, each with its answer",
               lambda ns, raw: [q in trace3.MeshQuestion(mesh, lambda: REC[0].tape) for q in (3, 29)],
               tape=[["mesh_has", [3], True], ["mesh_has", [29], False]])
    ok &= case("M4 any other use of mesh by the block: refused (its length)",
               lambda ns, raw: len(trace3.MeshQuestion(mesh, lambda: REC[0].tape)), raises="TypeError")
    ok &= case("M5 any other use of mesh by the block: refused (a difference)",
               lambda ns, raw: trace3.MeshQuestion(mesh, lambda: REC[0].tape) - {3}, raises="TypeError")
    # ---- what is not logged: the known limits
    ok &= case("a value changed in place to what it was: no write", lambda ns, raw: ns["bits"]["a"].set(0),
               reads=[["bits", ["a"], 1]], limit=True)
    ok &= case("a container kept from outside the call: its accesses are not logged",
               lambda ns, raw: raw["deep"]["a"].__setitem__(1, 11), limit=True)
    ok &= case("another section's value changed in place: not refused, not logged",
               lambda ns, raw: (ns["other"].get("q").append(2)), tape=[["read", "other", ["q"], [1]]], limit=True)
    ok &= case("whether a row that is there is there: t.get(k) is None logs nothing",
               lambda ns, raw: ns["deep"].get("a") is None, limit=True)
    # ---- the pinned toy's lazy tables (v0.10): a read allocates nothing, a write through a detached entry stays
    L = fresh_lazy
    ok &= case("lazy: t[k][p] of a missing row, which raises as a dict: read, and nothing stored",
               lambda ns, raw: ns["tried"]["z"][1], reads=[["tried", ["z", 1], None]], raises="KeyError", make=L,
               post=lambda raw: not stored(raw, "tried", "z"))
    ok &= case("lazy: t[k][p] = v through a missing row: written, and the row joins its table",
               lambda ns, raw: ns["tried"]["z"].__setitem__(2, 5), writes=[["tried", ["z", 2], 5]], make=L,
               post=lambda raw: stored(raw, "tried", "z") and dict.get(raw["tried"], "z") == {2: 5})
    ok &= case("lazy: a bitmap of a missing peer and group read: nothing stored at either level",
               lambda ns, raw: ns["offered"][2]["g"].has(1), reads=[["offered", [2, "g"], None]], make=L,
               post=lambda raw: not stored(raw, "offered", 2))
    ok &= case("lazy: a bitmap of a missing peer and group set: written, and both levels join",
               lambda ns, raw: ns["offered"][2]["g"].set(1), reads=[["offered", [2, "g"], None]],
               writes=[["offered", [2, "g"], 2]], make=L,
               post=lambda raw: stored(raw, "offered", 2) and dict.get(raw["offered"], 2).get("g").v == 2)
    ok &= case("lazy: a missing offer list read: nothing stored",
               lambda ns, raw: list(ns["offers"]["z"]), reads=[["offers", ["z"], None]], make=L,
               post=lambda raw: not stored(raw, "offers", "z"))
    ok &= case("lazy: a missing offer list appended to: written, it joins `offers`, and `listed` counts it",
               lambda ns, raw: ns["offers"]["z"].append(3), reads=[["offers", ["z"], None]],
               writes=[["offers", ["z"], [3]]], make=L,
               post=lambda raw: stored(raw, "offers", "z") and raw["offers"].listed.get(3) == 1)
    ok &= case("lazy: a member of a missing set asked: read, and nothing stored",
               lambda ns, raw: 4 in ns["sets"]["d"], reads=[["sets", ["d", 4], None]], make=L,
               post=lambda raw: not stored(raw, "sets", "d"))
    ok &= case("lazy: a member added to a missing set: written, and the set joins its table",
               lambda ns, raw: ns["sets"]["d"].add(4), writes=[["sets", ["d", 4], True]], make=L,
               post=lambda raw: stored(raw, "sets", "d") and 4 in dict.get(raw["sets"], "d"))
    # the shapes the first eight did not have
    ok &= case("lazy: a member added to a missing set of one level (asked_parked's shape): read, written, and it joins",
               lambda ns, raw: ns["pset"]["k"].add(4), reads=[["pset", ["k"], None]], writes=[["pset", ["k"], [4]]],
               make=L, post=lambda raw: stored(raw, "pset", "k"))
    ok &= case("lazy: a count of a DefaultMap read where missing: 0, and nothing stored",
               lambda ns, raw: ns["cnt"][7], reads=[["cnt", [7], None]], make=L,
               post=lambda raw: not stored(raw, "cnt", 7))
    ok &= case("lazy: a count incremented where missing (`x[p] += 1`): read, then written",
               lambda ns, raw: ns["cnt"].__setitem__(7, ns["cnt"][7] + 1), reads=[["cnt", [7], None]],
               writes=[["cnt", [7], 1]], make=L, post=lambda raw: stored(raw, "cnt", 7))
    ok &= case("lazy: a lazy table of another section read where missing: on the tape, and nothing stored",
               lambda ns, raw: ns["omine"]["g"].has(1), tape=[["read", "omine", ["g"], None]], make=L,
               post=lambda raw: not stored(raw, "omine", "g"))
    ok &= case("lazy: an entry emptied and left (a row's last key popped): written, the row stays, empty",
               lambda ns, raw: ns["tried"]["a"].pop(1), reads=[["tried", ["a", 1], 10]], writes=[["tried", ["a", 1], None]],
               make=L, post=lambda raw: stored(raw, "tried", "a") and len(dict.get(raw["tried"], "a")) == 0)
    # ---- presence: `tied`'s rows, over the toy's tie_table()
    T = fresh_tied
    rows1 = [["tied", ["r1", 1], True], ["tied", ["r1"], True]]       # rest's order: by the JSON of [table, path]
    ok &= case("P1 presence: a bitmap read (tied[r][p][g]): read; the rows above it observed, in the rest",
               lambda ns, raw: ns["tied"]["r1"][1]["g"].has(0), reads=[["tied", ["r1", 1, "g"], 1]], rest=rows1, make=T)
    ok &= case("P2 presence: a bitmap set under missing rows: read, and written with the rows it makes",
               lambda ns, raw: ns["tied"]["r9"][5]["g"].set(2), reads=[["tied", ["r9", 5, "g"], None]],
               writes=[["tied", ["r9"], True], ["tied", ["r9", 5], True], ["tied", ["r9", 5, "g"], 4]], make=T,
               post=lambda raw: stored(raw, "tied", "r9"))
    # `planned`: `k in t` at a row's level of a table with `presence_in` is a read of that row's own entry
    PL = fresh_planned
    ok &= case("P-in 1 presence_in: `g in planned`, the row there: a read of the row's entry alone; nothing under it read, no scan",
               lambda ns, raw: "g1" in ns["planned"], reads=[["planned", ["g1"], True]], make=PL)
    ok &= case("P-in 2 presence_in: `g in planned`, the row not there: a read of the row's entry, missing; no row made",
               lambda ns, raw: "g9" in ns["planned"], reads=[["planned", ["g9"], None]], make=PL,
               post=lambda raw: "g9" not in raw["planned"])
    ok &= case("P-in 3 presence_in: an index's peers read after the test: the entry, and its row observed in the reads",
               lambda ns, raw: ("g1" in ns["planned"]) and 2 in ns["planned"]["g1"].get(0, ()),
               reads=[["planned", ["g1"], True], ["planned", ["g1", 0], [2, 5]]], make=PL)
    ok &= case("P3 presence: a bitmap emptied in place: written as 0, not missing",
               lambda ns, raw: ns["tied"]["r1"][1]["g"].clear(0), reads=[["tied", ["r1", 1, "g"], 1]],
               writes=[["tied", ["r1", 1, "g"], 0]], rest=rows1, make=T)
    ok &= case("P4 presence: a bitmap popped from its row (drop_beyond's pop): written missing; the peer row stays",
               lambda ns, raw: ns["tied"]["r1"][1].pop("g"), reads=[["tied", ["r1", 1, "g"], 1]],
               writes=[["tied", ["r1", 1, "g"], None]], rest=rows1, make=T,
               post=lambda raw: raw["tied"]._d["r1"]._d[1]._d == {})
    ok &= case("P5 presence: a row asked (`k in tied`): the row read, with what is under it, a row there and empty",
               lambda ns, raw: "r2" in ns["tied"], reads=[["tied", ["r2"], True], ["tied", ["r2", 2], True]],
               scans=[["tied", ["r2"]]], make=T)
    ok &= case("P6 presence: a missing row asked: read as missing", lambda ns, raw: "r7" in ns["tied"],
               reads=[["tied", ["r7"], None]], scans=[["tied", ["r7"]]], make=T)
    ok &= case("P7 presence: the whole table read (tied.values(), tied_to_root's): every row and bitmap",
               lambda ns, raw: list(ns["tied"].values()),
               reads=[["tied", ["r1"], True], ["tied", ["r1", 1], True], ["tied", ["r1", 1, "g"], 1],
                      ["tied", ["r1", 3], True], ["tied", ["r1", 3, "g"], 0], ["tied", ["r2"], True],
                      ["tied", ["r2", 2], True]], scans=[["tied", []]], make=T)
    made = [["tied", ["r9", 5, "g"], 4], ["tied", ["r9", 5], True], ["tied", ["r9"], True]]   # sorted, by the JSON
    ok &= case("P8 presence: a callee sets a bitmap under missing rows: its cw has the rows it made, in one order",
               lambda ns, raw: callee(lambda: ns["tied"]["r9"][5]["g"].set(2)),                #   of [table, path]
               writes=made, tape=[["call", [["tied", ["r9", 5, "g"], None]], made]], make=T)
    ok &= case("P9 presence: rows observed, then read by the block: the block's reads, with their values before",
               lambda ns, raw: (ns["tied"]["r1"][1]["g"].has(0), "r1" in ns["tied"]),
               reads=[["tied", ["r1"], True], ["tied", ["r1", 1], True], ["tied", ["r1", 1, "g"], 1],
                      ["tied", ["r1", 3], True], ["tied", ["r1", 3, "g"], 0]], scans=[["tied", ["r1"]]], make=T)
    ok &= case("P10 the block's read of an entry a callee read first: a read of the block's, with the value before",
               lambda ns, raw: (callee(lambda: ns["flat"]["a"]), ns["flat"]["a"]), reads=[["flat", ["a"], 1]],
               tape=[["call", [["flat", ["a"], 1]], []]], make=T)
    ok &= case("P11 a callee that touches entries in an order of its own: its cr and cw, and the call's log, sorted",
               lambda ns, raw: callee(lambda: (ns["flat"]["b"], ns["flat"]["a"], ns["flat"].__setitem__("z", 3),
                                               ns["flat"].__setitem__("c", 4))),
               writes=[["flat", ["c"], 4], ["flat", ["z"], 3]], rest=[["flat", ["a"], 1], ["flat", ["b"], 2]],
               tape=[["call", [["flat", ["a"], 1], ["flat", ["b"], 2]], [["flat", ["c"], 4], ["flat", ["z"], 3]]]],
               make=T)
    # ---- the queue: the toy's PeerQueue, its lanes as keys, its rows kept, its order asked
    Q = fresh_queue
    iw = [[None, [["iwant", ["a", "b"]]], False]]
    row1, row2 = ["queue", [1], True], ["queue", [2], True]
    ok &= case("Q1 queue[p].normal: the lane read, its row observed (in the rest)",
               lambda ns, raw: ns["queue"][1].normal, reads=[["queue", [1, "normal"], iw]], rest=[row1], make=Q)
    ok &= case("Q2 a missing peer's lane: read as missing, and nothing stored",
               lambda ns, raw: ns["queue"][9].normal, reads=[["queue", [9, "normal"], None]], make=Q,
               post=lambda raw: not dict.__contains__(raw["queue"], 9))
    one = [None, [["iwant", ["c"]]], False]
    ok &= case("Q3 an append to a detached queue, in a callee (enqueue's): the lane, the other lane and the row written"
               " (a row made in the call brings both lanes), in one order",
               lambda ns, raw: callee(lambda: ns["queue"][9].normal.append(QW[0].Entry(control=QW[0].IWANT(["c"])))),
               writes=[["queue", [9, "normal"], [one]], ["queue", [9, "urgent"], []], ["queue", [9], True]],
               tape=[["call", [["queue", [9, "normal"], None]],
                      [["queue", [9, "normal"], [one]], ["queue", [9, "urgent"], []], ["queue", [9], True]]]],
               make=Q, post=lambda raw: dict.__contains__(raw["queue"], 9))
    ok &= case("Q4 a lane assigned whole (drop_offer's filter), in a callee: read, then written",
               lambda ns, raw: callee(lambda: setattr(ns["queue"][1], "normal",
                                                      [e for e in ns["queue"][1].normal if "z" in e.control.items[0].ids])),
               writes=[["queue", [1, "normal"], []]], rest=[["queue", [1, "normal"], iw], row1],
               tape=[["call", [["queue", [1, "normal"], iw]], [["queue", [1, "normal"], []]]]], make=Q)

    def drop_a(ns):
        for e in ns["queue"][1].normal:
            for c in e.iwants():
                c.ids = [b for b in c.ids if b != "a"]
    ib = [[None, [["iwant", ["b"]]], False]]
    ok &= case("Q5 an entry changed in place (drop_offer's removal of an ask), in a callee: a write by its value",
               lambda ns, raw: callee(lambda: drop_a(ns)), writes=[["queue", [1, "normal"], ib]],
               rest=[["queue", [1, "normal"], iw], row1], tape=[["call", [["queue", [1, "normal"], iw]], [["queue", [1, "normal"], ib]]]],
               make=Q)
    ok &= case("Q6 an entry changed in place by the block (add_ihave's kind): a write of its lane",
               lambda ns, raw: ns["queue"][1].normal[0].add_ihave("h"),
               reads=[["queue", [1, "normal"], iw]],
               writes=[["queue", [1, "normal"], [[None, [["iwant", ["a", "b"]], ["ihave", ["h"]]], False]]]],
               rest=[row1], make=Q)
    ok &= case("Q7 a lane emptied and left in its row: written as [], the row stays",
               lambda ns, raw: setattr(ns["queue"][1], "normal", []), writes=[["queue", [1, "normal"], []]],
               rest=[["queue", [1, "normal"], iw], row1], make=Q, post=lambda raw: dict.__contains__(raw["queue"], 1))
    whole = [row1, ["queue", [1, "urgent"], []], ["queue", [1, "normal"], iw], row2, ["queue", [2, "urgent"], []],
             ["queue", [2, "normal"], []]]
    ok &= case("Q8 list(queue) by the block: every row and lane read, and the rows' order on the tape",
               lambda ns, raw: list(ns["queue"]), reads=whole, scans=[["queue", []]],
               tape=[["keys", "queue", [], [1, 2]]], make=Q)
    ok &= case("Q9 list(queue) in a callee: read whole into its log, and no order on the tape",
               lambda ns, raw: callee(lambda: list(ns["queue"])),
               rest=sorted(whole, key=lambda e: F.json.dumps(e[:2])),
               tape=[["call", sorted(whole, key=lambda e: F.json.dumps(e[:2])), []]], make=Q)
    ok &= case("Q10 another attribute of a PeerQueue by the block (one the views do not know): refused",
               lambda ns, raw: ns["queue"][1].size, raises="TypeError", make=Q)
    # next_to_send's `q.has_chunks()`
    ok &= case("Q13 q.has_chunks() of a lane with an IWANT and no chunk: a read of the normal lane, and false",
               lambda ns, raw: ns["queue"][1].has_chunks(), reads=[["queue", [1, "normal"], iw]], rest=[row1],
               make=Q, post=lambda raw: raw["queue"][1].has_chunks() is False)
    ok &= case("Q14 q.has_chunks() of a row there with both lanes empty: the empty lane read",
               lambda ns, raw: ns["queue"][2].has_chunks(), reads=[["queue", [2, "normal"], []]], rest=[row2], make=Q)
    ok &= case("Q15 a callee appends to a lane and the block pops it back off (an owed answer, enqueued and "
               "sent): the lane in the call's writes, at its value at the end, its value before in the rest",
               lambda ns, raw: (callee(lambda: ns["queue"][1].normal.append(QW[0].Entry(control=QW[0].IWANT(["c"])))),
                                ns["queue"][1].normal.pop()),
               writes=[["queue", [1, "normal"], iw]], rest=[["queue", [1, "normal"], iw], row1],
               tape=[["call", [["queue", [1, "normal"], iw]], [["queue", [1, "normal"], iw + [one]]]]], make=Q)

    class AliasRefused(Exception):
        pass

    def alias(ns, raw):                 # one entry object in two lanes: trace3.py's alias check must refuse it, in its
        import trace3                   #   own words (its SystemExit, taken here as the case's exception)
        e = raw["queue"][1].normal[0]
        raw["queue"][2].urgent.append(e)
        try:
            trace3.Tracer3.alias_check(None, REC[0], 7)
        except SystemExit as x:
            if str(x).startswith("trace3: node 7: one queue entry stands in two places, (1, 'normal', 0) and (2, 'urgent', 0)"):
                raise AliasRefused() from x
            raise
    ok &= case("Q11 one entry in two lanes: trace3.py's alias check refuses the run", alias, raises="AliasRefused",
               make=Q)
    # ---- ordered levels below the top, a pop above them, and items() of an ordered top level
    O = fresh_ordered
    r1 = [["tied", ["r1"], True], ["tied", ["r1", 1], True], ["tied", ["r1", 1, "g"], 1], ["tied", ["r1", 3], True],
          ["tied", ["r1", 3, "g"], 0]]
    ok &= case("O1 a root's row of tied iterated (an ordered level): read whole, and its peers' order on the tape",
               lambda ns, raw: list(ns["tied"]["r1"]), reads=r1, scans=[["tied", ["r1"]]],
               tape=[["keys", "tied", ["r1"], [1, 3]]], make=O)
    ok &= case("O2 a root's row popped (tied.pop(root)): read whole and erased, and the order of every ordered level "
               "under it on the tape, outer first", lambda ns, raw: ns["tied"].pop("r1"), reads=r1,
               scans=[["tied", ["r1"]]], writes=[[e[0], e[1], None] for e in r1],
               tape=[["keys", "tied", ["r1"], [1, 3]], ["keys", "tied", ["r1", 1], ["g"]], ["keys", "tied", ["r1", 3], ["g"]]],
               make=O)
    ok &= case("O3 a peer's groups iterated by items() (an ordered level, the last): read, and their order on the tape",
               lambda ns, raw: list(ns["tied"]["r1"][1].items()),
               reads=[["tied", ["r1", 1], True], ["tied", ["r1", 1, "g"], 1]], scans=[["tied", ["r1", 1]]],
               rest=[["tied", ["r1"], True]], tape=[["keys", "tied", ["r1", 1], ["g"]]], make=O)
    ok &= case("O4 items() of a pair-keyed table's ordered top level (tie_slot's): read whole, and its keys' order on "
               "the tape", lambda ns, raw: list(ns["ts"].items()),
               reads=[["ts", [["r1", 1]], 5], ["ts", [["r2", 2]], 6]], scans=[["ts", []]],
               tape=[["keys", "ts", [], [["r1", 1], ["r2", 2]]]], make=O)
    ok &= case("O5 setdefault of an entry there (tie_slot's): read, and no write",
               lambda ns, raw: ns["ts"].setdefault(("r1", 1), 9), reads=[["ts", [["r1", 1]], 5]], make=O)
    ok &= case("O6 setdefault of an entry missing: read as missing, and written",
               lambda ns, raw: ns["ts"].setdefault(("r3", 4), 9), reads=[["ts", [["r3", 4]], None]],
               writes=[["ts", [["r3", 4]], 9]], make=O)
    # ---- a row made by one callee through one lane, the other lane read by a later callee; the log against the
    #      tables themselves at both ends (snapshot), as a whole-state trace checks it
    ns, rec, raw = fresh_queue()
    REC[0] = rec
    before = rec.snapshot()
    rec.clear()
    rec.on = True
    raised = None
    try:                                # a view that refuses a lane is this case's failure, not the test's end
        callee(lambda: ns["queue"][9].urgent.append(QW[0].Entry(control=QW[0].IWANT(["d"]))))
        callee(lambda: len(ns["queue"][9].normal))
    except Exception as e:              # noqa: BLE001
        raised = type(e).__name__
    rec.on = False
    r, s_, w = rec.footprint()
    said = {(e[0], F.json.dumps(e[1])): e[2] for e in r if e[2] is not None}
    said.update({(e[0], F.json.dumps(e[1])): e[2] for e in rec.rest(False)})
    for e in r + rec.rest(False):       # a cell's record holds the entries it touched: the state before, on them
        k = (e[0], F.json.dumps(e[1]))
        if before.get(k) != said.get(k):
            said = None
            break
    after = {k: v for k, v in before.items()}
    for e in w:
        k = (e[0], F.json.dumps(e[1]))
        if e[2] is None:
            after.pop(k, None)
        else:
            after[k] = e[2]
    second = rec.tape[-1] if rec.tape else None
    q12 = (raised is None and said is not None and after == rec.snapshot() and second is not None
           and second[1] == [["queue", [9, "normal"], []]] and ["queue", [9, "normal"], None] not in rec.rest(False)
           and not any(e[:2] == ["queue", [9, "normal"]] for e in rec.rest(False)))
    print(f"case, Q12 a row made by a callee through one lane, the other lane read by a later callee: the reads and "
          f"rest give the state before, the writes the state after, and the second callee read the lane as [], "
          f"made in the call: {'as the contract says' if q12 else 'NOT  <-- FAIL'}")
    ok &= q12
    # ---- within one callee (origin_acked sends a HAVE and an announcement to one peer): a row made through one
    #      lane and the other lane read and appended to, by the same callee
    ns, rec, raw = fresh_queue()
    REC[0] = rec
    before = rec.snapshot()
    rec.clear()
    rec.on = True
    raised = None

    def both():
        ns["queue"][9].urgent.append(QW[0].Entry(control=QW[0].IWANT(["d"])))
        ns["queue"][9].normal.append(QW[0].Entry(control=QW[0].IWANT(["e"])))
    try:
        callee(both)
    except Exception as e:              # noqa: BLE001
        raised = type(e).__name__
    rec.on = False
    r, s_, w = rec.footprint()
    said = {(e[0], F.json.dumps(e[1])): e[2] for e in r if e[2] is not None}
    said.update({(e[0], F.json.dumps(e[1])): e[2] for e in rec.rest(True)})
    after = dict(said)
    for e in w:
        k = (e[0], F.json.dumps(e[1]))
        if e[2] is None:
            after.pop(k, None)
        else:
            after[k] = e[2]
    log = rec.tape[-1] if rec.tape else None
    q16 = (raised is None and said == before and after == rec.snapshot() and log is not None
           and not any(e[:2] == ["queue", [9, "normal"]] and e[2] is not None for e in log[1])
           and not any(e[:2] == ["queue", [9, "normal"]] for e in rec.rest(True)))
    print(f"case, Q16 a row made by a callee through one lane, and its other lane read by the same callee: the reads "
          f"and rest give the state before, the writes the state after, and the lane was missing before, in the "
          f"callee's log and in the rest: {'as the contract says' if q16 else 'NOT  <-- FAIL'}")
    ok &= q16
    # ---- a table whose values' order is asked (`held_back.values()`)
    def fresh_values():
        ns, rec, raw = fresh()
        rec.roots["flat"][0].values_ordered = VALUES_ORDERED[0]
        return ns, rec, raw
    ok &= case("V1 values() of a table whose values' order is asked: read whole, and its keys on the tape",
               lambda ns, raw: list(ns["flat"].values()), reads=[["flat", ["a"], 1], ["flat", ["b"], 2]],
               scans=[["flat", []]], tape=[["keys", "flat", [], ["a", "b"]]], make=fresh_values)
    ok &= case("V2 values() of another table: read whole, nothing on the tape",
               lambda ns, raw: list(ns["flat"].values()), reads=[["flat", ["a"], 1], ["flat", ["b"], 2]],
               scans=[["flat", []]])
    ok &= case("V3 values() in a callee: its read, no keys on the tape",
               lambda ns, raw: callee(lambda: list(ns["flat"].values())),
               rest=[["flat", ["a"], 1], ["flat", ["b"], 2]],
               tape=[["call", [["flat", ["a"], 1], ["flat", ["b"], 2]], []]], make=fresh_values)
    # ---- a list of the namespace, a table of one entry
    J1, J2, J3 = [4, ["x"], 1.0], [5, ["x", "y"], 1.0], [6, ["z"], 2.0]
    both = ["pq", ["jobs"], [J1, J2]]
    ok &= case("L1 a truth test of the list: a read of its entry", lambda ns, raw: bool(ns["pq"]), reads=[both],
               make=fresh_list)
    ok &= case("L2 a truth test of an empty list: a read, of no value", lambda ns, raw: bool(ns["pq"]),
               reads=[["pq", ["jobs"], None]], make=fresh_list_empty)
    ok &= case("L3 len of the list: a read", lambda ns, raw: len(ns["pq"]), reads=[both], make=fresh_list)
    ok &= case("L4 the list iterated: a read", lambda ns, raw: [q for q, _, _ in ns["pq"]], reads=[both],
               make=fresh_list)
    ok &= case("L5 an append: a read and a write", lambda ns, raw: ns["pq"].append((6, ["z"], 2.0)), reads=[both],
               writes=[["pq", ["jobs"], [J1, J2, J3]]], make=fresh_list, post=lambda raw: len(raw["pq"]) == 3)
    ok &= case("L6 an append to an empty list", lambda ns, raw: ns["pq"].append((6, ["z"], 2.0)),
               reads=[["pq", ["jobs"], None]], writes=[["pq", ["jobs"], [J3]]], make=fresh_list_empty)
    ok &= case("L7 pop(0): a read and a write", lambda ns, raw: ns["pq"].pop(0), reads=[both],
               writes=[["pq", ["jobs"], [J2]]], make=fresh_list)

    def drain(ns, raw):                 # on_pace_tick's loop, to the end
        while ns["pq"]:
            ns["pq"].pop(0)
    ok &= case("L8 the list popped until empty: one read, of the value before; written as no value", drain,
               reads=[both], writes=[["pq", ["jobs"], None]], make=fresh_list, post=lambda raw: raw["pq"] == [])
    ok &= case("L9 a pop not of the first job raises", lambda ns, raw: ns["pq"].pop(), raises="TypeError",
               make=fresh_list, post=lambda raw: len(raw["pq"]) == 2)
    ok &= case("L10 a job by its place raises", lambda ns, raw: ns["pq"][0], raises="TypeError", make=fresh_list)
    ok &= case("L11 the block's clear raises", lambda ns, raw: ns["pq"].clear(), raises="TypeError", make=fresh_list,
               post=lambda raw: len(raw["pq"]) == 2)

    def closed(ns, raw):                # the toy's link close, a callee: the jobs of peer 4 go
        def body():
            pq = ns["pq"]
            if pq:
                kept = [x for x in pq if x[0] != 4]
                pq.clear()
                pq.extend(kept)
        callee(body)
    ok &= case("L12 a callee's clear and extend: its log apart, the entry before the call in the rest", closed,
               writes=[["pq", ["jobs"], [J2]]], rest=[both], tape=[["call", [both], [["pq", ["jobs"], [J2]]]]],
               make=fresh_list)

    def paced(ns, raw):                 # the toy's discard_paced (v0.10.4), a callee: the ids "x" leave every job, a
        def body():                     #   job left empty goes, and the list is rebuilt in place
            jobs = []
            for q, ids, at in ns["pq"]:
                left = [m for m in ids if m != "x"]
                if left or not ids:
                    jobs.append((q, ids if len(left) == len(ids) else left, at))
            ns["pq"][:] = jobs
        callee(body)
    J2y = [5, ["y"], 1.0]
    ok &= case("L15 a callee's assignment of the whole list (discard_paced): its log apart, the list the same object",
               paced, writes=[["pq", ["jobs"], [J2y]]], rest=[both], tape=[["call", [both], [["pq", ["jobs"], [J2y]]]]],
               make=fresh_list, post=lambda raw: raw["pq"] == [(5, ["y"], 1.0)])
    ok &= case("L16 the block's assignment of the whole list raises",
               lambda ns, raw: ns["pq"].__setitem__(slice(None), []), raises="TypeError", make=fresh_list,
               post=lambda raw: len(raw["pq"]) == 2)
    ok &= case("L17 a callee's assignment to a part of the list raises",
               lambda ns, raw: callee(lambda: ns["pq"].__setitem__(slice(0, 1), [])), raises="TypeError",
               make=fresh_list, post=lambda raw: len(raw["pq"]) == 2)
    # ---- repr during a record; a method taken before a record
    shown = []
    ok &= case("L18 repr of the list in a call: no job in its text, and no read", lambda ns, raw: shown.append(repr(ns["pq"])),
               make=fresh_list, post=lambda raw: shown[-1] == "ListView(pq)")

    def taken_before(make_callee):
        def body(ns, raw):
            ext = TAKEN[0]              # the list's `extend`, taken from the view before the record opened
            if make_callee:
                callee(lambda: ext([(6, ["z"], 2.0)]))
            else:
                ext([(6, ["z"], 2.0)])
        return body

    def fresh_list_taken():
        ns, rec, raw = fresh_list()
        TAKEN[0] = ns["pq"].extend      # the recorder is off here
        return ns, rec, raw
    TAKEN = [None]
    ok &= case("L19 a method taken while the recorder was off, called by the block in a call: refused", taken_before(False),
               raises="TypeError", make=fresh_list_taken, post=lambda raw: len(raw["pq"]) == 2)
    ok &= case("L20 the same, called by a callee: logged as its write", taken_before(True),
               writes=[["pq", ["jobs"], [J1, J2, J3]]], rest=[both], tape=[["call", [both], [["pq", ["jobs"], [J1, J2, J3]]]]],
               make=fresh_list_taken, post=lambda raw: len(raw["pq"]) == 3)
    ns, rec, raw = fresh_list()         # the recorder off: the list's own, nothing logged
    ns["pq"].clear()
    ns["pq"].extend([(7, [], 3.0)])
    ns["pq"].sort()
    ns["pq"][:] = list(ns["pq"])        # (v0.10.4's discard_paced outside a record: the list's own too)
    r, s, w = rec.footprint()
    loff = ((r, s, w, rec.tape) == ([], [], [], []) and raw["pq"] == [(7, [], 3.0)] and F.unwrap(ns["pq"]) is raw["pq"]
            and rec.snapshot() == {("pq", '["jobs"]'): [[7, [], 3.0]], ("flat", '["a"]'): 1, ("flat", '["b"]'): 2})
    print(f"case, L13 the recorder off: the list's own operations, nothing logged, and the snapshot has its entry: "
          f"{'as the contract says' if loff else 'NOT  <-- FAIL'}")
    ok &= loff
    try:                                # a list under a table of two keys is refused at the install
        F.install(F.Recorder(), {"pq": []}, [F.Table("pq", [str, str], lambda v: v)])
        two = False
    except TypeError:
        two = True
    print(f"case, L14 a list under a table of two keys is refused: {'as the contract says' if two else 'NOT  <-- FAIL'}")
    ok &= two
    # ---- the window's count (a cell under the name), its line (a deque) and `sent`'s missed pop
    CNT, LN = ["in_flight", ["count"]], ["waiters", ["line"]]
    SK = ["sent", [[5, "g", 3]]]

    def run(src):                       # the document's own statements, in the node's namespace
        return lambda ns, raw: exec(src, ns)
    cell = lambda ns: isinstance(ns["in_flight"], F.CountCell)     # noqa: E731
    ok &= case("W1 a comparison of the count: one read", run("x = in_flight < W"), reads=[CNT + [1]], make=fresh_window)
    ok &= case("W2 `in_flight += 1`: a read and a write, and the name still holds the cell", run("in_flight += 1"),
               reads=[CNT + [1]], writes=[CNT + [2]], make=fresh_window, post=lambda raw: True)
    ns, rec, raw = fresh_window()
    rec.on = True
    exec("in_flight += 1\nin_flight -= 1\nin_flight += 1", ns)
    rec.on = False
    still = cell(ns) and F.unwrap(ns["in_flight"]) == 2
    print(f"case, W3 after three updates the name holds the cell, and the count is 2: "
          f"{'as the contract says' if still else 'NOT  <-- FAIL'}")
    ok &= still
    ok &= case("W4 `in_flight -= 1` at 0: the entry goes to -1", run("in_flight -= 1"),
               reads=[CNT + [None]], writes=[CNT + [["-", 1]]], make=lambda: fresh_window(count=0))
    ok &= case("W5 a failed acquisition (the window full, the peer in line): reads, no write",
               run("x = in_flight < W and (not waiters or waiters[0] == 7)\ny = 7 not in waiters"),
               reads=[CNT + [2], LN + [[5, 7]]], make=lambda: fresh_window(count=2))
    ok &= case("W6 the count in a sum (v2's `in_flight + need <= W`): one read", run("x = in_flight + 1 <= W"),
               reads=[CNT + [1]], make=fresh_window)
    ok &= case("W7 the line: `if waiters`, `waiters[0]`, `p in waiters`: one read",
               run("x = bool(waiters) and waiters[0] == 5 and 7 in waiters"), reads=[LN + [[5, 7]]], make=fresh_window)
    ok &= case("W8 `waiters.popleft()`: a read and a write", run("waiters.popleft()"),
               reads=[LN + [[5, 7]]], writes=[LN + [[7]]], make=fresh_window)
    ok &= case("W9 `waiters.append(p)`: a read and a write", run("waiters.append(9)"),
               reads=[LN + [[5, 7]]], writes=[LN + [[5, 7, 9]]], make=fresh_window)
    ok &= case("W10 `waiters.appendleft(p)` (the toy's writer for an answer): a read and a write", run("waiters.appendleft(9)"),
               reads=[LN + [[5, 7]]], writes=[LN + [[9, 5, 7]]], make=fresh_window)
    ok &= case("W11 `waiters.remove(p)`, the last one left: a read and a write to nothing",
               run("waiters.remove(5)\nwaiters.remove(7)"), reads=[LN + [[5, 7]]], writes=[LN + [None]], make=fresh_window)
    ok &= case("W12 `len(waiters)` is refused", run("len(waiters)"), raises="TypeError", make=fresh_window)
    ok &= case("W13 iterating the line is refused", run("list(waiters)"), raises="TypeError", make=fresh_window)
    ok &= case("W14 `waiters[1]` is refused", run("waiters[1]"), raises="TypeError", make=fresh_window)
    ok &= case("W15 `sent.pop(key, None)` that finds nothing: a read alone", run("x = sent.pop((9, 'g', 1), None)"),
               reads=[["sent", [[9, "g", 1]], None]], make=fresh_window)
    ok &= case("W16 `sent.pop(key, None)` that finds the send: a read and a write", run("x = sent.pop((5, 'g', 3), None)"),
               reads=[SK + [0.25]], writes=[SK + [None]], make=fresh_window)
    ok &= case("W17 `key in sent`, `sent[key] = now`, `sent.get(key)`, `del sent[key]`",
               run("x = (9, 'g', 1) in sent\nsent[(9, 'g', 1)] = 1.5\ny = sent.get((5, 'g', 3))\ndel sent[(5, 'g', 3)]"),
               reads=[["sent", [[9, "g", 1]], None], SK + [0.25]], writes=[["sent", [[9, "g", 1]], 1.5], SK + [None]],
               make=fresh_window)
    ok &= case("W18 a call on the tape that takes a slot: its log has the read and the write; the call's rest the value before",
               lambda ns, raw: callee(lambda: exec("in_flight += 1", ns)),
               writes=[CNT + [2]], rest=[CNT + [1]], tape=[["call", [CNT + [1]], [CNT + [2]]]], make=fresh_window)
    ns, rec, raw = fresh_window()       # the recorder off: the count's and the line's own, nothing logged
    exec("in_flight += 1\nwaiters.append(9)\nn = len(waiters)\nx = sent.pop((9, 'g', 1), None)", ns)
    r, s, w = rec.footprint()
    woff = ((r, s, w, rec.tape) == ([], [], [], []) and cell(ns) and F.unwrap(ns["in_flight"]) == 2 and ns["n"] == 3
            and F.unwrap(ns["waiters"]) is raw["waiters"]
            and rec.snapshot() == {("in_flight", '["count"]'): 2, ("waiters", '["line"]'): [5, 7, 9],
                                   ("sent", '[[5, "g", 3]]'): 0.25})
    print(f"case, W19 the recorder off: the count's and the line's own operations, nothing logged, and the snapshot has "
          f"the three: {'as the contract says' if woff else 'NOT  <-- FAIL'}")
    ok &= woff
    # ---- the recorder off: the views are transparent
    ns, rec, raw = fresh()
    ns["flat"]["a"]
    ns["flat"].update({"z": 1})
    ns["other"]["q"] = [3]
    r, s, w = rec.footprint()
    off = (r, s, w, rec.tape) == ([], [], [], []) and raw["flat"] == {"a": 1, "b": 2, "z": 1} and raw["other"] == {"q": [3]}
    print(f"case, the recorder off: nothing logged, every operation the container's own: "
          f"{'as the contract says' if off else 'NOT  <-- FAIL'}")
    ok &= off
    # ---- the log against the state: snapshot
    ns, rec, raw = fresh()
    before = rec.snapshot()
    rec.clear()
    rec.on = True
    ns["flat"]["a"] = 5
    raw["deep"]["a"][1] = 11            # a write that went round the views
    rec.on = False
    r, s, w = rec.footprint()
    said = {(e[0], F.json.dumps(e[1])): e[2] for e in r if e[2] is not None}
    said.update({(e[0], F.json.dumps(e[1])): e[2] for e in rec.rest(True)})
    snap = said != before
    print(f"case, a write that went round the views: reads and rest no longer give the state before: "
          f"{'as the contract says' if snap else 'NOT  <-- FAIL'}")
    ok &= snap
    # ---- the log against the state, where a level is assigned whole and its entries are touched again
    ns, rec, raw = fresh()
    before = rec.snapshot()
    rec.clear()
    rec.on = True
    ns["deep"]["a"] = {3: 30}
    ns["deep"]["a"][3]
    ns["deep"]["a"] = {3: 31, 4: 40}
    rec.on = False
    r, s, w = rec.footprint()
    said = {(e[0], F.json.dumps(e[1])): e[2] for e in r if e[2] is not None}
    said.update({(e[0], F.json.dumps(e[1])): e[2] for e in rec.rest(True)})
    after = dict(said)
    for e in w:
        if e[2] is None:
            after.pop((e[0], F.json.dumps(e[1])), None)
        else:
            after[(e[0], F.json.dumps(e[1]))] = e[2]
    acct = said == before and after == rec.snapshot()
    print(f"case, a row assigned whole, read, and assigned again: reads and rest give the state before, and the "
          f"writes the state after: {'as the contract says' if acct else 'NOT  <-- FAIL'}")
    ok &= acct
    print("ok: every case as the contract says" if ok else "footprint_test: a case is NOT as the contract says")
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--broken"]:    # the control of these cases: a view that lets a read through unlogged
        F.View.__contains__ = lambda self, k: k in self._o
    if sys.argv[1:] == ["--broken-level"]:  # and one that does not note, at the assignment, what a level brings
        F.Recorder.assigned_level = lambda self, t, prefix: None
    if sys.argv[1:] == ["--broken-copy"]:   # and views that hand out a fresh entry of no table in place of a missing
        _sub, _get = F.View._sub, F.View.__getitem__   #   one's detached entry: a write then joins nothing

        def fresh_entry(o, k, v):
            stored_ = k in (o._d if hasattr(o, "_d") else dict.keys(o)) if hasattr(o, "_d") or isinstance(o, dict) else True
            if stored_:
                return v
            return type(v)(getattr(v, "_make", None)) if isinstance(v, dict) else type(v)()

        def sub(self, k, v):
            return _sub(self, k, fresh_entry(self._o, k, v))

        def get(self, k):
            v = _get(self, k)
            return fresh_entry(self._o, k, v) if self._leaf() and self._r.on and not isinstance(v, (int, float)) else v
        F.View._sub, F.View.__getitem__ = sub, get
    if sys.argv[1:] == ["--broken-callee"]:     # and a recorder with no third state: a call on the tape turns
        def off(self):                          #   the log off and gives no cr or cw
            self.on = False

        def on(self):
            self.on = True
            return [], []
        F.Recorder.begin_callee, F.Recorder.end_callee = off, on
    if sys.argv[1:] == ["--broken-keys"]:   # and views that put no keys on the tape for another section's level
        F.View._foreign_keys = lambda self: False
    if sys.argv[1:] == ["--broken-mesh"]:   # and a mesh question answered in rising order, not the Python's
        import trace3                       # noqa: E402
        trace3.MeshQuestion.__or__ = lambda self, other: trace3._MeshAnd(self, list(other), sorted(set.__or__(self.m, other)))
    if sys.argv[1:] == ["--broken-rows"]:   # and a recorder that observes no row above an entry touched (presence)
        F.Recorder._touch = lambda self, t, p, rw: self._touch1(t, p, rw)
    if sys.argv[1:] == ["--broken-bread"]:  # and one that never takes a block's read after a callee's or an
        _touch1 = F.Recorder._touch1        #   observation as the block's read

        def touch1(self, t, p, rw):
            _touch1(self, t, p, rw)
            self.bread.clear()
        F.Recorder._touch1 = touch1
    if sys.argv[1:] == ["--broken-order"]:  # and a recorder that keeps a callee's own order of touches
        F._one_order = lambda items, key: list(items)
    if sys.argv[1:] == ["--broken-ordered-levels"]:     # and views that ask no order below the top
        F.View._ordered_keys = lambda self: (self._r.on and self._r.callee is None and not self._t.foreign
                                             and self._t.ordered and not self._p)
        F.Recorder.order_tree = lambda self, t, prefix, raw: None
    if sys.argv[1:] == ["--broken-made-rows"]:  # and views that write only the touched entry of a row made
        F.MADE_ROWS = False
    if sys.argv[1:] == ["--broken-cw-writes"]:  # and a call whose writes leave out a callee's write the block undid
        F.CW_WRITES = False
    if sys.argv[1:] == ["--broken-lanes"]:  # and views that do not take a PeerQueue's lane as a key
        F.View._attr_key = lambda self, name: False
    if sys.argv[1:] == ["--broken-ordered"]:    # and views that put no order on the tape for list(queue)
        F.View._ordered_keys = lambda self: False
    if sys.argv[1:] == ["--broken-attr-reads"]:     # and views that know no method's reads (has_chunks)
        F.ATTR_READS.clear()
        _fresh_queue = fresh_queue

        def fresh_queue_bare():
            out = _fresh_queue()
            F.ATTR_READS.clear()
            return out
        globals()["fresh_queue"] = fresh_queue_bare
    if sys.argv[1:] == ["--broken-values-order"]:   # and a table whose values' order is not asked
        VALUES_ORDERED[0] = False
    if sys.argv[1:] == ["--broken-cell"]:   # and a cell whose `+=` and `-=` log a write alone: it cannot replay
        def _update(self, d):
            if self._r.on:
                self._r.write(self._t, ("count",))
            self._h.count += d
            return self
        F.CountCell._update = _update
    if sys.argv[1:] == ["--broken-line"]:   # and a line whose changes log a write alone
        _line_log = F.DequeView._log

        def _log(self, write=False):
            if write:
                if self._r.on:
                    self._r.write(self._t, ("line",))
            else:
                _line_log(self)
        F.DequeView._log = _log
    if sys.argv[1:] == ["--broken-pop-miss"]:   # and views that take a pop that finds nothing as a write too
        F.POP_MISS_READ = False
    if sys.argv[1:] == ["--broken-list"]:   # and a view of a list that logs nothing
        F.ListView._log = lambda self, write=False: None
    if sys.argv[1:] == ["--broken-alias"]:  # and an alias check that refuses nothing
        import trace3                       # noqa: E402
        trace3.Tracer3.alias_check = lambda self, rec, nid: None
    if sys.argv[1:] == ["--broken-alloc"]:  # and views that store the row a read of a missing one hands out, as
        _sub = F.View._sub                  #   the toy's AutoMap did before v0.10 (§8.1: reading allocates nothing)

        def alloc(self, k, v):
            if isinstance(self._o, dict) and not dict.__contains__(self._o, k):
                dict.__setitem__(self._o, k, v)
            return _sub(self, k, v)
        F.View._sub = alloc
    sys.exit(main())
