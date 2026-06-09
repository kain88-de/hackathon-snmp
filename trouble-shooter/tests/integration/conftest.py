from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from emulator import EmulatorConfig, EmulatorServer
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Generator

from trouble_shooter.main import app

_FAST_CONFIG = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
_SLOW_CONFIG = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.05, n_interfaces=1)


@pytest.fixture(scope="session")
def _fast_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_FAST_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _slow_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_SLOW_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def emulator_fast(_fast_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _fast_server
    _fast_server.reset()


@pytest.fixture
def emulator_slow(_slow_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _slow_server
    _slow_server.reset()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
