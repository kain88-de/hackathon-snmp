"""CLI entry point for oidtrace.

Subcommand: walk

    oidtrace walk <host> [options]

Operator errors (bad DNS, bad --start-oid) exit 2 with a stderr message and
no trace file written.

Logging is configured only here (libraries never configure handlers):
  default    WARNING  + \\r progress sink on stderr
  -v         INFO     (progress suppressed; logs supersede)
  -vv        DEBUG    (progress suppressed)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from traceformat import TraceRecord

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
            # Clear the progress line
            sys.stderr.write("\r")
            sys.stderr.flush()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oidtrace",
        description="OIDTrace: record SNMP walks to structured trace files.",
    )
    sub = parser.add_subparsers(dest="subcommand")

    walk = sub.add_parser("walk", help="Walk an SNMP agent and record to a trace file.")
    walk.add_argument("host", help="Target hostname or IP address.")
    walk.add_argument("--port", type=int, default=161, help="UDP port (default: 161).")
    walk.add_argument("--out", default=".", help="Output directory (default: current dir).")
    walk.add_argument("--label", default=None, help="Human label; used in filename and header.")
    walk.add_argument(
        "--bulk-size",
        type=int,
        default=10,
        metavar="N",
        help="GetBulk max-repetitions (default: 10).",
    )
    walk.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        metavar="SECS",
        help="Per-attempt timeout in seconds (default: 2.0).",
    )
    walk.add_argument(
        "--retries", type=int, default=2, help="Retransmissions after first send (default: 2)."
    )
    walk.add_argument(
        "--start-oid", default="1.3.6.1", metavar="OID", help="Subtree root OID (default: 1.3.6.1)."
    )
    walk.add_argument(
        "--time-budget",
        type=float,
        default=None,
        metavar="SECS",
        help="Wall-time budget in seconds (default: unlimited).",
    )
    walk.add_argument(
        "--community", default="public", help="SNMP v2c community string (default: public)."
    )
    walk.add_argument(
        "--give-up-after",
        type=int,
        default=3,
        metavar="N",
        dest="give_up_after",
        help="Consecutive misses before UNRESPONSIVE (default: 3).",
    )
    walk.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase verbosity: -v INFO, -vv DEBUG."
    )

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand != "walk":
        parser.print_help(sys.stderr)
        return 2

    # --- Configure logging (only here, never in libraries) ---
    verbosity: int = args.verbose
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:  # noqa: PLR2004
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
        force=True,
    )

    # --- Validate --start-oid BEFORE DNS (fail fast on cheap check) ---
    from oidtrace.oid import Oid  # noqa: PLC0415

    try:
        start_oid = Oid.from_str(args.start_oid)
    except ValueError as exc:
        print(f"error: invalid --start-oid {args.start_oid!r}: {exc}", file=sys.stderr)
        return 2

    # --- DNS resolution (operator error if it fails) ---
    host: str = args.host
    try:
        results = socket.getaddrinfo(host, None, socket.AF_INET)
        resolved_ip = cast("str", results[0][4][0])
    except OSError as exc:
        print(f"error: cannot resolve host {host!r}: {exc}", file=sys.stderr)
        return 2

    log.info("resolved %s -> %s", host, resolved_ip)

    # --- Build trace path ---
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    label: str | None = args.label
    prefix = label if label else "walk"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trace_path = out_dir / f"{prefix}-{timestamp}.oidtrace.jsonl.gz"

    log.info("trace path: %s", trace_path)

    # --- Build settings ---
    from oidtrace.walker import WalkSettings, run_walk  # noqa: PLC0415

    settings = WalkSettings(
        bulk_size=args.bulk_size,
        timeout_s=args.timeout,
        retries=args.retries,
        start_oid=start_oid,
        time_budget_s=args.time_budget,
        give_up_after=args.give_up_after,
        community=args.community.encode(),
    )

    # --- Progress sink (only at default verbosity) ---
    extra_sinks = []
    if verbosity == 0:
        extra_sinks.append(_ProgressSink())

    # --- Run the walk ---
    # Ctrl-C falls through to terminal summary; the INTERRUPTED summary is
    # already flushed by walk_with_transport before KeyboardInterrupt propagates.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run_walk(
                resolved_ip,
                args.port,
                settings=settings,
                path=trace_path,
                label=label,
                sinks=extra_sinks,
            )
        )

    # --- Terminal summary from the trace ---
    _print_summary(trace_path)
    return 0


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------


def _print_summary(trace_path: Path) -> None:
    """Print the Summary record from the trace to stdout."""
    from oidtrace.tracefile import read_trace  # noqa: PLC0415

    summary = None
    for record in read_trace(trace_path):
        if record.type == "summary":
            summary = record
            break

    if summary is None:
        print("(no summary in trace)", flush=True)
        return

    print(f"end_reason  : {summary.end_reason}", flush=True)  # type: ignore[union-attr]
    print(f"exchanges   : {summary.exchanges}", flush=True)  # type: ignore[union-attr]
    print(f"oids_seen   : {summary.oids_seen}", flush=True)  # type: ignore[union-attr]

    violations = getattr(summary, "violations", None)
    if violations:
        print(f"violations  : {violations}", flush=True)

    print(f"trace       : {trace_path}", flush=True)
