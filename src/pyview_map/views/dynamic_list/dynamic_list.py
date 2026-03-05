import asyncio
from dataclasses import dataclass, field
from typing import Any

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.components import LiveComponent
from pyview.components.base import ComponentMeta, ComponentSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.stream import Stream
from pyview.template import TemplateView
from pyview.template.live_view_template import live_component, stream_for

from .api_list_source import APIListSource
from .dlist_item import DListItem
from pyview_map.views.dynamic_map.event_broadcaster import EventBroadcaster
from .list_command_queue import ListCommandQueue
from .list_events import ListItemClickEvent


# ---------------------------------------------------------------------------
# DynamicListComponent — renders a scrollable list with stream items
# ---------------------------------------------------------------------------

@dataclass
class DynamicListComponentContext:
    items: Stream[DListItem]
    component_id: str
    _last_version: int = 0


def _apply_list_ops(items: Stream[DListItem], ops: list[dict], *, stream_name: str = "list-items") -> None:
    """Apply a list of list operation dicts to a Stream."""
    for op_dict in ops:
        op = op_dict["op"]
        if op == "add":
            at = op_dict.get("at", -1)
            items.insert(
                DListItem(
                    id=op_dict["id"],
                    label=op_dict["label"],
                    subtitle=op_dict.get("subtitle", ""),
                ),
                at=at,
            )
        elif op == "delete":
            items.delete_by_id(f"{stream_name}-{op_dict['id']}")
        elif op == "clear":
            items.reset([])


class DynamicListComponent(LiveComponent[DynamicListComponentContext]):
    """Renders a scrollable list of items with click events.

    Lifecycle:
      - mount(): create Stream from initial items
      - update(): receive pending ops from parent, apply to Stream
      - template(): t-string with stream_for() rendering clickable items
    """

    async def mount(self, socket: ComponentSocket[DynamicListComponentContext], assigns: dict[str, Any]) -> None:
        component_id = assigns.get("component_id", "dlist")
        initial_items = assigns.get("initial_items", [])
        socket.context = DynamicListComponentContext(
            items=Stream(initial_items, name=f"{component_id}-list-items"),
            component_id=component_id,
        )

    async def update(self, socket: ComponentSocket[DynamicListComponentContext], assigns: dict[str, Any]) -> None:
        version = assigns.get("ops_version", 0)
        ctx = socket.context
        if version <= ctx._last_version:
            return
        ctx._last_version = version

        stream_name = f"{ctx.component_id}-list-items"
        _apply_list_ops(ctx.items, assigns.get("list_ops", []), stream_name=stream_name)

    async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[DynamicListComponentContext]) -> None:
        if event == "item-click":
            item_id = payload.get("id", "")
            label = payload.get("label", "")
            evt = ListItemClickEvent(event="click", id=item_id, label=label)
            EventBroadcaster.broadcast(evt)

    def template(self, assigns: DynamicListComponentContext, meta: ComponentMeta):
        component_id = assigns.component_id
        items_id = f"{component_id}-list-items"

        items_html = stream_for(assigns.items, lambda dom_id, item:
            t'<div id="{dom_id}" class="list-item px-3 py-2 cursor-pointer hover:bg-blue-50 border-b border-gray-100 transition-colors" phx-click="item-click" phx-target="{meta.myself}" phx-value-id="{item.id}" phx-value-label="{item.label}"><div class="font-medium text-sm text-gray-800">{item.label}</div><div class="text-xs text-gray-500">{item.subtitle}</div></div>'
        )

        return t"""<div data-component-id="{component_id}">
    <div id="{component_id}"
         phx-hook="DynamicList"
         class="w-full max-h-96 lg:max-h-[580px] overflow-y-auto rounded-md border border-gray-300 bg-white">
        <div id="{items_id}" phx-update="stream">
            {items_html}
        </div>
    </div>
</div>"""


# ---------------------------------------------------------------------------
# Parent LiveView — drives ticks, drains list source, embeds list component
# ---------------------------------------------------------------------------

@dataclass
class DynamicListPageContext:
    initial_items: list[DListItem] = field(default_factory=list)
    list_ops: list[dict] = field(default_factory=list)
    ops_version: int = 0


class DynamicListLiveView(TemplateView, LiveView[DynamicListPageContext]):
    """
    Standalone list page — mainly for testing the list component.

    Usage:
        app.add_live_view("/list", DynamicListLiveView)
    """

    tick_interval: float = 1.2

    async def mount(self, socket: LiveViewSocket[DynamicListPageContext], session):
        self._list_source = APIListSource()
        socket.context = DynamicListPageContext(
            initial_items=self._list_source.items,
        )
        if socket.connected:
            self._cmd_queue = ListCommandQueue.subscribe()
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DynamicListPageContext]):
        if event.name != "tick":
            return

        # Drain all pending list updates
        list_ops: list[dict] = []
        while True:
            update = self._list_source.next_update()
            if update["op"] == "noop":
                break
            list_ops.append(update)

        # Drain pending list commands
        while True:
            try:
                cmd = self._cmd_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            event_name, payload = cmd.to_push_event(target="dlist")
            await socket.push_event(event_name, payload)

        socket.context.list_ops = list_ops
        if list_ops:
            socket.context.ops_version += 1

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DynamicListPageContext]):
        socket.context.list_ops = []

    def template(self, assigns: DynamicListPageContext, meta: PyViewMeta):
        comp = live_component(DynamicListComponent, id="dlist",
            initial_items=assigns.initial_items,
            list_ops=assigns.list_ops,
            ops_version=assigns.ops_version,
            component_id="dlist",
        )

        return t"""<div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Dynamic List</h1>
        <p class="text-sm text-gray-500 mb-6">
            Items are streamed in real-time via the JSON-RPC API.
        </p>
        {comp}
    </div>
</div>"""
