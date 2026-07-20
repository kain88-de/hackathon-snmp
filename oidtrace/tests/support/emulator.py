"""Scripted quirk emulator for integration tests.

A loopback UDP DatagramProtocol that decodes incoming SNMP GetBulk requests
using the codec and responds according to a configured EmuDevice + Quirks.
Intended for use via the emulator_factory fixture in tests/integration/conftest.py.

EmulatorThread is a reusable context manager that starts an emulator on a daemon
thread and tears it down cleanly — importable by any test or library.
"""

from __future__ import annotations

import asyncio
import bisect
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, override

from oidtrace.codec import (
    PDU_GET,
    PDU_GETBULK,
    PDU_GETNEXT,
    PDU_REPORT,
    Malformed,
    Message,
    V3Params,
    Varbind,
    authenticate_msg,
    decode_message,
    decode_v3_message,
    encode_response,
    encode_v3_response,
    verify_auth,
)
from oidtrace.oid import Oid

if TYPE_CHECKING:
    from collections.abc import Mapping

    from oidtrace.auth import AuthProto

EMU_ENGINE_ID: bytes = b"\x80\x00\x00\x00\x01testemu\x00"
_USM_STATS_UNKNOWN_USER_NAMES = Oid.from_str("1.3.6.1.6.3.15.1.1.4.0")


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
    corrupt_auth_responses: bool = False
    delay_first_response_s: float = 0.0
    corrupt_discovery_reply: bool = False


# Varbind tree entry: (oid, tag, value_length)
_TreeEntry = tuple[Oid, int, int]

# OID prefix for a synthetic ifTable-like tree
_IF_TABLE = Oid.from_str("1.3.6.1.2.1.2.2.1")
_N_COLUMNS = 10
_INTEGER_TAG = 0x02
_TAG_NULL = 0x05
_TAG_NO_SUCH_OBJECT = 0x80  # v2c exception: Get for an OID the device does not expose


@dataclass(frozen=True, slots=True)
class EmuDevice:
    """An emulated SNMP device with a fixed OID tree and behavioral quirks.

    Attributes:
        tree: Sorted tuple of (oid, tag, value_length) entries.
        quirks: Behavioral modifiers.
        auth_users: Maps username (bytes) to (proto, kul) for authenticated v3.
        system_info: Maps system-group OID -> (tag, value_bytes) for plain Get
            requests (sysDescr/sysObjectID/sysUpTime/sysName). An OID absent from
            this map models a device that does not expose that field: a Get for it
            comes back NoSuchObject.
    """

    tree: tuple[_TreeEntry, ...]
    quirks: Quirks = field(default_factory=Quirks)
    auth_users: dict[bytes, tuple[AuthProto, bytes]] = field(default_factory=dict)
    system_info: Mapping[Oid, tuple[int, bytes]] = field(default_factory=dict)

    @classmethod
    def simple(
        cls,
        n_oids: int = 100,
        quirks: Quirks | None = None,
        auth_users: dict[bytes, tuple[AuthProto, bytes]] | None = None,
        system_info: Mapping[Oid, tuple[int, bytes]] | None = None,
    ) -> EmuDevice:
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
        return cls(
            tree=tuple(entries),
            quirks=quirks or Quirks(),
            system_info=system_info or {},
            auth_users=auth_users or {},
        )


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
        self._delayed_first_response = False

    @override
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self._transport = transport

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | bytes | bytearray, int]) -> None:
        task = asyncio.get_event_loop().create_task(self._handle(data, addr))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def aclose(self) -> None:
        """Cancel and await any in-flight datagram handlers.

        Called from the emulator's own event loop at shutdown so pending
        tasks don't get garbage-collected mid-flight ("Task was destroyed
        but it is pending!").
        """
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @override
    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        pass

    @override
    def connection_lost(self, exc: Exception | None) -> None:  # pragma: no cover
        pass

    def _get_response(
        self,
        varbinds_in: tuple[Varbind, ...],
        system_info: Mapping[Oid, tuple[int, bytes]],
        rid: int,
        version: int = 0,
    ) -> bytes:
        """Build a Get response: exact-match value if the device has it, else NoSuchObject."""
        varbinds = [
            (vb.oid, *system_info[vb.oid])
            if vb.oid in system_info
            else (vb.oid, _TAG_NO_SUCH_OBJECT, b"")
            for vb in varbinds_in
        ]
        return encode_response(rid, varbinds, version=version)

    def _getnext_response(
        self,
        request_oid: Oid,
        idx: int,
        tree: tuple[_TreeEntry, ...],
        rid: int,
        version: int = 0,
    ) -> bytes:
        """Build a GetNext response: next OID if found, else error_status=2 + Null."""
        if idx < len(tree):
            oid, tag, vlen = tree[idx]
            return encode_response(rid, [(oid, tag, b"\x00" * vlen)], version=version)
        return encode_response(
            rid, [(request_oid, _TAG_NULL, b"")], error_status=2, version=version
        )

    async def _getbulk_varbinds(
        self,
        request_oid: Oid,
        chunk: list[_TreeEntry],
        quirks: Quirks,
        tree: tuple[_TreeEntry, ...],
    ) -> list[tuple[Oid, int, bytes]] | None:
        """Build varbinds for a GetBulk response. Returns None to signal silence."""
        if chunk:
            if quirks.slow_prefix is not None and quirks.per_oid_delay_s > 0:
                total_delay = sum(
                    quirks.per_oid_delay_s
                    for oid, _, _ in chunk
                    if oid.in_subtree(quirks.slow_prefix)
                )
                if total_delay > 0:
                    await asyncio.sleep(total_delay)
            return [(oid, tag, b"\x00" * vlen) for oid, tag, vlen in chunk]
        # End of MIB
        match quirks.end_of_mib:
            case EndOfMib.SILENCE:
                return None
            case EndOfMib.WRAP:
                if not tree:
                    return None
                oid, tag, vlen = tree[0]
                return [(oid, tag, b"\x00" * vlen)]
            case EndOfMib.EOM:
                return [(request_oid, 0x82, b"")]

    async def _handle(self, data: bytes, addr: tuple[str | bytes | bytearray, int]) -> None:
        device = self._device
        quirks = device.quirks

        if quirks.drop_all:
            return

        if quirks.delay_first_response_s > 0 and not self._delayed_first_response:
            self._delayed_first_response = True
            # Runs as its own task (see datagram_received) so later requests
            # are handled concurrently, not blocked behind this delay.
            await asyncio.sleep(quirks.delay_first_response_s)

        # Try v3 first; fall through to v1/v2c if not a valid v3 message.
        v3_result = decode_v3_message(data)
        if not isinstance(v3_result, Malformed):
            msg, params = v3_result
            await self._handle_v3(msg, params, addr, raw_data=data)
            return

        msg = decode_message(data)
        if isinstance(msg, Malformed):
            return

        # Guard: ignore requests with no varbinds
        if not msg.varbinds:
            return

        request_oid = msg.varbinds[0].oid

        tree = device.tree
        keys = [e[0] for e in tree]
        idx = bisect.bisect_right(keys, request_oid)
        rid = quirks.fixed_request_id if quirks.fixed_request_id is not None else msg.request_id

        if msg.pdu_tag in (PDU_GET, PDU_GETNEXT):
            response = (
                self._get_response(msg.varbinds, device.system_info, rid, version=0)
                if msg.pdu_tag == PDU_GET
                else self._getnext_response(request_oid, idx, tree, rid, version=0)
            )
            assert self._transport is not None
            self._transport.sendto(response, addr)
            return

        max_reps = max(msg.f2, 1)
        chunk = list(tree[idx : idx + max_reps])
        varbinds = await self._getbulk_varbinds(request_oid, chunk, quirks, tree)
        if varbinds is None:
            return

        response = encode_response(rid, varbinds)

        assert self._transport is not None
        self._transport.sendto(response, addr)
        if quirks.duplicate_responses:
            self._transport.sendto(response, addr)

    async def _handle_v3(  # noqa: PLR0911, PLR0912
        self,
        msg: Message,
        params: V3Params,
        addr: tuple[str | bytes | bytearray, int],
        raw_data: bytes,
    ) -> None:
        # Auth check: if request carries a 12-byte auth_params, verify the MAC.
        # Drop silently on failure (unknown user or bad MAC).
        needs_auth = False
        auth_kul: bytes | None = None
        auth_proto: AuthProto | None = None
        if params.auth_params:  # non-empty auth_params means auth requested
            entry = self._device.auth_users.get(params.username)
            if entry is None:
                return
            auth_proto, auth_kul = entry
            if len(params.auth_params) != auth_proto.mac_length:
                return  # wrong length for this protocol — drop silently
            if not verify_auth(raw_data, params.auth_params, auth_kul, auth_proto):
                return
            needs_auth = True

        # Discovery: GetRequest with empty varbinds → Report PDU (always noAuthNoPriv)
        if msg.pdu_tag == PDU_GET and not msg.varbinds:
            if self._device.quirks.corrupt_discovery_reply:
                assert self._transport is not None
                self._transport.sendto(b"\x00" * 20, addr)
                return
            # simplified: real agents echo actual boots/time; our walker ignores these fields
            response = encode_v3_response(
                msg_id=params.msg_id,
                request_id=msg.request_id,
                varbinds=[(_USM_STATS_UNKNOWN_USER_NAMES, 0x41, b"\x00\x00\x00\x00")],
                engine_id=EMU_ENGINE_ID,
                username=params.username,
                pdu_tag=PDU_REPORT,
            )
            assert self._transport is not None
            self._transport.sendto(response, addr)
            return

        # GetNext: SNMPv3 walk uses GetNext instead of GetBulk
        if msg.pdu_tag == PDU_GETNEXT and msg.varbinds:
            request_oid = msg.varbinds[0].oid
            tree = self._device.tree
            keys = [e[0] for e in tree]
            idx = bisect.bisect_right(keys, request_oid)

            if idx < len(tree):
                oid, tag, vlen = tree[idx]
                varbinds = [(oid, tag, b"\x00" * vlen)]
            else:
                varbinds = [(request_oid, _TAG_NULL, b"")]

            # simplified: real agents echo actual boots/time; our walker ignores these fields
            response = encode_v3_response(
                msg_id=params.msg_id,
                request_id=msg.request_id,
                varbinds=varbinds,
                engine_id=EMU_ENGINE_ID,
                username=params.username,
                error_status=0 if idx < len(tree) else 2,
                proto=auth_proto,
            )
            if needs_auth:
                assert auth_kul is not None and auth_proto is not None
                sign_kul = (
                    auth_kul[:-1] + bytes([auth_kul[-1] ^ 0xFF])
                    if self._device.quirks.corrupt_auth_responses
                    else auth_kul
                )
                response = authenticate_msg(response, sign_kul, auth_proto)
            assert self._transport is not None
            self._transport.sendto(response, addr)
            return

        # GetBulk: reuse existing helper
        if msg.pdu_tag == PDU_GETBULK and msg.varbinds:
            request_oid = msg.varbinds[0].oid
            tree = self._device.tree
            keys = [e[0] for e in tree]
            idx = bisect.bisect_right(keys, request_oid)
            max_reps = max(msg.f2, 1)
            chunk = list(tree[idx : idx + max_reps])
            varbinds = await self._getbulk_varbinds(request_oid, chunk, self._device.quirks, tree)
            if varbinds is None:
                return
            # simplified: real agents echo actual boots/time; our walker ignores these fields
            response = encode_v3_response(
                msg_id=params.msg_id,
                request_id=msg.request_id,
                varbinds=varbinds,
                engine_id=EMU_ENGINE_ID,
                username=params.username,
                proto=auth_proto,
            )
            if needs_auth:
                assert auth_kul is not None and auth_proto is not None
                sign_kul = (
                    auth_kul[:-1] + bytes([auth_kul[-1] ^ 0xFF])
                    if self._device.quirks.corrupt_auth_responses
                    else auth_kul
                )
                response = authenticate_msg(response, sign_kul, auth_proto)
            assert self._transport is not None
            self._transport.sendto(response, addr)


# ---------------------------------------------------------------------------
# EmulatorThread — reusable context manager for test/library use
# ---------------------------------------------------------------------------


def _run_emulator_on_thread(
    port_ready: threading.Event,
    port_holder: list[int],
    state: dict[str, object],
    state_ready: threading.Event,
    device: EmuDevice,
) -> None:
    loop = asyncio.new_event_loop()

    async def _serve() -> None:
        stop = asyncio.Event()
        state["loop"] = loop
        state["stop"] = stop
        state_ready.set()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: EmuProtocol(device),
            local_addr=("127.0.0.1", 0),
        )
        sock = transport.get_extra_info("sockname")
        port_holder.append(sock[1])
        port_ready.set()
        await stop.wait()
        transport.close()
        await protocol.aclose()

    loop.run_until_complete(_serve())
    loop.close()


class EmulatorThread:
    """Context manager: starts an emulator on a daemon thread, tears it down on exit."""

    def __init__(
        self, quirks: object = None, auth_users: object = None, system_info: object = None
    ) -> None:
        self._port_ready: threading.Event = threading.Event()
        self._port_holder: list[int] = []
        self._state: dict[str, object] = {}
        self._state_ready: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._device = EmuDevice.simple(
            n_oids=20,
            quirks=quirks if isinstance(quirks, Quirks) else None,
            auth_users=auth_users if isinstance(auth_users, dict) else None,
            system_info=system_info if isinstance(system_info, dict) else None,
        )

    def __enter__(self) -> tuple[str, int]:
        self._thread = threading.Thread(
            target=_run_emulator_on_thread,
            args=(
                self._port_ready,
                self._port_holder,
                self._state,
                self._state_ready,
                self._device,
            ),
            daemon=True,
        )
        self._thread.start()
        self._port_ready.wait(timeout=5.0)
        assert self._port_holder, "Emulator did not bind a port in time"
        return "127.0.0.1", self._port_holder[0]

    def __exit__(self, *_: object) -> None:
        loop = self._state.get("loop")
        stop_event = self._state.get("stop")
        if isinstance(loop, asyncio.AbstractEventLoop) and isinstance(stop_event, asyncio.Event):
            loop.call_soon_threadsafe(stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
