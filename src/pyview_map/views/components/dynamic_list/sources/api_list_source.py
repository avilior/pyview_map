import asyncio

from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem


class APIListSource:
    """List item fan-out source with channel routing.

    Same bounded-queue fan-out pattern as APIMarkerSource.
    Each LiveView connection creates its own instance with a dedicated
    bounded queue. Push methods fan out operations to matching subscriber queues.

    Subscribers are keyed by channel — a required routing group identifier.
    The shared _items dict is partitioned by channel so initial state is isolated.
    """

    # channel → set of subscriber queues
    _subscribers: dict[str, set[asyncio.Queue]] = {}
    # channel → {item_id → DListItem}
    _items: dict[str, dict[str, DListItem]] = {}

    def __init__(self, *, channel: str):
        self._channel = channel
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(channel, set())
        subs.add(self._queue)

    @property
    def items(self) -> list[DListItem]:
        return list(self.__class__._items.get(self._channel, {}).values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, channel: str) -> None:
        """Fan out an op to all subscribers of the given channel."""
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        dead: list[asyncio.Queue] = []
        for q in subs:
            try:
                q.put_nowait(op)
            except asyncio.QueueFull:
                dead.append(q)

        for q in dead:
            subs.discard(q)

    @classmethod
    def push_add(
        cls, id: str, label: str, subtitle: str = "",
        *, at: int = -1, channel: str,
    ) -> None:
        channel_items = cls._items.setdefault(channel, {})
        channel_items[id] = DListItem(id=id, label=label, subtitle=subtitle)
        cls._broadcast(
            {"op": "add", "id": id, "label": label, "subtitle": subtitle, "at": at},
            channel=channel,
        )

    @classmethod
    def push_remove(cls, id: str, *, channel: str) -> None:
        channel_items = cls._items.get(channel, {})
        channel_items.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, channel=channel)

    @classmethod
    def push_clear(cls, *, channel: str) -> None:
        cls._items.pop(channel, None)
        cls._broadcast({"op": "clear"}, channel=channel)
