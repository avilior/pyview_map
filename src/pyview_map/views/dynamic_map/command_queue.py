from __future__ import annotations

import asyncio

from .map_events import MapCommand


class CommandQueue:
    """Fan-out queue for map commands from external clients.

    Each LiveView connection subscribes and gets its own bounded queue.
    JSON-RPC handlers push commands; push() fans out to all subscribers.
    Slow/dead subscribers are auto-cleaned when their queue fills up.
    """

    _subscribers: set[asyncio.Queue[MapCommand]] = set()

    @classmethod
    def subscribe(cls) -> asyncio.Queue[MapCommand]:
        q: asyncio.Queue[MapCommand] = asyncio.Queue(maxsize=256)
        cls._subscribers.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue[MapCommand]) -> None:
        cls._subscribers.discard(q)

    @classmethod
    def push(cls, cmd: MapCommand) -> None:
        dead: list[asyncio.Queue[MapCommand]] = []
        for q in cls._subscribers:
            try:
                q.put_nowait(cmd)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            cls._subscribers.discard(q)
