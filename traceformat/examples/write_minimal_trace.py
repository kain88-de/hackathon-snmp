#!/usr/bin/env python3
"""Minimal example: write a valid trace file using the traceformat API.

This shows the correct way to produce trace records — via the pydantic models
and dump_record(), not by hand-rolling JSON. Format changes are caught at
construction time rather than discovered at parse time.

Usage:
    uv run traceformat/examples/write_minimal_trace.py /tmp/example.oidtrace.jsonl.gz
"""
import gzip
import sys
from datetime import datetime, timezone

from traceformat import Header, Exchange, Summary, dump_record
from traceformat.models import (
    Attempt, Request, Settings, Snmp, Session,
)
from traceformat.vocab import EndReason

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/example.oidtrace.jsonl.gz"

now = datetime.now(timezone.utc)

header = Header(
    format_version=1,
    tool="traceformat/example",
    started_at=now,
    label="example-trace",
    session=Session(id="example", run=1, runs_total=1),
    snmp=Snmp(version="2c"),
    settings=Settings(
        bulk_size=10,
        timeout_s=2.0,
        retries=2,
        start_oid="1.3.6.1",
    ),
)

exchanges = [
    Exchange(
        seq=1,
        request=Request(
            pdu="getbulk",
            request_id=12345,
            oids=["1.3.6.1.2.1.1.1.0"],
            non_repeaters=0,
            max_repetitions=10,
        ),
        attempts=[
            Attempt(sent_at=0.001, received_at=0.045),
        ],
    ),
    Exchange(
        seq=2,
        request=Request(
            pdu="getbulk",
            request_id=12346,
            oids=["1.3.6.1.2.1.1.2.0"],
            non_repeaters=0,
            max_repetitions=10,
        ),
        attempts=[
            Attempt(sent_at=0.048, received_at=None),  # timeout
        ],
        violations=["request-id-mismatch"],
    ),
]

summary = Summary(
    at=2.05,
    exchanges=len(exchanges),
    oids_seen=10,
    end_reason=EndReason.COMPLETED,
    violation_counts={"request-id-mismatch": 1},
)

with gzip.open(path, "wt") as f:
    f.write(dump_record(header) + "\n")
    for ex in exchanges:
        f.write(dump_record(ex) + "\n")
    f.write(dump_record(summary) + "\n")

print(f"wrote {len(exchanges)} exchanges → {path}")
