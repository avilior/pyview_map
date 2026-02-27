import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.vendor.ibis import filters

from .mock_generator import MockGenerator


@filters.register
def json_encode(val: Any) -> str:
    return json.dumps(val)


@dataclass
class DynamicMapContext:
    markers: list[dict]  # initial DMarker dicts rendered into the template


class DynamicMapLiveView(LiveView[DynamicMapContext]):
    """
    Dynamic Map

    Markers (dmarks) are streamed in real-time from the server.
    The backend can add, delete, or move markers without a full page reload.
    A mock generator drives motion to simulate live tracking.
    """

    async def mount(self, socket: LiveViewSocket[DynamicMapContext], session):
        self._generator = MockGenerator(initial_count=5)
        socket.context = DynamicMapContext(
            markers=[m.to_dict() for m in self._generator.markers]
        )
        asyncio.create_task(self._stream_updates(socket))

    async def _stream_updates(self, socket) -> None:
        # Small delay so the WebSocket connection can fully establish
        await asyncio.sleep(0.3)
        while True:
            await asyncio.sleep(1.2)
            try:
                update = self._generator.next_update()
                op = update["op"]

                if op == "add":
                    await socket.push_event(
                        "dmarker-add",
                        {"id": update["id"], "name": update["name"], "latLng": update["latLng"]},
                    )
                elif op == "delete":
                    await socket.push_event("dmarker-delete", {"id": update["id"]})
                elif op == "update":
                    await socket.push_event(
                        "dmarker-update",
                        {"id": update["id"], "latLng": update["latLng"]},
                    )
            except Exception as exc:
                print(f"[DynamicMap] stream ended: {exc}")
                break

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[DynamicMapContext]
    ):
        pass  # no client-initiated events required
