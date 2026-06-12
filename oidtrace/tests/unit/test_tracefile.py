"""Tests for tracefile.py — gzip-JSONL I/O.

Contract:
  - TraceWriter(path): context manager; write(record) appends one JSON line + flush
  - read_trace(path): yields validated TraceRecord instances; stops quietly at truncation
  - A complete line that fails pydantic validation raises (our own bug, not tolerance)
  - Ctrl-C durability: after write() WITHOUT close(), the record is already readable
"""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pydantic
import pytest
from traceformat import Header, Summary, dump_record, parse_record

if TYPE_CHECKING:
    from pathlib import Path
from traceformat.models import (
    Oid,
    Reltime,
    Session,
    Settings,
    Snmp,
    Version,
)

from oidtrace.tracefile import TraceWriter, read_trace

# ---------------------------------------------------------------------------
# Minimal record constructors
# ---------------------------------------------------------------------------

_SESSION = Session(id="session-uuid-1", run=1, runs_total=1)
_SNMP = Snmp(version=Version.field_2c)
_SETTINGS = Settings(
    bulk_size=10,
    timeout_s=1.0,
    retries=3,
    start_oid=Oid("1.3.6.1"),
)


def _header() -> Header:
    return Header(
        type="header",
        format_version=1,
        tool="test-tool",
        started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
        session=_SESSION,
        snmp=_SNMP,
        settings=_SETTINGS,
    )


def _summary() -> Summary:
    return Summary(
        type="summary",
        at=Reltime(2.0),
        exchanges=5,
        oids_seen=42,
        end_reason="completed",
        violation_counts={},
    )


# ---------------------------------------------------------------------------
# Round-trip: write then read preserves order and equality
# ---------------------------------------------------------------------------


def test_roundtrip_header_then_summary(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    header = _header()
    summary = _summary()

    with TraceWriter(path) as writer:
        writer.write(header)
        writer.write(summary)

    records = list(read_trace(path))
    assert len(records) == 2
    assert records[0] == header
    assert records[1] == summary


def test_roundtrip_single_record(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    header = _header()

    with TraceWriter(path) as writer:
        writer.write(header)

    records = list(read_trace(path))
    assert records == [header]


def test_roundtrip_multiple_records_order_preserved(tmp_path: Path) -> None:
    """Order of written records is preserved on read."""
    path = tmp_path / "trace.jsonl.gz"
    # Write several summaries with distinct oids_seen to check ordering
    summaries = [
        Summary(
            type="summary",
            at=Reltime(float(i)),
            exchanges=i,
            oids_seen=i * 10,
            end_reason="completed",
            violation_counts={},
        )
        for i in range(1, 6)
    ]

    with TraceWriter(path) as writer:
        for s in summaries:
            writer.write(s)

    records = list(read_trace(path))
    assert records == summaries


# ---------------------------------------------------------------------------
# Truncation: chop bytes off the end — earlier records still yield, no exception
# ---------------------------------------------------------------------------


def test_truncation_earlier_records_still_yield(tmp_path: Path) -> None:
    """Chopping bytes from the end destroys the final record;
    earlier records still come through without exception.

    We chop enough bytes to corrupt the gzip end-of-stream marker and the
    summary record's data, but not so many that the compressed first record is
    also lost.  Removing ~20-25 bytes from the end is sufficient for records of
    this size while keeping the header decodable.
    """
    path = tmp_path / "trace.jsonl.gz"
    header = _header()
    summary = _summary()

    with TraceWriter(path) as writer:
        writer.write(header)
        writer.write(summary)

    # Chop 25 bytes from the end — enough to corrupt the final record and
    # gzip trailer, but the first record's compressed data remains intact.
    raw = path.read_bytes()
    path.write_bytes(raw[:-25])

    records = list(read_trace(path))
    # At least the first record must survive; the truncated final record is silently dropped
    assert len(records) >= 1
    assert records[0] == header


def test_truncation_empty_file_yields_nothing(tmp_path: Path) -> None:
    """A completely truncated (empty) file yields nothing and does not raise."""
    path = tmp_path / "trace.jsonl.gz"
    path.write_bytes(b"")

    records = list(read_trace(path))
    assert records == []


def test_truncation_partial_gzip_header_yields_nothing(tmp_path: Path) -> None:
    """A file with only a partial gzip magic header yields nothing, no exception."""
    path = tmp_path / "trace.jsonl.gz"
    path.write_bytes(b"\x1f\x8b")  # partial gzip magic, not a valid stream

    records = list(read_trace(path))
    assert records == []


def test_truncation_mid_line_final_record_dropped(tmp_path: Path) -> None:
    """A partial final line (no trailing newline) is silently dropped."""
    path = tmp_path / "trace.jsonl.gz"
    header = _header()
    summary = _summary()

    with TraceWriter(path) as writer:
        writer.write(header)
        writer.write(summary)

    # Decompress, strip the trailing newline from the last line, recompress
    with gzip.open(path, "rb") as f:
        content = f.read()

    # Remove the newline terminating the last line → partial line
    assert content.endswith(b"\n")
    truncated_content = content[:-1]

    path.write_bytes(gzip.compress(truncated_content))

    records = list(read_trace(path))
    # Only the header (first complete line) should be returned
    assert len(records) == 1
    assert records[0] == header


# ---------------------------------------------------------------------------
# Ctrl-C durability: flush-per-record means data is readable before close()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Context manager: __enter__ returns writer, __exit__ closes
# ---------------------------------------------------------------------------


def test_context_manager_returns_writer(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    with TraceWriter(path) as writer:
        assert isinstance(writer, TraceWriter)
        writer.write(_header())


def test_context_manager_file_readable_after_exit(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    header = _header()
    with TraceWriter(path) as writer:
        writer.write(header)

    assert list(read_trace(path)) == [header]


# ---------------------------------------------------------------------------
# read_trace yields properly validated TraceRecord instances
# ---------------------------------------------------------------------------


def test_read_trace_returns_correct_types(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    header = _header()
    summary = _summary()

    with TraceWriter(path) as writer:
        writer.write(header)
        writer.write(summary)

    records = list(read_trace(path))
    assert isinstance(records[0], Header)
    assert isinstance(records[1], Summary)


def test_read_trace_parse_record_equality(tmp_path: Path) -> None:
    """Ensure read_trace output matches direct parse_record output."""
    path = tmp_path / "trace.jsonl.gz"
    header = _header()

    with TraceWriter(path) as writer:
        writer.write(header)

    with gzip.open(path, "rt", encoding="utf-8") as f:
        line = f.readline().rstrip("\n")

    assert list(read_trace(path)) == [parse_record(line)]


# ---------------------------------------------------------------------------
# Empty trace file (written via context manager with no records)
# ---------------------------------------------------------------------------


def test_empty_writer_yields_nothing(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    with TraceWriter(path):
        pass

    assert list(read_trace(path)) == []


def test_blank_line_in_stream_is_skipped(tmp_path: Path) -> None:
    """A blank line (just a newline) between records is silently skipped."""
    path = tmp_path / "trace.jsonl.gz"
    header = _header()
    summary = _summary()

    # Construct content with a blank line between the two records
    content = dump_record(header) + "\n" + "\n" + dump_record(summary) + "\n"
    path.write_bytes(gzip.compress(content.encode("utf-8")))

    records = list(read_trace(path))
    assert len(records) == 2
    assert records[0] == header
    assert records[1] == summary


# ---------------------------------------------------------------------------
# read_trace raises on format-invalid complete lines (not silent skip)
# ---------------------------------------------------------------------------


def test_read_trace_raises_on_format_invalid_line(tmp_path: Path) -> None:
    """A syntactically-valid JSON line that fails schema validation must raise.

    {"type":"summary"} is valid JSON but missing required fields (at, exchanges,
    oids_seen, end_reason, violation_counts).  read_trace must propagate the
    pydantic.ValidationError rather than silently skipping the line.
    """
    path = tmp_path / "trace.jsonl.gz"
    invalid_line = '{"type":"summary"}\n'
    path.write_bytes(gzip.compress(invalid_line.encode("utf-8")))

    with pytest.raises(pydantic.ValidationError):
        list(read_trace(path))


# ---------------------------------------------------------------------------
# dump_record output is what actually gets written (content fidelity)
# ---------------------------------------------------------------------------


def test_written_content_matches_dump_record(tmp_path: Path) -> None:
    """The gzip file must contain exactly dump_record(record) + newline."""
    path = tmp_path / "trace.jsonl.gz"
    header = _header()

    with TraceWriter(path) as writer:
        writer.write(header)

    with gzip.open(path, "rt", encoding="utf-8") as f:
        content = f.read()

    expected = dump_record(header) + "\n"
    assert content == expected
