from __future__ import annotations

import asyncio
from typing import Any


class FanOutSource:
    """Generic fan-out source with shared state and channel/cid routing.

    Provides subscriber management, a per-instance bounded queue, shared
    item storage partitioned by channel, and the ``_broadcast`` fan-out
    method.  Subclasses only need to define domain-specific ``push_*``
    class methods and an items property.

    Each subclass gets its own class-level ``_subscribers`` and ``_items``
    dicts via ``__init_subclass__``.

    Usage::

        class APIMarkerSource(FanOutSource):
            @property
            def markers(self) -> list[DMarker]:
                return self._items_list()

            @classmethod
            def push_add(cls, id, name, lat_lng, *, channel, cid="*"):
                cls._store(channel, id, DMarker(...))
                cls._broadcast({...}, channel=channel, cid=cid)
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

    # -- Shared state helpers (called from subclass push_* methods) --

    @classmethod
    def _store(cls, channel: str, id: str, item: Any) -> None:
        cls._items.setdefault(channel, {})[id] = item

    @classmethod
    def _get(cls, channel: str, id: str) -> Any | None:
        return cls._items.get(channel, {}).get(id)

    @classmethod
    def _remove(cls, channel: str, id: str) -> None:
        cls._items.get(channel, {}).pop(id, None)

    @classmethod
    def _clear(cls, channel: str) -> None:
        cls._items.pop(channel, None)

    @classmethod
    def _channel_items(cls, channel: str) -> dict[str, Any]:
        return cls._items.get(channel, {})

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
