"""FastAPI sub-app factory — MCP router, health, and cross-cutting subscriptions.

Importing this module registers ``bff.subscribe`` on ``jrpc_service``.
Callers must import component API modules **before** calling ``create_api()``
so that all JRPC methods are registered before OpenRPC docs are generated.
"""

import asyncio

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router
from http_stream_transport.jsonrpc.openrpc import setup_rpc_docs

from bff_engine.shared.event_broadcaster import EventBroadcaster


# -- Cross-cutting subscriptions (registered at import time) ------------------

@jrpc_service.request("bff.subscribe")
async def bff_subscribe() -> asyncio.Queue:
    return EventBroadcaster.subscribe()


# -- Factory ------------------------------------------------------------------

def create_api(
    title: str = "dmap BFF",
    description: str = "PyView LiveView map demo",
) -> FastAPI:
    """Create a FastAPI sub-app with MCP router, OpenRPC docs, and health."""
    api_app = FastAPI(title=title, docs_url=None, redoc_url=None)
    api_app.include_router(mcp_router)

    setup_rpc_docs(
        api_app,
        jrpc_service,
        title=title,
        description=description,
    )

    @api_app.get("/health")
    async def health():
        return {"status": "ok"}

    return api_app
