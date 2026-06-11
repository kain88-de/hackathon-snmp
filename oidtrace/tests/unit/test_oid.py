"""Tests for oidtrace.oid — the core OID value type."""

import pytest

from oidtrace.oid import Oid


def test_parse_format_round_trip() -> None:
    s = "1.3.6.1.2.1"
    assert str(Oid.from_str(s)) == s


def test_tuple_ordering_beats_string_ordering() -> None:
    # "1.3.6.1.10" < "1.3.6.1.2" lexicographically as strings, but
    # as ordered dataclass over arcs the order is correct.
    assert Oid.from_str("1.3.6.1.2") < Oid.from_str("1.3.6.1.10")


def test_in_subtree_inside() -> None:
    root = Oid.from_str("1.3.6.1")
    oid = Oid.from_str("1.3.6.1.2.1")
    assert oid.in_subtree(root)


def test_in_subtree_outside() -> None:
    root = Oid.from_str("1.3.6.1")
    oid = Oid.from_str("1.3.7")
    assert not oid.in_subtree(root)


def test_in_subtree_equal_to_root() -> None:
    root = Oid.from_str("1.3.6.1")
    assert root.in_subtree(root)


def test_in_subtree_sibling_prefix_is_not_inside() -> None:
    # 1.3.6.10 shares the prefix "1.3.6.1" as a string but is a sibling, not a child
    assert not Oid.from_str("1.3.6.10").in_subtree(Oid.from_str("1.3.6.1"))


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "1.3.x",
        "1..3",
        ".1.3",
        "1.-3",
        " 1.3",
        "+1.3",
        "1_000",
        "01",
    ],
)
def test_parse_rejects_bad_input(bad: str) -> None:
    with pytest.raises(ValueError):
        Oid.from_str(bad)


def test_parse_zero_arcs() -> None:
    assert Oid.from_str("0.0").arcs == (0, 0)


def test_equality() -> None:
    assert Oid.from_str("1.3.6.1") == Oid.from_str("1.3.6.1")
    assert Oid.from_str("1.3.6.1") != Oid.from_str("1.3.6.2")


def test_hashable() -> None:
    oids = {Oid.from_str("1.3.6.1"), Oid.from_str("1.3.6.1"), Oid.from_str("1.3.6.2")}
    assert len(oids) == 2


def test_repr_readable() -> None:
    oid = Oid.from_str("1.3.6.1")
    assert repr(oid) == "Oid('1.3.6.1')"
