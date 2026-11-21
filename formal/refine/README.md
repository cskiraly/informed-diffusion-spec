# formal/refine: the asking path of the twin against the Veil model

This directory is a Lake package. It has both the Lean twin of `protocol.md` (`../twin`, by path) and the
generated transitions of one Veil model (`NoStallEquiv` in `../veil`), and it proves statements that relate the
two. It is a first piece of a refinement, with a narrow scope, stated below. It is not a proof that the twin
satisfies the model's properties.

## What the package proves and assumes

- **`Refine/`** relates the twin's side of the asking path of §6.1 to the model. `AskInterp.lean` defines an
  interpreter that answers the twin's questions from fixed functions. `RetryAsk.lean` defines an
  abstraction, `alpha`, from the state of the twin at one node and one chunk to the state of the model.
  Theorems show that a retry timer firing in the twin (`retry_offer`), read through `alpha`, is a step of the
  model's generated transition `retryAsk` or `retryNoop`, and that a promise falling due (`promise_due`) is the
  model's `promiseDue` or `parkOther` (`PromiseDue.lean`). A firing that changes the abstraction is one of these
  named transitions. A retry timer firing for a key of another chunk, or a promise of another group falling due,
  leaves the abstraction as it was, and the theorems take such a step as the model's `stutter`
  (`retryFire_asks_is_next_for`, `promiseDue_handler_is_next_for`). `Controls.lean` and the `…_applies`
  theorems apply the statements to concrete states, so that their hypotheses are shown to hold together.
- **`Carry/`** carries the model's safety clause along a run of the twin. A run is a finite sequence of steps, of
  three kinds that `Carry/Run.lean` defines. A covered step is a retry timer firing in one of four ways; for each
  way, a theorem of `RetryAsk.lean` proves what the firing does, and the step carries that theorem's hypotheses. A
  step of the second kind leaves the abstraction as it was. A step of the third kind is any other change, under
  the hypothesis that the abstraction satisfies `Invariants` after it. A promise falling due enters a run as a
  step of the third kind, and for it the package proves that hypothesis instead of assuming it: `promise_step` in
  `Carry/PromiseRun.lean` proves it from `Invariants` before the step and the model's statements for `promiseDue`
  and `parkOther`. The carried theorem states that if a run starts from a
  configuration whose abstraction satisfies the model's `Invariants`, then the abstraction of every configuration
  of the run satisfies `Invariants` too.

**The package takes these as hypotheses and does not prove them:**
- **The Veil model's own preservation statements**, for those four actions and for the initializer, are
  hypotheses. `Carry/Fv.lean` states them as five structures, with a field for each clause of `Invariants`. They
  are the statements that `formal/veil` proves after `#gen_spec`; this package does not build those proofs (see
  "The link to `formal/veil`" below).
- **After every step of the third kind other than a promise falling due, `Invariants` is assumed again.** The
  package covers four of the model's 31 actions: `retryAsk` and `retryNoop` through the covered steps, and
  `promiseDue` and `parkOther` through `promise_step`. Every other change of the twin's state that the
  abstraction sees can enter a run only as a step of the third kind, that is, only with `Invariants` assumed
  after it. Such changes include an arrival and a write of `stop_pull` for the tracked group.

**The package does not claim:**
- that the twin satisfies the model's `offers_resolve`, or any liveness property;
- anything about a step of the third kind beyond the hypothesis named above;
- **the correspondence of `stop`.** The model's `stop` is a node's decode claim. In the twin, `claim_group` sets
  `stop_pull` for that claim, `drop_group` sets it for a group found invalid, and `publish` sets it for the
  source's own group; nothing clears `stop_pull`. Whether the model's `stop` also means the last two cases is
  open.

## The link to `formal/veil`

Veil closes a module at `#gen_spec`. The theorems here need the model's generated definitions, but not the proofs
that follow them in `formal/veil`, which take a long build. So this package does not import the model from
`formal/veil`. Instead it holds two files whose text must be that of `formal/veil`:

- `NoStallEquivModel.lean`: `../veil/NoStallEquiv.lean` up to and including its `#gen_spec` line, then an empty
  line and `end NoStallEquiv`;
- `QuietRanking.lean`: the whole of `../veil/QuietRanking.lean`.

Do not edit these files; remake them from `formal/veil` by the rules above. `checks/veil-link.sh` checks each file
byte for byte against the text it must have. It also checks that the three `lean-toolchain` files are equal, and
that the `lake-manifest.json` of this package matches that of `formal/veil`, package for package, with one package
more: the twin (`spectwin` at `../twin`). The three other checks below run `veil-link.sh` first and fail if it
fails. So the link is by equal text: a statement taken here as a hypothesis has the form that `formal/veil`
proves, and nothing in this package checks that proof.

## Build and check

Use Lean 4.35.0 through [elan](https://github.com/leanprover/elan), as for `formal/veil`. Run `lake build` in this
directory to fetch Veil and its dependencies under `.lake/` and build the package. In one measurement, this took
about six minutes on eight threads and peaked at 7 GiB, the fetch included.

    bash formal/refine/checks/veil-link.sh               # the link alone: a second, nothing built
    bash formal/refine/checks/twinstep/check.sh          # Refine/TwinStep, PromiseDue, Controls
    bash formal/refine/checks/asking/check.sh            # Refine/AskInterp, RetryAsk
    bash formal/refine/checks/carry/check.sh             # Carry/

The three checks other than the link each build their files from their sources with no warning, and refuse
`sorry` and `admit`. Each audits every theorem of its namespace for the axioms the theorem rests on
(`Audit.lean`), and compares every statement and definition with the recorded ones in `statements.txt`. The
twinstep check records them as Lean prints them, so it does not see what a printed form hides, such as instance
arguments. The asking and carry checks also record a structural fingerprint of each (the hash of its type, and of
a definition's value), and the carry check records its inductive types and their constructors too. After an
intended change of a statement, run the check with `--update`,
commit, and run the check again without `--update`: only a run without `--update` can pass. Each check has
controls beside it (`check-controls.sh`): changes that the check, or the build, must refuse, each for its own
reason.

Keep the line endings as committed when you check the files out: CRLF changes the bytes that `veil-link.sh`
compares.
