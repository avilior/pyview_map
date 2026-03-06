import asyncio

from dataclasses import dataclass, field


from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import TemplateView
from pyview.template.live_view_template import live_component

from pyview_map.views.components.dynamic_map.api_polyline_source import APIPolylineSource
from pyview_map.views.components.dynamic_map.api_marker_source import MarkerSource
from pyview_map.views.components.dynamic_map.command_queue import CommandQueue
from pyview_map.views.components.dynamic_map.dmarker import DMarker
from pyview_map.views.components.dynamic_map.event_broadcaster import EventBroadcaster
from pyview_map.views.components.dynamic_map.icon_registry import icon_registry
from pyview_map.views.components.dynamic_map.latlng import LatLng
from pyview_map.views.components.dynamic_map.map_events import MapEvent, MarkerEvent, PolylineEvent
from pyview_map.views.components.dynamic_map.dynamic_map_component import DynamicMapComponent
from pyview_map.views.components.dynamic_map.dpolyline import DPolyline
# ---------------------------------------------------------------------------
# Parent LiveView — drives ticks, drains sources, embeds map component
# ---------------------------------------------------------------------------

@dataclass
class DynamicMapPageContext:
    initial_markers: list[DMarker] = field(default_factory=list)
    initial_polylines: list[DPolyline] = field(default_factory=list)
    icon_registry_json: str = ""
    last_marker_event: str = ""
    last_map_event: str = ""
    last_polyline_event: str = ""
    marker_ops: list[dict] = field(default_factory=list)
    polyline_ops: list[dict] = field(default_factory=list)
    ops_version: int = 0


class DynamicMapLiveView(TemplateView, LiveView[DynamicMapPageContext]):
    """
    Generic real-time marker map.

    Agnostic of any specific use case — plug in any MarkerSource to drive it.

    Usage:
        app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))
        app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource, tick_interval=2.0, **source_kwargs))

    The view handles:
      - Initial marker render via Stream (inside DynamicMapComponent)
      - Periodic ticks (schedule_info) that drain sources and pass ops to component
      - Marker and map events from Leaflet forwarded to handle_event
      - Map commands from CommandQueue pushed via socket.push_event
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

    async def mount(self, socket: LiveViewSocket[DynamicMapPageContext], session):
        if self.source_class is None:
            raise RuntimeError(
                "DynamicMapLiveView has no source_class. "
                "Use DynamicMapLiveView.with_source(MySource) when registering the route."
            )
        self._source: MarkerSource = self.source_class(**self._source_kwargs)
        self._polyline_source = APIPolylineSource()
        socket.context = DynamicMapPageContext(
            initial_markers=self._source.markers,
            initial_polylines=self._polyline_source.polylines,
            icon_registry_json=icon_registry.to_json(),
        )
        if socket.connected:
            self._cmd_queue = CommandQueue.subscribe()
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DynamicMapPageContext]):
        if event.name != "tick":
            return

        # Drain all pending marker updates
        marker_ops: list[dict] = []
        while True:
            update = self._source.next_update()
            if update["op"] == "noop":
                break
            marker_ops.append(update)

        # Drain all pending polyline updates
        polyline_ops: list[dict] = []
        while True:
            pl_update = self._polyline_source.next_update()
            if pl_update["op"] == "noop":
                break
            polyline_ops.append(pl_update)

        # Drain pending map commands — push directly via socket.push_event
        while True:
            try:
                cmd = self._cmd_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            event_name, payload = cmd.to_push_event(target="dmap")
            await socket.push_event(event_name, payload)

        # Store ops for the component; bump version so component applies them once
        socket.context.marker_ops = marker_ops
        socket.context.polyline_ops = polyline_ops
        if marker_ops or polyline_ops:
            socket.context.ops_version += 1

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DynamicMapPageContext]):
        # Clear stale ops so component doesn't re-apply on this re-render
        socket.context.marker_ops = []
        socket.context.polyline_ops = []

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
            socket.context.last_marker_event = detail
            EventBroadcaster.broadcast(me)

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
            socket.context.last_polyline_event = detail
            EventBroadcaster.broadcast(pe)

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
            socket.context.last_map_event = detail
            EventBroadcaster.broadcast(me)

    def template(self, assigns: DynamicMapPageContext, meta: PyViewMeta):
        last_me = assigns.last_marker_event
        last_mae = assigns.last_map_event
        last_pe = assigns.last_polyline_event

        comp = live_component(DynamicMapComponent, id="dmap",
            initial_markers=assigns.initial_markers,
            initial_polylines=assigns.initial_polylines,
            icon_registry_json=assigns.icon_registry_json,
            marker_ops=assigns.marker_ops,
            polyline_ops=assigns.polyline_ops,
            ops_version=assigns.ops_version,
            component_id="dmap",
        )

        # Server events — conditionally rendered
        marker_ev = t'<div class="text-blue-600 truncate" title="{last_me}">● {last_me}</div>' if last_me else t''
        map_ev = t'<div class="text-purple-600 truncate" title="{last_mae}">◆ {last_mae}</div>' if last_mae else t''
        polyline_ev = t'<div class="text-green-600 truncate" title="{last_pe}">▬ {last_pe}</div>' if last_pe else t''
        no_events = t'<div class="text-gray-400">No events yet</div>' if not (last_me or last_mae or last_pe) else t''

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">\U0001f4e1 Dynamic Marker Map</h1>
        <p class="text-sm text-gray-500 mb-6">
            Markers are streamed in real-time — they appear, disappear, and move across the map.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div class="lg:col-span-1 flex flex-col gap-4">
                <div>
                    <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                        Activity Log
                    </h2>
                    <div id="dmap-log"
                         class="space-y-0.5 max-h-96 overflow-y-auto text-xs font-mono">
                    </div>
                </div>
                <div class="pt-3 border-t border-gray-200">
                    <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                        Server Events
                    </h2>
                    <div class="text-xs font-mono space-y-1">
                        {marker_ev}
                        {map_ev}
                        {polyline_ev}
                        {no_events}
                    </div>
                </div>
            </div>
            <div class="lg:col-span-3">
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-4">
                    {comp}
                </div>
            </div>
        </div>
    </div>
</div>"""
