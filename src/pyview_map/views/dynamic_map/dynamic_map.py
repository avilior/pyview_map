import json
from dataclasses import dataclass, field
from typing import Any

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import InfoEvent
from pyview.stream import Stream
from pyview.vendor.ibis import filters

from .mock_generator import DMarker, MockGenerator


@filters.register
def json_encode(val: Any) -> str:
    return json.dumps(val)


@dataclass
class DynamicMapContext:
    markers: Stream[DMarker]
    last_marker_event: str = ""
    last_map_event: str = ""


class DynamicMapLiveView(LiveView[DynamicMapContext]):
    """
    Dynamic Map

    Uses pyview's Stream to push marker add, delete, and move operations
    directly to the DOM via the LiveView diff protocol.  A scheduled
    handle_info tick drives the mock movement simulation.
    """

    async def mount(self, socket: LiveViewSocket[DynamicMapContext], session):
        self._generator = MockGenerator(initial_count=120)

        socket.context = DynamicMapContext(markers=Stream(self._generator.markers, name="markers"))

        if socket.connected:
            socket.schedule_info(InfoEvent("tick"), seconds=1.2)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DynamicMapContext]):
        if event.name != "tick":
            return

        update = self._generator.next_update()
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
            evt  = payload.get("event", "?")
            name = payload.get("name", payload.get("id", "?"))
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
