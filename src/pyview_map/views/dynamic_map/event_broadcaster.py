import asyncio

from jrpc_common.jrpc_model import JSONRPCNotification

from .map_events import BroadcastEvent


class EventBroadcaster:
    """Broadcasts map/marker events from the LiveView to SSE subscribers.

    Uses class-level state so all LiveView connections share the same
    broadcaster — same pattern as APIMarkerSource.
    """

    _subscribers: set[asyncio.Queue] = set()

    @classmethod
    def subscribe(cls) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        cls._subscribers.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue) -> None:
        cls._subscribers.discard(q)

    @classmethod
    def broadcast(cls, event: BroadcastEvent) -> None:
        dead: list[asyncio.Queue] = []
        notification = JSONRPCNotification(
            method="notifications/map.event",
            params=event.to_dict(),
        )
        for q in cls._subscribers:
            try:
                q.put_nowait(notification)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            cls._subscribers.discard(q)
