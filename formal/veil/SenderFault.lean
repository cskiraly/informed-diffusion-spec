module

public import Veil

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- the longer traces need more than the solver's 60 s on a loaded machine
set_option veil.smt.timeout 300
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails: with the slot,
-- lean-smt could not rebuild the solver's proofs of the invariant's conditions in Veil v4.35.0
set_option veil.solver "grind+smt"

/-! # The sender's fault: A1's other penalties, for any number of nodes, blocks and groups

SEACAST, `protocol.md` v0.5 with the live window and the group's key (§1, §8.1, added after v0.6),
and v0.10's two checks: level 1 checks the slot a copy names against its block's (§3), and an
IHAVE's bitmap is held to a HAVE's limits (§4.4, §8.2). Besides the claim rule (`ClaimWins.lean`),
a node penalises a peer for three things: a chunk that fails level 1 (§3, §4.2: "level 1 failures
are the sender's"), a malformed HAVE (§4.3, §8.2: a bitmap longer than `MAX_HAVE_BYTES`, or naming
an index at or beyond N once the descriptor is known), and an IHAVE's bitmap malformed in the same
way (§4.4). §3 argues that the first is always the sender's fault: every node runs level 1 before
it claims, forwards or serves a chunk, and a chunk is checked against the block it names. This
model proves that none of the three penalties ever falls on an honest node, for every number of
nodes, blocks, slots, groups, indices and pieces, every interleaving, any loss and reordering of
messages, with forgers that send anything, a builder that commits an inconsistent code or an
invalid descriptor, and a proposer that signs several blocks for a slot, whose bids may commit the
same group or different ones.

- **The world.** A block is named by its root, so what it commits is the same at every node:
  `commits r g` (its bid commits the descriptor whose key, at the block's slot, is `g`; §1), and
  its slot, `slotOf r t`. A chunk names a root, a slot and a group, and carries a piece: its index,
  the descriptor (design A), the proof and the data. `good g x` says that piece `x` is the
  committed one of `g` at its index, of the right length: what level 1 checks once the block is
  installed (§3), besides the block's checks (that the bid commits the group, and since v0.10 that
  the slot the chunk names is the block's). `inRange g i` is "i < N" for
  `g`'s committed descriptor, `inBound i` "i < 8192", the most a HAVE bitmap holds (§2, §8.2).
  `consistent g`: the committed leaves form a codeword. The proof rests on two assumptions about
  this world: level 1 checks the index against N, so a good piece is in range; and a group with any
  good piece has a descriptor that passed `valid_descriptor`, so its N is at most 8192 (§1; that an
  honest builder's descriptor passes it is `../wire/`'s W1). Twelve more keep the traces below to
  worlds that can happen: a piece names one index; the indices below N, below a forged
  descriptor's N and below 8192 start at zero; `sameSlot` is reflexive and symmetric; a block's bid
  commits one group, and some group; every block whose bid commits a group is of one slot, since
  the key fixes the slot (§1, §8.1); a block has one slot, and some slot; and two blocks of one slot
  have the same `slotOf`. The proof does not need them (it was checked without them too).
- **Honest nodes.** A node installs blocks; publishes a group of a block it installed whose bid
  commits it, storing every committed piece, each naming that block and its slot (§5.1); stores a
  chunk that passes level 1 against the block it names, as it came, and defers one whose block is
  not installed, checking it when the block installs (§4.2); claims at its decode (§4.6); rebuilds a
  chunk only once level 2 has passed, naming a block whose bid commits the group, and that block's
  slot (§4.6: "the source's chunk, byte for byte"); sends any chunk it stores, to any peer, at any
  time (forwarding, answers, repair and the source's pushes, §4.1, §4.6, §5); sends a HAVE bit for
  any index in `mine`, which grows by the chunks that passed level 1 and the decode claim's N bits
  (§4.2, §4.6, §5.1; the source's paced HAVE names a subset); and announces, as an IHAVE bit, any
  index in `mine` or of a chunk it stores (what it can serve: §4.2's forwarding, §5.1, §5.4's join,
  §6.4's gossip). A HAVE or IHAVE bit stands for a bitmap's bit: a bitmap is penalised when any of
  its bits is. That covers the length check because an honest bitmap drops its trailing zero bytes
  (§2), so its length is set by its highest bit; a longer encoding is not modelled. An IHAVE entry
  that is a chunk's id is not a bitmap and is never penalised (§4.4), so it is not modelled.
- **Messages** are sets: any order, any loss, duplicates ignored. Expiry, the live window, a group
  past `MAX_PENDING_GROUPS`, a refused deferral and a closed connection only drop messages or state
  (`dropChunk`, `dropHave`, `dropIhave`, `dropDeferred`, `expire`).
- **The penalties.** Level 1 fails at an installed block, the slot the chunk names being another
  than the block's among its reasons: the sender is penalised (§3, §4.2, at arrival and when its
  block installs). A HAVE bit, or an IHAVE's bitmap bit, at or beyond 8192, or at or beyond N where
  the receiver knows the descriptor: the sender is penalised (§4.3, §4.4).

The rules the argument rests on are switches, `immutable` Booleans, each on in the spec; the
invariant holds where `premises`, all of them on. The known answers below are `sat trace`s, at
least one per rule turned off, each with an honest node penalised. v0.10's two checks add no rule
of their own: they are penalties, which the rules already keep off honest nodes. An honest node
sends a chunk as level 1 passed it, its slot included (`gateLevel1`), and announces only what it
can serve (`gateLevel1` again, with a known answer of its own).

Not modelled: the bytes (`good` stands for every check of §3 but the block's), timing, the window,
claims and asks (`ClaimWins.lean`), and the coding lemma (that level 2 passes at every node or at
none, §4.6): level 2's root check alone makes a rebuilt piece the committed one, and that is all
this property needs. No model check: the proof covers every size, and the traces the cases. -/

veil module SenderFault

-- Veil v4.35.0's solver needs more than `veil module`'s 500,000 heartbeats on some conditions
set_option maxHeartbeats 2000000

type node
type root                                    -- a beacon block, by its root
type slot
type group                                   -- a group, by its key (§1)
type index
type piece                                   -- what a chunk carries: index, descriptor, proof, data
instantiate ord : TotalOrder index
open TotalOrder

immutable relation honest (n : node) : Bool
-- the world, the same at every node: a root names one block, and its bid one descriptor
immutable relation commits (r : root) (g : group) : Bool       -- r's bid commits g, at r's slot
immutable relation sameSlot (r : root) (s : root) : Bool       -- two blocks of one slot
immutable relation slotOf (r : root) (t : slot) : Bool          -- r's slot
immutable relation pieceAt (x : piece) (i : index) : Bool      -- the index a piece names
immutable relation good (g : group) (x : piece) : Bool         -- level 1's checks but the block's
immutable relation inRange (g : group) (i : index) : Bool      -- i < N of g's committed descriptor
immutable relation inBound (i : index) : Bool                  -- i < 8192: MAX_HAVE_BYTES (§2)
immutable relation forgedRange (g : group) (i : index) : Bool  -- i < N of a forger's descriptor for g
immutable relation consistent (g : group) : Bool               -- the committed leaves are a codeword

immutable individual gateLevel1 : Bool       -- §3: level 1 before a chunk is stored, forwarded or served
immutable individual gateLevel2 : Bool       -- §3, §4.6: a rebuilt chunk only once level 2 has passed
immutable individual deferUnknown : Bool     -- §3, §4.2: a chunk whose block is not installed waits
immutable individual namedRoot : Bool        -- §3: level 1 checks the block the chunk names
immutable individual rebuiltRoot : Bool      -- §4.6: a rebuilt chunk names a block that commits its group
immutable individual claimValidated : Bool   -- §4.2: a HAVE names chunks that passed level 1
immutable individual descCommitted : Bool    -- §3, §8.2: a HAVE is judged by the committed descriptor

-- a node's state; a chunk names a root and a slot
relation installed (n : node) (r : root) : Bool
relation stored (n : node) (r : root) (t : slot) (g : group) (x : piece) : Bool   -- a chunk it holds
relation mine (n : node) (g : group) (i : index) : Bool        -- what its HAVE may name
relation knows (n : node) (g : group) : Bool                   -- it holds the committed descriptor
relation knowsForged (n : node) (g : group) : Bool             -- it took a forger's descriptor
relation deferred (n : node) (q : node) (r : root) (t : slot) (g : group) (x : piece) : Bool   -- from q
relation penalised (b : node) (a : node) : Bool
-- messages
relation msg (a : node) (b : node) (r : root) (t : slot) (g : group) (x : piece) : Bool
relation haveMsg (a : node) (b : node) (g : group) (i : index) : Bool    -- a bit of a HAVE bitmap
relation ihaveMsg (a : node) (b : node) (g : group) (i : index) : Bool   -- a bit of an IHAVE's bitmap
-- history only, for the non-vacuity queries below: no action reads them
relation everAccepted (b : node) (a : node) (r : root) (g : group) : Bool
relation everResumed (n : node) (r : root) : Bool
relation everBadHave (b : node) (a : node) (g : group) (i : index) : Bool    -- a HAVE bit penalised
relation everBadIhave (b : node) (a : node) (g : group) (i : index) : Bool   -- an IHAVE bit penalised
relation everBadSlot (b : node) (a : node) : Bool    -- level 1 failed on the slot alone

#gen_state

-- what the proof rests on: level 1 checks the index against N (§3), so a good piece is in range;
-- a group with a piece that passes level 1 has a descriptor that passed `valid_descriptor` (§1),
-- so N is at most 8192
assumption [good_in_range] good G X → pieceAt X I → inRange G I
assumption [valid_bound] good G X → inRange G J → inBound J
-- what keeps the traces to worlds that can happen: a piece names one index; indices below N, below
-- a forged descriptor's N and below 8192 start at zero; a block's bid commits one group, every
-- block's bid commits some group, and every block whose bid commits a group is of one slot, since
-- the key fixes it (§1, §8.1); a block has one slot, and some slot, and two blocks of one slot have
-- the same
assumption [one_index] pieceAt X I → pieceAt X J → I = J
assumption [range_from_zero] inRange G I → le J I → inRange G J
assumption [forged_from_zero] forgedRange G I → le J I → forgedRange G J
assumption [bound_from_zero] inBound I → le J I → inBound J
assumption [one_group_per_block] commits R G → commits R H → G = H
assumption [every_block_commits] ∃ G, commits R G
assumption [same_slot_refl] R = S → sameSlot R S
assumption [same_slot_symm] sameSlot R S → sameSlot S R
assumption [key_fixes_slot] commits R G → commits S G → sameSlot R S
assumption [one_slot_per_block] slotOf R T → slotOf R U → T = U
assumption [every_block_has_slot] ∃ T, slotOf R T
assumption [same_slot_slot] sameSlot R S → slotOf R T → slotOf S T

theory ghost relation premises :=
  gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧ descCommitted

after_init {
  installed N R := false
  stored N R T G X := false
  mine N G I := false
  knows N G := false
  knowsForged N G := false
  deferred N Q R T G X := false
  penalised B A := false
  msg A B R T G X := false
  haveMsg A B G I := false
  ihaveMsg A B G I := false
  everAccepted B A R G := false
  everResumed N R := false
  everBadHave B A G I := false
  everBadIhave B A G I := false
  everBadSlot B A := false
}

-- a block installs (validated and applied locally); several blocks of one slot may
action install (n : node) (r : root) {
  installed n r := true
}

-- §5.1: the source publishes a group of a block it installed whose bid commits it, holding every
-- committed piece, each naming the block and its slot; its descriptor passes `valid_descriptor`
-- (`../wire/`, W1)
action publish (n : node) (r : root) (g : group) {
  require honest n
  require installed n r ∧ commits r g ∧ consistent g
  require (∃ J, inRange g J) ∧ ∀ J, inRange g J → inBound J
  stored n r T g X := stored n r T g X || (good g X && slotOf r T)
  mine n g I := mine n g I || inRange g I
  knows n g := true
}

-- §4.1, §4.6, §5: an honest node sends a chunk it stores, as it stores it: a push, an answer, a
-- repair push
action send (n p : node) (r : root) (t : slot) (g : group) (x : piece) {
  require honest n ∧ n ≠ p
  require stored n r t g x
  msg n p r t g x := true
}

-- §3, §4.2: a chunk arrives and level 1 runs, against the block the chunk names (or, with namedRoot
-- off, against a block of the same slot the receiver picks): the bid commits the group, the slot the
-- chunk names is the block's (since v0.10), and the piece is the committed one; ahead of its block
-- the chunk is deferred
action receive (b a : node) (r s : root) (t : slot) (g : group) (x : piece) (i : index) {
  require honest b
  require msg a b r t g x
  require pieceAt x i
  require (namedRoot ∧ s = r) ∨ (¬ namedRoot ∧ sameSlot r s)
  msg a b r t g x := false
  if installed b s then
    if commits s g ∧ slotOf s t ∧ good g x then
      stored b r t g x := true
      mine b g i := true
      knows b g := true
      everAccepted b a r g := true
    else
      penalised b a := true
      if commits s g ∧ good g x then
        everBadSlot b a := true
  else
    if deferUnknown then
      deferred b a r t g x := true
    else
      penalised b a := true
}

-- §4.2: the block installs and level 1 resumes on the chunks deferred for it
action resume (n q : node) (r : root) (t : slot) (g : group) (x : piece) (i : index) {
  require honest n
  require deferred n q r t g x
  require pieceAt x i
  require installed n r
  deferred n q r t g x := false
  if commits r g ∧ slotOf r t ∧ good g x then
    stored n r t g x := true
    mine n g i := true
    knows n g := true
    everResumed n r := true
  else
    penalised n q := true
}

-- §4.6: the decode claim, all N bits, by a node that holds chunks of the group (at K, in the spec)
action claimDecode (n : node) (g : group) {
  require honest n
  require ∃ r t x, stored n r t g x
  mine n g I := mine n g I || inRange g I
  knows n g := true
}

-- §4.6: a rebuilt chunk is stored, for an index the node has not received, once level 2 has passed
-- (the rebuilt tree has the committed root, so each rebuilt piece is the committed one), naming a
-- block of the group's slot whose bid commits the group (with rebuiltRoot off, any block of that
-- slot the node installed), and that block's slot, as the source built the chunk. Without the gate
-- an inconsistent code's re-encoding can differ from the committed piece; a consistent one's cannot
action rebuild (n : node) (r : root) (t : slot) (g : group) (x : piece) (i : index) {
  require honest n
  require installed n r ∧ slotOf r t
  require pieceAt x i ∧ inRange g i
  require ∃ r1 t1 y, stored n r1 t1 g y ∧ sameSlot r1 r
  require ∀ r1 t1 y, stored n r1 t1 g y → ¬ pieceAt y i
  require ¬ rebuiltRoot ∨ commits r g
  require ¬ gateLevel2 ∨ (consistent g ∧ good g x)
  require ¬ consistent g ∨ good g x
  stored n r t g x := true
}

-- design B: the bid carries the descriptor, known once the block installs
action learnDesc (n : node) (r : root) (g : group) {
  require installed n r ∧ commits r g
  knows n g := true
}

-- §4.2, §4.6, §5.1: a HAVE bit, for any index in mine, to any peer, at any time
action sendHave (n p : node) (g : group) (i : index) {
  require honest n ∧ n ≠ p
  require mine n g i
  haveMsg n p g i := true
}

-- §4.3, §8.2: the receiver checks the bitmap's length, and its indices against N once known
action handleHave (b a : node) (g : group) (i : index) {
  require honest b
  require haveMsg a b g i
  haveMsg a b g i := false
  if ¬ inBound i ∨ (knows b g ∧ ¬ inRange g i) ∨ (knowsForged b g ∧ ¬ forgedRange g i) then
    penalised b a := true
    everBadHave b a g i := true
}

-- §4.4 (since v0.10): an IHAVE's bitmap bit, for what the node can serve: any index in mine, or of
-- a chunk it stores; to any peer, at any time (forwarding's announcements, the source's, a join's,
-- heartbeat gossip)
action sendIhave (n p : node) (g : group) (i : index) {
  require honest n ∧ n ≠ p
  require mine n g i ∨ ∃ r t x, stored n r t g x ∧ pieceAt x i
  ihaveMsg n p g i := true
}

-- §4.4, §8.2: an IHAVE's bitmap is held to a HAVE's limits: its length, and its indices against N
-- once known
action handleIhave (b a : node) (g : group) (i : index) {
  require honest b
  require ihaveMsg a b g i
  ihaveMsg a b g i := false
  if ¬ inBound i ∨ (knows b g ∧ ¬ inRange g i) ∨ (knowsForged b g ∧ ¬ forgedRange g i) then
    penalised b a := true
    everBadIhave b a g i := true
}

-- a forger sends anything
action forgeChunk (a b : node) (r : root) (t : slot) (g : group) (x : piece) {
  require ¬ honest a ∧ a ≠ b
  msg a b r t g x := true
}

action forgeHave (a b : node) (g : group) (i : index) {
  require ¬ honest a ∧ a ≠ b
  haveMsg a b g i := true
}

action forgeIhave (a b : node) (g : group) (i : index) {
  require ¬ honest a ∧ a ≠ b
  ihaveMsg a b g i := true
}

-- loss, duplicates, expiry, the live window, the limits of §8.2, a refused deferral, a closed
-- connection: messages and state go
action dropChunk (a b : node) (r : root) (t : slot) (g : group) (x : piece) {
  msg a b r t g x := false
}

action dropHave (a b : node) (g : group) (i : index) {
  haveMsg a b g i := false
}

action dropIhave (a b : node) (g : group) (i : index) {
  ihaveMsg a b g i := false
}

action dropDeferred (n q : node) (r : root) (t : slot) (g : group) (x : piece) {
  deferred n q r t g x := false
}

action expire (n : node) (g : group) {
  stored n R T g X := false
  mine n g I := false
  knows n g := false
  knowsForged n g := false
  deferred n Q R T g X := false
}

-- with gateLevel1 off: a node passes a chunk on before level 1 has run
action relayUnchecked (n p a : node) (r : root) (t : slot) (g : group) (x : piece) {
  require ¬ gateLevel1
  require honest n ∧ n ≠ p
  require msg a n r t g x
  msg n p r t g x := true
}

-- with gateLevel1 off: a node announces a chunk before level 1 has run, as one it can serve
action announceUnchecked (n p a : node) (r : root) (t : slot) (g : group) (x : piece) (i : index) {
  require ¬ gateLevel1
  require honest n ∧ n ≠ p
  require msg a n r t g x
  require pieceAt x i
  ihaveMsg n p g i := true
}

-- with claimValidated off: a node announces a chunk on arrival, before level 1 (as stock IDONTWANT
-- does an id)
action claimOnArrival (n p a : node) (r : root) (t : slot) (g : group) (x : piece) (i : index) {
  require ¬ claimValidated
  require honest n ∧ n ≠ p
  require msg a n r t g x
  require pieceAt x i
  haveMsg n p g i := true
}

-- with descCommitted off: a node takes the descriptor a forger's chunk carries without checking it
-- against the bid (design A)
action openForged (b a : node) (r : root) (t : slot) (g : group) (x : piece) {
  require ¬ descCommitted
  require honest b ∧ ¬ honest a
  require msg a b r t g x
  knowsForged b g := true
}

safety [sender_fault] premises → honest A ∧ honest B → ¬ penalised B A

-- every chunk an honest node stores, sends or has sent to it passes level 1 at any node that has its
-- block, which is the same block everywhere, of the same slot
invariant [stored_valid] premises → stored N R T G X → commits R G ∧ slotOf R T ∧ good G X
invariant [sent_valid] premises → honest A → msg A B R T G X → commits R G ∧ slotOf R T ∧ good G X
invariant [deferred_valid] premises → honest Q → deferred N Q R T G X →
  commits R G ∧ slotOf R T ∧ good G X
-- every HAVE or IHAVE bit an honest node holds or has sent is below N and 8192
invariant [mine_in_range] premises → mine N G I → inRange G I ∧ inBound I
invariant [have_in_range] premises → honest A → haveMsg A B G I → inRange G I ∧ inBound I
invariant [ihave_in_range] premises → honest A → ihaveMsg A B G I → inRange G I ∧ inBound I
invariant [no_forged_desc] premises → ¬ knowsForged N G
-- only honest nodes hold state
invariant [stored_honest] stored N R T G X → honest N
invariant [mine_honest] mine N G I → honest N

#gen_spec

/-! ## Non-vacuity: with every rule on, the cases the rules exist for happen -/

sat trace [premises_hold] {
  assert (premises ∧ ∃ A B F, honest A ∧ honest B ∧ A ≠ B ∧ ¬ honest F)
}

-- a forger's chunk fails level 1 and the forger is penalised
sat trace [forged_chunk_penalised] {
  forgeChunk
  install
  receive
  assert (premises ∧ ∃ B A, honest B ∧ ¬ honest A ∧ penalised B A)
}

-- a forger's HAVE names an index beyond N, and the forger is penalised
sat trace [forged_have_penalised] {
  install
  learnDesc
  forgeHave
  handleHave
  assert (premises ∧ ∃ B A G I, honest B ∧ ¬ honest A ∧ everBadHave B A G I ∧ knows B G ∧
    inBound I ∧ ¬ inRange G I)
}

-- since v0.10: a forger's IHAVE bitmap names an index beyond N, and the forger is penalised
sat trace [forged_ihave_penalised] {
  install
  learnDesc
  forgeIhave
  handleIhave
  assert (premises ∧ ∃ B A G I, honest B ∧ ¬ honest A ∧ everBadIhave B A G I ∧ knows B G ∧
    inBound I ∧ ¬ inRange G I)
}

-- since v0.10: a forger's copy of a committed piece, under a block whose bid commits the group but
-- naming a slot that is not the block's, fails level 1 on the slot alone, and the forger is
-- penalised
sat trace [forged_slot_penalised] {
  install
  forgeChunk
  receive
  assert (premises ∧ ∃ B A, honest B ∧ ¬ honest A ∧ everBadSlot B A)
}

-- a chunk that arrives ahead of its block waits, and passes level 1 when the block installs
sat trace [deferred_then_accepted] {
  install
  publish
  send
  receive
  install
  resume
  assert (premises ∧ ∃ N R, honest N ∧ everResumed N R)
}

-- equivocation: two blocks of one slot whose bids commit the same group; one node accepts chunks
-- naming each
sat trace [two_blocks_one_group] {
  install
  install
  publish
  publish
  send
  send
  install
  install
  receive
  receive
  assert (premises ∧ ∃ B A R S G, R ≠ S ∧ sameSlot R S ∧ honest A ∧
    everAccepted B A R G ∧ everAccepted B A S G)
}

-- equivocation: two blocks of one slot whose bids commit different groups; one node accepts chunks
-- of each
sat trace [two_blocks_two_groups] {
  install
  install
  publish
  publish
  send
  send
  install
  install
  receive
  receive
  assert (premises ∧ ∃ B A R S G H, R ≠ S ∧ G ≠ H ∧ sameSlot R S ∧ honest A ∧
    everAccepted B A R G ∧ everAccepted B A S H)
}

-- a builder's inconsistent code: its authentic pieces pass level 1 and are relayed between honest
-- nodes, unpenalised
sat trace [inconsistent_relayed] {
  forgeChunk
  install
  receive
  send
  install
  receive
  assert (premises ∧ ∃ B A R G, honest A ∧ honest B ∧ ¬ consistent G ∧ everAccepted B A R G)
}

/-! ## Known answers: with any one rule off, every other on, an honest node is penalised -/

-- a chunk relayed before level 1: the honest relay is penalised for a forger's chunk
sat trace [ka_relay_unchecked] {
  forgeChunk
  relayUnchecked
  install
  receive
  assert (¬ gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧
    descCommitted ∧ ∃ B A, honest A ∧ honest B ∧ penalised B A)
}

-- an IHAVE for a chunk before level 1: the honest announcer names a forger's index beyond N, and is
-- penalised (since v0.10, an IHAVE's bitmap is held to a HAVE's limits)
sat trace [ka_announce_unchecked] {
  install
  publish
  forgeChunk
  announceUnchecked
  handleIhave
  assert (¬ gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧
    descCommitted ∧ ∃ B A G I, honest A ∧ honest B ∧ everBadIhave B A G I ∧ knows B G ∧
    inBound I ∧ ¬ inRange G I)
}

-- a rebuilt chunk sent before level 2: an inconsistent code's re-encoding fails level 1 downstream
sat trace [ka_rebuilt_unchecked] {
  forgeChunk
  install
  receive
  rebuild
  send
  install
  receive
  assert (gateLevel1 ∧ ¬ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧
    descCommitted ∧ ∃ B A, honest A ∧ honest B ∧ penalised B A)
}

-- a chunk rejected because its block is not installed yet
sat trace [ka_reject_ahead_of_block] {
  install
  publish
  send
  receive
  assert (gateLevel1 ∧ gateLevel2 ∧ ¬ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧
    descCommitted ∧ ∃ B A, honest A ∧ honest B ∧ penalised B A)
}

-- level 1 against the receiver's own block of the slot: the other block's chunks fail
sat trace [ka_check_own_block] {
  install
  publish
  send
  install
  receive
  assert (gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ ¬ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧
    descCommitted ∧ ∃ B A, honest A ∧ honest B ∧ penalised B A)
}

-- a rebuilt chunk that names a block whose bid commits another group
sat trace [ka_rebuilt_other_block] {
  install
  publish
  send
  install
  receive
  install
  rebuild
  send
  install
  receive
  assert (gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ ¬ rebuiltRoot ∧ claimValidated ∧
    descCommitted ∧ ∃ B A, honest A ∧ honest B ∧ penalised B A)
}

-- a HAVE for a chunk on arrival, before level 1: a forger's index beyond N is announced
sat trace [ka_claim_on_arrival] {
  install
  publish
  forgeChunk
  claimOnArrival
  handleHave
  assert (gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ ¬ claimValidated ∧
    descCommitted ∧ ∃ B A G I, honest A ∧ honest B ∧ everBadHave B A G I ∧ knows B G ∧
    inBound I ∧ ¬ inRange G I)
}

-- a HAVE judged by a forger's descriptor, taken from a chunk without the bid's check
sat trace [ka_forged_descriptor] {
  install
  publish
  forgeChunk
  openForged
  sendHave
  handleHave
  assert (gateLevel1 ∧ gateLevel2 ∧ deferUnknown ∧ namedRoot ∧ rebuiltRoot ∧ claimValidated ∧
    ¬ descCommitted ∧ ∃ B A G I J, honest A ∧ honest B ∧ everBadHave B A G I ∧ inRange G I ∧
    ¬ forgedRange G I ∧ forgedRange G J)
}

/-! ## The proof: the clauses above are an inductive invariant

The SMT solver's answers are not trusted: lean-smt rebuilds a proof of each from cvc5's, and Lean's
kernel checks it. -/

#check_invariants

-- each proof as a theorem in the environment, which Lean's kernel checks as it adds it
#gen_theorems

-- the audit, every failure a build error: the verification conditions, derived from the module
-- itself (the initializer and each action, against `doesNotThrow` and each safety and invariant
-- clause), are all theorems; no clause is trusted instead of checked (the assumptions, about the
-- world, are listed); and every theorem in the module rests on Lean's own axioms only
open Lean Elab Command in
#eval show CommandElabM Unit from do
  let mod ← Veil.getCurrentModule
  let env ← getEnv
  let allowed := [``propext, ``Classical.choice, ``Quot.sound]
  let acts := mod.procedures.toList.filterMap fun p => match p.info with
    | .initializer => some "initializer"
    | .action n _ => some n.toString
    | .procedure _ => none
  let mut cls := ["doesNotThrow"]
  let mut assumed : List String := []
  for a in mod.assertions do
    match a.kind with
    | .safety | .invariant => cls := cls ++ [a.name.toString]
    | .assumption => assumed := assumed ++ [a.name.toString]
    | _ => logError m!"{a.name} is trusted, not checked"
  logInfo m!"actions {acts}; clauses {cls}; assumptions about the world {assumed}"
  let mut vcs : Nat := 0
  for act in acts do
    for cl in cls do
      let n := Name.mkStr `SenderFault s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `SenderFault && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in SenderFault, resting on {rest.toList}"

end SenderFault
