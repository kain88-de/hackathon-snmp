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

# Classes
_ = Violation
_ = EndReason
_ = EventKind
_ = AttemptError

# Violation members
REQUEST_ID_MISMATCH = Violation.REQUEST_ID_MISMATCH
OID_NOT_INCREASING = Violation.OID_NOT_INCREASING
MISSING_END_OF_MIB = Violation.MISSING_END_OF_MIB
DUPLICATE_RESPONSE = Violation.DUPLICATE_RESPONSE
MALFORMED_BER = Violation.MALFORMED_BER
RESPONSE_FROM_UNEXPECTED_SOURCE = Violation.RESPONSE_FROM_UNEXPECTED_SOURCE

# EndReason members
COMPLETED = EndReason.COMPLETED
UNRESPONSIVE = EndReason.UNRESPONSIVE
INTERRUPTED = EndReason.INTERRUPTED
TIME_BUDGET_EXCEEDED = EndReason.TIME_BUDGET_EXCEEDED
OID_LOOP = EndReason.OID_LOOP

# EventKind members
OID_LOOP_DETECTED = EventKind.OID_LOOP_DETECTED
WALK_ABORTED_BY_USER = EventKind.WALK_ABORTED_BY_USER

# AttemptError members
ICMP_PORT_UNREACHABLE = AttemptError.ICMP_PORT_UNREACHABLE
ICMP_HOST_UNREACHABLE = AttemptError.ICMP_HOST_UNREACHABLE
SEND_FAILED = AttemptError.SEND_FAILED

# cli entry point — referenced in pyproject.toml [project.scripts], not called
# directly in Python source.
# from oidtrace.cli import main
# _ = main  # uncomment once oidtrace/cli.py exists
