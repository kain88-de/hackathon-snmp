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

---

## Tech stack

Svelte 5 · TypeScript · Bun · Vite · see `oidviz/docs/web-guardrails.md` for toolchain guardrails.

Types are generated from `../traceformat/docs/trace-format.schema.json`:
```sh
bunx json-schema-to-typescript ../traceformat/docs/trace-format.schema.json -o src/types.gen.ts
```

Do not hand-write types for trace records.

---

## File loading and state model

### Load flow

1. App opens → landing screen with drag-and-drop zone and file-picker button
2. User drops or selects a `.oidtrace.jsonl.gz` file
3. File is parsed in a **Web Worker** (gzip decompress + JSONL parse)
4. A single-pass aggregator builds the ViewModel (subtree stats, device info from system OIDs) without holding all raw records in memory
5. App transitions to the viewer layout

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

---

## Sidebar

Always visible. Scrollable if content overflows.

Sections (top to bottom):

### Brand
`OIDviz` logotype.

### Walk summary
Shown after a file loads:
- End reason chip (Completed / Unresponsive / OID Loop / Interrupted / Time Budget) — colour-coded
- Duration (e.g. `7.1s`)
- Exchanges count
- OIDs seen
- Violations total (0 = green, >0 = amber)

### Device
Extracted from system MIB OIDs in exchange responses:

| Field | Source OID |
|---|---|
| sysName | `1.3.6.1.2.1.1.5.0` |
| sysDescr (first line) | `1.3.6.1.2.1.1.1.0` |
| sysUpTime | `1.3.6.1.2.1.1.3.0` |
| sysLocation | `1.3.6.1.2.1.1.6.0` |
| sysContact | `1.3.6.1.2.1.1.4.0` |
| sysObjectID | `1.3.6.1.2.1.1.2.0` |

Fields not found in the walk are shown as `—`. The section is hidden if no system MIB values were seen.

### Views
Navigation: Incident Stack · Minimap + Detail · OID Tree. Active view highlighted.

### Filters
- **Slow** (checkbox, on by default) — exchanges with RTT > slowMs
- **Violations** (checkbox, on by default) — exchanges with a violation
- **Retries** (checkbox, on by default) — exchanges with >1 attempt
- **Timeouts** (checkbox, off by default) — exchanges where an attempt timed out

Changing a filter immediately re-renders the active view.

### Settings
Slow threshold: number input (ms, default 1000). Changing it re-renders all views immediately.

### Walk config
Read-only fields from `header.settings`: bulk size, timeout, retries, give-up count, start OID.

---

## View: Incident Stack

Clusters anomalous exchanges into named, scored incidents using a gap-window algorithm.

### Anomaly detection
An exchange is anomalous if any of: RTT > slowMs, has a violation, has >1 attempt (retry), timed out.

### Clustering
Anomalous exchanges within a configurable gap window (default 8 non-anomalous exchanges) are merged into one cluster. Two anomalous exchanges separated by more than the gap window are merged only if they fall in the same OID region.

### OID regions
Well-known prefixes mapped to region names: `system`, `ifTable`, `interfaces`, `ip`, `tcp`, `snmp`, `hrSystem`, `enterprises`. Unknown OIDs use the first 8 arcs.

### Incident scoring
```
score = timeoutCount × 100
      + violationTypes × 50
      + retryCount × 10
      + log10(peakRtt) × 5
      + memberCount × 0.1
```

### Row layout
Each incident row (72px):
- **Severity chip** (48×48px): `err` (any timeout), `warn` (violation or slow), `info` (retry only)
- **Title**: `{region} — {type}` where type is the dominant anomaly
- **Subtitle**: seq range · peak RTT · exchange count · retry count
- **Walk position bar**: shows where in the walk this incident falls (proportional)

### Filters
Incidents are hidden/shown based on active sidebar filters. Count label updates accordingly.

### Virtualised rendering
Only rows within the visible viewport are rendered. ROW_PX = 72.

### Incident detail modal
Opens on row click. Fixed overlay with backdrop; clicking the backdrop or pressing Escape closes it.
- Header: incident number · region · seq range · Prev / Next navigation · close button
- Summary stats grid: Peak RTT, Timeouts, Retries, Exchanges, Violations
- Exchange table: Seq · OID · RTT · Flag (timeout / violation type / retry count)

---

## View: Minimap + Detail

Two-panel canvas layout for timeline-based exploration of the full walk.

### Minimap panel (80px tall)
Covers the full walk duration. Each pixel column represents a time bucket. Colour priority: timeout (`#ef4444`) > violation (`#f59e0b`) > retry (`#93c5fd`) > slow (`#3b82f6`) > ok (`#94a3b8`). Bar height proportional to event count in the bucket.

A selection rectangle highlights the current detail window.

Tooltip on hover: time offset, event count, max RTT, violation flag.

### Detail panel (flex remainder)
Shows individual exchange bars for exchanges whose time window overlaps the selection:
- One horizontal bar per exchange on a vertical list, ordered by sent time
- Bar length proportional to RTT on the shared time axis
- Retry attempts rendered as stacked bars (same colours as minimap)
- Violation marker `!` after the bar
- Seq number label on the left
- Time-axis tick marks and labels at the top

Hover tooltip: seq, % into trace, violation/status, RTT, sent-at time, OID.

### Window interaction
- **Drag** on empty minimap area: create new window
- **Drag** inside window: pan
- **Drag** window edges (±6px): resize
- **Click** (no drag): centre window at clicked point (window width = 5% of trace)
- **Arrow Left / Right**: shift window by 20% of current span

Toolbar: window time range label · "Zoom to problems" (focuses densest problem bucket) · "Reset window" (restores default 5% width).

### Filters
Active sidebar filters determine which exchanges are included in the minimap buckets and detail list.

---

## View: OID Tree

Trie built from exchange response varbind OIDs (up to 7 prefix levels). Stats rolled up per node.

### Data model
Each node: arc label, full OID, optional well-known name, children map, leaf exchanges, stats (count, maxRtt, violationCount), severity (0 = ok, 1 = slow, 2 = violation).

Leaves are individual filtered exchanges attached to the deepest matching prefix node.

Well-known prefixes: `system`, `interfaces`, `ip`, `tcp`, `snmp`, `host`, `cisco`, `snmpVacm`.

### Rollup
Stats aggregate bottom-up: children's stats fold into the parent. Severity propagates upward (max).

### Row layout
Virtualised, ROW_H = 22. Two row types:

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

Bundle a static map of ~2k standard RFC OID prefixes → names at build time.
Sources: SNMPv2-MIB, IF-MIB, IP-MIB, TCP-MIB, UDP-MIB, HOST-RESOURCES-MIB, SNMP-FRAMEWORK-MIB, common Cisco/Juniper/Net-SNMP enterprise prefixes.

Resolution: longest-prefix match. Unknown OIDs are shown as the numeric OID.

User-supplied MIB files are out of scope for the initial version.

---

## Reusable components (doctor UI contract)

The doctor UI embeds oidviz components to show walk results. The following components must be self-contained Svelte components: props-only (no global state reads), CSS custom properties for colours, exported TypeScript prop types.

| Component | Props | Used by |
|---|---|---|
| `LatencyBar` | `ms: number, slowMs: number` | OID Tree, incident modal stats |
| `ViolationBadge` | `type: string` | Incident Stack, OID Tree, incident modal |
| `ViolationBox` | `type: string, requestId?: {sent, received}` | Incident modal exchange table |
| `OidDisplay` | `oid: string, nameMap: Record<string,string>` | Incident modal, OID Tree |
| `IncidentDetail` | `cluster: Cluster, exchanges: Exchange[]` | Incident modal, doctor UI |
| `WalkSummaryBar` | `summary: Summary, header: Header` | Sidebar |
| `DeviceInfo` | `device: DeviceInfo` | Sidebar |

Components live in `oidviz/src/lib/`. The doctor UI imports them as a monorepo workspace package.

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
`axe-core/cli` run against the dev server. Zero WCAG 2.1 AA violations is a hard gate before merge.

---

## Dark mode

Default to system preference (`prefers-color-scheme`). Toggle in the sidebar header. CSS custom properties used throughout — no hard-coded colours in components. Dark mode is in scope for v1.
