"""Readiness check using only Python's standard library."""

import sys
from urllib.request import urlopen


def main():
    try:
        with urlopen("http://127.0.0.1:8000/ready", timeout=3) as response:
            return 0 if response.status == 200 else 1
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
