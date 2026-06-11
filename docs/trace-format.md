# OIDTrace File Format Specification

Version: 1 (`format_version: 1`)
Status: draft

This document is the authoritative specification of the OIDTrace file format. The
architecture rationale lives in
`superpowers/specs/2026-06-11-oidtrace-architecture-design.md`; where the two disagree,
this document wins.

## 1. Overview

An OIDTrace file records one SNMP walk (one settings combination) against one device as a
sequence of self-describing JSON records. Design goals, in priority order:

1. **Transparency** — an admin can inspect the file with `zcat`/`jq`/a text editor and
   verify what is being shared before uploading it.
2. **No values** — SNMP values are never stored, with two narrow, visible exceptions
   (§ 7).
3. **Evidence-grade detail** — raw (scrubbed) wire bytes and per-attempt timing survive,
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
- **Raw bytes**: lowercase hex strings without separators, e.g. `"30819f02010104..."`.
- **Unknown fields**: readers MUST ignore fields they do not know. Adding optional fields
  is a non-breaking change; removing or re-typing a field requires bumping
  `format_version`.
- **Open enums**: `violations[]`, `event.kind`, and `end_reason` may grow values within a
  format version; readers MUST tolerate unknown values.

## 4. Record types

Every record has a `type` field: one of `header`, `system_info`, `exchange`, `event`,
`summary`.

### 4.1 `header`

First record of every file.

| Field            | Type   | Req. | Meaning                                            |
|------------------|--------|------|----------------------------------------------------|
| `type`           | string | yes  | `"header"`                                         |
| `format_version` | int    | yes  | This document: `1`                                 |
| `tool`           | string | yes  | Producer and version, e.g. `"oidtrace 0.1.0"`      |
| `started_at`     | string | yes  | ISO 8601 UTC wall-clock walk start                 |
| `label`          | string | no   | Admin-chosen run label; the only correlation handle |
| `snmp.version`   | string | yes  | `"1"` or `"2c"` (v3 fields reserved for later)     |
| `settings`       | object | yes  | See below                                          |

`settings` fields: `bulk_size` (int; `0` means GetNext walk), `timeout_s` (number),
`retries` (int), `start_oid` (string), `time_budget_s` (number, optional).

The header deliberately contains **no target host name, IP, or port** (§ 7).

```json
{"type":"header","format_version":1,"tool":"oidtrace 0.1.0",
 "started_at":"2026-06-11T14:03:07Z","label":"switch-floor3",
 "snmp":{"version":"2c"},
 "settings":{"bulk_size":10,"timeout_s":2.0,"retries":2,"start_oid":"1.3.6.1"}}
```

### 4.2 `system_info`

Admin-approved values for the system-OID allowlist, captured by a dedicated Get at walk
start and again at walk end. Absent entirely when the admin hides system info.

| Field    | Type   | Req. | Meaning                                   |
|----------|--------|------|-------------------------------------------|
| `type`   | string | yes  | `"system_info"`                           |
| `at`     | number | yes  | Seconds since walk start                  |
| `point`  | string | yes  | `"start"` or `"end"`                      |
| `values` | object | yes  | OID → value; only allowlisted OIDs appear |

Allowlist in format version 1: sysDescr.0 (`1.3.6.1.2.1.1.1.0`, string), sysObjectID.0
(`1.3.6.1.2.1.1.2.0`, OID string), sysUpTime.0 (`1.3.6.1.2.1.1.3.0`, integer ticks).
A sysUpTime at `end` lower than at `start` proves a mid-walk device reboot.

```json
{"type":"system_info","at":0.0412,"point":"start",
 "values":{"1.3.6.1.2.1.1.1.0":"Cisco IOS 15.2","1.3.6.1.2.1.1.2.0":"1.3.6.1.4.1.9.1.516",
           "1.3.6.1.2.1.1.3.0":492711442}}
```

### 4.3 `exchange`

One record per logical request. `seq` starts at 1 and increments per logical request
(retries do not increment it).

| Field             | Type   | Req. | Meaning                                              |
|-------------------|--------|------|------------------------------------------------------|
| `type`            | string | yes  | `"exchange"`                                         |
| `seq`             | int    | yes  | 1-based logical request counter                      |
| `request`         | object | yes  | What we sent (§ below)                               |
| `attempts`        | array  | yes  | One entry per datagram sent, including retries       |
| `response`        | object | no*  | The decoded response attributed to this exchange     |
| `stray_responses` | array  | no   | Datagrams not attributable as *the* response         |
| `violations`      | array  | no   | Protocol violations observed (strings, open enum)    |
| `malformed`       | object | no*  | Present when the attributed datagram failed to decode |

\* Exactly one of: `response` present (decoded), `malformed` present (undecodable), or
both absent (no answer at all — every attempt timed out).

`request`: `pdu` (`"get"` | `"getnext"` | `"getbulk"`), `request_id` (int, as sent),
`oids` (array of OID strings), `non_repeaters` + `max_repetitions` (int, getbulk only),
`raw` (hex, scrubbed).

`attempts[]`: `sent_at` (number), `received_at` (number | null — null means this attempt
got no datagram). The response is attributed to the attempt whose `received_at` is set.

`response`: `request_id` (int, **as returned by the device** — compare with
`request.request_id`), `error_status` (int), `error_index` (int), `varbinds` (array),
`raw` (hex, scrubbed).

`varbinds[]`: `oid` (string), `vtype` (string, § 5), `vlen` (int — byte length of the BER
value octets of this varbind; value bytes themselves are zeroed in `raw` and never stored).

`stray_responses[]`: `received_at` (number), `raw` (hex, scrubbed). Duplicates, late
replies to earlier requests, unsolicited datagrams.

`malformed`: `raw` (hex, verbatim — see § 7), `error` (string), `salvaged` (object,
optional — whatever fields could be partially decoded).

`violations[]` initial vocabulary: `"request-id-mismatch"`, `"oid-not-increasing"`,
`"missing-end-of-mib"`, `"duplicate-response"`, `"malformed-ber"`.

```json
{"type":"exchange","seq":42,
 "request":{"pdu":"getbulk","request_id":1042,"oids":["1.3.6.1.2.1.2.2.1.3"],
            "non_repeaters":0,"max_repetitions":10,"raw":"3081..."},
 "attempts":[{"sent_at":12.004317,"received_at":null},
             {"sent_at":14.004901,"received_at":14.182230}],
 "response":{"request_id":1,"error_status":0,"error_index":0,
             "varbinds":[{"oid":"1.3.6.1.2.1.2.2.1.3.1","vtype":"Integer","vlen":1}],
             "raw":"3082..."},
 "stray_responses":[{"received_at":14.190112,"raw":"3082..."}],
 "violations":["request-id-mismatch","duplicate-response"]}
```

### 4.4 `event`

Walk-level observations not tied to one exchange.

| Field    | Type   | Req. | Meaning                          |
|----------|--------|------|-----------------------------------|
| `type`   | string | yes  | `"event"`                         |
| `at`     | number | yes  | Seconds since walk start          |
| `kind`   | string | yes  | Open enum, see below              |
| `detail` | object | no   | Kind-specific payload             |

Initial kinds: `"oid-loop-detected"` (detail: `{oid}`), `"walk-aborted-by-user"`,
`"time-budget-exceeded"`.

### 4.5 `summary`

Last record, best-effort (may be missing in truncated files).

| Field             | Type   | Req. | Meaning                                       |
|-------------------|--------|------|-----------------------------------------------|
| `type`            | string | yes  | `"summary"`                                   |
| `at`              | number | yes  | Seconds since walk start (= walk duration)    |
| `exchanges`       | int    | yes  | Logical requests issued                       |
| `oids_seen`       | int    | yes  | Distinct OIDs returned                        |
| `end_reason`      | string | yes  | `"completed"`, `"unresponsive"`, `"interrupted"`, `"time-budget-exceeded"`, `"oid-loop"` |
| `violation_counts`| object | yes  | violation string → count                      |

## 5. `vtype` vocabulary

BER universal and SNMP application types: `"Integer"`, `"OctetString"`, `"Null"`,
`"ObjectIdentifier"`, `"IpAddress"`, `"Counter32"`, `"Gauge32"`, `"TimeTicks"`,
`"Opaque"`, `"Counter64"`, and the v2c exceptions `"NoSuchObject"`, `"NoSuchInstance"`,
`"EndOfMibView"`. Unknown BER tags are recorded as `"tag:0xNN"`.

## 6. Scrubbing (what `raw` contains)

`raw` fields hold the BER packet re-encoded with **value octets and the community string
replaced by zero bytes of the same length**. Structure, tags, lengths, OIDs, request-ids,
and total packet size are preserved exactly. Consequence: packet sizes in the trace match
the wire, which downstream consumers (OIDEmu profile fitting) rely on.

The sole unscrubbed bytes in a trace are `malformed.raw`: packets we could not parse
cannot be scrubbed. They are kept verbatim because undecodability is itself the evidence;
`oidtrace show` highlights them, and `--drop-unparsed` removes them at capture time.

## 7. Privacy guarantees

A format-version-1 trace never contains:

- the target host name, IP address, or port;
- the SNMP community string (zeroed in every `raw`, absent from parsed records);
- SNMP values — except (a) the admin-approved `system_info` allowlist shown to the admin
  at capture time, and (b) verbatim `malformed.raw` packets unless `--drop-unparsed`.

It does contain: OID names and tree structure (reveals device vendor/MIBs and table
cardinalities), value types and lengths, timing, and the optional admin-chosen `label`.

## 8. JSON Schema

A machine-checkable companion schema lives at **`docs/trace-format.schema.json`** (JSON
Schema draft 2020-12): one `oneOf` branch per record type, validating any single line of a
trace. It encodes the structural rules of this document — including the
`response`/`malformed` mutual exclusion and the getbulk-requires-repetition-fields rule —
while leaving open enums and unknown extra fields unconstrained, as § 3 requires. The test
suite validates every line the trace writer emits against it. If this document and the
schema disagree, this document wins; fix the schema.

## 9. Versioning

`format_version` is a single integer. Within a version: new optional fields and new enum
values may appear; readers ignore/tolerate them. Any change that removes, re-types, or
re-interprets an existing field bumps the version. Readers encountering a higher version
than they know SHOULD still attempt best-effort reading and warn.
