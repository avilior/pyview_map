import asyncio

from pyview.template.live_view_template import live_component

from .sources.api_marker_source import APIMarkerSource, MarkerSource
from .sources.api_polyline_source import APIPolylineSource
from .sources.command_queue import CommandQueue
from .icon_registry import icon_registry
from .dynamic_map_component import DynamicMapComponent
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster
from pyview_map.views.components.shared.latlng import LatLng
from .models.map_events import MapEvent, MarkerEvent, PolylineEvent


class MapDriver:
    """Encapsulates all parent-side plumbing for hosting a DynamicMapComponent.

    A page developer only needs to call connect(), tick(), clear_ops(),
    handle_event(), and render() — no sources, queues, or ops tracking.

    Source routing:
      - Default (no source_class): uses APIMarkerSource with the driver's channel.
      - Explicit source_class: uses the given class with source_kwargs as-is.
        The marker source may not need a channel (e.g. MockGenerator).
        Polyline source and command queue always use the driver's channel.

    Usage::

        # Simple — default APIMarkerSource with channel routing:
        self._map = MapDriver("my-map")

        # Custom source class (e.g. MockGenerator):
        self._map = MapDriver("dmap", source_class=MockGenerator, source_kwargs={"initial_count": 10})
    """

    def __init__(self, channel: str, *, source_class: type | None = None, source_kwargs: dict | None = None):
        self._channel = channel

        if source_class is not None:
            # Explicit source class — use source_kwargs as-is
            kwargs = dict(source_kwargs) if source_kwargs else {}
            self._source: MarkerSource = source_class(**kwargs)
        else:
            # Default: APIMarkerSource with channel routing
            kwargs = dict(source_kwargs) if source_kwargs else {}
            kwargs.setdefault("channel", channel)
            self._source = APIMarkerSource(**kwargs)

        # Polyline source and command queue always use the driver's channel
        self._polyline_source = APIPolylineSource(channel=channel)

        self._initial_markers = self._source.markers
        self._initial_polylines = self._polyline_source.polylines
        self._icon_registry_json = icon_registry.to_json()
        self._marker_ops: list[dict] = []
        self._polyline_ops: list[dict] = []
        self._ops_version: int = 0
        self._cmd_queue: asyncio.Queue | None = None

    def connect(self):
        """Subscribe to CommandQueue. Call when socket.connected."""
        self._cmd_queue = CommandQueue.subscribe(channel=self._channel)

    async def tick(self, socket):
        """Drain sources + command queue. Push commands via socket. Call from handle_info("tick")."""
        # Drain marker updates
        marker_ops: list[dict] = []
        while True:
            update = self._source.next_update()
            if update["op"] == "noop":
                break
            marker_ops.append(update)

        # Drain polyline updates
        polyline_ops: list[dict] = []
        while True:
            pl_update = self._polyline_source.next_update()
            if pl_update["op"] == "noop":
                break
            polyline_ops.append(pl_update)

        # Drain commands → push_event
        if self._cmd_queue is not None:
            while True:
                try:
                    cmd = self._cmd_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                event_name, payload = cmd.to_push_event(target=self._channel)
                await socket.push_event(event_name, payload)

        self._marker_ops = marker_ops
        self._polyline_ops = polyline_ops
        if marker_ops or polyline_ops:
            self._ops_version += 1

    def clear_ops(self):
        """Clear stale ops so component doesn't re-apply. Call at start of handle_event."""
        self._marker_ops = []
        self._polyline_ops = []

    def handle_event(self, event: str, payload: dict) -> str | None:
        """Parse marker/polyline/map events, broadcast, return summary or None."""
        if event == "marker-event":
            raw_ll = payload.get("latLng", [])
            ll = LatLng.from_list(raw_ll) if raw_ll else LatLng(0, 0)
            me = MarkerEvent(
                event=payload.get("event", "?"),
                id=payload.get("id", ""),
                name=payload.get("name", payload.get("id", "?")),
                latLng=ll,
            )
            detail = f"{me.event} → {me.name}"
            if me.latLng:
                detail += f" @ ({me.latLng.lat:.2f}, {me.latLng.lng:.2f})"
            EventBroadcaster.broadcast(me)
            return detail

        elif event == "polyline-event":
            raw_ll = payload.get("latLng", [])
            ll = LatLng.from_list(raw_ll) if raw_ll else LatLng(0, 0)
            pe = PolylineEvent(
                event=payload.get("event", "?"),
                id=payload.get("id", ""),
                name=payload.get("name", payload.get("id", "?")),
                latLng=ll,
            )
            detail = f"{pe.event} → {pe.name}"
            if pe.latLng:
                detail += f" @ ({pe.latLng.lat:.2f}, {pe.latLng.lng:.2f})"
            EventBroadcaster.broadcast(pe)
            return detail

        elif event == "map-event":
            raw_center = payload.get("center", [])
            raw_ll = payload.get("latLng")
            raw_bounds = payload.get("bounds")
            me = MapEvent(
                event=payload.get("event", "?"),
                center=LatLng.from_list(raw_center) if raw_center else LatLng(0, 0),
                zoom=payload.get("zoom", 0),
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
                bounds=(LatLng.from_list(raw_bounds[0]), LatLng.from_list(raw_bounds[1])) if raw_bounds else None,
            )
            detail = me.event
            if me.center:
                detail += f" center=({me.center.lat:.2f}, {me.center.lng:.2f})"
            if me.zoom is not None:
                detail += f" zoom={me.zoom}"
            EventBroadcaster.broadcast(me)
            return detail

        return None

    def render(self):
        """Return live_component() call with current state."""
        return live_component(DynamicMapComponent, id=self._channel,
            initial_markers=self._initial_markers,
            initial_polylines=self._initial_polylines,
            icon_registry_json=self._icon_registry_json,
            marker_ops=self._marker_ops,
            polyline_ops=self._polyline_ops,
            ops_version=self._ops_version,
            channel=self._channel,
        )
