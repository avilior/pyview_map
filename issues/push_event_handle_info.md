# push_event calls during handle_info are never delivered to the browser

**Repository:** https://github.com/ogrodnek/pyview

## Bug

`socket.push_event()` called inside `handle_info()` never reaches the browser. Events accumulate silently in `socket.pending_events` and are only flushed when a *user-initiated* event (e.g. `phx-click`) triggers the `handle_event` code path. This makes server-initiated push events unreliable — they appear to work only when a user happens to interact with the page shortly after.

## Root cause

There are two code paths that send WebSocket messages to the browser, and only one of them flushes `pending_events`:

**`ws_handler.py` (handle_event path) — correctly includes push events:**

```python
# ws_handler.py lines 211-222
hook_events = {} if not socket.pending_events else {"e": socket.pending_events}
diff = socket.diff(rendered)
socket.pending_events = []

resp = [
    joinRef, messageRef, topic, "phx_reply",
    {"response": {"diff": diff | hook_events}, "status": "ok"},
]
```

**`live_socket.py` (handle_info path) — does NOT include push events:**

```python
# live_socket.py lines 212-219
async def send_info(self, event: InfoEvent):
    await self.liveview.handle_info(event, self)

    rendered = await self.render_with_components()
    resp = [None, None, self.topic, "diff", self.diff(rendered)]
    #                                       ^^^^^^^^^^^^^^^^
    #              pending_events are never included or cleared

    try:
        await self.websocket.send_text(json.dumps(resp))
```

`push_event()` appends to `self.pending_events`, but `send_info()` never reads or clears that list. The events silently accumulate until the next `handle_event` response happens to flush them.

## Reproduction

Any LiveView that calls `socket.push_event()` during a scheduled tick:

```python
class MyView(LiveView[MyContext]):
    async def mount(self, socket, session):
        socket.context = MyContext()
        if socket.connected:
            socket.schedule_info(InfoEvent("tick"), seconds=1.0)

    async def handle_info(self, event, socket):
        if event.name == "tick":
            # This event never reaches the browser
            await socket.push_event("my-event", {"value": 42})
```

The JS `handleEvent("my-event", ...)` callback never fires — until the user interacts with the page (triggering `handle_event`), at which point *all* accumulated events arrive at once.

## Suggested fix

Include `pending_events` in the diff payload under the `"e"` key in `send_info()`, mirroring what `ws_handler.py` already does:

```python
async def send_info(self, event: InfoEvent):
    await self.liveview.handle_info(event, self)

    rendered = await self.render_with_components()
    diff = self.diff(rendered)

    if self.pending_events:
        diff["e"] = self.pending_events
        self.pending_events = []

    resp = [None, None, self.topic, "diff", diff]

    try:
        await self.websocket.send_text(json.dumps(resp))
    except Exception:
        for id in list(self.scheduled_jobs):
            try:
                self.scheduler.remove_job(id)
            except Exception:
                pass
```

The Phoenix LiveView JS client already handles the `"e"` key in diff messages, so no client-side changes are needed.

## Versions

- pyview-web 0.8.3
- Python 3.14
