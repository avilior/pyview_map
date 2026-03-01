import asyncio

from pyview_map.views.dynamic_map.dmarker import DMarker
from pyview_map.views.dynamic_map.latlng import LatLng


class APIMarkerSource:
    """MarkerSource implementation with per-instance subscriber queues.

    Each LiveView connection creates its own instance, which gets a dedicated
    bounded queue. Push methods fan out operations to all subscriber queues,
    so every connected browser sees every update.

    The shared _markers dict stays class-level so all instances see the same
    current state on mount.
    """

    _subscribers: set[asyncio.Queue] = set()
    _markers: dict[str, DMarker] = {}

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        type(self)._subscribers.add(self._queue)

    @property
    def markers(self) -> list[DMarker]:
        return list(self.__class__._markers.values())

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
    def push_add(cls, id: str, name: str, lat_lng: LatLng) -> None:
        cls._markers[id] = DMarker(id=id, name=name, lat_lng=lat_lng)
        cls._broadcast({"op": "add", "id": id, "name": name, "latLng": lat_lng.to_list()})

    @classmethod
    def push_update(cls, id: str, name: str, lat_lng: LatLng) -> None:
        if id in cls._markers:
            cls._markers[id].lat_lng = lat_lng
        cls._broadcast({"op": "update", "id": id, "name": name, "latLng": lat_lng.to_list()})

    @classmethod
    def push_delete(cls, id: str) -> None:
        cls._markers.pop(id, None)
        cls._broadcast({"op": "delete", "id": id})
