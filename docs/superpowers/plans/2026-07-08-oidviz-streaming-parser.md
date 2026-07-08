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

  Delete `readAllChunks` (lines 13-33) and `decompressGzip` (lines 35-60) entirely, and replace
  `parseTrace` (lines 117-175) with:

  ```ts
  function parseTrace(buffer: ArrayBuffer): Promise<ParseResult> {
  	const t0 = performance.now();

  	let header: Header | null = null;
  	let summary: Summary | null = null;
  	let systemInfo: SystemInfo | null = null;
  	const exchanges: DomainExchange[] = [];
  	let truncated = false;

  	// Returns false to tell the pump to stop feeding further lines — used
  	// when a line fails to parse. oidtrace only ever appends, so nothing
  	// valid follows a bad line; there's no reason to keep decoding.
  	function handleLine(line: string): boolean {
  		if (line.trim().length === 0) {
  			return true;
  		}
  		let record: { type: string; [k: string]: unknown };
  		try {
  			record = JSON.parse(line) as { type: string; [k: string]: unknown };
  		} catch {
  			truncated = true;
  			return false;
  		}
  		switch (record.type) {
  			case "header": {
  				header = record as unknown as Header;
  				break;
  			}
  			case "system_info": {
  				systemInfo = record as unknown as SystemInfo;
  				break;
  			}
  			case "exchange": {
  				exchanges.push(mapExchange(record as unknown as Exchange));
  				break;
  			}
  			case "summary": {
  				summary = record as unknown as Summary;
  				break;
  			}
  			default:
  		}
  		return true;
  	}

  	const ds = new DecompressionStream("gzip");
  	const writer = ds.writable.getWriter();
  	const reader = ds.readable.getReader();
  	const decoder = new TextDecoder();
  	let leftover = "";
  	let stopped = false;

  	function pump(): Promise<void> {
  		return reader.read().then(({ done, value }): Promise<void> => {
  			if (done) {
  				const finalLine = leftover + decoder.decode();
  				if (finalLine.trim().length > 0) {
  					handleLine(finalLine);
  				}
  				return Promise.resolve();
  			}
  			leftover += decoder.decode(value, { stream: true });
  			const parts = leftover.split("\n");
  			leftover = parts.pop() ?? "";
  			for (const part of parts) {
  				if (!handleLine(part)) {
  					stopped = true;
  					break;
  				}
  			}
  			if (stopped) {
  				return reader.cancel().catch((): void => {});
  			}
  			return pump();
  		});
  	}

  	// CRITICAL: read and write MUST run concurrently to avoid deadlock.
  	// Writing to the writable side blocks on backpressure if the readable
  	// side is not already being consumed.
  	const writeDone = writer
  		.write(new Uint8Array(buffer))
  		.then((): Promise<void> => writer.close())
  		.catch((err: unknown): void => {
  			// Cancelling the reader early (on a bad line) also errors the
  			// writable side — swallow only that self-inflicted case.
  			if (!stopped) {
  				throw err;
  			}
  		});

  	return Promise.all([writeDone, pump()]).then((): ParseResult => {
  		if (header === null) {
  			throw new Error("Trace file missing header record");
  		}
  		const parseMs = performance.now() - t0;
  		return { exchanges, header, parseMs, summary, systemInfo, truncated };
  	});
  }
  ```

  The trap this code has to get right: calling `reader.cancel()` on the readable side of a
  `DecompressionStream` also errors its writable side. If `writeDone`'s `.catch` didn't check
  `stopped` and swallow that specific case, an intentional early-stop-on-truncation would
  incorrectly surface as a hard parse error instead of a clean `truncated: true` result. The
  `stopped` flag is set synchronously in the same tick as the `reader.cancel()` call, before any
  microtask can reject `writeDone` — so the check is race-free.

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
  | `truncated` | `landing.spec.ts`, `minimap-detail.spec.ts` | A bad line still triggers `truncated: true` with the earlier valid exchange kept — now via the early-cancel path instead of draining to completion |
  | `no-summary` | `landing.spec.ts`, `sidebar.spec.ts` | Missing summary record still falls back to derived totals |

  All tests must pass with the same pass count as the Step 1 baseline — no test silently skipped
  or newly flaky.

- [ ] **Step 5: Commit**

  ```bash
  git add oidviz/src/lib/parser.worker.ts
  git commit -m "$(cat <<'EOF'
  fix(oidviz): stream-decode and stream-parse traces instead of materializing full copies

  parser.worker.ts held 4-5 full-size copies of a trace in memory at once
  (chunk array, merged buffer, decoded string, split-lines array) before
  parsing a single record. Decoding and line-dispatching now happen
  incrementally as gzip chunks arrive, cutting peak memory to roughly the
  decompressed size plus the parsed output. An unparseable line now cancels
  the stream immediately instead of finishing decompression first, since
  oidtrace only ever appends and nothing valid follows a bad line.

  findings.md #5.
  EOF
  )"
  ```

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
