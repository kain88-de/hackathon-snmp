"""SNMPv2c message encoding — encode side only (decode in Task 5).

Uses oidtrace.ber for all BER primitives; no I/O.
"""

from collections.abc import Sequence

from oidtrace.ber import encode_int, encode_oid, tlv
from oidtrace.oid import Oid

# PDU type tags (context-constructed, class 0xA0)
_TAG_GET_BULK = 0xA5
_TAG_RESPONSE = 0xA2


def _pdu(tag: int, request_id: int, field1: int, field2: int, varbind_list: bytes) -> bytes:
    """Encode a PDU with two integer fields before the varbind list.

    For GetBulk: field1=non_repeaters, field2=max_repetitions.
    For Response: field1=error_status, field2=error_index.
    """
    body = (
        encode_int(request_id) + encode_int(field1) + encode_int(field2) + tlv(0x30, varbind_list)
    )
    return tlv(tag, body)


def _message(pdu: bytes, community: bytes) -> bytes:
    """Wrap a PDU in a v2c SNMP message: SEQ(version=1, community, pdu)."""
    return tlv(0x30, encode_int(1) + tlv(0x04, community) + pdu)


def encode_getbulk(
    request_id: int,
    oid: Oid,
    non_repeaters: int,
    max_repetitions: int,
    community: bytes = b"public",
) -> bytes:
    """Encode an SNMPv2c GetBulk message for a single OID."""
    varbind = tlv(0x30, encode_oid(oid) + tlv(0x05, b""))
    pdu = _pdu(_TAG_GET_BULK, request_id, non_repeaters, max_repetitions, varbind)
    return _message(pdu, community)


def encode_response(
    request_id: int,
    varbinds: Sequence[tuple[Oid, int, bytes]],
    community: bytes = b"public",
    error_status: int = 0,
    error_index: int = 0,
) -> bytes:
    """Encode an SNMPv2c Response message.

    Each varbind is (oid, tag, value_bytes).  The tag and value_bytes are
    wrapped as a single TLV — callers supply the raw value body.
    """
    vb_bytes = b"".join(tlv(0x30, encode_oid(oid) + tlv(tag, val)) for oid, tag, val in varbinds)
    pdu = _pdu(_TAG_RESPONSE, request_id, error_status, error_index, vb_bytes)
    return _message(pdu, community)
