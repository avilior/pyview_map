import asyncio
from typing import Protocol

from jrpc_common.jrpc_model import JSONRPCNotification


class Broadcastable(Protocol):
    notification_method: str
    def to_dict(self) -> dict: ...


class EventBroadcaster:
    """Broadcasts map/marker events from the LiveView to SSE subscribers.

    Uses class-level state so all LiveView connections share the same
    broadcaster.
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
    def broadcast(cls, event: Broadcastable) -> None:
        dead: list[asyncio.Queue] = []
        notification = JSONRPCNotification(
            method=event.notification_method,
            params=event.to_dict(),
        )
        for q in cls._subscribers:
            try:
                q.put_nowait(notification)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            cls._subscribers.discard(q)
