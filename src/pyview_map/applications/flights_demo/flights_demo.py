import asyncio
import logging
from dataclasses import dataclass

from pyview.template import TemplateView
from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket
from pyview.live_view import Session
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta

from pyview_map.components.dynamic_map import MapDriver

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from jrpc_common.jrpc_model import JSONRPCNotification, JSONRPCRequest, JSONRPCResponse

LOG = logging.getLogger(__name__)

FLIGHTS_SERVICE_URL = "http://localhost:8300/api"
FLIGHTS_SERVICE_TOKEN = "tok-acme-001"
BFF_CALLBACK_URL = "http://localhost:8123/api"


@dataclass
class FlightsViewContext:
    last_event: str = ""


class FlightsView(TemplateView, LiveView[FlightsViewContext]):
    base_channel: str = "flights"

    async def mount(self, socket: LiveViewSocket[FlightsViewContext], session: Session):
        self._map = MapDriver(f"{self.base_channel}-map")
        self._subscribe_task: asyncio.Task | None = None
        socket.context = FlightsViewContext()

        if socket.connected:
            await self._map.connect(socket)

    async def _subscribe_to_flights(self):
        """Open BE→BFF SSE channel via flights.subscribe.

        The BE uses a reverse connection to push airport markers and
        live flight positions via JSON-RPC calls back to the BFF.
        """
        try:
            async with ClientRPC(base_url=FLIGHTS_SERVICE_URL, auth_token=FLIGHTS_SERVICE_TOKEN) as rpc:
                req = JSONRPCRequest(
                    method="flights.subscribe",
                    params={
                        "callback_url": BFF_CALLBACK_URL,
                        "map_channel": f"{self.base_channel}-map",
                        "map_cid": self._map.cid,
                    },
                )
                async for msg in rpc.send_request(req):
                    match msg:
                        case JSONRPCNotification():
                            LOG.info("BE notification: %s", msg.method)
                        case JSONRPCResponse():
                            LOG.info("flights.subscribe stream closed: %s", msg.result)
                            break
        except asyncio.CancelledError:
            LOG.info("flights subscription cancelled")
        except Exception:
            LOG.exception("Failed to subscribe to flights from BE (%s)", FLIGHTS_SERVICE_URL)

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[FlightsViewContext]):
        await self._map.handle_info(event, socket)

    async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[FlightsViewContext]):
        self._map.clear_ops()
        summary = self._map.handle_event(event, payload)
        if summary:
            socket.context.last_event = summary

        if event == "map-ready" and self._subscribe_task is None:
            LOG.info("map ready — subscribing to flights BE")
            self._subscribe_task = asyncio.create_task(self._subscribe_to_flights())

    async def disconnect(self, socket: ConnectedLiveViewSocket[FlightsViewContext]):
        LOG.info("disconnecting")
        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()
        self._map.disconnect()

    def template(self, assigns: FlightsViewContext, meta: PyViewMeta):
        last_event = assigns.last_event
        map_comp = self._map.render()

        event_line = (
            t'<div class="text-xs font-mono text-gray-600 truncate">{last_event}</div>'
            if last_event
            else t'<div class="text-xs text-gray-400">No events yet</div>'
        )

        return t"""<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-1">Flights Demo</h1>
        <p class="text-sm text-gray-500 mb-6">
            BE simulates flights and pushes real-time positions via reverse JSON-RPC connection.
        </p>
        {map_comp}
        <div class="border-t border-gray-200 pt-3 mt-4">
            {event_line}
        </div>
    </div>
</div>"""
