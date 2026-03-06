import asyncio

from dataclasses import dataclass, field

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import TemplateView
from pyview.template.live_view_template import live_component

from pyview_map.views.components.dynamic_map.api_polyline_source import APIPolylineSource

from pyview_map.views.components.dynamic_map.command_queue import CommandQueue
from pyview_map.views.components.dynamic_map.event_broadcaster import EventBroadcaster
from pyview_map.views.components.dynamic_map.icon_registry import icon_registry
from pyview_map.views.components.dynamic_map.latlng import LatLng
from pyview_map.views.components.dynamic_map.map_events import MapEvent, MarkerEvent, PolylineEvent
from pyview_map.views.components.dynamic_map.dynamic_map_component import DynamicMapComponent
from pyview_map.views.components.dynamic_map.api_marker_source import MarkerSource

@dataclass
class _MapSlot:
    """Per-map internal state (not part of the context — stored on the instance)."""
    component_id: str
    source: MarkerSource
    polyline_source: APIPolylineSource
    cmd_queue: asyncio.Queue


@dataclass
class MultiMapPageContext:
    icon_registry_json: str = ""
    last_marker_event: str = ""
    last_map_event: str = ""
    last_polyline_event: str = ""
    # Per-map initial data — keyed by component_id
    initial_data: dict = field(default_factory=dict)   # component_id → {markers, polylines}
    # Per-map ops — keyed by component_id
    map_ops: dict = field(default_factory=dict)         # component_id → {marker_ops, polyline_ops, ops_version}


class MultiMapLiveView(TemplateView, LiveView[MultiMapPageContext]):
    """
    Multi-map page with two side-by-side DynamicMapComponent instances.

    Each map has its own component_id. External clients use the component_id parameter
    to route markers/polylines/commands to a specific map.

    Usage:
        app.add_live_view("/mmap", MultiMapLiveView.with_maps(["left", "right"]))
    """

    component_ids: list[str] = []
    source_class: type = None  # type: ignore[assignment]
    tick_interval: float = 1.2

    @classmethod
    def with_maps(cls, component_ids: list[str], *, source_class: type | None = None, tick_interval: float = 1.2):
        """Return a configured MultiMapLiveView class."""

        from pyview_map.views.components.dynamic_map.api_marker_source import APIMarkerSource as _DefaultSource

        return type(
            "MultiMapLiveView",
            (cls,),
            {
                "component_ids": component_ids,
                "source_class": source_class or _DefaultSource,
                "tick_interval": tick_interval,
            },
        )

    async def mount(self, socket: LiveViewSocket[MultiMapPageContext], session):
        self._slots: dict[str, _MapSlot] = {}
        initial_data: dict = {}
        map_ops: dict = {}

        for component_id in self.component_ids:
            source = self.source_class(component_id=component_id)
            polyline_source = APIPolylineSource(component_id=component_id)
            self._slots[component_id] = _MapSlot(
                component_id=component_id,
                source=source,
                polyline_source=polyline_source,
                cmd_queue=asyncio.Queue(maxsize=1),  # placeholder
            )
            initial_data[component_id] = {
                "markers": source.markers,
                "polylines": polyline_source.polylines,
            }
            map_ops[component_id] = {"marker_ops": [], "polyline_ops": [], "ops_version": 0}

        socket.context = MultiMapPageContext(
            icon_registry_json=icon_registry.to_json(),
            initial_data=initial_data,
            map_ops=map_ops,
        )

        if socket.connected:
            for component_id, slot in self._slots.items():
                slot.cmd_queue = CommandQueue.subscribe(component_id=component_id)
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[MultiMapPageContext]):
        if event.name != "tick":
            return

        for component_id, slot in self._slots.items():
            # Drain marker updates
            marker_ops: list[dict] = []
            while True:
                update = slot.source.next_update()
                if update["op"] == "noop":
                    break
                marker_ops.append(update)

            # Drain polyline updates
            polyline_ops: list[dict] = []
            while True:
                pl_update = slot.polyline_source.next_update()
                if pl_update["op"] == "noop":
                    break
                polyline_ops.append(pl_update)

            # Drain commands
            while True:
                try:
                    cmd = slot.cmd_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                event_name, payload = cmd.to_push_event(target=component_id)
                await socket.push_event(event_name, payload)

            # Update context
            ops = socket.context.map_ops[component_id]
            ops["marker_ops"] = marker_ops
            ops["polyline_ops"] = polyline_ops
            if marker_ops or polyline_ops:
                ops["ops_version"] = ops.get("ops_version", 0) + 1

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[MultiMapPageContext]):
        # Clear stale ops
        for ops in socket.context.map_ops.values():
            ops["marker_ops"] = []
            ops["polyline_ops"] = []

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

    def template(self, assigns: MultiMapPageContext, meta: PyViewMeta):
        last_me = assigns.last_marker_event
        last_mae = assigns.last_map_event
        last_pe = assigns.last_polyline_event

        # Build a component for each map
        map_components = []
        for component_id in self.component_ids:
            init = assigns.initial_data.get(component_id, {})
            ops = assigns.map_ops.get(component_id, {})
            comp = live_component(DynamicMapComponent, id=component_id,
                initial_markers=init.get("markers", []),
                initial_polylines=init.get("polylines", []),
                icon_registry_json=assigns.icon_registry_json,
                marker_ops=ops.get("marker_ops", []),
                polyline_ops=ops.get("polyline_ops", []),
                ops_version=ops.get("ops_version", 0),
                component_id=component_id,
            )
            map_components.append((component_id, comp))

        # For 2 park_map_demo: side-by-side layout
        left_id, left_comp = map_components[0] if len(map_components) > 0 else ("", t"")
        right_id, right_comp = map_components[1] if len(map_components) > 1 else ("", t"")

        # Server events
        marker_ev = t'<div class="text-blue-600 truncate" title="{last_me}">● {last_me}</div>' if last_me else t''
        map_ev = t'<div class="text-purple-600 truncate" title="{last_mae}">◆ {last_mae}</div>' if last_mae else t''
        polyline_ev = t'<div class="text-green-600 truncate" title="{last_pe}">▬ {last_pe}</div>' if last_pe else t''
        no_events = t'<div class="text-gray-400">No events yet</div>' if not (last_me or last_mae or last_pe) else t''

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">\U0001f4e1 Multi-Map Dashboard</h1>
        <p class="text-sm text-gray-500 mb-6">
            Two independent maps — use <code>component_id</code> to route markers to a specific map.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div>
                <h2 class="text-sm font-semibold text-gray-700 mb-2">{left_id}</h2>
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    {left_comp}
                </div>
            </div>
            <div>
                <h2 class="text-sm font-semibold text-gray-700 mb-2">{right_id}</h2>
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    {right_comp}
                </div>
            </div>
        </div>
        <div class="border-t border-gray-200 pt-4">
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
</div>"""
