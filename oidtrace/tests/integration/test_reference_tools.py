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

from oidtrace.auth import password_to_key
from oidtrace.tracefile import read_trace
from oidtrace.walker import WalkSettings, run_walk
from tests.support.emulator import _EMU_ENGINE_ID, EmuDevice

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


@pytest.mark.asyncio
async def test_snmpwalk_v1(
    emulator_factory: _EmuFactory,
) -> None:
    """snmpwalk -v1 against emulator returns all 50 OIDs with exit code 0."""
    snmpwalk = _require_tool("snmpwalk")

    device_size = 50

    async with emulator_factory(EmuDevice.simple(device_size)) as (host, port):
        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    snmpwalk,
                    "-v1",
                    "-c",
                    "public",
                    "-On",
                    "-t",
                    "2",
                    "-r",
                    "0",
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    assert proc_result.returncode == 0, (
        f"snmpwalk exited {proc_result.returncode}. stderr: {proc_result.stderr!r}"
    )

    oid_lines = [line for line in proc_result.stdout.splitlines() if line.startswith(".")]
    assert len(oid_lines) == device_size, (
        f"Expected {device_size} OID lines, got {len(oid_lines)}.\n"
        f"stdout: {proc_result.stdout[:500]!r}"
    )


@pytest.mark.asyncio
async def test_snmpwalk_v1_crosswalk(
    emulator_factory: _EmuFactory,
    tmp_path: Path,
) -> None:
    """Our v1 OID sequence matches snmpwalk -v1's output on same emulator."""
    snmpwalk = _require_tool("snmpwalk")

    device_size = 50
    trace_path = tmp_path / "crosswalk_v1.oidtrace.jsonl.gz"

    async with emulator_factory(EmuDevice.simple(device_size)) as (host, port):
        # Run our walker
        await run_walk(
            host,
            port,
            settings=WalkSettings(snmp_version="1", timeout_s=2.0),
            path=trace_path,
        )

        # Run snmpwalk against the same live emulator
        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    snmpwalk,
                    "-v1",
                    "-c",
                    "public",
                    "-On",  # numeric OIDs
                    "-t",
                    "2",
                    "-r",
                    "0",
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    # Parse snmpwalk output: lines starting with "." → token before first space
    ref_oids: list[str] = []
    for line in proc_result.stdout.splitlines():
        if line.startswith("."):
            token = line.split()[0]
            ref_oids.append(token.lstrip("."))

    assert ref_oids, f"snmpwalk produced no output. stderr: {proc_result.stderr!r}"

    # Parse our trace: exchange varbinds in order, excluding Null/noSuchName varbinds
    our_oids: list[str] = []
    for record in read_trace(trace_path):
        if record.type == "exchange" and record.response is not None:
            for vb in record.response.varbinds:
                if vb.vtype != "Null":
                    our_oids.append(vb.oid.root)

    # v1 stops cleanly on noSuchName — sequences should match exactly
    assert our_oids == ref_oids, (
        f"OID mismatch.\n"
        f"  ours ({len(our_oids)}): {our_oids[:5]}...\n"
        f"  ref  ({len(ref_oids)}): {ref_oids[:5]}..."
    )

    # And we saw exactly device_size distinct OIDs
    assert len(our_oids) == device_size, f"Expected {device_size} OIDs, got {len(our_oids)}"


@pytest.mark.asyncio
async def test_snmpwalk_v3_noauthnopriv(
    emulator_factory: _EmuFactory,
) -> None:
    """snmpwalk -v3 noAuthNoPriv against emulator returns all 50 OIDs with exit code 0."""
    snmpwalk = _require_tool("snmpwalk")

    device_size = 50

    async with emulator_factory(EmuDevice.simple(device_size)) as (host, port):
        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    snmpwalk,
                    "-v3",
                    "-u",
                    "noAuthUser",
                    "-l",
                    "noAuthNoPriv",
                    "-On",
                    "-t",
                    "2",
                    "-r",
                    "0",
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    assert proc_result.returncode == 0, (
        f"snmpwalk exited {proc_result.returncode}. stderr: {proc_result.stderr!r}"
    )

    oid_lines = [line for line in proc_result.stdout.splitlines() if line.startswith(".")]
    assert len(oid_lines) == device_size, (
        f"Expected {device_size} OID lines, got {len(oid_lines)}.\n"
        f"stdout: {proc_result.stdout[:500]!r}"
    )


@pytest.mark.asyncio
async def test_v3_oidtrace_vs_snmpwalk_crosswalk(
    emulator_factory: _EmuFactory,
    tmp_path: Path,
) -> None:
    """Our v3 OID sequence matches snmpwalk -v3 noAuthNoPriv prefix (trap #13)."""
    snmpwalk = _require_tool("snmpwalk")

    device_size = 50
    trace_path = tmp_path / "crosswalk_v3.oidtrace.jsonl.gz"

    async with emulator_factory(EmuDevice.simple(device_size)) as (host, port):
        # Run our walker
        await run_walk(
            host,
            port,
            settings=WalkSettings(
                snmp_version="3", v3_user="noAuthUser", bulk_size=10, timeout_s=2.0
            ),
            path=trace_path,
        )

        # Run snmpwalk -v3 against the same live emulator
        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    snmpwalk,
                    "-v3",
                    "-u",
                    "noAuthUser",
                    "-l",
                    "noAuthNoPriv",
                    "-On",  # numeric OIDs
                    "-t",
                    "2",
                    "-r",
                    "0",
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    # Parse snmpwalk output: lines starting with "." → token before first space
    ref_oids: list[str] = []
    for line in proc_result.stdout.splitlines():
        if line.startswith("."):
            token = line.split()[0]
            ref_oids.append(token.lstrip("."))

    assert ref_oids, f"snmpwalk -v3 produced no output. stderr: {proc_result.stderr!r}"

    # Parse our trace: exchange varbinds in order, excluding EndOfMibView
    # Skip the discovery exchange (pdu == "discovery")
    our_oids: list[str] = []
    for record in read_trace(trace_path):
        if record.type == "exchange" and record.response is not None:
            if record.request.pdu.value == "discovery":
                continue
            for vb in record.response.varbinds:
                if vb.vtype != "EndOfMibView":
                    our_oids.append(vb.oid.root)

    # Trap #13: our sequence is a prefix of snmpwalk's
    assert our_oids == ref_oids[: len(our_oids)], (
        f"OID mismatch.\n"
        f"  ours ({len(our_oids)}): {our_oids[:5]}...\n"
        f"  ref  ({len(ref_oids)}): {ref_oids[:5]}..."
    )

    # And we saw exactly device_size distinct OIDs
    assert len(set(our_oids)) == device_size, (
        f"Expected {device_size} distinct OIDs, got {len(set(our_oids))}"
    )


@pytest.mark.asyncio
async def test_snmpwalk_v3_authnopriv(
    emulator_factory: _EmuFactory,
) -> None:
    """snmpwalk -v3 authNoPriv MD5 against emulator returns all 20 OIDs with exit code 0."""
    snmpwalk = _require_tool("snmpwalk")

    device_size = 20
    kul = password_to_key(b"testpass1", _EMU_ENGINE_ID, "MD5")

    async with emulator_factory(
        EmuDevice.simple(n_oids=device_size, auth_users={b"authuser": ("MD5", kul)})
    ) as (host, port):
        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    snmpwalk,
                    "-v3",
                    "-u",
                    "authuser",
                    "-l",
                    "authNoPriv",
                    "-a",
                    "MD5",
                    "-A",
                    "testpass1",
                    "-On",
                    "-t",
                    "2",
                    "-r",
                    "0",
                    f"{host}:{port}",
                    "1.3.6.1",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ),
        )

    assert proc_result.returncode == 0, (
        f"snmpwalk exited {proc_result.returncode}. stderr: {proc_result.stderr!r}"
    )

    oid_lines = [line for line in proc_result.stdout.splitlines() if line.startswith(".")]
    assert len(oid_lines) == device_size, (
        f"Expected {device_size} OID lines, got {len(oid_lines)}.\n"
        f"stdout: {proc_result.stdout[:500]!r}"
    )
