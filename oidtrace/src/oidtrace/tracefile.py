"""gzip-JSONL I/O for OIDTrace records.

TraceWriter: single gzip stream opened once; write() appends one JSON line;
close() flushes.  read_trace tolerates truncation so interrupted walks are
readable up to the last complete line.
"""

from __future__ import annotations

import gzip
from typing import TYPE_CHECKING

from traceformat import TraceRecord, dump_record, parse_record

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class TraceWriter:
    """Append-only gzip-JSONL writer.

    Opens the gzip stream on construction and keeps it open until close() /
    __exit__.  Records are buffered in the gzip stream; close() flushes.
    read_trace tolerates truncated files so an interrupted walk is still
    readable up to the last complete line.
    """

    def __init__(self, path: Path) -> None:
        self._gz = gzip.open(path, "wt", encoding="utf-8")  # noqa: SIM115

    def write(self, record: TraceRecord) -> None:
        self._gz.write(dump_record(record) + "\n")

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
    f = gzip.open(path, "rt", encoding="utf-8")  # noqa: SIM115
    try:
        while True:
            try:
                line = f.readline()
            except (EOFError, gzip.BadGzipFile):
                break
            if not line:
                break
            if not line.endswith("\n"):
                break
            stripped = line.rstrip("\n")
            if stripped:
                yield parse_record(stripped)
    finally:
        f.close()
