# pyview_map

A PyView LiveView demo app showing interactive Leaflet.js maps.

**Claude Code memory**: `~/.claude/projects/-Users-avilior-developer-python-pyview-map/memory/MEMORY.md`

## Running

```bash
uv run --package flights-bff flights-bff   # Flights BFF on :8123
uv run --package places-bff places-bff     # Places BFF on :8124
just all                                   # Both BEs + both BFFs, opens browser
just places                                # Parks BE + Places BFF
just flights                               # Flights BE + Flights BFF
```

Routes: `/flights` (flight simulation on flights-bff:8123), `/places_demo` (places list + map on places-bff:8124)

### Release (GHCR)

```bash
just release-build       # Build multi-arch images + push to ghcr.io
just release-up          # Pull + start from registry
just release-down        # Stop release services
just release-logs        # Tail release logs
```

Images are built for `linux/amd64` + `linux/arm64` and pushed to `ghcr.io/avilior/pyview-map-{flights-bff,places-bff,places-backend,flights-backend}` with `:latest` + `:<sha>` tags.

Requires `GITHUB_USER` and `GITHUB_TOKEN` (PAT with `read:packages` + `write:packages`) in `.env`. See `.env.example`.

Deploy compose file: `docker-compose.release.yml` (pull-only, no build context). Use `IMAGE_TAG=<sha>` to pin a specific version.

### Remote deployment

```bash
just deploy avi@nuc8.local /home/avi/docker/pyview   # scp files to remote
# Then on remote:
cp .env.example .env   # edit with credentials
just up                # login + pull + start all services
just health            # check service health
just upgrade <sha>     # deploy a specific version
```

`justfile.deploy` is copied to the remote as `justfile`. It has: `up`, `down`, `restart`, `upgrade`, `up-flights`, `up-places`, `health`, `status`, `logs`, `logs-service`, `images`, `list`.

## Project layout

```
pyproject.toml               # workspace root (no app code)
uv.lock                     # single unified lock
packages/
├── dmap_models/             # shared wire-protocol models
└── bff_engine/              # shared BFF engine — components, drivers, API/app factories
    ├── pyproject.toml
    └── src/bff_engine/
        ├── bff_app.py       # create_app() factory — PyView app, StaticFiles, CSS
        ├── bff_api.py       # create_api() factory — FastAPI, MCP router, bff.subscribe
        ├── shared/          # cid.py, event_broadcaster.py, item_store.py, topics.py
        ├── dynamic_map/     # Map LiveComponent + MapDriver + models + sources + api/
        └── dynamic_list/    # List LiveComponent + ListDriver + models + sources + api/
services/
├── flights_bff/             # Flights BFF (port 8123)
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/flights_bff/
│       ├── __main__.py      # Entry point — creates app/api, registers /flights
│       ├── settings.py      # FLIGHTS_BFF_* env vars
│       └── flights_demo.py  # FlightsView — MapDriver + flights BE
├── places_bff/              # Places BFF (port 8124)
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/places_bff/
│       ├── __main__.py      # Entry point — creates app/api, registers /places_demo
│       ├── settings.py      # PLACES_BFF_* env vars
│       └── places_demo.py   # PlacesView — ListDriver + MapDriver + parks BE
├── places_backend/          # parks_service.py (port 8200)
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/places_backend/
└── flights_backend/         # flights_service.py (port 8300)
    ├── pyproject.toml
    ├── Dockerfile
    └── src/flights_backend/
```

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

Installed as git subdirectory dependencies (see workspace root `pyproject.toml` `[tool.uv.sources]`).

## JSON-RPC API

Endpoint: `POST /api/mcp` (mounted in `__main__.py` via `app.mount("/api", api_app)`).

Full API reference with method tables, event types, channel/cid routing, and usage examples: **`docs/api-reference.md`**

## Important pitfalls

- **Hook init ordering** — `DMarkItem.mounted()` can fire before `DynamicMap.mounted()`. Hooks queue in `pendingMarkers`/`pendingPolylines`; flushed after Leaflet map created.
- **Follow-marker vs panTo** — Use `map.followMarker` for continuous tracking. Do NOT use `map.panTo` for continuous tracking (browser compositor issue).
- **LatLng conversion** — Internal: `LatLng` dataclass. Wire: `[lat, lng]` arrays. Convert at boundaries with `.to_list()` / `LatLng.from_list()`.

## Ruff & Python 3.14

Ruff 0.15+ supports t-string syntax (PEP 750) — no file exclusions needed.
