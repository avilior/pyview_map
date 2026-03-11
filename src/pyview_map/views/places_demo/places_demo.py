from dataclasses import dataclass
from pyview.template import TemplateView
from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket
from pyview.live_view import Session
from pyview.events import InfoEvent
from pyview_map.views.components.dynamic_list import ListDriver
from pyview_map.views.components.dynamic_map import MapDriver

from pyview.meta import PyViewMeta

import logging

LOG = logging.getLogger(__name__)


@dataclass
class PlacesViewContext:
    last_event: str = ""


class PlacesView(TemplateView, LiveView[PlacesViewContext]):

    base_channel: str = "places"
    tick_interval: float = 1.2

    async def mount(self, socket: LiveViewSocket[PlacesViewContext], session: Session):
        # PyView creates a separate LiveView instance for each phase:
        #   1. HTTP render — new instance + UnconnectedSocket → static HTML, then discarded
        #   2. WebSocket  — new instance + ConnectedLiveViewSocket → long-lived session
        # Drivers and subscriptions only matter on the connected instance.

        self._list_component = ListDriver(f"{self.base_channel}-list")
        self._map_component = MapDriver(f"{self.base_channel}-map")
        socket.context = PlacesViewContext()

        if socket.connected:
            self._list_component.connect()
            self._map_component.connect()
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[PlacesViewContext]):

        if event.name != "tick":
            return

        await self._list_component.tick(socket)
        await self._map_component.tick(socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[PlacesViewContext]):
        self._list_component.clear_ops()
        # This is wrong if we wanted to handle events within the Backend of the Frontend..... handle event logic should reside here instead of the list driver....this is because it is application logic.
        # The component event handler pushes the events to the Broadcaster.
        # The Broadcaster pushes the events to channel Which braodcasts the events to
        summary = self._list_component.handle_event(event, payload)

        if summary:
            socket.context.last_event = summary

    async def disconnect(self, socket: ConnectedLiveViewSocket[PlacesViewContext]):
      # custom cleanup here
      LOG.info("disconnecting")

    def template(self, assigns: PlacesViewContext, meta: PyViewMeta):

        last_event = assigns.last_event
        list_comp = self._list_component.render()
        map_comp = self._map_component.render()


        event_line = t'<div class="text-xs font-mono text-gray-600 truncate">{last_event}</div>' if last_event else t'<div class="text-xs text-gray-400">No events yet</div>'

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">List and Map Demo</h1>
        <p class="text-sm text-gray-500 mb-6">
            A list component —  (<code>zzz</code>) — and map component - (<code>yyy</code>) driven by the JSON-RPC API.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-1">
                <h2 class="text-sm font-semibold text-gray-700 mb-2">List of Parks</h2>
                {list_comp}
            </div>
            <div class="lg:col-span-2">
                <h2 class="text-sm font-semibold text-gray-700 mb-2">Map</h2>
                {map_comp}
            </div>
        </div>
        <div class="border-t border-gray-200 pt-3 mt-4">
            {event_line}
        </div>
    </div>
</div>"""

