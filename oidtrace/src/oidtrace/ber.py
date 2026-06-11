"""Minimal BER primitives — exactly what SNMP v2c needs, nothing more."""

from oidtrace.oid import Oid

_LONG_FORM_THRESHOLD = 0x80


def _encode_length(n: int) -> bytes:
    if n < _LONG_FORM_THRESHOLD:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([_LONG_FORM_THRESHOLD | len(b)]) + b


def tlv(tag: int, payload: bytes) -> bytes:
    """Emit tag + BER length + payload."""
    return bytes([tag]) + _encode_length(len(payload)) + payload


def encode_int(v: int, tag: int = 0x02) -> bytes:
    """Minimal two's-complement BER integer TLV.  Targets non-negative SNMP integers;
    negative powers-of-two (e.g. -128) get a non-minimal but valid two-byte body."""
    body = v.to_bytes(v.bit_length() // 8 + 1, "big", signed=True)
    return tlv(tag, body)


def encode_oid(oid: Oid) -> bytes:
    """OID TLV: first two arcs packed as 40*a+b, remaining arcs base-128."""
    body = bytearray([40 * oid.arcs[0] + oid.arcs[1]])
    for arc in oid.arcs[2:]:
        chunk = [arc & 0x7F]
        remaining = arc >> 7
        while remaining:
            chunk.insert(0, (remaining & 0x7F) | 0x80)
            remaining >>= 7
        body.extend(chunk)
    return tlv(0x06, bytes(body))


def read_tlv(buf: bytes, i: int) -> tuple[int, bytes, int]:
    """Parse one TLV from *buf* at offset *i*.

    Returns (tag, payload, next_i).  Raises ValueError on any truncation or
    invalid long-form length encoding.
    """
    if i + 2 > len(buf):
        raise ValueError("truncated TLV header")
    tag = buf[i]
    raw_len = buf[i + 1]
    i += 2

    if raw_len & 0x80:
        n = raw_len & 0x7F
        if n == 0:
            raise ValueError("indefinite-length form not supported")
        if i + n > len(buf):
            raise ValueError("truncated long-form length bytes")
        length = int.from_bytes(buf[i : i + n], "big")
        i += n
    else:
        length = raw_len

    end = i + length
    if end > len(buf):
        raise ValueError("truncated TLV body")
    return tag, buf[i:end], end


def decode_int(body: bytes, *, signed: bool = True) -> int:
    """Decode a BER integer body (two's-complement big-endian)."""
    return int.from_bytes(body, "big", signed=signed)


def decode_oid(body: bytes) -> Oid:
    """Decode a BER OID body into an Oid tuple.

    Raises ValueError on empty body or truncated multi-byte arc.
    """
    if not body:
        raise ValueError("empty OID body")
    arcs: list[int] = [body[0] // 40, body[0] % 40]
    acc = 0
    in_multibyte = False
    for byte in body[1:]:
        in_multibyte = True
        acc = (acc << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            arcs.append(acc)
            acc = 0
            in_multibyte = False
    if in_multibyte:
        raise ValueError("truncated multi-byte OID arc")
    return Oid(tuple(arcs))
