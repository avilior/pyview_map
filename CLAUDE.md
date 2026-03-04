# pyview_map

A PyView LiveView demo app showing interactive Leaflet.js maps.

**Claude Code memory**: `~/.claude/projects/-Users-avilior-developer-python-pyview-map/memory/MEMORY.md`

## Running

```bash
uv run pyview-map
```

Server starts at `http://localhost:8123`.  Available routes:

| Route   | View                      |
|---------|---------------------------|
| `/map`  | Static park map           |
| `/dmap` | Dynamic marker map        |
| `/mmap` | Multi-map dashboard (2×)  |

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
    └── dynamic_map/     # /dmap, /mmap — LiveComponent-based real-time streaming map
        ├── dynamic_map.py        # DynamicMapComponent (LiveComponent), DynamicMapLiveView, MultiMapLiveView
        ├── dynamic_map.css
        ├── latlng.py             # LatLng dataclass — replaces raw [lat, lng] lists
        ├── dmarker.py            # DMarker dataclass (uses LatLng)
        ├── dpolyline.py          # DPolyline dataclass (uses LatLng)
        ├── mock_generator.py     # MockGenerator — in-process MarkerSource (heading/speed simulation)
        ├── api_marker_source.py  # APIMarkerSource — fan-out queues with map_id routing
        ├── api_polyline_source.py # APIPolylineSource — same fan-out + map_id routing
        ├── marker_api.py         # FastAPI sub-app — JRPCService methods + mcp_router at /api/mcp
        ├── map_events.py         # Typed event/command dataclasses + parse_event()
        ├── command_queue.py      # CommandQueue — fan-out queue for map commands with map_id routing
        ├── event_broadcaster.py  # EventBroadcaster — fans out events to SSE subscribers
        ├── icon_registry.py      # DivIcon registry (icons.json → JSON for JS)
        └── static/
            ├── dynamic_map.js    # MapInstance class + Hooks: DynamicMap, DMarkItem, DPolylineItem
            └── icons.json        # Named DivIcon definitions
examples/
├── mock_client.py               # Reference external client — drives /dmap via ClientRPC (MCP)
└── planes/
    └── mock_planes.py           # Flight simulation — airports, polyline route, followMarker
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
- **Initial data → template** — pass data via context in `mount()`; render with `{{ value|json_encode }}` for JS consumption (ibis) or interpolation (t-strings).
- **Client → server events** — wire `phx-click` / `phx-value-*` in the template; handle in `handle_event()`.
- **Server → client events** — use `await socket.push_event("event-name", payload)` for ad-hoc JS events.
- **Map DOM stability** — wrap the Leaflet `div` in `phx-update="ignore"` so LiveView diffs don't touch it.
- **`json_encode` filter** — registered via `@filters.register` (from `pyview.vendor.ibis`); available in ibis templates.
- **Ibis template limits** — the ibis template engine does not support subscript syntax (`obj[0]`); use properties or filters instead.
- **t-string templates (Python 3.14)** — `DynamicMapComponent` and its parent LiveViews use t-string templates with `TemplateView` mixin + `live_component()` / `stream_for()` helpers from PyView. Ibis `.html` templates are still used for the `/map` parks view.

## Streaming live updates with `Stream`

Use `pyview.stream.Stream` for collections that change over time.

### Ibis template pattern

The ibis `{% for dom_id, item in stream %}` loop detects a `Stream` object and emits
the Phoenix wire-format stream diff automatically.

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

### t-string template pattern (LiveComponent)

In t-string templates (used by `DynamicMapComponent`), use `stream_for()` from
`pyview.template.live_view_template`:

```python
from pyview.template.live_view_template import stream_for

def template(self, assigns, meta):
    items_html = stream_for(assigns.items, lambda dom_id, item:
        t'<div id="{dom_id}" phx-hook="ItemHook" data-value="{item.value}">{item.name}</div>'
    )
    return t'<div id="items" phx-update="stream">{items_html}</div>'
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

## Dynamic map architecture

The dynamic map uses a **LiveComponent** architecture:

```
DynamicMapLiveView (TemplateView + LiveView)
├── owns schedule_info("tick") — drives all updates
├── owns marker source, polyline source, command queue
├── template() returns t-string with live_component() call
│
└── DynamicMapComponent (LiveComponent)
    ├── owns Stream[DMarker], Stream[DPolyline]
    ├── update() receives pending ops from parent → mutates streams
    ├── template() returns t-string with stream_for() for markers/polylines
    └── handle_event() handles marker-event, polyline-event, map-event
```

`MultiMapLiveView` hosts N independent `DynamicMapComponent` instances, each
with its own source/queue keyed by `map_id`.

### Data flow

1. Parent `handle_info("tick")` drains marker source, polyline source, command queue
2. Stores ops as lists of dicts in context + increments `ops_version`
3. Parent re-renders → `live_component()` passes ops as assigns
4. Component `update()` receives ops, applies them to its own Streams (gated by version counter to prevent duplicate application)
5. Component re-renders with updated stream diffs

### DynamicMapComponent

`DynamicMapComponent(LiveComponent[DynamicMapComponentContext])` is the reusable
map widget. Key lifecycle:

- **`mount()`** — creates empty `Stream[DMarker]` and `Stream[DPolyline]` with
  map_id-prefixed names (e.g. `"dmap-markers"`, `"left-markers"`)
- **`update()`** — receives `marker_ops`, `polyline_ops`, `ops_version` from parent;
  applies ops to streams only when version changes
- **`template()`** — t-string with `stream_for()` for markers/polylines,
  `phx-target="{meta.myself}"` for event targeting
- **`handle_event()`** — handles `marker-event`, `polyline-event`, `map-event`
  from Leaflet hooks; broadcasts via `EventBroadcaster`

Stream names use the pattern `f"{map_id}-markers"` and `f"{map_id}-polylines"`
to avoid DOM ID collisions between multiple map instances.

### Plugging in a custom data source

Implement the `MarkerSource` protocol and register with `with_source()`:

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

### Registering in __main__.py

```python
from pyview_map.views.dynamic_map import DynamicMapLiveView, MultiMapLiveView

# Single map:
app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))

# Pass constructor kwargs and override the tick interval (seconds):
app.add_live_view("/fleet", DynamicMapLiveView.with_source(FleetTracker, tick_interval=2.0, fleet_id=42))

# Multiple maps on one page:
app.add_live_view("/mmap", MultiMapLiveView.with_maps(["left", "right"]))
```

`MockGenerator` in `mock_generator.py` is an in-process reference implementation.
`APIMarkerSource` in `api_marker_source.py` is the default source used by `/dmap` —
it receives operations from the JSON-RPC API and fans them out to all connected
LiveView instances via per-instance subscriber queues.

### MultiMapLiveView

`MultiMapLiveView.with_maps(["left", "right"])` creates a page with N independent
map instances. Each map gets its own `APIMarkerSource`, `APIPolylineSource`, and
`CommandQueue` subscriber keyed by `map_id`. External clients target a specific
map via the `map_id` parameter on any API method (see below).

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
| `markers.add` | `id`, `name`, `latLng`, `map_id?` | Add marker; enqueue `add` op; broadcast `MarkerOpEvent` |
| `markers.update` | `id`, `name`, `latLng`, `map_id?` | Move/rename marker; enqueue `update` op; broadcast `MarkerOpEvent` |
| `markers.delete` | `id`, `map_id?` | Remove marker; enqueue `delete` op; broadcast `MarkerOpEvent` |
| `markers.list` | — | Return current `_markers` dict |
| `map.events.subscribe` | — | Returns `asyncio.Queue` → SSE stream of `JSONRPCNotification` events |

#### Polyline methods

| Method | Params | Effect |
|---|---|---|
| `polylines.add` | `id`, `name`, `path`, `color?`, `weight?`, `opacity?`, `dashArray?`, `map_id?` | Add polyline; enqueue `add` op; broadcast `PolylineOpEvent` |
| `polylines.update` | `id`, `name`, `path`, `color?`, `weight?`, `opacity?`, `dashArray?`, `map_id?` | Update polyline; enqueue `update` op; broadcast `PolylineOpEvent` |
| `polylines.delete` | `id`, `map_id?` | Remove polyline; enqueue `delete` op; broadcast `PolylineOpEvent` |
| `polylines.list` | — | Return current `_polylines` dict |

`path` is an array of `[lat, lng]` arrays. Polylines crossing the antimeridian
(±180°) are automatically unwrapped in JS so they draw the short path.

#### Map command methods

These let external clients control the browser's Leaflet map. Each method pushes
a command to `CommandQueue`; the LiveView tick drains the queue and calls
`socket.push_event()`, which triggers `handleEvent` in `dynamic_map.js`.

| Method | Params | JS effect |
|---|---|---|
| `map.setView` | `latLng`, `zoom`, `map_id?` | `map.setView(latLng, zoom)` |
| `map.panTo` | `latLng`, `map_id?` | `map.setView(latLng, currentZoom)` (instant, keeps zoom) |
| `map.flyTo` | `latLng`, `zoom`, `map_id?` | `map.flyTo(latLng, zoom)` (animated) |
| `map.fitBounds` | `corner1`, `corner2`, `map_id?` | `map.fitBounds([corner1, corner2])` |
| `map.flyToBounds` | `corner1`, `corner2`, `map_id?` | `map.flyToBounds([corner1, corner2])` (animated) |
| `map.setZoom` | `zoom`, `map_id?` | `map.setZoom(zoom)` |
| `map.resetView` | `map_id?` | Reset to US overview `[39.5, -98.35]` zoom 4 |
| `map.highlightMarker` | `id`, `map_id?` | Pan to marker and open its tooltip |
| `map.highlightPolyline` | `id`, `map_id?` | Fit bounds to polyline and open its tooltip |
| `map.followMarker` | `id`, `map_id?` | Auto-pan to marker on every update (see below) |
| `map.unfollowMarker` | `map_id?` | Stop auto-panning |

All `latLng`/`corner` params are `[lat, lng]` arrays on the wire; converted to
`LatLng` at the API boundary in `marker_api.py`.

#### `map_id` routing

All marker, polyline, and map command methods accept an optional `map_id` parameter:

- **`map_id` omitted or `None`** — operation is broadcast to ALL map instances (backwards compatible)
- **`map_id="left"`** — operation is routed only to the map instance subscribed with that ID

```python
# Target a specific map on the /mmap page:
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "map_id": "left"})

# Broadcast to all maps (backwards compatible):
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0]})
```

Internally, `APIMarkerSource`, `APIPolylineSource`, and `CommandQueue` use
`_subscribers: dict[str | None, set[Queue]]` keyed by `map_id`. The `None` key
holds broadcast subscribers. `push()` fans out to `_subscribers[map_id]` +
`_subscribers[None]`, with a `seen` set to avoid double-delivery.

#### Follow-marker (continuous tracking)

`map.followMarker(id)` tells the JS to auto-pan the map to the specified marker
whenever `DMarkItem.updated()` fires. The pan happens in the same rendering
context as the marker position update, so the browser paints both changes in a
single frame.

This is the correct approach for tracking moving markers. **Do not use
`map.panTo` for continuous tracking** — `push_event`-based view changes are not
reliably repainted by browsers without user interaction (a known Leaflet/browser
compositor issue). `map.panTo` is still available for one-shot pans triggered by
user action.

```python
# Start following a marker
await _send(rpc, "map.followMarker", {"id": "plane1"})

# Stop following
await _send(rpc, "map.unfollowMarker", {})

# Switch to following a different marker (overwrites previous)
await _send(rpc, "map.followMarker", {"id": "plane2"})
```

`APIMarkerSource`, `APIPolylineSource`, and `CommandQueue` use the **bounded-queue
fan-out** pattern (same as `EventBroadcaster`): each LiveView instance gets its
own subscriber queue; push methods fan out to subscribers by `map_id`; full queues
are auto-discarded. The shared `_markers`/`_polylines` dicts stay class-level so
all instances see the same state.

### Hook init ordering pitfall

`DMarkItem.mounted()` can fire before `DynamicMap.mounted()` creates the
`MapInstance`. To handle this, each `MapInstance` has `pendingMarkers` and
`pendingPolylines` arrays; hooks queue themselves there when their instance's
map isn't ready yet. `DynamicMap.mounted()` flushes all pending hooks after the
Leaflet map is created.

### JS: per-instance state (MapInstance)

Multiple maps on one page require per-instance state. `dynamic_map.js` uses a
`MapInstance` class and a global `_instances` Map keyed by map element ID:

```javascript
class MapInstance {
  constructor(mapEl) {
    this.map = null;              // Leaflet map
    this.markers = new Map();      // domId → L.marker
    this.polylines = new Map();    // domId → L.polyline
    this.repeatedMarkers = null;   // L.gridLayer.repeatedMarkers()
    this.followMarkerId = null;
    this.pendingMarkers = [];      // hooks queued before map init
    this.pendingPolylines = [];
    this.iconRegistry = {};
    this.mapElId = mapEl.id;
  }
}
```

Hooks find their instance via `_findInstance(el)` which walks up the DOM with
`el.closest('[data-map-instance]')` and looks up the instance in `_instances`.
All marker/polyline/command logic uses `instance.xxx` instead of module-level
globals. RepeatedMarkers prototype patches remain at module level.

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

1. **Client** calls `map.flyTo`, `map.setZoom`, etc. via JSON-RPC (optionally with `map_id`)
2. **`marker_api.py`** handler constructs a command dataclass and calls `CommandQueue.push(cmd, map_id=map_id)`
3. **`CommandQueue`** fans out the command to subscriber queues matching the `map_id`
4. **`dynamic_map.py`** parent LiveView `handle_info()` drains command queues on each tick, calling
   `socket.push_event()` for each command
5. **`dynamic_map.js`** `handleEvent` receivers on the `DynamicMap` hook call the corresponding
   Leaflet method on the correct `MapInstance`

Command dataclasses are defined in `map_events.py` (`SetViewCmd`, `PanToCmd`,
`FlyToCmd`, `FitBoundsCmd`, `FlyToBoundsCmd`, `SetZoomCmd`, `ResetViewCmd`,
`HighlightMarkerCmd`, `HighlightPolylineCmd`, `FollowMarkerCmd`, `UnfollowMarkerCmd`).
Each has `to_push_event() -> tuple[str, dict]`.

`CommandQueue` in `command_queue.py` uses the bounded-queue fan-out pattern:
each LiveView calls `CommandQueue.subscribe(map_id=...)` on mount and drains its
queue on each tick. `push(cmd, map_id=...)` fans out to matching subscriber
queues; full queues are auto-discarded.

## Event streaming to external clients

Browser map/marker events and API marker operations are broadcast to external
clients via SSE using `EventBroadcaster` and the `map.events.subscribe` method.

### Architecture

1. **Browser → LiveView** — `handle_event()` in `dynamic_map.py` receives
   `marker-event`, `polyline-event`, and `map-event` from Leaflet hooks,
   constructs typed event dataclasses, and calls `EventBroadcaster.broadcast()`.
2. **API → broadcast** — `markers.add/update/delete` and `polylines.add/update/delete`
   handlers in `marker_api.py` broadcast `MarkerOpEvent`/`PolylineOpEvent` after
   each mutation.
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
    MarkerOpEvent, MarkerEvent, MapEvent, PolylineOpEvent, PolylineEvent,
    BroadcastEvent, parse_event,
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

**`PolylineOpEvent`** — polyline CRUD from the API:
```python
PolylineOpEvent(op="add", id="route1", name="Route 1", path=[LatLng(40, -74), LatLng(51, -0.5)])
# to_dict() → {"type": "polyline-op", "op": ..., "id": ..., "path": [[lat, lng], ...], ...}
```

**`PolylineEvent`** — browser polyline interaction:
```python
PolylineEvent(event="click", id="polylines-route1", name="Route 1", latLng=LatLng(45, -37))
# to_dict() → {"type": "polyline-event", "event": ..., "id": ..., "name": ..., "latLng": [lat, lng]}
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
