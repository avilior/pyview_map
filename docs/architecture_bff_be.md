# Architecture: FE / BFF / BE Mapping

## The Three Actors

```
┌──────────┐    WebSocket/LiveView    ┌──────────┐    JSON-RPC/MCP    ┌──────────┐
│    FE    │◄────────────────────────►│   BFF    │◄──────────────────►│    BE    │
│ Browser  │                          │ PyView   │                    │ Parks    │
│          │                          │ Server   │                    │ Service  │
└──────────┘                          └──────────┘                    └──────────┘
```

### FE — Browser

Pure presentation. Renders the Leaflet map and list via LiveView hooks.
Captures user interactions (clicks, zooms) and sends them upstream. No domain
knowledge.

### BE — Parks Service (`parks_service.py`)

The domain layer. Owns the data (national parks), owns the business rules
("when user clicks a park, fly the map there and add a marker"). It's the
source of truth and the decision-maker.

### BFF — PyView Server (`places_demo.py`)

Sits between the browser and the backend:

- **Adapts protocols** — translates between WebSocket/LiveView (what the browser
  speaks) and JSON-RPC (what the backend speaks)
- **Owns no domain logic** — doesn't know what a park is, doesn't decide what
  happens on click
- **Provides rendering infrastructure** — list component, map component, streams,
  ticking
- **Shapes data for the frontend** — the `parks_item_renderer`, the layout
  template, the Tailwind styling

The telltale sign that `places_demo.py` is a BFF and not a BE: it has zero
business logic. Its `handle_event` just broadcasts events outward. It doesn't
react to them itself. All the "what should happen" decisions live in
`parks_service.py`.

## Client/Server Inversion

In the classical BFF pattern, the BFF is the **client** — it calls the BE's API
on behalf of the frontend:

```
Classical:
  Browser → BFF → BE
            client  server

  BFF calls BE's API to fetch/mutate data on behalf of the frontend.
```

In this system it's **inverted**:

```
This system:
  Browser → BFF ← BE
            server  client

  BE connects to BFF's API and pushes data into it.
```

The PyView server (BFF) hosts `/api/mcp`. The Parks Service (BE) initiates the
connection, calls `list.add`, subscribes to events. The BE is the client in
transport terms.

This inversion means the domain authority (BE) is dialing into the presentation
layer (BFF), not the other way around.

## Data Flow Example: List Click

```
1. User clicks "Yellowstone" in browser                          (FE)
2. Browser → phx-click → PlacesView.handle_event()              (FE → BFF)
3. EventBroadcaster → SSE → parks_service event_listener()      (BFF → BE)
4. parks_service looks up Yellowstone's LatLng in its own data   (BE)
5. parks_service → JSON-RPC → map.setView(latLng, zoom=12)      (BE → BFF)
6. CommandQueue → PlacesView tick → socket.push_event()          (BFF)
7. Browser Leaflet map flies to Yellowstone                      (BFF → FE)
```

The round-trip through the external process is intentional — it keeps the
domain logic (what to do when a park is clicked) in the service that owns the
data, not in the rendering layer.

## Startup Sequence

```
1. PyView server starts → /api/mcp is live, but the list and map are empty
2. Parks Service starts → connects to /api/mcp, completes MCP handshake
3. Parks Service calls list.add × N → PyView fans out to browser → list populates
4. Parks Service subscribes to events → SSE stream opens
5. User clicks a list item → event flows back to Parks Service
6. Parks Service calls markers.add + map.setView → marker appears, map pans
```

The UI is a passive rendering surface — it has no idea what parks are or where
they are. It just knows how to display list items and map markers. The Parks
Service decides what to show and how to react to user actions.

## API Discovery

Each service exposes auto-generated API documentation:

| Service | Docs URL | Spec URL |
|---|---|---|
| BFF (`:8123`) | `/api/docs` | `/api/openrpc.json` |
| Parks BE (`:8200`) | `/api/docs` | `/api/openrpc.json` |
| Flights BE (`:8300`) | `/api/docs` | `/api/openrpc.json` |

The spec is also available via the `rpc.discover` JSON-RPC method (MCP clients).
Each service's spec only includes that service's own methods — the BFF shows
marker/polyline/list/map commands, while each BE shows its subscribe + list methods.