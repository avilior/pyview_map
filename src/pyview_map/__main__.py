# import pyview as _pyview_pkg
# from pathlib import Path

import uvicorn

from pyview_map.views.park_map_demo.park_map_demo import MapLiveView
from pyview_map.views.dynamic_map_demo import DynamicMapLiveView
from pyview_map.views.multimaps_demo import MultiMapLiveView
from pyview_map.views.components.dynamic_map.api.marker_api import api_app
from pyview_map.views.components.dynamic_map.sources.api_marker_source import APIMarkerSource
import pyview_map.views.components.dynamic_list.api.list_api  # noqa: F401 — registers JRPC methods
from pyview_map.views.map_list_demo import DemoLiveView
from pyview_map.app import app

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
    print("Starting Park Map server on http://localhost:8123/map")
    print("Dynamic Map available at    http://localhost:8123/dmap")
    print("Multi-Map available at      http://localhost:8123/mmap")
    print("Map + List demo at          http://localhost:8123/map_list_demo")
    print("Marker API available at     http://localhost:8123/api/mcp")

    app.add_live_view("/map", MapLiveView)
    app.add_live_view("/dmap", DynamicMapLiveView.with_source(APIMarkerSource, channel="dmap"))
    app.add_live_view("/mmap", MultiMapLiveView.with_maps(channels=["left", "right"]))
    app.add_live_view("/map_list_demo", DemoLiveView)
    app.mount("/api", api_app)

    uvicorn.run("pyview_map.__main__:app", host="0.0.0.0", port=8123, reload=False)


if __name__ == "__main__":
    main()
