"""OID value type for oidtrace.

Design rationale — why tuple[int, ...] and not str:
  String comparison mis-orders OIDs with varying arc widths.  For example:
    "1.3.6.1.10" < "1.3.6.1.2"   (lexicographic — wrong)
    (1,3,6,1,10) > (1,3,6,1,2)   (tuple/numeric — correct)

  Storing arcs as a tuple[int, ...] gives correct OID ordering for free via
  Python's built-in tuple comparison, which compares element-by-element
  numerically.  This makes the type bisect-compatible and usable as a dict key
  or set member (frozen → hashable).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Only sequences of ASCII digits separated by dots.  No leading zeros (except
# the arc "0" itself), no signs, no whitespace, no underscores.
_ARC_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")


@dataclass(frozen=True, order=True, slots=True)
class Oid:
    """An SNMP Object Identifier stored as an immutable tuple of integer arcs.

    Attributes:
        arcs: The integer components of the OID, e.g. (1, 3, 6, 1) for 1.3.6.1.
    """

    arcs: tuple[int, ...]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_str(cls, s: str) -> Oid:
        """Parse a dotted-decimal OID string.

        Raises:
            ValueError: if the string is empty, contains empty arcs, has
                leading/trailing dots, negative arcs, whitespace, signs,
                underscores, or leading zeros on any arc.
        """
        if not s:
            raise ValueError("OID string must not be empty")
        parts = s.split(".")
        arcs: list[int] = []
        for part in parts:
            if not _ARC_RE.match(part):
                raise ValueError(f"Invalid OID arc {part!r} in {s!r}")
            arcs.append(int(part))
        return cls(arcs=tuple(arcs))

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return ".".join(str(a) for a in self.arcs)

    def __repr__(self) -> str:
        return f"Oid({'.'.join(str(a) for a in self.arcs)!r})"

    # ------------------------------------------------------------------
    # Subtree test
    # ------------------------------------------------------------------

    def in_subtree(self, root: Oid) -> bool:
        """Return True if this OID is equal to root or is a descendant of it.

        Uses arc-by-arc prefix comparison, so 1.3.6.10 is NOT in the subtree
        of 1.3.6.1 (they differ at the fourth arc: 10 ≠ 1).
        """
        n = len(root.arcs)
        return self.arcs[:n] == root.arcs
