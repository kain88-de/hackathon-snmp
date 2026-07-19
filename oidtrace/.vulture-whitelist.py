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

# codec.encode_response, encode_getnext — the emulator seed and SNMP v1 GetNext request
# encoder (tests/support/emulator.py and unit tests consume them; vulture only scans src/).
from oidtrace.codec import encode_getnext, encode_response

_ = encode_response
_ = encode_getnext

# v3 codec symbols — used by emulator (Task 5), walker (Task 7), and CLI (Task 8);
# vulture only scans src/ so test and support usages are invisible to it.
from oidtrace.codec import (
    PDU_REPORT,
    decode_v3_message,
    encode_v3_discovery,
    encode_v3_getbulk,
    encode_v3_response,
)

_ = PDU_REPORT
_ = decode_v3_message
_ = encode_v3_discovery
_ = encode_v3_getbulk
_ = encode_v3_response

# records.system_info_record — format-completeness stub; v1 walker never calls
# it (out of scope per plan).  Kept public for future hosts.
from oidtrace.records import system_info_record

_ = system_info_record

# cli entry point — referenced in pyproject.toml [project.scripts], not called
# directly in Python source.
from oidtrace.cli import main

_ = main

# Click command callbacks — dispatched by name at runtime via the walk group,
# never called directly in Python source.
from oidtrace.cli import walk_v1, walk_v2c, walk_v3

_ = walk_v1
_ = walk_v2c
_ = walk_v3

# auth/codec SNMPv3 symbols — used by emulator (authNoPriv), walker, and CLI;
# vulture only scans src/ so test/support usages are invisible to it.
from oidtrace.auth import AuthProto, password_to_key
from oidtrace.codec import authenticate_msg, verify_auth

_ = password_to_key
_ = authenticate_msg
_ = verify_auth

# AuthProto.SHA256 — used in tests and robot library (outside src/).
# AuthProto.key_length — used by emulator/walker/codec in future phases.
_ = AuthProto.SHA256
_ = AuthProto.key_length

# _SnmpProtocol asyncio callback methods — called by asyncio internals
# (event loop), not by Python source directly.  These are the standard
# DatagramProtocol interface mandated by asyncio.
from oidtrace.transport import _SnmpProtocol  # noqa: PLC2701

_ = _SnmpProtocol.connection_made
_ = _SnmpProtocol.datagram_received
_ = _SnmpProtocol.error_received
_ = _SnmpProtocol.connection_lost
