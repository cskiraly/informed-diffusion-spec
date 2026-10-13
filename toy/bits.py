"""Bitmaps and the read-without-allocating maps of the pseudocode's §8.1.

The pseudocode treats per-group and per-peer state as maps whose missing entries read as empty
"and reading it allocates nothing". Two of them also carry meaning in whether an entry exists at
all: card 16's guard asks whether a peer sent any HAVE for a group (`g not in peer_has[p]`), and
note_push starts a clock at the first push. LazyMap gives both: a missing key reads as a fresh,
detached entry, which inserts itself into the map the first time it is written to.
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
    __slots__ = ("_home", "_key")

    def _attach(self):
        home = object.__getattribute__(self, "_home")
        if home is not None:
            home._d[object.__getattribute__(self, "_key")] = self
            object.__setattr__(self, "_home", None)


class HaveEntry(_Lazy):
    """peer_has[p][g]: the union of p's HAVE bitmaps for g, and its expiry (§4.3)."""
    __slots__ = ("bits", "ttl")

    def __init__(self, home=None, key=None):
        object.__setattr__(self, "_home", home)
        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "bits", Bits())
        object.__setattr__(self, "ttl", 0)

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        self._attach()

    def has(self, i):
        return self.bits.has(i)


class PushEntry(Bits):
    """pushed[p][g]: the chunks we chose to push p, when the first went, and its expiry (§5.2)."""
    __slots__ = ("first_push", "ttl", "_home", "_key")

    def __init__(self, home=None, key=None):
        super().__init__(0)
        self.first_push = None
        self.ttl = 0
        self._home, self._key = home, key

    def _attach(self):
        if self._home is not None:
            self._home._d[self._key] = self
            self._home = None

    def set(self, i):
        super().set(i)
        self._attach()

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if k in ("first_push", "ttl") and getattr(self, "_home", None) is not None:
            self._attach()


class LazyMap:
    """A map whose missing keys read as a detached entry made by `make(home, key)`."""
    __slots__ = ("_d", "_make")

    def __init__(self, make):
        self._d = {}
        self._make = make

    def __getitem__(self, k):
        e = self._d.get(k)
        return e if e is not None else self._make(self, k)

    def __setitem__(self, k, v):
        self._d[k] = v

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
