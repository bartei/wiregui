from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class Rule(SQLModel, table=True):
    __tablename__ = "rules"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    action: str = Field(default="drop")  # "drop" | "accept"
    destination: str  # CIDR notation, e.g. "10.0.0.0/8" or "0.0.0.0/0"
    port_type: str | None = None  # "tcp" | "udp" | None (any)
    port_range: str | None = None  # e.g. "80-443" or "22" or None (any)

    # Evaluation order within a chain: lower runs first (top of the nftables chain).
    # nftables evaluates rules top-to-bottom, so e.g. a "drop all" must have a higher
    # priority number than the "accept" rules that should be matched before it.
    priority: int = Field(default=100, index=True)

    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)

    inserted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="rules")


from wiregui.models.user import User  # noqa: E402, F401
