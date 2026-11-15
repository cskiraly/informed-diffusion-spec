# informed-diffusion-spec

**SEACAST** (Segmented, Encoded, Availability-sampled broadCAST), a broadcast protocol for
Ethereum's large objects, written as Python-like pseudocode in the style of the consensus specs,
with a toy simulator that runs it. Up to v0.5 it was published as *Informed Diffusion*, a design of
segmented payload diffusion studied for [EIP-8411](https://eips.ethereum.org/EIPS/eip-8411) (Fast
Execution Payload Broadcast); Informed Diffusion now names how SEACAST diffuses, and `protocol.md`
keeps its title.

- [`protocol.md`](protocol.md): what a node does, one event at a time. The builder cuts the
  payload into chunks that its bid commits to (from tier 3 it compresses the payload first and adds
  parity chunks), and the chunks spread by push and pull, which tier 4 guides with HAVE bitmaps. The
  document covers every tier; the wire is specified to the field, and byte-exact layouts follow
  later.
- [`protocol-v2.md`](protocol-v2.md): **a draft** of SEACAST's next version (its decisions taken, in
  its §8; checked in the toy only; no client runs it, and the research harness's simulations ran
  only designs it contains as settings; not model-checked), the protocol on its own notions: object
  types, interest and duty, push and announce relations per family and colour, one HAVE and one WANT
  per link and group, claims, repair as one rule with parameters. It contains `protocol.md` as one
  setting (but for a source with no mesh peer, its §6.1) and variant C, PeerDAS custody, RowDAS rows
  and FullDAS sampling as others; its decisions are marked `[D1]` to `[D12]`. The toy runs it on top
  of `protocol.md` (`toy/run.py --doc v2 --setting t4|c|custody|rows`, `toy/check.py --doc v2`
  against its own `golden-v2.txt`): under its tier 4 setting it stays within 13 ms at the median and
  18 ms at the tail of `protocol.md`'s check cells (one seed each, a toy check; `check.py --doc v2
  --golden golden.txt`; its §6.1 says what the distance is); variant C, PeerDAS custody, FullDAS
  sampling and RowDAS rows run as settings, with the invariants of every setting checked on each run
  (`toy/invariants.py`), cross-fill and the claim's deferral included. Executing the settings found
  a stall in v0.3's window (fixed in `protocol.md` §7.1, the cells re-recorded), that card 12's
  projection assumes a code (its §4.9), that the window's slot unit throttles small chunks (its
  §4.11: the window in bytes), that a proposer of many groups must send its own chunks before its
  offers and answers (its §4.12, where answering before pushing is an option that was a wash in
  three-seed toy checks), that a row member needs a custodian link for every column, to gather its
  row and to repair the columns (its §4.6: the repair floor, which EIP-8371's fanout presumes), and
  that a rebuilt cell must complete the groups it fills (its §4.6).
- [`toy/`](toy/): runs every `python` block of `protocol.md`, once per node, on a simulated
  network. It shows that the document is complete enough to run, and is a place to try a rule
  before implementing it. Its numbers are not measurements.
- [`formal/`](formal/): a model of §4–§7, checked on small instances: what holds, what v0.5 fixed.
- [`formal/veil/`](formal/veil/): properties proved in Veil for any number of nodes, groups and chunks: A1, an honest node never penalised, for an ask (with no assumption under the live window, `protocol.md` §8.1, a group's key fixing its slot, §1, and under the fallback for groups without a slot given the bound on its tombstone), for a chunk that fails level 1 or for a malformed HAVE; and no stall (Q1): no quiet state in which an honest node reachable from the source along mesh links is incomplete, under the assumptions its README states, with the mesh changing and connections closing (§5.4 closes F9 for them), whose proof found the IHAVE gap that v0.7 closes (§4.4); and under equivocation, with §4.2's ties and §6.1's rule against a second ask of a peer at once, which close F6, for the nodes the source reaches through nodes that installed the builder's block (`NoStallEquiv.lean`).

## Where SEACAST stands

- **The latest release is [v0.10](https://github.com/cskiraly/informed-diffusion-spec/tree/v0.10)**, 2026-11-15:
  `protocol.md` at version 0.10, the toy and its recorded cells, the next version's draft with its
  decisions taken, and the proofs in `formal/veil/`, which are of v0.8's rules.
  [`CHANGELOG.md`](CHANGELOG.md) says what each release changed; changes after the latest tag are on
  `main`, and the changelog's first entry names them.
- **Each measurement says which code it ran.** The SEACAST post's figures ran on a research
  implementation; `protocol.md` §9 lists where it does as this text does and where it does not, and
  each results record names its code.
- **SEACAST's next version is a draft**, `protocol-v2.md` (above), checked in the toy only.
- **Results.** The announcement post, *[SEACAST: fast, lean broadcast for Ethereum, with an executable
  spec and a formal model](https://ethresear.ch/t/seacast-fast-lean-broadcast-for-ethereum-with-an-executable-spec-and-a-formal-model/26167)*
  (2026), stays as published; its text is kept current, with the latest results and the data and scripts
  behind them, in [eth-networking-studies](https://github.com/cskiraly/eth-networking-studies/tree/main/seacast), and news is posted as replies to the post.

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
