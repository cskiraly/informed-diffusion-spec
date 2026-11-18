module

public import Lentil
public import LentilApplications.RelationalRanking.Util

@[expose] public section

/-! # Going quiet by a ranking (Q3's general step)

The general step of the `Q3` proofs (`../../plans/fv-q3.md`). An execution whose every step is an
own step, an environment step or a stutter, in which every own step lowers a well-founded ranking,
a stutter changes nothing, the environment eventually takes no step, and each family of own
actions is weakly fair, eventually has no own action enabled, for good: after the environment's
last step the own steps are finitely many, by the ranking; after the last of them every step is a
stutter, so the state stays; an own action enabled there would stay enabled, and weak fairness
would make it take a step, which would lower the ranking of a state that does not change. -/

namespace FvQuiet

open Lentil

/-- A well-founded relation relates nothing to itself. -/
theorem not_rel_self {α : Sort u} {r : α → α → Prop} (hwf : WellFounded r) (a : α) : ¬ r a a :=
  hwf.induction (C := fun x => ¬ r x x) a fun x ih hxx => ih x hxx hxx

/-- A property of some number holds of a least one. -/
theorem first_of {p : Nat → Prop} : ∀ k, p k → ∃ j, p j ∧ ∀ i, i < j → ¬ p i := by
  intro k
  induction k using Nat.strongRecOn with
  | _ k ih =>
    intro hk
    by_cases h : ∃ i, i < k ∧ p i
    · obtain ⟨i, hik, hi⟩ := h
      exact ih i hik hi
    · exact ⟨k, hk, fun i hik hi => h ⟨i, hik, hi⟩⟩

/-- From any position `n ≥ T`, where every step is an own step (lowering `r`) or a stutter, the
execution reaches a position from which its state never changes. -/
theorem stabilises {σ : Type u} {own stut : action σ} {r : σ → σ → Prop} (hwf : WellFounded r)
    (hdec : ∀ s s', own s s' → r s' s) (hstut : ∀ s s', stut s s' → s' = s)
    (e : exec σ) (T : Nat) (hstep : ∀ n, T ≤ n → own (e n) (e (n + 1)) ∨ stut (e n) (e (n + 1))) :
    ∀ n, T ≤ n → ∃ T', n ≤ T' ∧ ∀ k, e (T' + k) = e T' := by
  suffices h : ∀ s n, T ≤ n → e n = s → ∃ T', n ≤ T' ∧ ∀ k, e (T' + k) = e T' from
    fun n hn => h _ n hn rfl
  intro s
  induction s using hwf.induction with
  | _ s ih =>
    intro n hn hs
    by_cases hown : ∃ k, own (e (n + k)) (e (n + k + 1))
    · obtain ⟨k0, hk0⟩ := hown
      obtain ⟨k, hk, hmin⟩ := first_of (p := fun k => own (e (n + k)) (e (n + k + 1))) k0 hk0
      -- the steps before the first own step are stutters, so the state at `n + k` is `s`
      have hsame : ∀ j, j ≤ k → e (n + j) = s := by
        intro j hj
        induction j with
        | zero => simpa using hs
        | succ j ihj =>
          rcases hstep (n + j) (by omega) with h | h
          · exact absurd h (hmin j (by omega))
          · rw [show n + (j + 1) = n + j + 1 by omega, hstut _ _ h]
            exact ihj (by omega)
      have hr : r (e (n + k + 1)) s := by
        have h := hdec _ _ hk
        rwa [hsame k (Nat.le_refl k)] at h
      obtain ⟨T', hT', hconst⟩ := ih _ hr (n + k + 1) (by omega) rfl
      exact ⟨T', by omega, hconst⟩
    · -- no own step from `n` on: every step is a stutter
      refine ⟨n, Nat.le_refl n, fun k => ?_⟩
      induction k with
      | zero => rfl
      | succ k ihk =>
        rcases hstep (n + k) (by omega) with h | h
        · exact absurd ⟨k, h⟩ hown
        · rw [show n + (k + 1) = n + k + 1 by omega, hstut _ _ h, ihk]

/-- **Going quiet, along one execution.** As `quiet_of_ranking` below, with each hypothesis about
the execution's steps from position `i` on. -/
theorem quiet_exec {σ : Type u} {ι : Sort v} (e : exec σ) (i : Nat)
    (own env stut : action σ) (fam : ι → action σ) (work : σ → Prop)
    (r : σ → σ → Prop) (hwf : WellFounded r)
    (hsplit : ∀ n, i ≤ n → own (e n) (e (n + 1)) ∨ env (e n) (e (n + 1)) ∨ stut (e n) (e (n + 1)))
    (hdec : ∀ n, i ≤ n → own (e n) (e (n + 1)) → r (e (n + 1)) (e n))
    (hstut : ∀ s s', stut s s' → s' = s)
    (hfam : ∀ j s s', fam j s s' → own s s')
    (hwork : ∀ n, i ≤ n → work (e n) → ∃ j, enabled (fam j) (e n))
    (hfair : ∀ j, weak_fairness (fam j) e i)
    (henv : eventually (always (tl_not (action_pred env))) e i) :
    eventually (always (state_pred (fun s => ¬ work s))) e i := by
  have hfair' : ∀ j k, (∀ m, enabled (fam j) (e (i + k + m))) →
      ∃ m, fam j (e (i + k + m)) (e (i + k + m + 1)) := hfair
  have henv' : ∃ k0, ∀ k, ¬ env (e (i + k0 + k)) (e (i + k0 + k + 1)) := henv
  obtain ⟨k0, hquiet⟩ := henv'
  -- from `i + k0` on, every step is an own step or a stutter
  have hstep : ∀ n, i + k0 ≤ n → own (e n) (e (n + 1)) ∨ stut (e n) (e (n + 1)) := by
    intro n hn
    have hne := hquiet (n - (i + k0))
    rw [show i + k0 + (n - (i + k0)) = n by omega] at hne
    rcases hsplit n (by omega) with h | h | h
    · exact Or.inl h
    · exact absurd h hne
    · exact Or.inr h
  have hdec' : ∀ n, i + k0 ≤ n → own (e n) (e (n + 1)) → r (e (n + 1)) (e n) :=
    fun n hn h => hdec n (by omega) h
  obtain ⟨T', hT', hconst⟩ := stabilises (own := fun s s' => own s s' ∧ r s' s) hwf
    (fun s s' h => h.2) hstut e (i + k0)
    (fun n hn => (hstep n hn).imp (fun h => ⟨h, hdec' n hn h⟩) id) (i + k0) (Nat.le_refl _)
  show ∃ k, ∀ m, ¬ work (e (i + k + m))
  refine ⟨T' - i, fun m => ?_⟩
  rw [show i + (T' - i) + m = T' + m by omega, hconst m]
  intro hw
  obtain ⟨j, hen⟩ := hwork T' (by omega) hw
  -- `fam j` stays enabled from `T'`, so weak fairness makes it take a step there
  have hfj := hfair' j (T' - i)
  rw [show i + (T' - i) = T' by omega] at hfj
  obtain ⟨m', hm'⟩ := hfj (fun m => by rw [hconst m]; exact hen)
  have hr := hdec (T' + m') (by omega) (hfam j _ _ hm')
  rw [show T' + m' + 1 = T' + (m' + 1) by omega, hconst (m' + 1), hconst m'] at hr
  exact not_rel_self hwf _ hr

/-- The elements of `xs` that satisfy `p`, counted. -/
noncomputable def count {α : Type u} (xs : List α) (p : α → Prop) : Nat :=
  xs.countP (fun x => @decide (p x) (Classical.propDecidable _))

/-- `count` agrees with the predicate's truth value. -/
theorem decide_classical {P : Prop} : @decide P (Classical.propDecidable _) = true ↔ P :=
  ⟨@of_decide_eq_true P (Classical.propDecidable _), @decide_eq_true P (Classical.propDecidable _)⟩

theorem count_le {α : Type u} (xs : List α) {p q : α → Prop} (h : ∀ x, q x → p x) :
    count xs q ≤ count xs p := by
  induction xs with
  | nil => simp [count]
  | cons a xs ih =>
    unfold count at ih ⊢
    rw [List.countP_cons, List.countP_cons]
    have hpq : @decide (q a) (Classical.propDecidable _) = true →
        @decide (p a) (Classical.propDecidable _) = true := by
      intro hq; rw [decide_classical] at hq ⊢; exact h a hq
    cases hqa : @decide (q a) (Classical.propDecidable _) <;>
      cases hpa : @decide (p a) (Classical.propDecidable _) <;> simp_all; omega

/-- A predicate that loses an element of `xs` and gains none counts less. -/
theorem count_lt {α : Type u} (xs : List α) {p q : α → Prop} (h : ∀ x, q x → p x) {x : α}
    (hx : x ∈ xs) (hp : p x) (hq : ¬ q x) : count xs q < count xs p := by
  induction xs with
  | nil => simp at hx
  | cons a xs ih =>
    have hle := count_le xs h
    unfold count at ih hle ⊢
    rw [List.countP_cons, List.countP_cons]
    rcases List.mem_cons.mp hx with hxa | hx'
    · rw [hxa] at hp hq
      have hpa : @decide (p a) (Classical.propDecidable _) = true := decide_classical.mpr hp
      have hqa : @decide (q a) (Classical.propDecidable _) = false := by
        cases hqq : @decide (q a) (Classical.propDecidable _)
        · rfl
        · exact absurd (decide_classical.mp hqq) hq
      simp [hpa, hqa]; omega
    · have hlt := ih hx'
      have hpq : @decide (q a) (Classical.propDecidable _) = true →
          @decide (p a) (Classical.propDecidable _) = true := by
        intro hq'; rw [decide_classical] at hq' ⊢; exact h a hq'
      cases hqa : @decide (q a) (Classical.propDecidable _) <;>
        cases hpa : @decide (p a) (Classical.propDecidable _) <;> simp_all; omega

theorem count_congr {α : Type u} (xs : List α) {p q : α → Prop} (h : ∀ x, p x ↔ q x) :
    count xs p = count xs q := by
  have : p = q := funext fun x => propext (h x)
  rw [this]

/-! ## A lexicographic ranking by levels

A model's ranking: levels `a`, `a + 1`, …, `a + n - 1`, each a relation `δ l` on elements, counted
over a list `xs` that holds every element, and compared highest (lowest-numbered) first. -/

/-- The counts of the levels `a`, …, `a + n - 1` at `s`. -/
noncomputable def counts {σ : Type u} {α : Type v} (xs : List α) (δ : Nat → α → σ → Prop)
    (a n : Nat) (s : σ) : List Nat :=
  (List.range' a n).map (fun l => count xs (fun x => δ l x s))

theorem counts_length {σ : Type u} {α : Type v} (xs : List α) (δ : Nat → α → σ → Prop)
    (a n : Nat) (s : σ) : (counts xs δ a n s).length = n := by
  simp [counts]

/-- The lexicographic order on the counts is well-founded. -/
theorem counts_wf {σ : Type u} {α : Type v} (xs : List α) (δ : Nat → α → σ → Prop) (a n : Nat) :
    WellFounded (fun s' s : σ =>
      LentilLib.ListLex.List.lexLt Nat.lt_wfRel (counts xs δ a n s') (counts xs δ a n s)) := by
  let W := LentilLib.ListLex.List.lexLt_wfRel Nat.lt_wfRel n
  let f : σ → { l : List Nat // l.length = n } :=
    fun s => ⟨counts xs δ a n s, counts_length xs δ a n s⟩
  refine Subrelation.wf (r := InvImage W.rel f) ?_ (InvImage.wf f W.wf)
  intro s' s h
  exact (LentilLib.ListLex.List.lexLt_wfRel_rel Nat.lt_wfRel n (f s') (f s)).mpr h

/-- A step that gains nothing at any level down to level `l` and loses an element at `l` lowers the
counts: the highest level that loses an element is the first that differs. -/
theorem counts_dec {σ : Type u} {α : Type v} (xs : List α) (hxs : ∀ x, x ∈ xs)
    (δ : Nat → α → σ → Prop) :
    ∀ (n a l : Nat) (s s' : σ), a ≤ l → l < a + n →
      (∀ j, a ≤ j → j ≤ l → ∀ x, δ j x s' → δ j x s) →
      (∃ w, δ l w s ∧ ¬ δ l w s') →
      LentilLib.ListLex.List.lexLt Nat.lt_wfRel (counts xs δ a n s') (counts xs δ a n s)
  | 0, _, _, _, _, _, hl, _, _ => absurd hl (by omega)
  | n + 1, a, l, s, s', hal, hl, hsub, hw => by
    simp only [counts, List.range'_succ, List.map_cons]
    show _ ∨ _
    by_cases hstrict : ∃ w, δ a w s ∧ ¬ δ a w s'
    · left
      obtain ⟨w, hw, hw'⟩ := hstrict
      exact count_lt xs (hsub a (Nat.le_refl a) (by omega)) (hxs w) hw hw'
    · right
      have heq : ∀ x, δ a x s' ↔ δ a x s := fun x =>
        ⟨hsub a (Nat.le_refl a) (by omega) x,
          fun h => Classical.byContradiction fun hn => hstrict ⟨x, h, hn⟩⟩
      refine ⟨count_congr xs heq, ?_⟩
      have hla : l ≠ a := by rintro rfl; exact hstrict hw
      exact counts_dec xs hxs δ n (a + 1) l s s' (by omega) (by omega)
        (fun j hj1 hj2 => hsub j (by omega) hj2) hw

/-- **Going quiet.** In an execution whose every step (`next`) is an own step, an environment step
or a stutter, if every own step lowers the well-founded `r`, a stutter changes nothing, every
action of the families `fam` is an own step, and `work` holds only where one of them is enabled,
then weak fairness of each family and an environment that eventually takes no step make `work`
false from some point on, for good. -/
theorem quiet_of_ranking {σ : Type u} {ι : Sort v}
    (next own env stut : action σ) (fam : ι → action σ) (work : σ → Prop)
    (r : σ → σ → Prop) (hwf : WellFounded r)
    (hsplit : ∀ s s', next s s' → own s s' ∨ env s s' ∨ stut s s')
    (hdec : ∀ s s', own s s' → r s' s)
    (hstut : ∀ s s', stut s s' → s' = s)
    (hfam : ∀ i s s', fam i s s' → own s s')
    (hwork : ∀ s, work s → ∃ i, enabled (fam i) s) :
    pred_implies [tlfml| □ ⟨next⟩ ∧ (∀ i, 𝒲ℱ (fam i)) ∧ ◇ □ ¬ ⟨env⟩]
      [tlfml| ◇ □ ⌜ fun s => ¬ work s ⌝] := by
  intro e i h
  obtain ⟨hnext, hfair, henv⟩ := h
  have hnext' : ∀ k, next (e (i + k)) (e (i + k + 1)) := hnext
  have hfair' : ∀ j k, (∀ m, enabled (fam j) (e (i + k + m))) →
      ∃ m, fam j (e (i + k + m)) (e (i + k + m + 1)) := hfair
  have henv' : ∃ k0, ∀ k, ¬ env (e (i + k0 + k)) (e (i + k0 + k + 1)) := henv
  obtain ⟨k0, hquiet⟩ := henv'
  -- from `i + k0` on, every step is an own step or a stutter
  have hstep : ∀ n, i + k0 ≤ n → own (e n) (e (n + 1)) ∨ stut (e n) (e (n + 1)) := by
    intro n hn
    have hnx := hnext' (n - i)
    have hne := hquiet (n - (i + k0))
    rw [show i + (n - i) = n by omega] at hnx
    rw [show i + k0 + (n - (i + k0)) = n by omega] at hne
    rcases hsplit _ _ hnx with h | h | h
    · exact Or.inl h
    · exact absurd h hne
    · exact Or.inr h
  obtain ⟨T', hT', hconst⟩ := stabilises hwf hdec hstut e (i + k0) hstep (i + k0) (Nat.le_refl _)
  show ∃ k, ∀ m, ¬ work (e (i + k + m))
  refine ⟨T' - i, fun m => ?_⟩
  rw [show i + (T' - i) + m = T' + m by omega, hconst m]
  intro hw
  obtain ⟨j, hen⟩ := hwork _ hw
  -- `fam j` stays enabled from `T'`, so weak fairness makes it take a step there
  have hfj := hfair' j (T' - i)
  rw [show i + (T' - i) = T' by omega] at hfj
  obtain ⟨m', hm'⟩ := hfj (fun m => by rw [hconst m]; exact hen)
  have hr := hdec _ _ (hfam j _ _ hm')
  rw [show T' + m' + 1 = T' + (m' + 1) by omega, hconst (m' + 1), hconst m'] at hr
  exact not_rel_self hwf _ hr

end FvQuiet
