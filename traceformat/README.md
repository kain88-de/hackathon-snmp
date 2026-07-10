# traceformat

[![Traceformat CI](https://github.com/kain88-de/hackathon-snmp/actions/workflows/traceformat-ci.yml/badge.svg)](https://github.com/kain88-de/hackathon-snmp/actions/workflows/traceformat-ci.yml)

The shared package holding the **types of the trace format**. Every
producer and consumer in the suite (oidtrace, oidviz) imports the same models and
vocabulary instead of re-testing dict shapes at each consumer.

## Authority chain

All three files live in this directory:

1. `trace-format.md` — the prose format spec. Wins every disagreement.
2. `trace-format.schema.json` — machine-checkable companion (fix it to match 1).
3. `src/traceformat/models.py` — pydantic v2 models **generated from 2**. Never
   hand-edited.

`trace-format.schema.json` generates client code beyond this package too — it's the
direct codegen input for `oidviz`'s TypeScript types (`json-schema-to-typescript`, see
its `Justfile`) and is loaded independently by `oidtrace/tests/conftest.py`'s
jsonschema-based validation fixture. Being shared across multiple dependents, not a
single consumer, is exactly why this copy is canonical instead of duplicated per
package.

## Codegen pipeline

 `just gen-types` runs `datamodel-code-generator` over the schema.

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
- `dump_record` / `parse_record` — see their docstrings for the exclude_unset/
  exclude_none distinction and the round-trip guarantee; that's load-bearing behavior,
  kept next to the code instead of only here.
- `vocab.py` — producer-side closed `StrEnum`s for the format's open vocabularies
  (`trace-format.md` § 3 names them); its own docstring covers the
  strict-emit/liberal-accept split.
- `py.typed` ships so consumers' strict type checkers resolve everything.

## Growing the vocabulary

Adding a value within format v1: add it to the relevant `vocab.py` enum AND to the
known-values `description` in the schema — the open-enum fields stay `string`; do NOT
add a schema `enum` list, that would break old readers on new traces. Structural
vocabulary changes (closed enums) are format-version territory — see `trace-format.md`
§ 9.
