import SpecTwin.Sec61

/-! # The twin's side: what two steps of the twin do to its state

This file imports the twin only, not Veil: the twin's steps are run by an interpreter of `Node61` that answers
from fixed functions and never touches the twin's state, and the state they leave is computed here. It answers
`writing` (§7.1, §7.3), the question of the window's functions, from a field of the answers too; the asking path
(`promise_due`, `retry_offer`) never asks it.

What this interpreter leaves out: it keeps no timers and enqueues nothing (`after` does nothing, `enqueue`
answers from a fixed function and leaves the twin's `queue` as it was: the queue is the twin's own table, which
only a call on the tape writes), and where the Python would raise it goes on with a default value (`crash`),
which the replay's interpreter does not. Neither matters for `promise_due`, which arms no timer, queues nothing
and cannot raise; both do for `retry_offer` past its first lines. -/

namespace Refine
open SpecTwin

-- The twin's keys compare lawfully (their `BEq` is the derived one). The map lemmas need it.
deriving instance ReflBEq, LawfulBEq for SpecTwin.Key

/-- What the rest of the node answers during one handler: the same at each ask (stable answers). -/
structure Answers where
  expired : Group → Bool := fun _ => false
  connectedTopicPeers : List Peer := []
  ownOrder : List Peer → Key → List Peer := fun xs _ => xs
  listed : Peer → Nat := fun _ => 0
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

/-- The interpreter: the answers are read, the twin's state lies below and no answer touches it. -/
abbrev I := ReaderT Answers (StateM State)

instance : Node61 I where
  expired g := return (← read).expired g
  connectedTopicPeers := return (← read).connectedTopicPeers
  ownOrder xs a := return (← read).ownOrder xs a
  listed p := return (← read).listed p
  enqueue p x u := return (← read).enqueue p x u
  after _ _ := pure ()
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
  crash _ := pure default
  branch _ := pure ()
  enter _ := pure ()

/-- The twin's tables under this interpreter: its state, and no note of what is touched. -/
instance instTablesI : Tables I := Tables.ofState fun _ => pure ()

/-- The state a call of the twin leaves, run from `st` with the answers `ans`. -/
def after {α : Type} (x : M I α) (ctx : Ctx) (ans : Answers) (st : State) : State :=
  (((x.run ctx).run ans).run st).2

/-- The twin's `promise_due(a, p, at)` as a step: the state it leaves. Named here, so that a file that imports
Veil too never elaborates the twin's monad (Veil's instances would answer for its state). -/
def promiseDueStep (a : Key) (p : Peer) (at_ : Float) (ctx : Ctx) (ans : Answers) (st : State) : State :=
  after (SpecTwin.promiseDue (m := I) a p at_) ctx ans st

/-- The twin's `retry_offer(a)` as a step. -/
def retryOfferStep (a : Key) (ctx : Ctx) (ans : Answers) (st : State) : State :=
  after (SpecTwin.retryOffer (m := I) a) ctx ans st

/-- `promise_due(a, p, at)`, where the promise is the one that fell due: the twin erases it and parks `p` for the
group. -/
theorem promiseDue_parks {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = false) :
    promiseDueStep a p at_ ctx ans st =
      { st with
        promises := st.promises.erase (a, p)
        park := st.park.insert p ((st.park.getD p {}).insert a.group (ctx.now + ctx.c.PARK_TTL)) } := by
  have h1 : st.promises[(a, p)]? = some t := by simpa using hget
  simp [promiseDueStep, after, SpecTwin.promiseDue, ReaderT.run, StateT.run, bind, ReaderT.bind, StateT.bind,
    read, readThe, MonadReaderOf.read, ReaderT.read, get, getThe, MonadStateOf.get, StateT.get, liftM, monadLift,
    MonadLift.monadLift, MonadLiftT.monadLift, pure, ReaderT.pure, StateT.pure, Tables.promise?, Tables.erasePromise, Tables.setPark, modify, modifyGet,
    MonadStateOf.modifyGet, StateT.modifyGet, Node61.branch, Node61.enter, h1, hdue]

/-- `promise_due(a, p, at)` where no promise of `a` to `p` is open: the twin changes nothing. -/
theorem promiseDue_gone {a : Key} {p : Peer} {at_ : Float} {ctx : Ctx} {ans : Answers} {st : State}
    (hget : st.promises.get? (a, p) = none) :
    promiseDueStep a p at_ ctx ans st = st := by
  have h1 : st.promises[(a, p)]? = none := by simpa using hget
  simp [promiseDueStep, after, SpecTwin.promiseDue, ReaderT.run, StateT.run, bind, ReaderT.bind, StateT.bind,
    read, readThe, MonadReaderOf.read, ReaderT.read, get, getThe, MonadStateOf.get, StateT.get, liftM, monadLift,
    MonadLift.monadLift, MonadLiftT.monadLift, pure, ReaderT.pure, StateT.pure, Tables.promise?, Node61.branch, Node61.enter, h1]

/-- `promise_due(a, p, at)` where the open promise is another ask's: the twin changes nothing. -/
theorem promiseDue_other {a : Key} {p : Peer} {at_ t : Float} {ctx : Ctx} {ans : Answers} {st : State}
    (hget : st.promises.get? (a, p) = some t) (hdue : (t != at_) = true) :
    promiseDueStep a p at_ ctx ans st = st := by
  have h1 : st.promises[(a, p)]? = some t := by simpa using hget
  simp [promiseDueStep, after, SpecTwin.promiseDue, ReaderT.run, StateT.run, bind, ReaderT.bind, StateT.bind,
    read, readThe, MonadReaderOf.read, ReaderT.read, get, getThe, MonadStateOf.get, StateT.get, liftM, monadLift,
    MonadLift.monadLift, MonadLiftT.monadLift, pure, ReaderT.pure, StateT.pure, Tables.promise?, Node61.branch, Node61.enter, h1, hdue]

/-- `retry_offer(a)` where the chunk is held: the twin returns at its first line and changes nothing. `held(a)` is
the twin's own code over its table `mine` (`Readers.lean`), not an answer: the chunk is held when its index is in
the state's `mine[group(a)]`. -/
theorem retryOffer_held {a : Key} {ctx : Ctx} {ans : Answers} {st : State}
    (hheld : (st.mine.getD a.group 0).has a.index = true) :
    retryOfferStep a ctx ans st = st := by
  simp [retryOfferStep, after, SpecTwin.retryOffer, SpecTwin.held, ReaderT.run, StateT.run, bind, ReaderT.bind,
    StateT.bind, read, readThe, MonadReaderOf.read, ReaderT.read, get, getThe, MonadStateOf.get, StateT.get, liftM,
    monadLift, MonadLift.monadLift, MonadLiftT.monadLift, pure, ReaderT.pure, StateT.pure, Tables.mineBits,
    Node61.branch, Node61.enter, hheld]

/-- The twin's `outstanding(q, a)` as a question: its answer. -/
def outstandingAns (q : Peer) (a : Key) (ctx : Ctx) (ans : Answers) (st : State) : Bool :=
  ((((SpecTwin.outstanding (m := I) q a).run ctx).run ans).run st).1

/-- `outstanding(q, a)` is: some open promise to `q` names the chunk, or an ask queued to `q` does, in the twin's
own `queue[q].normal`. -/
theorem outstanding_eq {q : Peer} {a : Key} {ctx : Ctx} {ans : Answers} {st : State} :
    outstandingAns q a ctx ans st =
      (st.promises.toList.any (fun ((b, r), _) => r == q && b.chunk == a.chunk) ||
        (((st.queue.getD q {}).get? .normal).getD []).any (fun e => e.asks.any (fun b => b.chunk == a.chunk))) := by
  cases h : st.promises.toList.any (fun ((b, r), _) => r == q && b.chunk == a.chunk) <;>
    simp [outstandingAns, SpecTwin.outstanding, ReaderT.run, StateT.run, bind, ReaderT.bind, StateT.bind,
      get, getThe, MonadStateOf.get, StateT.get, liftM, monadLift, MonadLift.monadLift, MonadLiftT.monadLift, pure,
      ReaderT.pure, StateT.pure, Tables.allPromises, Tables.lane?, Node61.branch, Node61.enter, h]

/-- The twin's `parked(p, a)` as a question: its answer. -/
def parkedAns (p : Peer) (a : Key) (ctx : Ctx) (ans : Answers) (st : State) : Bool :=
  ((((SpecTwin.parked (m := I) p a).run ctx).run ans).run st).1

/-- `parked(p, a)` is: `now` is before `park[p][group(a)]`, a missing park reading as minus infinity. -/
theorem parked_eq {p : Peer} {a : Key} {ctx : Ctx} {ans : Answers} {st : State} :
    parkedAns p a ctx ans st = decide (ctx.now < ((st.park.getD p {}).getD a.group negInf)) := by
  simp [parkedAns, SpecTwin.parked, ReaderT.run, StateT.run, bind, ReaderT.bind, StateT.bind,
    read, readThe, MonadReaderOf.read, ReaderT.read, get, getThe, MonadStateOf.get, StateT.get, liftM, monadLift,
    MonadLift.monadLift, MonadLiftT.monadLift, pure, ReaderT.pure, StateT.pure, Tables.parkUntil?, Node61.enter, Std.HashMap.getD_eq_getD_getElem?]

end Refine
