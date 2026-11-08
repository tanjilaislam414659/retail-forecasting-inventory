"""Build self-contained runtime sdist/wheel from an explicit source allowlist."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CORE = ["src/retail_forecasting/__init__.py", "src/retail_forecasting/baselines.py", "src/retail_forecasting/uncertainty.py"]


def stage_sources(root, destination):
    files = [root / name for name in CORE]
    for name in ("service", "deployment"):
        files.extend(sorted((root / "src/retail_forecasting" / name).glob("*.py")))
    files += [root / "src/retail_forecasting/deployment/runtime-code.json"]
    for source in files:
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(root / "packaging/runtime/pyproject.toml", destination / "pyproject.toml")
    shutil.copyfile(root / "deployment/README.md", destination / "README.md")
    for name in ("LICENSE", "DATA-LICENSE.md", "licenses/CC-BY-4.0-NOTICE.txt"):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root / "dist/runtime")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite existing package artifacts; choose a new empty output directory")
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runtime-package-", dir=cache) as directory:
        stage = Path(directory)
        stage_sources(root, stage)
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = "1793491200"
        environment["TMP"] = environment["TEMP"] = str(cache.resolve())
        subprocess.run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output), str(stage)],
            env=environment, check=True)


if __name__ == "__main__":
    main()
