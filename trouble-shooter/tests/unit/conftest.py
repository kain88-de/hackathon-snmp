from collections.abc import AsyncGenerator

import pytest
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine


@pytest.fixture
async def snmp_engine() -> AsyncGenerator[SnmpEngine]:
    engine = SnmpEngine()
    yield engine
    engine.close_dispatcher()
