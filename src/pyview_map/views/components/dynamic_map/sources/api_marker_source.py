import asyncio

from pyview_map.views.components.dynamic_map.models.dmarker import DMarker
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


class APIMarkerSource:
    """MarkerSource implementation with per-instance subscriber queues and channel routing.

    Each LiveView connection creates its own instance, which gets a dedicated
    bounded queue. Push methods fan out operations to matching subscriber queues.

    Subscribers are keyed by channel — a required routing group identifier.
    All instances subscribed to the same channel receive the same ops.

    The shared _markers dict is partitioned by channel so initial state is isolated.
    """

    # channel → set of subscriber queues
    _subscribers: dict[str, set[asyncio.Queue]] = {}
    # channel → {marker_id → DMarker}
    _markers: dict[str, dict[str, DMarker]] = {}

    def __init__(self, *, channel: str):
        self._channel = channel
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(channel, set())
        subs.add(self._queue)

    @property
    def markers(self) -> list[DMarker]:
        return list(self.__class__._markers.get(self._channel, {}).values())

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
        cls, id: str, name: str, lat_lng: LatLng,
        icon: str = "default", heading: float | None = None, speed: float | None = None,
        *, channel: str,
    ) -> None:
        channel_markers = cls._markers.setdefault(channel, {})
        channel_markers[id] = DMarker(id=id, name=name, lat_lng=lat_lng, icon=icon, heading=heading, speed=speed)
        op: dict = {"op": "add", "id": id, "name": name, "latLng": lat_lng.to_list(), "icon": icon}
        if heading is not None:
            op["heading"] = heading
        if speed is not None:
            op["speed"] = speed
        cls._broadcast(op, channel=channel)

    @classmethod
    def push_update(
        cls, id: str, name: str, lat_lng: LatLng,
        icon: str = "default", heading: float | None = None, speed: float | None = None,
        *, channel: str,
    ) -> None:
        channel_markers = cls._markers.get(channel, {})
        if id in channel_markers:
            channel_markers[id].lat_lng = lat_lng
            channel_markers[id].icon = icon
            channel_markers[id].heading = heading
            channel_markers[id].speed = speed
        op: dict = {"op": "update", "id": id, "name": name, "latLng": lat_lng.to_list(), "icon": icon}
        if heading is not None:
            op["heading"] = heading
        if speed is not None:
            op["speed"] = speed
        cls._broadcast(op, channel=channel)

    @classmethod
    def push_delete(cls, id: str, *, channel: str) -> None:
        channel_markers = cls._markers.get(channel, {})
        channel_markers.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, channel=channel)
