"""mock_client.py — external MCP client that mirrors MockGenerator behaviour.

Run this while the server is up to see markers appear and move on the /dmap page:

    uv run python examples/mock_client.py
"""

import asyncio
import math
import random
import uuid
from ctypes.wintypes import tagPOINT
from datetime import datetime, timezone, timedelta

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import JSONRPCRequest, JSONRPCError, JSONRPCResponse, JSONRPCNotification, JSONRPCErrorResponse

from pyview_map.views.dynamic_map import DPolyline
from pyview_map.views.dynamic_map.dmarker import DMarker
from pyview_map.views.dynamic_map.latlng import LatLng

from pyview_map.views.dynamic_map.map_events import (
    MarkerOpEvent, MarkerEvent, MapEvent, parse_event,
)
from dataclasses import dataclass
from navigation_utils import great_circle_flight_generator, bearing_deg
from typing import Tuple

BASE_URL = "http://localhost:8123/api"
AUTH_TOKEN = "tok-acme-001"


# _ICONS = ["default", "red-dot", "green-dot", "warning", "vehicle", "airplane"]


# def _random_latlng() -> list[float]:
#     return [round(random.uniform(*_LAT), 4), round(random.uniform(*_LNG), 4)]


# def _advance(marker: dict) -> list[float]:
#     """Move marker along its heading with slight drift; bounce off US bounds."""
#     angle = math.radians(marker["heading"])
#     speed = marker["speed"]
#     dlat = speed * math.cos(angle) * random.uniform(0.6, 1.4)
#     dlng = speed * math.sin(angle) * random.uniform(0.6, 1.4)
#
#     marker["heading"] = (marker["heading"] + random.uniform(-20, 20)) % 360
#
#     lat = marker["lat"] + dlat
#     lng = marker["lng"] + dlng
#
#     if not _LAT[0] <= lat <= _LAT[1]:
#         marker["heading"] = (180 - marker["heading"]) % 360
#         lat = max(_LAT[0], min(_LAT[1], lat))
#     if not _LNG[0] <= lng <= _LNG[1]:
#         marker["heading"] = (360 - marker["heading"]) % 360
#         lng = max(_LNG[0], min(_LNG[1], lng))
#
#     marker["lat"] = round(lat, 4)
#     marker["lng"] = round(lng, 4)
#     return [marker["lat"], marker["lng"]]


# helper function
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


# async def run_command_demo(rpc: ClientRPC, markers: dict[str, dict]) -> None:
#     """Demonstrate remote map control commands."""
#     print("\n--- Command demo ---")
#
#     # Pick first marker
#     first_id, first_m = next(iter(markers.items()))
#     lat, lng = first_m["lat"], first_m["lng"]
#
#     # Fly to the first marker
#     print(f"  flyTo {first_m['name']} at ({lat}, {lng}) zoom=8")
#     await _send(rpc, "map.flyTo", {"latLng": [lat, lng], "zoom": 8})
#     await asyncio.sleep(3)
#
#     # Highlight it
#     print(f"  highlightMarker {first_id}")
#     await _send(rpc, "map.highlightMarker", {"id": first_id})
#     await asyncio.sleep(2)
#
#     # Zoom to level 6
#     print("  setZoom 6")
#     await _send(rpc, "map.setZoom", {"zoom": 6})
#     await asyncio.sleep(2)
#
#     # Reset to US overview
#     print("  resetView")
#     await _send(rpc, "map.resetView")
#     await asyncio.sleep(2)
#
#     print("--- Command demo complete ---\n")

# @dataclass(kw_only=True)
# class LatLng:
#     lat: float
#     lng: float

@dataclass
class Airport:
    name: str
    latlng: LatLng
    marker: DMarker = None

airports = [
    Airport(name="JFK", latlng=LatLng(lat=40.64, lng=-73.78)),
    Airport(name="LHR", latlng=LatLng(lat=51.47, lng=-0.46)),
    Airport(name="CDG", latlng=LatLng(lat=49.01, lng=2.51)),
    Airport(name="AMS", latlng=LatLng(lat=52.37, lng=4.90)),
    Airport(name="EWR", latlng=LatLng(lat=40.69, lng=-74.18)),
    Airport(name="IAD", latlng=LatLng(lat=40.63, lng=-73.75)),
    Airport(name="LAX", latlng=LatLng(lat=33.94, lng=-118.40)),
    Airport(name="DEN", latlng=LatLng(lat=48.13, lng=11.58)),
    Airport(name="SFO", latlng=LatLng(lat=37.62, lng=-122.38)),
    Airport(name="SEA", latlng=LatLng(lat=60.19, lng=24.94)),
    Airport(name="HKG", latlng=LatLng(lat=22.30, lng=114.17)),
    Airport(name="JNB", latlng=LatLng(lat=40.71, lng=-74.01)),
    Airport(name="LGW", latlng=LatLng(lat=17.38, lng=103.85)),
    Airport(name="SIN", latlng=LatLng(lat=1.35, lng=103.86)),
    Airport(name="SYD", latlng=LatLng(lat=-33.86, lng=151.20)),
    Airport(name="YUL", latlng=LatLng(lat=45.4577, lng=-73.7497)),
    Airport(name="YOW", latlng=LatLng(lat=45.3202, lng=-75.6656)),
    Airport(name="YYZ", latlng=LatLng(lat=43.6798, lng=-79.6284)),
    Airport(name="YYC", latlng=LatLng(lat=51.1219, lng=-114.0153)),
    Airport(name="YVR", latlng=LatLng(lat=49.1951, lng=-123.1840)),
    Airport(name="YEG", latlng=LatLng(lat=53.3181, lng=-113.7112)),
    Airport(name="YWG", latlng=LatLng(lat=49.9097, lng=-97.2272)),
    Airport(name="YHZ", latlng=LatLng(lat=44.8808, lng=-63.5086)),
]

AIRPORT_REGISTRY= {ap.name:ap for ap in airports}


def init_airport_markers():
    for id, ap in enumerate(airports):
        marker = DMarker(id=f"ap_{id+1}_{ap.name}", name=ap.name, lat_lng=ap.latlng, icon="black-square",)
        ap.marker = marker


@dataclass
class Plane:
    id: str
    marker: DMarker = None


@dataclass
class Flight:
    id: str
    plane: Plane
    origin: Airport
    destination: Airport
    departure_time: datetime | None = None
    arrival_time: datetime | None = None
    planned_route: list[Tuple[datetime, float, float]] = None

def build_flight(from_airport_name: str, to_airport_name: str, flight_id: str, plane_id: str) -> Flight:

    from_airport = AIRPORT_REGISTRY[from_airport_name]
    to_airport = AIRPORT_REGISTRY[to_airport_name]

    planned_route = [t for t in great_circle_flight_generator(
                            from_latlng= from_airport.latlng,
                            to_latlng= to_airport.latlng,
                            ground_speed_knots = 500,
                            start_time = datetime.now(timezone.utc),
                            step=timedelta(minutes=1))]

    flight_duration = planned_route[-1][0] - planned_route[0][0]

    heading = bearing_deg(from_latlng= from_airport.latlng, to_latlng=to_airport.latlng)

    flight = Flight(
            id=flight_id,
            plane=Plane(id=plane_id, marker=DMarker(id=plane_id, name=plane_id, lat_lng=from_airport.latlng, icon="airplane", speed=500, heading=heading)),
            origin=from_airport,
            destination=to_airport,
            departure_time=datetime.now(timezone.utc),
            arrival_time=planned_route[-1][0],
            planned_route=planned_route,
    )
    return flight



async def main() -> None:
    #
    init_airport_markers()  # i

    async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:

        batch_req = [JSONRPCRequest(method="markers.add", params= ap.marker.to_dict()) for ap in airports]
        async for resp in rpc.send_request(batch_req):
                pass

        # for ap in airports:
        #     marker_as_dict = ap.marker.to_dict()
        #     req = JSONRPCRequest(method="markers.add", params= marker_as_dict)
        #     async for resp in rpc.send_request(req):
        #         pass

        print("Rendered airports")# consume response


        # create a flight

        flight = build_flight(from_airport_name="YOW", to_airport_name="SYD", flight_id="flight1", plane_id="plane1")

        # planned_route = [t for t in great_circle_flight_generator(
        #                     from_latlng= AIRPORT_REGISTRY["YOW"].latlng,
        #                     to_latlng= AIRPORT_REGISTRY["YVR"].latlng,
        #                     ground_speed_knots = 500,
        #                     start_time = datetime.now(timezone.utc),
        #                     step=timedelta(minutes=1))]
        #
        # flight_duration = planned_route[-1][0] - planned_route[0][0]
        #
        # heading = bearing_deg(
        #         from_latlng= AIRPORT_REGISTRY["YOW"].latlng,
        #         to_latlng= AIRPORT_REGISTRY["YVR"].latlng)
        #
        # flight = Flight(
        #     id="flight1",
        #     plane=Plane(id="plane1", marker=DMarker(id="plane1", name="plane1", lat_lng=AIRPORT_REGISTRY["YOW"].latlng, icon="airplane", speed=500, heading=heading)),
        #     origin=AIRPORT_REGISTRY["YOW"],
        #     destination=AIRPORT_REGISTRY["YVR"],
        #     departure_time=datetime.now(timezone.utc),
        #     arrival_time=planned_route[-1][0],
        #     planned_route=planned_route,
        # )

        # add the plane to the map
        await _send(rpc, "markers.add", flight.plane.marker.to_dict())

        # add the route to the map

        planned_route_dpolyline = DPolyline(
            id="flight1_route",
            name="Flight 1 Route",
            path=[latlng for _, latlng in flight.planned_route],
            color="#3388ff",
            weight=3,
            opacity=1.0,
        )
        await _send(rpc, "polylines.add", planned_route_dpolyline.to_dict())
        print("Added plane")

# async def main() -> None:
#
#     initial_count = 1000
#
#     async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:
#
#         # Start listening for map events in the background
#         event_task = asyncio.create_task(listen_events(rpc))
#
#         # Seed initial markers
#         markers: dict[str, dict] = {}
#         for i in range(initial_count):
#             mid = str(uuid.uuid4())[:8]
#             name = f"{_CALLSIGNS[i % len(_CALLSIGNS)]}-{i + 1:02d}"
#             lat, lng = _random_latlng()
#             icon = _ICONS[i % len(_ICONS)]
#             markers[mid] = {
#                 "name": name,
#                 "lat": lat,
#                 "lng": lng,
#                 "heading": random.uniform(0, 360),
#                 "speed": random.uniform(0.4, 1.2),
#                 "icon": icon,
#             }
#             heading = markers[mid]["heading"]
#             speed = markers[mid]["speed"]
#             req = JSONRPCRequest(method="markers.add", params={"id": mid, "name": name, "latLng": [lat, lng], "icon": icon, "heading": heading, "speed": speed})
#             async for resp in rpc.send_request(req):
#                 pass  # consume response
#             print(f"  added {name} ({icon}) at ({lat}, {lng}) heading={heading:.0f}° speed={speed:.1f}")
#
#         print(f"\nSeeded {initial_count} markers.")
#
#         # Run the command demo
#         await run_command_demo(rpc, markers)
#
#         print("Starting update loop (Ctrl-C to stop)...\n")
#
#         try:
#             while True:
#                 await asyncio.sleep(1.2)
#                 mid, m = random.choice(list(markers.items()))
#                 new_latlng = _advance(m)
#                 req = JSONRPCRequest(method="markers.update", params={"id": mid, "name": m["name"], "latLng": new_latlng, "icon": m["icon"], "heading": m["heading"], "speed": m["speed"]})
#                 async for resp in rpc.send_request(req):
#                     if resp.id != req.id:
#                         print(f"  ERROR: unexpected response id {resp.id} != {req.id}")
#                         break
#                     if isinstance(resp, JSONRPCError):
#                         print(f"  ERROR: {resp.error}")
#                         break
#
#                     # Cast to JSONRPCResponse to access result attribute
#                     if isinstance(resp, JSONRPCResponse):
#                         result = resp.result
#                         if result and not result.get('ok', True):
#                             print(f"  ERROR: unexpected result {result}")
#
#                     print(f"  moved {m['name']} → ({new_latlng[0]}, {new_latlng[1]})")
#
#         finally:
#             event_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
