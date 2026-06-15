# OIDviz spec review findings

Generated 2026-06-15 by Opus critical review. Items 1–6 (must fix) are resolved in the spec.
Items 7–16 are open and tracked here.

---

## Must fix — resolved

1. ~~`violation` (singular) vs `violations` (array) — schema field is `violations: array<string>`~~
2. ~~Type generation path `../traceformat/docs/trace-format.schema.json` doesn't exist — correct path is `../docs/trace-format.schema.json`~~
3. ~~"give-up count" doesn't exist in schema — real fields are `time_budget_s` and `resume_from`~~
4. ~~Timeout detection wrong — schema signals failed attempt via `received_at: null`, not RTT threshold~~
5. ~~RTT undefined for failed attempts — no rule for what RTT is when `received_at` is null~~
6. ~~Device section implies per-exchange OID lookup — actually read from `system_info.values` map~~

---

## Should fix — open

**7. Web Worker vs prototype contradiction**
Spec mandates a Web Worker with streaming aggregator that never holds all exchanges in memory.
The prototype holds the full `ALL[]` array and all three views re-scan it on every filter change.
Decision needed: is the Worker + streaming model real scope for v1, or aspirational? If real,
it requires a different data model (pre-aggregated ViewModel instead of raw exchange array),
which affects every view.

**8. Three inconsistent well-known-prefix lists**
- Incident Stack `oidRegion()`: `system, ifTable, interfaces, ip, tcp, snmp, hrSystem, enterprises`
- OID Tree `WK` map: `system, interfaces, ip, tcp, snmp, host, cisco, snmpVacm`
- Build-time OID name resolution: ~2k RFC prefix map (separate, not yet defined)
Decision needed: should these share one source, or are they intentionally separate
(clustering vs. tree labels vs. tooltip resolution)?

**9. Filter algebra not defined**
The four filters (Slow, Violations, Retries, Timeouts) interact differently across views.
In the prototype, Incident Stack shows a timeout cluster if *any* of Slow/Violations/Retries
is checked, making the Timeouts checkbox mostly inert there.
The spec describes four independent toggles but doesn't define the compose rule per view.

**10. Non-goals are weak**
Current non-goals (real-time monitoring, MIB compilation) are obvious and don't protect scope.
Missing non-goals that would actually constrain implementation decisions:
- No multi-file comparison / side-by-side
- No export (CSV, PNG, etc.)
- No URL-encoded view state / bookmarking
- No annotation or note-taking on traces
- No persistent storage of any kind

**11. Clustering rule ambiguous**
Two open questions:
- Which OID drives region assignment — `request.oids[0]` (what the prototype uses) or response
  varbind OIDs (what the tree uses)?
- Gap counting: the prototype mixes `i - lastIdx - 1` (anomalous-to-anomalous) and `i - lastIdx`
  (absolute index), inconsistently with the prose "8 non-anomalous exchanges".

---

## Consider — open

**12. Implementation constants in the spec**
Pixel values (`ROW_PX = 72`, `ROW_H = 22`, minimap `80px`, drag edge `±6px`), exact hex
colours (`#ef4444`, `#f59e0b`, etc.), and scoring weights belong in code. The prototype is
already the authoritative visual reference. Consider stripping these to "see prototype" and
keeping only product-meaningful defaults (slow threshold = 1s, gap window = 8).

**13. Accessibility CI gate is aspirational**
`axe-core` cannot inspect canvas internals. The Minimap + Detail view is entirely canvas-based;
its keyboard and screen-reader story is unaddressed. The "Zero WCAG 2.1 AA violations" gate
only applies to DOM-based content (sidebar, incident modal, OID Tree).

**14. Dark mode for canvas is unbudgeted**
Spec mandates CSS custom properties with no hard-coded colours and dark mode in scope for v1.
Canvas `fillStyle` calls cannot use CSS variables — dark mode for the Minimap + Detail view
requires explicit JS colour switching logic, which is non-trivial.

**15. Truncated file error UX**
Spec says "parse to last complete line; warn in sidebar." Prototype swallows parse errors
silently (`catch(e) { console.error(...) }`). Decide whether a sidebar warning is in scope
and what it should say.

**16. File input accepts plain `.jsonl` but parser always runs gzip decompression**
The prototype's file input `accept` attribute includes `.jsonl` (uncompressed), but
`parseAndShow` always pipes through `DecompressionStream('gzip')` — a plain `.jsonl` file
would fail to parse. Decide: support uncompressed input or restrict the file picker to `.gz`
only.
