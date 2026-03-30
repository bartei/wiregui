from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DeviceRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    public_key: str
    ipv4: str | None
    ipv6: str | None
    use_default_allowed_ips: bool
    use_default_dns: bool
    use_default_endpoint: bool
    use_default_mtu: bool
    use_default_persistent_keepalive: bool
    endpoint: str | None
    mtu: int | None
    persistent_keepalive: int | None
    allowed_ips: list[str]
    dns: list[str]
    rx_bytes: int | None
    tx_bytes: int | None
    latest_handshake: datetime | None
    user_id: UUID
    inserted_at: datetime
    updated_at: datetime


class DeviceCreate(BaseModel):
    name: str
    description: str | None = None
    user_id: UUID | None = None  # admin can assign to another user


class DeviceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    use_default_allowed_ips: bool | None = None
    use_default_dns: bool | None = None
    use_default_endpoint: bool | None = None
    use_default_mtu: bool | None = None
    use_default_persistent_keepalive: bool | None = None
    endpoint: str | None = None
    mtu: int | None = None
    persistent_keepalive: int | None = None
    allowed_ips: list[str] | None = None
    dns: list[str] | None = None
