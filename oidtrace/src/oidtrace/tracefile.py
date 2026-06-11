"""Gzipped-JSONL trace I/O for oidtrace.

One compact JSON object per line.  The writer flushes after every record so
that each write is durable without a close() — crash/Ctrl-C safe.
The reader tolerates truncation: EOFError, gzip.BadGzipFile, and partial
final lines are silently swallowed.
"""

from __future__ import annotations

import gzip
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from types import TracebackType


class TraceWriter:
    """Append-only writer for a gzipped JSONL trace file."""

    def __init__(self, path: Path) -> None:
        self._gz = gzip.open(path, "ab")  # noqa: SIM115

    def write(self, record: dict) -> None:  # type: ignore[type-arg]
        line = json.dumps(record, separators=(",", ":")) + "\n"
        self._gz.write(line.encode())
        self._gz.flush()

    def close(self) -> None:
        self._gz.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def read_trace(path: Path) -> Iterator[dict]:  # type: ignore[type-arg]
    """Yield records from a gzipped JSONL trace file.

    Stops quietly at truncation — EOFError, gzip.BadGzipFile, and incomplete
    final lines (no trailing newline) are all swallowed.
    """
    try:
        with gzip.open(path, "rb") as gz:
            for raw in gz:
                line = raw.decode()
                if not line.endswith("\n"):
                    # Partial line — truncated; stop here
                    return
                stripped = line.rstrip("\n")
                if stripped:
                    yield json.loads(stripped)
    except (EOFError, gzip.BadGzipFile):
        return
