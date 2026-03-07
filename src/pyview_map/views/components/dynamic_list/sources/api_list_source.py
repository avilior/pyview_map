import asyncio

from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem


class APIListSource:
    """List item fan-out source with channel/cid routing.

    Same bounded-queue fan-out pattern as APIMarkerSource.
    Subscribers are keyed by channel and cid. cid="*" broadcasts to all instances.
    The shared _items dict is partitioned by channel so initial state is isolated.
    """

    # channel → {cid → queue}
    _subscribers: dict[str, dict[str, asyncio.Queue]] = {}
    # channel → {item_id → DListItem}
    _items: dict[str, dict[str, DListItem]] = {}

    def __init__(self, *, channel: str, cid: str):
        self._channel = channel
        self._cid = cid
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(channel, {})
        subs[cid] = self._queue

    @property
    def items(self) -> list[DListItem]:
        return list(self.__class__._items.get(self._channel, {}).values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, channel: str, cid: str = "*") -> None:
        """Fan out an op to subscribers of the given channel.

        cid="*" broadcasts to all instances; a specific cid targets one instance.
        """
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        if cid == "*":
            dead: list[str] = []
            for instance_cid, q in subs.items():
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    dead.append(instance_cid)
            for instance_cid in dead:
                subs.pop(instance_cid, None)
        else:
            q = subs.get(cid)
            if q is not None:
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    subs.pop(cid, None)

    @classmethod
    def push_add(
        cls, id: str, label: str, subtitle: str = "",
        *, at: int = -1, channel: str, cid: str = "*",
    ) -> None:
        channel_items = cls._items.setdefault(channel, {})
        channel_items[id] = DListItem(id=id, label=label, subtitle=subtitle)
        cls._broadcast(
            {"op": "add", "id": id, "label": label, "subtitle": subtitle, "at": at},
            channel=channel, cid=cid,
        )

    @classmethod
    def push_remove(cls, id: str, *, channel: str, cid: str = "*") -> None:
        channel_items = cls._items.get(channel, {})
        channel_items.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, channel=channel, cid=cid)

    @classmethod
    def push_clear(cls, *, channel: str, cid: str = "*") -> None:
        cls._items.pop(channel, None)
        cls._broadcast({"op": "clear"}, channel=channel, cid=cid)
