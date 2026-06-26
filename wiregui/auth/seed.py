"""Seed the initial admin user and server keypair on first startup."""

import secrets
from pathlib import Path

import yaml
from loguru import logger
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User


async def seed_admin() -> None:
    """Create admin user if no users exist in the database."""
    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # users already exist

        settings = get_settings()
        password = settings.admin_password or secrets.token_urlsafe(16)

        admin = User(
            email=settings.admin_email,
            password_hash=hash_password(password),
            role="admin",
        )
        session.add(admin)
        await session.commit()

        logger.info("Admin user created: {}", settings.admin_email)
        logger.warning("Generated admin password: {}", password)


async def ensure_server_keypair() -> None:
    """Generate and store the server WireGuard keypair in Configuration if missing."""
    from wiregui.utils.crypto import generate_keypair

    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()

        if config is None:
            config = Configuration()
            session.add(config)

        if config.server_public_key and config.server_private_key:
            return  # already have keys

        try:
            private_key, public_key = generate_keypair()
            config.server_private_key = private_key
            config.server_public_key = public_key
            session.add(config)
            await session.commit()
            logger.info("Server WireGuard keypair generated (pubkey: {}...)", public_key[:20])
        except Exception as e:
            logger.warning("Could not generate server keypair (wg CLI not available?): {}", e)


def _upsert_providers(existing: list[dict], incoming: list[dict], kind: str) -> list[dict]:
    """Merge incoming providers into existing by `id`, returning the updated list.

    Providers in `incoming` overwrite existing entries with the same `id`.
    Existing providers not present in `incoming` are preserved.
    """
    by_id = {p["id"]: p for p in existing}
    for p in incoming:
        pid = p.get("id")
        if not pid:
            logger.warning("Skipping {} provider without 'id' in IdP config file", kind)
            continue
        action = "updated" if pid in by_id else "added"
        by_id[pid] = p
        logger.info("IdP seed: {} {} provider '{}'", action, kind, pid)
    return list(by_id.values())


async def seed_idp_providers() -> None:
    """Seed OIDC/SAML providers from a YAML config file (if configured).

    Reads WG_IDP_CONFIG_FILE, parses the YAML, and upserts providers into the
    Configuration singleton by `id`. Providers not in the YAML are preserved.
    """
    settings = get_settings()
    if not settings.idp_config_file:
        return

    path = Path(settings.idp_config_file)
    if not path.is_file():
        logger.warning("IdP config file not found: {}", path)
        return

    try:
        data = yaml.safe_load(path.read_text())
    except Exception as e:
        logger.error("Failed to parse IdP config file {}: {}", path, e)
        return

    if not isinstance(data, dict):
        logger.error("IdP config file must be a YAML mapping, got {}", type(data).__name__)
        return

    oidc_incoming = data.get("openid_connect_providers") or []
    saml_incoming = data.get("saml_identity_providers") or []

    if not oidc_incoming and not saml_incoming:
        logger.debug("IdP config file has no providers defined, skipping")
        return

    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()

        if config is None:
            config = Configuration()
            session.add(config)

        if oidc_incoming:
            config.openid_connect_providers = _upsert_providers(
                config.openid_connect_providers or [], oidc_incoming, "OIDC"
            )

        if saml_incoming:
            config.saml_identity_providers = _upsert_providers(
                config.saml_identity_providers or [], saml_incoming, "SAML"
            )

        session.add(config)
        await session.commit()
        logger.info("IdP providers seeded from {}", path)
