"""Integration tests for cli.py — sync tests with background-thread emulator."""

from __future__ import annotations

import asyncio
import io
import sys
import threading
from typing import TYPE_CHECKING

import pytest
from traceformat.models import Header, Summary

from oidtrace.cli import main
from oidtrace.tracefile import read_trace
from tests.support.emulator import EmuDevice, EmuProtocol

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Background-thread emulator helpers


async def _serve(device: EmuDevice, ready: threading.Event, info: dict[str, object]) -> None:
    """Spin up a UDP emulator on a background event loop; signal ready via event."""
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: EmuProtocol(device),
        local_addr=("127.0.0.1", 0),
    )
    host, port = transport.get_extra_info("sockname")
    info["host"] = host
    info["port"] = port
    ready.set()
    # Keep running until the thread is killed (daemon=True)
    await asyncio.Event().wait()


def _start_emulator(device: EmuDevice) -> tuple[str, int]:
    """Start the emulator in a daemon thread; return (host, port)."""
    ready = threading.Event()
    info: dict[str, object] = {}

    def _run() -> None:
        asyncio.run(_serve(device, ready, info))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    ready.wait(timeout=5)
    return str(info["host"]), int(info["port"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture(autouse=True)
def _community(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDTRACE_COMMUNITY", "public")


# ---------------------------------------------------------------------------
# Tests


def test_successful_walk(tmp_path: Path) -> None:
    """Walk a 30-OID device: exit 0, one trace file, label in header, summary completed."""
    host, port = _start_emulator(EmuDevice.simple(30))
    out_dir = tmp_path / "traces"

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = stdout_buf
    sys.stderr = stderr_buf
    try:
        rc = main(
            [
                "walk",
                host,
                "--port",
                str(port),
                "--out",
                str(out_dir),
                "--label",
                "mytest",
                "--bulk-size",
                "5",
                "--timeout",
                "2.0",
                "--retries",
                "0",
            ]
        )
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    stdout = stdout_buf.getvalue()
    stderr = stderr_buf.getvalue()

    assert rc == 0

    # Exactly one trace file in out dir
    trace_files = list(out_dir.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1

    # Header carries the label
    records = list(read_trace(trace_files[0]))
    header = records[0]
    assert isinstance(header, Header)
    assert header.label == "mytest"

    # Summary end_reason == completed
    summary = records[-1]
    assert isinstance(summary, Summary)
    assert summary.end_reason == "completed"

    # stdout contains "completed" and "exchanges"
    assert "completed" in stdout
    assert "exchanges" in stdout

    # stderr contains progress
    assert "exchanges" in stderr


def test_unresolvable_host(tmp_path: Path) -> None:
    """host.invalid → exit 2, stderr mentions resolution, no trace file."""
    out_dir = tmp_path / "traces"
    out_dir.mkdir()

    stderr_buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = stderr_buf
    try:
        rc = main(
            [
                "walk",
                "host.invalid",
                "--out",
                str(out_dir),
            ]
        )
    finally:
        sys.stderr = old_stderr

    assert rc == 2
    assert (
        "resolv" in stderr_buf.getvalue().lower() or "resolution" in stderr_buf.getvalue().lower()
    )
    assert list(out_dir.glob("*.oidtrace.jsonl.gz")) == []


def test_bad_start_oid(tmp_path: Path) -> None:
    """--start-oid 1.3.x → exit 2, stderr message, no trace file."""
    out_dir = tmp_path / "traces"
    out_dir.mkdir()

    stderr_buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = stderr_buf
    try:
        rc = main(
            [
                "walk",
                "127.0.0.1",
                "--out",
                str(out_dir),
                "--start-oid",
                "1.3.x",
            ]
        )
    finally:
        sys.stderr = old_stderr

    assert rc == 2
    assert stderr_buf.getvalue().strip() != ""
    assert list(out_dir.glob("*.oidtrace.jsonl.gz")) == []
