"""SNMP v1/v2c message codec — encode and tolerant decode.

SNMPv2c message structure (BER SEQUENCE):
    version     INTEGER 1           (version-2c)
    community   OCTET STRING
    data        PDU

SNMPv1 GetNext message structure (BER SEQUENCE):
    version     INTEGER 0           (version-1)
    community   OCTET STRING
    data        PDU

GetBulk PDU (tag 0xA5):
    request-id        INTEGER
    non-repeaters     INTEGER
    max-repetitions   INTEGER
    variable-bindings SEQUENCE OF SEQUENCE(OID, NULL)

GetNext PDU (tag 0xA1):
    request-id        INTEGER
    error-status      INTEGER (0)
    error-index       INTEGER (0)
    variable-bindings SEQUENCE OF SEQUENCE(OID, NULL)

Response PDU (tag 0xA2):
    request-id        INTEGER
    error-status      INTEGER
    error-index       INTEGER
    variable-bindings SEQUENCE OF SEQUENCE(OID, TLV(tag, value_bytes))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oidtrace.ber import decode_int, decode_oid, encode_int, encode_oid, read_tlv, tlv

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.oid import Oid

PDU_GETBULK: int = 0xA5
PDU_GETNEXT: int = 0xA1  # RFC 1157 GetNextRequest-PDU = context [1] = 0xA1; 0xA3 is SetRequest
PDU_RESPONSE: int = 0xA2

# v2c exception tags (§ 5 of trace-format.md)
EXCEPTION_TAGS: frozenset[int] = frozenset({0x80, 0x81, 0x82})

_TAG_SEQUENCE: int = 0x30
_TAG_INTEGER: int = 0x02
_TAG_OCTET_STRING: int = 0x04
_TAG_OID: int = 0x06
_TAG_NULL: int = 0x05
_TAG_END_OF_MIB_VIEW: int = 0x82

# BER tag → vtype name per format spec § 5
_TAG_NAMES: dict[int, str] = {
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


@dataclass(frozen=True, slots=True)
class Varbind:
    """A single varbind from a decoded SNMP message.

    Attributes:
        oid: The OID.
        tag: The BER tag of the value.
        value: The raw value bytes (payload only, not the TLV wrapper).
        vtype: Human-readable type name (derived from tag, per format § 5).
        vlen: Byte length of the value payload.
    """

    oid: Oid
    tag: int
    value: bytes

    @property
    def vtype(self) -> str:
        """Tag → format § 5 name, or 'tag:0xNN' for unknown tags."""
        return _TAG_NAMES.get(self.tag, f"tag:0x{self.tag:02x}")

    @property
    def vlen(self) -> int:
        """Byte length of the value payload."""
        return len(self.value)


@dataclass(frozen=True, slots=True)
class Message:
    """A successfully decoded SNMP v2c message.

    Attributes:
        pdu_tag: The PDU type tag (e.g. 0xA2 for Response, 0xA5 for GetBulk).
        request_id: The request-id integer.
        f1: First PDU integer field (error-status for responses, non-repeaters for GetBulk).
        f2: Second PDU integer field (error-index for responses, max-repetitions for GetBulk).
        varbinds: Tuple of decoded varbinds.
        raw: The original raw bytes.
    """

    pdu_tag: int
    request_id: int
    f1: int
    f2: int
    varbinds: tuple[Varbind, ...]
    raw: bytes


@dataclass(frozen=True, slots=True)
class Malformed:
    """A datagram that could not be decoded.

    Attributes:
        raw: The original raw bytes.
        error: A non-empty human-readable description of the decode failure.
    """

    raw: bytes
    error: str


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
    varbind_list = tlv(_TAG_SEQUENCE, tlv(_TAG_SEQUENCE, encode_oid(oid) + tlv(_TAG_NULL, b"")))
    pdu = tlv(
        PDU_GETBULK,
        encode_int(request_id)
        + encode_int(non_repeaters)
        + encode_int(max_repetitions)
        + varbind_list,
    )
    return tlv(
        _TAG_SEQUENCE,
        encode_int(1) + tlv(_TAG_OCTET_STRING, community) + pdu,
    )


def encode_getnext(
    request_id: int,
    oid: Oid,
    community: bytes = b"public",
) -> bytes:
    """Encode an SNMPv1 GetNext request.

    Returns a complete BER-encoded SNMP message with version byte 0 (SNMP v1).

    Args:
        request_id: Integer request identifier.
        oid: The OID for the GetNext request (single varbind, NULL value).
        community: Community string (default b"public").
    """
    varbind_list = tlv(_TAG_SEQUENCE, tlv(_TAG_SEQUENCE, encode_oid(oid) + tlv(_TAG_NULL, b"")))
    pdu = tlv(
        PDU_GETNEXT,
        encode_int(request_id) + encode_int(0) + encode_int(0) + varbind_list,
    )
    return tlv(
        _TAG_SEQUENCE,
        encode_int(0) + tlv(_TAG_OCTET_STRING, community) + pdu,
    )


def encode_response(  # noqa: PLR0913
    request_id: int,
    varbinds: Sequence[tuple[Oid, int, bytes]],
    community: bytes = b"public",
    error_status: int = 0,
    error_index: int = 0,
    version: int = 1,
) -> bytes:
    """Encode an SNMP Response message (used by the emulator).

    Args:
        request_id: Integer request identifier.
        varbinds: Sequence of (oid, tag, value_bytes) tuples.
            The tag is the BER tag for the value (e.g. 0x04 for OctetString,
            0x41 for Counter32).  value_bytes is the raw value payload.
        community: Community string (default b"public").
        error_status: Error status integer (default 0 = noError).
        error_index: Error index integer (default 0).
        version: SNMP version byte (0 = v1, 1 = v2c; default 1).
    """
    encoded_vbs = b"".join(
        tlv(_TAG_SEQUENCE, encode_oid(oid) + tlv(tag, value_bytes))
        for oid, tag, value_bytes in varbinds
    )
    pdu = tlv(
        PDU_RESPONSE,
        encode_int(request_id)
        + encode_int(error_status)
        + encode_int(error_index)
        + tlv(_TAG_SEQUENCE, encoded_vbs),
    )
    return tlv(
        _TAG_SEQUENCE,
        encode_int(version) + tlv(_TAG_OCTET_STRING, community) + pdu,
    )


def _read_pdu_f1_f2(pdu_body: bytes, j: int) -> tuple[int, int, int]:
    """Read f1 and f2 fields from PDU body.

    All SNMP PDU types (GetNext, GetResponse, GetBulk) include error-status
    and error-index (or non-repeaters/max-repetitions for GetBulk) after the
    request-id.  Requests send them as zeros; we read them unconditionally.

    Returns (f1, f2, next_j).
    """
    f1_tag, f1_body, j = read_tlv(pdu_body, j)
    if f1_tag != _TAG_INTEGER:
        raise ValueError(f"Expected f1 INTEGER tag 0x02, got 0x{f1_tag:02x}")
    f1 = decode_int(f1_body)

    f2_tag, f2_body, j = read_tlv(pdu_body, j)
    if f2_tag != _TAG_INTEGER:
        raise ValueError(f"Expected f2 INTEGER tag 0x02, got 0x{f2_tag:02x}")
    f2 = decode_int(f2_body)

    return f1, f2, j


def decode_message(raw: bytes) -> Message | Malformed:
    """Tolerantly decode a raw SNMP datagram (v1 or v2c).

    Returns a Message on success, or Malformed if the bytes cannot be parsed.
    Never raises: all parse errors (ValueError from the BER layer) are caught
    here and returned as Malformed.

    The boundary is strictly ValueError -- any other exception propagates so
    that our own bugs cannot masquerade as device garbage.

    Structure parsed:
        SEQUENCE {
            INTEGER (version: 0=v1, 1=v2c — accepted without validation)
            OCTET STRING (community)
            context-constructed PDU {
                INTEGER (request-id)
                INTEGER (f1: error-status or non-repeaters)
                INTEGER (f2: error-index or max-repetitions)
                SEQUENCE {
                    SEQUENCE { OID, TLV } ...
                }
            }
        }
    """
    try:
        outer_tag, outer_body, _ = read_tlv(raw, 0)
        if outer_tag != _TAG_SEQUENCE:
            raise ValueError(f"Expected outer SEQUENCE tag 0x30, got 0x{outer_tag:02x}")

        i = 0

        ver_tag, _ver_body, i = read_tlv(outer_body, i)
        if ver_tag != _TAG_INTEGER:
            raise ValueError(f"Expected version INTEGER tag 0x02, got 0x{ver_tag:02x}")

        comm_tag, _comm_body, i = read_tlv(outer_body, i)
        if comm_tag != _TAG_OCTET_STRING:
            raise ValueError(f"Expected community OCTET STRING tag 0x04, got 0x{comm_tag:02x}")

        pdu_tag, pdu_body, _i = read_tlv(outer_body, i)
        if (pdu_tag & 0xE0) != 0xA0:  # noqa: PLR2004
            raise ValueError(
                f"Expected context-constructed PDU tag (0xA0-0xBF), got 0x{pdu_tag:02x}"
            )

        j = 0

        rid_tag, rid_body, j = read_tlv(pdu_body, j)
        if rid_tag != _TAG_INTEGER:
            raise ValueError(f"Expected request-id INTEGER tag 0x02, got 0x{rid_tag:02x}")
        request_id = decode_int(rid_body)

        f1, f2, j = _read_pdu_f1_f2(pdu_body, j)

        vblist_tag, vblist_body, _j = read_tlv(pdu_body, j)
        if vblist_tag != _TAG_SEQUENCE:
            raise ValueError(f"Expected varbind-list SEQUENCE tag 0x30, got 0x{vblist_tag:02x}")

        varbinds: list[Varbind] = []
        k = 0
        while k < len(vblist_body):
            vb_tag, vb_body, k = read_tlv(vblist_body, k)
            if vb_tag != _TAG_SEQUENCE:
                raise ValueError(f"Expected varbind SEQUENCE tag 0x30, got 0x{vb_tag:02x}")
            m = 0
            oid_tag, oid_body, m = read_tlv(vb_body, m)
            if oid_tag != _TAG_OID:
                raise ValueError(f"Expected OID tag 0x06, got 0x{oid_tag:02x}")
            oid = decode_oid(oid_body)
            val_tag, val_body, _m = read_tlv(vb_body, m)
            varbinds.append(Varbind(oid=oid, tag=val_tag, value=val_body))

        return Message(
            pdu_tag=pdu_tag,
            request_id=request_id,
            f1=f1,
            f2=f2,
            varbinds=tuple(varbinds),
            raw=raw,
        )

    except ValueError as exc:
        return Malformed(raw=raw, error=str(exc))
