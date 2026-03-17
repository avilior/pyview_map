# Service: debate-bff (Chat UI)

## Overview
PyView BFF serving the debate chat UI to the browser via WebSocket/LiveView.
Communicates with the backend (`services/debate_backend` via `packages/server_pkg`)
over JSON-RPC 2.0 / SSE streaming.

## Key Context
- **Python 3.14**, **uv** package manager, **PyCharm Pro** IDE
- **PyView framework** — server-rendered HTML + WebSocket real-time updates (like Phoenix LiveView)
- Part of the `http_stream_prj` monorepo under `services/debate_bff`
- **Backend**: `packages/server_pkg` (FastAPI + JSON-RPC + SSE) loading `services/debate_backend`

## Architecture
- BFF (port 8001) → Backend (port 8000)
- Communication: JSON-RPC 2.0 over HTTP POST `/mcp`, SSE for streaming
- Auth: Bearer token (mock tenant: `tok-acme-001`)
- Client SDK: `http_stream_client` (workspace package at `packages/client`)

### Key Modules
- **`app.py`** — PyView Starlette app, mounts `/` (chat LiveView) and
  `/transcript/{debate_id}` (GET route serving stored transcripts)
- **`transcript_store.py`** — module-level dict storing `(content, format)`
  tuples keyed by debate_id, shared between ChatLiveView and the transcript route
- **`views/chat/chat_view.py`** — ChatLiveView handling user events,
  slash-command dispatch, debate streaming, and transcript storage
- **`services/rpc_client.py`** — async JSON-RPC client wrapper using `http_stream_client`
- **`__main__.py`** — entry point: `debate_bff.__main__:main`

## Commands
```bash
cd services/debate_bff && uv sync          # Install deps
cd services/debate_bff && uv run debate-bff  # Run BFF only
```

From the monorepo root:
```bash
make frontend          # Run BFF (port 8001)
make all               # Run both backend + BFF
make stop              # Stop both services
```

Ports are configurable: `FE_PORT=9001 BE_PORT=9000 make all`