import Refine.RetryAsk
/-! The asking path's audit: every theorem of the namespace `Refine.Ask` (`formal/refine/Refine/AskInterp.lean` and
`RetryAsk.lean`), what it rests on, and the statements and definitions as Lean prints them. Run by `check.sh`
beside this file. Nothing is listed by hand but the axioms allowed: the declarations are found in the environment,
by their namespace, so one added later is audited too.

A printed statement or definition can hide what it elides (`⋯`), an instance at a place it is applied, and a
structure's fields left at their defaults. So every statement and every definition also gets a fingerprint: the
structural hash of its type, and of a definition's value. The definitions Lean makes for the written ones (a
field's default, a matcher) are fingerprinted too, but not printed; those made inside a proof are left out, since
a proof may change.

What it does not see: a declaration outside the namespace `Refine.Ask`. -/
open Lean Elab Command Meta

/-- The axioms a theorem of the piece may rest on. -/
def allowed : List Name := [``propext, ``Classical.choice, ``Quot.sound]

/-- The six computed facts (`native_decide`: float comparisons), each with the axiom that tactic made for it; and
the seven applications, each resting on its fixture's fact. No other axiom may be declared. -/
def computed : List (Name × List Name) := [
  (`Refine.Ask.threeAnn_facts, [`Refine.Ask.threeAnn_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.threeAnnFull_facts, [`Refine.Ask.threeAnnFull_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.laterAsk_fourth_facts, [`Refine.Ask.laterAsk_fourth_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.laterAsk_later_facts, [`Refine.Ask.laterAsk_later_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_refines_applies, [`Refine.Ask.threeAnn_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_refines_applies_refused, [`Refine.Ask.threeAnnFull_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_refines_applies_fourth, [`Refine.Ask.laterAsk_fourth_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_refines_applies_later, [`Refine.Ask.laterAsk_later_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.threeAnn_after_facts, [`Refine.Ask.threeAnn_after_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_admitted_not_refused_applies, [`Refine.Ask.threeAnn_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_refused_not_admitted_applies, [`Refine.Ask.threeAnnFull_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.heldLast_facts, [`Refine.Ask.heldLast_facts._native.native_decide.ax_1_1]),
  (`Refine.Ask.retryFire_held_last_applies, [`Refine.Ask.heldLast_facts._native.native_decide.ax_1_1])]

elab "#audit" : command => do
  let env ← getEnv
  let mut thms : Array Name := #[]
  let mut axs : Array Name := #[]
  let mut defs : Array Name := #[]
  for (n, ci) in env.constants.toList do
    if (`Refine.Ask).isPrefixOf n then
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
    logInfo m!"axiom {a}: {if ok then "a computed fact's" else "NOT ALLOWED"}"
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
  -- the fingerprints: every statement; every definition, with those Lean makes for it, but none made in a proof
  let underTheorem (n : Name) : Bool := Id.run do
    let mut p := n.getPrefix
    while !p.isAnonymous do
      if let some (.thmInfo _) := env.find? p then return true
      p := p.getPrefix
    return false
  let mut made : Array Name := #[]
  for (n, ci) in env.constants.toList do
    if (`Refine.Ask).isPrefixOf n then
      if let .defnInfo _ := ci then
        if !underTheorem n then made := made.push n
  for n in byName thms do
    let some ci := env.find? n | continue
    logInfo m!"fingerprint statement {n} : {ci.type.hash}"
  for n in byName made do
    let some ci := env.find? n | continue
    let some v := ci.value? | continue
    logInfo m!"fingerprint definition {n} : {ci.type.hash} {v.hash}"

#audit
