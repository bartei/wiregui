"""WireGuard key generation and encryption utilities."""

import asyncio
import base64
import os


async def generate_private_key() -> str:
    """Generate a WireGuard private key using `wg genkey`."""
    proc = await asyncio.create_subprocess_exec(
        "wg", "genkey", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("wg genkey failed")
    return stdout.decode().strip()


async def derive_public_key(private_key: str) -> str:
    """Derive a WireGuard public key from a private key using `wg pubkey`."""
    proc = await asyncio.create_subprocess_exec(
        "wg", "pubkey", stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate(input=private_key.encode())
    if proc.returncode != 0:
        raise RuntimeError("wg pubkey failed")
    return stdout.decode().strip()


async def generate_keypair() -> tuple[str, str]:
    """Generate a WireGuard keypair. Returns (private_key, public_key)."""
    private_key = await generate_private_key()
    public_key = await derive_public_key(private_key)
    return private_key, public_key


def generate_preshared_key() -> str:
    """Generate a WireGuard preshared key (32 random bytes, base64-encoded)."""
    return base64.b64encode(os.urandom(32)).decode()
