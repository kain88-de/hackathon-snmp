"""Tests for oidtrace.ber — minimal BER primitives."""

import pytest

from oidtrace.ber import decode_int, decode_oid, encode_int, encode_oid, read_tlv, tlv
from oidtrace.oid import Oid

# ------------------------------------------------------------------ tlv / read_tlv


def test_tlv_short_form_header() -> None:
    payload = bytes(10)
    result = tlv(0x04, payload)
    assert result[:2] == bytes([0x04, 0x0A])
    assert result[2:] == payload


def test_tlv_long_form_header() -> None:
    payload = bytes(300)
    result = tlv(0x04, payload)
    # 300 = 0x012C → two length bytes → 0x82 0x01 0x2C
    assert result[:4] == bytes([0x04, 0x82, 0x01, 0x2C])
    assert result[4:] == payload


def test_read_tlv_short_form_roundtrip() -> None:
    payload = bytes(10)
    buf = tlv(0x04, payload)
    tag, body, next_i = read_tlv(buf, 0)
    assert tag == 0x04
    assert body == payload
    assert next_i == len(buf)


def test_read_tlv_long_form_roundtrip() -> None:
    payload = bytes(300)
    buf = tlv(0x04, payload)
    tag, body, next_i = read_tlv(buf, 0)
    assert tag == 0x04
    assert body == payload
    assert next_i == len(buf)


# ------------------------------------------------------------------ encode_int / decode_int


@pytest.mark.parametrize("v", [0, 1, 127, 128, 255, 1042, 2**31 - 1])
def test_int_roundtrip(v: int) -> None:
    buf = encode_int(v)
    tag, body, next_i = read_tlv(buf, 0)
    assert tag == 0x02
    assert next_i == len(buf)
    assert decode_int(body) == v


# ------------------------------------------------------------------ encode_oid / decode_oid


@pytest.mark.parametrize(
    "oid_str",
    [
        "1.3.6.1",
        "1.3.6.1.4.1.2636.3.60.1",
        "1.3.6.1.2.1.2.2.1.10.123456",
    ],
)
def test_oid_roundtrip(oid_str: str) -> None:
    oid = Oid.from_str(oid_str)
    buf = encode_oid(oid)
    tag, body, next_i = read_tlv(buf, 0)
    assert tag == 0x06
    assert next_i == len(buf)
    assert decode_oid(body) == oid


def test_oid_roundtrip_str() -> None:
    oid_str = "1.3.6.1.2.1"
    oid = Oid.from_str(oid_str)
    buf = encode_oid(oid)
    _, body, _ = read_tlv(buf, 0)
    assert str(decode_oid(body)) == oid_str


# ------------------------------------------------------------------ read_tlv error cases


def test_read_tlv_truncated_header() -> None:
    with pytest.raises(ValueError):
        read_tlv(b"\x04", 0)


def test_read_tlv_truncated_body() -> None:
    payload = bytes(10)
    buf = tlv(0x04, payload)
    # chop the last byte off
    with pytest.raises(ValueError):
        read_tlv(buf[:-1], 0)


def test_read_tlv_bad_long_form_zero_length_of_length() -> None:
    # 0x80 means "indefinite form" in BER, which we reject
    bad = bytes([0x04, 0x80])
    with pytest.raises(ValueError):
        read_tlv(bad, 0)


def test_read_tlv_long_form_length_bytes_truncated() -> None:
    # says 2 length bytes but only 1 follows
    bad = bytes([0x04, 0x82, 0x01])
    with pytest.raises(ValueError):
        read_tlv(bad, 0)


# ------------------------------------------------------------------ decode_oid error cases


def test_decode_oid_empty_body() -> None:
    with pytest.raises(ValueError):
        decode_oid(b"")


def test_decode_oid_truncated_multibyte_arc() -> None:
    # 0x2b = first two arcs (1.3), then 0x81 has continuation bit set but nothing follows
    with pytest.raises(ValueError):
        decode_oid(b"\x2b\x81")
