"""Tests for oidtrace.oid — the core OID value type."""

import pytest

from oidtrace.oid import Oid, format_oid, in_subtree, parse_oid


def test_parse_format_round_trip() -> None:
    s = "1.3.6.1.2.1"
    assert format_oid(parse_oid(s)) == s


def test_tuple_ordering_beats_string_ordering() -> None:
    # "1.3.6.1.10" < "1.3.6.1.2" lexicographically as strings, but
    # as tuples of ints the order is correct.
    assert parse_oid("1.3.6.1.2") < parse_oid("1.3.6.1.10")


def test_in_subtree_inside() -> None:
    root: Oid = (1, 3, 6, 1)
    oid: Oid = (1, 3, 6, 1, 2, 1)
    assert in_subtree(root, oid)


def test_in_subtree_outside() -> None:
    root: Oid = (1, 3, 6, 1)
    oid: Oid = (1, 3, 7)
    assert not in_subtree(root, oid)


def test_in_subtree_equal_to_root() -> None:
    root: Oid = (1, 3, 6, 1)
    assert in_subtree(root, root)


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
        parse_oid(bad)


def test_parse_zero_arcs() -> None:
    assert parse_oid("0.0") == (0, 0)
