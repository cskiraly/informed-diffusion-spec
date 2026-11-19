/-! # A trace's line, read strictly before it is parsed

Lean's JSON parser builds an object as a map: of two members with one name it keeps the last and drops the
other, in silence. A record with `"ret":false,"ret":true` would then be read as returning `true`. So before a
line is parsed, `strictLine` walks its text once and refuses what the tracer never writes. Only a line that
passes is given to the parser (`Main.lean`), so the parser never works on a line the scan refuses:

- a member name given twice in one object;
- an escape in a string, a member's name or a value (two spellings of one name would be two members to this scan
  and one to the parser; two spellings of one value would be one value to the parser and two texts to anything
  that searches the trace);
- a number that is not a plain integer without a sign: an exponent, a fraction, a minus, a plus, a leading zero
  (the tracer writes no negative number; a time is the 64 bits of its float, as a natural number);
- white space outside strings;
- anything that is not one JSON value from the line's start to its end.

(Comparing the line's length with that of its compact form after parsing would not do: a number written with an
exponent is shorter than its compact form, and that pays for a duplicated member.) -/

namespace SpecTwin.Strict

/-- The scan's place in the line, or what it refuses. -/
abbrev Scan := Except String Nat

private def at? (cs : Array Char) (i : Nat) : Option Char := cs[i]?

/-- A string, from its opening quote at `i`: the index after its closing quote. An escape is refused. -/
partial def string (cs : Array Char) (i : Nat) : Scan :=
  if at? cs i != some '"' then throw s!"a string expected at {i}" else go (i + 1)
where
  go (i : Nat) : Scan :=
    match at? cs i with
    | none => throw "a string that does not end"
    | some '"' => pure (i + 1)
    | some '\\' => throw s!"an escape in a string, at {i}"
    | some _ => go (i + 1)

/-- A natural number from `i`: digits, with no sign and no leading zero. -/
def integer (cs : Array Char) (i : Nat) : Scan := do
  let mut j := i
  while (at? cs j).any Char.isDigit do j := j + 1
  if j == i then throw s!"a number expected at {i}"
  if at? cs i == some '0' && j != i + 1 then throw s!"a number with a leading zero, at {i}"
  if (at? cs j).any fun c => c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-' then
    throw s!"a number that is not a plain integer, at {i}"
  return j

def literal (cs : Array Char) (i : Nat) (word : String) : Scan :=
  if (cs.extract i (i + word.length)).toList == word.toList then pure (i + word.length)
  else throw s!"not a value at {i}"

mutual
  /-- One value from `i`: the index after it. -/
  partial def value (cs : Array Char) (i : Nat) : Scan :=
    match at? cs i with
    | some '{' => if at? cs (i + 1) == some '}' then pure (i + 2) else members cs (i + 1) []
    | some '[' => if at? cs (i + 1) == some ']' then pure (i + 2) else items cs (i + 1)
    | some '"' => string cs i
    | some 't' => literal cs i "true"
    | some 'f' => literal cs i "false"
    | some 'n' => literal cs i "null"
    | some c =>
      if c.isDigit then integer cs i
      else if c == '-' || c == '+' then throw s!"a number with a sign, at {i}"
      else if c.isWhitespace then throw s!"white space outside a string, at {i}"
      else throw s!"not a value at {i}"
    | none => throw "a value expected at the line's end"

  /-- An object's members from `i`, after `{` or a comma; `seen` has the names so far. -/
  partial def members (cs : Array Char) (i : Nat) (seen : List (List Char)) : Scan := do
    let j ← string cs i
    let name := (cs.extract (i + 1) (j - 1)).toList
    if seen.contains name then throw s!"a member twice in one object: {String.ofList name}"
    if at? cs j != some ':' then throw s!"a colon expected at {j}"
    let k ← value cs (j + 1)
    match at? cs k with
    | some ',' => members cs (k + 1) (name :: seen)
    | some '}' => pure (k + 1)
    | _ => throw s!"a comma or a closing brace expected at {k}"

  /-- An array's items from `i`, after `[` or a comma. -/
  partial def items (cs : Array Char) (i : Nat) : Scan := do
    let k ← value cs i
    match at? cs k with
    | some ',' => items cs (k + 1)
    | some ']' => pure (k + 1)
    | _ => throw s!"a comma or a closing bracket expected at {k}"
end

/-- A line of a trace, without its newline: one value, as the tracer writes one. -/
def strictLine (line : String) : Except String Unit := do
  let cs := line.toList.toArray
  let j ← value cs 0
  if j != cs.size then throw s!"something after the line's value, at {j}"

end SpecTwin.Strict
