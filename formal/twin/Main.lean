import SpecTwin.Replay
import SpecTwin.Strict

/-! `replay [--only fn=NAME|table=NAME] [--content FILE] [TRACE]`: replay a trace of `trace3.py` (JSON lines; stdin
when no file is named, so that a gzipped trace goes through `zcat`) through the twin, and print what matched,
what did not, and how often each branch of the twin ran.

A trace's first line is its content line: what it was made from, each document by the sha256 of its code and each
file of the toy and the tools by the sha256 of its bytes (`tools/content.py`). `--content FILE` gives the line the
caller made over the tree it replays against, and the two must be the same bytes: a trace made from documents with
other code, another toy or other tools fails, and so does every trace where no file is given.
The header is the second line and the nodes line the third (each node's constants and the traced names
its namespace has replaced). A trace also fails with a header that is not its only one, with a record of a node
the nodes line does not name, with a line the tracer would not write (`Strict.lean`: a member given twice, which
the parser would drop in silence, a number that is not a plain integer, white space), with an envelope line that
has a member it should not, or with a trailer whose counts (the records, function by function, and the entries
of rest) are not what was read. -/

open Lean (Json)
open SpecTwin SpecTwin.Replay

/-- The members an envelope line may have, and must have: nothing else passes. -/
def members (what : String) (j : Json) (may must : List String) : Except String Unit := do
  let .ok kvs := j.getObj? | throw s!"{what}: not an object"
  if let some f := kvs.keys.find? (!may.contains ·) then throw s!"{what}: not a member of it: {f}"
  if let some f := must.find? (!kvs.keys.contains ·) then throw s!"{what}: no {f}"

def headerFields : List String :=
  ["format", "whole", "own", "foreign", "traced", "tracer", "args"]

/-- The content line (`tools/content.py`): `{"content":{"files":{NAME:SHA256,...},"version":2}}`, or version 1
(each document named by its bytes, not by its code). Its names with their hashes, or why it is not one. A trace
passes only with the line of `--content`, byte for byte, so the two lines are always of one version. -/
def contentFiles (line : String) : Except String (List (String × String)) := do
  let text := if line.endsWith "\n" then (line.dropEnd 1).toString else line
  Strict.strictLine text
  let j ← Json.parse text
  members "the content line" j ["content"] ["content"]
  let c ← j.getObjVal? "content"
  members "content" c ["files", "version"] ["files", "version"]
  if !([some 1, some 2].contains (c.getObjValAs? Nat "version").toOption) then
    throw "content: its version is neither 1 nor 2"
  let .ok kvs := (← c.getObjVal? "files").getObj? | throw "content: files is not an object"
  kvs.toList.mapM fun (k, v) => do return (k, ← v.getStr?)

/-- Where a trace's content line is not the caller's: the first name, in the names' order, whose hash differs or
that one line alone has. -/
def contentDiff (expected got : String) : String :=
  match contentFiles expected, contentFiles got with
  | .error e, _ => s!"the file given with --content is no content line ({e})"
  | _, .error e => s!"the trace's first line is no content line ({e})"
  | .ok a, .ok b =>
    let names := sortBy (· < ·) ((a.map (·.1) ++ b.map (·.1)).eraseDups)
    match names.find? fun n => a.lookup n != b.lookup n with
    | some n => match a.lookup n, b.lookup n with
      | some _, some _ => s!"{n}: another hash"
      | some _, none => s!"{n}: not in the trace's"
      | _, _ => s!"{n}: in the trace's alone"
    | none => "the same names and hashes, written otherwise"

def constNames : List String :=
  ["IWANT_WINDOW", "RETRY_SLACK", "PROMISE", "PARK_TTL", "MAX_IHAVE_MESSAGES", "MAX_IHAVE_LENGTH", "MAX_PENDING_GROUPS",
   "MAX_PLAIN_CHUNKS", "CANCEL", "PROJECT", "RAREST", "FAN_IN", "UNIT", "MAX_CHUNKS", "MAX_SEGMENT_SIZE",
   "HEARTBEAT", "GOSSIP_FACTOR", "D_LAZY", "PACED", "HAVE_TTL", "GOSSIP_RETRANSMISSION",
   "DESCRIPTOR_IN_CHUNK", "PUSH_TTL", "R_NODE", "GUARD_GRACE", "UPLINK", "STRIPE_UPLINK",
   "W", "WINDOW_TIMEOUT", "SOURCE_OFFERS", "R"]

def consts (j : Json) : Except String Consts := do
  members "consts" j constNames constNames
  let f (k : String) : Except String Float := do return Float.ofBits (← bits64 (← j.getObjVal? k))
  -- STRIPE_UPLINK alone may be +∞: where card 13 is off no uplink reaches the stripe's (the toy writes math.inf;
  -- the cell without-b). Any other float of the line is finite, as `bits64` holds it.
  let fOrInf (k : String) : Except String Float := do
    let v ← j.getObjVal? k
    if v == Json.num (0x7FF0000000000000 : Nat) then return Float.ofBits 0x7FF0000000000000 else f k
  -- a limit the client does not set (§8.2) is written `null`
  let limit (k : String) : Except String (Option Nat) := do
    let v ← j.getObjVal? k
    if v == .null then return none else return some (← v.getNat?)
  return { IWANT_WINDOW := ← f "IWANT_WINDOW", RETRY_SLACK := ← f "RETRY_SLACK", PROMISE := ← f "PROMISE",
           PARK_TTL := ← f "PARK_TTL", MAX_IHAVE_MESSAGES := ← limit "MAX_IHAVE_MESSAGES",
           MAX_IHAVE_LENGTH := ← limit "MAX_IHAVE_LENGTH", MAX_PENDING_GROUPS := ← limit "MAX_PENDING_GROUPS",
           MAX_PLAIN_CHUNKS := ← (← j.getObjVal? "MAX_PLAIN_CHUNKS").getNat?,
           CANCEL := ← (← j.getObjVal? "CANCEL").getBool?, PROJECT := ← (← j.getObjVal? "PROJECT").getBool?,
           RAREST := ← (← j.getObjVal? "RAREST").getBool?, FAN_IN := ← (← j.getObjVal? "FAN_IN").getNat?,
           UNIT := ← (← j.getObjVal? "UNIT").getNat?, MAX_CHUNKS := ← (← j.getObjVal? "MAX_CHUNKS").getNat?,
           MAX_SEGMENT_SIZE := ← (← j.getObjVal? "MAX_SEGMENT_SIZE").getNat?,
           HEARTBEAT := ← f "HEARTBEAT", GOSSIP_FACTOR := ← f "GOSSIP_FACTOR",
           D_LAZY := ← (← j.getObjVal? "D_LAZY").getNat?, PACED := ← (← j.getObjVal? "PACED").getBool?,
           HAVE_TTL := ← (← j.getObjVal? "HAVE_TTL").getNat?,
           GOSSIP_RETRANSMISSION := ← (← j.getObjVal? "GOSSIP_RETRANSMISSION").getNat?,
           DESCRIPTOR_IN_CHUNK := ← (← j.getObjVal? "DESCRIPTOR_IN_CHUNK").getBool?,
           PUSH_TTL := ← (← j.getObjVal? "PUSH_TTL").getNat?,
           R_NODE := ← (← j.getObjVal? "R_NODE").getNat?, GUARD_GRACE := ← f "GUARD_GRACE",
           UPLINK := ← f "UPLINK", STRIPE_UPLINK := ← fOrInf "STRIPE_UPLINK",
           W := ← limit "W", WINDOW_TIMEOUT := ← f "WINDOW_TIMEOUT",
           R := ← (← j.getObjVal? "R").getNat?,
           SOURCE_OFFERS_PUBLISH := ← (match ← j.getObjVal? "SOURCE_OFFERS" with
             | .str "ACK" => pure false
             | .str "PUBLISH" => pure true
             | v => throw s!"consts: SOURCE_OFFERS is ACK or PUBLISH: {v.compress}") }

/-- The traced names a node may run as something else, where the twin then asks the node. -/
def replaceable : List String := ["forward", "on_iwant", "push_rebuilt", "validate_chunk"]

/-- The replaceable names taken in a trace of the whole state alone (a directed set): a scenario's level 1. No cell
runs anything but the document's `validate_chunk`; a cell's nodes line that names it is refused. -/
def replaceableWhole : List String := ["validate_chunk"]

/-- The nodes line: its entries, each `{"n": [node, ...], "consts": {...}, "replaced": [name, ...]}`.
Every node once; a replaced name is one the twin has a question for. -/
def nodesLine (j : Json) : Except String (List (Nat × Consts × List String)) := do
  let mut out : List (Nat × Consts × List String) := []
  for e in (← j.getArr?) do
    members "nodes" e ["n", "consts", "replaced"] ["n", "consts", "replaced"]
    let cj ← e.getObjVal? "consts"
    let c ← (consts cj).mapError ("nodes: " ++ ·)
    let rp ← names "nodes: replaced" (← e.getObjVal? "replaced")
    if let some f := rp.find? (!replaceable.contains ·) then
      throw s!"nodes: a replaced function the twin has no question for: {f}"
    let ids ← (← (← e.getObjVal? "n").getArr?).toList.mapM (·.getNat?)
    if ids.isEmpty then throw "nodes: an entry of no node"
    for n in ids do
      if out.any (·.1 == n) then throw s!"nodes: a node twice: {n}"
      out := (n, c, rp) :: out
  return out

structure Tally where
  records : Nat := 0
  ok : Nat := 0
  perFn : Std.HashMap String (Nat × Nat) := {}
  branches : Std.HashMap String Nat := {}
  fewer : Std.HashMap String Nat := {}  -- per function: reads of the Python's that the twin did not make
  reasons : Std.HashMap String Nat := {}
  examples : Array String := #[]

def sorted (m : Std.HashMap String Nat) : List (String × Nat) := sortBy (·.1 < ·.1) m.toList

def main (args : List String) : IO UInt32 := do
  -- `--only fn=NAME` or `--only table=NAME`: a mutant's replay. Only the records whose line says, at its end,
  -- that the call reached that function, or touched that table, are read (and, for a replaceable name, the
  -- records that ask it on the tape: `asks` below); the others are counted and skipped
  -- unparsed, and of the trailer only the count of records is then checked.
  let (only?, args) := match args with
    | "--only" :: w :: rest => (some w, rest)
    | rest => (none, rest)
  -- `--content FILE`: the content line the caller made over the tree it replays against (`tools/content.py`). The
  -- trace's first line must be that line, byte for byte. With no file given nothing is compared, and the trace
  -- does not pass.
  let (contentFile?, files) := match args with
    | "--content" :: f :: rest => (some f, rest)
    | rest => (none, rest)
  let expected? ← match contentFile? with
    | some f => some <$> IO.FS.readFile f
    | none => pure none
  -- A name a node may replace is asked on the tape where it is replaced, and is not among what the record
  -- reached there; the twin's code under that name still runs at such a record (the line that asks the node). So
  -- `fn=NAME` takes those records too, for the replaceable names alone, by the tape entry's text, `["NAME",`,
  -- anywhere in the line: the tape is not at the line's end, and the line is not parsed before it is picked.
  -- Text that only looks like such an entry takes a record more. A pick may take too much, never too little.
  let asks (line : String) (f : String) : Bool :=
    replaceable.contains f && (line.splitOn s!"[\"{f}\",").length > 1
  let picked (line : String) (tail : List String × List String) : Bool := match only? with
    | none => true
    | some w => match w.splitOn "=" with
      | ["fn", f] => tail.1.contains f || asks line f
      | ["table", t] => tail.2.contains t
      | _ => false
  if let some w := only? then
    if !(match w.splitOn "=" with | ["fn", _] | ["table", _] => true | _ => false) then
      throw (IO.userError s!"replay: --only {w}: it is fn=NAME or table=NAME")
  let mut skipped := 0
  let h ← match files with
    | [] => IO.getStdin
    | [f] => IO.FS.Stream.ofHandle <$> IO.FS.Handle.mk f .read
    | _ => throw (IO.userError "usage: replay [--only fn=NAME|table=NAME] [--content FILE] [TRACE]")
  let mut headerOk := false
  let mut contentOk := false            -- the trace's first line is the caller's content line
  let mut headers := 0
  let mut nodes : Std.HashMap Nat (Consts × List String) := {}   -- each node's constants and replaced names
  let mut nodesSeen := false
  let mut whole := false                -- the header's: a trace of the whole state (a directed set)
  let mut traced? : Option (List String) := none   -- the functions the tracer traced, as the header lists them
  let mut t : Tally := {}
  let mut trailer : Option Nat := none
  let mut trailerRest : Option Nat := none
  let mut trailerByFn : Option (List (String × Nat)) := none
  let mut byFn : Std.HashMap String Nat := {}       -- records per function, a raise apart, as the tracer counts
  let mut restRead := 0                 -- entries of `rest` read, over the records: the trailer says how many
  let mut framed := true                -- the trailer is the trace's last line, and its only trailer
  let mut refused := 0                  -- lines the strict scan or the parser refused: none may be
  let mut lineNo := 0
  repeat
    let line ← h.getLine
    if line.isEmpty then break
    lineNo := lineNo + 1
    if lineNo == 1 then                 -- the content line, and nothing else, is the trace's first line
      match expected? with
      | none => IO.println "content: not compared (no --content given): the trace does not pass"
      | some e =>
        if line == e then
          match contentFiles line with
          | .ok fs =>
            contentOk := true
            IO.println s!"content: as --content's, {fs.length} names"
          | .error x => IO.println s!"content: the line is --content's, and is no content line: {x}"
        else IO.println s!"content: NOT --content's: {contentDiff e line}"
      continue
    let tail? := Replay.lineTail line
    if only?.isSome then
      if let some tail := tail? then
        if !picked line tail then
          skipped := skipped + 1
          continue
    -- The line's text is read strictly first (`Strict.lean`), and only a line that passes is parsed: the parser
    -- keeps the last of two members of one name and drops the other, and it would work through a number with a
    -- huge exponent before the scan could refuse it. A refused line is not read as anything: it fails the trace.
    let j ← match (do
        Strict.strictLine (if line.endsWith "\n" then (line.dropEnd 1).toString else line)
        Json.parse line : Except String Json) with
      | .ok j => pure j
      | .error e =>
        refused := refused + 1
        if refused ≤ 20 then IO.println s!"line {lineNo}: not a line the tracer writes: {e}"
        continue
    if trailer.isSome then              -- nothing after the trailer: a later one cannot undo a wrong count
      if framed then IO.println "trailer: a line after the trailer"
      framed := false
      continue
    let envelope (what : String) (inner : Json) (may must : List String) : Except String Unit := do
      members s!"the {what} line" j [what] [what]
      members what inner may must
    if let .ok _ := j.getObjVal? "content" then   -- the content line is the trace's first line, and no other is one
      IO.println "content: a content line that is not the trace's first line"
      contentOk := false
      headerOk := false
      continue
    if let .ok hd := j.getObjVal? "header" then
      IO.println s!"header: {hd.compress}"
      headers := headers + 1
      if let .error e := envelope "header" hd headerFields ["format", "whole", "own", "foreign", "traced"] then
        IO.println e
        headers := headers + 1          -- a header that is not one: as a second header, it fails the trace
      if (hd.getObjValAs? Bool "whole").toOption.isNone then
        IO.println "header: whole is not true or false"
        headers := headers + 1
      whole := (hd.getObjValAs? Bool "whole").toOption == some true
      if headers > 1 || nodesSeen || t.records > 0 || lineNo != 2 then  -- one header, the second line: a later one cannot undo a failure
        IO.println "header: not the trace's second line, or not its only header"
        headerOk := false
        continue
      let format := (hd.getObjValAs? Nat "format").toOption
      let tables (k : String) := (hd.getObjValAs? (List String) k).toOption
      -- the twin's own tables, as the schema names them (`ownTables`, generated), and the other sections' it reads
      let schema := tables "own" == some ownTables
        && tables "foreign" == some ["known_id", "chunks"]      -- (`unwanted` is the twin's own)
      -- the functions traced: sorted names, none twice; a record's `reached` names none but these
      traced? := (do names "traced" (← hd.getObjVal? "traced") : Except String (List String)).toOption
      headerOk := contentOk && format == some 7 && schema && traced?.isSome
      if traced?.isNone then IO.println "header: traced is not a sorted list of names, none twice"
      -- a subset names a function the header lists as traced, or a table of the twin's own: else it would pick
      -- no record, and a mutant replayed on it would pass unread
      if let some w := only? then
        let known := match w.splitOn "=" with
          | ["fn", f] => (traced?.getD []).contains f
          | ["table", tb] => ownTables.contains tb
          | _ => false
        if !known then
          IO.println s!"subset: --only {w}: not a function the header lists as traced, nor a table of the twin's own"
          headerOk := false
      if format != some 7 then IO.println s!"header: format {format}, this replay reads format 7"
      if !schema then IO.println "header: the tables are not this twin's (own, foreign)"
      continue
    if let .ok nj := j.getObjVal? "nodes" then
      if nodesSeen || t.records > 0 || lineNo != 3 then  -- one nodes line, the third line: a later one cannot change a
        IO.println "nodes: not the trace's third line, or a second nodes line"   --   node's constants for later records
        headerOk := false
        continue
      nodesSeen := true
      match (do members "the nodes line" j ["nodes"] ["nodes"]; nodesLine nj : Except String _) with
      | .ok l =>
        nodes := l.foldl (fun m (n, c, rp) => m.insert n (c, rp)) nodes
        if let some (n, _, rp) := l.find? fun (_, _, rp) => !whole && rp.any replaceableWhole.contains then
          IO.println s!"nodes: node {n} has replaced {rp.filter replaceableWhole.contains}, which only a trace of the whole state may"
          headerOk := false
        -- (a replaced name is one of the names the trace traces: push_rebuilt at a v2 node, whose header leaves
        -- it out, is refused here, also where no record of the node exercises it)
        if let some tr := traced? then
          if let some (n, _, rp) := l.find? fun (_, _, rp) => rp.any (!tr.contains ·) then
            IO.println s!"nodes: node {n} has replaced {rp.filter (!tr.contains ·)}, which the header does not list as traced"
            headerOk := false
      | .error e =>
        IO.println e
        headerOk := false
      continue
    if let .ok tj := j.getObjVal? "trailer" then
      IO.ofExcept (envelope "trailer" tj ["records", "by_fn", "rest"] ["records", "by_fn", "rest"])
      trailer := some (← IO.ofExcept (tj.getObjValAs? Nat "records"))
      trailerRest := some (← IO.ofExcept (tj.getObjValAs? Nat "rest"))
      trailerByFn := some (← IO.ofExcept do
        let .ok kvs := (← tj.getObjVal? "by_fn").getObj? | throw "trailer: by_fn is not an object"
        kvs.toList.mapM fun (k, v) => do return (k, ← v.getNat?))
      continue
    if !nodesSeen then throw (IO.userError "a record before the nodes line")
    t := { t with records := t.records + 1 }
    let r ← match (do
        let r ← record j
        -- the line must end with the two members a subset is picked by, saying what the record says
        if tail? != some (r.reached, r.tables) then throw "its line does not end with reached and tables, as the record has them"
        -- and a call reaches only functions the tracer traced
        if let some tr := traced? then
          if let some f := r.reached.find? (!tr.contains ·) then
            throw s!"reached: a function the header does not list as traced: {f}"
        -- and it is a record of a node the nodes line names
        if !nodes.contains r.n then throw s!"n: a node the nodes line does not name: {r.n}"
        pure r : Except String Record) with
      | .ok r => pure r
      | .error e =>                     -- a malformed record is a mismatch at itself
        let reason := s!"malformed record: {(e.splitOn ":").head!}"
        t := { t with reasons := t.reasons.insert reason (t.reasons.getD reason 0 + 1) }
        if t.examples.size < 20 then t := { t with examples := t.examples.push s!"malformed record: {e}" }
        continue
    restRead := restRead + r.rest.length
    let counted := if r.raises.isSome then r.fn ++ " (raises)" else r.fn
    byFn := byFn.insert counted (byFn.getD counted 0 + 1)
    let (n, ok) := t.perFn.getD r.fn (0, 0)
    let some (c, rp) := nodes[r.n]? | throw (IO.userError "a record of no node")   -- (checked above)
    match run c rp (traced?.getD []) r with
    | .ok (marks, fewer) =>
      t := { t with ok := t.ok + 1, perFn := t.perFn.insert r.fn (n + 1, ok + 1),
                    branches := marks.foldl (fun m b => m.insert b (m.getD b 0 + 1)) t.branches,
                    fewer := if fewer == 0 then t.fewer else t.fewer.insert r.fn (t.fewer.getD r.fn 0 + fewer) }
    | .error e =>
      -- one line, whatever a printed value holds: the reports are read line by line
      let reason := (s!"{r.fn}: {(e.splitOn ":").take 2 |> String.intercalate ":"}").replace "\n" " "
      t := { t with perFn := t.perFn.insert r.fn (n + 1, ok), reasons := t.reasons.insert reason (t.reasons.getD reason 0 + 1) }
      if t.examples.size < 20 then
        let ex := (s!"node {r.n} at {Float.ofBits r.t} {r.fn}{(Json.arr r.args).compress}: {e}").replace "\n" " "
        t := { t with examples := t.examples.push ex }
  IO.println s!"replay: {t.records} records, {t.ok} ok, {t.records - t.ok} mismatched"
  if refused > 0 then IO.println s!"lines refused before they were parsed, or by the parser: {refused}"
  if only?.isSome then IO.println s!"subset: --only {only?.getD ""}: {skipped} records skipped unread"
  match trailer with
  | some n => if n != t.records + skipped then IO.println s!"trailer: {n} records written, {t.records + skipped} read"
  | none => IO.println "trailer: none (the trace is cut off)"
  let restOk := only?.isSome || trailerRest == some restRead     -- a subset reads no skipped record's rest
  if trailer.isSome && !restOk then
    IO.println s!"trailer: {trailerRest} entries of rest written, {restRead} read"
  let byFnOk := only?.isSome || trailerByFn.map (sortBy (·.1 < ·.1) ·) == some (sortBy (·.1 < ·.1) byFn.toList)
  if trailer.isSome && !byFnOk then
    IO.println s!"trailer: by_fn is not the records read, function by function: {trailerByFn}"
  if headers == 0 then IO.println "header: none"       -- said, so that a reader of the report need not infer it
  if !nodesSeen then IO.println "nodes: none"
  for (f, n, ok) in sortBy (·.1 < ·.1) (t.perFn.toList.map fun (f, (n, ok)) => (f, n, ok)) do
    IO.println s!"fn {f}: {n} records, {ok} ok"
  for (b, n) in sorted t.branches do
    IO.println s!"branch {b}: {n}"
  IO.println s!"reads of the Python's that the twin did not make: {t.fewer.fold (fun a _ n => a + n) 0}"
  for (f, n) in sorted t.fewer do
    IO.println s!"fewer {f}: {n}"
  for (reason, n) in sorted t.reasons do
    IO.println s!"mismatch {reason}: {n}"
  for e in t.examples do
    IO.println s!"example: {e}"
  return if headerOk && framed && refused == 0 && headers == 1 && nodesSeen && t.ok == t.records
    && trailer == some (t.records + skipped) && restOk && byFnOk then 0 else 1
