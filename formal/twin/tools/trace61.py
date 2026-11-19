#!/usr/bin/env python3
"""protocol.md §6.1's functions wrapped in a toy cell: the base of trace3.py's tracer.

No program, and no tracer of its own: trace3.py's Tracer3 is the tracer, and takes from this file its base class
(the wrappers' frame and the encodings) and the names SEC61 and CONSTS. The record described below is the one
this class's own wrappers make (format 2); no replay reads it, and trace3.py's head says what its records hold
in place of `pre` and `post`.

TOYDIR is the toy. Nothing in it changes: each node's namespace is wrapped after the toy's own
overrides (Node._override), and the cell then runs as run.py runs it, printing what run.py prints, its digest
included with --digest, so that a run can show the tracer perturbs nothing.

One record per top-level call into §6.1's block (a call from outside the block), per node:
  n, t       the node and the time (now)
  fn, args   the function and its arguments
  pre        §6.1's state before the call: the call's neighbourhood, or the node's whole state (below)
  tape       what §6.1's own code asked of the rest of the node, in order, each with its answer: held,
             expired, tied_to_root, connected_topic_peers, own_order, listed, enqueue and after
  post       the same after the call
  ret        the return value

Format 2: every entry names its keys, so that a record can hold more than the call reads, and a twin that reads
more widely than the Python sees something there. The neighbourhood of a call on key a, chunk k, group g:
asked_at, tried and offers under every key of k, in either form (a ledger call has no k: every key of g);
asked_parked and last_resort_armed for every chunk of g; park and offered for every group; every promise
(whatever chunk it names, so that a wrong match shows); and stop_pull[g]. With whole=True (the directed
records, whose states are small), every key, chunk and group of the node instead.
In pre only: every ask in the IWANTs queued to each peer `outstanding` looks at (§6.1 never changes a queue but
by `enqueue`, after its last look); for ledger, mine[g] and known_id[g]. stop_pull, the queues, mine and
known_id are read through the interface, and the replay refuses a read of them outside what the record holds.

Rows come in the containers' own order, which a run fixes (dicts keep insertion order); the one set of the
state, last_resort_armed, is written sorted, since a set of byte keys iterates in an order that changes from
process to process (Python's hash seed). So a trace's content is the same in every run.

An empty entry is left out: the toy's AutoMap makes one on every read, where §8.1 says reading allocates
nothing. Floats are written as their IEEE-754 bits, keys as hex (a full id) or [group hex, index] (a
WantIndex), groups as hex, peers as the toy's node ids. A call that raises is written too, with `raises` (the
exception's class), for a KeyError `raises_key` (the missing key), and the state it left; the exception goes on.
"""
import functools
import json
import struct

SEC61 = ("may_ask", "retry_offer", "outstanding", "add_offer", "announcers", "ledger", "untried",
         "least_recently_tried", "promise_due", "parked", "last_resort", "ask_parked")
CONSTS = ("IWANT_WINDOW", "RETRY_SLACK", "PROMISE", "PARK_TTL")


def fbits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


class Tracer:
    def __init__(self, toy, out, argv, whole=False):
        raise SystemExit("trace61: this class is the base of trace3.py's tracer, and writes no trace of its own")

    def write(self, rec):
        self.out.write(json.dumps(rec, separators=(",", ":")) + "\n")

    # ---- encodings
    def key(self, a):
        if isinstance(a, self.Wm.WantIndex):
            return [a.group.hex(), a.index]
        if isinstance(a, bytes):
            return a.hex()
        raise TypeError(f"not an ask key: {a!r}")

    def control(self, x):
        if not isinstance(x, self.Wm.Control):
            raise TypeError(f"§6.1 enqueues control only, got {x!r}")
        return [[m.kind, [self.key(b) for b in m.ids]] for m in x.items]

    def args_of(self, fn, args):
        k = self.key
        if fn in ("retry_offer", "announcers", "last_resort", "ask_parked"):
            (a,) = args
            return [k(a)]
        if fn in ("may_ask", "add_offer"):
            a, p = args
            return [k(a), p]
        if fn in ("outstanding", "parked"):
            p, a = args
            return [p, k(a)]
        if fn in ("untried", "least_recently_tried"):
            cands, a = args
            return [list(cands), k(a)]
        if fn == "promise_due":
            a, p, at = args
            return [k(a), p, fbits(at)]
        if fn == "ledger":
            (g,) = args
            return [g.hex()]
        raise ValueError(fn)

    def ret_of(self, fn, r):
        if fn in ("may_ask", "outstanding", "parked"):
            assert isinstance(r, bool), (fn, r)
            return r
        if fn == "announcers":
            return list(r)
        if fn == "ledger":
            return [self.key(a) for a in r]
        if fn in ("untried", "least_recently_tried"):
            return r
        assert r is None, (fn, r)
        return None

    # ---- the projection (reads that allocate nothing: .get and iteration, never [] on the toy's AutoMaps)
    def project(self, ns, fn, a, k, g):
        p, key, gi, whole = {}, self.key, ns["group_index"], self.whole

        def near(b):                    # a key in the neighbourhood: of chunk k in either form (ledger: of g)
            x = gi(b)
            return whole or ((x.group, x.index) == k if k is not None else x.group == g)

        rows = {
            "asked_at": [[key(b), fbits(t)] for b, t in ns["asked_at"].items() if near(b)],
            "tried": [[key(b), [[q, fbits(t)] for q, t in d.items()]] for b, d in ns["tried"].items() if d and near(b)],
            "offers": [[key(b), list(o)] for b, o in ns["offers"].items() if o and near(b)],
            "asked_parked": [[[c[0].hex(), c[1]], sorted(s)] for c, s in ns["asked_parked"].items()
                             if s and (whole or c[0] == g)],
            "lr_armed": sorted([c[0].hex(), c[1]] for c in ns["last_resort_armed"] if whole or c[0] == g),
            "promises": [[key(b), r, fbits(t)] for (b, r), t in ns["promises"].items()],
            "offered": [[q, row] for q, d in ns["offered"].items()
                        if (row := [[h.hex(), x.v] for h, x in d.items() if x.v])],
            "park": [[q, row] for q, d in ns["park"].items() if (row := [[h.hex(), fbits(t)] for h, t in d.items()])],
        }
        p.update((name, v) for name, v in rows.items() if v)
        if ns["stop_pull"].get(g, False):
            p["stop_pull"] = True
        if fn == "ledger":
            m = ns["mine"].get(g)
            if m is not None and m.v:
                p["mine"] = m.v
            kid = ns["known_id"].get(g)
            if kid:
                p["known_id"] = [[i, key(x)] for i, x in kid.items()]
        return p

    def queued_asks(self, ns, q):
        """The asks in the IWANTs queued to q (normal lane): what `outstanding` reads of §7's queue."""
        pq, out = ns["queue"].get(q), []
        if pq is not None:
            for e in pq.normal:
                for c in e.iwants():
                    for b in c.ids:
                        out.append(self.key(b))
        return out

    # ---- the wrappers, per node
    def install(self, nd, ns):
        consts = {c: fbits(ns[c]) for c in CONSTS}
        if self.consts is None:
            self.consts = consts
            self.write({"consts": consts})
        elif consts != self.consts:
            raise SystemExit(f"trace61: node {nd.id}'s constants differ from the first node's: {consts}")
        st = {"depth": 0, "ext": 0, "cur": None}
        gi, key, tr = ns["group_index"], self.key, self

        def chunk(a):
            b = gi(a)
            return (b.group, b.index)

        def sec61(name, fn):
            @functools.wraps(fn)
            def w(*args):
                if st["ext"]:                       # inside an interface call: not §6.1's own call
                    return fn(*args)
                if name == "outstanding" and st["depth"]:   # what it will read of q's queue, once per call and peer
                    qd = st["cur"]["pre"].setdefault("queued", {})
                    if args[0] not in qd:
                        qd[args[0]] = tr.queued_asks(ns, args[0])
                if st["depth"]:
                    st["depth"] += 1
                    try:
                        return fn(*args)
                    finally:
                        st["depth"] -= 1
                if name == "ledger":
                    a, k, g = None, None, args[0]
                else:
                    a = args[1] if name in ("outstanding", "parked", "untried", "least_recently_tried") else args[0]
                    k = chunk(a)
                    g = k[0]
                rec = {"n": nd.id, "t": fbits(ns["now"]), "fn": name, "args": tr.args_of(name, args),
                       "pre": tr.project(ns, name, a, k, g), "tape": []}
                if name == "outstanding":
                    rec["pre"]["queued"] = {args[0]: tr.queued_asks(ns, args[0])}

                def finish(**out):
                    rec["post"] = tr.project(ns, name, a, k, g)
                    rec.update(out)
                    if "queued" in rec["pre"]:
                        rec["pre"]["queued"] = [[q, ks] for q, ks in rec["pre"]["queued"].items()]
                    tr.counts[name + (" (raises)" if "raises" in out else "")] += 1
                    tr.write(rec)

                st["cur"], st["depth"] = rec, 1
                try:
                    r = fn(*args)
                except Exception as e:              # written with the state it left; the exception goes on
                    if isinstance(e, KeyError):     # which key was missing: the place it raised
                        (miss,) = e.args
                        if not isinstance(miss, int):
                            raise TypeError(f"trace61: a KeyError on a key that is not a peer: {miss!r}") from e
                        finish(raises=type(e).__name__, raises_key=miss)
                    else:
                        finish(raises=type(e).__name__)
                    raise
                finally:
                    st["depth"], st["cur"] = 0, None
                finish(ret=tr.ret_of(name, r))
                return r
            return w

        def iface(name, fn, enc):
            @functools.wraps(fn)
            def w(*args, **kw):
                if not st["depth"] or st["ext"]:    # not asked by §6.1's own code
                    return fn(*args, **kw)
                st["ext"] += 1
                try:
                    r = fn(*args, **kw)
                finally:
                    st["ext"] -= 1
                st["cur"]["tape"].append([name, *enc(r, *args, **kw)])
                return r
            return w

        def after_args(delay, fn, *args):
            out = []
            for x in args:
                if isinstance(x, (bytes, self.Wm.WantIndex)):
                    out.append(key(x))
                else:
                    raise TypeError(f"§6.1 arms timers on keys only, got {x!r}")
            return [fbits(delay), fn.__name__, out]

        enc = {
            "held": lambda r, a: [[key(a)], bool(r)],
            "expired": lambda r, g: [[g.hex()], bool(r)],
            "tied_to_root": lambda r, p, a: [[p, key(a)], bool(r)],
            "connected_topic_peers": lambda r: [[], list(r)],
            "own_order": lambda r, xs, a: [[list(xs), key(a)], list(r)],
            "listed": lambda r, p: [[p], int(r)],
            "enqueue": lambda r, p, x, urgent=False: [[p, tr.control(x), bool(urgent)], bool(r)],
            "after": lambda r, delay, fn, *args: [after_args(delay, fn, *args), None],
        }
        for name in SEC61:
            ns[name] = sec61(name, ns[name])
        for name, e in enc.items():
            ns[name] = iface(name, ns[name], e)
