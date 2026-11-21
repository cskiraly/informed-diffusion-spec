#!/usr/bin/env python3
"""Controls that must fail, for format 3: twins with one rule changed, replayed over format-3 traces.

    python3 mutants3.py TRACEDIR WORKDIR [-j N] [MUTANT ...]
    python3 mutants3.py --self-test                                    the table check's own cases
    python3 mutants3.py --check-report REPORT PAIRS [TRACES.sha256]    a report made again from a pairs file, and
                                                        compared; with TRACES.sha256, the pairs' traces are its

Each mutant is a copy of formal/twin in WORKDIR/<mutant>/ with one exact replacement in one file (SpecTwin/Sec61.lean
unless it names another; it must match once), built there, and replayed over every TRACEDIR/*.jsonl.gz, with
--content as cells3.py runs the replay (the tree's content line, written once to WORKDIR). The mutants are built first, four at a time; then every mutant runs over every trace
in one pool of N. Each build and replay runs as a plain child, under the caller's limits; `lake` and `lean` are the
ones on PATH. The toy is the layout's, or SPEC_TOY's (layout.py).
--hashes FILE writes the sha256 of each mutant's replay as built, a line "sha256  mutant" in the order of the run:
two runs whose files are equal ran the same binaries (the record's run, `record.sh`, compares two runs' files).
--pairs FILE writes one line per mutant and trace: "mutant trace count reads-not-made kinds". The record's run
makes the hand cell's lines again and compares them with another run's.
A replay gives no verdict, and the run fails, when it did not read its trace whole: the trace's reader failed, the
replay printed a line about the content line, the header, the nodes line or the trailer, or it refused a line. A mutant's patch must
lie in the function its description names (`place_check`), since that name picks the records it is replayed on.

The mutants (the report's first line counts them):
- mutants.py's 37, format 2's. Of them 17 are as they were, and 19 have their text moved onto the table interface
  (the twin's code reads its state only through it, so a twin that reads more widely does so by a scan, and is
  seen to). One, a deletion of asked_at entries by may_ask, has no operation in the interface to be written with:
  it is a change of the tables' own setAskedAt (same name, in SpecTwin/Tables.lean).
- New ones, for what format 3 adds: a write and a noted erase outside the call's keys; a wider read found in the
  twin itself; a read that goes on past the Python's; a read of another index inside one bitmap (an entry
  is one value: only an outcome shows it); and operations of the tables that do not note what they do, or do
  not do what they note: a read not noted, a write not noted, a read wider than its note, an erase that erases
  more, an erase that erases nothing, a write that writes more.

For each mutant: the records that mismatch, by kind, and the reads of the Python's that the twin did not make
(which the replay counts and allows: a mutant that no record fails can still show there). The kinds are the
replay's first reason for a record: "return", "tape", "state" (the whole state after the call), "raise", "reached"
(the functions the twin entered are not the record's, with its return value and tape the Python's), and
"reads" and "writes", which are about the tables' notes alone: the replay compares the return value, the tape
and the state before the notes, so a record that fails by "reads" or "writes" had all three as the Python's.
"""
import argparse
import ast
import hashlib
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content                          # noqa: E402
import header3                          # noqa: E402
import mutants as M2                    # noqa: E402: format 2's list, for the mutants whose text did not change
import layout                           # noqa: E402
TWIN = layout.TWIN                      # main() takes --twin: the sources a run froze at its start
SEC61 = "SpecTwin/Sec61.lean"
TABLES = "SpecTwin/Tables.lean"

IN_FLIGHT = ("  if let some t := (← askedAt? a) then\n"
             "    if ctx.now - t < ctx.c.IWANT_WINDOW then                 -- 200 ms: an ask is in flight\n")
UNTRIED = "  for q in cands do\n    if (← tried? a q).isNone then return some q\n  return none"
LRT = 'let some t := (← tried? a q) | crash s!"KeyError: {q} (least_recently_tried: tried[a][q])"'
PARK = "let t := (← parkUntil? p a.group).getD negInf"
ARMED = 'if (← lrArmed? k) then\n    branch "last_resort: armed already"'
OVERFLOW = ("  if done.size ≥ 1024 then                                  -- 2 ** n does not convert to a double: Python\n"
            "    crash \"OverflowError: int too large to convert to float (last_resort)\"   --   raises, k already armed\n")
RETRY_W = 'if ctx.now - (← askedAt? a).getD negInf < ctx.c.IWANT_WINDOW then\n    branch "retry_offer: in flight"'
PARKED_W = "if ctx.now - (← askedAt? a).getD negInf < ctx.c.IWANT_WINDOW then   -- someone was asked meanwhile"
QLINE = "let r := ((← lane? q .normal).getD []).any (fun e => e.asks.any (fun b => b.chunk == k))"   # the queue

MOVED = {   # name -> (old, new) on the table interface; what it changes is mutants.py's line
    "untried-last": (UNTRIED, UNTRIED.replace("for q in cands do", "for q in cands.reverse do")),
    "last-resort-rearms": ("  " + ARMED + "\n    return\n", ""),
    "overflow-before-arming": ("  setLrArmed k true\n" + OVERFLOW, OVERFLOW + "  setLrArmed k true\n"),
    "lrt-skips-untried": (LRT, "let some t := (← tried? a q) | continue"),
    "parked-any-group": (PARK, "let t := (← allPark p).foldl (fun m (_, t) => if t > m then t else m) negInf"),
    "park-default-zero": (PARK, "let t := (← parkUntil? p a.group).getD 0.0"),
    "announcers-any-group": ("    return (← offeredBits q a.group).has a.index",
                             "    return (← allOffered q).any (fun (_, x) => x.has a.index)"),
    "window-per-chunk": (IN_FLIGHT,
                         "  if true then\n    if (← allAskedAt).any (fun (b, t) => b.chunk == a.chunk && "
                         "ctx.now - t < ctx.c.IWANT_WINDOW) then\n"),
    "untried-per-chunk": (UNTRIED,     # every key of the chunk, as format 2's: a scan of the whole of tried
                          "  let all ← allTriedAll\n  for q in cands do\n"
                          "    if !(all.any fun (b, m) => b.chunk == a.chunk && m.any (·.1 == q)) then return some q\n"
                          "  return none"),
    "retry-window-default-zero": (RETRY_W, RETRY_W.replace("getD negInf", "getD 0.0")),
    "ask-parked-window-default-zero": (PARKED_W, PARKED_W.replace("getD negInf", "getD 0.0")),
    "lrt-keyerror-last": (LRT, 'let some t := (← tried? a q) | crash s!"KeyError: {(← cands.filterM fun r => return '
                               '(← tried? a r).isNone).getLast!} (least_recently_tried: tried[a][q])"'),
    "retry-window-le": (RETRY_W, RETRY_W.replace("< ctx.c.IWANT_WINDOW", "≤ ctx.c.IWANT_WINDOW")),
    "ask-parked-window-le": (PARKED_W, PARKED_W.replace("< ctx.c.IWANT_WINDOW", "≤ ctx.c.IWANT_WINDOW")),
    "last-resort-done-per-group": ("  let done ← askedParkedOf k\n  let untied ←",
                                   "  let done := (← allAskedParked).foldl (fun acc (c, ps) => if c.1 == k.1 then "
                                   "ps.fold (fun acc q => acc.insert q) acc else acc) ({} : Std.HashSet Peer)\n  let untied ←"),
    "last-resort-armed-any-chunk": (ARMED, ARMED.replace("(← lrArmed? k)", "(← allLrArmed).any (·.1 == k.1)")),
    "announcers-list-any-form": ("  let o ← offersOf a\n  let peers ← connectedTopicPeers",
                                 "  let o := (← offersOf a) ++ ((← allOffers).filter fun (b, _) => b.chunk == a.chunk "
                                 "&& b != a).flatMap (·.2)\n  let peers ← connectedTopicPeers"),
    "last-resort-armed-any-group": (ARMED, ARMED.replace("(← lrArmed? k)", "(← allLrArmed).any (·.2 == k.2)")),
    # outstanding reads the twin's own queue[q].normal, not a question's answer
    "outstanding-no-queue": (QLINE, "let r := false"),
    "outstanding-queued-any-group": (QLINE, QLINE.replace("b.chunk == k", "b.chunk.2 == k.2")),
    "window-per-group": (IN_FLIGHT,
                         "  if true then\n    if (← allAskedAt).any (fun (b, t) => b.group == a.group && "
                         "ctx.now - t < ctx.c.IWANT_WINDOW) then\n"),
}
SET_ASKED_AT = "  setAskedAt a t := do note (.write (.askedAt a)); modify fun s => { s with askedAt := s.askedAt.insert a t }"
IN_TABLES = {   # name -> (old, new) in SpecTwin/Tables.lean: no operation of the interface could write it in Sec61
    "may-ask-erases-group": (SET_ASKED_AT, SET_ASKED_AT.replace(
        "s.askedAt.insert a t", "(s.askedAt.filter fun b _ => b.chunk == a.chunk || b.group != a.group).insert a t")),
}
NEW = {     # name -> (what it changes, file, old, new)
    "may-ask-writes-outside": ("may_ask: also sets asked_at of the group's next index (a write outside the call's keys)",
                               SEC61, "  setAskedAt a ctx.now\n",
                               "  setAskedAt a ctx.now\n  setAskedAt (.want a.group (a.index + 1)) ctx.now\n"),
    "ask-parked-reads-before": ("ask_parked: asked_parked[k] read once before the filter, also when no announcer is "
                                "left to test (the read rule 4 found in the twin)",
                                SEC61,
                                "    cands ← untied.filterM fun q => return !(← askedParkedOf k).contains q   -- read per "
                                "announcer, as the Python\n",
                                "    let done ← askedParkedOf k\n    cands := untied.filter fun q => !done.contains q\n"),
    "untried-reads-all": ("untried: tried[a][q] read for every candidate (the Python stops at the first untried); "
                          "the same answer",
                          SEC61, UNTRIED,
                          "  let ts ← cands.mapM fun q => tried? a q\n"
                          "  return ((cands.zip ts).find? (·.2.isNone)).map (·.1)"),
    "may-ask-erases-outside": ("may_ask: also discards the group's next index from last_resort_armed (a noted erase "
                               "outside the call's keys)",
                               SEC61, "  setAskedAt a ctx.now\n",
                               "  setAskedAt a ctx.now\n  setLrArmed (a.group, a.index + 1) false\n"),
    "announcers-any-index": ("announcers: a peer that offered any index of a's group (another bit of the one bitmap "
                             "the Python reads)",
                             SEC61, "    return (← offeredBits q a.group).has a.index",
                             "    return (← offeredBits q a.group) != 0"),
    "tables-read-wide": ("the tables: reading a park answers the peer's latest park in any group, and notes the one",
                         TABLES, "  parkUntil? p g := do note (.read (.park p g)); return ((← get).park.getD p {}).get? g",
                         "  parkUntil? p g := do note (.read (.park p g)); return ((← get).park.getD p {}).fold "
                         "(fun (m : Option Float) _ t => match m with | some x => if t > x then some t else m "
                         "| none => some t) none"),
    "tables-erase-none": ("the tables: discarding from last_resort_armed notes the write and erases nothing",
                          TABLES, "      lastResortArmed := if armed then s.lastResortArmed.insert k else s.lastResortArmed.erase k }",
                          "      lastResortArmed := if armed then s.lastResortArmed.insert k else s.lastResortArmed }"),
    "no-note-read": ("the tables: a read of asked_at is not noted",
                     TABLES, "  askedAt? a := do note (.read (.askedAt a)); return (← get).askedAt.get? a",
                     "  askedAt? a := do return (← get).askedAt.get? a"),
    "tables-erase-wide": ("the tables: erasing a promise erases every promise of its peer, and notes the one",
                          TABLES, "  erasePromise a p := do note (.write (.promise a p)); modify fun s => { s with "
                                  "promises := s.promises.erase (a, p) }",
                          "  erasePromise a p := do note (.write (.promise a p)); modify fun s => { s with "
                          "promises := s.promises.filter fun (_, r) _ => r != p }"),
    "tables-write-wide": ("the tables: setting a park also sets it for the group \"\" (an entry no one noted)",
                          TABLES, "    modify fun s => { s with park := s.park.insert p ((s.park.getD p {}).insert g t) }",
                          "    modify fun s => { s with park := s.park.insert p (((s.park.getD p {}).insert g t).insert \"\" t) }"),
    "tables-offered-wide": ("the tables: setting a peer's offers also sets them for the group \"\" (an entry no one noted)",
                            TABLES, "    modify fun s => { s with offered := s.offered.insert q ((s.offered.getD q {}).insert g b) }",
                            "    modify fun s => { s with offered := s.offered.insert q (((s.offered.getD q {}).insert g b).insert \"\" b) }"),
    "no-note-write": ("the tables: a write of asked_at is not noted",
                      TABLES, "  setAskedAt a t := do note (.write (.askedAt a)); modify fun s => { s with askedAt := "
                              "s.askedAt.insert a t }",
                      "  setAskedAt a t := do modify fun s => { s with askedAt := s.askedAt.insert a t }"),
}
SEC44 = "SpecTwin/Sec44.lean"
HELD = ('      if ← held a then\n        branch "on_ihave: held"\n        continue\n'
        '      if ← expired a.group then\n        branch "on_ihave: expired"\n        continue\n')
BLOCK = ('      if ← gated a then\n        branch "on_ihave: gated"\n        continue\n'
         '      if !(← authenticable a.group) then\n        branch "on_ihave: no block"\n        continue\n')
TIED = "      if ← tiedToRoot p a then                              -- its copy waits (§4.2)\n"
PARKED = ('      if ← parked p a then                                  -- [c5] park; last resort (§6.1)\n'
          '        lastResort a\n        branch "on_ihave: parked"\n        continue\n')
OUTST = "      if ← outstanding p a then                             -- an ask of it to p is open (§6.1)\n"
ASKLOOP = ('    if ← overIhaveLimits p then\n'
           '      setHeldBack (a.group, a.index) a                      -- retried at the next heartbeat (§6.4)\n'
           '      branch "on_ihave: held back"\n'
           '    else if ← mayAsk a p then\n'
           '      asks := asks.push a\n'
           '      setIhaveAsked p ((← ihaveAsked p) + 1)                -- an ask in reply to p\'s IHAVEs\n'
           '      branch "on_ihave: asks"\n')
RPCS = "  if !ids.isEmpty then setIhaveFrames p ((← ihaveFrames p) + 1)  -- IHAVE-bearing frames (§8.2)\n"
MINE = "      if !(← mineBits g).has i then                         -- `if not mine[g].has(i)`\n"
KNOWN = "        out := out.push ((← knownId g i).getD (.want g i))  -- `known_id[g].get(i) or WantIndex(group=g, index=i)`\n"
SLICE1 = {      # name -> (what it changes, file, old, new): §4.4 and §6.2
    "ihave-asks-expired-always": ("on_ihave: expired asked also where held decided (the twin's first version)", SEC44, HELD,
                                  '      if (← held a) || (← expired a.group) then\n        branch "on_ihave: held or expired"\n        continue\n'),
    "ihave-asks-block-always": ("on_ihave: authenticable asked also where gated decided (the twin's first version)", SEC44, BLOCK,
                                '      if (← gated a) || !(← authenticable a.group) then\n        branch "on_ihave: gated, or no block"\n        continue\n'),
    "ihave-expired-first": ("on_ihave: expired asked before held", SEC44, HELD,
                            '      if ← expired a.group then\n        branch "on_ihave: expired"\n        continue\n'
                            '      if ← held a then\n        branch "on_ihave: held"\n        continue\n'),
    "ihave-offers-held": ("on_ihave: a held chunk's offer is recorded all the same", SEC44,
                          '      if ← held a then\n        branch "on_ihave: held"\n',
                          '      if ← held a then\n        addOffer a p\n        branch "on_ihave: held"\n'),
    "ihave-tied-ignored": ("on_ihave: a chunk whose copy waits is asked for all the same", SEC44, TIED,
                           TIED.replace("if ← tiedToRoot p a then ", "if (← tiedToRoot p a) && false then")),
    "ihave-parked-no-last-resort": ("on_ihave: a parked peer: the last resort is not armed", SEC44, PARKED,
                                    PARKED.replace("        lastResort a\n", "")),
    "ihave-parked-goes-on": ("on_ihave: a parked peer: the last resort is armed, and the chunk is asked of it all the same",
                             SEC44, PARKED, PARKED.replace('        branch "on_ihave: parked"\n        continue\n',
                                                           '        branch "on_ihave: parked"\n')),
    "ihave-outstanding-ignored": ("on_ihave: an ask open to the peer does not stop another", SEC44, OUTST,
                                  OUTST.replace("if ← outstanding p a then ", "if (← outstanding p a) && false then")),
    "ihave-no-shuffle": ("on_ihave: the candidates in their own order, with no draw", SEC44,
                         "  for a in ← shuffled candidates.toList do                  -- §6.1\n",
                         "  for a in candidates.toList do\n"),
    "ihave-limit-after-ask": ("on_ihave: the limits are looked at after may_ask, not before", SEC44, ASKLOOP,
                              '    if ← mayAsk a p then\n'
                              '      if ← overIhaveLimits p then\n'
                              '        setHeldBack (a.group, a.index) a\n'
                              '        branch "on_ihave: held back"\n'
                              '      else\n'
                              '        asks := asks.push a\n'
                              '        setIhaveAsked p ((← ihaveAsked p) + 1)\n'
                              '        branch "on_ihave: asks"\n'),
    "ihave-held-back-key": ("on_ihave: an ask is held back under the next index", SEC44,
                            "      setHeldBack (a.group, a.index) a ", "      setHeldBack (a.group, a.index + 1) a "),
    "ihave-asked-not-counted": ("on_ihave: an ask in reply does not count", SEC44,
                                "      setIhaveAsked p ((← ihaveAsked p) + 1)                -- an ask in reply to p's IHAVEs\n", ""),
    "ihave-rpcs-not-counted": ("on_ihave: an IHAVE-bearing frame does not count", SEC44, RPCS, ""),
    "ihave-counts-empty": ("on_ihave: an IHAVE with no entry counts as a frame", SEC44, RPCS,
                           RPCS.replace("if !ids.isEmpty then setIhaveFrames", "if true then setIhaveFrames")),
    "limits-rpcs-ge": ("over_ihave_limits: over the limit at MAX_IHAVE_MESSAGES frames, not above it", SEC44,
                       "c.MAX_IHAVE_MESSAGES.any (frames > ·)", "c.MAX_IHAVE_MESSAGES.any (frames ≥ ·)"),
    "limits-asks-gt": ("over_ihave_limits: over the limit above MAX_IHAVE_LENGTH asks, not at it", SEC44,
                       "c.MAX_IHAVE_LENGTH.any (asked ≥ ·)", "c.MAX_IHAVE_LENGTH.any (asked > ·)"),
    "limits-reads-both": ("over_ihave_limits: ihave_asked[p] read also where the frames decided; the same answer", SEC44,
                          "  let frames ← ihaveFrames p\n  if c.MAX_IHAVE_MESSAGES.any (frames > ·) then\n",
                          "  let frames ← ihaveFrames p\n  let _ ← ihaveAsked p\n  if c.MAX_IHAVE_MESSAGES.any (frames > ·) then\n"),
    "expand-ignores-mine": ("expand: a bitmap's held indices are expanded too", SEC44, MINE,
                            MINE.replace("if !(← mineBits g).has i then ", "if !(← mineBits g).has i || true then")),
    "expand-ignores-known-id": ("expand: a known id is read and not used", SEC44, KNOWN,
                                "        let _ ← knownId g i\n        out := out.push (.want g i)\n"),
    "expand-known-id-first": ("expand: known_id read before mine, for every index", SEC44, MINE + KNOWN,
                              "      let k ← knownId g i\n      if !(← mineBits g).has i then\n        out := out.push (k.getD (.want g i))\n"),
    "gated-false": ("gated: stop_pull read and not heeded", SEC44,
                    '  enter "gated"\n  stopPull a.group\n',
                    '  enter "gated"\n  let _ ← stopPull a.group\n  return false\n'),
    # rules that no mutant above changes
    "ihave-held-ignored": ("on_ihave: held asked and not heeded: a held chunk is handled like any other", SEC44,
                           '      if ← held a then\n        branch "on_ihave: held"\n',
                           '      if (← held a) && false then\n        branch "on_ihave: held"\n'),
    "ihave-expired-ignored": ("on_ihave: expired asked and not heeded", SEC44,
                              '      if ← expired a.group then\n        branch "on_ihave: expired"\n',
                              '      if (← expired a.group) && false then\n        branch "on_ihave: expired"\n'),
    "ihave-block-ignored": ("on_ihave: authenticable asked and not heeded: a group without its block is asked for", SEC44,
                            '      if !(← authenticable a.group) then\n',
                            '      if !(← authenticable a.group) && false then\n'),
    "ihave-offer-after-gate": ("on_ihave: the offer recorded after the gate and the block, not before", SEC44,
                               "      addOffer a p                                          -- [c5] offer table (§6.1)\n"
                               "      -- `if gated(a) or not authenticable(group(a)): continue`: [c6] stop-pull; the block first (§3)\n"
                               + BLOCK,
                               BLOCK + "      addOffer a p\n"),
    "ihave-entries-reversed": ("on_ihave: the IHAVE's entries handled last to first", SEC44,
                               "  for entry in ids do\n", "  for entry in ids.reverse do\n"),
    "ihave-expand-one-by-one": ("on_ihave: a bitmap expanded index by index as its asks are handled, not whole before the first",
                                SEC44, "    for a in ← expand entry do                              -- [c7]\n",
                                "    for one in (match entry with | .id a => [IhaveEntry.id a] | .other r => [IhaveEntry.other r] | .bitmap g bits => bits.toList.map fun i => IhaveEntry.bitmap g ((0 : Bits).set i)) do\n"
                                "    for a in ← expand one do\n"),
    "ihave-held-back-and-asked": ("on_ihave: an ask over the limits is held back and asked all the same", SEC44,
                                  "    else if ← mayAsk a p then\n", "    if ← mayAsk a p then\n"),
    "ihave-asked-counted-always": ("on_ihave: an ask that may_ask refuses counts too", SEC44,
                                   '    else if ← mayAsk a p then\n      asks := asks.push a\n'
                                   '      setIhaveAsked p ((← ihaveAsked p) + 1)                -- an ask in reply to p\'s IHAVEs\n',
                                   '    else\n      setIhaveAsked p ((← ihaveAsked p) + 1)\n      if ← mayAsk a p then\n        asks := asks.push a\n'),
    "ihave-rpcs-per-entry": ("on_ihave: a frame counts once for each of its entries", SEC44,
                             RPCS + "  let mut candidates := #[]\n  for entry in ids do\n",
                             "  let mut candidates := #[]\n  for entry in ids do\n    setIhaveFrames p ((← ihaveFrames p) + 1)\n"),
    "ihave-shuffle-ignored": ("on_ihave: the draw asked and its order not used", SEC44,
                              "  for a in ← shuffled candidates.toList do                  -- §6.1\n",
                              "  let _ ← shuffled candidates.toList\n  for a in candidates.toList do\n"),
    "limits-unset-not-read": ("over_ihave_limits: ihave_frames[p] not read where no limit of frames is set", SEC44,
                              "  let frames ← ihaveFrames p\n",
                              "  let frames ← if c.MAX_IHAVE_MESSAGES.isSome then ihaveFrames p else pure 0\n"),
    "limits-asks-unset-not-read": ("over_ihave_limits: ihave_asked[p] not read where no limit of asks is set", SEC44,
                                   "  let asked ← ihaveAsked p\n",
                                   "  let asked ← if c.MAX_IHAVE_LENGTH.isSome then ihaveAsked p else pure 0\n"),
    "expand-downward": ("expand: a bitmap read from its highest index down", SEC44,
                        "    for i in bits.toList do\n", "    for i in bits.toList.reverse do\n"),
    "expand-id-dropped": ("expand: a full id expands to nothing", SEC44,
                          '      branch "expand: an id"\n      return [a]\n',
                          '      branch "expand: an id"\n      return []\n'),
    "expand-fallback-next-index": ("expand: an index with no known id is asked as the next index", SEC44, KNOWN,
                                   KNOWN.replace("(.want g i))", "(.want g (i + 1)))")),
    "tables-rpcs-write-none": ("the tables: a write of ihave_frames notes itself and writes nothing", TABLES,
                               # (three lines, as the name is long: the generator keeps a line to its width)
                               "  setIhaveFrames p n := do\n    note (.write (.ihaveFrames p))\n"
                               "    modify fun s => { s with ihaveFrames := s.ihaveFrames.insert p n }\n",
                               "  setIhaveFrames p _ := do\n    note (.write (.ihaveFrames p))\n"),
    "tables-rpcs-read-asked": ("the tables: a read of ihave_frames answers ihave_asked's entry, and notes its own", TABLES,
                               "  ihaveFrames p := do note (.read (.ihaveFrames p)); return (← get).ihaveFrames.getD p 0",
                               "  ihaveFrames p := do note (.read (.ihaveFrames p)); return (← get).ihaveAsked.getD p 0"),
    "tables-asked-write-wide": ("the tables: a write of ihave_asked also writes the next peer's", TABLES,
                                "    modify fun s => { s with ihaveAsked := s.ihaveAsked.insert p n }",
                                "    modify fun s => { s with ihaveAsked := (s.ihaveAsked.insert p n).insert (p + 1) n }"),
    "tables-asked-read-zero": ("the tables: a read of ihave_asked answers 0", TABLES,
                               "  ihaveAsked p := do note (.read (.ihaveAsked p)); return (← get).ihaveAsked.getD p 0",
                               "  ihaveAsked p := do note (.read (.ihaveAsked p)); return 0"),
    "tables-heldback-write-none": ("the tables: a write of held_back notes itself and writes nothing", TABLES,
                                   "  setHeldBack k a := do note (.write (.heldBack k)); modify fun s => { s with heldBack := s.heldBack.insert k a }",
                                   "  setHeldBack k _ := do note (.write (.heldBack k))"),
    "tables-heldback-wide": ("the tables: a write of held_back also writes the next index's", TABLES,
                             "  setHeldBack k a := do note (.write (.heldBack k)); modify fun s => { s with heldBack := s.heldBack.insert k a }",
                             "  setHeldBack k a := do note (.write (.heldBack k)); modify fun s => { s with heldBack := (s.heldBack.insert k a).insert (k.1, k.2 + 1) a }"),
}
# v0.10's §4.4: `valid_id`, and a bitmap held to a HAVE's limits in on_ihave
# (the twin reads the descriptor and calls §1's N of it: the three mutants below that change these lines have
# their text as the lines are)
VALID_DESC = ('    if (← desc a.group).isNone then                         -- `g not in desc or …`\n'
              '      branch "valid_id: the count not known"\n      return true\n'
              '    let n ← N (← desc a.group)                              -- `i < N(desc[g])`: §1\'s N, of a second read\n')
BITMAP_CHECK = ('    if let .bitmap g bits := entry then                     -- `if is_have_bitmap(entry) and not valid_have(entry):`\n'
                '      if !(← validHave g bits) then                         --   a bitmap is held to a HAVE\'s limits: ignored,\n'
                '        penalise p                                          --   and counted (§8.2)\n'
                '        branch "on_ihave: a bitmap beyond a HAVE\'s limits"\n        continue\n')
V010 = {
    "valid-id-any-length": ("valid_id: an id that is not 56 bytes is valid", SEC44,
                            '    branch "valid_id: not 56 bytes"\n    return false\n',
                            '    branch "valid_id: not 56 bytes"\n    return true\n'),
    "valid-id-cap-le": ("valid_id: index MAX_PLAIN_CHUNKS is one a group can have", SEC44,
                        "    if !(a.index < c.MAX_PLAIN_CHUNKS) then", "    if !(a.index ≤ c.MAX_PLAIN_CHUNKS) then"),
    "valid-id-cap-ignored": ("valid_id: no bound on the index but the group's count", SEC44,
                             "    if !(a.index < c.MAX_PLAIN_CHUNKS) then", "    if false then"),
    "valid-id-count-le": ("valid_id: index N is one a group of N chunks has", SEC44,
                          "    let r := a.index < n\n", "    let r := a.index ≤ n\n"),
    "valid-id-count-ignored": ("valid_id: a known count read and not compared", SEC44,
                               "    let r := a.index < n\n", "    let r := true\n"),
    "valid-id-unknown-invalid": ("valid_id: an id of a group whose count is not known is ignored", SEC44,
                                 '      branch "valid_id: the count not known"\n      return true\n',
                                 '      branch "valid_id: the count not known"\n      return false\n'),
    "expand-id-unchecked": ("expand: an id is kept without valid_id", SEC44,
                            "    if ← validId (.id a) then                               -- `return [entry] if valid_id(entry) else []`\n",
                            "    if true then\n"),
    "ihave-bitmap-unchecked": ("on_ihave: a bitmap is not held to a HAVE's limits", SEC44, BITMAP_CHECK, ""),
    "ihave-bitmap-not-penalised": ("on_ihave: a bitmap beyond a HAVE's limits is ignored, and its sender not penalised",
                                   SEC44, "        penalise p                                          --   and counted (§8.2)\n", ""),
    "ihave-bitmap-goes-on": ("on_ihave: a bitmap beyond a HAVE's limits penalises its sender, and is expanded all the same",
                             SEC44, BITMAP_CHECK, BITMAP_CHECK.replace("        continue\n", "")),
    # four rules of v0.10's §4.4 that no mutant above changes
    "ihave-ignored-id-penalised": ("on_ihave: an id that is ignored (not a chunk's structured id) penalises its sender", SEC44,
                                   "    for a in ← expand entry do                              -- [c7]\n",
                                   "    let xs ← expand entry\n"
                                   "    if xs.isEmpty && (match entry with | .bitmap .. => false | _ => true) then penalise p\n"
                                   "    for a in xs do\n"),
    "ihave-bitmap-check-ends-loop": ("on_ihave: a bitmap beyond a HAVE's limits ends the IHAVE's loop, not its own entry", SEC44,
                                     BITMAP_CHECK, BITMAP_CHECK.replace("        continue\n", "        break\n")),
    "ihave-bitmap-checked-after-expand": ("on_ihave: a bitmap is held to a HAVE's limits after it is expanded, not before", SEC44,
                                          BITMAP_CHECK + "    for a in ← expand entry do                              -- [c7]\n",
                                          "    let xs ← expand entry\n"
                                          + BITMAP_CHECK + "    for a in xs do\n"),
    "valid-id-bitmap-false": ("valid_id: of a bitmap it answers false, where the Python's len raises", SEC44,
                              '  | .bitmap .. => crash "TypeError: len() of a bitmap (valid_id)"',
                              '  | .bitmap .. => return false'),
    "ihave-ids-checked-as-bitmaps": ("on_ihave: an id is held to valid_have too, as a bitmap of its index", SEC44,
                                     "    if let .bitmap g bits := entry then                     -- `if is_have_bitmap(entry) and not valid_have(entry):`\n",
                                     # (an id of an index below 8192 only: 2**32 - 1 as a bitmap would be 4 Gbit)
                                     "    if let some (g, bits) := (match entry with | .bitmap g b => some (g, b) | .id a => (if a.index < 8192 then some (a.group, (0 : Bits).set a.index) else none) | .other _ => none) then\n"),
}
# §4.2: the six functions, the two readers, and the new tables' operations
SEC42 = "SpecTwin/Sec42.lean"
SEC72 = "SpecTwin/Sec72.lean"     # §7.2's writer
READERS_LEAN = "SpecTwin/Readers.lean"
SLICE2A = {     # name -> (what it changes, file, old, new)
    # pending_ids is the twin's own (`pendingId?`, a read of its table, not a question), and defer takes a fuel;
    # the four mutants that name them keep their rules, on that text
    "chunk-pending-first": ("on_chunk: pending_ids asked before seen", SEC42,
                            "  let mut dup ← seen mid\n  if !dup then dup ← pendingId? mid\n",
                            "  let mut dup ← pendingId? mid\n  if !dup then dup ← seen mid\n"),
    "chunk-waiting-not-tied": ("on_chunk: a copy of one that waits does not tie its sender", SEC42,
                               "    else if ← pendingId? mid then                           -- another copy of one that waits: its sender too\n      tie p f\n",
                               "    else if ← pendingId? mid then                           -- another copy of one that waits: its sender too\n      pure ()\n"),
    "chunk-dup-not-acked": ("on_chunk: an accepted duplicate is not acknowledged", SEC42,
                            '      sendHave p f.g\n      branch "on_chunk: a duplicate, acknowledged"\n',
                            '      branch "on_chunk: a duplicate, acknowledged"\n'),
    "chunk-live-ignored": ("on_chunk: the live window not asked", SEC42,
                           '  if !(← live f.slot) then\n    branch "on_chunk: not live"\n',
                           '  if false then\n    branch "on_chunk: not live"\n'),
    "validated-first-line-dropped": ("on_validated: expiry and the window not asked again", SEC42,
                                     '  if ← expired f.g then\n    branch "on_validated: expired"\n    return\n'
                                     '  if !(← live f.slot) then\n    branch "on_validated: not live"\n    return\n', ""),
    "validated-seen-before-defer": ("on_validated: mark_seen before the DEFER test", SEC42,
                                    "    defer fuel p f\n", "    markSeen f.mid\n    defer fuel p f\n"),
    "validated-reject-no-penalty": ("on_validated: a REJECT is not penalised", SEC42,
                                    '    penalise p\n    branch "on_validated: rejected"\n',
                                    '    branch "on_validated: rejected"\n'),
    "validated-no-drop-beyond": ("on_validated: a group opened without drop_beyond", SEC42,
                                 "    dropBeyond g                                            --   what named an index it has not goes (§8.2)\n", ""),
    "validated-invalid-ignored": ("on_validated: an INVALID group handled as any other", SEC42,
                                  "  if (← state? g) == some .invalid then ", "  if (← state? g) == some .invalid && false then "),
    "validated-received-no-ack": ("on_validated: a chunk received before is not acknowledged", SEC42,
                                  '    sendHave p g\n    branch "on_validated: received before"\n',
                                  '    branch "on_validated: received before"\n'),
    "validated-claim-always": ("on_validated: every stored chunk claimed to the mesh", SEC42,
                               "  let claim := !(← mineBits g).has i ", "  let claim := !(← mineBits g).has i || true "),
    "validated-mesh-without-sender": ("on_validated: the claim to the mesh, not to the sender", SEC42,
                                      "  let qs ← if claim then meshAnd p else pure [p] ",
                                      "  let qs ← if claim then (·.filter (· != p)) <$> meshAnd p else pure [p] "),
    "validated-k-gt": ("on_validated: the decode claim only past K", SEC42, "    if count ≥ k then\n", "    if count > k then\n"),
    "validated-no-decoding": ("on_validated: the state not set to DECODING at K", SEC42,
                              "      setState g .decoding                                  -- once per group\n", ""),
    "validated-store-no-received": ("on_validated: received not set at a store", SEC42,
                                    "  setReceived g ((← receivedBits g).set i)                  -- `received[g].set(i)`\n",
                                    "  let _ ← receivedBits g\n"),
    "drop-beyond-gt-n": ("drop_beyond: an offered index dropped only past N", SEC42,
                         "      if i ≥ n then idx := i :: idx\n", "      if i > n then idx := i :: idx\n"),
    "drop-beyond-offered-only": ("drop_beyond: the asks' keys not looked at", SEC42,
                                 "    if a.group == g && a.index ≥ n then idx := a.index :: idx\n",
                                 "    if a.group == g && a.index ≥ n && false then idx := a.index :: idx\n"),
    "drop-beyond-queue-once": ("drop_beyond: the queue's peers asked once, for every index", SEC42,
                               # the queue's rows read, and their order asked, once
                               "  for i in (sortBy (· < ·) idx.eraseDups) do                -- `for i in sorted(idx):`\n"
                               "    -- `for q in list(queue): drop_offer(g, i, q)`: the peers with a queue are the twin's rows,\n"
                               "    -- read as a whole, in the node's order of them\n"
                               "    for q in ← queueOrder ((← allQueue).map (·.1)) do",
                               "  let qs ← if idx.isEmpty then pure [] else queueOrder ((← allQueue).map (·.1))\n"
                               "  for i in (sortBy (· < ·) idx.eraseDups) do                -- `for i in sorted(idx):`\n"
                               "    for q in qs do"),
    "drop-beyond-no-ties": ("drop_beyond: ties beyond N kept", SEC42,
                            "        if b' == 0 then eraseTied r q g                     --     `if not bits: groups.pop(g)`\n"
                            "        else if b' != b then setTied r q g b'               --     `bits.clear(i)` for each i >= n, in place\n",
                            "        if b' == b then pure () else pure ()\n"),
    "drop-beyond-keeps-empty": ("drop_beyond: an emptied tie kept, as 0", SEC42,
                                "        if b' == 0 then eraseTied r q g ",
                                "        if b' == 0 then (if b' != b then setTied r q g b' else pure ()) "),
    "have-bits-mine-only": ("have_bits: origin not asked", SEC42,
                            "  if (← origin g).isSome then ", "  if false then "),
    "send-have-normal-lane": ("send_have: the HAVE queued on the normal lane", SEC42,
                              "  let _ ← enqueue p (.have g b) true ", "  let _ ← enqueue p (.have g b) false "),
    "close-of-any-peer": ("close_promises: the `of` form closes every peer's promise", SEC42,
                          "    if a.chunk == k && (of_.isNone || of_ == some q) then ", "    if a.chunk == k then "),
    "close-of-goes-on": ("close_promises: the `of` form goes on to every key", SEC42,
                         '    branch "close_promises: of a peer"\n    return\n', '    branch "close_promises: of a peer"\n'),
    "close-keeps-asked-parked": ("close_promises: the last resort's count kept", SEC42, "  eraseAskedParked k\n", ""),
    "close-offered-kept": ("close_promises: offered not cleared", SEC42,
                           "    if b.has i then setOffered q g (b.clear i)\n", "    if b.has i then pure ()\n"),
    "held-any-index": ("held: any index of the group held", READERS_LEAN,
                       "  return (← mineBits a.group).has a.index\n", "  return (← mineBits a.group) != 0\n"),
    "tied-any-peer": ("tied_to_root: a tie of any peer", READERS_LEAN,
                      "    q == p && groups.any fun (g, bits) => g == a.group && bits.has a.index\n",
                      "    (q == p || true) && groups.any fun (g, bits) => g == a.group && bits.has a.index\n"),
    "tied-any-group": ("tied_to_root: a tie of any group", READERS_LEAN,
                       "    q == p && groups.any fun (g, bits) => g == a.group && bits.has a.index\n",
                       "    q == p && groups.any fun (g, bits) => (g == a.group || true) && bits.has a.index\n"),
    "tied-any-index": ("tied_to_root: a tie of any index of the group", READERS_LEAN,
                       "    q == p && groups.any fun (g, bits) => g == a.group && bits.has a.index\n",
                       "    q == p && groups.any fun (g, bits) => g == a.group && bits != 0\n"),
    "tables-tied-erase-row": ("the tables: an erase of a tie takes its peer's row with it", TABLES,
                              "    modify fun s => { s with tied := s.tied.modify r (·.modify p (·.erase g)) }",
                              "    modify fun s => { s with tied := s.tied.modify r (·.erase p) }"),
    "tables-mine-write-none": ("the tables: a write of mine notes itself and writes nothing", TABLES,
                               "  setMine g b := do note (.write (.mine g)); modify fun s => { s with mine := s.mine.insert g b }",
                               "  setMine g _ := do note (.write (.mine g))"),
    "tables-state-read-none": ("the tables: a read of state notes itself and answers none", TABLES,
                               "  state? g := do note (.read (.state g)); return (← get).state.get? g",
                               "  state? g := do note (.read (.state g)); return none"),
    "tables-received-read-zero": ("the tables: a read of received notes itself and answers empty", TABLES,
                                  "  receivedBits g := do note (.read (.received g)); return (← get).received.getD g 0",
                                  "  receivedBits g := do note (.read (.received g)); return 0"),
}

# the twin's own queue; rules of §4.2 and close_promises that no mutant above changes; and drop_beyond's partial
# clear of a tie
QMOVE = {       # name -> (what it changes, file, old, new)
    # the queue
    "outstanding-urgent-too": ("outstanding: the urgent lane read too", SEC61, QLINE,
                               "let r := (((← lane? q .normal).getD []) ++ ((← lane? q .urgent).getD [])).any "
                               "(fun e => e.asks.any (fun b => b.chunk == k))"),
    "outstanding-first-entry": ("outstanding: the lane's first entry alone", SEC61, QLINE,
                                QLINE.replace("((← lane? q .normal).getD [])", "(((← lane? q .normal).getD []).take 1)")),
    "outstanding-ask-by-group": ("outstanding: a queued ask of any index of a's group", SEC61, QLINE,
                                 QLINE.replace("b.chunk == k", "b.chunk.1 == k.1")),
    "drop-beyond-skips-empty-rows": ("drop_beyond: the queue's rows with both lanes empty left out", SEC42,
                                     "    for q in ← queueOrder ((← allQueue).map (·.1)) do",
                                     "    for q in ← queueOrder (((← allQueue).filter fun (_, ls) => ls.any fun (_, es) => "
                                     "!es.isEmpty).map (·.1)) do"),
    "tables-lane-read-none": ("the tables: a read of a lane notes itself and answers none", TABLES,
                              "  lane? p l := do note (.read (.queue p l)); return ((← get).queue.getD p {}).get? l",
                              "  lane? p l := do note (.read (.queue p l)); return none"),
    # on_validated's calls on the tape
    "validated-no-store": ("on_validated: the chunk not stored", SEC42,
                           "  store g i f                                               -- also records known_id[g][i] = message_id(f)\n", ""),
    "validated-no-forward": ("on_validated: the chunk not forwarded", SEC42,
                             "  if (← read).replaced.contains \"forward\" then forwardNode f p   -- §5.2; or the node's own\n"
                             "  else forward f.narrow p\n", ""),
    "validated-no-claim-group": ("on_validated: no decode claim at K", SEC42,
                                 "      claimGroup g                                          -- [c10] the decode claim, at K (§4.6)\n", ""),
    "validated-no-start": ("on_validated: decoding not started at K", SEC42,
                           '      start "decode_group" g                                -- level 2, off the chunk path\n', ""),
    # close_promises' erase, its three pops each alone, and "under every key"
    "close-keeps-promises": ("close_promises: the chunk's promises kept", SEC42,
                             "      erasePromise a q\n", "      pure ()\n"),
    "close-keeps-offers": ("close_promises: the chunk's offers kept", SEC42, "    eraseOffers a\n", ""),
    "close-keeps-tried": ("close_promises: the chunk's tries kept", SEC42,
                          "    for (q, _) in ← allTried a do\n      eraseTried a q\n", ""),
    "close-keeps-asked-at": ("close_promises: the chunk's asked_at kept", SEC42, "    eraseAskedAt a\n", ""),
    "close-one-key": ("close_promises: one key of the chunk, not every key", SEC42,
                      ").filter (·.chunk == k)\n", ").filter (·.chunk == k) |>.eraseDups |>.take 1\n"),
    # the COLLECTING guard, mark_seen on a REJECT, on_chunk's accepted before pending_ids, and its expired
    "validated-decoding-any-state": ("on_validated: the decode claim at K whatever the group's state", SEC42,
                                     "  if (← state? g) == some .collecting then\n", "  if true then\n"),
    "validated-reject-not-seen": ("on_validated: a REJECT not marked seen", SEC42,
                                  "  markSeen (← messageId f)                                  -- `mark_seen(message_id(f))`: never validated again\n"
                                  "  if result == .reject then                                 -- `if result == REJECT: return penalise(p)`\n"
                                  '    penalise p\n    branch "on_validated: rejected"\n    return\n',
                                  "  let mid ← messageId f\n"      # (the id still computed where the Python does)
                                  "  if result == .reject then                                 -- `if result == REJECT: return penalise(p)`\n"
                                  '    penalise p\n    branch "on_validated: rejected"\n    return\n  markSeen mid\n'),
    "chunk-pending-before-accepted": ("on_chunk: a duplicate asked whether it waits before whether it was accepted", SEC42,
                                      "    if ← accepted mid then                                  -- [c14] duplicates are acknowledged too\n"
                                      '      sendHave p f.g\n      branch "on_chunk: a duplicate, acknowledged"\n'
                                      "    else if ← pendingId? mid then                           -- another copy of one that waits: its sender too\n"
                                      '      tie p f\n      branch "on_chunk: a duplicate of one waiting, tied"\n',
                                      "    if ← pendingId? mid then\n"
                                      '      tie p f\n      branch "on_chunk: a duplicate of one waiting, tied"\n'
                                      "    else if ← accepted mid then\n"
                                      '      sendHave p f.g\n      branch "on_chunk: a duplicate, acknowledged"\n'),
    "chunk-expired-ignored": ("on_chunk: expiry not asked", SEC42,
                              '  if ← expired f.g then\n    branch "on_chunk: expired"\n',
                              '  if false then\n    branch "on_chunk: expired"\n'),
    # drop_beyond's two `≥ n` (the asks' keys, and the ties)
    "drop-beyond-keys-gt-n": ("drop_beyond: an ask's key dropped only past N", SEC42,
                              "    if a.group == g && a.index ≥ n then idx := a.index :: idx\n",
                              "    if a.group == g && a.index > n then idx := a.index :: idx\n"),
    "drop-beyond-ties-gt-n": ("drop_beyond: a tie's index cleared only past N", SEC42,
                              "if i ≥ n then acc.clear i else acc", "if i > n then acc.clear i else acc"),
    # Sec42.lean's partial clear of a tie (setTied with indices left), reached once directed42 draws ties on both
    # sides of N
    "drop-beyond-tie-partial-erased": ("drop_beyond: a tie partly beyond N erased whole", SEC42,
                                       "        else if b' != b then setTied r q g b'               --     `bits.clear(i)` for each i >= n, in place\n",
                                       "        else if b' != b then eraseTied r q g\n"),
    "tables-tied-write-none": ("the tables: a write of a tie notes itself and its rows, and writes nothing", TABLES,
                               "  setTied r p g b := do\n    let s ← get\n"
                               "    if !s.tied.contains r then note (.write (.tiedRow r))\n"
                               "    if !(s.tied.getD r {}).contains p then note (.write (.tiedPeerRow r p))\n"
                               "    note (.write (.tied r p g))\n    modify fun s => { s with\n"
                               "      tied := s.tied.insert r ((s.tied.getD r {}).insert p (((s.tied.getD r {}).getD p {}).insert g b)) }",
                               "  setTied r p g _ := do\n    let s ← get\n"
                               "    if !s.tied.contains r then note (.write (.tiedRow r))\n"
                               "    if !(s.tied.getD r {}).contains p then note (.write (.tiedPeerRow r p))\n"
                               "    note (.write (.tied r p g))"),
}

# the rule of an entry's asks, as outstanding reads them; then the deferral path's and §7.2's writer's
AEND = {        # name -> (what it changes, file, old, new)
    "outstanding-asks-first-id": ("outstanding: an entry's first ask alone", SEC61, QLINE,
                                  QLINE.replace("e.asks.any", "(e.asks.take 1).any")),
    "outstanding-asks-first-message": ("outstanding: an entry's first control message alone", SEC61, QLINE,
                                       QLINE.replace("e.asks.any", "(match e.control with | some (.iwant ids :: _) => ids "
                                                     "| _ => []).any")),
    "outstanding-skips-chunk-entries": ("outstanding: an entry with a chunk not looked at", SEC61, QLINE,
                                        QLINE.replace("e.asks.any", "(if e.chunk.isSome then [] else e.asks).any")),
    # the deferral path: one rule each of the six functions, the fuel, the order questions where a traced function
    # asks them, and the tables' new operations
    "defer-installed-not-asked": ("defer: installed_block not asked: a copy whose block is there is kept", SEC42,
                                  "  if (← installedBlock f.slot f.root).isSome then           -- installed in the meantime\n",
                                  "  if false then\n"),
    "defer-admitted-not-asked": ("defer: admitted not asked", SEC42,
                                 "  if !(← admitted p f) then                                 -- a group beyond the peer's unknown groups (§8.2):\n",
                                 "  if false then\n"),
    "defer-reserve-before-tie": ("defer: the reservation asked before the tie", SEC42,
                                 "  tie p f                                                   -- kept or refused, its sender is tied to the root\n"
                                 "  if ← reserve p f then                                     -- a per-peer reservation in a bounded store (§8.2)\n",
                                 "  let kept ← reserve p f\n  tie p f\n  if kept then\n"),
    "defer-kept-not-listed": ("defer: a kept copy's id not put in pending_ids", SEC42,
                              "    setPendingId (← messageId f) true                       -- `pending_ids.add(message_id(f))`\n",
                              "    let _ ← messageId f\n"),
    "defer-kept-first": ("defer: a kept copy put first under its root, not last", SEC42,
                         "    setPending f.root ((← pendingOf f.root) ++ [(p, f)])    -- `pending[f.beacon_block_root].append((p, f))`\n",
                         "    setPending f.root ((p, f) :: (← pendingOf f.root))\n"),
    "tie-expiry-not-asked": ("tie: expiry not asked", SEC42,
                             '  if ← expired f.g then                                     -- `if expired(f.group) or not live(f.slot): return`\n'
                             '    branch "tie: expired"\n    return\n', ""),
    "tie-window-not-asked": ("tie: the live window not asked", SEC42,
                             '  if !(← live f.slot) then\n    branch "tie: not live"\n    return\n', ""),
    "tie-room-not-asked": ("tie: tie_room not asked", SEC42,
                           '  if !(← tieRoom p f) then\n    branch "tie: no room"\n    return\n', ""),
    "tie-slot-overwritten": ("tie: tie_slot written always, not set by default", SEC42,
                             "  if (← tieSlot? f.root p).isNone then                      -- `tie_slot.setdefault((root, p), f.slot)`: the\n"
                             "    setTieSlot f.root p f.slot                              --   slot p's first copy named\n",
                             "  setTieSlot f.root p f.slot\n"),
    "tie-closes-every-key": ("tie: the chunk's promises closed under every key, not p's alone", SEC42,
                             "  closePromises f.g f.i (some p)                            -- p answered: its promise for the index closes\n",
                             "  closePromises f.g f.i none\n"),
    "tie-room-index-bound-dropped": ("tie_room: an index no group has not refused", SEC42,
                                     "  if f.i ≥ c.MAX_PLAIN_CHUNKS then                          -- an index no group has,\n",
                                     "  if false then\n"),
    "tie-room-count-bound-dropped": ("tie_room: an index beyond a known count not refused", SEC42,
                                     '    if f.i ≥ n then\n      branch "tie_room: beyond the group\'s count"\n',
                                     '    if false then\n      branch "tie_room: beyond the group\'s count"\n'),
    "tie-room-tied-already-dropped": ("tie_room: a root and group tied already not looked at", SEC42,
                                      "  if (← tied? f.root p f.g).isSome then                     -- `f.group in tied[f.beacon_block_root][p]`: a root\n",
                                      "  if false then\n"),
    "tie-room-le": ("tie_room: the count against the limit by <=, not <", SEC42,
                    "    | some limit => n < limit\n", "    | some limit => n ≤ limit\n"),
    "obi-pending-kept": ("on_block_installed: the root's waits not popped", SEC42,
                         "  erasePending root                                         --   own order\n", ""),
    "obi-ids-kept": ("on_block_installed: a released copy's id kept in pending_ids", SEC42,
                     "    setPendingId (← messageId f) false                      -- `pending_ids.discard(message_id(f))`\n"
                     "    release p f                                             -- the reservation goes back\n",
                     "    let _ ← messageId f\n"
                     "    release p f                                             -- the reservation goes back\n"),
    "obi-no-release": ("on_block_installed: a reservation not given back", SEC42,
                       "    release p f                                             -- the reservation goes back\n", ""),
    "obi-release-after": ("on_block_installed: a copy validated before its reservation goes back", SEC42,
                          "    release p f                                             -- the reservation goes back\n"
                          "    onValidated deferDepth p f (← validateChunk f)          -- `on_validated(p, f, validate_chunk(f))`\n",
                          "    let v ← validateChunk f\n    release p f\n    onValidated deferDepth p f v\n"),
    "obi-peers-reversed": ("on_block_installed: the popped root's peers taken in the reverse of the node's order", SEC42,
                           "  for (p, groups) in ← popTiedRoot root do                  -- `for p, groups in tied.pop(root, {}).items():` the\n",
                           "  for (p, groups) in (← popTiedRoot root).reverse do\n"),
    "obi-forgery-released": ("on_block_installed: a tie of a group the root does not commit released", SEC42,
                             "      if g0 != some g then                                  -- a copy naming a group its root does not commit\n",
                             "      if false then\n"),
    "obi-expired-released": ("on_block_installed: a tie of an expired group released, expiry not asked", SEC42,
                             "      if ← expired g then                                   -- its offers went with its lifetime (§8.1)\n",
                             "      if false then\n"),
    "obi-park-kept": ("on_block_installed: the senders' parks not lifted", SEC42,
                      "      let _ ← parkUntil? p g                                -- `park[p].pop(g, None)`: the senders' parks for the\n"
                      "      erasePark p g                                         --   group lift,\n", ""),
    "obi-asked-parked-kept": ("on_block_installed: the last resort's counts not cleared", SEC42,
                              "        if done.contains p then                             --   their indices clear,\n"
                              "          setAskedParked (g, i) (done.erase p)\n", ""),
    "obi-beyond-count-offered": ("on_block_installed: an index beyond a count learnt meanwhile offered again", SEC42,
                                 '          if i ≥ n then\n            branch "on_block_installed: an index beyond the count learnt meanwhile"\n',
                                 '          if false then\n            branch "on_block_installed: an index beyond the count learnt meanwhile"\n'),
    "obi-held-offered": ("on_block_installed: an index held offered again", SEC42,
                         "        if !(← mineBits g).has i then                       --   and each is an offer of its index again\n",
                         "        if true then\n"),
    "obi-no-ledger": ("on_block_installed: the ledger's asks not retried", SEC42,
                      "    for a in ← ledger g0 do                                 --   released, is asked for now\n      retryOffer a\n",
                      "    let _ ← ledger g0\n"),
    "obi-tie-slot-kept": ("on_block_installed: a released peer's tie_slot kept", SEC42,
                          "    let _ ← tieSlot? root p                                 --   copies that waited for this root;\n"
                          "    eraseTieSlot root p                                     --   `tie_slot.pop((root, p), None)`\n", ""),
    "drop-beyond-roots-own-order": ("drop_beyond: tied's roots in the twin's order, the node's asked and not used", SEC42,
                                    "  for r in ← tiedRootsOrder (all.map (·.1)) do\n",
                                    "  let _ ← tiedRootsOrder (all.map (·.1))\n  for r in all.map (·.1) do\n"),
    "drop-tie-retries-always": ("drop_tie: retried whether the group is authenticable or not", SEC42,
                                "    if ← authenticable g then                               -- else the ledger asks at installation\n",
                                "    if true then\n"),
    "drop-tie-no-drop-offer": ("drop_tie: the sender's offers not dropped", SEC42, "    dropOffer g i p\n", ""),
    "stale-waits-expiry-not-asked": ("drop_stale_waits: a wait's expiry not asked", SEC42,
                                     "      if ← expired f.g then\n        stale := stale ++ [(p, f)]\n      else if !(← live f.slot) then\n",
                                     "      if !(← live f.slot) then\n"),
    "stale-waits-window-not-asked": ("drop_stale_waits: a wait's live window not asked", SEC42,
                                     "      else if !(← live f.slot) then\n        stale := stale ++ [(p, f)]\n    for (p, f) in stale do\n",
                                     "    for (p, f) in stale do\n"),
    "stale-waits-ids-kept": ("drop_stale_waits: a stale copy's id kept in pending_ids", SEC42,
                             "      setPendingId (← messageId f) false                    -- `pending_ids.discard(message_id(f))`\n",
                             "      let _ ← messageId f\n"),
    "stale-waits-no-release": ("drop_stale_waits: a stale copy's reservation not given back", SEC42,
                               '      release p f\n      branch "drop_stale_waits: a kept copy gone"\n',
                               '      branch "drop_stale_waits: a kept copy gone"\n'),
    "stale-waits-own-order": ("drop_stale_waits: pending's roots in the twin's order, the node's asked and not used", SEC42,
                              "  for root in ← pendingOrder ((← allPending).map (·.1)) do  -- `for root in list(pending):`\n",
                              "  let rs := (← allPending).map (·.1)\n  let _ ← pendingOrder rs\n  for root in rs do\n"),
    "stale-ties-expiry-not-asked": ("drop_stale_waits: a tie's expiry not asked", SEC42,
                                    "      if ← expired g then\n        stale := stale ++ [g]\n      else if !(← live s) then\n",
                                    "      if !(← live s) then\n"),
    "stale-ties-window-not-asked": ("drop_stale_waits: a tie's live window not asked", SEC42,
                                    "      else if !(← live s) then\n        stale := stale ++ [g]\n", ""),
    "stale-ties-peer-row-kept": ("drop_stale_waits: a peer's emptied row not popped", SEC42,
                                 "      popTiedPeer root p                                    -- `tied[root].pop(p, None)`\n", ""),
    "stale-ties-slot-kept": ("drop_stale_waits: an emptied tie's tie_slot kept", SEC42,
                             "      let _ ← tieSlot? root p                               -- `tie_slot.pop((root, p), None)`\n      eraseTieSlot root p\n",
                             ""),
    "stale-ties-root-row-kept": ("drop_stale_waits: a root's emptied row not popped", SEC42,
                                 '        let _ ← popTiedRoot root\n        branch "drop_stale_waits: a root\'s ties all gone"\n',
                                 '        branch "drop_stale_waits: a root\'s ties all gone"\n'),
    "chunk-defer-depth-one": ("on_chunk: the deferral's fuel (deferDepth) one level, not two", SEC42,
                              "  onValidated deferDepth p f (← validateChunk f)            -- level 1 (§3)\n",
                              "  onValidated 1 p f (← validateChunk f)\n"),
    "tables-tied-row-erase-none": ("the tables: a pop of a root's row of tied notes its writes and erases nothing", TABLES,
                                   "    modify fun s => { s with tied := s.tied.erase r }\n", ""),
    "tables-pending-write-none": ("the tables: a write of pending notes itself and writes nothing", TABLES,
                                  "  setPending r w := do note (.write (.pending r)); modify fun s => { s with pending := s.pending.insert r w }\n",
                                  "  setPending r w := do note (.write (.pending r))\n"),
    "tables-pending-id-read-none": ("the tables: a read of pending_ids notes itself and answers no", TABLES,
                                    "  pendingId? m := do note (.read (.pendingId m)); return (← get).pendingIds.contains m\n",
                                    "  pendingId? m := do note (.read (.pendingId m)); return false\n"),
    "tables-tie-slot-read-none": ("the tables: a read of tie_slot notes itself and answers none", TABLES,
                                  "  tieSlot? r p := do note (.read (.tieSlot r p)); return (← get).tieSlot.get? (r, p)\n",
                                  "  tieSlot? r p := do note (.read (.tieSlot r p)); return none\n"),
    "tables-park-erase-none": ("the tables: an erase of a park notes itself and erases nothing", TABLES,
                               "    modify fun s => { s with park := s.park.insert p ((s.park.getD p {}).erase g) }\n", ""),
    # §7.2's writer: one rule each of the five functions, the bound on next_to_send's turns, the order of owed, and
    # the tables' new writes
    "nts-owed-answer-ignored": ("next_to_send: an owed answer never queued", SEC72,
                                "  if !oa.isEmpty then\n    if ← hasRoom p then\n", "  if false then\n    if ← hasRoom p then\n"),
    "nts-urgent-ignored": ("next_to_send: the urgent lane not looked at", SEC72,
                           "  match (← lane? p .urgent).getD [] with\n", "  match ([] : List QEntry) with\n"),
    "nts-no-release-when-idle": ("next_to_send: a held slot kept when there is nothing to send", SEC72,
                                 '    releaseUnusedSlot p                                     -- nothing to send: a held slot goes back\n', ""),
    "nts-slot-not-noted": ("next_to_send: a slot taken and not noted as held", SEC72,
                           "      setSlotHeld p true\n      return .again bound\n", "      return .again bound\n"),
    "nts-rarest-always": ("next_to_send: rarest whatever the card", SEC72,
                          "  let k ← if c.RAREST then rarest normal else pure 0       -- `entry = q.normal.pop(rarest(q) if RAREST else 0)`\n",
                          "  let k ← rarest normal\n"),
    "nts-first-always": ("next_to_send: the lane's first entry whatever the card", SEC72,
                         "  let k ← if c.RAREST then rarest normal else pure 0       -- `entry = q.normal.pop(rarest(q) if RAREST else 0)`\n",
                         "  let k := 0\n"),
    "nts-no-release-no-chunk": ("next_to_send: the slot kept when no chunk leaves", SEC72,
                                "  if !(out.any (·.chunk.isSome)) then releaseUnusedSlot p   -- no chunk leaves: the slot goes back\n", ""),
    "nts-no-track": ("next_to_send: a chunk sent not tracked in flight", SEC72,
                     "      trackInFlight p f                                     -- [c14] the slot is used\n", ""),
    "nts-slot-still-held": ("next_to_send: the slot still noted as held after a chunk leaves", SEC72,
                            "      trackInFlight p f                                     -- [c14] the slot is used\n      setSlotHeld p false\n",
                            "      trackInFlight p f\n"),
    "nts-owed-not-riding": ("next_to_send: owed offers not added to a popped entry", SEC72,
                            "    return .done (match ← withOwed p o with | some e => .entry e | none => .nothing)   -- owed offers ride along\n",
                            "    return .done (.entry o)\n"),
    "nts-bound-lane-only": ("next_to_send: its turns bounded by the lane's length alone", SEC72,
                            "  let bound := 2 * (normal.length + oa.foldl (fun n (_, b) => n + b.popcount) 0) + 2\n",
                            "  let bound := normal.length\n"),
    "fe-cancel-dropped": ("filter_entry: a chunk the peer holds not cancelled", SEC72,
                          "    if c.CANCEL then cancel := (← peerHas p f.g).has f.i    -- `if CANCEL and peer_has[p][f.group].has(f.index)`\n", ""),
    "fe-answers-projected": ("filter_entry: an answer projected away too", SEC72,
                             "      if c.PROJECT && !entry.solicited then skip ← projected p f.g   -- `elif PROJECT and not entry.solicited and\n",
                             "      if c.PROJECT then skip ← projected p f.g\n"),
    "fe-no-unpush": ("filter_entry: a push projected away not unpushed", SEC72,
                     "        unpush p f.g f.i                                    -- [c3] not made: offered instead (§5.2)\n", ""),
    "fe-sent-to-kept": ("filter_entry: a chunk sent not noted in sent_to", SEC72,
                        "        setSentTo p f.g ((← sentToBits p f.g).set f.i)     -- `sent_to[p][f.group].set(f.index)`\n", ""),
    "fe-held-asks-kept": ("filter_entry: an ask of a chunk held kept", SEC72,
                          "          if ← held a then continue                         --   and not tied_to_root(p, a)`, in that order\n", ""),
    "fe-gated-asks-kept": ("filter_entry: an ask of a group no longer pulled kept", SEC72,
                           "          if ← gated a then continue\n", ""),
    "fe-expired-asks-kept": ("filter_entry: an ask of an expired group kept", SEC72,
                             "          if ← expired a.group then continue\n", ""),
    "fe-tied-asks-kept": ("filter_entry: an ask to a peer whose copy waits kept", SEC72,
                          "          if ← tiedToRoot p a then continue\n", ""),
    "fe-promise-renewed": ("filter_entry: a promise there already set again", SEC72,
                           "          if (← promise? a p).isNone then                   -- `if (a, p) not in promises:`\n",
                           "          if true then\n"),
    "fe-no-promise-timer": ("filter_entry: a promise's timer not armed", SEC72,
                            "            after c.PROMISE (.promiseDue a p (← read).now)  --   `after(PROMISE, promise_due, a, p, now)`\n", ""),
    "wo-pushed-not-taken": ("with_owed: what was pushed not taken out", SEC72,
                            "    let b1 := b0.minus (← pushed p g)\n", "    let b1 := b0\n"),
    "wo-claimed-not-taken": ("with_owed: what the peer claimed not taken out", SEC72,
                             "    let mut b := b1.minus (← peerHas p g)\n", "    let mut b := b1\n"),
    "wo-carried-kept": ("with_owed: the carried chunk's index offered too", SEC72,
                        "      if f.g == g then b := b.clear f.i\n", "      if false then b := b.clear f.i\n"),
    "wo-owed-kept": ("with_owed: an owed group not popped", SEC72, "    eraseOwed p g\n", ""),
    "wo-own-order": ("with_owed: owed's groups in the twin's order, the node's asked and not used", SEC72,
                     "  for g in ← owedOrder p (row.map (·.1)) do\n",
                     "  let _ ← owedOrder p (row.map (·.1))\n  for g in row.map (·.1) do\n"),
    "rarest-past-control": ("rarest: chunks behind a control-only entry looked at too", SEC72,
                            "    | none => break                                         -- never overtake a control-only entry\n",
                            "    | none => pure ()\n"),
    "rarest-latest-wins": ("rarest: the latest of the least wins a tie", SEC72,
                           "      if best.all (h < ·) then                              -- `if h < best:` (inf: always)\n",
                           "      if best.all (h ≤ ·) then\n"),
    "projected-fan-in-one": ("projected: FAN_IN taken as one", SEC72,
                             "  let r := has.popcount + c.FAN_IN * (sent.minus has).popcount ≥ k\n",
                             "  let r := has.popcount + (sent.minus has).popcount ≥ k\n"),
    "projected-gt": ("projected: K reached only past it", SEC72,
                     "  let r := has.popcount + c.FAN_IN * (sent.minus has).popcount ≥ k\n",
                     "  let r := has.popcount + c.FAN_IN * (sent.minus has).popcount > k\n"),
    "projected-sent-whole": ("projected: what was sent counted whole, the confirmed not taken out", SEC72,
                             "  let r := has.popcount + c.FAN_IN * (sent.minus has).popcount ≥ k\n",
                             "  let r := has.popcount + c.FAN_IN * sent.popcount ≥ k\n"),
    "tables-owed-erase-none": ("the tables: an erase of owed notes itself and erases nothing", TABLES,
                               "  eraseOwed p g := do note (.write (.owed p g)); modify fun s => { s with owed := s.owed.modify p (·.erase g) }\n",
                               "  eraseOwed p g := do note (.write (.owed p g))\n"),
    "tables-slot-held-write-none": ("the tables: a write of slot_held notes itself and writes nothing", TABLES,
                                    "      slotHeld := if armed then s.slotHeld.insert p else s.slotHeld.erase p }\n",
                                    "      slotHeld := s.slotHeld }\n"),
    "tables-sent-to-write-none": ("the tables: a write of sent_to notes itself and writes nothing", TABLES,
                                  '    modify fun s => { s with sentTo := s.sentTo.insert p ((s.sentTo.getD p {}).insert g b) }\n', ""),
    "tables-lane-write-none": ("the tables: a write of a lane notes itself and writes nothing", TABLES,
                               '    modify fun s => { s with queue := s.queue.insert p ((s.queue.getD p {}).insert l es) }\n', ""),
}


# rules of the deferral path, §7.2's writer and their tables that no mutant above changes
GA5 = {         # name -> (what it changes, file, old, new)
    # the deferral path
    "defer-kept-unreserved": ("defer: a copy kept whether its reservation was granted or not", SEC42,
                              "  if ← reserve p f then                                     -- a per-peer reservation in a bounded store (§8.2)\n",
                              "  let _ ← reserve p f\n  if true then\n"),
    "defer-no-tie": ("defer: tie not called", SEC42,
                     "  tie p f                                                   -- kept or refused, its sender is tied to the root\n", ""),
    "tie-not-admitted-tied": ("tie: a copy of a group not admitted tied anyway, admitted asked", SEC42,
                              "  if !(← admitted p f) then                                 -- `if not admitted(p, f) or not tie_room(p, f): return`\n"
                              "    branch \"tie: not admitted\"\n    return\n",
                              "  let _ ← admitted p f\n"),
    "obi-waits-reversed": ("on_block_installed: a root's waits validated in reverse", SEC42,
                           "  for (p, f) in waits do\n    setPendingId (← messageId f) false",
                           "  for (p, f) in waits.reverse do\n    setPendingId (← messageId f) false"),
    "stale-waits-not-removed": ("drop_stale_waits: a stale copy left in pending", SEC42,
                                "      setPending root ((← pendingOf root).erase (p, f))     -- `pending[root].remove((p, f))`: the first equal pair\n", ""),
    "stale-ties-slots-own-order": ("drop_stale_waits: tie_slot's pairs in the twin's order, the node's asked and not used", SEC42,
                                   "  for (root, p) in ← tieSlotOrder (slots.map (·.1)) do       -- `for (root, p), s in list(tie_slot.items()):`\n",
                                   "  let _ ← tieSlotOrder (slots.map (·.1))\n  for (root, p) in slots.map (·.1) do\n"),
    "stale-ties-groups-own-order": ("drop_stale_waits: a peer's groups in the twin's order, the node's asked and not used", SEC42,
                                    "    for g in ← tiedGroupsOrder root p (gs.map (·.1)) do\n      if ← expired g then",
                                    "    let _ ← tiedGroupsOrder root p (gs.map (·.1))\n    for g in gs.map (·.1) do\n      if ← expired g then"),
    # the writer
    "nts-no-room-asked": ("next_to_send: an owed answer queued without has_room asked", SEC72,
                          "    if ← hasRoom p then\n", "    if true then\n"),
    "nts-owed-answer-unsolicited": ("next_to_send: an owed answer queued as unsolicited", SEC72,
                                    "solicited := true }) false", "solicited := false }) false"),
    "nts-urgent-not-riding": ("next_to_send: an urgent entry sent without its owed offers", SEC72,
                              "    return .done (match ← withOwed p e with | some e => .entry e | none => .nothing)\n",
                              "    return .done (.entry e)\n"),
    "nts-urgent-last": ("next_to_send: the urgent lane's last entry popped, not its first", SEC72,
                        '  match (← lane? p .urgent).getD [] with\n  | e :: rest =>\n    setLane p .urgent rest                                  -- `q.urgent.pop(0)`\n',
                        '  match ((← lane? p .urgent).getD []).reverse with\n  | e :: rest =>\n    setLane p .urgent rest.reverse\n'),
    "nts-owed-alone-dropped": ("next_to_send: owed offers alone not sent", SEC72,
                               "    if let some o := out then\n      branch \"next_to_send: owed offers alone\"\n      return .done (.entry o)\n", ""),
    "nts-wait-as-nothing": ("next_to_send: nothing returned where the writer waits in line (WAIT)", SEC72,
                            "        return .done .wait\n", "        return .done .nothing\n"),
    "nts-again-as-nothing": ("next_to_send: an entry filtered to nothing ends the call, not again", SEC72,
                             "    return .again bound                                     -- start again from the urgent lane\n",
                             "    return .done .nothing\n"),
    "nts-bound-no-answers": ("next_to_send: the bound on its turns without the owed answers' term", SEC72,
                             "  let bound := 2 * (normal.length + oa.foldl (fun n (_, b) => n + b.popcount) 0) + 2\n",
                             "  let bound := 2 * normal.length + 2\n"),
    "fe-cancel-card-ignored": ("filter_entry: a chunk the peer holds cancelled whatever the card", SEC72,
                               "    if c.CANCEL then cancel := (← peerHas p f.g).has f.i    -- `if CANCEL and peer_has[p][f.group].has(f.index)`\n",
                               "    cancel := (← peerHas p f.g).has f.i\n"),
    "fe-project-card-ignored": ("filter_entry: a push projected away whatever the card", SEC72,
                                "      if c.PROJECT && !entry.solicited then skip ← projected p f.g   -- `elif PROJECT and not entry.solicited and\n",
                                "      if !entry.solicited then skip ← projected p f.g\n"),
    "fe-promise-not-set": ("filter_entry: a promise's timer armed, its start not written", SEC72,
                           "            setPromise a p (← read).now                     --   `promises[(a, p)] = now`\n", ""),
    "fe-promise-start-zero": ("filter_entry: a promise started at 0, not now", SEC72,
                              "            setPromise a p (← read).now ", "            setPromise a p 0 "),
    "fe-empty-kept": ("filter_entry: an entry left empty returned", SEC72,
                      "  return if e.isEmpty then none else some e                 -- control rides on and survives\n",
                      "  return some e\n"),
    "wo-empty-kept": ("with_owed: an entry left empty returned", SEC72,
                      "  return if e.isEmpty then none else some e\n\n/-- `filter_entry(p, entry)`",
                      "  return some e\n\n/-- `filter_entry(p, entry)`"),
    "wo-empty-offered": ("with_owed: an IHAVE added for an empty bitmap", SEC72,
                         "    if b != 0 then e := e.addIhave g b                      -- `if b: entry.add_ihave(HaveBitmap(group=g, bits=b))`\n",
                         "    e := e.addIhave g b\n"),
    "wo-popped-not-offered": ("with_owed: owed bits popped, no IHAVE added", SEC72,
                              "    if b != 0 then e := e.addIhave g b                      -- `if b: entry.add_ihave(HaveBitmap(group=g, bits=b))`\n",
                              ""),
    # the tables
    "tables-promise-write-none": ("the tables: a write of a promise notes itself and writes nothing", TABLES,
                                  "  setPromise a p t := do note (.write (.promise a p)); modify fun s => { s with promises := s.promises.insert (a, p) t }\n",
                                  "  setPromise a p t := do note (.write (.promise a p))\n"),
}

MUTANTS = {}                            # name -> (what it changes, file, old, new)
for _name, (_what, _old, _new) in M2.MUTANTS.items():
    if _name in IN_TABLES:
        MUTANTS[_name] = (_what + " (done by the tables' setAskedAt, which notes its one write)", TABLES, *IN_TABLES[_name])
    else:
        MUTANTS[_name] = (_what, SEC61, *MOVED.get(_name, (_old, _new)))
MUTANTS.update(NEW)
MUTANTS.update(SLICE1)
MUTANTS.update(V010)
MUTANTS.update(SLICE2A)
MUTANTS.update(QMOVE)
MUTANTS.update(AEND)
MUTANTS.update(GA5)
# Left out of the tool: since drop_offer is the twin's own code and no call on the tape, drop_beyond's calls of it
# for two indices show in no record (they commute, and the queue's order is asked of the same rows each time).
# Built and replayed on the sixteen directed sets: no record mismatches, 0 reads not made. Kept as text, in no list.
LEFT = {
    "drop-beyond-reversed": ("drop_beyond: the indices in falling order", SEC42,
                             "  for i in (sortBy (· < ·) idx.eraseDups) do", "  for i in (sortBy (· > ·) idx.eraseDups) do"),
    # `origin` is the twin's own table. The same entry read once or twice is one entry of a record's reads (as calls
    # on the tape they would be two reads): nothing tells this from the twin (predicted before the build, then built
    # and replayed on the sixteen directed sets and three cells)
    "have-bits-origin-once": ("have_bits: origin read once", SEC42,
                              "  if (← origin g).isSome then                               -- `origin[g] if g in origin else mine[g]`\n"
                              "    match ← origin g with\n",
                              "  let o ← origin g\n  if o.isSome then\n    match o with\n"),
    # `desc` is the twin's own table: as above, by protocol.md:715
    "valid-id-desc-read-once": ("valid_id: desc[g] read once, where the Python reads it twice (`in`, then `[]`)", SEC44,
                                VALID_DESC,
                                '    let d ← desc a.group\n    if d.isNone then\n'
                                '      branch "valid_id: the count not known"\n      return true\n    let n ← N d\n'),
}
assert not set(LEFT) & set(MUTANTS)
import mutants_c1 as C1                 # noqa: E402
assert not set(C1.CYCLE1) & set(MUTANTS), "a mutant of mutants_c1.py under a name already taken"
CYCLE1 = C1.CYCLE1
MUTANTS.update(CYCLE1)
import mutants_c2 as C2                 # noqa: E402
assert not set(C2.CYCLE2) & set(MUTANTS), "a mutant of mutants_c2.py under a name already taken"
MUTANTS.update(C2.CYCLE2)
COUNTS = (f"{len(MUTANTS)} mutants: {len(M2.MUTANTS)} of mutants.py's ({len(M2.MUTANTS) - len(MOVED) - len(IN_TABLES)} as "
          f"they were, {len(MOVED)} moved onto the tables, {len(IN_TABLES)} kept as a change of the tables), {len(NEW)} new"
          f", {len(SLICE1)} of §4.4 and §6.2, {len(V010)} of v0.10's §4.4 (valid_id, a bitmap's valid_have)"
          f", {len(SLICE2A)} of §4.2, {len(QMOVE)} of the twin's own queue and more of §4.2"
          f", {len(AEND)} of §6.1's outstanding, §4.2's deferred chunks and §7.2's writer, {len(GA5)} more of §4.2's"
          f" deferred chunks and §7.2's writer, {len(C1.CYCLE1)} of §1 to §3, §4.1, §4.3, §4.5, §4.6, §6.2, §6.4 and"
          f" drop_offer (mutants_c1.py), {len(C2.CYCLE2)} of §5 and §7.1, and more of the functions above"
          f" (mutants_c2.py)")


# Which records a mutant is replayed on. A mutant of a traced function: the records whose call reached that
# function, which its description names before its first colon. A mutant of an operation of the tables (its change
# is in SpecTwin/Tables.lean): the records that touch that operation's table. The replay picks them by each
# record's last two members (`--only`). With --all every mutant runs on every record: the two must give the same
# tallies, which is the filter's known answer.
TABLE_OF = {
    "may-ask-erases-group": "asked_at", "tables-read-wide": "park", "tables-erase-none": "last_resort_armed",
    "no-note-read": "asked_at", "tables-erase-wide": "promises", "tables-write-wide": "park",
    "tables-offered-wide": "offered", "no-note-write": "asked_at", "tables-rpcs-write-none": "ihave_frames",
    "tables-rpcs-read-asked": "ihave_frames", "tables-asked-write-wide": "ihave_asked",
    "tables-asked-read-zero": "ihave_asked", "tables-heldback-write-none": "held_back",
    "tables-heldback-wide": "held_back",
    "tables-tied-erase-row": "tied", "tables-mine-write-none": "mine", "tables-state-read-none": "state",
    "tables-received-read-zero": "received",
    "tables-lane-read-none": "queue", "tables-tied-write-none": "tied",     # QMOVE
    "tables-tied-row-erase-none": "tied", "tables-pending-write-none": "pending",    # the deferral path
    "tables-pending-id-read-none": "pending_ids", "tables-tie-slot-read-none": "tie_slot",
    "tables-park-erase-none": "park",
    "tables-owed-erase-none": "owed", "tables-slot-held-write-none": "slot_held",      # §7.2's writer
    "tables-sent-to-write-none": "sent_to", "tables-lane-write-none": "queue",
    "tables-promise-write-none": "promises",   # GA5
}
TABLE_OF.update(C1.TABLE_OF)            # mutants_c1.py's
TABLE_OF.update(C2.TABLE_OF)            # mutants_c2.py's
TRACED = ("may_ask", "retry_offer", "outstanding", "add_offer", "announcers", "ledger", "untried",
          "least_recently_tried", "promise_due", "parked", "last_resort", "ask_parked",
          "on_ihave", "over_ihave_limits", "valid_id", "expand", "gated",
          "held", "tied_to_root", "on_chunk", "on_validated", "send_have", "have_bits", "close_promises", "drop_beyond",
          "defer", "tie", "tie_room", "on_block_installed", "drop_tie", "drop_stale_waits",   # the deferral path
          "next_to_send", "filter_entry", "with_owed", "rarest", "projected")                  # §7.2's writer
TRACED += C1.TRACED                     # mutants_c1.py's
TRACED += C2.TRACED                     # mutants_c2.py's


# The operations of each table and its field of the state, by their exact names in SpecTwin/Tables.lean and
# State.lean: what a mutant picked by that table may patch. Written here by hand, for the tables that have a mutant.
TABLE_NAMES = {
    "asked_at": ("askedAt?", "setAskedAt", "askedAt"), "park": ("parkUntil?", "setPark", "erasePark", "park"),
    "last_resort_armed": ("lrArmed?", "setLrArmed", "lastResortArmed"),
    "promises": ("promise?", "setPromise", "erasePromise", "allPromises", "promises"),
    "offered": ("offeredBits", "setOffered", "offered"), "ihave_frames": ("ihaveFrames", "setIhaveFrames"),
    "ihave_asked": ("ihaveAsked", "setIhaveAsked"), "held_back": ("heldBack?", "setHeldBack", "heldBack"),
    "tied": ("tied?", "setTied", "eraseTied", "tiedRow?", "eraseTiedRow", "tiedPeerRow?", "eraseTiedPeerRow", "tied"),
    "mine": ("mineBits", "setMine", "mine"),
    "state": ("state?", "setState", "state"), "received": ("receivedBits", "setReceived", "received"),
    "queue": ("lane?", "setLane", "allQueue", "queue"),
    # the deferral path
    "pending": ("pendingOf", "setPending", "erasePending", "allPending", "pending"),
    "pending_ids": ("pendingId?", "setPendingId", "allPendingIds", "pendingIds"),
    "tie_slot": ("tieSlot?", "setTieSlot", "eraseTieSlot", "allTieSlot", "tieSlot"),
    # §7.2's writer
    "owed": ("owed?", "setOwed", "eraseOwed", "owedRow?", "eraseOwedRow", "allOwed", "owed"),
    "slot_held": ("slotHeld?", "setSlotHeld", "allSlotHeld", "slotHeld"),
    "sent_to": ("sentToBits", "setSentTo", "sentTo"),
}
TABLE_NAMES.update(C1.TABLE_NAMES)      # mutants_c1.py's tables, then (below) its operations of three tables above
TABLE_NAMES.update(C2.TABLE_NAMES)      # mutants_c2.py's
for _t, _more in C1.TABLE_NAMES_MORE.items():
    TABLE_NAMES[_t] = TABLE_NAMES[_t] + _more


def only(name):
    """The replay's --only for a mutant: fn=NAME or table=NAME. Every mutant must have one.
    fn=NAME takes the records that reached NAME and, for a name a node may replace, the records that ask it on
    their tape (the replay's `asks`: a mutant of the twin's line that asks the node runs at those records alone)."""
    what, file = MUTANTS[name][0], MUTANTS[name][1]
    if file == TABLES:
        if name not in TABLE_OF:
            raise SystemExit(f"{name}: a mutant of the tables with no table named for it (TABLE_OF)")
        return f"table={TABLE_OF[name]}"
    fn = what.split(":")[0]
    if fn not in TRACED:
        raise SystemExit(f"{name}: its description does not begin with a traced function's name: {what[:40]!r}")
    return f"fn={fn}"


def enclosing(file, old):
    """The Lean `def` whose text holds the first line of a mutant's patch, as the Python's name (onIhave -> on_ihave)."""
    text = (TWIN / file).read_text()
    at = text.index(old)
    # the nearest declaration at or before the patch, whatever its kind: only a plain `def NAME` at a line's start
    # counts as a traced function's own (a helper, a `private def` or a theorem above the patch gives None)
    decls = [m for m in re.finditer(r"^(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|noncomputable|partial|unsafe)\s+)*"
                                    r"(def|theorem|abbrev|instance|structure|class|inductive|opaque|axiom)\b[ \t]*(\w*)", text, re.M)
             if m.start() <= at]
    if not decls or not decls[-1].group(0).startswith("def "):
        return None
    return re.sub(r"(?<!^)([A-Z])", lambda m: "_" + m.group(1).lower(), decls[-1].group(2))


def patched_name(old):
    """The name a table mutant's patch begins with: the whole Lean identifier, digits, underscores and a final `?`
    included. A pattern of letters alone would stop before a digit or an underscore, and read `askedAt2` as
    `askedAt`."""
    m = re.match(r"\s*(?:modify fun s => \{ s with )?([A-Za-z_][A-Za-z0-9_']*\??)(?![A-Za-z0-9_'?])", old)
    return m.group(1) if m else None


def table_self_test():
    """The table check's own cases: an exact name passes, a longer name that begins the same way does not."""
    cases = [("  askedAt? a := do note (.read (.askedAt a))", "asked_at", True),
             ("    modify fun s => { s with park := s.park.erase p }", "park", True),
             ("  askedAt2 a := do note (.read (.askedAt a))", "asked_at", False),
             ("  askedAt_x a := do note (.read (.askedAt a))", "asked_at", False),
             ("  setParked p g t := do", "park", False)]
    bad = 0
    for old, table, ok in cases:
        got = patched_name(old) in TABLE_NAMES.get(table, ())
        bad += got != ok
        print(f"table check, {old.strip()[:40]!r} for {table}: {'taken' if got else 'refused'}, must be "
              f"{'taken' if ok else 'refused'}{'' if got == ok else '  <-- FAIL'}")
    print("ok: every case of the table check as it must be" if not bad else f"{bad} cases of the table check wrong")
    return 1 if bad else 0


# the twin's helpers that are a traced function's own code, by the Python name `enclosing` gives them: next_to_send's
# `while True` is `turn`, one turn, and `turns`, the turns after the first. Their records are next_to_send's
PART_OF = {"turn": "next_to_send", "turns": "next_to_send"}
PART_OF.update(C1.PART_OF)              # on_pace_tick's turns, on_heartbeat's count


def place_check(names):
    """A mutant filtered by a function must be patched inside that function: a description that names another one
    would have it replayed on the wrong records, and pass unseen."""
    for n in names:
        what, file, old, _ = MUTANTS[n]
        sub = only(n)
        if sub.startswith("table="):            # a table's mutant: the operation it patches must be that table's
            # by the exact name of the operation or of the state's field that the patch begins with (TABLE_NAMES:
            # "offer" is inside "offered", so a part of a name will not do)
            if patched_name(old) not in TABLE_NAMES.get(sub[6:], ()):
                raise SystemExit(f"{n}: it is picked by the table {sub[6:]}, and the operation it patches is not that "
                                 f"table's: {old[:60]!r}")
            continue
        got = enclosing(file, old)
        got = PART_OF.get(got, got)
        if got != sub[3:]:
            raise SystemExit(f"{n}: its description names {sub[3:]}, and its patch is in {got} ({file}): "
                             f"it would be replayed on the records of another function")


REUSE = False                           # --reuse: a mutant built before in WORKDIR, with its change in place, is not built again


def build(work, name, file, old, new):
    d = work / name
    exe = d / ".lake" / "build" / "bin" / "replay"
    if REUSE and exe.exists() and (d / file).read_text() == (TWIN / file).read_text().replace(old, new):
        return exe
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(TWIN, d, ignore=shutil.ignore_patterns(*layout.NOT_SOURCES))
    f = d / file
    s = f.read_text()
    if s.count(old) != 1:
        raise SystemExit(f"{name}: the replacement matches {s.count(old)} times in {file}")
    f.write_text(s.replace(old, new))
    p = subprocess.run(["lake", "build", "replay"], cwd=d, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"{name}: build failed\n{p.stdout[-2000:]}{p.stderr[-2000:]}")
    return d / ".lake" / "build" / "bin" / "replay"


_CONTENT = []


def content_file(work=None):
    """The file with the tree's content line (content.py), which every replay here is given: written once, under
    the run's work directory, by what replays (not at import)."""
    if work is not None and not _CONTENT:
        f = Path(work) / "content.line"
        f.write_text(content.line(content.content(layout.toy())))
        _CONTENT.append(f)
    if not _CONTENT:
        raise SystemExit("mutants3: no content file written yet (a replay before the run's work directory is known)")
    return _CONTENT[0]


def kind(reason):
    """The kind of a mismatch, from the replay's reason line ("fn: what: ..."). At a raise the reason has a prefix,
    "at the raise (X): ", and is classified by what follows it."""
    what = reason.split(": ", 1)[1] if ": " in reason else reason
    m = re.match(r"at the raise \([^)]*\): (.*)$", what)
    if m:
        what = m.group(1)
    for start, k in (("footprint, reads", "reads"), ("footprint, writes", "writes"), ("post", "state"),
                     ("return value", "return"), ("tape", "tape"), ("the Python raises", "raise"), ("crash", "raise"),
                     ("reached", "reached")):     # the functions the twin entered, against the record's
        if what.startswith(start):
            return k
    return "other"


def replay(exe, trace, sub=None):       # with --content, as cells3.py runs it: a trace of another tree fails
    pick = f"--only {sub} " if sub else ""
    # Both ends of the pipe say how they ended, on a line of their own: the command's own exit code is the echo's,
    # and is not read (`returncode` is not the replay's status).
    p = subprocess.run(["bash", "-c", f"zcat {trace} | {exe} {pick}--content {content_file()}; echo \"statuses ${{PIPESTATUS[*]}}\" >&2"],
                       capture_output=True, text=True)
    st = re.search(r"^statuses (\d+) (\d+)$", p.stderr, re.M)
    zrc, rrc = (int(st.group(1)), int(st.group(2))) if st else (None, None)
    m = re.search(r"^replay: (\d+) records, (\d+) ok, (\d+) mismatched$", p.stdout, re.M)
    first = re.search(r"^example: (.*)$", p.stdout, re.M)
    fewer = re.search(r"^reads of the Python's that the twin did not make: (\d+)$", p.stdout, re.M)
    kinds = Counter()
    for r in re.finditer(r"^mismatch (.*): (\d+)$", p.stdout, re.M):
        kinds[kind(r.group(1))] += int(r.group(2))
    # A replay that did not read its trace whole, or as a trace, gives no verdict, whatever it counted on the way:
    # a trace cut off after a mismatch would else pass for a smaller count. The reader of the trace must have ended
    # well too (zcat's own exit code).
    envelope = [l for l in p.stdout.splitlines()
                if l.startswith(("content: ", "header: ", "nodes: ", "trailer: ", "subset: --only"))
                and not l.startswith(("header: {", "content: as --content's, ")) and "records skipped unread" not in l]
    refused = re.search(r"^lines refused before they were parsed", p.stdout, re.M)
    # A verdict comes only from a report that is whole and agrees with how the replay ended: the summary and the
    # line of the reads are there; the replay ended with 0 or 1, and with 0 exactly when nothing mismatched; it
    # raised nothing.
    why = None
    if zrc != 0:
        why = f"the trace's reader failed (status {zrc})"
    elif envelope:
        why = "\n".join(envelope)
    elif refused:
        why = refused.group(0)
    elif not m or not fewer:
        why = "no whole report"
    elif rrc not in (0, 1) or "uncaught exception" in p.stderr:
        why = f"the replay ended with status {rrc}" + (", on an exception" if "uncaught exception" in p.stderr else "")
    elif (rrc == 0) != (m.group(3) == "0"):
        why = f"the replay ended with status {rrc}, and its report has {m.group(3)} mismatched"
    if why is not None:
        return None, why, 0, kinds
    return (int(m.group(3)) if m else None), (first.group(1)[:300] if first else ""), int(fewer.group(1)) if fewer else 0, kinds


def part_of(spec):
    """`K/N`: the Kth of N parts of a matrix (a matrix past one run's time is run in parts). (K, N), or an exit for
    anything else: N from 1 to 8, K from 1 to N."""
    m = re.fullmatch(r"([1-9])/([1-8])", spec or "")
    if not m or int(m.group(1)) > int(m.group(2)):
        raise SystemExit(f"mutants3: --part is K/N, with N from 1 to 8 and K from 1 to N: {spec!r}")
    return int(m.group(1)), int(m.group(2))


REHEARSAL = None                        # --rehearsal a,b,…: a merge of a few mutants, to try the reading of parts


def whole_list():
    """The mutants a matrix is of: the tool's, or a rehearsal's few."""
    return list(REHEARSAL) if REHEARSAL else list(MUTANTS)


def first_line():
    """A merged report's first line: the tool's counts. A rehearsal's says so there, where the record's run
    (`record.sh`) reads the count of a matrix it adopts: a rehearsal cannot be taken for one."""
    return COUNTS if not REHEARSAL else (f"rehearsal of the reading of parts, {len(REHEARSAL)} of the tool's mutants "
                                         f"(no matrix: nothing of it is adopted): {COUNTS}")


def part_names(names, part):
    """A part's mutants: every Nth of `names`, in their order, from the Kth. The parts of one N split the list:
    each name is in exactly one."""
    k, n = part
    return [x for i, x in enumerate(names) if i % n == k - 1]


def check_report(report, pairs, traces=None, part=(1, 1)):
    """A report's line for each mutant, and its last line, made again from a pairs file (--pairs) and compared: the
    counts, the traces, the kinds and the reads not made. The examples under a mutant's line are not in the pairs
    and are not compared. The record's run (`record.sh`) holds another run's report to that run's pairs with it,
    and makes the hand cell's pairs again itself: so every number of the adopted report is tied to the pairs, and
    one column of the pairs to a run of its own."""
    import ast
    rows = {}
    bad = []
    for l in Path(pairs).read_text().splitlines():
        n, c, cnt, fewer, kinds = l.split(" ", 4)
        if cnt == "no-verdict":
            print(f"{pairs}: no verdict for {n} on {c}")
            return 1
        if any(c == r[0] for r in rows.get(n, [])):
            bad.append(f"(the pairs have {n} on {c} twice)")
        rows.setdefault(n, []).append((c, int(cnt), int(fewer), Counter(ast.literal_eval(kinds))))
    # the pairs are whole: the tool's own mutants, in its order, each on the same traces, which are TRACES' if given
    names = list(rows)
    mine = part_names(whole_list(), part)   # a part's report and pairs hold its mutants, and no other
    if names != mine:
        bad.append("(the pairs' mutants are not the tool's, in its order)" if part == (1, 1) else
                   f"(the pairs' mutants are not part {part[0]} of {part[1]} of the tool's, in its order)")
    cols = [tuple(r[0] for r in res) for res in rows.values()]
    if len(set(cols)) != 1:
        bad.append("(the pairs do not have every mutant on the same traces)")
    if traces is not None:
        # a line a trace, its name last, as `content.py --hashes` writes them: "WHOLE  BODY  traces/NAME.jsonl.gz"
        want = sorted(re.findall(r"  (?:traces|directed)/(\S+?)\.jsonl\.gz$", Path(traces).read_text(), re.M))
        if not cols or sorted(cols[0]) != want or not want:
            bad.append(f"(the pairs' traces are not the {len(want)} of {traces})")
    lines = Path(report).read_text().splitlines()
    own = [l for l in lines[2:-1] if not l.startswith("    ")]
    got = {l.split(": ", 1)[0]: l for l in own}
    if len(got) != len(own):
        bad.append("(a mutant's line twice in the report)")
    if lines[:2] != [first_line() if part == (1, 1) else COUNTS,
                     "each mutant on the records that reached its function or touched its table: "
                     + ", ".join(f"{n} {only(n)}" for n in mine)]:
        bad.append("(the report's first two lines are not the tool's)")
    # the lines under a mutant's line: "    TRACE COUNT: example" for its first two traces that tell it, by the pairs
    cur, under = None, {}
    for l in lines[2:-1]:
        if l.startswith("    "):
            m = re.match(r"    (\S+) (\d+): ", l)
            under.setdefault(cur, []).append((m.group(1), int(m.group(2))) if m else None)
        else:
            cur = l.split(": ", 1)[0]
    for n, res in rows.items():
        if under.get(n, []) != [(r[0], r[1]) for r in res if r[1]][:2]:
            bad.append(f"{n} (its example lines' traces and counts)")
    bad += [n for n in rows if n not in mine] + [n for n in got if n not in rows] + [n for n in rows if n not in got]
    unseen = byfoot = bycount = 0
    for n, res in rows.items():
        if n in bad:
            continue
        hit = [r for r in res if r[1]]
        total, fewer = sum(r[1] for r in res), sum(r[2] for r in res)
        kinds = sum((r[3] for r in res), Counter())
        only_foot = bool(hit) and set(kinds) <= {"reads", "writes"}
        byfoot += only_foot
        bycount += (not hit) and fewer > 0
        unseen += (not hit) and fewer == 0
        how = (f"{total} mismatched records in {len(hit)} of {len(res)} traces, by {dict(sorted(kinds.items()))}"
               if hit else "no record mismatches")
        want = (f"{n}: {MUTANTS[n][0]}: {how}; {fewer} reads not made"
                + ("  <-- the notes alone" if only_foot else "")
                + ("  <-- the count of reads not made alone" if not hit and fewer else "")
                + ("  <-- no record tells it from the twin" if not hit and not fewer else ""))
        if got[n] != want:
            bad.append(n)
    last = (f"{len(rows) - unseen} of {len(rows)} mutants told from the twin by these traces: "
            f"{len(rows) - unseen - bycount} by a record that mismatches ({byfoot} of them by the notes alone: "
            f"return value, tape and state as the Python's), "
            f"{bycount} by the count of reads not made alone")
    if lines[-1] != last:
        bad.append("(the last line)")
    print(f"{report} against {pairs}: "
          + (f"the report is the pairs': its first two lines, each of the {len(rows)} mutants' lines with the counts of the "
             f"examples under it, and its last line; the pairs have each mutant on the same {len(cols[0]) if cols else 0} traces"
             if not bad else "NOT the pairs': " + ", ".join(bad[:8])))
    return 1 if bad else 0


LAST = re.compile(r"^(\d+) of (\d+) mutants told from the twin by these traces: (\d+) by a record that mismatches "
                  r"\((\d+) of them by the notes alone: return value, tape and state as the Python's\), "
                  r"(\d+) by the count of reads not made alone$")
# what every part must have alike: the content line (what it ran: the documents, the toy, the tools), the traces'
# and the directed sets' two hashes each, the cells' report, the replay as built
SAME = ("content.line", "traces.sha256", "cells.txt", "replay.sha256", "directed.sha256")
MERGED = SAME + ("mutants.sha256", "mutants-pairs.txt", "mutants-directed-pairs.txt", "mutants-cells.txt",
                 "mutants-directed.txt", "PARTS")


def blocks(path, names):
    """A report's lines per mutant (its line and the indented ones under it), and the numbers of its last line.
    The report must be of exactly `names`, in order, with the tool's two first lines for them."""
    lines = Path(path).read_text().splitlines()
    if len(lines) < 3 or lines[0] != COUNTS or not lines[1].endswith(", ".join(f"{n} {only(n)}" for n in names)):
        raise SystemExit(f"merge: {path}: its first two lines are not the tool's for its part")
    m = LAST.match(lines[-1])
    if not m:
        raise SystemExit(f"merge: {path}: its last line is not a report's (a replay with no verdict?): {lines[-1][:80]!r}")
    out, cur = {}, None
    for l in lines[2:-1]:
        if not l.startswith("    "):
            cur = l.split(": ", 1)[0]
            if cur in out:
                raise SystemExit(f"merge: {path}: {cur} twice")
            out[cur] = []
        if cur is None:
            raise SystemExit(f"merge: {path}: a line before the first mutant's")
        out[cur].append(l)
    if list(out) != names:
        raise SystemExit(f"merge: {path}: its mutants are not its part's, in the tool's order")
    return out, [int(x) for x in m.groups()]


SAMPLE_FILE = HERE / "sample_drafts.txt"   # the drafts' sample: "NAME<tab>REASON" a line, made by --sample-make


def group_of(name):
    """The table of this tool a mutant comes from: the drafts' sample takes at least one of each group and kind."""
    if name in M2.MUTANTS:
        return "IN_TABLES" if name in IN_TABLES else "MOVED" if name in MOVED else "M2"
    for g, t in (("NEW", NEW), ("SLICE1", SLICE1), ("V010", V010), ("SLICE2A", SLICE2A), ("QMOVE", QMOVE),
                 ("AEND", AEND), ("GA5", GA5), ("CYCLE1", CYCLE1), ("CYCLE2", C2.CYCLE2)):
        if name in t:
            return g
    raise SystemExit(f"mutants3: {name}: in no table of this tool")


def sample_table(merged, main_override=None):
    """The drafts' sample, made from a merged matrix's two pairs files: [(name, reason)] in the tool's order. A
    mutant is in it for the first of these that holds: the first of its group with its main kind (the kind most of
    its mismatched records have, or "none"); the footprint class (main kind `reads` or `writes`: the tables' notes);
    told by the notes alone; told by the count of reads not made alone. (Every mutant goes on the directed sets in a
    draft's run, so one only the directed sets tell needs no place here.) `main_override` changes main kinds: the
    control of --sample-check."""
    def pairs(p):
        out = {}
        for l in Path(p).read_text().splitlines():
            m, t, c, r, k = l.split(" ", 4)
            out.setdefault(m, []).append((int(c) if c.isdigit() else 0, int(r), Counter(ast.literal_eval(k))))
        return out
    d, c = pairs(Path(merged) / "mutants-directed-pairs.txt"), pairs(Path(merged) / "mutants-pairs.txt")
    if set(d) != set(MUTANTS) or set(c) != set(MUTANTS):
        raise SystemExit(f"mutants3: {merged}: its pairs are not of this tool's {len(MUTANTS)} mutants")
    told = {n: [p for p in d[n] + c[n] if p[0] > 0 or p[1] > 0] for n in MUTANTS}
    kinds = {n: sum((p[2] for p in told[n]), Counter()) for n in MUTANTS}
    main = {n: (kinds[n].most_common(1)[0][0] if kinds[n] else "none") for n in MUTANTS}
    main.update(main_override or {})
    reason, seen = {}, set()
    for n in MUTANTS:
        if (group_of(n), main[n]) not in seen:
            seen.add((group_of(n), main[n]))
            reason[n] = f"the first of group {group_of(n)} told mainly by {main[n]}"
    for n in MUTANTS:
        if main[n] in ("reads", "writes"):
            reason.setdefault(n, "the footprint class: told mainly by the tables' notes")
        if told[n] and set(kinds[n]) <= {"reads", "writes"}:
            reason.setdefault(n, "told by the notes alone")
        if told[n] and all(p[0] == 0 for p in told[n]):
            reason.setdefault(n, "told by the count of reads not made alone")
    return [(n, reason[n]) for n in MUTANTS if n in reason]


def sample_read():
    """The tool's drafts' sample: {name: reason}."""
    if not SAMPLE_FILE.exists():
        raise SystemExit(f"mutants3: no drafts' sample ({SAMPLE_FILE.name}): make it with --sample-make MERGED")
    rows = [l.split("\t", 1) for l in SAMPLE_FILE.read_text().splitlines() if l.strip()]
    names = [r[0] for r in rows]
    if any(len(r) != 2 for r in rows) or len(set(names)) != len(names) or not set(names) <= set(MUTANTS):
        raise SystemExit(f"mutants3: {SAMPLE_FILE.name}: not a table of this tool's mutants, each once with a reason")
    return dict(rows)


def sample_make(merged):
    """--sample-make MERGED: the drafts' sample made from a merged matrix, written to sample_drafts.txt."""
    t = sample_table(merged)
    SAMPLE_FILE.write_text("".join(f"{n}\t{r}\n" for n, r in t))
    by = Counter("one per group and kind" if r.startswith("the first") else r.split(":")[0] for _, r in t)
    print(f"the drafts' sample: {len(t)} of {len(MUTANTS)} mutants, by reason {dict(by)}")
    return 0


def sample_check(merged):
    """--sample-check MERGED: the sample made again from MERGED is the tool's table; and its control: with one
    mutant of the footprint class given another main kind, the table made is another."""
    t = sample_table(merged)
    tool = list(sample_read().items())
    same = [tuple(x) for x in tool] == t
    print(f"the drafts' sample made again from {merged}: {len(t)} mutants; the tool's: {len(tool)}; "
          f"{'the same, each with its reason' if same else 'NOT the same'}")
    fp = [n for n, r in t if r.startswith("the footprint class")]
    ctl = bool(fp) and sample_table(merged, {fp[0]: "tape"}) != t
    print(f"control, {fp[0] if fp else 'no footprint member'} given the main kind tape: "
          f"{'another table, as it must be' if ctl else 'the same table  <-- FAIL'}")
    return 0 if same and ctl else 1


def merge(outdir, parts):
    """The parts of one matrix, read as one. PARTS are the directories the matrix step of `check.sh` writes
    (`matrix/out`), part 1 first. Refused unless: each part holds exactly its slice of the tool's mutants; every
    part ran the same content (its content line) on the same traces and directed sets (their two hashes each),
    with the same replay and the same report on the cells; each part's two reports are its two pairs files'.
    Writes OUTDIR in a part's form: the pairs, the builds' hashes and the two reports in the tool's order, each
    mutant's lines as its part has them, the last lines' numbers added; then holds each merged report to its
    merged pairs."""
    import hashlib
    parts = [Path(d) for d in parts]
    n = len(parts)
    if not 2 <= n <= 8:
        raise SystemExit("merge: two to eight parts")
    for d in parts:                                 # a draft's sample ran only some mutants on the cells: no matrix
        if (d / "SAMPLE").exists():
            raise SystemExit(f"merge: {d} is a part of a draft's sample, not of a matrix: the merge reads a matrix's parts alone")
    whole = whole_list()
    first = parts[0]
    sha, pairs, dpairs, cells, directed = {}, {}, {}, {}, {}
    sums = {"cells": [0] * 5, "directed": [0] * 5}
    for k, d in enumerate(parts, 1):
        names = part_names(whole, (k, n))
        for f in SAME:
            if (d / f).read_bytes() != (first / f).read_bytes():
                raise SystemExit(f"merge: part {k}'s {f} is not part 1's")
        got = [l.split()[1] for l in (d / "mutants.sha256").read_text().splitlines()]
        if got != names:
            raise SystemExit(f"merge: part {k}'s builds are not part {k} of {n} of the tool's mutants, in its order")
        if check_report(d / "mutants-cells.txt", d / "mutants-pairs.txt", d / "traces.sha256", (k, n)):
            raise SystemExit(f"merge: part {k}'s report on the cells is not its pairs'")
        if check_report(d / "mutants-directed.txt", d / "mutants-directed-pairs.txt", d / "directed.sha256", (k, n)):
            raise SystemExit(f"merge: part {k}'s report on the directed sets is not its pairs'")
        for l in (d / "mutants.sha256").read_text().splitlines():
            sha[l.split()[1]] = l
        for f, table in (("mutants-pairs.txt", pairs), ("mutants-directed-pairs.txt", dpairs)):
            for l in (d / f).read_text().splitlines():
                table.setdefault(l.split(" ", 1)[0], []).append(l)
        for what, table in (("cells", cells), ("directed", directed)):
            b, nums = blocks(d / f"mutants-{what}.txt", names)
            table.update(b)
            sums[what] = [x + y for x, y in zip(sums[what], nums)]
    if list(sha) and sorted(sha) != sorted(whole) or sorted(pairs) != sorted(whole) or sorted(dpairs) != sorted(whole):
        raise SystemExit("merge: the parts together are not the tool's mutants")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    stray = sorted(x.name for x in out.iterdir() if x.name not in MERGED + ("outputs.sha256",))
    if stray:
        raise SystemExit(f"merge: {out} holds what a merge does not write: {stray[:4]}")
    for f in SAME:
        (out / f).write_bytes((first / f).read_bytes())
    (out / "mutants.sha256").write_text("".join(sha[x] + "\n" for x in whole))
    (out / "mutants-pairs.txt").write_text("".join(l + "\n" for x in whole for l in pairs[x]))
    (out / "mutants-directed-pairs.txt").write_text("".join(l + "\n" for x in whole for l in dpairs[x]))
    pick = ("each mutant on the records that reached its function or touched its table: "
            + ", ".join(f"{x} {only(x)}" for x in whole))
    for what, table in (("cells", cells), ("directed", directed)):
        a, b, c, e, f = sums[what]
        last = (f"{a} of {b} mutants told from the twin by these traces: {c} by a record that mismatches ({e} of them "
                f"by the notes alone: return value, tape and state as the Python's), {f} by the count of reads not made alone")
        (out / f"mutants-{what}.txt").write_text("\n".join([first_line(), pick] + [l for x in whole for l in table[x]] + [last]) + "\n")
    (out / "PARTS").write_text("".join(
        f"part {k} of {n}: {d.resolve().parent.name}; its outputs.sha256 {hashlib.sha256((d / 'outputs.sha256').read_bytes()).hexdigest()}\n"
        for k, d in enumerate(parts, 1)))
    (out / "outputs.sha256").write_text("".join(
        f"{hashlib.sha256((out / f).read_bytes()).hexdigest()}  {f}\n" for f in MERGED))
    if check_report(out / "mutants-cells.txt", out / "mutants-pairs.txt", out / "traces.sha256"):
        raise SystemExit("merge: the merged report on the cells is not the merged pairs'")
    if check_report(out / "mutants-directed.txt", out / "mutants-directed-pairs.txt", out / "directed.sha256"):
        raise SystemExit("merge: the merged report on the directed sets is not the merged pairs'")
    print(f"merge: {n} parts read as one matrix in {out}: {len(whole)} mutants; the directed sets tell {sums['directed'][0]} of "
          f"{sums['directed'][1]}")
    return 0


def places(argv):
    """--places [--twin DIR] [--part K/N]: every mutant's text held to the twin, and nothing built. Each replacement
    must stand in its file exactly once and change it, and sit in the function (or be the table's operation) its
    description names. A text only; a second here. A change of the twin can move a mutant's text: this finds it
    before anything is built. A step of the quick check (`check.sh`) and of the record's run (`record.sh`)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--twin", default=None)
    ap.add_argument("--part", default="1/1")
    a = ap.parse_args(argv)
    if a.twin:
        global TWIN
        TWIN = Path(a.twin).resolve()
    names = part_names(list(MUTANTS), part_of(a.part))
    bad = 0
    for n in names:
        _what, file, old, new = MUTANTS[n]
        c = (TWIN / file).read_text().count(old)
        why = None
        if c != 1:
            why = f"its text stands {c} times in {file}, not once"
        elif old == new:
            why = "its change changes nothing"
        else:
            try:
                place_check([n])
            except SystemExit as e:
                why = str(e)
        if why:
            bad += 1
            print(f"{n}: {why}  <-- NOT")
    print(f"{len(names) - bad} of {len(names)} mutants' texts stand in the twin once, each in the place its description names")
    return 1 if bad else 0


def typecheck(argv):
    """--typecheck BUILT WORK [-j N] [--part K/N] [NAME...]: each mutant's file, with
    its change, compiled alone against the imports of BUILT, a built copy of the twin's sources (the quick check's,
    or a run's own build). Nothing is linked and no replay is made: what it finds is a change that no longer
    type-checks in the twin as it is now, minutes into a matrix and not at that mutant's build. With it a control: a
    change that must not type-check. (A change whose own file compiles and a later file does not is found at its
    build alone.)"""
    ap = argparse.ArgumentParser()
    ap.add_argument("built")
    ap.add_argument("work")
    ap.add_argument("-j", type=int, default=8)
    ap.add_argument("--part", default="1/1")
    ap.add_argument("mutants", nargs="*")
    a = ap.parse_intermixed_args(argv)
    global TWIN
    TWIN = Path(a.built).resolve()
    if not (TWIN / ".lake" / "build" / "lib").is_dir():
        raise SystemExit(f"mutants3 --typecheck: {TWIN} is no built copy of the twin (no .lake/build/lib)")
    work = Path(a.work).resolve()
    names = part_names(a.mutants or list(MUTANTS), part_of(a.part))

    def one(job):
        name, file, old, new = job
        src = (TWIN / file).read_text()
        if src.count(old) != 1:
            return name, None, f"its text stands {src.count(old)} times in {file}"
        d = work / name
        d.mkdir(parents=True, exist_ok=True)
        f = d / Path(file).name
        f.write_text(src.replace(old, new))
        p = subprocess.run(["lake", "env", "lean", str(f)], cwd=TWIN, capture_output=True, text=True)
        errs = [x for x in (p.stdout + p.stderr).splitlines() if ": error" in x or x.startswith("error")]
        return name, p.returncode, (errs[0][-200:] if errs else (p.stdout + p.stderr).strip()[-200:])

    jobs = [(n, *MUTANTS[n][1:]) for n in names]
    # the control: a change of §1's N that cannot type-check (a count joined to a string)
    control = ("control, a change that does not type-check", "SpecTwin/Sec1.lean", "  return d.count\n", '  return d.count ++ ""\n')
    with ThreadPoolExecutor(a.j) as ex:
        res = list(ex.map(one, jobs + [control]))
    bad = 0
    for name, rc, why in res[:-1]:
        if rc != 0:
            bad += 1
            print(f"{name}: rc={rc}: {why}  <-- does NOT type-check")
    cname, crc, cwhy = res[-1]
    cok = crc not in (0, None) and "error" in cwhy
    print(f"{cname}: rc={crc}{': it fails, as it must' if cok else '  <-- it must fail with an error'}")
    print(f"{len(names) - bad} of {len(names)} mutants type-check alone against the twin's built imports")
    return 1 if bad or not cok else 0


def main(argv):
    if argv == ["--self-test"]:
        return table_self_test()
    if len(argv) >= 6 and argv[0] == "--merge" and argv[-2] == "--rehearsal":
        global REHEARSAL
        REHEARSAL = argv[-1].split(",")
        if len(set(REHEARSAL)) != len(REHEARSAL) or not set(REHEARSAL) <= set(MUTANTS) or len(REHEARSAL) >= len(MUTANTS):
            raise SystemExit("mutants3: --rehearsal names a few of the tool's mutants, each once")
        return merge(argv[1], argv[2:-2])
    if len(argv) >= 4 and argv[0] == "--merge":
        return merge(argv[1], argv[2:])
    if len(argv) in (5, 6) and argv[0] == "--check-report" and argv[-2] == "--part":
        return check_report(*argv[1:-2], part=part_of(argv[-1]))
    if len(argv) in (3, 4) and argv[0] == "--check-report":
        return check_report(*argv[1:])
    if len(argv) == 2 and argv[0] == "--sample-make":
        return sample_make(argv[1])
    if len(argv) == 2 and argv[0] == "--sample-check":
        return sample_check(argv[1])
    if argv[:1] == ["--places"]:
        return places(argv[1:])
    if argv[:1] == ["--typecheck"]:
        return typecheck(argv[1:])
    ap = argparse.ArgumentParser()
    ap.add_argument("traces")
    ap.add_argument("work")
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("--twin", default=None, help="the twin's sources to mutate (default: formal/twin)")
    ap.add_argument("--all", action="store_true", help="every mutant on every record, not only where it can matter")
    ap.add_argument("--reuse", action="store_true", help="do not build again a mutant that WORKDIR holds, built, with its change")
    ap.add_argument("--hashes", default=None, help="write the sha256 of each mutant's replay, as built, to this file")
    ap.add_argument("--pairs", default=None, help="write a line per mutant and trace to this file: its count, reads not made, kinds")
    ap.add_argument("--part", default="1/1", help="K/N: the Kth of N parts of the mutants (every Nth, from the Kth)")
    ap.add_argument("--sample", choices=["drafts"], default=None,
                    help="drafts: of the part's mutants, the drafts' sample's alone (sample_drafts.txt); a draft's run, never a matrix")
    ap.add_argument("mutants", nargs="*")
    a = ap.parse_intermixed_args(argv)
    global REUSE
    REUSE = a.reuse
    if a.twin:
        global TWIN
        TWIN = Path(a.twin).resolve()
    traces = sorted(Path(a.traces).glob("*.jsonl.gz"))
    if not traces:                              # no trace is no matrix: "0 of 91 told" with rc 0 would read as a result
        raise SystemExit(f"{a.traces}: no trace (*.jsonl.gz) there")
    work = Path(a.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    content_file(work)
    names = part_names(a.mutants or list(MUTANTS), part_of(a.part))
    if a.sample:                                # a draft's run: the sample's mutants of the part, in its order
        s = sample_read()
        whole = len(names)
        names = [n for n in names if n in s]
        print(f"a draft's sample ({SAMPLE_FILE.name}): {len(names)} of the part's {whole} mutants; not a matrix")
    toy = layout.toy()
    for t in traces:                            # a trace kept from other tools or documents is refused before
        why = header3.check(toy, t)             #   anything runs
        if why:
            raise SystemExit(f"{t}: {'; '.join(why)}")
    place_check(names)
    with ThreadPoolExecutor(4) as ex:           # the builds first
        exes = dict(zip(names, ex.map(lambda n: build(work, n, *MUTANTS[n][1:]), names)))
        if a.hashes:
            def sha(n):
                h = hashlib.sha256()
                with open(exes[n], "rb") as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
                return f"{h.hexdigest()}  {n}\n"
            Path(a.hashes).write_text("".join(ex.map(sha, names)))
    pairs = [(n, t) for n in names for t in traces]
    with ThreadPoolExecutor(a.j) as ex:         # then every mutant over every trace, in one pool
        out = dict(zip(pairs, ex.map(lambda nt: replay(exes[nt[0]], nt[1], None if a.all else only(nt[0])), pairs)))
    if a.pairs:                                 # one line per pair: what a run here can make again for one trace
        Path(a.pairs).write_text("".join(
            f"{n} {t.name.split('.')[0]} {'no-verdict' if out[(n, t)][0] is None else out[(n, t)][0]} "
            f"{out[(n, t)][2]} {dict(sorted(out[(n, t)][3].items()))}\n" for n in names for t in traces))
    unseen = noverdict = byfoot = bycount = 0
    print(COUNTS)
    print("every mutant on every record" if a.all else
          "each mutant on the records that reached its function or touched its table: "
          + ", ".join(f"{n} {only(n)}" for n in names))
    for name in names:
        res = [(t.name.split(".")[0], *out[(name, t)]) for t in traces]
        hit = [(c, n, e) for c, n, e, _, _ in res if n]
        total = sum(n or 0 for _, n, _, _, _ in res)
        fewer = sum(f for _, _, _, f, _ in res)
        kinds = sum((k for _, _, _, _, k in res), Counter())
        only_foot = bool(hit) and set(kinds) <= {"reads", "writes"}
        byfoot += only_foot
        bycount += (not hit) and fewer > 0
        unseen += (not hit) and fewer == 0
        how = (f"{total} mismatched records in {len(hit)} of {len(res)} traces, by {dict(sorted(kinds.items()))}"
               if hit else "no record mismatches")
        print(f"{name}: {MUTANTS[name][0]}: {how}; {fewer} reads not made"
              + ("  <-- the notes alone" if only_foot else "")
              + ("  <-- the count of reads not made alone" if not hit and fewer else "")
              + ("  <-- no record tells it from the twin" if not hit and not fewer else ""))
        for c, n, e in hit[:2]:
            print(f"    {c} {n}: {e}")
        for c, n, e, _, _ in res:
            if n is None:                       # no report, or failed with no mismatch: the header's lines
                noverdict += 1
                print(f"    no verdict from {c}: {e or 'no report'}")
    print(f"{len(names) - unseen} of {len(names)} mutants told from the twin by these traces: "
          f"{len(names) - unseen - bycount} by a record that mismatches ({byfoot} of them by the notes alone: "
          f"return value, tape and state as the Python's), "
          f"{bycount} by the count of reads not made alone")
    if noverdict:                               # a replay that gave no verdict is a failed run, not a miss
        print(f"{noverdict} replays gave no verdict")
    return 1 if noverdict else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
