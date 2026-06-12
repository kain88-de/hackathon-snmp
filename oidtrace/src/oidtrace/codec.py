"""SNMP v2c message codec — encode and tolerant decode.

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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oidtrace.ber import decode_int, decode_oid, encode_int, encode_oid, read_tlv, tlv

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.oid import Oid

# PDU context-class tags (application, constructed)
PDU_GETBULK: int = 0xA5
PDU_RESPONSE: int = 0xA2

# v2c exception tags (§ 5 of trace-format.md)
EXCEPTION_TAGS: frozenset[int] = frozenset({0x80, 0x81, 0x82})

# Private: BER tag → vtype name per format spec § 5
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


def decode_message(raw: bytes) -> Message | Malformed:
    """Tolerantly decode a raw SNMPv2c datagram.

    Returns a Message on success, or Malformed if the bytes do not form a
    valid SNMPv2c message.  Never raises: all parse errors (ValueError from
    the BER layer) are caught here and returned as Malformed.

    The boundary is strictly ValueError -- any other exception propagates so
    that our own bugs cannot masquerade as device garbage.

    Structure parsed:
        SEQUENCE {
            INTEGER (version, must be 1)
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
        # --- outer SEQUENCE ---
        outer_tag, outer_body, _ = read_tlv(raw, 0)
        if outer_tag != 0x30:  # noqa: PLR2004
            raise ValueError(f"Expected outer SEQUENCE tag 0x30, got 0x{outer_tag:02x}")

        i = 0

        # --- version INTEGER ---
        ver_tag, _ver_body, i = read_tlv(outer_body, i)
        if ver_tag != 0x02:  # noqa: PLR2004
            raise ValueError(f"Expected version INTEGER tag 0x02, got 0x{ver_tag:02x}")

        # --- community OCTET STRING ---
        comm_tag, _comm_body, i = read_tlv(outer_body, i)
        if comm_tag != 0x04:  # noqa: PLR2004
            raise ValueError(f"Expected community OCTET STRING tag 0x04, got 0x{comm_tag:02x}")

        # --- PDU (context-constructed, class bits 0xA0-0xBF) ---
        pdu_tag, pdu_body, _i = read_tlv(outer_body, i)
        if (pdu_tag & 0xE0) != 0xA0:  # noqa: PLR2004
            raise ValueError(
                f"Expected context-constructed PDU tag (0xA0-0xBF), got 0x{pdu_tag:02x}"
            )

        j = 0

        # --- request-id INTEGER ---
        rid_tag, rid_body, j = read_tlv(pdu_body, j)
        if rid_tag != 0x02:  # noqa: PLR2004
            raise ValueError(f"Expected request-id INTEGER tag 0x02, got 0x{rid_tag:02x}")
        request_id = decode_int(rid_body)

        # --- f1 INTEGER (error-status or non-repeaters) ---
        f1_tag, f1_body, j = read_tlv(pdu_body, j)
        if f1_tag != 0x02:  # noqa: PLR2004
            raise ValueError(f"Expected f1 INTEGER tag 0x02, got 0x{f1_tag:02x}")
        f1 = decode_int(f1_body)

        # --- f2 INTEGER (error-index or max-repetitions) ---
        f2_tag, f2_body, j = read_tlv(pdu_body, j)
        if f2_tag != 0x02:  # noqa: PLR2004
            raise ValueError(f"Expected f2 INTEGER tag 0x02, got 0x{f2_tag:02x}")
        f2 = decode_int(f2_body)

        # --- varbind-list SEQUENCE ---
        vblist_tag, vblist_body, _j = read_tlv(pdu_body, j)
        if vblist_tag != 0x30:  # noqa: PLR2004
            raise ValueError(f"Expected varbind-list SEQUENCE tag 0x30, got 0x{vblist_tag:02x}")

        # --- individual varbinds ---
        varbinds: list[Varbind] = []
        k = 0
        while k < len(vblist_body):
            vb_tag, vb_body, k = read_tlv(vblist_body, k)
            if vb_tag != 0x30:  # noqa: PLR2004
                raise ValueError(f"Expected varbind SEQUENCE tag 0x30, got 0x{vb_tag:02x}")
            m = 0
            oid_tag, oid_body, m = read_tlv(vb_body, m)
            if oid_tag != 0x06:  # noqa: PLR2004
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
