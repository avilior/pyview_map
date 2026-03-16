# pyview_map

A demo app built with [PyView](https://github.com/ogrodnek/pyview) showing how to build interactive and real-time maps using [Leaflet.js](https://leafletjs.com/) and LiveView.

Uses a **BFF/BE architecture**: the PyView server (BFF) hosts LiveView pages,
while backend services push data via reverse JSON-RPC connections. See
[`docs/architecture_bff_be.md`](docs/architecture_bff_be.md) for the full design.

## Routes

| Route | Description |
|---|---|
| `/flights` | Flight simulation — live aircraft tracking with polyline routes |
| `/places_demo` | National parks list + map — click a park to fly there |
| `/api/docs` | Interactive JSON-RPC API explorer |

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) _(optional, for convenience commands)_

## Getting started

```bash
git clone https://github.com/avilior/pyview_map
cd pyview_map

just install    # uv sync --all-packages
just run        # start the BFF server
```

The BFF starts at `http://localhost:8123`. To run with a backend:

```bash
# Terminal 1 — BFF
uv run --package pyview-map pyview-map

# Terminal 2 — Parks backend (for /places_demo)
uv run --package places-backend places-backend

# Terminal 3 — Flights backend (for /flights)
uv run --package flights-backend flights-backend
```

## JSON-RPC API

The BFF exposes a JSON-RPC 2.0 endpoint at `POST /api/mcp` (MCP transport).
External clients push marker/polyline/list operations and the LiveView streams
them to all connected browsers in real time.

### API documentation

Each service auto-generates API docs from its registered method signatures:

| Endpoint | Purpose |
|---|---|
| `GET /api/docs` | Interactive HTML explorer — browse methods, params, send test requests |
| `GET /api/openrpc.json` | Machine-readable [OpenRPC 1.3.2](https://open-rpc.org/) spec |
| `rpc.discover` (via MCP) | Same spec, accessible to any MCP client |

Browse to `http://localhost:8123/api/docs` to explore the BFF's 26 methods
(markers, polylines, list, map commands). Each backend has its own docs at
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
services/
├── bff/                     # PyView BFF
│   └── src/pyview_map/
│       ├── __main__.py      # Entry point — registers routes and starts uvicorn
│       ├── app.py           # PyView app, StaticFiles mount, root template
│       ├── api.py           # FastAPI sub-app, MCP router, health endpoint
│       ├── openrpc.py       # OpenRPC spec generator + docs/discovery endpoints
│       ├── components/      # Reusable LiveComponents (dynamic_map, dynamic_list)
│       └── applications/    # Front-end pages (flights_demo, places_demo)
├── places_backend/          # Parks BE — populates /places_demo list + map
└── flights_backend/         # Flights BE — simulates flights for /flights
packages/
└── dmap_models/             # Shared wire-protocol models
```

See [`CLAUDE.md`](CLAUDE.md) for the full project layout.
