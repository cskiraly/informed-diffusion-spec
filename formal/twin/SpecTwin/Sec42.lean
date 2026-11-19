import SpecTwin.Sec44
import SpecTwin.Sec2
import SpecTwin.Sec3
import SpecTwin.Sec54

/-! # protocol.md §4.2, "A chunk arrives" [c5, c7, c10, c14] (v0.10.4, spec 34f60f8, lines 467–570
and 459–477), and §6.1's `close_promises` (lines 1411–1421)

`on_chunk`, `on_validated`, `drop_beyond`, `send_have`, `have_bits` and `close_promises`; and the deferral path:
`defer`, `tie`, `tie_room`, `on_block_installed`, `drop_tie` and `drop_stale_waits`. Line for line.
`drop_offer` (§6.1, lines 1423–1433) is here too: it stands after `close_promises`, which it calls.
Python's meanings kept on purpose:
- `or` and `and` short-circuit, so the node is asked in the Python's order: `seen(mid)` before `mid in
  pending_ids`, `expired` before `live`, `admitted` before `tie_room`, `state[g] == COLLECTING` before
  `popcount(received[g])` and `desc[g]`;
- a read of another section's table is one read on the tape for each time the Python reads it: `g in origin` and
  then `origin[g]`; `g in desc` and then `N(desc[g])`;
- `mesh | {p}` is asked only where the chunk is claimed; where it is not, the Python iterates `{p}` and asks
  nothing;
- the Python iterates a dict in its insertion order, which no record holds. Where it iterates one of the twin's
  own levels whose order shows (`list(queue)`; `list(pending)`, `list(tie_slot.items())`, `tied`'s three
  levels), the twin asks the node's order of its rows: the replay checks the answer is a permutation of them.
  `list(queue)` is read once per index `drop_beyond` drops, as the Python makes the list again each time;
- `tied.pop(root)` hands out the toy's own object, which the Python then iterates: the order of each level under
  it is asked at the pop, outer first, where the row was there;
- a set iterates as the Python's `sorted(idx)` does here, upward; `idx` holds each index once; a list of waits
  keeps its order, and `remove` takes the first equal pair;
- `bits.clear(i)` in place, then `if not bits: groups.pop(g)`: a bitmap there and empty is popped, whether or not
  this call emptied it (`tied` keeps its rows, and a record holds a row's presence);
- a bitmap of `offered`, or a set of `asked_parked`, that a change in place leaves as it was is not written: the
  Python's change in place is no write then;
- `on_validated` and `defer` call each other. The recursion is cut by a fuel, `deferDepth`: at zero the twin
  stands where the Python would recurse again, with a crash. In the node, what bounds the depth is validate_chunk's
  own ask of `installed_block` (protocol.md:342). That ask runs inside a call on the tape, past the tracer's
  one-answer check. So the tracer also counts a record's chain of defers and stops at the third.
  The replay would report a crash at zero fuel as a mismatch, so no wrong twin passes.

The functions reach the block's tables through `Tables` and in no other way; `enter` marks each one's entry, for
the replay's comparison with the record's `reached`. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- How many times, at most, `defer` calls `on_validated` again within one call of the block. In the node, a
copy deferred again after its block installed would need `validate_chunk` to answer DEFER with the block there,
which it does not: one level suffices. The directed records validate twice by the scenario's word, so two. -/
def deferDepth : Nat := 2

/-- `have_bits(g)`: what our HAVE says of g: what we hold, or, for a group we publish, what is known to have
arrived [P4] -/
def haveBits (g : Group) : M m Bits := do
  enter "have_bits"
  if (← origin g).isSome then                               -- `origin[g] if g in origin else mine[g]`
    match ← origin g with
    | some b =>
      branch "have_bits: origin"
      return b
    | none => crash "KeyError: origin[g] (have_bits: g gone between `g in origin` and `origin[g]`)"
  branch "have_bits: mine"
  mineBits g

/-- `send_have(p, g)` [c7]: always the whole bitmap, as it is now -/
def sendHave (p : Peer) (g : Group) : M m Unit := do
  enter "send_have"
  let b ← haveBits g
  let _ ← enqueue p (.have g b) true                        -- `enqueue(p, IDONTWANT(HaveBitmap(…)), urgent=True)`

/-- `close_promises(g, i, of)` [c5]: chunk i of g arrived, from anyone: what was kept to ask for it goes, under
every key that names it (§8.1). With `of`, that peer alone answered, with a copy that waits (§4.2): its promise
closes, nothing else. -/
def closePromises (g : Group) (i : Nat) (of_ : Option Peer) : M m Unit := do
  enter "close_promises"
  let k : Chunk := (g, i)
  for ((a, q), _) in ← allPromises do                       -- `for (a, q) in list(promises)`
    if a.chunk == k && (of_.isNone || of_ == some q) then   -- `(group(a), index(a)) == k and of in (None, q)`
      erasePromise a q
  if of_.isSome then
    branch "close_promises: of a peer"
    return
  -- `[a for t in (offers, tried, asked_at) for a in list(t) if (group(a), index(a)) == k]`
  let as := ((← allOffers).map (·.1) ++ (← allTriedAll).map (·.1) ++ (← allAskedAt).map (·.1)).filter (·.chunk == k)
  for a in as do                                            -- `offers.pop(a, None); tried.pop(a, None);
    let _ ← offersOf a                                      --   asked_at.pop(a, None)`: a pop reads, then writes
    eraseOffers a
    for (q, _) in ← allTried a do
      eraseTried a q
    let _ ← askedAt? a
    eraseAskedAt a
  let _ ← askedParkedOf k                                   -- `asked_parked.pop(k, None)`: the last resort's count is per chunk
  eraseAskedParked k
  for (q, _) in ← allOfferedAll do                          -- `for q in list(offered):`
    let b ← offeredBits q g                                 --   `if g in offered[q]: offered[q][g].clear(i)`
    if b.has i then setOffered q g (b.clear i)
  branch "close_promises: every key"

/-- `drop_offer(g, i, p)` (§6.1, lines 1423–1433): p's offers of chunk i of g go, under every key that names it,
and its asks of the chunk with them (§4.2's drop_tie; the offers' expiry).
- The asks queued to p are removed in **the normal lane alone**: the document's loop is over `queue[p].normal`.
- `queue[p].normal = [...]` where p has no queue: the toy's detached queue takes the empty lane and joins no table
  (§8.1: reading allocates nothing). The lane is written and stays missing, and no row is made (`eraseLane`).
- The calls for two peers commute: each touches its own peer's bitmap, list entries, lane and promises. So the
  order in which drop_beyond calls it over `list(queue)` shows in no record. -/
def dropOffer (g : Group) (i : Nat) (p : Peer) : M m Unit := do
  enter "drop_offer"
  let k : Chunk := (g, i)
  let b ← offeredBits p g                                   -- `if g in offered[p]: offered[p][g].clear(i)`
  if b.has i then setOffered p g (b.clear i)
  -- `for a in [a for a in list(offers) if (group(a), index(a)) == k and p in offers[a]]:`
  for (a, o) in (← allOffers).filter fun (a, o) => a.chunk == k && o.contains p do
    let o' := o.erase p                                     -- `offers[a].remove(p)`
    if o'.isEmpty then eraseOffers a                        -- `if not offers[a]: del offers[a]`
    else setOffers a o'
  match ← lane? p .normal with                              -- `for e in queue[p].normal:`
  | none =>                                                 -- no queue of p's: nothing to filter, and the lane
    eraseLane p .normal                                     --   assigned stays missing
    branch "drop_offer: no queue of the peer's"
  | some normal =>
    -- `for c in e.iwants(): c.ids = [b for b in c.ids if (group(b), index(b)) != k]`: an ask of it still queued
    let cut : Ctl → Ctl
      | .iwant ids => .iwant (ids.filter fun b => b.chunk != k)
      | c => c
    let filtered := normal.map fun e => { e with control := e.control.map (·.map cut) }
    setLane p .normal (filtered.filter (!·.isEmpty))        -- `queue[p].normal = [e … if not e.is_empty()]`
    branch "drop_offer: the peer's normal lane filtered"
  closePromises g i (some p)                                -- and p's promise for it closes

/-- `drop_beyond(g)`: g's count is known now: what named an index it has not, while the count was unknown, goes
(§8.2) -/
def dropBeyond (g : Group) : M m Unit := do
  enter "drop_beyond"
  let n ← N (← desc g)                                      -- `n = N(desc[g])`: §1's N
  let mut idx : List Nat := []
  for (q, _) in ← allOfferedAll do                          -- `{i for q in list(offered) for i in offered[q][g] if i >= n}`
    for i in (← offeredBits q g).toList do
      if i ≥ n then idx := i :: idx
  -- `idx |= {index(a) for t in (offers, tried, asked_at) for a in list(t) if group(a) == g and index(a) >= n}`
  for a in (← allOffers).map (·.1) ++ (← allTriedAll).map (·.1) ++ (← allAskedAt).map (·.1) do
    if a.group == g && a.index ≥ n then idx := a.index :: idx
  for i in (sortBy (· < ·) idx.eraseDups) do                -- `for i in sorted(idx):`
    -- `for q in list(queue): drop_offer(g, i, q)`: the peers with a queue are the twin's rows,
    -- read as a whole, in the node's order of them
    for q in ← queueOrder ((← allQueue).map (·.1)) do
      dropOffer g i q
    closePromises g i none
  -- `for root, peers in list(tied.items()):` and `for q, groups in list(peers.items()):`: the roots, and each
  -- root's peers, in the node's order; the table read whole once
  let all ← allTiedAll
  for r in ← tiedRootsOrder (all.map (·.1)) do
    for q in ← tiedPeersOrder r (((all.lookup r).getD []).map (·.1)) do
      match ← tied? r q g with                              --     `bits = groups.get(g)`
      | none => continue
      | some b =>
        let b' := b.toList.foldl (fun acc i => if i ≥ n then acc.clear i else acc) b
        if b' == 0 then eraseTied r q g                     --     `if not bits: groups.pop(g)`
        else if b' != b then setTied r q g b'               --     `bits.clear(i)` for each i >= n, in place
  branch (if idx.isEmpty then "drop_beyond: nothing beyond" else "drop_beyond: dropped")
where
  sortBy (lt : Nat → Nat → Bool) (l : List Nat) : List Nat := (l.toArray.qsort lt).toList

/-- `tie_room(p, f)`: §8.2's limits on ties, per connection -/
def tieRoom (p : Peer) (f : ChunkF) : M m Bool := do
  enter "tie_room"
  let c := (← read).c
  if f.i ≥ c.MAX_PLAIN_CHUNKS then                          -- an index no group has,
    branch "tie_room: an index no group has"
    return false
  if (← desc f.g).isSome then                               -- `f.group in desc and f.index >= N(desc[f.group])`:
    let n ← N (← desc f.g)                                  --   or this group has not;
    if f.i ≥ n then
      branch "tie_room: beyond the group's count"
      return false
  if (← tied? f.root p f.g).isSome then                     -- `f.group in tied[f.beacon_block_root][p]`: a root
    branch "tie_room: tied already"                         --   and group tied for p already,
    return true
  -- `sum(len(t[p]) for t in tied.values()) < MAX_PENDING_GROUPS`: or room for another (none: no limit)
  let n := (← allTiedAll).foldl (fun acc (_, peers) => acc + ((peers.lookup p).map (·.length)).getD 0) 0
  let r := match c.MAX_PENDING_GROUPS with
    | none => true
    | some limit => n < limit
  branch (if r then "tie_room: room for another" else "tie_room: no room")
  return r

/-- `tie(p, f)`: a copy that cannot be checked yet ties its sender to the root it names, per connection and group,
within its lifetime and window and §8.2's limits on ties -/
def tie (p : Peer) (f : ChunkF) : M m Unit := do
  enter "tie"
  if ← expired f.g then                                     -- `if expired(f.group) or not live(f.slot): return`
    branch "tie: expired"
    return
  if !(← live f.slot) then
    branch "tie: not live"
    return
  if !(← admitted p f) then                                 -- `if not admitted(p, f) or not tie_room(p, f): return`
    branch "tie: not admitted"
    return
  if !(← tieRoom p f) then
    branch "tie: no room"
    return
  setTied f.root p f.g (((← tied? f.root p f.g).getD 0).set f.i)   -- `tied[root][p][f.group].set(f.index)`
  if (← tieSlot? f.root p).isNone then                      -- `tie_slot.setdefault((root, p), f.slot)`: the
    setTieSlot f.root p f.slot                              --   slot p's first copy named
  closePromises f.g f.i (some p)                            -- p answered: its promise for the index closes
  branch "tie: tied"

/-- `claim_group(g)` (§4.6, lines 835–839) [c10]: at the K-th chunk, before decoding. Here, and not with §4.6's
others (Sec46.lean), since on_validated calls it and it calls send_have. `close_promises_of_group` is the node's
(§8.2's interface): a call with its log. -/
def claimGroup (g : Group) : M m Unit := do
  enter "claim_group"
  setStopPull g true                                        -- [c6] no further asks for this group
  setMine g ((1 <<< (← N (← desc g))) - 1)                  -- [c10] `mine[g] = all_bits(N(desc[g]))`
  for q in ← meshList do sendHave q g                       -- [c10] the decode claim: all N bits
  closePromisesOfGroup g                                    -- [c5] nobody owes us chunks of this group

mutual

/-- `on_validated(p, f, result)`: the chunk's handling once level 1's result is known. `fuel`: how many more times
`defer` may call it within this call of the block. -/
def onValidated (fuel : Nat) (p : Peer) (f : ChunkF) (result : Verdict) : M m Unit := do
  enter "on_validated"
  -- `if expired(f.group) or not live(f.slot): return`: expired or out of the window meanwhile (§8.1)
  if ← expired f.g then
    branch "on_validated: expired"
    return
  if !(← live f.slot) then
    branch "on_validated: not live"
    return
  if result == .defer then                                  -- `if result == DEFER: return defer(p, f)`
    defer fuel p f
    branch "on_validated: deferred"
    return
  markSeen (← messageId f)                                  -- `mark_seen(message_id(f))`: never validated again
  if result == .reject then                                 -- `if result == REJECT: return penalise(p)`
    penalise p
    branch "on_validated: rejected"
    return
  let g := f.g
  let i := f.i
  if (← desc g).isNone then                                 -- `if g not in desc:`
    openGroup g f                                           --   desc[g] from the bid; state[g] = COLLECTING
    dropBeyond g                                            --   what named an index it has not goes (§8.2)
  if (← state? g) == some .invalid then                     -- a dropped group (§4.6)
    branch "on_validated: invalid"
    return
  if (← receivedBits g).has i then                          -- a second copy of a chunk we received: acknowledge
    sendHave p g
    branch "on_validated: received before"
    return
  store g i f                                               -- also records known_id[g][i] = message_id(f)
  setReceived g ((← receivedBits g).set i)                  -- `received[g].set(i)`
  closePromises g i none                                    -- [c5] the chunk arrived, from anyone
  let claim := !(← mineBits g).has i                        -- not yet claimed (decoded nodes claimed everything)
  if claim then setMine g ((← mineBits g).set i)            -- [c7] only chunks that passed level 1
  let qs ← if claim then meshAnd p else pure [p]            -- `for q in (mesh | {p}) if claim else {p}:`
  for q in qs do
    sendHave q g                                            -- [c7] the claim to the mesh, and [c14] the sender's ack
  if (← read).replaced.contains "forward" then forwardNode f p   -- §5.2; or the node's own
  else forward f.narrow p
  -- `if state[g] == COLLECTING and popcount(received[g]) >= K(desc[g]):`
  if (← state? g) == some .collecting then
    let count := (← receivedBits g).popcount
    let k ← K (← desc g)                                    -- §1's K
    if count ≥ k then
      setState g .decoding                                  -- once per group
      claimGroup g                                          -- [c10] the decode claim, at K (§4.6)
      start "decode_group" g                                -- level 2, off the chunk path
      branch "on_validated: stored, and K reached"
      return
  branch (if claim then "on_validated: stored and claimed" else "on_validated: stored, claimed before")
termination_by (fuel, 1)

/-- `defer(p, f)`: on the router's event loop, like installation -/
def defer (fuel : Nat) (p : Peer) (f : ChunkF) : M m Unit := do
  enter "defer"
  if (← installedBlock f.slot f.root).isSome then           -- installed in the meantime
    match fuel with
    | 0 => crash "RecursionError: defer (on_validated and defer past B1's depth)"
    | fuel + 1 =>
      onValidated fuel p f (← validateChunk f)              -- `return on_validated(p, f, validate_chunk(f))`
      branch (if fuel == 0 then "defer: installed in the meantime, at the last level B1 allows"
              else "defer: installed in the meantime")
      return
  if !(← admitted p f) then                                 -- a group beyond the peer's unknown groups (§8.2):
    branch "defer: not admitted"                            --   ignored, neither kept nor tied
    return
  tie p f                                                   -- kept or refused, its sender is tied to the root
  if ← reserve p f then                                     -- a per-peer reservation in a bounded store (§8.2)
    setPending f.root ((← pendingOf f.root) ++ [(p, f)])    -- `pending[f.beacon_block_root].append((p, f))`
    setPendingId (← messageId f) true                       -- `pending_ids.add(message_id(f))`
    branch "defer: kept"
  else
    branch "defer: refused"                                 -- not kept: a later copy is evaluated afresh; its
                                                            --   sender stays tied
termination_by (fuel, 0)

end

/-- `on_chunk(p, f)` -/
def onChunk (p : Peer) (f : ChunkF) : M m Unit := do
  enter "on_chunk"
  let mid ← messageId f                                     -- `mid = message_id(f)`: §2's function
  -- `if seen(mid) or mid in pending_ids:`: a duplicate, a chunk rejected before, or one waiting
  let mut dup ← seen mid
  if !dup then dup ← pendingId? mid
  if dup then
    if ← accepted mid then                                  -- [c14] duplicates are acknowledged too
      sendHave p f.g
      branch "on_chunk: a duplicate, acknowledged"
    else if ← pendingId? mid then                           -- another copy of one that waits: its sender too
      tie p f
      branch "on_chunk: a duplicate of one waiting, tied"
    else
      branch "on_chunk: a duplicate, ignored"
    return
  -- `if expired(f.group) or not live(f.slot): return`: past its lifetime or live window (§8.1)
  if ← expired f.g then
    branch "on_chunk: expired"
    return
  if !(← live f.slot) then
    branch "on_chunk: not live"
    return
  onValidated deferDepth p f (← validateChunk f)            -- level 1 (§3)

/-- `drop_tie(p, g, bits)`: a tie its root does not release (a mismatch, or its slot left the live window, §8.1):
p's offers of these indices go, with its asks of them (§6.1), and the recovery goes on without p -/
def dropTie (p : Peer) (g : Group) (bits : Bits) : M m Unit := do
  enter "drop_tie"
  for i in bits.toList do                                   -- `for i in bits:`, upward
    dropOffer g i p
    if ← authenticable g then                               -- else the ledger asks at installation
      retryOffer (.want g i)
  branch (if bits == 0 then "drop_tie: nothing" else "drop_tie: dropped")

/-- `tied.pop(root, {})` (or `tied.pop(root, None)`), as the Python then iterates what the pop hands out: the
row read whole and erased, and, where it was there, the node's order of its peers, then of each peer's groups,
asked at the pop. Not a function of the document: a step of the two that pop. -/
def popTiedRoot (r : Root) : M m (List (Peer × List (Group × Bits))) := do
  let there ← tiedRow? r
  let peers ← allTiedRoot r
  eraseTiedRow r
  if !there then return []
  let mut out : List (Peer × List (Group × Bits)) := []
  for p in ← tiedPeersOrder r (peers.map (·.1)) do
    let gs := (peers.lookup p).getD []
    let order ← tiedGroupsOrder r p (gs.map (·.1))
    out := out ++ [(p, order.map fun g => (g, (gs.lookup g).getD 0))]
  return out

/-- `tied[root].pop(p, None)`: the row read whole and erased, and, where it was there, the node's order of its
groups asked at the pop. A step of `drop_stale_waits`. -/
def popTiedPeer (r : Root) (p : Peer) : M m Unit := do
  let there ← tiedPeerRow? r p
  let gs ← allTiedPeer r p
  eraseTiedPeerRow r p
  if there then
    let _ ← tiedGroupsOrder r p (gs.map (·.1))

/-- `on_block_installed(root)`: resumes level 1 -/
def onBlockInstalled (root : Root) : M m Unit := do
  enter "on_block_installed"
  let waits ← pendingOf root                                -- `for p, f in pending.pop(root, []):`, in the list's
  erasePending root                                         --   own order
  for (p, f) in waits do
    setPendingId (← messageId f) false                      -- `pending_ids.discard(message_id(f))`
    release p f                                             -- the reservation goes back
    onValidated deferDepth p f (← validateChunk f)          -- `on_validated(p, f, validate_chunk(f))`
  let g0 ← bidGroup root                                    -- the group this root's bid commits
  for (p, groups) in ← popTiedRoot root do                  -- `for p, groups in tied.pop(root, {}).items():` the
    let _ ← tieSlot? root p                                 --   copies that waited for this root;
    eraseTieSlot root p                                     --   `tie_slot.pop((root, p), None)`
    for (g, bits) in groups do                              -- `for g, bits in groups.items():`
      if ← expired g then                                   -- its offers went with its lifetime (§8.1)
        branch "on_block_installed: a tie of an expired group"
        continue
      if g0 != some g then                                  -- a copy naming a group its root does not commit
        dropTie p g bits                                    --   is a forgery: nothing is released
        branch "on_block_installed: a tie of another group, dropped"
        continue
      let _ ← parkUntil? p g                                -- `park[p].pop(g, None)`: the senders' parks for the
      erasePark p g                                         --   group lift,
      for i in bits.toList do
        let done ← askedParkedOf (g, i)                     -- `asked_parked[(g, i)].discard(p)`: the last-resort counts for
        if done.contains p then                             --   their indices clear,
          setAskedParked (g, i) (done.erase p)
        if (← desc g).isSome then                           -- `if g in desc and i >= N(desc[g]): continue`: an
          let n ← N (← desc g)                              --   index the group, known now, has not is dropped
                                                            --   (§8.2), the others kept,
          if i ≥ n then
            branch "on_block_installed: an index beyond the count learnt meanwhile"
            continue
        if !(← mineBits g).has i then                       --   and each is an offer of its index again
          addOffer (.want g i) p
      branch "on_block_installed: a tie released"
  match g0 with                                             -- `for a in ledger(g0): retry_offer(a)`: what was
  | some g0 =>                                              --   announced meanwhile (§4.4), and what the ties
    for a in ← ledger g0 do                                 --   released, is asked for now
      retryOffer a
  | none =>                                                 -- a block of columns: `ledger(None)` reads `offered`
    let _ ← connectedTopicPeers                             --   under a group no table has, and finds nothing.
    branch "on_block_installed: no group committed"         --   No record holds those reads (the tracer writes a
                                                            --   group's key), so none reaches this way

/-- `drop_stale_waits()`: at each heartbeat (§6.4): what waits for a root not installed, past its group's lifetime
or its slot's live window (§8.1): a kept copy goes, its reservation back; and a tie, by the slot its sender's first
copy named, goes through drop_tie: the sender's offers and asks of those indices with it (§6.1) -/
def dropStaleWaits : M m Unit := do
  enter "drop_stale_waits"
  for root in ← pendingOrder ((← allPending).map (·.1)) do  -- `for root in list(pending):`
    -- `[(p, f) for p, f in pending[root] if expired(f.group) or not live(f.slot)]`
    let mut stale : List (Peer × ChunkF) := []
    for (p, f) in ← pendingOf root do
      if ← expired f.g then
        stale := stale ++ [(p, f)]
      else if !(← live f.slot) then
        stale := stale ++ [(p, f)]
    for (p, f) in stale do
      setPending root ((← pendingOf root).erase (p, f))     -- `pending[root].remove((p, f))`: the first equal pair
      setPendingId (← messageId f) false                    -- `pending_ids.discard(message_id(f))`
      release p f
      branch "drop_stale_waits: a kept copy gone"
    if (← pendingOf root).isEmpty then                      -- `if not pending[root]: del pending[root]`
      erasePending root
      branch "drop_stale_waits: a root's waits all gone"
  let slots ← allTieSlot
  for (root, p) in ← tieSlotOrder (slots.map (·.1)) do       -- `for (root, p), s in list(tie_slot.items()):`
    let s := (slots.lookup (root, p)).getD 0
    -- `groups = tied[root][p]`; `[g for g in groups if expired(g) or not live(s)]`: iterated in the node's order.
    -- The Python's iteration reads the row whole, its presence too, as each `not groups` and `not tied[root]` does
    let _ ← tiedPeerRow? root p
    let gs ← allTiedPeer root p
    let mut stale : List Group := []
    for g in ← tiedGroupsOrder root p (gs.map (·.1)) do
      if ← expired g then
        stale := stale ++ [g]
      else if !(← live s) then
        stale := stale ++ [g]
    for g in stale do                                       -- `drop_tie(p, g, groups.pop(g))`
      let some bits ← tied? root p g
        | return (← crash "KeyError: groups.pop(g) (drop_stale_waits)")
      eraseTied root p g
      dropTie p g bits
      branch "drop_stale_waits: a tie gone"
    if (← allTiedPeer root p).isEmpty then                  -- `if not groups:` nothing left of p under the root
      popTiedPeer root p                                    -- `tied[root].pop(p, None)`
      let _ ← tieSlot? root p                               -- `tie_slot.pop((root, p), None)`
      eraseTieSlot root p
      branch "drop_stale_waits: a peer's ties under a root all gone"
      let _ ← tiedRow? root
      if (← allTiedRoot root).isEmpty then                  -- `if not tied[root]: tied.pop(root, None)`
        let _ ← popTiedRoot root
        branch "drop_stale_waits: a root's ties all gone"
  branch "drop_stale_waits: done"

end SpecTwin
