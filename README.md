# seacast-spec

**SEACAST** (Segmented, Encoded, Availability-sampled broadCAST) is a broadcast protocol for
Ethereum's large objects, written as Python-like pseudocode in the style of the consensus specs,
with a toy simulator that runs it. Up to v0.5 it was published as *Informed Diffusion*, a design of
segmented payload diffusion studied for [EIP-8411](https://eips.ethereum.org/EIPS/eip-8411) (Fast
Execution Payload Broadcast). *Informed Diffusion*, the title of `protocol.md` until v0.10.3, now
names how SEACAST diffuses.

- [`protocol.md`](protocol.md): what a node does, one event at a time. The builder cuts the payload
  into chunks that its bid commits to (from tier 3 it compresses the payload first and adds parity
  chunks), and the chunks spread by push and pull, which tier 4 guides with HAVE bitmaps. The
  document covers every tier. The wire is specified to the field; byte-exact layouts follow later.
  Its §0 says how to read it.
- [`protocol-v2.md`](protocol-v2.md): **a draft** of SEACAST's next version, the protocol on its own
  notions: object types, interest and duty, push and announce relations per family and colour, one
  HAVE and one WANT per link and group, claims, and repair as one rule with parameters. It contains
  `protocol.md` as one setting (but for a source with no mesh peer, its §6.1), and variant C,
  PeerDAS custody, RowDAS rows and FullDAS sampling as others. Its decisions are taken and marked
  `[D1]` to `[D12]` (its §8). It is checked in the toy only: no client runs it, the research
  harness's simulations ran only designs it contains as settings, and it is not model-checked. The
  toy runs it on top of `protocol.md` (`toy/run.py --doc v2 --setting t4|c|custody|rows`,
  `toy/check.py --doc v2` against its own `golden-v2.txt`), with the invariants of every setting
  checked on each run (`toy/invariants.py`), cross-fill and the claim's deferral included. Its §6.1
  says how far its tier 4 setting is from `protocol.md` (`toy/check.py --doc v2 --golden
  golden.txt` compares the two). Running the settings found what the texts now address: a stall
  in v0.3's window (fixed in `protocol.md` §7.1), that card 12's projection assumes a code
  (its §4.9), that the window's slot unit throttles small chunks (its §4.11: the window in bytes),
  that a proposer of many groups must send its own chunks before its offers and answers (its
  §4.12), that a row member needs a custodian link for every column, to gather its row and to
  repair the columns (its §4.6: the repair floor, which EIP-8371's fanout presumes), and that a
  rebuilt cell must complete the groups it fills (its §4.6).
- [`protocol-v2-bindings.md`](protocol-v2-bindings.md): the next version's bindings, a companion of
  `protocol-v2.md`, whose §7 says what every binding provides. The standalone binding, SEACAST's own
  protocol (`/seacast/2.0.0`), is defined to the byte, on a stream of its own or in Waggle's framing.
  The bindings onto gossipsub's wires, with the Partial Messages Extension and v0.3's, are defined to
  the field.
- [`toy/`](toy/): runs every `python` block of `protocol.md`, once per node, on a simulated
  network. It shows that the document is complete enough to run, and is a place to try a rule
  before implementing it. Its numbers are not measurements.
- [`formal/`](formal/): the checks of `protocol.md` beyond the toy, and the map of how they fit
  together. Beside the proofs and the twin below: a Quint model of §4–§7 at v0.5's rules, checked on
  small instances by TLC and random simulation; monitors of five of its safety properties on the
  toy; and a check of §1–§2's arithmetic over every compressed length of a coded group and the
  extremes of each plain one.
- [`formal/veil/`](formal/veil/): properties of v0.8's rules, proved in Veil for any number of
  nodes, groups and chunks:
  - A1, an honest node is never penalised: for an ask, for a chunk that fails level 1, or for a
    malformed HAVE. For an ask, it needs no assumption under the live window (`protocol.md` §8.1,
    with a group's key fixing its slot, §1), and, for groups without a slot, the bound on the
    tombstone;
  - no stall (Q1): no quiet state in which an honest node reachable from the source along mesh
    links is incomplete, under the assumptions its README states, with the mesh changing and
    connections closing;
  - Q1 under equivocation, with §4.2's ties and §6.1's rule against a second ask of a peer at once,
    for the nodes the source reaches through nodes that installed the builder's block
    (`NoStallEquiv.lean`);
  - Q1 with malicious peers, for the honest nodes the source reaches through honest nodes that
    installed the block, relabelled copies excluded; and a run in which an announcer that is never
    parked holds the last resort off, which `protocol.md` §6.1 leaves open;
  - a run goes quiet (Q3): with finitely many nodes and weak fairness, once the environment stops
    (with malicious peers, their actions included), the transport and v0.8's asking (with
    `NO_REASK_OPEN`) eventually have nothing left to do, for good (with malicious peers, the honest
    nodes' machinery);
  - agreement and integrity: level 2 is all or none, a check that succeeds recovers the bytes the
    root commits, and two honest nodes never deliver different payloads for a group, under the
    codec's assumptions its README lists, an MDS code and a binding hash among them.

  The models do not have the rules `protocol.md` changed since v0.8; their README lists them.
- [`formal/twin/`](formal/twin/): a transcription of `protocol.md`'s Python into Lean, function by
  function, executable, checked against the toy by trace replay. `check.sh`, which builds the twin,
  replays small traces of the toy through it and runs controls that must fail, passes at this
  commit. The twin's record is in `formal/twin/record/`: every cell of the toy traced under both
  documents, the hand runs and the directed sets, each trace replayed through the twin, and the
  matrix of the mutants, which shows which mutants part of those traces tell from the twin. Its
  [`RECORD.md`](formal/twin/record/RECORD.md) says what the record shows and what it does not.
- [`formal/refine/`](formal/refine/): a first piece of a refinement from the twin to a Veil model,
  on the asking path of §6.1, with the narrow scope its README states. It is not a proof that the
  twin satisfies the model's properties.

## Where SEACAST stands

- **The latest release is [v0.10.7](https://github.com/cskiraly/seacast-spec/tree/v0.10.7)**, 2026-11-20:
  `protocol.md` at version 0.10.7, v0.10's rules with the text rewritten for readers, its constants
  in three kinds, reference values for gossipsub's two IHAVE limits, the source's choice of when it
  announces (`SOURCE_OFFERS`), an IDONTWANT's stock ids kept as stock gossipsub keeps them, an open
  question on a coded group's compressed bytes, and a window whose line a writer that cannot write
  no longer holds; the toy and its recorded cells, the next version's draft, rewritten for readers,
  with its decisions taken and its bindings in a document of their own, the proofs in `formal/veil/`
  on Veil's release, with malicious peers, runs that go quiet (Q3) and agreement, which are of
  v0.8's rules, and the Lean twin of `protocol.md`'s Python, a draft, with a map of how the checks
  fit together.
  [`CHANGELOG.md`](CHANGELOG.md) says what each release changed; changes after the latest tag are on
  `main`, and the changelog's first entry names them.
- **Each measurement says which code it ran.** The SEACAST post's figures ran on a research
  implementation; `protocol.md` §9 lists where it does as this text does and where it does not, and
  each results record names its code.
- **SEACAST's next version is a draft**, `protocol-v2.md` (above), checked in the toy only.
- **What the checks show.** How the toy, the Quint model, the Veil proofs and the Lean twin fit
  together, and what each shows at this commit:
  [`formal/README.md`](formal/README.md#how-the-checks-fit-together).
- **Results.** The announcement post, *[SEACAST: fast, lean broadcast for Ethereum, with an executable
  spec and a formal model](https://ethresear.ch/t/seacast-fast-lean-broadcast-for-ethereum-with-an-executable-spec-and-a-formal-model/26167)*
  (2026), stays as published. Its text is kept current, with the latest results and the data and
  scripts behind them, in [eth-networking-studies](https://github.com/cskiraly/eth-networking-studies/tree/main/seacast),
  and news is posted as replies to the post.

## Running it

```
cd toy
python3 run.py --nodes 100 --msgs 4    # tier 4, 100 nodes on 50/100 Mbps links, four payloads
python3 check.py                       # the document still runs as recorded
```

Python 3 and its standard library (tested with 3.12). [`toy/README.md`](toy/README.md) describes
the options, the network model and what the toy adds to the document.

## Related

- [Wen fast payload broadcast? Segment, code, push, pull, and everything in between](https://ethresear.ch/t/wen-fast-payload-broadcast-segment-code-push-pull-and-everything-in-between/25913)
  (2026): the design space and the commitment;
- [EIP-8411: what segmented payload diffusion is made of](https://ethresear.ch/t/eip-8411-what-segmented-payload-diffusion-is-made-of/26025)
  (2026): tiers 1 to 3;
- [*Informed Diffusion: making home builders publish fast*](https://ethresear.ch/t/informed-diffusion-making-home-builders-publish-fast/26151) (2026): tier 4 and its
  measurements;
- [Segmented payload diffusion, card by card](https://notes.ethereum.org/@cskiraly/segmented-stack-cards)
  (2026): each mechanism in prose, what it costs and when it matters;
- [Who decides that a payload is revealed?](https://notes.ethereum.org/@cskiraly/eip-8411-envelope-signature)
  (2026): how the envelope's signature travels;
- [*What a forwarding node checks, and when it decodes*](https://notes.ethereum.org/@cskiraly/informed-diffusion-decoding) (2026): the validation levels, the decode claim
  and repair.

## License

[CC0 1.0](LICENSE): public domain, like the EIPs and the consensus specs.
