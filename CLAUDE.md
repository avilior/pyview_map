# pyview_map

A PyView LiveView demo app showing interactive Leaflet.js maps.

**Claude Code memory**: `~/.claude/projects/-Users-avilior-developer-python-pyview-map/memory/MEMORY.md`

## Running

```bash
uv run pyview-map        # BFF on :8123
just all                 # Both BEs + BFF, opens browser
just places              # Parks BE + BFF
just flights             # Flights BE + BFF
```

Routes: `/flights` (flight simulation), `/places_demo` (places list + map)

### Release (GHCR)

```bash
just release-build       # Build multi-arch images + push to ghcr.io
just release-up          # Pull + start from registry
just release-down        # Stop release services
just release-logs        # Tail release logs
```

Images are built for `linux/amd64` + `linux/arm64` and pushed to `ghcr.io/avilior/pyview-map-{bff,places-backend,flights-backend}` with `:latest` + `:` tags.

Requires `GITHUB_USER` and `GITHUB_TOKEN` (PAT with `read:packages` + `write:packages`) in `.env`. See `.env.example`.

Deploy compose file: `docker-compose.release.yml` (pull-only, no build context). Use `IMAGE_TAG=<sha>` to pin a specific version.

## Project layout

```
src/pyview_map/
├── __main__.py          # Entry point — route registration + uvicorn
├── app.py               # PyView app, StaticFiles, root template
├── api.py               # FastAPI sub-app, MCP router, bff.subscribe
├── openrpc.py           # OpenRPC spec generator + /docs, /openrpc.json
├── components/
│   ├── shared/          # cid.py, latlng.py, event_broadcaster.py, item_store.py, topics.py
│   ├── dynamic_map/     # Map LiveComponent + MapDriver + models + sources + api/
│   └── dynamic_list/    # List LiveComponent + ListDriver + models + sources + api/
├── applications/
│   ├── flights_demo/    # FlightsView — MapDriver + flights BE
│   └── places_demo/     # PlacesView — ListDriver + MapDriver + parks BE
backends/
├── places_backend/      # parks_service.py (port 8200)
└── flights_backend/     # flights_service.py (port 8300)
```

## Adding a new application

1. Create `src/pyview_map/applications/<name>/` with `__init__.py` and `<name>.py`.
2. If static assets needed, add to `app.py`: `("pyview_map.applications.<name>", "static")`
   — use the full dotted package name.
3. If JS hook, add a `<script defer>` tag in `app.py`.
4. Register in `__main__.py`: `app.add_live_view("/<path>", MyLiveView)`

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

# Ibis template:
# {% for dom_id, item in items %} ... {% endfor %} inside phx-update="stream"

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

## Dependencies

Packages from [`http_stream_prj`](https://github.com/avilior/http_stream_prj):

| Package | Purpose |
|---|---|
| `http-stream-transport` | `JRPCService`, `mcp_router` |
| `http-stream-client` | `ClientRPC` async client |
| `jrpc-common` | `JSONRPCRequest` / `JSONRPCResponse` models |

Installed as git subdirectory dependencies (see `pyproject.toml` `[tool.uv.sources]`).

## JSON-RPC API

Endpoint: `POST /api/mcp` (mounted in `__main__.py` via `app.mount("/api", api_app)`).

Full API reference with method tables, event types, channel/cid routing, and usage examples: **`docs/api-reference.md`**

## Important pitfalls

- **Hook init ordering** — `DMarkItem.mounted()` can fire before `DynamicMap.mounted()`. Hooks queue in `pendingMarkers`/`pendingPolylines`; flushed after Leaflet map created.
- **Follow-marker vs panTo** — Use `map.followMarker` for continuous tracking. Do NOT use `map.panTo` for continuous tracking (browser compositor issue).
- **LatLng conversion** — Internal: `LatLng` dataclass. Wire: `[lat, lng]` arrays. Convert at boundaries with `.to_list()` / `LatLng.from_list()`.

## Ruff & Python 3.14

Ruff 0.15+ supports t-string syntax (PEP 750) — no file exclusions needed.
