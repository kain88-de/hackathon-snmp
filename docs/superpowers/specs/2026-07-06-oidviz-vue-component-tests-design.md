# OIDviz — Vue component tests design

OIDviz has two test layers today: `tests/unit/*.test.ts` (Bun's test runner, pure `src/lib/*.ts`
functions only) and `tests/e2e/*.spec.ts` (Playwright, full app through a real browser and real
trace fixture files). There's no layer that mounts a Vue component in isolation and asserts its
own prop-in / render-and-emit-out contract. This design adds that layer.

## Tooling

Bun's test runner has no native `.vue` SFC support — Vue SFCs need `@vue/compiler-sfc`
preprocessing that only a Vite-based runner (or a custom, unmaintained Bun plugin) provides
([oven-sh/bun#5967](https://github.com/oven-sh/bun/issues/5967)). Rather than add a second
unit-level runner just for components, **Vitest replaces Bun's test runner entirely** — it becomes
the one runner for both the migrated `tests/unit/**` and the new `tests/component/**`. Playwright
and `tests/e2e/**` are unaffected — different job (real browser), no reason to change it.

- New devDependencies: `vitest`, `@vue/test-utils`, `happy-dom`, `@vitest/coverage-v8`.
- New `oidviz/vitest.config.ts`: reuses the same `@vitejs/plugin-vue()` already used for the real
  build (so SFC compilation matches production), sets `test.environment = "happy-dom"`, and sets an
  **explicit** `test.include` of `["tests/unit/**/*.test.ts", "tests/component/**/*.test.ts"]`.
  Vitest's default glob also matches `*.spec.ts`, which would otherwise try to execute Playwright's
  e2e specs and fail.
- `package.json`: `"test"` script becomes `"vitest run"`.
- `Justfile`: `test` → `vitest run`; `coverage` → `vitest run --coverage`.
- Migrate all 7 `tests/unit/*.test.ts` files: swap
  `import { describe, expect, test } from "bun:test"` → `from "vitest"`. Mechanical only — no test
  logic changes; the two APIs are compatible.
- CI (`.github/workflows/oidviz-ci.yml`) needs no changes — it only calls `just ci`.

**Canvas note:** `MinimapDetail.vue`'s draw functions (`src/lib/minimapDraw.ts`) all guard with
`if (!ctx) return;` before drawing. Since `HTMLCanvasElement.getContext("2d")` returns `null` under
happy-dom (no real canvas support), mounting `MinimapDetail` needs no canvas polyfill — the draw
calls just no-op. Canvas *pixel* output stays covered by `tests/unit/minimapDraw.test.ts`, which
tests those functions directly.

## Scope

All 5 leaf components get a dedicated `tests/component/<Name>.test.ts`: **LandingScreen, Sidebar,
FindingsByCategory, OidTree, MinimapDetail**.

**`App.vue` is explicitly out of scope.** It's a thin composition root whose only real logic is
wiring a Web Worker (`parser.worker.ts`) to child-component props. Testing that wiring in isolation
means mocking `Worker`, which would mostly test the mock rather than real behavior — the thing
worth proving (a real trace file → real worker → real parsed result → correct props) is exactly
what the e2e suite already exercises end-to-end. Same spirit as the "Known gaps" section in
`docs/oidviz.md`: a deliberate line, not an oversight.

Overlap between component tests and e2e tests is expected and fine, not wasteful: component tests
are the fast, synthetic-data layer (no browser, no file parsing, cheap to hit edge-case prop
combinations); e2e stays the small set of realistic, full-stack checks. Standard test-pyramid
reasoning — the same behavior checked at two layers is intentional redundancy.

## Per-component test contracts

Each suite mounts the component with `@vue/test-utils` and asserts **props → rendered DOM** and
**interaction → emitted event**, using synthetic data — no fixture files.

| Component | What the test suite covers |
|---|---|
| **Sidebar** | Emits `file-selected`/`file-error`/`view-change`/`facet-change` with correct payloads on interaction. Device/Walk info/Walk config section presence follows the `result` prop's shape (missing system info, missing summary, missing optional settings like `resume_from`/`time_budget_s`) — synthetic `ParseResult` objects cover edge cases that would otherwise need new e2e fixture files. Truncation banner follows `result.truncated`. |
| **LandingScreen** | Drag-over/drop and keyboard-open (`Enter`/`Space`) interactions emit `file-selected` with the file's buffer; a rejected file read emits `file-error`. Loading vs. error phase rendering driven by `appState.phase`. |
| **FindingsByCategory** | Section headers' counts reflect `categorise()` of the synthetic `exchanges` prop. Clicking a header toggles that section's rows. Clicking a row emits `focus-exchange` with the row's `seq`. |
| **OidTree** | Clicking a node row emits `reflatten`. "Collapse all" emits `collapse-all`. Slow/violation/retry badges render per node/leaf flags in synthetic `FlatRow[]`. |
| **MinimapDetail** | mousedown+mousemove on the minimap canvas moves the selection window (verified via observable side effects — cursor style, tooltip, emitted focus — not pixel output). Click on the detail canvas emits `focus-exchange` with the hit-tested exchange's `seq`. Hover shows/hides the tooltip with the right status text. |

**Shared helpers:** `tests/component/helpers.ts` holds small factories (`makeExchange`,
`makeFacetState`, `makeParseResult`, `makeFlatRows`) so all 5 suites build synthetic props
consistently. `tests/unit/*.test.ts` already duplicates a similar `makeExchange` across 5 files —
left as-is (out of scope for this task), but the new layer won't add a 6th duplicate.

## Test comment convention & enforcement

`tests/component/**` follows the same convention as `tests/e2e/**`
(`tests/e2e/CLAUDE.md`), adapted for synthetic data: every `test()` gets a comment stating (a) the
synthetic prop values that matter for this case, and (b) the behavior contract being verified —
"fixture fact" becomes "synthetic prop fact" since there's no fixture file.

- New `tests/component/CLAUDE.md` documenting this, mirroring `tests/e2e/CLAUDE.md`'s wording.
- Extend the `local/require-test-comment` ESLint rule's `files` glob in `eslint.config.mjs` to also
  match `tests/component/**/*.test.ts`. No rule logic changes needed — it only checks that a `test()`
  call (an `Identifier` callee named `test`) has a preceding comment, and Vitest's `test()` matches
  the same shape as Bun's and Playwright's.
- Add `tests/component/` to the `bunx eslint` invocation in `just lint`.

## Files

- Create: `oidviz/vitest.config.ts`, `oidviz/tests/component/{helpers,LandingScreen,Sidebar,FindingsByCategory,OidTree,MinimapDetail}.test.ts`, `oidviz/tests/component/CLAUDE.md`
- Modify: `oidviz/package.json`, `oidviz/Justfile`, `oidviz/eslint.config.mjs`, all 7 `oidviz/tests/unit/*.test.ts` (import swap only)
