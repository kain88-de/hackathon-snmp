"""Smoke tests for the quirk emulator fixture (OIDEmu seed)."""

import asyncio

import pytest

from oidtrace.codec import Malformed, Message, decode_message, encode_getbulk
from oidtrace.oid import Oid
from tests.support.emulator import EmuDevice, Quirks


@pytest.fixture
async def default_device(emulator_factory):
    """A simple 100-OID device with no quirks."""
    async with emulator_factory(EmuDevice.simple()) as (host, port):
        yield host, port


@pytest.fixture
async def fixed_rid_device(emulator_factory):
    """A simple device with fixed_request_id=1 quirk."""
    device = EmuDevice.simple(quirks=Quirks(fixed_request_id=1))
    async with emulator_factory(device) as (host, port):
        yield host, port


async def _send_getbulk(
    host: str, port: int, oid: Oid, request_id: int, max_rep: int = 10
) -> bytes:
    """Send a GetBulk and return the raw response bytes via raw asyncio datagram."""
    loop = asyncio.get_running_loop()
    received: asyncio.Future[bytes] = loop.create_future()

    class _Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: object) -> None:  # noqa: ARG002
            if not received.done():
                received.set_result(data)

        def error_received(self, exc: Exception) -> None:
            if not received.done():
                received.set_exception(exc)

    raw = encode_getbulk(request_id, oid, non_repeaters=0, max_repetitions=max_rep)
    transport, _ = await loop.create_datagram_endpoint(_Proto, remote_addr=(host, port))
    try:
        transport.sendto(raw)
        return await asyncio.wait_for(received, timeout=2.0)
    finally:
        transport.close()


async def test_getbulk_returns_requested_count(default_device: tuple[str, int]) -> None:
    """A GetBulk for 10 entries returns 10 varbinds and echoes the request-id."""
    host, port = default_device
    request_id = 42
    start = Oid.from_str("1.3.6.1.2.1.2.2.1.1")

    raw = await _send_getbulk(host, port, start, request_id, max_rep=10)

    msg = decode_message(raw)
    assert not isinstance(msg, Malformed), f"decode failed: {msg.error}"
    assert isinstance(msg, Message)
    assert msg.request_id == request_id
    assert len(msg.varbinds) == 10


async def test_fixed_request_id_quirk_overrides_echoed_id(
    fixed_rid_device: tuple[str, int],
) -> None:
    """With fixed_request_id=1, the response carries id=1 regardless of what we sent."""
    host, port = fixed_rid_device
    sent_rid = 12345
    start = Oid.from_str("1.3.6.1.2.1.2.2.1.1")

    raw = await _send_getbulk(host, port, start, sent_rid, max_rep=5)

    msg = decode_message(raw)
    assert not isinstance(msg, Malformed), f"decode failed: {msg.error}"
    assert isinstance(msg, Message)
    assert msg.request_id == 1
    assert msg.request_id != sent_rid
