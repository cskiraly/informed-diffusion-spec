import SpecTwin.Sec42
import SpecTwin.Sec43
import SpecTwin.Sec44

/-! # The twin of protocol.md §4.1, "The order of handling", and §4.5, "An IWANT arrives" (v0.10.4, spec 34f60f8):
`on_frame` (lines 430–438), `respond` (lines 440–448) and `on_iwant` (lines 786–799)

`on_frame`'s branch for an IDONTWANT entry that is not a bitmap (lines 436–437, `else: unwanted[p].add(h)`) came
with v0.10.4. No cell handles such an entry: directed41's records do.

- **One record per frame:** `on_frame` calls the twin's own `on_chunk`, `on_ihave`, `on_iwant`, `on_have` and
  `respond`, so a frame's handling is one record with theirs in it.
- **`serve_count` is the twin's own table:** [peer, id] to a count. **`unwanted` is the twin's own too**
  (on_frame writes it): a peer to the set of ids it said it does not want, the ids as hex strings.
- **Questions:** `resolve(a)` and `chunk_of(mid)` (the node's store, §8's interface); `handle_graft_prune`
  (stock): the prunes, of which the toy's runs have none.
- **An ask key always has a group and an index here** (`Key`), so `group_index(a)` is never none: the tracer
  refuses an IWANT id that is neither a `WantIndex` nor a structured id of 56 bytes.
- **`answers` is a dict by id:** an id answered twice in one frame keeps its first place and takes the later
  chunk, as a Python dict does.
- **A node that runs something else as `on_iwant`** (a withholder) is asked, where the document's function
  would be called: `Ctx.replaced` names it, from the node's line of the trace.
- **respond's control** is `IWANT(asks) + PRUNE(prunes)`: two messages wherever there is an ask or a prune, the
  PRUNE empty where there is none. -/

namespace SpecTwin

open Node61 Tables

variable {m : Type → Type} [Monad m] [Tables m] [Node61 m]

/-- `on_iwant(p, iw)` (lines 786–799): the answers (§4.1) -/
def onIwant (p : Peer) (ids : List Key) : M m (List ChunkF) := do
  enter "on_iwant"
  let mut answers : List (Key × ChunkF) := []               -- by id: one answer per id per frame
  for a in ids do
    if ← expired a.group then                               -- past its active lifetime: ignored, no penalty
      branch "on_iwant: expired"
      continue
    if (← peerHas p a.group).has a.index then
      penalise p                                            -- it asks for a chunk it claimed: dropped
      branch "on_iwant: an ask of a chunk the asker claimed"
      continue
    match ← resolve a with                                  -- [c7] our id at that index: received or rebuilt
    | none =>
      branch "on_iwant: nothing to answer with"
      continue
    | some mid =>
      if (← unwantedOf p).contains mid.idHex then            -- `mid in unwanted[p]`
        branch "on_iwant: unwanted"
        continue
      let n := (← serveCount p mid) + 1                     -- `serve_count[p][mid] += 1`
      setServeCount p mid n
      if n > (← read).c.GOSSIP_RETRANSMISSION then          -- stock: 3 answers per id per peer
        branch "on_iwant: served too often"
        continue
      let f ← chunkOf mid                                   -- `answers[mid] = chunk_of(mid)`
      answers := if answers.any (·.1 == mid) then answers.map fun (k, v) => if k == mid then (k, f) else (k, v)
                 else answers ++ [(mid, f)]
      branch "on_iwant: answered"
  return answers.map (·.2)                                  -- [c14] one chunk per queue entry (§4.1)

/-- `respond(p, asks, answers, prunes)` (lines 440–448): one response per frame handled. `prunes`: how many. -/
def respond (p : Peer) (asks : List Key) (answers : List ChunkF) (prunes : Nat) : M m Unit := do
  enter "respond"
  -- `control = IWANT(asks) + PRUNE(prunes) if asks or prunes else None`: an empty part is left out by the queue
  let control : Option (List Ctl) := if !asks.isEmpty || prunes > 0 then some [.iwant asks, .prune] else none
  if answers.isEmpty then
    if control.isSome then
      let _ ← enqueue p (.entry { chunk := none, control, solicited := false }) false
      branch "respond: control alone"
    else branch "respond: nothing to ask, answer or prune"
    return
  let mut first := true
  for f in answers do                                       -- one chunk per entry; the control rides on the first
    let e : QEntry := { chunk := some f, control := if first then control else none, solicited := true }
    first := false
    if !(← enqueue p (.entry e) false) then                 -- refused by a full queue: owed, and queued once
      setOwedAnswers p f.g ((← owedAnswerBits p f.g).set f.i)    --   there is room (§7.2)
      branch "respond: an answer refused, owed"
  branch "respond: answers"

/-- `on_frame(p, frame)` (lines 430–438) -/
def onFrame (p : Peer) (fr : Frame) : M m Unit := do
  enter "on_frame"
  for f in fr.chunks do onChunk p f                         -- §4.2
  let asks ← onIhave p fr.ihave                             -- §4.4
  let answers ← if (← read).replaced.contains "on_iwant" then onIwantNode p fr.iwant    -- §4.5; or the node's own
                else onIwant p fr.iwant
  let prunes ← handleGraftPrune p                           -- stock
  for h in fr.idontwant do                                  -- §4.3: a HAVE bitmap (§2); any other entry is an
    match h with                                            --   opaque id, kept with stock's admission and
    | .bitmap g bits => onHave p g bits                     --   lifetime (§8.1)
    | .id a => setUnwanted p ((← unwantedOf p).insert a.idHex)      -- `unwanted[p].add(h)`
    | .other raw => setUnwanted p ((← unwantedOf p).insert raw)
  respond p asks answers prunes

end SpecTwin
