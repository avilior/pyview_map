# pyview_map

A PyView LiveView demo app showing interactive Leaflet.js maps.

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
        ├── mock_generator.py     # MockGenerator — in-process MarkerSource (heading/speed simulation)
        ├── api_marker_source.py  # APIMarkerSource — MarkerSource backed by asyncio.Queue (API-driven)
        ├── marker_api.py         # FastAPI sub-app — JSON-RPC 2.0 endpoint at /api/rpc
        └── static/
            └── dynamic_map.js    # Hooks.DynamicMap (map init) + Hooks.DMarkItem (lifecycle)
examples/
└── mock_client.py               # Reference external client — drives /dmap via JSON-RPC HTTP
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

class MySource:                          # no need to inherit — duck typing
    @property
    def markers(self) -> list[DMarker]:
        """Called once on mount to populate the initial map state."""
        return [DMarker(id="1", name="HQ", lat_lng=[40.7, -74.0])]

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
from pyview_map.views.dynamic_map import DynamicMapLiveView
from myapp.sources import MySource

app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))

# Pass constructor kwargs and override the tick interval (seconds):
app.add_live_view("/fleet", DynamicMapLiveView.with_source(FleetTracker, tick_interval=2.0, fleet_id=42))
```

`MockGenerator` in `mock_generator.py` is an in-process reference implementation.
`APIMarkerSource` in `api_marker_source.py` is the default source used by `/dmap` —
it receives operations from the JSON-RPC API and queues them for the LiveView tick.

## JSON-RPC API (`/api/rpc`)

`marker_api.py` mounts a FastAPI sub-app at `/api` with a single `POST /rpc` endpoint
that speaks JSON-RPC 2.0. It is mounted in `__main__.py`:

```python
app.mount("/api", api_app)
```

### Methods

| Method | Params | Effect |
|---|---|---|
| `markers.add` | `id`, `name`, `latLng` | Add marker; enqueue `add` op |
| `markers.update` | `id`, `name`, `latLng` | Move/rename marker; enqueue `update` op |
| `markers.delete` | `id` | Remove marker; enqueue `delete` op |
| `markers.list` | — | Return current `_markers` dict |

`APIMarkerSource` uses **class-level** state (`_queue`, `_markers`) so all LiveView
connections share the same queue — every connected browser sees every update.

### Hook init ordering pitfall

`DMarkItem.mounted()` can fire before `DynamicMap.mounted()` sets `_map` (Phoenix
LiveView processes the `phx-update="stream"` container before the
`phx-update="ignore"` wrapper). To handle this, `dynamic_map.js` queues pending
hooks in `_pending[]` and flushes them inside `DynamicMap.mounted()` after `_map`
is created.
