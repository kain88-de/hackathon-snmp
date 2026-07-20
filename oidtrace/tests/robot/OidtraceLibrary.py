"""Robot Framework keyword library for oidtrace spec testing.

Drives the oidtrace binary via subprocess so the spec is language-agnostic:
any conforming reimplementation passes as long as it ships an `oidtrace`
binary with the same CLI contract and trace format.

The emulator stays Python — it is a test fixture, not the thing being specced.
Trace assertions use the traceformat reader for convenience; raw JSON would
work equally well.
"""

from __future__ import annotations

import gzip
import os
import select
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from robot.api.deco import keyword
from traceformat.models import Exchange, Header, Summary, SystemInfo

from oidtrace.auth import AuthProto, password_to_key
from oidtrace.ber import encode_int, encode_oid, read_tlv
from oidtrace.oid import Oid
from oidtrace.tracefile import read_trace
from tests.support.emulator import EMU_ENGINE_ID, EmulatorThread, EndOfMib, Quirks

# All emulator OIDs live under this ifTable-like prefix (see EmuDevice.simple).
_EMU_TREE_PREFIX = "1.3.6.1.2.1.2.2.1"

# System-group allowlist (trace-format.md §4.2): name -> OID, keyed the same way
# "Trace System Info At Should Have"/"...Should Have No" take their `name` argument.
_SYSTEM_INFO_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
}
_OCTET_STRING_TAG = 0x04
_OBJECT_IDENTIFIER_TAG = 0x06
_TIME_TICKS_TAG = 0x43


def _octet_string_value(s: str) -> tuple[int, bytes]:
    return (_OCTET_STRING_TAG, s.encode())


def _object_identifier_value(oid_str: str) -> tuple[int, bytes]:
    """Raw BER payload for an ObjectIdentifier-typed value (e.g. sysObjectID.0)."""
    _tag, payload, _next = read_tlv(encode_oid(Oid.from_str(oid_str)), 0)
    return (_OBJECT_IDENTIFIER_TAG, payload)


def _time_ticks_value(ticks: int) -> tuple[int, bytes]:
    """Raw BER payload for a TimeTicks-typed value (e.g. sysUpTime.0)."""
    _tag, payload, _next = read_tlv(encode_int(ticks, tag=_TIME_TICKS_TAG), 0)
    return (_TIME_TICKS_TAG, payload)


class OidtraceLibrary:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self) -> None:
        self._emulator: EmulatorThread | None = None
        self._snmpd_proc: subprocess.Popen[bytes] | None = None
        self._snmpd_conf_dir: Path | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._out_dir: Path | None = None
        self._stdout: str = ""
        self._stderr: str = ""
        self._rc: int = -1
        self._trace_path: Path | None = None

    # ------------------------------------------------------------------
    # Emulator lifecycle
    # ------------------------------------------------------------------

    @keyword("Start Emulator")
    def start_emulator(self) -> None:
        self._emulator = EmulatorThread()
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Fixed Request Id")
    def start_emulator_with_fixed_request_id(self, request_id: int) -> None:
        self._emulator = EmulatorThread(quirks=Quirks(fixed_request_id=int(request_id)))
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With End Of Mib Wrap")
    def start_emulator_with_end_of_mib_wrap(self) -> None:
        self._emulator = EmulatorThread(quirks=Quirks(end_of_mib=EndOfMib.WRAP))
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Drop All")
    def start_emulator_with_drop_all(self) -> None:
        self._emulator = EmulatorThread(quirks=Quirks(drop_all=True))
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Corrupted Discovery Reply")
    def start_emulator_with_corrupted_discovery_reply(self) -> None:
        self._emulator = EmulatorThread(quirks=Quirks(corrupt_discovery_reply=True))
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Duplicate Responses")
    def start_emulator_with_duplicate_responses(self) -> None:
        self._emulator = EmulatorThread(quirks=Quirks(duplicate_responses=True))
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Slow Oids")
    def start_emulator_with_slow_oids(self, per_oid_delay: float = 0.05) -> None:
        """Emulator that stalls per_oid_delay seconds per returned OID.

        Used to make a walk long enough to hit a time budget or a Ctrl-C
        before it completes on its own.
        """
        self._emulator = EmulatorThread(
            quirks=Quirks(
                slow_prefix=Oid.from_str(_EMU_TREE_PREFIX),
                per_oid_delay_s=float(per_oid_delay),
            )
        )
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Delayed First Response")
    def start_emulator_with_delayed_first_response(self, delay_s: float = 0.6) -> None:
        """Emulator whose very first reply is delayed; every later one is slow but on time.

        Used to simulate a genuinely late response: the walker's first exchange
        times out (no correlation to save it), the walk continues, and the
        stale reply lands in the transport's queue sometime later, during a
        subsequent exchange's wait window. Every other reply is throttled via
        the existing per-OID delay so the walk stays alive long enough (many
        seconds) for the stale reply to land mid-walk rather than after the
        walk (and its socket) is already gone.
        """
        self._emulator = EmulatorThread(
            quirks=Quirks(
                delay_first_response_s=float(delay_s),
                slow_prefix=Oid.from_str(_EMU_TREE_PREFIX),
                per_oid_delay_s=0.05,
            )
        )
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Auth User")
    def start_emulator_with_auth_user(self, username: str, proto: str, password: str) -> None:
        # Normalize case: "sha-256" -> "SHA-256", "md5" -> "MD5", etc.
        auth_proto = AuthProto(proto.upper())
        kul = password_to_key(password.encode(), EMU_ENGINE_ID, auth_proto)
        auth_users = {username.encode(): (auth_proto, kul)}
        self._emulator = EmulatorThread(auth_users=auth_users)
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With Auth User And Corrupted Responses")
    def start_emulator_with_auth_user_and_corrupted_responses(
        self, username: str, proto: str, password: str
    ) -> None:
        auth_proto = AuthProto(proto.upper())
        kul = password_to_key(password.encode(), EMU_ENGINE_ID, auth_proto)
        auth_users = {username.encode(): (auth_proto, kul)}
        self._emulator = EmulatorThread(
            quirks=Quirks(corrupt_auth_responses=True), auth_users=auth_users
        )
        self._host, self._port = self._emulator.__enter__()

    @keyword("Start Emulator With System Info")
    def start_emulator_with_system_info(
        self,
        sys_descr: str | None = None,
        sys_object_id: str | None = None,
        sys_uptime: int | None = None,
        sys_name: str | None = None,
    ) -> None:
        """Emulator whose system group answers Get only for the given OIDs.

        An allowlisted OID left as None is absent from the device: a plain Get for
        it comes back NoSuchObject, modeling a device that does not expose that
        field (e.g. sysName unconfigured). sys_object_id is a dotted OID string
        (ObjectIdentifier); sys_uptime is an integer tick count (TimeTicks); the
        other two are OctetString.
        """
        system_info: dict[Oid, tuple[int, bytes]] = {}
        if sys_descr is not None:
            system_info[Oid.from_str(_SYSTEM_INFO_OIDS["sysDescr"])] = _octet_string_value(
                sys_descr
            )
        if sys_object_id is not None:
            system_info[Oid.from_str(_SYSTEM_INFO_OIDS["sysObjectID"])] = _object_identifier_value(
                sys_object_id
            )
        if sys_uptime is not None:
            system_info[Oid.from_str(_SYSTEM_INFO_OIDS["sysUpTime"])] = _time_ticks_value(
                int(sys_uptime)
            )
        if sys_name is not None:
            system_info[Oid.from_str(_SYSTEM_INFO_OIDS["sysName"])] = _octet_string_value(sys_name)
        self._emulator = EmulatorThread(system_info=system_info)
        self._host, self._port = self._emulator.__enter__()

    @keyword("Stop Emulator")
    def stop_emulator(self) -> None:
        if self._emulator is not None:
            self._emulator.__exit__(None, None, None)
            self._emulator = None

    # ------------------------------------------------------------------
    # snmpd lifecycle (reference-tier: requires net-snmp installed)
    # ------------------------------------------------------------------

    @keyword("Start Snmpd With SHA256 User")
    def start_snmpd_with_sha256_user(self, username: str, auth_proto: str, auth_pass: str) -> None:
        """Start snmpd configured with one SNMPv3 auth user.

        snmpd's libnetsnmp implements SHA-256 independently of our auth.py,
        making it an authoritative oracle for wire-correct 24-byte MACs.
        Requires net-snmp >= 5.8 (first release with SHA-2 USM support).
        """
        if shutil.which("snmpd") is None:
            raise AssertionError(
                "snmpd not found — install net-snmp to run reference_tools scenarios"
            )

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        self._snmpd_conf_dir = Path(tempfile.mkdtemp())
        conf_path = self._snmpd_conf_dir / "snmpd.conf"
        conf_path.write_text(
            f'createUser {username} {auth_proto} "{auth_pass}"\n'
            f"rouser {username} authNoPriv .1.3.6\n"
        )

        self._snmpd_proc = subprocess.Popen(
            [
                "snmpd",
                "-f",
                "-Lo",
                "--no-root-check",
                "-C",
                "-c",
                str(conf_path),
                f"udp:127.0.0.1:{port}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)

        if self._snmpd_proc.poll() is not None:
            raise AssertionError(
                f"snmpd exited immediately (rc={self._snmpd_proc.returncode}) — "
                "check that net-snmp supports SHA-256 (requires >= 5.8)"
            )

        self._host = "127.0.0.1"
        self._port = port

    @keyword("Stop Snmpd")
    def stop_snmpd(self) -> None:
        if self._snmpd_proc is not None:
            self._snmpd_proc.terminate()
            try:
                self._snmpd_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._snmpd_proc.kill()
            self._snmpd_proc = None
        if self._snmpd_conf_dir is not None:
            shutil.rmtree(self._snmpd_conf_dir, ignore_errors=True)
            self._snmpd_conf_dir = None

    # ------------------------------------------------------------------
    # Walk invocation
    # ------------------------------------------------------------------

    def _build_walk_cmd(
        self,
        version_args: list[str],
        host: str | None,
        label: str | None,
        give_up_after: int,
        start_oid: str | None,
        timeout: str,
        time_budget: str | None,
        community: str | None,
        bulk_size: int | None = None,
        retries: int = 0,
    ) -> list[str]:
        h = host or self._host or "127.0.0.1"
        cmd = ["oidtrace", "walk", *version_args, h]
        if self._port is not None:
            cmd += ["--port", str(self._port)]
        cmd += [
            "--out",
            str(self._out_dir),
            "--timeout",
            timeout,
            "--retries",
            str(retries),
            "--give-up-after",
            str(give_up_after),
        ]
        if label:
            cmd += ["--label", label]
        if start_oid:
            cmd += ["--start-oid", start_oid]
        if time_budget:
            cmd += ["--time-budget", time_budget]
        if community:
            cmd += ["--community", community]
        if bulk_size is not None:
            cmd += ["--bulk-size", str(bulk_size)]
        return cmd

    def _run_walk(
        self,
        version_args: list[str],
        host: str | None = None,
        label: str | None = None,
        give_up_after: int = 2,
        start_oid: str | None = None,
        time_budget: str | None = None,
        community: str | None = None,
        timeout: str = "1.0",
        bulk_size: int | None = None,
        retries: int = 0,
    ) -> int:
        self._out_dir = Path(tempfile.mkdtemp())
        cmd = self._build_walk_cmd(
            version_args,
            host,
            label,
            give_up_after,
            start_oid,
            timeout,
            time_budget,
            community,
            bulk_size,
            retries,
        )
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self._rc = result.returncode
        self._stdout = result.stdout
        self._stderr = result.stderr

        traces = list(self._out_dir.glob("*.oidtrace.jsonl.gz"))
        self._trace_path = traces[0] if traces else None
        return self._rc

    @keyword("Walk V2c")
    def walk_v2c(
        self,
        host: str | None = None,
        label: str | None = None,
        give_up_after: int = 2,
        start_oid: str | None = None,
        time_budget: str | None = None,
        community: str | None = None,
        timeout: str = "1.0",
        bulk_size: int | None = None,
        retries: int = 0,
    ) -> int:
        return self._run_walk(
            ["v2c"],
            host=host,
            label=label,
            give_up_after=int(give_up_after),
            start_oid=start_oid,
            time_budget=time_budget,
            community=community,
            timeout=timeout,
            bulk_size=bulk_size,
            retries=int(retries),
        )

    @keyword("Walk V2c And Interrupt After")
    def walk_v2c_and_interrupt_after(self, delay_s: float = 0.3) -> int:
        """Start a walk, wait until it is actually walking, then send SIGINT.

        Exercises the Ctrl-C-is-a-first-class-exit contract: the CLI flushes the
        interrupted summary, prints the terminal verdict, and exits 0.

        The signal must land *inside* the walk loop, not during the child's
        interpreter startup and imports (which take longer than any fixed sleep
        and happen before the CLI installs its KeyboardInterrupt-suppressing
        block). Firing early races that startup and gets the child killed by
        raw SIGINT (rc=-2) instead of the graceful exit-0 path. So we wait for
        the first progress line on stderr — emitted only once the walk loop is
        running — then let delay_s of real walking elapse before interrupting.
        """
        self._out_dir = Path(tempfile.mkdtemp())
        cmd = self._build_walk_cmd(
            ["v2c"], None, None, 2, None, timeout="5.0", time_budget=None, community=None
        )
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stderr_prefix = self._wait_for_walk_start(proc, marker=b"exchanges", timeout_s=10.0)
        time.sleep(float(delay_s))
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=15)
        self._stdout = out.decode()
        self._stderr = (stderr_prefix + err).decode()
        self._rc = proc.returncode

        traces = list(self._out_dir.glob("*.oidtrace.jsonl.gz"))
        self._trace_path = traces[0] if traces else None
        return self._rc

    @staticmethod
    def _wait_for_walk_start(
        proc: subprocess.Popen[bytes], marker: bytes, timeout_s: float
    ) -> bytes:
        """Block until the child prints the progress marker on stderr.

        Returns the stderr bytes consumed while waiting, so the caller can
        prepend them to the rest captured by communicate(). Raises if the child
        exits or the marker never appears within timeout_s (a real failure: the
        walk never started).
        """
        assert proc.stderr is not None
        fd = proc.stderr.fileno()
        no_fds: list[int] = []
        buf = b""
        deadline = time.monotonic() + timeout_s
        while marker not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    f"walk did not emit progress within {timeout_s}s; "
                    f"stderr so far:\n{buf.decode(errors='replace')}"
                )
            ready, _, _ = select.select([fd], no_fds, no_fds, remaining)
            if not ready:
                continue
            chunk = os.read(fd, 4096)
            if not chunk:  # EOF: child exited before walking
                raise AssertionError(
                    f"walk exited before emitting progress (rc={proc.poll()}); "
                    f"stderr:\n{buf.decode(errors='replace')}"
                )
            buf += chunk
        return buf

    @keyword("Walk V1")
    def walk_v1(self, host: str | None = None, give_up_after: int = 2) -> int:
        return self._run_walk(["v1"], host=host, give_up_after=int(give_up_after))

    @keyword("Walk V3 As User")
    def walk_v3_as_user(self, user: str, host: str | None = None, give_up_after: int = 2) -> int:
        return self._run_walk(["v3", "--user", user], host=host, give_up_after=int(give_up_after))

    @keyword("Walk V3 With Auth Proto Only")
    def walk_v3_with_auth_proto_only(
        self, user: str, auth_proto: str, host: str | None = None
    ) -> int:
        return self._run_walk(["v3", "--user", user, "--auth-proto", auth_proto], host=host)

    @keyword("Walk V3 With Auth")
    def walk_v3_with_auth(
        self,
        user: str,
        auth_proto: str,
        auth_pass: str,
        host: str | None = None,
        give_up_after: int = 2,
    ) -> int:
        return self._run_walk(
            ["v3", "--user", user, "--auth-proto", auth_proto, "--auth-pass", auth_pass],
            host=host,
            give_up_after=int(give_up_after),
        )

    @keyword("Run Oidtrace Walk With No Version")
    def run_oidtrace_walk_with_no_version(self) -> int:
        """Invoke `oidtrace walk` with no v1/v2c/v3 sub-subcommand."""
        result = subprocess.run(["oidtrace", "walk"], capture_output=True, text=True, check=False)
        self._rc = result.returncode
        self._stdout = result.stdout
        self._stderr = result.stderr
        self._trace_path = None
        return self._rc

    @keyword("Walk V1 With Bulk Size Flag")
    def walk_v1_with_bulk_size_flag(self, host: str | None = None) -> int:
        """Attempt `oidtrace walk v1 --bulk-size` — v1 has no such flag."""
        self._out_dir = Path(tempfile.mkdtemp())
        h = host or self._host or "127.0.0.1"
        cmd = ["oidtrace", "walk", "v1", h, "--bulk-size", "10", "--out", str(self._out_dir)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self._rc = result.returncode
        self._stdout = result.stdout
        self._stderr = result.stderr
        traces = list(self._out_dir.glob("*.oidtrace.jsonl.gz"))
        self._trace_path = traces[0] if traces else None
        return self._rc

    @keyword("Walk V3 With No User")
    def walk_v3_with_no_user(self, host: str | None = None) -> int:
        """Attempt `oidtrace walk v3` without --user — USM has no anonymous identity."""
        self._out_dir = Path(tempfile.mkdtemp())
        h = host or self._host or "127.0.0.1"
        cmd = ["oidtrace", "walk", "v3", h, "--out", str(self._out_dir)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self._rc = result.returncode
        self._stdout = result.stdout
        self._stderr = result.stderr
        traces = list(self._out_dir.glob("*.oidtrace.jsonl.gz"))
        self._trace_path = traces[0] if traces else None
        return self._rc

    # ------------------------------------------------------------------
    # Assertions: exit code and output streams
    # ------------------------------------------------------------------

    @keyword("Last Exit Code Should Be")
    def last_exit_code_should_be(self, expected: int) -> None:
        assert self._rc == int(expected), f"Expected exit code {expected}, got {self._rc}"

    @keyword("Stdout Should Contain")
    def stdout_should_contain(self, text: str) -> None:
        assert text.lower() in self._stdout.lower(), f"Expected {text!r} in stdout:\n{self._stdout}"

    @keyword("Stderr Should Contain")
    def stderr_should_contain(self, text: str) -> None:
        assert text.lower() in self._stderr.lower(), f"Expected {text!r} in stderr:\n{self._stderr}"

    # ------------------------------------------------------------------
    # Assertions: trace file
    # ------------------------------------------------------------------

    @keyword("Trace File Should Exist")
    def trace_file_should_exist(self) -> None:
        assert self._trace_path and self._trace_path.exists(), (
            f"Expected a trace file in {self._out_dir}"
        )

    @keyword("No Trace File Should Exist")
    def no_trace_file_should_exist(self) -> None:
        if self._out_dir and self._out_dir.exists():
            traces = list(self._out_dir.glob("*.oidtrace.jsonl.gz"))
            assert not traces, f"Expected no trace file, found {traces}"

    @keyword("Trace Filename Should Start With")
    def trace_filename_should_start_with(self, prefix: str) -> None:
        assert self._trace_path, "No trace file found"
        assert self._trace_path.name.startswith(prefix), (
            f"Expected filename starting with {prefix!r}, got {self._trace_path.name!r}"
        )

    @keyword("No File Matching Should Exist In Out Dir Parent")
    def no_file_matching_should_exist_in_out_dir_parent(self, pattern: str) -> None:
        """Assert a hostile --label did not write a file outside --out.

        Cleans up any leaked file so a pre-fix (failing) run doesn't litter /tmp.
        """
        assert self._out_dir, "No out dir recorded"
        leaked = list(self._out_dir.parent.glob(pattern))
        for f in leaked:
            f.unlink(missing_ok=True)
        assert not leaked, f"Label caused file(s) to escape --out directory: {leaked}"

    # ------------------------------------------------------------------
    # Assertions: trace records
    # ------------------------------------------------------------------

    @keyword("Trace Header Label Should Be")
    def trace_header_label_should_be(self, label: str) -> None:
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Header):
                assert record.label == label, f"Expected label {label!r}, got {record.label!r}"
                return
        raise AssertionError("No Header record in trace")

    @keyword("Trace Should Have End Reason")
    def trace_should_have_end_reason(self, end_reason: str) -> None:
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Summary):
                assert record.end_reason == end_reason, (
                    f"Expected end_reason {end_reason!r}, got {record.end_reason!r}"
                )
                return
        raise AssertionError("No Summary record in trace")

    @keyword("Trace System Info At Should Have")
    def trace_system_info_at_should_have(self, point: str, name: str, expected: str) -> None:
        """Assert the system_info record at `point` (start/end) has `name`
        (sysDescr/sysObjectID/sysUpTime/sysName) equal to `expected`.
        """
        oid = _SYSTEM_INFO_OIDS[name]
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, SystemInfo) and record.point.value == point:
                actual = record.values.get(oid)
                assert str(actual) == expected, (
                    f"Expected {name} {expected!r} at point={point!r}, got {actual!r}"
                )
                return
        raise AssertionError(f"No system_info record at point={point!r} in trace")

    @keyword("Trace System Info At Should Have No")
    def trace_system_info_at_should_have_no(self, point: str, name: str) -> None:
        """Assert the system_info record at `point` omits `name` entirely."""
        oid = _SYSTEM_INFO_OIDS[name]
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, SystemInfo) and record.point.value == point:
                assert oid not in record.values, (
                    f"Expected no {name} in system_info at point={point!r}, got {record.values}"
                )
                return
        raise AssertionError(f"No system_info record at point={point!r} in trace")

    @keyword("Trace Should Have Violation")
    def trace_should_have_violation(self, violation: str) -> None:
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Summary):
                assert violation in record.violation_counts, (
                    f"Violation {violation!r} not in {record.violation_counts}"
                )
                return
        raise AssertionError("No Summary record in trace")

    @keyword("Trace Should Not Contain End Of Mib")
    def trace_should_not_contain_end_of_mib(self) -> None:
        """Assert no exchange carries an EndOfMibView varbind.

        A full-MIB walk ends *because* the device returns EndOfMibView; a
        subtree-scoped walk ends because the cursor left the subtree, so no
        EndOfMibView is ever seen. This distinguishes the two COMPLETED paths.
        """
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Exchange) and record.response is not None:
                for vb in record.response.varbinds:
                    assert vb.vtype != "EndOfMibView", (
                        f"Unexpected EndOfMibView varbind at {vb.oid.root}"
                    )

    @keyword("Trace Bytes Should Not Contain")
    def trace_bytes_should_not_contain(self, text: str) -> None:
        """Assert the raw decompressed trace never contains the given text.

        Guards the privacy contract: the community string (and any other
        sensitive input) must never reach the trace file in any record.
        """
        assert self._trace_path, "No trace file found"
        raw = gzip.decompress(self._trace_path.read_bytes())
        assert text.encode() not in raw, f"Trace unexpectedly contains {text!r}"

    @keyword("Trace First Exchange Should Be Discovery")
    def trace_first_exchange_should_be_discovery(self) -> None:
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Exchange):
                pdu = record.request.pdu.value
                assert pdu == "discovery", f"Expected first exchange pdu='discovery', got {pdu!r}"
                return
        raise AssertionError("No Exchange records in trace")

    @keyword("Trace First Exchange Should Have No Violations")
    def trace_first_exchange_should_have_no_violations(self) -> None:
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Exchange):
                assert not record.violations, (
                    f"Expected no violations on first exchange, got {record.violations}"
                )
                return
        raise AssertionError("No Exchange records in trace")

    # ------------------------------------------------------------------
    # Reference-tier assertions (require net-snmp tools installed)
    # ------------------------------------------------------------------

    @keyword("OID Sequence Should Match Snmpwalk V3 Auth")
    def oid_sequence_should_match_snmpwalk_v3_auth(
        self, user: str, auth_proto: str, auth_pass: str
    ) -> None:
        """Run snmpwalk against the live emulator and compare OID sequences.

        snmpwalk uses an independent libnetsnmp SHA-2 implementation, so a match
        proves our key derivation and MAC are wire-correct, not just internally
        consistent.
        """
        assert self._host and self._port, "No emulator running"
        assert self._trace_path, "No trace recorded — call Walk V3 With Auth first"

        result = subprocess.run(
            [
                "snmpwalk",
                "-v3",
                "-u",
                user,
                "-l",
                "authNoPriv",
                "-a",
                auth_proto,
                "-A",
                auth_pass,
                "-On",
                "-t",
                "2",
                "-r",
                "0",
                f"{self._host}:{self._port}",
                "1.3.6.1",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

        ref_oids: list[str] = []
        for line in result.stdout.splitlines():
            if line.startswith("."):
                ref_oids.append(line.split()[0].lstrip("."))

        assert ref_oids, (
            f"snmpwalk produced no output — not installed or auth failed. stderr: {result.stderr!r}"
        )

        our_oids: list[str] = []
        for record in read_trace(self._trace_path):
            if (
                isinstance(record, Exchange)
                and record.request.pdu.value != "discovery"
                and record.response is not None
            ):
                for vb in record.response.varbinds:
                    if vb.vtype != "EndOfMibView":
                        our_oids.append(vb.oid.root)

        assert our_oids, "Our trace has no data varbinds"
        assert our_oids == ref_oids[: len(our_oids)], (
            f"OID sequence mismatch.\n"
            f"  ours ({len(our_oids)}): {our_oids[:5]}...\n"
            f"  snmpwalk ({len(ref_oids)}): {ref_oids[:5]}..."
        )
