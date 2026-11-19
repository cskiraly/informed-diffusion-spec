# The twin's tools

What traces the toy for the Lean twin's replay, and what checks that the replay tells a wrong twin from the right
one. `../check.sh` runs them together; each file's head says what it does and what it does not see.

Every file here is named in a trace's content line (`content.py`), this one too: an edit of any of them makes
every earlier trace another tree's, and the traces are made again.

## What each is

| file | what it is |
|---|---|
| `layout.py` | where things are, from this directory's own place; the command a tracer's Python is started with |
| `content.py` | the content line: what a trace is made from, each file by its sha256; a trace's two hashes |
| `trace3.py` | the tracer: one record per top-level call of a traced function, with what it read and wrote |
| `trace61.py` | the tracer's base class and encodings; §6.1's names |
| `footprint.py` | the recording views of the toy's tables, which the tracer wraps them in |
| `gen/schema.py` | the twin's tables: one schema, which the tracer and the twin's generated Lean both come from |
| `gen/gen.py`, `gen/makers.py` | the generated Lean files held to the schema; where a `Tables` value is made |
| `cells3.py` | the toy's cells (its `check.py`), traced and replayed; the header and nodes line of each |
| `header3.py` | a trace's first line is this tree's content line, and its header is of a known kind |
| `directed*.py` | the directed sets: the toy's own functions called on generated states (22 sets: `directed3.py` runs `directed61.py`'s samples, `directed44.py` runs with and without its limits, `directed7.py` three ways) |
| `mutants3.py` | the mutants: twins with one rule changed, built and replayed (the lists below); a matrix in parts, read as one (`--merge`) |
| `against.py` | a run's manifest against a record's: as recorded; another content and the same bodies; or not the record's. `--matrix`: a matrix's traces against a record's, by body. `--bodies`: every trace of two manifests by body, both ways, counted by directory (a record of an earlier kit too). `--bodies-in`: each trace of a list of hashes, by body |
| `matrixdiff.py` | two merged matrices of the same mutants, pair by pair: what each tells, what one tells that the other does not |
| `fullid.py` | how many records of a trace hold a chunk's full id outside the places one stands by design |

The controls, each of which must fail for its reason:

| file | what it controls |
|---|---|
| `altered3.py` | the replay's comparisons: records, content lines, headers and nodes lines altered one member at a time |
| `contentcontrols.py` | the content line: a trace of another tree, and a tracer started so that what runs need not be what the line names |
| `perturb3.py` | "the tracer perturbs nothing": a tracer whose view does perturb |
| `tracerfaults3.py`, `unlogged3.py` | the tracer's checks of its own log: faults planted in a run |
| `footprint_test.py` | the views' contract, a case a line |
| `fixcontrols.py` | the replay's pick of a replaced name's records; a directed set's draw |
| `commentsonly.py` | a change of the twin or the tools that claims to touch comments only |

## The mutants' lists

`mutants3.py`'s `MUTANTS` is these lists together. A list's name is a name, and says nothing of what it holds;
this table does.

| list | where | what its mutants change |
|---|---|---|
| `MUTANTS` of `mutants.py` | `mutants.py` | §6.1's functions, one rule each. `mutants3.py` restates some on the tables' interface (`MOVED`) and one as a change of the tables (`IN_TABLES`) |
| `NEW` | `mutants3.py` | §6.1 once more (`may_ask`, `ask_parked`, `announcers`, `untried`): a read or a write beyond the Python's; and operations of its tables that do more, do less, or note nothing |
| `SLICE1` | `mutants3.py` | §4.4 and §6.2 |
| `V010` | `mutants3.py` | §4.4's `valid_id` and a bitmap's `valid_have` |
| `SLICE2A` | `mutants3.py` | §4.2 |
| `QMOVE` | `mutants3.py` | the twin's own queue, and more of §4.2 |
| `AEND` | `mutants3.py` | §6.1's `outstanding`, §4.2's deferred chunks, §7.2's writer |
| `GA5` | `mutants3.py` | more of §4.2's deferred chunks and §7.2's writer |
| `CYCLE1` | `mutants_c1.py` | §1 to §3, §4.1, §4.3, §4.5, §4.6, §6.2, §6.4 and `drop_offer` |
| `CYCLE2` | `mutants_c2.py` | §5 and §7.1, and more of the functions above |

`python3 mutants3.py --places --twin ..` checks that every mutant's text stands in the twin once, in the function
its description names. `LEFT` in `mutants3.py` is three changes that no record
tells from the twin, kept as text with the reason, in no list.
