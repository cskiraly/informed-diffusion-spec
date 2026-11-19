#!/usr/bin/env python3
"""The controls of the tracer's own checks, each by a fault planted in a run of directed42.py. directed42.py's records
hold the whole state, a share of its samples runs the toy's own enqueue, and its DEFER verdicts reach the deferral
path.

    python3 tracerfaults3.py --made-rows-off TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --alias TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --alias-control TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --installed-flip TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --pending-twice TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --alias-start TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --alias-message TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --defer-chain TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --replaced TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --false-wrapper TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --stale-id TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --level1-in-cell TOYDIR OUT.jsonl.gz [ignored]
    python3 tracerfaults3.py --late-rebind TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --stale-id-callee TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --rebind-after-records TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]
    python3 tracerfaults3.py --limit-fraction TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]

- `--made-rows-off`: the views write only the entry a call touched under a row it made (footprint.MADE_ROWS off).
  A row the toy's enqueue makes then has a lane in no entry. The tracer's check of its log against the tables
  (trace3.py's `account`) must stop it.
- `--alias`: the first entry the toy puts in a lane is also put in the same peer's other lane: one entry object in
  two places. The alias check (trace3.py's `alias_check`, called at the end of each record that touches the queue)
  must stop it. Q11 of footprint_test.py calls the check directly; this run checks that the tracer calls it.
- `--alias-control`: the first entry the toy puts in a lane with a control gets a twin in the same peer's other
  lane: another entry, sharing that control (drop_offer changes a message's ids in place). The alias check must
  stop it.
- `--installed-flip`: the second time a record asks installed_block of one (slot, root), the answer is the other one
  (a block where there was none, or none where there was one). The twin's recursion between on_validated and defer,
  with its fuel of two, assumes one answer within a call; trace3.py's `installed` must stop it.
- `--pending-twice`: the first copy defer keeps is kept again under its root: one (peer, chunk) twice in a list of
  waits. The twin removes a pair as Python's list.remove does, the first equal one, and no pair may be there twice;
  the check at the end of each record that touches `pending` (trace3.py's `pending_check`) must stop it.
- `--alias-start`: at the first record's start where a lane holds an entry with a control, another entry sharing
  that control is put in the same peer's other lane, as if made outside any record. The alias check at the record's
  start must stop it, before the call can consume one side of it.
- `--alias-message`: the first entry the toy puts in a lane with a control gets a twin in the same peer's other lane
  with a control of its own that holds the same message objects. Distinct controls, one message: the check of the
  messages' identity must stop it, which `--alias-control` never reaches.
- `--defer-chain`: where a record's chain already holds two DEFERs and the block is installed, the next validation
  answers DEFER once more. The twin's fuel (deferDepth, 2) would end there; the tracer's count of a record's chain
  of defers must stop it.

- `--replaced`: a traced name (may_ask) is a function of this tool's own at the node, with none of the document's
  code behind it, as a fault or a variant of the toy's would be. The tracer's check of each traced name at its
  install (trace3.py's `own_code`) must stop it, before any record.
- `--false-wrapper`: the same name is a function with a listed wrapper's qualified name that holds another of the
  document's functions in its closure. The check must stop it: a wrapper is listed by its name and by what it
  wraps.

- `--stale-id`: the id a chunk has stored is not the document's message_id of it (its content id answers
  otherwise). The toy's wrapper returns the stored id; the tracer's check at each call of message_id by the block,
  against the document's own function, must stop it.

- `--rebind-after-records`: a traced name (may_ask) bound again after the trace's first record, to a function of this
  tool's own. The names' check at the trace's end must stop it (the one at the nodes line is past).
- `--limit-fraction`: a node's MAX_IHAVE_LENGTH is 2.5. The tracer's check that each limit is a count must stop it
  at its install, where int() would make it 2.

Each must end with a non-zero exit code and the tracer's own line. If the trace is written to the end, the check
checks nothing. Its own line on stderr says which fault, and how many times it was planted.
"""
import functools
import runpy
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import footprint as F                   # noqa: E402
import trace3 as T                      # noqa: E402: the module directed42.py imports (one sys.modules entry)

PLANTED = [0]


def made_rows_off():
    F.MADE_ROWS = False
    PLANTED[0] = 1


def alias(toy):
    sys.path.insert(0, str(Path(toy).resolve()))
    import node as N                    # noqa: E402: the pinned toy's

    _append = N._Lane.append

    def append(self, x):
        _append(self, x)
        if not PLANTED[0]:              # the fault, once: the entry in the other lane of its queue too
            q = self._q
            other = q.urgent if self is q.normal else q.normal
            list.append(other, x)
            PLANTED[0] += 1

    N._Lane.append = append


def alias_control(toy):
    sys.path.insert(0, str(Path(toy).resolve()))
    import node as N                    # noqa: E402: the pinned toy's
    import wire as W                    # noqa: E402

    _append = N._Lane.append

    def append(self, x):
        _append(self, x)
        if not PLANTED[0] and getattr(x, "control", None) is not None:   # the fault, once: another entry, its
            q = self._q                                                     #   control the same object
            other = q.urgent if self is q.normal else q.normal
            list.append(other, W.Entry(control=x.control))
            PLANTED[0] += 1

    N._Lane.append = append


def before_install(wrap):
    """Run `wrap(tracer, ns)` on the node's namespace just before the tracer installs itself, so that what `wrap`
    puts there is what the tracer wraps (a block function the tracer then traces, an interface answer it records)."""
    _install = T.Tracer3.install

    @functools.wraps(_install)
    def install(self, nd, ns):
        wrap(self, ns)
        return _install(self, nd, ns)

    T.Tracer3.install = install


def installed_flip():
    def wrap(tr, ns):
        ib = ns["installed_block"]

        def installed_block(slot, root):
            r = ib(slot, root)
            k = (int(slot), bytes(root))
            if not PLANTED[0] and k in getattr(tr, "ib", {}):   # asked before in this record: the other answer, once
                PLANTED[0] += 1
                return None if tr.ib[k] else types.SimpleNamespace(slot=slot, root=root)
            return r

        ns["installed_block"] = installed_block

    before_install(wrap)


def pending_twice():
    def wrap(tr, ns):
        defer = ns["defer"]

        @functools.wraps(defer)
        def twice(p, f):
            pend, root = ns["pending"], f.beacon_block_root
            n = len(pend[root]) if root in pend else 0
            r = defer(p, f)
            if not PLANTED[0] and root in pend and len(pend[root]) > n:     # kept: kept again, once, as defer keeps
                pend[root].append((p, f))
                PLANTED[0] += 1
            return r

        ns["defer"] = twice
        # the check of each traced name (trace3.own_code) would stop this fault's own wrapper first: it is listed
        # for this run, as the wrapper of the document's defer that it is, so that the check of `pending` stops it
        T.WRAPPERS["defer"] = twice.__qualname__

    before_install(wrap)


def alias_start(toy):
    sys.path.insert(0, str(Path(toy).resolve()))
    import wire as W                    # noqa: E402: the pinned toy's

    _check = T.Tracer3.alias_check

    def check(self, rec, nid, args=(), when="end"):
        if when == "start" and not PLANTED[0]:      # the fault, once: an alias there before the call
            raw = rec.roots["queue"][1]
            for p in F._keys(raw):
                pq = F._peek(raw, p)
                for ln in ("urgent", "normal"):
                    for e in list(getattr(pq, ln)):
                        if e.control is not None:
                            other = pq.urgent if ln == "normal" else pq.normal
                            list.append(other, W.Entry(control=e.control))
                            PLANTED[0] += 1
                            return _check(self, rec, nid, args, when)
        return _check(self, rec, nid, args, when)

    T.Tracer3.alias_check = check


def alias_message(toy):
    sys.path.insert(0, str(Path(toy).resolve()))
    import node as N                    # noqa: E402: the pinned toy's
    import wire as W                    # noqa: E402

    _append = N._Lane.append

    def append(self, x):
        _append(self, x)
        if not PLANTED[0] and getattr(x, "control", None) is not None and x.control.items:   # once: another entry,
            q = self._q                                                     #   its control its own, its messages
            other = q.urgent if self is q.normal else q.normal              #   the same objects
            list.append(other, W.Entry(control=W.Control(list(x.control.items))))
            PLANTED[0] += 1

    N._Lane.append = append


def defer_chain():
    def wrap(tr, ns):
        vc, ib, DEFER = ns["validate_chunk"], ns["installed_block"], ns["DEFER"]
        cur = {"rec": None, "n": 0}

        def validate_chunk(f):
            r = vc(f)
            if cur["rec"] is not tr.ib:             # a new record: tr.ib is made afresh at each record's start
                cur["rec"], cur["n"] = tr.ib, 0
            if r == DEFER:
                cur["n"] += 1
            elif not PLANTED[0] and cur["n"] >= 2 and ib(f.slot, f.beacon_block_root):
                PLANTED[0] += 1                     # once: a third DEFER in the chain, the block installed
                return DEFER
            return r

        ns["validate_chunk"] = validate_chunk

    before_install(wrap)


def replaced():
    def wrap(tr, ns):
        def may_ask(a, p):              # a function of this tool's own under a traced name, as a fault or a variant
            return False                #   of the toy's would be: none of the document's code is behind it
        ns["may_ask"] = may_ask
        PLANTED[0] += 1

    before_install(wrap)


def false_wrapper():
    def wrap(tr, ns):
        other = ns["parked"]            # the document's code, but not may_ask's

        def may_ask(a, p):
            return other(p, a)
        may_ask.__qualname__ = T.WRAPPERS["may_ask"]    # a listed wrapper's name, on a function that wraps another
        ns["may_ask"] = may_ask
        PLANTED[0] += 1

    before_install(wrap)


def stale_id():
    def wrap(tr, ns):
        scenario = ns["content_id"]     # directed42.py's: the chunk's own content id, as its stored id has it

        def content_id(f):              # another content id than the one the chunk's stored id was made with: the
            c = scenario(f)             #   document's message_id of the chunk is then not the id the toy returns
            return bytes([c[0] ^ 1]) + c[1:]
        ns["content_id"] = content_id
        PLANTED[0] += 1

    before_install(wrap)


def after_install(wrap):
    """Run `wrap(tracer, ns)` on the node's namespace just after the tracer installed itself: what the toy does where
    it binds a name after `_override` returns."""
    _install = T.Tracer3.install

    @functools.wraps(_install)
    def install(self, nd, ns):
        r = _install(self, nd, ns)
        wrap(self, ns)
        return r

    T.Tracer3.install = install


def late_rebind():
    """A traced name bound again after the tracer's install (as Node.__init__ and `_v2` bind theirs), to a function of
    this tool's own. The names' second check, at the nodes line, must stop it."""
    def wrap(tr, ns):
        def may_ask(a, p):
            return False
        ns["may_ask"] = may_ask
        PLANTED[0] += 1

    after_install(wrap)


def rebind_after_records():
    """A traced name bound again once the trace has records: the names' check at the trace's end must stop it."""
    nss = []
    after_install(lambda tr, ns: nss.append(ns))
    _write = T.Tracer3.write

    @functools.wraps(_write)
    def write(self, rec):
        r = _write(self, rec)
        if not PLANTED[0] and isinstance(rec, dict) and "fn" in rec and nss:
            def may_ask(a, p):
                return False
            nss[0]["may_ask"] = may_ask
            PLANTED[0] += 1
        return r

    T.Tracer3.write = write


def limit_fraction():
    """A limit that is no count, as a variant could set one: the tracer must refuse it at its install."""
    def wrap(tr, ns):
        ns["MAX_IHAVE_LENGTH"] = 2.5
        PLANTED[0] += 1

    before_install(wrap)


def stale_id_callee():
    """A chunk's stored id made stale where only a call on the tape reads it next: the node's open_group leaves
    another id on the chunk, and the node's store, a callee, asks message_id of it. The tracer's check of message_id
    against the document's own function must stop it there."""
    def wrap(tr, ns):
        og = ns["open_group"]

        def open_group(g, f):
            r = og(g, f)
            m = getattr(f, "mid", None)
            if not PLANTED[0] and m is not None:
                f.mid = m[:36] + bytes([m[36] ^ 1]) + m[37:]
                PLANTED[0] += 1
            return r
        ns["open_group"] = open_group

    before_install(wrap)


def level1_in_cell():
    """The condition on level 1, a replaceable name: a cell whose node runs something else as validate_chunk. A
    directed set's scenario may (in a trace of the whole state); a cell may not. The fault runs the hand-counted
    cell, not directed42.py, with a level 1 of this tool's own at every node."""
    def wrap(tr, ns):
        def validate_chunk(f):
            return "ACCEPT"
        ns["validate_chunk"] = validate_chunk
        PLANTED[0] += 1

    before_install(wrap)


FAULTS = ("--made-rows-off", "--alias", "--alias-control", "--installed-flip", "--pending-twice", "--alias-start",
          "--alias-message", "--defer-chain", "--replaced", "--false-wrapper", "--stale-id", "--level1-in-cell",
          "--late-rebind", "--stale-id-callee", "--rebind-after-records", "--limit-fraction")
HAND5 = ["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"]


def main(argv):
    if len(argv) < 3 or argv[0] not in FAULTS:
        print(f"usage: tracerfaults3.py {'|'.join(FAULTS)} TOYDIR OUT.jsonl.gz [directed42.py's arguments ...]",
              file=sys.stderr)
        return 2
    fault, rest = argv[0], argv[1:]
    if fault == "--made-rows-off":
        made_rows_off()
    elif fault == "--alias":
        alias(rest[0])
    elif fault == "--alias-control":
        alias_control(rest[0])
    elif fault == "--installed-flip":
        installed_flip()
    elif fault == "--pending-twice":
        pending_twice()
    elif fault == "--alias-start":
        alias_start(rest[0])
    elif fault == "--alias-message":
        alias_message(rest[0])
    elif fault == "--defer-chain":
        defer_chain()
    elif fault == "--replaced":
        replaced()
    elif fault == "--false-wrapper":
        false_wrapper()
    elif fault == "--level1-in-cell":
        level1_in_cell()
    elif fault == "--late-rebind":
        late_rebind()
    elif fault == "--stale-id-callee":
        stale_id_callee()
    elif fault == "--rebind-after-records":
        rebind_after_records()
    elif fault == "--limit-fraction":
        limit_fraction()
    else:
        stale_id()
    sys.argv = [str(HERE / "directed42.py"), *rest]
    try:
        if fault == "--level1-in-cell":     # a cell's trace, not of the whole state: trace3.py's own run of hand5
            T.main([rest[0], rest[1], *HAND5])
        else:
            runpy.run_path(str(HERE / "directed42.py"), run_name="__main__")
    finally:
        print(f"tracerfaults3: {fault[2:]}, planted {PLANTED[0]} time{'s' if PLANTED[0] != 1 else ''}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
