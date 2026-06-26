"""Tests for SNMPv3 encoding — encode_v3_discovery, encode_v3_getbulk, encode_v3_response, V3Params.

Wire format constraints:
  - discovery probe: 64 bytes exactly (matches live snmpwalk capture)
  - All wire assertions verify BER structure matches SNMPv3 RFC 3412/3414
"""

from __future__ import annotations

import pytest

from oidtrace.ber import encode_oid
from oidtrace.codec import (
    PDU_GET,
    PDU_REPORT,
    V3Params,
    encode_v3_discovery,
    encode_v3_getbulk,
    encode_v3_response,
)
from oidtrace.oid import Oid

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
