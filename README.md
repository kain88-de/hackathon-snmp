# OIDSense

OIDSense is a suite of tools to troubleshoot SNMP devices — the slow, the
RFC-violating, and the silently broken.

## The tools

**doctor** — the planned MVP entry point (not yet implemented). Design: one command
that walks the support settings ladder down until the device responds cleanly,
subtree-scoped and time-budgeted, answering: _which settings make this device work?_
The exact ladder rungs are still an open question — see the design sketch:
`docs/superpowers/specs/2026-06-11-doctor-mvp-design.md`.

**OIDTrace** — the capture layer and CLI underneath everything, implemented and
validated end-to-end (see "Where things stand" below). Walks a device and records
parsed wire evidence — per-attempt timing, the request-id the device actually
returned, protocol violations — into a portable gzipped-JSONL trace. Traces contain no
values, no packet bytes, and no device identity; an admin can read one with `zcat`
before sharing it. Format spec:
`traceformat/trace-format.md` (+ JSON Schema).

**OIDViz** — a Vue web app that loads an `oidtrace` trace file in the browser and
renders it client-side, no server round-trip. Current views are documented in
[`oidviz/README.md`](oidviz/README.md), not restated here. Live at the GitHub Pages
link below, or build and self-host.

Under the hood, a **quirk emulator** (fixed request-ids, bulk-size crashes, slow
subtrees, end-of-MIB silence) lives in the test suite — every pathology the tools must
handle is reproducible over loopback UDP. An **adaptive settings finder** (survey →
pinpoint slow OIDs → derive settings) is doctor's planned successor; both are sketched
in the design doc linked above.

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

**Status**: the capture layer (`oidtrace`) is implemented end-to-end and validated
against a real snmpd and net-snmp cross-walks. Exactly what's supported (and what
isn't yet) is tracked in [`oidtrace/README.md`](oidtrace/README.md)'s own
"What is implemented, and what is not" section — not restated here, so the two
can't silently disagree. The trace format (`traceformat/trace-format.md` +
`traceformat/trace-format.schema.json`) is authoritative. Next: the doctor, then
further OIDViz work.
