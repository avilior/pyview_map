import asyncio
import logging
from dataclasses import dataclass

from pyview.template import TemplateView
from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket
from pyview.live_view import Session
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta

from pyview_map.components.dynamic_list import ListDriver
from pyview_map.components.dynamic_list.models.dlist_item import DListItem
from pyview_map.components.dynamic_map import MapDriver

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import JSONRPCNotification, JSONRPCRequest, JSONRPCResponse

LOG = logging.getLogger(__name__)

PARKS_SERVICE_URL = "http://localhost:8200/api"
PARKS_SERVICE_TOKEN = "tok-acme-001"
BFF_CALLBACK_URL = "http://localhost:8123/api"


def parks_item_renderer(item: DListItem):
    """Render a park list item with its emoji icon."""
    icon = item.data.get("icon", "")
    return t'<div class="flex items-center gap-2"><span class="text-lg">{icon}</span><div><div class="font-medium text-sm text-gray-800">{item.label}</div><div class="text-xs text-gray-500">{item.subtitle}</div></div></div>'


@dataclass
class PlacesViewContext:
    last_event: str = ""


class PlacesView(TemplateView, LiveView[PlacesViewContext]):

    base_channel: str = "places"

    async def mount(self, socket: LiveViewSocket[PlacesViewContext], session: Session):
        self._list_component = ListDriver(f"{self.base_channel}-list", item_renderer=parks_item_renderer)
        self._map_component = MapDriver(f"{self.base_channel}-map")
        self._subscribe_task: asyncio.Task | None = None
        socket.context = PlacesViewContext()

        if socket.connected:
            await self._list_component.connect(socket)
            await self._map_component.connect(socket)
            self._subscribe_task = asyncio.create_task(self._subscribe_to_parks())

    async def _subscribe_to_parks(self):
        """Open BE→BFF SSE channel via parks.subscribe.

        The BE uses a reverse connection to populate the list and map
        via JSON-RPC calls back to the BFF. This SSE stream stays open
        for the BE to push notifications at any time.
        """
        try:
            async with ClientRPC(base_url=PARKS_SERVICE_URL, auth_token=PARKS_SERVICE_TOKEN) as rpc:
                req = JSONRPCRequest(
                    method="parks.subscribe",
                    params={
                        "callback_url": BFF_CALLBACK_URL,
                        "list_channel": f"{self.base_channel}-list",
                        "list_cid": self._list_component.cid,
                        "map_channel": f"{self.base_channel}-map",
                        "map_cid": self._map_component.cid,
                    },
                )
                async for msg in rpc.send_request(req):
                    match msg:
                        case JSONRPCNotification():
                            LOG.info("BE notification: %s", msg.method)
                        case JSONRPCResponse():
                            LOG.info("parks.subscribe stream closed: %s", msg.result)
                            break
        except asyncio.CancelledError:
            LOG.info("parks subscription cancelled")
        except Exception:
            LOG.exception("Failed to subscribe to parks from BE (%s)", PARKS_SERVICE_URL)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[PlacesViewContext]):
        if await self._list_component.handle_info(event, socket):
            return
        if await self._map_component.handle_info(event, socket):
            return

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[PlacesViewContext]):
        self._list_component.clear_ops()
        self._map_component.clear_ops()

        summary = self._list_component.handle_event(event, payload)
        if not summary:
            summary = self._map_component.handle_event(event, payload)
        if summary:
            socket.context.last_event = summary

    async def disconnect(self, socket: ConnectedLiveViewSocket[PlacesViewContext]):
        LOG.info("disconnecting")
        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()

    def template(self, assigns: PlacesViewContext, meta: PyViewMeta):

        last_event = assigns.last_event
        list_comp = self._list_component.render()
        map_comp = self._map_component.render()

        event_line = t'<div class="text-xs font-mono text-gray-600 truncate">{last_event}</div>' if last_event else t'<div class="text-xs text-gray-400">No events yet</div>'

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Places Demo</h1>
        <p class="text-sm text-gray-500 mb-6">
            BE populates list and map via reverse JSON-RPC connection.
            Click a park — BE handles the event and pans the map.
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
