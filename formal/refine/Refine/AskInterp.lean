import SpecTwin.Sec61

/-! # The twin's side: an interpreter that keeps the queue, the timers and the asks' numbers

This file imports the twin only, not Veil (a file that imports Veil must not elaborate the twin's monad).

**The interpreter's contracts:**
- **The world** is the twin's state and, beside it, what the interpreter keeps: the armed timers, the count of
  asks each peer's queue took (a ghost history: nothing reads it), and the raises.
- **`enqueue(p, x, urgent)` writes the twin's own queue.** Where the queue takes the entry, it is appended to
  `queue[p].urgent` or `queue[p].normal`, as `toy/node.py` 797–809 does (spec 34f60f8), and the count of each
  chunk it asks `p` for goes up. An empty entry is never appended (node.py 802–803). Whether the queue takes an
  entry (`admits`) and what `enqueue` answers (`enqueue`) are two answers of the node: under `--churn` the toy
  answers True for a closed link and appends nothing (node.py 798–799). The model's `full` is read from `admits`,
  that is, from whether the lane grew, never from the answer.
- **`after(delay, fn, a)` arms a timer:** appended to the world's timers, with its delay.
- **`crash`** is noted in the world and goes on with a default value. A step's theorem shows the note unchanged.
- **`writing(p)`** (§7.1, §7.3), the question of the window's functions (`front`, `wake_front`, `acquire_slot`),
  is answered from a field of the answers like the others. The asking path (`retry_offer`, `promise_due`) never
  asks it.
- **Every other operation of `Node61` leaves the world alone:** the questions are answered from fixed functions
  (the same at each ask within a handler), and the other effects (`penalise`, `mark_seen`, `open_group`, `store`,
  `forward` and `push_rebuilt` at a node that runs something else under the name, `gossip_history.put`, `start`,
  `release`, `deliver`, `wake`, `close_promises_of_group`, `discard_queued`, `discard_paced`,
  `gossip_history.remove_group`) do nothing here. None of them is called on a path a theorem here covers; a proof
  that meets one must give it a state. For four of them doing nothing is not what the node does to the twin's
  tables (`toy/node.py` 654–656 and 725–757): `open_group` writes `desc[g]` and `state[g]`;
  `close_promises_of_group` removes promises; `discard_queued` strips or removes entries of the twin's `queue`
  and pops the group from `owed` and `owed_answers`; `discard_paced` trims or removes jobs of its `pace_queue`.
  One question does too: `pop_owed_answer` takes its entry out of `owed_answers` (node.py 814–821), and is
  answered here with nothing taken.
- **What is the twin's own:** `stop_pull`, `desc`, `origin`, `peer_has`, `pushed` and `holders` are the twin's
  own tables, read from the world's `st`, not answers; `claim_group`, `forward`, `drop_offer`, `validate_chunk`
  and §7.1's window (`acquire_slot`, `release_unused_slot`, `track_in_flight`) and `unpush` are the twin's own
  code, which writes `st` itself.

**The step** is a timer's firing, not a call: `retryFire i a` takes the armed timer at place `i` away and runs
the twin's `retry_offer(a)`. That the timer at `i` is a retry timer of `a` is a hypothesis of the theorems that
need it. -/

namespace Refine.Ask
open SpecTwin

-- The twin's keys compare lawfully (their `BEq` is the derived one). The map lemmas need it.
deriving instance ReflBEq, LawfulBEq for SpecTwin.Key
deriving instance ReflBEq, LawfulBEq for SpecTwin.Lane

/-- What the rest of the node answers during one handler: the same at each ask (stable answers). -/
structure Answers where
  expired : Group → Bool := fun _ => false
  connectedTopicPeers : List Peer := []
  ownOrder : List Peer → Key → List Peer := fun xs _ => xs
  listed : Peer → Nat := fun _ => 0
  /-- whether p's queue takes the entry: it is appended exactly then (and where the entry is not empty) -/
  admits : Peer → Msg → Bool → Bool := fun _ _ _ => true
  /-- what `enqueue` answers; nothing here ties it to `admits` -/
  enqueue : Peer → Msg → Bool → Bool := fun _ _ _ => true
  knownId : Group → Nat → Option Key := fun _ _ => none
  authenticable : Group → Bool := fun _ => false
  shuffled : List Key → List Key := fun xs => xs
  validHave : Group → Bits → Bool := fun _ _ => true
  seen : Key → Bool := fun _ => false
  accepted : Key → Bool := fun _ => false
  live : Nat → Bool := fun _ => true
  validateChunkNode : ChunkF → Verdict := fun _ => .accept
  queueOrder : List Peer → List Peer := fun qs => qs
  meshAnd : Peer → List Peer := fun p => [p]
  -- §4.2's deferral path: its questions, and the node's orders of the twin's own levels
  installedBlock : Nat → Root → Option Block := fun _ _ => none
  admitted : Peer → ChunkF → Bool := fun _ _ => true
  reserve : Peer → ChunkF → Bool := fun _ _ => true
  bidGroup : Root → Option Group := fun _ => none
  pendingOrder : List Root → List Root := fun rs => rs
  tieSlotOrder : List (Root × Peer) → List (Root × Peer) := fun ks => ks
  tiedRootsOrder : List Root → List Root := fun rs => rs
  tiedPeersOrder : Root → List Peer → List Peer := fun _ ps => ps
  tiedGroupsOrder : Root → Peer → List Group → List Group := fun _ _ gs => gs
  -- §7.2's writer: its questions, the chunk an owed answer is, other sections' reads, owed's order
  hasRoom : Peer → Bool := fun _ => true
  popOwedAnswer : Peer → ChunkF := fun _ => { g := "", i := 0, slot := 0, root := "", mid := .want "" 0 }
  -- §5.3's keys of the push order
  tiebreak : ChunkF → Peer → Nat := fun _ _ => 0
  peerIdBytes : Peer → String := fun _ => ""
  -- the store's keys (on_mesh_join)
  chunksGroups : List Group := []
  chunkIndices : Group → List Nat := fun _ => []
  owedOrder : Peer → List Group → List Group := fun _ gs => gs
  -- §1: the hash, the serialization, the codec and the tree, each a function of its arguments
  sha256 : Hex → Hex := fun b => b
  serialize : Descriptor → Hex := fun _ => ""
  snappyBlockEncode : Blob → Blob := fun b => b
  padEach : List Blob → Nat → List Blob := fun s _ => s
  rsParity : List Blob → Nat → List Blob := fun _ _ => []
  merkleRoot : List Blob → Hex := fun _ => ""
  merkleProof : List Blob → Nat → List Hex := fun _ _ => []
  contentId : ChunkF → Hex := fun _ => ""
  connected : Peer → Bool := fun _ => true
  groupBits : List Key → List (Group × Bits) := fun _ => []
  heldBackOrder : List Chunk → List Chunk := fun ks => ks
  gossipIds : List Key := []
  topicPeers : List Peer := []
  meshHas : Peer → Bool := fun _ => false
  gossipEligible : Peer → Bool := fun _ => true
  sample : List Peer → Nat → List Peer := fun xs k => xs.take k
  meshList : List Peer := []
  resolve : Key → Option Key := fun _ => none
  chunkOf : Key → ChunkF := fun a => { g := a.group, i := a.index, slot := 0, root := "", mid := a }
  handleGraftPrune : Peer → Nat := fun _ => 0
  onIwantNode : Peer → List Key → List ChunkF := fun _ _ => []
  decodeAndReencode : Group → Descriptor → Option (List (Nat × ChunkF)) := fun _ _ => none
  payloadOf : List (Nat × ChunkF) → Option Blob := fun _ => none
  chunkAt : Group → Nat → ChunkF := fun g i => { g, i, slot := 0, root := "", mid := .want g i }
  blockRoot : Block → Root := fun _ => ""
  shuffledNats : List Nat → List Nat := fun xs => xs
  /-- what `writing(p)` answers: only the window's functions ask it (`front`, `wake_front`, `acquire_slot`) -/
  writing : Peer → Bool := fun _ => false
  verifyMerkleProof : Hex → Blob → Nat → Nat → List Hex → Bool := fun _ _ _ _ _ => true

/-- The world a step runs in: the twin's state, and what the interpreter keeps beside it. -/
structure World where
  /-- the twin's own state (§8.1), its queue among it -/
  st : State := {}
  /-- the armed timers, in the order they were armed: the delay each was armed with, and what it runs -/
  timers : List (Float × Timer) := []
  /-- a ghost history: how many asks of the chunk p's queue has taken. Nothing reads it but the abstraction. -/
  made : Chunk → Peer → Nat := fun _ _ => 0
  /-- where the Python would have raised -/
  crashed : List String := []

/-- An entry as `enqueue` makes it of what it is given (node.py 800–801): a control message alone, a chunk alone,
or the entry. A chunk alone is kept narrow, as the twin keeps every chunk in a lane (`ChunkF`'s docstring). No
theorem here covers a path that enqueues either of the last two cases. -/
def entryOf : Msg → QEntry
  | .iwant ids => { chunk := none, control := some [.iwant ids], solicited := false }
  | .have g bits => { chunk := none, control := some [.idontwant [.bitmap g bits]], solicited := false }
  | .entry e => e
  | .chunk f => { chunk := some f.narrow, control := none, solicited := false }
  | .ihave g bits => { chunk := none, control := some [.ihave [.bitmap g bits]], solicited := false }

/-- The queue takes an entry: appended to p's lane, and the count of each chunk it asks p for goes up. -/
def World.push (w : World) (p : Peer) (l : Lane) (e : QEntry) : World :=
  { w with
    st := { w.st with
      queue := w.st.queue.insert p
        ((w.st.queue.getD p {}).insert l (((w.st.queue.getD p {}).getD l []) ++ [e])) }
    made := fun k q => w.made k q + (if q = p then (e.asks.filter (·.chunk == k)).length else 0) }

/-- The interpreter: the answers are read, the world lies below. -/
abbrev I := ReaderT Answers (StateM World)

/-- The twin's state within the world: what its tables read and write. -/
instance : MonadStateOf State (StateM World) where
  get := fun w => (w.st, w)
  set s := fun w => ((), { w with st := s })
  modifyGet f := fun w => ((f w.st).1, { w with st := (f w.st).2 })

instance : Node61 I where
  expired g := return (← read).expired g
  connectedTopicPeers := return (← read).connectedTopicPeers
  ownOrder xs a := return (← read).ownOrder xs a
  listed p := return (← read).listed p
  enqueue p x u := do
    let ans ← read
    if !(entryOf x).isEmpty && ans.admits p x u then
      modifyThe World fun w => w.push p (if u then .urgent else .normal) (entryOf x)
    return ans.enqueue p x u
  after d t := modifyThe World fun w => { w with timers := w.timers ++ [(d, t)] }
  knownId g i := return (← read).knownId g i
  authenticable g := return (← read).authenticable g
  shuffled xs := return (← read).shuffled xs
  validHave g b := return (← read).validHave g b
  penalise _ := pure ()
  seen a := return (← read).seen a
  accepted a := return (← read).accepted a
  markSeen _ := pure ()
  live s := return (← read).live s
  validateChunkNode f := return (← read).validateChunkNode f
  queueOrder qs := return (← read).queueOrder qs
  meshAnd p := return (← read).meshAnd p
  openGroup _ _ := pure ()
  store _ _ _ := pure ()
  forwardNode _ _ := pure ()
  gossipPut _ := pure ()
  chunksGroups := return (← read).chunksGroups
  chunkIndices g := return (← read).chunkIndices g
  start _ _ := pure ()
  installedBlock sl r := return (← read).installedBlock sl r
  admitted p f := return (← read).admitted p f
  reserve p f := return (← read).reserve p f
  release _ _ := pure ()
  bidGroup r := return (← read).bidGroup r
  pendingOrder rs := return (← read).pendingOrder rs
  tieSlotOrder ks := return (← read).tieSlotOrder ks
  tiedRootsOrder rs := return (← read).tiedRootsOrder rs
  tiedPeersOrder r ps := return (← read).tiedPeersOrder r ps
  tiedGroupsOrder r p gs := return (← read).tiedGroupsOrder r p gs
  hasRoom p := return (← read).hasRoom p
  popOwedAnswer p := return (← read).popOwedAnswer p
  owedOrder p gs := return (← read).owedOrder p gs
  sha256 b := return (← read).sha256 b
  serialize d := return (← read).serialize d
  snappyBlockEncode b := return (← read).snappyBlockEncode b
  padEach s n := return (← read).padEach s n
  rsParity s k := return (← read).rsParity s k
  merkleRoot l := return (← read).merkleRoot l
  merkleProof l i := return (← read).merkleProof l i
  contentId f := return (← read).contentId f
  connected q := return (← read).connected q
  groupBits ids := return (← read).groupBits ids
  heldBackOrder ks := return (← read).heldBackOrder ks
  gossipIds := return (← read).gossipIds
  topicPeers := return (← read).topicPeers
  meshHas q := return (← read).meshHas q
  gossipEligible q := return (← read).gossipEligible q
  sample xs k := return (← read).sample xs k
  meshList := return (← read).meshList
  resolve a := return (← read).resolve a
  chunkOf a := return (← read).chunkOf a
  handleGraftPrune p := return (← read).handleGraftPrune p
  onIwantNode p ids := return (← read).onIwantNode p ids
  decodeAndReencode g d := return (← read).decodeAndReencode g d
  payloadOf r := return (← read).payloadOf r
  deliver _ _ := pure ()
  chunkAt g i := return (← read).chunkAt g i
  blockRoot b := return (← read).blockRoot b
  shuffledNats xs := return (← read).shuffledNats xs
  wake _ := pure ()
  writing p := return (← read).writing p
  tiebreak c p := return (← read).tiebreak c p
  peerIdBytes p := return (← read).peerIdBytes p
  pushRebuiltNode _ _ := pure ()
  verifyMerkleProof r d i c p := return (← read).verifyMerkleProof r d i c p
  closePromisesOfGroup _ := pure ()
  discardQueued _ := pure ()
  discardPaced _ := pure ()
  gossipRemoveGroup _ := pure ()
  crash msg := do
    modifyThe World fun w => { w with crashed := w.crashed ++ [msg] }
    pure default
  branch _ := pure ()
  enter _ := pure ()

/-- The twin's tables under this interpreter: the world's `st`, and no note of what is touched. -/
instance instTablesI : Tables I := Tables.ofState fun _ => pure ()

/-- A call of the twin, run from the world `w` with the answers `ans`: its value and the world it leaves. -/
def run {α : Type} (x : M I α) (ctx : Ctx) (ans : Answers) (w : World) : α × World :=
  Id.run (((x.run ctx).run ans).run w)

/-- **The step.** The armed timer at place `i` fires: it is taken away, and the twin's `retry_offer(a)` runs. -/
def retryFire (i : Nat) (a : Key) (ctx : Ctx) (ans : Answers) (w : World) : World :=
  (run (SpecTwin.retryOffer (m := I) a) ctx ans { w with timers := w.timers.eraseIdx i }).2

/-! ## What the twin's questions read of the world, as plain functions

Each is proved below to be the twin's own function, run. The statements and the abstraction are written with
them, so that a hypothesis is about the state, the answers or the constants. -/

/-- `stop_pull[g]`: the group's pull is stopped. The twin's own table, not an answer of the node's. `claim_group`,
`drop_group` and `publish` set it (`Sec42.lean` 215, `Sec46.lean` 51, `Sec51.lean` 97), and no function of the
twin clears it. -/
def stopP (st : State) (g : Group) : Bool := st.stopPull.contains g

/-- `held(a)`, by the chunk: its index is in `mine[g]`. -/
def heldP (st : State) (k : Chunk) : Bool := (st.mine.getD k.1 0).has k.2

/-- `parked(q, a)`, by the group: `now < park[q][g]`, a missing park reading as minus infinity. -/
def parkedP (now : Float) (st : State) (q : Peer) (g : Group) : Bool :=
  decide (now < (((st.park.getD q {}).get? g).getD negInf))

/-- `tied_to_root(q, a)`, by the chunk: a copy of the chunk from q waits for some root. -/
def tiedP (st : State) (q : Peer) (k : Chunk) : Bool :=
  (st.tied.toList.map fun ((r, m) : Root × Std.HashMap Peer (Std.HashMap Group Bits)) =>
      (r, m.toList.map fun ((p, m) : Peer × Std.HashMap Group Bits) => (p, m.toList))).any fun (_, peers) =>
    peers.any fun (p, groups) => p == q && groups.any fun (g, bits) => g == k.1 && bits.has k.2

/-- The first clause of `outstanding(q, a)`: a promise of some key of the chunk to q is open. -/
def promisedP (st : State) (q : Peer) (k : Chunk) : Bool :=
  st.promises.toList.any (fun ((b, r), _) => r == q && b.chunk == k)

/-- Its second clause: an IWANT in `queue[q].normal` names the chunk. -/
def queuedP (st : State) (q : Peer) (k : Chunk) : Bool :=
  (((st.queue.getD q {}).get? .normal).getD []).any (fun e => e.asks.any (fun b => b.chunk == k))

/-- `outstanding(q, a)`, by the chunk. -/
def outstandingP (st : State) (q : Peer) (k : Chunk) : Bool := promisedP st q k || queuedP st q k

/-- `announcers(a)`: the list, then every other connected peer that offered a's chunk, in the node's own order. -/
def announcersP (ans : Answers) (st : State) (a : Key) : List Peer :=
  (st.offers.getD a []) ++
    ans.ownOrder (ans.connectedTopicPeers.filter fun q =>
      !(st.offers.getD a []).contains q && ((st.offered.getD q {}).getD a.group 0).has a.index) a

/-- `retry_offer`'s candidates: the announcers neither parked nor tied. -/
def candsP (ctx : Ctx) (ans : Answers) (st : State) (a : Key) : List Peer :=
  (announcersP ans st a).filter fun q => !parkedP ctx.now st q a.group && !tiedP st q a.chunk

/-- Those of them with no ask outstanding. -/
def freeP (ctx : Ctx) (ans : Answers) (st : State) (a : Key) : List Peer :=
  (candsP ctx ans st a).filter fun q => !outstandingP st q a.chunk

/-- Some key of the chunk has q on its offer list, or q is connected and offered the chunk beyond the lists: q is
in `announcers(b)` for a key b of the chunk, whatever the node's own order (a permutation). -/
def offeredP (ans : Answers) (st : State) (k : Chunk) (q : Peer) : Bool :=
  st.offers.toList.any (fun (b, o) => b.chunk == k && o.contains q) ||
    (ans.connectedTopicPeers.contains q && ((st.offered.getD q {}).getD k.1 0).has k.2)

/-- Some key of the chunk has its window open at `now`: `now − asked_at[b] < IWANT_WINDOW`. -/
def windowP (ctx : Ctx) (st : State) (k : Chunk) : Bool :=
  st.askedAt.toList.any fun (b, t) => b.chunk == k && decide (ctx.now - t < ctx.c.IWANT_WINDOW)

/-- A retry timer of some key of the chunk is armed. -/
def retryArmedP (w : World) (k : Chunk) : Bool :=
  w.timers.any fun (_, t) => match t with
    | .retryOffer b => b.chunk == k
    | _ => false

/-- `tried[a].get(q)` -/
def triedP (st : State) (a : Key) (q : Peer) : Option Float := (st.tried.getD a {}).get? q

/-- One turn of `least_recently_tried`'s loop: the first of the least so far. A candidate never tried is passed
over here; the twin raises there, and is shown not to get there. -/
def lrtStep (st : State) (a : Key) (best : Option (Peer × Float)) (q : Peer) : Option (Peer × Float) :=
  match triedP st a q with
  | none => best
  | some t =>
    match best with
    | none => some (q, t)
    | some (bq, bt) => if t < bt then some (q, t) else some (bq, bt)

/-- **The pick:** the earliest announcer of `free` not asked yet, or else the least recently tried, the first of
the least. It is `retry_offer`'s own pick (`retryFire_asks`), so the pick is part of what is proved, not a
hypothesis. -/
def pickP (ctx : Ctx) (ans : Answers) (st : State) (a : Key) : Peer :=
  match (freeP ctx ans st a).find? fun q => (triedP st a q).isNone with
  | some q => q
  | none => (((freeP ctx ans st a).foldl (lrtStep st a) none).map (·.1)).getD default

/-- **The world after the asking path:** `may_ask` notes the ask (`asked_at`, `tried`) and arms the next retry,
after the fired timer is gone; then, where the queue takes the IWANT, the pick's normal lane grows by it and the
count of the chunk's asks to the pick goes up. Nothing else changes, and nothing raised. -/
def askedWorld (i : Nat) (a : Key) (ctx : Ctx) (ans : Answers) (w : World) : World :=
  let pick := pickP ctx ans w.st a
  let w1 : World := { w with
    st := { w.st with
      askedAt := w.st.askedAt.insert a ctx.now
      tried := w.st.tried.insert a ((w.st.tried.getD a {}).insert pick ctx.now) }
    timers := w.timers.eraseIdx i ++ [(ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK, .retryOffer a)] }
  if ans.admits pick (.iwant [a]) false then w1.push pick .normal (entryOf (.iwant [a])) else w1

/-! ## The twin's code, run: one lemma per operation, then per function

`run_bind_eq` takes a call one bind at a time. The leaf lemmas hold by computation; they are stated with `id rfl`
so that `simp` uses them as rewrite rules and not by unfolding. A filter whose test leaves the world alone is a
plain filter (`run_filterM`), and a `for` loop whose body does is a plain loop (`run_forIn`). -/

section
variable {α β : Type} {ctx : Ctx} {ans : Answers} {w : World}

theorem run_pure (v : α) : run (pure v : M I α) ctx ans w = (v, w) := id rfl

theorem run_bind (x : M I α) (f : α → M I β) :
    run (x >>= f) ctx ans w = run (f (run x ctx ans w).1) ctx ans (run x ctx ans w).2 := rfl

theorem run_ite (c : Prop) [Decidable c] (x y : M I α) :
    run (if c then x else y) ctx ans w = if c then run x ctx ans w else run y ctx ans w := by
  split <;> rfl

theorem run_read : run (read : M I Ctx) ctx ans w = (ctx, w) := id rfl
theorem run_enter (s : String) : run (Node61.enter s : M I Unit) ctx ans w = ((), w) := id rfl
theorem run_branch (s : String) : run (Node61.branch s : M I Unit) ctx ans w = ((), w) := id rfl
theorem run_stopPull (g : Group) : run (Tables.stopPull g : M I Bool) ctx ans w = (stopP w.st g, w) := id rfl
theorem run_expired (g : Group) : run (Node61.expired g : M I Bool) ctx ans w = (ans.expired g, w) := id rfl
theorem run_connected : run (Node61.connectedTopicPeers : M I _) ctx ans w = (ans.connectedTopicPeers, w) := id rfl
theorem run_ownOrder (xs : List Peer) (a : Key) : run (Node61.ownOrder xs a : M I _) ctx ans w = (ans.ownOrder xs a, w) := id rfl
theorem run_askedAt (a : Key) : run (Tables.askedAt? a : M I _) ctx ans w = (w.st.askedAt.get? a, w) := id rfl
theorem run_tried (a : Key) (q : Peer) : run (Tables.tried? a q : M I _) ctx ans w = (triedP w.st a q, w) := id rfl
theorem run_offersOf (a : Key) : run (Tables.offersOf a : M I _) ctx ans w = (w.st.offers.getD a [], w) := id rfl
theorem run_offeredBits (q : Peer) (g : Group) : run (Tables.offeredBits q g : M I _) ctx ans w = ((w.st.offered.getD q {}).getD g 0, w) := id rfl
theorem run_parkUntil (q : Peer) (g : Group) : run (Tables.parkUntil? q g : M I _) ctx ans w = ((w.st.park.getD q {}).get? g, w) := id rfl
theorem run_mineBits (g : Group) : run (Tables.mineBits g : M I _) ctx ans w = (w.st.mine.getD g 0, w) := id rfl
theorem run_allPromises : run (Tables.allPromises : M I _) ctx ans w = (w.st.promises.toList, w) := id rfl
theorem run_lane (q : Peer) (l : Lane) : run (Tables.lane? q l : M I _) ctx ans w = ((w.st.queue.getD q {}).get? l, w) := id rfl
theorem run_allTiedAll : run (Tables.allTiedAll : M I _) ctx ans w =
  (w.st.tied.toList.map fun ((r, m) : Root × Std.HashMap Peer (Std.HashMap Group Bits)) =>
      (r, m.toList.map fun ((p, m) : Peer × Std.HashMap Group Bits) => (p, m.toList)), w) := id rfl
theorem run_setAskedAt (a : Key) (t : Float) : run (Tables.setAskedAt a t : M I _) ctx ans w =
  ((), { w with st := { w.st with askedAt := w.st.askedAt.insert a t } }) := id rfl
theorem run_setTried (a : Key) (p : Peer) (t : Float) : run (Tables.setTried a p t : M I _) ctx ans w =
  ((), { w with st := { w.st with tried := w.st.tried.insert a ((w.st.tried.getD a {}).insert p t) } }) := id rfl
theorem run_after (d : Float) (t : Timer) : run (Node61.after d t : M I _) ctx ans w =
  ((), { w with timers := w.timers ++ [(d, t)] }) := id rfl
theorem run_enqueue (p : Peer) (x : Msg) (u : Bool) : run (Node61.enqueue p x u : M I _) ctx ans w =
  (ans.enqueue p x u, if !(entryOf x).isEmpty && ans.admits p x u then w.push p (if u then .urgent else .normal) (entryOf x) else w) := by
  simp [run, Node61.enqueue, ReaderT.run, StateT.run, bind, ReaderT.bind, StateT.bind, read, readThe, MonadReaderOf.read, ReaderT.read, monadLift,
    MonadLift.monadLift, MonadLiftT.monadLift, pure, StateT.pure, modifyThe, MonadStateOf.modifyGet]
  split <;> rfl

theorem run_filterAuxM (f : α → M I Bool) (g : α → Bool) (h : ∀ x, run (f x) ctx ans w = (g x, w))
    (xs acc : List α) : run (List.filterAuxM f xs acc) ctx ans w = ((xs.filter g).reverse ++ acc, w) := by
  induction xs generalizing acc with
  | nil => simp [List.filterAuxM, run_pure]
  | cons x xs ih =>
    simp only [List.filterAuxM, run_bind, h, ih]
    cases hg : g x <;> simp [hg]

theorem run_filterM (f : α → M I Bool) (g : α → Bool) (h : ∀ x, run (f x) ctx ans w = (g x, w))
    (xs : List α) : run (xs.filterM f) ctx ans w = (xs.filter g, w) := by
  simp only [List.filterM, run_bind, run_filterAuxM f g h, run_pure]
  simp

/-- A `for` loop over a list, without the monad: what it leaves, stopping at the first `done`. -/
def loopP {σ : Type} (g : α → σ → ForInStep σ) : List α → σ → σ
  | [], s => s
  | x :: xs, s => match g x s with
    | .done s' => s'
    | .yield s' => loopP g xs s'

theorem run_forIn {σ : Type} (f : α → σ → M I (ForInStep σ)) (g : α → σ → ForInStep σ) (xs : List α)
    (h : ∀ x ∈ xs, ∀ s, run (f x s) ctx ans w = (g x s, w)) (s : σ) :
    run (forIn xs s f) ctx ans w = (loopP g xs s, w) := by
  induction xs generalizing s with
  | nil => simp [run_pure, loopP]
  | cons x xs ih =>
    simp only [List.forIn_cons, run_bind, h x (List.mem_cons_self) s, loopP]
    cases g x s with
    | done s' => simp [run_pure]
    | yield s' => exact ih (fun y hy => h y (List.mem_cons_of_mem _ hy)) s'

theorem run_held (a : Key) : run (SpecTwin.held (m := I) a) ctx ans w = (heldP w.st a.chunk, w) := id rfl
theorem run_parked (q : Peer) (a : Key) :
    run (SpecTwin.parked (m := I) q a) ctx ans w = (parkedP ctx.now w.st q a.group, w) := id rfl
theorem run_tiedToRoot (q : Peer) (a : Key) :
    run (SpecTwin.tiedToRoot (m := I) q a) ctx ans w = (tiedP w.st q a.chunk, w) := id rfl
theorem run_outstanding (q : Peer) (a : Key) :
    run (SpecTwin.outstanding (m := I) q a) ctx ans w = (outstandingP w.st q a.chunk, w) := by
  unfold SpecTwin.outstanding
  simp only [run_bind, run_ite, run_enter, run_allPromises]
  split
  · next h =>
    have hp : promisedP w.st q a.chunk = true := h
    simp [run_branch, run_pure, outstandingP, hp]
  · next h =>
    have hp : promisedP w.st q a.chunk = false := Bool.eq_false_of_ne_true h
    simp [run_branch, run_pure, run_lane, outstandingP, hp, queuedP]
theorem run_announcers (a : Key) :
    run (SpecTwin.announcers (m := I) a) ctx ans w = (announcersP ans w.st a, w) := by
  unfold SpecTwin.announcers
  simp only [run_bind, run_enter, run_offersOf, run_connected]
  rw [run_filterM (g := fun q => !(w.st.offers.getD a []).contains q && ((w.st.offered.getD q {}).getD a.group 0).has a.index)]
  · simp only [run_ownOrder, run_pure, announcersP]
  · intro q
    simp only [run_ite, run_bind, run_offeredBits, run_pure]
    cases h : (w.st.offers.getD a []).contains q <;> simp

theorem loopP_find (p : α → Bool) (xs : List α) :
    loopP (fun q (_ : Option (Option α) × Unit) =>
      if p q then ForInStep.done (some (some q), ()) else ForInStep.yield (none, ())) xs (none, ()) =
      ((xs.find? p).map some, ()) := by
  induction xs with
  | nil => rfl
  | cons x xs ih => cases h : p x <;> simp [loopP, h, ih]

theorem loopP_foldl {σ : Type} (f : σ → α → σ) (xs : List α) (s : σ) :
    loopP (fun x s => ForInStep.yield (f s x)) xs s = xs.foldl f s := by
  induction xs generalizing s with
  | nil => rfl
  | cons x xs ih => simp [loopP, ih]

theorem run_untried (cands : List Peer) (a : Key) :
    run (SpecTwin.untried (m := I) cands a) ctx ans w =
      (cands.find? (fun q => (triedP w.st a q).isNone), w) := by
  unfold SpecTwin.untried
  simp only [run_bind, run_enter]
  rw [run_forIn (g := fun q _ =>
    if (triedP w.st a q).isNone then ForInStep.done (some (some q), ()) else ForInStep.yield (none, ()))]
  · rw [loopP_find]
    cases cands.find? (fun q => (triedP w.st a q).isNone) <;> simp [run_pure]
  · intro q _ s
    simp only [run_bind, run_tried, run_ite, run_pure]
    split <;> rfl

theorem lrt_fold (st : State) (a : Key) (cands : List Peer) (hall : ∀ q ∈ cands, (triedP st a q).isSome)
    (best : Option (Peer × Float)) (hne : cands ≠ [] ∨ best.isSome) :
    ∃ p t, cands.foldl (lrtStep st a) best = some (p, t) ∧ (p ∈ cands ∨ ∃ t', best = some (p, t')) := by
  induction cands generalizing best with
  | nil =>
    cases best with
    | none => simp at hne
    | some b => exact ⟨b.1, b.2, rfl, Or.inr ⟨b.2, rfl⟩⟩
  | cons q qs ih =>
    have hq := hall q List.mem_cons_self
    obtain ⟨t, ht⟩ := Option.isSome_iff_exists.mp hq
    have hstep : (lrtStep st a best q).isSome := by
      unfold lrtStep; rw [ht]; cases best with
      | none => rfl
      | some b => simp only []; split <;> rfl
    obtain ⟨p, t', hf, hm⟩ := ih (fun y hy => hall y (List.mem_cons_of_mem _ hy)) (lrtStep st a best q) (Or.inr hstep)
    refine ⟨p, t', by simpa [List.foldl_cons] using hf, ?_⟩
    rcases hm with hm | ⟨t'', hb⟩
    · exact Or.inl (List.mem_cons_of_mem _ hm)
    · unfold lrtStep at hb; rw [ht] at hb
      cases best with
      | none => simp at hb; exact Or.inl (by simp [hb.1])
      | some b =>
        simp only [] at hb
        split at hb
        · simp at hb; exact Or.inl (by simp [hb.1])
        · simp at hb; exact Or.inr ⟨b.2, by rw [← hb.1]⟩

theorem run_leastRecentlyTried (cands : List Peer) (a : Key) (hall : ∀ q ∈ cands, (triedP w.st a q).isSome)
    (hne : cands ≠ []) :
    run (SpecTwin.leastRecentlyTried (m := I) cands a) ctx ans w =
      (((cands.foldl (lrtStep w.st a) none).map (·.1)).getD default, w) := by
  unfold SpecTwin.leastRecentlyTried
  simp only [run_bind, run_enter]
  rw [run_forIn (g := fun q best => ForInStep.yield (lrtStep w.st a best q))]
  · rw [loopP_foldl]
    obtain ⟨p, t, hf, _⟩ := lrt_fold w.st a cands hall none (Or.inl hne)
    simp [hf, run_pure]
  · intro q hq best
    obtain ⟨t, ht⟩ := Option.isSome_iff_exists.mp (hall q hq)
    simp only [run_bind, run_tried, ht, lrtStep]
    cases best with
    | none => simp [run_pure]
    | some b => simp only [run_ite, run_pure]; split <;> rfl

theorem run_bind_eq (x : M I α) (f : α → M I β) {v : α} {w' : World} (h : run x ctx ans w = (v, w')) :
    run (x >>= f) ctx ans w = run (f v) ctx ans w' := by rw [run_bind, h]

theorem run_bind_filterM {γ : Type} (f : γ → M I Bool) (g : γ → Bool) (xs : List γ) (k : List γ → M I β)
    (h : ∀ x, run (f x) ctx ans w = (g x, w)) :
    run (xs.filterM f >>= k) ctx ans w = run (k (xs.filter g)) ctx ans w := by
  rw [run_bind, run_filterM f g h]

theorem run_mayAsk (a : Key) (p : Peer)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false) :
    run (SpecTwin.mayAsk (m := I) a p) ctx ans w =
      (true, { w with
        st := { w.st with
          askedAt := w.st.askedAt.insert a ctx.now
          tried := w.st.tried.insert a ((w.st.tried.getD a {}).insert p ctx.now) }
        timers := w.timers ++ [(ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK, .retryOffer a)] }) := by
  have hw := of_decide_eq_false hwin
  unfold SpecTwin.mayAsk
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_askedAt _)]
  cases h : w.st.askedAt.get? a with
  | none =>
    dsimp only
    rw [run_bind_eq _ _ (run_setAskedAt _ _), run_bind_eq _ _ (run_setTried _ _ _),
      run_bind_eq _ _ (run_after _ _), run_bind_eq _ _ (run_branch _), run_pure]
  | some t =>
    rw [h] at hw
    simp only [Option.getD_some] at hw
    dsimp only
    rw [run_ite, ite_eq_right hw]
    rw [run_bind_eq _ _ (run_setAskedAt _ _), run_bind_eq _ _ (run_setTried _ _ _),
      run_bind_eq _ _ (run_after _ _), run_bind_eq _ _ (run_branch _), run_pure]

theorem pickP_mem (a : Key) (st : State) (hfree : freeP ctx ans st a ≠ []) :
    pickP ctx ans st a ∈ freeP ctx ans st a := by
  unfold pickP
  cases h : (freeP ctx ans st a).find? (fun q => (triedP st a q).isNone) with
  | some q => exact List.mem_of_find?_eq_some h
  | none =>
    have hall : ∀ q ∈ freeP ctx ans st a, (triedP st a q).isSome := by
      intro q hq
      have := List.find?_eq_none.mp h q hq
      cases ht : triedP st a q with
      | none => simp [ht] at this
      | some t => rfl
    obtain ⟨p, t, hf, hm⟩ := lrt_fold st a _ hall none (Or.inl hfree)
    simp only [hf, Option.map_some, Option.getD_some]
    rcases hm with hm | ⟨_, hb⟩
    · exact hm
    · simp at hb

theorem iwant_not_empty (a : Key) : (entryOf (.iwant [a])).isEmpty = false := rfl

theorem run_retryOffer_asks {a : Key}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ []) :
    (run (SpecTwin.retryOffer (m := I) a) ctx ans w).2 =
      if ans.admits (pickP ctx ans w.st a) (.iwant [a]) false then
        ({ w with
            st := { w.st with
              askedAt := w.st.askedAt.insert a ctx.now
              tried := w.st.tried.insert a ((w.st.tried.getD a {}).insert (pickP ctx ans w.st a) ctx.now) }
            timers := w.timers ++ [(ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK, .retryOffer a)] } : World).push
          (pickP ctx ans w.st a) .normal (entryOf (.iwant [a]))
      else
        { w with
          st := { w.st with
            askedAt := w.st.askedAt.insert a ctx.now
            tried := w.st.tried.insert a ((w.st.tried.getD a {}).insert (pickP ctx ans w.st a) ctx.now) }
          timers := w.timers ++ [(ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK, .retryOffer a)] } := by
  have hw := of_decide_eq_false hwin
  have hcands : ¬ (List.filter (fun q => !parkedP ctx.now w.st q a.group && !tiedP w.st q a.chunk)
      (announcersP ans w.st a)).isEmpty = true := by
    intro h
    exact hfree (by simp [freeP, candsP, List.isEmpty_iff.mp h])
  have hfr : ¬ (freeP ctx ans w.st a).isEmpty = true := fun h => hfree (List.isEmpty_iff.mp h)
  have hfree_eq : List.filter (fun q => !outstandingP w.st q a.chunk)
      (List.filter (fun q => !parkedP ctx.now w.st q a.group && !tiedP w.st q a.chunk) (announcersP ans w.st a)) =
      freeP ctx ans w.st a := rfl
  unfold SpecTwin.retryOffer
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_held _)]
  rw [run_ite, ite_eq_right (by simp [hheld])]
  rw [run_bind_eq _ _ (run_stopPull _), run_ite, ite_eq_right (by simp [hstop])]
  rw [run_bind_eq _ _ (run_expired _), run_ite, ite_eq_right (by simp [hexp])]
  rw [run_bind_eq _ _ (run_askedAt _), run_ite, ite_eq_right hw]
  rw [run_bind_eq _ _ (run_announcers _)]
  rw [run_bind_filterM (g := fun q => !parkedP ctx.now w.st q a.group && !tiedP w.st q a.chunk)]
  · rw [run_ite, ite_eq_right hcands]
    rw [run_bind_filterM (g := fun q => !outstandingP w.st q a.chunk)]
    · rw [hfree_eq, run_ite, ite_eq_right hfr, run_bind_eq _ _ (run_untried _ _)]
      cases hfind : (freeP ctx ans w.st a).find? (fun q => (triedP w.st a q).isNone) with
      | some q =>
        have hp : pickP ctx ans w.st a = q := by unfold pickP; rw [hfind]
        dsimp only
        rw [run_bind_eq _ _ (run_branch _), run_bind_eq _ _ (run_pure _), run_bind_eq _ _ (run_mayAsk a q hwin)]
        rw [run_ite, ite_eq_left rfl, run_bind_eq _ _ (run_enqueue _ _ _), run_pure, hp]
        cases ans.admits q (.iwant [a]) false <;> rfl
      | none =>
        have hall : ∀ q ∈ freeP ctx ans w.st a, (triedP w.st a q).isSome := by
          intro q hq
          have := List.find?_eq_none.mp hfind q hq
          cases ht : triedP w.st a q with
          | none => simp [ht] at this
          | some t => rfl
        have hp : pickP ctx ans w.st a =
            (((freeP ctx ans w.st a).foldl (lrtStep w.st a) none).map (·.1)).getD default := by
          unfold pickP; rw [hfind]
        dsimp only
        rw [run_bind_eq _ _ (run_branch _),
          run_bind_eq _ _ (run_leastRecentlyTried _ a hall hfree), ← hp,
          run_bind_eq _ _ (run_mayAsk a _ hwin)]
        rw [run_ite, ite_eq_left rfl, run_bind_eq _ _ (run_enqueue _ _ _), run_pure]
        cases ans.admits (pickP ctx ans w.st a) (.iwant [a]) false <;> rfl
    · intro q
      rw [run_bind_eq _ _ (run_outstanding _ _), run_pure]
  · intro q
    rw [run_bind_eq _ _ (run_parked _ _), run_ite]
    cases parkedP ctx.now w.st q a.group
    · rw [ite_eq_right (by simp), run_bind_eq _ _ (run_tiedToRoot _ _), run_pure]; rfl
    · rw [ite_eq_left rfl, run_pure]; rfl
end

/-- **The twin's side of the asking path.** Where the chunk is not held, the pull not stopped, the group not
expired, the key's window closed, and some announcer is neither parked, nor tied, nor outstanding: the firing
leaves `askedWorld`. This is a statement about the twin's own `retry_offer`, run: its two filters over the
announcers, `untried`'s and `least_recently_tried`'s loops, `may_ask`, `after` and `enqueue`. -/
theorem retryFire_asks {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ []) :
    retryFire i a ctx ans w = askedWorld i a ctx ans w := by
  unfold retryFire
  rw [run_retryOffer_asks (w := { w with timers := w.timers.eraseIdx i }) hheld hstop hexp hwin hfree]
  rfl

/-- **The interpreter's queue is the twin's own.** After a firing whose ask the queue took, the twin's own
`outstanding(pick, a)`, run in the world the firing left, answers true: the ask is where the twin's code looks
for it. -/
theorem retryFire_admitted_outstanding {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = true) :
    (run (SpecTwin.outstanding (m := I) (pickP ctx ans w.st a) a) ctx ans (retryFire i a ctx ans w)).1 = true := by
  rw [run_outstanding, retryFire_asks hheld hstop hexp hwin hfree]
  simp [askedWorld, hadm, World.push, outstandingP, queuedP, entryOf, QEntry.asks]

/-- **A refusal leaves the history and the queue as they were:** no ask is counted, and no lane grows. -/
theorem retryFire_refused_keeps {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = false) (hstop : stopP w.st a.group = false)
    (hexp : ans.expired a.group = false)
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hfree : freeP ctx ans w.st a ≠ [])
    (hadm : ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = false) :
    (retryFire i a ctx ans w).made = w.made ∧ (retryFire i a ctx ans w).st.queue = w.st.queue := by
  rw [retryFire_asks hheld hstop hexp hwin hfree]
  simp [askedWorld, hadm]

/-! ## What the asking path leaves, table by table -/
section
variable (i : Nat) (a : Key) (ctx : Ctx) (ans : Answers) (w : World)

theorem askedWorld_mine : (askedWorld i a ctx ans w).st.mine = w.st.mine := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_stopPull : (askedWorld i a ctx ans w).st.stopPull = w.st.stopPull := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_offers : (askedWorld i a ctx ans w).st.offers = w.st.offers := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_offered : (askedWorld i a ctx ans w).st.offered = w.st.offered := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_park : (askedWorld i a ctx ans w).st.park = w.st.park := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_promises : (askedWorld i a ctx ans w).st.promises = w.st.promises := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_tied : (askedWorld i a ctx ans w).st.tied = w.st.tied := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_lrArmed : (askedWorld i a ctx ans w).st.lastResortArmed = w.st.lastResortArmed := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_askedParked : (askedWorld i a ctx ans w).st.askedParked = w.st.askedParked := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_crashed : (askedWorld i a ctx ans w).crashed = w.crashed := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_askedAt : (askedWorld i a ctx ans w).st.askedAt = w.st.askedAt.insert a ctx.now := by
  unfold askedWorld; dsimp only; split <;> rfl
theorem askedWorld_timers : (askedWorld i a ctx ans w).timers =
    w.timers.eraseIdx i ++ [(ctx.c.IWANT_WINDOW + ctx.c.RETRY_SLACK, .retryOffer a)] := by
  unfold askedWorld; dsimp only; split <;> rfl

/-- The count of the chunk's asks goes up by one for the pick where the queue took the ask, and nowhere else. -/
theorem askedWorld_made (q : Peer) : (askedWorld i a ctx ans w).made a.chunk q =
    w.made a.chunk q +
      (if ans.admits (pickP ctx ans w.st a) (.iwant [a]) false = true ∧ q = pickP ctx ans w.st a then 1 else 0) := by
  unfold askedWorld; dsimp only
  split
  · next h => by_cases hq : q = pickP ctx ans w.st a <;> simp [World.push, entryOf, QEntry.asks, h, hq]
  · next h => simp [h]

/-- A queued ask of the chunk: as before, and to the pick where the queue took the ask. -/
theorem askedWorld_queued (q : Peer) : queuedP (askedWorld i a ctx ans w).st q a.chunk =
    (queuedP w.st q a.chunk ||
      (ans.admits (pickP ctx ans w.st a) (.iwant [a]) false && decide (q = pickP ctx ans w.st a))) := by
  unfold askedWorld; dsimp only
  split
  · next h =>
    by_cases hq : q = pickP ctx ans w.st a
    · subst hq
      simp [World.push, queuedP, entryOf, QEntry.asks, h]
    · have hq' : ¬ pickP ctx ans w.st a = q := fun e => hq e.symm
      simp [World.push, queuedP, h, hq, Std.HashMap.getD_insert, hq']
  · next h => simp [queuedP, h]
end

/-! ## What the hypotheses give of the world before -/

theorem retryArmedP_of_timer {w : World} {i : Nat} {d : Float} {a : Key}
    (h : w.timers[i]? = some (d, Timer.retryOffer a)) : retryArmedP w a.chunk = true := by
  unfold retryArmedP
  rw [List.any_eq_true]
  exact ⟨(d, .retryOffer a), List.mem_of_getElem? h, by simp⟩

theorem retryArmedP_asked (i : Nat) (a : Key) (ctx : Ctx) (ans : Answers) (w : World) :
    retryArmedP (askedWorld i a ctx ans w) a.chunk = true := by
  unfold retryArmedP
  rw [askedWorld_timers]
  simp

theorem windowP_closed {ctx : Ctx} {w : World} {a : Key}
    (hwin : decide (ctx.now - (w.st.askedAt.get? a).getD negInf < ctx.c.IWANT_WINDOW) = false)
    (hone : ∀ b : Key, b.chunk = a.chunk → b ∈ w.st.askedAt → b = a) :
    windowP ctx w.st a.chunk = false := by
  have hw := of_decide_eq_false hwin
  unfold windowP
  rw [Bool.eq_false_iff]
  intro h
  rw [List.any_eq_true] at h
  obtain ⟨⟨b, t⟩, hmem, hb⟩ := h
  simp only [Bool.and_eq_true, beq_iff_eq, decide_eq_true_eq] at hb
  have hget := Std.HashMap.mem_toList_iff_getElem?_eq_some.mp hmem
  have hin : b ∈ w.st.askedAt := by
    rw [Std.HashMap.mem_iff_isSome_getElem?, hget]; rfl
  have hba := hone b hb.1 hin
  subst hba
  have : w.st.askedAt.get? b = some t := by simpa using hget
  rw [this] at hw
  exact hw hb.2

theorem windowP_asked (i : Nat) (a : Key) (ctx : Ctx) (ans : Answers) (w : World)
    (hW : ctx.now - ctx.now < ctx.c.IWANT_WINDOW) :
    windowP ctx (askedWorld i a ctx ans w).st a.chunk = true := by
  unfold windowP
  rw [askedWorld_askedAt, List.any_eq_true]
  refine ⟨(a, ctx.now), ?_, by simp [hW]⟩
  rw [Std.HashMap.mem_toList_iff_getElem?_eq_some]
  simp

theorem offeredP_of_announcer {ans : Answers} {st : State} {a : Key} {q : Peer}
    (hperm : ∀ (xs : List Peer) (b : Key), (ans.ownOrder xs b).Perm xs)
    (h : q ∈ announcersP ans st a) : offeredP ans st a.chunk q = true := by
  unfold announcersP at h
  unfold offeredP
  rw [List.mem_append] at h
  rcases h with h | h
  · have hin : a ∈ st.offers := by
      rw [Std.HashMap.mem_iff_contains]
      cases hc : st.offers.contains a with
      | true => rfl
      | false =>
        have : st.offers.getD a [] = [] := Std.HashMap.getD_eq_fallback_of_contains_eq_false hc
        rw [this] at h; simp at h
    have hget : st.offers[a]? = some (st.offers.getD a []) := by
      rw [Std.HashMap.getD_eq_getD_getElem?]
      obtain ⟨o, ho⟩ := Option.isSome_iff_exists.mp (Std.HashMap.mem_iff_isSome_getElem?.mp hin)
      simp [ho]
    rw [Bool.or_eq_true]
    left
    rw [List.any_eq_true]
    exact ⟨(a, st.offers.getD a []), Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr hget, by simp [h]⟩
  · have h' := (hperm _ a).mem_iff.mp h
    rw [List.mem_filter] at h'
    simp only [Bool.and_eq_true] at h'
    rw [Bool.or_eq_true]
    right
    simp [h'.1, h'.2.2, Key.chunk]

theorem free_gives {ctx : Ctx} {ans : Answers} {st : State} {a : Key} {q : Peer} (h : q ∈ freeP ctx ans st a) :
    q ∈ announcersP ans st a ∧ parkedP ctx.now st q a.group = false ∧ tiedP st q a.chunk = false ∧
      outstandingP st q a.chunk = false := by
  unfold freeP candsP at h
  simp only [List.mem_filter, Bool.and_eq_true, Bool.not_eq_true'] at h
  exact ⟨h.1.1, h.1.2.1, h.1.2.2, h.2⟩

/-! ## The `held` branch, and a firing read at another chunk -/

/-- An element the test is false on, taken away, leaves `any` as it was. -/
theorem any_eraseIdx_of_false {α : Type} (p : α → Bool) (l : List α) (i : Nat) (x : α)
    (h : l[i]? = some x) (hx : p x = false) : (l.eraseIdx i).any p = l.any p := by
  induction l generalizing i with
  | nil => simp
  | cons y ys ih =>
    cases i with
    | zero =>
      simp only [List.getElem?_cons_zero, Option.some.injEq] at h
      subst h
      simp [hx]
    | succ i =>
      simp only [List.getElem?_cons_succ] at h
      simp [ih i h]

/-- An entry the test is false on, inserted, leaves `any` over the map as it was. -/
theorem any_toList_insert_of_false {β : Type} (m : Std.HashMap Key β) (a : Key) (v : β) (p : Key × β → Bool)
    (hp : ∀ v', p (a, v') = false) : (m.insert a v).toList.any p = m.toList.any p := by
  rw [Bool.eq_iff_iff, List.any_eq_true, List.any_eq_true]
  constructor
  · rintro ⟨⟨b, t⟩, hmem, hb⟩
    have hget := Std.HashMap.mem_toList_iff_getElem?_eq_some.mp hmem
    rw [Std.HashMap.getElem?_insert] at hget
    by_cases hab : a = b
    · subst hab; rw [hp t] at hb; exact absurd hb (by simp)
    · simp only [beq_iff_eq, hab, ↓reduceIte] at hget
      exact ⟨(b, t), Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr hget, hb⟩
  · rintro ⟨⟨b, t⟩, hmem, hb⟩
    have hget := Std.HashMap.mem_toList_iff_getElem?_eq_some.mp hmem
    have hab : ¬ a = b := by
      intro hab; subst hab; rw [hp t] at hb; exact absurd hb (by simp)
    refine ⟨(b, t), Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr ?_, hb⟩
    rw [Std.HashMap.getElem?_insert]
    simp only [beq_iff_eq, hab, ↓reduceIte]
    exact hget

/-- A retry timer of the chunk that remains after one is taken away was there before. -/
theorem retryArmedP_of_rest {w : World} {i : Nat} {k : Chunk}
    (h : retryArmedP { w with timers := w.timers.eraseIdx i } k = true) : retryArmedP w k = true := by
  unfold retryArmedP at h ⊢
  rw [List.any_eq_true] at h ⊢
  obtain ⟨x, hx, hp⟩ := h
  exact ⟨x, List.mem_of_mem_eraseIdx hx, hp⟩

/-- `retry_offer(a)` where the chunk is held: the fired timer is gone, and nothing else changes. -/
theorem retryFire_held {i : Nat} {a : Key} {ctx : Ctx} {ans : Answers} {w : World}
    (hheld : heldP w.st a.chunk = true) :
    retryFire i a ctx ans w = { w with timers := w.timers.eraseIdx i } := by
  unfold retryFire SpecTwin.retryOffer
  rw [run_bind_eq _ _ (run_enter _), run_bind_eq _ _ run_read, run_bind_eq _ _ (run_held _)]
  rw [run_ite, ite_eq_left (show heldP w.st a.chunk = true from hheld), run_bind_eq _ _ (run_branch _), run_pure]

/-- A retry timer of another chunk's key, taken away, leaves the tracked chunk's timers as they were. -/
theorem retryArmedP_eraseIdx_other {w : World} {i : Nat} {d : Float} {a : Key} {k : Chunk}
    (h : w.timers[i]? = some (d, Timer.retryOffer a)) (hk : a.chunk ≠ k) :
    retryArmedP { w with timers := w.timers.eraseIdx i } k = retryArmedP w k := by
  unfold retryArmedP
  exact any_eraseIdx_of_false _ _ i _ h (by simp [hk])

/-- The asking path for a key of another chunk leaves the tracked chunk's part of the world as it was: its
windows, its retry timers, its queued asks and its asks' count. -/
theorem askedWorld_other_chunk {i : Nat} {d : Float} {a : Key} {ctx : Ctx} {ans : Answers} {w : World} {k : Chunk}
    (h : w.timers[i]? = some (d, Timer.retryOffer a)) (hk : a.chunk ≠ k) :
    windowP ctx (askedWorld i a ctx ans w).st k = windowP ctx w.st k ∧
    retryArmedP (askedWorld i a ctx ans w) k = retryArmedP w k ∧
    (∀ q, queuedP (askedWorld i a ctx ans w).st q k = queuedP w.st q k) ∧
    (∀ q, (askedWorld i a ctx ans w).made k q = w.made k q) := by
  refine ⟨?_, ?_, ?_, ?_⟩
  · unfold windowP
    rw [askedWorld_askedAt]
    exact any_toList_insert_of_false _ _ _ _ (by simp [hk])
  · have h2 := retryArmedP_eraseIdx_other h hk
    unfold retryArmedP at h2 ⊢
    rw [askedWorld_timers, List.any_append, h2]
    simp [hk]
  · intro q
    unfold askedWorld; dsimp only
    split
    · next hadm =>
      by_cases hq : q = pickP ctx ans w.st a
      · subst hq
        have hkb : (a.chunk == k) = false := by simp [hk]
        simp [World.push, queuedP, entryOf, QEntry.asks, hkb, Std.HashMap.getD_eq_getD_getElem?]
      · have hq' : ¬ pickP ctx ans w.st a = q := fun e => hq e.symm
        simp [World.push, queuedP, Std.HashMap.getD_insert, hq']
    · rfl
  · intro q
    unfold askedWorld; dsimp only
    split
    · simp [World.push, entryOf, QEntry.asks, hk]
    · rfl

/-! ## Fixtures

Worlds the statements are applied to, so that their hypotheses are shown to hold together. They are not worlds a
run reaches: the group `"g"` is not a key the toy makes; two retry timers of one key are armed with nothing said
of when; and a peer asked several times has no promise or park to show for it. The theorems hold for any keys and
worlds; the fixtures show only that the hypotheses can hold at once. -/

/-- The tracked chunk's one key: an ask by index. -/
def kA : Key := .want "g" 0

/-- The document's constants (§8.3: IWANT_WINDOW 200 ms, RETRY_SLACK 5 ms, PROMISE 400 ms, PARK_TTL 30 s) and
`now` = 1.0. The constants are written by name, the others at the twin's defaults, so that a constant a later
section adds does not break the fixture. The fixture so follows the twin's defaults: a default changed there
changes this value with no printed difference, and only the check's fingerprint shows it. -/
def ctx1 : Ctx :=
  { c := { IWANT_WINDOW := 0.2, RETRY_SLACK := 0.005, PROMISE := 0.4, PARK_TTL := 30.0, MAX_PLAIN_CHUNKS := 8192 }
    now := 1.0 }

/-- Three peers connected; the queue takes what it is given. -/
def ans1 : Answers := { connectedTopicPeers := [1, 2, 3, 4] }

/-- The same, with a queue that takes nothing (and answers so). -/
def ansFull : Answers := { ans1 with admits := fun _ _ _ => false, enqueue := fun _ _ _ => false }

/-- **Three announcers** of the chunk, and two retry timers armed:
- peer 1, on the offer list, asked at 0.1 and parked since;
- peer 2, on the offer list, asked at 0.5, its ask (the first to it) still queued;
- peer 3, which offered the chunk beyond the list (`offered[3]["g"]`), not asked yet.

The key's window (asked at 0.5) is closed at `now` = 1.0. -/
def threeAnn : World :=
  { st := {
      offers := (∅ : Std.HashMap Key (List Peer)).insert kA [1, 2]
      offered := (∅ : Std.HashMap Peer (Std.HashMap Group Bits)).insert 3 ((∅ : Std.HashMap Group Bits).insert "g" 1)
      park := (∅ : Std.HashMap Peer (Std.HashMap Group Float)).insert 1 ((∅ : Std.HashMap Group Float).insert "g" 30.6)
      askedAt := (∅ : Std.HashMap Key Float).insert kA 0.5
      tried := (∅ : Std.HashMap Key (Std.HashMap Peer Float)).insert kA
        (((∅ : Std.HashMap Peer Float).insert 1 0.1).insert 2 0.5)
      queue := (∅ : Std.HashMap Peer (Std.HashMap Lane (List QEntry))).insert 2
        ((∅ : Std.HashMap Lane (List QEntry)).insert .normal [entryOf (.iwant [kA])]) }
    timers := [(0.205, .retryOffer kA), (0.205, .retryOffer kA)]
    made := fun k q => if k = kA.chunk ∧ (q = 1 ∨ q = 2) then 1 else 0 }

/-- **A fourth ask.** As `threeAnn`, with peer 3 on the list and asked three times (last at 0.3), and peer 4,
beyond the list, asked five times (last at 0.2): neither is outstanding, so the pick is the least recently tried,
peer 4, and its ask is a sixth. With `tried[kA][4]` at 0.4 the pick is peer 3, and its ask the fourth. -/
def laterAsk (t4 : Float) : World :=
  { st := { threeAnn.st with
      offers := (∅ : Std.HashMap Key (List Peer)).insert kA [1, 2, 3]
      offered := (∅ : Std.HashMap Peer (Std.HashMap Group Bits)).insert 4 ((∅ : Std.HashMap Group Bits).insert "g" 1)
      tried := (∅ : Std.HashMap Key (Std.HashMap Peer Float)).insert kA
        (((((∅ : Std.HashMap Peer Float).insert 1 0.1).insert 2 0.5).insert 3 0.3).insert 4 t4) }
    timers := [(0.205, .retryOffer kA)]
    made := fun k q => if k = kA.chunk then (if q = 1 ∨ q = 2 then 1 else if q = 3 then 3 else if q = 4 then 5 else 0) else 0 }

/-- What a statement's hypotheses compute to on a fixture: the chunk not held, the key's window closed, an announcer
free, the pick, and an ask made now in its window. -/
abbrev FixtureOk (ans : Answers) (w : World) (pick : Peer) : Prop :=
  heldP w.st kA.chunk = false ∧
  decide (ctx1.now - (w.st.askedAt.get? kA).getD negInf < ctx1.c.IWANT_WINDOW) = false ∧
  freeP ctx1 ans w.st kA ≠ [] ∧ pickP ctx1 ans w.st kA = pick ∧
  ctx1.now - ctx1.now < ctx1.c.IWANT_WINDOW

/-! One computed fact per world and answers (`native_decide`: the float comparisons are computed, and the
check's audit names the compiler's axioms one by one). -/

theorem threeAnn_facts : FixtureOk ans1 threeAnn 3 := by native_decide
theorem threeAnnFull_facts : FixtureOk ansFull threeAnn 3 := by native_decide
theorem laterAsk_fourth_facts : FixtureOk ans1 (laterAsk 0.4) 3 := by native_decide
theorem laterAsk_later_facts : FixtureOk ans1 (laterAsk 0.2) 4 := by native_decide

/-- The fixtures' `stop_pull` is empty: the chunk's group is not stopped. -/
theorem threeAnn_stop : stopP threeAnn.st kA.group = false := by simp [stopP, threeAnn]
theorem laterAsk_stop (t4 : Float) : stopP (laterAsk t4).st kA.group = false := by
  simp [stopP, laterAsk, threeAnn]

/-- **Held, and the last timer:** as `threeAnn`, with the chunk held meanwhile (`mine["g"]` has index 0) and one
retry timer armed. The key's window (asked at 0.5) is closed at `now` = 1.0. -/
def heldLast : World :=
  { threeAnn with
    st := { threeAnn.st with mine := (∅ : Std.HashMap Group Bits).insert "g" 1 }
    timers := [(0.205, .retryOffer kA)] }

/-- **The step, computed.** The twin's own `retry_offer`, run under the interpreter on the three announcers'
world, with no theorem of this file between: where the queue takes the ask, an IWANT of the chunk is queued to
peer 3, its count is one, two timers are armed (by their count: which two is `askedWorld_timers`'s to say),
nothing raised, and the key's window is open; where the queue takes nothing, no ask is queued to peer 3 and none is counted. A twin whose
`retry_offer` does otherwise on this world fails here, with the answers as they are. -/
theorem threeAnn_after_facts :
    queuedP (retryFire 0 kA ctx1 ans1 threeAnn).st 3 kA.chunk = true ∧
    (retryFire 0 kA ctx1 ans1 threeAnn).made kA.chunk 3 = 1 ∧
    (retryFire 0 kA ctx1 ans1 threeAnn).timers.length = 2 ∧
    (retryFire 0 kA ctx1 ans1 threeAnn).crashed = [] ∧
    windowP ctx1 (retryFire 0 kA ctx1 ans1 threeAnn).st kA.chunk = true ∧
    queuedP (retryFire 0 kA ctx1 ansFull threeAnn).st 3 kA.chunk = false ∧
    (retryFire 0 kA ctx1 ansFull threeAnn).made kA.chunk 3 = 0 := by native_decide

theorem heldLast_facts :
    heldP heldLast.st kA.chunk = true ∧
    retryArmedP { heldLast with timers := heldLast.timers.eraseIdx 0 } kA.chunk = false ∧
    windowP ctx1 heldLast.st kA.chunk = false := by native_decide

end Refine.Ask
