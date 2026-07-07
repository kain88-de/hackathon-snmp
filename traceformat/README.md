# traceformat

The shared uv-workspace package holding the **types of the trace format**. Every
producer and consumer in the suite (oidtrace, oidviz) imports the same models and
vocabulary instead of re-testing dict shapes at each consumer.

## Authority chain

All three files live in this directory:

1. `trace-format.md` — the prose format spec. Wins every disagreement.
2. `trace-format.schema.json` — machine-checkable companion (fix it to match 1).
3. `src/traceformat/models.py` — pydantic v2 models **generated from 2**. Never
   hand-edited.

`trace-format.schema.json` is also the direct codegen input for `oidviz`'s TypeScript
types (`json-schema-to-typescript`, see its `Justfile`) and is loaded by
`oidtrace/tests/conftest.py` for an independent jsonschema-based validation fixture —
this package's copy is the one canonical file both reach into.

## Codegen pipeline

- `just gen-types` runs `datamodel-code-generator` over the schema (pydantic_v2
  output, standard collections, field constraints, `--use-default-kwarg` — pyright
  needs keyword defaults — `--formatters ruff-format`, `--disable-timestamp` for
  reproducibility).
- `just types-fresh` (in `just ci`) regenerates to a temp file and diffs against the
  committed `models.py` — schema drift fails CI. **The temp file must live inside the
  package tree**: ruff-format resolves line-length from the nearest `pyproject.toml`,
  so a `/tmp` scratch file formats differently and the gate false-alarms.
- `models.py` is excluded from ruff lint and pyright (generated-code exemption);
  everything else in the package is gated strict.
- Schema enums that are **closed** (`snmp.version`, `system_info.point`, `request.pdu`)
  come out as real `Enum` classes; the deliberately **open** vocabularies
  (`violations[]`, `event.kind`, `end_reason` — see `trace-format.md` § 3) come out as
  `str` by design.

## Wire-boundary invariants (`_validators.py`)

`datamodel-code-generator` does not translate JSON Schema's `not`/`if-then-else`
keywords into pydantic validators, so a few structural rules the schema encodes are
invisible to the generated models: `exchange`'s `response`/`malformed` mutual
exclusion, getbulk's required `non_repeaters`/`max_repetitions`, `attempts[].error`
implying `received_at: null`, and non-negative `violation_counts` values.
`parse_record` closes this gap by running `_validators.check_invariants` after
pydantic validation, raising `TraceFormatViolationError` — a hand-written module, kept
separate from the generated `models.py`. `tests/test_schema_parity.py` is the guard
against this class of gap reopening: it asserts `jsonschema` and `parse_record` agree
on the same fixtures, including negatives for each of the four rules above.

## Hand-written surface (`__init__.py`, `vocab.py`)

- `TraceRecord = Header | SystemInfo | Exchange | Event | Summary` — the record union.
- `dump_record(record) -> str` — compact JSON via `model_dump_json(exclude_unset=True)`.
  **exclude_unset, never exclude_none**: optional _keys_ (`label`, `response`,
  `malformed` …) must be absent when unset, while required-but-nullable fields
  (`attempts[].received_at`) must serialize as explicit `null`.
- `parse_record(line) -> TraceRecord` — module-level `TypeAdapter` validation plus the
  invariant checks above; readers get the round-trip guarantee
  (`parse_record(dump_record(r)) == r`).
- `vocab.py` — producer-side closed `StrEnum`s for the format's open vocabularies:
  `Violation`, `EndReason`, `EventKind`, `AttemptError`. Strict in what we emit,
  liberal in what anyone accepts; JSON serialization yields the wire strings.
- `py.typed` ships so consumers' strict type checkers resolve everything.

## Growing the vocabulary

Adding a value within format v1: add it to the relevant `vocab.py` enum AND to the
known-values `description` in the schema — the open-enum fields stay `string`; do NOT
add a schema `enum` list, that would break old readers on new traces. Structural
vocabulary changes (closed enums) are format-version territory — see `trace-format.md`
§ 9.

## Dependencies and consumers

Runtime: pydantic only. Consumers depend via `{workspace = true}`. `oidtrace`'s record
builders construct these models (typed, validated at construction); its tracefile
writes with `dump_record` and reads with `parse_record`. Generated models never leak
below consumers' records/walker boundaries.

## Running

`just fmt` / `lint` / `lint-schema` / `types` / `test` / `cov` / `gen-types` /
`types-fresh` / `ci`. `just cov` requires 100% branch coverage.
