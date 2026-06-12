"""Tests for oidtrace.tracefile — gzip-JSONL trace I/O over traceformat models."""

from pathlib import Path

from traceformat import TraceRecord, parse_record

from oidtrace.tracefile import TraceWriter, read_trace


def _records() -> list[TraceRecord]:
    return [
        parse_record(
            '{"type":"exchange","seq":1,'
            '"request":{"pdu":"getbulk","request_id":1,"oids":["1.3.6.1"],'
            '"non_repeaters":0,"max_repetitions":10},'
            '"attempts":[{"sent_at":1.0,"received_at":1.5}]}'
        ),
        parse_record('{"type":"event","at":2.0,"kind":"oid-loop-detected"}'),
        parse_record(
            '{"type":"summary","at":3.0,"exchanges":1,"oids_seen":10,'
            '"end_reason":"completed","violation_counts":{}}'
        ),
    ]


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    records = _records()
    with TraceWriter(path) as w:
        for r in records:
            w.write(r)

    result = list(read_trace(path))
    assert result == records


def test_truncation_tolerance(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    records = _records()
    with TraceWriter(path) as w:
        for r in records:
            w.write(r)

    # Chop the last 20 bytes to simulate a crash mid-write
    data = path.read_bytes()
    path.write_bytes(data[:-20])

    result = list(read_trace(path))
    # At least the first record must survive; exact count depends on truncation point
    assert len(result) >= 1
    for i, rec in enumerate(result):
        assert rec == records[i]


def test_ctrl_c_safety(tmp_path: Path) -> None:
    """After write() without close(), the record is already readable."""
    path = tmp_path / "trace.jsonl.gz"
    record = parse_record('{"type":"event","at":0.0,"kind":"oid-loop-detected"}')

    w = TraceWriter(path)
    w.write(record)
    # Do NOT call close() — simulate Ctrl-C here

    # Open the file independently and read what's there
    result = list(read_trace(path))
    assert record in result

    w.close()  # cleanup
