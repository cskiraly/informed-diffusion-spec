import NoStallEquivModel
import Refine.TwinStep

/-! # The model's side: the twin's `promise_due` is the model's `promiseDue`

The transitions used here are the ones Veil generates for the asking model (`NoStallEquiv.<action>.ext.tr`, and
`NoStallEquiv.NextTr` over them), taken as they are, at the representation Veil generates beside them
(`FieldAbstractType`: every relation a function to `Bool`). Nothing of the model is written again here. No
tactic of Veil's is used: the proofs are `unfold`, `simp` and case splits. -/

namespace Refine
open SpecTwin
open scoped NoStallEquiv    -- Veil's instances for the model's fields are scoped

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- The model's state with the twin's peers as its nodes. -/
abbrev MState := NoStallEquiv.State (NoStallEquiv.FieldAbstractType Peer kind ord)

/-- The model's constants (which cards are on). -/
abbrev MTheory := NoStallEquiv.Theory Peer kind ord

open Classical in
/-- A projection onto the two relations this file needs; not a candidate for the whole refinement's abstraction.
Node `n₀`'s §6.1 state `st`, read at `now` for the chunk `k`, gives the model's row `n₀` of `promise` and `parked`;
every other row, and every other relation, is `bg`'s, the same state before and after: that this step leaves the
rest alone is part of each statement, not proved from anything, and nothing ties the interpreter's answers to
`bg` (`held` to `got`, say).
- `promise n₀ q`: a promise of some key of the chunk to `q` is open (the first clause of the twin's `outstanding`);
- `parked n₀ q`: `now < park[q][g]` (the twin's `parked`). -/
noncomputable def alpha (n₀ : Peer) (k : Chunk) (now : Float) (bg : MState kind ord) (st : SpecTwin.State) :
    MState kind ord :=
  { bg with
    promise := fun n q =>
      if n = n₀ then decide (∃ b : Key, b.chunk = k ∧ (b, q) ∈ st.promises) else bg.promise n q
    parked := fun n q =>
      if n = n₀ then decide (now < (st.park.getD q {}).getD k.1 negInf) else bg.parked n q }

/-- **The real action.** The twin's `promise_due(a, p, at)` at node `n₀`, where the promise is the one that fell
due, is the model's `promiseDue n₀ p`: Veil's generated transition holds between the abstractions of the twin's
state before and after. Conditions:
- `hone`: no other key of the chunk has a promise open to `p` (the model's `promise n q` is one bit per chunk and
  peer; the twin's promises are per ask key);
- `hnow`: the park lasts (`now < now + PARK_TTL`: the two are finite and `PARK_TTL` is positive and not lost in
  rounding). -/
theorem promiseDue_refines {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ st.promises → b = a)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ p r
      (alpha kind ord n₀ a.chunk ctx.now bg st)
      (alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st)) := by
  rw [promiseDue_parks hget hdue]
  have hmem : (a, p) ∈ st.promises := by
    rw [Std.HashMap.mem_iff_isSome_getElem?]
    have h1 : st.promises[(a, p)]? = some t := by simpa using hget
    simp [h1]
  unfold NoStallEquiv.promiseDue.ext.tr
  refine ⟨?_, ?_⟩
  · simp only [NoStallEquiv.en_promiseDue, getFrom]
    show (alpha kind ord n₀ a.chunk ctx.now bg st).promise n₀ p = true
    simp only [alpha, ite_true, decide_eq_true_eq]
    exact ⟨a, rfl, hmem⟩
  · simp only [setIn, getFrom]
    unfold alpha
    congr 1
    · funext x y
      simp [Veil.FieldRepresentation.setSingle]
      by_cases hx : x = n₀ <;> by_cases hy : y = p <;>
        simp [Veil.CanonicalField.set, Veil.IteratedArrow.curry, Veil.IteratedArrow.uncurry,
          Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy, Key.chunk, Std.HashMap.getD_insert]
      · exact hnow                                          -- the parked peer: the park lasts
      · have hy' : ¬ p = y := fun h => hy h.symm            -- another peer of this node: its park is as it was
        rw [Bool.eq_iff_iff]
        simp [hy']
        exact decide_eq_true_iff
      · intro h; exact absurd h.symm hx                     -- another node's row: `bg`'s
      · intro h; exact absurd h.symm hx
    · funext x y
      simp [Veil.FieldRepresentation.setSingle]
      by_cases hx : x = n₀ <;> by_cases hy : y = p <;>
        simp [Veil.CanonicalField.set, Veil.IteratedArrow.curry, Veil.IteratedArrow.uncurry,
          Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy, Std.HashMap.mem_erase]
      · intro b hb hne hm                                   -- the peer: no key of the chunk promises it now
        exact hne (hone b hb hm).symm
      · have hy' : ¬ p = y := fun h => hy h.symm            -- another peer of this node: its promises stay
        simp [hy']
      · intro _ h; exact hx h.symm                          -- another node's row: `bg`'s
      · intro _; exact Or.inl (fun h => hx h.symm)

open Classical in
/-- `NextTr` at the label `promiseDue n q` is the action's `ext.tr`, by definition. -/
theorem nextTr_promiseDue_iff {n q : Peer} {r : MTheory kind ord} {s s' : MState kind ord} :
    NoStallEquiv.NextTr (MTheory kind ord) (MState kind ord) Peer kind ord
        (NoStallEquiv.FieldAbstractType Peer kind ord) r s (NoStallEquiv.Label.promiseDue n q) s' ↔
      NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
        (NoStallEquiv.FieldAbstractType Peer kind ord) n q r s s' :=
  Iff.rfl

open Classical in
/-- `NextStep` is a step of `NextTr` under some label, by definition. -/
theorem nextStep_iff {r : MTheory kind ord} {s s' : MState kind ord} :
    NoStallEquiv.NextStep (MTheory kind ord) (MState kind ord) Peer kind ord
        (NoStallEquiv.FieldAbstractType Peer kind ord) r s s' ↔
      ∃ label, NoStallEquiv.NextTr (MTheory kind ord) (MState kind ord) Peer kind ord
        (NoStallEquiv.FieldAbstractType Peer kind ord) r s label s' :=
  Iff.rfl

open Classical in
/-- The same, as a step of the model: `NoStallEquiv.NextTr` is the generated next-step relation over the
actions' transitions, by label. It unfolds to the action's `ext.tr` by itself. -/
theorem promiseDue_is_next {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hone : ∀ b : Key, b.chunk = a.chunk → (b, p) ∈ st.promises → b = a)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.NextTr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r
      (alpha kind ord n₀ a.chunk ctx.now bg st)
      (NoStallEquiv.Label.promiseDue n₀ p)
      (alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st)) :=
  promiseDue_refines kind ord hget hdue hone hnow

open Classical in
/-- A step of the twin that leaves its state as it was leaves the projection as it was, which is the model's
`stutter`, whatever the chunk and the time the projection reads. -/
theorem same_state_stutters {n₀ : Peer} {k : Chunk} {now : Float} {bg : MState kind ord} {r : MTheory kind ord}
    {st st' : SpecTwin.State} (h : st' = st) :
    NoStallEquiv.NextTr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r
      (alpha kind ord n₀ k now bg st) NoStallEquiv.Label.stutter (alpha kind ord n₀ k now bg st') := by
  subst h
  show NoStallEquiv.stutter.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
    (NoStallEquiv.FieldAbstractType Peer kind ord) r _ _
  unfold NoStallEquiv.stutter.ext.tr
  rfl

open Classical in
/-- `retry_offer(a)` where the chunk is held: the twin's state is as it was, so the projection is, and that is
the model's `stutter` here. It is so only because the projection takes `retryArmed` from `bg`: the timer that
fired is not in any state of this file. Which step of the model the firing is, once armed timers are in the
abstraction, is not proved here: if `retryArmed` means that some retry timer of the chunk is pending, a firing
that leaves another pending can be a stutter, and the last one can be `retryNoop`, whose guard also needs the
window closed. -/
theorem retryOffer_held_stutters {n₀ : Peer} {k : Chunk} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State} (hheld : (st.mine.getD a.group 0).has a.index = true) :
    NoStallEquiv.NextTr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r
      (alpha kind ord n₀ k ctx.now bg st) NoStallEquiv.Label.stutter
      (alpha kind ord n₀ k ctx.now bg (retryOfferStep a ctx ans st)) :=
  same_state_stutters kind ord (retryOffer_held hheld)

/-- **The generated transition as a hypothesis.** From a `promiseDue n q` step of the model, in plain Lean: the
promise was open, it is closed, the peer is parked, and what the action does not name is as it was (here `got`,
and another peer's park). -/
theorem promiseDue_tr_gives {n q : Peer} {r : MTheory kind ord} {s s' : MState kind ord}
    (h : NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n q r s s') :
    s.promise n q = true ∧ s'.promise n q = false ∧ s'.parked n q = true ∧ s'.got = s.got ∧
      ∀ q', q' ≠ q → s'.parked n q' = s.parked n q' := by
  unfold NoStallEquiv.promiseDue.ext.tr at h
  obtain ⟨hen, hupd⟩ := h
  simp only [NoStallEquiv.en_promiseDue, getFrom] at hen
  simp only [setIn, getFrom] at hupd
  subst hupd
  refine ⟨hen, ?_, ?_, rfl, ?_⟩
  · simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
      Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp]
  · simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
      Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp]
  · intro q' hq'
    have hq'' : ¬ q = q' := fun h => hq' h.symm
    simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
      Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hq'']

/-- **Where `hone` fails.** Another key of the chunk has a promise open to `p` (the chunk asked of the same peer
under several keys): the twin still erases the one promise and parks `p`, and the chunk's promise to `p` stays
open. This handler's state change is then that of the model's `parkOther n₀ p`, which parks and has no guard. It
does not follow that several keys of one chunk fit the model. -/
theorem promiseDue_refines_parkOther {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ st.promises)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ p r
      (alpha kind ord n₀ a.chunk ctx.now bg st)
      (alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st)) := by
  rw [promiseDue_parks hget hdue]
  obtain ⟨b, hba, hbk, hbm⟩ := hmore
  unfold NoStallEquiv.parkOther.ext.tr
  simp only [setIn, getFrom]
  unfold alpha
  congr 1
  · funext x y
    simp [Veil.FieldRepresentation.setSingle]
    by_cases hx : x = n₀ <;> by_cases hy : y = p <;>
      simp [Veil.CanonicalField.set, Veil.IteratedArrow.curry, Veil.IteratedArrow.uncurry,
        Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy, Key.chunk, Std.HashMap.getD_insert]
    · exact hnow
    · have hy' : ¬ p = y := fun h => hy h.symm
      rw [Bool.eq_iff_iff]
      simp [hy']
      exact decide_eq_true_iff
    · intro h; exact absurd h.symm hx
    · intro h; exact absurd h.symm hx
  · funext x y
    by_cases hx : x = n₀ <;> by_cases hy : y = p <;> simp [hx, hy, Std.HashMap.mem_erase]
    · constructor                                           -- the peer: `b`'s promise keeps the bit
      · intro _; exact ⟨b, hbk, fun h => hba h.symm, hbm⟩
      · intro _; exact ⟨a, rfl, by
          rw [Std.HashMap.mem_iff_isSome_getElem?]
          have h1 : st.promises[(a, p)]? = some t := by simpa using hget
          simp [h1]⟩
    · have hy' : ¬ p = y := fun h => hy h.symm              -- another peer of this node
      simp [hy']

/-- **The control: the statement can fail.** With that second promise open, the twin's step is not the model's
`promiseDue n₀ p`: the model closes the chunk's promise to `p`, and under the abstraction it is still open. So
`promiseDue_refines` needs `hone`, and the generated transition does tell the two steps apart. -/
theorem promiseDue_not_promiseDue {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ st.promises) :
    ¬ NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ p r
      (alpha kind ord n₀ a.chunk ctx.now bg st)
      (alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st)) := by
  intro h
  have hclosed := (promiseDue_tr_gives kind ord h).2.1
  rw [promiseDue_parks hget hdue] at hclosed
  obtain ⟨b, hba, hbk, hbm⟩ := hmore
  simp [alpha] at hclosed
  exact hclosed b hbk (fun h => hba h.symm) hbm

open Classical in
/-- **Every way through the handler, at its own chunk.** Each of the ways through the twin's
`promise_due(a, p, at)` is a step of the model, for any state of the twin, read at the chunk of `a` and at one
`now`, with `hnow` alone (`promiseDue_handler_is_next_for`, below, has it for any tracked chunk):
- `promiseDue n₀ p` where the promise is the one that fell due and no other key of the chunk promises `p`;
- `parkOther n₀ p` where another key does;
- a stutter where the promise is gone or is another ask's. -/
theorem promiseDue_handler_is_next {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.NextStep (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r
      (alpha kind ord n₀ a.chunk ctx.now bg st)
      (alpha kind ord n₀ a.chunk ctx.now bg (promiseDueStep a p at_ ctx ans st)) := by
  cases hget : st.promises.get? (a, p) with
  | none => exact ⟨NoStallEquiv.Label.stutter, same_state_stutters kind ord (promiseDue_gone hget)⟩
  | some t =>
    cases hdue : (t != at_) with
    | true => exact ⟨NoStallEquiv.Label.stutter, same_state_stutters kind ord (promiseDue_other hget hdue)⟩
    | false =>
      by_cases hmore : ∃ b : Key, b ≠ a ∧ b.chunk = a.chunk ∧ (b, p) ∈ st.promises
      · exact ⟨NoStallEquiv.Label.parkOther n₀ p, promiseDue_refines_parkOther kind ord (r := r) hget hdue hmore hnow⟩
      · refine ⟨NoStallEquiv.Label.promiseDue n₀ p, promiseDue_is_next kind ord hget hdue ?_ hnow⟩
        intro b hb hm
        exact Classical.byContradiction fun hne => hmore ⟨b, hne, hb, hm⟩

/-! ## Against a tracked chunk

The theorems above read the abstraction at the chunk of the handler's own key. A refinement fixes the chunk
first. For a tracked chunk `k`, a due promise of another chunk of `k`'s group parks the peer, and one of another
group changes nothing of `k`'s rows. -/

/-- A due promise of another chunk of the tracked chunk's group: the model's `parkOther n₀ p`. -/
theorem promiseDue_other_chunk_parkOther {n₀ : Peer} {k : Chunk} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hk : a.chunk ≠ k) (hg : a.group = k.1)
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ p r
      (alpha kind ord n₀ k ctx.now bg st)
      (alpha kind ord n₀ k ctx.now bg (promiseDueStep a p at_ ctx ans st)) := by
  rw [promiseDue_parks hget hdue]
  unfold NoStallEquiv.parkOther.ext.tr
  simp only [setIn, getFrom]
  unfold alpha
  congr 1
  · funext x y
    simp [Veil.FieldRepresentation.setSingle]
    by_cases hx : x = n₀ <;> by_cases hy : y = p <;>
      simp [Veil.CanonicalField.set, Veil.IteratedArrow.curry, Veil.IteratedArrow.uncurry,
        Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy, hg, Std.HashMap.getD_insert]
    · exact hnow
    · have hy' : ¬ p = y := fun h => hy h.symm
      rw [Bool.eq_iff_iff]
      simp [hy']
    · intro h; exact absurd h.symm hx
    · intro h; exact absurd h.symm hx
  · funext x y
    by_cases hx : x = n₀ <;> simp [hx, Std.HashMap.mem_erase]
    constructor
    · rintro ⟨b, hb, hm⟩; exact ⟨b, hb, fun h _ => hk (h ▸ hb), hm⟩
    · rintro ⟨b, hb, _, hm⟩; exact ⟨b, hb, hm⟩

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- A due promise of a chunk of another group: nothing of the tracked chunk's rows changes. -/
theorem promiseDue_other_group_same {n₀ : Peer} {k : Chunk} {bg : MState kind ord}
    {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false)
    (hg : a.group ≠ k.1) :
    alpha kind ord n₀ k ctx.now bg (promiseDueStep a p at_ ctx ans st) = alpha kind ord n₀ k ctx.now bg st := by
  rw [promiseDue_parks hget hdue]
  have hk : a.chunk ≠ k := fun h => hg (h ▸ rfl)
  unfold alpha
  congr 1
  · funext x y
    by_cases hx : x = n₀ <;> by_cases hy : y = p <;> simp [hx, hy, Std.HashMap.getD_insert, hg]
    have hy' : ¬ p = y := fun h => hy h.symm
    simp [hy']
  · funext x y
    by_cases hx : x = n₀ <;> simp [hx, Std.HashMap.mem_erase]
    constructor
    · rintro ⟨b, hb, _, hm⟩; exact ⟨b, hb, hm⟩
    · rintro ⟨b, hb, hm⟩; exact ⟨b, hb, fun h _ => hk (h ▸ hb), hm⟩

open Classical in
/-- **The handler against a tracked chunk.** For any chunk `k` the projection reads, every way through
`promise_due(a, p, at)` is a step of the model's `NextStep`, under `hnow`:
- the due promise is of `k`: `promiseDue n₀ p`, or `parkOther n₀ p` where another key of `k` promises `p`;
- it is of another chunk of `k`'s group: `parkOther n₀ p`;
- it is of another group, or is gone, or is another ask's: a stutter. -/
theorem promiseDue_handler_is_next_for {n₀ : Peer} {k : Chunk} {bg : MState kind ord} {r : MTheory kind ord}
    {a : Key} {p : Peer} {at_ : Float} {ctx : Ctx} {ans : Answers} {st : SpecTwin.State}
    (hnow : ctx.now < ctx.now + ctx.c.PARK_TTL) :
    NoStallEquiv.NextStep (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r
      (alpha kind ord n₀ k ctx.now bg st)
      (alpha kind ord n₀ k ctx.now bg (promiseDueStep a p at_ ctx ans st)) := by
  by_cases hk : a.chunk = k
  · subst hk
    exact promiseDue_handler_is_next kind ord hnow
  cases hget : st.promises.get? (a, p) with
  | none => exact ⟨NoStallEquiv.Label.stutter, same_state_stutters kind ord (promiseDue_gone hget)⟩
  | some t =>
    cases hdue : (t != at_) with
    | true => exact ⟨NoStallEquiv.Label.stutter, same_state_stutters kind ord (promiseDue_other hget hdue)⟩
    | false =>
      by_cases hg : a.group = k.1
      · exact ⟨NoStallEquiv.Label.parkOther n₀ p,
          promiseDue_other_chunk_parkOther kind ord (r := r) hget hdue hk hg hnow⟩
      · refine ⟨NoStallEquiv.Label.stutter, ?_⟩
        show NoStallEquiv.stutter.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
          (NoStallEquiv.FieldAbstractType Peer kind ord) r _ _
        unfold NoStallEquiv.stutter.ext.tr
        exact (promiseDue_other_group_same kind ord hget hdue hg).symm

end

end Refine
