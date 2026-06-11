"""Experiment: validate the trace-format performance claims.

Claims under test (docs/trace-format.md §6a, OIDEmu draft "Performance model"):
  H1 size:   100k-OID device -> tens of MB raw, single-digit MB gz; 1k OIDs -> ~hundreds of KB
  H2 speed:  streaming parse + fit-style aggregation of worst file (bulk-1, 100k lines) = seconds
  H3 memory: peak memory ~ distinct OIDs (aggregate), far below uncompressed file size
  H4 tail:   reading the trailing summary = one full decompression pass, sub-second
  H5 serve:  successor lookup over 100k sorted OIDs = microseconds

Run: uv run --with jsonschema python experiments/trace_format_perf.py
"""

import bisect
import gzip
import json
import random
import time
import tracemalloc
from pathlib import Path

OUT = Path(__file__).parent / "data"
SCHEMA = Path(__file__).parent.parent / "docs" / "trace-format.schema.json"

VTYPES = ["Integer", "OctetString", "Counter32", "Gauge32", "TimeTicks", "ObjectIdentifier"]


def make_oids(n: int) -> list[str]:
    """ifTable-ish: a handful of column prefixes, many instances."""
    cols = [f"1.3.6.1.2.1.2.2.1.{c}" for c in range(1, 11)]
    per_col = n // len(cols) + 1
    oids = [f"{col}.{i}" for col in cols for i in range(1, per_col + 1)]
    return sorted(oids[:n], key=lambda o: [int(x) for x in o.split(".")])


def fake_raw(oids: list[str], vlens: list[int]) -> str:
    """Scrubbed-packet stand-in with realistic entropy: BER-ish header, hex-encoded
    OID bytes (varying), zeroed value octets (00 * vlen). Random hex would compress
    far worse than real scrubbed packets and skew H1."""
    parts = ["30820100020101040000a2820100"]  # envelope-ish, community zeroed
    for oid, vlen in zip(oids, vlens):
        oid_hex = oid.encode().hex()
        parts.append(f"30{len(oid_hex) // 2 + vlen + 4:02x}06{len(oid_hex) // 2:02x}{oid_hex}04{vlen:02x}" + "00" * vlen)
    return "".join(parts)


def generate(path: Path, n_oids: int, bulk: int, seed: int = 7) -> None:
    rng = random.Random(seed)
    oids = make_oids(n_oids)
    t = 0.0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        def emit(rec):
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")

        emit({"type": "header", "format_version": 1, "tool": "oidtrace 0.1.0",
              "started_at": "2026-06-11T14:03:07Z", "label": "perf-experiment",
              "session": {"id": "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42", "run": 1, "runs_total": 1},
              "snmp": {"version": "2c"},
              "settings": {"bulk_size": bulk, "timeout_s": 2.0, "retries": 2, "start_oid": "1.3.6.1"}})
        emit({"type": "system_info", "at": 0.01, "point": "start",
              "values": {"1.3.6.1.2.1.1.1.0": "Acme Router 9000 fw 4.2.1",
                         "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9999.1", "1.3.6.1.2.1.1.3.0": 492711442}})

        step = max(bulk, 1)
        seq = 0
        for i in range(0, len(oids), step):
            seq += 1
            chunk = oids[i:i + step]
            vlens = [rng.choice((1, 2, 4, 4, 11, 17, 32)) for _ in chunk]
            latency = rng.choice((0.004, 0.006, 0.011)) if rng.random() > 0.001 else 7.0
            req_oid = oids[i - 1] if i else "1.3.6.1"
            req = {"pdu": "getbulk" if bulk else "getnext", "request_id": 1000 + seq,
                   "oids": [req_oid], "raw": fake_raw([req_oid], [0])}
            if bulk:
                req["non_repeaters"] = 0
                req["max_repetitions"] = bulk
            emit({"type": "exchange", "seq": seq, "request": req,
                  "attempts": [{"sent_at": round(t, 6), "received_at": round(t + latency, 6)}],
                  "response": {"request_id": 1000 + seq, "error_status": 0, "error_index": 0,
                               "varbinds": [{"oid": o, "vtype": rng.choice(VTYPES), "vlen": vl}
                                            for o, vl in zip(chunk, vlens)],
                               "raw": fake_raw(chunk, vlens)}})
            t += latency
        emit({"type": "system_info", "at": round(t, 6), "point": "end",
              "values": {"1.3.6.1.2.1.1.3.0": 492711442 + int(t * 100)}})
        emit({"type": "summary", "at": round(t, 6), "exchanges": seq, "oids_seen": len(oids),
              "end_reason": "completed", "violation_counts": {}})


def validate_sample(path: Path, k: int = 50) -> int:
    from jsonschema import Draft202012Validator
    v = Draft202012Validator(json.load(SCHEMA.open()))
    n = 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i % max(1, 100_000 // k) == 0:
                v.validate(json.loads(line))
                n += 1
    return n


def stream_fit(path: Path) -> dict:
    """Fitting-style single pass: tree shape + per-OID latency stats + violation counts."""
    tracemalloc.start()
    t0 = time.monotonic()
    tree: dict[str, tuple[str, int]] = {}
    lat: dict[str, list[float]] = {}  # per-OID [count, total, max] keyed by first varbind OID
    violations: dict[str, int] = {}
    lines = raw_bytes = 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            lines += 1
            raw_bytes += len(line)
            rec = json.loads(line)
            if rec["type"] != "exchange":
                continue
            resp = rec.get("response")
            if not resp:
                continue
            a = rec["attempts"][-1]
            dt = (a["received_at"] or 0) - a["sent_at"]
            for vb in resp["varbinds"]:
                tree[vb["oid"]] = (vb["vtype"], vb["vlen"])
            key = resp["varbinds"][0]["oid"] if resp["varbinds"] else "?"
            s = lat.setdefault(key, [0, 0.0, 0.0])
            s[0] += 1
            s[1] += dt
            s[2] = max(s[2], dt)
            for vio in rec.get("violations", ()):
                violations[vio] = violations.get(vio, 0) + 1
    wall = time.monotonic() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"wall_s": wall, "lines": lines, "uncompressed_mb": raw_bytes / 1e6,
            "peak_py_mb": peak / 1e6, "tree_oids": len(tree)}


def tail_read(path: Path) -> float:
    t0 = time.monotonic()
    last = ""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            last = line
    assert json.loads(last)["type"] == "summary"
    return time.monotonic() - t0


def bisect_bench(n_oids: int, lookups: int = 200_000) -> float:
    tree = [tuple(int(x) for x in o.split(".")) for o in make_oids(n_oids)]
    tree.sort()
    rng = random.Random(1)
    probes = [tree[rng.randrange(len(tree))] for _ in range(lookups)]
    t0 = time.monotonic()
    for p in probes:
        bisect.bisect_right(tree, p)
    return (time.monotonic() - t0) / lookups * 1e6  # µs/lookup


def main() -> None:
    OUT.mkdir(exist_ok=True)
    cases = [("1k OIDs, bulk 10", 1_000, 10), ("100k OIDs, bulk 10", 100_000, 10),
             ("100k OIDs, bulk 1 (worst case)", 100_000, 1)]
    print(f"{'case':<32} {'gz MB':>7} {'raw MB':>8} {'lines':>8} {'fit s':>7} "
          f"{'MB/s':>7} {'peak MB':>8} {'tail s':>7}")
    for name, n, bulk in cases:
        path = OUT / f"perf_{n}_{bulk}.oidtrace.jsonl.gz"
        generate(path, n, bulk)
        validated = validate_sample(path)
        r = stream_fit(path)
        tail = tail_read(path)
        print(f"{name:<32} {path.stat().st_size / 1e6:>7.2f} {r['uncompressed_mb']:>8.1f} "
              f"{r['lines']:>8} {r['wall_s']:>7.2f} {r['uncompressed_mb'] / r['wall_s']:>7.1f} "
              f"{r['peak_py_mb']:>8.1f} {tail:>7.2f}   ({validated} lines schema-validated, "
              f"{r['tree_oids']} OIDs in tree)")
    us = bisect_bench(100_000)
    print(f"\nH5 serve path: successor lookup over 100k sorted OIDs: {us:.2f} µs/lookup")


if __name__ == "__main__":
    main()
