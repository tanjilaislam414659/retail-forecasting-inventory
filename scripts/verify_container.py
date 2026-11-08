"""Build/run local Docker integration if available; report blockers without installing."""

from datetime import datetime, timezone
from contextlib import closing
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/generated/deployment" / ("docker-check-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    default = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
    docker = shutil.which("docker") or (str(default) if default.is_file() else None)

    def save(report):
        (output / "docker.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        print(f"Saved {output}", flush=True)

    if docker is None:
        save({"status": "BLOCKED", "blocker": "Docker executable absent from PATH and standard Windows Docker Desktop CLI path. Daemon/build/run checks unavailable.",
            "container_execution_passed": False, "image_size_bytes": None, "container_startup_ms": None})
        return 2
    version = subprocess.run([docker, "version"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if version.returncode:
        save({"status": "BLOCKED", "blocker": "Docker CLI found, daemon/version request failed", "detail": version.stderr[-1000:],
            "container_execution_passed": False, "image_size_bytes": None, "container_startup_ms": None})
        return 2
    from retail_forecasting.deployment.bundle import verify_bundle
    from retail_forecasting.service.artifacts import load_engine
    bundle = root / "artifacts/runtime/milestone-9-v0.1.0"
    verify_bundle(bundle)
    reference = load_engine(root)
    image = "retail-forecasting-runtime:0.1.0"
    containers = []
    with (output / "docker.log").open("x", encoding="utf-8") as log:
        def command(arguments, expected=0):
            result = subprocess.run([docker] + arguments, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log.write(result.stdout + result.stderr)
            log.flush()
            if result.returncode != expected:
                raise RuntimeError("Docker check command failed; inspect saved docker.log")
            return result.stdout.strip()

        def start(mount):
            name = "retail-forecast-check-" + uuid4().hex[:12]
            command(["run", "-d", "--name", name, "--publish", "127.0.0.1::8000", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--mount", f"type=bind,source={mount},target=/runtime,readonly", image])
            containers.append(name)
            port = command(["port", name, "8000/tcp"]).rsplit(":", 1)[1]
            client = httpx.Client(base_url="http://127.0.0.1:" + port, timeout=3, trust_env=False)
            deadline = time.perf_counter() + 45
            while time.perf_counter() < deadline:
                try:
                    if client.get("/health").status_code == 200:
                        return name, client
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            client.close()
            raise TimeoutError("Container did not reach process liveness in 45 seconds")

        try:
            command(["build", "--platform", "linux/amd64", "--tag", image, "."])
            info = json.loads(command(["image", "inspect", image]))[0]
            assert info["Config"]["User"] == "10001:10001"
            started = time.perf_counter()
            name, client = start(bundle)
            startup_ms = (time.perf_counter() - started) * 1000
            maximum_difference = 0.
            with closing(client):
                for endpoint in ("/health", "/ready", "/metadata"):
                    assert client.get(endpoint).status_code == 200
                assert client.get("/ready").json()["status"] == "ready"
                metadata = client.get("/metadata").json()
                assert len(metadata["supported_skus"]) == 100 and len(metadata["supported_origins"]) == 20
                parity = 0
                for sku in ("21212", "21166", "21533"):
                    for origin in (reference.origins[0], reference.origins[-1]):
                        response = client.post("/forecast", json={"sku": sku, "origin": origin.isoformat()})
                        assert response.status_code == 200
                        result = response.json()
                        expected = reference.predict(sku, origin).model_dump(mode="json")
                        assert len(result["predictions"]) == 28
                        for got, want in zip(result["predictions"], expected["predictions"]):
                            assert got["target_date"] == want["target_date"] and got["horizon_day"] == want["horizon_day"]
                            a = [got["predicted_sales"]] + [got[f"interval_{level}"][end] for level in (80, 95) for end in ("lower", "upper")]
                            b = [want["predicted_sales"]] + [want[f"interval_{level}"][end] for level in (80, 95) for end in ("lower", "upper")]
                            np.testing.assert_allclose(a, b, rtol=1e-12, atol=1e-9)
                            maximum_difference = max(maximum_difference, float(np.max(np.abs(np.array(a) - b))))
                        parity += 1
                for invalid in ({"sku": "unknown"}, {"origin": "2026-11-04"}, {"horizon_days": 7}):
                    assert client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07", **invalid}).status_code == 422
            command(["exec", name, "python", "-m", "retail_forecasting.deployment.healthcheck"])
            failures = {}
            contract = json.loads((bundle / "service/artifact-contract.json").read_text())
            for kind in ("missing", "corrupt"):
                with tempfile.TemporaryDirectory(prefix="docker-fixture-", dir=root / ".cache") as directory:
                    fixture = Path(directory) / "bundle"
                    shutil.copytree(bundle, fixture)
                    target = fixture / contract["artifacts"]["quantiles"]["path"]
                    if kind == "missing":
                        target.unlink()
                    else:
                        target.write_bytes(b"CORRUPT TEST COPY")
                    bad_name, bad_client = start(fixture)
                    with closing(bad_client):
                        ready = bad_client.get("/ready")
                        assert ready.status_code == 503
                        assert bad_client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07"}).status_code == 503
                        failures[kind] = ready.json()["error_code"]
                    command(["exec", bad_name, "python", "-m", "retail_forecasting.deployment.healthcheck"], expected=1)
                    command(["rm", "-f", bad_name])
                    containers.remove(bad_name)
            save({"status": "PASS", "container_execution_passed": True, "image_id": info["Id"], "image_size_bytes": info["Size"],
                "container_startup_ms": startup_ms, "non_root_user": info["Config"]["User"], "parity_cases": parity,
                "parity_dated_predictions": parity * 28, "maximum_absolute_numeric_difference": maximum_difference,
                "relative_tolerance": 1e-12, "absolute_tolerance": 1e-9,
                "missing_corrupt_readiness": failures, "scope": "Local container integration only; no new performance evaluation or publication"})
        finally:
            for name in containers:
                subprocess.run([docker, "rm", "-f", name], cwd=root, capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
