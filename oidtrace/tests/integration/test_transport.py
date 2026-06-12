"""Integration tests for oidtrace.transport.UdpTransport."""

from __future__ import annotations

import asyncio
import time

from traceformat.vocab import AttemptError

from oidtrace.codec import encode_getbulk
from oidtrace.oid import Oid
from oidtrace.transport import UdpTransport
from tests.support.emulator import EmuDevice, Quirks

# A minimal GetBulk payload (request_id=1, oid=1.3.6, max_rep=1)
_RAW = encode_getbulk(1, Oid.from_str("1.3.6"), non_repeaters=0, max_repetitions=1)


async def test_simple_response(emulator_factory) -> None:
    """EmuDevice.simple(20): response present, exactly one attempt, received_at > sent_at."""
    device = EmuDevice.simple(20)
    async with emulator_factory(device) as (host, port):  # noqa: SIM117
        async with await UdpTransport.create(host, port, rel=time.monotonic) as t:
            result = await t.exchange(_RAW, timeout_s=2.0, retries=0)

    assert result.response is not None
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.received_at is not None
    assert attempt.received_at > attempt.sent_at
    assert attempt.sent_at >= 0.0


async def test_drop_all_timeout(emulator_factory) -> None:
    """drop_all + timeout_s=0.1, retries=2: response None, exactly 3 attempts, all unanswered."""
    device = EmuDevice.simple(20, quirks=Quirks(drop_all=True))
    async with emulator_factory(device) as (host, port):  # noqa: SIM117
        async with await UdpTransport.create(host, port, rel=time.monotonic) as t:
            result = await t.exchange(_RAW, timeout_s=0.1, retries=2)

    assert result.response is None
    assert len(result.attempts) == 3
    for attempt in result.attempts:
        assert attempt.received_at is None
        assert attempt.error is None


async def test_duplicate_responses(emulator_factory) -> None:
    """duplicate_responses, retries=0: one stray present with arrival-honest timestamps."""
    device = EmuDevice.simple(20, quirks=Quirks(duplicate_responses=True))
    async with emulator_factory(device) as (host, port):  # noqa: SIM117
        async with await UdpTransport.create(host, port, rel=time.monotonic) as t:
            result = await t.exchange(_RAW, timeout_s=2.0, retries=0)

    assert result.response is not None
    # The emulator sends both datagrams back-to-back; asyncio.sleep(0) in exchange()
    # drains the duplicate into strays reliably for loopback traffic.
    assert len(result.strays) == 1
    resp_at, resp_bytes = result.response
    stray_at, stray_bytes = result.strays[0]
    assert stray_bytes == resp_bytes
    # Both datagrams were arrival-stamped in datagram_received; they must be close
    # in time (sent back-to-back by the emulator on loopback).
    assert abs(stray_at - resp_at) < 0.05


async def test_icmp_port_unreachable() -> None:
    """Bind-and-close a local UDP port to guarantee refusal; at least one ICMP_PORT_UNREACHABLE."""
    # Grab a port, then immediately close the socket so ICMP unreachable fires.
    loop = asyncio.get_running_loop()
    tmp_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol,
        local_addr=("127.0.0.1", 0),
    )
    host, port = tmp_transport.get_extra_info("sockname")
    tmp_transport.close()
    # Allow the OS to reclaim the port before we send to it.
    await asyncio.sleep(0.01)

    async with await UdpTransport.create(host, port, rel=time.monotonic) as t:
        result = await t.exchange(_RAW, timeout_s=0.3, retries=1)

    assert result.response is None
    errors = [a.error for a in result.attempts if a.error is not None]
    assert any(e == AttemptError.ICMP_PORT_UNREACHABLE for e in errors)
