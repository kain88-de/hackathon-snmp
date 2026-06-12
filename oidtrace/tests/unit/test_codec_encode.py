"""Tests for oidtrace.codec — encode side only (Task 4).

Spec-driven cross-check: every encoded packet is decoded via pysnmp's v2c
Message spec (decoder.decode with asn1Spec) with the remainder asserted empty,
AND content is verified via the api getters (request-id, non-repeaters,
max-repetitions, varbind count, first OID for GetBulk; request-id, error-status,
error-index, varbind count for responses).

Wire-level assertions complement the spec-driven decode to catch symmetric
field-swaps that the pysnmp decode alone would miss.
"""

from __future__ import annotations

import pytest
from pyasn1.codec.ber import decoder  # type: ignore[import-untyped]
from pysnmp.proto.api import v2c  # type: ignore[import-untyped]

from oidtrace.codec import PDU_GETBULK, PDU_RESPONSE, encode_getbulk, encode_response
from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OID_1_3_6_1 = Oid.from_str("1.3.6.1")
_OID_1_3_6_1_2_1_1_1_0 = Oid.from_str("1.3.6.1.2.1.1.1.0")
_OID_1_3_6_1_2_1_1_3_0 = Oid.from_str("1.3.6.1.2.1.1.3.0")


def _decode_msg(raw: bytes) -> object:
    """Decode raw bytes via pysnmp's v2c Message spec; assert empty remainder."""
    msg, remainder = decoder.decode(raw, asn1Spec=v2c.Message())  # type: ignore[no-untyped-call]
    assert remainder == b"", f"Non-empty remainder after decode: {remainder!r}"
    return msg


def _get_bulk_pdu(msg: object) -> object:
    return v2c.apiMessage.get_pdu(msg)  # type: ignore[attr-defined]


def _get_response_pdu(msg: object) -> object:
    return v2c.apiMessage.get_pdu(msg)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# PDU tag constants
# ---------------------------------------------------------------------------


def test_pdu_tag_constants() -> None:
    assert PDU_GETBULK == 0xA5
    assert PDU_RESPONSE == 0xA2


# ---------------------------------------------------------------------------
# encode_getbulk — spec-driven decode + content assertions (bulk 10)
# ---------------------------------------------------------------------------


def test_encode_getbulk_spec_decode_bulk10() -> None:
    """Packet parses against pysnmp v2c Message spec with empty remainder."""
    raw = encode_getbulk(42, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    _decode_msg(raw)


def test_encode_getbulk_request_id_bulk10() -> None:
    raw = encode_getbulk(42, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    assert int(v2c.apiBulkPDU.get_request_id(pdu)) == 42  # type: ignore[attr-defined]


def test_encode_getbulk_non_repeaters_bulk10() -> None:
    raw = encode_getbulk(42, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    assert int(v2c.apiBulkPDU.get_non_repeaters(pdu)) == 0  # type: ignore[attr-defined]


def test_encode_getbulk_max_repetitions_bulk10() -> None:
    raw = encode_getbulk(42, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    assert int(v2c.apiBulkPDU.get_max_repetitions(pdu)) == 10  # type: ignore[attr-defined]


def test_encode_getbulk_varbind_count_bulk10() -> None:
    """GetBulk always has exactly one varbind (the start OID with NULL)."""
    raw = encode_getbulk(42, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    vbs = v2c.apiBulkPDU.get_varbinds(pdu)  # type: ignore[attr-defined]
    assert len(vbs) == 1


def test_encode_getbulk_first_oid_bulk10() -> None:
    """First varbind OID must match what was requested."""
    raw = encode_getbulk(42, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    vbs = v2c.apiBulkPDU.get_varbinds(pdu)  # type: ignore[attr-defined]
    assert vbs[0][0].prettyPrint() == str(_OID_1_3_6_1)


# ---------------------------------------------------------------------------
# encode_getbulk — spec-driven decode + content assertions (bulk 1)
# ---------------------------------------------------------------------------


def test_encode_getbulk_spec_decode_bulk1() -> None:
    raw = encode_getbulk(7, _OID_1_3_6_1, non_repeaters=0, max_repetitions=1)
    _decode_msg(raw)


def test_encode_getbulk_max_repetitions_bulk1() -> None:
    raw = encode_getbulk(7, _OID_1_3_6_1, non_repeaters=0, max_repetitions=1)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    assert int(v2c.apiBulkPDU.get_max_repetitions(pdu)) == 1  # type: ignore[attr-defined]


def test_encode_getbulk_request_id_bulk1() -> None:
    raw = encode_getbulk(7, _OID_1_3_6_1, non_repeaters=0, max_repetitions=1)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    assert int(v2c.apiBulkPDU.get_request_id(pdu)) == 7  # type: ignore[attr-defined]


def test_encode_getbulk_first_oid_bulk1() -> None:
    raw = encode_getbulk(7, _OID_1_3_6_1, non_repeaters=0, max_repetitions=1)
    msg = _decode_msg(raw)
    pdu = _get_bulk_pdu(msg)
    vbs = v2c.apiBulkPDU.get_varbinds(pdu)  # type: ignore[attr-defined]
    assert vbs[0][0].prettyPrint() == str(_OID_1_3_6_1)


# ---------------------------------------------------------------------------
# encode_getbulk — wire-level assertions (prevent symmetric field swaps)
# ---------------------------------------------------------------------------


def test_encode_getbulk_wire_max_repetitions_8() -> None:
    """max-repetitions=8 must produce the exact bytes 02 01 08 somewhere in the PDU."""
    raw = encode_getbulk(1, _OID_1_3_6_1, non_repeaters=0, max_repetitions=8)
    assert bytes([0x02, 0x01, 0x08]) in raw


def test_encode_getbulk_wire_pdu_tag() -> None:
    """GetBulk PDU uses tag 0xA5."""
    raw = encode_getbulk(1, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    assert 0xA5 in raw


def test_encode_getbulk_community_default_public() -> None:
    """Default community is b'public'."""
    raw = encode_getbulk(1, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    assert b"public" in raw


def test_encode_getbulk_community_custom() -> None:
    """Custom community string is embedded in the packet."""
    raw = encode_getbulk(1, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10, community=b"private")
    assert b"private" in raw
    assert b"public" not in raw


def test_encode_getbulk_version_is_1() -> None:
    """SNMPv2c messages encode version as INTEGER 1 (version-2c)."""
    raw = encode_getbulk(1, _OID_1_3_6_1, non_repeaters=0, max_repetitions=10)
    # version INTEGER 1 encodes as 02 01 01
    assert bytes([0x02, 0x01, 0x01]) in raw


# ---------------------------------------------------------------------------
# encode_response — spec-driven decode + content assertions
# ---------------------------------------------------------------------------


def test_encode_response_spec_decode_two_varbinds() -> None:
    """Response with OctetString + Counter32 parses with empty remainder."""
    raw = encode_response(
        99,
        [
            (_OID_1_3_6_1_2_1_1_1_0, 0x04, b""),  # OctetString empty
            (_OID_1_3_6_1_2_1_1_3_0, 0x41, b"\x00"),  # Counter32 zero
        ],
    )
    _decode_msg(raw)


def test_encode_response_request_id() -> None:
    raw = encode_response(
        99,
        [
            (_OID_1_3_6_1_2_1_1_1_0, 0x04, b""),
            (_OID_1_3_6_1_2_1_1_3_0, 0x41, b"\x00"),
        ],
    )
    msg = _decode_msg(raw)
    pdu = _get_response_pdu(msg)
    assert int(v2c.apiPDU.get_request_id(pdu)) == 99  # type: ignore[attr-defined]


def test_encode_response_error_status_default_zero() -> None:
    raw = encode_response(99, [(_OID_1_3_6_1_2_1_1_1_0, 0x04, b"")])
    msg = _decode_msg(raw)
    pdu = _get_response_pdu(msg)
    assert int(v2c.apiPDU.get_error_status(pdu)) == 0  # type: ignore[attr-defined]


def test_encode_response_error_index_default_zero() -> None:
    raw = encode_response(99, [(_OID_1_3_6_1_2_1_1_1_0, 0x04, b"")])
    msg = _decode_msg(raw)
    pdu = _get_response_pdu(msg)
    assert int(v2c.apiPDU.get_error_index(pdu, muteErrors=True)) == 0  # type: ignore[attr-defined]


def test_encode_response_varbind_count() -> None:
    raw = encode_response(
        99,
        [
            (_OID_1_3_6_1_2_1_1_1_0, 0x04, b""),
            (_OID_1_3_6_1_2_1_1_3_0, 0x41, b"\x00"),
        ],
    )
    msg = _decode_msg(raw)
    pdu = _get_response_pdu(msg)
    vbs = v2c.apiPDU.get_varbinds(pdu)  # type: ignore[attr-defined]
    assert len(vbs) == 2


def test_encode_response_varbind_oids() -> None:
    """Both varbind OIDs must be preserved in order."""
    raw = encode_response(
        99,
        [
            (_OID_1_3_6_1_2_1_1_1_0, 0x04, b""),
            (_OID_1_3_6_1_2_1_1_3_0, 0x41, b"\x00"),
        ],
    )
    msg = _decode_msg(raw)
    pdu = _get_response_pdu(msg)
    vbs = v2c.apiPDU.get_varbinds(pdu)  # type: ignore[attr-defined]
    assert vbs[0][0].prettyPrint() == str(_OID_1_3_6_1_2_1_1_1_0)
    assert vbs[1][0].prettyPrint() == str(_OID_1_3_6_1_2_1_1_3_0)


# ---------------------------------------------------------------------------
# encode_response — wire-level assertions
# ---------------------------------------------------------------------------


def test_encode_response_wire_pdu_tag() -> None:
    """Response PDU uses tag 0xA2."""
    raw = encode_response(1, [(_OID_1_3_6_1, 0x04, b"")])
    assert 0xA2 in raw


def test_encode_response_community_default_public() -> None:
    raw = encode_response(1, [(_OID_1_3_6_1, 0x04, b"")])
    assert b"public" in raw


def test_encode_response_community_custom() -> None:
    raw = encode_response(1, [(_OID_1_3_6_1, 0x04, b"")], community=b"secret")
    assert b"secret" in raw
    assert b"public" not in raw


def test_encode_response_custom_error_status() -> None:
    """error_status and error_index are passed through."""
    raw = encode_response(1, [(_OID_1_3_6_1, 0x05, b"")], error_status=2, error_index=1)
    msg = _decode_msg(raw)
    pdu = _get_response_pdu(msg)
    assert int(v2c.apiPDU.get_error_status(pdu)) == 2  # type: ignore[attr-defined]
    assert int(v2c.apiPDU.get_error_index(pdu, muteErrors=True)) == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("tag", [0x04, 0x41])
def test_encode_response_varbind_tag_preserved(tag: int) -> None:
    """The varbind value tag is encoded in the wire bytes."""
    raw = encode_response(1, [(_OID_1_3_6_1, tag, b"\x00")])
    assert tag in raw
