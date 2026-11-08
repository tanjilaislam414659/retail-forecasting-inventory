"""Build a separate demo wheel with static assets and small saved reports."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from build_runtime_package import stage_sources


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root / "dist/demo")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite package artifacts")
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="demo-package-", dir=cache) as directory:
        stage = Path(directory)
        stage_sources(root, stage)
        shutil.copytree(root / "src/retail_forecasting/demo", stage / "src/retail_forecasting/demo", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(root / "packaging/demo/pyproject.toml", stage / "pyproject.toml")
        shutil.copyfile(root / "demo/README.md", stage / "README.md")
        environment = os.environ.copy()
        environment["TMP"] = environment["TEMP"] = str(cache.resolve())
        environment["SOURCE_DATE_EPOCH"] = "1793491200"
        subprocess.run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output), str(stage)], env=environment, check=True)


if __name__ == "__main__":
    main()
