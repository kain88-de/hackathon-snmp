import pytest
from fastapi.testclient import TestClient

from emulator import EmulatorConfig, EmulatorServer
from main import app

FAST = EmulatorConfig(slow_prefixes=(), slow_delay=0.0)
SLOW = EmulatorConfig(slow_prefixes=("1.3.6.1.2.1.2.2.1",), slow_delay=0.05)


@pytest.fixture(scope="session")
def emulator_fast():
    s = EmulatorServer(FAST)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def emulator_slow():
    s = EmulatorServer(SLOW)
    s.start()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def reset_emulators(emulator_fast: EmulatorServer, emulator_slow: EmulatorServer):
    yield
    emulator_fast.reset()
    emulator_slow.reset()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
