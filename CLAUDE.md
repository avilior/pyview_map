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
    └── dynamic_map/     # /dmap — Real-time streaming marker map
        ├── dynamic_map.py        # LiveView class — Stream[DMarker] context, schedule_info tick
        ├── dynamic_map.html      # phx-update="stream" sentinel divs + phx-update="ignore" map
        ├── dynamic_map.css
        ├── mock_generator.py     # MockGenerator — heading/speed motion simulation
        └── static/
            └── dynamic_map.js    # Hooks.DynamicMap (map init) + Hooks.DMarkItem (lifecycle)
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
