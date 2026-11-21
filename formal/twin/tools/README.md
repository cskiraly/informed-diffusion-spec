# The tools of the Lean twin

The tools in this directory trace runs of the toy for the Lean twin to replay, and check that the replay tells a
wrong twin from the right one. `../check.sh` runs them together. The head of each file says what the file does and
what it does not see.

The content line is the first line of a trace (`content.py`). It names what the trace is made from: each document
by the sha256 of its code, which is the text that the toy's `extract.py` makes of it, and each file of the toy and
of this directory by the sha256 of its bytes. A file whose name ends in `.md`, this one included, is prose, and
the line does not name it; nor does it name a directory called `__pycache__`. So an edit of a document's code (a
heading over a code block included), or of any file here but a README, makes every earlier trace a trace of
another tree, and the traces are made again. An edit of a document's other prose, or of a README, does not.

## What each file is

| file | what it is |
|---|---|
| `layout.py` | where things are, from the place of this directory; the command that starts a tracer's Python |
| `content.py` | the content line: each document by its code, each file of the toy and of the tools by its bytes, with `.md` files and `__pycache__` left out; the two hashes of a trace: of the whole trace, and of its body, the trace from its second line on |
| `trace3.py` | the tracer, which writes one record per top-level call of a traced function, with what the call read and wrote |
| `trace61.py` | the base class and the encodings of the tracer; the names of §6.1 |
| `footprint.py` | the recording views that the tracer wraps the toy's tables in |
| `gen/schema.py` | the tables of the twin, in one schema, from which both the tracer and the generated Lean of the twin come |
| `gen/gen.py`, `gen/makers.py` | the generated Lean files, held to the schema (`gen.py`); where the built replay makes a `Tables` value (`makers.py`) |
| `cells3.py` | the toy's cells (those of its `check.py`), traced and replayed; the header and the nodes line of each |
| `header3.py` | the check that the first line of a trace is the content line of this tree, and that its header is of a known kind |
| `directed*.py` | the directed sets: the toy's own functions called on generated states. There are 22 sets. `directed3.py` runs the samples of `directed61.py`, `directed44.py` runs with and without its limits, and `directed7.py` runs three ways |
| `mutants3.py` | the mutants (twins with one rule changed, in the lists below), built and replayed; a matrix made in parts, read as one (`--merge`); the run of a draft (`--sample drafts`). `--sample-make` makes `sample_drafts.txt` from a matrix, and `--sample-check` checks it |
| `sample_drafts.txt` | the sample for drafts, each mutant with its reason. On the cells, the run of a draft replays these mutants alone; on the directed sets, it replays every mutant |
| `against.py` | the manifest of a run against that of a record, with one of three results: as recorded; another content and the same bodies; or not the record's. `--matrix`: the traces of a matrix against those of a record, by body. `--bodies`: every trace of two manifests, by body, both ways, counted by directory (also for a record of an earlier kit). `--bodies-in`: each trace of a list of hashes against a record, by body |
| `matrixdiff.py` | two merged matrices of the same mutants, compared pair by pair: what each tells, and what one tells that the other does not. `--common` compares them over the mutants that both have, where one has mutants added or dropped |
| `fullid.py` | how many records of a trace hold a full id (56 bytes) outside the places where a chunk's own id stands by design |

Each of these controls must give the result written for it. Most must fail, each for its own reason:

| file | what it controls |
|---|---|
| `altered3.py` | the comparisons of the replay: records, content lines, headers and nodes lines, altered one member at a time |
| `contentcontrols.py` | the content line: a trace of another tree, and a tracer started so that what runs need not be what the line names, which must fail; and the same tree traced from another place, a bytecode file planted beside a source of the toy, a planted module on `PYTHONPATH`, which the isolated tracer does not load, and edits of prose and of READMEs, which must leave the trace as it was, so that the replay passes it |
| `perturb3.py` | the claim that the tracer perturbs nothing: a tracer whose view changes what the toy reads |
| `tracerfaults3.py`, `unlogged3.py` | the checks that the tracer makes of its own log: faults planted in a run |
| `footprint_test.py` | the contract of the views, one case for each of its lines |
| `fixcontrols.py` | the replay's choice of records for a name that the node has replaced; the draw of a directed set |
| `commentsonly.py` | a change of the twin or the tools that claims to touch comments only |

## The lists of mutants

In `mutants3.py`, `MUTANTS` puts these lists together. A list's name says nothing of what the list holds; the
table does.

| list | where | what its mutants change |
|---|---|---|
| `MUTANTS` of `mutants.py` | `mutants.py` | the functions of §6.1, one rule each. `mutants3.py` restates some of these mutants on the interface of the tables (`MOVED`), and one as a change of the tables (`IN_TABLES`) |
| `NEW` | `mutants3.py` | §6.1 once more (`may_ask`, `ask_parked`, `announcers`, `untried`): a read or a write beyond those of the Python; and operations of its tables that do more, do less, or note nothing |
| `SLICE1` | `mutants3.py` | §4.4 and §6.2 |
| `V010` | `mutants3.py` | `valid_id` of §4.4, and a bitmap's `valid_have` |
| `SLICE2A` | `mutants3.py` | §4.2 |
| `QMOVE` | `mutants3.py` | the twin's own queue, and more of §4.2 |
| `AEND` | `mutants3.py` | `outstanding` of §6.1, the deferred chunks of §4.2, and the writer of §7.2 |
| `GA5` | `mutants3.py` | more of the deferred chunks of §4.2 and of the writer of §7.2 |
| `CYCLE1` | `mutants_c1.py` | §1 to §3, §4.1, §4.3, §4.5, §4.6, §6.2, §6.4 and `drop_offer` |
| `CYCLE2` | `mutants_c2.py` | §5 and §7.1, and more of the functions above |

`python3 mutants3.py --places --twin ..` checks that the text of every mutant occurs once in the twin, in the
function that its description names. `LEFT` in `mutants3.py` keeps, as text and with the reason, three changes
that no record tells apart from the twin; no list includes them.
