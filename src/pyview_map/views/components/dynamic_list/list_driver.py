import asyncio

from pyview.template.live_view_template import live_component

from .sources.api_list_source import APIListSource
from .sources.list_command_queue import ListCommandQueue
from .dynamic_list import DynamicListComponent
from pyview_map.views.components.shared.event_broadcaster import EventBroadcaster
from .models.list_events import ListItemClickEvent


class ListDriver:
    """Encapsulates all parent-side plumbing for hosting a DynamicListComponent.

    A page developer only needs to call connect(), tick(), clear_ops(),
    handle_event(), and render() — no sources, queues, or ops tracking.

    Usage::

        class MyPageView(TemplateView, LiveView[MyContext]):
            async def mount(self, socket, session):
                self._list = ListDriver("my-list")
                socket.context = MyContext()
                if socket.connected:
                    self._list.connect()
                    socket.schedule_info(InfoEvent("tick"), seconds=1.2)

            async def handle_info(self, event, socket):
                if event.name == "tick":
                    await self._list.tick(socket)

            async def handle_event(self, event, payload, socket):
                self._list.clear_ops()
                summary = self._list.handle_event(event, payload)
                if summary:
                    socket.context.last_event = summary

            def template(self, assigns, meta):
                return t'<div>{self._list.render()}</div>'
    """

    def __init__(self, component_id: str):
        self._component_id = component_id
        self._list_source = APIListSource(component_id=component_id)
        self._initial_items = self._list_source.items
        self._list_ops: list[dict] = []
        self._ops_version: int = 0
        self._cmd_queue: asyncio.Queue | None = None

    def connect(self):
        """Subscribe to ListCommandQueue. Call when socket.connected."""
        self._cmd_queue = ListCommandQueue.subscribe(component_id=self._component_id)

    async def tick(self, socket):
        """Drain list source + command queue. Push commands via socket. Call from handle_info("tick")."""
        # Drain list updates
        list_ops: list[dict] = []
        while True:
            update = self._list_source.next_update()
            if update["op"] == "noop":
                break
            list_ops.append(update)

        # Drain commands → push_event
        if self._cmd_queue is not None:
            while True:
                try:
                    cmd = self._cmd_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                event_name, payload = cmd.to_push_event(target=self._component_id)
                await socket.push_event(event_name, payload)

        self._list_ops = list_ops
        if list_ops:
            self._ops_version += 1

    def clear_ops(self):
        """Clear stale ops so component doesn't re-apply. Call at start of handle_event."""
        self._list_ops = []

    def handle_event(self, event: str, payload: dict) -> str | None:
        """Parse item-click events, broadcast, return summary or None."""
        if event == "item-click":
            item_id = payload.get("id", "")
            label = payload.get("label", "")
            evt = ListItemClickEvent(event="click", id=item_id, label=label)
            EventBroadcaster.broadcast(evt)
            return f"click → {label}"
        return None

    def render(self):
        """Return live_component() call with current state."""
        return live_component(DynamicListComponent, id=self._component_id,
            initial_items=self._initial_items,
            list_ops=self._list_ops,
            ops_version=self._ops_version,
            component_id=self._component_id,
        )
