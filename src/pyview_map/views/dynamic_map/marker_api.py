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
    FollowMarkerCmd,
    HighlightMarkerCmd,
    HighlightPolylineCmd,
    MarkerOpEvent,
    PanToCmd,
    PolylineOpEvent,
    ResetViewCmd,
    SetViewCmd,
    SetZoomCmd,
    UnfollowMarkerCmd,
)


# -- Register marker methods on the global JRPCService instance -----------

@jrpc_service.request("markers.add")
def markers_add(
    id: str, name: str, latLng: list[float],
    icon: str = "default", heading: float | None = None, speed: float | None = None,
    component_id: str | None = None,
) -> dict:
    ll = LatLng.from_list(latLng)
    APIMarkerSource.push_add(id, name, ll, icon=icon, heading=heading, speed=speed, component_id=component_id)
    EventBroadcaster.broadcast(MarkerOpEvent(op="add", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed))
    return {"ok": True}


@jrpc_service.request("markers.update")
def markers_update(
    id: str, name: str, latLng: list[float],
    icon: str = "default", heading: float | None = None, speed: float | None = None,
    component_id: str | None = None,
) -> dict:
    ll = LatLng.from_list(latLng)
    APIMarkerSource.push_update(id, name, ll, icon=icon, heading=heading, speed=speed, component_id=component_id)
    EventBroadcaster.broadcast(MarkerOpEvent(op="update", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed))
    return {"ok": True}


@jrpc_service.request("markers.delete")
def markers_delete(id: str, component_id: str | None = None) -> dict:
    APIMarkerSource.push_delete(id, component_id=component_id)
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
def map_set_view(latLng: list[float], zoom: int, component_id: str | None = None) -> dict:
    CommandQueue.push(SetViewCmd(latLng=LatLng.from_list(latLng), zoom=zoom), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.panTo")
def map_pan_to(latLng: list[float], component_id: str | None = None) -> dict:
    CommandQueue.push(PanToCmd(latLng=LatLng.from_list(latLng)), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.flyTo")
def map_fly_to(latLng: list[float], zoom: int, component_id: str | None = None) -> dict:
    CommandQueue.push(FlyToCmd(latLng=LatLng.from_list(latLng), zoom=zoom), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.fitBounds")
def map_fit_bounds(corner1: list[float], corner2: list[float], component_id: str | None = None) -> dict:
    CommandQueue.push(FitBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2)), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.flyToBounds")
def map_fly_to_bounds(corner1: list[float], corner2: list[float], component_id: str | None = None) -> dict:
    CommandQueue.push(FlyToBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2)), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.setZoom")
def map_set_zoom(zoom: int, component_id: str | None = None) -> dict:
    CommandQueue.push(SetZoomCmd(zoom=zoom), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.resetView")
def map_reset_view(component_id: str | None = None) -> dict:
    CommandQueue.push(ResetViewCmd(), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.highlightMarker")
def map_highlight_marker(id: str, component_id: str | None = None) -> dict:
    CommandQueue.push(HighlightMarkerCmd(id=id), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.highlightPolyline")
def map_highlight_polyline(id: str, component_id: str | None = None) -> dict:
    CommandQueue.push(HighlightPolylineCmd(id=id), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.followMarker")
def map_follow_marker(id: str, component_id: str | None = None) -> dict:
    CommandQueue.push(FollowMarkerCmd(id=id), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("map.unfollowMarker")
def map_unfollow_marker(component_id: str | None = None) -> dict:
    CommandQueue.push(UnfollowMarkerCmd(), component_id=component_id)
    return {"ok": True}


# -- Polyline methods ------------------------------------------------------

@jrpc_service.request("polylines.add")
def polylines_add(
    id: str, name: str, path: list[list[float]],
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None,
    component_id: str | None = None,
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    APIPolylineSource.push_add(id, name, ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray, component_id=component_id)
    EventBroadcaster.broadcast(PolylineOpEvent(op="add", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray))
    return {"ok": True}


@jrpc_service.request("polylines.update")
def polylines_update(
    id: str, name: str, path: list[list[float]],
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None,
    component_id: str | None = None,
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    APIPolylineSource.push_update(id, name, ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray, component_id=component_id)
    EventBroadcaster.broadcast(PolylineOpEvent(op="update", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray))
    return {"ok": True}


@jrpc_service.request("polylines.delete")
def polylines_delete(id: str, component_id: str | None = None) -> dict:
    APIPolylineSource.push_delete(id, component_id=component_id)
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
