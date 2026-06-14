# OIDviz — specification

Hosted browser-based viewer for oidtrace walk files.
Supersedes `docs/superpowers/specs/2026-06-11-oidviz-design.md`.

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

Svelte 5 · TypeScript · Bun · Vite · see `docs/web-guardrails.md` for toolchain guardrails.

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

The trace file is **not persisted** — no IndexedDB, no localStorage for file content.
On page reload, the app returns to the landing screen and the user must provide the file again.
Settings (slow threshold, selected view, filter state) ARE persisted in `localStorage` under key `oidviz`.

### localStorage schema

```ts
{
  slowMs: number;          // default 2 — slow RTT threshold in milliseconds
  view: 'waterfall' | 'subtree';  // last active view
}
```

human question: this should reset on reload! do we need it?

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
┌─────────────┬─────────────────────────────────┬─────────────┐
│   Sidebar   │          Main view               │  Slideout   │
│   210px     │          flex-1                  │  320px      │
│   fixed     │          Waterfall or Subtree    │  hidden     │
│             │                                  │  until sel. │
└─────────────┴─────────────────────────────────┴─────────────┘
```

Slideout slides in from the right when an exchange or subtree row is selected. It does not push the main view — it overlaps on narrow screens, sits alongside on wide screens.

---

## Sidebar

Always visible. Scrollable if content overflows.

Sections (top to bottom):

### Brand
`OIDviz` logotype.

### Walk summary
Shown immediately after a file loads. Fields:
- End reason chip (Completed / Unresponsive / OID Loop / Interrupted / Time Budget) — colour-coded
- Duration (e.g. `7.1s`)
- Exchanges count
- OIDs seen
- Violations total (0 = green, >0 = amber)

### Device
Extracted from system MIB OIDs in the first exchange responses:

| Field | Source OID |
|---|---|
| sysName | `1.3.6.1.2.1.1.5.0` |
| sysDescr (first line) | `1.3.6.1.2.1.1.1.0` |
| sysUpTime | `1.3.6.1.2.1.1.3.0` |
| sysLocation | `1.3.6.1.2.1.1.6.0` |
| sysContact | `1.3.6.1.2.1.1.4.0` |
| sysObjectID → vendor | `1.3.6.1.2.1.1.2.0` |

Fields that were not found in the walk are shown as `—`.

### Views
Navigation: Waterfall · Subtree. Active view highlighted.

### Settings
Slow threshold: number input (ms). Persisted. Changing it re-renders all views immediately.

### Walk config
Read-only fields from `header.settings`: bulk size, timeout, retries, give-up count, start OID.

---

## View: Waterfall

Canvas-based. Renders one horizontal bar per exchange on a shared time axis.

### Bar colours
- Blue `#3b82f6` — OK
- Amber `#f59e0b` — exchange has a violation
- Red `#ef4444` — attempt timed out
- Light blue `#93c5fd` — retry attempt (after a timeout)

### Toolbar
- Zoom slider (1×–20×, default 5×)
- Filters: **Violations** · **Slow** · **Retries** (each independently toggleable)
  - Slow filter is **on by default**
  - Slow filter uses the sidebar slow threshold
- Legend

### Exchange detail slideout
Opens on click. Contains:
- Status chip (ok / violation type / timeout+retry)
- Attempt timing bars (proportional to max RTT in this exchange)
- Exchange metadata: sent at, total RTT, attempts, PDU / bulk size
- Cursor OID with resolved name
- Response varbinds list: OID, resolved name if known, vtype badge
- Violation box (name + plain-English explanation) if applicable

### Performance and scale
Target: render up to **50k exchanges** without jank.
Implementation requirement: **row virtualisation** — only paint rows within the visible scroll viewport. A 100k-exchange trace should open in under 2 seconds on a mid-range laptop.

Performance gates (to be validated before shipping):
- 5k exchanges: open < 500ms, scroll at 60fps
- 50k exchanges: open < 2s, scroll at 60fps
- 100k exchanges: open < 5s (acceptable jank on scroll)

### Accessibility (WCAG 2.1 AA)
The canvas cannot be read by screen readers. Required mitigations:
- `role="application"` + `aria-label="Exchange waterfall"` on the canvas wrapper
- Keyboard navigation: Tab focuses the canvas; arrow keys move the selected exchange; Enter opens the detail slideout
- The detail slideout (HTML, not canvas) carries full accessible content for the selected exchange
- Focus moves to the slideout heading on open, returns to canvas on close

---

## View: Subtree

HTML table. One row per OID subtree aggregated from the walk.

### Aggregation
Single-pass over exchange records: for each response varbind OID, identify the longest matching OID prefix in the known subtree list. Accumulate exchange count, RTT sum, RTT samples (for P99), violation count.

P99 is computed from a reservoir sample (max 1000 samples per subtree) to avoid unbounded memory.

### Columns
Subtree (name + OID) · Exchanges · Avg RTT · P99 RTT · Violations · Reliability · Copy OID

### Latency colours
Relative to the slow threshold `slowMs`:
- Green: `< slowMs × 0.5`
- Amber: `≥ slowMs × 0.5`
- Red: `≥ slowMs`

Changing `slowMs` re-colours the entire table immediately.

### Filters (toolbar)
- **Slow P99** (amber) — show only rows where P99 RTT > slowMs
- **Violations** (red) — show only rows with violations > 0
- Filters compose with OR: either condition is sufficient to show a row
- A parent row is shown if it or any of its children match

### Subtree detail slideout
Opens on row click. Contains:
- Subtree name, OID, description
- Stats grid: exchanges, violations (coloured), avg RTT (coloured), P99 RTT (coloured)
- Notable exchanges list: worst RTT and violated exchanges for this subtree
  - Each notable exchange is expandable inline: RTT, attempts, violation box
- "slow P99" badge on section title when P99 > slowMs

---

## OID name resolution

Bundle a static map of ~2k standard RFC OID prefixes → names at build time.
Sources: SNMPv2-MIB, IF-MIB, IP-MIB, TCP-MIB, UDP-MIB, HOST-RESOURCES-MIB, SNMP-FRAMEWORK-MIB, common Cisco/Juniper/Net-SNMP enterprise prefixes.

Resolution: longest-prefix match. Unknown OIDs are shown as the numeric OID.

User-supplied MIB files are **out of scope** for the initial version.

---

## Reusable components (doctor UI contract)

The doctor UI is an interactive tool for tuning monitoring settings. It embeds oidviz components to show walk results and guide users without switching apps.

The following components must be designed as self-contained Svelte components that accept data via props, emit events upward, and carry no global state.

| Component | Props | Used by |
|---|---|---|
| `LatencyBar` | `ms: number, slowMs: number` | Subtree table, slideout stats |
| `ViolationBadge` | `type: string` | Waterfall, exchange detail |
| `ViolationBox` | `type: string, requestId?: {sent, received}` | Exchange detail slideout |
| `OidDisplay` | `oid: string, nameMap: Record<string,string>` | Varbind lists, subtree rows |
| `ExchangeDetail` | `exchange: Exchange` | Waterfall slideout, doctor UI |
| `SubtreeStat` | `label: string, value: string\|number, color?: string` | Slideout stats grid |
| `WalkSummaryBar` | `summary: Summary, header: Header` | Sidebar |
| `DeviceInfo` | `device: DeviceInfo` | Sidebar |

Components must:
- Accept `slowMs` as a prop where colour-coding is involved (no localStorage reads inside components)
- Use CSS custom properties for colours so the doctor UI can theme them
- Export TypeScript prop types

### Sharing mechanism
Components live in `oidviz/src/lib/`. The doctor UI imports them directly from the monorepo (workspace package) rather than a published npm package. If the doctor UI is built on a different stack, agree on a web component wrapper at that point.

---

## Accessibility — WCAG 2.1 AA requirements

### Colour
- All text/background combinations must meet 4.5:1 contrast ratio (3:1 for large text)
- Latency colouring (green/amber/red) must never be the **only** indicator — pair with a text label or icon
- The existing violation `!` marker on the canvas counts as the paired indicator for waterfall bars

### Keyboard
| Element | Keys |
|---|---|
| File drop zone | Tab to focus, Enter/Space to open file picker |
| Waterfall canvas | Tab to focus, ←→ to step exchanges, Enter to open slideout |
| Subtree table rows | Tab, Enter to open slideout |
| Slideout | Escape to close, focus returns to trigger element |
| Filter buttons | Tab, Space/Enter to toggle |
| Number inputs | Standard keyboard editing |

### Screen reader
- Landmark roles: `<aside>` for sidebar, `<main>` for view area, `role="complementary"` for slideout
- Table: proper `<thead>`, `<th scope="col">` for all columns
- Sort buttons: `aria-sort="ascending|descending|none"`
- Canvas: `role="application"`, `aria-label`, hidden off-screen table with the currently selected exchange for screen readers
- Status messages (file loaded, filter changed): `aria-live="polite"` region in the sidebar

### Focus management
- Slideout open: focus moves to the slideout's `<h2>` heading
- Slideout close: focus returns to the row/bar that opened it
- File loaded: focus moves to the first view (waterfall or last selected)

### Axe-core CI gate
Run `axe-core/cli` against the dev server as part of CI. Zero violations at WCAG 2.1 AA level is a hard gate before merge.

---

## Open questions / future work

- **Dark mode**: not in scope for v1, but CSS custom properties must be used throughout so it can be added without structural changes
  -> yes dark mode, and guess from system by default show this in the header/hero
- **URL state**: view and filter state could be encoded in the URL hash to allow bookmarking a specific view — deferred
  -> hm is this needed?
- **Export**: copy OID is implemented; CSV export of subtree stats is a reasonable v2 addition
 -> no
- **Trace comparison**: loading two traces side-by-side is useful for before/after tuning — deferred
 -> yes not needed here
