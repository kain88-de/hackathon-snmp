"""Shared trace-format types: pydantic models, vocabulary enums, and serialisation helpers."""

from __future__ import annotations

from pydantic import TypeAdapter

from .models import Event, Exchange, Header, Summary, SystemInfo

TraceRecord = Header | SystemInfo | Exchange | Event | Summary

_adapter: TypeAdapter[TraceRecord] = TypeAdapter(TraceRecord)

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


def dump_record(record: TraceRecord) -> str:
    return record.model_dump_json(exclude_unset=True)


def parse_record(line: str) -> TraceRecord:
    return _adapter.validate_json(line)
