# OIDViz Streaming Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate `parser.worker.ts`'s full-size intermediate copies (gzip chunk array, merged
buffer, decoded string, split-lines array) by rewriting its decompress+parse path to stream and
dispatch records line-by-line, cutting peak memory during trace parsing from ~4-5x to ~1x the
decompressed trace size.

**Architecture:** Fold `readAllChunks` + `decompressGzip` + the split/filter loop into a single
streaming `parseTrace` that decodes each `DecompressionStream` chunk incrementally
(`TextDecoder({stream: true})`) and dispatches complete lines immediately into the existing
per-record-type switch. An unparseable line now cancels the stream immediately (oidtrace only ever
appends, so nothing valid follows a bad line) instead of finishing decompression before discovering
the trace was cut short.

**Tech Stack:** TypeScript, Web Streams API (`DecompressionStream`, `TextDecoder`), the existing
Playwright e2e fixtures as the regression oracle. Full design context:
`docs/superpowers/specs/2026-07-08-oidviz-streaming-parser-design.md`.

## Global Constraints

- Only `oidviz/src/lib/parser.worker.ts` changes. No new fixtures, no size-limit guard — see the
  design doc's Scope section for why those are explicitly out.
- All 5 existing e2e fixtures (`canonical`, `no-summary`, `unknown-record-type`, `truncated`,
  `not-gzip`) must produce identical `ParseResult` behavior to today. This is a memory-shape
  change only, never an output change.
- The writer/reader pair on the `DecompressionStream` must keep running concurrently
  (`Promise.all`), never sequentially — sequencing them deadlocks via backpressure (see the
  `CRITICAL` comment already in the file, which carries over unchanged).
- `just hook` (from `oidviz/`) must stay green; `just ci` (adds Playwright e2e + a11y) is the
  final gate before this is done.

## Files

- Modify: `oidviz/src/lib/parser.worker.ts`

---

## Task 1: Stream-decode and stream-parse instead of materializing full copies

**Files:**
- Modify: `oidviz/src/lib/parser.worker.ts:13-175` (removes `readAllChunks`, `decompressGzip`,
  and the body of `parseTrace`; everything else in the file — imports, constants, `truncateOid`,
  `getLastAttempt`, `mapExchange`, and the `self.addEventListener` handler at the bottom — is
  untouched)

**Interfaces:**
- Produces: `parseTrace(buffer: ArrayBuffer): Promise<ParseResult>` — same signature as today, so
  the `self.addEventListener("message", ...)` handler at the bottom of the file needs zero changes.

- [ ] **Step 1: Establish the baseline**

  Run `cd oidviz && just ci`. Confirm everything is green before touching any code — this is the
  regression oracle the rest of this task checks against.

- [ ] **Step 2: Replace `readAllChunks`, `decompressGzip`, and `parseTrace`'s body**

  Delete `readAllChunks` (lines 13-33) and `decompressGzip` (lines 35-60) entirely. Rewrite
  `parseTrace` (lines 117-175) to open the `DecompressionStream` directly instead of going through
  `decompressGzip`:

  - Move the per-record-type `switch` (header/system_info/exchange/summary) out of the old loop
    body and into a `handleLine(line)` helper that parses one JSON line, updates the same
    `header`/`summary`/`systemInfo`/`exchanges`/`truncated` locals as today, and returns `false`
    when `JSON.parse` fails (setting `truncated = true`) or `true` otherwise.
  - Drive a `pump()` loop against the stream's reader: decode each chunk with
    `TextDecoder({ stream: true })`, append to a `leftover` buffer, split on `"\n"`, pop the last
    (possibly incomplete) piece back into `leftover`, and run every complete line through
    `handleLine`. On `done`, flush the decoder and run any remaining `leftover` through
    `handleLine` as the final line.
  - Keep the existing `CRITICAL` comment and the `Promise.all([writeDone, pump()])` structure
    unchanged — the writer must still write-then-close concurrently with the reader being pumped,
    or the stream deadlocks on backpressure exactly as the comment already warns.
  - The one behavioral change: when `handleLine` returns `false`, `pump()` must call
    `reader.cancel()` and stop instead of draining the rest of the stream.

  The trap to get right: cancelling the readable side of a `DecompressionStream` also errors its
  writable side. The write promise's `.catch` must swallow exactly that self-inflicted error —
  guarded by a `stopped` flag set synchronously in the same tick as the `reader.cancel()` call, so
  there's no race with a rejecting microtask — otherwise an intentional early-stop-on-truncation
  would incorrectly surface as a hard parse error instead of a clean `truncated: true` result.

  After both promises settle, keep the existing `header === null` check and the
  `parseMs`/`ParseResult` construction unchanged.

- [ ] **Step 3: Run `just hook`**

  Run `cd oidviz && just hook` (fmt-check, lint, types, vitest unit tests). Expect green — none of
  these files import from `parser.worker.ts` directly, so this mainly confirms the new code
  type-checks and lints clean under the project's strict settings (`noUncheckedIndexedAccess`
  is why `parts.pop() ?? ""` is needed above).

- [ ] **Step 4: Run `just ci` and confirm identical behavior to the baseline**

  Run `cd oidviz && just ci`. This adds the Playwright suite, which is the actual regression check
  for this refactor since every fixture-driven behavior change would show up here:

  | Fixture | Spec | Behavior this proves survived the rewrite |
  | --- | --- | --- |
  | `canonical` | `landing.spec.ts`, `findings.spec.ts`, `facets.spec.ts`, `sidebar.spec.ts`, `oid-tree.spec.ts`, `minimap-detail.spec.ts`, `a11y.spec.ts` | A well-formed trace still parses fully and reaches the viewer with correct data |
  | `not-gzip` | `landing.spec.ts` | Genuine decompression failure (not the self-cancel path) still rejects `parseTrace` and reaches the error phase |
  | `unknown-record-type` | `landing.spec.ts` | An unrecognized `type` is still skipped without breaking the parse |
  | `truncated` | `landing.spec.ts`, `minimap-detail.spec.ts` | A bad line still triggers `truncated: true` with the earlier valid exchange kept |
  | `no-summary` | `landing.spec.ts`, `sidebar.spec.ts` | Missing summary record still falls back to derived totals |

  All tests must pass with the same pass count as the Step 1 baseline — no test silently skipped
  or newly flaky.

  **Coverage gap, confirmed by the final review:** the `truncated` fixture's bad data is a
  trailing line with no newline (`tests/e2e/test-data/generate.mjs`), so it is handled by the
  `leftover`/`done` branch, not by the new mid-stream `reader.cancel()` path — that fixture alone
  does not exercise the early-cancel behavior. No existing fixture contains a newline-terminated
  unparseable line followed by more data, so the `reader.cancel()` call and its race-free
  `stopped`-guarded `.catch` are verified by code inspection only, not by any test. Global
  Constraints forbid adding a new fixture to close this gap; it is accepted as a known,
  inspection-only-verified path rather than fixed.

- [ ] **Step 5: Commit**

  Commit `oidviz/src/lib/parser.worker.ts` with a message explaining that it held 4-5 full-size
  copies of a trace in memory at once (chunk array, merged buffer, decoded string, split-lines
  array) before parsing a single record, and that decoding/dispatching now happen incrementally
  as gzip chunks arrive — cutting peak memory to roughly the decompressed size plus the parsed
  output. Note that an unparseable line now cancels the stream immediately instead of finishing
  decompression first, since oidtrace only ever appends and nothing valid follows a bad line.
  Reference findings.md #5.

---

## Self-Review Notes

- **Spec coverage:** the design doc's two sections — the streaming rewrite and the
  cancel-on-truncation behavior — are both implemented in Task 1's single code block; the Scope
  section (no new fixtures, no size guard) is enforced by Global Constraints and by not adding
  either.
- **Placeholder scan:** none — the full replacement code is given verbatim, not described.
- **Type consistency:** `parseTrace`'s signature (`(buffer: ArrayBuffer) => Promise<ParseResult>`)
  is unchanged from the current file, so no downstream caller (the `self.addEventListener` handler)
  needs any edit.
