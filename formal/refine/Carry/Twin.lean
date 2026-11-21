import Refine.AskInterp

/-! # The twin's side of the witness and of the negative control

This file imports the twin and `Refine/AskInterp.lean`'s interpreter, not Veil (a file that imports Veil must not
elaborate the twin's monad).

- `retryFire_expired`: `retry_offer`'s `expired` branch, run: the fired timer is gone, and nothing else changes.
- `IdleW`: nothing of the tracked chunk is in flight at the node. `idleW_of_empty` gives it of a world whose
  tables of asks are empty.
- Two fixtures and their computed facts: `quietHeld` (the witness) and `stalledStart` (the negative control). -/

namespace Refine.Carry
open SpecTwin Refine.Ask

/-- `retry_offer(a)` where the chunk is not held, the pull not stopped and the group expired: the fired timer is
gone, and nothing else changes. The twin's own code, run, as `retryFire_held` is for the `held` branch. -/
theorem retryFire_expired {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = true) :
    retryFire i a ctx ans w = { w with timers := w.timers.eraseIdx i } := by
  unfold retryFire SpecTwin.retryOffer
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_held _)]
  rw [run_ite, ite_eq_right (by simp [hheld])]
  rw [run_bind_eq _ _ (run_stopPull _), run_ite, ite_eq_right (by simp [hstop])]
  rw [run_bind_eq _ _ (run_expired _), run_ite, ite_eq_left (by simp [hexp]), run_bind_eq _ _ (run_branch _),
    run_pure]

/-- **Nothing of the chunk `k` is in flight at the node `n₀`:** no window of it open, the last resort not armed,
no announcer parked or counted by the last resort, no promise, no tie, no ask queued, none ever taken by a queue;
and the node is not its own announcer. What is left free: whether the chunk is held, whether the pull is
stopped, who offered it, and the retry timers. -/
structure IdleW (ctx : Ctx) (ans : Answers) (w : World) (n₀ : Peer) (k : Chunk) : Prop where
  window : windowP ctx w.st k = false
  lr : w.st.lastResortArmed.contains k = false
  park : ∀ q, parkedP ctx.now w.st q k.1 = false
  askedParked : ∀ q, (w.st.askedParked.getD k {}).contains q = false
  promise : ∀ q, promisedP w.st q k = false
  tied : ∀ q, tiedP w.st q k = false
  queued : ∀ q, queuedP w.st q k = false
  made : ∀ q, w.made k q = 0
  self : offeredP ans w.st k n₀ = false

/-- A world whose tables of asks are empty is idle for every chunk: no ask noted, no last resort, no park, no
promise, no tie, nothing queued, no ask counted. `hnow`: `now` is not below minus infinity (true of every float;
the floating-point lemma is not proved here, as `Refine`'s `hW`). -/
theorem idleW_of_empty {ctx : Ctx} {ans : Answers} {w : World} {n₀ : Peer} {k : Chunk}
    (hasked : w.st.askedAt = {}) (hlr : w.st.lastResortArmed = {}) (hpark : w.st.park = {})
    (hap : w.st.askedParked = {}) (hprom : w.st.promises = {}) (htied : w.st.tied = {})
    (hq : w.st.queue = {}) (hmade : w.made = fun _ _ => 0) (hnow : ¬ ctx.now < negInf)
    (hself : offeredP ans w.st k n₀ = false) : IdleW ctx ans w n₀ k where
  window := by simp [windowP, hasked]
  lr := by simp [hlr]
  park := by intro q; simp [parkedP, hpark, hnow]
  askedParked := by intro q; simp [hap]
  promise := by intro q; simp [promisedP, hprom]
  tied := by intro q; simp [tiedP, htied]
  queued := by intro q; simp [queuedP, hq]
  made := by intro q; simp [hmade]
  self := hself

/-- **As `IdleW`, with the promises left free:** nothing of the chunk is in flight at the node but, perhaps,
promises of it. -/
structure IdleButPromises (ctx : Ctx) (ans : Answers) (w : World) (n₀ : Peer) (k : Chunk) : Prop where
  window : windowP ctx w.st k = false
  lr : w.st.lastResortArmed.contains k = false
  park : ∀ q, parkedP ctx.now w.st q k.1 = false
  askedParked : ∀ q, (w.st.askedParked.getD k {}).contains q = false
  tied : ∀ q, tiedP w.st q k = false
  queued : ∀ q, queuedP w.st q k = false
  made : ∀ q, w.made k q = 0
  self : offeredP ans w.st k n₀ = false

/-- A world whose tables of asks are empty but for its promises is idle but for them. -/
theorem idleButPromises_of_empty {ctx : Ctx} {ans : Answers} {w : World} {n₀ : Peer} {k : Chunk}
    (hasked : w.st.askedAt = {}) (hlr : w.st.lastResortArmed = {}) (hpark : w.st.park = {})
    (hap : w.st.askedParked = {}) (htied : w.st.tied = {})
    (hq : w.st.queue = {}) (hmade : w.made = fun _ _ => 0) (hnow : ¬ ctx.now < negInf)
    (hself : offeredP ans w.st k n₀ = false) : IdleButPromises ctx ans w n₀ k where
  window := by simp [windowP, hasked]
  lr := by simp [hlr]
  park := by intro q; simp [parkedP, hpark, hnow]
  askedParked := by intro q; simp [hap]
  tied := by intro q; simp [tiedP, htied]
  queued := by intro q; simp [queuedP, hq]
  made := by intro q; simp [hmade]
  self := hself

/-- Taking a timer away leaves the twin's state, the asks' counts, and so idleness, as they were. -/
theorem IdleW.eraseTimer {ctx : Ctx} {ans : Answers} {w : World} {n₀ : Peer} {k : Chunk}
    (h : IdleW ctx ans w n₀ k) (i : Nat) : IdleW ctx ans { w with timers := w.timers.eraseIdx i } n₀ k :=
  ⟨h.window, h.lr, h.park, h.askedParked, h.promise, h.tied, h.queued, h.made, h.self⟩

/-! ## Fixtures

As `Refine/AskInterp.lean`'s, they are not worlds a run reaches (the group `"g"` is not a key the toy makes, and a
timer is armed with nothing said of when). They show that the hypotheses can hold at once. -/

/-- The node of the fixtures. -/
def n0 : Peer := 0

/-- Two answers, each on its own: `authenticable` says that an installed block's bid commits the group, and
`installed_block` answers every slot and root with a block. Peer 1 is connected; nothing is expired.
(`installed_block` answers with the block. The block here is a dummy, of slot 0 with neither a group id nor a
descriptor: the abstraction reads only that there is one, and nothing here reads its content. It is not a block
a node could present with this `authenticable`: the twin's own level 1 (`Sec3.lean`, `validate_chunk`) accepts
no chunk that names it, under either design. Whether a pull is stopped is the world's, not the answers'.) -/
def ansBlock : Answers :=
  { connectedTopicPeers := [1], authenticable := fun _ => true,
    installedBlock := fun _ _ => some { slot := 0, groupId := none, desc := none } }

/-- The same, with the group expired. -/
def ansExpired : Answers := { ansBlock with expired := fun _ => true }

/-- **The witness's world:** the node holds the chunk (`mine["g"]` has index 0); peer 1 is on the chunk's offer
list; one retry timer is armed; nothing else. -/
def quietHeld : World :=
  { st := {
      mine := (∅ : Std.HashMap Group Bits).insert "g" 1
      offers := (∅ : Std.HashMap Key (List Peer)).insert kA [1] }
    timers := [(0.205, .retryOffer kA)] }

/-- **The negative control's world:** as `quietHeld`, but the chunk is not held. -/
def stalledStart : World :=
  { st := { offers := (∅ : Std.HashMap Key (List Peer)).insert kA [1] }
    timers := [(0.205, .retryOffer kA)] }

/-- What is computed on a fixture (`native_decide`, as `Refine`'s): whether the chunk is held; the timer at place
0 is the chunk's last retry timer; peer 1 offered the chunk and the node did not; `now` is not below minus
infinity. -/
abbrev FixtureFacts (ans : Answers) (w : World) (held : Bool) : Prop :=
  heldP w.st kA.chunk = held ∧
  retryArmedP w kA.chunk = true ∧
  retryArmedP { w with timers := w.timers.eraseIdx 0 } kA.chunk = false ∧
  offeredP ans w.st kA.chunk 1 = true ∧
  offeredP ans w.st kA.chunk n0 = false ∧
  decide (ctx1.now < negInf) = false

theorem quietHeld_facts : FixtureFacts ansBlock quietHeld true := by native_decide
theorem stalledStart_facts : FixtureFacts ansExpired stalledStart false := by native_decide

/-- Neither world has a pull stopped: its `stop_pull` is empty. -/
theorem quietHeld_stop : stopP quietHeld.st kA.group = false := by simp [stopP, quietHeld]
theorem stalledStart_stop : stopP stalledStart.st kA.group = false := by simp [stopP, stalledStart]

/-- The negative control's world with the group **not** expired: `Refine/AskInterp.lean`'s facts for the asking
path hold of it (the chunk not held, the key's window closed, an announcer free, the pick peer 1, an ask made now
in its window). -/
theorem stalledStart_asks_facts : FixtureOk ansBlock stalledStart 1 := by native_decide

/-- The witness's world is idle for the chunk. -/
theorem quietHeld_idle : IdleW ctx1 ansBlock quietHeld n0 kA.chunk :=
  idleW_of_empty rfl rfl rfl rfl rfl rfl rfl rfl (of_decide_eq_false quietHeld_facts.2.2.2.2.2)
    quietHeld_facts.2.2.2.2.1

/-- The negative control's world is idle for the chunk. -/
theorem stalledStart_idle : IdleW ctx1 ansExpired stalledStart n0 kA.chunk :=
  idleW_of_empty rfl rfl rfl rfl rfl rfl rfl rfl (of_decide_eq_false stalledStart_facts.2.2.2.2.2)
    stalledStart_facts.2.2.2.2.1

/-- **The witness's step, computed** (no theorem of this file between): the twin's own `retry_offer`, run on
`quietHeld`, leaves no timer and nothing raised, with the chunk still held and peer 1 still its announcer. -/
theorem quietHeld_after_facts :
    (retryFire 0 kA ctx1 ansBlock quietHeld).timers.length = 0 ∧
    (retryFire 0 kA ctx1 ansBlock quietHeld).crashed = [] ∧
    heldP (retryFire 0 kA ctx1 ansBlock quietHeld).st kA.chunk = true ∧
    offeredP ansBlock (retryFire 0 kA ctx1 ansBlock quietHeld).st kA.chunk 1 = true := by native_decide

/-- **The control's step, computed:** the twin's own `retry_offer`, run on `stalledStart` with the group
expired, leaves no timer and nothing raised, with the chunk not held and peer 1 still its announcer. With the
group not expired the same firing asks: an IWANT is queued to peer 1 and a timer is armed. -/
theorem stalledStart_after_facts :
    (retryFire 0 kA ctx1 ansExpired stalledStart).timers.length = 0 ∧
    (retryFire 0 kA ctx1 ansExpired stalledStart).crashed = [] ∧
    heldP (retryFire 0 kA ctx1 ansExpired stalledStart).st kA.chunk = false ∧
    offeredP ansExpired (retryFire 0 kA ctx1 ansExpired stalledStart).st kA.chunk 1 = true ∧
    queuedP (retryFire 0 kA ctx1 ansExpired stalledStart).st 1 kA.chunk = false ∧
    queuedP (retryFire 0 kA ctx1 ansBlock stalledStart).st 1 kA.chunk = true ∧
    (retryFire 0 kA ctx1 ansBlock stalledStart).timers.length = 1 := by native_decide

end Refine.Carry
