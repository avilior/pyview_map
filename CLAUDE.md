# pyview_map

A PyView LiveView demo app showing interactive Leaflet.js maps.

**Claude Code memory**: `~/.claude/projects/-Users-avilior-developer-python-pyview-map/memory/MEMORY.md`

## Running

```bash
uv run pyview-map
```

Server starts at `http://localhost:8123`.  Available routes:

| Route   | View                           |
|---------|--------------------------------|
| `/map`  | Static park map                |
| `/dmap` | Dynamic marker map             |
| `/mmap` | Multi-map dashboard (2×)       |
| `/map_list_demo` | Map + list demo (2 components) |
| `/places_demo` | Places list + map (external parks service) |

## Project layout

```
src/pyview_map/
├── __main__.py          # Entry point — registers routes and starts uvicorn
├── app.py               # PyView app, StaticFiles mount, root template (Tailwind + Leaflet CDN)
└── views/
    ├── components/      # Reusable LiveComponents
    │   ├── shared/                  # Cross-component utilities
    │   │   ├── cid.py                # next_cid() — monotonic counter for channel instance IDs
    │   │   ├── latlng.py             # LatLng dataclass — replaces raw [lat, lng] lists
    │   │   ├── event_broadcaster.py  # EventBroadcaster — fans out events to SSE subscribers
    │   │   ├── item_store.py         # ItemStore[T] — channel-partitioned state store
    │   │   └── topics.py             # PubSub topic naming functions
    │   ├── dynamic_map/             # Real-time streaming Leaflet map component
    │   │   ├── dynamic_map_component.py  # DynamicMapComponent (LiveComponent)
    │   │   ├── map_driver.py          # MapDriver — encapsulates parent-side plumbing for hosting a map
    │   │   ├── dynamic_map.css
    │   │   ├── icon_registry.py      # DivIcon registry (icons.json → JSON for JS)
    │   │   ├── models/               # Data types + events + commands
    │   │   │   ├── dmarker.py         # DMarker dataclass (uses LatLng)
    │   │   │   ├── dpolyline.py       # DPolyline dataclass (uses LatLng)
    │   │   │   └── map_events.py      # Typed event/command dataclasses + parse_event()
    │   │   ├── sources/              # Data providers + state stores
    │   │   │   ├── api_marker_source.py  # marker_store (ItemStore)
    │   │   │   └── api_polyline_source.py # polyline_store (ItemStore)
    │   │   ├── api/                  # JRPC methods + FastAPI sub-app
    │   │   │   └── marker_api.py      # JRPCService methods + mcp_router at /api/mcp
    │   │   └── static/
    │   │       ├── dynamic_map.js    # MapInstance class + Hooks: DynamicMap, DMarkItem, DPolylineItem
    │   │       └── icons.json        # Named DivIcon definitions
    │   └── dynamic_list/            # API-controlled scrollable list component
    │       ├── dynamic_list.py       # DynamicListComponent (LiveComponent), DynamicListLiveView
    │       ├── list_driver.py       # ListDriver — encapsulates parent-side plumbing for hosting a list
    │       ├── dynamic_list.css      # Highlight animation
    │       ├── models/               # Data types + events
    │       │   ├── dlist_item.py      # DListItem dataclass
    │       │   └── list_events.py     # ListItemOpEvent, ListItemClickEvent, HighlightListItemCmd
    │       ├── sources/              # Data providers + state stores
    │       │   └── api_list_source.py  # list_store (ItemStore)
    │       ├── api/                  # JRPC methods
    │       │   └── list_api.py        # JRPC methods registered on global jrpc_service
    │       └── static/
    │           └── dynamic_list.js   # Hook: DynamicList (highlight scroll/flash)
    ├── park_map_demo/       # /map — National Parks Leaflet map
    │   ├── park_map_demo.py # LiveView class + MapContext dataclass
    │   ├── map.html         # Jinja2/ibis template
    │   ├── map.css
    │   ├── parks.py         # Static park data
    │   └── static/
    │       └── map.js       # ParksMap class + Hooks.ParksMap
    ├── dynamic_map_demo/    # /dmap — single dynamic map page
    │   └── dynamic_map_demo.py   # DynamicMapLiveView — hosts DynamicMapComponent
    ├── multimaps_demo/      # /mmap — multi-map dashboard (2×)
    │   └── multimaps_demo.py     # MultiMapLiveView — hosts N DynamicMapComponent instances
    ├── map_list_demo/       # /map_list_demo — map + list side by side
    │   └── map_list_demo.py      # DemoLiveView — hosts DynamicMapComponent + DynamicListComponent
    └── places_demo/         # /places_demo — places list + map
        └── places_demo.py        # PlacesView — hosts ListDriver + MapDriver
examples/
├── mock_client.py               # Reference external client — drives /dmap via ClientRPC (MCP)
├── map_list_demo.py             # Coordinator for /map_list_demo — syncs map viewport to list, click→highlight
├── list/
│   ├── parks.py                 # National parks data (NationalPark TypedDict)
│   └── parks_service.py         # External client — populates /places_demo list, listens for click events
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
- **t-string templates (Python 3.14)** — `DynamicMapComponent`, `DynamicListComponent`, and their parent LiveViews use t-string templates with `TemplateView` mixin + `live_component()` / `stream_for()` helpers from PyView. Ibis `.html` templates are still used for the `/map` parks view.

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

In t-string templates (used by `DynamicMapComponent`, `DynamicListComponent`), use `stream_for()` from
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

The dynamic map uses a **LiveComponent** + **Driver** architecture:

```
DynamicMapLiveView (TemplateView + LiveView)
├── owns MapDriver (encapsulates all plumbing)
├── mount: creates MapDriver, calls await driver.connect(socket)
├── handle_info: routes PubSub messages to driver.handle_info(event, socket)
├── handle_event: calls driver.clear_ops() + driver.handle_event()
├── template: calls driver.render() to get live_component()
│
└── MapDriver
    ├── subscribes to PubSub topics on connect (marker-ops, polyline-ops, map-cmd)
    ├── handle_info(): receives PubSub messages, updates ops/version, pushes commands
    ├── handle_event(): parses events, broadcasts, returns summary
    ├── render(): returns live_component(DynamicMapComponent, ...)
    │
    └── DynamicMapComponent (LiveComponent)
        ├── owns Stream[DMarker], Stream[DPolyline]
        ├── update() receives pending ops from driver → mutates streams
        ├── template() returns t-string with stream_for() for markers/polylines
        └── handle_event() handles marker-event, polyline-event, map-event
```

`MultiMapLiveView` hosts N `MapDriver` instances, one per channel.
`DemoLiveView` hosts a `MapDriver` + `ListDriver` side by side.

### Data flow (PubSub)

1. API handler (e.g. `markers.add`) stores item in `ItemStore`, broadcasts op via `pub_sub_hub`
2. PubSub delivers message to subscribed sockets → `handle_info(InfoEvent(topic, op))`
3. Parent routes to `driver.handle_info()` → driver stores op, bumps `ops_version`
4. For commands: driver calls `socket.push_event()` directly
5. Re-render → `driver.render()` calls `live_component()` with current ops
6. Component `update()` applies ops to Streams (gated by version counter)
7. Component re-renders with updated stream diffs


### DynamicMapComponent

`DynamicMapComponent(LiveComponent[DynamicMapComponentContext])` is the reusable
map widget. Key lifecycle:

- **`mount()`** — creates empty `Stream[DMarker]` and `Stream[DPolyline]` with
  channel-prefixed names (e.g. `"dmap-markers"`, `"left-markers"`)
- **`update()`** — receives `marker_ops`, `polyline_ops`, `ops_version` from parent;
  applies ops to streams only when version changes
- **`template()`** — t-string with `stream_for()` for markers/polylines,
  `phx-target="{meta.myself}"` for event targeting
- **`handle_event()`** — handles `marker-event`, `polyline-event`, `map-event`
  from Leaflet hooks; broadcasts via `EventBroadcaster`

Stream names use the pattern `f"{channel}-markers"` and `f"{channel}-polylines"`
to avoid DOM ID collisions between multiple map instances.

### Registering in __main__.py

```python
from pyview_map.views.components.dynamic_map import DynamicMapLiveView

# Single map:
app.add_live_view("/dmap", DynamicMapLiveView.with_channel("dmap"))
```

### MapDriver and ListDriver

`MapDriver` and `ListDriver` encapsulate all parent-side plumbing for hosting
components. Page developers only interact with 5 methods:

```python
from pyview_map.views.components.dynamic_map import MapDriver
from pyview_map.views.components.dynamic_list import ListDriver

@dataclass
class MyPageContext:
    last_event: str = ""

class MyPageView(TemplateView, LiveView[MyPageContext]):
    async def mount(self, socket, session):
        self._map = MapDriver("my-map")
        self._list = ListDriver("my-list")
        socket.context = MyPageContext()
        if socket.connected:
            await self._map.connect(socket)
            await self._list.connect(socket)

    async def handle_info(self, event, socket):
        if await self._map.handle_info(event, socket):
            return
        if await self._list.handle_info(event, socket):
            return

    async def handle_event(self, event, payload, socket):
        self._map.clear_ops()
        self._list.clear_ops()
        summary = self._map.handle_event(event, payload) or self._list.handle_event(event, payload)
        if summary:
            socket.context.last_event = summary

    def template(self, assigns, meta):
        return t'<div>{self._map.render()}{self._list.render()}</div>'
```

Each driver auto-generates a unique `cid` (channel instance ID) via `next_cid()`.
The cid identifies a specific browser connection within a channel, enabling
per-connection targeting from the API.

```python
# Default — PubSub-driven with channel routing:
MapDriver("my-map")
```

### MultiMapLiveView

`MultiMapLiveView.with_maps(channels=["left", "right"])` creates a page with N independent
`MapDriver` instances. Each driver auto-subscribes using its channel for routing.
External clients target a specific map via the `channel` parameter on any API method.

## Dynamic list architecture

The dynamic list follows the same **LiveComponent + Driver** pattern as the map:

```
DynamicListLiveView (TemplateView + LiveView)
├── owns ListDriver (encapsulates all plumbing)
├── mount: creates ListDriver, calls await driver.connect(socket)
├── handle_info: routes PubSub messages to driver.handle_info(event, socket)
├── template: calls driver.render()
│
└── ListDriver
    ├── subscribes to PubSub topics on connect (list-ops, list-cmd)
    ├── handle_info(): receives PubSub messages, updates ops/version, pushes commands
    ├── handle_event(): parses item-click events, broadcasts
    ├── render(): returns live_component(DynamicListComponent, ...)
    │
    └── DynamicListComponent (LiveComponent)
        ├── owns Stream[DListItem]
        ├── update() receives pending ops from driver → mutates stream
        ├── template() returns t-string with stream_for() for clickable items
        └── handle_event("item-click") → broadcasts ListItemClickEvent
```

`DynamicListComponent` is reusable — `DemoLiveView` hosts it via `ListDriver`
alongside a `MapDriver` on the `/map_list_demo` page.

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

`marker_api.py` and `list_api.py` register methods on the global `jrpc_service` from
`http_stream_transport` and include `mcp_router` on a FastAPI sub-app mounted at `/api`.
The MCP endpoint is at `POST /api/mcp`. It is mounted in `__main__.py`:

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

Clients must complete the MCP lifecycle before calling methods:
1. `GET /api/health` — liveness check
2. `POST /api/mcp` — send `initialize` request → receive session ID
3. `POST /api/mcp` — send `notifications/initialized` notification
4. `POST /api/mcp` — call methods with `Mcp-Session-Id` header

`ClientRPC` from `http_stream_client` handles this automatically via `async with`.

### Methods

#### Marker methods

| Method | Params | Effect |
|---|---|---|
| `markers.add` | `id`, `name`, `latLng`, `channel`, `cid?` | Add marker; enqueue `add` op; broadcast `MarkerOpEvent` |
| `markers.update` | `id`, `name`, `latLng`, `channel`, `cid?` | Move/rename marker; enqueue `update` op; broadcast `MarkerOpEvent` |
| `markers.delete` | `id`, `channel`, `cid?` | Remove marker; enqueue `delete` op; broadcast `MarkerOpEvent` |
| `markers.list` | `channel` | Return current `_markers` dict for channel |
| `map.events.subscribe` | — | Returns `asyncio.Queue` → SSE stream of `JSONRPCNotification` events |

#### Polyline methods

| Method | Params | Effect |
|---|---|---|
| `polylines.add` | `id`, `name`, `path`, `channel`, `color?`, `weight?`, `opacity?`, `dashArray?`, `cid?` | Add polyline; enqueue `add` op; broadcast `PolylineOpEvent` |
| `polylines.update` | `id`, `name`, `path`, `channel`, `color?`, `weight?`, `opacity?`, `dashArray?`, `cid?` | Update polyline; enqueue `update` op; broadcast `PolylineOpEvent` |
| `polylines.delete` | `id`, `channel`, `cid?` | Remove polyline; enqueue `delete` op; broadcast `PolylineOpEvent` |
| `polylines.list` | `channel` | Return current `_polylines` dict for channel |

`path` is an array of `[lat, lng]` arrays. Polylines crossing the antimeridian
(±180°) are automatically unwrapped in JS so they draw the short path.

#### List methods

| Method | Params | Effect |
|---|---|---|
| `list.add` | `id`, `label`, `channel`, `subtitle?`, `at?` (-1=bottom, 0=top), `cid?` | Add item at position |
| `list.remove` | `id`, `channel`, `cid?` | Remove item by id |
| `list.clear` | `channel`, `cid?` | Remove all items |
| `list.highlight` | `id`, `channel`, `cid?` | Push highlight command (scroll + flash) |
| `list.list` | `channel` | Return current items for channel |
| `list.events.subscribe` | — | Returns `asyncio.Queue` → SSE stream of list events |

#### Map command methods

These let external clients control the browser's Leaflet map. Each method
broadcasts a command via PubSub; the driver receives it in `handle_info()` and calls
`socket.push_event()`, which triggers `handleEvent` in `dynamic_map.js`.

| Method | Params | JS effect |
|---|---|---|
| `map.setView` | `latLng`, `zoom`, `channel`, `cid?` | `map.setView(latLng, zoom)` |
| `map.panTo` | `latLng`, `channel`, `cid?` | `map.setView(latLng, currentZoom)` (instant, keeps zoom) |
| `map.flyTo` | `latLng`, `zoom`, `channel`, `cid?` | `map.flyTo(latLng, zoom)` (animated) |
| `map.fitBounds` | `corner1`, `corner2`, `channel`, `cid?` | `map.fitBounds([corner1, corner2])` |
| `map.flyToBounds` | `corner1`, `corner2`, `channel`, `cid?` | `map.flyToBounds([corner1, corner2])` (animated) |
| `map.setZoom` | `zoom`, `channel`, `cid?` | `map.setZoom(zoom)` |
| `map.resetView` | `channel`, `cid?` | Reset to US overview `[39.5, -98.35]` zoom 4 |
| `map.highlightMarker` | `id`, `channel`, `cid?` | Pan to marker and open its tooltip |
| `map.highlightPolyline` | `id`, `channel`, `cid?` | Fit bounds to polyline and open its tooltip |
| `map.followMarker` | `id`, `channel`, `cid?` | Auto-pan to marker on every update (see below) |
| `map.unfollowMarker` | `channel`, `cid?` | Stop auto-panning |

All `latLng`/`corner` params are `[lat, lng]` arrays on the wire; converted to
`LatLng` at the API boundary in `marker_api.py`.

#### `channel` and `cid` routing

All marker, polyline, list, and map command methods require a `channel` parameter
and accept an optional `cid` parameter:

- **`channel`** (required) — identifies the routing group (e.g. `"dmap"`, `"left"`,
  `"map_list_demo-map"`). All browser tabs subscribed to the same channel receive
  the same ops. Different channels are fully isolated — no cross-channel leakage.
- **`cid`** (optional, default `"*"`) — channel instance ID. Each browser connection
  gets a unique cid (monotonic counter via `next_cid()`). `cid="*"` broadcasts to
  all instances of the channel. A specific cid targets a single connection.

```python
# Broadcast to all instances of the "dmap" channel:
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "channel": "dmap"})

# Target a specific map on the /mmap page:
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "channel": "left"})

# Target a specific browser connection (cid obtained from event stream):
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "channel": "dmap", "cid": "3"})

# Target the list on the /map_list_demo page:
await _send(rpc, "list.add", {"id": "item1", "label": "Item 1", "channel": "map_list_demo-list"})
```

Internally, API handlers use PubSub for delivery and `ItemStore` for state:

- **PubSub topics** follow the pattern `{prefix}:{channel}` for broadcast or
  `{prefix}:{channel}:{cid}` for targeted delivery. Topic functions are in
  `shared/topics.py` (e.g. `marker_ops_topic()`, `map_cmd_topic()`).
- **`ItemStore[T]`** maintains shared state partitioned by channel:
  `dict[str, dict[str, T]]` (channel → {id → item}). Used for `*.list` query
  methods and initial mount snapshots. No fan-out — PubSub handles delivery.
- **Drivers** subscribe to both broadcast and targeted topics on `connect()`.
  PubSub messages arrive as `InfoEvent(name=topic, payload=data)` in `handle_info`.

#### Namespaced push_event

Server-to-client commands are namespaced with `channel` to prevent leaking
between components on the same page:

```python
# Server side (dynamic_map_demo.py / multimaps_demo.py):
event_name, payload = cmd.to_push_event(target=channel)
await socket.push_event(event_name, payload)
# → pushes "left:setView" instead of "setView"

# JS side (dynamic_map.js):
this.handleEvent(`${channel}:setView`, handler);
```

All command dataclasses accept `target` in `to_push_event(*, target="")`.

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

Data delivery uses **PyView PubSub** (`pub_sub_hub` from `pyview.live_socket`):
API handlers update `ItemStore` for shared state, then broadcast ops/commands
via `pub_sub_hub.send_all_on_topic_async(topic, payload)`. Drivers subscribe
to PubSub topics in `connect()` and process messages in `handle_info()`.
`EventBroadcaster` is still used separately for SSE event streaming to
external clients.

### Hook init ordering pitfall

`DMarkItem.mounted()` can fire before `DynamicMap.mounted()` creates the
`MapInstance`. To handle this, each `MapInstance` has `pendingMarkers` and
`pendingPolylines` arrays; hooks queue themselves there when their instance's
map isn't ready yet. `DynamicMap.mounted()` flushes all pending hooks after the
Leaflet map is created.

### JS: per-instance state (MapInstance)

Multiple maps on one page require per-instance state. `dynamic_map.js` uses a
`MapInstance` class and a global `_instances` Map keyed by channel:

```javascript
class MapInstance {
  constructor(channel) {
    this.channel = channel;
    this.map = null;              // Leaflet map
    this.markers = new Map();      // domId → L.marker
    this.polylines = new Map();    // domId → L.polyline
    this.repeatedMarkers = null;   // L.gridLayer.repeatedMarkers()
    this.followMarkerId = null;
    this.pendingMarkers = [];      // hooks queued before map init
    this.pendingPolylines = [];
    this.iconRegistry = {};
  }
}
```

Hooks find their instance via `_findInstance(el)` which walks up the DOM with
`el.closest('[data-channel]')` and looks up the instance in `_instances`.
All marker/polyline/command logic uses `instance.xxx` instead of module-level
globals. RepeatedMarkers prototype patches remain at module level.

## LatLng type

All lat/lng values use the `LatLng` dataclass (`latlng.py`) internally.
Wire format (JSON-RPC params, JS payloads) remains `[lat, lng]` arrays.

```python
from pyview_map.views.components.shared.latlng import LatLng

ll = LatLng(39.5, -98.35)
ll.to_list()  # → [39.5, -98.35]
LatLng.from_list([39.5, -98.35])  # → LatLng(lat=39.5, lng=-98.35)
```

Conversion happens at boundaries:
- **API → internal**: `marker_api.py` calls `LatLng.from_list()` on wire params
- **Browser → internal**: `dynamic_map.py` `handle_event()` converts payload lists
- **Internal → wire**: `to_dict()` / `to_push_event()` call `.to_list()`

## Map commands (client → browser)

External clients can control the browser map via `map.*` JSON-RPC methods.
The flow is:

1. **Client** calls `map.flyTo`, `map.setZoom`, etc. via JSON-RPC with `channel` (and optionally `cid`)
2. **`marker_api.py`** handler constructs a command dataclass and calls `CommandQueue.push(cmd, channel=channel, cid=cid)`
3. **`CommandQueue`** fans out the command to subscriber queues matching the `channel` and `cid`
4. **`dynamic_map.py`** parent LiveView `handle_info()` drains command queues on each tick, calling
   `socket.push_event()` with namespaced event names (e.g. `"left:setView"`)
5. **`dynamic_map.js`** namespaced `handleEvent` receivers on the `DynamicMap` hook call the corresponding
   Leaflet method on the correct `MapInstance`

Command dataclasses are defined in `map_events.py` (`SetViewCmd`, `PanToCmd`,
`FlyToCmd`, `FitBoundsCmd`, `FlyToBoundsCmd`, `SetZoomCmd`, `ResetViewCmd`,
`HighlightMarkerCmd`, `HighlightPolylineCmd`, `FollowMarkerCmd`, `UnfollowMarkerCmd`).
Each has `to_push_event(*, target="") -> tuple[str, dict]`.

Commands are delivered via PubSub: API handlers broadcast command objects on
`map-cmd:{channel}` (or `map-cmd:{channel}:{cid}`) topics. Drivers receive
them in `handle_info()` and call `socket.push_event()` immediately.

## Event streaming to external clients

Browser map/marker/list events and API operations are broadcast to external
clients via SSE using `EventBroadcaster` and the `map.events.subscribe` method.

### Architecture

1. **Browser → LiveView** — `handle_event()` in `dynamic_map.py` / `dynamic_list.py`
   receives events from hooks, constructs typed event dataclasses, and calls
   `EventBroadcaster.broadcast()`.
2. **API → broadcast** — `markers.add/update/delete`, `polylines.add/update/delete`,
   and `list.add/remove/clear` handlers broadcast events after each mutation.
3. **EventBroadcaster** — maintains a set of subscriber `asyncio.Queue`s (bounded,
   maxsize=256). `broadcast()` is non-blocking (`put_nowait`); slow consumers are
   dropped. The `JSONRPCNotification` is built once and shared across all subscribers.
4. **SSE delivery** — `map.events.subscribe` returns a queue; `mcp_router` detects
   the queue return and opens an SSE stream, sending `JSONRPCNotification` messages
   with method `notifications/map.event`.

### Event types (`map_events.py` + `list_events.py`)

All events are `@dataclass(slots=True)` for minimal allocation overhead.
Each has `to_dict()` for serialization; `parse_event()` reconstructs them
from a notification params dict.

```python
from pyview_map.views.components.shared.latlng import LatLng
from pyview_map.views.components.dynamic_map.models.map_events import (
    MarkerOpEvent, MarkerEvent, MapEvent, PolylineOpEvent, PolylineEvent,
    BroadcastEvent, parse_event,
)
from pyview_map.views.components.dynamic_list.models.list_events import ListItemOpEvent, ListItemClickEvent
```

**`MarkerOpEvent`** — marker CRUD from the API:
```python
MarkerOpEvent(op="add", id="abc", name="Alpha-01", latLng=LatLng(39.5, -98.3), channel="dmap", cid="*")
MarkerOpEvent(op="update", id="abc", name="Alpha-01", latLng=LatLng(40.0, -97.0), channel="dmap", cid="3")
MarkerOpEvent(op="delete", id="abc", channel="dmap")
# to_dict() → {"type": "marker-op", "op": ..., "id": ..., "name": ..., "latLng": [lat, lng], "channel": ..., "cid": ...}
```

**`MarkerEvent`** — browser marker interaction:
```python
MarkerEvent(event="click", id="markers-abc", name="Alpha-01", latLng=LatLng(39.5, -98.3))
# to_dict() → {"type": "marker-event", "event": ..., "id": ..., "name": ..., "latLng": [lat, lng]}
```

**`MapEvent`** — browser map interaction (now includes `bounds`):
```python
MapEvent(event="zoomend", center=LatLng(39.5, -98.3), zoom=6, latLng=None, bounds=(LatLng(30, -110), LatLng(50, -80)))
# to_dict() → {"type": "map-event", "event": ..., "center": ..., "zoom": ..., "bounds": [[sw_lat, sw_lng], [ne_lat, ne_lng]]}
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

**`ListItemOpEvent`** — list item CRUD from the API:
```python
ListItemOpEvent(op="add", id="item1", label="Airport JFK", subtitle="(40.64, -73.78)", channel="my-list", cid="*")
ListItemOpEvent(op="delete", id="item1", channel="my-list")
ListItemOpEvent(op="clear", channel="my-list")
# to_dict() → {"type": "list-item-op", "op": ..., "id": ..., "label": ..., "channel": ..., "cid": ...}
```

**`ListItemClickEvent`** — user clicked a list item:
```python
ListItemClickEvent(event="click", id="item1", label="Airport JFK", channel="my-list", cid="2")
# to_dict() → {"type": "list-item-event", "event": ..., "id": ..., "label": ..., "channel": ..., "cid": ...}
```

### Client subscription example

```python
from pyview_map.views.components.dynamic_map.models.map_events import MarkerOpEvent, MarkerEvent, MapEvent, parse_event
from pyview_map.views.components.dynamic_list.models.list_events import ListItemClickEvent

req = JSONRPCRequest(method="map.events.subscribe")
async for msg in rpc.send_request(req):
    match msg:
        case JSONRPCNotification():
            evt = parse_event(msg.params)
            match evt:
                case MarkerOpEvent():
                    ...
                case MarkerEvent():
                    ...
                case MapEvent():
                    ...
                case ListItemClickEvent():
                    ...
        case JSONRPCResponse():
            break  # end of channel
```
