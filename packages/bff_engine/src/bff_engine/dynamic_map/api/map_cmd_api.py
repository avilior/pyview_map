from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview.live_socket import pub_sub_hub

from dmap_models.latlng import LatLng
from bff_engine.shared.topics import map_cmd_topic
from bff_engine.dynamic_map.models.map_commands import (
    FitBoundsCmd,
    FlyToBoundsCmd,
    FlyToCmd,
    FollowMarkerCmd,
    HighlightMarkerCmd,
    HighlightPolylineCmd,
    PanToCmd,
    ResetViewCmd,
    SetViewCmd,
    SetZoomCmd,
    UnfollowMarkerCmd,
)


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
