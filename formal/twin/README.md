# The Lean twin of `protocol.md`'s Python (draft)

**This is a draft.** What this commit shows is that `check.sh` passes at this commit, and nothing more. The
record that shows more (below) follows in a later release.

The twin is a transcription of the Python in `protocol.md`'s code blocks into Lean 4, function by function, with
the same branches; some of its tables have a form of their own. It is executable, not an abstract model. On its
own it proves nothing. Its value is that it can be checked
against the Python on one side, which this directory does, and linked to the Veil models on the other, which it
does not do yet.

## How it is checked: trace replay

A tracer runs the toy (`toy/`), which runs `protocol.md`'s code blocks directly. For every call of a covered
function it logs what the call read and wrote of the node's own tables, what it asked of the rest of the node and
what it returned. The twin replays each call from the logged state, with the logged answers, and must read what the
Python read, write what it wrote and return what it returned. Mutants, twins with one rule changed, show whether the
traces are strong enough to tell a wrong twin from the right one.

This is evidence on the scenarios traced, not on all inputs. A faithful twin copies a bug in the Python: replay
checks the copying, not the rules.

**A blind spot of the replay, known.** A trace logs what a call read and wrote, not at which point within the call
each access was made. Where a function asks the rest of the node to do something that writes an entry of the
twin's own tables, and the function's own code also reads that entry, a twin that reads it after that call, where
the Python reads it before, is not refused unless the value it reads changes what the replay compares.

## Scope

Every function that `protocol.md`'s code blocks define has its twin, matched by name. `check.sh`'s step `scope`
holds this to the document: each `def` must have an `enter "NAME"` in `SpecTwin/` and a case of the replay's for
`NAME`. By section:

| § | functions | § | functions | § | functions |
|---|---|---|---|---|---|
| 1 | 7 | 4.4 | 4 | 5.4 | 1 |
| 2 | 1 | 4.5 | 1 | 6.1 | 14 |
| 3 | 2 | 4.6 | 4 | 6.2 | 1 |
| 4.1 | 2 | 5.1 | 4 | 6.4 | 3 |
| 4.2 | 12 | 5.2 | 5 | 7.1 | 6 |
| 4.3 | 1 | 5.3 | 2 | 7.2 | 5 |

That is 75 functions; §6.3 and §8 define none. The twin also replays `held`, the toy's reader of what a node holds,
which §4.2's code calls. The files of `SpecTwin/` are named for parts of the document, not one to one with its
sections.

Not in the twin:
- the helpers `protocol.md` names but does not write out (`resolve`, `chunk_of` and the like): the replay answers
  them from the trace;
- the events it gives in prose: a connection's close, an announcer's offers ageing out, a group's expiry;
- `protocol-v2.md`'s own functions: a trace of a cell under `protocol-v2.md` replays through the functions of
  `protocol.md` that it keeps.

## What is not here yet

- **The record**: every trace of every cell of the toy's `check.py` under both documents, and the mutants' matrix
  that shows those traces tell each mutant from the twin. `record.sh` makes it; it follows in a later release.
- **The link to the Veil models** (`formal/veil/`): a refinement from the twin to the models, under way, is not in
  this repository.

## Running it

It needs Lean 4 at the version `lean-toolchain` names (with elan, `lake` and `lean` come from it), Python 3, and
bash with `zcat`. From the repository's top:

    bash formal/twin/check.sh            # ends "check.sh: PASS"
    bash formal/twin/check.sh --help     # its options; the steps are described at the top of the script

It builds the twin from nothing into `formal/twin/out/check/` and writes nothing outside it. Its steps:

- **build**: a copy of the twin's sources, built with `lake build replay`;
- **selftests**, **tables**: the tools' own cases, the generated Lean held to its schema, the tracer's views held
  to their contract;
- **scope**: the table above, held to the document;
- **mutants**: each mutant's text stands in the twin once, and each type-checks;
- **screen**: the first lines of every cell's trace, under both documents, read by the replay;
- **cells**, **small**, **directed**: the toy's cell `none`, small hand runs (under both documents) and directed
  sets (states generated to reach what the cells do not, with the functions called on them) traced and replayed;
  a traced run's digest must be the untraced run's, and `none`'s the toy's `golden.txt`;
- **replays**, **headers**: every replay read its trace to the end with no record mismatched and no read of the
  Python's left unmade, and every trace names the tree it was made from;
- **picks**: the replay's choice of records where the node may replace a function with its own, and a directed
  set's draw;
- **controls**, **perturbed**: checks that must fail, each for its own reason: a mutant replayed, altered records
  and headers, a trace cut short, a trace of another tree, a tracer that perturbs what the toy reads.

`record.sh` is `check.sh --record`: every cell, under both documents, with more controls, hours on a server.

A trace's first line names the documents, the toy and the tools it was made from, each by its sha256. A checkout
that changes line endings (CRLF) changes every such hash.

## Layout

- `SpecTwin/`: the twin, and `Replay.lean`, which reads a trace's records;
- `Main.lean`: the replay, the executable a trace is piped through;
- `tools/`: the tracer, the mutants, the directed sets and the checks of the checks (`tools/README.md`);
- `check.sh`, `record.sh`.
