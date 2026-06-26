"""Integration tests for cli.py — sync tests that drive main() directly.

The emulator runs on a daemon thread with its own event loop, bound to a
free port exposed via threading.Event.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from traceformat.models import Header

from oidtrace.cli import main
from oidtrace.tracefile import read_trace
from tests.support.emulator import EmuDevice, EmuProtocol, Quirks

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# ---------------------------------------------------------------------------
# Helpers: emulator on a background thread
# ---------------------------------------------------------------------------


def _run_emulator_on_thread(
    port_ready: threading.Event,
    port_holder: list[int],
    state: dict[str, object],
    state_ready: threading.Event,
    quirks: object = None,
) -> None:
    """Start an asyncio loop on a daemon thread, bind the emulator, set port_ready."""
    loop = asyncio.new_event_loop()

    async def _serve() -> None:
        stop = asyncio.Event()
        state["loop"] = loop
        state["stop"] = stop
        state_ready.set()

        device = EmuDevice.simple(n_oids=20, quirks=quirks if isinstance(quirks, Quirks) else None)
        transport, _ = await loop.create_datagram_endpoint(
            lambda: EmuProtocol(device),
            local_addr=("127.0.0.1", 0),
        )
        sock = transport.get_extra_info("sockname")
        port_holder.append(sock[1])
        port_ready.set()
        await stop.wait()
        transport.close()

    loop.run_until_complete(_serve())
    loop.close()


class EmulatorThread:
    """Context manager that starts an emulator on a daemon thread and tears it down."""

    def __init__(self, quirks: object = None) -> None:
        self._port_ready: threading.Event = threading.Event()
        self._port_holder: list[int] = []
        self._state: dict[str, object] = {}
        self._state_ready: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._quirks = quirks

    def __enter__(self) -> tuple[str, int]:
        self._thread = threading.Thread(
            target=_run_emulator_on_thread,
            args=(
                self._port_ready,
                self._port_holder,
                self._state,
                self._state_ready,
                self._quirks,
            ),
            daemon=True,
        )
        self._thread.start()
        self._port_ready.wait(timeout=5.0)
        assert self._port_holder, "Emulator did not bind a port in time"
        return "127.0.0.1", self._port_holder[0]

    def __exit__(self, *_: object) -> None:
        # Signal the asyncio stop event on its own loop
        loop = self._state.get("loop")
        stop_event = self._state.get("stop")
        if isinstance(loop, asyncio.AbstractEventLoop) and isinstance(stop_event, asyncio.Event):
            loop.call_soon_threadsafe(stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_successful_walk_exit_0_and_trace_file(tmp_path: Path) -> None:
    """Successful walk: exit 0, exactly one trace file, stdout has end_reason + exchanges."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0

    # Exactly one trace file written
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, f"Expected 1 trace file, found {trace_files}"


def test_successful_walk_header_label(tmp_path: Path) -> None:
    """--label is recorded in the trace header."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--label",
                "myrun",
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1
    records = list(read_trace(trace_files[0]))
    assert isinstance(records[0], Header)
    header = records[0]
    assert header.type == "header"
    assert header.label == "myrun"


def test_successful_walk_stdout_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Terminal summary on stdout: end_reason and 'exchanges' appear."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "end_reason" in out
    assert "exchange" in out.lower()


def test_successful_walk_stderr_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """At default verbosity (no -v), stderr has \\r progress lines."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0
    captured = capsys.readouterr()
    assert "\r" in captured.err


def test_verbose_vv_debug_lines_no_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """walk -vv: DEBUG lines on stderr, NO \\r progress."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
                "-vv",
            ]
        )

    assert ret == 0
    captured = capsys.readouterr()
    assert "DEBUG" in captured.err
    assert "\r" not in captured.err


def test_unresolvable_host_exit_2_no_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unresolvable host → exit 2, stderr mentions resolve, no trace file."""
    ret = main(
        [
            "walk",
            "v2c",
            "host.invalid",
            "--out",
            str(tmp_path),
        ]
    )

    assert ret == 2
    captured = capsys.readouterr()
    assert "resolve" in captured.err.lower()
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 0, (
        f"No trace file should be created on DNS error, found {trace_files}"
    )


def test_bad_start_oid_exit_2_no_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Bad --start-oid '1.3.x' → exit 2, no trace file."""
    ret = main(
        [
            "walk",
            "v2c",
            "127.0.0.1",
            "--out",
            str(tmp_path),
            "--start-oid",
            "1.3.x",
        ]
    )

    assert ret == 2
    captured = capsys.readouterr()
    assert "start-oid" in captured.err.lower()
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 0, f"No trace file should be created on bad OID, found {trace_files}"


def test_trace_filename_uses_label(tmp_path: Path) -> None:
    """Trace filename is <label>-<timestamp>.oidtrace.jsonl.gz when --label is given."""
    with EmulatorThread() as (host, port):
        main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--label",
                "testlabel",
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    trace_files = list(tmp_path.glob("testlabel-*.oidtrace.jsonl.gz"))
    all_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, f"Expected trace file with testlabel prefix, found {all_files}"


def test_trace_filename_fallback_walk(tmp_path: Path) -> None:
    """Without --label, trace filename starts with 'walk-'."""
    with EmulatorThread() as (host, port):
        main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    trace_files = list(tmp_path.glob("walk-*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, (
        f"Expected trace file with walk- prefix, found {list(tmp_path.glob('*.oidtrace.jsonl.gz'))}"
    )


def test_out_dir_created(tmp_path: Path) -> None:
    """--out dir is created if it does not exist."""
    out_dir = tmp_path / "nested" / "subdir"
    assert not out_dir.exists()

    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(out_dir),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0
    assert out_dir.exists()
    trace_files = list(out_dir.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1


def test_violation_counts_in_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """With fixed_request_id=1, every exchange produces a request-id-mismatch.

    The terminal summary printed to stdout must mention 'request-id-mismatch'
    and its non-zero count.
    """
    quirks = Quirks(fixed_request_id=1)
    with EmulatorThread(quirks=quirks) as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "request-id-mismatch" in out
    # The count must be a positive integer — check that the line is not "none"
    assert "violations  : none" not in out


def test_verbose_v_info_lines_no_progress_no_debug(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """walk -v: INFO lines on stderr, no \\r progress, no DEBUG lines."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v2c",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
                "-v",
            ]
        )

    assert ret == 0
    captured = capsys.readouterr()
    err = captured.err
    assert "INFO" in err
    assert "\r" not in err
    assert "DEBUG" not in err


def test_no_subcommand_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    """Calling main() with no subcommand prints help to stderr and returns 2."""
    ret = main([])
    assert ret == 2
    err = capsys.readouterr().err
    assert "walk" in err.lower() or "usage" in err.lower()


def test_walk_no_version_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    """Calling main(['walk']) with no version prints walk-level help to stderr and returns 2."""
    ret = main(["walk"])
    assert ret == 2
    err = capsys.readouterr().err
    assert any(tok in err for tok in ("v1", "v2c", "v3", "usage"))


def test_v1_walk_exit_0_and_trace_file(tmp_path: Path) -> None:
    """v1 walk: exit 0, exactly one trace file."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v1",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0

    # Exactly one trace file written
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, f"Expected 1 trace file, found {trace_files}"


def test_v1_walk_header_version(tmp_path: Path) -> None:
    """v1 walk: trace header has snmp.version == '1'."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v1",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--timeout",
                "1.0",
                "--retries",
                "1",
                "--give-up-after",
                "2",
            ]
        )

    assert ret == 0
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1
    records = list(read_trace(trace_files[0]))
    assert isinstance(records[0], Header)
    header = records[0]
    assert header.type == "header"
    assert str(header.snmp.version.value) == "1"


def test_walk_v3_not_implemented(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """v3 is not yet implemented: exit 2, stderr contains 'v3' and 'implement', no trace file."""
    ret = main(["walk", "v3", "127.0.0.1", "--user", "admin", "--out", str(tmp_path)])

    assert ret == 2
    captured = capsys.readouterr()
    err = captured.err.lower()
    assert "v3" in err
    assert "implement" in err
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 0, (
        f"No trace file should be created for v3 stub, found {trace_files}"
    )
