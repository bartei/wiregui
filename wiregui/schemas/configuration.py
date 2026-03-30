from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConfigurationRead(BaseModel):
    id: UUID
    allow_unprivileged_device_management: bool
    allow_unprivileged_device_configuration: bool
    local_auth_enabled: bool
    disable_vpn_on_oidc_error: bool
    default_client_persistent_keepalive: int
    default_client_mtu: int
    default_client_endpoint: str | None
    default_client_dns: list[str]
    default_client_allowed_ips: list[str]
    vpn_session_duration: int
    logo_url: str | None
    logo_type: str | None
    inserted_at: datetime
    updated_at: datetime


class ConfigurationUpdate(BaseModel):
    allow_unprivileged_device_management: bool | None = None
    allow_unprivileged_device_configuration: bool | None = None
    local_auth_enabled: bool | None = None
    disable_vpn_on_oidc_error: bool | None = None
    default_client_persistent_keepalive: int | None = None
    default_client_mtu: int | None = None
    default_client_endpoint: str | None = None
    default_client_dns: list[str] | None = None
    default_client_allowed_ips: list[str] | None = None
    vpn_session_duration: int | None = None
    logo_url: str | None = None
    logo_type: str | None = None
