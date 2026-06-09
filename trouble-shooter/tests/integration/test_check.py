from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulator import EmulatorServer
    from starlette.testclient import TestClient

_CREDS = {"username": "monitor", "auth_password": "authpass1"}


def test_check_reachable_device(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/check",
        json={"host": "127.0.0.1", "port": emulator_fast.port, **_CREDS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["snmp"]["reachable"] is True
    assert "Emulated" in data["snmp"]["sysDescr"]


def test_check_wrong_credentials(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/check",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "username": "unknown",
            "auth_password": "authpass1",
            "timeout": 0.5,
            "retries": 0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_unreachable_port(client: TestClient) -> None:
    resp = client.post(
        "/api/check",
        json={"host": "127.0.0.1", "port": 19999, "timeout": 0.3, "retries": 0, **_CREDS},
    )
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_invalid_host(client: TestClient) -> None:
    resp = client.post(
        "/api/check",
        json={"host": "not_a_host!!", "port": 1161, **_CREDS},
    )
    assert resp.status_code == 400
