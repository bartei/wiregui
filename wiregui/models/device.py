from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlalchemy import BigInteger
from sqlmodel import Field, JSON, Column, Relationship, SQLModel


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    description: str | None = None

    public_key: str = Field(unique=True, index=True)
    preshared_key: str | None = None  # encrypted at application level

    # Client config: use server defaults or per-device overrides
    use_default_allowed_ips: bool = Field(default=True)
    use_default_dns: bool = Field(default=True)
    use_default_endpoint: bool = Field(default=True)
    use_default_mtu: bool = Field(default=True)
    use_default_persistent_keepalive: bool = Field(default=True)

    # Per-device overrides (used when use_default_* is False)
    endpoint: str | None = None
    mtu: int | None = None
    persistent_keepalive: int | None = None
    allowed_ips: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=[]))
    dns: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=[]))

    # Assigned tunnel addresses
    ipv4: str | None = Field(default=None, unique=True)
    ipv6: str | None = Field(default=None, unique=True)

    # Peer stats (updated periodically from WireGuard)
    remote_ip: str | None = None
    # BigInteger: WireGuard byte counters routinely exceed the int32 range (~2 GB);
    # a plain Integer column overflows and aborts the collector's commit.
    rx_bytes: int | None = Field(default=None, sa_column=Column(BigInteger))
    tx_bytes: int | None = Field(default=None, sa_column=Column(BigInteger))
    latest_handshake: datetime | None = None

    user_id: UUID = Field(foreign_key="users.id", index=True)

    inserted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="devices")


from wiregui.models.user import User  # noqa: E402, F401
