# Implementation Plan: Chat Frontend + Debate Agents

## Context

We need to build a chat-like frontend UI using PyView and a backend application layer for an LLM debate feature. The frontend communicates with the backend via JSON-RPC over HTTP (MCP streaming protocol). The backend's transport and JRPC layers already exist in `http_stream_prj`; we only need to build the application layer on top.

The MVP is two LLM Chat Agents debating each other, with the user acting as moderator, using Ollama for local LLM inference.

---

## Phase 1: Project Setup & Basic PyView App

### 1.1 Update `pyproject.toml` and install dependencies

**File:** `packages/frontend/pyproject.toml`

- Add dependencies: `pyview-web`, `uvicorn[standard]`, `httpx`
- Add path dependencies to sibling packages:
  - `http_stream_client` → `../client`
  - `jrpc_common` → `../jrpc_common`
- Run `uv sync`

### 1.2 Create project structure

```
packages/frontend/
├── pyproject.toml
└── src/
    └── front_end/
        ├── __init__.py
        ├── app.py                 # Starlette app + PyView setup + routes
        ├── views/
        │   ├── __init__.py
        │   └── chat/
        │       ├── __init__.py
        │       ├── chat_view.py   # ChatLiveView class
        │       └── chat_view.html # Jinja2 template
        ├── services/
        │   ├── __init__.py
        │   └── rpc_client.py      # Thin wrapper around ClientRPC
        ├── templates/
        │   └── root.html          # Base HTML layout
        └── static/
            └── css/
                └── styles.css     # Chat styling
```

### 1.3 Get minimal PyView app running

- Create `app.py` with Starlette app, mount PyView, register `/` route to `ChatLiveView`
- Create a stub `ChatLiveView` with mount/render displaying "Hello PyView"
- Create `root.html` base template (includes PyView JS client)
- Run: `uv run uvicorn src.front_end.app:app --reload --port 8001`
- Verify it loads in browser at `http://localhost:8001`

---

## Phase 2: Application-Agnostic Chat UI

### 2.1 Chat data model

In `chat_view.py`, define:
- `ChatMessage` dataclass: `id`, `role` (user/agent/system), `sender_name`, `content`, `timestamp`, `is_streaming`
- Chat context: `messages` (PyView Stream for efficient delta rendering), `input_text`, `is_connected`, `session_id`, `status`

### 2.2 ChatLiveView lifecycle

**File:** `src/front_end/views/chat/chat_view.py`

- `mount()` — initialize empty message list, connection status
- `handle_event("send_message")` — capture user input, add user message to stream, clear input, trigger backend call via background task
- `handle_event("update_input")` — track input field changes
- `handle_info("token")` — receive streaming tokens from background task, update in-progress agent message in stream
- `handle_info("stream_complete")` — mark agent message as complete

### 2.3 Chat template

**File:** `src/front_end/views/chat/chat_view.html`

- Message list with `phx-update="stream"` for efficient rendering
- Role-based styling (user messages right-aligned, agent messages left-aligned)
- Input form with `phx-submit="send_message"`
- Connection status indicator
- Streaming indicator (typing animation while `is_streaming=True`)

### 2.4 Verify streaming works locally

Before backend integration, test with a fake async generator that simulates token streaming via `handle_info` / `send_info`. This de-risks the PyView streaming mechanism early.

---

## Phase 3: Frontend-Backend Integration

### 3.1 RPC client service

**File:** `src/front_end/services/rpc_client.py`

Thin wrapper around the existing `ClientRPC` from `http_stream_client`:
- `connect()` — create `ClientRPC`, call `start()` (health + initialize + initialized)
- `send_request(method, params)` → `AsyncGenerator[JSONRPCMessage]` — send JSON-RPC request, yield SSE notifications and final response
- `disconnect()` — close the client
- Defaults: `base_url=http://localhost:8000`, `auth_token=tok-acme-001`

### 3.2 Wire into ChatLiveView

- On `mount()`, create `ChatRPCClient`, connect to backend, store session ID in context
- On `handle_event("send_message")`, spawn background asyncio task that:
  1. Calls `rpc_client.send_request()` with the user's message
  2. For each `JSONRPCNotification` (streaming token), calls `socket.send_info()` to push to UI
  3. On `JSONRPCResponse`, calls `socket.send_info()` to mark complete

### 3.3 Test with existing backend methods

- Test with `echo` method (simple request/response)
- Test with `streaming` method (SSE notifications + response)
- Verify tokens appear in chat UI in real-time

---

## Phase 4: Backend Application Layer — Debate Agents

### 4.1 Debate state model

**New file:** `packages/server_pkg/http_stream_transport/application/debate.py`

- `DebateAgent` dataclass: `name`, `model` (Ollama model), `system_prompt`
- `DebateState` dataclass: `debate_id`, `topic`, `agents` (2), `history`, `current_turn`, `status`
- In-memory store: `dict[str, DebateState]`

### 4.2 Ollama client

**New file:** `packages/server_pkg/http_stream_transport/application/ollama_client.py`

- `ollama_chat_stream(model, messages)` → `AsyncGenerator[str]`
- Uses httpx to stream from `http://localhost:11434/api/chat`
- Yields tokens as they arrive

### 4.3 JSON-RPC methods

All registered via `@jrpc_service.request(...)` in `debate.py`:

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `debate.start` | `topic`, `agent1_model`, `agent2_model` | debate config | Start new debate |
| `debate.next_turn` | `debate_id` | SSEQueue (streaming) | Trigger next agent's turn, stream tokens |
| `debate.inject` | `debate_id`, `message` | SSEQueue (streaming) | Moderator injects a prompt |
| `debate.status` | `debate_id` | state summary | Get current debate state |
| `debate.stop` | `debate_id` | confirmation | End the debate |

Streaming methods follow the existing pattern in `methods.py`:
- Return `SSEQueue`
- Background task puts `JSONRPCNotification` (tokens) then final `JSONRPCResponse`

### 4.4 Register handlers

**Modify:** `packages/server_pkg/http_stream_transport/application/__init__.py`

- Add import of `debate` module so handlers are registered at server startup

**Modify:** `packages/server_pkg/pyproject.toml`

- Add `httpx` to dependencies (for Ollama client)

### 4.5 Debate prompt construction

For each agent's turn, build Ollama chat messages from history:
- Agent sees its own past messages as `"assistant"` role
- Agent sees opponent's messages as `"user"` role
- Moderator injections appear as `"user"` role
- System prompt sets the debate context and agent personality

---

## Phase 5: End-to-End Integration & Testing

### 5.1 Development workflow

Run three processes:
1. **Ollama:** `ollama serve` (port 11434) + `ollama pull llama3.2`
2. **Backend:** `make server` (port 8000)
3. **Frontend:** `make frontend` (port 8001)
Or run both: `make all`

### 5.2 Testing

- **Backend unit tests:** Test debate handlers with mocked Ollama responses in `http_stream_prj/packages/server_pkg/tests/test_debate.py`
- **Frontend manual testing:** Interact via browser at `http://localhost:8001`
- **Integration:** Full flow — start debate, trigger turns, inject moderator prompts, see streaming responses

### 5.3 Key risks and mitigations

| Risk | Mitigation |
|------|------------|
| PyView `handle_info`/`send_info` may not work from background tasks | Test early in Phase 2 with a fake timer before building full integration |
| SSE streaming may stall/timeout | httpx `timeout=None` on client; keep Ollama model small for dev |
| Path dependency on http_stream_client creates coupling | Accept for MVP; refactor when frontend joins mono repo |

---

## Critical files summary

| File | Action |
|------|--------|
| `packages/frontend/pyproject.toml` | Modify — add dependencies |
| `packages/frontend/src/front_end/app.py` | Create — Starlette + PyView app |
| `packages/frontend/src/front_end/views/chat/chat_view.py` | Create — ChatLiveView |
| `packages/frontend/src/front_end/views/chat/chat_view.html` | Create — chat template |
| `packages/frontend/src/front_end/services/rpc_client.py` | Create — RPC client wrapper |
| `packages/frontend/src/front_end/templates/root.html` | Create — base HTML layout |
| `packages/frontend/src/front_end/static/css/styles.css` | Create — chat styling |
| `packages/server_pkg/.../application/debate.py` | Create — debate handlers + state |
| `packages/server_pkg/.../application/ollama_client.py` | Create — Ollama streaming client |
| `packages/server_pkg/.../application/__init__.py` | Modify — register debate handlers |
| `packages/server_pkg/.../pyproject.toml` | Modify — add httpx dependency |
