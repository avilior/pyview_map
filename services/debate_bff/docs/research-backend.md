# Backend (http_stream_prj) Research

## Overview
Mono repo implementing MCP Streamable HTTP Transport — FastAPI server and client with JSON-RPC over HTTP + SSE.

**Repo:** https://github.com/avilior/http_stream_prj
**Local path:** `/Users/avilior/developer/python/http_stream_prj`

## Structure
```
http_stream_prj/
├── pyproject.toml          # uv workspace root
├── Makefile                # make server, make frontend, make all, make test
├── CLAUDE.md
├── specification/          # MCP lifecycle + transport specs
└── packages/
    ├── jrpc_common/        # Shared JSON-RPC 2.0 Pydantic models
    ├── server_pkg/         # http_stream_transport (FastAPI server)
    ├── client/             # http_stream_client (httpx-based client SDK)
    └── frontend/           # front-end (PyView chat UI)
```

## Packages

### jrpc_common
- `JSONRPCRequest`, `JSONRPCResponse`, `JSONRPCNotification`, `JSONRPCErrorResponse`
- `parse_jsonrpc()` — smart parser
- `JrpcAudit` — request/response lifecycle tracking
- Depends on: Pydantic 2+

### server_pkg (http_stream_transport)
**Transport layer:**
- FastAPI app with `POST /mcp` endpoint
- Handles JSON-RPC requests, notifications, responses
- SSE streaming via `StreamingResponse`
- Session management (in-memory, UUID-based)
- Accept header validation (must include `application/json, text/event-stream`)

**JRPC layer (`jsonrpc/jrpc_service.py`):**
- `JRPCService` — registry-based dispatcher
- Decorators: `@jrpc_service.request("method")`, `@jrpc_service.notification("method")`
- `RequestContext` — holds tenant + session
- `SSEQueue = asyncio.Queue[JSONRPCNotification | JSONRPCResponse | JSONRPCErrorResponse]`
- Built-in handlers: `initialize`, `notifications/initialized`
- Handler signatures: `async fn(info: RequestInfo, param1: type, ...) -> dict | SSEQueue`

**Application layer:**
- `mock_tenant.py` — Bearer token tenants (tok-acme-001 → Acme Corp, tok-globex-002 → Globex Inc, tok-initech-003 → Initech LLC)
- `methods.py` — example handlers: `echo` (simple), `streaming` (SSE with queue)
- `calculator.py` — exists (not examined in detail)

### client (http_stream_client)
- `ClientRPC` — async context manager for one MCP session
- `start()` → health check + initialize + initialized notification
- `send_request()` → `AsyncGenerator[JSONRPCMessage]` (handles SSE + JSON responses)
- `send_notification()` → expects 202
- `BearerAuth` for httpx
- Auto-manages `Mcp-Session-Id` header

## How to Add Application Methods

In `packages/server_pkg/http_stream_transport/application/methods.py` (or new file):

```python
from http_stream_transport.jsonrpc.jrpc_service import jrpc_service, SSEQueue
from http_stream_transport.jsonrpc.handler_meta import RequestInfo

# Simple request
@jrpc_service.request("my_method")
async def my_method(**kwargs) -> dict:
    return kwargs

# Streaming request
@jrpc_service.request("my_streaming")
async def my_streaming(info: RequestInfo, count: int = 3) -> SSEQueue:
    queue: SSEQueue = asyncio.Queue()
    async def _produce():
        for i in range(count):
            await queue.put(JSONRPCNotification(
                method="notifications/my_streaming",
                params={"requestId": info.id, "sequence": i}
            ))
        await queue.put(JSONRPCResponse(id=info.id, result={"done": True}))
    asyncio.create_task(_produce())
    return queue
```

## Build & Run
```bash
make server           # Start server on port 8000
make client           # Run demo client
make test             # Run server tests (pytest)
```

## Dependencies
- Server: FastAPI, Uvicorn, Pydantic Settings, jrpc_common
- Client: httpx, jrpc_common
- All: Python >=3.14, Hatchling build system
