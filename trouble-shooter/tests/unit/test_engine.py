from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from trouble_shooter.detector.engine import diagnose
from trouble_shooter.detector.models import Batch, Bucket, DetectorConfig, Sample, WalkReason

BUCKETS = [Bucket("OK", 500), Bucket("SLOW", 3000), Bucket("CRITICAL", None)]


class FakeProber:
    def __init__(self, batches: list[Batch], samples: dict[str, Sample] | None = None) -> None:
        self._batches = batches
        self._samples = samples or {}

    async def bulk_walk(self, root_oid: str, bulk_size: int) -> AsyncIterator[Batch]:  # noqa: ARG002
        for batch in self._batches:
            yield batch

    async def probe_oid(self, oid: str) -> Sample:
        return self._samples.get(oid, Sample(oid=oid, value="v", elapsed_ms=10.0, responded=True))


async def test_diagnose_clean_walk_is_complete() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
            Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
        ]
    )
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    )
    assert report.complete is True
    assert report.reason == WalkReason.END_OF_MIB
    assert report.summary["OK"] == 2
    assert report.summary.get("SLOW", 0) == 0
    assert len(report.regions) == 0
    assert len(report.oids) == 2


async def test_diagnose_timeout_batch_stops_walk() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
            Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "")], elapsed_ms=5000, timed_out=True),
        ]
    )
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    )
    assert report.complete is False
    assert report.reason == WalkReason.TIMEOUT
    assert report.stopped_at == "1.3.6.1.2.1.2.2.1.1.1"
    assert report.summary.get("TIMEOUT", 0) == 1


async def test_diagnose_slow_region_appears_in_regions() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
            Batch(
                oids=[("1.3.6.1.2.1.2.2.1.1.1", "a"), ("1.3.6.1.2.1.2.2.1.2.1", "b")],
                elapsed_ms=800,
                timed_out=False,
            ),
        ]
    )
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    )
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
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=True)
    )
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
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    )
    assert not any(o.phase == "pinpoint" for o in report.oids)


async def test_diagnose_budget_exceeded() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
            Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
        ]
    )
    report = await diagnose(
        prober,
        buckets=BUCKETS,
        config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False, total_timeout=0),
    )
    assert report.complete is False
    assert report.reason == WalkReason.BUDGET_EXCEEDED


async def test_diagnose_stopped_at_is_last_oid() -> None:
    prober = FakeProber(
        [
            Batch(
                oids=[("1.3.6.1.2.1.1.1.0", "a"), ("1.3.6.1.2.1.1.2.0", "b")],
                elapsed_ms=100,
                timed_out=False,
            ),
        ]
    )
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=False)
    )
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
    report = await diagnose(
        prober, buckets=BUCKETS, config=DetectorConfig(root_oid="1.3.6.1.2.1", pinpoint=True)
    )
    pinpoint = [o for o in report.oids if o.phase == "pinpoint"]
    assert pinpoint[0].bucket == "TIMEOUT"


async def test_diagnose_elapsed_total_ms_is_non_negative() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "a")], elapsed_ms=100, timed_out=False),
        ]
    )
    report = await diagnose(prober, buckets=BUCKETS, config=DetectorConfig(pinpoint=False))
    assert report.elapsed_total_ms >= 0
