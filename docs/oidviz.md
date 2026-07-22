# OIDviz

Hosted browser-based viewer for oidtrace walk files (`.oidtrace.jsonl.gz`). Helps a monitoring
admin see whether a device behaved correctly during a walk, which OID subtrees were slow or
unreliable, and what timeout/poll interval to configure. Secondary user: an SNMP expert drilling
into a specific exchange.

**Behavior is defined by the test suite, not by this doc.** `oidviz/tests/e2e/*.spec.ts` and
`oidviz/tests/unit/*.test.ts` are the source of truth for what the app does — read those to find
out how a view renders, what a facet does, or what an error state looks like. This doc only covers
product intent and cross-cutting rules that no single test asserts, plus current gaps between
"finished" and what's actually shipped. It supersedes
`docs/superpowers/specs/2026-06-15-oidviz-spec.md` (deleted — superseded by the acceptance-test
suite per `docs/superpowers/plans/2026-07-06-oidviz-acceptance-tests.md`).

## Non-goals

Deliberately out of scope for now — if a request looks like one of these, it's a scope decision,
not an oversight:

- Server-side storage or trace sharing; nothing persists across a page reload
- Real-time / live monitoring (input is always a completed walk file)
- MIB compilation, MIB browser, or user-supplied MIB files
- Mobile layout (desktop-first, 1280px minimum width; responsive is not required)
- Multi-file comparison or side-by-side diff
- Export (CSV, PNG, or any other format)
- URL-encoded view state or bookmarking
- Annotation or note-taking on traces
- Dark mode (CSS custom properties are used throughout so it could be added later without
  touching component logic, but nothing wires it up today)

## Tech stack

Vue 3 · TypeScript · Bun · Vite. Trace record types are generated from
`traceformat/trace-format.schema.json` via `just gen-types` — never hand-write types for trace
records, the schema is authoritative (see `traceformat/trace-format.md`).

## Visual language

One colour + one glyph per anomaly dimension, shared across all views (DOM and canvas), defined as
`--dim-*` CSS custom properties in `app.css` and read via `getComputedStyle` at canvas draw time:

| Dimension | Glyph | Meaning |
|---|---|---|
| Timeout | ✕ | Last attempt had no response |
| Violation | ⚠ | Protocol error in `violations[]` |
| Slow | ⏱ | RTT > the slow threshold |
| Retry | ↻ | `attemptCount > 1` |
| OK / neutral | — | No anomaly |

Where one element can only show one colour (a minimap pixel, a canvas bar), the **display
precedence** is `Timeout > Violation > Slow > Retry`. This is a display-only tiebreak — it doesn't
rank problem types by product importance, and no individual test asserts it as a named rule even
though several tests exercise instances of it.

## OID name resolution

`src/lib/oidNames.gen.ts` is a generated build-time map of standard-MIB OID prefixes → name plus a
one-sentence description, resolved by longest-prefix match, used for tooltip and label display.
Scope is standard IETF MIBs only — vendor/enterprise OIDs resolve through their generic ancestor
(e.g. `enterprises`), not a vendor-specific name. The table is compiled from standard MIB modules
via `pysmi` (`scripts/gen_oid_names.py`); regenerate with `just gen-oid-names` whenever the module
set changes. This is the only OID-name list in the app — an earlier design had a second, separate
list for incident-clustering region names, but that was removed along with the Incident Stack view
(see Known gaps below).

## Accessibility

Target is WCAG 2.1 AA (4.5:1 text contrast, 3:1 large text), gated in CI via `just a11y`
(`@axe-core/playwright`) against DOM content only — axe cannot inspect canvas internals, so the
Minimap + Detail canvas is exempt from the automated gate and only validated manually.

## Viewport

Minimum supported width is 1280px; below that the layout is untested and may break. The main area
has no max-width cap — canvas views resize via `ResizeObserver` and are expected to work on
ultrawide/4K displays. No special handling for OS zoom or DPI scaling.

## Known gaps (intentional, not bugs)

These look like unfinished features but were deliberately left as-is when the behavior spec was
retired in favor of the test suite — don't "fix" them without a product decision first:

- Clicking a Findings row does nothing (`onFocusExchange` in `App.vue` is a placeholder). An
  earlier design had it jump to the exchange in Minimap + Detail; that wiring was never built.
- The Minimap + Detail toolbar (time-range label, "Zoom to problems", "Reset window") described in
  earlier design work doesn't exist in the component at all.
- The Incident Stack view (gap-window clustering of anomalous exchanges into scored incidents) was
  removed from the app entirely; only Findings, Minimap + Detail, and OID Tree remain.
- Findings sections render expanded by default, not collapsed.
- A timed-out exchange's RTT renders as `0.0ms` in the UI rather than the configured timeout
  budget.
