from __future__ import annotations

import asyncio

from pyview_map.views.components.dynamic_map.models.map_events import MapCommand


class CommandQueue:
    """Fan-out queue for map commands from external clients with channel/cid routing.

    Each LiveView connection subscribes and gets its own bounded queue
    identified by a unique cid (channel instance ID).

    Routing:
      - channel: required routing group
      - cid: identifies a specific connection within a channel
      - cid="*": broadcast to all instances of a channel (default for push)

    Slow/dead subscribers are auto-cleaned when their queue fills up.
    """

    # channel → {cid → queue}
    _subscribers: dict[str, dict[str, asyncio.Queue[MapCommand]]] = {}

    @classmethod
    def subscribe(cls, *, channel: str, cid: str) -> asyncio.Queue[MapCommand]:
        q: asyncio.Queue[MapCommand] = asyncio.Queue(maxsize=256)
        subs = cls._subscribers.setdefault(channel, {})
        subs[cid] = q
        return q

    @classmethod
    def unsubscribe(cls, *, channel: str, cid: str) -> None:
        subs = cls._subscribers.get(channel)
        if subs:
            subs.pop(cid, None)

    @classmethod
    def push(cls, cmd: MapCommand, *, channel: str, cid: str = "*") -> None:
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        if cid == "*":
            dead: list[str] = []
            for instance_cid, q in subs.items():
                try:
                    q.put_nowait(cmd)
                except asyncio.QueueFull:
                    dead.append(instance_cid)
            for instance_cid in dead:
                subs.pop(instance_cid, None)
        else:
            q = subs.get(cid)
            if q is not None:
                try:
                    q.put_nowait(cmd)
                except asyncio.QueueFull:
                    subs.pop(cid, None)
