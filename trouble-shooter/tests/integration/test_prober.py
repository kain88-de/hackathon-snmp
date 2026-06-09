from __future__ import annotations

from typing import TYPE_CHECKING

from trouble_shooter.detector.prober import SnmpProber

if TYPE_CHECKING:
    from emulator import EmulatorServer

    from trouble_shooter.detector.models import Batch

_USER = "monitor"
_PASS = "authpass1"


async def test_bulk_walk_yields_batches_for_clean_device(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber(
        "127.0.0.1", _USER, emulator_clean.port, auth_password=_PASS, timeout=2.0, retries=1
    )
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    assert len(batches) > 0
    assert not any(b.timed_out for b in batches)
    all_oids = [oid for b in batches for oid, _ in b.oids]
    assert any("1.3.6.1.2.1.1" in oid for oid in all_oids), "system group missing"
    assert any("1.3.6.1.2.1.2.2.1" in oid for oid in all_oids), "ifTable missing"


async def test_bulk_walk_all_batches_have_non_negative_elapsed_ms(
    emulator_clean: EmulatorServer,
) -> None:
    prober = SnmpProber(
        "127.0.0.1", _USER, emulator_clean.port, auth_password=_PASS, timeout=2.0, retries=1
    )
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    assert all(b.elapsed_ms >= 0 for b in batches)


async def test_bulk_walk_slow_subtree_has_high_elapsed_ms(emulator_slow_if: EmulatorServer) -> None:
    # emulator has slow_delay=0.8s on ifTable; prober timeout=3s so it responds
    prober = SnmpProber(
        "127.0.0.1", _USER, emulator_slow_if.port, auth_password=_PASS, timeout=3.0, retries=0
    )
    batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]
    slow_batches = [b for b in batches if any("1.3.6.1.2.1.2.2.1" in oid for oid, _ in b.oids)]
    assert len(slow_batches) > 0
    assert any(b.elapsed_ms >= 700 for b in slow_batches)


async def test_bulk_walk_yields_timed_out_batch_when_dropped(
    emulator_drop_if: EmulatorServer,
) -> None:
    # emulator has slow_delay=10s on ifTable; prober timeout=1s so it times out
    prober = SnmpProber(
        "127.0.0.1", _USER, emulator_drop_if.port, auth_password=_PASS, timeout=1.0, retries=0
    )
    batches: list[Batch] = []
    async for batch in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10):
        batches.append(batch)
        if batch.timed_out:
            break
    assert any(b.timed_out for b in batches)


async def test_probe_oid_returns_responded_sample(emulator_clean: EmulatorServer) -> None:
    prober = SnmpProber(
        "127.0.0.1", _USER, emulator_clean.port, auth_password=_PASS, timeout=2.0, retries=1
    )
    sample = await prober.probe_oid("1.3.6.1.2.1.1.1.0")
    assert sample.responded is True
    assert sample.oid == "1.3.6.1.2.1.1.1.0"
    assert "Emulated" in sample.value
    assert sample.elapsed_ms >= 0


async def test_probe_oid_returns_unresponded_sample_on_timeout(
    emulator_drop_if: EmulatorServer,
) -> None:
    prober = SnmpProber(
        "127.0.0.1", _USER, emulator_drop_if.port, auth_password=_PASS, timeout=1.0, retries=0
    )
    sample = await prober.probe_oid("1.3.6.1.2.1.2.2.1.1.1")
    assert sample.responded is False
