from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime.

    SQLModel maps `datetime` fields to TIMESTAMP WITH TIME ZONE and rejects naive
    values, so every datetime that reaches the database must carry an offset.
    """
    return datetime.now(UTC)


def connection_status(latest_handshake: datetime | None) -> tuple[str, str]:
    """Return (color, label) based on handshake age.

    Green: handshake < 2 min
    Yellow: handshake < 5 min
    Red: no recent handshake or never connected
    """
    if latest_handshake is None:
        return "red", "offline"
    if latest_handshake.tzinfo is None:
        latest_handshake = latest_handshake.replace(tzinfo=UTC)
    age = (utcnow() - latest_handshake).total_seconds()
    if age < 120:
        return "green", "online"
    if age < 300:
        return "yellow", "idle"
    return "red", "offline"
