module

public import Veil

/-! # A small Veil module with its theorems generated

The cut model in this package (`NoStallEquivModel.lean`) stops at `#gen_spec` and has no `<action>_<clause>`
theorem; the Veil model's proved file (`formal/veil`'s `NoStallEquiv.lean`) takes about 25 minutes and 20 GB to
build. This module is small enough to be checked and to have its theorems generated here, in seconds, with the
solver settings of the Veil model: two relations, one action with a parameter and a `require`, one invariant.
`Carry/BridgeUse.lean` takes its generated theorems through the bridge. -/

-- as the Veil model: the SMT solver's unsat answers are not trusted, and Lean's grind comes first
set_option veil.smt.trust false
set_option veil.solver "grind+smt"

veil module BridgeToy

type node

relation flag (n : node) : Bool
relation seen (n : node) : Bool

#gen_state

after_init {
  flag N := false
  seen N := false
}

action raise (n : node) {
  require ¬ flag n
  flag n := true
  seen n := true
}

invariant [flag_seen] flag N → seen N

#gen_spec

#check_invariants

#gen_theorems

end BridgeToy
