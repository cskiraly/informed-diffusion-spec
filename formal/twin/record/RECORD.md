# The record of the Lean twin

This file describes the record of the Lean twin that the spec carries from version 0.10.9. It says what
ran, what the runs show, and what they do not show. The other files in this directory, but for `FILES.sha256`,
are the outputs of the runs: the manifest of the traces, the reports of the replays, the matrix of mutants, and
the reports of the controls, with the log of the script that started the quick check. Each is as the runs wrote
it, but for one substitution in four files, which the end of this file names. `FILES.sha256` was made when the
record was frozen, and it gives the SHA-256 hash of every other file in this directory, this file included. The
traces themselves are not kept, because they take about 50 GB uncompressed (`manifest/sizes.txt`). `record.sh`
makes them again, and the hashes in the manifest tell whether a new run made the same traces.

This file uses the terms of the twin's README (`../README.md`). The toy (`toy/`) runs the Python in the code
blocks of the documents directly. The tracer runs the toy and writes a trace: one record for each top-level call,
at a node, of a traced function, unless the node replaces that function with its own. The traced functions are
among those that the twin covers, and the header of a trace names them. A record holds what the call read and
wrote in the node's own tables, the tape, and what the call returned or raised. The tape holds, in order, what the
call asked of the rest of the node and the answers, among them the reads that its own code makes of tables that
are not the twin's, and the orders of rows that the twin asks for. The replay (`Main.lean`) replays each record
through the twin. A cell is one of the small runs of the toy that `toy/check.py` names, and its digest is a
SHA-256 hash of every event that the run processes; the golden files hold its first 16 hex digits. A directed
set is a set of generated states, made to reach what the cells do not, with the toy's own functions called on
them. A mutant is a copy of the twin with one rule changed. Traces tell a mutant from the twin when the replay
through the mutant mismatches a record, or leaves unmade a read that the Python made.

## What ran

- **One commit supplied everything.** Every run below started from a fresh clone of the spec at commit `69b5952`,
  with nothing added to it. That commit is in the published history of the spec, before the commit that adds this
  record. It holds the two documents (`protocol.md` and `protocol-v2.md`), the toy, the twin in `formal/twin`, and
  the twin's tools. Its toy is this release's, and its documents differ from this release's only outside their
  code.
- **The content line and the list of the sources of the twin tie the record to what ran**
  (`manifest/content.line`, the first line of every trace, and `manifest/twin-sources.txt`; the content line is
  described below). Both are made from the files of a tree, and a reader can make both on any tree:
  `tools/content.py` makes the content line, and the build step of `check.sh` writes the list of the sources of
  the twin, each with its SHA-256 hash. This release holds the same `toy/` and `formal/twin/` as `69b5952`, file
  for file, apart from `formal/twin/record/`. Run on the tree of this release, `tools/content.py` gives the line
  in `manifest/content.line`. The sources of the twin there, by path and hash, are those that
  `manifest/twin-sources.txt` lists.
- **These files show the clone and the toolchain of some of the runs.** The record's Lean is in
  `controls/check.txt` and its Python in the manifest. The quick check's clone, Lean and Python are in
  `quick-check/run.log`. The clone of the record's run, and the clone, Lean and Python of each part of the matrix,
  are in the logs of the script that started each run, which are not among these files.
- **The toolchain** was Lean 4.35.0 (commit `eb6cafb7290e8bd5f2937522d8d804f58f02bafc`). The record ran under
  Python 3.12.3.
- **The platform** was x86-64 Linux.
- **The record's run was one run of `record.sh`,** with all its steps. `record.sh` runs `check.sh --record`, which
  traces and replays every cell of `toy/check.py` under both documents, and adds the controls that only the record
  runs. The run passed: the last line of its output is "check.sh: PASS (the record's run)" (`controls/check.txt`).
- **The quick check passed too.** `check.sh` alone passed in a run of its own from a fresh clone of `69b5952`
  (`quick-check/check.txt`, and `quick-check/run.log`, the log of the script that started that run).

## What it shows

- **The record made 55 traces** (`manifest/record-manifest.txt`): the 15 cells under `protocol.md`, three traces
  of small hand runs (`hand5`, `hand5-publish` and `hand5-sec61`), the 22 directed sets, and the 15 cells under
  `protocol-v2.md`. The manifest names each trace by two SHA-256 hashes of its uncompressed bytes: one of the
  whole trace, and one of its body, which is the trace from its second line on. The manifest also gives the
  SHA-256 of the replay, of the sources of the twin, and of the names of the mutants in the order of
  `tools/mutants3.py`. The record also made and replayed three small traces that are not in the manifest:
  `late16`, and `hand5` and `hand5-own` under `protocol-v2.md`. That makes 58 traces, and `replays/` holds the
  report of the replay of each.
- **The content line** (`manifest/content.line`) is the first line of every trace. It names each document by the
  SHA-256 of its code, and each file of the toy and of the tools by the SHA-256 of its bytes. The code of a
  document is what `toy/extract.py` makes of it: every `python` block of the document, in order, each under the
  heading of the section that holds it. The files of the toy and of the tools whose names end in `.md`, and the
  directories named `__pycache__`, are not in the line. Every other file under the toy and the tools is in it,
  committed or not, and a link among them is refused. So a change to a document outside its code, or to a README,
  leaves the content line as it was, and a change to the code changes it. The manifest also gives the SHA-256 of
  the bytes of each document, in its `documents` line. Those hashes are of the documents at `69b5952`. If a
  document of this release differs from its counterpart at `69b5952` only outside its code, the SHA-256 of its
  bytes is not the one in the `documents` line, and the SHA-256 of its code is still the one in the content line.
  The `documents` line is for information: `tools/against.py`, which compares a new run with this record, reports
  a difference in it and decides nothing by it.
- **The twin replayed every record of the 58 traces with no mismatch** (`replays/`). It also made every read of
  the Python that the records hold.
- **In 36 traces, tracing left the first 16 hex digits of the digest as they were.** For each of the 30 cells,
  they are the ones in the golden file of its document (`controls/cells.txt`, `controls/cells-v2.txt`). For each
  of the six small traces, the three hand traces and the three outside the manifest, they are the ones that the
  untraced run with the same arguments gives (`controls/digests.txt`). A directed set has no digest, so nothing
  compares its run with an untraced one.
- **Traces made again, each in a new Python process with hash randomization on, had the same bytes.** The record
  made each of the 22 directed sets twice more, and two cells (`withholders` and `loss-thin`) once more. That is
  46 traces made again from 24, and each had the same bytes as the first trace (`controls/same-content.txt`).
- **Every function of `protocol.md` has its twin.** Each of the 78 functions defined in the code blocks of
  `protocol.md` has a twin under the same name: an `enter` of that name in the twin, and a case for it in the
  replay (`controls/scope.txt`). The twin also replays one function of the toy, `held`, that no code block of
  `protocol.md` defines.
- **Every control gave the result written for it** (`controls/`). Most controls must fail, each for its own
  reason, and each of them failed:
  - a mutant that compiles is told from the twin by a mismatched record;
  - the replay refuses records, headers (the second line of a trace) and nodes lines (the third) altered in the
    ways that must fail;
  - the replay refuses a trace cut short;
  - the replay refuses a trace made after a change to the code, and names the file that changed
    (`controls/c-content.txt`). The changes tried are a statement, a comment in a block, the heading over a block
    and a fence, each changed in a document; a file of the toy and a tool, each with other bytes; and a file added
    to the toy and one taken from it;
  - the tracer stops at each start that must fail, and says why. Under a Python that does not run isolated or
    writes bytecode, or with no bytecode prefix set or one that holds a file, code other than what the content
    line names could run. Under a Python that runs optimised, the assertions of the tracer would not run. A dump
    of a topology is an input that the content line does not name, and the cross-check recorder is refused too. A
    document given in a form that the toy and the header of the trace would read differently (twice, under two
    names) is refused as well;
  - a tracer that changes what the toy reads changes the digest of a cell;
  - the check of the twin's tables fails on each change planted for it, except two that its controls keep as known
    limits. It checks that each of the three generated files of the twin is, byte for byte, what
    `tools/gen/gen.py` makes from the schema of the tables (`tools/gen/schema.py`). It searches the Lean written
    by hand for a declaration of one of 16 names that the generated files declare (`NAMES` in `gen.py`), and the
    two limits are declarations that this search misses. It also checks that the instance of `Tables` (the
    interface through which the twin reaches its tables) in the replay is the fixed text. The check that lists
    what makes a `Tables` value in the built replay fails on each change planted for it;
  - each broken version of the tracer's views (the wrappers through which it logs the accesses to the toy's
    tables) fails as many of its own cases as written for it (`controls/views-controls.txt`). In
    `controls/views-stubs.txt`, each of the three lines marked "<-- NOT" reports a stub of the test that fails in
    another way than the test does, and the line after it says that the stub was refused, as it must be;
  - a tracer whose views let an assignment through without logging it stops, and so does a tracer with each
    fault planted in it.

  The other controls must pass, and each passed. A change to the prose of a document, to its version line or to a
  heading with no code under it, and a change to a README of the toy or of the tools, leave the content line as it
  was. The trace made after such a change has the same bytes as the first trace, and the replay passes it. The
  same holds for a copy of the tree traced from another directory. With a bytecode file of other code planted
  beside a source of the toy, which the Python of the tracer does not run, and with a module planted on
  `PYTHONPATH`, which the isolated tracer does not load, the tracer also writes a trace with the same bytes as the
  first (`controls/c-content.txt`).
- **The matrix covers 562 mutants** (`matrix/`). `matrix/mutants.sha256` holds the hash of the replay built for
  each. Each mutant was built and replayed on the records that reach its function or touch its table, and, for a
  function that a node may replace, on the records that ask it on the tape. Those records were taken from the 22
  directed sets and from the traces of the 15 cells under `protocol.md`, `hand5` and `hand5-publish`. **The
  directed sets tell all 562 mutants from the twin:** 556 by a mismatched record, and 6 only because the mutant
  left unmade a read that the Python made. **The 15 cells tell 386, and with the two hand traces 392:** 381 by a
  mismatched record, and 11 only by reads left unmade. The directed sets are the only traces that tell the other
  170. Two reports, `matrix/mutants-directed.txt` and `matrix/mutants-cells.txt`, give the counts of each mutant
  and, where records mismatch, up to two example records. The two pairs files, `matrix/mutants-directed-pairs.txt`
  and `matrix/mutants-pairs.txt`, hold one line for each pair of a mutant and a trace, and the counts in the
  reports follow from them.

## How the matrix is tied to this record

The matrix ran in five parts, each from a fresh clone of `69b5952`, and the outputs of the five were merged into
one (`matrix/PARTS`). The parts ran under the same Lean as the record, and under Python 3.13.5 (parts 1, 2 and 5)
and 3.12.3 (parts 3 and 4); the logs that show the clones and the toolchains are not among these files. Four facts
in these files tie the matrix to this record:
- It has the content line of this record (`matrix/content.line` and `manifest/content.line`).
- Its 39 traces have the same hashes as in the manifest, of the body and of the whole trace
  (`matrix/traces.sha256` and `matrix/directed.sha256`).
- Its replay has the same SHA-256 as the replay of this record (`matrix/replay.sha256`).
- Its 562 mutants have the same names as the mutants of this record, in the same order (`matrix/mutants.sha256`;
  the manifest's `mutants` line is the SHA-256 of those names, one to a line, with no line end after the last).
  Its sources of the twin are the same files (`matrix/twin-sources.txt` and `manifest/twin-sources.txt`).

## What it does not show

- **It does not cover all inputs.** A replay is evidence about the scenarios that were traced. If the Python has a
  bug, a faithful twin copies it, so the replay checks the copying and not the rules.
- **The trace gives the twin some things that the twin does not compute.** Each call starts from the state that
  the trace recorded. The trace answers the calls to the helpers that `protocol.md` names but does not write out,
  among them the hash, serialization, compression, code and tree of §1. It also answers the calls to a function
  that a node replaces with its own. Where the twin asks for the order of the rows of its own tables, the tape
  gives that order, and the replay checks only that it is a permutation of the rows.
- **The twin does not model everything in the documents.** It does not model the events that `protocol.md` gives
  in prose: a connection that closes, the offers of an announcer that age out, and a group that expires. Nor does
  it model the functions of `protocol-v2.md`: a trace under that document records only some of the functions of
  `protocol.md` that `protocol-v2.md` keeps, and the toy's `held`.
- **The replay can miss a change in when, or how often, the twin reads or writes its own tables.** It checks which
  entries the twin read and scanned, what the twin wrote, and the state at the end of the call, against the
  record. It checks the order of some accesses. The calls on the tape must come in the recorded order. A call on
  the tape that logged what it read must find those values in the state of the twin when it is made. The twin may
  read an entry that the Python did not read only after writing it. Beyond such checks, a read of the twin's own
  tables made at another point in the call, or made once where the Python makes it twice, can pass. Suppose a
  function calls the rest of the node, that call writes an entry of the twin's own tables, and the code of the
  function also reads that entry. Then a twin that reads the entry after the call, where the Python reads it
  before, is not refused unless the value it reads changes what the replay compares. `wake` is a call on the tape
  that carries no log of its own and writes none of the twin's tables: it only schedules the node's writer for the
  peer and notes it as scheduled, unless it already is. So a twin that calls `wake` before a write of its own,
  where the Python calls it after, can pass: in `owe`, for example, a `wake` moved to just before the write to
  `owed` leaves the tape and everything else that the replay compares as it was. The twin calls `wake` in two
  functions, `owe` and `wake_front`, and every other function that reaches it does so through one of them.
  `acquire_slot`, `release_unused_slot`, `free_slot` and `write_waits` call `wake_front`, and `next_to_send`
  reaches it through `acquire_slot`, `release_unused_slot` and `track_in_flight`, whose second copy of a chunk in
  flight gives its slot back at once through `free_slot`. `unpush`, `announce`, `push_rebuilt` and `forward` call
  `owe`, and `next_to_send` reaches `unpush` through `filter_entry`.
- **The tracer does not see every access.** It may miss a change that is made in place and undone between two of
  its observations. It does not see an access through a container kept from outside the call, an in-place change
  to the values of another section, an object reached by a second path, or some tests of whether a row is present.
  Its check of the whole state runs only in the directed sets, whose records hold the whole state. There it
  checks, at the two ends of a call, that its log accounts for the state of the twin's own tables, and it cannot
  recover those accesses. In the traces of the cells and of the small runs, nothing compares the log of the tracer
  with the tables. An entry that is present and empty counts as missing, except where the schema keeps empty
  values, as it does for `tied`, the lanes of the queue and `origin`.
- **A pop that finds nothing** is recorded as a read and no write. The twin still erases at those places, and the
  replay allows that, since erasing a missing entry changes nothing. More generally, the replay allows a write by
  the twin that the Python did not make, where the Python read the entry and the twin leaves it at the value read.
- **The tracer refuses some runs, and a record holds some values in part.** The tracer stops a run when a value
  that it is to record is one that a record cannot hold. Among such values are a frame with a PRUNE, a GRAFT or a
  JOIN; prunes of the stock, where a traced call receives them or the stock answers with them; a control message
  in the queue of a kind that a record cannot hold (an empty PRUNE it can); an answer of `installed_block` that is
  neither a block nor nothing, or that says, within one record, that a block of one slot and root is there and
  that it is not; and a `KeyError` on a key that is not a peer. A value that the tracer does not record stops
  nothing: in a run that traces §6.1's functions alone, as that of `hand5-sec61` does, `on_frame` is not traced,
  and a frame with a PRUNE does not stop the run. Where a record holds the data of a chunk or the body of a
  payload, it holds them as their length and the toy's tag, not as their bytes. Some records, such as those of
  `forward`, hold a chunk without its data. Where a traced call raises, the replay compares the kind of the
  exception and, for a `KeyError`, its key, which is a peer, and not its message.
- **The twin narrows the Python in three places,** as its sources say:
  - the id of an ask always has a group and an index, and the tracer refuses an IWANT id that is neither a request
    by index nor a structured id of 56 bytes;
  - the recursion of `defer` through `on_validated` and the loops of `on_pace_tick` and of `next_to_send` are
    bounded. Past a bound, the twin stops with a crash, which the replay reports as a mismatch. For `defer`, the
    tracer stops first, at a chain of three calls in one record;
  - where `origin_acked` looks up a group that has no row in `planned`, the twin reads none and the Python raises
    an error.
- **Some cases that the sources name are in no record of the 58 traces:** `decode_group` with no descriptor;
  `origin_acked` on a group that is in `planned` and not in `origin`; `publish` with a descriptor of no chunk, or
  of more chunks than the shards give; and `on_block_installed` with no group committed.
- **Three changes that the traces are not expected to tell from the twin** are kept as text in
  `tools/mutants3.py`, under `LEFT`, each with its reason. They are not among the 562, and this record did not
  replay them.
- **The record does not link the twin to the Veil models.** That the twin refines them is not part of this record.
- **The cells and the two hand traces tell 392 of the 562 mutants.** Only the directed sets tell the other 170. No
  mutant was replayed on a trace under `protocol-v2.md`, on `hand5-sec61` or on `late16`.

The files are as the runs wrote them, but for one substitution in four of them. `controls/check.txt` and
`quick-check/check.txt` name the directory of the toy in their runs, and `controls/headers.txt` names the paths of
the traces of the record's run. In these three files, the directory of each run on the machine where it ran is
written `RUN`. `quick-check/run.log` names the machine of the quick check, and its name is written `HOST`. Every
other byte of these four files, and every other file but `FILES.sha256`, is as the runs wrote it.
