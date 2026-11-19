#!/usr/bin/env python3
"""The Lean code of the twin's tables, from schema.py: three files of the twin, written whole.

    python3 gen.py --check TWINDIR            # each generated file against the twin's; exit code 1 if one differs
    python3 gen.py --write TWINDIR            # write the three files
    python3 gen.py --control TWINDIR WORKDIR  # the check's controls: each must make the same check fail

The three files, each generated from its first byte to its last and compared byte for byte:
- SpecTwin/State.lean: `State`, `Cell`, `Level`, `Touch`, and `ownTables`, the tables' names as a trace gives them;
- SpecTwin/Tables.lean: the class `Tables`, `Tables.ofState`, `Tables.lift` and its instance through ReaderT;
- SpecTwin/ReplayTables.lean: the replay's per-table functions (`cell`, `val`, `level`, `valueAt`, `put`, `drop`,
  `entries`, `under`, `covers`).
So nothing in these files is written by hand: not a first line, not a line after a body, not a comment. (A check
that compares slices of hand-written files, regions or declarations' bodies, misses text that the slices do not
hold.)

A tripwire beside it, a heuristic and no proof. It looks in the twin's other files for a declaration of one of
the 16 names in NAMES, which these files declare (a `def drop` in another namespace, say), and says whether it
found one: "no matching declaration found" is all it can say. It reads declarations by a pattern over the start
of each line (DECL), after an attribute, a doc comment on the same line, and the modifiers it lists. So it does
not find (the first two have controls that show it, as limits):
- a name in guillemets (`def «drop»`);
- a declaration by a keyword the pattern does not list (`axiom`, a macro of the file's own);
- a declaration that follows another command on its line, or whose name is on a line after its keyword;
- a name brought in under another one (`export`, `open ... renaming`).
It can also take declaration-shaped text inside a comment for a declaration. And it looks for those 16 names
alone: a hand-written function of another name, called from Replay.lean where a generated one was called,
passes the comparison and the tripwire both. How the hand-written files use the generated ones (Replay.lean's
calls, Main.lean) is known by reading them and by the replay's behaviour, not by this check.

The instances of `Tables` written by hand: the twin's other files hold one, the replay's (Replay.lean,
`instance : Tables R`, which is `Tables.ofState` with the replay's note). The check holds it as one fixed unit: its
header must be the only instance header that names `Tables` in the hand-written files, and from that header on
the file must read REPLAY_INSTANCE, a blank line and the next section's first line (REPLAY_AFTER), so that a copy
kept in a comment, a second instance, or a line that goes on with its body are each a difference. Any other line
of a hand-written file that declares something of type `Tables` (`: Tables`, as a `def` made an instance by an
attribute) is a difference too. An instance that overrode one operation would change the replay's answers
without changing a generated file. Not seen by these rules, which read text: a header that names `Tables` only
on a line after its keyword and has no `: Tables` on any line; and every other spelling of the type or of the
value (`SpecTwin.Tables`, a parenthesised type, an abbreviation, a definition with no type written, a structure
update, a `let` inside a function). Another check, which reads no text, covers what goes through the generated
makers: TablesMakers.lean, run by makers.py on the built twin, asks Lean which constants of the replay's own modules
mention one of them or have a `Tables` for their type, and its controls plant such spellings that this text check
passes. Its own header says what it does not see (a cast, a foreign function, a compiler substitution). Not seen by either:
instances of other classes for the generated types (a `BEq Cell` by hand, say), which would show only by the
replay's behaviour.

What the check does not look at, all of it written by hand:
- per-table code in the twin's other files: `Val` and the parsers of keys (ReplayBase.lean); the reads of other
  sections' tables (the tape's entries, `foreignRead`, `Node61`); the table mutants; the directed generators;
- Main.lean's list of the other sections' tables a header must name (`tables "foreign"`), written out there;
- whether Main.lean demands `ownTables` of a header. That Main.lean names `ownTables` is known by reading it
  (`let schema := tables "own" == some ownTables`). By behaviour, two things are shown. Every trace's header
  carries the schema's list and is accepted, and a header with another list is refused (altered3.py's
  control): a list written out in Main.lean would do the same. And a twin whose generated `ownTables` lacks a
  name refuses a header that the twin accepts: a list written out in Main.lean would not.

A line is written on one line if it fits in WIDTH columns, and otherwise with its note and its change of the
state on lines of their own, as the hand-written code had it. (A scan of a table of three keys and the replay's
arms for one are not wrapped, and can be longer.)

The shapes: a table has any number of keys, nested, or two keyed as a pair; a level read as a whole is given any
number of its outer keys short of all of them (`Scan.depth`). A table can keep its rows (`Table.rows`): a row
there is then an entry of its own, a flag, with or without anything under it, so that a record's null for a row
always says that it went. For such a table:
- a write of an entry makes the rows on its way, and notes each it made as written, outer first;
- an erase makes no row, and leaves the rows there as they were, empty or not;
- a row put (a record's reads) is made if missing and left as it is if there; a row dropped goes with all under it;
- a level read as a whole holds the entries below it and the rows among them, and not its own row;
- its last level's value has presence too (`pbits`: 0 is a bitmap there and empty; `lane`: [] is a lane there
  and empty).
A schema line of another shape is refused (`validate`), not written.
"""
import copy
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))    # an isolated Python (-I) puts no directory there itself
from schema import PARSE, STATE_ORDER, TABLES, VALUES     # noqa: E402

WIDTH = 120
NOT_SOURCES = (".lake", "tools", "record", "__pycache__")    # what is not the twin's sources (as ../layout.py's)


def vars_(t):
    return " ".join(k for k, _ in t.keys)


def cellof(t, names=None):
    return f".{t.cell} " + " ".join(names or [k for k, _ in t.keys])


def keytype(t):
    return " → ".join(ty for _, ty in t.keys)


def depth(s):
    """The outer keys a scan's level is given: 0 for the whole table, 1 for a row, and so on."""
    return s.depth if s.depth is not None else (1 if s.row else 0)


def rowcell(t, ks):
    """The cell of a row of a table that keeps its rows: the row under the keys `ks`."""
    return f".{t.rows[len(ks) - 1]} " + " ".join(ks)


def rowpat(t, n):
    """A pattern for the cells of the rows of `n` keys, the keys not looked at."""
    return f".{t.rows[n - 1]} _" if n == 1 else f".{t.rows[n - 1]} .."


def chain(base, ks):
    """The map under the outer keys `ks`, read without changing anything: `((base.getD k {}).getD k' {})`."""
    for k in ks:
        base = f"({base}.getD {k} {{}})"
    return base


def inserted(base, ks, x, last="insert"):
    """`base` with `x` set under the keys `ks`, every level on the way made where it is missing. With `last`
    "erase", the entry under them erased, the levels on the way made too: for a table without its rows."""
    k = ks[0]
    if len(ks) == 1:
        return f"{base}.{last} {k}" + (f" {x}" if last == "insert" else "")
    return f"{base}.insert {k} ({inserted(f'({base}.getD {k} {{}})', ks[1:], x, last)})"


def modified(base, ks):
    """`base` with the entry under the keys `ks` erased, and no level made: `base.modify k (·.erase k')`."""
    def inner(ks):
        return f"(·.erase {ks[0]})" if len(ks) == 1 else f"(·.modify {ks[0]} {inner(ks[1:])})"
    return f"{base}.erase {ks[0]}" if len(ks) == 1 else f"{base}.modify {ks[0]} {inner(ks[1:])}"


def ensured(base, ks):
    """`base` with a row under the keys `ks`, as it was if it was there and empty if not, and every level on the way."""
    k = ks[0]
    if len(ks) == 1:
        return f"(if {base}.contains {k} then {base} else {base}.insert {k} {{}})"
    return f"{base}.insert {k} {ensured(f'({base}.getD {k} {{}})', ks[1:])}"


def listed(base, ks):
    """The map `base`, keyed by `ks`, as nested lists: `base.toList.map fun (k, m) => (k, m.toList)` for two keys."""
    if len(ks) == 1:
        return f"{base}.toList"
    return f"{base}.toList.map fun ({ks[0]}, m) => ({ks[0]}, {listed('m', ks[1:])})"


def found(t, lst, ks, outer):
    """The cells a scan's nested list `lst` holds: under the keys `outer`, given, the keys `ks`; for a table that
    keeps its rows, every row among them too."""
    k, here = ks[0], outer + [ks[0]]
    if len(ks) == 1:
        return f"{lst}.map fun ({k}, _) => {cellof(t, here)}"
    sub = f"{ks[1]}s"
    row = f"{rowcell(t, here)} :: " if t.rows else ""
    return f"{lst}.flatMap fun ({k}, {sub}) => {row}{found(t, sub, ks[1:], here)}"


def keys_of(f, ks, c):
    """Every key of the map `s.f` down to the keys `ks`, as the cell `c` names them."""
    def inner(ks):
        return (f"m.toList.map fun ({ks[0]}, _) => {c}" if len(ks) == 1
                else f"m.toList.flatMap fun ({ks[0]}, m) => {inner(ks[1:])}")
    return (f"s.{f}.toList.map (fun ({ks[0]}, _) => {c})" if len(ks) == 1
            else f"s.{f}.toList.flatMap (fun ({ks[0]}, m) => {inner(ks[1:])})")


# kept: the hand-written second names of the keys in `under`, which are the key's own with a prime otherwise
KEPT_OTHER = {("tried", "a"): "b", ("offered", "q"): "r", ("park", "p"): "r"}


def others(t, ks):
    return [KEPT_OTHER.get((t.name, k), k + "'") for k in ks]


def validate():
    """The shapes the generator writes, and only those: a schema line of another shape is refused, not written."""
    for t in TABLES:
        n, why = len(t.keys), None
        if t.value not in VALUES:
            why = f"no kind of value {t.value!r}"
        elif any(ty not in PARSE for _, ty in t.keys):
            why = "a key of a type with no parser (PARSE)"
        elif VALUES[t.value]["read"] == "member" and (n != 1 or t.rows):
            why = "a set has one key, its members, and no rows"
        elif t.shape == "pair" and (n != 2 or t.rows):
            why = "a table keyed by a pair has two keys and no rows"
        elif t.shape not in ("nested", "pair"):
            why = f"no shape {t.shape!r}"
        elif t.rows is not None and (n < 2 or len(t.rows) != n - 1):
            why = f"a table that keeps its rows names one row cell per key but the last: {n - 1}, not {len(t.rows)}"
        elif bool(VALUES[t.value].get("presence")) != bool(t.rows):
            why = ("a value with presence (pbits, lane) is the value of a table that keeps its rows, and only of one"
                   if VALUES[t.value].get("presence") else "a table that keeps its rows has a value with presence")
        elif any(not 0 <= depth(s) < n or (depth(s) and (t.shape == "pair" or VALUES[t.value]["read"] == "member")) for s in t.scans):
            why = "a level given as many outer keys as the table has, or more, or a row of a table that has none"
        elif t.row_ops and (not t.rows or sorted(d for d, *_ in t.row_ops) != sorted({d for d, *_ in t.row_ops})
                            or any(not 1 <= d < n for d, *_ in t.row_ops)):
            why = "a row's operations are of a table that keeps its rows, one set per row level, at a level it has"
        if why:
            raise SystemExit(f"gen.py: the schema's {t.name}: {why}")


def elem_type(t, keys):
    """The type of one scanned element over `keys` (the inner keys of a row, or all keys)."""
    v = VALUES[t.value]
    if VALUES[t.value]["read"] == "member":
        return keys[0][1]
    if len(keys) == 2 and t.shape == "pair":
        return f"({keys[0][1]} × {keys[1][1]}) × {v['lean']}"
    if len(keys) == 1:
        return f"{keys[0][1]} × {v['lean']}"
    return f"{keys[0][1]} × List ({elem_type(t, keys[1:])})"


def class_fields():
    out, later = [], []
    for t in TABLES:
        v = VALUES[t.value]
        lean = f"({v['lean']})" if v["lean"] and " " in v["lean"] else v["lean"]   # `Option (List QEntry)`
        ret = {"option": f"Option {lean}", "default": v["lean"], "member": "Bool"}[v["read"]]
        ret = f"({ret})" if " " in ret else ret
        out += [f"  /-- {t.read[1]} -/", f"  {t.read[0]} : {keytype(t)} → m {ret}"]
        if t.write:
            arg = "Bool" if VALUES[t.value]["read"] == "member" else v["lean"]
            out += [f"  /-- {t.write[1]} -/", f"  {t.write[0]} : {keytype(t)} → {arg} → m Unit"]
        if t.erase:
            out += [f"  /-- {t.erase[1]} -/", f"  {t.erase[0]} : {keytype(t)} → m Unit"]
        if t.clear:
            out += [f"  /-- {t.clear[1]} -/", f"  {t.clear[0]} : m Unit"]
        for d, rd, rdoc, er, edoc in t.row_ops:     # a row's presence, and its erase with all under it
            given = " → ".join(ty for _, ty in t.keys[:d])
            out += [f"  /-- {rdoc} -/", f"  {rd} : {given} → m Bool", f"  /-- {edoc} -/", f"  {er} : {given} → m Unit"]
        for s in t.scans:
            keys = t.keys[depth(s):]
            ty = f"m (List ({elem_type(t, keys)}))" if " " in elem_type(t, keys) else f"m (List {elem_type(t, keys)})"
            decl = f"  {s.name} : " + "".join(f"{ty_} → " for _, ty_ in t.keys[:depth(s)]) + ty
            (out if s.used else later).extend([f"  /-- {s.doc} -/", decl])
    return out, later


def fit(head, note, change):
    one = f"  {head} := do {note}; {change}"
    return [one] if len(one) <= WIDTH else [f"  {head} := do", f"    {note}", f"    {change}"]


def of_state():
    out, later = [], []
    for t in TABLES:
        v, f, ks = VALUES[t.value], t.field, [k for k, _ in t.keys]
        note_r, note_w = f"note (.read ({cellof(t)}))", f"note (.write ({cellof(t)}))"
        if len(ks) == 1 or t.shape == "pair":
            k = ks[0] if len(ks) == 1 else f"({ks[0]}, {ks[1]})"
            got = {"option": f"(← get).{f}.get? {k}", "default": f"(← get).{f}.getD {k} {v.get('default')}",
                   "member": f"(← get).{f}.contains {k}"}[v["read"]]
            ins = f"s.{f}.insert {k} {v['param']}"
            ers = f"s.{f}.erase {k}"
        else:
            row = chain(f"(← get).{f}", ks[:-1])
            got = {"option": f"{row}.get? {ks[-1]}", "default": f"{row}.getD {ks[-1]} {v.get('default')}"}[v["read"]]
            ins = inserted(f"s.{f}", ks, v["param"])
            # a table that keeps its rows keeps them when an entry goes; one that does not, has no empty row to show
            ers = modified(f"s.{f}", ks) if t.rows else inserted(f"s.{f}", ks, None, "erase")
        out.append(f"  {t.read[0]} {vars_(t)} := do {note_r}; return {got}")
        if t.write and VALUES[t.value]["read"] == "member":
            k = ks[0]
            out += [f"  {t.write[0]} {vars_(t)} {v['param']} := do", f"    {note_w}", "    modify fun s => { s with",
                    f"      {f} := if {v['param']} then s.{f}.insert {k} else s.{f}.erase {k} }}"]
        elif t.write and t.rows:            # the rows a write makes are written too
            out += [f"  {t.write[0]} {vars_(t)} {v['param']} := do", "    let s ← get"]
            for d in range(1, len(ks)):
                out.append(f"    if !{chain(f's.{f}', ks[:d - 1])}.contains {ks[d - 1]} then note (.write ({rowcell(t, ks[:d])}))")
            mod = f"    modify fun s => {{ s with {f} := {ins} }}"
            out += [f"    {note_w}", *([mod] if len(mod) <= WIDTH else ["    modify fun s => { s with", f"      {f} := {ins} }}"])]
        elif t.write:
            out += fit(f"{t.write[0]} {vars_(t)} {v['param']}", note_w, f"modify fun s => {{ s with {f} := {ins} }}")
        if t.erase:
            out += fit(f"{t.erase[0]} {vars_(t)}", note_w, f"modify fun s => {{ s with {f} := {ers} }}")
        if t.clear:                                 # the table emptied, each entry there written
            assert len(ks) == 1, f"{t.name}: clear is for a table of one key"
            out += [f"  {t.clear[0]} := do",
                    f"    for ({ks[0]}, _) in (← get).{f}.toList do {note_w}",
                    f"    modify fun s => {{ s with {f} := {{}} }}"]
        for d, rd, _, er, _ in t.row_ops:           # the row read as the views read it, and erased as they pop it:
            given = ks[:d]                          #   the row written, and every entry under it
            out.append(f"  {rd} {' '.join(given)} := do note (.read ({rowcell(t, given)})); "
                       f"return {chain(f'(← get).{f}', given[:-1])}.contains {given[-1]}")
            out += [f"  {er} {' '.join(given)} := do",
                    f"    let l := {listed(chain(f'(← get).{f}', given), ks[d:])}",
                    f"    note (.write ({rowcell(t, given)}))",
                    f"    for c in {found(t, 'l', ks[d:], given)} do note (.write c)",
                    f"    modify fun s => {{ s with {f} := {modified(f's.{f}', given)} }}"]
        for s in t.scans:
            d = depth(s)
            if VALUES[t.value]["read"] == "member":
                block = [f"  {s.name} := do", f"    let l := (← get).{f}.toList",
                         f"    note (.scan .{s.level} (l.map fun {ks[0]} => {cellof(t)}))", "    return l"]
            elif t.shape == "pair":
                block = [f"  {s.name} := do", f"    let l := (← get).{f}.toList",
                         f"    note (.scan .{s.level} (l.map fun (({ks[0]}, {ks[1]}), _) => {cellof(t)}))", "    return l"]
            else:
                given = ks[:d]
                lvl = f".{s.level}" if not d else f"(.{s.level} {' '.join(given)})"
                block = [f"  {s.name}{''.join(' ' + k for k in given)} := do",
                         f"    let l := {listed(chain(f'(← get).{f}', given), ks[d:])}",
                         f"    note (.scan {lvl} ({found(t, 'l', ks[d:], given)}))", "    return l"]
            (out if s.used else later).extend(block)
    return out + later


def lift():
    out, later = [], []
    for t in TABLES:
        v = VALUES[t.value]
        out.append(f"  {t.read[0]} {vars_(t)} := f ({t.read[0]} {vars_(t)})")
        if t.write:
            p = t.lift_param or v["param"]
            out.append(f"  {t.write[0]} {vars_(t)} {p} := f ({t.write[0]} {vars_(t)} {p})")
        if t.erase:
            out.append(f"  {t.erase[0]} {vars_(t)} := f ({t.erase[0]} {vars_(t)})")
        if t.clear:
            out.append(f"  {t.clear[0]} := f {t.clear[0]}")
        for d, rd, _, er, _ in t.row_ops:
            k = " ".join(k for k, _ in t.keys[:d])
            out += [f"  {rd} {k} := f ({rd} {k})", f"  {er} {k} := f ({er} {k})"]
        for s in t.scans:
            k = " ".join(k for k, _ in t.keys[:depth(s)])
            line = f"  {s.name} {k} := f ({s.name} {k})" if depth(s) else f"  {s.name} := f {s.name}"
            (out if s.used else later).append(line)
    return out + later


def state_order():
    """The order of State's fields: the hand-written order of the first tables (STATE_ORDER), then every other table
    in the schema's order. A name in STATE_ORDER that is no table is refused."""
    names = [t.name for t in TABLES]
    stray = [n for n in STATE_ORDER if n not in names]
    if stray:
        raise SystemExit(f"gen.py: STATE_ORDER names no table of the schema: {stray}")
    return STATE_ORDER + [n for n in names if n not in STATE_ORDER]


def basic():
    by = {t.name: t for t in TABLES}
    state = []
    for name in state_order():
        t = by[name]
        v, ks = VALUES[t.value], [ty for _, ty in t.keys]
        if VALUES[t.value]["read"] == "member":
            ty = f"Std.HashSet {ks[0]}"
        else:
            inner = f"({v['lean']})" if " " in v["lean"] else v["lean"]
            if t.shape == "pair":
                ty = f"Std.HashMap ({ks[0]} × {ks[1]}) {inner}"
            else:
                ty = inner
                for n, k in enumerate(reversed(ks)):
                    ty = f"Std.HashMap {k} {ty if n == 0 else '(' + ty + ')'}"
        state.append(f"  {t.field} : {ty} := {{}}")
    cell = []
    for t in TABLES:
        cell.append("  | " + t.cell + "".join(f" ({k} : {ty})" for k, ty in t.keys))
        for n, r in enumerate(t.rows or [], 1):
            cell.append("  | " + r + "".join(f" ({k} : {ty})" for k, ty in t.keys[:n]))
    level = []
    for t in TABLES:
        for s in t.scans:
            line = f"  | {s.level}" + "".join(f" ({k} : {ty})" for k, ty in t.keys[:depth(s)])
            level.append(f"{line:<42}-- {s.note}" if s.note else line)
    return state, cell, level


def pat(t, wild=True, names=None):
    """A pattern for a table's cell: its keys named, or not looked at."""
    if not wild:
        return f".{t.cell} " + " ".join(names or [k for k, _ in t.keys])
    return f".{t.cell} _" if len(t.keys) == 1 else f".{t.cell} .."


def replay():
    r = {}
    # cell: an entry's name, from a record's table and path
    out = []
    for t in TABLES:
        ks = t.keys
        made = f"return .{t.cell} " + " ".join(f"(← {PARSE[ty]} {k})" for k, ty in ks)
        if t.shape == "pair" and len(ks) == 2:
            both = ks[0][0] + ks[1][0]
            out += [f'  | "{t.name}", #[{both}] =>',
                    f'    let #[{ks[0][0]}, {ks[1][0]}] ← {both}.getArr? | throw s!"not a {t.cell}\'s key: {{{both}.compress}}"',
                    f"    {made}"]
        else:
            out.append(f'  | "{t.name}", #[{", ".join(k for k, _ in ks)}] => {made}')
            for n, row in enumerate(t.rows or [], 1):        # a row's path: its keys alone
                made = f"return .{row} " + " ".join(f"(← {PARSE[ty]} {k})" for k, ty in ks[:n])
                out.append(f'  | "{t.name}", #[{", ".join(k for k, _ in ks[:n])}] => {made}')
    r["cell"] = out
    # val: an entry's value, by its kind
    out = []
    for kind, v in VALUES.items():
        ts = [t for t in TABLES if t.value == kind]
        if not ts:
            continue
        pats = " | ".join(pat(t) for t in ts)
        if kind == "time":
            out.append(f"  | {pats} => return some (.time (← bits64 j))")
        elif kind == "peers":
            out += [f"  | {pats} =>", "    let l ← peers j", f'    if l.isEmpty then throw "{v["empty"]} as a value"',
                    "    return some (.peers l)"]
        elif kind == "peerset":
            out += [f"  | {pats} =>", "    let l ← peers j", f'    if l.isEmpty then throw "{v["empty"]} as a value"',
                    '    if !(l.zip (l.drop 1)).all (fun (x, y) => x < y) then throw s!"a set not sorted, or with a peer twice: {j.compress}"',
                    "    return some (.peers l)"]
        elif kind == "ppeerset":                    # there and empty is []: a value
            out += [f"  | {pats} =>", "    let l ← peers j",
                    '    if !(l.zip (l.drop 1)).all (fun (x, y) => x < y) then throw s!"a set not sorted, or with a peer twice: {j.compress}"',
                    "    return some (.peers l)"]
        elif kind == "bits":
            out += [f"  | {pats} =>", "    let b ← nat j", f'    if b == 0 then throw "{v["empty"]} as a value"',
                    "    return some (.bits b)"]
        elif v["read"] == "member":         # a set, and a flagset
            out.append(f'  | {pats} => if j == .bool true then return some .flag else throw s!"not a set\'s member: {{j.compress}}"')
        elif kind == "count":
            out += [f"  | {pats} =>", "    let n ← nat j", f'    if n == 0 then throw "{v["empty"]} as a value"',
                    "    return some (.count n)"]
        elif kind == "idset":                       # a set of ids, as hex, sorted
            out += [f"  | {pats} =>", "    let l ← hexes j", f'    if l.isEmpty then throw "{v["empty"]} as a value"',
                    '    if !(l.zip (l.drop 1)).all (fun (x, y) => x < y) then throw s!"a set not sorted, or with an id twice: {j.compress}"',
                    "    return some (.ids l)"]
        elif kind == "int":                         # the window: a signed count, 0 no value
            out += [f"  | {pats} =>", "    let n ← intOf j", f'    if n == 0 then throw "{v["empty"]} as a value"',
                    "    return some (.int n)"]
        elif kind == "askkey":
            out.append(f"  | {pats} => return some (.key (← key j))")
        elif kind == "state":
            out.append(f"  | {pats} => return some (.state (← {v['parse']} j))")
        elif kind in ("pbits", "obits"):            # there and empty is 0: a value
            out.append(f"  | {pats} => return some (.bits (← nat j))")
        elif kind == "lane":                        # there and empty is []: a value
            out.append(f"  | {pats} => return some (.lane (← {v['parse']} j))")
        elif kind == "waits":                       # an empty list of waits is no value
            out += [f"  | {pats} =>", f"    let l ← {v['parse']} j", f'    if l.isEmpty then throw "{v["empty"]} as a value"',
                    "    return some (.waits l)"]
        elif kind == "slot":
            out.append(f"  | {pats} => return some (.slot (← nat j))")
        elif kind == "have":                        # an entry there with no bit is a value
            out.append(f"  | {pats} => return some (.have (← {v['parse']} j))")
        elif kind == "push":                        # an entry there with no bit is a value
            out.append(f"  | {pats} => return some (.push (← {v['parse']} j))")
        elif kind == "desc":                        # a group's descriptor
            out.append(f"  | {pats} => return some (.desc (← {v['parse']} j))")
        elif kind == "jobs":                        # an empty pace queue is no value
            out += [f"  | {pats} =>", f"    let l ← {v['parse']} j", f'    if l.isEmpty then throw "{v["empty"]} as a value"',
                    "    return some (.jobs l)"]
        else:
            raise SystemExit(f"gen.py: no `val` arm is written for the kind of value {kind!r}")
    rows = [rowpat(t, n) for t in TABLES for n in range(1, len(t.rows or []) + 1)]
    if rows:                                        # a row that is there: true
        out.append(f"  | {' | '.join(rows)} =>")
        out.append('    if j == .bool true then return some .flag else throw s!"not a row\'s presence: {j.compress}"')
    r["val"] = out
    # level
    out = []
    for t in TABLES:
        for s in t.scans:
            ks = t.keys[:depth(s)]
            out.append(f'  | "{t.name}", #[{", ".join(k for k, _ in ks)}] => return .{s.level} '
                       + " ".join(f"(← {PARSE[ty]} {k})" for k, ty in ks) if ks
                       else f'  | "{t.name}", #[] => return .{s.level}')
    r["level"] = out
    # valueAt, put, drop, entries
    va, put, drop, ent = [], [], [], []
    for t in TABLES:
        v, f, ks = VALUES[t.value], t.field, [k for k, _ in t.keys]
        c = pat(t, wild=False)
        if len(ks) == 1 or t.shape == "pair":
            k = ks[0] if len(ks) == 1 else f"({ks[0]}, {ks[1]})"
            got_opt, got_def = f"(s.{f}.get? {k})", f"s.{f}.getD {k} {v.get('default')}"
            ins = lambda x: f"s.{f}.insert {k} {x}"
            ers = f"s.{f}.erase {k}"
            keysof = (f"s.{f}.toList.map (fun (({ks[0]}, {ks[1]}), _) => {c})" if len(ks) == 2
                      else f"s.{f}.toList.map (fun ({k}, _) => {c})")
        else:
            row = chain(f"s.{f}", ks[:-1])
            got_opt, got_def = f"({row}.get? {ks[-1]})", f"{row}.getD {ks[-1]} {v.get('default')}"
            ins = lambda x, f=f, ks=ks: inserted(f"s.{f}", ks, x)
            ers = modified(f"s.{f}", ks) if t.rows else inserted(f"s.{f}", ks, None, "erase")
            keysof = keys_of(f, ks, c)
        if t.value == "time":
            va.append(f"  | {c} => {got_opt}.map (.time ·.toBits)")
            put.append(f"  | {c}, .time t => pure {{ s with {f} := {ins('(Float.ofBits t)')} }}")
        elif t.value == "peers":
            va += [f"  | {c} => match {got_def} with", "    | [] => none", "    | l => some (.peers l)"]
            put.append(f"  | {c}, .peers l => pure {{ s with {f} := {ins('l')} }}")
        elif t.value == "peerset":
            va += [f"  | {c} => match sortBy (· < ·) ({got_def}).toList with", "    | [] => none", "    | l => some (.peers l)"]
            put.append(f"  | {c}, .peers l => pure {{ s with {f} := {ins('(l.foldl (·.insert ·) {})')} }}")
        elif t.value == "ppeerset":                # there and empty is a value
            va.append(f"  | {c} => {got_opt}.map (fun ps => .peers (sortBy (· < ·) ps.toList))")
            put.append(f"  | {c}, .peers l => pure {{ s with {f} := {ins('(l.foldl (·.insert ·) {})')} }}")
        elif t.value == "bits":
            va += [f"  | {c} => match {got_def} with", "    | 0 => none", "    | b => some (.bits b)"]
            put.append(f"  | {c}, .bits b => pure {{ s with {f} := {ins('b')} }}")
        elif VALUES[t.value]["read"] == "member":
            va.append(f"  | {c} => if s.{f}.contains {ks[0]} then some .flag else none")
            put.append(f"  | {c}, .flag => pure {{ s with {f} := s.{f}.insert {ks[0]} }}")
            keysof = f"s.{f}.toList.map (fun {ks[0]} => {c})"
        elif t.value == "count":
            va += [f"  | {c} => match {got_def} with", "    | 0 => none", "    | n => some (.count n)"]
            put.append(f"  | {c}, .count n => pure {{ s with {f} := {ins('n')} }}")
        elif t.value == "idset":                   # a set of ids
            va += [f"  | {c} => match sortBy (· < ·) ({got_def}).toList with", "    | [] => none", "    | l => some (.ids l)"]
            put.append(f"  | {c}, .ids l => pure {{ s with {f} := {ins('(l.foldl (·.insert ·) {})')} }}")
        elif t.value == "int":                     # the window: a signed count, 0 where missing
            va += [f"  | {c} => match {got_def} with", "    | 0 => none", "    | n => some (.int n)"]
            put.append(f"  | {c}, .int n => pure {{ s with {f} := {ins('n')} }}")
        elif t.value == "askkey":
            va.append(f"  | {c} => {got_opt}.map (.key ·)")
            put.append(f"  | {c}, .key a => pure {{ s with {f} := {ins('a')} }}")
        elif t.value == "state":
            va.append(f"  | {c} => {got_opt}.map (.state ·)")
            put.append(f"  | {c}, .state x => pure {{ s with {f} := {ins('x')} }}")
        elif t.value in ("pbits", "obits"):        # there and empty is a value
            va.append(f"  | {c} => {got_opt}.map (.bits ·)")
            put.append(f"  | {c}, .bits b => pure {{ s with {f} := {ins('b')} }}")
        elif t.value == "lane":                    # there and empty is a value
            va.append(f"  | {c} => {got_opt}.map (.lane ·)")
            put.append(f"  | {c}, .lane es => pure {{ s with {f} := {ins('es')} }}")
        elif t.value == "waits":
            va += [f"  | {c} => match {got_def} with", "    | [] => none", "    | l => some (.waits l)"]
            put.append(f"  | {c}, .waits w => pure {{ s with {f} := {ins('w')} }}")
        elif t.value == "jobs":
            va += [f"  | {c} => match {got_def} with", "    | [] => none", "    | l => some (.jobs l)"]
            put.append(f"  | {c}, .jobs js => pure {{ s with {f} := {ins('js')} }}")
        elif t.value == "slot":
            va.append(f"  | {c} => {got_opt}.map (.slot ·)")
            put.append(f"  | {c}, .slot n => pure {{ s with {f} := {ins('n')} }}")
        elif t.value == "have":
            va.append(f"  | {c} => {got_opt}.map (.have ·)")
            put.append(f"  | {c}, .have e => pure {{ s with {f} := {ins('e')} }}")
        elif t.value == "push":
            va.append(f"  | {c} => {got_opt}.map (.push ·)")
            put.append(f"  | {c}, .push e => pure {{ s with {f} := {ins('e')} }}")
        elif t.value == "desc":
            va.append(f"  | {c} => {got_opt}.map (.desc ·)")
            put.append(f"  | {c}, .desc d => pure {{ s with {f} := {ins('d')} }}")
        else:
            raise SystemExit(f"gen.py: no `valueAt` and `put` arms are written for the kind of value {t.value!r}")
        drop.append(f"  | {c} => {{ s with {f} := {ers} }}")
        ent.append(("    " if not ent else "    ++ ") + keysof)
        for n in range(1, len(t.rows or []) + 1):  # the rows: there or not, with anything under them or nothing
            rc, rk = rowcell(t, ks[:n]), ks[:n]
            va.append(f"  | {rc} => if {chain(f's.{f}', rk[:-1])}.contains {rk[-1]} then some .flag else none")
            put.append(f"  | {rc}, .flag => pure {{ s with {f} := {ensured(f's.{f}', rk)} }}")
            drop.append(f"  | {rc} => {{ s with {f} := {modified(f's.{f}', rk)} }}")
            ent.append("    ++ " + keys_of(f, rk, rc))
    r["valueAt"], r["put"], r["drop"], r["entries"] = va, put, drop, ent
    # under, covers
    un, co = [], []
    for t in TABLES:
        n = len(t.keys)
        for s in t.scans:
            d = depth(s)
            # under a level: the entries below it, the rows among them, and not the level's own row
            below = [(f".{t.cell}", n)] + [(f".{t.rows[m - 1]}", m) for m in range(d + 1, n)] if t.rows else [(f".{t.cell}", n)]
            if not d:
                un += [f"  | .{s.level}, {pat(t) if c == f'.{t.cell}' else rowpat(t, m)} => true" for c, m in below]
                continue
            ks, os = [k for k, _ in t.keys[:d]], others(t, [k for k, _ in t.keys[:d]])
            same = " && ".join(f"{k} == {o}" for k, o in zip(ks, os))
            un += [f"  | .{s.level} {' '.join(ks)}, {c} {' '.join(os + ['_'] * (m - d))} => {same}" for c, m in below]
            for s1 in t.scans:                      # a level holds the levels below it
                d1 = depth(s1)
                if d1 >= d:
                    continue
                if not d1:
                    co.append(f"  | .{s1.level}, .{s.level} {' '.join(['_'] * d)} => true")
                else:
                    co.append(f"  | .{s1.level} {' '.join(ks[:d1])}, .{s.level} {' '.join(os[:d1] + ['_'] * (d - d1))} => "
                              + " && ".join(f"{k} == {o}" for k, o in zip(ks[:d1], os[:d1])))
    r["under"], r["covers"] = un, co
    return r


GENERATED = ("This file is written whole by `tools/gen/gen.py` from `gen/schema.py`, one entry there per\n"
             "table, and `gen.py --check` compares it byte for byte. Do not edit it: change the schema, or the generator.")


def wrapped(items, indent, width=WIDTH):
    """Items joined by ", " into lines of at most `width` columns, each after the first indented by one more."""
    lines, cur = [], indent + "["
    for n, x in enumerate(items):
        piece = x + ("," if n + 1 < len(items) else "]")
        if cur.strip() != "[" and len(cur) + 1 + len(piece) > width:
            lines.append(cur)
            cur = indent + " " + piece
        else:
            cur += (" " if not cur.endswith("[") else "") + piece
    return lines + [cur]


def state_file():
    state, cell, level = basic()
    return "\n".join([
        "import SpecTwin.Basic",
        "",
        "/-! # The twin's state and the names of its entries (generated)",
        "",
        GENERATED,
        "",
        "The state the twin keeps (§8.1), the names of its entries (`Cell`), of the levels a table can be read whole at",
        "(`Level`), what one access of the state touches (`Touch`), and the tables' names as a trace's header and its",
        "records give them (`ownTables`). -/",
        "",
        "namespace SpecTwin",
        "",
        "/-- The state §6.1's block keeps (§8.1). A missing entry reads as empty, and reading allocates nothing. -/",
        "structure State where",
        *state,
        "",
        "/-- An entry of §6.1's tables: the table and its keys, down to the level at which the code reads values (the",
        "schema, `tools/gen/schema.py`). A missing entry is a value too, and reading it is a read. -/",
        "inductive Cell where",
        *cell,
        "  deriving BEq, Repr",
        "",
        "/-- A level of a table read as a whole: every entry under it. -/",
        "inductive Level where",
        *level,
        "  deriving BEq, Repr",
        "",
        "/-- What one access of the state touches. -/",
        "inductive Touch where",
        "  | read (c : Cell)",
        "  | write (c : Cell)",
        "  | scan (l : Level) (found : List Cell)  -- a level read as a whole, and the entries it held",
        "  deriving BEq, Repr",
        "",
        "/-- The twin's own tables, by the names a trace's header and its records give them, in the schema's order. -/",
        "def ownTables : List String :=",
        *wrapped([f'"{t.name}"' for t in TABLES], "  "),
        "",
        "end SpecTwin",
        "",
    ])


def tables_file():
    used, later = class_fields()
    return "\n".join([
        "import SpecTwin.State",
        "",
        "/-! # The twin's state, read and written entry by entry (generated)",
        "",
        GENERATED,
        "",
        "§6.1's code reaches its state through this interface and in no other way: `Sec61.lean` is written over a monad",
        "that has `Tables` and `Node61`, and no state of its own. One operation per table and kind of access: read an",
        "entry, write it, or read a level as a whole.",
        "",
        "`Tables.ofState` is the interface over the twin's `State`: each operation does its work on the state and notes",
        "what it touched (`Touch`): the entry read or written, or the level read as a whole with the entries it held.",
        "The replay collects the notes and compares them with what the Python read and wrote",
        "(`Replay.lean`); a proof's interpreter notes nothing.",
        "",
        "The notes are this file's word for what its operations do. The replay does not take that word alone: it also",
        "compares the twin's whole state after a call with the record's (`Replay.lean`, `wholeState`), and the mutants",
        "of this file (`mutants3.py`, the `tables-` ones) show what that comparison sees in each kind of record. -/",
        "",
        "namespace SpecTwin",
        "",
        "/-- §6.1's own state (§8.1), as its code uses it. A missing entry reads as empty, and reading allocates nothing. -/",
        "class Tables (m : Type → Type) where",
        *used,
        "  -- The levels §6.1's code never reads as a whole. They are here so that a twin that does, a mutant, can be",
        "  -- written, and is then seen to.",
        *later,
        "",
        "namespace Tables",
        "",
        "/-- The interface over the twin's `State`, with a note of each access. -/",
        "@[instance_reducible]",
        "def ofState {m : Type → Type} [Monad m] [MonadStateOf State m] (note : Touch → m Unit) : Tables m where",
        *of_state(),
        "",
        "/-- The interface through a monad transformer. -/",
        "abbrev lift {m n : Type → Type} [Tables m] (f : ∀ {α : Type}, m α → n α) : Tables n where",
        *lift(),
        "",
        "instance instReaderT {m : Type → Type} {ρ : Type} [Monad m] [Tables m] : Tables (ReaderT ρ m) :=",
        "  lift (m := m) (n := ReaderT ρ m) fun x => monadLift x",
        "",
        "end Tables",
        "",
        "end SpecTwin",
        "",
    ])


def replay_tables_file():
    r = replay()
    return "\n".join([
        "import SpecTwin.State",
        "import SpecTwin.ReplayBase",
        "",
        "/-! # The replay's reading and comparing of the twin's state, table by table (generated)",
        "",
        GENERATED,
        "",
        "How an entry and a level are read from a record (`cell`, `val`, `level`), and how a state is looked up, changed",
        "and listed entry by entry (`valueAt`, `put`, `drop`, `entries`, `under`, `covers`). The kinds of value (`Val`)",
        "and the parsers of keys are in `ReplayBase.lean`, written by hand. -/",
        "",
        "namespace SpecTwin.Replay",
        "",
        "open Lean (Json)",
        "",
        "/-- An entry of §6.1's tables, from its table's name and its path (one element per level). -/",
        "def cell (table : String) (path : Json) : Except String Cell := do",
        "  match table, ← path.getArr? with",
        *r["cell"],
        '  | _, _ => throw s!"not an entry of §6.1\'s tables: {table}{path.compress}"',
        "",
        "/-- An entry's value: `null` for a missing one. An empty value is refused: the tracer writes it as missing. -/",
        "def val (c : Cell) (j : Json) : Except String (Option Val) := do",
        "  if j == .null then return none",
        "  match c with",
        *r["val"],
        "",
        "/-- A level read as a whole: `[table, prefix]`. -/",
        "def level (j : Json) : Except String Level := do",
        '  let #[.str table, pre] ← j.getArr? | throw s!"not a level: {j.compress}"',
        "  match table, ← pre.getArr? with",
        *r["level"],
        '  | _, _ => throw s!"not a level of §6.1\'s tables: {j.compress}"',
        "",
        "/-- An entry's value in a state: none where it is missing or empty. -/",
        "def valueAt (s : State) : Cell → Option Val",
        *r["valueAt"],
        "",
        "/-- A state with one more entry: how a record's `reads` become the twin's state. -/",
        "def put (s : State) (c : Cell) (v : Val) : Except String State :=",
        "  match c, v with",
        *r["put"],
        '  | c, v => throw s!"not a value of {reprStr c}: {reprStr v}"',
        "",
        "/-- A state without an entry: how a record's erasing write is applied. -/",
        "def drop (s : State) : Cell → State",
        *r["drop"],
        "",
        "/-- Every entry a state holds, empty ones left out: what two states are compared by. -/",
        "def entries (s : State) : List (Cell × Val) :=",
        "  let all : List Cell :=",
        *r["entries"],
        "  all.filterMap fun c => (valueAt s c).map fun v => (c, v)",
        "",
        "/-- Whether a level read as a whole holds an entry. -/",
        "def under (c : Cell) (l : Level) : Bool :=",
        "  match l, c with",
        *r["under"],
        "  | _, _ => false",
        "",
        "/-- Whether a level holds another: itself, or a table's whole against one of its rows. -/",
        "def covers (l₁ l₂ : Level) : Bool :=",
        "  l₁ == l₂ || match l₁, l₂ with",
        *r["covers"],
        "  | _, _ => false",
        "",
        "end SpecTwin.Replay",
        "",
    ])


FILES = {"SpecTwin/State.lean": state_file, "SpecTwin/Tables.lean": tables_file,
         "SpecTwin/ReplayTables.lean": replay_tables_file}
# the names the three files declare, which no other file of the twin may declare (the tripwire). `lift` and
# `instReaderT` are left out: `Node61` has a `lift` of its own, by hand.
NAMES = ("State", "Cell", "Level", "Touch", "ownTables", "Tables", "ofState",
         "cell", "val", "level", "valueAt", "put", "drop", "entries", "under", "covers")
DECL = re.compile(r"^\s*(?:/--.*?-/\s*)?(?:@\[[^\]]*\]\s*)?"
                  r"(?:(?:private|protected|partial|noncomputable|unsafe|nonrec|public|scoped|local)\s+)*"
                  r"(?:def|abbrev|structure|inductive|class|theorem|opaque|instance)\s+([A-Za-z_][\w.'?!]*)", re.M)
# an instance header that names `Tables` on its own line, after the attribute and modifiers it may have
INST_TABLES = re.compile(r"^[ \t]*(?:@\[[^\]]*\][ \t]*)?(?:(?:private|protected|noncomputable|nonrec|public|scoped|local)[ \t]+)*"
                         r"instance\b[^\n]*\bTables\b[^\n]*", re.M)
# a line of a hand-written file that declares something of type `Tables` (an instance by `def`, say)
TABLES_TYPE = re.compile(r":\s*Tables\b")
# what must follow the replay's instance: a blank line, and the first line of the next section of Replay.lean
REPLAY_AFTER = "\n/-! ## The twin's state, entry by entry\n"
# the one instance of `Tables` written by hand, the replay's, as its text must be (Replay.lean)
REPLAY_INSTANCE = 'instance : Tables R :=\n  let _ : MonadStateOf State R := {\n    get := do return (← getThe RSt).twin\n    set := fun s => modifyThe RSt fun rs => { rs with twin := s }\n    modifyGet := fun f => modifyGetThe RSt fun rs => let (a, s) := f rs.twin; (a, { rs with twin := s }) }\n  Tables.ofState fun t => modifyThe RSt fun s => { s with touches := s.touches.push t }\n'


def hand_files(twin):
    """The twin's Lean files that are written by hand: every .lean under it but the three generated ones, what a
    build left, and what is not its sources (the tools' own Lean file among them)."""
    twin = Path(twin)
    return sorted(str(f.relative_to(twin)) for f in twin.rglob("*.lean")
                  if not set(f.relative_to(twin).parts) & set(NOT_SOURCES) and str(f.relative_to(twin)) not in FILES)


def compare(twin):
    """The check itself, which --check prints and every control runs: per generated file (its path, the lines the
    twin's has or None if it is not there, the lines generated, whether the two are the same bytes, the first line
    that differs), and the tripwire's finds (a hand-written file, a name the generated files declare)."""
    validate()
    out = []
    for f, make in FILES.items():
        want = make()
        path = Path(twin, f)
        if not path.is_file():
            out.append((f, None, want.count("\n"), False, "the twin has no such file"))
            continue
        have = path.read_bytes().decode()
        diff = None
        if have != want:
            a, b = have.split("\n"), want.split("\n")
            diff = next((f"line {n + 1}: the file: {x!r}; generated: {y!r}" for n, (x, y) in enumerate(zip(a, b)) if x != y),
                        f"the file has {len(a) - 1} lines, generated {len(b) - 1}")
        out.append((f, have.count("\n"), want.count("\n"), have == want, diff))
    trips, insts, heads = [], [], []
    for f in hand_files(twin):
        text = Path(twin, f).read_text()
        for m in DECL.finditer(text):
            name = m.group(1).split(".")[-1]
            if name in NAMES:
                trips.append((f, m.group(1)))
        here = [m.group(0).strip() for m in INST_TABLES.finditer(text)]
        heads += [(f, h, m.start()) for h, m in zip(here, INST_TABLES.finditer(text))]
        for line in text.split("\n"):
            if TABLES_TYPE.search(line) and line.strip() not in here:
                insts.append(f"{f}: a declaration of type Tables by hand: {line.strip()}")
    allowed = [(f, h, at) for f, h, at in heads if (f, h) == ("SpecTwin/Replay.lean", "instance : Tables R :=")]
    for f, h, _ in heads:
        if (f, h) != ("SpecTwin/Replay.lean", "instance : Tables R :="):
            insts.append(f"{f}: an instance of Tables by hand: {h}")
    if len(allowed) > 1:
        insts.append("SpecTwin/Replay.lean: more than one instance : Tables R")
    replay = Path(twin, "SpecTwin/Replay.lean")
    unit = REPLAY_INSTANCE + REPLAY_AFTER
    text = replay.read_text() if replay.is_file() else ""
    if len(allowed) != 1 or text.count(unit) != 1 or text.index(unit) != allowed[0][2]:
        insts.append("SpecTwin/Replay.lean: its instance of Tables is not the fixed text")
    return out, trips, insts


def differing(twin):
    """What the check finds wrong: the generated files that are not the schema's, and the tripwire's finds."""
    files, trips, insts = compare(twin)
    return [f for f, _, _, same, _ in files if not same] + [f"{f} declares {name}" for f, name in trips] + insts


def check(twin):
    files, trips, insts = compare(twin)
    bad = 0
    for f, n, m, same, diff in files:
        print(f"{f}: {n if n is not None else 'no'} lines in the twin, {m} generated: "
              f"{'the same, byte for byte' if same else 'DIFFERENT  <-- FAIL'}")
        if not same:
            bad += 1
            print(f"   {diff}")
    hand = hand_files(twin)
    for f, name in trips:
        bad += 1
        print(f"{f}: declares {name}, a name the generated files declare  <-- FAIL")
    print(f"the tripwire, in the twin's other files ({', '.join(hand)}): "
          f"{'no matching declaration found' if not trips else str(len(trips)) + ' matching declarations found'} "
          f"({len(NAMES)} names the generated files declare, by a pattern over each line's start: a heuristic)")
    for i in insts:
        bad += 1
        print(f"{i}  <-- FAIL")
    if not insts:
        print(f"the instances of Tables written by hand: one, Replay.lean's, its text as fixed "
              f"({REPLAY_INSTANCE.count(chr(10))} lines)")
    total = sum(m for _, _, m, _, _ in files)
    print(f"{len(files)} of {len(files)} generated files are the schema's, whole, {total} lines; {len(TABLES)} tables"
          if not bad else f"{bad} files or names are NOT the schema's")
    return 1 if bad else 0


def write(twin):
    validate()
    total = 0
    for f, make in FILES.items():
        text = make()
        Path(twin, f).write_text(text)
        total += text.count("\n")
    print(f"written: {len(FILES)} files, {total} lines")
    return 0


def controls(twin, work):
    """The check's controls. Each changes one thing, in the schema or in a copy of the twin's files, and runs the
    check itself (`differing`): it must find what the control names."""
    global TABLES
    ok = True
    kept = TABLES

    def schema(what, change, must):
        nonlocal ok
        global TABLES
        TABLES = copy.deepcopy(kept)
        order = list(STATE_ORDER)
        try:
            change(TABLES)
            d = differing(twin)
        finally:
            TABLES = kept
            STATE_ORDER[:] = order
        good = d == must
        ok &= good
        print(f"control, the schema with {what}: the check finds {', '.join(d) or 'nothing'}"
              f"{'' if good else '  <-- must find ' + ', '.join(must)}")

    S, T, R = FILES
    def rename_read(ts):
        ts[0].read = (ts[0].read[0].rstrip("?") + "X", ts[0].read[1])

    def rename_level(ts):
        ts[1].scans[0].level += "X"

    def rename_table(ts):                   # in the schema's own second list too, or the schema refuses itself
        STATE_ORDER[STATE_ORDER.index(ts[0].name)] = ts[0].name + "x"
        ts[0].name += "x"

    schema("one constructor of Cell renamed", lambda ts: setattr(ts[2], "cell", ts[2].cell + "X"), [S, T, R])
    schema("one operation renamed", rename_read, [T])
    schema("one field of State renamed", lambda ts: setattr(ts[0], "field", ts[0].field + "X"), [S, T, R])
    schema("one level renamed", rename_level, [S, T, R])
    schema("one table's name in a record changed", rename_table, [S, R])
    schema("one doc line of an operation changed", lambda ts: setattr(ts[3], "erase", (ts[3].erase[0], "changed")), [T])

    from schema import Scan, Table      # noqa: E402: shapes which no table of today's schema has

    def tied(**kw):
        a = dict(rows=["tiedRow", "tiedPeerRow"],
                 scans=[Scan("allTiedAll", "tiedAll", "every `tied`"), Scan("allTiedRoot", "tiedRoot", "every `tied[r]`", row=True),
                        Scan("allTiedPeer", "tiedPeer", "every `tied[r][p]`", depth=2)])
        a.update(kw)
        return Table("tied", "tied", "tied", [("r", "Root"), ("p", "Peer"), ("g", "Group")], "pbits",
                     read=("tied?", "`tied[r][p].get(g)`"), write=("setTied", "`tied[r][p][g] = b`"),
                     erase=("eraseTied", "`tied[r][p].pop(g)`"), **a)

    schema("a table of three keys that keeps its rows, added", lambda ts: ts.append(tied()), [S, T, R])

    def refused(what, change, must):
        nonlocal ok
        global TABLES
        TABLES = copy.deepcopy(kept)
        try:
            change(TABLES)
            validate()
            said = None
        except SystemExit as e:
            said = str(e)
        finally:
            TABLES = kept
        good = said is not None and must in said
        ok &= good
        print(f"control, the schema with {what}: {'refused: ' + said if said else 'NOT refused'}"
              f"{'' if good else '  <-- must be refused, saying ' + repr(must)}")

    refused("a table that keeps its rows, one row cell short", lambda ts: ts.append(tied(rows=["tiedRoot"])),
            "one row cell per key but the last")
    refused("a set of two keys", lambda ts: ts[7].keys.append(("p", "Peer")), "a set has one key")
    refused("a bitmap with presence in a table that keeps no rows", lambda ts: setattr(ts[4], "value", "pbits"),
            "a value with presence (pbits, lane) is the value of a table that keeps its rows, and only of one")
    refused("a lane, a value with presence, in a table that keeps no rows",
            lambda ts: setattr(ts[4], "value", "lane"), "a value with presence (pbits, lane)")
    refused("the queue, which keeps its rows, with a lane's value of no presence (a bitmap)",
            lambda ts: setattr(next(t for t in ts if t.name == "queue"), "value", "bits"),
            "a table that keeps its rows has a value with presence")
    refused("a level given as many keys as its table has", lambda ts: ts.append(tied(
        scans=[Scan("allTiedG", "tiedG", "every `tied[r][p][g]`", depth=3)])), "as many outer keys as the table has")
    refused("a key of a type no parser reads", lambda ts: ts[0].keys.__setitem__(0, ("a", "Slot")), "no parser")

    def files(what, edit, must):
        nonlocal ok
        d = Path(work, "twin")
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(twin, d, ignore=shutil.ignore_patterns(*NOT_SOURCES))
        edit(d)
        got = differing(d)
        good = got == must
        ok &= good
        print(f"control, a copy of the twin with {what}: the check finds {', '.join(got) or 'nothing'}"
              f"{'' if good else '  <-- must find ' + ', '.join(must)}")

    def change(f, old, new):
        def edit(d):
            text = (d / f).read_text()
            if text.count(old) != 1:
                raise SystemExit(f"gen.py: a control's text is there {text.count(old)} times in {f}, must be once: {old!r}")
            (d / f).write_text(text.replace(old, new))
        return edit

    def append(f, more):
        return lambda d: (d / f).write_text((d / f).read_text() + more)

    # the cases against a check of slices, which a whole file holds: each must be found
    files("a field added to State after a blank line", change(S, "\n\n/-- An entry of", "\n\n  extra : Nat := 0\n\n/-- An entry of"), [S])
    files("a comment at column 0 and a field after it, in State", change(S, "\n\n/-- An entry of", "\n-- another field\n  extra : Nat := 0\n\n/-- An entry of"), [S])
    files("an arm added to valueAt after a comment", change(R, "\n\n/-- A state with one more entry", "\n  -- by hand\n  | .askedAt _ => none\n\n/-- A state with one more entry"), [R])
    files("the catch-all of put changed", change(R, '  | c, v => throw s!"not a value of {reprStr c}: {reprStr v}"', "  | _, _ => pure s"), [R])
    files("code put on the first line of valueAt", change(R, "def valueAt (s : State) : Cell → Option Val\n", "def valueAt (s : State) : Cell → Option Val := fun c => (fun\n"), [R])
    files("a line after put's body that goes on with it", change(R, '{reprStr v}"\n\n/-- A state without', '{reprStr v}"\n<|> pure s\n\n/-- A state without'), [R])
    def decoy(d):
        # drop's whole declaration, as generated, left inside a comment with its first line still at column 0, and
        # another drop after it. (A check of declarations' bodies would read the commented one and pass.)
        text = (d / R).read_text()
        first = "def drop (s : State) : Cell → State\n"
        doc = "/-- A state without an entry"
        if text.count(first) != 1 or text.count(doc) != 1:
            raise SystemExit(f"gen.py: the decoy control's anchors are not there once each in {R}")
        a = text.index(doc)
        b = text.index("\n\n", text.index(first)) + 1
        (d / R).write_text(text[:a] + "/-\n" + text[a:b] + "-/\n@[inline] def drop (s : State) (_ : Cell) : State := s\n" + text[b:])

    files("drop's whole declaration left inside a comment, its first line at column 0, and another drop after it", decoy, [R])
    files("one operation of ofState without its note", change(T, "  askedAt? a := do note (.read (.askedAt a)); return", "  askedAt? a := do return"), [T])
    files("a table more in ownTables, with a digit in its name", change(S, '["asked_at", ', '["asked_at", "rogue1", '), [S])
    files("a trailing space on one line of Tables.lean", change(T, "namespace Tables\n", "namespace Tables \n"), [T])
    files("State.lean missing", lambda d: (d / S).rename(d / "SpecTwin/State.lean.away"), [S])
    # the tripwire: a name of the generated files declared by hand elsewhere, in another namespace
    files("a second drop declared by hand in Replay.lean, in a namespace of its own",
          append("SpecTwin/Replay.lean", "\nnamespace SpecTwin.Replay.Mine\ndef drop (s : State) (_ : Cell) : State := s\nend SpecTwin.Replay.Mine\n"),
          ["SpecTwin/Replay.lean declares drop"])
    files("a second State declared by hand in a new file",
          lambda d: (d / "SpecTwin/Other.lean").write_text("namespace Other\nstructure State where\n  n : Nat\nend Other\n"),
          ["SpecTwin/Other.lean declares State"])
    files("drop declared by hand with a doc comment on its line, in a namespace of its own",
          append("SpecTwin/Replay.lean", "\nnamespace SpecTwin.Replay.Mine\n/-- mine -/ def drop (s : State) (_ : Cell) : State := s\nend SpecTwin.Replay.Mine\n"),
          ["SpecTwin/Replay.lean declares drop"])
    files("a nonrec drop declared by hand, in a namespace of its own",
          append("SpecTwin/Replay.lean", "\nnamespace SpecTwin.Replay.Mine\nnonrec def drop (s : State) (_ : Cell) : State := s\nend SpecTwin.Replay.Mine\n"),
          ["SpecTwin/Replay.lean declares drop"])
    # the instances of Tables written by hand: one more, or the replay's own changed
    files("a second instance of Tables, by hand, in Sec61.lean",
          append("SpecTwin/Sec61.lean", "\ninstance (priority := high) {ρ : Type} : Tables (ReaderT ρ Id) := sorry\n"),
          ["SpecTwin/Sec61.lean: an instance of Tables by hand: instance (priority := high) {ρ : Type} : Tables (ReaderT ρ Id) := sorry"])
    files("the replay's instance of Tables with its note of each access left out",
          change("SpecTwin/Replay.lean", "{ s with touches := s.touches.push t }", "{ s with touches := s.touches }"),
          ["SpecTwin/Replay.lean: its instance of Tables is not the fixed text"])
    files("the replay's instance of Tables kept whole in a comment, and a live one without the note after it",
          change("SpecTwin/Replay.lean", REPLAY_INSTANCE, "/-\n" + REPLAY_INSTANCE + "-/\n"
                 + REPLAY_INSTANCE.replace("{ s with touches := s.touches.push t }", "{ s with touches := s.touches }")),
          ["SpecTwin/Replay.lean: more than one instance : Tables R",
           "SpecTwin/Replay.lean: its instance of Tables is not the fixed text"])
    files("a line after the replay's instance of Tables that goes on with it",
          change("SpecTwin/Replay.lean", REPLAY_INSTANCE, REPLAY_INSTANCE + "    |> fun s => { s with touches := #[] }\n"),
          ["SpecTwin/Replay.lean: its instance of Tables is not the fixed text"])
    files("a def of type Tables, made an instance by an attribute, in Sec61.lean",
          append("SpecTwin/Sec61.lean", "\n@[instance] def mine {ρ : Type} : Tables (ReaderT ρ Id) := sorry\n"),
          ["SpecTwin/Sec61.lean: a declaration of type Tables by hand: @[instance] def mine {ρ : Type} : Tables (ReaderT ρ Id) := sorry"])
    # two limits, as the docstring says: the tripwire does not find these, and the check says nothing of them
    files("(a limit) drop in guillemets, declared by hand in a namespace of its own",
          append("SpecTwin/Replay.lean", "\nnamespace SpecTwin.Replay.Mine\ndef «drop» (s : State) (_ : Cell) : State := s\nend SpecTwin.Replay.Mine\n"),
          [])
    files("(a limit) drop declared by hand as an axiom, in a namespace of its own",
          append("SpecTwin/Replay.lean", "\nnamespace SpecTwin.Replay.Mine\naxiom drop : Nat\nend SpecTwin.Replay.Mine\n"),
          [])
    for bad in (["--chek", str(twin)], [], ["--check"], ["--check", str(twin), "x"], ["--control", str(twin)]):
        rc = main(bad, quiet=True)
        ok &= rc == 2
        print(f"control, gen.py {' '.join(bad[:1]) or '(no argument)'} with {len(bad)} argument{'s' if len(bad) != 1 else ''}: "
              f"rc={rc}, must be 2 (nothing compared, nothing said to be the schema's)")
    print("ok: every control of the check as it must be" if ok else "controls of the check wrong")
    return 0 if ok else 1


def main(argv, quiet=False):
    if len(argv) == 2 and argv[0] == "--check":
        return check(argv[1])
    if len(argv) == 2 and argv[0] == "--write":
        return write(argv[1])
    if len(argv) == 3 and argv[0] == "--control":
        return controls(argv[1], argv[2])
    if not quiet:
        print("usage: gen.py --check TWINDIR | --write TWINDIR | --control TWINDIR WORKDIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
