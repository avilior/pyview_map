from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview_map.views.components.dynamic_list.sources.api_list_source import list_source
from pyview_map.views.components.dynamic_list.sources.list_command_queue import list_command_queue
from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem
from pyview_map.views.components.dynamic_list.models.list_events import HighlightListItemCmd, ListItemOpEvent
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster

import asyncio


@jrpc_service.request("list.add")
def list_add(
    id: str, label: str, channel: str,
    subtitle: str = "", at: int = -1, cid: str = "*",
    data: dict | None = None,
) -> dict:
    item_data = data or {}
    item = DListItem(id=id, label=label, subtitle=subtitle, data=item_data)
    list_source.push_op({"op": "add", "id": id, "label": label, "subtitle": subtitle, "at": at, "data": item_data}, channel=channel, cid=cid, item=item)
    EventBroadcaster.broadcast(ListItemOpEvent(op="add", id=id, label=label, subtitle=subtitle, at=at, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("list.remove")
def list_remove(id: str, channel: str, cid: str = "*") -> dict:
    list_source.push_op({"op": "delete", "id": id}, channel=channel, cid=cid)
    EventBroadcaster.broadcast(ListItemOpEvent(op="delete", id=id, channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("list.clear")
def list_clear(channel: str, cid: str = "*") -> dict:
    list_source.push_op({"op": "clear"}, channel=channel, cid=cid)
    EventBroadcaster.broadcast(ListItemOpEvent(op="clear", channel=channel, cid=cid))
    return {"ok": True}


@jrpc_service.request("list.highlight")
def list_highlight(id: str, channel: str, cid: str = "*") -> dict:
    list_command_queue.push(HighlightListItemCmd(id=id), channel=channel, cid=cid)
    return {"ok": True}


@jrpc_service.request("list.list")
def list_list(channel: str) -> dict:
    return {"items": [{"id": item.id, "label": item.label, "subtitle": item.subtitle, "data": item.data} for item in list_source.channel_items(channel).values()]}

@jrpc_service.request("list.events.subscribe")
async def map_events_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()

