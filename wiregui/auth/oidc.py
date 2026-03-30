"""OIDC authentication via authlib — provider registry and authorization code flow."""

from authlib.integrations.starlette_client import OAuth
from loguru import logger

from wiregui.db import async_session
from wiregui.models.configuration import Configuration

# Global OAuth instance — providers are registered dynamically
oauth = OAuth()


async def load_providers() -> list[dict]:
    """Load OIDC provider configs from the Configuration singleton."""
    from sqlmodel import select

    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()
        if not config:
            return []
        return config.openid_connect_providers or []


async def register_providers() -> None:
    """Register all configured OIDC providers with authlib. Call on startup."""
    providers = await load_providers()
    for p in providers:
        provider_id = p.get("id")
        if not provider_id:
            continue
        try:
            oauth.register(
                name=provider_id,
                client_id=p.get("client_id"),
                client_secret=p.get("client_secret"),
                server_metadata_url=p.get("discovery_document_uri"),
                client_kwargs={"scope": p.get("scope", "openid email profile")},
            )
            logger.info("OIDC provider registered: {}", provider_id)
        except Exception as e:
            logger.error("Failed to register OIDC provider {}: {}", provider_id, e)


def get_client(provider_id: str):
    """Get an authlib OAuth client for a registered provider."""
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
