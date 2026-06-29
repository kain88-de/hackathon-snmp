# OIDTrace SNMP v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the SNMP v1 walker — GetNext loop, `noSuchName` termination — replacing the current exit-2 stub.

**Architecture:** `WalkSettings` gains a `snmp_version` field; `walk_records` branches on it for request encoding and termination; the emulator gains GetNext handling; `cli.py` wires the v1 branch to the real walker.

**Tech Stack:** Python stdlib asyncio, pytest, `just` for task runner.

**Spec:** `docs/superpowers/specs/2026-06-25-oidtrace-snmp-versions-cli-design.md` (v1 section only).

## Global Constraints

- SNMP v1 uses GetNext (one OID per request). No `--bulk-size` flag on the v1 CLI path.
- SNMP v1 wire: message version byte = `0` (integer). v2c uses `1`.
- End-of-MIB for v1: `error-status = 2` (`noSuchName`). No `EndOfMibView` (0x82) exception tag.
- Trace header: `snmp.version = "1"`. Settings model: `bulk_size = 0` (per trace-format.md: "0 means GetNext walk").
- v3 stub remains unchanged (exit 2, not implemented).
- `just test` must pass after every task. `just ci` must pass at the final review step.

All changes live under `oidtrace/` (`src/oidtrace/`, `tests/`).

---

### Task 1: `encode_getnext` in codec.py

> **Model: haiku** — mechanical BER encoding, clear contract.

**Tests:**

| Input | Outcome |
|-------|---------|
| `encode_getnext(42, oid)` decoded via `decode_message` | `pdu_tag == PDU_GETNEXT`, `request_id == 42`, one varbind with the original OID |
| BER version byte of `encode_getnext(1, oid)` | integer `0` (v1 wire format) |
| `encode_getnext(7, oid, community=b"private")` decoded | no error, `request_id == 7` |

**Interfaces:**
- `PDU_GETNEXT: int = 0xA3`
- `encode_getnext(request_id: int, oid: Oid, community: bytes = b"public") -> bytes` — SNMP v1 GetNext PDU; same shape as `encode_getbulk` but version byte `0`, PDU tag `0xA3`, no non-repeaters/max-repetitions fields

- [ ] Write failing tests → `just test oidtrace/tests/unit/test_codec_encode.py` → FAIL. Implement. Run `just test` → PASS. Commit.

---

### Task 2: Emulator GetNext support + smoke test

> **Model: sonnet** — async protocol dispatch, needs to reason about PDU branching and error encoding.

**Tests** (add to `test_emulator_smoke.py`; mirror the existing `_send_getbulk` helper with a `_send_getnext` variant):

| Scenario | Outcome |
|----------|---------|
| GetNext for OID before the tree | response decodes, `pdu_tag == PDU_RESPONSE`, exactly 1 varbind, `request_id` echoed |
| GetNext for last OID in the tree | response has `error_status == 2` (noSuchName), `request_id` echoed |

**Interfaces:**
- `EmuProtocol._handle`: detect GetNext by `msg.pdu_tag == PDU_GETNEXT`; cap varbind count to 1; for end-of-MIB with GetNext, reply with `error_status=2` and a Null varbind (instead of the `EndOfMibView` tag used for GetBulk)

- [ ] Write failing tests → `just test oidtrace/tests/integration/test_emulator_smoke.py` → FAIL. Implement. Run `just test` → PASS. Commit.

---

### Task 3: `snmpwalk -v1` emulator validation

> **Model: haiku** — test writing based on the existing reference-tool pattern.

Validate that `snmpwalk -v1` can successfully walk the emulator and sees the correct OID count. This tests the emulator's v1 behaviour (GetNext dispatch + `noSuchName` EOM) independently of our walker, which is not yet implemented. Add to `test_reference_tools.py` using the same `reference_tools` marker and `_require_tool` guard as the existing crosswalk. Invocation: `snmpwalk -v1 -c public -On <host>:<port> 1.3.6.1`.

**Tests:**

| Scenario | Outcome |
|----------|---------|
| `snmpwalk -v1` against a 50-OID emulator | exits successfully, output contains exactly 50 OID lines |

- [ ] Write test, run `just test-all` → PASS. Commit.

---

### Task 4: `WalkSettings.snmp_version` + settings model

> **Model: haiku** — trivial dataclass field addition and validation guard.

**Tests:**

| Input | Outcome |
|-------|---------|
| `WalkSettings()` | `snmp_version == "2c"` |
| `WalkSettings(snmp_version="1")` | accepted without error |

**Interfaces:**
- `WalkSettings.snmp_version: Literal["1", "2c"] = "2c"` — `bulk_size >= 1` validation skipped when `snmp_version == "1"`
- `_make_settings_model` emits `bulk_size=0` when `snmp_version == "1"`

- [ ] Write failing tests → `just test oidtrace/tests/unit/test_walker_logic.py` → FAIL. Implement. Run `just test` → PASS. Commit.

---

### Task 5: `walk_records` v1 branch + walker integration test

> **Model: opus** — most complex task: async generator branching, correct termination ordering, type contracts across the walker boundary.

Use `FakeTransport` (already in `test_walker_logic.py`) for unit tests. A `noSuchName` response is `encode_response(..., error_status=2)`. Integration tests go in `test_walker.py` alongside the existing v2c tests; use `emulator_factory` and `record_validator`.

**Unit tests:**

| Scenario | Outcome |
|----------|---------|
| v1 walk: one data reply, then `noSuchName` | `Header.snmp.version == "1"` |
| v1 walk: one data reply, then `noSuchName` | `Summary.end_reason == "completed"` |
| v1 walk: any exchange | `Exchange.request.pdu == "getnext"` |

**Integration test** (add to `test_walker.py`):

| Scenario | Outcome |
|----------|---------|
| v1 walk over emulator, 20 OIDs | `end_reason == COMPLETED`, `summary.oids_seen == 20`, all records schema-valid |

**Interfaces:**
- `walk_records` passes `settings.snmp_version` to `header_record`
- When `snmp_version == "1"`: encodes via `encode_getnext`; builds `Request(pdu="getnext", oids=[cursor])`; terminates `COMPLETED` when `decoded_msg.f1 == 2` — this check must happen before varbind processing

- [ ] Write failing unit tests, run → FAIL. Implement walker branch. Run `just test` → PASS. Write integration test, run → PASS. Commit.

---

### Task 6: Wire v1 in CLI + walker-vs-snmpwalk crosswalk

> **Model: haiku** — straightforward CLI wiring; crosswalk follows the existing `test_snmpbulkwalk_crosswalk` pattern exactly.

Replace `test_walk_v1_not_implemented` in `test_cli.py` with v1 smoke tests using `EmulatorThread`. Extend `test_reference_tools.py` with a full crosswalk that compares our walker's OID sequence to `snmpwalk -v1`'s output on the same live emulator.

**CLI tests:**

| Scenario | Outcome |
|----------|---------|
| `walk v1 <host> --timeout 1.0 --retries 1 --give-up-after 2` via emulator | exit 0, exactly one trace file in `tmp_path` |
| same walk, trace header read back | `header.snmp.version == "1"` |

**Crosswalk test:**

| Scenario | Outcome |
|----------|---------|
| our v1 walk OID sequence vs `snmpwalk -v1` on same emulator | sequences match (both stop on noSuchName; no overshoot unlike v2c) |

**Interfaces:**
- v1 branch in `main()` removed from "not yet implemented" guard; builds `WalkSettings(snmp_version="1", ...)` without `bulk_size`

- [ ] Write failing CLI tests → FAIL (still exit 2). Implement CLI branch. Run `just test` → PASS. Write crosswalk test, run `just test-all` → PASS. Commit.

---

### Review checkpoint

> **Model: opus** — quality review requires careful reasoning about test coverage gaps and correctness.

Run `just ci` (ruff → pyrefly → vulture → pytest). Expected: clean pass.

Verify manually:

| Command | Expected |
|---------|----------|
| `oidtrace walk v1 127.0.0.1 --community public --timeout 2.0` | Walk runs against local snmpd, trace file written, `end_reason=completed`, `oids_seen > 0` in terminal summary |
| `oidtrace walk v2c <host> --timeout 1.0 --retries 1` | Unchanged behaviour |
| `oidtrace walk v3 <host> --user public` | Exits 2, stderr names v3 + not implemented |

#### Test review

Spawn a review agent against the v1-related tests with this prompt:

---

Apply the following checklist. For each item, cite the specific test(s) affected and
explain concretely why it is or is not a problem. Do not flag issues already guarded by
the type checker or linter.

**Anti-patterns to check:**
- **Brittle mocking** — any mocks verifying call sequences rather than outcomes?
  The emulator-thread pattern is intentional; flag only unexpected `unittest.mock` usage.
- **Always-passing tests** — do assertions have a realistic chance of failing? Check
  that string-presence assertions (e.g. `"v1" in stderr`) would fail if the stub
  printed the wrong message or nothing at all.
- **Vague failure messages** — if a test fails, does pytest output tell you what went
  wrong without reading the source?
- **Fixture soup** — is `EmulatorThread` used only where a live network exchange is
  genuinely required? Flag any v1/v3 stub test that starts an emulator unnecessarily.
- **Test doing multiple things** — can each test be named in one sentence describing
  one behaviour?
- **Wrong level** — do any v1/v3 stub tests reach into argparse internals or patch
  private functions? Correct level: call `main([...])`, observe outputs.
- **Redundant assertions** — do any tests re-check what `just ci` already guarantees?

**Red flags to answer explicitly:**
1. Does every test fail for a reason someone can act on?
2. Is anything being patched that we own (beyond the emulator thread pattern)?
3. Do test names describe behaviour or mechanism?
4. Are the v1/v3 stub tests at the right level, or do they over-specify internals?

Conclude with: a short list of issues to fix (severity: must-fix / nice-to-have), and a
one-line verdict on whether the test suite earns its place.

---

Only proceed to merge once `just ci` is clean, all three manual checks pass, and the test review raises no must-fix issues.
