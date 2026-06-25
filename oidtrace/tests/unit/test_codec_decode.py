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
from oidtrace.ber import tlv as ber_tlv
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
    assert "f1" in result.error.lower()


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
    assert "f2" in result.error.lower()


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
# Tolerant-decode leniencies (deliberate; "misbehavior is data")
# ---------------------------------------------------------------------------


def test_trailing_junk_after_outer_sequence_is_accepted() -> None:
    """Trailing bytes after the outer SEQUENCE TLV are silently ignored.

    decode_message reads exactly the outer SEQUENCE (read_tlv discards
    next_i), so extra bytes appended to the datagram do not cause Malformed.
    This is deliberate: on UDP, any framing junk beyond the SEQUENCE is
    irrelevant and we prefer not to discard an otherwise valid message.
    """
    raw = _valid_response()
    result = decode_message(raw + b"\xff\xff\xff")
    assert isinstance(result, Message)


def _build_junk_inside_pdu() -> bytes:
    """Return a valid response re-encoded with extra bytes inside the PDU TLV.

    We reconstruct the packet from scratch so there are no magic offsets:
    parse the valid encoding, then reassemble the PDU body with b'\\xff\\xff'
    appended after the varbind-list TLV, updating all lengths via ber.tlv.
    """
    raw = _valid_response()
    # Peel outer SEQUENCE
    outer_tag, outer_body, _ = read_tlv(raw, 0)
    assert outer_tag == 0x30
    # Peel version, community, PDU
    _, ver_body, ver_end = read_tlv(outer_body, 0)
    _, comm_body, comm_end = read_tlv(outer_body, ver_end)
    pdu_tag, pdu_body, _ = read_tlv(outer_body, comm_end)
    # Peel PDU fields
    j = 0
    _, rid_body, j = read_tlv(pdu_body, j)
    _, f1_body, j = read_tlv(pdu_body, j)
    _, f2_body, j = read_tlv(pdu_body, j)
    _, vblist_body, _ = read_tlv(pdu_body, j)
    # Rebuild PDU body: same fields + junk after varbind list
    new_pdu_body = (
        ber_tlv(0x02, rid_body)
        + ber_tlv(0x02, f1_body)
        + ber_tlv(0x02, f2_body)
        + ber_tlv(0x30, vblist_body)
        + b"\xff\xff"
    )
    new_outer_body = (
        ber_tlv(0x02, ver_body) + ber_tlv(0x04, comm_body) + ber_tlv(pdu_tag, new_pdu_body)
    )
    return ber_tlv(0x30, new_outer_body)


def test_junk_inside_pdu_after_varbind_list_is_accepted() -> None:
    """Extra bytes inside the PDU TLV payload after the varbind-list are ignored.

    decode_message reads the varbind-list with read_tlv (discarding next_j),
    so any trailing bytes inside the PDU body are silently dropped.  This is
    deliberate: strict length enforcement would reject otherwise valid
    responses from devices that pad their PDU bodies.
    """
    result = decode_message(_build_junk_inside_pdu())
    assert isinstance(result, Message)


def _rebuild_with_pdu_tag(new_tag: int) -> bytes:
    """Return a valid response re-encoded with the PDU context tag replaced."""
    raw = _valid_response()
    outer_tag, outer_body, _ = read_tlv(raw, 0)
    assert outer_tag == 0x30
    _, ver_body, ver_end = read_tlv(outer_body, 0)
    _, comm_body, comm_end = read_tlv(outer_body, ver_end)
    _, pdu_body, _ = read_tlv(outer_body, comm_end)
    new_outer_body = ber_tlv(0x02, ver_body) + ber_tlv(0x04, comm_body) + ber_tlv(new_tag, pdu_body)
    return ber_tlv(0x30, new_outer_body)


def test_pdu_tag_0xbf_context_constructed_31_is_accepted() -> None:
    """PDU tag 0xBF (context-constructed, type-number 31) is within 0xA0-0xBF -> Message.

    The check is (pdu_tag & 0xE0) == 0xA0, which accepts any tag in the
    range 0xA0-0xBF.  0xBF is the upper boundary and must be accepted.
    """
    result = decode_message(_rebuild_with_pdu_tag(0xBF))
    assert isinstance(result, Message)


def test_pdu_tag_0xc0_private_class_is_malformed() -> None:
    """PDU tag 0xC0 (private-constructed) is outside 0xA0-0xBF -> Malformed.

    0xC0 sets the class bits to 11 (private), which fails the context-class
    check (0xC0 & 0xE0 == 0xC0, not 0xA0).
    """
    result = decode_message(_rebuild_with_pdu_tag(0xC0))
    assert isinstance(result, Malformed)


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
