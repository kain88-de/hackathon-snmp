# OIDTrace Executable Spec Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire oidtrace's narrative design/plan docs by converting every testable claim into
`spec_*.robot` coverage (rarely, a pytest unit test) and every non-testable claim into a new
`oidtrace/README.md`, following the exact audit-and-retire convention already used for
`traceformat` and `oidviz` (and, within oidtrace itself, for RFC 7860).

**Architecture:** Wire `robot` into `just ci` first (Task 1), so every task after it lands as a
commit CI actually checks — not a big-bang integration at the end, same convention as the oidviz
acceptance-test plan. Then apply one repeatable recipe — audit claims against current code/tests,
categorize each as covered/gap/stale, fill gaps as Robot Framework scenarios (default) or pytest
(rare fallback), move rationale to the new README, delete the doc(s) — once per topic, across the
remaining four tasks. Each topic's spec doc and its paired historical implementation plan (in
`docs/superpowers/plans/`) retire together, since both are now redundant with the same
code+tests+README.

**Tech Stack:** Robot Framework (`oidtrace/tests/robot/`), pytest (`oidtrace/tests/{unit,integration}/`),
`OidtraceLibrary.py` keyword library, `just robot` / `just ci`.

## Global Constraints

- Default target for any observable claim is a `spec_*.robot` scenario, not a pytest unit test —
  reserve pytest only for claims with no possible CLI/emulator-observable manifestation (e.g.
  Hypothesis codec fuzzing).
- `just ci` (from `oidtrace/`) must be green after every task's commit, not just at the end. After
  Task 1, `just ci` includes the fast robot tier — verify both `just robot` and `just ci` per task.
- A doc is deleted only once every one of its claims has a confirmed home: an existing test, a
  newly added test, or a `oidtrace/README.md` section. No stub, no "Backlog" landing spot — git
  history is the record, matching the traceformat/oidviz precedent.
- Out of scope: `docs/superpowers/specs/2026-06-11-doctor-mvp-design.md` (unbuilt, separate
  component, still draft) stays untouched. findings.md finding #2 (late-UDP-response
  misattribution, `transport.py:245-283`) is not fixed here — flagged as a separate follow-up.
  Adding a GitHub Actions CI workflow for oidtrace (there currently isn't one — only `oidviz-ci.yml`
  exists) is also not fixed here; this plan only wires the local `just ci`.
- New Robot scenarios follow the `spec_rfc7860.robot` convention: `[Tags]`, `[Documentation]`
  citing the doc/RFC section being replaced, `[Teardown]` cleaning up any started emulator/snmpd.

---

## Task 1: Wire `robot` into `just ci`

**Files:**
- Modify: `oidtrace/Justfile`
- Modify: `oidtrace/tests/robot/spec_rfc7860_reference.robot`

Right now `just ci` is `lint types deadcode test` — it never runs the robot suite at all. Separately,
`just robot` runs all 22 scenarios unfiltered, including the 2 `reference_tools`-tagged ones in
`spec_rfc7860_reference.robot` that need `snmpd`/`snmpwalk` installed — unlike the pytest side,
which already splits `test` (`-m "not reference_tools"`) from `test-all`
(`REQUIRE_REFERENCE_TOOLS=1`). `spec_rfc7860_reference.robot`'s own doc comment (line 16) even
claims a `just robot-reference` target exists — it doesn't; this task adds it for real.

- [ ] Confirm the current gap: `grep -n "^ci:\|^robot" oidtrace/Justfile` shows `ci` has no `robot`
      dependency, and `robot` has no `--exclude`/`--include` filtering.
- [ ] Edit `oidtrace/Justfile`'s `robot` recipe to exclude `reference_tools` by default, and add a
      `robot-reference` recipe for the tools-required tier (mirrors the existing `test`/`test-all`
      split):

  ```
  robot:
      uv run robot --pythonpath src --pythonpath . --pythonpath tests/robot --exclude reference_tools tests/robot/

  robot-reference:
      uv run robot --pythonpath src --pythonpath . --pythonpath tests/robot --include reference_tools tests/robot/
  ```

- [ ] Add `robot` to the `ci` recipe: `ci: lint types deadcode test robot`.
- [ ] Fix `spec_rfc7860_reference.robot` line 16 — replace
      `Run with: just robot-reference   (or: REQUIRE_REFERENCE_TOOLS=1 just robot)` with
      `Run with: just robot-reference` (the env-var form never existed as a real mechanism; only
      document the target that's actually implemented above).
- [ ] Run `cd oidtrace && just robot` — confirm the 20 non-reference scenarios pass and neither
      `reference_tools`-tagged scenario runs.
- [ ] Run `cd oidtrace && just robot-reference` — if net-snmp is installed, confirm both pass. If
      not installed, expect a hard failure (Robot has no skip-by-tag-if-tool-missing mechanism the
      way pytest's marker+guard does) — that's a pre-existing limitation, not something this task
      fixes; note it and move on.
- [ ] Run `cd oidtrace && just ci` — confirm green, now covering the fast robot tier.
- [ ] Commit:

  ```bash
  git add oidtrace/Justfile oidtrace/tests/robot/spec_rfc7860_reference.robot
  git commit -m "ci(oidtrace): wire robot's fast tier into just ci, add robot-reference target"
  ```

---

## The Recipe (apply once per topic, Tasks 3-5)

1. Read the spec doc (and its paired plan doc, if any) fully. Write a numbered checklist of every
   claim describing observable behavior.
2. For each claim, grep `oidtrace/tests/robot/*.robot` and `oidtrace/tests/{unit,integration}/` for
   existing coverage. Categorize: **COVERED** (cite scenario/test), **STALE** (doc says X, code/tests
   say Y), or **GAP**.
3. For each GAP: add a Test Case to the best-fitting existing `spec_*.robot` file, or create a new
   `spec_<topic>.robot` if none fits. Add new `OidtraceLibrary.py` keywords only when no existing
   keyword expresses the scenario — keep them thin wrappers, matching the existing
   `Start Emulator With *` style.
4. For each STALE claim: make the README describe reality; fix or remove any test that still
   asserts the old (wrong) behavior.
5. Move every remaining non-testable claim (rationale, alternatives-considered, de-scoping
   reasoning) into `oidtrace/README.md`.
6. Run `just robot` then `just ci` from `oidtrace/`. Both green.
7. `git rm` the spec doc and its paired plan doc (if fully accounted for). Fix any dangling
   cross-reference to the deleted doc elsewhere in the repo. Commit.

Example Test Case shape to match (from `spec_rfc7860.robot`):

```robot
<Doc/RFC Reference> - <Behavior Being Asserted>
    [Tags]    <topic>    <version>
    [Documentation]    <ties this scenario to the claim it replaces>
    Start Emulator With Auth User    sha256user    SHA-256    testpass256
    Walk V3 With Auth    sha256user    SHA-256    testpass256
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator
```

---

## Task 2: Retire the SHA-256 plan + fix the RFC 7860 overclaim *(model: Sonnet)*

**Files:**
- Modify: `oidtrace/tests/robot/spec_rfc7860.robot`
- Modify: `oidtrace/tests/support/emulator.py` (`Quirks` dataclass, `_handle_v3`)
- Modify: `oidtrace/tests/robot/OidtraceLibrary.py`
- Delete: `docs/superpowers/specs/2026-06-29-sha256-auth-implementation-plan.md`

The mechanical quick win: the plan's 7 phases are already delivered in code, and its living spec
(`spec_rfc7860.robot`) already exists and passes. The one real gap: the spec's own Documentation
text overclaims that oidtrace "verifies responses" — it doesn't (`walker.py:476-477` deliberately
skips response MAC verification: "diagnostic tracer, not a security client").

- [ ] Confirm each phase's deliverable is in place:
      `grep -n "class AuthProto" oidtrace/src/oidtrace/auth.py` shows a `StrEnum` with
      `hash_algo`/`key_length`/`mac_length` properties; `grep -n "proto: AuthProto"
      oidtrace/src/oidtrace/codec.py` shows `verify_auth`, `encode_v3_getbulk`,
      `encode_v3_response` all take it; `grep -n "AuthProto(" oidtrace/src/oidtrace/cli.py` shows
      the CLI constructing it from `--auth-proto`.
- [ ] Run `cd oidtrace && just robot` — confirm all 5 `spec_rfc7860.robot` scenarios pass.
- [ ] In `oidtrace/tests/support/emulator.py`, add a quirk to `Quirks` (around line 52-61):

  ```python
  @dataclass(frozen=True, slots=True)
  class Quirks:
      """Behavioral modifiers for an EmuDevice."""

      fixed_request_id: int | None = None
      end_of_mib: EndOfMib = EndOfMib.EOM
      duplicate_responses: bool = False
      slow_prefix: Oid | None = None
      per_oid_delay_s: float = 0.0
      drop_all: bool = False
      corrupt_auth_responses: bool = False
  ```

- [ ] In `_handle_v3`, everywhere `authenticate_msg(response, auth_kul, auth_proto)` is called
      (the GetNext branch around line 302-304, and the mirroring GetBulk branch further down),
      sign with a deliberately wrong key when the quirk is set, so the MAC is well-formed but
      invalid:

  ```python
  if needs_auth:
      assert auth_kul is not None and auth_proto is not None
      sign_kul = (
          auth_kul[:-1] + bytes([auth_kul[-1] ^ 0xFF])
          if self._device.quirks.corrupt_auth_responses
          else auth_kul
      )
      response = authenticate_msg(response, sign_kul, auth_proto)
  ```

- [ ] In `OidtraceLibrary.py`, import `Quirks` alongside the existing `EmulatorThread` import, and
      add a keyword next to `start_emulator_with_auth_user` (around line 68-75):

  ```python
  @keyword("Start Emulator With Auth User And Corrupted Responses")
  def start_emulator_with_auth_user_and_corrupted_responses(
      self, username: str, proto: str, password: str
  ) -> None:
      auth_proto = AuthProto(proto.upper())
      kul = password_to_key(password.encode(), EMU_ENGINE_ID, auth_proto)
      auth_users = {username.encode(): (auth_proto, kul)}
      self._emulator = EmulatorThread(
          quirks=Quirks(corrupt_auth_responses=True), auth_users=auth_users
      )
      self._host, self._port = self._emulator.__enter__()
  ```

- [ ] In `spec_rfc7860.robot`, fix the Settings Documentation's last line — replace "and verifies
      responses for SHA-256 auth users." with "and correctly signs outgoing requests for SHA-256
      auth users. oidtrace does not verify inbound response authenticity — see the
      known-limitation scenario below."
- [ ] Add the new Test Case:

  ```robot
  RFC 7860 §2.1 - Tampered Response Authenticity Is Not Verified (Known Limitation)
      [Tags]    rfc7860    v3    auth    known-limitation
      [Documentation]    oidtrace authenticates its own outgoing requests but deliberately
      ...                does not verify inbound response authenticity (walker.py:
      ...                "diagnostic tracer, not a security client"). This documents that
      ...                a response signed with the wrong key is still accepted and the
      ...                walk completes normally. Intentional current behavior, not a
      ...                defect this spec expects fixed.
      Start Emulator With Auth User And Corrupted Responses    sha256user    SHA-256    testpass256
      Walk V3 With Auth    sha256user    SHA-256    testpass256
      Trace Should Have End Reason    completed
      [Teardown]    Stop Emulator
  ```

- [ ] Run `just robot` — confirm the new scenario and all pre-existing ones pass.
- [ ] Run `just ci` — confirm green.
- [ ] `git rm docs/superpowers/specs/2026-06-29-sha256-auth-implementation-plan.md`. Commit.

---

## Task 3: `oidtrace-architecture-design.md` — the foundational doc *(model: Opus)*

**Files:**
- Modify: `oidtrace/tests/robot/*.robot` (likely `spec_cli.robot`, `spec_rfc3416.robot`; new files
  as needed, e.g. `spec_crash_safety.robot`)
- Modify: `oidtrace/tests/robot/OidtraceLibrary.py` (new keywords as needed)
- Create: `oidtrace/README.md`
- Modify: `traceformat/trace-format.md:6-8`
- Delete: `docs/superpowers/specs/2026-06-11-oidtrace-architecture-design.md`
- Delete: `docs/superpowers/plans/2026-06-11-oidtrace.md`

Apply the Recipe to the 308-line architecture doc. Known starting points from the brainstorm
(confirm and extend during the audit — this list is not exhaustive):

| Claim | Starting hypothesis | Where to check |
| --- | --- | --- |
| System-OID allowlist (sysDescr/sysObjectID/sysUpTime) | Doc calls it "post-MVP, not emitted" — but `TODO.md` says oidviz's display of this data shipped 2026-06-30. Likely STALE: probably implemented. | `grep -rn "system_info\|sysDescr\|hide.system.info" oidtrace/src/` |
| Ctrl-C → `end_reason: interrupted`, exit 0 | Likely GAP — no obvious SIGINT test found during the brainstorm. | `grep -rln "SIGINT\|KeyboardInterrupt" oidtrace/tests/` |
| Walk termination modes (end-of-MIB, subtree-exit, OID-loop, time-budget) | `spec_rfc3416.robot` covers completed/loop/unresponsive/v1-getnext — subtree-exit and time-budget look uncovered. | Cross-reference the `EndReason` type against `spec_rfc3416.robot`'s scenarios |
| Transport never validates responses (wrong request-id/duplicate/late replies recorded, not dropped) | Likely COVERED via `spec_rfc3416.robot`'s request-id-mismatch scenario — confirm it asserts the walk *continues*, not just that a violation is recorded. | `oidtrace/tests/robot/spec_rfc3416.robot` |
| Codec never raises on malformed input | COVERED (Hypothesis fuzz, per the doc's own Testing section) — stays pytest; this is the Recipe's rare fallback case. | `grep -rl hypothesis oidtrace/tests/unit/` |
| Settings-matrix CLI convenience, multi-`--start-oid`/`--resume` | Check whether these shipped at all. If not, this becomes a README "not implemented" note, not a test gap. | `grep -n "matrix\|resume_from\|--resume" oidtrace/src/oidtrace/cli.py` |

- [ ] Run the audit (Recipe steps 1-2) against the full doc — every section (Purpose, Trace format
      decision, Components, CLI usability, Transport, Codec, Walk engine, Raw capture, Trace
      writer, Packaging, Error handling, De-scoping order, Out of scope), not just the table above.
- [ ] For each GAP, write the Robot Test Case (Recipe step 3).
- [ ] For each STALE claim, correct the record (Recipe step 4) — the README states current reality.
- [ ] Create `oidtrace/README.md`, mirroring `traceformat/README.md`'s structure (short intro, then
      focused sections, no speculative "Backlog"): what/why, trace-format decision rationale (why
      JSONL over CBOR/pcapng/protobuf), adoption thesis, capture-scope guidance, current
      de-scoping/limitations (corrected per the audit), out-of-scope items, a pointer to
      `just test`/`just robot`/`just ci` and the robot-over-unit-test convention for future spec
      claims.
- [ ] Update `traceformat/trace-format.md:6-8` — replace the
      `superpowers/specs/2026-06-11-oidtrace-architecture-design.md` pointer with a pointer to
      `oidtrace/README.md`.
- [ ] Run `just robot` then `just ci` from `oidtrace/`. Green.
- [ ] Confirm `docs/superpowers/plans/2026-06-11-oidtrace.md` (236 lines) is now fully redundant
      with code+tests+README. If anything genuinely isn't, prefer leaving it out of the README
      entirely (matching commit `fa5c679`'s "a README documents the package as built, not
      speculative future work") rather than adding a Backlog section — rely on git history.
- [ ] `git rm` both `docs/superpowers/specs/2026-06-11-oidtrace-architecture-design.md` and
      `docs/superpowers/plans/2026-06-11-oidtrace.md`. Commit.

---

## Task 4: `snmp-versions-cli-design.md` — reconcile the stale v1/v3 claims *(model: Sonnet)*

**Files:**
- Modify: `oidtrace/tests/robot/spec_cli.robot` (or a new `spec_cli_versions.robot`)
- Modify: `oidtrace/README.md` (append)
- Delete: `docs/superpowers/specs/2026-06-25-oidtrace-snmp-versions-cli-design.md`
- Delete: `docs/superpowers/plans/2026-06-25-oidtrace-snmp-versions-cli.md`
- Delete: `docs/superpowers/plans/2026-06-26-oidtrace-snmp-v1.md`

Apply the Recipe. This doc (2026-06-25) predates both SNMPv3 (2026-06-26) and SHA-256 (2026-06-29)
— expect significant staleness.

| Claim | Starting hypothesis | Where to check |
| --- | --- | --- |
| `walk v1`/`walk v3` → "not yet implemented", exit 2 | STALE — both are implemented now. Check for a leftover test still asserting the old stub message and remove/update it. | `grep -rn "not.yet.implemented" oidtrace/` |
| `--auth-proto` accepts MD5/SHA/SHA-224/SHA-256/SHA-384/SHA-512 | STALE — cross-check against the actual `AuthProto` enum members; only a subset is real. | `oidtrace/src/oidtrace/auth.py` |
| Security level inferred from supplied creds (noAuthNoPriv/authNoPriv/authPriv) | noAuthNoPriv and authNoPriv are exercised (`spec_rfc3414.robot`, `spec_rfc7860.robot`); authPriv is very likely unimplemented (priv crypto out of scope) — confirm, note as a README limitation, not a test gap. | `oidtrace/src/oidtrace/cli.py` |
| `walk` with no version → prints help, exit 2 | Likely still true — confirm it's tested. | `oidtrace/tests/robot/spec_cli.robot` |
| Shared-options defaults table (timeout 2.0, retries 2, give-up-after 3, etc.) | Confirm each default still matches `cli.py`'s argparse definitions exactly. | `oidtrace/src/oidtrace/cli.py` |

- [ ] Run the audit against the full doc.
- [ ] Write Robot Test Cases for confirmed gaps; remove/update any test still encoding the old
      "not yet implemented" stub behavior for v1/v3.
- [ ] Append a section to `oidtrace/README.md` covering the current CLI version-subcommand shape
      and the noAuthNoPriv/authNoPriv/authPriv support matrix (correcting the aspirational parts).
- [ ] Run `just robot` then `just ci`. Green.
- [ ] `git rm` all three files (the spec and both paired plans) once accounted for. Commit.

---

## Task 5: `snmpv3-noauthnopriv.md` — mostly covered, close the remainder *(model: Sonnet)*

**Files:**
- Modify: `oidtrace/tests/robot/spec_rfc3414.robot`
- Modify: `oidtrace/README.md` (append, if anything non-testable remains)
- Delete: `docs/superpowers/specs/2026-06-26-oidtrace-snmpv3-noauthnopriv.md`
- Delete: `docs/superpowers/plans/2026-06-26-oidtrace-snmpv3-noauthnopriv.md`

Apply the Recipe. `spec_rfc3414.robot`'s 3 existing scenarios (discovery recorded, walk completes,
discovery failure) likely cover most of this doc already — this task closes the remainder, not
building from scratch.

| Claim | Starting hypothesis | Where to check |
| --- | --- | --- |
| `bulk_size=0` invalid for v3 (`WalkSettings.__post_init__` rejects it) | Check whether this validation exists and is tested. | `oidtrace/src/oidtrace/walker.py` (`__post_init__`) |
| `v3_user` required when `snmp_version == "3"` | Check validation + test coverage. | `oidtrace/src/oidtrace/walker.py`, `oidtrace/tests/robot/spec_cli.robot` |
| Auth/priv flags "silently ignored with a warning" when unsupplied | STALE — true before SHA-256 shipped; auth is real now. Check current behavior when only `--priv-proto` is supplied without auth (priv alone is still unimplemented). | `oidtrace/src/oidtrace/cli.py` |
| Discovery response (Report PDU, 0xA8) not flagged as a PDU-tag-mismatch violation | Check `check_exchange` doesn't validate `response_pdu_tag`, and that this is exercised by a scenario. | `oidtrace/src/oidtrace/walker.py` (`check_exchange`), `spec_rfc3414.robot` |

- [ ] Run the audit against the full doc.
- [ ] Write Robot Test Cases for confirmed gaps in `spec_rfc3414.robot`.
- [ ] Append any remaining non-testable rationale to `oidtrace/README.md`.
- [ ] Run `just robot` then `just ci`. Green.
- [ ] `git rm` both files. Commit.

---

## Self-Review Notes

Every doc in scope has a task; each task's "confirm before delete" step enforces the Global
Constraint that nothing gets deleted with unaccounted-for claims. `oidtrace/README.md` is created
once (Task 3) and appended to (Tasks 4-5), avoiding four separate landing spots. The
`traceformat/trace-format.md` cross-reference is fixed in Task 3 so no dangling link survives that
deletion. `doctor-mvp-design.md` and findings.md #2 are named explicitly as non-goals so no task's
audit accidentally "fixes" either. CI wiring (Task 1) is sequenced before any doc-by-doc work,
matching the oidviz acceptance-test plan's convention.

#### Test review *(model: Opus)*

Spawn a review agent after all five tasks land, with this prompt:

---

Review every `spec_*.robot` scenario added or modified in this plan, plus `oidtrace/README.md`.
For each new scenario, cite it and answer:

1. Does its `[Documentation]` accurately describe current behavior — not aspirational or
   original-design behavior that drifted?
2. Does it fail for a reason someone can act on (a real, checkable assertion — not a tautology)?
3. Is `known-limitation`-tagged content clearly distinguished from behavior the suite expects to
   hold?
4. Does `oidtrace/README.md` describe the codebase as built, not speculative future work (no
   reintroduced "Backlog")?
5. Cross-check: does anything in the repo still reference a deleted doc's path
   (`grep -rn` for each deleted filename)?

Conclude with a must-fix / nice-to-have list and a one-line verdict.
