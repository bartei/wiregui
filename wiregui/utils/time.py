from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime (for Postgres TIMESTAMP WITHOUT TIME ZONE)."""
    return datetime.now(UTC).replace(tzinfo=None)


def connection_status(latest_handshake: datetime | None) -> tuple[str, str]:
    """Return (color, label) based on handshake age.

    Green: handshake < 2 min
    Yellow: handshake < 5 min
    Red: no recent handshake or never connected
    """
    if latest_handshake is None:
        return "red", "offline"
    age = (utcnow() - latest_handshake).total_seconds()
    if age < 120:
        return "green", "online"
    if age < 300:
        return "yellow", "idle"
    return "red", "offline"
