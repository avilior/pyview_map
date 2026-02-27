import asyncio

from pyview_map.views.dynamic_map.mock_generator import DMarker


class APIMarkerSource:
    """MarkerSource implementation backed by a class-level asyncio.Queue.

    All LiveView connections share the same queue and marker dict, so updates
    pushed via the HTTP API reach every connected client.
    """

    _queue: asyncio.Queue = asyncio.Queue()
    _markers: dict[str, DMarker] = {}

    @property
    def markers(self) -> list[DMarker]:
        return list(self.__class__._markers.values())

    def next_update(self) -> dict:
        try:
            return self.__class__._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def push_add(cls, id: str, name: str, lat_lng: list[float]) -> None:
        cls._markers[id] = DMarker(id=id, name=name, lat_lng=lat_lng)
        cls._queue.put_nowait({"op": "add", "id": id, "name": name, "latLng": lat_lng})

    @classmethod
    def push_update(cls, id: str, name: str, lat_lng: list[float]) -> None:
        if id in cls._markers:
            cls._markers[id].lat_lng = lat_lng
        cls._queue.put_nowait({"op": "update", "id": id, "name": name, "latLng": lat_lng})

    @classmethod
    def push_delete(cls, id: str) -> None:
        cls._markers.pop(id, None)
        cls._queue.put_nowait({"op": "delete", "id": id})
