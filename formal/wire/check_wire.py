#!/usr/bin/env python3
"""Arithmetic and wire-format properties of §1–§2 of the spec (as of v0.4 and v0.5), checked exhaustively
over every payload size. Run: python3 -I formal/wire/check_wire.py

W1  build_group's K (from the body) and valid_descriptor's K(d) (from the compressed length) agree,
    for every body size and every compressed length snappy can produce;
W2  every chunk fits MAX_SEGMENT_SIZE, under snappy's worst-case expansion;
W3  the chunk lengths add up to total_length, and the last data chunk is not empty;
W4  a Merkle proof fits the wire's List[Bytes32, 14], and a HAVE bitmap names every index of a
    group in MAX_HAVE_BYTES;
W5  the three id forms in control fields (structured id, HAVE string, WANT string) by length.
"""
from math import ceil

UNIT = 16 * 1024
MAX_CHUNKS = 256
MAX_PLAIN_CHUNKS = 8192
MAX_SEGMENT_SIZE = 2 * UNIT
MAX_HAVE_BYTES = 1024
PROOF_MAX = 14
SNAPPY_MAX_RATIO = 21.4            # a copy of 64 bytes costs 3: 64/3 = 21.3x on 1 MiB of zeros (measured)


def snappy_max(n):                 # snappy's documented worst case: 32 + n + n/6
    return 32 + n + n // 6


def snappy_min(n):
    return max(1, int(n / SNAPPY_MAX_RATIO))


def k_of(L, size):
    return ceil(L / size)


def check_coded():
    bad_k = bad_size = bad_len = 0
    worst_size = 0
    for K in range(1, MAX_CHUNKS // 2 + 1):                      # coded: 2K <= MAX_CHUNKS
        lo_body, hi_body = (K - 1) * UNIT + 1, K * UNIT          # bodies that give this K
        lo_L, hi_L = snappy_min(lo_body), snappy_max(hi_body)    # every compressed length possible
        for L in range(lo_L, hi_L + 1):
            size = ceil(L / K)
            if k_of(L, size) != K:
                bad_k += 1
            worst_size = max(worst_size, size)
            if size > MAX_SEGMENT_SIZE:
                bad_size += 1
            last = L - (K - 1) * size
            if not (0 < last <= size):
                bad_len += 1
    return bad_k, bad_size, bad_len, worst_size


def check_plain():
    bad = 0
    for K in range(MAX_CHUNKS // 2 + 1, MAX_PLAIN_CHUNKS + 1):   # plain: no compression, N = K
        for L in ((K - 1) * UNIT + 1, K * UNIT):                 # the extremes for this K
            size = ceil(L / K)
            last = L - (K - 1) * size
            if k_of(L, size) != K or size > MAX_SEGMENT_SIZE or not (0 < last <= size):
                bad += 1
    return bad


def proof_depth(n):
    w = 1
    while w < n:
        w *= 2
    return w.bit_length() - 1


def main():
    bk, bs, bl, ws = check_coded()
    print(f"W1 coded groups, every K and compressed length: K(d) != K in {bk} cases")
    print(f"W2 largest chunk {ws} bytes against MAX_SEGMENT_SIZE {MAX_SEGMENT_SIZE}: {bs} over")
    print(f"W3 last data chunk empty or longer than the others: {bl} cases")
    print(f"W1-W3 plain groups (K up to {MAX_PLAIN_CHUNKS}): {check_plain()} failures")
    print(f"W4 proof depth at N = {MAX_CHUNKS}: {proof_depth(MAX_CHUNKS)}, at N = {MAX_PLAIN_CHUNKS}: "
          f"{proof_depth(MAX_PLAIN_CHUNKS)} (wire limit {PROOF_MAX}); bitmap for N = {MAX_PLAIN_CHUNKS}: "
          f"{ceil(MAX_PLAIN_CHUNKS / 8)} bytes (limit {MAX_HAVE_BYTES})")
    # W5: the forms as strings in a message-id field
    structured = 32 + 4 + 20
    want = 4 + 1 + 32 + 4
    have_min, have_max = 4 + 1 + 32, 4 + 1 + 32 + MAX_HAVE_BYTES
    print(f"W5 lengths: structured id {structured}, WANT {want}, HAVE {have_min}..{have_max}: "
          f"a HAVE with {structured - have_min} bitmap bytes is as long as a structured id, so only the "
          f"5-byte MAGIC+VERSION prefix tells them apart; a group id is sha256 of the descriptor, and a "
          f"builder that grinds its payload finds one starting 'HAVE\\x01' in about 2^40 hashes")
    # how compressible a body must be to break W1, for the record
    print("W1 breaks only if compression exceeds about UNIT/K: "
          + ", ".join(f"K={K}: {((K - 1) * UNIT + 1) / (K * (K - 1)):.0f}x" for K in (2, 8, 64, 128)))


if __name__ == "__main__":
    main()
