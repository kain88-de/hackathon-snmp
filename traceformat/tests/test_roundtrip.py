"""Round-trip and serialisation tests for dump_record / parse_record."""

from __future__ import annotations

import json

import pytest

from traceformat import (
    Event,
    Exchange,
    Header,
    Summary,
    SystemInfo,
    dump_record,
    parse_record,
)
from traceformat.models import (
    Attempt,
    Malformed,
    Oid,
    Pdu,
    Point,
    Reltime,
    Request,
    Response,
    Session,
    Settings,
    Snmp,
    Varbind,
    Version,
)

# ---------------------------------------------------------------------------
# Minimal fixture constructors
# ---------------------------------------------------------------------------

_SESSION = Session(id="session-uuid-1", run=1, runs_total=1)
_SNMP = Snmp(version=Version.field_2c)
_SETTINGS = Settings(
    bulk_size=10,
    timeout_s=1.0,
    retries=3,
    start_oid=Oid("1.3.6.1"),
)
_STARTED_AT = "2026-06-12T10:00:00+00:00"
_DEFAULT_RECEIVED_AT = Reltime(0.5)


def _minimal_header() -> Header:
    return Header(
        type="header",
        format_version=1,
        tool="test-tool",
        started_at=_STARTED_AT,  # type: ignore[arg-type]
        session=_SESSION,
        snmp=_SNMP,
        settings=_SETTINGS,
    )


def _minimal_system_info() -> SystemInfo:
    return SystemInfo(
        type="system_info",
        at=Reltime(0.0),
        point=Point.start,
        values={"1.3.6.1.2.1.1.1.0": "Linux"},
    )


def _minimal_exchange(received_at: Reltime | None = _DEFAULT_RECEIVED_AT) -> Exchange:
    return Exchange(
        type="exchange",
        seq=1,
        request=Request(
            pdu=Pdu.getbulk,
            request_id=42,
            oids=[Oid("1.3.6.1.2.1")],
            non_repeaters=0,
            max_repetitions=10,
        ),
        attempts=[Attempt(sent_at=Reltime(0.1), received_at=received_at)],
    )


def _minimal_event() -> Event:
    return Event(
        type="event",
        at=Reltime(1.0),
        kind="walk-aborted-by-user",
    )


def _minimal_summary() -> Summary:
    return Summary(
        type="summary",
        at=Reltime(2.0),
        exchanges=5,
        oids_seen=42,
        end_reason="completed",
        violation_counts={},
    )


# ---------------------------------------------------------------------------
# required-but-nullable: received_at=None → "received_at":null in JSON
# ---------------------------------------------------------------------------


def test_received_at_none_serializes_as_null() -> None:
    exchange = _minimal_exchange(received_at=None)
    serialized = dump_record(exchange)
    data = json.loads(serialized)
    attempt = data["attempts"][0]
    assert "received_at" in attempt
    assert attempt["received_at"] is None


# ---------------------------------------------------------------------------
# unset optional: label never set → absent from JSON
# ---------------------------------------------------------------------------


def test_unset_optional_label_absent() -> None:
    header = _minimal_header()
    serialized = dump_record(header)
    data = json.loads(serialized)
    assert "label" not in data


def test_set_optional_label_present() -> None:
    header = _minimal_header()
    header = header.model_copy(update={"label": "my-label"})
    serialized = dump_record(header)
    data = json.loads(serialized)
    assert data["label"] == "my-label"


# ---------------------------------------------------------------------------
# Round-trip: parse_record(dump_record(r)) == r for one of each type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "record",
    [
        _minimal_header(),
        _minimal_system_info(),
        _minimal_exchange(),
        _minimal_event(),
        _minimal_summary(),
    ],
    ids=["header", "system_info", "exchange", "event", "summary"],
)
def test_roundtrip(record: Header | SystemInfo | Exchange | Event | Summary) -> None:
    assert parse_record(dump_record(record)) == record


# ---------------------------------------------------------------------------
# parse_record ignores unknown extra fields
# ---------------------------------------------------------------------------


def test_parse_ignores_extra_fields() -> None:
    header = _minimal_header()
    data = json.loads(dump_record(header))
    data["bogus_extra_field"] = "should be ignored"
    result = parse_record(json.dumps(data))
    assert isinstance(result, Header)
    assert result.tool == header.tool
    assert result.session == header.session


# ---------------------------------------------------------------------------
# Exchange with non-trivial optional fields set → round-trips correctly
# ---------------------------------------------------------------------------


def test_exchange_with_response_roundtrip() -> None:
    exchange = Exchange(
        type="exchange",
        seq=2,
        request=Request(
            pdu=Pdu.getnext,
            request_id=99,
            oids=[Oid("1.3.6.1.2.1.1")],
        ),
        attempts=[Attempt(sent_at=Reltime(0.2), received_at=Reltime(0.3))],
        response=Response(
            request_id=99,
            error_status=0,
            error_index=0,
            varbinds=[Varbind(oid=Oid("1.3.6.1.2.1.1.1.0"), vtype="OctetString", vlen=12)],
        ),
        violations=["request-id-mismatch"],
        malformed=Malformed(error="bad-ber", length=10),
    )
    assert parse_record(dump_record(exchange)) == exchange
