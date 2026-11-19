import Lake
open Lake DSL

-- A twin of protocol.md's Python in Lean 4: core Lean only, so that it can be imported
-- beside Veil v4.35.0, whose toolchain it shares.
package spectwin where

@[default_target]
lean_lib SpecTwin where

lean_exe replay where
  root := `Main
