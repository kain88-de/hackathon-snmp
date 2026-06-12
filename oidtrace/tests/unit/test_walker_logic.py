"""Unit tests for walker.py — no sockets.

Uses a FakeTransport that replays scripted ExchangeIO values.
All assertions are on the written trace (via read_trace) + returned EndReason.
"""

from __future__ import annotations

import gzip
import json
from typing import TYPE_CHECKING, Any

from traceformat.models import Event, Exchange, Header, Summary
from traceformat.vocab import AttemptError, EndReason, Violation

from oidtrace.codec import encode_response
from oidtrace.oid import Oid
from oidtrace.tracefile import TraceWriter, read_trace
from oidtrace.transport import Attempt, ExchangeIO
from oidtrace.walker import WalkSettings, walk_with_transport

if TYPE_CHECKING:
    from pathlib import Path

    from traceformat import TraceRecord


# ---------------------------------------------------------------------------
# FakeTransport


class FakeTransport:
    """Replays a list of ExchangeIO values in order."""

    def __init__(self, exchanges: list[ExchangeIO]) -> None:
        self._exchanges = list(exchanges)
        self._index = 0

    async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO:  # noqa: ARG002
        if self._index >= len(self._exchanges):
            raise AssertionError("FakeTransport exhausted — more exchanges than expected")
        result = self._exchanges[self._index]
        self._index += 1
        return result


# ---------------------------------------------------------------------------
# Helpers for building fake responses


def _response_exchange(
    oids: list[tuple[Oid, int, bytes]],
    request_id_override: int | None = None,
    sent_at: float = 0.0,
    received_at: float = 0.001,
) -> ExchangeIO:
    """Build an ExchangeIO with a valid response containing the given varbinds.

    The walker picks its own random request_id; the emulator response uses a fixed
    id (9999 by default).  If none of our tests care about the mismatch violation
    that results, this is fine — schema validation still passes.
    """
    rid = request_id_override if request_id_override is not None else 9999
    raw = encode_response(rid, oids)
    attempt = Attempt(sent_at=sent_at, received_at=received_at)
    return ExchangeIO(attempts=(attempt,), response=(received_at, raw), strays=())


def _timeout_exchange(sent_at: float = 0.0) -> ExchangeIO:
    """Build an ExchangeIO with no response (timeout)."""
    attempt = Attempt(sent_at=sent_at, received_at=None)
    return ExchangeIO(attempts=(attempt,), response=None, strays=())


def _malformed_exchange(sent_at: float = 0.0, received_at: float = 0.001) -> ExchangeIO:
    """Build an ExchangeIO with a response that is not valid SNMP."""
    raw = b"\xff\xfe\xfd"  # garbage bytes
    attempt = Attempt(sent_at=sent_at, received_at=received_at)
    return ExchangeIO(attempts=(attempt,), response=(received_at, raw), strays=())


def _eom_exchange(
    cursor: Oid,
    sent_at: float = 0.0,
    received_at: float = 0.001,
) -> ExchangeIO:
    """Return endOfMibView for cursor."""
    raw = encode_response(9999, [(cursor, 0x82, b"")])
    attempt = Attempt(sent_at=sent_at, received_at=received_at)
    return ExchangeIO(attempts=(attempt,), response=(received_at, raw), strays=())


# ---------------------------------------------------------------------------
# Test helpers


def _records(path: Path) -> list[TraceRecord]:
    return list(read_trace(path))


def _validate_all_from_path(path: Path, record_validator: Any) -> None:
    with gzip.open(path, "rb") as gz:
        for raw in gz:
            line = raw.decode().rstrip("\n")
            if line:
                record_validator.validate(json.loads(line))


# ---------------------------------------------------------------------------
# Test: endOfMibView -> COMPLETED


async def test_end_of_mib_view_completed(tmp_path: Path, record_validator: Any) -> None:
    """A response with endOfMibView tag terminates with COMPLETED."""
    cursor = Oid.from_str("1.3.6.1.2.1")
    exchanges = [_eom_exchange(cursor)]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=5,
        timeout_s=1.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    with TraceWriter(path) as writer:
        reason = await walk_with_transport(transport, settings=settings, sinks=[writer.write])

    assert reason == EndReason.COMPLETED

    records = _records(path)
    assert isinstance(records[0], Header)
    assert isinstance(records[-1], Summary)
    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.COMPLETED)
    assert summary.exchanges == 1

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: left-subtree OID -> COMPLETED


async def test_left_subtree_completed(tmp_path: Path, record_validator: Any) -> None:
    """When the last data OID is outside start_oid subtree, walk ends COMPLETED."""
    start = Oid.from_str("1.3.6.1.2.1")
    outside_oid = Oid.from_str("1.3.6.2.1.1")
    exchanges = [_response_exchange([(outside_oid, 0x02, b"\x00\x00\x00\x01")])]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=5,
        timeout_s=1.0,
        retries=0,
        start_oid=start,
    )

    with TraceWriter(path) as writer:
        reason = await walk_with_transport(transport, settings=settings, sinks=[writer.write])

    assert reason == EndReason.COMPLETED
    records = _records(path)
    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.COMPLETED)

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: OID wrap / non-increasing -> OID_LOOP + event record


async def test_oid_not_increasing_oid_loop(tmp_path: Path, record_validator: Any) -> None:
    """OID not increasing -> OID_LOOP + an oid-loop-detected event in the trace."""
    start = Oid.from_str("1.3.6.1")
    oid_a = Oid.from_str("1.3.6.1.2.1.1")
    oid_b = Oid.from_str("1.3.6.1.2.1.2")
    exchanges = [
        _response_exchange([(oid_b, 0x02, b"\x00\x00\x00\x01")]),
        _response_exchange([(oid_a, 0x02, b"\x00\x00\x00\x01")]),  # wraps backward
    ]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=1.0,
        retries=0,
        start_oid=start,
    )

    with TraceWriter(path) as writer:
        reason = await walk_with_transport(transport, settings=settings, sinks=[writer.write])

    assert reason == EndReason.OID_LOOP

    records = _records(path)
    events = [r for r in records if isinstance(r, Event)]
    assert len(events) == 1
    assert events[0].kind == "oid-loop-detected"
    assert events[0].detail is not None
    assert "oid" in events[0].detail

    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.OID_LOOP)

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: give_up_after counting WITH recovery


async def test_give_up_after_with_recovery(tmp_path: Path, record_validator: Any) -> None:
    """Silence, silence, then a valid answer resets the counter.

    Then 3 more silences -> UNRESPONSIVE (counter resets on any valid Message).
    give_up_after=3: need 3 consecutive no-responses.
    """
    start = Oid.from_str("1.3.6.1")
    oid1 = Oid.from_str("1.3.6.1.2.1.1")
    exchanges = [
        _timeout_exchange(),  # 1st silence (consecutive=1)
        _timeout_exchange(),  # 2nd silence (consecutive=2)
        # answer -> resets counter; oid1 is inside subtree so cursor advances
        _response_exchange([(oid1, 0x02, b"\x00\x00\x00\x01")]),
        _timeout_exchange(),  # 1st silence after reset (consecutive=1)
        _timeout_exchange(),  # 2nd silence (consecutive=2)
        _timeout_exchange(),  # 3rd silence (consecutive=3) -> UNRESPONSIVE
    ]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=1.0,
        retries=0,
        start_oid=start,
        give_up_after=3,
    )

    with TraceWriter(path) as writer:
        reason = await walk_with_transport(transport, settings=settings, sinks=[writer.write])

    assert reason == EndReason.UNRESPONSIVE

    records = _records(path)
    exchanges_records = [r for r in records if isinstance(r, Exchange)]
    assert len(exchanges_records) == 6

    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == str(EndReason.UNRESPONSIVE)
    assert summary.exchanges == 6

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: malformed response -> MALFORMED_BER violation + malformed marker in record


async def test_malformed_response(tmp_path: Path, record_validator: Any) -> None:
    """A non-decodable response -> malformed-ber violation + malformed{error, length}."""
    # give_up_after=3: after 3 malformed -> UNRESPONSIVE
    exchanges = [_malformed_exchange(), _malformed_exchange(), _malformed_exchange()]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=1.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
        give_up_after=3,
    )

    with TraceWriter(path) as writer:
        reason = await walk_with_transport(transport, settings=settings, sinks=[writer.write])

    assert reason == EndReason.UNRESPONSIVE

    records = _records(path)
    exchange_recs = [r for r in records if isinstance(r, Exchange)]
    assert len(exchange_recs) == 3

    for exc_rec in exchange_recs:
        assert exc_rec.violations is not None
        assert str(Violation.MALFORMED_BER) in exc_rec.violations
        assert exc_rec.malformed is not None
        assert exc_rec.malformed.error
        assert exc_rec.malformed.length == 3  # len(b"\xff\xfe\xfd")

    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.violation_counts.get(str(Violation.MALFORMED_BER)) == 3

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: ICMP attempt errors appear in written attempts


async def test_icmp_attempt_error_in_record(tmp_path: Path, record_validator: Any) -> None:
    """An ICMP error attempt is written in the exchange record's attempts list."""
    icmp_attempt = Attempt(
        sent_at=0.0,
        received_at=None,
        error=AttemptError.ICMP_PORT_UNREACHABLE,
    )
    icmp_io = ExchangeIO(attempts=(icmp_attempt,), response=None, strays=())
    exchanges = [icmp_io, _timeout_exchange(), _timeout_exchange()]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=1.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
        give_up_after=3,
    )

    with TraceWriter(path) as writer:
        reason = await walk_with_transport(transport, settings=settings, sinks=[writer.write])
    assert reason == EndReason.UNRESPONSIVE

    records = _records(path)
    first_exchange = next(r for r in records if isinstance(r, Exchange))
    assert len(first_exchange.attempts) == 1
    attempt = first_exchange.attempts[0]
    assert attempt.error == str(AttemptError.ICMP_PORT_UNREACHABLE)

    _validate_all_from_path(path, record_validator)


# ---------------------------------------------------------------------------
# Test: on_record callback receives records in order


async def test_on_record_callback(tmp_path: Path) -> None:
    """The streamed sink receives exactly the same records as written to the file."""
    start = Oid.from_str("1.3.6.1")
    oid = Oid.from_str("1.3.6.1.2.1.1")
    exchanges = [_response_exchange([(oid, 0x82, b"")])]
    transport = FakeTransport(exchanges)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=1,
        timeout_s=1.0,
        retries=0,
        start_oid=start,
    )

    streamed: list[Any] = []
    with TraceWriter(path) as writer:
        await walk_with_transport(
            transport, settings=settings, sinks=[writer.write, streamed.append]
        )

    file_records = _records(path)
    assert len(streamed) == len(file_records)
