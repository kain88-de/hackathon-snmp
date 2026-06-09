from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from .classify import bucket_for, find_slow_regions, validate_buckets
from .models import Batch, Bucket, DetectorConfig, DiagnosisReport, OidResult, Sample, WalkReason


@runtime_checkable
class Prober(Protocol):
    def bulk_walk(self, root_oid: str, bulk_size: int) -> AsyncIterator[Batch]: ...
    async def probe_oid(self, oid: str) -> Sample: ...


async def diagnose(
    prober: Prober, *, buckets: list[Bucket], config: DetectorConfig
) -> DiagnosisReport:
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
            oid_results.append(
                OidResult(oid=oid, value=value, bucket=b_name, ms=batch.elapsed_ms, phase="bulk")
            )
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
                oid_results.append(
                    OidResult(
                        oid=sample.oid,
                        value=sample.value,
                        bucket=b_name,
                        ms=sample.elapsed_ms,
                        phase="pinpoint",
                    )
                )

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
