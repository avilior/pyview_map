# PyView Framework Research

## What It Is
- Python web framework inspired by Phoenix LiveView (Elixir)
- Server-side rendered HTML with WebSocket for real-time updates
- All business logic stays on the server — no JavaScript required
- Reuses Phoenix LiveView's JavaScript client library
- Built on Starlette (ASGI)
- Package: `pyview-web` on PyPI (v0.8.3, Jan 2026)
- MIT Licensed, early development stage

## Installation
```bash
uv add pyview-web
# or
pip install pyview-web
```

Cookiecutter template: `cookiecutter gh:ogrodnek/pyview-cookiecutter`

## Core Architecture
```
Browser                              Server (Python/Starlette)
──────                              ──────────────────────────
HTML Page
  │
  ├─ phx-click ──────────────────> LiveView Class
  ├─ phx-change                      │
  └─ phx-submit ─────────────────>   ├─ handle_event()
                                     ├─ Update context (state)
                                     ├─ Re-render template
                                     └─ Send HTML diff ──────> WebSocket (only changes)
```

## Lifecycle
1. **mount()** — initialize component state (dict or Pydantic model in `socket.context`)
2. **render()** — convert state to HTML via Jinja2 templates
3. **handle_event()** — user interactions trigger server-side async handlers via WebSocket
4. **handle_info()** — async server-side events pushed to the LiveView (for streaming)

## Key Features

### Streams (efficient list rendering)
- `phx-update="stream"` on container element
- Only delta operations sent (insert/delete/move), not entire list
- Perfect for chat message lists

### PubSub
- `socket.subscribe("topic")` in mount
- `broadcast("topic", data)` to send to all subscribers
- Useful for multi-tab sync

### handle_info / send_info
- Mechanism for pushing async updates from background tasks
- Background asyncio task calls `socket.send_info(event)` → triggers `handle_info(event, socket)`
- This is how streaming tokens will be pushed to the chat UI

### User Input
- `phx-submit="event_name"` on forms
- `phx-click="event_name"` on buttons
- `phx-change="event_name"` on inputs
- `phx-value-*` attributes for passing data

## Project Structure Convention
```
my_app/
├── app.py              # Starlette app + routes
├── views/
│   └── my_view.py      # LiveView classes
├── templates/
│   ├── root.html       # Base layout
│   └── my_view.html    # View templates
├── static/
│   └── css/
└── pyproject.toml
```

## Routing
```python
from starlette.applications import Starlette
from starlette.routing import Route
from pyview import live

app = Starlette(routes=[
    Route("/", endpoint=live(ChatLiveView)),
])
```

## Examples
- Counter, AI Chat, File Upload, Streams, Kanban, Presence Tracking
- AI Chat example: `pyview-example-ai-chat` (demonstrates streaming chat)
- Examples site: https://examples.pyview.rocks/

## GitHub
- https://github.com/ogrodnek/pyview
- 113 stars, actively maintained
