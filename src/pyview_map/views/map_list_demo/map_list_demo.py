from dataclasses import dataclass

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import TemplateView

from pyview_map.views.components.dynamic_map import MapDriver
from pyview_map.views.components.dynamic_list import ListDriver


@dataclass
class DemoPageContext:
    last_event: str = ""


class DemoLiveView(TemplateView, LiveView[DemoPageContext]):
    """Demo page hosting a DynamicMapComponent and DynamicListComponent side by side.

    Usage:
        app.add_live_view("/map_list_demo", DemoLiveView)
    """

    tick_interval: float = 1.2

    async def mount(self, socket: LiveViewSocket[DemoPageContext], session):
        self._map = MapDriver("map_list_demo-map")
        self._list = ListDriver("map_list_demo-list")
        socket.context = DemoPageContext()
        if socket.connected:
            self._map.connect()
            self._list.connect()
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DemoPageContext]):
        if event.name != "tick":
            return
        await self._map.tick(socket)
        await self._list.tick(socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DemoPageContext]):
        self._map.clear_ops()
        self._list.clear_ops()
        summary = self._map.handle_event(event, payload) or self._list.handle_event(event, payload)
        if summary:
            socket.context.last_event = summary

    def template(self, assigns: DemoPageContext, meta: PyViewMeta):
        last_event = assigns.last_event
        map_comp = self._map.render()
        list_comp = self._list.render()

        event_line = t'<div class="text-xs font-mono text-gray-600 truncate">{last_event}</div>' if last_event else t'<div class="text-xs text-gray-400">No events yet</div>'

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Map + List Demo</h1>
        <p class="text-sm text-gray-500 mb-6">
            Two independent components — map (<code>map_list_demo-map</code>) and list (<code>map_list_demo-list</code>) — driven by the JSON-RPC API.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2">
                <h2 class="text-sm font-semibold text-gray-700 mb-2">Map</h2>
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    {map_comp}
                </div>
            </div>
            <div class="lg:col-span-1">
                <h2 class="text-sm font-semibold text-gray-700 mb-2">List</h2>
                {list_comp}
            </div>
        </div>
        <div class="border-t border-gray-200 pt-3 mt-4">
            {event_line}
        </div>
    </div>
</div>"""
