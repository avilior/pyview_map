from __future__ import annotations

import asyncio

from pyview_map.views.components.dynamic_map.models.map_events import MapCommand


class CommandQueue:
    """Fan-out queue for map commands from external clients with channel routing.

    Each LiveView connection subscribes and gets its own bounded queue.
    JSON-RPC handlers push commands; push() fans out to matching subscribers.

    Subscribers are keyed by channel — a required routing group identifier.
    Slow/dead subscribers are auto-cleaned when their queue fills up.
    """

    # channel → set of subscriber queues
    _subscribers: dict[str, set[asyncio.Queue[MapCommand]]] = {}

    @classmethod
    def subscribe(cls, *, channel: str) -> asyncio.Queue[MapCommand]:
        q: asyncio.Queue[MapCommand] = asyncio.Queue(maxsize=256)
        subs = cls._subscribers.setdefault(channel, set())
        subs.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue[MapCommand]) -> None:
        for s in cls._subscribers.values():
            s.discard(q)

    @classmethod
    def push(cls, cmd: MapCommand, *, channel: str) -> None:
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        dead: list[asyncio.Queue[MapCommand]] = []
        for q in subs:
            try:
                q.put_nowait(cmd)
            except asyncio.QueueFull:
                dead.append(q)

        for q in dead:
            subs.discard(q)
