"""Integration test fixtures."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest

from tests.support.emulator import EmuDevice, EmuProtocol

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


@asynccontextmanager
async def _emulator_context(device: EmuDevice) -> AsyncGenerator[tuple[str, int]]:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: EmuProtocol(device),
        local_addr=("127.0.0.1", 0),
    )
    try:
        host, port = transport.get_extra_info("sockname")
        yield host, port
    finally:
        transport.close()


@pytest.fixture
def emulator_factory() -> Callable[[EmuDevice], object]:
    """Return an async context manager factory.

    Usage::

        async with emulator_factory(device) as (host, port):
            ...
    """
    return _emulator_context
