# OIDviz — specification

Hosted browser-based viewer for oidtrace walk files.
Supersedes `docs/superpowers/specs/2026-06-11-oidviz-design.md` (deleted).

---

## Goals

Help a monitoring admin answer:
- Is this device behaving correctly? (violations, end reason)
- Which OID subtrees are slow or unreliable?
- What timeout and poll interval should I configure?

Secondary user: SNMP expert drilling into a specific exchange to debug device agent behaviour.

## Non-goals

- Server-side storage or trace sharing
- Real-time / live monitoring (input is a completed walk file)
- MIB compilation or full MIB browser
- Mobile layout (desktop-first; responsive is acceptable but not required)
- Multi-file comparison or side-by-side diff
- Export (CSV, PNG, or any other format)
- URL-encoded view state or bookmarking
- Annotation or note-taking on traces
- Persistent storage of any kind (settings, history, preferences)

---

## Tech stack

Vue 3 · TypeScript · Bun · Vite · `@vitejs/plugin-vue` · see `oidviz/docs/web-guardrails.md` for toolchain guardrails.

Types are generated from `../docs/trace-format.schema.json` (path relative to `oidviz/`):
```sh
bunx json-schema-to-typescript ../docs/trace-format.schema.json -o src/types.gen.ts
```

Do not hand-write types for trace records.

---

## File loading and state model

### Load flow

1. App opens → landing screen with drag-and-drop zone and file-picker button
2. User drops or selects a `.oidtrace.jsonl.gz` file
3. File is parsed off the main thread (gzip decompress + JSONL parse) — the UI stays responsive during loading, even for large trace files.
4. App transitions to the viewer layout once parsing completes.

### Reload behaviour

Nothing is persisted. On page reload the app returns to the landing screen; the user must provide the file again. All settings (slow threshold, active view) reset to defaults.

### Error states

| Condition | Behaviour |
|---|---|
| File not gzip | Show inline error, keep landing screen open |
| Truncated file | Parse up to the last complete line; warn in sidebar |
| Missing summary record | Derive totals from exchange records |
| Unknown record type | Skip silently |

---

## Layout

```
┌──────────┬────────────────────────────────┐
│ Sidebar  │         Main view              │
│  220px   │  Incident Stack                │
│  fixed   │  Minimap + Detail              │
│          │  OID Tree                      │
└──────────┴────────────────────────────────┘
```

Two columns. Detail content appears as a modal overlay (Incident Stack) or hover tooltip (Minimap + Detail). OID Tree has no detail panel.

### Viewport
- Minimum supported width: **1280px**. Below this the layout is not tested and may break.
- The main area stretches to fill all available width — no max-width cap. Canvas-based views resize via `ResizeObserver` and work correctly on 4K and ultrawide displays.
- System zoom and DPI scaling are handled by the OS/browser; the app requires no special treatment.

---

## Sidebar

Always visible. Scrollable if content overflows.

Sections (top to bottom):

### Brand
`OIDviz` logotype.

### Load
"Open trace file…" button + shortcut buttons for bundled fixture files. Hidden file input accepts `.oidtrace.jsonl.gz`. Uncompressed `.oidtrace.jsonl` is not accepted.

### Device
Populated from the `system_info` record (`type: "system_info"`, `point: "start"`) when present. Hidden if no such record exists in the trace. Values are looked up by OID key in `system_info.values`.

| Field | Key in `system_info.values` |
|---|---|
| sysDescr (first line only) | `1.3.6.1.2.1.1.1.0` |
| sysObjectID | `1.3.6.1.2.1.1.2.0` |
| sysUpTime | `1.3.6.1.2.1.1.3.0` |

Fields not found are shown as `—`.

### Walk info
Shown after a file loads:
- Label (from `header.label`)
- SNMP version (from `header.snmp.version`)
- Start OID (from `header.settings.start_oid`)
- Exchanges count
- OIDs seen (from `summary.oids_seen`)
- Duration
- Violations total (0 = green, >0 = red)
- End reason (raw string from `summary.end_reason`)
- Parse time (ms elapsed to parse the file)

### Views
Navigation: Incident Stack · Minimap + Detail · OID Tree. Active view highlighted.

### Filters
- **Slow** (checkbox, on by default) — exchanges with RTT > threshold; inline threshold input in seconds (default `1`)
- **Violations** (checkbox, on by default) — exchanges with at least one entry in `violations`
- **Retries** (checkbox, on by default) — exchanges with >1 attempt
- **Timeouts** (checkbox, off by default) — exchanges where any attempt has `received_at === null`

Changing a filter or threshold immediately re-renders the active view.

#### Filter compose rule per view

An exchange **matches** the active filters if it satisfies at least one checked criterion. When no filter is checked, all exchanges are shown (not zero).

| View | Unit filtered | Match condition |
|---|---|---|
| Incident Stack | Cluster | Show cluster if it has at least one matching exchange (slow: `peakRtt > slowMs`; violations: `violationTypes.size > 0`; retries: `retryCount > 0`; timeouts: `timeoutCount > 0`) |
| Minimap + Detail | Exchange | Show exchange if it matches at least one checked criterion |
| OID Tree | Exchange | Same as Minimap + Detail — exchange enters the trie if it matches at least one checked criterion |

The four filters are fully independent — the Timeouts checkbox alone is sufficient to surface timeout exchanges/clusters.

### Walk config
Read-only fields from `header.settings`: `bulk_size`, `timeout_s`, `retries`, `start_oid`, `time_budget_s` (optional), `resume_from` (optional).

---

## Visual reference

`oidviz/prototypes/index.html` is the authoritative visual reference for all three views. Open it in a browser to see the exact layout, colours, and interactions. The descriptions below specify structure and behaviour; the prototype resolves any ambiguity about appearance.

---

## View: Incident Stack

Clusters anomalous exchanges into named, scored incidents using a gap-window algorithm.

### Violations
`exchange.violations` is an array of strings (open enum). Known values: `request-id-mismatch`, `oid-not-increasing`, `missing-end-of-mib`, `duplicate-response`, `malformed-ber`, `response-from-unexpected-source`. An exchange may have multiple violations simultaneously.

### Timeouts and RTT
An attempt is a **timeout** when `received_at === null`. RTT for a timed-out attempt is defined as `timeout_s` (the configured timeout, i.e. the minimum time the walker waited). Exchange RTT is `last_attempt.received_at - first_attempt.sent_at`; if the last attempt timed out, use `last_attempt.sent_at + timeout_s - first_attempt.sent_at`.

### Anomaly detection
An exchange is anomalous if any of: RTT > slowMs, `violations` is non-empty, has >1 attempt (retry), any attempt timed out (`received_at === null`).

### Clustering
Anomalous exchanges are merged into clusters using a gap-window algorithm:
- OID for region assignment: `request.oids[0]` (always present; represents what the walker requested at that point).
- Two consecutive anomalous exchanges are merged into the same cluster if the number of non-anomalous exchanges *between* them is ≤ `GAP_WINDOW` (default 8), **or** both map to the same OID region (regardless of gap size).
- Non-anomalous exchanges are never added to a cluster as members; they are only used to compute the gap.
- The gap count is `(indexB − indexA − 1)` where A and B are the indices of the two anomalous exchanges.

### OID regions
Well-known prefixes mapped to region names for **clustering only** (coarse topology grouping):

| Prefix | Name |
|---|---|
| `1.3.6.1.2.1.1.` | `system` |
| `1.3.6.1.2.1.2.2.1` | `ifTable` |
| `1.3.6.1.2.1.2.` | `interfaces` |
| `1.3.6.1.2.1.4.` | `ip` |
| `1.3.6.1.2.1.6.` | `tcp` |
| `1.3.6.1.2.1.11.` | `snmp` |
| `1.3.6.1.2.1.25.` | `hrSystem` |
| `1.3.6.1.4.1.` | `enterprises` |

Matching is longest-prefix-first. Unknown OIDs use the first 8 arcs as the region label.

This list is intentionally separate from the OID Tree's well-known name map (which is for display labels) and from the build-time resolution map (which covers ~2k prefixes for tooltips). Each list is sized to its purpose.

### Incident scoring
Score prioritises: timeouts > distinct violation types > retries > peak RTT > member count. `distinctViolationTypes` is the count of unique violation strings across all member exchanges.

Weights (implemented as named constants):
```
score = 100 × timeoutCount + 50 × violationTypes.size + 10 × retryCount
      + log10(max(peakRtt, 1)) × 5 + members.length × 0.1
```

### Row layout
Each incident row:
- **Severity chip** (48×48px): `err` (any timeout), `warn` (violation or slow), `info` (retry only)
- **Title**: `{region} — {type}` where region is a well-known name or the first 8 OID arcs for unknown prefixes, and type summarises the dominant anomaly (e.g. `timeout ×3`, `request-id-mismatch`, `slow region`, `2 retries`)
- **Subtitle**: seq range (or single seq if start = end) · peak RTT · exchange count · retry count (omitted if 0)
- **Walk position bar**: shows where in the walk this incident falls (proportional)

### Filters
Incidents are hidden/shown based on active sidebar filters. Count label updates accordingly.

### Virtualised rendering
Only rows within the visible viewport are rendered.

### Incident detail modal
Opens on row click. Fixed overlay with backdrop; clicking the backdrop or pressing Escape closes it.
- Header: incident number · region · seq range · Prev / Next navigation · close button
- Summary stats grid: Peak RTT, Timeouts, Retries, Exchanges, Violations
- Exchange table: Seq · OID · RTT · Flag (timeout / violation type / retry count)

---

## View: Minimap + Detail

Two-panel canvas layout for timeline-based exploration of the full walk.

### Minimap panel
Covers the full walk duration. Each pixel column represents a time bucket; ok (non-anomalous) exchanges are not shown. Colour priority for anomalous buckets: timeout > violation > retry > slow (see prototype for exact colours). Bar height proportional to event count in the bucket.

A selection rectangle highlights the current detail window.

Tooltip on hover: time offset, event count, max RTT, violation flag.

### Detail panel (flex remainder)
Shows individual exchange bars for exchanges whose time window overlaps the selection:
- One horizontal bar per exchange on a vertical list, ordered by sent time
- Bar length proportional to RTT on the shared time axis
- Retry attempts rendered as stacked bars — colours follow the same priority as the minimap (see prototype for exact colours)
- Violation marker `!` after the bar
- Seq number label on the left
- Time-axis tick marks and labels at the top

Hover tooltip: seq, % into trace, violation/status, RTT, sent-at time, OID.

### Window interaction
- **Drag** on empty minimap area: create new window
- **Drag** inside window: pan
- **Drag** window edges: resize
- **Click** (no drag): centre window at clicked point (window width = 5% of trace)
- **Arrow Left / Right**: shift window by 20% of current span

Toolbar: window time range label · "Zoom to problems" (focuses densest problem bucket) · "Reset window" (restores default 5% width).

### Filters
Active sidebar filters determine which exchanges are included in the minimap buckets and detail list.

---

## View: OID Tree

Trie built from exchange response varbind OIDs (up to 7 prefix levels). Stats rolled up per node.

### Data model
Each node: arc label, full OID, optional well-known name, children map, leaf exchanges, stats (count, maxRtt, violationCount), severity (`Severity` enum: `Ok = 0`, `Slow = 1`, `Violation = 2`).

Leaves are individual filtered exchanges attached to the deepest matching prefix node.

Well-known prefix names for **display labels** in the tree (distinct from the clustering region list):
`system`, `interfaces`, `ip`, `tcp`, `snmp`, `host`, `cisco`, `snmpVacm`.

### Rollup
Stats aggregate bottom-up: children's stats fold into the parent. Severity propagates upward (max).

### Row layout
Virtualised. Two row types:

**Node row**: indent · caret (▸/▾) · OID arc · well-known name (muted) | Count | Max RTT (coloured) | Violations (badge)

**Leaf row**: indent · seq number · OID prefix · (shared) tag if OID appeared in multiple exchanges | attempts (×N or —) | RTT (coloured) | violation badge

Clicking a node toggles expand/collapse and re-flattens the visible row list.
Leaf rows are display-only — no detail panel.

### Toolbar
"Collapse all" · matching/shown count label.

### Filters
Active sidebar filters determine which exchanges are included in the trie. Auto-expand: nodes containing anomalous leaves are expanded on initial load.

---

## OID name resolution

Bundle a static map of ~2k standard RFC OID prefixes → names at build time. Used for **tooltip display** and node labels that fall outside the OID Tree's short well-known-name list.

Sources: SNMPv2-MIB, IF-MIB, IP-MIB, TCP-MIB, UDP-MIB, HOST-RESOURCES-MIB, SNMP-FRAMEWORK-MIB, common Cisco/Juniper/Net-SNMP enterprise prefixes.

Resolution: longest-prefix match. Unknown OIDs are shown as the numeric OID.

User-supplied MIB files are out of scope for the initial version.

Note: the project uses three OID prefix lists with distinct purposes — see [OID regions](#oid-regions) for the clustering list, [OID Tree well-known names](#data-model) for the tree display list, and this section for the comprehensive tooltip resolution map. They are intentionally separate.

---

## Accessibility (WCAG 2.1 AA)

### Colour
- All text/background combinations: 4.5:1 contrast ratio (3:1 for large text)
- Latency/severity colouring is never the only indicator — paired with a text label or icon

### Keyboard

| Element | Keys |
|---|---|
| File drop zone | Tab to focus, Enter/Space to open picker |
| Minimap canvas | Tab to focus, Arrow to shift window |
| OID Tree rows | Tab, Enter to expand/collapse |
| Incident Stack rows | Tab, Enter to open modal |
| Incident modal | Escape to close, focus returns to trigger row |
| Filter checkboxes | Tab, Space/Enter to toggle |
| Number inputs | Standard keyboard editing |

### Screen reader
- `<aside>` for sidebar, `<main>` for view area
- Canvas wrappers: `role="application"`, `aria-label`
- `aria-live="polite"` region in the sidebar for status messages (file loaded, filter changed)
- Modal open: focus moves to modal heading; modal close: focus returns to trigger row

### CI gate
`axe-core` cannot inspect canvas internals. The gate applies to DOM-based content only: sidebar, incident modal, and OID Tree. Zero WCAG 2.1 AA violations in DOM content is a hard gate before merge. Minimap + Detail (canvas) is validated manually.

---

## Dark mode

Default to system preference (`prefers-color-scheme`). Toggle in the sidebar header.

DOM-based content (sidebar, incident modal, OID Tree) uses CSS custom properties throughout — no hard-coded colours. Dark mode is in scope for v1.

Canvas-based views (Minimap + Detail) use hard-coded colours (`fillStyle` cannot read CSS variables). Dark mode for canvas is out of scope for v1.
