# Test Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the SNMP emulator into an importable Python library and wire up a pytest suite in trouble-shooter that runs fast end-to-end tests over real UDP — shared setup for both Claude and human developers.

**Architecture:** The emulator project grows an `emulator/` package alongside `snmp_emulator.py` (which becomes a thin wrapper for container/manual use). A uv workspace at the repo root lets trouble-shooter declare the emulator as a dev dependency. Pytest fixtures start two session-scoped `EmulatorServer` instances (fast and slow) and call `reset()` after each test to drop any in-flight UDP replies.

**Tech Stack:** Python 3.12+, uv workspaces, pytest, httpx, pysnmp, FastAPI TestClient

---

## File map

**Create:**
- `hackathon/pyproject.toml` — uv workspace root
- `emulator/emulator/__init__.py` — exports `EmulatorConfig`, `EmulatorServer`
- `emulator/emulator/_core.py` — `EmulatorConfig` dataclass + `EmulatorServer` class (all UDP logic)
- `emulator/emulator/_mibs.py` — OID tree builder, extracted from `mibs.py` with `n_interfaces` param
- `trouble-shooter/tests/__init__.py` — empty, marks tests as a package
- `trouble-shooter/tests/conftest.py` — session emulator fixtures + FastAPI client
- `trouble-shooter/tests/test_emulator.py` — direct EmulatorServer unit tests
- `trouble-shooter/tests/test_check.py` — `/api/check` endpoint tests
- `trouble-shooter/tests/test_walk.py` — `/api/walk` endpoint tests

**Modify:**
- `emulator/pyproject.toml` — add `[build-system]` block
- `emulator/Containerfile` — copy `emulator/` package instead of `mibs.py`
- `emulator/snmp_emulator.py` — rewrite as thin wrapper using `EmulatorServer`
- `trouble-shooter/pyproject.toml` — add dev deps and pytest config

**Delete:**
- `emulator/mibs.py` — replaced by `emulator/emulator/_mibs.py`

---

## Task 1: uv workspace + emulator package skeleton

**Files:**
- Create: `hackathon/pyproject.toml`
- Create: `emulator/emulator/__init__.py`
- Create: `emulator/emulator/_mibs.py`
- Modify: `emulator/pyproject.toml`

- [ ] **Step 1: Create workspace root**

Create `hackathon/pyproject.toml`:
```toml
[tool.uv.workspace]
members = ["emulator", "trouble-shooter"]
```

- [ ] **Step 2: Add build-system to emulator**

Edit `emulator/pyproject.toml` to add:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Full file after edit:
```toml
[project]
name = "emulator"
version = "0.1.0"
description = "SNMP device emulator"
requires-python = ">=3.12"
dependencies = [
    "pysnmp>=7.1.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Create the emulator Python package**

Create `emulator/emulator/__init__.py` (empty for now):
```python
```

- [ ] **Step 4: Create _mibs.py (parameterized OID tree builder)**

Create `emulator/emulator/_mibs.py`:
```python
from pysnmp.proto import rfc1902


def build_oid_tree(n_interfaces: int = 4) -> dict:
    data = {}

    # system group (fast)
    data[(1,3,6,1,2,1,1,1,0)] = rfc1902.OctetString("Emulated Slow SNMP Device; Cisco IOS 15.2 (emulated)")
    data[(1,3,6,1,2,1,1,2,0)] = rfc1902.ObjectIdentifier((1,3,6,1,4,1,9,1,1))
    data[(1,3,6,1,2,1,1,4,0)] = rfc1902.OctetString("noc@example.com")
    data[(1,3,6,1,2,1,1,5,0)] = rfc1902.OctetString("slow-router.example.com")
    data[(1,3,6,1,2,1,1,6,0)] = rfc1902.OctetString("Lab, Rack 1, Unit 3")
    data[(1,3,6,1,2,1,1,7,0)] = rfc1902.Integer32(78)

    data[(1,3,6,1,2,1,2,1,0)] = rfc1902.Integer32(n_interfaces)

    for idx in range(1, n_interfaces + 1):
        p = (1,3,6,1,2,1,2,2,1)
        data[p + (1,  idx)] = rfc1902.Integer32(idx)
        data[p + (2,  idx)] = rfc1902.OctetString(f"GigabitEthernet0/{idx - 1}")
        data[p + (3,  idx)] = rfc1902.Integer32(6)
        data[p + (4,  idx)] = rfc1902.Integer32(1500)
        data[p + (5,  idx)] = rfc1902.Gauge32(1_000_000_000)
        data[p + (6,  idx)] = rfc1902.OctetString(bytes([0x00, 0x11, 0x22, 0x33, 0x44, idx]))
        data[p + (7,  idx)] = rfc1902.Integer32(1)
        data[p + (8,  idx)] = rfc1902.Integer32(1)
        data[p + (9,  idx)] = rfc1902.TimeTicks(0)
        data[p + (10, idx)] = rfc1902.Counter32(idx * 1_234_567)
        data[p + (11, idx)] = rfc1902.Counter32(idx * 8_901)
        data[p + (12, idx)] = rfc1902.Counter32(0)
        data[p + (13, idx)] = rfc1902.Counter32(0)
        data[p + (14, idx)] = rfc1902.Counter32(0)
        data[p + (15, idx)] = rfc1902.Counter32(0)
        data[p + (16, idx)] = rfc1902.Counter32(idx * 987_654)
        data[p + (17, idx)] = rfc1902.Counter32(idx * 7_432)
        data[p + (18, idx)] = rfc1902.Counter32(0)
        data[p + (19, idx)] = rfc1902.Counter32(0)
        data[p + (20, idx)] = rfc1902.Counter32(0)
        data[p + (21, idx)] = rfc1902.Gauge32(0)
        data[p + (22, idx)] = rfc1902.ObjectIdentifier((1,3,6,1,2,1,10,7,1))

    return dict(sorted(data.items()))
```

- [ ] **Step 5: Sync workspace and verify**

```bash
cd /home/max/work/hackathon && uv sync
```

Expected: resolves both workspace members without error.

- [ ] **Step 6: Verify existing emulator still works**

```bash
cd /home/max/work/hackathon/emulator && uv run python snmp_emulator.py &
sleep 1
snmpget -v2c -c public 127.0.0.1:1161 1.3.6.1.2.1.1.1.0
kill %1
```

Expected: sysDescr value printed. (`mibs.py` still exists and imports still work.)

- [ ] **Step 7: Commit**

```bash
git add hackathon/pyproject.toml emulator/emulator/__init__.py emulator/emulator/_mibs.py emulator/pyproject.toml
git commit -m "feat: add uv workspace root and emulator package skeleton with _mibs.py"
```

---

## Task 2: trouble-shooter test environment

**Files:**
- Modify: `trouble-shooter/pyproject.toml`
- Create: `trouble-shooter/tests/__init__.py`

- [ ] **Step 1: Add dev deps and pytest config to trouble-shooter**

Edit `trouble-shooter/pyproject.toml`:
```toml
[project]
name = "trouble-shooter"
version = "0.1.0"
description = "SNMP Troubleshooter"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "pysnmp>=7.1.27",
    "uvicorn[standard]",
]

[dependency-groups]
dev = ["emulator", "pytest", "httpx"]

[tool.uv.sources]
emulator = { workspace = true }

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create tests package**

Create `trouble-shooter/tests/__init__.py` (empty file).

- [ ] **Step 3: Sync and verify**

```bash
cd /home/max/work/hackathon && uv sync
```

Expected: `emulator` package listed as installed in trouble-shooter's environment.

- [ ] **Step 4: Verify emulator is importable from trouble-shooter**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run python -c "from emulator import EmulatorConfig; print('ok')"
```

Expected: prints `ok`. (EmulatorConfig doesn't exist yet — this will fail. That's the failing test we'll fix in Task 3.)

Note: this command is expected to FAIL at this point — it confirms the import path is correct but the symbol isn't defined yet.

- [ ] **Step 5: Commit**

```bash
git add trouble-shooter/pyproject.toml trouble-shooter/tests/__init__.py
git commit -m "feat: add trouble-shooter test env with emulator workspace dep"
```

---

## Task 3: EmulatorServer start/stop (TDD)

**Files:**
- Create: `trouble-shooter/tests/test_emulator.py`
- Create: `emulator/emulator/_core.py`
- Modify: `emulator/emulator/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `trouble-shooter/tests/test_emulator.py`:
```python
import asyncio
import threading
import time

import pytest
from emulator import EmulatorConfig, EmulatorServer
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData, ContextData, ObjectIdentity, ObjectType,
    SnmpEngine, UdpTransportTarget, get_cmd,
)


async def _snmp_get(port: int, oid: str, community: str = "public", timeout: float = 1.0):
    engine = SnmpEngine()
    try:
        err, status, _, var_binds = await get_cmd(
            engine,
            CommunityData(community),
            await UdpTransportTarget.create(("127.0.0.1", port), timeout=timeout, retries=0),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        return err, var_binds
    finally:
        engine.close_dispatcher()


def test_server_responds_to_snmp_get():
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0"))
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


def test_server_port_is_assigned_when_zero():
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config, port=0)
    server.start()
    try:
        assert server.port > 0
    finally:
        server.stop()


def test_server_uses_community_string():
    config = EmulatorConfig(community="secret", slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        # wrong community — should get no response (timeout error)
        err, _ = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0", community="wrong"))
        assert err is not None

        # correct community — should respond
        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0", community="secret"))
        assert err is None
    finally:
        server.stop()


def test_server_slow_prefix_adds_delay():
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.1)
    server = EmulatorServer(config)
    server.start()
    try:
        import time
        t = time.monotonic()
        err, _ = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.2.1.0", timeout=2.0))
        elapsed = time.monotonic() - t
        assert err is None
        assert elapsed >= 0.1
    finally:
        server.stop()
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_emulator.py -v
```

Expected: `ImportError: cannot import name 'EmulatorServer' from 'emulator'`

- [ ] **Step 3: Implement EmulatorConfig and EmulatorServer (start/stop)**

Create `emulator/emulator/_core.py`:
```python
import socket
import threading
import time
from dataclasses import dataclass

from pyasn1.codec.ber import decoder, encoder
from pyasn1.type.univ import ObjectIdentifier
from pysnmp.proto import api, rfc1902

from ._mibs import build_oid_tree

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
        self._oid_tree: dict = {}
        self._sorted_oids: list = []

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        self._oid_tree = build_oid_tree(self._config.n_interfaces)
        self._sorted_oids = sorted(self._oid_tree.keys())
        self._stop_event.clear()
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

    def _bind(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        self._port = sock.getsockname()[1]
        self._sock = sock

    def _close_sock(self) -> None:
        sock, self._sock = self._sock, None
        if sock:
            try:
                sock.close()
            except OSError:
                pass

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
            if resp is not None and not self._reset_event.is_set():
                try:
                    sock.sendto(resp, addr)
                except OSError:
                    pass

    def _lookup(self, oid_tuple: tuple):
        if oid_tuple == _SYSUPTIME_OID:
            return rfc1902.TimeTicks(int((time.monotonic() - _START_TIME) * 100))
        return self._oid_tree.get(oid_tuple)

    def _lookup_next(self, oid_tuple: tuple) -> tuple[tuple | None, object]:
        for oid in self._sorted_oids:
            if oid > oid_tuple:
                val = self._lookup(oid)
                if val is not None:
                    return oid, val
        return None, None

    def _is_slow(self, oid_tuple: tuple) -> bool:
        s = ".".join(map(str, oid_tuple))
        return any(s.startswith(p) for p in self._config.slow_prefixes)

    def _process(self, data: bytes, addr) -> bytes | None:
        try:
            ver = api.decodeMessageVersion(data)
            pMod = api.PROTOCOL_MODULES[ver]
            reqMsg, _ = decoder.decode(data, asn1Spec=pMod.Message())
        except Exception:
            return None

        if bytes(pMod.apiMessage.get_community(reqMsg)).decode() != self._config.community:
            return None

        reqPDU = pMod.apiMessage.get_pdu(reqMsg)
        pdu_name = reqPDU.__class__.__name__
        req_binds = pMod.apiPDU.get_varbinds(reqPDU)
        rsp_binds = []
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
                    break
                slow = slow or self._is_slow(next_oid)
                rsp_binds.append((ObjectIdentifier(next_oid), val))

        elif pdu_name == "GetBulkRequestPDU":
            non_rep = int(pMod.apiBulkPDU.get_non_repeaters(reqPDU))
            max_rep = int(pMod.apiBulkPDU.get_max_repetitions(reqPDU))
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

        if slow:
            self._reset_event.wait(timeout=self._config.slow_delay)
            if self._reset_event.is_set():
                return None

        rspMsg = pMod.apiMessage.get_response(reqMsg)
        rspPDU = pMod.apiMessage.get_pdu(rspMsg)
        pMod.apiPDU.set_varbinds(rspPDU, rsp_binds)
        pMod.apiPDU.set_error_status(rspPDU, 0)
        pMod.apiPDU.set_error_index(rspPDU, 0)
        return encoder.encode(rspMsg)
```

- [ ] **Step 4: Export from __init__.py**

Edit `emulator/emulator/__init__.py`:
```python
from ._core import EmulatorConfig, EmulatorServer

__all__ = ["EmulatorConfig", "EmulatorServer"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_emulator.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add emulator/emulator/_core.py emulator/emulator/__init__.py trouble-shooter/tests/test_emulator.py
git commit -m "feat: implement EmulatorServer start/stop with TDD"
```

---

## Task 4: EmulatorServer reset (TDD)

**Files:**
- Modify: `trouble-shooter/tests/test_emulator.py`
- Modify: `emulator/emulator/_core.py`

- [ ] **Step 1: Add reset tests to test_emulator.py**

Append to `trouble-shooter/tests/test_emulator.py`:
```python
def test_reset_server_still_responds_after_reset():
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        server.reset()
        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0"))
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


def test_reset_drops_in_flight_slow_response():
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.3)
    server = EmulatorServer(config)
    server.start()
    try:
        received = []

        def slow_get():
            err, var_binds = asyncio.run(
                _snmp_get(server.port, "1.3.6.1.2.1.2.1.0", timeout=1.0)
            )
            if err is None:
                received.append(var_binds)

        t = threading.Thread(target=slow_get)
        t.start()
        time.sleep(0.05)  # let request arrive at emulator before reset
        server.reset()
        t.join(timeout=1.5)

        assert received == [], "slow response should have been dropped by reset"

        # server works for new requests after reset
        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0"))
        assert err is None
    finally:
        server.stop()
```

`import threading` is already in `test_emulator.py` from Task 3. No import changes needed.

- [ ] **Step 2: Run to verify new tests fail**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_emulator.py::test_reset_server_still_responds_after_reset tests/test_emulator.py::test_reset_drops_in_flight_slow_response -v
```

Expected: FAILED — `EmulatorServer` has no `reset` method.

- [ ] **Step 3: Implement reset() in _core.py**

Add `reset()` and `_close_sock()` update to `EmulatorServer` in `emulator/emulator/_core.py`. Add this method after `stop()`:

```python
def reset(self) -> None:
    self._reset_event.set()
    self._close_sock()
    time.sleep(0.02)  # give loop thread time to see the closed socket
    self._reset_event.clear()
    self._bind()
```

- [ ] **Step 4: Run all emulator tests**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_emulator.py -v
```

Expected: 6 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add emulator/emulator/_core.py trouble-shooter/tests/test_emulator.py
git commit -m "feat: add EmulatorServer.reset() with in-flight drop"
```

---

## Task 5: Update snmp_emulator.py and Containerfile

**Files:**
- Modify: `emulator/snmp_emulator.py`
- Modify: `emulator/Containerfile`
- Delete: `emulator/mibs.py`

- [ ] **Step 1: Rewrite snmp_emulator.py as a thin wrapper**

Replace entire `emulator/snmp_emulator.py` with:
```python
#!/usr/bin/env python3
import os
import signal

from emulator import EmulatorConfig, EmulatorServer


def main() -> None:
    config = EmulatorConfig(
        community=os.environ.get("SNMP_COMMUNITY", "public"),
        slow_prefixes=(os.environ.get("SLOW_PREFIXES", "1.3.6.1.2.1.2.2.1"),),
        slow_delay=float(os.environ.get("SLOW_DELAY", "3.0")),
        n_interfaces=int(os.environ.get("N_INTERFACES", "4")),
    )
    host = os.environ.get("SNMP_HOST", "0.0.0.0")
    port = int(os.environ.get("SNMP_PORT", "1161"))

    server = EmulatorServer(config, port=port, host=host)
    server.start()
    print(f"SNMP emulator  udp://{host}:{server.port}  community={config.community}")
    print(f"Slow prefixes: {config.slow_prefixes}  delay={config.slow_delay}s")
    print(f"Interfaces: {config.n_interfaces}")
    print("Listening... (Ctrl-C to stop)")

    try:
        signal.pause()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.stop()
        print("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update Containerfile to copy the package**

Replace `emulator/Containerfile` with:
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY emulator/ ./emulator/
COPY snmp_emulator.py ./

ENV SNMP_PORT=1161 \
    SNMP_HOST=0.0.0.0 \
    SNMP_COMMUNITY=public

EXPOSE 1161/udp

CMD ["uv", "run", "python", "snmp_emulator.py"]
```

- [ ] **Step 3: Delete mibs.py**

```bash
rm /home/max/work/hackathon/emulator/mibs.py
```

- [ ] **Step 4: Verify local dev mode still works**

```bash
cd /home/max/work/hackathon/emulator && uv run python snmp_emulator.py &
sleep 1
snmpget -v2c -c public 127.0.0.1:1161 1.3.6.1.2.1.1.1.0
kill %1
```

Expected: sysDescr value printed.

- [ ] **Step 5: Commit**

```bash
git add emulator/snmp_emulator.py emulator/Containerfile
git rm emulator/mibs.py
git commit -m "refactor: snmp_emulator.py becomes thin wrapper; remove mibs.py"
```

---

## Task 6: conftest.py with session fixtures and FastAPI client

**Files:**
- Create: `trouble-shooter/tests/conftest.py`

- [ ] **Step 1: Write conftest.py**

Create `trouble-shooter/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient

from emulator import EmulatorConfig, EmulatorServer
from main import app

FAST = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
SLOW = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.05)


@pytest.fixture(scope="session")
def emulator_fast():
    s = EmulatorServer(FAST)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def emulator_slow():
    s = EmulatorServer(SLOW)
    s.start()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def reset_emulators(emulator_fast, emulator_slow):
    yield
    emulator_fast.reset()
    emulator_slow.reset()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
```

- [ ] **Step 2: Verify collection works**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest --collect-only
```

Expected: collects `test_emulator.py` tests, no import errors.

- [ ] **Step 3: Commit**

```bash
git add trouble-shooter/tests/conftest.py
git commit -m "feat: add session-scoped emulator fixtures and FastAPI test client"
```

---

## Task 7: test_check.py

**Files:**
- Create: `trouble-shooter/tests/test_check.py`

- [ ] **Step 1: Write failing tests**

Create `trouble-shooter/tests/test_check.py`:
```python
def test_check_reachable_device(client, emulator_fast):
    resp = client.post("/api/check", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["snmp"]["reachable"] is True
    assert "Emulated" in data["snmp"]["sysDescr"]


def test_check_wrong_community(client, emulator_fast):
    resp = client.post("/api/check", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "wrong",
    })
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_unreachable_port(client):
    resp = client.post("/api/check", json={
        "host": "127.0.0.1",
        "port": 19999,
        "community": "public",
    })
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_invalid_host(client):
    resp = client.post("/api/check", json={
        "host": "not_a_host!!",
        "community": "public",
        "port": 1161,
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_check.py -v
```

Expected: 4 tests PASSED. If any fail with an assertion error, there is a real bug in `main.py` — fix it before moving on. If there's an import error on `from main import app`, check that `pythonpath = ["."]` is set in pytest config (Task 2).

- [ ] **Step 3: Run all tests to verify they pass**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_check.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add trouble-shooter/tests/test_check.py
git commit -m "test: add /api/check endpoint tests"
```

---

## Task 8: test_walk.py

**Files:**
- Create: `trouble-shooter/tests/test_walk.py`

- [ ] **Step 1: Write failing tests**

Create `trouble-shooter/tests/test_walk.py`:
```python
def test_walk_returns_oids(client, emulator_fast):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1.1",
        "timeout": 2,
        "total_timeout": 10,
    })
    assert resp.status_code == 200
    oids = resp.json()["oids"]
    assert len(oids) > 0
    assert all("oid" in o and "value" in o and "ms" in o for o in oids)


def test_walk_covers_system_and_interface_groups(client, emulator_fast):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1",
        "timeout": 2,
        "total_timeout": 10,
    })
    assert resp.status_code == 200
    oid_strings = {o["oid"] for o in resp.json()["oids"]}
    assert any("1.3.6.1.2.1.1" in oid for oid in oid_strings), "system group missing"
    assert any("1.3.6.1.2.1.2" in oid for oid in oid_strings), "interface group missing"


def test_walk_slow_subtree_takes_longer(client, emulator_slow):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_slow.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1",
        "timeout": 5,
        "total_timeout": 30,
    })
    assert resp.status_code == 200
    oids = resp.json()["oids"]
    slow_oids = [o for o in oids if "1.3.6.1.2.1.2.2" in o["oid"]]
    assert len(slow_oids) > 0
    assert any(o["ms"] >= 40 for o in slow_oids), "expected slow OIDs to take >=40ms"


def test_walk_total_timeout_returns_empty(client, emulator_fast):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1",
        "timeout": 1,
        "total_timeout": 0,
    })
    assert resp.status_code == 200
    assert resp.json()["oids"] == []


def test_walk_invalid_host(client):
    resp = client.post("/api/walk", json={
        "host": "not_valid!!",
        "community": "public",
        "port": 1161,
        "root_oid": "1.3.6.1.2.1",
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/test_walk.py -v
```

Expected: FAILED or PASSED. If any fail, the test is surfacing a real bug — fix it in `main.py` before proceeding.

- [ ] **Step 3: Run the full suite**

```bash
cd /home/max/work/hackathon/trouble-shooter && uv run pytest -v
```

Expected: all tests in `test_emulator.py`, `test_check.py`, `test_walk.py` PASSED.

- [ ] **Step 4: Commit**

```bash
git add trouble-shooter/tests/test_walk.py
git commit -m "test: add /api/walk endpoint tests"
```
