"""Smoke tests for the quirk emulator over loopback UDP.

Uses a raw asyncio datagram client — no transport module yet.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import override

from oidtrace.codec import PDU_RESPONSE, Malformed, decode_message, encode_getbulk, encode_getnext
from oidtrace.oid import Oid
from tests.support.emulator import EmuDevice, Quirks

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
