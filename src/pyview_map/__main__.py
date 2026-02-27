# import pyview as _pyview_pkg
# from pathlib import Path

import uvicorn
# from markupsafe import Markup
# from pyview import PyView, defaultRootTemplate
# from starlette.staticfiles import StaticFiles

from pyview_map.views.maps.map import MapLiveView
from pyview_map.views.dynamic_map import DynamicMapLiveView
from pyview_map.views.dynamic_map.mock_generator import MockGenerator
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
    print("Starting PyView Map server on http://localhost:8123/map")
    print("Dynamic Map available at    http://localhost:8123/dmap")

    app.add_live_view("/map", MapLiveView)
    app.add_live_view("/dmap", DynamicMapLiveView.with_source(MockGenerator, initial_count=5))

    uvicorn.run("pyview_map.__main__:app", host="0.0.0.0", port=8123, reload=False)


if __name__ == "__main__":
    main()
