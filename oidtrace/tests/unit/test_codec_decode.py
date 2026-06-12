"""Tests for oidtrace.codec — tolerant decode side (Task 5).

Coverage target: codec.py 100% statement + branch.

Per-layer malformation tests locate tag bytes by re-encoding prefixes, never
by magic offsets, so they remain correct if the encoder changes.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from oidtrace.ber import read_tlv
from oidtrace.codec import (
    EXCEPTION_TAGS,
    Malformed,
    Message,
    decode_message,
    encode_getbulk,
    encode_response,
)
from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OID = Oid.from_str("1.3.6.1.2.1.1.1.0")
_OID2 = Oid.from_str("1.3.6.1.2.1.1.3.0")


def _valid_response(
    rid: int = 1042,
    varbinds: list[tuple[Oid, int, bytes]] | None = None,
) -> bytes:
    """Encode a well-formed Response for use as test input."""
    if varbinds is None:
        varbinds = [(_OID, 0x43, b"\x00\x00\x00\x01")]  # TimeTicks 4-byte
    return encode_response(rid, varbinds)


def _tlv_header_size(buf: bytes, offset: int) -> int:
    """Return the byte-size of the TLV header (tag + length fields) at offset."""
    length_byte = buf[offset + 1]
    if length_byte & 0x80:
        return 2 + (length_byte & 0x7F)
    return 2


def _find_pdu_body_start(raw_bytes: bytes) -> int:
    """Locate the first byte of the PDU body in a well-formed SNMP message."""
    outer_hdr = _tlv_header_size(raw_bytes, 0)
    _, _, ver_end = read_tlv(raw_bytes, outer_hdr)
    _, _, comm_end = read_tlv(raw_bytes, ver_end)
    return comm_end + _tlv_header_size(raw_bytes, comm_end)


# ---------------------------------------------------------------------------
# Well-formed round-trip
# ---------------------------------------------------------------------------


def test_decode_response_returns_message() -> None:
    raw = _valid_response()
    result = decode_message(raw)
    assert isinstance(result, Message)


def test_decode_response_pdu_tag_is_0xa2() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.pdu_tag == 0xA2


def test_decode_response_request_id_preserved() -> None:
    raw = _valid_response(rid=1042)
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.request_id == 1042


def test_decode_response_rid_1_preserved() -> None:
    raw = _valid_response(rid=1)
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.request_id == 1


def test_decode_response_f1_is_error_status_zero() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.f1 == 0


def test_decode_response_f2_is_error_index_zero() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.f2 == 0


def test_decode_response_varbind_count() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert len(msg.varbinds) == 1


def test_decode_response_varbind_oid() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.varbinds[0].oid == _OID


def test_decode_response_varbind_timeticks_tag() -> None:
    """TimeTicks tag 0x43 -> vtype 'TimeTicks'."""
    raw = _valid_response(varbinds=[(_OID, 0x43, b"\x00\x00\x00\x01")])
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.varbinds[0].tag == 0x43
    assert msg.varbinds[0].vtype == "TimeTicks"


def test_decode_response_varbind_timeticks_vlen_4() -> None:
    """TimeTicks 4-byte value -> vlen == 4."""
    raw = _valid_response(varbinds=[(_OID, 0x43, b"\x00\x00\x00\x01")])
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.varbinds[0].vlen == 4


def test_decode_response_raw_equals_input() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.raw == raw


def test_decode_response_varbinds_is_tuple() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert isinstance(msg.varbinds, tuple)


def test_decode_response_two_varbinds() -> None:
    raw = encode_response(
        7,
        [(_OID, 0x43, b"\x00\x00\x00\x01"), (_OID2, 0x02, b"\x05")],
    )
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert len(msg.varbinds) == 2
    assert msg.varbinds[0].oid == _OID
    assert msg.varbinds[1].oid == _OID2


# ---------------------------------------------------------------------------
# vtype vocabulary (§ 5 of trace-format.md)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "expected_vtype"),
    [
        (0x02, "Integer"),
        (0x04, "OctetString"),
        (0x05, "Null"),
        (0x06, "ObjectIdentifier"),
        (0x40, "IpAddress"),
        (0x41, "Counter32"),
        (0x42, "Gauge32"),
        (0x43, "TimeTicks"),
        (0x44, "Opaque"),
        (0x46, "Counter64"),
        (0x80, "NoSuchObject"),
        (0x81, "NoSuchInstance"),
        (0x82, "EndOfMibView"),
    ],
)
def test_varbind_vtype_known_tags(tag: int, expected_vtype: str) -> None:
    raw = encode_response(1, [(_OID, tag, b"\x00")])
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.varbinds[0].vtype == expected_vtype


def test_varbind_unknown_tag_format() -> None:
    """Unknown tag 0x99 -> 'tag:0x99'."""
    raw = encode_response(1, [(_OID, 0x99, b"\x00")])
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.varbinds[0].vtype == "tag:0x99"


def test_varbind_unknown_tag_0x03_format() -> None:
    """Unknown tag 0x03 -> 'tag:0x03'."""
    raw = encode_response(1, [(_OID, 0x03, b"\x00")])
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.varbinds[0].vtype == "tag:0x03"


# ---------------------------------------------------------------------------
# EXCEPTION_TAGS constant
# ---------------------------------------------------------------------------


def test_exception_tags_contains_no_such_object() -> None:
    assert 0x80 in EXCEPTION_TAGS


def test_exception_tags_contains_no_such_instance() -> None:
    assert 0x81 in EXCEPTION_TAGS


def test_exception_tags_contains_end_of_mib_view() -> None:
    assert 0x82 in EXCEPTION_TAGS


def test_exception_tags_is_frozenset() -> None:
    assert isinstance(EXCEPTION_TAGS, frozenset)


def test_exception_tags_length() -> None:
    assert len(EXCEPTION_TAGS) == 3


# ---------------------------------------------------------------------------
# GetBulk request decodes (pdu_tag 0xA5, f1/f2 = non-reps/max-reps)
# ---------------------------------------------------------------------------


def test_decode_getbulk_request_pdu_tag() -> None:
    raw = encode_getbulk(55, _OID, non_repeaters=2, max_repetitions=7)
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.pdu_tag == 0xA5


def test_decode_getbulk_request_id() -> None:
    raw = encode_getbulk(55, _OID, non_repeaters=2, max_repetitions=7)
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.request_id == 55


def test_decode_getbulk_f1_is_non_repeaters() -> None:
    raw = encode_getbulk(55, _OID, non_repeaters=2, max_repetitions=7)
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.f1 == 2


def test_decode_getbulk_f2_is_max_repetitions() -> None:
    raw = encode_getbulk(55, _OID, non_repeaters=2, max_repetitions=7)
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    assert msg.f2 == 7


# ---------------------------------------------------------------------------
# Garbage inputs -> Malformed (never raises)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"\x30\x82\x01\x00" + b"\x00" * 10,  # overlong-length claim
        b"GET / HTTP/1.1\r\nHost: localhost\r\n",  # ASCII text
        b"\x00" * 4,
        b"\x30\x03\x01\x02",  # valid header, truncated body
    ],
    ids=["empty", "single-ff", "overlong-length", "ascii-text", "null-bytes", "truncated-body"],
)
def test_garbage_returns_malformed(raw: bytes) -> None:
    result = decode_message(raw)
    assert isinstance(result, Malformed)


def test_malformed_carries_exact_raw() -> None:
    raw = b"\xff"
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.raw == raw


def test_malformed_has_nonempty_error() -> None:
    raw = b"\xff"
    result = decode_message(raw)
    assert isinstance(result, Malformed)
    assert result.error != ""


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"\x30\x82\x01\x00" + b"\x00" * 10,
        b"GET / HTTP/1.1\r\nHost: localhost\r\n",
    ],
)
def test_garbage_never_raises(raw: bytes) -> None:
    """decode_message must never raise -- all errors become Malformed."""
    decode_message(raw)


# ---------------------------------------------------------------------------
# Varbind / Message are frozen dataclasses
# ---------------------------------------------------------------------------


def test_varbind_is_frozen() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    vb = msg.varbinds[0]
    with pytest.raises((AttributeError, TypeError)):
        vb.tag = 0x99  # type: ignore[misc]


def test_message_is_frozen() -> None:
    raw = _valid_response()
    msg = decode_message(raw)
    assert isinstance(msg, Message)
    with pytest.raises((AttributeError, TypeError)):
        msg.request_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Per-layer malformations -- every tag-check branch covered
#
# Strategy: build a valid packet with encode_response, then locate the
# specific byte by re-encoding the prefix up to that layer, and flip it.
# ---------------------------------------------------------------------------


def test_malformed_outer_seq_tag_wrong() -> None:
    """Outer SEQUENCE tag (0x30) is wrong -> Malformed with distinctive error."""
    raw = bytearray(_valid_response())
    raw[0] = 0x31  # flip outer SEQ tag
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "outer" in result.error.lower() or "sequence" in result.error.lower()


def test_malformed_version_tag_wrong() -> None:
    """Version INTEGER tag (0x02) inside outer SEQ is wrong -> Malformed."""
    raw_bytes = _valid_response()
    outer_hdr = _tlv_header_size(raw_bytes, 0)
    raw = bytearray(raw_bytes)
    raw[outer_hdr] = 0x04  # flip version tag: 0x02 INTEGER -> 0x04 OCTET STRING
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "version" in result.error.lower()


def test_malformed_community_tag_wrong() -> None:
    """Community OCTET STRING tag (0x04) is wrong -> Malformed."""
    raw_bytes = _valid_response()
    outer_hdr = _tlv_header_size(raw_bytes, 0)
    _, _, ver_end = read_tlv(raw_bytes, outer_hdr)
    raw = bytearray(raw_bytes)
    raw[ver_end] = 0x02  # flip community tag: 0x04 OCTET STRING -> 0x02 INTEGER
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "community" in result.error.lower()


def test_malformed_pdu_tag_not_context_constructed() -> None:
    """PDU tag must be context-constructed (0xA0-0xBF); wrong tag -> Malformed."""
    raw_bytes = _valid_response()
    outer_hdr = _tlv_header_size(raw_bytes, 0)
    _, _, ver_end = read_tlv(raw_bytes, outer_hdr)
    _, _, comm_end = read_tlv(raw_bytes, ver_end)
    raw = bytearray(raw_bytes)
    raw[comm_end] = 0x30  # flip PDU tag: 0xA2 -> 0x30 (plain SEQUENCE)
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "pdu" in result.error.lower()


def test_malformed_rid_tag_wrong() -> None:
    """Request-ID INTEGER tag wrong inside PDU -> Malformed."""
    raw_bytes = _valid_response()
    pdu_start = _find_pdu_body_start(raw_bytes)
    raw = bytearray(raw_bytes)
    raw[pdu_start] = 0x04  # flip request-id tag: 0x02 INTEGER -> 0x04
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "request" in result.error.lower() or "rid" in result.error.lower()


def test_malformed_f1_tag_wrong() -> None:
    """f1 INTEGER tag wrong inside PDU -> Malformed."""
    raw_bytes = _valid_response()
    pdu_start = _find_pdu_body_start(raw_bytes)
    _, _, rid_end = read_tlv(raw_bytes, pdu_start)
    raw = bytearray(raw_bytes)
    raw[rid_end] = 0x04  # flip f1 INTEGER tag
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "f1" in result.error.lower() or "error" in result.error.lower()


def test_malformed_f2_tag_wrong() -> None:
    """f2 INTEGER tag wrong inside PDU -> Malformed."""
    raw_bytes = _valid_response()
    pdu_start = _find_pdu_body_start(raw_bytes)
    _, _, rid_end = read_tlv(raw_bytes, pdu_start)
    _, _, f1_end = read_tlv(raw_bytes, rid_end)
    raw = bytearray(raw_bytes)
    raw[f1_end] = 0x04  # flip f2 INTEGER tag
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "f2" in result.error.lower() or "error" in result.error.lower()


def test_malformed_vblist_tag_wrong() -> None:
    """Varbind-list SEQUENCE tag wrong -> Malformed."""
    raw_bytes = _valid_response()
    pdu_start = _find_pdu_body_start(raw_bytes)
    _, _, rid_end = read_tlv(raw_bytes, pdu_start)
    _, _, f1_end = read_tlv(raw_bytes, rid_end)
    _, _, f2_end = read_tlv(raw_bytes, f1_end)
    raw = bytearray(raw_bytes)
    raw[f2_end] = 0x31  # flip 0x30 SEQUENCE tag
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "varbind" in result.error.lower()


def test_malformed_varbind_seq_tag_wrong() -> None:
    """Individual varbind SEQUENCE tag wrong -> Malformed."""
    raw_bytes = _valid_response()
    pdu_start = _find_pdu_body_start(raw_bytes)
    _, _, rid_end = read_tlv(raw_bytes, pdu_start)
    _, _, f1_end = read_tlv(raw_bytes, rid_end)
    _, _, f2_end = read_tlv(raw_bytes, f1_end)
    vblist_body_start = f2_end + _tlv_header_size(raw_bytes, f2_end)
    raw = bytearray(raw_bytes)
    raw[vblist_body_start] = 0x31  # flip first varbind SEQ tag
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "varbind" in result.error.lower()


def test_malformed_oid_tag_wrong_in_varbind() -> None:
    """OID tag (0x06) wrong inside varbind -> Malformed."""
    raw_bytes = _valid_response()
    pdu_start = _find_pdu_body_start(raw_bytes)
    _, _, rid_end = read_tlv(raw_bytes, pdu_start)
    _, _, f1_end = read_tlv(raw_bytes, rid_end)
    _, _, f2_end = read_tlv(raw_bytes, f1_end)
    vblist_body_start = f2_end + _tlv_header_size(raw_bytes, f2_end)
    vb_body_start = vblist_body_start + _tlv_header_size(raw_bytes, vblist_body_start)
    raw = bytearray(raw_bytes)
    raw[vb_body_start] = 0x04  # flip OID tag 0x06 to 0x04
    result = decode_message(bytes(raw))
    assert isinstance(result, Malformed)
    assert "oid" in result.error.lower()


# ---------------------------------------------------------------------------
# Hypothesis fuzz -- never raises
# ---------------------------------------------------------------------------


@given(st.binary(max_size=200))
@settings(max_examples=500)
def test_fuzz_arbitrary_bytes_never_raises(raw: bytes) -> None:
    """decode_message must never raise for any input."""
    result = decode_message(raw)
    assert isinstance(result, (Message, Malformed))


@given(st.binary(max_size=200))
@settings(max_examples=500)
def test_fuzz_arbitrary_bytes_malformed_has_nonempty_error(raw: bytes) -> None:
    """Any Malformed result must carry a non-empty error and preserve raw."""
    result = decode_message(raw)
    if isinstance(result, Malformed):
        assert result.error != ""
        assert result.raw == raw


@given(st.integers(min_value=0, max_value=2**16))
@settings(max_examples=300)
def test_fuzz_single_byte_mutations_of_valid_packet(bit_flip_pos: int) -> None:
    """Single-byte mutations of a valid encode_response packet never raise."""
    raw = bytearray(_valid_response())
    if bit_flip_pos < len(raw):
        raw[bit_flip_pos] ^= 0xFF
    result = decode_message(bytes(raw))
    assert isinstance(result, (Message, Malformed))
