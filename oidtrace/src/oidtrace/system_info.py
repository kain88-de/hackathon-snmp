"""System-info allowlist (trace-format.md § 4.2): OIDs and value decoding.

Encoding the Get request reuses codec.encode_get/encode_v3_get directly (same
call shape as every other request in walker.py) — this module owns only the
allowlist itself and turning its varbinds into SystemInfo.values, the one
genuinely new kind of logic here: nothing else in oidtrace decodes a value's
bytes back into a native str/int, since ordinary Exchange records deliberately
keep values as opaque (vtype, vlen) only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from oidtrace.ber import decode_int, decode_oid
from oidtrace.codec import EXCEPTION_TAGS
from oidtrace.oid import Oid

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.codec import Varbind

_OCTET_STRING_TAG = 0x04
_OBJECT_IDENTIFIER_TAG = 0x06
_TIME_TICKS_TAG = 0x43

# sysDescr.0, sysObjectID.0, sysUpTime.0, sysName.0 — trace-format.md § 4.2.
SYSTEM_INFO_ALLOWLIST: tuple[Oid, ...] = (
    Oid.from_str("1.3.6.1.2.1.1.1.0"),
    Oid.from_str("1.3.6.1.2.1.1.2.0"),
    Oid.from_str("1.3.6.1.2.1.1.3.0"),
    Oid.from_str("1.3.6.1.2.1.1.5.0"),
)


def decode_values(varbinds: Sequence[Varbind]) -> dict[str, str | int]:
    """Decode allowlisted varbinds into a SystemInfo.values mapping.

    A varbind the device doesn't have (NoSuchObject/NoSuchInstance) or whose
    tag isn't one the allowlist actually uses is skipped, not fabricated —
    "only allowlisted OIDs appear" applies per-OID.
    """
    values: dict[str, str | int] = {}
    for vb in varbinds:
        decoded = _decode_allowlist_value(vb.tag, vb.value)
        if decoded is not None:
            values[str(vb.oid)] = decoded
    return values


def _decode_allowlist_value(tag: int, raw: bytes) -> str | int | None:
    """Decode a BER value for the system-info allowlist's known types.

    Returns None for exception tags or any tag outside this narrow vocabulary
    (OctetString, ObjectIdentifier, TimeTicks — the only types the four
    allowlisted OIDs use) so the caller omits the OID rather than guessing.

    Deliberately narrow: a general BER-value decoder (any vtype -> str | int)
    would look almost identical but belongs in codec.py, next to _TAG_NAMES,
    for reuse beyond system_info (e.g. the not-yet-built `show` subcommand).
    """
    if tag in EXCEPTION_TAGS:
        return None
    if tag == _OCTET_STRING_TAG:
        return raw.decode("utf-8", errors="replace")
    if tag == _OBJECT_IDENTIFIER_TAG:
        return str(decode_oid(raw))
    if tag == _TIME_TICKS_TAG:
        return decode_int(raw)
    return None
