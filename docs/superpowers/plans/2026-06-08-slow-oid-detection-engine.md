# Slow-OID Detection Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone two-phase SNMP slow-OID detection engine in `trouble-shooter/detector/` that discovers which OIDs/subtrees are slow, classifies them into configurable severity buckets, and reports completeness — then wires it into the FastAPI app as `/api/diagnose`.

**Architecture:** Three-layer package: `models.py` (pure dataclasses), `classify.py` (pure functions, no I/O), `prober.py` (pysnmp async I/O only), `engine.py` (orchestrator). Phase 1 does one timed GETBULK round-trip per `Batch`; Phase 2 re-probes each OID in slow regions individually with `get_cmd` for an exact per-OID timing.

**Tech Stack:** Python 3.12+, pysnmp ≥ 7.1.27 (`bulk_cmd`, `get_cmd` from `pysnmp.hlapi.v3arch.asyncio`), FastAPI, pytest, existing `emulator` session-scoped fixtures.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `trouble-shooter/detector/__init__.py` | Public re-exports |
| Create | `trouble-shooter/detector/models.py` | All shared dataclasses + WalkReason enum |
| Create | `trouble-shooter/detector/classify.py` | Pure bucketing + region-detection functions |
| Create | `trouble-shooter/detector/prober.py` | `SnmpProber` — only code that touches pysnmp |
| Create | `trouble-shooter/detector/engine.py` | `diagnose()` async orchestrator |
| Modify | `trouble-shooter/main.py` | Add `/api/diagnose` endpoint |
| Create | `trouble-shooter/tests/detector/__init__.py` | pytest package marker |
| Create | `trouble-shooter/tests/detector/conftest.py` | Emulator fixtures for detector tests |
| Create | `trouble-shooter/tests/detector/test_classify.py` | Pure unit tests |
| Create | `trouble-shooter/tests/detector/test_engine.py` | Engine tests with FakeProber |
| Create | `trouble-shooter/tests/detector/test_prober.py` | Integration tests against emulator |
| Create | `trouble-shooter/tests/detector/test_api_diagnose.py` | API smoke test |

---

## Task 1: Package skeleton + data models

**Files:**
- Create: `trouble-shooter/detector/__init__.py`
- Create: `trouble-shooter/detector/models.py`

- [ ] **Step 1: Create `detector/models.py`**

```python
# trouble-shooter/detector/models.py
from dataclasses import dataclass, field
from enum import Enum


class WalkReason(str, Enum):
    END_OF_MIB = "END_OF_MIB"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


@dataclass
class Bucket:
    name: str
    max_ms: int | None  # None = catch-all (must be last in list)


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
    prefix: str        # longest common OID prefix
    bucket: str        # worst bucket name in this region
    batch_ms: float    # max batch elapsed_ms in this region
    oid_count: int
    oids: list[str] = field(default_factory=list)  # internal; excluded from API output


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
    summary: dict[str, int]   # bucket name → count of OidResults in that bucket
    regions: list[Region]
    oids: list[OidResult]
    elapsed_total_ms: float
```

- [ ] **Step 2: Create `detector/__init__.py`**

```python
# trouble-shooter/detector/__init__.py
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

- [ ] **Step 3: Verify the package is importable**

Run (from `trouble-shooter/`):
```bash
uv run python -c "from detector.models import Batch, Bucket, DetectorConfig, DiagnosisReport"
```
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add trouble-shooter/detector/
git commit -m "feat(detector): add data model package skeleton"
```

---

## Task 2: `classify.py` — pure functions + unit tests

**Files:**
- Create: `trouble-shooter/detector/classify.py`
- Create: `trouble-shooter/tests/detector/__init__.py`
- Create: `trouble-shooter/tests/detector/test_classify.py`

- [ ] **Step 1: Write the failing tests**

```python
# trouble-shooter/tests/detector/test_classify.py
import pytest
from detector.classify import bucket_for, common_prefix, find_slow_regions, validate_buckets
from detector.models import Batch, Bucket

BUCKETS = [Bucket("OK", 500), Bucket("SLOW", 3000), Bucket("CRITICAL", None)]


# --- validate_buckets ---

def test_validate_buckets_valid():
    validate_buckets(BUCKETS)  # must not raise


def test_validate_buckets_no_catch_all():
    with pytest.raises(ValueError, match="catch-all"):
        validate_buckets([Bucket("OK", 500), Bucket("SLOW", 3000)])


def test_validate_buckets_catch_all_not_last():
    with pytest.raises(ValueError, match="last"):
        validate_buckets([Bucket("OK", None), Bucket("SLOW", 3000)])


def test_validate_buckets_non_ascending():
    with pytest.raises(ValueError, match="ascending"):
        validate_buckets([Bucket("A", 3000), Bucket("B", 500), Bucket("C", None)])


def test_validate_buckets_empty():
    with pytest.raises(ValueError):
        validate_buckets([])


# --- bucket_for ---

def test_bucket_for_below_first_threshold():
    assert bucket_for(499, BUCKETS) == "OK"


def test_bucket_for_at_first_threshold():
    # 500 is NOT below 500, so it falls to SLOW
    assert bucket_for(500, BUCKETS) == "SLOW"


def test_bucket_for_above_first_threshold():
    assert bucket_for(501, BUCKETS) == "SLOW"


def test_bucket_for_below_second_threshold():
    assert bucket_for(2999, BUCKETS) == "SLOW"


def test_bucket_for_at_second_threshold():
    assert bucket_for(3000, BUCKETS) == "CRITICAL"


def test_bucket_for_catch_all():
    assert bucket_for(999999, BUCKETS) == "CRITICAL"


def test_bucket_for_four_tier():
    four = [Bucket("OK", 500), Bucket("WARN", 1000), Bucket("SLOW", 3000), Bucket("CRIT", None)]
    assert bucket_for(499, four) == "OK"
    assert bucket_for(500, four) == "WARN"
    assert bucket_for(999, four) == "WARN"
    assert bucket_for(1000, four) == "SLOW"
    assert bucket_for(3000, four) == "CRIT"


# --- common_prefix ---

def test_common_prefix_shared_prefix():
    result = common_prefix(["1.3.6.1.2.1.2.2.1.1.1", "1.3.6.1.2.1.2.2.1.2.1"])
    assert result == "1.3.6.1.2.1.2.2.1"


def test_common_prefix_single_oid():
    assert common_prefix(["1.3.6.1.2.1.1.1.0"]) == "1.3.6.1.2.1.1.1.0"


def test_common_prefix_empty_list():
    assert common_prefix([]) == ""


def test_common_prefix_no_shared_prefix():
    assert common_prefix(["1.2.3", "4.5.6"]) == ""


def test_common_prefix_fully_identical():
    assert common_prefix(["1.3.6.1", "1.3.6.1"]) == "1.3.6.1"


# --- find_slow_regions ---

def test_find_slow_regions_empty_batches():
    assert find_slow_regions([], BUCKETS) == []


def test_find_slow_regions_all_ok():
    batches = [
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "foo")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.1.2.0", "bar")], elapsed_ms=200, timed_out=False),
    ]
    assert find_slow_regions(batches, BUCKETS) == []


def test_find_slow_regions_one_slow_region():
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


def test_find_slow_regions_timeout_batch():
    batches = [
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "")], elapsed_ms=1000, timed_out=True),
    ]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 1
    assert regions[0].bucket == "TIMEOUT"


def test_find_slow_regions_two_separate_regions():
    batches = [
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "a")], elapsed_ms=800, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.3.1.1", "b")], elapsed_ms=100, timed_out=False),  # OK gap
        Batch(oids=[("1.3.6.1.2.1.4.1.1", "c")], elapsed_ms=600, timed_out=False),
    ]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 2


def test_find_slow_regions_worst_bucket_is_critical():
    batches = [
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "a")], elapsed_ms=800, timed_out=False),   # SLOW
        Batch(oids=[("1.3.6.1.2.1.2.2.1.2.1", "b")], elapsed_ms=4000, timed_out=False),  # CRITICAL
    ]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 1
    assert regions[0].bucket == "CRITICAL"
```

- [ ] **Step 2: Create `tests/detector/__init__.py`**

Empty file — pytest package marker.

```bash
touch trouble-shooter/tests/detector/__init__.py
```

- [ ] **Step 3: Run tests — verify they all fail**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_classify.py -v
```
Expected: `ImportError: No module named 'detector.classify'` or similar.

- [ ] **Step 4: Create `detector/classify.py`**

```python
# trouble-shooter/detector/classify.py
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
        if bounded[i].max_ms >= bounded[i + 1].max_ms:
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
    bucket_names = [b.name for b in buckets]
    worst_idx = 0
    for batch in batches:
        name = bucket_for(batch.elapsed_ms, buckets)
        idx = bucket_names.index(name)
        worst_idx = max(worst_idx, idx)
    return bucket_names[worst_idx]
```

- [ ] **Step 5: Run tests — verify they all pass**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_classify.py -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add trouble-shooter/detector/classify.py trouble-shooter/tests/detector/
git commit -m "feat(detector): add classify.py with bucket/region pure functions and unit tests"
```

---

## Task 3: `prober.py` — SNMP I/O layer + integration tests

**Files:**
- Create: `trouble-shooter/detector/prober.py`
- Create: `trouble-shooter/tests/detector/conftest.py`
- Create: `trouble-shooter/tests/detector/test_prober.py`

- [ ] **Step 1: Write the failing tests**

```python
# trouble-shooter/tests/detector/test_prober.py
import asyncio

from detector.models import DetectorConfig
from detector.prober import SnmpProber


def test_bulk_walk_yields_batches_for_clean_device(emulator_clean):
    prober = SnmpProber("127.0.0.1", "public", emulator_clean.port, timeout=2.0, retries=1)

    async def run():
        batches = []
        async for batch in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10):
            batches.append(batch)
        return batches

    batches = asyncio.run(run())
    assert len(batches) > 0
    assert not any(b.timed_out for b in batches)
    all_oids = [oid for b in batches for oid, _ in b.oids]
    assert any("1.3.6.1.2.1.1" in oid for oid in all_oids), "system group missing"
    assert any("1.3.6.1.2.1.2.2.1" in oid for oid in all_oids), "ifTable missing"


def test_bulk_walk_all_batches_have_positive_elapsed_ms(emulator_clean):
    prober = SnmpProber("127.0.0.1", "public", emulator_clean.port, timeout=2.0, retries=1)

    async def run():
        return [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]

    batches = asyncio.run(run())
    assert all(b.elapsed_ms >= 0 for b in batches)


def test_bulk_walk_slow_subtree_has_high_elapsed_ms(emulator_slow_if):
    # emulator_slow_if has slow_delay=0.8s on ifTable; prober timeout=3s so it responds
    prober = SnmpProber("127.0.0.1", "public", emulator_slow_if.port, timeout=3.0, retries=0)

    async def run():
        return [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]

    batches = asyncio.run(run())
    slow_batches = [
        b for b in batches if any("1.3.6.1.2.1.2.2.1" in oid for oid, _ in b.oids)
    ]
    assert len(slow_batches) > 0
    assert any(b.elapsed_ms >= 700 for b in slow_batches)


def test_bulk_walk_yields_timed_out_batch_when_dropped(emulator_drop_if):
    # emulator_drop_if has slow_delay=10s on ifTable; prober timeout=1s so it times out
    prober = SnmpProber("127.0.0.1", "public", emulator_drop_if.port, timeout=1.0, retries=0)

    async def run():
        batches = []
        async for batch in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10):
            batches.append(batch)
            if batch.timed_out:
                break
        return batches

    batches = asyncio.run(run())
    assert any(b.timed_out for b in batches)


def test_probe_oid_returns_responded_sample(emulator_clean):
    prober = SnmpProber("127.0.0.1", "public", emulator_clean.port, timeout=2.0, retries=1)
    sample = asyncio.run(prober.probe_oid("1.3.6.1.2.1.1.1.0"))
    assert sample.responded is True
    assert sample.oid == "1.3.6.1.2.1.1.1.0"
    assert "Emulated" in sample.value
    assert sample.elapsed_ms >= 0


def test_probe_oid_returns_unresponded_sample_on_timeout(emulator_drop_if):
    prober = SnmpProber("127.0.0.1", "public", emulator_drop_if.port, timeout=1.0, retries=0)
    # ifTable OID is dropped
    sample = asyncio.run(prober.probe_oid("1.3.6.1.2.1.2.2.1.1.1"))
    assert sample.responded is False
```

- [ ] **Step 2: Create `tests/detector/conftest.py`**

```python
# trouble-shooter/tests/detector/conftest.py
import pytest
from emulator import EmulatorConfig, EmulatorServer

_CLEAN = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
_SLOW_IF = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.8)
_DROP_IF = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=10.0)


@pytest.fixture(scope="session")
def emulator_clean():
    s = EmulatorServer(_CLEAN)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def emulator_slow_if():
    s = EmulatorServer(_SLOW_IF)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def emulator_drop_if():
    s = EmulatorServer(_DROP_IF)
    s.start()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def reset_detector_emulators(emulator_clean, emulator_slow_if, emulator_drop_if):
    yield
    emulator_clean.reset()
    emulator_slow_if.reset()
    emulator_drop_if.reset()
```

- [ ] **Step 3: Run tests — verify they fail with ImportError**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_prober.py -v 2>&1 | head -20
```
Expected: `ImportError: No module named 'detector.prober'` or similar.

- [ ] **Step 4: Create `detector/prober.py`**

```python
# trouble-shooter/detector/prober.py
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

    async def bulk_walk(
        self, root_oid: str, bulk_size: int
    ) -> AsyncGenerator[Batch, None]:
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
                error_indication, _, __, var_binds = await bulk_cmd(
                    engine,
                    CommunityData(self._community),
                    transport,
                    ContextData(),
                    0,           # nonRepeaters
                    bulk_size,   # maxRepetitions
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
            error_indication, _, __, var_binds = await get_cmd(
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

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_prober.py -v
```
Expected: all tests PASS (slow tests may take 5–15 seconds due to real SNMP delays).

- [ ] **Step 6: Commit**

```bash
git add trouble-shooter/detector/prober.py trouble-shooter/tests/detector/conftest.py trouble-shooter/tests/detector/test_prober.py
git commit -m "feat(detector): add SnmpProber with bulk_walk and probe_oid, integration tests"
```

---

## Task 4: `engine.py` — orchestrator + fake prober tests

**Files:**
- Create: `trouble-shooter/detector/engine.py`
- Create: `trouble-shooter/tests/detector/test_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# trouble-shooter/tests/detector/test_engine.py
import asyncio

import pytest

from detector.classify import validate_buckets
from detector.engine import diagnose
from detector.models import Batch, Bucket, DetectorConfig, Sample, WalkReason

BUCKETS = [Bucket("OK", 500), Bucket("SLOW", 3000), Bucket("CRITICAL", None)]


class FakeProber:
    def __init__(self, batches: list[Batch], samples: dict[str, Sample] | None = None):
        self._batches = batches
        self._samples = samples or {}

    async def bulk_walk(self, root_oid: str, bulk_size: int):
        for batch in self._batches:
            yield batch

    async def probe_oid(self, oid: str) -> Sample:
        return self._samples.get(
            oid, Sample(oid=oid, value="v", elapsed_ms=10.0, responded=True)
        )


def test_diagnose_clean_walk_is_complete():
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
    ])
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert report.complete is True
    assert report.reason == WalkReason.END_OF_MIB
    assert report.summary["OK"] == 2
    assert report.summary.get("SLOW", 0) == 0
    assert len(report.regions) == 0
    assert len(report.oids) == 2


def test_diagnose_timeout_batch_stops_walk():
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "")], elapsed_ms=5000, timed_out=True),
    ])
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert report.complete is False
    assert report.reason == WalkReason.TIMEOUT
    assert report.stopped_at == "1.3.6.1.2.1.2.2.1.1.1"
    assert report.summary.get("TIMEOUT", 0) == 1


def test_diagnose_slow_region_appears_in_regions():
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(
            oids=[("1.3.6.1.2.1.2.2.1.1.1", "a"), ("1.3.6.1.2.1.2.2.1.2.1", "b")],
            elapsed_ms=800,
            timed_out=False,
        ),
    ])
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert len(report.regions) == 1
    assert report.regions[0].prefix == "1.3.6.1.2.1.2.2.1"
    assert report.regions[0].bucket == "SLOW"
    assert report.regions[0].oid_count == 2


def test_diagnose_pinpoint_adds_pinpoint_oid_results():
    slow_oid = "1.3.6.1.2.1.2.2.1.1.1"
    prober = FakeProber(
        batches=[Batch(oids=[(slow_oid, "a")], elapsed_ms=800, timed_out=False)],
        samples={slow_oid: Sample(oid=slow_oid, value="a", elapsed_ms=2500.0, responded=True)},
    )
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=True)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    bulk_results = [o for o in report.oids if o.phase == "bulk"]
    pinpoint_results = [o for o in report.oids if o.phase == "pinpoint"]

    assert len(bulk_results) == 1
    assert len(pinpoint_results) == 1
    assert pinpoint_results[0].oid == slow_oid
    assert pinpoint_results[0].bucket == "SLOW"
    assert pinpoint_results[0].ms == 2500.0


def test_diagnose_pinpoint_skipped_when_disabled():
    slow_oid = "1.3.6.1.2.1.2.2.1.1.1"
    prober = FakeProber(
        batches=[Batch(oids=[(slow_oid, "a")], elapsed_ms=800, timed_out=False)],
        samples={slow_oid: Sample(oid=slow_oid, value="a", elapsed_ms=2500.0, responded=True)},
    )
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert not any(o.phase == "pinpoint" for o in report.oids)


def test_diagnose_budget_exceeded():
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
        Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
    ])
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False, total_timeout=0)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert report.complete is False
    assert report.reason == WalkReason.BUDGET_EXCEEDED


def test_diagnose_stopped_at_is_last_oid():
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "a"), ("1.3.6.1.2.1.1.2.0", "b")], elapsed_ms=100, timed_out=False),
    ])
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert report.stopped_at == "1.3.6.1.2.1.1.2.0"


def test_diagnose_invalid_buckets_raises():
    prober = FakeProber([])
    with pytest.raises(ValueError):
        asyncio.run(diagnose(prober, buckets=[Bucket("OK", 500)], config=DetectorConfig()))


def test_diagnose_pinpoint_unresponded_oid_gets_timeout_bucket():
    slow_oid = "1.3.6.1.2.1.2.2.1.1.1"
    prober = FakeProber(
        batches=[Batch(oids=[(slow_oid, "")], elapsed_ms=800, timed_out=False)],
        samples={slow_oid: Sample(oid=slow_oid, value="", elapsed_ms=1000.0, responded=False)},
    )
    config = DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=True)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    pinpoint = [o for o in report.oids if o.phase == "pinpoint"]
    assert pinpoint[0].bucket == "TIMEOUT"


def test_diagnose_elapsed_total_ms_is_positive():
    prober = FakeProber([
        Batch(oids=[("1.3.6.1.2.1.1.1.0", "a")], elapsed_ms=100, timed_out=False),
    ])
    config = DetectorConfig(pinpoint=False)
    report = asyncio.run(diagnose(prober, buckets=BUCKETS, config=config))

    assert report.elapsed_total_ms >= 0
```

- [ ] **Step 2: Run tests — verify ImportError**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_engine.py -v 2>&1 | head -10
```
Expected: `ImportError: No module named 'detector.engine'`.

- [ ] **Step 3: Create `detector/engine.py`**

```python
# trouble-shooter/detector/engine.py
from time import monotonic

from .classify import bucket_for, find_slow_regions, validate_buckets
from .models import Batch, Bucket, DetectorConfig, DiagnosisReport, OidResult, WalkReason


async def diagnose(prober, *, buckets: list[Bucket], config: DetectorConfig) -> DiagnosisReport:
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

- [ ] **Step 4: Run tests — verify they all pass**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_engine.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add trouble-shooter/detector/engine.py trouble-shooter/tests/detector/test_engine.py
git commit -m "feat(detector): add engine.diagnose orchestrator with fake prober tests"
```

---

## Task 5: API endpoint + smoke test

**Files:**
- Modify: `trouble-shooter/main.py`
- Create: `trouble-shooter/tests/detector/test_api_diagnose.py`

- [ ] **Step 1: Write the failing test**

```python
# trouble-shooter/tests/detector/test_api_diagnose.py


def test_diagnose_endpoint_returns_valid_report(client, emulator_clean):
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


def test_diagnose_endpoint_invalid_host(client):
    resp = client.post("/api/diagnose", json={
        "host": "not_valid!!",
        "community": "public",
        "port": 1161,
        "buckets": [{"name": "OK", "max_ms": 500}, {"name": "CRIT", "max_ms": None}],
    })
    assert resp.status_code == 400


def test_diagnose_endpoint_region_excludes_oids_field(client, emulator_clean):
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
    # Regions in the response must NOT expose the internal oids list
    for region in resp.json()["regions"]:
        assert "prefix" in region
        assert "bucket" in region
        assert "batch_ms" in region
        assert "oid_count" in region
        assert "oids" not in region  # internal field must be excluded
```

- [ ] **Step 2: Run test — verify it fails with 404**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_api_diagnose.py -v 2>&1 | head -20
```
Expected: FAIL because `/api/diagnose` doesn't exist yet (404 or assert error).

- [ ] **Step 3: Add the `/api/diagnose` endpoint to `main.py`**

Add after the existing imports and before `@app.get("/")`:

```python
from detector import SnmpProber, diagnose
from detector.models import Bucket, DetectorConfig
```

Add these new Pydantic models after the existing `WalkRequest` class:

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

Add this new endpoint after `/api/walk`:

```python
@app.post("/api/diagnose")
async def diagnose_device(req: DiagnoseRequest):
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

- [ ] **Step 4: Run the API tests — verify they pass**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/detector/test_api_diagnose.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest -v
```
Expected: all tests PASS (including existing `/api/walk` and `/api/check` tests).

- [ ] **Step 6: Commit**

```bash
git add trouble-shooter/main.py trouble-shooter/tests/detector/test_api_diagnose.py
git commit -m "feat(detector): wire diagnose engine into /api/diagnose FastAPI endpoint"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] §Architecture — prober/classify/engine 3-layer — Task 1–4
- [x] §prober.py — bulk_walk generator, probe_oid — Task 3
- [x] §classify.py — bucket_for, find_slow_regions, validate_buckets, common_prefix — Task 2
- [x] §engine.py — diagnose, Phase 1 + budget + Phase 2 — Task 4
- [x] §Two-phase algorithm — bulk walk loop, reason enum, stopped_at — Task 4
- [x] §Region detection — coalescing adjacent non-OK batches, common prefix — Task 2+4
- [x] §Phase 2 pinpoint — per-OID GET, only in slow regions — Task 4
- [x] §Classification configurable — buckets passed as parameter, no hard-coded defaults — Tasks 2, 4, 5
- [x] §TIMEOUT special bucket — timed_out flag → "TIMEOUT" name, not time-based — Tasks 2, 4
- [x] §Completeness — complete/stopped_at/reason fields — Task 4
- [x] §DetectorConfig — all fields present — Task 1
- [x] §DiagnosisReport — all fields present — Task 1
- [x] §Testing strategy — pure unit tests, fake prober, integration, API smoke — Tasks 2, 4, 3, 5
- [x] §API thin wrapper — /api/diagnose — Task 5

**Type/name consistency:**
- `Batch.oids: list[tuple[str, str]]` — used consistently in classify.py, engine.py, prober.py
- `bucket_for(ms, buckets)` — correct in classify.py and engine.py
- `find_slow_regions(batches, buckets)` — correct in classify.py and engine.py
- `Region.oids` (internal field) — correctly excluded from API output in Task 5
- `WalkReason.value` — correctly serialized as string in API response
- `DetectorConfig.total_timeout` — compared against `monotonic()` seconds (not ms) in engine.py
