"""The first mutants of the twin: one rule of §6.1 changed in each, as a name, what it changes, and an exact
replacement in SpecTwin/Sec61.lean. mutants3.py takes this list (its MUTANTS) and says, mutant by mutant, which
of them stand as they are here and which it restates; it builds and replays them all. This file is the list alone.
"""

MUTANTS = {   # name -> (what it changes, old, new)
    "window-le": ("may_ask: an ask is in flight while now - t <= IWANT_WINDOW (for <)",
                  "if ctx.now - t < ctx.c.IWANT_WINDOW then", "if ctx.now - t ≤ ctx.c.IWANT_WINDOW then"),
    "untried-last": ("untried: the last untried candidate (for the first)",
                     "return cands.find? fun q => !tr.contains q", "return cands.reverse.find? fun q => !tr.contains q"),
    "lrt-last": ("least_recently_tried: the last of the least (for the first)",
                 "| some (_, bt) => if t < bt then best := some (q, t)",
                 "| some (_, bt) => if t ≤ bt then best := some (q, t)"),
    "backoff-x2": ("last_resort: PROMISE * 2^(n+1) (for 2^n)",
                   "after (ctx.c.PROMISE * (2 ^ done.size).toFloat) (.askParked a)",
                   "after (ctx.c.PROMISE * (2 ^ (done.size + 1)).toFloat) (.askParked a)"),
    "offers-15": ("add_offer: at most 15 announcers in a list (for 16)",
                  "if !o.contains p && o.length < 16 then", "if !o.contains p && o.length < 15 then"),
    "park-longer": ("promise_due: parks for PARK_TTL + 1 s",
                    "(ctx.now + ctx.c.PARK_TTL)", "(ctx.now + ctx.c.PARK_TTL + 1.0)"),
    "outstanding-no-queue": ("outstanding: promises only, the queue unread",
                             "let r := (← queuedAsks q).any (fun b => b.chunk == k)", "let r := false"),
    "announcers-peers-first": ("announcers: the other offerers before the list",
                               "return o ++ (← ownOrder rest a)", "return (← ownOrder rest a) ++ o"),
    "retry-expired-first": ("retry_offer: expired asked before stop_pull is read",
                            '  if (← stopPull a.group) then branch "retry_offer: stop-pull"; return\n'
                            '  if (← expired a.group) then branch "retry_offer: expired"; return\n',
                            '  if (← expired a.group) then branch "retry_offer: expired"; return\n'
                            '  if (← stopPull a.group) then branch "retry_offer: stop-pull"; return\n'),
    "parked-le": ("parked: now <= the park's end (for <)",
                  "return (← read).now < t", "return (← read).now ≤ t"),
    "last-resort-rearms": ("last_resort: no check that its timer is armed already",
                           '  if (← get).lastResortArmed.contains k then\n    branch "last_resort: armed already"\n    return\n',
                           ""),
    "ask-parked-counts-all": ("ask_parked: counts the ask whether or not its peer is parked",
                              "if (← parked pick a) then                             -- counted once",
                              "if true then                             -- counted once"),
    # what the records' negative examples and exceptions must catch
    "outstanding-group-only": ("outstanding: a promise of any chunk of the group counts",
                               "fun ((b, r), _) => r == q && b.chunk == k", "fun ((b, r), _) => r == q && b.group == k.1"),
    "no-overflow": ("last_resort: no exception past 1,023 counted asks (a timer at infinity)",
                    '  if done.size ≥ 1024 then                                  -- 2 ** n does not convert to a double: Python\n'
                    '    crash "OverflowError: int too large to convert to float (last_resort)"   --   raises, k already armed\n',
                    ""),
    "overflow-before-arming": ("last_resort: raises before arming k (the Python arms, then raises)",
                               "  modify fun s => { s with lastResortArmed := s.lastResortArmed.insert k }\n"
                               "  if done.size ≥ 1024 then                                  -- 2 ** n does not convert to a double: Python\n"
                               "    crash \"OverflowError: int too large to convert to float (last_resort)\"   --   raises, k already armed\n",
                               "  if done.size ≥ 1024 then                                  -- 2 ** n does not convert to a double: Python\n"
                               "    crash \"OverflowError: int too large to convert to float (last_resort)\"   --   raises, k already armed\n"
                               "  modify fun s => { s with lastResortArmed := s.lastResortArmed.insert k }\n"),
    "overflow-at-1023": ("last_resort: raises at 1,023 counted asks already (for 1,024)",
                         "  if done.size ≥ 1024 then", "  if done.size ≥ 1023 then"),
    "lrt-skips-untried": ("least_recently_tried: an untried candidate is passed over (for a KeyError)",
                          'let some t := tr.get? q | crash s!"KeyError: {q} (least_recently_tried: tried[a][q])"',
                          "let some t := tr.get? q | continue"),
    # twins that read more widely than the Python, the -inf defaults, and where a KeyError is raised
    "parked-any-group": ("parked: the latest park of p in any group (for a's group's)",
                         "let t := ((← get).park.getD p {}).getD a.group negInf",
                         "let t := ((← get).park.getD p {}).fold (fun m _ t => if t > m then t else m) negInf"),
    "park-default-zero": ("parked: a missing park reads as 0.0 (for -inf)",
                          "let t := ((← get).park.getD p {}).getD a.group negInf",
                          "let t := ((← get).park.getD p {}).getD a.group 0.0"),
    "announcers-any-group": ("announcers: a peer that offered a's index in any group",
                             "((s.offered.getD q {}).getD a.group 0).has a.index",
                             "(s.offered.getD q {}).fold (fun b _ x => b || Bits.has x a.index) false"),
    "outstanding-queued-any-group": ("outstanding: a queued ask of a's index in any group",
                                     "let r := (← queuedAsks q).any (fun b => b.chunk == k)",
                                     "let r := (← queuedAsks q).any (fun b => b.chunk.2 == k.2)"),
    "window-per-chunk": ("may_ask: in flight if any key of a's chunk was asked inside the window (for a's own key)",
                         "  if let some t := (← get).askedAt.get? a then\n"
                         "    if ctx.now - t < ctx.c.IWANT_WINDOW then                 -- 200 ms: an ask is in flight\n",
                         "  if true then\n"
                         "    if (← get).askedAt.toList.any (fun (b, t) => b.chunk == a.chunk && ctx.now - t < ctx.c.IWANT_WINDOW) then\n"),
    "untried-per-chunk": ("untried: tried under any key of a's chunk (for a's own)",
                          "  let tr := (← get).tried.getD a {}\n  return cands.find? fun q => !tr.contains q",
                          "  let s ← get\n  return cands.find? fun q => !(s.tried.toList.any fun (b, m) => b.chunk == a.chunk && m.contains q)"),
    "retry-window-default-zero": ("retry_offer: a missing asked_at reads as 0.0 (for -inf)",
                                  'if ctx.now - (← get).askedAt.getD a negInf < ctx.c.IWANT_WINDOW then\n    branch "retry_offer: in flight"',
                                  'if ctx.now - (← get).askedAt.getD a 0.0 < ctx.c.IWANT_WINDOW then\n    branch "retry_offer: in flight"'),
    "ask-parked-window-default-zero": ("ask_parked: a missing asked_at reads as 0.0 (for -inf)",
                                       "if ctx.now - (← get).askedAt.getD a negInf < ctx.c.IWANT_WINDOW then   -- someone was asked meanwhile",
                                       "if ctx.now - (← get).askedAt.getD a 0.0 < ctx.c.IWANT_WINDOW then   -- someone was asked meanwhile"),
    "lrt-keyerror-last": ("least_recently_tried: the KeyError names the last untried candidate (for the first)",
                          'let some t := tr.get? q | crash s!"KeyError: {q} (least_recently_tried: tried[a][q])"',
                          'let some t := tr.get? q | crash s!"KeyError: {(cands.filter (!tr.contains ·)).getLast!} (least_recently_tried: tried[a][q])"'),
    # the retry's and the last resort's own window lines; reads the nine above leave out (asked_parked and
    # last_resort_armed of another chunk, the list under the chunk's other form); and what only a whole-state
    # record shows (a read of another group's armed set or of another chunk's window, and a deletion outside
    # the call's neighbourhood)
    "retry-window-le": ("retry_offer: in flight while now - asked_at <= IWANT_WINDOW (for <)",
                        'if ctx.now - (← get).askedAt.getD a negInf < ctx.c.IWANT_WINDOW then\n    branch "retry_offer: in flight"',
                        'if ctx.now - (← get).askedAt.getD a negInf ≤ ctx.c.IWANT_WINDOW then\n    branch "retry_offer: in flight"'),
    "ask-parked-window-le": ("ask_parked: in flight while now - asked_at <= IWANT_WINDOW (for <)",
                             "if ctx.now - (← get).askedAt.getD a negInf < ctx.c.IWANT_WINDOW then   -- someone was asked meanwhile",
                             "if ctx.now - (← get).askedAt.getD a negInf ≤ ctx.c.IWANT_WINDOW then   -- someone was asked meanwhile"),
    "last-resort-done-per-group": ("last_resort: counts the asks of every chunk of the group (for a's chunk's)",
                                   "  let done := (← get).askedParked.getD k {}\n  let untied ←",
                                   "  let done := (← get).askedParked.fold (fun acc c ps => if c.1 == k.1 then ps.fold (fun acc q => acc.insert q) acc else acc) ({} : Std.HashSet Peer)\n  let untied ←"),
    "last-resort-armed-any-chunk": ("last_resort: armed already if any chunk of the group is armed (for a's chunk)",
                                    'if (← get).lastResortArmed.contains k then\n    branch "last_resort: armed already"',
                                    'if (← get).lastResortArmed.toList.any (·.1 == k.1) then\n    branch "last_resort: armed already"'),
    "announcers-list-any-form": ("announcers: a's own offer list, then the lists under the chunk's other keys (for a's own alone)",
                                 "let o := s.offers.getD a []\n  let peers ← connectedTopicPeers",
                                 "let o := s.offers.getD a [] ++ (s.offers.toList.filter fun (b, _) => b.chunk == a.chunk && b != a).flatMap (·.2)\n  let peers ← connectedTopicPeers"),
    "last-resort-armed-any-group": ("last_resort: armed already if a's index is armed in any group (for a's group)",
                                    'if (← get).lastResortArmed.contains k then\n    branch "last_resort: armed already"',
                                    'if (← get).lastResortArmed.toList.any (·.2 == k.2) then\n    branch "last_resort: armed already"'),
    "window-per-group": ("may_ask: in flight if any key of a's group was asked inside the window (for a's own key)",
                         "  if let some t := (← get).askedAt.get? a then\n"
                         "    if ctx.now - t < ctx.c.IWANT_WINDOW then                 -- 200 ms: an ask is in flight\n",
                         "  if true then\n"
                         "    if (← get).askedAt.toList.any (fun (b, t) => b.group == a.group && ctx.now - t < ctx.c.IWANT_WINDOW) then\n"),
    # with §6.1's own order of the announcers beyond the list (the draft of 2026-11-14)
    "own-order-unasked": ("announcers: the others in connection order, the node's own order not asked",
                          "return o ++ (← ownOrder rest a)", "return o ++ rest"),
    "own-order-of-all": ("announcers: the node's own order asked of every announcer, the list's too",
                         "return o ++ (← ownOrder rest a)", "return (← ownOrder (o ++ rest) a)"),
    "own-order-reversed": ("announcers: the node's own order taken backwards",
                           "return o ++ (← ownOrder rest a)", "return o ++ (← ownOrder rest a).reverse"),
    "may-ask-erases-group": ("may_ask: also erases asked_at under the group's other chunks (a deletion outside the call's keys)",
                             "    askedAt := s.askedAt.insert a ctx.now\n",
                             "    askedAt := (s.askedAt.filter fun b _ => b.chunk == a.chunk || b.group != a.group).insert a ctx.now\n"),
}
