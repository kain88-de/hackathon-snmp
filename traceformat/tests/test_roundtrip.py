"""Tests for traceformat serialization helpers."""

from __future__ import annotations

import json
from typing import Any

from traceformat import Exchange, dump_record, parse_record

_REQUEST: dict[str, Any] = {
    "pdu": "getbulk",
    "request_id": 42,
    "oids": ["1.3.6.1.2.1.1"],
    "non_repeaters": 0,
    "max_repetitions": 10,
}


def test_received_at_none_serializes_as_null() -> None:
    """received_at is required-but-nullable: explicit None must appear as null."""
    rec = Exchange.model_validate(
        {
            "type": "exchange",
            "seq": 1,
            "request": _REQUEST,
            "attempts": [{"sent_at": 1.0, "received_at": None}],
        }
    )
    obj: dict[str, Any] = json.loads(dump_record(rec))
    assert "received_at" in obj["attempts"][0]
    assert obj["attempts"][0]["received_at"] is None


def test_optional_keys_omitted_when_unset() -> None:
    """Unset optional keys (label, response, ...) must not be serialized."""
    rec = Exchange.model_validate(
        {
            "type": "exchange",
            "seq": 1,
            "request": _REQUEST,
            "attempts": [{"sent_at": 1.0, "received_at": 1.5}],
        }
    )
    obj: dict[str, Any] = json.loads(dump_record(rec))
    assert "response" not in obj
    assert "stray_responses" not in obj
    assert "violations" not in obj
    assert "malformed" not in obj


def test_parse_dump_round_trip() -> None:
    rec = Exchange.model_validate(
        {
            "type": "exchange",
            "seq": 2,
            "request": _REQUEST,
            "attempts": [{"sent_at": 1.0, "received_at": 1.5}],
            "response": {
                "request_id": 42,
                "error_status": 0,
                "error_index": 0,
                "varbinds": [{"oid": "1.3.6.1.2.1.1.1.0", "vtype": "OctetString", "vlen": 9}],
            },
        }
    )
    assert parse_record(dump_record(rec)) == rec
