import Refine.AskInterp
import Carry.Twin

/-! # The twin's side of `promise_due` under `Refine/AskInterp.lean`'s interpreter

Here `promise_due` is proved again under that interpreter's world, with its timer's consumption and its three ways
out together. `Refine/TwinStep.lean` and `Refine/PromiseDue.lean` prove them against another abstraction and
without timers. This file imports the twin and that interpreter, not Veil.

- `promiseFire`: the armed timer at place `i` fires, and the twin's `promise_due(a, p, at)` runs.
- Its three ways out, run: the promise gone, another ask's, or fallen due (`promiseFire_gone`,
  `promiseFire_other`, `promiseFire_parks`).
- What the twin's `promised` and `parked` read after the park. -/

namespace Refine.Carry
open SpecTwin Refine.Ask

section
variable {ctx : Ctx} {ans : Answers} {w : World}

theorem run_promise (a : Key) (p : Peer) :
    run (Tables.promise? a p : M I _) ctx ans w = (w.st.promises.get? (a, p), w) := id rfl
theorem run_erasePromise (a : Key) (p : Peer) : run (Tables.erasePromise a p : M I _) ctx ans w =
    ((), { w with st := { w.st with promises := w.st.promises.erase (a, p) } }) := id rfl
theorem run_setPark (p : Peer) (g : Group) (t : Float) : run (Tables.setPark p g t : M I _) ctx ans w =
    ((), { w with st := { w.st with park := w.st.park.insert p ((w.st.park.getD p {}).insert g t) } }) := id rfl
end

/-- **The step.** The armed timer at place `i` fires: it is taken away, and the twin's `promise_due(a, p, at)` runs. -/
def promiseFire (i : Nat) (a : Key) (p : Peer) (at_ : Float) (ctx : Ctx) (ans : Answers) (w : World) : World :=
  (run (SpecTwin.promiseDue (m := I) a p at_) ctx ans { w with timers := w.timers.eraseIdx i }).2

/-- `promise_due(a, p, at)` where no promise of `a` to `p` is open: the fired timer is gone, and nothing else
changes. -/
theorem promiseFire_gone {i : Nat} {a : Key} {p : Peer} {at_ : Float} {ctx : Ctx} {ans : Answers} {w : World}
    (hget : w.st.promises.get? (a, p) = none) :
    promiseFire i a p at_ ctx ans w = { w with timers := w.timers.eraseIdx i } := by
  unfold promiseFire SpecTwin.promiseDue
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_promise _ _)]
  simp only [hget]
  rw [run_bind_eq _ _ (run_branch _), run_pure]

/-- `promise_due(a, p, at)` where the open promise is another ask's: the fired timer is gone, and nothing else
changes. -/
theorem promiseFire_other {i : Nat} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World}
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = true) :
    promiseFire i a p at_ ctx ans w = { w with timers := w.timers.eraseIdx i } := by
  unfold promiseFire SpecTwin.promiseDue
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_promise _ _)]
  simp only [hget]
  rw [run_ite, ite_eq_left hdue, run_bind_eq _ _ (run_branch _), run_pure]

/-- **The world after the park:** the promise is erased, the peer is parked for the group until
`now + PARK_TTL`, and the fired timer is gone. Nothing else changes. -/
def parkedWorld (i : Nat) (a : Key) (p : Peer) (ctx : Ctx) (w : World) : World :=
  { w with
    st := { w.st with
      promises := w.st.promises.erase (a, p)
      park := w.st.park.insert p ((w.st.park.getD p {}).insert a.group (ctx.now + ctx.c.PARK_TTL)) }
    timers := w.timers.eraseIdx i }

/-- `promise_due(a, p, at)` where the promise is the one that fell due: the twin's own code, run, leaves
`parkedWorld`. -/
theorem promiseFire_parks {i : Nat} {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {w : World}
    (hget : w.st.promises.get? (a, p) = some t) (hdue : (t != at_) = false) :
    promiseFire i a p at_ ctx ans w = parkedWorld i a p ctx w := by
  unfold promiseFire SpecTwin.promiseDue
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_promise _ _)]
  simp only [hget]
  rw [run_ite, ite_eq_right (by simp [hdue]), run_bind_eq _ _ (run_erasePromise _ _),
    run_bind_eq _ _ (run_setPark _ _ _), run_branch]
  rfl

/-! ## What the twin's questions read after the park -/

/-- `promised` reads the promises only. -/
theorem promisedP_of_promises {st st' : State} (h : st'.promises = st.promises) (q : Peer) (k : Chunk) :
    promisedP st' q k = promisedP st q k := by
  unfold promisedP; rw [h]

/-- `parked` reads the parks only. -/
theorem parkedP_of_park {st st' : State} (h : st'.park = st.park) (now : Float) (q : Peer) (g : Group) :
    parkedP now st' q g = parkedP now st q g := by
  unfold parkedP; rw [h]

/-- A promise timer is not a retry timer: taken away, it leaves the chunk's retry timers as they were. -/
theorem retryArmedP_erase_promise {w : World} {i : Nat} {d : Float} {a : Key} {p : Peer} {at_ : Float}
    (h : w.timers[i]? = some (d, Timer.promiseDue a p at_)) (k : Chunk) :
    retryArmedP { w with timers := w.timers.eraseIdx i } k = retryArmedP w k := by
  unfold retryArmedP
  exact any_eraseIdx_of_false _ _ i _ h rfl

/-- A promise of some key of the chunk to `q` is open: said by membership. -/
theorem promisedP_iff {st : State} {q : Peer} {k : Chunk} :
    promisedP st q k = true ↔ ∃ b : Key, b.chunk = k ∧ (b, q) ∈ st.promises := by
  unfold promisedP
  rw [List.any_eq_true]
  constructor
  · rintro ⟨⟨⟨b, r⟩, t⟩, hmem, hb⟩
    simp only [Bool.and_eq_true, beq_iff_eq] at hb
    have hget := Std.HashMap.mem_toList_iff_getElem?_eq_some.mp hmem
    obtain ⟨hr, hk⟩ := hb
    subst hr
    exact ⟨b, hk, by rw [Std.HashMap.mem_iff_isSome_getElem?, hget]; rfl⟩
  · rintro ⟨b, hk, hm⟩
    obtain ⟨t, ht⟩ := Option.isSome_iff_exists.mp (Std.HashMap.mem_iff_isSome_getElem?.mp hm)
    exact ⟨((b, q), t), Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr ht, by simp [hk]⟩

/-- After `(a, p)`'s promise is erased: a promise of the chunk to `q` is open iff one other than `(a, p)` was. -/
theorem promisedP_erase {st : State} {a : Key} {p q : Peer} {k : Chunk} :
    promisedP { st with promises := st.promises.erase (a, p) } q k = true ↔
      ∃ b : Key, b.chunk = k ∧ (b, q) ≠ (a, p) ∧ (b, q) ∈ st.promises := by
  rw [promisedP_iff]
  constructor
  · rintro ⟨b, hk, hm⟩
    rw [Std.HashMap.mem_erase] at hm
    exact ⟨b, hk, fun h => by simp [h] at hm, hm.2⟩
  · rintro ⟨b, hk, hne, hm⟩
    refine ⟨b, hk, ?_⟩
    rw [Std.HashMap.mem_erase]
    exact ⟨beq_eq_false_iff_ne.mpr (fun h => hne h.symm), hm⟩

/-- The erased promise is of another peer or another chunk: the chunk's promise to `q` is as it was. -/
theorem promisedP_erase_other {st : State} {a : Key} {p q : Peer} {k : Chunk} (h : q ≠ p ∨ a.chunk ≠ k) :
    promisedP { st with promises := st.promises.erase (a, p) } q k = promisedP st q k := by
  rw [Bool.eq_iff_iff, promisedP_erase, promisedP_iff]
  constructor
  · rintro ⟨b, hk, _, hm⟩; exact ⟨b, hk, hm⟩
  · rintro ⟨b, hk, hm⟩
    refine ⟨b, hk, ?_, hm⟩
    intro he
    rcases h with h | h
    · exact h (congrArg Prod.snd he)
    · have e : b = a := congrArg Prod.fst he
      exact h (by rw [← e]; exact hk)

/-- The erased promise was the chunk's only one to `p`: none is open after. -/
theorem promisedP_erase_last {st : State} {a : Key} {p : Peer}
    (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ st.promises → b = a) :
    promisedP { st with promises := st.promises.erase (a, p) } p a.chunk = false := by
  rw [Bool.eq_false_iff]
  intro h
  obtain ⟨b, hk, hne, hm⟩ := promisedP_erase.mp h
  exact hne (by rw [hone b hk hm])

/-- Another key of the chunk has a promise open to `p`: one is open after. -/
theorem promisedP_erase_more {st : State} {a : Key} {p : Peer}
    (hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ st.promises) :
    promisedP { st with promises := st.promises.erase (a, p) } p a.chunk = true := by
  obtain ⟨b, hba, hk, hm⟩ := hmore
  exact promisedP_erase.mpr ⟨b, hk, fun he => hba (congrArg Prod.fst he), hm⟩

/-- After `p` is parked for the group `g` until `t`: `p` is parked for `g` iff `now < t`. -/
theorem parkedP_park_self {st : State} {now t : Float} {p : Peer} {g : Group} :
    parkedP now { st with park := st.park.insert p ((st.park.getD p {}).insert g t) } p g = decide (now < t) := by
  simp [parkedP]

/-- ... and every other peer or group is as it was. -/
theorem parkedP_park_other {st : State} {now t : Float} {p q : Peer} {g g' : Group} (h : q ≠ p ∨ g' ≠ g) :
    parkedP now { st with park := st.park.insert p ((st.park.getD p {}).insert g t) } q g' = parkedP now st q g' := by
  unfold parkedP
  by_cases hq : q = p
  · subst hq
    have hg : g' ≠ g := by rcases h with h | h; exact absurd rfl h; exact h
    have hg' : ¬ g = g' := fun e => hg e.symm
    simp [Std.HashMap.getElem?_insert, hg', Std.HashMap.getD_eq_getD_getElem?]
  · have hq' : ¬ p = q := fun e => hq e.symm
    simp [Std.HashMap.getD_insert, hq']

/-! ## The same, of the world after the park -/

section
variable {i : Nat} {a : Key} {p : Peer} {ctx : Ctx} {w : World}

/-- After the park, `p` is parked for the promise's group iff the park lasts. -/
theorem parkedWorld_parked_self :
    parkedP ctx.now (parkedWorld i a p ctx w).st p a.group = decide (ctx.now < ctx.now + ctx.c.PARK_TTL) :=
  (parkedP_of_park (st := { w.st with park := w.st.park.insert p ((w.st.park.getD p {}).insert a.group
    (ctx.now + ctx.c.PARK_TTL)) }) rfl _ _ _).trans parkedP_park_self

/-- ... and every other peer or group is as it was. -/
theorem parkedWorld_parked_other {q : Peer} {g : Group} (h : q ≠ p ∨ g ≠ a.group) :
    parkedP ctx.now (parkedWorld i a p ctx w).st q g = parkedP ctx.now w.st q g :=
  (parkedP_of_park (st := { w.st with park := w.st.park.insert p ((w.st.park.getD p {}).insert a.group
    (ctx.now + ctx.c.PARK_TTL)) }) rfl _ _ _).trans (parkedP_park_other h)

/-- After the park, the promises of another peer, or of another chunk, are as they were. -/
theorem parkedWorld_promised_other {q : Peer} {k : Chunk} (h : q ≠ p ∨ a.chunk ≠ k) :
    promisedP (parkedWorld i a p ctx w).st q k = promisedP w.st q k :=
  (promisedP_of_promises (st := { w.st with promises := w.st.promises.erase (a, p) }) rfl _ _).trans
    (promisedP_erase_other h)

/-- The promise was the chunk's only one to `p`: none is open after the park. -/
theorem parkedWorld_promised_last (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ w.st.promises → b = a) :
    promisedP (parkedWorld i a p ctx w).st p a.chunk = false :=
  (promisedP_of_promises (st := { w.st with promises := w.st.promises.erase (a, p) }) rfl _ _).trans
    (promisedP_erase_last hone)

/-- Another key of the chunk has a promise open to `p`: one is open after the park. -/
theorem parkedWorld_promised_more (hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ w.st.promises) :
    promisedP (parkedWorld i a p ctx w).st p a.chunk = true :=
  (promisedP_of_promises (st := { w.st with promises := w.st.promises.erase (a, p) }) rfl _ _).trans
    (promisedP_erase_more hmore)

/-- The park takes a promise timer away: the chunk's retry timers are as they were. -/
theorem parkedWorld_retryArmed {d at_ : Float} (h : w.timers[i]? = some (d, Timer.promiseDue a p at_))
    (k : Chunk) : retryArmedP (parkedWorld i a p ctx w) k = retryArmedP w k :=
  retryArmedP_erase_promise h k

/-- An open promise of the key to `p` is one of its chunk's. -/
theorem promisedP_of_get {st : State} {t : Float} (hget : st.promises.get? (a, p) = some t) :
    promisedP st p a.chunk = true := by
  refine promisedP_iff.mpr ⟨a, rfl, ?_⟩
  rw [Std.HashMap.mem_iff_isSome_getElem?]
  have h1 : st.promises[(a, p)]? = some t := by simpa using hget
  simp [h1]
end

/-! ## A fixture

As `Refine`'s fixtures, not a world a run reaches. -/

/-- **One promise fallen due:** peer 1 is on the chunk's offer list; a promise of `kA` to it, made for 0.6, is
open; its timer is armed, and so is a retry timer of the key (without one the model's `unparked_retry` fails of
this world). -/
def promisedOne : World :=
  { st := {
      offers := (∅ : Std.HashMap Key (List Peer)).insert kA [1]
      promises := (∅ : Std.HashMap (Key × Peer) Float).insert (kA, 1) 0.6 }
    timers := [(0.4, .promiseDue kA 1 0.6), (0.205, .retryOffer kA)] }

/-- **The step, computed** (no theorem of this file between): the twin's own `promise_due`, run on `promisedOne`
at `now` = 1.0, leaves the retry timer alone and nothing raised, no promise of the chunk to peer 1, and peer 1
parked for the group; before it the promise was open and the peer not parked. The promise is the one that fell
due, and the park lasts. Before it: the chunk is not held, a retry timer of it is armed, peer 1 offered it and
the node did not, and `now` is not below minus infinity. -/
theorem promisedOne_facts :
    (promisedOne.st.promises.get? (kA, 1)).isSome = true ∧
    ((0.6 : Float) != 0.6) = false ∧
    promisedP promisedOne.st 1 kA.chunk = true ∧
    parkedP ctx1.now promisedOne.st 1 kA.group = false ∧
    (promiseFire 0 kA 1 0.6 ctx1 ansBlock promisedOne).timers.length = 1 ∧
    (promiseFire 0 kA 1 0.6 ctx1 ansBlock promisedOne).crashed = [] ∧
    promisedP (promiseFire 0 kA 1 0.6 ctx1 ansBlock promisedOne).st 1 kA.chunk = false ∧
    parkedP ctx1.now (promiseFire 0 kA 1 0.6 ctx1 ansBlock promisedOne).st 1 kA.group = true ∧
    decide (ctx1.now < ctx1.now + ctx1.c.PARK_TTL) = true ∧
    heldP promisedOne.st kA.chunk = false ∧
    retryArmedP promisedOne kA.chunk = true ∧
    offeredP ansBlock promisedOne.st kA.chunk 1 = true ∧
    offeredP ansBlock promisedOne.st kA.chunk n0 = false ∧
    decide (ctx1.now < negInf) = false := by native_decide

/-- `promisedOne` is idle for the chunk but for its promise. -/
theorem promisedOne_idle : IdleButPromises ctx1 ansBlock promisedOne n0 kA.chunk :=
  idleButPromises_of_empty rfl rfl rfl rfl rfl rfl rfl
    (of_decide_eq_false promisedOne_facts.2.2.2.2.2.2.2.2.2.2.2.2.2) promisedOne_facts.2.2.2.2.2.2.2.2.2.2.2.2.1

/-- Every promise of the chunk in `promisedOne` is to an announcer of it. -/
theorem promisedOne_promised_offered (q : Peer) (h : promisedP promisedOne.st q kA.chunk = true) :
    offeredP ansBlock promisedOne.st kA.chunk q = true := by
  obtain ⟨b, _, hm⟩ := promisedP_iff.mp h
  have hq : q = 1 := by
    simp [promisedOne] at hm
    exact hm.2.symm
  subst hq
  exact promisedOne_facts.2.2.2.2.2.2.2.2.2.2.2.1

end Refine.Carry
