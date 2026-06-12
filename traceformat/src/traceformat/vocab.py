"""Closed producer-side vocabularies for the OID trace format.

Readers should treat these as open enums. StrEnum so JSON serialization
yields wire strings.
"""

from __future__ import annotations

from enum import StrEnum


class Violation(StrEnum):
    REQUEST_ID_MISMATCH = "request-id-mismatch"
    OID_NOT_INCREASING = "oid-not-increasing"
    DUPLICATE_RESPONSE = "duplicate-response"
    MALFORMED_BER = "malformed-ber"


class EndReason(StrEnum):
    COMPLETED = "completed"
    UNRESPONSIVE = "unresponsive"
    INTERRUPTED = "interrupted"
    TIME_BUDGET_EXCEEDED = "time-budget-exceeded"
    OID_LOOP = "oid-loop"


class EventKind(StrEnum):
    OID_LOOP_DETECTED = "oid-loop-detected"
    WALK_ABORTED_BY_USER = "walk-aborted-by-user"
    TIME_BUDGET_EXCEEDED = "time-budget-exceeded"


class AttemptError(StrEnum):
    ICMP_PORT_UNREACHABLE = "icmp-port-unreachable"
    ICMP_HOST_UNREACHABLE = "icmp-host-unreachable"
    SEND_FAILED = "send-failed"
