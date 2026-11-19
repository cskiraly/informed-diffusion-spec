"""The twin's tables, one entry per table: the schema the Lean code of the tables is generated from (gen.py).

A table has keys (each a variable name and a Lean type, any number of them, outer first), a kind of value, the
name of its field in `State`, of its `Cell` constructor and of its levels, and its operations with the names the
twin's code calls them by. The names of §6.1's eight tables are the hand-written ones, kept, with the two places
where the hand-written text is irregular marked `# kept`.

A table of two or more keys can keep its rows (`rows`, presence): a row that is there is then an entry of its
own, a `Cell` of its level whose value is a flag, with or without anything under it, so that a record's null for a
row always says that the row went. Its last level's value is then one whose empty value is a value too (a kind
with `presence`: `pbits`, a bitmap there and empty is 0, not missing; `lane`, a lane there and empty is []).
"""
from dataclasses import dataclass, field

# kinds of value: the Lean type; how a read answers (an Option, or a default for a missing entry); the write's
# parameter; how the replay writes the value in a record (Val's constructor)
VALUES = {      # in the order of the replay's arms by kind (`val`)
    "time":    dict(lean="Float", read="option", param="t", val="time"),
    "peers":   dict(lean="List Peer", read="default", default="[]", param="o", val="peers", empty="an empty offer list"),
    "peerset": dict(lean="Std.HashSet Peer", read="default", default="{}", param="ps", val="peers", empty="an empty set"),
    "bits":    dict(lean="Bits", read="default", default="0", param="b", val="bits", empty="an empty bitmap"),
    "member":  dict(lean=None, read="member", param="armed", val="flag"),      # a set: its keys are its members
    "count":   dict(lean="Nat", read="default", default="0", param="n", val="count", empty="a count of zero"),
    "askkey":  dict(lean="Key", read="option", param="a", val="key"),
    "state":   dict(lean="GroupState", read="option", param="st", val="state", parse="groupState"),
    "pbits":   dict(lean="Bits", read="option", param="b", val="bits", presence=True),   # 0 is a value
    # a lane of a peer's queue, its entries in order; with presence, [] is a value
    "lane":    dict(lean="List QEntry", read="option", param="es", val="lane", parse="laneEntries", presence=True),
    # a root's waiting copies, in order; and a slot (0 is a value)
    "waits":   dict(lean="List (Peer × ChunkF)", read="default", default="[]", param="w", val="waits", parse="waitList",
                    empty="an empty list of waits"),
    "slot":    dict(lean="Nat", read="option", param="sl", val="slot"),
    # a set kept as a map to bools (the toy's `DefaultMap(False)`, which stores an explicit False): a key is a
    # member where its value is true. The twin's as `member`; the tracer writes a false value as missing
    "flagset": dict(lean=None, read="member", param="armed", val="flag"),
    # what a peer said it holds of a group, and the heartbeats its claim still lives (§4.3). An entry there with no
    # bit is a value: an empty HAVE makes it
    "have":    dict(lean="HaveEntry", read="option", param="e", val="have", parse="haveEntry"),
    # the pace queue's jobs, in order; an empty queue is no value
    "jobs":    dict(lean="List Job", read="default", default="[]", param="js", val="jobs", parse="jobList",
                    empty="an empty pace queue"),
    # a bitmap in a table of one key whose entry there and empty is a value (`origin`: a group published with
    # nothing acknowledged yet is there with 0, and `g in origin` is asked). As `pbits`, which is the same for a
    # table that keeps its rows; as `slot` is for a number
    "obits":   dict(lean="Bits", read="option", param="b", val="bits"),
    # a set of peers in a table that keeps its rows, there and empty a value (`planned[g][i]`, the targets chosen
    # for a chunk: none chosen is a set there). As `peerset`, with presence
    "ppeerset": dict(lean="Std.HashSet Peer", read="option", param="ps", val="peers", presence=True),
    # what the node chose to push a peer of a group, when the first went, and the heartbeats the entry still lives
    # (§5.2's `pushed[p][g]`). An entry there with no bit is a value: unpush clears a bit and keeps the entry, its
    # clock and its ttl
    "push":    dict(lean="PushEntry", read="option", param="e", val="push", parse="pushEntry"),
    # a group's descriptor (§1), whole, as a record's tape writes one
    "desc":    dict(lean="Descriptor", read="option", param="d", val="desc", parse="descriptor"),
    # a signed count (§7.1's `in_flight`: free_slot at 0 leaves -1 on drawn states); 0 where missing. On the wire
    # a natural number, or ["-", n] below zero (a record has no signed number)
    "int":     dict(lean="Int", read="default", default="0", param="n", val="int", empty="a count of zero"),
    # a set of opaque ids, as hex strings (`unwanted[p]`, the ids a peer said it does not want: on_frame adds one,
    # on_iwant asks whether one is there). As `peerset`, of ids
    "idset":   dict(lean="Std.HashSet Hex", read="default", default="{}", param="ids", val="ids", empty="an empty set"),
}
# how a key of each Lean type is read from a record's path
PARSE = {"Key": "key", "Peer": "nat", "Group": "groupKey", "Chunk": "chunk", "Root": "rootKey", "Lane": "laneName",
         "PaceKey": "paceKey", "Nat": "nat",
         "CountKey": "countKey", "LineKey": "lineKey", "SendKey": "sendKey"}       # the window's three


@dataclass
class Scan:
    name: str                   # the operation's name
    level: str                  # the Level constructor
    doc: str
    row: bool = False           # a row of a nested table (one outer key given), not the whole table
    note: str = None            # a comment beside the Level constructor
    used: bool = False          # §-code reads this level: declared among the table's operations, not after them
    depth: int = None           # the outer keys given, for a level below the first row (row: 1, else 0)


@dataclass
class Table:
    name: str                   # the Python's name
    field: str                  # the field of State
    cell: str                   # the Cell constructor
    keys: list                  # [(variable, Lean type)], outer first
    value: str                  # a kind of VALUES
    read: tuple                 # (name, doc)
    write: tuple = None         # (name, doc)
    erase: tuple = None         # (name, doc)
    values_ordered: bool = False    # the order of `t.values()` is asked (`held_back.values()`, the order of the
                                # heartbeat's retries); `tied.values()` is not: `any` over it
    clear: tuple = None         # (name, doc): the whole table emptied (`t.clear()`), a write of every entry there;
                                # for a table of one key (the heartbeat's three)
    scans: list = field(default_factory=list)
    presence_in: bool = False   # `planned`: the Python's `k in t` at a row's level is a read of that row's
                                # presence alone (the tracer's view; the twin's row operation is that read already)
    shape: str = "nested"       # for two keys: "nested" (a map of maps) or "pair" (one map keyed by the pair)
    lift_param: str = None      # kept: the write's parameter in `lift`, where the hand-written text names it otherwise
    rows: list = None           # presence: the Cell constructor of each level's rows, outer first, one per key but
                                # the last; a row there is an entry, a flag
    ordered: bool = False       # the order the Python iterates its top level is asked (`list(queue)`): the tracer
                                # puts it on the tape, the twin asks it of its rows
    ordered_levels: list = field(default_factory=list)   # the depths below the top whose order is asked too,
                                # where the block iterates one, or pops a level above one
    row_ops: list = field(default_factory=list)   # for a table that keeps its rows, per row level
                                # (depth, read, read's doc, erase, erase's doc): whether the row is there (a read of
                                # its cell), and the row erased with all under it (`tied.pop(r)`: the views' pop
                                # writes the row and every entry under it)


TABLES = [
    Table("asked_at", "askedAt", "askedAt", [("a", "Key")], "time",
          read=("askedAt?", "`asked_at.get(a)`"), write=("setAskedAt", "`asked_at[a] = t`"),
          erase=("eraseAskedAt", "`asked_at.pop(a, None)`"),      # close_promises
          scans=[Scan("allAskedAt", "askedAt", "every `asked_at`")]),
    Table("tried", "tried", "tried", [("a", "Key"), ("p", "Peer")], "time",
          read=("tried?", "`tried[a].get(p)`"), write=("setTried", "`tried[a][p] = t`"),
          erase=("eraseTried", "`tried[a].pop(p)`"),               # close_promises, a row's entries
          scans=[Scan("allTriedAll", "triedAll", "every `tried`, under every key", note="every `tried[a][p]`"),
                 Scan("allTried", "tried", "every `tried[a]`", row=True, note="every `tried[a][p]` of one key")]),
    Table("offers", "offers", "offers", [("a", "Key")], "peers",
          read=("offersOf", "`offers[a]`"), write=("setOffers", "`offers[a] = o`"),
          erase=("eraseOffers", "`offers.pop(a, None)`"),          # close_promises
          scans=[Scan("allOffers", "offers", "every offer list")]),
    Table("promises", "promises", "promise", [("a", "Key"), ("p", "Peer")], "time", shape="pair",
          read=("promise?", "`promises.get((a, p))`"), erase=("erasePromise", "`del promises[(a, p)]`"),
          write=("setPromise", "`promises[(a, p)] = t`"),      # filter_entry's promise at the write
          scans=[Scan("allPromises", "promises", "every promise: `for (b, r) in promises`", used=True)]),
    Table("offered", "offered", "offered", [("q", "Peer"), ("g", "Group")], "bits",
          read=("offeredBits", "`offered[q][g]`"), write=("setOffered", "`offered[q][g] = b`"),
          scans=[Scan("allOfferedAll", "offeredAll", "every `offered`, of every peer", note="every `offered[q][g]`"),
                 Scan("allOffered", "offered", "every `offered[q]`", row=True)]),
    Table("park", "park", "park", [("p", "Peer"), ("g", "Group")], "time",
          read=("parkUntil?", "`park[p].get(g)`"), write=("setPark", "`park[p][g] = t`"),
          erase=("erasePark", "`park[p].pop(g, None)`"),         # on_block_installed
          scans=[Scan("allParkAll", "parkAll", "every `park`, of every peer", note="every `park[p][g]`"),
                 Scan("allPark", "park", "every `park[p]`", row=True)]),
    Table("asked_parked", "askedParked", "askedParked", [("k", "Chunk")], "peerset",
          read=("askedParkedOf", "`asked_parked[k]`"), write=("setAskedParked", "`asked_parked[k] = s`"),
          erase=("eraseAskedParked", "`asked_parked.pop(k, None)`"),     # close_promises
          scans=[Scan("allAskedParked", "askedParked", "every `asked_parked`")]),
    Table("last_resort_armed", "lastResortArmed", "lrArmed", [("k", "Chunk")], "member",
          read=("lrArmed?", "`k in last_resort_armed`"),
          write=("setLrArmed", "`last_resort_armed.add(k)`, or `.discard(k)`"),
          scans=[Scan("allLrArmed", "lrArmed", "every member of `last_resort_armed`")],
          lift_param="b"),      # kept
    # §4.4
    Table("ihave_frames", "ihaveFrames", "ihaveFrames", [("p", "Peer")], "count",
          read=("ihaveFrames", "`ihave_frames[p]`"), write=("setIhaveFrames", "`ihave_frames[p] = n`"),
          clear=("clearIhaveFrames", "`ihave_frames.clear()`: a write of every entry there"),
          scans=[Scan("allIhaveFrames", "ihaveFrames", "every `ihave_frames`")]),
    Table("ihave_asked", "ihaveAsked", "ihaveAsked", [("p", "Peer")], "count",
          read=("ihaveAsked", "`ihave_asked[p]`"), write=("setIhaveAsked", "`ihave_asked[p] = n`"),
          clear=("clearIhaveAsked", "`ihave_asked.clear()`: a write of every entry there"),
          scans=[Scan("allIhaveAsked", "ihaveAsked", "every `ihave_asked`")]),
    Table("held_back", "heldBack", "heldBack", [("k", "Chunk")], "askkey",
          read=("heldBack?", "`held_back.get(k)`"), write=("setHeldBack", "`held_back[k] = a`"),
          clear=("clearHeldBack", "`held_back.clear()`: a write of every entry there"), values_ordered=True,
          scans=[Scan("allHeldBack", "heldBack", "every `held_back`: `held_back.values()`", used=True)]),
    # §4.2: the tables its own code writes, `tied` with its rows (presence)
    Table("received", "received", "received", [("g", "Group")], "bits", read=("receivedBits", "`received[g]`"),
          write=("setReceived", "`received[g] = b`"), scans=[Scan("allReceived", "received", "every `received`")]),
    Table("mine", "mine", "mine", [("g", "Group")], "bits", read=("mineBits", "`mine[g]`"),
          write=("setMine", "`mine[g] = b`"), scans=[Scan("allMine", "mine", "every `mine`")]),
    Table("state", "state", "state", [("g", "Group")], "state", read=("state?", "`state[g]`"),
          write=("setState", "`state[g] = st`"), scans=[Scan("allState", "state", "every `state`")]),
    Table("tied", "tied", "tied", [("r", "Root"), ("p", "Peer"), ("g", "Group")], "pbits",
          read=("tied?", "`tied[r][p].get(g)`"), write=("setTied", "`tied[r][p][g] = b`"),
          erase=("eraseTied", "`tied[r][p].pop(g)`"), rows=["tiedRow", "tiedPeerRow"],
          # every level's order is asked, the top's at drop_beyond's `list(tied.items())`, whose roots' peer orders
          # then follow on the tape in that order
          ordered=True, ordered_levels=[1, 2],
          row_ops=[(1, "tiedRow?", "`r in tied`: the row there", "eraseTiedRow", "`tied.pop(r, ...)`: the row and all under it"),
                   (2, "tiedPeerRow?", "`p in tied[r]`: the row there", "eraseTiedPeerRow",
                    "`tied[r].pop(p, ...)`: the row and all under it")],
          scans=[Scan("allTiedAll", "tiedAll", "every `tied`", note="every row and bitmap of `tied`", used=True),
                 Scan("allTiedRoot", "tiedRoot", "every `tied[r]`", row=True, used=True),
                 Scan("allTiedPeer", "tiedPeer", "every `tied[r][p]`", depth=2, used=True)]),
    # §7's queue: one value per lane, its rows kept. The twin's code reads it alone: its writes come as the calls'
    # `cw` on the tape (enqueue, drop_offer, forward, ...)
    Table("queue", "queue", "queue", [("p", "Peer"), ("l", "Lane")], "lane",
          read=("lane?", "`queue[p].normal`, or `queue[p].urgent`"), rows=["queueRow"], ordered=True,
          write=("setLane", "a lane after the writer's pop"),
          # drop_offer: `queue[p].normal = [...]` where p has no queue: the toy's detached queue takes the
          # empty lane and joins no table, so the lane is written and stays missing, and no row is made
          erase=("eraseLane", "a lane assigned empty to a queue that is not there: it stays missing, no row made"),
          scans=[Scan("allQueue", "queueAll", "every `queue[p]`: `list(queue)`", note="every row and lane of `queue`",
                      used=True)]),
    # §4.2's deferral path
    Table("pending", "pending", "pending", [("r", "Root")], "waits",
          read=("pendingOf", "`pending[root]`"), write=("setPending", "`pending[root] = w`"),
          erase=("erasePending", "`pending.pop(root, None)`, `del pending[root]`"), ordered=True,
          scans=[Scan("allPending", "pending", "every `pending`: `list(pending)`", used=True)]),
    Table("pending_ids", "pendingIds", "pendingId", [("m", "Key")], "member",
          read=("pendingId?", "`mid in pending_ids`"),
          write=("setPendingId", "`pending_ids.add(mid)`, or `.discard(mid)`"),
          scans=[Scan("allPendingIds", "pendingIds", "every member of `pending_ids`")]),
    Table("tie_slot", "tieSlot", "tieSlot", [("r", "Root"), ("p", "Peer")], "slot", shape="pair",
          read=("tieSlot?", "`tie_slot.get((root, p))`"), write=("setTieSlot", "`tie_slot[(root, p)] = s`"),
          erase=("eraseTieSlot", "`tie_slot.pop((root, p), None)`"), ordered=True,
          scans=[Scan("allTieSlot", "tieSlot", "every `tie_slot`: `list(tie_slot.items())`", used=True)]),
    # §7.2's writer
    Table("owed", "owed", "owed", [("p", "Peer"), ("g", "Group")], "pbits",
          read=("owed?", "`owed[p].get(g)`"), write=("setOwed", "`owed[p][g] = b`"),
          erase=("eraseOwed", "`owed[p].pop(g)`"), rows=["owedRow"], ordered_levels=[1],
          # `if owed[p]` reads the row whole, its presence too, as the views' scan does
          row_ops=[(1, "owedRow?", "`p in owed`: the row there", "eraseOwedRow", "`owed.pop(p)`: the row and all under it")],
          scans=[Scan("allOwed", "owed", "every `owed[p]`: `if owed[p]`, `list(owed[p])`", row=True, used=True),
                 Scan("allOwedAll", "owedAll", "every `owed`", note="every row and bitmap of `owed`")]),
    Table("owed_answers", "owedAnswers", "owedAnswers", [("p", "Peer"), ("g", "Group")], "bits",
          read=("owedAnswerBits", "`owed_answers[p][g]`"),
          write=("setOwedAnswers", "`owed_answers[p][g] = b`"),     # respond's `.set(i)`
          scans=[Scan("allOwedAnswers", "owedAnswers", "every `owed_answers[p]`: `if owed_answers[p]`", row=True,
                      used=True),
                 Scan("allOwedAnswersAll", "owedAnswersAll", "every `owed_answers`", note="every `owed_answers[p][g]`")]),
    Table("sent_to", "sentTo", "sentTo", [("p", "Peer"), ("g", "Group")], "bits",
          read=("sentToBits", "`sent_to[p][g]`"), write=("setSentTo", "`sent_to[p][g] = b`"),
          scans=[Scan("allSentToAll", "sentToAll", "every `sent_to`", note="every `sent_to[p][g]`")]),
    Table("slot_held", "slotHeld", "slotHeld", [("p", "Peer")], "flagset",
          read=("slotHeld?", "`slot_held[p]`"), write=("setSlotHeld", "`slot_held[p] = True`, or `= False`"),
          scans=[Scan("allSlotHeld", "slotHeld", "every peer whose writer holds a slot")]),
]

# §6.4's pace queue. A list in the node's namespace: one entry, named `jobs` as a lane is named `normal`, whose
# value is the jobs in order. on_heartbeat appends, on_pace_tick pops.
TABLES.append(
    Table("pace_queue", "paceQueue", "paceQueue", [("e", "PaceKey")], "jobs",
          read=("paceJobs", "`pace_queue`, the jobs in order"), write=("setPaceJobs", "`pace_queue` after an append or a pop"),
          scans=[Scan("allPaceQueue", "paceQueue", "the pace queue's one entry")]))

# §6.2's `stop_pull`, the toy's `DefaultMap(False)` as slot_held is. The twin's own since claim_group and
# drop_group, which set it, are the twin's code.
TABLES.append(
    Table("stop_pull", "stopPull", "stopPull", [("g", "Group")], "flagset",
          read=("stopPull", "`stop_pull[g]`"), write=("setStopPull", "`stop_pull[g] = True`"),
          scans=[Scan("allStopPull", "stopPull", "every group stopped")]))

# §4.3's `peer_has` and `holders`, the twin's own since on_have, which writes them, is the twin's code. The
# writer's reads of them (§7.2) are reads of the twin's state.
TABLES.append(
    Table("peer_has", "peerHas", "peerHas", [("p", "Peer"), ("g", "Group")], "have",
          read=("peerHasEntry?", "`peer_has[p][g]`: the entry, or none where p sent no HAVE for g"),
          write=("setPeerHas", "`peer_has[p][g]`'s bits and ttl set"),
          scans=[Scan("allPeerHas", "peerHas", "every `peer_has`")]))
TABLES.append(
    Table("holders", "holders", "holders", [("g", "Group"), ("i", "Nat")], "peerset",
          read=("holdersOf", "`holders[g][i]`"), write=("setHolders", "`holders[g][i] = s`"),
          scans=[Scan("allHolders", "holders", "every `holders`")]))

# §4.5's `serve_count`, how many times an id was served to a peer: the twin's own since on_iwant, which counts,
# is the twin's code. Its second key is a chunk's full id.
TABLES.append(
    Table("serve_count", "serveCount", "serveCount", [("p", "Peer"), ("m", "Key")], "count",
          read=("serveCount", "`serve_count[p][mid]`"), write=("setServeCount", "`serve_count[p][mid] = n`"),
          scans=[Scan("allServeCount", "serveCount", "every `serve_count`")]))

# §5.1's `origin`, at the source the bits of a group acknowledged so far. The twin's own since publish and
# origin_acked, which write it, are the twin's code. Whether a group is there is asked (`g in origin`, have_bits),
# and a group there with no bit is a value: `obits`.
TABLES.append(
    Table("origin", "origin", "origin", [("g", "Group")], "obits",
          read=("origin", "`origin[g]`, as `g in origin` or `origin[g]`: the bitmap, or none where g is not there"),
          write=("setOrigin", "`origin[g] = b`, `origin[g].set(i)`"),
          scans=[Scan("allOrigin", "origin", "every `origin`")]))

# §5.1's `planned`, at the source the peers each chunk of a group was planned for. A row a group, whose presence
# alone on_have asks (`g in planned`); under it a set of peers an index, which origin_acked reads
# (`planned[g].get(i, ())`). publish writes a group's row whole.
TABLES.append(
    Table("planned", "planned", "planned", [("g", "Group"), ("i", "Nat")], "ppeerset",
          read=("plannedTargets?", "`planned[g].get(i)`: the peers chosen for chunk i, or none where i has no entry"),
          write=("setPlanned", "`planned[g][i] = set(targets)`"), rows=["plannedRow"], presence_in=True,
          row_ops=[(1, "planned", "`g in planned`: the row there", "erasePlannedRow", "the row and all under it")],
          scans=[Scan("allPlannedAll", "plannedAll", "every `planned`", note="every row and set of `planned`")]))

# §5.2's `pushed`. The twin's own since note_push and unpush, which write it, are the twin's code. An entry is
# the toy's PushEntry whole: its bits, the time of its first push (none before one) and its ttl. The heartbeat's
# countdown and its deletion of a run-down entry are the simulation's, outside any record: what they leave is what
# the next record reads.
TABLES.append(
    Table("pushed", "pushed", "pushed", [("p", "Peer"), ("g", "Group")], "push",
          read=("pushedEntry?", "`pushed[p][g]`: the entry, or none where nothing was pushed p of g"),
          write=("setPushed", "`pushed[p][g]`'s bits, clock and ttl set"),
          scans=[Scan("allPushed", "pushed", "every `pushed`")]))

# `desc`, a group's descriptor. The twin's own since publish, which writes it (`desc[g] = d`), is the twin's code.
# The node's open_group writes it too, a call on the tape: its write is in the call's log, as its write of `state`
# is. Whether a group is there is asked (`g in desc`).
TABLES.append(
    Table("desc", "desc", "desc", [("g", "Group")], "desc",
          read=("desc", "`desc[g]`, as `g in desc` or `desc[g]`: the group's descriptor, or none where it is not there"),
          write=("setDesc", "`desc[g] = d`"),
          scans=[Scan("allDesc", "desc", "every `desc`")]))

# kept: the order of State's fields in the hand-written text (the tables' order but for these two)
STATE_ORDER = ["asked_at", "tried", "offers", "offered", "promises", "park", "asked_parked", "last_resort_armed",
               "ihave_frames", "ihave_asked", "held_back"]


# §7.1's window. `in_flight`, a number of the namespace, and `waiters`, a deque, are one entry each (named `count`
# and `line`, as the pace queue's is named `jobs`); `sent` is a map from the send key, (peer, group, index), to the
# send's time.
TABLES.append(
    Table("in_flight", "inFlight", "inFlight", [("e", "CountKey")], "int",
          read=("inFlight", "`in_flight`, the slots in use"), write=("setInFlight", "`in_flight += 1`, `in_flight -= 1`"),
          scans=[Scan("allInFlight", "inFlight", "the window's count's one entry")]))
TABLES.append(
    Table("waiters", "waiters", "waiters", [("e", "LineKey")], "peers",
          read=("waitersLine", "`waiters`, the peers in line, in order"),
          write=("setWaitersLine", "`waiters` after a popleft, an append or a remove"),
          scans=[Scan("allWaiters", "waiters", "the line's one entry")]))
TABLES.append(
    Table("sent", "sent", "sent", [("k", "SendKey")], "time",
          read=("sentAt?", "`sent.get(key)`, `key in sent`"), write=("setSentAt", "`sent[key] = now`"),
          erase=("eraseSentAt", "`del sent[key]`, `sent.pop(key)`"),
          scans=[Scan("allSent", "sent", "every `sent`")]))

# `unwanted`, stock gossipsub's IDONTWANT state, is written by the block since on_frame keeps an IDONTWANT's entry
# that is no bitmap there (§4.1). A peer to the set of ids it said it does not want: the set is the entry's value,
# as `asked_parked`'s is (the toy holds both as a lazy map of sets)
TABLES.append(
    Table("unwanted", "unwanted", "unwanted", [("p", "Peer")], "idset",
          read=("unwantedOf", "`unwanted[p]`: the ids p said it does not want"),
          write=("setUnwanted", "`unwanted[p].add(h)`"),
          scans=[Scan("allUnwanted", "unwanted", "every `unwanted`")]))


def python_tables(F, key, fbits, lane=None, waits=None, jobs=None, desc=None):
    """The own tables as the Python tracer's schema lines (footprint.Table): how each key and each value is
    written in a record. `key` writes an ask key, `fbits` a float as its 64 bits, `lane` a lane of a peer's queue
    (the tracer's, which knows the toy's entries)."""
    keyenc = {"Key": key, "Peer": int, "Group": lambda g: g.hex(), "Chunk": lambda c: [c[0].hex(), c[1]],
              "Root": lambda r: r.hex(), "Lane": str, "PaceKey": str, "Nat": int,
              "CountKey": str, "LineKey": str,                      # the window's one-entry tables
              "SendKey": lambda k: [int(k[0]), k[1].hex(), int(k[2])]}
    valenc = {
        "time": fbits,
        "peers": lambda o: list(o) or None,
        "peerset": lambda s: sorted(s) or None,
        "bits": lambda b: b.v or None,
        "member": lambda x: True,
        "flagset": lambda x: True if x else None,     # slot_held's False is no member
        "count": lambda n: n or None,
        "askkey": key,
        "state": lambda s: s,
        "pbits": lambda b: b.v,
        "lane": lane,
        "waits": waits,
        "slot": int,
        "jobs": jobs,
        "have": lambda e: [e.bits.v, int(e.ttl)],     # the toy's HaveEntry (v2's two claims are not §4.3's)
        "obits": lambda b: b.v,                       # 0 is a value
        "ppeerset": lambda s: sorted(s),              # an empty set there is a value
        # the toy's PushEntry, whole: [bits, the first push's time as its 64 bits or null, ttl]
        "push": lambda e: [e.v, None if e.first_push is None else fbits(e.first_push), int(e.ttl)],
        "desc": desc,                                 # the tracer's own writing of a descriptor
        "int": lambda n: None if n == 0 else int(n) if n > 0 else ["-", int(-n)],     # a signed count
        "idset": lambda s: sorted(bytes(x).hex() for x in s) or None,     # ids as hex, sorted
    }
    out = []
    for t in TABLES:
        encs = [keyenc[ty] for _, ty in t.keys]
        if t.shape == "pair" and len(encs) == 2:
            a, b = encs
            encs = [lambda k, a=a, b=b: [a(k[0]), b(k[1])]]      # one level, keyed by the pair
        out.append(F.Table(t.name, encs, valenc[t.value], rows=bool(t.rows),   # a row there: an entry, True
                           ordered=t.ordered, ordered_levels=t.ordered_levels, values_ordered=t.values_ordered,
                           presence_in=t.presence_in))
    return out
