"""Tests for oidtrace.auth — SNMP v3 key derivation and MAC computation.

Contract coverage:
  - password_to_key: RFC 3414 A.2 localization algorithm
    - MD5 vector (RFC 3414 A.3.1)
    - SHA vector (RFC 3414 A.3.2)
    - Output length: MD5=16, SHA=20
    - Different engineIDs produce different keys from same password
  - compute_mac: HMAC truncation (12 bytes for MD5/SHA, 24 bytes for SHA-256)
    - Output length matches proto.mac_length
    - Different messages produce different MACs
    - Different keys produce different MACs
"""

from __future__ import annotations

import pytest

from oidtrace.auth import AuthProto, compute_mac, password_to_key

# ---------------------------------------------------------------------------
# password_to_key: RFC 3414 vectors
# ---------------------------------------------------------------------------


def test_password_to_key_md5_rfc3414_a31() -> None:
    """RFC 3414 A.3.1 vector: password='maplesyrup', engineID=12 bytes."""
    key = password_to_key(
        b"maplesyrup",
        bytes.fromhex("000000000000000000000002"),
        AuthProto.MD5,
    )
    assert key == bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")


def test_password_to_key_sha_rfc3414_a32() -> None:
    """RFC 3414 A.3.2 vector: password='maplesyrup', engineID=12 bytes."""
    key = password_to_key(
        b"maplesyrup",
        bytes.fromhex("000000000000000000000002"),
        AuthProto.SHA,
    )
    assert key == bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")


# ---------------------------------------------------------------------------
# password_to_key: length
# ---------------------------------------------------------------------------


def test_password_to_key_md5_length() -> None:
    """MD5 localized key is 16 bytes."""
    key = password_to_key(b"test", bytes.fromhex("000000000000000000000001"), AuthProto.MD5)
    assert len(key) == 16


def test_password_to_key_sha_length() -> None:
    """SHA localized key is 20 bytes."""
    key = password_to_key(b"test", bytes.fromhex("000000000000000000000001"), AuthProto.SHA)
    assert len(key) == 20


# ---------------------------------------------------------------------------
# password_to_key: engineID sensitivity
# ---------------------------------------------------------------------------


def test_password_to_key_different_engineids() -> None:
    """Same password with different engineIDs produces different keys."""
    password = b"secret"
    engine_id_1 = bytes.fromhex("000000000000000000000001")
    engine_id_2 = bytes.fromhex("000000000000000000000002")

    key1 = password_to_key(password, engine_id_1, AuthProto.MD5)
    key2 = password_to_key(password, engine_id_2, AuthProto.MD5)

    assert key1 != key2


# ---------------------------------------------------------------------------
# password_to_key: validation
# ---------------------------------------------------------------------------


def test_password_to_key_rejects_empty_password() -> None:
    """Empty password raises ValueError."""
    with pytest.raises(ValueError):
        password_to_key(b"", b"\x00" * 12, AuthProto.MD5)


# ---------------------------------------------------------------------------
# compute_mac: length
# ---------------------------------------------------------------------------


def test_compute_mac_md5_length() -> None:
    """HMAC-MD5 MAC is truncated to 12 bytes."""
    kul = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    msg = b"test message"
    mac = compute_mac(kul, msg, AuthProto.MD5)
    assert len(mac) == 12


def test_compute_mac_sha_length() -> None:
    """HMAC-SHA MAC is truncated to 12 bytes."""
    kul = bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")
    msg = b"test message"
    mac = compute_mac(kul, msg, AuthProto.SHA)
    assert len(mac) == 12


# ---------------------------------------------------------------------------
# compute_mac: tampering detection
# ---------------------------------------------------------------------------


def test_compute_mac_different_messages() -> None:
    """Different messages produce different MACs."""
    kul = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    msg1 = b"original message"
    msg2 = b"tampered message"

    mac1 = compute_mac(kul, msg1, AuthProto.MD5)
    mac2 = compute_mac(kul, msg2, AuthProto.MD5)

    assert mac1 != mac2


def test_compute_mac_different_keys() -> None:
    """Different keys produce different MACs."""
    msg = b"test message"
    kul1 = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    kul2 = bytes.fromhex("000000000000000000000000000000d0")

    mac1 = compute_mac(kul1, msg, AuthProto.MD5)
    mac2 = compute_mac(kul2, msg, AuthProto.MD5)

    assert mac1 != mac2


# ---------------------------------------------------------------------------
# SHA-256 tests
# ---------------------------------------------------------------------------


def test_password_to_key_sha256_length() -> None:
    """SHA-256 localized key is 32 bytes."""
    key = password_to_key(b"test", bytes.fromhex("000000000000000000000001"), AuthProto.SHA256)
    assert len(key) == 32


def test_password_to_key_sha256_kat() -> None:
    """SHA-256 key derivation: known-answer test (RFC 3414 A.2 algorithm with SHA-256)."""
    key = password_to_key(
        b"maplesyrup",
        bytes.fromhex("000000000000000000000002"),
        AuthProto.SHA256,
    )
    assert key == bytes.fromhex("8982e0e549e866db361a6b625d84cccc11162d453ee8ce3a6445c2d6776f0f8b")


def test_compute_mac_sha256_length() -> None:
    """HMAC-SHA-256 MAC is truncated to 24 bytes."""
    kul = password_to_key(b"test", bytes.fromhex("000000000000000000000001"), AuthProto.SHA256)
    mac = compute_mac(kul, b"test message", AuthProto.SHA256)
    assert len(mac) == 24


def test_compute_mac_md5_still_12_bytes() -> None:
    """MD5 MAC still 12 bytes after SHA-256 support added."""
    kul = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    assert len(compute_mac(kul, b"test", AuthProto.MD5)) == 12


def test_compute_mac_sha_still_12_bytes() -> None:
    """SHA-1 MAC still 12 bytes after SHA-256 support added."""
    kul = bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")
    assert len(compute_mac(kul, b"test", AuthProto.SHA)) == 12
