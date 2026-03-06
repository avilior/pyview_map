# pyview_map

A demo app built with [PyView](https://github.com/ogrodnek/pyview) showing how to build interactive and real-time maps using [Leaflet.js](https://leafletjs.com/) and LiveView.

## Views

### `/map` — National Park Planner
A static Leaflet map with a sidebar of US national parks. Clicking a park pans the map and opens a popup. Demonstrates bidirectional LiveView events: client → server (`phx-click`) and server → client (`push_event`).

### `/dmap` — Dynamic Marker Map
A real-time tracking map where markers stream in from the server — appearing, moving, and disappearing continuously. Features a day/night terminator overlay and a live activity log. All Leaflet marker and map events are forwarded to the server.

`/dmap` is built as a **generic framework**: it knows nothing about where markers come from. Implement the `MarkerSource` protocol to feed any data in. The default setup uses `APIMarkerSource`, which receives marker updates from external clients via a **JSON-RPC HTTP API** mounted at `/api/rpc`.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) _(optional, for convenience commands)_

## Getting started

```bash
git clone https://github.com/avilior/pyview_map
cd pyview_map

just install    # uv sync
just dmap       # start server and open /dmap in the browser
just mock-run   # (separate terminal) start the mock client — markers appear on the map
```

Other just commands:

```
just run        # start the server
just stop       # stop the server
just mock-stop  # stop the mock client
just open-map   # open /map in the browser
just open-dmap  # open /dmap in the browser
```

## JSON-RPC API

The server exposes a JSON-RPC 2.0 endpoint at `POST /api/rpc`. External clients push marker operations and the LiveView streams them to all connected browsers in real time.

### Methods

| Method | Params | Description |
|---|---|---|
| `markers.add` | `id`, `name`, `latLng` | Add a new marker |
| `markers.update` | `id`, `name`, `latLng` | Move / rename a marker |
| `markers.delete` | `id` | Remove a marker |
| `markers.list` | — | Return all current markers |

### Example

```bash
curl -X POST http://localhost:8123/api/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"markers.add","params":{"id":"hq","name":"HQ","latLng":[40.7,-74.0]},"id":1}'
```

### Mock client

`examples/mock_client.py` is a reference external client. It seeds markers and moves them using the same physics as `MockGenerator`, but drives them over HTTP instead of running in-process:

```bash
uv run python examples/mock_client.py
```

Or use `just mock-run` which also ensures the server is running and opens the browser first.

## How the streaming map works

Each marker is a `DMarker` dataclass with an `id`, `name`, and `lat_lng`. On every tick the source returns one operation and the server mutates a `Stream[DMarker]`. PyView sends only the diff over the WebSocket; the JS hook lifecycle drives Leaflet directly.

```
External client                      Server                               Browser
───────────────                      ──────                               ───────
POST /api/rpc markers.add
                               APIMarkerSource._queue
                                 source.next_update()
                                   → stream.insert()        ──▶  DMarkItem.mounted()   → L.marker().addTo(map)
                                   → stream.insert(update)  ──▶  DMarkItem.updated()   → marker.setLatLng()
                                   → stream.delete_by_id()  ──▶  DMarkItem.destroyed() → marker.remove()

                                                            Leaflet event (click, drag…)
                                                                                 ──▶  pushEvent("marker-event")
                                                                                 ──▶  handle_event() on server
```

## Plugging in a custom data source

Implement the `MarkerSource` protocol and register it with `with_source()`:

```python
from pyview_map.views.components.dynamic_map.dynamic_map_component import DMarker


class MySource:
    @property
    def markers(self) -> list[DMarker]:
        """Initial markers shown on mount."""
        return [DMarker(id="hq", name="HQ", lat_lng=[40.7, -74.0])]

    def next_update(self) -> dict:
        """Called on every tick. Return one operation."""
        # {"op": "add",    "id": str, "name": str, "latLng": [lat, lng]}
        # {"op": "delete", "id": str}
        # {"op": "update", "id": str, "name": str, "latLng": [lat, lng]}
        # {"op": "noop"}   ← return this when there is nothing to do
        ...
```

Register in `__main__.py`:

```python
app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))

# Pass constructor kwargs and override the tick interval (seconds):
app.add_live_view("/fleet", DynamicMapLiveView.with_source(FleetTracker, tick_interval=2.0, fleet_id=42))
```

`MockGenerator` in `mock_generator.py` and `APIMarkerSource` in `api_marker_source.py` are both reference implementations.

## Project structure

```
src/pyview_map/
├── app.py                          # PyView app + root template (Tailwind, Leaflet, Terminator CDN)
├── __main__.py                     # Entry point — registers routes and starts uvicorn
└── views/
    ├── maps/                       # /map
    │   ├── map.py
    │   ├── map.html
    │   ├── parks.py
    │   └── static/map.js
    └── dynamic_map/                # /dmap
        ├── dynamic_map.py          # DynamicMapLiveView (generic) + MarkerSource protocol
        ├── dynamic_map.html
        ├── mock_generator.py       # In-process MarkerSource — simulates moving vehicles
        ├── api_marker_source.py    # MarkerSource backed by a class-level asyncio.Queue
        ├── marker_api.py           # FastAPI sub-app — JSON-RPC 2.0 endpoint at /api/rpc
        └── static/dynamic_map.js
examples/
└── mock_client.py                  # Reference external client — drives /dmap via JSON-RPC
```

See [`CLAUDE.md`](CLAUDE.md) for development conventions and deeper implementation notes.
