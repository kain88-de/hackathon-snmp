"""Property-based fuzz tests for SNMPv3 codec (Task 4).

Tests:
  - decode_v3_message never raises on arbitrary bytes
  - encode_v3_discovery -> decode_v3_message roundtrips msg_id and request_id
  - encode_v3_getbulk -> decode_v3_message roundtrips all six fields
  - encode_v3_response -> decode_v3_message roundtrips request_id, engine_id, msg_id
  - Bit-flip mutations of a discovery packet never raise
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from oidtrace.codec import (
    Malformed,
    decode_v3_message,
    encode_v3_discovery,
    encode_v3_getbulk,
    encode_v3_response,
)
from oidtrace.oid import Oid

_INT = st.integers(min_value=0, max_value=2**31 - 1)
_BYTES = st.binary(min_size=0, max_size=32)

# A fixed valid OID used for getbulk roundtrips.
_OID = Oid.from_str("1.3.6.1.2.1.1.1.0")


# ---------------------------------------------------------------------------
# Never raises on arbitrary bytes
# ---------------------------------------------------------------------------


@given(st.binary(max_size=200))
@settings(max_examples=500)
def test_decode_v3_never_raises(raw: bytes) -> None:
    """decode_v3_message must never raise for any input."""
    result = decode_v3_message(raw)
    assert isinstance(result, (tuple, Malformed))


# ---------------------------------------------------------------------------
# Discovery roundtrip
# ---------------------------------------------------------------------------


@given(msg_id=_INT, req_id=_INT)
@settings(max_examples=300)
def test_discovery_roundtrip(msg_id: int, req_id: int) -> None:
    """encode_v3_discovery -> decode_v3_message roundtrips msg_id and request_id."""
    raw = encode_v3_discovery(msg_id, req_id)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, params = result
    assert params.msg_id == msg_id
    assert msg.request_id == req_id


# ---------------------------------------------------------------------------
# GetBulk roundtrip
# ---------------------------------------------------------------------------


@given(
    msg_id=_INT,
    req_id=_INT,
    max_reps=_INT,
    engine_id=_BYTES,
    engine_boots=_INT,
    engine_time=_INT,
)
@settings(max_examples=300)
def test_getbulk_roundtrip(  # noqa: PLR0913
    msg_id: int,
    req_id: int,
    max_reps: int,
    engine_id: bytes,
    engine_boots: int,
    engine_time: int,
) -> None:
    """encode_v3_getbulk -> decode_v3_message roundtrips all six fields."""
    raw = encode_v3_getbulk(
        msg_id, req_id, _OID, max_reps, engine_id, engine_boots, engine_time, b"user"
    )
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, params = result
    assert params.msg_id == msg_id
    assert msg.request_id == req_id
    assert params.engine_id == engine_id
    assert params.engine_boots == engine_boots
    assert params.engine_time == engine_time
    assert msg.f2 == max_reps


# ---------------------------------------------------------------------------
# Response roundtrip
# ---------------------------------------------------------------------------


@given(msg_id=_INT, req_id=_INT, engine_id=_BYTES)
@settings(max_examples=300)
def test_response_roundtrip(msg_id: int, req_id: int, engine_id: bytes) -> None:
    """encode_v3_response -> decode_v3_message roundtrips request_id, engine_id, msg_id."""
    raw = encode_v3_response(msg_id, req_id, [], engine_id)
    result = decode_v3_message(raw)
    assert isinstance(result, tuple)
    msg, params = result
    assert msg.request_id == req_id
    assert params.engine_id == engine_id
    assert params.msg_id == msg_id


# ---------------------------------------------------------------------------
# Bit-flip mutations of a discovery packet never raise
# ---------------------------------------------------------------------------


@given(st.integers(min_value=0, max_value=127))
@settings(max_examples=300)
def test_bit_flip_never_raises(byte_pos: int) -> None:
    """XOR-mutating each byte of a discovery packet never raises."""
    raw = bytearray(encode_v3_discovery(1, 1))
    if byte_pos < len(raw):
        raw[byte_pos] ^= 0xFF
    result = decode_v3_message(bytes(raw))
    assert isinstance(result, (tuple, Malformed))
