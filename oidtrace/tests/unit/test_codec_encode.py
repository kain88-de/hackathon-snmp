"""Tests for oidtrace.codec — encode side (Task 4).

Cross-validates encode_getbulk and encode_response against pysnmp's spec-driven
BER decoder, which is an independent implementation of the same wire format.
"""

from pyasn1.codec.ber import decoder as ber_decoder  # type: ignore[import-untyped]
from pysnmp.proto.api import v2c as pmod  # type: ignore[import-untyped]

from oidtrace.codec import encode_getbulk, encode_response
from oidtrace.oid import Oid

# ---------------------------------------------------------------------------
# pysnmp spec — shared across all tests

_SPEC = pmod.Message()

_OID = Oid.from_str("1.3.6.1.2.1.1.1")


def _decode(raw: bytes) -> object:
    """Spec-driven decode; assert no trailing bytes."""
    msg, rest = ber_decoder.decode(raw, asn1Spec=_SPEC)  # pyright: ignore[reportUnknownVariableType]
    assert not rest, f"unexpected trailing bytes: {rest!r}"
    return msg  # pyright: ignore[reportUnknownVariableType]


# ---------------------------------------------------------------------------
# encode_getbulk


def test_getbulk_bulk10_decodes_via_pysnmp() -> None:
    raw = encode_getbulk(42, _OID, non_repeaters=0, max_repetitions=10)
    msg = _decode(raw)
    decoded_pdu = pmod.apiMessage.get_pdu(msg)  # pyright: ignore[reportUnknownVariableType]
    varbinds = pmod.apiBulkPDU.get_varbind_list(decoded_pdu)  # pyright: ignore[reportUnknownVariableType]
    oid0, _ = pmod.apiVarBind.get_oid_value(varbinds[0])  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiPDU.get_request_id(decoded_pdu)) == 42  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiBulkPDU.get_non_repeaters(decoded_pdu)) == 0  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiBulkPDU.get_max_repetitions(decoded_pdu)) == 10  # pyright: ignore[reportUnknownVariableType]
    assert len(varbinds) == 1
    assert oid0.prettyPrint() == str(_OID)  # pyright: ignore[reportUnknownVariableType]


def test_getbulk_bulk1_decodes_via_pysnmp() -> None:
    raw = encode_getbulk(1, _OID, non_repeaters=0, max_repetitions=1)
    msg = _decode(raw)
    decoded_pdu = pmod.apiMessage.get_pdu(msg)  # pyright: ignore[reportUnknownVariableType]
    varbinds = pmod.apiBulkPDU.get_varbind_list(decoded_pdu)  # pyright: ignore[reportUnknownVariableType]
    oid0, _ = pmod.apiVarBind.get_oid_value(varbinds[0])  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiPDU.get_request_id(decoded_pdu)) == 1  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiBulkPDU.get_non_repeaters(decoded_pdu)) == 0  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiBulkPDU.get_max_repetitions(decoded_pdu)) == 1  # pyright: ignore[reportUnknownVariableType]
    assert len(varbinds) == 1
    assert oid0.prettyPrint() == str(_OID)  # pyright: ignore[reportUnknownVariableType]


def test_getbulk_max_repetitions_visible_on_wire() -> None:
    # max-repetitions=8 → INTEGER 8 → 02 01 08
    raw = encode_getbulk(7, _OID, non_repeaters=0, max_repetitions=8)
    assert bytes([0x02, 0x01, 0x08]) in raw


def test_getbulk_community_settable() -> None:
    raw = encode_getbulk(1, _OID, non_repeaters=0, max_repetitions=10, community=b"s3cret")
    assert b"s3cret" in raw


def test_getbulk_custom_community_decodes_via_pysnmp() -> None:
    raw = encode_getbulk(99, _OID, non_repeaters=0, max_repetitions=5, community=b"s3cret")
    _decode(raw)


# ---------------------------------------------------------------------------
# encode_response


def test_response_with_octetstring_and_counter32_decodes_via_pysnmp() -> None:
    varbinds = [
        (Oid.from_str("1.3.6.1.2.1.1.1.0"), 0x04, bytes(4)),  # OctetString, 4 zero bytes
        (Oid.from_str("1.3.6.1.2.1.1.3.0"), 0x41, b"\x00\x00\x01\x00"),  # Counter32
    ]
    raw = encode_response(1, varbinds)
    _decode(raw)


def test_response_single_varbind_decodes_via_pysnmp() -> None:
    varbinds = [(Oid.from_str("1.3.6.1.2.1.1.1.0"), 0x04, b"hello")]
    raw = encode_response(5, varbinds)
    msg = _decode(raw)
    decoded_pdu = pmod.apiMessage.get_pdu(msg)  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiPDU.get_request_id(decoded_pdu)) == 5  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiPDU.get_error_status(decoded_pdu)) == 0  # pyright: ignore[reportUnknownVariableType]
    assert int(pmod.apiPDU.get_error_index(decoded_pdu)) == 0  # pyright: ignore[reportUnknownVariableType]
    assert len(pmod.apiPDU.get_varbind_list(decoded_pdu)) == 1  # pyright: ignore[reportUnknownVariableType]


def test_response_community_settable() -> None:
    varbinds = [(Oid.from_str("1.3.6.1.2.1.1.1.0"), 0x04, b"")]
    raw = encode_response(1, varbinds, community=b"s3cret")
    assert b"s3cret" in raw


def test_response_custom_community_decodes_via_pysnmp() -> None:
    varbinds = [(Oid.from_str("1.3.6.1.2.1.1.1.0"), 0x04, b"test")]
    raw = encode_response(3, varbinds, community=b"s3cret")
    _decode(raw)
