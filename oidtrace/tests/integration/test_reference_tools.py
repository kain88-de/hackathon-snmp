"""Cross-walk test: compare our walker output against snmpbulkwalk (net-snmp)."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from traceformat.models import Exchange

from oidtrace.oid import Oid
from oidtrace.tracefile import read_trace
from oidtrace.walker import WalkSettings, run_walk
from tests.support.emulator import EmuDevice

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.reference_tools


def _require_snmpbulkwalk() -> None:
    """Skip or hard-fail if snmpbulkwalk is not on PATH."""
    if shutil.which("snmpbulkwalk") is not None:
        return
    if os.environ.get("REQUIRE_REFERENCE_TOOLS"):
        pytest.fail("snmpbulkwalk not on PATH — install net-snmp to run reference_tools tests")
    pytest.skip("snmpbulkwalk not on PATH — install net-snmp to run reference_tools tests")


async def test_walker_matches_snmpbulkwalk(
    tmp_path: Path,
    emulator_factory: Callable[[EmuDevice], Any],
) -> None:
    """OID sequence from our walker matches snmpbulkwalk against the same emulator."""
    _require_snmpbulkwalk()

    device = EmuDevice.simple(n_oids=50)
    path = tmp_path / "trace.gz"
    settings = WalkSettings(
        bulk_size=10,
        timeout_s=2.0,
        retries=0,
        start_oid=Oid.from_str("1.3.6.1"),
    )

    async with emulator_factory(device) as (host, port):
        await run_walk(host, port, settings=settings, path=path)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    "snmpbulkwalk",
                    "-v2c",
                    "-c",
                    "public",
                    "-On",
                    "-Cr10",
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    # Parse reference OID sequence from snmpbulkwalk output.
    # Each data line looks like: .1.3.6.1.2.1.2.2.1.1.1 = INTEGER: 0
    ref_oids: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("."):
            token = line.split()[0]
            ref_oids.append(token.lstrip("."))

    # Parse our OID sequence from the trace (exclude exception vtypes).
    our_oids: list[str] = []
    for record in read_trace(path):
        if isinstance(record, Exchange) and record.response is not None:
            for vb in record.response.varbinds:
                if vb.vtype not in {"EndOfMibView", "NoSuchObject", "NoSuchInstance"}:
                    our_oids.append(vb.oid.root)

    assert len(ref_oids) > 0, "snmpbulkwalk returned no OIDs"

    # snmpbulkwalk may overshoot by fetching one past the MIB end; our walker
    # stops exactly at the boundary.  Our sequence must be a prefix of the
    # reference, and the reference must not exceed ours by more than one bulk.
    assert ref_oids[: len(our_oids)] == our_oids, (
        "OID sequence mismatch — first divergence at index "
        + str(
            next(
                (i for i, (a, b) in enumerate(zip(ref_oids, our_oids, strict=False)) if a != b),
                len(our_oids),
            )
        )
    )

    # We must have seen exactly 50 distinct OIDs.
    assert len(set(our_oids)) == 50
