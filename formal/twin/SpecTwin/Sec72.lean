import SpecTwin.Sec42
import SpecTwin.Sec71
import SpecTwin.Sec52
import SpecTwin.Sec51

/-! # protocol.md §7.2, "Choosing what to send, at the moment of sending" [c8, c9, c12, c14] (v0.10.7,
lines 1831–1896)

next_to_send's line at PUBLISH (line 1855, `if SOURCE_OFFERS == PUBLISH: origin_written(out.chunk)`) came with
v0.10.4; `origin_written` is §5.1's (Sec51.lean). Every cell runs at ACK: the line runs in
hand5-publish and directed7p.

`next_to_send`, `filter_entry`, `with_owed`, `rarest` and `projected`, line for line. §7.1's window
(`acquire_slot`, `release_unused_slot`, `track_in_flight`, and `wake_front` for a writer in line that writes an
urgent entry or owed offers alone, v0.10.7) and §5.2's `unpush` are the twin's own (Sec71.lean, Sec52.lean); §4.1's `pop_owed_answer` is a call on the tape; `peer_has`, `pushed` and `holders` are the twin's
own tables, read through Readers.lean. Python's meanings kept on purpose:
- `and` short-circuits: `CANCEL and peer_has[p][g].has(i)` reads `peer_has` only with the card on, and
  `PROJECT and not entry.solicited and projected(p, g)` calls projected only for an unsolicited chunk;
- `while True` is one turn at a time (`turn`), at most a bound of turns, taken from the reads the first turn
  makes anyway: twice the normal lane's length and the owed answers' count, and two;
- the entry in hand is a value: popped from its lane (which is written whole), changed (its chunk dropped, its
  IWANTs' ids filtered, IHAVEs added after its messages) and returned;
- `list(owed[p])`'s order is the node's, and an entry's IHAVEs go in that order;
- rarest's `inf` is `none`, and the earliest of the least wins, as `<` keeps the first;
- a read of a row's presence where the Python's scan reads it (`if owed[p]`, `list(owed[p])`), so that no read of
  the Python's is left unmade.

The functions reach the block's tables through `Tables` and in no other way. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- What `next_to_send` returns: an entry to write, `None` (nothing to send), or `WAIT` (in line for a slot). -/
inductive Next where
  | entry (e : QEntry)
  | nothing
  | wait
  deriving BEq, Repr, Inhabited

/-- `projected(p, g)` [c12]: p reaches K without another push of ours: what it holds, plus FAN_IN times what we
sent it and it has not confirmed -/
def projected (p : Peer) (g : Group) : M m Bool := do
  enter "projected"
  let c := (← read).c
  let has ← peerHas p g                                     -- `has, sent = peer_has[p][g].bits, sent_to[p][g]`
  let sent ← sentToBits p g
  let k ← K (← desc g)                                      -- `K(desc[g])`: §1's K
  let r := has.popcount + c.FAN_IN * (sent.minus has).popcount ≥ k
  branch (if r then "projected: K reached without us" else "projected: not yet")
  return r

/-- `rarest(q)` [c9]: the position, in the normal lane, of the chunk the fewest of our peers hold, among the
chunks ahead of the first control-only entry; the earliest wins ties. The lane is the one its caller read. -/
def rarest (normal : List QEntry) : M m Nat := do
  enter "rarest"
  let mut best : Option Nat := none                         -- `best, best_i = inf, 0`
  let mut bestI := 0
  let mut i := 0
  for e in normal do                                        -- `for i, entry in enumerate(q.normal):`
    match e.chunk with
    | none => break                                         -- never overtake a control-only entry
    | some f =>
      let h ← holders f.g f.i                               -- `len(holders[g][i])`
      if best.all (h < ·) then                              -- `if h < best:` (inf: always)
        best := some h
        bestI := i
    i := i + 1
  return bestI

/-- `rarest(queue[p])` called alone (v2's choose calls protocol.md's rarest): the lane read, as the Python's
`q.normal` reads it, then rarest -/
def rarestOf (p : Peer) : M m Nat := do
  rarest ((← lane? p .normal).getD [])

/-- `with_owed(p, entry)`: what is owed to p rides along, one IHAVE per group, minus what we pushed p since and
what p has claimed -/
def withOwed (p : Peer) (entry : QEntry) : M m (Option QEntry) := do
  enter "with_owed"
  let _ ← owedRow? p                                        -- `for g in list(owed[p]):` the row read whole, its
  let row ← allOwed p                                       --   presence too, in the node's order
  let mut e := entry
  for g in ← owedOrder p (row.map (·.1)) do
    let b0 ← match ← owed? p g with                         -- `b = owed[p].pop(g) & ~pushed[p][g] & ~peer_has[p][g].bits`
      | some b => pure b
      | none => crash "KeyError: owed[p].pop(g) (with_owed)"
    eraseOwed p g
    let b1 := b0.minus (← pushed p g)
    let mut b := b1.minus (← peerHas p g)
    if let some f := e.chunk then                           -- `if entry.chunk and entry.chunk.group == g:`
      if f.g == g then b := b.clear f.i
    if b != 0 then e := e.addIhave g b                      -- `if b: entry.add_ihave(HaveBitmap(group=g, bits=b))`
  return if e.isEmpty then none else some e

/-- `filter_entry(p, entry)` [c8, c12], and stale asks: what of the entry still goes -/
def filterEntry (p : Peer) (entry : QEntry) : M m (Option QEntry) := do
  enter "filter_entry"
  let c := (← read).c
  let mut e := entry
  if let some f := entry.chunk then
    let mut cancel := false
    if c.CANCEL then cancel := (← peerHas p f.g).has f.i    -- `if CANCEL and peer_has[p][f.group].has(f.index)`
    if cancel then
      e := { e with chunk := none }                         -- [c8] it became a duplicate
      branch "filter_entry: cancelled"
    else
      let mut skip := false
      if c.PROJECT && !entry.solicited then skip ← projected p f.g   -- `elif PROJECT and not entry.solicited and
      if skip then                                                    --   projected(p, f.group)`
        e := { e with chunk := none }                       -- [c12]
        unpush p f.g f.i                                    -- [c3] not made: offered instead (§5.2)
        branch "filter_entry: projected away"
      else
        setSentTo p f.g ((← sentToBits p f.g).set f.i)     -- `sent_to[p][f.group].set(f.index)`
        branch "filter_entry: sent"
  -- `for c in entry.iwants():` the asker drops asks for chunks it now holds, no longer pulls, of a group past its
  -- lifetime, and asks to a peer whose copy waits; the promise starts at the write [c5]
  match e.control with
  | none => pure ()
  | some cs =>
    let mut out : List Ctl := []
    for m in cs do
      match m with
      | .iwant ids =>
        let mut kept : List Key := []
        for a in ids do                                     -- `not held(a) and not gated(a) and not expired(group(a))
          if ← held a then continue                         --   and not tied_to_root(p, a)`, in that order
          if ← gated a then continue
          if ← expired a.group then continue
          if ← tiedToRoot p a then continue
          kept := kept ++ [a]
        for a in kept do
          if (← promise? a p).isNone then                   -- `if (a, p) not in promises:`
            setPromise a p (← read).now                     --   `promises[(a, p)] = now`
            after c.PROMISE (.promiseDue a p (← read).now)  --   `after(PROMISE, promise_due, a, p, now)`
        out := out ++ [.iwant kept]
      | m => out := out ++ [m]
    e := { e with control := some out }
  return if e.isEmpty then none else some e                 -- control rides on and survives

/-- One turn of `next_to_send`'s `while True`: its outcome, or a turn more, with the bound taken from what this
turn read (the normal lane's length and the owed answers' count) -/
inductive Turn where
  | done (r : Next)
  | again (bound : Nat)

/-- One turn of `next_to_send(p)` -/
def turn (p : Peer) : M m Turn := do
  let c := (← read).c
  -- `if owed_answers[p] and has_room(p):` an answer a full queue refused (§4.1)
  let oa ← allOwedAnswers p
  if !oa.isEmpty then
    if ← hasRoom p then
      let f ← popOwedAnswer p                               -- `enqueue(p, Entry(chunk=pop_owed_answer(p),
      let _ ← enqueue p (.entry { chunk := some f, control := none, solicited := true }) false   -- solicited=True))`
  -- `if q.urgent: return with_owed(p, q.urgent.pop(0))`: HAVEs, acks, decode claims first
  match (← lane? p .urgent).getD [] with
  | e :: rest =>
    -- `if p in waiters: wake_front(past=p)`: a writer in line writes one, whose write may not complete (§7.3): the
    -- next may take a slot
    if (← waitersLine .line).contains p then wakeFront (some p)
    setLane p .urgent rest                                  -- `q.urgent.pop(0)`
    return .done (match ← withOwed p e with | some e => .entry e | none => .nothing)
  | [] => pure ()
  let normal := (← lane? p .normal).getD []
  let bound := 2 * (normal.length + oa.foldl (fun n (_, b) => n + b.popcount) 0) + 2
  if normal.isEmpty then                                    -- `if not q.normal:`
    let _ ← owedRow? p                                      -- `out = with_owed(p, Entry()) if owed[p] else None`
    let owed ← allOwed p
    let out ← if owed.isEmpty then pure none else withOwed p QEntry.blank
    if out.isSome then                                      -- `if out: if p in waiters: wake_front(past=p)`: as for
      if (← waitersLine .line).contains p then wakeFront (some p)  --   an urgent entry
    if let some o := out then
      branch "next_to_send: owed offers alone"
      return .done (.entry o)
    releaseUnusedSlot p                                     -- nothing to send: a held slot goes back
    branch "next_to_send: nothing"
    return .done .nothing
  -- `if q.has_chunks() and not slot_held[p]:`
  if normal.any (·.chunk.isSome) then
    if !(← slotHeld? p) then
      if !(← acquireSlot p) then                            -- [c14] in line, FIFO over peers
        branch "next_to_send: in line"
        return .done .wait
      setSlotHeld p true
      return .again bound
  let k ← if c.RAREST then rarest normal else pure 0       -- `entry = q.normal.pop(rarest(q) if RAREST else 0)`
  let entry ← match normal[k]? with
    | some e => pure e
    | none => crash "IndexError: pop index out of range (next_to_send)"
  setLane p .normal (normal.eraseIdx k)
  let out ← filterEntry p entry                             -- [c8, c12], and stale asks
  if !(out.any (·.chunk.isSome)) then releaseUnusedSlot p   -- no chunk leaves: the slot goes back
  match out with
  | some o =>
    if let some f := o.chunk then
      trackInFlight p f                                     -- [c14] the slot is used
      setSlotHeld p false
      if (← read).c.SOURCE_OFFERS_PUBLISH then originWritten f   -- [P4] the source's HAVE (§5.1)
    branch (if o.chunk.isSome then "next_to_send: a chunk" else "next_to_send: control")
    return .done (match ← withOwed p o with | some e => .entry e | none => .nothing)   -- owed offers ride along
  | none =>
    branch "next_to_send: nothing left of the entry, again"
    return .again bound                                     -- start again from the urgent lane

/-- The turns after the first, at most `fuel` -/
def turns (p : Peer) : Nat → M m Next
  | 0 => crash "RecursionError: next_to_send (more turns than W5's bound)"
  | fuel + 1 => do
    match ← turn p with
    | .done r => return r
    | .again _ => turns p fuel

/-- `next_to_send(p)`: an entry to write, nothing, or WAIT -/
def nextToSend (p : Peer) : M m Next := do
  enter "next_to_send"
  match ← turn p with
  | .done r => return r
  | .again bound => turns p bound

end SpecTwin
