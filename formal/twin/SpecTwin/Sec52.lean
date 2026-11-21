import SpecTwin.Readers

/-! # The twin of protocol.md §5.2, "A node forwards" [c3, c7] (v0.10.4, spec 34f60f8): `announce`, `unpush`,
`owe` and `note_push`

`forward`, the section's fifth function, is in Sec54.lean.

- **`pushed` is the twin's own table:** an entry is the bits, the time of the first push and a ttl.
  A missing entry reads as no bit and joins the table at its first push (`note_push`). `unpush` of a missing entry
  leaves it missing: the toy's entry joins its map when a bit is set, or its clock or ttl is, and a cleared bit
  of nothing sets none (toy/bits.py, `PushEntry`).
- **`owed`** is the writer's (§7.2), and the twin's own: `owed[p][g] |= bits` reads the entry and writes it, also
  where the bits were owed already.
- **Calls:** `enqueue` (§7.2's admission, the node's) and `wake` (the node's writer). `p in mesh` is a question
  (`meshHas`).
- **The time** of a first push is the call's `now`, kept as its 64 bits, as a record writes it. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `owe(p, g, bits)` (§5.2): an offer that must not be lost: the next write to p carries it (§7.2) -/
def owe (p : Peer) (g : Group) (bits : Bits) : M m Unit := do
  enter "owe"
  setOwed p g (((← owed? p g).getD 0) ||| bits)             -- `owed[p][g] |= bits`
  wake p

/-- `note_push(p, g, i)` (§5.2) -/
def notePush (p : Peer) (g : Group) (i : Nat) : M m Unit := do
  enter "note_push"
  let e := (← pushedEntry? p g).getD {}                     -- `e = pushed[p][g]`: created at the first push
  let now := (← read).now.toBits
  let first := if e.bits == 0 then some now else e.firstPush   -- `if e.empty(): e.first_push = now`: the guard's
                                                            --   clock (§5.3)
  -- `e.set(i); e.ttl = PUSH_TTL`: heartbeats
  setPushed p g { bits := e.bits.set i, firstPush := first, ttl := (← read).c.PUSH_TTL }
  branch (if e.bits == 0 then "note_push: the first push" else "note_push: a later push")

/-- `unpush(p, g, i)` (§5.2) [c3]: a chosen push that will not be made: not counted (the guard's clock
stays), offered instead -/
def unpush (p : Peer) (g : Group) (i : Nat) : M m Unit := do
  enter "unpush"
  match ← pushedEntry? p g with                             -- `pushed[p][g].clear(i)`
  | some e => setPushed p g { e with bits := e.bits.clear i }
  | none => branch "unpush: nothing pushed"                 -- a missing entry stays missing
  if ← meshHas p then                                       -- `if p in mesh: owe(p, g, bitmap({i}))`
    owe p g (1 <<< i)
    branch "unpush: in the mesh, owed"
  else
    branch "unpush: not in the mesh"

/-- `announce(p, g, bits)` (§5.2) [c3, c7] -/
def announce (p : Peer) (g : Group) (bits : Bits) : M m Unit := do
  enter "announce"
  -- `b = bits & ~pushed[p][g] & ~peer_has[p][g].bits`
  let b := (bits.minus (← pushed p g)).minus (← peerHas p g)
  if b == 0 then                                            -- an empty bitmap is not sent
    branch "announce: nothing to offer"
  else if !(← enqueue p (.ihave g b) false) then            -- `enqueue(p, IHAVE(HaveBitmap(group=g, bits=b)), urgent=False)`
    owe p g b                                               -- refused by a full queue: owed
    branch "announce: refused, owed"
  else
    branch "announce: offered"

end SpecTwin
