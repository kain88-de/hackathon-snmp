"""Integration tests for walker.py — real UdpTransport + emulator.

All assertions on written trace records (read_trace) + returned EndReason.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from typing import TYPE_CHECKING, Any

import pytest
from traceformat.models import Event, Exchange, Header, Summary
from traceformat.vocab import EndReason, Violation

from oidtrace.oid import Oid
from oidtrace.tracefile import read_trace
from oidtrace.walker import WalkSettings, run_walk
from tests.support.emulator import EmuDevice, EndOfMib, Quirks

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from traceformat import TraceRecord


# ---------------------------------------------------------------------------
# Helpers


def _records(path: Path) -> list[TraceRecord]:
    return list(read_trace(path))


def _validate_all_from_path(path: Path, record_validator: Any) -> None:
    with gzip.open(path, "rb") as gz:
        for raw in gz:
            line = raw.decode().rstrip("\n")
            if line:
                record_validator.validate(json.loads(line))


def _exchanges(records: list[TraceRecord]) -> list[Exchange]:
    return [r for r in records if isinstance(r, Exchange)]


def _events(records: list[TraceRecord]) -> list[Event]:
    return [r for r in records if isinstance(r, Event)]


# ---------------------------------------------------------------------------
# Test: clean 50-OID walk -> COMPLETED


async def test_clean_walk_completed(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
    record_validator: Any,
) -> None:
    """50-OID device: COMPLETED, header first, summary last, oids_seen == 50."""
    device = EmuDevice.simple(n_oids=50)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=10,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    async with emulator_factory(device) as (host, port):
        reason = await run_walk(host, port, settings=settings, path=path)

    assert reason == EndReason.COMPLETED

    records = _records(path)
    assert isinstance(records[0], Header)
    assert isinstance(records[-1], Summary)

    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.COMPLETED)
    assert summary.oids_seen == 50

    # All OIDs returned by exchanges are distinct
    seen: set[str] = set()
    for exc in _exchanges(records):
        if exc.response is not None:
            for vb in exc.response.varbinds:
                if vb.vtype not in {"EndOfMibView", "NoSuchObject", "NoSuchInstance"}:
                    seen.add(str(vb.oid))
    assert len(seen) == 50

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: fixed_request_id -> REQUEST_ID_MISMATCH violation in every exchange


async def test_fixed_request_id_violations(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
    record_validator: Any,
) -> None:
    """fixed_request_id=1: walk COMPLETES, every exchange has request-id-mismatch."""
    device = EmuDevice.simple(n_oids=20, quirks=Quirks(fixed_request_id=1))
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=10,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    async with emulator_factory(device) as (host, port):
        reason = await run_walk(host, port, settings=settings, path=path)

    assert reason == EndReason.COMPLETED

    records = _records(path)
    exchanges = _exchanges(records)
    assert len(exchanges) > 0

    for exc in exchanges:
        if exc.response is not None:
            # Every response carries request_id=1
            assert exc.response.request_id == 1
            assert exc.violations is not None
            assert str(Violation.REQUEST_ID_MISMATCH) in exc.violations

    summary = records[-1]
    assert isinstance(summary, Summary)
    mismatch_count = summary.violation_counts.get(str(Violation.REQUEST_ID_MISMATCH), 0)
    assert mismatch_count == len([e for e in exchanges if e.response is not None])

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: EndOfMib.WRAP -> OID_LOOP + event


async def test_end_of_mib_wrap_oid_loop(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
    record_validator: Any,
) -> None:
    """EndOfMib.WRAP causes the walk to loop and end with OID_LOOP."""
    device = EmuDevice.simple(n_oids=10, quirks=Quirks(end_of_mib=EndOfMib.WRAP))
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=10,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    async with emulator_factory(device) as (host, port):
        reason = await run_walk(host, port, settings=settings, path=path)

    assert reason == EndReason.OID_LOOP

    records = _records(path)
    events = _events(records)
    assert any(e.kind == "oid-loop-detected" for e in events)

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: drop_all + give_up_after=2 -> UNRESPONSIVE, exactly 2 exchanges


async def test_drop_all_unresponsive(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
    record_validator: Any,
) -> None:
    """drop_all + give_up_after=2, retries=0 -> UNRESPONSIVE, exactly 2 exchanges."""
    device = EmuDevice.simple(n_oids=10, quirks=Quirks(drop_all=True))
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=5,
        timeout_s=0.1,
        retries=1,  # retries+1 = 2 attempts per exchange
        start_oid=Oid.from_str("1.3.6.1"),
        give_up_after=2,
    )

    async with emulator_factory(device) as (host, port):
        reason = await run_walk(host, port, settings=settings, path=path)

    assert reason == EndReason.UNRESPONSIVE

    records = _records(path)
    exchanges = _exchanges(records)
    assert len(exchanges) == 2

    # All attempts have no response
    for exc in exchanges:
        assert exc.response is None
        # Each exchange has retries+1 = 2 attempts
        assert len(exc.attempts) == 2

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: slow device + time_budget_s -> TIME_BUDGET_EXCEEDED + event


async def test_time_budget_exceeded(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
    record_validator: Any,
) -> None:
    """A slow device causes TIME_BUDGET_EXCEEDED when time_budget_s elapses."""
    slow_prefix = Oid.from_str("1.3.6.1.2.1.2.2.1")
    device = EmuDevice.simple(
        n_oids=100,
        quirks=Quirks(slow_prefix=slow_prefix, per_oid_delay_s=0.1),
    )
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
        time_budget_s=0.15,  # budget just a bit over one slow response
    )

    async with emulator_factory(device) as (host, port):
        reason = await run_walk(host, port, settings=settings, path=path)

    assert reason == EndReason.TIME_BUDGET_EXCEEDED

    records = _records(path)
    events = _events(records)
    assert any(e.kind == "time-budget-exceeded" for e in events)

    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.TIME_BUDGET_EXCEEDED)

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: cancellation mid-walk -> INTERRUPTED + summary at end


async def test_cancellation_interrupted(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
    record_validator: Any,
) -> None:
    """Cancelling the walk task produces a summary with end_reason=interrupted."""
    slow_prefix = Oid.from_str("1.3.6.1.2.1.2.2.1")
    device = EmuDevice.simple(
        n_oids=100,
        quirks=Quirks(slow_prefix=slow_prefix, per_oid_delay_s=0.2),
    )
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    async with emulator_factory(device) as (host, port):
        task = asyncio.create_task(run_walk(host, port, settings=settings, path=path))
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    records = _records(path)
    assert len(records) >= 2  # at minimum header + summary
    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.INTERRUPTED)

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: on_record receives exactly the records written in order


async def test_on_record_matches_file(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
) -> None:
    """on_record callback receives exactly the records written to the trace file."""
    device = EmuDevice.simple(n_oids=10)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=5,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    streamed: list[Any] = []
    async with emulator_factory(device) as (host, port):
        await run_walk(
            host,
            port,
            settings=settings,
            path=path,
            sinks=[streamed.append],
        )

    file_records = _records(path)
    assert len(streamed) == len(file_records)
    # Types match in order
    for cb, fr in zip(streamed, file_records, strict=True):
        assert type(cb) is type(fr)
