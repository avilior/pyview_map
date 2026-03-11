# import pyview as _pyview_pkg
# from pathlib import Path

import json
import uvicorn

# ---------------------------------------------------------------------------
# Monkey-patch: pyview's send_info() doesn't flush pending push_events
# (they only get sent after handle_event, not handle_info). This means
# socket.push_event() called during a tick never reaches the browser.
# Patch send_info to include pending_events in the diff payload.
# Remove this once pyview-web is fixed upstream.
# ---------------------------------------------------------------------------
import pyview.live_socket as _live_socket

_original_send_info = _live_socket.ConnectedLiveViewSocket.send_info


async def _patched_send_info(self, event):
    await self.liveview.handle_info(event, self)

    rendered = await self.render_with_components()
    diff = self.diff(rendered)

    if self.pending_events:
        diff["e"] = self.pending_events
        self.pending_events = []

    resp = [None, None, self.topic, "diff", diff]

    try:
        await self.websocket.send_text(json.dumps(resp))
    except Exception:
        for id in list(self.scheduled_jobs):
            try:
                self.scheduler.remove_job(id)
            except Exception:
                pass


_live_socket.ConnectedLiveViewSocket.send_info = _patched_send_info

from pyview_map.views.dynamic_map_demo import DynamicMapLiveView
from pyview_map.views.multimaps_demo import MultiMapLiveView
from pyview_map.views.places_demo import PlacesView
from pyview_map.views.image_list_demo import ImageListView
from pyview_map.views.components.dynamic_map.api.marker_api import api_app
import pyview_map.views.components.dynamic_list.api.list_api  # noqa: F401 — registers JRPC methods
from pyview_map.views.map_list_demo import DemoLiveView
from pyview_map.app import app

import logging

LOG = logging.getLogger(__name__)

# app = PyView()
# app.rootTemplate = defaultRootTemplate(css=Markup(
#     '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />'
#     '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
#     '<script src="https://cdn.tailwindcss.com"></script>'
#     '<script defer src="/assets/map.js"></script>'
# ))
# app.add_live_view("/map", MapLiveView)

# _pyview_static = Path(_pyview_pkg.__file__).parent / "static"
# _app_static = Path(__file__).parent / "static"
# app.mount("/static", StaticFiles(directory=str(_pyview_static)), name="static")
# app.mount("/assets", StaticFiles(directory=str(_app_static)), name="assets")


def main():

    LOG.info("Dynamic Map available at    http://localhost:8123/dmap")
    LOG.info("Multi-Map available at      http://localhost:8123/mmap")
    LOG.info("Map + List demo at          http://localhost:8123/map_list_demo")
    LOG.info("Marker API available at  http://localhost:8123/api/mcp")
    LOG.info("Places Demo              http://localhost:8123/places_demo")
    LOG.info("Image List Demo          http://localhost:8123/image_list")

    app.add_live_view("/dmap", DynamicMapLiveView.with_source(channel="dmap"))
    app.add_live_view("/mmap", MultiMapLiveView.with_maps(channels=["left", "right"]))
    app.add_live_view("/map_list_demo", DemoLiveView)
    app.add_live_view("/places_demo", PlacesView)
    app.add_live_view("/image_list", ImageListView)
    app.mount("/api", api_app)

    uvicorn.run("pyview_map.__main__:app", host="0.0.0.0", port=8123, reload=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)

    main()
