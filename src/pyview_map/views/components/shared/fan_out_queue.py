from __future__ import annotations

import asyncio
from typing import Any


class FanOutQueue:
    """Generic bounded-queue fan-out with channel/cid routing.

    Each subclass gets its own class-level ``_subscribers`` dict via
    ``__init_subclass__``, so different queue types are fully isolated.

    Usage::

        class CommandQueue(FanOutQueue):
            pass

        q = CommandQueue.subscribe(channel="dmap", cid="1")
        CommandQueue.push(some_cmd, channel="dmap")       # cid="*" broadcast
        CommandQueue.push(some_cmd, channel="dmap", cid="1")  # targeted
    """

    _subscribers: dict[str, dict[str, asyncio.Queue]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._subscribers = {}

    @classmethod
    def subscribe(cls, *, channel: str, cid: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        cls._subscribers.setdefault(channel, {})[cid] = q
        return q

    @classmethod
    def unsubscribe(cls, *, channel: str, cid: str) -> None:
        subs = cls._subscribers.get(channel)
        if subs:
            subs.pop(cid, None)

    @classmethod
    def push(cls, item: Any, *, channel: str, cid: str = "*") -> None:
        subs = cls._subscribers.get(channel)
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
