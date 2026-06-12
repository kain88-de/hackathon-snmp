"""Wire-string identity tests for all producer-side vocabulary enums."""

import json

import pytest

from traceformat.vocab import AttemptError, EndReason, EventKind, Violation


@pytest.mark.parametrize("member", list(Violation))
def test_violation_wire_string(member: Violation) -> None:
    assert str(member) == member.value
    assert json.dumps(member) == f'"{member.value}"'


@pytest.mark.parametrize("member", list(EndReason))
def test_end_reason_wire_string(member: EndReason) -> None:
    assert str(member) == member.value
    assert json.dumps(member) == f'"{member.value}"'


@pytest.mark.parametrize("member", list(EventKind))
def test_event_kind_wire_string(member: EventKind) -> None:
    assert str(member) == member.value
    assert json.dumps(member) == f'"{member.value}"'


@pytest.mark.parametrize("member", list(AttemptError))
def test_attempt_error_wire_string(member: AttemptError) -> None:
    assert str(member) == member.value
    assert json.dumps(member) == f'"{member.value}"'
