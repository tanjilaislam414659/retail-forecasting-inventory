"""Verify an installed package from outside the source tree, without network access."""

from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Run this script with the project's .venv Python.")

    executable_dir = "Scripts" if sys.platform == "win32" else "bin"
    executable_name = "retail-forecasting.exe" if sys.platform == "win32" else "retail-forecasting"
    console = Path(sys.prefix) / executable_dir / executable_name
    if not console.is_file():
        raise SystemExit("Console command missing: install the project first.")

    with tempfile.TemporaryDirectory(prefix="retail-verify-") as directory:
        for command in (
            [sys.executable, "-I", "-m", "retail_forecasting", "check"],
            [str(console), "check"],
        ):
            result = subprocess.run(
                command, cwd=directory, capture_output=True, text=True, check=True
            )
            report = json.loads(result.stdout)
            if report.get("status") != "ok" or report.get("virtual_environment") is not True:
                raise SystemExit(f"Environment check failed: {report}")
            if report.get("version") != version("retail-forecasting"):
                raise SystemExit("Package metadata and CLI version differ.")

        result = subprocess.run(
            [sys.executable, "-I", "-m", "retail_forecasting", "--version"],
            cwd=directory, capture_output=True, text=True, check=True,
        )
        if result.stdout.strip() != version("retail-forecasting"):
            raise SystemExit("Version command failed.")

    print("PASS: installed module, console command, version, and environment isolation.")


if __name__ == "__main__":
    main()
