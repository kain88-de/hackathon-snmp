"""SNMP v3 key derivation and MAC computation — RFC 3414."""

from __future__ import annotations

import hashlib
import hmac
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class AuthProto(StrEnum):
    """Authentication protocol for SNMP v3 (RFC 3414 / RFC 7860)."""

    MD5 = "MD5"
    SHA = "SHA"
    SHA256 = "SHA-256"

    @property
    def hash_algo(self) -> Callable[..., Any]:
        if self is AuthProto.MD5:
            return hashlib.md5
        if self is AuthProto.SHA:
            return hashlib.sha1
        return hashlib.sha256

    @property
    def key_length(self) -> int:
        if self is AuthProto.MD5:
            return 16
        if self is AuthProto.SHA:
            return 20
        return 32

    @property
    def mac_length(self) -> int:
        if self is AuthProto.MD5:
            return 12
        if self is AuthProto.SHA:
            return 12
        return 24


# RFC 3414 A.2: key derivation buffer size (2^20 bytes)
_KU_BUFFER_SIZE = 1_048_576

# RFC 3414 §11.2 recommends a minimum passphrase length of 8 characters to
# resist dictionary attacks against the derived key. This is not enforced
# here — a real device may be configured with a shorter one — but is used
# by the CLI to warn when --auth-pass falls below it.
MIN_PASSWORD_LENGTH = 8


def password_to_key(
    password: bytes,
    engine_id: bytes,
    proto: AuthProto,
) -> bytes:
    """Derive a localized authentication key from password.

    Implements RFC 3414 Appendix A.2 key localization.

    Args:
        password: User's password (arbitrary bytes)
        engine_id: SNMP engine ID (typically 12 bytes)
        proto: Hash algorithm - "MD5" for MD5, "SHA" for SHA-1, "SHA-256" for SHA-256

    Returns:
        Localized key: 16 bytes for MD5, 20 bytes for SHA-1, 32 bytes for SHA-256
    """
    if not password:
        raise ValueError("password must not be empty")

    hash_algo = proto.hash_algo

    # Step 1: Repeat password to fill buffer, then hash to get Ku
    reps = -(-_KU_BUFFER_SIZE // len(password))  # ceiling division
    ku_input = (password * reps)[:_KU_BUFFER_SIZE]

    ku = hash_algo(ku_input).digest()

    # Step 2: Localize: Kul = hash(Ku + engineID + Ku)
    kul = hash_algo(ku + engine_id + ku).digest()

    return kul


def compute_mac(
    kul: bytes,
    whole_msg: bytes,
    proto: AuthProto,
) -> bytes:
    """Compute SNMP v3 authentication MAC (message integrity code).

    Implements RFC 3414 / RFC 7860 authentication using HMAC, truncated per protocol.

    Args:
        kul: Localized key (from password_to_key)
        whole_msg: Complete message to authenticate
        proto: Hash algorithm - "MD5" for HMAC-MD5, "SHA" for HMAC-SHA-1, "SHA-256" for HMAC-SHA-256

    Returns:
        Truncated authentication MAC: 12 bytes for MD5/SHA-1, 24 bytes for SHA-256
    """
    hash_algo = proto.hash_algo

    # Compute HMAC and truncate to protocol-defined length
    full_mac = hmac.new(kul, whole_msg, hash_algo).digest()
    return full_mac[: proto.mac_length]
