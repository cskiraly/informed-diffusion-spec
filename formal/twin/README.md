# The Lean twin of the Python in `protocol.md`

This directory holds an executable Lean 4 twin of the Python in the code blocks of `protocol.md`. The twin is a
transcription of that Python, function by function. It is not an abstract model, and on its own it proves nothing.
Its value is that it can be checked against the Python, which this directory does by trace replay (below), and
linked to the Veil models, a link that `formal/refine/` begins (below).

The record of the twin is in `record/`. It shows that the twin replays the traces of the toy's cells, of the hand
runs and of the directed sets with no mismatch, and which mutants of the twin part of those traces tell apart from
it (below). `record/RECORD.md` says what the record ran, what it shows and what it does not show.

The twin has the same branches as the Python, with these restrictions, which its sources name:
- An ask is an IWANT for one chunk. In the twin, an ask's id always has a group and an index; the tracer,
  described below, refuses any other id.
- Three recursions or loops are bounded: the recursion of `defer` through `on_validated`, the loop of
  `on_pace_tick`, and the loop of `next_to_send`. The number of jobs at entry bounds the loop of `on_pace_tick`.
  If a run passes a bound, the twin stops with a crash, which the replay reports as a mismatch.

Some tables use representations specific to the twin.

## How it is checked: trace replay

A tracer runs the toy (`toy/`), which runs the code blocks of `protocol.md` directly. The tracer writes one record
for each top-level call of a function that the twin covers; a call of such a function from inside another such
function is part of the record of its caller. A record holds what the call read and wrote in the node's own
tables, what it asked of the rest of the node, and what it returned. The twin replays each call from the recorded
state, with the recorded answers. It must read the same entries as the Python, though not necessarily as often or
in the same order; it must write what the Python wrote and return what the Python returned.

A mutant is a twin with one rule changed. The mutants are there to show whether the traces are strong enough to
tell a wrong twin from the right one. `check.sh` replays one mutant as a control and requires the replay to tell
it apart from the twin. The matrix of all the mutants is part of the record (below).

The replay is evidence about the scenarios traced, not about all inputs. If the Python has a bug, a faithful twin
copies it: the replay checks the copying, not the rules.

**The replay has a known blind spot.** A trace records what a call read and wrote, but not when, within the call,
each access happened. Suppose a function's own code reads an entry of the twin's own tables, and the function also
asks the rest of the node to do something that writes that entry. If the Python reads the entry before it asks
and the twin reads it after, the replay detects the difference only if the value read changes something that the
replay compares.

## Scope

Every function that the code blocks of `protocol.md` define has a twin of the same name. The `scope` step of
`check.sh` checks this against the document: for each `def` named `NAME`, there must be an `enter "NAME"` in
`SpecTwin/` and a case for `NAME` in the replay. The table counts the functions by section:

| § | functions | § | functions | § | functions |
|---|---|---|---|---|---|
| 1 | 7 | 4.4 | 4 | 5.4 | 1 |
| 2 | 1 | 4.5 | 1 | 6.1 | 14 |
| 3 | 2 | 4.6 | 4 | 6.2 | 1 |
| 4.1 | 2 | 5.1 | 4 | 6.4 | 3 |
| 4.2 | 12 | 5.2 | 5 | 7.1 | 8 |
| 4.3 | 1 | 5.3 | 2 | 7.2 | 5 |

That makes 77 functions. The other sections (§0, §6.3, §7.3, §8, §9) define none. The twin also replays `held`, a
function of the toy that says what a node holds: whether a chunk is in `mine` (§4.2). The code of §4.4, §6.1 and
§7.2 calls `held`. The files of `SpecTwin/` are named for parts of the document; they do not follow its sections
one to one.

- The twin leaves out the helpers that `protocol.md` names but does not write out, such as `resolve` and
  `chunk_of`. The replay answers calls to them from the trace.
- The twin leaves out the events that `protocol.md` gives in prose: a connection closing, an announcer's offers
  ageing out, and a group expiring.
- The twin leaves out the functions specific to `protocol-v2.md`. A trace of a cell of the toy under
  `protocol-v2.md` replays through the functions of `protocol.md` that `protocol-v2.md` keeps.

## The record

The record (`record/`) holds outputs of one run of `record.sh`, and the matrix of the mutants, which runs of its
own make. It names every trace of every cell of the toy's `check.py` under both documents, the hand traces and the
directed sets, each by its hashes; the traces themselves are not kept. A directed set is a set of generated
states, made to reach what the cells do not, with the toy's own functions called on them. The record also holds
the reports of the replays and of the controls. The matrix shows which mutants the replay tells apart from the
twin on the cells under `protocol.md`, two hand traces and the directed sets. `record.sh` makes the traces again,
and `record.sh --matrix K/N` makes each part of the matrix; `tools/mutants3.py --merge` reads the parts as one.

## The link to the Veil models

A refinement from the twin to the Veil models (`formal/veil/`) is under way. A first piece of it is in
`formal/refine/`, and its README states the piece's scope.

## Running it

`check.sh` needs Lean 4 at the version that `lean-toolchain` names, Python 3, and bash with `zcat`. With elan,
`lake` and `lean` come from that version. Run it from the top of the repository:

    bash formal/twin/check.sh            # ends "check.sh: PASS"
    bash formal/twin/check.sh --help     # its options; the steps are described at the top of the script

By default, `check.sh` builds the twin from scratch into `formal/twin/out/check/` and writes its output there. The
self-tests of two tools write fixtures to the system's temporary directory: `content.py` removes its own, and
`matrixdiff.py` leaves its fixtures there. `check.sh` runs these steps:

- **build** builds a copy of the twin's sources with `lake build replay`.
- **selftests** runs the tools' own cases.
- **tables** checks that the generated Lean matches its schema, and tests the tracer's views against their
  contract.
- **scope** checks that every function of the document's code blocks has a twin of the same name and a case in
  the replay, and prints the count by section (the table above).
- **mutants** checks that the text of each mutant occurs once in the twin, and that each mutant type-checks.
- **screen** traces every cell, under both documents, with no message published, to get its header and its nodes
  line; the replay reads those two lines.
- **cells** traces and replays the toy's cell `none` (under `protocol.md`); its digest must be the one in the
  toy's `golden.txt`.
- **small** traces and replays small hand runs (under both documents); the digest of each must be that of the
  same run untraced.
- **directed** traces and replays the directed sets.
- **replays** checks that every replay read its trace to the end, with no record mismatched, and made every read
  that the Python made.
- **headers** checks that every trace names the tree it was made from.
- **picks** checks the replay's choice of records where the node may replace a function with its own, and the
  draw of a directed set.
- **controls** and **perturbed** run checks with a result written for each. Most must fail, each for its own
  reason: they replay a mutant, alter records and headers, cut a trace short, use a trace of another tree, and run
  a tracer that perturbs what the toy reads. A few of the content line's controls must pass instead, each leaving
  the trace as it was: the same tree traced from another place, a bytecode file planted beside a source of the
  toy, a planted module on `PYTHONPATH`, which the isolated tracer does not load, and edits of prose and of
  READMEs.

`record.sh` runs `check.sh --record`. It covers every cell, under both documents, with more controls, and takes
hours on a server.

The first line of a trace names what the trace was made from: each document by the sha256 of its code, which is
the text that the toy's `extract.py` makes of it, and each file of the toy and of the tools by the sha256 of its
bytes. Files whose names end in `.md`, and directories named `__pycache__`, are left out. The prose of a document
is not named either, but a heading over a code block is part of the document's code. A checkout that changes line
endings (CRLF) changes the hash of each file whose bytes it changes, but not the hash of a document's code:
`extract.py` reads a document as text, which turns CRLF into LF.

## Layout

- `SpecTwin/` holds the twin, and `Replay.lean`, which reads the records of a trace.
- `Main.lean` is the replay: the executable that a trace is piped through.
- `tools/` holds the tracer, the mutants, the directed sets and the checks of the checks (`tools/README.md`).
- `record/` holds the record (`record/RECORD.md`).
- `check.sh` runs the quick check; `record.sh` runs `check.sh --record` (above).
