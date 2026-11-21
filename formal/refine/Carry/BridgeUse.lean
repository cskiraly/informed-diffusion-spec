import Carry.Bridge
import Carry.BridgeToy

/-! # The bridge, exercised end to end on the toy

`Carry/BridgeToy.lean` is a Veil module with one action and one invariant, checked and with its theorems
generated (`#gen_theorems`). Here the generated theorems `raise_flag_seen` and `initializer_flag_seen` are taken
through the bridge to the generated transitions, at the representation Veil generates beside them
(`FieldAbstractType`: every relation a function to `Bool`), as `Refine` takes the asking model's. -/

namespace Refine.Carry
open scoped BridgeToy

/-- The toy's state with every relation a function to `Bool`. -/
abbrev ToyState (node : Type) := BridgeToy.State (BridgeToy.FieldAbstractType node)

/-- The toy's constants (none). -/
abbrev ToyTheory (node : Type) := BridgeToy.Theory node

section
variable {node : Type} [DecidableEq node] [Inhabited node]

/-- The generated `raise_flag_seen`, through the bridge: from a state where the toy's `Invariants` hold, a step
of the generated transition `raise.ext.tr` leaves the clause `flag_seen`. -/
theorem toy_raise_flag_seen (n : node) {r : ToyTheory node} {s s' : ToyState node}
    (hinv : BridgeToy.Invariants (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) r s)
    (htr : BridgeToy.raise.ext.tr (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) n r s s') :
    BridgeToy.flag_seen r s' :=
  bridge _ _ (BridgeToy.raise.ext.derived_eq (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) n)
    _ _ _ (BridgeToy.raise_flag_seen (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) n)
    trivial hinv htr

/-- The generated `initializer_flag_seen`, through the bridge: the toy's `Init` gives the clause. -/
theorem toy_init_flag_seen {r : ToyTheory node} {s : ToyState node}
    (hinit : BridgeToy.Init (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) r s) :
    BridgeToy.flag_seen r s :=
  bridge _ _ (BridgeToy.initializer.ext.derived_eq (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node))
    _ (fun _ _ => True) _
    (BridgeToy.initializer_flag_seen (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node))
    trivial trivial hinit

/-- The generated theorems, kept closed in `Meets`, as `Carry/Fv.lean` takes the Veil model's: each by `⟨·⟩` from
the theorem `#gen_theorems` made. -/
theorem toy_raise_meets (n : node) :
    Meets (BridgeToy.raise.ext (ρ := ToyTheory node) (σ := ToyState node) (χ := BridgeToy.FieldAbstractType node) n)
      (BridgeToy.Assumptions (ToyTheory node) node)
      (BridgeToy.Invariants (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node))
      (fun rd st => BridgeToy.flag_seen rd st) :=
  ⟨BridgeToy.raise_flag_seen (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) n⟩

theorem toy_init_meets :
    Meets (BridgeToy.initializer.ext (ρ := ToyTheory node) (σ := ToyState node)
        (χ := BridgeToy.FieldAbstractType node))
      (BridgeToy.Assumptions (ToyTheory node) node) (fun _ _ => True)
      (fun rd st => BridgeToy.flag_seen rd st) :=
  ⟨BridgeToy.initializer_flag_seen (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node)⟩

/-- **End to end, in plain terms.** After a `raise` step from a state where every flagged node is seen, every
flagged node is seen: the clause read off the abstract state, with nothing of Veil's left in the statement but
the generated transition. -/
theorem toy_raise_plain (n : node) {r : ToyTheory node} {s s' : ToyState node}
    (hinv : ∀ x, s.flag x = true → s.seen x = true)
    (htr : BridgeToy.raise.ext.tr (ToyTheory node) (ToyState node) node (BridgeToy.FieldAbstractType node) n r s s') :
    ∀ x, s'.flag x = true → s'.seen x = true := by
  have h := toy_raise_flag_seen n (r := r) (s := s) (s' := s') (by
    show BridgeToy.flag_seen r s
    exact hinv) htr
  exact h

end

end Refine.Carry
