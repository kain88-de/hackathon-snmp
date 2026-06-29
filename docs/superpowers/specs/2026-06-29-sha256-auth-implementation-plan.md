# SHA-256 Auth Implementation Plan (RFC 7860 §2.1)

**Spec:** `tests/robot/spec_rfc7860.robot` (5 emulator scenarios) +
         `tests/robot/spec_rfc7860_reference.robot` (2 reference scenarios)
**Branch:** `feat/robot-living-spec`
**Goal:** All 7 spec scenarios pass; existing 15 robot scenarios stay green; `just ci` passes.

---

## What RFC 7860 §2.1 requires

| Property | MD5 | SHA-1 | SHA-256 |
|---|---|---|---|
| Hash function | MD5 | SHA-1 | SHA-256 |
| Key size (Ku, Kul) | 16 bytes | 20 bytes | **32 bytes** |
| auth_params placeholder | 12 bytes | 12 bytes | **24 bytes** |
| MAC truncation | 12 bytes | 12 bytes | **24 bytes** |

The 24-byte auth_params length is the critical wire-format difference. It is currently hardcoded as `12` in four files. Every change below traces back to this single number becoming a property of the protocol type.

---

## Phase 0 — Type design (before any TDD step)

The current codebase has `Literal["MD5", "SHA"]` scattered across `auth.py`, `codec.py`, `emulator.py`, `walker.py`, and `cli.py`. This is primitive obsession: a closed vocabulary at a boundary should be a `StrEnum`, not a repeated string literal. Adding SHA-256 as a bare string would make it six files.

**Define `AuthProto(StrEnum)` in `src/oidtrace/auth.py`** with members `MD5`, `SHA`, and `SHA256` (value `"SHA-256"`, matching the RFC 7860 protocol name and the CLI flag). `StrEnum` is the right base class: values serialize to their string form, and the constructor parses from a string — making CLI validation a single try/except around the constructor.

**Properties on the enum** — these replace every if/elif chain in the codebase:

| Property | MD5 | SHA | SHA256 |
|---|---|---|---|
| `hash_algo` | `hashlib.md5` | `hashlib.sha1` | `hashlib.sha256` |
| `key_length` | 16 | 20 | 32 |
| `mac_length` | 12 | 12 | 24 |

With this enum, adding SHA-384 or SHA-512 in the future is one new member with three property values — no new branches anywhere else.

**`AuthProto` as a `StrEnum`** means it parses from a CLI string, serialises to its value, and raises `ValueError` for unknown inputs — the CLI validation becomes a try/except around the constructor, with no separate allowlist to maintain.

**Run `just types` after defining the enum.** The type checker flags every `Literal["MD5", "SHA"]` annotation that needs replacing with `AuthProto`. Those call sites become the work list for Phases 1–5.

---

## Phase 1 — Emulator (TDD start)

**Why start here:** the emulator has the richest existing test coverage for auth (`test_emulator_smoke.py` already parametrizes MD5 and SHA). Adding `AuthProto.SHA256` to those parametrize lists gives concrete RED tests immediately, without touching the walker or CLI. The emulator is also the fixture that all robot spec scenarios depend on — if the emulator is correct, the spec scenarios have a trustworthy oracle to run against.

**`tests/support/emulator.py`**

- `EmuDevice.auth_users`: change type from `dict[bytes, tuple[Literal["MD5", "SHA"], bytes]]` to `dict[bytes, tuple[AuthProto, bytes]]`
- `EmuProtocol._handle_v3` auth gate: `len(params.auth_params) == 12` → `len(params.auth_params) == proto.mac_length` (where `proto` comes from the user entry lookup)
- `verify_auth` call site: add `proto` argument (see Phase 3 — `codec.py` change)
- `authenticate_msg` call sites: unchanged in call signature, but will work correctly once `codec.py` is updated

**Unit/smoke tests to add** (`tests/integration/test_emulator_smoke.py`):
- Extend `@pytest.mark.parametrize("proto", ["MD5", "SHA"])` to `["MD5", "SHA", "SHA-256"]` for `test_v3_authnopriv_getbulk_correct_key` and `test_v3_authnopriv_getbulk_wrong_key`
- Assert `len(resp_params.auth_params) == proto.mac_length` in the correct-key test (currently asserts `!= b"\x00" * 12` — update to use protocol-appropriate length)

**Spec scenarios going green:** none yet — `auth.py` and `cli.py` not updated.
**Verification checkpoint:** `uv run pytest tests/integration/test_emulator_smoke.py` — SHA-256 parametrized cases pass (RED → GREEN as auth.py is implemented in Phase 2).

---

## Phase 2 — `auth.py`: replace if/elif with enum properties

With `AuthProto` already defined in `auth.py`:

**`password_to_key(password, engine_id, proto: AuthProto)`**
Replace the MD5/SHA if/elif with a lookup through `proto.hash_algo`. Key length follows from the digest size, which the enum encodes in `proto.key_length`.

**`compute_mac(kul, whole_msg, proto: AuthProto)`**
Replace the MD5/SHA if/elif with `proto.hash_algo`. Truncate the HMAC to `proto.mac_length` bytes. No separate `_mac_len` helper needed — the enum property is the public surface.

**Unit tests to add** (`tests/unit/test_auth.py`):
- Known-answer test: `password_to_key(b"testpass256", EMU_ENGINE_ID, AuthProto.SHA256)` matches a pre-computed reference value. Use net-snmp's source KAT or derive once from a reference implementation and pin the bytes.
- `compute_mac(..., AuthProto.SHA256)` returns exactly 24 bytes
- `compute_mac(..., AuthProto.MD5)` and `compute_mac(..., AuthProto.SHA)` still return 12 bytes (regression guard for existing protocols)

**Spec scenarios going green:** none yet — CLI still rejects SHA-256.
**Verification checkpoint:** `uv run pytest tests/unit/test_auth.py` — all KAT and length assertions pass.

---

## Phase 3 — `codec.py`: proto-aware encode and verify

The 12-byte constant appears in at least four places. All become `proto.mac_length`.

**`verify_auth(raw_data, auth_params, kul, proto: AuthProto)`**
Add `proto` parameter. Change `if len(auth_params) != 12` to `if len(auth_params) != proto.mac_length`. This is a signature change — all callers (emulator, any future walker call) must pass proto in the same commit.

**`encode_v3_getbulk` and `encode_v3_response`**
Both embed `b"\x00" * 12` as the auth_params placeholder. Replace with `bytes(proto.mac_length)`. Thread `proto: AuthProto | None` through to both (currently they receive an `auth: bool` flag — promote to `proto: AuthProto | None` where `None` means noAuth).

**`authenticate_msg(msg, kul, proto: AuthProto)`**
Searches for and overwrites the placeholder. Verify whether the current implementation scans for `b"\x00" * 12` (must become `bytes(proto.mac_length)`) or uses a fixed offset (works unchanged). Check this before assuming generalisation is free.

**Unit tests to add** (`tests/unit/test_codec.py`):
- `encode_v3_getbulk(..., proto=AuthProto.SHA256)` produces a message with a 24-byte auth_params field (parse with `decode_v3_message` and assert `len(params.auth_params) == 24`)
- `authenticate_msg` + `verify_auth` round-trip with SHA-256: sign, verify passes; tamper one byte, verify fails
- `verify_auth` with SHA-256 proto rejects a 12-byte auth_params (length guard)

**Spec scenarios going green:** none yet — CLI not updated.
**Verification checkpoint:** `uv run pytest tests/unit/test_codec.py` — SHA-256 codec round-trip and length guard pass.

---

## Phase 4 — `cli.py`: parse to `AuthProto`

**`_parse_v3_auth` validation block**
Replace the explicit allowlist check with a try/except around the `AuthProto` constructor. The enum is the allowlist. The error message should enumerate valid values from the enum members rather than a hard-coded string. The existing `cast(...)` call becomes unnecessary — the constructor already returns the correctly typed value.

**Spec scenarios going green (emulator tier — all at once):**
- ✅ `RFC 7860 §2.1 - Auth Proto Without Password Is A CLI Validation Error`
  (CLI now accepts SHA-256 as a valid proto, then flags the missing `--auth-pass`)
- ✅ `RFC 7860 §2.1 - SHA-256 Authenticated Walk Completes Successfully`
- ✅ `RFC 7860 §2.1 - SHA-256 Auth Proto Is Case Insensitive`
  (`AuthProto("sha-256".upper())` == `AuthProto("SHA-256")` — case normalisation is already in `cli.py`)
- ✅ `RFC 7860 §2.1 - Wrong Password Causes HMAC Mismatch And Walk Becomes UNRESPONSIVE`
- ✅ `RFC 7860 §2.1 - SHA-256 Walk Begins With A Discovery Exchange`

All 5 emulator-tier scenarios green; all 15 pre-existing scenarios still green.
**Verification checkpoint:** `just robot` — 20 of 22 scenarios pass (reference tier needs net-snmp).

---

## Phase 5 — `walker.py`: type annotation update

**`WalkSettings.v3_auth_proto`**
Change from `Literal["MD5", "SHA"] | None` to `AuthProto | None`.

**Any call site** that passes `v3_auth_proto` to `password_to_key`, `compute_mac`, or codec functions now passes an `AuthProto` directly — no further cast needed.

**Spec scenarios going green:** none (already green at runtime after Phase 4).
**Verification checkpoint:** `just ci` — lint, types (`pyrefly` + `pyright`), deadcode, all pytest pass.

---

## Phase 6 — Reference tier (net-snmp required)

With net-snmp ≥ 5.8 installed:

**`OID Sequence Should Match Snmpwalk V3 Auth` keyword — flag aliasing fix**
Before asserting no output, try `-a SHA-256`; if snmpwalk exits with "invalid auth" error, retry with `-a SHA256` and `-a SHA2`. Robustness change, not a new scenario.

**Spec scenarios going green:**
- ✅ `RFC 7860 §2.1 - SHA-256 Walk OID Sequence Matches snmpwalk (Interop)`
  (snmpwalk sends 24-byte MACs to our emulator; updated length gate accepts them; OID sequences match)
- ✅ `RFC 7860 §2.1 - SHA-256 Walk Against Real SNMP Agent Completes`
  (our walker sends correct 24-byte MACs; snmpd accepts and responds with 24-byte MACs; walker parses them)

**Verification checkpoint:** `REQUIRE_REFERENCE_TOOLS=1 just robot` — all 22 scenarios pass.

---

## Known risks

**`verify_auth` signature change** — adding `proto` is a breaking change. All callers must be updated in the same commit. The type checker enforces this once the annotation is changed.

**`authenticate_msg` placeholder scan** — verify whether the current implementation locates the placeholder by scanning for `b"\x00" * 12` or by a fixed byte offset before assuming Phase 3 generalises for free.

**`encode_v3_getbulk` proto threading** — currently takes `auth: bool`. Promoting to `proto: AuthProto | None` changes the call signature everywhere `encode_v3_getbulk` is called. Check all call sites (walker + emulator + tests) before committing.
