#!/usr/bin/env python3
"""Generate synthetic oidtrace files at arbitrary scale for performance testing.

Usage:
    uv run oidviz/tools/gen_trace.py 5000   /tmp/trace-5k.oidtrace.jsonl.gz
    uv run oidviz/tools/gen_trace.py 50000  /tmp/trace-50k.oidtrace.jsonl.gz
    uv run oidviz/tools/gen_trace.py 100000 /tmp/trace-100k.oidtrace.jsonl.gz
"""
import gzip
import json
import random
import sys
from datetime import datetime, timezone
from typing import Any

OID_PREFIXES = [
    "1.3.6.1.2.1.1",
    "1.3.6.1.2.1.2.2.1",
    "1.3.6.1.2.1.4",
    "1.3.6.1.2.1.4.21",
    "1.3.6.1.2.1.6",
    "1.3.6.1.2.1.11",
    "1.3.6.1.2.1.25",
    "1.3.6.1.2.1.25.3",
    "1.3.6.1.4.1.9.9",
    "1.3.6.1.4.1.9.2",
    "1.3.6.1.6.3.16",
]
VTYPES = ["Gauge32", "Counter32", "Integer", "OctetString", "IpAddress", "TimeTicks", "ObjectIdentifier"]
BULK = 10


def gen_trace(n: int, path: str, seed: int = 42) -> None:
    rng = random.Random(seed)

    header = {
        "type": "header",
        "format_version": 1,
        "tool": "oidtrace/synthetic",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "label": f"synthetic-{n}",
        "session": {"id": "synthetic", "run": 1, "runs_total": 1},
        "snmp": {"version": "2c"},
        "settings": {
            "bulk_size": BULK,
            "timeout_s": 2.0,
            "retries": 2,
            "start_oid": "1.3.6.1",
            "time_budget_s": 600.0,
        },
    }

    t = 0.0005  # seconds
    oids_seen = 0
    violation_counts: dict[str, int] = {}

    with gzip.open(path, "wt", compresslevel=6) as f:
        f.write(json.dumps(header) + "\n")

        for i in range(n):
            spike = rng.random() < 0.03
            timeout = rng.random() < 0.006
            base_rtt: float = rng.uniform(0.003, 0.010) if spike else rng.uniform(0.0001, 0.0009)

            prefix = OID_PREFIXES[i % len(OID_PREFIXES)]
            cursor_oid = f"{prefix}.{i % 500 + 1}"

            violation: str | None = None
            if not timeout and rng.random() < 0.012:
                violation = rng.choice(["request-id-mismatch", "oid-not-increasing"])
                violation_counts[violation] = violation_counts.get(violation, 0) + 1

            req_id = rng.randint(100_000_000, 999_999_999)
            resp_id = rng.randint(100_000_000, 999_999_999) if violation == "request-id-mismatch" else req_id

            attempts: list[dict[str, float]] = []
            if timeout:
                attempts.append({"sent_at": t, "received_at": t + 2.0})
                if rng.random() < 0.6:
                    t2: float = t + 2.3
                    attempts.append({"sent_at": t2, "received_at": t2 + rng.uniform(0.0002, 0.0006)})
            else:
                attempts.append({"sent_at": t, "received_at": t + base_rtt})

            received_at: float = attempts[-1]["received_at"]

            varbinds: list[dict[str, Any]] = [
                {
                    "oid": f"{prefix}.{(i * BULK + j) % 10_000 + 1}",
                    "vtype": VTYPES[(i + j) % len(VTYPES)],
                    "vlen": rng.randint(1, 8),
                }
                for j in range(BULK)
            ]
            oids_seen += len(varbinds)

            exchange: dict[str, Any] = {
                "type": "exchange",
                "seq": i + 1,
                "request": {
                    "pdu": "getbulk",
                    "request_id": req_id,
                    "oids": [cursor_oid],
                    "non_repeaters": 0,
                    "max_repetitions": BULK,
                },
                "attempts": attempts,
                "response": {
                    "request_id": resp_id,
                    "error_status": 0,
                    "error_index": 0,
                    "varbinds": varbinds,
                },
            }
            if violation:
                exchange["violation"] = violation

            f.write(json.dumps(exchange) + "\n")

            gap: float = rng.uniform(0.0003, 0.0012)
            t = received_at + gap

        summary = {
            "type": "summary",
            "at": t,
            "exchanges": n,
            "oids_seen": oids_seen,
            "end_reason": "completed",
            "violation_counts": violation_counts,
        }
        f.write(json.dumps(summary) + "\n")

    import os
    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"✓ {n:,} exchanges → {path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    gen_trace(int(sys.argv[1]), sys.argv[2])
