# pyview_map

A demo app built with [PyView](https://github.com/ogrodnek/pyview) showing how to build interactive and real-time maps using [Leaflet.js](https://leafletjs.com/) and LiveView.

## Views

### `/map` — National Park Planner
A static Leaflet map with a sidebar of US national parks. Clicking a park pans the map and opens a popup. Demonstrates bidirectional LiveView events: client → server (`phx-click`) and server → client (`push_event`).

### `/dmap` — Dynamic Marker Map
A real-time tracking map where markers stream in from the server — appearing, moving, and disappearing continuously. Features a day/night terminator overlay and a live activity log. All Leaflet marker and map events are forwarded to the server.

`/dmap` is built as a **generic framework**: it knows nothing about where markers come from. A `MarkerSource` provides the data; the included `MockGenerator` is one example that simulates moving vehicles. See [Plugging in a custom data source](#plugging-in-a-custom-data-source) below.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) _(optional, for convenience commands)_

## Getting started

```bash
git clone https://github.com/avilior/pyview_map
cd pyview_map

just install   # uv sync
just dmap      # start server and open /dmap in the browser
```

Other just commands:

```
just run       # start the server
just stop      # stop the server
just open-map  # open /map in the browser
just open-dmap # open /dmap in the browser
```

## How the streaming map works

Each marker is a `DMarker` dataclass with an `id`, `name`, and `lat_lng`. On every tick the source returns one operation and the server mutates a `Stream[DMarker]`. PyView sends only the diff over the WebSocket; the JS hook lifecycle drives Leaflet directly.

```
Server                               Client
──────                               ──────
source.next_update()
  → stream.insert(marker)        ──▶  DMarkItem.mounted()   → L.marker().addTo(map)
  → stream.insert(update_only)   ──▶  DMarkItem.updated()   → marker.setLatLng()
  → stream.delete_by_id()        ──▶  DMarkItem.destroyed() → marker.remove()

Leaflet event (click, drag, zoom…)
                                 ──▶  pushEvent("marker-event" | "map-event")
                                 ──▶  handle_event() on server
```

The server never holds the full marker list in memory after the initial mount — only pending stream operations are tracked. The client DOM is the source of truth.

## Plugging in a custom data source

Implement the `MarkerSource` protocol and register it with `with_source()`:

```python
from pyview_map.views.dynamic_map.dynamic_map import DMarker

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
        ...
```

Register in `__main__.py`:

```python
app.add_live_view("/mymap", DynamicMapLiveView.with_source(MySource))

# Pass constructor kwargs and override the tick interval (seconds):
app.add_live_view("/fleet", DynamicMapLiveView.with_source(FleetTracker, tick_interval=2.0, fleet_id=42))
```

`MockGenerator` in `mock_generator.py` is a reference implementation — read it as a starting point.

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
        ├── mock_generator.py       # Example MarkerSource — simulates moving vehicles
        └── static/dynamic_map.js
```

See [`CLAUDE.md`](CLAUDE.md) for development conventions and deeper implementation notes.
