"""Unit tests for SnmpProber.bulk_walk batch-construction logic.

These tests mock ``bulk_cmd`` and ``UdpTransportTarget.create`` so no real
network I/O occurs.  They exercise the SNMP end-of-MIB path where pysnmp
returns EndOfMibView sentinels in the varbind list.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pysnmp.proto.rfc1902 import ObjectName, OctetString
from pysnmp.proto.rfc1905 import EndOfMibView

from trouble_shooter.detector.prober import SnmpProber

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REAL_OID = "1.3.6.1.2.1.1.1.0"
_SENTINEL_OID = "1.3.6.1.2.1.1.5.0"


def _real_vb(oid: str = _REAL_OID, value: str = "hello") -> tuple[object, ...]:
    """Return a (ObjectName, OctetString) varbind as pysnmp yields."""
    return (ObjectName(oid), OctetString(value))


def _sentinel_vb(oid: str = _SENTINEL_OID) -> tuple[object, ...]:
    """Return a (ObjectName, EndOfMibView) varbind representing end-of-MIB."""
    return (ObjectName(oid), EndOfMibView().clone(""))


def _make_prober() -> SnmpProber:
    return SnmpProber("127.0.0.1", "monitor", 161, auth_password="authpass1", timeout=1.0, retries=0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_walk_end_of_mib_sentinel_not_in_batch() -> None:
    """EndOfMibView varbinds must NOT appear as OIDs in any yielded Batch.

    Regression test: the old code built `oids` from ALL varbinds before
    filtering, so the sentinel entry leaked into Batch.oids.
    """
    fake_transport = MagicMock()

    async def fake_bulk_cmd(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        # Single response: one real OID followed by one EndOfMibView sentinel.
        return (None, 0, 0, [_real_vb(), _sentinel_vb()])

    with (
        patch("trouble_shooter.detector.prober.bulk_cmd", new=fake_bulk_cmd),
        patch(
            "trouble_shooter.detector.prober.UdpTransportTarget.create",
            new=AsyncMock(return_value=fake_transport),
        ),
    ):
        prober = _make_prober()
        batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]

    all_oid_keys = [oid for b in batches for oid, _ in b.oids]

    # The sentinel OID must not appear in any batch.
    assert _SENTINEL_OID not in all_oid_keys, (
        f"Sentinel OID {_SENTINEL_OID!r} leaked into batch.oids: {all_oid_keys}"
    )

    # Only the real OID should be present.
    assert all_oid_keys == [_REAL_OID], f"Expected only [{_REAL_OID!r}] but got {all_oid_keys}"

    # The walk must have terminated (exactly one batch, not an infinite loop).
    assert len(batches) == 1


@pytest.mark.asyncio
async def test_bulk_walk_multiple_sentinels_not_in_batch() -> None:
    """All EndOfMibView entries must be filtered when maxRepetitions overshoots.

    When bulk_size overshoots the remaining MIB, pysnmp can return MORE THAN
    ONE trailing EndOfMibView in the same response.
    """
    fake_transport = MagicMock()

    async def fake_bulk_cmd(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        return (
            None,
            0,
            0,
            [
                _real_vb("1.3.6.1.2.1.1.1.0", "v1"),
                _sentinel_vb("1.3.6.1.2.1.1.5.0"),
                _sentinel_vb("1.3.6.1.2.1.1.6.0"),
            ],
        )

    with (
        patch("trouble_shooter.detector.prober.bulk_cmd", new=fake_bulk_cmd),
        patch(
            "trouble_shooter.detector.prober.UdpTransportTarget.create",
            new=AsyncMock(return_value=fake_transport),
        ),
    ):
        prober = _make_prober()
        batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]

    all_oid_keys = [oid for b in batches for oid, _ in b.oids]
    sentinel_oids = {"1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.6.0"}

    assert not (sentinel_oids & set(all_oid_keys)), (
        f"Sentinel OIDs {sentinel_oids} leaked into batches: {all_oid_keys}"
    )
    assert all_oid_keys == ["1.3.6.1.2.1.1.1.0"]
    assert len(batches) == 1


@pytest.mark.asyncio
async def test_bulk_walk_all_sentinels_yields_no_batch() -> None:
    """When the entire response is EndOfMibView sentinels, no Batch is yielded."""
    fake_transport = MagicMock()

    async def fake_bulk_cmd(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        return (None, 0, 0, [_sentinel_vb("1.3.6.1.2.1.1.5.0")])

    with (
        patch("trouble_shooter.detector.prober.bulk_cmd", new=fake_bulk_cmd),
        patch(
            "trouble_shooter.detector.prober.UdpTransportTarget.create",
            new=AsyncMock(return_value=fake_transport),
        ),
    ):
        prober = _make_prober()
        batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]

    assert batches == [], f"Expected no batches but got {batches}"


@pytest.mark.asyncio
async def test_bulk_walk_cursor_advances_to_last_real_oid() -> None:
    """After a partial end-of-MIB response, the cursor must use the last REAL OID.

    This verifies the fix does not accidentally advance the cursor to a sentinel
    OID, which would corrupt the next GETBULK request.
    """
    fake_transport = MagicMock()
    calls: list[str] = []

    async def fake_bulk_cmd(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        # Record which OIDs were requested.
        # ObjectType is at positional args index 5 (0-indexed):
        # engine, community, transport, context, nonRepeaters, maxRep, ObjectType
        # The cursor is embedded in the ObjectType at args[-1].
        call_count = len(calls)
        if call_count == 0:
            calls.append("first")
            # Normal response — two real OIDs, no sentinel.
            return (
                None,
                0,
                0,
                [
                    _real_vb("1.3.6.1.2.1.1.1.0", "v1"),
                    _real_vb("1.3.6.1.2.1.1.2.0", "v2"),
                ],
            )
        if call_count == 1:
            calls.append("second")
            # End-of-MIB: one real OID + one sentinel.
            return (
                None,
                0,
                0,
                [
                    _real_vb("1.3.6.1.2.1.1.3.0", "v3"),
                    _sentinel_vb("1.3.6.1.2.1.1.5.0"),
                ],
            )
        calls.append("overflow")
        return (None, 0, 0, list[object]())  # should never reach here

    with (
        patch("trouble_shooter.detector.prober.bulk_cmd", new=fake_bulk_cmd),
        patch(
            "trouble_shooter.detector.prober.UdpTransportTarget.create",
            new=AsyncMock(return_value=fake_transport),
        ),
    ):
        prober = _make_prober()
        batches = [b async for b in prober.bulk_walk("1.3.6.1.2.1", bulk_size=10)]

    # Walk should stop after the second call (end-of-MIB), not loop further.
    assert "overflow" not in calls, (
        "bulk_cmd called after end-of-MIB — cursor may point at sentinel"
    )

    all_oids = [oid for b in batches for oid, _ in b.oids]
    assert "1.3.6.1.2.1.1.5.0" not in all_oids
    assert len(all_oids) == 3  # v1, v2, v3 — no sentinel
