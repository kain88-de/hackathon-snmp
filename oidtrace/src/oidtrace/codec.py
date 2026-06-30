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

import hmac
from dataclasses import dataclass
from typing import TYPE_CHECKING

from oidtrace.auth import AuthProto, compute_mac
from oidtrace.ber import decode_int, decode_oid, encode_int, encode_oid, read_tlv, tlv

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oidtrace.oid import Oid

PDU_GET: int = 0xA0  # GetRequest — SNMPv3 discovery probe
PDU_GETBULK: int = 0xA5
PDU_GETNEXT: int = 0xA1  # RFC 1157 GetNextRequest-PDU = context [1] = 0xA1; 0xA3 is SetRequest
PDU_RESPONSE: int = 0xA2
PDU_REPORT: int = 0xA8  # SNMPv3 Report PDU — discovery response

# v2c exception tags (§ 5 of trace-format.md)
EXCEPTION_TAGS: frozenset[int] = frozenset({0x80, 0x81, 0x82})

_TAG_SEQUENCE: int = 0x30
_TAG_INTEGER: int = 0x02
_TAG_OCTET_STRING: int = 0x04
_TAG_OID: int = 0x06
_TAG_NULL: int = 0x05
_TAG_END_OF_MIB_VIEW: int = 0x82
_PDU_CLASS_MASK: int = 0xE0
_PDU_CLASS_CONTEXT_CONSTRUCTED: int = 0xA0
_SNMP_VERSION_3: int = 3

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


_AUTH_PARAMS_PLACEHOLDER: bytes = b"\x04\x0c" + b"\x00" * 12


@dataclass(frozen=True, slots=True)
class V3Params:
    """Extracted USM parameters from a decoded SNMPv3 message.

    Attributes:
        engine_id: The authoritativeEngineID (may be empty in discovery response).
        engine_boots: The authoritativeEngineBoots counter.
        engine_time: The authoritativeEngineTime value.
        msg_id: The msgID from msgGlobalData (needed to echo in response PDUs).
        username: The msgSecurityParameters username (needed to echo in responses).
        auth_params: The msgAuthenticationParameters (12 bytes if auth, empty otherwise).
    """

    engine_id: bytes
    engine_boots: int
    engine_time: int
    msg_id: int
    username: bytes = b""
    auth_params: bytes = b""


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


def _encode_msg_global_data(msg_id: int, auth: bool = False) -> bytes:
    """Encode SNMPv3 msgGlobalData SEQUENCE.

    Structure (RFC 3412):
        SEQUENCE {
            INTEGER msgID
            INTEGER msgMaxSize (fixed 65507)
            OCTET STRING msgFlags (0x05 if auth, else 0x04 = reportable, noAuth, noPriv)
            INTEGER msgSecurityModel (3 = USM)
        }
    """
    msg_flags = bytes([0x05]) if auth else bytes([0x04])
    return tlv(
        _TAG_SEQUENCE,
        encode_int(msg_id) + encode_int(65507) + tlv(_TAG_OCTET_STRING, msg_flags) + encode_int(3),
    )


def _encode_usm_params(
    engine_id: bytes,
    engine_boots: int,
    engine_time: int,
    username: bytes,
    auth_params: bytes = b"",
) -> bytes:
    """Encode SNMPv3 USM security parameters (RFC 3414).

    Returns the OCTET STRING containing the BER-encoded SEQUENCE of USM fields.

    Structure (inside the OCTET STRING):
        SEQUENCE {
            OCTET STRING msgAuthoritativeEngineID
            INTEGER msgAuthoritativeEngineBoots
            INTEGER msgAuthoritativeEngineTime
            OCTET STRING msgUserName
            OCTET STRING msgAuthenticationParameters (empty = noAuth, 12 zeros = placeholder)
            OCTET STRING msgPrivacyParameters (empty = noPriv)
        }
    """
    usm_sequence = tlv(
        _TAG_SEQUENCE,
        tlv(_TAG_OCTET_STRING, engine_id)
        + encode_int(engine_boots)
        + encode_int(engine_time)
        + tlv(_TAG_OCTET_STRING, username)
        + tlv(_TAG_OCTET_STRING, auth_params)
        + tlv(_TAG_OCTET_STRING, b""),
    )
    return tlv(_TAG_OCTET_STRING, usm_sequence)


def _encode_scoped_pdu(context_engine_id: bytes, pdu: bytes) -> bytes:
    """Encode SNMPv3 ScopedPDU SEQUENCE.

    Structure (RFC 3412):
        SEQUENCE {
            OCTET STRING contextEngineID
            OCTET STRING contextName (empty for noAuthNoPriv)
            PDU (GetRequest, GetBulk, etc.)
        }
    """
    return tlv(
        _TAG_SEQUENCE,
        tlv(_TAG_OCTET_STRING, context_engine_id) + tlv(_TAG_OCTET_STRING, b"") + pdu,
    )


def _tlv_header_len(buf: bytes, offset: int) -> int:
    """Return the number of bytes in the TLV header (tag + length) at buf[offset]."""
    len_byte = buf[offset + 1]
    if len_byte & 0x80:
        return 2 + (len_byte & 0x7F)
    return 2


def _auth_params_value_offset(raw: bytes) -> int:
    """BER-walk raw to find the byte offset of the auth_params VALUE (past tag+length).

    Walks structurally:
        outer SEQUENCE → skip INTEGER(3) → skip msgGlobalData SEQUENCE
        → enter USM OCTET STRING → enter inner USM SEQUENCE
        → skip engineID / boots / time / username
        → return byte offset of the auth_params VALUE (past its tag+length).

    Raises ValueError if the structure is not as expected.
    """
    # Determine outer SEQUENCE header size
    outer_tag, outer_body, _ = read_tlv(raw, 0)
    if outer_tag != _TAG_SEQUENCE:
        raise ValueError(f"Expected outer SEQUENCE 0x30, got 0x{outer_tag:02x}")
    outer_body_start = _tlv_header_len(raw, 0)  # abs offset where outer_body starts

    i = 0  # position within outer_body

    # skip version INTEGER
    _, _, i = read_tlv(outer_body, i)

    # skip msgGlobalData SEQUENCE
    _, _, i = read_tlv(outer_body, i)

    # USM OCTET STRING: record its abs position in raw before consuming it
    usm_os_abs_start = outer_body_start + i
    usm_os_tag, usm_os_body, _ = read_tlv(outer_body, i)
    if usm_os_tag != _TAG_OCTET_STRING:
        raise ValueError(f"Expected USM OCTET STRING 0x04, got 0x{usm_os_tag:02x}")
    usm_os_body_abs_start = usm_os_abs_start + _tlv_header_len(raw, usm_os_abs_start)

    # inner USM SEQUENCE inside the OCTET STRING body
    inner_seq_tag, inner_seq_body, _ = read_tlv(usm_os_body, 0)
    if inner_seq_tag != _TAG_SEQUENCE:
        raise ValueError(f"Expected inner USM SEQUENCE 0x30, got 0x{inner_seq_tag:02x}")
    inner_seq_body_abs_start = usm_os_body_abs_start + _tlv_header_len(usm_os_body, 0)

    # Walk USM fields within inner_seq_body: engineID, boots, time, username
    u = 0
    _, _, u = read_tlv(inner_seq_body, u)  # engineID
    _, _, u = read_tlv(inner_seq_body, u)  # boots
    _, _, u = read_tlv(inner_seq_body, u)  # time
    _, _, u = read_tlv(inner_seq_body, u)  # username

    # auth_params TLV starts at abs offset: inner_seq_body_abs_start + u
    ap_abs_start = inner_seq_body_abs_start + u
    ap_tag = raw[ap_abs_start]
    if ap_tag != _TAG_OCTET_STRING:
        raise ValueError(f"Expected auth_params OCTET STRING 0x04, got 0x{ap_tag:02x}")

    return ap_abs_start + _tlv_header_len(raw, ap_abs_start)


def authenticate_msg(raw: bytes, kul: bytes, proto: AuthProto) -> bytes:
    """Sign a v3 message that contains a zero-filled auth_params placeholder.

    Uses _auth_params_value_offset to locate the placeholder structurally
    (avoids false matches when engineID happens to contain zero bytes).

    Args:
        raw: Message bytes with zero-filled auth_params placeholder.
        kul: Localized key from password_to_key.
        proto: Hash algorithm to use for the MAC.

    Returns:
        Message bytes with the placeholder replaced by the computed MAC.
    """
    offset = _auth_params_value_offset(raw)
    # Zero the auth params slot (it should already be zero, but be explicit)
    zeroed = raw[:offset] + bytes(proto.mac_length) + raw[offset + proto.mac_length :]
    mac = compute_mac(kul, zeroed, proto)
    return raw[:offset] + mac + raw[offset + proto.mac_length :]


def verify_auth(raw: bytes, auth_params: bytes, kul: bytes, proto: AuthProto) -> bool:
    """Verify the authentication MAC of a signed v3 message.

    Args:
        raw: The signed message bytes.
        auth_params: The MAC extracted from the message (from V3Params.auth_params).
        kul: Localized key from password_to_key.
        proto: Hash algorithm ("MD5" or "SHA").

    Returns:
        True if the MAC is valid, False otherwise (wrong key, tampered, malformed).
    """
    if len(auth_params) != proto.mac_length:
        return False
    try:
        offset = _auth_params_value_offset(raw)
    except ValueError:
        return False
    zeroed = raw[:offset] + bytes(proto.mac_length) + raw[offset + proto.mac_length :]
    expected_mac = compute_mac(kul, zeroed, proto)
    return hmac.compare_digest(expected_mac, auth_params)


def encode_v3_discovery(msg_id: int, request_id: int) -> bytes:
    """Encode an SNMPv3 discovery probe (GetRequest with empty varbinds).

    Discovery probe:
    - msgFlags = 0x04 (reportable, noAuth, noPriv)
    - All USM fields empty/zero except msg_id
    - GetRequest (0xA0) PDU with empty VarBindList
    - contextEngineID empty

    Args:
        msg_id: Message identifier (random, per-message).
        request_id: Request identifier (echoed by the agent).

    Returns:
        Complete SNMPv3 message bytes (64 bytes for canonical inputs).
    """
    # GetRequest PDU with empty varbinds
    varbind_list = tlv(_TAG_SEQUENCE, b"")
    pdu = tlv(
        PDU_GET,
        encode_int(request_id) + encode_int(0) + encode_int(0) + varbind_list,
    )

    # ScopedPDU with empty contextEngineID
    scoped_pdu = _encode_scoped_pdu(b"", pdu)

    # USM params: all fields empty/zero
    usm_params = _encode_usm_params(b"", 0, 0, b"")

    # msgGlobalData
    msg_global = _encode_msg_global_data(msg_id)

    # Outer SEQUENCE: version 3, msgGlobalData, USM params, ScopedPDU
    return tlv(
        _TAG_SEQUENCE,
        encode_int(3) + msg_global + usm_params + scoped_pdu,
    )


def encode_v3_getbulk(  # noqa: PLR0913
    msg_id: int,
    request_id: int,
    oid: Oid,
    max_repetitions: int,
    engine_id: bytes,
    engine_boots: int,
    engine_time: int,
    username: bytes,
    proto: AuthProto | None = None,
) -> bytes:
    """Encode an SNMPv3 GetBulk request.

    Args:
        msg_id: Message identifier.
        request_id: Request identifier.
        oid: The start OID for the bulk walk (single varbind, NULL value).
        max_repetitions: Maximum repetitions per varbind.
        engine_id: AuthoritativeEngineID (from discovery).
        engine_boots: AuthoritativeEngineBoots (from discovery).
        engine_time: AuthoritativeEngineTime (from discovery).
        username: Username for this request.
        proto: AuthProto | None — if not None, set msgFlags auth bit and embed
            zero-filled auth placeholder of the correct length.

    Returns:
        Complete SNMPv3 message bytes.
    """
    # GetBulk PDU with the requested OID and max_repetitions
    varbind_list = tlv(_TAG_SEQUENCE, tlv(_TAG_SEQUENCE, encode_oid(oid) + tlv(_TAG_NULL, b"")))
    pdu = tlv(
        PDU_GETBULK,
        encode_int(request_id)
        + encode_int(0)  # non_repeaters
        + encode_int(max_repetitions)
        + varbind_list,
    )

    # ScopedPDU with contextEngineID from discovery
    scoped_pdu = _encode_scoped_pdu(engine_id, pdu)

    # USM params with discovery values; zero-filled placeholder when proto is not None
    auth_params_bytes = bytes(proto.mac_length) if proto is not None else b""
    usm_params = _encode_usm_params(
        engine_id, engine_boots, engine_time, username, auth_params_bytes
    )

    # msgGlobalData
    msg_global = _encode_msg_global_data(msg_id, auth=proto is not None)

    # Outer SEQUENCE: version 3, msgGlobalData, USM params, ScopedPDU
    return tlv(
        _TAG_SEQUENCE,
        encode_int(3) + msg_global + usm_params + scoped_pdu,
    )


def encode_v3_response(  # noqa: PLR0913
    msg_id: int,
    request_id: int,
    varbinds: Sequence[tuple[Oid, int, bytes]],
    engine_id: bytes,
    username: bytes = b"",
    error_status: int = 0,
    error_index: int = 0,
    pdu_tag: int = PDU_RESPONSE,
    proto: AuthProto | None = None,
) -> bytes:
    """Encode an SNMPv3 Response or Report PDU (used by the emulator).

    Args:
        msg_id: Message identifier (echoed from request).
        request_id: Request identifier (echoed from request).
        varbinds: Sequence of (oid, tag, value_bytes) tuples.
        engine_id: AuthoritativeEngineID to embed in response.
        username: Username (default b"").
        error_status: Error status (default 0 = noError).
        error_index: Error index (default 0).
        pdu_tag: PDU tag (default PDU_RESPONSE=0xA2; use PDU_REPORT=0xA8 for discovery response).
        proto: AuthProto | None — if not None, set msgFlags auth bit and embed
            zero-filled auth placeholder of the correct length.

    Returns:
        Complete SNMPv3 message bytes.
    """
    # Encode varbinds
    encoded_vbs = b"".join(
        tlv(_TAG_SEQUENCE, encode_oid(oid) + tlv(tag, value_bytes))
        for oid, tag, value_bytes in varbinds
    )

    # Response or Report PDU
    pdu = tlv(
        pdu_tag,
        encode_int(request_id)
        + encode_int(error_status)
        + encode_int(error_index)
        + tlv(_TAG_SEQUENCE, encoded_vbs),
    )

    # ScopedPDU with contextEngineID from discovery
    scoped_pdu = _encode_scoped_pdu(engine_id, pdu)

    # USM params; zero-filled placeholder when proto is not None
    auth_params_bytes = bytes(proto.mac_length) if proto is not None else b""
    usm_params = _encode_usm_params(engine_id, 0, 0, username, auth_params_bytes)

    # msgGlobalData
    msg_global = _encode_msg_global_data(msg_id, auth=proto is not None)

    # Outer SEQUENCE: version 3, msgGlobalData, USM params, ScopedPDU
    return tlv(
        _TAG_SEQUENCE,
        encode_int(3) + msg_global + usm_params + scoped_pdu,
    )


def _expect_tlv(buf: bytes, i: int, tag: int, name: str) -> tuple[bytes, int]:
    """Read one TLV and assert its tag, returning (body, next_i).

    Raises ValueError with a consistent message if the tag does not match.
    """
    got_tag, body, next_i = read_tlv(buf, i)
    if got_tag != tag:
        raise ValueError(f"Expected {name} tag 0x{tag:02x}, got 0x{got_tag:02x}")
    return body, next_i


def _read_pdu_f1_f2(pdu_body: bytes, j: int) -> tuple[int, int, int]:
    """Read f1 and f2 fields from PDU body.

    All SNMP PDU types (GetNext, GetResponse, GetBulk) include error-status
    and error-index (or non-repeaters/max-repetitions for GetBulk) after the
    request-id.  Requests send them as zeros; we read them unconditionally.

    Returns (f1, f2, next_j).
    """
    f1_body, j = _expect_tlv(pdu_body, j, _TAG_INTEGER, "f1 INTEGER")
    f1 = decode_int(f1_body)

    f2_body, j = _expect_tlv(pdu_body, j, _TAG_INTEGER, "f2 INTEGER")
    f2 = decode_int(f2_body)

    return f1, f2, j


def _decode_pdu(pdu_body: bytes) -> tuple[int, int, int, tuple[Varbind, ...]]:
    """Parse a PDU body and return (request_id, f1, f2, varbinds).

    Shared by decode_message and decode_v3_message.

    Raises:
        ValueError: on any structural parse error.
    """
    j = 0

    rid_body, j = _expect_tlv(pdu_body, j, _TAG_INTEGER, "request-id INTEGER")
    request_id = decode_int(rid_body)

    f1, f2, j = _read_pdu_f1_f2(pdu_body, j)

    vblist_body, _j = _expect_tlv(pdu_body, j, _TAG_SEQUENCE, "varbind-list SEQUENCE")

    varbinds: list[Varbind] = []
    k = 0
    while k < len(vblist_body):
        vb_body, k = _expect_tlv(vblist_body, k, _TAG_SEQUENCE, "varbind SEQUENCE")
        oid_body, m = _expect_tlv(vb_body, 0, _TAG_OID, "OID")
        oid = decode_oid(oid_body)
        val_tag, val_body, _m = read_tlv(vb_body, m)
        varbinds.append(Varbind(oid=oid, tag=val_tag, value=val_body))

    return request_id, f1, f2, tuple(varbinds)


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
        outer_body, _ = _expect_tlv(raw, 0, _TAG_SEQUENCE, "outer SEQUENCE")

        i = 0

        _ver_body, i = _expect_tlv(outer_body, i, _TAG_INTEGER, "version INTEGER")
        _comm_body, i = _expect_tlv(outer_body, i, _TAG_OCTET_STRING, "community OCTET STRING")

        pdu_tag, pdu_body, _i = read_tlv(outer_body, i)
        if (pdu_tag & _PDU_CLASS_MASK) != _PDU_CLASS_CONTEXT_CONSTRUCTED:
            raise ValueError(
                f"Expected context-constructed PDU tag (0xA0-0xBF), got 0x{pdu_tag:02x}"
            )

        request_id, f1, f2, varbinds = _decode_pdu(pdu_body)

        return Message(
            pdu_tag=pdu_tag,
            request_id=request_id,
            f1=f1,
            f2=f2,
            varbinds=varbinds,
            raw=raw,
        )

    except ValueError as exc:
        return Malformed(raw=raw, error=str(exc))


def decode_v3_message(raw: bytes) -> tuple[Message, V3Params] | Malformed:
    """Tolerantly decode a raw SNMPv3 (noAuthNoPriv) datagram.

    Returns a (Message, V3Params) tuple on success, or Malformed if the bytes
    cannot be parsed.  Never raises: all parse errors are caught and returned
    as Malformed.

    Structure parsed:
        SEQUENCE {
            INTEGER (version: must be 3)
            SEQUENCE (msgGlobalData) {
                INTEGER (msgID)
                INTEGER (msgMaxSize — ignored)
                OCTET STRING (msgFlags — ignored)
                INTEGER (msgSecurityModel — ignored)
            }
            OCTET STRING (USM params containing a BER SEQUENCE) {
                SEQUENCE {
                    OCTET STRING (engineID)
                    INTEGER (engineBoots)
                    INTEGER (engineTime)
                    OCTET STRING (username — ignored)
                    OCTET STRING (authParams — returned in V3Params.auth_params)
                    OCTET STRING (privParams — ignored)
                }
            }
            SEQUENCE (ScopedPDU — tag must be 0x30; 0x04 means encrypted) {
                OCTET STRING (contextEngineID — ignored)
                OCTET STRING (contextName — ignored)
                PDU
            }
        }
    """
    try:
        outer_body, _ = _expect_tlv(raw, 0, _TAG_SEQUENCE, "outer SEQUENCE")

        i = 0

        # version must be 3
        ver_body, i = _expect_tlv(outer_body, i, _TAG_INTEGER, "version INTEGER")
        version = decode_int(ver_body)
        if version != _SNMP_VERSION_3:
            raise ValueError(f"Expected SNMPv3 version 3, got {version}")

        # msgGlobalData SEQUENCE
        gd_body, i = _expect_tlv(outer_body, i, _TAG_SEQUENCE, "msgGlobalData SEQUENCE")
        msg_id_body, _gd_i = _expect_tlv(gd_body, 0, _TAG_INTEGER, "msgID INTEGER")
        msg_id = decode_int(msg_id_body)
        # skip msgMaxSize, msgFlags, msgSecurityModel

        # USM OCTET STRING containing BER-encoded SEQUENCE
        usm_os_body, i = _expect_tlv(outer_body, i, _TAG_OCTET_STRING, "USM OCTET STRING")
        usm_body, _ = _expect_tlv(usm_os_body, 0, _TAG_SEQUENCE, "USM inner SEQUENCE")
        u = 0
        engine_id, u = _expect_tlv(usm_body, u, _TAG_OCTET_STRING, "engineID OCTET STRING")
        boots_body, u = _expect_tlv(usm_body, u, _TAG_INTEGER, "engineBoots INTEGER")
        engine_boots = decode_int(boots_body)
        time_body, u = _expect_tlv(usm_body, u, _TAG_INTEGER, "engineTime INTEGER")
        engine_time = decode_int(time_body)
        username, u = _expect_tlv(usm_body, u, _TAG_OCTET_STRING, "username OCTET STRING")
        auth_params, _u = _expect_tlv(usm_body, u, _TAG_OCTET_STRING, "authParams OCTET STRING")

        # ScopedPDU — must be plain SEQUENCE (0x30); 0x04 = encrypted (Priv)
        scoped_tag, scoped_body, _i = read_tlv(outer_body, i)
        if scoped_tag == _TAG_OCTET_STRING:
            raise ValueError("ScopedPDU is encrypted (Priv); noAuthNoPriv decoder cannot decrypt")
        if scoped_tag != _TAG_SEQUENCE:
            raise ValueError(f"Expected ScopedPDU SEQUENCE tag 0x30, got 0x{scoped_tag:02x}")

        # Skip contextEngineID and contextName, then parse the PDU
        s = 0
        _, _, s = read_tlv(scoped_body, s)  # contextEngineID
        _, _, s = read_tlv(scoped_body, s)  # contextName
        pdu_tag, pdu_body, _s = read_tlv(scoped_body, s)
        if (pdu_tag & _PDU_CLASS_MASK) != _PDU_CLASS_CONTEXT_CONSTRUCTED:
            raise ValueError(
                f"Expected context-constructed PDU tag (0xA0-0xBF), got 0x{pdu_tag:02x}"
            )

        request_id, f1, f2, varbinds = _decode_pdu(pdu_body)

        params = V3Params(
            engine_id=engine_id,
            engine_boots=engine_boots,
            engine_time=engine_time,
            msg_id=msg_id,
            username=username,
            auth_params=auth_params,
        )
        msg = Message(
            pdu_tag=pdu_tag,
            request_id=request_id,
            f1=f1,
            f2=f2,
            varbinds=varbinds,
            raw=raw,
        )
        return msg, params

    except ValueError as exc:
        return Malformed(raw=raw, error=str(exc))
