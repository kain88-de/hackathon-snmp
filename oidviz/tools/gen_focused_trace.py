#!/usr/bin/env python3
"""Generate a synthetic SNMP trace with problems concentrated in 3 OID regions."""
import gzip, json, random, math, sys
from datetime import datetime, timezone

rng = random.Random(42)

# ── OID walk plan ──────────────────────────────────────────────────────────────
# Each segment: (oid_prefix, n_exchanges, problem_type)
# problem_type: None | 'slow' | 'timeout' | 'violation'
SEGMENTS = [
    # system table — fast
    ("1.3.6.1.2.1.1",      120, None),
    # interfaces — fast start
    ("1.3.6.1.2.1.2.2.1",  280, None),
    # ── PROBLEM AREA 1: ifTable congestion — slow 50-300ms ──
    ("1.3.6.1.2.1.2.2.1",  250, "slow"),
    # interfaces remainder — fast
    ("1.3.6.1.2.1.2.2.1",  200, None),
    # ip table — fast
    ("1.3.6.1.2.1.4",      380, None),
    # tcp — fast
    ("1.3.6.1.2.1.6",      120, None),
    # snmp group — fast
    ("1.3.6.1.2.1.11",      60, None),
    # hrSystem start — fast
    ("1.3.6.1.2.1.25.1",   150, None),
    # ── PROBLEM AREA 2: hrStorage timeouts ──
    ("1.3.6.1.2.1.25.2",   180, "timeout"),
    # hrDevice — fast
    ("1.3.6.1.2.1.25.3",   350, None),
    # enterprises start — fast
    ("1.3.6.1.4.1.9.2",    300, None),
    # ── PROBLEM AREA 3: Cisco enterprise OID violations + moderate slow ──
    ("1.3.6.1.4.1.9.9",    200, "violation"),
    # enterprises tail — fast
    ("1.3.6.1.4.1.9.9",    410, None),
]

def make_oid(prefix, i):
    return f"{prefix}.{i // 10 + 1}.{i % 10 + 1}"

def fast_rtt():
    return rng.uniform(0.08, 0.9)   # ms

def slow_rtt():
    return rng.uniform(50, 300)     # ms — ifTable congestion

def violation_rtt():
    return rng.uniform(15, 80)      # ms — enterprise oddness

lines = []

# Header
lines.append(json.dumps({
    "type": "header",
    "format_version": 1,
    "tool": "oidtrace/synthetic",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "label": "focused-problems-5k",
    "session": {"id": "focused", "run": 1, "runs_total": 1},
    "snmp": {"version": "2c"},
    "settings": {
        "bulk_size": 10, "timeout_s": 2.0, "retries": 2,
        "start_oid": "1.3.6.1", "time_budget_s": 600.0,
    },
}))

lines.append(json.dumps({
    "type": "system_info",
    "at": 0.0,
    "point": "start",
    "values": {
        "1.3.6.1.2.1.1.1.0": "Cisco IOS Software, Version 15.2(4)M — focused problem trace",
        "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.516",
        "1.3.6.1.2.1.1.3.0": 492711442,
    },
}))

seq = 0
t = 0.0005        # seconds from start
violation_counts = {}

for (prefix, count, problem) in SEGMENTS:
    for i in range(count):
        seq += 1
        oid = make_oid(prefix, i)

        if problem == "timeout":
            # Two failed attempts at 2s each, then success or give up
            attempts = []
            sent = t
            for attempt_n in range(rng.choice([1, 2])):
                attempts.append({"sent_at": round(sent, 6),
                                 "received_at": round(sent + 2.0, 6)})
                sent += 2.0 + rng.uniform(0.001, 0.003)
            # Sometimes a third attempt succeeds
            if len(attempts) < 2 and rng.random() < 0.5:
                rtt_s = rng.uniform(0.05, 0.3)
                attempts.append({"sent_at": round(sent, 6),
                                 "received_at": round(sent + rtt_s, 6)})
            t = attempts[-1]["received_at"] + rng.uniform(0.001, 0.003)
            viol = None

        elif problem == "slow":
            rtt_s = slow_rtt() / 1000
            attempts = [{"sent_at": round(t, 6),
                         "received_at": round(t + rtt_s, 6)}]
            t = t + rtt_s + rng.uniform(0.001, 0.003)
            viol = None

        elif problem == "violation":
            rtt_s = violation_rtt() / 1000
            attempts = [{"sent_at": round(t, 6),
                         "received_at": round(t + rtt_s, 6)}]
            t = t + rtt_s + rng.uniform(0.001, 0.003)
            # ~40% chance of a violation
            if rng.random() < 0.40:
                viol = rng.choice(["oid-not-increasing", "request-id-mismatch"])
                violation_counts[viol] = violation_counts.get(viol, 0) + 1
            else:
                viol = None

        else:  # fast, normal
            rtt_s = fast_rtt() / 1000
            attempts = [{"sent_at": round(t, 6),
                         "received_at": round(t + rtt_s, 6)}]
            t = t + rtt_s + rng.uniform(0.0005, 0.002)
            viol = None

        rec = {
            "type": "exchange",
            "seq": seq,
            "request": {"pdu": "getbulk", "request_id": rng.randint(1, 2**31),
                        "oids": [oid], "non_repeaters": 0, "max_repetitions": 10},
            "attempts": attempts,
        }
        if viol:
            rec["violation"] = viol
        lines.append(json.dumps(rec))

# Summary
lines.append(json.dumps({
    "type": "summary",
    "at": round(t, 6),
    "exchanges": seq,
    "oids_seen": seq * 10,
    "end_reason": "completed",
    "violation_counts": violation_counts,
}))

out = "/home/max/work/hackathon/oidviz/tools/fixtures/trace-focused.oidtrace.jsonl.gz"
with gzip.open(out, "wt") as f:
    f.write("\n".join(lines) + "\n")

print(f"wrote {seq} exchanges → {out}")
print(f"  violations: {violation_counts}")
print(f"  total time: {t:.1f}s")

# Print segment breakdown
print("\nSegment breakdown:")
for prefix, count, problem in SEGMENTS:
    label = f"  {prefix[:20]:<22} {count:>4} exchanges"
    if problem:
        print(f"{label}  ← {problem.upper()}")
    else:
        print(f"{label}  (normal)")
