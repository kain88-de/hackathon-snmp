"""Tests for oidtrace.tracefile — gzip-JSONL trace I/O."""

from pathlib import Path

from oidtrace.tracefile import TraceWriter, read_trace


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    records = [
        {"type": "get", "oid": "1.3.6.1.2.1.1.1.0"},
        {"type": "response", "value": 42},
        {"type": "end"},
    ]
    with TraceWriter(path) as w:
        for r in records:
            w.write(r)

    result = list(read_trace(path))
    assert result == records


def test_truncation_tolerance(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl.gz"
    records = [
        {"seq": 0},
        {"seq": 1},
        {"seq": 2},
    ]
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
    record = {"event": "hello"}

    w = TraceWriter(path)
    w.write(record)
    # Do NOT call close() — simulate Ctrl-C here

    # Open the file independently and read what's there
    result = list(read_trace(path))
    assert record in result

    w.close()  # cleanup
