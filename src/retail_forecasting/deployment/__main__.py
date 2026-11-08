"""Container entry point: explicit all-interface binding; host publish is loopback."""

import argparse
import logging
from pathlib import Path

import uvicorn

from retail_forecasting.deployment import __version__
from retail_forecasting.deployment.bundle import load_runtime_engine
from retail_forecasting.service.app import LOGGER, create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Historical-demo runtime; engineering version " + __version__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--root", type=Path, default=Path("/runtime"))
    parser.add_argument("--host", choices=["0.0.0.0", "127.0.0.1"], default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    LOGGER.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False
    uvicorn.run(create_app(args.root, loader=load_runtime_engine), host=args.host, port=args.port,
        workers=1, access_log=False, log_level="warning", server_header=False)


if __name__ == "__main__":
    main()
