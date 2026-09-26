"""OIDC authentication via authlib — provider registry and authorization code flow."""

import hashlib
import json

from authlib.integrations.starlette_client import OAuth
from loguru import logger

from wiregui.db import async_session
from wiregui.models.configuration import Configuration

# Global OAuth instance — providers are registered dynamically
oauth = OAuth()

# provider_id -> fingerprint of the config it was last registered with, so a provider edited
# in the admin UI is rebuilt instead of keeping the credentials it was booted with.
_registered: dict[str, str] = {}

# The config keys that determine the client authlib builds; a change to any of them means the
# registered client is stale.
_CLIENT_KEYS = ("client_id", "client_secret", "discovery_document_uri", "scope")


def _fingerprint(provider: dict) -> str:
    payload = json.dumps({k: provider.get(k) for k in _CLIENT_KEYS}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def load_providers() -> list[dict]:
    """Load OIDC provider configs from the Configuration singleton."""
    from sqlmodel import select

    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()
        if not config:
            return []
        return config.openid_connect_providers or []


def register_provider(provider: dict) -> None:
    """Register — or re-register — a single provider with authlib.

    A no-op when the provider is already registered with the same settings.
    """
    provider_id = provider.get("id")
    if not provider_id:
        return

    fingerprint = _fingerprint(provider)
    if _registered.get(provider_id) == fingerprint:
        return

    # oauth.register() only replaces the stored *config*: create_client() hands back the
    # instance it built the first time, so without evicting that cache a re-register would
    # silently keep serving the previous client_id/secret.
    oauth._clients.pop(provider_id, None)
    oauth.register(
        name=provider_id,
        client_id=provider.get("client_id"),
        client_secret=provider.get("client_secret"),
        server_metadata_url=provider.get("discovery_document_uri"),
        client_kwargs={"scope": provider.get("scope", "openid email profile")},
    )
    _registered[provider_id] = fingerprint
    logger.info("OIDC provider registered: {}", provider_id)


def unregister_provider(provider_id: str) -> None:
    """Drop a provider from the authlib registry, e.g. once it has been deleted."""
    oauth._registry.pop(provider_id, None)
    oauth._clients.pop(provider_id, None)
    if _registered.pop(provider_id, None) is not None:
        logger.info("OIDC provider unregistered: {}", provider_id)


async def register_providers() -> None:
    """Register all configured OIDC providers with authlib. Call on startup."""
    providers = await load_providers()
    for p in providers:
        try:
            register_provider(p)
        except Exception as e:
            logger.error("Failed to register OIDC provider {}: {}", p.get("id"), e)


async def get_client(provider_id: str):
    """Get an authlib OAuth client for a provider, registering it on demand.

    The provider is resolved from the database on every call rather than trusting the
    registry built at startup. Providers are created and edited in the admin UI while the
    process is running, and a startup-only registry leaves every one of those changes dead
    until the next restart — the login page offers the button (it reads the database) while
    the auth route 307s straight back to /login.
    """
    provider = await get_provider_config(provider_id)
    if provider is None:
        raise ValueError(f"OIDC provider '{provider_id}' is not configured")

    register_provider(provider)

    client = oauth.create_client(provider_id)
    if client is None:
        raise ValueError(f"OIDC provider '{provider_id}' is not registered")
    return client


async def get_provider_config(provider_id: str) -> dict | None:
    """Get the config dict for a specific provider."""
    providers = await load_providers()
    for p in providers:
        if p.get("id") == provider_id:
            return p
    return None
