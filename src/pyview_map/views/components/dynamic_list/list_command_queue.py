from __future__ import annotations

import asyncio

from .list_events import ListCommand


class ListCommandQueue:
    """Fan-out queue for list commands from external clients with component_id routing.

    Same pattern as CommandQueue but for list commands.
    """

    # component_id → set of subscriber queues.  None key = "receive all" (broadcast).
    _subscribers: dict[str | None, set[asyncio.Queue[ListCommand]]] = {}

    @classmethod
    def subscribe(cls, *, component_id: str | None = None) -> asyncio.Queue[ListCommand]:
        q: asyncio.Queue[ListCommand] = asyncio.Queue(maxsize=256)
        subs = cls._subscribers.setdefault(component_id, set())
        subs.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue[ListCommand]) -> None:
        for s in cls._subscribers.values():
            s.discard(q)

    @classmethod
    def push(cls, cmd: ListCommand, *, component_id: str | None = None) -> None:
        targets: list[set[asyncio.Queue[ListCommand]]] = []

        if None in cls._subscribers:
            targets.append(cls._subscribers[None])

        if component_id is not None and component_id in cls._subscribers:
            targets.append(cls._subscribers[component_id])

        dead: list[asyncio.Queue[ListCommand]] = []
        seen: set[int] = set()

        for target_set in targets:
            for q in target_set:
                qid = id(q)
                if qid in seen:
                    continue
                seen.add(qid)
                try:
                    q.put_nowait(cmd)
                except asyncio.QueueFull:
                    dead.append(q)

        for q in dead:
            for s in cls._subscribers.values():
                s.discard(q)
