from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def snmp_engine() -> AsyncGenerator[SnmpEngine]:
    engine = SnmpEngine()
    yield engine
    engine.close_dispatcher()
