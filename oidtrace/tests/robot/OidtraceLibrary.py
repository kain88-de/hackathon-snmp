"""Robot Framework keyword library for oidtrace spec testing.

Drives the oidtrace binary via subprocess so the spec is language-agnostic:
any conforming reimplementation passes as long as it ships an `oidtrace`
binary with the same CLI contract and trace format.

The emulator stays Python — it is a test fixture, not the thing being specced.
Trace assertions use the traceformat reader for convenience; raw JSON would
work equally well.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from robot.api.deco import keyword
from traceformat.models import Exchange, Header, Summary

from oidtrace.auth import password_to_key
from oidtrace.tracefile import read_trace
from tests.support.emulator import EMU_ENGINE_ID, EmulatorThread, EndOfMib, Quirks


class OidtraceLibrary:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self) -> None:
        self._emulator: EmulatorThread | None = None
        self._snmpd_proc: subprocess.Popen | None = None  # type: ignore[type-arg]
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

    @keyword("Start Emulator With Auth User")
    def start_emulator_with_auth_user(self, username: str, proto: str, password: str) -> None:
        kul = password_to_key(password.encode(), EMU_ENGINE_ID, proto)  # type: ignore[arg-type]
        auth_users = {username.encode(): (proto, kul)}
        self._emulator = EmulatorThread(auth_users=auth_users)
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

    def _run_walk(
        self,
        version_args: list[str],
        host: str | None = None,
        label: str | None = None,
        give_up_after: int = 2,
        start_oid: str | None = None,
    ) -> int:
        self._out_dir = Path(tempfile.mkdtemp())
        h = host or self._host or "127.0.0.1"
        cmd = ["oidtrace", "walk", *version_args, h]
        if self._port is not None:
            cmd += ["--port", str(self._port)]
        cmd += [
            "--out",
            str(self._out_dir),
            "--timeout",
            "1.0",
            "--retries",
            "0",
            "--give-up-after",
            str(give_up_after),
        ]
        if label:
            cmd += ["--label", label]
        if start_oid:
            cmd += ["--start-oid", start_oid]

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
    ) -> int:
        return self._run_walk(
            ["v2c"], host=host, label=label, give_up_after=int(give_up_after), start_oid=start_oid
        )

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

    @keyword("Trace First Exchange Should Be Discovery")
    def trace_first_exchange_should_be_discovery(self) -> None:
        assert self._trace_path, "No trace file found"
        for record in read_trace(self._trace_path):
            if isinstance(record, Exchange):
                pdu = record.request.pdu.value
                assert pdu == "discovery", f"Expected first exchange pdu='discovery', got {pdu!r}"
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
