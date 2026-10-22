import Lake
open Lake DSL

-- Veil 2.0, a pre-release: pinned to main as of 2026-10-17 (its lean-toolchain is ours)
require veil from git "https://github.com/verse-lab/veil" @ "02791b2d1576efc88fcbfcd417cbb2862c88a8ad"

package fvveil where

@[default_target]
lean_lib FvVeil where
  roots := #[`ClaimWins]
