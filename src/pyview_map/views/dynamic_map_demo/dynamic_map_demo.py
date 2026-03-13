from dataclasses import dataclass

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.live_view import Session
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import TemplateView

from pyview_map.views.components.dynamic_map import MapDriver

import logging

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parent LiveView — PubSub-driven updates, embeds map component
# ---------------------------------------------------------------------------

@dataclass
class DynamicMapPageContext:
    last_marker_event: str = ""
    last_map_event: str = ""
    last_polyline_event: str = ""


class DynamicMapLiveView(TemplateView, LiveView[DynamicMapPageContext]):
    """
    Generic real-time marker map.

    Usage:
        app.add_live_view("/dmap", DynamicMapLiveView.with_channel("dmap"))

    The view handles:
      - Initial marker render via Stream (inside DynamicMapComponent)
      - PubSub-driven updates from the JSON-RPC API
      - Marker and map events from Leaflet forwarded to handle_event
      - Map commands from PubSub pushed via socket.push_event
    """

    _channel: str = "dmap"

    @classmethod
    def with_channel(cls, channel: str = "dmap"):
        """Return a configured DynamicMapLiveView class bound to a channel."""
        return type(
            "DynamicMapLiveView",
            (cls,),
            {"_channel": channel},
        )

    async def mount(self, socket: LiveViewSocket[DynamicMapPageContext], session: Session):
        self._map = MapDriver(self._channel)
        socket.context = DynamicMapPageContext()

        if socket.connected:
            await self._map.connect(socket)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[DynamicMapPageContext]):
        await self._map.handle_info(event, socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[DynamicMapPageContext]):
        self._map.clear_ops()
        summary = self._map.handle_event(event, payload)
        if summary:
            if event == "marker-event":
                socket.context.last_marker_event = summary
            elif event == "polyline-event":
                socket.context.last_polyline_event = summary
            elif event == "map-event":
                socket.context.last_map_event = summary

    async def disconnect(self, socket: ConnectedLiveViewSocket[DynamicMapPageContext]):
        LOG.info("disconnecting")

    def template(self, assigns: DynamicMapPageContext, meta: PyViewMeta):
        last_me = assigns.last_marker_event
        last_mae = assigns.last_map_event
        last_pe = assigns.last_polyline_event

        comp = self._map.render()

        # Server events — conditionally rendered
        marker_ev = t'<div class="text-blue-600 truncate" title="{last_me}">● {last_me}</div>' if last_me else t''
        map_ev = t'<div class="text-purple-600 truncate" title="{last_mae}">◆ {last_mae}</div>' if last_mae else t''
        polyline_ev = t'<div class="text-green-600 truncate" title="{last_pe}">▬ {last_pe}</div>' if last_pe else t''
        no_events = t'<div class="text-gray-400">No events yet</div>' if not (last_me or last_mae or last_pe) else t''

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">\U0001f4e1 Dynamic Marker Map</h1>
        <p class="text-sm text-gray-500 mb-6">
            Markers are streamed in real-time — they appear, disappear, and move across the map.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div class="lg:col-span-1 flex flex-col gap-4">
                <div>
                    <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                        Activity Log
                    </h2>
                    <div id="dmap-log"
                         class="space-y-0.5 max-h-96 overflow-y-auto text-xs font-mono">
                    </div>
                </div>
                <div class="pt-3 border-t border-gray-200">
                    <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                        Server Events
                    </h2>
                    <div class="text-xs font-mono space-y-1">
                        {marker_ev}
                        {map_ev}
                        {polyline_ev}
                        {no_events}
                    </div>
                </div>
            </div>
            <div class="lg:col-span-3">
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-4">
                    {comp}
                </div>
            </div>
        </div>
    </div>
</div>"""
