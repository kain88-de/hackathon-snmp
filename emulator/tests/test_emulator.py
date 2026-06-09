import asyncio
import threading
import time
from typing import TYPE_CHECKING

from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    usmHMACMD5AuthProtocol,
)

from emulator import EmulatorConfig, EmulatorServer

if TYPE_CHECKING:
    from pysnmp.proto import errind


async def _snmp_get(
    engine: SnmpEngine,
    port: int,
    oid: str,
    username: str = "monitor",
    auth_password: str = "authpass1",  # noqa: S107
    timeout: float = 0.5,
) -> tuple[errind.ErrorIndication | None, tuple[ObjectType, ...]]:
    err, _status, _, var_binds = await get_cmd(
        engine,
        UsmUserData(username, authKey=auth_password, authProtocol=usmHMACMD5AuthProtocol),
        await UdpTransportTarget.create(("127.0.0.1", port), timeout=timeout, retries=0),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    return err, var_binds


async def test_server_responds_to_snmp_get(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        err, var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


def test_server_port_is_assigned_when_zero() -> None:
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config, port=0)
    server.start()
    try:
        assert server.port > 0
    finally:
        server.stop()


async def test_server_rejects_wrong_credentials(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(
        username="monitor",
        auth_password="authpass1",  # noqa: S106
        slow_prefixes=(),
        slow_delay=0.0,
    )
    server = EmulatorServer(config)
    server.start()
    try:
        wrong_engine = SnmpEngine()
        try:
            err, _ = await _snmp_get(
                wrong_engine,
                server.port,
                "1.3.6.1.2.1.1.1.0",
                username="unknown",
                auth_password="authpass1",  # noqa: S106
                timeout=0.5,
            )
            assert err is not None
        finally:
            wrong_engine.close_dispatcher()

        err, _var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
    finally:
        server.stop()


async def test_server_slow_prefix_adds_delay(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.1)
    server = EmulatorServer(config)
    server.start()
    try:
        t = time.monotonic()
        err, _ = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.2.1.0", timeout=2.0)
        elapsed = time.monotonic() - t
        assert err is None
        assert elapsed >= 0.1
    finally:
        server.stop()


async def test_reset_server_still_responds_after_reset(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
    server = EmulatorServer(config)
    server.start()
    try:
        server.reset()
        err, var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
        assert "Emulated" in str(var_binds[0][1])
    finally:
        server.stop()


async def test_reset_drops_in_flight_slow_response(snmp_engine: SnmpEngine) -> None:
    config = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2",), slow_delay=0.3)
    server = EmulatorServer(config)
    server.start()
    try:
        received: list[object] = []

        def slow_get() -> None:
            async def _do() -> None:
                engine = SnmpEngine()
                try:
                    err, var_binds = await _snmp_get(
                        engine, server.port, "1.3.6.1.2.1.2.1.0", timeout=1.0
                    )
                    if err is None:
                        received.append(var_binds)
                finally:
                    engine.close_dispatcher()

            asyncio.run(_do())

        t = threading.Thread(target=slow_get)
        t.start()
        await asyncio.sleep(0.15)  # allow SNMPv3 engine-ID discovery + request to arrive
        server.reset()
        t.join(timeout=2.0)

        assert received == [], "slow response should have been dropped by reset"

        err, _var_binds = await _snmp_get(snmp_engine, server.port, "1.3.6.1.2.1.1.1.0")
        assert err is None
    finally:
        server.stop()
