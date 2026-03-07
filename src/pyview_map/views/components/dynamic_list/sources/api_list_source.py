import asyncio

from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem


class APIListSource:
    """List item fan-out source with component_id routing.

    Same bounded-queue fan-out pattern as APIMarkerSource.
    Each LiveView connection creates its own instance with a dedicated
    bounded queue. Push methods fan out operations to matching subscriber queues.
    """

    # component_id → set of subscriber queues.  None key = "receive all" (broadcast).
    _subscribers: dict[str | None, set[asyncio.Queue]] = {}
    _items: dict[str, DListItem] = {}

    def __init__(self, *, component_id: str | None = None):
        self._component_id = component_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(component_id, set())
        subs.add(self._queue)

    @property
    def items(self) -> list[DListItem]:
        return list(self.__class__._items.values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, component_id: str | None = None) -> None:
        """Fan out an op to targeted subscribers and broadcast (None-key) subscribers."""
        targets: list[set[asyncio.Queue]] = []

        if None in cls._subscribers:
            targets.append(cls._subscribers[None])

        if component_id is not None and component_id in cls._subscribers:
            targets.append(cls._subscribers[component_id])

        dead: list[tuple[str | None, asyncio.Queue]] = []
        seen: set[int] = set()

        for target_set in targets:
            for q in target_set:
                qid = id(q)
                if qid in seen:
                    continue
                seen.add(qid)
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    dead.append((component_id, q))

        for key, q in dead:
            for s in cls._subscribers.values():
                s.discard(q)

    @classmethod
    def push_add(
        cls, id: str, label: str, subtitle: str = "",
        *, at: int = -1, component_id: str | None = None,
    ) -> None:
        cls._items[id] = DListItem(id=id, label=label, subtitle=subtitle)
        cls._broadcast(
            {"op": "add", "id": id, "label": label, "subtitle": subtitle, "at": at},
            component_id=component_id,
        )

    @classmethod
    def push_remove(cls, id: str, *, component_id: str | None = None) -> None:
        cls._items.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, component_id=component_id)

    @classmethod
    def push_clear(cls, *, component_id: str | None = None) -> None:
        cls._items.clear()
        cls._broadcast({"op": "clear"}, component_id=component_id)
