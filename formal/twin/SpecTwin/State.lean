import SpecTwin.Basic

/-! # The twin's state and the names of its entries (generated)

This file is written whole by `tools/gen/gen.py` from `gen/schema.py`, one entry there per
table, and `gen.py --check` compares it byte for byte. Do not edit it: change the schema, or the generator.

The state the twin keeps (§8.1), the names of its entries (`Cell`), of the levels a table can be read whole at
(`Level`), what one access of the state touches (`Touch`), and the tables' names as a trace's header and its
records give them (`ownTables`). -/

namespace SpecTwin

/-- The state §6.1's block keeps (§8.1). A missing entry reads as empty, and reading allocates nothing. -/
structure State where
  askedAt : Std.HashMap Key Float := {}
  tried : Std.HashMap Key (Std.HashMap Peer Float) := {}
  offers : Std.HashMap Key (List Peer) := {}
  offered : Std.HashMap Peer (Std.HashMap Group Bits) := {}
  promises : Std.HashMap (Key × Peer) Float := {}
  park : Std.HashMap Peer (Std.HashMap Group Float) := {}
  askedParked : Std.HashMap Chunk (Std.HashSet Peer) := {}
  lastResortArmed : Std.HashSet Chunk := {}
  ihaveFrames : Std.HashMap Peer Nat := {}
  ihaveAsked : Std.HashMap Peer Nat := {}
  heldBack : Std.HashMap Chunk Key := {}
  received : Std.HashMap Group Bits := {}
  mine : Std.HashMap Group Bits := {}
  state : Std.HashMap Group GroupState := {}
  tied : Std.HashMap Root (Std.HashMap Peer (Std.HashMap Group Bits)) := {}
  queue : Std.HashMap Peer (Std.HashMap Lane (List QEntry)) := {}
  pending : Std.HashMap Root (List (Peer × ChunkF)) := {}
  pendingIds : Std.HashSet Key := {}
  tieSlot : Std.HashMap (Root × Peer) Nat := {}
  owed : Std.HashMap Peer (Std.HashMap Group Bits) := {}
  owedAnswers : Std.HashMap Peer (Std.HashMap Group Bits) := {}
  sentTo : Std.HashMap Peer (Std.HashMap Group Bits) := {}
  slotHeld : Std.HashSet Peer := {}
  paceQueue : Std.HashMap PaceKey (List Job) := {}
  stopPull : Std.HashSet Group := {}
  peerHas : Std.HashMap Peer (Std.HashMap Group HaveEntry) := {}
  holders : Std.HashMap Group (Std.HashMap Nat (Std.HashSet Peer)) := {}
  serveCount : Std.HashMap Peer (Std.HashMap Key Nat) := {}
  origin : Std.HashMap Group Bits := {}
  planned : Std.HashMap Group (Std.HashMap Nat (Std.HashSet Peer)) := {}
  pushed : Std.HashMap Peer (Std.HashMap Group PushEntry) := {}
  desc : Std.HashMap Group Descriptor := {}
  inFlight : Std.HashMap CountKey Int := {}
  waiters : Std.HashMap LineKey (List Peer) := {}
  sent : Std.HashMap SendKey Float := {}
  unwanted : Std.HashMap Peer (Std.HashSet Hex) := {}

/-- An entry of §6.1's tables: the table and its keys, down to the level at which the code reads values (the
schema, `tools/gen/schema.py`). A missing entry is a value too, and reading it is a read. -/
inductive Cell where
  | askedAt (a : Key)
  | tried (a : Key) (p : Peer)
  | offers (a : Key)
  | promise (a : Key) (p : Peer)
  | offered (q : Peer) (g : Group)
  | park (p : Peer) (g : Group)
  | askedParked (k : Chunk)
  | lrArmed (k : Chunk)
  | ihaveFrames (p : Peer)
  | ihaveAsked (p : Peer)
  | heldBack (k : Chunk)
  | received (g : Group)
  | mine (g : Group)
  | state (g : Group)
  | tied (r : Root) (p : Peer) (g : Group)
  | tiedRow (r : Root)
  | tiedPeerRow (r : Root) (p : Peer)
  | queue (p : Peer) (l : Lane)
  | queueRow (p : Peer)
  | pending (r : Root)
  | pendingId (m : Key)
  | tieSlot (r : Root) (p : Peer)
  | owed (p : Peer) (g : Group)
  | owedRow (p : Peer)
  | owedAnswers (p : Peer) (g : Group)
  | sentTo (p : Peer) (g : Group)
  | slotHeld (p : Peer)
  | paceQueue (e : PaceKey)
  | stopPull (g : Group)
  | peerHas (p : Peer) (g : Group)
  | holders (g : Group) (i : Nat)
  | serveCount (p : Peer) (m : Key)
  | origin (g : Group)
  | planned (g : Group) (i : Nat)
  | plannedRow (g : Group)
  | pushed (p : Peer) (g : Group)
  | desc (g : Group)
  | inFlight (e : CountKey)
  | waiters (e : LineKey)
  | sent (k : SendKey)
  | unwanted (p : Peer)
  deriving BEq, Repr

/-- A level of a table read as a whole: every entry under it. -/
inductive Level where
  | askedAt
  | triedAll                              -- every `tried[a][p]`
  | tried (a : Key)                       -- every `tried[a][p]` of one key
  | offers
  | promises
  | offeredAll                            -- every `offered[q][g]`
  | offered (q : Peer)
  | parkAll                               -- every `park[p][g]`
  | park (p : Peer)
  | askedParked
  | lrArmed
  | ihaveFrames
  | ihaveAsked
  | heldBack
  | received
  | mine
  | state
  | tiedAll                               -- every row and bitmap of `tied`
  | tiedRoot (r : Root)
  | tiedPeer (r : Root) (p : Peer)
  | queueAll                              -- every row and lane of `queue`
  | pending
  | pendingIds
  | tieSlot
  | owed (p : Peer)
  | owedAll                               -- every row and bitmap of `owed`
  | owedAnswers (p : Peer)
  | owedAnswersAll                        -- every `owed_answers[p][g]`
  | sentToAll                             -- every `sent_to[p][g]`
  | slotHeld
  | paceQueue
  | stopPull
  | peerHas
  | holders
  | serveCount
  | origin
  | plannedAll                            -- every row and set of `planned`
  | pushed
  | desc
  | inFlight
  | waiters
  | sent
  | unwanted
  deriving BEq, Repr

/-- What one access of the state touches. -/
inductive Touch where
  | read (c : Cell)
  | write (c : Cell)
  | scan (l : Level) (found : List Cell)  -- a level read as a whole, and the entries it held
  deriving BEq, Repr

/-- The twin's own tables, by the names a trace's header and its records give them, in the schema's order. -/
def ownTables : List String :=
  ["asked_at", "tried", "offers", "promises", "offered", "park", "asked_parked", "last_resort_armed", "ihave_frames",
   "ihave_asked", "held_back", "received", "mine", "state", "tied", "queue", "pending", "pending_ids", "tie_slot",
   "owed", "owed_answers", "sent_to", "slot_held", "pace_queue", "stop_pull", "peer_has", "holders", "serve_count",
   "origin", "planned", "pushed", "desc", "in_flight", "waiters", "sent", "unwanted"]

end SpecTwin
