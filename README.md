# segmented-broadcast-spec

Segmented payload diffusion, the design studied for
[EIP-8411](https://eips.ethereum.org/EIPS/eip-8411) (Fast Execution Payload Broadcast), written as
Python-like pseudocode in the style of the consensus specs, with a toy simulator that runs it.

- [`protocol.md`](protocol.md): what a node does, one event at a time. The builder cuts the
  payload into frames that its bid commits to (from tier 3 it compresses the payload first and adds
  parity frames), and the frames spread by push and pull, which tier 4 guides with HAVE bitmaps. The
  document covers every tier; the wire is specified to the field, and byte-exact layouts follow
  later.
- [`toy/`](toy/): runs every `python` block of `protocol.md`, once per node, on a simulated
  network. It shows that the document is complete enough to run, and is a place to try a rule
  before implementing it. Its numbers are not measurements.

**Status:** draft v0.3, 2026-10-05. Since v0.2, a node that has decoded a group pushes the frames
it rebuilt to the mesh peers that still lack enough frames to decode (§4.6), instead of holding
them.

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
- *EIP-8411 tier 4: informed diffusion at a 50 Mbps floor* (forthcoming): tier 4 and its
  measurements;
- [Segmented payload diffusion, card by card](https://notes.ethereum.org/@cskiraly/segmented-stack-cards)
  (2026): each mechanism in prose, what it costs and when it matters;
- [Who decides that a payload is revealed?](https://notes.ethereum.org/@cskiraly/eip-8411-envelope-signature)
  (2026): how the envelope's signature travels;
- *What a relay checks, and when it decodes* (forthcoming): the validation levels, the decode claim
  and repair.

## License

[CC0 1.0](LICENSE): public domain, like the EIPs and the consensus specs.
