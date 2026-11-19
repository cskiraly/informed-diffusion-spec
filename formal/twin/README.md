# The Lean twin of `protocol.md`'s Python (draft)

**This is a draft.** What this commit shows is that `check.sh` passes at this commit, and nothing more. The
record that shows more (below) follows in a later release.

The twin is a transcription of the Python in `protocol.md`'s code blocks into Lean 4, function by function, with
the same branches, but for narrowings its sources name: an ask's id always has a group and an index (the tracer
refuses any other id); and three recursions or loops are bounded (`defer` through `on_validated`; `on_pace_tick`'s
turns, by the jobs at entry; `next_to_send`'s turns), past which the twin stops with a crash that the replay
reports as a mismatch. Some of its tables have a form of their own. It is executable, not an abstract model. On
its own it proves nothing. Its value is that it can be checked against the Python on one side, which this
directory does, and linked to the Veil models on the other, which it does not do yet.

## How it is checked: trace replay

A tracer runs the toy (`toy/`), which runs `protocol.md`'s code blocks directly. For every top-level call of a
covered function (one called from inside another is part of its caller's record) it logs what the call read and
wrote of the node's own tables, what it asked of the rest of the node and what it returned. The twin replays each
call from the logged state, with the logged answers, and must read what the Python read (which entries, not how
often or in which order), write what it wrote and return what it returned. Mutants, twins with one rule changed,
are there to show whether the traces are strong enough to tell a wrong twin from the right one: `check.sh` replays
one as a control, and the matrix of all of them is part of the record (below).

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

That is 75 functions; the other sections (§0, §6.3, §7.3, §8, §9) define none. The twin also replays `held`, the
toy's reader of what a node holds (whether a chunk is in §4.2's `mine`), which the code of §4.4, §6.1 and §7.2
calls. The files of `SpecTwin/` are named for parts of the document, not one to one with its sections.

Not in the twin:
- the helpers `protocol.md` names but does not write out (`resolve`, `chunk_of` and the like): the replay answers
  them from the trace;
- the events it gives in prose: a connection's close, an announcer's offers ageing out, a group's expiry;
- `protocol-v2.md`'s own functions: a trace of a cell under `protocol-v2.md` replays through the functions of
  `protocol.md` that it keeps.

## What is not here yet

- **The record**: every trace of every cell of the toy's `check.py` under both documents, the directed sets, and
  the mutants' matrix, which shows which mutants the traces it replays (the cells under `protocol.md`, two hand
  traces and the directed sets) tell from the twin. `record.sh` makes the traces, and `record.sh --matrix K/N`
  each part of the matrix (`tools/mutants3.py --merge` reads the parts as one); it follows in a later release.
- **The link to the Veil models** (`formal/veil/`): a refinement from the twin to the models, under way, is not in
  this repository.

## Running it

It needs Lean 4 at the version `lean-toolchain` names (with elan, `lake` and `lean` come from it), Python 3, and
bash with `zcat`. From the repository's top:

    bash formal/twin/check.sh            # ends "check.sh: PASS"
    bash formal/twin/check.sh --help     # its options; the steps are described at the top of the script

It builds the twin from nothing into `formal/twin/out/check/` and writes its output there; two tools' self-tests
write fixtures to the system's temporary directory (`content.py` removes its own; `matrixdiff.py` leaves them).
Its steps:

- **build**: a copy of the twin's sources, built with `lake build replay`;
- **selftests**, **tables**: the tools' own cases, the generated Lean held to its schema, the tracer's views held
  to their contract;
- **scope**: every function of the document's code blocks has its twin, by name, and a case of the replay's; it
  prints the count by section (the table above);
- **mutants**: each mutant's text stands in the twin once, and each type-checks;
- **screen**: every cell's header and nodes line, under both documents, read by the replay (each cell traced with
  no message published, for those two lines);
- **cells**, **small**, **directed**: the toy's cell `none` (under `protocol.md`), small hand runs (under both
  documents) and directed sets (states generated to reach what the cells do not, with the functions called on
  them) traced and replayed; `none`'s digest must be the toy's `golden.txt`'s, and each small run's that of the
  same run untraced;
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
