import Carry.Plain
import Carry.Twin

/-! # An idle node over a background of holders

The witness and the negative control share one shape: nothing of the chunk is in flight at `n₀` (`IdleW`,
`Carry/Twin.lean`), and every other node holds the chunk with the builder's block and has nothing in flight
(`bgHolders`). The abstraction of such a configuration is an explicit state of the model (`idleState`, by
`abs_idle`), with four things left free: whether `n₀` holds the chunk, whether its pull is stopped, whether a
retry timer is armed, and who offered.

Of that state, in the model's own terms:
- `idleState_invariants`: with a retry timer armed, the model's `Invariants` hold, whatever the switches;
- `idleState_no_work`: with none armed, the model's `work` is false;
- `idleState_stalled`: with none armed, the chunk not held, the pull not stopped and an offer, the safety clause
  is false. -/

namespace Refine.Carry
open SpecTwin Refine.Ask
open scoped NoStallEquiv

section
variable (kind ord : Type) [DecidableEq kind] [Inhabited kind] [NoStallEquiv.kind_EnumClass kind]
  [DecidableEq ord] [Inhabited ord] [NoStallEquiv.ord_EnumClass ord]

/-- **A background of holders:** every node holds the chunk, with the builder's block installed and the gate
open, and nothing else: no offer, no timer, no ask or answer on its way, no claim known. -/
def bgHolders : MState kind ord :=
  { gate := fun _ => true, installed := fun _ => true, got := fun _ => true, stop := fun _ => false,
    peerHas := fun _ _ => false, offered := fun _ _ => false, ledger := fun _ _ => false,
    inWindow := fun _ => false, retryArmed := fun _ => false, lrArmed := fun _ => false,
    parked := fun _ _ => false, askedParked := fun _ _ => false, promise := fun _ _ => false,
    tied := fun _ _ => false, made := fun _ _ _ => false, stage := fun _ _ _ _ => false,
    everLastResort := fun _ => false, everEarly := fun _ => false, everHeldBack := fun _ => false,
    everTied := fun _ => false, everSwitched := fun _ => false, closedAsk := fun _ => false }

/-- **The model's state for an idle node over a background of holders:** `n₀` has the builder's block; it holds
the chunk or not (`held`), has stopped its pull or not (`stop`), has a retry timer armed or not (`armed`), and
was offered the chunk by the peers of `off`. -/
def idleState (n₀ : Peer) (held stop armed : Bool) (off : Peer → Bool) : MState kind ord :=
  { bgHolders kind ord with
    got := fun n => if n = n₀ then held else true
    stop := fun n => if n = n₀ then stop else false
    offered := fun n q => if n = n₀ then off q else false
    retryArmed := fun n => if n = n₀ then armed else false }

omit [Inhabited kind] [Inhabited ord] in
/-- **The abstraction of an idle configuration** over a background of holders, with the builder's block installed
and the gate open, is `idleState`: read off the world, the answers and the timers. -/
theorem abs_idle {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {w : World} {ctx : Ctx} {ans : Answers}
    (hidle : IdleW ctx ans w n₀ k) (hgate : ans.authenticable k.1 = true)
    (hinst : (ans.installedBlock sl rt).isSome = true) :
    abs kind ord n₀ k sl rt ⟨w, ctx, ans, bgHolders kind ord⟩ =
      idleState kind ord n₀ (heldP w.st k) (stopP w.st k.1) (retryArmedP w k) (offeredP ans w.st k) := by
  unfold abs alpha withBlocks idleState bgHolders
  congr 1
  · funext n; by_cases h : n = n₀ <;> simp [h, hgate]
  · funext n; by_cases h : n = n₀ <;> simp [h, hinst]
  · funext n; by_cases h : n = n₀ <;> simp [h, hidle.window]
  · funext n; by_cases h : n = n₀ <;> simp [h, hidle.lr]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.park]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.askedParked]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.promise]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.tied]
  · funext n q j; by_cases h : n = n₀ <;> simp [h, hidle.made, madeOrd]
  · funext K n q j; by_cases h : n = n₀ <;> simp [h, hidle.queued]

/-- **With a retry timer armed, the idle state satisfies the model's `Invariants`,** whatever the switches. `n₀`
is not its own announcer (`hself`), so every announcer is a holder. The safety clause holds because an offer
unresolved, with the timer armed and nothing parked or tied, is `work` (the model's `retryAsk` is enabled). -/
theorem idleState_invariants (r : MTheory kind ord) (n₀ : Peer) (held stop : Bool) (off : Peer → Bool)
    (hself : off n₀ = false) : MInv kind ord r (idleState kind ord n₀ held stop true off) := by
  apply minv_of_plain
  constructor
  case offers_resolve =>
    intro N Q _ hw hi ho
    rw [work_iff] at hw
    by_cases hN : N = n₀
    · subst hN
      cases held with
      | true => simp [idleState, bgHolders]
      | false =>
        cases stop with
        | true => simp [idleState, bgHolders]
        | false =>
          -- neither held nor stopped: the offer, with the timer armed and nothing parked or tied, is `work`
          exfalso
          apply hw
          simp [idleState, bgHolders] at ho
          simp [WorkP, OutstandingP, idleState, bgHolders]
          exact Or.inl ⟨Q, ho⟩
    · simp [idleState, bgHolders, hN]
  case offer_holder =>
    intro N Q
    by_cases hQ : Q = n₀
    · subst hQ; simp [idleState, bgHolders, hself]
    · simp [idleState, bgHolders, hQ]
  case unparked_retry =>
    intro N Q _
    by_cases hN : N = n₀ <;> simp [idleState, bgHolders, hN]
  case offer_active =>
    intro N M _
    by_cases hN : N = n₀ <;> simp [idleState, bgHolders, hN]
  all_goals simp [idleState, bgHolders, PipelineP]

/-- **With no retry timer armed, the idle state has no `work`:** none of the model's twelve enabling conditions
holds, at `n₀` or elsewhere. -/
theorem idleState_no_work (r : MTheory kind ord) (n₀ : Peer) (held stop : Bool) (off : Peer → Bool) :
    ¬ NoStallEquiv.work r (idleState kind ord n₀ held stop false off) := by
  rw [work_iff]
  simp [WorkP, OutstandingP, idleState, bgHolders]

/-- **The model's `stalled`, at the idle state:** no timer armed, the chunk not held, the pull not stopped, and
an offer: with the switches on, the safety clause is false. -/
theorem idleState_stalled {r : MTheory kind ord} (hon : AllOn kind ord r) (n₀ : Peer) {off : Peer → Bool}
    {q : Peer} (hoff : off q = true) :
    ¬ NoStallEquiv.offers_resolve r (idleState kind ord n₀ false false false off) := by
  intro h
  have h' := offers_resolve_gives kind ord h hon (idleState_no_work kind ord r n₀ false false off)
    (N := n₀) (Q := q) (by simp [idleState, bgHolders]) (by simp [idleState, hoff])
  simp [idleState] at h'

/-- **The idle state with promises:** as `idleState`, and `n₀` has an open promise of the chunk to the peers of
`prom`. -/
def promState (n₀ : Peer) (held stop armed : Bool) (off prom : Peer → Bool) : MState kind ord :=
  { idleState kind ord n₀ held stop armed off with
    promise := fun n q => if n = n₀ then prom q else false }

omit [Inhabited kind] [Inhabited ord] in
/-- The abstraction of a configuration that is idle but for its promises, over a background of holders. -/
theorem abs_prom {n₀ : Peer} {k : Chunk} {sl : Nat} {rt : Root} {w : World} {ctx : Ctx} {ans : Answers}
    (hidle : IdleButPromises ctx ans w n₀ k) (hgate : ans.authenticable k.1 = true)
    (hinst : (ans.installedBlock sl rt).isSome = true) :
    abs kind ord n₀ k sl rt ⟨w, ctx, ans, bgHolders kind ord⟩ =
      promState kind ord n₀ (heldP w.st k) (stopP w.st k.1) (retryArmedP w k) (offeredP ans w.st k)
        (fun q => promisedP w.st q k) := by
  unfold abs alpha withBlocks promState idleState bgHolders
  congr 1
  · funext n; by_cases h : n = n₀ <;> simp [h, hgate]
  · funext n; by_cases h : n = n₀ <;> simp [h, hinst]
  · funext n; by_cases h : n = n₀ <;> simp [h, hidle.window]
  · funext n; by_cases h : n = n₀ <;> simp [h, hidle.lr]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.park]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.askedParked]
  · funext n q; by_cases h : n = n₀ <;> simp [h, hidle.tied]
  · funext n q j; by_cases h : n = n₀ <;> simp [h, hidle.made, madeOrd]
  · funext K n q j; by_cases h : n = n₀ <;> simp [h, hidle.queued]

/-- **With a retry timer armed, the idle state with promises satisfies the model's `Invariants`,** whatever the
switches, where `n₀` is not its own announcer and every promise is to an announcer (`hsub`). The safety clause
holds because an offer unresolved is `work`: the promise to that announcer falls due (`promiseDue`), or, with
none to it, the retry asks it (`retryAsk`). -/
theorem promState_invariants (r : MTheory kind ord) (n₀ : Peer) (held stop : Bool) (off prom : Peer → Bool)
    (hself : off n₀ = false) (hsub : ∀ q, prom q = true → off q = true) :
    MInv kind ord r (promState kind ord n₀ held stop true off prom) := by
  apply minv_of_plain
  constructor
  case offers_resolve =>
    intro N Q _ hw hi ho
    rw [work_iff] at hw
    by_cases hN : N = n₀
    · subst hN
      cases held with
      | true => simp [promState, idleState, bgHolders]
      | false =>
        cases stop with
        | true => simp [promState, idleState, bgHolders]
        | false =>
          exfalso
          apply hw
          simp [promState, idleState, bgHolders] at ho
          cases hp : prom Q with
          | true =>
            exact Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr
              ⟨N, Q, by simp [promState, hp]⟩))))))))))
          | false =>
            exact Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inl
              ⟨N, Q, by simp [promState, idleState, bgHolders, OutstandingP, hp, ho]⟩)))))))
    · simp [promState, idleState, bgHolders, hN]
  case offer_holder =>
    intro N Q
    by_cases hQ : Q = n₀
    · subst hQ; simp [promState, idleState, bgHolders, hself]
    · simp [promState, idleState, bgHolders, hQ]
  case asked_offered =>
    intro N Q J _
    by_cases hN : N = n₀
    · simp [promState, idleState, bgHolders, hN]
      intro h
      exact Or.inl (hsub Q h)
    · simp [promState, idleState, bgHolders, hN]
  case unparked_retry =>
    intro N Q _
    by_cases hN : N = n₀ <;> simp [promState, idleState, bgHolders, hN]
  case offer_active =>
    intro N M _
    by_cases hN : N = n₀ <;> simp [promState, idleState, bgHolders, hN]
  all_goals simp [promState, idleState, bgHolders, PipelineP]

end

end Refine.Carry
