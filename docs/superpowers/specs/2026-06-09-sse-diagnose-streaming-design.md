# SSE Diagnose Streaming Design

**Date:** 2026-06-09
**Scope:** Replace the blocking `/api/diagnose` request-response with an SSE stream so the UI renders OIDs incrementally as the walk progresses.

---

## Decision

- SSE via `fetch` + `ReadableStream` (not `EventSource`) — POST body keeps credentials out of the URL
- Diagnose only — `/api/check` and `/api/walk` stay as request-response
- Existing `/api/diagnose` endpoint is kept untouched — tests are unaffected
- New endpoint: `POST /api/diagnose/stream`

---

## Event Schema

All events are `data: <json>\n\n` SSE lines.

| Event | Fields | When emitted |
|---|---|---|
| `oids` | `oids: list[OidResult]` | Once per bulk batch; once per pinpoint probe |
| `done` | `complete`, `reason`, `stopped_at`, `summary`, `regions`, `elapsed_total_ms` | After all work is finished |
| `error` | `detail: str` | If an exception escapes the generator |

`oids` carries a list (not one OID per event) so a bulk batch of 10 OIDs is one SSE event. `phase` field on each OID distinguishes `"bulk"` vs `"pinpoint"`. `done` carries the same payload as the current `/api/diagnose` response.

---

## Backend

### `engine.py` — new `diagnose_stream` async generator

Mirrors `diagnose` logic but yields events instead of accumulating:

1. **Bulk walk phase** — for each batch from `prober.bulk_walk`: classify, append to local `oid_results`, yield `{"type": "oids", "oids": [...]}`. Respect `total_timeout` and budget as before.
2. **Pinpoint phase** — if `config.pinpoint`: for each slow/timeout OID call `prober.probe_oid`, yield `{"type": "oids", "oids": [result]}` immediately.
3. **Done** — call `find_slow_regions` on accumulated results, build summary, yield `{"type": "done", ...}`.

Signature:
```python
async def diagnose_stream(
    prober: Prober,
    *,
    buckets: list[Bucket],
    config: DetectorConfig,
) -> AsyncGenerator[dict[str, object], None]:
```

The existing `diagnose` function is untouched.

### `main.py` — new endpoint

```python
@app.post("/api/diagnose/stream")
async def diagnose_device_stream(req: DiagnoseRequest) -> StreamingResponse:
    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for event in diagnose_stream(prober, buckets=buckets, config=config):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

`DiagnoseRequest` model is reused unchanged.

---

## Frontend (`diagnose.html` / `app.js`)

### SSE reader

Replace the single `await fetch + resp.json()` with:

```js
const resp = await fetch('/api/diagnose/stream', { method: 'POST', headers: {...}, body: JSON.stringify(req) });
const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buf = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const lines = buf.split('\n');
  buf = lines.pop();  // keep partial last line
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const event = JSON.parse(line.slice(6));
    if (event.type === 'oids')  appendOidsToWaterfall(event.oids);
    if (event.type === 'done')  renderDone(event);
    if (event.type === 'error') showError(event.detail);
  }
}
```

### Incremental rendering

- **On page load / run start:** render an empty waterfall container and a live counter `<div id="oid-count">`.
- **On each `oids` event:** append rows to the existing waterfall DOM; update counter text ("walked N OIDs…").
- **On `done`:** render summary chips and regions table; update counter to final state; re-enable Run button.
- **On `error`:** show error banner; re-enable Run button.

Existing render functions (`renderDiagChart`, `renderDiagSummary`, `renderDiagRegions`, `renderDiagOids`) are refactored:
- `renderDiagChart` → split into `initWaterfall()` (called once on run) + `appendOidsToWaterfall(oids)` (called per event)
- `renderDiagSummary`, `renderDiagRegions` → called once on `done`, unchanged in logic
- `renderDiagOids` → also called incrementally via `appendOidsToWaterfall` (the OIDs table tab gets the same rows appended as the waterfall)

---

## What is not changing

- `/api/diagnose` endpoint — kept, tests pass through it
- `DiagnoseRequest` model — reused unchanged by the new endpoint
- `diagnose()` function in `engine.py` — untouched
- `/api/check`, `/api/walk` — stay as request-response
- Emulator, prober, classify logic — untouched
