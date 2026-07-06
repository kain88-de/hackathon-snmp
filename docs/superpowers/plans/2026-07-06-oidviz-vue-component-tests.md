# OIDviz Vue Component Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **Deviation from the usual plan format:** per explicit instruction, this plan does not embed
> code. Steps describe what to build and which tests to write in prose/tables; the implementer
> writes the actual code from that description, following existing patterns in the codebase
> (`tests/unit/*.test.ts`, `tests/e2e/*.spec.ts`, and the components under test).

**Goal:** Replace `bun:test` with Vitest across `oidviz`, and add a `tests/component/*.test.ts`
suite (Vitest + `@vue/test-utils` + happy-dom) that mounts each of the 5 leaf Vue components in
isolation and asserts its prop-in / render-and-emit-out contract.

**Architecture:** The runner swap lands first, proven against the 7 already-passing
`tests/unit/*.test.ts` files (a mechanical import-only migration), before any new test is written —
so every later task lands on a runner already known to work. Test-infra scaffolding specific to
component tests (ESLint rule extension, shared synthetic-data helpers, comment-convention doc)
lands next, once, before the first component suite needs it. Then one task per component,
simplest first, each adding its own `tests/component/<Name>.test.ts` against the *existing*
(already correct) component behavior — these are regression/contract tests for code that already
works, not TDD for new features. If a written test fails against current behavior, treat that as a
signal to stop and investigate (wrong synthetic-prop assumption, or a real latent bug) rather than
adjusting the assertion to match.

**Tech Stack:** Vue 3 + TypeScript + Bun (package manager/runtime only, no longer the test runner)
+ Vitest + `@vue/test-utils` + `happy-dom` (new) + `@vitejs/plugin-vue` (existing, reused). Full
design context: `docs/superpowers/specs/2026-07-06-oidviz-vue-component-tests-design.md`.

## Global Constraints

- No new fixture files for component tests — all props are built with plain synthetic objects via
  `oidviz/tests/component/helpers.ts`. Fixture `.gz` files stay an e2e-only concern.
- `App.vue` is explicitly out of scope — no `App.test.ts`. It's a thin Worker-wiring composition
  root; that integration is what `tests/e2e/landing.spec.ts` et al. already prove end-to-end.
- `just hook` (lint, types, fmt-check, test) must stay green after every task's commit; run
  `just ci` (adds e2e, a11y) before considering the whole plan done.
- Every `test()` under `oidviz/tests/component/**` needs a comment directly above it stating the
  synthetic prop values that matter for that case and the behavior contract being verified — same
  spirit as `oidviz/tests/e2e/CLAUDE.md`, "fixture fact" becomes "synthetic prop fact" since there's
  no fixture file. Title describes the behavior under test, not the DOM mechanism used to check it.
- Vitest's `test.include` must be explicit (`tests/unit/**/*.test.ts`, `tests/component/**/*.test.ts`)
  — its default glob also matches `*.spec.ts` and would otherwise try to run Playwright's e2e specs.
- `MinimapDetail.vue`'s draw functions (`src/lib/minimapDraw.ts`) all guard `if (!ctx) return;`
  before drawing, and `HTMLCanvasElement.getContext("2d")` returns `null` under happy-dom — so no
  canvas polyfill is needed for component tests, and no component test should assert on canvas
  pixel output (that stays `tests/unit/minimapDraw.test.ts`'s job).

## Files

- Create: `oidviz/vitest.config.ts`
- Create: `oidviz/tests/component/CLAUDE.md`
- Create: `oidviz/tests/component/helpers.ts`
- Create: `oidviz/tests/component/{LandingScreen,Sidebar,FindingsByCategory,OidTree,MinimapDetail}.test.ts`
- Modify: `oidviz/package.json`, `oidviz/Justfile`, `oidviz/eslint.config.mjs`
- Modify (import swap only): all 7 files in `oidviz/tests/unit/*.test.ts`

## Recommended models

| Task | Model | Why |
| --- | --- | --- |
| 1. Runner swap: Vitest + migrate unit tests | Opus | Foundational — every later task depends on this working correctly; config subtleties (include globs, coverage provider) can fail silently. |
| 2. Component-test scaffolding | Sonnet | Small, well-specified, but touches a shared ESLint config that already has e2e-scoped rules — must not regress those. |
| 3. `LandingScreen.test.ts` | Haiku | Fewest interactions, fully specified. |
| 4. `Sidebar.test.ts` | Sonnet | Most branches/tests of any component; several conditional-rendering edge cases need careful synthetic `ParseResult` construction. |
| 5. `FindingsByCategory.test.ts` | Haiku | Straightforward; virtual-scroll internals already covered by `tests/unit/virtualScroll.test.ts`. |
| 6. `OidTree.test.ts` | Sonnet | Expand/collapse mutates the underlying `TrieNode` object directly rather than going through props — needs care to assert correctly. |
| 7. `MinimapDetail.test.ts` | Opus | Manual `addEventListener`-based interactions and canvas/geometry math; real risk of wrong coordinate assumptions under happy-dom, may need diagnosis. |

---

### Task 1: Runner swap — Vitest replaces bun:test *(model: Opus)*

Add `vitest`, `@vue/test-utils`, `happy-dom`, and `@vitest/coverage-v8` as devDependencies. Create
`oidviz/vitest.config.ts`: reuse the existing `@vitejs/plugin-vue()` plugin (same one `vite.config.ts`
uses, so SFC compilation matches the real build), set the test environment to `happy-dom`, and set
an explicit `test.include` covering `tests/unit/**/*.test.ts` and `tests/component/**/*.test.ts`
only (not `tests/e2e/**`).

Update `package.json`'s `"test"` script to run Vitest once (not in watch mode) instead of
`bun test`. Update the `Justfile`'s `test` target to match, and its `coverage` target to run
Vitest's coverage mode using the new coverage provider dependency.

Migrate all 7 files under `oidviz/tests/unit/*.test.ts`: the only change is the test-runner import
line (currently `import { describe, expect, test } from "bun:test"`) switching to import the same
four names from `"vitest"` instead. Nothing else in these files changes — Bun's test API and
Vitest's are compatible for everything these files use.

- [ ] **Step 1:** Add the four devDependencies to `package.json` and install them.
- [ ] **Step 2:** Write `vitest.config.ts` as described above.
- [ ] **Step 3:** Update the `test` script/target in both `package.json` and `Justfile`, and the
      `coverage` target in `Justfile`, to invoke Vitest instead of `bun test`.
- [ ] **Step 4:** Update the import line in each of the 7 `tests/unit/*.test.ts` files from
      `bun:test` to `vitest`.
- [ ] **Step 5:** Run the new test command and confirm all pre-existing unit tests still pass,
      with the same test count as before the migration (no test silently skipped).
- [ ] **Step 6:** Run `just hook` and confirm it's fully green (lint/types/fmt-check are unaffected
      by this task, but confirm anyway since `tests/unit/` files changed).
- [ ] **Step 7:** Commit.

---

### Task 2: Component-test scaffolding *(model: Sonnet)*

Create `oidviz/tests/component/helpers.ts` with small factory functions for the synthetic data
every component suite will need: an exchange factory (equivalent in shape to the `makeExchange`
helper already duplicated across several `tests/unit/*.test.ts` files — reuse that shape, don't
invent a new one), a facet-state factory, a `ParseResult` factory (covering the fields `Sidebar`
reads: header, summary, systemInfo, exchanges, truncated, parseMs), and a `FlatRow[]`/`TrieNode`
factory for `OidTree`. Each factory takes an optional partial-overrides argument, matching the
existing `makeExchange` pattern.

Create `oidviz/tests/component/CLAUDE.md`, adapted from `oidviz/tests/e2e/CLAUDE.md`: every
`test()` needs a comment stating the synthetic prop values that matter for that case and the
behavior contract being verified (not the DOM mechanism used to check it).

Extend the `local/require-test-comment` ESLint rule's scope in `eslint.config.mjs` to also apply to
`tests/component/**/*.test.ts` (currently scoped to `tests/e2e/**/*.spec.ts` only) — no change to
the rule's logic, it already matches any `Identifier` callee named `test`, which covers Vitest's
`test()` the same way it covers Playwright's. Add `tests/component/` to the `bunx eslint`
invocation inside the `Justfile`'s `lint` target, alongside the existing `src/` and `tests/e2e/`.

- [ ] **Step 1:** Write `tests/component/helpers.ts` with the four factories described above.
- [ ] **Step 2:** Write `tests/component/CLAUDE.md`.
- [ ] **Step 3:** Extend the ESLint rule's `files` glob and the `Justfile`'s `lint` target.
- [ ] **Step 4:** Prove the rule fires: temporarily add one `test()` call with no preceding comment
      to a throwaway file under `tests/component/`, run `just lint`, confirm it fails citing that
      rule. Delete the throwaway file.
- [ ] **Step 5:** Run `just lint` clean (nothing under `tests/component/` yet other than
      `helpers.ts`, which has no `test()` calls) and `just hook` green.
- [ ] **Step 6:** Commit.

---

### Task 3: `LandingScreen.test.ts` *(model: Haiku)*

`LandingScreen.vue` takes `appState: AppState` and emits `file-selected` (an `ArrayBuffer`) and
`file-error` (a message string).

| Test | Synthetic setup | Assertion |
| --- | --- | --- |
| landing phase shows the drop zone | `appState = { phase: "landing" }` | drop zone (`role="region"`, name "Drop zone for OID trace files") visible; loading overlay and error banner both absent |
| loading phase shows the overlay | `appState = { phase: "loading" }` | loading overlay (`role="status"`, aria-label "Loading trace file") visible; drop zone absent |
| error phase shows the drop zone and an error banner | `appState = { phase: "error", message: "boom" }` | error banner (`role="alert"`) visible with text `"boom"`; drop zone still visible (only `loading` hides it) |
| Enter on the drop zone opens the file picker | `appState = { phase: "landing" }`, spy on `HTMLInputElement.prototype.click` | pressing `Enter` on the drop zone calls the hidden file input's `click()` |
| Space on the drop zone opens the file picker | same as above | pressing `" "` on the drop zone calls `click()` |
| dropping a file emits file-selected | a synthetic `File` with known text content dropped onto the drop zone | `file-selected` emitted once with an `ArrayBuffer` whose decoded contents match the file |
| a file read failure emits file-error | a `File`-like object whose `arrayBuffer()` rejects with a known error message | `file-error` emitted with that message |

- [ ] **Step 1:** Write the 7 tests described above in `tests/component/LandingScreen.test.ts`,
      each with a comment per the Global Constraints convention.
- [ ] **Step 2:** Run `bunx vitest run tests/component/LandingScreen.test.ts`, confirm all pass.
- [ ] **Step 3:** Run `just hook`, confirm green.
- [ ] **Step 4:** Commit.

---

### Task 4: `Sidebar.test.ts` *(model: Sonnet)*

`Sidebar.vue` takes `appState`, `result: ParseResult | null`, `facetState`, `activeView`, and emits
`file-selected`, `file-error`, `view-change`, `facet-change`.

| Test | Synthetic setup | Assertion |
| --- | --- | --- |
| file-open control only in viewer phase | `appState.phase` = `"viewer"` vs. any other phase | "Open file" button + hidden file input present only when `viewer` |
| Open file button opens the file picker | phase `"viewer"`, spy on `click()` | clicking "Open file" calls the hidden input's `click()` |
| Device section renders system_info fields | `result.systemInfo` with `point: "start"`, sysDescr containing an embedded newline | Device section shows sysDescr truncated to its first line, sysObjectID, sysUpTime |
| Device section absent without system_info | `result.systemInfo` undefined/wrong `point` | Device section title not present at all |
| Walk info renders from summary | `result.summary` populated (label, snmp version, start OID, exchange count, oids_seen, violation_counts, end_reason) | each Walk info field matches; duration formatted as `"Ns"` under 60s and as `"Mm Ss"` at/over 60s (two sub-cases) |
| Walk info derives totals without a summary | `result.summary` null, exchanges carry known violations/response OIDs | violations = sum of exchanges' violation arrays; oidsSeen = count of distinct response OIDs; duration and end reason render `"—"` |
| violations styling follows the count | one case with 0 violations, one with >0 | 0 → `.info-val--ok`; >0 → `.info-val--err` |
| Walk config renders optional fields when present | settings with `resume_from` and `time_budget_s` set | both rows render with their values |
| Walk config omits optional fields when absent | settings without `resume_from`/`time_budget_s` | both rows absent; bulk size/timeout/retries still render |
| all result-derived sections absent when result is null | `result = null` | Device, Walk info, Walk config sections all absent |
| truncation warning follows result.truncated | `result.truncated` true vs. false/undefined | warning text visible only when true |
| clicking a view button emits view-change | each of the 3 view buttons in turn | `view-change` emitted with the matching `ActiveView` value; the currently active button has `aria-current="page"` |
| performance facet radios emit facet-change | each of Any/Fast/Slow/Timed out | `facet-change` emitted with `{ perf: <value> }` |
| correctness facet radios emit facet-change | Any and Violations only | `facet-change` emitted with `{ corr: <value> }` |
| retries-only checkbox emits facet-change | toggle on, then off | `facet-change` emitted with `{ retryOnly: true }` then `{ retryOnly: false }` |
| slow-threshold input emits facet-change in ms | entering `"2"` (seconds) | `facet-change` emitted with `{ slowMs: 2000 }` |
| invalid slow-threshold input emits nothing | entering `"0"` or a non-numeric value | no `facet-change` emitted (guarded by `seconds > 0 && !isNaN`) |

- [ ] **Step 1:** Write the tests described above in `tests/component/Sidebar.test.ts`, using the
      `ParseResult`/facet-state factories from `helpers.ts`, each with a comment per convention.
- [ ] **Step 2:** Run `bunx vitest run tests/component/Sidebar.test.ts`, confirm all pass.
- [ ] **Step 3:** Run `just hook`, confirm green.
- [ ] **Step 4:** Commit.

---

### Task 5: `FindingsByCategory.test.ts` *(model: Haiku)*

`FindingsByCategory.vue` takes `exchanges: DomainExchange[]` and `facetState`, emits
`focus-exchange` with a `seq`.

| Test | Synthetic setup | Assertion |
| --- | --- | --- |
| section headers reflect categorised counts | a mix of fast/slow/timeout exchanges | headers read `"Slow (n)"`, `"Timed out (n)"` with correct counts |
| Fast section only appears when there are fast exchanges | one case with 0 fast exchanges, one with some | Fast header absent vs. present with correct count |
| sections default expanded | any non-empty exchange set | every section header has `aria-expanded="true"` |
| clicking a header toggles it | click the Slow header | `aria-expanded` flips to `"false"`, that section's rows no longer render |
| violation badge on a row | an exchange with 2 entries in `violations` | that row shows `.badge-violation` reading `"2 viol"` |
| retry badge on a row | an exchange with `attemptCount: 3` | that row shows `.badge-retry` reading `"×3"` |
| clicking a row emits focus-exchange | any exchange row | `focus-exchange` emitted with that exchange's `seq` |
| row rtt class matches the exchange's status | one exchange each for slow / timeout / fast, using the same `slowMs` boundary cases as `tests/unit/utils.test.ts` | row's rtt element has class `dim-slow` / `dim-timeout` / `dim-fast` respectively |

- [ ] **Step 1:** Write the tests described above in `tests/component/FindingsByCategory.test.ts`,
      each with a comment per convention.
- [ ] **Step 2:** Run `bunx vitest run tests/component/FindingsByCategory.test.ts`, confirm all pass.
- [ ] **Step 3:** Run `just hook`, confirm green.
- [ ] **Step 4:** Commit.

---

### Task 6: `OidTree.test.ts` *(model: Sonnet)*

`OidTree.vue` takes `flatRows: FlatRow[]`, `facetState`, `matchingCount`, emits `reflatten` and
`collapse-all`. Node rows carry a live reference to a `TrieNode` object whose `expanded` field the
component mutates directly (not through props) — the tests need to hold onto that same object
reference to observe the mutation, matching the `// TrieNode.expanded is intentionally mutable`
comment in the component's source.

| Test | Synthetic setup | Assertion |
| --- | --- | --- |
| toolbar shows the matching count | `matchingCount = 7` | toolbar text reads `"7 exchanges"` |
| Collapse all emits collapse-all | any non-empty `flatRows` | clicking "Collapse all" emits `collapse-all` |
| node row renders its fields | a node row with a name, count, and `maxRtt > 0` | arc, name, count, and formatted maxRtt (with its rtt class) all render; a node with `maxRtt === 0` renders no maxRtt element |
| node row reflects expanded state | one node `expanded: true`, one `false` | toggle glyph and `aria-expanded` match each |
| clicking a node row emits reflatten and flips expansion | a node starting `expanded: false` | after click, `reflatten` is emitted and the same `TrieNode` object's `.expanded` is now `true` |
| keyboard toggle on a node row | Enter, then Space, on two separate node rows | both emit `reflatten` and flip `.expanded` the same as a click |
| node badges follow flags | one node per flag: `slow`, `violation`, `retry`, and one with none | `.badge-slow` / `.badge-violation` / `.badge-retry` render exactly when the corresponding flag is set |
| leaf row renders its fields | a leaf row for an exchange with a violation and `shared: true` | requestOid, rtt (with its rtt class), `.badge-violation`, and `.badge-shared` all render |

- [ ] **Step 1:** Write the tests described above in `tests/component/OidTree.test.ts`, each with a
      comment per convention.
- [ ] **Step 2:** Run `bunx vitest run tests/component/OidTree.test.ts`, confirm all pass.
- [ ] **Step 3:** Run `just hook`, confirm green.
- [ ] **Step 4:** Commit.

---

### Task 7: `MinimapDetail.test.ts` *(model: Opus)*

`MinimapDetail.vue` takes `exchanges`, `facetState`, emits `focus-exchange`. Its interactions are
wired with raw `addEventListener` calls on the two `<canvas>` refs rather than Vue template event
bindings, and its coordinate math (`colFromMouseX`, `detailRowFromMouseY`) reads `canvas.width` and
`canvas.getBoundingClientRect()`. Under happy-dom there's no real layout engine, so
`getBoundingClientRect()` returns a zero-origin rect and `clientWidth` reads `0` — meaning
`redraw()`'s `cssW > 0` guard will not resize the canvas away from its default width (300px).
Tests must account for this: pick `clientX`/`clientY` values as direct column/row coordinates
(since `rect.left`/`rect.top` are 0) and be aware the effective canvas width during tests is the
default 300px unless a test explicitly sets `canvas.width` before dispatching events.

Since Vue Test Utils' `trigger()` helper doesn't cover raw canvas event listeners well, dispatch
native `MouseEvent`/`KeyboardEvent` objects directly on the mounted canvas elements.

| Test | Synthetic setup | Assertion |
| --- | --- | --- |
| both canvases and the legend render | a small non-empty `exchanges` list | `.minimap-canvas` and `.detail-canvas` both present; 5 `.legend-item`s reading Timeout/Violation/Slow/Retry/Normal in order |
| mounting with data doesn't throw | non-empty `exchanges` | mount completes without a thrown error or unhandled rejection (covers `runAutoFocus`/`redraw` running against a null 2D context) |
| hovering the minimap shows a tooltip | a known small exchange set, hover at a column with exchanges in it | tooltip becomes visible with exchange count, computed status, and a `+Nms` offset |
| moving off the minimap hides the tooltip | continuing from the previous case, dispatch `mouseleave` | tooltip no longer visible |
| a click (no drag) on the minimap re-centers the window | mousedown then mouseup at the same column | a subsequent hover at a column now inside the new (re-centered) window produces a non-empty tooltip |
| dragging the minimap moves the cursor style | mousedown at one column, mousemove to another, inside vs. outside the current selection's edges | canvas `style.cursor` becomes `crosshair` / `grab` / `ew-resize` as appropriate for the drag mode |
| hovering the detail canvas shows a tooltip with OID/RTT/status | an exchange with a request OID under 40 chars, and a separate case over 40 chars | tooltip shows the OID (truncated with `…` only in the over-40 case), RTT, and status; `mouseleave` hides it |
| clicking a detail row emits focus-exchange | click at the row corresponding to a known exchange in the (auto-focused) window | `focus-exchange` emitted with that exchange's `seq` |
| clicking below the last detail row emits nothing | click far below all rendered rows, or with an empty `exchanges` prop | no `focus-exchange` emitted |
| arrow keys shift the selection window | `ArrowLeft` then `ArrowRight` on a focused minimap canvas | window shift is observable via a subsequent hover's tooltip changing to reflect the new window |

- [ ] **Step 1:** Write the tests described above in `tests/component/MinimapDetail.test.ts`,
      each with a comment per convention, applying the happy-dom coordinate notes above.
- [ ] **Step 2:** Run `bunx vitest run tests/component/MinimapDetail.test.ts`, confirm all pass.
      If a coordinate assumption is wrong, fix the test's synthetic setup — don't loosen the
      assertion — since the underlying component behavior is already correct and covered by e2e.
- [ ] **Step 3:** Run `just hook`, confirm green.
- [ ] **Step 4:** Commit.

---

### Task 8: Full verification *(model: Haiku)*

- [ ] **Step 1:** Run `just ci` (lint, types, fmt-check, test, e2e, a11y) end to end and confirm
      every stage passes.
- [ ] **Step 2:** Run the coverage target (`just coverage`) once and skim the report for any of the
      5 components with unexpectedly low coverage — not a hard gate, just a sanity check that the
      new suite is exercising real branches rather than only the happy path.
- [ ] **Step 3:** Confirm the total Vitest test count equals the pre-migration `bun test` count
      (from Task 1) plus the new component tests — nothing was accidentally skipped or duplicated.

---

## Self-Review Notes

Every component named in the design doc's scope section (LandingScreen, Sidebar,
FindingsByCategory, OidTree, MinimapDetail) has a task; `App.vue` is confirmed excluded per the
design's Global Constraints. The runner swap (Task 1) is proven against already-passing tests
before any new test is written, matching the design's stated migration order. The comment
convention and its ESLint enforcement (Task 2) land before the first component suite that must
follow it (Task 3). Sidebar and MinimapDetail — the two components with the most branching logic —
are assigned to stronger models and scheduled after the simpler components, so any test-harness
issues (e.g. the happy-dom coordinate behavior noted in Task 7) surface on lower-risk components
first. All prop/emit names, event names, and CSS class names referenced in the test tables above
were read directly from the current component source, not inferred.
