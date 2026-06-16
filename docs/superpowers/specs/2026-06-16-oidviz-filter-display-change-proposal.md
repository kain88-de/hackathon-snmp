# OIDviz — Filter & Display Redesign Change Proposal

Date: 2026-06-16  
Status: Approved by product owner, pending prototype + spec update

---

## Why this change

A review of the existing implementation found 12 inconsistencies between the filter model, the display model, and the three views. The root cause is that **filters compose by OR (union)** while **every display collapses to a single priority bucket** — these two models are incompatible and produce confusing UX throughout.

---

## Confirmed inconsistencies (all 12)

### Known before the review

1. **`incidentType()` single priority chain loses information.** An incident labelled `"timeout"` may also have violations and slow exchanges; that is invisible to the user.

2. **`severityClass()` conflates violation and slow.** Both map to `severity-warn` / `⚠`. A protocol violation (`request-id-mismatch`) looks identical to "just slow."

3. **Filter ↔ label inconsistency.** Filters use OR (show if *any* checked dimension matches); labels use priority (show *only* the worst property). Result: unchecking "timeouts" still shows an incident labelled `✕ timeout` because it also happened to be slow.

4. **OID trie `severity` is a single max value.** `TrieNode.severity` collapses to `Violation > Slow > Ok`. A subtree with both slow and violating exchanges shows only "violation", losing the "also slow" signal.

5. **Exchange categories overlap; display treats them as mutually exclusive.** An exchange can simultaneously be slow, have violations, have retries, and be a timeout. The filter checkboxes are independent OR dimensions but every display renders only one.

### Found during the review

6. **Timeouts are structurally invisible in the OID tree.** The trie is keyed on `responseOids` but timeout exchanges have no response (`responseOids` is empty). The tree cannot show the most severe anomaly class at all. *(Accepted as correct per Q4 — but the empty state when filtering for timeouts must say so explicitly.)*

7. **Incident modal ignores filter state.** `IncidentModal` iterates `incident.members` raw. With only "timeouts" checked, the modal still lists purely-slow members that are hidden in every other view.

8. **Minimap detail panel ignores filters entirely.** `drawDetail` filters bars by time window only, not by `matchesFilters`. The minimap overview above it filters by `matchesFilters` + `isAnomalous`. The two panels of the same view disagree about what exists.

9. **Colour language contradicts across views for the same property.**
   - Violation: amber in minimap, red in OID tree, "warn" in incident stack.
   - Slow: blue in minimap, amber in OID tree, "warn" in incident stack.
   A user who learns "amber = violation" in the minimap reads "amber = slow" in the OID tree.

10. **Retry has no severity representation in two of three views.** OID tree `Severity` is only Ok/Slow/Violation — a retry-only subtree renders green "ok". The incident chip maps retry to `severity-info`. Only the minimap gives retry a colour.

11. **`peakRtt` inflated by timeout budget blurs slow vs timeout.** A timeout's RTT is `sent + timeout_s − first.sent` (several seconds). A timeout incident almost always also passes the "slow" filter, blurring the distinction the UI tries to draw.

12. **OID tree leaf rows show `requestOid` but are filed under a `responseOid` path.** In a GETNEXT/BULK walk you request OID `X` and get back `X.1`, `X.2`, etc. The leaf's displayed OID contradicts its own position in the tree.

---

## Decisions made

| # | Question | Decision |
|---|---|---|
| Q1 | Filter semantics: OR or AND? | **AND** — each checkbox narrows the set; more intuitive as "additive" |
| Q2 | Single priority label vs multiple badges? | **Neither** — add a new categorised Findings view |
| Q3 | Canonical severity ordering? | **Obsolete** for cross-category ranking; intra-section sort only (see §4) |
| Q4 | OID tree include timeouts? | **No** — tree is responses-only; waterfall handles timeouts |
| Q5 | Incident modal respect filter? | **Moot** — modal kept as-is; Findings view respects filter by construction |
| — | Keep Incident Stack? | **Yes** — it is a valuable temporal clustering summary; do not delete |
| — | Where does the Findings view go? | **4th view, default landing** — Findings · Incidents · Minimap · OID Tree |

---

## 1. Filter model — AND semantics

### New composition rule

An exchange **passes the filter** iff it satisfies **every checked** dimension:

```
matchesFilters(ex, state) =
  (!state.slow       || ex.rtt > state.slowMs)        &&
  (!state.violations || ex.violations.length > 0)     &&
  (!state.retries    || ex.attemptCount > 1)          &&
  (!state.timeouts   || ex.isTimeout)
```

Each unchecked box contributes a vacuously-true clause and never narrows. This is the exact inverse of today's early-return-true OR logic.

### "All unchecked" = show everything

With no boxes checked every clause is vacuously true → returns `true` for all exchanges. Preserves today's "no filter = unfiltered firehose" identity and is the natural identity element of AND.

### Edge cases

| Case | Behaviour |
|---|---|
| All four checked | Only exchanges that are slow AND violating AND retried AND timed out. Likely empty — show explicit empty state: *"No exchanges match all four filters. Uncheck a filter to widen."* |
| Timeout + Slow | A timed-out exchange has an RTT (timeout budget). Both clauses evaluated independently and ANDed; no special-casing. |
| Timeout filter active → OID tree | The filtered set is timeout exchanges → `responseOids` empty → **tree is empty**. Empty state must say: *"Timeouts have no response OIDs — see the Minimap view."* |
| `slowMs = 0` | Slow clause becomes `rtt > 0`, matches almost everything. Allowed. |

### Code changes

- **Rewrite** `matchesFilters` in `filters.ts` to AND (invert early-returns).
- **Keep** `clusterMatchesFilters` — still used by Incident Stack.
- **Rewrite** `filters.test.ts`: replace OR-composition tests with AND-composition tests. The "all unchecked → true" case stays. Add: "slow+retries checked, exchange only slow → false"; "both satisfied → true".

---

## 2. New view: Findings by Category (default)

### Purpose

The Findings view answers: *"What types of problems exist in this trace, and where?"* It is the **default landing view** — the first thing a user sees after loading a file.

### View order in sidebar

1. **Findings** ← new, default (`activeView` initialised to `'findings'`)
2. **Incident Stack** ← existing, unchanged
3. **Minimap + Detail** ← existing
4. **OID Tree** ← existing

### Structure: four collapsible sections

```
SLOW        (n)   ← --dim-slow colour
VIOLATION   (n)   ← --dim-violation colour
RETRY       (n)   ← --dim-retry colour
TIMEOUT     (n)   ← --dim-timeout colour
```

- All four section headers always visible simultaneously (accordion, not tabs) so absence is informative ("0 timeouts").
- Sections with zero members shown collapsed and greyed.
- An exchange that is both slow and violating **appears in both the SLOW and VIOLATION sections** — membership is per-dimension, not exclusive.

### Unit of display: the exchange

Each row is an exchange (the atom that carries all four dimension fields). One exchange with N response OIDs is still one row — per-OID detail is the OID Tree's job.

### Row contents per section

| Section | Left | Right (category metric) | Secondary |
|---|---|---|---|
| Slow | `requestOid` (named if known) · `#seq` | **`{rtt}ms`** in `--dim-slow` | `t=…s` |
| Violation | `requestOid` · `#seq` | **violation type(s)** | `{rtt}ms`, `t=…s` |
| Retry | `requestOid` · `#seq` | **`{attemptCount}×`** | `{rtt}ms`, `t=…s` |
| Timeout | `requestOid` · `#seq` | **`timeout`** badge | `t=…s` |

### Sorting within each section (intra-section only; no cross-section ranking)

| Section | Sort key (descending) |
|---|---|
| Slow | `rtt` |
| Violation | violation count, then `rtt` |
| Retry | `attemptCount` |
| Timeout | `seq` (chronological) |

### Interaction with AND filter

Sections categorise the **already-filtered set**. When no box is checked (common "explore" case) the filtered set is everything, and each section shows all exchanges exhibiting that dimension — the pure "what did we find" view. When boxes are checked, the filtered set narrows first, then categorisation applies to the intersection.

**Critical:** sections do not re-widen the filtered set. When "Slow + Violation" are checked, both the SLOW and VIOLATION sections contain the same exchanges (the intersection). This must be explicit in the implementation.

### Click behaviour

Clicking a row focuses that exchange in the Minimap view (jump to time `sentAtMs`). This replaces the old per-incident modal for findings-originated drill-down.

### Code changes

- **New** `src/components/FindingsByCategory.vue` — four collapsible sections, virtual-scroll rows (reuse the `FlatRow`-style interleaved header+row approach from OID Tree).
- **New** pure helper `categorise(exchanges: readonly DomainExchange[], state: FilterState): { slow: DomainExchange[], violation: DomainExchange[], retry: DomainExchange[], timeout: DomainExchange[] }` — unit-tested.
- **Update** `App.vue`: add `'findings'` to `activeView` type; initialise to `'findings'`.
- **Update** `Sidebar.vue`: add Findings nav button (first, active by default).
- **Update** `model.ts`: add `'findings'` to the `activeView` union if it lives there.

---

## 3. Incident Stack — kept, no structural changes

The Incident Stack (gap-window clustering, score sort, incident modal) is **preserved unchanged**. It answers a different question from Findings: *"What were the major events, when did they happen, and how bad were they?"* Temporal grouping by OID region makes incidents more informative than a flat list when a burst of related failures occurred.

**Minor fix only:** the incident modal currently shows members regardless of active filter (inconsistency #7). Fix: filter `incident.members` through `matchesFilters` before rendering rows in the modal table.

---

## 4. Shared visual language — one colour per dimension

Define the palette **once** as CSS custom properties. All three views (DOM and canvas) read from these tokens.

| Dimension | Token | Light | Dark | Glyph |
|---|---|---|---|---|
| Slow | `--dim-slow` | `#3b82f6` | `#60a5fa` | ⏱ |
| Violation | `--dim-violation` | `#f59e0b` | `#fbbf24` | ⚠ |
| Retry | `--dim-retry` | `#93c5fd` | `#bfdbfe` | ↻ |
| Timeout | `--dim-timeout` | `#ef4444` | `#f87171` | ✕ |
| Neutral / OK | `--dim-none` | `#94a3b8` | `#64748b` | — |

**Rules:**
1. A dimension is always the same colour and glyph in all three views. No view invents its own mapping.
2. Canvas reads the tokens via `getComputedStyle` at draw time (fixes dark-mode canvas — currently hardcodes light-mode hex).
3. Where one element can only show one colour (a single minimap pixel, a single canvas bar), use the **display precedence**: `Timeout > Violation > Slow > Retry`. This precedence is display-only — it does not imply a cross-category product ranking.
4. Retire the `severity-err / severity-warn / severity-info` / `--info-*` triad — everything maps to one of the four dimension tokens or neutral.

### Incident Stack chip — updated mapping

| Chip | Old condition | New condition |
|---|---|---|
| `--dim-timeout` (✕) | `timeoutCount > 0` | unchanged |
| `--dim-violation` (⚠) | `violationTypes.size > 0 \|\| peakRtt > slowMs` | `violationTypes.size > 0` only |
| `--dim-slow` (⏱) | — | `peakRtt > slowMs` (new, was merged into warn) |
| `--dim-retry` (↻) | `severity-info` | `retryCount > 0` and none of the above |

---

## 5. OID Tree — two fixes

### Fix 1: Leaf OID bug (inconsistency #12)

The trie files each leaf under a `responseOid` path, but `OidTree.vue` renders `exchange.requestOid` for the leaf. These differ in bulk walks. Fix:

- Add `oid: OidString` to `TrieLeaf` — set at insert time to the specific response OID for this placement.
- `FlatRow` leaf variant carries that `oid`.
- Template renders `truncateOid(item.row.oid)` instead of `item.row.exchange.requestOid`.

### Fix 2: Dimension flags replace single `Severity` max

Replace `TrieNode.severity: Severity` with per-node dimension flags:

```ts
flags: { slow: boolean; violation: boolean; retry: boolean }
// timeout excluded: no response OIDs in timeout exchanges (Q4)
```

Rolled up by OR-ing children + own leaves (not max). Render as **small dimension dots** on the node row, one per present flag in the dimension colour. `autoExpand` changes from `severity > Severity.Ok` to `flags.slow || flags.violation || flags.retry`.

The existing numeric stats (`count`, `maxRtt`, `violationCount`) stay and keep their thresholded `rtt-ok/warn/err` colour for the `maxRtt` number itself.

---

## 6. Minimap + Detail — two fixes

### Fix 1: Remove `isAnomalous` double-gating

`buildBuckets` currently does `filteredExchanges.filter(isAnomalous)`. Under AND filtering, `filteredExchanges` is already the precise set of interest; the extra `isAnomalous` pass is redundant. Remove it — plot `filteredExchanges` directly. When nothing is checked (all-pass), every exchange is plotted; colour carries the dimension signal.

### Fix 2: Canvas uses `--dim-*` tokens

Replace all hardcoded hex in `bucketColor`, `exchangeBarColor`, selection overlay, violation marker, and tick labels with values resolved from `getComputedStyle` at draw time. One colour per dimension; display precedence `Timeout > Violation > Slow > Retry` for single-pixel/single-bar rendering.

---

## 7. What stays, what changes, what is new

### Stays unchanged
- `DomainExchange`, parser worker, `ParseResult`, `FilterState` shape
- `clusterMatchesFilters` (still used by Incident Stack)
- `incidentStack.ts`, `Incident`, `IncidentModal.vue`, gap-window clustering, scoring
- Minimap/Detail interaction model (window, pan, zoom, ResizeObserver)
- Sidebar filter UI shape (four checkboxes + slow threshold) — only *meaning* changes to AND
- OID Tree virtual-scroll machinery

### Changes
| Item | Change |
|---|---|
| `matchesFilters` | OR → AND (invert early-returns) |
| `TrieNode.severity` | Single `Severity` enum → dimension flags `{slow, violation, retry}` |
| `TrieLeaf` | Add `oid: OidString` per placement |
| `FlatRow` leaf | Render `item.row.oid` not `exchange.requestOid` |
| `autoExpand` | `severity > Ok` → `any flag set` |
| `app.css` | Add `--dim-*` tokens; retire `--info-*`; update `severity-*` classes |
| `MinimapDetail.vue` | Remove `isAnomalous` gating; read `--dim-*` from `getComputedStyle` |
| `IncidentStack.vue` | Update chip classes to use `--dim-*`; fix violation vs slow chip distinction |
| `IncidentModal.vue` | Filter `incident.members` through `matchesFilters` before rendering |
| `App.vue` | Add `'findings'` to `activeView`; default to `'findings'` |
| `Sidebar.vue` | Add Findings nav button (first, default active) |
| `filters.test.ts` | Rewrite for AND semantics |
| `oidTrie.test.ts` | Update for flags rollup and leaf-OID-equals-placement-path |

### New
| Item | Purpose |
|---|---|
| `src/components/FindingsByCategory.vue` | Four-section categorised view, default landing |
| `categorise()` helper in `FindingsByCategory.vue` or `src/lib/findings.ts` | Pure: `(exchanges, state) → {slow, violation, retry, timeout}` arrays |
| `--dim-*` CSS tokens in `app.css` | Shared visual language across DOM + canvas |

---

## Suggested implementation order

Each step is independently verifiable:

1. **AND filter** — rewrite `matchesFilters`, rewrite `filters.test.ts`. Verify tests pass. All views inherit the narrowing automatically.
2. **`--dim-*` palette** — add tokens to `app.css`, update Incident Stack chip classes, update minimap canvas to `getComputedStyle`. Verify dark mode works on canvas.
3. **OID tree fixes** — add `flags` rollup, fix leaf OID. Update `oidTrie.test.ts`. Eyeball against a bulk-walk trace.
4. **FindingsByCategory view** — new component + `categorise` helper + sidebar nav button + App.vue default. Verify all four sections populate correctly; verify AND filter narrows each section.
5. **Minimap double-gating** — remove `isAnomalous` filter in `buildBuckets`. Verify filtered counts match across Findings and Minimap.
6. **Incident modal filter** — filter members through `matchesFilters` in `IncidentModal`. Verify modal only shows matching members.

---

## Files to update in the prototype

The prototype at `oidviz/prototypes/index.html` is the authoritative visual reference and must be updated before the spec is revised.

Changes needed:
- Add `--dim-*` colour tokens to `:root` / `[data-theme=dark]`
- Add Findings view HTML (four accordion sections, exchange rows)
- Make Findings the default active view
- Update sidebar nav order
- Update filter JS to AND semantics
- Update incident chip CSS/JS to use `--dim-*` and fix violation ≠ slow
- Fix OID tree leaf to show response OID not request OID
- Fix minimap canvas to read colours from CSS variables
