"""Record builders for the trace format.

Every builder returns a traceformat model instance (Header, Exchange, Event,
Summary, or SystemInfo).  Serialization is deferred to dump_record which uses
exclude_unset semantics — absent optional fields stay absent in JSON (never
emitted as null).

Domain-to-format conversions happen here and ONLY here:
  - oidtrace.oid.Oid  → str(oid) → models.Oid (wire string)
  - codec.Varbind     → {oid, vtype, vlen} (value bytes are NEVER forwarded)

No Any in signatures.  Producer-closed enums only (Violation/EndReason/EventKind).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import traceformat.models as tf

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from traceformat.vocab import EndReason, EventKind, Violation

    from oidtrace.codec import Varbind


def header_record(  # noqa: PLR0913
    *,
    tool: str,
    started_at: datetime,
    label: str | None,
    session_id: str,
    run: int,
    runs_total: int,
    snmp_version: Literal["1", "2c"],
    settings: tf.Settings,
) -> tf.Header:
    """Build a Header record.

    Args:
        tool: Tool name and version string (e.g. "oidtrace/0.1.0").
        started_at: Walk start time (timezone-aware datetime, UTC).
        label: Optional human label; absent from JSON when None.
        session_id: UUID string shared by all files in a matrix run.
        run: This run's index (1-based).
        runs_total: Total number of runs in the matrix.
        snmp_version: SNMP version string ("1" or "2c").
        settings: Pre-built Settings model.

    Returns:
        A validated Header model instance.
    """
    # Only pass label when it is set — exclude_unset semantics keep it absent.
    if label is not None:
        return tf.Header(
            type="header",
            format_version=1,
            tool=tool,
            started_at=started_at,
            label=label,
            session=tf.Session(id=session_id, run=run, runs_total=runs_total),
            snmp=tf.Snmp(version=tf.Version(snmp_version)),
            settings=settings,
        )
    return tf.Header(
        type="header",
        format_version=1,
        tool=tool,
        started_at=started_at,
        session=tf.Session(id=session_id, run=run, runs_total=runs_total),
        snmp=tf.Snmp(version=tf.Version(snmp_version)),
        settings=settings,
    )


def exchange_record(  # noqa: PLR0913
    *,
    seq: int,
    request: tf.Request,
    attempts: Sequence[tf.Attempt],
    response_request_id: int | None,
    response_error_status: int | None,
    response_error_index: int | None,
    varbinds: Sequence[Varbind],
    strays: Sequence[tf.StrayResponse],
    violations: Sequence[Violation],
    malformed: tf.Malformed | None,
) -> tf.Exchange:
    """Build an Exchange record.

    response and malformed are mutually exclusive per the schema.  A ValueError
    is raised if both response_request_id and malformed are non-None, making it
    impossible to produce an invalid record via this builder.

    Varbind conversion: codec.Varbind → {oid, vtype, vlen}.  The value bytes
    are NEVER forwarded; they remain invisible to any caller of this function.

    Conditional keys (response, stray_responses, violations, malformed) are
    constructed only when non-empty / non-None so exclude_unset omits them.

    Args:
        seq: Exchange sequence number (1-based).
        request: Pre-built Request model.
        attempts: Non-empty sequence of Attempt models.
        response_request_id: request_id from the response PDU, or None (timeout/malformed).
        response_error_status: error_status from the response, or None.
        response_error_index: error_index from the response, or None.
        varbinds: Decoded codec.Varbind instances from the response.
        strays: StrayResponse models for out-of-cycle datagrams.
        violations: Violation enum values detected for this exchange.
        malformed: Malformed model if the response could not be decoded, else None.

    Returns:
        A validated Exchange model instance.

    Raises:
        ValueError: If both response_request_id and malformed are non-None
            (response and malformed are mutually exclusive).
    """
    if response_request_id is not None and malformed is not None:
        raise ValueError(
            "response_request_id and malformed are mutually exclusive: "
            "a decoded response and a malformed datagram cannot both be present."
        )

    response: tf.Response | None = None
    if response_request_id is not None:
        # response_error_status and response_error_index are always set together.
        assert response_error_status is not None
        assert response_error_index is not None
        response = tf.Response(
            request_id=response_request_id,
            error_status=response_error_status,
            error_index=response_error_index,
            varbinds=[
                tf.Varbind(
                    oid=tf.Oid(str(vb.oid)),
                    vtype=vb.vtype,
                    vlen=vb.vlen,
                )
                for vb in varbinds
            ],
        )

    # Build only the present fields — model_validate sets _fields_set to
    # exactly the supplied keys, so exclude_unset omits absent optional fields.
    fields: dict[str, object] = {
        "type": "exchange",
        "seq": seq,
        "request": request,
        "attempts": list(attempts),
    }
    if response is not None:
        fields["response"] = response
    if strays:
        fields["stray_responses"] = list(strays)
    if violations:
        fields["violations"] = [str(v) for v in violations]
    if malformed is not None:
        fields["malformed"] = malformed

    return tf.Exchange.model_validate(fields)


def event_record(
    *,
    at: float,
    kind: EventKind,
    detail: dict[str, object] | None = None,
) -> tf.Event:
    """Build an Event record.

    Args:
        at: Relative time in seconds since walk start.
        kind: Event kind (closed EventKind enum).
        detail: Optional detail dict; absent from JSON when None.

    Returns:
        A validated Event model instance.
    """
    if detail is not None:
        return tf.Event(type="event", at=tf.Reltime(at), kind=str(kind), detail=detail)
    return tf.Event(type="event", at=tf.Reltime(at), kind=str(kind))


def summary_record(
    *,
    at: float,
    exchanges: int,
    oids_seen: int,
    end_reason: EndReason,
    violation_counts: Mapping[Violation, int],
) -> tf.Summary:
    """Build a Summary record.

    Args:
        at: Relative time in seconds since walk start.
        exchanges: Total number of exchanges attempted.
        oids_seen: Number of unique OIDs observed.
        end_reason: Why the walk terminated (closed EndReason enum).
        violation_counts: Mapping from Violation to count; keys become wire strings.

    Returns:
        A validated Summary model instance.
    """
    return tf.Summary(
        type="summary",
        at=tf.Reltime(at),
        exchanges=exchanges,
        oids_seen=oids_seen,
        end_reason=str(end_reason),
        violation_counts={str(v): count for v, count in violation_counts.items()},
    )


def system_info_record(
    *,
    at: float,
    point: Literal["start", "end"],
    values: dict[str, str | int],
) -> tf.SystemInfo:
    """Build a SystemInfo record.

    This builder exists for format completeness.  The v1 walker never calls it,
    but consumers may use it when system OID values are available.

    Args:
        at: Relative time in seconds since walk start.
        point: "start" or "end" — when the system info was captured.
        values: OID-keyed dict of string or integer values.

    Returns:
        A validated SystemInfo model instance.
    """
    return tf.SystemInfo(
        type="system_info",
        at=tf.Reltime(at),
        point=tf.Point(point),
        values=values,
    )
