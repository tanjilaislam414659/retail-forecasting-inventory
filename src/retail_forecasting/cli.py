"""Small, offline command-line entry point for checking the installation."""

import argparse
from importlib.metadata import version
import json
import platform
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    """Check installation, acquire public data, or prepare auditable sales panels."""
    parser = argparse.ArgumentParser(
        description="Retail Forecasting and Inventory Decision Support"
    )
    parser.add_argument("--version", action="version", version=version("retail-forecasting"))
    parser.add_argument("command", choices=["check", "acquire", "prepare", "baselines", "ridge", "boosting", "uncertainty", "freeze-final-evaluation", "final-evaluation"], help="project operation")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    args = parser.parse_args(argv)

    if args.command == "check":
        isolated = sys.prefix != sys.base_prefix
        print(json.dumps({
            "project": "retail-forecasting",
            "version": version("retail-forecasting"),
            "python": platform.python_version(),
            "executable": sys.executable,
            "virtual_environment": isolated,
            "status": "ok" if isolated else "use a virtual environment",
        }, indent=2))
        return 0 if isolated else 1
    if sys.prefix == sys.base_prefix:
        parser.error("Use the project's virtual environment for data operations.")
    if args.command == "acquire":
        from retail_forecasting.acquisition import acquire
        acquire(args.root.resolve())
    elif args.command == "prepare":
        from retail_forecasting.preparation import prepare
        prepare(args.root.resolve())
    elif args.command == "baselines":
        from retail_forecasting.baseline_validation import run_baselines
        run_baselines(args.root.resolve())
    elif args.command == "ridge":
        from retail_forecasting.ridge_experiment import run_ridge
        run_ridge(args.root.resolve())
    elif args.command == "boosting":
        from retail_forecasting.boosting_experiment import run_boosting
        run_boosting(args.root.resolve())
    elif args.command == "uncertainty":
        from retail_forecasting.uncertainty_experiment import run_uncertainty
        run_uncertainty(args.root.resolve())
    elif args.command == "freeze-final-evaluation":
        from retail_forecasting.final_evaluation import freeze_release
        freeze_release(args.root.resolve())
    elif args.command == "final-evaluation":
        from retail_forecasting.final_evaluation import run_final
        run_final(args.root.resolve())
    return 0
