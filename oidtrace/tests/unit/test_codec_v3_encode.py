"""Tests for SNMPv3 encoding — encode_v3_discovery, encode_v3_getbulk, encode_v3_response, V3Params.

Wire format constraints:
  - discovery probe: 64 bytes exactly (matches live snmpwalk capture)
  - All wire assertions verify BER structure matches SNMPv3 RFC 3412/3414
"""

from __future__ import annotations

import pytest

from oidtrace.auth import AuthProto, password_to_key
from oidtrace.ber import encode_oid
from oidtrace.codec import (
    _AUTH_PARAMS_PLACEHOLDER,
    PDU_GET,
    PDU_REPORT,
    V3Params,
    authenticate_msg,
    decode_v3_message,
    encode_v3_discovery,
    encode_v3_getbulk,
    encode_v3_response,
    verify_auth,
)
from oidtrace.oid import Oid

_ENGINE_ID = b"\x80\x00\x1f\x88\x04\x01\x02\x03\x04\x05\x06\x07"
_KUL_MD5 = password_to_key(b"authpass", _ENGINE_ID, AuthProto.MD5)
_KUL_SHA = password_to_key(b"authpass", _ENGINE_ID, AuthProto.SHA)
_KUL = _KUL_MD5  # kept for existing single-proto tests


def _kul_for(proto: AuthProto) -> bytes:
    return _KUL_SHA if proto == AuthProto.SHA else _KUL_MD5


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_OID_1_3_6_1 = Oid.from_str("1.3.6.1")


# ---------------------------------------------------------------------------
# V3Params frozen dataclass
# ---------------------------------------------------------------------------


def test_v3_params_frozen() -> None:
    """V3Params is frozen; assigning .engine_boots raises AttributeError."""
    params = V3Params(engine_id=b"x", engine_boots=1, engine_time=2, msg_id=3)
    with pytest.raises(AttributeError):
        params.engine_boots = 999  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PDU tag constants
# ---------------------------------------------------------------------------


def test_pdu_tag_constants() -> None:
    """PDU_GET = 0xA0, PDU_REPORT = 0xA8."""
    assert PDU_GET == 0xA0
    assert PDU_REPORT == 0xA8


# ---------------------------------------------------------------------------
# encode_v3_discovery — size constraint
# ---------------------------------------------------------------------------


def test_encode_v3_discovery_exact_64_bytes_live_inputs() -> None:
    """encode_v3_discovery(0x10000001, 0x20000001) produces exactly 64 bytes."""
    raw = encode_v3_discovery(0x10000001, 0x20000001)
    assert len(raw) == 64, f"Expected 64 bytes, got {len(raw)}"


# ---------------------------------------------------------------------------
# encode_v3_discovery — version INTEGER 3
# ---------------------------------------------------------------------------


def test_encode_v3_discovery_version_3() -> None:
    """SNMPv3 encodes version as INTEGER 3 (02 01 03)."""
    raw = encode_v3_discovery(1, 42)
    assert bytes([0x02, 0x01, 0x03]) in raw


# ---------------------------------------------------------------------------
# encode_v3_discovery — GetRequest PDU tag
# ---------------------------------------------------------------------------


def test_encode_v3_discovery_pdu_tag_is_getrequest() -> None:
    """Discovery probe uses GetRequest tag 0xA0."""
    raw = encode_v3_discovery(1, 42)
    assert 0xA0 in raw


# ---------------------------------------------------------------------------
# encode_v3_discovery — empty VarBindList
# ---------------------------------------------------------------------------


def test_encode_v3_discovery_empty_varbind_list() -> None:
    """Discovery probe has empty VarBindList (30 00)."""
    raw = encode_v3_discovery(1, 42)
    assert bytes([0x30, 0x00]) in raw


# ---------------------------------------------------------------------------
# encode_v3_discovery — empty USM fields
# ---------------------------------------------------------------------------


def test_encode_v3_discovery_empty_usm_fields() -> None:
    """Discovery probe has >= 5 empty OCTET STRINGs (04 00) for USM+ScopedPDU fields."""
    raw = encode_v3_discovery(1, 42)
    # engineID, username, auth_params, priv_params, contextEngineID, contextName
    assert raw.count(bytes([0x04, 0x00])) >= 5


# ---------------------------------------------------------------------------
# encode_v3_getbulk — presence of OID and max_repetitions
# ---------------------------------------------------------------------------


def test_encode_v3_getbulk_contains_oid() -> None:
    """GetBulk request contains the OID."""
    oid = _OID_1_3_6_1
    raw = encode_v3_getbulk(1, 42, oid, 7, b"engine", 1, 0, b"user")
    # The OID is BER-encoded, and the repr should be in the raw bytes
    assert encode_oid(oid) in raw


def test_encode_v3_getbulk_contains_max_repetitions() -> None:
    """GetBulk request encodes max_repetitions=7 (02 01 07)."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, b"engine", 1, 0, b"user")
    assert bytes([0x02, 0x01, 0x07]) in raw


# ---------------------------------------------------------------------------
# encode_v3_getbulk — PDU tag, engine_id, username
# ---------------------------------------------------------------------------


def test_encode_v3_getbulk_pdu_tag_is_getbulk() -> None:
    """GetBulk uses tag 0xA5."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, b"engine", 1, 0, b"user")
    assert 0xA5 in raw


def test_encode_v3_getbulk_contains_engine_id() -> None:
    """GetBulk request contains the engine_id."""
    engine_id = b"myengine"
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, engine_id, 1, 0, b"user")
    assert engine_id in raw


def test_encode_v3_getbulk_contains_username() -> None:
    """GetBulk request contains the username."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, b"engine", 1, 0, b"user")
    assert b"user" in raw


# ---------------------------------------------------------------------------
# encode_v3_response — Response PDU tag (default)
# ---------------------------------------------------------------------------


def test_encode_v3_response_default_pdu_tag_is_response() -> None:
    """encode_v3_response defaults to Response tag 0xA2."""
    raw = encode_v3_response(1, 42, [], b"engine")
    assert 0xA2 in raw


# ---------------------------------------------------------------------------
# encode_v3_response — Report PDU tag (explicit)
# ---------------------------------------------------------------------------


def test_encode_v3_response_pdu_tag_report() -> None:
    """encode_v3_response(pdu_tag=PDU_REPORT) uses tag 0xA8."""
    raw = encode_v3_response(1, 42, [], b"engine", pdu_tag=PDU_REPORT)
    assert 0xA8 in raw


# ---------------------------------------------------------------------------
# auth=True: msgFlags byte 0x05
# ---------------------------------------------------------------------------


def test_encode_v3_getbulk_auth_true_msgflags_0x05() -> None:
    """encode_v3_getbulk(..., auth=True) sets msgFlags to 0x05 (reportable+auth)."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    assert b"\x04\x01\x05" in raw


def test_encode_v3_getbulk_auth_false_msgflags_0x04() -> None:
    """encode_v3_getbulk(..., auth=False) keeps msgFlags 0x04 (regression)."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=False)
    assert b"\x04\x01\x04" in raw


# ---------------------------------------------------------------------------
# auth=True: 12-zero placeholder present in USM params
# ---------------------------------------------------------------------------


def test_encode_v3_getbulk_auth_true_has_placeholder() -> None:
    """encode_v3_getbulk(..., auth=True) embeds 12-zero auth placeholder."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    assert _AUTH_PARAMS_PLACEHOLDER in raw


def test_encode_v3_response_auth_true_has_placeholder() -> None:
    """encode_v3_response(..., auth=True) embeds 12-zero auth placeholder."""
    raw = encode_v3_response(1, 42, [], _ENGINE_ID, auth=True)
    assert _AUTH_PARAMS_PLACEHOLDER in raw


# ---------------------------------------------------------------------------
# authenticate_msg: same length, placeholder replaced, MAC non-zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("proto", [AuthProto.MD5, AuthProto.SHA])
def test_authenticate_msg_same_length(proto: AuthProto) -> None:
    """authenticate_msg returns bytes of same length as input."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    result = authenticate_msg(raw, _kul_for(proto), proto)
    assert len(result) == len(raw)


@pytest.mark.parametrize("proto", [AuthProto.MD5, AuthProto.SHA])
def test_authenticate_msg_mac_slot_nonzero(proto: AuthProto) -> None:
    """authenticate_msg replaces the placeholder with a non-zero MAC."""
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    result = authenticate_msg(raw, _kul_for(proto), proto)
    # placeholder should be gone
    assert _AUTH_PARAMS_PLACEHOLDER not in result


# ---------------------------------------------------------------------------
# verify_auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("proto", [AuthProto.MD5, AuthProto.SHA])
def test_verify_auth_correct_kul_returns_true(proto: AuthProto) -> None:
    """verify_auth returns True for a correctly signed message."""
    kul = _kul_for(proto)
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    signed = authenticate_msg(raw, kul, proto)
    result = decode_v3_message(signed)
    assert isinstance(result, tuple)
    _msg, params = result
    assert verify_auth(signed, params.auth_params, kul, proto) is True


@pytest.mark.parametrize("proto", [AuthProto.MD5, AuthProto.SHA])
def test_verify_auth_wrong_kul_returns_false(proto: AuthProto) -> None:
    """verify_auth returns False when the key is wrong."""
    kul = _kul_for(proto)
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    signed = authenticate_msg(raw, kul, proto)
    wrong_kul = password_to_key(b"wrongpass", _ENGINE_ID, proto)
    result = decode_v3_message(signed)
    assert isinstance(result, tuple)
    _msg, params = result
    assert verify_auth(signed, params.auth_params, wrong_kul, proto) is False


@pytest.mark.parametrize("proto", [AuthProto.MD5, AuthProto.SHA])
def test_verify_auth_tampered_returns_false(proto: AuthProto) -> None:
    """verify_auth returns False when the message is tampered after signing."""
    kul = _kul_for(proto)
    raw = encode_v3_getbulk(1, 42, _OID_1_3_6_1, 7, _ENGINE_ID, 1, 0, b"user", auth=True)
    signed = bytearray(authenticate_msg(raw, kul, proto))
    # Flip the last byte of the engine_id in the message (safe: changes content, not structure)
    # Find the engine_id bytes and flip one byte inside the engine_id value
    engine_id_pos = bytes(signed).index(_ENGINE_ID)
    signed[engine_id_pos] ^= 0x01
    result = decode_v3_message(bytes(signed))
    assert isinstance(result, tuple)
    _msg, params = result
    assert verify_auth(bytes(signed), params.auth_params, kul, proto) is False
