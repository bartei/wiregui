"""Helpers for turning a desired ordering into stored priority values."""

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

PRIORITY_STEP = 10


def assign_priorities(ordered_ids: Sequence[T], step: int = PRIORITY_STEP) -> dict[T, int]:
    """Map an ordered sequence of ids to spaced priority values.

    The first id gets `step`, the second `2*step`, and so on. Spacing leaves
    room between rules and keeps the lowest-priority number first — matching the
    top-to-bottom evaluation order of an nftables chain.
    """
    return {rule_id: (index + 1) * step for index, rule_id in enumerate(ordered_ids)}
