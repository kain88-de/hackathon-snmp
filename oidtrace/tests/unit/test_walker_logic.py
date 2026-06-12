"""Unit tests for walker.py — FakeTransport, no real I/O.

All exchange responses are built with codec.encode_response so they
reflect real wire format, then replayed by FakeTransport.

Every test validates all produced records against the JSON schema via
the record_validator fixture.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from traceformat import dump_record
from traceformat.vocab import EndReason, EventKind, Violation

from oidtrace.codec import encode_response
from oidtrace.oid import Oid
from oidtrace.transport import Attempt, ExchangeIO

if TYPE_CHECKING:
    from collections.abc import Callable

    from jsonschema import Draft202012Validator
    from traceformat import TraceRecord


# ---------------------------------------------------------------------------
# FakeTransport
# ---------------------------------------------------------------------------


@dataclass
class FakeTransport:
    """Replays scripted ExchangeIO responses.

    Implements the Transport protocol: async exchange(raw, *, timeout_s, retries).
    Responses are consumed in order; AssertionError if more exchanges are made
    than scripted.
    """

    responses: list[ExchangeIO] = field(default_factory=list)
    _index: int = field(default=0, init=False)

    async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO:  # noqa: ARG002
        assert self._index < len(self.responses), (
            f"FakeTransport exhausted at index {self._index}: no more scripted responses"
        )
        result = self.responses[self._index]
        self._index += 1
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_START_OID = Oid.from_str("1.3.6.1")
_OID_A = Oid.from_str("1.3.6.1.2.1.1.1.0")
_OID_B = Oid.from_str("1.3.6.1.2.1.1.2.0")
_OID_C = Oid.from_str("1.3.6.1.2.1.1.3.0")
_INTEGER_TAG = 0x02


def _make_rel(start: float = 0.0) -> Callable[[], float]:
    """Return a monotonically-increasing clock starting at start."""
    t = [start]

    def rel() -> float:
        v = t[0]
        t[0] += 0.001
        return v

    return rel


def _response_exchange(oids: list[Oid], request_id: int = 42) -> ExchangeIO:
    """Build an ExchangeIO with a real encoded response."""
    varbinds = [(oid, _INTEGER_TAG, b"\x00\x00\x00\x01") for oid in oids]
    raw = encode_response(request_id, varbinds)
    return ExchangeIO(
        attempts=(Attempt(sent_at=0.001, received_at=0.002),),
        response=(0.002, raw),
        strays=(),
    )


def _eom_exchange(after_oid: Oid, request_id: int = 42) -> ExchangeIO:
    """EndOfMibView response (tag 0x82) after the given OID."""
    raw = encode_response(request_id, [(after_oid, 0x82, b"")])
    return ExchangeIO(
        attempts=(Attempt(sent_at=0.001, received_at=0.002),),
        response=(0.002, raw),
        strays=(),
    )


def _no_response_exchange() -> ExchangeIO:
    """Timed-out exchange with no response."""
    return ExchangeIO(
        attempts=(Attempt(sent_at=0.001),),
        response=None,
        strays=(),
    )


def _validate_all(records: list[TraceRecord], validator: Draft202012Validator) -> None:
    for r in records:
        raw = json.loads(dump_record(r))
        errors = list(validator.iter_errors(raw))
        assert not errors, f"Schema validation failed: {errors[0].message!r} on {raw}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _default_settings() -> object:
    """Import WalkSettings with defaults."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    return WalkSettings()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def _collect(transport: FakeTransport, **kw: object) -> list[TraceRecord]:
    """Run walk_records and collect all yielded records."""
    from oidtrace.walker import WalkSettings, walk_records  # noqa: PLC0415

    settings = kw.pop("settings", WalkSettings())
    rel = kw.pop("rel", _make_rel())
    records: list[TraceRecord] = []
    async with aclosing(
        walk_records(transport, rel=rel, settings=settings, **kw)  # type: ignore[arg-type]
    ) as gen:
        async for r in gen:
            records.append(r)
    return records


@pytest.mark.asyncio
async def test_record_order_header_first_summary_last(
    record_validator: Draft202012Validator,
) -> None:
    """Header is always first; Summary is always last."""
    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A]),
            _eom_exchange(_OID_A),
        ]
    )
    records = await _collect(transport)

    assert records[0].type == "header"  # type: ignore[union-attr]
    assert records[-1].type == "summary"  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_summary_stats_match_exchanges(
    record_validator: Draft202012Validator,
) -> None:
    """Summary.exchanges and oids_seen match what was observed."""
    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A, _OID_B]),
            _eom_exchange(_OID_B),
        ]
    )
    records = await _collect(transport)

    summary = records[-1]
    assert summary.type == "summary"  # type: ignore[union-attr]
    assert summary.exchanges == 2  # type: ignore[union-attr]
    assert summary.oids_seen == 2  # type: ignore[union-attr]
    assert summary.end_reason == str(EndReason.COMPLETED)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_early_break_and_aclose_no_summary(
    record_validator: Draft202012Validator,
) -> None:
    """Breaking out of the loop (partial consumer) yields no Summary."""
    from oidtrace.walker import WalkSettings, walk_records  # noqa: PLC0415

    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A]),
            _response_exchange([_OID_B]),
            _eom_exchange(_OID_B),
        ]
    )
    records: list[TraceRecord] = []
    gen = walk_records(transport, rel=_make_rel(), settings=WalkSettings())
    async with aclosing(gen):
        async for r in gen:
            records.append(r)
            if r.type == "exchange":  # type: ignore[union-attr]
                break  # stop after first exchange

    assert records[-1].type != "summary"  # type: ignore[union-attr]
    types = [r.type for r in records]  # type: ignore[union-attr]
    assert "summary" not in types
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_explicit_aclose_no_exception(
    record_validator: Draft202012Validator,
) -> None:
    """Calling aclose() directly does not raise."""
    from oidtrace.walker import WalkSettings, walk_records  # noqa: PLC0415

    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A]),
        ]
    )
    gen = walk_records(transport, rel=_make_rel(), settings=WalkSettings())
    records: list[TraceRecord] = []
    async for r in gen:
        records.append(r)
        if r.type == "header":  # type: ignore[union-attr]
            break
    await gen.aclose()  # must not raise
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_end_of_mib_view_completed(
    record_validator: Draft202012Validator,
) -> None:
    """EndOfMibView (tag 0x82) terminates with COMPLETED."""
    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A]),
            _eom_exchange(_OID_A),
        ]
    )
    records = await _collect(transport)

    summary = records[-1]
    assert summary.type == "summary"  # type: ignore[union-attr]
    assert summary.end_reason == str(EndReason.COMPLETED)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_left_subtree_oid_completed(
    record_validator: Draft202012Validator,
) -> None:
    """Response with OID outside start_oid subtree → COMPLETED."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    outside_oid = Oid.from_str("1.3.6.2.1.1.1.0")  # outside 1.3.6.1 subtree
    transport = FakeTransport(
        responses=[
            _response_exchange([outside_oid]),
        ]
    )
    records = await _collect(transport, settings=WalkSettings(start_oid=_START_OID))

    summary = records[-1]
    assert summary.type == "summary"  # type: ignore[union-attr]
    assert summary.end_reason == str(EndReason.COMPLETED)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_oid_not_increasing_loop(
    record_validator: Draft202012Validator,
) -> None:
    """OID wrapping (non-increasing) → OID_LOOP_DETECTED event + OID_LOOP summary."""
    # First response goes forward; second wraps back
    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_B]),
            _response_exchange([_OID_A]),  # non-increasing: _OID_A < _OID_B
        ]
    )
    records = await _collect(transport)

    types = [r.type for r in records]  # type: ignore[union-attr]
    assert "event" in types

    event = next(r for r in records if r.type == "event")  # type: ignore[union-attr]
    assert event.kind == str(EventKind.OID_LOOP_DETECTED)  # type: ignore[union-attr]

    summary = records[-1]
    assert summary.end_reason == str(EndReason.OID_LOOP)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_give_up_unresponsive(
    record_validator: Draft202012Validator,
) -> None:
    """Consecutive no-response exchanges → UNRESPONSIVE after give_up_after."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    settings = WalkSettings(give_up_after=2, timeout_s=0.01, retries=0)
    transport = FakeTransport(
        responses=[
            _no_response_exchange(),
            _no_response_exchange(),
        ]
    )
    records = await _collect(transport, settings=settings)

    summary = records[-1]
    assert summary.end_reason == str(EndReason.UNRESPONSIVE)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_give_up_with_recovery_resets_count(
    record_validator: Draft202012Validator,
) -> None:
    """A valid response resets the give_up counter; subsequent silence still works."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    settings = WalkSettings(give_up_after=2, timeout_s=0.01, retries=0)
    transport = FakeTransport(
        responses=[
            _no_response_exchange(),  # 1 miss
            _response_exchange([_OID_A]),  # recovery — resets counter
            _no_response_exchange(),  # 1 miss again
            _no_response_exchange(),  # 2 misses → UNRESPONSIVE
        ]
    )
    records = await _collect(transport, settings=settings)

    summary = records[-1]
    assert summary.end_reason == str(EndReason.UNRESPONSIVE)  # type: ignore[union-attr]
    # 4 exchanges total
    assert summary.exchanges == 4  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_malformed_response_adds_violation(
    record_validator: Draft202012Validator,
) -> None:
    """Malformed BER in response → MALFORMED_BER violation on the exchange."""
    junk_raw = b"\x00" * 20
    malformed_exchange = ExchangeIO(
        attempts=(Attempt(sent_at=0.001, received_at=0.002),),
        response=(0.002, junk_raw),
        strays=(),
    )
    transport = FakeTransport(
        responses=[
            malformed_exchange,
            _eom_exchange(_START_OID),
        ]
    )
    records = await _collect(transport)

    exchange_records = [r for r in records if r.type == "exchange"]
    first_exchange = exchange_records[0]
    assert first_exchange.violations is not None  # type: ignore[union-attr]
    assert str(Violation.MALFORMED_BER) in first_exchange.violations  # type: ignore[union-attr]
    assert first_exchange.malformed is not None  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_malformed_increments_give_up_count(
    record_validator: Draft202012Validator,
) -> None:
    """Malformed responses count toward give_up_after (same as no-response)."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    settings = WalkSettings(give_up_after=2, timeout_s=0.01, retries=0)
    junk = b"\x00" * 5
    transport = FakeTransport(
        responses=[
            ExchangeIO(
                attempts=(Attempt(sent_at=0.001, received_at=0.002),),
                response=(0.002, junk),
                strays=(),
            ),
            ExchangeIO(
                attempts=(Attempt(sent_at=0.003, received_at=0.004),),
                response=(0.004, junk),
                strays=(),
            ),
        ]
    )
    records = await _collect(transport, settings=settings)

    summary = records[-1]
    assert summary.end_reason == str(EndReason.UNRESPONSIVE)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_icmp_attempts_appear_in_exchange(
    record_validator: Draft202012Validator,
) -> None:
    """ICMP error attempts are reflected in exchange attempt list."""
    from traceformat.vocab import AttemptError  # noqa: PLC0415

    from oidtrace.transport import Attempt  # noqa: PLC0415

    icmp_exchange = ExchangeIO(
        attempts=(Attempt(sent_at=0.001, error=AttemptError.ICMP_PORT_UNREACHABLE),),
        response=None,
        strays=(),
    )
    transport = FakeTransport(
        responses=[
            icmp_exchange,
            icmp_exchange,
            icmp_exchange,
        ]
    )
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    settings = WalkSettings(give_up_after=3)
    records = await _collect(transport, settings=settings)

    exchange_records = [r for r in records if r.type == "exchange"]
    first = exchange_records[0]
    # Attempt has error set
    assert first.attempts[0].error is not None  # type: ignore[union-attr]
    assert first.attempts[0].received_at is None  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_walk_with_transport_cancellation_emits_interrupted_summary(
    record_validator: Draft202012Validator,
) -> None:
    """CancelledError mid-walk → INTERRUPTED summary emitted to sinks, error re-raised."""
    from oidtrace.walker import WalkSettings, walk_with_transport  # noqa: PLC0415

    # Infinite no-response to stall the walk
    class SlowTransport:
        async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO:  # noqa: ARG002
            await asyncio.sleep(10.0)  # will be cancelled
            return _no_response_exchange()

    sinks_received: list[TraceRecord] = []

    async def run() -> None:
        await walk_with_transport(
            SlowTransport(),
            rel=_make_rel(),
            settings=WalkSettings(timeout_s=10.0, retries=0),
            sinks=[sinks_received.append],
            label=None,
            session_id="test-session",
            run=1,
            runs_total=1,
        )

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)  # let it start
    task.cancel()
    with pytest.raises((asyncio.CancelledError, BaseException)):
        await task

    # Last record in sinks must be summary with INTERRUPTED
    assert sinks_received, "No records emitted before cancellation"
    last = sinks_received[-1]
    assert last.type == "summary"  # type: ignore[union-attr]
    assert last.end_reason == str(EndReason.INTERRUPTED)  # type: ignore[union-attr]
    _validate_all(sinks_received, record_validator)


@pytest.mark.asyncio
async def test_logging_privacy_no_community_in_logs(
    caplog: pytest.LogCaptureFixture,
    record_validator: Draft202012Validator,
) -> None:
    """Community string must NEVER appear in any log record."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    secret_community = b"s3cret-community"
    settings = WalkSettings(community=secret_community)
    transport = FakeTransport(
        responses=[
            _eom_exchange(_START_OID),
        ]
    )
    with caplog.at_level(logging.DEBUG):
        records = await _collect(transport, settings=settings)

    # Check no log record contains the community string
    for log_record in caplog.records:
        msg = log_record.getMessage()
        assert "s3cret-community" not in msg, f"Community string leaked into log: {msg!r}"
        assert secret_community.decode() not in msg

    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_logging_info_start_and_end(
    caplog: pytest.LogCaptureFixture,
    record_validator: Draft202012Validator,
) -> None:
    """Walker emits INFO log at start and end of walk."""
    transport = FakeTransport(
        responses=[
            _eom_exchange(_START_OID),
        ]
    )
    with caplog.at_level(logging.INFO, logger="oidtrace.walker"):
        records = await _collect(transport)

    info_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("start" in m.lower() or "walk" in m.lower() for m in info_msgs), (
        f"Expected INFO start log, got: {info_msgs}"
    )
    assert any(
        "completed" in m.lower()
        or "end" in m.lower()
        or "unresponsive" in m.lower()
        or "loop" in m.lower()
        or "budget" in m.lower()
        or "interrupt" in m.lower()
        for m in info_msgs
    ), f"Expected INFO end log, got: {info_msgs}"
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_walkstats_observe_accumulates(
    record_validator: Draft202012Validator,
) -> None:
    """WalkStats.observe accumulates exchanges and oid counts."""
    from oidtrace.walker import WalkSettings, WalkStats, walk_records  # noqa: PLC0415

    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A, _OID_B]),
            _eom_exchange(_OID_B),
        ]
    )
    stats = WalkStats()
    records_collected: list[TraceRecord] = []
    async with aclosing(walk_records(transport, rel=_make_rel(), settings=WalkSettings())) as gen:
        async for r in gen:
            stats.observe(r)
            records_collected.append(r)

    assert stats.exchanges == 2
    assert stats.oids_seen >= 2  # may be higher due to bulk_size overshoot
    _validate_all(records_collected, record_validator)


@pytest.mark.asyncio
async def test_time_budget_exceeded(
    record_validator: Draft202012Validator,
) -> None:
    """Walk terminates TIME_BUDGET_EXCEEDED when rel() exceeds time_budget_s."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    # Use a clock that jumps far ahead on second call
    calls = [0]

    def fast_clock() -> float:
        calls[0] += 1
        # Budget is 0.1s; after first call return 0.0, then jump past budget
        if calls[0] <= 2:
            return 0.0
        return 1.0  # past 0.1s budget

    settings = WalkSettings(time_budget_s=0.1)
    transport = FakeTransport(
        responses=[
            _response_exchange([_OID_A]),
            _response_exchange([_OID_B]),
            _response_exchange([_OID_C]),
        ]
    )
    records = await _collect(transport, rel=fast_clock, settings=settings)

    summary = records[-1]
    assert summary.end_reason == str(EndReason.TIME_BUDGET_EXCEEDED)  # type: ignore[union-attr]

    types = [r.type for r in records]  # type: ignore[union-attr]
    assert "event" in types
    event = next(r for r in records if r.type == "event")  # type: ignore[union-attr]
    assert event.kind == str(EventKind.TIME_BUDGET_EXCEEDED)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_walk_with_transport_returns_end_reason(
    record_validator: Draft202012Validator,
) -> None:
    """walk_with_transport returns the EndReason from the final Summary."""
    from oidtrace.walker import WalkSettings, walk_with_transport  # noqa: PLC0415

    transport = FakeTransport(
        responses=[
            _eom_exchange(_START_OID),
        ]
    )
    sinks_received: list[TraceRecord] = []
    result = await walk_with_transport(
        transport,
        rel=_make_rel(),
        settings=WalkSettings(),
        sinks=[sinks_received.append],
        label=None,
        session_id="test-session",
        run=1,
        runs_total=1,
    )
    assert result == EndReason.COMPLETED
    _validate_all(sinks_received, record_validator)


@pytest.mark.asyncio
async def test_no_data_response_completed(
    record_validator: Draft202012Validator,
) -> None:
    """Empty varbinds in response → COMPLETED."""
    empty_raw = encode_response(42, [])
    empty_exchange = ExchangeIO(
        attempts=(Attempt(sent_at=0.001, received_at=0.002),),
        response=(0.002, empty_raw),
        strays=(),
    )
    transport = FakeTransport(responses=[empty_exchange])
    records = await _collect(transport)

    summary = records[-1]
    assert summary.end_reason == str(EndReason.COMPLETED)  # type: ignore[union-attr]
    _validate_all(records, record_validator)


@pytest.mark.asyncio
async def test_walk_settings_bulk_size_validation() -> None:
    """WalkSettings with bulk_size=0 raises ValueError."""
    from oidtrace.walker import WalkSettings  # noqa: PLC0415

    with pytest.raises(ValueError, match="bulk_size"):
        WalkSettings(bulk_size=0)


@pytest.mark.asyncio
async def test_duplicate_response_stray_violation(
    record_validator: Draft202012Validator,
) -> None:
    """Duplicate datagram in strays → DUPLICATE_RESPONSE violation."""
    varbinds = [(_OID_A, _INTEGER_TAG, b"\x00\x00\x00\x01")]
    raw = encode_response(42, varbinds)
    dup_exchange = ExchangeIO(
        attempts=(Attempt(sent_at=0.001, received_at=0.002),),
        response=(0.002, raw),
        strays=((0.003, raw),),  # exact duplicate
    )
    transport = FakeTransport(
        responses=[
            dup_exchange,
            _eom_exchange(_OID_A),
        ]
    )
    records = await _collect(transport)

    exchange_records = [r for r in records if r.type == "exchange"]
    first = exchange_records[0]
    assert first.violations is not None  # type: ignore[union-attr]
    assert str(Violation.DUPLICATE_RESPONSE) in first.violations  # type: ignore[union-attr]
    _validate_all(records, record_validator)
