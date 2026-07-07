"""Schema-parity tests: jsonschema and parse_record must agree on every fixture.

datamodel-code-generator does not translate the JSON Schema `not`/`if-then-else`
keywords into pydantic validators, so four real invariants in
trace-format.schema.json are silently absent from models.py. These tests prove
traceformat.parse_record enforces what the schema enforces at the wire boundary —
fixtures are raw JSON strings, not model constructions, since some invalid shapes
(e.g. an exchange with both response and malformed) construct just fine today.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from pydantic import ValidationError

from traceformat import TraceFormatViolationError, parse_record

_SCHEMA = json.loads((Path(__file__).parents[1] / "trace-format.schema.json").read_text())
_VALIDATOR = validator_for(_SCHEMA)(_SCHEMA)

_MINIMAL_HEADER: dict[str, Any] = {
    "type": "header",
    "format_version": 1,
    "tool": "test-tool",
    "started_at": "2026-06-12T10:00:00+00:00",
    "session": {"id": "session-uuid-1", "run": 1, "runs_total": 1},
    "snmp": {"version": "2c"},
    "settings": {"bulk_size": 10, "timeout_s": 1.0, "retries": 3, "start_oid": "1.3.6.1"},
}

_MINIMAL_SYSTEM_INFO: dict[str, Any] = {
    "type": "system_info",
    "at": 0.0,
    "point": "start",
    "values": {"1.3.6.1.2.1.1.1.0": "Linux"},
}


def _exchange(
    request: dict[str, Any] | None = None,
    attempts: list[dict[str, Any] | None] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A minimal valid exchange, with just the parts a test case cares about swapped in."""
    if request is None:
        request = {"pdu": "get", "request_id": 1, "oids": ["1.3.6.1"]}
    if attempts is None:
        attempts = [{"sent_at": 0.1, "received_at": 0.2}]
    return {"type": "exchange", "seq": 1, "request": request, "attempts": attempts, **extra}


_MINIMAL_EXCHANGE: dict[str, Any] = _exchange()

_MINIMAL_EVENT: dict[str, Any] = {"type": "event", "at": 1.0, "kind": "walk-aborted-by-user"}

_MINIMAL_SUMMARY: dict[str, Any] = {
    "type": "summary",
    "at": 2.0,
    "exchanges": 5,
    "oids_seen": 42,
    "end_reason": "completed",
    "violation_counts": {},
}

# One row per case: the fixture, then whether it should be accepted by BOTH jsonschema
# and parse_record (the two must always agree — see module docstring). `id=` names the
# invariant under test; look there first when a row fails.
_CASES = [
    pytest.param(_MINIMAL_HEADER, True, id="header-minimal"),
    pytest.param(
        {**_MINIMAL_HEADER, "snmp": {"version": "3"}}, True, id="header-snmp-v3-sanctioned"
    ),
    pytest.param(_MINIMAL_SYSTEM_INFO, True, id="system-info-minimal"),
    pytest.param(_MINIMAL_EVENT, True, id="event-minimal"),
    pytest.param(_MINIMAL_SUMMARY, True, id="summary-minimal"),
    pytest.param(_MINIMAL_EXCHANGE, True, id="exchange-minimal"),
    pytest.param(
        _exchange(request={"pdu": "discovery", "request_id": 1, "oids": []}),
        True,
        id="exchange-discovery-sanctioned",
    ),
    pytest.param(
        _exchange(
            response={"request_id": 1, "error_status": 0, "error_index": 0, "varbinds": []},
            malformed={"error": "bad-ber"},
        ),
        False,
        id="exchange-response-and-malformed-rejected",
    ),
    pytest.param(
        _exchange(request={"pdu": "getbulk", "request_id": 1, "oids": ["1.3.6.1"]}),
        False,
        id="exchange-getbulk-missing-repetition-fields-rejected",
    ),
    pytest.param(
        _exchange(
            request={
                "pdu": "getbulk",
                "request_id": 1,
                "oids": ["1.3.6.1"],
                "non_repeaters": 0,
                "max_repetitions": 10,
            }
        ),
        True,
        id="exchange-getbulk-with-repetition-fields-accepted",
    ),
    pytest.param(
        _exchange(attempts=[{"sent_at": 0.1, "received_at": 0.2, "error": "send-failed"}]),
        False,
        id="exchange-attempt-error-with-received-at-rejected",
    ),
    pytest.param(
        _exchange(attempts=[{"sent_at": 0.1, "received_at": None, "error": "send-failed"}]),
        True,
        id="exchange-attempt-error-with-null-received-at-accepted",
    ),
    pytest.param(
        {**_MINIMAL_SUMMARY, "violation_counts": {"oid-not-increasing": -1}},
        False,
        id="summary-negative-violation-count-rejected",
    ),
    pytest.param(
        {
            **_MINIMAL_SUMMARY,
            "violation_counts": {"oid-not-increasing": 2, "duplicate-response": 1},
        },
        True,
        id="summary-multiple-violation-counts-accepted",
    ),
]


def _schema_valid(data: dict[str, Any]) -> bool:
    return _VALIDATOR.is_valid(data)


def _parse_valid(line: str) -> bool:
    try:
        parse_record(line)
    except (ValidationError, TraceFormatViolationError):
        return False
    return True


@pytest.mark.parametrize("data,expected_valid", _CASES)
def test_schema_and_parse_record_agree(data: dict[str, Any], expected_valid: bool) -> None:
    line = json.dumps(data)
    assert _schema_valid(data) is expected_valid
    assert _parse_valid(line) is expected_valid
