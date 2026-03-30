"""Tests for the notification service."""

from wiregui.services import notifications


def setup_function():
    """Clear notifications before each test."""
    notifications.clear_all()


def test_add_notification():
    n = notifications.add("info", "Test message")
    assert n.severity == "info"
    assert n.message == "Test message"
    assert n.user is None
    assert n.id is not None
    assert n.timestamp is not None


def test_add_notification_with_user():
    n = notifications.add("error", "Something broke", user="admin@example.com")
    assert n.user == "admin@example.com"
    assert n.severity == "error"


def test_current_returns_newest_first():
    notifications.add("info", "First")
    notifications.add("warning", "Second")
    notifications.add("error", "Third")

    current = notifications.current()
    assert len(current) == 3
    assert current[0].message == "Third"
    assert current[1].message == "Second"
    assert current[2].message == "First"


def test_count():
    assert notifications.count() == 0
    notifications.add("info", "One")
    notifications.add("info", "Two")
    assert notifications.count() == 2


def test_clear_specific():
    n1 = notifications.add("info", "Keep this")
    n2 = notifications.add("error", "Remove this")

    notifications.clear(n2.id)
    current = notifications.current()
    assert len(current) == 1
    assert current[0].id == n1.id


def test_clear_nonexistent_id_is_noop():
    notifications.add("info", "Test")
    notifications.clear("nonexistent-id")
    assert notifications.count() == 1


def test_clear_all():
    notifications.add("info", "One")
    notifications.add("info", "Two")
    notifications.add("info", "Three")
    assert notifications.count() == 3

    notifications.clear_all()
    assert notifications.count() == 0
    assert notifications.current() == []


def test_to_dict():
    n = notifications.add("warning", "Test dict", user="someone@example.com")
    d = n.to_dict()
    assert d["severity"] == "warning"
    assert d["message"] == "Test dict"
    assert d["user"] == "someone@example.com"
    assert "id" in d
    assert "timestamp" in d


def test_max_notifications():
    """Deque should cap at MAX_NOTIFICATIONS."""
    for i in range(notifications.MAX_NOTIFICATIONS + 10):
        notifications.add("info", f"Notification {i}")

    assert notifications.count() == notifications.MAX_NOTIFICATIONS
    # Newest should be the last one added
    assert notifications.current()[0].message == f"Notification {notifications.MAX_NOTIFICATIONS + 9}"
