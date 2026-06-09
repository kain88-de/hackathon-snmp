# Deploying & Testing the Slow-OID Detection Engine

This guide shows how to stand up SNMP emulators that exhibit different "buggy"
behaviors, point the trouble-shooter's `/api/diagnose` engine at them, and read
back the list of slow / dropped OIDs.

---

## 1. How the pieces fit together

```
   ┌─────────────────────────┐         SNMP (UDP/1161)         ┌──────────────────────┐
   │  trouble-shooter         │  ───────────────────────────▶  │  emulator pod #1     │
   │  FastAPI on host :8080   │   GETBULK walk + per-OID GET   │  127.0.0.2  "slow"   │
   │  POST /api/diagnose      │  ◀───────────────────────────  │                      │
   │                          │                                └──────────────────────┘
   │   detector/              │         SNMP (UDP/1161)         ┌──────────────────────┐
   │     engine.diagnose()    │  ───────────────────────────▶  │  emulator pod #2     │
   │     prober (pysnmp)      │  ◀───────────────────────────  │  127.0.0.3  "buggy"  │
   └─────────────────────────┘                                 └──────────────────────┘
```

- **Emulators** are SNMP devices implemented by `emulator/snmp_emulator.py`. Each
  is configured entirely through environment variables (no code changes needed to
  change behavior). They run either directly on the host or as Podman pods.
- **trouble-shooter** is the FastAPI service. It is **not** containerized — you run
  it on the host. `/api/diagnose` does a two-phase scan and returns a report.
- The web UI (`/`) only wires up `/api/check` and `/api/walk`; **`/api/diagnose`
  is API-only**, so we drive it with `curl` + `jq`.

---

## 2. How the emulator generates "buggy" behavior  (read this first)

There is exactly one knob, and understanding it makes the whole guide obvious.

Any OID whose dotted string **starts with** one of `SLOW_PREFIXES` is "slow": when
the device is asked for it, it **waits `SLOW_DELAY` seconds before replying**.

What the prober sees depends on how that delay compares to the prober `timeout`:

| `SLOW_DELAY` vs prober `timeout`        | Result on the wire                | Bucket in the report   |
|-----------------------------------------|-----------------------------------|------------------------|
| delay **<** timeout (e.g. 0.8s vs 3s)   | reply arrives, just late          | `SLOW` / `CRITICAL` (by ms) |
| delay **>** timeout (e.g. 10s vs 2s)    | request times out → no reply      | `TIMEOUT`, walk stops  |
| not under a slow prefix                 | immediate reply                   | `OK`                   |

So:

- **"slow but answering" device** → low delay (e.g. `0.8`), prober `timeout` above it.
  You get full per-OID timings (the engine's *pinpoint* phase re-probes every OID
  in the slow subtree).
- **"buggy / dropped" device** → high delay (e.g. `10`), prober `timeout` below it.
  The walk stops at the first unanswered batch: `reason: "TIMEOUT"`,
  `complete: false`, and `stopped_at` points at the boundary OID of the broken
  subtree. (The device never answers below that point, so the engine reports the
  *entry point* of the buggy region — it cannot enumerate OIDs the device refuses
  to return.)

### Emulator environment variables

Read in `emulator/snmp_emulator.py`:

| Variable         | Default                 | Meaning                                              |
|------------------|-------------------------|------------------------------------------------------|
| `SLOW_PREFIXES`  | `1.3.6.1.2.1.2.2.1`     | OID prefix that is slow. **One prefix only** via env. |
| `SLOW_DELAY`     | `3.0`                   | Seconds to stall a matching request.                 |
| `N_INTERFACES`   | `4`                     | Size of the simulated `ifTable` (more = bigger MIB). |
| `SNMP_COMMUNITY` | `public`                | Community string. A mismatch → device stays silent.  |
| `SNMP_HOST`      | `0.0.0.0` (container)   | Bind address.                                        |
| `SNMP_PORT`      | `1161`                  | UDP port.                                            |

`1.3.6.1.2.1.2.2.1` is the interfaces table (`ifTable`) — a realistic place for a
device to be slow. The system group (`1.3.6.1.2.1.1`) is always fast.

---

## 3. Prerequisites

- `uv` (Python toolchain — repo pins Python 3.14.2)
- `just`
- For the container path: `podman`, and `sudo` once to add loopback aliases
- Optional but handy: `snmp` CLI tools (`snmpget`, `snmpbulkwalk`) and `jq`

> **Heads-up (fixed bug):** `emulator/snmp_emulator.py` previously had a
> Python-2-style `except KeyboardInterrupt, SystemExit:` that made the script fail
> to start under Python 3 — i.e. the container `CMD` crashed immediately. That line
> has been corrected to `except (KeyboardInterrupt, SystemExit):`. If you have an
> **old image cached, rebuild it** (Option B below), or the pods will crash-loop.

---

## 4. Option A — Quick local test (no containers)

Fastest way to see the feature work. Run two emulators on `127.0.0.1` with
different ports and different behaviors.

**Terminal 1 — "slow but answering" device on :1161**

```bash
cd emulator
uv sync
SNMP_HOST=127.0.0.1 SNMP_PORT=1161 \
  SLOW_PREFIXES=1.3.6.1.2.1.2.2.1 SLOW_DELAY=0.8 N_INTERFACES=8 \
  uv run python snmp_emulator.py
```

**Terminal 2 — "buggy / dropped" device on :1162**

```bash
cd emulator
SNMP_HOST=127.0.0.1 SNMP_PORT=1162 \
  SLOW_PREFIXES=1.3.6.1.2.1.2.2.1 SLOW_DELAY=10 N_INTERFACES=8 \
  uv run python snmp_emulator.py
```

Each prints its config and then logs every request as `[FAST]` / `[SLOW]` (and
`→ dropped` when a slow request is abandoned). Leave them running.

**Terminal 3 — the trouble-shooter service**

```bash
cd trouble-shooter
uv sync
just run            # uvicorn on http://0.0.0.0:8080  (frees the port first)
```

Now jump to **Section 6** to run diagnoses (use `port: 1161` and `port: 1162`).

---

## 5. Option B — Container deployment (Podman pods)

Mirrors a more realistic "two devices on the network" setup: two pods on separate
loopback IPs, both on UDP 1161.

### 5.1 Give each device a distinct behavior

`emulator/pods.yaml` ships with two identical devices (only `SNMP_COMMUNITY` set, so
both use the defaults). Edit it so each device behaves differently — add `SLOW_DELAY`
/ `N_INTERFACES` (and optionally `SLOW_PREFIXES`) to each container's `env:` list.

Device #1 → slow but answering:

```yaml
      env:
        - name: SNMP_COMMUNITY
          value: public
        - name: SLOW_PREFIXES
          value: "1.3.6.1.2.1.2.2.1"
        - name: SLOW_DELAY
          value: "0.8"
        - name: N_INTERFACES
          value: "8"
```

Device #2 → buggy / dropped:

```yaml
      env:
        - name: SNMP_COMMUNITY
          value: public
        - name: SLOW_PREFIXES
          value: "1.3.6.1.2.1.2.2.1"
        - name: SLOW_DELAY
          value: "10"
        - name: N_INTERFACES
          value: "8"
```

> Env-var changes live in the **pod spec**, not the image — applying them only needs
> a pod restart (`--down` then re-apply), **no rebuild**. You only rebuild the image
> when you change emulator **Python source**.

### 5.2 Build, network, start

From the `emulator/` directory:

```bash
cd emulator
just containers-start
```

That target does three things: builds the image (`podman build -t snmp-emulator
-f emulator/Containerfile ..`), adds the loopback aliases `127.0.0.2` and
`127.0.0.3` (`sudo ip addr add …/8 dev lo`, idempotent), then `podman play kube
pods.yaml` (tearing down any previous run first).

Individual targets if you prefer: `just build`, `just setup-net`, `just containers-stop`,
`just containers-logs`.

> Loopback aliases do **not** survive a reboot. Re-run `just setup-net` (or
> `just containers-start`) after rebooting.

### 5.3 Confirm the pods are up

```bash
podman ps
podman logs snmp-device-1-emulator | head     # should show the "SNMP emulator …" banner
```

Then run the trouble-shooter on the host:

```bash
cd ../trouble-shooter
uv sync
just run
```

For containers the device addresses are `127.0.0.2:1161` and `127.0.0.3:1161`.

---

## 6. Run a diagnosis & retrieve buggy OIDs

The endpoint is `POST /api/diagnose`. Request fields (all optional except `host`):

| field           | default            | notes                                                        |
|-----------------|--------------------|--------------------------------------------------------------|
| `host`          | —                  | device IP/hostname (validated; bad host → HTTP 400)          |
| `community`     | `public`           |                                                              |
| `port`          | `1161`             |                                                              |
| `root_oid`      | `1.3.6.1.2.1`      | where the walk starts (lexicographic walk from here)         |
| `bulk_size`     | `10`               | GETBULK max-repetitions per round-trip                       |
| `timeout`       | `5.0`              | per-request seconds — **the lever vs `SLOW_DELAY`**          |
| `retries`       | `2`                | set `0` for fast failure on the buggy device                 |
| `total_timeout` | `60.0`             | budget (s) for the **bulk walk (Phase 1) only** → `reason: "BUDGET_EXCEEDED"`. Does **not** bound pinpoint — see note below. |
| `pinpoint`      | `true`             | Phase 2: re-probe each OID in slow regions individually      |
| `buckets`       | OK<500, SLOW<3000, CRITICAL | severity tiers in **ms**; exactly one catch-all (`max_ms: null`), last |

### 6.1 Slow-but-answering device — full per-OID timings

`timeout: 3` is above the device's `0.8s` delay, so everything answers (just slowly).
`pinpoint: true` re-probes each OID in the slow subtree to attribute the latency.

> **⚠️ Pinpoint cost (measured):** Phase 2 re-probes **every OID in a slow region
> one-by-one**, and each probe pays the full `SLOW_DELAY`. With `N_INTERFACES=8`
> the `ifTable` is ~176 OIDs, so a `0.8s`-delay device takes **~175s** to pinpoint —
> and `total_timeout` does **not** stop it (it only bounds the Phase-1 walk). For a
> large slow subtree, either set `"pinpoint": false` (you still get the slow
> *regions* and bulk timings, just not per-OID), narrow `root_oid` to the subtree
> you care about, or use a smaller `N_INTERFACES` on the emulator.

```bash
curl -s localhost:8080/api/diagnose \
  -H 'content-type: application/json' \
  -d '{
    "host": "127.0.0.1", "port": 1161, "community": "public",
    "root_oid": "1.3.6.1.2.1", "bulk_size": 10,
    "timeout": 3.0, "retries": 0, "total_timeout": 30,
    "pinpoint": true
  }' | jq
```

Healthy-walk shape (the slow subtree shows up as a region and as non-OK OIDs):

```jsonc
{
  "complete": true,
  "stopped_at": "1.3.6.1.2.1.…",
  "reason": "END_OF_MIB",
  "summary": { "OK": 21, "SLOW": 40, "CRITICAL": 0, "TIMEOUT": 0 },
  "regions": [
    { "prefix": "1.3.6.1.2.1.2.2.1", "bucket": "SLOW", "batch_ms": 812.4, "oid_count": 40 }
  ],
  "oids": [
    { "oid": "1.3.6.1.2.1.1.1.0", "value": "Emulated …", "bucket": "OK",   "ms": 1.9,   "phase": "bulk" },
    { "oid": "1.3.6.1.2.1.2.2.1.2.1", "value": "eth0",   "bucket": "SLOW", "ms": 803.1, "phase": "pinpoint" }
  ],
  "elapsed_total_ms": 1840.5
}
```

### 6.2 Buggy / dropped device — find the broken subtree

`timeout: 2` is below the device's `10s` delay, so the slow subtree never answers.
The walk halts at the first dead batch.

```bash
curl -s localhost:8080/api/diagnose \
  -H 'content-type: application/json' \
  -d '{
    "host": "127.0.0.1", "port": 1162, "community": "public",
    "root_oid": "1.3.6.1.2.1", "bulk_size": 10,
    "timeout": 2.0, "retries": 0, "total_timeout": 30,
    "pinpoint": true
  }' | jq
```

```jsonc
{
  "complete": false,
  "reason": "TIMEOUT",
  "stopped_at": "1.3.6.1.2.1.2.2.1.1.1",     // entry point of the broken subtree
  "summary": { "OK": 9, "SLOW": 0, "CRITICAL": 0, "TIMEOUT": 2 },
  "regions": [ { "prefix": "1.3.6.1.2.1.2.2.1.1.1", "bucket": "TIMEOUT", "batch_ms": 2003.7, "oid_count": 1 } ],
  "oids": [ { "oid": "1.3.6.1.2.1.2.2.1.1.1", "value": "", "bucket": "TIMEOUT", "ms": 2003.7, "phase": "bulk" } ],
  "elapsed_total_ms": 4012.0
}
```

`reason: "TIMEOUT"` + `complete: false` is the signal that a subtree is broken;
`stopped_at` is where it starts.

### 6.3 Extracting just the OIDs you care about with `jq`

```bash
# Save a report
curl -s localhost:8080/api/diagnose -H 'content-type: application/json' \
  -d '{"host":"127.0.0.1","port":1161,"timeout":3.0,"retries":0,"pinpoint":true}' > report.json

# One-line verdict
jq '{complete, reason, stopped_at, summary}' report.json

# The slow regions (subtrees), worst bucket + count each
jq '.regions' report.json

# Every dropped/timed-out OID
jq -r '.oids[] | select(.bucket=="TIMEOUT") | .oid' report.json

# Every slow-or-worse OID with its measured latency (pinpoint = per-OID truth)
jq -r '.oids[] | select(.phase=="pinpoint" and .bucket!="OK")
        | "\(.bucket)\t\(.ms)ms\t\(.oid)"' report.json
```

### 6.4 Custom severity buckets

Thresholds are in **milliseconds**, must be strictly ascending, and the last
bucket must be the catch-all (`"max_ms": null`):

```bash
curl -s localhost:8080/api/diagnose -H 'content-type: application/json' -d '{
  "host":"127.0.0.1","port":1161,"timeout":3.0,"retries":0,"pinpoint":true,
  "buckets":[
    {"name":"FAST","max_ms":200},
    {"name":"WARN","max_ms":1000},
    {"name":"BAD","max_ms":5000},
    {"name":"DEAD","max_ms":null}
  ]
}' | jq '.summary'
```

---

## 7. Teardown

```bash
# Option A: Ctrl-C each terminal (emulators + trouble-shooter)

# Option B: stop the pods
cd emulator
just containers-stop          # podman play kube pods.yaml --down
# loopback aliases are cosmetic; they vanish on reboot, or remove manually:
#   sudo ip addr del 127.0.0.2/8 dev lo
#   sudo ip addr del 127.0.0.3/8 dev lo
```

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Pod crash-loops immediately | Stale image from before the `snmp_emulator.py` syntax fix. `just build` then restart. Source edits to the emulator **require a rebuild + pod recreate** — env-var edits don't. |
| `/api/diagnose` returns everything `OK`, no regions | The device isn't actually slow for that `root_oid`, or `timeout` ≥ `SLOW_DELAY` and the subtree is small. Lower `timeout` or raise `SLOW_DELAY`; confirm `SLOW_PREFIXES` sits under `root_oid`. |
| Always `reason: "TIMEOUT"`, `complete: false` even on the "good" device | Prober `timeout` is below `SLOW_DELAY`. Raise `timeout` above the delay to let it answer. |
| `reason: "BUDGET_EXCEEDED"` | The **bulk walk** exceeded `total_timeout` (big MIB × per-request latency). Raise `total_timeout`, lower `retries`, or shrink `N_INTERFACES`. (Note: this budget governs Phase 1 only.) |
| Diagnose call "hangs" for minutes, then returns `END_OF_MIB` | Phase-2 pinpoint over a large slow subtree — it's unbounded by `total_timeout`. Set `"pinpoint": false` or narrow `root_oid`. See §6.1. |
| HTTP 400 `Invalid host` | `host` failed validation (e.g. contains `_`/`!`). Use a plain IP or DNS name. |
| Device silent / `reachable:false` from `/api/check` | Community mismatch (must equal the emulator's `SNMP_COMMUNITY`), wrong port, or — for containers — loopback alias missing (`just setup-net`). |
| `address already in use` on emulator start | Another process holds that UDP port. Pick a different `SNMP_PORT`, or for :8080 `just run` already frees it via `fuser`. |

---

## 9. Reference

- Emulator entrypoint / env vars: `emulator/snmp_emulator.py`
- Emulator behavior model: `emulator/emulator/_core.py` (`_is_slow`, the `SLOW_DELAY` wait)
- Pod manifest: `emulator/pods.yaml`; container build: `emulator/Containerfile`; tasks: `emulator/Justfile`
- Detection engine: `trouble-shooter/src/trouble_shooter/detector/` (`engine.py`, `prober.py`, `classify.py`, `models.py`)
- Endpoint + request/response schema: `trouble-shooter/src/trouble_shooter/main.py` (`/api/diagnose`, `DiagnoseRequest`, `BucketSpec`)
