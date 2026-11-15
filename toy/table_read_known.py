#!/usr/bin/env python3
"""Known answers for §8.1's rule in the toy's tables: "reading it allocates nothing".

    python3 table_read_known.py

The document reads its per-peer and per-group tables as maps whose missing entries are empty, and some of its
decisions go by whether an entry is there at all (the writer's `if owed_answers[p]`, for one). Each table
here is read on one node of a small network, built and not run, the way the document reads it, for a peer and a
group it holds nothing for; then nothing may be in the table that was not there. Then one write through the
same reads (the control) must leave exactly the entry it wrote.

And the case that made the rule matter for the writer, found in review: reading
`owed_answers[p][G].empty()` used to leave an empty group under p, and `next_to_send(p)` then took it for an
answer owed and failed on `min` of an empty bitmap. Here `next_to_send(p)` must return nothing to send.
"""
import sys
from pathlib import Path

SEED, NODE, P = 7, 2, 1
G = bytes([0x55]) * 32                                      # a group the node knows nothing of


def shape(t):
    """What a table holds, level by level: keys and the entries' contents, as plain values."""
    if isinstance(t, dict):
        return {k: shape(v) for k, v in dict.items(t)}
    if hasattr(t, "urgent") and hasattr(t, "normal"):
        return (list(t.urgent), list(t.normal))
    if hasattr(t, "v"):
        return sorted(t)
    return t


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run
    import sim as S
    import wire as Wm
    from bits import Bits, popcount
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)])
    ns = got["sim"].nodes[NODE].ns
    bad = 0

    def line(what, got_, want):
        nonlocal bad
        bad += got_ != want
        print(f"{what}: {got_}{'' if got_ == want else f'  <-- must be {want}'}")

    entry = Wm.Entry(control=Wm.IWANT([Wm.WantIndex(G, 0)]))
    a, k, root = Wm.WantIndex(G, 0), (G, 0), bytes([0x66]) * 32
    cases = [                       # table, the reads (as the document makes them), one write through them, its key
        ("owed", lambda t: (bool(t[P]), t[P][G].empty(), list(t[P])), lambda t: t[P][G].__ior__({3}), P),
        ("owed_answers", lambda t: (bool(t[P]), t[P][G].empty(), t[P][G].has(3)), lambda t: t[P][G].set(3), P),
        ("queue", lambda t: (bool(t[P].urgent), bool(t[P].normal), t[P].has_chunks(), [e for e in t[P].normal]),
         lambda t: t[P].normal.append(entry), P),
        ("tried", lambda t: (P in t[a], t.get(a, {}), list(t[a])), lambda t: t[a].__setitem__(P, 1.0), a),
        ("offered", lambda t: (t[P][G].has(0), Bits() | t[P][G], G in t[P], t[P].pop(G, None)),
         lambda t: t[P][G].set(0), P),
        ("asked_parked", lambda t: (P in t[k], len(t[k]), t[k].discard(P)), lambda t: t[k].add(P), k),
        ("park", lambda t: (t[P].get(G, -1.0), t[P].pop(G, None)), lambda t: t[P].__setitem__(G, 1.0), P),
        ("pending", lambda t: ([x for x in t[root]], bool(t[root]), t.get(root, [])),
         lambda t: t[root].append((P, None)), root),
        ("chunks", lambda t: (t.get(G), 0 in t[G], len(t[G])), lambda t: t[G].__setitem__(0, "a chunk"), G),
        ("known_id", lambda t: (t[G].get(0), 0 in t[G]), lambda t: t[G].__setitem__(0, b"an id"), G),
        ("received", lambda t: (t[G].has(0), popcount(t[G])), lambda t: t[G].set(0), G),
        ("mine", lambda t: (t[G].has(0), popcount(t[G]), Bits() | t[G]), lambda t: t[G].set(0), G),
        ("holders", lambda t: (len(t[G][0]), P in t[G][0], list(t[G])), lambda t: t[G][0].add(P), G),
        ("sent_to", lambda t: (t[P][G].has(0), list(t[P])), lambda t: t[P][G].set(0), P),
        ("unwanted", lambda t: (b"an id" in t[P], len(t[P])), lambda t: t[P].add(b"an id"), P),
        ("serve_count", lambda t: (t[P][G], list(t[P])), lambda t: t[P].__setitem__(G, t[P][G] + 1), P),
    ]
    line("the tables are the toy's lazy ones (a check that the node uses them)",
         sorted(n for n, *_ in cases if type(ns[n]).__name__ == "LazyDict"), sorted(n for n, *_ in cases))
    for name, read, write, key in cases:
        t = ns[name]
        before = shape(t)
        read(t)
        line(f"{name}: read for a peer and a group it holds nothing for; the table as it was", shape(t) == before, True)
        write(t)
        after = shape(t)
        new = {k_: v for k_, v in after.items() if before.get(k_) != v}
        line(f"{name}: one write through the same reads (the control); what is new", list(new), [key])

    for name in ("owed", "owed_answers", "queue"):          # the writer's case, from a clean state for P
        ns[name].pop(P, None)
    ns["owed_answers"][P][G].empty()
    try:
        out = ns["next_to_send"](P)
    except ValueError as err:
        out = f"failed: {err}"
    line("the writer, after a read of owed_answers[p][G].empty(): next_to_send(p)", out, None)
    print("ok" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
