"""Independent inventory-simulation entry point; frozen research CLI unchanged."""

import argparse
from pathlib import Path
import sys

from retail_forecasting.inventory.experiment import freeze_run, run


def main():
    parser = argparse.ArgumentParser(description="Fixed synthetic inventory-policy replay on validation only")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if sys.prefix == sys.base_prefix:
        parser.error("Use the project .venv Python")
    root = args.root.resolve()
    output = root / "data/inventory_simulation/v0.1.0"
    if args.freeze_only:
        freeze_run(root, output)
    else:
        run(root, output)


if __name__ == "__main__":
    main()
