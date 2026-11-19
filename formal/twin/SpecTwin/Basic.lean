import Std.Data.HashMap
import Std.Data.HashSet

/-! # The types of the twin of protocol.md §6.1, §4.4 and §4.2 (v0.10.4, spec 34f60f8)

Ask keys (§2), bitmaps, and `Node61`: everything the block asks of the rest of the node. That is the reads of
other sections' state, the node's own order of announcers, and the effects (`enqueue`, `after`); §6.1 draws
nothing. The replay answers it from a trace; a proof answers it with anything the interface allows.

The state the block keeps (§8.1), with the names of its entries (`Cell`, `Level`, `Touch`), is in `State.lean`,
and the block reaches it through `Tables` (`Tables.lean`): both files are generated from one schema
(`tools/gen/`). -/

namespace SpecTwin

/-- A peer: the toy's node id. -/
abbrev Peer := Nat

/-- A group's key (§1): 32 bytes, as 64 lowercase hex digits. -/
abbrev Group := String

/-- A block root: 64 lowercase hex digits. -/
abbrev Root := String

/-- A group's state (§4.6). -/
inductive GroupState where
  | collecting
  | decoding
  | complete
  | invalid
  deriving BEq, Repr

/-- A chunk: its group and its index. -/
abbrev Chunk := Group × Nat

/-- A set of chunk indices: bit `i` is index `i`. -/
abbrev Bits := Nat

def Bits.has (b : Bits) (i : Nat) : Bool := b.testBit i

def Bits.set (b : Bits) (i : Nat) : Bits := b ||| (1 <<< i)

def Bits.clear (b : Bits) (i : Nat) : Bits := if b.testBit i then b - (1 <<< i) else b

/-- `a & ~b`: the indices of a that b has not -/
def Bits.minus (a b : Bits) : Bits := a ^^^ (a &&& b)

/-- The indices, upward, as a bitmap iterates (`for i in bits`). -/
def Bits.toList (b : Bits) : List Nat := (List.range (b.log2 + 1)).filter b.testBit

/-- `popcount(b)`: how many indices -/
def Bits.popcount (b : Bits) : Nat := (Bits.toList b).length

/-- An ask key (§2, §6.1): a chunk's structured id, or an ask by index (`WantIndex`). The id is
`group (32 bytes) + uint32_le(index) + content_id (20 bytes)`; its group and index are read once, by
`Key.ofId`, from that layout. -/
inductive Key where
  | id (raw : String) (g : Group) (i : Nat)
  | want (g : Group) (i : Nat)
  deriving BEq, Hashable, Repr, Inhabited

def Key.group : Key → Group
  | .id _ g _ => g
  | .want g _ => g

def Key.index : Key → Nat
  | .id _ _ i => i
  | .want _ i => i

/-- `(group(a), index(a))` -/
def Key.chunk (a : Key) : Chunk := (a.group, a.index)

/-- A structured id's bytes, as the hex digits it was read from (the key of `unwanted[p]`'s members). An ask by
index is no id: it has none, and the text here is no hex string, so it is a member of no set of ids. -/
def Key.idHex : Key → String
  | .id raw _ _ => raw
  | .want _ _ => "(an ask by index: no id)"

private def hexDigit (c : Char) : Option Nat :=
  if '0' ≤ c ∧ c ≤ '9' then some (c.toNat - '0'.toNat)
  else if 'a' ≤ c ∧ c ≤ 'f' then some (c.toNat - 'a'.toNat + 10)
  else none

private def hexBytes : List Char → Option (List Nat)
  | [] => some []
  | h :: l :: rest => do
    let b := (← hexDigit h) * 16 + (← hexDigit l)
    return b :: (← hexBytes rest)
  | [_] => none

/-- A structured id, from its 112 hex digits (§2's layout). -/
def Key.ofId (raw : String) : Option Key := do
  let bytes ← hexBytes raw.toList
  if bytes.length != 56 then none
  let g := String.ofList (raw.toList.take 64)
  let i := (bytes.drop 32).take 4 |>.foldr (fun b acc => b + 256 * acc) 0
  return .id raw g i

/-- An entry of an IHAVE (§2, §4.4): an id of the 56 bytes of a chunk's structured id, read as one (its index
may still be one no group has: `valid_id` decides); an id of any other length, as its hex digits; or a bitmap of
a group's indices. -/
inductive IhaveEntry where
  | id (a : Key)
  | other (raw : String)
  | bitmap (g : Group) (bits : Bits)
  deriving BEq, Repr

/-- A byte string, as its lowercase hex digits (as `Group` and `Root` are). -/
abbrev Hex := String

/-- A byte string the twin does not look into (a payload's body, a chunk's data): its length, and its name, the
toy's tag written as compact JSON (`toy/wire.py`'s `Blob`). -/
structure Blob where
  n : Nat
  tag : String
  deriving BEq, Repr, Inhabited

/-- `b[lo:hi]`, as the toy's `Blob.__getitem__`: the bounds clamped to the length, the slice named after its
blob and them. -/
def Blob.slice (b : Blob) (lo hi : Nat) : Blob :=
  let a := min lo b.n
  let z := min hi b.n
  { n := z - a, tag := s!"[{b.tag},{a},{z}]" }

/-- `SegmentDescriptor` (§1): what a bid commits of a group, whole. `N(d)` and `K(d)` are
§1's functions of it (`Sec1.lean`). -/
structure Descriptor where
  version : Nat
  hashId : Nat
  encoding : Nat
  count : Nat
  segmentSize : Nat
  totalLength : Nat
  root : Hex
  deriving BEq, Repr, Inhabited

/-- What level 1 reads of a chunk beyond its name (§3): the descriptor it carries (design
A), its proof's digests, and its data, a blob. A record has it where a chunk arrives or waits: a frame's chunk, the
arguments of on_chunk, on_validated, defer and tie, and `pending`'s values. -/
structure Wide where
  /-- `f.descriptor`: there under design A; a design B chunk has no such field on the wire (§2: "design A only").
  A chunk is wide with or without it, so that a design B chunk can be written in its wire shape. -/
  desc : Option Descriptor
  proof : List Hex
  data : Blob
  deriving BEq, Repr

/-- A chunk as §4.2's code reads it (`f`): its group, index, slot and block root, and its id `message_id(f)`, which
the toy computes once per chunk and the record carries. A chunk in a lane of a queue, in the node's store or on the
tape is narrow (`wide` none): nothing reads more of it there. -/
structure ChunkF where
  g : Group
  i : Nat
  slot : Nat
  root : Root
  mid : Key
  wide : Option Wide := none
  deriving BEq, Repr

/-- The chunk as a tape's call or a lane has it: without what level 1 reads. -/
def ChunkF.narrow (f : ChunkF) : ChunkF := { f with wide := none }

/-- A block, as level 1 reads it (§3): its slot, and what its bid commits: the group's id (design A)
and the descriptor (design B). `installed_block` answers with it, or with nothing. -/
structure Block where
  slot : Nat
  groupId : Option Hex
  desc : Option Descriptor
  deriving BEq, Repr

/-- A lane of a peer's queue (§7): `queue[p].urgent` or `queue[p].normal`. -/
inductive Lane where
  | urgent
  | normal
  deriving BEq, Hashable, Repr

/-- `peer_has[p][g]` (§4.3): the union of p's HAVE bitmaps for g, and the heartbeats the claim
still lives. -/
structure HaveEntry where
  bits : Bits := 0
  ttl : Nat := 0
  deriving BEq, Repr, Inhabited

/-- `pushed[p][g]` (§5.2): the chunks the node chose to push p of g, the time of the first push as
its 64 bits (none before one: the guard's clock, §5.3), and the heartbeats the entry still lives. -/
structure PushEntry where
  bits : Bits := 0
  firstPush : Option UInt64 := none
  ttl : Nat := 0
  deriving BEq, Repr, Inhabited

/-- The pace queue's one entry (§6.4): a list in the node, named as a lane of a queue is. -/
inductive PaceKey where
  | jobs
  deriving BEq, Hashable, Repr

/-- The window's count's one entry (§7.1's `in_flight`): a number in the node, named as the pace
queue's entry is. -/
inductive CountKey where
  | count
  deriving BEq, Hashable, Repr

/-- The window's line's one entry (§7.1's `waiters`): a deque in the node, the peers in order. -/
inductive LineKey where
  | line
  deriving BEq, Hashable, Repr

/-- A send's key in §7.1's `sent`: the peer, the group and the index of the chunk in flight. -/
abbrev SendKey := Peer × Group × Nat

/-- A job of the pace queue (§6.4): the peer to gossip to, the ids to gossip, and when the heartbeat queued it. Its
time is kept as its 64 bits, as a record writes a time, so that two jobs are equal as their records are. -/
structure Job where
  q : Peer
  ids : List Key
  at_ : UInt64
  deriving BEq, Repr

/-- A control message of a queue entry (§7.2), as a record writes it: its kind and its ids. The block reads an
IWANT's ids alone (`outstanding`), as ask keys; an IHAVE's and an IDONTWANT's are IHAVE entries; a PRUNE's are
none in the toy's runs (its stock prunes are none), and a GRAFT or a JOIN is never queued there. -/
inductive Ctl where
  | iwant (ids : List Key)
  | ihave (ids : List IhaveEntry)
  | idontwant (ids : List IhaveEntry)
  | prune
  deriving BEq, Repr

/-- A queue entry (§7.2): at most one chunk, its control (none, or a list of messages), and whether it answers an
ask. The toy's own marks of when and on which lane it was queued are not part of it. -/
structure QEntry where
  chunk : Option ChunkF
  control : Option (List Ctl)
  solicited : Bool
  deriving BEq, Repr, Inhabited

/-- The asks of an entry's IWANTs: `for c in e.iwants() for b in c.ids`. -/
def QEntry.asks (e : QEntry) : List Key :=
  match e.control with
  | none => []
  | some cs => cs.flatMap fun | .iwant ids => ids | _ => []

/-- A control message with no ids (the toy's `_Msg.empty`): a PRUNE's are none in the toy's runs, so it is one. -/
def Ctl.isEmpty : Ctl → Bool
  | .iwant ids => ids.isEmpty
  | .ihave ids => ids.isEmpty
  | .idontwant ids => ids.isEmpty
  | .prune => true

/-- `e.is_empty()` (§7.2): no chunk, and no control or only empty messages -/
def QEntry.isEmpty (e : QEntry) : Bool := e.chunk.isNone && e.control.all (·.all Ctl.isEmpty)

/-- `e.add_ihave(HaveBitmap(group=g, bits=b))` (§7.2's with_owed): one IHAVE more, after the entry's messages -/
def QEntry.addIhave (e : QEntry) (g : Group) (b : Bits) : QEntry :=
  { e with control := some (e.control.getD [] ++ [.ihave [.bitmap g b]]) }

/-- An empty entry, `Entry()` -/
def QEntry.blank : QEntry := { chunk := none, control := none, solicited := false }

/-- What the block enqueues: one IWANT (§2) naming its asks (§6.1); one IDONTWANT of a group's whole bitmap,
`IDONTWANT(HaveBitmap(group=g, bits=b))` (§4.2's `send_have`); or a whole entry (next_to_send's
owed answer, `Entry(chunk=..., solicited=True)`). -/
inductive Msg where
  | iwant (ids : List Key)
  | have (g : Group) (bits : Bits)
  | entry (e : QEntry)
  | chunk (f : ChunkF)                    -- a chunk alone (push_rebuilt's `enqueue(q, chunks[g][i])`)
  | ihave (g : Group) (bits : Bits)       -- an IHAVE of one bitmap (announce's
                                          --   `enqueue(p, IHAVE(HaveBitmap(group=g, bits=b)))`)
  deriving BEq, Repr

/-- `validate_chunk(f)`'s result (§3, level 1). -/
inductive Verdict where
  | accept
  | reject
  | defer
  deriving BEq, Repr, Inhabited

/-- The timers §6.1 arms (`after(delay, fn, a)`). -/
inductive Timer where
  | retryOffer (a : Key)
  | askParked (a : Key)
  | promiseDue (a : Key) (p : Peer) (at_ : Float)       -- filter_entry's promise (§7.2)
  | windowTimeout (k : Peer × Group × Nat) (at_ : Float)   -- track_in_flight's timer (§7.1)
  deriving BEq, Repr

/-- The constants §6.1 reads (§8.3). -/
structure Consts where
  IWANT_WINDOW : Float
  RETRY_SLACK : Float
  PROMISE : Float
  PARK_TTL : Float
  /-- §8.2's two IHAVE limits, the client's; `none` where it sets none (§4.4) -/
  MAX_IHAVE_MESSAGES : Option Nat := none
  MAX_IHAVE_LENGTH : Option Nat := none
  /-- §2's bound on a group's chunks: an index at or beyond it is one no group has (§4.4's `valid_id`) -/
  MAX_PLAIN_CHUNKS : Nat
  /-- §8.2's limit on a peer's pending groups, the client's; `none` where it sets none (§4.2's `tie_room`) -/
  MAX_PENDING_GROUPS : Option Nat := none
  /-- §7.2's cards: cancel [c8], projection [c12], rarest at pop [c9]; and FAN_IN [c12] -/
  CANCEL : Bool := false
  PROJECT : Bool := false
  RAREST : Bool := false
  FAN_IN : Nat := 2
  /-- §1's constants: the target segment size, the codec's limit on data and parity chunks, and
  the largest segment -/
  UNIT : Nat := 16384
  MAX_CHUNKS : Nat := 256
  MAX_SEGMENT_SIZE : Nat := 32768
  /-- §6.4's constants: the heartbeat's period, the share and the least count of the eligible
  peers that gossip goes to, and card 15 (paced gossip) -/
  HEARTBEAT : Float := 0.7
  GOSSIP_FACTOR : Float := 0.25
  D_LAZY : Nat := 6
  PACED : Bool := false
  /-- §4.3's constant: the heartbeats a peer's HAVE for a group lives -/
  HAVE_TTL : Nat := 3
  /-- §4.5's constant (stock): how many answers an id gets per peer -/
  GOSSIP_RETRANSMISSION : Nat := 3
  /-- §3's choice: design A, a chunk carries its descriptor and the bid commits its id -/
  DESCRIPTOR_IN_CHUNK : Bool := true
  /-- §5.2's constant: the heartbeats a peer's `pushed` entry lives after its last push -/
  PUSH_TTL : Nat := 6
  /-- §5.3's constants: the pushes a node makes of a chunk it forwards, by its uplink class
  [c17], and the guard's grace -/
  R_NODE : Nat := 2
  GUARD_GRACE : Float := 0.2
  /-- §5.1's constant [c2]: the copies of each chunk a source pushes at publish -/
  R : Nat := 2
  /-- §5.1's stripe [c13]: the node's configured uplink, and the uplink from which a source
  pushes to every connected peer (infinite where the card is off) -/
  UPLINK : Float := 50e6
  STRIPE_UPLINK : Float := 1e9
  /-- §7.1's window [c14]: the slots, none where the node has no window; and the time after
  which a send's slot is released without a claim -/
  W : Option Nat := none
  WINDOW_TIMEOUT : Float := 0.5
  /-- §5.1's choice (spec v0.10.4): whether the source announces a chunk at publish (`SOURCE_OFFERS = PUBLISH`), or
  at its acknowledgement (`ACK`, the default) -/
  SOURCE_OFFERS_PUBLISH : Bool := false

/-- What a call reads that does not change during it: the constants and `now`. -/
structure Ctx where
  c : Consts
  now : Float
  /-- The traced names the node runs as something else (a fault, a variant). The twin asks the
  node where it would call one of them (`on_iwant`, at a node that withholds). -/
  replaced : List String := []

/-- What a receiver's `on_frame` sees (§4.1): the frame's chunks and its control, grouped by kind. An IDONTWANT's
entries are HAVE bitmaps (a stock id there is not in a record). PRUNEs, GRAFTs and JOINs are the stock's
(`handle_graft_prune`). -/
structure Frame where
  chunks : List ChunkF
  ihave : List IhaveEntry
  iwant : List Key
  /-- an IDONTWANT's entries, in order: HAVE bitmaps, and any other entry, an opaque id (§4.1; since v0.10.4) -/
  idontwant : List IhaveEntry
  deriving BEq, Repr

/-- `Shard` (§1): a chunk's content, before it has a block to name -/
structure Shard where
  index : Nat
  proof : List Hex
  data : Blob
  deriving BEq, Repr, Inhabited

/-- What §6.1's block asks of the rest of the node, in the order its code asks it. (`held(a)` and
`tied_to_root(p, a)` are the twin's own code, over its tables `mine` and `tied`: `Readers.lean`.) -/
class Node61 (m : Type → Type) where
  /-- `expired(g)` -/
  expired : Group → m Bool
  /-- `connected_topic_peers()`, in its order -/
  connectedTopicPeers : m (List Peer)
  /-- `own_order(xs, a)`: the peers `xs` in the node's own order for a's chunk (§6.1). The node answers with a
  permutation of `xs`; which one is the node's secret. A proof about §6.1 takes it as any permutation. -/
  ownOrder : List Peer → Key → m (List Peer)
  /-- `listed(p)`: in how many offer lists p is (§8.2) -/
  listed : Peer → m Nat
  /-- `enqueue(p, x, urgent)`: whether the queue took it (§7) -/
  enqueue : Peer → Msg → Bool → m Bool
  /-- `after(delay, fn, a)` -/
  after : Float → Timer → m Unit
  /-- `known_id[g].get(i)` (§4.2) -/
  knownId : Group → Nat → m (Option Key)
  /-- `authenticable(g)`: an installed block's bid commits the group (§4.4, §8.1) -/
  authenticable : Group → m Bool
  /-- `shuffled(xs)`: the asks `xs` in an order the node draws (§4.4). The node answers with a permutation of
  `xs`; a proof about §4.4 takes it as any permutation. -/
  shuffled : List Key → m (List Key)
  /-- `valid_have(entry)` for an IHAVE's bitmap: within a HAVE's limits (§4.3, §8.2) -/
  validHave : Group → Bits → m Bool
  /-- `penalise(p)` (§8.2) -/
  penalise : Peer → m Unit
  -- §4.2: questions, reads of other sections' tables, and calls whose writes of the twin's tables the
  -- tape carries
  /-- `seen(mid)`: the stock seen cache -/
  seen : Key → m Bool
  /-- `accepted(mid)`: the id was stored (a dropped group keeps its chunks) -/
  accepted : Key → m Bool
  /-- `mark_seen(mid)` -/
  markSeen : Key → m Unit
  /-- `live(slot)`: within the live window (§8.1) -/
  live : Nat → m Bool
  /-- `validate_chunk(f)` (§3, level 1) at a node that runs something else under the name (a directed set's
  scenario, which draws level 1's result; no cell has one) -/
  validateChunkNode : ChunkF → m Verdict
  /-- `list(queue)`'s order: the peers with a queue, which are the rows of the twin's `queue`, in the order the node
  iterates them (§7). The node answers with a permutation of them; a proof takes it as any permutation. -/
  queueOrder : List Peer → m (List Peer)
  /-- `mesh | {p}`: the mesh peers and p, in the order the node iterates them -/
  meshAnd : Peer → m (List Peer)
  /-- `open_group(g, f)`: `desc[g]` from the bid; `state[g] = COLLECTING` -/
  openGroup : Group → ChunkF → m Unit
  /-- `store(g, i, f)`: the chunk, and `known_id[g][i]` -/
  store : Group → Nat → ChunkF → m Unit
  /-- `forward(f, p)` (§5.2) at a node that runs something else under the name -/
  forwardNode : ChunkF → Peer → m Unit
  /-- `gossip_history.put(f)` (stock): the chunk into the message cache -/
  gossipPut : ChunkF → m Unit
  /-- `list(chunks)`: the groups the node's store holds, in the order it iterates them -/
  chunksGroups : m (List Group)
  /-- `set(chunks[g])`: the indices the store holds of g -/
  chunkIndices : Group → m (List Nat)
  /-- `start(fn, g)`: a level of the check, off the chunk path (`start(decode_group, g)`) -/
  start : String → Group → m Unit
  -- §4.2's deferral path: `defer`, `tie` and `pending_ids` are the twin's own; these it asks
  /-- `installed_block(slot, root)`: the block with the root, validated and applied locally, or nothing (§8). Of
  the block the twin reads what level 1 does (`Block`). -/
  installedBlock : Nat → Root → m (Option Block)
  /-- `admitted(p, f)`: the chunk's group within the peer's limits on unknown groups (§8.2) -/
  admitted : Peer → ChunkF → m Bool
  /-- `reserve(p, f)`: a per-peer reservation in the bounded store of deferred copies (§8.2): whether there was
  room -/
  reserve : Peer → ChunkF → m Bool
  /-- `release(p, f)`: the reservation goes back -/
  release : Peer → ChunkF → m Unit
  /-- `bid_group(root)`: the key of the group the bid of the installed block with this root commits; none for a
  block whose payload is not segmented (a block of columns) -/
  bidGroup : Root → m (Option Group)
  -- The orders in which the Python iterates the twin's own levels. The node answers each with a
  -- permutation of the twin's rows there, which the replay checks; a proof takes it as any permutation.
  /-- `list(pending)`: the roots with copies waiting -/
  pendingOrder : List Root → m (List Root)
  /-- `list(tie_slot.items())`: the (root, peer) pairs with a slot -/
  tieSlotOrder : List (Root × Peer) → m (List (Root × Peer))
  /-- `list(tied.items())`: the roots of `tied` -/
  tiedRootsOrder : List Root → m (List Root)
  /-- a root's peers in `tied`: as `tied[root].items()` iterates them, or the row `tied.pop(root)` hands out -/
  tiedPeersOrder : Root → List Peer → m (List Peer)
  /-- a peer's groups under a root in `tied`: as `tied[root][p]` iterates them, or the row a pop hands out -/
  tiedGroupsOrder : Root → Peer → List Group → m (List Group)
  -- §7.2's writer: its questions, the calls it makes of §7.1, §4.1 and §5.2, and other sections' reads
  /-- `has_room(p)`: p's queue takes another entry (§7) -/
  hasRoom : Peer → m Bool
  /-- `pop_owed_answer(p)`: an answer a full queue refused, now taken from `owed_answers` (§4.1) -/
  popOwedAnswer : Peer → m ChunkF
  /-- `list(owed[p])`: the groups owed to p, in the order the node iterates them -/
  owedOrder : Peer → List Group → m (List Group)
  -- §1: the hash, the serialization, the codec and the tree are the toy's stand-ins, so each
  -- is a question, asked with the arguments the document's line gives it
  /-- `sha256(b)` -/
  sha256 : Hex → m Hex
  /-- `serialize(d)` -/
  serialize : Descriptor → m Hex
  /-- `snappy_block_encode(body)` -/
  snappyBlockEncode : Blob → m Blob
  /-- `pad_each(segs, size)` -/
  padEach : List Blob → Nat → m (List Blob)
  /-- `rs_parity(segs, K)` -/
  rsParity : List Blob → Nat → m (List Blob)
  /-- `merkle_root(leaves)` -/
  merkleRoot : List Blob → m Hex
  /-- `merkle_proof(leaves, i)` -/
  merkleProof : List Blob → Nat → m (List Hex)
  /-- `content_id(f)` (§2): the 20-byte id of the Altair rules, over the topic and the decompressed chunk. The node
  answers it, from a cache or by hashing (the toy stores a chunk's id on the chunk); a proof
  takes it as any function of the chunk. -/
  contentId : ChunkF → m Hex
  -- §6.4
  /-- `connected(q)`: whether the peer is still there -/
  connected : Peer → m Bool
  /-- `group_bits(ids)` (stock gossip's ids, by group): each group's indices among the ids, the groups in the order
  of their first id. The node answers it; a proof takes it as any list. -/
  groupBits : List Key → m (List (Group × Bits))
  /-- `held_back.values()`: the chunks with an ask held back, in the order the node iterates them. The
  node answers with a permutation of the twin's rows; a proof takes it as any permutation. -/
  heldBackOrder : List Chunk → m (List Chunk)
  /-- `gossip_history.gossip_ids()` (stock): the ids of the last heartbeats' chunks -/
  gossipIds : m (List Key)
  /-- `topic_peers()`: the peers on the topic, in the node's order -/
  topicPeers : m (List Peer)
  /-- `q in mesh` -/
  meshHas : Peer → m Bool
  /-- `gossip_eligible(q)` (stock: scores) -/
  gossipEligible : Peer → m Bool
  -- §4.6
  /-- `for q in mesh`: the mesh peers, in the order the node iterates them -/
  meshList : m (List Peer)
  /-- `close_promises_of_group(g)` (§8.2's interface): the node's, a call with what it does to the twin's tables -/
  closePromisesOfGroup : Group → m Unit
  /-- `discard_queued(g)`: the node's, a call -/
  discardQueued : Group → m Unit
  /-- `discard_paced(g)`: the node's, a call -/
  discardPaced : Group → m Unit
  /-- `gossip_history.remove_group(g)` (stock) -/
  gossipRemoveGroup : Group → m Unit
  -- §4.3
  -- §4.1 and §4.5
  /-- `resolve(a)` [c7]: our id at that index, received or rebuilt; none for a group dropped or a chunk not held -/
  resolve : Key → m (Option Key)
  /-- `chunk_of(mid)`: the chunk of that id -/
  chunkOf : Key → m ChunkF
  /-- `handle_graft_prune(p, frame)` (stock): how many prunes it returns. None in the toy's runs: a record holds
  no prune's content, and `Ctl.prune` carries none. -/
  handleGraftPrune : Peer → m Nat
  /-- `on_iwant(p, iw)` at a node that runs something else under the name: the node's answers -/
  onIwantNode : Peer → List Key → m (List ChunkF)
  -- §4.6's decode and repair
  /-- `decode_and_reencode(chunks[g], d)` (§1): any K chunks to all N, each under its index, in the node's order;
  none where the rebuilt root differs. The chunks held are the node's store. -/
  decodeAndReencode : Group → Descriptor → m (Option (List (Nat × ChunkF)))
  /-- `payload_of(rebuilt)`: the payload the chunks carry; the node's (level 3 reads it) -/
  payloadOf : List (Nat × ChunkF) → m (Option Blob)
  /-- `deliver(g, payload)`: level 3, the application's -/
  deliver : Group → Option Blob → m Unit
  /-- a read of `chunks[g][i]` (§4.2): the chunk held under that index -/
  chunkAt : Group → Nat → m ChunkF
  /-- `block_root(block)` (§5.1's publish): the root of the block a published chunk names -/
  blockRoot : Block → m Root
  /-- `shuffled(xs)` of peers, or of indices: a draw. The node answers with a permutation; a proof takes it as
  any. -/
  shuffledNats : List Nat → m (List Nat)
  /-- `wake(p)` (§7.2): p's writer is told there is something to send (owe's call, and the
  window's) -/
  wake : Peer → m Unit
  /-- `push_rebuilt(g, new)` at a node that runs something else under the name -/
  pushRebuiltNode : Group → List Nat → m Unit
  /-- `verify_merkle_proof(root, data, index, count, proof)` (§1): the tree is the node's stand-in (the boundary) -/
  verifyMerkleProof : Hex → Blob → Nat → Nat → List Hex → m Bool
  /-- `sample_without_replacement(xs, k)`: a draw. The node answers with k of xs, none twice; a proof takes it as
  any such list. -/
  sample : List Peer → Nat → m (List Peer)
  /-- `tiebreak(f, p)` (§5.3): the push order's first key, a number. The node answers it; a proof takes it as any
  function of the chunk and the peer. -/
  tiebreak : ChunkF → Peer → m Nat
  /-- `peer_id_bytes(p)` (§5.3): the push order's second key, the peer's id, as the hex of its bytes -/
  peerIdBytes : Peer → m String
  /-- where the Python would raise an exception -/
  crash : {α : Type} → [Inhabited α] → String → m α
  /-- a branch taken: counted by the replay, nothing otherwise -/
  branch : String → m Unit
  /-- a function of the twin entered (`reached`): compared by the replay with the record's, nothing otherwise -/
  enter : String → m Unit

namespace Node61

/-- Asking through a monad transformer. -/
abbrev lift {m n : Type → Type} [Node61 m] (f : ∀ {α : Type}, m α → n α) : Node61 n where
  expired g := f (expired g)
  connectedTopicPeers := f connectedTopicPeers
  ownOrder xs a := f (ownOrder xs a)
  listed p := f (listed p)
  enqueue p x u := f (enqueue p x u)
  after d t := f (after d t)
  knownId g i := f (knownId g i)
  authenticable g := f (authenticable g)
  shuffled xs := f (shuffled xs)
  validHave g b := f (validHave g b)
  penalise p := f (penalise p)
  seen a := f (seen a)
  accepted a := f (accepted a)
  markSeen a := f (markSeen a)
  live s := f (live s)
  validateChunkNode c := f (validateChunkNode c)
  queueOrder qs := f (queueOrder qs)
  meshAnd p := f (meshAnd p)
  openGroup g c := f (openGroup g c)
  store g i c := f (store g i c)
  forwardNode c p := f (forwardNode c p)
  gossipPut c := f (gossipPut c)
  chunksGroups := f chunksGroups
  chunkIndices g := f (chunkIndices g)
  start fn g := f (start fn g)
  installedBlock sl r := f (installedBlock sl r)
  admitted p c := f (admitted p c)
  reserve p c := f (reserve p c)
  release p c := f (release p c)
  bidGroup r := f (bidGroup r)
  pendingOrder rs := f (pendingOrder rs)
  tieSlotOrder ks := f (tieSlotOrder ks)
  tiedRootsOrder rs := f (tiedRootsOrder rs)
  tiedPeersOrder r ps := f (tiedPeersOrder r ps)
  tiedGroupsOrder r p gs := f (tiedGroupsOrder r p gs)
  hasRoom p := f (hasRoom p)
  popOwedAnswer p := f (popOwedAnswer p)
  owedOrder p gs := f (owedOrder p gs)
  sha256 b := f (sha256 b)
  serialize d := f (serialize d)
  snappyBlockEncode b := f (snappyBlockEncode b)
  padEach s n := f (padEach s n)
  rsParity s k := f (rsParity s k)
  merkleRoot l := f (merkleRoot l)
  merkleProof l i := f (merkleProof l i)
  contentId c := f (contentId c)
  connected q := f (connected q)
  groupBits ids := f (groupBits ids)
  heldBackOrder ks := f (heldBackOrder ks)
  gossipIds := f gossipIds
  topicPeers := f topicPeers
  meshHas q := f (meshHas q)
  gossipEligible q := f (gossipEligible q)
  sample xs k := f (sample xs k)
  tiebreak c p := f (tiebreak c p)
  peerIdBytes p := f (peerIdBytes p)
  meshList := f meshList
  resolve a := f (resolve a)
  chunkOf a := f (chunkOf a)
  handleGraftPrune p := f (handleGraftPrune p)
  onIwantNode p ids := f (onIwantNode p ids)
  decodeAndReencode g d := f (decodeAndReencode g d)
  payloadOf r := f (payloadOf r)
  deliver g b := f (deliver g b)
  chunkAt g i := f (chunkAt g i)
  blockRoot b := f (blockRoot b)
  shuffledNats xs := f (shuffledNats xs)
  wake p := f (wake p)
  pushRebuiltNode g new := f (pushRebuiltNode g new)
  verifyMerkleProof r d i c p := f (verifyMerkleProof r d i c p)
  closePromisesOfGroup g := f (closePromisesOfGroup g)
  discardQueued g := f (discardQueued g)
  discardPaced g := f (discardPaced g)
  gossipRemoveGroup g := f (gossipRemoveGroup g)
  crash msg := f (crash msg)
  branch b := f (branch b)
  enter fn := f (enter fn)

instance {m : Type → Type} {σ : Type} [Monad m] [Node61 m] : Node61 (StateT σ m) := lift (m := m) (n := StateT σ m) fun x => monadLift x
instance {m : Type → Type} {ρ : Type} [Monad m] [Node61 m] : Node61 (ReaderT ρ m) := lift (m := m) (n := ReaderT ρ m) fun x => monadLift x

end Node61

/-- A call of §6.1: the context it reads, over a monad that has its tables (`Tables m`) and answers what it
asks (`Node61 m`). The state behind the tables lies in the base monad, so that whatever runs the twin keeps it
also where the twin stops at a raise. -/
abbrev M (m : Type → Type) := ReaderT Ctx m

def negInf : Float := -(1.0 / 0.0)

end SpecTwin
