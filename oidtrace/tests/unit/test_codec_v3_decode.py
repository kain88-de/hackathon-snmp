"""Tests for decode_v3_message and the _decode_pdu refactor (Task 3).

Coverage target:
  - decode_v3_message: all success paths (discovery, getbulk, response, report)
  - decrypt guard (ScopedPDU tag 0x04 -> Malformed)
  - version mismatch (v2c packet -> Malformed)
  - garbage input -> Malformed
  - decode_message regression after _decode_pdu refactor
"""

from __future__ import annotations

import pytest

from oidtrace.auth import AuthProto, password_to_key
from oidtrace.ber import read_tlv
from oidtrace.codec import (
    PDU_GET,
    PDU_GETBULK,
    PDU_REPORT,
    PDU_RESPONSE,
    Malformed,
    Message,
    authenticate_msg,
    decode_message,
    decode_v3_message,
    encode_getbulk,
    encode_v3_discovery,
    encode_v3_getbulk,
    encode_v3_response,
)
from oidtrace.oid import Oid

_ENGINE_ID = b"\x80\x00\x1f\x88\x04\x01\x02\x03\x04\x05\x06\x07"
_KUL = password_to_key(b"authpass", _ENGINE_ID, AuthProto.MD5)

_OID = Oid.from_str("1.3.6.1.2.1.1.1.0")
_ENG_ID = b"\x80\x00\x1f\x88\x04"


# ---------------------------------------------------------------------------
# Discovery probe: encode_v3_discovery -> decode_v3_message
# ---------------------------------------------------------------------------


def test_v3_discovery_pdu_tag_is_get() -> None:
    raw = encode_v3_discovery(99, 42)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.pdu_tag == PDU_GET


def test_v3_discovery_varbinds_empty() -> None:
    raw = encode_v3_discovery(99, 42)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.varbinds == ()


def test_v3_discovery_engine_id_empty() -> None:
    raw = encode_v3_discovery(99, 42)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.engine_id == b""


def test_v3_discovery_msg_id() -> None:
    raw = encode_v3_discovery(99, 42)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.msg_id == 99


def test_v3_discovery_request_id() -> None:
    raw = encode_v3_discovery(99, 42)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.request_id == 42


# ---------------------------------------------------------------------------
# GetBulk: encode_v3_getbulk -> decode_v3_message
# ---------------------------------------------------------------------------


def test_v3_getbulk_pdu_tag() -> None:
    raw = encode_v3_getbulk(99, 42, _OID, 10, _ENG_ID, 5, 100, b"u")
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.pdu_tag == PDU_GETBULK


def test_v3_getbulk_engine_id() -> None:
    raw = encode_v3_getbulk(99, 42, _OID, 10, _ENG_ID, 5, 100, b"u")
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.engine_id == _ENG_ID


def test_v3_getbulk_engine_boots() -> None:
    raw = encode_v3_getbulk(99, 42, _OID, 10, _ENG_ID, 5, 100, b"u")
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.engine_boots == 5


def test_v3_getbulk_engine_time() -> None:
    raw = encode_v3_getbulk(99, 42, _OID, 10, _ENG_ID, 5, 100, b"u")
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.engine_time == 100


def test_v3_getbulk_msg_id() -> None:
    raw = encode_v3_getbulk(99, 42, _OID, 10, _ENG_ID, 5, 100, b"u")
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.msg_id == 99


# ---------------------------------------------------------------------------
# Response: encode_v3_response -> decode_v3_message
# ---------------------------------------------------------------------------


def test_v3_response_pdu_tag() -> None:
    raw = encode_v3_response(7, 55, [(_OID, 0x04, b"hi")], _ENG_ID)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.pdu_tag == PDU_RESPONSE


def test_v3_response_request_id() -> None:
    raw = encode_v3_response(7, 55, [(_OID, 0x04, b"hi")], _ENG_ID)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.request_id == 55


def test_v3_response_varbind_count() -> None:
    raw = encode_v3_response(7, 55, [(_OID, 0x04, b"hi")], _ENG_ID)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert len(msg.varbinds) == 1


# ---------------------------------------------------------------------------
# Report PDU
# ---------------------------------------------------------------------------


def test_v3_report_pdu_tag() -> None:
    raw = encode_v3_response(7, 55, [(_OID, 0x04, b"hi")], _ENG_ID, pdu_tag=PDU_REPORT)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, _params = result
    assert msg.pdu_tag == PDU_REPORT


# ---------------------------------------------------------------------------
# Encrypted ScopedPDU (tag 0x04 instead of 0x30) -> Malformed
# ---------------------------------------------------------------------------


def _make_encrypted_scoped_pdu_packet() -> bytes:
    """Build a v3 packet where the ScopedPDU is wrapped in OCTET STRING (0x04)
    instead of SEQUENCE (0x30), simulating an encrypted (Priv) message."""
    # Build a valid discovery packet, then locate and flip the ScopedPDU tag.
    raw = bytearray(encode_v3_discovery(1, 1))
    # The outer SEQUENCE body starts at offset 2 (short-form length).
    # Structure: outer SEQUENCE -> version INTEGER -> msgGlobalData SEQUENCE ->
    #            USM OCTET_STRING -> ScopedPDU SEQUENCE
    # Parse to find the ScopedPDU tag position.
    outer_tag, outer_body, _ = read_tlv(bytes(raw), 0)
    assert outer_tag == 0x30
    i = 0
    # skip version
    _, _, i = read_tlv(outer_body, i)
    # skip msgGlobalData
    _, _, i = read_tlv(outer_body, i)
    # skip USM OCTET_STRING
    _, _, i = read_tlv(outer_body, i)
    # i now points at start of ScopedPDU within outer_body
    # Find absolute offset: outer TLV header is 2 bytes (short-form, <128 body)
    outer_header_size = 2
    scoped_pdu_abs_offset = outer_header_size + i
    # Flip ScopedPDU tag from 0x30 to 0x04
    assert raw[scoped_pdu_abs_offset] == 0x30, (
        f"Expected 0x30 at {scoped_pdu_abs_offset}, got 0x{raw[scoped_pdu_abs_offset]:02x}"
    )
    raw[scoped_pdu_abs_offset] = 0x04
    return bytes(raw)


def test_encrypted_scoped_pdu_returns_malformed() -> None:
    raw = _make_encrypted_scoped_pdu_packet()
    result = decode_v3_message(raw)
    assert isinstance(result, Malformed)


def test_encrypted_scoped_pdu_error_mentions_encrypt_or_priv() -> None:
    raw = _make_encrypted_scoped_pdu_packet()
    result = decode_v3_message(raw)
    assert isinstance(result, Malformed)
    error_lower = result.error.lower()
    assert "encrypt" in error_lower or "priv" in error_lower


# ---------------------------------------------------------------------------
# Version mismatch: v2c packet -> Malformed
# ---------------------------------------------------------------------------


def test_v2c_packet_returns_malformed() -> None:
    raw = encode_getbulk(1, _OID, 0, 5)
    result = decode_v3_message(raw)
    assert isinstance(result, Malformed)


# ---------------------------------------------------------------------------
# Garbage inputs -> Malformed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [b"", b"\xff", b"\x00" * 4, b"GET / HTTP/1.1\r\n"],
    ids=["empty", "single-ff", "null-bytes", "ascii"],
)
def test_garbage_returns_malformed(raw: bytes) -> None:
    result = decode_v3_message(raw)
    assert isinstance(result, Malformed)


def test_garbage_never_raises() -> None:
    for raw in [b"", b"\xff", b"\x00" * 100, b"random bytes here"]:
        result = decode_v3_message(raw)
        assert isinstance(result, (tuple, Malformed))


# ---------------------------------------------------------------------------
# Regression: decode_message still works after _decode_pdu refactor
# ---------------------------------------------------------------------------


def test_regression_decode_message_getbulk() -> None:
    raw = encode_getbulk(42, _OID, 0, 5)
    result = decode_message(raw)
    assert isinstance(result, Message)
    assert result.pdu_tag == PDU_GETBULK
    assert result.request_id == 42


# ---------------------------------------------------------------------------
# auth_params field in V3Params
# ---------------------------------------------------------------------------


def test_decode_v3_authenticated_message_has_nonzero_auth_params() -> None:
    """decode_v3_message of a signed message returns 12 non-zero auth_params bytes."""
    raw = encode_v3_getbulk(1, 42, _OID, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    signed = authenticate_msg(raw, _KUL, AuthProto.MD5)
    result = decode_v3_message(signed)
    assert isinstance(result, tuple)
    _msg, params = result
    assert len(params.auth_params) == 12
    assert params.auth_params != b"\x00" * 12


def test_decode_v3_discovery_auth_params_empty() -> None:
    """decode_v3_message of a discovery probe returns empty auth_params."""
    raw = encode_v3_discovery(1, 42)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    _msg, params = result
    assert params.auth_params == b""
