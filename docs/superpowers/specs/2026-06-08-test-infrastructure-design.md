# Test Infrastructure Design

**Date:** 2026-06-08  
**Scope:** SNMP emulator + trouble-shooter — fast e2e test setup with shared manual-testing infrastructure

---

## Problem

The current setup has no automated tests. The development loop is manual: start emulator, hit API, inspect results. Two specific blockers:

1. **Emulator is hard-coded** — all config (slow prefixes, delay, interface count, community) is baked into `mibs.py`. No way to configure per-device or per-test.
2. **No abort mechanism** — once a slow walk is in flight, the emulator keeps sleeping and sending UDP replies even after the client has moved on. This makes shared emulator instances unreliable across tests.

---

## Goals

- `pytest` runs fast end-to-end tests against real SNMP over real UDP
- Same emulator instances usable for manual testing by humans (via containers)
- Claude can run `uv run pytest` and get a reliable result in seconds
- Emulator config is expressed as Python objects — easy to parametrize in tests

---

## Architecture

### Repository structure

```
hackathon/
  pyproject.toml              ← uv workspace root
  emulator/
    emulator/                 ← importable Python package
      __init__.py             ← public API: EmulatorConfig, EmulatorServer
      _core.py                ← UDP server logic (extracted from snmp_emulator.py)
      _mibs.py                ← OID tree builder (was mibs.py)
    snmp_emulator.py          ← thin __main__ wrapper (unchanged for containers)
    Containerfile             ← unchanged
    pods.yaml                 ← unchanged
    Justfile                  ← unchanged
    pyproject.toml            ← add package discovery for emulator/
  trouble-shooter/
    tests/
      conftest.py             ← session-scoped emulator fixtures
      test_walk.py
      test_check.py
    main.py                   ← unchanged
    pyproject.toml            ← add dev deps: emulator (workspace), pytest, httpx
```

### uv workspace

`hackathon/pyproject.toml`:
```toml
[tool.uv.workspace]
members = ["emulator", "trouble-shooter"]
```

`trouble-shooter/pyproject.toml` (additions):
```toml
[dependency-groups]
dev = ["emulator", "pytest", "httpx"]

[tool.uv.sources]
emulator = { workspace = true }
```

---

## Emulator library

### EmulatorConfig

```python
@dataclass
class EmulatorConfig:
    community: str = "public"
    slow_prefixes: tuple[str, ...] = ("1.3.6.1.2.1.2.2.1",)
    slow_delay: float = 3.0
    n_interfaces: int = 4
```

### EmulatorServer

```python
class EmulatorServer:
    def __init__(self, config: EmulatorConfig, port: int = 0): ...

    @property
    def port(self) -> int: ...   # actual bound port — useful when port=0

    def start(self) -> None: ... # bind UDP socket, start background thread
    def stop(self) -> None: ...  # close socket, join thread
    def reset(self) -> None: ... # drop in-flight, reopen socket on same port
```

**reset() mechanism:**
1. Sets a `threading.Event` that the slow-delay sleep checks — interrupts any in-progress sleep immediately
2. Closes the UDP socket — unblocks `recvfrom` in the loop thread
3. Reopens a new socket on the same port
4. Clears the event so subsequent requests behave normally

Using `port=0` lets the OS assign a free port, avoiding conflicts when two emulator instances run in the same session.

### snmp_emulator.py (unchanged externally)

Becomes a thin wrapper:
```python
if __name__ == "__main__":
    config = EmulatorConfig(
        community=os.environ.get("SNMP_COMMUNITY", "public"),
        slow_delay=float(os.environ.get("SLOW_DELAY", "3.0")),
        ...
    )
    server = EmulatorServer(config, port=int(os.environ.get("SNMP_PORT", "1161")))
    server.start()
    # wait for signal
```

Container builds and `just run-dev` continue working without changes.

---

## Test fixtures

```python
# tests/conftest.py
from emulator import EmulatorConfig, EmulatorServer

FAST = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
SLOW = EmulatorConfig(slow_delay=0.05)   # short delay — exercises slow path without 3s waits

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
```

Two session-scoped emulators start once at the beginning of the run. The `autouse` function-scoped fixture calls `reset()` after every test, dropping any in-flight UDP replies before the next test begins.

Tests receive the server object to build their requests:

```python
async def test_walk_returns_oids(emulator_fast, async_client):
    resp = await async_client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
    })
    assert resp.status_code == 200
    assert len(resp.json()["oids"]) > 0
```

---

## Manual testing (humans)

The container setup (`pods.yaml`, `Justfile`, `Containerfile`) is **unchanged**. `snmp_emulator.py` remains the container entrypoint. Humans use `just containers-start` to get two emulated devices on `127.0.0.2:1161` and `127.0.0.3:1161` and point the trouble-shooter UI at them.

The emulator code is shared — the container runs the same `EmulatorServer` logic that tests use, just wrapped differently.

---

## Running tests

```bash
# from workspace root or trouble-shooter/
uv run pytest

# with output
uv run pytest -v

# single test file
uv run pytest tests/test_walk.py
```

No external services required. Both emulators start in-process at session start.

---

## Out of scope

- OID exclude ranges and bulk size config in the trouble-shooter (separate feature)
- Multi-device scenarios beyond fast/slow profiles (add named profiles as needed)
- CI integration (follows naturally from `uv run pytest` working locally)
