"""mock_planes.py — flight simulation client for the /dmap dynamic map.

Run this while the server is up to see a plane fly from Ottawa to Sydney:

    uv run python examples/planes/mock_planes.py
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Tuple

from dataclasses import dataclass
from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import (
    JSONRPCRequest, JSONRPCResponse, JSONRPCNotification, JSONRPCErrorResponse,
)

from pyview_map.views.dynamic_map import DPolyline
from pyview_map.views.dynamic_map.dmarker import DMarker
from pyview_map.views.dynamic_map.latlng import LatLng
from pyview_map.views.dynamic_map.map_events import (
    MarkerOpEvent, MarkerEvent, MapEvent, parse_event,
)
from navigation_utils import great_circle_flight_generator, bearing_deg, great_circle_position_at_time

BASE_URL = "http://localhost:8123/api"
AUTH_TOKEN = "tok-acme-001"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _send(rpc: ClientRPC, method: str, params: dict | None = None) -> None:
    """Fire a JSON-RPC request and consume the response."""
    req = JSONRPCRequest(method=method, params=params or {})
    async for resp in rpc.send_request(req):
        pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

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

AIRPORT_REGISTRY = {ap.name: ap for ap in airports}


def init_airport_markers():
    for idx, ap in enumerate(airports):
        ap.marker = DMarker(
            id=f"ap_{idx + 1}_{ap.name}", name=ap.name,
            lat_lng=ap.latlng, icon="black-square",
        )


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
    last_position: LatLng | None = None


def build_flight(from_airport_name: str, to_airport_name: str, flight_id: str, plane_id: str) -> Flight:
    from_airport = AIRPORT_REGISTRY[from_airport_name]
    to_airport = AIRPORT_REGISTRY[to_airport_name]

    planned_route = list(great_circle_flight_generator(
        from_latlng=from_airport.latlng,
        to_latlng=to_airport.latlng,
        ground_speed_knots=500,
        start_time=datetime.now(timezone.utc),
        step=timedelta(minutes=1),
    ))

    heading = bearing_deg(from_latlng=from_airport.latlng, to_latlng=to_airport.latlng)

    return Flight(
        id=flight_id,
        plane=Plane(
            id=plane_id,
            marker=DMarker(
                id=plane_id, name=plane_id,
                lat_lng=from_airport.latlng, icon="airplane",
                speed=500, heading=heading,
            ),
        ),
        origin=from_airport,
        destination=to_airport,
        departure_time=datetime.now(timezone.utc),
        arrival_time=planned_route[-1][0],
        planned_route=planned_route,
        last_position=from_airport.latlng,
    )


# ---------------------------------------------------------------------------
# Event listener
# ---------------------------------------------------------------------------

async def listen_events(rpc: ClientRPC) -> None:
    """Subscribe to map/marker events and print them as they arrive."""
    req = JSONRPCRequest(method="map.events.subscribe")
    async for msg in rpc.send_request(req):
        match msg:
            case JSONRPCNotification():
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
                print(f"Response received: {msg} END OF CHANNEL")
            case JSONRPCErrorResponse():
                print(f"Error response received: {msg}")
            case _:
                print(f"Unknown message type: {type(msg)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    init_airport_markers()

    async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:
        event_task = asyncio.create_task(listen_events(rpc))

        # Add airport markers (batched)
        batch_req = [JSONRPCRequest(method="markers.add", params=ap.marker.to_dict()) for ap in airports]
        async for resp in rpc.send_request(batch_req):
            pass
        print("Rendered airports")

        # Create and display flight
        flight = build_flight("YOW", "SYD", flight_id="flight1", plane_id="plane1")
        await _send(rpc, "markers.add", flight.plane.marker.to_dict())

        planned_route_dpolyline = DPolyline(
            id="flight1_route",
            name="Flight 1 Route",
            path=[latlng for _, latlng in flight.planned_route],
            color="#3388ff",
            weight=3,
            opacity=1.0,
        )
        await _send(rpc, "polylines.add", planned_route_dpolyline.to_dict())
        await _send(rpc, "map.followMarker", {"id": "plane1"})
        print("Added plane — following plane1")

        try:
            while True:
                await asyncio.sleep(1)

                current_latlng = great_circle_position_at_time(
                    from_latlng=flight.origin.latlng,
                    to_latlng=flight.destination.latlng,
                    ground_speed_knots=flight.plane.marker.speed,
                    start_time=flight.departure_time,
                    current_time=datetime.now(timezone.utc),
                )

                heading = bearing_deg(from_latlng=flight.last_position, to_latlng=current_latlng)
                flight.plane.marker.heading = heading
                flight.plane.marker.lat_lng = current_latlng
                flight.last_position = current_latlng

                await _send(rpc, "markers.update", flight.plane.marker.to_dict())
        finally:
            event_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
