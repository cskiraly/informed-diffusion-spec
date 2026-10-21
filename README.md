# informed-diffusion-spec

Informed Diffusion, a design of segmented payload diffusion studied for
[EIP-8411](https://eips.ethereum.org/EIPS/eip-8411) (Fast Execution Payload Broadcast), written as
Python-like pseudocode in the style of the consensus specs, with a toy simulator that runs it.

- [`protocol.md`](protocol.md): what a node does, one event at a time. The builder cuts the
  payload into chunks that its bid commits to (from tier 3 it compresses the payload first and adds
  parity chunks), and the chunks spread by push and pull, which tier 4 guides with HAVE bitmaps. The
  document covers every tier; the wire is specified to the field, and byte-exact layouts follow
  later.
- [`toy/`](toy/): runs every `python` block of `protocol.md`, once per node, on a simulated
  network. It shows that the document is complete enough to run, and is a place to try a rule
  before implementing it. Its numbers are not measurements.
- [`formal/`](formal/): a model of §4–§7, checked on small instances: what holds, what v0.5 fixed.

**Status:** draft v0.5, 2026-10-21. Since v0.4, fixes from a model check of v0.4: a push to a
mesh peer that does not happen is offered to it instead, and an offer or answer a full queue
refuses is owed (§5.2, §7.2, §4.1); every offer is kept, per connection and group, and when every
announcer of a chunk is parked, each is asked once more, at a wait that doubles (§6.1, §8.2); no
ask before the block is installed, and what was offered meanwhile is asked for then (§3, §4.4,
§4.2); expiry is checked by the retry, the writer's ask filter and a decode that returns, and a
group's pull state goes at its expiry (§6.1, §7.2, §4.6, §8.1); a promise starts when the ask is
written and closes with its connection (§7.2, §6.1); and a copy the deferred store refuses counts
as its sender's offer (§4.2). §8's state, limits and constants follow, and §9 lists these rules
among those the measured implementation predates. The toy runs the text as written, so its
recorded results moved.

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
