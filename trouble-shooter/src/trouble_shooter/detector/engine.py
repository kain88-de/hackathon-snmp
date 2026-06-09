from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

from .classify import bucket_for, find_slow_regions, validate_buckets
from .models import Batch, Bucket, DetectorConfig, DiagnosisReport, OidResult, Sample, WalkReason

log = logging.getLogger(__name__)


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

    log.info("bulk walk starting at %s (bulk_size=%d)", config.root_oid, config.bulk_size)
    batch_count = 0
    async for batch in prober.bulk_walk(config.root_oid, config.bulk_size):
        batches.append(batch)
        batch_count += 1
        b_name = "TIMEOUT" if batch.timed_out else bucket_for(batch.elapsed_ms, buckets)
        for oid, value in batch.oids:
            oid_results.append(
                OidResult(oid=oid, value=value, bucket=b_name, ms=batch.elapsed_ms, phase="bulk")
            )
        if batch.oids:
            stopped_at = batch.oids[-1][0]
        log.info(
            "batch #%d: %d OIDs, %.0fms [%s]  last=%s",
            batch_count,
            len(batch.oids),
            batch.elapsed_ms,
            b_name,
            stopped_at,
        )
        if batch.timed_out:
            reason = WalkReason.TIMEOUT
            log.warning("batch #%d timed out — stopping walk", batch_count)
            break
        if (monotonic() - t_start) > config.total_timeout:
            reason = WalkReason.BUDGET_EXCEEDED
            log.warning("total_timeout exceeded after %d batches — stopping walk", batch_count)
            break

    log.info(
        "bulk walk done: %d batches, %d OIDs, reason=%s",
        batch_count,
        len(oid_results),
        reason.value,
    )
    regions = find_slow_regions(batches, buckets)

    if config.pinpoint:
        log.info("pinpoint phase: %d slow region(s)", len(regions))
        for region in regions:
            log.info("  probing region %s (%d OIDs)", region.prefix, len(region.oids))
            for oid in region.oids:
                sample = await prober.probe_oid(oid)
                b_name = bucket_for(sample.elapsed_ms, buckets) if sample.responded else "TIMEOUT"
                log.info("    %s → %.0fms [%s]", oid, sample.elapsed_ms, b_name)
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


def _oid_dict(o: OidResult) -> dict[str, object]:
    return {"oid": o.oid, "value": o.value, "bucket": o.bucket, "ms": o.ms, "phase": o.phase}


async def diagnose_stream(
    prober: Prober,
    *,
    buckets: list[Bucket],
    config: DetectorConfig,
) -> AsyncGenerator[dict[str, object], None]:
    validate_buckets(buckets)
    t_start = monotonic()
    batches: list[Batch] = []
    all_oid_results: list[OidResult] = []
    reason = WalkReason.END_OF_MIB
    stopped_at = config.root_oid

    log.info("bulk walk starting at %s (bulk_size=%d)", config.root_oid, config.bulk_size)
    batch_count = 0
    async for batch in prober.bulk_walk(config.root_oid, config.bulk_size):
        batches.append(batch)
        batch_count += 1
        b_name = "TIMEOUT" if batch.timed_out else bucket_for(batch.elapsed_ms, buckets)
        batch_results = [
            OidResult(oid=oid, value=value, bucket=b_name, ms=batch.elapsed_ms, phase="bulk")
            for oid, value in batch.oids
        ]
        all_oid_results.extend(batch_results)
        if batch.oids:
            stopped_at = batch.oids[-1][0]
        log.info(
            "batch #%d: %d OIDs, %.0fms [%s]  last=%s",
            batch_count, len(batch.oids), batch.elapsed_ms, b_name, stopped_at,
        )
        yield {
            "type": "oids",
            "oids": [_oid_dict(o) for o in batch_results],
        }
        if batch.timed_out:
            reason = WalkReason.TIMEOUT
            log.warning("batch #%d timed out — stopping walk", batch_count)
            break
        if (monotonic() - t_start) > config.total_timeout:
            reason = WalkReason.BUDGET_EXCEEDED
            log.warning("total_timeout exceeded after %d batches — stopping walk", batch_count)
            break

    log.info("bulk walk done: %d batches, %d OIDs, reason=%s", batch_count, len(all_oid_results), reason.value)
    regions = find_slow_regions(batches, buckets)

    if config.pinpoint:
        log.info("pinpoint phase: %d slow region(s)", len(regions))
        for region in regions:
            log.info("  probing region %s (%d OIDs)", region.prefix, len(region.oids))
            for oid in region.oids:
                sample = await prober.probe_oid(oid)
                b_name = bucket_for(sample.elapsed_ms, buckets) if sample.responded else "TIMEOUT"
                log.info("    %s → %.0fms [%s]", oid, sample.elapsed_ms, b_name)
                result = OidResult(
                    oid=sample.oid, value=sample.value, bucket=b_name,
                    ms=sample.elapsed_ms, phase="pinpoint",
                )
                all_oid_results.append(result)
                yield {
                    "type": "oids",
                    "oids": [_oid_dict(result)],
                }

    summary: dict[str, int] = {b.name: 0 for b in buckets}
    summary["TIMEOUT"] = 0
    for o in all_oid_results:
        summary[o.bucket] = summary.get(o.bucket, 0) + 1

    yield {
        "type": "done",
        "complete": reason == WalkReason.END_OF_MIB,
        "stopped_at": stopped_at,
        "reason": reason.value,
        "summary": summary,
        "regions": [
            {"prefix": r.prefix, "bucket": r.bucket, "batch_ms": r.batch_ms, "oid_count": r.oid_count}
            for r in regions
        ],
        "elapsed_total_ms": (monotonic() - t_start) * 1000,
    }
