"""Tests for oidtrace.violations.check_exchange — pure checks over decoded exchanges."""

from traceformat.vocab import Violation

from oidtrace.codec import EXCEPTION_TAGS, Varbind
from oidtrace.oid import Oid
from oidtrace.violations import check_exchange

# Helpers
_OID = Oid.from_str
_PLAIN_TAG = 0x04  # OctetString — never in EXCEPTION_TAGS


def _vb(oid_str: str, tag: int = _PLAIN_TAG) -> Varbind:
    return Varbind(oid=_OID(oid_str), tag=tag, value=b"")


# ---------------------------------------------------------------------------
# request-id-mismatch


def test_request_id_mismatch_detected() -> None:
    violations = check_exchange(
        sent_id=1,
        returned_id=2,
        prev_oid=_OID("1.3.6.1"),
        varbinds=[],
        response_raw=b"data",
        strays=[],
    )
    assert Violation.REQUEST_ID_MISMATCH in violations


def test_request_id_match_no_mismatch_violation() -> None:
    violations = check_exchange(
        sent_id=5,
        returned_id=5,
        prev_oid=_OID("1.3.6.1"),
        varbinds=[],
        response_raw=b"data",
        strays=[],
    )
    assert Violation.REQUEST_ID_MISMATCH not in violations


# ---------------------------------------------------------------------------
# oid-not-increasing


def test_oid_equal_to_prev_is_not_increasing() -> None:
    """Equal OID counts as non-increasing (must be strictly greater)."""
    prev = _OID("1.3.6.1.2.1.1.1.0")
    violations = check_exchange(
        sent_id=1,
        returned_id=1,
        prev_oid=prev,
        varbinds=[_vb("1.3.6.1.2.1.1.1.0")],  # same as prev
        response_raw=b"data",
        strays=[],
    )
    assert Violation.OID_NOT_INCREASING in violations


def test_oid_violation_between_two_varbinds() -> None:
    """Non-increasing between consecutive varbinds (not just vs. prev_oid)."""
    violations = check_exchange(
        sent_id=1,
        returned_id=1,
        prev_oid=_OID("1.3.6.1.2.1.1.1.0"),
        varbinds=[
            _vb("1.3.6.1.2.1.1.2.0"),  # OK: greater than prev_oid
            _vb("1.3.6.1.2.1.1.1.5"),  # BAD: less than previous varbind
        ],
        response_raw=b"data",
        strays=[],
    )
    assert Violation.OID_NOT_INCREASING in violations


def test_oid_increasing_is_clean() -> None:
    violations = check_exchange(
        sent_id=1,
        returned_id=1,
        prev_oid=_OID("1.3.6.1.2.1.1.1.0"),
        varbinds=[
            _vb("1.3.6.1.2.1.1.2.0"),
            _vb("1.3.6.1.2.1.1.3.0"),
        ],
        response_raw=b"data",
        strays=[],
    )
    assert Violation.OID_NOT_INCREASING not in violations


def test_exception_tag_varbind_skipped_by_ordering_check() -> None:
    """EndOfMibView (0x82) between two data varbinds — ordering check skips it."""
    end_of_mib_tag = 0x82
    assert end_of_mib_tag in EXCEPTION_TAGS
    violations = check_exchange(
        sent_id=1,
        returned_id=1,
        prev_oid=_OID("1.3.6.1.2.1.1.1.0"),
        varbinds=[
            _vb("1.3.6.1.2.1.1.2.0"),  # good data varbind
            _vb("1.3.6.1.2.1.1.1.5", end_of_mib_tag),  # exception — skip
            _vb("1.3.6.1.2.1.1.3.0"),  # next data varbind: still increasing vs 1.2.0
        ],
        response_raw=b"data",
        strays=[],
    )
    assert Violation.OID_NOT_INCREASING not in violations


# ---------------------------------------------------------------------------
# duplicate-response


def test_duplicate_response_detected_when_stray_equals_response() -> None:
    raw = b"\x30\x01\x00"
    violations = check_exchange(
        sent_id=1,
        returned_id=1,
        prev_oid=_OID("1.3"),
        varbinds=[],
        response_raw=raw,
        strays=[raw],  # exact duplicate
    )
    assert Violation.DUPLICATE_RESPONSE in violations


def test_different_stray_does_not_trigger_duplicate() -> None:
    violations = check_exchange(
        sent_id=1,
        returned_id=1,
        prev_oid=_OID("1.3"),
        varbinds=[],
        response_raw=b"\x30\x01\x00",
        strays=[b"\x30\x01\x01"],  # different bytes
    )
    assert Violation.DUPLICATE_RESPONSE not in violations


# ---------------------------------------------------------------------------
# clean exchange


def test_clean_exchange_returns_empty_list() -> None:
    violations = check_exchange(
        sent_id=42,
        returned_id=42,
        prev_oid=_OID("1.3.6.1.2.1.1.1.0"),
        varbinds=[
            _vb("1.3.6.1.2.1.1.2.0"),
            _vb("1.3.6.1.2.1.1.3.0"),
        ],
        response_raw=b"unique",
        strays=[b"other"],
    )
    assert violations == []
