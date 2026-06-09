from emulator import EmulatorServer
from starlette.testclient import TestClient


def test_check_reachable_device(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/check",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "community": "public",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["snmp"]["reachable"] is True
    assert "Emulated" in data["snmp"]["sysDescr"]


def test_check_wrong_community(client: TestClient, emulator_fast: EmulatorServer) -> None:
    resp = client.post(
        "/api/check",
        json={
            "host": "127.0.0.1",
            "port": emulator_fast.port,
            "community": "wrong",
            "timeout": 0.3,
            "retries": 0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_unreachable_port(client: TestClient) -> None:
    resp = client.post(
        "/api/check",
        json={
            "host": "127.0.0.1",
            "port": 19999,
            "community": "public",
            "timeout": 0.3,
            "retries": 0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["snmp"]["reachable"] is False


def test_check_invalid_host(client: TestClient) -> None:
    resp = client.post(
        "/api/check",
        json={
            "host": "not_a_host!!",
            "community": "public",
            "port": 1161,
        },
    )
    assert resp.status_code == 400
