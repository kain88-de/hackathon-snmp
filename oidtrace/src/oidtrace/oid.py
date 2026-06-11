"""OID value type for oidtrace.

OIDs are represented internally as ``tuple[int, ...]`` rather than strings
because string comparison mis-orders them: ``"1.3.6.1.10" < "1.3.6.1.2"``
lexicographically, which is wrong.  Tuples of ints compare correctly.
Strings appear only at the package boundary (parse / format).
"""

type Oid = tuple[int, ...]


def parse_oid(s: str) -> Oid:
    """Parse a dotted-decimal OID string into an Oid tuple.

    Raises ValueError for any input that is not a non-empty sequence of
    non-negative integers separated by single dots.
    """
    if not s or s.startswith("."):
        raise ValueError(f"Invalid OID: {s!r}")
    parts = s.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        raise ValueError(f"Invalid OID: {s!r}") from None


def format_oid(oid: Oid) -> str:
    """Format an Oid tuple as a dotted-decimal string."""
    return ".".join(str(n) for n in oid)


def in_subtree(root: Oid, oid: Oid) -> bool:
    """Return True if *oid* is equal to *root* or is a descendant of it."""
    return oid[: len(root)] == root
