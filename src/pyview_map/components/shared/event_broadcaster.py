import asyncio
from typing import Protocol, runtime_checkable

from jrpc_common.jrpc_model import JSONRPCNotification


class Broadcastable(Protocol):
    notification_method: str

    def to_dict(self) -> dict: ...


@runtime_checkable
class Retainable(Protocol):
    """Events that should be stored and replayed to new subscribers."""

    def retained_key(self) -> str: ...


class EventBroadcaster:
    """Broadcasts map/marker events from the LiveView to SSE subscribers.

    Uses class-level state so all LiveView connections share the same
    broadcaster.

    Events that implement ``retained_key() -> str`` are stored and replayed
    to new subscribers (like MQTT retained messages).  This guarantees that
    late subscribers always receive ready events regardless of timing.
    """

    _subscribers: set[asyncio.Queue] = set()
    _retained: dict[str, JSONRPCNotification] = {}

    @classmethod
    def subscribe(cls) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        for notification in cls._retained.values():
            q.put_nowait(notification)
        cls._subscribers.add(q)
        return q

    @classmethod
    def unsubscribe(cls, q: asyncio.Queue) -> None:
        cls._subscribers.discard(q)

    @classmethod
    def broadcast(cls, event: Broadcastable) -> None:
        dead: list[asyncio.Queue] = []
        notification = JSONRPCNotification(method=event.notification_method, params=event.to_dict())

        if isinstance(event, Retainable):
            cls._retained[event.retained_key()] = notification

        for q in cls._subscribers:
            try:
                q.put_nowait(notification)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            cls._subscribers.discard(q)

    @classmethod
    def clear_retained(cls, key: str) -> None:
        """Remove a retained event by key."""
        cls._retained.pop(key, None)
