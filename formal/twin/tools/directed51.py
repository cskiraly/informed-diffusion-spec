#!/usr/bin/env python3
"""Directed records for publish (protocol.md lines 1000-1032 at v0.10.4). The toy's own publish is called in a
toy node's namespace on generated states, and trace3.py's tracer logs each call with the node's whole state.

    python3 directed51.py TOYDIR OUT.jsonl.gz [--n N] [--seed S]

A record here holds a whole publish (each chunk built, stored, planned and queued), ten and more times another
set's record: **N // 10 calls are made**, so that `--n 20000`, every set's in the record's run, gives 2,000
records.

What the records reach that the cells do not (a cell publishes a coded group once, on an empty node whose queues
have room, at a slot inside the live window):
- **the two ways out before anything is written**: the group expired; the slot past its live window;
- **a plain group** (MAX_CHUNKS is 8 at these nodes, so a body of five units and more is not coded) beside coded
  ones of 2, 4, 6 and 8 chunks;
- **a push the queue refuses** (unpush: owed instead), a few of a publish's or all of them;
- **a group published again** (the state of the publish before is kept: `planned[g]`'s row replaced whole, `origin`
  back to nothing, the peers' `pushed` entries there already), also with other shards of another descriptor at
  another slot;
- **shards the descriptor does not count** (an index at N(d) and beyond: stored, never planned) and **an index
  twice** (the second chunk replaces the first in the store; both are stored, each with its id);
- **peers that hold chunks already** (candidates_for_source leaves them out), no mesh at all, a mesh smaller than
  R; the stripe's pool (node 3: every connected topic peer) with R = 3;
- **SOURCE_OFFERS = PUBLISH** (node 4): the offers to the mesh peers not pushed a chunk, at publish;
- a slot beyond a uint64 (group_key raises: the record's `raises`).

Not drawn, each a limit of this set: a descriptor of no chunk; a descriptor that counts more chunks than the
shards give (`chunks[g][i]` raises: no record can hold another section's read that raises); a shard's index
beyond a uint32 (the toy's store raises in its own message_id, a call that is not written when it raises).

The descriptors and shards are build_group's own, made before the tracer is installed (so they are no records
here). The scenario answers expired, live, connected_topic_peers and the push order's two keys (as directed54's),
and draws enqueue's refusals; the store, the seen set, the gossip history and content_id are the toy's own. Three
nodes of a 5-node cell built as run.py builds it: node 2 as it is, node 3 at the stripe's uplink with R = 3, node 4
at SOURCE_OFFERS = PUBLISH. A sample on which the Python raises is written with `raises` by the tracer; the counts
are printed.
"""
import argparse
import random
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace3                           # noqa: E402

CLEARED = ("asked_at", "promises", "last_resort_armed", "tried", "offered", "asked_parked", "park",
           "stop_pull", "queue", "mine", "known_id", "ihave_frames", "ihave_asked", "held_back", "desc",
           "received", "state", "origin", "pending_ids", "pending", "chunks", "tie_slot", "owed",
           "owed_answers", "sent_to", "slot_held", "peer_has", "pushed", "holders", "pace_queue", "planned")


class Scenario:
    def __init__(self):
        self.tie, self.ids, self.expired, self.connected, self.live, self.refuse = {}, {}, set(), [], True, 0.0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("toy")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    toy = Path(a.toy).resolve()
    tr = trace3.Tracer3(toy, a.out, ["directed51", f"--n={a.n}", f"--seed={a.seed}"], whole=True)
    import bits as B                    # noqa: E402: the pinned toy's
    import run                          # noqa: E402
    import sim as S                     # noqa: E402
    Wm = tr.Wm
    got = {}
    run.run = lambda cfg, out=sys.stdout: got.setdefault("sim", S.Sim(cfg))
    run.main(["--nodes", "5", "--degree", "4", "--msgs", "1", "--payload", "16384", "--seed", "7"])
    sc = Scenario()
    rng = random.Random(a.seed)
    nodes = {}
    built = None
    for k in (2, 3, 4):
        nd = got["sim"].nodes[k]
        ns = nd.ns
        ns["MAX_CHUNKS"] = 8            # a body of five units and more is a plain group (read by build_group below
        #                                 and by the tracer at install: the node's constant)
        if built is None:               # build_group's own results, before the tracer is installed: no records
            unit = int(ns["UNIT"])
            built = [ns["build_group"](Wm.Blob(n, ("payload", j)))
                     for j, n in enumerate((1, unit, unit + 1, 3 * unit, 4 * unit, 5 * unit, 6 * unit + 3))]
            gid_of, key_of = ns["group_id"], ns["group_key"]            # the document's, untraced still
            assert [(d.version, d.count) for d, _ in built] == [(2, 2), (2, 2), (2, 4), (2, 6), (2, 8), (1, 5), (1, 7)], \
                [(d.version, d.count) for d, _ in built]
        ns["expired"] = lambda g: g in sc.expired
        ns["live"] = lambda slot: sc.live
        ns["connected_topic_peers"] = lambda: list(sc.connected)
        ns["tiebreak"] = lambda f, p: sc.tie[p]
        ns["peer_id_bytes"] = lambda p: sc.ids[p]

        def enqueue(p, x, urgent=False, own=ns["enqueue"]):         # the toy's own, but for the refusals drawn
            return False if not urgent and rng.random() < sc.refuse else own(p, x, urgent)
        ns["enqueue"] = enqueue
        if k == 3:                      # at the stripe's uplink: the source's pool is every connected peer [c13]
            ns["UPLINK"] = ns["STRIPE_UPLINK"] = 1e9
            ns["R"] = 3
        if k == 4:
            ns["SOURCE_OFFERS"] = ns["PUBLISH"]
        tr.install(nd, ns)
        nodes[k] = (nd, ns)
    assert int(nodes[2][1]["R"]) == 2 and nodes[2][1]["SOURCE_OFFERS"] != nodes[2][1]["PUBLISH"]
    Shard = type(built[0][1][0])

    def shard(index, like):
        try:
            return Shard(index=index, proof=like.proof, data=like.data)
        except TypeError:
            return types.SimpleNamespace(index=index, proof=like.proof, data=like.data)

    raised, kinds = Counter(), Counter()
    last = {}                           # per node: the publish before, for a group published again

    for _ in range(max(1, a.n // 10)):
        k = rng.choice((2, 2, 3, 4))
        nd, ns = nodes[k]
        ns["now"] = rng.choice([1.0, 3.25])
        peers = rng.sample(range(1, 64), rng.randrange(0, 9))
        again = k in last and rng.random() < 0.25
        d, shards = rng.choice(built)
        slot = rng.choice([1, 1, 2, 7, 2 ** 32, 2 ** 64 - 1])
        if again and rng.random() < 0.7:        # the same group: the same descriptor at the same slot
            d, shards, slot = last[k]
        if rng.random() < 0.02:
            slot = 2 ** 64                      # group_key raises
        n = int(d.count)
        shards = list(shards)
        extra = twice = False
        r = rng.random()
        if r < 0.12:                            # an index the descriptor does not count: stored, never planned
            shards.insert(rng.randrange(len(shards) + 1), shard(n + rng.choice([0, 1, 5]), rng.choice(shards)))
            extra = True
        elif r < 0.24:                          # an index twice: the later chunk is the store's
            j = rng.randrange(len(shards))
            shards.insert(rng.randrange(j + 1, len(shards) + 1), shard(shards[j].index, rng.choice(shards)))
            twice = True
        gid = gid_of(d)
        g = key_of(gid, slot) if slot < 2 ** 64 else None
        sc.__init__()
        r = rng.random()
        sc.refuse = 0.0 if r < 0.6 else 1.0 if r < 0.7 else rng.choice([0.2, 0.5])
        sc.live = rng.random() >= 0.08
        if g is not None and rng.random() < 0.08:
            sc.expired = {g}
        wide = rng.random() < 0.5
        for q in range(1, 64):
            sc.tie[q] = rng.randrange(1 << 64) if wide else rng.choice([0, 1, 2, (1 << 64) - 1])
            sc.ids[q] = bytes([rng.choice([0, 0x80]), q])

        # ---- the state: cleared and drawn, or the publish before's, kept
        if not again:
            for name in CLEARED:
                ns[name].clear()
            ns["offers"]._d.clear()
            ns["offers"].listed.clear()
            ns["tied"]._d.clear()
            nd._by_index.clear()
            nd.writer_kicked.clear()
            for w in ns["gossip_history"].windows:
                w.clear()
            mesh = rng.sample(peers, rng.randrange(len(peers) + 1))
            ns["mesh"] = set(mesh)
            if g is not None:
                for q in peers:
                    r = rng.random()
                    if r < 0.3:                 # a peer that holds chunks of the group already (as on_have leaves it)
                        h = ns["peer_has"][q][g]
                        h.bits = B.Bits((1 << n) - 1 if r < 0.04 else rng.randrange(1 << n))
                        h.ttl = int(ns["HAVE_TTL"])
                    if rng.random() < 0.2:
                        ns["queue"][q].normal.append(Wm.Entry(control=Wm.IHAVE(Wm.HaveBitmap(
                            group=bytes([0x11]) * 32, bits=B.Bits(rng.randrange(1, 1 << 4))))))
        mesh = sorted(ns["mesh"])
        sc.connected = rng.sample(peers, rng.randrange(len(peers) + 1))
        block = S.Block(slot, bytes([0xa1 + (slot % 3)]) * 32, gid)

        # ---- the call
        stripe = ns["UPLINK"] >= ns["STRIPE_UPLINK"]
        pool = sc.connected if stripe else mesh
        if g is None:
            kind = "a slot beyond a uint64 (group_key raises)"
        elif g in sc.expired:
            kind = "the group expired"
        elif not sc.live:
            kind = "past its live window"
        else:
            kind = (("a plain group" if d.version == 1 else "a coded group") + f" of {n}"
                    + (", published again" if again else "")
                    + (", a shard the descriptor does not count" if extra else ", an index twice" if twice else "")
                    + (", nobody to push to" if not pool else ", a pool under R" if len(pool) < int(ns["R"]) else "")
                    + (", every push refused" if sc.refuse == 1.0 and pool else ", some pushes refused" if sc.refuse and pool else "")
                    + (", at PUBLISH" if k == 4 else ", the stripe's pool" if k == 3 else ""))
        kinds[kind] += 1
        try:
            ns["publish"](block, d, shards)
            if g is not None and g not in sc.expired and sc.live:
                # a later "again" takes build_group's own shards of that descriptor, at that slot
                last[k] = (d, next(sh for dd, sh in built if dd is d), slot)
        except Exception as e:              # noqa: BLE001: the tracer wrote it, with `raises`
            raised[type(e).__name__] += 1
    tr.close()
    print(f"directed51: {sum(tr.counts.values())} records, raised {dict(raised)}, {dict(sorted(tr.counts.items()))}",
          file=sys.stderr)
    for kk, c in sorted(kinds.items()):
        print(f"  {kk}: {c}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
