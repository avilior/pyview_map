import asyncio

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router

from pyview_map.views.components.dynamic_map.sources.api_marker_source import APIMarkerSource
from pyview_map.views.components.dynamic_map.sources.api_polyline_source import APIPolylineSource
from pyview_map.views.components.dynamic_map.sources.command_queue import CommandQueue
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster
from pyview_map.views.components.shared.latlng import LatLng
from pyview_map.views.components.dynamic_map.models.map_events import (
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
    id: str, name: str, latLng: list[float], channel: str,
    icon: str = "default", heading: float | None = None, speed: float | None = None,
    cid: str = "*",
) -> dict:
    ll = LatLng.from_list(latLng)
    APIMarkerSource.push_add(id, name, ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid)
    EventBroadcaster.broadcast(MarkerOpEvent(op="add", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("markers.update")
def markers_update(
    id: str, name: str, latLng: list[float], channel: str,
    icon: str = "default", heading: float | None = None, speed: float | None = None,
    cid: str = "*",
) -> dict:
    ll = LatLng.from_list(latLng)
    APIMarkerSource.push_update(id, name, ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid)
    EventBroadcaster.broadcast(MarkerOpEvent(op="update", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("markers.delete")
def markers_delete(id: str, channel: str, cid: str = "*") -> dict:
    APIMarkerSource.push_delete(id, channel=channel, cid=cid)
    EventBroadcaster.broadcast(MarkerOpEvent(op="delete", id=id, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("markers.list")
def markers_list(channel: str) -> dict:
    return {"markers": [m.to_dict() for m in APIMarkerSource._markers.get(channel, {}).values()]}


@jrpc_service.request("map.events.subscribe")
async def map_events_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()


# -- Map command methods ---------------------------------------------------

@jrpc_service.request("map.setView")
def map_set_view(latLng: list[float], zoom: int, channel: str, cid: str = "*") -> dict:
    CommandQueue.push(SetViewCmd(latLng=LatLng.from_list(latLng), zoom=zoom), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.panTo")
def map_pan_to(latLng: list[float], channel: str, cid: str = "*") -> dict:
    CommandQueue.push(PanToCmd(latLng=LatLng.from_list(latLng)), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.flyTo")
def map_fly_to(latLng: list[float], zoom: int, channel: str, cid: str = "*") -> dict:
    CommandQueue.push(FlyToCmd(latLng=LatLng.from_list(latLng), zoom=zoom), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.fitBounds")
def map_fit_bounds(corner1: list[float], corner2: list[float], channel: str, cid: str = "*") -> dict:
    CommandQueue.push(FitBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2)), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.flyToBounds")
def map_fly_to_bounds(corner1: list[float], corner2: list[float], channel: str, cid: str = "*") -> dict:
    CommandQueue.push(FlyToBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2)), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.setZoom")
def map_set_zoom(zoom: int, channel: str, cid: str = "*") -> dict:
    CommandQueue.push(SetZoomCmd(zoom=zoom), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.resetView")
def map_reset_view(channel: str, cid: str = "*") -> dict:
    CommandQueue.push(ResetViewCmd(), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.highlightMarker")
def map_highlight_marker(id: str, channel: str, cid: str = "*") -> dict:
    CommandQueue.push(HighlightMarkerCmd(id=id), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.highlightPolyline")
def map_highlight_polyline(id: str, channel: str, cid: str = "*") -> dict:
    CommandQueue.push(HighlightPolylineCmd(id=id), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.followMarker")
def map_follow_marker(id: str, channel: str, cid: str = "*") -> dict:
    CommandQueue.push(FollowMarkerCmd(id=id), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("map.unfollowMarker")
def map_unfollow_marker(channel: str, cid: str = "*") -> dict:
    CommandQueue.push(UnfollowMarkerCmd(), channel=channel, cid=cid)
    return {"ok": True}


# -- Polyline methods ------------------------------------------------------

@jrpc_service.request("polylines.add")
def polylines_add(
    id: str, name: str, path: list[list[float]], channel: str,
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None, cid: str = "*",
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    APIPolylineSource.push_add(id, name, ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray, channel=channel, cid=cid)
    EventBroadcaster.broadcast(PolylineOpEvent(op="add", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("polylines.update")
def polylines_update(
    id: str, name: str, path: list[list[float]], channel: str,
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None, cid: str = "*",
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    APIPolylineSource.push_update(id, name, ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray, channel=channel, cid=cid)
    EventBroadcaster.broadcast(PolylineOpEvent(op="update", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("polylines.delete")
def polylines_delete(id: str, channel: str, cid: str = "*") -> dict:
    APIPolylineSource.push_delete(id, channel=channel, cid=cid)
    EventBroadcaster.broadcast(PolylineOpEvent(op="delete", id=id, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("polylines.list")
def polylines_list(channel: str) -> dict:
    return {"polylines": [p.to_dict() for p in APIPolylineSource._polylines.get(channel, {}).values()]}


# -- FastAPI sub-app mounted at /api in __main__.py -----------------------

api_app = FastAPI(title="dmap Marker API")
api_app.include_router(mcp_router)


@api_app.get("/health")
async def health():
    return {"status": "ok"}
