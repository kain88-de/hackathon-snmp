"""Tests for records.py — record builder functions.

Every builder output:
  1. Is a traceformat model instance (Header, Exchange, Event, Summary, SystemInfo)
  2. Schema-validates via JSON round-trip against the canonical trace-format schema
  3. Contains no Varbind.value bytes (the secret-value leak test)

Additional invariants tested:
  - Conditional keys stay absent (UNSET) when not provided
  - response + malformed are mutually exclusive (enforced by builder interface)
  - Malformed carries {error, length}
  - Stray responses, violations, and attempt errors serialize correctly
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pydantic
import pytest
from traceformat import dump_record
from traceformat import models as tf
from traceformat.vocab import EndReason, EventKind, Violation

from oidtrace.codec import Varbind
from oidtrace.oid import Oid
from oidtrace.records import (
    event_record,
    exchange_record,
    header_record,
    summary_record,
    system_info_record,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    # pyrefly: ignore [untyped-import]
    from jsonschema import Draft202012Validator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STARTED_AT = datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)
_SETTINGS = tf.Settings(
    bulk_size=10,
    timeout_s=2.0,
    retries=2,
    start_oid=tf.Oid("1.3.6.1"),
)


def _validate(
    record_obj: tf.Header | tf.SystemInfo | tf.Exchange | tf.Event | tf.Summary,
    validator: Draft202012Validator,
) -> None:
    """Dump a record to JSON, parse it back, and schema-validate."""
    raw = dump_record(record_obj)
    data = json.loads(raw)
    errors = list(validator.iter_errors(data))
    assert errors == [], f"Schema validation errors: {errors}"


def _make_request(*, request_id: int = 1, oid: str = "1.3.6.1") -> tf.Request:
    return tf.Request(
        pdu=tf.Pdu.getbulk,
        request_id=request_id,
        oids=[tf.Oid(oid)],
        non_repeaters=0,
        max_repetitions=10,
    )


def _make_attempt(*, sent_at: float = 0.1, received_at: float | None = 0.15) -> tf.Attempt:
    return tf.Attempt(
        sent_at=tf.Reltime(sent_at),
        received_at=tf.Reltime(received_at) if received_at is not None else None,
    )


def _vb(oid_str: str, tag: int = 0x04, value: bytes = b"sysDescr value") -> Varbind:
    return Varbind(oid=Oid.from_str(oid_str), tag=tag, value=value)


# ---------------------------------------------------------------------------
# header_record
# ---------------------------------------------------------------------------


def test_header_record_schema_validates(record_validator: Draft202012Validator) -> None:
    r = header_record(
        tool="oidtrace/0.1.0",
        started_at=_STARTED_AT,
        label="lab-device",
        session_id="550e8400-e29b-41d4-a716-446655440000",
        run=1,
        runs_total=1,
        snmp_version="2c",
        settings=_SETTINGS,
    )
    _validate(r, record_validator)


def test_header_record_snmp_version_3(record_validator: Draft202012Validator) -> None:
    """header_record should accept snmp_version="3" and set Version.field_3."""
    r = header_record(
        tool="oidtrace/0.1.0",
        started_at=_STARTED_AT,
        label="lab-device",
        session_id="550e8400-e29b-41d4-a716-446655440000",
        run=1,
        runs_total=1,
        snmp_version="3",
        settings=_SETTINGS,
    )
    assert r.snmp.version.value == "3"
    _validate(r, record_validator)


def test_header_record_type_is_header() -> None:
    r = header_record(
        tool="oidtrace/0.1.0",
        started_at=_STARTED_AT,
        label=None,
        session_id="550e8400-e29b-41d4-a716-446655440000",
        run=1,
        runs_total=1,
        snmp_version="2c",
        settings=_SETTINGS,
    )
    assert isinstance(r, tf.Header)
    assert r.type == "header"
    assert r.format_version == 1


def test_header_record_no_label_key_absent(record_validator: Draft202012Validator) -> None:
    r = header_record(
        tool="oidtrace/0.1.0",
        started_at=_STARTED_AT,
        label=None,
        session_id="550e8400-e29b-41d4-a716-446655440000",
        run=1,
        runs_total=1,
        snmp_version="2c",
        settings=_SETTINGS,
    )
    raw = dump_record(r)
    data = json.loads(raw)
    # label must be absent (not null) when not provided
    assert "label" not in data
    _validate(r, record_validator)


# ---------------------------------------------------------------------------
# exchange_record — with response
# ---------------------------------------------------------------------------


def test_exchange_with_response_schema_validates(record_validator: Draft202012Validator) -> None:
    vbs = [_vb("1.3.6.1.2.1.1.1.0"), _vb("1.3.6.1.2.1.1.2.0")]
    r = exchange_record(
        seq=1,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_request_id=1,
        response_error_status=0,
        response_error_index=0,
        varbinds=vbs,
        strays=[],
        violations=[],
        malformed=None,
    )
    _validate(r, record_validator)


def test_exchange_with_stray_and_violation(record_validator: Draft202012Validator) -> None:
    """Exchange with a stray response and a violation serializes correctly."""
    stray = tf.StrayResponse(received_at=tf.Reltime(0.05))
    vbs = [_vb("1.3.6.1.2.1.1.1.0")]
    r = exchange_record(
        seq=2,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_request_id=99,  # mismatched
        response_error_status=0,
        response_error_index=0,
        varbinds=vbs,
        strays=[stray],
        violations=[Violation.REQUEST_ID_MISMATCH],
        malformed=None,
    )
    _validate(r, record_validator)
    raw = dump_record(r)
    data = json.loads(raw)
    assert data["violations"] == ["request-id-mismatch"]
    assert len(data["stray_responses"]) == 1


def test_exchange_without_response_no_response_key(record_validator: Draft202012Validator) -> None:
    """Exchange where all attempts timed out — no response or malformed."""
    attempt_no_recv = tf.Attempt(sent_at=tf.Reltime(0.1), received_at=None)
    r = exchange_record(
        seq=3,
        request=_make_request(),
        attempts=[attempt_no_recv],
        response_request_id=None,
        response_error_status=None,
        response_error_index=None,
        varbinds=[],
        strays=[],
        violations=[],
        malformed=None,
    )
    raw = dump_record(r)
    data = json.loads(raw)
    # response key must be absent, not null
    assert "response" not in data
    assert "malformed" not in data
    _validate(r, record_validator)


def test_exchange_with_malformed_carries_error_and_length(
    record_validator: Draft202012Validator,
) -> None:
    """Malformed response carries error string and length."""
    malformed = tf.Malformed(error="truncated BER", length=7)
    attempt_no_recv = tf.Attempt(sent_at=tf.Reltime(0.1), received_at=None)
    r = exchange_record(
        seq=4,
        request=_make_request(),
        attempts=[attempt_no_recv],
        response_request_id=None,
        response_error_status=None,
        response_error_index=None,
        varbinds=[],
        strays=[],
        violations=[Violation.MALFORMED_BER],
        malformed=malformed,
    )
    raw = dump_record(r)
    data = json.loads(raw)
    assert "response" not in data
    assert data["malformed"]["error"] == "truncated BER"
    assert data["malformed"]["length"] == 7
    _validate(r, record_validator)


def test_exchange_attempt_with_error(record_validator: Draft202012Validator) -> None:
    """Attempt with an error field (ICMP) — received_at is null."""
    attempt_err = tf.Attempt(
        sent_at=tf.Reltime(0.1),
        received_at=None,
        error="icmp-port-unreachable",
    )
    r = exchange_record(
        seq=5,
        request=_make_request(),
        attempts=[attempt_err],
        response_request_id=None,
        response_error_status=None,
        response_error_index=None,
        varbinds=[],
        strays=[],
        violations=[],
        malformed=None,
    )
    _validate(r, record_validator)
    raw = dump_record(r)
    data = json.loads(raw)
    assert data["attempts"][0]["error"] == "icmp-port-unreachable"
    assert data["attempts"][0]["received_at"] is None


# ---------------------------------------------------------------------------
# SECRET-VALUE leak test
# ---------------------------------------------------------------------------


def test_varbind_value_never_reaches_serialized_output(
    record_validator: Draft202012Validator,
) -> None:
    """Varbind.value bytes must NEVER appear in serialized output.

    The varbind dict must have exactly the keys {oid, vtype, vlen}.
    The raw value bytes, their base64, and their hex encoding must not appear.
    """
    secret = b"SECRET-VALUE"
    secret_b64 = base64.b64encode(secret).decode()
    secret_hex = secret.hex()

    vbs = [Varbind(oid=Oid.from_str("1.3.6.1.2.1.1.1.0"), tag=0x04, value=secret)]
    r = exchange_record(
        seq=1,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_request_id=1,
        response_error_status=0,
        response_error_index=0,
        varbinds=vbs,
        strays=[],
        violations=[],
        malformed=None,
    )
    raw = dump_record(r)

    # The raw secret must not appear
    assert "SECRET-VALUE" not in raw
    # Base64-encoded secret must not appear
    assert secret_b64 not in raw
    # Hex-encoded secret must not appear
    assert secret_hex not in raw

    # Varbind dict must have exactly {oid, vtype, vlen}
    data = json.loads(raw)
    varbind_keys = set(data["response"]["varbinds"][0].keys())
    assert varbind_keys == {"oid", "vtype", "vlen"}

    _validate(r, record_validator)


# ---------------------------------------------------------------------------
# exchange_record validates at construction (pydantic, not model_construct)
# ---------------------------------------------------------------------------


def test_exchange_record_negative_seq_raises_validation_error() -> None:
    """seq < 1 must raise pydantic.ValidationError at construction."""
    with pytest.raises(pydantic.ValidationError):
        exchange_record(
            seq=-5,
            request=_make_request(),
            attempts=[_make_attempt()],
            response_request_id=1,
            response_error_status=0,
            response_error_index=0,
            varbinds=[],
            strays=[],
            violations=[],
            malformed=None,
        )


def test_exchange_record_empty_attempts_raises_validation_error() -> None:
    """attempts=[] violates min_length=1 and must raise pydantic.ValidationError."""
    with pytest.raises(pydantic.ValidationError):
        exchange_record(
            seq=1,
            request=_make_request(),
            attempts=[],
            response_request_id=None,
            response_error_status=None,
            response_error_index=None,
            varbinds=[],
            strays=[],
            violations=[],
            malformed=None,
        )


# ---------------------------------------------------------------------------
# response + malformed mutual exclusion (interface-level)
# ---------------------------------------------------------------------------


def test_response_and_malformed_cannot_be_constructed_simultaneously() -> None:
    """The exchange_record builder cannot produce response+malformed together.

    When malformed is provided, response_request_id must be None (no response).
    When response_request_id is set, malformed must be None.
    This documents the None-gating: the builder only builds a response when
    response_request_id is not None, and only includes malformed when not None.
    If both were non-None, the schema's 'not required [response, malformed]'
    constraint would be violated — so we verify that is impossible via the builder.
    """
    malformed = tf.Malformed(error="bad bytes", length=5)
    # Passing both non-None triggers the mutual-exclusion guard
    with pytest.raises(ValueError, match="mutually exclusive"):
        exchange_record(
            seq=1,
            request=_make_request(),
            attempts=[_make_attempt()],
            response_request_id=1,  # response provided
            response_error_status=0,
            response_error_index=0,
            varbinds=[],
            strays=[],
            violations=[],
            malformed=malformed,  # and malformed provided
        )


# ---------------------------------------------------------------------------
# event_record
# ---------------------------------------------------------------------------


def test_event_record_schema_validates(record_validator: Draft202012Validator) -> None:
    r = event_record(at=1.5, kind=EventKind.OID_LOOP_DETECTED)
    _validate(r, record_validator)


def test_event_record_with_detail(record_validator: Draft202012Validator) -> None:
    r = event_record(at=2.0, kind=EventKind.TIME_BUDGET_EXCEEDED, detail={"budget_s": 30.0})
    _validate(r, record_validator)
    raw = dump_record(r)
    data = json.loads(raw)
    assert data["detail"] == {"budget_s": 30.0}


def test_event_record_no_detail_key_absent(record_validator: Draft202012Validator) -> None:
    r = event_record(at=0.5, kind=EventKind.WALK_ABORTED_BY_USER)
    raw = dump_record(r)
    data = json.loads(raw)
    assert "detail" not in data
    _validate(r, record_validator)


# ---------------------------------------------------------------------------
# summary_record
# ---------------------------------------------------------------------------


def test_summary_record_schema_validates(record_validator: Draft202012Validator) -> None:
    violation_counts: Mapping[Violation, int] = {Violation.REQUEST_ID_MISMATCH: 2}
    r = summary_record(
        at=10.5,
        exchanges=42,
        oids_seen=100,
        end_reason=EndReason.COMPLETED,
        violation_counts=violation_counts,
    )
    _validate(r, record_validator)


def test_summary_record_violation_counts_use_wire_strings(
    record_validator: Draft202012Validator,
) -> None:
    violation_counts: Mapping[Violation, int] = {
        Violation.OID_NOT_INCREASING: 3,
        Violation.DUPLICATE_RESPONSE: 1,
    }
    r = summary_record(
        at=5.0,
        exchanges=10,
        oids_seen=50,
        end_reason=EndReason.OID_LOOP,
        violation_counts=violation_counts,
    )
    raw = dump_record(r)
    data = json.loads(raw)
    # Keys must be the StrEnum wire strings
    assert data["violation_counts"] == {"oid-not-increasing": 3, "duplicate-response": 1}
    _validate(r, record_validator)


def test_summary_record_empty_violation_counts(record_validator: Draft202012Validator) -> None:
    r = summary_record(
        at=1.0,
        exchanges=5,
        oids_seen=20,
        end_reason=EndReason.UNRESPONSIVE,
        violation_counts={},
    )
    _validate(r, record_validator)


# ---------------------------------------------------------------------------
# system_info_record
# ---------------------------------------------------------------------------


def test_system_info_record_schema_validates(record_validator: Draft202012Validator) -> None:
    values: dict[str, str | int] = {
        "1.3.6.1.2.1.1.1.0": "Linux router 5.15",
        "1.3.6.1.2.1.1.5.0": "my-router",
    }
    r = system_info_record(at=0.1, point="start", values=values)
    _validate(r, record_validator)
