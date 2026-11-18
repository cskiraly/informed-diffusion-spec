module

public import Veil
public import QuietRanking

-- the SMT solver's unsat answers are not trusted: lean-smt rebuilds each proof for Lean's kernel
set_option veil.smt.trust false
-- Lean's grind first (kernel-checked as it is), the SMT solver where grind fails
set_option veil.solver "grind+smt"

/-- Q3's per-step facts (as `NoStallTransport.lean`'s): Veil's reduction
of a one-step temporal goal to first-order form, the enum axioms' distinctness as inequalities, then
Lean's `grind`, which the kernel checks. `veil_solve_temporal` ends in the SMT solver instead, whose
translation or proof reconstruction fails on most of these goals in Veil v4.35.0. -/
macro "fv_step" : tactic => `(tactic| (
  unveil_temporal
  (try veil_cases_type* Or)
  all_goals (
    (try veil_destruct only [And, Exists])
    veil_fol !
    (try simp only [distinctN_pairwise_neq, List.nodup_cons, List.mem_cons, List.not_mem_nil, or_false,
      not_or, List.nodup_nil, and_true] at *)
    grind)))
-- the longer traces need more than the solver's 60 s on a loaded machine
set_option veil.smt.timeout 300

/-! # No stall, the transport part, with malicious peers, for any number of nodes

`NoStallTransport.lean` with adversaries. The adversaries (`adv`, any
set of nodes but the source) are part of the environment: they send an authentic copy of the chunk
if they hold it, at any time and to anyone (a push or an answer); they announce it whether they
hold it or not; they claim it whether they hold it or not (a HAVE: which only keeps honest nodes
from pushing it to them or announcing it to them, and counts among a forwarder's holders); and
they join and leave honest nodes' meshes and close their connections, as the environment already
lets every node. A copy that is not the committed piece fails level 1, and one that names a root
that never installs waits for good; either has an id of its own (§2: the id covers the content), so
it neither takes the place of an authentic copy nor makes one look seen, and changes nothing here.
Their own pending events are not work: "nothing left to do" is about honest nodes (what they have
to forward, queued, in flight to them, deferred with their block installed, due to repair). The
result: **when no honest node has anything left to do, an honest node that has its block holds
every chunk an honest mesh neighbour received, or has stopped pulling, or holds that neighbour's
offer of it**, whatever the adversaries did.

The rest of this header is `NoStallTransport.lean`'s.

SEACAST, `protocol.md` v0.7 (§3, §4.2, §4.4, §4.6, §5, §7.2, §8.1), with F9's rule, §5.4 since v0.8:
**when the transport has nothing left to do, a node that has its block holds every chunk a mesh
neighbour received, or has stopped pulling the group, or holds that neighbour's offer of the
chunk**, which the asking part (`NoStallAsk.lean`) then resolves. The chunk is any one chunk of the
group, so the result holds for each; the mesh is the one the quiet state has, however it changed.

The transport, as the spec writes it: the source publishes, pushing or announcing the chunk to each
mesh peer (§5.1); a node that stores the chunk forwards it to each mesh peer that is neither its
sender nor known to hold it, pushed (counted) or announced, any targets (§4.2, §5.2, §5.3); a queue
may refuse any entry (the group's other traffic can fill it), and a refused push or announcement is
owed and offered (A′); the writer cancels a push the peer has claimed, may skip any push by
projection, which is then uncounted and offered (A′), and sends what is owed, minus what it pushed
the peer and what the peer claimed (§7.2); an announcement is recorded as an offer unless the chunk
is claimed (§4.4); a chunk ahead of its block is deferred, or refused by the store and then its
sender's offer, and dropped if a copy already waits (§4.2); a deferred copy is taken in when the block
installs; a decoded node's repair may push the chunk to mesh peers that have not claimed it (§4.6).

The rest of the protocol is the **environment**, events at any time and any number of times, not in
`work`: a node's block installs; a node stops pulling the group (its decode claim, which takes the
block); a stopped node's decode stores the chunk and makes its repair due; a node learns that a peer
claims the chunk (a HAVE: true, possibly never sent); an answer brings the chunk to a node with its
block from a node that holds it (the asking part); and the mesh changes: a peer joins a node's mesh
(a GRAFT, sent or accepted), leaves it (a PRUNE) or loses its connection, which takes with it what
is queued, owed or in flight on it and the state kept per connection (§8.1). The mesh is directed,
as gossipsub's is: `mesh n m` is "m is in n's mesh", the peers n forwards to; it starts empty, so
every mesh is reached by joins. What is proved is about the states in which the transport is done,
in whatever mesh they have.

F9's rule (§5.4 since v0.8), as a switch with two known answers: a peer that joins a node's mesh is
announced what the node holds of each live group, as `announce` sends it (minus what the node pushed
it and what it claimed; a full queue owes it, A′). Without it nothing guarantees that a reconnection
is offered again what the old connection lost (F9), or that a peer that joins the mesh after the
chunk was forwarded is offered it: offers come from announcements, which follow a chunk's arrival.
Heartbeat gossip may announce the chunk on a connection before it joins the mesh, and a later copy
may be forwarded, but neither need happen (the gossip goes to a sample of peers outside the mesh,
for three heartbeats); the model leaves both out, so its known answers show the missing guarantee.

A rule since v0.7, as a switch with a known answer: every announcement is recorded, an IHAVE over
the receiver's IHAVE limits too, and what the receiver would ask in reply waits for the next
heartbeat (§4.4, §6.4; the asking part's `offerHeldBack`). The known answer is F11: up to v0.6, §8.2
let a receiver ignore IHAVEs beyond `MAX_IHAVE_MESSAGES` (4096) IHAVE-bearing RPCs per peer and
heartbeat, shared by all groups, and `MAX_IHAVE_LENGTH` ids each; a peer announces one chunk per
IHAVE, so a plain group of more chunks than that (up to 8192) announced within a heartbeat could
exceed it, and nothing guarantees an ignored announcement is offered again (the announcer does not
learn of the drop, and repeats an announcement only when an offer of it is owed or when it forwards
a copy received after rebuilding the chunk). Also assumed: §8.2's limits admit the one group
modelled, so a copy the deferred store refuses counts as its sender's offer (`admitted`).

Equivocation (`NoStallEquiv.lean`, F6) needs nothing more here, given that every honest copy names
the builder's block, rebuilt ones included (assumed: v0.7's §4.6 let a rebuilt chunk name either
installed block whose bid commits the group, and one naming the other block waits for good at a
node with only the builder's; since v0.8 it names the block the chunks it was rebuilt from name). `installed` is the builder's block, so a node that installed the
proposer's other block is a node without its block: its copies wait, and it forwards nothing of the
group until it switches. With `ROOT_TIED` a copy the store refuses ties its sender instead of being
its offer at once, and the builder's block's installation turns the tie into the offer
`refusedAsOffer` records; before that block the offers here are the asking part's ledger, or its
offers once the other block opened its gate.

Not modelled here: what is asked and answered (the asking part), traffic outside the mesh (heartbeat
gossip, §6.4, and the source's stripes, §5.1), lifetimes; the send window, assumed to let every
queue drain (W2, W3). -/

veil module NoStallTransportAdv

-- the long traces' simplification needs more than the depth `veil module` sets (1024)
set_option maxRecDepth 8192
-- and this model's `#gen_spec` more than the heartbeats it sets (500000)
set_option maxHeartbeats 2000000

type node
-- a queued push or announcement, an owed offer, and a chunk or announcement in flight, from a to b
enum pk = { qPush, qIhave, owedOffer, fChunk, fIhave }

immutable relation source (n : node) : Bool
-- the adversaries
immutable relation adv (n : node) : Bool

immutable individual offerSkipped : Bool     -- A′ (§5.2, §7.2): a skipped push is uncounted and offered
immutable individual oweRefused : Bool       -- A′ (§5.2, §8.2): a refused push or announcement is owed
immutable individual refusedAsOffer : Bool   -- §4.2: a copy the deferred store refuses is an offer
-- §4.4 (v0.7): every announcement is recorded, an IHAVE over the receiver's IHAVE limits too (up to
-- v0.6 the receiver ignored those for the rest of the heartbeat)
immutable individual ihaveHandled : Bool
-- §5.4 (v0.8), F9's rule: a peer that joins the mesh is announced what the node holds
immutable individual resyncOnJoin : Bool

relation mesh (n : node) (m : node) : Bool    -- m is in n's mesh: n forwards to m
individual published : Bool
relation installed (n : node) : Bool
relation stop (n : node) : Bool               -- stopped pulling the group (its decode claim)
relation rcv (n : node) : Bool                -- received the chunk (or published it): forwards it
relation holds (n : node) : Bool              -- holds the chunk: received or rebuilt
relation peerHas (m : node) (n : node) : Bool       -- m knows that n claims the chunk
relation pushed (m : node) (n : node) : Bool        -- m counts a push of the chunk to n
relation pendingFwd (m : node) (n : node) : Bool    -- m's forwarding of the chunk to n, due
relation fwdFrom (m : node) (n : node) : Bool       -- m's first copy came from n
relation repairDue (m : node) (n : node) : Bool
relation pipe (k : pk) (a : node) (b : node) : Bool
relation pend (n : node) (m : node) : Bool          -- n's deferred store holds m's copy
relation offered (n : node) (m : node) : Bool       -- m offered the chunk to n
-- history only, for the non-vacuity queries below: no action reads them
relation everDeferred (n : node) : Bool
relation everRefused (n : node) : Bool
relation everResynced (n : node) (m : node) : Bool   -- n announced its holding to m as m joined
relation lostPush (n : node) (m : node) : Bool       -- a close lost n's queued push to m
relation everAdvOffered (n : node) : Bool            -- n recorded an adversary's announcement

#gen_state

assumption [one_source] source N → source M → N = M
assumption [honest_source] source N → ¬ adv N

theory ghost relation premises :=
  offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin

-- the transport's actions' enabling conditions, each its action's only `require`
ghost relation en_publish (s : node) := source s ∧ ¬ published
ghost relation en_fwd (m : node) (n : node) := pendingFwd m n
ghost relation en_writePush (m : node) (n : node) := pipe qPush m n
ghost relation en_writeIhave (m : node) (n : node) := pipe qIhave m n
ghost relation en_writeOwed (m : node) (n : node) := pipe owedOffer m n
ghost relation en_recvChunk (n : node) (m : node) := pipe fChunk m n
ghost relation en_resume (n : node) (m : node) := installed n ∧ pend n m
ghost relation en_recvIhave (n : node) (m : node) := pipe fIhave m n
ghost relation en_repair (m : node) (n : node) := repairDue m n

-- an honest node's transport has something to do: the event is at an honest node (its forwarding,
-- its queue, a message it receives, its deferred copies, its repair); an adversary's is not work
ghost relation work :=
  (∃ S, en_publish S) ∨ (∃ M N, ¬ adv M ∧ en_fwd M N) ∨ (∃ M N, ¬ adv M ∧ en_writePush M N) ∨
  (∃ M N, ¬ adv M ∧ en_writeIhave M N) ∨ (∃ M N, ¬ adv M ∧ en_writeOwed M N) ∨
  (∃ N M, ¬ adv N ∧ en_recvChunk N M) ∨ (∃ N M, ¬ adv N ∧ en_resume N M) ∨
  (∃ N M, ¬ adv N ∧ en_recvIhave N M) ∨ (∃ M N, ¬ adv M ∧ en_repair M N)

-- for the known answers: a quiet state in which a node with its block lacks a chunk a mesh
-- neighbour received, has not stopped, and holds no offer of it from that neighbour
ghost relation undelivered :=
  ¬ work ∧ ∃ M N, ¬ adv M ∧ ¬ adv N ∧ installed N ∧ rcv M ∧ mesh M N ∧ ¬ holds N ∧ ¬ stop N ∧
    ¬ offered N M

-- Q3 with malicious peers: the honest transport's ranking
-- (`NoStallTransport.lean`), every node's elements counted, adversaries' too. Ten levels, highest
-- first, each a relation on pairs of nodes: the unpublished source; nodes that have not received the
-- chunk; forwarding due; repair due; queued pushes; queued announcements; owed offers; chunks in
-- flight; deferred copies; announcements in flight. A step of the transport, any node's, gains
-- nothing at any level down to its own and loses an element there; one of the environment, an
-- adversary's copy or announcement among them, may raise it.
ghost relation lv0 (_m : node) (_n : node) := ¬ published
ghost relation lv1 (m : node) (_n : node) := ¬ rcv m
ghost relation lv2 (m : node) (n : node) := pendingFwd m n
ghost relation lv3 (m : node) (n : node) := repairDue m n
ghost relation lv4 (m : node) (n : node) := pipe qPush m n
ghost relation lv5 (m : node) (n : node) := pipe qIhave m n
ghost relation lv6 (m : node) (n : node) := pipe owedOffer m n
ghost relation lv7 (m : node) (n : node) := pipe fChunk m n
ghost relation lv8 (m : node) (n : node) := pend m n
ghost relation lv9 (m : node) (n : node) := pipe fIhave m n
-- the two cases of `recvChunk` and of `resume`
ghost relation cRecv (n : node) := installed n ∧ ¬ rcv n
ghost relation cResume (n : node) := ¬ rcv n
-- an honest node: the transport's fairness is assumed for its steps
ghost relation hon (n : node) := ¬ adv n

after_init {
  mesh N M := false
  published := false
  installed N := false
  stop N := false
  rcv N := false
  holds N := false
  peerHas M N := false
  pushed M N := false
  pendingFwd M N := false
  fwdFrom M N := false
  repairDue M N := false
  pipe K A B := false
  pend N M := false
  offered N M := false
  everDeferred N := false
  everRefused N := false
  everResynced N M := false
  lostPush N M := false
  everAdvOffered N := false
}

/-! ## The environment -/

-- §3: n's block installs (its deferred copies are then taken in, by `resume`)
action install (n : node) {
  require ¬ installed n
  installed n := true
}

-- §4.6: n's decode claim, which takes the block
action stopPull (n : node) {
  require installed n
  stop n := true
}

-- §4.6: a stopped node's decode stores the chunk; repair may push it to mesh peers that have not
-- claimed it, if the node did not receive it
action rebuild (n : node) {
  require stop n
  holds n := true
  repairDue n Q := mesh n Q && !rcv n && !peerHas n Q
}

-- §4.3: m learns from n's HAVE that n claims the chunk: true of an honest node, anything of an
-- adversary
action learnClaim (m n : node) {
  require holds n ∨ stop n ∨ adv n
  peerHas m n := true
}

-- an adversary that holds the chunk sends n an authentic copy, at any time
action advChunk (a n : node) {
  require adv a ∧ a ≠ n ∧ holds a
  pipe fChunk a n := true
}

-- an adversary announces the chunk to n, whether it holds it or not
action advIhave (a n : node) {
  require adv a ∧ a ≠ n
  pipe fIhave a n := true
}

-- §4.5, §6.3: an answer brings the chunk to n, which has its block, from q, which holds it: stored,
-- its offers go, claimed (a HAVE: the environment) and forwarded
action answerArrives (n q : node) {
  require installed n ∧ holds q ∧ ¬ rcv n
  holds n := true
  rcv n := true
  fwdFrom n q := true
  offered n Q := false
  pendingFwd n Q := mesh n Q && !peerHas n Q
}

-- the mesh changes (stock gossipsub: GRAFT, PRUNE, the heartbeat's upkeep). m joins n's mesh, by n's
-- GRAFT or by m's that n accepts; with F9's rule, n announces what it holds to m, as `announce` does
-- (§5.2): minus what it pushed m and what m claimed, owed if a full queue refuses it (A′)
action join (n m : node) (full : Bool) {
  require n ≠ m ∧ ¬ mesh n m
  mesh n m := true
  if resyncOnJoin ∧ holds n ∧ ¬ pushed n m ∧ ¬ peerHas n m then
    everResynced n m := true
    if full then
      if oweRefused then
        pipe owedOffer n m := true
    else
      pipe qIhave n m := true
}

-- m leaves n's mesh (a PRUNE, sent or received): the connection stays, and what is on it
action leave (n m : node) {
  require mesh n m
  mesh n m := false
}

-- §8.1: the connection between n and m closes (a reconnection is a new connection, in the mesh again
-- only once a peer joins it): each leaves the other's mesh; what is queued, owed or in flight on it is
-- lost, both ways, and so is the forwarding and repair still due to the other, whose entries the
-- queue would have held; the state kept per connection goes: claims, counted pushes, offers. A
-- deferred copy stays: the deferred store is kept per block root, not per connection
action close (n m : node) {
  require n ≠ m
  if pipe qPush n m then
    lostPush n m := true
  if pipe qPush m n then
    lostPush m n := true
  mesh n m := false
  mesh m n := false
  pipe K n m := false
  pipe K m n := false
  pendingFwd n m := false
  pendingFwd m n := false
  repairDue n m := false
  repairDue m n := false
  peerHas n m := false
  peerHas m n := false
  pushed n m := false
  pushed m n := false
  offered n m := false
  offered m n := false
}

/-! ## The transport -/

-- §5.1: the source holds the chunk, has claimed the group and pulls nothing; the chunk is pushed or
-- announced to each mesh peer, as forwarding does
action publish (s : node) {
  require en_publish s
  published := true
  installed s := true
  stop s := true
  rcv s := true
  holds s := true
  pendingFwd s Q := mesh s Q
}

-- §5.2, §5.3: m forwards the chunk to n: pushed (counted) or announced, minus what it pushed n and
-- what n claimed; refused by a full queue, owed instead (A′); never to the copy's sender
action fwd (m n : node) (pushIt full : Bool) {
  require en_fwd m n
  pendingFwd m n := false
  if ¬ fwdFrom m n then
    if pushIt then
      if full then
        if oweRefused then
          pipe owedOffer m n := true
      else
        pipe qPush m n := true
        pushed m n := true
    else
      if ¬ pushed m n ∧ ¬ peerHas m n then
        if full then
          if oweRefused then
            pipe owedOffer m n := true
        else
          pipe qIhave m n := true
}

-- §7.2: a queued push: cancelled if n has claimed the chunk; skipped by projection, then uncounted
-- and offered if n is still in m's mesh (A′, §5.2's `unpush`); else sent
action writePush (m n : node) (projected : Bool) {
  require en_writePush m n
  pipe qPush m n := false
  if ¬ peerHas m n then
    if projected then
      if offerSkipped then
        pushed m n := false
        if mesh m n then
          pipe owedOffer m n := true
    else
      pipe fChunk m n := true
}

action writeIhave (m n : node) {
  require en_writeIhave m n
  pipe qIhave m n := false
  pipe fIhave m n := true
}

-- §7.2: what is owed leaves with the next write, minus what m pushed n and what n claimed
action writeOwed (m n : node) {
  require en_writeOwed m n
  pipe owedOffer m n := false
  if ¬ pushed m n ∧ ¬ peerHas m n then
    pipe fIhave m n := true
}

-- §4.2: the chunk arrives at n from m. With the block: a first copy is stored, its offers go, it is
-- claimed (a HAVE: the environment) and forwarded; a second copy is acknowledged (the environment).
-- Ahead of the block: dropped if a copy already waits, else deferred, or refused by the store and then
-- m's offer
action recvChunk (n m : node) (kept : Bool) {
  require en_recvChunk n m
  pipe fChunk m n := false
  if installed n then
    if ¬ rcv n then
      holds n := true
      rcv n := true
      fwdFrom n m := true
      offered n Q := false
      pendingFwd n Q := mesh n Q && !peerHas n Q
  else
    if ¬ (∃ P, pend n P) then
      if kept then
        pend n m := true
        everDeferred n := true
      else
        if refusedAsOffer then
          offered n m := true
          everRefused n := true
}

-- §4.2: the block installed, a deferred copy resumes level 1, as a chunk that arrives
action resume (n m : node) {
  require en_resume n m
  pend n m := false
  if ¬ rcv n then
    holds n := true
    rcv n := true
    fwdFrom n m := true
    offered n Q := false
    pendingFwd n Q := mesh n Q && !peerHas n Q
}

-- §4.4: an announcement from m: recorded as m's offer unless n claims the chunk (what is asked is
-- the asking part's)
action recvIhave (n m : node) {
  require en_recvIhave n m
  pipe fIhave m n := false
  if ¬ holds n ∧ ¬ stop n then
    offered n m := true
    if adv m then
      everAdvOffered n := true
}

-- §4.4, §8.2 up to v0.6: without the rule, an announcement beyond the receiver's limit is ignored
action dropIhave (n m : node) {
  require en_recvIhave n m ∧ ¬ ihaveHandled
  pipe fIhave m n := false
}

-- §4.6: repair pushes the rebuilt chunk to n, or not (each mesh peer's shortfall picks)
action repair (m n : node) (pushIt full : Bool) {
  require en_repair m n
  repairDue m n := false
  if pushIt then
    if full then
      if oweRefused then
        pipe owedOffer m n := true
    else
      pipe qPush m n := true
      pushed m n := true
}

-- Q3: nothing happens (a step of time: the runs a temporal proof considers take an action at every
-- step)
action stutter { pure () }

-- when the transport is done, a node with its block holds every chunk a mesh neighbour received, has
-- stopped pulling, or holds the neighbour's offer of it
safety [delivered] premises → ¬ work → installed N → rcv M → mesh M N → ¬ adv M → ¬ adv N →
  holds N ∨ stop N ∨ offered N M

-- no node is in its own mesh
invariant [mesh_irrefl] mesh N M → N ≠ M
-- what is stored and claimed
invariant [stored] (rcv N → holds N) ∧ (holds N → rcv N ∨ stop N) ∧ (stop N → installed N) ∧
  (holds N → installed N)
invariant [claims_true] peerHas M N → holds N ∨ stop N ∨ adv N
-- what is sent, forwarded, repaired, deferred or offered is held by its sender
invariant [senders_hold] (pipe qPush M N → holds M) ∧ (pipe fChunk M N → holds M) ∧
  (pendingFwd M N → holds M) ∧ (repairDue M N → holds M) ∧ (pipe qIhave M N → holds M) ∧
  (pipe fIhave M N → holds M ∨ adv M) ∧ (pipe owedOffer M N → holds M)
invariant [others_hold] (fwdFrom N P → holds P) ∧ (pend N P → holds P) ∧
  (offered N Q → holds Q ∨ adv Q)
-- a queued push is counted
invariant [qpush_pushed] pipe qPush M N → pushed M N
-- the chain that carries a chunk across a mesh link: forwarded, then pushed or offered
invariant [delivery] premises → rcv M → mesh M N →
  holds N ∨ stop N ∨ pendingFwd M N ∨ pipe qPush M N ∨ pushed M N ∨ pipe owedOffer M N ∨
    pipe qIhave M N ∨ pipe fIhave M N ∨ offered N M ∨ peerHas M N
-- a counted push arrives, waits in the deferred store, or is refused by it and then an offer
invariant [pushed_chain] premises → pushed M N →
  holds N ∨ stop N ∨ pipe qPush M N ∨ pipe fChunk M N ∨ (∃ P, pend N P) ∨ offered N M ∨
    peerHas M N

-- Q3 with malicious peers: with finitely many nodes, the transport's actions weakly fair at every
-- honest node (an adversary's steps are not forced) and an environment that eventually stops, the
-- adversaries' copies and announcements included, the honest nodes' transport eventually has
-- nothing to do, for good. In a proof `⟨a⟩` says that a step has the effect of some execution of
-- `a`, whatever action took it; so "the environment stops" is stated as: from some point on, every
-- step that changes the state has a transport action's effect, any node's, or no environment
-- action's
temporal (only := verify) [quiet]
  ⌞ ∃ l : List node, ∀ n : node, n ∈ l ⌟ ∧
  (∀ m : node, ⌜ hon m ⌝ → (𝒲ℱ (publish m) ∧ 𝒲ℱ (fwd m · · ·) ∧ 𝒲ℱ (writePush m · ·) ∧ 𝒲ℱ (writeIhave m ·) ∧ 𝒲ℱ (writeOwed m ·) ∧ 𝒲ℱ (recvChunk m · ·) ∧ 𝒲ℱ (resume m ·) ∧ 𝒲ℱ (recvIhave m ·) ∧ 𝒲ℱ (repair m · · ·))) ∧
  ◇ □ (⟨stutter⟩ ∨ ⟨publish⟩ ∨ ⟨fwd⟩ ∨ ⟨writePush⟩ ∨ ⟨writeIhave⟩ ∨ ⟨writeOwed⟩ ∨ ⟨recvChunk⟩ ∨ ⟨resume⟩ ∨ ⟨recvIhave⟩ ∨ ⟨repair⟩ ∨ ⟨dropIhave⟩ ∨
    (¬ ⟨install⟩ ∧ ¬ ⟨stopPull⟩ ∧ ¬ ⟨rebuild⟩ ∧ ¬ ⟨learnClaim⟩ ∧ ¬ ⟨advChunk⟩ ∧ ¬ ⟨advIhave⟩ ∧ ¬ ⟨answerArrives⟩ ∧ ¬ ⟨join⟩ ∧ ¬ ⟨leave⟩ ∧ ¬ ⟨close⟩)) →
  ◇ □ ⌜ ¬ work ⌝
temporal (only := verify) [workEnabled]
  □ (⌜ work ⌝ → (∃ s, ⌜ hon s ⌝ ∧ Enabled (publish s)) ∨
    (∃ m, ∃ n, ⌜ hon m ⌝ ∧ Enabled (fwd m n true false)) ∨
    (∃ m, ∃ n, ⌜ hon m ⌝ ∧ Enabled (writePush m n false)) ∨
    (∃ m, ∃ n, ⌜ hon m ⌝ ∧ Enabled (writeIhave m n)) ∨ (∃ m, ∃ n, ⌜ hon m ⌝ ∧ Enabled (writeOwed m n)) ∨
    (∃ n, ∃ m, ⌜ hon n ⌝ ∧ Enabled (recvChunk n m true)) ∨ (∃ n, ∃ m, ⌜ hon n ⌝ ∧ Enabled (resume n m)) ∨
    (∃ n, ∃ m, ⌜ hon n ⌝ ∧ Enabled (recvIhave n m)) ∨
    (∃ m, ∃ n, ⌜ hon m ⌝ ∧ Enabled (repair m n true false)))
temporal (only := verify) [publishPre]
  ∀ a, □ (⟨publish a⟩ → ⌜ lv0 a a ⌝)
temporal (only := verify) [publishPost]
  ∀ a, □ (⟨publish a⟩ → ¬ ◯ ⌜ lv0 a a ⌝)
temporal (only := verify) [publishKeep_0]
  ∀ a, ∀ x, ∀ y, □ (⟨publish a⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [fwdPre]
  ∀ m, ∀ n, ∀ p, ∀ f, □ (⟨fwd m n p f⟩ → ⌜ lv2 m n ⌝)
temporal (only := verify) [fwdPost]
  ∀ m, ∀ n, ∀ p, ∀ f, □ (⟨fwd m n p f⟩ → ¬ ◯ ⌜ lv2 m n ⌝)
temporal (only := verify) [fwdKeep_0]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨fwd m n p f⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [fwdKeep_1]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨fwd m n p f⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [fwdKeep_2]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨fwd m n p f⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [writePushPre]
  ∀ m, ∀ n, ∀ p, □ (⟨writePush m n p⟩ → ⌜ lv4 m n ⌝)
temporal (only := verify) [writePushPost]
  ∀ m, ∀ n, ∀ p, □ (⟨writePush m n p⟩ → ¬ ◯ ⌜ lv4 m n ⌝)
temporal (only := verify) [writePushKeep_0]
  ∀ m, ∀ n, ∀ p, ∀ x, ∀ y, □ (⟨writePush m n p⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [writePushKeep_1]
  ∀ m, ∀ n, ∀ p, ∀ x, ∀ y, □ (⟨writePush m n p⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [writePushKeep_2]
  ∀ m, ∀ n, ∀ p, ∀ x, ∀ y, □ (⟨writePush m n p⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [writePushKeep_3]
  ∀ m, ∀ n, ∀ p, ∀ x, ∀ y, □ (⟨writePush m n p⟩ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [writePushKeep_4]
  ∀ m, ∀ n, ∀ p, ∀ x, ∀ y, □ (⟨writePush m n p⟩ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [writeIhavePre]
  ∀ m, ∀ n, □ (⟨writeIhave m n⟩ → ⌜ lv5 m n ⌝)
temporal (only := verify) [writeIhavePost]
  ∀ m, ∀ n, □ (⟨writeIhave m n⟩ → ¬ ◯ ⌜ lv5 m n ⌝)
temporal (only := verify) [writeIhaveKeep_0]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeIhave m n⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [writeIhaveKeep_1]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeIhave m n⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [writeIhaveKeep_2]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeIhave m n⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [writeIhaveKeep_3]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeIhave m n⟩ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [writeIhaveKeep_4]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeIhave m n⟩ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [writeIhaveKeep_5]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeIhave m n⟩ → ◯ ⌜ lv5 x y ⌝ → ⌜ lv5 x y ⌝)
temporal (only := verify) [writeOwedPre]
  ∀ m, ∀ n, □ (⟨writeOwed m n⟩ → ⌜ lv6 m n ⌝)
temporal (only := verify) [writeOwedPost]
  ∀ m, ∀ n, □ (⟨writeOwed m n⟩ → ¬ ◯ ⌜ lv6 m n ⌝)
temporal (only := verify) [writeOwedKeep_0]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [writeOwedKeep_1]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [writeOwedKeep_2]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [writeOwedKeep_3]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [writeOwedKeep_4]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [writeOwedKeep_5]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv5 x y ⌝ → ⌜ lv5 x y ⌝)
temporal (only := verify) [writeOwedKeep_6]
  ∀ m, ∀ n, ∀ x, ∀ y, □ (⟨writeOwed m n⟩ → ◯ ⌜ lv6 x y ⌝ → ⌜ lv6 x y ⌝)
temporal (only := verify) [recvChunkPre1]
  ∀ n, ∀ m, ∀ kp, □ (⟨recvChunk n m kp⟩ → ⌜ cRecv n ⌝ → ⌜ lv1 n n ⌝)
temporal (only := verify) [recvChunkPost1]
  ∀ n, ∀ m, ∀ kp, □ (⟨recvChunk n m kp⟩ → ⌜ cRecv n ⌝ → ¬ ◯ ⌜ lv1 n n ⌝)
temporal (only := verify) [recvChunkKeep1_0]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ cRecv n ⌝ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [recvChunkKeep1_1]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ cRecv n ⌝ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [recvChunkPre2]
  ∀ n, ∀ m, ∀ kp, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ⌜ lv7 m n ⌝)
temporal (only := verify) [recvChunkPost2]
  ∀ n, ∀ m, ∀ kp, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ¬ ◯ ⌜ lv7 m n ⌝)
temporal (only := verify) [recvChunkKeep2_0]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [recvChunkKeep2_1]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [recvChunkKeep2_2]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [recvChunkKeep2_3]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [recvChunkKeep2_4]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [recvChunkKeep2_5]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv5 x y ⌝ → ⌜ lv5 x y ⌝)
temporal (only := verify) [recvChunkKeep2_6]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv6 x y ⌝ → ⌜ lv6 x y ⌝)
temporal (only := verify) [recvChunkKeep2_7]
  ∀ n, ∀ m, ∀ kp, ∀ x, ∀ y, □ (⟨recvChunk n m kp⟩ → ⌜ ¬ cRecv n ⌝ → ◯ ⌜ lv7 x y ⌝ → ⌜ lv7 x y ⌝)
temporal (only := verify) [resumePre1]
  ∀ n, ∀ m, □ (⟨resume n m⟩ → ⌜ cResume n ⌝ → ⌜ lv1 n n ⌝)
temporal (only := verify) [resumePost1]
  ∀ n, ∀ m, □ (⟨resume n m⟩ → ⌜ cResume n ⌝ → ¬ ◯ ⌜ lv1 n n ⌝)
temporal (only := verify) [resumeKeep1_0]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ cResume n ⌝ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [resumeKeep1_1]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ cResume n ⌝ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [resumePre2]
  ∀ n, ∀ m, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ⌜ lv8 n m ⌝)
temporal (only := verify) [resumePost2]
  ∀ n, ∀ m, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ¬ ◯ ⌜ lv8 n m ⌝)
temporal (only := verify) [resumeKeep2_0]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [resumeKeep2_1]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [resumeKeep2_2]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [resumeKeep2_3]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [resumeKeep2_4]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [resumeKeep2_5]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv5 x y ⌝ → ⌜ lv5 x y ⌝)
temporal (only := verify) [resumeKeep2_6]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv6 x y ⌝ → ⌜ lv6 x y ⌝)
temporal (only := verify) [resumeKeep2_7]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv7 x y ⌝ → ⌜ lv7 x y ⌝)
temporal (only := verify) [resumeKeep2_8]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨resume n m⟩ → ⌜ ¬ cResume n ⌝ → ◯ ⌜ lv8 x y ⌝ → ⌜ lv8 x y ⌝)
temporal (only := verify) [recvIhavePre]
  ∀ n, ∀ m, □ (⟨recvIhave n m⟩ → ⌜ lv9 m n ⌝)
temporal (only := verify) [recvIhavePost]
  ∀ n, ∀ m, □ (⟨recvIhave n m⟩ → ¬ ◯ ⌜ lv9 m n ⌝)
temporal (only := verify) [recvIhaveKeep_0]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [recvIhaveKeep_1]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [recvIhaveKeep_2]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [recvIhaveKeep_3]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [recvIhaveKeep_4]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [recvIhaveKeep_5]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv5 x y ⌝ → ⌜ lv5 x y ⌝)
temporal (only := verify) [recvIhaveKeep_6]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv6 x y ⌝ → ⌜ lv6 x y ⌝)
temporal (only := verify) [recvIhaveKeep_7]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv7 x y ⌝ → ⌜ lv7 x y ⌝)
temporal (only := verify) [recvIhaveKeep_8]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv8 x y ⌝ → ⌜ lv8 x y ⌝)
temporal (only := verify) [recvIhaveKeep_9]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨recvIhave n m⟩ → ◯ ⌜ lv9 x y ⌝ → ⌜ lv9 x y ⌝)
temporal (only := verify) [repairPre]
  ∀ m, ∀ n, ∀ p, ∀ f, □ (⟨repair m n p f⟩ → ⌜ lv3 m n ⌝)
temporal (only := verify) [repairPost]
  ∀ m, ∀ n, ∀ p, ∀ f, □ (⟨repair m n p f⟩ → ¬ ◯ ⌜ lv3 m n ⌝)
temporal (only := verify) [repairKeep_0]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨repair m n p f⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [repairKeep_1]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨repair m n p f⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [repairKeep_2]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨repair m n p f⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [repairKeep_3]
  ∀ m, ∀ n, ∀ p, ∀ f, ∀ x, ∀ y, □ (⟨repair m n p f⟩ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [dropIhavePre]
  ∀ n, ∀ m, □ (⟨dropIhave n m⟩ → ⌜ lv9 m n ⌝)
temporal (only := verify) [dropIhavePost]
  ∀ n, ∀ m, □ (⟨dropIhave n m⟩ → ¬ ◯ ⌜ lv9 m n ⌝)
temporal (only := verify) [dropIhaveKeep_0]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv0 x y ⌝ → ⌜ lv0 x y ⌝)
temporal (only := verify) [dropIhaveKeep_1]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv1 x y ⌝ → ⌜ lv1 x y ⌝)
temporal (only := verify) [dropIhaveKeep_2]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv2 x y ⌝ → ⌜ lv2 x y ⌝)
temporal (only := verify) [dropIhaveKeep_3]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv3 x y ⌝ → ⌜ lv3 x y ⌝)
temporal (only := verify) [dropIhaveKeep_4]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv4 x y ⌝ → ⌜ lv4 x y ⌝)
temporal (only := verify) [dropIhaveKeep_5]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv5 x y ⌝ → ⌜ lv5 x y ⌝)
temporal (only := verify) [dropIhaveKeep_6]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv6 x y ⌝ → ⌜ lv6 x y ⌝)
temporal (only := verify) [dropIhaveKeep_7]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv7 x y ⌝ → ⌜ lv7 x y ⌝)
temporal (only := verify) [dropIhaveKeep_8]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv8 x y ⌝ → ⌜ lv8 x y ⌝)
temporal (only := verify) [dropIhaveKeep_9]
  ∀ n, ∀ m, ∀ x, ∀ y, □ (⟨dropIhave n m⟩ → ◯ ⌜ lv9 x y ⌝ → ⌜ lv9 x y ⌝)

#gen_spec

/-! ## Non-vacuity: with every rule on, runs reach a quiet state (the mesh starts empty: each trace
first lets a peer join the source's) -/

-- a push delivered
sat trace [push_delivered] {
  join
  publish
  install
  fwd
  writePush
  recvChunk
  assert (premises ∧ ¬ work ∧ ∃ N, holds N ∧ ¬ source N)
}

-- an announcement, recorded as an offer for the asking part
sat trace [announced_offer] {
  join
  publish
  fwd
  writeIhave
  recvIhave
  install
  assert (premises ∧ ¬ work ∧ ∃ N M, installed N ∧ offered N M ∧ ¬ holds N)
}

-- a copy ahead of the block, deferred and taken in when it installs
sat trace [deferred_taken_in] {
  join
  publish
  fwd
  writePush
  recvChunk
  install
  resume
  assert (premises ∧ ¬ work ∧ ∃ N, holds N ∧ everDeferred N)
}

-- a copy the deferred store refuses, recorded as its sender's offer
sat trace [refused_copy_offer] {
  join
  publish
  fwd
  writePush
  recvChunk
  install
  assert (premises ∧ ¬ work ∧ ∃ N M, everRefused N ∧ installed N ∧ offered N M)
}

-- F9's case: the connection closes with a push of the chunk queued; the peer joins the mesh again,
-- and the resync's announcement is recorded as an offer
sat trace [resync_after_close] {
  join
  publish
  fwd
  close
  join
  writeIhave
  recvIhave
  install
  assert (premises ∧ ¬ work ∧
    ∃ N M, installed N ∧ offered N M ∧ ¬ holds N ∧ everResynced M N ∧ lostPush M N)
}

-- a peer that joins the mesh after the publish is announced the chunk
sat trace [resync_late_join] {
  publish
  join
  writeIhave
  recvIhave
  install
  assert (premises ∧ ¬ work ∧ ∃ N M, installed N ∧ offered N M ∧ ¬ holds N ∧ everResynced M N)
}

/-! ## Known answers: with any one rule off, a node is left without the chunk and without an offer -/

-- F1: a push projection skips is still counted, and offered to nobody
sat trace [ka_skip_counted] {
  join
  publish
  install
  fwd
  writePush
  assert (¬ offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- a push a full queue refuses is lost
sat trace [ka_refused_lost] {
  join
  publish
  install
  fwd
  assert (offerSkipped ∧ ¬ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- F7: a push the deferred store refuses is lost
sat trace [ka_refused_copy_lost] {
  join
  publish
  fwd
  writePush
  recvChunk
  install
  assert (offerSkipped ∧ oweRefused ∧ ¬ refusedAsOffer ∧ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- F11: an announcement the receiver's IHAVE limit ignores is lost, and offered by nobody again
sat trace [ka_ihave_dropped] {
  join
  publish
  install
  fwd
  writeIhave
  dropIhave
  assert (offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ¬ ihaveHandled ∧ resyncOnJoin ∧ undelivered)
}

-- F9: the connection closes with a push of the chunk queued, the peer joins the mesh again, and
-- nothing offers it the chunk
sat trace [ka_rejoin_lost] {
  join
  publish
  fwd
  close
  join
  install
  assert (offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ ¬ resyncOnJoin ∧ ¬ work ∧
    ∃ M N, lostPush M N ∧ installed N ∧ rcv M ∧ mesh M N ∧ ¬ holds N ∧ ¬ stop N ∧ ¬ offered N M)
}

-- the same gap without a close: nothing offers the chunk to a peer that joins the mesh after the
-- publish
sat trace [ka_late_join] {
  publish
  join
  install
  assert (offerSkipped ∧ oweRefused ∧ refusedAsOffer ∧ ihaveHandled ∧ ¬ resyncOnJoin ∧ undelivered)
}

/-! ## Non-vacuity with adversaries -/

-- a false claim: an honest node believes an adversary holds the chunk, and the chunk still arrives
sat trace [adv_false_claim] {
  join
  publish
  install
  learnClaim
  fwd
  writePush
  recvChunk
  assert (premises ∧ ¬ work ∧ ∃ N A, ¬ adv N ∧ installed N ∧ holds N ∧ ¬ source N ∧ adv A ∧
    peerHas N A ∧ ¬ holds A)
}

-- an adversary's announcement of a chunk it does not hold, recorded: a quiet state with that offer
-- left to the asking part, where only honest offers must resolve
sat trace [adv_offer_left] {
  install
  advIhave
  recvIhave
  assert (premises ∧ ¬ work ∧ ∃ N A, ¬ adv N ∧ installed N ∧ adv A ∧ offered N A ∧ ¬ holds A ∧
    everAdvOffered N)
}

/-! ## The proof: the clauses above are an inductive invariant -/

#check_invariants

-- each proof as a theorem in the environment, which Lean's kernel checks as it adds it
#gen_theorems

/-! ## Q3 with malicious peers: the honest transport goes quiet

The ranking's facts, per own action and case: its witness element is at its level before the step
(`…Pre`) and not after (`…Post`), and no level down to its own gains an element (`…Keep_j`). Then
the proof: a list of the nodes, the ranking's counts, the steps sorted into the transport's (any
node's), the environment's (the adversaries' included) and stutters, the fair families (one
action's steps taken by one honest node), and `FvQuiet.quiet_exec`. -/

prove_temporal_by [publishPre]
  tclear hInit hInv
  tintro a
  tmonotone
  fv_step

prove_temporal_by [publishPost]
  tclear hInit hInv
  tintro a
  tmonotone
  fv_step

prove_temporal_by [publishKeep_0]
  tclear hInit hInv
  tintro a x y
  tmonotone
  fv_step

prove_temporal_by [fwdPre]
  tclear hInit hInv
  tintro m n p f
  tmonotone
  fv_step

prove_temporal_by [fwdPost]
  tclear hInit hInv
  tintro m n p f
  tmonotone
  fv_step

prove_temporal_by [fwdKeep_0]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [fwdKeep_1]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [fwdKeep_2]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [writePushPre]
  tclear hInit hInv
  tintro m n p
  tmonotone
  fv_step

prove_temporal_by [writePushPost]
  tclear hInit hInv
  tintro m n p
  tmonotone
  fv_step

prove_temporal_by [writePushKeep_0]
  tclear hInit hInv
  tintro m n p x y
  tmonotone
  fv_step

prove_temporal_by [writePushKeep_1]
  tclear hInit hInv
  tintro m n p x y
  tmonotone
  fv_step

prove_temporal_by [writePushKeep_2]
  tclear hInit hInv
  tintro m n p x y
  tmonotone
  fv_step

prove_temporal_by [writePushKeep_3]
  tclear hInit hInv
  tintro m n p x y
  tmonotone
  fv_step

prove_temporal_by [writePushKeep_4]
  tclear hInit hInv
  tintro m n p x y
  tmonotone
  fv_step

prove_temporal_by [writeIhavePre]
  tclear hInit hInv
  tintro m n
  tmonotone
  fv_step

prove_temporal_by [writeIhavePost]
  tclear hInit hInv
  tintro m n
  tmonotone
  fv_step

prove_temporal_by [writeIhaveKeep_0]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeIhaveKeep_1]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeIhaveKeep_2]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeIhaveKeep_3]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeIhaveKeep_4]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeIhaveKeep_5]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedPre]
  tclear hInit hInv
  tintro m n
  tmonotone
  fv_step

prove_temporal_by [writeOwedPost]
  tclear hInit hInv
  tintro m n
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_0]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_1]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_2]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_3]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_4]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_5]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [writeOwedKeep_6]
  tclear hInit hInv
  tintro m n x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkPre1]
  tclear hInit hInv
  tintro n m kp
  tmonotone
  fv_step

prove_temporal_by [recvChunkPost1]
  tclear hInit hInv
  tintro n m kp
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep1_0]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep1_1]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkPre2]
  tclear hInit hInv
  tintro n m kp
  tmonotone
  fv_step

prove_temporal_by [recvChunkPost2]
  tclear hInit hInv
  tintro n m kp
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_0]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_1]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_2]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_3]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_4]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_5]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_6]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [recvChunkKeep2_7]
  tclear hInit hInv
  tintro n m kp x y
  tmonotone
  fv_step

prove_temporal_by [resumePre1]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [resumePost1]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [resumeKeep1_0]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep1_1]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumePre2]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [resumePost2]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_0]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_1]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_2]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_3]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_4]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_5]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_6]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_7]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [resumeKeep2_8]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhavePre]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [recvIhavePost]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_0]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_1]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_2]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_3]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_4]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_5]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_6]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_7]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_8]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [recvIhaveKeep_9]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [repairPre]
  tclear hInit hInv
  tintro m n p f
  tmonotone
  fv_step

prove_temporal_by [repairPost]
  tclear hInit hInv
  tintro m n p f
  tmonotone
  fv_step

prove_temporal_by [repairKeep_0]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [repairKeep_1]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [repairKeep_2]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [repairKeep_3]
  tclear hInit hInv
  tintro m n p f x y
  tmonotone
  fv_step

prove_temporal_by [dropIhavePre]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [dropIhavePost]
  tclear hInit hInv
  tintro n m
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_0]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_1]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_2]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_3]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_4]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_5]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_6]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_7]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_8]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [dropIhaveKeep_9]
  tclear hInit hInv
  tintro n m x y
  tmonotone
  fv_step

prove_temporal_by [workEnabled]
  tclear hInit hNext hInv
  tmonotone
  veil_solve_temporal

prove_temporal_by [quiet]
  texit
  intro e i h hprem
  obtain ⟨hfin, hfp, henv⟩ := hprem
  obtain ⟨xs, hxs⟩ := hfin
  -- every pair of nodes, and the ranking's levels on them
  let xs2 : List (node × node) := xs.flatMap (fun a => xs.map (fun b => (a, b)))
  have hxs2 : ∀ x, x ∈ xs2 := by
    intro x; rcases x with ⟨a, b⟩; simp [xs2, hxs]
  let δ : Nat → node × node → σ → Prop := fun l x s => match l with
    | 0 => lv0 x.1 x.2 th s
    | 1 => lv1 x.1 x.2 th s
    | 2 => lv2 x.1 x.2 th s
    | 3 => lv3 x.1 x.2 th s
    | 4 => lv4 x.1 x.2 th s
    | 5 => lv5 x.1 x.2 th s
    | 6 => lv6 x.1 x.2 th s
    | 7 => lv7 x.1 x.2 th s
    | 8 => lv8 x.1 x.2 th s
    | 9 => lv9 x.1 x.2 th s
    | _ => False
  -- the transport's actions, by family (`dropIhave` last, not fair) and by the node that takes
  -- the step, its first argument, and the environment's
  let fam' : Nat → node → σ → σ → Prop := fun j w s s' => match j with
    | 0 => NoStallTransportAdv.publish.ext.tr ρ σ node pk χ w th s s'
    | 1 => ∃ n, ∃ p, ∃ f, NoStallTransportAdv.fwd.ext.tr ρ σ node pk χ w n p f th s s'
    | 2 => ∃ n, ∃ p, NoStallTransportAdv.writePush.ext.tr ρ σ node pk χ w n p th s s'
    | 3 => ∃ n, NoStallTransportAdv.writeIhave.ext.tr ρ σ node pk χ w n th s s'
    | 4 => ∃ n, NoStallTransportAdv.writeOwed.ext.tr ρ σ node pk χ w n th s s'
    | 5 => ∃ m, ∃ kp, NoStallTransportAdv.recvChunk.ext.tr ρ σ node pk χ w m kp th s s'
    | 6 => ∃ m, NoStallTransportAdv.resume.ext.tr ρ σ node pk χ w m th s s'
    | 7 => ∃ m, NoStallTransportAdv.recvIhave.ext.tr ρ σ node pk χ w m th s s'
    | 8 => ∃ n, ∃ p, ∃ f, NoStallTransportAdv.repair.ext.tr ρ σ node pk χ w n p f th s s'
    | _ => ∃ m, NoStallTransportAdv.dropIhave.ext.tr ρ σ node pk χ w m th s s'
  let own : σ → σ → Prop := fun s s' => ∃ j, ∃ w, fam' j w s s'
  let envf : Nat → σ → σ → Prop := fun j s s' => match j with
    | 0 => ∃ n, NoStallTransportAdv.install.ext.tr ρ σ node pk χ n th s s'
    | 1 => ∃ n, NoStallTransportAdv.stopPull.ext.tr ρ σ node pk χ n th s s'
    | 2 => ∃ n, NoStallTransportAdv.rebuild.ext.tr ρ σ node pk χ n th s s'
    | 3 => ∃ m, ∃ n, NoStallTransportAdv.learnClaim.ext.tr ρ σ node pk χ m n th s s'
    | 4 => ∃ a, ∃ n, NoStallTransportAdv.advChunk.ext.tr ρ σ node pk χ a n th s s'
    | 5 => ∃ a, ∃ n, NoStallTransportAdv.advIhave.ext.tr ρ σ node pk χ a n th s s'
    | 6 => ∃ n, ∃ q, NoStallTransportAdv.answerArrives.ext.tr ρ σ node pk χ n q th s s'
    | 7 => ∃ n, ∃ m, ∃ f, NoStallTransportAdv.join.ext.tr ρ σ node pk χ n m f th s s'
    | 8 => ∃ n, ∃ m, NoStallTransportAdv.leave.ext.tr ρ σ node pk χ n m th s s'
    | _ => ∃ n, ∃ m, NoStallTransportAdv.close.ext.tr ρ σ node pk χ n m th s s'
  -- a step is sorted by its effect: one with an own action's effect is own, whatever action took it;
  -- an environment step that changes nothing is a stutter
  let env : σ → σ → Prop := fun s s' => (∃ j, envf j s s') ∧ ¬ own s s' ∧ s' ≠ s
  -- the fair families: an action's instances taken by one honest node
  refine FvQuiet.quiet_exec e i own env (fun s s' => s' = s)
    (fun p : {p : Fin 9 × node // hon p.2 th (e i)} => fam' p.1.1.val p.1.2) _
    (fun s' s => LentilLib.ListLex.List.lexLt Nat.lt_wfRel
      (FvQuiet.counts xs2 δ 0 10 s') (FvQuiet.counts xs2 δ 0 10 s))
    (FvQuiet.counts_wf xs2 δ 0 10) ?hsplit ?hdec (fun s s' h => h)
    (fun p s s' h => ⟨p.1.1.val, p.1.2, h⟩) ?hwork ?hfair ?henv
  case hsplit =>
    intro k hk
    have hk' := h.2.1 (k - i)
    rw [show i + (k - i) = k by omega] at hk'
    obtain ⟨label, hl⟩ := hk'
    rcases Classical.em (e (k + 1) = e k) with hs | hs
    · exact Or.inr (Or.inr hs)
    rcases Classical.em (own (e k) (e (k + 1))) with ho | ho
    · exact Or.inl ho
    cases label with
    | publish a => exact Or.inl ⟨0, a, hl⟩
    | fwd m n p f => exact Or.inl ⟨1, m, n, p, f, hl⟩
    | writePush m n p => exact Or.inl ⟨2, m, n, p, hl⟩
    | writeIhave m n => exact Or.inl ⟨3, m, n, hl⟩
    | writeOwed m n => exact Or.inl ⟨4, m, n, hl⟩
    | recvChunk n m kp => exact Or.inl ⟨5, n, m, kp, hl⟩
    | resume n m => exact Or.inl ⟨6, n, m, hl⟩
    | recvIhave n m => exact Or.inl ⟨7, n, m, hl⟩
    | repair m n p f => exact Or.inl ⟨8, m, n, p, f, hl⟩
    | dropIhave n m => exact Or.inl ⟨9, n, m, hl⟩
    | install n => exact Or.inr (Or.inl ⟨⟨0, n, hl⟩, ho, hs⟩)
    | stopPull n => exact Or.inr (Or.inl ⟨⟨1, n, hl⟩, ho, hs⟩)
    | rebuild n => exact Or.inr (Or.inl ⟨⟨2, n, hl⟩, ho, hs⟩)
    | learnClaim m n => exact Or.inr (Or.inl ⟨⟨3, m, n, hl⟩, ho, hs⟩)
    | advChunk a n => exact Or.inr (Or.inl ⟨⟨4, a, n, hl⟩, ho, hs⟩)
    | advIhave a n => exact Or.inr (Or.inl ⟨⟨5, a, n, hl⟩, ho, hs⟩)
    | answerArrives n q => exact Or.inr (Or.inl ⟨⟨6, n, q, hl⟩, ho, hs⟩)
    | join n m f => exact Or.inr (Or.inl ⟨⟨7, n, m, f, hl⟩, ho, hs⟩)
    | leave n m => exact Or.inr (Or.inl ⟨⟨8, n, m, hl⟩, ho, hs⟩)
    | close n m => exact Or.inr (Or.inl ⟨⟨9, n, m, hl⟩, ho, hs⟩)
    | stutter => exact absurd hl.symm hs
  case hdec =>
    intro k hk hown
    obtain ⟨k', rfl⟩ : ∃ k', k = i + k' := ⟨k - i, by omega⟩
    obtain ⟨j, hj⟩ := hown
    rcases j with _ | _ | _ | _ | _ | _ | _ | _ | _ | j
    · -- publish
      obtain ⟨a, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 0 _ _ (by omega) (by omega) ?_
        ⟨(a, a), publishPre._proof th hass e i h a k' hs,
          publishPost._proof th hass e i h a k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | l
      · exact publishKeep_0._proof th hass e i h a x y k' hs hx
      · omega
    · -- fwd
      obtain ⟨m, n, p, f, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 2 _ _ (by omega) (by omega) ?_
        ⟨(m, n), fwdPre._proof th hass e i h m n p f k' hs,
          fwdPost._proof th hass e i h m n p f k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | l
      · exact fwdKeep_0._proof th hass e i h m n p f x y k' hs hx
      · exact fwdKeep_1._proof th hass e i h m n p f x y k' hs hx
      · exact fwdKeep_2._proof th hass e i h m n p f x y k' hs hx
      · omega
    · -- writePush
      obtain ⟨m, n, p, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 4 _ _ (by omega) (by omega) ?_
        ⟨(m, n), writePushPre._proof th hass e i h m n p k' hs,
          writePushPost._proof th hass e i h m n p k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | _ | _ | l
      · exact writePushKeep_0._proof th hass e i h m n p x y k' hs hx
      · exact writePushKeep_1._proof th hass e i h m n p x y k' hs hx
      · exact writePushKeep_2._proof th hass e i h m n p x y k' hs hx
      · exact writePushKeep_3._proof th hass e i h m n p x y k' hs hx
      · exact writePushKeep_4._proof th hass e i h m n p x y k' hs hx
      · omega
    · -- writeIhave
      obtain ⟨m, n, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 5 _ _ (by omega) (by omega) ?_
        ⟨(m, n), writeIhavePre._proof th hass e i h m n k' hs,
          writeIhavePost._proof th hass e i h m n k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | _ | _ | _ | l
      · exact writeIhaveKeep_0._proof th hass e i h m n x y k' hs hx
      · exact writeIhaveKeep_1._proof th hass e i h m n x y k' hs hx
      · exact writeIhaveKeep_2._proof th hass e i h m n x y k' hs hx
      · exact writeIhaveKeep_3._proof th hass e i h m n x y k' hs hx
      · exact writeIhaveKeep_4._proof th hass e i h m n x y k' hs hx
      · exact writeIhaveKeep_5._proof th hass e i h m n x y k' hs hx
      · omega
    · -- writeOwed
      obtain ⟨m, n, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 6 _ _ (by omega) (by omega) ?_
        ⟨(m, n), writeOwedPre._proof th hass e i h m n k' hs,
          writeOwedPost._proof th hass e i h m n k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | l
      · exact writeOwedKeep_0._proof th hass e i h m n x y k' hs hx
      · exact writeOwedKeep_1._proof th hass e i h m n x y k' hs hx
      · exact writeOwedKeep_2._proof th hass e i h m n x y k' hs hx
      · exact writeOwedKeep_3._proof th hass e i h m n x y k' hs hx
      · exact writeOwedKeep_4._proof th hass e i h m n x y k' hs hx
      · exact writeOwedKeep_5._proof th hass e i h m n x y k' hs hx
      · exact writeOwedKeep_6._proof th hass e i h m n x y k' hs hx
      · omega
    · -- recvChunk
      obtain ⟨n, m, kp, hs⟩ := hj
      by_cases hc : cRecv n th (e (i + k'))
      · -- level 1
        refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 1 _ _ (by omega) (by omega) ?_
          ⟨(n, n), recvChunkPre1._proof th hass e i h n m kp k' hs hc,
            recvChunkPost1._proof th hass e i h n m kp k' hs hc⟩
        intro l _ hl x hx
        rcases x with ⟨x, y⟩
        rcases l with _ | _ | l
        · exact recvChunkKeep1_0._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep1_1._proof th hass e i h n m kp x y k' hs hc hx
        · omega
      · -- level 7
        refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 7 _ _ (by omega) (by omega) ?_
          ⟨(m, n), recvChunkPre2._proof th hass e i h n m kp k' hs hc,
            recvChunkPost2._proof th hass e i h n m kp k' hs hc⟩
        intro l _ hl x hx
        rcases x with ⟨x, y⟩
        rcases l with _ | _ | _ | _ | _ | _ | _ | _ | l
        · exact recvChunkKeep2_0._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_1._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_2._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_3._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_4._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_5._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_6._proof th hass e i h n m kp x y k' hs hc hx
        · exact recvChunkKeep2_7._proof th hass e i h n m kp x y k' hs hc hx
        · omega
    · -- resume
      obtain ⟨n, m, hs⟩ := hj
      by_cases hc : cResume n th (e (i + k'))
      · -- level 1
        refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 1 _ _ (by omega) (by omega) ?_
          ⟨(n, n), resumePre1._proof th hass e i h n m k' hs hc,
            resumePost1._proof th hass e i h n m k' hs hc⟩
        intro l _ hl x hx
        rcases x with ⟨x, y⟩
        rcases l with _ | _ | l
        · exact resumeKeep1_0._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep1_1._proof th hass e i h n m x y k' hs hc hx
        · omega
      · -- level 8
        refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 8 _ _ (by omega) (by omega) ?_
          ⟨(n, m), resumePre2._proof th hass e i h n m k' hs hc,
            resumePost2._proof th hass e i h n m k' hs hc⟩
        intro l _ hl x hx
        rcases x with ⟨x, y⟩
        rcases l with _ | _ | _ | _ | _ | _ | _ | _ | _ | l
        · exact resumeKeep2_0._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_1._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_2._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_3._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_4._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_5._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_6._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_7._proof th hass e i h n m x y k' hs hc hx
        · exact resumeKeep2_8._proof th hass e i h n m x y k' hs hc hx
        · omega
    · -- recvIhave
      obtain ⟨n, m, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 9 _ _ (by omega) (by omega) ?_
        ⟨(m, n), recvIhavePre._proof th hass e i h n m k' hs,
          recvIhavePost._proof th hass e i h n m k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | l
      · exact recvIhaveKeep_0._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_1._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_2._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_3._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_4._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_5._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_6._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_7._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_8._proof th hass e i h n m x y k' hs hx
      · exact recvIhaveKeep_9._proof th hass e i h n m x y k' hs hx
      · omega
    · -- repair
      obtain ⟨m, n, p, f, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 3 _ _ (by omega) (by omega) ?_
        ⟨(m, n), repairPre._proof th hass e i h m n p f k' hs,
          repairPost._proof th hass e i h m n p f k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | _ | l
      · exact repairKeep_0._proof th hass e i h m n p f x y k' hs hx
      · exact repairKeep_1._proof th hass e i h m n p f x y k' hs hx
      · exact repairKeep_2._proof th hass e i h m n p f x y k' hs hx
      · exact repairKeep_3._proof th hass e i h m n p f x y k' hs hx
      · omega
    · -- dropIhave
      obtain ⟨n, m, hs⟩ := hj
      refine FvQuiet.counts_dec xs2 hxs2 δ 10 0 9 _ _ (by omega) (by omega) ?_
        ⟨(m, n), dropIhavePre._proof th hass e i h n m k' hs,
          dropIhavePost._proof th hass e i h n m k' hs⟩
      intro l _ hl x hx
      rcases x with ⟨x, y⟩
      rcases l with _ | _ | _ | _ | _ | _ | _ | _ | _ | _ | l
      · exact dropIhaveKeep_0._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_1._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_2._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_3._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_4._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_5._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_6._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_7._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_8._proof th hass e i h n m x y k' hs hx
      · exact dropIhaveKeep_9._proof th hass e i h n m x y k' hs hx
      · omega
  case hwork =>
    intro k hk hw
    obtain ⟨k', rfl⟩ : ∃ k', k = i + k' := ⟨k - i, by omega⟩
    rcases workEnabled._proof th hass e i h k' hw with
      ⟨s0, hhn, s', hs'⟩ | ⟨m, n, hhn, s', hs'⟩ | ⟨m, n, hhn, s', hs'⟩ | ⟨m, n, hhn, s', hs'⟩ | ⟨m, n, hhn, s', hs'⟩ | ⟨n, m, hhn, s', hs'⟩ | ⟨n, m, hhn, s', hs'⟩ | ⟨n, m, hhn, s', hs'⟩ | ⟨m, n, hhn, s', hs'⟩
    · exact ⟨⟨(⟨0, by omega⟩, s0), hhn⟩, s', by dsimp only; exact hs'⟩
    · exact ⟨⟨(⟨1, by omega⟩, m), hhn⟩, s', by dsimp only; exact ⟨n, true, false, hs'⟩⟩
    · exact ⟨⟨(⟨2, by omega⟩, m), hhn⟩, s', by dsimp only; exact ⟨n, false, hs'⟩⟩
    · exact ⟨⟨(⟨3, by omega⟩, m), hhn⟩, s', by dsimp only; exact ⟨n, hs'⟩⟩
    · exact ⟨⟨(⟨4, by omega⟩, m), hhn⟩, s', by dsimp only; exact ⟨n, hs'⟩⟩
    · exact ⟨⟨(⟨5, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨m, true, hs'⟩⟩
    · exact ⟨⟨(⟨6, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨m, hs'⟩⟩
    · exact ⟨⟨(⟨7, by omega⟩, n), hhn⟩, s', by dsimp only; exact ⟨m, hs'⟩⟩
    · exact ⟨⟨(⟨8, by omega⟩, m), hhn⟩, s', by dsimp only; exact ⟨n, true, false, hs'⟩⟩
  case hfair =>
    intro p
    obtain ⟨⟨j, m⟩, hm⟩ := p
    obtain ⟨hw0, hw1, hw2, hw3, hw4, hw5, hw6, hw7, hw8⟩ := hfp m hm
    match j with
    | ⟨0, _⟩ => exact hw0
    | ⟨1, _⟩ => exact hw1
    | ⟨2, _⟩ => exact hw2
    | ⟨3, _⟩ => exact hw3
    | ⟨4, _⟩ => exact hw4
    | ⟨5, _⟩ => exact hw5
    | ⟨6, _⟩ => exact hw6
    | ⟨7, _⟩ => exact hw7
    | ⟨8, _⟩ => exact hw8
    | ⟨j + 9, hj⟩ => exact absurd hj (by omega)
  case henv =>
    obtain ⟨k0, hk0⟩ := henv
    refine ⟨k0, fun k ⟨⟨j, hj⟩, hno, hne⟩ => ?_⟩
    rcases hk0 k with hst | ho0 | ho1 | ho2 | ho3 | ho4 | ho5 | ho6 | ho7 | ho8 | ho9 | ⟨h0, h1, h2, h3, h4, h5, h6, h7, h8, h9⟩
    · exact hne (Eq.symm hst)
    · obtain ⟨a, hh⟩ := ho0; exact hno ⟨0, a, hh⟩
    · obtain ⟨m, n, p, f, hh⟩ := ho1; exact hno ⟨1, m, n, p, f, hh⟩
    · obtain ⟨m, n, p, hh⟩ := ho2; exact hno ⟨2, m, n, p, hh⟩
    · obtain ⟨m, n, hh⟩ := ho3; exact hno ⟨3, m, n, hh⟩
    · obtain ⟨m, n, hh⟩ := ho4; exact hno ⟨4, m, n, hh⟩
    · obtain ⟨n, m, kp, hh⟩ := ho5; exact hno ⟨5, n, m, kp, hh⟩
    · obtain ⟨n, m, hh⟩ := ho6; exact hno ⟨6, n, m, hh⟩
    · obtain ⟨n, m, hh⟩ := ho7; exact hno ⟨7, n, m, hh⟩
    · obtain ⟨m, n, p, f, hh⟩ := ho8; exact hno ⟨8, m, n, p, f, hh⟩
    · obtain ⟨n, m, hh⟩ := ho9; exact hno ⟨9, n, m, hh⟩
    rcases j with _ | _ | _ | _ | _ | _ | _ | _ | _ | j
    · obtain ⟨n, hs⟩ := hj; exact h0 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hj; exact h1 ⟨n, hs⟩
    · obtain ⟨n, hs⟩ := hj; exact h2 ⟨n, hs⟩
    · obtain ⟨m, n, hs⟩ := hj; exact h3 ⟨m, n, hs⟩
    · obtain ⟨a, n, hs⟩ := hj; exact h4 ⟨a, n, hs⟩
    · obtain ⟨a, n, hs⟩ := hj; exact h5 ⟨a, n, hs⟩
    · obtain ⟨n, q, hs⟩ := hj; exact h6 ⟨n, q, hs⟩
    · obtain ⟨n, m, f, hs⟩ := hj; exact h7 ⟨n, m, f, hs⟩
    · obtain ⟨n, m, hs⟩ := hj; exact h8 ⟨n, m, hs⟩
    · obtain ⟨n, m, hs⟩ := hj; exact h9 ⟨n, m, hs⟩


-- the audit, every failure a build error: the verification conditions, derived from the module
-- itself (the initializer and each action, against `doesNotThrow` and each safety and invariant
-- clause), are all theorems; no clause is trusted instead of checked (the assumption, that there is
-- one source, is listed); and every theorem in the module rests on Lean's own axioms only
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
  logInfo m!"actions {acts}; clauses {cls}; assumptions {assumed}"
  let mut vcs : Nat := 0
  for act in acts do
    for cl in cls do
      let n := Name.mkStr `NoStallTransportAdv s!"{act}_{cl}"
      if (env.find? n).any (·.isTheorem) then vcs := vcs + 1
      else logError m!"no theorem {n}"
  let mut thms : Nat := 0
  let mut rest : Std.HashSet Name := {}
  for (n, ci) in env.constants.map₂.toList do
    if n.getRoot == `NoStallTransportAdv && ci.isTheorem then
      thms := thms + 1
      for a in ← liftCoreM (collectAxioms n) do
        rest := rest.insert a
        unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"{vcs} of {acts.length * cls.length} verification conditions are theorems; \
    {thms} theorems in NoStallTransportAdv, resting on {rest.toList}"

end NoStallTransportAdv
