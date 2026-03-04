from __future__ import annotations

import asyncio

from .map_events import MapCommand


class CommandQueue:
    """Fan-out queue for map commands from external clients with map_id routing.

    Each LiveView connection subscribes and gets its own bounded queue.
    JSON-RPC handlers push commands; push() fans out to matching subscribers.

    Subscribers are keyed by map_id:
      - subscribe(map_id="fleet") → receives commands targeted at "fleet" AND broadcasts
      - subscribe(map_id=None) → receives ALL commands regardless of target map_id

    Slow/dead subscribers are auto-cleaned when their queue fills up.
    """

    # map_id → set of subscriber queues.  None key = "receive all" (broadcast subscribers).
    _subscribers: dict[str | None, set[asyncio.Queue[MapCommand]]] = {}

    @classmethod
    def subscribe(cls, *, map_id: str | None = None) -> asyncio.Queue[MapCommand]:
        q: asyncio.Queue[MapCommand] = asyncio.Queue(maxsize=256)
        subs = cls._subscribers.setdefault(map_id, set())
        subs.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue[MapCommand]) -> None:
        for s in cls._subscribers.values():
            s.discard(q)

    @classmethod
    def push(cls, cmd: MapCommand, *, map_id: str | None = None) -> None:
        targets: list[set[asyncio.Queue[MapCommand]]] = []

        # Always include broadcast subscribers (map_id=None key)
        if None in cls._subscribers:
            targets.append(cls._subscribers[None])

        # If a specific map_id was given, also include its subscribers
        if map_id is not None and map_id in cls._subscribers:
            targets.append(cls._subscribers[map_id])

        dead: list[asyncio.Queue[MapCommand]] = []
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
