import Carry.Witness
import Carry.AfterAsk
import Carry.BridgeUse
import Carry.PromiseRun
/-! The carry's audit: every theorem of the namespace `Refine.Carry` (`formal/refine/Carry/*.lean`), what it rests
on, and the statements, definitions and inductive types as Lean prints them. Run by `check.sh` beside this file.
Nothing is listed by hand but the axioms allowed and the toy's four generated theorems: the declarations are
found in the environment, by their namespace, so one added later is audited too.

The inductive types are in the record with their constructors, since the piece's claims rest on them: the five
structures of the Veil model's statements (`FvRetryAsk`, `FvRetryNoop`, `FvInit`, `FvPromiseDue`, `FvParkOther`: a
constructor's type is its 21 fields), `Meets`, the run (`Cfg`, `Covered`, `Step`, `Run`, `CoveredRun`,
`PromiseCovered`), `PlainInv`, `IdleW` and `IdleButPromises`.

As `../asking/Audit.lean`, every statement, definition and constructor also gets a fingerprint (the structural hash of
its type, and of a definition's value), for what a printed form hides.

What it does not see: a declaration outside the namespace `Refine.Carry`, but for the toy's four generated
theorems, which are checked for their axioms and whose statements are in the record. Piece 1's declarations (`Refine.Ask`) are its own check's. -/
open Lean Elab Command Meta

/-- The axioms a theorem of the piece may rest on. -/
def allowed : List Name := [``propext, ``Classical.choice, ``Quot.sound]

def qF : Name := `Refine.Carry.quietHeld_facts._native.native_decide.ax_1_1
def qA : Name := `Refine.Carry.quietHeld_after_facts._native.native_decide.ax_1_1
def sF : Name := `Refine.Carry.stalledStart_facts._native.native_decide.ax_1_1
def sA : Name := `Refine.Carry.stalledStart_after_facts._native.native_decide.ax_1_1
def sK : Name := `Refine.Carry.stalledStart_asks_facts._native.native_decide.ax_1_1
def pF : Name := `Refine.Carry.promisedOne_facts._native.native_decide.ax_1_1

/-- The six computed facts (`native_decide`), each with the axiom that tactic made for it; and the theorems
about the three fixtures, each resting on its fixture's facts. No other axiom may be declared, and no other
theorem may rest on one of these. -/
def computed : List (Name × List Name) := [
  (`Refine.Carry.quietHeld_facts, [qF]),
  (`Refine.Carry.quietHeld_after_facts, [qA]),
  (`Refine.Carry.stalledStart_facts, [sF]),
  (`Refine.Carry.stalledStart_after_facts, [sA]),
  (`Refine.Carry.stalledStart_asks_facts, [sK]),
  (`Refine.Carry.quietHeld_idle, [qF]),
  (`Refine.Carry.stalledStart_idle, [sF]),
  (`Refine.Carry.witness_start, [qF]),
  (`Refine.Carry.witness_step, [qF]),
  (`Refine.Carry.witness_after_abs, [qF]),
  (`Refine.Carry.witness_not_stutter, [qF]),
  (`Refine.Carry.witness_antecedent, [qF]),
  (`Refine.Carry.witness_carried, [qF]),
  (`Refine.Carry.witness_safety, [qF, qA]),
  (`Refine.Carry.control_asks_start, [sF]),
  (`Refine.Carry.control_asks_carried, [sF, sK]),
  (`Refine.Carry.promisedOne_idle, [pF]),
  (`Refine.Carry.promisedOne_promised_offered, [pF]),
  (`Refine.Carry.promise_start, [pF]),
  (`Refine.Carry.promise_step_applies, [pF]),
  (`Refine.Carry.control_start, [sF]),
  (`Refine.Carry.control_after_abs, [sF]),
  (`Refine.Carry.control_stalled, [sF]),
  (`Refine.Carry.control_not_a_step, [sF]),
  (`Refine.Carry.control_asks_when_not_expired, [sK]),
  (`Refine.Carry.promisedOne_facts, [pF]),
  (`Refine.Carry.promise_due_applies, [pF])]

/-- The toy's generated theorems (`#gen_theorems`, `Carry/BridgeToy.lean`): they must be there, on the allowed
axioms. -/
def toy : List Name := [`BridgeToy.raise_flag_seen, `BridgeToy.initializer_flag_seen,
  `BridgeToy.raise_doesNotThrow, `BridgeToy.initializer_doesNotThrow]

elab "#audit" : command => do
  let env ← getEnv
  let mut thms : Array Name := #[]
  let mut axs : Array Name := #[]
  let mut defs : Array Name := #[]
  let mut inds : Array Name := #[]
  for (n, ci) in env.constants.toList do
    if (`Refine.Carry).isPrefixOf n then
      match ci with
      | .thmInfo _ => if !n.isInternalDetail then thms := thms.push n
      | .axiomInfo _ => axs := axs.push n
      | .defnInfo _ => if !n.isInternalDetail then defs := defs.push n
      | .inductInfo _ => if !n.isInternalDetail && n.getString! != "below" then inds := inds.push n
      | _ => pure ()
  let byName (a : Array Name) := a.qsort (·.toString < ·.toString)
  let mut bad : Nat := 0
  for n in byName thms do
    let used := byName (← collectAxioms n)
    let own := (computed.lookup n).getD []
    let ok := used.all fun a => allowed.contains a || own.contains a
    if !ok then bad := bad + 1
    logInfo m!"theorem {n}: {if ok then "ok" else "NOT ALLOWED"} {used}"
  for a in byName axs do
    let ok := computed.any (·.2.contains a)
    if !ok then bad := bad + 1
    logInfo m!"axiom {a}: {if ok then "a computed fact's" else "NOT ALLOWED"}"
  for n in toy do
    match env.find? n with
    | some (.thmInfo _) =>
      let used := byName (← collectAxioms n)
      let ok := used.all fun a => allowed.contains a
      if !ok then bad := bad + 1
      logInfo m!"toy theorem {n}: {if ok then "ok" else "NOT ALLOWED"} {used}"
    | _ =>
      bad := bad + 1
      logInfo m!"toy theorem {n}: NOT THERE"
  logInfo m!"audit: {thms.size} theorems, {defs.size} definitions, {inds.size} inductive types, {axs.size} axioms declared, {bad} not allowed"
  -- the record: every statement, every declared axiom's, every definition, every inductive type
  for n in byName thms do
    let some ci := env.find? n | continue
    logInfo m!"statement {n} : {← liftTermElabM (ppExpr ci.type)}"
  for n in byName axs do
    let some ci := env.find? n | continue
    logInfo m!"axiom's statement {n} : {← liftTermElabM (ppExpr ci.type)}"
  for n in byName defs do
    let some ci := env.find? n | continue
    let some v := ci.value? | continue
    logInfo m!"definition {n} : {← liftTermElabM (ppExpr ci.type)} :=\n{← liftTermElabM (ppExpr v)}"
  for n in byName inds do
    let some (.inductInfo iv) := env.find? n | continue
    logInfo m!"inductive {n} : {← liftTermElabM (ppExpr iv.type)}"
    for c in iv.ctors do
      let some cc := env.find? c | continue
      logInfo m!"constructor {c} : {← liftTermElabM (ppExpr cc.type)}"
  -- the toy's generated theorems, as `#gen_theorems` states them: the form the model's statements are written after
  for n in toy do
    let some ci := env.find? n | continue
    logInfo m!"toy statement {n} : {← liftTermElabM (ppExpr ci.type)}"
  -- the fingerprints: every statement; every definition, with those Lean makes for it, but none made in a proof;
  -- every inductive type and constructor
  let underTheorem (n : Name) : Bool := Id.run do
    let mut p := n.getPrefix
    while !p.isAnonymous do
      if let some (.thmInfo _) := env.find? p then return true
      p := p.getPrefix
    return false
  let mut made : Array Name := #[]
  for (n, ci) in env.constants.toList do
    if (`Refine.Carry).isPrefixOf n then
      if let .defnInfo _ := ci then
        if !underTheorem n then made := made.push n
  for n in byName thms do
    let some ci := env.find? n | continue
    logInfo m!"fingerprint statement {n} : {ci.type.hash}"
  for n in byName made do
    let some ci := env.find? n | continue
    let some v := ci.value? | continue
    logInfo m!"fingerprint definition {n} : {ci.type.hash} {v.hash}"
  for n in byName inds do
    let some (.inductInfo iv) := env.find? n | continue
    logInfo m!"fingerprint inductive {n} : {iv.type.hash}"
    for c in iv.ctors do
      let some cc := env.find? c | continue
      logInfo m!"fingerprint constructor {c} : {cc.type.hash}"

#audit
