"""SNMP v3 key derivation and MAC computation — RFC 3414."""

from __future__ import annotations

import hashlib
import hmac
from typing import Literal

# RFC 3414 A.2: key derivation buffer size (2^20 bytes)
_KU_BUFFER_SIZE = 1_048_576


def password_to_key(
    password: bytes,
    engine_id: bytes,
    proto: Literal["MD5", "SHA"],
) -> bytes:
    """Derive a localized authentication key from password.

    Implements RFC 3414 Appendix A.2 key localization.

    Args:
        password: User's password (arbitrary bytes)
        engine_id: SNMP engine ID (typically 12 bytes)
        proto: Hash algorithm - "MD5" for MD5, "SHA" for SHA-1

    Returns:
        Localized key: 16 bytes for MD5, 20 bytes for SHA-1
    """
    if not password:
        raise ValueError("password must not be empty")

    if proto == "MD5":
        hash_algo = hashlib.md5
    elif proto == "SHA":
        hash_algo = hashlib.sha1
    else:
        raise ValueError(f"Unsupported protocol: {proto}")

    # Step 1: Repeat password to fill buffer, then hash to get Ku
    ku_input = b""
    while len(ku_input) < _KU_BUFFER_SIZE:
        ku_input += password

    ku_input = ku_input[:_KU_BUFFER_SIZE]  # Trim to exactly _KU_BUFFER_SIZE bytes

    ku = hash_algo(ku_input).digest()

    # Step 2: Localize: Kul = hash(Ku + engineID + Ku)
    kul = hash_algo(ku + engine_id + ku).digest()

    return kul


def compute_mac(
    kul: bytes,
    whole_msg: bytes,
    proto: Literal["MD5", "SHA"],
) -> bytes:
    """Compute SNMP v3 authentication MAC (message integrity code).

    Implements RFC 3414 authentication using HMAC, truncated to 12 bytes.

    Args:
        kul: Localized key (from password_to_key)
        whole_msg: Complete message to authenticate
        proto: Hash algorithm - "MD5" for HMAC-MD5, "SHA" for HMAC-SHA-1

    Returns:
        12-byte authentication MAC
    """
    if proto == "MD5":
        hash_algo = hashlib.md5
    elif proto == "SHA":
        hash_algo = hashlib.sha1
    else:
        raise ValueError(f"Unsupported protocol: {proto}")

    # Compute HMAC and truncate to first 12 bytes
    full_mac = hmac.new(kul, whole_msg, hash_algo).digest()
    return full_mac[:12]
