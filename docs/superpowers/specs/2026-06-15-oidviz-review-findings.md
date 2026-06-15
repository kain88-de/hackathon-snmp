# OIDviz spec review findings

Generated 2026-06-15 by Opus critical review. Items 1–6 (must fix) are resolved in the spec.
Items 7–11 (should fix) are resolved in the spec. Items 12–16 are open and tracked here.

---

## Must fix — resolved

1. ~~`violation` (singular) vs `violations` (array) — schema field is `violations: array<string>`~~
2. ~~Type generation path `../traceformat/docs/trace-format.schema.json` doesn't exist — correct path is `../docs/trace-format.schema.json`~~
3. ~~"give-up count" doesn't exist in schema — real fields are `time_budget_s` and `resume_from`~~
4. ~~Timeout detection wrong — schema signals failed attempt via `received_at: null`, not RTT threshold~~
5. ~~RTT undefined for failed attempts — no rule for what RTT is when `received_at` is null~~
6. ~~Device section implies per-exchange OID lookup — actually read from `system_info.values` map~~

---

## Should fix — resolved

**7. Web Worker vs prototype contradiction** ✓
Spec now describes the product behaviour ("UI stays responsive during loading") rather than the
implementation mechanism. Web Worker remains the implementation choice for v1 but is not
mentioned in the spec.

**8. Three inconsistent well-known-prefix lists** ✓
The three lists serve distinct purposes and are intentionally separate:
- Incident Stack `oidRegion()`: coarse topology grouping for clustering (8 entries + enterprises catch-all)
- OID Tree `WK` map: human-readable display labels for trie nodes (different set)
- Build-time map: comprehensive tooltip/hover resolution (~2k prefixes)
Spec now documents this distinction in each section.

**9. Filter algebra not defined** ✓
Defined: an exchange/cluster is shown if it matches at least one checked criterion. When no filter
is checked, all exchanges are shown. Compose rule documented per view in the spec (Filters section).
The Timeouts filter is now fully independent — it surfaces timeout exchanges/clusters on its own.

**10. Non-goals are weak** ✓
Added: no multi-file comparison, no export, no URL-encoded state, no annotations, no persistent
storage of any kind.

**11. Clustering rule ambiguous** ✓
OID source: `request.oids[0]` (always present; correct for clustering — it represents the OID
being walked at that point, not what the device happened to respond with).
Gap counting: gap = `(indexB − indexA − 1)` non-anomalous exchanges between two anomalous ones.
The non-anomalous scan guard `i − lastIdx ≤ GAP_WINDOW` is a correct early-exit equivalent.
Spec now uses `(indexB − indexA − 1)` as the canonical definition.

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
