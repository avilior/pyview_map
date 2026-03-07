from __future__ import annotations

import asyncio
from typing import Any


class FanOutReader:
    """Per-connection reader returned by ``FanOutSource.subscribe()``.

    Provides ``next_update()`` to drain the instance queue and an ``items``
    property for the current shared state of the channel.
    """

    def __init__(self, source: FanOutSource, channel: str) -> None:
        self._source = source
        self._channel = channel
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @property
    def items(self) -> list:
        """Current items for this reader's channel."""
        return list(self._source._items.get(self._channel, {}).values())


class FanOutSource:
    """Generic fan-out source with shared state and channel/cid routing.

    Create one instance per data type (markers, polylines, list items).
    Each instance has its own subscriber registry and item storage.

    Usage::

        # Module level — one per data type:
        marker_source = FanOutSource()
        polyline_source = FanOutSource()

        # Driver subscribes to get a reader:
        reader = marker_source.subscribe(channel="dmap", cid="1")
        initial = reader.items        # shared state snapshot
        update = reader.next_update() # drain per-connection queue

        # API layer pushes ops:
        marker_source.push_op({"op": "add", "id": "m1", ...}, channel="dmap", item=marker)
    """

    def __init__(self) -> None:
        # channel → {cid → queue}
        self._subscribers: dict[str, dict[str, asyncio.Queue]] = {}
        # channel → {item_id → item}
        self._items: dict[str, dict[str, Any]] = {}

    def subscribe(self, channel: str, cid: str) -> FanOutReader:
        """Create a reader for the given channel and cid."""
        reader = FanOutReader(self, channel)
        self._subscribers.setdefault(channel, {})[cid] = reader._queue
        return reader

    def unsubscribe(self, channel: str, cid: str) -> None:
        subs = self._subscribers.get(channel)
        if subs:
            subs.pop(cid, None)

    def channel_items(self, channel: str) -> dict[str, Any]:
        """Return the raw item dict for a channel (used by list/query APIs)."""
        return self._items.get(channel, {})

    def push_op(
        self, op: dict, *, channel: str, cid: str = "*", item: Any = None,
    ) -> None:
        """Store/remove an item and broadcast the op dict.

        For add/update ops, pass ``item`` to store it in shared state.
        For delete ops, the item is removed by ``op["id"]``.
        For clear ops, all items for the channel are removed.
        """
        match op.get("op"):
            case "add" | "update":
                if item is not None:
                    self._items.setdefault(channel, {})[op["id"]] = item
            case "delete":
                self._items.get(channel, {}).pop(op.get("id", ""), None)
            case "clear":
                self._items.pop(channel, None)

        self._broadcast(op, channel=channel, cid=cid)

    def _broadcast(self, op: dict, *, channel: str, cid: str = "*") -> None:
        """Fan out an op dict to subscribers of the given channel."""
        subs = self._subscribers.get(channel)
        if not subs:
            return

        if cid == "*":
            dead: list[str] = []
            for instance_cid, q in subs.items():
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    dead.append(instance_cid)
            for instance_cid in dead:
                subs.pop(instance_cid, None)
        else:
            q = subs.get(cid)
            if q is not None:
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    subs.pop(cid, None)
