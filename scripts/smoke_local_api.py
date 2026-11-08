"""Start/stop our own loopback server and record real local HTTP smoke evidence."""

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/generated/service" / ("smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    started = time.perf_counter()
    with (output / "server.log").open("x", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-u", "-m", "retail_forecasting.service", "--root", str(root), "--port", str(port)],
            cwd=root, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as client:
                deadline = time.perf_counter() + 25
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Local server exited; inspect the saved server log")
                    try:
                        ready = client.get("/ready")
                        if ready.status_code == 200:
                            break
                        if ready.status_code == 503:
                            raise RuntimeError(f"Artifacts not ready: {ready.json()['error_code']}")
                    except httpx.ConnectError:
                        pass
                    if time.perf_counter() > deadline:
                        raise TimeoutError("Local API readiness exceeded 25 seconds")
                    time.sleep(.1)
                process_to_ready_ms = (time.perf_counter() - started) * 1000
                checks = {}
                for path in ("/health", "/ready", "/metadata", "/openapi.json", "/docs"):
                    response = client.get(path)
                    assert response.status_code == 200, response.text
                    assert response.headers.get("x-request-id")
                    checks[path] = response.status_code
                metadata = client.get("/metadata").json()
                assert len(metadata["supported_skus"]) == 100 and len(metadata["supported_origins"]) == 20
                payload = {"sku": "21212", "origin": "2011-11-07", "horizon_days": 28}
                response = client.post("/forecast", json=payload)
                assert response.status_code == 200, response.text
                body = response.json()
                assert len(body["predictions"]) == 28 and body["predictions"][-1]["target_date"] == "2011-12-04"
                assert body["history_cutoff"] == "2011-11-06" and body["historical_demo"] and body["intervals_experimental"]
                assert "actual" not in response.text.lower() and "customer" not in response.text.lower()
                latencies = []
                for _ in range(20):
                    before = time.perf_counter()
                    result = client.post("/forecast", json=payload)
                    assert result.status_code == 200 and result.json() == body
                    latencies.append((time.perf_counter() - before) * 1000)
                for change in ({"sku": "unknown"}, {"origin": "2011-08-15"}, {"horizon_days": 7}):
                    assert client.post("/forecast", json={**payload, **change}).status_code == 422
                report = {"status": "PASS", "transport": "real HTTP on 127.0.0.1; our subprocess stopped after smoke test",
                    "service_version": body["service_version"], "port": port, "endpoint_statuses": checks,
                    "forecast_status": 200, "invalid_requests_status": 422,
                    "artifact_startup_ms": ready.json()["startup_ms"], "process_to_ready_ms": process_to_ready_ms,
                    "warm_http_samples": len(latencies), "warm_http_median_ms": float(np.median(latencies)),
                    "warm_http_p95_ms": float(np.quantile(latencies, .95)), "warm_http_min_ms": float(min(latencies)),
                    "warm_http_max_ms": float(max(latencies)), "latency_scope": "sequential local HTTP response including client parsing; not a load test",
                    "request": payload, "first_prediction": body["predictions"][0], "prediction_count": 28}
                for name, value in (("smoke.json", report), ("example-response.json", body), ("metadata.json", metadata)):
                    with (output / name).open("x", encoding="utf-8") as stream:
                        json.dump(value, stream, indent=2)
                        stream.write("\n")
                print(json.dumps(report, indent=2), flush=True)
                print(f"Saved {output}", flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
