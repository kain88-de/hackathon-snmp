"""Tests for oidtrace.auth — SNMP v3 key derivation and MAC computation.

Contract coverage:
  - password_to_key: RFC 3414 A.2 localization algorithm
    - MD5 vector (RFC 3414 A.3.1)
    - SHA vector (RFC 3414 A.3.2)
    - Output length: MD5=16, SHA=20
    - Different engineIDs produce different keys from same password
  - compute_mac: HMAC truncation to 12 bytes
    - Output length always 12 bytes
    - Different messages produce different MACs
    - Different keys produce different MACs
"""

from __future__ import annotations

import pytest

from oidtrace.auth import compute_mac, password_to_key

# ---------------------------------------------------------------------------
# password_to_key: RFC 3414 vectors
# ---------------------------------------------------------------------------


def test_password_to_key_md5_rfc3414_a31() -> None:
    """RFC 3414 A.3.1 vector: password='maplesyrup', engineID=12 bytes."""
    key = password_to_key(
        b"maplesyrup",
        bytes.fromhex("000000000000000000000002"),
        "MD5",
    )
    assert key == bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")


def test_password_to_key_sha_rfc3414_a32() -> None:
    """RFC 3414 A.3.2 vector: password='maplesyrup', engineID=12 bytes."""
    key = password_to_key(
        b"maplesyrup",
        bytes.fromhex("000000000000000000000002"),
        "SHA",
    )
    assert key == bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")


# ---------------------------------------------------------------------------
# password_to_key: length
# ---------------------------------------------------------------------------


def test_password_to_key_md5_length() -> None:
    """MD5 localized key is 16 bytes."""
    key = password_to_key(b"test", bytes.fromhex("000000000000000000000001"), "MD5")
    assert len(key) == 16


def test_password_to_key_sha_length() -> None:
    """SHA localized key is 20 bytes."""
    key = password_to_key(b"test", bytes.fromhex("000000000000000000000001"), "SHA")
    assert len(key) == 20


# ---------------------------------------------------------------------------
# password_to_key: engineID sensitivity
# ---------------------------------------------------------------------------


def test_password_to_key_different_engineids() -> None:
    """Same password with different engineIDs produces different keys."""
    password = b"secret"
    engine_id_1 = bytes.fromhex("000000000000000000000001")
    engine_id_2 = bytes.fromhex("000000000000000000000002")

    key1 = password_to_key(password, engine_id_1, "MD5")
    key2 = password_to_key(password, engine_id_2, "MD5")

    assert key1 != key2


# ---------------------------------------------------------------------------
# password_to_key: validation
# ---------------------------------------------------------------------------


def test_password_to_key_rejects_empty_password() -> None:
    """Empty password raises ValueError."""
    with pytest.raises(ValueError):
        password_to_key(b"", b"\x00" * 12, "MD5")


# ---------------------------------------------------------------------------
# compute_mac: length
# ---------------------------------------------------------------------------


def test_compute_mac_md5_length() -> None:
    """HMAC-MD5 MAC is truncated to 12 bytes."""
    kul = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    msg = b"test message"
    mac = compute_mac(kul, msg, "MD5")
    assert len(mac) == 12


def test_compute_mac_sha_length() -> None:
    """HMAC-SHA MAC is truncated to 12 bytes."""
    kul = bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")
    msg = b"test message"
    mac = compute_mac(kul, msg, "SHA")
    assert len(mac) == 12


# ---------------------------------------------------------------------------
# compute_mac: tampering detection
# ---------------------------------------------------------------------------


def test_compute_mac_different_messages() -> None:
    """Different messages produce different MACs."""
    kul = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    msg1 = b"original message"
    msg2 = b"tampered message"

    mac1 = compute_mac(kul, msg1, "MD5")
    mac2 = compute_mac(kul, msg2, "MD5")

    assert mac1 != mac2


def test_compute_mac_different_keys() -> None:
    """Different keys produce different MACs."""
    msg = b"test message"
    kul1 = bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")
    kul2 = bytes.fromhex("000000000000000000000000000000d0")

    mac1 = compute_mac(kul1, msg, "MD5")
    mac2 = compute_mac(kul2, msg, "MD5")

    assert mac1 != mac2
