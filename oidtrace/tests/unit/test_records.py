"""Tests for oidtrace.records — record builders returning traceformat models.

Builders return pydantic models; we still validate their serialized form against
the JSON schema (belt and braces against codegen gaps).
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import jsonschema

from traceformat import TraceRecord, dump_record
from traceformat.models import Attempt, Malformed, Oid, Request, Settings, StrayResponse
from traceformat.vocab import EventKind, Violation

from oidtrace.codec import Varbind
from oidtrace.oid import Oid as OidtraceOid
from oidtrace.records import (
    event_record,
    exchange_record,
    header_record,
    summary_record,
    system_info_record,
)

# ---------------------------------------------------------------------------
# Helpers


def _valid(validator: jsonschema.Draft202012Validator, record: TraceRecord) -> dict[str, Any]:
    """Assert the record's serialized form validates against the schema.

    Returns the decoded JSON object for further field assertions.
    """
    obj: dict[str, Any] = json.loads(dump_record(record))
    errors = list(validator.iter_errors(obj))
    assert not errors, "\n".join(e.message for e in errors)
    return obj


def _make_settings() -> Settings:
    return Settings(
        bulk_size=10,
        timeout_s=2.0,
        retries=2,
        start_oid=Oid("1.3.6.1"),
    )


def _make_request() -> Request:
    return Request(pdu="getnext", request_id=42, oids=[Oid("1.3.6.1.2.1.1.1")])  # type: ignore[arg-type]


def _make_attempt(received_at: float | None = 1.5, error: str | None = None) -> Attempt:
    if error is not None:
        return Attempt(sent_at=1.0, received_at=received_at, error=error)  # type: ignore[arg-type]
    return Attempt(sent_at=1.0, received_at=received_at)  # type: ignore[arg-type]


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
        settings=_make_settings(),
    )
    obj = _valid(record_validator, rec)
    assert obj["type"] == "header"
    assert obj["format_version"] == 1
    assert "label" not in obj  # omitted when None


def test_header_with_label(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = header_record(
        tool="oidtrace 0.1.0",
        started_at="2026-06-11T14:03:07Z",
        label="switch-floor3",
        session_id="5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42",
        run=2,
        runs_total=5,
        snmp_version="2c",
        settings=_make_settings(),
    )
    obj = _valid(record_validator, rec)
    assert obj["label"] == "switch-floor3"
    assert obj["session"] == {
        "id": "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42",
        "run": 2,
        "runs_total": 5,
    }


# ---------------------------------------------------------------------------
# exchange_record


def test_exchange_with_response_and_strays_and_violations(
    record_validator: jsonschema.Draft202012Validator,
) -> None:
    vb = Varbind(oid=OidtraceOid.from_str("1.3.6.1.2.1.1.1.0"), tag=0x04, value=b"SomeValue")
    rec = exchange_record(
        seq=1,
        request=_make_request(),
        attempts=[_make_attempt(received_at=1.5), _make_attempt(received_at=None)],
        response_request_id=42,
        response_error_status=0,
        response_error_index=0,
        varbinds=[vb],
        strays=[StrayResponse(received_at=1.55)],  # type: ignore[arg-type]
        violations=[Violation.REQUEST_ID_MISMATCH],
        malformed=None,
    )
    obj = _valid(record_validator, rec)
    assert obj["type"] == "exchange"
    assert obj["seq"] == 1
    assert "response" in obj
    assert obj["response"]["varbinds"] == [
        {"oid": "1.3.6.1.2.1.1.1.0", "vtype": "OctetString", "vlen": 9}
    ]
    assert obj["stray_responses"] == [{"received_at": 1.55}]
    assert obj["violations"] == ["request-id-mismatch"]
    assert "malformed" not in obj


def test_exchange_attempt_with_icmp_error(
    record_validator: jsonschema.Draft202012Validator,
) -> None:
    rec = exchange_record(
        seq=2,
        request=_make_request(),
        attempts=[_make_attempt(received_at=None, error="icmp-port-unreachable")],
        response_request_id=None,
        response_error_status=None,
        response_error_index=None,
        varbinds=[],
        strays=[],
        violations=[],
        malformed=None,
    )
    obj = _valid(record_validator, rec)
    assert obj["attempts"][0]["error"] == "icmp-port-unreachable"
    assert obj["attempts"][0]["received_at"] is None
    assert "response" not in obj
    assert "stray_responses" not in obj
    assert "violations" not in obj
    assert "malformed" not in obj


def test_exchange_no_response(record_validator: jsonschema.Draft202012Validator) -> None:
    """Both response and malformed absent means every attempt timed out."""
    rec = exchange_record(
        seq=3,
        request=_make_request(),
        attempts=[_make_attempt(received_at=None)],
        response_request_id=None,
        response_error_status=None,
        response_error_index=None,
        varbinds=[],
        strays=[],
        violations=[],
        malformed=None,
    )
    obj = _valid(record_validator, rec)
    assert "response" not in obj
    assert "malformed" not in obj
    # required-but-nullable received_at must survive serialization as null
    assert obj["attempts"][0]["received_at"] is None


def test_exchange_malformed(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = exchange_record(
        seq=4,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_request_id=None,
        response_error_status=None,
        response_error_index=None,
        varbinds=[],
        strays=[],
        violations=[Violation.MALFORMED_BER],
        malformed=Malformed(error="truncated BER", length=27),
    )
    obj = _valid(record_validator, rec)
    assert obj["malformed"] == {"error": "truncated BER", "length": 27}
    assert "response" not in obj


# ---------------------------------------------------------------------------
# "No values" guarantee: bytes in Varbind never appear in JSON output


def test_exchange_varbind_value_not_serialized() -> None:
    secret = b"SECRET-VALUE"
    vb = Varbind(oid=OidtraceOid.from_str("1.3.6.1.2.1.1.1.0"), tag=0x04, value=secret)
    rec = exchange_record(
        seq=1,
        request=_make_request(),
        attempts=[_make_attempt()],
        response_request_id=1,
        response_error_status=0,
        response_error_index=0,
        varbinds=[vb],
        strays=[],
        violations=[],
        malformed=None,
    )
    serialized = dump_record(rec)
    assert "SECRET-VALUE" not in serialized
    assert base64.b64encode(secret).decode() not in serialized
    assert secret.hex() not in serialized
    # varbind dict must be exactly oid/vtype/vlen — no value field
    obj: dict[str, Any] = json.loads(serialized)
    vb_dict = obj["response"]["varbinds"][0]
    assert set(vb_dict.keys()) == {"oid", "vtype", "vlen"}
    assert vb_dict == {"oid": "1.3.6.1.2.1.1.1.0", "vtype": "OctetString", "vlen": 12}


# ---------------------------------------------------------------------------
# event_record


def test_event_without_detail(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = event_record(at=5.123, kind=EventKind.WALK_ABORTED_BY_USER)
    obj = _valid(record_validator, rec)
    assert obj["type"] == "event"
    assert obj["at"] == 5.123
    assert obj["kind"] == "walk-aborted-by-user"
    assert "detail" not in obj


def test_event_with_detail(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = event_record(
        at=3.0, kind=EventKind.OID_LOOP_DETECTED, detail={"oid": "1.3.6.1.2.1.1.1.0"}
    )
    obj = _valid(record_validator, rec)
    assert obj["detail"] == {"oid": "1.3.6.1.2.1.1.1.0"}


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
    obj = _valid(record_validator, rec)
    assert obj["type"] == "summary"
    assert obj["end_reason"] == "completed"
    assert obj["violation_counts"] == {"request-id-mismatch": 3, "oid-not-increasing": 1}


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
    obj = _valid(record_validator, rec)
    assert obj["type"] == "system_info"
    assert obj["point"] == "start"


def test_system_info_end(record_validator: jsonschema.Draft202012Validator) -> None:
    rec = system_info_record(
        at=120.5,
        point="end",
        values={"1.3.6.1.2.1.1.3.0": 123456},
    )
    obj = _valid(record_validator, rec)
    assert obj["point"] == "end"
