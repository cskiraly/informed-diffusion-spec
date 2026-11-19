import Lean.Data.Json
import SpecTwin.Basic

/-! # What the replay's reading of a record starts from

The kinds of value an entry can have in a record (`Val`), the parsers of numbers, keys and lists, and a sort.
Written by hand; the per-table reading built on them is `ReplayTables.lean`, which is generated. -/

namespace SpecTwin.Replay

open Lean (Json)

/-- An entry's value, as a record writes it. A missing or empty entry has none. -/
inductive Val where
  | time (t : UInt64)                     -- a float's bits
  | peers (l : List Peer)                 -- an offer list in its order, or a set of peers sorted
  | bits (b : Nat)                        -- a bitmap
  | flag                                  -- a member of a set
  | count (n : Nat)                       -- a count, not zero
  | key (k : Key)                         -- an ask key
  | state (s : GroupState)                -- a group's state
  | lane (l : List QEntry)                -- a lane of a peer's queue, its entries in order; there and empty is a value
  | waits (l : List (Peer × ChunkF))     -- a root's waiting copies, in order; empty is no value
  | slot (n : Nat)                        -- a slot (`tie_slot`); 0 is a value
  | jobs (l : List Job)                   -- the pace queue's jobs, in order; empty is no value
  | have (e : HaveEntry)                  -- what a peer said it holds of a group, and its ttl
  | push (e : PushEntry)                  -- what the node chose to push a peer, its clock and its ttl
  | desc (d : Descriptor)                 -- a group's descriptor
  | int (n : Int)                         -- a signed count, not zero (the window's `in_flight`)
  | ids (l : List Hex)                    -- a set of opaque ids as hex, sorted (`unwanted[p]`)
  deriving BEq, Repr

/-! ## Reading a record: strictly, so that an altered field cannot pass by wrapping or collapsing -/

def nat (j : Json) : Except String Nat := j.getNat?

/-- A float's IEEE-754 word: 64 bits, and finite, as every time and delay is. -/
def bits64 (j : Json) : Except String UInt64 := do
  let n ← j.getNat?
  if n ≥ 2 ^ 64 then throw s!"not a 64-bit word: {n}"
  if !(Float.ofBits (UInt64.ofNat n)).isFinite then throw s!"not a finite float: {n}"
  return UInt64.ofNat n

/-- A group's key: 64 lowercase hex digits. -/
def group (s : String) : Except String Group := do
  if s.length == 64 && s.all (fun c => ('0' ≤ c ∧ c ≤ '9') ∨ ('a' ≤ c ∧ c ≤ 'f')) then return s
  throw s!"not a group key: {s}"

/-- No key twice in a list that stands for a map or a set. -/
def nodup {α} [BEq α] (what : String) (l : List α) : Except String Unit :=
  if l.eraseDups.length == l.length then pure () else throw s!"{what}: a key twice"

def key (j : Json) : Except String Key :=
  match j with
  | .str s => match Key.ofId s with
    | some k => pure k
    | none => throw s!"not a structured id: {s}"
  | .arr #[.str g, i] => return .want (← group g) (← i.getNat?)
  | _ => throw s!"not an ask key: {j.compress}"

def arr (j : Json) : Except String (List Json) := return (← j.getArr?).toList

def field (j : Json) (k : String) : Option Json := (j.getObjVal? k).toOption

/-- A list of rows, each a pair. -/
def pairs {α β} (what : String) (fa : Json → Except String α) (fb : Json → Except String β) (j : Json) :
    Except String (List (α × β)) := do
  (← arr j).mapM fun e => do
    let #[x, y] ← e.getArr? | throw s!"not a {what} row: {e.compress}"
    return (← fa x, ← fb y)

def peerFloats (j : Json) : Except String (List (Peer × UInt64)) := pairs "peer and time" nat bits64 j

def peers (j : Json) : Except String (List Peer) := do (← arr j).mapM nat

def groupKey (j : Json) : Except String Group := do
  let .str h := j | throw s!"not a group key: {j.compress}"
  group h

def rootKey (j : Json) : Except String Root := do
  let .str h := j | throw s!"not a root: {j.compress}"
  if h.length == 64 && h.all (fun c => ('0' ≤ c ∧ c ≤ '9') ∨ ('a' ≤ c ∧ c ≤ 'f')) then return h
  throw s!"not a root: {h}"

def groupState (j : Json) : Except String GroupState :=
  match j with
  | .str "COLLECTING" => pure .collecting
  | .str "DECODING" => pure .decoding
  | .str "COMPLETE" => pure .complete
  | .str "INVALID" => pure .invalid
  | _ => throw s!"not a group's state: {j.compress}"

def chunk (j : Json) : Except String Chunk := do
  let #[h, i] ← j.getArr? | throw s!"not a chunk: {j.compress}"
  return (← groupKey h, ← nat i)

/-- An entry of an IHAVE, as a record writes it: an id as its hex digits (one of 56 bytes read as a structured
id, any other as it is), or `["bits", group, bitmap]`. -/
def ihaveEntry (j : Json) : Except String IhaveEntry := do
  match j with
  | .arr #[.str "bits", g, b] => return .bitmap (← groupKey g) (← nat b)
  | .str s => match Key.ofId s with
    | some k => return .id k
    | none =>
      if s.length % 2 == 0 && s.all (fun c => ('0' ≤ c ∧ c ≤ '9') ∨ ('a' ≤ c ∧ c ≤ 'f')) && s.length != 112 then
        return .other s
      throw s!"not an IHAVE's entry: {j.compress}"
  | _ => throw s!"not an IHAVE's entry: {j.compress}"

/-- Byte strings as a record writes them: lowercase hex digits, two a byte. -/
def hex (j : Json) : Except String Hex := do
  let .str s := j | throw s!"not a byte string: {j.compress}"
  if s.length % 2 == 0 && s.all (fun c => ('0' ≤ c ∧ c ≤ '9') ∨ ('a' ≤ c ∧ c ≤ 'f')) then return s
  throw s!"not hex digits, two a byte: {s}"

/-- A list of byte strings (a set of ids, as a record writes `unwanted[p]`). -/
def hexes (j : Json) : Except String (List Hex) := do (← arr j).mapM hex

/-- A descriptor, as a record writes it: `[version, hash_id, encoding, count, segment_size,
total_length, root]`. -/
def descriptor (j : Json) : Except String Descriptor := do
  let #[v, h, e, c, s, t, r] ← j.getArr? | throw s!"not a descriptor: {j.compress}"
  return { version := ← nat v, hashId := ← nat h, encoding := ← nat e, count := ← nat c, segmentSize := ← nat s,
           totalLength := ← nat t, root := ← hex r }

def descriptorJson (d : Descriptor) : Json :=
  Json.arr #[d.version, d.hashId, d.encoding, d.count, d.segmentSize, d.totalLength, Json.str d.root]

/-- A blob, as a record writes it: `[length, tag]`, the tag the toy's, its tuples as lists. The twin keeps
the tag as its compact JSON. -/
def blob (j : Json) : Except String Blob := do
  let #[n, tag] ← j.getArr? | throw s!"not a blob: {j.compress}"
  return { n := ← nat n, tag := tag.compress }

def blobJson (b : Blob) : Json := Json.arr #[b.n, (Json.parse b.tag).toOption.getD (Json.str b.tag)]

/-- A chunk as a record writes it: `[group, index, slot, root, id]`, and where it arrives or waits a
sixth member, what level 1 reads of it: `[descriptor, [proof's digests], data]`. Its id is a chunk's structured id,
of its group and index (§2), as the toy's `message_id` makes it. -/
def chunkF (j : Json) : Except String ChunkF := do
  let a ← j.getArr?
  let (five, wide) ← match a with
    | #[g, i, slot, root, mid] => pure ((g, i, slot, root, mid), none)
    | #[g, i, slot, root, mid, w] =>
      let #[d, proof, data] ← w.getArr? | throw s!"not what level 1 reads of a chunk: {w.compress}"
      pure ((g, i, slot, root, mid),
            some { desc := ← (if d == .null then pure none else some <$> descriptor d),    -- none: design B's shape
                   proof := ← (← arr proof).mapM hex, data := ← blob data : Wide })
    | _ => throw s!"not a chunk: {j.compress}"
  let (g, i, slot, root, mid) := five
  let g ← groupKey g
  let i ← nat i
  -- (a chunk with no id, written null: one whose id the document's message_id cannot
  -- give, an index beyond a uint32. The twin holds it as an ask by index, which is no id: `Key.idHex`)
  if mid == .null then return { g, i, slot := ← nat slot, root := ← rootKey root, mid := .want g i, wide }
  let .str mid := mid | throw s!"not a chunk: {j.compress}"
  let some k := Key.ofId mid | throw s!"a chunk's id is not a structured id: {mid}"
  if k.group != g || k.index != i then throw s!"a chunk's id is not of its group and index: {j.compress}"
  return { g, i, slot := ← nat slot, root := ← rootKey root, mid := k, wide }

/-- A block as a record writes it: `[slot, the bid's group id or null, the bid's descriptor or
null]`. -/
def blockOf (j : Json) : Except String Block := do
  let #[sl, gid, d] ← j.getArr? | throw s!"not a block: {j.compress}"
  return { slot := ← nat sl, groupId := ← if gid == .null then pure none else some <$> hex gid,
           desc := ← if d == .null then pure none else some <$> descriptor d }

/-- A lane's name in a record's path: `"urgent"` or `"normal"`. -/
def laneName (j : Json) : Except String Lane :=
  match j with
  | .str "urgent" => pure .urgent
  | .str "normal" => pure .normal
  | _ => throw s!"not a lane: {j.compress}"

/-- A control message of a queue entry: `[kind, ids]`. A PRUNE has no ids in the toy's runs; a GRAFT, a JOIN, a PRUNE
with ids, or another kind is not one the record can hold. -/
def ctl (j : Json) : Except String Ctl := do
  match ← j.getArr? with
  | #[.str "iwant", ids] => return .iwant (← (← arr ids).mapM key)
  | #[.str "ihave", ids] => return .ihave (← (← arr ids).mapM ihaveEntry)
  | #[.str "idontwant", ids] => return .idontwant (← (← arr ids).mapM ihaveEntry)
  | #[.str "prune", .arr #[]] => return .prune
  | _ => throw s!"not a control message of a queue entry: {j.compress}"

/-- A queue entry: `[chunk or null, control or null, solicited]`. -/
def qentry (j : Json) : Except String QEntry := do
  let #[c, ctrl, .bool sol] ← j.getArr? | throw s!"not a queue entry: {j.compress}"
  let chunk ← if c == .null then pure none else some <$> chunkF c
  let control ← if ctrl == .null then pure none else some <$> (← arr ctrl).mapM ctl
  return { chunk, control, solicited := sol }

/-- A lane's value: its entries, in order. -/
def laneEntries (j : Json) : Except String (List QEntry) := do (← arr j).mapM qentry

/-- A root's waiting copies (`pending[root]`): `[[peer, chunk], ...]`, in order. -/
def waitList (j : Json) : Except String (List (Peer × ChunkF)) := do
  (← arr j).mapM fun e => do
    let #[p, f] ← e.getArr? | throw s!"not a waiting copy: {e.compress}"
    return (← nat p, ← chunkF f)

/-- An entry of `peer_has` (§4.3): `[bits, ttl]`. -/
def haveEntry (j : Json) : Except String HaveEntry := do
  let #[b, t] ← j.getArr? | throw s!"not an entry of peer_has: {j.compress}"
  return { bits := ← nat b, ttl := ← nat t }

/-- An entry of `pushed` (§5.2): `[bits, the first push's time as its 64 bits or null, ttl]`. -/
def pushEntry (j : Json) : Except String PushEntry := do
  let #[b, fp, t] ← j.getArr? | throw s!"not an entry of pushed: {j.compress}"
  return { bits := ← nat b, firstPush := ← (if fp == .null then pure none else some <$> bits64 fp), ttl := ← nat t }

/-- An integer that can be negative, as a record writes it: a natural number, or `["-", n]` for −n, n not 0. The
tracer writes no number with a sign (`Strict.lean`). -/
def intOf (j : Json) : Except String Int := do
  match j with
  | .arr #[.str "-", n] =>
    let n ← nat n
    if n == 0 then throw "not an integer of a record: minus zero"
    return -(n : Int)
  | j => return ((← nat j) : Int)

/-- The window's one-entry tables' names in a record's path: `"count"`, `"line"`. -/
def countKey (j : Json) : Except String CountKey :=
  match j with
  | .str "count" => pure .count
  | _ => throw s!"not the window's count's entry: {j.compress}"

def lineKey (j : Json) : Except String LineKey :=
  match j with
  | .str "line" => pure .line
  | _ => throw s!"not the window's line's entry: {j.compress}"

/-- A send's key in a record's path: `[peer, group, index]`. -/
def sendKey (j : Json) : Except String SendKey := do
  let #[p, g, i] ← j.getArr? | throw s!"not a send's key: {j.compress}"
  return (← nat p, ← groupKey g, ← nat i)

/-- The pace queue's one entry's name in a record's path: `"jobs"`. -/
def paceKey (j : Json) : Except String PaceKey :=
  match j with
  | .str "jobs" => pure .jobs
  | _ => throw s!"not the pace queue's entry: {j.compress}"

/-- The pace queue's value (§6.4): `[[peer, [id, ...], time], ...]`, the jobs in order; an id is a chunk's
structured id, a time its 64 bits. -/
def jobList (j : Json) : Except String (List Job) := do
  (← arr j).mapM fun e => do
    let #[q, ids, t] ← e.getArr? | throw s!"not a job of the pace queue: {e.compress}"
    let ids ← (← arr ids).mapM fun x => do
      let .str s := x | throw s!"not a gossip id: {x.compress}"
      let some k := Key.ofId s | throw s!"a gossip id is not a structured id: {s}"
      pure k
    return { q := ← nat q, ids, at_ := ← bits64 t }

def sortBy {α} (f : α → α → Bool) (l : List α) : List α := (l.toArray.qsort f).toList

end SpecTwin.Replay
