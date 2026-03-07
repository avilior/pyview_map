"""map_list_demo.py — external coordinator for the /map_list_demo page.

Wires map ↔ list interaction to prove the components are independent:

1. Subscribe to map.events.subscribe (SSE stream)
2. On moveend/zoomend events with bounds:
   - Get all markers via markers.list
   - Filter markers within bounds
   - Clear the list and re-populate with visible markers
3. On ListItemClickEvent from SSE:
   - Highlight the corresponding marker on the map

Run this while the server is up and /map_list_demo is open:

    uv run python examples/map_list_demo.py

Optionally add some airports first:

    uv run python examples/planes/mock_planes.py --component-id map_list_demo-map
"""

import asyncio

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import (
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
)

from pyview_map.views.components.dynamic_map.models.map_events import (
    MapEvent,
    MarkerOpEvent,
    parse_event,
)
from pyview_map.views.components.dynamic_list.models.list_events import ListItemClickEvent

BASE_URL = "http://localhost:8123/api"
AUTH_TOKEN = "tok-acme-001"


async def _send(rpc: ClientRPC, method: str, params: dict | None = None) -> dict | None:
    """Fire a JSON-RPC request and return the result."""
    req = JSONRPCRequest(method=method, params=params or {})
    result = None
    async for msg in rpc.send_request(req):
        if isinstance(msg, JSONRPCResponse):
            result = msg.result
    return result


def _in_bounds(lat: float, lng: float, sw: list[float], ne: list[float]) -> bool:
    """Check if a point is within a bounding box."""
    return sw[0] <= lat <= ne[0] and sw[1] <= lng <= ne[1]


async def sync_list_to_viewport(rpc: ClientRPC, bounds: list[list[float]]) -> None:
    """Clear the list and re-populate with markers visible in the given bounds."""
    sw, ne = bounds[0], bounds[1]

    # Get all markers
    result = await _send(rpc, "markers.list")
    if not result or "markers" not in result:
        return

    # Filter to visible markers
    visible = [
        m for m in result["markers"]
        if _in_bounds(m["latLng"][0], m["latLng"][1], sw, ne)
    ]

    # Clear and re-populate list
    await _send(rpc, "list.clear", {"component_id": "map_list_demo-list"})
    for m in visible:
        await _send(rpc, "list.add", {
            "id": m["id"],
            "label": m["name"],
            "subtitle": f"({m['latLng'][0]:.2f}, {m['latLng'][1]:.2f})",
            "component_id": "map_list_demo-list",
        })

    print(f"  Synced list: {len(visible)} markers in viewport")


async def listen_and_coordinate(rpc: ClientRPC) -> None:
    """Subscribe to events and coordinate map ↔ list."""
    req = JSONRPCRequest(method="map.events.subscribe")
    async for msg in rpc.send_request(req):
        match msg:
            case JSONRPCNotification() if isinstance(msg.params, dict):
                evt = parse_event(msg.params)
                match evt:
                    case MapEvent() if evt.event in ("moveend", "zoomend") and evt.bounds:
                        bounds = [evt.bounds[0].to_list(), evt.bounds[1].to_list()]
                        await sync_list_to_viewport(rpc, bounds)

                    case MarkerOpEvent() if evt.op in ("add", "delete"):
                        # Re-sync on marker add/delete too
                        print(f"  [marker-op] {evt.op} {evt.id}")

                    case ListItemClickEvent():
                        print(f"  [list-click] {evt.id} → highlighting on map")
                        await _send(rpc, "map.highlightMarker", {
                            "id": evt.id,
                            "component_id": "map_list_demo-map",
                        })

                    case _:
                        print(f"  [unhandled] {evt}")

            case JSONRPCResponse():
                print("Event stream ended")
                break
            case JSONRPCErrorResponse():
                print(f"Error: {msg}")
                break


async def main() -> None:
    async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:

        print("Connected. Listening for events...")
        print("Open http://localhost:8123/demo and add markers to see coordination.")
        print("Tip: run 'uv run python examples/planes/mock_planes.py --component-id map_list_demo-map' in another terminal")
        try:
            await listen_and_coordinate(rpc)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nStopped.")


if __name__ == "__main__":
    asyncio.run(main())
