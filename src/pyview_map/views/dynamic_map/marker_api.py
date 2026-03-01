import asyncio

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router

from pyview_map.views.dynamic_map.api_marker_source import APIMarkerSource
from pyview_map.views.dynamic_map.event_broadcaster import EventBroadcaster
from pyview_map.views.dynamic_map.map_events import MarkerOpEvent


# -- Register marker methods on the global JRPCService instance -----------

@jrpc_service.request("markers.add")
def markers_add(id: str, name: str, latLng: list[float]) -> dict:
    APIMarkerSource.push_add(id, name, latLng)
    EventBroadcaster.broadcast(MarkerOpEvent(op="add", id=id, name=name, latLng=latLng))
    return {"ok": True}


@jrpc_service.request("markers.update")
def markers_update(id: str, name: str, latLng: list[float]) -> dict:
    APIMarkerSource.push_update(id, name, latLng)
    EventBroadcaster.broadcast(MarkerOpEvent(op="update", id=id, name=name, latLng=latLng))
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


# -- FastAPI sub-app mounted at /api in __main__.py -----------------------

api_app = FastAPI(title="dmap Marker API")
api_app.include_router(mcp_router)


@api_app.get("/health")
async def health():
    return {"status": "ok"}
