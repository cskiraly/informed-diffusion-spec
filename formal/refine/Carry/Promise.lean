import Carry.Plain
import Carry.TwinPromise

/-! # `promise_due` under `Refine`'s world and abstraction

A promise timer fires (`promiseFire`, `Carry/TwinPromise.lean`), and for a tracked chunk `k` the step is, by the
way out and by what the promise is of:
- the promise gone, or another ask's: the abstraction is as it was (`promiseFire_noop_same`);
- fallen due, a key of another group: as it was (`promiseFire_parks_other_group_same`);
- fallen due, a key of `k`, the chunk's only promise to `p`: the model's `promiseDue n₀ p`
  (`promiseFire_refines_promiseDue`);
- fallen due, a key of `k` with another promise of `k` open to `p`, or a key of another chunk of `k`'s group: the
  model's `parkOther n₀ p` (`promiseFire_refines_parkOther`, `promiseFire_other_chunk_parkOther`).

`hnow`: the park lasts (`now < now + PARK_TTL`: the floating-point lemma is not proved here, as `Refine`'s `hW`). -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- The generated `promiseDue` transition, from its content in plain terms. -/
theorem promiseDue_tr_intro {n q : Peer} {r : MTheory kind ord} {s s' : MState kind ord}
    (hprom : s.promise n q = true)
    (hupd : s' = { s with
      parked := fun x y => if x = n ∧ y = q then true else s.parked x y
      promise := fun x y => if x = n ∧ y = q then false else s.promise x y }) :
    NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      n q r s s' := by
  unfold NoStallEquiv.promiseDue.ext.tr
  simp only [getFrom, setIn, readFrom, id]
  refine ⟨hprom, ?_⟩
  subst hupd
  congr 1
  · funext x y
    by_cases hx : x = n <;> by_cases hy : y = q <;>
      simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
        Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy,
        @eq_comm _ n x, @eq_comm _ q y]
  · funext x y
    by_cases hx : x = n <;> by_cases hy : y = q <;>
      simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
        Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy,
        @eq_comm _ n x, @eq_comm _ q y]

/-- The generated `parkOther` transition, from its content in plain terms. -/
theorem parkOther_tr_intro {n q : Peer} {r : MTheory kind ord} {s s' : MState kind ord}
    (hupd : s' = { s with parked := fun x y => if x = n ∧ y = q then true else s.parked x y }) :
    NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      n q r s s' := by
  unfold NoStallEquiv.parkOther.ext.tr
  simp only [getFrom, setIn, id]
  subst hupd
  congr 1
  funext x y
  by_cases hx : x = n <;> by_cases hy : y = q <;>
    simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
      Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy,
      @eq_comm _ n x, @eq_comm _ q y]

omit [Inhabited kind] [Inhabited ord] in
/-- **The promise gone, or another ask's:** the fired timer is gone and nothing else changes, so the abstraction
is as it was (a promise timer is not a retry timer). -/
theorem promiseFire_noop_same {n₀ : Peer} {bg : MState kind ord} {i : Nat} {d : Float} {a : Key} {p : Peer}
    {at_ : Float} {ctx : Ctx} {ans : Answers} {w : World} (k : Chunk)
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (hnoop : promiseFire i a p at_ ctx ans w = { w with timers := w.timers.eraseIdx i }) :
    alpha kind ord n₀ k ctx ans bg (promiseFire i a p at_ ctx ans w) = alpha kind ord n₀ k ctx ans bg w := by
  rw [hnoop]
  unfold alpha
  congr 1
  funext x
  by_cases hx : x = n₀ <;> simp [hx, retryArmedP_erase_promise htimer]

omit [Inhabited kind] [Inhabited ord] in
/-- The abstraction after the park, given what the tracked chunk's `parked` and `promise` rows read there. -/
theorem alpha_parkedWorld {n₀ : Peer} {bg : MState kind ord} {i : Nat} {d : Float} {a : Key} {p : Peer}
    {at_ : Float} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_)) (park prom : Peer → Bool)
    (hpark : ∀ q, parkedP ctx.now (parkedWorld i a p ctx w).st q k.1 = park q)
    (hprom : ∀ q, promisedP (parkedWorld i a p ctx w).st q k = prom q) :
    alpha kind ord n₀ k ctx ans bg (parkedWorld i a p ctx w) =
      { alpha kind ord n₀ k ctx ans bg w with
        parked := fun n q => if n = n₀ then park q else bg.parked n q
        promise := fun n q => if n = n₀ then prom q else bg.promise n q } := by
  unfold alpha
  congr 1
  case e_retryArmed => funext x; by_cases hx : x = n₀ <;> simp [hx, parkedWorld_retryArmed htimer]
  case e_parked => funext x q; by_cases hx : x = n₀ <;> simp [hx, hpark]
  case e_promise => funext x q; by_cases hx : x = n₀ <;> simp [hx, hprom]

omit [Inhabited kind] [Inhabited ord] in
/-- **Fallen due, a key of another group:** the park is another group's and the promise another chunk's, so the
abstraction is as it was. -/
theorem promiseFire_parks_other_group_same {n₀ : Peer} {bg : MState kind ord} {i : Nat} {d : Float} {a : Key}
    {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false) (hg : a.group ≠ k.1) :
    alpha kind ord n₀ k ctx ans bg (promiseFire i a p at_ ctx ans w) = alpha kind ord n₀ k ctx ans bg w := by
  have hk : a.chunk ≠ k := fun e => hg (by rw [← e]; rfl)
  rw [promiseFire_parks hget hdue,
    alpha_parkedWorld kind ord htimer (fun q => parkedP ctx.now w.st q k.1) (fun q => promisedP w.st q k)
      (fun q => parkedWorld_parked_other (Or.inr (Ne.symm hg))) (fun q => parkedWorld_promised_other (Or.inr hk))]
  rfl

/-- **The real action.** A promise timer fires for a key of the tracked chunk, the promise is the one that fell
due, and it is the chunk's only promise to `p` (`hone`: the model's `promise n q` is one bit per chunk and peer;
the twin's promises are per ask key): the model's `promiseDue n₀ p`. -/
theorem promiseFire_refines_promiseDue {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World}
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ w.st.promises → b = a)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) n₀ p r
      (alpha kind ord n₀ a.chunk ctx ans bg w)
      (alpha kind ord n₀ a.chunk ctx ans bg (promiseFire i a p at_ ctx ans w)) := by
  rw [promiseFire_parks hget hdue]
  apply promiseDue_tr_intro
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).promise n₀ p = true
    simp [alpha, promisedP_of_get hget]
  · rw [alpha_parkedWorld kind ord htimer (fun q => if q = p then true else parkedP ctx.now w.st q a.chunk.1)
      (fun q => if q = p then false else promisedP w.st q a.chunk)]
    · dsimp only
      congr 1
      · funext x y
        by_cases hx : x = n₀ <;> by_cases hy : y = p <;> simp [alpha, hx, hy]
      · funext x y
        by_cases hx : x = n₀ <;> by_cases hy : y = p <;> simp [alpha, hx, hy]
    · intro q
      by_cases hq : q = p
      · subst hq
        show parkedP ctx.now (parkedWorld i a q ctx w).st q a.group = _
        rw [parkedWorld_parked_self]
        simp [hnow]
      · rw [parkedWorld_parked_other (Or.inl hq)]
        simp [hq]
    · intro q
      by_cases hq : q = p
      · subst hq
        rw [parkedWorld_promised_last hone]
        simp
      · rw [parkedWorld_promised_other (Or.inl hq)]
        simp [hq]

/-- The park without the promise's bit: a promise timer fires, the promise fell due, the park is for the tracked
chunk's group, and the tracked chunk's promises read the same after as before: the model's `parkOther n₀ p`. -/
theorem promiseFire_parkOther_of {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false) (hg : a.group = k.1)
    (hprom : ∀ q, promisedP (parkedWorld i a p ctx w).st q k = promisedP w.st q k)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) n₀ p r
      (alpha kind ord n₀ k ctx ans bg w)
      (alpha kind ord n₀ k ctx ans bg (promiseFire i a p at_ ctx ans w)) := by
  rw [promiseFire_parks hget hdue]
  apply parkOther_tr_intro
  rw [alpha_parkedWorld kind ord htimer (fun q => if q = p then true else parkedP ctx.now w.st q k.1)
    (fun q => promisedP w.st q k) _ hprom]
  · dsimp only
    congr 1
    funext x y
    by_cases hx : x = n₀ <;> by_cases hy : y = p <;> simp [alpha, hx, hy]
  · intro q
    by_cases hq : q = p
    · subst hq
      rw [← hg, parkedWorld_parked_self]
      simp [hnow]
    · rw [parkedWorld_parked_other (Or.inl hq)]
      simp [hq]

/-- **The other action, at the promise's own chunk:** another key of the chunk has a promise open to `p`
(`hmore`), so the chunk's bit stays: the model's `parkOther n₀ p`. -/
theorem promiseFire_refines_parkOther {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World}
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ w.st.promises)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) n₀ p r
      (alpha kind ord n₀ a.chunk ctx ans bg w)
      (alpha kind ord n₀ a.chunk ctx ans bg (promiseFire i a p at_ ctx ans w)) := by
  refine promiseFire_parkOther_of kind ord htimer hget hdue rfl (fun q => ?_) hnow
  by_cases hq : q = p
  · subst hq
    rw [parkedWorld_promised_more hmore, promisedP_of_get hget]
  · exact parkedWorld_promised_other (Or.inl hq)

/-- **The other action, for another chunk of the group:** the promise is another chunk's, the park is the
group's: the model's `parkOther n₀ p`. -/
theorem promiseFire_other_chunk_parkOther {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (htimer : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hk : a.chunk ≠ k) (hg : a.group = k.1) (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) n₀ p r
      (alpha kind ord n₀ k ctx ans bg w)
      (alpha kind ord n₀ k ctx ans bg (promiseFire i a p at_ ctx ans w)) :=
  promiseFire_parkOther_of kind ord htimer hget hdue hg (fun _ => parkedWorld_promised_other (Or.inr hk)) hnow

end

end Refine.Carry
