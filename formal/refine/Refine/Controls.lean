import Refine.PromiseDue

/-! # What shows that the theorems say something

Checks of `Refine/PromiseDue.lean`'s statements, kept apart from them:
- the projection's `promise` is what the twin's own `outstanding`, run, reads of its state, and its `parked` is
  the twin's own `parked`, run;
- the real action is not a stutter;
- `promiseDue_refines` applies to a state of the twin, and so does the control `promiseDue_not_promiseDue`
  (which shows that the statement can fail). These two compute float comparisons by `native_decide`, whose
  axioms are the compiler's; no other theorem rests on them. -/

namespace Refine
open SpecTwin
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- The projection's `promise n₀ q`, as a test over the list of promises. -/
theorem alpha_promise_eq_any (n₀ : Peer) (k : Chunk) (now : Float) (bg : MState kind ord)
    (st : SpecTwin.State) (q : Peer) :
    (alpha kind ord n₀ k now bg st).promise n₀ q =
      st.promises.toList.any (fun ((b, r), _) => r == q && b.chunk == k) := by
  rw [Bool.eq_iff_iff]
  simp only [alpha, ite_true, decide_eq_true_eq, List.any_eq_true]
  constructor
  · rintro ⟨b, hb, hm⟩
    obtain ⟨v, hv⟩ : ∃ v, st.promises[(b, q)]? = some v := by
      rw [Std.HashMap.mem_iff_isSome_getElem?] at hm
      exact Option.isSome_iff_exists.mp hm
    exact ⟨((b, q), v), Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr hv, by simp [hb]⟩
  · rintro ⟨⟨⟨b, r⟩, v⟩, hmem, hp⟩
    have hv := Std.HashMap.mem_toList_iff_getElem?_eq_some.mp hmem
    simp only [Bool.and_eq_true, beq_iff_eq] at hp
    obtain ⟨hr, hb⟩ := hp
    subst hr
    refine ⟨b, hb, ?_⟩
    rw [Std.HashMap.mem_iff_isSome_getElem?, hv]
    rfl

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- **The projection against the twin's own code.** The twin's `outstanding(q, a)`, run (`outstandingAns`, the
function of `Sec61.lean` under the interpreter), answers: the projection's `promise n₀ q` at `a`'s chunk, or an
ask of the chunk queued to `q` (in the twin's own `queue[q].normal`). So the projection's `promise` is the part
of the twin's `outstanding` that its promises decide. -/
theorem alpha_promise_is_outstanding (n₀ : Peer) (now : Float) (bg : MState kind ord)
    (q : Peer) (a : Key) (ctx : Ctx) (ans : Answers) (st : SpecTwin.State) :
    outstandingAns q a ctx ans st =
      ((alpha kind ord n₀ a.chunk now bg st).promise n₀ q ||
        (((st.queue.getD q {}).get? .normal).getD []).any (fun e => e.asks.any (fun b => b.chunk == a.chunk))) := by
  rw [outstanding_eq, alpha_promise_eq_any]

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- **The projection's `parked` against the twin's own code.** The twin's `parked(p, a)`, run (`parkedAns`, the
function of `Sec61.lean` under the interpreter), is the projection's `parked n₀ p` at `a`'s chunk and the call's
`now`. -/
theorem alpha_parked_is_parked (n₀ : Peer) (bg : MState kind ord)
    (p : Peer) (a : Key) (ctx : Ctx) (ans : Answers) (st : SpecTwin.State) :
    parkedAns p a ctx ans st = (alpha kind ord n₀ a.chunk ctx.now bg st).parked n₀ p := by
  rw [parked_eq]
  simp [alpha, Key.chunk]
  rw [Bool.eq_iff_iff]                  -- the two sides decide the same comparison, by different instances
  exact ⟨fun h => decide_eq_true (of_decide_eq_true h), fun h => decide_eq_true (of_decide_eq_true h)⟩

/-- The real action is not a stutter: the abstraction of the twin's state changes. -/
theorem promiseDue_not_stutter {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ st.promises → b = a)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st) ≠
      alpha kind ord n₀ a.chunk ctx.now bg st := by
  intro h
  have hg := promiseDue_tr_gives kind ord (promiseDue_refines kind ord (n₀ := n₀) (bg := bg) (r := r) (ans := ans)
    hget hdue hone hnow)
  rw [h] at hg
  rw [hg.1] at hg
  exact absurd hg.2.1 (by simp)

end

/-- A state of the twin with one promise, of an ask by index to peer 1, written at 0.5. The handler is run for
that write time, at `someCtx`'s `now`, 1.0. The group `"g"` here and the id `"x"` below are not keys the toy
makes: the theorems hold for any keys, and these show only that their conditions can hold together. -/
def oneDue : SpecTwin.State := { promises := (∅ : Std.HashMap (Key × Peer) Float).insert (.want "g" 0, 1) 0.5 }

/-- The same with a second promise of the chunk to the same peer, under a full id. -/
def twoDue : SpecTwin.State :=
  { promises := ((∅ : Std.HashMap (Key × Peer) Float).insert (.id "x" "g" 0, 1) 0.5).insert (.want "g" 0, 1) 0.5 }

def someCtx : Ctx := ⟨⟨0.2, 0.05, 0.4, 30.0, none, none, 8192, none, false, false, false, 2, 16384, 256, 32768, 0.7, 0.25, 6, false, 3, 3, true, 6, 2, 0.2, 2, 50e6, 1e9, none, 0.5, false⟩, 1.0, []⟩   -- MAX_PENDING_GROUPS: none; the writer's cards off, FAN_IN 2; PUSH_TTL 6, R_NODE 2, GUARD_GRACE 0.2; R 2

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- **`promiseDue_refines` is not empty.** The theorem itself, applied to a state of the twin: its conditions
hold together there. (Were a condition added to the theorem, this would no longer build.) The two float
comparisons are computed, by `native_decide`. -/
theorem promiseDue_refines_applies (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) (ans : Answers) :
    NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 1 r
      (alpha kind ord n₀ (Key.want "g" 0).chunk someCtx.now bg oneDue)
      (alpha kind ord n₀ (Key.want "g" 0).chunk someCtx.now bg (promiseDueStep (.want "g" 0) 1 0.5 someCtx ans oneDue)) :=
  promiseDue_refines kind ord (t := 0.5) (by simp [oneDue]) (by native_decide)
    (by
      intro b _ hm
      simp [oneDue, Std.HashMap.mem_insert] at hm
      exact hm.symm)
    (by native_decide)

/-- **The control is not empty either.** `promiseDue_not_promiseDue`, applied: with the second promise open, the
twin's step is not the model's `promiseDue`. -/
theorem promiseDue_not_promiseDue_applies (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) (ans : Answers) :
    ¬ NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 1 r
      (alpha kind ord n₀ (Key.want "g" 0).chunk someCtx.now bg twoDue)
      (alpha kind ord n₀ (Key.want "g" 0).chunk someCtx.now bg (promiseDueStep (.want "g" 0) 1 0.5 someCtx ans twoDue)) :=
  promiseDue_not_promiseDue kind ord (t := 0.5) (by simp [twoDue]) (by native_decide)
    ⟨.id "x" "g" 0, by simp, rfl, by simp [twoDue]⟩

end

end Refine
