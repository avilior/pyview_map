from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview.live_socket import pub_sub_hub

from dmap_models.dmarker import DMarker
from dmap_models.latlng import LatLng
from dmap_models.map_events import MarkerOpEvent
from bff_engine.dynamic_map.sources.api_marker_source import marker_store
from bff_engine.shared.event_broadcaster import EventBroadcaster
from bff_engine.shared.topics import marker_ops_topic


@jrpc_service.request("markers.add")
async def markers_add(
    id: str,
    name: str,
    latLng: list[float],
    channel: str,
    icon: str = "default",
    heading: float | None = None,
    speed: float | None = None,
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
    EventBroadcaster.broadcast(
        MarkerOpEvent(
            op="add", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid
        )
    )
    return {"ok": True}


@jrpc_service.request("markers.update")
async def markers_update(
    id: str,
    name: str,
    latLng: list[float],
    channel: str,
    icon: str = "default",
    heading: float | None = None,
    speed: float | None = None,
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
    EventBroadcaster.broadcast(
        MarkerOpEvent(
            op="update", id=id, name=name, latLng=ll, icon=icon, heading=heading, speed=speed, channel=channel, cid=cid
        )
    )
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
