"""CLI entry point for oidtrace."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from traceformat.models import Exchange, Summary

from oidtrace.oid import Oid
from oidtrace.tracefile import read_trace
from oidtrace.walker import WalkSettings, run_walk

if TYPE_CHECKING:
    from traceformat import TraceRecord

logger = logging.getLogger(__name__)


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _resolve_host(host: str) -> str | None:
    """Return the resolved IPv4 address, or None (and print to stderr) on failure."""
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
        return str(infos[0][4][0])
    except socket.gaierror as exc:
        print(f"error: cannot resolve host {host!r}: {exc}", file=sys.stderr)
        return None


def _progress_sink(record: TraceRecord) -> None:
    if isinstance(record, Exchange):
        print(f"\r{record.seq} exchanges...", end="", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oidtrace")
    sub = parser.add_subparsers(dest="command")

    walk_p = sub.add_parser("walk")
    walk_p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v INFO, -vv DEBUG)",
    )
    walk_p.add_argument("host")
    walk_p.add_argument("--port", type=int, default=161)
    walk_p.add_argument("--out", default=".")
    walk_p.add_argument("--label")
    walk_p.add_argument("--bulk-size", type=int, default=10)
    walk_p.add_argument("--timeout", type=float, default=2.0)
    walk_p.add_argument("--retries", type=int, default=2)
    walk_p.add_argument("--start-oid", default="1.3.6.1")
    walk_p.add_argument("--time-budget", type=float, default=None)
    walk_p.add_argument("--community", default="public", help="SNMP community string")
    return parser


def _configure_logging(verbosity: int) -> None:
    """Configure root logger: WARNING / INFO / DEBUG by verbosity count."""
    log_level = (
        logging.WARNING if verbosity == 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    )
    logging.basicConfig(
        level=log_level,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure logging: WARNING (default) / INFO (-v) / DEBUG (-vv)
    verbosity: int = args.verbose
    _configure_logging(verbosity)

    if args.command != "walk":
        parser.print_help(sys.stderr)
        return 2

    # Validate start-oid before touching the filesystem
    try:
        start_oid = Oid.from_str(args.start_oid)
    except ValueError as exc:
        print(f"error: invalid --start-oid {args.start_oid!r}: {exc}", file=sys.stderr)
        return 2

    # DNS fail-fast (IPv4)
    resolved_ip = _resolve_host(args.host)
    if resolved_ip is None:
        return 2
    logger.info("resolved %s -> %s", args.host, resolved_ip)

    # Build output path
    label = args.label or "walk"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    trace_path = out_dir / f"{label}-{stamp}.oidtrace.jsonl.gz"

    community = args.community.encode()

    settings = WalkSettings(
        bulk_size=args.bulk_size,
        timeout_s=args.timeout,
        retries=args.retries,
        start_oid=start_oid,
        time_budget_s=args.time_budget,
        community=community,
    )

    # Progress sink only at default verbosity (logs supersede it under -v)
    sinks = [] if verbosity > 0 else [_progress_sink]

    # The INTERRUPTED summary is already flushed to the file on Ctrl-C; suppress
    # and fall through so the operator still gets the terminal summary + trace path.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run_walk(
                args.host,
                args.port,
                settings=settings,
                path=trace_path,
                label=args.label,
                sinks=sinks,
            )
        )

    logger.info("trace written to %s", trace_path)

    if verbosity == 0:
        print(file=sys.stderr)  # newline after \r progress

    # Terminal summary
    summary: Summary | None = None
    exchange_count = 0
    for record in read_trace(trace_path):
        if isinstance(record, Summary):
            summary = record
            exchange_count = record.exchanges

    if summary is not None:
        violations = dict(summary.violation_counts)
        viol_str = ", ".join(f"{k}={v}" for k, v in violations.items()) or "none"
        print(f"end_reason:   {summary.end_reason}")
        print(f"exchanges:    {exchange_count}")
        print(f"oids_seen:    {summary.oids_seen}")
        print(f"violations:   {viol_str}")
        print(f"trace:        {trace_path}")

    return 0
