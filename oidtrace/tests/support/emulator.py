"""Scripted quirk emulator for integration tests.

A loopback UDP DatagramProtocol that decodes incoming SNMP GetBulk requests
using the codec and responds according to a configured EmuDevice + Quirks.
Intended for use via the emulator_factory fixture in tests/integration/conftest.py.
"""

from __future__ import annotations

import asyncio
import bisect
from dataclasses import dataclass, field
from enum import StrEnum
from typing import override

from oidtrace.codec import Malformed, decode_message, encode_response
from oidtrace.oid import Oid


class EndOfMib(StrEnum):
    """How the emulator signals end-of-MIB when the walk exhausts the tree."""

    EOM = "eom"  # one varbind (request oid, 0x82 EndOfMibView, b"")
    SILENCE = "silence"  # no response — caller times out
    WRAP = "wrap"  # return the first tree entry


@dataclass(frozen=True, slots=True)
class Quirks:
    """Behavioral modifiers for an EmuDevice."""

    fixed_request_id: int | None = None
    end_of_mib: EndOfMib = EndOfMib.EOM
    duplicate_responses: bool = False
    slow_prefix: Oid | None = None
    per_oid_delay_s: float = 0.0
    drop_all: bool = False


# Varbind tree entry: (oid, tag, value_length)
_TreeEntry = tuple[Oid, int, int]

# OID prefix for a synthetic ifTable-like tree
_IF_TABLE = Oid.from_str("1.3.6.1.2.1.2.2.1")
_N_COLUMNS = 10
_INTEGER_TAG = 0x02


@dataclass(frozen=True, slots=True)
class EmuDevice:
    """An emulated SNMP device with a fixed OID tree and behavioral quirks.

    Attributes:
        tree: Sorted tuple of (oid, tag, value_length) entries.
        quirks: Behavioral modifiers.
    """

    tree: tuple[_TreeEntry, ...]
    quirks: Quirks = field(default_factory=Quirks)

    @classmethod
    def simple(cls, n_oids: int = 100, quirks: Quirks | None = None) -> EmuDevice:
        """Build a sorted ifTable-like tree with n_oids entries.

        Creates 10 columns under 1.3.6.1.2.1.2.2.1.<col>, with
        ceil(n_oids / 10) instances per column, INTEGER tag 0x02, vlen 4.
        The tree is sorted by OID.
        """
        entries: list[_TreeEntry] = []
        n_instances = max(1, (n_oids + _N_COLUMNS - 1) // _N_COLUMNS)
        for col in range(1, _N_COLUMNS + 1):
            for inst in range(1, n_instances + 1):
                oid = Oid(arcs=(*_IF_TABLE.arcs, col, inst))
                entries.append((oid, _INTEGER_TAG, 4))
        entries.sort(key=lambda e: e[0])
        return cls(tree=tuple(entries), quirks=quirks or Quirks())


class EmuProtocol(asyncio.DatagramProtocol):
    """UDP DatagramProtocol implementing scripted SNMP responses.

    Public so that conftest.py can reference it directly when creating
    the asyncio datagram endpoint.
    """

    def __init__(self, device: EmuDevice) -> None:
        self._device = device
        self._transport: asyncio.DatagramTransport | None = None
        # Keep references to spawned tasks (RUF006 compliance).
        self._tasks: set[asyncio.Task[None]] = set()

    @override
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self._transport = transport

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | bytes | bytearray, int]) -> None:
        task = asyncio.get_event_loop().create_task(self._handle(data, addr))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @override
    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        pass

    @override
    def connection_lost(self, exc: Exception | None) -> None:  # pragma: no cover
        pass

    async def _handle(self, data: bytes, addr: tuple[str | bytes | bytearray, int]) -> None:
        device = self._device
        quirks = device.quirks

        if quirks.drop_all:
            return

        msg = decode_message(data)
        if isinstance(msg, Malformed):
            return

        # Guard: ignore requests with no varbinds
        if not msg.varbinds:
            return

        request_oid = msg.varbinds[0].oid
        max_reps = max(msg.f2, 1)

        # Bisect: find the first tree entry strictly AFTER request_oid
        tree = device.tree
        keys = [e[0] for e in tree]
        idx = bisect.bisect_right(keys, request_oid)

        chunk = list(tree[idx : idx + max_reps])

        # Build response varbinds
        if chunk:
            # Per-OID delay for OIDs under slow_prefix
            if quirks.slow_prefix is not None and quirks.per_oid_delay_s > 0:
                total_delay = sum(
                    quirks.per_oid_delay_s
                    for oid, _, _ in chunk
                    if oid.in_subtree(quirks.slow_prefix)
                )
                if total_delay > 0:
                    await asyncio.sleep(total_delay)
            varbinds: list[tuple[Oid, int, bytes]] = [
                (oid, tag, b"\x00" * vlen) for oid, tag, vlen in chunk
            ]
        else:
            # End of MIB
            match quirks.end_of_mib:
                case EndOfMib.SILENCE:
                    return
                case EndOfMib.WRAP:
                    if not tree:
                        return
                    oid, tag, vlen = tree[0]
                    varbinds = [(oid, tag, b"\x00" * vlen)]
                case EndOfMib.EOM:
                    varbinds = [(request_oid, 0x82, b"")]

        rid = quirks.fixed_request_id if quirks.fixed_request_id is not None else msg.request_id
        response = encode_response(rid, varbinds)

        assert self._transport is not None
        self._transport.sendto(response, addr)
        if quirks.duplicate_responses:
            self._transport.sendto(response, addr)
