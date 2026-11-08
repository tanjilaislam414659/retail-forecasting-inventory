"""Check the running demo image; no evaluation, simulation, build or fitting."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
from uuid import uuid4

import httpx
import numpy as np

from retail_forecasting.service.artifacts import load_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="retail-forecasting-demo-m11-demo-1")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker CLI unavailable; container checks cannot run")
    output = root / "reports/generated/demo" / ("docker-smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    reference = load_engine(root)
    image = "retail-forecasting-demo:0.1.0"
    log = []

    def command(arguments, expected=0):
        result = subprocess.run([docker, *arguments], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log.append({"arguments": arguments, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode != expected:
            raise RuntimeError(f"Docker command failed: {arguments[:2]}")
        return result.stdout.strip()

    def validate_container(name):
        info = json.loads(command(["inspect", name]))[0]
        assert info["Config"]["User"] == "10001:10001"
        assert info["HostConfig"]["ReadonlyRootfs"]
        runtime = [mount for mount in info["Mounts"] if mount["Destination"] == "/runtime"]
        assert len(runtime) == 1 and not runtime[0]["RW"]
        assert all(binding["HostIp"] == "127.0.0.1" for binding in info["HostConfig"]["PortBindings"]["8000/tcp"])
        probe = "import os,pathlib; print(os.getuid()); p=pathlib.Path('/runtime/.demo-write-probe'); p.write_text('test')"
        assert command(["exec", name, "python", "-c", probe], expected=1) == "10001"
        return info

    try:
        info = validate_container(args.container)
        assert info["State"]["Health"]["Status"] == "healthy"
        image_info = json.loads(command(["image", "inspect", image]))[0]
        maximum_difference, parity_cases = 0.0, 0
        timings = []
        with httpx.Client(base_url=args.url, timeout=10, trust_env=False) as client:
            endpoints = ("/", "/health", "/ready", "/metadata", "/demo/assets/app.js", "/demo/assets/style.css", "/demo/api/evaluation", "/demo/api/inventory", "/docs")
            for endpoint in endpoints:
                assert client.get(endpoint).status_code == 200, endpoint
            ready = client.get("/ready").json()
            evaluation = client.get("/demo/api/evaluation").json()
            inventory = client.get("/demo/api/inventory").json()
            assert len(evaluation["validation"]["data"]["models"]) == 5
            assert len(evaluation["final_test"]["data"]["models"]) == 2
            assert len(inventory["data"]["scenarios"]) == 18
            for section, filename in ((evaluation["validation"], "validation"), (evaluation["final_test"], "final-test"), (inventory, "inventory")):
                expected = json.loads((root / f"src/retail_forecasting/demo/reports/{filename}.json").read_bytes())
                assert section["data"] == expected
            for sku in ("21212", "21166", "21533"):
                for origin in (reference.origins[0], reference.origins[-1]):
                    payload = {"sku": sku, "origin": origin.isoformat(), "horizon_days": 28}
                    started = time.perf_counter()
                    response = client.post("/forecast", json=payload)
                    timings.append((time.perf_counter() - started) * 1000)
                    assert response.status_code == 200
                    result = response.json()
                    expected = reference.predict(sku, origin).model_dump(mode="json")
                    assert len(result["predictions"]) == 28
                    assert {key: value for key, value in result.items() if key != "predictions"} == {key: value for key, value in expected.items() if key != "predictions"}
                    for got, want in zip(result["predictions"], expected["predictions"]):
                        assert got["target_date"] == want["target_date"] and got["horizon_day"] == want["horizon_day"]
                        a = [got["predicted_sales"]] + [got[f"interval_{level}"][end] for level in (80, 95) for end in ("lower", "upper")]
                        b = [want["predicted_sales"]] + [want[f"interval_{level}"][end] for level in (80, 95) for end in ("lower", "upper")]
                        np.testing.assert_allclose(a, b, rtol=1e-12, atol=1e-9)
                        maximum_difference = max(maximum_difference, float(np.max(np.abs(np.array(a) - b))))
                    parity_cases += 1
            invalid = ({"sku": "unknown"}, {"origin": "2026-11-07"}, {"origin": "invalid"}, {"horizon_days": 7}, {"unexpected": True})
            for update in invalid:
                assert client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07", **update}).status_code == 422
        command(["exec", args.container, "python", "-m", "retail_forecasting.deployment.healthcheck"])
        bundle = root / "artifacts/runtime/milestone-9-v0.1.0"
        contract = json.loads((bundle / "service/artifact-contract.json").read_bytes())
        failures = {}
        for kind in ("missing", "corrupt"):
            with tempfile.TemporaryDirectory(prefix="demo-docker-", dir=root / ".cache") as directory:
                fixture = Path(directory) / "bundle"
                shutil.copytree(bundle, fixture)
                target = fixture / contract["artifacts"]["quantiles"]["path"]
                if kind == "missing":
                    target.unlink()
                else:
                    target.write_bytes(b"CORRUPT DISPOSABLE CHECK COPY")
                name = "retail-demo-check-" + uuid4().hex[:12]
                try:
                    started = time.perf_counter()
                    command(["run", "-d", "--name", name, "--publish", "127.0.0.1::8000", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--mount", f"type=bind,source={fixture},target=/runtime,readonly", image])
                    port = command(["port", name, "8000/tcp"]).rsplit(":", 1)[1]
                    with httpx.Client(base_url="http://127.0.0.1:" + port, timeout=3, trust_env=False) as client:
                        deadline = time.perf_counter() + 40
                        while True:
                            try:
                                if client.get("/health").status_code == 200:
                                    break
                            except httpx.TransportError:
                                pass
                            if time.perf_counter() > deadline:
                                raise TimeoutError("Failure-state container did not start")
                            time.sleep(.1)
                        assert client.get("/").status_code == 200
                        assert client.get("/demo/api/evaluation").json()["final_test"]["status"] == "available"
                        bad_ready = client.get("/ready")
                        assert bad_ready.status_code == 503
                        assert client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07"}).status_code == 503
                        failures[kind] = {"ready": bad_ready.json(), "process_start_ms": (time.perf_counter() - started) * 1000}
                    command(["exec", name, "python", "-m", "retail_forecasting.deployment.healthcheck"], expected=1)
                finally:
                    command(["rm", "-f", name])
        result = {"status": "PASS", "image_id": image_info["Id"], "image_size_bytes": image_info["Size"], "healthy": True,
            "non_root_uid": 10001, "read_only_runtime_write_rejected": True, "read_only_root": True, "loopback_publication": True,
            "ready": ready, "endpoint_checks": list(endpoints), "invalid_requests_rejected": len(invalid),
            "parity_cases": parity_cases, "dated_predictions": parity_cases * 28, "numeric_values": parity_cases * 28 * 5,
            "maximum_absolute_numeric_difference": maximum_difference, "rtol": 1e-12, "atol": 1e-9,
            "forecast_http_ms": {"samples": len(timings), "minimum": min(timings), "median": statistics.median(timings), "maximum": max(timings)},
            "runtime_failure_checks": failures, "packaged_saved_report_parity": True,
            "scope": "Engineering regression only; no evaluation or inventory replay; hosted Actions pending"}
        (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        print(f"Saved {output}")
    finally:
        (output / "docker-log.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
