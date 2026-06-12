"""UDP transport for OIDTrace — the only I/O in the package.

All packets are opaque bytes; no decoding/validation here.
Timestamps are round(rel(), 6) where rel is a caller-supplied clock.
"""

from __future__ import annotations

import asyncio
import errno
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from traceformat.vocab import AttemptError

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# I/O domain types (distinct from traceformat.models.Attempt)


@dataclass(frozen=True)
class Attempt:
    """A single send attempt with its final outcome."""

    sent_at: float
    received_at: float | None = None
    error: AttemptError | None = None


@dataclass(frozen=True)
class ExchangeIO:
    """The full result of one exchange (all attempts + response + strays)."""

    attempts: tuple[Attempt, ...]
    response: tuple[float, bytes] | None
    strays: tuple[tuple[float, bytes], ...]


# ---------------------------------------------------------------------------
# Protocol (walker depends on this only)


class Transport(Protocol):
    async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO: ...


# ---------------------------------------------------------------------------
# Event types for the internal queue


@dataclass(frozen=True)
class _DatagramEvent:
    received_at: float
    data: bytes


@dataclass(frozen=True)
class _ErrorEvent:
    received_at: float
    error: AttemptError


# ---------------------------------------------------------------------------
# asyncio DatagramProtocol that feeds the queue


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        queue: asyncio.Queue[_DatagramEvent | _ErrorEvent],
        rel: Callable[[], float],
    ) -> None:
        self._queue = queue
        self._rel = rel

    def datagram_received(self, data: bytes, addr: object) -> None:  # noqa: ARG002
        # Stamp at arrival time so stray timestamps are honest (trace-format.md § 4.3 rule 3).
        self._queue.put_nowait(_DatagramEvent(received_at=round(self._rel(), 6), data=data))

    def error_received(self, exc: Exception) -> None:
        received_at = round(self._rel(), 6)
        err_no = getattr(exc, "errno", None)
        if err_no == errno.ECONNREFUSED:
            error = AttemptError.ICMP_PORT_UNREACHABLE
        elif err_no in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            error = AttemptError.ICMP_HOST_UNREACHABLE
        else:
            error = AttemptError.SEND_FAILED
        self._queue.put_nowait(_ErrorEvent(received_at=received_at, error=error))


# ---------------------------------------------------------------------------
# UdpTransport


class UdpTransport:
    """Connected asyncio UDP transport."""

    def __init__(
        self,
        transport: asyncio.DatagramTransport,
        queue: asyncio.Queue[_DatagramEvent | _ErrorEvent],
        rel: Callable[[], float],
    ) -> None:
        self._transport = transport
        self._queue = queue
        self._rel = rel

    @classmethod
    async def create(
        cls,
        host: str,
        port: int,
        rel: Callable[[], float],
    ) -> UdpTransport:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[_DatagramEvent | _ErrorEvent] = asyncio.Queue()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _UdpProtocol(queue, rel),
            remote_addr=(host, port),
        )
        return cls(transport, queue, rel)  # type: ignore[arg-type]

    async def __aenter__(self) -> UdpTransport:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._transport.is_closing():
            self._transport.close()

    async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO:
        attempts: list[Attempt] = []
        response: tuple[float, bytes] | None = None

        total = 1 + retries
        for _ in range(total):
            sent_at = round(self._rel(), 6)
            self._transport.sendto(raw)

            try:
                async with asyncio.timeout(timeout_s):
                    event = await self._queue.get()
            except TimeoutError:
                attempts.append(Attempt(sent_at=sent_at))
                continue

            if isinstance(event, _ErrorEvent):
                # Attribution by arrival window (trace-format.md § 4.3): the error is
                # attributed to whichever attempt's wait it arrived during.
                attempts.append(Attempt(sent_at=sent_at, error=event.error))
                continue

            # DatagramEvent — got a response; use the arrival-stamped timestamp.
            attempts.append(Attempt(sent_at=sent_at, received_at=event.received_at))
            response = (event.received_at, event.data)
            break

        # Drain immediately-available datagrams into strays; timestamps were already
        # set at arrival time in datagram_received — use them as-is.
        strays: list[tuple[float, bytes]] = []
        if response is not None:
            await asyncio.sleep(0)
            while not self._queue.empty():
                event = self._queue.get_nowait()
                if isinstance(event, _DatagramEvent):
                    strays.append((event.received_at, event.data))

        return ExchangeIO(
            attempts=tuple(attempts),
            response=response,
            strays=tuple(strays),
        )
