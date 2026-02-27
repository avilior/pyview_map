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
    │   ├── map.html     # Jinja2 template
    │   ├── map.css
    │   ├── parks.py     # Static park data
    │   └── static/
    │       └── map.js   # ParksMap class + Hooks.ParksMap
    └── dynamic_map/     # /dmap — Real-time streaming marker map
        ├── dynamic_map.py        # LiveView class + background streaming task
        ├── dynamic_map.html
        ├── dynamic_map.css
        ├── mock_generator.py     # MockGenerator — simulates marker motion
        └── static/
            └── dynamic_map.js    # DynamicMap class + Hooks.DynamicMap
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
- **Initial data → template** — pass data via context in `mount()`; render it with `{{ value|json_encode }}` for JS consumption.
- **Server → client events** — use `await socket.push_event("event-name", payload)` from `handle_event()` or a background task.
- **Client → server events** — wire `phx-click` / `phx-value-*` in the template; handle in `handle_event()`.
- **Map DOM stability** — wrap the Leaflet `div` in `phx-update="ignore"` so LiveView diffs don't touch it.
- **Background streaming** — start an `asyncio.create_task()` in `mount()`; catch exceptions to detect disconnect.
- **`json_encode` filter** — registered globally via `@filters.register` (from `pyview.vendor.ibis`); available in all templates.