"""Record builders for OIDTrace trace files.

Builders construct and return validated ``traceformat`` model instances.
Varbind values are never serialized -- the "no values" promise is enforced at
this boundary (only oid/vtype/vlen cross into the record).

Conditional keys stay *unset* (omitted from the serialized record) by not
being passed at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from traceformat.models import (
    Attempt,
    Event,
    Exchange,
    Header,
    Malformed,
    Request,
    Response,
    Settings,
    StrayResponse,
    Summary,
    SystemInfo,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from traceformat.vocab import EventKind, Violation

    from oidtrace.codec import Varbind


def header_record(
    *,
    tool: str,
    started_at: str,
    label: str | None,
    session_id: str,
    run: int,
    runs_total: int,
    snmp_version: str,
    settings: Settings,
) -> Header:
    fields: dict[str, object] = {
        "type": "header",
        "format_version": 1,
        "tool": tool,
        "started_at": started_at,
        "session": {"id": session_id, "run": run, "runs_total": runs_total},
        "snmp": {"version": snmp_version},
        "settings": settings.model_dump(exclude_unset=True),
    }
    if label is not None:
        fields["label"] = label
    return Header.model_validate(fields)


def exchange_record(
    *,
    seq: int,
    request: Request,
    attempts: Sequence[Attempt],
    response_request_id: int | None,
    response_error_status: int | None,
    response_error_index: int | None,
    varbinds: Sequence[Varbind],
    strays: Sequence[StrayResponse],
    violations: Sequence[Violation],
    malformed: Malformed | None,
) -> Exchange:
    fields: dict[str, object] = {
        "type": "exchange",
        "seq": seq,
        "request": request.model_dump(exclude_unset=True),
        "attempts": [a.model_dump(exclude_unset=True) for a in attempts],
    }
    if response_request_id is not None:
        fields["response"] = Response(
            request_id=response_request_id,
            error_status=response_error_status or 0,
            error_index=response_error_index or 0,
            varbinds=[  # type: ignore[list-item]
                {"oid": str(v.oid), "vtype": v.vtype, "vlen": v.vlen} for v in varbinds
            ],
        ).model_dump()
    if strays:
        fields["stray_responses"] = [s.model_dump(exclude_unset=True) for s in strays]
    if violations:
        fields["violations"] = [str(v) for v in violations]
    if malformed is not None:
        fields["malformed"] = malformed.model_dump(exclude_unset=True)
    return Exchange.model_validate(fields)


def event_record(*, at: float, kind: EventKind, detail: dict[str, object] | None = None) -> Event:
    fields: dict[str, object] = {"type": "event", "at": at, "kind": kind}
    if detail is not None:
        fields["detail"] = detail
    return Event.model_validate(fields)


def summary_record(
    *,
    at: float,
    exchanges: int,
    oids_seen: int,
    end_reason: str,
    violation_counts: Mapping[Violation, int],
) -> Summary:
    return Summary(
        type="summary",
        at=at,  # pyright: ignore[reportArgumentType]
        exchanges=exchanges,
        oids_seen=oids_seen,
        end_reason=end_reason,
        violation_counts={str(k): v for k, v in violation_counts.items()},
    )


def system_info_record(*, at: float, point: str, values: dict[str, str | int]) -> SystemInfo:
    return SystemInfo.model_validate(
        {"type": "system_info", "at": at, "point": point, "values": values}
    )
