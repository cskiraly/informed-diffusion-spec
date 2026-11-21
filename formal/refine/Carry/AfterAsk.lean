import Carry.Plain

/-! # After the asking step, covered steps alone do not reach a state without `work`

The asking step opens the node's window, an open window is `work` (the model's `windowElapse` is enabled), and
no covered step closes one: the two that are model steps take the window closed, and the two others leave the
abstraction as it was. So the safety clause's antecedent is not reached after an ask without a step that is not
covered (the window's end, at the least). The witness therefore runs the `held` branch. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- An open window at a node is `work`. -/
theorem open_window_is_work (r : MTheory kind ord) {s : MState kind ord} {n : Peer}
    (h : s.inWindow n = true) : NoStallEquiv.work r s := by
  rw [work_iff]
  exact Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inl ⟨n, h⟩)))))

open Classical in
/-- **The asking step opens the node's window:** after a retry timer of a key of `k` fires and the twin asks,
the abstraction's `inWindow n₀` is true, whether the queue took the ask or not. -/
theorem asks_opens_window {n₀ : Peer} {k : Chunk} (sl : Nat) (rt : Root)
    {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {bg : MState kind ord} {w : World}
    (hk : a.chunk = k)
    (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hone : ∀ b : Key, b.chunk = a.chunk → b ∈ w.st.askedAt → b = a)
    (hperm : ∀ (xs : List Peer) (b : Key), (ans.ownOrder xs b).Perm xs)
    (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) :
    (abs kind ord n₀ k sl rt ⟨retryFire i a ctx ans w, ctx, ans, bg⟩).inWindow n₀ = true := by
  subst hk
  exact retryAsk_tr_window_gives kind ord
    (retryFire_refines_retryAsk kind ord (n₀ := n₀) (bg := withBlocks kind ord n₀ a.chunk sl rt ans bg)
      (r := default) htimer hheld hstop hexp hwin hfree hone hperm hW)

omit [Inhabited kind] [Inhabited ord] in
/-- **No covered step closes the node's window.** The asking step and the `held` branch's `retryNoop` take the
window closed, so they do not start from an open one; the two others leave the abstraction as it was. -/
theorem covered_keeps_window {n₀ : Peer} {k : Chunk} (sl : Nat) (rt : Root) {c c' : Cfg kind ord}
    (h : Covered kind ord n₀ k c c') (hw : (abs kind ord n₀ k sl rt c).inWindow n₀ = true) :
    (abs kind ord n₀ k sl rt c').inWindow n₀ = true := by
  cases h with
  | asks hk htimer hheld hstop hexp hwin hfree hone hperm hW =>
    subst hk
    have hc := windowP_closed hwin hone
    simp [abs, alpha, hc] at hw
  | @asksOther i d a ctx ans bg w hk htimer hheld hstop hexp hwin hfree =>
    have he := retryFire_other_chunk_same kind ord (n₀ := n₀)
      (bg := withBlocks kind ord n₀ k sl rt ans bg) htimer hheld hstop hexp hwin hfree hk
    unfold abs
    rw [he]
    exact hw
  | @heldSame i d a ctx ans bg w hk _ hheld hrest =>
    subst hk
    have he := retryFire_held_same kind ord (n₀ := n₀) (bg := withBlocks kind ord n₀ a.chunk sl rt ans bg)
      (ctx := ctx) (ans := ans) hheld hrest
    unfold abs
    rw [he]
    exact hw
  | heldLast hk htimer hheld hlast hclosed =>
    subst hk
    simp [abs, alpha, hclosed] at hw

/-- A sequence of covered steps. -/
inductive CoveredRun (n₀ : Peer) (k : Chunk) : Cfg kind ord → Cfg kind ord → Prop
  | start (c : Cfg kind ord) : CoveredRun n₀ k c c
  | step {c₀ c c' : Cfg kind ord} (hrun : CoveredRun n₀ k c₀ c) (hstep : Covered kind ord n₀ k c c') :
      CoveredRun n₀ k c₀ c'

/-- **From an open window, covered steps alone keep `work`:** the state reached has the model's `work`, so the
safety clause's antecedent is false there. With `asks_opens_window`: after the asking step, a state without
`work` is not reached by covered steps. -/
theorem covered_run_keeps_work {n₀ : Peer} {k : Chunk} (sl : Nat) (rt : Root) (r : MTheory kind ord)
    {c₀ c : Cfg kind ord} (hrun : CoveredRun kind ord n₀ k c₀ c)
    (hw : (abs kind ord n₀ k sl rt c₀).inWindow n₀ = true) :
    NoStallEquiv.work r (abs kind ord n₀ k sl rt c) := by
  have h : (abs kind ord n₀ k sl rt c).inWindow n₀ = true := by
    induction hrun with
    | start => exact hw
    | step _ hstep ih => exact covered_keeps_window kind ord sl rt hstep ih
  exact open_window_is_work kind ord r h

/-- **Along a run, one of three holds at `n₀`:** the chunk is held, a window of the chunk is open, or the
model's safety clause holds of the abstraction. From the safety clause at the start alone, and with nothing of
the Veil model's:
- a step of the third kind gives `Invariants` after it, the safety clause among them;
- a step that leaves the abstraction as it was keeps whichever held;
- the asking step opens the window (`asks_opens_window`);
- the `held` branch's `retryNoop` has the chunk held, before and after. -/
theorem run_held_or_window_or_clause {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord}
    {c₀ c : Cfg kind ord} (hrun : Run kind ord n₀ k sl rt r c₀ c)
    (h0 : NoStallEquiv.offers_resolve r (abs kind ord n₀ k sl rt c₀)) :
    (abs kind ord n₀ k sl rt c).got n₀ = true ∨ (abs kind ord n₀ k sl rt c).inWindow n₀ = true ∨
      NoStallEquiv.offers_resolve r (abs kind ord n₀ k sl rt c) := by
  induction hrun with
  | start => exact Or.inr (Or.inr h0)
  | step _ hstep ih =>
    cases hstep with
    | other h => exact Or.inr (Or.inr h.1)
    | same h => rw [h]; exact ih
    | covered h =>
      cases h with
      | asks hk htimer hheld hstop hexp hwin hfree hone hperm hW =>
        exact Or.inr (Or.inl (asks_opens_window kind ord sl rt hk htimer hheld hstop hexp hwin hfree hone hperm hW))
      | @asksOther i d a ctx ans bg w hk htimer hheld hstop hexp hwin hfree =>
        have he := retryFire_other_chunk_same kind ord (n₀ := n₀)
          (bg := withBlocks kind ord n₀ k sl rt ans bg) htimer hheld hstop hexp hwin hfree hk
        unfold abs at ih ⊢
        rw [he]
        exact ih
      | @heldSame i d a ctx ans bg w hk _ hheld hrest =>
        subst hk
        have he := retryFire_held_same kind ord (n₀ := n₀) (bg := withBlocks kind ord n₀ a.chunk sl rt ans bg)
          (ctx := ctx) (ans := ans) hheld hrest
        unfold abs at ih ⊢
        rw [he]
        exact ih
      | heldLast hk htimer hheld hlast hclosed =>
        subst hk
        left
        rw [retryFire_held hheld]
        simp [abs, alpha, hheld]

/-- **The safety clause in the twin's terms, at `n₀`, along a run: it needs nothing of the Veil model's.** From
a configuration whose abstraction satisfies the safety clause: with the switches on and the abstraction without
`work`, if the builder's block is installed and `q` is an announcer of the chunk, the chunk is held or the pull
of its group is stopped.

Why this theorem takes nothing of the model's proof: by `run_held_or_window_or_clause`, the chunk is held (the
conclusion), or a window is open (which is `work`), or the clause holds since the last step of the third kind.
That step assumed it, or, for a promise timer's firing, proved it from the Veil model's statements
(`promise_step`): there the clause does come from the model's proof. No covered step changes whether the chunk
is held or the pull stopped. What the Veil model's statements give along covered steps is the other 20 clauses,
and the clause at the background's nodes (`carried`). -/
theorem run_safety_twin {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord}
    {c₀ c : Cfg kind ord} (hrun : Run kind ord n₀ k sl rt r c₀ c)
    (h0 : NoStallEquiv.offers_resolve r (abs kind ord n₀ k sl rt c₀))
    (hon : AllOn kind ord r) (hquiet : ¬ NoStallEquiv.work r (abs kind ord n₀ k sl rt c))
    (hinst : (c.ans.installedBlock sl rt).isSome = true) {q : Peer} (hoff : offeredP c.ans c.w.st k q = true) :
    heldP c.w.st k = true ∨ stopP c.w.st k.1 = true := by
  rcases run_held_or_window_or_clause kind ord hrun h0 with hg | hw | hc
  · left
    simpa [abs, alpha] using hg
  · exact absurd (open_window_is_work kind ord r hw) hquiet
  · exact offers_resolve_twin kind ord hc hon hquiet hinst hoff

end

end Refine.Carry
