from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulator import EmulatorServer
    from starlette.testclient import TestClient

_CREDS = {"username": "monitor", "auth_password": "authpass1"}
_BUCKETS: list[dict[str, str | int | None]] = [
    {"name": "OK", "max_ms": 500},
    {"name": "SLOW", "max_ms": 3000},
    {"name": "CRITICAL", "max_ms": None},
]


def test_diagnose_endpoint_returns_valid_report(
    client: TestClient, emulator_clean: EmulatorServer
) -> None:
    resp = client.post(
        "/api/diagnose",
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
    data = resp.json()
    assert data["complete"] is True
    assert data["reason"] == "END_OF_MIB"
    assert "summary" in data
    assert "regions" in data
    assert "oids" in data
    assert "elapsed_total_ms" in data
    assert len(data["oids"]) > 0


def test_diagnose_endpoint_invalid_host(client: TestClient) -> None:
    resp = client.post(
        "/api/diagnose",
        json={
            "host": "not_valid!!",
            "port": 1161,
            "buckets": [{"name": "OK", "max_ms": 500}, {"name": "CRIT", "max_ms": None}],
            **_CREDS,
        },
    )
    assert resp.status_code == 400


def test_diagnose_endpoint_region_excludes_oids_field(
    client: TestClient, emulator_clean: EmulatorServer
) -> None:
    resp = client.post(
        "/api/diagnose",
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
    for region in resp.json()["regions"]:
        assert "prefix" in region
        assert "bucket" in region
        assert "batch_ms" in region
        assert "oid_count" in region
        assert "oids" not in region


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
