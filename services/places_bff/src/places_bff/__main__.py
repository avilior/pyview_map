import logging

import uvicorn

# Import component API modules BEFORE create_api() so JRPC methods are registered
import bff_engine.dynamic_map.api.marker_api  # noqa: F401
import bff_engine.dynamic_map.api.polyline_api  # noqa: F401
import bff_engine.dynamic_map.api.map_cmd_api  # noqa: F401
import bff_engine.dynamic_list.api.list_api  # noqa: F401

from bff_engine.bff_app import create_app
from bff_engine.bff_api import create_api
from places_bff.places_demo import PlacesView
from places_bff.settings import settings

LOG = logging.getLogger(__name__)

MAP_SCRIPT = '<script defer type="text/javascript" src="/static/dynamic_map.js"></script>'
LIST_SCRIPT = '<script defer type="text/javascript" src="/static/dynamic_list.js"></script>'

app = create_app(
    static_packages=["bff_engine.dynamic_map", "bff_engine.dynamic_list"],
    extra_head_html=MAP_SCRIPT + "\n" + LIST_SCRIPT,
)
api_app = create_api(
    title="Places BFF",
    description="Places list and map — marker, polyline, list, and map command APIs",
)


def main():
    display_host = "localhost" if settings.host == "0.0.0.0" else settings.host
    base = f"http://{display_host}:{settings.port}" if settings.port != 80 else f"http://{display_host}"

    LOG.info("Places Demo   %s/places_demo", base)
    LOG.info("API           %s/api/mcp", base)

    app.add_live_view("/places_demo", PlacesView)
    app.mount("/api", api_app)

    uvicorn.run("places_bff.__main__:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)

    main()
