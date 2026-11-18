import Lean

/-! # Agreement and integrity: level 2 is all or none (L3), in plain Lean

SEACAST, `protocol.md` v0.8, §1 (the descriptor and its commitment), §3 (levels 1 and 2) and §4.6
(decode, the decode claim, repair). A node that has K chunks of a group, each passing level 1 (its
Merkle proof against the descriptor's root), decodes them, re-encodes the recovered segmented byte
string into the N leaves, and compares their Merkle root with the descriptor's (level 2); it
delivers the payload decompressed from those bytes, or drops the group. Whatever the builder
committed, a consistent code or not:

- **all or none** (`level2_all_or_none`, L3): any two level-2 checks of a group, each from any K
  distinct positions whose chunks passed level 1, succeed or fail together;
- **integrity** (`integrity`): a check that succeeds recovers the one byte string whose encoding the
  root commits;
- **agreement** (`agreement`, `agreement_by_key`): so two honest nodes never deliver different
  payloads for a group, the payload being a function of those bytes, and a group's key naming one
  descriptor (its group id is the descriptor's hash, `group_key(group_id(d), slot)`);
- **the decode claim** (`claim_sound`, `claim_wrong_only_dropped`): the claim of all N chunks that a
  node sends at K, before level 2, is true of a group whose check succeeds (each claimed chunk is
  the recovered encoding's leaf, which passes level 1), and wrong only of a group every node that
  reaches K drops.

The coding layer is abstract, one `Codec` per valid descriptor d (`valid_descriptor`, K(d), N(d)):
the descriptor's segmented byte strings, their encoding into N leaves (segmentation into K data
chunks of `segment_length`, the last one short and padded for coding, then Reed–Solomon parity; no
parity for a plain group, N = K), a decoder from given positions, the Merkle root and the proof
check. Each theorem takes the hypotheses it uses: the decoder reads only the positions it is given
(`Local`) and recovers the bytes from any K positions of an encoding (`MDS`); a proof binds a
position to one leaf (`Binding`), and every leaf of a committed vector has one (`Complete`). That a
Reed–Solomon code over the spec's field is MDS is assumed here, not proved (Mathlib's interpolation
would prove it, in a project of its own); `Binding` is the hash's collision resistance, taken as
exact; it also covers level 1's length check (a leaf that passes under a root whose check succeeds
is the encoding's, of the length its index has). Known answers: without `Binding` two checks succeed
with different bytes (`binding_needed`), and with a code that is not MDS one succeeds and one fails
(`mds_needed`), the other hypotheses holding in each; and an instance meets all four
(`plainOne_meets_all`). The converse of L3's "none" (`honest_succeeds`): a root that commits an
encoding passes at every node, the honest builder's case. Not covered: a group that expires while it
decodes (the spec then stores and delivers nothing), and whether a check is ever made (a node below
K neither decodes nor drops). -/

namespace Agreement

/-- how many of the N positions `S` names -/
def count {N : Nat} (S : Fin N → Bool) : Nat := (List.finRange N).countP S

/-- the coding layer of one valid descriptor (§1) -/
structure Codec (N K : Nat) where
  /-- the segmented byte strings the descriptor describes: the payload, compressed -/
  Bytes : Type
  /-- a chunk's data, `segment_length` bytes for its index (the last data chunk short) -/
  Leaf : Type
  Root : Type
  Proof : Type
  /-- segmentation into K data chunks, then the parity (none for a plain group) -/
  encode : Bytes → Fin N → Leaf
  /-- decoding from the leaves at positions `S`; padding the short last chunk for the decoder and
  truncating it after are its own -/
  decode : (Fin N → Bool) → (Fin N → Leaf) → Bytes
  /-- the Merkle root over the N leaves -/
  commit : (Fin N → Leaf) → Root
  /-- the Merkle proof check -/
  verify : Root → Fin N → Leaf → Proof → Bool

variable {N K : Nat}

/-- level 1 (§3): `x` passes as the leaf at position `i` under root `r` -/
def passes (C : Codec N K) (r : C.Root) (i : Fin N) (x : C.Leaf) : Prop :=
  ∃ π, C.verify r i x π = true

/-- what a node decodes from (§4.6): at least K distinct positions, each leaf passing level 1 under
the descriptor's root `r`; any K of a node's chunks, the first K received or others -/
structure Collected (C : Codec N K) (r : C.Root) where
  S : Fin N → Bool
  leaf : Fin N → C.Leaf
  enough : K ≤ count S
  valid : ∀ i, S i = true → passes C r i (leaf i)

/-- the bytes a node's decode recovers -/
def recovered {C : Codec N K} {r : C.Root} (c : Collected C r) : C.Bytes :=
  C.decode c.S c.leaf

/-- level 2 (§3, §4.6): the recovered bytes' encoding has the descriptor's root -/
def level2 {C : Codec N K} {r : C.Root} (c : Collected C r) : Prop :=
  C.commit (C.encode (recovered c)) = r

/-- the decoder reads only the positions it is given (where they are at least K) -/
def Local (C : Codec N K) : Prop :=
  ∀ S l l', K ≤ count S → (∀ i, S i = true → l i = l' i) → C.decode S l = C.decode S l'

/-- MDS: from any K positions of an encoding the decoder recovers its bytes -/
def MDS (C : Codec N K) : Prop := ∀ S b, K ≤ count S → C.decode S (C.encode b) = b

/-- position binding: at most one leaf passes at a position under a root -/
def Binding (C : Codec N K) : Prop :=
  ∀ r i x y π π', C.verify r i x π = true → C.verify r i y π' = true → x = y

/-- completeness: each leaf of a committed vector passes under its root -/
def Complete (C : Codec N K) : Prop := ∀ l i, ∃ π, C.verify (C.commit l) i (l i) π = true

/-- once a check of root `r` succeeds, every leaf that passes level 1 under `r` is the recovered
encoding's -/
theorem leaves_of_success {C : Codec N K} (hB : Binding C) (hC : Complete C) {r : C.Root}
    (c : Collected C r) (h : level2 c) :
    ∀ i x, passes C r i x → x = C.encode (recovered c) i := by
  intro i x ⟨π, hπ⟩
  obtain ⟨π', hπ'⟩ := hC (C.encode (recovered c)) i
  rw [show C.commit (C.encode (recovered c)) = r from h] at hπ'
  exact hB r i x _ π π' hπ hπ'

/-- once a check of root `r` succeeds, every other collection under `r` recovers the same bytes -/
theorem recovered_same {C : Codec N K} (hL : Local C) (hM : MDS C) (hB : Binding C)
    (hC : Complete C) {r : C.Root} (c₁ c₂ : Collected C r) (h : level2 c₁) :
    recovered c₂ = recovered c₁ := by
  have hagree : ∀ i, c₂.S i = true → c₂.leaf i = C.encode (recovered c₁) i :=
    fun i hi => leaves_of_success hB hC c₁ h i (c₂.leaf i) (c₂.valid i hi)
  show C.decode c₂.S c₂.leaf = recovered c₁
  rw [hL c₂.S c₂.leaf (C.encode (recovered c₁)) c₂.enough hagree]
  exact hM c₂.S _ c₂.enough

/-- L3: any two checks of a root succeed or fail together -/
theorem level2_all_or_none {C : Codec N K} (hL : Local C) (hM : MDS C) (hB : Binding C)
    (hC : Complete C) {r : C.Root} (c₁ c₂ : Collected C r) : level2 c₁ ↔ level2 c₂ := by
  constructor
  · intro h
    show C.commit (C.encode (recovered c₂)) = r
    rw [recovered_same hL hM hB hC c₁ c₂ h]
    exact h
  · intro h
    show C.commit (C.encode (recovered c₁)) = r
    rw [recovered_same hL hM hB hC c₂ c₁ h]
    exact h

/-- integrity: a check that succeeds recovers the one byte string whose encoding has root `r` -/
theorem integrity {C : Codec N K} (hM : MDS C) (hB : Binding C) (hC : Complete C) {r : C.Root}
    (c : Collected C r) (h : level2 c) :
    ∀ b, C.commit (C.encode b) = r → b = recovered c := by
  intro b hb
  have he : C.encode b = C.encode (recovered c) := funext fun i => by
    obtain ⟨π, hπ⟩ := hC (C.encode b) i
    rw [hb] at hπ
    exact leaves_of_success hB hC c h i _ ⟨π, hπ⟩
  calc b = C.decode c.S (C.encode b) := (hM c.S b c.enough).symm
    _ = C.decode c.S (C.encode (recovered c)) := by rw [he]
    _ = recovered c := hM c.S _ c.enough

/-- agreement: two nodes whose checks succeed deliver the same payload (`extract`: the
decompression, a function of the recovered bytes) -/
theorem agreement {C : Codec N K} {P : Type} (extract : C.Bytes → P) (hL : Local C)
    (hM : MDS C) (hB : Binding C) (hC : Complete C) {r : C.Root} (c₁ c₂ : Collected C r)
    (h₁ : level2 c₁) :
    extract (recovered c₁) = extract (recovered c₂) := by
  rw [recovered_same hL hM hB hC c₁ c₂ h₁]

/-- agreement for a group: its key names one descriptor (the group id is the descriptor's hash,
taken as collision-free); `Desc` stands for a descriptor at its slot, the key being
`group_key(group_id(d), slot)`. So two nodes that deliver for one key deliver the same payload -/
theorem agreement_by_key {Desc Key P : Type} {Nf Kf : Desc → Nat}
    (C : (d : Desc) → Codec (Nf d) (Kf d)) (key : Desc → Key)
    (key_inj : ∀ d₁ d₂, key d₁ = key d₂ → d₁ = d₂)
    (root : (d : Desc) → (C d).Root) (extract : (d : Desc) → (C d).Bytes → P)
    (hL : ∀ d, Local (C d)) (hM : ∀ d, MDS (C d)) (hB : ∀ d, Binding (C d))
    (hC : ∀ d, Complete (C d))
    (d₁ d₂ : Desc) (hk : key d₁ = key d₂)
    (c₁ : Collected (C d₁) (root d₁)) (c₂ : Collected (C d₂) (root d₂)) (h₁ : level2 c₁) :
    extract d₁ (recovered c₁) = extract d₂ (recovered c₂) := by
  obtain rfl := key_inj d₁ d₂ hk
  exact agreement (extract d₁) (hL d₁) (hM d₁) (hB d₁) (hC d₁) c₁ c₂ h₁

/-- the decode claim is true of a group whose check succeeds: every claimed chunk is the recovered
encoding's leaf, which passes level 1 at any node (a rebuilt chunk, §4.6) -/
theorem claim_sound {C : Codec N K} (hC : Complete C) {r : C.Root} (c : Collected C r)
    (h : level2 c) :
    ∀ j, passes C r j (C.encode (recovered c) j) := by
  intro j
  obtain ⟨π, hπ⟩ := hC (C.encode (recovered c)) j
  rw [show C.commit (C.encode (recovered c)) = r from h] at hπ
  exact ⟨π, hπ⟩

/-- the decode claim is wrong only of a group that every node reaching K drops: a check that fails
fails at every node -/
theorem claim_wrong_only_dropped {C : Codec N K} (hL : Local C) (hM : MDS C) (hB : Binding C)
    (hC : Complete C) {r : C.Root} (c₁ c₂ : Collected C r) (h : ¬ level2 c₁) : ¬ level2 c₂ :=
  fun h₂ => h ((level2_all_or_none hL hM hB hC c₁ c₂).2 h₂)

/-- the converse (§3: "only the builder can fail it"): a root that commits an encoding passes level
2 at every node, from any K positions; an honest builder's group is delivered wherever K arrive -/
theorem honest_succeeds {C : Codec N K} (hL : Local C) (hM : MDS C) (hB : Binding C)
    (hC : Complete C) {r : C.Root} (b : C.Bytes) (hb : C.commit (C.encode b) = r)
    (c : Collected C r) : level2 c := by
  have hagree : ∀ i, c.S i = true → c.leaf i = C.encode b i := fun i hi => by
    obtain ⟨π, hπ⟩ := c.valid i hi
    obtain ⟨π', hπ'⟩ := hC (C.encode b) i
    rw [hb] at hπ'
    exact hB r i _ _ π π' hπ hπ'
  show C.commit (C.encode (C.decode c.S c.leaf)) = r
  rw [hL c.S c.leaf (C.encode b) c.enough hagree, hM c.S b c.enough]
  exact hb

/-! ## Known answers and non-vacuity -/

/-- the hypotheses can all hold: a plain group of one chunk whose root is the chunk -/
def plainOne : Codec 1 1 where
  Bytes := Bool
  Leaf := Bool
  Root := Bool
  Proof := Unit
  encode := fun b _ => b
  decode := fun _ l => l 0
  commit := fun l => l 0
  verify := fun r _ x _ => x == r

/-- a set of positions of one that counts at least one names position 0 -/
theorem one_position (S : Fin 1 → Bool) (h : 1 ≤ count S) : S 0 = true := by
  have hS : S = fun _ => S 0 := funext fun i => by rw [show i = 0 from Fin.ext (by omega)]
  rw [hS] at h
  revert h
  generalize S 0 = s
  cases s <;> decide

/-- a set of positions of two that counts at least one and leaves out position 0 names position 1 -/
theorem two_positions (S : Fin 2 → Bool) (h : 1 ≤ count S) (h0 : S 0 = false) : S 1 = true := by
  have hS : S = fun i => if i.val = 0 then S 0 else S 1 := funext fun i => by
    show S i = if i.val = 0 then S 0 else S 1
    by_cases hi : i.val = 0
    · rw [ite_eq_left hi]; exact congrArg S (Fin.ext hi)
    · rw [ite_eq_right hi]; exact congrArg S (Fin.ext (show i.val = 1 by have := i.isLt; omega))
  rw [hS] at h
  revert h h0
  generalize S 0 = a
  generalize S 1 = b
  cases a <;> cases b <;> decide

theorem plainOne_meets_all : Local plainOne ∧ MDS plainOne ∧ Binding plainOne ∧ Complete plainOne := by
  refine ⟨fun S l l' hK h => h 0 (one_position S hK), fun _ _ _ => rfl, ?_, ?_⟩
  · intro r i x y π π' hx hy
    have hx' : (x : Bool) = r := (beq_iff_eq (α := Bool)).mp hx
    have hy' : (y : Bool) = r := (beq_iff_eq (α := Bool)).mp hy
    rw [hx', hy']
  · intro l i
    refine ⟨(), ?_⟩
    rw [show i = 0 from Fin.ext (by omega)]
    exact beq_self_eq_true (α := Bool) _

/-- `Binding` is needed: if every leaf passes, two checks succeed with different bytes; the other
three hypotheses hold -/
def noBinding : Codec 1 1 where
  Bytes := Bool
  Leaf := Bool
  Root := Unit
  Proof := Unit
  encode := fun b _ => b
  decode := fun _ l => l 0
  commit := fun _ => ()
  verify := fun _ _ _ _ => true

theorem noBinding_meets_rest : Local noBinding ∧ MDS noBinding ∧ Complete noBinding :=
  ⟨fun S _ _ hK h => h 0 (one_position S hK), fun _ _ _ => rfl, fun _ _ => ⟨(), rfl⟩⟩

theorem binding_needed :
    ∃ c₁ c₂ : Collected noBinding (), level2 c₁ ∧ level2 c₂ ∧ recovered c₁ ≠ recovered c₂ :=
  ⟨⟨fun _ => true, fun _ => true, by decide, fun _ _ => ⟨(), rfl⟩⟩,
   ⟨fun _ => true, fun _ => false, by decide, fun _ _ => ⟨(), rfl⟩⟩,
   rfl, rfl, fun h => Bool.noConfusion (h : (true : Bool) = false)⟩

/-- `MDS` is needed: a code whose second position carries nothing (it is always `true`), so no
decoder recovers the bytes from it alone; a check from the first position succeeds and one from the
second fails; the other three hypotheses hold -/
def noMDS : Codec 2 1 where
  Bytes := Bool
  Leaf := Bool
  Root := Bool × Bool
  Proof := Unit
  encode := fun b i => if i = 0 then b else true
  decode := fun S l => if S 0 then l 0 else l 1
  commit := fun l => (l 0, l 1)
  verify := fun r i x _ => if i = 0 then x == r.1 else x == r.2

theorem noMDS_meets_rest : Local noMDS ∧ Binding noMDS ∧ Complete noMDS := by
  refine ⟨?_, ?_, ?_⟩
  · intro S l l' hK h
    cases h0 : S 0
    · have e : l 1 = l' 1 := h 1 (two_positions S hK h0)
      simp [noMDS, h0, e] <;> rfl
    · have e : l 0 = l' 0 := h 0 h0
      simp [noMDS, h0, e] <;> rfl
  · intro r i x y π π' hx hy
    by_cases hi : i = 0
    · have hx' : (x : Bool) = r.1 := (beq_iff_eq (α := Bool)).mp (by simpa [noMDS, hi] using hx)
      have hy' : (y : Bool) = r.1 := (beq_iff_eq (α := Bool)).mp (by simpa [noMDS, hi] using hy)
      rw [hx', hy']
    · have hx' : (x : Bool) = r.2 := (beq_iff_eq (α := Bool)).mp (by simpa [noMDS, hi] using hx)
      have hy' : (y : Bool) = r.2 := (beq_iff_eq (α := Bool)).mp (by simpa [noMDS, hi] using hy)
      rw [hx', hy']
  · intro l i
    refine ⟨(), ?_⟩
    by_cases hi : i = 0
    · subst hi; simp only [noMDS]; exact beq_self_eq_true (α := Bool) _
    · have h1 : i = 1 := Fin.ext (by
        have := i.isLt
        have : i.val ≠ 0 := fun h => hi (Fin.ext h)
        show i.val = 1
        omega)
      subst h1; simp only [noMDS]; exact beq_self_eq_true (α := Bool) _

theorem mds_needed : ∃ c₁ c₂ : Collected noMDS (false, true), level2 c₁ ∧ ¬ level2 c₂ :=
  ⟨⟨fun i => i == 0, noMDS.encode false, by decide, fun i _ => ⟨(), by revert i; decide⟩⟩,
   ⟨fun i => i == 1, noMDS.encode false, by decide, fun i _ => ⟨(), by revert i; decide⟩⟩,
   rfl, fun h => by
     have h' : ((true, true) : Bool × Bool) = (false, true) := h
     cases h'⟩

end Agreement

-- the audit, a failure a build error: the theorems rest on Lean's own axioms only
open Lean Elab Command in
#eval show CommandElabM Unit from do
  let allowed := [``propext, ``Classical.choice, ``Quot.sound]
  let mut rest : Std.HashSet Name := {}
  for n in [``Agreement.leaves_of_success, ``Agreement.recovered_same,
      ``Agreement.level2_all_or_none, ``Agreement.integrity, ``Agreement.agreement,
      ``Agreement.agreement_by_key, ``Agreement.claim_sound, ``Agreement.claim_wrong_only_dropped,
      ``Agreement.honest_succeeds, ``Agreement.one_position, ``Agreement.two_positions,
      ``Agreement.plainOne_meets_all, ``Agreement.noBinding_meets_rest, ``Agreement.binding_needed,
      ``Agreement.noMDS_meets_rest, ``Agreement.mds_needed] do
    for a in ← liftCoreM (collectAxioms n) do
      rest := rest.insert a
      unless allowed.contains a do logError m!"{n} rests on {a}"
  logInfo m!"the sixteen theorems rest on {rest.toList}"
