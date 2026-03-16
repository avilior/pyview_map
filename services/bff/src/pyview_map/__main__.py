import uvicorn

from pyview_map.applications.flights_demo import FlightsView
from pyview_map.applications.places_demo import PlacesView
from pyview_map.api import api_app
from pyview_map.app import app
from pyview_map.settings import settings

import logging

LOG = logging.getLogger(__name__)


def main():
    display_host = "localhost" if settings.host == "0.0.0.0" else settings.host
    base = f"http://{display_host}:{settings.port}" if settings.port != 80 else f"http://{display_host}"

    LOG.info("Flights Demo  %s/flights", base)
    LOG.info("Places Demo   %s/places_demo", base)
    LOG.info("Marker API    %s/api/mcp", base)

    app.add_live_view("/flights", FlightsView)
    app.add_live_view("/places_demo", PlacesView)
    app.mount("/api", api_app)

    uvicorn.run("pyview_map.__main__:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)

    main()
