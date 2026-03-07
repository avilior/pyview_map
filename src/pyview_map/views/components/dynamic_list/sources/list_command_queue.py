from __future__ import annotations

import asyncio

from pyview_map.views.components.dynamic_list.models.list_events import ListCommand


class ListCommandQueue:
    """Fan-out queue for list commands from external clients with channel/cid routing.

    Same pattern as CommandQueue but for list commands.
    Subscribers are keyed by channel and cid. cid="*" broadcasts to all instances.
    """

    # channel → {cid → queue}
    _subscribers: dict[str, dict[str, asyncio.Queue[ListCommand]]] = {}

    @classmethod
    def subscribe(cls, *, channel: str, cid: str) -> asyncio.Queue[ListCommand]:
        q: asyncio.Queue[ListCommand] = asyncio.Queue(maxsize=256)
        subs = cls._subscribers.setdefault(channel, {})
        subs[cid] = q
        return q

    @classmethod
    def unsubscribe(cls, *, channel: str, cid: str) -> None:
        subs = cls._subscribers.get(channel)
        if subs:
            subs.pop(cid, None)

    @classmethod
    def push(cls, cmd: ListCommand, *, channel: str, cid: str = "*") -> None:
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
