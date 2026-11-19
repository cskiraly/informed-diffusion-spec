import Main
import Lean

/-! Which declarations of the replay make a `Tables` value: asked of Lean's own environment, after the build.

`gen.py --check` reads the hand-written files' text for an instance of `Tables` (one header, its text fixed). A
text rule sees the spellings it names (`SpecTwin.Tables`, a parenthesised type, an abbreviation and a definition
without its type written pass it). This file asks the built modules instead. Run in the built copy of the twin:

    lake env lean tools/gen/TablesMakers.lean

It imports `Main`, and so every module the replay is built from, and goes through every constant of the modules
that are the twin's own, the generated `SpecTwin.Tables` apart. Which modules are the twin's own is given from
outside, in TWIN_MODULES, by `makers.py`, from the files of the twin's directory: a module is the twin's because
its source lies there, whatever its name (one named `Lean.Extra` too). Every one of them that the replay imports
is read. A module that the replay imports and that is not in that list must be the toolchain's, by where its
compiled file lies (inside the toolchain's own library directory, by real paths and at a component's boundary:
`inside`), not by its name. It
lists each one
- that mentions `Tables.mk`, `Tables.mk._flat_ctor`, `Tables.ofState` or `Tables.lift` in its type or its value (an
  `opaque` constant's value too): the two constructors, and the two functions of the generated file that build a `Tables` value, from a
  state or from another one. That these four and the instance through `ReaderT` are all the generated file has
  that give a `Tables` is checked here too, against the module as built (`generated`). A `Tables`
  value that is not the generated file's own is built through one of the three, however it is written: an
  instance, a definition with or without its type, an abbreviation, a structure update, a `let` inside a function;
- or whose type, with every argument given and definitions unfolded, is a `Tables` (an axiom, an `opaque`
  constant and a `sorry` are of this kind).
The list must be the replay's one instance, by `Tables.ofState` (`expected`): anything else is an error, and
`lean` then ends with exit code 1.

What it does not see: a module the replay does not import; a value cast into a `Tables` inside a function
(`unsafeCast`), and a foreign function (`extern`) that returns one; `implemented_by` and `csimp`, which change what
the compiled replay calls without making a `Tables` value (the function put in its place is itself a constant, and
is read here like any other); and what the one instance does, which is the fixed text `gen.py --check` holds it
to. -/

open Lean Meta

/-- Does `e` mention the constant `n`? -/
def mentions (e : Expr) (n : Name) : Bool := (e.find? fun x => x.isConstOf n).isSome

/-- Is a value of this type, once every argument is given, a `Tables`? Definitions are unfolded. -/
def givesTables (type : Expr) : MetaM Bool :=
  forallTelescopeReducing type fun _ body => do
    return (← whnf body).getAppFn.isConstOf ``SpecTwin.Tables

/-- Is the file `p` inside the directory `d`? Both by their real paths (links and `..` resolved), and at a path
component's boundary: `lib/lean-extra/X` is not inside `lib/lean`, though its text begins with it. -/
def inside (p d : System.FilePath) : IO Bool := do
  let p ← IO.FS.realPath p
  let d ← IO.FS.realPath d
  return p.toString.startsWith (d.toString ++ "/")

/-- The functions that build a `Tables` value: the class's constructor, the second constructor Lean makes for a
structure (`mk._flat_ctor`, which the first version of this list lacked: `generated` below found it), and the
generated file's two. -/
def makers : List Name :=
  [``SpecTwin.Tables.mk, `SpecTwin.Tables.mk._flat_ctor, ``SpecTwin.Tables.ofState, ``SpecTwin.Tables.lift]

/-- What the generated `SpecTwin.Tables` has that gives a `Tables`: the four makers, and the instance through
`ReaderT`, which lifts the one a monad has. -/
def generated : List String :=
  ["SpecTwin.Tables.instReaderT", "SpecTwin.Tables.lift", "SpecTwin.Tables.mk", "SpecTwin.Tables.mk._flat_ctor",
   "SpecTwin.Tables.ofState"]

/-- What the list must be: the replay's one instance. -/
def expected : List String :=
  ["SpecTwin.Replay.instTablesR (SpecTwin.Replay): a Tables value; mentions [SpecTwin.Tables.ofState]"]

#eval show MetaM Unit from do
  let env ← getEnv
  let some listed ← IO.getEnv "TWIN_MODULES" | throwError "TWIN_MODULES is not set: the twin's modules, by its files"
  let twins := (listed.splitOn " ").filter (· != "")
  let own (m : Name) : Bool := twins.contains m.toString
  let mut gen : Array String := #[]
  let mut found : Array String := #[]
  let mut scanned := 0
  let mut mods : Std.HashSet Name := {}
  for (name, info) in env.constants.map₁.toList do
    let some idx := env.getModuleIdxFor? name | continue
    let mod := env.header.moduleNames[idx.toNat]!
    if !own mod then continue
    mods := mods.insert mod
    if mod == `SpecTwin.Tables then
      if ← (try givesTables info.type catch _ => pure true) then gen := gen.push name.toString
      continue
    scanned := scanned + 1
    let exprs := info.type :: (info.value? (allowOpaque := true)).toList
    let uses := makers.filter fun mk => exprs.any (mentions · mk)
    let gives ← try givesTables info.type catch _ => pure true      -- a type that cannot be read counts as one
    if !uses.isEmpty || gives then
      found := found.push s!"{name} ({mod}): {if gives then "a Tables value" else "not a Tables value"}; mentions {uses}"
  let listed := found.toList.mergeSort
  IO.println s!"the makers of a Tables value, by Lean's own account of the replay as built (gen/TablesMakers.lean):"
  IO.println s!"  the replay's modules that are the twin's own, by its files: {(mods.toList.map toString).mergeSort}"
  -- Every other module the replay imports must be the toolchain's, by where its compiled file lies and not by its
  -- name: under the toolchain's own library directory. (A library of the twin's package whose sources lie outside
  -- the twin's directory, named `Lake.X`, is no file of the twin and has a toolchain's name: its compiled file
  -- lies in the package's build directory, and that tells it.) And each of the twin's own lies in the build here.
  let tc := (← Lean.findSysroot) / "lib" / "lean"
  let here := (← IO.currentDir) / ".lake" / "build"
  -- the test of place, tried on two real files before it is used: a file beside a directory whose name begins its
  -- own (`Init.olean` and `Init/`), which a comparison of the paths as text takes for inside; and a path with `..`
  if ← inside (tc / "Init.olean") (tc / "Init") then
    throwError "the test of place takes lib/lean/Init.olean for a file inside lib/lean/Init"
  if !(← inside (tc / "Init" / ".." / "Init.olean") tc) || (← inside (tc / "Init" / ".." / ".." / "lean" / "Init.olean") (tc / "Init")) then
    throwError "the test of place does not resolve a path with .. in it"
  let mut strangers : Array String := #[]
  let mut others := 0
  for mod in env.header.moduleNames do
    let p ← Lean.findOLean mod
    if own mod then
      if !(← inside p here) then strangers := strangers.push s!"{mod} (one of the twin's files by its name, compiled at {p})"
    else
      others := others + 1
      if !(← inside p tc) then strangers := strangers.push s!"{mod} (compiled at {p})"
  IO.println s!"  the other modules it imports: {others}, each compiled under the toolchain's own library directory"
  if !strangers.isEmpty then
    throwError "the replay imports a module that is neither a file of the twin nor the toolchain's: {strangers.toList}"
  if gen.toList.mergeSort != generated then
    throwError "the generated SpecTwin.Tables gives a Tables by other constants than the five known: {gen.toList.mergeSort}"
  IO.println s!"  their constants, the generated SpecTwin.Tables apart: {scanned}"
  for l in listed do IO.println s!"  {l}"
  if !mods.contains `SpecTwin.Tables || !mods.contains `SpecTwin.Replay then
    throwError "the replay's modules do not hold SpecTwin.Tables and SpecTwin.Replay: this is not the twin"
  if listed != expected then
    throwError "the makers of a Tables value are not the replay's one instance alone: {listed.length} listed, expected {expected}"
  IO.println "  ok: the replay's one instance, by Tables.ofState, and nothing else"
