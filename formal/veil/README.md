# The claim wins (A1), in Veil

A model of one argument of the spec, `protocol.md` §4.5, proved for **any number of nodes, groups
and chunk indices** and every interleaving: an honest node is never penalised for asking a peer for
a chunk it has claimed to that peer. With §8.1's live window it holds with no assumption; under the
fallback for groups without a slot, it holds given the bound §8.1 sets on the tombstone's lifetime
(below). The Quint model next door (`../diffusion.qnt`, monitor `noPenalty`) checks the same
property on three or four nodes.

`ClaimWins.lean` holds the model, its inductive invariant, the queries that show it is not vacuous,
the known answers, model checks and an audit of the proof. Its header says what is modelled and what
is not: in short, claims (HAVE bits from `mine`), asks, the writer's filter, a link as one ordered
stream of RPCs that a coalescing transport can join, the receiver's IWANT-before-IDONTWANT, claims
that lapse, a group's expiry, its tombstone, the live window and the tombstone's end, and
connections that close; not the chunks themselves, the send window or timers (every lifetime can
end at any time), how a node tells a group's slot, and not the other two reasons for a penalty (a
chunk failing level 1, a malformed HAVE). The queue is a set, so the result holds for any order the
writer picks.

## What it rests on

§4.5's argument and §8.1's tombstone rule, each part a switch in the model (an `immutable` Boolean,
on in the spec), and the fallback's assumption, also a switch:

| switch | rule | where |
|---|---|---|
| `filterAsks` | the writer drops a queued ask for a chunk in `mine` (`held`), of a stop-pulled group or of an expired one | §7.2 |
| `asksFirst` | within one RPC, IWANT is handled before IDONTWANT | §4.1 |
| `inOrder` | one ordered writer per peer: RPCs are handled in the order written | §4.5, §7.2 |
| `expiryInFilter` | the writer's filter also checks expiry (v0.5) | §7.2 |
| `discardAtExpiry` | a group's expiry discards its queued IWANTs (v0.5) | §8.1 |
| `liveWindow` | a group whose slot has left the node's live window is expired, whatever its active lifetime, and its tombstone goes only then | §8.1 |
| `windowForward` | the live window only moves forward, and a group's slot is fixed: its key names it | §8.1, §1 |
| `claimsGoFirst` | the fallback, for groups without a slot, assumed: a node's tombstone for a group goes only once no claim of the group from it is queued, on a stream or held by a peer, as the bound on `TOMBSTONE_TTL` provides | §8.1 |

The invariant holds where `premises`: the first three rules, at least one of the two expiry rules,
and the tombstone rule: the live window, moving only forward, or, without a window, the assumption.

**The tombstone.** Past its active lifetime a node keeps only a group's key and slot, its tombstone
(§8.1). A node's claims of a group outlive the group's expiry: a HAVE still queued leaves after it,
and a peer keeps the claim for `HAVE_TTL`. A node that took the group up again could ask for a chunk
a peer still holds as its claim. v0.5 kept the tombstone "until the seen cache forgets its chunks",
which with the stock seen cache can be at expiry already, and nothing stopped the node from taking
the group up again. The live window closes this for good: a group whose slot has left the window
stays out, so the tombstone can go then, and the proof needs no bound on queues, the transport or
clocks, nor nodes that agree on the window: each node's own window must only move forward, and a
group's slot must be fixed, which its key does (§1): a bid of a later slot that commits the same
descriptor names another group. Without a slot, the fallback keeps the tombstone `TOMBSTONE_TTL` after the expiry; the model has no time,
so the proof assumes what that bound provides, that the tombstone outlives the claims. Two known
answers show what each part prevents. With neither the window nor the assumption an honest node is
penalised with every rule on: the asker's group expires and its tombstone goes while the peer still
holds its claim; the asker takes the group up again and asks. A window that moves back does the
same: the group's slot leaves the window and comes back, as it would for a group named by its group
id alone that a later slot's bid commits again.

## Results (2026-10-23, Veil at `02791b2`)

| check | how | result |
|---|---|---|
| the claim wins, any size | an inductive invariant of ten clauses (`#check_invariants`); 154 verification conditions (eleven for each of thirteen actions and at initialisation), each a theorem Lean's kernel checks (`#gen_theorems`), with the SMT solver's answers rebuilt as proofs, not trusted | **holds**: with the live window, with no assumption; under the fallback, given its bound |
| the audit | every verification condition, derived from the module itself, must be a theorem; no clause may be assumed instead of checked; every theorem the module adds must rest on Lean's own axioms only; any failure fails the build | 154 of 154; none assumed; all 537 theorems rest on `propext`, `Classical.choice` and `Quot.sound` |
| not vacuous | `sat trace`, every rule on: the spec as written (with the window) and the fallback can each hold; an ask queued before its chunk arrived is still queued when the claim reaches the peer; an ask and the claim of its chunk travel in one RPC; with the window, the tombstone gone while a peer still holds the node's claim of a chunk the node no longer has; under the fallback, a group taken up again after its tombstone went, with an ask on its way for a chunk the asker once claimed to that peer | all six found |
| known answers | `sat trace`, every other rule on, with the window: no filter; IDONTWANT first; RPCs out of order; neither expiry rule; neither the window nor the assumption, the tombstone gone while the peer holds the claim; a window that moves back | **a penalty in each** (7, 6, 7, 8, 9 and 9 steps), on two nodes and one chunk |
| a small instance, every state | `#model_check interpreted`: two nodes, one group of one chunk, two RPC positions per link (two RPCs per link over the whole run), every rule on, with the window and under the fallback | no clause violated: 127,504 states with the window, 88,000 under the fallback |

So the filter, IWANT first and in-order handling are each needed, and so is a tombstone rule; of
the two expiry rules v0.5 added (D′) either alone suffices, since the proof holds with one, and with
neither an honest node is penalised: the asker's group expires, `mine` goes with it, and an ask
queued before the chunk arrived passes the filter while the peer, whose group is still alive, holds
the claim. v0.4 had
neither rule (its filter checked `held` and stop-pull, and `discard_queued` ran only at
`drop_group`), so it could penalise an honest node that way. Its lifetimes do not prevent it: a HAVE
queued before the expiry still leaves after it (queued HAVEs survive expiry, in v0.5 too) and
refreshes the peer's claim, whatever `HAVE_TTL` is. It takes an ask that stays queued from before
its chunk arrived until the group expired, at least `GROUP_TTL`, with a HAVE of the chunk leaving
ahead of it.

## Running it

Veil is the 2.0 pre-release, pinned to a commit in `lakefile.lean`, and every dependency by commit
in `lake-manifest.json`; `lean-toolchain` names the Lean release. With
[elan](https://github.com/leanprover/elan) installed, and the system dependencies Veil's README
lists, from this directory:

```sh
lake build Veil      # once: Veil and its dependencies (about 4 minutes on 8 cores)
lake build           # the model: queries, model checks, proof, theorems, audit (about 1.5 minutes)
```

A clean `lake build` means every check passed: a clause that fails, a query without a trace, a
violation and a failed audit are errors. Packages and build outputs go to `.lake` (about 1.5 GB).
For larger instances `#model_check compiled` builds a native checker, which needs `clang`, `lld`,
`libc++-dev` and `libc++abi-dev`: on the window's instance above it finds the same 127,504 states
in about 80 seconds with its build.

## Veil 2.0, as met here

A pre-release: these cost time, and each has its workaround in the model.

- A relation binder names one variable: `(a : node) (b : node)`, not `(a b : node)` (the error
  says only "unable to extract type from binder").
- `sat trace` queries fail to translate (`cannot translate Type`, or a lambda SMT-LIB lacks) on a
  higher-order choice (`let s : (group → index → Bool) :| …`), on `decide $ …` over an update's
  quantified variables, and on a ghost relation read after such an update. `#check_invariants`
  handles all three. Hence one-part writes, Bool operators in updates, and conditions on the state
  before the updates.
- `set_option veil.smt.trust false` works at file level, not as `set_option … in #check_invariants`;
  `#check_invariants` alone adds no theorem, `#gen_theorems` does.
- The model checker's memory grows fast: two nodes with two chunks and three positions filled
  24 GB in 50 minutes interpreted, and in 4 minutes compiled (on an earlier version of the model).
- `lake env lean` on a loose file does not load cvc5; pass the plugins listed in
  `.lake/build/ir/ClaimWins.setup.json` (`--plugin=…`) to check one by hand.
