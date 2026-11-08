"""Loopback by default; explicit container binding via the demo Compose file."""

import argparse
import logging
from pathlib import Path

import uvicorn

from retail_forecasting.demo.app import create_demo_app
from retail_forecasting.deployment.bundle import load_runtime_engine
from retail_forecasting.service.app import LOGGER
from retail_forecasting.service.artifacts import load_engine


def main():
    parser = argparse.ArgumentParser(description="Three-view historical forecasting demo 0.1.0")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runtime-bundle", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    LOGGER.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False
    uvicorn.run(create_demo_app(args.root, loader=load_runtime_engine if args.runtime_bundle else load_engine),
        host=args.host, port=args.port, workers=1, access_log=False, log_level="warning", server_header=False)


if __name__ == "__main__":
    main()
