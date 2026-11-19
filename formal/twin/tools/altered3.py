#!/usr/bin/env python3
"""Controls that must fail: the hand-counted trace with one field altered, replayed through the twin; each must give
one mismatch, at the altered record, for the reason the alteration is for.

    python3 altered3.py TRACE61 WORKDIR DIRECTED HAND DIRECTED44 [DIRECTED42 [V2 [DIRECTED4B [DIRECTED7]]]]

TRACE61 is the 5-node hand-counted cell's trace with §6.1's twelve traced alone (TRACE3_ONLY=sec61): its six
records are add_offer, parked, outstanding, may_ask, retry_offer, promise_due. HAND is the same cell traced whole:
its one on_ihave record that reaches §6.1's functions is altered too. DIRECTED and DIRECTED44 are §6.1's directed
records and directed44.py's, which hold the whole state. V2 is a cell's trace under --doc v2: its header and one of
its records (`v2_controls`).

- Alterations of what a record says happened: a return value, a tape, a write's value, a write removed or added.
  The replay compares the state before the tables' notes, so these fail as "return value", "tape" or "post".
- Alterations that leave the outcome and the state alone and change only what was read or written: a read
  removed, a scan removed, a write of the value an entry had (which the twin does not make), an entry moved from
  the writes to the rest (which the twin then writes unasked). These fail as "footprint, reads" or
  "footprint, writes".
- Records that are not records: refused as malformed, each for its own reason.
- The members `reached` and `tables`: missing, not sorted, twice, or not what the record says; a function the
  header does not list as traced; a line that does not end with the two. Every alteration of the reads, scans or
  writes leaves `tables` as the tracer would write it for the altered record (`retable`), so that the check of
  `tables` does not refuse the record before what the alteration is for is seen.
- One alteration must pass, and shows what the replay does not see: a read the twin does not make (allowed, and
  counted). The replay compares `reached` with the functions the twin entered, so a function left out of it, or
  one put in, fails.
- With DIRECTED42, the §4.2 directed records: a callee's `cr` and `cw` at the call, the queue's keys and the mesh
  question, and the chunk argument (`format5_controls`).
- With DIRECTED4B, the deferral path's directed records: the orders of the twin's own levels asked (`pending`,
  `tie_slot`, and `tied`'s three levels), and installed_block's answer (`deferral_controls`).
- The queue, on HAND: a lane's `cw` on the other lane, dropped, and one entry shorter (`queue_controls`); and, on
  TRACE61, a read of `queue` on the tape, which is no other section's table.

Then the trace's envelope (header, constants, trailer, framing), the reader's controls (a line the strict scan
must refuse before it is parsed, each for the scan's own reason: `reader_controls`), a replay of a subset
(`--only`: `subset_controls`), and header3.py's check.

With DIRECTED, whose records hold the whole state: the controls of a raise, of own_order on a tape, and of `rest`,
among them the record whose scan would bring in the rest of the state. With DIRECTED44: of shuffled on a tape.
"""
import copy
import gzip
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content                          # noqa: E402
import header3                          # noqa: E402
import layout                           # noqa: E402
import os                               # noqa: E402
# the replay a run built for itself (SPEC_TWIN_REPLAY), or the twin's own build
REPLAY = Path(os.environ.get("SPEC_TWIN_REPLAY") or layout.REPLAY)


def retable(r):
    """`tables` as the tracer writes it for the record as it now is: the tables its reads, scans and writes name."""
    r["tables"] = sorted({e[0] for e in r["reads"]} | {s[0] for s in r["scans"]} | {e[0] for e in r["writes"]})


# ---- what a record says happened
def alter_may_ask(r):                   # a write's value: asked_at one ulp later
    r["writes"][0][2] += 1


def alter_add_offer(r):                 # its tape: listed answers 256, at the limit (the twin then does not list)
    r["tape"][0][2] = 256


def alter_outstanding(r):               # its read of queue[4].normal: an IWANT of the chunk queued there
    e = next(e for e in r["reads"] if e[0] == "queue")
    e[2] = [[None, [["iwant", [r["args"][1]]]], False]]


def alter_parked(r):                    # its return value
    r["ret"] = not r["ret"]


def alter_retry_offer(r):               # its read of mine: the chunk not held, so the twin asks on
    a = r["args"][0]
    g, i = (a[0], a[1]) if isinstance(a, list) else (a[:64], int.from_bytes(bytes.fromhex(a)[32:36], "little"))
    e = next(e for e in r["reads"] if e[:2] == ["mine", [g]])
    v = (e[2] or 0) ^ (1 << i)
    e[2] = v or None


def alter_write_removed(r):             # may_ask: the write of tried is not in the record
    r["writes"] = r["writes"][:1]
    retable(r)


def alter_write_added(r):               # parked: the record says the Python set the park it read
    r["writes"] = [[r["reads"][0][0], r["reads"][0][1], r["t"]]]
    retable(r)


def alter_read_value(r):                # may_ask: asked_at read as now, so an ask is in flight
    r["reads"][0][2] = r["t"]


# ---- what was read and written, the outcome and the state left alone
def alter_read_removed(r):              # promise_due: the read of its promise is not in the record
    r["reads"] = []
    retable(r)


def alter_scan_removed(r):              # outstanding: the scan of the promises is not in the record
    r["scans"] = []
    retable(r)


def alter_write_same(r):                # parked: the record says the Python wrote the park, to what it was
    r["writes"] = [[r["reads"][0][0], r["reads"][0][1], r["reads"][0][2]]]
    retable(r)


def alter_write_to_rest(r):             # may_ask: tried is in the rest, as written, and not among the writes
    r["rest"] = [r["writes"][1]]
    r["writes"] = r["writes"][:1]
    retable(r)


# ---- a record that is not one: refused as malformed (or, for an argument, where the call reads it)
def alter_bits_wrap(r):                 # a float word past 64 bits (it would wrap to the same value)
    r["writes"][0][2] += 2 ** 64


def alter_entry_twice(r):               # an entry twice among the reads
    r["reads"].append(r["reads"][0])
    retable(r)


def alter_write_twice(r):               # an entry twice among the writes
    r["writes"].append(r["writes"][0])
    retable(r)


def alter_scan_twice(r):                # a level twice among the scans
    r["scans"].append(r["scans"][0])
    retable(r)


def alter_group_case(r):                # a group key in capitals, in the arguments
    r["args"][0][0] = r["args"][0][0].upper()


def alter_state_group_case(r):          # a group key in capitals, in an entry's path (offered)
    r["writes"][0][1][1] = r["writes"][0][1][1].upper()


def alter_unknown_table(r):             # an entry of a table the twin does not have
    r["reads"][0][0] = "parks"
    retable(r)


def alter_unknown_foreign(r):           # a read, on the tape, of a table the twin does not ask (outstanding's tape
    r["tape"].insert(0, ["read", "queues", [r["args"][0]], None])   #   is empty: one is put on it)


def alter_queue_on_tape(r):             # a read of `queue` on the tape. The queue is the twin's own table: no tape
    r["tape"].insert(0, ["read", "queue", [r["args"][0]], None])    #   entry of it


def alter_not_list(r):                  # reads that are not a list (`tables` is left as it was)
    r["reads"] = {}


def alter_record_field(r):              # a field no record has
    r["raised"] = "KeyError"


def alter_no_ret(r):                    # neither a return value nor an exception (it would read as None)
    del r["ret"]


def alter_ret_and_raises(r):            # a return value and an exception
    r["raises"] = "ValueError"


def alter_empty_value(r):               # an empty offer list written as a value (the tracer writes it as missing)
    r["writes"][1][2] = []


def alter_value_kind(r):                # a value of another table's kind: a list where asked_at has a time
    r["reads"][0][2] = [4]


def alter_level(r):                     # a level that is none of the twin's tables'
    r["scans"] = [["promises", [1]]]
    retable(r)


def alter_no_rest(r):                   # no rest at all (it would read as empty)
    del r["rest"]


def alter_after_result(r):              # the timer's entry on the tape with a result (`after` returns nothing)
    r["tape"][0][2] = {}


# ---- the members reached and tables, and the line's end
def alter_no_reached(r):
    del r["reached"]


def alter_reached_without_own(r):       # reached, without the call's own function
    r["reached"] = []


def alter_reached_unsorted(r):          # may_ask: reached with a second function, not in order
    r["reached"] = ["outstanding", "may_ask"]


def alter_reached_twice(r):
    r["reached"] = [r["fn"], r["fn"]]


def alter_reached_not_name(r):
    r["reached"] = [r["fn"], 4]


def alter_reached_untraced(r):          # may_ask: reached names on_ihave, which a §6.1-only trace does not trace
    r["reached"] = sorted([r["fn"], "on_ihave"])


def alter_no_tables(r):
    del r["tables"]


def alter_tables_more(r):               # tables names one table more than the reads, scans and writes
    r["tables"] = sorted(r["tables"] + ["promises"])


def alter_tables_fewer(r):              # tables leaves one out
    r["tables"] = r["tables"][:-1]


def alter_tables_unsorted(r):
    r["tables"] = r["tables"][::-1]


def alter_reached_last(r):              # tables before reached, at the line's end
    r["reached"] = r.pop("reached")


def alter_member_after(r):              # ret after the two
    r["ret"] = r.pop("ret")


ENDS = "malformed record: its line does not end with reached and tables, as the record has them"
NOT_NAMED = "malformed record: tables: not the tables the reads, scans and writes name"
ALTER = {   # name -> (the change, how the replay's reason must begin: after "fn[...]: ", or "malformed record: ...")
    "may_ask": (alter_may_ask, "post"),
    "add_offer": (alter_add_offer, "post"),
    "outstanding": (alter_outstanding, "return value"),
    "parked": (alter_parked, "return value"),
    "retry_offer": (alter_retry_offer, "tape"),
    "may_ask/write-removed": (alter_write_removed, "post"),
    "parked/write-added": (alter_write_added, "post"),
    "may_ask/read-value": (alter_read_value, "tape"),
    "promise_due/read-removed": (alter_read_removed, "footprint, reads: the twin reads"),
    "outstanding/scan-removed": (alter_scan_removed, "footprint, reads: the twin scans"),
    "parked/write-same": (alter_write_same, "footprint, writes: the twin does not write"),
    "may_ask/write-to-rest": (alter_write_to_rest, "footprint, writes: the twin writes"),
    "may_ask/bits": (alter_bits_wrap, "malformed record: not a 64-bit word"),
    "add_offer/entry-twice": (alter_entry_twice, "malformed record: reads: a key twice"),
    "add_offer/write-twice": (alter_write_twice, "malformed record: writes: a key twice"),
    "outstanding/scan-twice": (alter_scan_twice, "malformed record: scans: a key twice"),
    "promise_due/group": (alter_group_case, "not a group key"),      # refused where the arguments are read
    "add_offer/state-group": (alter_state_group_case, "malformed record: not a group key"),
    "parked/table": (alter_unknown_table, "malformed record: not an entry of §6.1's tables: parks"),
    "outstanding/foreign-table": (alter_unknown_foreign, "malformed record: not a table §6.1 reads of another section"),
    "outstanding/queue-on-tape": (alter_queue_on_tape, "malformed record: not a table §6.1 reads of another section: queue"),
    "may_ask/reads-not-a-list": (alter_not_list, "malformed record: array expected"),
    "retry_offer/record-field": (alter_record_field, "malformed record: not a field of a record: raised"),
    "promise_due/no-ret": (alter_no_ret, "malformed record: a record has ret or raises, one of them"),
    "parked/ret-and-raises": (alter_ret_and_raises, "malformed record: a record has ret or raises, one of them"),
    "add_offer/empty-value": (alter_empty_value, "malformed record: an empty offer list as a value"),
    "may_ask/value-kind": (alter_value_kind, "malformed record: Natural number expected"),
    "outstanding/level": (alter_level, "malformed record: not a level of §6.1's tables"),
    "retry_offer/no-rest": (alter_no_rest, "malformed record: no rest"),
    "may_ask/after-result": (alter_after_result, "malformed record: after returns nothing"),
    "may_ask/no-reached": (alter_no_reached, "malformed record: no reached"),
    "may_ask/reached-without-own": (alter_reached_without_own,
                                    "malformed record: reached: the call's own function is not in it"),
    "may_ask/reached-unsorted": (alter_reached_unsorted, "malformed record: reached: not sorted, or a name twice"),
    "may_ask/reached-twice": (alter_reached_twice, "malformed record: reached: not sorted, or a name twice"),
    "may_ask/reached-not-a-name": (alter_reached_not_name, "malformed record: reached: not a name"),
    "may_ask/reached-untraced": (alter_reached_untraced,
                                 "malformed record: reached: a function the header does not list as traced: on_ihave"),
    "may_ask/no-tables": (alter_no_tables, "malformed record: no tables"),
    "may_ask/tables-more": (alter_tables_more, NOT_NAMED),
    "may_ask/tables-fewer": (alter_tables_fewer, NOT_NAMED),
    "may_ask/tables-unsorted": (alter_tables_unsorted, "malformed record: tables: not sorted, or a name twice"),
    "may_ask/reached-last": (alter_reached_last, ENDS),
    "may_ask/member-after": (alter_member_after, ENDS),
}


# ---- the whole hand cell's one record of an IHAVE that reaches §6.1's functions. A cell has no record of on_ihave
#      of its own: it is the frame's record that carries the IHAVE. on_ihave's return value is not in that record:
#      the asks show in the entry respond enqueues.
def big_ihave(r):
    return r["fn"] == "on_frame" and "may_ask" in r["reached"]


def alter_ihave_ret(r):                 # the asks on_ihave returned, as respond sends them: none
    e = next(t for t in r["tape"] if t[0] == "enqueue" and t[1][1][0] == "entry")
    iw = next(m for m in e[1][1][1][1] if m[0] == "iwant")
    assert iw[1], "the frame's response carries no ask"
    iw[1] = []


def alter_ihave_write_removed(r):       # the write of ihave_asked is not in the record
    r["writes"] = [e for e in r["writes"] if e[0] != "ihave_asked"]
    retable(r)


def alter_ihave_authenticable(r):       # its tape: the group is not authenticable
    at = next(i for i, t in enumerate(r["tape"]) if t[0] == "authenticable")
    r["tape"][at][2] = False


def alter_ihave_read_removed(r):        # the read of ihave_frames is not in the record (its write is)
    r["reads"] = [e for e in r["reads"] if e[0] != "ihave_frames"]
    retable(r)


ALTER44 = {
    "on_frame/ihave-asks-not-sent": (alter_ihave_ret, "tape"),
    "on_frame/ihave-write-removed": (alter_ihave_write_removed, "post"),
    "on_frame/ihave-authenticable": (alter_ihave_authenticable, "tape"),
    "on_frame/ihave-read-removed": (alter_ihave_read_removed, "footprint, reads: the twin reads"),
}


CFILE = []                              # the file with the tree's content line, written once by main


def run(f, *spec, given=True):
    """The replay on a file, with the tree's content line unless `spec` gives another (`given=False`: with none)."""
    if not spec and given:
        spec = ("--content", CFILE[0])
    p = subprocess.run([str(REPLAY), *spec, str(f)], capture_output=True, text=True)
    m = re.search(r"^replay: (\d+) records, (\d+) ok, (\d+) mismatched$", p.stdout, re.M)
    ex = re.findall(r"^example: (.*)$", p.stdout, re.M)
    fewer = re.search(r"^reads of the Python's that the twin did not make: (\d+)$", p.stdout, re.M)
    # the whole output (an uncaught exception's line is on stderr), and stderr alone, which a judgment wants empty
    return p.returncode, m, ex, int(fewer.group(1)) if fewer else None, p.stdout + p.stderr, p.stderr


def dump(r):
    return json.dumps(r, separators=(",", ":"))


CONTENT = []                            # the tree's content line (content.py), which every trace written here starts with
RAW = object()                          # first in a list of lines: the lines are the whole file, with no content line put first


def content_line():
    if not CONTENT:
        CONTENT.append(content.line(content.content(layout.toy())))
    return CONTENT[0]


def load(path):
    """A trace's lines from its header on, parsed. Its first line must be this tree's content line."""
    with gzip.open(path, "rt") as f:
        assert f.readline() == content_line(), f"{path}: its first line is not this tree's content line"
        return [json.loads(x) for x in f]


def write(f, lines):                    # a line given as text is written as it is; the content line first
    lines = list(lines)
    start = "" if lines[:1] == [RAW] else content_line()
    f.write_text(start + "".join((r if isinstance(r, str) else dump(r)) + "\n" for r in lines if r is not RAW))


def alone(hdr, consts, r, rest=None):
    """A trace of one record, with its trailer."""
    n = len(r.get("rest", [])) if rest is None else rest
    name = r["fn"] + (" (raises)" if "raises" in r else "")
    return [hdr, consts, r, {"trailer": {"records": 1, "by_fn": {name: 1}, "rest": n}}]


def altered(lines, pick, alter, f):
    """The trace with the one record `pick` takes altered, written to f, the trailer's count of the rest kept right;
    the altered record's function."""
    out = copy.deepcopy(lines)
    hit = [r for r in out if "fn" in r and pick(r)]
    assert len(hit) == 1, (f.name, len(hit))
    alter(hit[0])
    out[-1]["trailer"]["rest"] = sum(len(r.get("rest", [])) for r in out if "fn" in r)
    write(f, out)
    return hit[0]["fn"]


def as_must(rc, m, ex, fewer, fn, reason, err=""):
    """The replay ended with 1 on a whole report (its summary and its line of the reads), with one mismatch, at the
    altered record, for the reason: a malformed record's, or the reason after "fn[...]: ". A replay that printed
    the expected lines and then died is not that, by a signal or by an uncaught exception: an exception also ends
    with 1, and writes its line on stderr, which must be empty."""
    if rc != 1 or fewer is None or err.strip():
        return False
    if m is None or m.group(3) != "1" or len(ex) != 1:
        return False
    if reason.startswith("malformed record: "):
        return ex[0].startswith(reason)
    at = re.match(rf".* {fn}\[.*?\]: (.*)$", ex[0])
    return at is not None and at.group(1).startswith(reason)


def alterations(lines, hand, work):
    bad = 0
    cases = [(name, lines, lambda r, fn=name.split("/")[0]: r["fn"] == fn, alter, reason)
             for name, (alter, reason) in ALTER.items()]
    cases += [(name, hand, big_ihave, alter, reason) for name, (alter, reason) in ALTER44.items()]
    for name, ls, pick, alter, reason in cases:
        f = work / f"altered-{name.replace('/', '-')}.jsonl"
        fn = altered(ls, pick, alter, f)
        rc, m, ex, fewer, _, err = run(f)
        ok = as_must(rc, m, ex, fewer, fn, reason, err)
        bad += not ok
        print(f"{name}: {m.group(0) if m else 'no report'}; {ex[0][:400] if ex else '-'}{'' if ok else '  <-- FAIL'}")

    # the two alterations that must pass: what the replay does not see
    def read_added(r):                  # add_offer: a read of a park, which the twin does not make
        r["reads"].append(["park", [r["args"][1], r["args"][0][0]], None])
        retable(r)

    def reached_fewer(r):               # the frame with an IHAVE: may_ask left out of reached
        r["reached"] = [x for x in r["reached"] if x != "may_ask"]

    def reached_more(r):                # the same frame: ledger, a traced function it does not reach, put in reached
        r["reached"] = sorted(r["reached"] + ["ledger"])

    f = work / "altered-add_offer-read-added.jsonl"
    altered(lines, lambda r: r["fn"] == "add_offer", read_added, f)
    rc, m, ex, fewer, _, err = run(f)
    ok = rc == 0 and m is not None and m.group(3) == "0" and fewer == 1 and not err.strip()
    bad += not ok
    print(f"add_offer/read-added (must pass, with one read counted): {m.group(0) if m else 'no report'}; "
          f"reads the twin did not make: {fewer}{'' if ok else '  <-- FAIL'}")
    # the replay compares reached with the functions the twin entered: a call that reached one fewer, or one more,
    # fails
    for name, change in (("on_frame/reached-fewer", reached_fewer), ("on_frame/reached-more", reached_more)):
        f = work / f"altered-{name.replace('/', '-')}.jsonl"
        altered(hand, big_ihave, change, f)
        rc, m, ex, fewer, _, err = run(f)
        ok = as_must(rc, m, ex, fewer, "on_frame", "reached: the twin entered", err)
        bad += not ok
        print(f"{name} (must fail: reached is not what the twin entered): {m.group(0) if m else 'no report'}; "
              f"{ex[0][:300] if ex else '-'}{'' if ok else '  <-- FAIL'}")
    print("ok: every alteration as it must be" if not bad else f"{bad} alterations not as they must be")
    return bad


def self_test():
    """The judgment of an alteration (`as_must`), on what a replay could say: the expected report with its exit
    code; the same report from a replay that then died; the same without its last lines; another reason."""
    summary = re.search(r"^replay: (\d+) records, (\d+) ok, (\d+) mismatched$", "replay: 6 records, 5 ok, 1 mismatched", re.M)
    ex = ["node 2 at 3.096190 may_ask[[\"g\",0],4]: post: the whole state: …"]
    cases = [("the expected report, exit code 1", (1, summary, ex, 0, "may_ask", "post"), True),
             ("the same report from a replay that was killed after it (137)", (137, summary, ex, 0, "may_ask", "post"), False),
             ("the same report with exit code 0", (0, summary, ex, 0, "may_ask", "post"), False),
             ("the same report without its line of the reads", (1, summary, ex, None, "may_ask", "post"), False),
             ("another reason than the alteration's", (1, summary, ex, 0, "may_ask", "tape"), False),
             ("the expected report with exit code 1, and an uncaught exception's line on stderr",
              (1, summary, ex, 0, "may_ask", "post", "uncaught exception: replay: …\n"), False)]
    bad = 0
    for name, args, want in cases:
        got = as_must(*args)
        bad += got != want
        print(f"altered3 self-test, {name}: {'taken as its failure' if got else 'not taken'}"
              f"{'' if got == want else '  <-- must be ' + ('taken' if want else 'not taken')}")
    return 1 if bad else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    src, work, directed, hand_src, directed44 = Path(argv[0]), Path(argv[1]), Path(argv[2]), Path(argv[3]), Path(argv[4])
    work.mkdir(parents=True, exist_ok=True)
    lines, hand = load(src), load(hand_src)      # from the header on: the content line is written back by `write`
    assert lines[0]["header"]["traced"] == sorted(header3.trace3.SEC61), "TRACE61 is not a trace of §6.1's twelve alone"
    assert hand[0]["header"]["traced"] == sorted(header3.trace3.BLOCK), "HAND is not a trace of the whole block"
    head = str(work / "content.line")   # the tree's content line, which every replay here is given
    Path(head).write_text(content_line())
    CFILE.append(head)
    bad = alterations(lines, hand, work)
    other = str(work / "content-other.line")    # the same names, one file's bytes another's
    one = json.loads(content_line())
    one["content"]["files"]["toy/node.py"] = "0" * 64
    Path(other).write_text(content.line(one))
    more = content_line().replace(',"version":1}}', ',"note":1,"version":1}}')
    assert more != content_line()
    hdr, trailer = lines[0], lines[-1]

    def variant(**change):
        h = copy.deepcopy(hdr)
        h["header"].update(change)
        return h

    def tr(**change):
        t = copy.deepcopy(trailer)
        t["trailer"].update(change)
        return t

    ask = next(i for i, r in enumerate(lines) if r.get("fn") == "may_ask")
    assert "nodes" in lines[1] and "fn" in lines[2], "TRACE61's second line is not its nodes line, or its third no record"

    def nodes_of(change):               # the nodes line with its entries changed
        return {"nodes": change(copy.deepcopy(lines[1]["nodes"]))}
    twice = dump(lines[ask]).replace('"ret":true', '"ret":false,"ret":true')
    assert twice != dump(lines[ask])
    # an exponent makes the line as much shorter than its compact form as the member twice makes it longer
    padded = twice.replace(f'"n":{lines[ask]["n"]},', '"n":1e15,')
    assert padded != twice and len(padded) - len(dump(lines[ask])) == len("1000000000000000") - len(str(lines[ask]["n"]))
    escaped = dump(lines[ask]).replace('"ret":true', '"r\\u0065t":true')
    assert escaped != dump(lines[ask])
    fns = dict(trailer["trailer"]["by_fn"])
    traced = hdr["header"]["traced"]
    cl = content_line()[:-1]
    cases = {   # name -> (lines, --content, the exit code it must give, the words its refusal must have)
        "the trace, the right --content": (lines, head, 0, None),
        # the content line: the trace's first line, the bytes of the file given with --content
        "another content than --content's": (lines, other, 1, "content: NOT --content's: toy/node.py: other bytes"),
        "no content line": ([RAW] + lines, head, 1, "content: NOT --content's: the trace's first line is no content line"),
        "the trace, with no --content given": (lines, None, 1, "content: not compared (no --content given): the trace does not pass"),
        "the content line twice": ([RAW, cl, cl] + lines, head, 1, "content: a content line that is not the trace's first line"),
        "the content line once more, after the nodes line": (lines[:2] + [cl] + lines[2:], head, 1,
                                                             "content: a content line that is not the trace's first line"),
        "the content line after the header": ([RAW, hdr, cl] + lines[1:], head, 1,
                                              "content: NOT --content's: the trace's first line is no content line"),
        "a content line with a member more": ([RAW, more[:-1]] + lines, head, 1,
                                              "content: NOT --content's: the trace's first line is no content line"),
        "a content line with a space in it": ([RAW, cl.replace('"version":1', '"version": 1')] + lines, head, 1,
                                              "content: NOT --content's: "),
        "a header of format 6, with its commit, and no content line": (
            [RAW, variant(format=6, spec_head="0" * 40, spec_clean=True)] + lines[1:], head, 1,
            "content: NOT --content's: the trace's first line is no content line"),
        "a header twice": (lines[:1] + lines, head, 1, "header: not the trace's second line, or not its only header"),
        "a failed header, then the right one": ([variant(format=6)] + lines[1:-1] + [hdr, trailer], head, 1,
                                                "header: not the trace's second line, or not its only header"),
        "no header": (lines[1:], head, 1, "nodes: not the trace's third line, or a second nodes line"),
        "no header, and nothing after the content line": ([], head, 1, "header: none"),
        "format 6": ([variant(format=6)] + lines[1:], head, 1, "header: format (some 6), this replay reads format 7"),
        "a header that names a commit": ([variant(spec_head="0" * 40)] + lines[1:], head, 1, "header: not a member of it: spec_head"),
        "another table among its own": ([variant(own=hdr["header"]["own"] + ["queue"])] + lines[1:], head, 1,
                                        "header: the tables are not this twin's"),
        "a header with a member it should not have": ([variant(note="x")] + lines[1:], head, 1, "header: not a member of it: note"),
        "a header that does not say whether the state is whole": (
            [{"header": {k: v for k, v in hdr["header"].items() if k != "whole"}}] + lines[1:], head, 1, "header: no whole"),
        "a header that does not say what was traced": (
            [{"header": {k: v for k, v in hdr["header"].items() if k != "traced"}}] + lines[1:], head, 1, "header: no traced"),
        "a header whose traced is not sorted": ([variant(traced=traced[::-1])] + lines[1:], head, 1,
                                                "header: traced is not a sorted list of names"),
        "a header whose traced leaves out a function a record reached": (
            [variant(traced=[f for f in traced if f != "may_ask"])] + lines[1:], head, 1,
            "malformed record: reached: a function the header does not list as traced: may_ask"),
        # the nodes line: one, before every record, every node of a record in it
        "a second nodes line": (lines[:2] + [lines[1]] + lines[2:], head, 1,
                                "nodes: not the trace's third line, or a second nodes line"),
        "no nodes line, and no record": ([hdr, tr(records=0, rest=0, by_fn={})], head, 1, "nodes: none"),
        "the nodes line after the first record": ([hdr, lines[2], lines[1]] + lines[3:], head, 1,
                                                  "a record before the nodes line"),
        "a nodes line that leaves out a record's node": (
            [hdr, nodes_of(lambda es: [{**es[0], "n": [n for n in es[0]["n"] if n != lines[ask]["n"]]}])] + lines[2:],
            head, 1, f"malformed record: n: a node the nodes line does not name: {lines[ask]['n']}"),
        "a nodes line with a node twice": (
            [hdr, nodes_of(lambda es: es + [{**es[0], "n": es[0]["n"][:1]}])] + lines[2:], head, 1,
            f"nodes: a node twice: {lines[1]['nodes'][0]['n'][0]}"),
        "a nodes line with an entry of no node": (
            [hdr, nodes_of(lambda es: es + [{**es[0], "n": []}])] + lines[2:], head, 1, "nodes: an entry of no node"),
        "a nodes line whose entry has a member it should not have": (
            [hdr, nodes_of(lambda es: [{**es[0], "note": "x"}])] + lines[2:], head, 1, "nodes: not a member of it: note"),
        "a nodes line whose entry has no replaced": (
            [hdr, nodes_of(lambda es: [{k: v for k, v in es[0].items() if k != "replaced"}])] + lines[2:], head, 1,
            "nodes: no replaced"),
        "a nodes line with a replaced name the twin has no question for": (
            [hdr, nodes_of(lambda es: [{**es[0], "replaced": ["on_chunk"]}])] + lines[2:], head, 1,
            "nodes: a replaced function the twin has no question for: on_chunk"),
        # level 1 replaced: a scenario's validate_chunk is a directed set's, a trace of the whole state; this cell's
        # trace is not one. (Where it is taken: level1_controls, directed42's record.)
        "a cell's nodes line with validate_chunk replaced at its nodes": (
            [hdr, nodes_of(lambda es: [{**es[0], "replaced": ["validate_chunk"]}])] + lines[2:], head, 1,
            "which only a trace of the whole state may"),
        "a nodes line whose constants lack one": (
            [hdr, nodes_of(lambda es: [{**es[0], "consts": {k: v for k, v in es[0]["consts"].items() if k != "PROMISE"}}])]
            + lines[2:], head, 1, "nodes: consts: no PROMISE"),
        "a wrong trailer, then the right one": (lines[:-1] + [tr(records=7), trailer], head, 1, "trailer: 7 records written, 6 read"),
        "a record after the trailer": (lines + [lines[2]], head, 1, "trailer: a line after the trailer"),
        "no trailer": (lines[:-1], head, 1, "trailer: none (the trace is cut off)"),
        "a trailer with another count of the rest": (lines[:-1] + [tr(rest=trailer["trailer"]["rest"] + 1)], head, 1,
                                                     "entries of rest written, 0 read"),
        "a record with a member twice": (lines[:ask] + [twice] + lines[ask + 1:], head, 1, "a member twice in one object: ret"),
        "a record with a member twice, and a number with an exponent that hides its length": (
            lines[:ask] + [padded] + lines[ask + 1:], head, 1, "a number that is not a plain integer"),
        "a record with a number with a sign": (
            lines[:ask] + [dump(lines[ask]).replace(f'"n":{lines[ask]["n"]},', f'"n":-{lines[ask]["n"]},')] + lines[ask + 1:],
            head, 1, "a number with a sign"),
        "a record with a number with an exponent": (
            lines[:ask] + [dump(lines[ask]).replace(f'"n":{lines[ask]["n"]},', '"n":2e0,')] + lines[ask + 1:], head, 1,
            "a number that is not a plain integer"),
        "a record with an escape in a member's name": (lines[:ask] + [escaped] + lines[ask + 1:], head, 1, "an escape in a string"),
        "a record with a space after it": (lines[:ask] + [dump(lines[ask]) + " "] + lines[ask + 1:], head, 1,
                                           "something after the line's value"),
        "a record with a space inside it": (
            lines[:ask] + [dump(lines[ask]).replace('"ret":true', '"ret": true')] + lines[ask + 1:], head, 1,
            "white space outside a string"),
        "a trailer whose by_fn is not a map": (lines[:-1] + [tr(by_fn=False)], head, 1, "trailer: by_fn is not an object"),
        "a trailer with one function's count wrong": (lines[:-1] + [tr(by_fn={**fns, "may_ask": 2})], head, 1,
                                                       "trailer: by_fn is not the records read"),
        "a trailer without by_fn": (
            lines[:-1] + [{"trailer": {k: v for k, v in trailer["trailer"].items() if k != "by_fn"}}], head, 1, "trailer: no by_fn"),
        "the constants with a member twice": (
            [hdr, dump(lines[1]).replace('"PROMISE":', '"PROMISE":1,"PROMISE":', 1)] + lines[2:], head, 1,
            "a member twice in one object: PROMISE"),
    }
    hbad = 0
    for name, (ls, spec, want, why) in cases.items():
        f = work / f"header-{name.replace(' ', '-').replace(',', '')}.jsonl"
        write(f, ls)
        rc, _, _, _, out, _ = run(f, "--content", spec) if spec is not None else run(f, given=False)
        if why is None:
            said, word = True, ""
        else:
            said = why in out
            word = ("; says: " if said else "; does NOT say: ") + why
        ok = rc == want and said
        hbad += not ok
        print(f"envelope, {name}: replay rc={rc}, must be {want}{word}{'' if ok else '  <-- FAIL'}")
    print("ok: every control of the envelope as it must be" if not hbad else f"{hbad} controls of the envelope wrong")
    hbad += reader_controls(lines, ask, work, head)
    sbad = subset_controls(lines, hand, work, head)
    kbad = header3_controls(hdr, hand[0], work, directed, directed44)
    rbad = raise_controls(directed, work, head)
    obad = order_controls(directed, work, head)
    wbad = rest_controls(directed, work, head)
    pbad = shuffled_controls(directed44, work, head)
    vbad = v010_controls(directed44, work, head)
    fbad = format5_controls(Path(argv[5]), work, head) if len(argv) > 5 else 0
    v2bad = v2_controls(Path(argv[6]), work, head) if len(argv) > 6 else 0
    dbad = deferral_controls(Path(argv[7]), Path(argv[5]), work, head) if len(argv) > 7 else 0
    dbad += writer_controls(Path(argv[8]), work, head) if len(argv) > 8 else 0
    dbad += nodes_controls(Path(argv[8]), work, head) if len(argv) > 8 else 0
    dbad += sec1_controls(Path(argv[9]), work, head) if len(argv) > 9 else 0
    dbad += drop_offer_controls(Path(argv[10]), work, head) if len(argv) > 10 else 0
    dbad += pace_controls(Path(argv[11]), work, head) if len(argv) > 11 else 0
    dbad += heartbeat_controls(Path(argv[12]), work, head) if len(argv) > 12 else 0
    dbad += claim_controls(Path(argv[13]), Path(argv[4]), work, head) if len(argv) > 13 else 0
    dbad += have_controls(Path(argv[14]), work, head) if len(argv) > 14 else 0
    dbad += frame_controls(Path(argv[15]), work, head) if len(argv) > 15 else 0
    dbad += decode_controls(Path(argv[16]), work, head) if len(argv) > 16 else 0
    dbad += level1_controls(Path(argv[17]), Path(argv[5]), work, head) if len(argv) > 17 else 0
    dbad += sec52_controls(Path(argv[18]), work, head) if len(argv) > 18 else 0
    dbad += sec53_controls(Path(argv[19]), work, head) if len(argv) > 19 else 0
    dbad += sec54_controls(Path(argv[20]), work, head) if len(argv) > 20 else 0
    dbad += publish_controls(Path(argv[21]), Path(argv[22]), work, head) if len(argv) > 22 else 0
    dbad += sec71_controls(Path(argv[23]), work, head) if len(argv) > 23 else 0
    dbad += sec51p_controls(Path(argv[24]), work, head) if len(argv) > 24 else 0
    dbad += stripe_controls(Path(argv[20]), work, head) if len(argv) > 20 else 0
    dbad += carried_controls(Path(argv[17]), Path(argv[9]), Path(argv[6]), work, head) if len(argv) > 17 else 0
    qbad = queue_controls(hand, work, head)
    return 1 if bad or hbad or sbad or kbad or rbad or obad or wbad or pbad or vbad or fbad or v2bad or dbad or qbad else 0


def queue_controls(hand, work, head):
    """The queue's altered records, on the whole hand cell's first record where one call on the tape writes a lane of
    the queue that no other call of the record touches (its enqueue of a HAVE, with its row): the record alone
    replays; with that call's cw on the other lane, with the lane's write dropped from its cw, and with the lane's
    value one entry shorter, it must fail, each at the whole state the record's writes give ("post"). Each outcome
    was written before it first ran."""
    hdr, consts = hand[0], hand[1]

    def pick(d):
        if "fn" not in d or "raises" in d:
            return None
        for k, t in enumerate(d["tape"]):
            if t[0] != "enqueue" or len(t) != 4 or not isinstance(t[3], dict):
                continue
            lanes = [e for e in t[3]["cw"] if e[0] == "queue" and len(e[1]) == 2 and e[2]]
            if len(lanes) != 1:
                continue
            # the lane alone, in a row that was there: where the call makes the row its cw has the other lane too,
            # and the control that moves the write to the other lane would name a lane twice (the cell's first
            # record with such a call is a frame whose response makes its peer's row)
            if len([e for e in t[3]["cw"] if e[0] == "queue" and len(e[1]) == 2]) != 1:
                continue
            path = lanes[0][1]
            others = [u for j, u in enumerate(d["tape"]) if j != k and len(u) == 4 and isinstance(u[3], dict)
                      and any(e[0] == "queue" and e[1][:1] == path[:1] for e in u[3]["cr"] + u[3]["cw"])]
            if not others:
                return k
        return None
    rec = next(d for d in hand if pick(d) is not None)
    k = pick(rec)

    def lane_of(r):
        return next(e for e in r["tape"][k][3]["cw"] if e[0] == "queue" and len(e[1]) == 2)
    other = copy.deepcopy(rec)
    e = lane_of(other)
    e[1] = [e[1][0], "normal" if e[1][1] == "urgent" else "urgent"]
    dropped = copy.deepcopy(rec)
    dropped["tape"][k][3]["cw"] = [x for x in dropped["tape"][k][3]["cw"] if not (x[0] == "queue" and len(x[1]) == 2)]
    fewer = copy.deepcopy(rec)
    lane_of(fewer)[2] = lane_of(fewer)[2][:-1]
    # a call's log: what the callee read must be the twin's state at the call, and a log has both members
    assert rec["tape"][k][3]["cr"], "the record's enqueue read no entry of the twin's tables first"
    cr_changed = copy.deepcopy(rec)
    e0 = cr_changed["tape"][k][3]["cr"][0]
    e0[2] = [] if e0[2] is None else None                   # a lane there and empty for a missing one, or the other way
    no_cw = copy.deepcopy(rec)
    del no_cw["tape"][k][3]["cw"]
    return check("the queue", {
        "that call's cr with a value changed": (alone(hdr, consts, cr_changed), 1, "its callee read"),
        "that call's log without cw": (alone(hdr, consts, no_cw), 1, "a call's log without cw"),
        "a record whose one call writes a lane, alone": (alone(hdr, consts, rec), 0, None),
        "that call's cw on the other lane": (alone(hdr, consts, other), 1, "]: post"),
        "that call's write of the lane dropped from its cw": (alone(hdr, consts, dropped), 1, "]: post"),
        "the lane's value in that cw one entry shorter": (alone(hdr, consts, fewer), 1, "]: post"),
    }, work, head, "queue")


def v2_controls(v2trace, work, head):
    """The controls of a cell's trace under --doc v2, each with the outcome written before it first ran:
    - header3.py passes its header as v2's kept, and refuses it with on_ihave among its traced (on_ihave calls gated,
      which v2 redefines), with gated among them (v2 redefines it), and with --doc v2 gone from its args (v2's kept
      is a kind only for a trace run so);
    - one of its may_ask records, alone, replays; with its read of asked_at as now (an ask in flight) it fails at
      that record for the reason hand5's may_ask/read-value fails ("tape": the twin arms no retry).
    A third control, a traced list with a redefined name left in, is trace3.py's own (--self-test-v2)."""
    toy = layout.toy()
    hdr, consts, rec = first(v2trace, lambda d: d["fn"] == "may_ask" and d.get("ret") is True and d["reads"][:1] != []
                             and d["reads"][0][0] == "asked_at" and d["reads"][0][2] is None)
    h = hdr["header"]
    assert header3.trace3.doc_of(h["args"]) == "v2", "V2 is not a trace run with --doc v2"

    def variant(**change):
        out = copy.deepcopy(hdr)
        out["header"].update(change)
        return out

    args = list(h["args"])
    k = args.index("--doc")
    hcases = {  # name -> (the header line, whether it must pass)
        "a v2 cell's header, v2's kept": (hdr, True),
        "with on_ihave among its traced": (variant(traced=sorted(h["traced"] + ["on_ihave"])), False),
        "with gated among its traced": (variant(traced=sorted(h["traced"] + ["gated"])), False),
        "with the whole block as its traced": (variant(traced=sorted(header3.trace3.BLOCK)), False),
        "with §6.1's twelve alone as its traced": (
            variant(traced=sorted(header3.trace3.SEC61)), False),
        "v2's kept, from a trace not run with --doc v2": (variant(args=args[:k] + args[k + 2:]), False),
    }
    bad = 0
    for name, (hl, must) in hcases.items():
        f = work / f"v2-header3-{re.sub(r'[^A-Za-z0-9_.]+', '-', name)}.jsonl"
        write(f, [hl])
        why = header3.check(toy, f)
        ok = (not why) == must
        bad += not ok
        print(f"v2, header3, {name}: {'passes' if not why else 'refused: ' + '; '.join(why)[:160]}, "
              f"must {'pass' if must else 'be refused'}{'' if ok else '  <-- FAIL'}")
    now = copy.deepcopy(rec)
    now["reads"][0][2] = rec["t"]
    bad += check("v2", {
        "a may_ask record of a v2 cell, alone": (alone(hdr, consts, rec), 0, None),
        "the same, its read of asked_at as now": (alone(hdr, consts, now), 1, "]: tape"),
    }, work, head, "v2")
    return bad


def reader_controls(lines, ask, work, head):
    """The strict reading of a line (formal/twin/SpecTwin/Strict.lean), which comes before the parser: one record's
    text is changed, and the replay must refuse that line unparsed, for the reason given here, go on to its
    report, and fail. A line the parser alone would refuse (a leading zero, a sign) or would labour over (a huge
    exponent) must be refused by the scan too: the reason says which of the two spoke."""
    rec = dump(lines[ask])
    n = f'"n":{lines[ask]["n"]},'
    assert rec.count(n) == 1 and rec.count('"ret":true') == 1 and rec.count('"fn":"may_ask"') == 1
    twice = rec.replace('"ret":true', '"ret":false,"ret":true')
    cases = {   # name -> (the line's text, how the scan's reason must begin)
        "a member twice": (twice, "a member twice in one object: ret"),
        "a member twice, and an exponent that hides its length": (twice.replace(n, '"n":1e15,'),
                                                                   "a number that is not a plain integer"),
        "a number with a huge exponent": (rec.replace(n, '"n":1e1000000000,'), "a number that is not a plain integer"),
        "an escape in a member's name": (rec.replace('"ret":true', '"r\\u0065t":true'), "an escape in a string"),
        "an escape in a value": (rec.replace('"fn":"may_ask"', '"fn":"may\\u005fask"'), "an escape in a string"),
        "a minus zero": (rec.replace(n, '"n":-0,'), "a number with a sign"),
        "a plus sign": (rec.replace(n, '"n":+2,'), "a number with a sign"),
        "a leading zero": (rec.replace(n, '"n":02,'), "a number with a leading zero"),
        "a space after the line's value": (rec + " ", "something after the line's value"),
        "a space inside it": (rec.replace('"ret":true', '"ret": true'), "white space outside a string"),
        "an empty line": ("", "a value expected at the line's end"),
    }
    bad = 0
    for name, (text, why) in cases.items():
        assert text != rec
        f = work / f"reader-{name.replace(' ', '-').replace(',', '').replace(chr(39), '')}.jsonl"
        write(f, lines[:ask] + [text] + lines[ask + 1:])
        try:
            p = subprocess.run([str(REPLAY), "--content", head, str(f)], capture_output=True, text=True, timeout=20)
            said = re.findall(r"^line (\d+): not a line the tracer writes: (.*)$", p.stdout, re.M)
            report = re.search(r"^replay: \d+ records, ", p.stdout, re.M) is not None
            count = re.search(r"^lines refused before they were parsed, or by the parser: 1$", p.stdout, re.M) is not None
            ok = (p.returncode == 1 and report and count and len(said) == 1 and int(said[0][0]) == ask + 2
                  and said[0][1].startswith(why))
            got = f"rc={p.returncode}, {'line ' + said[0][0] + ' refused: ' + said[0][1] if said else 'no line refused'}"
            got += "" if report else ", no report"
        except subprocess.TimeoutExpired:
            ok, got = False, "no answer in 20 s"
        bad += not ok
        print(f"reader, {name}: {got}; must be rc=1, line {ask + 2} refused: {why}{'' if ok else '  <-- FAIL'}")
    print("ok: every control of the reader as it must be" if not bad else f"{bad} controls of the reader wrong")
    return bad


def subset_controls(lines, hand, work, head):
    """A replay of a subset (`--only`, a mutant's): it reads the records whose line ends naming the function or the
    table, and skips the others unread; a line that does not end as it must is read whatever it names; and a
    subset that names a function the header does not list as traced, or a table not the twin's, is refused."""
    loose = copy.deepcopy(lines)        # parked's record with tables before reached, at its line's end
    p = next(r for r in loose if r.get("fn") == "parked")
    p["reached"] = p.pop("reached")
    n61, nh = sum("fn" in r for r in lines), sum("fn" in r for r in hand)
    cases = {   # name -> (lines, the subset, rc, records read, mismatched, records skipped, refused as naming nothing)
        "fn=may_ask, §6.1 alone": (lines, "fn=may_ask", 0, 1, 0, n61 - 1, False),
        "table=promises, §6.1 alone": (lines, "table=promises", 0, 2, 0, n61 - 2, False),
        "fn=may_ask, with parked's line not ending as it must": (loose, "fn=may_ask", 1, 2, 1, n61 - 2, False),
        "fn=may_ask, the whole cell": (hand, "fn=may_ask", 0, 1, 0, nh - 1, False),
        # (not held_back, which every record of on_heartbeat reads whole; hand5's five nodes are one mesh, so no
        # heartbeat there has a peer to gossip to, and no record touches the pace queue)
        "table=pace_queue, the whole cell, where no record touches it": (hand, "table=pace_queue", 0, 0, 0, nh, False),
        "fn=on_ihave, §6.1 alone, where it is not traced": (lines, "fn=on_ihave", 1, 0, 0, n61, True),
        "fn=no_such": (hand, "fn=no_such", 1, 0, 0, nh, True),
        "table=no_such": (hand, "table=no_such", 1, 0, 0, nh, True),
    }
    bad = 0
    for name, (ls, w, want, nread, nbad, nskip, nothing) in cases.items():
        f = work / f"subset-{re.sub(r'[^A-Za-z0-9_=.]+', '-', name)}.jsonl"
        write(f, ls)
        q = subprocess.run([str(REPLAY), "--only", w, "--content", head, str(f)], capture_output=True, text=True)
        m = re.search(r"^replay: (\d+) records, (\d+) ok, (\d+) mismatched$", q.stdout, re.M)
        s = re.search(rf"^subset: --only {re.escape(w)}: (\d+) records skipped unread$", q.stdout, re.M)
        refused = re.search(rf"^subset: --only {re.escape(w)}: not a function the header lists as traced", q.stdout,
                            re.M) is not None
        ok = (q.returncode == want and m is not None and int(m.group(1)) == nread and int(m.group(3)) == nbad
              and s is not None and int(s.group(1)) == nskip and refused == nothing)
        got = f"rc={q.returncode}; {m.group(0) if m else 'no report'}; {s.group(0) if s else 'no subset line'}"
        got += "; refused as naming nothing" if refused else ""
        bad += not ok
        print(f"subset, {name}: {got}; must be rc={want}, {nread} read, {nbad} mismatched, {nskip} skipped"
              f"{', refused as naming nothing' if nothing else ''}{'' if ok else '  <-- FAIL'}")
    print("ok: every control of a subset as it must be" if not bad else f"{bad} controls of a subset wrong")
    return bad


def first(directed, want):
    """The header, the nodes line (each node's constants) and the first record of a trace that `want` accepts."""
    hdr = consts = None
    for x in gzip.open(directed, "rt"):
        d = json.loads(x)
        if "header" in d:
            hdr = d
        elif "nodes" in d:              # the nodes line: each node's constants
            consts = d
        elif "fn" in d and want(d):
            return hdr, consts, d
    raise AssertionError("no such record")


def check(what, cases, work, head, tag):
    """Each case: (lines, the exit code, the words its reason must have). The words are looked for in the one example
    of the one-record trace, which must then have one mismatch; or, where the record itself replays, in the
    trailer's line or the nodes line's (words that begin with "trailer: " or "nodes: "). So a case that must fail
    fails for its reason, and not only with its code."""
    bad = 0
    for name, (ls, want, why) in cases.items():
        f = work / f"{tag}-{name.replace(' ', '-').replace(',', '')}.jsonl"
        write(f, ls)
        rc, m, ex, _, out, _ = run(f, "--content", head)
        if why is None:
            said = True
        elif why.startswith(("trailer: ", "nodes: ")):      # a refusal of the trailer's, or of the nodes line's
            kind = why[:why.index(" ") + 1]
            said = why[len(kind):] in "\n".join(l for l in out.splitlines() if l.startswith(kind))
        else:
            said = m is not None and m.group(3) == "1" and len(ex) == 1 and why in ex[0]
        ok = rc == want and said
        bad += not ok
        print(f"{what}, {name}: replay rc={rc}, must be {want}"
              f"{'' if why is None else ('; says: ' if said else '; does NOT say: ') + why}{'' if ok else '  <-- FAIL'}")
    print(f"ok: every control of {what} as it must be" if not bad else f"{bad} controls of {what} wrong")
    return bad


def rest_controls(directed, work, head):
    """`rest` in a record of the whole state: read strictly, counted by the trailer, and out of a scan's reach."""
    hdr, consts, rec = first(directed, lambda d: len(d["rest"]) >= 2 and d["reads"] and "raises" not in d)
    both = copy.deepcopy(rec)
    both["rest"].append([rec["reads"][0][0], rec["reads"][0][1], rec["rest"][0][2]])
    novalue = copy.deepcopy(rec)
    novalue["rest"][0][2] = None
    fewer = copy.deepcopy(rec)
    fewer["rest"] = fewer["rest"][1:]
    twice = copy.deepcopy(rec)
    twice["rest"].append(twice["rest"][0])
    # a scan that found promises, with those promises moved from the reads to the rest. The twin's scan would then
    # read the rest of the state, with its level allowed.
    _, _, scan = first(directed, lambda d: d["fn"] == "outstanding" and d.get("ret") is True
                       and any(e[0] == "promises" and e[2] is not None for e in d["reads"]))
    moved = copy.deepcopy(scan)
    moved["rest"] = moved["rest"] + [e for e in moved["reads"] if e[0] == "promises" and e[2] is not None]
    moved["reads"] = [e for e in moved["reads"] if e[0] != "promises"]
    retable(moved)
    return check("the rest of a record", {
        "the record as it is": (alone(hdr, consts, rec), 0, None),
        "one entry left out, and the trailer's count with it": (alone(hdr, consts, fewer), 0, None),
        "one entry left out, the trailer's count kept": (alone(hdr, consts, fewer, rest=len(rec["rest"])), 1,
                                                         "trailer: entries of rest written"),
        "an entry both read and in the rest": (alone(hdr, consts, both), 1, "malformed record: an entry both read and in the rest"),
        "an entry of the rest without a value": (alone(hdr, consts, novalue), 1, "malformed record: an entry of the rest without a value"),
        "an entry of the rest twice": (alone(hdr, consts, twice), 1, "malformed record: rest: a key twice"),
        "a record that scans the promises, as it is": (alone(hdr, consts, scan), 0, None),
        "that record with its promises moved from the reads to the rest": (alone(hdr, consts, moved), 1,
                                                                           "footprint, reads: the twin's scan holds an entry the Python did not read"),
    }, work, head, "rest")


def raise_controls(directed, work, head):
    hdr, consts, rec = first(directed, lambda d: d.get("raises") == "KeyError")
    return check("a KeyError's record", {
        "the record as it is": (alone(hdr, consts, rec), 0, None),
        "without its raises_key": (alone(hdr, consts, {k: v for k, v in rec.items() if k != "raises_key"}), 1,
                                   "malformed record: raises_key goes with a KeyError"),
        "with another key": (alone(hdr, consts, {**rec, "raises_key": rec["raises_key"] + 1000}), 1, "the Python raises KeyError on "),
        "raises_key on another exception": (alone(hdr, consts, {**rec, "raises": "ValueError"}), 1,
                                            "malformed record: raises_key goes with a KeyError"),
    }, work, head, "raise")


def order_controls(directed, work, head):
    """own_order on a record's tape: the first directed record that asks the order of two peers or more must
    pass alone; with an answer that is not a permutation of the question, or with another question than the
    twin asks, it must fail."""
    def asks(d):
        return "raises" not in d and any(t[0] == "own_order" and len(t[1][0]) >= 2 for t in d["tape"])
    hdr, consts, rec = first(directed, asks)
    at = next(i for i, t in enumerate(rec["tape"]) if t[0] == "own_order" and len(t[1][0]) >= 2)
    notperm = copy.deepcopy(rec)
    notperm["tape"][at][2][0] = max(rec["tape"][at][1][0]) + 1000     # a peer that was not asked about
    other = copy.deepcopy(rec)
    other["tape"][at][1][0] = other["tape"][at][1][0][::-1]           # the question's peers in another order
    return check("own_order on a tape", {
        "the record as it is": (alone(hdr, consts, rec), 0, None),
        "an answer that is not a permutation": (alone(hdr, consts, notperm), 1,
                                                "malformed record: own_order's answer is not a permutation of its question"),
        "another question than the twin asks": (alone(hdr, consts, other), 1, "tape: own_order("),
    }, work, head, "order")


def shuffled_controls(directed44, work, head):
    """shuffled on a record's tape (a draw is a question whose answer must be a permutation of it): the first record
    of DIRECTED44 that shuffles two asks or more must pass alone; with an answer that is not a permutation of the
    question, or with another question than the twin asks, it must fail."""
    def asks(d):
        return "raises" not in d and any(t[0] == "shuffled" and len(t[1][0]) >= 2 for t in d["tape"])
    hdr, consts, rec = first(directed44, asks)
    at = next(i for i, t in enumerate(rec["tape"]) if t[0] == "shuffled" and len(t[1][0]) >= 2)
    notperm = copy.deepcopy(rec)
    notperm["tape"][at][2][0] = notperm["tape"][at][2][1]             # one ask twice, another left out
    other = copy.deepcopy(rec)
    other["tape"][at][1][0] = other["tape"][at][1][0][::-1]           # the question's asks in another order
    return check("shuffled on a tape", {
        "the record as it is": (alone(hdr, consts, rec), 0, None),
        "an answer that is not a permutation": (alone(hdr, consts, notperm), 1,
                                                "malformed record: shuffled's answer is not a permutation of its question"),
        "another question than the twin asks": (alone(hdr, consts, other), 1, "tape: shuffled("),
    }, work, head, "shuffled")


def v010_controls(directed44, work, head):
    """v0.10's §4.4 on a record's tape: valid_id's reads of desc, a bitmap's valid_have, and the penalty. Each record
    passes alone as it is, and fails for its reason once changed."""
    # (`desc` is the twin's own: valid_id's reads of it are one entry of the record's reads, and the three controls
    # of those reads alter that entry. "said known" gets another answer from the twin, since the descriptor it is
    # given has the id's index for its count; "of another group" leaves the twin's read of the id's own group out of
    # the record's reads.)
    def dread(d):
        return next((e for e in d["reads"] if e[0] == "desc"), None)

    def valid_id(is_known):
        return lambda d: (d["fn"] == "valid_id" and "raises" not in d and d["ret"] is True
                          and dread(d) is not None and (dread(d)[2] is not None) == is_known)
    hdr, consts, known = first(directed44, valid_id(True))         # the count known: the group's descriptor read
    index = int.from_bytes(bytes.fromhex(known["args"][0])[32:36], "little")
    lower = copy.deepcopy(known)
    # (a read of desc carries the descriptor whole: its count is the fourth field)
    dread(lower)[2][3] = index                                      # N: the index
    _, _, unknown = first(directed44, valid_id(False))             # the count not known: no descriptor there
    said_known = copy.deepcopy(unknown)
    dread(said_known)[2] = copy.deepcopy(dread(known)[2])           # the read says it is known: a descriptor whose
    dread(said_known)[2][3] = int.from_bytes(bytes.fromhex(unknown["args"][0])[32:36], "little")   # count is the index
    odd = copy.deepcopy(unknown)
    odd["args"][0] = odd["args"][0] + "4"                           # an id of an odd number of hex digits
    def unheld_refused(d):              # an on_ihave whose refused bitmap has an index not in mine (mine is
        if not (d["fn"] == "on_ihave" and "raises" not in d and any(t[0] == "penalise" for t in d["tape"])):
            return False                #   the twin's own: said to hold, the bitmap is expanded, and its known_id read)
        _, g, b = next(t for t in d["tape"] if t[0] == "valid_have" and t[2] is False)[1][0]
        m = next((e[2] for e in d["reads"] + d["rest"] if e[:2] == ["mine", [g]]), None) or 0
        return b & ~m != 0
    _, _, pen = first(directed44, unheld_refused)
    no_pen = copy.deepcopy(pen)
    no_pen["tape"] = [t for t in no_pen["tape"] if t[0] != "penalise"]
    within = copy.deepcopy(pen)
    at = next(i for i, t in enumerate(within["tape"]) if t[0] == "valid_have" and t[2] is False)
    within["tape"][at][2] = True                                    # the bitmap said to be within a HAVE's limits
    # a question's argument changed, so that the replay's comparison of it is shown to act
    other_group = copy.deepcopy(known)
    g = dread(other_group)[1][0]
    dread(other_group)[1][0] = ("0" if g[0] != "0" else "1") + g[1:]              # desc's read, of another group
    other_bits = copy.deepcopy(pen)
    other_bits["tape"][at][1][0][2] += 8                                        # valid_have asked of another bitmap
    other_peer = copy.deepcopy(pen)
    pt = next(i for i, t in enumerate(other_peer["tape"]) if t[0] == "penalise")
    other_peer["tape"][pt][1][0] += 100                                         # penalise of another peer
    return check("v0.10's §4.4 on a tape", {
        "valid_id, the count known, as it is": (alone(hdr, consts, known), 0, None),
        "valid_id, the count read is the id's index": (alone(hdr, consts, lower), 1, "return value"),
        "valid_id, the count not known, as it is": (alone(hdr, consts, unknown), 0, None),
        "valid_id, the read says the count is known, and is the id's index": (alone(hdr, consts, said_known), 1, "return value"),
        "valid_id, an id of an odd number of hex digits": (alone(hdr, consts, odd), 1, "not an IHAVE's entry"),
        "on_ihave, a bitmap beyond a HAVE's limits, as it is": (alone(hdr, consts, pen), 0, None),
        "on_ihave, its penalty not on the tape": (alone(hdr, consts, no_pen), 1, "tape: penalise("),
        "on_ihave, valid_have said to hold": (alone(hdr, consts, within), 1, "tape: known_id["),
        # (written "reads" before it ran; it fails as it must, and the replay tells an earlier difference: finding no
        # descriptor of the id's own group, the twin does not enter N, which the record says was reached)
        "valid_id, its read of desc is of another group": (alone(hdr, consts, other_group), 1, "reached: the twin entered"),
        "on_ihave, valid_have asked of another bitmap": (alone(hdr, consts, other_bits), 1, "tape: valid_have("),
        "on_ihave, penalise of another peer": (alone(hdr, consts, other_peer), 1, "tape: penalise("),
    }, work, head, "v010")


def format5_controls(directed42, work, head):
    """The rules of a call's log, the queue's keys, the mesh question and the chunk argument, on §4.2's directed
    records. Two records pass as they are: one that reads an entry, has a callee write it, and reads it again
    (drop_beyond's offered, around drop_offer), and one that a callee writes and the block then reads (open_group's
    state). The rest must fail, each for the reason written beside it, which was written before the controls first
    ran."""
    def logged(t, name):                # a tape entry of the call `name`, with its log
        return t[0] == name and len(t) == 4

    # (drop_offer is the twin's own code, with no log. The pattern of a callee's write that the block then reads is
    # open_group's below; a callee's log's own rules are the queue's controls, on enqueue's.)
    hdr, consts, _ = first(directed42, lambda d: True)

    def wr(d):                          # on_validated: open_group writes state, the block reads it, and goes on
        return (d["fn"] == "on_validated" and "raises" not in d and any(t[0] == "store" for t in d["tape"])
                and "claim_group" not in d["reached"]
                and any(logged(t, "open_group") and any(e[0] == "state" for e in t[3]["cw"]) for t in d["tape"]))
    _, _, w = first(directed42, wr)
    og = next(k for k, t in enumerate(w["tape"]) if t[0] == "open_group")
    invalid = copy.deepcopy(w)
    invalid["tape"][og][3]["cw"] = [[e[0], e[1], "INVALID" if e[0] == "state" else e[2]] for e in invalid["tape"][og][3]["cw"]]

    # a call's log: its controls are the queue's, on enqueue's log (queue_controls)

    def two_keys(d):                    # drop_beyond: the queue's keys, two peers or more, each with a drop_offer
        return (d["fn"] == "drop_beyond" and "raises" not in d
                and any(t[:2] == ["keys", "queue"] and len(set(t[3])) >= 2 for t in d["tape"]))
    _, _, k2 = first(directed42, two_keys)
    kq = next(k for k, t in enumerate(k2["tape"]) if t[:2] == ["keys", "queue"] and len(set(t[3])) >= 2)
    keys_twice = copy.deepcopy(k2)
    keys_twice["tape"][kq][3] = keys_twice["tape"][kq][3] + keys_twice["tape"][kq][3][:1]
    keys_order = copy.deepcopy(k2)
    keys_order["tape"][kq][3] = keys_order["tape"][kq][3][::-1]
    keys_short = copy.deepcopy(k2)              # the order must be of the twin's own rows, all of them
    keys_short["tape"][kq][3] = keys_short["tape"][kq][3][1:]
    keys_stranger = copy.deepcopy(k2)           #   and of no other peer
    keys_stranger["tape"][kq][3] = keys_stranger["tape"][kq][3] + [max(keys_stranger["tape"][kq][3]) + 1000]

    def meshed(d):                      # a claim to a mesh of two peers or more
        return (d["fn"] in ("on_chunk", "on_validated") and "raises" not in d
                and any(t[0] == "mesh_and" and len(t[2]) >= 2 for t in d["tape"]))
    _, _, ms = first(directed42, meshed)
    mq = next(k for k, t in enumerate(ms["tape"]) if t[0] == "mesh_and")
    p = ms["tape"][mq][1][0]
    mesh_without = copy.deepcopy(ms)
    mesh_without["tape"][mq][2] = [q for q in mesh_without["tape"][mq][2] if q != p]
    mesh_twice = copy.deepcopy(ms)
    mesh_twice["tape"][mq][2] = mesh_twice["tape"][mq][2] + mesh_twice["tape"][mq][2][:1]
    mesh_order = copy.deepcopy(ms)
    mesh_order["tape"][mq][2] = mesh_order["tape"][mq][2][::-1]

    def fresh(d):                       # on_chunk of a chunk not seen: validated, accepted, a group opened and stored
        return (d["fn"] == "on_chunk" and "raises" not in d
                and any(t[0] == "validate_chunk" and t[2] == "ACCEPT" for t in d["tape"])
                and any(t[0] == "open_group" for t in d["tape"]) and any(t[0] == "store" for t in d["tape"]))
    _, _, fr = first(directed42, fresh)
    other_id = copy.deepcopy(fr)
    c = other_id["args"][1]
    ix = bytes.fromhex(c[4])
    c[4] = (ix[:32] + (c[1] + 1).to_bytes(4, "little") + ix[36:]).hex()          # the id of the next index
    og2 = next(k for k, t in enumerate(fr["tape"]) if t[0] == "open_group")
    other_group = copy.deepcopy(fr)
    g = other_group["tape"][og2][1][0]
    other_group["tape"][og2][1][0] = ("0" if g[0] != "0" else "1") + g[1:]
    st = next(k for k, t in enumerate(fr["tape"]) if t[0] == "store")
    other_index = copy.deepcopy(fr)
    other_index["tape"][st][1][1] += 1
    vc = next(k for k, t in enumerate(fr["tape"]) if t[0] == "validate_chunk")
    rejected = copy.deepcopy(fr)
    rejected["tape"][vc][2] = "REJECT"
    one = (hdr, consts)
    return check("a call's log, the queue's keys, mesh_and and the chunk on a tape", {
        "on_validated: open_group writes state, the block reads it, as it is": (alone(*one, w), 0, None),
        "on_validated: open_group's cw says INVALID": (alone(*one, invalid), 1, "tape: the toy asked more"),
        "the queue's keys with a peer twice": (alone(*one, keys_twice), 1, "keys of queue: a key twice"),
        # this one PASSES, and says what no record shows: drop_offer is the twin's own code, and its calls for two
        # peers commute (each touches its own peer's entries), so the order of list(queue) is asked and, in
        # drop_beyond, decides nothing
        "the queue's keys in another order: it passes since drop_offer is the twin's own": (alone(*one, keys_order), 0, None),
        "the queue's keys without one of the twin's rows": (alone(*one, keys_short), 1,
                                                            "tape: list(queue): the node's order"),
        "the queue's keys with a peer that has no row": (alone(*one, keys_stranger), 1,
                                                         "tape: list(queue): the node's order"),
        "mesh_and without its peer": (alone(*one, mesh_without), 1, "mesh_and's answer does not have its peer"),
        "mesh_and with a peer twice": (alone(*one, mesh_twice), 1, "mesh_and: a key twice"),
        "mesh_and in another order": (alone(*one, mesh_order), 1, "tape: enqueue("),
        "on_chunk: the chunk's id of another index": (alone(*one, other_id), 1, "a chunk's id is not of its group and index"),
        "on_chunk: open_group asked of another group": (alone(*one, other_group), 1, "tape: open_group("),
        "on_chunk: store asked of another index": (alone(*one, other_index), 1, "tape: store("),
        "on_chunk: validate_chunk said REJECT": (alone(*one, rejected), 1, "tape: penalise("),
    }, work, head, "format5")


def deferral_controls(directed4b, directed42, work, head):
    """The orders of the twin's own levels the Python iterates, each a permutation of the twin's rows, and the
    question installed_block, on directed4b's records (and on directed42's for drop_beyond's roots). Each altered
    record must fail, for the reason written beside it, which was written before the controls first ran."""
    def keys_at(d, table, depth, n):    # the first keys item of `table` at `depth`, with n keys or more
        return next((k for k, t in enumerate(d.get("tape", [])) if t[0] == "keys" and t[1] == table
                     and len(t[2]) == depth and len(t[3]) >= n), None)

    def picks(fn, table, depth, n):
        return lambda d: d["fn"] == fn and "raises" not in d and keys_at(d, table, depth, n) is not None

    hdr, consts, pw = first(directed4b, picks("drop_stale_waits", "pending", 0, 2))
    kp = keys_at(pw, "pending", 0, 2)
    pending_twice = copy.deepcopy(pw)
    pending_twice["tape"][kp][3] = pending_twice["tape"][kp][3] + pending_twice["tape"][kp][3][:1]
    pending_short = copy.deepcopy(pw)
    pending_short["tape"][kp][3] = pending_short["tape"][kp][3][1:]
    _, _, ts = first(directed4b, picks("drop_stale_waits", "tie_slot", 0, 1))
    kt = keys_at(ts, "tie_slot", 0, 1)
    slot_stranger = copy.deepcopy(ts)
    ks = slot_stranger["tape"][kt][3]
    slot_stranger["tape"][kt][3] = ks + [[ks[0][0], max(k[1] for k in ks) + 1000]]
    h42, c42, rb = first(directed42, picks("drop_beyond", "tied", 0, 2))
    kr = keys_at(rb, "tied", 0, 2)
    roots_order = copy.deepcopy(rb)
    roots_order["tape"][kr][3] = roots_order["tape"][kr][3][::-1]

    def nested(d):                      # on_block_installed's pop: a root's peers, two or more, and a peer's groups
        return (d["fn"] == "on_block_installed" and "raises" not in d and keys_at(d, "tied", 1, 2) is not None
                and keys_at(d, "tied", 2, 1) is not None)
    _, _, ob = first(directed4b, nested)
    k1, k2 = keys_at(ob, "tied", 1, 2), keys_at(ob, "tied", 2, 1)
    peers_twice = copy.deepcopy(ob)
    peers_twice["tape"][k1][3] = peers_twice["tape"][k1][3] + peers_twice["tape"][k1][3][:1]
    groups_stranger = copy.deepcopy(ob)
    groups_stranger["tape"][k2][3] = groups_stranger["tape"][k2][3] + ["ee" * 32]

    def not_installed(d):               # defer alone: no block yet, and admitted asked next
        return (d["fn"] == "defer" and "raises" not in d
                and any(t[0] == "installed_block" and t[2] is None for t in d["tape"])     # (the answer is the
                #                                             block as level 1 reads it, or nothing)
                and any(t[0] == "admitted" for t in d["tape"]))
    _, _, nd = first(directed4b, not_installed)
    ib = next(k for k, t in enumerate(nd["tape"]) if t[0] == "installed_block")
    installed_said = copy.deepcopy(nd)
    installed_said["tape"][ib][2] = [nd["tape"][ib][1][0], None, None]      # a block of the slot asked, with no bid

    # (a call's log: drop_offer is the twin's own code. A log's write dropped or changed, its cr changed, and a log
    # without cw are the queue's controls, on enqueue's log.)
    one = (hdr, consts)
    return check("§4.2's deferred chunks on a tape", {
        "drop_stale_waits: list(pending) with a root twice": (alone(*one, pending_twice), 1,
                                                              "keys of pending: a key twice"),
        "drop_stale_waits: list(pending) without one of the twin's roots": (alone(*one, pending_short), 1,
                                                                            "tape: list(pending): the node's order"),
        "drop_stale_waits: list(tie_slot.items()) with a pair the twin has not": (
            alone(*one, slot_stranger), 1, "tape: list(tie_slot.items()): the node's order"),
        "drop_beyond: list(tied.items())'s roots in another order": (alone(h42, c42, roots_order), 1, "tape: tied["),
        "on_block_installed: a root's peers with a peer twice": (alone(*one, peers_twice), 1,
                                                                 "keys of a root of tied: a key twice"),
        "on_block_installed: a peer's groups with a group the twin has not": (alone(*one, groups_stranger), 1,
                                                                              "'s groups: the node's order"),
        "defer: installed_block said a block is there, where it said none": (alone(*one, installed_said), 1,
                                                                            "tape: validate_chunk("),
    }, work, head, "deferral")


def writer_controls(directed7, work, head):
    """next_to_send's return value, and the order of owed's groups, on directed7's records. Each altered record must
    fail, for the reason written beside it, which was written before the controls first ran."""
    def waits(d):                       # next_to_send in line for a slot
        return d["fn"] == "next_to_send" and "raises" not in d and d.get("ret") == "WAIT"
    hdr, consts, w = first(directed7, waits)
    said_nothing = copy.deepcopy(w)
    said_nothing["ret"] = None

    def owes_two(d):                    # owed groups, two or more, iterated
        return (d["fn"] in ("next_to_send", "with_owed") and "raises" not in d
                and any(t[0] == "keys" and t[1] == "owed" and len(t[3]) >= 2 for t in d["tape"]))
    _, _, o = first(directed7, owes_two)
    ko = next(k for k, t in enumerate(o["tape"]) if t[0] == "keys" and t[1] == "owed" and len(t[3]) >= 2)
    owed_twice = copy.deepcopy(o)
    owed_twice["tape"][ko][3] = owed_twice["tape"][ko][3] + owed_twice["tape"][ko][3][:1]
    owed_stranger = copy.deepcopy(o)
    owed_stranger["tape"][ko][3] = owed_stranger["tape"][ko][3] + ["ee" * 32]
    one = (hdr, consts)
    return check("§7.2's writer on a tape", {
        "next_to_send: in line, as it is": (alone(*one, w), 0, None),
        "next_to_send: in line, written as nothing to send": (alone(*one, said_nothing), 1, "return value"),
        "with_owed: owed's groups with one twice": (alone(*one, owed_twice), 1, "keys of a row of owed: a key twice"),
        "with_owed: owed's groups with one the twin has not": (alone(*one, owed_stranger), 1,
                                                               "'s groups: the node's order"),
    }, work, head, "writer")


def nodes_controls(directed7, work, head):
    """A record is replayed with its own node's constants. On directed7's first filter_entry record that cancels its
    chunk (CANCEL on, the peer has claimed the chunk: the first thing its tape has is that read of peer_has). Each
    outcome was written before the controls first ran."""
    def cancels(d):
        if d["fn"] != "filter_entry" or "raises" in d or d["args"][1][0] is None or not d["tape"]:
            return False
        (g, i), p = d["args"][1][0][:2], d["args"][0]       # (that read is among the record's reads, not on its
        return any(e[0] == "peer_has" and e[1] == [p, g] and e[2] and e[2][0] >> i & 1 == 1 for e in d["reads"])   # tape)
    hdr, nodes, rec = first(directed7, cancels)
    (own,) = [e for e in nodes["nodes"] if rec["n"] in e["n"]]
    assert own["consts"]["CANCEL"] is True, "directed7 is not the set with the cards on"
    off = {**own, "consts": {**own["consts"], "CANCEL": False}}
    other = max(n for e in nodes["nodes"] for n in e["n"]) + 1          # a node the trace has no record of

    def line(*entries):
        return {"nodes": [copy.deepcopy(e) for e in entries]}
    return check("the nodes line", {
        "filter_entry: a chunk cancelled, as it is": (alone(hdr, nodes, rec), 0, None),
        # (the peer's claim is the twin's state: the entry returned, not cancelled, tells)
        "its node's constants with CANCEL off": (alone(hdr, line({**off, "n": [rec["n"]]}), rec), 1, "return value"),
        "another node's entry with CANCEL off, its own as it is": (
            alone(hdr, line({**own, "n": [rec["n"]]}, {**off, "n": [other]}), rec), 0, None),
        "the two entries' nodes exchanged": (
            alone(hdr, line({**own, "n": [other]}, {**off, "n": [rec["n"]]}), rec), 1, "return value"),
    }, work, head, "nodes")


def drop_offer_controls(directed6o, work, head):
    """drop_offer (the twin's own code; it asks nothing, so a record of it is its state before and after), on
    directed6o's records. Each outcome was written before the controls first ran."""
    def lane_write(d, lane):
        return next((e for e in d["writes"] if e[0] == "queue" and e[1][1:] == [lane]), None)

    def filtered(d):                    # p's normal lane written shorter than it was read: an entry emptied and gone
        if "raises" in d:
            return False
        w = lane_write(d, "normal")
        r = next((e for e in d["reads"] if e[0] == "queue" and e[1][1:] == ["normal"]), None)
        return w is not None and r is not None and r[2] and w[2] is not None and len(w[2]) < len(r[2])
    hdr, nodes, rec = first(directed6o, filtered)
    kept = copy.deepcopy(rec)                                   # the lane as it was read: nothing filtered
    lane_write(kept, "normal")[2] = next(e for e in rec["reads"] if e[0] == "queue" and e[1][1:] == ["normal"])[2]

    def no_queue(d):                    # no queue of p's: the lane written, and left missing
        w = lane_write(d, "normal")
        return "raises" not in d and w is not None and w[2] is None
    _, _, none = first(directed6o, no_queue)
    made = copy.deepcopy(none)
    lane_write(made, "normal")[2] = []                          # the lane there and empty: a row made

    def promise_closed(d):
        return "raises" not in d and any(e[0] == "promises" and e[2] is None for e in d["writes"])
    _, _, pc = first(directed6o, promise_closed)
    open_ = copy.deepcopy(pc)
    open_["writes"] = [e for e in open_["writes"] if not (e[0] == "promises" and e[2] is None)]
    retable(open_)

    def list_gone(d):
        return "raises" not in d and any(e[0] == "offers" and e[2] is None for e in d["writes"])
    _, _, lg = first(directed6o, list_gone)
    stays = copy.deepcopy(lg)
    w = next(e for e in stays["writes"] if e[0] == "offers" and e[2] is None)
    w[2] = [stays["args"][2]]                                   # the list left with p alone in it
    one = (hdr, nodes)
    return check("§6.1's drop_offer", {
        "an ask of the chunk filtered out of p's normal lane, as it is": (alone(*one, rec), 0, None),
        "the lane written as it was read": (alone(*one, kept), 1, "post"),
        "no queue of p's, as it is": (alone(*one, none), 0, None),
        "no queue of p's: the lane written there and empty": (alone(*one, made), 1, "post"),
        "a promise of p's closed, as it is": (alone(*one, pc), 0, None),
        "that promise not closed": (alone(*one, open_), 1, "post"),
        "an offer list of p alone gone, as it is": (alone(*one, lg), 0, None),
        "that list left with p in it": (alone(*one, stays), 1, "post"),
    }, work, head, "dropoffer")


def pace_controls(directed64, work, head):
    """§6.4's on_pace_tick and send_gossip (the pace queue the twin's own table of one entry), on directed64's
    records. Each outcome was written before the controls first ran."""
    def fl(b):
        return struct.unpack("<d", struct.pack("<Q", b))[0]

    def jobs(d):                        # the queue as the call read it
        return next((e[2] for e in d["reads"] if e[0] == "pace_queue"), None) or []

    def names(d):
        return [t[0] for t in d["tape"]]

    def dropped_then_sent(d):           # a stale job dropped, then another peer's sent: connected asked once
        js = jobs(d)
        return (d["fn"] == "on_pace_tick" and "raises" not in d and len(js) >= 2 and names(d)[:2] == ["connected", "group_bits"]
                and d["tape"][0][2] is True and d["tape"][0][1] == [js[1][0]] and js[0][0] != js[1][0]
                and len(d["tape"][1][2]) >= 1)
    hdr, nodes, rec = first(directed64, dropped_then_sent)
    (own,) = [e for e in nodes["nodes"] if rec["n"] in e["n"]]
    HB = fl(own["consts"]["HEARTBEAT"])
    assert fl(rec["t"]) - fl(jobs(rec)[0][2]) >= HB, "the record's first job is not stale"
    fresh = copy.deepcopy(rec)                                  # the first job queued now: not stale
    jobs(fresh)[0][2] = rec["t"]
    long_hb = {"nodes": [{**copy.deepcopy(own), "n": [rec["n"]],
                          "consts": {**own["consts"], "HEARTBEAT": struct.unpack("<Q", struct.pack("<d", 100.0))[0]}}]}
    left = copy.deepcopy(rec)                                   # the peer said to have left: its job dropped too
    left["tape"][0][2] = False
    twice = copy.deepcopy(rec)                                  # group_bits answers with a group twice
    twice["tape"][1][2] = twice["tape"][1][2] + twice["tape"][1][2][:1]
    other_bits = copy.deepcopy(rec)                             # and with another index of its first group
    other_bits["tape"][1][2][0][1] ^= 1 << 7
    no_group = copy.deepcopy(rec)                               # and with a group of no index
    no_group["tape"][1][2][0][1] = 0

    def leaves_jobs(d):                 # the queue written with jobs left in it
        w = next((e for e in d["writes"] if e[0] == "pace_queue"), None)
        return d["fn"] == "on_pace_tick" and "raises" not in d and w is not None and w[2] and len(w[2]) >= 1
    _, nodes2, lj = first(directed64, leaves_jobs)
    assert nodes2 == nodes
    one_more = copy.deepcopy(lj)                                # written with one more job popped
    w = next(e for e in one_more["writes"] if e[0] == "pace_queue")
    w[2] = w[2][1:] or None
    not_popped = copy.deepcopy(lj)                              # written as it was read
    next(e for e in not_popped["writes"] if e[0] == "pace_queue")[2] = copy.deepcopy(jobs(lj))

    # (announce is the twin's own: the tape has announce's enqueue of the offer, with its log, and the three controls
    # are on it. An enqueue has an answer, so the third turns it.)
    def announces(d):                   # send_gossip whose first announce enqueued an offer: its log
        return (d["fn"] == "send_gossip" and "raises" not in d and len(d["tape"]) >= 2 and d["tape"][1][0] == "enqueue"
                and d["tape"][1][2] is True and len(d["tape"][1]) == 4)
    _, _, sg = first(directed64, announces)
    other_peer = copy.deepcopy(sg)                              # the offer enqueued to another peer
    other_peer["tape"][1][1][0] += 1
    no_log = copy.deepcopy(sg)                                  # the enqueue without its log: nothing enqueued
    del no_log["tape"][1][3]
    answered = copy.deepcopy(sg)                                # the queue said to refuse the offer: owed, then
    answered["tape"][1][2] = False

    def empty_tick(d):
        return d["fn"] == "on_pace_tick" and "raises" not in d and not d["tape"] and not jobs(d) and d["reads"]
    _, _, et = first(directed64, empty_tick)
    a_job = copy.deepcopy(et)                                   # the empty queue read as one fresh job
    next(e for e in a_job["reads"] if e[0] == "pace_queue")[2] = [[1, [], et["t"]]]
    empty_list = copy.deepcopy(et)                              # and as `[]`, which a record does not write
    next(e for e in empty_list["reads"] if e[0] == "pace_queue")[2] = []
    one = (hdr, nodes)
    return check("§6.4's paced gossip", {
        "a stale job dropped and the next one's gossip sent, as it is": (alone(*one, rec), 0, None),
        "the first job's time written as now": (alone(*one, fresh), 1, "tape"),
        "its node's HEARTBEAT written as 100 s": (alone(hdr, long_hb, rec), 1, "tape"),
        "the next job's peer said to have left": (alone(*one, left), 1, "tape"),
        "group_bits' answer with a group twice": (alone(*one, twice), 1, "group_bits: a key twice"),
        "group_bits' answer with another index": (alone(*one, other_bits), 1, "tape"),
        "group_bits' answer with a group of no index": (alone(*one, no_group), 1, "a group with no index"),
        "a tick that leaves jobs, as it is": (alone(*one, lj), 0, None),
        "the queue written with one more job popped": (alone(*one, one_more), 1, "post"),
        "the queue written as it was read": (alone(*one, not_popped), 1, "post"),
        "send_gossip with an offer enqueued, as it is": (alone(*one, sg), 0, None),
        "its offer enqueued to another peer": (alone(*one, other_peer), 1, "tape"),
        "its enqueue without its log": (alone(*one, no_log), 1, "post"),
        "the queue said to refuse its offer": (alone(*one, answered), 1, "tape"),
        "a tick on an empty queue, as it is": (alone(*one, et), 0, None),
        "the empty queue read as one job": (alone(*one, a_job), 1, "tape"),
        "the empty queue read as an empty list": (alone(*one, empty_list), 1, "an empty pace queue as a value"),
    }, work, head, "pace")


def heartbeat_controls(directed64h, work, head):
    """§6.4's on_heartbeat, on directed64h's records. Each outcome was written before the controls first ran."""
    def fb(x):
        return struct.unpack("<Q", struct.pack("<d", x))[0]

    def at(d, name, k=0):               # the place on the tape of the k-th entry of that name
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def held_keys(d):
        return next((t for t in d["tape"] if t[0] == "keys" and t[1] == "held_back"), None)

    def sample(d):
        return d["tape"][at(d, "sample_without_replacement")]

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def with_consts(nodes, d, **change):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **change}}]}

    # ---- the retries' order: two asks held back, of two groups. A retry of a chunk held meanwhile asks nothing
    #      and writes nothing, so two such retries commute, and their order on the tape is free (`quiet`: the
    #      first run of these controls had this record under "must fail", and it passed: the record's choice was
    #      wrong, not the twin). Where each retry asks whether its group expired, the order shows (`asking`; a
    #      retry's read of stop_pull, the twin's own table, is not on the tape).
    def stops(d):                       # the groups the retries ask `expired` of, in order: the tape between the
        i = d["tape"].index(held_keys(d))       # held-back keys and drop_stale_waits' first entry, pending's keys
        j = next(k for k, t in enumerate(d["tape"]) if k > i and t[0] == "keys" and t[1] == "pending")
        return [t[1][0] for t in d["tape"][i + 1:j] if t[0] == "expired"], j - i - 1

    def two_held(d, asking=True):
        k = held_keys(d)
        if "raises" in d or k is None or len(k[3]) != 2 or k[3][0][0] == k[3][1][0]:
            return False
        asked, between = stops(d)
        return (asked == [k[3][0][0], k[3][1][0]]) if asking else between == 0
    hdr, nodes, th = first(directed64h, two_held)
    swapped = copy.deepcopy(th)
    held_keys(swapped)[3].reverse()
    _, _, quiet = first(directed64h, lambda d: two_held(d, asking=False))
    quiet_swapped = copy.deepcopy(quiet)
    held_keys(quiet_swapped)[3].reverse()
    short = copy.deepcopy(th)
    held_keys(short)[3].pop()
    kept = copy.deepcopy(th)                                    # one held-back ask written as still there
    w = next(e for e in kept["writes"] if e[0] == "held_back")
    w[2] = next(e[2] for e in kept["reads"] if e[0] == "held_back" and e[1] == w[1])

    # ---- the gossip, paced: some of the eligible peers sampled, ids there
    def paced_some(d, paced=True):
        if "raises" in d or not any(t[0] == "sample_without_replacement" for t in d["tape"]):
            return False
        sm = sample(d)
        ids = d["tape"][at(d, "gossip_ids")][2]
        return (1 <= sm[1][1] < len(sm[1][0]) and ids
                and any(e[0] == "pace_queue" for e in d["writes"]) == paced
                and d["tape"][at(d, "topic_peers")][2][0] in sm[1][0])   # the first topic peer is eligible
    _, nodes2, ps = first(directed64h, paced_some)
    assert nodes2 == nodes and node_of(nodes, ps)["consts"]["PACED"] is True
    fewer_ids = copy.deepcopy(ps)
    fewer_ids["tape"][at(ps, "gossip_ids")][2].pop()
    topic_rev = copy.deepcopy(ps)
    topic_rev["tape"][at(ps, "topic_peers")][2].reverse()
    assert topic_rev["tape"][at(ps, "topic_peers")][2][0] != ps["tape"][at(ps, "topic_peers")][2][0]
    in_mesh = copy.deepcopy(ps)                                 # the first topic peer said to be in the mesh
    in_mesh["tape"][at(ps, "mesh_has")][2] = True
    assert ps["tape"][at(ps, "mesh_has")][2] is False
    not_elig = copy.deepcopy(ps)                                # and said not to be eligible
    not_elig["tape"][at(ps, "gossip_eligible")][2] = False
    assert ps["tape"][at(ps, "gossip_eligible")][2] is True
    sm = sample(ps)
    twice, stranger, one_short, another = (copy.deepcopy(ps) for _ in range(4))
    sample(twice)[2] = sm[2][:-1] + sm[2][:1] if len(sm[2]) > 1 else sm[2] + sm[2]
    sample(stranger)[2] = sm[2][:-1] + [max(sm[1][0]) + 1]
    sample(one_short)[2] = sm[2][:-1]
    sample(another)[2] = sm[2][:-1] + [next(q for q in sm[1][0] if q not in sm[2])]     # another draw: another job
    ulp = copy.deepcopy(ps)                                     # the last job's time one ulp later
    next(e for e in ulp["writes"] if e[0] == "pace_queue")[2][-1][2] += 1
    counts_kept = None

    def clears(d):                      # a count of §4.4's limits there, and cleared
        return "raises" not in d and any(e[0] == "ihave_frames" and e[2] is None for e in d["writes"])
    _, _, cl = first(directed64h, clears)
    counts_kept = copy.deepcopy(cl)
    counts_kept["writes"] = [e for e in counts_kept["writes"] if e[0] != "ihave_frames"]
    retable(counts_kept)

    # ---- not paced: send_gossip at once
    _, _, un = first(directed64h, lambda d: paced_some(d, paced=False) and any(t[0] == "group_bits" for t in d["tape"]))
    assert node_of(nodes, un)["consts"]["PACED"] is False
    return check("§6.4's heartbeat", {
        "two asks held back, each retry asking, as it is": (alone(hdr, nodes, th), 0, None),
        "their order on the tape reversed": (alone(hdr, nodes, swapped), 1, "tape"),
        "two asks held back of chunks held meanwhile, their order reversed": (alone(hdr, nodes, quiet_swapped), 0, None),
        "their order with one left out": (alone(hdr, nodes, short), 1, "the node's order"),
        "one of them written as still held back": (alone(hdr, nodes, kept), 1, "post"),
        "paced gossip to some of the eligible peers, as it is": (alone(hdr, nodes, ps), 0, None),
        "gossip_ids' answer one id shorter": (alone(hdr, nodes, fewer_ids), 1, "post"),
        "topic_peers' answer reversed": (alone(hdr, nodes, topic_rev), 1, "tape"),
        "the first topic peer said to be in the mesh": (alone(hdr, nodes, in_mesh), 1, "tape"),
        "the first topic peer said not to be eligible": (alone(hdr, nodes, not_elig), 1, "tape"),
        "the draw's answer with a peer twice": (alone(hdr, nodes, twice), 1, "sample_without_replacement: a key twice"),
        "the draw's answer with a peer not of the question's": (alone(hdr, nodes, stranger), 1,
                                                                "a peer that is not of the question's"),
        "the draw's answer one peer short": (alone(hdr, nodes, one_short), 1, "peers: ["),
        "the draw's answer with another of the eligible peers": (alone(hdr, nodes, another), 1, "post"),
        "the last job's time one ulp later": (alone(hdr, nodes, ulp), 1, "post"),
        "its node's D_LAZY written as 1000": (alone(hdr, with_consts(nodes, ps, D_LAZY=1000), ps), 1, "tape"),
        "its node's GOSSIP_FACTOR written as 1.0": (alone(hdr, with_consts(nodes, ps, GOSSIP_FACTOR=fb(1.0)), ps), 1,
                                                    "tape"),
        "its node's PACED written as off": (alone(hdr, with_consts(nodes, ps, PACED=False), ps), 1, "tape"),
        "a count of the limits cleared, as it is": (alone(hdr, nodes, cl), 0, None),
        "that count's clearing left out of the writes": (alone(hdr, nodes, counts_kept), 1, "post"),
        "gossip sent at once, as it is": (alone(hdr, nodes, un), 0, None),
        "its node's PACED written as on": (alone(hdr, with_consts(nodes, un, PACED=True), un), 1, "tape"),
    }, work, head, "heartbeat")


def claim_controls(directed46, directed44, work, head):
    """§4.6's claim_group and drop_group (the twin's own code; `stop_pull` the twin's own table), on directed46's
    records and one of directed44's. Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def write_of(d, table):
        return next(e for e in d["writes"] if e[0] == table)

    # Two outcomes were stated wrong at these controls' first run, in their reason and not in their code (each
    # failed, as stated): stop_pull's write left out of a record whose group was stopped already leaves the whole
    # state as it is, and the notes tell it (the twin writes an entry the Python did not), so the two cases are
    # apart now; and a descriptor with another count shows first in the HAVE the claim sends, on the tape.
    def claims(d, stopped=False):       # a claim to two mesh peers or more, a HAVE enqueued for the first two
        if d["fn"] != "claim_group" or "raises" in d:
            return False
        m = d["tape"][at(d, "mesh")][2]
        enq = [t[1][0] for t in d["tape"] if t[0] == "enqueue"]
        have = [t[1][1][0][1][0][2] for t in d["tape"] if t[0] == "enqueue"]   # the bits of each HAVE sent
        # (stopped: the claimed group's own entry was there before the call. The HAVE sent is of `mine` as the
        # claim writes it, not of `origin` (have_bits, §4.2): the control of the descriptor's count stands on that)
        return (len(m) >= 2 and enq[:2] == m[:2] and any(e[0] == "stop_pull" for e in d["writes"])
                and have[:1] == [write_of(d, "mine")[2]]
                and any(e[0] == "stop_pull" and e[1] == [d["args"][0]] for e in d["rest"]) == stopped
                and any(t[0] == "close_promises_of_group" and len(t) == 4 for t in d["tape"])
                and (write_of(d, "mine")[2] or 0) >= 15)
    hdr, nodes, cl = first(directed46, claims)
    _, _, again = first(directed46, lambda d: claims(d, stopped=True))     # a claim of a group stopped already
    again_unwritten = copy.deepcopy(again)
    again_unwritten["writes"] = [e for e in again_unwritten["writes"] if e[0] != "stop_pull"]
    retable(again_unwritten)
    rev, twice, not_stopped, short, open_, fewer = (copy.deepcopy(cl) for _ in range(6))
    rev["tape"][at(cl, "mesh")][2].reverse()
    twice["tape"][at(cl, "mesh")][2].append(cl["tape"][at(cl, "mesh")][2][0])
    not_stopped["writes"] = [e for e in not_stopped["writes"] if e[0] != "stop_pull"]
    retable(not_stopped)
    write_of(short, "mine")[2] >>= 1                            # the claim of all bits, written one bit short
    del open_["tape"][at(cl, "close_promises_of_group")][3]     # the node's helper, without what it closed
    next(e for e in fewer["reads"] if e[0] == "desc")[2][3] -= 1    # the descriptor's count one less: another N
    #                                     (`desc` the twin's own: its read is the record's, not the tape's)

    def changed(log, table):            # a call's writes of `table` that are not what it read there
        return [e for e in log["cw"] if e[0] == table
                and e[2] != next((r[2] for r in log["cr"] if r[:2] == e[:2]), None)]

    def drops(d):                       # a drop that changes a lane and the paced jobs, with a state written
        # (in v0.10.4, discard_queued sets both lanes of every queue, changed or not, and discard_paced rebuilds
        # the jobs in place: the controls stand on a write that changes something)
        return (d["fn"] == "drop_group" and "raises" not in d and len(d["tape"][at(d, "discard_queued")]) == 4
                and changed(d["tape"][at(d, "discard_queued")][3], "queue")
                and len(d["tape"][at(d, "discard_paced")]) == 4
                and changed(d["tape"][at(d, "discard_paced")][3], "pace_queue")
                and any(e[0] == "state" for e in d["writes"]))
    _, _, dg = first(directed46, drops)
    complete, kept, other, no_paced, answered, paced_kept = (copy.deepcopy(dg) for _ in range(6))
    write_of(complete, "state")[2] = "COMPLETE"
    log = kept["tape"][at(dg, "discard_queued")][3]             # a lane it changed, written as the callee read it
    lane = changed(log, "queue")[0]
    lane[2] = next(e[2] for e in log["cr"] if e[:2] == lane[:2])
    plog = paced_kept["tape"][at(dg, "discard_paced")][3]       # the paced jobs written as the callee read them
    jobs = changed(plog, "pace_queue")[0]
    jobs[2] = next(e[2] for e in plog["cr"] if e[:2] == jobs[:2])
    g = dg["args"][0]
    other["tape"][at(dg, "gossip_remove_group")][1][0] = ("22" if g[:2] != "22" else "33") * 32
    del no_paced["tape"][at(dg, "discard_paced")]
    answered["tape"][at(dg, "discard_paced")][2] = True

    def gated_stopped(d):               # directed44's gated of a group stopped: read from the twin's state now
        return (d["fn"] == "gated" and "raises" not in d and d["ret"] is True
                and any(e[0] == "stop_pull" and e[2] is True for e in d["reads"]))
    hdr44, nodes44, gs = first(directed44, gated_stopped)
    assert not gs["tape"], "gated's record has something on its tape"
    not_set = copy.deepcopy(gs)
    next(e for e in not_set["reads"] if e[0] == "stop_pull")[2] = None
    on_tape = copy.deepcopy(gs)                                 # the read on the tape
    on_tape["reads"] = [e for e in on_tape["reads"] if e[0] != "stop_pull"]
    on_tape["tape"] = [["read", "stop_pull", [gs["args"][0][0] if isinstance(gs["args"][0], list) else gs["args"][0][:64]], True]]
    retable(on_tape)
    one = (hdr, nodes)
    return check("§4.6's claim and drop", {
        "a claim to the mesh, as it is": (alone(*one, cl), 0, None),
        "the mesh's order reversed": (alone(*one, rev), 1, "tape"),
        "the mesh's answer with a peer twice": (alone(*one, twice), 1, "mesh: a key twice"),
        "stop_pull's write left out": (alone(*one, not_stopped), 1, "post"),
        "a claim of a group stopped already, as it is": (alone(*one, again), 0, None),
        "its write of stop_pull left out": (alone(*one, again_unwritten), 1,
                                            "the twin writes an entry the Python neither read nor wrote"),
        "mine written one bit short of all": (alone(*one, short), 1, "post"),
        "close_promises_of_group without its log": (alone(*one, open_), 1, "post"),
        "the descriptor read with a count one less": (alone(*one, fewer), 1, "tape"),
        "a group dropped, as it is": (alone(*one, dg), 0, None),
        "its state written COMPLETE": (alone(*one, complete), 1, "post"),
        "discard_queued's lane written as it was read": (alone(*one, kept), 1, "post"),
        "the gossip history told to remove another group": (alone(*one, other), 1, "tape"),
        "discard_paced not on the tape": (alone(*one, no_paced), 1, "tape"),
        "discard_paced written with an answer": (alone(*one, answered), 1, "a call that returns nothing"),
        "discard_paced's jobs written as they were read": (alone(*one, paced_kept), 1, "post"),
        "gated of a stopped group, as it is": (alone(hdr44, nodes44, gs), 0, None),
        "that group's stop_pull read as not set": (alone(hdr44, nodes44, not_set), 1, "return value"),
        "that read written on the tape instead": (alone(hdr44, nodes44, on_tape), 1, "stop_pull"),
    }, work, head, "claim")


def have_controls(directed43, work, head):
    """§4.3's on_have (`peer_has` and `holders` the twin's own tables), on directed43's records. Each outcome was
    written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def entry(d, table, where="writes"):
        return next((e for e in d[where] if e[0] == table), None)

    def new_bits(d):                    # the indices the HAVE newly brings, by window_release's reads of `sent`
        # (§7.1 is the twin's own: each new index is a read of the send's entry, [peer, group, index])
        return [e[1][0][2] for e in d["reads"] if e[0] == "sent"]

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    # ---- a HAVE with two new indices or more, to an entry there, of a group not planned
    def brings(d):
        r = entry(d, "peer_has", "reads")
        return ("raises" not in d and len(new_bits(d)) >= 2 and "origin_acked" not in d["reached"]
                and r is not None and r[2] is not None and entry(d, "peer_has") is not None)
    hdr, nodes, hv = first(directed43, brings)
    i0 = new_bits(hv)[0]
    had, ttl_less, bits_less, no_holder, other_index, planned, gone, invalid = (copy.deepcopy(hv) for _ in range(8))
    entry(had, "peer_has", "reads")[2][0] |= 1 << i0           # the entry read with the first new bit there already
    entry(ttl_less, "peer_has")[2][1] -= 1
    entry(bits_less, "peer_has")[2][0] ^= 1 << i0
    hw = next(e for e in no_holder["writes"] if e[0] == "holders" and e[1][1] == i0)
    hw[2] = [q for q in hw[2] if q != hv["args"][0]] or None
    next(e for e in other_index["reads"] if e[0] == "sent")[1][0][2] += 64     # the send's entry of another index
    # (`planned` is the twin's own: `g in planned` is a read of the group's row, an entry of the record's reads. In
    # the two controls the twin then asks, or does not ask, origin_acked, and the tape differs)
    def prow(d):                        # the record's read of its group's row of `planned`
        return next(e for e in d["reads"] if e[0] == "planned" and len(e[1]) == 1)
    assert prow(hv)[2] is None
    prow(planned)[2] = True
    gone["tape"][at(hv, "expired")][2] = True
    invalid["tape"][at(hv, "valid_have")][2] = False
    own = node_of(nodes, hv)
    long_ttl = {"nodes": [{**copy.deepcopy(own), "n": [hv["n"]], "consts": {**own["consts"], "HAVE_TTL": 7}}]}

    # ---- an invalid HAVE; an empty one to a peer with no entry; nothing new, the ttl run down; a planned group
    _, _, bad = first(directed43, lambda d: "raises" not in d and names(d)[-1:] == ["penalise"])
    unpunished = copy.deepcopy(bad)
    del unpunished["tape"][-1]

    def makes(d):
        w = entry(d, "peer_has")
        return ("raises" not in d and d["args"][2] == 0 and w is not None and w[2] is not None and w[2][0] == 0
                and entry(d, "peer_has", "reads")[2] is None)
    _, _, em = first(directed43, makes)
    unmade = copy.deepcopy(em)
    unmade["writes"] = [e for e in unmade["writes"] if e[0] != "peer_has"]
    retable(unmade)

    def refreshes(d):
        r, w = entry(d, "peer_has", "reads"), entry(d, "peer_has")
        return ("raises" not in d and not new_bits(d) and r is not None and r[2] is not None and w is not None
                and w[2][0] == r[2][0] and w[2][1] != r[2][1])
    _, _, rf = first(directed43, refreshes)
    stale = copy.deepcopy(rf)
    stale["writes"] = [e for e in stale["writes"] if e[0] != "peer_has"]
    retable(stale)

    # (origin_acked is the twin's own, and its work is the record's own: `origin` among the writes, the mesh's
    # questions and the enqueues on the tape)
    def acks(d):                        # a HAVE that acknowledges two chunks or more of a group the node publishes
        w = entry(d, "origin")
        r = entry(d, "origin", "reads")
        return ("raises" not in d and "origin_acked" in d["reached"] and w is not None and "mesh" in names(d)
                and r is not None and bin((w[2] or 0) & ~(r[2] or 0)).count("1") >= 2)
    _, _, ak = first(directed43, acks)
    unacked, one_less, not_planned = (copy.deepcopy(ak) for _ in range(3))
    unacked["writes"] = [e for e in unacked["writes"] if e[0] != "origin"]
    retable(unacked)
    grown = (entry(ak, "origin")[2] or 0) & ~(entry(ak, "origin", "reads")[2] or 0)
    entry(one_less, "origin")[2] ^= 1 << (grown.bit_length() - 1)     # the last bit acknowledged, not written
    assert prow(ak)[2] is True
    gk = prow(ak)[1][0]
    prow(not_planned)[2] = None         # the row gone, with all under it (a trace of the whole state has them)
    for where in ("reads", "rest"):
        not_planned[where] = [e for e in not_planned[where] if not (e[0] == "planned" and len(e[1]) == 2 and e[1][0] == gk)]
    one = (hdr, nodes)
    return check("§4.3's HAVE", {
        "a HAVE with new indices, as it is": (alone(*one, hv), 0, None),
        # (window_release is the twin's own: nothing of a new index is on the tape, and the twin, taking the bit
        # as held, leaves the index's holder unwritten: the state)
        "the peer's entry read with the first new bit there": (alone(*one, had), 1, "post"),
        "the entry written with a ttl one less": (alone(*one, ttl_less), 1, "post"),
        "the entry written without the first new bit": (alone(*one, bits_less), 1, "post"),
        "the first new index's holders written without the peer": (alone(*one, no_holder), 1, "post"),
        "the send's entry read under another index": (alone(*one, other_index), 1, "footprint, reads"),
        # (origin_acked is the twin's own: a group in planned with no `origin` is a KeyError in the Python and in
        # the twin)
        "the group said to be planned": (alone(*one, planned), 1, "KeyError"),
        "the group said to have expired": (alone(*one, gone), 1, "tape"),
        "the HAVE said not to be valid": (alone(*one, invalid), 1, "tape"),
        "its node's HAVE_TTL written as 7": (alone(hdr, long_ttl, hv), 1, "post"),
        "an invalid HAVE, as it is": (alone(*one, bad), 0, None),
        "its sender not penalised": (alone(*one, unpunished), 1, "tape"),
        "an empty HAVE that makes the peer's entry, as it is": (alone(*one, em), 0, None),
        "that entry's write left out": (alone(*one, unmade), 1, "post"),
        "a HAVE of nothing new that refreshes the ttl, as it is": (alone(*one, rf), 0, None),
        "that refresh left out of the writes": (alone(*one, stale), 1, "post"),
        "a HAVE for a group the node publishes, as it is": (alone(*one, ak), 0, None),
        "origin's write left out": (alone(*one, unacked), 1, "post"),
        "origin written without the last chunk acknowledged": (alone(*one, one_less), 1, "post"),
        "that group said not to be planned": (alone(*one, not_planned), 1, "tape"),
    }, work, head, "have")


def frame_controls(directed41, work, head):
    """§4.1's on_frame and respond, §4.5's on_iwant (`serve_count` the twin's own; a node's own on_iwant a call on
    the tape), on directed41's records. Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **change):       # the nodes line with this record's node alone, changed
        own = node_of(nodes, d)
        e = {**copy.deepcopy(own), "n": [d["n"]]}
        if "consts" in change:
            e["consts"] = {**e["consts"], **change.pop("consts")}
        e.update(change)
        return {"nodes": [e]}

    def ok(d, fn):
        return d["fn"] == fn and "raises" not in d

    # ---- on_iwant: one ask, answered (the tape: expired, resolve, chunk_of; `unwanted[p]` among its reads, the
    # twin's own table)
    def answers_one(d):
        return (ok(d, "on_iwant") and names(d) == ["expired", "resolve", "chunk_of"] and len(d["ret"]) == 1
                and any(e[0] == "serve_count" for e in d["writes"])
                and [e[1] for e in d["reads"] if e[0] == "unwanted"] == [[d["args"][0]]])
    hdr, nodes, ia = first(directed41, answers_one)
    no_id, unwanted, uncounted, other_chunk, replaced = (copy.deepcopy(ia) for _ in range(5))
    no_id["tape"][1][2] = None
    said = next(e for e in unwanted["reads"] if e[0] == "unwanted")    # the peer's set read with the id in it
    said[2] = sorted((said[2] or []) + [ia["tape"][1][2]])
    uncounted["writes"] = [e for e in uncounted["writes"] if e[0] != "serve_count"]
    retable(uncounted)
    other_chunk["tape"][2][2][1] += 1                           # chunk_of answers with the next index's chunk,
    c = other_chunk["tape"][2][2]                               #   whole: its id is that index's
    c[4] = c[4][:64] + c[1].to_bytes(4, "little").hex() + c[4][72:]
    torn = copy.deepcopy(ia)                                    # (these controls' first run had the index alone
    torn["tape"][2][2][1] += 1                                  #   changed: the chunk's own reader refused it first)
    _, _, two = first(directed41, lambda d: ok(d, "on_iwant") and len(d["ret"]) >= 2)
    swapped = copy.deepcopy(two)
    swapped["ret"].reverse()

    def asked_twice(d):                 # one chunk asked twice, answered once
        cs = [t[1][0] for t in d["tape"] if t[0] == "chunk_of"] if ok(d, "on_iwant") else []
        return len(cs) >= 2 and len(set(cs)) < len(cs) and len(d["ret"]) == len(set(cs))
    _, _, tw = first(directed41, asked_twice)
    doubled = copy.deepcopy(tw)
    doubled["ret"].append(copy.deepcopy(tw["ret"][0]))

    # ---- respond
    def rides(d):                       # the control on the first of two answers or more, each admitted
        es = [t for t in d["tape"] if t[0] == "enqueue"] if ok(d, "respond") else []
        return len(es) >= 2 and es[0][1][1][1][1] is not None and all(t[2] is True for t in es)
    _, _, rs = first(directed41, rides)
    both = copy.deepcopy(rs)
    both["tape"][at(rs, "enqueue", 1)][1][1][1][1] = copy.deepcopy(rs["tape"][at(rs, "enqueue")][1][1][1][1])
    unsolicited = copy.deepcopy(rs)
    unsolicited["tape"][at(rs, "enqueue")][1][1][1][2] = False

    def owes(d):
        return ok(d, "respond") and any(e[0] == "owed_answers" for e in d["writes"])
    _, _, ow = first(directed41, owes)
    not_owed = copy.deepcopy(ow)
    not_owed["writes"] = [e for e in not_owed["writes"] if e[0] != "owed_answers"]
    retable(not_owed)

    def alone_control(d):
        return ok(d, "respond") and names(d) == ["enqueue"] and d["tape"][0][1][1][1][0] is None
    _, _, ac = first(directed41, alone_control)
    no_prune = copy.deepcopy(ac)
    no_prune["tape"][0][1][1][1][1] = [m for m in no_prune["tape"][0][1][1][1][1] if m[0] != "prune"]

    # ---- on_frame: an ask answered and the same chunk's HAVE taken, in one frame
    # (the ask answered and the HAVE's new index are of ONE chunk, by group and index, and the tape has the answer
    # before the stock's prunes and the HAVE's questions after them: with the two of different chunks, the control
    # would fail as stated without the conflict its name says. The HAVE's new index is its read of `sent`
    # (window_release, the twin's own))
    def new_have(d):                    # the (group, index) the frame's HAVEs newly bring, from its peer
        return {(e[1][0][1], e[1][0][2]) for e in d["reads"] if e[0] == "sent" and e[1][0][0] == d["args"][0]}

    def ask_then_have(d):
        if not ok(d, "on_frame") or "chunk_of" not in names(d) or "handle_graft_prune" not in names(d):
            return False
        hp = at(d, "handle_graft_prune")
        answered = {(t[2][0], t[2][1]) for j, t in enumerate(d["tape"]) if t[0] == "chunk_of" and j < hp}
        asked_after = {t[1][0] for j, t in enumerate(d["tape"]) if t[0] == "expired" and j > hp}
        return any(c in new_have(d) and c[0] in asked_after for c in answered)
    _, _, fr = first(directed41, ask_then_have)

    def chunk_then_have(d):             # the other frame: a chunk accepted and stored, and its HAVE in the same frame
        if not ok(d, "on_frame") or "store" not in names(d) or "handle_graft_prune" not in names(d):
            return False
        hp = at(d, "handle_graft_prune")
        stored = {(t[1][0], t[1][1]) for j, t in enumerate(d["tape"]) if t[0] == "store" and j < hp}
        asked_after = {t[1][0] for j, t in enumerate(d["tape"]) if t[0] == "expired" and j > hp}
        return any(c in new_have(d) and c[0] in asked_after for c in stored)
    _, _, ch = first(directed41, chunk_then_have)
    ch_no_have = copy.deepcopy(ch)
    ch_no_have["args"][1][3] = []                               # the frame without its IDONTWANT
    no_have, prunes, at_other = (copy.deepcopy(fr) for _ in range(3))
    no_have["args"][1][3] = []                                  # the frame without its IDONTWANT
    prunes["tape"][at(fr, "handle_graft_prune")][2] = [["a prune"]]
    assert "on_iwant" not in node_of(nodes, fr)["replaced"]

    # ---- on_frame: an IDONTWANT's entry that is no bitmap (v0.10.4; each outcome written before these first
    # ran): the id goes into the peer's set, `unwanted[p]`, the twin's own table
    def ids_of(d):
        return [h for h in d["args"][1][3] if isinstance(h, str)]

    def unw(d, where):                  # the record's entry of unwanted[p] in its reads or its writes
        return [e for e in d[where] if e[0] == "unwanted" and e[1] == [d["args"][0]]]

    def keeps_new(d):                   # one id, not said before, into a set that has others
        return (ok(d, "on_frame") and len(ids_of(d)) == 1 and len(unw(d, "writes")) == 1
                and len(unw(d, "reads")) == 1 and unw(d, "reads")[0][2] and len(ids_of(d)[0]) == 40)
    _, _, fi = first(directed41, keeps_new)
    unkept, as_read, other_id = (copy.deepcopy(fi) for _ in range(3))
    unkept["writes"] = [e for e in unkept["writes"] if e[0] != "unwanted"]
    retable(unkept)
    unw(as_read, "writes")[0][2] = copy.deepcopy(unw(fi, "reads")[0][2])
    k = next(j for j, h in enumerate(other_id["args"][1][3]) if isinstance(h, str))
    other_id["args"][1][3][k] = "25" * 20

    def said_already(d):                # every id of the frame said before: the set read, and not changed
        return (ok(d, "on_frame") and ids_of(d) and not unw(d, "writes") and len(unw(d, "reads")) == 1
                and set(ids_of(d)) <= set(unw(d, "reads")[0][2] or []))
    _, _, fa = first(directed41, said_already)
    not_said = copy.deepcopy(fa)
    e = unw(not_said, "reads")[0]
    e[2] = [x for x in e[2] if x != ids_of(fa)[0]] or None

    def node_answers(d):                # a frame at the node with its own on_iwant, which answered
        return ok(d, "on_frame") and "on_iwant" in names(d) and d["tape"][at(d, "on_iwant")][2]
    _, _, nf = first(directed41, node_answers)
    assert "on_iwant" in node_of(nodes, nf)["replaced"]

    def with_iwant(d):                  # the node's replaced names and on_iwant (this set's nodes have the
        return sorted(set(node_of(nodes, d)["replaced"]) | {"on_iwant"})      # scenario's level 1 among them)

    def without_iwant(d):
        return [x for x in node_of(nodes, d)["replaced"] if x != "on_iwant"]
    fewer = copy.deepcopy(nf)
    fewer["tape"][at(nf, "on_iwant")][2].pop()
    one = (hdr, nodes)
    return check("§4.1's frame and §4.5's IWANT", {
        "on_iwant: one ask answered, as it is": (alone(*one, ia), 0, None),
        "resolve's answer written as none": (alone(*one, no_id), 1, "tape"),
        "the id read as one the peer does not want": (alone(*one, unwanted), 1, "tape"),
        "serve_count's write left out": (alone(*one, uncounted), 1, "post"),
        "chunk_of's answer the next index's chunk": (alone(*one, other_chunk), 1, "not the chunk of the id asked"),
        "chunk_of's answer with another index under the same id": (alone(*one, torn), 1,
                                                                   "a chunk's id is not of its group and index"),
        "its node's GOSSIP_RETRANSMISSION written as 0": (
            alone(hdr, line(nodes, ia, consts={"GOSSIP_RETRANSMISSION": 0}), ia), 1, "tape"),
        "its node said to run its own on_iwant": (alone(hdr, line(nodes, ia, replaced=with_iwant(ia)), ia), 1,
                                                  "a record of on_iwant at a node that has replaced it"),
        "on_iwant: two answers, as it is": (alone(*one, two), 0, None),
        "the two answers returned in the other order": (alone(*one, swapped), 1, "return value"),
        "on_iwant: a chunk asked twice, answered once, as it is": (alone(*one, tw), 0, None),
        "that chunk returned twice": (alone(*one, doubled), 1, "return value"),
        "respond: the control on the first of several answers, as it is": (alone(*one, rs), 0, None),
        "the control on the second answer too": (alone(*one, both), 1, "tape"),
        "the first answer's entry not marked solicited": (alone(*one, unsolicited), 1, "tape"),
        "respond: an answer refused and owed, as it is": (alone(*one, ow), 0, None),
        "the owed answer's write left out": (alone(*one, not_owed), 1, "post"),
        "respond: control alone, as it is": (alone(*one, ac), 0, None),
        "its entry without the empty PRUNE": (alone(*one, no_prune), 1, "tape"),
        "on_frame: an ask answered, then the same chunk's HAVE, as it is": (alone(*one, fr), 0, None),
        "the frame written without its IDONTWANT": (alone(*one, no_have), 1, "tape"),
        "on_frame: a chunk stored, then its own HAVE, as it is": (alone(*one, ch), 0, None),
        "that frame written without its IDONTWANT": (alone(*one, ch_no_have), 1, "tape"),
        "handle_graft_prune's answer with a prune": (alone(*one, prunes), 1, "prunes, of which a record holds none"),
        "the frame's node said to run its own on_iwant": (alone(hdr, line(nodes, fr, replaced=with_iwant(fr)), fr), 1,
                                                          "tape"),
        "on_frame at a node with its own on_iwant, as it is": (alone(*one, nf), 0, None),
        "that node said to run the document's": (alone(hdr, line(nodes, nf, replaced=without_iwant(nf)), nf), 1, "tape"),
        "the node's answers one fewer": (alone(*one, fewer), 1, "tape"),
        "on_frame: an IDONTWANT's id kept, as it is": (alone(*one, fi), 0, None),
        "its write of unwanted left out": (alone(*one, unkept), 1, "post"),
        "unwanted written as it was read": (alone(*one, as_read), 1, "post"),
        "the frame's id written as another": (alone(*one, other_id), 1, "post"),
        "on_frame: an id the peer said already, as it is": (alone(*one, fa), 0, None),
        "that id not in the set read": (alone(*one, not_said), 1, "post"),
    }, work, head, "frame")


def decode_controls(directed46d, work, head):
    """§4.6's decode_group and push_rebuilt (a node's own push_rebuilt a call on the tape), on directed46d's records.
    Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def ok(d, fn):
        return d["fn"] == fn and "raises" not in d

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, replaced):
        return {"nodes": [{**copy.deepcopy(node_of(nodes, d)), "n": [d["n"]], "replaced": replaced}]}

    # (note_push and owe are the twin's own, and not on the tape: a push made shows as its enqueue taken, one owed
    # as its enqueue refused)
    def taken(d):                       # the peers of the pushes the queue took, in order
        return [t[1][0] for t in d["tape"] if t[0] == "enqueue" and t[2] is True]

    # ---- decode_group at the node that runs the document's repair: new chunks stored, a chunk pushed
    def decodes(d):
        return (ok(d, "decode_group") and names(d).count("store") >= 2 and taken(d)
                and len(d["tape"][at(d, "decode_and_reencode")][2]) >= 4)
    hdr, nodes, dg = first(directed46d, decodes)
    assert node_of(nodes, dg)["replaced"] == []
    k = at(dg, "decode_and_reencode")
    differs, gone, fewer, swapped, twice, other_group, undone, no_payload, blobbed = (copy.deepcopy(dg) for _ in range(9))
    differs["tape"][k][2] = None
    gone["tape"][at(dg, "expired")][2] = True
    stored = dg["tape"][at(dg, "store")][1][1]                  # the first new index
    fewer["tape"][k][2] = [x for x in fewer["tape"][k][2] if x[0] != stored]
    a, b = [j for j, x in enumerate(dg["tape"][k][2]) if x[0] in [t[1][1] for t in dg["tape"] if t[0] == "store"]][:2]
    swapped["tape"][k][2][a], swapped["tape"][k][2][b] = swapped["tape"][k][2][b], swapped["tape"][k][2][a]
    twice["tape"][k][2].append(copy.deepcopy(dg["tape"][k][2][0]))
    c = other_group["tape"][k][2][0][1]
    c[0] = ("ee" if c[0][:2] != "ee" else "dd") * 32
    c[4] = c[0] + c[4][64:]
    undone["writes"] = [e for e in undone["writes"] if e[0] != "state"]
    retable(undone)
    del no_payload["tape"][at(dg, "payload_of")]
    blobbed["tape"][at(dg, "payload_of")][2] = [5, "x"]

    # ---- the root differs: the group dropped
    _, _, dr = first(directed46d, lambda d: ok(d, "decode_group") and "discard_queued" in names(d))
    rebuilt = copy.deepcopy(dr)
    rebuilt["tape"][at(dr, "decode_and_reencode")][2] = []

    # ---- decode_group at the node with its own push_rebuilt, which pushed
    def node_pushes(d):
        return ok(d, "decode_group") and "push_rebuilt" in names(d) and len(d["tape"][at(d, "push_rebuilt")]) == 4
    _, _, np_ = first(directed46d, node_pushes)
    assert node_of(nodes, np_)["replaced"] == ["push_rebuilt"]
    other_new = copy.deepcopy(np_)
    other_new["tape"][at(np_, "push_rebuilt")][1][1] = other_new["tape"][at(np_, "push_rebuilt")][1][1][:-1]
    no_log = copy.deepcopy(np_)
    del no_log["tape"][at(np_, "push_rebuilt")][3]

    # ---- push_rebuilt: two mesh peers or more, the first short and pushed to
    def pushes(d):
        if not ok(d, "push_rebuilt") or not taken(d):
            return False
        m = d["tape"][at(d, "mesh")][2]
        # (two peers pushed to: with `pushed` and `desc` the twin's own, the order of the mesh's peers shows on the
        # tape by the order of their pushes alone. With one peer pushed to, the mesh's own order replays as the
        # draw.)
        return (len(m) >= 2 and d["tape"][at(d, "shuffled")][2] != m and len(d["tape"][at(d, "shuffled", 1)][2]) >= 2
                and len(set(taken(d))) >= 2)
    _, _, pr = first(directed46d, pushes)
    in_order, lacks_rev, pushed_all, wrong_chunk, unnoted = (copy.deepcopy(pr) for _ in range(5))
    in_order["tape"][at(pr, "shuffled")][2] = list(pr["tape"][at(pr, "mesh")][2])       # the draw: the mesh's own order
    lacks_rev["tape"][at(pr, "shuffled", 1)][2].reverse()
    # (`pushed` is the twin's own: the first peer's entry is the record's first read of it; an entry is [bits, the
    # first push's time, ttl])
    q0 = taken(pr)[0]                                           # the first peer pushed to
    next(e for e in pushed_all["reads"] if e[0] == "pushed" and e[1][0] == q0)[2] = [(1 << 8) - 1, 0, 6]
    #                                     everything said to be pushed to that peer already: no push to it, then
    ck = next(j for j, t in enumerate(pr["tape"]) if t[0] == "read" and t[1] == "chunks")
    wrong_chunk["tape"][ck][3][1] += 1                          # the chunk read: of the next index, under this one
    # (the push not counted: the entry of `pushed` written without the first index pushed to that peer)
    i0 = next(t for t in pr["tape"] if t[0] == "enqueue" and t[2] is True)[1][1][1][1]     # ["chunk", [g, i, ...]]
    w0 = next(e for e in unnoted["writes"] if e[0] == "pushed" and e[1][0] == q0)
    assert w0[2][0] >> i0 & 1, (w0, i0)
    w0[2][0] ^= 1 << i0

    def owes(d):
        return ok(d, "push_rebuilt") and any(t[0] == "enqueue" and t[2] is False for t in d["tape"])
    _, _, ow = first(directed46d, owes)
    admitted = copy.deepcopy(ow)
    e = next(j for j, t in enumerate(ow["tape"]) if t[0] == "enqueue" and t[2] is False)
    admitted["tape"][e][2] = True
    one = (hdr, nodes)
    return check("§4.6's decode and repair", {
        "decode_group: new chunks stored, one pushed, as it is": (alone(*one, dg), 0, None),
        "the decode said to give nothing (the root differs)": (alone(*one, differs), 1, "tape"),
        "the group said to have expired meanwhile": (alone(*one, gone), 1, "tape"),
        "the rebuilt chunks without the first new one": (alone(*one, fewer), 1, "tape"),
        "two new rebuilt chunks in the other order": (alone(*one, swapped), 1, "tape"),
        "a rebuilt index twice": (alone(*one, twice), 1, "decode_and_reencode: a key twice"),
        "a rebuilt chunk of another group": (alone(*one, other_group), 1, "a rebuilt chunk of another group"),
        "the state's write left out": (alone(*one, undone), 1, "post"),
        "payload_of not on the tape": (alone(*one, no_payload), 1, "tape"),
        "payload_of's answer a blob, deliver's still nothing": (alone(*one, blobbed), 1, "tape"),
        "its node said to run its own push_rebuilt": (alone(hdr, line(nodes, dg, ["push_rebuilt"]), dg), 1, "tape"),
        "decode_group: the root differs, the group dropped, as it is": (alone(*one, dr), 0, None),
        "that decode said to give no chunk, but to succeed": (alone(*one, rebuilt), 1, "tape"),
        "decode_group at a node with its own push_rebuilt, as it is": (alone(*one, np_), 0, None),
        "that node said to run the document's": (alone(hdr, line(nodes, np_, []), np_), 1, "tape"),
        "the node's push_rebuilt asked of fewer new chunks": (alone(*one, other_new), 1, "tape"),
        "the node's push_rebuilt without its log": (alone(*one, no_log), 1, "post"),
        "push_rebuilt: a draw of the mesh, a peer pushed to, as it is": (alone(*one, pr), 0, None),
        "the draw of the mesh written as the mesh's own order": (alone(*one, in_order), 1, "tape"),
        "the draw of what the peer lacks reversed": (alone(*one, lacks_rev), 1, "tape"),
        "everything said to be pushed to the first peer already": (alone(*one, pushed_all), 1, "tape"),
        "the chunk read from the store of the next index": (alone(*one, wrong_chunk), 1, "a chunk's id is not of its group and index"),
        "the first peer's entry of pushed written without its first index": (alone(*one, unnoted), 1, "post"),
        "push_rebuilt: a push refused and owed, as it is": (alone(*one, ow), 0, None),
        "that push said to be admitted": (alone(*one, admitted), 1, "tape"),
    }, work, head, "decode")


def level1_controls(directed3v, directed42, work, head):
    """§3's level 1 (validate_chunk and committed_descriptor; a chunk wide where it arrives or waits, a block what
    level 1 reads of it; a scenario's level 1 a call on the tape in a directed set), on directed3v's records and one
    of directed42's. Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **change):
        own = node_of(nodes, d)
        e = {**copy.deepcopy(own), "n": [d["n"]]}
        if "consts" in change:
            e["consts"] = {**e["consts"], **change.pop("consts")}
        e.update(change)
        return {"nodes": [e]}

    def design_a(nodes, d):
        return node_of(nodes, d)["consts"]["DESCRIPTOR_IN_CHUNK"] is True

    hdr, nodes, _ = first(directed3v, lambda d: True)

    # ---- an accepted chunk, design A: the block, the two ids, the key, the length, the proof
    def accepted(d):
        return (d["fn"] == "validate_chunk" and "raises" not in d and d["ret"] == "ACCEPT" and design_a(nodes, d)
                and len(d["args"][0][5][1]) >= 1)
    _, _, ok = first(directed3v, accepted)
    k = at(ok, "installed_block")
    no_block, other_slot, no_id, other_id, narrow, longer, far, refused, said_reject, one_hash = (
        copy.deepcopy(ok) for _ in range(10))
    no_block["tape"][k][2] = None
    other_slot["tape"][k][2][0] += 1
    no_id["tape"][k][2][1] = None
    other_id["tape"][k][2][1] = ("ee" if ok["tape"][k][2][1][:2] != "ee" else "dd") * 32
    narrow["args"][0] = narrow["args"][0][:5]                   # the chunk without what level 1 reads
    longer["args"][0][5][2][0] += 1                             # its data one byte longer
    far["args"][0][1] = ok["args"][0][5][0][3]                  # its index at the count: another chunk, its id too
    c = far["args"][0]
    c[4] = c[4][:64] + c[1].to_bytes(4, "little").hex() + c[4][72:]
    refused["tape"][at(ok, "verify_merkle_proof")][2] = False
    said_reject["ret"] = "REJECT"
    one_hash["tape"] = [t for j, t in enumerate(ok["tape"]) if j != at(ok, "sha256", 1)]    # the second hash not asked

    # ---- the other outcomes, each as it is and with its cause taken away
    def rejected_for(branch_tail):      # by where the tape ends
        return lambda d: (d["fn"] == "validate_chunk" and "raises" not in d and d["ret"] == "REJECT"
                          and design_a(nodes, d) and names(d)[-1] == branch_tail)
    _, _, bad_proof = first(directed3v, rejected_for("verify_merkle_proof"))
    proof_ok = copy.deepcopy(bad_proof)
    proof_ok["tape"][-1][2] = True
    # (at a design B node: a block of no group is rejected there with no question, so the altered record fails by
    # its return value. At a design A node the document first asks the hash of the chunk's descriptor, and the
    # altered record would fail by its tape. The pick asks for a design B node.)
    _, _, deferred = first(directed3v, lambda d: d["fn"] == "validate_chunk" and "raises" not in d and d["ret"] == "DEFER"
                           and not design_a(nodes, d))
    there = copy.deepcopy(deferred)
    there["tape"][0][2] = [deferred["args"][0][2], None, None]  # a block there, of no group

    # ---- design B: the bid's descriptor
    def b_accepted(d):
        # (a chunk with its descriptor on it: the wire shape without one is carried_controls')
        return (d["fn"] == "validate_chunk" and "raises" not in d and d["ret"] == "ACCEPT" and not design_a(nodes, d)
                and d["args"][0][5][0] is not None)
    _, _, okb = first(directed3v, b_accepted)
    kb = at(okb, "installed_block")
    b_none, b_other, as_a = (copy.deepcopy(okb) for _ in range(3))
    b_none["tape"][kb][2][2] = None
    b_other["tape"][kb][2][2][6] = ("ee" if okb["tape"][kb][2][2][6][:2] != "ee" else "dd") * 32    # another root
    # ---- committed_descriptor, alone
    def cd(d, a):
        return d["fn"] == "committed_descriptor" and "raises" not in d and d["ret"] is not None and design_a(nodes, d) == a
    _, _, ca = first(directed3v, lambda d: cd(d, True))
    ca_none = copy.deepcopy(ca)
    ca_none["ret"] = None
    ca_block = copy.deepcopy(ca)
    ca_block["args"][0][1] = None
    # ---- a scenario's level 1 (directed42): a record whose node has validate_chunk replaced
    hdr42, nodes42, sv = first(directed42, lambda d: d["fn"] == "on_chunk" and "raises" not in d
                               and "validate_chunk" in [t[0] for t in d["tape"]])
    # (forward is a traced name the scenario of directed42 answers too, so its node's line names both; the control
    # turns level 1 alone, and keeps the scenario's forward)
    assert node_of(nodes42, sv)["replaced"] == ["forward", "validate_chunk"]
    one = (hdr, nodes)
    return check("§3's level 1", {
        "validate_chunk: a chunk accepted, as it is": (alone(*one, ok), 0, None),
        # (the three whose twin returns before the tape's end were stated "return value" at these controls' first
        # run: the tape left is told first)
        "the block said not to be there": (alone(*one, no_block), 1, "tape: the toy asked more"),
        "the block of the next slot": (alone(*one, other_slot), 1, "tape: the toy asked more"),
        "the block's bid with no group id": (alone(*one, no_id), 1, "tape"),
        "the block's bid with another group id": (alone(*one, other_id), 1, "tape"),
        "the chunk written without what level 1 reads": (alone(*one, narrow), 1, "AttributeError"),
        "the chunk's data one byte longer": (alone(*one, longer), 1, "tape"),
        "the chunk's index at the count": (alone(*one, far), 1, "tape"),
        "the proof said to fail": (alone(*one, refused), 1, "return value"),
        "the result written REJECT": (alone(*one, said_reject), 1, "return value"),
        "the key's hash not on the tape": (alone(*one, one_hash), 1, "tape"),
        "its node said to run design B": (alone(hdr, line(nodes, ok, consts={"DESCRIPTOR_IN_CHUNK": False}), ok), 1, "tape"),
        "its node said to run its own validate_chunk": (alone(hdr, line(nodes, ok, replaced=["validate_chunk"]), ok), 1,
                                                        "a record of validate_chunk at a node that has replaced it"),
        "validate_chunk: a proof the tree refuses, as it is": (alone(*one, bad_proof), 0, None),
        "that proof said to hold": (alone(*one, proof_ok), 1, "return value"),
        "validate_chunk: no block yet, as it is": (alone(*one, deferred), 0, None),
        "a block said to be there, of no group": (alone(*one, there), 1, "return value"),
        "validate_chunk under design B: accepted, as it is": (alone(*one, okb), 0, None),
        "the bid with no descriptor": (alone(*one, b_none), 1, "tape: the toy asked more"),
        "the bid's descriptor with another root": (alone(*one, b_other), 1, "tape"),
        "its node said to run design A": (alone(hdr, line(nodes, okb, consts={"DESCRIPTOR_IN_CHUNK": True}), okb), 1, "tape"),
        "committed_descriptor under design A: the chunk's, as it is": (alone(*one, ca), 0, None),
        "its answer written as none": (alone(*one, ca_none), 1, "return value"),
        "its block's bid with no group id": (alone(*one, ca_block), 1, "return value"),
        "on_chunk at a node with a scenario's level 1, as it is": (alone(hdr42, nodes42, sv), 0, None),
        "that node said to run the document's": (alone(hdr42, line(nodes42, sv, replaced=["forward"]), sv), 1, "tape"),
    }, work, head, "level1")


def sec52_controls(directed52, work, head):
    """§5.2's owe, note_push, unpush and announce (the twin's own; `wake` a call on the tape), on directed52's
    records. Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def entry(d, table, where="writes"):                # the record's entry of a table for its own peer and group
        return next((e for e in d[where] if e[0] == table and len(e[1]) == 2 and e[1] == d["args"][:2]), None)

    def plain(d, fn):
        return d["fn"] == fn and "raises" not in d

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    # ---- note_push: a later push onto an entry whose ttl has run down; a first push
    def later(d):
        r = entry(d, "pushed", "reads") if plain(d, "note_push") else None
        return (r is not None and r[2] is not None and r[2][0] and not r[2][0] >> d["args"][2] & 1
                and r[2][2] < 6 and r[2][1] != d["t"])
    hdr, nodes, lp = first(directed52, later)
    ttl_less, clock_now, no_bit = (copy.deepcopy(lp) for _ in range(3))
    entry(ttl_less, "pushed")[2][2] -= 1
    entry(clock_now, "pushed")[2][1] = lp["t"]
    entry(no_bit, "pushed")[2][0] ^= 1 << lp["args"][2]
    own = node_of(nodes, lp)
    long_ttl = {"nodes": [{**copy.deepcopy(own), "n": [lp["n"]], "consts": {**own["consts"], "PUSH_TTL": 7}}]}
    _, _, fp = first(directed52, lambda d: plain(d, "note_push") and entry(d, "pushed", "reads")[2] is None)
    unmade = copy.deepcopy(fp)
    unmade["writes"] = [e for e in unmade["writes"] if e[0] != "pushed"]
    retable(unmade)

    # ---- owe: bits added to an entry that has others
    def adds(d):
        r = entry(d, "owed", "reads") if plain(d, "owe") else None
        return r is not None and r[2] is not None and d["args"][2] & ~r[2] and r[2] & ~d["args"][2]
    _, _, ow = first(directed52, adds)
    unwoken, replaced_bits = copy.deepcopy(ow), copy.deepcopy(ow)
    del unwoken["tape"][at(ow, "wake")]
    entry(replaced_bits, "owed")[2] = ow["args"][2]

    # ---- unpush: a bit of several, in the mesh; an entry, outside the mesh; no entry
    def mesh(d):
        return d["tape"][at(d, "mesh_has")][2]

    def of_several(d):
        r = entry(d, "pushed", "reads") if plain(d, "unpush") else None
        return r is not None and r[2] is not None and r[2][0] >> d["args"][2] & 1 and r[2][0] != 1 << d["args"][2] and mesh(d)
    _, _, um = first(directed52, of_several)
    not_mesh, kept_bit = copy.deepcopy(um), copy.deepcopy(um)
    not_mesh["tape"][at(um, "mesh_has")][2] = False
    entry(kept_bit, "pushed")[2][0] |= 1 << um["args"][2]

    def outside(d):
        r = entry(d, "pushed", "reads") if plain(d, "unpush") else None
        return r is not None and r[2] is not None and not mesh(d)
    _, _, uo = first(directed52, outside)
    in_mesh = copy.deepcopy(uo)
    in_mesh["tape"][at(uo, "mesh_has")][2] = True
    _, _, un = first(directed52, lambda d: plain(d, "unpush") and entry(d, "pushed", "reads")[2] is None)
    there = copy.deepcopy(un)
    entry(there, "pushed", "reads")[2] = [1 << un["args"][2], un["t"], 3]

    # ---- announce: an offer taken; one refused; nothing to offer
    def enq(d):
        return d["tape"][at(d, "enqueue")] if plain(d, "announce") and "enqueue" in names(d) else None
    _, _, ao = first(directed52, lambda d: enq(d) is not None and enq(d)[2] is True)
    more_bits, said_refused = copy.deepcopy(ao), copy.deepcopy(ao)
    e = more_bits["tape"][at(ao, "enqueue")][1][1][0][1][0]     # [p, [["ihave", [["bits", g, b]]]], urgent]
    assert e[0] == "bits", e
    e[2] ^= 1 << 9
    said_refused["tape"][at(ao, "enqueue")][2] = False
    _, _, ar = first(directed52, lambda d: enq(d) is not None and enq(d)[2] is False)
    said_taken = copy.deepcopy(ar)
    said_taken["tape"][at(ar, "enqueue")][2] = True

    def nothing(d):
        return (plain(d, "announce") and d["args"][2] and "enqueue" not in names(d)
                and (entry(d, "pushed", "reads")[2] is not None or entry(d, "peer_has", "reads")[2] is not None))
    _, _, an = first(directed52, nothing)
    unknown = copy.deepcopy(an)
    entry(unknown, "pushed", "reads")[2] = None
    entry(unknown, "peer_has", "reads")[2] = None
    one = (hdr, nodes)
    return check("§5.2", {
        "a later push, as it is": (alone(*one, lp), 0, None),
        "the entry written with a ttl one less": (alone(*one, ttl_less), 1, "post"),
        "the entry written with its clock at now": (alone(*one, clock_now), 1, "post"),
        "the entry written without the index": (alone(*one, no_bit), 1, "post"),
        "its node's PUSH_TTL written as 7": (alone(hdr, long_ttl, lp), 1, "post"),
        "a first push, as it is": (alone(*one, fp), 0, None),
        "that entry's write left out": (alone(*one, unmade), 1, "post"),
        "an offer owed on top of others, as it is": (alone(*one, ow), 0, None),
        "its wake taken off the tape": (alone(*one, unwoken), 1, "tape"),
        "owed written as the call's bits alone": (alone(*one, replaced_bits), 1, "post"),
        "a push of several unpushed in the mesh, as it is": (alone(*one, um), 0, None),
        "its peer said not to be in the mesh": (alone(*one, not_mesh), 1, "tape"),
        "the entry written with the index still there": (alone(*one, kept_bit), 1, "post"),
        "a push unpushed outside the mesh, as it is": (alone(*one, uo), 0, None),
        "its peer said to be in the mesh": (alone(*one, in_mesh), 1, "tape"),
        "an unpush of nothing pushed, as it is": (alone(*one, un), 0, None),
        "the entry read as there, with the index": (alone(*one, there), 1, "post"),
        "an offer the queue takes, as it is": (alone(*one, ao), 0, None),
        "the offer on the tape with a bit more": (alone(*one, more_bits), 1, "tape"),
        "the queue said to refuse it": (alone(*one, said_refused), 1, "tape"),
        "an offer the queue refuses, as it is": (alone(*one, ar), 0, None),
        "the queue said to take it": (alone(*one, said_taken), 1, "tape"),
        "nothing to offer, as it is": (alone(*one, an), 0, None),
        "the peer read as holding and pushed nothing": (alone(*one, unknown), 1, "tape"),
    }, work, head, "sec52")


def sec53_controls(directed53, work, head):
    """§5.3's guard_fails and choose_push (the twin's own; the push order's keys calls on the tape), on directed53's
    records. Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def entry(d, table):                # the record's read of a table for its own peer and group
        return next((e for e in d["reads"] if e[0] == table and e[1] == d["args"][:2]), None)

    def plain(d, fn):
        return d["fn"] == fn and "raises" not in d

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def ones(v):
        return bin(v).count("1")

    # ---- guard_fails: a peer demoted, with exactly R_NODE (2) pushed; one with fewer pushed
    def demoted(d):
        r = entry(d, "pushed") if plain(d, "guard_fails") else None
        return r is not None and r[2] is not None and d["ret"] is True and ones(r[2][0]) == 2 and entry(d, "peer_has")[2] is None
    hdr, nodes, gd = first(directed53, demoted)
    fewer, fresh, heard = (copy.deepcopy(gd) for _ in range(3))
    b = entry(fewer, "pushed")[2]
    b[0] &= b[0] - 1                                            # its lowest bit cleared
    entry(fresh, "pushed")[2][1] = gd["t"]
    entry(heard, "peer_has")[2] = [0, 3]
    own = node_of(nodes, gd)

    def line(**consts):
        return {"nodes": [{**copy.deepcopy(own), "n": [gd["n"]], "consts": {**own["consts"], **consts}}]}
    hundred = int.from_bytes(struct.pack("<d", 100.0), "little")
    _, _, gf = first(directed53, lambda d: plain(d, "guard_fails") and d["ret"] is False
                     and entry(d, "pushed")[2] is not None and ones(entry(d, "pushed")[2][0]) < 2)

    # ---- choose_push: a draw of two or more; everyone; at the source; nobody proven
    def draw(d):
        return d["tape"][at(d, "sample_without_replacement")] if plain(d, "choose_push") and "sample_without_replacement" in names(d) else None
    _, _, cd = first(directed53, lambda d: draw(d) is not None and len(draw(d)[2]) >= 2
                     and len(draw(d)[1][0]) > len(draw(d)[2]))
    k = at(cd, "sample_without_replacement")
    reversed_, smaller_pool, no_key, as_source = (copy.deepcopy(cd) for _ in range(4))
    reversed_["tape"][k][2].reverse()
    assert reversed_["tape"][k][2] != cd["tape"][k][2]
    gone = next(q for q in reversed(cd["tape"][k][1][0]) if q not in cd["tape"][k][2])   # a peer of the pool not drawn
    smaller_pool["tape"][k][1][0].remove(gone)
    del no_key["tape"][at(cd, "tiebreak")]
    as_source["args"][3] = True
    _, _, ce = first(directed53, lambda d: plain(d, "choose_push") and not d["tape"] and len(d["args"][1]) >= 2
                     and d["args"][2] >= len(d["args"][1]))
    short = copy.deepcopy(ce)
    short["args"][2] = len(ce["args"][1]) - 1
    _, _, cs = first(directed53, lambda d: plain(d, "choose_push") and d["args"][3] is True and d["tape"])
    _, _, cn = first(directed53, lambda d: plain(d, "choose_push") and d["args"][3] is False and d["tape"]
                     and "sample_without_replacement" not in names(d))
    one = (hdr, nodes)
    return check("§5.3", {
        "a peer demoted with exactly R_NODE pushed, as it is": (alone(*one, gd), 0, None),
        "pushed read with one bit fewer": (alone(*one, fewer), 1, "return"),
        "the first push's time read as now": (alone(*one, fresh), 1, "return"),
        "peer_has read as there, with no bit": (alone(*one, heard), 1, "return"),
        "its node's R_NODE written as 9": (alone(hdr, line(R_NODE=9), gd), 1, "return"),
        "its node's GUARD_GRACE written as 100 s": (alone(hdr, line(GUARD_GRACE=hundred), gd), 1, "return"),
        "a peer with fewer than R_NODE pushed, as it is": (alone(*one, gf), 0, None),
        "a draw of two or more, as it is": (alone(*one, cd), 0, None),
        "the draw's answer in the other order": (alone(*one, reversed_), 1, "return"),
        "the draw's question without a peer of its pool": (alone(*one, smaller_pool), 1, "tape"),
        "the first tiebreak taken off the tape": (alone(*one, no_key), 1, "tape"),
        "at_source written as true": (alone(*one, as_source), 1, "tape"),
        "a budget that covers the candidates, as it is": (alone(*one, ce), 0, None),
        "the budget written one less than the candidates": (alone(*one, short), 1, "tape"),
        "choose_push at the source, as it is": (alone(*one, cs), 0, None),
        "choose_push with nobody proven, as it is": (alone(*one, cn), 0, None),
    }, work, head, "sec53")


def carried_controls(directed3v, directed1, v2trace, work, head):
    """Three cases. Each outcome was written before the controls first ran. Without a case's fix the picked record
    does not exist: the pick raises "no such record", and the tool fails.
    - a design B chunk in its wire shape, without a descriptor field;
    - message_id of an index beyond a uint32, whose raise is a record;
    - a node's `replaced` holds a name the header does not list as traced."""
    def names(d):
        return [t[0] for t in d["tape"]]

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **consts):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **consts}}]}

    def design_a(nodes, d):
        return node_of(nodes, d)["consts"]["DESCRIPTOR_IN_CHUNK"]

    def bare(d):                        # the record's chunk is wide and has no descriptor
        c = d["args"][0]
        return len(c) == 6 and c[5][0] is None

    hdr, nodes, _ = first(directed3v, lambda d: True)

    def b_bare(d):                      # design B: accepted with no descriptor on the chunk, the proof asked
        return (d["fn"] == "validate_chunk" and "raises" not in d and d["ret"] == "ACCEPT" and not design_a(nodes, d)
                and bare(d) and names(d)[-1] == "verify_merkle_proof")
    _, _, bb = first(directed3v, b_bare)
    longer = copy.deepcopy(bb)
    longer["args"][0][5][2][0] += 1                             # its data one byte longer

    def a_bare(d):                      # design A: the document reads f.descriptor, and raises
        return d["fn"] == "validate_chunk" and d.get("raises") == "AttributeError" and design_a(nodes, d) and bare(d)
    _, _, ab = first(directed3v, a_bare)
    _, _, any_a = first(directed3v, lambda d: d["fn"] == "validate_chunk" and design_a(nodes, d) and len(d["args"][0]) == 6
                        and d["args"][0][5][0] is not None)
    given = copy.deepcopy(ab)
    given["args"][0][5][0] = copy.deepcopy(any_a["args"][0][5][0])      # a descriptor on it after all

    hdr1, nodes1, ov = first(directed1, lambda d: d["fn"] == "message_id" and d.get("raises") == "OverflowError")
    assert ov["args"][0][4] is None and ov["args"][0][1] == 2 ** 32 and not ov["tape"]
    within = copy.deepcopy(ov)
    within["args"][0][1] = 2 ** 32 - 1                          # the last index a uint32 holds
    # the third: a v2 cell's record with its node said to have replaced push_rebuilt, which v2's kept leaves out
    hdr2, nodes2, r2 = first(v2trace, lambda d: d["fn"] == "may_ask" and "raises" not in d)
    assert "push_rebuilt" not in hdr2["header"]["traced"], "V2's header traces push_rebuilt"
    own2 = node_of(nodes2, r2)
    untraced = {"nodes": [{**copy.deepcopy(own2), "n": [r2["n"]], "replaced": sorted(set(own2["replaced"]) | {"push_rebuilt"})}]}
    just = {"nodes": [{**copy.deepcopy(own2), "n": [r2["n"]]}]}
    return check("a chunk without a descriptor field, an index past a uint32, an untraced name replaced", {
        "design B: a chunk with no descriptor field, accepted, as it is": (alone(hdr, nodes, bb), 0, None),
        "its data one byte longer": (alone(hdr, nodes, longer), 1, "tape"),
        "its node said to run design A": (alone(hdr, line(nodes, bb, DESCRIPTOR_IN_CHUNK=True), bb), 1, "AttributeError"),
        "design A: a chunk with no descriptor field raises, as it is": (alone(hdr, nodes, ab), 0, None),
        "that chunk given a descriptor": (alone(hdr, nodes, given), 1, "the Python raises AttributeError"),
        "message_id of an index beyond a uint32 raises, as it is": (alone(hdr1, nodes1, ov), 0, None),
        "its index written as the last a uint32 holds": (alone(hdr1, nodes1, within), 1, "the Python raises OverflowError"),
        "a v2 cell's record with its node's line, as it is": (alone(hdr2, just, r2), 0, None),
        "that node said to have replaced push_rebuilt, which the header does not trace": (
            alone(hdr2, untraced, r2), 1, "nodes: has replaced [push_rebuilt], which the header does not list as traced"),
    }, work, head, "carried")


def sec71_controls(directed71, work, head):
    """§7.1's six, the twin's own, on directed71's records. Each outcome was written before the controls first ran,
    by the replay's order of checks: a question against the tape, the tape used up, the return value, the
    functions reached, the whole state, the notes."""
    def names(d):
        return [t[0] for t in d["tape"]]

    def plain(d, fn):
        return d["fn"] == fn and "raises" not in d

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **consts):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **consts}}]}

    def ent(d, table, where="reads"):
        return next((e for e in d[where] if e[0] == table), None)

    def val(d, table, where="reads"):
        e = ent(d, table, where)
        return None if e is None else e[2]

    hdr, nodes, _ = first(directed71, lambda d: True)
    windowed = lambda d: node_of(nodes, d)["consts"]["W"] == 2      # noqa: E731: the node with a window of 2

    # ---- acquire_slot
    def takes_alone(d):                 # a slot free, nobody in line: nothing on the tape
        return plain(d, "acquire_slot") and windowed(d) and d["ret"] is True and not d["tape"] and val(d, "waiters") is None
    _, _, aq = first(directed71, takes_alone)
    full = copy.deepcopy(aq)
    ent(full, "in_flight")[2] = 2                               # the count read at the window

    def wakes_next(d):                  # the peer first in line, another behind, two slots free: the next is woken
        return (plain(d, "acquire_slot") and windowed(d) and d["ret"] is True and names(d) == ["wake"]
                and len(val(d, "waiters") or []) >= 2)
    _, _, aw = first(directed71, wakes_next)
    alone_in_line, uncounted = copy.deepcopy(aw), copy.deepcopy(aw)
    ent(alone_in_line, "waiters")[2] = ent(aw, "waiters")[2][:1]
    uncounted["writes"] = [e for e in uncounted["writes"] if e[0] != "in_flight"]
    retable(uncounted)

    def joins(d):                       # another first: the peer joins the line
        return (plain(d, "acquire_slot") and d["ret"] is False and ent(d, "waiters", "writes") is not None
                and d["args"][0] not in (val(d, "waiters") or []))
    _, _, aj = first(directed71, joins)
    not_joined = copy.deepcopy(aj)
    ent(not_joined, "waiters", "writes")[2] = copy.deepcopy(val(aj, "waiters"))

    def unbounded(d):                   # the node with no window: a slot whatever the count
        return (plain(d, "acquire_slot") and not windowed(d) and d["ret"] is True and not d["tape"]
                and (val(d, "in_flight") or 0) >= 2 and val(d, "waiters") is None)
    _, _, au = first(directed71, unbounded)

    # ---- release_unused_slot: the peer in line leaves it; nobody is woken, no slot held
    def leaves(d):
        return (plain(d, "release_unused_slot") and d["args"][0] in (val(d, "waiters") or []) and not d["tape"]
                and d["reached"] == ["release_unused_slot"])
    _, _, rl = first(directed71, leaves)
    not_in_line = copy.deepcopy(rl)
    ent(not_in_line, "waiters")[2] = [q for q in val(rl, "waiters") if q != rl["args"][0]] or None

    # ---- track_in_flight: a new send
    def new_send(d):
        return plain(d, "track_in_flight") and names(d) == ["after"] and val(d, "sent") is None
    _, _, tf = first(directed71, new_send)
    no_timer, second = copy.deepcopy(tf), copy.deepcopy(tf)
    no_timer["tape"] = []
    ent(second, "sent")[2] = ent(tf, "sent", "writes")[2]      # the send read as in flight already

    # ---- window_release: a send in flight released, nobody in line
    def released(d):
        return (plain(d, "window_release") and val(d, "sent") is not None and not d["tape"]
                and "free_slot" in d["reached"])
    _, _, wr = first(directed71, released)
    not_sent = copy.deepcopy(wr)
    ent(not_sent, "sent")[2] = None

    # ---- window_timeout: still in flight for a planned group (origin_acked asked); and a stale timer
    def live_planned(d):
        # (origin_acked is the twin's own: by `reached`, at a node at ACK whose mesh is asked)
        return (plain(d, "window_timeout") and "origin_acked" in d["reached"] and "free_slot" in d["reached"]
                and "mesh" in names(d))
    _, _, wt = first(directed71, live_planned)
    unplanned = copy.deepcopy(wt)       # the group's row gone, and its entries with it (a row with an entry is there)
    gk = wt["args"][0][1]
    for where in ("reads", "rest"):
        unplanned[where] = [e for e in unplanned[where] if not (e[0] == "planned" and len(e[1]) == 2 and e[1][0] == gk)]
    next(e for e in unplanned["reads"] if e[0] == "planned" and e[1] == [gk])[2] = None
    retable(unplanned)

    def stale(d):                       # sent again since: the timer's time is not the send's; nobody in line, the
        # (a stale timer reads the send alone: the line and the rows of planned are in the record's rest, if anywhere)
        return (plain(d, "window_timeout") and val(d, "sent") is not None and d["reached"] == ["window_timeout"]   # group
                and not any(e[0] in ("waiters", "planned") and e[2] for e in d["reads"] + d["rest"]))               # not planned
    _, _, ws = first(directed71, stale)
    timely = copy.deepcopy(ws)
    timely["args"][1] = val(ws, "sent")                         # the timer's time written as the send's

    # ---- origin_acked by itself: the HAVE grows, to a mesh of two or more, and a peer is announced
    def acks_alone(d):
        return (plain(d, "origin_acked") and ent(d, "origin", "writes") is not None and "mesh" in names(d)
                and len(d["tape"][names(d).index("mesh")][2]) >= 2 and "announce" in d["reached"])
    _, _, oa = first(directed71, acks_alone)
    acked_before = copy.deepcopy(oa)
    ent(acked_before, "origin")[2] |= 1 << oa["args"][1]           # the bit read as acknowledged already

    def at_publish(d):                  # at a node at PUBLISH: entered, nothing done
        return (plain(d, "origin_acked") and node_of(nodes, d)["consts"]["SOURCE_OFFERS"] == "PUBLISH"
                and not d["tape"] and not d["writes"])
    _, _, op = first(directed71, at_publish)

    # ---- free_slot with somebody in line
    def frees(d):
        return plain(d, "free_slot") and names(d) == ["wake"]
    _, _, fs = first(directed71, frees)
    nobody = copy.deepcopy(fs)
    ent(nobody, "waiters")[2] = None
    one = (hdr, nodes)
    return check("§7.1's window", {
        "acquire_slot: a slot, nobody in line, as it is": (alone(*one, aq), 0, None),
        "the count read at the window": (alone(*one, full), 1, "return value"),
        "acquire_slot: first in line, the next woken, as it is": (alone(*one, aw), 0, None),
        "the line read with the peer alone in it": (alone(*one, alone_in_line), 1, "tape"),
        "its write of the count left out": (alone(*one, uncounted), 1, "post"),
        "acquire_slot: another first, the peer joins the line, as it is": (alone(*one, aj), 0, None),
        "the line written as it was read": (alone(*one, not_joined), 1, "post"),
        "acquire_slot at a node with no window, as it is": (alone(*one, au), 0, None),
        "that node's W written as 2": (alone(hdr, line(nodes, au, W=2), au), 1, "return value"),
        "release_unused_slot: the peer leaves the line, as it is": (alone(*one, rl), 0, None),
        # (the state after is then the same either way, the line without the peer: the notes tell it)
        "the line read without the peer": (alone(*one, not_in_line), 1, "footprint, writes"),
        "track_in_flight: a new send, as it is": (alone(*one, tf), 0, None),
        "its timer left off the tape": (alone(*one, no_timer), 1, "tape"),
        "the send read as in flight already": (alone(*one, second), 1, "tape"),
        "window_release: a send in flight released, as it is": (alone(*one, wr), 0, None),
        "the send read as not in flight": (alone(*one, not_sent), 1, "reached"),
        "window_timeout: still in flight, a planned group, as it is": (alone(*one, wt), 0, None),
        "the group's row of planned read as not there": (alone(*one, unplanned), 1, "tape"),
        "window_timeout: a stale timer, as it is": (alone(*one, ws), 0, None),
        "the timer's time written as the send's": (alone(*one, timely), 1, "reached"),
        "origin_acked: the HAVE grows and a mesh peer is announced, as it is": (alone(*one, oa), 0, None),
        "origin read with the chunk acknowledged already": (alone(*one, acked_before), 1, "tape"),
        "its node's SOURCE_OFFERS written as PUBLISH": (alone(hdr, line(nodes, oa, SOURCE_OFFERS="PUBLISH"), oa), 1, "tape"),
        "origin_acked at PUBLISH: nothing, as it is": (alone(*one, op), 0, None),
        "free_slot with somebody in line, as it is": (alone(*one, fs), 0, None),
        "the line read as empty": (alone(*one, nobody), 1, "tape"),
    }, work, head, "sec71")


def stripe_controls(directed54, work, head):
    """Where card 13 is off a node's STRIPE_UPLINK is infinite (two of the record's cells), and a replay that refused
    it would refuse the nodes line, every record with it. That constant alone may be +inf; any other float of the
    line is finite. On directed54's candidates_for_source records."""
    INF = 0x7FF0000000000000

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **consts):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **consts}}]}

    def cfs(d, first_call):
        return d["fn"] == "candidates_for_source" and "raises" not in d and d["tape"] and d["tape"][0][0] == first_call

    hdr, nodes, under = first(directed54, lambda d: cfs(d, "mesh"))                    # the pool is the mesh
    _, _, at = first(directed54, lambda d: cfs(d, "connected_topic_peers"))            # the stripe's pool
    assert node_of(nodes, under)["consts"]["STRIPE_UPLINK"] != INF and node_of(nodes, at)["consts"]["STRIPE_UPLINK"] != INF
    return check("the stripe's threshold where card 13 is off", {
        "candidates_for_source under the stripe's uplink, as it is": (alone(hdr, nodes, under), 0, None),
        "its node's STRIPE_UPLINK written infinite": (alone(hdr, line(nodes, under, STRIPE_UPLINK=INF), under), 0, None),
        "a node at the stripe's uplink, its STRIPE_UPLINK written infinite":
            (alone(hdr, line(nodes, at, STRIPE_UPLINK=INF), at), 1, "tape"),
        "a node's UPLINK written infinite": (alone(hdr, line(nodes, under, UPLINK=INF), under), 1,
                                             "nodes: not a finite float"),
    }, work, head, "stripe")


def sec51p_controls(directed51, work, head):
    """publish, the twin's own, on directed51's records. Each outcome was written before the controls first ran, by
    the replay's order of checks. The chunk publish builds is on the tape whole and with no id at `store` and at its
    `content_id`: most of these alter one member of it."""
    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **consts):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **consts}}]}

    def at(d, name, k=0):               # the place on the tape of the k-th call of that name
        return [j for j, e in enumerate(d["tape"]) if e[0] == name][k]

    def pushes(d):                      # the chunks' enqueues: (peer, index)
        return [(e[1][0], e[1][1][1][1]) for e in d["tape"] if e[0] == "enqueue" and e[1][1][0] == "chunk"]

    hdr, nodes, _ = first(directed51, lambda d: True)

    def ack(d):
        return node_of(nodes, d)["consts"]["SOURCE_OFFERS"] == "ACK" and node_of(nodes, d)["consts"]["R"] == 2

    def two_copies(d):                  # at ACK with R 2: published, a chunk pushed to two peers, a mesh peer left
        if d["fn"] != "publish" or "raises" in d or not ack(d):
            return False
        ps = pushes(d)
        idx = [i for _, i in ps]
        mesh = next((e[2] for e in d["tape"] if e[0] == "mesh"), [])
        return (any(idx.count(i) == 2 for i in idx) and len(d["args"][2]) == d["args"][1][3]
                and any(q not in {p for p, _ in ps} for q in mesh))
    _, _, pb = first(directed51, two_copies)
    st, ci, br, ms = at(pb, "store"), at(pb, "content_id"), at(pb, "block_root"), at(pb, "mark_seen")
    # what each control stands on: the first chunk stored is built, whole and with no id, and its content_id's too
    built = pb["tape"][st][1][2]
    assert built[4] is None and len(built) == 6 and built[5][0] is not None and built[5][1], built
    assert pb["tape"][ci][1][0] == built and st < ci < ms

    def alt(fn):
        d = copy.deepcopy(pb)
        fn(d)
        assert d != pb
        return d

    def data_longer(d): d["tape"][st][1][2][5][2][0] += 1                                   # noqa: E704
    def proof_other(d): d["tape"][st][1][2][5][1][0] = "ab" * 32                             # noqa: E704
    def no_desc(d): d["tape"][st][1][2][5][0] = None                                        # noqa: E704
    def with_id(d): d["tape"][st][1][2][4] = d["tape"][ms][1][0]                             # noqa: E704
    def next_index(d): d["tape"][st][1][1] += 1                                              # noqa: E704
    def other_root(d): d["tape"][br][2] = "cd" * 32                                          # noqa: E704
    def other_cid(d): d["tape"][ci][2] = "ef" * 20                                           # noqa: E704

    def cid_narrow(d):                  # content_id's chunk as it is written outside a publish: narrow, with its id
        d["tape"][ci][1][0] = d["tape"][ci][1][0][:4] + [d["tape"][ms][1][0]]

    def shard_index(d): d["args"][2][0][0] += 100                                            # noqa: E704
    def no_chunk(d): d["args"][1][3] = 0                                                     # noqa: E704

    # the ways out: the group expired, as it is; and that answer turned
    _, _, ex = first(directed51, lambda d: d["fn"] == "publish" and "raises" not in d and d["tape"]
                     and d["tape"][-1][0] == "expired" and d["tape"][-1][2] is True)
    alive = copy.deepcopy(ex)
    alive["tape"][-1][2] = False
    _, _, late = first(directed51, lambda d: d["fn"] == "publish" and "raises" not in d and d["tape"]
                       and d["tape"][-1][0] == "live" and d["tape"][-1][2] is False)
    in_time = copy.deepcopy(late)
    in_time["tape"][-1][2] = True
    return check("§5.1's publish", {
        "a publish with a chunk pushed twice, as it is": (alone(hdr, nodes, pb), 0, None),
        "a stored chunk's data one byte longer": (alone(hdr, nodes, alt(data_longer)), 1, "tape"),
        "a digest of its proof another": (alone(hdr, nodes, alt(proof_other)), 1, "tape"),
        "it stored without its descriptor": (alone(hdr, nodes, alt(no_desc)), 1, "tape"),
        "it stored with its id on it": (alone(hdr, nodes, alt(with_id)), 1, "tape"),
        "it stored under the next index": (alone(hdr, nodes, alt(next_index)), 1, "tape"),
        "the block's root answered as another": (alone(hdr, nodes, alt(other_root)), 1, "tape"),
        "its content_id answered as another": (alone(hdr, nodes, alt(other_cid)), 1, "tape"),
        "its content_id asked of the narrow chunk with its id": (alone(hdr, nodes, alt(cid_narrow)), 1, "tape"),
        "the first shard's index another in the arguments": (alone(hdr, nodes, alt(shard_index)), 1, "tape"),
        "its node's R written as 1": (alone(hdr, line(nodes, pb, R=1), pb), 1, "tape"),
        "its node said to be at PUBLISH": (alone(hdr, line(nodes, pb, SOURCE_OFFERS="PUBLISH"), pb), 1, "tape"),
        "its descriptor written with no chunk": (alone(hdr, nodes, alt(no_chunk)), 1,
                                               "limit: publish of a descriptor of no chunk"),
        "an expired group's publish, as it is": (alone(hdr, nodes, ex), 0, None),
        "that group said not to be expired": (alone(hdr, nodes, alive), 1, "tape"),
        "a publish past its live window, as it is": (alone(hdr, nodes, late), 0, None),
        "that slot said to be live": (alone(hdr, nodes, in_time), 1, "tape"),
    }, work, head, "publish6")


def publish_controls(directed7p, hand5_publish, work, head):
    """next_to_send's line at SOURCE_OFFERS = PUBLISH and §5.1's origin_written (v0.10.4), the twin's own, on
    directed7p's records and the small traced cell's (hand5-publish). Each outcome was written before the controls
    first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def plain(d, fn):
        return d["fn"] == fn and "raises" not in d

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **consts):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **consts}}]}

    def origin_of(d, where):
        return [e for e in d[where] if e[0] == "origin"]

    # ---- next_to_send at PUBLISH: a chunk leaves, its bit joins the node's HAVE, the HAVE goes to a mesh of two
    def writes_first(d):
        return (plain(d, "next_to_send") and "origin_written" in d["reached"] and origin_of(d, "writes")
                and "mesh" in names(d) and len(d["tape"][at(d, "mesh")][2]) >= 2)
    hdr, nodes, nw = first(directed7p, writes_first)
    assert node_of(nodes, nw)["consts"]["SOURCE_OFFERS"] == "PUBLISH"
    unwritten = copy.deepcopy(nw)
    unwritten["writes"] = [e for e in unwritten["writes"] if e[0] != "origin"]
    retable(unwritten)

    # ---- origin_written by itself: the HAVE grows, to a mesh of two or more
    def grows(d):
        return (plain(d, "origin_written") and origin_of(d, "writes") and "mesh" in names(d)
                and len(d["tape"][at(d, "mesh")][2]) >= 2)
    _, _, ow = first(directed7p, grows)
    rev, there = copy.deepcopy(ow), copy.deepcopy(ow)
    rev["tape"][at(ow, "mesh")][2].reverse()
    origin_of(there, "reads")[0][2] |= 1 << ow["args"][0][1]   # the bit read as there already

    def not_ours(d):                    # a group the node does not publish, with a mesh: nothing asked, nothing done
        return (plain(d, "origin_written") and not d["tape"] and origin_of(d, "reads")
                and origin_of(d, "reads")[0][2] is None)
    _, _, no = first(directed7p, not_ours)
    ours = copy.deepcopy(no)
    origin_of(ours, "reads")[0][2] = 0                          # the group read as one it publishes, no bit yet

    # ---- the small traced cell at PUBLISH: a write that runs origin_written
    def in_cell(d):
        return plain(d, "next_to_send") and "origin_written" in d["reached"] and origin_of(d, "writes")
    hdr_c, nodes_c, hc = first(hand5_publish, in_cell)
    not_reached = copy.deepcopy(hc)
    not_reached["reached"] = [x for x in hc["reached"] if x != "origin_written"]
    one = (hdr, nodes)
    return check("next_to_send at PUBLISH and §5.1's origin_written", {
        "next_to_send at PUBLISH: a chunk leaves and the HAVE grows, as it is": (alone(*one, nw), 0, None),
        "its node's SOURCE_OFFERS written as ACK": (alone(hdr, line(nodes, nw, SOURCE_OFFERS="ACK"), nw), 1, "tape"),
        "its write of origin left out": (alone(*one, unwritten), 1, "post"),
        "origin_written: the HAVE grows, as it is": (alone(*one, ow), 0, None),
        "the mesh's order reversed": (alone(*one, rev), 1, "tape"),
        "origin read with the chunk's bit there already": (alone(*one, there), 1, "tape"),
        "origin_written: not a group the node publishes, as it is": (alone(*one, no), 0, None),
        "that group read as one it publishes": (alone(*one, ours), 1, "tape"),
        "hand5-publish: a write that runs origin_written, as it is": (alone(hdr_c, nodes_c, hc), 0, None),
        "its reached without origin_written": (alone(hdr_c, nodes_c, not_reached), 1, "reached"),
    }, work, head, "publish")


def sec54_controls(directed54, work, head):
    """forward, candidates_for_source and on_mesh_join (the twin's own; the stock cache's put and the store's keys on
    the tape), on directed54's records. Each outcome was written before the controls first ran."""
    def at(d, name, k=0):
        return [j for j, t in enumerate(d["tape"]) if t[0] == name][k]

    def names(d):
        return [t[0] for t in d["tape"]]

    def plain(d, fn):
        return d["fn"] == fn and "raises" not in d

    def node_of(nodes, d):
        (own,) = [e for e in nodes["nodes"] if d["n"] in e["n"]]
        return own

    def line(nodes, d, **consts):
        own = node_of(nodes, d)
        return {"nodes": [{**copy.deepcopy(own), "n": [d["n"]], "consts": {**own["consts"], **consts}}]}

    def chunk_enq(d):                   # the enqueues of the chunk itself: the pushes, in order
        return [j for j, t in enumerate(d["tape"]) if t[0] == "enqueue" and t[1][1][0] == "chunk"]

    def offers(d):                      # the enqueues of an IHAVE: the announcements
        return [j for j, t in enumerate(d["tape"]) if t[0] == "enqueue" and t[1][1][0] != "chunk"]

    # ---- forward with a draw: a push the queue took, a candidate offered the chunk, the sender in the mesh
    def draws(d):
        if not plain(d, "forward") or "sample_without_replacement" not in names(d):
            return False
        return (chunk_enq(d) and all(d["tape"][j][2] is True for j in chunk_enq(d)) and offers(d)
                and d["args"][1] in d["tape"][at(d, "mesh")][2])
    hdr, nodes, fw = first(directed54, draws)
    no_put, fewer_cands, refused, unnoted, other_sender = (copy.deepcopy(fw) for _ in range(5))
    del no_put["tape"][at(fw, "gossip_put")]
    offered = fw["tape"][offers(fw)[0]][1][0]                   # a candidate that was offered the chunk
    fewer_cands["tape"][at(fw, "mesh", 1)][2].remove(offered)   # the mesh's second answer without it
    refused["tape"][chunk_enq(fw)[0]][2] = False
    q0 = fw["tape"][chunk_enq(fw)[0]][1][0]                     # the first peer pushed
    unnoted["writes"] = [e for e in unnoted["writes"] if not (e[0] == "pushed" and e[1][0] == q0)]
    retable(unnoted)
    other_sender["args"][1] = q0                                # the sender said to be that peer: no candidate, then

    # ---- forward with a push refused; with no budget
    def owed(d):
        return plain(d, "forward") and chunk_enq(d) and d["tape"][chunk_enq(d)[0]][2] is False
    _, _, fr = first(directed54, owed)
    taken = copy.deepcopy(fr)
    taken["tape"][chunk_enq(fr)[0]][2] = True

    def spent(d):                       # R_NODE holders or more, and somebody to offer the chunk to
        return plain(d, "forward") and not chunk_enq(d) and offers(d) and d["n"] == 2 and (
            "sample_without_replacement" not in names(d) or d["tape"][at(d, "sample_without_replacement")][1][1] == 0)
    _, nodes_b, fb = first(directed54, spent)

    # ---- candidates_for_source: the mesh with a holder; every connected peer
    def holder(d):
        return (plain(d, "candidates_for_source") and "mesh" in names(d)
                and len(d["ret"]) < len(d["tape"][at(d, "mesh")][2]) and d["ret"])
    _, _, cm = first(directed54, holder)
    unheld, striped = copy.deepcopy(cm), None
    h = next(q for q in cm["tape"][at(cm, "mesh")][2] if q not in cm["ret"])
    next(e for e in unheld["reads"] if e[0] == "peer_has" and e[1][0] == h)[2] = None
    own = node_of(nodes, cm)
    striped = line(nodes, cm, UPLINK=own["consts"]["STRIPE_UPLINK"])

    def connected(d):
        return plain(d, "candidates_for_source") and "connected_topic_peers" in names(d) and d["ret"]
    _, _, cc = first(directed54, connected)
    one_less = copy.deepcopy(cc)
    one_less["tape"][at(cc, "connected_topic_peers")][2].remove(cc["ret"][-1])

    # ---- on_mesh_join: two groups offered or more; an expired or dropped group passed over; nothing held
    def keys_of(d):
        return [t for t in d["tape"] if t[0] == "keys" and t[1] == "chunks"]

    def two(d):
        return plain(d, "on_mesh_join") and len(offers(d)) >= 2 and all(d["tape"][j][2] is True for j in offers(d))
    _, _, mj = first(directed54, two)
    reversed_, gone, less = (copy.deepcopy(mj) for _ in range(3))
    keys_of(reversed_)[0][3].reverse()
    g0 = mj["tape"][offers(mj)[0]][1][1][0][1][0][1]            # the first group offered
    next(t for t in gone["tape"] if t[0] == "expired" and t[1] == [g0])[2] = True
    ks = next(t for t in keys_of(less) if t[2] == [g0])
    b0 = mj["tape"][offers(mj)[0]][1][1][0][1][0][2]            # the bits offered of it
    ks[3].remove(next(j for j in ks[3] if b0 >> j & 1))

    def dropped(d):
        return (plain(d, "on_mesh_join") and any(e[0] == "state" and e[2] == "INVALID" for e in d["reads"])
                and not offers(d) and "wake" not in names(d))
    _, _, md = first(directed54, dropped)
    alive = copy.deepcopy(md)
    next(e for e in alive["reads"] if e[0] == "state" and e[2] == "INVALID")[2] = "COMPLETE"
    _, _, mn = first(directed54, lambda d: plain(d, "on_mesh_join") and keys_of(d) and keys_of(d)[0][3] == [])
    one = (hdr, nodes)
    return check("forward, candidates_for_source and on_mesh_join", {
        "forward with a draw, a push and an offer, as it is": (alone(*one, fw), 0, None),
        "its gossip_put taken off the tape": (alone(*one, no_put), 1, "tape"),
        "the mesh's second answer without a candidate that was offered": (alone(*one, fewer_cands), 1, "tape"),
        "its first push said to be refused": (alone(*one, refused), 1, "tape"),
        "the write of pushed for its first push left out": (alone(*one, unnoted), 1, "post"),
        "its sender written as the first peer pushed": (alone(*one, other_sender), 1, "tape"),
        "forward with a push refused and owed, as it is": (alone(*one, fr), 0, None),
        "that push said to be taken": (alone(*one, taken), 1, "tape"),
        "forward with no budget, as it is": (alone(*one, fb), 0, None),
        "its node's R_NODE written as 9": (alone(hdr, line(nodes_b, fb, R_NODE=9), fb), 1, "tape"),
        "candidates_for_source in the mesh with a holder, as it is": (alone(*one, cm), 0, None),
        "the holder's peer_has read as missing": (alone(*one, unheld), 1, "return"),
        "its node's UPLINK written as the stripe's": (alone(hdr, striped, cm), 1, "tape"),
        "candidates_for_source among every connected peer, as it is": (alone(*one, cc), 0, None),
        "connected_topic_peers' answer without its last candidate": (alone(*one, one_less), 1, "return"),
        "on_mesh_join with two groups offered, as it is": (alone(*one, mj), 0, None),
        "the store's groups in the other order": (alone(*one, reversed_), 1, "tape"),
        "the first group offered said to have expired": (alone(*one, gone), 1, "tape"),
        "that group's indices without one that was offered": (alone(*one, less), 1, "tape"),
        "on_mesh_join that passes over a dropped group and offers nothing, as it is": (alone(*one, md), 0, None),
        "the dropped group's state read as COMPLETE": (alone(*one, alive), 1, "tape"),
        "on_mesh_join with nothing held, as it is": (alone(*one, mn), 0, None),
    }, work, head, "sec54")


def sec1_controls(directed1, work, head):
    """The controls on directed1's records: a question is asked with the arguments the document's line gives it; a
    question that raises is on the tape as one; an integer that can be negative is written without a sign. Each
    outcome was written before the controls first ran."""
    def asks(name):
        return lambda d: "raises" not in d and any(t[0] == name for t in d["tape"])
    hdr, nodes, gid = first(directed1, lambda d: d["fn"] == "group_id" and asks("sha256")(d))
    at = next(k for k, t in enumerate(gid["tape"]) if t[0] == "sha256")
    st = next(k for k, t in enumerate(gid["tape"]) if t[0] == "serialize")
    prefix = copy.deepcopy(gid)
    prefix["tape"][at][1][0] = "03" + prefix["tape"][at][1][0][2:]          # the hash asked of 0x03 ‖ …
    serial = copy.deepcopy(gid)
    serial["tape"][st][2] = ("00" if serial["tape"][st][2][:2] != "00" else "01") + serial["tape"][st][2][2:]
    other_desc = copy.deepcopy(gid)
    other_desc["tape"][st][1][0][3] += 1                                    # serialize asked of another count
    _, _, slot = first(directed1, lambda d: d["fn"] == "group_key" and asks("sha256")(d)
                       and d["tape"][0][1][0][-16:] != "".join(reversed([d["tape"][0][1][0][-16:][i:i + 2] for i in range(0, 16, 2)])))
    be = copy.deepcopy(slot)
    b0 = be["tape"][0][1][0]
    be["tape"][0][1][0] = b0[:-16] + "".join(reversed([b0[-16:][i:i + 2] for i in range(0, 16, 2)]))
    _, _, kk = first(directed1, lambda d: d["fn"] == "K" and "raises" not in d)
    more = copy.deepcopy(kk)
    more["ret"] += 1
    _, _, neg = first(directed1, lambda d: d["fn"] == "segment_length" and isinstance(d.get("ret"), list))
    unsigned = copy.deepcopy(neg)
    unsigned["ret"] = neg["ret"][1]
    zero = copy.deepcopy(neg)
    zero["ret"] = ["-", 0]
    _, _, over = first(directed1, lambda d: d["fn"] == "group_id" and d.get("raises") == "OverflowError")
    answered = copy.deepcopy(over)
    answered["tape"][-1][2] = "00"                                          # the question that raised, answered
    _, _, built = first(directed1, lambda d: d["fn"] == "build_group" and "raises" not in d and len(d["tape"]) > 3)
    fewer = copy.deepcopy(built)
    del fewer["tape"][-1]
    # §2's message_id: content_id is a question at every call, its answer the chunk's own
    _, _, mid = first(directed1, lambda d: d["fn"] == "message_id" and "raises" not in d)
    other_cid = copy.deepcopy(mid)
    c = other_cid["tape"][0][2]
    other_cid["tape"][0][2] = ("00" if c[:2] != "00" else "01") + c[2:]
    other_ret = copy.deepcopy(mid)
    i8 = other_ret["ret"][64:72]
    other_ret["ret"] = other_ret["ret"][:64] + ("ff" if i8[:2] != "ff" else "fe") + other_ret["ret"][66:]
    no_ask = copy.deepcopy(mid)
    no_ask["tape"] = []
    one = (hdr, nodes)
    return check("§1", {
        "message_id, as it is": (alone(*one, mid), 0, None),
        "message_id: content_id's answer not the chunk's": (
            alone(*one, other_cid), 1, "tape: content_id: its answer: not the last 20 bytes of the id its chunk carries"),
        "message_id: its return value of another index": (alone(*one, other_ret), 1, "return value"),
        "message_id: content_id not on its tape": (alone(*one, no_ask), 1, "tape: content_id"),
        "group_id, as it is": (alone(*one, gid), 0, None),
        "group_id: sha256 asked of 0x03 and the rest": (alone(*one, prefix), 1, "tape: sha256"),
        "group_id: serialize's answer another": (alone(*one, serial), 1, "tape: sha256"),
        "group_id: serialize asked of another count": (alone(*one, other_desc), 1, "tape: serialize"),
        "group_key: the slot's eight bytes in the other order": (alone(*one, be), 1, "tape: sha256"),
        "K, as it is": (alone(*one, kk), 0, None),
        "K: one more": (alone(*one, more), 1, "return value"),
        "segment_length: a negative length, as it is": (alone(*one, neg), 0, None),
        "segment_length: that length without its sign": (alone(*one, unsigned), 1, "return value"),
        "segment_length: minus zero": (alone(*one, zero), 1, "not an integer of a record: minus zero"),
        "group_id: serialize raises, as it is": (alone(*one, over), 0, None),
        "group_id: the question that raised, answered": (alone(*one, answered), 1, "the Python raises OverflowError"),
        "build_group, as it is": (alone(*one, built), 0, None),
        "build_group: its last question not on the tape": (alone(*one, fewer), 1, "tape: merkle_proof"),
    }, work, head, "sec1")


def header3_controls(hdr, hand_hdr, work, directed, directed44):
    """header3.py's check of a trace's first two lines: the hand cell's pass, §6.1 alone and whole; a content
    line of another tool, another document or another file of the toy, one with a file more, no content line,
    format 6, a cell that claims the whole state and a list of functions traced that is neither must be refused,
    each for its reason; the directed traces' headers pass, and are refused where they do not claim the whole
    state."""
    toy = layout.toy()

    def variant(**change):
        out = copy.deepcopy(hdr)
        out["header"].update(change)
        return out

    def other(name, sha="0" * 64):      # the content line with one file's bytes another's, or one file more
        c = json.loads(content_line())
        c["content"]["files"][name] = sha
        return [RAW, content.line(c)[:-1], hdr]

    T = content.TOOLS
    cases = {   # name -> (the header line, or the file's lines; whether it must pass; the words of its refusal)
        "the hand cell's header, §6.1 alone": (hdr, True, None),
        "the hand cell's header, the whole block": (hand_hdr, True, None),
        "a cell that says it holds the whole state": (variant(whole=True), False, "whole: True"),
        "another trace3.py": (other(f"{T}/trace3.py"), False, f"content: not this tree's: {T}/trace3.py: other bytes"),
        "another footprint.py": (other(f"{T}/footprint.py"), False, f"content: not this tree's: {T}/footprint.py: other bytes"),
        "another gen/schema.py": (other(f"{T}/gen/schema.py"), False, f"content: not this tree's: {T}/gen/schema.py: other bytes"),
        "another directed41.py": (other(f"{T}/directed41.py"), False, f"content: not this tree's: {T}/directed41.py: other bytes"),
        "another protocol.md": (other("protocol.md"), False, "content: not this tree's: protocol.md: other bytes"),
        "another toy/node.py": (other("toy/node.py"), False, "content: not this tree's: toy/node.py: other bytes"),
        "a module more in the toy": (other("toy/zz.py"), False, "content: not this tree's: toy/zz.py: only in the second"),
        "no content line": ([RAW, hdr, hdr], False, "content: the first line is no content line"),
        "format 6": (variant(format=6), False, "format: 6, must be 7"),
        "another table among the foreign": (variant(foreign=["queue"]), False, "foreign: ['queue']"),
        "traced, neither the block nor §6.1 alone": (variant(traced=["may_ask"]), False, "traced: ['may_ask']"),
    }
    for tag, path in (("§6.1's", directed), ("§4.4's", directed44)):
        dh = load(path)[0]
        nw = copy.deepcopy(dh)
        nw["header"]["whole"] = False
        cases[f"{tag} directed trace's header"] = (dh, True, None)
        cases[f"{tag} directed trace, not holding the whole state"] = (nw, False, "whole: False")
    bad = 0
    for name, (h, must, words) in cases.items():
        f = work / f"header3-{re.sub(r'[^A-Za-z0-9_.]+', '-', name)}.jsonl"
        write(f, h if isinstance(h, list) else [h])
        why = header3.check(toy, f)
        ok = (not why) == must and (must or (len(why) == 1 and words in why[0]))     # refused for its one reason
        bad += not ok
        print(f"header3, {name}: {'passes' if not why else 'refused: ' + '; '.join(why)[:160]}, "
              f"must {'pass' if must else 'be refused'}{'' if ok else '  <-- FAIL'}")
    print("ok: every header3 control as it must be" if not bad else f"{bad} header3 controls wrong")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
