import Lake
open Lake DSL

-- Veil 2.0's release v4.35.0 (2026-11-07; its lean-toolchain is ours)
require veil from git "https://github.com/verse-lab/veil" @ "00a1f980bd46bf3f039d355db141183d05797e9f"

package fvveil where

@[default_target]
lean_lib FvVeil where
  roots := #[`ClaimWins, `SenderFault, `NoStallAsk, `NoStallTransport, `NoStallCount, `NoStallEquiv,
    `Agreement, `QuietRanking, `NoStallAskAdv, `NoStallTransportAdv, `NoStallEquivAdv]
