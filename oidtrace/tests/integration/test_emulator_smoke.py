"""Smoke tests for the quirk emulator over loopback UDP.

Uses a raw asyncio datagram client — no transport module yet.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal, override

import pytest

from oidtrace.auth import password_to_key
from oidtrace.codec import (
    PDU_REPORT,
    PDU_RESPONSE,
    Malformed,
    authenticate_msg,
    decode_message,
    decode_v3_message,
    encode_getbulk,
    encode_getnext,
    encode_v3_discovery,
    encode_v3_getbulk,
    verify_auth,
)
from oidtrace.oid import Oid
from tests.support.emulator import EMU_ENGINE_ID, EmuDevice, Quirks

_EmuFactory = Callable[..., AbstractAsyncContextManager[tuple[str, int]]]


@dataclass
class _GetBulkArgs:
    request_id: int
    oid: Oid
    max_repetitions: int
    timeout_s: float = 2.0


async def _send_getbulk(host: str, port: int, args: _GetBulkArgs) -> bytes:
    """Send a GetBulk and return the raw response bytes."""
    raw = encode_getbulk(args.request_id, args.oid, 0, args.max_repetitions)
    loop = asyncio.get_event_loop()

    received: asyncio.Future[bytes] = loop.create_future()

    class _OneShot(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self._transport: asyncio.DatagramTransport | None = None

        @override
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            assert isinstance(transport, asyncio.DatagramTransport)
            self._transport = transport
            transport.sendto(raw)

        @override
        def datagram_received(self, data: bytes, addr: object) -> None:
            if not received.done():
                received.set_result(data)

        @override
        def error_received(self, exc: Exception) -> None:  # pragma: no cover
            if not received.done():
                received.set_exception(exc)

    transport, _ = await loop.create_datagram_endpoint(
        _OneShot,
        remote_addr=(host, port),
    )
    try:
        return await asyncio.wait_for(received, timeout=args.timeout_s)
    finally:
        transport.close()


async def test_getbulk_returns_requested_count(emulator_factory: _EmuFactory) -> None:
    """GetBulk for N varbinds returns exactly N varbinds and echoes the request id."""
    bulk_size = 5
    rid = 42
    start = Oid.from_str("1.3.6.1.2.1.2.2.1")  # one step before the tree

    async with emulator_factory(EmuDevice.simple(n_oids=100)) as (host, port):
        raw = await _send_getbulk(
            host, port, _GetBulkArgs(request_id=rid, oid=start, max_repetitions=bulk_size)
        )

    msg = decode_message(raw)
    assert not isinstance(msg, Malformed), f"Decode failed: {msg}"
    assert len(msg.varbinds) == bulk_size
    assert msg.request_id == rid


async def _send_getnext(host: str, port: int, oid: Oid, request_id: int = 1) -> bytes:
    """Send a GetNext and return the raw response bytes."""
    raw = encode_getnext(request_id, oid)
    loop = asyncio.get_event_loop()

    received: asyncio.Future[bytes] = loop.create_future()

    class _OneShot(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self._transport: asyncio.DatagramTransport | None = None

        @override
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            assert isinstance(transport, asyncio.DatagramTransport)
            self._transport = transport
            transport.sendto(raw)

        @override
        def datagram_received(self, data: bytes, addr: object) -> None:
            if not received.done():
                received.set_result(data)

        @override
        def error_received(self, exc: Exception) -> None:  # pragma: no cover
            if not received.done():
                received.set_exception(exc)

    transport, _ = await loop.create_datagram_endpoint(
        _OneShot,
        remote_addr=(host, port),
    )
    try:
        return await asyncio.wait_for(received, timeout=2.0)
    finally:
        transport.close()


async def test_getnext_before_tree(emulator_factory: _EmuFactory) -> None:
    """GetNext for OID before the tree returns one varbind and echoes the request_id."""
    rid = 99
    start = Oid.from_str("1.3.6.1.2.1.2.2.1")  # one step before the tree

    async with emulator_factory(EmuDevice.simple(n_oids=10)) as (host, port):
        raw = await _send_getnext(host, port, start, request_id=rid)

    msg = decode_message(raw)
    assert not isinstance(msg, Malformed), f"Decode failed: {msg}"
    assert msg.pdu_tag == PDU_RESPONSE
    assert len(msg.varbinds) == 1
    assert msg.request_id == rid


async def test_getnext_past_last_oid(emulator_factory: _EmuFactory) -> None:
    """GetNext for the last OID in the tree returns error_status == 2 (noSuchName)."""
    rid = 77
    # Use an OID beyond anything in the tree
    beyond = Oid.from_str("1.3.6.1.2.1.2.2.1.10.999")

    async with emulator_factory(EmuDevice.simple(n_oids=10)) as (host, port):
        raw = await _send_getnext(host, port, beyond, request_id=rid)

    msg = decode_message(raw)
    assert not isinstance(msg, Malformed), f"Decode failed: {msg}"
    assert msg.f1 == 2  # error_status = noSuchName
    assert msg.request_id == rid
    assert len(msg.varbinds) == 1
    assert msg.varbinds[0].tag == 0x05  # Null, not EndOfMibView (0x82)


async def test_fixed_request_id_overrides(emulator_factory: _EmuFactory) -> None:
    """fixed_request_id=1 means response carries rid=1 even when we sent rid=12345."""
    quirks = Quirks(fixed_request_id=1)
    start = Oid.from_str("1.3.6.1.2.1.2.2.1")

    async with emulator_factory(EmuDevice.simple(quirks=quirks)) as (host, port):
        raw = await _send_getbulk(
            host, port, _GetBulkArgs(request_id=12345, oid=start, max_repetitions=3)
        )

    msg = decode_message(raw)
    assert not isinstance(msg, Malformed), f"Decode failed: {msg}"
    assert msg.request_id == 1


async def _send_raw(host: str, port: int, raw: bytes, timeout_s: float = 2.0) -> bytes:
    """Send a raw UDP datagram and return the response bytes."""
    loop = asyncio.get_event_loop()
    received: asyncio.Future[bytes] = loop.create_future()

    class _OneShot(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self._transport: asyncio.DatagramTransport | None = None

        @override
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            assert isinstance(transport, asyncio.DatagramTransport)
            self._transport = transport
            transport.sendto(raw)

        @override
        def datagram_received(self, data: bytes, addr: object) -> None:
            if not received.done():
                received.set_result(data)

        @override
        def error_received(self, exc: Exception) -> None:  # pragma: no cover
            if not received.done():
                received.set_exception(exc)

    transport, _ = await loop.create_datagram_endpoint(
        _OneShot,
        remote_addr=(host, port),
    )
    try:
        return await asyncio.wait_for(received, timeout=timeout_s)
    finally:
        transport.close()


async def test_v3_discovery_returns_report(emulator_factory: _EmuFactory) -> None:
    """Sending an SNMPv3 discovery probe returns a Report PDU echoing the request_id."""
    async with emulator_factory(EmuDevice.simple()) as (host, port):
        raw_resp = await _send_raw(host, port, encode_v3_discovery(1, 42))

    result = decode_v3_message(raw_resp)
    assert not isinstance(result, Malformed), f"Decode failed: {result}"
    msg, _params = result
    assert msg.pdu_tag == PDU_REPORT, f"Expected PDU_REPORT, got 0x{msg.pdu_tag:02x}"
    assert msg.request_id == 42


async def test_v3_discovery_response_has_engine_id(emulator_factory: _EmuFactory) -> None:
    """Discovery response params carry a non-empty engineID."""
    async with emulator_factory(EmuDevice.simple()) as (host, port):
        raw_resp = await _send_raw(host, port, encode_v3_discovery(1, 42))

    result = decode_v3_message(raw_resp)
    assert not isinstance(result, Malformed), f"Decode failed: {result}"
    _msg, params = result
    assert params.engine_id != b"", "Expected non-empty engineID in discovery response"


async def test_v3_getbulk_after_discovery(emulator_factory: _EmuFactory) -> None:
    """After discovery, a v3 GetBulk returns a Response PDU with the requested varbind count."""
    start = Oid.from_str("1.3.6.1.2.1.2.2.1")

    async with emulator_factory(EmuDevice.simple(n_oids=100)) as (host, port):
        # Step 1: discovery
        raw_disc = await _send_raw(host, port, encode_v3_discovery(1, 42))
        disc_result = decode_v3_message(raw_disc)
        assert not isinstance(disc_result, Malformed), f"Discovery decode failed: {disc_result}"
        _disc_msg, params = disc_result

        # Step 2: GetBulk using engine_id from discovery
        raw_bulk = encode_v3_getbulk(
            msg_id=2,
            request_id=99,
            oid=start,
            max_repetitions=5,
            engine_id=params.engine_id,
            engine_boots=params.engine_boots,
            engine_time=params.engine_time,
            username=b"",
        )
        raw_resp = await _send_raw(host, port, raw_bulk)

    result = decode_v3_message(raw_resp)
    assert not isinstance(result, Malformed), f"Decode failed: {result}"
    msg, _params = result
    assert msg.pdu_tag == PDU_RESPONSE, f"Expected PDU_RESPONSE, got 0x{msg.pdu_tag:02x}"
    assert msg.request_id == 99
    assert len(msg.varbinds) == 5


@pytest.mark.parametrize("proto", ["MD5", "SHA"])
async def test_v3_authnopriv_getbulk_correct_key(
    emulator_factory: _EmuFactory, proto: Literal["MD5", "SHA"]
) -> None:
    """Auth GetBulk with correct MAC returns a signed response (MD5 and SHA)."""
    start = Oid.from_str("1.3.6.1.2.1.2.2.1")
    kul = password_to_key(b"testpass1", EMU_ENGINE_ID, proto)

    async with emulator_factory(
        EmuDevice.simple(n_oids=10, auth_users={b"authuser": (proto, kul)})
    ) as (host, port):
        # Step 1: discovery
        raw_disc = await _send_raw(host, port, encode_v3_discovery(1, 42))
        disc_result = decode_v3_message(raw_disc)
        assert not isinstance(disc_result, Malformed), f"Discovery decode failed: {disc_result}"
        _disc_msg, disc_params = disc_result

        # Step 2: authenticated GetBulk
        raw_bulk = encode_v3_getbulk(
            msg_id=2,
            request_id=100,
            oid=start,
            max_repetitions=5,
            engine_id=disc_params.engine_id,
            engine_boots=disc_params.engine_boots,
            engine_time=disc_params.engine_time,
            username=b"authuser",
            auth=True,
        )
        raw_signed = authenticate_msg(raw_bulk, kul, proto)
        raw_resp = await _send_raw(host, port, raw_signed)

    result = decode_v3_message(raw_resp)
    assert not isinstance(result, Malformed), f"Decode failed: {result}"
    msg, resp_params = result
    assert msg.pdu_tag == PDU_RESPONSE, f"Expected PDU_RESPONSE, got 0x{msg.pdu_tag:02x}"
    assert msg.request_id == 100
    # Response must carry a 12-byte auth_params
    assert len(resp_params.auth_params) == 12, (
        f"Expected 12-byte auth_params, got {len(resp_params.auth_params)}"
    )
    assert resp_params.auth_params != b"\x00" * 12, "auth_params must not be all zeros"
    assert verify_auth(raw_resp, resp_params.auth_params, kul, proto), (
        "Response MAC verification failed"
    )


@pytest.mark.parametrize("proto", ["MD5", "SHA"])
async def test_v3_authnopriv_getbulk_wrong_key_silently_dropped(
    emulator_factory: _EmuFactory,
    proto: Literal["MD5", "SHA"],
) -> None:
    """Auth GetBulk signed with wrong key is silently dropped — no response (MD5 and SHA)."""
    start = Oid.from_str("1.3.6.1.2.1.2.2.1")
    kul = password_to_key(b"testpass1", EMU_ENGINE_ID, proto)
    wrong_kul = password_to_key(b"wrongpass!", EMU_ENGINE_ID, proto)

    async with emulator_factory(
        EmuDevice.simple(n_oids=10, auth_users={b"authuser": (proto, kul)})
    ) as (host, port):
        # Discovery first to get engine_id
        raw_disc = await _send_raw(host, port, encode_v3_discovery(1, 42))
        disc_result = decode_v3_message(raw_disc)
        assert not isinstance(disc_result, Malformed), f"Discovery decode failed: {disc_result}"
        _disc_msg, disc_params = disc_result

        # Authenticated GetBulk signed with wrong key — expect no response
        raw_bulk = encode_v3_getbulk(
            msg_id=3,
            request_id=101,
            oid=start,
            max_repetitions=5,
            engine_id=disc_params.engine_id,
            engine_boots=disc_params.engine_boots,
            engine_time=disc_params.engine_time,
            username=b"authuser",
            auth=True,
        )
        raw_signed_wrong = authenticate_msg(raw_bulk, wrong_kul, proto)

        with pytest.raises(asyncio.TimeoutError):
            await _send_raw(host, port, raw_signed_wrong, timeout_s=0.3)
