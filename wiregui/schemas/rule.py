from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RuleRead(BaseModel):
    id: UUID
    action: str
    destination: str
    port_type: str | None
    port_range: str | None
    priority: int
    user_id: UUID | None
    inserted_at: datetime
    updated_at: datetime


class RuleCreate(BaseModel):
    action: str = "drop"
    destination: str
    port_type: str | None = None
    port_range: str | None = None
    priority: int = 100
    user_id: UUID | None = None


class RuleUpdate(BaseModel):
    action: str | None = None
    destination: str | None = None
    port_type: str | None = None
    port_range: str | None = None
    priority: int | None = None
    user_id: UUID | None = None
