import Carry.Run

/-! # The model's clauses and its `work`, read plainly at `Refine`'s representation

At `FieldAbstractType` every relation is a function to `Bool`, and Veil's reader of a field
(`Veil.FieldRepresentation.get`) is the identity on it, by computation. `Refine` uses that through `show`, atom by
atom. Here each of the 21 clauses of `Invariants`, and `work`, is written once in plain terms (`PlainInv`,
`WorkP`), after the model's text (`NoStallEquivModel.lean` 131–173, 524–574), and **Lean checks each against the
generated one by definitional equality** (`minv_of_plain`, `work_iff`): a plain clause that is not the generated
one does not type-check there. So nothing here is the model's on trust.

Then the generated safety clause is read at any state, and at a configuration's abstraction in the twin's terms
(`offers_resolve_twin`). That it holds along a run is `Carry/AfterAsk.lean`'s (`run_safety_twin`), which takes
nothing of the Veil model's. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- All seven of the model's switches are on: the generated `premises`, said field by field. -/
def AllOn (r : MTheory kind ord) : Prop :=
  r.lastResort = true ∧ r.owedAnswers = true ∧ r.askLedger = true ∧ r.heldBackRetry = true ∧
    r.rootTied = true ∧ r.noReask = true ∧ r.countsReset = true

local notation "askQ" => (NoStallEquiv.kind_EnumClass.askQ : kind)
local notation "askF" => (NoStallEquiv.kind_EnumClass.askF : kind)
local notation "ansQ" => (NoStallEquiv.kind_EnumClass.ansQ : kind)
local notation "ansOwed" => (NoStallEquiv.kind_EnumClass.ansOwed : kind)
local notation "ansF" => (NoStallEquiv.kind_EnumClass.ansF : kind)
local notation "o1" => (NoStallEquiv.ord_EnumClass.o1 : ord)
local notation "o2" => (NoStallEquiv.ord_EnumClass.o2 : ord)
local notation "o3" => (NoStallEquiv.ord_EnumClass.o3 : ord)

/-- The model's `pipeline n q j`: the j-th ask from n to q, or its answer, is on its way. -/
def PipelineP (s : MState kind ord) (n q : Peer) (j : ord) : Prop :=
  s.stage askQ n q j = true ∨ s.stage askF n q j = true ∨ s.stage ansQ q n j = true ∨
    s.stage ansOwed q n j = true ∨ s.stage ansF q n j = true

/-- The model's `outstanding n q`: an ask of the chunk from n to q is queued, or its promise open. -/
def OutstandingP (s : MState kind ord) (n q : Peer) : Prop :=
  (∃ J, s.stage askQ n q J = true) ∨ s.promise n q = true

/-- **The model's `work`, in plain terms:** its twelve enabling conditions, in the model's order (`writeAsk`,
`recvAsk`, `owedToQueue`, `writeAns`, `recvAns`, `windowElapse`, `retryNoop`, `retryAsk`, `retryParked`,
`lrNoop`, `lrAsk`, `promiseDue`). -/
def WorkP (r : MTheory kind ord) (s : MState kind ord) : Prop :=
  (∃ N Q J, s.stage askQ N Q J = true) ∨ (∃ Q N J, s.stage askF N Q J = true) ∨
  (∃ Q N J, s.stage ansOwed Q N J = true) ∨ (∃ Q N J, s.stage ansQ Q N J = true) ∨
  (∃ N Q J, s.stage ansF Q N J = true) ∨ (∃ N, s.inWindow N = true) ∨
  (∃ N, s.retryArmed N = true ∧ ¬ s.inWindow N = true ∧ (s.got N = true ∨ s.stop N = true)) ∨
  (∃ N Q, s.retryArmed N = true ∧ ¬ s.inWindow N = true ∧ ¬ s.got N = true ∧ ¬ s.stop N = true ∧
    s.offered N Q = true ∧ ¬ s.parked N Q = true ∧ ¬ s.tied N Q = true ∧
    ¬ (r.noReask = true ∧ OutstandingP kind ord s N Q)) ∨
  (∃ N, s.retryArmed N = true ∧ ¬ s.inWindow N = true ∧ ¬ s.got N = true ∧ ¬ s.stop N = true ∧
    ∀ Q, s.offered N Q = true → s.parked N Q = true ∨ s.tied N Q = true) ∨
  (∃ N, s.lrArmed N = true ∧ (s.got N = true ∨ s.stop N = true ∨ s.inWindow N = true ∨
    ∀ Q, s.offered N Q = true → s.tied N Q = true ∨ (s.parked N Q = true ∧ s.askedParked N Q = true))) ∨
  (∃ N Q, s.lrArmed N = true ∧ ¬ s.got N = true ∧ ¬ s.stop N = true ∧ ¬ s.inWindow N = true ∧
    s.offered N Q = true ∧ ¬ s.tied N Q = true ∧ ¬ (r.noReask = true ∧ OutstandingP kind ord s N Q) ∧
    (¬ s.parked N Q = true ∨
      ((∀ Q', s.offered N Q' = true → s.parked N Q' = true ∨ s.tied N Q' = true) ∧
        ¬ s.askedParked N Q = true))) ∨
  (∃ N Q, s.promise N Q = true)

/-- The generated `work` is the plain one, by definitional equality. -/
theorem work_iff (r : MTheory kind ord) (s : MState kind ord) : NoStallEquiv.work r s ↔ WorkP kind ord r s :=
  Iff.rfl

/-- **The 21 clauses of the model's `Invariants`, in plain terms,** in the model's order. `work` in the safety
clause stays the generated one. -/
structure PlainInv (r : MTheory kind ord) (s : MState kind ord) : Prop where
  offers_resolve : ∀ N Q, AllOn kind ord r → ¬ NoStallEquiv.work r s → s.installed N = true →
    s.offered N Q = true → s.got N = true ∨ s.stop N = true
  blocks : ∀ N Q, (s.installed N = true → s.gate N = true) ∧ (s.got N = true → s.installed N = true) ∧
    (s.stop N = true → s.installed N = true) ∧ (s.tied N Q = true → ¬ s.installed N = true)
  offer_holder : ∀ N Q, (s.offered N Q = true → s.got Q = true) ∧ (s.ledger N Q = true → s.got Q = true) ∧
    (s.tied N Q = true → s.got Q = true)
  ledger_before : ∀ N Q, s.ledger N Q = true → ¬ s.gate N = true
  ask_holder : ∀ N Q J, (s.stage askQ N Q J = true → s.got Q = true) ∧
    (s.stage askF N Q J = true → s.got Q = true) ∧ (s.stage ansQ Q N J = true → s.got Q = true) ∧
    (s.stage ansOwed Q N J = true → s.got Q = true) ∧ (s.stage ansF Q N J = true → s.got Q = true)
  claims_true : ∀ Q N, s.peerHas Q N = true → s.got N = true ∨ s.stop N = true
  window_retry : ∀ N, s.inWindow N = true → s.retryArmed N = true
  askedparked_offered : ∀ N Q, AllOn kind ord r → s.askedParked N Q = true → s.offered N Q = true
  askedparked_parked : ∀ N Q, s.askedParked N Q = true → s.parked N Q = true
  after_gate : ∀ N Q J, (s.offered N Q = true → s.gate N = true) ∧ (s.retryArmed N = true → s.gate N = true) ∧
    (s.lrArmed N = true → s.gate N = true) ∧ (s.promise N Q = true → s.gate N = true) ∧
    (s.made N Q J = true → s.gate N = true) ∧ (s.stage askQ N Q J = true → s.gate N = true) ∧
    (s.stage askF N Q J = true → s.gate N = true) ∧ (s.stage ansQ Q N J = true → s.gate N = true) ∧
    (s.stage ansOwed Q N J = true → s.gate N = true) ∧ (s.stage ansF Q N J = true → s.gate N = true)
  made_order : ∀ N Q, (s.made N Q o2 = true → s.made N Q o1 = true) ∧
    (s.made N Q o3 = true → s.made N Q o2 = true) ∧
    (s.made N Q NoStallEquiv.ord_EnumClass.o4 = true → s.made N Q o3 = true)
  stage_made : ∀ N Q J, (s.stage askQ N Q J = true → s.made N Q J = true) ∧
    (s.stage askF N Q J = true → s.made N Q J = true) ∧ (s.stage ansQ Q N J = true → s.made N Q J = true) ∧
    (s.stage ansOwed Q N J = true → s.made N Q J = true) ∧ (s.stage ansF Q N J = true → s.made N Q J = true)
  asked_offered : ∀ N Q J, AllOn kind ord r →
    (s.stage askQ N Q J = true → s.offered N Q = true ∨ s.got N = true) ∧
    (s.promise N Q = true → s.offered N Q = true ∨ s.got N = true)
  first_ask : ∀ N Q, AllOn kind ord r → ¬ s.installed N = true → s.made N Q o1 = true →
    (∃ J, s.stage askQ N Q J = true) ∨ s.promise N Q = true ∨ s.parked N Q = true ∨ s.tied N Q = true ∨
      s.got N = true ∨ s.stop N = true
  second_ask : ∀ N Q, AllOn kind ord r → ¬ s.installed N = true → s.made N Q o2 = true →
    s.askedParked N Q = true ∨ s.tied N Q = true
  two_before : ∀ N Q, AllOn kind ord r → ¬ s.installed N = true → ¬ s.made N Q o3 = true
  third_answered : ∀ N Q, AllOn kind ord r → s.made N Q o3 = true →
    PipelineP kind ord s N Q o3 ∨ s.got N = true ∨ s.stop N = true ∨ s.peerHas Q N = true
  unparked_retry : ∀ N Q, AllOn kind ord r → s.offered N Q = true → ¬ s.parked N Q = true →
    ¬ s.tied N Q = true → s.got N = true ∨ s.stop N = true ∨ s.retryArmed N = true
  parked_timer : ∀ N Q, AllOn kind ord r → s.offered N Q = true → s.parked N Q = true →
    ¬ s.tied N Q = true → ¬ s.askedParked N Q = true →
    s.got N = true ∨ s.stop N = true ∨ s.retryArmed N = true ∨ s.lrArmed N = true
  offer_active : ∀ N M, AllOn kind ord r → s.installed N = true → s.offered N M = true →
    s.got N = true ∨ s.stop N = true ∨ s.retryArmed N = true ∨ s.lrArmed N = true ∨
      (∃ Q J, PipelineP kind ord s N Q J) ∨
      (∀ Q, s.offered N Q = true → s.parked N Q = true ∧ s.askedParked N Q = true)
  asked_parked : ∀ N Q, AllOn kind ord r → s.askedParked N Q = true →
    s.got N = true ∨ s.stop N = true ∨ s.tied N Q = true ∨ s.peerHas Q N = true ∨
      (∃ J, PipelineP kind ord s N Q J)

/-- **The plain clauses give the generated `Invariants`:** each field is its generated clause, by definitional
equality. -/
theorem minv_of_plain {r : MTheory kind ord} {s : MState kind ord} (h : PlainInv kind ord r s) :
    MInv kind ord r s :=
  ⟨h.offers_resolve, h.blocks, h.offer_holder, h.ledger_before, h.ask_holder, h.claims_true, h.window_retry,
    h.askedparked_offered, h.askedparked_parked, h.after_gate, h.made_order, h.stage_made, h.asked_offered,
    h.first_ask, h.second_ask, h.two_before, h.third_answered, h.unparked_retry, h.parked_timer,
    h.offer_active, h.asked_parked⟩

/-- **And back:** the generated `Invariants` give the plain clauses. -/
theorem plain_of_minv {r : MTheory kind ord} {s : MState kind ord} (h : MInv kind ord r s) :
    PlainInv kind ord r s :=
  ⟨h.1, h.2.1, h.2.2.1, h.2.2.2.1, h.2.2.2.2.1, h.2.2.2.2.2.1, h.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.1,
    h.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.2.1,
    h.2.2.2.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.1,
    h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.1,
    h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.1,
    h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.1, h.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2⟩

/-- **The generated safety clause, read:** with the switches on and no `work`, a node with the builder's block
and an offer holds the chunk or has stopped its pull. `work` stays the model's own, as generated. -/
theorem offers_resolve_gives {r : MTheory kind ord} {s : MState kind ord}
    (h : NoStallEquiv.offers_resolve r s) (hon : AllOn kind ord r)
    (hquiet : ¬ NoStallEquiv.work r s) {N Q : Peer} (hinst : s.installed N = true)
    (hoff : s.offered N Q = true) : s.got N = true ∨ s.stop N = true :=
  h N Q hon hquiet hinst hoff

/-- **The model's safety clause of a configuration's abstraction, read in the twin's terms at `n₀`:** with the
switches on and the abstraction without `work`, if the builder's block is installed (`installed_block(sl, rt)`)
and `q` is an announcer of the chunk, the chunk is held or the pull of its group is stopped. -/
theorem offers_resolve_twin {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord}
    {c : Cfg kind ord} (h : NoStallEquiv.offers_resolve r (abs kind ord n₀ k sl rt c))
    (hon : AllOn kind ord r) (hquiet : ¬ NoStallEquiv.work r (abs kind ord n₀ k sl rt c))
    (hinst : (c.ans.installedBlock sl rt).isSome = true) {q : Peer} (hoff : offeredP c.ans c.w.st k q = true) :
    heldP c.w.st k = true ∨ stopP c.w.st k.1 = true := by
  have h' := offers_resolve_gives kind ord h hon hquiet
    (N := n₀) (Q := q) (by simp [abs, alpha, withBlocks, hinst]) (by simp [abs, alpha, hoff])
  simpa [abs, alpha] using h'

/-- **The carried invariant, clause by clause in plain terms:** along a run from a configuration whose
abstraction satisfies the model's `Invariants`, the 21 plain clauses hold of the abstraction of the configuration
reached. The Veil model's statements for `retryAsk` and `retryNoop` are hypotheses. -/
theorem carried_plain (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c₀ c : Cfg kind ord}
    (hrun : Run kind ord n₀ k sl rt r c₀ c) (h0 : MInv kind ord r (abs kind ord n₀ k sl rt c₀)) :
    PlainInv kind ord r (abs kind ord n₀ k sl rt c) :=
  plain_of_minv kind ord (carried kind ord hA hN hrun h0)

end

end Refine.Carry
