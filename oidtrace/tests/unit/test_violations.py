"""Tests for violations.check_exchange — pure protocol violation detection."""

from traceformat.vocab import Violation

from oidtrace.codec import EXCEPTION_TAGS, Varbind
from oidtrace.oid import Oid
from oidtrace.violations import check_exchange

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXCEPTION_TAG = next(iter(EXCEPTION_TAGS))  # first tag in EXCEPTION_TAGS set


def _vb(oid_str: str, tag: int = 0x04) -> Varbind:
    return Varbind(oid=Oid.from_str(oid_str), tag=tag, value=b"x")


def _clean(
    *,
    sent_id: int = 1,
    returned_id: int = 1,
    prev_oid: Oid | None = None,
    varbinds: list[Varbind] | None = None,
    response_raw: bytes = b"response",
    strays: list[bytes] | None = None,
) -> list[Violation]:
    """Call check_exchange with sane defaults; override specific args."""
    return check_exchange(
        sent_id=sent_id,
        returned_id=returned_id,
        prev_oid=prev_oid if prev_oid is not None else Oid.from_str("1.2.0"),
        varbinds=varbinds if varbinds is not None else [_vb("1.3.0")],
        response_raw=response_raw,
        strays=strays if strays is not None else [],
    )


# ---------------------------------------------------------------------------
# REQUEST_ID_MISMATCH
# ---------------------------------------------------------------------------


def test_mismatch_detected() -> None:
    result = _clean(sent_id=10, returned_id=99)
    assert Violation.REQUEST_ID_MISMATCH in result


def test_mismatch_clean_when_equal() -> None:
    result = _clean(sent_id=42, returned_id=42)
    assert Violation.REQUEST_ID_MISMATCH not in result


# ---------------------------------------------------------------------------
# OID_NOT_INCREASING — prev_oid boundary (first varbind vs prev_oid)
# ---------------------------------------------------------------------------


def test_equal_oid_to_prev_counts_as_not_increasing() -> None:
    # First varbind OID == prev_oid → not increasing
    result = _clean(prev_oid=Oid.from_str("1.3.0"), varbinds=[_vb("1.3.0")])
    assert Violation.OID_NOT_INCREASING in result


def test_oid_less_than_prev_counts_as_not_increasing() -> None:
    result = _clean(prev_oid=Oid.from_str("1.3.0"), varbinds=[_vb("1.2.99")])
    assert Violation.OID_NOT_INCREASING in result


# ---------------------------------------------------------------------------
# OID_NOT_INCREASING — consecutive varbinds
# ---------------------------------------------------------------------------


def test_violation_between_two_consecutive_varbinds() -> None:
    # Second varbind OID <= first → violation
    vbs = [_vb("1.3.1"), _vb("1.3.1")]  # equal between two varbinds
    result = _clean(prev_oid=Oid.from_str("1.2.0"), varbinds=vbs)
    assert Violation.OID_NOT_INCREASING in result


def test_strictly_increasing_clean() -> None:
    vbs = [_vb("1.3.1"), _vb("1.3.2"), _vb("1.3.3")]
    result = _clean(prev_oid=Oid.from_str("1.2.0"), varbinds=vbs)
    assert Violation.OID_NOT_INCREASING not in result


# ---------------------------------------------------------------------------
# OID_NOT_INCREASING — exception-tag varbinds skipped without advancing cursor
# ---------------------------------------------------------------------------


def test_exception_tag_skipped_no_cursor_advance() -> None:
    # Sequence: prev=1.2.0  →  data 1.2.1  →  exception(1.1.5)  →  data 1.3.0
    # The exception tag varbind (1.1.5) is skipped and does NOT advance the
    # cursor, so the subsequent data varbind 1.3.0 is compared against 1.2.1
    # (the last data cursor), making this a clean walk.
    vbs = [
        _vb("1.2.1"),  # data, cursor → 1.2.1
        _vb("1.1.5", _EXCEPTION_TAG),  # exception — skipped, cursor stays 1.2.1
        _vb("1.3.0"),  # data, 1.3.0 > 1.2.1 → clean
    ]
    result = _clean(prev_oid=Oid.from_str("1.2.0"), varbinds=vbs)
    assert Violation.OID_NOT_INCREASING not in result


def test_exception_tag_only_varbinds_no_violation() -> None:
    # All exception tags → no data cursor movement → no OID_NOT_INCREASING
    vbs = [_vb("1.1.0", _EXCEPTION_TAG), _vb("0.9.0", _EXCEPTION_TAG)]
    result = _clean(prev_oid=Oid.from_str("1.2.0"), varbinds=vbs)
    assert Violation.OID_NOT_INCREASING not in result


# ---------------------------------------------------------------------------
# OID_NOT_INCREASING — reported only once
# ---------------------------------------------------------------------------


def test_not_increasing_reported_once_even_with_multiple_bad_varbinds() -> None:
    # Multiple non-increasing varbinds → violation appears exactly once
    vbs = [_vb("1.3.1"), _vb("1.3.0"), _vb("1.2.9")]
    result = _clean(prev_oid=Oid.from_str("1.2.0"), varbinds=vbs)
    assert result.count(Violation.OID_NOT_INCREASING) == 1


# ---------------------------------------------------------------------------
# DUPLICATE_RESPONSE
# ---------------------------------------------------------------------------


def test_duplicate_detected_when_stray_equals_response() -> None:
    raw = b"snmp-response-bytes"
    result = _clean(response_raw=raw, strays=[raw])
    assert Violation.DUPLICATE_RESPONSE in result


def test_duplicate_not_detected_when_stray_differs() -> None:
    result = _clean(response_raw=b"response", strays=[b"other"])
    assert Violation.DUPLICATE_RESPONSE not in result


def test_duplicate_not_detected_with_no_strays() -> None:
    result = _clean(response_raw=b"response", strays=[])
    assert Violation.DUPLICATE_RESPONSE not in result


# ---------------------------------------------------------------------------
# Clean exchange → empty list
# ---------------------------------------------------------------------------


def test_clean_exchange_produces_empty_list() -> None:
    result = _clean()
    assert result == []
