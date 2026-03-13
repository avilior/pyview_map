import asyncio

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router

from pyview.live_socket import pub_sub_hub

from pyview_map.views.components.dynamic_map.sources.api_marker_source import marker_store
from pyview_map.views.components.dynamic_map.sources.api_polyline_source import polyline_store
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster
from pyview_map.views.components.shared.latlng import LatLng
from pyview_map.views.components.shared.topics import marker_ops_topic, polyline_ops_topic, map_cmd_topic
from pyview_map.views.components.dynamic_map.models.dmarker import DMarker
from pyview_map.views.components.dynamic_map.models.dpolyline import DPolyline
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
async def markers_add(
    id: str, name: str, latLng: list[float], channel: str,
    icon: str = "default", heading: float | None = None, speed: float | None = None,
    cid: str = "*",
) -> dict:
    ll = LatLng.from_list(latLng)
    marker = DMarker(id=id, name=name, lat_lng=ll, icon=icon, heading=heading, speed=speed)
    op: dict = {"op": "add", "id": id, "name": name, "latLng": latLng, "icon": icon}
    if heading is not None:
        op["heading"] = heading
    if speed is not None:
        op["speed"] = speed
    marker_store.store(op, channel=channel, item=marker)
    await pub_sub_hub.send_all_on_topic_async(marker_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(MarkerOpEvent(op="add", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("markers.update")
async def markers_update(
    id: str, name: str, latLng: list[float], channel: str,
    icon: str = "default", heading: float | None = None, speed: float | None = None,
    cid: str = "*",
) -> dict:
    ll = LatLng.from_list(latLng)
    marker = DMarker(id=id, name=name, lat_lng=ll, icon=icon, heading=heading, speed=speed)
    op: dict = {"op": "update", "id": id, "name": name, "latLng": latLng, "icon": icon}
    if heading is not None:
        op["heading"] = heading
    if speed is not None:
        op["speed"] = speed
    marker_store.store(op, channel=channel, item=marker)
    await pub_sub_hub.send_all_on_topic_async(marker_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(MarkerOpEvent(op="update", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("markers.delete")
async def markers_delete(id: str, channel: str, cid: str = "*") -> dict:
    op = {"op": "delete", "id": id}
    marker_store.store(op, channel=channel)
    await pub_sub_hub.send_all_on_topic_async(marker_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(MarkerOpEvent(op="delete", id=id, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("markers.list")
def markers_list(channel: str) -> dict:
    return {"markers": [m.to_dict() for m in marker_store.channel_items(channel).values()]}


@jrpc_service.request("map.subscribe")
async def map_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()


@jrpc_service.request("bff.subscribe")
async def bff_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()


# -- Map command methods ---------------------------------------------------

@jrpc_service.request("map.setView")
async def map_set_view(latLng: list[float], zoom: int, channel: str, cid: str = "*") -> dict:
    cmd = SetViewCmd(latLng=LatLng.from_list(latLng), zoom=zoom)
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.panTo")
async def map_pan_to(latLng: list[float], channel: str, cid: str = "*") -> dict:
    cmd = PanToCmd(latLng=LatLng.from_list(latLng))
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.flyTo")
async def map_fly_to(latLng: list[float], zoom: int, channel: str, cid: str = "*") -> dict:
    cmd = FlyToCmd(latLng=LatLng.from_list(latLng), zoom=zoom)
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.fitBounds")
async def map_fit_bounds(corner1: list[float], corner2: list[float], channel: str, cid: str = "*") -> dict:
    cmd = FitBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2))
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.flyToBounds")
async def map_fly_to_bounds(corner1: list[float], corner2: list[float], channel: str, cid: str = "*") -> dict:
    cmd = FlyToBoundsCmd(corner1=LatLng.from_list(corner1), corner2=LatLng.from_list(corner2))
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.setZoom")
async def map_set_zoom(zoom: int, channel: str, cid: str = "*") -> dict:
    cmd = SetZoomCmd(zoom=zoom)
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.resetView")
async def map_reset_view(channel: str, cid: str = "*") -> dict:
    cmd = ResetViewCmd()
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.highlightMarker")
async def map_highlight_marker(id: str, channel: str, cid: str = "*") -> dict:
    cmd = HighlightMarkerCmd(id=id)
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.highlightPolyline")
async def map_highlight_polyline(id: str, channel: str, cid: str = "*") -> dict:
    cmd = HighlightPolylineCmd(id=id)
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.followMarker")
async def map_follow_marker(id: str, channel: str, cid: str = "*") -> dict:
    cmd = FollowMarkerCmd(id=id)
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("map.unfollowMarker")
async def map_unfollow_marker(channel: str, cid: str = "*") -> dict:
    cmd = UnfollowMarkerCmd()
    await pub_sub_hub.send_all_on_topic_async(map_cmd_topic(channel, cid), cmd)
    return {"ok": True}


# -- Polyline methods ------------------------------------------------------

@jrpc_service.request("polylines.add")
async def polylines_add(
    id: str, name: str, path: list[list[float]], channel: str,
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None, cid: str = "*",
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    polyline = DPolyline(id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray)
    op: dict = {"op": "add", "id": id, "name": name, "path": path, "color": color, "weight": weight, "opacity": opacity}
    if dashArray is not None:
        op["dashArray"] = dashArray
    polyline_store.store(op, channel=channel, item=polyline)
    await pub_sub_hub.send_all_on_topic_async(polyline_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(PolylineOpEvent(op="add", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("polylines.update")
async def polylines_update(
    id: str, name: str, path: list[list[float]], channel: str,
    color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
    dashArray: str | None = None, cid: str = "*",
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    polyline = DPolyline(id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray)
    op: dict = {"op": "update", "id": id, "name": name, "path": path, "color": color, "weight": weight, "opacity": opacity}
    if dashArray is not None:
        op["dashArray"] = dashArray
    polyline_store.store(op, channel=channel, item=polyline)
    await pub_sub_hub.send_all_on_topic_async(polyline_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(PolylineOpEvent(op="update", id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dashArray=dashArray, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("polylines.delete")
async def polylines_delete(id: str, channel: str, cid: str = "*") -> dict:
    op = {"op": "delete", "id": id}
    polyline_store.store(op, channel=channel)
    await pub_sub_hub.send_all_on_topic_async(polyline_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(PolylineOpEvent(op="delete", id=id, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("polylines.list")
def polylines_list(channel: str) -> dict:
    return {"polylines": [p.to_dict() for p in polyline_store.channel_items(channel).values()]}


# -- FastAPI sub-app mounted at /api in __main__.py -----------------------

api_app = FastAPI(title="dmap Marker API")
api_app.include_router(mcp_router)


@api_app.get("/health")
async def health():
    return {"status": "ok"}
