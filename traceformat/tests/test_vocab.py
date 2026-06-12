"""Tests for traceformat.vocab — StrEnum vocabularies."""

from __future__ import annotations

import json

import pytest

from traceformat.vocab import AttemptError, EndReason, EventKind, Violation

_ALL_MEMBERS = [*Violation, *EndReason, *EventKind, *AttemptError]


@pytest.mark.parametrize("member", _ALL_MEMBERS, ids=lambda m: f"{type(m).__name__}.{m.name}")
def test_str_equals_value(member: Violation | EndReason | EventKind | AttemptError) -> None:
    assert str(member) == member.value


@pytest.mark.parametrize("member", _ALL_MEMBERS, ids=lambda m: f"{type(m).__name__}.{m.name}")
def test_json_serializes_as_wire_string(
    member: Violation | EndReason | EventKind | AttemptError,
) -> None:
    assert json.dumps(member) == f'"{member.value}"'
