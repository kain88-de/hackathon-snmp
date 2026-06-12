"""Cross-walk test: compare our walker output against snmpbulkwalk (net-snmp).

Marker: reference_tools  — deselected by `just ci`, required by `just test-all`.
Gate: tool missing → pytest.fail when REQUIRE_REFERENCE_TOOLS set, else pytest.skip.

Trap #13: our sequence is a *prefix* of snmpbulkwalk's — snmpbulkwalk overshoots
end-of-MIB by one (it returns the final EndOfMibView entry); we stop before it.
So the assertion is: ours == ref[:len(ours)], not ours == ref.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

import pytest

from tests.support.emulator import EmuDevice

if TYPE_CHECKING:
    from pathlib import Path

_EmuFactory = Callable[..., AbstractAsyncContextManager[tuple[str, int]]]

pytestmark = pytest.mark.reference_tools


# ---------------------------------------------------------------------------
# Gate helper
# ---------------------------------------------------------------------------


def _require_tool(name: str) -> str:
    """Return the full path to *name* or skip/fail depending on env gate."""
    path = shutil.which(name)
    if path is not None:
        return path
    msg = (
        f"net-snmp tool '{name}' not found on PATH. "
        f"Install with: sudo apt install snmp  (or brew install net-snmp on macOS)"
    )
    if os.environ.get("REQUIRE_REFERENCE_TOOLS"):
        pytest.fail(msg)
    else:
        pytest.skip(msg)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snmpbulkwalk_crosswalk(
    emulator_factory: _EmuFactory,
    tmp_path: Path,
) -> None:
    """Our OID sequence matches snmpbulkwalk's prefix (trap #13)."""
    from oidtrace.tracefile import read_trace  # noqa: PLC0415
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    snmpbulkwalk = _require_tool("snmpbulkwalk")

    device_size = 50
    trace_path = tmp_path / "crosswalk.oidtrace.jsonl.gz"

    async with emulator_factory(EmuDevice.simple(device_size)) as (host, port):
        # Run our walker
        await run_walk(
            host,
            port,
            settings=WalkSettings(bulk_size=10, timeout_s=2.0),
            path=trace_path,
        )

        # Run snmpbulkwalk against the same live emulator
        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    snmpbulkwalk,
                    "-v2c",
                    "-c",
                    "public",
                    "-On",  # numeric OIDs
                    "-Cr10",  # max-repetitions=10
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    # Parse snmpbulkwalk output: lines starting with "." → token before first space
    ref_oids: list[str] = []
    for line in proc_result.stdout.splitlines():
        if line.startswith("."):
            token = line.split()[0]
            ref_oids.append(token.lstrip("."))

    assert ref_oids, f"snmpbulkwalk produced no output. stderr: {proc_result.stderr!r}"

    # Parse our trace: exchange varbinds in order, excluding EndOfMibView
    our_oids: list[str] = []
    for record in read_trace(trace_path):
        if record.type == "exchange" and record.response is not None:
            for vb in record.response.varbinds:
                if vb.vtype != "EndOfMibView":
                    our_oids.append(vb.oid.root)

    # Trap #13: our sequence is a prefix of snmpbulkwalk's
    assert our_oids == ref_oids[: len(our_oids)], (
        f"OID mismatch.\n"
        f"  ours ({len(our_oids)}): {our_oids[:5]}...\n"
        f"  ref  ({len(ref_oids)}): {ref_oids[:5]}..."
    )

    # And we saw exactly device_size distinct OIDs
    assert len(set(our_oids)) == device_size, (
        f"Expected {device_size} distinct OIDs, got {len(set(our_oids))}"
    )
