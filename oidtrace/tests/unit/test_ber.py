"""Tests for oidtrace.ber — BER encode/decode primitives.

Contract coverage:
  - tlv: exact header bytes for short-form (len < 128) and long-form (len >= 128)
  - round-trips: tlv + read_tlv, with next_i == len(buf)
  - encode_int / decode_int: round-trip over a set of non-negative SNMP integers
  - encode_oid / decode_oid: round-trips including multi-byte arcs
  - read_tlv ValueError cases: truncated header, truncated long-form length bytes,
    zero length-of-length (indefinite form), body overrun
  - decode_oid ValueError cases: empty body, trailing continuation bit
"""

from __future__ import annotations

import pytest

from oidtrace.ber import decode_int, decode_oid, encode_int, encode_oid, read_tlv, tlv
from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# tlv — exact header bytes
# ---------------------------------------------------------------------------


def test_tlv_short_form_header() -> None:
    """Payload length 10: tag byte 0x04, then 0x0a (single byte, short form)."""
    buf = tlv(0x04, b"x" * 10)
    assert buf[:2] == bytes([0x04, 0x0A])
    assert len(buf) == 12


def test_tlv_long_form_header() -> None:
    """Payload length 300: 0x04 0x82 0x01 0x2c (two-byte long form)."""
    buf = tlv(0x04, b"x" * 300)
    assert buf[:4] == bytes([0x04, 0x82, 0x01, 0x2C])
    assert len(buf) == 304


def test_tlv_short_form_boundary_127() -> None:
    """127 bytes: still short form (0x7f)."""
    buf = tlv(0x04, b"x" * 127)
    assert buf[1] == 0x7F


def test_tlv_long_form_boundary_128() -> None:
    """128 bytes: first long-form case (0x81 0x80)."""
    buf = tlv(0x04, b"x" * 128)
    assert buf[1] == 0x81
    assert buf[2] == 0x80


def test_tlv_empty_payload() -> None:
    buf = tlv(0x05, b"")
    assert buf == bytes([0x05, 0x00])


# ---------------------------------------------------------------------------
# read_tlv — round-trips
# ---------------------------------------------------------------------------


def test_read_tlv_roundtrip_short_form() -> None:
    """Round-trip for payload length 10; next_i must equal len(buf)."""
    payload = b"a" * 10
    buf = tlv(0x04, payload)
    tag, body, next_i = read_tlv(buf, 0)
    assert tag == 0x04
    assert body == payload
    assert next_i == len(buf)


def test_read_tlv_roundtrip_long_form() -> None:
    """Round-trip for payload length 300; next_i must equal len(buf)."""
    payload = b"b" * 300
    buf = tlv(0x04, payload)
    tag, body, next_i = read_tlv(buf, 0)
    assert tag == 0x04
    assert body == payload
    assert next_i == len(buf)


def test_read_tlv_payload_is_slice() -> None:
    """body must be bytes (a slice), not indices."""
    payload = b"hello"
    buf = tlv(0x02, payload)
    _, body, _ = read_tlv(buf, 0)
    assert isinstance(body, bytes)
    assert body == payload


def test_read_tlv_nonzero_offset() -> None:
    """read_tlv must handle a nonzero starting offset (e.g. nested TLVs)."""
    prefix = bytes([0x01, 0x02])
    payload = b"world"
    buf = prefix + tlv(0x04, payload)
    tag, body, next_i = read_tlv(buf, 2)
    assert tag == 0x04
    assert body == payload
    assert next_i == len(buf)


# ---------------------------------------------------------------------------
# read_tlv — ValueError cases
# ---------------------------------------------------------------------------


def test_read_tlv_error_truncated_header_zero_bytes() -> None:
    """Zero bytes at offset: cannot read tag."""
    with pytest.raises(ValueError):
        read_tlv(b"", 0)


def test_read_tlv_error_truncated_header_one_byte() -> None:
    """One byte (tag only): cannot read length."""
    with pytest.raises(ValueError):
        read_tlv(bytes([0x04]), 0)


def test_read_tlv_error_zero_length_of_length_indefinite() -> None:
    """0x80 as length byte means indefinite form — must raise ValueError."""
    buf = bytes([0x04, 0x80]) + b"somedata"
    with pytest.raises(ValueError):
        read_tlv(buf, 0)


def test_read_tlv_error_truncated_long_form_length_bytes() -> None:
    """Long-form says 2 length bytes, but buffer ends after 1 — ValueError."""
    # 0x82 means 2-byte length follows, but we only supply 1.
    buf = bytes([0x04, 0x82, 0x01])
    with pytest.raises(ValueError):
        read_tlv(buf, 0)


def test_read_tlv_error_body_overrun() -> None:
    """Length field claims more bytes than are present — ValueError."""
    # Tag 0x04, length 10, but only 5 bytes of body.
    buf = bytes([0x04, 0x0A]) + b"x" * 5
    with pytest.raises(ValueError):
        read_tlv(buf, 0)


# ---------------------------------------------------------------------------
# encode_int / decode_int — round-trips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("v", [0, 1, 127, 128, 255, 1042, 2**31 - 1])
def test_encode_decode_int_roundtrip(v: int) -> None:
    """Integer round-trip: encode then decode must recover the original value."""
    buf = encode_int(v)
    _, body, _ = read_tlv(buf, 0)
    assert decode_int(body) == v


def test_encode_int_128_needs_leading_zero() -> None:
    """128 (0x80) must be encoded with a leading 0x00 byte (two's complement)."""
    buf = encode_int(128)
    _, body, _ = read_tlv(buf, 0)
    assert body[0] == 0x00
    assert len(body) == 2


def test_encode_int_255_needs_leading_zero() -> None:
    """255 (0xFF) must be encoded with a leading 0x00 byte (two's complement)."""
    buf = encode_int(255)
    _, body, _ = read_tlv(buf, 0)
    assert body[0] == 0x00
    assert len(body) == 2


def test_encode_int_uses_tag_0x02() -> None:
    buf = encode_int(1)
    assert buf[0] == 0x02


def test_encode_int_custom_tag() -> None:
    buf = encode_int(1, tag=0x41)
    assert buf[0] == 0x41


def test_encode_int_zero_is_one_byte() -> None:
    buf = encode_int(0)
    _, body, _ = read_tlv(buf, 0)
    assert body == b"\x00"


def test_encode_int_127_is_one_byte() -> None:
    buf = encode_int(127)
    _, body, _ = read_tlv(buf, 0)
    assert body == b"\x7f"


def test_decode_int_signed_default() -> None:
    """decode_int is signed=True by default; a body of 0xFF decodes as -1."""
    assert decode_int(b"\xff") == -1


def test_decode_int_unsigned() -> None:
    """With signed=False, body 0xFF decodes as 255."""
    assert decode_int(b"\xff", signed=False) == 255


# ---------------------------------------------------------------------------
# encode_oid / decode_oid — round-trips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dotted",
    [
        "1.3.6.1",
        "1.3.6.1.2.1.1.1.0",
        "0.0",
        "2.5.4.3",
    ],
)
def test_encode_decode_oid_roundtrip_basic(dotted: str) -> None:
    oid = Oid.from_str(dotted)
    buf = encode_oid(oid)
    # encode_oid returns a full TLV (tag 0x06)
    _, body, _ = read_tlv(buf, 0)
    assert decode_oid(body) == oid


def test_encode_oid_tag_is_0x06() -> None:
    buf = encode_oid(Oid.from_str("1.3.6.1"))
    assert buf[0] == 0x06


def test_encode_decode_oid_multi_byte_arc_2636() -> None:
    """Arc 2636 requires multi-byte base-128 encoding (> 127)."""
    oid = Oid.from_str("1.3.6.1.4.1.2636.1")
    buf = encode_oid(oid)
    _, body, _ = read_tlv(buf, 0)
    assert decode_oid(body) == oid


def test_encode_decode_oid_large_instance_123456() -> None:
    """Instance arc 123456 (> 2**14) tests three-byte base-128 encoding."""
    oid = Oid.from_str("1.3.6.1.2.1.2.2.1.1.123456")
    buf = encode_oid(oid)
    _, body, _ = read_tlv(buf, 0)
    assert decode_oid(body) == oid


def test_encode_oid_first_two_arcs_packed() -> None:
    """First two arcs are packed as 40*a0 + a1 in the first byte of the body."""
    # 1.3 -> 40*1 + 3 = 43 = 0x2B
    oid = Oid.from_str("1.3.6.1")
    buf = encode_oid(oid)
    _, body, _ = read_tlv(buf, 0)
    assert body[0] == 40 * 1 + 3


# ---------------------------------------------------------------------------
# decode_oid — ValueError cases
# ---------------------------------------------------------------------------


def test_decode_oid_error_empty_body() -> None:
    """An empty body must raise ValueError."""
    with pytest.raises(ValueError):
        decode_oid(b"")


def test_decode_oid_error_trailing_continuation_bit() -> None:
    """A body ending with a byte that has the continuation bit set must raise ValueError."""
    # 0x81 has the high bit set — continuation bit set at end of buffer.
    with pytest.raises(ValueError):
        decode_oid(bytes([0x2B, 0x81]))
