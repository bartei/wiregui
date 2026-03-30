from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, JSON, Column, SQLModel


class ConnectivityCheck(SQLModel, table=True):
    __tablename__ = "connectivity_checks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    url: str
    response_code: int | None = None
    response_headers: dict | None = Field(default=None, sa_column=Column(JSON))
    response_body: str | None = None

    inserted_at: datetime = Field(default_factory=utcnow)
