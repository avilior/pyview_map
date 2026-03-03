import asyncio

from pyview_map.views.dynamic_map.dpolyline import DPolyline
from pyview_map.views.dynamic_map.latlng import LatLng


class APIPolylineSource:
    """Polyline fan-out source — structural clone of APIMarkerSource.

    Each LiveView connection creates its own instance with a dedicated
    bounded queue. Push methods fan out operations to all subscriber queues.
    The shared _polylines dict stays class-level so all instances see the
    same current state on mount.
    """

    _subscribers: set[asyncio.Queue] = set()
    _polylines: dict[str, DPolyline] = {}

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        type(self)._subscribers.add(self._queue)

    @property
    def polylines(self) -> list[DPolyline]:
        return list(self.__class__._polylines.values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict) -> None:
        dead: list[asyncio.Queue] = []
        for q in cls._subscribers:
            try:
                q.put_nowait(op)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            cls._subscribers.discard(q)

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
        cls._broadcast(op)

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
        cls._broadcast(op)

    @classmethod
    def push_delete(cls, id: str) -> None:
        cls._polylines.pop(id, None)
        cls._broadcast({"op": "delete", "id": id})
