import NoStallEquivModel
import Refine.AskInterp

/-! # The model's side: a retry timer's firing is the model's `retryAsk` when the twin asks

The transition is the one Veil generates for the asking model (`NoStallEquiv.retryAsk.ext.tr`), taken as it is,
at the representation Veil generates beside it (`FieldAbstractType`: every relation a function to `Bool`).
Nothing of the model is written again here, and no tactic of Veil's is used.

The twin's side (the interpreter, the world, the step `retryFire`, and what the twin's questions read of the world
as plain functions) is `Refine/AskInterp.lean`, which does not import Veil. This file never elaborates the twin's
monad. -/

namespace Refine.Ask
open SpecTwin
open scoped NoStallEquiv    -- Veil's instances for the model's fields are scoped

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- The model's state with the twin's peers as its nodes. -/
abbrev MState := NoStallEquiv.State (NoStallEquiv.FieldAbstractType Peer kind ord)

/-- The model's constants (which cards are on). -/
abbrev MTheory := NoStallEquiv.Theory Peer kind ord

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord] in
/-- The number the model gives the next ask to a peer, after `c` asks of the chunk that its queue took: the
first, the second, the third, and `o4` for every later one. -/
def nextOrd (c : Nat) : ord :=
  match c with
  | 0 => NoStallEquiv.ord_EnumClass.o1
  | 1 => NoStallEquiv.ord_EnumClass.o2
  | 2 => NoStallEquiv.ord_EnumClass.o3
  | _ => NoStallEquiv.ord_EnumClass.o4

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [Inhabited ord] in
/-- The model's `made · · j`, from the count `c` of asks the peer's queue took: the first was made once one was,
the second once two were, the third once three were, and `o4` once four were. -/
def madeOrd (c : Nat) (j : ord) : Bool :=
  decide ((j = NoStallEquiv.ord_EnumClass.o1 ∧ 1 ≤ c) ∨ (j = NoStallEquiv.ord_EnumClass.o2 ∧ 2 ≤ c) ∨
    (j = NoStallEquiv.ord_EnumClass.o3 ∧ 3 ≤ c) ∨ (j = NoStallEquiv.ord_EnumClass.o4 ∧ 4 ≤ c))

/-- **The abstraction, for this file.** Node `n₀`'s world `w`, read at `ctx.now` for the tracked chunk `k`, with
the answers `ans`, gives the model's row `n₀` of twelve relations. Every other row, and the ten other relations
(`gate`, `installed`, `peerHas`, `ledger`, the stages other than a queued ask of `n₀`'s, and the six history
relations), are `bg`'s, the same before and after: that the step leaves them alone is part of each statement.
- `got n₀`: the chunk is held (`mine`); `stop n₀`: the group is in the twin's `stop_pull` (`stopP`: its own
  table, so a step of the twin can set it, and none clears it);
- `offered n₀ q`: q is an announcer of some key of the chunk (`offeredP`);
- `inWindow n₀`: some key of the chunk has its window open (`windowP`);
- `retryArmed n₀`: a retry timer of some key of the chunk is armed, among the interpreter's timers;
- `lrArmed n₀`: the chunk is in `last_resort_armed`; `askedParked n₀ q`: q is in `asked_parked[k]`;
- `parked n₀ q`: `now < park[q][g]`; `tied n₀ q`: a copy of the chunk from q waits for a root;
- `promise n₀ q`: a promise of some key of the chunk to q is open;
- `made n₀ q j`: from the interpreter's count of the asks of the chunk that q's queue took (`madeOrd`);
- `stage askQ n₀ q j`: an IWANT in the twin's own `queue[q].normal` names the chunk, and `j` is the number of
  the last ask q's queue took. (A queued ask with a count of zero would read as the first: `World.push` raises
  the count with every ask it appends, so no world the interpreter makes from one without queued asks has it.) -/
def alpha (n₀ : Peer) (k : Chunk) (ctx : Ctx) (ans : Answers) (bg : MState kind ord) (w : World) :
    MState kind ord :=
  { bg with
    got := fun n => if n = n₀ then heldP w.st k else bg.got n
    stop := fun n => if n = n₀ then stopP w.st k.1 else bg.stop n
    offered := fun n q => if n = n₀ then offeredP ans w.st k q else bg.offered n q
    inWindow := fun n => if n = n₀ then windowP ctx w.st k else bg.inWindow n
    retryArmed := fun n => if n = n₀ then retryArmedP w k else bg.retryArmed n
    lrArmed := fun n => if n = n₀ then w.st.lastResortArmed.contains k else bg.lrArmed n
    parked := fun n q => if n = n₀ then parkedP ctx.now w.st q k.1 else bg.parked n q
    askedParked := fun n q => if n = n₀ then (w.st.askedParked.getD k {}).contains q else bg.askedParked n q
    promise := fun n q => if n = n₀ then promisedP w.st q k else bg.promise n q
    tied := fun n q => if n = n₀ then tiedP w.st q k else bg.tied n q
    made := fun n q j => if n = n₀ then madeOrd ord (w.made k q) j else bg.made n q j
    stage := fun K x y j =>
      if K = NoStallEquiv.kind_EnumClass.askQ ∧ x = n₀ then
        queuedP w.st y k && decide (j = nextOrd ord (w.made k y - 1))
      else bg.stage K x y j }

/-! ## The asks' numbers, and the generated transition in plain terms

`retryAsk_tr_intro` gives the generated `retryAsk.ext.tr` from its content said in plain terms (the guard,
relation by relation, and the three updates as functions); the two `_gives` lemmas take it as a hypothesis. All
three are proved from the generated definition, unfolded: nothing here is taken as the model's on trust. -/

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord] in
/-- The four numbers differ. -/
theorem ord_ne :
    (NoStallEquiv.ord_EnumClass.o1 : ord) ≠ NoStallEquiv.ord_EnumClass.o2 ∧
    (NoStallEquiv.ord_EnumClass.o1 : ord) ≠ NoStallEquiv.ord_EnumClass.o3 ∧
    (NoStallEquiv.ord_EnumClass.o1 : ord) ≠ NoStallEquiv.ord_EnumClass.o4 ∧
    (NoStallEquiv.ord_EnumClass.o2 : ord) ≠ NoStallEquiv.ord_EnumClass.o3 ∧
    (NoStallEquiv.ord_EnumClass.o2 : ord) ≠ NoStallEquiv.ord_EnumClass.o4 ∧
    (NoStallEquiv.ord_EnumClass.o3 : ord) ≠ NoStallEquiv.ord_EnumClass.o4 := by
  have h := NoStallEquiv.ord_EnumClass.distinct (ord := ord)
  simp only [distinctN_pairwise_neq, List.nodup_cons, List.mem_cons, List.not_mem_nil, or_false,
    not_or, List.nodup_nil, and_true] at h
  obtain ⟨⟨h12, h13, h14⟩, ⟨h23, h24⟩, h34, _⟩ := h
  exact ⟨h12, h13, h14, h23, h24, h34⟩

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [Inhabited ord] in
/-- The next ask's number, after `c` asks, is the model's `nextAsk` over `madeOrd c`. -/
theorem nextOrd_next (c : Nat) :
    (nextOrd ord c = NoStallEquiv.ord_EnumClass.o1 ∧ madeOrd ord c NoStallEquiv.ord_EnumClass.o1 = false) ∨
    (nextOrd ord c = NoStallEquiv.ord_EnumClass.o2 ∧ madeOrd ord c NoStallEquiv.ord_EnumClass.o1 = true ∧
      madeOrd ord c NoStallEquiv.ord_EnumClass.o2 = false) ∨
    (nextOrd ord c = NoStallEquiv.ord_EnumClass.o3 ∧ madeOrd ord c NoStallEquiv.ord_EnumClass.o2 = true ∧
      madeOrd ord c NoStallEquiv.ord_EnumClass.o3 = false) ∨
    (nextOrd ord c = NoStallEquiv.ord_EnumClass.o4 ∧ madeOrd ord c NoStallEquiv.ord_EnumClass.o3 = true) := by
  obtain ⟨h12, h13, h14, h23, h24, h34⟩ := ord_ne ord
  match c with
  | 0 => simp [nextOrd, madeOrd]
  | 1 => simp [nextOrd, madeOrd, h12, Ne.symm h12]
  | 2 => simp [nextOrd, madeOrd, h12, h13, h23, Ne.symm h12, Ne.symm h13, Ne.symm h23]
  | n + 3 => simp [nextOrd, madeOrd, h34, Ne.symm h34, Ne.symm h13, Ne.symm h23]

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [Inhabited ord] in
/-- One ask more: the next number is made, and what was made stays. -/
theorem madeOrd_succ (c : Nat) (j : ord) :
    madeOrd ord (c + 1) j = (decide (j = nextOrd ord c) || madeOrd ord c j) := by
  obtain ⟨h12, h13, h14, h23, h24, h34⟩ := ord_ne ord
  rcases NoStallEquiv.ord_EnumClass.complete j with rfl | rfl | rfl | rfl <;>
  match c with
  | 0 => simp [nextOrd, madeOrd, h12, h13, h14, h23, h24, h34, Ne.symm h12, Ne.symm h13, Ne.symm h14, Ne.symm h23, Ne.symm h24, Ne.symm h34]
  | 1 => simp [nextOrd, madeOrd, h12, h13, h14, h23, h24, h34, Ne.symm h12, Ne.symm h13, Ne.symm h14, Ne.symm h23, Ne.symm h24, Ne.symm h34]
  | 2 => simp [nextOrd, madeOrd, h12, h13, h14, h23, h24, h34, Ne.symm h12, Ne.symm h13, Ne.symm h14, Ne.symm h23, Ne.symm h24, Ne.symm h34]
  | n + 3 => simp [nextOrd, madeOrd, h12, h13, h14, h23, h24, h34, Ne.symm h12, Ne.symm h13, Ne.symm h14, Ne.symm h23, Ne.symm h24, Ne.symm h34]

open Classical in
/-- The generated transition, from its content in plain terms. -/
theorem retryAsk_tr_intro {n q : Peer} {j : ord} {full : Bool} {r : MTheory kind ord} {s s' : MState kind ord}
    (harmed : s.retryArmed n = true) (hwin : s.inWindow n = false) (hgot : s.got n = false)
    (hstop : s.stop n = false) (hoff : s.offered n q = true) (hpark : s.parked n q = false)
    (htied : s.tied n q = false)
    (hout : r.noReask = true →
      (∀ x : ord, s.stage NoStallEquiv.kind_EnumClass.askQ n q x = false) ∧ s.promise n q = false)
    (hnext : (j = NoStallEquiv.ord_EnumClass.o1 ∧ s.made n q NoStallEquiv.ord_EnumClass.o1 = false) ∨
      (j = NoStallEquiv.ord_EnumClass.o2 ∧ s.made n q NoStallEquiv.ord_EnumClass.o1 = true ∧
        s.made n q NoStallEquiv.ord_EnumClass.o2 = false) ∨
      (j = NoStallEquiv.ord_EnumClass.o3 ∧ s.made n q NoStallEquiv.ord_EnumClass.o2 = true ∧
        s.made n q NoStallEquiv.ord_EnumClass.o3 = false) ∨
      (j = NoStallEquiv.ord_EnumClass.o4 ∧ s.made n q NoStallEquiv.ord_EnumClass.o3 = true))
    (hupd : s' = { s with
      inWindow := fun x => if x = n then true else s.inWindow x
      made := fun x y z => if full = false ∧ x = n ∧ y = q ∧ z = j then true else s.made x y z
      stage := fun K x y z =>
        if full = false ∧ K = NoStallEquiv.kind_EnumClass.askQ ∧ x = n ∧ y = q ∧ z = j then true
        else s.stage K x y z }) :
    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n q j full r s s' := by
  unfold NoStallEquiv.retryAsk.ext.tr
  simp only [getFrom, setIn, readFrom, id]
  refine ⟨harmed, ?_, ?_, ?_, hoff, ?_, ?_, ?_, ?_, ?_⟩
  · show ¬ s.inWindow n = true
    simp [hwin]
  · show ¬ s.got n = true
    simp [hgot]
  · show ¬ s.stop n = true
    simp [hstop]
  · show ¬ s.parked n q = true
    simp [hpark]
  · show ¬ s.tied n q = true
    simp [htied]
  · intro hr
    obtain ⟨h1, h2⟩ := hout hr
    refine ⟨fun x => ?_, ?_⟩
    · show ¬ s.stage NoStallEquiv.kind_EnumClass.askQ n q x = true
      simp [h1 x]
    · show ¬ s.promise n q = true
      simp [h2]
  · simp only [NoStallEquiv.nextAsk]
    show (j = NoStallEquiv.ord_EnumClass.o1 ∧ ¬ s.made n q NoStallEquiv.ord_EnumClass.o1 = true) ∨
      (j = NoStallEquiv.ord_EnumClass.o2 ∧ s.made n q NoStallEquiv.ord_EnumClass.o1 = true ∧
        ¬ s.made n q NoStallEquiv.ord_EnumClass.o2 = true) ∨
      (j = NoStallEquiv.ord_EnumClass.o3 ∧ s.made n q NoStallEquiv.ord_EnumClass.o2 = true ∧
        ¬ s.made n q NoStallEquiv.ord_EnumClass.o3 = true) ∨
      (j = NoStallEquiv.ord_EnumClass.o4 ∧ s.made n q NoStallEquiv.ord_EnumClass.o3 = true)
    simpa only [Bool.not_eq_true] using hnext
  · subst hupd
    cases full
    · simp only [↓reduceIte, true_and]
      congr 1
      · funext x
        by_cases hx : x = n <;>
          simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
            Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, @eq_comm _ n x]
      · funext x y z
        by_cases hx : x = n <;> by_cases hy : y = q <;> by_cases hz : z = j <;>
          simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
            Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hy, hz,
            @eq_comm _ n x, @eq_comm _ q y, @eq_comm _ j z]
      · funext K x y z
        by_cases hK : K = NoStallEquiv.kind_EnumClass.askQ <;> by_cases hx : x = n <;> by_cases hy : y = q <;>
          by_cases hz : z = j <;>
          simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
            Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hK, hx, hy, hz,
            @eq_comm _ n x, @eq_comm _ q y, @eq_comm _ j z, @eq_comm _ NoStallEquiv.kind_EnumClass.askQ K]
    · simp only [Bool.true_eq_false, ↓reduceIte, false_and]
      congr 1
      funext x
      by_cases hx : x = n <;>
        simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
          Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, @eq_comm _ n x]

open Classical in
/-- The generated transition as a hypothesis, refused: the stages and the asks' numbers are as they were. -/
theorem retryAsk_tr_refused_gives {n q : Peer} {j : ord} {r : MTheory kind ord} {s s' : MState kind ord}
    (h : NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n q j true r s s') :
    s'.stage = s.stage ∧ s'.made = s.made := by
  unfold NoStallEquiv.retryAsk.ext.tr at h
  simp only [getFrom, setIn, readFrom, id] at h
  obtain ⟨_, _, _, _, _, _, _, _, _, hupd⟩ := h
  simp only [Bool.true_eq_false, ↓reduceIte] at hupd
  subst hupd
  exact ⟨rfl, rfl⟩

open Classical in
/-- The generated transition as a hypothesis, either outcome: the node's window is open after it. -/
theorem retryAsk_tr_window_gives {n q : Peer} {j : ord} {full : Bool} {r : MTheory kind ord} {s s' : MState kind ord}
    (h : NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n q j full r s s') :
    s'.inWindow n = true := by
  unfold NoStallEquiv.retryAsk.ext.tr at h
  simp only [getFrom, setIn, readFrom, id] at h
  obtain ⟨_, _, _, _, _, _, _, _, _, hupd⟩ := h
  cases full
  · simp only [↓reduceIte] at hupd
    subst hupd
    simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
      Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp]
  · simp only [Bool.true_eq_false, ↓reduceIte] at hupd
    subst hupd
    simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
      Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp]

open Classical in
/-- The generated transition as a hypothesis, admitted: the ask is queued. -/
theorem retryAsk_tr_admitted_gives {n q : Peer} {j : ord} {r : MTheory kind ord} {s s' : MState kind ord}
    (h : NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n q j false r s s') :
    s'.stage NoStallEquiv.kind_EnumClass.askQ n q j = true := by
  unfold NoStallEquiv.retryAsk.ext.tr at h
  simp only [getFrom, setIn, readFrom, id] at h
  obtain ⟨_, _, _, _, _, _, _, _, _, hupd⟩ := h
  simp only [↓reduceIte] at hupd
  subst hupd
  simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
    Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp]

/-! ## The statement

**The step:** the armed timer at place `i` is a retry timer of the key `a` (`htimer`); it fires, and the twin's
`retry_offer(a)` runs (`retryFire`). The tracked chunk is `a`'s.

**The hypotheses**, each about the state, the answers or the constants:
- `hheld`, `hstop`: the chunk is not held, and the pull is not stopped;
- `hexp`: the group is not expired. The model has no lifetimes;
- `hwin`: the key's window is closed at `now`;
- `hfree`: some announcer is neither parked, nor tied, nor outstanding (the asking path);
- `hone`: **one form of key per chunk** in `asked_at`. The twin's window is per ask key and the model's per
  chunk;
- `hperm`: the node's own order is a permutation;
- `hW`: an ask made now is in its window (`now − now < IWANT_WINDOW`: `now` finite and `IWANT_WINDOW > 0`. The
  floating-point lemma from those two to this is not proved here).

**The model's step** is `retryAsk n₀ q j full`, with:
- `q` the twin's own pick (`pickP`: part of what is proved, by `retryFire_asks`);
- `j` the number of the next ask to it, from the interpreter's count;
- `full` read from whether the queue took the IWANT (`admits`), not from what `enqueue` answered. Both outcomes
  are in the one statement. -/

open Classical in
/-- **The asking path, refined.** A firing of a retry timer of the tracked chunk, where the twin asks, is the model's
`retryAsk n₀ pick j full`: Veil's generated transition holds between the abstractions of the world before and
after. -/
theorem retryFire_refines_retryAsk {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hone : ∀ b : Key, b.chunk = a.chunk → b ∈ w.st.askedAt → b = a)
    (hperm : ∀ (xs : List Peer) (b : Key), (ans.ownOrder xs b).Perm xs)
    (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) :
    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ (pickP ctx ans w.st a)
      (nextOrd ord (w.made a.chunk (pickP ctx ans w.st a)))
      (!ans.admits (pickP ctx ans w.st a) (.iwant [a]) false) r
      (alpha kind ord n₀ a.chunk ctx ans bg w)
      (alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w)) := by
  rw [retryFire_asks hheld hstop hexp hwin hfree]
  obtain ⟨hann, hpk, htd, hout⟩ := free_gives (pickP_mem a w.st hfree)
  have hprom : promisedP w.st (pickP ctx ans w.st a) a.chunk = false := by
    cases h : promisedP w.st (pickP ctx ans w.st a) a.chunk <;> simp_all [outstandingP]
  have hqd : queuedP w.st (pickP ctx ans w.st a) a.chunk = false := by
    cases h : queuedP w.st (pickP ctx ans w.st a) a.chunk <;> simp_all [outstandingP]
  apply retryAsk_tr_intro
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).retryArmed n₀ = true
    simp [alpha, retryArmedP_of_timer htimer]
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).inWindow n₀ = false
    simp [alpha, windowP_closed hwin hone]
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).got n₀ = false
    simp [alpha, hheld]
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).stop n₀ = false
    simpa [alpha, Key.chunk] using hstop
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).offered n₀ _ = true
    simp [alpha, offeredP_of_announcer hperm hann]
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).parked n₀ _ = false
    simpa [alpha, Key.chunk] using hpk
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).tied n₀ _ = false
    simp [alpha, htd]
  · intro _
    refine ⟨fun x => ?_, ?_⟩
    · show (alpha kind ord n₀ a.chunk ctx ans bg w).stage _ n₀ _ x = false
      simp [alpha, hqd]
    · show (alpha kind ord n₀ a.chunk ctx ans bg w).promise n₀ _ = false
      simp [alpha, hprom]
  · have h := nextOrd_next ord (w.made a.chunk (pickP ctx ans w.st a))
    simpa [alpha] using h
  · unfold alpha
    congr 1
    case e_got => simp only [heldP, askedWorld_mine]
    case e_stop => simp only [stopP, askedWorld_stopPull]
    case e_offered => simp only [offeredP, askedWorld_offers, askedWorld_offered]
    case e_inWindow =>
      funext x
      by_cases hx : x = n₀ <;> simp [hx, windowP_asked i a ctx ans w hW]
    case e_retryArmed =>
      funext x
      by_cases hx : x = n₀ <;> simp [hx, retryArmedP_asked, retryArmedP_of_timer htimer]
    case e_lrArmed => simp only [askedWorld_lrArmed]
    case e_parked => simp only [parkedP, askedWorld_park]
    case e_askedParked => simp only [askedWorld_askedParked]
    case e_promise => simp only [promisedP, askedWorld_promises]
    case e_tied => simp only [tiedP, askedWorld_tied]
    case e_made =>
      funext x y z
      dsimp only
      rw [askedWorld_made]
      by_cases hx : x = n₀ <;> by_cases hy : y = pickP ctx ans w.st a <;>
        cases hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false <;>
        simp [hx, hy, madeOrd_succ]
    case e_stage =>
      funext K x y z
      dsimp only
      rw [askedWorld_queued, askedWorld_made]
      by_cases hK : K = NoStallEquiv.kind_EnumClass.askQ <;> by_cases hx : x = n₀ <;>
        by_cases hy : y = pickP ctx ans w.st a <;>
        cases hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false <;>
        simp [hK, hx, hy, hqd]

open Classical in
/-- **The control, with the admission outcome fixed: the queue took the ask.** Then the step is not the model's
refused ask, `retryAsk … true`, of any peer under any number: a refused ask leaves the stages as they were, and
the abstraction has a queued ask to the pick that it had not. So the statement tells the two outcomes apart. -/
theorem retryFire_admitted_not_refused {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = true) (q : Peer) (j : ord) :
    ¬ NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ q j true r
      (alpha kind ord n₀ a.chunk ctx ans bg w)
      (alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w)) := by
  intro h
  rw [retryFire_asks hheld hstop hexp hwin hfree] at h
  obtain ⟨_, _, _, hout⟩ := free_gives (pickP_mem a w.st hfree)
  have hqd : queuedP w.st (pickP ctx ans w.st a) a.chunk = false := by
    cases h : queuedP w.st (pickP ctx ans w.st a) a.chunk <;> simp_all [outstandingP]
  have hst := congrFun (congrFun (congrFun (congrFun (retryAsk_tr_refused_gives kind ord h).1
    NoStallEquiv.kind_EnumClass.askQ) n₀) (pickP ctx ans w.st a))
    (nextOrd ord (w.made a.chunk (pickP ctx ans w.st a)))
  simp [alpha, askedWorld_queued, askedWorld_made, hadm, hqd] at hst

open Classical in
/-- **The other way: the queue refused the ask.** Then the step is not the model's admitted ask of the pick,
under any number: the model would have a queued ask to the pick, and the twin's queue is as it was. A step whose
enqueue is dropped leaves this world, the refused one, whatever the queue would have answered: this theorem is
the one that says such a step does not pass as the admitted ask. -/
theorem retryFire_refused_not_admitted {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = false) (j : ord) :
    ¬ NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ (pickP ctx ans w.st a) j false r
      (alpha kind ord n₀ a.chunk ctx ans bg w)
      (alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w)) := by
  intro h
  rw [retryFire_asks hheld hstop hexp hwin hfree] at h
  obtain ⟨_, _, _, hout⟩ := free_gives (pickP_mem a w.st hfree)
  have hqd : queuedP w.st (pickP ctx ans w.st a) a.chunk = false := by
    cases h : queuedP w.st (pickP ctx ans w.st a) a.chunk <;> simp_all [outstandingP]
  have hst := retryAsk_tr_admitted_gives kind ord h
  simp [alpha, askedWorld_queued, hadm, hqd] at hst

/-! ## Against a tracked chunk

The theorem above reads the abstraction at the chunk of the timer's own key. A refinement fixes the chunk first.
For a tracked chunk `k`, a firing for a key of another chunk, where the twin asks, changes nothing of `k`'s rows:
the ask's window, its timer, its queued IWANT and its count are another chunk's. -/

omit [Inhabited kind] [Inhabited ord] in
/-- A firing for a key of another chunk, where the twin asks: the tracked chunk's abstraction is as it was. -/
theorem retryFire_other_chunk_same {n₀ : Peer} {bg : MState kind ord}
    {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hk : a.chunk ≠ k) :
    alpha kind ord n₀ k ctx ans bg (retryFire i a ctx ans w) = alpha kind ord n₀ k ctx ans bg w := by
  rw [retryFire_asks hheld hstop hexp hwin hfree]
  obtain ⟨hw, ht, hq, hm⟩ := askedWorld_other_chunk (ctx := ctx) (ans := ans) htimer hk
  unfold alpha
  congr 1
  case e_got => simp only [heldP, askedWorld_mine]
  case e_stop => simp only [stopP, askedWorld_stopPull]
  case e_offered => simp only [offeredP, askedWorld_offers, askedWorld_offered]
  case e_inWindow => simp only [hw]
  case e_retryArmed => simp only [ht]
  case e_lrArmed => simp only [askedWorld_lrArmed]
  case e_parked => simp only [parkedP, askedWorld_park]
  case e_askedParked => simp only [askedWorld_askedParked]
  case e_promise => simp only [promisedP, askedWorld_promises]
  case e_tied => simp only [tiedP, askedWorld_tied]
  case e_made => simp only [hm]
  case e_stage => simp only [hq, hm]

open Classical in
/-- **The firing against a tracked chunk.** For any chunk `k` the abstraction reads, a firing of a retry timer
where the twin asks is a step of the model (`NextStep`): `retryAsk n₀ pick j full` where the timer's key is of `k`,
and a stutter where it is of another chunk. -/
theorem retryFire_asks_is_next_for {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hone : ∀ b : Key, b.chunk = a.chunk → b ∈ w.st.askedAt → b = a)
    (hperm : ∀ (xs : List Peer) (b : Key), (ans.ownOrder xs b).Perm xs)
    (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) :
    NoStallEquiv.NextStep (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r
      (alpha kind ord n₀ k ctx ans bg w)
      (alpha kind ord n₀ k ctx ans bg (retryFire i a ctx ans w)) := by
  by_cases hk : a.chunk = k
  · subst hk
    exact ⟨NoStallEquiv.Label.retryAsk n₀ _ _ _,
      retryFire_refines_retryAsk kind ord htimer hheld hstop hexp hwin hfree hone hperm hW⟩
  · refine ⟨NoStallEquiv.Label.stutter, ?_⟩
    show NoStallEquiv.stutter.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) r _ _
    unfold NoStallEquiv.stutter.ext.tr
    exact (retryFire_other_chunk_same kind ord htimer hheld hstop hexp hwin hfree hk).symm

/-! ## The `held` branch: several retry timers against the model's one bit

Where the chunk is held, `retry_offer` returns at its first line: the twin's state is as it was, and the fired
timer is gone. Which step of the model that is depends on the timers that remain:
- another retry timer of the chunk remains: the abstraction is as it was, a stutter;
- none remains, and no window of the chunk is open: the model's `retryNoop`;
- none remains, and a window of the chunk is open: not `retryNoop`. No theorem here says which step it is. -/

omit [Inhabited kind] [Inhabited ord] in
/-- Held, and another retry timer of the chunk remains: the abstraction is as it was. -/
theorem retryFire_held_same {n₀ : Peer} {bg : MState kind ord}
    {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = true)
    (hrest : retryArmedP { w with timers := w.timers.eraseIdx i } a.chunk = true) :
    alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w) = alpha kind ord n₀ a.chunk ctx ans bg w := by
  rw [retryFire_held hheld]
  have h0 := retryArmedP_of_rest hrest
  unfold alpha
  congr 1
  funext x
  by_cases hx : x = n₀ <;> simp [hx, hrest, h0]

/-- Held, the fired timer was the chunk's last retry timer, and no window of the chunk is open: the model's
`retryNoop n₀`. -/
theorem retryFire_held_last_retryNoop {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
    (hheld : heldP w.st a.chunk = true)
    (hlast : retryArmedP { w with timers := w.timers.eraseIdx i } a.chunk = false)
    (hclosed : windowP ctx w.st a.chunk = false) :
    NoStallEquiv.retryNoop.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ r
      (alpha kind ord n₀ a.chunk ctx ans bg w)
      (alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w)) := by
  rw [retryFire_held hheld]
  unfold NoStallEquiv.retryNoop.ext.tr
  simp only [getFrom, setIn]
  refine ⟨?_, ?_, Or.inl ?_, ?_⟩
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).retryArmed n₀ = true
    simp [alpha, retryArmedP_of_timer htimer]
  · show ¬ (alpha kind ord n₀ a.chunk ctx ans bg w).inWindow n₀ = true
    simp [alpha, hclosed]
  · show (alpha kind ord n₀ a.chunk ctx ans bg w).got n₀ = true
    simp [alpha, hheld]
  · unfold alpha
    congr 1
    funext x
    by_cases hx : x = n₀ <;>
      simp [Veil.FieldRepresentation.setSingle, Veil.CanonicalField.set, Veil.IteratedArrow.curry,
        Veil.IteratedArrow.uncurry, Veil.FieldUpdatePat.match, Veil.IteratedProd.patCmp, hx, hlast,
        @eq_comm _ n₀ x]

/-- **The control, with the window fixed open.** Held, the last retry timer, and a window of the chunk open: the
step is not the model's `retryNoop`, whose guard needs the window closed; and it is not a stutter, since the
abstraction's `retryArmed` falls. -/
theorem retryFire_held_last_open_not_retryNoop {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (htimer : w.timers[i]? = some (d, Timer.retryOffer a))
    (hheld : heldP w.st a.chunk = true)
    (hlast : retryArmedP { w with timers := w.timers.eraseIdx i } a.chunk = false)
    (hopen : windowP ctx w.st a.chunk = true) :
    ¬ NoStallEquiv.retryNoop.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
        (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ r
        (alpha kind ord n₀ a.chunk ctx ans bg w)
        (alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w)) ∧
      alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w) ≠ alpha kind ord n₀ a.chunk ctx ans bg w := by
  rw [retryFire_held hheld]
  constructor
  · intro h
    unfold NoStallEquiv.retryNoop.ext.tr at h
    simp only [getFrom, setIn] at h
    exact h.2.1 (by
      show (alpha kind ord n₀ a.chunk ctx ans bg w).inWindow n₀ = true
      simp [alpha, hopen])
  · intro h
    have h1 := congrFun (congrArg (·.retryArmed) h) n₀
    simp [alpha, hlast, retryArmedP_of_timer htimer] at h1

/-- `retryFire_held_last_retryNoop`, applied: the chunk held, one retry timer, the window closed. -/
theorem retryFire_held_last_applies (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) :
    NoStallEquiv.retryNoop.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ r
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg heldLast)
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (retryFire 0 kA ctx1 ans1 heldLast)) := by
  obtain ⟨hheld, hlast, hclosed⟩ := heldLast_facts
  exact retryFire_held_last_retryNoop kind ord (d := 0.205) rfl hheld hlast hclosed

/-! ## The statement's checks: it applied to worlds

The fixtures are `Refine/AskInterp.lean`'s. Each of these must elaborate as stated, and is then proved by the
theorem above, so that its hypotheses are shown to hold together. -/

open Classical in
/-- **Three announcers** (peer 1 parked, peer 2 with its ask still queued, peer 3 not asked yet) and a second
retry timer pending: the firing of the first is the model's `retryAsk n₀ 3 o1 false`, the first ask to peer 3. -/
theorem retryFire_refines_applies (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) :
    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 3 NoStallEquiv.ord_EnumClass.o1 false r
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg threeAnn)
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (retryFire 0 kA ctx1 ans1 threeAnn)) := by
  obtain ⟨hheld, hwin, hfree, hpick, hW⟩ := threeAnn_facts
  have h := retryFire_refines_retryAsk kind ord (n₀ := n₀) (bg := bg) (r := r) (i := 0) (d := 0.205) (a := kA)
    (ctx := ctx1) (ans := ans1) (w := threeAnn) rfl hheld threeAnn_stop rfl hwin hfree
    (by
      intro b _ hm
      simp [threeAnn, Std.HashMap.mem_insert] at hm
      exact hm.symm)
    (fun xs _ => List.Perm.refl xs) hW
  rw [hpick] at h
  exact h

open Classical in
/-- The control `retryFire_admitted_not_refused`, applied to that world: its step is no refused ask of the model. -/
theorem retryFire_admitted_not_refused_applies (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord)
    (q : Peer) (j : ord) :
    ¬ NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ q j true r
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg threeAnn)
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (retryFire 0 kA ctx1 ans1 threeAnn)) := by
  obtain ⟨hheld, hwin, hfree, _, _⟩ := threeAnn_facts
  exact retryFire_admitted_not_refused kind ord hheld threeAnn_stop rfl hwin hfree rfl q j

open Classical in
/-- The control `retryFire_refused_not_admitted`, applied to the same world with a queue that takes nothing: its
step is not the model's admitted ask of peer 3, under any number. -/
theorem retryFire_refused_not_admitted_applies (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) (j : ord) :
    ¬ NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 3 j false r
      (alpha kind ord n₀ kA.chunk ctx1 ansFull bg threeAnn)
      (alpha kind ord n₀ kA.chunk ctx1 ansFull bg (retryFire 0 kA ctx1 ansFull threeAnn)) := by
  obtain ⟨hheld, hwin, hfree, hpick, _⟩ := threeAnnFull_facts
  have h := retryFire_refused_not_admitted kind ord (n₀ := n₀) (bg := bg) (r := r) (i := 0) (a := kA) (ctx := ctx1)
    (ans := ansFull) (w := threeAnn) hheld threeAnn_stop rfl hwin hfree rfl j
  rw [hpick] at h
  exact h

open Classical in
/-- **A refusal:** the same world with a queue that takes nothing: `retryAsk n₀ 3 o1 true`. -/
theorem retryFire_refines_applies_refused (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) :
    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 3 NoStallEquiv.ord_EnumClass.o1 true r
      (alpha kind ord n₀ kA.chunk ctx1 ansFull bg threeAnn)
      (alpha kind ord n₀ kA.chunk ctx1 ansFull bg (retryFire 0 kA ctx1 ansFull threeAnn)) := by
  obtain ⟨hheld, hwin, hfree, hpick, hW⟩ := threeAnnFull_facts
  have h := retryFire_refines_retryAsk kind ord (n₀ := n₀) (bg := bg) (r := r) (i := 0) (d := 0.205) (a := kA)
    (ctx := ctx1) (ans := ansFull) (w := threeAnn) rfl hheld threeAnn_stop rfl hwin hfree
    (by
      intro b _ hm
      simp [threeAnn, Std.HashMap.mem_insert] at hm
      exact hm.symm)
    (fun xs _ => List.Perm.refl xs) hW
  rw [hpick] at h
  exact h

open Classical in
/-- **A fourth ask:** peer 3 was asked three times and is the least recently tried: `retryAsk n₀ 3 o4 false`. -/
theorem retryFire_refines_applies_fourth (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) :
    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 3 NoStallEquiv.ord_EnumClass.o4 false r
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (laterAsk 0.4))
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (retryFire 0 kA ctx1 ans1 (laterAsk 0.4))) := by
  obtain ⟨hheld, hwin, hfree, hpick, hW⟩ := laterAsk_fourth_facts
  have h := retryFire_refines_retryAsk kind ord (n₀ := n₀) (bg := bg) (r := r) (i := 0) (d := 0.205) (a := kA)
    (ctx := ctx1) (ans := ans1) (w := laterAsk 0.4) rfl hheld (laterAsk_stop _) rfl hwin hfree
    (by
      intro b _ hm
      simp [laterAsk, threeAnn, Std.HashMap.mem_insert] at hm
      exact hm.symm)
    (fun xs _ => List.Perm.refl xs) hW
  rw [hpick] at h
  exact h

open Classical in
/-- **A later ask:** peer 4 was asked five times and is the least recently tried: its sixth ask is `o4` again. -/
theorem retryFire_refines_applies_later (n₀ : Peer) (bg : MState kind ord) (r : MTheory kind ord) :
    NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord
      (NoStallEquiv.FieldAbstractType Peer kind ord) n₀ 4 NoStallEquiv.ord_EnumClass.o4 false r
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (laterAsk 0.2))
      (alpha kind ord n₀ kA.chunk ctx1 ans1 bg (retryFire 0 kA ctx1 ans1 (laterAsk 0.2))) := by
  obtain ⟨hheld, hwin, hfree, hpick, hW⟩ := laterAsk_later_facts
  have h := retryFire_refines_retryAsk kind ord (n₀ := n₀) (bg := bg) (r := r) (i := 0) (d := 0.205) (a := kA)
    (ctx := ctx1) (ans := ans1) (w := laterAsk 0.2) rfl hheld (laterAsk_stop _) rfl hwin hfree
    (by
      intro b _ hm
      simp [laterAsk, threeAnn, Std.HashMap.mem_insert] at hm
      exact hm.symm)
    (fun xs _ => List.Perm.refl xs) hW
  rw [hpick] at h
  exact h

end

end Refine.Ask
