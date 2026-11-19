import SpecTwin.Readers
import SpecTwin.Sec51
import SpecTwin.Sec71

/-! # The twin of protocol.md §4.3, "A HAVE arrives in an IDONTWANT" [c7] (v0.10.4, spec 34f60f8): `on_have`
(lines 660–670)

- **`peer_has` and `holders` are the twin's own tables,** since on_have writes them. `peer_has[p][g]` is an
  entry of bits and a ttl, there from p's first HAVE for g, an empty one too. The writer's reads (§7.2) are of the
  twin's state: `peerHas` and `holders` in Readers.lean.
- **The twin's own too:** `window_release` (§7.1, Sec71.lean) and `origin_acked` (§5.1, Sec51.lean).
- **`h.group in planned`** is a read of another section's table, asked once for each new index, as the Python
  evaluates it. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `on_have(p, h)` (lines 660–670): h is a HAVE's bitmap, a group and its bits -/
def onHave (p : Peer) (g : Group) (bits : Bits) : M m Unit := do
  enter "on_have"
  if ← expired g then                                       -- past its active lifetime (§8.1): ignored
    branch "on_have: expired"; return
  if !(← validHave g bits) then                             -- length, and indices within N once known (§8.2)
    penalise p
    branch "on_have: not a valid HAVE"; return
  let e := (← peerHasEntry? p g).getD {}                    -- created at p's first HAVE for the group
  let newly := bits.minus e.bits                            -- `h.bits & ~e.bits`
  -- `e.bits |= h.bits`; `e.ttl = HAVE_TTL`: heartbeats, refreshed by each HAVE from p for the group
  setPeerHas p g { bits := e.bits ||| bits, ttl := (← read).c.HAVE_TTL }
  for i in newly.toList do
    setHolders g i ((← holdersOf g i).insert p)             -- [c9] distinct live holders
    windowRelease p g i                                     -- [c14] a slot to p frees when p holds i, from anyone
    if ← planned g then originAcked g i                     -- [c3, P4] a copy of i exists elsewhere (§5.1)
  branch (if newly == 0 then "on_have: nothing new" else "on_have: new indices")

end SpecTwin
