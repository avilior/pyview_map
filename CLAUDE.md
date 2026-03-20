# pyview_map

A uv workspace monorepo with PyView LiveView apps (interactive maps, flight
simulation) and an LLM debate platform, sharing a common MCP streaming
transport layer.

## Architecture

### Shared infrastructure (packages/)

1. **Transport** (`server_pkg`) — FastAPI HTTP router for `/mcp`, SSE streaming, auth, sessions
2. **JSON-RPC** (`server_pkg`) — `JRPCService` dispatch/registry with handler introspection
3. **Client SDK** (`client`) — `ClientRPC` async RPC client
4. **Wire models** (`jrpc_common`) — shared JSON-RPC 2.0 models and audit tracking
5. **BFF Engine** (`bff_engine`) — shared BFF framework: components, drivers, API/app factories
6. **Data Models** (`dmap_models`) — shared wire-protocol models for map/list components

Dependency direction: Services → Packages (never the reverse)

### Service pattern (services/)

Each application is a BE + BFF pair:
- **Backend (BE)** — FastAPI + JSON-RPC handlers, domain logic
- **BFF** — PyView LiveView frontend, connects to BE via `ClientRPC`

## Project layout

```
pyproject.toml               # workspace root (no app code)
uv.lock                     # single unified lock
packages/
├── jrpc_common/             # shared JSON-RPC 2.0 models
├── server_pkg/              # HTTP/SSE transport + JSON-RPC dispatch
├── client/                  # ClientRPC async client SDK
├── dmap_models/             # shared wire-protocol models
└── bff_engine/              # shared BFF engine — components, drivers, API/app factories
    └── src/bff_engine/
        ├── bff_app.py       # create_app() factory — PyView app, StaticFiles, CSS
        ├── bff_api.py       # create_api() factory — FastAPI, MCP router, bff.subscribe
        ├── shared/          # cid.py, event_broadcaster.py, item_store.py, topics.py
        ├── dynamic_map/     # Map LiveComponent + MapDriver + models + sources + api/
        └── dynamic_list/    # List LiveComponent + ListDriver + models + sources + api/
services/
├── flights_bff/             # Flights BFF (port 8123)
├── flights_backend/         # Flights BE (port 8300)
├── places_bff/              # Places BFF (port 8124)
├── places_backend/          # Places/Parks BE (port 8200)
├── debate_backend/          # Debate BE (port 8000)
│   ├── src/debate_backend/
│   │   ├── __main__.py      # Entry point, imports debate modules, runs uvicorn
│   │   ├── debate.py        # Debate model + JSON-RPC handlers
│   │   ├── commands.py      # Slash-command dispatcher
│   │   ├── spec_parser.py   # Markdown spec file parser
│   │   └── engine/          # LangGraph orchestration
│   ├── tests/               # 84 debate tests
│   └── data/                # templates/, debates/, specs/
└── debate_bff/              # Debate BFF (port 8001)
    └── src/debate_bff/
        ├── __main__.py      # uvicorn on port 8001
        ├── app.py
        ├── transcript_store.py
        ├── views/chat/chat_view.py
        └── services/rpc_client.py
docs/
├── specification/           # MCP spec text (reference)
├── langgraph-refactor.md    # LangGraph architecture decisions
├── adr-dialog-implementation.md
├── api-reference.md
└── architecture_bff_be.md
```

## Commands

```bash
just install           # uv sync --all-packages

# Local development
just flights           # Flights BE + BFF, opens browser
just places            # Parks BE + Places BFF, opens browser
just debate            # Debate BE + BFF, opens browser
just all               # All 6 services, opens all demos
just stop-all          # Stop everything

# Testing
just test              # All tests (transport + debate + client)
just test-transport    # Transport tests (packages/server_pkg) — 80 tests
just test-debate       # Debate tests (services/debate_backend) — 84 tests
just test-client       # Client tests (packages/client)

# Docker
just docker-build      # Build all images
just docker-up         # Start all in Docker
just docker-places     # Start only places in Docker
just docker-flights    # Start only flights in Docker
just docker-debate     # Start only debate in Docker

# Release (GHCR)
just release-build     # Build multi-arch images + push to ghcr.io
just release-up        # Pull + start from registry
just release-list      # Show local release images

# Deploy
just deploy user@host [dest]   # scp compose + justfile to remote
```

Ports are configurable via env vars: `FLIGHTS_BFF_PORT`, `PLACES_BFF_PORT`,
`PLACES_PORT`, `FLIGHTS_PORT`, `BE_PORT`, `FE_PORT`.

## Dependencies

Managed with `uv` workspaces. All inter-package deps use `{ workspace = true }`.

- `uv sync --all-packages` — install everything
- `cd packages/server_pkg && uv sync --group dev` — install server deps
- `cd services/debate_backend && uv sync --group dev` — install debate deps

## Adding a new application

1. Create a new BFF service: `services/<name>_bff/` with `pyproject.toml` and `src/<name>_bff/`.
2. Add `bff-engine` as a dependency in `pyproject.toml`.
3. In `__main__.py`:
   - Import the component API modules you need (e.g. `import bff_engine.dynamic_map.api.marker_api`)
   - Call `create_app(static_packages=[...], extra_head_html=...)` with the component packages
   - Call `create_api(title=..., description=...)` to create the FastAPI sub-app
   - Register your live view and mount the API
4. Create your view file importing drivers from `bff_engine.dynamic_map` / `bff_engine.dynamic_list`.
5. Create a `settings.py` with your own env prefix.
6. Add a `Dockerfile` following the pattern in existing BFFs.

## Architecture Decision Records

For architecture-type decisions (evaluating multiple approaches, choosing patterns, making trade-offs), create an ADR in `docs/adr-<topic>.md` to capture the context, analysis, and decision. An ADR should include: Status, Date, Context (the problem), Decision (chosen approach with details and code examples), alternatives considered, and Consequences. See `docs/adr-dialog-implementation.md` as a reference.

## Key conventions

- **Context** — each view defines a `@dataclass` context passed to `LiveViewSocket[T]`.
- **Client → server** — `phx-click` / `phx-value-*` in template → `handle_event()`.
- **Server → client** — `await socket.push_event("event-name", payload)`.
- **Map DOM stability** — wrap Leaflet `div` in `phx-update="ignore"`.
- **Ibis limits** — no subscript syntax (`obj[0]`); use properties or filters.
- **t-string templates** — components and app views use t-strings with `TemplateView` mixin + `live_component()` / `stream_for()`.

## Driver pattern

`MapDriver` and `ListDriver` encapsulate all parent-side plumbing. 6 methods:

```python
from bff_engine.dynamic_map import MapDriver
from bff_engine.dynamic_list import ListDriver

class MyPageView(TemplateView, LiveView[MyContext]):
    async def mount(self, socket, session):
        self._map = MapDriver("my-map")
        self._list = ListDriver("my-list")
        socket.context = MyContext()
        if socket.connected:
            await self._map.connect(socket)
            await self._list.connect(socket)

    async def handle_info(self, event, socket):
        if await self._map.handle_info(event, socket): return
        if await self._list.handle_info(event, socket): return

    async def handle_event(self, event, payload, socket):
        self._map.clear_ops()
        self._list.clear_ops()
        summary = self._map.handle_event(event, payload) or self._list.handle_event(event, payload)

    async def disconnect(self, socket):
        self._map.disconnect()     # clears retained events
        self._list.disconnect()

    def template(self, assigns, meta):
        return t'<div>{self._map.render()}{self._list.render()}</div>'
```

Each driver auto-generates a unique `cid` via `next_cid()`.

## Readiness gating and retained events

BFF gates BE subscription on component readiness. Views track `_list_ready` / `_map_ready` flags set by `handle_event("list-ready"/"map-ready")` and only subscribe to BEs when all required components are ready.

`EventBroadcaster` supports retained events (like MQTT): ready events implement `retained_key()` and are replayed to late subscribers. Cleared on `driver.disconnect()`.

Both apps use Scheme A (single multiplexed `bff.subscribe` channel). Startup order doesn't matter.

## Streaming live updates with `Stream`

```python
# t-string template (LiveComponent):
items_html = stream_for(assigns.items, lambda dom_id, item:
    t'<div id="{dom_id}" phx-hook="ItemHook">{item.name}</div>')
return t'<div id="items" phx-update="stream">{items_html}</div>'

# Mutations (server side):
socket.context.items.insert(new_item)                # append
socket.context.items.insert(item, update_only=True)  # update
socket.context.items.delete_by_id("items-<id>")      # remove
```

## Data flow

1. API handler stores item in `ItemStore`, broadcasts op via `pub_sub_hub`
2. PubSub delivers to subscribed sockets → `handle_info(InfoEvent(topic, op))`
3. Driver stores op, bumps `ops_version`; commands go straight to `push_event()`
4. Component `update()` applies ops to Streams; re-renders with diffs

PubSub topics: `{prefix}:{channel}` (broadcast) or `{prefix}:{channel}:{cid}` (targeted).
Server-to-client commands namespaced: `to_push_event(target=channel)` → `"left:setView"`.

## Icon registry

The map component uses a pluggable icon registry to resolve marker icon names
to Leaflet `DivIcon` definitions. Icons can be built-in (shipped with
`bff_engine`), loaded from a custom JSON file, or added/removed at runtime via
JSON-RPC.

### Icon definition schema

Each icon is a JSON object keyed by name:

```json
{
  "my-icon": {
    "html": "<div style=\"...\">...</div>",
    "iconSize": [24, 24],
    "iconAnchor": [12, 12],
    "className": ""
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `html` | `string` | HTML content rendered inside the Leaflet `DivIcon` |
| `iconSize` | `[width, height]` | Size in pixels |
| `iconAnchor` | `[x, y]` | Anchor point relative to top-left corner |
| `className` | `string` | Optional CSS class applied to the icon container |

### Resolution order

When `_makeIcon(instance, iconName, heading)` runs in the browser:

1. Look up `iconName` in the icon registry
2. If not found and `iconName` is not `"default"` — treat `iconName` as **literal
   content** (emoji, SVG, HTML) and wrap in a centered container
3. If not found and `iconName` is `"default"` — use the `"default"` registry
   entry, falling back to a hardcoded blue dot

### Built-in icons

Defined in `packages/bff_engine/src/bff_engine/dynamic_map/icons.json`:
`default`, `red-dot`, `green-dot`, `black-dot`, `black-square`, `warning`,
`vehicle`, `airplane`.

Built-in icons **cannot** be overwritten or removed at runtime.

### Configurable icon file

Call `configure(path)` from `bff_engine.dynamic_map.icon_registry` to load a
custom JSON file. The built-in icons are loaded first, then the custom file is
merged on top — so custom files can add new icons or override built-in
definitions at load time (but not at runtime via the API).

### JSON-RPC API (`icons.*`)

| Method | Params | Description |
|--------|--------|-------------|
| `icons.add` | `name, html, iconSize, iconAnchor, className?` | Register a new icon. Rejects if name already exists (built-in or dynamic) |
| `icons.remove` | `name` | Remove a dynamic icon. Built-in icons cannot be removed |
| `icons.list` | *(none)* | Return all icon names and definitions |

To replace a dynamic icon: call `icons.remove` then `icons.add`.

After `icons.add` or `icons.remove`, the full registry JSON is broadcast to all
connected MapDrivers via the global `icon-cmd` PubSub topic. Each driver pushes
an `updateIconRegistry` event to the browser, which replaces the in-memory
registry so subsequent marker renders use the updated icons.

### Key files

| File | Role |
|------|------|
| `dynamic_map/icons.json` | Built-in icon definitions |
| `dynamic_map/icon_registry.py` | `IconRegistry` class, global `icon_registry`, `configure()` |
| `dynamic_map/api/icon_api.py` | `icons.add/remove/list` JSON-RPC handlers |
| `dynamic_map/models/icon_commands.py` | `UpdateIconRegistryCmd` dataclass |
| `dynamic_map/static/dynamic_map.js` | `_makeIcon()` + `updateIconRegistry` event handler |
| `shared/topics.py` | `icon_cmd_topic()` — global PubSub topic |

## Spec compliance (MCP transport)

The server enforces MCP streaming spec rules:
- Spec §2: POST requests must include `Accept: application/json, text/event-stream`
- Spec §3: Batches must not mix responses with requests/notifications
- Spec §4: Notification/response-only payloads return 202
- Spec §5-6: Requests return SSE or JSON at the server's discretion

The spec source is in `docs/specification/streamable_http_transport`.

## Testing

Tests use `starlette.testclient.TestClient` (in-process, no running server).

- `packages/server_pkg/tests/` — transport tests (80 tests)
- `services/debate_backend/tests/` — debate tests (84 tests)

## Linting & Type Checking

- `ruff check` — lint (from repo root)
- `cd packages/server_pkg && uv run ty check` — type check with ty

## Ruff & Python 3.14

Ruff 0.15+ supports t-string syntax (PEP 750) — no file exclusions needed.

## JSON-RPC API

Endpoint: `POST /api/mcp` (mounted in `__main__.py` via `app.mount("/api", api_app)`).

Full API reference with method tables, event types, channel/cid routing, and usage examples: **`docs/api-reference.md`**

## Important pitfalls

- **Hook init ordering** — `DMarkItem.mounted()` can fire before `DynamicMap.mounted()`. Hooks queue in `pendingMarkers`/`pendingPolylines`; flushed after Leaflet map created.
- **Follow-marker vs panTo** — Use `map.followMarker` for continuous tracking. Do NOT use `map.panTo` for continuous tracking (browser compositor issue).
- **LatLng conversion** — Internal: `LatLng` dataclass. Wire: `[lat, lng]` arrays. Convert at boundaries with `.to_list()` / `LatLng.from_list()`.

---

## Debate Application

The debate app (`services/debate_backend/`) lets N LLM agents debate a topic
with a user as moderator. Orchestration is handled by a LangGraph graph.

### Key modules

- **`debate.py`** — `Debate` domain model + `DebateEngine` wrapper, in-memory
  store (`_engines`), JSON-RPC handlers:
  `debate.start`, `debate.next_turn`, `debate.inject`, `debate.announce`,
  `debate.status`, `debate.stop`
- **`engine/`** — LangGraph orchestration layer:
  - `state.py` — `DebateState` TypedDict (routing state only; includes `main_flow_speaker`)
  - `models.py` — `TemplateConfig`, `RouterConfig`, `EvaluatorConfig` (Pydantic);
    `AgentConfig.server_url: str` is required with no default
  - `llm_factory.py` — `create_llm(model_string, server_url)` → LangChain `BaseChatModel`;
    exports `OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"` (used as fallback
    only when loading old saves that lack `server_url`)
  - `routers/` — `Router` protocol + `RoundRobinRouter`
  - `graphs/debate_graph.py` — builds the compiled LangGraph; LLM errors surface
    as `[LLM Error @ {server_url} — ExcType: message]` in the agent bubble
- **`commands.py`** — slash-command dispatcher (`debate.command` RPC method),
  file I/O for YAML templates, JSON saves, spec files, transcript generation
- **`spec_parser.py`** — `parse_spec_file(path) -> SpecData`; parses `# Topic`,
  `# Max Rounds`, `# Background`, `# Agent Guidelines` / `## AgentName` sections

### Model string format

```
"llama3.2"                  → Ollama llama3.2  (bare name defaults to ollama)
"ollama:llama3.2"           → Ollama llama3.2
"openai:gpt-4o"             → OpenAI gpt-4o
"anthropic:claude-opus-4-6" → Anthropic claude-opus-4-6
```

### Slash Commands

| Command | Description |
|---|---|
| `/new -t <template> -o <filename> [-s <spec>] [<topic>]` | Start a new debate from a template; `-s` loads topic/background/guidelines from a spec file |
| `/save` | Save the current debate |
| `/save-as <filename>` | Save with a specific name |
| `/load <filename>` | Load and resume a saved debate |
| `/continue [N]` | Run N full rounds (default 1, max 20) |
| `/end` | End the current debate and save it |
| `/templates` | List available debate templates |
| `/template <name>` | Show the raw YAML contents of a debate template |
| `/specs` | List available debate spec files |
| `/spec <filename>` | Show the raw markdown contents of a spec file |
| `/debates` | List saved debates |
| `/debate <filename>` | Show topic, agents, status, and full turn history of a saved debate |
| `/transcript [-html] [-i <filename>]` | Open transcript in a new tab |
| `/help` | Show available commands |
| `/config` | Show server configuration |

### Moderator Features

- **System prompt awareness** — `build_messages()` auto-appends a moderator
  clause so agents know to follow moderator instructions (injected at LLM-call
  time, not stored on the agent).
- **`@Agent` targeting** — prefix a message with `@AgentName` to start a side
  conversation with that specific agent (only that agent responds). The main
  debate position is saved in LangGraph state (`main_flow_speaker`). A
  **"Resume Debate"** button appears and resumes from exactly where the main
  debate paused.
- **Next Turn is always manual** — untagged moderator messages are recorded via
  `debate.announce()` (no auto-response). The user always clicks "Next Turn" to
  advance the main debate. Only `@Agent`-targeted messages trigger an immediate
  response.
- **Auto-opening** — after `/new`, the frontend auto-generates a moderator
  opening announcement, shows it as a Moderator bubble, and calls
  `debate.announce` to persist it in backend history. If a spec file was used,
  the opening mentions it.
- **`/continue N`** — runs N full rounds automatically (frontend chains
  `debate_continue` events recursively).
- **`<think>` stripping** — `strip_think` flag (default `True`). Blocks are
  stripped from LLM input but preserved in history for transcripts.

### Debate Spec Files

Spec files (`data/specs/*.md`) define a debate's topic, background, and
per-agent guidelines in a simple Markdown format:

```markdown
# Topic
Should AI replace humans in the workplace?

# Background
Recent advances in AI...

# Agent Guidelines
## Agent Alpha
Argue strongly in favor of AI replacing humans...
## Agent Beta
Argue against AI replacing humans...
```

- Parsed by `spec_parser.py` → `SpecData(topic, background, agent_guidelines, max_rounds)`
- Used via `/new -t <template> -o <filename> -s <spec>` (topic from spec if no
  positional topic given; positional arg overrides spec topic)
- `Debate` stores `spec_file`, `background_info`, `agent_instructions`,
  `max_rounds`; injected into agent system prompts by `build_messages()` and
  persisted in saved JSON
- `max_rounds` lives in the spec file (`# Max Rounds` section), not in
  templates. `None` means no limit. When the router detects the round cap,
  `run_turn()` checks `get_state().values["next_action"] == "end"` after
  `ainvoke`, calls `debate.stop()`, and returns `debate_ended: True` to the
  frontend, which disables the Next Turn button and shows an amber badge.
- `data/specs/ai_workplace.md` — example spec file
- Path: `settings.debate_specs_dir`

### Per-Agent `server_url`

Every agent in a template YAML **must** have an explicit `server_url`:

```yaml
agents:
  - name: "Advocate"
    model: "llama3.2"
    server_url: "http://localhost:11434"
```

`server_url` has no default. `OLLAMA_DEFAULT_BASE_URL` in `llm_factory.py` is
used only as a fallback when loading old saves that predate this field.
Cloud providers (OpenAI, Anthropic) only receive `server_url` when it differs
from the Ollama default (prevents localhost being forwarded to cloud APIs).

### Side Conversations + Resume

When the moderator uses `@Agent`, a side conversation starts:

- `RoundRobinRouter` saves the next main-debate speaker as `main_flow_speaker`
  in LangGraph state on the first targeted turn; subsequent targeted turns
  leave it unchanged
- `ChatContext.in_side_conversation: bool` is set True after a targeted inject;
  cleared when "Resume Debate" or "Next Turn" is clicked
- The "Resume Debate" button (purple) replaces "Next Turn" (green) while in a
  side conversation — both buttons are always in the DOM, toggled via Tailwind
  `hidden` class to avoid Phoenix LiveView diff mismatches
- `ctx.current_agent` is preserved across targeted injects so the Resume button
  correctly shows the main-flow speaker, not the post-side-convo rotation agent
- On Resume: router uses `main_flow_speaker`, clears it, and debate continues
  from exactly the right position

### Frontend — ChatContext fields

`ChatContext` has application-populated generic fields so the template stays
debate-agnostic:

- `session_title: str` — shown as header subtitle (set to debate topic)
- `status_bar: list[dict]` — `[{"label": str, "value": str}]` strip; built by
  `_update_status_bar()`: shows Template, Spec (if any), Round X/N or X
- `agent_turn_count: int` — incremented per agent placeholder; embedded in
  bubble labels as `"Agent Alpha · 3"`; seeded from history on `/load`
- `in_side_conversation: bool` — True while a side conversation is active;
  controls Resume Debate vs Next Turn button visibility
- `debate_ended: bool` — True when max_rounds reached or debate stopped;
  disables Next Turn/Resume buttons, shows amber "Debate complete" badge
- `debate_max_rounds: int | None` — used in status bar Round display (`X / N`)
- `debate_template: str` — template name shown in status bar
- `debate_spec_file: str` — spec filename shown in status bar (empty if none)

### Transcript Format

- **Markdown** (default) — rendered in a `<pre>` tag
- **HTML** (`-html` flag) — styled HTML with agent cards and turn blocks

Backend returns `{"content": "...", "format": "markdown"|"html"}`.
Frontend stores tuples in `transcript_store`; `/transcript/{debate_id}` renders.

### Data Directories

- `data/templates/` — YAML debate templates
- `data/debates/` — saved debate JSON files
- `data/specs/` — Markdown debate spec files

Paths: `settings.debate_templates_dir`, `settings.debate_saves_dir`,
`settings.debate_specs_dir`.

### LangGraph design notes

See `docs/langgraph-refactor.md` for full architecture decisions, phase plan,
and next-session starting points (Phase 3: evaluator node).

### PyView / LiveView template notes

- **Avoid swapping elements in conditionals** — when a `{% if %}` replaces one
  element with a different element (e.g. two different `<button>` tags), the
  Phoenix LiveView JS diff algorithm can misread dynamic-value indices, causing
  JavaScript `undefined` to appear in the rendered text. Instead, always render
  both elements and toggle visibility with Tailwind's `hidden` class.
