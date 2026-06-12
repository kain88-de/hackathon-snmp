"""UDP transport layer for OIDTrace.

The only I/O module — everything else is pure.  Packets are treated as opaque
bytes; no SNMP decoding happens here.

Key design decisions
--------------------
- Timestamps are stamped **in protocol callbacks** (event time), never at
  dequeue time.  This is required by trace-format.md § 4.3 rule 3 so that
  stray arrival gaps are honest.
- Mutable state lives only in the protocol's asyncio.Queue.
- UdpTransport is an async context manager — no bare try/close at call sites.
"""

from __future__ import annotations

import asyncio
import errno
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, override

from traceformat.vocab import AttemptError

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain types (I/O domain — distinct from generated models.Attempt)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attempt:
    """One datagram send and its outcome.

    Constructed once with its final outcome; never mutated mid-retry.
    Deliberately distinct from generated ``models.Attempt`` (see plan §
    Type-driven rules).  The walker converts transport.Attempt →
    models.Attempt at the records boundary.
    """

    sent_at: float
    received_at: float | None = None
    error: AttemptError | None = None


@dataclass(frozen=True)
class ExchangeIO:
    """Result of one logical exchange (initial send + retries).

    Attributes:
        attempts: One entry per datagram sent.  The last attempt whose
            ``received_at`` is set is the one that got the response.
        response: ``(received_at, raw_bytes)`` of the attributed response, or
            ``None`` when every attempt timed out or errored.
        strays: Immediately-available datagrams drained *after* the response
            arrived (duplicate replies, late answers to earlier requests, …).
            Each entry is ``(received_at, raw_bytes)``.
    """

    attempts: tuple[Attempt, ...]
    response: tuple[float, bytes] | None
    strays: tuple[tuple[float, bytes], ...]


# ---------------------------------------------------------------------------
# Transport Protocol (walker depends on this, not on UdpTransport directly)
# ---------------------------------------------------------------------------


class Transport(Protocol):
    """Minimal async transport protocol consumed by the walker."""

    async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO: ...


# ---------------------------------------------------------------------------
# Internal asyncio Protocol — stamps timestamps in callbacks (event time)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DatagramEvent:
    """A received UDP datagram, timestamped at callback time."""

    received_at: float
    data: bytes


@dataclass(frozen=True)
class _ErrorEvent:
    """An ICMP or OS error, timestamped at callback time."""

    received_at: float
    kind: AttemptError


_QueueItem = _DatagramEvent | _ErrorEvent


def _icmp_error_kind(exc: Exception) -> AttemptError:
    """Map an OS error to the closest AttemptError enum value."""
    code = getattr(exc, "errno", None)
    if code == errno.ECONNREFUSED:
        return AttemptError.ICMP_PORT_UNREACHABLE
    if code in (errno.EHOSTUNREACH, errno.ENETUNREACH):
        return AttemptError.ICMP_HOST_UNREACHABLE
    return AttemptError.SEND_FAILED


class _SnmpProtocol(asyncio.DatagramProtocol):
    """Asyncio datagram protocol that stamps timestamps in callbacks.

    Every event (datagram or ICMP error) is timestamped at the moment the
    callback fires — never when it is dequeued.  This is the critical
    invariant for trace-format.md § 4.3 rule 3.
    """

    def __init__(self, rel: Callable[[], float]) -> None:
        self._rel = rel
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue()
        self._transport: asyncio.DatagramTransport | None = None

    def now(self) -> float:
        """Return the current relative time, rounded to microseconds."""
        return round(self._rel(), 6)

    @override
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self._transport = transport

    @override
    def datagram_received(self, data: bytes, addr: object) -> None:
        received_at = self.now()
        log.debug("datagram received len=%d at %.6f", len(data), received_at)
        self._queue.put_nowait(_DatagramEvent(received_at=received_at, data=data))

    @override
    def error_received(self, exc: Exception) -> None:
        received_at = self.now()
        kind = _icmp_error_kind(exc)
        log.debug("error_received %s at %.6f", kind, received_at)
        self._queue.put_nowait(_ErrorEvent(received_at=received_at, kind=kind))

    @override
    def connection_lost(self, exc: Exception | None) -> None:  # pragma: no cover
        pass

    def send(self, raw: bytes) -> None:
        assert self._transport is not None
        self._transport.sendto(raw)

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()

    @property
    def queue(self) -> asyncio.Queue[_QueueItem]:
        return self._queue


# ---------------------------------------------------------------------------
# UdpTransport
# ---------------------------------------------------------------------------


class UdpTransport:
    """Connected UDP socket transport with retry and stray-drain logic.

    Create via ``await UdpTransport.create(host, port, rel)`` then use as an
    async context manager::

        async with await UdpTransport.create(host, port, rel) as t:
            result = await t.exchange(raw, timeout_s=2.0, retries=2)
    """

    def __init__(self, protocol: _SnmpProtocol) -> None:
        self._protocol = protocol
        self._closed = False

    @classmethod
    async def create(cls, host: str, port: int, rel: Callable[[], float]) -> UdpTransport:
        """Create a connected UDP datagram endpoint.

        Args:
            host: Target hostname or IP address.
            port: Target UDP port.
            rel: Callable returning relative time (seconds, monotonic).
        """
        loop = asyncio.get_event_loop()
        protocol = _SnmpProtocol(rel)
        await loop.create_datagram_endpoint(
            lambda: protocol,
            remote_addr=(host, port),
        )
        log.debug("UdpTransport created → %s:%d", host, port)
        return cls(protocol)

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> UdpTransport:
        return self

    async def __aexit__(self, *_: object) -> None:
        self._close()

    def _close(self) -> None:
        if not self._closed:
            self._closed = True
            self._protocol.close()
            log.debug("UdpTransport closed")

    # ------------------------------------------------------------------
    # exchange
    # ------------------------------------------------------------------

    async def exchange(self, raw: bytes, *, timeout_s: float, retries: int) -> ExchangeIO:
        """Send *raw* and wait for a response, retrying up to *retries* times.

        Per-attempt behaviour:
        - Send the byte-identical datagram.
        - Wait up to *timeout_s* for the first queue event.
        - Datagram → record as response, stop.
        - ICMP error → record error on this attempt, continue to next attempt.
        - Timeout → record unanswered attempt, continue to next retry.

        After the retry loop: yield to the event loop once (``asyncio.sleep(0)``),
        then drain all immediately-available datagrams from the queue into
        *strays*.

        Timestamps come from protocol callbacks — never re-stamped here.
        """
        protocol = self._protocol
        attempts: list[Attempt] = []
        response: tuple[float, bytes] | None = None

        total_sends = 1 + retries

        for send_idx in range(total_sends):
            sent_at = protocol.now()
            protocol.send(raw)
            log.debug("send #%d sent_at=%.6f", send_idx, sent_at)

            try:
                async with asyncio.timeout(timeout_s):
                    item = await protocol.queue.get()
            except TimeoutError:
                log.debug("send #%d timed out", send_idx)
                attempts.append(Attempt(sent_at=sent_at))
                continue

            # Decode the queue item
            if isinstance(item, _DatagramEvent):
                log.debug("send #%d response received_at=%.6f", send_idx, item.received_at)
                attempts.append(Attempt(sent_at=sent_at, received_at=item.received_at))
                response = (item.received_at, item.data)
                break
            else:
                assert isinstance(item, _ErrorEvent)
                log.debug("send #%d error %s at %.6f", send_idx, item.kind, item.received_at)
                attempts.append(Attempt(sent_at=sent_at, error=item.kind))
                # Errors are consumed in the attempt-wait window (format § 4.3 arrival-window
                # rule); a single queue.get() per attempt means no cross-attempt deferral.

        await asyncio.sleep(0)
        strays: list[tuple[float, bytes]] = []
        while not protocol.queue.empty():
            item = protocol.queue.get_nowait()
            if isinstance(item, _DatagramEvent):
                strays.append((item.received_at, item.data))
                log.debug("stray drained received_at=%.6f", item.received_at)

        return ExchangeIO(
            attempts=tuple(attempts),
            response=response,
            strays=tuple(strays),
        )
