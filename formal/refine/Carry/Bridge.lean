import Veil

/-! # The bridge from a generated theorem to a generated transition

`#gen_theorems` states an action's theorem for a clause in weakest-precondition form
(`VeilM.meetsSpecificationIfSuccessfulAssuming`: Veil's `VCGen/Induction.lean`), and a refinement step is proved
against the action's generated transition (`<action>.ext.tr`). Veil proves the two ends meet: an action's
`ext.derived_eq` says its derived transition is its `ext.tr`, and `Transition.meetsSpecificationIfSuccessful_eq`
says the transition form of a specification is the weakest-precondition form. This file puts them together once,
over Veil's library alone: no model is imported, and no tactic of Veil's is used. -/

namespace Refine.Carry
open Veil

/-- **The bridge.** For any action and any transition equal to its derived one: what the action's
weakest-precondition theorem says of a postcondition holds after a step of the transition, from a state where
the assumptions and the precondition hold. -/
theorem bridge {m : Mode} {ρ σ α : Type} [Inhabited α] (act : VeilM m ρ σ α) (tr : Transition ρ σ)
    (hder : act.toTransitionDerived = tr) (assu : ρ → Prop) (pre post : SProp ρ σ)
    (h : act.meetsSpecificationIfSuccessfulAssuming assu pre post)
    {r : ρ} {s s' : σ} (ha : assu r) (hp : pre r s) (ht : tr r s s') : post r s' := by
  subst hder
  rw [← VeilM.toTransitionDerived_sound] at ht
  have h' : act.toTransition.meetsSpecificationIfSuccessful (fun th st => assu th ∧ pre th st) post := by
    rw [Transition.meetsSpecificationIfSuccessful_eq]
    exact h
  exact h' r s s' ⟨ha, hp⟩ ht

/-- **A `#gen_theorems` statement, kept closed.** Its one field is the statement as Veil states it
(`VeilM.meetsSpecificationIfSuccessfulAssuming`): from the assumptions and the precondition, the action, if it
succeeds, leaves the postcondition.

Why a structure and not the statement itself. **Observed:** with the statement bare, a term of that type for the
model's initializer did not elaborate within the default limit, and Lean's diagnostics showed the action's binds
being unfolded; with this structure around it, it does. For `retryAsk`, `retryNoop`, `promiseDue` and
`parkOther` both forms elaborate. **Inferred, not established:** Veil's form is a reducible definition, and Lean
normalises the type of a term it elaborates, which unfolds that form into the action's weakest precondition; how
far that goes depends on the action. A `require` is not what stops it (`parkOther` has none, and was no
trouble): the initializer's 22 assignments are the likelier cause. A structure does not unfold. -/
structure Meets {m : Mode} {ρ σ α : Type} (act : VeilM m ρ σ α) (assu : ρ → Prop) (pre post : SProp ρ σ) :
    Prop where
  /-- the statement, as `#gen_theorems` states it -/
  out : act.meetsSpecificationIfSuccessfulAssuming assu pre post

/-- The bridge, from a statement kept closed. -/
theorem Meets.bridge {m : Mode} {ρ σ α : Type} [Inhabited α] {act : VeilM m ρ σ α} {tr : Transition ρ σ}
    {assu : ρ → Prop} {pre post : SProp ρ σ} (h : Meets act assu pre post)
    (hder : act.toTransitionDerived = tr)
    {r : ρ} {s s' : σ} (ha : assu r) (hp : pre r s) (ht : tr r s s') : post r s' :=
  Refine.Carry.bridge act tr hder assu pre post h.out ha hp ht

end Refine.Carry
