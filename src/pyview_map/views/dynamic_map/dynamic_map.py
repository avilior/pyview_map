import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.components import LiveComponent
from pyview.components.base import ComponentMeta, ComponentSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.stream import Stream
from pyview.template import TemplateView
from pyview.template.live_view_template import live_component, stream_for

from .api_polyline_source import APIPolylineSource
from .command_queue import CommandQueue
from .dmarker import DMarker
from .dpolyline import DPolyline
from .event_broadcaster import EventBroadcaster
from .icon_registry import icon_registry
from .latlng import LatLng
from .map_events import MapEvent, MarkerEvent, PolylineEvent


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
# DynamicMapComponent — renders a single Leaflet map with marker/polyline streams
# ---------------------------------------------------------------------------

@dataclass
class DynamicMapComponentContext:
    markers: Stream[DMarker]
    polylines: Stream[DPolyline]
    icon_registry_json: str
    map_id: str
    _last_version: int = 0


def _apply_marker_ops(markers: Stream[DMarker], ops: list[dict], *, stream_name: str = "markers") -> None:
    """Apply a list of marker operation dicts to a Stream."""
    for op_dict in ops:
        op = op_dict["op"]
        if op == "add":
            markers.insert(DMarker(
                id=op_dict["id"], name=op_dict["name"],
                lat_lng=LatLng.from_list(op_dict["latLng"]),
                icon=op_dict.get("icon", "default"),
                heading=op_dict.get("heading"),
                speed=op_dict.get("speed"),
            ))
        elif op == "delete":
            markers.delete_by_id(f"{stream_name}-{op_dict['id']}")
        elif op == "update":
            markers.insert(DMarker(
                id=op_dict["id"], name=op_dict["name"],
                lat_lng=LatLng.from_list(op_dict["latLng"]),
                icon=op_dict.get("icon", "default"),
                heading=op_dict.get("heading"),
                speed=op_dict.get("speed"),
            ), update_only=True)


def _apply_polyline_ops(polylines: Stream[DPolyline], ops: list[dict], *, stream_name: str = "polylines") -> None:
    """Apply a list of polyline operation dicts to a Stream."""
    for op_dict in ops:
        op = op_dict["op"]
        if op == "add":
            polylines.insert(DPolyline(
                id=op_dict["id"], name=op_dict["name"],
                path=[LatLng.from_list(p) for p in op_dict["path"]],
                color=op_dict.get("color", "#3388ff"),
                weight=op_dict.get("weight", 3),
                opacity=op_dict.get("opacity", 1.0),
                dash_array=op_dict.get("dashArray"),
            ))
        elif op == "delete":
            polylines.delete_by_id(f"{stream_name}-{op_dict['id']}")
        elif op == "update":
            polylines.insert(DPolyline(
                id=op_dict["id"], name=op_dict["name"],
                path=[LatLng.from_list(p) for p in op_dict["path"]],
                color=op_dict.get("color", "#3388ff"),
                weight=op_dict.get("weight", 3),
                opacity=op_dict.get("opacity", 1.0),
                dash_array=op_dict.get("dashArray"),
            ), update_only=True)


class DynamicMapComponent(LiveComponent[DynamicMapComponentContext]):
    """Renders a single Leaflet map with marker and polyline streams.

    Lifecycle:
      - mount(): create empty Streams from initial markers/polylines
      - update(): receive pending ops from parent, apply to Streams
      - template(): t-string with map div + stream_for() containers
    """

    async def mount(self, socket: ComponentSocket[DynamicMapComponentContext], assigns: dict[str, Any]) -> None:
        map_id = assigns.get("map_id", "dmap")
        initial_markers = assigns.get("initial_markers", [])
        initial_polylines = assigns.get("initial_polylines", [])
        socket.context = DynamicMapComponentContext(
            markers=Stream(initial_markers, name=f"{map_id}-markers"),
            polylines=Stream(initial_polylines, name=f"{map_id}-polylines"),
            icon_registry_json=assigns.get("icon_registry_json", "{}"),
            map_id=map_id,
        )

    async def update(self, socket: ComponentSocket[DynamicMapComponentContext], assigns: dict[str, Any]) -> None:
        version = assigns.get("ops_version", 0)
        ctx = socket.context
        if version <= ctx._last_version:
            return
        ctx._last_version = version

        marker_stream_name = f"{ctx.map_id}-markers"
        polyline_stream_name = f"{ctx.map_id}-polylines"
        _apply_marker_ops(ctx.markers, assigns.get("marker_ops", []), stream_name=marker_stream_name)
        _apply_polyline_ops(ctx.polylines, assigns.get("polyline_ops", []), stream_name=polyline_stream_name)

    def template(self, assigns: DynamicMapComponentContext, meta: ComponentMeta):
        map_id = assigns.map_id
        icon_json = assigns.icon_registry_json
        markers_id = f"{map_id}-markers"
        polylines_id = f"{map_id}-polylines"

        markers_html = stream_for(assigns.markers, lambda dom_id, marker:
            t'<div id="{dom_id}" phx-hook="DMarkItem" data-name="{marker.name}" data-lat="{marker.lat}" data-lng="{marker.lng}" data-icon="{marker.icon}" data-heading="{marker.heading}" data-speed="{marker.speed}"></div>'
        )

        polylines_html = stream_for(assigns.polylines, lambda dom_id, polyline:
            t'<div id="{dom_id}" phx-hook="DPolylineItem" data-name="{polyline.name}" data-path="{json.dumps(polyline.path_as_lists)}" data-color="{polyline.color}" data-weight="{polyline.weight}" data-opacity="{polyline.opacity}" data-dash-array="{polyline.dash_array}"></div>'
        )

        return t"""<div data-map-instance="{map_id}">
    <div phx-update="ignore" id="{map_id}_wrapper">
        <div id="{map_id}"
             phx-hook="DynamicMap"
             data-icon-registry="{icon_json}"
             class="w-full h-96 lg:h-[580px] rounded-md overflow-hidden border border-gray-300">
        </div>
    </div>
    <div id="{markers_id}" phx-update="stream" style="display:none" aria-hidden="true">
        {markers_html}
    </div>
    <div id="{polylines_id}" phx-update="stream" style="display:none" aria-hidden="true">
        {polylines_html}
    </div>
</div>"""


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
            event_name, payload = cmd.to_push_event()
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
            me = MapEvent(
                event=payload.get("event", "?"),
                center=LatLng.from_list(raw_center) if raw_center else LatLng(0, 0),
                zoom=payload.get("zoom", 0),
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
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
            map_id="dmap",
        )

        # Server events — conditionally rendered
        marker_ev = t'<div class="text-blue-600 truncate" title="{last_me}">\u25cf {last_me}</div>' if last_me else t''
        map_ev = t'<div class="text-purple-600 truncate" title="{last_mae}">\u25c6 {last_mae}</div>' if last_mae else t''
        polyline_ev = t'<div class="text-green-600 truncate" title="{last_pe}">\u25ac {last_pe}</div>' if last_pe else t''
        no_events = t'<div class="text-gray-400">No events yet</div>' if not (last_me or last_mae or last_pe) else t''

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">\U0001f4e1 Dynamic Marker Map</h1>
        <p class="text-sm text-gray-500 mb-6">
            Markers are streamed in real-time \u2014 they appear, disappear, and move across the map.
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


# ---------------------------------------------------------------------------
# MultiMapLiveView — multiple DynamicMapComponent instances on one page
# ---------------------------------------------------------------------------

@dataclass
class _MapSlot:
    """Per-map internal state (not part of the context — stored on the instance)."""
    map_id: str
    source: MarkerSource
    polyline_source: APIPolylineSource
    cmd_queue: asyncio.Queue


@dataclass
class MultiMapPageContext:
    icon_registry_json: str = ""
    last_marker_event: str = ""
    last_map_event: str = ""
    last_polyline_event: str = ""
    # Per-map initial data — keyed by map_id
    initial_data: dict = field(default_factory=dict)   # map_id → {markers, polylines}
    # Per-map ops — keyed by map_id
    map_ops: dict = field(default_factory=dict)         # map_id → {marker_ops, polyline_ops, ops_version}


class MultiMapLiveView(TemplateView, LiveView[MultiMapPageContext]):
    """
    Multi-map page with two side-by-side DynamicMapComponent instances.

    Each map has its own map_id. External clients use the map_id parameter
    to route markers/polylines/commands to a specific map.

    Usage:
        app.add_live_view("/mmap", MultiMapLiveView.with_maps(["left", "right"]))
    """

    map_ids: list[str] = []
    source_class: type = None  # type: ignore[assignment]
    tick_interval: float = 1.2

    @classmethod
    def with_maps(cls, map_ids: list[str], *, source_class: type | None = None, tick_interval: float = 1.2):
        """Return a configured MultiMapLiveView class."""
        from .api_marker_source import APIMarkerSource as _DefaultSource
        return type(
            "MultiMapLiveView",
            (cls,),
            {
                "map_ids": map_ids,
                "source_class": source_class or _DefaultSource,
                "tick_interval": tick_interval,
            },
        )

    async def mount(self, socket: LiveViewSocket[MultiMapPageContext], session):
        self._slots: dict[str, _MapSlot] = {}
        initial_data: dict = {}
        map_ops: dict = {}

        for map_id in self.map_ids:
            source = self.source_class(map_id=map_id)
            polyline_source = APIPolylineSource(map_id=map_id)
            self._slots[map_id] = _MapSlot(
                map_id=map_id,
                source=source,
                polyline_source=polyline_source,
                cmd_queue=asyncio.Queue(maxsize=1),  # placeholder
            )
            initial_data[map_id] = {
                "markers": source.markers,
                "polylines": polyline_source.polylines,
            }
            map_ops[map_id] = {"marker_ops": [], "polyline_ops": [], "ops_version": 0}

        socket.context = MultiMapPageContext(
            icon_registry_json=icon_registry.to_json(),
            initial_data=initial_data,
            map_ops=map_ops,
        )

        if socket.connected:
            for map_id, slot in self._slots.items():
                slot.cmd_queue = CommandQueue.subscribe(map_id=map_id)
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[MultiMapPageContext]):
        if event.name != "tick":
            return

        for map_id, slot in self._slots.items():
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
                event_name, payload = cmd.to_push_event()
                await socket.push_event(event_name, payload)

            # Update context
            ops = socket.context.map_ops[map_id]
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
            detail = f"{me.event} \u2192 {me.name}"
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
            detail = f"{pe.event} \u2192 {pe.name}"
            if pe.latLng:
                detail += f" @ ({pe.latLng.lat:.2f}, {pe.latLng.lng:.2f})"
            socket.context.last_polyline_event = detail
            EventBroadcaster.broadcast(pe)

        elif event == "map-event":
            raw_center = payload.get("center", [])
            raw_ll = payload.get("latLng")
            me = MapEvent(
                event=payload.get("event", "?"),
                center=LatLng.from_list(raw_center) if raw_center else LatLng(0, 0),
                zoom=payload.get("zoom", 0),
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
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
        for map_id in self.map_ids:
            init = assigns.initial_data.get(map_id, {})
            ops = assigns.map_ops.get(map_id, {})
            comp = live_component(DynamicMapComponent, id=map_id,
                initial_markers=init.get("markers", []),
                initial_polylines=init.get("polylines", []),
                icon_registry_json=assigns.icon_registry_json,
                marker_ops=ops.get("marker_ops", []),
                polyline_ops=ops.get("polyline_ops", []),
                ops_version=ops.get("ops_version", 0),
                map_id=map_id,
            )
            map_components.append((map_id, comp))

        # For 2 maps: side-by-side layout
        left_id, left_comp = map_components[0] if len(map_components) > 0 else ("", t"")
        right_id, right_comp = map_components[1] if len(map_components) > 1 else ("", t"")

        # Server events
        marker_ev = t'<div class="text-blue-600 truncate" title="{last_me}">\u25cf {last_me}</div>' if last_me else t''
        map_ev = t'<div class="text-purple-600 truncate" title="{last_mae}">\u25c6 {last_mae}</div>' if last_mae else t''
        polyline_ev = t'<div class="text-green-600 truncate" title="{last_pe}">\u25ac {last_pe}</div>' if last_pe else t''
        no_events = t'<div class="text-gray-400">No events yet</div>' if not (last_me or last_mae or last_pe) else t''

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">\U0001f4e1 Multi-Map Dashboard</h1>
        <p class="text-sm text-gray-500 mb-6">
            Two independent maps \u2014 use <code>map_id</code> to route markers to a specific map.
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
