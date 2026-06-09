# Slow-OID Detection Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-phase SNMP slow-OID detection engine in `src/trouble_shooter/detector/` that discovers which OIDs/subtrees are slow, classifies them into configurable severity buckets, and reports completeness — then wires it into the FastAPI app as `/api/diagnose`.

**Architecture:** Three-layer subpackage: `models.py` (pure dataclasses), `classify.py` (pure functions, no I/O), `prober.py` (pysnmp async I/O only), `engine.py` (async orchestrator). Phase 1 does one timed GETBULK round-trip per `Batch`; Phase 2 re-probes each OID in slow regions individually with `get_cmd` for per-OID timing.

**Tech Stack:** Python 3.12+, pysnmp ≥ 7.1.27 (`bulk_cmd`, `get_cmd` from `pysnmp.hlapi.v3arch.asyncio`), FastAPI, pytest with pytest-asyncio (`asyncio_mode = "auto"`), existing `emulator` package.

---

## Test suite layout

Tests in this project are separated by two axes: **package** and **I/O boundary**.

| Suite | Path | When to use |
|-------|------|-------------|
| unit | `tests/unit/` | Pure logic — no network, no emulator, no TestClient |
| integration | `tests/integration/` | Uses TestClient and/or emulator over real SNMP |

**Emulator package tests** (testing the emulator itself) live in `emulator/tests/`, not here.

Current `just` targets in `trouble-shooter/`:
```
just ci           # format + lint + types + unit + integration
just test         # integration only (current default — extended in Task 1)
```

After Task 1, `just test` will run both suites.

---

## File map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/trouble_shooter/detector/__init__.py` | Public re-exports (stub in Task 1, filled in Task 5) |
| Create | `src/trouble_shooter/detector/models.py` | All shared dataclasses + WalkReason enum |
| Create | `src/trouble_shooter/detector/classify.py` | Pure bucketing + region-detection functions |
| Create | `src/trouble_shooter/detector/prober.py` | `SnmpProber` — only code that touches pysnmp |
| Create | `src/trouble_shooter/detector/engine.py` | `diagnose()` async orchestrator |
| Modify | `src/trouble_shooter/main.py` | Add `/api/diagnose` endpoint |
| Create | `tests/unit/__init__.py` | pytest package marker for unit suite |
| Create | `tests/unit/test_classify.py` | Pure unit tests — no I/O |
| Create | `tests/unit/test_engine.py` | Unit tests with FakeProber — no I/O |
| Modify | `tests/integration/conftest.py` | Add three new emulator fixtures |
| Create | `tests/integration/test_prober.py` | Integration tests against emulator |
| Create | `tests/integration/test_api_diagnose.py` | API smoke tests via TestClient |
| Modify | `Justfile` | Add `unit` target; update `test` to run both suites |

---

## Task 1: Package skeleton, data models, Justfile

**Files:**
- Create: `src/trouble_shooter/detector/__init__.py`
- Create: `src/trouble_shooter/detector/models.py`
- Create: `tests/unit/__init__.py`
- Modify: `Justfile`

- [ ] **Step 1: Create the detector package and stub `__init__.py`**

```bash
mkdir -p src/trouble_shooter/detector
touch src/trouble_shooter/detector/__init__.py
```

Leave `__init__.py` empty for now — it will be filled in Task 5 once all submodules exist.

- [ ] **Step 2: Create `src/trouble_shooter/detector/models.py`**

```python
from dataclasses import dataclass, field
from enum import Enum


class WalkReason(str, Enum):
    END_OF_MIB = "END_OF_MIB"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


@dataclass
class Bucket:
    name: str
    max_ms: int | None  # None = catch-all; must be last in list


@dataclass
class Batch:
    oids: list[tuple[str, str]]  # (oid_string, value_string)
    elapsed_ms: float
    timed_out: bool


@dataclass
class Sample:
    oid: str
    value: str
    elapsed_ms: float
    responded: bool


@dataclass
class Region:
    prefix: str       # longest common OID prefix of all OIDs in this region
    bucket: str       # worst bucket name seen across all batches in this region
    batch_ms: float   # max batch elapsed_ms across batches in this region
    oid_count: int
    oids: list[str] = field(default_factory=list)  # internal; excluded from API response


@dataclass
class OidResult:
    oid: str
    value: str
    bucket: str
    ms: float
    phase: str  # "bulk" or "pinpoint"


@dataclass
class DetectorConfig:
    root_oid: str = "1.3.6.1.2.1"
    bulk_size: int = 10
    timeout: float = 5.0
    retries: int = 2
    total_timeout: float = 60.0
    pinpoint: bool = True


@dataclass
class DiagnosisReport:
    complete: bool
    stopped_at: str
    reason: WalkReason
    summary: dict[str, int]   # bucket name → count of OidResults
    regions: list[Region]
    oids: list[OidResult]
    elapsed_total_ms: float
```

- [ ] **Step 3: Create `tests/unit/__init__.py`**

```bash
mkdir -p tests/unit
touch tests/unit/__init__.py
```

- [ ] **Step 4: Update `Justfile`**

Replace the current content with:

```just
run:
    -fuser -k 8080/tcp
    uv run python -m trouble_shooter.main

unit:
    uv run pytest tests/unit --durations=10 -q

integration:
    uv run pytest tests/integration --durations=10 -q

test: unit integration

types:
    uv run pyrefly check --remove-unused-ignores

lint:
    uv run ruff check . --fix

format:
    uv run ruff format .

ci: format lint types test
```

- [ ] **Step 5: Verify models are importable and CI still passes**

```bash
uv run python -c "from trouble_shooter.detector.models import Batch, Bucket, DetectorConfig, DiagnosisReport; print('ok')"
```

Expected: `ok`

```bash
just ci
```

Expected: all checks pass (unit suite has 0 tests so far — that's fine).

- [ ] **Step 6: Commit**

```bash
git add src/trouble_shooter/detector/ tests/unit/__init__.py Justfile
git commit -m "feat(detector): add data model skeleton and unit test suite"
```

---

## Task 2: `classify.py` — pure bucketing functions

**Files:**
- Create: `src/trouble_shooter/detector/classify.py`
- Create: `tests/unit/test_classify.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_classify.py`:

```python
import pytest

from trouble_shooter.detector.classify import bucket_for, common_prefix, find_slow_regions, validate_buckets
from trouble_shooter.detector.models import Batch, Bucket

BUCKETS = [Bucket("OK", 500), Bucket("SLOW", 3000), Bucket("CRITICAL", None)]


# --- validate_buckets ---

def test_validate_buckets_valid() -> None:
    validate_buckets(BUCKETS)  # must not raise


def test_validate_buckets_no_catch_all() -> None:
    with pytest.raises(ValueError, match="catch-all"):
        validate_buckets([Bucket("OK", 500), Bucket("SLOW", 3000)])


def test_validate_buckets_catch_all_not_last() -> None:
    with pytest.raises(ValueError, match="last"):
        validate_buckets([Bucket("OK", None), Bucket("SLOW", 3000)])


def test_validate_buckets_non_ascending() -> None:
    with pytest.raises(ValueError, match="ascending"):
        validate_buckets([Bucket("A", 3000), Bucket("B", 500), Bucket("C", None)])


def test_validate_buckets_empty() -> None:
    with pytest.raises(ValueError):
        validate_buckets([])


# --- bucket_for ---

def test_bucket_for_below_first_threshold() -> None:
    assert bucket_for(499, BUCKETS) == "OK"


def test_bucket_for_at_first_threshold() -> None:
    # 500 is NOT below 500, so it falls to SLOW
    assert bucket_for(500, BUCKETS) == "SLOW"


def test_bucket_for_above_first_threshold() -> None:
    assert bucket_for(501, BUCKETS) == "SLOW"


def test_bucket_for_below_second_threshold() -> None:
    assert bucket_for(2999, BUCKETS) == "SLOW"


def test_bucket_for_at_second_threshold() -> None:
    assert bucket_for(3000, BUCKETS) == "CRITICAL"


def test_bucket_for_catch_all() -> None:
    assert bucket_for(999999, BUCKETS) == "CRITICAL"


def test_bucket_for_four_tier() -> None:
    four = [Bucket("OK", 500), Bucket("WARN", 1000), Bucket("SLOW", 3000), Bucket("CRIT", None)]
    assert bucket_for(499, four) == "OK"
    assert bucket_for(500, four) == "WARN"
    assert bucket_for(999, four) == "WARN"
    assert bucket_for(1000, four) == "SLOW"
    assert bucket_for(3000, four) == "CRIT"


# --- common_prefix ---

def test_common_prefix_shared_prefix() -> None:
    assert common_prefix(["1.3.6.1.2.1.2.2.1.1.1", "1.3.6.1.2.1.2.2.1.2.1"]) == "1.3.6.1.2.1.2.2.1"


def test_common_prefix_single_oid() -> None:
    assert common_prefix(["1.3.6.1.2.1.1.1.0"]) == "1.3.6.1.2.1.1.1.0"


def test_common_prefix_empty_list() -> None:
    assert common_prefix([]) == ""


def test_common_prefix_no_shared_prefix() -> None:
    assert common_prefix(["1.2.3", "4.5.6"]) == ""


def test_common_prefix_fully_identical() -> None:
    assert common_prefix(["1.3.6.1", "1.3.6.1"]) == "1.3.6.1"


# --- find_slow_regions ---

def test_find_slow_regions_empty_batches() -> None:
    assert find_slow_regions([], BUCKETS) == []


def test_find_slow_regions_all_ok() -> None:
    batches = [
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "foo")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.1.2.0", "bar")], elapsed_ms=200, timed_out=False),
    ]
    assert find_slow_regions(batches, BUCKETS) == []


def test_find_slow_regions_one_slow_region() -> None:
    batches = [
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "a"), ("1.3.6.1.2.1.2.2.1.2.1", "b")], elapsed_ms=800, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.2.2.1.3.1", "c")], elapsed_ms=900, timed_out=False),
    ]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 1
    r = regions[0]
    assert r.prefix == "1.3.6.1.2.1.2.2.1"
    assert r.bucket == "SLOW"
    assert r.oid_count == 3
    assert r.batch_ms == 900.0
    assert "1.3.6.1.2.1.2.2.1.1.1" in r.oids


def test_find_slow_regions_timeout_batch() -> None:
    batches = [Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "")], elapsed_ms=1000, timed_out=True)]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 1
    assert regions[0].bucket == "TIMEOUT"


def test_find_slow_regions_two_separate_regions() -> None:
    batches = [
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "a")], elapsed_ms=800, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.3.1.1", "b")], elapsed_ms=100, timed_out=False),   # OK gap
        Batch(oids=[("1.3.6.1.2.1.4.1.1", "c")], elapsed_ms=600, timed_out=False),
    ]
    assert len(find_slow_regions(batches, BUCKETS)) == 2


def test_find_slow_regions_worst_bucket_is_critical() -> None:
    batches = [
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "a")], elapsed_ms=800, timed_out=False),   # SLOW
        Batch(oids=[("1.3.6.1.2.1.2.2.1.2.1", "b")], elapsed_ms=4000, timed_out=False),  # CRITICAL
    ]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 1
    assert regions[0].bucket == "CRITICAL"
```

- [ ] **Step 2: Run tests — verify ImportError**

```bash
uv run pytest tests/unit/test_classify.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'bucket_for' from 'trouble_shooter.detector.classify'`

- [ ] **Step 3: Create `src/trouble_shooter/detector/classify.py`**

```python
from .models import Batch, Bucket, Region


def validate_buckets(buckets: list[Bucket]) -> None:
    if not buckets:
        raise ValueError("buckets must not be empty")
    if len([b for b in buckets if b.max_ms is None]) != 1:
        raise ValueError("exactly one catch-all bucket (max_ms=None) required")
    if buckets[-1].max_ms is not None:
        raise ValueError("catch-all bucket must be last")
    bounded = [b for b in buckets if b.max_ms is not None]
    for i in range(len(bounded) - 1):
        if bounded[i].max_ms >= bounded[i + 1].max_ms:  # type: ignore[operator]
            raise ValueError(
                f"bucket max_ms values must be strictly ascending: "
                f"{bounded[i].max_ms} >= {bounded[i + 1].max_ms}"
            )


def bucket_for(ms: float, buckets: list[Bucket]) -> str:
    for b in buckets:
        if b.max_ms is None or ms < b.max_ms:
            return b.name
    return buckets[-1].name


def common_prefix(oids: list[str]) -> str:
    if not oids:
        return ""
    parts = [oid.split(".") for oid in oids]
    prefix = []
    for components in zip(*parts):
        if len(set(components)) == 1:
            prefix.append(components[0])
        else:
            break
    return ".".join(prefix)


def find_slow_regions(batches: list[Batch], buckets: list[Bucket]) -> list[Region]:
    ok_name = buckets[0].name
    regions: list[Region] = []
    pending: list[Batch] = []

    for batch in batches:
        b_name = "TIMEOUT" if batch.timed_out else bucket_for(batch.elapsed_ms, buckets)
        if b_name == ok_name:
            if pending:
                regions.append(_make_region(pending, buckets))
                pending = []
        else:
            pending.append(batch)

    if pending:
        regions.append(_make_region(pending, buckets))

    return regions


def _make_region(batches: list[Batch], buckets: list[Bucket]) -> Region:
    all_oids = [oid for b in batches for oid, _ in b.oids]
    return Region(
        prefix=common_prefix(all_oids),
        bucket=_worst_bucket(batches, buckets),
        batch_ms=max(b.elapsed_ms for b in batches),
        oid_count=len(all_oids),
        oids=all_oids,
    )


def _worst_bucket(batches: list[Batch], buckets: list[Bucket]) -> str:
    if any(b.timed_out for b in batches):
        return "TIMEOUT"
    names = [b.name for b in buckets]
    worst = 0
    for batch in batches:
        idx = names.index(bucket_for(batch.elapsed_ms, buckets))
        worst = max(worst, idx)
    return names[worst]
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
uv run pytest tests/unit/test_classify.py -v
```

Expected: all 20 tests PASS.

- [ ] **Step 5: Run `just ci`**

```bash
just ci
```

Expected: all checks pass.

- [ ] **Step 6: Commit**

```bash
git add src/trouble_shooter/detector/classify.py tests/unit/test_classify.py
git commit -m "feat(detector): add classify.py with pure bucket/region functions and unit tests"
```

---

## Task 3: `engine.py` — orchestrator

**Files:**
- Create: `src/trouble_shooter/detector/engine.py`
- Create: `tests/unit/test_engine.py`

Engine is tested with a `FakeProber` — no I/O — so it lives in `tests/unit/`. Tests are `async def`; pytest-asyncio handles the event loop automatically.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_engine.py`:

```python
import pytest

from trouble_shooter.detector.engine import diagnose
from trouble_shooter.detector.models import Batch, Bucket, DetectorConfig, Sample, WalkReason

BUCKETS = [Bucket("OK", 500), Bucket("SLOW", 3000), Bucket("CRITICAL", None)]


class FakeProber:
    def __init__(self, batches: list[Batch], samples: dict[str, Sample] | None = None) -> None:
        self._batches = batches
        self._samples = samples or {}

    async def bulk_walk(self, root_oid: str, bulk_size: int):
        for batch in self._batches:
            yield batch

    async def probe_oid(self, oid: str) -> Sample:
        return self._samples.get(oid, Sample(oid=oid, value="v", elapsed_ms=10.0, responded=True))


async def test_diagnose_clean_walk_is_complete() -> None:
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
    ])
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False))
    assert report.complete is True
    assert report.reason == WalkReason.END_OF_MIB
    assert report.summary["OK"] == 2
    assert report.summary.get("SLOW", 0) == 0
    assert len(report.regions) == 0
    assert len(report.oids) == 2


async def test_diagnose_timeout_batch_stops_walk() -> None:
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "")], elapsed_ms=5000, timed_out=True),
    ])
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False))
    assert report.complete is False
    assert report.reason == WalkReason.TIMEOUT
    assert report.stopped_at == "1.3.6.1.2.1.2.2.1.1.1"
    assert report.summary.get("TIMEOUT", 0) == 1


async def test_diagnose_slow_region_appears_in_regions() -> None:
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(
            oids=[("1.3.6.1.2.1.2.2.1.1.1", "a"), ("1.3.6.1.2.1.2.2.1.2.1", "b")],
            elapsed_ms=800,
            timed_out=False,
        ),
    ])
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False))
    assert len(report.regions) == 1
    assert report.regions[0].prefix == "1.3.6.1.2.1.2.2.1"
    assert report.regions[0].bucket == "SLOW"
    assert report.regions[0].oid_count == 2


async def test_diagnose_pinpoint_adds_pinpoint_oid_results() -> None:
    slow_oid = "1.3.6.1.2.1.2.2.1.1.1"
    prober = FakeProber(
        batches=[Batch(oids=[(slow_oid, "a")], elapsed_ms=800, timed_out=False)],
        samples={slow_oid: Sample(oid=slow_oid, value="a", elapsed_ms=2500.0, responded=True)},
    )
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=True))
    bulk_results = [o for o in report.oids if o.phase == "bulk"]
    pinpoint_results = [o for o in report.oids if o.phase == "pinpoint"]
    assert len(bulk_results) == 1
    assert len(pinpoint_results) == 1
    assert pinpoint_results[0].oid == slow_oid
    assert pinpoint_results[0].bucket == "SLOW"
    assert pinpoint_results[0].ms == 2500.0


async def test_diagnose_pinpoint_skipped_when_disabled() -> None:
    slow_oid = "1.3.6.1.2.1.2.2.1.1.1"
    prober = FakeProber(
        batches=[Batch(oids=[(slow_oid, "a")], elapsed_ms=800, timed_out=False)],
        samples={slow_oid: Sample(oid=slow_oid, value="a", elapsed_ms=2500.0, responded=True)},
    )
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False))
    assert not any(o.phase == "pinpoint" for o in report.oids)


async def test_diagnose_budget_exceeded() -> None:
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
    ])
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False, total_timeout=0))
    assert report.complete is False
    assert report.reason == WalkReason.BUDGET_EXCEEDED


async def test_diagnose_stopped_at_is_last_oid() -> None:
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "a"), ("1.3.6.1.2.1.1.2.0", "b")], elapsed_ms=100, timed_out=False),
    ])
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False))
    assert report.stopped_at == "1.3.6.1.2.1.1.2.0"


async def test_diagnose_invalid_buckets_raises() -> None:
    prober = FakeProber([])
    with pytest.raises(ValueError):
        await diagnose(prober, buckets=[Bucket("OK", 500)], config=DetectorConfig())


async def test_diagnose_pinpoint_unresponded_oid_gets_timeout_bucket() -> None:
    slow_oid = "1.3.6.1.2.1.2.2.1.1.1"
    prober = FakeProber(
        batches=[Batch(oids=[(slow_oid, "")], elapsed_ms=800, timed_out=False)],
        samples={slow_oid: Sample(oid=slow_oid, value="", elapsed_ms=1000.0, responded=False)},
    )
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=True))
    pinpoint = [o for o in report.oids if o.phase == "pinpoint"]
    assert pinpoint[0].bucket == "TIMEOUT"


async def test_diagnose_elapsed_total_ms_is_non_negative() -> None:
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "a")], elapsed_ms=100, timed_out=False),
    ])
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(pinpoint=False))
    assert report.elapsed_total_ms >= 0
```

- [ ] **Step 2: Run tests — verify ImportError**

```bash
uv run pytest tests/unit/test_engine.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'diagnose' from 'trouble_shooter.detector.engine'`

- [ ] **Step 3: Create `src/trouble_shooter/detector/engine.py`**

```python
from time import monotonic
from typing import Protocol, runtime_checkable

from .classify import bucket_for, find_slow_regions, validate_buckets
from .models import Batch, Bucket, DetectorConfig, DiagnosisReport, OidResult, WalkReason


@runtime_checkable
class Prober(Protocol):
    def bulk_walk(self, root_oid: str, bulk_size: int): ...
    async def probe_oid(self, oid: str): ...


async def diagnose(prober: Prober, *, buckets: list[Bucket], config: DetectorConfig) -> DiagnosisReport:
    validate_buckets(buckets)
    t_start = monotonic()
    batches: list[Batch] = []
    oid_results: list[OidResult] = []
    reason = WalkReason.END_OF_MIB
    stopped_at = config.root_oid

    async for batch in prober.bulk_walk(config.root_oid, config.bulk_size):
        batches.append(batch)
        b_name = "TIMEOUT" if batch.timed_out else bucket_for(batch.elapsed_ms, buckets)
        for oid, value in batch.oids:
            oid_results.append(OidResult(oid=oid, value=value, bucket=b_name, ms=batch.elapsed_ms, phase="bulk"))
        if batch.oids:
            stopped_at = batch.oids[-1][0]
        if batch.timed_out:
            reason = WalkReason.TIMEOUT
            break
        if (monotonic() - t_start) > config.total_timeout:
            reason = WalkReason.BUDGET_EXCEEDED
            break

    regions = find_slow_regions(batches, buckets)

    if config.pinpoint:
        for region in regions:
            for oid in region.oids:
                sample = await prober.probe_oid(oid)
                b_name = bucket_for(sample.elapsed_ms, buckets) if sample.responded else "TIMEOUT"
                oid_results.append(OidResult(
                    oid=sample.oid,
                    value=sample.value,
                    bucket=b_name,
                    ms=sample.elapsed_ms,
                    phase="pinpoint",
                ))

    summary: dict[str, int] = {b.name: 0 for b in buckets}
    summary["TIMEOUT"] = 0
    for o in oid_results:
        summary[o.bucket] = summary.get(o.bucket, 0) + 1

    return DiagnosisReport(
        complete=(reason == WalkReason.END_OF_MIB),
        stopped_at=stopped_at,
        reason=reason,
        summary=summary,
        regions=regions,
        oids=oid_results,
        elapsed_total_ms=(monotonic() - t_start) * 1000,
    )
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
uv run pytest tests/unit/test_engine.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Run `just ci`**

```bash
just ci
```

Expected: all checks pass.

- [ ] **Step 6: Commit**

```bash
git add src/trouble_shooter/detector/engine.py tests/unit/test_engine.py
git commit -m "feat(detector): add engine.diagnose orchestrator with FakeProber unit tests"
```

---

## Task 4: `prober.py` — SNMP I/O layer

**Files:**
- Create: `src/trouble_shooter/detector/prober.py`
- Modify: `tests/integration/conftest.py` — append three new emulator fixtures
- Create: `tests/integration/test_prober.py`

These tests perform real SNMP I/O against the emulator — `tests/integration/`. Tests are `async def`; no `asyncio.run()` wrappers needed.

- [ ] **Step 1: Extend `tests/integration/conftest.py`**

Append to the **end** of the existing file. Do not change anything already there.

```python
# --- detector emulators ---

_CLEAN_CONFIG = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
_SLOW_IF_CONFIG = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.8)
_DROP_IF_CONFIG = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=10.0)


@pytest.fixture(scope="session")
def _clean_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_CLEAN_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _slow_if_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_SLOW_IF_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _drop_if_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_DROP_IF_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def emulator_clean(_clean_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _clean_server
    _clean_server.reset()


@pytest.fixture
def emulator_slow_if(_slow_if_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _slow_if_server
    _slow_if_server.reset()


@pytest.fixture
def emulator_drop_if(_drop_if_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _drop_if_server
    _drop_if_server.reset()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/integration/test_prober.py`:

```python
from emulator import EmulatorServer

from trouble_shooter.detector.models import Batch
from trouble_shooter.detector.prober import SnmpProber


async def test_bulk_walk_yields_batches_for_clean_device(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber("127.0.0.1", "public", emulator_clean.port, timeout=2.0, retries=1)
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    assert len(batches) > 0
    assert not any(b.timed_out for b in batches)
    all_oids = [oid for b in batches for oid, _ in b.oids]
    assert any("1.3.6.1.2.1.1" in oid for oid in all_oids), "system group missing"
    assert any("1.3.6.1.2.1.2.2.1" in oid for oid in all_oids), "ifTable missing"


async def test_bulk_walk_all_batches_have_non_negative_elapsed_ms(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber("127.0.0.1", "public", emulator_clean.port, timeout=2.0, retries=1)
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    assert all(b.elapsed_ms >= 0 for b in batches)


async def test_bulk_walk_slow_subtree_has_high_elapsed_ms(emulator_slow_if: EmulatorServer) -> None:
    # emulator has slow_delay=0.8s on ifTable; prober timeout=3s so it responds
    prober = SnmpProber("127.0.0.1", "public", emulator_slow_if.port, timeout=3.0, retries=0)
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    slow_batches = [b for b in batches if any("1.3.6.1.2.1.2.2.1" in oid for oid, _ in b.oids)]
    assert len(slow_batches) > 0
    assert any(b.elapsed_ms >= 700 for b in slow_batches)


async def test_bulk_walk_yields_timed_out_batch_when_dropped(emulator_drop_if: EmulatorServer) -> None:
    # emulator has slow_delay=10s on ifTable; prober timeout=1s so it times out
    prober = SnmpProber("127.0.0.1", "public", emulator_drop_if.port, timeout=1.0, retries=0)
    batches: list[Batch] = []
    async for batch in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10):
        batches.append(batch)
        if batch.timed_out:
            break
    assert any(b.timed_out for b in batches)


async def test_probe_oid_returns_responded_sample(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber("127.0.0.1", "public", emulator_clean.port, timeout=2.0, retries=1)
    sample = await prober.probe_oid("1.3.6.1.2.1.1.1.0")
    assert sample.responded is True
    assert sample.oid == "1.3.6.1.2.1.1.1.0"
    assert "Emulated" in sample.value
    assert sample.elapsed_ms >= 0


async def test_probe_oid_returns_unresponded_sample_on_timeout(emulator_drop_if: EmulatorServer) -> None:
    prober = SnmpProber("127.0.0.1", "public", emulator_drop_if.port, timeout=1.0, retries=0)
    sample = await prober.probe_oid("1.3.6.1.2.1.2.2.1.1.1")
    assert sample.responded is False
```

- [ ] **Step 3: Run tests — verify ImportError**

```bash
uv run pytest tests/integration/test_prober.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'SnmpProber' from 'trouble_shooter.detector.prober'`

- [ ] **Step 4: Create `src/trouble_shooter/detector/prober.py`**

```python
from time import monotonic
from typing import AsyncGenerator

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulk_cmd,
    get_cmd,
)
from pysnmp.proto.rfc1905 import EndOfMibView

from .models import Batch, Sample


class SnmpProber:
    def __init__(
        self,
        host: str,
        community: str,
        port: int,
        timeout: float = 5.0,
        retries: int = 2,
    ) -> None:
        self._host = host
        self._community = community
        self._port = port
        self._timeout = timeout
        self._retries = retries

    async def bulk_walk(self, root_oid: str, bulk_size: int) -> AsyncGenerator[Batch, None]:
        engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )
        try:
            cursor = root_oid
            while True:
                t0 = monotonic()
                error_indication, _status, _index, var_binds = await bulk_cmd(
                    engine,
                    CommunityData(self._community),
                    transport,
                    ContextData(),
                    0,          # nonRepeaters
                    bulk_size,  # maxRepetitions
                    ObjectType(ObjectIdentity(cursor)),
                    lookupMib=False,
                )
                elapsed_ms = (monotonic() - t0) * 1000

                if error_indication:
                    yield Batch(oids=[(cursor, "")], elapsed_ms=elapsed_ms, timed_out=True)
                    return

                if not var_binds:
                    return

                oids = [(str(vb[0]), str(vb[1])) for vb in var_binds]
                end_of_mib = isinstance(var_binds[-1][1], EndOfMibView)

                yield Batch(oids=oids, elapsed_ms=elapsed_ms, timed_out=False)

                if end_of_mib:
                    return

                cursor = str(var_binds[-1][0])
        finally:
            engine.close_dispatcher()

    async def probe_oid(self, oid: str) -> Sample:
        engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )
        try:
            t0 = monotonic()
            error_indication, _status, _index, var_binds = await get_cmd(
                engine,
                CommunityData(self._community),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lookupMib=False,
            )
            elapsed_ms = (monotonic() - t0) * 1000

            if error_indication or not var_binds:
                return Sample(oid=oid, value="", elapsed_ms=elapsed_ms, responded=False)

            return Sample(
                oid=oid,
                value=str(var_binds[0][1]),
                elapsed_ms=elapsed_ms,
                responded=True,
            )
        finally:
            engine.close_dispatcher()
```

- [ ] **Step 5: Run tests — verify all pass**

```bash
uv run pytest tests/integration/test_prober.py -v
```

Expected: all 6 tests PASS. The slow/drop tests take a few seconds due to real SNMP delays.

- [ ] **Step 6: Run `just ci`**

```bash
just ci
```

Expected: all checks pass.

- [ ] **Step 7: Commit**

```bash
git add src/trouble_shooter/detector/prober.py tests/integration/conftest.py tests/integration/test_prober.py
git commit -m "feat(detector): add SnmpProber with bulk_walk and probe_oid; integration tests"
```

---

## Task 5: Public API + `/api/diagnose` endpoint

**Files:**
- Modify: `src/trouble_shooter/detector/__init__.py` — fill in re-exports
- Modify: `src/trouble_shooter/main.py` — add `/api/diagnose` endpoint
- Create: `tests/integration/test_api_diagnose.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_api_diagnose.py`:

```python
from emulator import EmulatorServer
from starlette.testclient import TestClient


def test_diagnose_endpoint_returns_valid_report(client: TestClient, emulator_clean: EmulatorServer) -> None:
    resp = client.post("/api/diagnose", json={
        "host": "127.0.0.1",
        "port": emulator_clean.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1.1",
        "bulk_size": 10,
        "timeout": 2.0,
        "retries": 1,
        "total_timeout": 30.0,
        "pinpoint": False,
        "buckets": [
            {"name": "OK", "max_ms": 500},
            {"name": "SLOW", "max_ms": 3000},
            {"name": "CRITICAL", "max_ms": None},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["complete"] is True
    assert data["reason"] == "END_OF_MIB"
    assert "summary" in data
    assert "regions" in data
    assert "oids" in data
    assert "elapsed_total_ms" in data
    assert len(data["oids"]) > 0


def test_diagnose_endpoint_invalid_host(client: TestClient) -> None:
    resp = client.post("/api/diagnose", json={
        "host": "not_valid!!",
        "community": "public",
        "port": 1161,
        "buckets": [{"name": "OK", "max_ms": 500}, {"name": "CRIT", "max_ms": None}],
    })
    assert resp.status_code == 400


def test_diagnose_endpoint_region_excludes_oids_field(client: TestClient, emulator_clean: EmulatorServer) -> None:
    resp = client.post("/api/diagnose", json={
        "host": "127.0.0.1",
        "port": emulator_clean.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1.1",
        "bulk_size": 10,
        "timeout": 2.0,
        "retries": 1,
        "total_timeout": 30.0,
        "pinpoint": False,
        "buckets": [
            {"name": "OK", "max_ms": 500},
            {"name": "SLOW", "max_ms": 3000},
            {"name": "CRITICAL", "max_ms": None},
        ],
    })
    assert resp.status_code == 200
    for region in resp.json()["regions"]:
        assert "prefix" in region
        assert "bucket" in region
        assert "batch_ms" in region
        assert "oid_count" in region
        assert "oids" not in region  # internal field must be excluded from API response
```

- [ ] **Step 2: Run tests — verify 404**

```bash
uv run pytest tests/integration/test_api_diagnose.py -v 2>&1 | head -15
```

Expected: FAIL — `/api/diagnose` doesn't exist yet.

- [ ] **Step 3: Fill in `src/trouble_shooter/detector/__init__.py`**

```python
from .engine import diagnose
from .models import (
    Batch,
    Bucket,
    DetectorConfig,
    DiagnosisReport,
    OidResult,
    Region,
    Sample,
    WalkReason,
)
from .prober import SnmpProber

__all__ = [
    "diagnose",
    "Batch",
    "Bucket",
    "DetectorConfig",
    "DiagnosisReport",
    "OidResult",
    "Region",
    "Sample",
    "SnmpProber",
    "WalkReason",
]
```

- [ ] **Step 4: Add `/api/diagnose` to `src/trouble_shooter/main.py`**

Add after the existing imports (after `walk_cmd`):

```python
from trouble_shooter.detector import SnmpProber, diagnose
from trouble_shooter.detector.models import Bucket, DetectorConfig
```

Add after the existing `WalkRequest` class:

```python
class BucketSpec(BaseModel):
    name: str
    max_ms: int | None = None


class DiagnoseRequest(BaseModel):
    host: str
    community: str = "public"
    port: int = 1161
    root_oid: str = "1.3.6.1.2.1"
    bulk_size: int = 10
    timeout: float = 5.0
    retries: int = 2
    total_timeout: float = 60.0
    pinpoint: bool = True
    buckets: list[BucketSpec] = [
        BucketSpec(name="OK", max_ms=500),
        BucketSpec(name="SLOW", max_ms=3000),
        BucketSpec(name="CRITICAL", max_ms=None),
    ]
```

Add after `/api/walk`:

```python
@app.post("/api/diagnose")
async def diagnose_device(req: DiagnoseRequest) -> dict[str, object]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    prober = SnmpProber(req.host, req.community, req.port, req.timeout, req.retries)
    buckets = [Bucket(name=b.name, max_ms=b.max_ms) for b in req.buckets]
    config = DetectorConfig(
        root_oid=req.root_oid,
        bulk_size=req.bulk_size,
        timeout=req.timeout,
        retries=req.retries,
        total_timeout=req.total_timeout,
        pinpoint=req.pinpoint,
    )
    report = await diagnose(prober, buckets=buckets, config=config)
    return {
        "complete": report.complete,
        "stopped_at": report.stopped_at,
        "reason": report.reason.value,
        "summary": report.summary,
        "regions": [
            {
                "prefix": r.prefix,
                "bucket": r.bucket,
                "batch_ms": r.batch_ms,
                "oid_count": r.oid_count,
            }
            for r in report.regions
        ],
        "oids": [
            {"oid": o.oid, "value": o.value, "bucket": o.bucket, "ms": o.ms, "phase": o.phase}
            for o in report.oids
        ],
        "elapsed_total_ms": report.elapsed_total_ms,
    }
```

- [ ] **Step 5: Run API tests — verify all pass**

```bash
uv run pytest tests/integration/test_api_diagnose.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run full suite — verify no regressions**

```bash
just ci
```

Expected: all checks pass, all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/trouble_shooter/detector/__init__.py src/trouble_shooter/main.py tests/integration/test_api_diagnose.py
git commit -m "feat(detector): wire diagnose engine into /api/diagnose endpoint"
```

---

## Self-review checklist

**Spec coverage:**
- [x] Three-layer package (models / classify / prober / engine) — Tasks 1–4
- [x] `bulk_walk` GETBULK generator — Task 4
- [x] `probe_oid` GET per-OID — Task 4
- [x] `bucket_for`, `find_slow_regions`, `validate_buckets`, `common_prefix` — Task 2
- [x] `diagnose` orchestrator, Phase 1 bulk loop — Task 3
- [x] `total_timeout` / BUDGET_EXCEEDED — Task 3
- [x] Phase 2 pinpoint, only for slow regions — Task 3
- [x] Configurable buckets, no hard-coded defaults in engine — Tasks 2, 3, 5
- [x] TIMEOUT as special bucket (timed_out flag, not time-based) — Tasks 2, 3
- [x] `complete`, `stopped_at`, `reason` fields on report — Task 3
- [x] `Region.oids` excluded from API response — Task 5
- [x] `/api/diagnose` endpoint — Task 5
- [x] TDD red-green-commit every task — all tasks
- [x] Test layout: pure unit in `tests/unit/`, I/O in `tests/integration/`, emulator tests in `emulator/tests/` — all tasks

**Type/name consistency:**
- `Batch.oids: list[tuple[str, str]]` — consistent in classify.py, engine.py, prober.py
- `bucket_for(ms, buckets)` — same signature in classify.py and engine.py
- `find_slow_regions(batches, buckets)` — same signature in classify.py and engine.py
- `Region.oids: list[str]` — excluded from API dict in Task 5 (not in the returned dict)
- `WalkReason.value` — serialised as string via `.value` in API response
- `DetectorConfig.total_timeout` — compared against `monotonic()` seconds (not ms) in engine.py
- `SnmpProber(host, community, port, timeout, retries)` — constructor order consistent across prober.py, test fixtures, and main.py
