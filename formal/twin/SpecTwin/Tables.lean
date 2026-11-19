import SpecTwin.State

/-! # The twin's state, read and written entry by entry (generated)

This file is written whole by `tools/gen/gen.py` from `gen/schema.py`, one entry there per
table, and `gen.py --check` compares it byte for byte. Do not edit it: change the schema, or the generator.

§6.1's code reaches its state through this interface and in no other way: `Sec61.lean` is written over a monad
that has `Tables` and `Node61`, and no state of its own. One operation per table and kind of access: read an
entry, write it, or read a level as a whole.

`Tables.ofState` is the interface over the twin's `State`: each operation does its work on the state and notes
what it touched (`Touch`): the entry read or written, or the level read as a whole with the entries it held.
The replay collects the notes and compares them with what the Python read and wrote
(`Replay.lean`); a proof's interpreter notes nothing.

The notes are this file's word for what its operations do. The replay does not take that word alone: it also
compares the twin's whole state after a call with the record's (`Replay.lean`, `wholeState`), and the mutants
of this file (`mutants3.py`, the `tables-` ones) show what that comparison sees in each kind of record. -/

namespace SpecTwin

/-- §6.1's own state (§8.1), as its code uses it. A missing entry reads as empty, and reading allocates nothing. -/
class Tables (m : Type → Type) where
  /-- `asked_at.get(a)` -/
  askedAt? : Key → m (Option Float)
  /-- `asked_at[a] = t` -/
  setAskedAt : Key → Float → m Unit
  /-- `asked_at.pop(a, None)` -/
  eraseAskedAt : Key → m Unit
  /-- `tried[a].get(p)` -/
  tried? : Key → Peer → m (Option Float)
  /-- `tried[a][p] = t` -/
  setTried : Key → Peer → Float → m Unit
  /-- `tried[a].pop(p)` -/
  eraseTried : Key → Peer → m Unit
  /-- `offers[a]` -/
  offersOf : Key → m (List Peer)
  /-- `offers[a] = o` -/
  setOffers : Key → List Peer → m Unit
  /-- `offers.pop(a, None)` -/
  eraseOffers : Key → m Unit
  /-- `promises.get((a, p))` -/
  promise? : Key → Peer → m (Option Float)
  /-- `promises[(a, p)] = t` -/
  setPromise : Key → Peer → Float → m Unit
  /-- `del promises[(a, p)]` -/
  erasePromise : Key → Peer → m Unit
  /-- every promise: `for (b, r) in promises` -/
  allPromises : m (List ((Key × Peer) × Float))
  /-- `offered[q][g]` -/
  offeredBits : Peer → Group → m Bits
  /-- `offered[q][g] = b` -/
  setOffered : Peer → Group → Bits → m Unit
  /-- `park[p].get(g)` -/
  parkUntil? : Peer → Group → m (Option Float)
  /-- `park[p][g] = t` -/
  setPark : Peer → Group → Float → m Unit
  /-- `park[p].pop(g, None)` -/
  erasePark : Peer → Group → m Unit
  /-- `asked_parked[k]` -/
  askedParkedOf : Chunk → m (Std.HashSet Peer)
  /-- `asked_parked[k] = s` -/
  setAskedParked : Chunk → Std.HashSet Peer → m Unit
  /-- `asked_parked.pop(k, None)` -/
  eraseAskedParked : Chunk → m Unit
  /-- `k in last_resort_armed` -/
  lrArmed? : Chunk → m Bool
  /-- `last_resort_armed.add(k)`, or `.discard(k)` -/
  setLrArmed : Chunk → Bool → m Unit
  /-- `ihave_frames[p]` -/
  ihaveFrames : Peer → m Nat
  /-- `ihave_frames[p] = n` -/
  setIhaveFrames : Peer → Nat → m Unit
  /-- `ihave_frames.clear()`: a write of every entry there -/
  clearIhaveFrames : m Unit
  /-- `ihave_asked[p]` -/
  ihaveAsked : Peer → m Nat
  /-- `ihave_asked[p] = n` -/
  setIhaveAsked : Peer → Nat → m Unit
  /-- `ihave_asked.clear()`: a write of every entry there -/
  clearIhaveAsked : m Unit
  /-- `held_back.get(k)` -/
  heldBack? : Chunk → m (Option Key)
  /-- `held_back[k] = a` -/
  setHeldBack : Chunk → Key → m Unit
  /-- `held_back.clear()`: a write of every entry there -/
  clearHeldBack : m Unit
  /-- every `held_back`: `held_back.values()` -/
  allHeldBack : m (List (Chunk × Key))
  /-- `received[g]` -/
  receivedBits : Group → m Bits
  /-- `received[g] = b` -/
  setReceived : Group → Bits → m Unit
  /-- `mine[g]` -/
  mineBits : Group → m Bits
  /-- `mine[g] = b` -/
  setMine : Group → Bits → m Unit
  /-- `state[g]` -/
  state? : Group → m (Option GroupState)
  /-- `state[g] = st` -/
  setState : Group → GroupState → m Unit
  /-- `tied[r][p].get(g)` -/
  tied? : Root → Peer → Group → m (Option Bits)
  /-- `tied[r][p][g] = b` -/
  setTied : Root → Peer → Group → Bits → m Unit
  /-- `tied[r][p].pop(g)` -/
  eraseTied : Root → Peer → Group → m Unit
  /-- `r in tied`: the row there -/
  tiedRow? : Root → m Bool
  /-- `tied.pop(r, ...)`: the row and all under it -/
  eraseTiedRow : Root → m Unit
  /-- `p in tied[r]`: the row there -/
  tiedPeerRow? : Root → Peer → m Bool
  /-- `tied[r].pop(p, ...)`: the row and all under it -/
  eraseTiedPeerRow : Root → Peer → m Unit
  /-- every `tied` -/
  allTiedAll : m (List (Root × List (Peer × List (Group × Bits))))
  /-- every `tied[r]` -/
  allTiedRoot : Root → m (List (Peer × List (Group × Bits)))
  /-- every `tied[r][p]` -/
  allTiedPeer : Root → Peer → m (List (Group × Bits))
  /-- `queue[p].normal`, or `queue[p].urgent` -/
  lane? : Peer → Lane → m (Option (List QEntry))
  /-- a lane after the writer's pop -/
  setLane : Peer → Lane → List QEntry → m Unit
  /-- a lane assigned empty to a queue that is not there: it stays missing, no row made -/
  eraseLane : Peer → Lane → m Unit
  /-- every `queue[p]`: `list(queue)` -/
  allQueue : m (List (Peer × List (Lane × List QEntry)))
  /-- `pending[root]` -/
  pendingOf : Root → m (List (Peer × ChunkF))
  /-- `pending[root] = w` -/
  setPending : Root → List (Peer × ChunkF) → m Unit
  /-- `pending.pop(root, None)`, `del pending[root]` -/
  erasePending : Root → m Unit
  /-- every `pending`: `list(pending)` -/
  allPending : m (List (Root × List (Peer × ChunkF)))
  /-- `mid in pending_ids` -/
  pendingId? : Key → m Bool
  /-- `pending_ids.add(mid)`, or `.discard(mid)` -/
  setPendingId : Key → Bool → m Unit
  /-- `tie_slot.get((root, p))` -/
  tieSlot? : Root → Peer → m (Option Nat)
  /-- `tie_slot[(root, p)] = s` -/
  setTieSlot : Root → Peer → Nat → m Unit
  /-- `tie_slot.pop((root, p), None)` -/
  eraseTieSlot : Root → Peer → m Unit
  /-- every `tie_slot`: `list(tie_slot.items())` -/
  allTieSlot : m (List ((Root × Peer) × Nat))
  /-- `owed[p].get(g)` -/
  owed? : Peer → Group → m (Option Bits)
  /-- `owed[p][g] = b` -/
  setOwed : Peer → Group → Bits → m Unit
  /-- `owed[p].pop(g)` -/
  eraseOwed : Peer → Group → m Unit
  /-- `p in owed`: the row there -/
  owedRow? : Peer → m Bool
  /-- `owed.pop(p)`: the row and all under it -/
  eraseOwedRow : Peer → m Unit
  /-- every `owed[p]`: `if owed[p]`, `list(owed[p])` -/
  allOwed : Peer → m (List (Group × Bits))
  /-- `owed_answers[p][g]` -/
  owedAnswerBits : Peer → Group → m Bits
  /-- `owed_answers[p][g] = b` -/
  setOwedAnswers : Peer → Group → Bits → m Unit
  /-- every `owed_answers[p]`: `if owed_answers[p]` -/
  allOwedAnswers : Peer → m (List (Group × Bits))
  /-- `sent_to[p][g]` -/
  sentToBits : Peer → Group → m Bits
  /-- `sent_to[p][g] = b` -/
  setSentTo : Peer → Group → Bits → m Unit
  /-- `slot_held[p]` -/
  slotHeld? : Peer → m Bool
  /-- `slot_held[p] = True`, or `= False` -/
  setSlotHeld : Peer → Bool → m Unit
  /-- `pace_queue`, the jobs in order -/
  paceJobs : PaceKey → m (List Job)
  /-- `pace_queue` after an append or a pop -/
  setPaceJobs : PaceKey → List Job → m Unit
  /-- `stop_pull[g]` -/
  stopPull : Group → m Bool
  /-- `stop_pull[g] = True` -/
  setStopPull : Group → Bool → m Unit
  /-- `peer_has[p][g]`: the entry, or none where p sent no HAVE for g -/
  peerHasEntry? : Peer → Group → m (Option HaveEntry)
  /-- `peer_has[p][g]`'s bits and ttl set -/
  setPeerHas : Peer → Group → HaveEntry → m Unit
  /-- `holders[g][i]` -/
  holdersOf : Group → Nat → m (Std.HashSet Peer)
  /-- `holders[g][i] = s` -/
  setHolders : Group → Nat → Std.HashSet Peer → m Unit
  /-- `serve_count[p][mid]` -/
  serveCount : Peer → Key → m Nat
  /-- `serve_count[p][mid] = n` -/
  setServeCount : Peer → Key → Nat → m Unit
  /-- `origin[g]`, as `g in origin` or `origin[g]`: the bitmap, or none where g is not there -/
  origin : Group → m (Option Bits)
  /-- `origin[g] = b`, `origin[g].set(i)` -/
  setOrigin : Group → Bits → m Unit
  /-- `planned[g].get(i)`: the peers chosen for chunk i, or none where i has no entry -/
  plannedTargets? : Group → Nat → m (Option (Std.HashSet Peer))
  /-- `planned[g][i] = set(targets)` -/
  setPlanned : Group → Nat → Std.HashSet Peer → m Unit
  /-- `g in planned`: the row there -/
  planned : Group → m Bool
  /-- the row and all under it -/
  erasePlannedRow : Group → m Unit
  /-- `pushed[p][g]`: the entry, or none where nothing was pushed p of g -/
  pushedEntry? : Peer → Group → m (Option PushEntry)
  /-- `pushed[p][g]`'s bits, clock and ttl set -/
  setPushed : Peer → Group → PushEntry → m Unit
  /-- `desc[g]`, as `g in desc` or `desc[g]`: the group's descriptor, or none where it is not there -/
  desc : Group → m (Option Descriptor)
  /-- `desc[g] = d` -/
  setDesc : Group → Descriptor → m Unit
  /-- `in_flight`, the slots in use -/
  inFlight : CountKey → m Int
  /-- `in_flight += 1`, `in_flight -= 1` -/
  setInFlight : CountKey → Int → m Unit
  /-- `waiters`, the peers in line, in order -/
  waitersLine : LineKey → m (List Peer)
  /-- `waiters` after a popleft, an append or a remove -/
  setWaitersLine : LineKey → List Peer → m Unit
  /-- `sent.get(key)`, `key in sent` -/
  sentAt? : SendKey → m (Option Float)
  /-- `sent[key] = now` -/
  setSentAt : SendKey → Float → m Unit
  /-- `del sent[key]`, `sent.pop(key)` -/
  eraseSentAt : SendKey → m Unit
  /-- `unwanted[p]`: the ids p said it does not want -/
  unwantedOf : Peer → m (Std.HashSet Hex)
  /-- `unwanted[p].add(h)` -/
  setUnwanted : Peer → Std.HashSet Hex → m Unit
  -- The levels §6.1's code never reads as a whole. They are here so that a twin that does, a mutant, can be
  -- written, and is then seen to.
  /-- every `asked_at` -/
  allAskedAt : m (List (Key × Float))
  /-- every `tried`, under every key -/
  allTriedAll : m (List (Key × List (Peer × Float)))
  /-- every `tried[a]` -/
  allTried : Key → m (List (Peer × Float))
  /-- every offer list -/
  allOffers : m (List (Key × List Peer))
  /-- every `offered`, of every peer -/
  allOfferedAll : m (List (Peer × List (Group × Bits)))
  /-- every `offered[q]` -/
  allOffered : Peer → m (List (Group × Bits))
  /-- every `park`, of every peer -/
  allParkAll : m (List (Peer × List (Group × Float)))
  /-- every `park[p]` -/
  allPark : Peer → m (List (Group × Float))
  /-- every `asked_parked` -/
  allAskedParked : m (List (Chunk × Std.HashSet Peer))
  /-- every member of `last_resort_armed` -/
  allLrArmed : m (List Chunk)
  /-- every `ihave_frames` -/
  allIhaveFrames : m (List (Peer × Nat))
  /-- every `ihave_asked` -/
  allIhaveAsked : m (List (Peer × Nat))
  /-- every `received` -/
  allReceived : m (List (Group × Bits))
  /-- every `mine` -/
  allMine : m (List (Group × Bits))
  /-- every `state` -/
  allState : m (List (Group × GroupState))
  /-- every member of `pending_ids` -/
  allPendingIds : m (List Key)
  /-- every `owed` -/
  allOwedAll : m (List (Peer × List (Group × Bits)))
  /-- every `owed_answers` -/
  allOwedAnswersAll : m (List (Peer × List (Group × Bits)))
  /-- every `sent_to` -/
  allSentToAll : m (List (Peer × List (Group × Bits)))
  /-- every peer whose writer holds a slot -/
  allSlotHeld : m (List Peer)
  /-- the pace queue's one entry -/
  allPaceQueue : m (List (PaceKey × List Job))
  /-- every group stopped -/
  allStopPull : m (List Group)
  /-- every `peer_has` -/
  allPeerHas : m (List (Peer × List (Group × HaveEntry)))
  /-- every `holders` -/
  allHolders : m (List (Group × List (Nat × Std.HashSet Peer)))
  /-- every `serve_count` -/
  allServeCount : m (List (Peer × List (Key × Nat)))
  /-- every `origin` -/
  allOrigin : m (List (Group × Bits))
  /-- every `planned` -/
  allPlannedAll : m (List (Group × List (Nat × Std.HashSet Peer)))
  /-- every `pushed` -/
  allPushed : m (List (Peer × List (Group × PushEntry)))
  /-- every `desc` -/
  allDesc : m (List (Group × Descriptor))
  /-- the window's count's one entry -/
  allInFlight : m (List (CountKey × Int))
  /-- the line's one entry -/
  allWaiters : m (List (LineKey × List Peer))
  /-- every `sent` -/
  allSent : m (List (SendKey × Float))
  /-- every `unwanted` -/
  allUnwanted : m (List (Peer × Std.HashSet Hex))

namespace Tables

/-- The interface over the twin's `State`, with a note of each access. -/
@[instance_reducible]
def ofState {m : Type → Type} [Monad m] [MonadStateOf State m] (note : Touch → m Unit) : Tables m where
  askedAt? a := do note (.read (.askedAt a)); return (← get).askedAt.get? a
  setAskedAt a t := do note (.write (.askedAt a)); modify fun s => { s with askedAt := s.askedAt.insert a t }
  eraseAskedAt a := do note (.write (.askedAt a)); modify fun s => { s with askedAt := s.askedAt.erase a }
  tried? a p := do note (.read (.tried a p)); return ((← get).tried.getD a {}).get? p
  setTried a p t := do
    note (.write (.tried a p))
    modify fun s => { s with tried := s.tried.insert a ((s.tried.getD a {}).insert p t) }
  eraseTried a p := do
    note (.write (.tried a p))
    modify fun s => { s with tried := s.tried.insert a ((s.tried.getD a {}).erase p) }
  offersOf a := do note (.read (.offers a)); return (← get).offers.getD a []
  setOffers a o := do note (.write (.offers a)); modify fun s => { s with offers := s.offers.insert a o }
  eraseOffers a := do note (.write (.offers a)); modify fun s => { s with offers := s.offers.erase a }
  promise? a p := do note (.read (.promise a p)); return (← get).promises.get? (a, p)
  setPromise a p t := do note (.write (.promise a p)); modify fun s => { s with promises := s.promises.insert (a, p) t }
  erasePromise a p := do note (.write (.promise a p)); modify fun s => { s with promises := s.promises.erase (a, p) }
  allPromises := do
    let l := (← get).promises.toList
    note (.scan .promises (l.map fun ((a, p), _) => .promise a p))
    return l
  offeredBits q g := do note (.read (.offered q g)); return ((← get).offered.getD q {}).getD g 0
  setOffered q g b := do
    note (.write (.offered q g))
    modify fun s => { s with offered := s.offered.insert q ((s.offered.getD q {}).insert g b) }
  parkUntil? p g := do note (.read (.park p g)); return ((← get).park.getD p {}).get? g
  setPark p g t := do
    note (.write (.park p g))
    modify fun s => { s with park := s.park.insert p ((s.park.getD p {}).insert g t) }
  erasePark p g := do
    note (.write (.park p g))
    modify fun s => { s with park := s.park.insert p ((s.park.getD p {}).erase g) }
  askedParkedOf k := do note (.read (.askedParked k)); return (← get).askedParked.getD k {}
  setAskedParked k ps := do
    note (.write (.askedParked k))
    modify fun s => { s with askedParked := s.askedParked.insert k ps }
  eraseAskedParked k := do
    note (.write (.askedParked k))
    modify fun s => { s with askedParked := s.askedParked.erase k }
  lrArmed? k := do note (.read (.lrArmed k)); return (← get).lastResortArmed.contains k
  setLrArmed k armed := do
    note (.write (.lrArmed k))
    modify fun s => { s with
      lastResortArmed := if armed then s.lastResortArmed.insert k else s.lastResortArmed.erase k }
  ihaveFrames p := do note (.read (.ihaveFrames p)); return (← get).ihaveFrames.getD p 0
  setIhaveFrames p n := do
    note (.write (.ihaveFrames p))
    modify fun s => { s with ihaveFrames := s.ihaveFrames.insert p n }
  clearIhaveFrames := do
    for (p, _) in (← get).ihaveFrames.toList do note (.write (.ihaveFrames p))
    modify fun s => { s with ihaveFrames := {} }
  ihaveAsked p := do note (.read (.ihaveAsked p)); return (← get).ihaveAsked.getD p 0
  setIhaveAsked p n := do
    note (.write (.ihaveAsked p))
    modify fun s => { s with ihaveAsked := s.ihaveAsked.insert p n }
  clearIhaveAsked := do
    for (p, _) in (← get).ihaveAsked.toList do note (.write (.ihaveAsked p))
    modify fun s => { s with ihaveAsked := {} }
  heldBack? k := do note (.read (.heldBack k)); return (← get).heldBack.get? k
  setHeldBack k a := do note (.write (.heldBack k)); modify fun s => { s with heldBack := s.heldBack.insert k a }
  clearHeldBack := do
    for (k, _) in (← get).heldBack.toList do note (.write (.heldBack k))
    modify fun s => { s with heldBack := {} }
  allHeldBack := do
    let l := (← get).heldBack.toList
    note (.scan .heldBack (l.map fun (k, _) => .heldBack k))
    return l
  receivedBits g := do note (.read (.received g)); return (← get).received.getD g 0
  setReceived g b := do note (.write (.received g)); modify fun s => { s with received := s.received.insert g b }
  mineBits g := do note (.read (.mine g)); return (← get).mine.getD g 0
  setMine g b := do note (.write (.mine g)); modify fun s => { s with mine := s.mine.insert g b }
  state? g := do note (.read (.state g)); return (← get).state.get? g
  setState g st := do note (.write (.state g)); modify fun s => { s with state := s.state.insert g st }
  tied? r p g := do note (.read (.tied r p g)); return (((← get).tied.getD r {}).getD p {}).get? g
  setTied r p g b := do
    let s ← get
    if !s.tied.contains r then note (.write (.tiedRow r))
    if !(s.tied.getD r {}).contains p then note (.write (.tiedPeerRow r p))
    note (.write (.tied r p g))
    modify fun s => { s with
      tied := s.tied.insert r ((s.tied.getD r {}).insert p (((s.tied.getD r {}).getD p {}).insert g b)) }
  eraseTied r p g := do
    note (.write (.tied r p g))
    modify fun s => { s with tied := s.tied.modify r (·.modify p (·.erase g)) }
  tiedRow? r := do note (.read (.tiedRow r)); return (← get).tied.contains r
  eraseTiedRow r := do
    let l := ((← get).tied.getD r {}).toList.map fun (p, m) => (p, m.toList)
    note (.write (.tiedRow r))
    for c in l.flatMap fun (p, gs) => .tiedPeerRow r p :: gs.map fun (g, _) => .tied r p g do note (.write c)
    modify fun s => { s with tied := s.tied.erase r }
  tiedPeerRow? r p := do note (.read (.tiedPeerRow r p)); return ((← get).tied.getD r {}).contains p
  eraseTiedPeerRow r p := do
    let l := (((← get).tied.getD r {}).getD p {}).toList
    note (.write (.tiedPeerRow r p))
    for c in l.map fun (g, _) => .tied r p g do note (.write c)
    modify fun s => { s with tied := s.tied.modify r (·.erase p) }
  allTiedAll := do
    let l := (← get).tied.toList.map fun (r, m) => (r, m.toList.map fun (p, m) => (p, m.toList))
    note (.scan .tiedAll (l.flatMap fun (r, ps) => .tiedRow r :: ps.flatMap fun (p, gs) => .tiedPeerRow r p :: gs.map fun (g, _) => .tied r p g))
    return l
  allTiedRoot r := do
    let l := ((← get).tied.getD r {}).toList.map fun (p, m) => (p, m.toList)
    note (.scan (.tiedRoot r) (l.flatMap fun (p, gs) => .tiedPeerRow r p :: gs.map fun (g, _) => .tied r p g))
    return l
  allTiedPeer r p := do
    let l := (((← get).tied.getD r {}).getD p {}).toList
    note (.scan (.tiedPeer r p) (l.map fun (g, _) => .tied r p g))
    return l
  lane? p l := do note (.read (.queue p l)); return ((← get).queue.getD p {}).get? l
  setLane p l es := do
    let s ← get
    if !s.queue.contains p then note (.write (.queueRow p))
    note (.write (.queue p l))
    modify fun s => { s with queue := s.queue.insert p ((s.queue.getD p {}).insert l es) }
  eraseLane p l := do note (.write (.queue p l)); modify fun s => { s with queue := s.queue.modify p (·.erase l) }
  allQueue := do
    let l := (← get).queue.toList.map fun (p, m) => (p, m.toList)
    note (.scan .queueAll (l.flatMap fun (p, ls) => .queueRow p :: ls.map fun (l, _) => .queue p l))
    return l
  pendingOf r := do note (.read (.pending r)); return (← get).pending.getD r []
  setPending r w := do note (.write (.pending r)); modify fun s => { s with pending := s.pending.insert r w }
  erasePending r := do note (.write (.pending r)); modify fun s => { s with pending := s.pending.erase r }
  allPending := do
    let l := (← get).pending.toList
    note (.scan .pending (l.map fun (r, _) => .pending r))
    return l
  pendingId? m := do note (.read (.pendingId m)); return (← get).pendingIds.contains m
  setPendingId m armed := do
    note (.write (.pendingId m))
    modify fun s => { s with
      pendingIds := if armed then s.pendingIds.insert m else s.pendingIds.erase m }
  tieSlot? r p := do note (.read (.tieSlot r p)); return (← get).tieSlot.get? (r, p)
  setTieSlot r p sl := do note (.write (.tieSlot r p)); modify fun s => { s with tieSlot := s.tieSlot.insert (r, p) sl }
  eraseTieSlot r p := do note (.write (.tieSlot r p)); modify fun s => { s with tieSlot := s.tieSlot.erase (r, p) }
  allTieSlot := do
    let l := (← get).tieSlot.toList
    note (.scan .tieSlot (l.map fun ((r, p), _) => .tieSlot r p))
    return l
  owed? p g := do note (.read (.owed p g)); return ((← get).owed.getD p {}).get? g
  setOwed p g b := do
    let s ← get
    if !s.owed.contains p then note (.write (.owedRow p))
    note (.write (.owed p g))
    modify fun s => { s with owed := s.owed.insert p ((s.owed.getD p {}).insert g b) }
  eraseOwed p g := do note (.write (.owed p g)); modify fun s => { s with owed := s.owed.modify p (·.erase g) }
  owedRow? p := do note (.read (.owedRow p)); return (← get).owed.contains p
  eraseOwedRow p := do
    let l := ((← get).owed.getD p {}).toList
    note (.write (.owedRow p))
    for c in l.map fun (g, _) => .owed p g do note (.write c)
    modify fun s => { s with owed := s.owed.erase p }
  allOwed p := do
    let l := ((← get).owed.getD p {}).toList
    note (.scan (.owed p) (l.map fun (g, _) => .owed p g))
    return l
  owedAnswerBits p g := do note (.read (.owedAnswers p g)); return ((← get).owedAnswers.getD p {}).getD g 0
  setOwedAnswers p g b := do
    note (.write (.owedAnswers p g))
    modify fun s => { s with owedAnswers := s.owedAnswers.insert p ((s.owedAnswers.getD p {}).insert g b) }
  allOwedAnswers p := do
    let l := ((← get).owedAnswers.getD p {}).toList
    note (.scan (.owedAnswers p) (l.map fun (g, _) => .owedAnswers p g))
    return l
  sentToBits p g := do note (.read (.sentTo p g)); return ((← get).sentTo.getD p {}).getD g 0
  setSentTo p g b := do
    note (.write (.sentTo p g))
    modify fun s => { s with sentTo := s.sentTo.insert p ((s.sentTo.getD p {}).insert g b) }
  slotHeld? p := do note (.read (.slotHeld p)); return (← get).slotHeld.contains p
  setSlotHeld p armed := do
    note (.write (.slotHeld p))
    modify fun s => { s with
      slotHeld := if armed then s.slotHeld.insert p else s.slotHeld.erase p }
  paceJobs e := do note (.read (.paceQueue e)); return (← get).paceQueue.getD e []
  setPaceJobs e js := do note (.write (.paceQueue e)); modify fun s => { s with paceQueue := s.paceQueue.insert e js }
  stopPull g := do note (.read (.stopPull g)); return (← get).stopPull.contains g
  setStopPull g armed := do
    note (.write (.stopPull g))
    modify fun s => { s with
      stopPull := if armed then s.stopPull.insert g else s.stopPull.erase g }
  peerHasEntry? p g := do note (.read (.peerHas p g)); return ((← get).peerHas.getD p {}).get? g
  setPeerHas p g e := do
    note (.write (.peerHas p g))
    modify fun s => { s with peerHas := s.peerHas.insert p ((s.peerHas.getD p {}).insert g e) }
  holdersOf g i := do note (.read (.holders g i)); return ((← get).holders.getD g {}).getD i {}
  setHolders g i ps := do
    note (.write (.holders g i))
    modify fun s => { s with holders := s.holders.insert g ((s.holders.getD g {}).insert i ps) }
  serveCount p m := do note (.read (.serveCount p m)); return ((← get).serveCount.getD p {}).getD m 0
  setServeCount p m n := do
    note (.write (.serveCount p m))
    modify fun s => { s with serveCount := s.serveCount.insert p ((s.serveCount.getD p {}).insert m n) }
  origin g := do note (.read (.origin g)); return (← get).origin.get? g
  setOrigin g b := do note (.write (.origin g)); modify fun s => { s with origin := s.origin.insert g b }
  plannedTargets? g i := do note (.read (.planned g i)); return ((← get).planned.getD g {}).get? i
  setPlanned g i ps := do
    let s ← get
    if !s.planned.contains g then note (.write (.plannedRow g))
    note (.write (.planned g i))
    modify fun s => { s with planned := s.planned.insert g ((s.planned.getD g {}).insert i ps) }
  planned g := do note (.read (.plannedRow g)); return (← get).planned.contains g
  erasePlannedRow g := do
    let l := ((← get).planned.getD g {}).toList
    note (.write (.plannedRow g))
    for c in l.map fun (i, _) => .planned g i do note (.write c)
    modify fun s => { s with planned := s.planned.erase g }
  pushedEntry? p g := do note (.read (.pushed p g)); return ((← get).pushed.getD p {}).get? g
  setPushed p g e := do
    note (.write (.pushed p g))
    modify fun s => { s with pushed := s.pushed.insert p ((s.pushed.getD p {}).insert g e) }
  desc g := do note (.read (.desc g)); return (← get).desc.get? g
  setDesc g d := do note (.write (.desc g)); modify fun s => { s with desc := s.desc.insert g d }
  inFlight e := do note (.read (.inFlight e)); return (← get).inFlight.getD e 0
  setInFlight e n := do note (.write (.inFlight e)); modify fun s => { s with inFlight := s.inFlight.insert e n }
  waitersLine e := do note (.read (.waiters e)); return (← get).waiters.getD e []
  setWaitersLine e o := do note (.write (.waiters e)); modify fun s => { s with waiters := s.waiters.insert e o }
  sentAt? k := do note (.read (.sent k)); return (← get).sent.get? k
  setSentAt k t := do note (.write (.sent k)); modify fun s => { s with sent := s.sent.insert k t }
  eraseSentAt k := do note (.write (.sent k)); modify fun s => { s with sent := s.sent.erase k }
  unwantedOf p := do note (.read (.unwanted p)); return (← get).unwanted.getD p {}
  setUnwanted p ids := do note (.write (.unwanted p)); modify fun s => { s with unwanted := s.unwanted.insert p ids }
  allAskedAt := do
    let l := (← get).askedAt.toList
    note (.scan .askedAt (l.map fun (a, _) => .askedAt a))
    return l
  allTriedAll := do
    let l := (← get).tried.toList.map fun (a, m) => (a, m.toList)
    note (.scan .triedAll (l.flatMap fun (a, ps) => ps.map fun (p, _) => .tried a p))
    return l
  allTried a := do
    let l := ((← get).tried.getD a {}).toList
    note (.scan (.tried a) (l.map fun (p, _) => .tried a p))
    return l
  allOffers := do
    let l := (← get).offers.toList
    note (.scan .offers (l.map fun (a, _) => .offers a))
    return l
  allOfferedAll := do
    let l := (← get).offered.toList.map fun (q, m) => (q, m.toList)
    note (.scan .offeredAll (l.flatMap fun (q, gs) => gs.map fun (g, _) => .offered q g))
    return l
  allOffered q := do
    let l := ((← get).offered.getD q {}).toList
    note (.scan (.offered q) (l.map fun (g, _) => .offered q g))
    return l
  allParkAll := do
    let l := (← get).park.toList.map fun (p, m) => (p, m.toList)
    note (.scan .parkAll (l.flatMap fun (p, gs) => gs.map fun (g, _) => .park p g))
    return l
  allPark p := do
    let l := ((← get).park.getD p {}).toList
    note (.scan (.park p) (l.map fun (g, _) => .park p g))
    return l
  allAskedParked := do
    let l := (← get).askedParked.toList
    note (.scan .askedParked (l.map fun (k, _) => .askedParked k))
    return l
  allLrArmed := do
    let l := (← get).lastResortArmed.toList
    note (.scan .lrArmed (l.map fun k => .lrArmed k))
    return l
  allIhaveFrames := do
    let l := (← get).ihaveFrames.toList
    note (.scan .ihaveFrames (l.map fun (p, _) => .ihaveFrames p))
    return l
  allIhaveAsked := do
    let l := (← get).ihaveAsked.toList
    note (.scan .ihaveAsked (l.map fun (p, _) => .ihaveAsked p))
    return l
  allReceived := do
    let l := (← get).received.toList
    note (.scan .received (l.map fun (g, _) => .received g))
    return l
  allMine := do
    let l := (← get).mine.toList
    note (.scan .mine (l.map fun (g, _) => .mine g))
    return l
  allState := do
    let l := (← get).state.toList
    note (.scan .state (l.map fun (g, _) => .state g))
    return l
  allPendingIds := do
    let l := (← get).pendingIds.toList
    note (.scan .pendingIds (l.map fun m => .pendingId m))
    return l
  allOwedAll := do
    let l := (← get).owed.toList.map fun (p, m) => (p, m.toList)
    note (.scan .owedAll (l.flatMap fun (p, gs) => .owedRow p :: gs.map fun (g, _) => .owed p g))
    return l
  allOwedAnswersAll := do
    let l := (← get).owedAnswers.toList.map fun (p, m) => (p, m.toList)
    note (.scan .owedAnswersAll (l.flatMap fun (p, gs) => gs.map fun (g, _) => .owedAnswers p g))
    return l
  allSentToAll := do
    let l := (← get).sentTo.toList.map fun (p, m) => (p, m.toList)
    note (.scan .sentToAll (l.flatMap fun (p, gs) => gs.map fun (g, _) => .sentTo p g))
    return l
  allSlotHeld := do
    let l := (← get).slotHeld.toList
    note (.scan .slotHeld (l.map fun p => .slotHeld p))
    return l
  allPaceQueue := do
    let l := (← get).paceQueue.toList
    note (.scan .paceQueue (l.map fun (e, _) => .paceQueue e))
    return l
  allStopPull := do
    let l := (← get).stopPull.toList
    note (.scan .stopPull (l.map fun g => .stopPull g))
    return l
  allPeerHas := do
    let l := (← get).peerHas.toList.map fun (p, m) => (p, m.toList)
    note (.scan .peerHas (l.flatMap fun (p, gs) => gs.map fun (g, _) => .peerHas p g))
    return l
  allHolders := do
    let l := (← get).holders.toList.map fun (g, m) => (g, m.toList)
    note (.scan .holders (l.flatMap fun (g, is) => is.map fun (i, _) => .holders g i))
    return l
  allServeCount := do
    let l := (← get).serveCount.toList.map fun (p, m) => (p, m.toList)
    note (.scan .serveCount (l.flatMap fun (p, ms) => ms.map fun (m, _) => .serveCount p m))
    return l
  allOrigin := do
    let l := (← get).origin.toList
    note (.scan .origin (l.map fun (g, _) => .origin g))
    return l
  allPlannedAll := do
    let l := (← get).planned.toList.map fun (g, m) => (g, m.toList)
    note (.scan .plannedAll (l.flatMap fun (g, is) => .plannedRow g :: is.map fun (i, _) => .planned g i))
    return l
  allPushed := do
    let l := (← get).pushed.toList.map fun (p, m) => (p, m.toList)
    note (.scan .pushed (l.flatMap fun (p, gs) => gs.map fun (g, _) => .pushed p g))
    return l
  allDesc := do
    let l := (← get).desc.toList
    note (.scan .desc (l.map fun (g, _) => .desc g))
    return l
  allInFlight := do
    let l := (← get).inFlight.toList
    note (.scan .inFlight (l.map fun (e, _) => .inFlight e))
    return l
  allWaiters := do
    let l := (← get).waiters.toList
    note (.scan .waiters (l.map fun (e, _) => .waiters e))
    return l
  allSent := do
    let l := (← get).sent.toList
    note (.scan .sent (l.map fun (k, _) => .sent k))
    return l
  allUnwanted := do
    let l := (← get).unwanted.toList
    note (.scan .unwanted (l.map fun (p, _) => .unwanted p))
    return l

/-- The interface through a monad transformer. -/
abbrev lift {m n : Type → Type} [Tables m] (f : ∀ {α : Type}, m α → n α) : Tables n where
  askedAt? a := f (askedAt? a)
  setAskedAt a t := f (setAskedAt a t)
  eraseAskedAt a := f (eraseAskedAt a)
  tried? a p := f (tried? a p)
  setTried a p t := f (setTried a p t)
  eraseTried a p := f (eraseTried a p)
  offersOf a := f (offersOf a)
  setOffers a o := f (setOffers a o)
  eraseOffers a := f (eraseOffers a)
  promise? a p := f (promise? a p)
  setPromise a p t := f (setPromise a p t)
  erasePromise a p := f (erasePromise a p)
  allPromises := f allPromises
  offeredBits q g := f (offeredBits q g)
  setOffered q g b := f (setOffered q g b)
  parkUntil? p g := f (parkUntil? p g)
  setPark p g t := f (setPark p g t)
  erasePark p g := f (erasePark p g)
  askedParkedOf k := f (askedParkedOf k)
  setAskedParked k ps := f (setAskedParked k ps)
  eraseAskedParked k := f (eraseAskedParked k)
  lrArmed? k := f (lrArmed? k)
  setLrArmed k b := f (setLrArmed k b)
  ihaveFrames p := f (ihaveFrames p)
  setIhaveFrames p n := f (setIhaveFrames p n)
  clearIhaveFrames := f clearIhaveFrames
  ihaveAsked p := f (ihaveAsked p)
  setIhaveAsked p n := f (setIhaveAsked p n)
  clearIhaveAsked := f clearIhaveAsked
  heldBack? k := f (heldBack? k)
  setHeldBack k a := f (setHeldBack k a)
  clearHeldBack := f clearHeldBack
  allHeldBack := f allHeldBack
  receivedBits g := f (receivedBits g)
  setReceived g b := f (setReceived g b)
  mineBits g := f (mineBits g)
  setMine g b := f (setMine g b)
  state? g := f (state? g)
  setState g st := f (setState g st)
  tied? r p g := f (tied? r p g)
  setTied r p g b := f (setTied r p g b)
  eraseTied r p g := f (eraseTied r p g)
  tiedRow? r := f (tiedRow? r)
  eraseTiedRow r := f (eraseTiedRow r)
  tiedPeerRow? r p := f (tiedPeerRow? r p)
  eraseTiedPeerRow r p := f (eraseTiedPeerRow r p)
  allTiedAll := f allTiedAll
  allTiedRoot r := f (allTiedRoot r)
  allTiedPeer r p := f (allTiedPeer r p)
  lane? p l := f (lane? p l)
  setLane p l es := f (setLane p l es)
  eraseLane p l := f (eraseLane p l)
  allQueue := f allQueue
  pendingOf r := f (pendingOf r)
  setPending r w := f (setPending r w)
  erasePending r := f (erasePending r)
  allPending := f allPending
  pendingId? m := f (pendingId? m)
  setPendingId m armed := f (setPendingId m armed)
  tieSlot? r p := f (tieSlot? r p)
  setTieSlot r p sl := f (setTieSlot r p sl)
  eraseTieSlot r p := f (eraseTieSlot r p)
  allTieSlot := f allTieSlot
  owed? p g := f (owed? p g)
  setOwed p g b := f (setOwed p g b)
  eraseOwed p g := f (eraseOwed p g)
  owedRow? p := f (owedRow? p)
  eraseOwedRow p := f (eraseOwedRow p)
  allOwed p := f (allOwed p)
  owedAnswerBits p g := f (owedAnswerBits p g)
  setOwedAnswers p g b := f (setOwedAnswers p g b)
  allOwedAnswers p := f (allOwedAnswers p)
  sentToBits p g := f (sentToBits p g)
  setSentTo p g b := f (setSentTo p g b)
  slotHeld? p := f (slotHeld? p)
  setSlotHeld p armed := f (setSlotHeld p armed)
  paceJobs e := f (paceJobs e)
  setPaceJobs e js := f (setPaceJobs e js)
  stopPull g := f (stopPull g)
  setStopPull g armed := f (setStopPull g armed)
  peerHasEntry? p g := f (peerHasEntry? p g)
  setPeerHas p g e := f (setPeerHas p g e)
  holdersOf g i := f (holdersOf g i)
  setHolders g i ps := f (setHolders g i ps)
  serveCount p m := f (serveCount p m)
  setServeCount p m n := f (setServeCount p m n)
  origin g := f (origin g)
  setOrigin g b := f (setOrigin g b)
  plannedTargets? g i := f (plannedTargets? g i)
  setPlanned g i ps := f (setPlanned g i ps)
  planned g := f (planned g)
  erasePlannedRow g := f (erasePlannedRow g)
  pushedEntry? p g := f (pushedEntry? p g)
  setPushed p g e := f (setPushed p g e)
  desc g := f (desc g)
  setDesc g d := f (setDesc g d)
  inFlight e := f (inFlight e)
  setInFlight e n := f (setInFlight e n)
  waitersLine e := f (waitersLine e)
  setWaitersLine e o := f (setWaitersLine e o)
  sentAt? k := f (sentAt? k)
  setSentAt k t := f (setSentAt k t)
  eraseSentAt k := f (eraseSentAt k)
  unwantedOf p := f (unwantedOf p)
  setUnwanted p ids := f (setUnwanted p ids)
  allAskedAt := f allAskedAt
  allTriedAll := f allTriedAll
  allTried a := f (allTried a)
  allOffers := f allOffers
  allOfferedAll := f allOfferedAll
  allOffered q := f (allOffered q)
  allParkAll := f allParkAll
  allPark p := f (allPark p)
  allAskedParked := f allAskedParked
  allLrArmed := f allLrArmed
  allIhaveFrames := f allIhaveFrames
  allIhaveAsked := f allIhaveAsked
  allReceived := f allReceived
  allMine := f allMine
  allState := f allState
  allPendingIds := f allPendingIds
  allOwedAll := f allOwedAll
  allOwedAnswersAll := f allOwedAnswersAll
  allSentToAll := f allSentToAll
  allSlotHeld := f allSlotHeld
  allPaceQueue := f allPaceQueue
  allStopPull := f allStopPull
  allPeerHas := f allPeerHas
  allHolders := f allHolders
  allServeCount := f allServeCount
  allOrigin := f allOrigin
  allPlannedAll := f allPlannedAll
  allPushed := f allPushed
  allDesc := f allDesc
  allInFlight := f allInFlight
  allWaiters := f allWaiters
  allSent := f allSent
  allUnwanted := f allUnwanted

instance instReaderT {m : Type → Type} {ρ : Type} [Monad m] [Tables m] : Tables (ReaderT ρ m) :=
  lift (m := m) (n := ReaderT ρ m) fun x => monadLift x

end Tables

end SpecTwin
