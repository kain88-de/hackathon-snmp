"""Vulture dead-code whitelist for oidtrace.

Add entries here when vulture flags a symbol that is genuinely used but
not statically reachable (e.g. entry points, protocol implementations,
pytest fixtures, exception handler args).

Vulture recognises any name that *appears* in a scanned file, so the pattern
here is to mention the name in a comment and then assign it to _ so both
linters and vulture are satisfied.

Entries will grow as modules are added.  Prefix each block with a comment
explaining why the symbol is whitelisted.
"""

from traceformat.vocab import AttemptError, EndReason, EventKind, Violation

# traceformat.vocab producer vocabulary — the enums and their members are the
# published API consumed by oidtrace modules that don't exist yet in this
# scaffold.  Whitelisted here so the dead-code gate passes at task 1;
# remove entries as each module that imports them is added.

# AttemptError — class and members not yet used in production code (walker is Task 11).
_ = AttemptError
ICMP_PORT_UNREACHABLE = AttemptError.ICMP_PORT_UNREACHABLE
ICMP_HOST_UNREACHABLE = AttemptError.ICMP_HOST_UNREACHABLE
SEND_FAILED = AttemptError.SEND_FAILED

# Violation members still unused by production code (violations.py uses the
# class directly; these members are not yet referenced elsewhere)
MISSING_END_OF_MIB = Violation.MISSING_END_OF_MIB
MALFORMED_BER = Violation.MALFORMED_BER
RESPONSE_FROM_UNEXPECTED_SOURCE = Violation.RESPONSE_FROM_UNEXPECTED_SOURCE

# EndReason members — enum class used by records.py; individual members whitelisted
# until the walker adds them as call-site values.
COMPLETED = EndReason.COMPLETED
UNRESPONSIVE = EndReason.UNRESPONSIVE
INTERRUPTED = EndReason.INTERRUPTED
TIME_BUDGET_EXCEEDED = EndReason.TIME_BUDGET_EXCEEDED
OID_LOOP = EndReason.OID_LOOP

# EventKind members — enum class used by records.py; individual members whitelisted.
OID_LOOP_DETECTED = EventKind.OID_LOOP_DETECTED
WALK_ABORTED_BY_USER = EventKind.WALK_ABORTED_BY_USER

# oid.Oid public API — from_str is the constructor (used at call sites that
# don't exist yet in this task; in_subtree is the main behavioral method).
# Both are contract-public names per the plan.
from oidtrace.oid import Oid

_ = Oid.from_str
_ = Oid.in_subtree

# ber.py decode functions — consumed by codec decode side (Task 5).
# Whitelisted until codec.py decode is added.
from oidtrace.ber import decode_int, decode_oid, read_tlv

_ = read_tlv
_ = decode_int
_ = decode_oid

# codec.py public API — consumed by walker (Task 11) and emulator (Task 9).
# Whitelisted until those modules are added.
from oidtrace.codec import (
    EXCEPTION_TAGS,
    Malformed,
    Message,
    PDU_GETBULK,
    PDU_RESPONSE,
    Varbind,
    decode_message,
    encode_getbulk,
    encode_response,
)

_ = PDU_GETBULK
_ = PDU_RESPONSE
_ = encode_getbulk
# encode_response and decode_message are consumed by tests/support/emulator.py;
# vulture only scans src/, so they stay whitelisted here until the walker uses them.
_ = encode_response
_ = decode_message
_ = EXCEPTION_TAGS
_ = Varbind.vtype
_ = Varbind.vlen
_ = Message
_ = Malformed.error

# violations.check_exchange — consumed by tests and the walker (not yet added).
from oidtrace.violations import check_exchange

_ = check_exchange

# records.py public builders — consumed by the walker (Task 11).
# Whitelisted until walker.py is added.
from oidtrace.records import (
    event_record,
    exchange_record,
    header_record,
    summary_record,
    system_info_record,
)

_ = header_record
_ = exchange_record
_ = event_record
_ = summary_record
_ = system_info_record

# tracefile.py public API — TraceWriter and read_trace are consumed by walker
# (Task 11) and tests.  TraceWriter.close() is a public method callable outside
# a context manager (e.g. post-Ctrl-C cleanup in tests).
from oidtrace.tracefile import TraceWriter, read_trace

_ = TraceWriter.close
_ = read_trace

# walker.py public entry point — called by CLI (not yet added) and integration tests;
# vulture only scans src/ so it can't see the test call sites.
from oidtrace.walker import (
    RecordSink,
    WalkSettings,
    WalkStats,
    run_walk,
    walk_records,
    walk_with_transport,
)

_ = run_walk
_ = walk_records
_ = walk_with_transport
_ = WalkSettings
_ = WalkStats
_ = RecordSink

# cli entry point — referenced in pyproject.toml [project.scripts], not called
# directly in Python source.
# from oidtrace.cli import main
# _ = main  # uncomment once oidtrace/cli.py exists

# transport.py public API — Transport protocol and UdpTransport are consumed by
# integration tests and will be consumed by walker (Task 11).
# _SnmpProtocol callback methods (connection_made, datagram_received,
# error_received, connection_lost) are called by asyncio internals, not by
# Python source directly.
from oidtrace.transport import ExchangeIO, Transport, UdpTransport

_ = Transport
_ = Transport.exchange
_ = UdpTransport.create
_ = UdpTransport.exchange
_ = ExchangeIO

# _SnmpProtocol asyncio callback methods — called by asyncio internals
# (event loop), not by Python source directly.  These are the standard
# DatagramProtocol interface mandated by asyncio.
from oidtrace.transport import _SnmpProtocol  # noqa: PLC2701

_ = _SnmpProtocol.connection_made
_ = _SnmpProtocol.datagram_received
_ = _SnmpProtocol.error_received
_ = _SnmpProtocol.connection_lost
