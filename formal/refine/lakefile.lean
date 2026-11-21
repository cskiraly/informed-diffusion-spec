import Lake
open Lake DSL

-- The twin of §6.1 beside the asking model's generated transitions. Veil at the release the model was checked
-- with (v4.35.0, 00a1f980; the manifest is `formal/veil`'s).
require veil from git "https://github.com/verse-lab/veil" @ "00a1f980bd46bf3f039d355db141183d05797e9f"
require spectwin from "../twin"

package refine where

@[default_target]
lean_lib Refine where
  roots := #[`QuietRanking, `NoStallEquivModel, `Refine.TwinStep, `Refine.PromiseDue, `Refine.Controls, `Refine.AskInterp, `Refine.RetryAsk]

-- The carry of the model's safety theorem to the twin's runs, apart from Refine.
-- Every module under Carry/ is in the library, so a file added there does not change this file.
lean_lib Carry where
  globs := #[.submodules `Carry]
