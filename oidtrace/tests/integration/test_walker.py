"""Integration tests for walker.py — uses run_walk + loopback UDP emulator."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from traceformat import dump_record
from traceformat.vocab import EndReason, EventKind

from tests.support.emulator import EmuDevice, EndOfMib, Quirks

if TYPE_CHECKING:
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from traceformat import TraceRecord


def _validate_all(records: list[TraceRecord], validator: Draft202012Validator) -> None:
    for r in records:
        raw = json.loads(dump_record(r))
        errors = list(validator.iter_errors(raw))
        assert not errors, f"Schema validation failed: {errors[0].message!r} on {raw}"


@pytest.mark.asyncio
async def test_clean_50_oid_walk(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Clean 50-OID walk: header first, summary last, oids_seen==50."""
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    device = EmuDevice.simple(n_oids=50)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10),
            path=trace_path,
        )

    assert end_reason == EndReason.COMPLETED

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    assert records[0].type == "header"  # type: ignore[union-attr]
    assert records[-1].type == "summary"  # type: ignore[union-attr]

    summary = records[-1]
    assert summary.oids_seen == 50  # type: ignore[union-attr]
    assert summary.end_reason == str(EndReason.COMPLETED)  # type: ignore[union-attr]

    # Distinct OIDs from exchange varbinds
    seen_oids: set[str] = set()
    for r in records:
        if r.type == "exchange" and r.response is not None:  # type: ignore[union-attr]
            for vb in r.response.varbinds:  # type: ignore[union-attr]
                seen_oids.add(vb.oid.root)
    assert len(seen_oids) == 50

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_fixed_request_id_mismatch_completes(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """fixed_request_id=1 on emulator → every exchange gets request-id-mismatch violation."""
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    quirks = Quirks(fixed_request_id=1)
    device = EmuDevice.simple(n_oids=10, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10),
            path=trace_path,
        )

    # Walk still completes (violations are recorded, not fatal)
    assert end_reason == EndReason.COMPLETED

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    exchange_records = [r for r in records if r.type == "exchange"]
    assert exchange_records, "Expected at least one exchange"

    # Every exchange must have request-id-mismatch
    for exch in exchange_records:
        assert exch.violations is not None, f"Exchange {exch.seq} has no violations"  # type: ignore[union-attr]
        assert "request-id-mismatch" in exch.violations, (  # type: ignore[union-attr]
            f"Exchange {exch.seq} missing request-id-mismatch"
        )

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_wrap_oid_loop(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Emulator with WRAP end-of-mib → OID_LOOP + event."""
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    quirks = Quirks(end_of_mib=EndOfMib.WRAP)
    device = EmuDevice.simple(n_oids=5, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=5),
            path=trace_path,
        )

    assert end_reason == EndReason.OID_LOOP

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    event_records = [r for r in records if r.type == "event"]
    assert any(e.kind == str(EventKind.OID_LOOP_DETECTED) for e in event_records)  # type: ignore[union-attr]

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_drop_all_unresponsive(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """drop_all emulator → UNRESPONSIVE after give_up_after exchanges."""
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    quirks = Quirks(drop_all=True)
    device = EmuDevice.simple(quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(give_up_after=2, timeout_s=0.05, retries=1),
            path=trace_path,
        )

    assert end_reason == EndReason.UNRESPONSIVE

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    exchange_records = [r for r in records if r.type == "exchange"]

    # Exactly give_up_after=2 exchanges
    assert len(exchange_records) == 2

    # Each exchange has retries+1=2 attempts, no response keys
    for exch in exchange_records:
        assert len(exch.attempts) == 2  # retries=1 → 2 sends  # type: ignore[union-attr]
        assert exch.response is None  # type: ignore[union-attr]

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_time_budget_exceeded(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Slow emulator + budget → TIME_BUDGET_EXCEEDED + event."""
    # 50ms delay per OID under the ifTable prefix, 0.1s budget → exceeds quickly
    from oidtrace.oid import Oid  # noqa: PLC0415
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    slow_prefix = Oid.from_str("1.3.6.1.2.1.2.2.1")  # ifTable (all emulator OIDs are here)
    quirks = Quirks(slow_prefix=slow_prefix, per_oid_delay_s=0.05)
    device = EmuDevice.simple(n_oids=100, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=5, time_budget_s=0.1, timeout_s=1.0),
            path=trace_path,
        )

    assert end_reason == EndReason.TIME_BUDGET_EXCEEDED

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    event_records = [r for r in records if r.type == "event"]
    assert any(e.kind == str(EventKind.TIME_BUDGET_EXCEEDED) for e in event_records)  # type: ignore[union-attr]

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_cancellation_interrupted_summary(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Cancelling mid-walk → file ends with INTERRUPTED summary."""
    # Slow emulator so the walk doesn't finish before cancel
    from oidtrace.oid import Oid  # noqa: PLC0415
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    slow_prefix = Oid.from_str("1.3.6.1.2.1.2.2.1")  # ifTable prefix
    quirks = Quirks(slow_prefix=slow_prefix, per_oid_delay_s=0.05)
    device = EmuDevice.simple(n_oids=100, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async def run() -> None:
        async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
            await run_walk(
                host,
                port,
                settings=WalkSettings(bulk_size=5, timeout_s=1.0),
                path=trace_path,
            )

    task = asyncio.create_task(run())
    await asyncio.sleep(0.1)  # let it start
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    assert records, "No records written before cancellation"
    assert records[0].type == "header"  # type: ignore[union-attr]
    assert records[-1].type == "summary"  # type: ignore[union-attr]
    assert records[-1].end_reason == str(EndReason.INTERRUPTED)  # type: ignore[union-attr]

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_appended_sink_receives_same_records(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """An appended sink receives exactly the records written in order."""
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    device = EmuDevice.simple(n_oids=20)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    sink_records: list[TraceRecord] = []
    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10),
            path=trace_path,
            sinks=[sink_records.append],
        )

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    file_records = list(read_trace(trace_path))
    assert len(sink_records) == len(file_records)

    # Records in same order (compare by JSON representation)
    for s, f in zip(sink_records, file_records, strict=True):
        assert dump_record(s) == dump_record(f)

    _validate_all(sink_records, record_validator)


@pytest.mark.asyncio
async def test_shared_timeline_sent_at_and_summary(
    emulator_factory: object,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """attempt.sent_at and summary.at use the same zero (shared clock, trap #11)."""
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    device = EmuDevice.simple(n_oids=5)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):  # type: ignore[attr-defined]
        await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=5),
            path=trace_path,
        )

    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    records = list(read_trace(trace_path))
    exchange_records = [r for r in records if r.type == "exchange"]
    summary = records[-1]

    assert exchange_records, "Expected at least one exchange"
    first_attempt_sent_at = exchange_records[0].attempts[0].sent_at.root  # type: ignore[union-attr]
    summary_at = summary.at.root  # type: ignore[union-attr]

    # Both are relative to the same zero: sent_at must be < summary.at
    assert first_attempt_sent_at >= 0.0
    assert summary_at > first_attempt_sent_at, (
        f"summary.at={summary_at} must be > first attempt sent_at={first_attempt_sent_at}"
    )

    _validate_all(records, record_validator)
