"""Integration test fixtures."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

import pytest

from tests.support.emulator import EmuDevice, EmuProtocol, Quirks

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


@pytest.fixture
def emulator_factory() -> Callable[..., AbstractAsyncContextManager[tuple[str, int]]]:
    """Async-contextmanager fixture that binds a quirk emulator to a loopback UDP port.

    Usage::

        async with emulator_factory(EmuDevice.simple()) as (host, port):
            ...
    """

    @asynccontextmanager
    async def _factory(
        device: EmuDevice | None = None,
        *,
        quirks: Quirks | None = None,
    ) -> AsyncGenerator[tuple[str, int]]:
        if device is None:
            device = EmuDevice.simple(quirks=quirks)
        loop = asyncio.get_event_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: EmuProtocol(device),
            local_addr=("127.0.0.1", 0),
        )
        try:
            sock = transport.get_extra_info("sockname")
            host: str = sock[0]
            port: int = sock[1]
            yield host, port
        finally:
            transport.close()

    return _factory
