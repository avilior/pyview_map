from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview_map.views.components.dynamic_list.sources.api_list_source import APIListSource
from pyview_map.views.components.dynamic_list.sources.list_command_queue import ListCommandQueue
from pyview_map.views.components.dynamic_list.models.list_events import HighlightListItemCmd, ListItemOpEvent
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster


@jrpc_service.request("list.add")
def list_add(
    id: str, label: str, subtitle: str = "",
    at: int = -1, component_id: str | None = None,
) -> dict:
    APIListSource.push_add(id, label, subtitle, at=at, component_id=component_id)
    EventBroadcaster.broadcast(ListItemOpEvent(op="add", id=id, label=label, subtitle=subtitle, at=at))
    return {"ok": True}


@jrpc_service.request("list.remove")
def list_remove(id: str, component_id: str | None = None) -> dict:
    APIListSource.push_remove(id, component_id=component_id)
    EventBroadcaster.broadcast(ListItemOpEvent(op="delete", id=id))
    return {"ok": True}


@jrpc_service.request("list.clear")
def list_clear(component_id: str | None = None) -> dict:
    APIListSource.push_clear(component_id=component_id)
    EventBroadcaster.broadcast(ListItemOpEvent(op="clear"))
    return {"ok": True}


@jrpc_service.request("list.highlight")
def list_highlight(id: str, component_id: str | None = None) -> dict:
    ListCommandQueue.push(HighlightListItemCmd(id=id), component_id=component_id)
    return {"ok": True}


@jrpc_service.request("list.list")
def list_list() -> dict:
    return {"items": [{"id": item.id, "label": item.label, "subtitle": item.subtitle} for item in APIListSource._items.values()]}
