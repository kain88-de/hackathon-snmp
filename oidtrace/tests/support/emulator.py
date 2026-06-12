"""Quirk emulator test support (OIDEmu seed).

Provides EmuDevice and Quirks dataclasses plus an asyncio DatagramProtocol
responder.  Used via the emulator_factory fixture in tests/integration/conftest.py.
"""

from __future__ import annotations

import asyncio
import bisect
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from oidtrace.codec import Malformed, decode_message, encode_response
from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# Public data types


class EndOfMib(StrEnum):
    EOM = "eom"
    SILENCE = "silence"
    WRAP = "wrap"


@dataclass(frozen=True)
class Quirks:
    fixed_request_id: int | None = None
    end_of_mib: EndOfMib = EndOfMib.EOM
    duplicate_responses: bool = False
    slow_prefix: Oid | None = None
    per_oid_delay_s: float = 0.0
    drop_all: bool = False


@dataclass(frozen=True)
class EmuDevice:
    """An emulated SNMP device.

    tree entries: (oid, ber_tag, vlen), sorted by OID.
    """

    tree: tuple[tuple[Oid, int, int], ...]
    quirks: Quirks = field(default_factory=Quirks)

    @classmethod
    def simple(
        cls,
        n_oids: int = 100,
        quirks: Quirks | None = None,
    ) -> EmuDevice:
        """Build an ifTable-like tree.

        10 columns under 1.3.6.1.2.1.2.2.1.<c>, instances 1..n/10,
        tag 0x02 (Integer), vlen 4.
        """
        columns = range(1, 11)
        instances = range(1, n_oids // 10 + 1)
        entries: list[tuple[Oid, int, int]] = [
            (Oid.from_str(f"1.3.6.1.2.1.2.2.1.{c}.{i}"), 0x02, 4)
            for c in columns
            for i in instances
        ]
        entries.sort(key=lambda t: t[0])
        return cls(
            tree=tuple(entries),
            quirks=quirks if quirks is not None else Quirks(),
        )


# ---------------------------------------------------------------------------
# Asyncio protocol


class EmuProtocol(asyncio.DatagramProtocol):
    def __init__(self, device: EmuDevice) -> None:
        self._device = device
        self._keys: list[Oid] = [oid for oid, _, _ in device.tree]
        self._transport: asyncio.DatagramTransport | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        task = asyncio.ensure_future(self._handle(data, addr))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        transport = self._transport
        if transport is None:
            return

        quirks = self._device.quirks

        if quirks.drop_all:
            return

        decoded = decode_message(data)
        if isinstance(decoded, Malformed):
            return  # malformed — silently drop
        msg = decoded

        if not msg.varbinds:
            return

        # Successor lookup from the first varbind OID
        request_oid = msg.varbinds[0].oid
        idx = bisect.bisect_right(self._keys, request_oid)
        count = max(msg.f2, 1)
        chunk = self._device.tree[idx : idx + count]

        if chunk:
            varbinds: list[tuple[Oid, int, bytes]] = [
                (oid, tag, b"\x00" * vlen) for oid, tag, vlen in chunk
            ]

            # Per-OID delay for OIDs under slow_prefix
            if quirks.slow_prefix is not None and quirks.per_oid_delay_s > 0.0:
                delay = sum(
                    quirks.per_oid_delay_s
                    for oid, _, _ in chunk
                    if oid.in_subtree(quirks.slow_prefix)
                )
                if delay > 0.0:
                    await asyncio.sleep(delay)
        else:
            match quirks.end_of_mib:
                case EndOfMib.SILENCE:
                    return
                case EndOfMib.WRAP:
                    first_oid, first_tag, first_vlen = self._device.tree[0]
                    varbinds = [(first_oid, first_tag, b"\x00" * first_vlen)]
                case _:  # EndOfMib.EOM and any unknown future value
                    varbinds = [(request_oid, 0x82, b"")]

        rid = quirks.fixed_request_id if quirks.fixed_request_id is not None else msg.request_id
        raw = encode_response(rid, varbinds)

        transport.sendto(raw, addr)
        if quirks.duplicate_responses:
            transport.sendto(raw, addr)
