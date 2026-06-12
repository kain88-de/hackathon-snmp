"""Pure checks over decoded SNMP exchanges.

check_exchange detects: request-id-mismatch, oid-not-increasing,
duplicate-response.  No I/O, no state.  "malformed-ber" is added by
the walker, not here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from traceformat.vocab import Violation

from oidtrace.codec import EXCEPTION_TAGS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.codec import Varbind
    from oidtrace.oid import Oid


def check_exchange(
    *,
    sent_id: int,
    returned_id: int,
    prev_oid: Oid,
    varbinds: Sequence[Varbind],
    response_raw: bytes,
    strays: Sequence[bytes],
) -> list[Violation]:
    """Return a list of violation strings for one request/response exchange."""
    violations: list[Violation] = []

    if returned_id != sent_id:
        violations.append(Violation.REQUEST_ID_MISMATCH)

    cursor = prev_oid
    for vb in varbinds:
        if vb.tag in EXCEPTION_TAGS:
            continue
        if vb.oid <= cursor:
            violations.append(Violation.OID_NOT_INCREASING)
            break
        cursor = vb.oid

    if any(s == response_raw for s in strays):
        violations.append(Violation.DUPLICATE_RESPONSE)

    return violations
