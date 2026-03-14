import asyncio

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview.live_socket import pub_sub_hub

from pyview_map.components.dynamic_list.sources.api_list_source import list_store
from pyview_map.components.dynamic_list.models.dlist_item import DListItem
from pyview_map.components.dynamic_list.models.list_events import HighlightListItemCmd, ListItemOpEvent
from pyview_map.components.shared.event_broadcaster import EventBroadcaster
from pyview_map.components.shared.topics import list_ops_topic, list_cmd_topic


@jrpc_service.request("list.add")
async def list_add(
    id: str, label: str, channel: str, subtitle: str = "", at: int = -1, cid: str = "*", data: dict | None = None
) -> dict:
    item_data = data or {}
    item = DListItem(id=id, label=label, subtitle=subtitle, data=item_data)
    op = {"op": "add", "id": id, "label": label, "subtitle": subtitle, "at": at, "data": item_data}
    list_store.store(op, channel=channel, item=item)
    await pub_sub_hub.send_all_on_topic_async(list_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(
        ListItemOpEvent(op="add", id=id, label=label, subtitle=subtitle, at=at, channel=channel, cid=cid)
    )
    return {"ok": True}


@jrpc_service.request("list.remove")
async def list_remove(id: str, channel: str, cid: str = "*") -> dict:
    op = {"op": "delete", "id": id}
    list_store.store(op, channel=channel)
    await pub_sub_hub.send_all_on_topic_async(list_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(ListItemOpEvent(op="delete", id=id, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("list.clear")
async def list_clear(channel: str, cid: str = "*") -> dict:
    op = {"op": "clear"}
    list_store.store(op, channel=channel)
    await pub_sub_hub.send_all_on_topic_async(list_ops_topic(channel, cid), op)
    EventBroadcaster.broadcast(ListItemOpEvent(op="clear", channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("list.highlight")
async def list_highlight(id: str, channel: str, cid: str = "*") -> dict:
    cmd = HighlightListItemCmd(id=id)
    await pub_sub_hub.send_all_on_topic_async(list_cmd_topic(channel, cid), cmd)
    return {"ok": True}


@jrpc_service.request("list.list")
def list_list(channel: str) -> dict:
    return {
        "items": [
            {"id": item.id, "label": item.label, "subtitle": item.subtitle, "data": item.data}
            for item in list_store.channel_items(channel).values()
        ]
    }


@jrpc_service.request("list.subscribe")
async def list_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()
