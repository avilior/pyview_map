from __future__ import annotations

import asyncio


class FanOutQueue[T]:
    """Generic bounded-queue fan-out with channel/cid routing.

    Create one instance per command type. Each instance has its own
    subscriber registry, providing isolation without subclassing.

    Usage::

        from pyview_map.views.components.dynamic_map.models.map_events import MapCommand

        command_queue = FanOutQueue[MapCommand]()

        q = command_queue.subscribe(channel="dmap", cid="1")
        command_queue.push(some_cmd, channel="dmap")           # cid="*" broadcast
        command_queue.push(some_cmd, channel="dmap", cid="1")  # targeted
    """

    def __init__(self) -> None:
        # channel → {cid → queue}
        self._subscribers: dict[str, dict[str, asyncio.Queue[T]]] = {}

    def subscribe(self, channel: str, cid: str) -> asyncio.Queue[T]:
        q: asyncio.Queue[T] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(channel, {})[cid] = q
        return q

    def unsubscribe(self, channel: str, cid: str) -> None:
        subs = self._subscribers.get(channel)
        if subs:
            subs.pop(cid, None)

    def push(self, item: T, *, channel: str, cid: str = "*") -> None:
        subs = self._subscribers.get(channel)
        if not subs:
            return

        if cid == "*":
            dead: list[str] = []
            for instance_cid, q in subs.items():
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:
                    dead.append(instance_cid)
            for instance_cid in dead:
                subs.pop(instance_cid, None)
        else:
            q = subs.get(cid)
            if q is not None:
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:
                    subs.pop(cid, None)
