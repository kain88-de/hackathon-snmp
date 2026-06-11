"""OID value type for oidtrace."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True, slots=True)
class Oid:
    """An SNMP Object Identifier.

    Stored as a tuple of integer arcs.  Ordering is numeric (correct OID
    ordering), not lexicographic.  Frozen → hashable; order=True → bisect-
    compatible.
    """

    arcs: tuple[int, ...]

    @classmethod
    def from_str(cls, s: str) -> Oid:
        """Parse a dotted-decimal OID string.

        Raises ValueError for any input that is not a non-empty sequence of
        non-negative integers separated by single dots.  Each arc must consist
        solely of ASCII digits with no leading zeros.
        """
        if not s or s.startswith("."):
            raise ValueError(f"Invalid OID: {s!r}")
        parts = s.split(".")
        for p in parts:
            if not (p.isascii() and p.isdigit()):
                raise ValueError(f"Invalid OID: {s!r}")
            if len(p) > 1 and p[0] == "0":
                raise ValueError(f"Invalid OID: {s!r}")
        return cls(tuple(int(p) for p in parts))

    def __str__(self) -> str:
        return ".".join(str(n) for n in self.arcs)

    def __repr__(self) -> str:
        return f"Oid('{self}')"

    def in_subtree(self, root: Oid) -> bool:
        """Return True if self is equal to root or is a descendant of it."""
        return self.arcs[: len(root.arcs)] == root.arcs
