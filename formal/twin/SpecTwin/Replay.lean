import Lean.Data.Json
import SpecTwin.Sec61
import SpecTwin.Sec44
import SpecTwin.Sec42
import SpecTwin.Sec72
import SpecTwin.Sec64
import SpecTwin.Sec46
import SpecTwin.Sec43
import SpecTwin.Sec41
import SpecTwin.Sec1
import SpecTwin.Sec2
import SpecTwin.Sec3
import SpecTwin.Sec52
import SpecTwin.Sec53
import SpecTwin.Sec54
import SpecTwin.Sec71
import SpecTwin.ReplayTables

/-! # Replaying a trace of the toy through the twin

A record is one top-level call into §6.1 at one node (`tools/trace3.py`): the entries of §6.1's
state that the Python read, with their values before the call (`reads`, and `scans` for the levels it read as a
whole), the entries it wrote, with their values after (`writes`), the tape of what §6.1's own code asked the rest
of the node, with the answers, and the return value.

Every record also has `rest`: entries the call did not read, with their values before it. In any trace these are
the entries the call wrote without reading (so that an erase that erases nothing shows); in a trace of the whole
state (the directed records) they are every other entry of the node's state too.

The replay loads `reads` and `rest` as the twin's state, runs the twin's function with the record's arguments, and
answers each question from the tape (the question must be the tape's next entry, with the same arguments). A
record passes if:
1. the return value, or the raise, is the Python's;
2. the tape is used up, question for question;
3. the twin's whole state afterwards is `reads` and `rest` with the record's `writes` applied, entry for entry,
   whatever the twin's tables noted; and by their notes the twin wrote the entries the Python wrote, and no other
   (but one it leaves as the record holds it);
4. by their notes the twin read no entry that the Python did not read (but one it wrote itself before): none
   of `rest`, by a read or by a scan.
The state is compared before the notes, so a mismatch reported as "footprint" is one where the return value, the
tape and the state, as far as the record holds the state, were all the Python's.
An entry that is empty counts as missing (§8.1): before v0.10 the toy created empty entries on reads, and since
v0.10 an entry that is emptied stays empty in its table. -/

namespace SpecTwin.Replay

open Lean (Json)

/-- One entry of the tape: a question §6.1 asked, with its arguments and the toy's answer. -/
inductive Entry where
  | expired (g : Group) (r : Bool)
  | connectedTopicPeers (r : List Peer)
  | ownOrder (xs : List Peer) (a : Key) (r : List Peer)
  | listed (p : Peer) (r : Nat)
  | enqueue (p : Peer) (msg : Msg) (urgent : Bool) (r : Bool)
  | after (delay : UInt64) (t : Timer)
  | readKnownId (g : Group) (i : Nat) (k : Option Key)  -- `known_id[g].get(i)`
  | authenticable (g : Group) (r : Bool)
  | shuffled (xs : List Key) (r : List Key)
  | shuffledNats (xs : List Nat) (r : List Nat)         -- of peers, or of indices
  | readChunkAt (g : Group) (i : Nat) (f : ChunkF)      -- `chunks[g][i]`
  | validHave (g : Group) (bits : Nat) (r : Bool)       -- `valid_have(entry)` of an IHAVE's bitmap
  | penalise (p : Peer)
  -- §4.2
  | seen (mid : Key) (r : Bool)
  | accepted (mid : Key) (r : Bool)
  | markSeen (mid : Key)
  | live (slot : Nat) (r : Bool)
  | validateChunk (f : ChunkF) (r : Verdict)
  | queueKeys (qs : List Peer)                          -- `list(queue)`: its keys, in the Python's order: its
                                                        --   rows, the twin's own
  | meshAnd (p : Peer) (qs : List Peer)                 -- `mesh | {p}`, in the Python's order
  | openGroup (g : Group) (f : ChunkF)
  | store (g : Group) (i : Nat) (f : ChunkF)
  | forward (f : ChunkF) (p : Peer)
  | start (fn : String) (g : Group)
  -- §4.2's deferral path: its questions, and the orders of the twin's levels the Python iterates,
  -- each a list of keys in the Python's order
  | installedBlock (slot : Nat) (root : Root) (r : Option Block)  -- the block as level 1 reads it, or nothing
  | admitted (p : Peer) (f : ChunkF) (r : Bool)
  | reserve (p : Peer) (f : ChunkF) (r : Bool)
  | release (p : Peer) (f : ChunkF)
  | bidGroup (root : Root) (g : Option Group)
  | pendingKeys (rs : List Root)                        -- `list(pending)`
  | tieSlotKeys (ks : List (Root × Peer))               -- `list(tie_slot.items())`
  | tiedKeys (rs : List Root)                           -- `list(tied.items())`
  | heldBackKeys (ks : List Chunk)                      -- `held_back.values()`
  | tiedPeerKeys (r : Root) (ps : List Peer)            -- a root's peers in `tied`
  | tiedGroupKeys (r : Root) (p : Peer) (gs : List Group)   -- a peer's groups under a root
  -- §7.2's writer: its questions and calls, other sections' reads, and owed's order
  | hasRoom (p : Peer) (r : Bool)
  | popOwedAnswer (p : Peer) (f : ChunkF)
  | owedKeys (p : Peer) (gs : List Group)               -- `list(owed[p])`
  | chunksKeys (gs : List Group)                        -- `list(chunks)`: the store's groups
  | chunkIndexKeys (g : Group) (is : List Nat)          -- `set(chunks[g])`: a group's indices
  -- a question kept as the record writes it, its arguments and its answer
  -- as compact JSON. The twin's question must have these arguments, and reads the answer where it asks
  | call (name : String) (args : String) (r : String)
  deriving BEq, Repr

/-- What a call on the tape did to the twin's tables: `cr`, the entries whose first touch in it was
a read, with their values then; `cw`, the ones it wrote, with their values at its end. -/
structure CallLog where
  cr : List (Cell × Option Val)
  cw : List (Cell × Option Val)
  deriving Repr

/-- One item of a record's tape: an entry, and, for a call that touched the twin's tables, what it did to them. -/
abbrev TapeItem := Entry × Option CallLog

structure Record where
  n : Nat
  t : UInt64
  fn : String
  args : Array Json
  reads : List (Cell × Option Val)        -- what the Python read, before the call
  scans : List Level
  writes : List (Cell × Option Val)       -- what it wrote, after the call
  rest : List (Cell × Val)                -- entries the call did not read, before the call: the ones it wrote
                                          --   without reading, and, in a trace of the whole state, every other
  tape : List TapeItem
  ret : Json
  raises : Option String
  raisesKey : Option Nat                  -- a `KeyError`'s missing key: where the Python raised
  reached : List String                   -- the traced functions the call reached, itself among them
  tables : List String                    -- the own tables its reads, scans and writes name

/-! ## Reading a record: strictly, so that an altered field cannot pass by wrapping or collapsing

The parsers of keys and of values are `ReplayBase.lean`'s; of an entry, its value and a level, `ReplayTables.lean`'s. -/

/-- A list of footprint entries, each `[table, path, value]`, no entry twice. -/
def cells (what : String) (j : Json) : Except String (List (Cell × Option Val)) := do
  let l ← (← arr j).mapM fun e => do
    let #[.str table, path, v] ← e.getArr? | throw s!"not an entry of {what}: {e.compress}"
    let c ← cell table path
    return (c, ← val c v)
  nodup what (l.map (·.1))
  return l

def msg (j : Json) : Except String Msg := do
  match ← j.getArr? with
  | #[.str "entry", q] => return .entry (← qentry q)       -- next_to_send's owed answer, a whole entry
  | #[.str "chunk", c] => return .chunk (← chunkF c)       -- push_rebuilt's chunk alone
  | #[e] => match ← e.getArr? with
    | #[.str "iwant", ids] => return .iwant (← (← arr ids).mapM key)
    | #[.str "idontwant", .arr #[h]] => match ← ihaveEntry h with    -- one HAVE: a group's whole bitmap (§4.2)
      | .bitmap g b => return .have g b
      | _ => throw s!"not an IDONTWANT of one bitmap: {j.compress}"
    | #[.str "ihave", .arr #[h]] => match ← ihaveEntry h with        -- announce's offer, one bitmap (§5.2)
      | .bitmap g b => return .ihave g b
      | _ => throw s!"not an IHAVE of one bitmap: {j.compress}"
    | _ => throw s!"not an IWANT, nor an IDONTWANT or an IHAVE of one bitmap: {j.compress}"
  | _ => throw s!"not one control message: {j.compress}"

def verdict (j : Json) : Except String Verdict :=
  match j with
  | .str "ACCEPT" => pure .accept
  | .str "REJECT" => pure .reject
  | .str "DEFER" => pure .defer
  | _ => throw s!"not a result of validate_chunk: {j.compress}"

/-- A chunk's id on the tape: its 112 hex digits. -/
def mid (j : Json) : Except String Key := do
  let .str s := j | throw s!"not a message id: {j.compress}"
  let some k := Key.ofId s | throw s!"not a structured id: {s}"
  return k

/-- A list of peers, none twice (an order the Python iterated). -/
def peerList (what : String) (j : Json) : Except String (List Peer) := do
  let l ← peers j
  nodup what l
  return l

def blobsJson (l : List Blob) : Json := Json.arr (l.map blobJson).toArray

def shardJson (s : Shard) : Json :=
  Json.arr #[s.index, Json.arr (s.proof.map Json.str).toArray, blobJson s.data]

/-- The questions kept as the record writes them (`Entry.call`). -/
def callNames : List String :=
  ["sha256", "serialize", "snappy_block_encode", "pad_each", "rs_parity", "merkle_root", "merkle_proof", "content_id",
   "connected", "group_bits", "wake", "writing", "tiebreak", "peer_id_bytes", "gossip_put",
   "gossip_ids", "topic_peers", "mesh_has", "gossip_eligible", "sample_without_replacement",
   "mesh", "close_promises_of_group", "discard_queued", "discard_paced", "gossip_remove_group",
   "resolve", "chunk_of", "handle_graft_prune", "on_iwant",
   "decode_and_reencode", "payload_of", "deliver", "push_rebuilt", "verify_merkle_proof", "block_root"]

/-- An ask key as a record writes it (`key` reads it). -/
def keyJson : Key → Json
  | .id raw _ _ => Json.str raw
  | .want g i => Json.arr #[Json.str g, i]

/-- A chunk as a record writes it (`chunkF` reads it): `[group, index, slot, root, id]`. -/
def chunkJson (f : ChunkF) : Json :=
  Json.arr #[Json.str f.g, f.i, f.slot, Json.str f.root, (match f.mid with | .id raw _ _ => Json.str raw | .want .. => Json.null)]

/-- A chunk the block built (publish's), as a record writes it at `store` and at its
`content_id`: the chunk with no id yet, and all of its content, `[descriptor or null, [proof's digests], data]`.
Any other chunk is written narrow. -/
def builtJson (f : ChunkF) : Json :=
  match f.mid, f.wide with
  | .want .., some w =>
    Json.arr #[Json.str f.g, f.i, f.slot, Json.str f.root, Json.null,
               Json.arr #[(match w.desc with | some d => descriptorJson d | none => Json.null),
                          Json.arr (w.proof.map Json.str).toArray, blobJson w.data]]
  | _, _ => chunkJson f

/-- A block as a record writes it (`blockOf` reads it). -/
def blockJson (b : Block) : Json :=
  Json.arr #[b.slot, (match b.groupId with | some g => Json.str g | none => Json.null),
             (match b.desc with | some d => descriptorJson d | none => Json.null)]

/-- A shard as a record writes it (`shardJson` writes it): `[index, [proof's digests], data]`. -/
def shardOf (j : Json) : Except String Shard := do
  let #[i, proof, data] ← j.getArr? | throw s!"not a shard: {j.compress}"
  return { index := ← nat i, proof := ← (← arr proof).mapM hex, data := ← blob data }

/-- A read of another section's table, on the tape: `["read", table, path, value]`. -/
def foreignRead (table : String) (path v : Json) : Except String Entry := do
  match table, ← path.getArr? with
  | "known_id", #[g, i] =>
    return .readKnownId (← groupKey g) (← nat i) (← if v == .null then pure none else some <$> key v)
  -- a missing entry (null) is a peer that has said nothing, nothing pushed, a chunk no peer holds
  | "chunks", #[g, i] =>                -- the chunk held under that index
    if v == .null then throw s!"chunks: no chunk there, where the Python raises: {path.compress}"
    let f ← chunkF v
    if f.g != (← groupKey g) || f.i != (← nat i) then throw s!"chunks: not the chunk of its place: {v.compress}"
    return .readChunkAt f.g f.i f
  | _, _ => throw s!"not a table §6.1 reads of another section: {table}{path.compress}"

/-- An own level's keys on the tape, in the order the Python iterated them: `["keys", table, path,
keys]`, none twice. (`list(queue)`'s is read by its own arm.) -/
def ownKeys (t : String) (path : Array Json) (ks : Json) : Except String Entry := do
  match t, path with
  | "pending", #[] =>
    let l ← (← arr ks).mapM rootKey
    nodup "keys of pending" l
    return .pendingKeys l
  | "tie_slot", #[] =>
    let l ← (← arr ks).mapM fun k => do
      let #[r, p] ← k.getArr? | throw s!"not a (root, peer) key of tie_slot: {k.compress}"
      return (← rootKey r, ← nat p)
    nodup "keys of tie_slot" l
    return .tieSlotKeys l
  | "tied", #[] =>
    let l ← (← arr ks).mapM rootKey
    nodup "keys of tied" l
    return .tiedKeys l
  | "held_back", #[] =>                 -- §6.4's
    let l ← (← arr ks).mapM chunk
    nodup "keys of held_back" l
    return .heldBackKeys l
  | "tied", #[r] => return .tiedPeerKeys (← rootKey r) (← peerList "keys of a root of tied" ks)
  | "tied", #[r, p] =>
    let l ← (← arr ks).mapM groupKey
    nodup "keys of a peer of tied" l
    return .tiedGroupKeys (← rootKey r) (← nat p) l
  | "chunks", #[] =>                    -- another section's, read by its keys (on_mesh_join)
    let l ← (← arr ks).mapM groupKey
    nodup "keys of chunks" l
    return .chunksKeys l
  | "chunks", #[g] =>
    let l ← (← arr ks).mapM nat
    nodup "keys of a group of chunks" l
    return .chunkIndexKeys (← groupKey g) l
  | "owed", #[p] =>                     -- §7.2's
    let l ← (← arr ks).mapM groupKey
    nodup "keys of a row of owed" l
    return .owedKeys (← nat p) l
  | _, _ => throw s!"not a level whose order the twin asks: {t} {(Json.arr path).compress}"

def entry (j : Json) : Except String Entry := do
  if let .ok #[.str "read", .str table, path, v] := j.getArr? then return ← foreignRead table path v
  if let .ok #[.str "keys", .str "queue", .arr #[], ks] := j.getArr? then return .queueKeys (← peerList "keys of queue" ks)
  if let .ok #[.str "keys", .str t, .arr path, ks] := j.getArr? then return ← ownKeys t path ks
  if let .ok #[.str "mesh_and", .arr #[p], qs] := j.getArr? then
    let p ← nat p
    let qs ← peerList "mesh_and" qs
    if !qs.contains p then throw s!"mesh_and's answer does not have its peer: {j.compress}"
    return .meshAnd p qs
  let #[.str name, args, r] ← j.getArr? | throw s!"not a tape entry: {j.compress}"
  let as ← args.getArr?
  if callNames.contains name then return .call name args.compress r.compress
  match name, as with
  | "expired", #[.str g] => return .expired (← group g) (← r.getBool?)
  | "connected_topic_peers", #[] => return .connectedTopicPeers (← (← arr r).mapM nat)
  | "own_order", #[xs, a] =>          -- the node's own order of xs: any permutation of xs, and nothing else
    let xs ← peers xs
    let r ← peers r
    if !(xs.length == r.length && xs.all fun q => xs.count q == r.count q) then
      throw s!"own_order's answer is not a permutation of its question: {j.compress}"
    return .ownOrder xs (← key a) r
  | "listed", #[p] => return .listed (← nat p) (← nat r)
  | "authenticable", #[.str g] => return .authenticable (← group g) (← r.getBool?)
  | "shuffled", #[xs] =>              -- a draw: any permutation of xs, and nothing else
    -- of numbers (peers, or indices: push_rebuilt's), where there is one and every member is a number
    if let .ok l := (do (← arr xs).mapM nat : Except String (List Nat)) then
      if !l.isEmpty then
        let r ← (← arr r).mapM nat
        if !(l.length == r.length && l.all fun a => l.count a == r.count a) then
          throw s!"shuffled's answer is not a permutation of its question: {j.compress}"
        return .shuffledNats l r
    let xs ← (← arr xs).mapM key
    let r ← (← arr r).mapM key
    if !(xs.length == r.length && xs.all fun a => xs.count a == r.count a) then
      throw s!"shuffled's answer is not a permutation of its question: {j.compress}"
    return .shuffled xs r
  | "enqueue", #[p, x, u] => return .enqueue (← nat p) (← msg x) (← u.getBool?) (← r.getBool?)
  | "valid_have", #[e] => match ← ihaveEntry e with
    | .bitmap g b => return .validHave g b (← r.getBool?)
    | _ => throw s!"valid_have is asked of an IHAVE's bitmap: {j.compress}"
  | "penalise", #[p] =>
    if r != .null then throw s!"penalise returns nothing: {j.compress}"
    return .penalise (← nat p)
  | "seen", #[m] => return .seen (← mid m) (← r.getBool?)
  | "accepted", #[m] => return .accepted (← mid m) (← r.getBool?)
  | "live", #[s] => return .live (← nat s) (← r.getBool?)
  | "validate_chunk", #[f] => return .validateChunk (← chunkF f) (← verdict r)
  | "installed_block", #[sl, root] =>
    return .installedBlock (← nat sl) (← rootKey root) (← if r == .null then pure none else some <$> blockOf r)
  | "admitted", #[p, f] => return .admitted (← nat p) (← chunkF f) (← r.getBool?)
  | "reserve", #[p, f] => return .reserve (← nat p) (← chunkF f) (← r.getBool?)
  | "bid_group", #[root] => return .bidGroup (← rootKey root) (← if r == .null then pure none else some <$> groupKey r)
  | "has_room", #[p] => return .hasRoom (← nat p) (← r.getBool?)       -- §7.2's
  | "pop_owed_answer", #[p] => return .popOwedAnswer (← nat p) (← chunkF r)
  | "after", #[d, .str f, xs] =>
    if r != .null then throw s!"after returns nothing: {j.compress}"
    match f, ← xs.getArr? with
    | "retry_offer", #[a] => return .after (← bits64 d) (.retryOffer (← key a))
    | "ask_parked", #[a] => return .after (← bits64 d) (.askParked (← key a))
    | "promise_due", #[a, p, t] => return .after (← bits64 d) (.promiseDue (← key a) (← nat p) (Float.ofBits (← bits64 t)))
    | "window_timeout", #[k, t] => return .after (← bits64 d) (.windowTimeout (← sendKey k) (Float.ofBits (← bits64 t)))
    | _, _ => throw s!"not a timer of §6.1: {j.compress}"
  | name, as =>
    if r != .null then throw s!"{name} returns nothing: {j.compress}"
    match name, as with
    | "mark_seen", #[m] => return .markSeen (← mid m)
    | "open_group", #[g, f] => return .openGroup (← groupKey g) (← chunkF f)
    | "store", #[g, i, f] => return .store (← groupKey g) (← nat i) (← chunkF f)
    | "forward", #[f, p] => return .forward (← chunkF f) (← nat p)
    | "start", #[.str fn, g] => return .start fn (← groupKey g)
    | "release", #[p, f] => return .release (← nat p) (← chunkF f)
    | _, _ => throw s!"not a question of the block: {j.compress}"

/-- A tape's item: an entry, and fourth and last, for a call that touched the twin's tables, `{"cr": [...], "cw": [...]}`.
A call's entry is its name, its arguments and its answer; the log is a fourth member, never the answer. -/
def tapeItem (j : Json) : Except String TapeItem := do
  let a ← j.getArr?
  match (if a.size == 4 then a.back? else none) with
  | some o@(.obj _) =>
    let some cr := field o "cr" | throw s!"a call's log without cr: {j.compress}"
    let some cw := field o "cw" | throw s!"a call's log without cw: {j.compress}"
    if let .ok kvs := o.getObj? then
      if kvs.size != 2 then throw s!"a call's log with more than cr and cw: {j.compress}"
    let cr ← cells "cr" cr
    let cw ← cells "cw" cw
    if cr.isEmpty && cw.isEmpty then throw s!"a call's log that is empty: {j.compress}"
    return (← entry (.arr a.pop), some { cr, cw })
  | _ => return (← entry j, none)

def recordFields : List String :=
  ["n", "t", "fn", "args", "reads", "scans", "writes", "rest", "tape", "ret", "raises", "raises_key", "reached",
   "tables"]

/-- The names in a JSON list of strings, which must be sorted, with none twice. -/
def names (what : String) (j : Json) : Except String (List String) := do
  let l ← (← arr j).mapM fun x => match x with
    | .str s => pure s
    | x => throw s!"{what}: not a name: {x.compress}"
  if !(l.zip (l.drop 1)).all (fun (x, y) => x < y) then throw s!"{what}: not sorted, or a name twice: {j.compress}"
  return l

/-- The table named first in each entry of a list of footprint entries or levels. -/
def tablesOf (j : Json) : Except String (List String) := do
  (← arr j).mapM fun e => match e.getArrVal? 0 with
    | .ok (.str t) => pure t
    | _ => throw s!"an entry without its table's name: {e.compress}"

def record (j : Json) : Except String Record := do
  let .ok kvs := j.getObj? | throw s!"not a record: {j.compress}"
  if let some f := kvs.keys.find? (!recordFields.contains ·) then throw s!"not a field of a record: {f}"
  let some n := field j "n" | throw "no n"
  let some t := field j "t" | throw "no t"
  let some (.str fn) := field j "fn" | throw "no fn"
  let some args := field j "args" | throw "no args"
  let some reads := field j "reads" | throw "no reads"
  let some scans := field j "scans" | throw "no scans"
  let some writes := field j "writes" | throw "no writes"
  let some tape := field j "tape" | throw "no tape"
  let raises ← match field j "raises" with
    | some (.str x) => pure (some x)
    | some x => throw s!"not an exception's name: {x.compress}"
    | none => pure none
  let raisesKey ← match field j "raises_key" with
    | some x => some <$> nat x
    | none => pure none
  if (raises == some "KeyError") != raisesKey.isSome then      -- the place a KeyError was raised, always
    throw "raises_key goes with a KeyError, and with nothing else"
  let ret? := field j "ret"              -- a return value (null for None) or an exception: one of them
  if ret?.isSome == raises.isSome then throw "a record has ret or raises, one of them"
  -- the two members a mutant's replay picks its records by: the traced functions the call reached,
  -- itself among them, and the own tables it touched, which must be those its reads, scans and writes name
  let some reachedJ := field j "reached" | throw "no reached"
  let reached ← names "reached" reachedJ
  if !reached.contains fn then throw s!"reached: the call's own function is not in it: {reachedJ.compress}"
  let some tablesJ := field j "tables" | throw "no tables"
  let tables ← names "tables" tablesJ
  let touched := ((← tablesOf reads) ++ (← tablesOf scans) ++ (← tablesOf writes)).eraseDups
  if !(tables.all touched.contains && touched.all tables.contains) then
    throw s!"tables: not the tables the reads, scans and writes name: {tablesJ.compress}"
  let args ← args.getArr?
  let scans ← (← arr scans).mapM level
  nodup "scans" scans
  let reads ← cells "reads" reads
  -- the rest: entries the call did not read, each with its value before the call
  let some restJ := field j "rest" | throw "no rest"
  let rest ← (← cells "rest" restJ).mapM fun (c, v) => match v with
    | some v => pure (c, v)
    | none => throw s!"an entry of the rest without a value: {reprStr c}"
  if let some (c, _) := rest.find? fun (c, _) => reads.any (·.1 == c) then
    throw s!"an entry both read and in the rest: {reprStr c}"
  return { n := ← nat n, t := ← bits64 t, fn, args, reads, scans, writes := ← cells "writes" writes, rest,
           tape := ← (← arr tape).mapM tapeItem, ret := ret?.getD .null, raises, raisesKey, reached, tables }

/-- What a record's line says, at its very end, of the functions reached and the tables touched: the text after
`,"reached":[`, which must be the names, `],"tables":[`, the names, `]}`. None if the line does not end so. A
replay of a subset picks its records by this alone, without parsing the line. -/
def lineTail (line : String) : Option (List String × List String) :=
  let line := if line.endsWith "\n" then (line.dropEnd 1).toString else line
  let unq (s : String) : List String := if s.isEmpty then [] else (s.splitOn ",").map fun x => (x.drop 1).dropEnd 1 |>.toString
  match line.splitOn ",\"reached\":[" with
  | [_, tail] => match tail.splitOn "],\"tables\":[" with
    | [r, t] => if t.endsWith "]}" then some (unq r, unq ((t.dropEnd 2).toString)) else none
    | _ => none
  | _ => none

/-! ## Answering the twin from the tape -/

structure RSt where
  tape : List TapeItem
  marks : Array String := #[]
  entered : Array String := #[]           -- the twin's functions entered, for the record's `reached`
  touches : Array Touch := #[]            -- what the twin read and wrote of its state, in order
  twin : State := {}                      -- the twin's state, kept also where it raises

/-- The replay's state, the twin's with it, lies under the exceptions, so that it survives a raise. -/
abbrev R := ExceptT String (StateM RSt)

/-- The tape's next entry. Where it is a call that touched the twin's tables, the call's log is taken here, at
the call: every entry of its `cr` must be the twin's state now (rule 1), and its `cw` is applied to that state and
noted as the twin's write, so that it counts as written before for rule 4 (rule 2). -/
def pop : R (Option Entry) := do
  let s ← getThe RSt
  match s.tape with
  | [] => return none
  | (e, log) :: rest =>
    modifyThe RSt (fun s => { s with tape := rest })
    if let some l := log then
      for (c, v) in l.cr do
        let w := valueAt (← getThe RSt).twin c
        if w != v then
          throw s!"tape: {reprStr e}: its callee read {reprStr c} as {reprStr v}, the twin's state has {reprStr w}"
      for (c, v) in l.cw do
        let t := (← getThe RSt).twin
        let t' ← match v with
          | some v => match put t c v with
            | .ok t' => pure t'
            | .error x => throw s!"tape: {reprStr e}: its callee's write: {x}"
          | none => pure (drop t c)
        modifyThe RSt fun s => { s with twin := t', touches := s.touches.push (.write c) }
    return some e

def asked {α} (q : String) (e : Option Entry) : R α :=
  throw s!"tape: {q} asked, {match e with | some e => reprStr e | none => "the tape is over"} logged"

/-- The node's order of the twin's rows at one of its levels: a permutation of them, and nothing else. The
keys on the tape are none twice (`ownKeys`), and the rows are a map's keys. -/
def permOf {α} [BEq α] [Repr α] (what : String) (rows ks : List α) : R (List α) :=
  if ks.length == rows.length && rows.all ks.contains then pure ks
  else throw s!"tape: {what}: the node's order {reprStr ks} is not of the twin's rows {reprStr rows}"

/-- The answer of a call that returns nothing. -/
def nothing (j : Json) : Except String Unit :=
  if j == .null then pure () else throw s!"a call that returns nothing, with an answer: {j.compress}"

/-- A question kept as the record writes it (`Entry.call`): the tape's next entry must be this question, with
these arguments as compact JSON. Its answer is read here; `{"raises": X}` for an answer is the node's helper
raising X, which the twin's call then raises too. -/
def askCall {α} (name : String) (args : List Json) (read : Json → Except String α) : R α := do
  let q := (Json.arr args.toArray).compress
  match ← pop with
  | some (.call n a r) =>
    if n != name || a != q then asked s!"{name}{q}" (some (.call n a r))
    match Json.parse r with
    | .error e => throw s!"tape: {name}: its answer cannot be read: {e}"
    | .ok j =>
      if let .ok (.str x) := j.getObjVal? "raises" then throw s!"crash: {x}: (the node's {name})"
      match read j with
      | .ok v => return v
      | .error e => throw s!"tape: {name}: its answer: {e}"
  | e => asked s!"{name}{q}" e

instance : Node61 R where
  expired g := do
    match ← pop with
    | some (.expired g' r) => if g' == g then return r else asked s!"expired({g})" (some (.expired g' r))
    | e => asked s!"expired({g})" e
  connectedTopicPeers := do
    match ← pop with
    | some (.connectedTopicPeers r) => return r
    | e => asked "connected_topic_peers()" e
  ownOrder xs a := do
    match ← pop with
    | some (.ownOrder xs' a' r) =>
      if xs' == xs && a' == a then return r else asked s!"own_order({xs}, {reprStr a})" (some (.ownOrder xs' a' r))
    | e => asked s!"own_order({xs}, {reprStr a})" e
  listed p := do
    match ← pop with
    | some (.listed p' r) => if p' == p then return r else asked s!"listed({p})" (some (.listed p' r))
    | e => asked s!"listed({p})" e
  enqueue p x u := do
    match ← pop with
    | some (.enqueue p' x' u' r) =>
      if p' == p && x' == x && u' == u then return r
      else asked s!"enqueue({p}, {reprStr x}, {u})" (some (.enqueue p' x' u' r))
    | e => asked s!"enqueue({p}, {reprStr x}, {u})" e
  after d t := do
    match ← pop with
    | some (.after d' t') =>
      if d' == d.toBits && t' == t then return () else asked s!"after({d}, {reprStr t})" (some (.after d' t'))
    | e => asked s!"after({d}, {reprStr t})" e
  knownId g i := do
    match ← pop with
    | some (.readKnownId g' i' k) =>
      if g' == g && i' == i then return k else asked s!"known_id[{g}][{i}]" (some (.readKnownId g' i' k))
    | e => asked s!"known_id[{g}][{i}]" e
  authenticable g := do
    match ← pop with
    | some (.authenticable g' r) =>
      if g' == g then return r else asked s!"authenticable({g})" (some (.authenticable g' r))
    | e => asked s!"authenticable({g})" e
  shuffled xs := do
    match ← pop with
    | some (.shuffled xs' r) =>
      if xs' == xs then return r else asked s!"shuffled({reprStr xs})" (some (.shuffled xs' r))
    | e => asked s!"shuffled({reprStr xs})" e
  validHave g b := do
    match ← pop with
    | some (.validHave g' b' r) =>
      if g' == g && b' == b then return r else asked s!"valid_have({g}, {b})" (some (.validHave g' b' r))
    | e => asked s!"valid_have({g}, {b})" e
  penalise p := do
    match ← pop with
    | some (.penalise p') => if p' == p then return () else asked s!"penalise({p})" (some (.penalise p'))
    | e => asked s!"penalise({p})" e
  seen a := do
    match ← pop with
    | some (.seen a' r) => if a' == a then return r else asked s!"seen({reprStr a})" (some (.seen a' r))
    | e => asked s!"seen({reprStr a})" e
  accepted a := do
    match ← pop with
    | some (.accepted a' r) => if a' == a then return r else asked s!"accepted({reprStr a})" (some (.accepted a' r))
    | e => asked s!"accepted({reprStr a})" e
  markSeen a := do
    match ← pop with
    | some (.markSeen a') => if a' == a then return () else asked s!"mark_seen({reprStr a})" (some (.markSeen a'))
    | e => asked s!"mark_seen({reprStr a})" e
  live sl := do
    match ← pop with
    | some (.live sl' r) => if sl' == sl then return r else asked s!"live({sl})" (some (.live sl' r))
    | e => asked s!"live({sl})" e
  validateChunkNode f := do
    match ← pop with
    | some (.validateChunk f' r) =>
      if f' == f.narrow then return r else asked s!"validate_chunk({reprStr f})" (some (.validateChunk f' r))
    | e => asked s!"validate_chunk({reprStr f})" e
  queueOrder rows := do                 -- the node's order of the twin's rows: a permutation of them, and nothing else
    match ← pop with
    | some (.queueKeys qs) =>
      if qs.length == rows.length && rows.all qs.contains then return qs
      else throw s!"tape: list(queue): the node's order {qs} is not of the twin's rows {rows}"
    | e => asked s!"list(queue) of {rows}" e
  meshAnd p := do
    match ← pop with
    | some (.meshAnd p' qs) => if p' == p then return qs else asked s!"mesh | \{{p}}" (some (.meshAnd p' qs))
    | e => asked s!"mesh | \{{p}}" e
  openGroup g f := do
    match ← pop with
    | some (.openGroup g' f') =>
      if g' == g && f' == f.narrow then return () else asked s!"open_group({g}, {reprStr f})" (some (.openGroup g' f'))
    | e => asked s!"open_group({g}, {reprStr f})" e
  store g i f := do
    match ← pop with
    | some (.store g' i' f') =>
      -- (a chunk publish built is on the tape with its content and no id, and is compared whole; any
      -- other is narrow there, with its id)
      if g' == g && i' == i && f' == (if f'.wide.isSome then f else f.narrow) then return ()
      else asked s!"store({g}, {i}, {reprStr f})" (some (.store g' i' f'))
    | e => asked s!"store({g}, {i}, {reprStr f})" e
  forwardNode f p := do
    match ← pop with
    | some (.forward f' p') =>
      if f' == f.narrow && p' == p then return () else asked s!"forward({reprStr f}, {p})" (some (.forward f' p'))
    | e => asked s!"forward({reprStr f}, {p})" e
  start fn g := do
    match ← pop with
    | some (.start fn' g') => if fn' == fn && g' == g then return () else asked s!"start({fn}, {g})" (some (.start fn' g'))
    | e => asked s!"start({fn}, {g})" e
  installedBlock sl r := do
    match ← pop with
    | some (.installedBlock sl' r' v) =>
      if sl' == sl && r' == r then return v else asked s!"installed_block({sl}, {r})" (some (.installedBlock sl' r' v))
    | e => asked s!"installed_block({sl}, {r})" e
  admitted p f := do
    match ← pop with
    | some (.admitted p' f' v) =>
      if p' == p && f' == f.narrow then return v else asked s!"admitted({p}, {reprStr f})" (some (.admitted p' f' v))
    | e => asked s!"admitted({p}, {reprStr f})" e
  reserve p f := do
    match ← pop with
    | some (.reserve p' f' v) =>
      if p' == p && f' == f.narrow then return v else asked s!"reserve({p}, {reprStr f})" (some (.reserve p' f' v))
    | e => asked s!"reserve({p}, {reprStr f})" e
  release p f := do
    match ← pop with
    | some (.release p' f') =>
      if p' == p && f' == f.narrow then return () else asked s!"release({p}, {reprStr f})" (some (.release p' f'))
    | e => asked s!"release({p}, {reprStr f})" e
  bidGroup r := do
    match ← pop with
    | some (.bidGroup r' g) => if r' == r then return g else asked s!"bid_group({r})" (some (.bidGroup r' g))
    | e => asked s!"bid_group({r})" e
  -- the orders of the twin's own levels: the node's order of the twin's rows there, a permutation of them
  pendingOrder rows := do
    match ← pop with
    | some (.pendingKeys ks) => permOf "list(pending)" rows ks
    | e => asked s!"list(pending) of {rows}" e
  tieSlotOrder rows := do
    match ← pop with
    | some (.tieSlotKeys ks) => permOf "list(tie_slot.items())" rows ks
    | e => asked s!"list(tie_slot.items()) of {rows}" e
  tiedRootsOrder rows := do
    match ← pop with
    | some (.tiedKeys ks) => permOf "list(tied.items())" rows ks
    | e => asked s!"list(tied.items()) of {rows}" e
  tiedPeersOrder r rows := do
    match ← pop with
    | some (.tiedPeerKeys r' ks) =>
      if r' == r then permOf s!"tied[{r}]'s peers" rows ks
      else asked s!"tied[{r}]'s peers, of {rows}" (some (.tiedPeerKeys r' ks))
    | e => asked s!"tied[{r}]'s peers, of {rows}" e
  tiedGroupsOrder r p rows := do
    match ← pop with
    | some (.tiedGroupKeys r' p' ks) =>
      if r' == r && p' == p then permOf s!"tied[{r}][{p}]'s groups" rows ks
      else asked s!"tied[{r}][{p}]'s groups, of {rows}" (some (.tiedGroupKeys r' p' ks))
    | e => asked s!"tied[{r}][{p}]'s groups, of {rows}" e
  hasRoom p := do
    match ← pop with
    | some (.hasRoom p' r) => if p' == p then return r else asked s!"has_room({p})" (some (.hasRoom p' r))
    | e => asked s!"has_room({p})" e
  popOwedAnswer p := do
    match ← pop with
    | some (.popOwedAnswer p' f) => if p' == p then return f else asked s!"pop_owed_answer({p})" (some (.popOwedAnswer p' f))
    | e => asked s!"pop_owed_answer({p})" e
  owedOrder p rows := do
    match ← pop with
    | some (.owedKeys p' ks) =>
      if p' == p then permOf s!"owed[{p}]'s groups" rows ks
      else asked s!"owed[{p}]'s groups, of {rows}" (some (.owedKeys p' ks))
    | e => asked s!"owed[{p}]'s groups, of {rows}" e
  sha256 b := askCall "sha256" [Json.str b] hex
  serialize d := askCall "serialize" [descriptorJson d] hex
  snappyBlockEncode b := askCall "snappy_block_encode" [blobJson b] blob
  padEach s n := askCall "pad_each" [blobsJson s, n] fun j => do (← arr j).mapM blob
  rsParity s k := askCall "rs_parity" [blobsJson s, k] fun j => do (← arr j).mapM blob
  merkleRoot l := askCall "merkle_root" [blobsJson l] hex
  merkleProof l i := askCall "merkle_proof" [blobsJson l, i] fun j => do (← arr j).mapM hex
  -- §2: asked at every call of message_id. Its answer is 20 bytes, and the last 20 of the id the record's
  -- chunk carries: the chunk's identity in a record and what the node answers must be one id
  contentId f := askCall "content_id" [builtJson f] fun j => do
    let c ← hex j
    if c.length != 40 then throw s!"not 20 bytes: {c}"
    match f.mid with
    | .id raw _ _ =>
      if (raw.drop 72).toString != c then throw s!"not the last 20 bytes of the id its chunk carries ({raw})"
      return c
    | .want .. =>                       -- a chunk publish built; its id is this answer's (the tracer checks the id returned)
      if f.wide.isSome then return c else throw "its chunk carries no structured id"
  -- §6.4 (group D). group_bits' answer: no group twice, and no group without an index
  connected q := askCall "connected" [q] fun j => j.getBool?
  groupBits ids := askCall "group_bits" [Json.arr (ids.map keyJson).toArray] fun j => do
    let l ← pairs "group and bitmap" groupKey nat j
    nodup "group_bits" (l.map (·.1))
    if l.any (·.2 == 0) then throw "a group with no index"
    return l
  heldBackOrder rows := do
    match ← pop with
    | some (.heldBackKeys ks) => permOf "held_back.values()" rows ks
    | e => asked s!"held_back.values() of {reprStr rows}" e
  gossipIds := askCall "gossip_ids" [] fun j => do (← arr j).mapM mid
  topicPeers := askCall "topic_peers" [] (peerList "topic_peers")
  meshHas q := askCall "mesh_has" [q] fun j => j.getBool?
  gossipEligible q := askCall "gossip_eligible" [q] fun j => j.getBool?
  -- the draw's answer: k of the question's peers, none twice
  sample xs k := askCall "sample_without_replacement" [Json.arr (xs.map fun (q : Peer) => Json.num q).toArray, k] fun j => do
    let l ← peerList "sample_without_replacement" j
    if l.length != k then throw s!"not {k} peers: {j.compress}"
    if !l.all xs.contains then throw s!"a peer that is not of the question's: {j.compress}"
    return l
  -- §4.1 and §4.5 (group B). chunk_of's answer is the chunk of the id asked; a record holds no prune
  resolve a := askCall "resolve" [keyJson a] fun j => if j == .null then pure none else some <$> mid j
  chunkOf a := askCall "chunk_of" [keyJson a] fun j => do
    let f ← chunkF j
    if f.mid != a then throw s!"not the chunk of the id asked: {j.compress}"
    return f
  handleGraftPrune p := askCall "handle_graft_prune" [p] fun j => do
    if !(← arr j).isEmpty then throw s!"prunes, of which a record holds none: {j.compress}"
    return 0
  onIwantNode p ids := askCall "on_iwant" [p, Json.arr (ids.map keyJson).toArray] fun j => do (← arr j).mapM chunkF
  -- §4.6's decode and repair (group B). The rebuilt chunks: `[[index, chunk], ...]`, no index twice, each chunk
  -- of the group; a payload is nothing (the toy's) or a blob
  decodeAndReencode g d := askCall "decode_and_reencode" [Json.str g, descriptorJson d] fun j => do
    if j == .null then return none
    let l ← pairs "index and chunk" nat chunkF j
    nodup "decode_and_reencode" (l.map (·.1))
    if l.any fun (_, f) => f.g != g then throw s!"a rebuilt chunk of another group: {j.compress}"
    return some l
  payloadOf r := askCall "payload_of" [Json.arr (r.map fun (i, f) => Json.arr #[(i : Json), chunkJson f]).toArray]
    fun j => if j == .null then pure none else some <$> blob j
  deliver g b := askCall "deliver" [Json.str g, match b with | none => Json.null | some b => blobJson b] nothing
  blockRoot b := askCall "block_root" [blockJson b] rootKey
  chunkAt g i := do
    match ← pop with
    | some (.readChunkAt g' i' f) =>
      if g' == g && i' == i then return f else asked s!"chunks[{g}][{i}]" (some (.readChunkAt g' i' f))
    | e => asked s!"chunks[{g}][{i}]" e
  shuffledNats xs := do
    match ← pop with
    | some (.shuffledNats xs' r) =>
      if xs' == xs then return r else asked s!"shuffled({xs})" (some (.shuffledNats xs' r))
    | some (.shuffled [] []) => if xs.isEmpty then return [] else asked s!"shuffled({xs})" (some (.shuffled [] []))
    | e => asked s!"shuffled({xs})" e
  wake p := askCall "wake" [p] nothing                       -- owe's, and the window's
  writing p := askCall "writing" [p] fun j => j.getBool?     -- the window's line (§7.1's front)
  -- the push order's keys. The tie-break is asked by the chunk's id, as the record writes it
  tiebreak c p := askCall "tiebreak" [Json.str (match c.mid with | .id raw _ _ => raw | .want .. => ""), p]
    fun j => j.getNat?
  peerIdBytes p := askCall "peer_id_bytes" [p] hex
  -- the stock cache's put, and the store's keys (another section's, read by on_mesh_join)
  gossipPut c := askCall "gossip_put" [chunkJson c] nothing
  chunksGroups := do
    match ← pop with
    | some (.chunksKeys gs) => return gs
    | e => asked "list(chunks)" e
  chunkIndices g := do
    match ← pop with
    | some (.chunkIndexKeys g' l) => if g' == g then return l else asked s!"set(chunks[{g}])" (some (.chunkIndexKeys g' l))
    | e => asked s!"set(chunks[{g}])" e
  pushRebuiltNode g new := askCall "push_rebuilt" [Json.str g, Json.arr (new.map fun (i : Nat) => Json.num i).toArray]
    nothing
  -- §3 (group B): the tree's check
  verifyMerkleProof root data i count proof :=
    askCall "verify_merkle_proof" [Json.str root, blobJson data, i, count, Json.arr (proof.map Json.str).toArray]
      fun j => j.getBool?
  -- §4.3 (group B)
  -- §4.6 (group B)
  meshList := askCall "mesh" [] (peerList "mesh")
  closePromisesOfGroup g := askCall "close_promises_of_group" [Json.str g] nothing
  discardQueued g := askCall "discard_queued" [Json.str g] nothing
  discardPaced g := askCall "discard_paced" [Json.str g] nothing
  gossipRemoveGroup g := askCall "gossip_remove_group" [Json.str g] nothing
  crash msg := throw s!"crash: {msg}"
  branch b := modifyThe RSt fun s => { s with marks := s.marks.push b }
  enter fn := modifyThe RSt fun s => { s with entered := s.entered.push fn }

/-- The twin's tables in the replay: its state, with every access noted. The way to that state is local to this
instance: the replay's monad has no `MonadStateOf State`, so a function of §6.1 that asked for one, to read the
state around the tables, would not run here. -/
instance : Tables R :=
  let _ : MonadStateOf State R := {
    get := do return (← getThe RSt).twin
    set := fun s => modifyThe RSt fun rs => { rs with twin := s }
    modifyGet := fun f => modifyGetThe RSt fun rs => let (a, s) := f rs.twin; (a, { rs with twin := s }) }
  Tables.ofState fun t => modifyThe RSt fun s => { s with touches := s.touches.push t }

/-! ## The twin's state, entry by entry

How one entry is looked up, set and dropped, and how a state's entries are listed, is `ReplayTables.lean`'s,
generated from the tables' schema; how a record's entry and its value are read is there too. -/

/-- The state a record describes: what the Python read, and the record's rest (the entries the call wrote without
reading; in a trace of the whole state, every other entry too). -/
def load (r : Record) : Except String State := do
  let s ← r.reads.foldlM (fun s (c, v) => match v with
    | some v => put s c v
    | none => pure s) {}
  r.rest.foldlM (fun s (c, v) => put s c v) s

/-- Rule 3 again, on the whole state and without the twin's notes: the twin's state must be the state the
record's reads describe with the record's writes applied, entry for entry. An operation of the tables that
changed an entry and noted nothing, or noted another, shows here. -/
def wholeState (r : Record) (rs : RSt) : Except String Unit := do
  let mut want ← load r
  for (c, v) in r.writes do
    want ← match v with
      | some v => put want c v              -- a row's write keeps what lies under it (a row's presence)
      | none => pure (drop want c)
  let (a, b) := (entries rs.twin, entries want)
  if let some (c, v) := a.find? (!b.contains ·) then
    throw s!"post: the whole state: the twin has {reprStr c} = {reprStr v}; the record's reads and writes give {reprStr (valueAt want c)}"
  if let some (c, v) := b.find? (!a.contains ·) then
    throw s!"post: the whole state: the record's reads and writes give {reprStr c} = {reprStr v}; the twin has {reprStr (valueAt rs.twin c)}"

/-- Rules 3 and 4 by the twin's notes, after the whole state has been compared (`wholeState`): which entries
it read, and which it wrote. Gives the number of entries the Python read and the twin did not: allowed, and
reported.

An entry the twin may read: one the Python read, or one the twin wrote before. A level the twin reads as a
whole must be one the Python read as a whole, and every entry the twin's scan held must be one the Python read or
the twin wrote before: so a scan cannot bring in the rest of the state.

(Not allowed, though it would be right: a read of a missing entry under a level the Python read as a whole. No
function of §6.1 makes one.) -/
def footprint (r : Record) (rs : RSt) : Except String Nat := do
  let pyRead := r.reads.map (·.1)
  let mut written : List Cell := []
  let mut read : List Cell := []
  let mut scanned : List Level := []
  for t in rs.touches do                  -- rule 4, in the order of the twin's accesses
    match t with
    | .read c =>
      if !(pyRead.contains c || written.contains c) then
        throw s!"footprint, reads: the twin reads an entry the Python did not read: {reprStr c}"
      read := c :: read
    | .scan l found =>
      if !r.scans.any (covers · l) then
        throw s!"footprint, reads: the twin scans a level the Python did not: {reprStr l}"
      if let some c := found.find? fun c => !(pyRead.contains c || written.contains c) then
        throw s!"footprint, reads: the twin's scan holds an entry the Python did not read: {reprStr l}: {reprStr c}"
      scanned := l :: scanned
    | .write c => if !written.contains c then written := c :: written
  for (c, v) in r.writes do               -- rule 3: the Python's writes, made, and to the same values
    if !written.contains c then
      throw s!"footprint, writes: the twin does not write an entry the Python writes: {reprStr c}"
    if valueAt rs.twin c != v then
      throw s!"post: an entry's value: {reprStr c}: twin {reprStr (valueAt rs.twin c)}, toy {reprStr v}"
  let pyWritten := r.writes.map (·.1)
  for c in written do                     -- and no other write, but one that leaves what the record holds
    if !pyWritten.contains c then
      match r.reads.find? (·.1 == c) with
      | some (_, v) =>
        if valueAt rs.twin c != v then
          throw s!"post: the twin changes an entry the Python did not write: {reprStr c}"
      | none => throw s!"footprint, writes: the twin writes an entry the Python neither read nor wrote: {reprStr c}"
  return (pyRead.filter fun c => !(read.contains c || scanned.any (under c))).length

/-! ## One record -/

/-- The functions the twin entered, of those the header lists as traced, must be the record's `reached`: a call
that reaches one the twin does not enter, or the other way round, shows here. -/
def reachedOk (traced : List String) (r : Record) (rs : RSt) : Except String Unit := do
  let got := (rs.entered.toList.eraseDups.filter traced.contains).toArray.qsort (· < ·) |>.toList
  if got != r.reached then
    throw s!"reached: the twin entered {got}, the record has {r.reached}"

/-- What one replayed record gives: the branches it took and how many of the Python's reads the twin did not
make, or the first difference. -/
def run (c : Consts) (replaced traced : List String) (r : Record) : Except String (Array String × Nat) := do
  let ctx : Ctx := { c, now := Float.ofBits r.t, replaced }
  -- a node that runs something else under a traced name has no record of that function
  if replaced.contains r.fn then throw s!"a record of {r.fn} at a node that has replaced it"
  let rs0 : RSt := { tape := r.tape, twin := ← load r }
  -- the twin's run: its state with whether its return value is the toy's, or its error; and the replay's state
  -- (the tape left, the branches taken, the twin's state where it raised)
  -- The return value is compared only where the Python returned: where it raised, the record has none, and a
  -- twin that returns there is reported as that ("the Python raises ...; the twin returns").
  let exec {α} (x : M R α) (ok : α → Except String Bool) : Except String (Except String (State × Bool) × RSt) := do
    let (res, rs) := Id.run (((x.run ctx).run).run rs0)
    match res with
    | .ok v => return (.ok (rs.twin, ← if r.raises.isSome then pure true else ok v), rs)
    | .error e => return (.error e, rs)
  let retNat (j : Json) : Except String Nat := j.getNat?
  let (res, rs) ← match r.fn, r.args with
    | "may_ask", #[a, p] => do exec (mayAsk (← key a) (← nat p)) fun v => return v == (← r.ret.getBool?)
    | "retry_offer", #[a] => do exec (retryOffer (← key a)) fun _ => return r.ret == .null
    | "outstanding", #[q, a] => do exec (outstanding (← nat q) (← key a)) fun v => return v == (← r.ret.getBool?)
    | "add_offer", #[a, p] => do exec (addOffer (← key a) (← nat p)) fun _ => return r.ret == .null
    | "announcers", #[a] => do exec (announcers (← key a)) fun v => return v == (← (← arr r.ret).mapM retNat)
    | "ledger", #[.str g'] => do exec (ledger (← group g')) fun v => return v == (← (← arr r.ret).mapM key)
    | "untried", #[cs, a] => do
      exec (untried (← (← arr cs).mapM nat) (← key a)) fun v => do
        return v == (← if r.ret == .null then pure none else some <$> retNat r.ret)
    | "least_recently_tried", #[cs, a] => do
      exec (leastRecentlyTried (← (← arr cs).mapM nat) (← key a)) fun v => return v == (← retNat r.ret)
    | "promise_due", #[a, p, t] => do
      exec (promiseDue (← key a) (← nat p) (Float.ofBits (← bits64 t))) fun _ => return r.ret == .null
    | "parked", #[p, a] => do exec (parked (← nat p) (← key a)) fun v => return v == (← r.ret.getBool?)
    | "last_resort", #[a] => do exec (lastResort (← key a)) fun _ => return r.ret == .null
    | "ask_parked", #[a] => do exec (askParked (← key a)) fun _ => return r.ret == .null
    | "on_ihave", #[p, ids] => do
      exec (onIhave (← nat p) (← (← arr ids).mapM ihaveEntry)) fun v => return v == (← (← arr r.ret).mapM key)
    | "over_ihave_limits", #[p] => do exec (overIhaveLimits (← nat p)) fun v => return v == (← r.ret.getBool?)
    | "expand", #[e] => do exec (expand (← ihaveEntry e)) fun v => return v == (← (← arr r.ret).mapM key)
    | "valid_id", #[e] => do exec (validId (← ihaveEntry e)) fun v => return v == (← r.ret.getBool?)
    | "gated", #[a] => do exec (gated (← key a)) fun v => return v == (← r.ret.getBool?)
    | "held", #[a] => do exec (held (← key a)) fun v => return v == (← r.ret.getBool?)
    | "tied_to_root", #[p, a] => do exec (tiedToRoot (← nat p) (← key a)) fun v => return v == (← r.ret.getBool?)
    | "on_chunk", #[p, f] => do exec (onChunk (← nat p) (← chunkF f)) fun _ => return r.ret == .null
    | "on_validated", #[p, f, v] => do
      exec (onValidated deferDepth (← nat p) (← chunkF f) (← verdict v)) fun _ => return r.ret == .null
    | "send_have", #[p, .str g'] => do exec (sendHave (← nat p) (← group g')) fun _ => return r.ret == .null
    | "have_bits", #[.str g'] => do exec (haveBits (← group g')) fun v => return v == (← r.ret.getNat?)
    | "close_promises", #[.str g', i, o] => do
      exec (closePromises (← group g') (← nat i) (← if o == .null then pure none else some <$> nat o))
        fun _ => return r.ret == .null
    | "drop_beyond", #[.str g'] => do exec (dropBeyond (← group g')) fun _ => return r.ret == .null
    -- §4.2's deferral path. `defer` and `tie` are reached from on_chunk and on_validated; a directed record
    -- may call any of the six alone
    | "defer", #[p, f] => do exec (defer deferDepth (← nat p) (← chunkF f)) fun _ => return r.ret == .null
    | "tie", #[p, f] => do exec (tie (← nat p) (← chunkF f)) fun _ => return r.ret == .null
    | "tie_room", #[p, f] => do exec (tieRoom (← nat p) (← chunkF f)) fun v => return v == (← r.ret.getBool?)
    | "on_block_installed", #[root] => do exec (onBlockInstalled (← rootKey root)) fun _ => return r.ret == .null
    | "drop_tie", #[p, .str g', b] => do
      exec (dropTie (← nat p) (← group g') (← nat b)) fun _ => return r.ret == .null
    | "drop_stale_waits", #[] => do exec dropStaleWaits fun _ => return r.ret == .null
    | "drop_offer", #[.str g', i, p] => do      -- §6.1's
      exec (dropOffer (← group g') (← nat i) (← nat p)) fun _ => return r.ret == .null
    -- §7.2's writer. next_to_send's return value is an entry, "WAIT" or null; filter_entry's and
    -- with_owed's an entry or null. rarest is called by next_to_send alone, with no record of its own
    | "next_to_send", #[p] => do
      exec (nextToSend (← nat p)) fun v => do
        let want : Next ← match r.ret with
          | .str "WAIT" => pure .wait
          | .null => pure .nothing
          | j => .entry <$> qentry j
        return v == want
    | "filter_entry", #[p, e] => do
      exec (filterEntry (← nat p) (← qentry e)) fun v => do
        return v == (← if r.ret == .null then pure none else some <$> qentry r.ret)
    | "with_owed", #[p, e] => do
      exec (withOwed (← nat p) (← qentry e)) fun v => do
        return v == (← if r.ret == .null then pure none else some <$> qentry r.ret)
    | "projected", #[p, .str g'] => do exec (projected (← nat p) (← group g')) fun v => return v == (← r.ret.getBool?)
    | "rarest", #[p] => do exec (rarestOf (← nat p)) fun v => return v == (← retNat r.ret)   -- v2's choose calls it
    -- §1's seven. K and N take what the caller read of `desc`: a descriptor, or null
    | "message_id", #[f] => do exec (messageId (← chunkF f)) fun v => return v == (← mid r.ret)   -- §2
    -- §6.4's paced gossip
    | "on_pace_tick", #[] => do exec onPaceTick fun _ => return r.ret == .null
    | "on_heartbeat", #[] => do exec onHeartbeat fun _ => return r.ret == .null
    -- §4.6's
    -- §4.1's and §4.5's. A frame: `[chunks, ihave, iwant, idontwant]`
    | "on_iwant", #[p, ids] => do
      exec (onIwant (← nat p) (← (← arr ids).mapM key)) fun v => return v == (← (← arr r.ret).mapM chunkF)
    | "respond", #[p, asks, answers, prunes] => do
      exec (respond (← nat p) (← (← arr asks).mapM key) (← (← arr answers).mapM chunkF) (← nat prunes)) fun _ =>
        return r.ret == .null
    | "on_frame", #[p, .arr #[cs, ih, iw, idw]] => do
      -- (since v0.10.4 an IDONTWANT's entry is a HAVE bitmap or an opaque id: an IHAVE's entry, in either list)
      let fr : Frame := { chunks := ← (← arr cs).mapM chunkF, ihave := ← (← arr ih).mapM ihaveEntry,
                          iwant := ← (← arr iw).mapM key, idontwant := ← (← arr idw).mapM ihaveEntry }
      exec (onFrame (← nat p) fr) fun _ => return r.ret == .null
    -- §3's level 1
    | "validate_chunk", #[f] => do exec (validateChunk (← chunkF f)) fun v => return v == (← verdict r.ret)
    | "committed_descriptor", #[b, f] => do
      exec (committedDescriptor (← blockOf b) (← chunkF f)) fun v =>
        return v == (← if r.ret == .null then pure none else some <$> descriptor r.ret)
    | "on_have", #[p, .str g', b] => do exec (onHave (← nat p) (← group g') (← nat b)) fun _ => return r.ret == .null
    | "claim_group", #[.str g'] => do exec (claimGroup (← group g')) fun _ => return r.ret == .null
    | "drop_group", #[.str g'] => do exec (dropGroup (← group g')) fun _ => return r.ret == .null
    | "decode_group", #[.str g'] => do exec (decodeGroup (← group g')) fun _ => return r.ret == .null
    | "push_rebuilt", #[.str g', new] => do
      exec (pushRebuilt (← group g') (← (← arr new).mapM nat)) fun _ => return r.ret == .null
    | "send_gossip", #[q, ids] => do
      exec (sendGossip (← nat q) (← (← arr ids).mapM mid)) fun _ => return r.ret == .null
    -- §5.2's four. A record of its own where the simulation or an untraced function
    -- calls one
    | "owe", #[p, .str g', b] => do exec (owe (← nat p) (← group g') (← nat b)) fun _ => return r.ret == .null
    | "note_push", #[p, .str g', i] => do
      exec (notePush (← nat p) (← group g') (← nat i)) fun _ => return r.ret == .null
    | "unpush", #[p, .str g', i] => do exec (unpush (← nat p) (← group g') (← nat i)) fun _ => return r.ret == .null
    | "announce", #[p, .str g', b] => do
      exec (announce (← nat p) (← group g') (← nat b)) fun _ => return r.ret == .null
    -- §5.3's two
    -- §7.1's eight
    | "front", #[] => do exec front fun v => return r.ret == (match v with | some q => Json.num q | none => Json.null)
    | "wake_front", #[past] => do       -- `past`: none, or the writer in line that writes control
      let past ← if past == .null then pure none else some <$> nat past
      exec (wakeFront past) fun _ => return r.ret == .null
    | "free_slot", #[] => do exec freeSlot fun _ => return r.ret == .null
    | "acquire_slot", #[p] => do exec (acquireSlot (← nat p)) fun v => return v == (← r.ret.getBool?)
    | "release_unused_slot", #[p] => do exec (releaseUnusedSlot (← nat p)) fun _ => return r.ret == .null
    | "track_in_flight", #[p, c] => do exec (trackInFlight (← nat p) (← chunkF c)) fun _ => return r.ret == .null
    | "window_release", #[p, .str g', i] => do
      exec (windowRelease (← nat p) (← group g') (← nat i)) fun _ => return r.ret == .null
    | "window_timeout", #[k, t] => do
      exec (windowTimeout (← sendKey k) (Float.ofBits (← bits64 t))) fun _ => return r.ret == .null
    -- forward, candidates_for_source, on_mesh_join
    | "forward", #[c, p] => do exec (forward (← chunkF c) (← nat p)) fun _ => return r.ret == .null
    | "candidates_for_source", #[c] => do
      exec (candidatesForSource (← chunkF c)) fun v => return v == (← (← arr r.ret).mapM retNat)
    | "on_mesh_join", #[p] => do exec (onMeshJoin (← nat p)) fun _ => return r.ret == .null
    -- §5.1's origin_written (v0.10.4's)
    | "origin_written", #[c] => do exec (originWritten (← chunkF c)) fun _ => return r.ret == .null
    -- §5.1's origin_acked
    | "origin_acked", #[.str g', i] => do exec (originAcked (← group g') (← nat i)) fun _ => return r.ret == .null
    -- §5.1's publish
    | "publish", #[b, d, sh] => do
      exec (publish (← blockOf b) (← descriptor d) (← (← arr sh).mapM shardOf)) fun _ => return r.ret == .null
    | "guard_fails", #[p, .str g'] => do exec (guardFails (← nat p) (← group g')) fun v => return v == (← r.ret.getBool?)
    | "choose_push", #[c, cands, budget, src] => do
      exec (choosePush (← chunkF c) (← (← arr cands).mapM nat) (← nat budget) (← src.getBool?)) fun v =>
        return v == (← (← arr r.ret).mapM retNat)
    | "group_id", #[d] => do exec (groupId (← descriptor d)) fun v => return Json.str v == r.ret
    -- (`SpecTwin.groupKey` is §1's function; `groupKey` alone is this namespace's reader of a group's key)
    | "group_key", #[g', sl] => do exec (SpecTwin.groupKey (← hex g') (← nat sl)) fun v => return Json.str v == r.ret
    | "K", #[d] => do
      exec (K (← if d == .null then pure none else some <$> descriptor d)) fun v => return v == (← retNat r.ret)
    | "N", #[d] => do
      exec (N (← if d == .null then pure none else some <$> descriptor d)) fun v => return v == (← retNat r.ret)
    | "segment_length", #[d, i] => do
      exec (segmentLength (← descriptor d) (← nat i)) fun v => return v == (← intOf r.ret)
    | "valid_descriptor", #[d] => do exec (validDescriptor (← descriptor d)) fun v => return v == (← r.ret.getBool?)
    | "build_group", #[b] => do
      exec (buildGroup (← blob b)) fun (d, shards) =>
        return (Json.arr #[descriptorJson d, Json.arr (shards.map shardJson).toArray]).compress == r.ret.compress
    | f, _ => throw s!"not a function of the twin, or not its arguments: {f}"
  match r.raises, res with
  | some x, .error e =>
    -- the Python raised: the twin must raise the same, at the same place (a KeyError's key), with the tape used
    -- up, and its state as the Python left it
    let want : String := match r.raisesKey with
      | some q => s!"crash: {x}: {q} ("
      | none => s!"crash: {x}:"
    if !e.startsWith want then throw s!"the Python raises {x}{(r.raisesKey.map (s!" on {·}")).getD ""}; the twin: {e}"
    if !rs.tape.isEmpty then throw s!"the Python raises {x}; the twin raises it with tape left: {reprStr rs.tape}"
    reachedOk traced r rs
    (wholeState r rs).mapError (s!"at the raise ({x}): " ++ ·)
    let fewer ← (footprint r rs).mapError (s!"at the raise ({x}): " ++ ·)
    return (rs.marks.push s!"raises: {x}", fewer)
  | some x, .ok _ => throw s!"the Python raises {x}; the twin returns"
  | none, .error e => throw e
  | none, .ok (_, retOk) =>
    if !rs.tape.isEmpty then throw s!"tape: the toy asked more: {reprStr rs.tape}"
    if !retOk then throw s!"return value: toy {r.ret.compress}"
    reachedOk traced r rs
    wholeState r rs                         -- the state first: what follows is then about the notes alone
    return (rs.marks, ← footprint r rs)

end SpecTwin.Replay
