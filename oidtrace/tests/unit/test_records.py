"""Tests for oidtrace.records — schema-validated record builders."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import jsonschema

from oidtrace.codec import Varbind
from oidtrace.oid import Oid
from oidtrace.records import (
    event_record,
    exchange_record,
    header_record,
    summary_record,
    system_info_record,
)
from oidtrace.vocab import Violation

# ---------------------------------------------------------------------------
# Helpers


def _valid(validator: jsonschema.Draft202012Validator, record: dict) -> None:
    """Assert record validates against the schema; pretty-print errors if not."""
    errors = list(validator.iter_errors(record))
    assert not errors, "\n".join(e.message for e in errors)


# ---------------------------------------------------------------------------
# header_record


def test_header_minimal(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = header_record(
        tool="oidtrace 0.1.0",
        started_at="2026-06-11T14:03:07Z",
        label=None,
        session_id="5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42",
        run=1,
        runs_total=1,
        snmp_version="2c",
        settings={
            "bulk_size": 10,
            "timeout_s": 2.0,
            "retries": 2,
            "start_oid": "1.3.6.1",
        },
    )
    _valid(record_validator, rec)
    assert rec["type"] == "header"
    assert rec["format_version"] == 1
    assert "label" not in rec  # omitted when None


def test_header_with_label(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = header_record(
        tool="oidtrace 0.1.0",
        started_at="2026-06-11T14:03:07Z",
        label="switch-floor3",
        session_id="5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42",
        run=2,
        runs_total=5,
        snmp_version="2c",
        settings={
            "bulk_size": 10,
            "timeout_s": 2.0,
            "retries": 2,
            "start_oid": "1.3.6.1",
        },
    )
    _valid(record_validator, rec)
    assert rec["label"] == "switch-floor3"
    assert rec["session"] == {
        "id": "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42",
        "run": 2,
        "runs_total": 5,
    }


# ---------------------------------------------------------------------------
# exchange_record


def _make_request() -> dict:
    return {
        "pdu": "getnext",
        "request_id": 42,
        "oids": ["1.3.6.1.2.1.1.1"],
    }


def _make_attempt(received_at: float | None = 1.5, error: str | None = None) -> dict:
    a: dict = {"sent_at": 1.0, "received_at": received_at}
    if error is not None:
        a["error"] = error
        a["received_at"] = None
    return a


def test_exchange_with_response_and_strays_and_violations(
    record_validator: jsonschema.Draft202012Validator,
) -> None:
    vb = Varbind(oid=Oid.from_str("1.3.6.1.2.1.1.1.0"), tag=0x04, value=b"SomeValue")
    rec = exchange_record(
        seq=1,
        request=_make_request(),
        attempts=[_make_attempt(received_at=1.5), _make_attempt(received_at=None)],
        response_fields={"request_id": 42, "error_status": 0, "error_index": 0},
        varbinds=[vb],
        strays=[{"received_at": 1.55}],
        violations=[Violation.REQUEST_ID_MISMATCH],
        malformed=None,
    )
    _valid(record_validator, rec)
    assert rec["type"] == "exchange"
    assert rec["seq"] == 1
    assert "response" in rec
    assert rec["response"]["varbinds"] == [
        {"oid": "1.3.6.1.2.1.1.1.0", "vtype": "OctetString", "vlen": 9}
    ]
    assert rec["stray_responses"] == [{"received_at": 1.55}]
    assert rec["violations"] == ["request-id-mismatch"]
    assert "malformed" not in rec


def test_exchange_attempt_with_icmp_error(
    record_validator: jsonschema.Draft202012Validator,
) -> None:
    rec = exchange_record(
        seq=2,
        request=_make_request(),
        attempts=[_make_attempt(received_at=None, error="icmp-port-unreachable")],
        response_fields=None,
        varbinds=[],
        strays=[],
        violations=[],
        malformed=None,
    )
    _valid(record_validator, rec)
    assert rec["attempts"][0]["error"] == "icmp-port-unreachable"
    assert rec["attempts"][0]["received_at"] is None
    assert "response" not in rec
    assert "stray_responses" not in rec
    assert "violations" not in rec
    assert "malformed" not in rec


def test_exchange_no_response(record_validator: jsonschema.Draft202012Validator) -> None:
    """Both response and malformed absent means every attempt timed out."""
    rec = exchange_record(
        seq=3,
        request=_make_request(),
        attempts=[_make_attempt(received_at=None)],
        response_fields=None,
        varbinds=[],
        strays=[],
        violations=[],
        malformed=None,
    )
    _valid(record_validator, rec)
    assert "response" not in rec
    assert "malformed" not in rec


def test_exchange_malformed(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = exchange_record(
        seq=4,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_fields=None,
        varbinds=[],
        strays=[],
        violations=["malformed-ber"],
        malformed={"error": "truncated BER", "length": 27},
    )
    _valid(record_validator, rec)
    assert rec["malformed"] == {"error": "truncated BER", "length": 27}
    assert "response" not in rec


# ---------------------------------------------------------------------------
# "No values" guarantee: bytes in Varbind never appear in JSON output


def test_exchange_varbind_value_not_serialized() -> None:
    secret = b"SECRET-VALUE"
    vb = Varbind(oid=Oid.from_str("1.3.6.1.2.1.1.1.0"), tag=0x04, value=secret)
    rec = exchange_record(
        seq=1,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_fields={"request_id": 1, "error_status": 0, "error_index": 0},
        varbinds=[vb],
        strays=[],
        violations=[],
        malformed=None,
    )
    serialized = json.dumps(rec)
    assert "SECRET-VALUE" not in serialized
    assert base64.b64encode(secret).decode() not in serialized
    assert secret.hex() not in serialized
    # varbind dict must be exactly oid/vtype/vlen — no value field
    vb_dict = rec["response"]["varbinds"][0]
    assert set(vb_dict.keys()) == {"oid", "vtype", "vlen"}
    assert vb_dict == {"oid": "1.3.6.1.2.1.1.1.0", "vtype": "OctetString", "vlen": 12}


# ---------------------------------------------------------------------------
# event_record


def test_event_without_detail(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = event_record(at=5.123, kind="walk-aborted-by-user")
    _valid(record_validator, rec)
    assert rec["type"] == "event"
    assert rec["at"] == 5.123
    assert rec["kind"] == "walk-aborted-by-user"
    assert "detail" not in rec


def test_event_with_detail(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = event_record(at=3.0, kind="oid-loop-detected", detail={"oid": "1.3.6.1.2.1.1.1.0"})
    _valid(record_validator, rec)
    assert rec["detail"] == {"oid": "1.3.6.1.2.1.1.1.0"}


# ---------------------------------------------------------------------------
# summary_record


def test_summary(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = summary_record(
        at=120.5,
        exchanges=1000,
        oids_seen=5000,
        end_reason="completed",
        violation_counts={"request-id-mismatch": 3, "oid-not-increasing": 1},
    )
    _valid(record_validator, rec)
    assert rec["type"] == "summary"
    assert rec["end_reason"] == "completed"
    assert rec["violation_counts"] == {"request-id-mismatch": 3, "oid-not-increasing": 1}


def test_summary_empty_violations(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = summary_record(
        at=10.0,
        exchanges=5,
        oids_seen=25,
        end_reason="unresponsive",
        violation_counts={},
    )
    _valid(record_validator, rec)


# ---------------------------------------------------------------------------
# system_info_record


def test_system_info(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = system_info_record(
        at=0.0412,
        point="start",
        values={
            "1.3.6.1.2.1.1.1.0": "Cisco IOS 15.2",
            "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.516",
            "1.3.6.1.2.1.1.3.0": 492711442,
        },
    )
    _valid(record_validator, rec)
    assert rec["type"] == "system_info"
    assert rec["point"] == "start"


def test_system_info_end(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = system_info_record(
        at=120.5,
        point="end",
        values={"1.3.6.1.2.1.1.3.0": 123456},
    )
    _valid(record_validator, rec)
    assert rec["point"] == "end"
