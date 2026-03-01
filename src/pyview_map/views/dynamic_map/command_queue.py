from __future__ import annotations

import asyncio

from .map_events import MapCommand


class CommandQueue:
    """Class-level queue for map commands from external clients.

    JSON-RPC handlers push commands; the LiveView tick drains them.
    """

    _queue: asyncio.Queue[MapCommand] = asyncio.Queue()

    @classmethod
    def push(cls, cmd: MapCommand) -> None:
        cls._queue.put_nowait(cmd)

    @classmethod
    def pop(cls) -> MapCommand | None:
        try:
            return cls._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
