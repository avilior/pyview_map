import asyncio

from pyview.template.live_view_template import live_component

from .sources.api_marker_source import marker_source, MarkerSource
from .sources.api_polyline_source import polyline_source
from .sources.command_queue import command_queue
from .icon_registry import icon_registry
from .dynamic_map_component import DynamicMapComponent
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster
from pyview_map.views.components.shared.latlng import LatLng
from pyview_map.views.components.shared.cid import next_cid
from .models.map_events import MapEvent, MapReadyEvent, MarkerEvent, PolylineEvent


class MapDriver:
    """Encapsulates all parent-side plumbing for hosting a DynamicMapComponent.

    A page developer only needs to call connect(), tick(), clear_ops(),
    handle_event(), and render() — no sources, queues, or ops tracking.

    Each driver instance gets a unique cid (channel instance ID) via a
    monotonic counter. The cid is shared across all its subscriptions
    (marker source, polyline source, command queue) and included in
    events so external clients can identify and target specific connections.

    Source routing:
      - Default (no source_class): subscribes to the module-level marker_source.
      - Explicit source_class: uses the given class with source_kwargs as-is.
        The marker source may not need channel/cid (e.g. MockGenerator).
        Polyline source and command queue always use the driver's channel and cid.

    Usage::

        # Simple — default marker_source with channel routing:
        self._map = MapDriver("my-map")

        # Custom source class (e.g. MockGenerator):
        self._map = MapDriver("dmap", source_class=MockGenerator, source_kwargs={"initial_count": 10})
    """

    def __init__(self, channel: str, *, source_class: type | None = None, source_kwargs: dict | None = None):
        self._channel = channel
        self._cid = next_cid()

        if source_class is not None:
            # Explicit source class — use source_kwargs as-is
            kwargs = dict(source_kwargs) if source_kwargs else {}
            self._source: MarkerSource = source_class(**kwargs)
        else:
            # Default: subscribe to the module-level marker_source
            self._source = marker_source.subscribe(channel, self._cid)

        # Polyline source and command queue always use the driver's channel and cid
        self._polyline_reader = polyline_source.subscribe(channel, self._cid)

        self._initial_markers = self._source.items
        self._initial_polylines = self._polyline_reader.items
        self._icon_registry_json = icon_registry.to_json()
        self._marker_ops: list[dict] = []
        self._polyline_ops: list[dict] = []
        self._ops_version: int = 0
        self._cmd_queue: asyncio.Queue | None = None

    @property
    def cid(self) -> str:
        """The channel instance ID for this driver."""
        return self._cid

    def connect(self):
        """Subscribe to CommandQueue. Call when socket.connected."""
        self._cmd_queue = command_queue.subscribe(self._channel, self._cid)

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
            pl_update = self._polyline_reader.next_update()
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
                channel=self._channel,
                cid=self._cid,
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
                channel=self._channel,
                cid=self._cid,
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
                channel=self._channel,
                cid=self._cid,
            )
            detail = me.event
            if me.center:
                detail += f" center=({me.center.lat:.2f}, {me.center.lng:.2f})"
            if me.zoom is not None:
                detail += f" zoom={me.zoom}"
            EventBroadcaster.broadcast(me)
            return detail

        elif event == "map-ready":
            EventBroadcaster.broadcast(MapReadyEvent(
                channel=self._channel, cid=self._cid,
            ))
            return "map ready"

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
