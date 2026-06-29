# OIDSense

OIDSense is a suite of tools to troubleshoot SNMP devices — the slow, the
RFC-violating, and the silently broken.

## The tools

**doctor** — the MVP. One command that automates the support settings ladder
(bulk 10 → 8 → 5 → 1, then timeouts), subtree-scoped and time-budgeted, and answers:
_which settings make this device work?_ Output: a paste-ready Checkmk settings verdict,
a self-contained HTML report, and a trace bundle as the escalation artifact. Progress
streams live while it runs.

**OIDTrace** — the capture layer and CLI underneath everything. Walks a device and
records parsed wire evidence — per-attempt timing, the request-id the device actually
returned, protocol violations — into a portable gzipped-JSONL trace. Traces contain no
values, no packet bytes, and no device identity; an admin can read one with `zcat`
before sharing it. Format spec:
`docs/trace-format.md` (+ JSON Schema).

**OIDViz** — renders a trace or session bundle as a self-contained HTML report:
verdict panel, latency waterfall, subtree heat, run comparison. Opens by double-click,
attaches to a ticket, works offline. Shares its rendering with the doctor's report.

Under the hood, a **quirk emulator** (fixed request-ids, bulk-size crashes, slow
subtrees, end-of-MIB silence) lives in the test suite — every pathology the tools must
handle is reproducible over loopback UDP. An **adaptive settings finder** (survey →
pinpoint slow OIDs → derive settings) is the doctor's planned successor; its design
sketches live in git history.

## Quick start

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

**One-off — no install:**
```sh
uvx --from "git+https://github.com/kain88-de/hackathon-snmp#subdirectory=oidtrace" \
    oidtrace walk v2c 192.168.1.1 --community public
```

**Persistent install:**
```sh
uv tool install "git+https://github.com/kain88-de/hackathon-snmp#subdirectory=oidtrace"
oidtrace walk v2c 192.168.1.1 --community public
```

**Common options:**
```sh
oidtrace walk v2c 192.168.1.1 \
    --community public \
    --bulk-size 5 \
    --timeout 5 \
    --time-budget 120 \
    --out ./traces \
    --label my-device
```

**v3 (authNoPriv):**
```sh
oidtrace walk v3 192.168.1.1 \
    --user myuser --auth-proto SHA --auth-pass secret
```

Traces are written as gzipped JSONL (`.oidtrace.jsonl.gz`) and are readable with `zcat`.

## OIDViz

Live at **[kain88-de.github.io/hackathon-snmp](https://kain88-de.github.io/hackathon-snmp/)** — deployed automatically from `main` via GitHub Actions whenever `oidviz/` changes.

To run locally or self-host:
```sh
cd oidviz && bun install && bun run build   # outputs to oidviz/dist/
```
Then serve `dist/` with any static file server or open `dist/index.html` directly.

## Where things stand

**Status**: the capture layer was implemented end-to-end (validated against a real
snmpd), then deliberately deleted for a one-shot replay experiment — the refined spec
and contract-level plan are the surviving artifacts and the input for the rebuild.
Design specs live in `docs/superpowers/specs/`; the trace format
(`docs/trace-format.md` + `docs/trace-format.schema.json`) is authoritative and
validated by experiments in `experiments/`. The plan to execute:
`docs/superpowers/plans/2026-06-11-oidtrace.md`. Next: the doctor, then OIDViz.
