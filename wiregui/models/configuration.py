from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, JSON, Column, SQLModel


class Configuration(SQLModel, table=True):
    __tablename__ = "configurations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Device management permissions
    allow_unprivileged_device_management: bool = Field(default=True)
    allow_unprivileged_device_configuration: bool = Field(default=True)

    # Auth
    local_auth_enabled: bool = Field(default=True)
    disable_vpn_on_oidc_error: bool = Field(default=False)

    # Client defaults
    default_client_persistent_keepalive: int = Field(default=25)
    default_client_mtu: int = Field(default=1280)
    default_client_endpoint: str | None = None
    default_client_dns: list[str] = Field(
        default_factory=lambda: ["1.1.1.1", "1.0.0.1"],
        sa_column=Column(JSON, default=["1.1.1.1", "1.0.0.1"]),
    )
    default_client_allowed_ips: list[str] = Field(
        default_factory=lambda: ["0.0.0.0/0", "::/0"],
        sa_column=Column(JSON, default=["0.0.0.0/0", "::/0"]),
    )

    # Server WireGuard keypair (generated on first startup)
    server_private_key: str | None = None
    server_public_key: str | None = None

    # VPN session
    vpn_session_duration: int = Field(default=0)  # seconds, 0 = unlimited

    # Logo
    logo_url: str | None = None
    logo_type: str | None = None  # "url" | "file" | "upload" | None (default)

    # OIDC providers (list of dicts)
    # Each: {id, label, scope, response_type, client_id, client_secret,
    #         discovery_document_uri, redirect_uri, auto_create_users}
    openid_connect_providers: list[dict] = Field(
        default_factory=list, sa_column=Column(JSON, default=[])
    )

    # SAML identity providers (list of dicts)
    # Each: {id, label, base_url, metadata, sign_requests, sign_metadata,
    #         signed_assertion_in_resp, signed_envelopes_in_resp, auto_create_users}
    saml_identity_providers: list[dict] = Field(
        default_factory=list, sa_column=Column(JSON, default=[])
    )

    inserted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
