"""Walk orchestrator for OIDTrace.

``run_walk`` is the public entry point; it creates a UdpTransport and delegates
to ``walk_with_transport``, which accepts any Transport-protocol object so unit
tests can inject a fake without opening sockets.

``walk_records`` is the async-generator core: it yields every record in order
(header → exchanges/events → summary) and owns no sinks.  Consumers drive it
with ``async for`` and own cancellation — breaking out of the loop is safe.

``walk_with_transport`` is the sink-pumping adapter on top of ``walk_records``:
it fans records to sinks, catches ``CancelledError``, emits an INTERRUPTED
summary from its accumulated ``WalkStats``, and re-raises.

``walk_with_transport`` knows nothing about files — it accepts a
``sinks: Sequence[RecordSink]`` and fans every record out to all of them.
``run_walk`` owns file concerns: it opens a TraceWriter and prepends it to the
sinks list before delegating.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import uuid
from collections import Counter
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from traceformat.models import Attempt as ModelAttempt
from traceformat.models import Exchange, Request, Settings, StrayResponse, Summary
from traceformat.models import Malformed as ModelMalformed
from traceformat.vocab import EndReason, EventKind, Violation

from oidtrace.codec import EXCEPTION_TAGS, decode_message, encode_getbulk
from oidtrace.codec import Malformed as CodecMalformed
from oidtrace.oid import Oid
from oidtrace.records import (
    event_record,
    exchange_record,
    header_record,
    summary_record,
)
from oidtrace.tracefile import TraceWriter
from oidtrace.transport import Attempt as TransportAttempt
from oidtrace.transport import UdpTransport
from oidtrace.violations import check_exchange

if TYPE_CHECKING:
    from pathlib import Path

    from traceformat import TraceRecord

    from oidtrace.transport import Transport

logger = logging.getLogger(__name__)

RecordSink = Callable[["TraceRecord"], None]

_TAG_END_OF_MIB_VIEW = 0x82
_VTYPE_END_OF_MIB_VIEW = "EndOfMibView"


def _monotonic_rel() -> Callable[[], float]:
    """Return a rel() closure anchored to now."""
    t0 = time.monotonic()
    return lambda: round(time.monotonic() - t0, 6)


# ---------------------------------------------------------------------------
# Settings


@dataclass(frozen=True)
class WalkSettings:
    bulk_size: int = 10
    timeout_s: float = 2.0
    retries: int = 2
    start_oid: Oid = field(default_factory=lambda: Oid.from_str("1.3.6.1"))
    time_budget_s: float | None = None
    give_up_after: int = 3
    community: bytes = b"public"

    def __post_init__(self) -> None:
        if self.bulk_size < 1:
            raise ValueError(f"bulk_size must be >= 1, got {self.bulk_size}")


# ---------------------------------------------------------------------------
# WalkStats accumulator


class WalkStats:
    """Consumer-side accumulator for a stream of TraceRecords.

    Feed every record from a ``walk_records`` stream via ``observe``; the
    instance then exposes exchange counts, distinct response OIDs seen, and
    violation tallies.

    **Delta vs generator-internal accounting:** the generator only counts
    OIDs from *continuing* exchanges (termination-triggering exchanges are not
    accumulated before the loop breaks).  ``WalkStats`` counts every data
    varbind OID from every Exchange record it sees, including the terminal one.
    For interrupted walks the delta is zero (no terminal exchange accumulation
    happens on the generator side either).  For normal terminations,
    ``WalkStats.oids_seen`` may be >= the generator's ``oids_seen`` by up to
    ``bulk_size`` (the varbinds from the last exchange).  Use the Summary
    record's ``oids_seen`` field for the authoritative count; ``WalkStats`` is
    the consumer-side approximation useful for synthesising an INTERRUPTED
    summary before a Summary record has been yielded.
    """

    def __init__(self) -> None:
        self._exchanges: int = 0
        self._oids: set[str] = set()
        self._violation_counts: Counter[Violation] = Counter()

    @property
    def exchanges(self) -> int:
        return self._exchanges

    @property
    def oids_seen(self) -> int:
        return len(self._oids)

    @property
    def violation_counts(self) -> Counter[Violation]:
        return Counter(self._violation_counts)

    def observe(self, record: TraceRecord) -> None:
        """Update stats from one record.  Ignores Header, Event, Summary."""
        if not isinstance(record, Exchange):
            return
        self._exchanges += 1
        if record.response is not None:
            for vb in record.response.varbinds:
                if vb.vtype != _VTYPE_END_OF_MIB_VIEW:
                    self._oids.add(vb.oid.root)
        if record.violations:
            for v_str in record.violations:
                with contextlib.suppress(ValueError):
                    self._violation_counts[Violation(v_str)] += 1

    def interrupted_summary(self, at: float) -> Summary:
        """Build a Summary record for an INTERRUPTED walk using accumulated stats."""
        return summary_record(
            at=at,
            exchanges=self._exchanges,
            oids_seen=self.oids_seen,
            end_reason=str(EndReason.INTERRUPTED),
            violation_counts=self._violation_counts,
        )


# ---------------------------------------------------------------------------
# Internal helpers


def _to_model_attempt(a: TransportAttempt) -> ModelAttempt:
    kwargs: dict[str, object] = {
        "sent_at": a.sent_at,
        "received_at": a.received_at,
    }
    if a.error is not None:
        kwargs["error"] = str(a.error)
    return ModelAttempt.model_validate(kwargs)


# ---------------------------------------------------------------------------
# Async-generator core


async def walk_records(
    transport: Transport,
    *,
    rel: Callable[[], float],
    settings: WalkSettings,
    label: str | None = None,
    session_id: str | None = None,
    run: int = 1,
    runs_total: int = 1,
) -> AsyncGenerator[TraceRecord]:
    """Yield every TraceRecord produced by a walk in order.

    Yields: Header → Exchange/Event records → Summary (on normal termination).

    The generator does NOT catch ``CancelledError``.  Breaking out of the
    ``async for`` loop closes the generator cleanly; no Summary is yielded in
    that case.  Consumers that need a Summary on cancellation should use
    ``walk_with_transport`` instead.

    Logging stays here.  Sinks belong in the caller.
    """
    sid = session_id or str(uuid.uuid4())

    model_settings = Settings(
        bulk_size=settings.bulk_size,
        timeout_s=settings.timeout_s,
        retries=settings.retries,
        start_oid=str(settings.start_oid),  # type: ignore[arg-type]
        **({"time_budget_s": settings.time_budget_s} if settings.time_budget_s is not None else {}),
    )

    # Header
    yield header_record(
        tool="oidtrace",
        started_at=datetime.now(UTC).isoformat(),
        label=label,
        session_id=sid,
        run=run,
        runs_total=runs_total,
        snmp_version="2c",
        settings=model_settings,
    )

    logger.info(
        "walk start bulk_size=%d timeout_s=%s retries=%d start_oid=%s budget=%s",
        settings.bulk_size,
        settings.timeout_s,
        settings.retries,
        settings.start_oid,
        settings.time_budget_s,
    )

    cursor = settings.start_oid
    seq = 0
    oids_seen: set[Oid] = set()
    violation_counts: Counter[Violation] = Counter()
    consecutive_no_response = 0
    end_reason: EndReason | None = None

    while True:
        # Time-budget check at loop top.
        # A zero-exchange trace (header + event + summary) is intentional when the
        # budget is already exceeded before the first exchange.
        if settings.time_budget_s is not None and rel() > settings.time_budget_s:
            logger.info("walk event: time-budget-exceeded")
            yield event_record(
                at=rel(),
                kind=EventKind.TIME_BUDGET_EXCEEDED,
            )
            end_reason = EndReason.TIME_BUDGET_EXCEEDED
            break

        # Build and send request
        seq += 1
        request_id = random.randint(1, 2**31 - 1)

        raw_request = encode_getbulk(
            request_id,
            cursor,
            0,
            settings.bulk_size,
            settings.community,
        )

        exchange_io = await transport.exchange(
            raw_request,
            timeout_s=settings.timeout_s,
            retries=settings.retries,
        )

        # Convert transport.Attempt -> models.Attempt
        model_attempts = [_to_model_attempt(a) for a in exchange_io.attempts]

        # Build stray responses
        model_strays = [StrayResponse(received_at=ts) for ts, _ in exchange_io.strays]  # type: ignore[arg-type]
        stray_raws = [raw for _, raw in exchange_io.strays]

        # Decode response
        decoded = None
        model_malformed: ModelMalformed | None = None
        violations: list[Violation] = []

        if exchange_io.response is not None:
            _, response_bytes = exchange_io.response
            decoded = decode_message(response_bytes)

            if isinstance(decoded, CodecMalformed):
                model_malformed = ModelMalformed(
                    error=decoded.error,
                    length=len(decoded.raw),
                )
                violations.append(Violation.MALFORMED_BER)
                consecutive_no_response += 1
                decoded = None
            else:
                # Valid Message
                consecutive_no_response = 0
                exchange_violations = check_exchange(
                    sent_id=request_id,
                    returned_id=decoded.request_id,
                    prev_oid=cursor,
                    varbinds=decoded.varbinds,
                    response_raw=response_bytes,
                    strays=stray_raws,
                )
                violations.extend(exchange_violations)
        else:
            consecutive_no_response += 1

        # Count violations
        for v in violations:
            violation_counts[v] += 1

        # DEBUG per exchange
        if decoded is not None and not isinstance(decoded, CodecMalformed):
            logger.debug(
                "exchange seq=%d cursor=%s response=%d varbinds violations=%s",
                seq,
                cursor,
                decoded.request_id,
                [str(v) for v in violations] or "none",
            )
        elif model_malformed is not None:
            logger.debug(
                "exchange seq=%d cursor=%s malformed length=%d violations=%s",
                seq,
                cursor,
                model_malformed.length,
                [str(v) for v in violations] or "none",
            )
        else:
            logger.debug("exchange seq=%d cursor=%s no-response", seq, cursor)

        # Build exchange record
        req = Request(
            pdu="getbulk",  # type: ignore[arg-type]
            request_id=request_id,
            oids=[str(cursor)],  # type: ignore[list-item]
            non_repeaters=0,
            max_repetitions=settings.bulk_size,
        )

        if decoded is not None:
            rec = exchange_record(
                seq=seq,
                request=req,
                attempts=model_attempts,
                response_request_id=decoded.request_id,
                response_error_status=decoded.f1,
                response_error_index=decoded.f2,
                varbinds=decoded.varbinds,
                strays=model_strays,
                violations=violations,
                malformed=model_malformed,
            )
        else:
            rec = exchange_record(
                seq=seq,
                request=req,
                attempts=model_attempts,
                response_request_id=None,
                response_error_status=None,
                response_error_index=None,
                varbinds=[],
                strays=model_strays,
                violations=violations,
                malformed=model_malformed,
            )
        yield rec

        # Termination checks
        if decoded is None:
            # No valid response: check give_up_after
            if consecutive_no_response >= settings.give_up_after:
                end_reason = EndReason.UNRESPONSIVE
                break
            continue

        # Collect data varbinds (non-exception tags)
        data_varbinds = [vb for vb in decoded.varbinds if vb.tag not in EXCEPTION_TAGS]

        # EndOfMibView in any varbind -> COMPLETED
        if any(vb.tag == _TAG_END_OF_MIB_VIEW for vb in decoded.varbinds):
            end_reason = EndReason.COMPLETED
            break

        # No data varbinds -> COMPLETED
        if not data_varbinds:
            end_reason = EndReason.COMPLETED
            break

        last_oid = data_varbinds[-1].oid

        # Left subtree: last data OID not in start_oid's subtree -> COMPLETED
        if not last_oid.in_subtree(settings.start_oid):
            end_reason = EndReason.COMPLETED
            break

        # OID not increasing (detected by check_exchange) -> OID_LOOP
        if Violation.OID_NOT_INCREASING in violations:
            logger.info("walk event: oid-loop-detected oid=%s", last_oid)
            yield event_record(
                at=rel(),
                kind=EventKind.OID_LOOP_DETECTED,
                detail={"oid": str(last_oid)},
            )
            end_reason = EndReason.OID_LOOP
            break

        # Accumulate seen OIDs (only for continuing exchanges)
        for vb in data_varbinds:
            oids_seen.add(vb.oid)

        cursor = last_oid

    assert end_reason is not None
    logger.info(
        "walk end end_reason=%s exchanges=%d oids_seen=%d",
        end_reason,
        seq,
        len(oids_seen),
    )
    yield summary_record(
        at=rel(),
        exchanges=seq,
        oids_seen=len(oids_seen),
        end_reason=str(end_reason),
        violation_counts=violation_counts,
    )


# ---------------------------------------------------------------------------
# Sink-pumping adapter


async def walk_with_transport(
    transport: Transport,
    *,
    rel: Callable[[], float],
    settings: WalkSettings,
    sinks: Sequence[RecordSink],
    label: str | None = None,
    session_id: str | None = None,
    run: int = 1,
    runs_total: int = 1,
) -> EndReason:
    """Drive the walk loop using *transport* (any Transport-protocol object).

    *rel* is the shared monotonic clock (anchored to the same t0 used by the
    transport), so transport timestamps and record timestamps live on one timeline.

    Emits every record to all *sinks* in order.  Knows nothing about files —
    file concerns belong in ``run_walk``.  ``asyncio.CancelledError`` emits a
    summary with INTERRUPTED to all sinks and re-raises.
    """
    stats = WalkStats()
    end_reason: EndReason | None = None

    def emit(record: TraceRecord) -> None:
        for sink in sinks:
            sink(record)

    gen = walk_records(
        transport,
        rel=rel,
        settings=settings,
        label=label,
        session_id=session_id,
        run=run,
        runs_total=runs_total,
    )
    try:
        async for record in gen:
            stats.observe(record)
            emit(record)
            if isinstance(record, Summary):
                end_reason = EndReason(record.end_reason)
    except asyncio.CancelledError:
        logger.info(
            "walk end end_reason=interrupted exchanges=%d oids_seen=%d",
            stats.exchanges,
            stats.oids_seen,
        )
        emit(stats.interrupted_summary(at=rel()))
        raise
    finally:
        await gen.aclose()

    assert end_reason is not None
    return end_reason


# ---------------------------------------------------------------------------
# Public entry point


async def run_walk(
    host: str,
    port: int,
    *,
    settings: WalkSettings,
    path: Path,
    label: str | None = None,
    session_id: str | None = None,
    run: int = 1,
    runs_total: int = 1,
    sinks: Sequence[RecordSink] = (),
) -> EndReason:
    """Walk *host:port*, writing a trace to *path*.  Returns the EndReason."""
    rel = _monotonic_rel()  # single clock shared by transport and records

    with TraceWriter(path) as writer:
        all_sinks: Sequence[RecordSink] = (writer.write, *sinks)
        async with await UdpTransport.create(host, port, rel) as transport:
            return await walk_with_transport(
                transport,
                rel=rel,
                settings=settings,
                sinks=all_sinks,
                label=label,
                session_id=session_id,
                run=run,
                runs_total=runs_total,
            )
