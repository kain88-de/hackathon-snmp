"""Tests for oidtrace.oid — Oid value type.

Contract coverage:
  - round-trip: Oid.from_str / str(oid)
  - tuple-based ordering (string comparison mis-orders 1.3.6.1.10 vs 1.3.6.1.2)
  - in_subtree: inside / outside / equal / sibling-prefix trap
  - bad inputs: ValueError on garbage (see Task-order trap #2)
  - equality / hash / repr
"""

from __future__ import annotations

import pytest

from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------


def test_round_trip_basic() -> None:
    assert str(Oid.from_str("1.3.6.1")) == "1.3.6.1"


def test_round_trip_single_arc() -> None:
    assert str(Oid.from_str("0")) == "0"


def test_round_trip_zero_zero() -> None:
    # "0.0" is a valid OID
    assert str(Oid.from_str("0.0")) == "0.0"


def test_round_trip_long() -> None:
    s = "1.3.6.1.2.1.1.1.0"
    assert str(Oid.from_str(s)) == s


# ---------------------------------------------------------------------------
# ordering — tuple comparison, not string comparison
# ---------------------------------------------------------------------------


def test_ordering_tuple_vs_string_pitfall() -> None:
    """String comparison mis-orders 1.3.6.1.10 vs 1.3.6.1.2; tuple ordering must be correct."""
    a = Oid.from_str("1.3.6.1.2")
    b = Oid.from_str("1.3.6.1.10")
    assert a < b, "1.3.6.1.2 must sort before 1.3.6.1.10 (numeric, not lexicographic)"


def test_ordering_equal() -> None:
    a = Oid.from_str("1.3.6.1")
    b = Oid.from_str("1.3.6.1")
    assert a == b
    assert not (a < b)
    assert not (a > b)


def test_ordering_longer_is_greater() -> None:
    parent = Oid.from_str("1.3.6")
    child = Oid.from_str("1.3.6.1")
    assert parent < child


def test_ordering_shorter_prefix_less() -> None:
    a = Oid.from_str("1.3.6.1")
    b = Oid.from_str("1.3.6.2")
    assert a < b


# ---------------------------------------------------------------------------
# in_subtree
# ---------------------------------------------------------------------------


def test_in_subtree_inside() -> None:
    root = Oid.from_str("1.3.6.1")
    child = Oid.from_str("1.3.6.1.2.1")
    assert child.in_subtree(root)


def test_in_subtree_equal() -> None:
    oid = Oid.from_str("1.3.6.1")
    assert oid.in_subtree(oid)


def test_in_subtree_outside() -> None:
    root = Oid.from_str("1.3.6.1")
    other = Oid.from_str("1.3.6.2")
    assert not other.in_subtree(root)


def test_in_subtree_sibling_prefix_trap() -> None:
    """1.3.6.10 is NOT in the subtree of 1.3.6.1 — numeric prefix check required."""
    root = Oid.from_str("1.3.6.1")
    sibling = Oid.from_str("1.3.6.10")
    assert not sibling.in_subtree(root)


def test_in_subtree_parent_not_in_child() -> None:
    root = Oid.from_str("1.3.6.1")
    child = Oid.from_str("1.3.6.1.2")
    assert not root.in_subtree(child)


# ---------------------------------------------------------------------------
# bad inputs — ValueError (trap #2: reject negatives, whitespace, signs,
# underscores, leading zeros; ASCII digits only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        "1.3.x",  # non-digit arc
        "1..3",  # empty arc
        ".1.3",  # leading dot
        "1.-3",  # negative arc
        " 1.3",  # leading whitespace
        "+1.3",  # leading plus
        "1_000",  # underscore (int() accepts this — must be rejected)
        "01",  # leading zero
        "1.03",  # leading zero in arc
        "1.3.",  # trailing dot
    ],
)
def test_from_str_bad_inputs(bad: str) -> None:
    with pytest.raises(ValueError):
        Oid.from_str(bad)


# ---------------------------------------------------------------------------
# equality / hash / repr
# ---------------------------------------------------------------------------


def test_equality() -> None:
    a = Oid.from_str("1.3.6.1")
    b = Oid.from_str("1.3.6.1")
    assert a == b


def test_inequality() -> None:
    a = Oid.from_str("1.3.6.1")
    b = Oid.from_str("1.3.6.2")
    assert a != b


def test_hash_equal_oids() -> None:
    a = Oid.from_str("1.3.6.1")
    b = Oid.from_str("1.3.6.1")
    assert hash(a) == hash(b)


def test_hashable_in_set() -> None:
    s = {Oid.from_str("1.3.6.1"), Oid.from_str("1.3.6.1"), Oid.from_str("1.3.6.2")}
    assert len(s) == 2


def test_repr_readable() -> None:
    oid = Oid.from_str("1.3.6.1")
    r = repr(oid)
    assert "1.3.6.1" in r
    # Should not just be the dataclass default with tuple repr
    assert "Oid" in r


def test_frozen_immutable() -> None:
    oid = Oid.from_str("1.3.6.1")
    with pytest.raises((AttributeError, TypeError)):
        oid.arcs = (1, 2, 3)  # type: ignore[misc]
