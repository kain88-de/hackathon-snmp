"""Integration tests for transport.py — loopback UDP via the quirk emulator."""

from __future__ import annotations

import socket
import time

from traceformat.vocab import AttemptError

from oidtrace.codec import encode_getbulk
from oidtrace.oid import Oid
from oidtrace.transport import UdpTransport
from tests.support.emulator import EmuDevice, Quirks

_OID = Oid.from_str("1.3.6.1.2.1.2.2.1")
_RAW = encode_getbulk(1, _OID, 0, 5)


def _rel() -> float:
    """Monotonic clock — absolute value used as relative time origin for tests."""
    return time.monotonic()


# ---------------------------------------------------------------------------
# 1. Simple device → response, one attempt, received_at > sent_at >= 0
# ---------------------------------------------------------------------------
async def test_simple_response(emulator_factory) -> None:  # type: ignore[no-untyped-def]
    """A simple device returns one response with proper timestamps."""
    async with (
        emulator_factory(EmuDevice.simple()) as (host, port),
        await UdpTransport.create(host, port, _rel) as t,
    ):
        result = await t.exchange(_RAW, timeout_s=2.0, retries=0)

    assert result.response is not None
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.error is None
    assert attempt.received_at is not None
    assert attempt.sent_at >= 0
    assert attempt.received_at > attempt.sent_at


# ---------------------------------------------------------------------------
# 2. drop_all, timeout_s=0.1, retries=2 → None response, exactly 3 attempts
# ---------------------------------------------------------------------------
async def test_drop_all_timeout(emulator_factory) -> None:  # type: ignore[no-untyped-def]
    """drop_all with 2 retries yields no response and 3 unanswered attempts."""
    quirks = Quirks(drop_all=True)
    async with (
        emulator_factory(EmuDevice.simple(quirks=quirks)) as (host, port),
        await UdpTransport.create(host, port, _rel) as t,
    ):
        result = await t.exchange(_RAW, timeout_s=0.1, retries=2)

    assert result.response is None
    assert len(result.attempts) == 3  # 1 initial + 2 retries
    for attempt in result.attempts:
        assert attempt.received_at is None
        assert attempt.error is None


# ---------------------------------------------------------------------------
# 3. duplicate_responses, retries=0 → one stray, bytes == response bytes,
#    stray timestamp close to response timestamp (arrival-stamped, abs < 0.05 s)
# ---------------------------------------------------------------------------
async def test_duplicate_responses_creates_stray(emulator_factory) -> None:  # type: ignore[no-untyped-def]
    """duplicate_responses quirk produces exactly one stray with honest timestamps."""
    quirks = Quirks(duplicate_responses=True)
    async with (
        emulator_factory(EmuDevice.simple(quirks=quirks)) as (host, port),
        await UdpTransport.create(host, port, _rel) as t,
    ):
        result = await t.exchange(_RAW, timeout_s=2.0, retries=0)

    assert result.response is not None
    assert len(result.strays) == 1

    resp_at, resp_bytes = result.response
    stray_at, stray_bytes = result.strays[0]

    # Bytes are identical (same datagram sent twice by the emulator)
    assert stray_bytes == resp_bytes

    # Both timestamps are arrival-stamped in callbacks (close together, loopback)
    assert abs(stray_at - resp_at) < 0.05


# ---------------------------------------------------------------------------
# 4. Closed local UDP port → ICMP_PORT_UNREACHABLE, no response
# ---------------------------------------------------------------------------
async def test_icmp_port_unreachable() -> None:
    """Sending to a closed UDP port triggers an ICMP port-unreachable error."""
    # Bind and immediately close a socket to get a free port nothing listens on.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    async with await UdpTransport.create("127.0.0.1", port, _rel) as t:
        result = await t.exchange(_RAW, timeout_s=1.0, retries=1)

    error_attempts = [a for a in result.attempts if a.error is not None]
    assert len(error_attempts) >= 1
    assert error_attempts[0].error == AttemptError.ICMP_PORT_UNREACHABLE
    assert result.response is None


# ---------------------------------------------------------------------------
# 5. Async CM usage: async with await UdpTransport.create(...) as t:
# ---------------------------------------------------------------------------
async def test_async_context_manager(emulator_factory) -> None:  # type: ignore[no-untyped-def]
    """UdpTransport works as an async context manager (required CM form)."""
    async with (
        emulator_factory(EmuDevice.simple()) as (host, port),
        await UdpTransport.create(host, port, _rel) as t,
    ):
        result = await t.exchange(_RAW, timeout_s=2.0, retries=0)

    assert result.response is not None
    assert len(result.attempts) == 1


# ---------------------------------------------------------------------------
# Extra: idempotent close (no exception on double-close)
# ---------------------------------------------------------------------------
async def test_close_is_idempotent(emulator_factory) -> None:  # type: ignore[no-untyped-def]
    """Calling __aexit__ twice must not raise."""
    async with emulator_factory(EmuDevice.simple()) as (host, port):
        t = await UdpTransport.create(host, port, _rel)
        await t.__aenter__()
        await t.__aexit__(None, None, None)
        await t.__aexit__(None, None, None)  # second close is a no-op
