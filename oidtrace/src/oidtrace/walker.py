"""Walker orchestrator for OIDTrace.

The walk core is an async generator (walk_records) that yields a self-sufficient
stream of TraceRecord objects: Header → Exchanges → Events → Summary.

walk_with_transport wraps the generator as a sink-pumping adapter:
  - feeds records to all sinks deterministically
  - catches CancelledError → emits INTERRUPTED summary → re-raises
  - returns the EndReason from the final Summary

run_walk is the file-producing composition:
  - opens TraceWriter(path) as a CM
  - creates ONE shared monotonic clock (trap #11: transport + records must share a zero)
  - manages the UdpTransport async CM
  - prepends the writer's write method to caller sinks

Key implementation rules
------------------------
- NO CancelledError handling inside walk_records (the async generator must not
  resume after GeneratorExit / cancellation — that is illegal).
- Partial consumers MUST close via contextlib.aclosing or explicit aclose().
- All times: round(rel(), 6) so microsecond precision.
- One shared rel() clock passed to both UdpTransport.create and the loop.
- NEVER log varbind values or the community string.

WalkStats oids_seen note
------------------------
WalkStats.observe counts OIDs from Exchange records (response.varbinds); this
may exceed the generator's own in-subtree oids_seen by up to bulk_size on the
terminal exchange, because the generator stops advancing the cursor as soon as it
detects termination but has already decoded the full varbind list. This is
acceptable for interrupted summaries (slightly over-counts vs. exact).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import traceformat.models as tf
from traceformat import TraceRecord
from traceformat.vocab import EndReason, EventKind, Violation

from oidtrace.auth import AuthProto, password_to_key
from oidtrace.codec import (
    EXCEPTION_TAGS,
    Malformed,
    Message,
    V3Params,
    Varbind,
    authenticate_msg,
    decode_message,
    decode_v3_message,
    encode_getbulk,
    encode_getnext,
    encode_v3_discovery,
    encode_v3_getbulk,
)
from oidtrace.oid import Oid
from oidtrace.records import (
    event_record,
    exchange_record,
    header_record,
    summary_record,
)
from oidtrace.tracefile import TraceWriter
from oidtrace.transport import Attempt as TransportAttempt
from oidtrace.transport import ExchangeIO, Transport, UdpTransport
from oidtrace.violations import check_exchange

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public type alias
# ---------------------------------------------------------------------------

RecordSink = Callable[[TraceRecord], None]

# ---------------------------------------------------------------------------
# WalkSettings
# ---------------------------------------------------------------------------

_DEFAULT_START_OID_STR = "1.3.6.1"


@dataclass(frozen=True)
class WalkSettings:
    """Configuration for a single walk.

    Attributes:
        bulk_size: GetBulk max-repetitions (must be >= 1, or 0 for SNMP v1).
        timeout_s: Per-attempt timeout in seconds.
        retries: Number of retransmissions after the first send.
        start_oid: Subtree root OID; walk stays in this subtree.
        time_budget_s: Optional wall-time budget in seconds; None = unlimited.
        give_up_after: Consecutive response-less exchanges before UNRESPONSIVE.
        community: SNMP v2c community string.
        snmp_version: SNMP protocol version ("1" GetNext, "2c"/"3" GetBulk).
        v3_user: SNMPv3 USM username; required when snmp_version == "3".
    """

    bulk_size: int = 10
    timeout_s: float = 2.0
    retries: int = 2
    start_oid: Oid = field(default_factory=lambda: Oid.from_str(_DEFAULT_START_OID_STR))
    time_budget_s: float | None = None
    give_up_after: int = 3
    community: bytes = b"public"
    snmp_version: Literal["1", "2c", "3"] = "2c"
    v3_user: str | None = None
    v3_auth_proto: AuthProto | None = None
    v3_auth_pass: str | None = None

    def __post_init__(self) -> None:
        if self.snmp_version in ("2c", "3") and self.bulk_size < 1:
            raise ValueError(f"bulk_size must be >= 1, got {self.bulk_size}")
        if self.snmp_version == "3" and self.v3_user is None:
            raise ValueError("v3_user is required when snmp_version == '3'")
        if self.v3_auth_proto is not None and self.v3_auth_pass is None:
            raise ValueError("v3_auth_pass required when v3_auth_proto is set")


# ---------------------------------------------------------------------------
# WalkStats
# ---------------------------------------------------------------------------


class WalkStats:
    """Accumulator for walk statistics derived from emitted records.

    Useful for synthesising an INTERRUPTED summary when a consumer has only
    seen a prefix of the stream.

    Note on oids_seen: this counter reflects the count of DISTINCT OIDs present
    in Exchange response varbinds (excluding exception tags).  It may exceed the
    generator's own in-subtree oids_seen by up to bulk_size on the terminal
    exchange — acceptable for interrupted summaries.
    """

    def __init__(self) -> None:
        self.exchanges: int = 0
        self._oids_seen_set: set[str] = set()
        self.violation_counts: dict[Violation, int] = {}

    @property
    def oids_seen(self) -> int:
        """Count of distinct OIDs seen across all observed exchanges."""
        return len(self._oids_seen_set)

    def observe(self, record: TraceRecord) -> None:
        """Accumulate stats from one record."""
        if isinstance(record, tf.Exchange):
            self.exchanges += 1
            if record.response is not None:
                for vb in record.response.varbinds:
                    # Don't count exception-tag varbinds
                    # We check via vtype string since models.Varbind doesn't carry raw tag
                    if vb.vtype not in ("EndOfMibView", "NoSuchObject", "NoSuchInstance"):
                        self._oids_seen_set.add(str(vb.oid))
            if record.violations:
                for v_str in record.violations:
                    try:
                        v = Violation(v_str)
                        self.violation_counts[v] = self.violation_counts.get(v, 0) + 1
                    except ValueError:
                        pass  # unknown violation string — tolerate


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TOOL_NAME = "oidtrace/0.1.0"


def _monotonic_rel() -> Callable[[], float]:
    """Return a closure that gives seconds elapsed since creation (microsecond precision)."""
    t0 = time.monotonic()

    def rel() -> float:
        return round(time.monotonic() - t0, 6)

    return rel


def _now(rel: Callable[[], float]) -> float:
    return round(rel(), 6)


def _make_settings_model(settings: WalkSettings) -> tf.Settings:
    # For SNMP v1, emit bulk_size=0 (GetNext walk)
    bulk_size = 0 if settings.snmp_version == "1" else settings.bulk_size
    fields: dict[str, object] = {
        "bulk_size": bulk_size,
        "timeout_s": settings.timeout_s,
        "retries": settings.retries,
        "start_oid": tf.Oid(str(settings.start_oid)),
    }
    if settings.time_budget_s is not None:
        fields["time_budget_s"] = settings.time_budget_s
    return tf.Settings.model_validate(fields)


def _transport_attempt_to_model(attempt: TransportAttempt) -> tf.Attempt:
    """Convert transport.Attempt → models.Attempt.

    Uses model_validate with only the present fields so exclude_unset keeps
    null values absent from JSON (the Attempt schema forbids null for received_at
    when error is set, and null error is the default — omit when absent).
    """
    fields: dict[str, object] = {
        "sent_at": tf.Reltime(round(attempt.sent_at, 6)),
    }
    if attempt.received_at is not None:
        fields["received_at"] = tf.Reltime(round(attempt.received_at, 6))
    else:
        # Schema requires received_at to be present but null when no response came
        fields["received_at"] = None
    if attempt.error is not None:
        fields["error"] = str(attempt.error)
    return tf.Attempt.model_validate(fields)


# ---------------------------------------------------------------------------
# walk_records — async generator core
# ---------------------------------------------------------------------------


async def walk_records(  # noqa: PLR0912, PLR0913, PLR0915
    transport: Transport,
    *,
    rel: Callable[[], float],
    settings: WalkSettings,
    label: str | None = None,
    session_id: str | None = None,
    run: int = 1,
    runs_total: int = 1,
) -> AsyncGenerator[TraceRecord]:
    """Async generator yielding Header → Exchanges → Events → Summary.

    The generator is self-sufficient: consumers can synthesize an INTERRUPTED
    summary from the records they consumed via WalkStats.

    Termination semantics:
    - endOfMibView (0x82) on any varbind → COMPLETED
    - all varbinds outside start_oid subtree → COMPLETED
    - empty varbind list → COMPLETED
    - oid-not-increasing (non-exception varbind) → OID_LOOP_DETECTED event + OID_LOOP
    - give_up_after consecutive response-less or malformed exchanges → UNRESPONSIVE
      (valid decoded Message resets the consecutive counter)
    - time_budget_s exceeded at loop top → TIME_BUDGET_EXCEEDED event + TIME_BUDGET_EXCEEDED

    CancelledError: must NOT be caught here. The generator must not yield after
    GeneratorExit (illegal per Python async generator contract).

    Args:
        transport: Object implementing Transport protocol.
        rel: Shared monotonic clock (seconds since walk start).
        settings: Walk configuration.
        label: Optional human label for the Header.
        session_id: UUID string; a fresh one is generated if None.
        run: 1-based run index.
        runs_total: Total runs in the matrix.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    started_at = datetime.now(UTC)
    sid = session_id

    log.info(
        "walk start session=%s run=%d/%d start_oid=%s bulk=%d",
        sid,
        run,
        runs_total,
        settings.start_oid,
        settings.bulk_size,
    )

    yield header_record(
        tool=_TOOL_NAME,
        started_at=started_at,
        label=label,
        session_id=sid,
        run=run,
        runs_total=runs_total,
        snmp_version=settings.snmp_version,
        settings=_make_settings_model(settings),
    )

    cursor: Oid = settings.start_oid
    seq: int = 0
    consecutive_no_response: int = 0
    violation_counts: dict[Violation, int] = {}
    oids_seen_set: set[Oid] = set()  # distinct in-subtree OIDs
    end_reason: EndReason | None = None
    v3_params: V3Params | None = None
    v3_kul: bytes | None = None

    # --- SNMPv3 discovery (recorded as seq=1; the GetBulk loop starts at seq=2) ---
    if settings.snmp_version == "3":
        assert settings.v3_user is not None  # enforced by WalkSettings.__post_init__
        seq = 1
        msg_id = random.randint(1, 2**31 - 1)
        request_id = random.randint(1, 2**31 - 1)
        raw_request = encode_v3_discovery(msg_id, request_id)
        exchange_io = await transport.exchange(
            raw_request,
            timeout_s=settings.timeout_s,
            retries=settings.retries,
        )
        log.debug(
            "exchange seq=1 request_id=%d response=%s (v3 discovery)",
            request_id,
            "yes" if exchange_io.response is not None else "no",
        )

        discovery_attempts = [_transport_attempt_to_model(a) for a in exchange_io.attempts]
        discovery_strays = [
            tf.StrayResponse(received_at=tf.Reltime(round(ts, 6))) for ts, _ in exchange_io.strays
        ]
        discovery_request = tf.Request.model_validate(
            {"pdu": "discovery", "request_id": request_id, "oids": []}
        )

        response_rid: int | None = None
        response_es: int | None = None
        response_ei: int | None = None
        discovery_vbs: list[Varbind] = []
        if exchange_io.response is not None:
            decoded = decode_v3_message(exchange_io.response[1])
            if isinstance(decoded, Malformed):
                consecutive_no_response += 1
            else:
                msg, v3_params = decoded
                response_rid = msg.request_id
                response_es = msg.f1
                response_ei = msg.f2
                discovery_vbs = list(msg.varbinds)
                consecutive_no_response = 0
        else:
            consecutive_no_response += 1

        yield exchange_record(
            seq=seq,
            request=discovery_request,
            attempts=discovery_attempts,
            response_request_id=response_rid,
            response_error_status=response_es,
            response_error_index=response_ei,
            varbinds=discovery_vbs,
            strays=discovery_strays,
            violations=[],
            malformed=None,
        )

        # Without engine parameters we cannot encode any GetBulk — discovery
        # failure (no response or malformed Report) terminates the walk.
        if v3_params is None:
            log.info("walk unresponsive: v3 discovery failed (no engine params)")
            end_reason = EndReason.UNRESPONSIVE
        elif settings.v3_auth_proto is not None:
            assert settings.v3_auth_pass is not None  # enforced by WalkSettings.__post_init__
            v3_kul = password_to_key(
                settings.v3_auth_pass.encode(), v3_params.engine_id, settings.v3_auth_proto
            )

    while end_reason is None:
        # --- Time budget check (at loop top — zero-exchange trace intentional) ---
        if settings.time_budget_s is not None and _now(rel) >= settings.time_budget_s:
            yield event_record(
                at=_now(rel),
                kind=EventKind.TIME_BUDGET_EXCEEDED,
            )
            log.info("walk time budget exceeded at=%.6f", _now(rel))
            end_reason = EndReason.TIME_BUDGET_EXCEEDED
            break

        seq += 1
        request_id = random.randint(1, 2**31 - 1)

        if settings.snmp_version == "1":
            raw_request = encode_getnext(
                request_id,
                cursor,
                community=settings.community,
            )
            # Omit non_repeaters/max_repetitions entirely (GetNext has neither);
            # model_validate sets _fields_set to exactly the supplied keys so
            # exclude_unset keeps them absent rather than emitting null.
            request_model = tf.Request.model_validate(
                {
                    "pdu": "getnext",
                    "request_id": request_id,
                    "oids": [tf.Oid(str(cursor))],
                }
            )
        else:
            # v2c and v3 share the same GetBulk request model; only the wire
            # encoding (community vs. USM) differs between them.
            if settings.snmp_version == "3":
                assert v3_params is not None  # discovery succeeded or loop never starts
                assert settings.v3_user is not None  # enforced by WalkSettings.__post_init__
                raw_request = encode_v3_getbulk(
                    msg_id=random.randint(1, 2**31 - 1),
                    request_id=request_id,
                    oid=cursor,
                    max_repetitions=settings.bulk_size,
                    engine_id=v3_params.engine_id,
                    engine_boots=v3_params.engine_boots,
                    engine_time=v3_params.engine_time,
                    username=settings.v3_user.encode(),
                    auth=v3_kul is not None,
                )
                if v3_kul is not None:
                    assert settings.v3_auth_proto is not None
                    raw_request = authenticate_msg(raw_request, v3_kul, settings.v3_auth_proto)
            else:
                raw_request = encode_getbulk(
                    request_id,
                    cursor,
                    non_repeaters=0,
                    max_repetitions=settings.bulk_size,
                    community=settings.community,
                )
            request_model = tf.Request(
                pdu=tf.Pdu("getbulk"),
                request_id=request_id,
                oids=[tf.Oid(str(cursor))],
                non_repeaters=0,
                max_repetitions=settings.bulk_size,
            )

        exchange_io: ExchangeIO = await transport.exchange(
            raw_request,
            timeout_s=settings.timeout_s,
            retries=settings.retries,
        )

        log.debug(
            "exchange seq=%d request_id=%d response=%s",
            seq,
            request_id,
            "yes" if exchange_io.response is not None else "no",
        )

        model_attempts = [_transport_attempt_to_model(a) for a in exchange_io.attempts]
        model_strays = [
            tf.StrayResponse(received_at=tf.Reltime(round(ts, 6))) for ts, _ in exchange_io.strays
        ]

        decoded_msg: Message | None = None
        malformed_model: tf.Malformed | None = None
        varbinds_from_response: list[Varbind] = []
        response_request_id: int | None = None
        response_error_status: int | None = None
        response_error_index: int | None = None

        if exchange_io.response is not None:
            _received_at, raw_response = exchange_io.response
            if settings.snmp_version == "3":
                # Response MAC verification intentionally skipped: this is a
                # diagnostic tracer, not a security client.
                decoded = decode_v3_message(raw_response)
                msg = decoded if isinstance(decoded, Malformed) else decoded[0]
            else:
                msg = decode_message(raw_response)
            if isinstance(msg, Malformed):
                malformed_model = tf.Malformed(
                    error=msg.error,
                    length=len(msg.raw),
                )
                consecutive_no_response += 1
            else:
                decoded_msg = msg
                varbinds_from_response = list(msg.varbinds)
                response_request_id = msg.request_id
                response_error_status = msg.f1
                response_error_index = msg.f2
                # Valid decoded Message → reset give-up counter
                consecutive_no_response = 0
        else:
            consecutive_no_response += 1

        exchange_violations: list[Violation] = []
        if malformed_model is not None:
            exchange_violations.append(Violation.MALFORMED_BER)
        elif decoded_msg is not None and response_request_id is not None:
            exchange_violations = check_exchange(
                sent_id=request_id,
                returned_id=response_request_id,
                prev_oid=cursor,
                varbinds=varbinds_from_response,
                response_raw=exchange_io.response[1] if exchange_io.response else b"",
                strays=[raw for _, raw in exchange_io.strays],
            )

        for v in exchange_violations:
            violation_counts[v] = violation_counts.get(v, 0) + 1

        yield exchange_record(
            seq=seq,
            request=request_model,
            attempts=model_attempts,
            response_request_id=response_request_id,
            response_error_status=response_error_status,
            response_error_index=response_error_index,
            varbinds=varbinds_from_response,
            strays=model_strays,
            violations=exchange_violations,
            malformed=malformed_model,
        )

        # --- Termination decisions (after yielding the exchange) ---
        if consecutive_no_response >= settings.give_up_after:
            log.info("walk unresponsive after %d consecutive misses", consecutive_no_response)
            end_reason = EndReason.UNRESPONSIVE
            break

        if exchange_io.response is None or malformed_model is not None:
            continue

        # SNMP v1 end-of-MIB: noSuchName (error_status=2). This must be checked
        # BEFORE any varbind processing — v1 responses do not use EndOfMibView
        # tags, they signal end-of-MIB via error_status=2 with a Null varbind.
        if settings.snmp_version == "1" and decoded_msg is not None and decoded_msg.f1 == 2:  # noqa: PLR2004
            log.info("walk completed: noSuchName (v1 end-of-MIB)")
            end_reason = EndReason.COMPLETED
            break

        if not varbinds_from_response:
            log.info("walk completed: empty varbind response")
            end_reason = EndReason.COMPLETED
            break

        if any(vb.tag == 0x82 for vb in varbinds_from_response):  # noqa: PLR2004
            log.info("walk completed: EndOfMibView")
            end_reason = EndReason.COMPLETED
            break

        # Find the last non-exception varbind (the new cursor candidate)
        data_vbs = [vb for vb in varbinds_from_response if vb.tag not in EXCEPTION_TAGS]

        # If all varbinds are exception tags (shouldn't normally happen after EOM check above)
        if not data_vbs:
            log.info("walk completed: only exception-tag varbinds")
            end_reason = EndReason.COMPLETED
            break

        new_cursor = data_vbs[-1].oid

        # OID not increasing → OID_LOOP (derived from check_exchange, the single source of truth)
        if Violation.OID_NOT_INCREASING in exchange_violations:
            yield event_record(
                at=_now(rel),
                kind=EventKind.OID_LOOP_DETECTED,
                detail={"oid": str(new_cursor), "prev_oid": str(cursor)},
            )
            log.info("walk oid-loop detected oid=%s prev=%s", new_cursor, cursor)
            end_reason = EndReason.OID_LOOP
            break

        if not new_cursor.in_subtree(settings.start_oid):
            log.info("walk completed: left subtree oid=%s", new_cursor)
            end_reason = EndReason.COMPLETED
            break

        for vb in data_vbs:
            if vb.oid.in_subtree(settings.start_oid):
                oids_seen_set.add(vb.oid)

        cursor = new_cursor

    assert end_reason is not None
    at = _now(rel)
    oids_seen = len(oids_seen_set)
    log.info("walk end reason=%s at=%.6f exchanges=%d oids_seen=%d", end_reason, at, seq, oids_seen)
    yield summary_record(
        at=at,
        exchanges=seq,
        oids_seen=oids_seen,
        end_reason=end_reason,
        violation_counts=violation_counts,
    )


# ---------------------------------------------------------------------------
# walk_with_transport — sink-pumping adapter
# ---------------------------------------------------------------------------


async def walk_with_transport(  # noqa: PLR0913
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
    """Pump walk_records into sinks; handle cancellation.

    Catches CancelledError → emits an INTERRUPTED summary to sinks → re-raises.
    Sinks are called synchronously; sink failures propagate (v1: sinks are trusted).

    Returns the EndReason from the final Summary record.

    Args:
        transport: Object implementing Transport protocol.
        rel: Shared monotonic clock.
        settings: Walk configuration.
        sinks: Sequence of callables receiving each TraceRecord.
        label: Optional human label.
        session_id: UUID string; generated if None.
        run: 1-based run index.
        runs_total: Total runs in matrix.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    stats = WalkStats()
    end_reason: EndReason | None = None

    def emit(record: TraceRecord) -> None:
        for sink in sinks:
            sink(record)

    try:
        async with aclosing(
            walk_records(
                transport,
                rel=rel,
                settings=settings,
                label=label,
                session_id=session_id,
                run=run,
                runs_total=runs_total,
            )
        ) as gen:
            async for record in gen:
                stats.observe(record)
                emit(record)
                if isinstance(record, tf.Summary):
                    end_reason = EndReason(record.end_reason)
    except asyncio.CancelledError:
        at = _now(rel)
        interrupted = summary_record(
            at=at,
            exchanges=stats.exchanges,
            oids_seen=stats.oids_seen,
            end_reason=EndReason.INTERRUPTED,
            violation_counts=stats.violation_counts,
        )
        emit(interrupted)
        raise

    assert end_reason is not None
    return end_reason


# ---------------------------------------------------------------------------
# run_walk — file-producing composition
# ---------------------------------------------------------------------------


async def run_walk(  # noqa: PLR0913
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
    """Full walk: opens trace file, creates transport, runs walk_with_transport.

    ONE shared _monotonic_rel() clock is created here and passed to both
    UdpTransport.create and walk_with_transport.  This is mandatory (trap #11):
    two independent clocks would silently desynchronize timestamps.

    TraceWriter CM is outermost; transport async CM is inner.
    writer.write is prepended as the first sink.

    Args:
        host: Target hostname or IP.
        port: Target UDP port.
        settings: Walk configuration.
        path: Output trace file path (.oidtrace.jsonl.gz).
        label: Optional human label.
        session_id: UUID string; generated if None.
        run: 1-based run index.
        runs_total: Total runs in matrix.
        sinks: Additional record sinks (writer is always first).
    """
    rel = _monotonic_rel()

    with TraceWriter(path) as writer:
        all_sinks: list[RecordSink] = [writer.write, *sinks]
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
