import json
from dataclasses import dataclass
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


class DynamicMapLiveView(LiveView[DynamicMapContext]):
    """
    Dynamic Map

    Uses pyview's Stream to push marker add, delete, and move operations
    directly to the DOM via the LiveView diff protocol.  A scheduled
    handle_info tick drives the mock movement simulation.
    """

    async def mount(self, socket: LiveViewSocket[DynamicMapContext], session):
        self._generator = MockGenerator(initial_count=5)
        socket.context = DynamicMapContext(
            markers=Stream(self._generator.markers, name="markers")
        )
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

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[DynamicMapContext]
    ):
        pass
