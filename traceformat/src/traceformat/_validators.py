"""Wire-boundary invariants the generated models don't encode.

datamodel-code-generator does not translate the JSON Schema `not`/`if-then-else`
keywords into pydantic validators, so these checks close the gap between what
trace-format.schema.json forbids and what models.py actually rejects.
"""

from __future__ import annotations

from .models import Exchange, Pdu, Summary


class TraceFormatViolationError(ValueError):
    """A record matches its pydantic model but violates a schema invariant
    datamodel-code-generator couldn't translate (see trace-format.schema.json)."""


def check_invariants(record: object) -> None:
    if isinstance(record, Exchange):
        _check_exchange(record)
    elif isinstance(record, Summary):
        _check_summary(record)


def _check_exchange(exchange: Exchange) -> None:
    if exchange.response is not None and exchange.malformed is not None:
        raise TraceFormatViolationError("exchange: response and malformed are mutually exclusive")
    if exchange.request.pdu == Pdu.getbulk and (
        exchange.request.non_repeaters is None or exchange.request.max_repetitions is None
    ):
        raise TraceFormatViolationError(
            "exchange.request: getbulk requires non_repeaters and max_repetitions"
        )
    for attempt in exchange.attempts:
        if attempt.error is not None and attempt.received_at is not None:
            raise TraceFormatViolationError(
                "exchange.attempts[]: error set requires received_at null"
            )


def _check_summary(summary: Summary) -> None:
    for violation, count in summary.violation_counts.items():
        if count < 0:
            raise TraceFormatViolationError(f"summary.violation_counts[{violation!r}] must be >= 0")
