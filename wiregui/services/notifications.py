"""In-memory notification queue with severity levels."""

from collections import deque
from datetime import datetime
from typing import Any
from uuid import uuid4

from loguru import logger

from wiregui.utils.time import utcnow

MAX_NOTIFICATIONS = 100


class Notification:
    __slots__ = ("id", "severity", "message", "user", "timestamp")

    def __init__(self, severity: str, message: str, user: str | None = None):
        self.id = str(uuid4())
        self.severity = severity  # "info" | "warning" | "error"
        self.message = message
        self.user = user
        self.timestamp = utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "message": self.message,
            "user": self.user,
            "timestamp": self.timestamp.isoformat(),
        }


_notifications: deque[Notification] = deque(maxlen=MAX_NOTIFICATIONS)


def add(severity: str, message: str, user: str | None = None) -> Notification:
    """Add a notification to the queue."""
    n = Notification(severity, message, user)
    _notifications.appendleft(n)
    logger.debug("Notification added: [{}] {}", severity, message)
    return n


def current() -> list[Notification]:
    """Return all current notifications (newest first)."""
    return list(_notifications)


def clear(notification_id: str) -> None:
    """Remove a specific notification by ID."""
    for i, n in enumerate(_notifications):
        if n.id == notification_id:
            del _notifications[i]
            return


def clear_all() -> None:
    """Remove all notifications."""
    _notifications.clear()


def count() -> int:
    return len(_notifications)
