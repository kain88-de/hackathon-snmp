# SSE Diagnose Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blocking `/api/diagnose` fetch with a streaming SSE endpoint so the diagnose UI shows OIDs appearing live as the walk progresses.

**Architecture:** A new `diagnose_stream` async generator in `engine.py` yields `oids`/`done`/`error` event dicts as work happens; a new `POST /api/diagnose/stream` endpoint wraps it in a `StreamingResponse`; the diagnose UI switches to a `fetch` + `ReadableStream` reader that updates a live counter and calls the existing `renderWaterfall`/`renderSummary` once `done` arrives.

**Tech Stack:** Python `AsyncGenerator`, FastAPI `StreamingResponse`, browser `fetch` + `ReadableStream` + `TextDecoder`.

---

## File map

| File | Change |
|---|---|
| `trouble-shooter/src/trouble_shooter/detector/engine.py` | Add `diagnose_stream` async generator |
| `trouble-shooter/src/trouble_shooter/detector/__init__.py` | Export `diagnose_stream` |
| `trouble-shooter/src/trouble_shooter/main.py` | Add `import json`, add `POST /api/diagnose/stream` endpoint |
| `trouble-shooter/tests/unit/test_engine.py` | Add 2 unit tests for `diagnose_stream` |
| `trouble-shooter/tests/integration/test_api_diagnose.py` | Add 1 integration test for the stream endpoint |
| `trouble-shooter/static/diagnose.html` | Replace `runDiagnose` body with SSE reader |

---

### Task 1: Add `diagnose_stream` to engine + unit tests

**Files:**
- Modify: `trouble-shooter/src/trouble_shooter/detector/engine.py`
- Modify: `trouble-shooter/src/trouble_shooter/detector/__init__.py`
- Test: `trouble-shooter/tests/unit/test_engine.py`

- [ ] **Step 1: Write failing unit tests**

Add to `trouble-shooter/tests/unit/test_engine.py` (after the existing imports, add `diagnose_stream` to the import line):

```python
from trouble_shooter.detector.engine import diagnose, diagnose_stream
```

Then add these two tests at the bottom of the file:

```python
async def test_diagnose_stream_yields_oids_then_done() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "desc")], elapsed_ms=100, timed_out=False),
            Batch(oids=[("1.3.6.1.2.1.1.2.0", "oid")], elapsed_ms=150, timed_out=False),
        ]
    )
    events = [e async for e in diagnose_stream(prober, buckets=BUCKETS, config=DetectorConfig(pinpoint=False))]

    oids_events = [e for e in events if e["type"] == "oids"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(oids_events) == 2  # one per batch
    assert len(done_events) == 1

    all_oids = [o["oid"] for e in oids_events for o in e["oids"]]
    assert all_oids == ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.2.0"]
    assert all(o["phase"] == "bulk" for e in oids_events for o in e["oids"])

    done = done_events[0]
    assert done["complete"] is True
    assert done["reason"] == "END_OF_MIB"
    assert done["summary"]["OK"] == 2
    assert len(done["regions"]) == 0


async def test_diagnose_stream_timeout_stops_and_reports_done() -> None:
    prober = FakeProber(
        [
            Batch(oids=[("1.3.6.1.2.1.1.1.0", "v")], elapsed_ms=100, timed_out=False),
            Batch(oids=[("1.3.6.1.2.1.2.2.1.1.1", "")], elapsed_ms=5000, timed_out=True),
        ]
    )
    events = [e async for e in diagnose_stream(prober, buckets=BUCKETS, config=DetectorConfig(pinpoint=False))]

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["complete"] is False
    assert done_events[0]["reason"] == "TIMEOUT"
    assert done_events[0]["summary"].get("TIMEOUT", 0) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/unit/test_engine.py::test_diagnose_stream_yields_oids_then_done tests/unit/test_engine.py::test_diagnose_stream_timeout_stops_and_reports_done -v 2>&1 | tail -10
```

Expected: both FAIL with `ImportError: cannot import name 'diagnose_stream'`

- [ ] **Step 3: Add `diagnose_stream` to `engine.py`**

Add to the `TYPE_CHECKING` block at the top of `engine.py`:

```python
if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
```

Then add this function after the existing `diagnose` function:

```python
async def diagnose_stream(
    prober: Prober,
    *,
    buckets: list[Bucket],
    config: DetectorConfig,
) -> AsyncGenerator[dict[str, object], None]:
    validate_buckets(buckets)
    t_start = monotonic()
    batches: list[Batch] = []
    all_oid_results: list[OidResult] = []
    reason = WalkReason.END_OF_MIB
    stopped_at = config.root_oid

    log.info("bulk walk starting at %s (bulk_size=%d)", config.root_oid, config.bulk_size)
    batch_count = 0
    async for batch in prober.bulk_walk(config.root_oid, config.bulk_size):
        batches.append(batch)
        batch_count += 1
        b_name = "TIMEOUT" if batch.timed_out else bucket_for(batch.elapsed_ms, buckets)
        batch_results = [
            OidResult(oid=oid, value=value, bucket=b_name, ms=batch.elapsed_ms, phase="bulk")
            for oid, value in batch.oids
        ]
        all_oid_results.extend(batch_results)
        if batch.oids:
            stopped_at = batch.oids[-1][0]
        log.info(
            "batch #%d: %d OIDs, %.0fms [%s]  last=%s",
            batch_count, len(batch.oids), batch.elapsed_ms, b_name, stopped_at,
        )
        yield {
            "type": "oids",
            "oids": [
                {"oid": o.oid, "value": o.value, "bucket": o.bucket, "ms": o.ms, "phase": o.phase}
                for o in batch_results
            ],
        }
        if batch.timed_out:
            reason = WalkReason.TIMEOUT
            log.warning("batch #%d timed out — stopping walk", batch_count)
            break
        if (monotonic() - t_start) > config.total_timeout:
            reason = WalkReason.BUDGET_EXCEEDED
            log.warning("total_timeout exceeded after %d batches — stopping walk", batch_count)
            break

    log.info("bulk walk done: %d batches, %d OIDs, reason=%s", batch_count, len(all_oid_results), reason.value)
    regions = find_slow_regions(batches, buckets)

    if config.pinpoint:
        log.info("pinpoint phase: %d slow region(s)", len(regions))
        for region in regions:
            log.info("  probing region %s (%d OIDs)", region.prefix, len(region.oids))
            for oid in region.oids:
                sample = await prober.probe_oid(oid)
                b_name = bucket_for(sample.elapsed_ms, buckets) if sample.responded else "TIMEOUT"
                log.info("    %s → %.0fms [%s]", oid, sample.elapsed_ms, b_name)
                result = OidResult(
                    oid=sample.oid, value=sample.value, bucket=b_name,
                    ms=sample.elapsed_ms, phase="pinpoint",
                )
                all_oid_results.append(result)
                yield {
                    "type": "oids",
                    "oids": [{"oid": result.oid, "value": result.value, "bucket": result.bucket, "ms": result.ms, "phase": result.phase}],
                }

    summary: dict[str, int] = {b.name: 0 for b in buckets}
    summary["TIMEOUT"] = 0
    for o in all_oid_results:
        summary[o.bucket] = summary.get(o.bucket, 0) + 1

    yield {
        "type": "done",
        "complete": reason == WalkReason.END_OF_MIB,
        "stopped_at": stopped_at,
        "reason": reason.value,
        "summary": summary,
        "regions": [
            {"prefix": r.prefix, "bucket": r.bucket, "batch_ms": r.batch_ms, "oid_count": r.oid_count}
            for r in regions
        ],
        "elapsed_total_ms": (monotonic() - t_start) * 1000,
    }
```

- [ ] **Step 4: Export from `__init__.py`**

In `trouble-shooter/src/trouble_shooter/detector/__init__.py`, add `diagnose_stream` to the import and `__all__`:

```python
from .engine import diagnose, diagnose_stream
```

And add `"diagnose_stream"` to `__all__`.

- [ ] **Step 5: Run unit tests — all should pass**

```
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/unit/test_engine.py -v 2>&1 | tail -15
```

Expected: all tests PASS (including the two new ones).

- [ ] **Step 6: Commit**

```bash
cd /home/max/work/hackathon
git add trouble-shooter/src/trouble_shooter/detector/engine.py \
        trouble-shooter/src/trouble_shooter/detector/__init__.py \
        trouble-shooter/tests/unit/test_engine.py
git commit -m "feat(engine): add diagnose_stream async generator for SSE"
```

---

### Task 2: Add `/api/diagnose/stream` endpoint

**Files:**
- Modify: `trouble-shooter/src/trouble_shooter/main.py`
- Test: `trouble-shooter/tests/integration/test_api_diagnose.py`

- [ ] **Step 1: Write failing integration test**

Add to `trouble-shooter/tests/integration/test_api_diagnose.py` at the top, add `import json`. Then add this test at the bottom:

```python
import json

def test_diagnose_stream_endpoint_returns_sse_events(
    client: TestClient, emulator_clean: EmulatorServer
) -> None:
    resp = client.post(
        "/api/diagnose/stream",
        json={
            "host": "127.0.0.1",
            "port": emulator_clean.port,
            "root_oid": "1.3.6.1.2.1.1",
            "bulk_size": 10,
            "timeout": 2.0,
            "retries": 1,
            "total_timeout": 30.0,
            "pinpoint": False,
            "buckets": _BUCKETS,
            **_CREDS,
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    lines = [line for line in resp.text.split("\n") if line.startswith("data: ")]
    events = [json.loads(line[6:]) for line in lines]

    oids_events = [e for e in events if e["type"] == "oids"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(oids_events) > 0
    assert len(done_events) == 1
    assert done_events[0]["complete"] is True
    assert done_events[0]["reason"] == "END_OF_MIB"
    all_oids = [o["oid"] for e in oids_events for o in e["oids"]]
    assert len(all_oids) > 0
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/integration/test_api_diagnose.py::test_diagnose_stream_endpoint_returns_sse_events -v 2>&1 | tail -10
```

Expected: FAIL with 404 or `AttributeError`.

- [ ] **Step 3: Update `main.py`**

Add `import json` to the stdlib imports at the top of `main.py` (after `import asyncio`).

Add `diagnose_stream` to the detector import:

```python
from trouble_shooter.detector import SnmpProber, diagnose, diagnose_stream
```

Add `StreamingResponse` to the fastapi imports — it's already in `fastapi.responses`:

```python
from fastapi.responses import FileResponse, StreamingResponse
```

Add `AsyncGenerator` import — add to stdlib imports section:

```python
from collections.abc import AsyncGenerator
```

Add this new endpoint after the existing `diagnose_device` endpoint:

```python
@app.post("/api/diagnose/stream")
async def diagnose_device_stream(req: DiagnoseRequest) -> StreamingResponse:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    prober = SnmpProber(req.host, req.username, req.port, req.auth_password, req.timeout, req.retries)
    buckets = [Bucket(name=b.name, max_ms=b.max_ms) for b in req.buckets]
    config = DetectorConfig(
        root_oid=req.root_oid,
        bulk_size=req.bulk_size,
        timeout=req.timeout,
        retries=req.retries,
        total_timeout=req.total_timeout,
        pinpoint=req.pinpoint,
    )

    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for event in diagnose_stream(prober, buckets=buckets, config=config):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: Run integration test — should pass**

```
cd /home/max/work/hackathon/trouble-shooter && uv run pytest tests/integration/test_api_diagnose.py -v 2>&1 | tail -15
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/max/work/hackathon
git add trouble-shooter/src/trouble_shooter/main.py \
        trouble-shooter/tests/integration/test_api_diagnose.py
git commit -m "feat(api): add POST /api/diagnose/stream SSE endpoint"
```

---

### Task 3: Update diagnose.html UI to use SSE

**Files:**
- Modify: `trouble-shooter/static/diagnose.html`

- [ ] **Step 1: Replace the `runDiagnose` function**

In `trouble-shooter/static/diagnose.html`, find the `runDiagnose` function (starts around line 228) and replace it entirely with:

```js
async function runDiagnose() {
  const btn = document.getElementById('run');
  btn.disabled = true;
  setStatus('Starting…');
  clearResults();

  const req = {
    host:          document.getElementById('host').value.trim(),
    username:      document.getElementById('username').value.trim(),
    auth_password: document.getElementById('auth_password').value,
    port:          parseInt(document.getElementById('port').value, 10),
    bulk_size:     parseInt(document.getElementById('bulk_size').value, 10),
    root_oid:      document.getElementById('root_oid').value.trim(),
    buckets:       getBucketDefs(),
  };

  let resp;
  try {
    resp = await fetch('/api/diagnose/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
  } catch (e) {
    setStatus('Error: ' + e.message, true);
    btn.disabled = false;
    return;
  }

  const allOids = [];
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let event;
        try { event = JSON.parse(line.slice(6)); } catch { continue; }
        if (event.type === 'oids') {
          allOids.push(...event.oids);
          setStatus(`Walking… ${allOids.length} OIDs`);
        } else if (event.type === 'done') {
          setStatus('');
          renderSummary({ ...event, oids: allOids });
          renderWaterfall(allOids);
        } else if (event.type === 'error') {
          setStatus('Error: ' + event.detail, true);
        }
      }
    }
  } catch (e) {
    setStatus('Stream error: ' + e.message, true);
  } finally {
    btn.disabled = false;
  }
}
```

- [ ] **Step 2: Manual smoke test**

Start the app:
```
cd /home/max/work/hackathon/trouble-shooter && uv run python -m trouble_shooter.main
```

Open `http://localhost:8080/diagnose` in a browser. Fill in host/credentials/port and click Run. Verify:
- Status line updates live: "Walking… 10 OIDs", "Walking… 20 OIDs", etc.
- When done, the waterfall appears with grouped buckets
- Summary bar appears with OID count, elapsed time, reason

- [ ] **Step 3: Commit**

```bash
cd /home/max/work/hackathon
git add trouble-shooter/static/diagnose.html
git commit -m "feat(ui): stream diagnose results via SSE — live OID counter"
```

---

### Task 4: Full CI

- [ ] **Step 1: Run trouble-shooter CI**

```
cd /home/max/work/hackathon/trouble-shooter && just ci 2>&1 | tail -20
```

Expected: format → lint → type-check → tests all pass.

- [ ] **Step 2: Run emulator CI (sanity check — nothing changed there)**

```
cd /home/max/work/hackathon/emulator && just ci 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 3: Fix any lint/type issues**

Common issues:
- Ruff may flag `AsyncGenerator` as unused if the return type annotation is inferred — if so, move it under `TYPE_CHECKING`
- Pyrefly may warn about the `diagnose_stream` return type annotation on an async generator function — if so, add `# type: ignore` on that line

- [ ] **Step 4: Commit any fixes**

```bash
git add -p
git commit -m "fix: lint and type issues from SSE streaming"
```
