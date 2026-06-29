"""Integration tests for walker.py — uses run_walk + loopback UDP emulator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

import pytest
from traceformat import dump_record
from traceformat.models import Exchange, Header, Summary
from traceformat.vocab import EndReason, EventKind, Violation

from oidtrace.auth import password_to_key
from oidtrace.oid import Oid
from oidtrace.tracefile import read_trace
from oidtrace.walker import WalkSettings, run_walk
from tests.support.emulator import _EMU_ENGINE_ID, EmuDevice, EndOfMib, Quirks

if TYPE_CHECKING:
    from pathlib import Path

    # pyrefly: ignore [untyped-import]
    from jsonschema import Draft202012Validator
    from traceformat import TraceRecord

_EmuFactory = Callable[..., AbstractAsyncContextManager[tuple[str, int]]]


def _validate_all(records: list[TraceRecord], validator: Draft202012Validator) -> None:
    for r in records:
        raw = json.loads(dump_record(r))
        errors = list(validator.iter_errors(raw))
        assert not errors, f"Schema validation failed: {errors[0].message!r} on {raw}"


@pytest.mark.asyncio
async def test_clean_50_oid_walk(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Clean 50-OID walk: header first, summary last, oids_seen==50."""

    device = EmuDevice.simple(n_oids=50)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10),
            path=trace_path,
        )

    assert end_reason == EndReason.COMPLETED

    records = list(read_trace(trace_path))
    assert isinstance(records[0], Header)
    assert isinstance(records[-1], Summary)

    summary = records[-1]
    assert summary.oids_seen == 50
    assert summary.end_reason == str(EndReason.COMPLETED)

    # Distinct OIDs from exchange varbinds
    seen_oids: set[str] = set()
    for r in records:
        if isinstance(r, Exchange) and r.response is not None:
            for vb in r.response.varbinds:
                seen_oids.add(vb.oid.root)
    assert len(seen_oids) == 50

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_v1_clean_20_oid_walk(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """SNMP v1 GetNext walk over a 20-OID emulator → COMPLETED, oids_seen==20."""

    device = EmuDevice.simple(n_oids=20)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(snmp_version="1"),
            path=trace_path,
        )

    assert end_reason == EndReason.COMPLETED

    records = list(read_trace(trace_path))
    assert isinstance(records[0], Header)
    assert isinstance(records[-1], Summary)

    summary = records[-1]
    assert summary.oids_seen == 20
    assert summary.end_reason == str(EndReason.COMPLETED)

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_v3_clean_20_oid_walk(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """SNMPv3 noAuthNoPriv walk over a 20-OID emulator → COMPLETED, oids_seen==20.

    The first exchange must be the discovery probe (pdu=discovery, seq=1).
    """

    device = EmuDevice.simple(n_oids=20)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(snmp_version="3", v3_user="probe", bulk_size=10),
            path=trace_path,
        )

    assert end_reason == EndReason.COMPLETED

    records = list(read_trace(trace_path))
    assert isinstance(records[0], Header)
    assert records[0].snmp.version.value == "3"
    assert isinstance(records[-1], Summary)

    summary = records[-1]
    assert summary.oids_seen == 20
    assert summary.end_reason == str(EndReason.COMPLETED)

    # First exchange is the discovery probe.
    exchange_records = [r for r in records if isinstance(r, Exchange)]
    assert exchange_records[0].seq == 1
    assert exchange_records[0].request.pdu.value == "discovery"
    assert exchange_records[0].request.oids == []
    # The GetBulk loop starts at seq=2.
    assert exchange_records[1].seq == 2
    assert exchange_records[1].request.pdu.value == "getbulk"

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_fixed_request_id_mismatch_completes(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """fixed_request_id=1 on emulator → every exchange gets request-id-mismatch violation."""

    quirks = Quirks(fixed_request_id=1)
    device = EmuDevice.simple(n_oids=10, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10),
            path=trace_path,
        )

    assert end_reason == EndReason.COMPLETED

    records = list(read_trace(trace_path))
    exchange_records = [r for r in records if isinstance(r, Exchange)]
    assert exchange_records, "Expected at least one exchange"

    # Every exchange must have request-id-mismatch
    for exch in exchange_records:
        assert exch.violations is not None, f"Exchange {exch.seq} has no violations"
        assert str(Violation.REQUEST_ID_MISMATCH) in exch.violations, (
            f"Exchange {exch.seq} missing request-id-mismatch"
        )

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_wrap_oid_loop(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Emulator with WRAP end-of-mib → OID_LOOP + event."""

    quirks = Quirks(end_of_mib=EndOfMib.WRAP)
    device = EmuDevice.simple(n_oids=5, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=5),
            path=trace_path,
        )

    assert end_reason == EndReason.OID_LOOP

    records = list(read_trace(trace_path))
    event_records = [r for r in records if r.type == "event"]
    assert any(e.kind == str(EventKind.OID_LOOP_DETECTED) for e in event_records)

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_drop_all_unresponsive(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """drop_all emulator → UNRESPONSIVE after give_up_after exchanges."""

    quirks = Quirks(drop_all=True)
    device = EmuDevice.simple(quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(give_up_after=2, timeout_s=0.05, retries=1),
            path=trace_path,
        )

    assert end_reason == EndReason.UNRESPONSIVE

    records = list(read_trace(trace_path))
    exchange_records = [r for r in records if isinstance(r, Exchange)]

    assert len(exchange_records) == 2

    # Each exchange has retries+1=2 attempts, no response keys
    for exch in exchange_records:
        assert len(exch.attempts) == 2  # retries=1 → 2 sends
        assert exch.response is None

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_time_budget_exceeded(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Slow emulator + budget → TIME_BUDGET_EXCEEDED + event."""
    # 50ms delay per OID under the ifTable prefix, 0.1s budget → exceeds quickly

    slow_prefix = Oid.from_str("1.3.6.1.2.1.2.2.1")  # ifTable (all emulator OIDs are here)
    quirks = Quirks(slow_prefix=slow_prefix, per_oid_delay_s=0.05)
    device = EmuDevice.simple(n_oids=100, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=5, time_budget_s=0.1, timeout_s=1.0),
            path=trace_path,
        )

    assert end_reason == EndReason.TIME_BUDGET_EXCEEDED

    records = list(read_trace(trace_path))
    event_records = [r for r in records if r.type == "event"]
    assert any(e.kind == str(EventKind.TIME_BUDGET_EXCEEDED) for e in event_records)

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_cancellation_interrupted_summary(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """Cancelling mid-walk → file ends with INTERRUPTED summary."""
    # Slow emulator so the walk doesn't finish before cancel

    slow_prefix = Oid.from_str("1.3.6.1.2.1.2.2.1")  # ifTable prefix
    quirks = Quirks(slow_prefix=slow_prefix, per_oid_delay_s=0.05)
    device = EmuDevice.simple(n_oids=100, quirks=quirks)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async def run() -> None:
        async with emulator_factory(device) as (host, port):
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

    records = list(read_trace(trace_path))
    assert records, "No records written before cancellation"
    assert isinstance(records[0], Header)
    assert isinstance(records[-1], Summary)
    assert records[-1].end_reason == str(EndReason.INTERRUPTED)

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_appended_sink_receives_same_records(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """An appended sink receives exactly the records written in order."""

    device = EmuDevice.simple(n_oids=20)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    sink_records: list[TraceRecord] = []
    async with emulator_factory(device) as (host, port):
        await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10),
            path=trace_path,
            sinks=[sink_records.append],
        )

    file_records = list(read_trace(trace_path))
    assert len(sink_records) == len(file_records)

    for s, f in zip(sink_records, file_records, strict=True):
        assert dump_record(s) == dump_record(f)

    _validate_all(sink_records, record_validator)


@pytest.mark.asyncio
async def test_shared_timeline_sent_at_and_summary(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """attempt.sent_at and summary.at use the same zero (shared clock, trap #11)."""

    device = EmuDevice.simple(n_oids=5)
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=5),
            path=trace_path,
        )

    records = list(read_trace(trace_path))
    exchange_records = [r for r in records if isinstance(r, Exchange)]
    assert isinstance(records[-1], Summary)
    summary = records[-1]

    assert exchange_records, "Expected at least one exchange"
    first_attempt_sent_at = exchange_records[0].attempts[0].sent_at.root
    summary_at = summary.at.root

    assert first_attempt_sent_at >= 0.0
    assert summary_at > first_attempt_sent_at, (
        f"summary.at={summary_at} must be > first attempt sent_at={first_attempt_sent_at}"
    )

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_v3_authnopriv_20_oid_walk(
    emulator_factory: _EmuFactory,
    record_validator: Draft202012Validator,
    tmp_path: Path,
) -> None:
    """SNMPv3 authNoPriv walk over a 20-OID auth emulator → COMPLETED, oids_seen==20."""
    kul = password_to_key(b"testpass1", _EMU_ENGINE_ID, "MD5")
    device = EmuDevice.simple(n_oids=20, auth_users={b"authuser": ("MD5", kul)})
    trace_path = tmp_path / "trace.oidtrace.jsonl.gz"

    async with emulator_factory(device) as (host, port):
        end_reason = await run_walk(
            host,
            port,
            settings=WalkSettings(
                snmp_version="3",
                v3_user="authuser",
                v3_auth_proto="MD5",
                v3_auth_pass="testpass1",
                bulk_size=10,
            ),
            path=trace_path,
        )

    assert end_reason == EndReason.COMPLETED

    records = list(read_trace(trace_path))
    assert isinstance(records[-1], Summary)
    summary = records[-1]
    assert summary.oids_seen == 20
    assert summary.end_reason == str(EndReason.COMPLETED)

    _validate_all(records, record_validator)
