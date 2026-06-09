import asyncio
import threading
import time
from dataclasses import dataclass
from typing import override

from pyasn1.type.univ import ObjectIdentifier
from pysnmp.carrier.asyncio.dgram.udp import SNMP_UDP_DOMAIN, UdpTransport
from pysnmp.entity import config as snmp_config
from pysnmp.entity.engine import SnmpEngine
from pysnmp.entity.rfc3413 import cmdrsp
from pysnmp.entity.rfc3413.context import SnmpContext
from pysnmp.proto import rfc1902, rfc1905
from pysnmp.proto.api import v2c as snmp_v2c

from ._mibs import SnmpValue, build_oid_tree

_START_TIME = time.monotonic()
_SYSUPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)


@dataclass
class EmulatorConfig:
    username: str = "monitor"
    auth_password: str = "authpass1"  # noqa: S105
    slow_prefixes: tuple[str, ...] = ("1.3.6.1.2.1.2.2.1.10", "1.3.6.1.2.1.2.2.1.16")
    slow_delay: float = 1.0
    n_interfaces: int = 4


class _OurResponder(cmdrsp.CommandResponderBase):
    SUPPORTED_PDU_TYPES = (
        rfc1905.GetRequestPDU.tagSet,
        rfc1905.GetNextRequestPDU.tagSet,
        rfc1905.GetBulkRequestPDU.tagSet,
    )

    def __init__(
        self,
        snmp_engine: SnmpEngine,
        snmp_context: SnmpContext,
        server: EmulatorServer,
    ) -> None:
        super().__init__(snmp_engine, snmp_context)
        self._server = server

    @override
    def handle_management_operation(
        self,
        snmpEngine: SnmpEngine,
        stateReference: object,
        contextName: object,
        PDU: object,
        acCtx: object = None,
    ) -> None:
        t0 = time.monotonic()
        pdu_name = PDU.__class__.__name__
        req_binds = snmp_v2c.apiPDU.get_varbinds(PDU)
        rsp_binds: list[tuple[object, object]] = []
        slow = False

        if pdu_name == "GetRequestPDU":
            for oid, _ in req_binds:
                t = tuple(oid)
                slow = slow or self._server._is_slow(t)
                val = self._server._lookup(t)
                rsp_binds.append((oid, val if val is not None else rfc1902.OctetString("")))

        elif pdu_name == "GetNextRequestPDU":
            for oid, _ in req_binds:
                t = tuple(oid)
                next_oid, val = self._server._lookup_next(t)
                if next_oid is None:
                    rsp_binds.append((oid, rfc1905.endOfMibView))
                    continue
                slow = slow or self._server._is_slow(next_oid)
                rsp_binds.append((ObjectIdentifier(next_oid), val))

        elif pdu_name == "GetBulkRequestPDU":
            non_rep = int(snmp_v2c.apiBulkPDU.get_non_repeaters(PDU))
            max_rep = int(snmp_v2c.apiBulkPDU.get_max_repetitions(PDU))
            for oid, _ in req_binds[:non_rep]:
                t = tuple(oid)
                next_oid, val = self._server._lookup_next(t)
                if next_oid and val is not None:
                    slow = slow or self._server._is_slow(next_oid)
                    rsp_binds.append((ObjectIdentifier(next_oid), val))
            rep_oids = [tuple(oid) for oid, _ in req_binds[non_rep:]]
            for _ in range(max_rep):
                if not rep_oids:
                    break
                advanced = []
                for t in rep_oids:
                    next_oid, val = self._server._lookup_next(t)
                    if next_oid and val is not None:
                        slow = slow or self._server._is_slow(next_oid)
                        rsp_binds.append((ObjectIdentifier(next_oid), val))
                        advanced.append(next_oid)
                rep_oids = advanced

        if req_binds:
            first_oid = ".".join(map(str, tuple(req_binds[0][0])))
            tag = "[SLOW]" if slow else "[FAST]"
            print(f"{tag} {pdu_name:<22} {first_oid}", end="", flush=True)

        if slow:
            self._server._reset_event.wait(timeout=self._server._config.slow_delay)
            if self._server._reset_event.is_set():
                if req_binds:
                    print("  →  dropped", flush=True)
                self.release_state_information(stateReference)
                return

        if req_binds:
            print(f"  →  {time.monotonic() - t0:.2f}s", flush=True)

        self.send_varbinds(snmpEngine, stateReference, 0, 0, rsp_binds)
        self.release_state_information(stateReference)


class EmulatorServer:
    def __init__(self, config: EmulatorConfig, port: int = 0, host: str = "127.0.0.1") -> None:
        self._config = config
        self._host = host
        self._port = port
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._snmp_engine: SnmpEngine | None = None
        self._reset_event = threading.Event()
        self._oid_tree: dict[tuple[int, ...], SnmpValue] = {}
        self._sorted_oids: list[tuple[int, ...]] = []

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        self._oid_tree = build_oid_tree(self._config.n_interfaces)
        self._sorted_oids = sorted(self._oid_tree.keys())
        self._reset_event.clear()
        ready = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait()

    def stop(self) -> None:
        self._reset_event.set()  # unblock any in-progress slow delay
        loop = self._loop
        engine = self._snmp_engine
        if loop and loop.is_running():
            if engine:
                loop.call_soon_threadsafe(engine.close_dispatcher)
            loop.call_soon_threadsafe(loop.stop)
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._loop = None
        self._snmp_engine = None

    def reset(self) -> None:
        self._reset_event.set()
        if self._config.slow_prefixes:
            time.sleep(0.05)
        self._reset_event.clear()

    def _run(self, ready: threading.Event) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._setup(ready))  # type: ignore[union-attr]
        self._loop.run_forever()  # type: ignore[union-attr]

    async def _setup(self, ready: threading.Event) -> None:
        loop = asyncio.get_running_loop()
        engine = SnmpEngine()
        self._snmp_engine = engine

        udp_transport = UdpTransport(loop=loop)
        udp_transport.open_server_mode(iface=(self._host, self._port))
        await udp_transport._lport  # type: ignore[misc]
        if udp_transport.transport is None:
            raise RuntimeError("UDP transport failed to bind")
        self._port = udp_transport.transport.get_extra_info("sockname")[1]

        snmp_config.add_transport(engine, SNMP_UDP_DOMAIN, udp_transport)
        snmp_config.add_v3_user(
            engine,
            self._config.username,
            authProtocol=snmp_config.USM_AUTH_HMAC96_MD5,
            authKey=self._config.auth_password,
        )
        snmp_config.add_vacm_user(
            engine,
            3,
            self._config.username,
            "authNoPriv",
            readSubTree=(1,),
        )
        snmp_context = SnmpContext(engine)
        _OurResponder(engine, snmp_context, self)
        ready.set()

    def _is_slow(self, oid_tuple: tuple[int, ...]) -> bool:
        s = ".".join(map(str, oid_tuple))
        return any(s.startswith(p) for p in self._config.slow_prefixes)

    def _lookup(self, oid_tuple: tuple[int, ...]) -> SnmpValue | None:
        if oid_tuple == _SYSUPTIME_OID:
            return rfc1902.TimeTicks(int((time.monotonic() - _START_TIME) * 100))
        return self._oid_tree.get(oid_tuple)

    def _lookup_next(
        self, oid_tuple: tuple[int, ...]
    ) -> tuple[tuple[int, ...] | None, SnmpValue | None]:
        for oid in self._sorted_oids:
            if oid > oid_tuple:
                val = self._lookup(oid)
                if val is not None:
                    return oid, val
        return None, None
