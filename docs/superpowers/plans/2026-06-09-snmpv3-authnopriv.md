# SNMPv3 authNoPriv/MD5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SNMPv2c community-string auth with SNMPv3 USM authNoPriv/HMAC-MD5 across the emulator and trouble-shooter packages.

**Architecture:** The emulator's raw UDP loop is replaced by pysnmp's entity framework (`SnmpEngine` + `CommandResponderBase`); pysnmp handles auth/engine-ID discovery automatically while our OID-tree and slow-region logic move verbatim into a private `_OurResponder` class. The prober and `main.py` swap `CommunityData` for `UsmUserData`; tests swap credentials accordingly.

**Tech Stack:** pysnmp 7.1.27 (`entity.config`, `entity.rfc3413.cmdrsp`, `carrier.asyncio.dgram.udp`), asyncio (new event loop per emulator thread), pyasn1.

---

## File map

| File | Action |
|---|---|
| `emulator/emulator/_core.py` | Full rewrite — new imports, `EmulatorConfig`, `_OurResponder`, `EmulatorServer` |
| `emulator/tests/test_emulator.py` | Swap `CommunityData` helper → `UsmUserData`; rename community test |
| `trouble-shooter/src/trouble_shooter/detector/prober.py` | Constructor + import swap |
| `trouble-shooter/tests/unit/test_prober_bulk_walk.py` | Update `_make_prober()` |
| `trouble-shooter/tests/integration/conftest.py` | Add `username`/`auth_password` to all `EmulatorConfig` and `SnmpProber` calls |
| `trouble-shooter/tests/integration/test_prober.py` | Update all direct `SnmpProber(...)` calls |
| `trouble-shooter/src/trouble_shooter/main.py` | Request models + `_snmp_get`/`_snmp_walk` helper swap |
| `trouble-shooter/tests/integration/test_check.py` | Replace `"community"` in all JSON payloads |
| `trouble-shooter/tests/integration/test_walk.py` | Replace `"community"` in all JSON payloads |
| `trouble-shooter/tests/integration/test_api_diagnose.py` | Replace `"community"` in all JSON payloads |

---

### Task 1: Update emulator unit tests (write failing tests first)

**Files:**
- Modify: `emulator/tests/test_emulator.py`

- [ ] **Step 1: Replace the entire test file**

```python
import asyncio
import threading
import time
from typing import TYPE_CHECKING

from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    usmHMACMD5AuthProtocol,
)

from emulator import EmulatorConfig, EmulatorServer

if TYPE_CHECKING:
    from pysnmp.proto import errind


async def _snmp_get(
    engine: SnmpEngine,
    port: int,
    oid: str,
    username: str = "monitor",
    auth_password: str = "authpass1",
    timeout: float = 0.5,
) -> tuple["errind.ErrorIndication | None", tuple[ObjectType, ...]]:
    err, _status, _, var_binds = await get_cmd(
        engine,
        UsmUserData(username, authKey=auth_password, authProtocol=usmHMACMD5AuthProtocol),
        await UdpTransportTarget.create(("127.0.0.1", port), timeout=timeout, retries=0),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    return err, var_binds


async def test_server_responds_to_snmp_get(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        err, var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


def test_server_port_is_assigned_when_zero() -> None:
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config, port=0)
    server.start()
    try:
        assert server.port > 0
    finally:
        server.stop()


async def test_server_rejects_wrong_credentials(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(username="monitor", auth_password="authpass1", slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        wrong_engine = SnmpEngine()
        try:
            err, _ = await _snmp_get(
                wrong_engine, server.port, "1.3.6.1.2.1.1.1.0",
                username="unknown", auth_password="authpass1", timeout=0.5,
            )
            assert err is not None
        finally:
            wrong_engine.close_dispatcher()

        err, var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
    finally:
        server.stop()


async def test_server_slow_prefix_adds_delay(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.1)
    server = EmulatorServer(config)
    server.start()
    try:
        t = time.monotonic()
        err, _ = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.2.1.0", timeout=2.0)
        elapsed = time.monotonic() - t
        assert err is None
        assert elapsed >= 0.1
    finally:
        server.stop()


async def test_reset_server_still_responds_after_reset(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        server.reset()
        err, var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


async def test_reset_drops_in_flight_slow_response(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.3)
    server = EmulatorServer(config)
    server.start()
    try:
        received: list[object] = []

        def slow_get() -> None:
            async def _do() -> None:
                engine = SnmpEngine()
                try:
                    err, var_binds = await _snmp_get(
                        engine, server.port, "1.3.6.1.2.1.2.1.0", timeout=1.0
                    )
                    if err is None:
                        received.append(var_binds)
                finally:
                    engine.close_dispatcher()
            asyncio.run(_do())

        t = threading.Thread(target=slow_get)
        t.start()
        await asyncio.sleep(0.15)  # allow SNMPv3 engine-ID discovery + request to arrive
        server.reset()
        t.join(timeout=2.0)

        assert received == [], "slow response should have been dropped by reset"

        err, _var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
    finally:
        server.stop()
```

- [ ] **Step 2: Run tests — expect failures**

```
cd emulator && uv run pytest tests/test_emulator.py -v
```

Expected: `test_server_responds_to_snmp_get` FAIL, `test_server_rejects_wrong_credentials` FAIL (second `assert err is None`), `test_server_slow_prefix_adds_delay` FAIL, `test_reset_*` FAIL. `test_server_port_is_assigned_when_zero` may PASS.

---

### Task 2: Rewrite `emulator/_core.py` with SNMPv3 entity framework

**Files:**
- Modify: `emulator/emulator/_core.py`

- [ ] **Step 1: Replace the entire file**

```python
import asyncio
import threading
import time
from dataclasses import dataclass

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
    auth_password: str = "authpass1"
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
        server: "EmulatorServer",
    ) -> None:
        super().__init__(snmp_engine, snmp_context)
        self._server = server

    def handle_management_operation(
        self,
        snmpEngine: SnmpEngine,
        stateReference: object,
        contextName: object,
        PDU: object,
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
    def __init__(
        self, config: EmulatorConfig, port: int = 0, host: str = "127.0.0.1"
    ) -> None:
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
        self._loop.run_until_complete(self._setup(ready))
        self._loop.run_forever()

    async def _setup(self, ready: threading.Event) -> None:
        loop = asyncio.get_running_loop()
        engine = SnmpEngine()
        self._snmp_engine = engine

        udp_transport = UdpTransport(loop=loop)
        udp_transport.open_server_mode(iface=(self._host, self._port))
        await udp_transport._lport
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
```

- [ ] **Step 2: Run emulator tests — all should pass**

```
cd emulator && uv run pytest tests/test_emulator.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add emulator/emulator/_core.py emulator/tests/test_emulator.py
git commit -m "feat(emulator): replace SNMPv2c with SNMPv3 authNoPriv/MD5"
```

---

### Task 3: Update `SnmpProber` constructor

**Files:**
- Modify: `trouble-shooter/tests/unit/test_prober_bulk_walk.py` (one line)
- Modify: `trouble-shooter/src/trouble_shooter/detector/prober.py`

- [ ] **Step 1: Write failing test — update `_make_prober` in unit tests**

In `trouble-shooter/tests/unit/test_prober_bulk_walk.py`, change line 37:
```python
# Before:
def _make_prober() -> SnmpProber:
    return SnmpProber("127.0.0.1", "public", 161, timeout=1.0, retries=0)

# After:
def _make_prober() -> SnmpProber:
    return SnmpProber("127.0.0.1", "monitor", 161, auth_password="authpass1", timeout=1.0, retries=0)
```

- [ ] **Step 2: Run unit tests — expect TypeError**

```
cd trouble-shooter && uv run pytest tests/unit/test_prober_bulk_walk.py -v
```

Expected: all 4 tests FAIL with `TypeError: __init__() missing 1 required positional argument: 'auth_password'`

- [ ] **Step 3: Update `prober.py`**

Replace the entire `prober.py`:

```python
from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING

from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_cmd,
    get_cmd,
    usmHMACMD5AuthProtocol,
)
from pysnmp.proto.errind import EmptyResponse
from pysnmp.proto.rfc1905 import EndOfMibView

from .models import Batch, Sample

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class SnmpProber:
    def __init__(
        self,
        host: str,
        username: str,
        port: int,
        auth_password: str,
        timeout: float = 5.0,
        retries: int = 2,
    ) -> None:
        self._host = host
        self._username = username
        self._port = port
        self._auth_password = auth_password
        self._timeout = timeout
        self._retries = retries

    def _auth(self) -> UsmUserData:
        return UsmUserData(
            self._username,
            authKey=self._auth_password,
            authProtocol=usmHMACMD5AuthProtocol,
        )

    async def bulk_walk(self, root_oid: str, bulk_size: int) -> AsyncGenerator[Batch]:
        engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )
        try:
            cursor = root_oid
            while True:
                t0 = monotonic()
                error_indication, _status, _index, var_binds = await bulk_cmd(
                    engine,
                    self._auth(),
                    transport,
                    ContextData(),
                    0,
                    bulk_size,
                    ObjectType(ObjectIdentity(cursor)),
                    lookupMib=False,
                )
                elapsed_ms = (monotonic() - t0) * 1000

                if error_indication:
                    if isinstance(error_indication, EmptyResponse):
                        return
                    yield Batch(oids=[(cursor, "")], elapsed_ms=elapsed_ms, timed_out=True)
                    return

                if not var_binds:
                    return

                end_of_mib = any(isinstance(vb[1], EndOfMibView) for vb in var_binds)
                real_vbs = [vb for vb in var_binds if not isinstance(vb[1], EndOfMibView)]

                if not real_vbs:
                    return

                oids = [(str(vb[0]), str(vb[1])) for vb in real_vbs]
                yield Batch(oids=oids, elapsed_ms=elapsed_ms, timed_out=False)

                if end_of_mib:
                    return

                cursor = str(real_vbs[-1][0])
        finally:
            engine.close_dispatcher()

    async def probe_oid(self, oid: str) -> Sample:
        engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )
        try:
            t0 = monotonic()
            error_indication, _status, _index, var_binds = await get_cmd(
                engine,
                self._auth(),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lookupMib=False,
            )
            elapsed_ms = (monotonic() - t0) * 1000

            if error_indication or not var_binds:
                return Sample(oid=oid, value="", elapsed_ms=elapsed_ms, responded=False)

            return Sample(
                oid=oid,
                value=str(var_binds[0][1]),
                elapsed_ms=elapsed_ms,
                responded=True,
            )
        finally:
            engine.close_dispatcher()
```

- [ ] **Step 4: Run unit tests — all should pass**

```
cd trouble-shooter && uv run pytest tests/unit/test_prober_bulk_walk.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add trouble-shooter/src/trouble_shooter/detector/prober.py \
        trouble-shooter/tests/unit/test_prober_bulk_walk.py
git commit -m "feat(prober): replace CommunityData with UsmUserData authNoPriv/MD5"
```

---

### Task 4: Update integration test fixtures and prober tests

**Files:**
- Modify: `trouble-shooter/tests/integration/conftest.py`
- Modify: `trouble-shooter/tests/integration/test_prober.py`

- [ ] **Step 1: Update `conftest.py`**

Replace the full file:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from emulator import EmulatorConfig, EmulatorServer
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Generator

from trouble_shooter.main import app

_FAST_CONFIG = EmulatorConfig(username="monitor", auth_password="authpass1", slow_prefixes=(), slow_delay=0.0)
_SLOW_CONFIG = EmulatorConfig(
    username="monitor", auth_password="authpass1",
    slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.05, n_interfaces=1,
)


@pytest.fixture(scope="session")
def _fast_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_FAST_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _slow_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_SLOW_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def emulator_fast(_fast_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _fast_server
    _fast_server.reset()


@pytest.fixture
def emulator_slow(_slow_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _slow_server
    _slow_server.reset()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


# --- detector emulators ---

_CLEAN_CONFIG = EmulatorConfig(username="monitor", auth_password="authpass1", slow_prefixes=(), slow_delay=0.0)
_SLOW_IF_CONFIG = EmulatorConfig(
    username="monitor", auth_password="authpass1",
    slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.8, n_interfaces=1,
)
_DROP_IF_CONFIG = EmulatorConfig(
    username="monitor", auth_password="authpass1",
    slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=10.0,
)


@pytest.fixture(scope="session")
def _clean_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_CLEAN_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _slow_if_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_SLOW_IF_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _drop_if_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_DROP_IF_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def emulator_clean(_clean_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _clean_server
    _clean_server.reset()


@pytest.fixture
def emulator_slow_if(_slow_if_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _slow_if_server
    _slow_if_server.reset()


@pytest.fixture
def emulator_drop_if(_drop_if_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _drop_if_server
    _drop_if_server.reset()
```

- [ ] **Step 2: Update `test_prober.py` — replace all `SnmpProber("127.0.0.1", "public", ...)` calls**

Replace the full file:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from trouble_shooter.detector.prober import SnmpProber

if TYPE_CHECKING:
    from emulator import EmulatorServer

    from trouble_shooter.detector.models import Batch

_USER = "monitor"
_PASS = "authpass1"


async def test_bulk_walk_yields_batches_for_clean_device(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber("127.0.0.1", _USER, emulator_clean.port, auth_password=_PASS, timeout=2.0, retries=1)
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    assert len(batches) > 0
    assert not any(b.timed_out for b in batches)
    all_oids = [oid for b in batches for oid, _ in b.oids]
    assert any("1.3.6.1.2.1.1" in oid for oid in all_oids), "system group missing"
    assert any("1.3.6.1.2.1.2.2.1" in oid for oid in all_oids), "ifTable missing"


async def test_bulk_walk_all_batches_have_non_negative_elapsed_ms(
    emulator_clean: EmulatorServer,
) -> None:
    prober = SnmpProber("127.0.0.1", _USER, emulator_clean.port, auth_password=_PASS, timeout=2.0, retries=1)
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    assert all(b.elapsed_ms >= 0 for b in batches)


async def test_bulk_walk_slow_subtree_has_high_elapsed_ms(emulator_slow_if: EmulatorServer) -> None:
    # emulator has slow_delay=0.8s on ifTable; prober timeout=3s so it responds
    prober = SnmpProber("127.0.0.1", _USER, emulator_slow_if.port, auth_password=_PASS, timeout=3.0, retries=0)
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    slow_batches = [b for b in batches if any("1.3.6.1.2.1.2.2.1" in oid for oid, _ in b.oids)]
    assert len(slow_batches) > 0
    assert any(b.elapsed_ms >= 700 for b in slow_batches)


async def test_bulk_walk_yields_timed_out_batch_when_dropped(
    emulator_drop_if: EmulatorServer,
) -> None:
    # emulator has slow_delay=10s on ifTable; prober timeout=1s so it times out
    prober = SnmpProber("127.0.0.1", _USER, emulator_drop_if.port, auth_password=_PASS, timeout=1.0, retries=0)
    batches: list[Batch] = []
    async for batch in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10):
        batches.append(batch)
        if batch.timed_out:
            break
    assert any(b.timed_out for b in batches)


async def test_probe_oid_returns_responded_sample(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber("127.0.0.1", _USER, emulator_clean.port, auth_password=_PASS, timeout=2.0, retries=1)
    sample = await prober.probe_oid("1.3.6.1.2.1.1.1.0")
    assert sample.responded is True
    assert sample.oid == "1.3.6.1.2.1.1.1.0"
    assert "Emulated" in sample.value
    assert sample.elapsed_ms >= 0


async def test_probe_oid_returns_unresponded_sample_on_timeout(
    emulator_drop_if: EmulatorServer,
) -> None:
    prober = SnmpProber("127.0.0.1", _USER, emulator_drop_if.port, auth_password=_PASS, timeout=1.0, retries=0)
    sample = await prober.probe_oid("1.3.6.1.2.1.2.2.1.1.1")
    assert sample.responded is False
```

- [ ] **Step 3: Run integration prober tests**

```
cd trouble-shooter && uv run pytest tests/integration/test_prober.py -v
```

Expected: all 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add trouble-shooter/tests/integration/conftest.py \
        trouble-shooter/tests/integration/test_prober.py
git commit -m "test(trouble-shooter): update fixtures and prober tests for SNMPv3"
```

---

### Task 5: Update `main.py` and API integration tests

**Files:**
- Modify: `trouble-shooter/src/trouble_shooter/main.py`
- Modify: `trouble-shooter/tests/integration/test_check.py`
- Modify: `trouble-shooter/tests/integration/test_walk.py`
- Modify: `trouble-shooter/tests/integration/test_api_diagnose.py`

- [ ] **Step 1: Update API tests first (failing)**

Replace `trouble-shooter/tests/integration/test_check.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulator import EmulatorServer
    from starlette.testclient import TestClient

_CREDS = {"username": "monitor", "auth_password": "authpass1"}


def test_check_reachable_device(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/check",
        json={"host": "127.0.0.1", "port": emulator_fast.port, **_CREDS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["snmp"]["reachable"] is True
    assert "Emulated" in data["snmp"]["sysDescr"]


def test_check_wrong_credentials(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/check",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "username": "unknown",
            "auth_password": "authpass1",
            "timeout": 0.5,
            "retries": 0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_unreachable_port(client: TestClient) -> None:
    resp = client.post(
        "/api/check",
        json={"host": "127.0.0.1", "port": 19999, "timeout": 0.3, "retries": 0, **_CREDS},
    )
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_invalid_host(client: TestClient) -> None:
    resp = client.post(
        "/api/check",
        json={"host": "not_a_host!!", "port": 1161, **_CREDS},
    )
    assert resp.status_code == 400
```

Replace `trouble-shooter/tests/integration/test_walk.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulator import EmulatorServer
    from starlette.testclient import TestClient

_CREDS = {"username": "monitor", "auth_password": "authpass1"}


def test_walk_returns_oids(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/walk",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "root_oid": "1.3.6.1.2.1.1",
            "timeout": 2,
            "total_timeout": 10,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    oids = resp.json()["oids"]
    assert len(oids) > 0
    assert all("oid" in o and "value" in o and "ms" in o for o in oids)


def test_walk_covers_system_and_interface_groups(
    client: TestClient, emulator_fast: EmulatorServer
) -> None:
    resp = client.post(
        "/api/walk",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "root_oid": "1.3.6.1.2.1",
            "timeout": 2,
            "total_timeout": 10,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    oid_strings = {o["oid"] for o in resp.json()["oids"]}
    assert any("1.3.6.1.2.1.1" in oid for oid in oid_strings), "system group missing"
    assert any("1.3.6.1.2.1.2" in oid for oid in oid_strings), "interface group missing"


def test_walk_slow_subtree_takes_longer(client: TestClient, emulator_slow: EmulatorServer) -> None:
    resp = client.post(
        "/api/walk",
        json={
            "host": "127.0.0.1",
            "port": emulator_slow.port,
            "root_oid": "1.3.6.1.2.1",
            "timeout": 5,
            "total_timeout": 30,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    oids = resp.json()["oids"]
    slow_oids = [o for o in oids if "1.3.6.1.2.1.2.2" in o["oid"]]
    assert len(slow_oids) > 0
    assert any(o["ms"] >= 40 for o in slow_oids), "expected slow OIDs to take >=40ms"


def test_walk_total_timeout_returns_empty(
    client: TestClient, emulator_fast: EmulatorServer
) -> None:
    resp = client.post(
        "/api/walk",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "root_oid": "1.3.6.1.2.1",
            "timeout": 1,
            "total_timeout": 0,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["oids"] == []


def test_walk_invalid_host(client: TestClient) -> None:
    resp = client.post(
        "/api/walk",
        json={"host": "not_valid!!", "port": 1161, "root_oid": "1.3.6.1.2.1", **_CREDS},
    )
    assert resp.status_code == 400
```

Replace `trouble-shooter/tests/integration/test_api_diagnose.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulator import EmulatorServer
    from starlette.testclient import TestClient

_CREDS = {"username": "monitor", "auth_password": "authpass1"}
_BUCKETS = [
    {"name": "OK", "max_ms": 500},
    {"name": "SLOW", "max_ms": 3000},
    {"name": "CRITICAL", "max_ms": None},
]


def test_diagnose_endpoint_returns_valid_report(
    client: TestClient, emulator_clean: EmulatorServer
) -> None:
    resp = client.post(
        "/api/diagnose",
        json={
            "host": "127.0.0.1",
            "port": emulator_clean.port,
            "root_oid": "1.3.6.1.2.1.1",
            "bulk_size": 10,
            "timeout": 2.0,
            "retries": 1,
            "total_timeout": 30.0,
            "pinpoint": False,
            "buckets": _BUCKETS,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["complete"] is True
    assert data["reason"] == "END_OF_MIB"
    assert "summary" in data
    assert "regions" in data
    assert "oids" in data
    assert "elapsed_total_ms" in data
    assert len(data["oids"]) > 0


def test_diagnose_endpoint_invalid_host(client: TestClient) -> None:
    resp = client.post(
        "/api/diagnose",
        json={
            "host": "not_valid!!",
            "port": 1161,
            "buckets": [{"name": "OK", "max_ms": 500}, {"name": "CRIT", "max_ms": None}],
            **_CREDS,
        },
    )
    assert resp.status_code == 400


def test_diagnose_endpoint_region_excludes_oids_field(
    client: TestClient, emulator_clean: EmulatorServer
) -> None:
    resp = client.post(
        "/api/diagnose",
        json={
            "host": "127.0.0.1",
            "port": emulator_clean.port,
            "root_oid": "1.3.6.1.2.1.1",
            "bulk_size": 10,
            "timeout": 2.0,
            "retries": 1,
            "total_timeout": 30.0,
            "pinpoint": False,
            "buckets": _BUCKETS,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    for region in resp.json()["regions"]:
        assert "prefix" in region
        assert "bucket" in region
        assert "batch_ms" in region
        assert "oid_count" in region
        assert "oids" not in region
```

- [ ] **Step 2: Run API tests — expect failures (422 Unprocessable Entity)**

```
cd trouble-shooter && uv run pytest tests/integration/test_check.py tests/integration/test_walk.py tests/integration/test_api_diagnose.py -v
```

Expected: failures because `main.py` still has `community` field (422 on new payloads, or 200 on old payloads that now fail validation).

- [ ] **Step 3: Update `main.py`**

Replace the full file:

```python
import asyncio
import ipaddress
import logging
import re
import subprocess
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    walk_cmd,
    usmHMACMD5AuthProtocol,
)

from trouble_shooter.detector import SnmpProber, diagnose
from trouble_shooter.detector.models import Bucket, DetectorConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/diagnose")
def diagnose_page() -> FileResponse:
    return FileResponse("static/diagnose.html")


class CheckRequest(BaseModel):
    host: str
    username: str
    auth_password: str
    port: int = 1161
    timeout: float = 2.0
    retries: int = 1


class WalkRequest(BaseModel):
    host: str
    username: str
    auth_password: str
    port: int = 1161
    root_oid: str = "1.3.6.1.2.1"
    timeout: int = 5
    total_timeout: int = 30


class BucketSpec(BaseModel):
    name: str
    max_ms: int | None = None


class DiagnoseRequest(BaseModel):
    host: str
    username: str
    auth_password: str
    port: int = 1161
    root_oid: str = "1.3.6.1.2.1"
    bulk_size: int = 10
    timeout: float = 5.0
    retries: int = 2
    total_timeout: float = 60.0
    pinpoint: bool = True
    buckets: list[BucketSpec] = Field(
        default_factory=lambda: [
            BucketSpec(name="OK", max_ms=500),
            BucketSpec(name="SLOW", max_ms=3000),
            BucketSpec(name="CRITICAL", max_ms=None),
        ]
    )


@app.post("/api/walk")
async def walk_device(req: WalkRequest) -> dict[str, list[dict[str, str | int]]]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    oids = await _snmp_walk(
        req.host, req.username, req.auth_password, req.port, req.root_oid, req.timeout, req.total_timeout
    )
    return {"oids": oids}


@app.post("/api/diagnose")
async def diagnose_device(req: DiagnoseRequest) -> dict[str, object]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    prober = SnmpProber(req.host, req.username, req.port, req.auth_password, req.timeout, req.retries)
    buckets = [Bucket(name=b.name, max_ms=b.max_ms) for b in req.buckets]
    config = DetectorConfig(
        root_oid=req.root_oid,
        bulk_size=req.bulk_size,
        timeout=req.timeout,
        retries=req.retries,
        total_timeout=req.total_timeout,
        pinpoint=req.pinpoint,
    )
    report = await diagnose(prober, buckets=buckets, config=config)
    return {
        "complete": report.complete,
        "stopped_at": report.stopped_at,
        "reason": report.reason.value,
        "summary": report.summary,
        "regions": [
            {
                "prefix": r.prefix,
                "bucket": r.bucket,
                "batch_ms": r.batch_ms,
                "oid_count": r.oid_count,
            }
            for r in report.regions
        ],
        "oids": [
            {"oid": o.oid, "value": o.value, "bucket": o.bucket, "ms": o.ms, "phase": o.phase}
            for o in report.oids
        ],
        "elapsed_total_ms": report.elapsed_total_ms,
    }


@app.post("/api/check")
async def check_device(req: CheckRequest) -> dict[str, object]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    ping_ok = _ping(req.host)
    snmp = await _snmp_get(req.host, req.username, req.auth_password, req.port, req.timeout, req.retries)
    return {"host": req.host, "ping": ping_ok, "snmp": snmp}


def _valid_host(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return bool(re.fullmatch(r"[A-Za-z0-9.-]{1,253}", h)) and not h.startswith("-")


def _ping(host: str) -> bool:
    if not _valid_host(host):
        return False
    result = subprocess.run(
        ["/usr/bin/ping", "-c", "1", "-W", "2", "--", host],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _auth(username: str, auth_password: str) -> UsmUserData:
    return UsmUserData(username, authKey=auth_password, authProtocol=usmHMACMD5AuthProtocol)


async def _snmp_get(
    host: str, username: str, auth_password: str, port: int, timeout: float = 2.0, retries: int = 1
) -> dict[str, object]:
    engine = SnmpEngine()
    try:
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine,
            _auth(username, auth_password),
            await UdpTransportTarget.create((host, port), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity("SNMPv2-MIB", "sysDescr", 0)),
        )
    finally:
        engine.close_dispatcher()

    if error_indication:
        return {"reachable": False, "error": str(error_indication)}
    if error_status:
        return {
            "reachable": False,
            "error": f"{error_status} at index {error_index}",
        }

    sys_descr = str(var_binds[0][1])
    return {"reachable": True, "sysDescr": sys_descr}


async def _snmp_walk(
    host: str,
    username: str,
    auth_password: str,
    port: int,
    root_oid: str,
    timeout: int = 5,
    total_timeout: int = 30,
) -> list[dict[str, str | int]]:
    engine = SnmpEngine()
    results = []
    try:
        async with asyncio.timeout(total_timeout):
            t = time.monotonic()
            async for error_indication, error_status, _, var_binds in walk_cmd(
                engine,
                _auth(username, auth_password),
                await UdpTransportTarget.create((host, port), timeout=timeout, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(root_oid)),
            ):
                elapsed_ms = round((time.monotonic() - t) * 1000)
                t = time.monotonic()
                if error_indication:
                    break
                if error_status and int(error_status):
                    break
                results.extend(
                    {"oid": str(var_bind[0]), "value": str(var_bind[1]), "ms": elapsed_ms}
                    for var_bind in var_binds
                )
    except TimeoutError:
        pass
    finally:
        engine.close_dispatcher()
    return results


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("trouble_shooter.main:app", host="0.0.0.0", port=8080, reload=True)
```

- [ ] **Step 4: Run all API tests**

```
cd trouble-shooter && uv run pytest tests/integration/test_check.py tests/integration/test_walk.py tests/integration/test_api_diagnose.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add trouble-shooter/src/trouble_shooter/main.py \
        trouble-shooter/tests/integration/test_check.py \
        trouble-shooter/tests/integration/test_walk.py \
        trouble-shooter/tests/integration/test_api_diagnose.py
git commit -m "feat(api): replace community auth with SNMPv3 username/auth_password"
```

---

### Task 6: Full CI on both packages

- [ ] **Step 1: Run emulator CI**

```
cd emulator && just ci
```

Expected: format → lint → type-check → tests all pass.

- [ ] **Step 2: Run trouble-shooter CI**

```
cd trouble-shooter && just ci
```

Expected: format → lint → type-check → tests all pass.

- [ ] **Step 3: Fix any lint/type issues found**

Common issues to expect:
- Ruff may flag unused imports (e.g. old `CommunityData` import if left in a file)
- Pyright may flag `udp_transport._lport` as accessing a private attribute — if so, suppress with `# type: ignore`
- Pyright may flag `udp_transport.transport` as `None | DatagramTransport` — if so, add `assert udp_transport.transport is not None` before the `get_extra_info` call

- [ ] **Step 4: Commit any lint/type fixes**

```bash
git add -p  # stage only the relevant files
git commit -m "fix: resolve lint and type issues from SNMPv3 migration"
```
