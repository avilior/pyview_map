# pyview_map

A demo app built with [PyView](https://github.com/ogrodnek/pyview) showing how to build interactive and real-time maps using [Leaflet.js](https://leafletjs.com/) and LiveView.

## Views

### `/map` — National Park Planner
A static Leaflet map with a sidebar of US national parks. Clicking a park pans the map and opens a popup. Demonstrates bidirectional LiveView events: client → server (`phx-click`) and server → client (`push_event`).

### `/dmap` — Dynamic Marker Map
A real-time tracking map where markers are streamed from the server. Markers appear, move, and disappear continuously. Demonstrates pyview's `Stream` API — the server mutates a `Stream[DMarker]` on each tick and pyview sends only the diff over the WebSocket. An activity log on the left shows each event as it arrives.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) _(optional, for convenience commands)_

## Getting started

```bash
git clone https://github.com/avilior/pyview_map
cd pyview_map

just install   # uv sync
just run       # uv run pyview-map
```

Then open [http://localhost:8123/map](http://localhost:8123/map) or [http://localhost:8123/dmap](http://localhost:8123/dmap).

## How the streaming map works

Each marker is a `DMarker` dataclass with an `id`, `name`, and `lat_lng`.  A `MockGenerator` simulates motion — each marker has a heading and speed and bounces off the continental US bounding box.

```
Server                              Client
──────                              ──────
MockGenerator.next_update()
  → stream.insert(marker)       ──▶  DMarkItem.mounted()   → L.marker().addTo(map)
  → stream.insert(update_only)  ──▶  DMarkItem.updated()   → marker.setLatLng()
  → stream.delete_by_id()       ──▶  DMarkItem.destroyed() → marker.remove()
```

The server never holds the full marker list in memory after the initial mount — only pending stream operations are tracked. The client DOM is the source of truth.

## Project structure

```
src/pyview_map/
├── app.py                          # PyView app + root template
├── __main__.py                     # Entry point
└── views/
    ├── maps/                       # /map
    │   ├── map.py
    │   ├── map.html
    │   ├── parks.py
    │   └── static/map.js
    └── dynamic_map/                # /dmap
        ├── dynamic_map.py
        ├── dynamic_map.html
        ├── mock_generator.py
        └── static/dynamic_map.js
```

See [`CLAUDE.md`](CLAUDE.md) for development conventions.