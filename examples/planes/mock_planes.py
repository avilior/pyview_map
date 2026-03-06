"""mock_planes.py — flight simulation client for the /dmap dynamic map.

Run this while the server is up to see a plane fly from Ottawa to Montreal:

    uv run python examples/planes/mock_planes.py

To target a specific component instance (e.g. on the /mmap multi-map page):

    uv run python examples/planes/mock_planes.py --component-id left
"""

import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Tuple, Self

from dataclasses import dataclass
from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import (
    JSONRPCRequest, JSONRPCResponse, JSONRPCNotification, JSONRPCErrorResponse,
)

from pyview_map.views.components.dynamic_map import DPolyline
from pyview_map.views.components.dynamic_map.dmarker import DMarker
from pyview_map.views.components.dynamic_map.latlng import LatLng
from pyview_map.views.components.dynamic_map.map_events import (
    MarkerOpEvent, MarkerEvent, MapEvent, parse_event,
)
from navigation_utils import great_circle_flight_generator, bearing_deg, great_circle_position_at_time

BASE_URL = "http://localhost:8123/api"
AUTH_TOKEN = "tok-acme-001"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _send(rpc: ClientRPC, method: str, params: dict | None = None, *, component_id: str | None = None) -> None:
    """Fire a JSON-RPC request and consume the response."""
    p = dict(params) if params else {}
    if component_id is not None:
        p["component_id"] = component_id
    req = JSONRPCRequest(method=method, params=p)
    async for _ in rpc.send_request(req):
        pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Airport:
    name: str
    latlng: LatLng
    marker: DMarker | None = None


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
    marker: DMarker | None = None


class Flight:

    def __init__(self, id: str, plane: Plane, origin: Airport, destination: Airport,
                 departure_time: datetime | None = None,
                 arrival_time: datetime | None = None,
                 planned_route: list[Tuple[datetime, LatLng]] | None = None,
                 last_position: LatLng | None = None) -> None:

        self.id = id
        self.plane = plane
        self.origin: Airport = origin
        self.destination: Airport = destination

        self.departure_time: datetime | None = departure_time
        self.arrival_time: datetime | None = arrival_time
        self.planned_route: list[Tuple[datetime, LatLng]] | None = planned_route
        self.last_position: LatLng | None = last_position
        self.flight_completed: bool = False


    @classmethod
    def build_flight(cls, origin_airport_name: str, destination_airport_name: str, flight_id: str, plane_id: str, ground_speed_knots: int) -> Self:

        origin_airport = AIRPORT_REGISTRY[origin_airport_name]
        destination_airport = AIRPORT_REGISTRY[destination_airport_name]

        planned_route = list(great_circle_flight_generator(
            from_latlng=origin_airport.latlng,
            to_latlng=destination_airport.latlng,
            ground_speed_knots=ground_speed_knots,
            start_time=datetime.now(timezone.utc),
            step=timedelta(minutes=1),
        ))

        heading = bearing_deg(from_latlng=origin_airport.latlng, to_latlng=destination_airport.latlng)

        plane_marker  = DMarker( id=plane_id, name=plane_id,
                                 lat_lng=origin_airport.latlng, icon="airplane",
                                 speed=ground_speed_knots, heading=heading)

        plane = Plane( id=plane_id, marker=plane_marker)

        return cls(
            id = flight_id,
            plane = plane,
            origin = origin_airport,
            destination = destination_airport,
            departure_time = datetime.now(timezone.utc),
            arrival_time = planned_route[-1][0],
            planned_route = planned_route,
            last_position = origin_airport.latlng,
        )

    async def start(self, rpc, *, component_id: str | None = None):

        await _send(rpc, "markers.add", self.plane.marker.to_dict(), component_id=component_id)

        planned_route_dpolyline = DPolyline(
            id="flight1_route",
            name="Flight 1 Route",
            path=[latlng for _, latlng in self.planned_route],
            color="#3388ff",
            weight=3,
            opacity=1.0,
        )
        await _send(rpc, "polylines.add", planned_route_dpolyline.to_dict(), component_id=component_id)
        # await _send(rpc, "map.followMarker", {"id": "plane1"}, component_id=component_id)
        print(f"Added plane{' (component_id=' + component_id + ')' if component_id else ''}")

        while True:

            await asyncio.sleep(1)

            current_latlng = great_circle_position_at_time(
                from_latlng=self.origin.latlng,
                to_latlng=self.destination.latlng,
                ground_speed_knots=self.plane.marker.speed,
                start_time=self.departure_time,
                current_time=datetime.now(timezone.utc),
            )

            heading = bearing_deg(from_latlng=self.last_position, to_latlng=current_latlng)
            self.plane.marker.heading = heading
            self.plane.marker.lat_lng = current_latlng
            self.last_position = current_latlng

            await _send(rpc, "markers.update", self.plane.marker.to_dict(), component_id=component_id)

            # if the plane arrived at destination break
            if current_latlng == self.destination.latlng:
                print(f"The flight arrived at destination: {datetime.now(timezone.utc)}")
                break


# ---------------------------------------------------------------------------
# Event listener
# ---------------------------------------------------------------------------

async def listen_events(rpc: ClientRPC) -> None:
    """Subscribe to map/marker events and print them as they arrive."""
    req = JSONRPCRequest(method="map.events.subscribe")
    async for msg in rpc.send_request(req):
        match msg:
            case JSONRPCNotification() if isinstance(msg.params, dict):
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
    parser = argparse.ArgumentParser(description="Flight simulation client")
    parser.add_argument("--component-id", default=None, help="Target a specific component instance (e.g. 'left')")
    args = parser.parse_args()
    component_id: str | None = args.component_id

    init_airport_markers()

    all_tasks: list[asyncio.Task] = []

    async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:

        all_tasks.append(asyncio.create_task(listen_events(rpc)))

        # Add airport markers (batched)
        batch_req = []
        for ap in airports:
            params = ap.marker.to_dict()
            if component_id is not None:
                params["component_id"] = component_id
            batch_req.append(JSONRPCRequest(method="markers.add", params=params))
        async for resp in rpc.send_request(batch_req):
            pass
        print(f"Rendered airports{' (component_id=' + component_id + ')' if component_id else ''}")

        # Create and display flight

        try:

            flight = Flight.build_flight("YOW", "YUL", flight_id="flight1", plane_id="plane1", ground_speed_knots=500)

            all_tasks.append(asyncio.create_task(flight.start(rpc, component_id=component_id)))

            while True:
                await asyncio.sleep(1)

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("Keyboard interrupt")

        finally:

            # cancel all tasks and wait for them to finish
            [task.cancel() for task in all_tasks]
            await asyncio.gather(*all_tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
