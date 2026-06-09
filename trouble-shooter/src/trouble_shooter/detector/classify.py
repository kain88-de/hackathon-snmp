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
    for components in zip(*parts, strict=False):
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
