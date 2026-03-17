# Agent Client Protocol (ACP) Research

## What It Is
- Standardized protocol for communication between code editors (clients) and AI agents
- Built on **JSON-RPC 2.0**
- Designed for interoperability — any editor can connect with any agent
- Language agnostic (SDKs in Python, TypeScript, Rust, Kotlin, Go)
- Website: https://agentclientprotocol.com

## Message Types (JSON-RPC 2.0)

**Requests** (expects response):
```json
{"jsonrpc": "2.0", "id": 1, "method": "method_name", "params": {...}}
```

**Responses**:
```json
{"jsonrpc": "2.0", "id": 1, "result": {...}}
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "..."}}
```

**Notifications** (no response expected, no id):
```json
{"jsonrpc": "2.0", "method": "method_name", "params": {...}}
```

## Interaction Flow

### Initialization
1. Client sends `initialize` request (protocol version, capabilities)
2. Server responds with its capabilities and session ID
3. Client sends `notifications/initialized` notification

### Session
- `session/new` — create session
- `session/prompt` — send prompt to agent
- `session/update` — agent streams real-time updates (notifications)
- `session/cancel` — cancel ongoing processing

### Streaming
- Agent sends multiple `session/update` notifications during processing
- Notifications contain token chunks, tool calls, thoughts, etc.
- Final response terminates the stream
- Client must accept updates even after sending cancel

## Python SDK
- Package: `agent-client-protocol` on PyPI
- `acp.schema` — Pydantic models
- `acp.agent` — async base class for agents
- `acp.client` — async base class for clients
- Uses asyncio + stdio transport
- Repo: https://github.com/agentclientprotocol/python-sdk

## Note
The http_stream_prj backend implements a subset/adaptation of this protocol using HTTP+SSE transport rather than stdio. The JSON-RPC message format is the same.
