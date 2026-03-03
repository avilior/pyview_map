import asyncio

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router

from pyview_map.views.dynamic_map.api_marker_source import APIMarkerSource
from pyview_map.views.dynamic_map.api_polyline_source import APIPolylineSource
from pyview_map.views.dynamic_map.command_queue import CommandQueue
from pyview_map.views.dynamic_map.event_broadcaster import EventBroadcaster
from pyview_map.views.dynamic_map.latlng import LatLng
from pyview_map.views.dynamic_map.map_events import (
    FitBoundsCmd,
    FlyToBoundsCmd,
    FlyToCmd,
    HighlightMarkerCmd,
    HighlightPolylineCmd,
    MarkerOpEvent,
    PolylineOpEvent,
    ResetViewCmd,
    SetViewCmd,
    SetZoomCmd,
)


# -- Register marker methods on the global JRPCService instance -----------

@jrpc_service.request("markers.add")
def markers_add(id: str, name: str, latLng: list[float], icon: str = "default", heading: float | None = None, speed: float | None = None) -> dict:
    ll = LatLng.from_list(latLng)
    APIMarkerSource.push_add(id, name, ll, icon=icon, heading=heading, speed=speed)
    EventBroadcaster.broadcast(MarkerOpEvent(op="add", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed))
    return {"ok": True}


@jrpc_service.request("markers.update")
def markers_update(id: str, name: str, latLng: list[float], icon: str = "default", heading: float | None = None, speed: float | None = None) -> dict:
    ll = LatLng.from_list(latLng)
    APIMarkerSource.push_update(id, name, ll, icon=icon, heading=heading, speed=speed)
    EventBroadcaster.broadcast(MarkerOpEvent(op="update", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed))
    return {"ok": True}


@jrpc_service.request("markers.delete")
def markers_delete(id: str) -> dict:
    APIMarkerSource.push_delete(id)
    EventBroadcaster.broadcast(MarkerOpEvent(op="delete", id=id))
    return {"ok": True}


@jrpc_service.request("markers.list")
def markers_list() -> dict:
    return {"markers": [m.to_dict() for m in APIMarkerSource._markers.values()]}


@jrpc_service.request("map.events.subscribe")
async def map_events_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()


# -- Map command methods ---------------------------------------------------

@jrpc_service.request("map.setView")
def map_set_view(latLng: list[float], zoom: int) -> dict:
    CommandQueue.push(SetViewCmd(latLng=LatLng.from_list(latLng), zoom=zoom))
    return {"ok": True}


@jrpc_service.request("map.flyTo")
def map_fly_to(latLng: list[float], zoom: int) -> dict:
    CommandQueue.push(FlyToCmd(latLng=LatLng.from_list(latLng), zoom=zoom))
    return {"ok": True}


@jrpc_service.request("map.fitBounds")
def map_fit_bounds(corner1: list[float], corner2: list[float]) -> dict:
    CommandQueue.push(FitBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2)))
    return {"ok": True}


@jrpc_service.request("map.flyToBounds")
def map_fly_to_bounds(corner1: list[float], corner2: list[float]) -> dict:
    CommandQueue.push(FlyToBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2)))
    return {"ok": True}


@jrpc_service.request("map.setZoom")
def map_set_zoom(zoom: int) -> dict:
    CommandQueue.push(SetZoomCmd(zoom=zoom))
    return {"ok": True}


@jrpc_service.request("map.resetView")
def map_reset_view() -> dict:
    CommandQueue.push(ResetViewCmd())
    return {"ok": True}


@jrpc_service.request("map.highlightMarker")
def map_highlight_marker(id: str) -> dict:
    CommandQueue.push(HighlightMarkerCmd(id=id))
    return {"ok": True}


@jrpc_service.request("map.highlightPolyline")
def map_highlight_polyline(id: str) -> dict:
    CommandQueue.push(HighlightPolylineCmd(id=id))
    return {"ok": True}


# -- Polyline methods ------------------------------------------------------

@jrpc_service.request("polylines.add")
def polylines_add(
    id: str, name: str, path: list[list[float]],
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None,
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    APIPolylineSource.push_add(id, name, ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray)
    EventBroadcaster.broadcast(PolylineOpEvent(op="add", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray))
    return {"ok": True}


@jrpc_service.request("polylines.update")
def polylines_update(
    id: str, name: str, path: list[list[float]],
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None,
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    APIPolylineSource.push_update(id, name, ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray)
    EventBroadcaster.broadcast(PolylineOpEvent(op="update", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray))
    return {"ok": True}


@jrpc_service.request("polylines.delete")
def polylines_delete(id: str) -> dict:
    APIPolylineSource.push_delete(id)
    EventBroadcaster.broadcast(PolylineOpEvent(op="delete", id=id))
    return {"ok": True}


@jrpc_service.request("polylines.list")
def polylines_list() -> dict:
    return {"polylines": [p.to_dict() for p in APIPolylineSource._polylines.values()]}


# -- FastAPI sub-app mounted at /api in __main__.py -----------------------

api_app = FastAPI(title="dmap Marker API")
api_app.include_router(mcp_router)


@api_app.get("/health")
async def health():
    return {"status": "ok"}
