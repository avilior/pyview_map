import logging
import os

import debate_backend.debate    # registers debate.* JSON-RPC handlers
import debate_backend.commands  # registers debate.command handler

import uvicorn
from http_stream_transport.server.app import app

BE_PORT = int(os.environ.get("BE_PORT", 8000))


def main():
    uvicorn.run(app, host="0.0.0.0", port=BE_PORT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s[%(levelname)s] @%(module)s|%(name)s|%(funcName)s|%(lineno)d # %(message)s",
        datefmt="%y%m%d %H:%M:%S",
    )
    main()
