import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import InfoEvent
from pyview.stream import Stream
from pyview.vendor.ibis import filters

from .mock_generator import DMarker


@filters.register
def json_encode(val: Any) -> str:
    return json.dumps(val)


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


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@dataclass
class DynamicMapContext:
    markers: Stream[DMarker]
    last_marker_event: str = ""
    last_map_event: str = ""


# ---------------------------------------------------------------------------
# Generic LiveView
# ---------------------------------------------------------------------------

class DynamicMapLiveView(LiveView[DynamicMapContext]):
    """
    Generic real-time marker map.

    Agnostic of any specific use case — plug in any MarkerSource to drive it.

    Usage:
        app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))
        app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource, tick_interval=2.0, **source_kwargs))

    The view handles:
      - Initial marker render via Stream
      - Periodic ticks (schedule_info) that call source.next_update()
      - Marker and map events from Leaflet forwarded to handle_event
    """

    # Set by with_source(); subclasses can also set these as class attributes.
    source_class: type | None = None
    tick_interval: float = 1.2
    _source_kwargs: dict = {}

    @classmethod
    def with_source(cls, source_class: type, *, tick_interval: float = 1.2, **source_kwargs):
        """Return a configured DynamicMapLiveView class bound to source_class."""
        return type(
            "DynamicMapLiveView",
            (cls,),
            {
                "source_class": source_class,
                "tick_interval": tick_interval,
                "_source_kwargs": source_kwargs,
            },
        )

    async def mount(self, socket: LiveViewSocket[DynamicMapContext], session):
        if self.source_class is None:
            raise RuntimeError(
                "DynamicMapLiveView has no source_class. "
                "Use DynamicMapLiveView.with_source(MySource) when registering the route."
            )
        self._source: MarkerSource = self.source_class(**self._source_kwargs)
        socket.context = DynamicMapContext(
            markers=Stream(self._source.markers, name="markers")
        )
        if socket.connected:
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DynamicMapContext]):
        if event.name != "tick":
            return

        update = self._source.next_update()
        op = update["op"]

        if op == "add":
            socket.context.markers.insert(
                DMarker(id=update["id"], name=update["name"], lat_lng=update["latLng"])
            )
        elif op == "delete":
            socket.context.markers.delete_by_id(f"markers-{update['id']}")
        elif op == "update":
            socket.context.markers.insert(
                DMarker(id=update["id"], name=update["name"], lat_lng=update["latLng"]),
                update_only=True,
            )

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DynamicMapContext]):
        if event == "marker-event":
            evt    = payload.get("event", "?")
            name   = payload.get("name", payload.get("id", "?"))
            latlng = payload.get("latLng")
            detail = f"{evt} → {name}"
            if latlng:
                detail += f" @ ({latlng[0]:.2f}, {latlng[1]:.2f})"
            socket.context.last_marker_event = detail

        elif event == "map-event":
            evt    = payload.get("event", "?")
            center = payload.get("center")
            zoom   = payload.get("zoom")
            detail = evt
            if center:
                detail += f" center=({center[0]:.2f}, {center[1]:.2f})"
            if zoom is not None:
                detail += f" zoom={zoom}"
            socket.context.last_map_event = detail
