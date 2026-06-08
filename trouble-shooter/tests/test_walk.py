def test_walk_returns_oids(client, emulator_fast):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1.1",
        "timeout": 2,
        "total_timeout": 10,
    })
    assert resp.status_code == 200
    oids = resp.json()["oids"]
    assert len(oids) > 0
    assert all("oid" in o and "value" in o and "ms" in o for o in oids)


def test_walk_covers_system_and_interface_groups(client, emulator_fast):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1",
        "timeout": 2,
        "total_timeout": 10,
    })
    assert resp.status_code == 200
    oid_strings = {o["oid"] for o in resp.json()["oids"]}
    assert any("1.3.6.1.2.1.1" in oid for oid in oid_strings), "system group missing"
    assert any("1.3.6.1.2.1.2" in oid for oid in oid_strings), "interface group missing"


def test_walk_slow_subtree_takes_longer(client, emulator_slow):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_slow.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1",
        "timeout": 5,
        "total_timeout": 30,
    })
    assert resp.status_code == 200
    oids = resp.json()["oids"]
    slow_oids = [o for o in oids if "1.3.6.1.2.1.2.2" in o["oid"]]
    assert len(slow_oids) > 0
    assert any(o["ms"] >= 40 for o in slow_oids), "expected slow OIDs to take >=40ms"


def test_walk_total_timeout_returns_empty(client, emulator_fast):
    resp = client.post("/api/walk", json={
        "host": "127.0.0.1",
        "port": emulator_fast.port,
        "community": "public",
        "root_oid": "1.3.6.1.2.1",
        "timeout": 1,
        "total_timeout": 0,
    })
    assert resp.status_code == 200
    assert resp.json()["oids"] == []


def test_walk_invalid_host(client):
    resp = client.post("/api/walk", json={
        "host": "not_valid!!",
        "community": "public",
        "port": 1161,
        "root_oid": "1.3.6.1.2.1",
    })
    assert resp.status_code == 400
