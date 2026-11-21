import Carry.Promise
import Carry.Witness

/-! # `promise_due`'s firing as a step of a run

`promise_due`, `parkOther` among its ways out, is re-proved under `Refine`'s world (`Carry/Promise.lean`). Here
its six cases are one relation (`PromiseCovered`), and a step of it keeps the model's `Invariants`, given the Veil
model's statements for `promiseDue` and `parkOther` (`FvPromiseDue`, `FvParkOther`, `Carry/Fv.lean`).

The run's own definition is not changed (`Carry/Run.lean`): such a firing enters a run through the third step
kind, whose named hypothesis is then proved, not assumed (`promise_step`). So the carried theorem and its
hypotheses are as they were, and the coverage grows by this file's two. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- **A promise timer fires,** on one of the ways `Carry/Promise.lean` proves. The context, the answers and the
background are the same before and after. `hnow`: the park lasts. -/
inductive PromiseCovered (n₀ : Peer) (k : Chunk) : Cfg kind ord → Cfg kind ord → Prop
  /-- no promise of the key to the peer is open: the abstraction is as it was -/
  | gone {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ : Float} {ctx : Ctx} {ans : Answers}
      {bg : MState kind ord} {w : World}
      (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
      (hget : w.st.promises.get? (a, p) = none) :
      PromiseCovered n₀ k ⟨w, ctx, ans, bg⟩ ⟨promiseFire i a p at_ ctx ans w, ctx, ans, bg⟩
  /-- the open promise is another ask's: as it was -/
  | other {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers}
      {bg : MState kind ord} {w : World}
      (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
      (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = true) :
      PromiseCovered n₀ k ⟨w, ctx, ans, bg⟩ ⟨promiseFire i a p at_ ctx ans w, ctx, ans, bg⟩
  /-- fallen due, a key of another group: as it was -/
  | otherGroup {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers}
      {bg : MState kind ord} {w : World}
      (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
      (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false) (hg : a.group ≠ k.1) :
      PromiseCovered n₀ k ⟨w, ctx, ans, bg⟩ ⟨promiseFire i a p at_ ctx ans w, ctx, ans, bg⟩
  /-- fallen due, a key of `k`, the chunk's only promise to the peer: the model's `promiseDue n₀ p` -/
  | due {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers}
      {bg : MState kind ord} {w : World}
      (hk : a.chunk = k)
      (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
      (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
      (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ w.st.promises → b = a)
      (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
      PromiseCovered n₀ k ⟨w, ctx, ans, bg⟩ ⟨promiseFire i a p at_ ctx ans w, ctx, ans, bg⟩
  /-- fallen due, a key of `k`, another promise of `k` open to the peer: the model's `parkOther n₀ p` -/
  | more {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers}
      {bg : MState kind ord} {w : World}
      (hk : a.chunk = k)
      (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
      (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
      (hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ w.st.promises)
      (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
      PromiseCovered n₀ k ⟨w, ctx, ans, bg⟩ ⟨promiseFire i a p at_ ctx ans w, ctx, ans, bg⟩
  /-- fallen due, a key of another chunk of `k`'s group: the model's `parkOther n₀ p` -/
  | otherChunk {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers}
      {bg : MState kind ord} {w : World}
      (hk : a.chunk ≠ k) (hg : a.group = k.1)
      (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
      (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
      (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
      PromiseCovered n₀ k ⟨w, ctx, ans, bg⟩ ⟨promiseFire i a p at_ ctx ans w, ctx, ans, bg⟩

/-- **A promise timer's firing keeps the model's `Invariants`,** given the Veil model's statements for
`promiseDue` and `parkOther`: by the step's theorem, then the bridge. -/
theorem promise_preserves (hP : FvPromiseDue kind ord) (hK : FvParkOther kind ord)
    {n₀ : Peer} {k : Chunk} (sl : Nat) (rt : Root) {r : MTheory kind ord} {c c' : Cfg kind ord}
    (h : PromiseCovered kind ord n₀ k c c') (hinv : MInv kind ord r (abs kind ord n₀ k sl rt c)) :
    MInv kind ord r (abs kind ord n₀ k sl rt c') := by
  cases h with
  | @gone i d a p at_ ctx ans bg w htimer hget =>
    have he := promiseFire_noop_same kind ord (n₀ := n₀) (bg := withBlocks kind ord n₀ k sl rt ans bg)
      (ctx := ctx) (ans := ans) k htimer (promiseFire_gone hget)
    unfold abs
    rw [he]
    exact hinv
  | @other i d a p at_ t ctx ans bg w htimer hget hdue =>
    have he := promiseFire_noop_same kind ord (n₀ := n₀) (bg := withBlocks kind ord n₀ k sl rt ans bg)
      (ctx := ctx) (ans := ans) k htimer (promiseFire_other hget hdue)
    unfold abs
    rw [he]
    exact hinv
  | @otherGroup i d a p at_ t ctx ans bg w htimer hget hdue hg =>
    have he := promiseFire_parks_other_group_same kind ord (n₀ := n₀)
      (bg := withBlocks kind ord n₀ k sl rt ans bg) (ctx := ctx) (ans := ans) htimer hget hdue hg
    unfold abs
    rw [he]
    exact hinv
  | due hk htimer hget hdue hone hnow =>
    subst hk
    exact promiseDue_preserves kind ord hP hinv
      (promiseFire_refines_promiseDue kind ord htimer hget hdue hone hnow)
  | more hk htimer hget hdue hmore hnow =>
    subst hk
    exact parkOther_preserves kind ord hK hinv
      (promiseFire_refines_parkOther kind ord htimer hget hdue hmore hnow)
  | otherChunk hk hg htimer hget hdue hnow =>
    exact parkOther_preserves kind ord hK hinv
      (promiseFire_other_chunk_parkOther kind ord htimer hget hdue hk hg hnow)

/-- **A promise timer's firing is a step of a run** from a configuration where `Invariants` hold: of the third
kind, with its named hypothesis proved from the Veil model's statements for `promiseDue` and `parkOther`. -/
theorem promise_step (hP : FvPromiseDue kind ord) (hK : FvParkOther kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c c' : Cfg kind ord}
    (h : PromiseCovered kind ord n₀ k c c') (hinv : MInv kind ord r (abs kind ord n₀ k sl rt c)) :
    Step kind ord n₀ k sl rt r c c' :=
  Step.other (promise_preserves kind ord hP hK sl rt h hinv)

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- **It applies:** on `promisedOne`, the firing of the promise's timer is the `due` case, the model's
`promiseDue n₀ 1`, for any background and answers. So the case's hypotheses hold together. -/
theorem promise_due_applies (bg : MState kind ord) (ans : Answers) :
    PromiseCovered kind ord n0 kA.chunk ⟨promisedOne, ctx1, ans, bg⟩
      ⟨promiseFire 0 kA 1 0.6 ctx1 ans promisedOne, ctx1, ans, bg⟩ := by
  refine PromiseCovered.due (d := 0.4) (t := 0.6) rfl rfl ?_ promisedOne_facts.2.1 ?_
    (of_decide_eq_true promisedOne_facts.2.2.2.2.2.2.2.2.1)
  · simp [promisedOne]
  · intro b _ hm
    simp [promisedOne] at hm
    exact hm.symm

/-- The model's `Invariants` hold of the abstraction of `promisedOne`, over a background of holders with the
builder's block installed, all seven switches on. -/
theorem promise_start :
    MInv kind ord (rOn kind ord)
      (abs kind ord n0 kA.chunk 0 "r" ⟨promisedOne, ctx1, ansBlock, bgHolders kind ord⟩) := by
  rw [abs_prom kind ord promisedOne_idle rfl rfl, promisedOne_facts.2.2.2.2.2.2.2.2.2.2.1]
  exact promState_invariants kind ord _ n0 _ _ _ _ promisedOne_facts.2.2.2.2.2.2.2.2.2.2.2.2.1
    promisedOne_promised_offered

/-- **`promise_step`, applied:** from that configuration, where `Invariants` hold, the firing of the promise's
timer is a step of a run, given the Veil model's statements for `promiseDue` and `parkOther`. So
`promise_step`'s hypotheses hold together. Here `Invariants` after the step, the safety clause among them, come
from the Veil model's theorem for `promiseDue`, applied to `Invariants` before it (`promise_start`) through the
step's refinement theorem (`promiseFire_refines_promiseDue`): no shorter argument gives the clause (without the
retry timer the same firing leaves the model's `stalled`). -/
theorem promise_step_applies (hP : FvPromiseDue kind ord) (hK : FvParkOther kind ord) :
    Step kind ord n0 kA.chunk 0 "r" (rOn kind ord) ⟨promisedOne, ctx1, ansBlock, bgHolders kind ord⟩
      ⟨promiseFire 0 kA 1 0.6 ctx1 ansBlock promisedOne, ctx1, ansBlock, bgHolders kind ord⟩ :=
  promise_step kind ord hP hK (promise_due_applies kind ord _ _) (promise_start kind ord)

end

end Refine.Carry
