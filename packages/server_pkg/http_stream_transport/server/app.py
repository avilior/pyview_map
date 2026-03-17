import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router

LOG = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    LOG.info("Registered JSON-RPC Requests and Notifications:")
    for name, rec in jrpc_service.registered_methods().items():
        LOG.info(f"  {name}:")
        LOG.info(f"    kind:          {rec.kind}")
        LOG.info(f"    async:         {rec.is_async}")
        LOG.info(f"    module:        {rec.module}")
        LOG.info(f"    qualname:      {rec.qualname}")
        LOG.info(f"    docstring:     {rec.docstring}")
        LOG.info(f"    param_schema:  {rec.param_schema}")
        LOG.info(f"    return_schema: {rec.return_schema}")

    yield


app = FastAPI(
    title="MCP Streamable HTTP Transport",
    description="FastAPI server implementing the MCP streaming spec (2025-03-26).",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(mcp_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
