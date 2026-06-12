"""Vulture dead-code whitelist for oidtrace.

Add entries here when vulture flags a symbol that is genuinely used but
not statically reachable (e.g. entry points, protocol implementations,
pytest fixtures, exception handler args).

Vulture recognises any name that *appears* in a scanned file, so the pattern
here is to mention the name in a comment and then assign it to _ so both
linters and vulture are satisfied.
"""

from traceformat.vocab import EventKind, Violation

# Violation members with no v1 producer yet (kept for future tasks).
MISSING_END_OF_MIB = Violation.MISSING_END_OF_MIB
RESPONSE_FROM_UNEXPECTED_SOURCE = Violation.RESPONSE_FROM_UNEXPECTED_SOURCE

# EventKind member with no v1 producer yet (kept for future tasks).
WALK_ABORTED_BY_USER = EventKind.WALK_ABORTED_BY_USER

# codec.encode_response — the emulator seed (tests/support/emulator.py and
# unit tests consume it heavily; vulture only scans src/).
from oidtrace.codec import encode_response

_ = encode_response

# records.system_info_record — format-completeness stub; v1 walker never calls
# it (out of scope per plan).  Kept public for future hosts.
from oidtrace.records import system_info_record

_ = system_info_record

# cli entry point — referenced in pyproject.toml [project.scripts], not called
# directly in Python source.
from oidtrace.cli import main

_ = main

# _SnmpProtocol asyncio callback methods — called by asyncio internals
# (event loop), not by Python source directly.  These are the standard
# DatagramProtocol interface mandated by asyncio.
from oidtrace.transport import _SnmpProtocol  # noqa: PLC2701

_ = _SnmpProtocol.connection_made
_ = _SnmpProtocol.datagram_received
_ = _SnmpProtocol.error_received
_ = _SnmpProtocol.connection_lost
