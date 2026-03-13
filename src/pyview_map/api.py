"""App-level API: FastAPI sub-app, MCP router, health, and cross-cutting subscriptions.

Importing this module triggers JRPC method registration for all components.
"""

import asyncio

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router

from pyview_map.components.shared.event_broadcaster import EventBroadcaster

# Import component API modules to register their JRPC methods on jrpc_service
import pyview_map.components.dynamic_map.api.marker_api  # noqa: F401
import pyview_map.components.dynamic_map.api.polyline_api  # noqa: F401
import pyview_map.components.dynamic_map.api.map_cmd_api  # noqa: F401
import pyview_map.components.dynamic_list.api.list_api  # noqa: F401


# -- Cross-cutting subscriptions ---------------------------------------------

@jrpc_service.request("bff.subscribe")
async def bff_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()


# -- FastAPI sub-app mounted at /api in __main__.py ---------------------------

api_app = FastAPI(title="dmap Marker API")
api_app.include_router(mcp_router)


@api_app.get("/health")
async def health():
    return {"status": "ok"}
