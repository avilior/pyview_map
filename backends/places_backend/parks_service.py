"""Parks Service — the Backend (BE).

Exposes national park data via JSON-RPC over MCP.
The BFF (PyView server) connects here on mount to fetch park data.

    cd backends/places_backend && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200
"""

import asyncio
import logging

import uvicorn
from fastapi import FastAPI

from http_stream_client.jsonrpc.client_sdk import ClientRPC
from http_stream_transport.jsonrpc.handler_meta import RequestInfo
from http_stream_transport.jsonrpc.jrpc_service import jrpc_service
from http_stream_transport.server.mcp_router import router as mcp_router
from pyview_map.openrpc import setup_rpc_docs
from jrpc_common.jrpc_model import JSONRPCRequest, JSONRPCResponse, JSONRPCNotification

from pyview_map.components.dynamic_list.models.list_events import (
    NOTIFICATION_METHOD as LIST_NOTIFICATION_METHOD,
    ListItemClickEvent,
    ListItemOpEvent,
    ListReadyEvent,
    parse_list_event,
)

from parks import national_parks

LOG = logging.getLogger(__name__)

BFF_TOKEN = "tok-acme-001"


async def _send(rpc: ClientRPC, method: str, params: dict | None = None) -> None:
    """Fire a JSON-RPC request and consume the response."""
    req = JSONRPCRequest(method=method, params=params or {})
    async for resp in rpc.send_request(req):
        pass


async def _reverse_connection(
    callback_url: str, list_channel: str, list_cid: str, map_channel: str, map_cid: str
) -> None:
    """Connect back to the BFF: wait for components, populate list, react to events."""
    LOG.info(
        "reverse connection → %s (list=%s/%s, map=%s/%s)", callback_url, list_channel, list_cid, map_channel, map_cid
    )
    try:
        async with ClientRPC(base_url=callback_url, auth_token=BFF_TOKEN) as rpc:
            req = JSONRPCRequest(method="bff.subscribe")
            populated = False

            async for msg in rpc.send_request(req):
                match msg:
                    case JSONRPCNotification() if msg.method == LIST_NOTIFICATION_METHOD:
                        evt = parse_list_event(msg.params)
                        match evt:
                            case ListReadyEvent() if (
                                evt.channel == list_channel and evt.cid == list_cid and not populated
                            ):
                                populated = True
                                LOG.info("list ready — populating %d parks", len(national_parks))
                                for np in national_parks.values():
                                    await _send(
                                        rpc,
                                        "list.add",
                                        {
                                            "id": np.name,
                                            "label": np.name,
                                            "subtitle": np.description,
                                            "channel": list_channel,
                                            "cid": list_cid,
                                            "data": {"icon": np.icon},
                                        },
                                    )
                            case ListItemOpEvent(op="add") if evt.channel == list_channel:
                                park = national_parks.get(evt.id)
                                if park:
                                    LOG.info("list add → %s, adding marker", evt.id)
                                    await _send(
                                        rpc,
                                        "markers.add",
                                        {
                                            "id": park.name,
                                            "name": park.name,
                                            "latLng": park.lat_lng.to_list(),
                                            "icon": park.icon,
                                            "channel": map_channel,
                                            "cid": map_cid,
                                        },
                                    )
                            case ListItemClickEvent() if evt.channel == list_channel and evt.cid == list_cid:
                                park = national_parks.get(evt.id)
                                if park:
                                    LOG.info("click → %s, sending setView", evt.id)
                                    await _send(
                                        rpc,
                                        "map.setView",
                                        {
                                            "latLng": park.lat_lng.to_list(),
                                            "zoom": 12,
                                            "channel": map_channel,
                                            "cid": map_cid,
                                        },
                                    )

                    case JSONRPCResponse():
                        LOG.info("reverse connection: event stream ended")
                        break

    except asyncio.CancelledError:
        LOG.info("reverse connection cancelled")
    except Exception:
        LOG.exception("reverse connection failed")


@jrpc_service.request("parks.subscribe")
async def parks_subscribe(
    info: RequestInfo, callback_url: str, list_channel: str, list_cid: str, map_channel: str, map_cid: str
) -> asyncio.Queue:
    """Establish BE→BFF SSE channel and spawn reverse connection."""
    LOG.info(
        "BFF subscribed: list=%s/%s, map=%s/%s, callback=%s", list_channel, list_cid, map_channel, map_cid, callback_url
    )
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    asyncio.create_task(_reverse_connection(callback_url, list_channel, list_cid, map_channel, map_cid))
    return queue


@jrpc_service.request("parks.list")
def parks_list() -> list[dict]:
    return [
        {"name": np.name, "lat_lng": np.lat_lng.to_list(), "description": np.description, "icon": np.icon}
        for np in national_parks.values()
    ]


app = FastAPI(title="Parks Service")
app.include_router(mcp_router, prefix="/api")

setup_rpc_docs(
    app,
    jrpc_service,
    title="Parks Service",
    description="National parks data backend — exposes park data via JSON-RPC",
    prefix="/api",
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )

    uvicorn.run("parks_service:app", host="0.0.0.0", port=8200, reload=False)
