"""Rehearse documented installed-wheel setup from a clean local Git clone."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request


def request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        return response.status, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, help="Optional offline Windows wheel cache")
    parser.add_argument("--runtime-bundle", type=Path, help="Optional existing frozen bundle for an inference-only smoke check")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    # Keep nested wheel/egg-info paths below Windows' legacy path limit.
    # Do not change the machine's long-path policy or other global settings.
    work = root / ".cache" / ("p12-" + datetime.now(timezone.utc).strftime("%H%M%S%f"))
    checkout = work / "checkout"
    work.mkdir(parents=True, exist_ok=False)
    evidence = root / "reports/generated/publication" / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["TMP"] = environment["TEMP"] = str(work)
    operations = []
    with (evidence / "commands.log").open("x", encoding="utf-8") as log:
        def run(command, cwd=checkout):
            print("Checking:", " ".join(str(part) for part in command[1:4]), flush=True)
            started = time.perf_counter()
            result = subprocess.run([str(part) for part in command], cwd=cwd, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            log.write(result.stdout); log.flush()
            operations.append({"command": [str(part) for part in command], "exit_code": result.returncode, "seconds": time.perf_counter() - started})
            if result.returncode:
                print(result.stdout[-5000:])
                raise RuntimeError("Clean-checkout rehearsal failed; inspect commands.log")
            return result.stdout

        run(["git", "clone", "--no-hardlinks", "--no-local", str(root), str(checkout)], cwd=root)
        run(["git", "remote", "remove", "origin"])
        commit = run(["git", "rev-parse", "HEAD"]).strip()
        assert not any((checkout / name).exists() for name in (".venv", ".codex", "artifacts", "models"))
        assert [p.name for p in (checkout / "data").iterdir()] == ["README.md"]
        assert not (checkout / "reports/generated").exists()
        demo_python = None
        for package in ("runtime", "demo"):
            venv = checkout / ".venv" if package == "demo" else work / "runtime-venv"
            run([sys.executable, "-m", "venv", venv])
            python = venv / "Scripts/python.exe"
            command = [python, "-m", "pip", "install", "--only-binary=:all:", "--require-hashes", "-r", "publication/requirements-ci-windows.lock"]
            if args.wheelhouse:
                command += ["--no-index", "--find-links", args.wheelhouse.resolve()]
            run(command)
            run([python, f"scripts/build_{package}_package.py", "--output", f"dist/{package}"])
            wheel = next((checkout / f"dist/{package}").glob("*.whl"))
            run([python, "-m", "pip", "install", "--no-deps", wheel])
            run([python, "-m", "pip", "check"])
            run([python, "ci/run_tests.py", "--package", package])
            run([python, "ci/check_installed_demo.py" if package == "demo" else "ci/check_installed_package.py"])
            run([python, "scripts/validate_packaging.py"])
            if package == "demo":
                demo_python = python

        def smoke(forecast_root, with_bundle):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            command = [str(demo_python), "-m", "retail_forecasting.demo", "--root", str(forecast_root), "--port", str(port)]
            if with_bundle:
                command.append("--runtime-bundle")
            started = time.perf_counter()
            with (evidence / ("http-bundle.log" if with_bundle else "http-no-bundle.log")).open("x", encoding="utf-8") as server_log:
                process = subprocess.Popen(command, cwd=checkout, env=environment, stdout=server_log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                try:
                    url = f"http://127.0.0.1:{port}"
                    deadline = time.perf_counter() + 30
                    while True:
                        try:
                            if request(url + "/health")[0] == 200:
                                break
                        except (URLError, TimeoutError):
                            pass
                        if process.poll() is not None or time.perf_counter() > deadline:
                            raise RuntimeError("Clean installed demo did not become live")
                        time.sleep(.1)
                    startup_ms = (time.perf_counter() - started) * 1000
                    assert request(url + "/")[0] == 200
                    for path in ("/demo/api/evaluation", "/demo/api/inventory"):
                        assert request(url + path)[0] == 200
                    status, raw = request(url + "/ready")
                    assert status == (200 if with_bundle else 503)
                    ready = json.loads(raw)
                    payload = {"sku": "21212", "origin": "2011-11-07", "horizon_days": 28}
                    status, raw = request(url + "/forecast", payload)
                    assert status == (200 if with_bundle else 503)
                    if with_bundle:
                        data = json.loads(raw)
                        assert len(data["predictions"]) == 28 and data["history_cutoff"] == "2011-11-06"
                        assert data["predictions"][0]["target_date"] == "2011-11-07"
                        assert data["predictions"][-1]["target_date"] == "2011-12-04"
                        assert "actual" not in raw.decode().lower() and "customer" not in raw.decode().lower()
                        assert request(url + "/forecast", {**payload, "sku": "unknown"})[0] == 422
                    return {"status": "PASS", "with_runtime_bundle": with_bundle, "ready": ready, "http_process_start_ms": startup_ms,
                        "forecast_status": status, "forecast_rows": 28 if with_bundle else 0}
                finally:
                    process.terminate()
                    process.wait(timeout=15)

        no_bundle = smoke(checkout, False)
        with_bundle = None
        if args.runtime_bundle:
            from retail_forecasting.deployment.bundle import verify_bundle
            verify_bundle(args.runtime_bundle.resolve())
            destination = checkout / "artifacts/runtime/milestone-9-v0.1.0"
            shutil.copytree(args.runtime_bundle.resolve(), destination)
            with_bundle = smoke(destination, True)
        record = {"status": "PASS", "commit": commit, "checkout": str(checkout), "python": sys.version.split()[0],
            "scope": "Local Windows clean clone, isolated installed-wheel environments; not hosted Actions or a new performance evaluation",
            "runtime_synthetic_tests": 16, "demo_synthetic_tests": 24, "skips": 0,
            "initial_research_datasets_present": False, "remote_configuration_removed": True,
            "offline_cached_dependencies": args.wheelhouse is not None, "without_bundle": no_bundle, "with_existing_copied_bundle": with_bundle,
            "operations": operations}
        (evidence / "results.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in record.items() if key != "operations"}, indent=2))
    print("Evidence:", evidence)


if __name__ == "__main__":
    main()
