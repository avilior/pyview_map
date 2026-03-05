import asyncio
from dataclasses import dataclass, field

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import TemplateView
from pyview.template.live_view_template import live_component

from pyview_map.views.dynamic_map.api_marker_source import APIMarkerSource
from pyview_map.views.dynamic_map.api_polyline_source import APIPolylineSource
from pyview_map.views.dynamic_map.command_queue import CommandQueue
from pyview_map.views.dynamic_map.dmarker import DMarker
from pyview_map.views.dynamic_map.dpolyline import DPolyline
from pyview_map.views.dynamic_map.dynamic_map import DynamicMapComponent
from pyview_map.views.dynamic_map.event_broadcaster import EventBroadcaster
from pyview_map.views.dynamic_map.icon_registry import icon_registry
from pyview_map.views.dynamic_map.latlng import LatLng
from pyview_map.views.dynamic_map.map_events import MapEvent, MarkerEvent, PolylineEvent
from pyview_map.views.dynamic_list.api_list_source import APIListSource
from pyview_map.views.dynamic_list.dlist_item import DListItem
from pyview_map.views.dynamic_list.dynamic_list import DynamicListComponent
from pyview_map.views.dynamic_list.list_command_queue import ListCommandQueue
from pyview_map.views.dynamic_list.list_events import ListItemClickEvent


@dataclass
class DemoPageContext:
    # Map component data
    initial_markers: list[DMarker] = field(default_factory=list)
    initial_polylines: list[DPolyline] = field(default_factory=list)
    icon_registry_json: str = ""
    marker_ops: list[dict] = field(default_factory=list)
    polyline_ops: list[dict] = field(default_factory=list)
    map_ops_version: int = 0
    # List component data
    initial_items: list[DListItem] = field(default_factory=list)
    list_ops: list[dict] = field(default_factory=list)
    list_ops_version: int = 0
    # Event display
    last_event: str = ""


class DemoLiveView(TemplateView, LiveView[DemoPageContext]):
    """Demo page hosting a DynamicMapComponent and DynamicListComponent side by side.

    Usage:
        app.add_live_view("/demo", DemoLiveView)
    """

    tick_interval: float = 1.2

    async def mount(self, socket: LiveViewSocket[DemoPageContext], session):
        self._marker_source = APIMarkerSource(component_id="demo-map")
        self._polyline_source = APIPolylineSource(component_id="demo-map")
        self._list_source = APIListSource(component_id="demo-list")

        socket.context = DemoPageContext(
            initial_markers=self._marker_source.markers,
            initial_polylines=self._polyline_source.polylines,
            icon_registry_json=icon_registry.to_json(),
            initial_items=self._list_source.items,
        )

        if socket.connected:
            self._map_cmd_queue = CommandQueue.subscribe(component_id="demo-map")
            self._list_cmd_queue = ListCommandQueue.subscribe(component_id="demo-list")
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DemoPageContext]):
        if event.name != "tick":
            return

        # Drain marker updates
        marker_ops: list[dict] = []
        while True:
            update = self._marker_source.next_update()
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

        # Drain map commands
        while True:
            try:
                cmd = self._map_cmd_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            event_name, payload = cmd.to_push_event(target="demo-map")
            await socket.push_event(event_name, payload)

        # Drain list updates
        list_ops: list[dict] = []
        while True:
            update = self._list_source.next_update()
            if update["op"] == "noop":
                break
            list_ops.append(update)

        # Drain list commands
        while True:
            try:
                cmd = self._list_cmd_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            event_name, payload = cmd.to_push_event(target="demo-list")
            await socket.push_event(event_name, payload)

        # Update map context
        socket.context.marker_ops = marker_ops
        socket.context.polyline_ops = polyline_ops
        if marker_ops or polyline_ops:
            socket.context.map_ops_version += 1

        # Update list context
        socket.context.list_ops = list_ops
        if list_ops:
            socket.context.list_ops_version += 1

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DemoPageContext]):
        # Clear stale ops
        socket.context.marker_ops = []
        socket.context.polyline_ops = []
        socket.context.list_ops = []

        if event == "marker-event":
            raw_ll = payload.get("latLng", [])
            ll = LatLng.from_list(raw_ll) if raw_ll else LatLng(0, 0)
            me = MarkerEvent(
                event=payload.get("event", "?"),
                id=payload.get("id", ""),
                name=payload.get("name", payload.get("id", "?")),
                latLng=ll,
            )
            socket.context.last_event = f"marker: {me.event} → {me.name}"
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
            socket.context.last_event = f"polyline: {pe.event} → {pe.name}"
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
            socket.context.last_event = f"map: {me.event} zoom={me.zoom}"
            EventBroadcaster.broadcast(me)

        elif event == "item-click":
            item_id = payload.get("id", "")
            label = payload.get("label", "")
            evt = ListItemClickEvent(event="click", id=item_id, label=label)
            socket.context.last_event = f"list: click → {label}"
            EventBroadcaster.broadcast(evt)

    def template(self, assigns: DemoPageContext, meta: PyViewMeta):
        last_event = assigns.last_event

        map_comp = live_component(DynamicMapComponent, id="demo-map",
            initial_markers=assigns.initial_markers,
            initial_polylines=assigns.initial_polylines,
            icon_registry_json=assigns.icon_registry_json,
            marker_ops=assigns.marker_ops,
            polyline_ops=assigns.polyline_ops,
            ops_version=assigns.map_ops_version,
            component_id="demo-map",
        )

        list_comp = live_component(DynamicListComponent, id="demo-list",
            initial_items=assigns.initial_items,
            list_ops=assigns.list_ops,
            ops_version=assigns.list_ops_version,
            component_id="demo-list",
        )

        event_line = t'<div class="text-xs font-mono text-gray-600 truncate">{last_event}</div>' if last_event else t'<div class="text-xs text-gray-400">No events yet</div>'

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Map + List Demo</h1>
        <p class="text-sm text-gray-500 mb-6">
            Two independent components — map (<code>demo-map</code>) and list (<code>demo-list</code>) — driven by the JSON-RPC API.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2">
                <h2 class="text-sm font-semibold text-gray-700 mb-2">Map</h2>
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    {map_comp}
                </div>
            </div>
            <div class="lg:col-span-1">
                <h2 class="text-sm font-semibold text-gray-700 mb-2">List</h2>
                {list_comp}
            </div>
        </div>
        <div class="border-t border-gray-200 pt-3 mt-4">
            {event_line}
        </div>
    </div>
</div>"""
