"""WireGuard key generation and encryption utilities — pure Python, no wg CLI needed."""

import base64
import os

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat


def generate_private_key() -> str:
    """Generate a WireGuard private key (Curve25519, base64-encoded)."""
    key = X25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return base64.b64encode(raw).decode()


def derive_public_key(private_key: str) -> str:
    """Derive a WireGuard public key from a private key."""
    raw = base64.b64decode(private_key)
    key = X25519PrivateKey.from_private_bytes(raw)
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(pub).decode()


def generate_keypair() -> tuple[str, str]:
    """Generate a WireGuard keypair. Returns (private_key, public_key)."""
    private_key = generate_private_key()
    public_key = derive_public_key(private_key)
    return private_key, public_key


def generate_preshared_key() -> str:
    """Generate a WireGuard preshared key (32 random bytes, base64-encoded)."""
    return base64.b64encode(os.urandom(32)).decode()
