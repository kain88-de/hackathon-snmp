# Trace format performance experiment — results

Date: 2026-06-11
Script: `experiments/trace_format_perf.py` (`uv run --with jsonschema python experiments/trace_format_perf.py`)
Tests the claims in `docs/trace-format.md` § 6a and the OIDEmu draft's performance model,
on schema-validated synthetic traces with realistic scrubbed-packet entropy.

| case                      | gz MB | raw MB | lines  | fit s | MB/s | peak MB | tail s |
| ------------------------- | ----- | ------ | ------ | ----- | ---- | ------- | ------ |
| 1k OIDs, bulk 10          | 0.01  | 0.2    | 104    | 0.00  | 44   | 0.5     | 0.00   |
| 100k OIDs, bulk 10        | 1.11  | 18.7   | 10004  | 0.40  | 46   | 23.8    | 0.02   |
| 100k OIDs, bulk 1 (worst) | 2.98  | 56.5   | 100004 | 1.72  | 33   | 39.6    | 0.06   |

Serve path: successor lookup over 100k sorted OIDs = **1.05 µs/lookup** (sorted list + bisect).

## Verdict per hypothesis

- **H1 size — PASS, claims were conservative.** Worst file is 3 MB gzipped (claimed ~10),
  56 MB raw (claimed 100–150). The 1k-OID case is 0.2 MB raw.
- **H2 speed — PASS.** Worst file streams + aggregates in 1.7 s (stdlib `json`; orjson
  would cut this further if it ever matters).
- **H3 memory — PASS.** Peak Python heap 24–40 MB, driven by the per-OID aggregate
  (10k vs 100k latency keys explains the 24→40 growth), not by the 3×
  larger file. Far below uncompressed file size.
- **H4 tail access — PASS.** Full-decompression cost to reach the trailing summary is
  0.02–0.06 s — the documented gzip limitation is real but cheap at these sizes.
- **H5 serve path — PASS.** ~1 µs per successor lookup; request-path budget is dominated
  by modeled device latency, not lookup.

Conclusion: no format changes needed for performance. The BGZF escape hatch (§ 6a)
remains unexercised and unneeded at realistic scale.
