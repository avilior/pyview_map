
import json
from dataclasses import dataclass
from typing import Any

from pyview.components import LiveComponent
from pyview.components.base import ComponentMeta, ComponentSocket
from pyview.stream import Stream
from pyview.template.live_view_template import stream_for

from .models.dmarker import DMarker
from .models.dpolyline import DPolyline
from pyview_map.views.components.shared.latlng import LatLng


# ---------------------------------------------------------------------------
# DynamicMapComponent — renders a single Leaflet map with marker/polyline streams
# ---------------------------------------------------------------------------

@dataclass
class DynamicMapComponentContext:
    markers: Stream[DMarker]
    polylines: Stream[DPolyline]
    icon_registry_json: str
    channel: str
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
        channel = assigns.get("channel", "dmap")
        initial_markers = assigns.get("initial_markers", [])
        initial_polylines = assigns.get("initial_polylines", [])
        socket.context = DynamicMapComponentContext(
            markers=Stream(initial_markers, name=f"{channel}-markers"),
            polylines=Stream(initial_polylines, name=f"{channel}-polylines"),
            icon_registry_json=assigns.get("icon_registry_json", "{}"),
            channel=channel,
        )

    async def update(self, socket: ComponentSocket[DynamicMapComponentContext], assigns: dict[str, Any]) -> None:
        version = assigns.get("ops_version", 0)
        ctx = socket.context
        if version <= ctx._last_version:
            return
        ctx._last_version = version

        marker_stream_name = f"{ctx.channel}-markers"
        polyline_stream_name = f"{ctx.channel}-polylines"
        _apply_marker_ops(ctx.markers, assigns.get("marker_ops", []), stream_name=marker_stream_name)
        _apply_polyline_ops(ctx.polylines, assigns.get("polyline_ops", []), stream_name=polyline_stream_name)

    def template(self, assigns: DynamicMapComponentContext, meta: ComponentMeta):
        channel = assigns.channel
        icon_json = assigns.icon_registry_json
        markers_id = f"{channel}-markers"
        polylines_id = f"{channel}-polylines"

        markers_html = stream_for(assigns.markers, lambda dom_id, marker:
            t'<div id="{dom_id}" phx-hook="DMarkItem" data-name="{marker.name}" data-lat="{marker.lat}" data-lng="{marker.lng}" data-icon="{marker.icon}" data-heading="{marker.heading}" data-speed="{marker.speed}"></div>'
        )

        polylines_html = stream_for(assigns.polylines, lambda dom_id, polyline:
            t'<div id="{dom_id}" phx-hook="DPolylineItem" data-name="{polyline.name}" data-path="{json.dumps(polyline.path_as_lists)}" data-color="{polyline.color}" data-weight="{polyline.weight}" data-opacity="{polyline.opacity}" data-dash-array="{polyline.dash_array}"></div>'
        )

        return t"""<div data-channel="{channel}">
    <div phx-update="ignore" id="{channel}_wrapper">
        <div id="{channel}"
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


