// -*- mode: Bluespec; -*-
/**
 * The protocol of ../protocol.md, draft v0.4 (8d735e5), §4–§7 for one group: what a node does
 * when an RPC arrives (§4.1–§4.6), how it forwards (§5.2), asks (§6.1–§6.2) and sends (§7.1–§7.2),
 * and how the source publishes (§5.1). The rules v0.5 added are switches (README.md).
 *
 * One step is one event: a link delivers its oldest RPC, a writer runs once, a timer fires, a node
 * finishes decoding, the source publishes. Links are FIFO and deliver at any time; timers fire at
 * any time after they are armed, so the model has no clock and covers every timing. Where the
 * spec's rule picks among candidates (push targets, rarest at pop, the retry's least recently
 * tried, the repair's shuffle), any pick is allowed. Honest nodes send only authentic chunks; with
 * ADV_FORGE an adversary also sends forged ones. The code is consistent (level 2 passes) unless
 * BAD_CODE.
 *
 * Simplifications: one RPC is one queue entry; every connection is a mesh link; no heartbeat
 * gossip; a disconnect closes a connection and opens a new one at once; one ask timer per chunk
 * does the work of the window's end and the retry 5 ms later (§6.1); a block's deferred chunks
 * resume one per step, ahead of every other event, as on_block_installed resumes them in one. Block
 * gate, expiry, queue limits, equivocation and disconnects are switches.
 */
module diffusion {
  // ---- parameters ----
  const NN: int                  // nodes 0 .. NN−1; node 0 is the source
  const K: int                   // data chunks: any K of the N decode
  const N: int                   // chunks in the group
  const MESH: int -> Set[int]    // each node's mesh, symmetric; every connection is a mesh link
  const R: int                   // the source's push degree (§5.1)
  const R_NODE: int              // a forwarding node's push degree (§5.2)
  const W: int                   // window slots per node (§7.1)
  const OFFERS_MAX: int          // announcers kept per chunk (§8.2: 16)
  const SERVE_MAX: int           // answers per chunk and peer (GOSSIP_RETRANSMISSION: 3)
  const FAN_IN: int              // card 12's assumed number of pushers
  const CANCEL: bool             // card 8
  const PROJECT: bool            // card 12
  const RAREST: bool             // card 9
  const REPAIR: bool             // card 10's repair: a decoded node pushes what it rebuilt
  const PACED_SRC_HAVE: bool     // P4: the source's HAVE names only chunks it has sent
  const PARK: bool               // card 5's park: a broken promise parks the peer for the group
  // A candidate fix, not in the spec (false: the spec).
  const PROJECT_OFFERS: bool     // a push that projection skips is forgotten and announced instead (F1)
  const PARK_LAST_RESORT: bool   // a parked announcer is still asked when every announcer of the chunk is parked (F2)
  const PROMISE_AT_WRITE: bool   // an ask's promise starts when the ask is written, not when it is decided (F5)
  const FORGET_DROPPED: bool     // a push dropped at a full queue is forgotten too (F1 through the queue)
  const CLOSE_ON_DEFER: bool     // any copy that arrives closes the chunk's promises, and a waiting copy counts as held for asks (F3, fix C)
  const RETRY_CHECKS_EXPIRY: bool // retry_offer checks expiry (F4, fix D)
  // The fixes as revised, in v0.5 (false: left out). A′ is PROJECT_OFFERS with ADMIT_OFFERS, B′
  // LAST_RESORT with OFFERS_DURABLE (OFFER_REPLACE: its first form), C′ NO_ASK_BEFORE_INSTALL, D′
  // RETRY_CHECKS_EXPIRY with EXPIRY_CLEANUP, E PROMISE_AT_WRITE.
  const ADMIT_OFFERS: bool       // A′: what a refused push or announcement named is owed to the peer, and the next write to it
                                 // carries the offer; a refused answer is owed too, and queued once there is room
  const LAST_RESORT: bool        // B′: when every announcer of a chunk is parked, one is asked later, each at most LR_MAX times per chunk
  const LR_MAX: int              // B′'s bound per announcer and chunk (the spec text: one, at a doubling wait from PROMISE)
  const OFFER_REPLACE: bool      // in a full offer table an announcer not yet asked for the chunk replaces one already asked
                                 // (B′'s first form, superseded by OFFERS_DURABLE)
  const OFFERS_DURABLE: bool     // B′: every offer is kept, one bitmap per announcer; the per-chunk list is the order to try
  const NO_ASK_BEFORE_INSTALL: bool // C′: no ask before the block is installed; the offers recorded meanwhile are asked for at installation
  const EXPIRY_CLEANUP: bool     // D′: at expiry the group's offers, asks, promises and queued work go, and the writer drops an expired group's asks
  // Extensions of the setting (false: left out).
  const MAX_ASKS: int            // asks a node decides per chunk; finite for exhaustive checks, large otherwise
  const COALESCE: bool           // the transport merges a written entry into the RPC still on the link (at most one chunk)
  const BLOCK_GATE: bool         // chunks ahead of the block are deferred until it installs (§3, §4.2)
  const EXPIRY: bool             // a group may pass its active lifetime at any node but the source (§8.1)
  const INSTALL_LATE: bool       // with BLOCK_GATE, a node's block installs only once a chunk is waiting for it
  const EXPIRE_LATE: bool        // with EXPIRY, a group expires only while an ask of it is out or queued (random
                                 // simulation expires groups early otherwise, before anything is asked)
  const DROP_LATE: bool          // with BAD_CODE, a node decodes, and so drops the group, only while a writer of it
                                 // waits in line for a slot (the precondition of NO_WAKE_ON_LEAVE's known answer)
  // With EXPIRY, a directed case: a group expires only while it decodes. Otherwise the model assumes
  // that a decode finishes within GROUP_TTL (at least 7 heartbeats after the group's last chunk, §8.3;
  // the spec puts a decode at milliseconds but bounds it nowhere), so no group expires while it decodes
  const EXPIRE_DECODING: bool
  // A candidate addition (false: as written, decode_group does not look at expiry when it returns): a
  // decode that returns for a group past its active lifetime is dropped, so nothing of the group is
  // stored, pushed, offered or delivered again
  const DECODE_CHECKS_EXPIRY: bool
  // A known-answer switch for §4.1's handling order (false: the spec, IWANT before IDONTWANT).
  const IDONTWANT_FIRST: bool
  // Adversarial nodes: they answer nothing, forward nothing, acknowledge nothing, and send at most
  // ADV_MSGS announcements or HAVEs of their choice, each naming any chunks; with ADV_FORGE also
  // forged chunks: one that names the real block root and fails its proof, or one that names a
  // root that never installs
  const ADV: Set[int]
  const ADV_MSGS: int
  const ADV_FORGE: bool
  const FORGE_KINDS: Set[int]    // which forgeries: BAD_PROOF, BOGUS_ROOT
  // The deferred store may refuse a chunk: "nothing is remembered" (§4.2)
  const DEFER_REFUSE: bool
  // Equivocation (§3): the nodes in EQ installed the proposer's other block for the slot, whose bid
  // commits the same group. Every honest chunk names the builder's block, so at them it waits for a
  // root they have not installed; with C′ they still ask, since their block's bid commits the group.
  // With EQ_SWITCH they install the builder's block later (fork choice); with EQ_LATE only once they
  // have parked every peer, or once nothing else is left to happen; with EQ_EXHAUST (a directed case,
  // in place of EQ_LATE) only once, for a chunk the node lacks with nothing of it waiting or on its
  // way, every mesh peer has answered it SERVE_MAX times (GOSSIP_RETRANSMISSION spent before the
  // switch), or once nothing else is left to happen
  const EQ: Set[int]
  const EQ_SWITCH: bool
  const EQ_LATE: bool
  const EQ_EXHAUST: bool
  // A candidate addition to C′ for equivocation (false: left out): a block's installation lifts the
  // parks of its group and resets B′'s last-resort counts, since an answer may have waited for it
  const EQ_UNPARK: bool
  // Disconnects (§8.1): up to DISC_MAX times a connection between two honest nodes closes and a new
  // one opens at once. What is on the link is lost, per-connection state is reset (B′'s counts with
  // `tried`), the queue closes and its slots come back, parks stay; promises keep their own
  // lifetime, as written. DISC_LATE: only while one of the two has a promise open to the other.
  // DISC_AT, where the closes fall (directed cases): 0 anywhere; 1 while one side decodes; 2 once one
  // side has dropped the group; 3 a connection of the source's before it has written any chunk; 4 once
  // one side's group has expired; 5 a connection of an adversarial node's (with DISC_ADV).
  // DISC_ADV: an adversarial node's connections close too
  const DISC_MAX: int
  const DISC_LATE: bool
  const DISC_AT: int
  const DISC_ADV: bool
  // A candidate addition (false: as written): a peer's promises close with its connection
  const CLOSE_PROMISES_ON_DISC: bool
  // A candidate addition to C′ (false: as written, "refused: nothing is remembered"): a copy the
  // deferred store refuses counts as an announcement from its sender (its sender counted it as
  // pushed, and offers it to nobody): recorded, so the ledger asks it at installation, and acted on
  // at once where the node may already pull
  const REFUSE_OFFERS: bool
  // A candidate addition (false: as written): on a new connection each side announces what it can
  // serve of the group, one IHAVE bitmap: the chunks it holds, received or rebuilt, nothing of a
  // dropped or expired group (the old connection's offers, pushes and queue went with it).
  // RESYNC_MINE, a known answer: the first form, which announced the decode claim (`mine`)
  const RESYNC_ON_CONNECT: bool
  const RESYNC_MINE: bool
  // A candidate addition in place of EQ_UNPARK and REFUSE_OFFERS (false: as written), tied to the root
  // a copy names: a copy that waits for a root not installed, kept or refused, ties its sender to that
  // root for its index. The sender's promise for the index closes (it answered, with a copy that
  // cannot be checked yet), and it is not asked for the index until that root installs. At the
  // installation the root's ties are released: each sender's park for the group lifts, B′'s count for
  // it and the index clears, and it becomes an offer of the index, asked if still wanted. A root that
  // never installs keeps its ties
  const ROOT_TIED: bool
  // A candidate addition (false: as written): no announcer is asked for a chunk while an earlier ask
  // of it for the chunk is outstanding, queued or promised; a retry that skips every candidate for
  // that reason looks again a window later, and a last resort waits the same way (an announcer is
  // asked again only once its earlier answer is overdue)
  const NO_REASK_OPEN: bool
  // Eventual completion: by DONE_BY steps every run is quiet and every honest node complete (0: off;
  // the step count is then not kept, so that exhaustive checks stay finite)
  const DONE_BY: int
  // The builder committed a non-codeword: every node's level-2 check fails and it drops the group (§4.6)
  const BAD_CODE: bool
  // Entries a per-peer queue holds, both lanes together; a new entry beyond it is dropped (§8.2)
  const QMAX: int
  // A writer runs until it has nothing to send or waits for a slot, in one step, as the toy's writer
  // does when the transport takes every write at once (fewer interleavings, for exhaustive checks)
  const EAGER_WRITERS: bool
  // Switches that bring back bugs found earlier, to check that the model finds them (false: the spec).
  const LR_AT_DECISION: bool     // B′ counts a last resort when it is decided, even if the queue refuses the ask (its first form)
  const NO_ASK_FILTER: bool      // the writer keeps asks for chunks now held (a bug found in an implementation)
  const NO_WAKE_ON_TAKE: bool    // acquire_slot wakes nobody while slots remain (spec before 97be57d)
  const NO_WAKE_ON_LEAVE: bool   // release_unused_slot wakes nobody (the toy's first window, 2026-10-03)

  pure val SRC = 0
  pure val NODES = 0.to(NN - 1)
  pure val CHUNKS = 0.to(N - 1)
  pure val NONE = -1
  pure val COLLECTING = 0
  pure val DECODING = 1
  pure val COMPLETE = 2
  pure val INVALID = 3

  pure def imin(a: int, b: int): int = if (a < b) a else b
  pure def imax(a: int, b: int): int = if (a > b) a else b
  pure def toSet(l: List[int]): Set[int] = l.foldl(Set(), (acc, x) => acc.union(Set(x)))
  pure def has(l: List[int], x: int): bool = l.indices().exists(j => l[j] == x)
  pure def without(l: List[int], x: int): List[int] = l.select(y => y != x)
  pure def dropAt(l: List[Entry], k: int): List[Entry] = l.slice(0, k).concat(l.slice(k + 1, l.length()))
  // subsets of S with exactly m elements
  pure def subsetsOf(S: Set[int], m: int): Set[Set[int]] = S.powerset().filter(x => x.size() == m)

  // ---- messages ----
  // A queue entry carries at most one chunk, plus control (§7.2); a HAVE travels alone on the
  // urgent lane, in IDONTWANT (§2).
  type Entry = {
    chunk: int,          // the chunk's index, or NONE
    sol: bool,           // the chunk answers an ask
    forged: int,         // AUTHENTIC, or a forgery: BAD_PROOF (the real root), BOGUS_ROOT (a root that never installs)
    iwant: Set[int],     // asks by index (WantIndex)
    ihave: Set[int],     // an announcement's bitmap
    have: Set[int],      // a HAVE's bitmap
    isHave: bool,
  }
  pure val AUTHENTIC = 0
  pure val BAD_PROOF = 1
  pure val BOGUS_ROOT = 2
  pure val EMPTY: Entry = { chunk: NONE, sol: false, forged: AUTHENTIC, iwant: Set(), ihave: Set(), have: Set(), isHave: false }
  pure def chunkEntry(i: int, sol: bool): Entry = { ...EMPTY, chunk: i, sol: sol }
  pure def haveEntry(b: Set[int]): Entry = { ...EMPTY, have: b, isHave: true }
  pure def isEmpty(e: Entry): bool =
    e.chunk == NONE and e.iwant == Set() and e.ihave == Set() and not(e.isHave)
  pure def hasChunks(q: List[Entry]): bool = q.indices().exists(j => q[j].chunk != NONE)

  // ---- state ----
  type Node = {
    recv: Set[int],              // received from the network (received[g]); also the seen ids
    mine: Set[int],              // what this node's HAVE claims (mine[g])
    stored: Set[int],            // held: received or rebuilt
    stage: int,                  // COLLECTING, DECODING, COMPLETE
    stopPull: bool,              // §6.2
    origin: Set[int],            // the source: the chunks it has sent (P4)
    peerHas: int -> Set[int],    // what each peer said it holds (HAVEs in IDONTWANT)
    pushed: int -> Set[int],     // what this node chose to push to each peer (note_push)
    sentTo: int -> Set[int],     // what it actually sent each peer (for projection)
    served: int -> (int -> int), // answers per peer and chunk
    parked: Set[int],            // peers parked for this group
    qUrg: int -> List[Entry],    // per-peer queue, urgent lane
    qNorm: int -> List[Entry],   // per-peer queue, normal lane
    runnable: Set[int],          // peers whose writer will run: kicked, woken, or between entries
    inFlight: int,               // window slots taken
    waiters: List[int],          // writers waiting for a slot, first come first served
    slotHeld: Set[int],          // writers holding a slot they have not used yet
    sent: Set[(int, int)],       // (peer, chunk) in flight, each with its WINDOW_TIMEOUT armed
    asking: Set[int],            // chunks with an ask in flight, each with its timer armed
    offers: int -> List[int],    // announcers per chunk, in announcement order
    tried: int -> Set[int],      // peers asked per chunk
    promises: Set[(int, int)],   // (chunk, peer) promises open, each with PROMISE armed
    askCount: int -> int,        // asks decided per chunk (bounded by MAX_ASKS)
    installed: bool,             // the block carrying the bid is installed (always, without BLOCK_GATE)
    other: bool,                 // EQ: the proposer's other block is installed, its bid committing the group
    orphans: Set[(int, int)],    // (chunk, peer): a promise open when that peer's connection closed (a monitor)
    pending: Set[(int, int, int)], // deferred chunks, (sender, chunk, forged): the id is the index and the content
    seenCopy: bool,              // a chunk naming the builder's block arrived and waited, kept or refused (INSTALL_LATE's gate)
    tied: Set[(int, int, int)],  // ROOT_TIED: (sender, chunk, root): its copy of the chunk waits for that root,
                                 // AUTHENTIC for the builder's block, BOGUS_ROOT for one that never installs
    rejected: Set[(int, int)],   // (chunk, forged): ids that failed level 1, seen and never validated again
    lvl1Pen: Set[int],           // peers penalised for a chunk that failed level 1 (a monitor)
    gotFrom: Set[(int, int)],    // (peer, chunk): that peer's authentic copy arrived, deferred or not, since our last
                                 // ask of it for the chunk was written (a monitor: an earlier copy, refused or
                                 // dropped, does not excuse a later answer's lateness)
    askWritten: Set[(int, int)], // (chunk, peer): an ask for the chunk left for that peer (a monitor)
    dropped: Set[(int, int)],    // (peer, chunk): a push just dropped at a full queue, for notePush
    owed: int -> Set[int],       // A′: chunks owed to each peer as an offer (a refused push or announcement)
    offered: int -> Set[int],    // B′ (OFFERS_DURABLE): the chunks each peer offered, not yet received
    owedAns: int -> Set[int],    // A′: answers a full queue refused, per peer, queued once there is room
    lastResort: int -> (int -> int), // B′: last-resort asks made per chunk and announcer
    lrArmed: Set[int],           // B′: chunks with a last-resort timer armed
    expired: bool,               // the group is past its active lifetime: only its tombstone is left
  }
  type State = {
    nodes: int -> Node,
    links: (int, int) -> List[Entry],    // (from, to), FIFO
    published: bool,
    // monitors
    penalties: Set[(int, int, int)],     // (node, peer it penalised, chunk asked after its claim)
    badAsk: Set[(int, int, int)],        // (node, peer, chunk): an ask written for a chunk held or not pulled
    badHave: Set[(int, int)],            // (peer, chunk): the source's HAVE named a chunk it had not sent
    badPark: Set[(int, int, int)],       // (node, peer, chunk): a peer parked although its copy had arrived
    badParkSame: Set[(int, int, int)],   // the same, by a node not on the other block when it parked
    badIhave: Set[(int, int, int)],      // (node, peer, chunk): an announcement named a chunk its sender could not serve
    badExpiredAsk: Set[(int, int)],      // (node, chunk): an ask written for a group past its lifetime
    led: int -> int,                     // the source's first chunk for each peer it pushes to
    advSent: int,                        // messages the adversarial nodes have sent
    badDrop: Set[(int, int)],            // (node, peer): a chunk, IHAVE or IWANT written after drop_group
    badUnsent: Set[(int, int, int)],     // (node, peer, chunk): a peer parked for an ask it never received
    badClose: Set[(int, int, int)],      // (node, chunk, peer): that peer's promise closed by a forged copy
    discs: int,                          // connections closed so far (DISC_MAX)
    badDiscPark: Set[(int, int, int)],   // (node, peer, chunk): a peer parked for a promise its closed connection left open
    exhaustSwitch: Set[int],             // nodes on the other block that switched with a chunk's answers spent (EQ_EXHAUST)
  }
  var s: State
  var clock: int                         // steps taken, kept only with DONE_BY

  pure def emptyNode(n: int): Node = {
    recv: Set(), mine: Set(), stored: Set(), stage: COLLECTING, stopPull: false, origin: Set(),
    peerHas: NODES.mapBy(p => Set()), pushed: NODES.mapBy(p => Set()), sentTo: NODES.mapBy(p => Set()),
    served: NODES.mapBy(p => CHUNKS.mapBy(i => 0)), parked: Set(),
    qUrg: NODES.mapBy(p => List()), qNorm: NODES.mapBy(p => List()), runnable: Set(),
    inFlight: 0, waiters: List(), slotHeld: Set(), sent: Set(),
    asking: Set(), offers: CHUNKS.mapBy(i => List()), tried: CHUNKS.mapBy(i => Set()), promises: Set(),
    askCount: CHUNKS.mapBy(i => 0), installed: n == SRC or not(BLOCK_GATE or EQ.contains(n)),
    other: EQ.contains(n), orphans: Set(), pending: Set(), seenCopy: false, tied: Set(),
    rejected: Set(), lvl1Pen: Set(), gotFrom: Set(),
    askWritten: Set(), dropped: Set(), owed: NODES.mapBy(p => Set()), offered: NODES.mapBy(p => Set()),
    owedAns: NODES.mapBy(p => Set()),
    lastResort: CHUNKS.mapBy(i => NODES.mapBy(q => 0)), lrArmed: Set(),
    expired: false,
  }

  // ---- the queue and the HAVE (§4.2, §7) ----
  // A′: chunks owed to p as an offer; p's writer runs, and its next write carries them
  pure def owe(nd: Node, p: int, bits: Set[int]): Node =
    if (bits == Set()) nd
    else { ...nd, owed: nd.owed.set(p, nd.owed.get(p).union(bits)), runnable: nd.runnable.union(Set(p)) }
  pure def enqueue(nd: Node, p: int, e: Entry, urgent: bool): Node =
    if (isEmpty(e)) nd                                   // an empty response or bitmap is not sent
    else if (nd.qUrg.get(p).length() + nd.qNorm.get(p).length() >= QMAX) {   // full: dropped, urgent included
      val push = e.chunk != NONE and not(e.sol)
      // with the candidate fixes, a refused push is not counted as pushed (notePush runs after enqueue)
      val nd1 = if ((FORGET_DROPPED or ADMIT_OFFERS) and push) { ...nd, dropped: nd.dropped.union(Set((p, e.chunk))) } else nd
      // A′: what the refused entry pushed or announced is owed to p as an offer, and an answer is owed as such
      val nd2 = if (ADMIT_OFFERS and e.chunk != NONE and e.sol)
          { ...nd1, owedAns: nd1.owedAns.set(p, nd1.owedAns.get(p).union(Set(e.chunk))) } else nd1
      if (ADMIT_OFFERS) owe(nd2, p, e.ihave.union(if (push) Set(e.chunk) else Set())) else nd2
    }
    else if (urgent) { ...nd, qUrg: nd.qUrg.set(p, nd.qUrg.get(p).append(e)), runnable: nd.runnable.union(Set(p)) }
    else { ...nd, qNorm: nd.qNorm.set(p, nd.qNorm.get(p).append(e)), runnable: nd.runnable.union(Set(p)) }

  // have_bits: the source's HAVE names what it has sent [P4]; everyone else's, what it holds
  pure def haveBits(nd: Node, n: int): Set[int] = if (n == SRC and PACED_SRC_HAVE) nd.origin else nd.mine
  pure def sendHave(nd: Node, n: int, q: int): Node = enqueue(nd, q, haveEntry(haveBits(nd, n)), true)

  pure def announce(nd: Node, q: int, bits: Set[int]): Node = {
    val b = bits.exclude(nd.pushed.get(q)).exclude(nd.peerHas.get(q))
    if (b == Set()) nd else enqueue(nd, q, { ...EMPTY, ihave: b }, false)
  }
  pure def notePush(nd: Node, q: int, i: int): Node =
    if (nd.dropped.contains((q, i))) { ...nd, dropped: nd.dropped.exclude(Set((q, i))) }   // dropped at the queue: not pushed
    else { ...nd, pushed: nd.pushed.set(q, nd.pushed.get(q).union(Set(i))) }

  // ---- the window (§7.1) ----
  pure def wake(nd: Node, q: int): Node = { ...nd, runnable: nd.runnable.union(Set(q)) }
  pure def freeSlot(nd: Node): Node = {
    val nd1 = { ...nd, inFlight: nd.inFlight - 1 }
    if (nd1.waiters.length() > 0) wake(nd1, nd1.waiters.head()) else nd1
  }
  // acquire_slot: (node, true) when p's writer now holds a slot; (node, false) when it waits in line
  pure def acquireSlot(nd: Node, p: int): (Node, bool) =
    if (nd.inFlight < W and (nd.waiters.length() == 0 or nd.waiters.head() == p)) {
      val w1 = if (nd.waiters.length() > 0) nd.waiters.tail() else nd.waiters
      val f1 = nd.inFlight + 1
      val nd1 = { ...nd, waiters: w1, inFlight: f1, slotHeld: nd.slotHeld.union(Set(p)) }
      val nd2 = if (not(NO_WAKE_ON_TAKE) and w1.length() > 0 and f1 < W) wake(nd1, w1.head()) else nd1
      (nd2, true)
    } else {
      val w1 = if (has(nd.waiters, p)) nd.waiters else nd.waiters.append(p)   // it keeps its place
      ({ ...nd, waiters: w1 }, false)
    }
  pure def releaseUnusedSlot(nd: Node, p: int): Node = {
    val inLine = has(nd.waiters, p)
    val w1 = if (inLine) without(nd.waiters, p) else nd.waiters
    val nd1 = { ...nd, waiters: w1 }
    val nd2 = if (inLine and not(NO_WAKE_ON_LEAVE) and w1.length() > 0 and nd1.inFlight < W) wake(nd1, w1.head()) else nd1
    if (nd2.slotHeld.contains(p)) freeSlot({ ...nd2, slotHeld: nd2.slotHeld.exclude(Set(p)) }) else nd2
  }
  // track_in_flight: the writer's slot now travels with chunk i to p; a second copy returns it at once
  pure def trackInFlight(nd: Node, p: int, i: int): Node = {
    val nd1 = { ...nd, slotHeld: nd.slotHeld.exclude(Set(p)) }
    if (nd1.sent.contains((p, i))) freeSlot(nd1) else { ...nd1, sent: nd1.sent.union(Set((p, i))) }
  }
  pure def windowRelease(nd: Node, p: int, i: int): Node =
    if (nd.sent.contains((p, i))) freeSlot({ ...nd, sent: nd.sent.exclude(Set((p, i))) }) else nd

  // ---- asking (§6.1) ----
  pure def addOffer(nd0: Node, i: int, p: int): Node = {
    // B′: the offer is kept whatever the list does with it
    val nd = if (OFFERS_DURABLE) { ...nd0, offered: nd0.offered.set(p, nd0.offered.get(p).union(Set(i))) } else nd0
    val l = nd.offers.get(i)
    if (has(l, p)) nd
    else if (l.length() < OFFERS_MAX) { ...nd, offers: nd.offers.set(i, l.append(p)) }
    else if (OFFER_REPLACE and not(nd.tried.get(i).contains(p))) {
      // B′: a full table takes an announcer not yet asked for the chunk, parked or not, in place of the
      // earliest one already asked, a parked one first (an ask still out can still deliver); one never
      // asked is never displaced
      val tr = l.select(q => nd.tried.get(i).contains(q))
      val trp = tr.select(q => nd.parked.contains(q))
      val old = if (trp.length() > 0) trp[0] else if (tr.length() > 0) tr[0] else NONE
      if (old == NONE) nd else { ...nd, offers: nd.offers.set(i, without(l, old).append(p)) }
    }
    else nd                                                         // refused (§8.2)
  }
  // may_ask, once its window check has passed: the ask is in flight, p tried, p's promise open
  pure def askNow(nd: Node, i: int, p: int): Node = { ...nd,
    askCount: nd.askCount.set(i, nd.askCount.get(i) + 1),
    asking: nd.asking.union(Set(i)),
    tried: nd.tried.set(i, nd.tried.get(i).union(Set(p))),
    // a promise already open is not refreshed; with the candidate fix E it starts at the write instead
    promises: if (PROMISE_AT_WRITE) nd.promises else nd.promises.union(Set((i, p))),
    orphans: if (PROMISE_AT_WRITE or nd.promises.contains((i, p))) nd.orphans else nd.orphans.exclude(Set((i, p))),
  }
  // close_promises (the toy's): the chunk arrived, from anyone
  pure def closePromises(nd: Node, i: int): Node = { ...nd,
    promises: nd.promises.filter(x => x._1 != i),
    offers: nd.offers.set(i, List()),
    offered: nd.offered.keys().mapBy(q => nd.offered.get(q).exclude(Set(i))),
    asking: nd.asking.exclude(Set(i)),
    lrArmed: nd.lrArmed.exclude(Set(i)),
    tried: nd.tried.set(i, Set()),
  }

  // ---- receiving (§4) ----
  // §5.2: the candidates for pushing chunk i that arrived from `from`, and the budget
  pure def fwdCands(nd: Node, n: int, i: int, from: int): Set[int] = {
    val holding = MESH.get(n).filter(q => nd.peerHas.get(q).contains(i))
    MESH.get(n).exclude(holding).exclude(Set(from))
  }
  pure def fwdBudget(nd: Node, n: int, i: int): int = {
    val holding = MESH.get(n).filter(q => nd.peerHas.get(q).contains(i))
    imax(0, R_NODE - holding.size())
  }
  // the push targets the spec's selector could pick: any `budget` of the candidates
  pure def fwdOptions(nd: Node, n: int, e: Entry, from: int): Set[Set[int]] =
    if (e.chunk == NONE or e.forged != AUTHENTIC or n == SRC or nd.recv.contains(e.chunk)) Set(Set())
    else {
      val c = fwdCands(nd, n, e.chunk, from)
      subsetsOf(c, imin(fwdBudget(nd, n, e.chunk), c.size()))
    }
  pure def forward(nd: Node, n: int, i: int, from: int, tgt: Set[int]): Node = {
    val c = fwdCands(nd, n, i, from)
    val nd1 = tgt.fold(nd, (acc, q) => notePush(enqueue(acc, q, chunkEntry(i, false), false), q, i))
    c.exclude(tgt).fold(nd1, (acc, q) => announce(acc, q, Set(i)))
  }
  // claim_group (§4.6): the decode claim at the K-th chunk
  pure def claimGroup(nd: Node, n: int): Node = {
    val nd1 = { ...nd, stage: DECODING, stopPull: true, mine: CHUNKS }
    val nd2 = MESH.get(n).fold(nd1, (acc, q) => sendHave(acc, n, q))
    { ...nd2, promises: Set() }         // close_promises_of_group: promises only (the toy's)
  }
  // level 1 fails: the sender is penalised and the id marked seen (§4.2); nothing else changes
  pure def rejectChunk(nd: Node, p: int, i: int, v: int): Node =
    { ...nd, rejected: nd.rejected.union(Set((i, v))), lvl1Pen: nd.lvl1Pen.union(Set(p)) }
  // ROOT_TIED: p's copy of i waits for the root it names, so p is tied to that root for i, and its
  // promise for i closes (it answered, with a copy that cannot be checked yet)
  pure def tie(nd: Node, p: int, i: int, v: int): Node =
    if (not(ROOT_TIED)) nd
    else { ...nd, tied: nd.tied.union(Set((p, i, if (v == BOGUS_ROOT) BOGUS_ROOT else AUTHENTIC))),
                  promises: nd.promises.exclude(Set((i, p))) }
  // on_chunk: a duplicate is acknowledged; ahead of the block a chunk waits (DEFER: not claimed, not
  // forwarded) if the deferred store admits it; otherwise level 1 accepts or rejects it. A copy's id
  // is its index and its content (`forged`); a forgery naming a root that never installs always waits
  pure def onChunk(nd0: Node, n: int, p: int, i: int, v: int, tgt: Set[int], admit: bool): Node = {
    val nd = if (v == AUTHENTIC) { ...nd0, gotFrom: nd0.gotFrom.union(Set((p, i))) } else nd0
    // with fix C a copy that arrives closes the chunk's promises whether it is accepted or waits
    // (§6.1's prose: "a promise closes when the chunk arrives from anyone")
    val ndc = if (CLOSE_ON_DEFER) { ...nd, promises: nd.promises.filter(x => x._1 != i) } else nd
    // a copy that waits for the builder's block opens INSTALL_LATE's gate, kept or refused
    val seen = nd.seenCopy or v != BOGUS_ROOT
    if (n == SRC) (if (v == AUTHENTIC) sendHave(nd, n, p) else nd)       // the source has seen every authentic id
    else if (v == AUTHENTIC and nd.recv.contains(i)) sendHave(nd, n, p)   // seen and accepted: acknowledged [c14]
    else if (nd.rejected.contains((i, v))) nd                             // seen and rejected: nothing
    else if (nd.pending.exists(x => x._2 == i and x._3 == v)) tie(ndc, p, i, v)   // in pending_ids: nothing
    else if (v == BOGUS_ROOT or not(nd.installed))
      if (admit) tie({ ...ndc, pending: ndc.pending.union(Set((p, i, v))), seenCopy: seen }, p, i, v)   // reserved: it waits
      else if (REFUSE_OFFERS) {                                           // refused: an announcement from its
        val nd1 = addOffer({ ...nd, seenCopy: seen }, i, p)               //   sender, kept, and acted on now if
        if (mayPull(nd1)) { ...nd1, asking: nd1.asking.union(Set(i)) } else nd1   // the node may pull (an offer
      }                                                                   //   nobody asks would hold B′ off)
      else tie({ ...nd, seenCopy: seen }, p, i, v)                        // refused: nothing is remembered
    else if (v == BAD_PROOF) rejectChunk(nd, p, i, v)
    else acceptChunk(nd, n, p, i, tgt)
  }
  // on_validated with ACCEPT
  pure def acceptChunk(nd: Node, n: int, p: int, i: int, tgt: Set[int]): Node =
    if (n == SRC or nd.recv.contains(i)) sendHave(nd, n, p)       // a duplicate: acknowledged [c14]
    else if (nd.stage == INVALID) { ...nd, recv: nd.recv.union(Set(i)) }   // a dropped group: seen, nothing more
    else {
      val nd1 = closePromises({ ...nd, recv: nd.recv.union(Set(i)), stored: nd.stored.union(Set(i)) }, i)
      val claim = not(nd1.mine.contains(i))
      val nd2 = if (claim) { ...nd1, mine: nd1.mine.union(Set(i)) } else nd1
      val haveTo = if (claim) MESH.get(n).union(Set(p)) else Set(p)
      val nd3 = haveTo.fold(nd2, (acc, q) => sendHave(acc, n, q))
      val nd4 = forward(nd3, n, i, p, tgt)
      if (nd4.stage == COLLECTING and nd4.recv.size() >= K) claimGroup(nd4, n) else nd4
    }
  // on_ihave: returns the node and the asks
  // a chunk the node will not ask for: held, or (with fix C) a copy waiting for the block
  pure def noAsk(nd: Node): Set[int] =
    if (CLOSE_ON_DEFER) nd.mine.union(nd.pending.map(x => x._2)) else nd.mine
  // the node may pull: not stopped, and with C′ a block whose bid commits the group installed
  pure def mayPull(nd: Node): bool = not(nd.stopPull) and not(NO_ASK_BEFORE_INSTALL and not(nd.installed or nd.other))
  // ROOT_TIED: q's copy of chunk i waits for a root not installed, so q is not asked for it meanwhile
  pure def tiedTo(nd: Node, q: int, i: int): bool = ROOT_TIED and nd.tied.exists(x => x._1 == q and x._2 == i)
  // the announcers of chunk i: the list in announcement order, then (B′) every other peer that offered
  // it; a peer tied for it is not one until its root installs
  pure def annc(nd: Node, i: int): List[int] = {
    val l = nd.offers.get(i)
    val offerers = if (OFFERS_DURABLE) range(0, NN).foldl(l, (acc, q) => if (nd.offered.get(q).contains(i) and not(has(l, q))) acc.append(q) else acc)
      else l
    if (ROOT_TIED) offerers.select(q => not(tiedTo(nd, q, i))) else offerers
  }
  pure def allParked(nd: Node, i: int): bool = annc(nd, i).select(q => not(nd.parked.contains(q))).length() == 0
  // B′: the announcers of chunk i with last-resort asks left (an adversary that announced first cannot
  // use up an honest announcer's)
  pure def lrLeft(nd: Node, i: int): List[int] = annc(nd, i).select(q => nd.lastResort.get(i).get(q) < LR_MAX)
  pure def onIhave(nd: Node, p: int, bits: Set[int]): (Node, Set[int]) = {
    val cand = bits.exclude(noAsk(nd))                            // held chunks are skipped
    val nd1 = cand.fold(nd, (acc, i) => addOffer(acc, i, p))      // the offer table is also C′'s ledger
    // with the candidate fix B, a parked announcer is asked when every announcer of the chunk is parked
    val lastResortB = cand.filter(i => PARK_LAST_RESORT and allParked(nd1, i))
    val askable = if (not(mayPull(nd1))) Set() else if (nd1.parked.contains(p)) lastResortB else cand
    // may_ask; not a peer tied for the chunk (ROOT_TIED), nor one with an ask of it outstanding (NO_REASK_OPEN)
    val asks = askable.filter(i => not(nd1.asking.contains(i)) and nd1.askCount.get(i) < MAX_ASKS
                                   and not(tiedTo(nd1, p, i)) and not(NO_REASK_OPEN and outstanding(nd1, i, p)))
    val nd2 = asks.fold(nd1, (acc, i) => askNow(acc, i, p))
    // B′: a parked announcer's announcement arms the last resort for a chunk whose announcers are all parked
    val arm = if (LAST_RESORT and mayPull(nd2) and nd2.parked.contains(p))
        cand.filter(i => annc(nd2, i).length() > 0 and allParked(nd2, i) and not(nd2.asking.contains(i))
                         and lrLeft(nd2, i) != List())
      else Set()
    ({ ...nd2, lrArmed: nd2.lrArmed.union(arm) }, asks)
  }
  // on_iwant: returns the node, the answers and the penalties
  pure def onIwant(nd: Node, n: int, p: int, ids: Set[int]): (Node, Set[int], Set[(int, int, int)]) = {
    val claimed = ids.filter(i => nd.peerHas.get(p).contains(i))
    val pens = claimed.map(i => (n, p, i))                        // an ask for a chunk it claimed
    // resolve: nothing for a dropped group
    val cand = ids.exclude(claimed).filter(i => nd.stored.contains(i) and nd.stage != INVALID)
    val ok = cand.filter(i => nd.served.get(p).get(i) < SERVE_MAX)
    val nd1 = { ...nd, served: nd.served.set(p, cand.fold(nd.served.get(p), (m, i) => m.set(i, m.get(i) + 1))) }
    (nd1, ok, pens)
  }
  pure def onHave(nd: Node, p: int, bits: Set[int]): Node = {
    val newly = bits.exclude(nd.peerHas.get(p))
    val nd1 = { ...nd, peerHas: nd.peerHas.set(p, nd.peerHas.get(p).union(bits)) }
    newly.fold(nd1, (acc, i) => windowRelease(acc, p, i))
  }
  // respond: one response per RPC; the asks ride on the first answer
  pure def respond(nd: Node, p: int, asks: Set[int], answers: Set[int]): Node =
    if (answers == Set()) enqueue(nd, p, { ...EMPTY, iwant: asks }, false)
    else {
      val first = answers.fold(N, (m, i) => imin(m, i))
      answers.fold(nd, (acc, i) =>
        enqueue(acc, p, { ...chunkEntry(i, true), iwant: if (i == first) asks else Set() }, false))
    }
  // on_rpc (§4.1): chunks, IHAVE, IWANT, IDONTWANT, then the response
  pure def onRpc(st: State, n: int, p: int, e: Entry, tgt: Set[int], admit: bool): State = {
    val nd0 = st.nodes.get(n)
    if (ADV.contains(n)) st     // an adversarial node takes what it gets and does nothing with it
    else if (nd0.expired) st    // past its active lifetime: chunks and controls of the group are ignored
    else {
      val nd1 = if (e.chunk != NONE) onChunk(nd0, n, p, e.chunk, e.forged, tgt, admit) else nd0
      // other peers' promises for the chunk that a forged copy closed (fix C closes them on any copy;
      // with ROOT_TIED a forged answer closes its own sender's, which is then tied to the root it names)
      val closed = if (e.chunk != NONE and e.forged != AUTHENTIC)
          nd0.promises.filter(x => x._1 == e.chunk and x._2 != p and not(nd1.promises.contains(x))).map(x => (n, x._1, x._2))
        else Set()
      val ndh = if (IDONTWANT_FIRST and e.isHave) onHave(nd1, p, e.have) else nd1
      val r2 = onIhave(ndh, p, e.ihave)
      val r3 = onIwant(r2._1, n, p, e.iwant)
      val nd4 = if (not(IDONTWANT_FIRST) and e.isHave) onHave(r3._1, p, e.have) else r3._1
      val nd5 = respond(nd4, p, r2._2, r3._2)
      { ...st, nodes: st.nodes.set(n, nd5), penalties: st.penalties.union(r3._3), badClose: st.badClose.union(closed) }
    }
  }

  // ---- the source (§5.1) ----
  // every ordered list of `m` distinct mesh peers of the source
  pure def orderedPicks(S: Set[int], m: int): Set[List[int]] =
    range(0, m).foldl(Set(List()), (acc, _j) =>
      acc.map(l => S.exclude(toSet(l)).map(x => l.append(x))).flatten())
  pure val SRC_PICKS = orderedPicks(MESH.get(SRC), imin(R, MESH.get(SRC).size()))
  // the source notes its pushes when it plans them; with FORGET_DROPPED one dropped at a full queue is forgotten
  pure def enqueuePlanned(nd: Node, q: int, i: int): Node = {
    val nd1 = enqueue(nd, q, chunkEntry(i, false), false)
    if (nd1.dropped.contains((q, i)))
      { ...nd1, dropped: nd1.dropped.exclude(Set((q, i))), pushed: nd1.pushed.set(q, nd1.pushed.get(q).exclude(Set(i))) }
    else nd1
  }
  // §5.1 and §5.3 at the source: chunks in index order, each to the R peers with the fewest chunks
  // planned so far (fewest first, no draw); ties go any way, as the tie-break hash may send them
  pure def fewestFirst(plan: int -> List[int]): bool =
    range(0, N).foldl((true, MESH.get(SRC).mapBy(q => 0)), (acc, i) => {
      val cnt = acc._2
      val t = plan.get(i)
      val ts = toSet(t)
      val ok = MESH.get(SRC).exclude(ts).forall(q => ts.forall(x => cnt.get(x) <= cnt.get(q)))
        and t.indices().forall(j => t.indices().forall(k => j >= k or cnt.get(t[j]) <= cnt.get(t[k])))
      (acc._1 and ok, ts.fold(cnt, (m, q) => m.set(q, m.get(q) + 1)))
    })._1
  pure val SRC_PLANS = CHUNKS.setOfMaps(SRC_PICKS).filter(pl => fewestFirst(pl))
  pure def publish(st: State, plan: int -> List[int]): State = {
    val nd0 = { ...st.nodes.get(SRC), stored: CHUNKS, mine: CHUNKS, stage: COMPLETE, stopPull: true }
    val nd1 = CHUNKS.fold(nd0, (acc, i) => toSet(plan.get(i)).fold(acc, (a2, q) => notePush(a2, q, i)))
    // the first copy of every chunk before any second [c2]; a peer's first chunk follows a HAVE naming it [P4]
    val r = range(0, R).foldl((nd1, st.led), (acc, c) =>
      range(0, N).foldl(acc, (a2, i) =>
        if (c < plan.get(i).length()) {
          val q = plan.get(i)[c]
          val first = a2._2.get(q) == NONE
          val ndh = if (first) enqueue(a2._1, q, haveEntry(haveBits(a2._1, SRC).union(Set(i))), true) else a2._1
          (enqueuePlanned(ndh, q, i), if (first) a2._2.set(q, i) else a2._2)
        } else a2))
    // mesh peers not pushed a chunk are announced it [c3]
    val nd3 = range(0, N).foldl(r._1, (acc, i) => MESH.get(SRC).fold(acc, (a2, q) => announce(a2, q, Set(i))))
    { ...st, nodes: st.nodes.set(SRC, nd3), published: true, led: r._2 }
  }
  // origin_sent: a chunk of the published group leaves for the first time; the HAVE follows it to the mesh
  pure def originSent(nd: Node, n: int, i: int): Node =
    if (n != SRC or nd.origin.contains(i)) nd
    else MESH.get(SRC).fold({ ...nd, origin: nd.origin.union(Set(i)) }, (acc, q) => sendHave(acc, SRC, q))

  // ---- sending (§7.2) ----
  pure def projected(nd: Node, p: int): bool = {
    val h = nd.peerHas.get(p)
    h.size() + FAN_IN * nd.sentTo.get(p).exclude(h).size() >= K
  }
  // the length of the queue's leading run of chunk entries: rarest at pop never overtakes control
  pure def chunkPrefix(q: List[Entry]): int =
    q.foldl((0, true), (acc, e) => if (acc._2 and e.chunk != NONE) (acc._1 + 1, true) else (acc._1, false))._1
  // rarest at pop (§7.2, card 9): among the leading chunk entries, the one the fewest peers hold
  // (distinct holders by HAVE), the earliest on ties
  pure def holders(nd: Node, i: int): int = NODES.filter(q => nd.peerHas.get(q).contains(i)).size()
  pure def popOptions(nd: Node, p: int): Set[int] = {
    val q = nd.qNorm.get(p)
    val L = chunkPrefix(q)
    if (RAREST and L > 1)
      Set(range(0, L).foldl(0, (best, j) => if (holders(nd, q[j].chunk) < holders(nd, q[best].chunk)) j else best))
    else Set(0)
  }
  // filter_entry: cancel, projection, and the asker's stale asks
  pure def filterEntry(nd: Node, p: int, e: Entry): (Node, Entry) = {
    val cancel = e.chunk != NONE and CANCEL and nd.peerHas.get(p).contains(e.chunk)
    val project = e.chunk != NONE and not(cancel) and PROJECT and not(e.sol) and projected(nd, p)
    val e1 = if (cancel or project) { ...e, chunk: NONE } else e
    // with the candidate fix, the skipped push is forgotten and the chunk offered instead (with A′,
    // owed: this write or the next carries the offer)
    val unpushed = { ...nd, pushed: nd.pushed.set(p, nd.pushed.get(p).exclude(Set(e.chunk))) }
    val nd0 = if (project and PROJECT_OFFERS)
        (if (ADMIT_OFFERS) owe(unpushed, p, Set(e.chunk)) else announce(unpushed, p, Set(e.chunk)))
      else nd
    val nd1 = if (e1.chunk != NONE) { ...nd0, sentTo: nd0.sentTo.set(p, nd0.sentTo.get(p).union(Set(e1.chunk))) } else nd0
    // the asker drops asks for chunks it holds, after stop-pull, (D′) for an expired group, and
    // (ROOT_TIED) for chunks this peer is tied for
    val asks = if (NO_ASK_FILTER) e1.iwant else if (nd.stopPull or (EXPIRY_CLEANUP and nd.expired)) Set()
      else e1.iwant.exclude(noAsk(nd)).filter(i => not(tiedTo(nd, p, i)))
    (nd1, { ...e1, iwant: asks })
  }
  // write: append to the link, and record what the monitors look at
  pure def write(st: State, n: int, p: int, nd0: Node, e0: Entry): State = {
    // A′: the offers owed to p ride on this entry, less what p holds or is pushed
    val ow = if (ADMIT_OFFERS) nd0.owed.get(p).exclude(nd0.pushed.get(p)).exclude(nd0.peerHas.get(p)).exclude(Set(e0.chunk)) else Set()
    val e = { ...e0, ihave: e0.ihave.union(ow) }
    val nd = if (ADMIT_OFFERS) { ...nd0, owed: nd0.owed.set(p, Set()) } else nd0
    if (isEmpty(e)) { ...st, nodes: st.nodes.set(n, nd) }      // nothing owed is left to offer
    else writeEntry(st, n, p, nd, e)
  }
  pure def writeEntry(st: State, n: int, p: int, nd: Node, e: Entry): State = {
    val bad = e.iwant.filter(i => nd.mine.contains(i) or nd.stopPull).map(i => (n, p, i))
    // an announcement says who can serve (§4.4): it names only chunks its sender can serve now
    val badI = e.ihave.exclude(servable(nd)).map(i => (n, p, i))
    val badX = if (nd.expired) e.iwant.map(i => (n, i)) else Set()  // an ask written for an expired group
    // after drop_group nothing of the group but HAVEs leaves the node
    val badDrop = if (nd.stage == INVALID and (e.chunk != NONE or e.ihave != Set() or e.iwant != Set())) Set((n, p)) else Set()
    val badH = if (n == SRC and e.isHave)
      e.have.filter(i => not(nd.origin.contains(i)) and st.led.get(p) != i).map(i => (p, i)) else Set()
    val l = st.links.get((n, p))
    val last = if (l.length() > 0) l[l.length() - 1] else EMPTY
    // with COALESCE the transport folds the entry into the RPC still on the link, at most one chunk per RPC
    val l2 = if (COALESCE and l.length() > 0 and not(last.chunk != NONE and e.chunk != NONE))
        l.slice(0, l.length() - 1).append({
          chunk: if (last.chunk != NONE) last.chunk else e.chunk,
          sol: if (last.chunk != NONE) last.sol else e.sol,
          forged: if (last.chunk != NONE) last.forged else e.forged,
          iwant: last.iwant.union(e.iwant), ihave: last.ihave.union(e.ihave),
          have: last.have.union(e.have), isHave: last.isHave or e.isHave })
      else l.append(e)
    val fresh = e.iwant.map(i => (i, p)).filter(x => not(nd.promises.contains(x)))   // promises newly opened
    val nd2 = { ...nd, askWritten: nd.askWritten.union(e.iwant.map(i => (i, p))),
                gotFrom: nd.gotFrom.exclude(e.iwant.map(i => (p, i))),
                promises: if (PROMISE_AT_WRITE) nd.promises.union(e.iwant.map(i => (i, p))) else nd.promises,
                orphans: if (PROMISE_AT_WRITE) nd.orphans.exclude(fresh) else nd.orphans }
    { ...st, nodes: st.nodes.set(n, nd2), links: st.links.set((n, p), l2),
      badAsk: st.badAsk.union(bad), badHave: st.badHave.union(badH), badDrop: st.badDrop.union(badDrop),
      badExpiredAsk: st.badExpiredAsk.union(badX), badIhave: st.badIhave.union(badI) }
  }
  // one run of next_to_send for p's writer at n, up to its next return or "start again"
  pure def writerStep(st: State, n: int, p: int, k: int): State = {
    val nd0 = st.nodes.get(n)
    // A′: an answer a full queue refused is queued as soon as there is room (the lowest index first)
    val oa = nd0.owedAns.get(p)
    val room = nd0.qUrg.get(p).length() + nd0.qNorm.get(p).length() < QMAX
    val nd = if (ADMIT_OFFERS and oa != Set() and room) {
        val i = oa.fold(N, (m, x) => imin(m, x))
        { ...nd0, owedAns: nd0.owedAns.set(p, oa.exclude(Set(i))), qNorm: nd0.qNorm.set(p, nd0.qNorm.get(p).append(chunkEntry(i, true))) }
      } else nd0
    val qu = nd.qUrg.get(p)
    val qn = nd.qNorm.get(p)
    if (qu.length() > 0) write(st, n, p, { ...nd, qUrg: nd.qUrg.set(p, qu.tail()) }, qu.head())
    else if (qn.length() == 0 and ADMIT_OFFERS and nd.owed.get(p) != Set()) write(st, n, p, nd, EMPTY)   // A′: the owed offers alone
    else if (qn.length() == 0) {
      val nd1 = releaseUnusedSlot(nd, p)                          // nothing to send: a held slot goes back
      { ...st, nodes: st.nodes.set(n, { ...nd1, runnable: nd1.runnable.exclude(Set(p)) }) }
    } else if (hasChunks(qn) and not(nd.slotHeld.contains(p))) {
      val r = acquireSlot(nd, p)                                  // [c14] FIFO over peers
      val nd1 = if (r._2) r._1 else { ...r._1, runnable: r._1.runnable.exclude(Set(p)) }   // WAIT
      { ...st, nodes: st.nodes.set(n, nd1) }
    } else {
      val e = qn[k]
      val nd1 = { ...nd, qNorm: nd.qNorm.set(p, dropAt(qn, k)) }
      val f = filterEntry(nd1, p, e)
      val e2 = f._2
      val nd2 = if (e2.chunk == NONE) releaseUnusedSlot(f._1, p) else f._1   // no chunk leaves: the slot goes back
      if (isEmpty(e2)) { ...st, nodes: st.nodes.set(n, nd2) }   // nothing left: start again
      else if (e2.chunk != NONE) write(st, n, p, originSent(trackInFlight(nd2, p, e2.chunk), n, e2.chunk), e2)
      else write(st, n, p, nd2, e2)
    }
  }

  // ---- decoding and repair (§4.6) ----
  // repair: each mesh peer short of K is pushed at most its shortfall of the rebuilt chunks it lacks
  pure def repairOptions(nd: Node, n: int, q: int): Set[Set[int]] =
    if (not(REPAIR) or not(MESH.get(n).contains(q))) Set(Set())
    else {
      val known = nd.peerHas.get(q).union(nd.pushed.get(q))
      val short = K - known.size()
      val lacks = CHUNKS.exclude(nd.recv).exclude(known)
      if (short <= 0) Set(Set()) else subsetsOf(lacks, imin(short, lacks.size()))
    }
  pure def decode(nd: Node, n: int, sel: int -> Set[int]): Node =
    if (BAD_CODE) dropGroup(nd)
    else {
      val nd1 = { ...nd, stored: CHUNKS, stage: COMPLETE }
      MESH.get(n).fold(nd1, (acc, q) => sel.get(q).fold(acc, (a2, i) => notePush(enqueue(a2, q, chunkEntry(i, false), false), q, i)))
    }
  // drop_group (§4.6): stop pulling, discard the group's chunks, IHAVEs and IWANTs from every queue
  // (HAVEs stay), close its promises: the announcers did nothing wrong
  pure def dropGroup(nd: Node): Node = { ...nd,
    stage: INVALID, stopPull: true, promises: Set(),
    qNorm: nd.qNorm.keys().mapBy(p => List()),       // a normal entry holds only chunks, IHAVEs, IWANTs
    owed: nd.owed.keys().mapBy(p => Set()),          // A′: owed offers are IHAVEs too
    owedAns: nd.owedAns.keys().mapBy(p => Set()),    //   and owed answers chunks
  }

  // ---- events ----
  action init = all {
    s' = {
      nodes: NODES.mapBy(n => emptyNode(n)),
      links: tuples(NODES, NODES).mapBy(k => List()),
      published: false,
      penalties: Set(), badAsk: Set(), badHave: Set(), badPark: Set(), badParkSame: Set(), badIhave: Set(), badExpiredAsk: Set(),
      led: NODES.mapBy(n => NONE), advSent: 0, badDrop: Set(), badUnsent: Set(), badClose: Set(),
      discs: 0, badDiscPark: Set(), exhaustSwitch: Set(),
    },
    clock' = 0,
  }

  action publishAct = all {
    not(s.published),
    nondet plan = SRC_PLANS.oneOf()
    s' = publish(s, plan),
  }
  pure def busyLinks(st: State): Set[(int, int)] = tuples(NODES, NODES).filter(k => st.links.get(k).length() > 0)
  action deliverAct = all {
    busyLinks(s) != Set(),
    nondet lk = busyLinks(s).oneOf()
    val src = lk._1
    val dst = lk._2
    val e = s.links.get(lk).head()
    val st1 = { ...s, links: s.links.set(lk, s.links.get(lk).tail()) }
    nondet tgt = fwdOptions(st1.nodes.get(dst), dst, e, src).oneOf()
    // the deferred store admits the chunk, or (DEFER_REFUSE) may refuse it
    nondet admit = (if (DEFER_REFUSE) Set(true, false) else Set(true)).oneOf()
    s' = onRpc(st1, dst, src, e, tgt, admit),
  }
  pure def runnableWriters(st: State): Set[(int, int)] =
    tuples(NODES, NODES).filter(k => st.nodes.get(k._1).runnable.contains(k._2))
  // with EAGER_WRITERS, writerStep repeats while the writer stays runnable (rarest at pop is
  // deterministic, so the run is a function of the state); 3 × N + 8 steps cover any queue the
  // instances build
  pure def drain(st: State, n: int, p: int): State =
    range(0, 3 * N + 8).foldl(st, (acc, _j) =>
      if (acc.nodes.get(n).runnable.contains(p)) writerStep(acc, n, p, popOptions(acc.nodes.get(n), p).fold(0, (m, x) => x))
      else acc)
  action writerAct = all {
    runnableWriters(s) != Set(),
    nondet w = runnableWriters(s).oneOf()
    nondet k = popOptions(s.nodes.get(w._1), w._2).oneOf()
    s' = if (EAGER_WRITERS) drain(s, w._1, w._2) else writerStep(s, w._1, w._2, k),
  }
  // WINDOW_TIMEOUT: a slot comes back without a covering HAVE
  pure def timeouts(st: State): Set[(int, (int, int))] =
    NODES.map(n => st.nodes.get(n).sent.map(key => (n, key))).flatten()
  action windowTimeoutAct = all {
    timeouts(s) != Set(),
    nondet t = timeouts(s).oneOf()
    val nd = s.nodes.get(t._1)
    s' = { ...s, nodes: s.nodes.set(t._1, freeSlot({ ...nd, sent: nd.sent.exclude(Set(t._2)) })) },
  }
  // PROMISE: a broken promise parks the peer for this group (§6.1, k = 1)
  pure def duePromises(st: State): Set[(int, (int, int))] =
    NODES.map(n => st.nodes.get(n).promises.map(x => (n, x))).flatten()
  action promiseDueAct = all {
    duePromises(s) != Set(),
    nondet d = duePromises(s).oneOf()
    val nd = s.nodes.get(d._1)
    val parked = if (PARK) nd.parked.union(Set(d._2._2)) else nd.parked
    val bad = if (PARK and nd.gotFrom.contains((d._2._2, d._2._1))) Set((d._1, d._2._2, d._2._1)) else Set()
    // C′'s residual is a park by a node on the other block at the time (not one that has switched)
    val badSame = if (nd.other and not(nd.installed)) Set() else bad
    // parked for an ask that never left this node: dropped at a full queue, or held behind chunks while
    // the writer waits for a window slot (an idle writer writes at once, which the model's timing omits)
    val i = d._2._1
    val q = d._2._2
    val queued = nd.qNorm.get(q).indices().exists(j => nd.qNorm.get(q)[j].iwant.contains(i))
    val stuck = queued and has(nd.waiters, q) and not(nd.askWritten.contains(d._2))
    val dropped = not(queued) and not(nd.askWritten.contains(d._2))
    val unsent = if (PARK and (stuck or dropped)) Set((d._1, q, i)) else Set()
    // parked for a promise whose connection closed while it was open (DISC)
    val orphan = if (PARK and nd.orphans.contains(d._2)) Set((d._1, q, i)) else Set()
    val nd1 = { ...nd, promises: nd.promises.exclude(Set(d._2)), parked: parked, orphans: nd.orphans.exclude(Set(d._2)) }
    s' = { ...s, nodes: s.nodes.set(d._1, nd1),
           badPark: s.badPark.union(bad), badParkSame: s.badParkSame.union(badSame),
           badUnsent: s.badUnsent.union(unsent), badDiscPark: s.badDiscPark.union(orphan) },
  }
  // IWANT_WINDOW closes and retry_offer runs: move on to an untried announcer, else any unparked one
  pure def asksOpen(st: State): Set[(int, int)] = NODES.map(n => st.nodes.get(n).asking.map(i => (n, i))).flatten()
  // the chunk is still to be asked for: not held, pulling, under the model's bound, and (fix D) not expired
  pure def wanted(nd: Node, i: int): bool =
    not(noAsk(nd).contains(i)) and mayPull(nd) and nd.askCount.get(i) < MAX_ASKS and not(RETRY_CHECKS_EXPIRY and nd.expired)
  // the earliest of l not tried yet, else any of them
  pure def pickFrom(nd: Node, i: int, l: List[int]): Set[int] = {
    val untried = l.select(q => not(nd.tried.get(i).contains(q)))
    if (l.length() == 0) Set(NONE) else if (untried.length() > 0) Set(untried.head()) else toSet(l)
  }
  // NO_REASK_OPEN: an ask of chunk i to q is outstanding while it is queued or its promise is open
  pure def outstanding(nd: Node, i: int, q: int): bool =
    nd.promises.contains((i, q)) or nd.qNorm.get(q).select(e => e.iwant.contains(i)).length() > 0
  pure def unpromised(nd: Node, i: int, l: List[int]): List[int] =
    if (NO_REASK_OPEN) l.select(q => not(outstanding(nd, i, q))) else l
  // every candidate in l skipped for an outstanding ask: the retry (or the last resort) looks again later
  pure def skippedOnly(nd: Node, i: int, l: List[int]): bool =
    NO_REASK_OPEN and l.length() > 0 and unpromised(nd, i, l).length() == 0
  pure def retryList(nd: Node, i: int): List[int] = {
    val unparked = annc(nd, i).select(q => not(nd.parked.contains(q)))
    if (PARK_LAST_RESORT and unparked.length() == 0) annc(nd, i) else unparked
  }
  pure def retryOptions(nd: Node, i: int): Set[int] =
    // no expiry check: retry_offer has none (§6.1); fix D adds it
    if (not(wanted(nd, i))) Set(NONE) else pickFrom(nd, i, unpromised(nd, i, retryList(nd, i)))
  action askTimeoutAct = all {
    asksOpen(s) != Set(),
    nondet a = asksOpen(s).oneOf()
    val n = a._1
    val i = a._2
    val nd = s.nodes.get(n)
    val nd1 = { ...nd, asking: nd.asking.exclude(Set(i)) }
    nondet pick = retryOptions(nd1, i).oneOf()
    val nd2 = if (pick != NONE) enqueue(askNow(nd1, i, pick), pick, { ...EMPTY, iwant: Set(i) }, false)
      // NO_REASK_OPEN: every candidate has an ask outstanding: look again a window later
      else if (wanted(nd1, i) and skippedOnly(nd1, i, retryList(nd1, i))) { ...nd1, asking: nd1.asking.union(Set(i)) }
      // B′: every announcer is parked: the last resort's timer is armed while one has asks left
      else if (LAST_RESORT and wanted(nd1, i) and annc(nd1, i).length() > 0 and allParked(nd1, i)
               and lrLeft(nd1, i) != List()) { ...nd1, lrArmed: nd1.lrArmed.union(Set(i)) }
      else nd1
    s' = { ...s, nodes: s.nodes.set(n, nd2) },
  }
  // B′: the last resort's timer fires (in the spec PROMISE × 2^n after it is armed): an announcer
  // unparked meanwhile if there is one, else any parked one, counted
  pure def lrOpen(st: State): Set[(int, int)] = NODES.map(n => st.nodes.get(n).lrArmed.map(i => (n, i))).flatten()
  // the last resort's candidates: an announcer unparked meanwhile if there is one, else the parked
  // ones with asks left
  pure def lrList(nd: Node, i: int): List[int] = {
    val unparked = annc(nd, i).select(q => not(nd.parked.contains(q)))
    if (unparked.length() > 0) unparked else lrLeft(nd, i)
  }
  pure def lastResortOptions(nd: Node, i: int): Set[int] =
    if (not(wanted(nd, i)) or nd.asking.contains(i)) Set(NONE)    // an ask went out meanwhile: its retry carries on
    else if (lrList(nd, i) == List()) Set(NONE)
    else pickFrom(nd, i, unpromised(nd, i, lrList(nd, i)))     // with NO_REASK_OPEN not one with an ask outstanding
  action lastResortAct = all {
    lrOpen(s) != Set(),
    nondet a = lrOpen(s).oneOf()
    val n = a._1
    val i = a._2
    val nd = s.nodes.get(n)
    val nd1 = { ...nd, lrArmed: nd.lrArmed.exclude(Set(i)) }
    nondet pick = lastResortOptions(nd1, i).oneOf()
    // NO_REASK_OPEN: every candidate has an ask outstanding: the last resort waits
    val nd2 = if (pick == NONE)
        (if (wanted(nd1, i) and not(nd1.asking.contains(i)) and skippedOnly(nd1, i, lrList(nd1, i)))
           { ...nd1, lrArmed: nd1.lrArmed.union(Set(i)) } else nd1)
      else {
      val nd3 = enqueue(askNow(nd1, i, pick), pick, { ...EMPTY, iwant: Set(i) }, false)
      // a parked announcer's last resort counts only once the queue has taken its ask: a refused
      // one leaves the budget, and the ask's retry arms the last resort again
      val admitted = nd3.qNorm.get(pick).length() > nd1.qNorm.get(pick).length()
      if (nd1.parked.contains(pick) and (admitted or LR_AT_DECISION))
        { ...nd3, lastResort: nd3.lastResort.set(i, nd3.lastResort.get(i).set(pick, nd3.lastResort.get(i).get(pick) + 1)) }
      else nd3
    }
    s' = { ...s, nodes: s.nodes.set(n, nd2) },
  }
  // the block installs: deferred chunks resume level 1, one at a time; with C′ the offers recorded
  // before it (the ledger) get their ask timers armed, and the retry asks for what is still wanted
  // INSTALL_LATE: a node's block installs only once a chunk has waited for it, kept or refused (with
  // C′, or once an offer is recorded)
  pure def heardOf(nd: Node): bool =
    nd.seenCopy or nd.pending != Set() or (NO_ASK_BEFORE_INSTALL and CHUNKS.exists(i => annc(nd, i).length() > 0))
  // EQ_EXHAUST's precondition: for a chunk n lacks, nothing of it waits at n or is on its way to n
  // (on a link, queued, owed), and every mesh peer has answered n for it SERVE_MAX times
  pure def exhausted(st: State, n: int): bool = {
    val nd = st.nodes.get(n)
    CHUNKS.exists(i => not(nd.recv.contains(i)) and not(nd.pending.exists(x => x._2 == i))
      and MESH.get(n).forall(q => {
        val nq = st.nodes.get(q)
        nq.served.get(n).get(i) >= SERVE_MAX and not(nq.owedAns.get(n).contains(i))
          and st.links.get((q, n)).select(e => e.chunk == i).length() == 0
          and nq.qNorm.get(n).select(e => e.chunk == i).length() == 0
      }))
  }
  // EQ: a node on the other block installs the builder's block only with EQ_SWITCH (EQ_LATE: once it
  // has parked every peer, the precondition of the stall B′ prevents; EQ_EXHAUST: once its providers'
  // answers for a chunk it lacks are spent; either, or once nothing else is left to happen)
  pure def switchable(st: State, n: int): bool =
    not(EQ.contains(n)) or (EQ_SWITCH and (
      if (EQ_EXHAUST) exhausted(st, n) or quietRest(st)
      else not(EQ_LATE) or MESH.get(n).forall(q => st.nodes.get(n).parked.contains(q)) or quietRest(st)))
  pure def uninstalled(st: State): Set[int] =
    NODES.filter(n => not(st.nodes.get(n).installed) and (not(INSTALL_LATE) or heardOf(st.nodes.get(n))) and switchable(st, n))
  // ROOT_TIED at the installation of the builder's block: its ties are released; each sender's park
  // lifts, B′'s count for it and the chunk clears, and it becomes an offer of the chunk
  pure def releaseTies(nd: Node): Node = {
    val rel = if (ROOT_TIED) nd.tied.filter(x => x._3 == AUTHENTIC) else Set()
    val nd1 = { ...nd, tied: nd.tied.exclude(rel), parked: nd.parked.exclude(rel.map(x => x._1)) }
    rel.fold(nd1, (acc, x) => {
      val acc1 = { ...acc, lastResort: acc.lastResort.set(x._2, acc.lastResort.get(x._2).set(x._1, 0)) }
      if (noAsk(acc1).contains(x._2)) acc1 else addOffer(acc1, x._2, x._1)
    })
  }
  action installAct = all {
    uninstalled(s) != Set(),
    nondet n = uninstalled(s).oneOf()
    val nd = s.nodes.get(n)
    val ndr = releaseTies(nd)
    // C′'s ledger, and (ROOT_TIED) the released chunks still wanted, get their ask timers armed
    val ledger = if (NO_ASK_BEFORE_INSTALL) CHUNKS.filter(i => annc(ndr, i).length() > 0) else Set()
    val freed = nd.tied.filter(x => ROOT_TIED and x._3 == AUTHENTIC).map(x => x._2).exclude(noAsk(ndr))
    val nd1 = { ...ndr, installed: true, asking: ndr.asking.union(ledger).union(freed) }
    val nd2 = if (EQ_UNPARK) { ...nd1, parked: Set(), lastResort: CHUNKS.mapBy(i => NODES.mapBy(q => 0)) } else nd1
    s' = { ...s, nodes: s.nodes.set(n, nd2),
           exhaustSwitch: if (EQ.contains(n) and exhausted(s, n)) s.exhaustSwitch.union(Set(n)) else s.exhaustSwitch },
  }
  // a forgery naming a root that never installs never resumes
  pure def replayable(st: State): Set[(int, (int, int, int))] =
    NODES.filter(n => st.nodes.get(n).installed)
      .map(n => st.nodes.get(n).pending.filter(x => x._3 != BOGUS_ROOT).map(x => (n, x))).flatten()
  action replayAct = all {
    replayable(s) != Set(),
    nondet r = replayable(s).oneOf()
    val n = r._1
    val p = r._2._1
    val i = r._2._2
    val nd = s.nodes.get(n)
    val nd1 = { ...nd, pending: nd.pending.exclude(Set(r._2)) }
    nondet tgt = fwdOptions(nd1, n, chunkEntry(i, false), p).oneOf()
    // level 1 at installation: the forgery that names the real root fails its proof
    s' = { ...s, nodes: s.nodes.set(n, if (r._2._3 == BAD_PROOF) rejectChunk(nd1, p, i, BAD_PROOF) else acceptChunk(nd1, n, p, i, tgt)) },
  }
  // the group passes its active lifetime at a node: only the tombstone is left (§8.1); the per-ask
  // state (offers, tried, the ask timers, promises) keeps its own lifetimes, unless D′ cleans it up.
  // Not while the group decodes, unless EXPIRE_DECODING: then only then (F10: decode_group does not look
  // at expiry when it returns, so a decode finishing after the group expired stores and pushes its
  // chunks again, and offers what it cannot serve; DECODE_CHECKS_EXPIRY drops such a decode)
  pure def pulling(nd: Node): bool =
    nd.asking != Set() or nd.lrArmed != Set() or NODES.exists(p => nd.qNorm.get(p).select(e => e.iwant != Set()).length() > 0)
  pure def expirable(st: State): Set[int] =
    if (EXPIRY) NODES.filter(n => n != SRC and not(st.nodes.get(n).expired)
                                  and (if (EXPIRE_DECODING) st.nodes.get(n).stage == DECODING
                                       else st.nodes.get(n).stage != DECODING and (not(EXPIRE_LATE) or pulling(st.nodes.get(n)))))
    else Set()
  action expireAct = all {
    expirable(s) != Set(),
    nondet n = expirable(s).oneOf()
    val nd = s.nodes.get(n)
    val nd1 = { ...nd, expired: true, mine: Set(), stored: Set(), recv: Set(), stopPull: false }
    // D′: the group's pull state and queued work go with it; window slots come back the usual ways
    val nd2 = if (EXPIRY_CLEANUP) { ...nd1,
        offers: CHUNKS.mapBy(i => List()), tried: CHUNKS.mapBy(i => Set()), promises: Set(),
        asking: Set(), lrArmed: Set(), owed: NODES.mapBy(p => Set()), offered: NODES.mapBy(p => Set()),
        owedAns: NODES.mapBy(p => Set()), qNorm: NODES.mapBy(p => List()) }
      else nd1
    s' = { ...s, nodes: s.nodes.set(n, nd2) },
  }
  // a connection closes and a new one opens at once (§8.1): the peer's per-connection state goes, B′'s
  // counts for it with `tried`, and (ROOT_TIED) its ties;
  // its queue closes, so the writer leaves the line and its slots come back (waking the next in line);
  // parks stay, kept by peer id; promises stay, as written, unless CLOSE_PROMISES_ON_DISC
  pure def closeConn(nd0: Node, p: int): Node = {
    val nd1 = releaseUnusedSlot(nd0, p)
    val inSent = nd1.sent.filter(x => x._1 == p)
    val nd2 = inSent.fold({ ...nd1, sent: nd1.sent.exclude(inSent) }, (acc, x) => freeSlot(acc))
    val open = nd2.promises.filter(x => x._2 == p)
    { ...nd2,
      peerHas: nd2.peerHas.set(p, Set()), pushed: nd2.pushed.set(p, Set()), sentTo: nd2.sentTo.set(p, Set()),
      served: nd2.served.set(p, CHUNKS.mapBy(i => 0)),
      qUrg: nd2.qUrg.set(p, List()), qNorm: nd2.qNorm.set(p, List()), runnable: nd2.runnable.exclude(Set(p)),
      offers: CHUNKS.mapBy(i => without(nd2.offers.get(i), p)),
      tried: CHUNKS.mapBy(i => nd2.tried.get(i).exclude(Set(p))),
      offered: nd2.offered.set(p, Set()), owed: nd2.owed.set(p, Set()), owedAns: nd2.owedAns.set(p, Set()),
      dropped: nd2.dropped.filter(x => x._1 != p),
      tied: nd2.tied.filter(x => x._1 != p),
      promises: if (CLOSE_PROMISES_ON_DISC) nd2.promises.exclude(open) else nd2.promises,
      orphans: if (CLOSE_PROMISES_ON_DISC) nd2.orphans else nd2.orphans.union(open),
      lastResort: CHUNKS.mapBy(i => nd2.lastResort.get(i).set(p, 0)),
    }
  }
  // what a node can serve (resolve, §4.5): the chunks it holds, received or rebuilt; nothing of a
  // dropped group, or of an expired one
  pure def servable(nd: Node): Set[int] = if (nd.stage == INVALID or nd.expired) Set() else nd.stored
  // the new connection: with RESYNC_ON_CONNECT each side offers the other what it can serve (the
  // source too: P4 paces its HAVE, not its IHAVE, §5.1); RESYNC_MINE, the first form, its decode claim
  pure def openConn(nd: Node, p: int): Node =
    if (not(RESYNC_ON_CONNECT)) nd else announce(nd, p, if (RESYNC_MINE) nd.mine else servable(nd))
  // DISC_AT: where the closes fall
  pure def discAt(st: State, a: int, b: int): bool = {
    val na = st.nodes.get(a)
    val nb = st.nodes.get(b)
    if (DISC_AT == 1) na.stage == DECODING or nb.stage == DECODING
    else if (DISC_AT == 2) na.stage == INVALID or nb.stage == INVALID
    else if (DISC_AT == 3) a == SRC and na.origin == Set()
    else if (DISC_AT == 4) na.expired or nb.expired
    else if (DISC_AT == 5) ADV.contains(a) or ADV.contains(b)
    else true
  }
  pure def disconnectable(st: State): Set[(int, int)] =
    if (DISC_MAX == 0 or not(st.published) or st.discs >= DISC_MAX) Set()
    else {
      val ends = if (DISC_ADV) NODES else NODES.exclude(ADV)
      tuples(ends, ends).filter(k => k._1 < k._2 and MESH.get(k._1).contains(k._2) and discAt(st, k._1, k._2)
        and (not(DISC_LATE) or st.nodes.get(k._1).promises.exists(x => x._2 == k._2)
                            or st.nodes.get(k._2).promises.exists(x => x._2 == k._1)))
    }
  action disconnectAct = all {
    disconnectable(s) != Set(),
    nondet k = disconnectable(s).oneOf()
    val a = k._1
    val b = k._2
    s' = { ...s, links: s.links.set((a, b), List()).set((b, a), List()),
           nodes: s.nodes.set(a, openConn(closeConn(s.nodes.get(a), b), b)).set(b, openConn(closeConn(s.nodes.get(b), a), a)),
           discs: s.discs + 1 },
  }
  // a decode in progress; with DECODE_CHECKS_EXPIRY, one whose group has expired meanwhile is dropped
  pure def decoding(st: State): Set[int] =
    NODES.filter(n => st.nodes.get(n).stage == DECODING and (not(DROP_LATE) or st.nodes.get(n).waiters.length() > 0)
                      and not(DECODE_CHECKS_EXPIRY and st.nodes.get(n).expired))
  action decodeAct = all {
    decoding(s) != Set(),
    nondet n = decoding(s).oneOf()
    val nd = s.nodes.get(n)
    // one nondeterministic pick per peer slot (NN ≤ 4)
    nondet r0 = repairOptions(nd, n, 0).oneOf()
    nondet r1 = repairOptions(nd, n, 1).oneOf()
    nondet r2 = repairOptions(nd, n, 2).oneOf()
    nondet r3 = repairOptions(nd, n, 3).oneOf()
    val sel = NODES.mapBy(q => if (q == 0) r0 else if (q == 1) r1 else if (q == 2) r2 else r3)
    s' = { ...s, nodes: s.nodes.set(n, decode(nd, n, sel)) },
  }
  // an adversarial node sends an announcement or a HAVE naming any chunks, to any mesh peer
  pure val ADV_ENTRIES: Set[Entry] =
    CHUNKS.powerset().exclude(Set(Set())).map(b => { ...EMPTY, ihave: b })
      .union(CHUNKS.powerset().map(b => haveEntry(b)))
      .union(if (ADV_FORGE) tuples(CHUNKS, FORGE_KINDS).map(x => { ...EMPTY, chunk: x._1, forged: x._2 }) else Set())
  action advAct = all {
    ADV != Set(), s.published, s.advSent < ADV_MSGS,
    nondet a = ADV.oneOf()
    nondet p = MESH.get(a).oneOf()
    nondet e = ADV_ENTRIES.oneOf()
    s' = { ...s, links: s.links.set((a, p), s.links.get((a, p)).append(e)), advSent: s.advSent + 1 },
  }
  pure def quietRest(st: State): bool = and {
    st.published, busyLinks(st) == Set(), runnableWriters(st) == Set(), timeouts(st) == Set(),
    duePromises(st) == Set(), asksOpen(st) == Set(), lrOpen(st) == Set(), decoding(st) == Set(),
    replayable(st) == Set(),
  }
  pure def quiescent(st: State): bool = quietRest(st) and uninstalled(st) == Set()
  action stutterAct = all { quiescent(s), s' = s }

  action tick = clock' = if (DONE_BY > 0) clock + 1 else clock
  // the deferred chunks resume on the installation, all before anything else happens (on_block_installed
  // replays them in one event, §4.2); the model takes them one per step, ahead of every other event
  action step = all {
    any {
      replayAct,
      all {
        replayable(s) == Set(),
        any {
          publishAct, deliverAct, writerAct, windowTimeoutAct, promiseDueAct, askTimeoutAct, lastResortAct,
          decodeAct, installAct, expireAct, advAct, disconnectAct, stutterAct,
        },
      },
    },
    tick,
  }
  // for probing: the same without block installation
  action stepNoInstall = all {
    any {
      publishAct, deliverAct, writerAct, windowTimeoutAct, promiseDueAct, askTimeoutAct, lastResortAct,
      decodeAct, expireAct, stutterAct,
    },
    tick,
  }

  // ---- properties ----
  // A1, the claim wins (§4.5): no honest node is penalised for an ask after its claim
  val noPenalty = s.penalties.filter(x => not(ADV.contains(x._2))) == Set()
  // W1: slots are conserved and bounded (§7.1)
  val windowConserved = NODES.forall(n => {
    val nd = s.nodes.get(n)
    nd.inFlight == nd.slotHeld.size() + nd.sent.size() and nd.inFlight <= W
  })
  // W2: no lost wake-up: with a slot free, the first writer in line will run
  val noLostWakeup = NODES.forall(n => {
    val nd = s.nodes.get(n)
    (nd.waiters.length() > 0 and nd.inFlight < W) implies nd.runnable.contains(nd.waiters.head())
  })
  // S1: no ask leaves for a chunk held, or after the pull stopped (§6.1, §6.2, §7.2)
  val noStaleAsk = s.badAsk == Set()
  // P4: the source's HAVE names only chunks it has sent, plus the receiver's first chunk (§5.1)
  val p4 = s.badHave == Set()
  // Q1: when nothing is left to happen, every honest node has completed and every slot is back
  // (a node on the other block that never installs the builder's block cannot complete)
  pure def doneOf(st: State, S: Set[int]): bool = S.forall(n => {
    val nd = st.nodes.get(n)
    nd.stage == COMPLETE and nd.inFlight == 0 and nd.slotHeld == Set()
  })
  pure def honestDone(st: State): bool = doneOf(st, NODES.exclude(ADV).exclude(if (EQ_SWITCH) Set() else EQ))
  val noStall = quiescent(s) implies honestDone(s)
  // Q3, eventual completion: by DONE_BY steps every run is quiet, and every honest node complete
  // (Q1 alone holds of a run whose retries never stop)
  val doneBy = (DONE_BY > 0 and clock >= DONE_BY) implies (quiescent(s) and honestDone(s))
  val safety = noPenalty and windowConserved and noLostWakeup and noStaleAsk and p4 and noStall
  // everything but the stall, for the instances where F1 stalls
  val safeNoStall = noPenalty and windowConserved and noLostWakeup and noStaleAsk and p4
  // parking is sound: a peer is never parked for a chunk whose copy from it has arrived (§6.1)
  val noBadPark = s.badPark == Set()
  // no ask leaves for a group past its active lifetime (§4.5, §8.1): checked where the ask is written
  val noExpiredAsk = s.badExpiredAsk == Set()
  // a peer is parked only for an ask it received (§6.1)
  val noParkUnasked = s.badUnsent == Set()
  // after drop_group nothing of the group but HAVEs leaves the node (§3, §4.6)
  val noDropLeak = s.badDrop == Set()
  // L4: a chunk that fails level 1 counts only against a forger: honest nodes send only what passed it (§3)
  val noHonestLvl1Pen = NODES.forall(n => s.nodes.get(n).lvl1Pen.forall(q => ADV.contains(q)))
  // L5: no forged copy closes another peer's promise (an unauthenticated copy must not discharge what
  // a peer owes)
  val noForgedClose = s.badClose == Set()
  // O1: an announcement names only chunks its sender can serve (§4.4, "who can serve"): held, of a
  // group neither dropped nor expired
  val noUnservableIhave = s.badIhave == Set()
  // every property but expiry's (a group may expire before its node completes, so the stall check
  // does not apply with EXPIRY) and the inconsistent code's (nodes short of K wait for good)
  val allProps = safety and noBadPark and noParkUnasked and noDropLeak and noHonestLvl1Pen and noForgedClose and noUnservableIhave
  val badCodeProps = safeNoStall and noBadPark and noParkUnasked and noDropLeak and noHonestLvl1Pen and noForgedClose and noUnservableIhave
  // forgeries against fixes that leave F5 alone (no E): everything but the park for an unsent ask
  val forgeProps = safety and noBadPark and noDropLeak and noHonestLvl1Pen and noForgedClose and noUnservableIhave
  // all of them, and eventual completion
  val liveProps = allProps and doneBy
  // completion alone: at quiescence, and by DONE_BY
  val live = noStall and doneBy
  // with equivocation, a node on the other block parks honest providers whose copies wait for the
  // builder's block (C′'s residual); every other park stays sound, a park by
  // a node that has switched included
  val noBadParkSameBlock = s.badParkSame == Set()
  val eqProps = safety and noBadParkSameBlock and noParkUnasked and noDropLeak and noHonestLvl1Pen and noForgedClose
                and noUnservableIhave and doneBy
  // eqProps but the park monitor: EQ_UNPARK leaves a promise open across the installation, and one
  // whose answer waited or was refused can park its provider again after the switch
  val eqOtherProps = safety and noParkUnasked and noDropLeak and noHonestLvl1Pen and noForgedClose
                     and noUnservableIhave and doneBy
  // witness: a node on the other block has parked a provider whose copy arrived (expected to be violated with EQ)
  val noEqPark = s.badPark == Set()
  // the stall the equivocation itself causes: at quiescence every other honest node completed and a
  // node on the other block, switched, did not (F2's stalls, at any node, are another matter)
  val noEqStall = (EQ_SWITCH and quiescent(s) and doneOf(s, NODES.exclude(ADV).exclude(EQ))) implies doneOf(s, EQ.exclude(ADV))
  // no peer is parked for a promise its closed connection left open (DISC; the ask or the answer went
  // with the connection)
  val noDiscPark = s.badDiscPark == Set()
  val discProps = safety and noBadPark and noParkUnasked and noDropLeak and noHonestLvl1Pen and noForgedClose
                  and noUnservableIhave and doneBy
  // equivocation and disconnects together, with the additions: eqOtherProps, and no park
  // for a closed connection's promise
  val eqDiscProps = eqOtherProps and noDiscPark
  // witness: a node on the other block switched once its providers' answers for a chunk it lacks were
  // spent (EQ_EXHAUST's precondition reached; expected to be violated where it is reachable)
  val noExhaustSwitch = s.exhaustSwitch == Set()
  // everything, with equivocation and disconnects together, where no park of a provider whose answer
  // arrived is allowed at all (ROOT_TIED: a waiting copy closes its sender's promise)
  val fullProps = liveProps and noDiscPark
  // witness: a node on the other block switched with every peer parked, short of K, nothing waiting
  // (expected to be violated with EQ_LATE and a store that refuses)
  val noEqSwitchShort = not(EQ.exists(n => {
    val nd = s.nodes.get(n)
    nd.installed and MESH.get(n).forall(q => nd.parked.contains(q)) and nd.recv.size() < K and nd.pending == Set()
  }))
  // D5: past its active lifetime only the group's tombstone is left (§8.1): an expired node stores
  // nothing of it (F10: a decode that returns after the expiry stores its chunks again)
  val noExpiredStore = NODES.forall(n => s.nodes.get(n).expired implies s.nodes.get(n).stored == Set())
  // with EXPIRY, completion does not apply: every other property, and no ask written past the lifetime
  val expiryProps = safeNoStall and noBadPark and noParkUnasked and noDropLeak and noHonestLvl1Pen and noForgedClose and noExpiredAsk
                    and noUnservableIhave and noExpiredStore
  // witness: two connections closed (expected to be violated where DISC_MAX = 2 and the closes are
  // reachable; with DISC_AT = 5 and DISC_LATE, two closes of a withholder's connections while it owed
  // an answer)
  val noSecondDisc = s.discs < 2
  // with an inconsistent code, nobody delivers, and every node that reached K has dropped the group
  val noBadDelivery = BAD_CODE implies NODES.forall(n => n == SRC or s.nodes.get(n).stage != COMPLETE)
  // witness: an answer is waiting for the block while its promise is open (expected to be violated with BLOCK_GATE)
  val noDeferredAnswer = not(NODES.exists(n => {
    val nd = s.nodes.get(n)
    nd.pending.exists(x => nd.promises.contains((x._2, x._1)))
  }))
  val noUninstalledAsk = not(NODES.exists(n => not(s.nodes.get(n).installed) and CHUNKS.exists(i => s.nodes.get(n).askCount.get(i) > 0)))
  val noPending = NODES.forall(n => s.nodes.get(n).pending == Set())
  val noChunkInFlightToUninstalled = not(NODES.exists(n => not(s.nodes.get(n).installed) and
    NODES.exists(m => s.links.get((m, n)).select(e => e.chunk != NONE).length() > 0)))
  val noArrivedOpenPromise = not(NODES.exists(n => {
    val nd = s.nodes.get(n)
    nd.gotFrom.exists(x => nd.promises.contains((x._2, x._1)))
  }))
  // witness: a run in which every node completes (expected to be violated)
  val notAllComplete = not(NODES.forall(n => s.nodes.get(n).stage == COMPLETE))
}
