# traceformat Design

Date: 2026-06-12
Status: approved (extracted from the OIDTrace design; first implementation deleted for the one-shot replay)

`traceformat` is the shared uv-workspace package holding the **types of the trace
format**. Every producer and consumer in the suite (oidtrace today; the doctor and
OIDViz next) imports the same models and vocabulary — validated round-trips instead of
re-tested dict shapes at each consumer.

## Authority chain

1. `docs/trace-format.md` — the prose format spec. Wins every disagreement.
2. `docs/trace-format.schema.json` — machine-checkable companion (fix it to match 1).
3. `traceformat/src/traceformat/models.py` — pydantic v2 models **generated from 2**.
   Never hand-edited.

## Codegen pipeline

- `just gen-types` runs `datamodel-code-generator` over the schema
  (pydantic_v2 output, standard collections, field constraints, `--use-default-kwarg`
  (pyright needs keyword defaults), `--formatters ruff-format`, `--disable-timestamp`
  for reproducibility; `--use-union-operator` is redundant — target 3.13 already emits `X | None`).
- `just types-fresh` (in `just ci`) regenerates to a temp file and diffs against the
  committed models — schema drift fails CI. **The temp file must live inside the
  package tree**: ruff-format resolves line-length from the nearest pyproject, so a
  `/tmp` scratch file formats differently and the gate false-alarms (learned the hard
  way).
- The generated file is excluded from ruff lint and pyright (generated-code exemption);
  everything else in the package is gated strict.
- Schema enums that are **closed** (snmp version, system_info point, pdu) come out as
  real Enum classes; the deliberately **open** vocabularies (violations, event.kind,
  end_reason — see trace-format.md § 3) come out as `str` by design.

## Hand-written surface (`__init__.py`, `vocab.py`)

- `TraceRecord = Header | SystemInfo | Exchange | Event | Summary` — the record union.
- `dump_record(record) -> str` — compact JSON via `model_dump_json(exclude_unset=True)`.
  **exclude_unset, never exclude_none**: optional _keys_ (label, response, malformed …)
  must be absent when unset, while required-but-nullable fields
  (`attempts[].received_at`) must serialize as explicit `null`. Tested.
- `parse_record(line) -> TraceRecord` — module-level `TypeAdapter` validation; readers
  get the round-trip guarantee (`parse_record(dump_record(r)) == r`).
- `vocab.py` — producer-side closed `StrEnum`s for the format's open vocabularies:
  `Violation`, `EndReason`, `EventKind`, `AttemptError`. Strict in what we emit,
  liberal in what anyone accepts; JSON serialization yields the wire strings.
- `py.typed` ships so consumers' strict type checkers resolve everything.

## Growing the vocabulary

Adding a value within format v1: add it to the relevant `vocab.py` enum AND to the
known-values `description` in the schema (§ the open-enum fields stay `string` —
do NOT add schema `enum` lists; that would break old readers on new traces). Structural
vocabulary changes (closed enums) are format-version territory — see trace-format.md § 9.

## Dependencies and consumers

Runtime: pydantic only. Consumers depend via `{workspace = true}`. oidtrace's records
builders construct these models (typed, validated at construction); its tracefile
writes with `dump_record` and reads with `parse_record`. Generated models never leak
below consumers' records/walker boundaries (see the OIDTrace plan's
"Domain types vs format models" rule).

## Testing & gates

- `tests/test_roundtrip.py` — dump/parse equality; `received_at: null` present when
  explicitly None; unset optional keys absent.
- `tests/test_vocab.py` — every enum member's `str()`/JSON form equals its wire string
  (iterates members; new values are covered automatically).
- `just ci` = types-fresh → ruff format/check → pyrefly → pytest. `just cov` (branch):
  100%.
