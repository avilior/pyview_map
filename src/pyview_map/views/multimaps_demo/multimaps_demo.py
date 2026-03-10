from dataclasses import dataclass

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.live_view import Session
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template import TemplateView

from pyview_map.views.components.dynamic_map import MapDriver

import logging

LOG = logging.getLogger(__name__)


@dataclass
class MultiMapPageContext:
    last_marker_event: str = ""
    last_map_event: str = ""
    last_polyline_event: str = ""


class MultiMapLiveView(TemplateView, LiveView[MultiMapPageContext]):
    """
    Multi-map page with two side-by-side DynamicMapComponent instances.

    Each map has its own channel. External clients use the channel parameter
    to route markers/polylines/commands to a specific map.

    Usage:
        app.add_live_view("/mmap", MultiMapLiveView.with_maps(["left", "right"]))
    """

    channels: list[str] = []
    source_class: type = None  # type: ignore[assignment]
    tick_interval: float = 1.2

    @classmethod
    def with_maps(cls, channels: list[str], *, source_class: type | None = None, tick_interval: float = 1.2):
        """Return a configured MultiMapLiveView class."""
        return type(
            "MultiMapLiveView",
            (cls,),
            {
                "channels": channels,
                "source_class": source_class,
                "tick_interval": tick_interval,
            },
        )

    async def mount(self, socket: LiveViewSocket[MultiMapPageContext], session: Session):
        # PyView creates a separate LiveView instance for each phase:
        #   1. HTTP render — new instance + UnconnectedSocket → static HTML, then discarded
        #   2. WebSocket  — new instance + ConnectedLiveViewSocket → long-lived session
        # Drivers and subscriptions only matter on the connected instance.

        self._maps: dict[str, MapDriver] = {}
        for channel in self.channels:
            if self.source_class:
                self._maps[channel] = MapDriver(
                    channel,
                    source_class=self.source_class,
                    source_kwargs={"channel": channel},
                )
            else:
                self._maps[channel] = MapDriver(channel)

        socket.context = MultiMapPageContext()

        if socket.connected:
            for driver in self._maps.values():
                driver.connect()
            socket.schedule_info(InfoEvent("tick"), seconds=self.tick_interval)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[MultiMapPageContext]):
        if event.name != "tick":
            return
        for driver in self._maps.values():
            await driver.tick(socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[MultiMapPageContext]):
        for driver in self._maps.values():
            driver.clear_ops()
        # Try each driver until one handles the event
        for driver in self._maps.values():
            summary = driver.handle_event(event, payload)
            if summary:
                if event == "marker-event":
                    socket.context.last_marker_event = summary
                elif event == "polyline-event":
                    socket.context.last_polyline_event = summary
                elif event == "map-event":
                    socket.context.last_map_event = summary
                break

    async def disconnect(self, socket: ConnectedLiveViewSocket[MultiMapPageContext]):
        LOG.info("disconnecting")

    def template(self, assigns: MultiMapPageContext, meta: PyViewMeta):
        last_me = assigns.last_marker_event
        last_mae = assigns.last_map_event
        last_pe = assigns.last_polyline_event

        # Build a component for each map
        map_components = [(ch, driver.render()) for ch, driver in self._maps.items()]

        # For 2 maps: side-by-side layout
        left_id, left_comp = map_components[0] if len(map_components) > 0 else ("", t"")
        right_id, right_comp = map_components[1] if len(map_components) > 1 else ("", t"")

        # Server events
        marker_ev = t'<div class="text-blue-600 truncate" title="{last_me}">● {last_me}</div>' if last_me else t''
        map_ev = t'<div class="text-purple-600 truncate" title="{last_mae}">◆ {last_mae}</div>' if last_mae else t''
        polyline_ev = t'<div class="text-green-600 truncate" title="{last_pe}">▬ {last_pe}</div>' if last_pe else t''
        no_events = t'<div class="text-gray-400">No events yet</div>' if not (last_me or last_mae or last_pe) else t''

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">\U0001f4e1 Multi-Map Dashboard</h1>
        <p class="text-sm text-gray-500 mb-6">
            Two independent maps — use <code>channel</code> to route markers to a specific map.
        </p>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div>
                <h2 class="text-sm font-semibold text-gray-700 mb-2">{left_id}</h2>
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    {left_comp}
                </div>
            </div>
            <div>
                <h2 class="text-sm font-semibold text-gray-700 mb-2">{right_id}</h2>
                <div class="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    {right_comp}
                </div>
            </div>
        </div>
        <div class="border-t border-gray-200 pt-4">
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
</div>"""
