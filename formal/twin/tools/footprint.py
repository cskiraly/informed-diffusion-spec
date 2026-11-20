#!/usr/bin/env python3
"""Recording views of the toy's state tables: what a call reads and writes, entry by entry.

A table of a node's namespace is replaced by a View of it. The toy's own container stays the stored object and
does every operation; the view logs the entry touched, while its Recorder is on, and is transparent while it
is off.

An entry is a table's name and a path of keys, down to the table's depth (its schema line). Its value is what
the schema's encoder makes of the stored object: a JSON value, or None for a missing entry and for an empty one
(§8.1: a missing entry reads as empty; before v0.10 the toy's AutoMap made one on a read, and since v0.10 a read
allocates nothing: a missing key reads as a detached entry, which joins its map at its first write, bits.py).

Two kinds of table:
- own: the block's own state. A call's footprint is its `reads` (the entries whose first touch in the call was a
  read, with their values before the call), its `scans` (levels read as a whole: every entry under one is in
  `reads`) and its `writes` (below). `rest` is entries the call did not read, as they were before it: the ones it
  wrote without reading, and, for a record of the whole state, every entry it never touched.
- foreign: another section's state that the block reads directly (the twin asks it through its interface). Each
  read goes on the call's tape, in order, with the value read. A write of one through a view is refused.

What is logged, exactly (the contract; footprint_test.py has a case for each line):
- **A read** is an access through a view to an entry: `t[k]`, `t.get(k)`, `k in t`, `t.pop(k)` (whether or not
  it finds the entry),
  `t.setdefault(k, v)` (and a write too where the entry was missing), or a level read as a whole (iteration,
  `len`, a truth test, `keys`, `values`, `items`, and `==`, which reads both sides where both are views).
- **A write** is an assignment, a deletion or a `pop` that finds its entry, through a view, a set's `add`,
  `discard` or `remove`, a
  level assigned, deleted, popped or cleared as a whole (every entry under it before, and every entry under it
  after; an entry an assignment brings is noted at the assignment, as missing before it, so that a later touch in
  the same call does not take the assigned value for the value before the call), or an entry whose value at the
  end of the call is not its value at its first touch: so a value changed
  in place (`offered[p][g].set(i)`, `offers[a].append(p)`) is a write of its entry. A change in place that leaves
  the value as it was (setting a bit that is set) is not a write: no record distinguishes it from none.
- **A pop that finds nothing is a read, and no write**, for every table, in the block and in a callee: nothing
  changed, and that the entry is not there is what the code learned. For an entry, "nothing" is the value a
  record holds: missing, or there and empty (§8.1: the Python then removes an empty object, which no record
  holds). For a level popped whole (`tied.pop(root, {})`, `tried.pop(a, None)`): no entry under it has a value
  and, in a table that keeps its rows, its row is not there; the level is read as a whole (and its row, there),
  and nothing is written. A row that is there with nothing under it is an entry of its own, and its pop a write.
- **An operation a view does not know raises** while the recorder is on. That holds for operations on a view:
  on a table, or on a level of one. A value handed out (a bitmap, a list, a set of peers, a queue) is the toy's
  own object, and what is done to it is seen only as a change of its entry's value.
- **Not logged, and not refused:** an access to a container or a value obtained while the recorder was off and
  kept; a change in place of a foreign table's value; a second path to one object; and whether a level that is
  there is there (`t.get(k)` of such a row hands out its view and logs nothing, so `t.get(k) is None` tells a
  row that is there from a missing one without a read; a missing row is logged, as read whole and empty).
  §6.1's code does none of these (its functions hold no state between calls, the toy makes one container per
  key, and it never asks whether a row is there).
- **A call the block makes on the tape** keeps its own log while it runs (`begin_callee`, `end_callee`): its
  `cr`, the own entries whose first touch in it was a read, with their values then, and its `cw`, the ones it
  wrote or changed in place, with their values at its end. An entry a callee touched first in the call is in the
  call's `rest` with its value before the call, and not among its reads; the call's `writes` hold its callees'
  writes too. In a callee another section's table is transparent: nothing on the tape, nothing refused. An
  operation the views do not know, on an own table, raises there as in the block, but for the attribute reads
  of CALLEE_ATTRS.
- **Another section's level iterated by the block** puts its keys on the tape, in the order the Python iterated
  them: ["keys", table, path, [key, ...]]. Its length, a truth test, its values or items are refused, as before.
- **A callee's order is not the record's:** its `cr` and `cw`, and the entries it touched first in the call, go into
  the record sorted by [table, path], whatever order the callee touched them in (a set of keys iterates in an order
  that changes with Python's hash seed: claim_group's). The block's own entries keep their order of first touch.
- **A block's read of an entry a callee read first,** unchanged since, is a read of the block's, with its value
  before the call, and not in `rest`. One a callee wrote first is written before, as at the replay: no read.
- **Presence (a table that keeps its rows: `tied`).** Each row that is there is an entry of its own, a
  path of fewer keys than the table's, whose value is True; a bitmap there and empty is 0, not missing. An access
  to an entry observes the rows above it: an observed row is no read, but its change by the end of the call (made
  or removed) is a write, and its value before the call is in `rest`, as a callee's touch is; read by the block
  later, unchanged, it is the block's read. A level read as a whole reads its row too (`k in tied`), and a level
  assigned or removed whole writes its row. Rows above an entry are observed, not read, because the Python's
  `tied[r][p][g]` hands out a detached entry where a row is missing, and its outcome does not depend on it.
- **A row made in the call:** every entry under it is written, each missing before the call, in a callee's `cw`
  and in the record. So a new PeerQueue's other lane is there, as the toy's is, and a later touch of it is no
  value "before the call".
- **A level held as attributes (the toy's `PeerQueue`, whose two lanes are `urgent` and `normal`).** A container
  of a type in ATTR_LEVELS has those attributes as its keys: reading one through a view (`queue[p].normal`) is a
  read of that entry, assigning one (`queue[p].normal = [...]`) a write, and a change of the list in place
  (`.append`, an entry's IWANT changed) a write of its entry by its value at the end, as for any value. Any other
  attribute of it is an operation the views do not know.
- **A table whose order is asked (`ordered`: `list(queue)`).** The block iterating its top level reads it as a
  whole, as any own table, and also puts its keys on the tape in the Python's order, as for another section's
  level: the twin's rows are the domain, the order is the node's. In a callee, only the read.
- **Ordered levels below the top:** a table's `ordered_levels` are depths whose order the twin asks too. The
  block iterating one through a view (`iter`, `keys()`, `items()`) puts its keys on the tape. A pop of a level
  above one hands out the toy's own object, whose iteration the views do not see: so the pop puts the order of
  every ordered level under it on the tape (`order_tree`), outer first, as the Python will iterate them.
- **A list of the namespace as a table of one entry (§6.4's `pace_queue`).** The list is the value of the one
  entry `jobs`, held as a lane is held by its PeerQueue (`ListHolder`). The block sees a `ListView`: a truth
  test, `len` and iteration are reads of the entry; `append` and `pop(0)` a read and a write (the new list is
  made from the old). A callee may also `clear` and `extend` it (the toy's link close). Any other use raises
  while the recorder is on.
- **A table whose values' order is asked (`values_ordered`: `held_back.values()`).** The block's `t.values()`
  reads the table as a whole and puts its keys on the tape in the Python's order, as an ordered level's iteration
  does. Other tables' `values()` put nothing there (`tied.values()`, read by `any`).
- **What checks the log, and how far.** In a trace of the whole state the log is compared with the tables
  themselves at the two ends of each call (`snapshot`, used by trace3.py's `account`): the tables before must be
  the reads and the rest, and the tables after, those with the writes applied. That is a check of the net change
  to the own tables. It does not see a read that was not logged, a write undone within the call, or a foreign
  value changed in place.
"""
import collections
import json

ABSENT = object()
# the containers that hold their keys as attributes (the toy's PeerQueue: its lanes), by type: the attributes'
# names, in order. Filled by the tracer, which knows the toy (trace3.py)
ATTR_LEVELS = {}
# the methods of such a container that read some of its attributes, by type: the method's name, and the attributes
# it reads (the toy's `PeerQueue.has_chunks`, next_to_send's `q.has_chunks()`: the normal lane). A call through a
# view is a read of each. Filled by the tracer
ATTR_READS = {}
# A row made in a call (missing at its first touch, there at the end) brings every entry under it, each missing
# before the call: they are written, so that a callee's cw holds them all and a later touch of one is not taken
# for its value before the call. The control (footprint_test.py --broken-made-rows) turns it off.
MADE_ROWS = True
# Every entry in a callee's `cw` is a write of the call too, whatever the block does to it afterwards. A change in
# place by a callee that the block then undoes (next_to_send's owed answer, enqueued by a callee and popped back by
# the block) ends at its value before the call, and was not among the call's writes, though the cw, which the
# twin applies, writes it. The control (footprint_test.py --broken-cw-writes) turns it off.
CW_WRITES = True
# A pop that finds nothing is a read and no write (the contract's line above). The control (footprint_test.py
# --broken-pop-miss) turns it off: every pop is then a write too, also of a missing entry.
POP_MISS_READ = True
# the attribute reads of an own table that a callee may make, unlogged: the toy's `listed` reads the count
# that `offers` keeps of the lists each announcer is in. Its answer is on the tape, trusted as it was before
CALLEE_ATTRS = {("offers", "listed")}


def _one_order(items, key):
    """A callee's log, and the entries it touched first in the call, in one order whatever the callee iterates: a
    set of keys iterates in an order that changes with Python's hash seed (claim_group's index of ask keys)."""
    return sorted(items, key=key)


class Table:
    """A schema line: the table's name, its kind, how its keys and its value are written. A table that keeps its
    rows (`rows`, presence) has an entry for each row that is there, at each level above the last: a
    path of fewer keys than the table's, whose value is True, or None where the row is not there."""

    def __init__(self, name, keys, value, foreign=False, rows=False, ordered=False, ordered_levels=(),
                 values_ordered=False, presence_in=False):
        self.name, self.keys, self.value, self.foreign, self.rows = name, keys, value, foreign, rows
        self.presence_in = presence_in  # `planned`: `k in t` at a row's level reads that row's presence
        #                                 alone, its own entry, and not the row whole (a table that keeps its rows)
        self.values_ordered = values_ordered    # `t.values()` of the block puts the keys on the tape too
        self.ordered = ordered          # its top level's order is asked: its keys on the tape where the block iterates it
        self.ordered_levels = tuple(ordered_levels)     # deeper levels whose order is asked too
        self.depth = len(keys)

    def path(self, p):                  # one element per level
        return [enc(k) for enc, k in zip(self.keys, p)]


def _peek(raw, k):
    """The stored object under k, without the toy's allocation on read."""
    names = ATTR_LEVELS.get(type(raw))
    if names is not None:                           # a PeerQueue: its lanes are its keys
        return getattr(raw, k) if k in names else ABSENT
    if isinstance(raw, (set, frozenset)):
        return True if k in raw else ABSENT
    if isinstance(raw, dict):
        return dict.get(raw, k, ABSENT)
    d = getattr(raw, "_d", None)                    # the toy's LazyMap
    if isinstance(d, dict):
        return d.get(k, ABSENT)
    raise TypeError(f"footprint: a container of a kind it does not know: {type(raw).__name__}")


def _keys(raw):
    names = ATTR_LEVELS.get(type(raw))
    if names is not None:
        return list(names)
    if isinstance(raw, (set, frozenset)):   # a set iterates in an order that changes from process to process
        return sorted(raw)                  #   (Python's hash seed): a record must not depend on it
    if isinstance(raw, dict):
        return list(dict.keys(raw))
    d = getattr(raw, "_d", None)
    if isinstance(d, dict):
        return list(d)
    raise TypeError(f"footprint: a container of a kind it does not know: {type(raw).__name__}")


class Recorder:
    """One node's log for the call in progress."""

    def __init__(self):
        self.on = False
        self.tape = None                # the call's tape, for the reads of foreign tables
        self.callee = None              # a call the block makes on the tape, in progress: its own log
        self.roots = {}                 # table name -> (Table, raw container)
        self.clear()

    def clear(self):
        self.pre = {}                   # entry -> its encoded value at its first touch in the call
        self.first = {}                 # entry -> "r" or "w": its first touch
        self.wrote = set()              # entries written explicitly
        self.bread = set()              # entries touched first by a callee or observed, and read by the block after
        self.scans = []                 # (table name, prefix) levels read as a whole, in order
        self.wlevels = []               # (table name, prefix) levels assigned as a whole
        self.callee = None

    # ---- reading an entry's stored value, without the views
    def _raw_at(self, t, prefix):
        raw = self.roots[t.name][1]
        for k in prefix:
            raw = _peek(raw, k)
            if raw is ABSENT:
                return ABSENT
        return raw

    def value(self, t, p):
        if len(p) < t.depth:                        # a row (presence): there, or not
            return True if self._raw_at(t, p) is not ABSENT else None
        raw = self._raw_at(t, p[:-1])
        if raw is ABSENT:
            return None
        v = _peek(raw, p[-1])
        return None if v is ABSENT else t.value(v)

    def _under(self, t, prefix):
        """Every entry now stored under a level."""
        raw = self._raw_at(t, prefix)
        if raw is ABSENT:
            return []
        if len(prefix) + 1 == t.depth:
            return [prefix + (k,) for k in _keys(raw)]
        out = []
        for k in _keys(raw):
            if t.rows:                              # a row that is there is an entry of its own
                out.append(prefix + (k,))
            out.extend(self._under(t, prefix + (k,)))
        return out

    # ---- the log
    def _touch(self, t, p, rw):
        if t.rows:                          # presence: the rows above an entry, observed, so that one the access
            for j in range(1, len(p)):      #   makes or removes shows as a write
                self._touch1(t, p[:j], "o")
        self._touch1(t, p, rw)

    def _before(self, t, p, *pres):
        """An entry's value at its first touch in a log, for that log's "before". Under a row that was missing at
        the row's own first touch in one of the logs `pres`, the entry was missing too, whatever it holds now: the
        row was made since, and its other entries with it (within one log too: origin_acked, one callee, makes a
        peer's queue through the urgent lane and then reads its normal lane; without this, that lane would be
        "empty before", which a trace of the whole state refuses)."""
        if t.rows and MADE_ROWS:
            for j in range(1, len(p)):
                row = (t.name, p[:j])
                if any(row in pre and pre[row] is None for pre in pres):
                    return None
        return self.value(t, p)

    def _touch1(self, t, p, rw):
        """One entry touched: "r" a read, "w" a write, "o" observed (a row above an entry touched: not a read, but
        a change of it by the end of the call is a write)."""
        e = (t.name, p)
        c = self.callee
        if c is not None:                   # a callee's: in its own log, and in the call's as touched by a callee
            f = c["first"].get(e)
            if f is None:
                c["first"][e] = rw
                c["pre"][e] = self._before(t, p, c["pre"])
            elif f == "o" and rw != "o":    # observed so far: a read of the value still observed is its first read
                c["first"][e] = "r" if rw == "r" and self.value(t, p) == c["pre"][e] else "w"
            if rw == "w":
                c["wrote"].add(e)
        call = "c" if c is not None or rw == "o" else rw    # the call's log: a callee's touch and an observation
        f = self.first.get(e)                               #   are neither its reads nor its writes
        if f is None and c is not None:     # a callee's first touch: into the call's log at the callee's end, in one
            if e not in c["calls"]:         #   order whatever the callee iterates (a set of keys, in claim_group)
                c["calls"][e] = self._before(t, p, c["pre"], c["calls"], self.pre)
        elif f is None:
            self.first[e] = call
            self.pre[e] = self._before(t, p, self.pre)
        elif f == "c" and call == "r" and e not in self.wrote and self.value(t, p) == self.pre[e]:
            self.bread.add(e)               # the block reads an entry a callee read, or one observed, first, and
                                            #   nothing changed: a read of the block's, with the value before the
                                            #   call. One a callee wrote is written before, as at the replay
        if call == "w" or (c is not None and e in c["wrote"]):
            self.wrote.add(e)

    def read(self, t, p):
        if t.foreign:
            if self.callee is None:         # in a callee, another section's table is the callee's business
                self.tape.append(["read", t.name, t.path(p), self.value(t, p)])
        else:
            self._touch(t, p, "r")

    def write(self, t, p):
        if t.foreign:
            if self.callee is None:
                raise TypeError(f"footprint: the block writes {t.name}{list(p)}, a table of another section")
            return
        self._touch(t, p, "w")

    def scan(self, t, prefix):
        if t.foreign:
            if self.callee is None:
                raise TypeError(f"footprint: the block scans {t.name}{list(prefix)}, a table of another section")
            return
        if self.callee is None and (t.name, prefix) not in self.scans:     # the block's own levels
            self.scans.append((t.name, prefix))
        if t.rows and prefix:               # a row read as a whole: whether it is there is read too
            self._touch(t, prefix, "r")
        for p in self._under(t, prefix):
            self._touch(t, p, "r")

    def keys(self, t, prefix, ks):
        """Another section's level iterated by the block, or an own table's level whose order is asked (`ordered`:
        `list(queue)`; `ordered_levels`): its keys, in the order the Python iterated them, on the tape."""
        enc = t.keys[len(prefix)]
        self.tape.append(["keys", t.name, t.path(prefix), [enc(k) for k in ks]])
        return ks

    def order_tree(self, t, prefix, raw):
        """A level popped whole by the block, whose levels below are ordered (`tied.pop(root)`): the order of each
        ordered level under it, as the Python will iterate the object the pop hands out, on the tape, outer first. A
        missing level gives nothing."""
        d = len(prefix)
        if raw is ABSENT or d >= t.depth:
            return
        ks = _keys(raw)
        if d in t.ordered_levels:
            self.keys(t, prefix, ks)
        if d + 1 < t.depth:
            for k in ks:
                self.order_tree(t, prefix + (k,), _peek(raw, k))

    def write_level(self, t, prefix):
        """A whole level assigned or removed: every entry under it before, and (at the end) after."""
        if t.foreign:
            if self.callee is None:
                raise TypeError(f"footprint: the block writes {t.name}{list(prefix)}, a table of another section")
            return
        if t.rows and prefix:               # the row itself, assigned or removed
            self._touch(t, prefix, "w")
        for p in self._under(t, prefix):
            self._touch(t, p, "w")
        self.wlevels.append((t.name, prefix))
        if self.callee is not None:
            self.callee["wlevels"].append((t.name, prefix))

    def level_there(self, t, prefix):
        """Whether a record holds anything at a level or under it: its row, in a table that keeps its rows, or an
        entry under it with a value."""
        if t.rows and prefix and self.value(t, prefix) is not None:
            return True
        return any(self.value(t, p) is not None for p in self._under(t, prefix))

    def assigned_level(self, t, prefix):
        """After a whole level was assigned: the entries it brought. `write_level` touched what was under the
        level before, so one that is not in the log yet was missing before the assignment, and its value before
        the call is "missing", whatever touches it later in the call."""
        if t.foreign:
            return
        c = self.callee
        for p in self._under(t, prefix):
            e = (t.name, p)
            if c is not None and e not in c["first"]:
                c["first"][e] = "w"
                c["pre"][e] = None
            if c is not None:
                c["wrote"].add(e)
                if e not in self.first and e not in c["calls"]:
                    c["calls"][e] = None
            elif e not in self.first:
                self.first[e] = "w"
                self.pre[e] = None
            self.wrote.add(e)

    # ---- a call the block makes on the tape: its accesses of the own tables, apart from the block's
    def begin_callee(self):
        # calls: the entries the callee touched first in the call, with their values before it, put into the call's
        # log at the callee's end, sorted
        self.callee = {"first": {}, "pre": {}, "wrote": set(), "wlevels": [], "calls": {}}

    def end_callee(self):
        """(cr, cw) of the callee: the own entries whose first touch in it was a read, each with its value then; and
        the ones it wrote or changed in place, each with its value at its end. An entry erased has the value None."""
        c, self.callee = self.callee, None
        for name, prefix in c["wlevels"]:   # what a level assigned in the callee holds at its end
            t = self.roots[name][0]
            for p in self._under(t, prefix):
                e = (name, p)
                if e not in c["first"]:
                    c["first"][e], c["pre"][e] = "w", None
                    if e not in self.first and e not in c["calls"]:
                        c["calls"][e] = None
                c["wrote"].add(e)
                self.wrote.add(e)
        if MADE_ROWS:                       # the entries under a row the callee made, each missing before it
            for e in list(c["first"]):
                name, p = e
                t = self.roots[name][0]
                if t.rows and len(p) < t.depth and c["pre"][e] is None and self.value(t, p) is not None:
                    for q in self._under(t, p):
                        e2 = (name, q)
                        if e2 not in c["first"]:
                            c["first"][e2], c["pre"][e2] = "w", None
                            if e2 not in self.first and e2 not in c["calls"]:
                                c["calls"][e2] = None
                        c["wrote"].add(e2)
                        self.wrote.add(e2)
        for e in _one_order(c["calls"], key=lambda e: json.dumps([e[0], self.roots[e[0]][0].path(e[1])])):
            self.first[e], self.pre[e] = "c", c["calls"][e]
        cr, cw = [], []
        for e, rw in c["first"].items():
            name, p = e
            t = self.roots[name][0]
            if rw == "r":
                cr.append([name, t.path(p), c["pre"][e]])
            post = self.value(t, p)
            if e in c["wrote"] or post != c["pre"][e]:
                cw.append([name, t.path(p), post])
                if CW_WRITES:
                    self.wrote.add(e)       # the callee's write is the call's, whatever comes after
        cr = _one_order(cr, key=lambda x: json.dumps(x[:2]))   # one order, whatever the callee iterates
        cw = _one_order(cw, key=lambda x: json.dumps(x[:2]))
        return cr, cw

    def rest(self, whole):
        """Entries of the own tables that the call did not read, each with its value before the call: the ones it
        wrote without reading first, and, with `whole`, the ones it never touched (as they are now, which is as
        they were if the log is complete: `snapshot` is there to check that). With a call's reads, the whole
        `rest` is the node's state before the call."""
        out = []
        if whole:
            for name, (t, _) in self.roots.items():
                if t.foreign:
                    continue
                for p in self._under(t, ()):
                    if (name, p) not in self.first:
                        v = self.value(t, p)
                        if v is not None:
                            out.append([name, t.path(p), v])
        for (name, p), rw in self.first.items():      # written first, or first touched by a callee or
            if rw in ("w", "c") and self.pre[(name, p)] is not None and (name, p) not in self.bread:   # observed
                out.append([name, self.roots[name][0].path(p), self.pre[(name, p)]])
        out.sort(key=lambda e: json.dumps(e[:2]))   # one order, whatever the tables' own
        return out

    def snapshot(self):
        """Every entry of the own tables as it is now, read from the containers themselves and not from the log:
        {(table, its path as JSON): value}, empty entries left out."""
        out = {}
        for name, (t, _) in self.roots.items():
            if t.foreign:
                continue
            for p in self._under(t, ()):
                v = self.value(t, p)
                if v is not None:
                    out[(name, json.dumps(t.path(p)))] = v
        return out

    def footprint(self):
        """(reads, scans, writes) of the call, as JSON values. An entry is [table, path, value]."""
        for name, prefix in self.wlevels:       # a level assigned or removed as a whole: what is under it now.
            t = self.roots[name][0]             #   An assignment's own entries were noted at the assignment
            for p in self._under(t, prefix):    #   (`assigned_level`); this catches one put under the level
                e = (name, p)                   #   later without a log. What was there before was touched then,
                if e not in self.first:         #   so an entry not in the log was missing before the call.
                    self.first[e] = "w"
                    self.pre[e] = None
                self.wrote.add(e)
        if MADE_ROWS:                           # the entries under a row the call made, each missing before it
            for e in list(self.first):
                name, p = e
                t = self.roots[name][0]
                if t.rows and len(p) < t.depth and self.pre[e] is None and self.value(t, p) is not None:
                    for q in self._under(t, p):
                        e2 = (name, q)
                        if e2 not in self.first:
                            self.first[e2], self.pre[e2] = "w", None
                        self.wrote.add(e2)
        reads, writes = [], []
        for (name, p), rw in self.first.items():
            t = self.roots[name][0]
            e = (name, p)
            if rw == "r" or e in self.bread:
                reads.append([name, t.path(p), self.pre[e]])
            post = self.value(t, p)
            if e in self.wrote or post != self.pre[e]:
                writes.append([name, t.path(p), post])
        scans = [[name, self.roots[name][0].path(prefix)] for name, prefix in self.scans]
        return reads, scans, writes


def unwrap(v):
    if isinstance(v, ListView):
        return v._h.jobs
    if isinstance(v, CountCell):
        return v._h.count
    if isinstance(v, DequeView):
        return v._h.line
    return v._o if isinstance(v, View) else v


class ListHolder:
    """A list of the namespace, held as the one entry `jobs` of its table (a level held as attributes)."""
    __slots__ = ("jobs",)

    def __init__(self, raw):
        self.jobs = raw


ATTR_LEVELS[ListHolder] = ("jobs",)


class ListView:
    """A list of the namespace as the block sees it: what the document does with `pace_queue`, logged as reads
    and writes of the one entry; anything else raises while the recorder is on."""
    __slots__ = ("_r", "_t", "_h")
    CALLEE_OPS = ("clear", "extend")    # what a callee may do besides (the toy's link close: its own code)

    def __init__(self, rec, table, holder):
        object.__setattr__(self, "_r", rec)
        object.__setattr__(self, "_t", table)
        object.__setattr__(self, "_h", holder)

    def _log(self, write=False):
        r = self._r
        if r.on:
            r.read(self._t, ("jobs",))
            if write:
                r.write(self._t, ("jobs",))

    def __bool__(self):
        self._log()
        return bool(self._h.jobs)

    def __len__(self):
        self._log()
        return len(self._h.jobs)

    def __iter__(self):
        self._log()
        return iter(self._h.jobs)

    def append(self, x):
        self._log(write=True)
        self._h.jobs.append(x)

    def pop(self, *a):
        if self._r.on and self._r.callee is None and a != (0,):
            raise TypeError(f"footprint: {self._t.name}.pop{a}: the block pops the first job, and nothing else")
        self._log(write=True)
        return self._h.jobs.pop(*a)

    def __setitem__(self, k, v):
        # the toy's discard_paced rebuilds the list in place, `pace_queue[:] = jobs`. A callee's assignment of the
        # whole list is a read and a write of the one entry, in its log; the block's, and an assignment to a part of
        # the list, stay unknown
        r = self._r
        if not r.on:                    # outside a record: the list's own, as its other operations are
            self._h.jobs[k] = v
            return
        if not (r.callee is not None and isinstance(k, slice) and k == slice(None)):
            raise TypeError(f"footprint: {self._t.name}[{k!r}] = ...: an operation the views do not know")
        self._log(write=True)
        self._h.jobs[k] = v

    def __repr__(self):
        # (the jobs shown here would be a read no record has: while a record is open the text names the table
        # alone)
        if self._r.on:
            return f"ListView({self._t.name})"
        return f"ListView({self._t.name}: {self._h.jobs!r})"

    def __getattr__(self, name):
        r = self._r
        attr = getattr(self._h.jobs, name)      # (an AttributeError here is the list's own)
        if not callable(attr):
            if not r.on:
                return attr
            raise TypeError(f"footprint: {self._t.name}.{name}: an operation the views do not know")
        if r.on and not (r.callee is not None and name in self.CALLEE_OPS):
            raise TypeError(f"footprint: {self._t.name}.{name}: an operation the views do not know")

        # (a method taken while the recorder is off would be the list's own bound method, and a call of it inside a
        # later record would change the list with nothing logged: it is judged when it is called)
        def call(*a, **kw):
            r = self._r
            if r.on:
                if not (r.callee is not None and name in self.CALLEE_OPS):
                    raise TypeError(f"footprint: {self._t.name}.{name}: an operation the views do not know")
                self._log(write=True)
            return getattr(self._h.jobs, name)(*a, **kw)
        return call

    def __setattr__(self, name, v):
        raise TypeError(f"footprint: {self._t.name}.{name} = ...: an operation the views do not know")

    def _refuse(self, *a, **kw):
        if self._r.on:
            raise TypeError(f"footprint: {self._t.name}: an operation the views do not know")
        raise TypeError(f"footprint: {self._t.name}: use the list itself (unwrap) outside a call")

    __getitem__ = __delitem__ = __contains__ = __eq__ = __ne__ = __add__ = __iadd__ = _refuse   # (__setitem__: above)
    __hash__ = None


class CountHolder:
    """A number of the namespace (the window's count), held as the one entry `count` of its table."""
    __slots__ = ("count",)

    def __init__(self, raw):
        self.count = raw


ATTR_LEVELS[CountHolder] = ("count",)


def _num(x):
    """The other side of a comparison or a sum with the count: a number, or another cell's (a read of it)."""
    return x._read() if isinstance(x, CountCell) else x


class CountCell:
    """`in_flight` as the block sees it: an object under the name in place of the integer. A comparison, a sum or
    a difference that gives a number, `int()` and `bool()` are reads of the one entry. `+=` and `-=` are a read and
    then a write, both logged before the change, and give back the cell itself, so that the document's rebinding
    (`global in_flight; in_flight += 1` stores the result under the name) stores the same object. While the
    recorder is off everything passes through unlogged. Anything else raises: nothing the documents or the toy do
    with the count needs more."""
    __slots__ = ("_r", "_t", "_h")

    def __init__(self, rec, table, holder):
        self._r, self._t, self._h = rec, table, holder

    def _read(self):
        if self._r.on:
            self._r.read(self._t, ("count",))
        return self._h.count

    def _update(self, d):
        if self._r.on:
            self._r.read(self._t, ("count",))       # before the change: the value read is the value before it
            self._r.write(self._t, ("count",))
        self._h.count += d
        return self

    def __lt__(self, o):
        return self._read() < _num(o)

    def __le__(self, o):
        return self._read() <= _num(o)

    def __gt__(self, o):
        return self._read() > _num(o)

    def __ge__(self, o):
        return self._read() >= _num(o)

    def __eq__(self, o):
        return self._read() == _num(o)

    def __ne__(self, o):
        return self._read() != _num(o)

    def __add__(self, o):
        return self._read() + _num(o)

    __radd__ = __add__

    def __sub__(self, o):
        return self._read() - _num(o)

    def __rsub__(self, o):
        return _num(o) - self._read()

    def __int__(self):
        return int(self._read())

    def __bool__(self):
        return bool(self._read())

    def __iadd__(self, o):
        return self._update(_num(o))

    def __isub__(self, o):
        return self._update(-_num(o))

    __hash__ = None

    def __repr__(self):
        return f"CountCell({self._t.name}: {self._h.count!r})"


class LineHolder:
    """A deque of the namespace (the window's line), held as the one entry `line` of its table."""
    __slots__ = ("line",)

    def __init__(self, raw):
        self.line = raw


ATTR_LEVELS[LineHolder] = ("line",)


class DequeView:
    """`waiters` as the block sees it: the line as one entry, the peers in order. `bool`, `[0]`, `in` and iteration
    (front's, v0.10.7: the deque's own iterator, so that a change of the line while it runs raises as the deque's
    does) are reads; `popleft`, `append`, `appendleft` and `remove` are a read and a write, logged before the change.
    `len` and an index beyond the first raise while the recorder is on: no code uses them."""
    __slots__ = ("_r", "_t", "_h")

    def __init__(self, rec, table, holder):
        object.__setattr__(self, "_r", rec)
        object.__setattr__(self, "_t", table)
        object.__setattr__(self, "_h", holder)

    def _log(self, write=False):
        r = self._r
        if r.on:
            r.read(self._t, ("line",))
            if write:
                r.write(self._t, ("line",))

    def __bool__(self):
        self._log()
        return bool(self._h.line)

    def __getitem__(self, i):
        if self._r.on and not (isinstance(i, int) and not isinstance(i, bool) and i == 0):
            raise TypeError(f"footprint: {self._t.name}[{i!r}]: the block reads the first in line, and nothing else")
        self._log()
        return self._h.line[i]

    def __contains__(self, p):
        self._log()
        return p in self._h.line

    def popleft(self):
        self._log(write=True)
        return self._h.line.popleft()

    def append(self, p):
        self._log(write=True)
        self._h.line.append(p)

    def appendleft(self, p):
        self._log(write=True)
        self._h.line.appendleft(p)

    def remove(self, p):
        self._log(write=True)
        self._h.line.remove(p)

    def __iter__(self):
        self._log()
        return iter(self._h.line)

    def __repr__(self):
        return f"DequeView({self._t.name}: {list(self._h.line)!r})"

    def __getattr__(self, name):
        if not self._r.on:
            return getattr(self._h.line, name)
        raise TypeError(f"footprint: {self._t.name}.{name}: an operation the views do not know")

    def __setattr__(self, name, v):
        raise TypeError(f"footprint: {self._t.name}.{name} = ...: an operation the views do not know")

    def _unlogged(name):               # noqa: N805: the deque's own, outside a call alone
        def f(self, *a):
            if self._r.on:
                raise TypeError(f"footprint: {self._t.name}.{name}: an operation the views do not know")
            return getattr(self._h.line, name)(*a)
        return f

    __len__ = _unlogged("__len__")
    del _unlogged
    __hash__ = None


class View:
    """A table, or a level of one, as the block sees it."""
    __slots__ = ("_r", "_t", "_p", "_o")

    def __init__(self, rec, table, prefix, raw):
        object.__setattr__(self, "_r", rec)
        object.__setattr__(self, "_t", table)
        object.__setattr__(self, "_p", prefix)
        object.__setattr__(self, "_o", raw)

    def _leaf(self):
        return len(self._p) + 1 == self._t.depth

    def _sub(self, k, v):
        return View(self._r, self._t, self._p + (k,), v)

    # ---- one key
    def __getitem__(self, k):
        if not self._r.on:
            return self._o[k]
        if self._leaf():
            self._r.read(self._t, self._p + (k,))
            return self._o[k]
        return self._sub(k, self._o[k])

    def get(self, k, default=None):
        if not self._r.on:
            return self._o.get(k, default)
        if self._leaf():
            self._r.read(self._t, self._p + (k,))
            return self._o.get(k, default)
        v = _peek(self._o, k)
        if v is ABSENT:                             # a level that is not there: read as a whole, and empty
            self._r.scan(self._t, self._p + (k,))
            return default
        return self._sub(k, v)

    def __contains__(self, k):
        if self._r.on:
            if self._leaf():
                self._r.read(self._t, self._p + (k,))
            elif self._t.rows and self._t.presence_in:      # the row's own entry says whether it is there
                self._r.read(self._t, self._p + (k,))
            else:
                self._r.scan(self._t, self._p + (k,))
        return k in self._o

    def __setitem__(self, k, v):
        if self._r.on:
            if self._leaf():
                self._r.write(self._t, self._p + (k,))
            else:
                self._r.write_level(self._t, self._p + (k,))
        self._o[k] = unwrap(v)
        if self._r.on and not self._leaf():
            self._r.assigned_level(self._t, self._p + (k,))

    def __delitem__(self, k):
        if self._r.on:
            if self._leaf():
                self._r.write(self._t, self._p + (k,))
            else:
                self._r.write_level(self._t, self._p + (k,))
        del self._o[k]

    def pop(self, k, *default):
        if self._r.on:
            # a pop that finds nothing is a read alone. (Another section's table keeps its write: the block's is
            # refused there whatever it finds, and a callee's is the callee's business.)
            miss_reads = POP_MISS_READ and not self._t.foreign
            if self._leaf():
                self._r.read(self._t, self._p + (k,))
                if not (miss_reads and self._r.value(self._t, self._p + (k,)) is None):
                    self._r.write(self._t, self._p + (k,))
            else:
                self._r.scan(self._t, self._p + (k,))
                if self._r.callee is None and self._t.ordered_levels:     # the popped object is iterated unseen
                    self._r.order_tree(self._t, self._p + (k,), _peek(self._o, k))
                if not (miss_reads and not self._r.level_there(self._t, self._p + (k,))):
                    self._r.write_level(self._t, self._p + (k,))
        return self._o.pop(k, *default)

    def setdefault(self, k, default=None):
        """`t.setdefault(k, v)` of an entry (`tie_slot.setdefault((root, p), f.slot)`): a read of the entry, and a
        write of it only where it was missing. Of a level above the entries: an operation the views do not know."""
        if not self._r.on:
            return self._o.setdefault(k, unwrap(default))
        if not self._leaf():
            raise TypeError(f"footprint: {self._t.name}{list(self._p)}.setdefault of a level: an operation the views do not know")
        self._r.read(self._t, self._p + (k,))
        if _peek(self._o, k) is ABSENT:
            self._r.write(self._t, self._p + (k,))
        return self._o.setdefault(k, unwrap(default))

    # ---- a set as a table (its members are its entries)
    def add(self, k):
        if self._r.on:
            self._r.write(self._t, self._p + (k,))
        self._o.add(k)

    def discard(self, k):
        if self._r.on:
            self._r.write(self._t, self._p + (k,))
        self._o.discard(k)

    def remove(self, k):
        if self._r.on:
            self._r.read(self._t, self._p + (k,))
            self._r.write(self._t, self._p + (k,))
        self._o.remove(k)

    # ---- the whole level
    def _scan(self):
        if self._r.on:
            self._r.scan(self._t, self._p)

    def _foreign_keys(self):
        """The block iterating another section's level: its keys on the tape, and nothing else of it read."""
        return self._r.on and self._t.foreign and self._r.callee is None

    def _ordered_keys(self):
        """The block iterating a level of an own table whose order is asked: read whole, and its keys on the tape
        (the top level, `ordered`; a deeper one, `ordered_levels`)."""
        return (self._r.on and self._r.callee is None and not self._t.foreign
                and ((self._t.ordered and not self._p) or len(self._p) in self._t.ordered_levels))

    def __iter__(self):
        if self._foreign_keys():
            return iter(self._r.keys(self._t, self._p, list(self._o)))
        self._scan()
        if self._ordered_keys():
            return iter(self._r.keys(self._t, self._p, list(self._o)))
        return iter(self._o)

    def __len__(self):
        self._scan()
        return len(self._o)

    def __bool__(self):
        self._scan()
        return bool(self._o)

    def keys(self):
        if self._foreign_keys():
            return self._r.keys(self._t, self._p, list(self._o))
        self._scan()
        if self._ordered_keys():
            return self._r.keys(self._t, self._p, list(self._o))
        return self._o.keys()

    def values(self):
        self._scan()
        if (self._r.on and self._r.callee is None and self._t.values_ordered and not self._p):
            self._r.keys(self._t, self._p, list(self._o))   # `held_back.values()`, the order of the heartbeat's
            #   retries. Not every ordered table's: `tied.values()` is read by `any`, in no order
        if self._r.on and not self._leaf():
            return [self._sub(k, v) for k, v in self._o.items()]
        return self._o.values()

    def items(self):
        self._scan()
        if self._ordered_keys():            # `list(tie_slot.items())`, a tied row's `.items()`
            self._r.keys(self._t, self._p, list(self._o))
        if self._r.on and not self._leaf():
            return [(k, self._sub(k, v)) for k, v in self._o.items()]
        return self._o.items()

    def clear(self):
        if self._r.on:
            self._r.write_level(self._t, self._p)
        self._o.clear()

    def __eq__(self, other):
        self._scan()
        if isinstance(other, View):             # the other side is read as a whole too
            other._scan()
        return self._o == unwrap(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = None

    def __repr__(self):
        return f"View({self._t.name}{list(self._p)}: {self._o!r})"

    # ---- anything else: the toy's own, while the recorder is off, and in a callee on another section's table;
    #      in a callee, also the attribute reads of CALLEE_ATTRS, unlogged
    def _passes(self, name=None):
        r = self._r
        return (not r.on or (r.callee is not None and self._t.foreign)
                or (r.callee is not None and not self._p and (self._t.name, name) in CALLEE_ATTRS))

    def _attr_key(self, name):
        """Whether `name` is a key of this level held as an attribute (a PeerQueue's lane), at the table's last level."""
        names = ATTR_LEVELS.get(type(self._o))
        return names is not None and name in names and self._leaf()

    def __getattr__(self, name):
        if self._attr_key(name):                    # `queue[p].normal`: a read of the lane
            if self._r.on:
                self._r.read(self._t, self._p + (name,))
            return getattr(self._o, name)
        reads = ATTR_READS.get(type(self._o), {}).get(name)
        if reads is not None and self._leaf():      # `q.has_chunks()`, a read of the lanes it looks at
            if self._r.on:
                for a in reads:
                    self._r.read(self._t, self._p + (a,))
            return getattr(self._o, name)
        if not self._passes(name):
            raise TypeError(f"footprint: {self._t.name}{list(self._p)}.{name}: an operation the views do not know")
        return getattr(self._o, name)

    def __setattr__(self, name, v):
        if self._attr_key(name):                    # `queue[p].normal = [...]`: a write of the lane
            if self._r.on:
                self._r.write(self._t, self._p + (name,))
            setattr(self._o, name, unwrap(v))
            return
        if not self._passes():
            raise TypeError(f"footprint: {self._t.name}{list(self._p)}.{name} = ...: an operation the views do not know")
        setattr(self._o, name, v)


def install(rec, ns, tables):
    """Replace each table of the namespace by its view."""
    for t in tables:
        raw = ns[t.name]
        if isinstance(raw, (View, ListView, CountCell, DequeView)):
            raise TypeError(f"footprint: {t.name} is wrapped already")
        if isinstance(raw, int) and not isinstance(raw, bool):      # a number of the namespace (the window's
            if t.depth != 1:                                        #   count), a table of one entry
                raise TypeError(f"footprint: {t.name} is a number, and its table has {t.depth} keys")
            holder = CountHolder(raw)
            rec.roots[t.name] = (t, holder)
            ns[t.name] = CountCell(rec, t, holder)
            continue
        if isinstance(raw, collections.deque):                      # a deque of the namespace (the line)
            if t.depth != 1:
                raise TypeError(f"footprint: {t.name} is a deque, and its table has {t.depth} keys")
            holder = LineHolder(raw)
            rec.roots[t.name] = (t, holder)
            ns[t.name] = DequeView(rec, t, holder)
            continue
        if isinstance(raw, list):               # a list of the namespace, a table of one entry
            if t.depth != 1:
                raise TypeError(f"footprint: {t.name} is a list, and its table has {t.depth} keys")
            holder = ListHolder(raw)
            rec.roots[t.name] = (t, holder)
            ns[t.name] = ListView(rec, t, holder)
            continue
        rec.roots[t.name] = (t, raw)
        ns[t.name] = View(rec, t, (), raw)
