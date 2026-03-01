"""mock_client.py — external MCP client that mirrors MockGenerator behaviour.

Run this while the server is up to see markers appear and move on the /dmap page:

    uv run python examples/mock_client.py
"""

import asyncio
import math
import random
import uuid

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import JSONRPCRequest, JSONRPCError, JSONRPCResponse, JSONRPCNotification, JSONRPCErrorResponse

from pyview_map.views.dynamic_map.map_events import (
    MarkerOpEvent, MarkerEvent, MapEvent, parse_event,
)

BASE_URL = "http://localhost:8123/api"
AUTH_TOKEN = "tok-acme-001"

# Continental US bounding box (same as MockGenerator)
_LAT = (25.0, 49.0)
_LNG = (-125.0, -66.0)

_CALLSIGNS = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo",
    "Foxtrot", "Golf", "Hotel", "India", "Juliet",
]


def _random_latlng() -> list[float]:
    return [round(random.uniform(*_LAT), 4), round(random.uniform(*_LNG), 4)]


def _advance(marker: dict) -> list[float]:
    """Move marker along its heading with slight drift; bounce off US bounds."""
    angle = math.radians(marker["heading"])
    speed = marker["speed"]
    dlat = speed * math.cos(angle) * random.uniform(0.6, 1.4)
    dlng = speed * math.sin(angle) * random.uniform(0.6, 1.4)

    marker["heading"] = (marker["heading"] + random.uniform(-20, 20)) % 360

    lat = marker["lat"] + dlat
    lng = marker["lng"] + dlng

    if not _LAT[0] <= lat <= _LAT[1]:
        marker["heading"] = (180 - marker["heading"]) % 360
        lat = max(_LAT[0], min(_LAT[1], lat))
    if not _LNG[0] <= lng <= _LNG[1]:
        marker["heading"] = (360 - marker["heading"]) % 360
        lng = max(_LNG[0], min(_LNG[1], lng))

    marker["lat"] = round(lat, 4)
    marker["lng"] = round(lng, 4)
    return [marker["lat"], marker["lng"]]


async def _send(rpc: ClientRPC, method: str, params: dict | None = None) -> None:
    """Fire a JSON-RPC request and consume the response."""
    req = JSONRPCRequest(method=method, params=params or {})
    async for resp in rpc.send_request(req):
        pass


async def listen_events(rpc: ClientRPC) -> None:
    """Subscribe to map/marker events and print them as they arrive."""
    # This will trigger the service to open a channel which will be used to receive Notification events
    # Upon receiving the Response to the request the channel will be closed.
    req = JSONRPCRequest(method="map.events.subscribe")
    async for msg in rpc.send_request(req):

        match msg:
            case JSONRPCNotification():
                print(f"[RX {msg.method}]:")
                evt = parse_event(msg.params)
                match evt:
                    case MarkerOpEvent():
                        ll = f"({evt.latLng.lat}, {evt.latLng.lng})" if evt.latLng else "-"
                        print(f"  [marker-op] {evt.op} id={evt.id} "
                              f"name={evt.name or '-'} latLng={ll}")
                    case MarkerEvent():
                        print(f"  [marker-event] {evt.event} id={evt.id} "
                              f"name={evt.name} latLng=({evt.latLng.lat}, {evt.latLng.lng})")
                    case MapEvent():
                        ll = f"({evt.latLng.lat}, {evt.latLng.lng})" if evt.latLng else "-"
                        print(f"  [map-event] {evt.event} "
                              f"center=({evt.center.lat}, {evt.center.lng}) "
                              f"zoom={evt.zoom} latLng={ll}")

            case JSONRPCResponse():
                # this would indicate the end of the channel.
                print(f"Response received: {msg} END OF CHANNEL")
            case JSONRPCErrorResponse():
                print(f"Error response received: {msg}")
                assert False, f"Error response received: {msg}"
            case _:
                print(f"Unknown message type: {type(msg)}")
                assert False, f"Unexpected message type: {type(msg)}"


async def run_command_demo(rpc: ClientRPC, markers: dict[str, dict]) -> None:
    """Demonstrate remote map control commands."""
    print("\n--- Command demo ---")

    # Pick first marker
    first_id, first_m = next(iter(markers.items()))
    lat, lng = first_m["lat"], first_m["lng"]

    # Fly to the first marker
    print(f"  flyTo {first_m['name']} at ({lat}, {lng}) zoom=8")
    await _send(rpc, "map.flyTo", {"latLng": [lat, lng], "zoom": 8})
    await asyncio.sleep(3)

    # Highlight it
    print(f"  highlightMarker {first_id}")
    await _send(rpc, "map.highlightMarker", {"id": first_id})
    await asyncio.sleep(2)

    # Zoom to level 6
    print("  setZoom 6")
    await _send(rpc, "map.setZoom", {"zoom": 6})
    await asyncio.sleep(2)

    # Reset to US overview
    print("  resetView")
    await _send(rpc, "map.resetView")
    await asyncio.sleep(2)

    print("--- Command demo complete ---\n")


async def main() -> None:

    initial_count = 1000

    async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:

        # Start listening for map events in the background
        event_task = asyncio.create_task(listen_events(rpc))

        # Seed initial markers
        markers: dict[str, dict] = {}
        for i in range(initial_count):
            mid = str(uuid.uuid4())[:8]
            name = f"{_CALLSIGNS[i % len(_CALLSIGNS)]}-{i + 1:02d}"
            lat, lng = _random_latlng()
            markers[mid] = {
                "name": name,
                "lat": lat,
                "lng": lng,
                "heading": random.uniform(0, 360),
                "speed": random.uniform(0.4, 1.2),
            }
            req = JSONRPCRequest(method="markers.add", params={"id": mid, "name": name, "latLng": [lat, lng]})
            async for resp in rpc.send_request(req):
                pass  # consume response
            print(f"  added {name} at ({lat}, {lng})")

        print(f"\nSeeded {initial_count} markers.")

        # Run the command demo
        await run_command_demo(rpc, markers)

        print("Starting update loop (Ctrl-C to stop)...\n")

        try:
            while True:
                await asyncio.sleep(1.2)
                mid, m = random.choice(list(markers.items()))
                new_latlng = _advance(m)
                req = JSONRPCRequest(method="markers.update", params={"id": mid, "name": m["name"], "latLng": new_latlng})
                async for resp in rpc.send_request(req):
                    if resp.id != req.id:
                        print(f"  ERROR: unexpected response id {resp.id} != {req.id}")
                        break
                    if isinstance(resp, JSONRPCError):
                        print(f"  ERROR: {resp.error}")
                        break

                    # Cast to JSONRPCResponse to access result attribute
                    if isinstance(resp, JSONRPCResponse):
                        result = resp.result
                        if result and not result.get('ok', True):
                            print(f"  ERROR: unexpected result {result}")

                    print(f"  moved {m['name']} → ({new_latlng[0]}, {new_latlng[1]})")

        finally:
            event_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
