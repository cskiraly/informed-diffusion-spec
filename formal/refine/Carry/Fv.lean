import NoStallEquivModel
import Refine.RetryAsk
import Carry.Bridge

/-! # The Veil model's statements as hypotheses, and what the bridge makes of them

The model here is the cut one (`NoStallEquivModel.lean`: `formal/veil`'s `NoStallEquiv.lean` to its
`#gen_spec`), which has the clauses, `Invariants`, `Init`, the actions and their generated transitions, and no
`<action>_<clause>` theorem: those come from `#gen_theorems`, after the 704 conditions are checked (the build of
`formal/veil`, about 25 minutes under 20 GB). So each statement this file takes from the Veil model is a **named
hypothesis**, written as `#gen_theorems` states it (Veil's `VCGen/Induction.lean` 172–184; the form is seen on
`Carry/BridgeToy.lean`), at `Refine`'s types: the twin's peers as nodes, every relation a function to `Bool`.
Each is kept closed in `Meets` (`Carry/Bridge.lean`), a structure whose one field is that form: a generated
theorem gives it by `⟨·⟩`.

Five structures, 21 fields each, one per clause of `Invariants` in its order: for `retryAsk`, `retryNoop`,
`promiseDue`, `parkOther` and the initializer. With them the bridge gives: `retryAsk.ext.tr`, `retryNoop.ext.tr`,
`promiseDue.ext.tr` and `parkOther.ext.tr` preserve `Invariants`, and `Init` gives it. Nothing of the model is
written again here. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- The model's representation at `Refine`'s types: every relation a function to `Bool`, over the twin's peers. -/
abbrev MChi := NoStallEquiv.FieldAbstractType Peer kind ord

/-- The model's `Invariants`, as generated, at `Refine`'s types: the safety clause and the 20 invariants. -/
abbrev MInv : MTheory kind ord → MState kind ord → Prop :=
  NoStallEquiv.Invariants (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)

/-- The model's `Assumptions`, as generated, at `Refine`'s types (it is `True`: the model has no assumption). -/
abbrev MAssu : MTheory kind ord → Prop :=
  NoStallEquiv.Assumptions (MTheory kind ord) Peer kind ord

/-- A clause of the model, as generated, at `Refine`'s types. -/
local notation "CL(" c ")" =>
  (fun (rd : MTheory kind ord) (st : MState kind ord) =>
    c (ρ := MTheory kind ord) (σ := MState kind ord) (node := Peer) (kind := kind) (ord := ord)
      (χ := MChi kind ord) rd st)

open Classical in
/-- The Veil model's statement for `retryAsk` and a clause, as `#gen_theorems` states it: from `Assumptions` and
`Invariants`, the action, if it succeeds, leaves the clause. -/
abbrev RetryAskMeets (cl : MTheory kind ord → MState kind ord → Prop) : Prop :=
  ∀ (n q : Peer) (j : ord) (full : Bool),
    Meets (NoStallEquiv.retryAsk.ext (ρ := MTheory kind ord) (σ := MState kind ord) (χ := MChi kind ord)
      n q j full) (MAssu kind ord) (MInv kind ord) cl

/-- The Veil model's statement for `retryNoop` and a clause. -/
abbrev RetryNoopMeets (cl : MTheory kind ord → MState kind ord → Prop) : Prop :=
  ∀ (n : Peer),
    Meets (NoStallEquiv.retryNoop.ext (ρ := MTheory kind ord) (σ := MState kind ord) (χ := MChi kind ord)
      n) (MAssu kind ord) (MInv kind ord) cl

/-- The Veil model's statement for `promiseDue` and a clause. -/
abbrev PromiseDueMeets (cl : MTheory kind ord → MState kind ord → Prop) : Prop :=
  ∀ (n q : Peer),
    Meets (NoStallEquiv.promiseDue.ext (ρ := MTheory kind ord) (σ := MState kind ord) (χ := MChi kind ord)
      n q) (MAssu kind ord) (MInv kind ord) cl

/-- The Veil model's statement for `parkOther` and a clause. -/
abbrev ParkOtherMeets (cl : MTheory kind ord → MState kind ord → Prop) : Prop :=
  ∀ (n q : Peer),
    Meets (NoStallEquiv.parkOther.ext (ρ := MTheory kind ord) (σ := MState kind ord) (χ := MChi kind ord)
      n q) (MAssu kind ord) (MInv kind ord) cl

/-- The Veil model's statement for the initializer and a clause: no invariant is assumed before it. -/
abbrev InitMeets (cl : MTheory kind ord → MState kind ord → Prop) : Prop :=
  Meets (NoStallEquiv.initializer.ext (ρ := MTheory kind ord) (σ := MState kind ord) (χ := MChi kind ord))
    (MAssu kind ord) (fun _ _ => True) cl

/-- **The Veil model's 21 statements for `retryAsk`,** as hypotheses: `NoStallEquiv.retryAsk_<clause>`, at
`Refine`'s types. -/
structure FvRetryAsk : Prop where
  offers_resolve : RetryAskMeets kind ord CL(NoStallEquiv.offers_resolve)
  blocks : RetryAskMeets kind ord CL(NoStallEquiv.blocks)
  offer_holder : RetryAskMeets kind ord CL(NoStallEquiv.offer_holder)
  ledger_before : RetryAskMeets kind ord CL(NoStallEquiv.ledger_before)
  ask_holder : RetryAskMeets kind ord CL(NoStallEquiv.ask_holder)
  claims_true : RetryAskMeets kind ord CL(NoStallEquiv.claims_true)
  window_retry : RetryAskMeets kind ord CL(NoStallEquiv.window_retry)
  askedparked_offered : RetryAskMeets kind ord CL(NoStallEquiv.askedparked_offered)
  askedparked_parked : RetryAskMeets kind ord CL(NoStallEquiv.askedparked_parked)
  after_gate : RetryAskMeets kind ord CL(NoStallEquiv.after_gate)
  made_order : RetryAskMeets kind ord CL(NoStallEquiv.made_order)
  stage_made : RetryAskMeets kind ord CL(NoStallEquiv.stage_made)
  asked_offered : RetryAskMeets kind ord CL(NoStallEquiv.asked_offered)
  first_ask : RetryAskMeets kind ord CL(NoStallEquiv.first_ask)
  second_ask : RetryAskMeets kind ord CL(NoStallEquiv.second_ask)
  two_before : RetryAskMeets kind ord CL(NoStallEquiv.two_before)
  third_answered : RetryAskMeets kind ord CL(NoStallEquiv.third_answered)
  unparked_retry : RetryAskMeets kind ord CL(NoStallEquiv.unparked_retry)
  parked_timer : RetryAskMeets kind ord CL(NoStallEquiv.parked_timer)
  offer_active : RetryAskMeets kind ord CL(NoStallEquiv.offer_active)
  asked_parked : RetryAskMeets kind ord CL(NoStallEquiv.asked_parked)

/-- **The Veil model's 21 statements for `retryNoop`,** as hypotheses: `NoStallEquiv.retryNoop_<clause>`. -/
structure FvRetryNoop : Prop where
  offers_resolve : RetryNoopMeets kind ord CL(NoStallEquiv.offers_resolve)
  blocks : RetryNoopMeets kind ord CL(NoStallEquiv.blocks)
  offer_holder : RetryNoopMeets kind ord CL(NoStallEquiv.offer_holder)
  ledger_before : RetryNoopMeets kind ord CL(NoStallEquiv.ledger_before)
  ask_holder : RetryNoopMeets kind ord CL(NoStallEquiv.ask_holder)
  claims_true : RetryNoopMeets kind ord CL(NoStallEquiv.claims_true)
  window_retry : RetryNoopMeets kind ord CL(NoStallEquiv.window_retry)
  askedparked_offered : RetryNoopMeets kind ord CL(NoStallEquiv.askedparked_offered)
  askedparked_parked : RetryNoopMeets kind ord CL(NoStallEquiv.askedparked_parked)
  after_gate : RetryNoopMeets kind ord CL(NoStallEquiv.after_gate)
  made_order : RetryNoopMeets kind ord CL(NoStallEquiv.made_order)
  stage_made : RetryNoopMeets kind ord CL(NoStallEquiv.stage_made)
  asked_offered : RetryNoopMeets kind ord CL(NoStallEquiv.asked_offered)
  first_ask : RetryNoopMeets kind ord CL(NoStallEquiv.first_ask)
  second_ask : RetryNoopMeets kind ord CL(NoStallEquiv.second_ask)
  two_before : RetryNoopMeets kind ord CL(NoStallEquiv.two_before)
  third_answered : RetryNoopMeets kind ord CL(NoStallEquiv.third_answered)
  unparked_retry : RetryNoopMeets kind ord CL(NoStallEquiv.unparked_retry)
  parked_timer : RetryNoopMeets kind ord CL(NoStallEquiv.parked_timer)
  offer_active : RetryNoopMeets kind ord CL(NoStallEquiv.offer_active)
  asked_parked : RetryNoopMeets kind ord CL(NoStallEquiv.asked_parked)

/-- **The Veil model's 21 statements for `promiseDue`,** as hypotheses: `NoStallEquiv.promiseDue_<clause>`. -/
structure FvPromiseDue : Prop where
  offers_resolve : PromiseDueMeets kind ord CL(NoStallEquiv.offers_resolve)
  blocks : PromiseDueMeets kind ord CL(NoStallEquiv.blocks)
  offer_holder : PromiseDueMeets kind ord CL(NoStallEquiv.offer_holder)
  ledger_before : PromiseDueMeets kind ord CL(NoStallEquiv.ledger_before)
  ask_holder : PromiseDueMeets kind ord CL(NoStallEquiv.ask_holder)
  claims_true : PromiseDueMeets kind ord CL(NoStallEquiv.claims_true)
  window_retry : PromiseDueMeets kind ord CL(NoStallEquiv.window_retry)
  askedparked_offered : PromiseDueMeets kind ord CL(NoStallEquiv.askedparked_offered)
  askedparked_parked : PromiseDueMeets kind ord CL(NoStallEquiv.askedparked_parked)
  after_gate : PromiseDueMeets kind ord CL(NoStallEquiv.after_gate)
  made_order : PromiseDueMeets kind ord CL(NoStallEquiv.made_order)
  stage_made : PromiseDueMeets kind ord CL(NoStallEquiv.stage_made)
  asked_offered : PromiseDueMeets kind ord CL(NoStallEquiv.asked_offered)
  first_ask : PromiseDueMeets kind ord CL(NoStallEquiv.first_ask)
  second_ask : PromiseDueMeets kind ord CL(NoStallEquiv.second_ask)
  two_before : PromiseDueMeets kind ord CL(NoStallEquiv.two_before)
  third_answered : PromiseDueMeets kind ord CL(NoStallEquiv.third_answered)
  unparked_retry : PromiseDueMeets kind ord CL(NoStallEquiv.unparked_retry)
  parked_timer : PromiseDueMeets kind ord CL(NoStallEquiv.parked_timer)
  offer_active : PromiseDueMeets kind ord CL(NoStallEquiv.offer_active)
  asked_parked : PromiseDueMeets kind ord CL(NoStallEquiv.asked_parked)

/-- **The Veil model's 21 statements for `parkOther`,** as hypotheses: `NoStallEquiv.parkOther_<clause>`. -/
structure FvParkOther : Prop where
  offers_resolve : ParkOtherMeets kind ord CL(NoStallEquiv.offers_resolve)
  blocks : ParkOtherMeets kind ord CL(NoStallEquiv.blocks)
  offer_holder : ParkOtherMeets kind ord CL(NoStallEquiv.offer_holder)
  ledger_before : ParkOtherMeets kind ord CL(NoStallEquiv.ledger_before)
  ask_holder : ParkOtherMeets kind ord CL(NoStallEquiv.ask_holder)
  claims_true : ParkOtherMeets kind ord CL(NoStallEquiv.claims_true)
  window_retry : ParkOtherMeets kind ord CL(NoStallEquiv.window_retry)
  askedparked_offered : ParkOtherMeets kind ord CL(NoStallEquiv.askedparked_offered)
  askedparked_parked : ParkOtherMeets kind ord CL(NoStallEquiv.askedparked_parked)
  after_gate : ParkOtherMeets kind ord CL(NoStallEquiv.after_gate)
  made_order : ParkOtherMeets kind ord CL(NoStallEquiv.made_order)
  stage_made : ParkOtherMeets kind ord CL(NoStallEquiv.stage_made)
  asked_offered : ParkOtherMeets kind ord CL(NoStallEquiv.asked_offered)
  first_ask : ParkOtherMeets kind ord CL(NoStallEquiv.first_ask)
  second_ask : ParkOtherMeets kind ord CL(NoStallEquiv.second_ask)
  two_before : ParkOtherMeets kind ord CL(NoStallEquiv.two_before)
  third_answered : ParkOtherMeets kind ord CL(NoStallEquiv.third_answered)
  unparked_retry : ParkOtherMeets kind ord CL(NoStallEquiv.unparked_retry)
  parked_timer : ParkOtherMeets kind ord CL(NoStallEquiv.parked_timer)
  offer_active : ParkOtherMeets kind ord CL(NoStallEquiv.offer_active)
  asked_parked : ParkOtherMeets kind ord CL(NoStallEquiv.asked_parked)

/-- **The Veil model's 21 statements for the initializer,** as hypotheses: `NoStallEquiv.initializer_<clause>`. -/
structure FvInit : Prop where
  offers_resolve : InitMeets kind ord CL(NoStallEquiv.offers_resolve)
  blocks : InitMeets kind ord CL(NoStallEquiv.blocks)
  offer_holder : InitMeets kind ord CL(NoStallEquiv.offer_holder)
  ledger_before : InitMeets kind ord CL(NoStallEquiv.ledger_before)
  ask_holder : InitMeets kind ord CL(NoStallEquiv.ask_holder)
  claims_true : InitMeets kind ord CL(NoStallEquiv.claims_true)
  window_retry : InitMeets kind ord CL(NoStallEquiv.window_retry)
  askedparked_offered : InitMeets kind ord CL(NoStallEquiv.askedparked_offered)
  askedparked_parked : InitMeets kind ord CL(NoStallEquiv.askedparked_parked)
  after_gate : InitMeets kind ord CL(NoStallEquiv.after_gate)
  made_order : InitMeets kind ord CL(NoStallEquiv.made_order)
  stage_made : InitMeets kind ord CL(NoStallEquiv.stage_made)
  asked_offered : InitMeets kind ord CL(NoStallEquiv.asked_offered)
  first_ask : InitMeets kind ord CL(NoStallEquiv.first_ask)
  second_ask : InitMeets kind ord CL(NoStallEquiv.second_ask)
  two_before : InitMeets kind ord CL(NoStallEquiv.two_before)
  third_answered : InitMeets kind ord CL(NoStallEquiv.third_answered)
  unparked_retry : InitMeets kind ord CL(NoStallEquiv.unparked_retry)
  parked_timer : InitMeets kind ord CL(NoStallEquiv.parked_timer)
  offer_active : InitMeets kind ord CL(NoStallEquiv.offer_active)
  asked_parked : InitMeets kind ord CL(NoStallEquiv.asked_parked)

open Classical in
/-- **`retryAsk`'s generated transition preserves `Invariants`,** given the Veil model's statements for it: each
clause by the bridge, from the action's `ext.derived_eq`. -/
theorem retryAsk_preserves (h : FvRetryAsk kind ord) {n q : Peer} {j : ord} {full : Bool}
    {r : MTheory kind ord} {s s' : MState kind ord} (hinv : MInv kind ord r s)
    (htr : NoStallEquiv.retryAsk.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      n q j full r s s') :
    MInv kind ord r s' :=
  have hder := NoStallEquiv.retryAsk.ext.derived_eq (MTheory kind ord) (MState kind ord) Peer kind ord
    (MChi kind ord) n q j full
  ⟨(h.offers_resolve n q j full).bridge hder trivial hinv htr,
    (h.blocks n q j full).bridge hder trivial hinv htr, (h.offer_holder n q j full).bridge hder trivial hinv htr,
    (h.ledger_before n q j full).bridge hder trivial hinv htr,
    (h.ask_holder n q j full).bridge hder trivial hinv htr,
    (h.claims_true n q j full).bridge hder trivial hinv htr,
    (h.window_retry n q j full).bridge hder trivial hinv htr,
    (h.askedparked_offered n q j full).bridge hder trivial hinv htr,
    (h.askedparked_parked n q j full).bridge hder trivial hinv htr,
    (h.after_gate n q j full).bridge hder trivial hinv htr,
    (h.made_order n q j full).bridge hder trivial hinv htr,
    (h.stage_made n q j full).bridge hder trivial hinv htr,
    (h.asked_offered n q j full).bridge hder trivial hinv htr,
    (h.first_ask n q j full).bridge hder trivial hinv htr,
    (h.second_ask n q j full).bridge hder trivial hinv htr,
    (h.two_before n q j full).bridge hder trivial hinv htr,
    (h.third_answered n q j full).bridge hder trivial hinv htr,
    (h.unparked_retry n q j full).bridge hder trivial hinv htr,
    (h.parked_timer n q j full).bridge hder trivial hinv htr,
    (h.offer_active n q j full).bridge hder trivial hinv htr,
    (h.asked_parked n q j full).bridge hder trivial hinv htr⟩

/-- **`retryNoop`'s generated transition preserves `Invariants`,** given the Veil model's statements for it. -/
theorem retryNoop_preserves (h : FvRetryNoop kind ord) {n : Peer}
    {r : MTheory kind ord} {s s' : MState kind ord} (hinv : MInv kind ord r s)
    (htr : NoStallEquiv.retryNoop.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      n r s s') :
    MInv kind ord r s' :=
  have hder := NoStallEquiv.retryNoop.ext.derived_eq (MTheory kind ord) (MState kind ord) Peer kind ord
    (MChi kind ord) n
  ⟨(h.offers_resolve n).bridge hder trivial hinv htr, (h.blocks n).bridge hder trivial hinv htr,
    (h.offer_holder n).bridge hder trivial hinv htr, (h.ledger_before n).bridge hder trivial hinv htr,
    (h.ask_holder n).bridge hder trivial hinv htr, (h.claims_true n).bridge hder trivial hinv htr,
    (h.window_retry n).bridge hder trivial hinv htr, (h.askedparked_offered n).bridge hder trivial hinv htr,
    (h.askedparked_parked n).bridge hder trivial hinv htr, (h.after_gate n).bridge hder trivial hinv htr,
    (h.made_order n).bridge hder trivial hinv htr, (h.stage_made n).bridge hder trivial hinv htr,
    (h.asked_offered n).bridge hder trivial hinv htr, (h.first_ask n).bridge hder trivial hinv htr,
    (h.second_ask n).bridge hder trivial hinv htr, (h.two_before n).bridge hder trivial hinv htr,
    (h.third_answered n).bridge hder trivial hinv htr, (h.unparked_retry n).bridge hder trivial hinv htr,
    (h.parked_timer n).bridge hder trivial hinv htr, (h.offer_active n).bridge hder trivial hinv htr,
    (h.asked_parked n).bridge hder trivial hinv htr⟩

/-- **`promiseDue`'s generated transition preserves `Invariants`,** given the Veil model's statements for it. -/
theorem promiseDue_preserves (h : FvPromiseDue kind ord) {n q : Peer}
    {r : MTheory kind ord} {s s' : MState kind ord} (hinv : MInv kind ord r s)
    (htr : NoStallEquiv.promiseDue.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      n q r s s') :
    MInv kind ord r s' :=
  have hder := NoStallEquiv.promiseDue.ext.derived_eq (MTheory kind ord) (MState kind ord) Peer kind ord
    (MChi kind ord) n q
  ⟨(h.offers_resolve n q).bridge hder trivial hinv htr, (h.blocks n q).bridge hder trivial hinv htr,
    (h.offer_holder n q).bridge hder trivial hinv htr, (h.ledger_before n q).bridge hder trivial hinv htr,
    (h.ask_holder n q).bridge hder trivial hinv htr, (h.claims_true n q).bridge hder trivial hinv htr,
    (h.window_retry n q).bridge hder trivial hinv htr, (h.askedparked_offered n q).bridge hder trivial hinv htr,
    (h.askedparked_parked n q).bridge hder trivial hinv htr, (h.after_gate n q).bridge hder trivial hinv htr,
    (h.made_order n q).bridge hder trivial hinv htr, (h.stage_made n q).bridge hder trivial hinv htr,
    (h.asked_offered n q).bridge hder trivial hinv htr, (h.first_ask n q).bridge hder trivial hinv htr,
    (h.second_ask n q).bridge hder trivial hinv htr, (h.two_before n q).bridge hder trivial hinv htr,
    (h.third_answered n q).bridge hder trivial hinv htr, (h.unparked_retry n q).bridge hder trivial hinv htr,
    (h.parked_timer n q).bridge hder trivial hinv htr, (h.offer_active n q).bridge hder trivial hinv htr,
    (h.asked_parked n q).bridge hder trivial hinv htr⟩

/-- **`parkOther`'s generated transition preserves `Invariants`,** given the Veil model's statements for it. -/
theorem parkOther_preserves (h : FvParkOther kind ord) {n q : Peer}
    {r : MTheory kind ord} {s s' : MState kind ord} (hinv : MInv kind ord r s)
    (htr : NoStallEquiv.parkOther.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      n q r s s') :
    MInv kind ord r s' :=
  have hder := NoStallEquiv.parkOther.ext.derived_eq (MTheory kind ord) (MState kind ord) Peer kind ord
    (MChi kind ord) n q
  ⟨(h.offers_resolve n q).bridge hder trivial hinv htr, (h.blocks n q).bridge hder trivial hinv htr,
    (h.offer_holder n q).bridge hder trivial hinv htr, (h.ledger_before n q).bridge hder trivial hinv htr,
    (h.ask_holder n q).bridge hder trivial hinv htr, (h.claims_true n q).bridge hder trivial hinv htr,
    (h.window_retry n q).bridge hder trivial hinv htr, (h.askedparked_offered n q).bridge hder trivial hinv htr,
    (h.askedparked_parked n q).bridge hder trivial hinv htr, (h.after_gate n q).bridge hder trivial hinv htr,
    (h.made_order n q).bridge hder trivial hinv htr, (h.stage_made n q).bridge hder trivial hinv htr,
    (h.asked_offered n q).bridge hder trivial hinv htr, (h.first_ask n q).bridge hder trivial hinv htr,
    (h.second_ask n q).bridge hder trivial hinv htr, (h.two_before n q).bridge hder trivial hinv htr,
    (h.third_answered n q).bridge hder trivial hinv htr, (h.unparked_retry n q).bridge hder trivial hinv htr,
    (h.parked_timer n q).bridge hder trivial hinv htr, (h.offer_active n q).bridge hder trivial hinv htr,
    (h.asked_parked n q).bridge hder trivial hinv htr⟩

/-- **The model's `Init` gives `Invariants`,** given the Veil model's statements for the initializer. -/
theorem init_invariants (h : FvInit kind ord) {r : MTheory kind ord} {s : MState kind ord}
    (hinit : NoStallEquiv.Init (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) r s) :
    MInv kind ord r s :=
  -- `Init` is the initializer's generated transition from the default state
  have htr : NoStallEquiv.initializer.ext.tr (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord)
      r default s := hinit
  have hder := NoStallEquiv.initializer.ext.derived_eq (MTheory kind ord) (MState kind ord) Peer kind ord
    (MChi kind ord)
  ⟨h.offers_resolve.bridge hder trivial trivial htr, h.blocks.bridge hder trivial trivial htr,
    h.offer_holder.bridge hder trivial trivial htr, h.ledger_before.bridge hder trivial trivial htr,
    h.ask_holder.bridge hder trivial trivial htr, h.claims_true.bridge hder trivial trivial htr,
    h.window_retry.bridge hder trivial trivial htr, h.askedparked_offered.bridge hder trivial trivial htr,
    h.askedparked_parked.bridge hder trivial trivial htr, h.after_gate.bridge hder trivial trivial htr,
    h.made_order.bridge hder trivial trivial htr, h.stage_made.bridge hder trivial trivial htr,
    h.asked_offered.bridge hder trivial trivial htr, h.first_ask.bridge hder trivial trivial htr,
    h.second_ask.bridge hder trivial trivial htr, h.two_before.bridge hder trivial trivial htr,
    h.third_answered.bridge hder trivial trivial htr, h.unparked_retry.bridge hder trivial trivial htr,
    h.parked_timer.bridge hder trivial trivial htr, h.offer_active.bridge hder trivial trivial htr,
    h.asked_parked.bridge hder trivial trivial htr⟩

end

end Refine.Carry
