# JSON-RPC API Reference

API endpoint: `POST /api/mcp`

## Authentication

All requests require a Bearer token:
```
Authorization: Bearer tok-acme-001
```

Pre-configured mock tokens: `tok-acme-001` (Acme Corp), `tok-globex-002`, `tok-initech-003`.

## MCP handshake

Clients must complete the MCP lifecycle before calling methods:
1. `GET /api/health` — liveness check
2. `POST /api/mcp` — send `initialize` request → receive session ID
3. `POST /api/mcp` — send `notifications/initialized` notification
4. `POST /api/mcp` — call methods with `Mcp-Session-Id` header

`ClientRPC` from `http_stream_client` handles this automatically via `async with`.

## API documentation and discovery

Each service (BFF, Parks BE, Flights BE) auto-generates API docs from registered JRPC methods.

| Endpoint | Purpose |
|---|---|
| `GET /api/docs` | Interactive HTML explorer — browse methods, view params, send test requests |
| `GET /api/openrpc.json` | Machine-readable OpenRPC 1.3.2 spec |
| `rpc.discover` (via MCP) | Same spec, accessible to any MCP client |

## Marker methods

| Method | Params | Effect |
|---|---|---|
| `markers.add` | `id`, `name`, `latLng`, `channel`, `cid?` | Add marker; enqueue `add` op; broadcast `MarkerOpEvent` |
| `markers.update` | `id`, `name`, `latLng`, `channel`, `cid?` | Move/rename marker; enqueue `update` op; broadcast `MarkerOpEvent` |
| `markers.delete` | `id`, `channel`, `cid?` | Remove marker; enqueue `delete` op; broadcast `MarkerOpEvent` |
| `markers.list` | `channel` | Return current `_markers` dict for channel |
| `map.events.subscribe` | — | Returns `asyncio.Queue` → SSE stream of `JSONRPCNotification` events |

## Polyline methods

| Method | Params | Effect |
|---|---|---|
| `polylines.add` | `id`, `name`, `path`, `channel`, `color?`, `weight?`, `opacity?`, `dashArray?`, `cid?` | Add polyline |
| `polylines.update` | `id`, `name`, `path`, `channel`, `color?`, `weight?`, `opacity?`, `dashArray?`, `cid?` | Update polyline |
| `polylines.delete` | `id`, `channel`, `cid?` | Remove polyline |
| `polylines.list` | `channel` | Return current polylines for channel |

`path` is an array of `[lat, lng]` arrays. Polylines crossing the antimeridian (±180°) are automatically unwrapped in JS.

## List methods

| Method | Params | Effect |
|---|---|---|
| `list.add` | `id`, `label`, `channel`, `subtitle?`, `at?` (-1=bottom, 0=top), `data?`, `cid?` | Add item at position |
| `list.remove` | `id`, `channel`, `cid?` | Remove item by id |
| `list.clear` | `channel`, `cid?` | Remove all items |
| `list.highlight` | `id`, `channel`, `cid?` | Push highlight command (scroll + flash) |
| `list.list` | `channel` | Return current items for channel |
| `list.events.subscribe` | — | Returns `asyncio.Queue` → SSE stream of list events |

## Map command methods

| Method | Params | JS effect |
|---|---|---|
| `map.setView` | `latLng`, `zoom`, `channel`, `cid?` | `map.setView(latLng, zoom)` |
| `map.panTo` | `latLng`, `channel`, `cid?` | `map.setView(latLng, currentZoom)` |
| `map.flyTo` | `latLng`, `zoom`, `channel`, `cid?` | `map.flyTo(latLng, zoom)` (animated) |
| `map.fitBounds` | `corner1`, `corner2`, `channel`, `cid?` | `map.fitBounds([corner1, corner2])` |
| `map.flyToBounds` | `corner1`, `corner2`, `channel`, `cid?` | `map.flyToBounds([corner1, corner2])` (animated) |
| `map.setZoom` | `zoom`, `channel`, `cid?` | `map.setZoom(zoom)` |
| `map.resetView` | `channel`, `cid?` | Reset to US overview `[39.5, -98.35]` zoom 4 |
| `map.highlightMarker` | `id`, `channel`, `cid?` | Pan to marker and open its tooltip |
| `map.highlightPolyline` | `id`, `channel`, `cid?` | Fit bounds to polyline and open its tooltip |
| `map.followMarker` | `id`, `channel`, `cid?` | Auto-pan to marker on every update |
| `map.unfollowMarker` | `channel`, `cid?` | Stop auto-panning |

All `latLng`/`corner` params are `[lat, lng]` arrays on the wire.

## `channel` and `cid` routing

- **`channel`** (required) — routing group (e.g. `"dmap"`, `"left"`, `"places-map"`). Fully isolated per channel.
- **`cid`** (optional, default `"*"`) — channel instance ID. `"*"` broadcasts to all instances. A specific cid targets one connection.

```python
# Broadcast to all instances of channel:
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "channel": "dmap"})

# Target a specific map:
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "channel": "left"})

# Target a specific browser connection:
await _send(rpc, "markers.add", {"id": "m1", "name": "HQ", "latLng": [40.7, -74.0], "channel": "dmap", "cid": "3"})
```

## Event types

All events are `@dataclass(slots=True)` with `to_dict()` for serialization and `parse_event()`/`parse_list_event()` for deserialization.

| Event | Type field | Source | Key fields |
|---|---|---|---|
| `MarkerOpEvent` | `marker-op` | API CRUD | `op`, `id`, `name`, `latLng`, `channel`, `cid` |
| `MarkerEvent` | `marker-event` | Browser interaction | `event`, `id`, `name`, `latLng` |
| `MapEvent` | `map-event` | Browser interaction | `event`, `center`, `zoom`, `latLng?`, `bounds?` |
| `PolylineOpEvent` | `polyline-op` | API CRUD | `op`, `id`, `name`, `path`, `channel`, `cid` |
| `PolylineEvent` | `polyline-event` | Browser interaction | `event`, `id`, `name`, `latLng` |
| `ListItemOpEvent` | `list-item-op` | API CRUD | `op`, `id`, `label`, `channel`, `cid` |
| `ListItemClickEvent` | `list-item-event` | Browser click | `event`, `id`, `label`, `channel`, `cid` |
| `ListReadyEvent` | `list-ready` | Component mount | `channel`, `cid` |
| `MapReadyEvent` | `map-ready` | Component mount | `channel`, `cid` |

### Client subscription example

```python
req = JSONRPCRequest(method="map.events.subscribe")
async for msg in rpc.send_request(req):
    match msg:
        case JSONRPCNotification():
            evt = parse_event(msg.params)
            match evt:
                case MarkerOpEvent(): ...
                case MarkerEvent(): ...
                case MapEvent(): ...
        case JSONRPCResponse():
            break
```

## Follow-marker (continuous tracking)

`map.followMarker(id)` auto-pans the map on every marker update in the same rendering frame.

**Do not use `map.panTo` for continuous tracking** — `push_event`-based view changes aren't reliably repainted by browsers without user interaction (Leaflet/browser compositor issue). `map.panTo` is for one-shot pans triggered by user action.

```python
await _send(rpc, "map.followMarker", {"id": "plane1"})  # start
await _send(rpc, "map.unfollowMarker", {})               # stop
await _send(rpc, "map.followMarker", {"id": "plane2"})   # switch target
```
