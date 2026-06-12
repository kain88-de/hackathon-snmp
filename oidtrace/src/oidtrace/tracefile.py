"""gzip-JSONL I/O for OIDTrace records.

TraceWriter: single gzip stream opened once; write() appends one JSON line and
flushes immediately (per-record durability -- a Ctrl-C after write() means the
record is already readable by an independent reader).

read_trace: yields validated TraceRecord instances for every complete line;
stops quietly when the stream is truncated (EOFError, gzip.BadGzipFile, or a
partial final line without a trailing newline).  A complete line that fails
pydantic validation is allowed to raise -- that is our own bug, not a tolerance
case.
"""

from __future__ import annotations

import gzip
from typing import TYPE_CHECKING

from traceformat import TraceRecord, dump_record, parse_record

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class TraceWriter:
    """Append-only gzip-JSONL writer with per-record durability.

    Opens the gzip stream on construction and keeps it open until close() /
    __exit__.  Every write() flushes to the underlying file so that an
    independent reader (or a post-Ctrl-C recovery) can see the record without
    waiting for close().
    """

    def __init__(self, path: Path) -> None:
        self._gz = gzip.open(path, "wt", encoding="utf-8")  # noqa: SIM115

    def write(self, record: TraceRecord) -> None:
        """Append one JSON line and flush."""
        self._gz.write(dump_record(record) + "\n")
        self._gz.flush()

    def close(self) -> None:
        self._gz.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()


def read_trace(path: Path) -> Iterator[TraceRecord]:
    """Yield validated TraceRecord instances from a gzip-JSONL trace file.

    Stops quietly at truncation (EOFError, gzip.BadGzipFile) or a partial
    final line (no trailing newline).  Raises on complete lines that fail
    pydantic validation -- that signals a producer bug, not a device quirk.
    """
    try:
        f = gzip.open(path, "rt", encoding="utf-8")  # noqa: SIM115
    except (EOFError, gzip.BadGzipFile):
        return
    try:
        while True:
            try:
                line = f.readline()
            except (EOFError, gzip.BadGzipFile):
                # Truncated mid-stream -- stop quietly.
                break
            if not line:
                # readline() returns "" at EOF (clean end of stream).
                break
            if not line.endswith("\n"):
                # Partial final line without trailing newline -- skip silently.
                break
            stripped = line.rstrip("\n")
            if stripped:
                yield parse_record(stripped)
    finally:
        f.close()
