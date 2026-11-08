"""Loopback-only single-worker launcher for the local historical demonstration."""

import argparse
import logging
from pathlib import Path

import uvicorn

from retail_forecasting.service.app import LOGGER, create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local historical retail forecast demo; binds only to 127.0.0.1")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    LOGGER.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False
    uvicorn.run(create_app(args.root), host="127.0.0.1", port=args.port,
        workers=1, access_log=False, log_level="warning", server_header=False)


if __name__ == "__main__":
    main()
