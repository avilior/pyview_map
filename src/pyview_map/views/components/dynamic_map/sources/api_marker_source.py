from pyview_map.views.components.dynamic_map.models.dmarker import DMarker
from pyview_map.views.components.shared.fan_out_source import FanOutSource
from pyview_map.views.components.shared.latlng import LatLng
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# MarkerSource protocol — implement this to feed any data into DynamicMapLiveView
# ---------------------------------------------------------------------------

@runtime_checkable
class MarkerSource(Protocol):
    """
    A data source that provides markers and a stream of updates.

    Implement this protocol to connect any backend (GPS feed, database,
    simulation, etc.) to DynamicMapLiveView.
    """

    @property
    def markers(self) -> list[DMarker]:
        """Return the current set of markers (used for initial render)."""
        ...

    def next_update(self) -> dict:
        """
        Return the next marker operation as a dict:
            {"op": "add",    "id": str, "name": str, "latLng": [lat, lng]}
            {"op": "delete", "id": str}
            {"op": "update", "id": str, "name": str, "latLng": [lat, lng]}
        """
        ...


class APIMarkerSource(FanOutSource):
    """MarkerSource backed by fan-out queues with channel/cid routing."""

    @property
    def markers(self) -> list[DMarker]:
        return self._items_list()

    @classmethod
    def push_add(
        cls, id: str, name: str, lat_lng: LatLng,
        icon: str = "default", heading: float | None = None, speed: float | None = None,
        *, channel: str, cid: str = "*",
    ) -> None:
        cls._store(channel, id, DMarker(id=id, name=name, lat_lng=lat_lng, icon=icon, heading=heading, speed=speed))
        op: dict = {"op": "add", "id": id, "name": name, "latLng": lat_lng.to_list(), "icon": icon}
        if heading is not None:
            op["heading"] = heading
        if speed is not None:
            op["speed"] = speed
        cls._broadcast(op, channel=channel, cid=cid)

    @classmethod
    def push_update(
        cls, id: str, name: str, lat_lng: LatLng,
        icon: str = "default", heading: float | None = None, speed: float | None = None,
        *, channel: str, cid: str = "*",
    ) -> None:
        existing = cls._get(channel, id)
        if existing is not None:
            existing.lat_lng = lat_lng
            existing.icon = icon
            existing.heading = heading
            existing.speed = speed
        op: dict = {"op": "update", "id": id, "name": name, "latLng": lat_lng.to_list(), "icon": icon}
        if heading is not None:
            op["heading"] = heading
        if speed is not None:
            op["speed"] = speed
        cls._broadcast(op, channel=channel, cid=cid)

    @classmethod
    def push_delete(cls, id: str, *, channel: str, cid: str = "*") -> None:
        cls._remove(channel, id)
        cls._broadcast({"op": "delete", "id": id}, channel=channel, cid=cid)
