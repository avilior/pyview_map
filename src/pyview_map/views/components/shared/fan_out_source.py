from __future__ import annotations

import asyncio
from typing import Any


class FanOutSource:
    """Generic fan-out source with shared state and channel/cid routing.

    Provides subscriber management, a per-instance bounded queue, shared
    item storage partitioned by channel, and the broadcast fan-out.

    Each subclass gets its own class-level ``_subscribers`` and ``_items``
    dicts via ``__init_subclass__``.

    Callers use ``push_op`` to store/remove items and broadcast op dicts
    in a single call::

        APIMarkerSource.push_op(
            {"op": "add", "id": "m1", ...},
            channel="dmap",
            item=DMarker(id="m1", ...),
        )
    """

    # channel → {cid → queue}
    _subscribers: dict[str, dict[str, asyncio.Queue]]
    # channel → {item_id → item}
    _items: dict[str, dict[str, Any]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._subscribers = {}
        cls._items = {}

    def __init__(self, *, channel: str, cid: str) -> None:
        self._channel = channel
        self._cid = cid
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(channel, {})
        subs[cid] = self._queue

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    def _items_list(self) -> list:
        """Return the current items for this instance's channel."""
        return list(type(self)._items.get(self._channel, {}).values())

    @classmethod
    def _channel_items(cls, channel: str) -> dict[str, Any]:
        return cls._items.get(channel, {})

    # -- Public API --

    @classmethod
    def push_op(
        cls, op: dict, *, channel: str, cid: str = "*", item: Any = None,
    ) -> None:
        """Store/remove an item and broadcast the op dict.

        For add/update ops, pass ``item`` to store it in shared state.
        For delete ops, the item is removed by ``op["id"]``.
        For clear ops, all items for the channel are removed.
        """
        match op.get("op"):
            case "add" | "update":
                if item is not None:
                    cls._items.setdefault(channel, {})[op["id"]] = item
            case "delete":
                cls._items.get(channel, {}).pop(op.get("id", ""), None)
            case "clear":
                cls._items.pop(channel, None)

        cls._broadcast(op, channel=channel, cid=cid)

    # -- Fan-out --

    @classmethod
    def _broadcast(cls, op: dict, *, channel: str, cid: str = "*") -> None:
        """Fan out an op dict to subscribers of the given channel."""
        subs = cls._subscribers.get(channel)
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
