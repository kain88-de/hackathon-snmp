"""BER codec primitives for oidtrace.

Scope: encoding and decoding of BER TLV structures only.
No SNMP semantics, no I/O.

Notes on integer encoding:
  encode_int targets non-negative SNMP integers.  The BER integer encoding is
  two's complement, so any value whose high bit would be set in the minimal
  unsigned representation needs a leading 0x00 byte.  For example:
    128 (0x80) encodes as b'\x00\x80'  (2 bytes)
    255 (0xFF) encodes as b'\x00\xff'  (2 bytes)
    127 (0x7F) encodes as b'\x7f'      (1 byte — high bit clear, no pad needed)
"""

from __future__ import annotations

from oidtrace.oid import Oid

_LONG_FORM_THRESHOLD = 0x80  # BER lengths >= 128 require long-form encoding


def tlv(tag: int, payload: bytes) -> bytes:
    """Build a BER TLV: tag byte + length field + payload.

    Uses short-form length (1 byte) for payload < 128 bytes, and long-form
    (0x80 | num_bytes, then the length in big-endian) otherwise.
    """
    n = len(payload)
    if n < _LONG_FORM_THRESHOLD:
        length_bytes = bytes([n])
    else:
        encoded_len = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length_bytes = bytes([0x80 | len(encoded_len)]) + encoded_len
    return bytes([tag]) + length_bytes + payload


def encode_int(v: int, tag: int = 0x02) -> bytes:
    """Encode an integer as a BER TLV using minimal two's-complement encoding.

    Targets non-negative SNMP integers.  Values whose minimal unsigned
    encoding would have the high bit set (e.g. 128, 255) receive a leading
    0x00 byte so the sign is unambiguous.
    """
    if v == 0:
        body = b"\x00"
    else:
        # to_bytes with signed=True uses minimal two's complement.
        byte_count = (v.bit_length() + 8) // 8  # +8 accounts for sign bit
        body = v.to_bytes(byte_count, "big", signed=True)
    return tlv(tag, body)


def encode_oid(oid: Oid) -> bytes:
    """Encode an Oid as a BER TLV with tag 0x06 (ObjectIdentifier).

    Encoding rules:
      - The first two arcs a0, a1 are packed as the single byte 40*a0 + a1.
      - Each subsequent arc is encoded in base-128 (7 bits per byte) with the
        continuation bit (0x80) set on all but the last byte of each arc.
    """
    arcs = oid.arcs
    body = bytearray([40 * arcs[0] + arcs[1]])
    for arc in arcs[2:]:
        val = arc
        chunk: list[int] = [val & 0x7F]
        val >>= 7
        while val:
            chunk.insert(0, (val & 0x7F) | 0x80)
            val >>= 7
        body.extend(chunk)
    return tlv(0x06, bytes(body))


def read_tlv(buf: bytes, i: int) -> tuple[int, bytes, int]:
    """Read one BER TLV from buf starting at offset i.

    Returns (tag, payload_bytes, next_i) where payload_bytes is a slice of
    buf (not indices) and next_i points one past the end of this TLV.

    Raises:
        ValueError: on truncated header, truncated long-form length bytes,
            zero length-of-length (indefinite form), or body overrun.
    """
    if i + 2 > len(buf):
        raise ValueError(f"Truncated TLV header at offset {i}: need 2 bytes, have {len(buf) - i}")
    tag = buf[i]
    length_byte = buf[i + 1]
    i += 2

    if length_byte & 0x80:
        num_len_bytes = length_byte & 0x7F
        if num_len_bytes == 0:
            raise ValueError("Indefinite-form length (0x80) is not supported")
        if i + num_len_bytes > len(buf):
            raise ValueError(
                f"Truncated long-form length: need {num_len_bytes} bytes, have {len(buf) - i}"
            )
        length = int.from_bytes(buf[i : i + num_len_bytes], "big")
        i += num_len_bytes
    else:
        length = length_byte

    end = i + length
    if end > len(buf):
        raise ValueError(
            f"TLV body overrun: declared length {length}, only {len(buf) - i} bytes available"
        )
    return tag, buf[i:end], end


def decode_int(body: bytes, *, signed: bool = True) -> int:
    """Decode a BER integer body (the payload bytes, not the full TLV)."""
    return int.from_bytes(body, "big", signed=signed)


def decode_oid(body: bytes) -> Oid:
    """Decode a BER ObjectIdentifier body into an Oid.

    The first byte unpacks into the first two arcs (a0 = byte // 40,
    a1 = byte % 40).  Subsequent arcs are base-128 encoded with continuation
    bits.

    Raises:
        ValueError: if body is empty or ends with a continuation byte
            (trailing continuation bit set — malformed encoding).
    """
    if not body:
        raise ValueError("OID body must not be empty")

    first = body[0]
    arcs: list[int] = [first // 40, first % 40]

    acc = 0
    has_pending = False
    for byte in body[1:]:
        acc = (acc << 7) | (byte & 0x7F)
        has_pending = bool(byte & 0x80)
        if not has_pending:
            arcs.append(acc)
            acc = 0

    if has_pending:
        raise ValueError("OID body ends with continuation bit set (truncated arc)")

    return Oid(arcs=tuple(arcs))
