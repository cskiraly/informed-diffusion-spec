"""Bitmaps and the read-without-allocating maps of the pseudocode's §8.1.

The pseudocode treats per-group and per-peer state as maps whose missing entries read as empty
"and reading it allocates nothing". Some also carry meaning in whether an entry exists at
all: card 16's guard asks whether a peer sent any HAVE for a group (`g not in peer_has[p]`),
note_push starts a clock at the first push, an installation releases the ties it finds (`tied`),
and the writer takes an owed answer for each group it finds (`owed_answers`). LazyMap and LazyDict
give both: a missing key reads as a fresh, detached entry, which inserts itself into the map the
first time it is written to. Every table of protocol.md's and of protocol-v2.md's is one of them, or a
DefaultMap. AutoMap, which creates an entry on a read, no longer holds any of them.
"""


def _v(x):
    if isinstance(x, Bits):
        return x.v
    if isinstance(x, (set, frozenset)):          # the pseudocode's {i} literals
        v = 0
        for i in x:
            v |= 1 << i
        return v
    return x.bits.v


class Bits:
    """A set of chunk indices backed by an int; bit i is index i."""
    __slots__ = ("v",)

    def __init__(self, v=0):
        self.v = v

    def has(self, i):
        return (self.v >> i) & 1 == 1

    def set(self, i):
        self.v |= 1 << i

    def clear(self, i):
        self.v &= ~(1 << i)

    def empty(self):
        return self.v == 0

    def copy(self):
        return Bits(self.v)

    def __or__(self, o):
        return Bits(self.v | _v(o))

    def __and__(self, o):
        return Bits(self.v & _v(o))

    __ror__ = __or__

    def __rand__(self, o):
        return Bits(_v(o) & self.v)

    def __invert__(self):
        return Bits(~self.v)

    def __ior__(self, o):
        self.v |= _v(o)
        return self

    def __bool__(self):
        return self.v != 0

    def __eq__(self, o):
        return isinstance(o, Bits) and self.v == o.v

    def __hash__(self):
        return hash(self.v)

    def __iter__(self):
        v = self.v
        if v < 0:
            raise ValueError("iterating a complemented bitmap")
        i = 0
        while v:
            if v & 1:
                yield i
            v >>= 1
            i += 1

    def __repr__(self):
        return f"Bits({sorted(self)})" if self.v >= 0 else f"Bits(~{sorted(Bits(~self.v))})"


def popcount(x):
    v = _v(x)
    if v < 0:
        raise ValueError("popcount of a complemented bitmap")
    return v.bit_count()


def all_bits(n):
    return Bits((1 << n) - 1)


def bitmap(indices):
    """The bitmap of a set of indices (§8.1)."""
    return Bits(_v(set(indices)))


class _Lazy:
    """Base of entries that join their map on first write."""
    __slots__ = ("_home", "_key", "__weakref__")

    def _attach(self):
        home = object.__getattribute__(self, "_home")
        if home is not None:
            object.__setattr__(self, "_home", None)
            home._adopt(object.__getattribute__(self, "_key"), self)


class HaveEntry(_Lazy):
    """peer_has[p][g]: the union of p's HAVE bitmaps for g, and its expiry (§4.3); v2 adds the two
    claims a holding carries (protocol-v2.md §1.5)."""
    __slots__ = ("bits", "ttl", "claim_all", "complete")

    def __init__(self, home=None, key=None):
        object.__setattr__(self, "_home", home)
        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "bits", Bits())
        object.__setattr__(self, "ttl", 0)
        object.__setattr__(self, "claim_all", False)
        object.__setattr__(self, "complete", False)

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        self._attach()

    def has(self, i):
        return self.bits.has(i)


class PushEntry(Bits):
    """pushed[p][g]: the chunks we chose to push p, when the first went, and its expiry (§5.2)."""
    __slots__ = ("first_push", "ttl", "_home", "_key", "__weakref__")

    def __init__(self, home=None, key=None):
        super().__init__(0)
        self.first_push = None
        self.ttl = 0
        self._home, self._key = home, key

    def _attach(self):
        home = self._home
        if home is not None:
            self._home = None
            home._adopt(self._key, self)

    def set(self, i):
        super().set(i)
        self._attach()

    def __ior__(self, o):
        super().__ior__(o)
        self._attach()
        return self

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if (k in ("first_push", "ttl") or (k == "v" and v)) and getattr(self, "_home", None) is not None:
            self._attach()


class OfferList(list):
    """offers[a]: an ask's announcers, in announcement order (§6.1). A missing one reads as an empty,
    detached list, which joins its map at its first append. It keeps its map's count of the lists
    each announcer is in (§8.2's `listed`), so that the count follows whoever changes a list. Only `append` and
    `remove` keep that count, so every other change of the list's members is refused."""
    __slots__ = ("_home", "_key", "_listed", "__weakref__")

    def __init__(self, home=None, key=None):
        super().__init__()
        self._home, self._key = home, key
        self._listed = home.listed if home is not None else None

    def append(self, x):
        super().append(x)
        if self._listed is not None:
            self._listed[x] = self._listed.get(x, 0) + 1
        home = self._home
        if home is not None:
            self._home = None
            home._adopt(self._key, self)

    def remove(self, x):
        super().remove(x)
        if self._listed is not None:
            self._listed[x] -= 1

    def _uncounted(self, *args, **kw):
        raise TypeError("an offer list changes only by append and remove, which keep `listed`")

    insert = extend = __setitem__ = __delitem__ = __iadd__ = __imul__ = pop = clear = _uncounted


class LazyMap:
    """A map whose missing keys read as a detached entry made by `make(home, key)`. An entry joins it through
    `_adopt`; a LazyMap that is itself a detached entry of another map (its home) joins that one then. As in
    LazyDict: two reads of one missing key give one detached entry until it is written or its key is set, and a
    detached entry written after another value was set under its key fails."""
    __slots__ = ("_d", "_make", "_home", "_key", "_detached", "__weakref__")

    def __init__(self, make, home=None, key=None):
        self._d = {}
        self._make = make
        self._home, self._key = home, key
        self._detached = None

    def _adopt(self, k, v):
        cur = self._d.get(k)
        if cur is not None and cur is not v:
            raise AssertionError(f"a lazy map: a detached entry of the key {k!r} written after another value was "
                                 f"set under it; one write would be lost")
        self._d[k] = v
        if self._detached is not None:
            self._detached.pop(k, None)
        _join(self)

    def __getitem__(self, k):
        e = self._d.get(k)
        if e is not None:
            return e
        d = self._detached
        if d is not None:
            e = d.get(k)
            if e is not None:
                return e
        e = self._make(self, k)
        if d is None:
            d = self._detached = {}
        d[k] = e
        return e

    def __setitem__(self, k, v):
        self._d[k] = v
        if self._detached is not None:
            self._detached.pop(k, None)
        _join(self)

    def __contains__(self, k):
        return k in self._d

    def __delitem__(self, k):
        del self._d[k]

    def pop(self, k, *default):
        return self._d.pop(k, *default)

    def get(self, k, default=None):
        return self._d.get(k, default)

    def items(self):
        return self._d.items()

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)


class OfferMap(LazyMap):
    """`offers`: ask -> its OfferList. `listed[p]` is the number of lists p is in, kept as lists gain and lose
    announcers and as a whole list goes."""
    __slots__ = ("listed",)

    def __init__(self):
        super().__init__(OfferList)
        self.listed = {}

    def _gone(self, lst):
        for x in lst or ():
            self.listed[x] -= 1

    def __delitem__(self, k):
        self._gone(self._d[k])
        del self._d[k]

    def pop(self, k, *default):
        self._gone(self._d.get(k))
        return self._d.pop(k, *default)

    def __setitem__(self, k, v):
        raise TypeError("an offer list joins `offers` by its first append, which keeps `listed`")


class TieMap(LazyMap):
    """A level of `tied` (block root -> connection -> group -> indices, §4.2). A missing key reads as a detached
    entry, and a level joins its own map when an entry of it does: a read creates nothing at any level, and what
    is in the map is what a copy tied. `on_block_installed` goes by the entries it finds, so here existence
    carries meaning."""
    __slots__ = ()


class TieBits(Bits):
    """tied[root][p][g]: the indices of p's copies of g that wait for the root; it joins its map at its first set."""
    __slots__ = ("_home", "_key", "__weakref__")

    def __init__(self, home=None, key=None):
        super().__init__(0)
        self._home, self._key = home, key

    def set(self, i):
        super().set(i)
        _join(self)

    def __ior__(self, o):
        super().__ior__(o)
        if self.v:
            _join(self)
        return self


def tie_table():
    return TieMap(lambda roots, root: TieMap(lambda peers, p: TieMap(TieBits, peers, p), roots, root))


class AutoMap(dict):
    """A map whose missing keys are created on read by `make()` (state where existence carries no meaning)."""
    __slots__ = ("_make",)

    def __init__(self, make):
        super().__init__()
        self._make = make

    def __missing__(self, k):
        v = self[k] = self._make()
        return v


class DefaultMap(dict):
    """A map whose missing keys read as a constant, without inserting it."""
    __slots__ = ("_default",)

    def __init__(self, default):
        super().__init__()
        self._default = default

    def __missing__(self, k):
        return self._default


# ---- §8.1's rule for the rest of the tables, as the tables show it: a read creates no entry, at any level, and a
# write through a read creates what it writes. A missing key reads as a detached entry (or a constant), which joins its map at its
# first write; the map, if it is itself such an entry of another, joins that one then, and so on up. Two reads
# of one missing key give the same detached entry until it joins or its key is set (a cache, which no `in`,
# `len` or iteration sees), so that a caller holding one sees what another writes through the other. The cache
# keeps an entry nobody holds: one not written is empty, as a new one would be, and a weak cache made and
# dropped an entry at most reads of a missing key. A detached entry written after another value was set under
# its key would lose a write: that fails (`_adopt`).
#
# So the toy keeps one entry for each missing key read, until the key is written. §8.1's "reading it allocates
# nothing" rules that out for a node: a peer can name groups never admitted (on_iwant reads `peer_has[p][g]`
# for any unexpired group an IWANT names, with no check that the group was admitted, and §8.2's limit counts only
# HAVEs, IHAVEs and deferred chunks), and a node that kept state for each such read would grow without bound. The
# toy's runs send no such IWANT, so the case does not arise there; and no outcome depends on the cache, which no
# `in`, `len` or iteration sees. The cache is the toy's, not the document's.

def _join(e):
    home = e._home
    if home is not None:
        e._home = None
        home._adopt(e._key, e)


class LazyDict(dict):
    """A map whose missing keys read as `make(self, key)`, inserting nothing (with `make` None a missing key
    raises, as a dict's does). A dict for every other use: `in`, `get`, iteration, `pop` and `del` read and
    change only what is there."""
    __slots__ = ("_make", "_home", "_key", "_detached", "__weakref__")

    def __init__(self, make=None, home=None, key=None):
        super().__init__()
        self._make, self._home, self._key, self._detached = make, home, key, None

    def __missing__(self, k):
        if self._make is None:
            raise KeyError(k)
        d = self._detached
        if d is not None:
            e = d.get(k)
            if e is not None:
                return e
        e = self._make(self, k)
        if hasattr(e, "_home"):                     # an entry that can join (a count reads as a plain 0)
            if d is None:
                d = self._detached = {}
            d[k] = e
        return e

    def _adopt(self, k, v):
        cur = dict.get(self, k)
        if cur is not None and cur is not v:
            raise AssertionError(f"a lazy map: a detached entry of the key {k!r} written after another value was "
                                 f"set under it; one write would be lost")
        dict.__setitem__(self, k, v)
        if self._detached is not None:
            self._detached.pop(k, None)
        _join(self)

    def __setitem__(self, k, v):
        dict.__setitem__(self, k, v)
        if self._detached is not None:
            self._detached.pop(k, None)
        _join(self)

    def setdefault(self, k, default=None):
        if k not in self:
            self[k] = default
        return dict.__getitem__(self, k)

    def update(self, *args, **kw):
        dict.update(self, *args, **kw)
        if self:
            _join(self)

    def __ior__(self, other):
        dict.update(self, other)
        if self:
            _join(self)
        return self


class LazyBits(Bits):
    """A bitmap entry of a LazyDict; it joins at its first set, or at any write that leaves it not empty."""
    __slots__ = ("_home", "_key", "__weakref__")

    def __init__(self, home=None, key=None):
        super().__init__(0)
        self._home, self._key = home, key

    def __setattr__(self, k, v):                # `v` set directly, as `set` and `|=` also do
        object.__setattr__(self, k, v)
        if k == "v" and v and getattr(self, "_home", None) is not None:
            _join(self)

    def set(self, i):
        super().set(i)
        _join(self)

    def __ior__(self, o):
        super().__ior__(o)
        _join(self)
        return self


class LazySet(set):
    """A set entry of a LazyDict; it joins at its first addition."""
    __slots__ = ("_home", "_key")

    def __init__(self, home=None, key=None):
        super().__init__()
        self._home, self._key = home, key

    def add(self, x):
        super().add(x)
        _join(self)

    def update(self, *others):
        super().update(*others)
        if self:
            _join(self)

    def __ior__(self, o):
        super().__ior__(o)
        if self:
            _join(self)
        return self

    def symmetric_difference_update(self, o):
        super().symmetric_difference_update(o)
        if self:
            _join(self)

    def __ixor__(self, o):
        super().__ixor__(o)
        if self:
            _join(self)
        return self


class LazyList(list):
    """A list entry of a LazyDict; it joins at its first addition."""
    __slots__ = ("_home", "_key", "__weakref__")

    def __init__(self, home=None, key=None):
        super().__init__()
        self._home, self._key = home, key

    def append(self, x):
        super().append(x)
        _join(self)

    def extend(self, xs):
        super().extend(xs)
        if self:
            _join(self)

    def insert(self, i, x):
        super().insert(i, x)
        _join(self)

    def __iadd__(self, xs):
        super().__iadd__(xs)
        if self:
            _join(self)
        return self

    def __setitem__(self, i, x):                # an element, or a slice
        super().__setitem__(i, x)
        if self:
            _join(self)


def lazy(leaf):
    """key -> leaf(home, key): a one-level table."""
    return LazyDict(leaf)


def lazy2(leaf):
    """key -> key -> leaf(home, key): a two-level table."""
    return LazyDict(lambda home, k: LazyDict(leaf, home, k))


def lazy3(leaf):
    """key -> key -> key -> leaf(home, key): a three-level table (protocol-v2.md's relations, by peer, type and
    family)."""
    return LazyDict(lambda h1, k1: LazyDict(lambda h2, k2: LazyDict(leaf, h2, k2), h1, k1))


def false(home, k):
    """A flag leaf: reads as False; setting it writes it through the map."""
    return False


def lazy_dict(home, k):
    """A dict leaf: a missing key of it raises, as a dict's does."""
    return LazyDict(None, home, k)


def zero(home, k):
    """A count leaf: reads as 0; `+= 1` writes it through the map."""
    return 0
