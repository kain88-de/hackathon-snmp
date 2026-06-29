# OIDTrace SNMPv3 noAuthNoPriv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the SNMPv3 noAuthNoPriv walker — engine discovery recorded as seq=1, GetBulk loop from seq=2 — extending traceformat, codec, emulator, walker, and CLI.

**Architecture:** `traceformat` gains `Version("3")`, `Pdu("discovery")`, relaxed `Request.oids`; `codec.py` gains three encode functions, `decode_v3_message`, a shared `_decode_pdu` helper, and `V3Params`; `walker.py` runs discovery as seq=1 then a GetBulk loop; the emulator handles v3 discovery and GetBulk; `cli.py` removes the exit-2 stub.

**Tech Stack:** Python stdlib asyncio, pytest, hypothesis (already in dev deps), `just` for task runner.

**Spec:** `docs/superpowers/specs/2026-06-26-oidtrace-snmpv3-noauthnopriv.md`

**Wire format:** Verified from live `snmpwalk -d` capture. See `docs/rfcs/rfc3412.txt` (message) and `docs/rfcs/rfc3414.txt` (USM).

## Global Constraints

- SNMPv3 outer wire: `SEQUENCE { INTEGER 3, SEQUENCE(msgGlobalData), OCTET_STRING(USM-blob), SEQUENCE(ScopedPDU) }`.
- noAuthNoPriv: `msgFlags = 0x04`. USM auth/priv params are empty OCTET STRINGs. ScopedPDU tag is `0x30` (plain; `0x04` = encrypted → reject as Malformed).
- Discovery probe: GetRequest PDU (`0xA0`) with empty VarBindList (`30 00`). All USM fields empty/zero. Response is Report PDU (`0xA8`) carrying engineID/boots/time.
- Discovery exchange is recorded as seq=1 with `pdu: "discovery"` and `oids: []`. Walk loop starts at seq=2.
- `bulk_size = 0` is invalid for v3. `WalkSettings.__post_init__` rejects it.
- `--auth-proto`, `--auth-pass`, `--priv-proto`, `--priv-pass` are parsed but ignored; CLI prints a warning if any are supplied.
- `just test` must pass after every task. `just ci` must pass at the final review step.
- Changes span `traceformat/` and `oidtrace/` (`src/oidtrace/`, `tests/`).

---

### Task 1: traceformat — Version "3", Pdu "discovery", Request.oids min_length=0

> **Model: haiku** — enum additions and one field change.

**Tests:**

| Input | Outcome |
|-------|---------|
| `Version("3")` | valid, `.value == "3"` |
| `Pdu("discovery")` | valid, `.value == "discovery"` |
| `Request(pdu=Pdu("discovery"), request_id=1, oids=[])` | valid — empty oids accepted |
| `header_record(..., snmp_version="3", ...)` | `header.snmp.version.value == "3"` |

**Interfaces:**
- `Version.field_3 = "3"` — new enum member in `traceformat/src/traceformat/models.py`
- `Pdu.discovery = "discovery"` — new enum member
- `Request.oids`: change `min_length=1` → `min_length=0`
- `header_record(snmp_version: Literal["1", "2c", "3"], ...)` — widen annotation in `oidtrace/src/oidtrace/records.py`

- [ ] Write failing tests in `traceformat/tests/test_smoke.py` and `oidtrace/tests/unit/test_records.py` → `just test` → FAIL. Implement. Run `just test` → PASS. Commit.

---

### Task 2: v3 codec encode — PDU_GET, PDU_REPORT, V3Params, three encode functions

> **Model: haiku** — mechanical BER encoding; shape mirrors `encode_getbulk`.

**Tests** (add to `oidtrace/tests/unit/test_codec_v3_encode.py`):

| Input | Outcome |
|-------|---------|
| `encode_v3_discovery(0x10000001, 0x20000001)` | `len(raw) == 64` (matches live snmpwalk capture) |
| `encode_v3_discovery(1, 42)` | `bytes([0x02, 0x01, 0x03]) in raw` (version INTEGER 3) |
| `encode_v3_discovery(1, 42)` | `0xA0 in raw` (GetRequest tag) |
| `encode_v3_discovery(1, 42)` | `bytes([0x30, 0x00]) in raw` (empty VarBindList) |
| `encode_v3_discovery(1, 42)` | `raw.count(bytes([0x04, 0x00])) >= 5` (all USM/ScopedPDU OCTET STRINGs empty) |
| `encode_v3_getbulk(1, 42, oid, 7, eng_id, 1, 0, b"user")` | `0xA5 in raw`, `b"user" in raw`, `eng_id in raw`, `bytes([0x02, 0x01, 0x07]) in raw` |
| `encode_v3_response(1, 42, [...], eng_id)` | `0xA2 in raw` |
| `encode_v3_response(..., pdu_tag=PDU_REPORT)` | `0xA8 in raw` |
| `V3Params(engine_id=b"x", engine_boots=1, engine_time=2, msg_id=3)` | frozen — assigning `.engine_boots` raises |

**Interfaces:**
```python
PDU_GET: int = 0xA0    # GetRequest — discovery probe
PDU_REPORT: int = 0xA8 # Report — discovery response

@dataclass(frozen=True, slots=True)
class V3Params:
    engine_id: bytes
    engine_boots: int
    engine_time: int
    msg_id: int  # from msgGlobalData; needed to echo in emulator responses

def encode_v3_discovery(msg_id: int, request_id: int) -> bytes
def encode_v3_getbulk(msg_id, request_id, oid, max_repetitions, engine_id, engine_boots, engine_time, username) -> bytes
def encode_v3_response(msg_id, request_id, varbinds, engine_id, username=b"", error_status=0, error_index=0, pdu_tag=PDU_RESPONSE) -> bytes
```

Internal helpers (private, not exported): `_encode_msg_global_data(msg_id)`, `_encode_usm_params(engine_id, boots, time, username)`, `_encode_scoped_pdu(context_engine_id, pdu)`.

- [ ] Write failing tests → `just test oidtrace/tests/unit/test_codec_v3_encode.py` → FAIL. Implement. Run `just test` → PASS. Commit.

---

### Task 3: v3 codec decode — _decode_pdu refactor + decode_v3_message

> **Model: sonnet** — nested BER: USM OCTET-STRING-inside-OCTET-STRING; must not break v1/v2c decode_message.

**Tests** (create `oidtrace/tests/unit/test_codec_v3_decode.py`):

| Input | Outcome |
|-------|---------|
| `decode_v3_message(encode_v3_discovery(99, 42))` | `msg.pdu_tag == PDU_GET`, `msg.varbinds == ()`, `params.engine_id == b""`, `params.msg_id == 99`, `msg.request_id == 42` |
| `decode_v3_message(encode_v3_getbulk(99, 42, oid, 10, eng_id, 5, 100, b"u"))` | `msg.pdu_tag == PDU_GETBULK`, `params.engine_id == eng_id`, `params.engine_boots == 5`, `params.engine_time == 100`, `params.msg_id == 99` |
| `decode_v3_message(encode_v3_response(7, 55, [(oid, 0x04, b"hi")], eng_id))` | `msg.pdu_tag == PDU_RESPONSE`, `msg.request_id == 55`, `len(msg.varbinds) == 1` |
| `decode_v3_message(encode_v3_response(..., pdu_tag=PDU_REPORT))` | `msg.pdu_tag == PDU_REPORT` |
| ScopedPDU tag flipped to `0x04` (simulate Priv) | `Malformed` with "encrypt" or "Priv" in `.error` |
| `decode_v3_message(encode_getbulk(1, oid, 0, 5))` (v2c packet) | `Malformed` |
| `decode_v3_message(b"")` or random bytes | `Malformed` |
| `decode_message(encode_getbulk(42, oid, 0, 5))` after refactor | still returns valid `Message` (regression) |

**Interfaces:**
```python
def decode_v3_message(raw: bytes) -> tuple[Message, V3Params] | Malformed
```

Refactor: extract `_decode_pdu(pdu_tag: int, pdu_body: bytes) -> tuple[int, int, int, tuple[Varbind, ...]]` (returns `request_id, f1, f2, varbinds`) shared between `decode_message` and `decode_v3_message`. `decode_message` behaviour is unchanged.

- [ ] Write failing tests → `just test oidtrace/tests/unit/test_codec_v3_decode.py` → FAIL. Implement. Run `just test` → PASS. Commit.

---

### Task 4: v3 codec fuzz tests

> **Model: sonnet** — hypothesis property-based tests; verify codec is symmetric and never raises.

**Tests** (create `oidtrace/tests/unit/test_codec_v3_fuzz.py`):

| Property | Description |
|----------|-------------|
| `test_decode_v3_never_raises` | `decode_v3_message(arbitrary_bytes: bytes)` — always `Malformed` or `(Message, V3Params)`, never raises |
| `test_discovery_roundtrip` | `encode_v3_discovery(msg_id, req_id)` → `decode_v3_message` roundtrips `msg_id` and `request_id` exactly |
| `test_getbulk_roundtrip` | `encode_v3_getbulk(msg_id, req_id, oid, reps, eng_id, boots, time, user)` roundtrips all six fields |
| `test_response_roundtrip` | `encode_v3_response(msg_id, req_id, vbs, eng_id)` roundtrips `request_id`, `engine_id`, `msg_id` |
| `test_bit_flip_never_raises` | XOR-mutating a discovery packet byte-by-byte never raises — always `Malformed` or valid |

Use `st.integers(min_value=0, max_value=2**31 - 1)` for integer fields, `st.binary(min_size=0, max_size=32)` for bytes fields.

- [ ] Write tests → `just test oidtrace/tests/unit/test_codec_v3_fuzz.py` → PASS. Run `just test` → PASS. Commit.

---

### Task 5: Emulator v3 — discovery reply + v3 GetBulk response

> **Model: sonnet** — async dispatch; new v3 branch alongside existing v1/v2c; must not break existing emulator tests.

**Tests** (add to `test_emulator_smoke.py`; add an `_send_raw(host, port, raw)` async helper):

| Scenario | Outcome |
|----------|---------|
| Send `encode_v3_discovery(1, 42)` to emulator | response decodes via `decode_v3_message`, `msg.pdu_tag == PDU_REPORT`, `msg.request_id == 42` |
| Discovery response | `params.engine_id != b""` |
| Send `encode_v3_getbulk(2, 99, oid, 5, params.engine_id, ...)` after discovery | `msg.pdu_tag == PDU_RESPONSE`, `msg.request_id == 99`, `len(msg.varbinds) == 5` |

**Interfaces (in `tests/support/emulator.py`):**
- `_EMU_ENGINE_ID: bytes = b"\x80\x00\x00\x00\x01testemu\x00"` — stable synthetic engineID
- `_USM_STATS_UNKNOWN_USER_NAMES = Oid.from_str("1.3.6.1.6.3.15.1.1.4.0")`
- Dispatch: call `decode_v3_message(data)` first; if not Malformed → handle v3 and return; otherwise fall through to existing `decode_message` path.
- v3 GetRequest (pdu_tag == PDU_GET, empty varbinds) → reply with `encode_v3_response(..., pdu_tag=PDU_REPORT)` carrying one `Counter32` varbind at `_USM_STATS_UNKNOWN_USER_NAMES`.
- v3 GetBulk → reuse existing `_getbulk_varbinds` helper; wrap result in `encode_v3_response(...)`.

- [ ] Write failing tests → FAIL (timeout). Implement. Run `just test` → PASS. Commit.

---

### Task 6: `snmpwalk -v3` against emulator

> **Model: haiku** — test writing; mirrors the existing `test_snmpwalk_v1` pattern exactly.

**Tests** (add to `test_reference_tools.py`):

| Scenario | Outcome |
|----------|---------|
| `snmpwalk -v3 -u noAuthUser -l noAuthNoPriv -On -t 2 -r 0 <host>:<port> 1.3.6.1` against 50-OID emulator | exits 0, exactly 50 OID lines in stdout |

Use the same `_require_tool`, `reference_tools` marker, and `emulator_factory` pattern as `test_snmpwalk_v1`.

- [ ] Write test → `REQUIRE_REFERENCE_TOOLS=1 just test-all ...::test_snmpwalk_v3_noauthnopriv` → PASS. Run `just test` → PASS. Commit.

---

### Task 7: `WalkSettings` v3 + `walk_records` v3 branch

> **Model: opus** — most complex task: async generator, discovery as seq=1, V3Params threading, correct termination.

**Unit tests** (add to `test_walker_logic.py`; use `FakeTransport` with scripted `ExchangeIO` responses built via `encode_v3_response`):

| Scenario | Outcome |
|----------|---------|
| `WalkSettings(snmp_version="3")` | `ValueError` containing "v3_user" |
| `WalkSettings(snmp_version="3", v3_user="x", bulk_size=0)` | `ValueError` containing "bulk_size" |
| v3 walk: header | `header.snmp.version.value == "3"` |
| v3 walk: first exchange | `seq == 1`, `request.pdu.value == "discovery"`, `request.oids == []` |
| v3 walk: second exchange | `seq == 2`, `request.pdu.value == "getbulk"` |
| v3 walk: discovery no-response, `give_up_after=1` | `summary.end_reason == "unresponsive"` |

**Integration test** (add to `test_walker.py`):

| Scenario | Outcome |
|----------|---------|
| v3 walk over emulator, 20 OIDs | `end_reason == "completed"`, `oids_seen == 20`, first exchange is discovery, all records schema-valid |

**Interfaces:**
```python
# WalkSettings additions:
snmp_version: Literal["1", "2c", "3"] = "2c"  # extend existing field
v3_user: str | None = None                      # required when snmp_version == "3"
# __post_init__: raise ValueError if snmp_version == "3" and v3_user is None
# __post_init__: raise ValueError if snmp_version == "3" and bulk_size < 1
```

`walk_records` v3 sequence: before the main loop, if `snmp_version == "3"`, perform discovery via `encode_v3_discovery` + `transport.exchange` + `decode_v3_message`, yield the exchange as seq=1 with `pdu="discovery"` and `oids=[]`. If no response or Malformed and `consecutive_no_response >= give_up_after`, set `end_reason = UNRESPONSIVE` and skip the main loop. Otherwise extract `V3Params` and start the GetBulk loop at seq=2 using `encode_v3_getbulk` / `decode_v3_message`.

- [ ] Write failing unit tests → FAIL. Implement `WalkSettings` additions and `walk_records` v3 branch. Run unit tests → PASS. Write integration test → PASS. Run `just test` → PASS. Commit.

---

### Task 8: CLI v3 wiring + walker-vs-snmpwalk crosswalk

> **Model: haiku** — remove stub, wire settings; crosswalk mirrors `test_snmpbulkwalk_crosswalk`.

**CLI tests** (replace `test_walk_v3_not_implemented` in `test_cli.py`; use existing `EmulatorThread`):

| Scenario | Outcome |
|----------|---------|
| `walk v3 <host> --user noAuthUser --timeout 1.0 --retries 1` | exit 0, one trace file, `header.snmp.version == "3"` |
| same with `--auth-proto SHA --auth-pass x` | exit 0, warning containing "noAuthNoPriv" printed to stderr |

**Crosswalk test** (add to `test_reference_tools.py`):

| Scenario | Outcome |
|----------|---------|
| our v3 OID sequence vs `snmpwalk -v3 -u noAuthUser -l noAuthNoPriv` on same emulator | `our_oids == ref_oids[:len(our_oids)]` (trap #13 — same prefix rule as v2c crosswalk); `len(set(our_oids)) == device_size`; skip discovery exchange when parsing trace |

**Interfaces:**
- Remove the `if args.version == "v3": print(...); return 2` block.
- Add v3 branch building `WalkSettings(snmp_version="3", v3_user=args.user, bulk_size=10, ...)`. Warn to stderr if any of `args.auth_proto`, `args.auth_pass`, `args.priv_proto`, `args.priv_pass` are set. Update CLI docstring to remove "not yet implemented".

- [ ] Write failing CLI tests → FAIL. Implement CLI branch. Run `just test` → PASS. Write crosswalk test → `REQUIRE_REFERENCE_TOOLS=1 just test-all` → PASS. Commit.

---

### Review checkpoint

> **Model: opus** — quality review.

Run `just ci` (ruff → pyrefly → vulture → pytest). Expected: clean pass.

Verify manually:

| Command | Expected |
|---------|----------|
| `oidtrace walk v3 127.0.0.1 --user noAuthUser --timeout 2.0` | trace written, `end_reason=completed`, first exchange is discovery |
| `oidtrace walk v3 127.0.0.1 --user noAuthUser --auth-proto SHA --auth-pass x` | warning on stderr, walk proceeds |
| `oidtrace walk v2c 127.0.0.1 --timeout 1.0 --retries 1` | unchanged behaviour |

#### Test review

Spawn a review agent (model: opus) against all v3-related test additions with this prompt:

---

Apply the following checklist. For each item, cite the specific test(s) affected and explain concretely why it is or is not a problem. Do not flag issues already caught by the type checker or linter.

**Anti-patterns:**
- **Always-passing tests** — would the fuzz roundtrip tests catch a symmetric field swap (e.g. engine_boots and engine_time swapped in encode/decode)?
- **Vague failure messages** — if a test fails, does pytest output tell you what went wrong without reading source?
- **Fixture soup** — do any walker unit tests start an emulator when `FakeTransport` suffices?
- **Wrong level** — do any tests patch private functions or reach into argparse internals?

**Red flags to answer explicitly:**
1. Does `pdu: "discovery"` and `oids: []` flow intact from codec → walker → trace file? Is there a test that would catch it being recorded as `pdu: "getbulk"` instead?
2. Is there a test that catches a regression where the walker sends a real GetBulk without waiting for discovery (i.e. `v3_params is None` but the loop runs anyway)?
3. Does `test_bit_flip_never_raises` exercise mutations that reach the USM body, or do most mutations fail at the outer SEQUENCE tag before getting deeper?

Conclude with: a short list of issues to fix (must-fix / nice-to-have), and a one-line verdict.

---

Only proceed to merge once `just ci` is clean, all manual checks pass, and the review raises no must-fix issues.
