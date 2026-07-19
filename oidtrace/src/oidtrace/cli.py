"""CLI entry point for oidtrace.

Subcommand: walk v1|v2c|v3

    oidtrace walk v2c <host> [options]   # SNMP v2c (implemented)
    oidtrace walk v1  <host> [options]   # SNMP v1  (implemented)
    oidtrace walk v3  <host> [options]   # SNMP v3  noAuthNoPriv (implemented)

Operator errors (bad DNS, bad --start-oid, out-of-range numeric options) exit
2 with a stderr message and no trace file written.

Logging is configured only here (libraries never configure handlers):
  default    WARNING  + \\r progress sink on stderr
  -v         INFO     (progress suppressed; logs supersede)
  -vv        DEBUG    (progress suppressed)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
from traceformat import Summary, TraceRecord

from oidtrace.auth import AuthProto
from oidtrace.oid import Oid
from oidtrace.tracefile import read_trace
from oidtrace.walker import RecordSink, WalkSettings, run_walk

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress sink
# ---------------------------------------------------------------------------


class _ProgressSink:
    """Writes \\r<seq> exchanges... to stderr at verbosity 0."""

    def __init__(self) -> None:
        self._seq = 0

    def __call__(self, record: TraceRecord) -> None:
        if record.type == "exchange":
            self._seq += 1
            sys.stderr.write(f"\r{self._seq} exchanges...")
            sys.stderr.flush()
        elif record.type == "summary":
            sys.stderr.write("\r")
            sys.stderr.flush()


# ---------------------------------------------------------------------------
# Shared options: numeric bounds are validated here, at option definition,
# via click.IntRange rather than in a separate post-parse validator.
# ---------------------------------------------------------------------------


def _walk_options[F: Callable[..., Any]](f: F) -> F:
    """Add flags common to all version sub-commands."""
    options = [
        click.argument("host"),
        click.option("--port", type=int, default=161, help="UDP port (default: 161)."),
        click.option("--out", default=".", help="Output directory (default: current dir)."),
        click.option("--label", default=None, help="Human label; used in filename and header."),
        click.option(
            "--timeout",
            type=float,
            default=2.0,
            metavar="SECS",
            help="Per-attempt timeout in seconds (default: 2.0).",
        ),
        click.option(
            "--retries",
            type=click.IntRange(min=0),
            default=2,
            help="Retransmissions after first send (default: 2).",
        ),
        click.option(
            "--start-oid",
            default="1.3.6.1",
            metavar="OID",
            help="Subtree root OID (default: 1.3.6.1).",
        ),
        click.option(
            "--time-budget",
            type=float,
            default=None,
            metavar="SECS",
            help="Wall-time budget in seconds (default: unlimited).",
        ),
        click.option(
            "--give-up-after",
            type=click.IntRange(min=1),
            default=3,
            metavar="N",
            help="Consecutive misses before UNRESPONSIVE (default: 3).",
        ),
        click.option("-v", "--verbose", count=True, help="Increase verbosity: -v INFO, -vv DEBUG."),
    ]
    for option in reversed(options):
        f = option(f)
    return cast("F", f)


# ---------------------------------------------------------------------------
# Boundary validation: --start-oid, host, --label
# ---------------------------------------------------------------------------


def _resolve_common(
    host: str, start_oid_raw: str, label: str | None
) -> tuple[Oid, str, str | None] | int:
    """Parse --start-oid, resolve the host, and validate --label.

    Returns:
        (start_oid, resolved_ip, label) on success, or an exit code (2) on error.
    """
    try:
        start_oid = Oid.from_str(start_oid_raw)
    except ValueError as exc:
        print(f"error: invalid --start-oid {start_oid_raw!r}: {exc}", file=sys.stderr)
        return 2

    try:
        results = socket.getaddrinfo(host, None, socket.AF_INET)
        resolved_ip = cast("str", results[0][4][0])
    except OSError as exc:
        print(f"error: cannot resolve host {host!r}: {exc}", file=sys.stderr)
        return 2

    if label is not None and ("/" in label or "\\" in label or ".." in label):
        print(
            f"error: --label must not contain path separators or '..': {label!r}", file=sys.stderr
        )
        return 2

    return start_oid, resolved_ip, label


# ---------------------------------------------------------------------------
# v3 auth validation
# ---------------------------------------------------------------------------


def _validate_v3_auth(
    auth_proto_raw: str | None,
    auth_pass: str | None,
    priv_proto: str | None,
    priv_pass: str | None,
) -> tuple[AuthProto | None, str | None] | int:
    """Validate SNMPv3 auth arguments.

    Returns:
        (v3_auth_proto, v3_auth_pass) on success, or an exit code (2) on error.
    """
    v3_auth_proto: AuthProto | None = None
    v3_auth_pass: str | None = None

    if auth_proto_raw is not None:
        try:
            v3_auth_proto = AuthProto(auth_proto_raw.upper())
        except ValueError:
            print(
                f"error: --auth-proto must be one of {[p.value for p in AuthProto]}, "
                f"got {auth_proto_raw!r}",
                file=sys.stderr,
            )
            return 2

        if auth_pass is None:
            print(
                "error: --auth-pass is required when --auth-proto is set",
                file=sys.stderr,
            )
            return 2

        v3_auth_pass = auth_pass

    if priv_proto is not None or priv_pass is not None:
        print(
            "warning: privacy (--priv-proto, --priv-pass) is not yet supported and will be ignored",
            file=sys.stderr,
        )

    return (v3_auth_proto, v3_auth_pass)


# ---------------------------------------------------------------------------
# Logging + walk execution (shared tail of every version sub-command)
# ---------------------------------------------------------------------------


def _configure_logging(verbosity: int) -> None:
    if verbosity == 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
        force=True,
    )


def _run_and_summarize(
    resolved_ip: str,
    port: int,
    settings: WalkSettings,
    out: str,
    label: str | None,
    verbosity: int,
) -> int:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = label if label else "walk"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trace_path = out_dir / f"{prefix}-{timestamp}.oidtrace.jsonl.gz"

    log.info("trace path: %s", trace_path)

    extra_sinks: list[RecordSink] = []
    if verbosity == 0:
        extra_sinks.append(_ProgressSink())

    # Ctrl-C falls through to terminal summary; the INTERRUPTED summary is
    # already flushed by walk_with_transport before KeyboardInterrupt propagates.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run_walk(
                resolved_ip,
                port,
                settings=settings,
                path=trace_path,
                label=label,
                sinks=extra_sinks,
            )
        )

    _print_summary(trace_path)
    return 0


# ---------------------------------------------------------------------------
# Command tree
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True, no_args_is_help=False)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """OIDTrace: record SNMP walks to structured trace files."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help(), err=True)
        ctx.exit(2)


@cli.group(invoke_without_command=True, no_args_is_help=False)
@click.pass_context
def walk(ctx: click.Context) -> None:
    """Walk an SNMP agent and record to a trace file."""
    if ctx.invoked_subcommand is None:
        click.echo("usage: oidtrace walk {v1,v2c,v3} ...", err=True)
        ctx.exit(2)


@walk.command("v1")
@_walk_options
@click.option("--community", default="public", help="SNMP v1 community string (default: public).")
def walk_v1(
    host: str,
    port: int,
    out: str,
    label: str | None,
    timeout: float,
    retries: int,
    start_oid: str,
    time_budget: float | None,
    give_up_after: int,
    verbose: int,
    community: str,
) -> int:
    """SNMP v1 walk."""
    _configure_logging(verbose)
    common = _resolve_common(host, start_oid, label)
    if isinstance(common, int):
        return common
    parsed_oid, resolved_ip, label = common
    log.info("resolved %s -> %s", host, resolved_ip)

    settings = WalkSettings(
        timeout_s=timeout,
        retries=retries,
        start_oid=parsed_oid,
        time_budget_s=time_budget,
        give_up_after=give_up_after,
        community=community.encode(),
        snmp_version="1",
    )
    return _run_and_summarize(resolved_ip, port, settings, out, label, verbose)


@walk.command("v2c")
@_walk_options
@click.option("--community", default="public", help="SNMP v2c community string (default: public).")
@click.option(
    "--bulk-size",
    type=click.IntRange(min=1),
    default=10,
    metavar="N",
    help="GetBulk max-repetitions (default: 10).",
)
def walk_v2c(
    host: str,
    port: int,
    out: str,
    label: str | None,
    timeout: float,
    retries: int,
    start_oid: str,
    time_budget: float | None,
    give_up_after: int,
    verbose: int,
    community: str,
    bulk_size: int,
) -> int:
    """SNMP v2c walk."""
    _configure_logging(verbose)
    common = _resolve_common(host, start_oid, label)
    if isinstance(common, int):
        return common
    parsed_oid, resolved_ip, label = common
    log.info("resolved %s -> %s", host, resolved_ip)

    settings = WalkSettings(
        bulk_size=bulk_size,
        timeout_s=timeout,
        retries=retries,
        start_oid=parsed_oid,
        time_budget_s=time_budget,
        give_up_after=give_up_after,
        community=community.encode(),
    )
    return _run_and_summarize(resolved_ip, port, settings, out, label, verbose)


@walk.command("v3")
@_walk_options
@click.option("--user", required=True, help="SNMPv3 username.")
@click.option("--auth-proto", default=None, help="Auth protocol (MD5, SHA, or SHA-256).")
@click.option("--auth-pass", default=None, help="Auth passphrase.")
@click.option("--priv-proto", default=None, help="Privacy protocol (e.g. AES).")
@click.option("--priv-pass", default=None, help="Privacy passphrase.")
def walk_v3(
    host: str,
    port: int,
    out: str,
    label: str | None,
    timeout: float,
    retries: int,
    start_oid: str,
    time_budget: float | None,
    give_up_after: int,
    verbose: int,
    user: str,
    auth_proto: str | None,
    auth_pass: str | None,
    priv_proto: str | None,
    priv_pass: str | None,
) -> int:
    """SNMP v3 walk."""
    _configure_logging(verbose)
    common = _resolve_common(host, start_oid, label)
    if isinstance(common, int):
        return common
    parsed_oid, resolved_ip, label = common
    log.info("resolved %s -> %s", host, resolved_ip)

    auth_result = _validate_v3_auth(auth_proto, auth_pass, priv_proto, priv_pass)
    if isinstance(auth_result, int):
        return auth_result
    v3_auth_proto, v3_auth_pass = auth_result

    settings = WalkSettings(
        bulk_size=10,
        timeout_s=timeout,
        retries=retries,
        start_oid=parsed_oid,
        time_budget_s=time_budget,
        give_up_after=give_up_after,
        snmp_version="3",
        v3_user=user,
        v3_auth_proto=v3_auth_proto,
        v3_auth_pass=v3_auth_pass,
    )
    return _run_and_summarize(resolved_ip, port, settings, out, label, verbose)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    try:
        return cli.main(args=argv, prog_name="oidtrace", standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------


def _print_summary(trace_path: Path) -> None:
    """Print the Summary record from the trace to stdout."""
    summary = None
    for record in read_trace(trace_path):
        if isinstance(record, Summary):
            summary = record
            break

    if summary is None:
        print("(no summary in trace)", flush=True)
        return

    print(f"end_reason  : {summary.end_reason}", flush=True)
    print(f"exchanges   : {summary.exchanges}", flush=True)
    print(f"oids_seen   : {summary.oids_seen}", flush=True)

    counts = summary.violation_counts
    if counts:
        print(f"violations  : {counts}", flush=True)
    else:
        print("violations  : none", flush=True)

    print(f"trace       : {trace_path}", flush=True)
