# import pyview as _pyview_pkg
# from pathlib import Path

import uvicorn

from pyview_map.views.park_map_demo.park_map_demo import MapLiveView
from pyview_map.views.dynamic_map_demo import DynamicMapLiveView
from pyview_map.views.multimaps_demo import MultiMapLiveView
from pyview_map.views.places_demo import PlacesView
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

    LOG.info("Starting Park Map server on http://localhost:8123/map")
    LOG.info("Dynamic Map available at    http://localhost:8123/dmap")
    LOG.info("Multi-Map available at      http://localhost:8123/mmap")
    LOG.info("Map + List demo at          http://localhost:8123/map_list_demo")
    LOG.info("Marker API available at  http://localhost:8123/api/mcp")
    LOG.info("Places Demo              http://localhost:8123/places_demo")

    app.add_live_view("/map", MapLiveView)
    app.add_live_view("/dmap", DynamicMapLiveView.with_source(channel="dmap"))
    app.add_live_view("/mmap", MultiMapLiveView.with_maps(channels=["left", "right"]))
    app.add_live_view("/map_list_demo", DemoLiveView)
    app.add_live_view("/places_demo", PlacesView)
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
