import SpecTwin.Tables

/-! # §4.2's two readers, `held(a)` and `tied_to_root(p, a)`: the twin's own code (v0.10.4, spec
34f60f8)

`mine` and `tied` are the twin's own tables, since its own code writes them, so the two readers are code over
them, and their reads go into a record's reads.

- `held(a)` is the toy's (`toy/node.py` 648–650: an ask's chunk is in `mine`):
  `group_index(a) is not None and mine[group].has(index)`. Every ask key has a group and an index (`Key`), so
  the first test always holds here.
- `tied_to_root(p, a)` is protocol.md's (line 526): `any(t[p][group(a)].has(index(a)) for t in tied.values())`.
  The Python reads `tied` as a whole (`tied.values()`), then `t[p][group(a)]` for each root until one has the
  index. The twin reads the whole table once and decides from it: the same answer, and a subset of the Python's
  reads. A missing row or bitmap has no index. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `peer_has[p][g].bits`: what p has said it holds of g; nothing where it sent no HAVE for g. The twin's own
table, which on_have writes. -/
def peerHas (p : Peer) (g : Group) : M m Bits := do
  return ((← peerHasEntry? p g).map (·.bits)).getD 0

/-- `pushed[p][g]` as a bitmap: what the node chose to push p of g; nothing where no entry is. The twin's own
table, which note_push writes. -/
def pushed (p : Peer) (g : Group) : M m Bits := do
  return ((← pushedEntry? p g).map (·.bits)).getD 0

/-- `len(holders[g][i])`: how many of our peers hold the chunk. -/
def holders (g : Group) (i : Nat) : M m Nat := do
  return (← holdersOf g i).size

/-- `held(a)`: the node holds a's chunk: its index is in `mine[group(a)]` -/
def held (a : Key) : M m Bool := do
  enter "held"
  return (← mineBits a.group).has a.index

/-- `tied_to_root(p, a)` (§4.2): a copy of a's chunk from p waits for a root -/
def tiedToRoot (p : Peer) (a : Key) : M m Bool := do
  enter "tied_to_root"
  let all ← allTiedAll
  return all.any fun (_, peers) => peers.any fun (q, groups) =>
    q == p && groups.any fun (g, bits) => g == a.group && bits.has a.index

end SpecTwin
