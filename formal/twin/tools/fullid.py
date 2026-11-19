#!/usr/bin/env python3
"""How many records of a trace hold a full id (56 bytes: 112 hex digits) anywhere but in the places where a chunk's
own id stands by design. The record's run (`record.sh`) asks it of each cell's trace, where the answer must be 0:
the document's own nodes ask by index, and never send a full id as an ask.

    python3 fullid.py TRACE.jsonl      a count, on one line
    python3 fullid.py --self-test      its own cases: each must give the count it states

The places a full id stands by design (trace3.py), and the only ones taken out before the search:
- the chunk argument `[group, index, slot, root, id]`: its last member, message_id(f). It is in the args of a record
  of a function that takes a chunk (CHUNK_FNS), and in the tape's validate_chunk, open_group, store, forward,
  admitted, reserve and release;
- the tape's seen, accepted and mark_seen, whose one argument is a chunk's id;
- a queue entry's chunk, the first member of each entry of a lane's value (`queue`'s entries in reads, writes,
  rest, and a callee's cr and cw): a pushed or answered chunk, as the toy queues it;
- the twin's own `pending` and `pending_ids`: each wait's chunk in a `pending` entry's value, and a `pending_ids`
  entry's path, which is a chunk's id (in reads, writes, rest, and a callee's cr and cw). A read of pending_ids on
  the tape is no place, and defer and tie are not on the tape;
- §7.2's writer (the entry in hand is a value): a queue entry's chunk where the writer holds the entry: in the
  `ret` of next_to_send, filter_entry and with_owed, and in the args of filter_entry and with_owed (`[p, entry]`);
  and on next_to_send's tape, track_in_flight's chunk (`[p, chunk]`), pop_owed_answer's answer (a chunk) and
  enqueue's entry (`[p, ["entry", entry], urgent]`, the owed answer queued).
- §6.4's paced gossip: the stock gossip's ids, which are chunks' own ids and no asks (`group_bits` turns them into
  bitmaps before anything is sent): each job's ids in the value of the twin's own `pace_queue` entry (in reads,
  writes, rest, and a callee's cr and cw); and in a record of on_pace_tick or send_gossip (GOSSIP_FNS),
  `group_bits`' question on the tape, and send_gossip's second argument; and in a record of on_heartbeat, those and
  `gossip_ids`' answer.
- §4.1's on_frame and respond, §4.5's on_iwant (an ask answered with our chunk):
  - on_frame is a chunk function: its frame's chunks (the first member of its second argument), and the tape's
    places of the chunk functions, since on_chunk runs inside its record;
  - in a record of on_iwant or on_frame (ANSWER_FNS): `resolve`'s answer (our id at the index asked), `chunk_of`'s
    id and chunk, the id in the path of a read of `unwanted`; on_iwant's `ret`, the answers; in on_frame's, the
    answers of a node's own `on_iwant` on the tape;
  - in a record of respond or on_frame: the chunk of an entry enqueued (an answer), and respond's third argument,
    the answers;
  - in any record, the id in the path of an entry of the twin's own `serve_count`.
  An IWANT's ids, in on_iwant's and on_frame's arguments and in `resolve`'s question, are asks, and count.
- decode_group and push_rebuilt (REBUILT_FNS: level 2 and the repair handle whole chunks): in a record of either,
  `decode_and_reencode`'s answer and `payload_of`'s argument (the rebuilt chunks, each under its index), `store`'s
  chunk, the value of a read of `chunks`, and a chunk enqueued alone (`["chunk", chunk]`).
- §5.3's push order, which ranks peers for one chunk: in a record of choose_push, its first
  argument, the chunk, and the first member of `tiebreak`'s question on its tape, that chunk's id (the toy's
  tie-break is a hash of the chunk's id and the peer's: no ask).
- forward, the twin's own: forward's first argument and candidates_for_source's one argument, each a chunk; and on
  the tape of a record that reached forward (by its `reached`: on_frame, on_chunk, on_validated and the deferral
  path's on_block_installed among them), `gossip_put`'s chunk and the chunk enqueued alone (`["chunk", chunk]`: a
  push); on the tape of a record that reached choose_push, its `tiebreak` questions (the chunk's id).
- publish, the twin's own (the source stores, marks, keeps and queues the chunks it built, each with its own id
  once message_id gave it): on the tape of a record of publish, `mark_seen`'s id, `gossip_put`'s chunk, the value
  of a read of `chunks`, and a chunk enqueued alone. (`store` and `content_id` hold the chunk as built there, with
  no id; `tiebreak` is choose_push's place, which publish reaches.)
The tape's places are taken out only in a record of a function whose code asks them (CHUNK_FNS, the deferral
path's functions among them); under another function, a seen or a mark_seen of a full id counts. Anywhere else,
the id counts: as an ask key in a record's args, its reads, writes, rest or scans, an IWANT on the tape or in a
lane, a callee's cr or cw, or any other member.
"""
import gzip
import json
import re
import sys

FULL = re.compile(r'"[0-9a-f]{112}"')
CHUNK_FNS = ("on_chunk", "on_validated",          # and the deferral path's, whose code asks them too
             "defer", "tie", "tie_room", "on_block_installed", "drop_stale_waits",
             "on_frame",                          # on_chunk runs inside a frame's record
             "committed_descriptor")              # level 1: its second argument is the chunk
ANSWER_FNS = ("on_iwant", "on_frame")             # their code resolves an ask to our chunk
ENQ_ENTRY_FNS = ("next_to_send", "respond", "on_frame")     # their code enqueues an entry with a chunk
REBUILT_FNS = ("decode_group", "push_rebuilt")              # level 2 and the repair
TAPE_CHUNK_AT = {"validate_chunk": 0, "open_group": 1, "store": 2, "forward": 0,
                 "admitted": 1, "reserve": 1, "release": 1,       # the deferral path's
                 "content_id": 0}       # message_id's question of its chunk
TAPE_MID = ("seen", "accepted", "mark_seen")
ENTRY_FNS = ("next_to_send", "filter_entry", "with_owed")   # their `ret` is an entry (or WAIT, or null)
ENTRY_ARG_FNS = ("filter_entry", "with_owed")               #   and these two take one: args [p, entry]
GOSSIP_FNS = ("on_pace_tick", "send_gossip", "on_heartbeat")    # their code asks group_bits of gossip ids;
#   on_heartbeat's also asks the gossip history for them (`gossip_ids`' answer)


def blank_chunk(c):
    """A chunk argument with its id taken out, or the value as it was if it is no chunk argument."""
    if isinstance(c, list) and len(c) in (5, 6) and isinstance(c[4], str):    # 6: wide
        return c[:4] + ["(the chunk's id)"] + c[5:]
    return c


def blank_entry(q):
    """A queue entry as a record writes it, [chunk, control, solicited], with its chunk's id taken out; its control
    (an IWANT's asks among it) stays."""
    if isinstance(q, list) and len(q) == 3:
        return [blank_chunk(q[0])] + q[1:]
    return q


def blank_lanes(entries):
    """A list of footprint entries, [table, path, value], with each queue entry's chunk taken out of a lane's value,
    each wait's chunk out of a `pending` entry's value, and the id out of a `pending_ids` entry's path."""
    out = []
    for e in entries if isinstance(entries, list) else []:
        if (isinstance(e, list) and len(e) == 3 and e[0] == "queue" and isinstance(e[1], list) and len(e[1]) == 2
                and isinstance(e[2], list)):
            e = [e[0], e[1], [[blank_chunk(q[0])] + q[1:] if isinstance(q, list) and q else q for q in e[2]]]
        elif (isinstance(e, list) and len(e) == 3 and e[0] == "pending" and isinstance(e[1], list) and len(e[1]) == 1
                and isinstance(e[2], list)):
            e = [e[0], e[1], [[w[0], blank_chunk(w[1])] if isinstance(w, list) and len(w) == 2 else w for w in e[2]]]
        elif (isinstance(e, list) and len(e) == 3 and e[0] == "pending_ids" and isinstance(e[1], list)
                and len(e[1]) == 1):
            e = [e[0], ["(the chunk's id)"], e[2]]
        elif (isinstance(e, list) and len(e) == 3 and e[0] == "serve_count" and isinstance(e[1], list)
                and len(e[1]) == 2):                # [peer, the chunk's id]
            e = [e[0], [e[1][0], "(the chunk's id)"], e[2]]
        elif (isinstance(e, list) and len(e) == 3 and e[0] == "pace_queue" and e[1] == ["jobs"]
                and isinstance(e[2], list)):        # each job's gossip ids
            e = [e[0], e[1], [[j[0], "(gossip ids)", j[2]] if isinstance(j, list) and len(j) == 3 else j for j in e[2]]]
        out.append(e)
    return out


def strip(d):
    """The record with the places a chunk's id stands by design taken out: the tape's and the args', in the records of
    CHUNK_FNS; and in any record a queue entry's chunk, a wait's, and a pending id."""
    for k in ("reads", "writes", "rest"):
        if k in d:
            d[k] = blank_lanes(d[k])
    chunk_fn = d.get("fn") in CHUNK_FNS or d.get("fn") == "message_id"
    if d.get("fn") == "validate_chunk" and isinstance(d.get("args"), list) and len(d["args"]) == 1:
        d["args"] = [blank_chunk(d["args"][0])]                         # level 1: its one argument is a chunk
    if d.get("fn") == "message_id":     # a record of message_id itself: its one argument is a
        if isinstance(d.get("args"), list) and len(d["args"]) == 1:     # chunk, and its return value that chunk's id
            d["args"] = [blank_chunk(d["args"][0])]
        if isinstance(d.get("ret"), str):
            d["ret"] = "(the chunk's id)"
    if d.get("fn") == "on_frame" and isinstance(d.get("args"), list) and len(d["args"]) == 2:
        fr = d["args"][1]                                               # [chunks, ihave, iwant, idontwant]
        if isinstance(fr, list) and len(fr) == 4 and isinstance(fr[0], list):
            d["args"] = [d["args"][0], [[blank_chunk(c) for c in fr[0]]] + fr[1:]]
    elif chunk_fn and isinstance(d.get("args"), list) and len(d["args"]) >= 2:
        d["args"] = [d["args"][0], blank_chunk(d["args"][1])] + d["args"][2:]
    answers = d.get("fn") in ANSWER_FNS
    if d.get("fn") == "on_iwant" and isinstance(d.get("ret"), list):    # the answers
        d["ret"] = [blank_chunk(c) for c in d["ret"]]
    if d.get("fn") == "respond" and isinstance(d.get("args"), list) and len(d["args"]) == 4 and isinstance(d["args"][2], list):
        d["args"] = d["args"][:2] + [[blank_chunk(c) for c in d["args"][2]]] + d["args"][3:]
    if d.get("fn") in ENTRY_FNS and "ret" in d:                         # the entry in hand, returned
        d["ret"] = blank_entry(d["ret"])
    if d.get("fn") in ENTRY_ARG_FNS and isinstance(d.get("args"), list) and len(d["args"]) == 2:
        d["args"] = [d["args"][0], blank_entry(d["args"][1])]           #   and taken
    gossip = d.get("fn") in GOSSIP_FNS
    if d.get("fn") == "send_gossip" and isinstance(d.get("args"), list) and len(d["args"]) == 2:
        d["args"] = [d["args"][0], "(gossip ids)"]                      # send_gossip(q, ids)
    reached = d.get("reached") if isinstance(d.get("reached"), list) else []
    push_order = d.get("fn") == "choose_push" or "choose_push" in reached     # its code asks a
    #                                                                            chunk's tie-break for a peer
    if d.get("fn") == "choose_push" and isinstance(d.get("args"), list) and len(d["args"]) == 4:
        d["args"] = [blank_chunk(d["args"][0])] + d["args"][1:]                     # [chunk, cands, budget, at_source]
    if d.get("fn") == "forward" and isinstance(d.get("args"), list) and len(d["args"]) == 2:
        d["args"] = [blank_chunk(d["args"][0]), d["args"][1]]                       # [chunk, from_peer]
    if d.get("fn") == "candidates_for_source" and isinstance(d.get("args"), list) and len(d["args"]) == 1:
        d["args"] = [blank_chunk(d["args"][0])]
    forwards = d.get("fn") == "forward" or "forward" in reached            # the record ran forward
    publishes = d.get("fn") == "publish"                                   # the source's own chunks
    writer = d.get("fn") == "next_to_send"
    enq_entry = d.get("fn") in ENQ_ENTRY_FNS
    tape = []
    for t in d.get("tape", []):
        if isinstance(t, list) and t and isinstance(t[-1], dict):       # a callee's log: its lanes' chunks
            t = t[:-1] + [{k: blank_lanes(v) for k, v in t[-1].items()}]
        if isinstance(t, list) and t and writer:                        # next_to_send's tape
            if t[0] == "track_in_flight" and len(t) >= 2 and isinstance(t[1], list) and len(t[1]) == 2:
                t = [t[0], [t[1][0], blank_chunk(t[1][1])]] + t[2:]
            elif t[0] == "pop_owed_answer" and len(t) >= 3:
                t = t[:2] + [blank_chunk(t[2])] + t[3:]
        if (isinstance(t, list) and t and enq_entry and t[0] == "enqueue" and len(t) >= 2 and isinstance(t[1], list)
                and len(t[1]) >= 2 and isinstance(t[1][1], list) and len(t[1][1]) == 2 and t[1][1][0] == "entry"):
            t = [t[0], [t[1][0], ["entry", blank_entry(t[1][1][1])]] + t[1][2:]] + t[2:]
        if isinstance(t, list) and len(t) >= 3 and d.get("fn") in REBUILT_FNS:    # the rebuilt chunks
            pairs = lambda l: [[x[0], blank_chunk(x[1])] if isinstance(x, list) and len(x) == 2 else x for x in l]  # noqa: E731
            if t[0] == "decode_and_reencode" and isinstance(t[2], list):
                t = t[:2] + [pairs(t[2])] + t[3:]
            elif t[0] == "payload_of" and isinstance(t[1], list) and len(t[1]) == 1 and isinstance(t[1][0], list):
                t = [t[0], [pairs(t[1][0])]] + t[2:]
            elif t[0] == "store" and isinstance(t[1], list) and len(t[1]) == 3:
                t = [t[0], t[1][:2] + [blank_chunk(t[1][2])]] + t[2:]
            elif t[0] == "read" and len(t) == 4 and t[1] == "chunks":
                t = t[:3] + [blank_chunk(t[3])]
            elif (t[0] == "enqueue" and isinstance(t[1], list) and len(t[1]) >= 2 and isinstance(t[1][1], list)
                    and len(t[1][1]) == 2 and t[1][1][0] == "chunk"):
                t = [t[0], [t[1][0], ["chunk", blank_chunk(t[1][1][1])]] + t[1][2:]] + t[2:]
        if isinstance(t, list) and len(t) >= 3 and answers:             # an ask resolved
            if t[0] == "resolve" and isinstance(t[2], str):
                t = t[:2] + ["(the chunk's id)"] + t[3:]
            elif t[0] == "chunk_of" and isinstance(t[1], list) and len(t[1]) == 1:
                t = [t[0], ["(the chunk's id)"], blank_chunk(t[2])] + t[3:]
            elif t[0] == "read" and len(t) == 4 and t[1] == "unwanted" and isinstance(t[2], list) and len(t[2]) == 2:
                t = [t[0], t[1], [t[2][0], "(the chunk's id)"], t[3]]
            elif t[0] == "on_iwant" and d.get("fn") == "on_frame" and isinstance(t[2], list):
                t = t[:2] + [[blank_chunk(c) for c in t[2]]] + t[3:]
        if (isinstance(t, list) and t and gossip and t[0] == "group_bits" and len(t) >= 2 and isinstance(t[1], list)
                and len(t[1]) == 1):                                    # group_bits(ids)
            t = [t[0], ["(gossip ids)"]] + t[2:]
        if (isinstance(t, list) and len(t) >= 3 and d.get("fn") == "on_heartbeat" and t[0] == "gossip_ids"
                and t[1] == []):                                        # gossip_history.gossip_ids()
            t = [t[0], t[1], "(gossip ids)"] + t[3:]
        if (isinstance(t, list) and len(t) >= 2 and push_order and t[0] == "tiebreak" and isinstance(t[1], list)
                and len(t[1]) == 2):                                    # tiebreak(the chunk's id, p)
            t = [t[0], ["(the chunk's id)", t[1][1]]] + t[2:]
        if isinstance(t, list) and len(t) >= 2 and forwards and isinstance(t[1], list):     # forward's calls
            if t[0] == "gossip_put" and len(t[1]) == 1:
                t = [t[0], [blank_chunk(t[1][0])]] + t[2:]
            elif (t[0] == "enqueue" and len(t[1]) >= 2 and isinstance(t[1][1], list) and len(t[1][1]) == 2
                    and t[1][1][0] == "chunk"):
                t = [t[0], [t[1][0], ["chunk", blank_chunk(t[1][1][1])]] + t[1][2:]] + t[2:]
        if isinstance(t, list) and len(t) >= 2 and publishes:                # publish's calls
            if t[0] == "mark_seen" and isinstance(t[1], list) and len(t[1]) == 1:
                t = [t[0], ["(the chunk's id)"]] + t[2:]
            elif t[0] == "gossip_put" and isinstance(t[1], list) and len(t[1]) == 1:
                t = [t[0], [blank_chunk(t[1][0])]] + t[2:]
            elif t[0] == "read" and len(t) == 4 and t[1] == "chunks":
                t = t[:3] + [blank_chunk(t[3])]
            elif (t[0] == "enqueue" and isinstance(t[1], list) and len(t[1]) >= 2 and isinstance(t[1][1], list)
                    and len(t[1][1]) == 2 and t[1][1][0] == "chunk"):
                t = [t[0], [t[1][0], ["chunk", blank_chunk(t[1][1][1])]] + t[1][2:]] + t[2:]
        if isinstance(t, list) and t and chunk_fn:
            if t[0] in TAPE_CHUNK_AT and len(t) >= 2 and isinstance(t[1], list):
                at = TAPE_CHUNK_AT[t[0]]
                if at < len(t[1]):
                    t = [t[0], t[1][:at] + [blank_chunk(t[1][at])] + t[1][at + 1:]] + t[2:]
            elif t[0] in TAPE_MID and len(t) >= 2 and isinstance(t[1], list) and len(t[1]) == 1:
                t = [t[0], ["(the chunk's id)"]] + t[2:]
        tape.append(t)
    if "tape" in d:
        d["tape"] = tape
    return d


def count(lines):
    n = 0
    for line in lines:
        if not FULL.search(line):       # most lines hold no full id at all: they are not parsed
            continue
        d = json.loads(line)
        if "fn" in d:
            d = strip(d)
        if FULL.search(json.dumps(d, separators=(",", ":"))):
            n += 1
    return n


def self_test():
    g = "11" * 32
    mid = g + "01000000" + "ab" * 20
    other = g + "02000000" + "cd" * 20
    chunk = [g, 1, 1, "22" * 32, mid]
    cases = [
        # the push order: one place a case, and the same entry under another function
        ("choose_push's chunk in its record's args", 0,
         {"fn": "choose_push", "args": [chunk, [4, 5], 1, True], "tape": [], "ret": [5]}),
        ("the chunk's id in tiebreak's question, under choose_push", 0,
         {"fn": "choose_push", "args": [[g, 1, 1, "22" * 32, "(no id)"], [4, 5], 1, True],
          "tape": [["tiebreak", [mid, 4], 7], ["peer_id_bytes", [4], "0004"]], "ret": [5]}),
        ("the chunk's id in tiebreak's question, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["tiebreak", [mid, 4], 7]]}),
        ("a full id as tiebreak's answer, under choose_push: no place, so it counts", 1,
         {"fn": "choose_push", "args": [[g, 1, 1, "22" * 32, "(no id)"], [4], 0, True], "tape": [["tiebreak", ["(x)", 4], other]]}),
        # forward: one place a case, and the same entry under another function
        ("forward's chunk in its record's args", 0, {"fn": "forward", "args": [chunk, 4], "tape": []}),
        ("candidates_for_source's chunk in its record's args", 0,
         {"fn": "candidates_for_source", "args": [chunk], "tape": [], "ret": [4]}),
        ("gossip_put's chunk, under on_validated", 0,
         {"fn": "on_validated", "args": [4, [g, 1, 1, "22" * 32, "(no id)"], "ACCEPT"], "tape": [["gossip_put", [chunk], None]],
          "reached": ["forward", "on_validated"]}),
        ("gossip_put's chunk, under on_block_installed that reached forward (the deferral path)", 0,
         {"fn": "on_block_installed", "args": ["22" * 32], "tape": [["gossip_put", [chunk], None]],
          "reached": ["forward", "on_block_installed", "on_validated"]}),
        ("gossip_put's chunk, under on_validated that did not reach forward", 1,
         {"fn": "on_validated", "args": [4, [g, 1, 1, "22" * 32, "(no id)"], "ACCEPT"], "tape": [["gossip_put", [chunk], None]],
          "reached": ["on_validated"]}),
        ("gossip_put's chunk, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["gossip_put", [chunk], None]]}),
        ("a chunk enqueued alone, under forward", 0,
         {"fn": "forward", "args": [[g, 1, 1, "22" * 32, "(no id)"], 4], "tape": [["enqueue", [5, ["chunk", chunk], False], True]]}),
        ("a chunk enqueued alone, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["enqueue", [5, ["chunk", chunk], False], True]]}),
        ("the chunk's id in tiebreak's question, under on_frame", 0,
         {"fn": "on_frame", "args": [4, [[], [], [], []]], "tape": [["tiebreak", [mid, 4], 7]],
          "reached": ["choose_push", "forward", "on_frame"]}),
        # publish's places, one a case; the same entries under another function count (above:
        # mark_seen, gossip_put and a chunk enqueued alone under send_have), and an ask on publish's tape counts
        ("mark_seen's id, under publish", 0,
         {"fn": "publish", "args": [[1, None, None], [2, 0, 1, 2, 5, 5, "22" * 32], []], "tape": [["mark_seen", [mid], None]]}),
        ("gossip_put's chunk, under publish", 0,
         {"fn": "publish", "args": [[1, None, None], [2, 0, 1, 2, 5, 5, "22" * 32], []], "tape": [["gossip_put", [chunk], None]]}),
        ("the value of a read of chunks, under publish", 0,
         {"fn": "publish", "args": [[1, None, None], [2, 0, 1, 2, 5, 5, "22" * 32], []], "tape": [["read", "chunks", [g, 1], chunk]]}),
        ("a chunk enqueued alone, under publish", 0,
         {"fn": "publish", "args": [[1, None, None], [2, 0, 1, 2, 5, 5, "22" * 32], []],
          "tape": [["enqueue", [5, ["chunk", chunk], False], True]]}),
        ("the value of a read of chunks, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["read", "chunks", [g, 1], chunk]]}),
        ("a full id in an IWANT on publish's tape: an ask, so it counts", 1,
         {"fn": "publish", "args": [[1, None, None], [2, 0, 1, 2, 5, 5, "22" * 32], []],
          "tape": [["enqueue", [4, [["iwant", [other]]], False], True]]}),
        ("a chunk function's record: the chunk's id where it stands by design", 0,
         {"fn": "on_chunk", "args": [4, chunk], "tape": [["seen", [mid], False],
                                                       ["validate_chunk", [chunk], "ACCEPT"], ["mark_seen", [mid], None],
                                                       ["open_group", [g, chunk], None], ["store", [g, 1, chunk], None],
                                                       ["forward", [chunk, 4], None], ["accepted", [mid], True]],
          "reads": [], "writes": [], "rest": []}),
        # the deferral path and its waits: one place a case
        ("on_validated's chunk on admitted's tape entry", 0,
         {"fn": "on_validated", "args": [4, chunk, "DEFER"], "tape": [["admitted", [4, chunk], True]]}),
        ("on_validated's chunk on reserve's tape entry", 0,
         {"fn": "on_validated", "args": [4, chunk, "DEFER"], "tape": [["reserve", [4, chunk], True]]}),
        ("a chunk on release's tape entry, under on_block_installed", 0,
         {"fn": "on_block_installed", "args": ["22" * 32], "tape": [["release", [4, chunk], None]]}),
        ("a chunk on validate_chunk's tape entry, under drop_stale_waits' (none asks it there, but the place is "
         "one of the deferral path's)", 0,
         {"fn": "drop_stale_waits", "args": [], "tape": [["validate_chunk", [chunk], "ACCEPT"]]}),
        ("defer's chunk in its record's args (a directed record)", 0, {"fn": "defer", "args": [4, chunk]}),
        ("a chunk's id on admitted's tape entry, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["admitted", [4, chunk], True]]}),
        ("a wait's chunk in pending's value, in a read", 0,
         {"fn": "send_have", "args": [4, g], "reads": [["pending", ["22" * 32], [[4, chunk]]]]}),
        ("a wait's chunk in pending's value, in a callee's cw", 0,
         {"fn": "on_chunk", "args": [4, chunk],
          "tape": [["forward", [chunk, 4], None, {"cr": [], "cw": [["pending", ["22" * 32], [[4, chunk]]]]}]]}),
        ("a pending id, in a write", 0,
         {"fn": "send_have", "args": [4, g], "writes": [["pending_ids", [mid], None]]}),
        ("a pending id, in the rest", 0,
         {"fn": "send_have", "args": [4, g], "rest": [["pending_ids", [mid], True]]}),
        ("a full id in a value of another table of pending's shape: not pending's, so it counts", 1,
         {"fn": "send_have", "args": [4, g], "reads": [["pendings", ["22" * 32], [[4, chunk]]]]}),
        ("a chunk's id in a tape read of pending_ids, a read of pending_ids on the tape: no place, so it counts", 1,
         {"fn": "on_chunk", "args": [4, chunk], "tape": [["read", "pending_ids", [mid], None]]}),
        ("a full id as an ask key in a record's args", 1, {"fn": "may_ask", "args": [other, 4], "tape": []}),
        ("a full id in an IWANT on the tape", 1,
         {"fn": "on_ihave", "args": [4, []], "tape": [["enqueue", [4, [["iwant", [other]]], False], True]]}),
        ("a full id as a key of a read", 1, {"fn": "retry_offer", "args": [[g, 1]], "reads": [["asked_at", [other], 1]]}),
        ("a full id in a callee's log", 1,
         {"fn": "on_chunk", "args": [4, chunk], "tape": [["tie", [4, chunk], None, {"cr": [], "cw": [["promises", [[other, 4]], None]]}]]}),
        ("a full id in a chunk's place but under another function", 1, {"fn": "send_have", "args": [4, chunk]}),
        ("another id where a chunk's id stands is still taken out: only the place counts", 0,
         {"fn": "on_chunk", "args": [4, [g, 1, 1, "22" * 32, other]], "tape": []}),
        # the tape's places are CHUNK_FNS' alone; one place a case (two in one case would pass if either alone were
        # taken out)
        ("a chunk's id on seen's tape entry, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["seen", [mid], False]]}),
        ("a chunk's id on accepted's tape entry, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["accepted", [mid], True]]}),
        ("a chunk's id on mark_seen's tape entry, under another function", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["mark_seen", [mid], None]]}),
        ("a chunk's id in store's chunk, under another function", 1,
         {"fn": "drop_beyond", "args": [g], "tape": [["store", [g, 1, chunk], None]]}),
        # a queue entry's chunk is taken out, wherever a lane's value stands; an ask is not
        ("a queue entry's chunk, in a read, a write and a callee's log", 0,
         {"fn": "send_have", "args": [4, g], "reads": [["queue", [4, "normal"], [[chunk, None, False]]]],
          "writes": [["queue", [4, "normal"], [[chunk, None, True]]]],
          "tape": [["enqueue", [4, [["idontwant", [["bits", g, 2]]]], True], True,
                    {"cr": [["queue", [5, "normal"], [[chunk, None, False]]]], "cw": [["queue", [5, "normal"], []]]}]]}),
        ("a queue entry's chunk in the rest alone", 0,
         {"fn": "outstanding", "args": [4, [g, 1]], "rest": [["queue", [4, "normal"], [[chunk, None, False]]]]}),
        ("a queue entry's chunk in a callee's cw alone", 0,
         {"fn": "on_validated", "args": [4, chunk, "ACCEPT"],
          "tape": [["forward", [chunk, 4], None, {"cr": [], "cw": [["queue", [5, "normal"], [[chunk, None, False]]]]}]]}),
        ("a full id as an IWANT's ask in a lane's value", 1,
         {"fn": "outstanding", "args": [4, [g, 1]], "reads": [["queue", [4, "normal"], [[None, [["iwant", [other]]], False]]]]}),
        ("a full id in a lane of another table's name: not a queue's, so it counts", 1,
         {"fn": "outstanding", "args": [4, [g, 1]], "reads": [["queues", [4, "normal"], [[chunk, None, False]]]]}),
        # §7.2's writer: one place a case, each with its counterpart that must still count
        ("next_to_send's returned entry's chunk", 0,
         {"fn": "next_to_send", "args": [4], "tape": [], "ret": [chunk, None, False]}),
        ("next_to_send's chunk on track_in_flight's tape entry", 0,
         {"fn": "next_to_send", "args": [4], "tape": [["track_in_flight", [4, chunk], None]], "ret": None}),
        ("next_to_send's owed answer on pop_owed_answer's tape entry", 0,
         {"fn": "next_to_send", "args": [4], "ret": None,
          "tape": [["pop_owed_answer", [4], chunk, {"cr": [["owed_answers", [4, g], 2]], "cw": [["owed_answers", [4, g], None]]}]]}),
        ("next_to_send's owed answer queued, on enqueue's tape entry", 0,
         {"fn": "next_to_send", "args": [4], "ret": None,
          "tape": [["enqueue", [4, ["entry", [chunk, None, True]], False], True]]}),
        ("with_owed's entry in its args (v2's choose calls it)", 0,
         {"fn": "with_owed", "args": [4, [chunk, None, False]], "tape": [], "ret": None}),
        ("with_owed's returned entry", 0,
         {"fn": "with_owed", "args": [4, [None, None, False]], "tape": [], "ret": [chunk, None, False]}),
        ("filter_entry's entry in its args (a directed record)", 0,
         {"fn": "filter_entry", "args": [4, [chunk, None, False]], "tape": [], "ret": None}),
        ("filter_entry's returned entry", 0,
         {"fn": "filter_entry", "args": [4, [None, None, False]], "tape": [], "ret": [chunk, None, False]}),
        ("a full id as an IWANT's ask in next_to_send's returned entry: an ask, so it counts", 1,
         {"fn": "next_to_send", "args": [4], "tape": [], "ret": [None, [["iwant", [other]]], False]}),
        ("a full id as an IWANT's ask in with_owed's entry: an ask, so it counts", 1,
         {"fn": "with_owed", "args": [4, [None, [["iwant", [other]]], False]], "tape": [], "ret": None}),
        ("a chunk on track_in_flight's tape entry, under another function", 1,
         {"fn": "retry_offer", "args": [[g, 1]], "tape": [["track_in_flight", [4, chunk], None]]}),
        ("a chunk on enqueue's entry, under another function", 1,
         {"fn": "retry_offer", "args": [[g, 1]], "tape": [["enqueue", [4, ["entry", [chunk, None, True]], False], True]]}),
        ("an entry's chunk in the ret of a function that returns none", 1,
         {"fn": "outstanding", "args": [4, [g, 1]], "tape": [], "ret": [chunk, None, False]}),
    ]
    cases += [  # message_id's own record, and its question where the block's code calls it
        ("a record of message_id: its chunk, its content_id's chunk, its return value", 0,
         {"fn": "message_id", "args": [chunk], "tape": [["content_id", [chunk], "ab" * 20]], "ret": mid}),
        ("a record of message_id with another full id on its tape", 1,
         {"fn": "message_id", "args": [chunk], "tape": [["content_id", [chunk], "ab" * 20], ["seen", [other], False],
                                                        ["enqueue", [4, [["iwant", [other]]], False], True]], "ret": mid}),
        ("on_chunk with message_id's question on its tape", 0,
         {"fn": "on_chunk", "args": [4, chunk], "tape": [["content_id", [chunk], "ab" * 20], ["seen", [mid], False]],
          "reads": [], "writes": [], "rest": []}),
        ("content_id's chunk on the tape of a function that takes no chunk", 1,
         {"fn": "retry_offer", "args": [[g, 1]], "tape": [["content_id", [chunk], "ab" * 20]]}),
    ]
    job, bits = [4, [mid, other], 1], [[g, 6]]
    cases += [  # §6.4's paced gossip: one place a case, each with a counterpart that must count
        ("a job's gossip ids in the pace queue's value, in a read", 0,
         {"fn": "on_pace_tick", "args": [], "reads": [["pace_queue", ["jobs"], [job]]], "tape": []}),
        ("a job's gossip ids in the pace queue's value, in a write", 0,
         {"fn": "on_pace_tick", "args": [], "writes": [["pace_queue", ["jobs"], [job]]], "tape": []}),
        ("a job's gossip ids in the pace queue's value, in the rest of another function's record", 0,
         {"fn": "send_have", "args": [4, g], "rest": [["pace_queue", ["jobs"], [job]]]}),
        ("a job's gossip ids in the pace queue's value, in a callee's cw", 0,
         {"fn": "send_have", "args": [4, g],
          "tape": [["enqueue", [4, [["idontwant", [["bits", g, 2]]]], True], True, {"cr": [], "cw": [["pace_queue", ["jobs"], [job]]]}]]}),
        ("group_bits' question on on_pace_tick's tape", 0,
         {"fn": "on_pace_tick", "args": [], "tape": [["connected", [4], True], ["group_bits", [[mid, other]], bits]]}),
        ("send_gossip's ids in its args, and group_bits' question on its tape", 0,
         {"fn": "send_gossip", "args": [4, [mid, other]], "tape": [["group_bits", [[mid, other]], bits]]}),
        ("send_gossip's ids in its args alone", 0, {"fn": "send_gossip", "args": [4, [mid]], "tape": []}),
        ("group_bits' question on the tape of another function: no place, so it counts", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["group_bits", [[mid]], bits]]}),
        ("a full id in a job's peer's place: not its ids, so it counts", 1,
         {"fn": "on_pace_tick", "args": [], "reads": [["pace_queue", ["jobs"], [[mid, [], 1]]]], "tape": []}),
        ("a full id in a value of another table of the pace queue's shape: so it counts", 1,
         {"fn": "on_pace_tick", "args": [], "reads": [["pace_queues", ["jobs"], [job]]], "tape": []}),
        ("a full id in group_bits' answer: no place, so it counts", 1,
         {"fn": "on_pace_tick", "args": [], "tape": [["group_bits", [[mid]], [[other, 6]]]]}),
        ("a full id as an ask on on_pace_tick's tape: an ask, so it counts", 1,
         {"fn": "on_pace_tick", "args": [], "tape": [["enqueue", [4, [["iwant", [other]]], False], True]]}),
        ("a full id in the ids' place of an argument of another function", 1,
         {"fn": "outstanding", "args": [4, [mid]]}),
        ("gossip_ids' answer on on_heartbeat's tape", 0,
         {"fn": "on_heartbeat", "args": [], "tape": [["gossip_ids", [], [mid, other]]]}),
        ("group_bits' question on on_heartbeat's tape (gossip not paced)", 0,
         {"fn": "on_heartbeat", "args": [], "tape": [["group_bits", [[mid, other]], bits]]}),
        ("gossip_ids' answer on the tape of another function: no place, so it counts", 1,
         {"fn": "on_pace_tick", "args": [], "tape": [["gossip_ids", [], [mid]]]}),
        ("a full id as an ask held back, in on_heartbeat's record: an ask, so it counts", 1,
         {"fn": "on_heartbeat", "args": [], "tape": [], "writes": [["held_back", [[g, 1]], None]],
          "rest": [["held_back", [[g, 1]], other]]}),
    ]
    ask = [g, 1]
    cases += [  # §4.1 and §4.5, an ask answered: one place a case, each with a counterpart that must count
        ("on_frame's chunk in its frame, and seen's id on its tape", 0,
         {"fn": "on_frame", "args": [4, [[chunk], [], [], []]], "tape": [["seen", [mid], False]]}),
        ("on_frame with a full id among its frame's IWANT ids: an ask, so it counts", 1,
         {"fn": "on_frame", "args": [4, [[], [], [other], []]], "tape": []}),
        ("on_frame with a full id among its frame's IHAVE ids: so it counts", 1,
         {"fn": "on_frame", "args": [4, [[], [other], [], []]], "tape": []}),
        ("on_iwant: resolve's answer", 0,
         {"fn": "on_iwant", "args": [4, [ask]], "tape": [["resolve", [ask], mid]], "ret": []}),
        ("on_iwant: chunk_of's id and chunk, and the answers returned", 0,
         {"fn": "on_iwant", "args": [4, [ask]], "tape": [["chunk_of", [mid], chunk]], "ret": [chunk]}),
        ("on_iwant: the id in the path of a read of unwanted", 0,
         {"fn": "on_iwant", "args": [4, [ask]], "tape": [["read", "unwanted", [4, mid], None]], "ret": []}),
        ("on_iwant: the id in serve_count's path, in a read and a write", 0,
         {"fn": "on_iwant", "args": [4, [ask]], "tape": [], "ret": [], "reads": [["serve_count", [4, mid], None]],
          "writes": [["serve_count", [4, mid], 1]]}),
        ("serve_count's path in the rest of another function's record", 0,
         {"fn": "send_have", "args": [4, g], "rest": [["serve_count", [4, mid], 2]]}),
        ("on_iwant asked by a full id: an ask, in its argument and in resolve's question, so it counts", 1,
         {"fn": "on_iwant", "args": [4, [other]], "tape": [["resolve", [other], None]], "ret": []}),
        ("resolve's answer on the tape of another function: no place, so it counts", 1,
         {"fn": "retry_offer", "args": [ask], "tape": [["resolve", [ask], mid]]}),
        ("a full id in serve_count's peer's place: so it counts", 1,
         {"fn": "on_iwant", "args": [4, [ask]], "tape": [], "ret": [], "reads": [["serve_count", [mid, 4], None]]}),
        ("respond: its answers, and the entry it enqueues", 0,
         {"fn": "respond", "args": [4, [ask], [chunk], 0],
          "tape": [["enqueue", [4, ["entry", [chunk, [["iwant", [ask]], ["prune", []]], True]], False], True]]}),
        ("respond with a full id among its asks: an ask, so it counts", 1,
         {"fn": "respond", "args": [4, [other], [], 0], "tape": []}),
        ("on_frame: an answer enqueued, and a node's own on_iwant's answers on the tape", 0,
         {"fn": "on_frame", "args": [4, [[], [], [ask], []]],
          "tape": [["on_iwant", [4, [ask]], [chunk]],
                   ["enqueue", [4, ["entry", [chunk, None, True]], False], True]]}),
        ("a node's on_iwant's answers on the tape of another function: so it counts", 1,
         {"fn": "respond", "args": [4, [], [], 0], "tape": [["on_iwant", [4, [ask]], [chunk]]]}),
        ("an entry enqueued with a chunk under a function that enqueues none: so it counts", 1,
         {"fn": "on_ihave", "args": [4, []], "tape": [["enqueue", [4, ["entry", [chunk, None, True]], False], True]]}),
    ]
    cases += [  # decode_group and push_rebuilt: one place a case, each with a counterpart that must count
        ("decode_group: the rebuilt chunks, decode_and_reencode's answer", 0,
         {"fn": "decode_group", "args": [g], "tape": [["decode_and_reencode", [g, [2, 0, 1, 4, 4, 8, "d0" * 32]], [[1, chunk]]]]}),
        ("decode_group: payload_of's argument", 0,
         {"fn": "decode_group", "args": [g], "tape": [["payload_of", [[[1, chunk]]], None]]}),
        ("decode_group: store's chunk", 0,
         {"fn": "decode_group", "args": [g], "tape": [["store", [g, 1, chunk], None]]}),
        ("push_rebuilt: a chunk read from the store, and enqueued alone", 0,
         {"fn": "push_rebuilt", "args": [g, [1]], "tape": [["read", "chunks", [g, 1], chunk],
                                                           ["enqueue", [4, ["chunk", chunk], False], True]]}),
        ("decode_group: a chunk enqueued alone, by its push_rebuilt", 0,
         {"fn": "decode_group", "args": [g], "tape": [["enqueue", [4, ["chunk", chunk], False], True]]}),
        ("a read of chunks on the tape of another function: no place, so it counts", 1,
         {"fn": "send_have", "args": [4, g], "tape": [["read", "chunks", [g, 1], chunk]]}),
        ("a chunk enqueued alone under another function: so it counts", 1,
         {"fn": "on_ihave", "args": [4, []], "tape": [["enqueue", [4, ["chunk", chunk], False], True]]}),
        ("decode_and_reencode's answer on the tape of another function: so it counts", 1,
         {"fn": "claim_group", "args": [g], "tape": [["decode_and_reencode", [g, None], [[1, chunk]]]]}),
        ("a full id in a rebuilt chunk's index's place: so it counts", 1,
         {"fn": "decode_group", "args": [g], "tape": [["decode_and_reencode", [g, None], [[mid, chunk]]]]}),
        ("push_rebuilt with an ask by full id on its tape: an ask, so it counts", 1,
         {"fn": "push_rebuilt", "args": [g, [1]], "tape": [["enqueue", [4, [["iwant", [other]]], False], True]]}),
    ]
    wide = chunk + [[[2, 0, 1, 4, 4, 8, "d0" * 32], ["00" * 32], [4, ["x", 1]]]]
    cases += [  # level 1 and the wide chunk
        ("a wide chunk in on_chunk's argument", 0, {"fn": "on_chunk", "args": [4, wide], "tape": []}),
        ("a wide chunk in a frame", 0, {"fn": "on_frame", "args": [4, [[wide], [], [], []]], "tape": []}),
        ("a wide chunk waiting, in pending's value", 0,
         {"fn": "send_have", "args": [4, g], "rest": [["pending", ["22" * 32], [[4, wide]]]]}),
        ("validate_chunk's chunk", 0, {"fn": "validate_chunk", "args": [wide], "tape": [], "ret": "ACCEPT"}),
        ("committed_descriptor's chunk", 0,
         {"fn": "committed_descriptor", "args": [[1, "ab" * 32, None], wide], "tape": [], "ret": None}),
        ("a full id in a wide chunk's proof: so it counts", 1,
         {"fn": "on_chunk", "args": [4, chunk + [[[2, 0, 1, 4, 4, 8, "d0" * 32], [mid], [4, ["x", 1]]]]], "tape": []}),
        ("a wide chunk in the argument of a function that takes none: so it counts", 1,
         {"fn": "retry_offer", "args": [wide], "tape": []}),
    ]
    bad = 0
    for name, want, rec in cases:
        got = count([json.dumps(rec)])
        ok = got == want
        bad += not ok
        print(f"fullid self-test, {name}: {got}, must be {want}{'' if ok else '  <-- FAIL'}")
    print("ok: every case as it must be" if not bad else f"{bad} cases wrong")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    path = sys.argv[1]
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
        print(count(f))
