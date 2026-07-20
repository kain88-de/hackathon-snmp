# OIDTrace File Format Specification

Version: 1 (`format_version: 1`)
Status: draft

This document is the authoritative specification of the OIDTrace file format. The
architecture rationale for the capture tool lives in
[`../oidtrace/README.md`](../oidtrace/README.md); where the two disagree, this
document wins.

## 1. Overview

An OIDTrace file records one SNMP walk (one settings combination) against one device as a
sequence of self-describing JSON records. Design goals, in priority order:

1. **Transparency** — an admin can inspect the file with `zcat`/`jq`/a text editor and
   verify what is being shared before uploading it.
2. **No values** — SNMP values are never stored, with one narrow, visible exception
   (§ 7).
3. **Evidence-grade detail** — parsed wire behavior and per-attempt timing survive,
   including protocol violations that SNMP libraries normally hide.
4. **Crash-validity** — a truncated file (crash, Ctrl-C, full disk) is still a valid,
   useful trace.

## 2. File conventions

- **Encoding**: gzip-compressed JSON Lines. Each line is one UTF-8 JSON object terminated
  by `\n`. No blank lines.
- **File extension**: `.oidtrace.jsonl.gz`.
- **Record order**: `header` first; `system_info` (point `start`) if present comes next;
  then `exchange` and `event` records in capture order; `system_info` (point `end`) and
  `summary` last, both best-effort.
- **Truncation semantics**: readers MUST accept a file that ends mid-line or without
  `summary`/`system_info(end)` records; all complete lines before the truncation point are
  valid. Writers flush after every record.

## 3. Common conventions

- **Timestamps**:
  - `started_at` (header only): wall-clock time, ISO 8601 UTC with second precision,
    e.g. `"2026-06-11T14:03:07Z"`. The only wall-clock time in the file.
  - All other time fields (`t`, `sent_at`, `received_at`, `at`): **seconds since walk
    start** as a JSON number with microsecond precision (e.g. `12.004317`), measured on a
    monotonic clock. Rationale: latency arithmetic is the point of the format; monotonic
    relative time is immune to NTP steps and keeps records compact.
- **OIDs**: dotted-decimal strings without a leading dot, e.g. `"1.3.6.1.2.1.1.1.0"`.
- **Unknown fields**: readers MUST ignore fields they do not know. Adding optional fields
  is a non-breaking change; removing or re-typing a field requires bumping
  `format_version`.
- **Open enums**: `violations[]`, `event.kind`, and `end_reason` may grow values within a
  format version; readers MUST tolerate unknown values. Producers should emit the closed
  `StrEnum`s in `traceformat/vocab.py` (`Violation`, `EventKind`, `EndReason`,
  `AttemptError`) rather than ad hoc strings — see that package's README for the
  procedure for adding a new value.

## 4. Record types

Every record has a `type` field: one of `header`, `system_info`, `exchange`, `event`,
`summary`.

### 4.1 `header`

First record of every file.

| Field            | Type   | Req. | Meaning                                             |
| ---------------- | ------ | ---- | --------------------------------------------------- |
| `type`           | string | yes  | `"header"`                                          |
| `format_version` | int    | yes  | This document: `1`                                  |
| `tool`           | string | yes  | Producer and version, e.g. `"oidtrace 0.1.0"`       |
| `started_at`     | string | yes  | ISO 8601 UTC wall-clock walk start                  |
| `label`          | string | no   | Admin-chosen run label; the only correlation handle |
| `session`        | object | yes  | Ties files of one invocation together (see below)   |
| `snmp.version`   | string | yes  | `"1"`, `"2c"`, or `"3"`                              |
| `settings`       | object | yes  | See below                                           |

`session` fields: `id` (string — random UUID generated per `walk` invocation; derived
from nothing, leaks nothing), `run` (int, 1-based index within the invocation),
`runs_total` (int). A matrix invocation writes one file per settings combo, all sharing
the same `session.id` — the correlation profile fitting and cross-run analysis need. A
single walk is `run: 1, runs_total: 1`.

`settings` fields: `bulk_size` (int; `0` means GetNext walk), `timeout_s` (number),
`retries` (int), `start_oid` (string), `time_budget_s` (number, optional),
`resume_from` (OID string, optional — the walk cursor was continued from a previous
run's stopping point; `start_oid` remains the subtree bound).

The header deliberately contains **no target host name, IP, or port** (§ 7). SNMPv3
walks (`snmp.version: "3"`) still carry no credentials or engine parameters here — the
discovery exchange that establishes them is recorded as an ordinary `exchange` record
with `request.pdu: "discovery"` (§ 4.3), same as every other request.

```json
{
  "type": "header",
  "format_version": 1,
  "tool": "oidtrace 0.1.0",
  "started_at": "2026-06-11T14:03:07Z",
  "label": "switch-floor3",
  "session": {
    "id": "5e1f3a9c-6a86-4a0b-9b6e-2f6d6a9c1d42",
    "run": 2,
    "runs_total": 5
  },
  "snmp": { "version": "2c" },
  "settings": {
    "bulk_size": 10,
    "timeout_s": 2.0,
    "retries": 2,
    "start_oid": "1.3.6.1"
  }
}
```

### 4.2 `system_info`

Values for the system-OID allowlist, captured unconditionally by a dedicated Get at walk
start and again at walk end — every walk, no flag to disable it.

| Field    | Type   | Req. | Meaning                                   |
| -------- | ------ | ---- | ----------------------------------------- |
| `type`   | string | yes  | `"system_info"`                           |
| `at`     | number | yes  | Seconds since walk start                  |
| `point`  | string | yes  | `"start"` or `"end"`                      |
| `values` | object | yes  | OID → value; only allowlisted OIDs appear |

Allowlist in format version 1: sysDescr.0 (`1.3.6.1.2.1.1.1.0`, string), sysObjectID.0
(`1.3.6.1.2.1.1.2.0`, OID string), sysUpTime.0 (`1.3.6.1.2.1.1.3.0`, integer ticks),
sysName.0 (`1.3.6.1.2.1.1.5.0`, string).
A sysUpTime at `end` lower than at `start` proves a mid-walk device reboot.

The underlying Get requests are real wire traffic like any other exchange in the walk:
they are **also recorded as ordinary `exchange` records** (participating in `seq`), with
their own timing and violations as evidence.

```json
{
  "type": "system_info",
  "at": 0.0412,
  "point": "start",
  "values": {
    "1.3.6.1.2.1.1.1.0": "Cisco IOS 15.2",
    "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.516",
    "1.3.6.1.2.1.1.3.0": 492711442,
    "1.3.6.1.2.1.1.5.0": "switch-floor3"
  }
}
```

### 4.3 `exchange`

One record per logical request. `seq` starts at 1 and increments per logical request
(retries do not increment it).

| Field             | Type   | Req. | Meaning                                               |
| ----------------- | ------ | ---- | ----------------------------------------------------- |
| `type`            | string | yes  | `"exchange"`                                          |
| `seq`             | int    | yes  | 1-based logical request counter                       |
| `request`         | object | yes  | What we sent (§ below)                                |
| `attempts`        | array  | yes  | One entry per datagram sent, including retries        |
| `response`        | object | no\* | The decoded response attributed to this exchange      |
| `stray_responses` | array  | no   | Datagrams not attributable as _the_ response          |
| `violations`      | array  | no   | Protocol violations observed (strings, open enum)     |
| `malformed`       | object | no\* | Present when the attributed datagram failed to decode |

\* Exactly one of: `response` present (decoded), `malformed` present (undecodable), or
both absent (no answer at all — every attempt timed out).

`request`: `pdu` (`"get"` | `"getnext"` | `"getbulk"` | `"discovery"` — the SNMPv3
authoritative-engine probe that precedes the walk proper, always `seq: 1`, `oids: []`),
`request_id` (int, as sent), `oids` (array of OID strings), `non_repeaters` +
`max_repetitions` (int, getbulk only).

`attempts[]`: `sent_at` (number), `received_at` (number | null — null means this attempt
got no datagram), `error` (string, optional, open enum — a socket-level error for this
attempt instead of silence: `"icmp-port-unreachable"`, `"icmp-host-unreachable"`,
`"send-failed"`; when set, `received_at` is null). Instant ICMP refusal and silent
timeout are diagnostically opposite outcomes and must be distinguishable.

Retries resend the **byte-identical datagram** (same request-id, matching net-snmp
behavior and avoiding double-processing semantics on agents that dedupe by request-id) —
which is why a late-arriving response is inherently
ambiguous between attempts: a reply to attempt 1 arriving just after attempt 2 was sent
is indistinguishable from a fast reply to attempt 2. The recorder attributes the response
to the attempt whose `received_at` is set, but that attribution is a bookkeeping
convention, not a timing claim.

**Normative rules for timing consumers** (profile fitting, latency analysis):

1. Only **single-attempt exchanges** (`len(attempts) == 1`) are valid point samples for
   latency. They are unambiguous by construction.
2. For multi-attempt exchanges, the true latency is only bounded:
   `received_at − attempts[-1].sent_at ≤ latency ≤ received_at − attempts[0].sent_at`.
   Use the bounds or discard; never use the naive last-attempt delta — when device
   latency consistently exceeds the timeout, that delta systematically underestimates.
3. **Disambiguation via strays**: a device answering every attempt produces the response
   plus a stray whose arrival gap matches the gap between attempt sends; when present,
   this pins the true latency to `first datagram − attempts[0].sent_at`. The per-datagram
   timestamps exist precisely to allow this.
4. A range that yields _only_ multi-attempt exchanges means the timeout was too low for
   reliable measurement there — the correct remedy is recapturing that range with a
   larger timeout, not statistical heroics over ambiguous samples.

`response`: `request_id` (int, **as returned by the device** — compare with
`request.request_id`), `error_status` (int), `error_index` (int), `varbinds` (array).

`varbinds[]`: `oid` (string), `vtype` (string, § 5), `vlen` (int — byte length of the BER
value octets of this varbind; value bytes themselves are never stored).

`stray_responses[]`: `received_at` (number). Duplicates, late replies to earlier
requests, unsolicited datagrams.

`malformed`: `error` (string — decode failure reason), `length` (int — datagram size in
bytes), `salvaged` (object, optional — whatever fields could be partially decoded).

`violations[]` initial vocabulary: `"request-id-mismatch"`, `"oid-not-increasing"`,
`"missing-end-of-mib"`, `"duplicate-response"`, `"malformed-ber"`,
`"response-from-unexpected-source"` (datagram arrived from a different source port or
address than queried — the _fact_ is recorded, the address never is).

```json
{
  "type": "exchange",
  "seq": 42,
  "request": {
    "pdu": "getbulk",
    "request_id": 1042,
    "oids": ["1.3.6.1.2.1.2.2.1.3"],
    "non_repeaters": 0,
    "max_repetitions": 10
  },
  "attempts": [
    { "sent_at": 12.004317, "received_at": null },
    { "sent_at": 14.004901, "received_at": 14.18223 }
  ],
  "response": {
    "request_id": 1,
    "error_status": 0,
    "error_index": 0,
    "varbinds": [
      { "oid": "1.3.6.1.2.1.2.2.1.3.1", "vtype": "Integer", "vlen": 1 }
    ]
  },
  "stray_responses": [{ "received_at": 14.190112 }],
  "violations": ["request-id-mismatch", "duplicate-response"]
}
```

### 4.4 `event`

Walk-level observations not tied to one exchange.

| Field    | Type   | Req. | Meaning                  |
| -------- | ------ | ---- | ------------------------ |
| `type`   | string | yes  | `"event"`                |
| `at`     | number | yes  | Seconds since walk start |
| `kind`   | string | yes  | Open enum, see below     |
| `detail` | object | no   | Kind-specific payload    |

Initial kinds: `"oid-loop-detected"` (detail: `{oid}`), `"walk-aborted-by-user"`,
`"time-budget-exceeded"`.

### 4.5 `summary`

Last record, best-effort (may be missing in truncated files).

| Field              | Type   | Req. | Meaning                                                                                  |
| ------------------ | ------ | ---- | ---------------------------------------------------------------------------------------- |
| `type`             | string | yes  | `"summary"`                                                                              |
| `at`               | number | yes  | Seconds since walk start (= walk duration)                                               |
| `exchanges`        | int    | yes  | Logical requests issued                                                                  |
| `oids_seen`        | int    | yes  | Distinct OIDs returned                                                                   |
| `end_reason`       | string | yes  | `"completed"`, `"unresponsive"`, `"interrupted"`, `"time-budget-exceeded"`, `"oid-loop"` |
| `violation_counts` | object | yes  | violation string → count                                                                 |

## 5. `vtype` vocabulary

BER universal and SNMP application types: `"Integer"`, `"OctetString"`, `"Null"`,
`"ObjectIdentifier"`, `"IpAddress"`, `"Counter32"`, `"Gauge32"`, `"TimeTicks"`,
`"Opaque"`, `"Counter64"`, and the v2c exceptions `"NoSuchObject"`, `"NoSuchInstance"`,
`"EndOfMibView"`. Unknown BER tags are recorded as `"tag:0xNN"`.

## 6. Streaming guarantee

The format is designed for **single-pass streaming consumption**: every record is
self-contained, all run-level context lives in the `header` (first line), and no record
references a later one. A conforming reader processes any trace with memory proportional
to its own aggregates (e.g. distinct OIDs), never to file size. This is a normative
constraint on future format changes: no record type may require look-ahead or whole-file
loading.

Realistic scale for consumers (measured against synthetic profiles in an experiment
retired from the tree — git history holds it): a 100k-OID device walked at
bulk 1 is ~100k lines, ~3 MB gzipped / ~56 MB uncompressed (measured before packet-bytes
fields were removed from the format — v1 traces are smaller), streamed and aggregated in under 2 s
with peak memory bounded by the per-OID aggregate (~40 MB), not file size. Trace files
are inputs to offline
aggregation (fitting, analysis, summaries); request-time consumers (OIDEmu serving) read
fitted profiles, never traces.

Known limitation: gzip is not seekable, so random access (reading only the trailing
`summary`, jumping to one exchange) costs a decompression of everything before it.
Designated escape hatch if interactive tooling ever needs it: write BGZF (block-gzip) —
output remains a valid gzip stream for all existing readers, gains block-level random
access. Additive writer change; no format version bump.

## 7. Privacy guarantees

A format-version-1 trace never contains:

- the target host name, IP address, or port;
- the SNMP community string;
- packet bytes;
- SNMP values — with one exception: the `system_info` allowlist (§ 4.2), captured on
  every walk.

It does contain: OID names and tree structure (reveals device vendor/MIBs and table
cardinalities), value types and lengths, timing, and the optional admin-chosen `label`.

## 8. JSON Schema

A machine-checkable companion schema lives at **`traceformat/trace-format.schema.json`** (JSON
Schema draft 2020-12): one `oneOf` branch per record type, validating any single line of a
trace. It encodes the structural rules of this document — including the
`response`/`malformed` mutual exclusion and the getbulk-requires-repetition-fields rule —
while leaving open enums and unknown extra fields unconstrained, as § 3 requires. The test
suite validates every line the trace writer emits against it. Producer/consumer code
uses pydantic models **generated from this schema** (`traceformat` package,
datamodel-code-generator; `just gen-types` regenerates, a CI freshness check forbids
drift). If this document and the schema disagree, this document wins; fix the schema.

## 9. Versioning

`format_version` is a single integer. Within a version: new optional fields and new enum
values may appear; readers ignore/tolerate them. Any change that removes, re-types, or
re-interprets an existing field bumps the version. Readers encountering a higher version
than they know SHOULD still attempt best-effort reading and warn.
