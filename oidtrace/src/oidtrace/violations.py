"""Pure protocol-violation checks for a single SNMP exchange.

This module is stateless: it takes the values produced by one exchange and
returns the list of violations observed.  The walker is responsible for
adding MALFORMED_BER (a structural decode failure); this module checks only
semantic violations derivable from successfully decoded values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from traceformat.vocab import Violation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.codec import Varbind
    from oidtrace.oid import Oid

from oidtrace.codec import EXCEPTION_TAGS


def check_exchange(  # noqa: PLR0913
    *,
    sent_id: int,
    returned_id: int,
    prev_oid: Oid,
    varbinds: Sequence[Varbind],
    response_raw: bytes,
    strays: Sequence[bytes],
) -> list[Violation]:
    """Check one exchange for protocol violations.

    Args:
        sent_id: The request-id we sent.
        returned_id: The request-id in the response.
        prev_oid: The OID cursor before this exchange (last data OID from the
            prior exchange, or the walk start OID).
        varbinds: The decoded varbinds from the response, in wire order.
        response_raw: The raw response bytes.
        strays: Raw bytes of datagrams that arrived outside the request/response
            cycle (e.g. delayed duplicates).

    Returns:
        A list of Violation values, deduplicated and in detection order.
        An empty list means a clean exchange.
    """
    violations: list[Violation] = []

    # --- REQUEST_ID_MISMATCH ---
    if returned_id != sent_id:
        violations.append(Violation.REQUEST_ID_MISMATCH)

    # --- OID_NOT_INCREASING ---
    # Walk varbinds in order; exception-tag varbinds are skipped and do NOT
    # advance the cursor.  Report at most once.
    cursor = prev_oid
    oid_violation_seen = False
    for vb in varbinds:
        if vb.tag in EXCEPTION_TAGS:
            continue  # skip — no cursor advance
        if not oid_violation_seen and vb.oid <= cursor:
            violations.append(Violation.OID_NOT_INCREASING)
            oid_violation_seen = True
        cursor = vb.oid

    # --- DUPLICATE_RESPONSE ---
    if any(s == response_raw for s in strays):
        violations.append(Violation.DUPLICATE_RESPONSE)

    return violations
