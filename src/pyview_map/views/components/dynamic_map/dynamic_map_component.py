
import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pyview.components import LiveComponent
from pyview.components.base import ComponentMeta, ComponentSocket
from pyview.stream import Stream
from pyview.template.live_view_template import stream_for

from .dmarker import DMarker
from .dpolyline import DPolyline
from .latlng import LatLng


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
    component_id: str
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
        component_id = assigns.get("component_id", "dmap")
        initial_markers = assigns.get("initial_markers", [])
        initial_polylines = assigns.get("initial_polylines", [])
        socket.context = DynamicMapComponentContext(
            markers=Stream(initial_markers, name=f"{component_id}-markers"),
            polylines=Stream(initial_polylines, name=f"{component_id}-polylines"),
            icon_registry_json=assigns.get("icon_registry_json", "{}"),
            component_id=component_id,
        )

    async def update(self, socket: ComponentSocket[DynamicMapComponentContext], assigns: dict[str, Any]) -> None:
        version = assigns.get("ops_version", 0)
        ctx = socket.context
        if version <= ctx._last_version:
            return
        ctx._last_version = version

        marker_stream_name = f"{ctx.component_id}-markers"
        polyline_stream_name = f"{ctx.component_id}-polylines"
        _apply_marker_ops(ctx.markers, assigns.get("marker_ops", []), stream_name=marker_stream_name)
        _apply_polyline_ops(ctx.polylines, assigns.get("polyline_ops", []), stream_name=polyline_stream_name)

    def template(self, assigns: DynamicMapComponentContext, meta: ComponentMeta):
        component_id = assigns.component_id
        icon_json = assigns.icon_registry_json
        markers_id = f"{component_id}-markers"
        polylines_id = f"{component_id}-polylines"

        markers_html = stream_for(assigns.markers, lambda dom_id, marker:
            t'<div id="{dom_id}" phx-hook="DMarkItem" data-name="{marker.name}" data-lat="{marker.lat}" data-lng="{marker.lng}" data-icon="{marker.icon}" data-heading="{marker.heading}" data-speed="{marker.speed}"></div>'
        )

        polylines_html = stream_for(assigns.polylines, lambda dom_id, polyline:
            t'<div id="{dom_id}" phx-hook="DPolylineItem" data-name="{polyline.name}" data-path="{json.dumps(polyline.path_as_lists)}" data-color="{polyline.color}" data-weight="{polyline.weight}" data-opacity="{polyline.opacity}" data-dash-array="{polyline.dash_array}"></div>'
        )

        return t"""<div data-component-id="{component_id}">
    <div phx-update="ignore" id="{component_id}_wrapper">
        <div id="{component_id}"
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


