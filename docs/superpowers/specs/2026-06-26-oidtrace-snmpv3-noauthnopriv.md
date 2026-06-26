# OIDTrace SNMPv3 noAuthNoPriv Implementation Spec

**Date:** 2026-06-26
**Scope:** SNMPv3 USM noAuthNoPriv walker — engine discovery, GetBulk walk loop, emulator support, CLI wiring, live crosswalk test.
**Out of scope:** auth (HMAC-MD5/SHA), priv (DES/AES), key localisation, time synchronisation enforcement.
**Reference RFCs:** `docs/rfcs/rfc3412.txt` (message format), `docs/rfcs/rfc3414.txt` (USM).

---

## Wire Format (verified from live snmpwalk -d capture)

### Outer SNMPv3 message structure (RFC 3412 §7)

```
SEQUENCE {
  INTEGER 3                        -- msgVersion
  SEQUENCE msgGlobalData {
    INTEGER                        -- msgID (random, per-message)
    INTEGER 65507                  -- msgMaxSize
    OCTET STRING (1 byte)          -- msgFlags: 0x04 = reportable, noAuth, noPriv
    INTEGER 3                      -- msgSecurityModel = 3 (USM)
  }
  OCTET STRING {                   -- msgSecurityParameters (BER-encoded USM blob)
    SEQUENCE UsmSecurityParameters {
      OCTET STRING                 -- msgAuthoritativeEngineID
      INTEGER                      -- msgAuthoritativeEngineBoots
      INTEGER                      -- msgAuthoritativeEngineTime
      OCTET STRING                 -- msgUserName
      OCTET STRING ""              -- msgAuthenticationParameters (empty = noAuth)
      OCTET STRING ""              -- msgPrivacyParameters       (empty = noPriv)
    }
  }
  SEQUENCE ScopedPDU {             -- tag 0x30 (plain) for noPriv; 0x04 (encrypted) for Priv
    OCTET STRING                   -- contextEngineID (= engineID after discovery)
    OCTET STRING ""                -- contextName
    PDU                            -- GetBulk (0xA5) or GetRequest (0xA0) for discovery
  }
}
```

### Discovery exchange (RFC 3414 §4)

**Probe** (client → agent): GetRequest (0xA0) with:
- All USM fields empty/zero
- contextEngineID = ""
- VarBindList **empty** (0x30 0x00)

**Response** (agent → client): Report PDU (0xA8) containing:
- `msgAuthoritativeEngineID` (17 bytes in live capture: `80 00 1F 88 …`)
- `msgAuthoritativeEngineBoots` (integer)
- `msgAuthoritativeEngineTime` (integer)

The walker extracts these three values and reuses them unchanged for all subsequent GetBulk requests. For noAuthNoPriv the agent does not enforce time windows so stale boots/time are harmless.

---

## Component Changes

### 1. `traceformat/models.py` — add `"3"` to Version enum

```python
class Version(Enum):
    field_1  = "1"
    field_2c = "2c"
    field_3  = "3"   # NEW
```

`records.py`: update `snmp_version` annotation `Literal["1", "2c"] → Literal["1", "2c", "3"]`.

### 2. `codec.py` — three new functions

**`encode_v3_discovery(msg_id, request_id) -> bytes`**

Encodes the discovery probe:
- `msgFlags = 0x04`
- All USM fields empty/zero
- GetRequest (0xA0) PDU with empty VarBindList

**`encode_v3_getbulk(msg_id, request_id, oid, max_repetitions, engine_id, engine_boots, engine_time, username) -> bytes`**

Encodes a real GetBulk request:
- `msgFlags = 0x04`
- USM: engine_id/boots/time from discovery, username, empty auth/priv params
- ScopedPDU with GetBulk (0xA5) PDU, non_repeaters=0

**`decode_v3_message(raw) -> Message | Malformed`**

Decodes a v3 response:
1. Verify outer SEQUENCE, INTEGER=3
2. Skip `msgGlobalData` (read and discard — we don't need msgID)
3. Decode USM OCTET STRING → extract `engine_id`, `engine_boots`, `engine_time` (needed for discovery response)
4. Read ScopedPDU SEQUENCE (tag must be 0x30; 0x04 = encrypted → Malformed)
5. Skip contextEngineID, contextName
6. Decode PDU using the existing `_decode_pdu` helper (factored out of `decode_message`)
7. Return `Message` — Report PDU (0xA8) returns as `Message` with `pdu_tag=0xA8`

`decode_message` (v1/v2c) is refactored to share the PDU-decoding inner loop with `decode_v3_message`.

A new frozen dataclass `V3Params` carries the extracted USM fields from a decoded v3 message:
```python
@dataclass(frozen=True, slots=True)
class V3Params:
    engine_id: bytes
    engine_boots: int
    engine_time: int
```

`decode_v3_message` returns `tuple[Message, V3Params] | Malformed` so the walker can extract the engine params from the discovery Report without a second parse.

### 3. `walker.py` — WalkSettings + walk_records

**WalkSettings additions:**
```python
snmp_version: Literal["1", "2c", "3"] = "2c"
v3_user: str | None = None  # required when snmp_version == "3"
```

`__post_init__` validation: if `snmp_version == "3"` and `v3_user is None` → `ValueError`.

**`_discover_engine` coroutine** (private, in walker.py):

```python
async def _discover_engine(transport, settings) -> V3Params:
```

Sends one discovery probe via `transport.exchange`, decodes via `decode_v3_message`, asserts `pdu_tag == 0xA8` (Report), returns `V3Params`. Raises `RuntimeError` on failure (walk aborts before first exchange is recorded).

**`walk_records` change:**

At the top of the generator, before entering the walk loop, if `snmp_version == "3"`:
```python
v3 = await _discover_engine(transport, settings)
```

Inside the loop, the `snmp_version == "3"` branch encodes requests with `encode_v3_getbulk` and decodes responses with `decode_v3_message`. Termination conditions are identical to v2c (EndOfMibView tag 0x82, left-subtree, empty varbinds).

`_make_settings_model`: for v3, `bulk_size` is passed through unchanged (GetBulk walk, not GetNext). `snmp_version` → `"3"`.

`header_record` call: `snmp_version="3"`.

### 4. `tests/support/emulator.py` — v3 discovery + GetBulk

`EmuProtocol._handle` gains a v3 branch:

1. Detect v3 by reading the version byte: peek at the BER SEQUENCE body — if `INTEGER = 3` it is v3; otherwise use `decode_message` for v1/v2c as today.
2. If v3 and pdu_tag == GetRequest (0xA0) with empty varbinds → discovery response:
   - Reply with a Report PDU (0xA8) containing a fixed synthetic engineID (`b'\x80\x00\x00\x00\x01testemu\x00'`), boots=1, time=0.
3. If v3 and pdu_tag == GetBulk (0xA5) → reuse existing GetBulk response logic, wrap result in a v3 response via `encode_v3_response` (new function in codec.py or inline in emulator).

`encode_v3_response` mirrors `encode_response` but wraps the PDU in a ScopedPDU and v3 outer envelope. It is added to `codec.py` alongside the other v3 encode functions (not inline in the emulator — codec.py owns all encode/decode).

### 5. `cli.py` — remove stub, wire to walker

Remove:
```python
if args.version == "v3":
    print(f"error: SNMP {args.version} not yet implemented", file=sys.stderr)
    return 2
```

Add v3 branch (alongside the existing v1/v2c branch):
```python
elif args.version == "v3":
    settings = WalkSettings(
        snmp_version="3",
        v3_user=args.user,
        bulk_size=args.bulk_size,
        timeout_s=args.timeout,
        retries=args.retries,
        start_oid=Oid.from_str(args.oid),
    )
```

The `--auth-proto`, `--auth-pass`, `--priv-proto`, `--priv-pass` args are parsed but silently ignored in this phase (noAuthNoPriv only). A warning is printed if any are supplied.

---

## Test Plan

### Unit tests (`tests/unit/`)

| File | Tests |
|------|-------|
| `test_codec_v3.py` | `encode_v3_discovery` round-trips via `decode_v3_message`; `encode_v3_getbulk` decodes correctly; `decode_v3_message` on a Report returns `pdu_tag=0xA8` and correct `V3Params`; non-v3 data returns `Malformed` |

### Integration tests (`tests/integration/`)

| File | Tests |
|------|-------|
| `test_emulator_smoke.py` | v3 discovery exchange → Report with engineID; v3 GetBulk → response varbinds |
| `test_cli.py` | `walk v3 127.0.0.1 --user noAuthUser` via emulator → trace file written, `snmp.version="3"`, oids_seen > 0; existing `test_walk_v3_not_implemented` deleted |

### Reference tool test (`tests/integration/test_reference_tools.py`)

`snmpwalk -v3 -u noAuthUser -l noAuthNoPriv` against a 50-OID emulator returns exactly 50 OID lines. Uses `reference_tools` marker + `_require_tool` guard (same pattern as v1 crosswalk).

Live-device crosswalk (marked `live_device`, skipped by default): `oidtrace walk v3 127.0.0.1 --user noAuthUser` vs `snmpwalk` against `127.0.0.1:161` — OID counts must match.

---

## Constraints

- `just test` must pass after every task. `just ci` must pass at final review.
- No auth/priv crypto in this phase. `--auth-proto`/`--auth-pass`/`--priv-proto`/`--priv-pass` are accepted by the CLI but trigger a "noAuthNoPriv only" warning and are not used.
- `bulk_size = 0` (GetNext) is invalid for v3 in this phase — `WalkSettings.__post_init__` rejects it.
- Discovery exchange is silent (not recorded in trace).
- `decode_message` (v1/v2c) is unchanged in behaviour; only the inner PDU-decoding loop is refactored into a shared helper.
