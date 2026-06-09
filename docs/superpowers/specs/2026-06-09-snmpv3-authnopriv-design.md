# SNMPv3 authNoPriv (MD5) Design

**Date:** 2026-06-09  
**Scope:** Replace SNMPv2c community-string auth with SNMPv3 USM authNoPriv/MD5 across the emulator and trouble-shooter packages.

---

## Decision

- Security level: **authNoPriv** (username + HMAC-MD5 auth password, no encryption)
- Auth protocol: **MD5** (`USM_AUTH_HMAC96_MD5`)
- SNMPv2c is **removed** entirely; no dual-mode support
- Both emulator (for tests) and prober/API (for real devices) are updated

---

## Architecture

Three layers change; the OID tree and slow-region logic are untouched.

| Layer | Change |
|---|---|
| `emulator/_core.py` | Replace raw UDP loop + community check with pysnmp `SnmpEngine` + USM `CommandResponderBase` subclass. pysnmp handles auth, engine-ID discovery, and replay protection. |
| `prober.py` | Constructor: `community` → `username`, `auth_password`. `CommunityData(...)` → `UsmUserData(username, authKey, USM_AUTH_HMAC96_MD5)` in `bulk_walk` and `probe_oid`. |
| `main.py` + request models | `community` field → `username` + `auth_password` in all three request models. Same swap in `_snmp_get` and `_snmp_walk`. |
| `conftest.py` + tests | `EmulatorConfig` and `SnmpProber` calls updated to use `username`/`auth_password`. |

Engine-ID discovery (the unauthenticated Get/Report exchange SNMPv3 requires before first authenticated request) is handled automatically by pysnmp on both sides — no application code needed.

---

## Emulator (`emulator/_core.py`)

### EmulatorConfig

```python
@dataclass
class EmulatorConfig:
    username: str = "monitor"
    auth_password: str = "authpass1"   # min 8 chars for HMAC-MD5
    slow_prefixes: tuple[str, ...] = ("1.3.6.1.2.1.2.2.1.10", "1.3.6.1.2.1.2.2.1.16")
    slow_delay: float = 1.0
    n_interfaces: int = 4
```

### EmulatorServer threading model

`start()` creates a private asyncio event loop and starts a daemon thread running it. All pysnmp entity setup runs inside a `_setup()` coroutine scheduled on that loop. A `threading.Event` (`_ready`) signals the caller once the port is bound and known.

`stop()` calls `loop.call_soon_threadsafe(engine.close_dispatcher)` then joins the thread.

`reset()` is unchanged — it sets/clears `_reset_event` with a brief sleep for slow emulators.

### Setup sequence (inside `_setup()`)

1. `SnmpEngine()` — creates engine with auto-generated engine ID
2. `UdpAsyncioTransport(loop=loop).open_server_mode((host, port))` — returns immediately; stores a future (`_lport`)
3. `await transport._lport` — waits for `create_datagram_endpoint` to complete; `transport.transport.get_extra_info('sockname')[1]` gives the actual port
4. `add_transport(engine, SNMP_UDP_DOMAIN, transport)`
5. `add_v3_user(engine, username, authProtocol=USM_AUTH_HMAC96_MD5, authKey=auth_password)`
6. `add_vacm_user(engine, securityModel=3, securityName=username, securityLevel="authNoPriv", readSubTree=(1,))`
7. `_OurResponder(engine, SnmpContext(engine), server=self)` — registers the responder

### `_OurResponder(CommandResponderBase)`

Private class. Holds a back-reference to `EmulatorServer` for OID tree access and slow-region state.

```
SUPPORTED_PDU_TYPES = (GetRequestPDU.tagSet, GetNextRequestPDU.tagSet, GetBulkRequestPDU.tagSet)
```

`handle_management_operation(snmpEngine, stateReference, contextName, PDU)`:
- Receives an already-authenticated, decoded PDU (pysnmp handles all USM verification before this point)
- Runs the existing Get/GetNext/GetBulk OID-lookup logic (moved verbatim from `_process`)
- Applies slow delay via `self._server._reset_event.wait(timeout=slow_delay)` — blocks the event loop thread intentionally; acceptable for a single-client test emulator
- On reset-drop: calls `release_state_information(stateReference)` and returns (no response sent)
- On success: calls `send_varbinds(snmpEngine, stateReference, 0, 0, rsp_binds)` then `release_state_information(stateReference)`

---

## Prober (`detector/prober.py`)

Constructor signature:

```python
def __init__(self, host: str, username: str, port: int, auth_password: str,
             timeout: float = 5.0, retries: int = 2) -> None:
```

In `bulk_walk` and `probe_oid`, replace:
```python
CommunityData(self._community)
```
with:
```python
UsmUserData(self._username, authKey=self._auth_password,
            authProtocol=usmHMACMD5AuthProtocol)
```

`usmHMACMD5AuthProtocol` is the hlapi alias for `USM_AUTH_HMAC96_MD5`; verify the exact export name from `pysnmp.hlapi.v3arch.asyncio` during implementation (pysnmp v7 renamed several constants but keeps compatibility aliases).

---

## API (`main.py`)

Request models — replace `community: str = "public"` with:
```python
username: str
auth_password: str
```
(no defaults — callers must supply credentials)

Affected models: `CheckRequest`, `WalkRequest`, `DiagnoseRequest`.

`_snmp_get` and `_snmp_walk` signatures gain `username: str, auth_password: str`; replace `CommunityData(community)` with `UsmUserData(username, authKey=auth_password, authProtocol=usmHMACMD5AuthProtocol)`.

---

## Tests (`conftest.py`)

All `EmulatorConfig(...)` literals gain `username="monitor", auth_password="authpass1"` (or rely on the new defaults where they match).

All `SnmpProber("127.0.0.1", community, port, ...)` calls become:
```python
SnmpProber("127.0.0.1", "monitor", port, auth_password="authpass1", ...)
```

No test logic changes — the same slow-region assertions hold.

---

## What is not changing

- OID tree (`_mibs.py`) — untouched
- Slow-region detection logic (`_is_slow`, slow delay, reset-drop) — moved verbatim into `_OurResponder.handle_management_operation`
- `DetectorConfig`, `DiagnosisReport`, classify/engine logic — untouched
- Test assertions — unchanged
