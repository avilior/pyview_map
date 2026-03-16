# pyview_map

A demo app built with [PyView](https://github.com/ogrodnek/pyview) showing how to build interactive and real-time maps using [Leaflet.js](https://leafletjs.com/) and LiveView.

Uses a **BFF/BE architecture**: each app has its own PyView BFF that hosts LiveView pages,
while backend services push data via reverse JSON-RPC connections. Shared components
live in the `bff-engine` package. See
[`docs/architecture_bff_be.md`](docs/architecture_bff_be.md) for the full design.

## Routes

| Route | BFF | Port | Description |
|---|---|---|---|
| `/flights` | flights-bff | 8123 | Flight simulation — live aircraft tracking with polyline routes |
| `/places_demo` | places-bff | 8124 | National parks list + map — click a park to fly there |
| `/api/docs` | each BFF | — | Interactive JSON-RPC API explorer |

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) _(optional, for convenience commands)_

## Getting started

```bash
git clone https://github.com/avilior/pyview_map
cd pyview_map

just install    # uv sync --all-packages
just all        # start both BEs + both BFFs, open browser
```

Or run individual apps:

```bash
just flights    # Flights BE + Flights BFF → opens /flights
just places     # Parks BE + Places BFF → opens /places_demo
```

Or run services individually:

```bash
# Terminal 1 — Flights BFF
uv run --package flights-bff flights-bff

# Terminal 2 — Flights backend
uv run --package flights-backend flights-backend

# Terminal 3 — Places BFF
uv run --package places-bff places-bff

# Terminal 4 — Parks backend
uv run --package places-backend places-backend
```

## JSON-RPC API

Each BFF exposes a JSON-RPC 2.0 endpoint at `POST /api/mcp` (MCP transport).
External clients push marker/polyline/list operations and the LiveView streams
them to all connected browsers in real time.

### API documentation

Each service auto-generates API docs from its registered method signatures:

| Endpoint | Purpose |
|---|---|
| `GET /api/docs` | Interactive HTML explorer — browse methods, params, send test requests |
| `GET /api/openrpc.json` | Machine-readable [OpenRPC 1.3.2](https://open-rpc.org/) spec |
| `rpc.discover` (via MCP) | Same spec, accessible to any MCP client |

Browse to `http://localhost:8123/api/docs` (flights) or `http://localhost:8124/api/docs` (places)
to explore the available methods. Each backend has its own docs at
`:8200/api/docs` and `:8300/api/docs`.

### Authentication

All requests to `/api/mcp` require a Bearer token:
```
Authorization: Bearer tok-acme-001
```

Pre-configured mock tokens: `tok-acme-001` (Acme Corp), `tok-globex-002`, `tok-initech-003`.

### Methods overview

| Namespace | Methods | Description |
|---|---|---|
| `markers.*` | add, update, delete, list | Marker CRUD on the map |
| `polylines.*` | add, update, delete, list | Polyline CRUD on the map |
| `map.*` | setView, panTo, flyTo, fitBounds, flyToBounds, setZoom, resetView, highlightMarker, highlightPolyline, followMarker, unfollowMarker | Browser map control |
| `list.*` | add, remove, clear, highlight, list | List component CRUD |
| `bff.subscribe` | — | SSE stream of all events |
| `list.subscribe` | — | SSE stream of list events |

See [`CLAUDE.md`](CLAUDE.md) for full parameter details, architecture docs, and development conventions.

## Project structure

```
packages/
├── dmap_models/             # Shared wire-protocol models
└── bff_engine/              # Shared BFF engine — components, drivers, API/app factories
    └── src/bff_engine/
        ├── bff_app.py       # create_app() factory
        ├── bff_api.py       # create_api() factory
        ├── shared/          # Shared utilities (cid, event_broadcaster, item_store, topics)
        ├── dynamic_map/     # Map LiveComponent + MapDriver + API
        └── dynamic_list/    # List LiveComponent + ListDriver + API
services/
├── flights_bff/             # Flights BFF (port 8123)
├── places_bff/              # Places BFF (port 8124)
├── places_backend/          # Parks BE — populates /places_demo list + map
└── flights_backend/         # Flights BE — simulates flights for /flights
```

See [`CLAUDE.md`](CLAUDE.md) for the full project layout.
