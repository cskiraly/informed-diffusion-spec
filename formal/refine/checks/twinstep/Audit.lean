import Refine.Controls
/-! The audit of the twinstep check: every theorem of `formal/refine/Refine/TwinStep.lean`, `PromiseDue.lean` and
`Controls.lean` (the files it imports), what it rests on, and the statements and definitions as Lean prints
them. Run by `check.sh` beside this file. Nothing is listed by hand but the axioms allowed: the declarations are
found in the environment, by their namespace, so one added later is audited too.

What it does not see: a declaration outside the namespace `Refine`, and what a printed statement hides (instance
arguments are not printed). -/
open Lean Elab Command Meta

/-- The axioms an audited theorem may rest on. -/
def allowed : List Name := [``propext, ``Classical.choice, ``Quot.sound]

/-- The two theorems that apply a theorem to a concrete state compute float comparisons by `native_decide`. Each
may also rest on the axioms that tactic made for it, named here one by one; no other axiom may be declared. -/
def computed : List (Name × List Name) := [
  (`Refine.promiseDue_refines_applies,
    [`Refine.promiseDue_refines_applies._native.native_decide.ax_1_2,
     `Refine.promiseDue_refines_applies._native.native_decide.ax_1_4]),
  (`Refine.promiseDue_not_promiseDue_applies,
    [`Refine.promiseDue_not_promiseDue_applies._native.native_decide.ax_1_2])]

elab "#audit" : command => do
  let env ← getEnv
  let mut thms : Array Name := #[]
  let mut axs : Array Name := #[]
  let mut defs : Array Name := #[]
  for (n, ci) in env.constants.toList do
    if (`Refine).isPrefixOf n then
      match ci with
      | .thmInfo _ => if !n.isInternalDetail then thms := thms.push n
      | .axiomInfo _ => axs := axs.push n
      | .defnInfo _ => if !n.isInternalDetail then defs := defs.push n
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
    logInfo m!"axiom {a}: {if ok then "a computed comparison's" else "NOT ALLOWED"}"
  logInfo m!"audit: {thms.size} theorems, {defs.size} definitions, {axs.size} axioms declared, {bad} not allowed"
  -- the record: every statement, every declared axiom's, every definition
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

#audit
