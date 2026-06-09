import contextlib
import socket
import threading
import time
from dataclasses import dataclass

from pyasn1.codec.ber import decoder, encoder
from pyasn1.type.univ import ObjectIdentifier
from pysnmp.proto import api, rfc1902
from pysnmp.proto.api import v2c as snmp_v2c

from ._mibs import SnmpValue, build_oid_tree

_START_TIME = time.monotonic()
_SYSUPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)


@dataclass
class EmulatorConfig:
    community: str = "public"
    slow_prefixes: tuple[str, ...] = ("1.3.6.1.2.1.2.2.1",)
    slow_delay: float = 3.0
    n_interfaces: int = 4


class EmulatorServer:
    def __init__(self, config: EmulatorConfig, port: int = 0, host: str = "127.0.0.1") -> None:
        self._config = config
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._reset_event = threading.Event()
        self._oid_tree: dict[tuple[int, ...], SnmpValue] = {}
        self._sorted_oids: list[tuple[int, ...]] = []

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        self._oid_tree = build_oid_tree(self._config.n_interfaces)
        self._sorted_oids = sorted(self._oid_tree.keys())
        self._stop_event.clear()
        self._reset_event.clear()
        self._bind()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._reset_event.set()
        self._close_sock()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def reset(self) -> None:
        self._reset_event.set()
        if self._config.slow_prefixes:
            time.sleep(0.05)  # hold set long enough to catch late-arriving slow requests
        self._reset_event.clear()

    def _bind(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.05)
        sock.bind((self._host, self._port))
        self._port = sock.getsockname()[1]
        self._sock = sock

    def _close_sock(self) -> None:
        sock, self._sock = self._sock, None
        if sock:
            with contextlib.suppress(OSError):
                sock.close()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            sock = self._sock
            if sock is None:
                time.sleep(0.01)
                continue
            try:
                data, addr = sock.recvfrom(65535)
            except OSError:
                if not self._stop_event.is_set():
                    time.sleep(0.01)
                continue
            resp = self._process(data, addr)
            if resp is not None:
                with contextlib.suppress(OSError):
                    sock.sendto(resp, addr)

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

    def _is_slow(self, oid_tuple: tuple[int, ...]) -> bool:
        s = ".".join(map(str, oid_tuple))
        return any(s.startswith(p) for p in self._config.slow_prefixes)

    def _process(self, data: bytes, _addr: tuple[str, int]) -> bytes | None:
        t0 = time.monotonic()

        try:
            ver = api.decodeMessageVersion(data)
            p_mod = api.PROTOCOL_MODULES[ver]
            req_msg, _ = decoder.decode(data, asn1Spec=p_mod.Message())
        except Exception:
            return None

        if bytes(p_mod.apiMessage.get_community(req_msg)).decode() != self._config.community:
            return None

        req_pdu = p_mod.apiMessage.get_pdu(req_msg)
        pdu_name = req_pdu.__class__.__name__
        req_binds = p_mod.apiPDU.get_varbinds(req_pdu)
        rsp_binds: list[tuple[object, object]] = []
        slow = False
        if pdu_name == "GetRequestPDU":
            for oid, _ in req_binds:
                t = tuple(oid)
                slow = slow or self._is_slow(t)
                val = self._lookup(t)
                rsp_binds.append((oid, val if val is not None else rfc1902.OctetString("")))

        elif pdu_name == "GetNextRequestPDU":
            for oid, _ in req_binds:
                t = tuple(oid)
                next_oid, val = self._lookup_next(t)
                if next_oid is None:
                    from pysnmp.proto.rfc1905 import endOfMibView

                    rsp_binds.append((oid, endOfMibView))
                    continue
                slow = slow or self._is_slow(next_oid)
                rsp_binds.append((ObjectIdentifier(next_oid), val))

        elif pdu_name == "GetBulkRequestPDU":
            non_rep = int(snmp_v2c.apiBulkPDU.get_non_repeaters(req_pdu))
            max_rep = int(snmp_v2c.apiBulkPDU.get_max_repetitions(req_pdu))
            for oid, _ in req_binds[:non_rep]:
                t = tuple(oid)
                next_oid, val = self._lookup_next(t)
                if next_oid and val is not None:
                    slow = slow or self._is_slow(next_oid)
                    rsp_binds.append((ObjectIdentifier(next_oid), val))
            rep_oids = [tuple(oid) for oid, _ in req_binds[non_rep:]]
            for _ in range(max_rep):
                if not rep_oids:
                    break
                advanced = []
                for t in rep_oids:
                    next_oid, val = self._lookup_next(t)
                    if next_oid and val is not None:
                        slow = slow or self._is_slow(next_oid)
                        rsp_binds.append((ObjectIdentifier(next_oid), val))
                        advanced.append(next_oid)
                rep_oids = advanced
        else:
            return None

        if req_binds:
            first_oid = ".".join(map(str, tuple(req_binds[0][0])))
            tag = "[SLOW]" if slow else "[FAST]"
            print(f"{tag} {pdu_name:<22} {first_oid}", end="", flush=True)

        if slow:
            self._reset_event.wait(timeout=self._config.slow_delay)
            if self._reset_event.is_set():
                if req_binds:
                    print("  →  dropped", flush=True)
                return None

        rsp_msg = p_mod.apiMessage.get_response(req_msg)
        rsp_pdu = p_mod.apiMessage.get_pdu(rsp_msg)
        p_mod.apiPDU.set_varbinds(rsp_pdu, rsp_binds)
        p_mod.apiPDU.set_error_status(rsp_pdu, 0)
        p_mod.apiPDU.set_error_index(rsp_pdu, 0)

        if req_binds:
            print(f"  →  {time.monotonic() - t0:.2f}s", flush=True)

        return encoder.encode(rsp_msg)
