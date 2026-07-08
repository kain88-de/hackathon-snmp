# OIDViz Streaming Parser Design

Date: 2026-07-08
Status: approved

Addresses `findings.md` #5 ("OIDViz parser has avoidable memory amplification
on large traces"), core fix only — no size-limit guard, no new large-fixture
test (see Scope below).

## Problem

`parser.worker.ts` decompresses a trace in three full-size passes before any
record is parsed: `readAllChunks` collects every gzip-decompressed chunk into
an array, `decompressGzip` merges them into one `Uint8Array` and decodes the
whole thing into one string, then `parseTrace` does `text.split("\n")` and
`.filter(...)`, producing two more full-size arrays. At peak, 4-5 full-size
copies of the decompressed trace are alive at once before a single JSON
record is parsed.

## Design

Replace `readAllChunks` + `decompressGzip` + the split/filter loop with one
streaming `parseTrace`:

- Read from the `DecompressionStream`'s reader chunk-by-chunk (same
  `reader.read()` recursive-pump shape already used in the file).
- Decode each chunk incrementally with `TextDecoder({stream: true})`,
  carrying only a small "leftover partial line" string across iterations —
  never the full text.
- Split each decoded chunk on `\n`; everything but the last piece is a
  complete line, dispatched immediately into `header` / `systemInfo` /
  `exchanges` / `summary` via the existing per-record-type switch. The last
  piece becomes the new leftover.
- On stream end, flush the decoder (`decoder.decode()` with no args) and
  process the final leftover as the last line, if non-empty.

Peak memory drops from ~4-5x the decompressed trace size to ~1x plus the
output structures (`exchanges` array, etc.), which are unavoidable — that's
the actual output.

The existing "write to the writable side while concurrently reading the
readable side" concurrency (required to avoid deadlock on backpressure) is
preserved unchanged.

## Truncation handling

Today, an unparseable line sets `truncated = true` and `break`s out of the
line loop, but the full decompressed text was already fully materialized
before that loop ran. In the streaming version there is no such loop to
break out of early — so line-handling returns `false` on parse failure, and
the pump responds by calling `reader.cancel()` and stopping immediately: no
further chunks are read or decoded.

This matches oidtrace's append-only write guarantee: once a bad line is
written, nothing valid follows it, so there is no reason to keep draining
the stream.

The writer-side promise (`writer.write(...).then(() => writer.close())`) is
caught and ignored specifically when the cancellation was self-inflicted
(tracked via a `stopped` flag), so a genuine decompression error (e.g. the
`not-gzip` fixture, which isn't valid gzip data at all) still propagates and
rejects `parseTrace` as before.

## Behavior preserved

No observable change for existing e2e fixtures:

- `canonical`, `no-summary`, `unknown-record-type`: no truncation path hit,
  unaffected.
- `truncated`: still resolves with `{header, exchanges: [exchange 1],
  truncated: true}` — the cut-off second exchange line is dropped exactly as
  before.
- `not-gzip`: still rejects with a decompression error, propagated through
  the worker's existing `catch` → error-response path.

## Scope

This is the "streaming decode and incremental line processing" follow-up
from finding #5 only. The other two follow-ups listed there —
large-fixture parse tests with time/memory budgets, and a graceful failure
above some size limit — are explicitly out of scope for this change:

- No principled size threshold exists yet in the repo. Picking one now would
  be a guess, not a finding-driven fix. Defining one needs real memory
  profiling across trace sizes in an actual browser, which hasn't been done.
- The existing e2e fixtures already exercise the parser's truncation and
  error paths; they serve as the regression check for this refactor, so no
  new fixture is added here.

## Files touched

- `oidviz/src/lib/parser.worker.ts` only.
