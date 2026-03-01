# pyview_map

A PyView LiveView demo app showing interactive Leaflet.js maps.

**Claude Code memory**: `~/.claude/projects/-Users-avilior-developer-python-pyview-map/memory/MEMORY.md`

## Running

```bash
uv run pyview-map
```

Server starts at `http://localhost:8123`.  Available routes:

| Route   | View               |
|---------|--------------------|
| `/map`  | Static park map    |
| `/dmap` | Dynamic marker map |

## Project layout

```
src/pyview_map/
├── __main__.py          # Entry point — registers routes and starts uvicorn
├── app.py               # PyView app, StaticFiles mount, root template (Tailwind + Leaflet CDN)
└── views/
    ├── maps/            # /map  — National Parks Leaflet map
    │   ├── map.py       # LiveView class + MapContext dataclass
    │   ├── map.html     # Jinja2/ibis template
    │   ├── map.css
    │   ├── parks.py     # Static park data
    │   └── static/
    │       └── map.js   # ParksMap class + Hooks.ParksMap
    └── dynamic_map/     # /dmap — Generic real-time streaming marker map
        ├── dynamic_map.py        # DynamicMapLiveView (generic) + MarkerSource protocol
        ├── dynamic_map.html      # phx-update="stream" sentinel divs + phx-update="ignore" map
        ├── dynamic_map.css
        ├── latlng.py             # LatLng dataclass — replaces raw [lat, lng] lists
        ├── dmarker.py            # DMarker dataclass (uses LatLng)
        ├── mock_generator.py     # MockGenerator — in-process MarkerSource (heading/speed simulation)
        ├── api_marker_source.py  # APIMarkerSource — MarkerSource backed by asyncio.Queue (API-driven)
        ├── marker_api.py         # FastAPI sub-app — JRPCService methods + mcp_router at /api/mcp
        ├── map_events.py         # Typed event/command dataclasses + parse_event()
        ├── command_queue.py      # CommandQueue — class-level queue for map commands
        ├── event_broadcaster.py  # EventBroadcaster — fans out events to SSE subscribers
        └── static/
            └── dynamic_map.js    # Hooks.DynamicMap (map init + command handlers) + Hooks.DMarkItem
examples/
└── mock_client.py               # Reference external client — drives /dmap via ClientRPC (MCP)
```

## Adding a new view

1. Create `src/pyview_map/views/<name>/` with `__init__.py`, `<name>.py`, `<name>.html`, and optionally `<name>.css` and `static/<name>.js`.
2. Add the static package to `app.py`:
   ```python
   ("pyview_map.views.<name>", "static"),
   ```
   **Use the full dotted package name** (`pyview_map.views.<name>`), not a relative name like `views.<name>` — Starlette resolves it via `importlib` and needs the fully qualified name.
3. If the view has a JS hook, add a `<script defer>` tag for it in the `css` string in `app.py`.
4. Register the route in `__main__.py`:
   ```python
   app.add_live_view("/<path>", MyLiveView)
   ```

## Key conventions

- **Context** — each view defines a `@dataclass` context (e.g. `MapContext`) passed to `LiveViewSocket[T]`.
- **Initial data → template** — pass data via context in `mount()`; render with `{{ value|json_encode }}` for JS consumption.
- **Client → server events** — wire `phx-click` / `phx-value-*` in the template; handle in `handle_event()`.
- **Server → client events** — use `await socket.push_event("event-name", payload)` for ad-hoc JS events.
- **Map DOM stability** — wrap the Leaflet `div` in `phx-update="ignore"` so LiveView diffs don't touch it.
- **`json_encode` filter** — registered via `@filters.register` (from `pyview.vendor.ibis`); available in all templates.
- **Ibis template limits** — the ibis template engine does not support subscript syntax (`obj[0]`); use properties or filters instead.

## Streaming live updates with `Stream`

Use `pyview.stream.Stream` for collections that change over time.  The ibis
`{% for dom_id, item in stream %}` loop detects a `Stream` object and emits
the Phoenix wire-format stream diff automatically.

### Pattern

```python
from pyview.stream import Stream
from pyview.events import InfoEvent

@dataclass
class MyContext:
    items: Stream[Item]

class MyLiveView(LiveView[MyContext]):
    async def mount(self, socket, session):
        self._state = MyState()
        socket.context = MyContext(items=Stream(self._state.items, name="items"))
        if socket.connected:
            socket.schedule_info(InfoEvent("tick"), seconds=1.0)

    async def handle_info(self, event: InfoEvent, socket):
        if event.name != "tick":
            return
        # mutate the stream — pyview sends only the diff
        socket.context.items.insert(new_item)             # append
        socket.context.items.insert(item, update_only=True)  # update in-place
        socket.context.items.delete_by_id("items-<id>")  # remove
```

### Template

```html
<!-- Stream container — id must match the Stream name -->
<div id="items" phx-update="stream">
    {% for dom_id, item in items %}
    <div id="{{ dom_id }}" phx-hook="ItemHook" data-value="{{ item.value }}">
        {{ item.name }}
    </div>
    {% endfor %}
</div>
```

### JS hook lifecycle

```js
window.Hooks.ItemHook = {
    mounted()   { /* element added to DOM   */ },
    updated()   { /* element's data changed */ },
    destroyed() { /* element removed        */ },
};
```

`schedule_info` uses pyview's `apscheduler`-backed scheduler; jobs are
automatically cancelled when the socket closes (`socket.close()`), so no
manual cleanup is needed.

Use `push_event` / `handleEvent` instead when you need to send arbitrary data
to JS without modifying the DOM (e.g. `highlight-park` in the `/map` view).

## DynamicMapLiveView — plugging in a custom data source

`DynamicMapLiveView` is a generic framework. It knows nothing about where
markers come from. Implement the `MarkerSource` protocol and register it with
`with_source()`.

### MarkerSource protocol

```python
from pyview_map.views.dynamic_map.dynamic_map import DMarker, MarkerSource
from pyview_map.views.dynamic_map.latlng import LatLng

class MySource:                          # no need to inherit — duck typing
    @property
    def markers(self) -> list[DMarker]:
        """Called once on mount to populate the initial map state."""
        return [DMarker(id="1", name="HQ", lat_lng=LatLng(40.7, -74.0))]

    def next_update(self) -> dict:
        """Called on every tick. Return one operation."""
        # {"op": "add",    "id": str, "name": str, "latLng": [lat, lng]}
        # {"op": "delete", "id": str}
        # {"op": "update", "id": str, "name": str, "latLng": [lat, lng]}
        # {"op": "noop"}   ← return this when there is nothing to do this tick
        return {"op": "update", "id": "1", "name": "HQ", "latLng": [40.71, -74.01]}
```

> **Note:** `DMarker.lat_lng` is a `LatLng` dataclass internally, but `next_update()`
> returns plain `[lat, lng]` lists in its dict (the wire format). The LiveView converts
> lists to `LatLng` at the boundary.

### Registering in __main__.py

```python
from pyview_map.views.dynamic_map import DynamicMapLiveView
from myapp.sources import MySource

app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))

# Pass constructor kwargs and override the tick interval (seconds):
app.add_live_view("/fleet", DynamicMapLiveView.with_source(FleetTracker, tick_interval=2.0, fleet_id=42))
```

`MockGenerator` in `mock_generator.py` is an in-process reference implementation.
`APIMarkerSource` in `api_marker_source.py` is the default source used by `/dmap` —
it receives operations from the JSON-RPC API and queues them for the LiveView tick.

## Dependencies

The marker API uses packages from the
[`http_stream_prj`](https://github.com/avilior/http_stream_prj) monorepo:

| Package | Purpose |
|---|---|
| `http-stream-transport` | `JRPCService` for method registration, `mcp_router` for MCP endpoint |
| `http-stream-client` | `ClientRPC` async client with MCP lifecycle |
| `jrpc-common` | Shared `JSONRPCRequest` / `JSONRPCResponse` models |

These are installed as git subdirectory dependencies (see `pyproject.toml` `[tool.uv.sources]`).

## JSON-RPC API (`/api/mcp`)

`marker_api.py` registers methods on the global `jrpc_service` from `http_stream_transport`
and includes `mcp_router` on a FastAPI sub-app mounted at `/api`. The MCP endpoint is at
`POST /api/mcp`. It is mounted in `__main__.py`:

```python
app.mount("/api", api_app)
```

### Authentication

All requests to `/api/mcp` require a Bearer token:
```
Authorization: Bearer tok-acme-001
```

Pre-configured mock tokens: `tok-acme-001` (Acme Corp), `tok-globex-002`, `tok-initech-003`.

### MCP handshake

Clients must complete the MCP lifecycle before calling marker methods:
1. `GET /api/health` — liveness check
2. `POST /api/mcp` — send `initialize` request → receive session ID
3. `POST /api/mcp` — send `notifications/initialized` notification
4. `POST /api/mcp` — call marker methods with `Mcp-Session-Id` header

`ClientRPC` from `http_stream_client` handles this automatically via `async with`.

### Methods

#### Marker methods

| Method | Params | Effect |
|---|---|---|
| `markers.add` | `id`, `name`, `latLng` | Add marker; enqueue `add` op; broadcast `MarkerOpEvent` |
| `markers.update` | `id`, `name`, `latLng` | Move/rename marker; enqueue `update` op; broadcast `MarkerOpEvent` |
| `markers.delete` | `id` | Remove marker; enqueue `delete` op; broadcast `MarkerOpEvent` |
| `markers.list` | — | Return current `_markers` dict |
| `map.events.subscribe` | — | Returns `asyncio.Queue` → SSE stream of `JSONRPCNotification` events |

#### Map command methods

These let external clients control the browser's Leaflet map. Each method pushes
a command to `CommandQueue`; the LiveView tick drains the queue and calls
`socket.push_event()`, which triggers `handleEvent` in `dynamic_map.js`.

| Method | Params | JS effect |
|---|---|---|
| `map.setView` | `latLng`, `zoom` | `_map.setView(latLng, zoom)` |
| `map.flyTo` | `latLng`, `zoom` | `_map.flyTo(latLng, zoom)` (animated) |
| `map.fitBounds` | `corner1`, `corner2` | `_map.fitBounds([corner1, corner2])` |
| `map.flyToBounds` | `corner1`, `corner2` | `_map.flyToBounds([corner1, corner2])` (animated) |
| `map.setZoom` | `zoom` | `_map.setZoom(zoom)` |
| `map.resetView` | — | Reset to US overview `[39.5, -98.35]` zoom 4 |
| `map.highlightMarker` | `id` | Pan to marker and open its tooltip |

All `latLng`/`corner` params are `[lat, lng]` arrays on the wire; converted to
`LatLng` at the API boundary in `marker_api.py`.

`APIMarkerSource` uses **class-level** state (`_queue`, `_markers`) so all LiveView
connections share the same queue — every connected browser sees every update.

### Hook init ordering pitfall

`DMarkItem.mounted()` can fire before `DynamicMap.mounted()` sets `_map` (Phoenix
LiveView processes the `phx-update="stream"` container before the
`phx-update="ignore"` wrapper). To handle this, `dynamic_map.js` queues pending
hooks in `_pending[]` and flushes them inside `DynamicMap.mounted()` after `_map`
is created.

## LatLng type

All lat/lng values use the `LatLng` dataclass (`latlng.py`) internally.
Wire format (JSON-RPC params, JS payloads) remains `[lat, lng]` arrays.

```python
from pyview_map.views.dynamic_map.latlng import LatLng

ll = LatLng(39.5, -98.35)
ll.to_list()                  # → [39.5, -98.35]
LatLng.from_list([39.5, -98.35])  # → LatLng(lat=39.5, lng=-98.35)
```

Conversion happens at boundaries:
- **API → internal**: `marker_api.py` calls `LatLng.from_list()` on wire params
- **Browser → internal**: `dynamic_map.py` `handle_event()` converts payload lists
- **Internal → wire**: `to_dict()` / `to_push_event()` call `.to_list()`

## Map commands (client → browser)

External clients can control the browser map via `map.*` JSON-RPC methods.
The flow is:

1. **Client** calls `map.flyTo`, `map.setZoom`, etc. via JSON-RPC
2. **`marker_api.py`** handler constructs a command dataclass and pushes to `CommandQueue`
3. **`dynamic_map.py`** `handle_info()` drains `CommandQueue` on every tick, calling
   `socket.push_event()` for each command
4. **`dynamic_map.js`** `handleEvent` receivers call the corresponding Leaflet method

Command dataclasses are defined in `map_events.py` (`SetViewCmd`, `FlyToCmd`,
`FitBoundsCmd`, `FlyToBoundsCmd`, `SetZoomCmd`, `ResetViewCmd`, `HighlightMarkerCmd`).
Each has `to_push_event() -> tuple[str, dict]`.

`CommandQueue` in `command_queue.py` uses class-level `asyncio.Queue` (same
singleton pattern as `APIMarkerSource` and `EventBroadcaster`).

## Event streaming to external clients

Browser map/marker events and API marker operations are broadcast to external
clients via SSE using `EventBroadcaster` and the `map.events.subscribe` method.

### Architecture

1. **Browser → LiveView** — `handle_event()` in `dynamic_map.py` receives
   `marker-event` and `map-event` from Leaflet hooks, constructs typed event
   dataclasses, and calls `EventBroadcaster.broadcast()`.
2. **API → broadcast** — `markers.add/update/delete` handlers in `marker_api.py`
   broadcast `MarkerOpEvent` after each mutation.
3. **EventBroadcaster** — maintains a set of subscriber `asyncio.Queue`s (bounded,
   maxsize=256). `broadcast()` is non-blocking (`put_nowait`); slow consumers are
   dropped. The `JSONRPCNotification` is built once and shared across all subscribers.
4. **SSE delivery** — `map.events.subscribe` returns a queue; `mcp_router` detects
   the queue return and opens an SSE stream, sending `JSONRPCNotification` messages
   with method `notifications/map.event`.

### Event types (`map_events.py`)

All events are `@dataclass(slots=True)` for minimal allocation overhead.
Each has `to_dict()` for serialization; `parse_event()` reconstructs them
from a notification params dict.

```python
from pyview_map.views.dynamic_map.latlng import LatLng
from pyview_map.views.dynamic_map.map_events import (
    MarkerOpEvent, MarkerEvent, MapEvent, BroadcastEvent, parse_event,
)
```

**`MarkerOpEvent`** — marker CRUD from the API:
```python
MarkerOpEvent(op="add", id="abc", name="Alpha-01", latLng=LatLng(39.5, -98.3))
MarkerOpEvent(op="update", id="abc", name="Alpha-01", latLng=LatLng(40.0, -97.0))
MarkerOpEvent(op="delete", id="abc")
# to_dict() → {"type": "marker-op", "op": ..., "id": ..., "name": ..., "latLng": [lat, lng]}
```

**`MarkerEvent`** — browser marker interaction:
```python
MarkerEvent(event="click", id="markers-abc", name="Alpha-01", latLng=LatLng(39.5, -98.3))
# to_dict() → {"type": "marker-event", "event": ..., "id": ..., "name": ..., "latLng": [lat, lng]}
```

**`MapEvent`** — browser map interaction:
```python
MapEvent(event="zoomend", center=LatLng(39.5, -98.3), zoom=6, latLng=None)
# to_dict() → {"type": "map-event", "event": ..., "center": [lat, lng], "zoom": ..., "latLng": ...}
```

### Client subscription example

```python
from pyview_map.views.dynamic_map.map_events import MarkerOpEvent, MarkerEvent, MapEvent, parse_event

req = JSONRPCRequest(method="map.events.subscribe")
async for msg in rpc.send_request(req):
    match msg:
        case JSONRPCNotification():
            evt = parse_event(msg.params)
            match evt:
                case MarkerOpEvent(): ...
                case MarkerEvent():   ...
                case MapEvent():      ...
        case JSONRPCResponse():
            break  # end of channel
```
