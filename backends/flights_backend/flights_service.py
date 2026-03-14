"""Flights Service — the Backend (BE).

Simulates aircraft flights and pushes real-time positions to the BFF map.
The BFF (PyView server) connects here on mount to subscribe to flight data.

    cd backends/flights_backend && uv run uvicorn flights_service:app --host 0.0.0.0 --port 8300
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Self
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from http_stream_transport.jsonrpc.handler_meta import RequestInfo
from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router
from pyview_map.openrpc import setup_rpc_docs
from jrpc_common.jrpc_model import JSONRPCRequest

from pyview_map.components.dynamic_map import DPolyline
from pyview_map.components.dynamic_map.models.dmarker import DMarker
from pyview_map.components.shared.latlng import LatLng
from navigation_utils import great_circle_flight_generator, bearing_deg, great_circle_position_at_time

LOG = logging.getLogger(__name__)

BFF_TOKEN = "tok-acme-001"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _send(rpc: ClientRPC, method: str, params: dict | None = None) -> None:
    """Fire a JSON-RPC request and consume the response."""
    req = JSONRPCRequest(method=method, params=params or {})
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
        ap.marker = DMarker(id=f"ap_{idx + 1}_{ap.name}", name=ap.name, lat_lng=ap.latlng, icon="black-square")


@dataclass
class Plane:
    id: str
    marker: DMarker


class Flight:
    def __init__(
        self,
        id: str,
        plane: Plane,
        origin: Airport,
        destination: Airport,
        departure_time: datetime,
        arrival_time: datetime,
        planned_route: list[Tuple[datetime, LatLng]],
        last_position: LatLng,
    ) -> None:

        self.id = id
        self.plane = plane
        self.origin: Airport = origin
        self.destination: Airport = destination

        self.departure_time: datetime = departure_time
        self.arrival_time: datetime = arrival_time
        self.planned_route: list[Tuple[datetime, LatLng]] = planned_route
        self.last_position: LatLng = last_position
        self.flight_completed: bool = False

    @classmethod
    def build_flight(
        cls,
        origin_airport_name: str,
        destination_airport_name: str,
        flight_id: str,
        plane_id: str,
        ground_speed_knots: int,
    ) -> Self:

        origin_airport = AIRPORT_REGISTRY[origin_airport_name]
        destination_airport = AIRPORT_REGISTRY[destination_airport_name]

        planned_route = list(
            great_circle_flight_generator(
                from_latlng=origin_airport.latlng,
                to_latlng=destination_airport.latlng,
                ground_speed_knots=ground_speed_knots,
                start_time=datetime.now(timezone.utc),
                step=timedelta(minutes=1),
            )
        )

        heading = bearing_deg(from_latlng=origin_airport.latlng, to_latlng=destination_airport.latlng)

        plane_marker = DMarker(
            id=plane_id,
            name=plane_id,
            lat_lng=origin_airport.latlng,
            icon="airplane",
            speed=ground_speed_knots,
            heading=heading,
        )

        plane = Plane(id=plane_id, marker=plane_marker)

        return cls(
            id=flight_id,
            plane=plane,
            origin=origin_airport,
            destination=destination_airport,
            departure_time=datetime.now(timezone.utc),
            arrival_time=planned_route[-1][0],
            planned_route=planned_route,
            last_position=origin_airport.latlng,
        )

    async def start(self, rpc: ClientRPC, *, map_channel: str, map_cid: str):

        params = self.plane.marker.to_dict()
        params["channel"] = map_channel
        params["cid"] = map_cid
        await _send(rpc, "markers.add", params)

        planned_route_dpolyline = DPolyline(
            id=f"{self.id}_route",
            name=f"{self.id} Route",
            path=[latlng for _, latlng in self.planned_route],
            color="#3388ff",
            weight=3,
            opacity=1.0,
        )
        polyline_params = planned_route_dpolyline.to_dict()
        polyline_params["channel"] = map_channel
        polyline_params["cid"] = map_cid
        await _send(rpc, "polylines.add", polyline_params)

        LOG.info("Flight %s: %s → %s started", self.id, self.origin.name, self.destination.name)

        while True:
            await asyncio.sleep(1)

            assert self.plane.marker.speed is not None
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

            params = self.plane.marker.to_dict()
            params["channel"] = map_channel
            params["cid"] = map_cid
            await _send(rpc, "markers.update", params)

            if current_latlng == self.destination.latlng:
                LOG.info("Flight %s arrived at %s", self.id, self.destination.name)
                break


# ---------------------------------------------------------------------------
# Reverse connection (BE → BFF)
# ---------------------------------------------------------------------------


async def _reverse_connection(callback_url: str, map_channel: str, map_cid: str) -> None:
    """Connect back to the BFF and push airport markers + live flight data."""
    LOG.info("reverse connection → %s (map=%s/%s)", callback_url, map_channel, map_cid)
    try:
        async with ClientRPC(base_url=callback_url, auth_token=BFF_TOKEN) as rpc:
            init_airport_markers()

            # Add airport markers
            for ap in airports:
                assert ap.marker is not None
                params = ap.marker.to_dict()
                params["channel"] = map_channel
                params["cid"] = map_cid
                await _send(rpc, "markers.add", params)
            LOG.info("Rendered %d airports", len(airports))

            # Create and run flight
            flight = Flight.build_flight("YOW", "YUL", flight_id="flight1", plane_id="plane1", ground_speed_knots=500)
            await flight.start(rpc, map_channel=map_channel, map_cid=map_cid)

    except asyncio.CancelledError:
        LOG.info("reverse connection cancelled")
    except Exception:
        LOG.exception("reverse connection failed")


# ---------------------------------------------------------------------------
# JRPC method — BFF calls this on mount
# ---------------------------------------------------------------------------


@jrpc_service.request("flights.subscribe")
async def flights_subscribe(info: RequestInfo, callback_url: str, map_channel: str, map_cid: str) -> asyncio.Queue:
    """Establish BE→BFF SSE channel and spawn reverse connection."""
    LOG.info("BFF subscribed: map=%s/%s, callback=%s", map_channel, map_cid, callback_url)
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    asyncio.create_task(_reverse_connection(callback_url, map_channel, map_cid))
    return queue


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Flights Service")
app.include_router(mcp_router, prefix="/api")

setup_rpc_docs(
    app,
    jrpc_service,
    title="Flights Service",
    description="Flight simulation backend — pushes real-time aircraft positions via JSON-RPC",
    prefix="/api",
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )

    uvicorn.run("flights_service:app", host="0.0.0.0", port=8300, reload=False)
