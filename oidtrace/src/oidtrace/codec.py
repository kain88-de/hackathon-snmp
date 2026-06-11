"""SNMPv2c message encoding and tolerant decoding.

Uses oidtrace.ber for all BER primitives; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oidtrace.ber import decode_int, decode_oid, encode_int, encode_oid, read_tlv, tlv

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# BER/SNMP tag constants

_TAG_INTEGER = 0x02
_TAG_OCTET_STRING = 0x04
_TAG_OID = 0x06
_TAG_SEQUENCE = 0x30
_TAG_PDU_MIN = 0xA0  # context-constructed PDU class mask


# ---------------------------------------------------------------------------
# Tag name registry (§ 5 of trace-format.md)

TAG_NAMES: dict[int, str] = {
    0x02: "Integer",
    0x04: "OctetString",
    0x05: "Null",
    0x06: "ObjectIdentifier",
    0x40: "IpAddress",
    0x41: "Counter32",
    0x42: "Gauge32",
    0x43: "TimeTicks",
    0x44: "Opaque",
    0x46: "Counter64",
    0x80: "NoSuchObject",
    0x81: "NoSuchInstance",
    0x82: "EndOfMibView",
}

EXCEPTION_TAGS: frozenset[int] = frozenset({0x80, 0x81, 0x82})


# ---------------------------------------------------------------------------
# Decoded value types


@dataclass(frozen=True)
class Varbind:
    """A single decoded varbind: OID + typed value bytes."""

    oid: Oid
    tag: int
    value: bytes

    @property
    def vtype(self) -> str:
        return TAG_NAMES.get(self.tag, f"tag:0x{self.tag:02x}")

    @property
    def vlen(self) -> int:
        return len(self.value)


@dataclass(frozen=True)
class Message:
    """A successfully decoded SNMPv2c message."""

    pdu_tag: int
    request_id: int
    f1: int
    f2: int
    varbinds: tuple[Varbind, ...]
    raw: bytes


@dataclass(frozen=True)
class Malformed:
    """A datagram that could not be decoded."""

    raw: bytes
    error: str


# ---------------------------------------------------------------------------
# Tolerant decoder


def decode_message(raw: bytes) -> Message | Malformed:
    """Decode a raw SNMPv2c datagram.

    Returns Message on success.  Any structural error returns Malformed with
    a description; never raises.
    """
    try:
        return _decode(raw)
    except ValueError as exc:
        return Malformed(raw=raw, error=str(exc) or repr(exc))


def _decode(raw: bytes) -> Message:
    """Parse a raw SNMPv2c datagram; raises ValueError on any structural issue."""
    if not raw:
        raise ValueError("empty datagram")

    # Outer SEQUENCE
    outer_tag, outer_body, _ = read_tlv(raw, 0)
    if outer_tag != _TAG_SEQUENCE:
        raise ValueError(f"expected outer SEQUENCE (0x30), got 0x{outer_tag:02x}")

    i = 0
    # version INTEGER
    _vtag, vbody, i = read_tlv(outer_body, i)
    if _vtag != _TAG_INTEGER:
        raise ValueError(f"expected version INTEGER (0x02), got 0x{_vtag:02x}")
    _version = decode_int(vbody)

    # community OCTET STRING
    ctag, _cbody, i = read_tlv(outer_body, i)
    if ctag != _TAG_OCTET_STRING:
        raise ValueError(f"expected community OCTET STRING (0x04), got 0x{ctag:02x}")

    # PDU TLV (context-constructed: GetBulk=0xA5, Response=0xA2, etc.)
    pdu_tag, pdu_body, _ = read_tlv(outer_body, i)
    if not (pdu_tag & _TAG_PDU_MIN):
        raise ValueError(f"expected PDU context tag, got 0x{pdu_tag:02x}")

    # request-id, f1, f2
    j = 0
    ridtag, ridbody, j = read_tlv(pdu_body, j)
    if ridtag != _TAG_INTEGER:
        raise ValueError(f"expected request-id INTEGER, got 0x{ridtag:02x}")
    request_id = decode_int(ridbody)

    f1tag, f1body, j = read_tlv(pdu_body, j)
    if f1tag != _TAG_INTEGER:
        raise ValueError(f"expected f1 INTEGER, got 0x{f1tag:02x}")
    f1 = decode_int(f1body)

    f2tag, f2body, j = read_tlv(pdu_body, j)
    if f2tag != _TAG_INTEGER:
        raise ValueError(f"expected f2 INTEGER, got 0x{f2tag:02x}")
    f2 = decode_int(f2body)

    # varbind-list SEQUENCE
    vltag, vlbody, _ = read_tlv(pdu_body, j)
    if vltag != _TAG_SEQUENCE:
        raise ValueError(f"expected varbind-list SEQUENCE (0x30), got 0x{vltag:02x}")

    varbinds = _decode_varbind_list(vlbody)
    return Message(
        pdu_tag=pdu_tag,
        request_id=request_id,
        f1=f1,
        f2=f2,
        varbinds=varbinds,
        raw=raw,
    )


def _decode_varbind_list(body: bytes) -> tuple[Varbind, ...]:
    """Parse the varbind-list body into a tuple of Varbind objects."""
    varbinds: list[Varbind] = []
    i = 0
    while i < len(body):
        # Each varbind is a SEQUENCE(OID, value TLV)
        vbtag, vbbody, i = read_tlv(body, i)
        if vbtag != _TAG_SEQUENCE:
            raise ValueError(f"expected varbind SEQUENCE (0x30), got 0x{vbtag:02x}")

        k = 0
        oidtag, oidbody, k = read_tlv(vbbody, k)
        if oidtag != _TAG_OID:
            raise ValueError(f"expected OID tag (0x06), got 0x{oidtag:02x}")
        oid = decode_oid(oidbody)

        vtag, vvalue, _ = read_tlv(vbbody, k)
        varbinds.append(Varbind(oid=oid, tag=vtag, value=vvalue))

    return tuple(varbinds)


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
