import logging
import os

import uvicorn

LOG = logging.getLogger(__name__)

FE_PORT = int(os.environ.get("FE_PORT", 8001))


def main():
    LOG.info("Debate BFF  http://localhost:%d", FE_PORT)
    uvicorn.run("debate_bff.app:app", host="0.0.0.0", port=FE_PORT, reload=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )
    main()
