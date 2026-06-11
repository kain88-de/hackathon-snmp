# SNMP Troubleshooting
<!-- Source: https://checkmk.com/blog/snmp-troubleshooting --> 

## Overview

Guide for diagnosing slow or broken SNMP implementations. Settings and workarounds should always be
applied **only to affected devices**, never globally.

---

## Quick Wins (80% of cases)

Try these three things in order before deeper investigation:

1. **Lower bulk size to 8** — the most common cause of crashes and hangs is a device that violates
   the RFC above a certain bulk threshold. Drop from the default 10 to 8 and retest.
2. **Increase timeout, reduce retries** — set timeout to observed response time + 1 s safety margin;
   drop retries to 2. This alone resolves most "slow device" symptoms.
3. **If a library client fails but `snmpbulkwalk` succeeds** — the device sends a fixed sequence
   number (always `1`). Switch to a client that tolerates non-incrementing sequence numbers.

---

## Baseline Measurement

Measure how long SNMP queries take before changing anything. Use verbose flags to identify which
specific OIDs or OID ranges are slow.

Target: queries should complete **well under 60 seconds** to avoid timeouts.

---

## Bulk Size

Default bulk size is typically 10 OIDs per request. Some devices crash or misbehave above a certain
threshold (e.g., bulk size > 8). Counterintuitively, raising bulk size can sometimes _increase_
total runtime.

Test different values with `snmpbulkwalk -Cr <n>` and record the working threshold.

---

## Timeouts and Retries

Some OIDs respond slowly (e.g., SFP temperature sensors: up to 7 s per request). The cumulative cost
is:

```
timeout × retries × number_of_OIDs
```

This can easily exceed 60 s.

Tuning approach:

1. Adjust the timeout (`-t` in `snmpbulkwalk`) until queries succeed reliably
2. Add 1 s safety margin
3. Reduce retries from the default (5) to 2–3 — repeated silent failures rarely recover on the tenth
   attempt

These two settings interact:

- **Query timeout** — time to wait for a single response; increase for slow devices
- **Retry count** — how many times to retry a non-answering OID; reduce to 2–3, repeated failures
  rarely recover

**Danger:** non-compliant devices that never send "NO SUCH OID" make long timeouts counterproductive
— they wait forever instead of failing fast.

---

## Disabling Slow OIDs

If certain OIDs are slow and not needed, removing the associated check entirely is often the most
pragmatic fix. Note that disabling individual OIDs within a bulk walk may not help — depending on
implementation, the entire OID range is still walked.

---

## Non-Standard Device Behaviour

Some devices violate the SNMP RFC in ways that cause incompatibilities:

- **Fixed sequence numbers** (e.g., always `1`) — some SNMP libraries enforce strict sequence
  tracking and reject these packets, while others (e.g., net-snmp CLI tools) tolerate them
- **No end-of-MIB signal** — device never replies with NO SUCH OID, causing the walk to hang until
  timeout
- **Crash on large bulk requests** — device reboots when bulk size exceeds its undocumented limit

When a Python/library-based SNMP client fails but `snmpbulkwalk` succeeds, the likely cause is one
of the above RFC violations.

---

## Takeaway

Real-world SNMP is full of RFC violations and non-obvious performance traps. Troubleshooting is
iterative. Sometimes the pragmatic answer is to disable the slow OIDs rather than chase perfect
compliance.
