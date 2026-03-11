from dataclasses import dataclass
from pyview.template import TemplateView
from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket
from pyview.live_view import Session
from pyview.events import InfoEvent
from pyview_map.views.components.dynamic_list import ListDriver
from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem

from pyview.meta import PyViewMeta

import logging

LOG = logging.getLogger(__name__)


def image_item_renderer(item: DListItem):
    """Render a list item as a single image."""
    src = item.data.get("image", "")
    alt = item.data.get("alt", item.label)
    return t'<img src="{src}" alt="{alt}" class="w-full h-auto rounded" />'


@dataclass
class ImageListViewContext:
    last_event: str = ""


class ImageListView(TemplateView, LiveView[ImageListViewContext]):

    base_channel: str = "image-list"
    tick_interval: float = 1.2

    async def mount(self, socket: LiveViewSocket[ImageListViewContext], session: Session):
        self._list = ListDriver(f"{self.base_channel}-list", item_renderer=image_item_renderer)
        socket.context = ImageListViewContext()

        if socket.connected:
            self._list.connect()
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[ImageListViewContext]):
        if event.name != "tick":
            return
        await self._list.tick(socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[ImageListViewContext]):
        self._list.clear_ops()
        summary = self._list.handle_event(event, payload)
        if summary:
            socket.context.last_event = summary

    async def disconnect(self, socket: ConnectedLiveViewSocket[ImageListViewContext]):
        LOG.info("disconnecting")

    def template(self, assigns: ImageListViewContext, meta: PyViewMeta):
        last_event = assigns.last_event
        list_comp = self._list.render()

        event_line = t'<div class="text-xs font-mono text-gray-600 truncate">{last_event}</div>' if last_event else t'<div class="text-xs text-gray-400">No events yet</div>'

        return t"""<div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Image List</h1>
        <p class="text-sm text-gray-500 mb-6">
            Each list item renders an image. Populated via the JSON-RPC API
            with <code>channel="{self.base_channel}-list"</code>.
        </p>
        {list_comp}
        <div class="border-t border-gray-200 pt-3 mt-4">
            {event_line}
        </div>
    </div>
</div>"""
