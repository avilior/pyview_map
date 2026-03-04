import asyncio

from pyview_map.views.dynamic_map.dpolyline import DPolyline
from pyview_map.views.dynamic_map.latlng import LatLng


class APIPolylineSource:
    """Polyline fan-out source with map_id routing — structural clone of APIMarkerSource.

    Each LiveView connection creates its own instance with a dedicated
    bounded queue. Push methods fan out operations to matching subscriber queues.

    Subscribers are keyed by map_id:
      - subscribe with map_id="fleet" → receives ops targeted at "fleet" AND broadcasts
      - subscribe with map_id=None → receives ALL ops regardless of target map_id

    The shared _polylines dict stays class-level so all instances see the
    same current state on mount.
    """

    # map_id → set of subscriber queues.  None key = "receive all" (broadcast subscribers).
    _subscribers: dict[str | None, set[asyncio.Queue]] = {}
    _polylines: dict[str, DPolyline] = {}

    def __init__(self, *, map_id: str | None = None):
        self._map_id = map_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(map_id, set())
        subs.add(self._queue)

    @property
    def polylines(self) -> list[DPolyline]:
        return list(self.__class__._polylines.values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, map_id: str | None = None) -> None:
        """Fan out an op to targeted subscribers and broadcast (None-key) subscribers."""
        targets: list[set[asyncio.Queue]] = []

        if None in cls._subscribers:
            targets.append(cls._subscribers[None])

        if map_id is not None and map_id in cls._subscribers:
            targets.append(cls._subscribers[map_id])

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
                    dead.append((map_id, q))

        for key, q in dead:
            for s in cls._subscribers.values():
                s.discard(q)

    @classmethod
    def push_add(
        cls,
        id: str,
        name: str,
        path: list[LatLng],
        color: str = "#3388ff",
        weight: int = 3,
        opacity: float = 1.0,
        dash_array: str | None = None,
        *,
        map_id: str | None = None,
    ) -> None:
        cls._polylines[id] = DPolyline(
            id=id, name=name, path=path,
            color=color, weight=weight, opacity=opacity, dash_array=dash_array,
        )
        op: dict = {
            "op": "add", "id": id, "name": name,
            "path": [ll.to_list() for ll in path],
            "color": color, "weight": weight, "opacity": opacity,
        }
        if dash_array is not None:
            op["dashArray"] = dash_array
        cls._broadcast(op, map_id=map_id)

    @classmethod
    def push_update(
        cls,
        id: str,
        name: str,
        path: list[LatLng],
        color: str = "#3388ff",
        weight: int = 3,
        opacity: float = 1.0,
        dash_array: str | None = None,
        *,
        map_id: str | None = None,
    ) -> None:
        if id in cls._polylines:
            p = cls._polylines[id]
            p.path = path
            p.name = name
            p.color = color
            p.weight = weight
            p.opacity = opacity
            p.dash_array = dash_array
        op: dict = {
            "op": "update", "id": id, "name": name,
            "path": [ll.to_list() for ll in path],
            "color": color, "weight": weight, "opacity": opacity,
        }
        if dash_array is not None:
            op["dashArray"] = dash_array
        cls._broadcast(op, map_id=map_id)

    @classmethod
    def push_delete(cls, id: str, *, map_id: str | None = None) -> None:
        cls._polylines.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, map_id=map_id)
