# Findings

This document captures a critical review of the repository as it exists today.
The goal is to create a working list of concrete issues and guardrails before
continuing with more AI-assisted development.

## Overall Assessment

The repository shows real effort around specs, tests, and tooling, but the
enforcement is not yet strong enough to safely scale AI-generated changes.

The dominant pattern is:

- strong design language
- decent test coverage in some areas
- incomplete enforcement of the contracts the repo claims to rely on

That is a dangerous combination for AI-heavy development. It creates a false
sense of safety while allowing behavioral drift in exactly the areas where the
code needs to be strict.

## Repository Map

Major components reviewed:

- `oidtrace/`: Python SNMP capture CLI and protocol stack
- `traceformat/`: shared Python trace-format models and parser surface
- `oidviz/`: Vue/TypeScript trace viewer
- `docs/`: format spec, product docs, design docs
- `.github/workflows/`: visible CI and deployment automation

## Highest-Priority Findings

### 1. OIDTrace appears to accept authenticated SNMPv3 responses without verifying response auth parameters
*DONE*

- Severity: Critical
- Status: RESOLVED (verified 2026-07-07) — reclassified as an intentional, documented limitation
- Files:
  - `oidtrace/src/oidtrace/walker.py:475-479`
  - `oidtrace/tests/robot/spec_rfc7860.robot:8-9`
  - `oidtrace/tests/robot/spec_rfc7860_reference.robot:45-50`

Why this matters:

The code path reportedly accepts SNMPv3 authenticated replies without checking
the returned `authParams`, even though the tests/spec text imply that responses
are verified.

Impact:

- forged or tampered packets may be accepted as valid authenticated replies
- traces may record attacker-controlled OIDs, violations, or end states
- the implementation may claim stronger protocol guarantees than it actually provides

Resolution:

- `walker.py` now carries an explicit comment that MAC verification is
  intentionally skipped ("diagnostic tracer, not a security client")
- `spec_rfc7860.robot`'s header states the non-verification explicitly, and a
  dedicated `known-limitation`-tagged test case ("Tampered Response
  Authenticity Is Not Verified") starts an emulator that corrupts response
  signatures and asserts the walk still completes normally — proving and
  locking in the actual behavior instead of leaving it as silent drift
- spec, code, and tests now agree; this is a documented design tradeoff, not
  a contract violation

Recommended follow-up:

- verify response authentication before accepting a v3 authenticated reply
- add a negative test proving a tampered authenticated response is rejected
- make the RFC/spec claim match the actual behavior

### 2. OIDTrace may attribute late UDP responses to the wrong request and still advance walk state
*DONE*

- Severity: Critical
- Status: RESOLVED (fixed 2026-07-07)
- Files:
  - `oidtrace/src/oidtrace/transport.py:245-277`
  - `oidtrace/src/oidtrace/transport.py:57-61`
  - `oidtrace/src/oidtrace/walker.py:503-510`
  - `oidtrace/src/oidtrace/walker.py:537-590`

Why this matters:

The transport layer appears to accept the first queued datagram for the current
exchange without robustly correlating it to the current request. The walker then
records a mismatch but can still use the payload to move the walk forward.

Impact:

- wrong OIDs can be attributed to the wrong exchange
- loop or completion detection can become incorrect
- resulting traces can look valid while being semantically wrong

Resolution:

- confirmed the gap was real and worse than a doc/code mismatch: a genuinely
  late reply to a timed-out exchange could be consumed by a *later* exchange,
  producing a false `oid-loop` verdict about an otherwise healthy, merely-slow
  agent (reproduced via a Robot scenario before the fix)
- `UdpTransport.exchange()` gained an optional `accept` predicate; a datagram
  that fails it is filed as a stray instead of being consumed as the
  response, and the wait continues within the same attempt's timeout budget
  (no retry spent) — `transport.py` still does no SNMP decoding itself
- the walker now tracks its own past request-ids and rejects a datagram
  echoing one of them as the current exchange's answer, while still accepting
  a foreign/never-sent id as data — preserving the existing RFC 3416
  fixed-request-id behavior exactly
- added a deterministic transport-level regression test and a Robot scenario
  (`spec_rfc3416.robot`, "Late Reply To A Timed-Out Exchange Must Not Corrupt
  A Later One") that reproduced the false verdict pre-fix and pass post-fix;
  full suite (392 pytest + 31 Robot tests) verified green, 3 consecutive runs

Recommended follow-up:

- require response/request correlation before a reply is allowed to influence state
- explicitly classify unmatched late packets as strays
- add a test with a delayed response from exchange N arriving during exchange N+1

### 3. Traceformat does not enforce multiple schema-critical invariants
*DONE*

- Severity: High
- Status: RESOLVED (verified 2026-07-07) — repo layout moved, gap independently closed
- Files:
  - `traceformat/src/traceformat/__init__.py:29-30`
  - `traceformat/src/traceformat/models.py:91-139`
  - `traceformat/src/traceformat/models.py:152-161`
  - `docs/trace-format.schema.json:107-109`
  - `docs/trace-format.schema.json:128-129`
  - `docs/trace-format.schema.json:147-148`
  - `docs/trace-format.schema.json:224-226`
  - `traceformat/tests/test_roundtrip.py:179-198`

Observed drift:

- `exchange.response` and `exchange.malformed` can coexist
- `getbulk` conditional fields are not fully enforced
- `attempt.error` does not force `received_at = null`
- `summary.violation_counts[*]` is not enforced non-negative

Why this matters:

This package is supposed to represent the trace-format contract. If it accepts
records the schema forbids, then downstream tools can trust invalid data.

Impact:

- schema and runtime validation disagree
- invalid traces can be treated as valid by Python consumers
- future AI changes will drift faster because the contract surface is weak

Resolution:

- the schema now lives at `traceformat/trace-format.schema.json`; a new
  `traceformat/src/traceformat/_validators.py` module hand-implements all four
  invariants above (`check_invariants()`, run inside `parse_record()`), since
  datamodel-code-generator cannot translate JSON Schema `not`/`if-then-else`
  into pydantic validators
- `traceformat/tests/test_schema_parity.py` is a dual-oracle suite: 14
  fixtures (including one negative case per invariant) validated by both
  `jsonschema` and `parse_record()`, asserting they agree — all 14 pass
- residual, documented scope decision: enforcement is at parse time, not at
  model-construction time, so an invalid `Exchange` can still be hand-built
  in Python without erroring; producers are still caught the moment anyone
  parses the output

Recommended follow-up:

- add schema-parity tests between `jsonschema` and `traceformat.parse_record()`
- add validators or a validation layer for schema-only invariants
- remove tests that currently encode invalid shapes as accepted behavior

### 4. OIDViz silently clips large detail windows
*DONE*

- Severity: High
- Files:
  - `oidviz/src/lib/minimapDraw.ts:6`
  - `oidviz/src/lib/minimapDraw.ts:256-261`
  - `oidviz/src/lib/minimapDraw.ts:284-299`
  - `oidviz/src/components/MinimapDetail.vue:406-410`

Why this matters:

The detail view height is hard-capped, but the renderer still behaves as if the
full selected row count is visible. Once the selected window grows beyond roughly
2700 rows, later rows are clipped off-canvas.

Impact:

- exchanges disappear from the UI without warning
- the detail view becomes misleading for larger traces
- users can make wrong diagnostic conclusions from incomplete data

Recommended follow-up:

- make the detail view scrollable or windowed instead of clipping silently
- add a test with a large selected range that exceeds the current canvas height
- add an explicit indicator when a view is truncated

### 5. OIDViz parser has avoidable memory amplification on large traces
*DONE*

- Severity: High
- Status: RESOLVED (verified 2026-07-10)
- Files:
  - `oidviz/src/lib/parser.worker.ts`

Why this matters:

The parser reportedly builds several full-size copies of the trace during
decompression and line splitting before parsing JSON records.

Impact:

- large trace files may stall the browser worker
- memory pressure and OOM risk increase significantly
- the viewer may fail exactly on the large traces it most needs to analyze

Resolution:

- `parseTrace` no longer drains the gzip `DecompressionStream` into a chunk
  array, merges that into one buffer, decodes it into one giant string, and
  splits that into a full line array before parsing anything — it now decodes
  each chunk incrementally (`TextDecoder({ stream: true })`) and dispatches
  complete lines to the existing per-record-type handling as soon as they
  arrive, cutting peak memory from ~4-5x to ~1x the decompressed trace size
- an unparseable line now cancels the stream immediately instead of finishing
  decompression first, since the producer only ever appends and nothing valid
  follows a bad line; a `stopped` flag set synchronously before
  `reader.cancel()` keeps that self-inflicted write-side error from
  surfacing as a false parse failure
- behavioral parity confirmed on all 5 existing e2e fixtures (`canonical`,
  `no-summary`, `unknown-record-type`, `truncated`, `not-gzip`) — this is a
  memory-shape change only, verified to produce identical `ParseResult`s
- known, accepted gap: no existing fixture contains a newline-terminated
  unparseable line followed by more data, so the new mid-stream
  `reader.cancel()` path itself is verified by code inspection, not by any
  test (see `docs/superpowers/plans/2026-07-08-oidviz-streaming-parser.md`)

Recommended follow-up:

- explicitly out of scope for this fix (see design doc): a size-limit guard
  and large-fixture parse tests with time/memory budgets were deliberately
  not added
- add a fixture covering a newline-terminated unparseable line followed by
  further data, to close the inspection-only coverage gap on the cancel path
- fail gracefully with a useful error if the trace exceeds supported limits

### 6. The repo's stated guardrails are stronger than its actual enforcement
*DONE*

- Severity: High
- Status: RESOLVED (merged 2026-07-18, PR #2)
- Files:
  - `.github/workflows/oidviz-ci.yml:1-22`
  - `.github/workflows/deploy-oidviz.yml:1-40`
  - `traceformat/Justfile:12-14`
  - `docs/dev-guidelines/web-guardrails.md:7-82`

Observed mismatch:

- visible GitHub Actions cover `oidviz`, but not obvious repo-wide Python CI
- `traceformat/Justfile` contains a committed `types` target that says:
  `SKIPPED (temporarily disabled by main session for cleanup speed — do not commit this Justfile)`
- frontend guidance says external data should be validated before entering the
  typed domain, but `oidviz` still trusts parsed record shapes by cast

Why this matters:

AI-generated repos fail when process discipline exists mainly in prose. If the
pipeline does not enforce the rule, the rule does not reliably exist.

Impact:

- contributors may assume guarantees that CI does not actually provide
- temporary bypasses can become permanent
- drift accumulates beneath a strict-looking process layer

Resolution:

- added `traceformat-ci.yml` and `oidtrace-ci.yml`, giving both packages the
  repo-wide lint/type/test coverage that previously only `oidviz` had
- hardened every workflow (`oidviz-ci.yml`, `deploy-oidviz.yml`, and the new
  ones): explicit least-privilege `permissions:`, every action pinned to a
  commit SHA, concurrency groups, `persist-credentials: false`
- added `actions-security.yml`, a zizmor scan that hard-fails CI on future
  regressions to any of the above
- added `.github/dependabot.yml` (7-day cooldown) to keep pinned SHAs current
- added CI status badges to `oidtrace/README.md`, `oidviz/README.md`,
  `traceformat/README.md`
- the committed `types: SKIPPED` bypass in `traceformat/Justfile` was already
  removed separately (pyrefly re-enabled in CI, commit `f601eb8`), prior to
  and independent of this PR

Recommended follow-up:

- enforce runtime validation at all external-data boundaries — done for
  oidviz's trace parser, see finding #16 (resolved)

## Component Reviews

### OIDTrace

General assessment:

This is the strongest component in the repo structurally. It has clear module
boundaries and the broadest test surface. It is also the highest-risk component
because protocol handling and trace correctness are its core job.

Additional findings:

#### 7. User-controlled `--label` text is used directly in output paths
*DONE*

- Severity: High
- Status: RESOLVED (fixed 2026-07-18)
- Files:
  - `oidtrace/src/oidtrace/cli.py:246-250`
  - `oidtrace/tests/robot/spec_cli.robot:79-111`
  - `oidtrace/tests/robot/OidtraceLibrary.py:475-484`

Impact:

- path traversal or directory escape is possible with separators like `/` or `..`
- file output can end up outside the intended trace directory

Resolution:

- confirmed the gap was real and worse than "path traversal is possible": a
  label containing `/` (no `..` needed, e.g. `sub/evil`) crashed the walk with
  an uncaught `FileNotFoundError` instead of a clean CLI error, and a label
  like `../escape-marker` silently wrote the trace file outside `--out`
  entirely (reproduced: the file landed directly in `/tmp` during test
  development)
- two new `spec_cli.robot` scenarios reproduced both failure modes pre-fix and
  pass post-fix; a new `No File Matching Should Exist In Out Dir Parent`
  keyword proves the trace file no longer escapes `--out`
- `main()` now rejects any `--label` containing `/`, `\`, or `..` before path
  construction, exiting 2 with a clear stderr message — same pattern as the
  existing `--start-oid`/host validation
- full suite verified green: 33 Robot + 392 pytest

Recommended follow-up:

- none — the fix is at the CLI boundary and the negative Robot cases lock in
  the behavior

#### 8. CLI numeric parameters are weakly validated and can produce nonsense behavior
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-19)
- Files:
  - `oidtrace/src/oidtrace/cli.py:68-112` (shared option definitions)
  - `oidtrace/src/oidtrace/cli.py:120-147` (`--start-oid`/host/`--label`)
  - `oidtrace/src/oidtrace/cli.py:317-323` (`--bulk-size`)
  - `oidtrace/src/oidtrace/walker.py:128-135`
  - `oidtrace/src/oidtrace/transport.py:243-245`
  - `oidtrace/src/oidtrace/walker.py:529-531`
  - `oidtrace/tests/robot/spec_cli.robot:107-152`
  - `oidtrace/tests/robot/OidtraceLibrary.py`

Examples:

- `--give-up-after 0` reportedly causes immediate termination as `UNRESPONSIVE`
- `--retries -1` reportedly results in zero sends

Impact:

- simple operator mistakes can create misleading traces
- the CLI may succeed with invalid intent instead of failing fast

Resolution:

- confirmed all three numeric parameters were worse than "weakly validated" in
  practice: `--give-up-after 0` exited 0 and reported end_reason
  `unresponsive` after exactly one exchange — even against a fully healthy,
  responding device, since walker.py's give-up check (`consecutive_no_response
  >= give_up_after`) fires unconditionally once `give_up_after` is 0;
  `--retries -1` was accepted by argparse and crashed deep inside the running
  walk with an uncaught pydantic `ValidationError` from traceformat's
  `Settings` model, only after a trace file had already been written to disk;
  `--bulk-size 0` (v2c) crashed with an uncaught `ValueError` from
  `WalkSettings.__post_init__`
- three new `spec_cli.robot` scenarios reproduced all three failure modes
  pre-fix and pass post-fix
- first pass fixed this with a post-parse `_validate_numeric_bounds` helper;
  follow-up replaced that with `click.IntRange(min=...)` on `--retries`,
  `--give-up-after`, and `--bulk-size` directly, migrating the whole CLI
  parser from argparse to Click so the bound lives at the option definition
  itself rather than in a separate validation pass — out-of-range values are
  now rejected by the option's own type before any command code runs, exiting
  2 with a stderr message naming the offending flag
  (`Invalid value for '--give-up-after': ...`); non-numeric checks
  (`--start-oid`, host resolution, `--label`) stayed as explicit post-parse
  checks since they aren't expressible as a `click.ParamType` bound
- migrating off argparse also changed how an unrecognized flag is rejected
  (`--bulk-size` on `v1`): Click reports "No such option" rather than
  argparse's "unrecognized arguments", so that pre-existing `spec_cli.robot`
  scenario's assertion and documentation were updated to match
- full suite verified green: 36 Robot + 392 pytest

Recommended follow-up:

- none — the fix is at the CLI boundary and the negative Robot cases lock in
  the behavior

#### 9. SNMPv3 auth passphrase minimum length is not enforced
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-19)
- Files:
  - `oidtrace/src/oidtrace/auth.py:49-53` (`MIN_PASSWORD_LENGTH` constant)
  - `oidtrace/src/oidtrace/cli.py:187-193` (`--auth-pass` warning)
  - `oidtrace/tests/unit/test_auth.py:91-95`
  - `oidtrace/tests/integration/test_cli.py:574-611`
  - `oidtrace/tests/robot/spec_rfc3414.robot:64-73`

Impact:

- the code accepts credentials that are reportedly non-compliant with SNMPv3 USM minimums
- emulator tests may pass while real devices fail in confusing ways

Resolution:

- confirmed the gap: `password_to_key` only rejected an empty password, never
  enforcing RFC 3414 §11.2's recommended 8-character minimum
- initial pass made a too-short `--auth-pass` a hard CLI error (exit 2), matching
  the enforcement style used for `--retries`/`--give-up-after`/`--bulk-size` in
  finding #8 — but this was reconsidered: unlike those numeric bounds, RFC 3414's
  8-character minimum is a security *recommendation* ("SHOULD"), not a wire
  requirement, and oidtrace is a diagnostic tracer, not a security-policy client
  (the same distinction already drawn in finding #1's resolution). A real device
  can be legitimately configured with a shorter passphrase, and the tool must
  still be able to trace it
- final behavior: `password_to_key` (`auth.py`) enforces nothing beyond
  non-empty, as before; `_validate_v3_auth` (`cli.py`) prints a stderr warning
  naming `--auth-pass` and the RFC 3414 §11.2 minimum when it is under 8
  characters, but the walk still proceeds — mirroring the existing
  `--priv-proto`/`--priv-pass` "not yet supported, ignored" warning style already
  in the same function
- a new unit test locks in that `password_to_key` accepts short passwords; a new
  `test_cli.py` integration test and a new `spec_rfc3414.robot` scenario
  ("RFC 3414 §11.2 - ... Still Walks, With A Warning") lock in that the CLI
  warns but still completes the walk against a matching emulator user
- full suite verified green: 37 Robot + 394 pytest

Recommended follow-up:

- none — the warning is at the CLI boundary and the new tests lock in the
  intended permissive-with-warning behavior

#### 10. The SNMPv3 discovery path appears duplicated and less validated than the main exchange path
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-19)
- Files:
  - `oidtrace/src/oidtrace/walker.py:250-260` (`_build_attempts_and_strays` helper)
  - `oidtrace/src/oidtrace/walker.py:362-438` (discovery block)
  - `oidtrace/src/oidtrace/violations.py` (`check_exchange`, now reused by discovery)
  - `oidtrace/tests/unit/test_walker_logic.py` (discovery malformed / request-id-mismatch tests)
  - `oidtrace/tests/support/emulator.py` (`Quirks.corrupt_discovery_reply`)
  - `oidtrace/tests/robot/OidtraceLibrary.py` (`Start Emulator With Corrupted Discovery Reply`)
  - `oidtrace/tests/robot/spec_rfc3414.robot`

Impact:

- discovery behavior can drift separately from normal request handling
- wrong-PDU or wrong-request discovery replies may be accepted too easily

Resolution:

- confirmed the gap: the discovery block built its own `attempts`/`strays` models
  and its own decode/malformed handling instead of sharing the main GetBulk loop's
  logic, and unconditionally recorded `violations=[]`/`malformed=None` on the
  discovery exchange no matter what came back — a malformed (BER decode failure)
  discovery reply was indistinguishable in the trace from no response at all, and
  a reply whose `request_id` didn't match ours (which the accept-predicate already
  lets through, by the same design the main loop uses for late/foreign replies)
  was silently trusted for engine-parameter derivation with no violation recorded
- de-duplicated the `attempts`/`strays` conversion into a shared
  `_build_attempts_and_strays` helper used by both the discovery exchange and
  every main-loop exchange
- the discovery block now builds a `tf.Malformed` model and appends
  `MALFORMED_BER` on decode failure, and calls the same `check_exchange` the
  main loop already uses (with `varbinds=[]`, since a Report PDU carries no
  OID-walk data) to flag `REQUEST_ID_MISMATCH`/`DUPLICATE_RESPONSE` on a
  successfully decoded reply — accept-but-flag, matching the main loop's
  existing, already-battle-tested handling of the identical condition; engine
  params are still used from a mismatched reply as before, only now visibly
  flagged instead of silently accepted as clean
- two new unit tests (`test_walker_logic.py`, via `FakeTransport`) lock in that a
  malformed discovery reply produces a `malformed` model + `MALFORMED_BER`, and
  that a foreign-request-id discovery reply produces `REQUEST_ID_MISMATCH`; a new
  emulator quirk (`corrupt_discovery_reply`) plus Robot scenario in
  `spec_rfc3414.robot` locks in the same malformed-reply behavior end-to-end
  (UNRESPONSIVE + `malformed-ber` in the trace) against a real UDP exchange
- full suite verified green: 38 Robot + 396 pytest

Recommended follow-up:

- none — discovery now shares the same violation-checking function as the main
  loop, and both the malformed and request-id-mismatch gaps are covered by tests
  at the unit and Robot-spec levels

Strengths:

- clear layering between transport, codec, walker, and trace writing
- stronger protocol-focused tests than most AI-developed repos
- evidence that privacy concerns were considered in trace content

Main testing gaps:

- no negative test proving tampered authenticated v3 responses are rejected
- no test for late-response attribution during the next exchange
- no CLI tests for hostile labels or invalid numeric bounds

### Traceformat

General assessment:

This package is small and should be one of the safest parts of the repo. Instead,
it is currently one of the most important weak points because it is supposed to
 be the contract layer.

Additional findings:

#### 11. The prose spec and the code/schema disagree on allowed format values
*DONE*

- Severity: High
- Status: RESOLVED (verified 2026-07-19) — already fixed before this review, independent of it
- Files:
  - `traceformat/trace-format.md:73` (moved from `docs/trace-format.md:70-71`)
  - `traceformat/trace-format.md:167-170` (moved from `docs/trace-format.md:161-162`)
  - `traceformat/trace-format.schema.json:64`
  - `traceformat/trace-format.schema.json:118`
  - `traceformat/src/traceformat/models.py:37-45`
  - `traceformat/src/traceformat/models.py:84-97`
  - `traceformat/tests/test_smoke.py:11-14`
  - `traceformat/tests/test_schema_parity.py:76-86` (`header-snmp-v3-sanctioned`,
    `exchange-discovery-sanctioned`)

Observed mismatch (at review time):

- prose said v1 `snmp.version` is only `"1"` or `"2c"`
- prose said `request.pdu` is only `"get"`, `"getnext"`, or `"getbulk"`
- schema, generated models, and tests also allow `"3"` and `"discovery"`

Why this matters:

Docs and runtime contract disagreeing erodes versioning discipline and lets
producers/consumers implement different assumptions.

Resolution:

- checked history: commit `62827b4` ("docs(trace-format): sanction snmp v3 and
  discovery pdu in the prose spec", 2026-07-07) already brought the prose in
  line with the schema/models — three days *before* this finding was written
  into `findings.md` (2026-07-10) — so the drift this finding describes no
  longer exists in the reviewed tree; the write-up simply lagged the fix
- verified directly: `trace-format.md` now states `snmp.version` is `"1"`,
  `"2c"`, or `"3"`, and `request.pdu` includes `"discovery"`, matching
  `trace-format.schema.json` and the generated `Version`/`Pdu` enums exactly
- the file itself also moved from `docs/trace-format.md` to
  `traceformat/trace-format.md` (finding #3's package-colocation move),
  explaining the stale paths in the original finding
- `just ci` (traceformat) re-run clean: 44 tests passed, including
  `test_schema_parity.py`'s `header-snmp-v3-sanctioned` and
  `exchange-discovery-sanctioned` cases, which pin `"3"`/`"discovery"` as
  accepted by both `jsonschema` and `parse_record()`

Recommended follow-up:

- none — prose, schema, and code already agree, and are pinned by
  `test_schema_parity.py`

#### 12. The anti-drift mechanism checks file freshness, not semantic parity
*DONE*

- Severity: Medium
- Status: RESOLVED (verified 2026-07-19) — closed as a side effect of finding #3's fix
- Files:
  - `traceformat/Justfile:24-58` (`types-fresh`, `ci`)
  - `traceformat/tests/test_schema_parity.py` (added by finding #3)
  - `traceformat/src/traceformat/_validators.py` (added by finding #3)
  - `traceformat/tests/test_smoke.py`
  - `traceformat/tests/test_roundtrip.py`
  - `traceformat/tests/test_vocab.py`

Impact (at review time):

- generated code could be up to date (per `types-fresh`'s diff check) and
  still wrong, because `datamodel-code-generator` cannot translate JSON
  Schema `not`/`if-then-else` keywords into pydantic validators
- schema-only constraints (the four invariants) could disappear without CI
  noticing, since nothing compared schema-enforced behavior against
  runtime-enforced behavior

Resolution:

- this finding's two recommended follow-ups were already delivered by finding
  #3's fix, filed independently before this finding was picked up:
  `_validators.py`'s `check_invariants()` hand-implements the four
  schema-only invariants inside `parse_record()`, and
  `test_schema_parity.py` is exactly the "schema-vs-model parity test" this
  finding asked for — 14 fixtures, each validated by both the real
  `jsonschema` validator and `parse_record()`, asserting they agree, with one
  negative fixture per invariant (`response`+`malformed`, missing getbulk
  fields, `attempt.error` with non-null `received_at`, negative
  `violation_counts`)
- re-verified directly rather than assumed: `just ci` (traceformat) passes
  clean today, 44 tests including all 14 `test_schema_parity.py` cases
- residual, accepted scope limit (same shape as finding #3's): the parity
  suite only exercises invariants someone has already encoded into
  `check_invariants()` and a matching fixture — a *new* schema conditional
  added later without a matching fixture and `check_invariants()` branch
  would not automatically be caught. This is a structural limit of testing
  by fixture rather than by schema introspection, not something left undone
  here

Recommended follow-up:

- when a new conditional/mutual-exclusion rule is added to
  `trace-format.schema.json`, add both a `check_invariants()` branch and a
  positive/negative fixture pair to `test_schema_parity.py` in the same
  change — no automatic enforcement of this exists, so it relies on reviewer
  discipline

#### 13. Generated names leak into the public API surface
*DONE*

- Severity: Low
- Status: RESOLVED (verified 2026-07-19) — already addressed by pre-existing design + finding #3's fix
- Files:
  - `traceformat/src/traceformat/models.py:37-40` (`Version.field_1`/`field_2c`/`field_3`)
  - `traceformat/src/traceformat/__init__.py:14-24` (`__all__`)
  - `oidtrace/src/oidtrace/records.py:65,74` (`tf.Version(snmp_version)`)
  - `oidtrace/src/oidtrace/walker.py:511` (`tf.Pdu("getbulk")`)
  - `traceformat/tests/test_smoke.py` (naming-pin tests already retired)

Impact (at review time):

- awkward names like `Version.field_1` and `Version.field_2c` become part of the supported API
- the library exposes codegen artifacts rather than a deliberate domain interface

Resolution:

- checked `__init__.py`'s history from its first commit (`8b6eb04`, 2026-06-12):
  `__all__` has **never** exported `Version` or `Pdu` — only the record classes
  (`Header`, `Exchange`, ...) plus `TraceRecord`/`dump_record`/`parse_record`.
  The "thin human-owned API layer" this finding's first recommended follow-up
  asked for has existed since the package was scaffolded, predating this
  finding by almost a month; `traceformat.Version`/`traceformat.Pdu` were
  never reachable at the top-level package surface
- checked every production call site (`oidtrace/src`, `traceformat/src`):
  none use the awkward member-access form (`Version.field_2c`) — both real
  construction sites use value-based construction (`tf.Version(snmp_version)`,
  `tf.Pdu("getbulk")`), which never touches the codegen-escaped names at all
- the second recommended follow-up — "avoid testing generator naming artifacts
  as if they are product behavior" — was already done independently: commit
  `275406f` (2026-07-07, part of finding #3's fix) explicitly retired
  `test_version_3_enum_value`/`test_pdu_discovery_enum_value`, the two
  `test_smoke.py` cases that pinned `Version.field_3`/`Pdu.discovery` as
  behavior-under-test, folding the underlying wire-value coverage into
  `test_schema_parity.py` instead
- residual, accepted observation (not a gap requiring action): two test
  fixtures (`oidtrace/tests/unit/test_tracefile.py:38`,
  `traceformat/tests/test_roundtrip.py:39`) still use `Version.field_2c`
  member-access to build a `Snmp` object, since a literal enum member reads
  slightly clearer than `Version("2c")` in a fixture constant — this is
  fixture-construction convenience, not a naming-artifact test, and never
  reaches the public surface or production code

Recommended follow-up:

- none — the API layer already omits these types, no production code touches
  the awkward names, and the tests that once pinned them as behavior are gone

Strengths:

- small public API surface
- clean separation of vocab concerns
- reproducible model generation path exists

Main testing gaps:

- `test_schema_parity.py` (added resolving finding #3) closed the direct
  JSON-Schema parity gap and the missing negative tests for mutual-exclusion
  and conditional field rules — see findings #11/#12
- no automatic enforcement that a *future* schema conditional gets a matching
  `check_invariants()` branch and fixture pair; this still relies on reviewer
  discipline (see finding #12's resolution)

### OIDViz

General assessment:

This frontend is better structured than most AI-built UI projects. The main risks
are around large-file behavior, unchecked external data, and canvas-heavy UX that
is harder to validate and keep accessible.

Additional findings:

#### 14. Minimap interactions appear to rescan the full trace repeatedly during hover and drag
*DONE*

- Severity: High
- Status: RESOLVED (fixed 2026-07-19)
- Files:
  - `oidviz/src/lib/minimapDraw.ts:139-194` (`getTimeRange`, `getColumnBuckets` caches)
  - `oidviz/src/lib/minimapDraw.ts:221-238,240-280,354-378` (`getWindowExchanges`, `drawMinimap`, `autoFocus` — now reuse the caches)
  - `oidviz/src/components/MinimapDetail.vue:51` (`currentWindowExchanges`)
  - `oidviz/src/components/MinimapDetail.vue:152-168` (`onMinimapHover` — now an O(1) bucket lookup)
  - `oidviz/src/components/MinimapDetail.vue:182,226-231,350` (detail hover/click read the cached window instead of recomputing it)
  - `oidviz/tests/unit/minimapDraw.test.ts` (`getTimeRange`/`getColumnBuckets` correctness + no-rescan cache tests)

Impact (confirmed):

- three independent full-trace rescans fired on pointer movement: minimap
  hover (`onMinimapHover`) ran its own `map`+min/max+`filter` over every
  exchange on every mouse-move — even with no drag in progress; dragging
  additionally re-ran `drawMinimap`'s bucket-building loop and
  `getWindowExchanges`'s `map`+min/max+filter on every mouse-move; detail-view
  hover (`onDetailHover`) recomputed the same window filter on every mouse-move
  over the detail canvas, despite the selection not having changed
  since the last `redraw()`
- `drawMinimap` and `autoFocus` additionally duplicated an identical
  column-bucketing loop, rebuilt from scratch on every call

Resolution:

- added two memoized helpers in `minimapDraw.ts`, both keyed by the
  `exchanges` array's identity via `WeakMap` (a new trace load is a new array
  reference, so the cache invalidates itself with no manual busting needed):
  `getTimeRange(exchanges)` (min/max/span, previously recomputed inline in
  four places) and `getColumnBuckets(exchanges, cols)` (per-pixel-column
  exchange groups, additionally keyed on column count so a canvas resize
  still invalidates correctly)
- `drawMinimap` and `autoFocus`'s duplicated bucket-building loops were
  replaced with calls to the shared `getColumnBuckets`; `getWindowExchanges`
  now gets its min/max/span from `getTimeRange` instead of recomputing it
  every call — all four functions' external behavior is unchanged (same
  formulas, same return values), this is a pure internal caching refactor
- `MinimapDetail.vue`'s `onMinimapHover` now does `getColumnBuckets(...)[col]`
  instead of its own O(n) filter — hover with no drag in progress is now O(1)
  against the cache instead of a full-trace rescan
- added `currentWindowExchanges`, populated only inside `redraw()` (i.e. only
  when the selection or data actually changes); `onDetailHover` and the
  detail-canvas click handler now read it directly instead of calling
  `getWindowExchanges` afresh on every pointer movement, since neither
  changes which exchanges are in view
- new unit tests (`minimapDraw.test.ts`) cover both helpers' correctness
  (bucket assignment, divide-by-zero fallback) and, as the "perf checks"
  this finding asked for, assert cache-hit behavior directly: calling either
  helper twice with the same array reference (and, for buckets, the same
  column count) returns the identical cached object, not a fresh
  recomputation — these fail if a future edit removes the memoization
- full suite verified green: `just lint`, `just types`, `just fmt-check`,
  171 vitest (unit + component) tests, 74 Playwright e2e tests, 4 a11y tests
- manually verified in a browser (dev server + Playwright) against both the
  canonical fixture and a real 5,000-exchange trace
  (`traceformat/examples/trace-5k.oidtrace.jsonl.gz`): hovering the minimap,
  dragging a selection, and hovering/clicking detail rows all behave
  correctly with zero console errors

Recommended follow-up:

- none — the redundant per-pointer-movement rescans are gone; the remaining
  O(n) work (the window filter in `getWindowExchanges`, run once per actual
  selection change) is necessary recomputation, not rebuilding a derived
  array that didn't change

#### 15. Empty minimap selections reportedly show the full trace instead of no rows
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-20)
- Files:
  - `oidviz/src/lib/minimapDraw.ts:221-238` (`getWindowExchanges`)
  - `oidviz/tests/unit/minimapDraw.test.ts` (empty-window regression test)

Impact (confirmed):

- `getWindowExchanges` filtered exchanges down to the selected time window,
  then fell back to returning the *entire* `exchanges` array whenever that
  filter matched nothing — so dragging a selection over a genuine quiet gap
  in the trace showed every exchange in the detail pane instead of none,
  making it look like the selection had no effect

Resolution:

- removed the `filtered.length > 0 ? filtered : exchanges` fallback; the
  function now always returns the filtered result, including an empty array
  when the selected window truly contains nothing
- the pre-existing `totalCols === 0 || colEnd <= colStart` early return
  (the "nothing selected yet" default view) is unchanged and still returns
  the full trace, since that is a distinct case from an explicit empty
  selection
- `drawDetail` already handled an empty `windowExchanges` array by rendering
  "No data" (used for empty traces), so no drawing-code change was needed
- rewrote the one existing unit test that had locked in the old fallback
  behavior (`getWindowExchanges > filter matching no exchanges falls back to
  returning original array`) to instead assert the window returns `[]`
- verified full suite green: `just lint`, `just types`, `just fmt-check`,
  171 vitest (unit + component) tests, 74 Playwright e2e tests, 4 a11y tests
- manually verified in a browser: built a synthetic trace with two exchange
  clusters separated by a 90s quiet gap, confirmed dragging a selection over
  the gap now shows "No data" (previously showed all 10 exchanges), while
  selecting an actual cluster still shows just that cluster's exchanges,
  with zero console errors

Recommended follow-up:

- none

#### 16. Parsed trace records are trusted by cast instead of validated at the boundary
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-20)
- Files:
  - `oidviz/scripts/gen-trace-validator.mjs` (new)
  - `oidviz/src/lib/traceValidator.gen.js` (new, generated — do not edit)
  - `oidviz/src/lib/traceValidator.gen.d.ts` (new, hand-written sidecar)
  - `oidviz/src/lib/parser.worker.ts` (`applyRecord`, `handleLine`)
  - `oidviz/Justfile` (`gen-validator` recipe)
  - `oidviz/tests/unit/parser.worker.test.ts` (new)

Impact (confirmed):

- every JSON-parsed record was assigned into application state via
  `record as unknown as Header/SystemInfo/Exchange/Summary` with no shape
  check, so a record whose declared `type` matched but whose fields didn't
  (e.g. an `exchange` with an empty `attempts` array) crashed deep inside
  `mapExchange` (`Cannot read properties of undefined (reading
  'received_at')`) instead of failing at the parse boundary
- that crash propagated out of the whole `parseTrace` promise, so a single
  malformed record anywhere in the file discarded the *entire* trace behind
  a bare error banner — worse than the existing truncation path, which
  already handled unparseable JSON lines gracefully by keeping everything
  parsed so far

Resolution:

- first pass hand-wrote type-guard validators mirroring each record's
  required fields; on review this duplicated `traceformat/trace-format.schema.json`
  by hand with no way to detect drift, so it was replaced with a generated
  validator compiled from that same schema — the same source `gen-types`
  already reads for compile-time types, now read a second time for a runtime
  check, via `ajv`'s standalone codegen (`oidviz/scripts/gen-trace-validator.mjs`,
  `just gen-validator`)
- the generator compiles one validator per record type oidviz actually
  dispatches on (`validateHeader`, `validateSystemInfo`, `validateExchange`,
  `validateSummary`) into `traceValidator.gen.js`, a dependency-free ESM
  module (no `ajv` import at runtime — `ajv` is a devDependency used only by
  the generator); `traceValidator.gen.d.ts` is a small hand-written sidecar
  giving each function a `data is Header/SystemInfo/Exchange/Summary` type
  predicate, so a passing check narrows the value for the rest of the app
  the same way the old hand-written guards did
- `record.type` is still checked as a plain string *before* picking which
  validator to call — the schema's top-level shape is a 5-way discriminated
  `oneOf`, which would reject any record whose `type` isn't one of its known
  branches, but the prose spec requires readers to silently ignore
  unrecognized record types (forward compatibility); dispatching by type
  first, then validating only the matching branch, preserves that
  requirement while still validating known types against the full schema
- this is strictly more validation than the hand-written first pass: it now
  also enforces schema invariants the hand-written version didn't attempt
  (e.g. a `getbulk` request missing `non_repeaters`/`max_repetitions`, per
  the schema's `if`/`then`), closing part of finding #3 for this one
  boundary, for free, because the schema is now executable instead of just
  read by eye
- an invalid record is still treated exactly like an unparseable JSON line:
  `truncated = true`, stop consuming further lines, keep what parsed so far
- a malformed `header` record still surfaces through the pre-existing
  "Trace file missing header record" error, rather than crashing later
  inside `Sidebar.vue`'s computed properties
- TDD: the original hand-written-validator pass was built test-first (13
  tests, watched RED, then GREEN); the swap to generated validators kept the
  two behavioral `parseTrace` integration tests as a regression guard
  throughout the refactor (both stayed green), dropped the now-obsolete
  per-function unit tests for the deleted hand-written guards, and added two
  new tests characterizing behavior the old version didn't have: the
  unrecognized-type-is-skipped guarantee, and the getbulk invariant now
  being enforced
- verified full suite green: `just lint`, `just types`, `just fmt-check`,
  175 vitest (unit + component) tests, 74 Playwright e2e tests (including
  the existing real-fixture coverage for unrecognized record types), 4 a11y
  tests
- manually verified in a browser, both before and after the generator swap:
  built a synthetic trace with 3 valid exchanges, one malformed exchange
  (`attempts: []`), then 2 more valid exchanges; the fixed code shows
  "Warning: trace was truncated" with the 3 valid exchanges and no console
  errors, while the pre-fix code (confirmed by temporarily reverting)
  crashed with "Error: can't access property \"received_at\", lastAttempt is
  undefined" and showed nothing at all

Recommended follow-up:

- none

#### 17. Virtual scroll sizing does not appear to react to resize/layout changes
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-20)
- Files:
  - `oidviz/src/composables/useVirtualScroll.ts`
  - `oidviz/tests/component/useVirtualScroll.test.ts` (new)

Impact (confirmed):

- `containerHeight` was measured once in `onMounted` and never updated
  afterward, even though it directly drives the virtualization math
  (`viewEnd = scrollTop + containerHeight`) in both consumers
  (`FindingsByCategory.vue`, `OidTree.vue`)
- reproduced with a real 5000-exchange trace in a real browser: loading the
  OID Tree view at a short window height, then growing the window/panel
  taller, left the list frozen at the row count computed from the original
  (smaller) height — a large blank area appeared below the last rendered
  row instead of more rows filling the extra space

Resolution:

- `useVirtualScroll` now creates a `ResizeObserver` on `containerEl` in
  `onMounted` (disconnected in `onUnmounted`), mirroring the pattern
  `MinimapDetail.vue` already uses for its own canvas resize handling; the
  observer's callback re-runs the same height measurement used at mount
  (extracted into a shared `measure()` function), so `containerHeight`
  stays current for the composable's two consumers with no changes needed
  to either component
- TDD: happy-dom's `ResizeObserver` is an inert no-op (`observe()` never
  calls back, `clientHeight` is always 0), so the new test stubs the global
  `ResizeObserver` with a mock that records `observe()` calls and exposes
  the stored callback; the first version of the test (asserting a
  `ResizeObserver` instance is created and observes the container) failed
  correctly against the unmodified composable, confirmed RED, then passed
  once the observer was wired in
- added a second test confirming the observer disconnects on unmount, to
  guard against a leak in the new lifecycle wiring
- verified full suite green: `just lint`, `just types`, `just fmt-check`,
  177 vitest (unit + component) tests, 74 Playwright e2e tests, 4 a11y tests
- manually verified in a real browser (not just happy-dom, which cannot
  simulate real layout/resize): loaded the 5000-exchange
  `traceformat/examples/trace-5k.oidtrace.jsonl.gz` fixture in the OID Tree
  view, resized the browser window from 500px to 1400px tall, and confirmed
  the rendered row count grew from 17 to 45 to match — before the fix
  (verified by temporarily reverting it), the same resize left the row
  count frozen at 17 with a large empty area below the list

Recommended follow-up:

- none

#### 18. Worker completion handling may allow stale results to overwrite newer state
*DONE*

- Severity: Medium
- Status: RESOLVED (fixed 2026-07-20)
- Files:
  - `oidviz/src/App.vue:36-67`
  - `oidviz/tests/component/App.test.ts` (new)

Impact (confirmed):

- `onFileSelected` terminated the previous worker but its `message`/`error`
  listeners stayed unconditionally live — if a superseded worker's result
  arrived after a newer load had already started (or finished), it would
  overwrite `state.value` with stale data, since nothing checked which
  worker a given message actually came from
- reproduced directly: mounted `App.vue` with a mock `Worker`, fired two
  file loads back to back, then had the first (superseded) worker deliver
  its result *after* the second (current) worker's own result — the stale
  message overwrote the correct one, dropping the exchange count from the
  current load's value back to the first load's

Resolution:

- each `message`/`error` listener now closes over its own `Worker` instance
  (`w`) and compares it against the module-level `worker` reference before
  applying anything; once a load is superseded, `worker` no longer points
  at the older instance, so its late-arriving listener is a no-op instead
  of clobbering state — implements the "bind handlers to a specific worker
  instance" option from the original recommended follow-up
- TDD: `tests/component/App.test.ts` stubs the global `Worker` with a
  minimal `EventTarget`-based mock exposing `terminate()`/`postMessage()`
  and a manual `emitResult()`; the stale-result test failed correctly
  against the unmodified code (exchange count regressed from the second
  load's value to the first's), confirmed RED, then passed once the
  instance check was added; a second test confirms a second load
  terminates the first worker
- verified full suite green: `just lint`, `just types`, `just fmt-check`,
  179 vitest (unit + component) tests, 74 Playwright e2e tests, 4 a11y
  tests
- manually verified in a real browser: loaded the canonical fixture
  through the drop zone and confirmed the golden path is unaffected
  (sidebar populates correctly, no console errors) — the instance check is
  a no-op for the normal single-load case, so this only guards the race,
  it doesn't change ordinary behavior

Recommended follow-up:

- none

#### 19. Accessibility is weaker than the current tooling posture suggests
*DONE*

- Severity: Low
- Files:
  - `oidviz/src/components/MinimapDetail.vue:59-68`
  - `oidviz/src/components/MinimapDetail.vue:176-197`
  - `oidviz/src/components/MinimapDetail.vue:398-413`
  - `oidviz/src/components/FindingsByCategory.vue:155-160`
  - `oidviz/src/lib/minimapDraw.ts` (`drawDetail`)
  - `oidviz/tests/component/FindingsByCategory.test.ts`
  - `oidviz/tests/component/MinimapDetail.test.ts`
  - `oidviz/tests/e2e/findings.spec.ts`
  - `oidviz/tests/e2e/minimap-detail.spec.ts`

Status: RESOLVED (fixed 2026-07-20)

Impact (confirmed):

- `FindingsByCategory.vue`'s exchange rows were clickable `div`s with no `tabindex` and no keyboard handler — a keyboard-only or screen-reader user could not reach or activate a row at all, only a mouse user could.
- `MinimapDetail.vue`'s detail canvas (the per-exchange row list) had no `tabindex` and no keyboard listener of any kind — every row was reachable only by hovering or clicking with a mouse, with zero keyboard path and zero screen-reader-visible content beyond a generic canvas label. The minimap canvas alongside it already had `tabindex` + arrow-key panning, showing the detail canvas was the more complete gap.
- Axe (WCAG 2.1 AA) coverage in `a11y.spec.ts` passes on both files today and would still pass on the pre-fix code — automated accessibility tooling does not flag "clickable element with no keyboard path", which is exactly the tooling-posture gap this finding named.

Resolution:

- `FindingsByCategory.vue`: converted each `.exchange-row` from a `<div @click>` to a real `<button type="button">` with equivalent CSS resets (matching the existing `.section-header` button pattern already used for header rows). This makes rows reachable by Tab and activatable with Enter/Space for free, and screen readers now announce them as buttons with the row's own text as the accessible name (confirmed via a Playwright accessibility snapshot: `button "1.3.6.1.2.1.2.2.1.16 1500.0ms"`).
- `MinimapDetail.vue` + `minimapDraw.ts`: the detail canvas now gets `tabindex="0"` and a keydown handler — ArrowUp/ArrowDown move a keyboard-selected row (clamped to the current window), Enter/Space emits `focus-exchange` for it (the keyboard equivalent of a mouse click). `drawDetail()` takes an optional `selectedIndex` and draws a highlight outline around that row (confirmed by reading back the canvas's pixel data at the row's top edge in a real browser: the pixel matched the alpha-blended highlight colour). A screen-reader-only `role="status" aria-live="polite"` region announces the selected row's OID, RTT, and status text, so non-sighted keyboard users get the same information sighted mouse users get from the hover tooltip.
- Followed TDD: wrote failing component tests first for each behavior (row renders as `<button>`; canvas has `tabindex="0"`; ArrowDown/ArrowUp move and clamp the selection with the live region updating; Enter emits `focus-exchange`), watched them fail for the right reason (feature missing), then implemented the minimal code to pass. Refactored `redraw()` and the new keydown handler into smaller named functions to satisfy the repo's cognitive-complexity lint budget.
- Full verification: `just lint`, `just types`, `just fmt-check`, 184 vitest tests (up from 179), 80 Playwright e2e tests including both axe a11y specs (up from 74), all green. Manually verified in a real browser: exchange rows appear as named buttons in the accessibility tree, ArrowDown on the detail canvas both draws a visible highlight and updates the live-region text, Enter fires with no console errors.

Remaining lower-priority gap (not fixed here, tracked for future follow-up):

- the minimap canvas's existing arrow-key panning (added previously) still has no screen-reader-visible announcement of the resulting selection window — a keyboard user can move it, but a non-sighted user gets no textual feedback on the new window's contents. The mouse-hover tooltip has no keyboard/AT equivalent either. This is the same class of gap as the detail canvas had, just not addressed in this pass to keep the fix scoped to the two clearest, previously-zero-support cases.

Strengths:

- parsing is moved off the main thread
- helper-level unit coverage exists
- Playwright and axe coverage are present
- strict TypeScript settings are enabled

Main testing gaps:

- no test for detail-view clipping at large row counts
- no meaningful large-trace performance budget tests
- no repeated-load race tests
- no resize-behavior tests for virtualized views
- no malformed-record validation tests

## Test Architecture Assessment

This section answers the maintainability questions directly:

- do we already have a good set of tests?
- is it easy to add tests?
- do the tests help prevent future spaghetti code?
- can a human reviewer understand what the code should do and how that is verified?

### Short answer

The repo has a better testing foundation than the bug list alone might suggest.
It is not starting from a weak place.

Current state by component:

- `traceformat`: good, compact, easy to review, easy to extend
- `oidtrace`: good coverage model and strong guardrails, but test ergonomics are starting to get unwieldy
- `oidviz`: good logic tests and decent e2e intent, but weaker UI test ergonomics and missing a middle layer between pure logic and browser flows

Overall answer:

- yes, there is already a meaningful test base
- no, it is not consistently easy to add the right kind of test everywhere
- partially, the tests help resist spaghetti code, but some structure improvements are needed now before the suite becomes hard to evolve
- mostly, a human can understand intended behavior, but some areas are much clearer than others

### What is already good

#### The repo has real test layering, not just a pile of tests

Useful structure already exists:

- `oidtrace/tests/unit/`
- `oidtrace/tests/integration/`
- `oidtrace/tests/robot/`
- `oidtrace/tests/support/`
- `traceformat/tests/`
- `oidviz/tests/unit/`
- `oidviz/tests/e2e/`

Why this matters:

This is one of the strongest anti-spaghetti signals in the repo. The code is not
being validated only through one giant integration bucket.

#### OIDTrace has the strongest behavioral guardrails

Good signs:

- unit, emulator-backed integration, reference-tool integration, and Robot specs are separate concerns
- schema validation is reused centrally: `oidtrace/tests/conftest.py:14-23`
- emulator infrastructure is centralized instead of copy/pasted: `oidtrace/tests/integration/conftest.py:17-48`, `oidtrace/tests/support/emulator.py:1-407`
- external reference-tool tests provide a partial independent oracle: `oidtrace/tests/integration/test_reference_tools.py:1-9`

This is a strong base for verifying future changes do not break protocol behavior.

#### Traceformat is small and easy to reason about

Files:

- `traceformat/tests/test_smoke.py`
- `traceformat/tests/test_roundtrip.py`
- `traceformat/tests/test_vocab.py`

Why this matters:

This package is currently the easiest part of the repo for a human to review.
There are only a few test files, their purpose is easy to infer, and the suite is
small enough that changes are easy to inspect.

#### OIDViz has a solid pure-logic test base

The frontend does one important thing right: a lot of logic lives in plain modules
under `src/lib/`, and those modules are directly unit tested.

Examples:

- `oidviz/src/lib/findings.ts`
- `oidviz/src/lib/filters.ts`
- `oidviz/src/lib/oidTrie.ts`
- `oidviz/src/lib/minimapDraw.ts`
- `oidviz/tests/unit/*.test.ts`

Why this matters:

This is one of the best protections against future spaghetti UI code. Logic that
lives outside components is easier to test, easier to review, and easier to keep
from turning into stateful template-driven behavior.

### Where the current test setup is weak

#### OIDTrace test files are getting too large

- `oidtrace/tests/unit/test_walker_logic.py:221-1291`
- `oidtrace/tests/integration/test_cli.py:29-647`
- `oidtrace/tests/unit/test_records.py:94-482`
- `oidtrace/tests/integration/test_reference_tools.py:64-543`

Problem:

The test architecture is good, but some files are becoming catch-all containers.
That makes it harder for a human reviewer to answer:

- what behavior is changing?
- where should a new test go?
- what part of the contract is this file responsible for?

This is an early warning sign for test-suite spaghetti even if the production code
is still reasonably structured.

#### OIDTrace duplicates small validation helpers and record builders

Examples:

- `oidtrace/tests/unit/test_records.py:57-65`
- `oidtrace/tests/integration/test_walker.py:32-37`
- `oidtrace/tests/unit/test_walker_logic.py:181-186`
- `traceformat/tests/test_roundtrip.py:38-102`
- `oidtrace/tests/unit/test_tracefile.py:37-67`

Problem:

The duplication is not terrible yet, but it increases friction and drift risk.
If left alone, future AI changes will likely copy an existing helper instead of
reusing a small shared factory or assertion helper.

#### OIDViz does not make full test execution obvious enough

- `oidviz/package.json:6-12`
- `oidviz/Justfile:25-37`

Problem:

`package.json` defines `test` as unit tests only. The end-to-end suite exists, but
the main entrypoint does not make that obvious.

Why this matters:

This is the kind of setup where people say “tests passed” while only running the
fast subset. That is not a good long-term guardrail for AI-driven frontend changes.

#### OIDViz reviewability is reduced by brittle e2e selectors

Examples:

- `oidviz/tests/e2e/sidebar.spec.ts:58-70`
- `oidviz/tests/e2e/sidebar.spec.ts:108-130`
- `oidviz/tests/e2e/sidebar.spec.ts:169-191`
- `oidviz/tests/e2e/landing.spec.ts:98-101`
- `oidviz/tests/e2e/landing.spec.ts:138-145`

Problem:

Some tests have good behavioral intent, but the assertions are expressed through
long CSS-structure selectors rather than stable semantic hooks.

Why this matters:

A human reviewer can understand the comment, but still has to reverse-engineer the
selector plumbing. That makes reviews slower and makes harmless markup changes look
larger or riskier than they are.

#### OIDViz is missing a component-test middle layer

Current split:

- pure logic unit tests in `oidviz/tests/unit/`
- browser e2e tests in `oidviz/tests/e2e/`

Affected component layer:

- `oidviz/src/components/Sidebar.vue`
- `oidviz/src/components/FindingsByCategory.vue`
- `oidviz/src/components/OidTree.vue`
- `oidviz/src/components/MinimapDetail.vue`

Problem:

There is little concise test coverage for component-level rendering and interaction.
That leaves a gap between “the pure helper works” and “the full browser flow works.”

Why this matters:

That gap makes UI regressions harder to localize and pushes too much verification
into slower end-to-end tests.

### Is it easy for a human to review what the code should do?

Current answer: mostly yes, but unevenly.

Best-reviewed areas:

- `traceformat/tests/*` because the suite is small and purpose-specific
- many `oidtrace` tests because they are named around protocol behaviors
- `oidviz` pure-logic tests because they exercise plain functions with direct inputs and outputs

Less reviewable areas:

- giant `oidtrace` test files where several concerns are mixed together
- `oidviz` e2e specs that rely on CSS structure details
- canvas-driven interactions where the tests can only partially assert outcomes

One good sign in the frontend is that the repo appears to care about reviewer-facing
test clarity:

- `oidviz/tests/e2e/CLAUDE.md:3-42`
- `oidviz/eslint.config.mjs:5-7`

That is a healthy instinct. It just is not fully carried through in the current
assertion style.

### Do the tests help prevent spaghetti code?

Current answer: yes, but they need reinforcement in a few places.

What helps today:

- logic is often extracted into testable modules instead of buried in UI or I/O code
- there are multiple test layers in `oidtrace`
- coverage and type-checking thresholds are fairly strict
- the repo already has the habit of writing behavior tests rather than only snapshot-like checks

What weakens that protection:

- oversized test files reduce navigability
- duplicated helpers increase copy/paste growth
- missing frontend component tests encourage logic to drift into `.vue` files without tight feedback
- partial or non-obvious test entrypoints make it easier to skip the important suite accidentally

### Practical recommendations for testability and reviewability

These are the most useful improvements if the goal is long-term maintainability,
easy human review, and less spaghetti.

#### 1. Add short testing READMEs per major component

Add:

- `oidtrace/tests/README.md`
- `oidviz/tests/README.md`
- optionally `traceformat/tests/README.md`

Each should answer:

- where should a new test go?
- what belongs in unit vs integration vs e2e?
- which helpers/factories should be reused?
- what command should a reviewer run locally?

This is low effort and high leverage for both humans and AI.

#### 2. Split the largest OIDTrace test files by behavior slice

Examples:

- split `test_walker_logic.py` by end conditions, protocol version, and retry/timeout behavior
- split `test_cli.py` into CLI success paths, validation errors, and output behavior

This will make diffs smaller and easier to review.

#### 3. Add tiny shared test factories, not a giant helper framework

Suggested targets:

- `oidtrace/tests/support/factories.py`
- `oidtrace/tests/support/assertions.py`
- `oidviz/tests/unit/helpers.ts`

Important constraint:

Keep helpers minimal. The goal is to remove repeated boilerplate, not to hide the
behavior under another abstraction layer.

#### 4. Make frontend test entrypoints explicit

In `oidviz/package.json`, add scripts like:

- `test:unit`
- `test:e2e`
- `test:all`

This makes it obvious which suite verifies what.

#### 5. Add a component-test layer to OIDViz

First candidates:

- `Sidebar.vue`
- `FindingsByCategory.vue`
- `OidTree.vue`

This would improve both reviewability and anti-spaghetti pressure by letting the
team verify UI behavior without going straight to Playwright.

#### 6. Prefer semantic test hooks over structural selectors

For the frontend:

- use accessible roles and labels first
- use stable `data-testid` only where semantics are not practical
- avoid long selectors tied to layout structure

This makes tests easier to read and less fragile under refactor.

#### 7. Add contract tests that explain behavior, not just pin branches

Especially for:

- `traceformat` schema invariants
- `oidtrace` protocol invariants
- `oidviz` parser boundary validation

These are the tests that best explain to a human reviewer what the code is
supposed to guarantee.

## Documentation and Process Findings

## Documentation and Process Findings

### 20. The README appears to contradict the current state of the repo

- Severity: Medium
- Files:
  - `README.md:78-84`

Observed mismatch:

The README says the capture layer was implemented and then deliberately deleted,
while the repo currently contains a substantial `oidtrace/` implementation.

Impact:

- readers cannot tell which docs are historical and which are current
- this lowers trust in all product and architecture documentation

Recommended follow-up:

- separate historical notes from current-state documentation
- make the README describe the current repository, not prior iteration history

### 21. The repo shows a pattern of process language outpacing enforceable controls

- Severity: Medium
- Files:
  - `docs/dev-guidelines/web-guardrails.md:53-82`
  - `traceformat/Justfile:12-14`
  - `.github/workflows/oidviz-ci.yml:1-22`

Why this matters:

This is the core AI-risk pattern in the repo. The language around quality is
better than the actual mechanisms preventing drift.

Impact:

- AI agents and human reviewers may over-trust the codebase
- defects survive because checks are aspirational instead of mandatory

Recommended follow-up:

- treat every stated guardrail as a testable control
- if a rule cannot be enforced automatically, make that explicit

## Guardrails Before More AI Development

These are the controls worth putting in place before asking AI to do more than
small, supervised changes.

### Required guardrails

1. Add repo-wide CI.

- run `oidtrace` lint, types, tests on every PR
- run `traceformat` lint, types, tests on every PR
- keep `oidviz` CI, but make it part of a single repository standard

2. Add contract parity tests.

- validate fixtures with both `jsonschema` and `traceformat.parse_record()`
- fail on any disagreement
- include negative fixtures for every schema invariant

3. Enforce runtime validation at data boundaries.

- validate trace records before they enter `oidviz` application state
- validate protocol and CLI invariants before `oidtrace` work begins

4. Ban committed bypasses.

- no committed `SKIPPED`, `temporary`, or `do not commit` workflow/type-check stubs
- review should fail immediately if such bypasses are present

5. Add large-input tests and budgets.

- large trace parse tests
- large trace interaction tests
- large detail-window rendering tests
- rough performance and memory expectations documented in CI or a benchmark job

6. Add negative protocol tests.

- tampered SNMPv3 authenticated response
- delayed response arriving during the next exchange
- malformed discovery replies
- invalid CLI boundary values

7. Make docs current or explicitly historical.

- README should describe current behavior only
- roadmap or historical notes should be labeled clearly
- format-doc changes should have an explicit review owner

## Suggested Work Order

If this document becomes the working plan, the order below is the most sensible
from a risk perspective.

1. Fix repo-wide CI coverage and remove committed bypasses.
2. Fix OIDTrace response authentication and response/request correlation.
3. Add traceformat schema-parity tests and resolve schema/model drift.
4. Add OIDViz runtime validation and fix detail-view clipping.
5. Address OIDViz large-trace performance paths.
6. Clean up docs so the stated contract matches reality.

## Final Assessment

This repository is promising, but it is not yet protected well enough for broad,
high-trust AI development.

The codebase already shows the main failure mode of AI-assisted engineering:
convincing structure with weaker-than-advertised enforcement. The right next move
is not more output volume from AI. The right next move is to harden the contract
surfaces, CI, and negative tests so future AI changes have narrower room to be
wrong.
