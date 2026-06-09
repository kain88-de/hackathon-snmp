from collections.abc import Generator

import pytest
from emulator import EmulatorConfig, EmulatorServer
from fastapi.testclient import TestClient

from main import app

FAST = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
SLOW = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.05)


@pytest.fixture(scope="session")
def emulator_fast() -> Generator[EmulatorServer]:
    s = EmulatorServer(FAST)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def emulator_slow() -> Generator[EmulatorServer]:
    s = EmulatorServer(SLOW)
    s.start()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def reset_emulators(
    emulator_fast: EmulatorServer, emulator_slow: EmulatorServer
) -> Generator[None]:
    yield
    emulator_fast.reset()
    emulator_slow.reset()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
