"""SNMP v2c message codec — encode side.

Scope: pure bytes-in / bytes-out encoding of GetBulk requests and Response
messages.  No I/O, no decode (that is Task 5).

SNMPv2c message structure (BER SEQUENCE):
    version     INTEGER 1           (version-2c)
    community   OCTET STRING
    data        PDU

GetBulk PDU (tag 0xA5):
    request-id        INTEGER
    non-repeaters     INTEGER
    max-repetitions   INTEGER
    variable-bindings SEQUENCE OF SEQUENCE(OID, NULL)

Response PDU (tag 0xA2):
    request-id        INTEGER
    error-status      INTEGER
    error-index       INTEGER
    variable-bindings SEQUENCE OF SEQUENCE(OID, TLV(tag, value_bytes))
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from oidtrace.ber import encode_int, encode_oid, tlv

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.oid import Oid

# PDU context-class tags (application, constructed)
PDU_GETBULK: int = 0xA5
PDU_RESPONSE: int = 0xA2


def encode_getbulk(
    request_id: int,
    oid: Oid,
    non_repeaters: int,
    max_repetitions: int,
    community: bytes = b"public",
) -> bytes:
    """Encode an SNMPv2c GetBulk request.

    Returns a complete BER-encoded SNMP message.

    Args:
        request_id: Integer request identifier.
        oid: The start OID for the bulk walk (single varbind, NULL value).
        non_repeaters: Number of non-repeating varbinds (typically 0).
        max_repetitions: Maximum repetitions per varbind.
        community: Community string (default b"public").
    """
    varbind_list = tlv(0x30, tlv(0x30, encode_oid(oid) + tlv(0x05, b"")))
    pdu = tlv(
        PDU_GETBULK,
        encode_int(request_id)
        + encode_int(non_repeaters)
        + encode_int(max_repetitions)
        + varbind_list,
    )
    return tlv(
        0x30,
        encode_int(1) + tlv(0x04, community) + pdu,
    )


def encode_response(
    request_id: int,
    varbinds: Sequence[tuple[Oid, int, bytes]],
    community: bytes = b"public",
    error_status: int = 0,
    error_index: int = 0,
) -> bytes:
    """Encode an SNMPv2c Response message (used by the emulator).

    Args:
        request_id: Integer request identifier.
        varbinds: Sequence of (oid, tag, value_bytes) tuples.
            The tag is the BER tag for the value (e.g. 0x04 for OctetString,
            0x41 for Counter32).  value_bytes is the raw value payload.
        community: Community string (default b"public").
        error_status: Error status integer (default 0 = noError).
        error_index: Error index integer (default 0).
    """
    encoded_vbs = b"".join(
        tlv(0x30, encode_oid(oid) + tlv(tag, value_bytes)) for oid, tag, value_bytes in varbinds
    )
    pdu = tlv(
        PDU_RESPONSE,
        encode_int(request_id)
        + encode_int(error_status)
        + encode_int(error_index)
        + tlv(0x30, encoded_vbs),
    )
    return tlv(
        0x30,
        encode_int(1) + tlv(0x04, community) + pdu,
    )
