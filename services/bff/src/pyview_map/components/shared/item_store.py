from __future__ import annotations


class ItemStore[T]:
    """Channel-partitioned state store for items.

    Maintains shared state for query APIs and initial mount snapshots.
    PubSub handles fan-out notifications to LiveView subscribers.
    """

    def __init__(self) -> None:
        # channel → {item_id → T}
        self._items: dict[str, dict[str, T]] = {}

    def store(self, op: dict, *, channel: str, item: T | None = None) -> None:
        """Update state based on op type (add/update/delete/clear)."""
        match op.get("op"):
            case "add" | "update":
                if item is not None:
                    self._items.setdefault(channel, {})[op["id"]] = item
            case "delete":
                self._items.get(channel, {}).pop(op.get("id", ""), None)
            case "clear":
                self._items.pop(channel, None)

    def channel_items(self, channel: str) -> dict[str, T]:
        """Return the raw item dict for a channel (used by query APIs)."""
        return self._items.get(channel, {})

    def all_items(self, channel: str) -> list[T]:
        """Return all items for a channel as a list (used for initial mount)."""
        return list(self._items.get(channel, {}).values())
