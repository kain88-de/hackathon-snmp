# Slow-OID Detection Engine — Design

**Date:** 2026-06-08
**Status:** Approved (brainstorm) — pending implementation plan
**Context:** Inspired by the Checkmk blog *SNMP Troubleshooting*
(https://checkmk.com/blog/snmp-troubleshooting). SNMP walks against slow
devices stall on particular OID subtrees and time out. We want to detect
*which* OIDs/subtrees are slow and classify them.

## Problem

An SNMP walk enumerates a device's OIDs by repeated `GETNEXT`/`GETBULK`
traversal — there is no "list all OIDs" RPC. The enumeration *is* the
operation that stalls. When one subtree (e.g. `ifTable`,
`1.3.6.1.2.1.2.2.1`) responds slowly or drops responses, the whole walk
slows down or terminates prematurely, and today the user gets a silently
truncated result with no indication of where or why.

The existing `trouble-shooter/main.py` `_snmp_walk` records a per-varbind
`ms`, but this is **misleading**: during a bulk walk many varbinds return in
a single response, so the round-trip time is attributed to the first OID in
the batch while the rest show ~0 ms. The current measurement isolates a slow
*request*, not a slow *OID*.

## Goal

A standalone, well-tested Python detection engine that:

1. Discovers the OIDs a device exposes (via traversal).
2. Classifies each OID / subtree into configurable severity buckets by
   response time.
3. Pinpoints the exact slow OIDs, not just slow regions.
4. Reports whether the walk completed or ended prematurely, and where/why.

API and CLI are thin wrappers over the engine.

## Environment / constraints

- `pysnmp >= 7.1.27` (installed and verified). Async hlapi v3arch provides
  `get_cmd`, `next_cmd`, `bulk_cmd`, `walk_cmd`, `bulk_walk_cmd`.
- The engine uses `bulk_cmd` (controlled GETBULK round-trips) and `get_cmd`
  (single-OID round-trips) directly, rather than the generator-based
  `walk_cmd`/`bulk_walk_cmd`, so that **every timed measurement is a single
  round-trip we control** — this is the fix for the per-varbind timing flaw.
- The existing `emulator/` (configurable `slow_prefixes`, `slow_delay`, and
  drop-on-reset) and its session-scoped pytest fixtures are the integration
  test harness.

## Architecture

A new package under `trouble-shooter/` (e.g. `detector/`) in three layers,
isolating pure logic from I/O so it is testable without a network.

### 1. `prober.py` — the I/O boundary (only layer touching pysnmp)

- `SnmpProber(host, community, port, timeout, retries)`.
- `bulk_walk(root_oid, bulk_size)` — a manual `bulk_cmd` loop. Each GETBULK is
  one round-trip timed by us, yielding
  `Batch(oids=[(oid, value), ...], elapsed_ms, timed_out: bool)`.
- `probe_oid(oid)` — a single `get_cmd` (one OID, one round-trip) returning
  `Sample(oid, value, elapsed_ms, responded: bool)`. Used for pinpointing.
  Falls back to `next_cmd` on the predecessor only if an OID does not answer a
  GET.
- This is the seam that tests mock/replace.

### 2. `classify.py` — pure functions, no I/O, no pysnmp

- `bucket_for(ms, buckets) -> Bucket` — assigns the first tier whose `max_ms`
  the measurement falls under.
- `find_slow_regions(batches, buckets) -> [Region]` — coalesces adjacent
  non-OK batches into contiguous spans and derives each region's longest
  common OID prefix (e.g. `1.3.6.1.2.1.2.2.1`).
- `validate_buckets(buckets)` — tiers must be ascending by `max_ms` with
  exactly one open-ended (`max_ms is None`) catch-all.
- Fully unit-testable with synthetic timing samples.

### 3. `engine.py` — the orchestrator

- `diagnose(prober, *, buckets, config) -> DiagnosisReport`: runs phase 1
  (discover + region timing), calls the classifier, runs phase 2 (pinpoint
  within slow regions), assembles the report.

### Thin wrappers

- `/api/diagnose` in `main.py` builds an `SnmpProber` + `DetectorConfig`,
  takes the bucket tiers from the request body, calls `engine.diagnose`,
  returns the report as JSON.
- A small CLI entrypoint calls the same `engine.diagnose` for terminal use.

## Two-phase algorithm

### Phase 1 — Discover + coarse timing (one bulk walk)

`prober.bulk_walk(root_oid, bulk_size)` is a generator that performs the GETBULK
loop below and yields one timed `Batch` per round-trip. `engine.diagnose`
consumes it, enforcing the `total_timeout` budget and assembling completeness:

```
# inside prober.bulk_walk — one timed round-trip per iteration:
oid_cursor = root_oid              # default 1.3.6.1.2.1
while True:
    t0 = monotonic()
    result = bulk_cmd(oid_cursor, max_repetitions=bulk_size)  # one round-trip
    elapsed = monotonic() - t0
    if no response (timeout/retries exhausted):
        yield Batch(oids=[oid_cursor], elapsed, timed_out=True)   # walk died here
        return
    yield Batch(oids=result.oids, elapsed_ms=elapsed, timed_out=False)
    if endOfMibView reached:
        return                     # walk completed normally
    oid_cursor = result.oids[-1]   # advance lexicographically

# inside engine.diagnose — consume batches, enforce budget:
for batch in prober.bulk_walk(config.root_oid, config.bulk_size):
    batches.append(batch)
    if batch.timed_out:           reason = TIMEOUT;          break
    if total elapsed > budget:    reason = BUDGET_EXCEEDED;  break
else:
    reason = END_OF_MIB           # generator exhausted cleanly
```

Simultaneously discovers every OID and records one honest round-trip time per
batch. `bulk_size` is configurable (the blog's `-Cr` knob). `complete` is true
only when `reason == END_OF_MIB`; `stopped_at` is the last OID in the last
successful batch.

### Region detection (pure)

- Bucket each batch by round-trip time.
- Coalesce adjacent non-OK batches into a `Region`; compute the longest common
  OID prefix of its OIDs → the human-meaningful "slow subtree" that maps to
  remediation.

### Phase 2 — Pinpoint (only within flagged regions)

- For each slow region, re-probe each discovered OID individually with
  `prober.probe_oid(oid)` (single GET, one OID per round-trip).
- Each gets an exact `elapsed_ms` → exact bucket. Now we report *which
  specific OIDs* are CRITICAL, not just which batch was slow.
- Runs only over flagged regions, so cost stays bounded.

**Rationale:** Phase 1 is fast and covers the whole tree but can only blame a
batch; Phase 2 is precise but expensive, so we spend it only where Phase 1 saw
trouble. Coarse-find, then fine-pinpoint.

## Classification (configurable, caller-supplied)

Bucket limits are **not hard-coded**. The package's public interface takes the
tier list as a required parameter:

```python
def diagnose(prober: Prober, *, buckets: Sequence[Bucket], config: DetectorConfig) -> DiagnosisReport
# classify.bucket_for(ms, buckets) and find_slow_regions(batches, buckets) likewise.
```

A `Bucket(name: str, max_ms: int | None)` list is an *example* a caller may
pass — there is no module-level default driving behavior. The API request
schema includes the buckets, so they are configurable per call from outside.

Example tier list a caller might pass:

| name | max_ms |
|---|---|
| OK | 500 |
| SLOW | 3000 |
| CRITICAL | None (catch-all) |

- Buckets are applied to **batches** in Phase 1 and to **individual OIDs** in
  Phase 2. A region inherits the worst bucket among its members.
- `TIMEOUT` is a special, non-time-based bucket assigned when there is no
  response at all (dropped / unanswered request) — not a time band.
- Callers can add tiers (e.g. split CRITICAL at `>7s` per the blog) freely.

## Completeness / premature-termination detection

The report always carries:

- `complete: bool` — did Phase 1 reach `endOfMibView`?
- `stopped_at: oid` — last OID successfully retrieved.
- `reason` — one of `END_OF_MIB` (clean), `TIMEOUT` (a request got no answer /
  was dropped), `BUDGET_EXCEEDED` (hit `total_timeout` first).

A dropped response mid-walk produces `complete=False, reason=TIMEOUT,
stopped_at=<oid>` plus a `TIMEOUT` batch — the user sees exactly where the walk
died instead of a silently truncated list. (Directly addresses the TODO items
"snmp walk implementation times out" and "we do not see if the answer ended
prematurely.")

## Configuration / data model

`DetectorConfig` dataclass (SNMP/probing knobs only — no thresholds):

- `root_oid` (default `1.3.6.1.2.1`)
- `bulk_size` (max_repetitions, default 10)
- `timeout` seconds per request (default 5), `retries` (default 2)
- `total_timeout` budget for the whole diagnosis (default 60)
- `pinpoint: bool` (default True — Phase 1 only if False)

`DiagnosisReport` dataclass (serialized by the API):

```
complete, stopped_at, reason,
summary: {<bucket name>: count, ...}
regions: [{prefix, bucket, batch_ms, oid_count}]
oids:    [{oid, value, bucket, ms, phase}]   # phase ∈ {bulk, pinpoint}
elapsed_total_ms
```

## Testing strategy

**Pure unit tests (`classify.py`) — no network:**

- `bucket_for` with custom tier lists (boundary values 499/500/501; 4-tier
  configs; catch-all).
- `find_slow_regions`: synthetic batches → correct coalescing and common-prefix
  derivation.
- `validate_buckets`: non-ascending tiers / missing catch-all raise.

**Integration tests against the emulator** (existing session-scoped fixtures):

- `slow_prefixes=("1.3.6.1.2.1.2.2.1",)`, `slow_delay=3.0` → that subtree
  flagged as a region, its OIDs pinpointed CRITICAL; system group OK.
- `slow_delay` > per-request timeout → `TIMEOUT` bucket + `complete=False`.
- Emulator `reset()` (drop) mid-walk → `reason=TIMEOUT`, `complete=False`,
  correct `stopped_at`.
- Clean device → `complete=True`, `reason=END_OF_MIB`, all OK.

**Prober tests with a fake:** a stub `Prober` returning scripted
`Batch`/`Sample` sequences → deterministic test of the two-phase orchestration
(region → pinpoint handoff, budget exhaustion) with no UDP.

**API smoke test:** `/api/diagnose` against the emulator via the existing
FastAPI test client → report shape is correct.

## Out of scope (YAGNI)

- Remediation automation (auto-tuning bulk size / timeouts). The report
  surfaces the data; humans act on it.
- Relative/statistical outlier detection. Tiered absolute buckets only.
- Frontend visualization is a thin follow-up, not part of this engine spec.
