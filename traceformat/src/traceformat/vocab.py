"""Producer-side closed vocabularies for the open-enum fields in the trace format.

Readers treat these as open enums (unknown values are tolerated per § 3); the producer
uses these StrEnums so that ``json.dumps`` emits the correct wire strings directly.
"""

from enum import StrEnum


class Violation(StrEnum):
    """Protocol violations observable on a single exchange (§ 4.3)."""

    REQUEST_ID_MISMATCH = "request-id-mismatch"
    OID_NOT_INCREASING = "oid-not-increasing"
    MISSING_END_OF_MIB = "missing-end-of-mib"
    DUPLICATE_RESPONSE = "duplicate-response"
    MALFORMED_BER = "malformed-ber"
    RESPONSE_FROM_UNEXPECTED_SOURCE = "response-from-unexpected-source"


class EndReason(StrEnum):
    """Why the walk terminated (``summary.end_reason``, § 4.5)."""

    COMPLETED = "completed"
    UNRESPONSIVE = "unresponsive"
    INTERRUPTED = "interrupted"
    TIME_BUDGET_EXCEEDED = "time-budget-exceeded"
    OID_LOOP = "oid-loop"


class EventKind(StrEnum):
    """Walk-level event kinds (``event.kind``, § 4.4)."""

    OID_LOOP_DETECTED = "oid-loop-detected"
    WALK_ABORTED_BY_USER = "walk-aborted-by-user"
    TIME_BUDGET_EXCEEDED = "time-budget-exceeded"


class AttemptError(StrEnum):
    """Socket-level errors on a single attempt (``attempts[].error``, § 4.3)."""

    ICMP_PORT_UNREACHABLE = "icmp-port-unreachable"
    ICMP_HOST_UNREACHABLE = "icmp-host-unreachable"
    SEND_FAILED = "send-failed"
