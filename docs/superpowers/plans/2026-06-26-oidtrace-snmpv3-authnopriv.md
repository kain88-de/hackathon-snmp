# OIDTrace SNMPv3 authNoPriv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add HMAC-MD5-96 and HMAC-SHA-96 authentication to the oidtrace SNMPv3 walker so that `oidtrace walk v3 <host> --user checkmk --auth-proto MD5 --auth-pass synology` produces a valid authenticated trace.

**Architecture:** New `auth.py` implements RFC 3414 key derivation and MAC computation. `codec.py` gains `auth=False` flags on the encode functions, a 12-zero placeholder for unsigned auth params, and `authenticate_msg` / `verify_auth` helpers. `walker.py` derives `kul` after discovery and stamps each GetBulk with an HMAC. The emulator verifies incoming MACs and signs outgoing responses. `cli.py` drops the "ignored" warning and wires `--auth-proto` / `--auth-pass`.

**Tech Stack:** Python stdlib `hashlib` + `hmac`, pytest, `just`.

**Wire format:** RFC 3414 §6.3.1 (HMAC-MD5-96), §7.3.1 (HMAC-SHA-96), Appendix A.2 (password-to-key). All in `docs/rfcs/rfc3414.txt`.

## Global Constraints

- `msgFlags` authNoPriv = `0x05` (`reportable | auth`); noAuthNoPriv stays `0x04`.
- Outgoing auth params = 12 zero bytes in unsigned message; replaced by HMAC before send.
- Key derivation: cycle password over 1 048 576 bytes → `Ku`; then `Kul = hash(Ku + engineID + Ku)`. MD5 → 16-byte key; SHA-1 → 20-byte key.
- Discovery is always noAuthNoPriv; `kul` cannot be derived until `engineID` is known.
- `v3_auth_proto` and `v3_auth_pass` must be set together; `WalkSettings.__post_init__` rejects `v3_auth_proto` alone.
- Emulator drops packets with invalid MACs silently.
- `just test` must pass after every task. `just ci` at the review step.

---

### Task 1: `auth.py` — key derivation and MAC computation

> **Model: haiku** — pure crypto; no BER.

**Files:**
- Create: `oidtrace/src/oidtrace/auth.py`
- Create: `oidtrace/tests/unit/test_auth.py`

**Tests** (`oidtrace/tests/unit/test_auth.py`):

| Input | Outcome |
|-------|---------|
| `password_to_key(b"maplesyrup", bytes.fromhex("000000000000000000000002"), "MD5")` | `== bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")` (RFC 3414 A.3.1; engineID = 12 bytes) |
| `password_to_key(b"maplesyrup", bytes.fromhex("000000000000000000000002"), "SHA")` | `== bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")` (RFC 3414 A.3.2) |
| MD5 key length | `len(...) == 16` |
| SHA key length | `len(...) == 20` |
| Same password, different engineIDs | keys differ |
| `compute_mac(kul, msg, "MD5")` | `len(...) == 12` |
| `compute_mac(kul, msg, "SHA")` | `len(...) == 12` |
| `compute_mac(kul, msg, ...)` vs `compute_mac(kul, tampered_msg, ...)` | differ |
| `compute_mac(kul1, msg, ...)` vs `compute_mac(kul2, msg, ...)` | differ |

**Interfaces:**
```python
def password_to_key(password: bytes, engine_id: bytes, proto: Literal["MD5", "SHA"]) -> bytes
def compute_mac(kul: bytes, whole_msg: bytes, proto: Literal["MD5", "SHA"]) -> bytes  # 12 bytes
```

- [ ] Write failing tests → `just test oidtrace/tests/unit/test_auth.py` → FAIL. Implement `auth.py`. Run `just test` → PASS. Commit.

---

### Task 2: codec — auth-aware encode, `authenticate_msg`, `verify_auth`, decode `auth_params`

> **Model: sonnet** — BER offset manipulation; must not break existing v3 or v1/v2c tests.

**Files:**
- Modify: `oidtrace/src/oidtrace/codec.py`
- Modify: `oidtrace/tests/unit/test_codec_v3_encode.py`
- Modify: `oidtrace/tests/unit/test_codec_v3_decode.py`

**Tests** (add to `test_codec_v3_encode.py`):

| Input | Outcome |
|-------|---------|
| `encode_v3_getbulk(..., auth=True)` | `b"\x04\x01\x05" in raw` (msgFlags 0x05) |
| `encode_v3_getbulk(..., auth=False)` | `b"\x04\x01\x04" in raw` (regression: unchanged) |
| `encode_v3_getbulk(..., auth=True)` | `b"\x04\x0c" + b"\x00"*12 in raw` (12-zero placeholder) |
| `authenticate_msg(raw_with_placeholder, kul, "MD5")` | `len(result) == len(raw)`, placeholder replaced, MAC slot non-zero |
| `verify_auth(authenticated, auth_params, kul, "MD5")` | `True` |
| `verify_auth(authenticated, auth_params, wrong_kul, "MD5")` | `False` |
| `verify_auth(tampered_after_sign, auth_params, kul, "MD5")` | `False` |
| `encode_v3_response(..., auth=True)` | `b"\x04\x0c" + b"\x00"*12 in raw` |

**Tests** (add to `test_codec_v3_decode.py`):

| Input | Outcome |
|-------|---------|
| `decode_v3_message(authenticate_msg(encode_v3_getbulk(..., auth=True), kul, "MD5"))` | `params.auth_params` is 12 non-zero bytes |
| `decode_v3_message(encode_v3_discovery(1, 42))` | `params.auth_params == b""` |

**Interfaces:**
```python
# V3Params — add field (after existing fields):
auth_params: bytes = b""

# _encode_msg_global_data — new param:
def _encode_msg_global_data(msg_id: int, auth: bool = False) -> bytes  # 0x05 if auth else 0x04

# _encode_usm_params — new param:
def _encode_usm_params(engine_id, engine_boots, engine_time, username, auth_params: bytes = b"") -> bytes

# Existing encode functions — new param:
def encode_v3_getbulk(..., auth: bool = False) -> bytes   # places b"\x00"*12 when auth=True
def encode_v3_response(..., auth: bool = False) -> bytes

# New helpers:
_AUTH_PARAMS_PLACEHOLDER: bytes = b"\x04\x0c" + b"\x00" * 12

def _auth_params_value_offset(raw: bytes) -> int
    # BER-walk the outer SEQUENCE → skip INTEGER(3) → skip msgGlobalData SEQUENCE
    # → enter USM OCTET STRING → enter inner SEQUENCE → skip engineID / boots / time /
    # username → return byte offset of the auth_params VALUE (past its tag+length).
    # Raises ValueError if structure is not as expected.

def authenticate_msg(raw: bytes, kul: bytes, proto: Literal["MD5", "SHA"]) -> bytes
    # Use _auth_params_value_offset(raw) to find the auth params position (not raw.index —
    # scanning b"\x04\x0c\x00*12" collides when engineID happens to be 12 zero bytes).
    # Zero the 12 bytes at that offset, compute_mac, splice MAC in.

def verify_auth(raw: bytes, auth_params: bytes, kul: bytes, proto: Literal["MD5", "SHA"]) -> bool
    # Use _auth_params_value_offset(raw) to find auth params position, zero it,
    # recompute MAC, compare_digest. Returns False if len(auth_params) != 12 or
    # the offset walk fails (Malformed message).
```

Import `compute_mac` from `oidtrace.auth`; import `hmac` for `compare_digest`.

- [ ] Write failing tests → FAIL. Implement codec changes. Run `just test` → PASS. Commit.

---

### Task 3: Emulator — verify incoming MAC, sign outgoing responses

> **Model: sonnet** — async dispatch; `_handle_v3` already exists; must not break existing emulator tests.

**Files:**
- Modify: `oidtrace/tests/support/emulator.py`
- Modify: `oidtrace/tests/integration/test_emulator_smoke.py`
- Modify: `oidtrace/tests/integration/test_reference_tools.py`

**Tests** (add to `test_emulator_smoke.py`):

| Scenario | Outcome |
|----------|---------|
| Auth GetBulk with correct MAC to auth emulator | response decodes via `decode_v3_message`, `params.auth_params` is 12 non-zero bytes, `verify_auth(response, params.auth_params, kul, "MD5") is True` |
| Same GetBulk signed with wrong key | no response within 300 ms |
| Existing noAuthNoPriv emulator tests | pass unchanged |

Perform discovery first to get the actual `engine_id`, then compute `kul = password_to_key(b"testpass1", engine_id, "MD5")`. The auth emulator is constructed with `EmuDevice.simple(n_oids=10, auth_users={b"authuser": ("MD5", kul)})`.

**Reference test** (add to `test_reference_tools.py`; verifies the emulator speaks correct authNoPriv against an independent implementation before the walker is wired):

| Scenario | Outcome |
|----------|---------|
| `snmpwalk -v3 -u authuser -l authNoPriv -a MD5 -A testpass1 -On -t 2 -r 0 <host>:<port> 1.3.6.1` against 20-OID auth emulator | exits 0, 20 OID lines in stdout |

Use `_require_tool("snmpwalk")` and the `reference_tools` marker. Same `EmuDevice.simple(n_oids=20, auth_users={b"authuser": ("MD5", kul)})` pattern as the smoke tests; derive `kul` from `_EMU_ENGINE_ID`.

**Interfaces:**
```python
# EmuDevice — add field:
auth_users: dict[bytes, tuple[Literal["MD5", "SHA"], bytes]] = field(default_factory=dict)

# EmuDevice.simple — new param:
@classmethod
def simple(cls, n_oids=100, quirks=None, auth_users: dict | None = None) -> EmuDevice

# _handle_v3 — add raw_data param, auth dispatch:
async def _handle_v3(self, msg, params, addr, raw_data: bytes) -> None
# If len(params.auth_params) == 12: look up params.username in auth_users,
#   call verify_auth; drop silently if not found or MAC invalid.
# Discovery response is always noAuthNoPriv (no auth flag).
# GetBulk/GetNext: encode_v3_response(..., auth=needs_auth), then authenticate_msg if needs_auth.
```

Call site in `datagram_received` must pass `data` as `raw_data` to `_handle_v3`.

- [ ] Write failing smoke tests → FAIL. Implement emulator changes. Run `just test` → PASS.
- [ ] Write snmpwalk reference test → `REQUIRE_REFERENCE_TOOLS=1 just test-all -k test_snmpwalk_v3_authnopriv` → PASS. Commit.

---

### Task 4: `WalkSettings` + `walk_records` auth wiring

> **Model: opus** — kul derivation after discovery; authenticated GetBulk loop.

**Files:**
- Modify: `oidtrace/src/oidtrace/walker.py`
- Modify: `oidtrace/tests/unit/test_walker_logic.py`
- Modify: `oidtrace/tests/integration/test_walker.py`

**Tests** (`test_walker_logic.py`):

| Input | Outcome |
|-------|---------|
| `WalkSettings(snmp_version="3", v3_user="u", v3_auth_proto="MD5")` | `ValueError` containing "v3_auth_pass" |
| `WalkSettings(snmp_version="3", v3_user="u", v3_auth_proto="MD5", v3_auth_pass="x")` | valid |
| `WalkSettings(snmp_version="3", v3_user="u", v3_auth_proto="SHA", v3_auth_pass="x")` | valid |

Use `FakeTransport` with scripted `encode_v3_response(..., auth=True)` / `authenticate_msg(...)` responses to verify the walker sends authenticated GetBulks and terminates with `end_reason == "completed"`.

**Tests** (`test_walker.py`):

| Scenario | Outcome |
|----------|---------|
| v3 authNoPriv walk over auth emulator, 20 OIDs | `end_reason == "completed"`, `oids_seen == 20` |

**Interfaces:**
```python
# WalkSettings — add fields after v3_user:
v3_auth_proto: Literal["MD5", "SHA"] | None = None
v3_auth_pass: str | None = None
# __post_init__: raise ValueError("v3_auth_pass required") if v3_auth_proto set without v3_auth_pass

# walk_records — after successful discovery, if v3_auth_proto set:
v3_kul = password_to_key(settings.v3_auth_pass.encode(), v3_params.engine_id, settings.v3_auth_proto)
# In GetBulk loop:
raw = encode_v3_getbulk(..., auth=v3_kul is not None)
if v3_kul: raw = authenticate_msg(raw, v3_kul, settings.v3_auth_proto)
```

Import `password_to_key` from `oidtrace.auth`; import `authenticate_msg` from `oidtrace.codec`.

- [ ] Write failing unit tests → FAIL. Implement `WalkSettings` additions and `walk_records` auth branch. Run `just test` → PASS. Write integration test → PASS. Commit.

---

### Task 5: CLI auth wiring

> **Model: haiku** — remove warning, validate and wire auth fields.

**Files:**
- Modify: `oidtrace/src/oidtrace/cli.py`
- Modify: `oidtrace/tests/integration/test_cli.py`

**Tests** (add to `test_cli.py`):

| Scenario | Outcome |
|----------|---------|
| `walk v3 <host> --user u --auth-proto MD5 --auth-pass p` against auth emulator | exit 0, trace written |
| `walk v3 <host> --user u` (no auth flags) | exit 0, noAuthNoPriv unchanged |
| `walk v3 <host> --user u --auth-proto MD5` (no `--auth-pass`) | exit 2 |
| `walk v3 <host> --user u --auth-proto DES --auth-pass p` | exit 2 |

**Interfaces:**
- Remove the `print("warning: auth/priv arguments are ignored")` block.
- Validate `args.auth_proto.upper() in ("MD5", "SHA")`; exit 2 with message if not.
- Require `args.auth_pass` when `args.auth_proto` is set; exit 2 if missing.
- Wire `v3_auth_proto` and `v3_auth_pass` into `WalkSettings`.
- Warn to stderr (no exit) if `args.priv_proto` or `args.priv_pass` are set.

- [ ] Write failing tests → FAIL. Implement CLI changes. Run `just test` → PASS. Commit.

---

### Task 6: walker vs `snmpwalk` crosswalk + real AP smoke test

> **Model: haiku** — mirrors `test_snmpbulkwalk_crosswalk` pattern; real-AP test uses `walk_ap.sh` credentials.

**Files:**
- Modify: `oidtrace/tests/integration/test_reference_tools.py`

**Tests**:

| Scenario | Outcome |
|----------|---------|
| Our v3 authNoPriv walker vs `snmpwalk -v3 -u authcross -l authNoPriv -a MD5 -A crosspass1` against same 30-OID auth emulator | `our_oids == ref_oids[:len(our_oids)]`, `len(set(our_oids)) == 30`; skip discovery exchange when parsing trace |
| `oidtrace walk v3 192.168.1.143 --user checkmk --auth-proto MD5 --auth-pass synology` | trace written, `summary.end_reason == "completed"`, `summary.oids_seen > 0` |

Use `_require_tool("snmpwalk")` and the `reference_tools` marker for both. Pre-compute `kul = password_to_key(b"crosspass1", _EMU_ENGINE_ID, "MD5")` for the crosswalk. The real-AP test reads credentials from the constants `_AP_HOST = "192.168.1.143"`, `_AP_USER = "checkmk"`, `_AP_PASS = "synology"` at the top of the file.

- [ ] Write crosswalk test → `REQUIRE_REFERENCE_TOOLS=1 just test-all ...::test_snmpwalk_v3_authnopriv_crosswalk` → PASS.
- [ ] Write real-AP test → `REQUIRE_REFERENCE_TOOLS=1 just test-all ...::test_oidtrace_v3_authnopriv_real_ap` → PASS. Run `just test` → PASS. Commit.

---

### Review checkpoint

> **Model: opus** — quality review.

Run `just ci` (ruff → pyrefly → vulture → pytest). Expected: clean pass.

Run `REQUIRE_REFERENCE_TOOLS=1 just test-all`. Expected: all reference tests pass, including the real AP test from Task 6.

#### Test review

Spawn a review agent (model: opus) against all auth-related test additions with this prompt:

---

Apply the following checklist. Cite the specific test and explain concretely why it is or is not a problem. Do not flag issues already caught by the type checker or linter.

**Anti-patterns:**
- **RFC vector coverage**: Does `test_password_to_key_md5_rfc_vector` use the RFC 3414 Appendix A.3.1 vector verbatim? Would a byte-swapped implementation pass?
- **MAC self-verification**: `test_verify_auth_accepts_correct_mac` calls `verify_auth` right after `authenticate_msg` with the same key. Could both share the same offset bug and still agree?
- **Wrong-MAC drop timing**: the emulator drop test waits 300 ms. Is this enough under load?
- **kul consistency**: integration tests pre-compute `kul` from `_EMU_ENGINE_ID`. If the emulator's engine ID changes, does the test catch the mismatch or silently pass?

**Red flags:**
1. Is there a test that catches `authenticate_msg` writing the MAC at the wrong byte offset?
2. Does the crosswalk test verify that `auth_params` in responses are non-zero (proving we sent authenticated requests, not a lucky noAuthNoPriv walk)?
3. If `v3_auth_pass` is set but `v3_auth_proto` is None — is this silently noAuthNoPriv? Is it tested?

Conclude with: must-fix / nice-to-have list and a one-line verdict.

---

Only proceed to merge once `just ci` is clean, the AP smoke test passes, and the review raises no must-fix issues.
