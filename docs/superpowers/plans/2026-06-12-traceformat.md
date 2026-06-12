# traceformat Implementation Plan (contract level)

> **Status: EXECUTED 2026-06-12** — extracted from the OIDTrace plan after the fact so
> the shared package has standalone docs. Spec:
> `docs/superpowers/specs/2026-06-12-traceformat-design.md`. This document records the
> as-built contracts and the open backlog; use it as the reference when extending the
> package.

**Goal:** the shared format-types package: schema-generated pydantic models +
producer vocabulary + serialization helpers, consumed by every suite tool.

## Tasks (all complete)

- [x] **Scaffold**: workspace member `traceformat/` (pydantic>=2 runtime dep only,
      hatchling, py.typed); same strict toolchain as oidtrace (ruff select list,
      pyrefly with workspace-venv interpreter, pyright strict, pytest); Justfile
      `fmt/lint/types/test/ci/cov` + `gen-types`/`types-fresh`.
- [x] **Codegen**: `models.py` generated from `docs/trace-format.schema.json`
      (datamodel-code-generator, `--formatters ruff-format`, `--disable-timestamp`);
      generated file excluded from ruff/pyright; `types-fresh` drift gate in ci with
      the temp file **inside the package tree** (ruff config resolution).
- [x] **Vocab**: `vocab.py` StrEnums — `Violation`, `EndReason`, `EventKind`,
      `AttemptError`; test iterates all members asserting wire-string identity.
- [x] **Union + helpers**: `TraceRecord` union; `dump_record` (compact,
      `exclude_unset` — required-but-nullable `received_at` serializes as `null`,
      unset optional keys absent); `parse_record` via module-level `TypeAdapter`;
      round-trip tests.

## Invariants to preserve when extending

- The schema is generated-from, never generated-to: `docs/trace-format.md` wins, the
  schema follows it, the models follow the schema.
- New open-vocabulary values: vocab enum + schema `description`, never a schema `enum`.
- `exclude_unset` semantics are load-bearing; any new serialization path must keep the
  null-vs-absent distinction and extend `test_roundtrip.py`.
- Coverage stays 100% (branch); `types-fresh` stays in ci.

## Backlog

- Reader-side conveniences for OIDViz/doctor (e.g. a streaming
  `iter_records(path)` that pairs tolerant truncation with `parse_record` — today that
  logic lives in oidtrace.tracefile and may move here when a second consumer needs it).
- Format v2 (packet capture) would regenerate models from a v2 schema — versioned
  module or package split to be designed then.
