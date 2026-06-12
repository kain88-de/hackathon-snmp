"""Record builders for OIDTrace trace files.

Builders construct and return validated ``traceformat`` model instances.
Varbind values are never serialized — the "no values" promise is enforced at
this boundary (only oid/vtype/vlen cross into the record).

The nested-dict parameters (``request``, ``attempts``, ``settings``, ...) are
validated at construction time by pydantic; conditional keys stay *unset*
(omitted from the serialized record) by not being passed at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traceformat.models import (
    Attempt,
    Event,
    Exchange,
    Header,
    Malformed,
    Request,
    Response,
    Session,
    Settings,
    Snmp,
    StrayResponse,
    Summary,
    SystemInfo,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    settings: dict[str, Any],
) -> Header:
    optional: dict[str, Any] = {}
    if label is not None:
        optional["label"] = label
    return Header(
        type="header",
        format_version=1,
        tool=tool,
        started_at=started_at,  # pyright: ignore[reportArgumentType]
        session=Session(id=session_id, run=run, runs_total=runs_total),
        snmp=Snmp.model_validate({"version": snmp_version}),
        settings=Settings.model_validate(settings),
        **optional,
    )


def exchange_record(
    *,
    seq: int,
    request: dict[str, Any],
    attempts: list[dict[str, Any]],
    response_fields: dict[str, Any] | None,
    varbinds: Sequence[Varbind],
    strays: list[dict[str, Any]],
    violations: list[str],
    malformed: dict[str, Any] | None,
) -> Exchange:
    optional: dict[str, Any] = {}
    if response_fields is not None:
        optional["response"] = Response.model_validate(
            {
                **response_fields,
                "varbinds": [
                    {"oid": str(v.oid), "vtype": v.vtype, "vlen": v.vlen} for v in varbinds
                ],
            }
        )
    if strays:
        optional["stray_responses"] = [StrayResponse.model_validate(s) for s in strays]
    if violations:
        optional["violations"] = violations
    if malformed is not None:
        optional["malformed"] = Malformed.model_validate(malformed)
    return Exchange(
        type="exchange",
        seq=seq,
        request=Request.model_validate(request),
        attempts=[Attempt.model_validate(a) for a in attempts],
        **optional,
    )


def event_record(*, at: float, kind: str, detail: dict[str, Any] | None = None) -> Event:
    optional: dict[str, Any] = {}
    if detail is not None:
        optional["detail"] = detail
    return Event(type="event", at=at, kind=kind, **optional)  # pyright: ignore[reportArgumentType]


def summary_record(
    *,
    at: float,
    exchanges: int,
    oids_seen: int,
    end_reason: str,
    violation_counts: dict[str, int],
) -> Summary:
    return Summary(
        type="summary",
        at=at,  # pyright: ignore[reportArgumentType]
        exchanges=exchanges,
        oids_seen=oids_seen,
        end_reason=end_reason,
        violation_counts=violation_counts,
    )


def system_info_record(*, at: float, point: str, values: dict[str, str | int]) -> SystemInfo:
    return SystemInfo.model_validate(
        {"type": "system_info", "at": at, "point": point, "values": values}
    )
