from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview.live_socket import pub_sub_hub

from dmap_models.dpolyline import DPolyline
from dmap_models.latlng import LatLng
from dmap_models.map_events import PolylineOpEvent
from bff_engine.dynamic_map.sources.api_polyline_source import polyline_store
from bff_engine.shared.event_broadcaster import EventBroadcaster
from bff_engine.shared.topics import polyline_ops_topic


@jrpc_service.request("polylines.add")
async def polylines_add(
    id: str,
    name: str,
    path: list[list[float]],
    channel: str,
    color: str = "#3388ff",
    weight: int = 3,
    opacity: float = 1.0,
    dashArray: str | None = None,
    cid: str = "*",
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    polyline = DPolyline(
        id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray
    )
    op: dict = {"op": "add", "id": id, "name": name, "path": path, "color": color, "weight": weight, "opacity": opacity}
    if dashArray is not None:
        op["dashArray"] = dashArray
    polyline_store.store(op, channel=channel, item=polyline)
    await pub_sub_hub.send_all_on_topic_async(polyline_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(
        PolylineOpEvent(
            op="add",
            id=id,
            name=name,
            path=ll_path,
            color=color,
            weight=weight,
            opacity=opacity,
            dashArray=dashArray,
            channel=channel,
            cid=cid,
        )
    )
    return {"ok": True}


@jrpc_service.request("polylines.update")
async def polylines_update(
    id: str,
    name: str,
    path: list[list[float]],
    channel: str,
    color: str = "#3388ff",
    weight: int = 3,
    opacity: float = 1.0,
    dashArray: str | None = None,
    cid: str = "*",
) -> dict:
    ll_path = [LatLng.from_list(p) for p in path]
    polyline = DPolyline(
        id=id, name=name, path=ll_path, color=color, weight=weight, opacity=opacity, dash_array=dashArray
    )
    op: dict = {
        "op": "update",
        "id": id,
        "name": name,
        "path": path,
        "color": color,
        "weight": weight,
        "opacity": opacity,
    }
    if dashArray is not None:
        op["dashArray"] = dashArray
    polyline_store.store(op, channel=channel, item=polyline)
    await pub_sub_hub.send_all_on_topic_async(polyline_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(
        PolylineOpEvent(
            op="update",
            id=id,
            name=name,
            path=ll_path,
            color=color,
            weight=weight,
            opacity=opacity,
            dashArray=dashArray,
            channel=channel,
            cid=cid,
        )
    )
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
