"""Tests for oidtrace.codec — decode side (Task 5).

Covers decode_message: happy-path round-trips and tolerant handling of garbage.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from oidtrace.ber import encode_oid, tlv
from oidtrace.codec import (
    Malformed,
    Message,
    Varbind,
    decode_message,
    encode_getbulk,
    encode_response,
)
from oidtrace.oid import Oid

_OID_SYSUPTIME = Oid.from_str("1.3.6.1.2.1.1.3.0")

# A fixed valid packet used by mutation-based fuzz tests.
_VALID_PACKET = encode_response(
    42,
    [(_OID_SYSUPTIME, 0x43, b"\x00\x01\x02\x03")],
)


# ---------------------------------------------------------------------------
# Well-formed round-trip


async def test_response_round_trip_timeticks() -> None:
    raw = encode_response(
        1042,
        [(_OID_SYSUPTIME, 0x43, (492711442).to_bytes(4, "big"))],
    )
    result = decode_message(raw)
    assert isinstance(result, Message)
    assert result.request_id == 1042
    assert len(result.varbinds) == 1
    vb = result.varbinds[0]
    assert isinstance(vb, Varbind)
    assert vb.oid == _OID_SYSUPTIME
    assert vb.vtype == "TimeTicks"
    assert vb.vlen == 4


async def test_request_id_preserved() -> None:
    raw = encode_response(1, [(_OID_SYSUPTIME, 0x43, b"\x00")])
    result = decode_message(raw)
    assert isinstance(result, Message)
    assert result.request_id == 1


async def test_unknown_tag_produces_tag_hex_vtype() -> None:
    raw = encode_response(7, [(_OID_SYSUPTIME, 0x99, b"\xab\xcd")])
    result = decode_message(raw)
    assert isinstance(result, Message)
    assert result.varbinds[0].vtype == "tag:0x99"


# ---------------------------------------------------------------------------
# Garbage inputs → Malformed, never raises


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"\x30\x82\xff\xff\x00\x00",
        b"hello world",
    ],
)
async def test_garbage_returns_malformed(raw: bytes) -> None:
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert result.error  # non-empty error string


# ---------------------------------------------------------------------------
# GetBulk request decodes (pdu_tag 0xA5, f1=non_repeaters, f2=max_repetitions)


async def test_getbulk_request_decodes() -> None:
    raw = encode_getbulk(99, _OID_SYSUPTIME, non_repeaters=0, max_repetitions=10)
    result = decode_message(raw)
    assert isinstance(result, Message)
    assert result.pdu_tag == 0xA5
    assert result.request_id == 99
    assert result.f1 == 0  # non_repeaters
    assert result.f2 == 10  # max_repetitions


# ---------------------------------------------------------------------------
# Per-branch malformation tests (lines 115, 121, 127, 132, 138, 143, 148, 154, 175, 180)
#
# Each packet is valid up to the layer under test, then the specific tag byte
# is replaced with a wrong value so the exact branch fires.


def _make_outer_seq(inner: bytes, wrong_tag: int = 0x30) -> bytes:
    """Wrap inner bytes in a top-level TLV with the given tag."""
    return tlv(wrong_tag, inner)


def _make_snmp_inner(
    *,
    version_tag: int = 0x02,
    community_tag: int = 0x04,
    pdu_tag: int = 0xA2,
    rid_tag: int = 0x02,
    f1_tag: int = 0x02,
    f2_tag: int = 0x02,
    vlist_tag: int = 0x30,
    vb_tag: int = 0x30,
    oid_tag: int = 0x06,
) -> bytes:
    """Build the inner body of an SNMP SEQUENCE with per-field tag overrides."""
    oid_body = encode_oid(_OID_SYSUPTIME)[2:]  # strip the 0x06 + length prefix
    varbind = tlv(vb_tag, tlv(oid_tag, oid_body) + tlv(0x43, b"\x00"))
    vlist = tlv(vlist_tag, varbind)
    pdu_body = tlv(rid_tag, b"\x01") + tlv(f1_tag, b"\x00") + tlv(f2_tag, b"\x00") + vlist
    pdu = tlv(pdu_tag, pdu_body)
    version = tlv(version_tag, b"\x01")
    community = tlv(community_tag, b"public")
    return version + community + pdu


async def test_malformed_outer_not_sequence() -> None:
    # Line 115: outer tag is not 0x30
    inner = _make_snmp_inner()
    raw = _make_outer_seq(inner, wrong_tag=0x10)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "outer SEQUENCE" in result.error


async def test_malformed_version_not_integer() -> None:
    # Line 121: version tag is not 0x02
    inner = _make_snmp_inner(version_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "version INTEGER" in result.error


async def test_malformed_community_not_octet_string() -> None:
    # Line 127: community tag is not 0x04
    inner = _make_snmp_inner(community_tag=0x02)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "community OCTET STRING" in result.error


async def test_malformed_pdu_not_context_tag() -> None:
    # Line 132: PDU tag has no bits in common with 0xA0, so `tag & 0xA0 == 0`.
    # Note: 0x30 & 0xA0 == 0x20 != 0, so 0x30 passes the check; use 0x02 instead.
    inner = _make_snmp_inner(pdu_tag=0x02)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "PDU context tag" in result.error


async def test_malformed_request_id_not_integer() -> None:
    # Line 138: request-id tag is not 0x02
    inner = _make_snmp_inner(rid_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "request-id INTEGER" in result.error


async def test_malformed_f1_not_integer() -> None:
    # Line 143: f1 tag is not 0x02
    inner = _make_snmp_inner(f1_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "f1 INTEGER" in result.error


async def test_malformed_f2_not_integer() -> None:
    # Line 148: f2 tag is not 0x02
    inner = _make_snmp_inner(f2_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "f2 INTEGER" in result.error


async def test_malformed_varbind_list_not_sequence() -> None:
    # Line 154: varbind-list tag is not 0x30
    inner = _make_snmp_inner(vlist_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "varbind-list SEQUENCE" in result.error


async def test_malformed_varbind_not_sequence() -> None:
    # Line 175: individual varbind tag is not 0x30
    inner = _make_snmp_inner(vb_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "varbind SEQUENCE" in result.error


async def test_malformed_oid_not_oid_tag() -> None:
    # Line 180: OID tag inside varbind is not 0x06
    inner = _make_snmp_inner(oid_tag=0x04)
    raw = tlv(0x30, inner)
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw
    assert "OID tag" in result.error


# ---------------------------------------------------------------------------
# Hypothesis fuzz tests


@given(st.binary(max_size=200))
def test_decode_never_raises_on_arbitrary_bytes(data: bytes) -> None:
    """decode_message must return Message or Malformed — never raise."""
    result = decode_message(data)
    assert isinstance(result, Message | Malformed)


@given(
    index=st.integers(min_value=0),
    byte=st.integers(min_value=0, max_value=255),
)
def test_decode_never_raises_on_mutated_valid_packet(index: int, byte: int) -> None:
    """Flipping any single byte of a valid packet must not raise."""
    mutated = bytearray(_VALID_PACKET)
    mutated[index % len(mutated)] = byte
    result = decode_message(bytes(mutated))
    assert isinstance(result, Message | Malformed)
