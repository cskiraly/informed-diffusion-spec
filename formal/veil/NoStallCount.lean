import Lean

/-! # No stall: the counting (Q1's third piece)

`NoStallTransport.lean` and `NoStallAsk.lean` give, for any one chunk, the per-link step: when nothing
is pending, a node that has its block holds every chunk a mesh neighbour received, or has stopped
pulling the group (the transport delivers the chunk or leaves the neighbour's offer, and the asking
resolves the offer). Where the source announces at a chunk's acknowledgement, they give it on the
source's links only as said below. A node that has not stopped holds only chunks it received: it
rebuilds only after its decode claim (`NoStallTransport`'s `stored`). The step from there to Q1 is
counting, here in plain Lean, without Veil:

- a node stops pulling at its K-th received chunk, and the source, stopped, has at least K in `rcv`
  (published, or received);
- with nothing pending, a node that has received K chunks has made its decode claim (§4.2 makes it at
  the K-th, so it is not left pending);
- so, by induction along mesh paths from the source, every node connected to it has stopped: its
  stopped neighbour received at least K chunks, each of which it holds, received, or it has stopped;
- and its decode, no longer pending, has returned: with an honest builder's code, the node is
  complete.

The hypotheses are the per-link step, the two counting facts, and the decode's outcome; the theorem
is about any node type, any mesh and any N and K. The theorems hold wherever their hypotheses do.

Where the source announces at the chunk's acknowledgement (§5.1, `SOURCE_OFFERS = ACK`), the
transport gives the step on the source's links only for a chunk that is acknowledged, or whose
neighbour received it, has stopped, or holds an offer of it, which the asking then resolves. So each
step the counting uses on a source's link must be had that way. The link from the pieces to these
hypotheses is by inspection.

The mesh is the one of the quiet state: the transport's mesh changes (peers join and leave it,
connections close), and its per-link step holds for every link the quiet state has (on the source's
links at `ACK`, as above), so the induction runs along those. Under equivocation
(`NoStallEquiv.lean`) the step holds for the links into nodes that installed the builder's block,
with the same condition at `ACK`, and the same theorem runs along the mesh restricted to them
(`every_installed_reachable_node_completes`).

Three corollaries of the per-link step as proved:
- **The builder releases only K of the N chunks** (`completes_from_K_chunks`): the source needs to
  publish any K distinct chunks (each as §5.1 does, to the mesh it has at the publish: holding them
  is not enough), not all N. For a chunk the source withholds, the transport piece is its model with
  no source (`one_source` allows none, and no invariant names the source), or, where the source
  announces it on a later join (§5.4: at the source, every chunk of a group it publishes), its model
  with the source publishing to the mesh it has, possibly none; so the per-link step holds for it
  too, at `ACK` on the source's links under the same condition. Its copies then come from nodes that
  hold it without having received it: a decoded node's
  repair, pushed or owed, or an announcement on a join (§5.4).
- **The source drops out** (`stops_from_holders`, `completes_from_holders`,
  `completes_from_holders_installed`): a node stops once K distinct chunks have each been received
  by some node that reaches it along the quiet state's mesh, or that has stopped, whether or not the
  source is still in that mesh, and though no one node may have received K. The mesh is the one the
  per-link step holds for: restricted to links into nodes that installed the block (the last form),
  unless every node on the paths installs it. The
  transport lets the source close its connections and leave every mesh at any time (`close`,
  `leave`), losing what was queued from it; the copies deferred at receivers stay, and are taken in
  once their block installs (`resume`), so a quiet state holds them.
- **Some nodes never install the block**: without equivocation,
  `every_installed_reachable_node_completes` with `inst` the nodes that installed it. The one-block
  pieces' per-link steps (`delivered`, `offers_resolve`) already hold for any receiver that
  installed the block, and assume nothing of the others: a node that never installs it is never
  complete, and the counting runs around it.

And with malicious peers (`every_honest_reachable_node_stops`, `every_honest_reachable_node_completes`):
the pieces with adversaries (`NoStallTransportAdv.lean`, `NoStallAskAdv.lean`) give the per-link
step for links from honest nodes into honest nodes that have the block, whatever the others do (on
the source's links at `ACK`, as above); the counting facts are honest nodes' own; so the induction
runs along such links, and every honest node the source reaches through honest nodes that installed
the block is complete. -/

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
    -- a node stops at its K-th received chunk (so a stopped source, too, has at least K in `rcv`:
    -- published, or received)
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
returned with an honest builder's code, given the per-link step on every link (`link`) -/
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

/-- Q1 under equivocation (`NoStallEquiv.lean`): the per-link step (`link`, a hypothesis) holds for
the links into nodes that installed the builder's block (`inst`), the block the chunks name (on the
source's links at `ACK`, under the header's condition), and a node on the proposer's
other block forwards nothing of the group until it switches. So the counting runs along the mesh
restricted to such nodes: every node the source reaches through them is complete. -/
theorem every_installed_reachable_node_completes {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (inst : Node → Prop) (src : Node)
    (rcv : Node → Fin N → Bool) (stop complete : Node → Prop)
    (source_stopped : stop src)
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    -- the per-link step, for the links into nodes with the builder's block
    (link : ∀ m n i, mesh m n → inst n → rcv m i = true → rcv n i = true ∨ stop n)
    (decoded : ∀ n, stop n → complete n) :
    ∀ n, Reach (fun m n => mesh m n ∧ inst n) src n → complete n :=
  every_connected_node_completes K (fun m n => mesh m n ∧ inst n) src rcv stop complete
    source_stopped stopped_has_K K_has_stopped (fun m n i h hi => link m n i h.1 h.2 hi) decoded

/-- Q1 with malicious peers (`NoStallTransportAdv.lean`, `NoStallAskAdv.lean`): the per-link step
holds for the links from honest nodes into honest nodes that installed the block, whatever the other
peers do (on the source's links at `ACK`, as the header says), and the counting facts hold of honest
nodes; so every honest node the source reaches along such links has stopped -/
theorem every_honest_reachable_node_stops {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (honest inst : Node → Prop) (src : Node)
    (rcv : Node → Fin N → Bool) (stop : Node → Prop)
    (source_honest : honest src) (source_stopped : stop src)
    (stopped_has_K : ∀ n, honest n → stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, honest n → K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → honest m → honest n → inst n → rcv m i = true →
      rcv n i = true ∨ stop n) :
    ∀ n, Reach (fun m n => mesh m n ∧ honest m ∧ honest n ∧ inst n) src n → stop n ∧ honest n := by
  intro n h
  induction h with
  | here => exact ⟨source_stopped, source_honest⟩
  | @step m n' _ hmn ih =>
    obtain ⟨hstop, hm⟩ := ih
    refine ⟨?_, hmn.2.2.1⟩
    by_cases hs : stop n'
    · exact hs
    · apply K_has_stopped n' hmn.2.2.1
      have hK := stopped_has_K m hm hstop
      have hle : count (rcv m) ≤ count (rcv n') := count_mono fun i hi => by
        rcases link m n' i hmn.1 hmn.2.1 hmn.2.2.1 hmn.2.2.2 hi with h | h
        · exact h
        · exact absurd h hs
      omega

/-- Q1 with malicious peers: every honest node the source reaches along links between honest nodes,
into nodes that installed the block, is complete, once its decode, no longer pending, has returned,
given the per-link step on those links (`link`) -/
theorem every_honest_reachable_node_completes {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (honest inst : Node → Prop) (src : Node)
    (rcv : Node → Fin N → Bool) (stop complete : Node → Prop)
    (source_honest : honest src) (source_stopped : stop src)
    (stopped_has_K : ∀ n, honest n → stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, honest n → K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → honest m → honest n → inst n → rcv m i = true →
      rcv n i = true ∨ stop n)
    (decoded : ∀ n, honest n → stop n → complete n) :
    ∀ n, Reach (fun m n => mesh m n ∧ honest m ∧ honest n ∧ inst n) src n → complete n :=
  fun n h =>
    let hs := every_honest_reachable_node_stops K mesh honest inst src rcv stop source_honest
      source_stopped stopped_has_K K_has_stopped link n h
    decoded n hs.2 hs.1

/-- the builder releases only K of the N chunks: a source that has published any K distinct ones
(`rcv` as for any node) suffices; a chunk it withholds reaches nodes from those that hold it without
having received it (repair, an announcement on a join), and its per-link step (`link`, a
hypothesis) is the transport piece's with no source, or with the source publishing to the mesh it
has. Where the source announces at a chunk's acknowledgement, the transport gives that step on the
source's links only for a chunk that is acknowledged, or whose receiver received it, has stopped,
or holds the source's offer of it, which the asking resolves -/
theorem completes_from_K_chunks {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (src : Node)
    (rcv : Node → Fin N → Bool) (stop complete : Node → Prop)
    (source_has_K : K ≤ count (rcv src))
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → rcv m i = true → rcv n i = true ∨ stop n)
    (decoded : ∀ n, stop n → complete n) :
    ∀ n, Reach mesh src n → complete n :=
  every_connected_node_completes K mesh src rcv stop complete (K_has_stopped src source_has_K)
    stopped_has_K K_has_stopped link decoded

/-- along the mesh from a node that received chunk `i`, every node has received it or has stopped -/
theorem received_or_stopped {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (rcv : Node → Fin N → Bool) (stop : Node → Prop)
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → rcv m i = true → rcv n i = true ∨ stop n)
    (h : Node) (i : Fin N) (hi : rcv h i = true) :
    ∀ n, Reach mesh h n → rcv n i = true ∨ stop n := by
  intro n hr
  induction hr with
  | here => exact Or.inl hi
  | @step m n' _ hmn ih =>
    rcases ih with hm | hm
    · exact link m n' i hmn hm
    · exact Or.inr (every_connected_node_stops K mesh m rcv stop hm stopped_has_K K_has_stopped
        link n' (Reach.step Reach.here hmn))

/-- the source drops out: a node stops once K distinct chunks (`S`) have each been received by some
node that reaches it along the quiet state's mesh, or held by one that has stopped; the source need
not be among them, nor any one of them have received K -/
theorem stops_from_holders {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (rcv : Node → Fin N → Bool) (stop : Node → Prop)
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → rcv m i = true → rcv n i = true ∨ stop n)
    (n : Node) (S : Fin N → Bool) (hS : K ≤ count S)
    (holder : ∀ i, S i = true → ∃ h, (rcv h i = true ∨ stop h) ∧ Reach mesh h n) :
    stop n := by
  by_cases hs : stop n
  · exact hs
  · apply K_has_stopped
    have hle : count S ≤ count (rcv n) := count_mono fun i hi => by
      obtain ⟨h, hh, hr⟩ := holder i hi
      rcases hh with hh | hh
      · rcases received_or_stopped K mesh rcv stop stopped_has_K K_has_stopped link h i hh n hr with
          h' | h'
        · exact h'
        · exact absurd h' hs
      · exact absurd (every_connected_node_stops K mesh h rcv stop hh stopped_has_K K_has_stopped
          link n hr) hs
    omega

/-- the source drops out, and the node's decode, no longer pending, has returned -/
theorem completes_from_holders {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (rcv : Node → Fin N → Bool) (stop complete : Node → Prop)
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → rcv m i = true → rcv n i = true ∨ stop n)
    (decoded : ∀ n, stop n → complete n)
    (n : Node) (S : Fin N → Bool) (hS : K ≤ count S)
    (holder : ∀ i, S i = true → ∃ h, (rcv h i = true ∨ stop h) ∧ Reach mesh h n) :
    complete n :=
  decoded n (stops_from_holders K mesh rcv stop stopped_has_K K_has_stopped link n S hS holder)

/-- the source drops out, the counting through the nodes that installed the block (`inst`): the
per-link step is needed only for links into them -/
theorem completes_from_holders_installed {Node : Type} {N : Nat} (K : Nat)
    (mesh : Node → Node → Prop) (inst : Node → Prop) (rcv : Node → Fin N → Bool)
    (stop complete : Node → Prop)
    (stopped_has_K : ∀ n, stop n → K ≤ count (rcv n))
    (K_has_stopped : ∀ n, K ≤ count (rcv n) → stop n)
    (link : ∀ m n i, mesh m n → inst n → rcv m i = true → rcv n i = true ∨ stop n)
    (decoded : ∀ n, stop n → complete n)
    (n : Node) (S : Fin N → Bool) (hS : K ≤ count S)
    (holder : ∀ i, S i = true →
      ∃ h, (rcv h i = true ∨ stop h) ∧ Reach (fun m n => mesh m n ∧ inst n) h n) :
    complete n :=
  completes_from_holders K (fun m n => mesh m n ∧ inst n) rcv stop complete stopped_has_K
    K_has_stopped (fun m n i h hi => link m n i h.1 h.2 hi) decoded n S hS holder

/-- `holder` is needed: two nodes and no mesh link, one chunk (K = 1) received by the first; every
other hypothesis of `stops_from_holders` holds, `holder` does not, and the second has not stopped -/
theorem holder_needed : ∃ (rcv : Bool → Fin 1 → Bool) (stop : Bool → Prop),
    (∀ n, stop n → 1 ≤ count (rcv n)) ∧ (∀ n, 1 ≤ count (rcv n) → stop n) ∧
    (∀ (m n : Bool) (i : Fin 1), False → rcv m i = true → rcv n i = true ∨ stop n) ∧
    1 ≤ count (rcv true) ∧
    ¬ (∀ i, rcv true i = true → ∃ h, (rcv h i = true ∨ stop h) ∧ Reach (fun _ _ => False) h false) ∧
    ¬ stop false := by
  refine ⟨fun b _ => b, fun b => b = true, ?_, ?_, fun _ _ _ h => h.elim, by decide, ?_, by decide⟩
  · intro n hn; subst hn; decide
  · intro n hn; cases n
    · exact absurd hn (by decide)
    · rfl
  · intro h
    obtain ⟨b, hb, hr⟩ := h 0 rfl
    cases hr with
    | here => rcases hb with hb | hb <;> exact absurd hb (by decide)
    | step _ hm => exact hm.elim

/-- K distinct chunks are needed: one link, both nodes holding the same one of the two chunks
needed (K = 2); every other hypothesis of `stops_from_holders` holds, and the receiver has not
stopped -/
theorem enough_needed : ∃ (rcv : Bool → Fin 2 → Bool) (stop : Bool → Prop) (S : Fin 2 → Bool),
    (∀ n, stop n → 2 ≤ count (rcv n)) ∧ (∀ n, 2 ≤ count (rcv n) → stop n) ∧
    (∀ (m n : Bool) (i : Fin 2), (m = true ∧ n = false) → rcv m i = true → rcv n i = true ∨ stop n) ∧
    (∀ i, S i = true → ∃ h, (rcv h i = true ∨ stop h) ∧
      Reach (fun m n => m = true ∧ n = false) h false) ∧
    ¬ (2 ≤ count S) ∧ ¬ stop false := by
  refine ⟨fun _ i => i == 0, fun _ => False, fun i => i == 0, fun _ h => h.elim, ?_, ?_, ?_,
    by decide, fun h => h⟩
  · intro n hn; exact absurd hn (by decide : ¬ 2 ≤ count (fun i : Fin 2 => i == 0))
  · intro m n i _ hi; exact Or.inl hi
  · intro i hi
    exact ⟨true, Or.inl hi, Reach.step Reach.here ⟨rfl, rfl⟩⟩

end NoStallCount

-- the audit, a failure a build error: the twelve theorems rest on Lean's own axioms only
open Lean Elab Command in
#eval show CommandElabM Unit from do
  let allowed := [``propext, ``Classical.choice, ``Quot.sound]
  let mut rest : Std.HashSet Name := {}
  for n in [``NoStallCount.every_connected_node_stops,
      ``NoStallCount.every_connected_node_completes,
      ``NoStallCount.every_installed_reachable_node_completes,
      ``NoStallCount.completes_from_K_chunks,
      ``NoStallCount.received_or_stopped,
      ``NoStallCount.stops_from_holders,
      ``NoStallCount.completes_from_holders,
      ``NoStallCount.completes_from_holders_installed,
      ``NoStallCount.holder_needed,
      ``NoStallCount.enough_needed,
      ``NoStallCount.every_honest_reachable_node_stops,
      ``NoStallCount.every_honest_reachable_node_completes] do
    for a in ← liftCoreM (collectAxioms n) do
      rest := rest.insert a
      unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"the twelve theorems rest on {rest.toList}"
