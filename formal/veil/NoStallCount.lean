import Lean

/-! # No stall: the counting (Q1's third piece)

`NoStallTransport.lean` and `NoStallAsk.lean` give, for any one chunk, the per-link step: when nothing
is pending, a node that has its block holds every chunk a mesh neighbour received, or has stopped
pulling the group (the transport delivers the chunk or leaves the neighbour's offer, and the asking
resolves the offer). A node that has not stopped holds only chunks it received: it rebuilds only
after its decode claim (`NoStallTransport`'s `stored`). The step from there to Q1 is counting, here
in plain Lean, without Veil:

- a node stops pulling at its K-th received chunk, and the source holds all N of them (N ≥ K);
- with nothing pending, a node that has received K chunks has made its decode claim (§4.2 makes it at
  the K-th, so it is not left pending);
- so, by induction along mesh paths from the source, every node connected to it has stopped: its
  stopped neighbour received at least K chunks, each of which it holds, received, or it has stopped;
- and its decode, no longer pending, has returned: with an honest builder's code, the node is
  complete.

The hypotheses are the per-link step, the two counting facts, and the decode's outcome; the theorem
is about any node type, any mesh and any N and K. -/

namespace NoStallCount

/-- how many of the group's N chunks `r` holds -/
def count {N : Nat} (r : Fin N → Bool) : Nat := (List.finRange N).countP r

theorem count_mono {N : Nat} {r s : Fin N → Bool} (h : ∀ i, r i = true → s i = true) :
    count r ≤ count s :=
  List.countP_mono_left (fun i _ hi => h i hi)

/-- connected to the source along mesh links -/
inductive Reach {Node : Type} (mesh : Node → Node → Prop) (src : Node) : Node → Prop
  | here : Reach mesh src src
  | step {m n : Node} : Reach mesh src m → mesh m n → Reach mesh src n

/-- every node connected to the source has stopped pulling: it reached K -/
theorem every_connected_node_stops {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (src : Node)
    (rcv : Node → Fin N → Bool) (stop : Node → Prop)
    (source_stopped : stop src)
    -- a node stops at its K-th received chunk; the source holds all N, at least K
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    -- nothing pending: a node that has received K chunks has made its decode claim
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    -- the per-link step, for every chunk (`NoStallTransport`, `NoStallAsk`)
    (link : ∀ m n i, mesh m n → rcv m i = true → rcv n i = true ∨ stop n) :
    ∀ n, Reach mesh src n → stop n := by
  intro n h
  induction h with
  | here => exact source_stopped
  | @step m n' _ hmn ih =>
    by_cases hs : stop n'
    · exact hs
    · apply K_has_stopped
      have hK := stopped_has_K m ih
      have hle : count (rcv m) ≤ count (rcv n') := count_mono fun i hi => by
        rcases link m n' i hmn hi with h | h
        · exact h
        · exact absurd h hs
      omega

/-- Q1: every node connected to the source is complete, once its decode, no longer pending, has
returned with an honest builder's code -/
theorem every_connected_node_completes {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (src : Node)
    (rcv : Node → Fin N → Bool) (stop complete : Node → Prop)
    (source_stopped : stop src)
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → rcv m i = true → rcv n i = true ∨ stop n)
    -- nothing pending: a stopped node's decode has returned, and an honest code decodes
    (decoded : ∀ n, stop n → complete n) :
    ∀ n, Reach mesh src n → complete n := fun n h =>
  decoded n (every_connected_node_stops K mesh src rcv stop source_stopped stopped_has_K
    K_has_stopped link n h)

end NoStallCount

-- the audit, a failure a build error: both theorems rest on Lean's own axioms only
open Lean Elab Command in
#eval show CommandElabM Unit from do
  let allowed := [``propext, ``Classical.choice, ``Quot.sound]
  let mut rest : Std.HashSet Name := {}
  for n in [``NoStallCount.every_connected_node_stops,
      ``NoStallCount.every_connected_node_completes] do
    for a in ← liftCoreM (collectAxioms n) do
      rest := rest.insert a
      unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"the two theorems rest on {rest.toList}"
