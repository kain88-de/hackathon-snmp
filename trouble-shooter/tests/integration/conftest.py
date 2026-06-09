from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from emulator import EmulatorConfig, EmulatorServer
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Generator

from trouble_shooter.main import app

_FAST_CONFIG = EmulatorConfig(username="monitor", auth_password="authpass1", slow_prefixes=(), slow_delay=0.0)
_SLOW_CONFIG = EmulatorConfig(
    username="monitor", auth_password="authpass1",
    slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.05, n_interfaces=1,
)


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


# --- detector emulators ---

_CLEAN_CONFIG = EmulatorConfig(username="monitor", auth_password="authpass1", slow_prefixes=(), slow_delay=0.0)
_SLOW_IF_CONFIG = EmulatorConfig(
    username="monitor", auth_password="authpass1",
    slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.8, n_interfaces=1,
)
_DROP_IF_CONFIG = EmulatorConfig(
    username="monitor", auth_password="authpass1",
    slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=10.0,
)


@pytest.fixture(scope="session")
def _clean_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_CLEAN_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _slow_if_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_SLOW_IF_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def _drop_if_server() -> Generator[EmulatorServer]:
    s = EmulatorServer(_DROP_IF_CONFIG)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def emulator_clean(_clean_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _clean_server
    _clean_server.reset()


@pytest.fixture
def emulator_slow_if(_slow_if_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _slow_if_server
    _slow_if_server.reset()


@pytest.fixture
def emulator_drop_if(_drop_if_server: EmulatorServer) -> Generator[EmulatorServer]:
    yield _drop_if_server
    _drop_if_server.reset()
