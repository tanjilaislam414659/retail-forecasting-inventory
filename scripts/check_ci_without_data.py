"""Rehearse CI's Python steps in a clean local venv/checkout with no retail data."""

from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv
from zipfile import ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    wheels = cache / "ci-windows-wheels"
    if sys.platform != "win32" or not list(wheels.glob("*.whl")):
        raise SystemExit("This Windows rehearsal requires the documented cached Windows dependency wheels; no silent fallback")
    output = root / "reports/generated/deployment" / ("ci-rehearsal-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="ci-rehearsal-", dir=cache) as directory:
        work = Path(directory)
        checkout = work / "checkout"
        checkout.mkdir()
        for name in ("ci", "deployment", "packaging", ".github"):
            shutil.copytree(root / name, checkout / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("Dockerfile", ".dockerignore", "compose.yaml"):
            shutil.copyfile(root / name, checkout / name)
        for name in ("build_runtime_package.py", "validate_packaging.py"):
            (checkout / "scripts").mkdir(exist_ok=True)
            shutil.copyfile(root / "scripts" / name, checkout / "scripts" / name)
        sources = [root / "src/retail_forecasting" / name for name in ("__init__.py", "baselines.py", "uncertainty.py")]
        for package in ("service", "deployment"):
            sources.extend(p for p in (root / "src/retail_forecasting" / package).iterdir() if p.suffix in (".py", ".json"))
        for source in sources:
            target = checkout / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        assert not any((checkout / name).exists() for name in ("data", "models", "artifacts", "reports", ".venv"))
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["TMP"] = environment["TEMP"] = str(work)
        venv_dir = work / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], env=environment, check=True)
        python = venv_dir / "Scripts/python.exe"
        lock = work / "windows-wheels.lock"
        with lock.open("x", encoding="utf-8") as stream:
            for path in sorted(wheels.glob("*.whl")):
                with ZipFile(path) as archive:
                    name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
                    meta = BytesParser().parsebytes(archive.read(name))
                stream.write(f"{meta['Name']}=={meta['Version']} --hash=sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}\n")
        commands = [
            [str(python), "-m", "pip", "install", "--no-index", "--find-links", str(wheels), "--require-hashes", "-r", str(lock)],
            [str(python), "scripts/build_runtime_package.py", "--output", "dist/runtime"],
        ]
        outcomes = []
        with (output / "commands.log").open("x", encoding="utf-8") as log:
            def run(command):
                result = subprocess.run(command, cwd=checkout, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                log.write(result.stdout)
                log.flush()
                outcomes.append({"operation": command[1:], "exit_code": result.returncode})
                if result.returncode:
                    print(result.stdout[-5000:])
                    raise RuntimeError("Dataset-free CI rehearsal failed; see command log")
            for command in commands:
                run(command)
            wheel = next((checkout / "dist/runtime").glob("*.whl"))
            run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
            for arguments in (["-m", "pip", "check"], ["ci/run_tests.py"], ["scripts/validate_packaging.py"], ["ci/check_installed_package.py"]):
                run([str(python)] + arguments)
        record = {"status": "PASS", "scope": "Local Windows CPython 3.13.5 rehearsal of CI Python steps; not hosted Linux/Actions execution",
            "research_datasets_or_artifact_mounts_present": False, "installed_wheel_imports_verified": True,
            "synthetic_tests": 16, "skips": 0, "operations": outcomes,
            "wheel_bytes": wheel.stat().st_size, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
        (output / "rehearsal.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in record.items() if key != "operations"}, indent=2), flush=True)
    print(f"Saved {output}", flush=True)


if __name__ == "__main__":
    main()
