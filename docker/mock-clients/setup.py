#!/usr/bin/env python3
"""Seed the test stack: generate server + client keypairs, write client WG configs,
and insert devices into the database.

Usage: uv run python docker/mock-clients/setup.py

Requires: Postgres running and migrations applied (alembic upgrade head).
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session, engine
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.utils.crypto import generate_keypair, generate_preshared_key

NUM_CLIENTS = 3
SUBNET = "10.3.2"
SERVER_ENDPOINT = "wiregui:51820"
CONFIG_DIR = Path(__file__).parent / "configs"

# Test admin user
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "admin123"

# Client definitions
CLIENTS = [
    {"name": f"test-client-{i}", "ip": f"{SUBNET}.{100 + i}"}
    for i in range(1, NUM_CLIENTS + 1)
]


async def seed():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    async with async_session() as session:
        # --- Server keypair ---
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if config is None:
            config = Configuration()
            session.add(config)
            await session.flush()

        if not config.server_private_key or not config.server_public_key:
            server_priv, server_pub = generate_keypair()
            config.server_private_key = server_priv
            config.server_public_key = server_pub
            session.add(config)
            print(f"  Server keypair generated: {server_pub[:20]}...")
        else:
            server_pub = config.server_public_key
            print(f"  Server keypair already exists: {server_pub[:20]}...")

        # --- Admin user ---
        admin = (await session.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )).scalar_one_or_none()
        if admin is None:
            admin = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
            )
            session.add(admin)
            await session.flush()
            print(f"  Admin user created: {ADMIN_EMAIL}")
        else:
            print(f"  Admin user already exists: {ADMIN_EMAIL}")

        # --- Client devices (delete + recreate for clean state) ---
        client_names = [c["name"] for c in CLIENTS]
        client_ips = [c["ip"] for c in CLIENTS]
        stale = (await session.execute(
            select(Device).where(
                Device.name.in_(client_names) | Device.ipv4.in_(client_ips)
            )
        )).scalars().all()
        for d in stale:
            await session.delete(d)
        if stale:
            await session.flush()
            print(f"  Cleaned up {len(stale)} stale device(s)")

        for client in CLIENTS:
            client_priv, client_pub = generate_keypair()
            psk = generate_preshared_key()

            device = Device(
                name=client["name"],
                public_key=client_pub,
                preshared_key=psk,
                ipv4=client["ip"],
                user_id=admin.id,
            )
            session.add(device)

            client["privkey"] = client_priv
            client["pubkey"] = client_pub
            client["psk"] = psk
            print(f"  Device '{client['name']}' created ({client['ip']})")

        await session.commit()

    # --- Write client WG configs ---
    for i, client in enumerate(CLIENTS):
        conf = f"""[Interface]
PrivateKey = {client["privkey"]}

[Peer]
PublicKey = {server_pub}
PresharedKey = {client["psk"]}
Endpoint = {SERVER_ENDPOINT}
AllowedIPs = {SUBNET}.0/24
PersistentKeepalive = 5
"""
        conf_path = CONFIG_DIR / f"client{i + 1}.conf"
        conf_path.write_text(conf)
        print(f"  Config written: {conf_path}")

    # --- Write env vars for compose ---
    env_lines = []
    for i, client in enumerate(CLIENTS):
        other_ips = " ".join(c["ip"] for c in CLIENTS if c["ip"] != client["ip"])
        env_lines.append(f"CLIENT{i + 1}_IP={client['ip']}")
        env_lines.append(f"CLIENT{i + 1}_PEERS={other_ips}")
    env_path = CONFIG_DIR / "clients.env"
    env_path.write_text("\n".join(env_lines) + "\n")

    await engine.dispose()


def main():
    print("[*] Seeding test stack...")
    asyncio.run(seed())
    print("\n[*] Done. Start the stack with:")
    print("    make test-stack-up")


if __name__ == "__main__":
    main()
