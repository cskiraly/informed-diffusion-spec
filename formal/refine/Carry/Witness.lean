import Carry.Idle
import Carry.AfterAsk

/-! # The witness, the negative control, the `held` branch's open case, and `Init`

- **The witness:** a run of one covered step that is not a stutter (the model's `retryNoop`), from a configuration
  whose abstraction satisfies the model's `Invariants` with all seven switches on, to one where the safety
  clause's antecedent holds: no `work`, the builder's block installed, an offer. The carried theorem applies.
- **The negative control:** the twin's `expired` branch at the last firing leaves the model's `stalled`: the
  safety clause is false. With the Veil model's statements, that firing is no step of a run. With the group not
  expired the same firing is a covered step.
- **The `held` branch's open case:** the clause `window_retry` is false after it.
- **`Init`:** the abstraction of the empty world over a background with every relation false is the model's
  `Init`. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- The model's constants with all seven switches on. -/
def rOn : MTheory kind ord :=
  { lastResort := true, owedAnswers := true, askLedger := true, heldBackRetry := true, rootTied := true,
    noReask := true, countsReset := true }

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
theorem rOn_allOn : AllOn kind ord (rOn kind ord) := ⟨rfl, rfl, rfl, rfl, rfl, rfl, rfl⟩

/-- **From a configuration where `Invariants` hold, a change to one where they do not is no step of a run,**
given the Veil model's statements: not a covered step, not one that leaves the abstraction as it was, and not
one under the named hypothesis. -/
theorem not_step_of_not_inv (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord)
    {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {r : MTheory kind ord} {c c' : Cfg kind ord}
    (hinv : MInv kind ord r (abs kind ord n₀ k sl rt c))
    (hbad : ¬ MInv kind ord r (abs kind ord n₀ k sl rt c')) : ¬ Step kind ord n₀ k sl rt r c c' :=
  fun h => hbad (step_preserves kind ord hA hN h hinv)

/-! ## The witness -/

/-- The witness's start: the node holds the chunk, peer 1 offered it, one retry timer is armed, nothing else is in
flight; the builder's block (slot 0, root `"r"`) is installed; every other node is a holder. -/
def cWitness : Cfg kind ord := ⟨quietHeld, ctx1, ansBlock, bgHolders kind ord⟩

/-- The witness's end: the timer has fired. -/
def cWitnessAfter : Cfg kind ord := ⟨retryFire 0 kA ctx1 ansBlock quietHeld, ctx1, ansBlock, bgHolders kind ord⟩

/-- The model's `Invariants` hold of the abstraction of the witness's start, all seven switches on. -/
theorem witness_start :
    MInv kind ord (rOn kind ord) (abs kind ord n0 kA.chunk 0 "r" (cWitness kind ord)) := by
  unfold cWitness
  rw [abs_idle kind ord quietHeld_idle rfl rfl, quietHeld_facts.2.1]
  exact idleState_invariants kind ord _ n0 _ _ _ quietHeld_facts.2.2.2.2.1

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- The firing is a covered step: the `held` branch at the chunk's last retry timer, no window open. -/
theorem witness_step : Covered kind ord n0 kA.chunk (cWitness kind ord) (cWitnessAfter kind ord) :=
  Covered.heldLast (d := 0.205) rfl rfl quietHeld_facts.1 quietHeld_facts.2.2.1 quietHeld_idle.window

omit [Inhabited kind] [Inhabited ord] in
/-- The abstraction after the firing: the idle state with the chunk held and no timer armed. -/
theorem witness_after_abs :
    abs kind ord n0 kA.chunk 0 "r" (cWitnessAfter kind ord) =
      idleState kind ord n0 true false false (offeredP ansBlock quietHeld.st kA.chunk) := by
  unfold cWitnessAfter
  rw [retryFire_held quietHeld_facts.1, abs_idle kind ord (quietHeld_idle.eraseTimer 0) rfl rfl,
    quietHeld_facts.2.2.1]
  show idleState kind ord n0 (heldP quietHeld.st kA.chunk) (stopP quietHeld.st kA.group) false _ = _
  rw [quietHeld_facts.1, quietHeld_stop]

omit [Inhabited kind] [Inhabited ord] in
/-- **The step is not a stutter:** the abstraction's `retryArmed n₀` falls. -/
theorem witness_not_stutter :
    abs kind ord n0 kA.chunk 0 "r" (cWitnessAfter kind ord) ≠ abs kind ord n0 kA.chunk 0 "r" (cWitness kind ord) := by
  rw [witness_after_abs]
  unfold cWitness
  rw [abs_idle kind ord quietHeld_idle rfl rfl, quietHeld_facts.2.1]
  intro h
  have h1 := congrFun (congrArg (·.retryArmed) h) n0
  simp [idleState] at h1

/-- **The safety clause's antecedent holds after the step:** the switches on, no `work`, the builder's block
installed at the node, and peer 1's offer. -/
theorem witness_antecedent :
    AllOn kind ord (rOn kind ord) ∧
    ¬ NoStallEquiv.work (rOn kind ord) (abs kind ord n0 kA.chunk 0 "r" (cWitnessAfter kind ord)) ∧
    (abs kind ord n0 kA.chunk 0 "r" (cWitnessAfter kind ord)).installed n0 = true ∧
    (abs kind ord n0 kA.chunk 0 "r" (cWitnessAfter kind ord)).offered n0 1 = true := by
  rw [witness_after_abs]
  refine ⟨rOn_allOn kind ord, idleState_no_work kind ord _ n0 _ _ _, ?_, ?_⟩
  · simp [idleState, bgHolders]
  · simp [idleState, quietHeld_facts.2.2.2.1]

/-- **The witness's run** (one covered step) **keeps the model's `Invariants`,** given the Veil model's
statements for `retryAsk` and `retryNoop`: the carried theorem applied. -/
theorem witness_carried (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord) :
    MInv kind ord (rOn kind ord) (abs kind ord n0 kA.chunk 0 "r" (cWitnessAfter kind ord)) :=
  carried kind ord hA hN (Run.step (Run.start _) (Step.covered (witness_step kind ord))) (witness_start kind ord)

/-- **The safety clause's conclusion at the witness's end,** by `run_safety_twin`, with nothing of the Veil
model's: the chunk is held or the pull stopped. It shows that the antecedent is reached by a covered step that is
not a stutter. It concludes nothing new: the chunk was held before the step (`quietHeld_facts`). -/
theorem witness_safety :
    heldP (cWitnessAfter kind ord).w.st kA.chunk = true ∨ stopP (cWitnessAfter kind ord).w.st kA.chunk.1 = true :=
  run_safety_twin kind ord
    (Run.step (Run.start _) (Step.covered (witness_step kind ord))) (witness_start kind ord).1
    (rOn_allOn kind ord) (witness_antecedent kind ord).2.1 rfl (q := 1) quietHeld_after_facts.2.2.2

/-! ## The negative control -/

/-- The control's start: as the witness's, but the chunk is not held and the group is expired. -/
def cControl : Cfg kind ord := ⟨stalledStart, ctx1, ansExpired, bgHolders kind ord⟩

/-- The control's end: the timer has fired, on `retry_offer`'s `expired` branch. -/
def cControlAfter : Cfg kind ord :=
  ⟨retryFire 0 kA ctx1 ansExpired stalledStart, ctx1, ansExpired, bgHolders kind ord⟩

/-- The model's `Invariants` hold of the abstraction of the control's start, all seven switches on. -/
theorem control_start :
    MInv kind ord (rOn kind ord) (abs kind ord n0 kA.chunk 0 "r" (cControl kind ord)) := by
  unfold cControl
  rw [abs_idle kind ord stalledStart_idle rfl rfl, stalledStart_facts.2.1]
  exact idleState_invariants kind ord _ n0 _ _ _ stalledStart_facts.2.2.2.2.1

omit [Inhabited kind] [Inhabited ord] in
/-- The abstraction after the firing: the idle state with the chunk not held, the pull not stopped, and no timer
armed. The firing is the twin's `expired` branch (`retryFire_expired`). -/
theorem control_after_abs :
    abs kind ord n0 kA.chunk 0 "r" (cControlAfter kind ord) =
      idleState kind ord n0 false false false (offeredP ansExpired stalledStart.st kA.chunk) := by
  unfold cControlAfter
  rw [retryFire_expired stalledStart_facts.1 stalledStart_stop rfl,
    abs_idle kind ord (stalledStart_idle.eraseTimer 0) rfl rfl, stalledStart_facts.2.2.1]
  show idleState kind ord n0 (heldP stalledStart.st kA.chunk) (stopP stalledStart.st kA.group) false _ = _
  rw [stalledStart_facts.1, stalledStart_stop]

/-- **The control: the safety clause is false after the `expired` firing.** No `work`, the builder's block
installed, peer 1's offer, the chunk not held and the pull not stopped: the model's `stalled`. -/
theorem control_stalled :
    ¬ NoStallEquiv.offers_resolve (rOn kind ord) (abs kind ord n0 kA.chunk 0 "r" (cControlAfter kind ord)) := by
  rw [control_after_abs]
  exact idleState_stalled kind ord (rOn_allOn kind ord) n0 (q := 1) stalledStart_facts.2.2.2.1

/-- **So that firing is no step of a run,** given the Veil model's statements: it is not a covered step (the
asking step takes `expired = false`), it moves the abstraction, and `Invariants` fail after it. -/
theorem control_not_a_step (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord) :
    ¬ Step kind ord n0 kA.chunk 0 "r" (rOn kind ord) (cControl kind ord) (cControlAfter kind ord) :=
  not_step_of_not_inv kind ord hA hN (control_start kind ord) (fun h => control_stalled kind ord h.1)

omit [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind] [DecidableEq ord] [Inhabited ord]
  [NoStallEquiv.ord_EnumClass ord] in
/-- **The positive side of the control: with the group not expired, the same firing is a covered step,** the
asking one. So `expired` is what tells the two apart. -/
theorem control_asks_when_not_expired :
    Covered kind ord n0 kA.chunk ⟨stalledStart, ctx1, ansBlock, bgHolders kind ord⟩
      ⟨retryFire 0 kA ctx1 ansBlock stalledStart, ctx1, ansBlock, bgHolders kind ord⟩ := by
  obtain ⟨hheld, hwin, hfree, _, hW⟩ := stalledStart_asks_facts
  exact Covered.asks (d := 0.205) rfl rfl hheld stalledStart_stop rfl hwin hfree
    (by intro b _ hm; simp [stalledStart] at hm)
    (fun xs _ => List.Perm.refl xs) hW

/-- The model's `Invariants` hold of the abstraction of the control's start with the group **not** expired, all
seven switches on: the two sets of answers differ in `expired` only, which the abstraction does not read. -/
theorem control_asks_start :
    MInv kind ord (rOn kind ord)
      (abs kind ord n0 kA.chunk 0 "r" ⟨stalledStart, ctx1, ansBlock, bgHolders kind ord⟩) := by
  have hidle : IdleW ctx1 ansBlock stalledStart n0 kA.chunk :=
    ⟨stalledStart_idle.window, stalledStart_idle.lr, stalledStart_idle.park, stalledStart_idle.askedParked,
      stalledStart_idle.promise, stalledStart_idle.tied, stalledStart_idle.queued, stalledStart_idle.made,
      stalledStart_idle.self⟩
  rw [abs_idle kind ord hidle rfl rfl, stalledStart_facts.2.1]
  exact idleState_invariants kind ord _ n0 _ _ _ stalledStart_facts.2.2.2.2.1

/-- **An asking step from a state where `Invariants` hold keeps them,** given the Veil model's statements: the
control's world with the group not expired, the model's `retryAsk n₀ 1 o1 false`. This is a covered step whose
preservation is the Veil model's theorem for `retryAsk`, not a reading of the fixture. -/
theorem control_asks_carried (hA : FvRetryAsk kind ord) (hN : FvRetryNoop kind ord) :
    MInv kind ord (rOn kind ord)
      (abs kind ord n0 kA.chunk 0 "r"
        ⟨retryFire 0 kA ctx1 ansBlock stalledStart, ctx1, ansBlock, bgHolders kind ord⟩) :=
  covered_preserves kind ord hA hN 0 "r" (control_asks_when_not_expired kind ord) (control_asks_start kind ord)

/-! ## The `held` branch's open case -/

/-- **The last retry timer fires with the chunk held and a window of the chunk open: the clause `window_retry` is
false after it,** whatever the background: the node's window is open and no retry timer is armed.
(`Refine/RetryAsk.lean` proves that this firing is not the model's `retryNoop` and not a stutter.) -/
theorem held_last_open_breaks_window_retry {n₀ : Peer} {bg : MState kind ord} {r : MTheory kind ord}
    {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = true)
    (hlast : retryArmedP { w with timers := w.timers.eraseIdx i } a.chunk = false)
    (hopen : windowP ctx w.st a.chunk = true) :
    ¬ NoStallEquiv.window_retry r (alpha kind ord n₀ a.chunk ctx ans bg (retryFire i a ctx ans w)) := by
  rw [retryFire_held hheld]
  intro h
  have h1 : (alpha kind ord n₀ a.chunk ctx ans bg { w with timers := w.timers.eraseIdx i }).retryArmed n₀ = true :=
    h n₀ (by
      show (alpha kind ord n₀ a.chunk ctx ans bg { w with timers := w.timers.eraseIdx i }).inWindow n₀ = true
      simp [alpha, hopen])
  simp [alpha, hlast] at h1

/-! ## `Init` -/

/-- The background with every relation false. -/
def bgFalse : MState kind ord :=
  { gate := fun _ => false, installed := fun _ => false, got := fun _ => false, stop := fun _ => false,
    peerHas := fun _ _ => false, offered := fun _ _ => false, ledger := fun _ _ => false,
    inWindow := fun _ => false, retryArmed := fun _ => false, lrArmed := fun _ => false,
    parked := fun _ _ => false, askedParked := fun _ _ => false, promise := fun _ _ => false,
    tied := fun _ _ => false, made := fun _ _ _ => false, stage := fun _ _ _ _ => false,
    everLastResort := fun _ => false, everEarly := fun _ => false, everHeldBack := fun _ => false,
    everTied := fun _ => false, everSwitched := fun _ => false, closedAsk := fun _ => false }

/-- The state with every relation false is the model's `Init`. -/
theorem bgFalse_init (r : MTheory kind ord) :
    NoStallEquiv.Init (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) r (bgFalse kind ord) :=
  rfl

/-- **The abstraction of the empty world is the model's `Init`,** under answers with the gate closed
(`authenticable` false for the chunk's group), no block installed and no connected peer, over the background
with every relation false. (`hnow`: `now` is not below minus infinity. The pull is not stopped: `stop_pull` is
the twin's table, and the empty world's is empty.) This is apart from the carried theorem: that `Init` gives
`Invariants` is the model's, taken as `FvInit`. -/
theorem empty_is_init {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {ctx : Ctx} {ans : Answers}
    (r : MTheory kind ord) (hgate : ans.authenticable k.1 = false)
    (hinst : (ans.installedBlock sl rt).isSome = false) (hconn : ans.connectedTopicPeers = [])
    (hnow : ¬ ctx.now < negInf) :
    NoStallEquiv.Init (MTheory kind ord) (MState kind ord) Peer kind ord (MChi kind ord) r
      (abs kind ord n₀ k sl rt ⟨{}, ctx, ans, bgFalse kind ord⟩) := by
  have hoff : ∀ q, offeredP ans ({} : World).st k q = false := by
    intro q; simp [offeredP, hconn]
  have hidle : IdleW ctx ans ({} : World) n₀ k :=
    idleW_of_empty rfl rfl rfl rfl rfl rfl rfl rfl hnow (hoff n₀)
  have he : abs kind ord n₀ k sl rt ⟨{}, ctx, ans, bgFalse kind ord⟩ = bgFalse kind ord := by
    unfold abs alpha withBlocks bgFalse
    congr 1
    · funext n; by_cases h : n = n₀ <;> simp [h, hgate]
    · funext n; by_cases h : n = n₀ <;> simp [h, hinst]
    · funext n; by_cases h : n = n₀ <;> simp [h, heldP, Bits.has]
    · funext n; by_cases h : n = n₀ <;> simp [h, stopP]
    · funext n q; by_cases h : n = n₀ <;> simp [h, hoff]
    · funext n; by_cases h : n = n₀ <;> simp [h, hidle.window]
    · funext n; by_cases h : n = n₀ <;> simp [h, retryArmedP]
    · funext n; by_cases h : n = n₀ <;> simp [h, hidle.lr]
    · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.park]
    · funext n q; by_cases h : n = n₀ <;> simp [h]
    · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.promise]
    · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.tied]
    · funext n q j; by_cases h : n = n₀ <;> simp [h, madeOrd]
    · funext K n q j; by_cases h : n = n₀ <;> simp [h, hidle.queued]
  rw [he]
  exact bgFalse_init kind ord r

end

end Refine.Carry
