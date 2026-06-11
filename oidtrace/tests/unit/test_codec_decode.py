"""Tests for oidtrace.codec — decode side (Task 5).

Covers decode_message: happy-path round-trips and tolerant handling of garbage.
"""

from __future__ import annotations

import pytest

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
