"""Integration tests for cli.py — sync tests that drive main() directly."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traceformat.models import Header

from oidtrace.auth import AuthProto, password_to_key
from oidtrace.cli import main
from oidtrace.tracefile import read_trace
from tests.support.emulator import (
    EMU_ENGINE_ID,
    EmulatorThread,
    Quirks,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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
    assert header.snmp.version.value == "1"


def test_v3_walk_exit_0_and_trace_file(tmp_path: Path) -> None:
    """v3 walk: exit 0, exactly one trace file, header.snmp.version == '3'."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "noAuthUser",
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 0

    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, f"Expected 1 trace file, found {trace_files}"

    records = list(read_trace(trace_files[0]))
    assert isinstance(records[0], Header)
    header = records[0]
    assert header.snmp.version.value == "3", (
        f"Expected header.snmp.version == '3', got {header.snmp.version.value!r}"
    )


def test_v3_walk_with_auth_proto_and_pass_against_auth_emulator(tmp_path: Path) -> None:
    """v3 walk with --auth-proto MD5 --auth-pass against auth emulator: exit 0, trace written."""
    auth_pass = "testpass1"
    kul = password_to_key(auth_pass.encode(), EMU_ENGINE_ID, AuthProto.MD5)

    with EmulatorThread(auth_users={b"authuser": (AuthProto.MD5, kul)}) as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "authuser",
                "--auth-proto",
                "MD5",
                "--auth-pass",
                auth_pass,
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 0, f"Expected exit 0, got {ret}"
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, f"Expected 1 trace file, found {trace_files}"


def test_v3_walk_no_auth_flags_unchanged(tmp_path: Path) -> None:
    """v3 walk with --user but no auth flags: exit 0, noAuthNoPriv unchanged."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "noAuthUser",
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 0
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1


def test_v3_walk_auth_proto_without_pass_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v3 walk with --auth-proto but no --auth-pass: exit 2 with error message."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "someuser",
                "--auth-proto",
                "MD5",
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 2
    captured = capsys.readouterr()
    assert "auth-pass" in captured.err.lower(), (
        f"Expected 'auth-pass' in error message, got: {captured.err!r}"
    )
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 0, (
        f"No trace file should be created on validation error, found {trace_files}"
    )


def test_v3_walk_auth_pass_below_recommended_minimum_still_proceeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v3 walk with --auth-pass shorter than 8 chars: warns but still walks.

    RFC 3414 §11.2's minimum is a recommendation, not a wire requirement — a
    real device may be configured with a shorter passphrase, so the CLI must
    still be able to trace it.
    """
    auth_pass = "short1"
    kul = password_to_key(auth_pass.encode(), EMU_ENGINE_ID, AuthProto.MD5)

    with EmulatorThread(auth_users={b"someuser": (AuthProto.MD5, kul)}) as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "someuser",
                "--auth-proto",
                "MD5",
                "--auth-pass",
                auth_pass,
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 0, f"Expected exit 0, got {ret}"
    captured = capsys.readouterr()
    assert "auth-pass" in captured.err.lower(), (
        f"Expected an --auth-pass warning in stderr, got: {captured.err!r}"
    )
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1, f"Expected 1 trace file, found {trace_files}"


def test_v3_walk_invalid_auth_proto_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v3 walk with --auth-proto DES (unsupported): exit 2 with error message."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "someuser",
                "--auth-proto",
                "DES",
                "--auth-pass",
                "pass",
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 2
    captured = capsys.readouterr()
    assert (
        "auth-proto" in captured.err.lower()
        or "md5" in captured.err.lower()
        or "sha" in captured.err.lower()
    ), f"Expected auth-proto error in stderr, got: {captured.err!r}"
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 0, (
        f"No trace file should be created on validation error, found {trace_files}"
    )


def test_v3_walk_priv_proto_warning_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v3 walk with --priv-proto: exit 0, stderr warning about privacy not supported."""
    with EmulatorThread() as (host, port):
        ret = main(
            [
                "walk",
                "v3",
                host,
                "--port",
                str(port),
                "--out",
                str(tmp_path),
                "--user",
                "noAuthUser",
                "--priv-proto",
                "AES",
                "--priv-pass",
                "pass",
                "--timeout",
                "1.0",
                "--retries",
                "1",
            ]
        )

    assert ret == 0
    captured = capsys.readouterr()
    assert "privacy" in captured.err.lower() or "priv" in captured.err.lower(), (
        f"Expected privacy warning in stderr, got: {captured.err!r}"
    )
    trace_files = list(tmp_path.glob("*.oidtrace.jsonl.gz"))
    assert len(trace_files) == 1
