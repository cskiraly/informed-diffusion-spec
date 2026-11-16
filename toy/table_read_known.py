#!/usr/bin/env python3
"""Known answers for §8.1's rule in the toy's tables: "reading it allocates nothing".

    python3 table_read_known.py
    python3 table_read_known.py --doc v2     # and the tables protocol-v2.md adds, on a node of its own

The document reads its per-peer and per-group tables as maps whose missing entries are empty, and some of its
decisions go by whether an entry is there at all (the writer's `if owed_answers[p]`, for one). Each table
here is read on one node of a small network, built and not run, the way the document reads it, for a peer and a
group it holds nothing for; then nothing may be in the table that was not there. Then one write through the
same reads (the control) must leave exactly the entry it wrote, with exactly what it wrote in it.

Then what a write through a held read does:
- two reads of one missing key, held at once, give one entry, so that a write through either is seen through
  both (for a one-level table, a two-level one, and the per-peer maps of `pushed` and `tied`);
- a held read written after another value was set under its key fails, since the write would be lost;
- the writes of the collections' own APIs that a document could use (`|=` on a dict, a set's symmetric
  difference, a slice assigned to a list or a queue's lane, a bitmap's value set, `|=` on a push entry or a
  tie) join the table as `set`, `add` and `append` do;
- an offer list refuses every change but `append` and `remove`, which keep `listed`, and `offers` refuses a
  list set into it.

And the case that made the rule matter for the writer, found in review: reading
`owed_answers[p][G].empty()` used to leave an empty group under p, and `next_to_send(p)` then took it for an
answer owed and failed on `min` of an empty bitmap. Here `next_to_send(p)` must return nothing to send.
"""
import sys
from pathlib import Path

SEED, NODE, P = 7, 2, 1
V2 = sys.argv[1:] == ["--doc", "v2"]
G = bytes([0x55]) * 32                                      # a group the node knows nothing of


def shape(t):
    """What a table holds, level by level: keys and the entries' contents, as plain values."""
    if isinstance(t, dict):
        return {k: shape(v) for k, v in dict.items(t)}
    if hasattr(t, "_d"):                                    # a LazyMap: peer_has[p], pushed[p]
        return {k: shape(v) for k, v in t.items()}
    if hasattr(t, "bits"):                                  # a HAVE entry
        return sorted(t.bits)
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
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", str(SEED)]
             + (["--doc", "v2"] if V2 else []))
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
        ("peer_has", lambda t: (G in t[P], t[P][G].has(0), t[P][G].ttl, list(t[P])),
         lambda t: setattr(t[P][G], "bits", Bits(1)), P),
        ("pushed", lambda t: (G in t[P], t[P][G].has(0), t[P][G].first_push), lambda t: t[P][G].set(0), P),
    ]
    wrote = {"owed": {G: [3]}, "owed_answers": {G: [3]}, "queue": ([], [entry]), "tried": {P: 1.0},
             "offered": {G: [0]}, "asked_parked": {P}, "park": {G: 1.0}, "pending": [(P, None)],
             "chunks": {0: "a chunk"}, "known_id": {0: b"an id"}, "received": [0], "mine": [0], "holders": {0: {P}},
             "sent_to": {G: [0]}, "unwanted": {b"an id"}, "serve_count": {G: 1}, "peer_has": {G: [0]}, "pushed": {G: [0]}}
    if V2:                          # protocol-v2.md's own tables (§3), read as its code reads them
        T, fam, c = "column", 5, 0                          # an object type, a family and a colour
        PV = 99                                             # a peer the node holds nothing for (peer 1 has JOINed)
        rel = (lambda t: (c in t[PV][T][fam], len(t[PV][T][fam]), list(t[PV][T])), lambda t: t[PV][T][fam].add(c), PV)
        cases += [
            ("rebuilt", lambda t: (t[G].has(0), popcount(t[G])), lambda t: t[G].set(0), G),
            ("served", lambda t: (t[PV][G], list(t[PV])), lambda t: t[PV].__setitem__(G, t[PV][G] + 1), PV),
            ("want_p", lambda t: (t[PV].get(G), G in t[PV]), lambda t: t[PV].__setitem__(G, "a want"), PV),
            ("join_recv", lambda t: (t[PV].get(T), T in t[PV]), lambda t: t[PV].__setitem__(T, "a join"), PV),
            ("join_sent", lambda t: (t[PV].get(T), T in t[PV]), lambda t: t[PV].__setitem__(T, "a join"), PV),
            ("push_out", *rel), ("push_in", *rel), ("grafted_out", *rel), ("grafted_in", *rel),
            ("owed_relations", lambda t: (list(t[PV]), bool(t[PV])), lambda t: t[PV].append("a JOIN"), PV),
            ("backoff", lambda t: (t[PV][T][fam].get(c), c in t[PV][T][fam]),
             lambda t: t[PV][T][fam].__setitem__(c, 1.0), PV),
            ("standing", lambda t: (P in t[G][0], t[G].get(0, ()), list(t[G])), lambda t: t[G][0].add(P), G),
            ("claims", lambda t: (P in t[G], len(t[G])), lambda t: t[G].add(P), G),
            ("probe_served", lambda t: (t[PV][G], G in t[PV]), lambda t: t[PV].__setitem__(G, True), PV),
            ("probe_answers", lambda t: (t[PV][G].has(0), list(t[PV])), lambda t: t[PV][G].set(0), PV),
            ("probe_waiting", lambda t: (PV in t[G], t[G].get(PV), list(t[G])), lambda t: t[G].__setitem__(PV, 0), G),
            ("rsample", lambda t: (list(t[G]), len(t[G]), 0 in t[G]), lambda t: t[G].append(0), G),
            ("rsample_asked", lambda t: (P in t[G][0], list(t[G])), lambda t: t[G][0].add(P), G),
            ("sampled_from", lambda t: (P in t[G], len(t[G])), lambda t: t[G].add(P), G),
            ("held_samples", lambda t: (list(t[G]), bool(t[G])), lambda t: t[G].append((G, 0)), G),
        ]
        wrote.update({"rebuilt": [0], "served": {G: 1}, "want_p": {G: "a want"}, "join_recv": {T: "a join"},
                      "join_sent": {T: "a join"}, "owed_relations": ["a JOIN"], "backoff": {T: {fam: {c: 1.0}}},
                      "standing": {0: {P}}, "claims": {P}, "probe_served": {G: True}, "probe_answers": {G: [0]}, "probe_waiting": {PV: 0},
                      "rsample": [0], "rsample_asked": {0: {P}}, "sampled_from": {P}, "held_samples": [(G, 0)]})
        wrote.update({n: {T: {fam: {c}}} for n in ("push_out", "push_in", "grafted_out", "grafted_in")})
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
        line(f"{name}: one write through the same reads (the control); what is new, and what is in it",
             new, {key: wrote[name]})

    from bits import PushEntry
    P2, G2, R2 = 9, bytes([0x5A]) * 32, bytes([0x6A]) * 32   # keys nothing holds yet
    x, y = ns["mine"][G2], ns["mine"][G2]
    x.set(1)
    line("held reads, one level (mine): the two the same, the write seen through the other, in the table",
         (x is y, y.has(1), G2 in ns["mine"]), (True, True, True))
    x, y = ns["owed"][P2][G2], ns["owed"][P2]
    x.set(1)
    line("held reads, two levels (owed): the write seen through the peer's map, both levels in the table",
         (y[G2].has(1), P2 in ns["owed"], G2 in ns["owed"][P2]), (True, True, True))
    x, y = ns["pushed"][P2][G2], ns["pushed"][P2][G2]
    x.set(1)
    line("held reads, a per-peer map (pushed): the two the same, the write seen, in the table",
         (x is y, y.has(1), P2 in ns["pushed"] and G2 in ns["pushed"][P2]), (True, True, True))
    x, y = ns["tied"][R2][P2][G2], ns["tied"][R2][P2][G2]
    x.set(1)
    line("held reads, three levels (tied): the two the same, the write seen, in the table",
         (x is y, y.has(1), R2 in ns["tied"] and P2 in ns["tied"][R2]), (True, True, True))

    def fails(write):
        try:
            write()
        except AssertionError:
            return "fails"
        return "passes"
    G3 = bytes([0x5B]) * 32
    x = ns["mine"][G3]
    ns["mine"][G3] = Bits(4)
    line("a held read written after a value was set under its key (mine)", fails(lambda: x.set(1)), "fails")
    x = ns["pushed"][P2][G3]
    ns["pushed"][P2][G3] = PushEntry()
    line("a held read written after a value was set under its key (pushed)", fails(lambda: x.set(1)), "fails")

    G4, a4, r4 = bytes([0x5C]) * 32, Wm.WantIndex(bytes([0x5C]) * 32, 1), bytes([0x6B]) * 32
    held = {"tried": ns["tried"][a4], "unwanted": ns["unwanted"][P2], "pending": ns["pending"][r4],
            "queue": ns["queue"][P2], "mine": ns["mine"][G4], "pushed": ns["pushed"][P2][G4],
            "tied": ns["tied"][r4][P2][G4]}
    held["tried"] |= {P: 1.0}
    held["unwanted"].symmetric_difference_update({b"an id"})
    held["pending"][:] = [(P, None)]
    held["queue"].normal[:] = [entry]
    held["mine"].v = 1
    held["pushed"] |= {2}
    held["tied"] |= {3}
    joined = {"tried": a4 in ns["tried"], "unwanted": P2 in ns["unwanted"], "pending": r4 in ns["pending"],
              "queue": P2 in ns["queue"], "mine": G4 in ns["mine"], "pushed": G4 in ns["pushed"][P2],
              "tied": r4 in ns["tied"]}
    line("the collections' own writes through a held read: the tables they joined", sorted(k_ for k_, v in joined.items() if v),
         sorted(joined))

    def refused(change):
        try:
            change()
        except TypeError:
            return "refused"
        return "done"
    a5 = Wm.WantIndex(bytes([0x5D]) * 32, 0)
    line("an offer list: insert, and a list set into offers", (refused(lambda: ns["offers"][a5].insert(0, P)),
         refused(lambda: ns["offers"].__setitem__(a5, []))), ("refused", "refused"))

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
