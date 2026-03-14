import logging

import uvicorn

from places_backend.settings import settings
from places_backend.parks_service import app  # noqa: F401 — uvicorn needs this in scope


def main():
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )

    uvicorn.run("places_backend.parks_service:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
