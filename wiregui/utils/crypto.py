"""WireGuard key generation and encryption utilities."""

import base64
import os
import subprocess


def generate_private_key() -> str:
    """Generate a WireGuard private key using `wg genkey`."""
    result = subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def derive_public_key(private_key: str) -> str:
    """Derive a WireGuard public key from a private key using `wg pubkey`."""
    result = subprocess.run(
        ["wg", "pubkey"], input=private_key, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def generate_keypair() -> tuple[str, str]:
    """Generate a WireGuard keypair. Returns (private_key, public_key)."""
    private_key = generate_private_key()
    public_key = derive_public_key(private_key)
    return private_key, public_key


def generate_preshared_key() -> str:
    """Generate a WireGuard preshared key (32 random bytes, base64-encoded)."""
    return base64.b64encode(os.urandom(32)).decode()
