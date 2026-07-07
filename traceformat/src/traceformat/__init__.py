"""Shared trace-format types: pydantic models, vocabulary enums, and serialisation helpers."""

from __future__ import annotations

from pydantic import TypeAdapter

from ._validators import TraceFormatViolationError, check_invariants
from .models import Event, Exchange, Header, Summary, SystemInfo

TraceRecord = Header | SystemInfo | Exchange | Event | Summary

_adapter: TypeAdapter[TraceRecord] = TypeAdapter(TraceRecord)

__all__ = [
    "Event",
    "Exchange",
    "Header",
    "Summary",
    "SystemInfo",
    "TraceFormatViolationError",
    "TraceRecord",
    "dump_record",
    "parse_record",
]


def dump_record(record: TraceRecord) -> str:
    """Compact JSON via ``exclude_unset`` — never ``exclude_none``.

    Optional *keys* (``label``, ``response``, ``malformed`` …) must be absent from the
    JSON when unset, while required-but-nullable fields (``attempts[].received_at``)
    must still serialize as explicit ``null``. Only ``exclude_unset`` preserves both.
    """
    return record.model_dump_json(exclude_unset=True)


def parse_record(line: str) -> TraceRecord:
    """Validate one JSON line, enforcing invariants the schema encodes but the
    generated models can't translate (see ``_validators``).

    Guarantees ``parse_record(dump_record(r)) == r`` for any ``TraceRecord`` ``r``.
    """
    record = _adapter.validate_json(line)
    check_invariants(record)
    return record
