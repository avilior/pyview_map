from __future__ import annotations

import asyncio

from pyview_map.views.components.dynamic_list.models.list_events import ListCommand


class ListCommandQueue:
    """Fan-out queue for list commands from external clients with channel routing.

    Same pattern as CommandQueue but for list commands.
    Subscribers are keyed by channel — a required routing group identifier.
    """

    # channel → set of subscriber queues
    _subscribers: dict[str, set[asyncio.Queue[ListCommand]]] = {}

    @classmethod
    def subscribe(cls, *, channel: str) -> asyncio.Queue[ListCommand]:
        q: asyncio.Queue[ListCommand] = asyncio.Queue(maxsize=256)
        subs = cls._subscribers.setdefault(channel, set())
        subs.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue[ListCommand]) -> None:
        for s in cls._subscribers.values():
            s.discard(q)

    @classmethod
    def push(cls, cmd: ListCommand, *, channel: str) -> None:
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        dead: list[asyncio.Queue[ListCommand]] = []
        for q in subs:
            try:
                q.put_nowait(cmd)
            except asyncio.QueueFull:
                dead.append(q)

        for q in dead:
            subs.discard(q)
