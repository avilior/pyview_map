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
    """MarkerSource implementation with per-instance subscriber queues and component_id routing.

    Each LiveView connection creates its own instance, which gets a dedicated
    bounded queue. Push methods fan out operations to matching subscriber queues.

    Subscribers are keyed by component_id:
      - subscribe(component_id="fleet") → receives ops targeted at "fleet" AND broadcasts (component_id=None)
      - subscribe(component_id=None) → receives ALL ops regardless of target component_id

    The shared _markers dict stays class-level so all instances see the same
    current state on mount.
    """

    # component_id → set of subscriber queues.  None key = "receive all" (broadcast subscribers).
    _subscribers: dict[str | None, set[asyncio.Queue]] = {}
    _markers: dict[str, DMarker] = {}

    def __init__(self, *, component_id: str | None = None):
        self._component_id = component_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(component_id, set())
        subs.add(self._queue)

    @property
    def markers(self) -> list[DMarker]:
        return list(self.__class__._markers.values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, component_id: str | None = None) -> None:
        """Fan out an op to targeted subscribers and broadcast (None-key) subscribers."""
        targets: list[set[asyncio.Queue]] = []

        # Always include broadcast subscribers (component_id=None key)
        if None in cls._subscribers:
            targets.append(cls._subscribers[None])

        # If a specific component_id was given, also include its subscribers
        if component_id is not None and component_id in cls._subscribers:
            targets.append(cls._subscribers[component_id])

        dead: list[tuple[str | None, asyncio.Queue]] = []
        seen: set[int] = set()  # avoid sending to the same queue twice

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
        cls, id: str, name: str, lat_lng: LatLng,
        icon: str = "default", heading: float | None = None, speed: float | None = None,
        *, component_id: str | None = None,
    ) -> None:
        cls._markers[id] = DMarker(id=id, name=name, lat_lng=lat_lng, icon=icon, heading=heading, speed=speed)
        op: dict = {"op": "add", "id": id, "name": name, "latLng": lat_lng.to_list(), "icon": icon}
        if heading is not None:
            op["heading"] = heading
        if speed is not None:
            op["speed"] = speed
        cls._broadcast(op, component_id=component_id)

    @classmethod
    def push_update(
        cls, id: str, name: str, lat_lng: LatLng,
        icon: str = "default", heading: float | None = None, speed: float | None = None,
        *, component_id: str | None = None,
    ) -> None:
        if id in cls._markers:
            cls._markers[id].lat_lng = lat_lng
            cls._markers[id].icon = icon
            cls._markers[id].heading = heading
            cls._markers[id].speed = speed
        op: dict = {"op": "update", "id": id, "name": name, "latLng": lat_lng.to_list(), "icon": icon}
        if heading is not None:
            op["heading"] = heading
        if speed is not None:
            op["speed"] = speed
        cls._broadcast(op, component_id=component_id)

    @classmethod
    def push_delete(cls, id: str, *, component_id: str | None = None) -> None:
        cls._markers.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, component_id=component_id)
