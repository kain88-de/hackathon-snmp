"""Shared OID trace format types.

The pydantic models in :mod:`traceformat.models` are generated from
``docs/trace-format.schema.json`` (never hand-edited). This module provides the
hand-written ``TraceRecord`` union over the five record models, plus
serialization helpers that respect the format's distinction between optional
*keys* and required-but-nullable fields.
"""

from __future__ import annotations

from pydantic import TypeAdapter

from traceformat.models import Event, Exchange, Header, Summary, SystemInfo

TraceRecord = Header | SystemInfo | Exchange | Event | Summary

_ADAPTER: TypeAdapter[TraceRecord] = TypeAdapter(TraceRecord)


def dump_record(record: TraceRecord) -> str:
    """Serialize one record to a compact JSON line.

    Uses ``exclude_unset`` (not ``exclude_none``): optional keys that were never
    set (label, response, ...) are omitted, while a field that is required but
    nullable and explicitly set to ``None`` (``attempts[].received_at``) is
    serialized as ``null``.
    """
    return record.model_dump_json(exclude_unset=True)


def parse_record(line: str) -> TraceRecord:
    """Parse one JSON line into the matching trace record model."""
    return _ADAPTER.validate_json(line)


__all__ = [
    "Event",
    "Exchange",
    "Header",
    "Summary",
    "SystemInfo",
    "TraceRecord",
    "dump_record",
    "parse_record",
]
