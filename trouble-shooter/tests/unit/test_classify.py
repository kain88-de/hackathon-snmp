import pytest

from trouble_shooter.detector.classify import (
    bucket_for,
    common_prefix,
    find_slow_regions,
    validate_buckets,
)
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
        Batch(
            oids=[("1.3.6.1.2.1.2.2.1.1.1", "a"), ("1.3.6.1.2.1.2.2.1.2.1", "b")],
            elapsed_ms=800,
            timed_out=False,
        ),
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
        Batch(oids=[("1.3.6.1.2.1.3.1.1", "b")], elapsed_ms=100, timed_out=False),  # OK gap
        Batch(oids=[("1.3.6.1.2.1.4.1.1", "c")], elapsed_ms=600, timed_out=False),
    ]
    assert len(find_slow_regions(batches, BUCKETS)) == 2


def test_find_slow_regions_worst_bucket_is_critical() -> None:
    batches = [
        Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "a")], elapsed_ms=800, timed_out=False),  # SLOW
        Batch(oids=[("1.3.6.1.2.1.2.2.1.2.1", "b")], elapsed_ms=4000, timed_out=False),  # CRITICAL
    ]
    regions = find_slow_regions(batches, BUCKETS)
    assert len(regions) == 1
    assert regions[0].bucket == "CRITICAL"
