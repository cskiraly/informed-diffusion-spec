import Carry.Fv

/-! # A run of the twin, and the model's safety theorem carried along it

**The abstraction** is `Refine/RetryAsk.lean`'s `alpha`, unchanged, over a background that takes two of `n₀`'s
relations from the answers: `gate n₀` from `authenticable`, `installed n₀` from `installed_block` at the
builder's slot and root. So every theorem of `Refine` applies to it as it stands.

**A step** is covered (a retry timer's firing, by one of `Refine/RetryAsk.lean`'s four theorems), or leaves the
abstraction as it was, or is any other change, under the named hypothesis that `Invariants` holds after it.

**The carried theorem:** along a run, from a configuration whose abstraction satisfies the model's `Invariants`,
the abstraction of every configuration does; so the model's safety clause holds there, and is read in the twin's
terms at `n₀`. The Veil model's statements for `retryAsk` and `retryNoop` are hypotheses (`Carry/Fv.lean`).
`Invariants` is not assumed along the run: it is assumed at the start, and after each step of the third kind. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- **The background with `n₀`'s blocks from the answers.** `gate n₀`: an installed block's bid commits the
chunk's group (`authenticable(g)`). `installed n₀`: the builder's block, of slot `sl` and root `rt`, is installed
(`installed_block(sl, rt)`). Every other relation and row is `bg`'s. -/
def withBlocks (n₀ : Peer) (k : Chunk) (sl : Nat) (rt : Root) (ans : Answers) (bg : MState kind ord) :
    MState kind ord :=
  { bg with
    gate := fun n => if n = n₀ then ans.authenticable k.1 else bg.gate n
    installed := fun n => if n = n₀ then (ans.installedBlock sl rt).isSome else bg.installed n }

/-- **A configuration:** the world (the twin's state, with the timers, asks' counts and raises of the
interpreter in `Refine/AskInterp.lean`), the context (the constants and `now`), the answers, and a background (a
state of the model). -/
structure Cfg where
  w : World
  ctx : Ctx
  ans : Answers
  bg : MState kind ord

/-- **The abstraction of a configuration:** `Refine/RetryAsk.lean`'s `alpha` over the background with `n₀`'s
blocks. -/
def abs (n₀ : Peer) (k : Chunk) (sl : Nat) (rt : Root) (c : Cfg kind ord) : MState kind ord :=
  alpha kind ord n₀ k c.ctx c.ans (withBlocks kind ord n₀ k sl rt c.ans c.bg) c.w

/-- **The covered steps:** a retry timer fires, on one of the four ways `Refine/RetryAsk.lean` proves. The
context, the answers and the background are the same before and after. Each carries the hypotheses of its
theorem there. -/
inductive Covered (n₀ : Peer) (k : Chunk) : Cfg kind ord → Cfg kind ord → Prop
  /-- a retry timer of a key of `k` fires, and the twin asks: the model's `retryAsk n₀ pick j full` -/
  | asks {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {bg : MState kind ord} {w : World}
      (hk : a.chunk = k)
      (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
      (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
      (hexp : ans.expired a.group = false)
      (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
      (hfree : freeP ctx ans w.st a ≠ [])
      (hone : ∀ b : Key, b.chunk = a.chunk → b ∈ w.st.askedAt → b = a)
      (hperm : ∀ (xs : List Peer) (b : Key), (ans.ownOrder xs b).Perm xs)
      (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) :
      Covered n₀ k ⟨w, ctx, ans, bg⟩ ⟨retryFire i a ctx ans w, ctx, ans, bg⟩
  /-- the same for a key of another chunk: the abstraction is as it was -/
  | asksOther {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {bg : MState kind ord} {w : World}
      (hk : a.chunk ≠ k)
      (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
      (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
      (hexp : ans.expired a.group = false)
      (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
      (hfree : freeP ctx ans w.st a ≠ []) :
      Covered n₀ k ⟨w, ctx, ans, bg⟩ ⟨retryFire i a ctx ans w, ctx, ans, bg⟩
  /-- a retry timer of a key of `k` fires, the chunk held, another retry timer of `k` remains: as it was -/
  | heldSame {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {bg : MState kind ord} {w : World}
      (hk : a.chunk = k)
      (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
      (hheld : heldP w.st a.chunk = true)
      (hrest : retryArmedP { w with timers := w.timers.eraseIdx i } a.chunk = true) :
      Covered n₀ k ⟨w, ctx, ans, bg⟩ ⟨retryFire i a ctx ans w, ctx, ans, bg⟩
  /-- the same, the last retry timer of `k`, no window of `k` open: the model's `retryNoop n₀` -/
  | heldLast {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {bg : MState kind ord} {w : World}
      (hk : a.chunk = k)
      (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
      (hheld : heldP w.st a.chunk = true)
      (hlast : retryArmedP { w with timers := w.timers.eraseIdx i } a.chunk = false)
      (hclosed : windowP ctx w.st a.chunk = false) :
      Covered n₀ k ⟨w, ctx, ans, bg⟩ ⟨retryFire i a ctx ans w, ctx, ans, bg⟩

/-- **A step of a run.** -/
inductive Step (n₀ : Peer) (k : Chunk) (sl : Nat) (rt : Root) (r : MTheory kind ord) :
    Cfg kind ord → Cfg kind ord → Prop
  /-- a covered step -/
  | covered {c c' : Cfg kind ord} (h : Covered kind ord n₀ k c c') : Step n₀ k sl rt r c c'
  /-- any change of the world, the clock, the answers or the background that leaves the abstraction as it was -/
  | same {c c' : Cfg kind ord} (h : abs kind ord n₀ k sl rt c' = abs kind ord n₀ k sl rt c) : Step n₀ k sl rt r c c'
  /-- **any other change, under the named hypothesis:** the model's `Invariants` holds of the abstraction after
  it. Nothing else is said of such a step: not that it is a step of the model, and not which. -/
  | other {c c' : Cfg kind ord} (h : MInv kind ord r (abs kind ord n₀ k sl rt c')) : Step n₀ k sl rt r c c'

/-- **A run:** a finite sequence of steps. -/
inductive Run (n₀ : Peer) (k : Chunk) (sl : Nat) (rt : Root) (r : MTheory kind ord) :
    Cfg kind ord → Cfg kind ord → Prop
  | start (c : Cfg kind ord) : Run n₀ k sl rt r c c
  | step {c₀ c c' : Cfg kind ord} (hrun : Run n₀ k sl rt r c₀ c) (hstep : Step kind ord n₀ k sl rt r c c') :
      Run n₀ k sl rt r c₀ c'

open Classical in
/-- A covered step preserves the model's `Invariants`, given the Veil model's statements for `retryAsk` and
`retryNoop`: by `Refine/RetryAsk.lean`'s theorem for the step, then the bridge. -/
theorem covered_preserves (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} (sl : Nat) (rt : Root) {r : MTheory kind ord} {c c' : Cfg kind ord}
    (h : Covered kind ord n₀ k c c') (hinv : MInv kind ord r (abs kind ord n₀ k sl rt c)) :
    MInv kind ord r (abs kind ord n₀ k sl rt c') := by
  cases h with
  | asks hk htimer hheld hstop hexp hwin hfree hone hperm hW =>
    subst hk
    exact retryAsk_preserves kind ord hA hinv
      (retryFire_refines_retryAsk kind ord htimer hheld hstop hexp hwin hfree hone hperm hW)
  | @asksOther i d a ctx ans bg w hk htimer hheld hstop hexp hwin hfree =>
    have he := retryFire_other_chunk_same kind ord (n₀ := n₀)
      (bg := withBlocks kind ord n₀ k sl rt ans bg) htimer hheld hstop hexp hwin hfree hk
    unfold abs
    rw [he]
    exact hinv
  | @heldSame i d a ctx ans bg w hk _ hheld hrest =>
    subst hk
    have he := retryFire_held_same kind ord (n₀ := n₀) (bg := withBlocks kind ord n₀ a.chunk sl rt ans bg)
      (ctx := ctx) (ans := ans) hheld hrest
    unfold abs
    rw [he]
    exact hinv
  | heldLast hk htimer hheld hlast hclosed =>
    subst hk
    exact retryNoop_preserves kind ord hN hinv
      (retryFire_held_last_retryNoop kind ord htimer hheld hlast hclosed)

/-- A step preserves the model's `Invariants`: a covered one by the Veil model's statements, one that leaves the
abstraction as it was by the equality, any other by its own hypothesis. -/
theorem step_preserves (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c c' : Cfg kind ord}
    (h : Step kind ord n₀ k sl rt r c c') (hinv : MInv kind ord r (abs kind ord n₀ k sl rt c)) :
    MInv kind ord r (abs kind ord n₀ k sl rt c') := by
  cases h with
  | covered h => exact covered_preserves kind ord hA hN sl rt h hinv
  | same h => rw [h]; exact hinv
  | other h => exact h

/-- **The carried invariant.** Along a run from a configuration whose abstraction satisfies the model's
`Invariants`, the abstraction of the configuration reached does. -/
theorem carried (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c₀ c : Cfg kind ord}
    (hrun : Run kind ord n₀ k sl rt r c₀ c) (h0 : MInv kind ord r (abs kind ord n₀ k sl rt c₀)) :
    MInv kind ord r (abs kind ord n₀ k sl rt c) := by
  induction hrun with
  | start => exact h0
  | step _ hstep ih => exact step_preserves kind ord hA hN hstep ih

/-- **The carried safety theorem, as the model states it:** `offers_resolve` holds of the abstraction of every
configuration of a run that starts where `Invariants` holds. -/
theorem carried_offers_resolve (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c₀ c : Cfg kind ord}
    (hrun : Run kind ord n₀ k sl rt r c₀ c) (h0 : MInv kind ord r (abs kind ord n₀ k sl rt c₀)) :
    NoStallEquiv.offers_resolve r (abs kind ord n₀ k sl rt c) :=
  (carried kind ord hA hN hrun h0).1

/-- **From the model's `Init`,** with the Veil model's statements for the initializer too: a run from a
configuration whose abstraction is the model's `Init`. -/
theorem carried_from_init (hI : FvInit kind ord) (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c₀ c : Cfg kind ord}
    (hrun : Run kind ord n₀ k sl rt r c₀ c)
    (hinit : NoStallEquiv.Init (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) r
      (abs kind ord n₀ k sl rt c₀)) :
    NoStallEquiv.offers_resolve r (abs kind ord n₀ k sl rt c) :=
  carried_offers_resolve kind ord hA hN hrun (init_invariants kind ord hI hinit)

end

end Refine.Carry
