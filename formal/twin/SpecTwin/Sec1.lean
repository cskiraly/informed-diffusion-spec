import SpecTwin.Basic

/-! # The twin of protocol.md §1, "The payload, the code and the commitment" (v0.10.4, spec 34f60f8)

group_id, group_key, K, N, segment_length, valid_descriptor and build_group (protocol.md §1), line for line.

- **What is asked, not computed:** `sha256`, `serialize`, `snappy_block_encode`,
  `pad_each`, `rs_parity`, `merkle_root`, `merkle_proof`. The toy's are stand-ins, so each is a question, asked
  with the arguments the document's line gives it. What a replay then shows of §1 is the orchestration: the
  prefixes 0x02 and 0x03, the slot's eight little-endian bytes, the order of the checks.
- **`K`'s division is the Python's:** `ceil(d.total_length / d.segment_size)` divides two ints to the nearest
  double, rounding the exact quotient once. `pyCeilDiv` computes that in integers. It is not an exact ceiling
  (at 2^53 + 1 over 1 the Python gives 2^53), nor two conversions and a division.
- **`K` and `N` take what the caller read of `desc`:** `K(desc[g])` of a group with no descriptor raises in `K`,
  after `K` is entered, as the Python's `None.total_length` does.
- **`segment_length` returns an integer that can be negative,** where K is not the exact ceiling. -/

namespace SpecTwin

open Node61

/-! ## Bytes and numbers: what the Python's operators do -/

private def hexByte (b : Nat) : String := String.ofList [Nat.digitChar (b / 16), Nat.digitChar (b % 16)]

/-- `uint32_le(n)` and `uint64_le(n)`: n in `width` bytes, little-endian, as hex digits -/
def leHex (width n : Nat) : Hex := String.join ((List.range width).map fun k => hexByte ((n >>> (8 * k)) % 256))

/-- `ceil(a / b)` for two Python ints, b not 0. The Python's `/` gives the double nearest the exact quotient,
ties to even, rounding once; `ceil` then gives the int that is its ceiling. Computed in integers alone. `none`
where the Python raises `OverflowError` (a quotient of 2^1024 or more after rounding). -/
def pyCeilDiv (a b : Nat) : Option Nat :=
  if a == 0 then some 0 else
  let la := a.log2
  let lb := b.log2
  -- e = floor(log2(a / b)): la - lb, or one less where a < b * 2^(la - lb)
  let below : Bool := if la ≥ lb then a < b <<< (la - lb) else a <<< (lb - la) < b
  let e : Int := (la : Int) - (lb : Int) - (if below then 1 else 0)
  if e < 0 then
    -- 0 < a / b < 1: every double it can round to has the ceiling 1, but 0.0 itself. It rounds to 0.0 below half
    -- the smallest double (2^-1074), and at exactly half (a tie, to even)
    if e < -1075 then some 0
    else if e == -1075 then (if a <<< 1075 == b then some 0 else some 1)
    else some 1
  else
    let e := e.toNat
    if e ≥ 1024 then none else
    -- m: the quotient scaled to 53 bits (2^52 ≤ a * 2^(52 - e) / b < 2^53), rounded to nearest, ties to even
    let (num, den) := if e ≤ 52 then (a <<< (52 - e), b) else (a, b <<< (e - 52))
    let m0 := num / den
    let r := num % den
    let m := if 2 * r > den || (2 * r == den && m0 % 2 == 1) then m0 + 1 else m0
    if e == 1023 && m == 2 ^ 53 then none
    else if e ≤ 52 then some ((m + (1 <<< (52 - e)) - 1) >>> (52 - e))      -- the ceiling of m / 2^(52 - e)
    else some (m <<< (e - 52))                                               -- a whole number already

variable {m : Type → Type} [Monad m] [Node61 m]

/-! ## §1 The payload, the code and the commitment [c1, c6] -/

/-- `group_id(d)` (§1) -/
def groupId (d : Descriptor) : M m Hex := do
  enter "group_id"
  sha256 ("02" ++ (← serialize d))                           -- `sha256(b"\x02" + serialize(d))`

/-- `group_key(gid, slot)` (§1): the group's name in diffusion: a group id committed at a slot -/
def groupKey (gid : Hex) (slot : Nat) : M m Hex := do
  enter "group_key"
  if slot ≥ 2 ^ 64 then                                     -- `uint64_le(slot)`
    return (← crash "OverflowError: int too big to convert (group_key: uint64_le(slot))")
  sha256 ("03" ++ gid ++ leHex 8 slot)                       -- `sha256(b"\x03" + gid + uint64_le(slot))`

/-- `K(d)` (§1): the data chunks. `d` is what the caller read: `K(desc[g])` of a group with no descriptor
raises here, in `K`. -/
def K (d : Option Descriptor) : M m Nat := do
  enter "K"
  let some d := d
    | crash "AttributeError: 'NoneType' object has no attribute 'total_length' (K)"
  if d.segmentSize == 0 then
    return (← crash "ZeroDivisionError: division by zero (K)")
  match pyCeilDiv d.totalLength d.segmentSize with           -- `ceil(d.total_length / d.segment_size)`
  | some k => return k
  | none => crash "OverflowError: integer division result too large for a float (K)"

/-- `N(d)` (§1) -/
def N (d : Option Descriptor) : M m Nat := do
  enter "N"
  let some d := d
    | crash "AttributeError: 'NoneType' object has no attribute 'count' (N)"
  return d.count

/-- `segment_length(d, i)` (§1) -/
def segmentLength (d : Descriptor) (i : Nat) : M m Int := do
  enter "segment_length"
  if (i : Int) == ((← K (some d)) : Int) - 1 then           -- `if i == K(d) - 1:` the last data chunk
    branch "segment_length: the last data chunk"
    return (d.totalLength : Int) - (((← K (some d)) : Int) - 1) * (d.segmentSize : Int)
  branch "segment_length: data and parity"
  return (d.segmentSize : Int)

/-- `valid_descriptor(d)` (§1): checked before any state is allocated for the group -/
def validDescriptor (d : Descriptor) : M m Bool := do
  enter "valid_descriptor"
  let c := (← read).c
  if d.hashId != 0 || d.segmentSize == 0 || d.segmentSize > c.MAX_SEGMENT_SIZE then
    branch "valid_descriptor: the hash or the segment size"
    return false
  if d.totalLength == 0 then
    branch "valid_descriptor: no length"
    return false
  if d.version == 2 then                                    -- `d.encoding == 1 and d.count == 2 * K(d) <= MAX_CHUNKS`
    if d.encoding != 1 then
      branch "valid_descriptor: coded, another encoding"
      return false
    let k2 := 2 * (← K (some d))                            -- the chain's middle term, once
    let r := d.count == k2 && k2 ≤ c.MAX_CHUNKS
    branch (if r then "valid_descriptor: coded" else "valid_descriptor: coded, another count")
    return r
  if d.version == 1 then                                    -- `d.encoding == 0 and d.count == K(d) <= MAX_PLAIN_CHUNKS`
    if d.encoding != 0 then
      branch "valid_descriptor: plain, another encoding"
      return false
    let k ← K (some d)
    let r := d.count == k && k ≤ c.MAX_PLAIN_CHUNKS
    branch (if r then "valid_descriptor: plain" else "valid_descriptor: plain, another count")
    return r
  branch "valid_descriptor: no such version"
  return false

/-- `build_group(body)` (§1): at bid time -/
def buildGroup (body : Blob) : M m (Descriptor × List Shard) := do
  enter "build_group"
  let c := (← read).c
  if c.UNIT == 0 then
    return (← crash "ZeroDivisionError: division by zero (build_group: len(body) / UNIT)")
  let some k := pyCeilDiv body.n c.UNIT                      -- `K = ceil(len(body) / UNIT)`: data chunks [c1]
    | crash "OverflowError: integer division result too large for a float (build_group: len(body) / UNIT)"
  let coded := 2 * k ≤ c.MAX_CHUNKS                          -- [c6]
  let data ← if coded then snappyBlockEncode body else pure body   -- compress first [c6]
  if k == 0 then
    return (← crash "ZeroDivisionError: division by zero (build_group: len(data) / K)")
  let some size := pyCeilDiv data.n k                        -- `size = ceil(len(data) / K)`
    | crash "OverflowError: integer division result too large for a float (build_group: len(data) / K)"
  let segs := (List.range k).map fun i => data.slice (i * size) ((i + 1) * size)   -- the last may be short
  let mut parity : List Blob := []                           -- `rs_parity(pad_each(segs, size), K) if coded else []`
  if coded then
    let padded ← padEach segs size
    parity ← rsParity padded k                               -- K parity chunks [c6]
  let leaves := segs ++ parity
  let root ← merkleRoot leaves
  let d : Descriptor :=
    { version := if coded then 2 else 1, hashId := 0, encoding := if coded then 1 else 0,
      count := leaves.length, segmentSize := size, totalLength := data.n, root := root }
  let mut shards : Array Shard := #[]
  for (leaf, i) in leaves.zipIdx do                          -- `for i in range(len(leaves))`
    let proof ← merkleProof leaves i
    shards := shards.push { index := i, proof := proof, data := leaf }
  return (d, shards.toList)

end SpecTwin
