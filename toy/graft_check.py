#!/usr/bin/env python3
"""graft_check.py [--bound N] [--doc FILE] [--model]: protocol-v2.md §4.1's JOIN and GRAFT
exchanges, every interleaving, for one link and one push relation between two nodes.

The document's own functions run as written: the last definition of each of NAMES in its code
blocks, one namespace per node, with the helpers they call stubbed for one object type, one family
and one colour. The nodes start connected, with no JOIN for the type: either opens the link with
its JOIN, or both do, at most once each. Node S may push node R. S's upkeep offers to push (a
GRAFT, direction OUT); R's asks to be pushed (IN), and prunes an in-pusher (IN); upkeep grafts only
a link (`links`: the peer's JOIN received, ours queued rather than owed). A node's sends go into a
per-peer queue of QUEUE entries, a JOIN ahead of the rest as on the urgent lane, from which a
writer step moves the head onto an ordered, lossless wire; other traffic may take the queue's room,
at most FILLERS times per node. A GRAFT that arrives may be accepted or refused, whatever the
receiver's counts (its caps and duty are drawn at will), so the check covers every decision an
honest node can take. Each node's upkeep acts at most N times.

Checked over every reachable state:
  - at rest (nothing queued, owed or on a wire) the two ends agree: S pushes R exactly when R
    counts S as a pusher, and no GRAFT is left unanswered;
  - at rest, once either end has opened the link, both ends hold the other's JOIN and have sent
    their own;
  - no GRAFT or PRUNE reaches a node that has no link for it, as before its sender's JOIN (the
    check drops it, and marks the state);
  - the state graph has no cycle: every exchange ends.
Counted, not at rest: states in which S pushes R while R neither counts S nor has asked, with no
PRUNE of R's on its way, and states in which R counts S while S neither pushes nor has offered, with
no PRUNE of S's on its way: the transient of a PRUNE that crosses other messages of the relation.

--doc runs another version of the document. Three earlier versions of §4.1's functions are kept as
controls in controls/, and must fail: graft-unanswered.md (before 2026-11-04), where a GRAFT's
sender recorded nothing; join-lost.md (2026-11-04), where a JOIN a full queue refused was lost; and,
with --diverged, held-graft-unanswered.md (before 2026-11-09), where a GRAFT for a relation its
receiver holds went unanswered. Each holds only the functions of NAMES, which is all this check
reads from a document. A text without `send_join` sends the opening JOIN as
`on_join` sends its answer, and its `join_sent` is recorded where the queue admits the JOIN.

--both: the relation of a SYMMETRIC type (gossipsub's mesh, §4.1) instead: both ends' upkeep grafts
it (BOTH, below F_LO) and prunes it (BOTH, at F_HI), and at rest the ends agree in both directions and
each end holds both directions or neither. In every state at rest in which an end holds it one way
only, that end's upkeep must act on it with its count between the floor and the cap, where neither
grafting up nor pruning down applies (2026-11-10).

--diverged: start instead from ends that disagree at rest, with the link formed: R counting S as a
pusher while S does not push R, or S pushing R while R does not count it (with --both, every way the
two ends can hold the relation but whole at both or at neither). Every state at rest after an upkeep
step has acted must then agree, with no GRAFT unanswered: the yes again to a GRAFT for a relation the
receiver holds (2026-11-09). The text before it fails: R reads S's GRAFT and answers nothing. A run
that checks no state at rest fails, since its check would be empty.

The backoff after a PRUNE (PRUNE_BACKOFF) only holds back when a node grafts, never how a GRAFT or
PRUNE is read, so every state reached with it is one reached without; the check runs at 0.

--model: the abstract model behind §4.1's comparison of the ways a GRAFT's sender may learn the
agreement, on one relation over FIFO channels without queues: counted at its GRAFT (gossipsub's way)
without a backoff, the same with gossipsub's backoff after a PRUNE, assumed longer than the round
trip, and answered (this document's way).
"""
import argparse
import ast
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract import blocks  # noqa: E402

DOC2 = HERE.parent / "protocol-v2.md"
NAMES = ("maintain_relations", "graft", "prune", "on_graft", "on_prune", "join_push", "send_relation",
         "queue_owed_relations", "on_join", "send_join", "yes", "no")
IN, OUT, BOTH, FORWARD, NONE, FAST, HOME = "IN", "OUT", "BOTH", "FORWARD", "NONE", "FAST", "HOME"
QUEUE = 1                           # entries a per-peer queue admits
FILLERS = 2                         # times other traffic may take a node's queue room
C, FAM = 0, 0                       # the one colour and the one family
FILLER = "other"                    # an entry of other traffic: it takes room and does nothing


@dataclass(frozen=True)
class Join:
    object_type: str
    interest: str
    custody_count: int
    duty: str
    colours: int


JOIN = Join(object_type="t", interest="ALL", custody_count=0, duty=FORWARD, colours=1)


@dataclass(frozen=True)
class Graft:
    object_type: str
    family: int
    colour: int
    direction: str
    answer: bool = False                # since 2026-11-09: a yes; a text before it sets none


@dataclass(frozen=True)
class Prune:
    object_type: str
    family: int
    colour: int
    direction: str


class Type:
    """The one object type; the document keys its maps by it."""
    id = "t"

    def __init__(self, symmetric=False):
        self.params = SimpleNamespace(M=1, F_LO=0, F_HI=1, D_OUT=0, D_OUT_FAST=0, D_OUT_MAX=1,
                                      SYMMETRIC=symmetric, PRUNE_BACKOFF=0.0)

    def family(self, g):
        return FAM


def functions(doc):
    """The document's code for NAMES, the last definition of each, and the names found."""
    found = {}
    for _section, code in blocks(Path(doc).read_text()):
        for node in ast.parse(code).body:
            if isinstance(node, ast.FunctionDef) and node.name in NAMES:
                found[node.name] = ast.get_source_segment(code, node)
    return "\n\n".join(found.values()), set(found)


def relmap():
    return defaultdict(lambda: defaultdict(lambda: defaultdict(set)))


class Node:
    """One node's namespace, running the document's functions; its state toward its one peer is
    loaded from and saved to a tuple, so the search can branch."""

    def __init__(self, code, peer, has, symmetric=False):
        self.peer, self.T = peer, Type(symmetric)
        ns = self.ns = {"IN": IN, "OUT": OUT, "BOTH": BOTH, "FORWARD": FORWARD, "FAST": FAST,
                        "INVALID": "INVALID", "Graft": Graft, "Prune": Prune, "Join": Join, "chunks": {},
                        "accept": True, "now": 0.0}
        T = self.T

        def send(p, m, urgent=False):           # the bounded per-peer queue: true if it admitted m
            q = ns["queue"]
            if len(q) >= QUEUE:
                return False
            if urgent:                          # the urgent lane goes first
                q.insert(sum(1 for e in q if isinstance(e, Join)), m)
            else:
                q.append(m)
            if isinstance(m, Join) and "send_join" not in has:
                ns["join_sent"][p][T] = m       # a text without send_join: recorded where the queue admits it
            return True

        def linked():                           # links(T): the peer's JOIN received, ours queued rather than owed
            return (T in ns["join_recv"][peer] and T in ns["join_sent"][peer]
                    and not any(isinstance(m, Join) for m in ns["owed_relations"][peer]))

        def candidates(T_, fam, c=C, d=None):   # the one peer, if it may take the relation
            if not linked():
                return []
            if d is None:                       # the signature before 2026-11-04: "not yet in the relation"
                ok = c not in ns["push_in"][peer][T][fam] and c not in ns["push_out"][peer][T][fam]
            else:                               # BOTH: in neither direction; out of the backoff, which at
                ds = (IN, OUT) if d == BOTH else (d,)   # PRUNE_BACKOFF 0 never holds a GRAFT back
                ok = all(c not in (ns["push_in"] if x == IN else ns["push_out"])[peer][T][fam]
                         and c not in (ns["grafted_in"] if x == IN else ns["grafted_out"])[peer][T][fam]
                         and ns["backoff"][peer][T][fam].get((c, x), 0.0) <= ns["now"] for x in ds)
            return [peer] if ok else []

        ns.update(
            sample_without_replacement=lambda xs, k: list(xs)[:k],   # one peer: no draw to make
            send=send, candidates=candidates, type_of=lambda tid: T, families_with_duty=lambda T_: [FAM],
            in_pushers=lambda T_, fam, c: [peer] if c in ns["push_in"][peer][T][fam] else [],
            out_pushees=lambda T_, fam, c: [peer] if c in ns["push_out"][peer][T][fam] else [],
            wants_family=lambda T_, fam: ns["accept"], uplink_class=lambda: HOME,
            has_room=lambda p: len(ns["queue"]) < QUEUE, wake=lambda p: None, our_join=lambda T_: JOIN)
        self.linked = linked
        exec(compile(code, "protocol-v2.md (§4.1's functions)", "exec"), ns)
        self.load((False,) * 4 + ((), ()) + (False,) * 4)

    def load(self, s):
        po, pi, go, gi, owed, queue, recv, sent, self.opened, self.early = s
        ns, p, T = self.ns, self.peer, self.T
        for name, on in (("push_out", po), ("push_in", pi), ("grafted_out", go), ("grafted_in", gi)):
            ns[name] = relmap()
            if on:
                ns[name][p][T][FAM].add(C)
        ns["owed_relations"] = defaultdict(list)
        ns["owed_relations"][p].extend(owed)
        ns["backoff"] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))   # not part of the state:
                                                #   at PRUNE_BACKOFF 0 it holds nothing back
        ns["queue"] = list(queue)
        ns["join_recv"], ns["join_sent"] = defaultdict(dict), defaultdict(dict)
        if recv:
            ns["join_recv"][p][T] = JOIN
        if sent:
            ns["join_sent"][p][T] = JOIN

    def save(self):
        ns, p, T = self.ns, self.peer, self.T
        return tuple(C in ns[name][p][T][FAM] for name in ("push_out", "push_in", "grafted_out", "grafted_in")) + (
            tuple(ns["owed_relations"][p]), tuple(ns["queue"]), T in ns["join_recv"][p], T in ns["join_sent"][p],
            self.opened, self.early)

    def params(self, **kw):
        for k, v in kw.items():
            setattr(self.T.params, k, v)


S, R = 0, 1
UPKEEP = {S: [("offers to push", dict(F_LO=0, F_HI=99, D_OUT=1, D_OUT_FAST=1))],
          R: [("asks to be pushed", dict(F_LO=1, F_HI=1, D_OUT=0, D_OUT_FAST=0)),
              ("prunes its pusher", dict(F_LO=0, F_HI=0, D_OUT=0, D_OUT_FAST=0))]}
UPKEEP_BOTH = {x: [("grafts the relation", dict(F_LO=1, F_HI=99, D_OUT=1, D_OUT_FAST=1)),     # --both: below F_LO
                   ("prunes the relation", dict(F_LO=0, F_HI=1, D_OUT=0, D_OUT_FAST=0))]     #   and at F_HI
               for x in (0, 1)}
STEADY = dict(F_LO=0, F_HI=2, D_OUT=1, D_OUT_FAST=1)   # --both: the count between the floor and the cap
NAME = {S: "S", R: "R"}


def acts(n, s):
    """--both: whether the node's upkeep acts on the relation in its state s with its count between
    the floor and the cap."""
    n.load(s)
    n.params(**STEADY)
    n.ns["maintain_relations"](n.T)
    return n.save() != s


def held(x):
    """How a node's state x holds the relation."""
    return {(True, True): "both ways", (True, False): "pushing only", (False, True): "counting only",
            (False, False): "nothing"}[(x[0], x[1])]


def label(m):
    if m == FILLER:
        return "other traffic"
    if isinstance(m, Join):
        return "JOIN"
    return f"{type(m).__name__.upper()} {m.direction}" + (" (a yes)" if getattr(m, "answer", False) else "")


def successors(nodes, has, st, upkeep=UPKEEP):
    """(label, next state) for every step enabled in st = (S's, R's, wire S->R, wire R->S, upkeep
    left at S and R, other traffic left at S and R)."""
    s_of, wires, up, fill = [st[0], st[1]], [st[2], st[3]], [st[4], st[5]], [st[6], st[7]]
    out = []

    def make(who, new, wire=None, wire_val=None, up_dec=0, fill_dec=0, other=None, other_val=None):
        s2, w2, u2, f2 = list(s_of), list(wires), list(up), list(fill)
        s2[who] = new
        if other is not None:
            s2[other] = other_val
        if wire is not None:
            w2[wire] = wire_val
        u2[who] -= up_dec
        f2[who] -= fill_dec
        return (s2[0], s2[1], w2[0], w2[1], u2[0], u2[1], f2[0], f2[1])

    for who in (S, R):
        n, peer_wire = nodes[who], who          # wire index: S->R is 0 (written by S), R->S is 1
        n.load(s_of[who])
        if not n.opened and n.T not in n.ns["join_sent"][n.peer]:   # the node opens the link: its JOIN
            if "send_join" in has:
                n.ns["send_join"](n.peer, JOIN)
            else:                               # a text without send_join: as on_join sends its answer
                n.ns["send"](n.peer, JOIN, urgent=True)
            n.opened = True
            out.append((f"{NAME[who]} opens the link", make(who, n.save())))
        if up[who]:                             # the upkeep, at a heartbeat
            for name, prm in upkeep[who]:
                n.load(s_of[who]); n.params(**prm)
                n.ns["maintain_relations"](n.T)
                new = n.save()
                if new != s_of[who]:
                    out.append((f"{NAME[who]} {name}", make(who, new, up_dec=1)))
        if fill[who] and len(s_of[who][5]) < QUEUE:      # other traffic takes the queue's room
            n.load(s_of[who])
            n.ns["queue"].append(FILLER)
            out.append((f"{NAME[who]} queues other traffic", make(who, n.save(), fill_dec=1)))
        if s_of[who][4] or s_of[who][5]:        # the writer: owed JOINs, GRAFTs and PRUNEs first, then the head
            n.load(s_of[who])
            if "queue_owed_relations" in has:
                n.ns["queue_owed_relations"](n.peer)
            q = n.ns["queue"]
            if q:
                m = q.pop(0)
                out.append((f"{NAME[who]} writes {label(m)}",
                            make(who, n.save(), wire=peer_wire, wire_val=wires[peer_wire] + (m,))))
        their = 1 - who                         # delivery at who, from the wire the other end writes
        if wires[their]:
            m, rest = wires[their][0], wires[their][1:]
            n.load(s_of[who])
            if m == FILLER:
                out.append((f"{NAME[who]} reads other traffic", make(who, s_of[who], wire=their, wire_val=rest)))
            elif isinstance(m, Join):
                n.ns["on_join"](n.peer, m)
                out.append((f"{NAME[who]} reads JOIN", make(who, n.save(), wire=their, wire_val=rest)))
            elif not n.linked():
                n.early = True                  # no link here for it: dropped, and the state marked
                out.append((f"{NAME[who]} reads {label(m)} before a link", make(who, n.save(), wire=their, wire_val=rest)))
            elif isinstance(m, Prune):
                n.ns["on_prune"](n.peer, m)
                out.append((f"{NAME[who]} reads {label(m)}", make(who, n.save(), wire=their, wire_val=rest)))
            else:
                for accept in (True, False):    # the receiver's caps and duty, drawn at will
                    n.load(s_of[who]); n.params(F_HI=1, D_OUT_MAX=1)
                    n.ns["accept"] = accept
                    n.ns["join_sent"][n.peer][n.T] = replace(JOIN, duty=FORWARD if accept else NONE)
                    back = n.ns["on_graft"](n.peer, m)
                    for pr in back or ():      # before 2026-11-04 the PRUNEs rode on the response: lost to a full queue
                        n.ns["send"](n.peer, pr)
                    verb = "accepts" if accept else "may refuse"
                    out.append((f"{NAME[who]} reads {label(m)}, {verb}", make(who, n.save(), wire=their, wire_val=rest)))
    return out


def in_flight(st, who, kind, direction):
    """A message of `kind` and `direction` from `who` still queued, owed or on its wire."""
    own = st[who]
    return any(isinstance(m, kind) and m.direction == direction for m in own[4] + own[5] + st[2 + who])


def starts(nodes, bound, both, diverged):
    """The start states: unjoined, or (--diverged) linked ends that disagree at rest."""
    if not diverged:
        return [(nodes[S].save(), nodes[R].save(), (), (), bound, bound, FILLERS, FILLERS)]
    linked = ((), (), True, True, True, False)              # owed, queue, recv, sent, opened, early
    none, counts, pushes, holds = (False,) * 4, (False, True, False, False), (True, False, False, False), \
        (True, True, False, False)
    pairs = [(none, counts), (pushes, none)]                # R counts S, S does not push; S pushes R, R does not count
    if both:                                                # every way the two ends can hold the relation, but
        ways = [none, counts, pushes, holds]                #   whole at both or at neither
        pairs = [(s, rr) for s in ways for rr in ways if not (s == rr and s[0] == s[1])]
    return [(s + linked, rr + linked, (), (), bound, bound, FILLERS, FILLERS) for s, rr in pairs]


def explore(doc, bound, both=False, diverged=False):
    code, has = functions(doc)
    nodes = {S: Node(code, "R", has, both), R: Node(code, "S", has, both)}
    inits = starts(nodes, bound, both, diverged)
    upkeep = UPKEEP_BOTH if both else UPKEEP
    parent, graph = {i: None for i in inits}, {}
    todo = deque(inits)
    r = dict(states=0, rest=0, disagree=0, unanswered=0, unlinked=0, early=0, unasked=0, unoffered=0,
             halves=0, unrepaired=0, trace=None, link_trace=None, early_trace=None, unrepaired_at=None, has=has)
    while todo:
        st = todo.popleft()
        r["states"] += 1
        s, rr = st[0], st[1]
        s_push, r_counts = s[0], rr[1]
        if s[9] or rr[9]:
            r["early"] += 1
            r["early_trace"] = r["early_trace"] or path(parent, st)
        acted = not diverged or st[4] < bound or st[5] < bound   # --diverged: once an upkeep has acted
        at_rest = not any((s[4], s[5], rr[4], rr[5], st[2], st[3]))
        if both and at_rest:                    # --both: a relation held one way only is acted on at any count
            if any(x[0] != x[1] and not acts(nodes[who], x) for who, x in ((S, s), (R, rr))):
                r["unrepaired"] += 1            # counted per state, as the other counts are
                r["unrepaired_at"] = r["unrepaired_at"] or (path(parent, st), held(s), held(rr))
        if at_rest and acted:
            r["rest"] += 1
            if s_push != r_counts or rr[0] != s[1]:     # each direction: the pusher's push_out, the other's push_in
                r["disagree"] += 1
                r["trace"] = r["trace"] or path(parent, st)
            if both and (s[0] != s[1] or rr[0] != rr[1]):
                r["halves"] += 1                        # --both: an end holding one direction only
                r["trace"] = r["trace"] or path(parent, st)
            if s[2] or s[3] or rr[2] or rr[3]:
                r["unanswered"] += 1
            if (s[8] or rr[8]) and not (s[6] and s[7] and rr[6] and rr[7]):
                r["unlinked"] += 1
                r["link_trace"] = r["link_trace"] or path(parent, st)
        elif s_push and not (r_counts or rr[3]) and not in_flight(st, R, Prune, IN):
            r["unasked"] += 1
        elif r_counts and not (s_push or s[2]) and not in_flight(st, S, Prune, OUT):
            r["unoffered"] += 1
        graph[st] = []
        for lab, n in successors(nodes, has, st, upkeep):
            graph[st].append(n)
            if n not in parent:
                parent[n] = (st, lab)
                todo.append(n)
    cycle = next((c for c in (find_cycle(graph, i) for i in inits) if c), None)
    r["acyclic"] = cycle is None
    if cycle:                                   # its steps, found again along the states
        r["cycle_trace"] = tuple([next(lab for lab, n in successors(nodes, has, a, upkeep) if n == b)
                                  for a, b in zip(sts, sts[1:])] for sts in cycle)
    return r


def path(parent, st):
    t = []
    while parent[st] is not None:
        st, lab = parent[st]
        t.append(lab)
    return t[::-1]


def find_cycle(graph, init):
    """None, or the first cycle reachable from init: (the states from init to it, its states round)."""
    colour, stack = {init: 1}, [(init, iter(graph[init]))]
    while stack:
        st, it = stack[-1]
        for n in it:
            c = colour.get(n, 0)
            if c == 1:
                states = [s for s, _ in stack]
                k = states.index(n)
                return states[:k + 1], states[k:] + [n]
            if c == 0:
                colour[n] = 1
                stack.append((n, iter(graph[n])))
                break
        else:
            colour[st] = 2
            stack.pop()
    return None


def acyclic(graph, init):
    return find_cycle(graph, init) is None


# ---- --model: the abstract comparison


@dataclass(frozen=True)
class St:
    s_own: int = 0          # at the GRAFT: S's push relation; answered: S has said "I will push you"
    s_heard: int = 0        # answered only: R's last word was "push me"
    r_own: int = 0          # at the GRAFT: R's in-relation; answered: R has said "push me"
    r_heard: int = 0        # answered only: S's last word was "I will push you"
    s2r: Tuple[str, ...] = ()
    r2s: Tuple[str, ...] = ()
    s_left: int = 0
    r_left: int = 0
    s_back: int = 0         # with the backoff: a PRUNE sent or received, the backoff not yet expired
    r_back: int = 0


def live(way, st, end):
    own, heard = (st.s_own, st.s_heard) if end == S else (st.r_own, st.r_heard)
    return own if way != "answered" else own and heard


def model_successors(way, st):
    """Each end's upkeep grafts when it is not in the relation and prunes when it is (bounded); a
    GRAFT that arrives may be accepted or refused. With the backoff, as gossipsub's: after sending
    or receiving a PRUNE a node neither grafts that peer nor accepts its GRAFT (it answers with a
    PRUNE) until the backoff expires, which here needs nothing of the exchange in flight."""
    backoff, out = way == "at the GRAFT, with a backoff", []
    if backoff and not st.s2r and not st.r2s:
        if st.s_back:
            out.append(("S's backoff expires", replace(st, s_back=0)))
        if st.r_back:
            out.append(("R's backoff expires", replace(st, r_back=0)))
    for end in (S, R):
        own, left, back = (st.s_own, st.s_left, st.s_back) if end == S else (st.r_own, st.r_left, st.r_back)
        wire = "s2r" if end == S else "r2s"
        pre = "s_" if end == S else "r_"
        if left:
            if not own and not (backoff and back):
                out.append((f"{NAME[end]} grafts", replace(st, **{pre + "own": 1, pre + "left": left - 1,
                                                                  wire: getattr(st, wire) + ("G",)})))
            elif own:
                kw = {pre + "own": 0, pre + "heard": 0, pre + "left": left - 1, wire: getattr(st, wire) + ("P",)}
                if backoff:
                    kw[pre + "back"] = 1
                out.append((f"{NAME[end]} prunes", replace(st, **kw)))
        their = "r2s" if end == S else "s2r"
        if getattr(st, their):
            m, rest = getattr(st, their)[0], getattr(st, their)[1:]
            base = replace(st, **{their: rest})
            back_now = st.s_back if end == S else st.r_back
            if m == "G":
                if way != "answered":
                    if own:
                        out.append((f"{NAME[end]} reads GRAFT, adds nothing", base))
                    elif backoff and back_now:
                        out.append((f"{NAME[end]} refuses GRAFT in backoff", replace(base, **{wire: getattr(st, wire) + ("P",)})))
                    else:
                        out.append((f"{NAME[end]} accepts GRAFT", replace(base, **{pre + "own": 1})))
                        kw = {wire: getattr(st, wire) + ("P",)}
                        if backoff:
                            kw[pre + "back"] = 1
                        out.append((f"{NAME[end]} refuses GRAFT", replace(base, **kw)))
                else:
                    heard = replace(base, **{pre + "heard": 1})
                    if own:
                        out.append((f"{NAME[end]} reads GRAFT: the yes, or a crossing", heard))
                    else:
                        out.append((f"{NAME[end]} accepts GRAFT, answers GRAFT",
                                    replace(heard, **{pre + "own": 1, wire: getattr(st, wire) + ("G",)})))
                        out.append((f"{NAME[end]} refuses GRAFT, answers PRUNE",
                                    replace(base, **{pre + "heard": 0, wire: getattr(st, wire) + ("P",)})))
            else:
                kw = {pre + "own": 0, pre + "heard": 0}
                if backoff:
                    kw[pre + "back"] = 1
                out.append((f"{NAME[end]} reads PRUNE", replace(base, **kw)))
    return out


def model_explore(way, bound):
    init = St(s_left=bound, r_left=bound)
    parent, graph, todo = {init: None}, {}, deque([init])
    r = dict(states=0, rest=0, disagree=0, trace=None, early=0)
    while todo:
        st = todo.popleft()
        r["states"] += 1
        ls, lr = live(way, st, S), live(way, st, R)
        if not st.s2r and not st.r2s:
            r["rest"] += 1
            if bool(ls) != bool(lr):
                r["disagree"] += 1
                r["trace"] = r["trace"] or path(parent, st)
        if (ls and not st.r_own and "P" not in st.r2s) or (lr and not st.s_own and "P" not in st.s2r):
            r["early"] += 1             # an end acts on a relation the other has not agreed to, nor is ending
        graph[st] = []
        for lab, n in model_successors(way, st):
            graph[st].append(n)
            if n not in parent:
                parent[n] = (st, lab)
                todo.append(n)
    r["acyclic"] = acyclic(graph, init)
    return r


WAYS = ("at the GRAFT, no backoff", "at the GRAFT, with a backoff", "answered")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bound", type=int, default=3, help="upkeep steps per node (default 3)")
    ap.add_argument("--doc", default=str(DOC2), help="the document whose §4.1 runs (default protocol-v2.md)")
    ap.add_argument("--model", action="store_true", help="the abstract comparison of the three ways")
    ap.add_argument("--both", action="store_true", help="a SYMMETRIC type's relation, grafted and pruned BOTH")
    ap.add_argument("--diverged", action="store_true", help="start from linked ends that disagree at rest")
    a = ap.parse_args(argv)
    ok = True
    if a.model:
        for b in range(1, a.bound + 1):
            print(f"upkeep steps per end at most {b}:")
            for way in WAYS:
                r = model_explore(way, b)
                print(f"  {way:30} {r['states']:6} states, {r['rest']:4} at rest, {r['disagree']:3} of them "
                      f"disagree; {r['early']:4} states act early; every exchange ends: {r['acyclic']}")
        for way in WAYS:
            r = model_explore(way, a.bound)
            if r["trace"]:
                print(f"the shortest disagreement, {way}: " + "; ".join(r["trace"]))
        return 0
    for b in range(1, a.bound + 1):
        r = explore(a.doc, b, a.both, a.diverged)
        missing = set(NAMES) - r["has"]
        print(f"upkeep steps per node at most {b}: {r['states']} states, {r['rest']} at rest"
              + (" (the starts apart)" if a.diverged else "") + "; "
              f"at rest the ends disagree in {r['disagree']}, "
              + (f"an end holds one direction only in {r['halves']}, " if a.both else "")
              + (f"an end's upkeep between its floor and its cap leaves a relation held one way in "
                 f"{r['unrepaired']}, " if a.both else "") +
              f"a GRAFT is unanswered in {r['unanswered']}, "
              f"a JOIN was sent and the link did not form at both ends in {r['unlinked']}; a GRAFT or PRUNE "
              f"reached a node with no link for it in {r['early']}; "
              f"in flight, S pushes unasked in {r['unasked']}, R counts an unoffered pusher in {r['unoffered']}; "
              f"every exchange ends: {r['acyclic']}" + (f"  (not in the document: {', '.join(sorted(missing))})"
                                                         if missing else ""))
        ok = (ok and not r["disagree"] and not r["unanswered"] and not r["unlinked"] and not r["early"]
              and not r["halves"] and not r["unrepaired"] and r["acyclic"] and (r["rest"] or not a.diverged))
        if a.diverged and not r["rest"]:
            print("  no state at rest was checked: the check is empty")
        if r["trace"]:
            print("  the shortest disagreement: " + "; ".join(r["trace"]))
        if r["unrepaired_at"]:
            to, hs, hr = r["unrepaired_at"]
            print(f"  a relation held one way that stays so, S holding {hs} and R {hr}: "
                  + ("; ".join(to) or "from the start"))
        if r["link_trace"]:
            print("  the shortest JOIN after which the link did not form: " + "; ".join(r["link_trace"]))
        if r["early_trace"]:
            print("  the shortest GRAFT or PRUNE that reached no link: " + "; ".join(r["early_trace"]))
        if r.get("cycle_trace"):
            to, loop = r["cycle_trace"]
            print("  an exchange that never ends: " + "; ".join(to) + "; then, round and round: " + "; ".join(loop))
    print("ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
