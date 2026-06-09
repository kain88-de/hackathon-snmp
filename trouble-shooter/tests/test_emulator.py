import asyncio
import threading
import time

from emulator import EmulatorConfig, EmulatorServer
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)


async def _snmp_get(
    port: int, oid: str, community: str = "public", timeout: float = 1.0
):
    engine = SnmpEngine()
    try:
        err, status, _, var_binds = await get_cmd(
            engine,
            CommunityData(community),
            await UdpTransportTarget.create(
                ("127.0.0.1", port), timeout=timeout, retries=0
            ),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        return err, var_binds
    finally:
        engine.close_dispatcher()


def test_server_responds_to_snmp_get():
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0"))
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


def test_server_port_is_assigned_when_zero():
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config, port=0)
    server.start()
    try:
        assert server.port > 0
    finally:
        server.stop()


def test_server_uses_community_string():
    config = EmulatorConfig(community="secret", slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        # wrong community — should get no response (timeout error)
        err, _ = asyncio.run(
            _snmp_get(server.port, "1.3.6.1.2.1.1.1.0", community="wrong")
        )
        assert err is not None

        # correct community — should respond
        err, var_binds = asyncio.run(
            _snmp_get(server.port, "1.3.6.1.2.1.1.1.0", community="secret")
        )
        assert err is None
    finally:
        server.stop()


def test_server_slow_prefix_adds_delay():
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.1)
    server = EmulatorServer(config)
    server.start()
    try:
        import time

        t = time.monotonic()
        err, _ = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.2.1.0", timeout=2.0))
        elapsed = time.monotonic() - t
        assert err is None
        assert elapsed >= 0.1
    finally:
        server.stop()


def test_reset_server_still_responds_after_reset():
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        server.reset()
        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0"))
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


def test_reset_drops_in_flight_slow_response():
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.3)
    server = EmulatorServer(config)
    server.start()
    try:
        received: list[object] = []

        def slow_get():
            err, var_binds = asyncio.run(
                _snmp_get(server.port, "1.3.6.1.2.1.2.1.0", timeout=1.0)
            )
            if err is None:
                received.append(var_binds)

        t = threading.Thread(target=slow_get)
        t.start()
        time.sleep(0.05)
        server.reset()
        t.join(timeout=1.5)

        assert received == [], "slow response should have been dropped by reset"

        err, var_binds = asyncio.run(_snmp_get(server.port, "1.3.6.1.2.1.1.1.0"))
        assert err is None
    finally:
        server.stop()
