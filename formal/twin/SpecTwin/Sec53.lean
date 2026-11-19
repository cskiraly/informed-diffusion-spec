import SpecTwin.Readers

/-! # The twin of protocol.md §5.3, "Whom to push to: furthest behind first" [c16] (v0.10.4, spec 34f60f8):
`choose_push` and `guard_fails` (lines 1228–1247)

- **The push order's keys are questions:** for each candidate, in the candidates' order, the node
  answers `tiebreak(f, p)`, a number, and `peer_id_bytes(p)`, the peer's id as bytes (their hex here: of ids of
  one length, the hex digits order as the bytes do). The twin sorts as the Python does: `sorted(…, reverse=True)`
  puts the largest key first and keeps equal elements in their first order, and `list.sort` is stable; both are a
  stable merge sort here.
- **`known` and `unproven`** are the Python's two dicts, each made in the candidates' order before any key is
  asked. A candidate named twice has one value in each.
- **The draw** is a question (`sample_without_replacement`), asked of the pool with `min(budget,
  len(pool))`, also where that is none of them.
- **`guard_fails` reads as the Python's `and` does:** the peer's HAVEs are looked at only where the first two
  tests hold. An entry of `pushed` with bits and no clock is in no state of the toy's; there the Python raises on
  `now - None`, and so does the twin. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `guard_fails(p, g)` (lines 1244–1247) [c16]: the proof guard -/
def guardFails (p : Peer) (g : Group) : M m Bool := do
  enter "guard_fails"
  let e := (← pushedEntry? p g).getD {}                     -- `e = pushed[p][g]`
  if e.bits.popcount < (← read).c.R_NODE then               -- `popcount(e) >= R_NODE and …`
    branch "guard_fails: fewer than R_NODE pushed"
    return false
  let some first := e.firstPush                             -- `now - e.first_push`
    | crash "TypeError: unsupported operand type(s) for -: 'float' and 'NoneType' (guard_fails: no first push)"
  if !((← read).now - Float.ofBits first > (← read).c.GUARD_GRACE) then
    branch "guard_fails: within the grace"
    return false
  let heard := (← peerHasEntry? p g).isSome                 -- `g not in peer_has[p]`: no HAVE at all from p for g
  branch (if heard then "guard_fails: a HAVE seen" else "guard_fails: demoted")   --   while we keep pushing it
  return !heard

/-- `choose_push(f, cands, budget, at_source)` (lines 1228–1242) [c16] -/
def choosePush (f : ChunkF) (cands : List Peer) (budget : Nat) (atSource : Bool) : M m (List Peer) := do
  enter "choose_push"
  if budget ≥ cands.length then                             -- everyone, no ordering needed
    branch "choose_push: everyone"
    return cands
  let g := f.g
  -- `known = {p: popcount(peer_has[p][g].bits | pushed[p][g]) for p in cands}`  [c16]
  let mut known : List (Peer × Nat) := []
  for p in cands do
    known := known ++ [(p, ((← peerHas p g) ||| (← pushed p g)).popcount)]
  -- `unproven = {p: guard_fails(p, g) for p in cands}`  [c16]
  let mut unproven : List (Peer × Bool) := []
  for p in cands do
    unproven := unproven ++ [(p, ← guardFails p g)]
  -- `order = sorted(cands, key=lambda p: (tiebreak(f, p), peer_id_bytes(p)), reverse=True)`: each key asked once,
  -- in the candidates' order, then the sort
  let mut keys : List (Peer × (Nat × String)) := []
  for p in cands do
    let t ← tiebreak f p
    keys := keys ++ [(p, (t, ← peerIdBytes p))]
  let key (p : Peer) : Nat × String := (keys.lookup p).getD (0, "")
  let larger (a b : Nat × String) : Bool := a.1 > b.1 || (a.1 == b.1 && a.2 > b.2)
  let order0 := cands.mergeSort fun a b => !(larger (key b) (key a))
  -- `order.sort(key=lambda p: (unproven[p], known[p]))`: stable: equal counts keep the tie-break
  let rank (p : Peer) : Nat × Nat := (if (unproven.lookup p).getD false then 1 else 0, (known.lookup p).getD 0)
  let mut order := order0.mergeSort fun a b =>
    (rank a).1 < (rank b).1 || ((rank a).1 == (rank b).1 && (rank a).2 ≤ (rank b).2)
  if !atSource then                                         -- [c16] safer form
    let ok := order.filter fun p => (rank p).1 == 0         -- `[p for p in order if not unproven[p]]`
    if ok.isEmpty then
      branch "choose_push: nobody proven"
    else
      let median := (rank (ok.getD ((ok.length - 1) / 2) 0)).2   -- `known[ok[(len(ok) - 1) // 2]]`
      let pool := ok.filter fun p => (rank p).2 ≤ median
      let drawn ← sample pool (min budget pool.length)      -- `sample_without_replacement(pool, min(budget, len(pool)))`
      order := drawn ++ order.filter fun p => !drawn.contains p
      branch "choose_push: drawn from the lower half"
  else
    branch "choose_push: at the source"
  return order.take budget                                  -- `order[:budget]`

end SpecTwin
