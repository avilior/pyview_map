from dataclasses import dataclass, field
from typing import Any, Callable

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.components import LiveComponent
from pyview.components.base import ComponentMeta, ComponentSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.stream import Stream
from pyview.template import TemplateView
from pyview.template.live_view_template import stream_for

from .models.dlist_item import DListItem

# Type alias for item renderers.
# A renderer receives a DListItem and returns the inner content (t-string).
# The component wraps this in the clickable container div.
ItemRenderer = Callable[[DListItem], Any]


def default_item_renderer(item: DListItem) -> Any:
    """Default renderer: label + subtitle."""
    return t'<div class="font-medium text-sm text-gray-800">{item.label}</div><div class="text-xs text-gray-500">{item.subtitle}</div>'


# ---------------------------------------------------------------------------
# DynamicListComponent — renders a scrollable list with stream items
# ---------------------------------------------------------------------------


@dataclass
class DynamicListComponentContext:
    items: Stream[DListItem]
    channel: str
    _item_renderer: ItemRenderer = field(default=default_item_renderer)
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
                    data=op_dict.get("data", {}),
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
        channel = assigns.get("channel", "dlist")
        initial_items = assigns.get("initial_items", [])
        item_renderer = assigns.get("item_renderer", default_item_renderer)
        socket.context = DynamicListComponentContext(
            items=Stream(initial_items, name=f"{channel}-list-items"), channel=channel, _item_renderer=item_renderer
        )

    async def update(self, socket: ComponentSocket[DynamicListComponentContext], assigns: dict[str, Any]) -> None:
        version = assigns.get("ops_version", 0)
        ctx = socket.context
        if version <= ctx._last_version:
            return
        ctx._last_version = version

        stream_name = f"{ctx.channel}-list-items"
        _apply_list_ops(ctx.items, assigns.get("list_ops", []), stream_name=stream_name)

    async def handle_event(
        self, event: str, payload: dict, socket: ComponentSocket[DynamicListComponentContext]
    ) -> None:
        pass  # click events bubble to parent LiveView; ListDriver handles broadcast with channel/cid

    def template(self, assigns: DynamicListComponentContext, meta: ComponentMeta):
        channel = assigns.channel
        items_id = f"{channel}-list-items"
        renderer = assigns._item_renderer

        items_html = stream_for(
            assigns.items,
            lambda dom_id, item: (
                t'<div id="{dom_id}" class="list-item px-3 py-2 cursor-pointer hover:bg-blue-50 border-b border-gray-100 transition-colors" phx-click="item-click" phx-value-id="{item.id}" phx-value-label="{item.label}">{renderer(item)}</div>'
            ),
        )

        return t"""<div data-channel="{channel}">
    <div id="{channel}"
         phx-hook="DynamicList"
         class="w-full max-h-96 lg:max-h-[580px] overflow-y-auto rounded-md border border-gray-300 bg-white">
        <div id="{items_id}" phx-update="stream">
            {items_html}
        </div>
    </div>
</div>"""


# ---------------------------------------------------------------------------
# Parent LiveView — PubSub-driven updates, embeds list component
# ---------------------------------------------------------------------------


@dataclass
class DynamicListPageContext:
    pass


class DynamicListLiveView(TemplateView, LiveView[DynamicListPageContext]):
    """
    Standalone list page — mainly for testing the list component.

    Usage:
        app.add_live_view("/list", DynamicListLiveView)
    """

    async def mount(self, socket: LiveViewSocket[DynamicListPageContext], session):
        from .list_driver import ListDriver

        self._list = ListDriver(channel="dlist")
        socket.context = DynamicListPageContext()
        if socket.connected:
            await self._list.connect(socket)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DynamicListPageContext]):
        await self._list.handle_info(event, socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DynamicListPageContext]):
        self._list.clear_ops()

    def template(self, assigns: DynamicListPageContext, meta: PyViewMeta):
        comp = self._list.render()

        return t"""<div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Dynamic List</h1>
        <p class="text-sm text-gray-500 mb-6">
            Items are streamed in real-time via the JSON-RPC API.
        </p>
        {comp}
    </div>
</div>"""
