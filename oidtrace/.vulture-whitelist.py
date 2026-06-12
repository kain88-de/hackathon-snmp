"""Vulture whitelist: names that are alive by contract, not by call graph.

Each entry documents WHY it is not dead code.
"""

from oidtrace import cli, codec, records, tracefile, transport
from traceformat import vocab

cli.main  # console-script entry point (pyproject [project.scripts])
codec.encode_response  # consumed by the test emulator (designated OIDEmu seed)
records.system_info_record  # format completeness; post-MVP system-info capture
transport._UdpProtocol.datagram_received  # asyncio.DatagramProtocol callback
transport._UdpProtocol.error_received  # asyncio.DatagramProtocol callback
vocab.EventKind.WALK_ABORTED_BY_USER  # format vocabulary; walker does not emit it in v1

_ = tracefile.TraceWriter.__exit__  # exc_type/exc_val/exc_tb are protocol params
