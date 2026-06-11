"""Record builders for OIDTrace trace files.

builders return dicts; varbind values are never serialized — the 'no values'
promise is enforced at this boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    settings: dict,
) -> dict:
    rec: dict = {
        "type": "header",
        "format_version": 1,
        "tool": tool,
        "started_at": started_at,
        "session": {"id": session_id, "run": run, "runs_total": runs_total},
        "snmp": {"version": snmp_version},
        "settings": settings,
    }
    if label is not None:
        rec["label"] = label
    return rec


def exchange_record(
    *,
    seq: int,
    request: dict,
    attempts: list[dict],
    response_fields: dict | None,
    varbinds: Sequence[Varbind],
    strays: list[dict],
    violations: list[str],
    malformed: dict | None,
) -> dict:
    rec: dict = {
        "type": "exchange",
        "seq": seq,
        "request": request,
        "attempts": attempts,
    }
    if response_fields is not None:
        rec["response"] = {
            **response_fields,
            "varbinds": [{"oid": str(v.oid), "vtype": v.vtype, "vlen": v.vlen} for v in varbinds],
        }
    if strays:
        rec["stray_responses"] = strays
    if violations:
        rec["violations"] = violations
    if malformed is not None:
        rec["malformed"] = malformed
    return rec


def event_record(*, at: float, kind: str, detail: dict | None = None) -> dict:
    rec: dict = {"type": "event", "at": at, "kind": kind}
    if detail is not None:
        rec["detail"] = detail
    return rec


def summary_record(
    *,
    at: float,
    exchanges: int,
    oids_seen: int,
    end_reason: str,
    violation_counts: dict[str, int],
) -> dict:
    return {
        "type": "summary",
        "at": at,
        "exchanges": exchanges,
        "oids_seen": oids_seen,
        "end_reason": end_reason,
        "violation_counts": violation_counts,
    }


def system_info_record(*, at: float, point: str, values: dict) -> dict:
    return {"type": "system_info", "at": at, "point": point, "values": values}
